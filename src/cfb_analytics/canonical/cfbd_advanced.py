"""Canonical parsing for CFBD's advanced game-level sources (Tier 2).

Two distinct CFBD endpoints are used for two distinct, non-overlapping sets
of concepts -- picked so no concept is ever sourced from two different CFBD
endpoints at once (see module docstrings on each parser for why):

- `/stats/game/advanced` (`advanced_game_stats.json`, one call per
  season/week -- cheap, so this is backfillable for every historical
  season): plays, drives, PPA, success rate, explosiveness, rushing
  efficiency (stuff rate, power success, line/second-level/open-field
  yards). Canonical source version: CFBD_STATS_GAME_ADVANCED_VERSION.
- `/game/box/advanced` (`advanced_box_scores.json`, one call per game --
  the only CFBD source for havoc, scoring opportunities, and field
  position; not backfillable at the same low cost). Canonical source
  version: CFBD_GAME_BOX_ADVANCED_VERSION.

Every row keeps a `sourceVersion` and `sourceEndpoint` field so a value's
provenance is never ambiguous. Raw responses are never modified in place;
this module only reads and reshapes them into a (gameId, team) keyed dict.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.storage import partition_dir

CFBD_STATS_GAME_ADVANCED_VERSION = "cfbd-stats-game-advanced-v1"
CFBD_GAME_BOX_ADVANCED_VERSION = "cfbd-game-box-advanced-v1"


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _n(v: Any) -> float | None:
    return float(v) if _num(v) else None


def _normalize_stats_game_advanced_row(row: dict[str, Any]) -> dict[str, Any]:
    """One (gameId, team) row from /stats/game/advanced -> flat, clearly
    named fields. `offense` is this team's own output; `defense` is what
    this team's own defense allowed (CFBD's own per-team split, not a
    cross-team lookup)."""
    off = row.get("offense") or {}
    deff = row.get("defense") or {}

    def side(block: dict[str, Any], prefix: str) -> dict[str, Any]:
        std = block.get("standardDowns") or {}
        pass_downs = block.get("passingDowns") or {}
        rushing = block.get("rushingPlays") or {}
        passing = block.get("passingPlays") or {}
        return {
            f"{prefix}_plays": block.get("plays"),
            f"{prefix}_drives": block.get("drives"),
            f"{prefix}_ppa_per_play": _n(block.get("ppa")),
            f"{prefix}_total_ppa": _n(block.get("totalPPA")),
            f"{prefix}_success_rate": _n(block.get("successRate")),
            f"{prefix}_explosiveness": _n(block.get("explosiveness")),
            f"{prefix}_power_success": _n(block.get("powerSuccess")),
            f"{prefix}_stuff_rate": _n(block.get("stuffRate")),
            f"{prefix}_line_yards_per_play": _n(block.get("lineYards")),
            f"{prefix}_line_yards_total": _n(block.get("lineYardsTotal")),
            f"{prefix}_second_level_yards_per_play": _n(block.get("secondLevelYards")),
            f"{prefix}_second_level_yards_total": _n(block.get("secondLevelYardsTotal")),
            f"{prefix}_open_field_yards_per_play": _n(block.get("openFieldYards")),
            f"{prefix}_open_field_yards_total": _n(block.get("openFieldYardsTotal")),
            f"{prefix}_standard_downs_ppa": _n(std.get("ppa")),
            f"{prefix}_standard_downs_success_rate": _n(std.get("successRate")),
            f"{prefix}_standard_downs_explosiveness": _n(std.get("explosiveness")),
            f"{prefix}_passing_downs_ppa": _n(pass_downs.get("ppa")),
            f"{prefix}_passing_downs_success_rate": _n(pass_downs.get("successRate")),
            f"{prefix}_passing_downs_explosiveness": _n(pass_downs.get("explosiveness")),
            f"{prefix}_rushing_ppa_per_play": _n(rushing.get("ppa")),
            f"{prefix}_rushing_total_ppa": _n(rushing.get("totalPPA")),
            f"{prefix}_rushing_success_rate": _n(rushing.get("successRate")),
            f"{prefix}_rushing_explosiveness": _n(rushing.get("explosiveness")),
            f"{prefix}_passing_ppa_per_play": _n(passing.get("ppa")),
            f"{prefix}_passing_total_ppa": _n(passing.get("totalPPA")),
            f"{prefix}_passing_success_rate": _n(passing.get("successRate")),
            f"{prefix}_passing_explosiveness": _n(passing.get("explosiveness")),
        }

    out = {
        "gameId": str(row.get("gameId")),
        "team": row.get("team"),
        "opponent": row.get("opponent"),
        "season": row.get("season"),
        "week": row.get("week"),
        "seasonType": row.get("seasonType"),
        "sourceEndpoint": "/stats/game/advanced",
        "sourceVersion": CFBD_STATS_GAME_ADVANCED_VERSION,
    }
    out.update(side(off, "offense"))
    out.update(side(deff, "defense"))
    return out


def load_stats_game_advanced_season(raw_root: Path, season: int) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for season_type, week in discover_partitions(raw_root, season):
        path = partition_dir(raw_root, season, season_type, week) / "advanced_game_stats.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            normalized = _normalize_stats_game_advanced_row(row)
            out[(normalized["gameId"], normalized["team"])] = normalized
    return out


def _normalize_game_box_advanced(game_id: str, payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """One /game/box/advanced payload (one game) -> {(gameId, team): row}.

    `havoc` in CFBD's payload is keyed by the DEFENSE that created it (team
    X's row = the share of X's OPPONENT's plays that X's defense disrupted).
    This is cross-mapped here so each team's row carries both
    `havoc_allowed` (this team's offense, i.e. the opponent's havoc row)
    and `havoc_forced` (this team's own defense, i.e. this team's own havoc
    row) -- so callers never have to know about the cross-team lookup.
    scoringOpportunities and fieldPosition are already this team's own
    offensive output in CFBD's payload; no cross-mapping needed there.
    """
    teams = payload.get("teams") or {}
    havoc_by_team = {r.get("team"): r for r in (teams.get("havoc") or [])}
    scoring_by_team = {r.get("team"): r for r in (teams.get("scoringOpportunities") or [])}
    field_pos_by_team = {r.get("team"): r for r in (teams.get("fieldPosition") or [])}

    team_names = set(havoc_by_team) | set(scoring_by_team) | set(field_pos_by_team)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for team in team_names:
        opponent = next((t for t in team_names if t != team), None)
        own_havoc = havoc_by_team.get(team) or {}
        opp_havoc = havoc_by_team.get(opponent) or {} if opponent else {}
        scoring = scoring_by_team.get(team) or {}
        field_pos = field_pos_by_team.get(team) or {}
        out[(game_id, team)] = {
            "gameId": game_id,
            "team": team,
            "opponent": opponent,
            "sourceEndpoint": "/game/box/advanced",
            "sourceVersion": CFBD_GAME_BOX_ADVANCED_VERSION,
            "havoc_forced": _n(own_havoc.get("total")),
            "havoc_forced_front_seven": _n(own_havoc.get("frontSeven")),
            "havoc_forced_db": _n(own_havoc.get("db")),
            "havoc_allowed": _n(opp_havoc.get("total")),
            "havoc_allowed_front_seven": _n(opp_havoc.get("frontSeven")),
            "havoc_allowed_db": _n(opp_havoc.get("db")),
            "scoring_opportunities": scoring.get("opportunities"),
            "scoring_opportunity_points": _n(scoring.get("points")),
            "points_per_scoring_opportunity": _n(scoring.get("pointsPerOpportunity")),
            "average_start_yards_to_goal": _n(field_pos.get("averageStart")),
            "average_starting_predicted_points": _n(field_pos.get("averageStartingPredictedPoints")),
        }
    return out


def load_game_box_advanced_season(raw_root: Path, season: int) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for season_type, week in discover_partitions(raw_root, season):
        path = partition_dir(raw_root, season, season_type, week) / "advanced_box_scores.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            game_id = str(row.get("gameId"))
            # advanced_box_scores.json stores {"gameId": ..., **rawPayload} per game.
            payload = {k: v for k, v in row.items() if k != "gameId"}
            if not payload.get("teams"):
                continue
            out.update(_normalize_game_box_advanced(game_id, payload))
    return out
