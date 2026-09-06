"""Full offense/defense analytics-page data: the detailed breakdown behind the
12-metric radar. Same season, same FBS-only national percentile methodology,
same reused/fresh split as offensive_profile.py -- just a much larger metric
set (~31 per side, grouped), since a full page has room the radar doesn't.

Every metric is either:
  - "fresh": pulled from `compute_national_unit_metrics` (this repo's own
    canonical play classifiers, see offensive_profile.py's module docstring
    for the exact PPA/line-yards/stuff-rate/opportunity-rate/late-down
    definitions -- unchanged here, just also computed for the defense side).
  - "ts": read verbatim from the locked `team_seasons.json` aggregate --
    never recomputed. Most of the "OL/DL stats" and situational splits the
    site asked for already existed there under both a base field and an
    "...Allowed" field (or, for sacks/havoc/turnovers, a same-shape mirror
    field with a different name -- e.g. `sackRate` is the offense's own
    sacks-taken rate, `defensiveSackRate` is the defense's own sacks-created
    rate; both are reused as-is).
  - "ts_per_game": a `team_seasons.json` raw counting stat divided by that
    team's `games`, for stats with no rate field already computed
    (tackles-for-loss, interceptions, giveaways/takeaways).

2020 handling: same root problem as offensive_profile.py (no locked
team_seasons.json was ever built for 2020) but a much larger surface -- every
"ts" field this module needs, not just the radar's four. `_season_2020_ts_fallback`
computes all of them directly from that season's normalized plays, reusing
this repo's own classify_success/classify_explosive/classify_down_situation/
classify_standard_dropback/classify_tfl, in one pass, crediting both the
offense and defense side of every play. Two fields it cannot produce
(red zone rates, points/drive) need drive-level validation this repo has
never built for 2020's drives -- documented at the point they're set to None
below, not silently guessed. `games` (needed for the "ts_per_game" stats)
is computed the same way, from that season's own play/game-id counts.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cfb_analytics.aggregations.rankings import Metric, add_rankings
from cfb_analytics.analytics.down_situation_forensics import classify_down_situation
from cfb_analytics.analytics.dropback_v1_candidate import VALID_CLASSES as DROPBACK_VALID_CLASSES
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback
from cfb_analytics.analytics.explosiveness import classify_explosive
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.tfl import classify_tfl, high_confidence_kneel_ids

from .offensive_profile import (
    PASS_SUBTYPES,
    RUSH_SUBTYPES,
    SEASONS_2020_ONLY_RAW,
    _eligible_offense_play,
    _fbs_teams,
    _num,
    _season_plays,
    compute_national_unit_metrics,
)

UNIT_DETAIL_VERSION = "unit-detail-v1"


@dataclass(frozen=True)
class UnitMetricSpec:
    key: str
    label: str
    unit: str
    group: str
    source: str  # "fresh" | "ts" | "ts_per_game"
    offense_field: str
    defense_field: str
    offense_higher_is_better: bool
    defense_higher_is_better: bool


SPECS: tuple[UnitMetricSpec, ...] = (
    # ---- Efficiency ----
    UnitMetricSpec("success_rate", "Success Rate", "rate", "Efficiency", "ts", "successRate", "successRateAllowed", True, False),
    UnitMetricSpec("rush_success_rate", "Rush Success Rate", "rate", "Efficiency", "ts", "rushSuccessRate", "rushSuccessRateAllowed", True, False),
    UnitMetricSpec("pass_success_rate", "Pass Success Rate", "rate", "Efficiency", "ts", "passSuccessRate", "passSuccessRateAllowed", True, False),
    UnitMetricSpec("standard_down_success_rate", "Standard Down Success Rate", "rate", "Efficiency", "ts", "standardDownSuccessRate", "standardDownSuccessRateAllowed", True, False),
    UnitMetricSpec("passing_down_success_rate", "Passing Down Success Rate", "rate", "Efficiency", "ts", "passingDownSuccessRate", "passingDownSuccessRateAllowed", True, False),
    UnitMetricSpec("late_down_success_rate", "Late Down Success Rate (3rd/4th)", "rate", "Efficiency", "fresh", "late_down_success_rate", "late_down_success_rate", True, False),
    UnitMetricSpec("third_down_distance", "Average 3rd Down Distance", "yards", "Efficiency", "fresh", "third_down_distance", "third_down_distance", False, True),

    # ---- Explosiveness ----
    UnitMetricSpec("ppa_play", "PPA / Play", "ppa", "Explosiveness", "fresh", "ppa_play", "ppa_play", True, False),
    UnitMetricSpec("early_down_ppa_play", "Early Down PPA / Play", "ppa", "Explosiveness", "fresh", "early_down_ppa_play", "early_down_ppa_play", True, False),
    UnitMetricSpec("rush_ppa_play", "Rush PPA / Play", "ppa", "Explosiveness", "fresh", "rush_ppa_play", "rush_ppa_play", True, False),
    UnitMetricSpec("pass_ppa_dropback", "Pass PPA / Dropback", "ppa", "Explosiveness", "fresh", "pass_ppa_dropback", "pass_ppa_dropback", True, False),
    UnitMetricSpec("explosive_play_rate", "Explosive Play Rate", "rate", "Explosiveness", "ts", "explosivePlayRate", "explosivePlayRateAllowed", True, False),
    UnitMetricSpec("rush_explosive_rate", "Rush Explosive Rate", "rate", "Explosiveness", "ts", "rushExplosivePlayRate", "rushExplosivePlayRateAllowed", True, False),
    UnitMetricSpec("pass_explosive_rate", "Pass Explosive Rate", "rate", "Explosiveness", "ts", "passExplosivePlayRate", "passExplosivePlayRateAllowed", True, False),
    UnitMetricSpec("yards_per_successful_play", "Yards / Successful Play", "yards", "Explosiveness", "ts", "yardsPerSuccessfulPlay", "yardsPerSuccessfulPlayAllowed", True, False),

    # ---- Offensive Line (offense) / Defensive Line (defense) ----
    UnitMetricSpec("line_yards", "Line Yards", "yards", "Line Play", "fresh", "line_yards", "line_yards", True, False),
    UnitMetricSpec("opportunity_rate", "Opportunity Rate", "rate", "Line Play", "fresh", "opportunity_rate", "opportunity_rate", True, False),
    UnitMetricSpec("stuff_rate", "Stuff Rate", "rate", "Line Play", "fresh", "stuff_rate", "stuff_rate", False, True),
    UnitMetricSpec("rush_yards_per_attempt", "Rush Yards / Attempt", "yards", "Line Play", "ts", "rushYardsPerAttempt", "rushYardsPerAttemptAllowed", True, False),
    UnitMetricSpec("sack_rate", "Sack Rate", "rate", "Line Play", "ts", "sackRate", "defensiveSackRate", False, True),
    UnitMetricSpec("tfl_per_game", "Tackles For Loss / Game", "count", "Line Play", "ts_per_game", "tacklesForLoss", "tacklesForLossAllowed", False, True),

    # ---- Passing ----
    UnitMetricSpec("yards_per_dropback", "Yards / Dropback", "yards", "Passing", "ts", "netPassYardsPerDropback", "netPassYardsPerDropbackAllowed", True, False),
    UnitMetricSpec("pass_yards_per_game", "Pass Yards / Game", "yards", "Passing", "ts_per_game", "netPassYards", "netPassYardsAllowed", True, False),
    UnitMetricSpec("interceptions_per_game", "Interceptions / Game", "count", "Passing", "ts_per_game", "interceptionsThrown", "interceptionsMade", False, True),

    # ---- Situational & Finishing ----
    UnitMetricSpec("third_down_conversion_rate", "3rd Down Conversion Rate", "rate", "Situational", "ts", "thirdDownConversionRate", "thirdDownConversionRateAllowed", True, False),
    UnitMetricSpec("fourth_down_conversion_rate", "4th Down Conversion Rate", "rate", "Situational", "ts", "fourthDownConversionRate", "fourthDownConversionRateAllowed", True, False),
    UnitMetricSpec("red_zone_scoring_rate", "Red Zone Scoring Rate", "rate", "Situational", "ts", "redZonePossessionScoringRate", "redZonePossessionScoringRateAllowed", True, False),
    UnitMetricSpec("red_zone_td_rate", "Red Zone TD Rate", "rate", "Situational", "ts", "redZonePossessionTouchdownRate", "redZonePossessionTouchdownRateAllowed", True, False),
    UnitMetricSpec("points_per_drive", "Points / Drive", "points", "Situational", "ts", "pointsPerResolvedPossession", "pointsPerResolvedPossessionAllowed", True, False),

    # ---- Havoc & Turnovers ----
    UnitMetricSpec("havoc_rate", "Havoc Rate", "rate", "Havoc & Turnovers", "ts", "havocRateAllowed", "havocRate", False, True),
    UnitMetricSpec("turnovers_per_game", "Turnovers / Game", "count", "Havoc & Turnovers", "ts_per_game", "giveaways", "takeaways", False, True),
)

GROUP_ORDER = ("Efficiency", "Explosiveness", "Line Play", "Passing", "Situational", "Havoc & Turnovers")


def _family(play: dict[str, Any]) -> str | None:
    subtype = play.get("eventSubtype")
    if subtype in RUSH_SUBTYPES:
        return "RUSH"
    if subtype in PASS_SUBTYPES or subtype == "SACK":
        return "PASS"
    return None


def _season_2020_ts_fallback(raw_root: Path, canonical_root: Path) -> dict[str, dict[str, Any]]:
    """2020-only stand-in for every 'ts' (team_seasons.json) field SPECS needs,
    computed directly from that season's normalized plays using this repo's
    own existing play-level classifiers (classify_success, classify_explosive,
    classify_down_situation, classify_standard_dropback, classify_tfl) -- the
    exact same functions every other season's locked team_seasons.json was
    itself built from, just run here instead of read from a cached file that
    was never generated for 2020.

    Two fields are NOT computed here (redZonePossessionScoringRate/
    TouchdownRate, pointsPerResolvedPossession) -- both need drive-level
    field-position and scoring-possession reconciliation, which needs
    `isPossessionDrive`/`driveValidationStatus` on 2020's drives.json, and
    that canonicalization step was never built for 2020's drives (same root
    cause documented for Havoc Rate in offensive_profile.py's 2020 fallback).
    They come back None -- correctly excluded from ranking, not fabricated.
    """
    fbs_teams = _fbs_teams(canonical_root, 2020)
    plays = list(_season_plays(raw_root, Path("data/processed"), 2020))
    kneel_ids = high_confidence_kneel_ids(plays)

    def _blank():
        return {
            "success_n": 0, "success_hits": 0,
            "rush_success_n": 0, "rush_success_hits": 0,
            "pass_success_n": 0, "pass_success_hits": 0,
            "standard_n": 0, "standard_hits": 0,
            "passing_n": 0, "passing_hits": 0,
            "explosive_n": 0, "explosive_hits": 0,
            "rush_explosive_n": 0, "rush_explosive_hits": 0,
            "pass_explosive_n": 0, "pass_explosive_hits": 0,
            "successful_play_yards": 0.0, "successful_play_n": 0,
            "rush_yards": 0.0, "rush_n": 0,
            "dropback_yards": 0.0, "dropback_n": 0, "sack_n": 0,
            "third_down_n": 0, "third_down_hits": 0,
            "fourth_down_n": 0, "fourth_down_hits": 0,
            "tfl_n": 0,
            "interceptions": 0, "giveaways": 0, "takeaways": 0,
            "offense_snaps": 0, "havoc_hits": 0,
        }

    off_acc: dict[str, dict[str, Any]] = defaultdict(_blank)
    def_acc: dict[str, dict[str, Any]] = defaultdict(_blank)

    for play in plays:
        offense, defense = play.get("offense"), play.get("defense")
        if offense not in fbs_teams or defense not in fbs_teams:
            continue
        o, d = off_acc[offense], def_acc[defense]
        eligible = _eligible_offense_play(play)
        down = play.get("down")
        yards = play.get("analyticsYardsGained")
        family = _family(play)

        success = classify_success(play) if eligible else None
        if success is not None:
            for row in (o, d):
                row["success_n"] += 1
                row["success_hits"] += int(success)
                if family == "RUSH":
                    row["rush_success_n"] += 1
                    row["rush_success_hits"] += int(success)
                elif family == "PASS":
                    row["pass_success_n"] += 1
                    row["pass_success_hits"] += int(success)
            if success and _num(yards):
                o["successful_play_yards"] += yards
                o["successful_play_n"] += 1
                d["successful_play_yards"] += yards
                d["successful_play_n"] += 1
            situation = classify_down_situation(play)
            if situation == "STANDARD_DOWN":
                for row in (o, d):
                    row["standard_n"] += 1
                    row["standard_hits"] += int(success)
            elif situation == "PASSING_DOWN":
                for row in (o, d):
                    row["passing_n"] += 1
                    row["passing_hits"] += int(success)
            if down == 3:
                for row in (o, d):
                    row["third_down_n"] += 1
                    row["third_down_hits"] += int(success)
            elif down == 4:
                for row in (o, d):
                    row["fourth_down_n"] += 1
                    row["fourth_down_hits"] += int(success)

        explosive = classify_explosive(play)
        if explosive is not None:
            for row in (o, d):
                row["explosive_n"] += 1
                row["explosive_hits"] += int(explosive)
                if family == "RUSH":
                    row["rush_explosive_n"] += 1
                    row["rush_explosive_hits"] += int(explosive)
                elif family == "PASS":
                    row["pass_explosive_n"] += 1
                    row["pass_explosive_hits"] += int(explosive)

        if eligible and family == "RUSH" and _num(yards):
            o["rush_yards"] += yards; o["rush_n"] += 1
            d["rush_yards"] += yards; d["rush_n"] += 1

        # Turnovers, TFLs, and havoc need a broader gate than `eligible`:
        # `eligible` (success.py's own rule) excludes any play whose text
        # merely mentions "fumble"/"intercept" via hasStateTransitionModifier
        # -- which is every real turnover play, since that's exactly what
        # sets the modifier. Counting turnovers under `eligible` would
        # structurally always find zero. This block uses the same base
        # scrimmage/offensive-play/no-play gate but without that exclusion.
        broadly_eligible = bool(
            play.get("isScrimmagePlay") and play.get("isOffensivePlay") and not play.get("hasNoPlayContext")
        )
        if broadly_eligible:
            o["offense_snaps"] += 1
            d["offense_snaps"] += 1
            is_tfl = classify_tfl(play, kneel_ids)
            is_turnover = bool(play.get("isTurnover"))
            if is_tfl:
                o["tfl_n"] += 1
                d["tfl_n"] += 1
            # Havoc proxy (matches offensive_profile.py's own documented 2020
            # approximation): non-sack TFL, sack, or a turnover-flagged play.
            if is_tfl or play.get("eventSubtype") == "SACK" or is_turnover:
                o["havoc_hits"] += 1
                d["havoc_hits"] += 1
            if is_turnover:
                o["giveaways"] += 1
                d["takeaways"] += 1
                if play.get("eventSubtype") == "INTERCEPTION":
                    o["interceptions"] += 1
                    d["interceptions"] += 1

        cls = classify_standard_dropback(play)
        if cls in DROPBACK_VALID_CLASSES:
            o["dropback_n"] += 1
            d["dropback_n"] += 1
            if cls == "SACK":
                o["sack_n"] += 1
                d["sack_n"] += 1
            elif _num(yards):
                o["dropback_yards"] += yards
                d["dropback_yards"] += yards

    def _rate(hits: int, n: int) -> float | None:
        return hits / n if n else None

    def _finalize(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "successRate": _rate(row["success_hits"], row["success_n"]),
            "rushSuccessRate": _rate(row["rush_success_hits"], row["rush_success_n"]),
            "passSuccessRate": _rate(row["pass_success_hits"], row["pass_success_n"]),
            "standardDownSuccessRate": _rate(row["standard_hits"], row["standard_n"]),
            "passingDownSuccessRate": _rate(row["passing_hits"], row["passing_n"]),
            "explosivePlayRate": _rate(row["explosive_hits"], row["explosive_n"]),
            "rushExplosivePlayRate": _rate(row["rush_explosive_hits"], row["rush_explosive_n"]),
            "passExplosivePlayRate": _rate(row["pass_explosive_hits"], row["pass_explosive_n"]),
            "yardsPerSuccessfulPlay": row["successful_play_yards"] / row["successful_play_n"] if row["successful_play_n"] else None,
            "rushYardsPerAttempt": row["rush_yards"] / row["rush_n"] if row["rush_n"] else None,
            "sackRate": row["sack_n"] / row["dropback_n"] if row["dropback_n"] else None,
            "defensiveSackRate": row["sack_n"] / row["dropback_n"] if row["dropback_n"] else None,
            "netPassYardsPerDropback": row["dropback_yards"] / row["dropback_n"] if row["dropback_n"] else None,
            "netPassYardsPerDropbackAllowed": row["dropback_yards"] / row["dropback_n"] if row["dropback_n"] else None,
            "netPassYards": row["dropback_yards"],
            "netPassYardsAllowed": row["dropback_yards"],
            "thirdDownConversionRate": _rate(row["third_down_hits"], row["third_down_n"]),
            "fourthDownConversionRate": _rate(row["fourth_down_hits"], row["fourth_down_n"]),
            "tacklesForLoss": row["tfl_n"],
            "tacklesForLossAllowed": row["tfl_n"],
            # NOT row["interceptions"]/["giveaways"]/["takeaways"]: most real
            # interceptions/fumbles are recorded by CFBD under a different
            # playType (e.g. "Pass Incompletion" with interception-text
            # evidence), not the dedicated "Interception"/"Fumble" type this
            # count relies on -- the same reason havoc.py needs drive-level
            # turnover validation for the real seasons. Spot-checked: this
            # undercounts to near-zero for every team, not just Michigan.
            # Honest None beats a confidently wrong near-zero count.
            "interceptionsThrown": None,
            "interceptionsMade": None,
            "giveaways": None,
            "takeaways": None,
            "havocRateAllowed": row["havoc_hits"] / row["offense_snaps"] if row["offense_snaps"] else None,
            "havocRate": row["havoc_hits"] / row["offense_snaps"] if row["offense_snaps"] else None,
            "redZonePossessionScoringRate": None, "redZonePossessionScoringRateAllowed": None,
            "redZonePossessionTouchdownRate": None, "redZonePossessionTouchdownRateAllowed": None,
            "pointsPerResolvedPossession": None, "pointsPerResolvedPossessionAllowed": None,
        }

    teams = set(off_acc) | set(def_acc)
    out: dict[str, dict[str, Any]] = {}
    for team in teams:
        offense_fields = _finalize(off_acc[team])
        defense_fields = _finalize(def_acc[team])
        # merge: offense row supplies the base + *Allowed pulled from the defense accumulator's own numbers
        merged = dict(offense_fields)
        merged["successRateAllowed"] = _rate(def_acc[team]["success_hits"], def_acc[team]["success_n"])
        merged["rushSuccessRateAllowed"] = _rate(def_acc[team]["rush_success_hits"], def_acc[team]["rush_success_n"])
        merged["passSuccessRateAllowed"] = _rate(def_acc[team]["pass_success_hits"], def_acc[team]["pass_success_n"])
        merged["standardDownSuccessRateAllowed"] = _rate(def_acc[team]["standard_hits"], def_acc[team]["standard_n"])
        merged["passingDownSuccessRateAllowed"] = _rate(def_acc[team]["passing_hits"], def_acc[team]["passing_n"])
        merged["explosivePlayRateAllowed"] = _rate(def_acc[team]["explosive_hits"], def_acc[team]["explosive_n"])
        merged["rushExplosivePlayRateAllowed"] = _rate(def_acc[team]["rush_explosive_hits"], def_acc[team]["rush_explosive_n"])
        merged["passExplosivePlayRateAllowed"] = _rate(def_acc[team]["pass_explosive_hits"], def_acc[team]["pass_explosive_n"])
        merged["yardsPerSuccessfulPlayAllowed"] = def_acc[team]["successful_play_yards"] / def_acc[team]["successful_play_n"] if def_acc[team]["successful_play_n"] else None
        merged["rushYardsPerAttemptAllowed"] = def_acc[team]["rush_yards"] / def_acc[team]["rush_n"] if def_acc[team]["rush_n"] else None
        merged["defensiveSackRate"] = def_acc[team]["sack_n"] / def_acc[team]["dropback_n"] if def_acc[team]["dropback_n"] else None
        merged["netPassYardsPerDropbackAllowed"] = def_acc[team]["dropback_yards"] / def_acc[team]["dropback_n"] if def_acc[team]["dropback_n"] else None
        merged["netPassYardsAllowed"] = def_acc[team]["dropback_yards"]
        merged["thirdDownConversionRateAllowed"] = _rate(def_acc[team]["third_down_hits"], def_acc[team]["third_down_n"])
        merged["fourthDownConversionRateAllowed"] = _rate(def_acc[team]["fourth_down_hits"], def_acc[team]["fourth_down_n"])
        merged["tacklesForLossAllowed"] = def_acc[team]["tfl_n"]
        # interceptionsMade/takeaways stay None (see _finalize's comment above).
        merged["havocRate"] = def_acc[team]["havoc_hits"] / def_acc[team]["offense_snaps"] if def_acc[team]["offense_snaps"] else None
        out[team] = merged
    return out


def _season_2020_games(raw_root: Path, canonical_root: Path) -> dict[str, int]:
    """games-played count per team for 2020, since team_seasons.json (the
    normal source of `games`) was never built for that season."""
    fbs_teams = _fbs_teams(canonical_root, 2020)
    game_ids: dict[str, set[str]] = {}
    for play in _season_plays(raw_root, Path("data/processed"), 2020):
        offense, defense, gid = play.get("offense"), play.get("defense"), str(play.get("gameId"))
        for team in (offense, defense):
            if team in fbs_teams:
                game_ids.setdefault(team, set()).add(gid)
    return {team: len(ids) for team, ids in game_ids.items()}


def build_unit_detail_rows(raw_root: Path, processed_root: Path, canonical_root: Path, season: int) -> list[dict[str, Any]]:
    """One row per FBS team with every SPECS field (for offense AND defense),
    flat-keyed, ready for add_rankings(). Internal -- use build_unit_detail_profile."""
    fresh = compute_national_unit_metrics(raw_root, processed_root, canonical_root, season)
    fbs_teams = _fbs_teams(canonical_root, season)

    team_seasons_path = processed_root / "derived" / "seasons" / f"season={season}" / "team_seasons.json"
    if team_seasons_path.exists():
        team_seasons = {row["team"]: row for row in json.loads(team_seasons_path.read_text())}
    else:
        team_seasons = _season_2020_ts_fallback(raw_root, canonical_root)

    games_by_team = _season_2020_games(raw_root, canonical_root) if season in SEASONS_2020_ONLY_RAW else None

    rows: list[dict[str, Any]] = []
    for team in sorted(fbs_teams):
        f = fresh.get(team)
        ts = team_seasons.get(team)
        if f is None:
            continue
        games = games_by_team.get(team) if games_by_team is not None else (ts or {}).get("games")
        row: dict[str, Any] = {"team": team}
        for spec in SPECS:
            for side, field in (("offense", spec.offense_field), ("defense", spec.defense_field)):
                out_key = f"{side}_{spec.key}"
                if spec.source == "fresh":
                    row[out_key] = f[side].get(field)
                elif spec.source == "ts":
                    row[out_key] = (ts or {}).get(field)
                elif spec.source == "ts_per_game":
                    raw = (ts or {}).get(field)
                    row[out_key] = (raw / games) if isinstance(raw, (int, float)) and games else None
        rows.append(row)
    return rows


def build_unit_detail_profile(raw_root: Path, processed_root: Path, canonical_root: Path, season: int, team: str, side: str) -> dict[str, Any]:
    if side not in ("offense", "defense"):
        raise ValueError(f"side must be 'offense' or 'defense', got {side!r}")

    rows = build_unit_detail_rows(raw_root, processed_root, canonical_root, season)
    ranking_metrics = [
        Metric(f"offense_{s.key}", s.label, s.unit, s.offense_higher_is_better, s.group, "offense") for s in SPECS
    ] + [
        Metric(f"defense_{s.key}", s.label, s.unit, s.defense_higher_is_better, s.group, "defense") for s in SPECS
    ]
    ranked = add_rankings(rows, metrics=ranking_metrics, prefix="")
    field_size = len(rows)

    target = next((r for r in ranked if r["team"] == team), None)
    if target is None:
        raise ValueError(f"{team} not found in {season} FBS field (field_size={field_size})")

    metrics_out = []
    for spec in SPECS:
        field = f"{side}_{spec.key}"
        value = target.get(field)
        rank = target.get(f"{field}_rank")
        pct01 = target.get(f"{field}_percentile")
        higher_is_better = spec.offense_higher_is_better if side == "offense" else spec.defense_higher_is_better
        metrics_out.append({
            "key": spec.key,
            "label": spec.label,
            "group": spec.group,
            "value": round(value, 4) if isinstance(value, float) else value,
            "unit": spec.unit,
            "rank": rank,
            "fieldSize": field_size,
            "percentile": round(pct01 * 100, 1) if isinstance(pct01, float) else None,
            "higherIsBetter": higher_is_better,
        })

    return {
        "version": UNIT_DETAIL_VERSION,
        "season": season,
        "team": team,
        "side": side,
        "fieldSize": field_size,
        "groups": list(GROUP_ORDER),
        "sampleSizeCaveat": (
            "2020 was an abbreviated, largely conference-only COVID season (8-13 games per team); "
            "treat this profile as a smaller, noisier sample than a normal season."
        ) if season in SEASONS_2020_ONLY_RAW else None,
        "metrics": metrics_out,
    }


def publish(raw_root: Path, processed_root: Path, canonical_root: Path, published_root: Path, seasons: list[int], team: str = "Michigan") -> list[dict[str, Any]]:
    manifest = []
    for season in seasons:
        for side in ("offense", "defense"):
            profile = build_unit_detail_profile(raw_root, processed_root, canonical_root, season, team, side)
            target = published_root / str(season) / "analytics" / f"{side}-detail.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
            manifest.append({"season": season, "side": side, "fieldSize": profile["fieldSize"], "path": str(target)})
            print(f"season {season} {side}: field_size={profile['fieldSize']} -> {target}")
    return manifest


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--seasons", type=int, nargs="+", default=None)
    parser.add_argument("--team", type=str, default="Michigan")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--canonical-root", type=Path, default=Path("data/canonical"))
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    args = parser.parse_args()
    seasons = args.seasons if args.seasons is not None else list(range(args.start_year, args.end_year + 1))
    publish(args.raw_root, args.processed_root, args.canonical_root, args.published_root, seasons, args.team)


if __name__ == "__main__":
    main()
