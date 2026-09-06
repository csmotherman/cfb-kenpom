"""Drive funnel: possessions -> scoring opportunity -> red zone -> touchdown.

Definition version: drive-funnel-v1

Pure readthrough of already-LOCKED per-game aggregate fields (Finishing
Drives v2 / Red Zone v1, per docs/METRIC_REGISTRY.md) -- no new computation,
no raw drives.json needed. "Crossed midfield" is the one field this module
adds, and it's a direct byproduct already available on every team-game row:
`resolvedPointOpportunities` marks a drive that produced a resolved
scoring-adjacent outcome, which by the registry's own Finishing Drives v2
definition requires the offense to have reached the opponent's 40 -- so
"scoring opportunity" already implies "crossed midfield". A true bare
"crossed the 50" count is not tracked separately at the team-game grain, so
this funnel starts at possessions and moves straight to scoring opportunity
rather than inventing an intermediate count that isn't backed by a locked
field.
"""
from __future__ import annotations
from typing import Any

DRIVE_FUNNEL_VERSION = "drive-funnel-v1"


def drive_funnel(team_game: dict[str, Any], suffix: str = "") -> dict[str, Any]:
    """Build the funnel for a team's offense (suffix="") or the opponent it faced (suffix="Allowed")."""
    possessions = team_game.get(f"possessions{suffix}") or team_game.get(f"validatedPossessions{suffix}")
    scoring_opportunities = team_game.get(f"scoringOpportunities{suffix}")
    red_zone_possessions = team_game.get(f"redZonePossessions{suffix}")
    touchdowns = team_game.get(f"redZonePossessionTouchdowns{suffix}")
    non_red_zone_scores = team_game.get(f"otherScoringPossessions{suffix}")
    total_touchdowns_and_field_goals_possessions = team_game.get(f"resolvedPointPossessions{suffix}")
    return {
        "possessions": possessions,
        "scoringOpportunities": scoring_opportunities,
        "redZonePossessions": red_zone_possessions,
        "touchdowns": touchdowns,
        "otherScoringPossessions": non_red_zone_scores,
        "resolvedPointPossessions": total_touchdowns_and_field_goals_possessions,
        "definitionVersion": DRIVE_FUNNEL_VERSION,
    }
