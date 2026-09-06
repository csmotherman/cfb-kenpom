from __future__ import annotations

import math
from collections import Counter


class IntegrityError(ValueError):
    pass


def validate_team_games(rows: list[dict]) -> dict:
    keys = [(str(row.get("game_id")), row.get("team_id")) for row in rows]
    games = Counter(str(row.get("game_id")) for row in rows)
    errors = []
    if len(keys) != len(set(keys)):
        errors.append("duplicate (game_id, team_id)")
    if any(not key[0] or key[1] is None for key in keys):
        errors.append("missing stable game/team identifier")
    if any(count != 2 for count in games.values()):
        errors.append("game does not have exactly two team rows")
    by_key = {(str(row["game_id"]), row["team_id"]): row for row in rows}
    for row in rows:
        peer = by_key.get((str(row["game_id"]), row.get("opponent_id")))
        if peer is None or peer.get("opponent_id") != row.get("team_id"):
            errors.append(f"asymmetric opponent relationship: {row['game_id']}")
            break
        pf, pa = row.get("points_for"), row.get("points_against")
        if pf is not None and (pf < 0 or pa < 0 or pf != peer.get("points_against") or pa != peer.get("points_for")):
            errors.append(f"impossible score relationship: {row['game_id']}")
            break
    if errors:
        raise IntegrityError("; ".join(errors))
    return {"status": "PASS", "team_game_rows": len(rows), "games": len(games), "duplicate_keys": 0}


def validate_team_seasons(rows: list[dict]) -> dict:
    keys = [(row.get("season"), row.get("team_id")) for row in rows]
    errors = []
    if len(keys) != len(set(keys)):
        errors.append("duplicate (season, team_id)")
    if any(row.get("classification") != "fbs" for row in rows):
        errors.append("unresolved/non-FBS membership in ranking universe")
    reconstructions = {
        "successRate": ("successfulPlays", "successEligiblePlays"),
        "successRateAllowed": ("successfulPlaysAllowed", "successEligiblePlaysAllowed"),
        "pointsPerResolvedPossession": ("possessionPoints", "resolvedPointPossessions"),
    }
    max_error = 0.0
    for row in rows:
        for metric, (numerator, denominator) in reconstructions.items():
            if row.get(metric) is None or not row.get(denominator):
                continue
            error = abs(float(row[metric]) - float(row[numerator]) / float(row[denominator]))
            max_error = max(max_error, error)
            if error > 1e-12:
                errors.append(f"metric reconstruction failed: {row.get('team')} {metric}")
    if errors:
        raise IntegrityError("; ".join(errors[:10]))
    return {"status": "PASS", "team_season_rows": len(rows), "duplicate_keys": 0, "max_reconstruction_error": max_error}

