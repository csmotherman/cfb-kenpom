"""Forensic audit: does CFBD play-by-play reconcile with CFBD's official box score?

This is a standalone, read-only audit. It does not write to `data/canonical`,
does not touch production metrics (APR, ratings, EPA, predictions), and does
not modify any pipeline module. It answers one question quantitatively:

    If we reconstruct a team's game statistics purely from CFBD /plays, how
    often does that reconstruction match CFBD's own official /games/teams
    box score, and exactly where/why does it differ?

Three populations are compared per team-game, for every completed game that
has both an official box score and play-by-play on disk:

  LAYER "raw"       -- CFBD /plays classified only by CFBD's own `playType`
                        label (via the same static taxonomy table the
                        production pipeline uses -- that table is a 1:1
                        reading of CFBD's own field, not an invented rule).
                        Uses raw `yardsGained`. No no-play exclusion. No
                        drive-ownership correction. This is what a reader
                        gets by taking /plays completely at face value.
  LAYER "canonical" -- the actual PRIME pipeline: `normalize_play` +
                        `promote_partition_yardage` (yards-v1 text-evidence
                        correction) + `correct_partition_drive_ownership`
                        (drive-ownership-v1). Uses `analyticsYardsGained`.
                        No-play context plays are excluded from counts.
  SOURCE "official" -- CFBD /games/teams, parsed with the exact same
                        `_normalize_box_team` parser already used in
                        `scripts/export_team_game_advanced.py` (BOX_SCORE_VERSION
                        = "cfbd-games-teams-v1"). This script does not
                        reimplement box-score parsing.

Two rush/pass attribution CONVENTIONS are tested empirically rather than
assumed (see module docstring section "CONVENTIONS"): sack-yardage may belong
to the passing bucket or the rushing bucket in NCAA official box scores. This
script measures both and reports which one CFBD's /games/teams actually
follows, per statistic, from the data itself.

Outputs land under `data/audits/pbp_box_score_consistency/` -- see
`scripts/audit_pbp_box_score_consistency_README.md` for the artifact list
and how to interpret it (that file is written by this script's --report step
if invoked, but the canonical documentation lives in the audit's own
README.md written alongside the other artifacts).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from cfb_analytics.raw.audit import discover_partitions  # noqa: E402
from cfb_analytics.raw.storage import partition_dir  # noqa: E402
from cfb_analytics.raw.sequence import _candidate_sort_key  # noqa: E402
from cfb_analytics.canonical.plays import normalize_play  # noqa: E402
from cfb_analytics.canonical.corrections import promote_partition_yardage  # noqa: E402
from cfb_analytics.canonical.drive_ownership import correct_partition_drive_ownership  # noqa: E402
from cfb_analytics.canonical.drive_grouping import derive_partition_drives  # noqa: E402
from cfb_analytics.analytics.turnover_forensics import (  # noqa: E402
    build_play_index,
    classify_drive_turnover_from_plays,
    _drive_plays,
    _signal_counts,
    INT_DIRECT,
    INT_RETURN,
    FUMBLE_LOST,
    FUMBLE_OWN,
)
from cfb_analytics.analytics.turnovers import classify_possession_turnover  # noqa: E402


# --------------------------------------------------------------------------
# Candidate fix (NOT applied to production): production turnovers-v1
# (cfb_analytics/analytics/turnover_forensics.py::classify_drive_turnover_from_plays)
# computes its `no_play` signal across EVERY play in the drive, so an
# unrelated no-play penalty earlier in the same possession (e.g. a 1st-down
# false start) wrongly nullifies a completely clean turnover later in the
# same drive (MODIFIED_CONTEXT_REVIEW). Measured on 2026 weeks 1-2: 112 of
# 114 such exclusions (98%) have the no-play penalty on a DIFFERENT play
# than the turnover signal -- i.e. false positives. This scopes the no-play
# check to the turnover-signal play itself, matching what the box score
# actually counts. See README "KNOWN BUG" section before ever porting this
# into production -- it is validated here only against the sack/turnover
# reconciliation, not against the rest of the turnovers-v1 test suite.
# --------------------------------------------------------------------------

def classify_drive_turnover_scoped_from_plays(ps: list[dict]) -> str:
    s = _signal_counts(ps)
    has_int = s["int_direct"] or s["int_return"]
    has_flost = s["fumble_lost"]
    turnover_signal_plays = [p for p in ps if p.get("eventSubtype") in (INT_DIRECT | INT_RETURN | FUMBLE_LOST)]
    no_play_on_signal = any(p.get("hasNoPlayContext") for p in turnover_signal_plays)
    if no_play_on_signal and (has_int or has_flost):
        return "MODIFIED_CONTEXT_REVIEW"
    if has_int and has_flost:
        return "MULTIPLE_TURNOVER_SIGNALS"
    if s["int_direct"]:
        return "INTERCEPTION_DIRECT"
    if s["int_return"]:
        return "INTERCEPTION_RETURN_ONLY"
    if has_flost:
        return "FUMBLE_LOST"
    if s["fumble_own"]:
        return "FUMBLE_RECOVERED_OWN"
    if s["fumble_base"]:
        return "FUMBLE_WITHOUT_RECOVERY_SIGNAL"
    if s["turn_records"]:
        return "OTHER_TURNOVER_RECORD"
    return "NO_EXPLICIT_TURNOVER"


def classify_possession_turnover_scoped(drive: dict, play_index: dict) -> dict:
    outcome = classify_drive_turnover_scoped_from_plays(_drive_plays(drive, play_index))
    if outcome in {"INTERCEPTION_DIRECT", "INTERCEPTION_RETURN_ONLY"}:
        return {"turnoverOutcome": "INTERCEPTION", "giveaway": 1, "interceptionThrown": 1, "fumbleLost": 0, "turnoverResolved": True}
    if outcome == "FUMBLE_LOST":
        return {"turnoverOutcome": "FUMBLE_LOST", "giveaway": 1, "interceptionThrown": 0, "fumbleLost": 1, "turnoverResolved": True}
    if outcome in {"FUMBLE_RECOVERED_OWN", "NO_EXPLICIT_TURNOVER"}:
        return {"turnoverOutcome": "NO_GIVEAWAY", "giveaway": 0, "interceptionThrown": 0, "fumbleLost": 0, "turnoverResolved": True}
    return {"turnoverOutcome": "UNRESOLVED_OR_EXCLUDED", "giveaway": 0, "interceptionThrown": 0, "fumbleLost": 0, "turnoverResolved": False}

import export_team_game_advanced as box_module  # noqa: E402

AUDIT_VERSION = "pbp-box-score-consistency-v1"
OUT_ROOT = REPO / "data/audits/pbp_box_score_consistency"

# --- CFBD playType -> stat-bucket groupings (direct reading of the existing
# static taxonomy in canonical/play_types.py; not a new classification). ---
RUSH_SUBTYPES = {"RUSH", "RUSH_TD"}
PASS_COMPLETE_SUBTYPES = {"PASS_COMPLETION", "PASS_TD"}
PASS_INCOMPLETE_SUBTYPES = {"PASS_INCOMPLETE"}
SACK_SUBTYPE = "SACK"
INTERCEPTION_THROWN_SUBTYPE = "INTERCEPTION"
PASS_UNSPECIFIED_SUBTYPE = "PASS_UNSPECIFIED"
TWO_POINT_SUBTYPES = {"TWO_POINT_PASS", "TWO_POINT_RUSH"}

# CFBD collapses the underlying snap's identity into a FUMBLE_*/SAFETY
# playType whenever a fumble or safety occurs -- "Rush", "Sack", and "Pass
# Reception" all disappear from the structured playType field, surviving
# only in playText (see README "CONVENTIONS" for the discovered example:
# game 401856766, TCU). These rules recover the underlying snap type from
# playText so it isn't silently dropped from rush/pass/sack counting.
TEXT_INFERENCE_SUBTYPES = {"FUMBLE", "FUMBLE_RECOVERY_OWN", "FUMBLE_RECOVERY_OPPONENT", "FUMBLE_RETURN_TD", "SAFETY"}
_SACKED_RE = re.compile(r"\bsacked\b", re.I)
_RUSH_RE = re.compile(r"\brush(ed)?\b", re.I)
_PASS_COMPLETE_RE = re.compile(r"\bpass complete\b", re.I)
_PASS_INCOMPLETE_RE = re.compile(r"\bpass incomplete\b", re.I)


def _text_inferred_subtype(p: dict) -> str | None:
    if p.get("eventSubtype") not in TEXT_INFERENCE_SUBTYPES:
        return None
    text = str(p.get("playText") or "")
    if _SACKED_RE.search(text):
        return "SACK"
    if _PASS_COMPLETE_RE.search(text):
        return "PASS_COMPLETION"
    if _PASS_INCOMPLETE_RE.search(text):
        return "PASS_INCOMPLETE"
    if _RUSH_RE.search(text):
        return "RUSH"
    return None


def _effective_subtype(p: dict) -> str | None:
    return _text_inferred_subtype(p) or p.get("eventSubtype")

CORE_STATS = (
    "points",
    "total_plays",
    "total_yards",
    "pass_attempts",
    "completions",
    "net_pass_yards",
    "rush_attempts",
    "rush_yards",
    "turnovers",
    "interceptions",
    "fumbles_lost",
)
SECONDARY_STATS = (
    "third_down_attempts",
    "third_down_conversions",
    "fourth_down_attempts",
    "fourth_down_conversions",
)

RECONSTRUCTABILITY = {
    "points": ("EXACTLY_RECONSTRUCTABLE", "Final offense/defenseScore on the chronologically last play is a direct passthrough of CFBD's own running score; not derived from our taxonomy at all."),
    "total_plays": ("EXACTLY_RECONSTRUCTABLE", "rush_plays + pass_attempts(excl. sack or incl. sack, whichever bucket) + sacks always sums to the same offensive-snap count regardless of which convention is used for the rush/pass split -- convention-independent."),
    "total_yards": ("EXACTLY_RECONSTRUCTABLE", "Sack yardage moves between the rushing and passing bucket depending on convention, but total offensive yardage does not change -- convention-independent."),
    "rush_attempts": ("RECONSTRUCTABLE_WITH_RULES", "Exact match requires picking the correct sack-attribution convention (see CONVENTION_RESULT in summary.json); ambiguous PASS_UNSPECIFIED and two-point plays are excluded by rule."),
    "rush_yards": ("RECONSTRUCTABLE_WITH_RULES", "Same convention dependency as rush_attempts."),
    "pass_attempts": ("RECONSTRUCTABLE_WITH_RULES", "Same convention dependency as rush_attempts; interceptions thrown count as attempts, two-point passes are excluded."),
    "completions": ("EXACTLY_RECONSTRUCTABLE", "Completions are convention-independent: PASS_COMPLETION/PASS_TD records never move between rush/pass buckets."),
    "net_pass_yards": ("RECONSTRUCTABLE_WITH_RULES", "Same convention dependency as pass_attempts."),
    "turnovers": ("RECONSTRUCTABLE_WITH_RULES", "Requires the validated drive-level turnover classifier (turnovers-v1) rather than naive per-play interception/fumble counting, because CFBD sometimes records a turnover-and-return as a separate non-possession drive group."),
    "interceptions": ("RECONSTRUCTABLE_WITH_RULES", "Same drive-level dependency as turnovers."),
    "fumbles_lost": ("RECONSTRUCTABLE_WITH_RULES", "Same drive-level dependency as turnovers; also the hardest-to-attribute NCAA stat historically."),
    "third_down_attempts": ("APPROXIMATELY_RECONSTRUCTABLE", "Down==3 offensive scrimmage snap count; excludes no-play penalty snaps by rule but cannot distinguish a defensive-penalty automatic-first-down non-snap from a real attempt in all cases."),
    "third_down_conversions": ("APPROXIMATELY_RECONSTRUCTABLE", "Structural yards>=distance-or-touchdown heuristic; prior repo research (first_down_generation_final_residual_forensics.py) already found unexplained reset/generation residuals in this exact signal, so this is a known-imperfect proxy, not a locked definition."),
    "fourth_down_attempts": ("APPROXIMATELY_RECONSTRUCTABLE", "Same as third_down_attempts."),
    "fourth_down_conversions": ("APPROXIMATELY_RECONSTRUCTABLE", "Same as third_down_conversions."),
}

MAJOR_MISMATCH_THRESHOLDS = {
    "points": 1, "total_plays": 2, "total_yards": 10, "pass_attempts": 2,
    "completions": 2, "net_pass_yards": 10, "rush_attempts": 2, "rush_yards": 10,
    "turnovers": 1, "interceptions": 1, "fumbles_lost": 1,
    "third_down_attempts": 2, "third_down_conversions": 2,
    "fourth_down_attempts": 1, "fourth_down_conversions": 1,
}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _n(v: Any) -> float:
    return float(v) if _num(v) else 0.0


# --------------------------------------------------------------------------
# Loading + layer construction
# --------------------------------------------------------------------------

def load_partition(raw_root: Path, season: int, season_type: str, week: int) -> dict[str, Any]:
    pdir = partition_dir(raw_root, season, season_type, week)
    games = json.loads((pdir / "games.json").read_text())
    raw_plays = json.loads((pdir / "plays.json").read_text())
    box_path = pdir / "game_team_stats.json"
    box_payload = json.loads(box_path.read_text()) if box_path.exists() else []

    layer_raw = [normalize_play(p) for p in raw_plays]
    layer_canon = copy.deepcopy(layer_raw)
    layer_canon = promote_partition_yardage(layer_canon)
    layer_canon, _ = correct_partition_drive_ownership(layer_canon, season, season_type, week)

    drives_raw, _ = derive_partition_drives(layer_raw, season, season_type, week)
    drives_canon, _ = derive_partition_drives(layer_canon, season, season_type, week)

    box_by_game_team: dict[tuple[str, str], dict] = {}
    for g in box_payload:
        gid = str(g.get("id"))
        for team_row in g.get("teams") or []:
            if not isinstance(team_row, dict) or not team_row.get("team"):
                continue
            box_by_game_team[(gid, team_row["team"])] = box_module._normalize_box_team(team_row)

    return {
        "games": games,
        "layer_raw": layer_raw,
        "layer_canon": layer_canon,
        "drives_raw": drives_raw,
        "drives_canon": drives_canon,
        "box": box_by_game_team,
        "season_type": season_type,
        "week": week,
    }


def load_season_corpus(raw_root: Path, season: int, weeks: set[int] | None = None) -> dict[str, Any]:
    games: dict[str, dict] = {}
    plays_raw: dict[str, list] = defaultdict(list)
    plays_canon: dict[str, list] = defaultdict(list)
    drives_raw: dict[str, list] = defaultdict(list)
    drives_canon: dict[str, list] = defaultdict(list)
    box: dict[tuple[str, str], dict] = {}

    for season_type, week in discover_partitions(raw_root, season):
        if weeks is not None and week not in weeks:
            continue
        part = load_partition(raw_root, season, season_type, week)
        for g in part["games"]:
            games[str(g["id"])] = g
        for p in part["layer_raw"]:
            plays_raw[str(p.get("gameId"))].append(p)
        for p in part["layer_canon"]:
            plays_canon[str(p.get("gameId"))].append(p)
        for d in part["drives_raw"]:
            drives_raw[str(d.get("gameId"))].append(d)
        for d in part["drives_canon"]:
            drives_canon[str(d.get("gameId"))].append(d)
        box.update(part["box"])

    return {
        "games": games, "plays_raw": plays_raw, "plays_canon": plays_canon,
        "drives_raw": drives_raw, "drives_canon": drives_canon, "box": box,
    }


# --------------------------------------------------------------------------
# Reconstruction
# --------------------------------------------------------------------------

def _final_score(plays_for_game: list[dict]) -> dict[str, float]:
    ordered = sorted(plays_for_game, key=_candidate_sort_key)
    score: dict[str, float] = {}
    for p in ordered:
        if p.get("offense") is not None and _num(p.get("offenseScore")):
            score[p["offense"]] = p["offenseScore"]
        if p.get("defense") is not None and _num(p.get("defenseScore")):
            score[p["defense"]] = p["defenseScore"]
    return score


def _is_clean(p: dict) -> bool:
    return not bool(p.get("hasNoPlayContext"))


def reconstruct_rush_pass(plays_for_game: list[dict], team: str, yards_field: str, text_inference: bool = True, exclude_ids: set[str] | None = None) -> dict[str, Any]:
    off = [p for p in plays_for_game if p.get("offense") == team and _is_clean(p) and (exclude_ids is None or str(p.get("id")) not in exclude_ids)]
    sub = _effective_subtype if text_inference else (lambda p: p.get("eventSubtype"))  # noqa: E731
    yards = lambda p: _n(p.get(yards_field))  # noqa: E731

    rush = [p for p in off if sub(p) in RUSH_SUBTYPES]
    sacks = [p for p in off if sub(p) == SACK_SUBTYPE]
    complete = [p for p in off if sub(p) in PASS_COMPLETE_SUBTYPES]
    incomplete = [p for p in off if sub(p) in PASS_INCOMPLETE_SUBTYPES]
    ints_thrown = [p for p in off if sub(p) == INTERCEPTION_THROWN_SUBTYPE]
    pass_unspecified = [p for p in off if sub(p) == PASS_UNSPECIFIED_SUBTYPE]
    two_point = [p for p in off if sub(p) in TWO_POINT_SUBTYPES]

    pass_no_sack = complete + incomplete + ints_thrown
    rush_yards_no_sack = sum(yards(p) for p in rush)
    sack_yards = sum(yards(p) for p in sacks)
    pass_yards_no_sack = sum(yards(p) for p in pass_no_sack)

    return {
        "rush_attempts_sackAsRush": len(rush) + len(sacks),
        "rush_yards_sackAsRush": rush_yards_no_sack + sack_yards,
        "rush_attempts_sackAsPass": len(rush),
        "rush_yards_sackAsPass": rush_yards_no_sack,
        "pass_attempts_sackAsRush": len(pass_no_sack),
        "pass_attempts_sackAsPass": len(pass_no_sack) + len(sacks),
        "net_pass_yards_sackAsRush": pass_yards_no_sack,
        "net_pass_yards_sackAsPass": pass_yards_no_sack + sack_yards,
        "completions": len(complete),
        "total_plays": len(rush) + len(pass_no_sack) + len(sacks),
        "total_yards": rush_yards_no_sack + sack_yards + pass_yards_no_sack,
        "sacks": len(sacks),
        "pass_unspecified_count": len(pass_unspecified),
        "two_point_count": len(two_point),
    }


def reconstruct_turnovers(team: str, drives: list[dict], plays_for_game: list[dict], scoped_fix: bool = False) -> dict[str, Any]:
    index = build_play_index(plays_for_game)
    off_drives = [d for d in drives if d.get("offense") == team and d.get("isPossessionDrive") is True and d.get("driveValidationStatus") == "PASS"]
    classify = classify_possession_turnover_scoped if scoped_fix else classify_possession_turnover
    interceptions = fumbles = 0
    unresolved = 0
    for d in off_drives:
        r = classify(d, index)
        interceptions += r["interceptionThrown"]
        fumbles += r["fumbleLost"]
        if not r["turnoverResolved"]:
            unresolved += 1
    return {
        "interceptions": interceptions,
        "fumbles_lost": fumbles,
        "turnovers": interceptions + fumbles,
        "unresolved_possessions": unresolved,
    }


def reconstruct_down_stats(team: str, plays_for_game: list[dict], yards_field: str) -> dict[str, Any]:
    off = [p for p in plays_for_game if p.get("offense") == team and _is_clean(p) and p.get("isOffensivePlay") is True and p.get("isScrimmagePlay") is True]
    out = {"third_down_attempts": 0, "third_down_conversions": 0, "fourth_down_attempts": 0, "fourth_down_conversions": 0}
    for p in off:
        down = p.get("down")
        distance = p.get("distance")
        yards = p.get(yards_field)
        if down not in (3, 4) or not _num(distance):
            continue
        key_attempt = "third_down_attempts" if down == 3 else "fourth_down_attempts"
        key_conv = "third_down_conversions" if down == 3 else "fourth_down_conversions"
        out[key_attempt] += 1
        text = str(p.get("playText") or "").upper()
        converted = ("TOUCHDOWN" in text) or (_num(yards) and yards >= distance)
        if converted:
            out[key_conv] += 1
    return out


def reconstruct_team_game(team: str, plays_for_game: list[dict], drives: list[dict], yards_field: str, final_scores: dict[str, float], text_inference: bool = True) -> dict[str, Any]:
    rp = reconstruct_rush_pass(plays_for_game, team, yards_field, text_inference=text_inference)
    to = reconstruct_turnovers(team, drives, plays_for_game)
    dn = reconstruct_down_stats(team, plays_for_game, yards_field)
    return {
        "points": final_scores.get(team),
        "total_plays": rp["total_plays"],
        "total_yards": rp["total_yards"],
        "completions": rp["completions"],
        **{f"pass_attempts_{c}": rp[f"pass_attempts_{c}"] for c in ("sackAsRush", "sackAsPass")},
        **{f"net_pass_yards_{c}": rp[f"net_pass_yards_{c}"] for c in ("sackAsRush", "sackAsPass")},
        **{f"rush_attempts_{c}": rp[f"rush_attempts_{c}"] for c in ("sackAsRush", "sackAsPass")},
        **{f"rush_yards_{c}": rp[f"rush_yards_{c}"] for c in ("sackAsRush", "sackAsPass")},
        "sacks": rp["sacks"],
        "pass_unspecified_count": rp["pass_unspecified_count"],
        "two_point_count": rp["two_point_count"],
        "turnovers": to["turnovers"],
        "interceptions": to["interceptions"],
        "fumbles_lost": to["fumbles_lost"],
        "turnover_unresolved_possessions": to["unresolved_possessions"],
        **dn,
    }


# --------------------------------------------------------------------------
# Convention selection (empirical, per Phase 3 -- do not assume)
# --------------------------------------------------------------------------

def pick_convention(rows: list[dict]) -> dict[str, Any]:
    """For each convention-dependent stat, measure exact-match rate under both
    sack conventions across every team-game and pick whichever the data
    actually supports. Returns the winning convention name and both scores."""
    results = {}
    for stat in ("rush_attempts", "rush_yards", "pass_attempts", "net_pass_yards"):
        scores = {}
        for conv in ("sackAsRush", "sackAsPass"):
            matches = 0
            total = 0
            for row in rows:
                official = row.get(f"box_{stat}")
                recon = row.get(f"canon_{stat}_{conv}")
                if official is None or recon is None:
                    continue
                total += 1
                matches += int(official == recon)
            scores[conv] = {"matches": matches, "total": total, "rate": matches / total if total else None}
        winner = max(scores, key=lambda c: (scores[c]["rate"] or -1))
        results[stat] = {"winner": winner, "scores": scores}
    return results


# --------------------------------------------------------------------------
# Comparison / diffing
# --------------------------------------------------------------------------

def build_team_game_rows(season: int, corpus: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for gid, game in corpus["games"].items():
        if game.get("completed") is not True:
            continue
        plays_raw = corpus["plays_raw"].get(gid, [])
        plays_canon = corpus["plays_canon"].get(gid, [])
        if not plays_raw:
            continue  # no PBP for this game; not part of the audit population
        drives_raw = corpus["drives_raw"].get(gid, [])
        drives_canon = corpus["drives_canon"].get(gid, [])
        scores_raw = _final_score(plays_raw)
        dup_ids = duplicate_play_ids(plays_canon)

        for side, opp_side in (("home", "away"), ("away", "home")):
            team = game.get(f"{side}Team")
            opponent = game.get(f"{opp_side}Team")
            box = corpus["box"].get((gid, team))
            raw_recon = reconstruct_team_game(team, plays_raw, drives_raw, "sourceYardsGained", scores_raw, text_inference=False)
            canon_recon = reconstruct_team_game(team, plays_canon, drives_canon, "analyticsYardsGained", scores_raw, text_inference=True)
            fixed_turnovers = reconstruct_turnovers(team, drives_canon, plays_canon, scoped_fix=True)
            dedup_rp = reconstruct_rush_pass(plays_canon, team, "analyticsYardsGained", text_inference=True, exclude_ids=dup_ids)

            row = {
                "game_id": gid,
                "season": season,
                "week": game.get("week"),
                "season_type": game.get("seasonType"),
                "team": team,
                "opponent": opponent,
                "home_away": side,
                "classification": game.get(f"{side}Classification"),
                "opponent_classification": game.get(f"{opp_side}Classification"),
                "box_score_available": box is not None,
                "official_final_score": game.get(f"{side}Points"),
            }
            for k, v in raw_recon.items():
                row[f"raw_{k}"] = v
            for k, v in canon_recon.items():
                row[f"canon_{k}"] = v
            row["canonfix_interceptions"] = fixed_turnovers["interceptions"]
            row["canonfix_fumbles_lost"] = fixed_turnovers["fumbles_lost"]
            row["canonfix_turnovers"] = fixed_turnovers["turnovers"]
            for stat in ("rush_attempts", "rush_yards", "pass_attempts", "net_pass_yards"):
                for conv in ("sackAsRush", "sackAsPass"):
                    row[f"canondedup_{stat}_{conv}"] = dedup_rp[f"{stat}_{conv}"]
            row["canondedup_total_plays"] = dedup_rp["total_plays"]
            row["canondedup_total_yards"] = dedup_rp["total_yards"]
            if box:
                row["box_points"] = box.get("points")
                row["box_total_plays"] = box.get("total_plays")
                row["box_total_yards"] = box.get("total_yards")
                row["box_completions"] = box.get("completions")
                row["box_pass_attempts"] = box.get("pass_attempts")
                row["box_net_pass_yards"] = box.get("net_pass_yards")
                row["box_rush_attempts"] = box.get("rush_attempts")
                row["box_rush_yards"] = box.get("rush_yards")
                row["box_turnovers"] = box.get("turnovers")
                row["box_interceptions"] = box.get("interceptions")
                row["box_fumbles_lost"] = box.get("fumbles_lost")
                row["box_third_down_attempts"] = box.get("third_down_attempts")
                row["box_third_down_conversions"] = box.get("third_down_conversions")
                row["box_fourth_down_attempts"] = box.get("fourth_down_attempts")
                row["box_fourth_down_conversions"] = box.get("fourth_down_conversions")
            rows.append(row)
    return rows


def finalize_convention(rows: list[dict[str, Any]], convention: dict[str, Any]) -> None:
    """Attach the winning-convention canon_/raw_ values under bare stat names
    (canon_rush_attempts, raw_rush_attempts, ...) so downstream comparison
    code doesn't need to know about conventions."""
    winners = {stat: convention[stat]["winner"] for stat in convention}
    for row in rows:
        for stat, winner in winners.items():
            row[f"canon_{stat}"] = row.get(f"canon_{stat}_{winner}")
            row[f"raw_{stat}"] = row.get(f"raw_{stat}_{winner}")
            row[f"canondedup_{stat}"] = row.get(f"canondedup_{stat}_{winner}")


# --------------------------------------------------------------------------
# Root-cause tagging
# --------------------------------------------------------------------------

_KNEEL_RE = re.compile(r"\bkneel(s|ed|ing)?\b", re.I)
_SPIKE_RE = re.compile(r"\bspike(s|d)?\b", re.I)


# --------------------------------------------------------------------------
# Duplicate-play detection (CFBD source data quality -- see README "KNOWN BUG"
# section: some games contain literal back-to-back duplicate play records --
# same driveId, same wallclock, same offense/down/distance/playText, but a
# DIFFERENT play `id` -- so the existing raw-integrity check in
# raw/audit.py (`unique_play_ids`), which only verifies `id` uniqueness,
# cannot catch this. Neither ingestion nor canonicalization deduplicates it
# today. Measured: 2026 weeks 1-2, 46/186 games (24.7%) affected, 141 excess
# duplicate rows / 32,601 total (0.43%). 2025 sample weeks (1,2,7,8,14,15),
# 247/335 games (73.7%) affected, 1,709 excess rows / 59,990 total (2.85%).
# --------------------------------------------------------------------------

def duplicate_play_ids(plays_for_game: list[dict]) -> set[str]:
    seen: dict[tuple, str] = {}
    excess: set[str] = set()
    for p in sorted(plays_for_game, key=_candidate_sort_key):
        key = (p.get("driveId"), p.get("offense"), p.get("defense"), p.get("down"), p.get("distance"), p.get("playText"), p.get("wallclock"))
        if key in seen:
            excess.add(str(p.get("id")))
        else:
            seen[key] = p.get("id")
    return excess


def _tag_play(p: dict) -> set[str]:
    tags = set()
    text = str(p.get("playText") or "")
    sub = p.get("eventSubtype")
    if sub == "SACK":
        tags.add("sack")
    if sub in TWO_POINT_SUBTYPES:
        tags.add("two_point_attempt")
    if p.get("hasNoPlayContext"):
        tags.add("no_play_penalty")
    if p.get("hasPenaltyContext"):
        tags.add("accepted_or_other_penalty")
    if p.get("hasReviewContext"):
        tags.add("replay_reversal")
    if p.get("hasFumbleContext") or sub in {"FUMBLE", "FUMBLE_RECOVERY_OWN", "FUMBLE_RECOVERY_OPPONENT", "FUMBLE_RETURN_TD"}:
        tags.add("fumble")
    if sub == "INTERCEPTION" or p.get("hasInterceptionContext"):
        tags.add("interception")
    if _KNEEL_RE.search(text):
        tags.add("kneel")
    if _SPIKE_RE.search(text):
        tags.add("spike")
    if sub == "PASS_UNSPECIFIED":
        tags.add("pass_unspecified")
    if sub == "SAFETY":
        tags.add("safety")
    if _text_inferred_subtype(p) is not None:
        tags.add("fumble_or_safety_swallows_scrimmage_type")
    if p.get("driveIdWasCorrected"):
        tags.add("drive_ownership_correction")
    if p.get("analyticsYardsWasCorrected"):
        tags.add("text_yardage_correction")
    return tags


def tag_team_game_plays(plays_for_game: list[dict], team: str) -> Counter:
    tags = Counter()
    for p in plays_for_game:
        if p.get("offense") != team and p.get("defense") != team:
            continue
        for t in _tag_play(p):
            tags[t] += 1
    return tags


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def _pct(n: int, d: int) -> float | None:
    return n / d if d else None


def compare_column(rows: list[dict], stat: str, recon_prefix: str) -> dict[str, Any]:
    diffs = []
    abs_diffs = []
    exact = 0
    total = 0
    for row in rows:
        official = row.get(f"box_{stat}")
        recon = row.get(f"{recon_prefix}_{stat}")
        if official is None or recon is None:
            continue
        total += 1
        d = recon - official
        diffs.append(d)
        abs_diffs.append(abs(d))
        if d == 0:
            exact += 1
    if not total:
        return {"comparisons": 0}
    sorted_abs = sorted(abs_diffs)
    p95_idx = min(len(sorted_abs) - 1, int(round(0.95 * (len(sorted_abs) - 1))))
    return {
        "comparisons": total,
        "exact_matches": exact,
        "mismatches": total - exact,
        "exact_match_rate": exact / total,
        "mean_signed_error": statistics.fmean(diffs),
        "mean_abs_error": statistics.fmean(abs_diffs),
        "median_abs_error": statistics.median(abs_diffs),
        "p95_abs_error": sorted_abs[p95_idx],
        "max_abs_diff": max(abs_diffs),
    }


def game_level_integrity(rows: list[dict], recon_prefix: str, stats: tuple[str, ...]) -> dict[str, Any]:
    zero_mismatch = one_or_more = two_or_more = major = 0
    total = 0
    for row in rows:
        mismatch_count = 0
        has_major = False
        counted = False
        for stat in stats:
            official = row.get(f"box_{stat}")
            recon = row.get(f"{recon_prefix}_{stat}")
            if official is None or recon is None:
                continue
            counted = True
            d = abs(recon - official)
            if d != 0:
                mismatch_count += 1
            if d > MAJOR_MISMATCH_THRESHOLDS.get(stat, 1):
                has_major = True
        if not counted:
            continue
        total += 1
        if mismatch_count == 0:
            zero_mismatch += 1
        if mismatch_count >= 1:
            one_or_more += 1
        if mismatch_count >= 2:
            two_or_more += 1
        if has_major:
            major += 1
    return {
        "team_games": total,
        "all_core_stats_match_pct": _pct(zero_mismatch, total),
        "at_least_one_mismatch_pct": _pct(one_or_more, total),
        "at_least_two_mismatches_pct": _pct(two_or_more, total),
        "major_mismatch_pct": _pct(major, total),
        "major_mismatch_definition": "abs(reconstructed - official) exceeds the per-statistic MAJOR_MISMATCH_THRESHOLDS in this script (e.g. >2 plays, >10 yards, >1 turnover) -- not an arbitrary tolerance band used to hide small noise, but a threshold for what counts as a materially wrong number rather than off-by-one counting noise.",
    }


# --------------------------------------------------------------------------
# Root-cause classification of individual mismatches
# --------------------------------------------------------------------------

DUPLICATE_AFFECTED_STATS = ("rush_attempts", "rush_yards", "pass_attempts", "net_pass_yards", "total_plays", "total_yards", "completions")


def classify_mismatch_cause(row: dict, stat: str, plays_for_game: list[dict], team: str) -> str:
    if stat in DUPLICATE_AFFECTED_STATS:
        dup_ids = duplicate_play_ids(plays_for_game)
        if dup_ids:
            team_dup_plays = [p for p in plays_for_game if str(p.get("id")) in dup_ids and p.get("offense") == team]
            if team_dup_plays:
                return "duplicate_plays"
    tags = tag_team_game_plays(plays_for_game, team)
    if stat in ("rush_attempts", "rush_yards", "pass_attempts", "net_pass_yards", "total_plays", "total_yards"):
        if tags.get("fumble_or_safety_swallows_scrimmage_type"):
            return "fumble_or_safety_swallows_scrimmage_type"
        if tags.get("safety"):
            return "safety_accounting"
    if stat in ("rush_attempts", "rush_yards", "pass_attempts", "net_pass_yards", "total_plays", "total_yards") and tags.get("sack"):
        return "sack_accounting"
    if tags.get("kneel"):
        return "kneel_accounting"
    if tags.get("spike"):
        return "spike_accounting"
    if tags.get("two_point_attempt"):
        return "two_point_attempt"
    if tags.get("no_play_penalty"):
        return "no_play_penalty"
    if tags.get("accepted_or_other_penalty"):
        return "accepted_or_declined_penalty"
    if tags.get("replay_reversal"):
        return "replay_reversal"
    if stat in ("turnovers", "interceptions", "fumbles_lost"):
        if tags.get("drive_ownership_correction"):
            return "drive_ownership_correction"
        if tags.get("fumble"):
            return "fumble_attribution"
        if tags.get("interception"):
            return "interception_attribution"
        return "turnover_unresolved"
    if tags.get("pass_unspecified"):
        return "pass_unspecified_playtype"
    if tags.get("text_yardage_correction"):
        return "source_inconsistency_yardage"
    return "unknown"


def mismatch_details(rows: list[dict], corpus: dict[str, Any], recon_prefix: str, stats: tuple[str, ...]) -> list[dict]:
    plays_key = "plays_raw" if recon_prefix == "raw" else "plays_canon"
    details = []
    for row in rows:
        for stat in stats:
            official = row.get(f"box_{stat}")
            recon = row.get(f"{recon_prefix}_{stat}")
            if official is None or recon is None or official == recon:
                continue
            plays_for_game = corpus[plays_key].get(row["game_id"], [])
            cause = classify_mismatch_cause(row, stat, plays_for_game, row["team"])
            details.append({
                "game_id": row["game_id"], "season": row["season"], "week": row["week"],
                "season_type": row["season_type"], "team": row["team"], "opponent": row["opponent"],
                "home_away": row["home_away"], "layer": recon_prefix, "statistic": stat,
                "official_value": official, "reconstructed_value": recon,
                "raw_difference": recon - official, "absolute_difference": abs(recon - official),
                "root_cause": cause,
            })
    return details


# --------------------------------------------------------------------------
# Output writing
# --------------------------------------------------------------------------

def _duplicate_prevalence(corpus: dict[str, Any]) -> dict[str, Any]:
    total_games = 0
    games_with_dups = 0
    total_excess = 0
    total_plays = 0
    for gid, plays in corpus["plays_canon"].items():
        total_games += 1
        total_plays += len(plays)
        excess = duplicate_play_ids(plays)
        if excess:
            games_with_dups += 1
        total_excess += len(excess)
    return {
        "games": total_games,
        "gamesWithDuplicatePlays": games_with_dups,
        "gamesWithDuplicatePlaysPct": _pct(games_with_dups, total_games),
        "excessDuplicatePlayRows": total_excess,
        "totalPlayRows": total_plays,
        "excessDuplicatePlayRowsPct": _pct(total_excess, total_plays),
    }


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run_audit(season: int, out_dir: Path, tag: str, weeks: set[int] | None = None) -> dict[str, Any]:
    raw_root = REPO / "data/raw"
    corpus = load_season_corpus(raw_root, season, weeks=weeks)
    rows = build_team_game_rows(season, corpus)
    box_rows = [r for r in rows if r["box_score_available"]]

    convention = pick_convention(box_rows)
    finalize_convention(rows, convention)

    summary: dict[str, Any] = {
        "auditVersion": AUDIT_VERSION,
        "season": season,
        "tag": tag,
        "teamGamesTotal": len(rows),
        "teamGamesWithBoxScore": len(box_rows),
        "teamGamesWithoutBoxScore": len(rows) - len(box_rows),
        "fbsVsFbs": sum(1 for r in rows if r["classification"] == "fbs" and r["opponent_classification"] == "fbs"),
        "fbsVsFcsOrOther": sum(1 for r in rows if not (r["classification"] == "fbs" and r["opponent_classification"] == "fbs")),
        "sackConvention": convention,
        "reconstructability": {k: {"class": v[0], "reason": v[1]} for k, v in RECONSTRUCTABILITY.items()},
        "statistics": {"raw": {}, "canonical": {}},
        "gameLevelIntegrity": {"raw": {}, "canonical": {}},
    }

    all_stats = CORE_STATS + SECONDARY_STATS
    for stat in all_stats:
        summary["statistics"]["raw"][stat] = compare_column(box_rows, stat, "raw")
        summary["statistics"]["canonical"][stat] = compare_column(box_rows, stat, "canon")

    summary["candidateTurnoverFix"] = {
        "description": (
            "NOT applied to production. cfb_analytics/analytics/turnover_forensics.py's "
            "classify_drive_turnover_from_plays computes its no-play signal across every "
            "play in the drive, so an unrelated no-play penalty earlier in the same "
            "possession wrongly excludes a clean turnover later in the drive "
            "(MODIFIED_CONTEXT_REVIEW). This scopes the no-play check to the turnover-signal "
            "play itself. before/after below is measured against the same box-score population."
        ),
        "before_turnovers-v1": {
            "interceptions": compare_column(box_rows, "interceptions", "canon"),
            "fumbles_lost": compare_column(box_rows, "fumbles_lost", "canon"),
            "turnovers": compare_column(box_rows, "turnovers", "canon"),
        },
        "after_scoped_no_play_fix": {
            "interceptions": compare_column(box_rows, "interceptions", "canonfix"),
            "fumbles_lost": compare_column(box_rows, "fumbles_lost", "canonfix"),
            "turnovers": compare_column(box_rows, "turnovers", "canonfix"),
        },
    }

    dedup_stats = ("rush_attempts", "rush_yards", "pass_attempts", "net_pass_yards", "total_plays", "total_yards")
    summary["candidateDuplicatePlayFix"] = {
        "description": (
            "NOT applied to production. Some CFBD /plays games contain literal duplicate "
            "play rows (same driveId/offense/down/distance/playText/wallclock, different "
            "play id) that neither ingestion nor canonicalization removes -- the existing "
            "raw/audit.py unique_play_ids check only verifies id uniqueness, which duplicate "
            "rows with distinct ids pass trivially. before/after strips duplicate rows "
            "(keeping the first occurrence) before reconstructing rush/pass/total stats."
        ),
        "duplicatePlayPrevalence": _duplicate_prevalence(corpus),
        "before": {s: compare_column(box_rows, s, "canon") for s in dedup_stats},
        "after_dedup": {s: compare_column(box_rows, s, "canondedup") for s in dedup_stats},
    }
    summary["gameLevelIntegrity"]["raw"] = game_level_integrity(box_rows, "raw", CORE_STATS)
    summary["gameLevelIntegrity"]["canonical"] = game_level_integrity(box_rows, "canon", CORE_STATS)

    mismatches_raw = mismatch_details(box_rows, corpus, "raw", all_stats)
    mismatches_canon = mismatch_details(box_rows, corpus, "canon", all_stats)

    root_cause_counts_raw = Counter(m["root_cause"] for m in mismatches_raw)
    root_cause_counts_canon = Counter(m["root_cause"] for m in mismatches_canon)
    root_cause_games_raw = defaultdict(set)
    root_cause_games_canon = defaultdict(set)
    for m in mismatches_raw:
        root_cause_games_raw[m["root_cause"]].add((m["game_id"], m["team"]))
    for m in mismatches_canon:
        root_cause_games_canon[m["root_cause"]].add((m["game_id"], m["team"]))

    summary["rootCauseFrequency"] = {
        "raw": {k: {"mismatches": v, "team_games_affected": len(root_cause_games_raw[k])} for k, v in root_cause_counts_raw.most_common()},
        "canonical": {k: {"mismatches": v, "team_games_affected": len(root_cause_games_canon[k])} for k, v in root_cause_counts_canon.most_common()},
    }
    summary["unknownRootCausePct"] = {
        "raw": _pct(root_cause_counts_raw.get("unknown", 0), sum(root_cause_counts_raw.values())),
        "canonical": _pct(root_cause_counts_canon.get("unknown", 0), sum(root_cause_counts_canon.values())),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    diff_columns = [
        "game_id", "season", "week", "season_type", "team", "opponent", "home_away",
        "classification", "opponent_classification", "box_score_available",
    ] + [f"box_{s}" for s in all_stats] + [f"raw_{s}" for s in all_stats] + [f"canon_{s}" for s in all_stats] + [
        "canonfix_interceptions", "canonfix_fumbles_lost", "canonfix_turnovers",
    ] + [f"canondedup_{s}" for s in ("rush_attempts", "rush_yards", "pass_attempts", "net_pass_yards", "total_plays", "total_yards")]
    write_csv(out_dir / "team_game_differences.csv", rows, diff_columns)

    mismatch_columns = ["game_id", "season", "week", "season_type", "team", "opponent", "home_away", "layer", "statistic", "official_value", "reconstructed_value", "raw_difference", "absolute_difference", "root_cause"]
    write_csv(out_dir / "mismatch_details.csv", mismatches_raw + mismatches_canon, mismatch_columns)

    # Evidence: actual plays behind the largest / unknown-cause mismatches only.
    evidence = []
    interesting = [m for m in mismatches_canon if m["root_cause"] == "unknown" or m["absolute_difference"] >= 4]
    interesting.sort(key=lambda m: -m["absolute_difference"])
    seen = set()
    for m in interesting[:60]:
        key = (m["game_id"], m["team"])
        if key in seen:
            continue
        seen.add(key)
        plays_for_game = corpus["plays_canon"].get(m["game_id"], [])
        team_plays = [p for p in plays_for_game if p.get("offense") == m["team"] or p.get("defense") == m["team"]]
        ordered = sorted(team_plays, key=_candidate_sort_key)
        evidence.append({
            "mismatch": m,
            "plays": [
                {k: p.get(k) for k in (
                    "id", "driveId", "playNumber", "offense", "defense", "period", "down", "distance",
                    "yardsGained", "analyticsYardsGained", "sourcePlayType", "eventCategory", "eventSubtype",
                    "hasNoPlayContext", "hasPenaltyContext", "isTurnover", "playText",
                )}
                for p in ordered
            ],
        })
    (out_dir / "mismatch_plays.json").write_text(json.dumps(evidence, indent=2)[:20_000_000])

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--sanity-season", type=int, default=2025)
    parser.add_argument("--sanity-weeks", type=int, nargs="*", default=[1, 2, 7, 8, 14, 15])
    parser.add_argument("--skip-sanity", action="store_true")
    parser.add_argument("--out-dir", default=str(OUT_ROOT))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    print(f"Running primary audit: season {args.season} (every completed game currently on disk) ...")
    primary = run_audit(args.season, out_dir / str(args.season), tag="primary")
    print(json.dumps({k: primary[k] for k in ("teamGamesTotal", "teamGamesWithBoxScore", "fbsVsFbs", "sackConvention")}, indent=2))

    if not args.skip_sanity:
        weeks = set(args.sanity_weeks)
        print(f"\nRunning sanity sample: season {args.sanity_season}, weeks {sorted(weeks)} ...")
        sanity = run_audit(args.sanity_season, out_dir / f"{args.sanity_season}_sanity", tag="sanity", weeks=weeks)
        print(json.dumps({k: sanity[k] for k in ("teamGamesTotal", "teamGamesWithBoxScore", "fbsVsFbs")}, indent=2))


if __name__ == "__main__":
    main()
