"""Quality gates and frozen-corpus comparison for broad source facts."""
from __future__ import annotations

from collections import Counter

from cfb_analytics.ingestion.games import classify_matchup, has_fbs_participant


class FactIntegrityError(ValueError):
    pass


def validate_fact_partition(games: list[dict], drives: list[dict], plays: list[dict]) -> dict:
    game_ids = [str(game.get("id")) for game in games]
    allowed = set(game_ids)
    errors = []
    if len(game_ids) != len(allowed):
        errors.append("duplicate game IDs")
    if any(game.get("id") is None for game in games):
        errors.append("missing stable game ID")
    if any(not has_fbs_participant(game) for game in games):
        errors.append("game has no FBS participant")
    if any(str(row.get("gameId")) not in allowed for row in drives):
        errors.append("orphan/out-of-universe drive")
    if any(str(row.get("gameId")) not in allowed for row in plays):
        errors.append("orphan/out-of-universe play")
    if errors:
        raise FactIntegrityError("; ".join(errors))
    matchup_counts = Counter(classify_matchup(game) for game in games)
    return {
        "status": "PASS",
        "games": len(games),
        "drives": len(drives),
        "plays": len(plays),
        "fbs_vs_fbs_games": matchup_counts["fbs_vs_fbs"],
        "fbs_vs_non_fbs_games": matchup_counts["fbs_vs_non_fbs"],
    }


def compare_legacy_universe(legacy_games: list[dict], fact_games: list[dict]) -> dict:
    legacy = {str(game.get("id")) for game in legacy_games}
    facts = {str(game.get("id")) for game in fact_games}
    missing = sorted(legacy - facts)
    added = sorted(facts - legacy)
    if missing:
        raise FactIntegrityError(f"broad fact universe dropped {len(missing)} legacy games")
    return {
        "status": "PASS",
        "legacy_games": len(legacy),
        "fact_games": len(facts),
        "legacy_games_missing": 0,
        "additional_games": len(added),
        "additional_game_ids": added,
    }

