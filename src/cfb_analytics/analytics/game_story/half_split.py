"""First-half vs. second-half success-rate splits from canonical plays.

Definition version: half-split-v1

Pure observation, no causal claim: this only reports that a rate changed
between periods 1-2 and 3-4. It deliberately does not attempt to attribute
the change to a "coaching adjustment" or any other cause -- that's a film
question for the video, not something the numbers alone establish.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.config.constants import DEFAULT_PROCESSED_ROOT

HALF_SPLIT_VERSION = "half-split-v1"


def _rate(successes: int, eligible: int) -> float | None:
    return successes / eligible if eligible else None


def half_split_success_rate(season: int, season_type: str, week: int, game_id: str | int, team: str, processed_root: Path = DEFAULT_PROCESSED_ROOT) -> dict[str, Any]:
    """First-half vs second-half offensive success rate for `team` in one game."""
    plays = json.loads((canonical_partition_dir(processed_root, season, season_type, week) / "plays.json").read_text())
    game_plays = [p for p in plays if str(p.get("gameId")) == str(game_id) and p.get("offense") == team]
    first_half = [p for p in game_plays if (p.get("period") or 0) <= 2]
    second_half = [p for p in game_plays if (p.get("period") or 0) > 2]

    def summarize(plays_subset: list[dict[str, Any]]) -> dict[str, Any]:
        eligible = successful = 0
        for p in plays_subset:
            result = classify_success(p)
            if result is not None:
                eligible += 1
                successful += int(result)
        return {"eligiblePlays": eligible, "successfulPlays": successful, "successRate": _rate(successful, eligible)}

    return {
        "team": team,
        "firstHalf": summarize(first_half),
        "secondHalf": summarize(second_half),
        "definitionVersion": HALF_SPLIT_VERSION,
    }
