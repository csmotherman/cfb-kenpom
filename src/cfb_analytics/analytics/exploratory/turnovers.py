"""LEILA Exploratory: Turnover metrics (2025 research build).

Reuses Wave 2's exact, already-tested turnover-play classification
(`analytics/exploratory/drives.py`'s `_INTERCEPTION_SUBTYPES` /
`_LOST_FUMBLE_SUBTYPES` / `_SELF_RECOVERED_FUMBLE_SUBTYPES`, keyed on the
canonical `eventCategory == "TURNOVER"` + `eventSubtype`) rather than any of
this repo's other turnover-adjacent classifiers (`dropbacks.py`'s narrower
"standard dropback" population undercounts real interceptions by ~3x on 2025
data -- confirmed empirically, not fit for this purpose; `havoc.py`'s
drive-anchored classifier serves a different attribution philosophy). A
self-recovered fumble (`FUMBLE_RECOVERY_OWN`) is tracked for validation only
and never counted as a turnover, per the explicit fumble rule: possession
must actually change to the defense.

CFBD fumble-recovery mislabel override (added after a live spot-check on
UConn 2025): CFBD's own `eventSubtype`/`playType` field occasionally says
"Fumble Recovery (Own)" while CFBD's own `playText` for the SAME play names
a different team's player as the one who recovered it -- confirmed by
reading the raw CFBD payload directly, not a bug introduced anywhere in
this pipeline. A corpus-wide check found 83 such plays in the 2025
FBS-vs-FBS turnover-eligible population (out of 341 FUMBLE_RECOVERY_OWN
plays with a parseable "recovered by" clause) where the text unambiguously
names (a) a recovering team matching the DEFENSE, not the offense, and (b)
a recovering player different from the player who fumbled -- e.g. "Conner
Harrell fumbled, recovered by APP Jaelin Willis" while `offense` is
Charlotte. `_confirmed_opponent_recovery_from_text` below detects exactly
that pattern and nothing looser: same-player-name "recoveries" (13 cases in
the same corpus, e.g. "Trevon Tate fumbled, recovered by LT Trevon Tate")
are left alone as genuine self-recoveries even when the recovering team
token nominally matches the defense -- that pattern reads as CFBD's text
template duplicating the fumbling player's own name, not a real distinct
recovery (finding the true fumbler requires checking the name immediately
before the word "fumbled" -- which, on pass plays, is the receiver, not the
passer named at the start of the text -- via
`_FUMBLED_IMMEDIATELY_BEFORE_RE`, falling back to `_FUMBLED_AT_START_RE`
only for the minority of plays where no name repeats before "fumbled").
Team tokens are matched against the canonical team name via
`_team_token_matches` (prefix match, e.g. TOL/PUR/BALL, falling back to
`_TEAM_CODES` for acronym-style tokens like FIU that aren't a literal
prefix). The remaining 245 cases are genuinely ambiguous/garbled text
(field position markers doubling as a false team match, a recovering team
token that matches the offense not the defense, multi-fumble sequences,
etc.) and are left unclassified by the regex, falling through to trusting
the original eventSubtype, same as before this override existed.

Pass attempts = clean offensive scrimmage snaps tagged PASS_COMPLETION /
PASS_INCOMPLETE / PASS_TD, plus every interception (a merged
throw+interception-return row is excluded from the clean-snap population by
`isScrimmagePlay=False`, so it must be added back explicitly -- an
intercepted pass is still a real pass attempt). Verified no double-count
risk: interception rows never carry a PASS_* eventSubtype even on the
minority that do keep isScrimmagePlay=True.

Turnover EPA uses the existing canonical `classify_epa` (CFBD's own `ppa`)
on each classified turnover play, summed RAW/signed (not forced negative,
not magnitude-clipped) -- see the research report for concrete
counterintuitive-EPA examples this surfaced on interception/fumble returns
with substantial positive yardage, which is a methodology question for a
future task, not something silently corrected here.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from cfb_analytics.analytics.epa import classify_epa
from cfb_analytics.analytics.exploratory.drives import (
    _INTERCEPTION_SUBTYPES,
    _LOST_FUMBLE_SUBTYPES,
    _SELF_RECOVERED_FUMBLE_SUBTYPES,
)
from cfb_analytics.analytics.exploratory.series import _clean_snaps

TURNOVERS_VERSION = "turnovers-v2-fumble-recovery-text-override"

_PASS_ATTEMPT_SUBTYPES = {"PASS_COMPLETION", "PASS_INCOMPLETE", "PASS_TD"}

# CFBD's fumble grammar isn't fully consistent, so this uses two patterns,
# tried in order (both deliberately case-SENSITIVE, not re.I -- that's what
# an earlier version got wrong: re.I let a lowercase verb like "run" get
# swallowed into the captured name).
#
# 1. The player who actually fumbled almost always has their name repeated
#    immediately before the literal word "fumbled" -- true for both run
#    plays ("...Ahmad Hardy fumbled...") and, critically, pass plays, where
#    it correctly captures the RECEIVER rather than the passer named at the
#    start of the text ("Demond Williams Jr. pass complete to Omari Evans
#    for 13 yds Omari Evans fumbled..." -> "Omari Evans", not "Demond
#    Williams Jr.").
# 2. Falls back to the name at the very START of the text only when #1
#    doesn't match -- covers the shorter "<Name> run fumbled" phrasing with
#    no repeated name, where a lowercase verb sits directly before "fumbled"
#    so pattern #1 can't match, but the subject at the start is still the
#    fumbler.
_FUMBLED_IMMEDIATELY_BEFORE_RE = re.compile(r"([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,2})\s+fumbled")
_FUMBLED_AT_START_RE = re.compile(r"^([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,2})")
# "recovered by <TEAM> <player name...>", stopping at the next comma, " for",
# " return", or end of string -- matches CFBD's consistent recovery grammar.
_RECOVERED_BY_RE = re.compile(r"recovered by\s+([A-Za-z0-9.'-]+)\s+([A-Za-z .'\-]+?)(?:\s*,|\s+for|\s+return|\s*$)", re.I)

# Team name -> short display code, ported verbatim from web/lib/teamCode.ts
# (itself ported from site/site.js CFF.teamCode) so play-text team tokens
# like "FIU" resolve against the same codes the rest of the site already
# uses -- needed because acronym-style abbreviations (FIU for "Florida
# International") aren't a literal prefix of the canonical team name, so
# prefix matching alone (which correctly handles PUR/TOL/BALL-style codes)
# misses them.
_TEAM_CODES: dict[str, str] = {
    "Air Force": "AFA", "Akron": "AKR", "Alabama": "ALA", "App State": "APP",
    "Appalachian State": "APP", "Arizona": "ARIZ", "Arizona State": "ASU",
    "Arkansas": "ARK", "Arkansas State": "ARST", "Army": "ARMY", "Auburn": "AUB",
    "BYU": "BYU", "Ball State": "BALL", "Baylor": "BAY", "Boise State": "BOIS",
    "Boston College": "BC", "Bowling Green": "BGSU", "Buffalo": "BUF",
    "California": "CAL", "Central Michigan": "CMU", "Charlotte": "CLT",
    "Cincinnati": "CIN", "Clemson": "CLEM", "Coastal Carolina": "CCU",
    "Colorado": "COLO", "Colorado State": "CSU", "Delaware": "DEL", "Duke": "DUKE",
    "East Carolina": "ECU", "Eastern Michigan": "EMU", "Florida": "FLA",
    "Florida Atlantic": "FAU", "Florida International": "FIU", "Florida State": "FSU",
    "Fresno State": "FRES", "Georgia": "UGA", "Georgia Southern": "GASO",
    "Georgia State": "GAST", "Georgia Tech": "GT", "Hawai'i": "HAW", "Hawaii": "HAW",
    "Houston": "HOU", "Illinois": "ILL", "Indiana": "IND", "Iowa": "IOWA",
    "Iowa State": "ISU", "Jacksonville State": "JVST", "James Madison": "JMU",
    "Kansas": "KU", "Kansas State": "KSU", "Kennesaw State": "KENN", "Kent State": "KENT",
    "Kentucky": "UK", "LSU": "LSU", "Liberty": "LIB", "Louisiana": "UL",
    "Louisiana Tech": "LT", "Louisville": "LOU", "Marshall": "MRSH", "Maryland": "MD",
    "Massachusetts": "MASS", "Memphis": "MEM", "Miami": "MIA", "Miami (OH)": "M-OH",
    "Michigan": "MICH", "Michigan State": "MSU", "Middle Tennessee": "MTSU",
    "Minnesota": "MINN", "Mississippi State": "MSST", "Missouri": "MIZ",
    "Missouri State": "MOST", "NC State": "NCST", "Navy": "NAVY", "Nebraska": "NEB",
    "Nevada": "NEV", "New Mexico": "UNM", "New Mexico State": "NMSU",
    "North Carolina": "UNC", "North Dakota State": "NDSU", "North Texas": "UNT",
    "Northern Illinois": "NIU", "Northwestern": "NU", "Notre Dame": "ND", "Ohio": "OHIO",
    "Ohio State": "OSU", "Oklahoma": "OU", "Oklahoma State": "OKST", "Old Dominion": "ODU",
    "Ole Miss": "MISS", "Oregon": "ORE", "Oregon State": "ORST", "Penn State": "PSU",
    "Pittsburgh": "PITT", "Purdue": "PUR", "Rice": "RICE", "Rutgers": "RUTG",
    "SMU": "SMU", "Sacramento State": "SAC", "Sam Houston": "SHSU",
    "San Diego State": "SDSU", "San José State": "SJSU", "San Jose State": "SJSU",
    "South Alabama": "USA", "South Carolina": "SC", "South Florida": "USF",
    "Southern Miss": "USM", "Stanford": "STAN", "Syracuse": "SYR", "TCU": "TCU",
    "Temple": "TEM", "Tennessee": "TENN", "Texas": "TEX", "Texas A&M": "TAMU",
    "Texas State": "TXST", "Texas Tech": "TTU", "Toledo": "TOL", "Troy": "TROY",
    "Tulane": "TULN", "Tulsa": "TLSA", "UAB": "UAB", "UCF": "UCF", "UCLA": "UCLA",
    "UConn": "CONN", "UL Monroe": "ULM", "UNLV": "UNLV", "USC": "USC", "UTEP": "UTEP",
    "UTSA": "UTSA", "Utah": "UTAH", "Utah State": "USU", "Vanderbilt": "VAN",
    "Virginia": "UVA", "Virginia Tech": "VT", "Wake Forest": "WAKE", "Washington": "WASH",
    "Washington State": "WSU", "West Virginia": "WVU", "Western Kentucky": "WKU",
    "Western Michigan": "WMU", "Wisconsin": "WIS", "Wyoming": "WYO",
}


def _team_token_matches(token: str, team: str | None) -> bool:
    if not team:
        return False
    token_u, team_u = token.upper(), team.upper()
    if token_u == team_u or team_u.startswith(token_u):
        return True
    return _TEAM_CODES.get(team, "").upper() == token_u


def _confirmed_opponent_recovery_from_text(play: dict[str, Any]) -> bool:
    """True only when playText unambiguously contradicts a
    FUMBLE_RECOVERY_OWN subtype: a recovering team token matching the
    DEFENSE (not the offense) attached to a player name distinct from
    whoever fumbled. See the module docstring for how this threshold was
    chosen against the real 2025 corpus."""
    text = play.get("playText") or ""
    recovered = _RECOVERED_BY_RE.search(text)
    if not recovered:
        return False
    recover_team, recover_player = recovered.group(1).strip().rstrip(".,"), recovered.group(2).strip()
    offense, defense = play.get("offense"), play.get("defense")
    if _team_token_matches(recover_team, offense) or not _team_token_matches(recover_team, defense):
        return False
    fumbled = _FUMBLED_IMMEDIATELY_BEFORE_RE.search(text) or _FUMBLED_AT_START_RE.match(text.strip())
    fumble_player = fumbled.group(1).strip() if fumbled else None
    if fumble_player and fumble_player.lower() == recover_player.lower():
        return False
    return True


def classify_turnover_play(play: dict[str, Any]) -> str | None:
    if play.get("eventCategory") != "TURNOVER":
        return None
    subtype = play.get("eventSubtype")
    if subtype in _INTERCEPTION_SUBTYPES:
        return "interception"
    if subtype in _LOST_FUMBLE_SUBTYPES:
        return "lost_fumble"
    if subtype in _SELF_RECOVERED_FUMBLE_SUBTYPES:
        if _confirmed_opponent_recovery_from_text(play):
            return "lost_fumble"
        return "self_recovered_fumble"
    return None


def build_drive_turnover_record(drive: dict[str, Any], drive_plays: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One record per validated possession drive: this drive's turnover
    events, pass attempts, and turnover EPA -- everything needed to fold
    into per-team-game counts without re-walking plays a second time."""
    if not (drive.get("isPossessionDrive") is True and drive.get("driveValidationStatus") == "PASS" and drive.get("offense")):
        return None

    offense = drive["offense"]
    defense = drive.get("defense")
    game_id = str(drive.get("gameId") or "")

    interceptions = 0
    lost_fumbles = 0
    self_recovered_fumbles = 0
    turnover_epa_sum = 0.0
    turnover_plays: list[tuple[str, dict[str, Any], float | None]] = []

    for p in drive_plays:
        if p.get("offense") != offense:
            continue
        kind = classify_turnover_play(p)
        if kind == "interception" or kind == "lost_fumble":
            epa = classify_epa(p)
            if epa is not None:
                turnover_epa_sum += epa
            turnover_plays.append((kind, p, epa))
            if kind == "interception":
                interceptions += 1
            else:
                lost_fumbles += 1
        elif kind == "self_recovered_fumble":
            self_recovered_fumbles += 1

    pass_attempts = interceptions + sum(
        1 for p in _clean_snaps(drive_plays)
        if p.get("offense") == offense and p.get("eventSubtype") in _PASS_ATTEMPT_SUBTYPES
    )

    return {
        "gameId": game_id,
        "offense": offense,
        "defense": defense,
        "interceptions": interceptions,
        "lostFumbles": lost_fumbles,
        "selfRecoveredFumbles": self_recovered_fumbles,
        "turnoverEpaSum": turnover_epa_sum,
        "passAttempts": pass_attempts,
        "turnoverPlays": turnover_plays,
    }


def team_turnover_counts(drive_records: list[dict[str, Any]], fbs_teams: set[str] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """(gameId, team) -> raw offense/defense turnover counts. Skips any
    drive where either side isn't in `fbs_teams` when given (FBS-vs-FBS
    only)."""
    out: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: defaultdict(float))

    for d in drive_records:
        if d is None:
            continue
        offense, defense = d.get("offense"), d.get("defense")
        if fbs_teams is not None and (offense not in fbs_teams or defense not in fbs_teams):
            continue
        game_id = d["gameId"]

        if offense:
            o = out[(game_id, offense)]
            o["opponent"] = defense
            o["offensiveDrives"] += 1
            o["turnovers"] += d["interceptions"] + d["lostFumbles"]
            o["interceptions"] += d["interceptions"]
            o["lostFumbles"] += d["lostFumbles"]
            o["selfRecoveredFumbles"] += d["selfRecoveredFumbles"]
            o["passAttempts"] += d["passAttempts"]
            o["turnoverEpaSum"] += d["turnoverEpaSum"]

        if defense:
            de = out[(game_id, defense)]
            de["opponent"] = offense
            de["opponentDrives"] += 1
            de["takeaways"] += d["interceptions"] + d["lostFumbles"]
            de["interceptionsForced"] += d["interceptions"]
            de["fumbleRecoveries"] += d["lostFumbles"]
            de["opponentSelfRecoveredFumbles"] += d["selfRecoveredFumbles"]
            de["opponentPassAttempts"] += d["passAttempts"]
            de["opponentTurnoverEpaSum"] += d["turnoverEpaSum"]

    return out


_INT_FIELDS = ("offensiveDrives", "turnovers", "interceptions", "lostFumbles", "selfRecoveredFumbles", "passAttempts")
_DEF_INT_FIELDS = ("opponentDrives", "takeaways", "interceptionsForced", "fumbleRecoveries", "opponentSelfRecoveredFumbles", "opponentPassAttempts")


def finish_turnover_counts(counts: dict[str, Any]) -> dict[str, Any]:
    """Cast raw accumulator counts to the stored int/float shape for one
    team-game row. `games` is 1 per row -- summing it across a week range is
    how the eventual /game rate denominators aggregate correctly."""
    out: dict[str, Any] = {"opponent": counts.get("opponent"), "games": 1}
    for field in _INT_FIELDS:
        out[field] = int(counts.get(field, 0))
    for field in _DEF_INT_FIELDS:
        out[field] = int(counts.get(field, 0))
    out["turnoverEpaSum"] = float(counts.get("turnoverEpaSum", 0.0))
    out["opponentTurnoverEpaSum"] = float(counts.get("opponentTurnoverEpaSum", 0.0))
    return out
