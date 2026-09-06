"""Fourth-down decision grading: go-for-it vs. field goal vs. punt.

Built entirely on this repo's independent EPA v2 research model
(``NextScoreExpectedPoints`` / ``epa-v2-research-next-score``), never on CFBD's
``ppa``. Three empirical historical rate curves, fit on the full validated
corpus, feed the same expected-points model to price each option:

- go-for-it conversion rate, by distance-to-go
- field-goal make rate, by kick distance (yardsToGoal + 17)
- punt outcome, by the receiving team's resulting yardsToGoal

This is research-grade, retrospective-analysis infrastructure: it grades
decisions against what has historically worked at scale, not a live win-
probability model, and it is not part of this repo's locked production
metric contract. See ``docs/METRIC_REGISTRY.md`` conventions for why that
distinction matters.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.epa_v1_research import (
    NextScoreExpectedPoints,
    _game_groups,
    half_number,
    play_epa_v2,
    state_eligible,
)
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions

FOURTH_DOWN_MODEL_VERSION = "fourth-down-decision-v1-epa-v2"
GO_FOR_IT_SUBTYPES = {"RUSH", "RUSH_TD", "PASS_COMPLETION", "PASS_TD", "PASS_INCOMPLETE", "PASS_UNSPECIFIED", "SACK"}
FIELD_GOAL_SUBTYPES = {"FIELD_GOAL_GOOD", "FIELD_GOAL_MISSED", "BLOCKED_FIELD_GOAL"}
PUNT_SUBTYPES = {"PUNT", "BLOCKED_PUNT", "BLOCKED_PUNT_TD", "PUNT_RETURN_TD"}

FG_DISTANCE_WIDTH = 5
PUNT_YTG_WIDTH = 10


def _fg_bucket(kick_distance: float) -> int:
    return int(kick_distance // FG_DISTANCE_WIDTH) * FG_DISTANCE_WIDTH


def _punt_bucket(ytg: float) -> int:
    return int(ytg // PUNT_YTG_WIDTH) * PUNT_YTG_WIDTH


def load_season_plays(raw_root: Path, processed_root: Path, season: int):
    for st, wk in discover_partitions(raw_root, season):
        path = canonical_partition_dir(processed_root, season, st, wk) / "plays.json"
        if path.exists():
            yield st, wk, json.loads(path.read_text())


class FourthDownRateCurves:
    """Empirical conversion / FG-make / punt-outcome rates from real history."""

    def __init__(self, min_count: int = 25) -> None:
        self.min_count = min_count
        self.go_stats: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # distance -> [attempts, conversions]
        self.fg_stats: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # kick-distance bucket -> [attempts, makes]
        self.punt_stats: dict[int, list[float]] = defaultdict(lambda: [0, 0.0])  # ytg bucket -> [count, sum(resultYtg)]

    def accumulate(self, plays: list[dict[str, Any]]) -> None:
        for rows in _game_groups(plays).values():
            ordered = [
                p for p in rows
                if p.get("offense") and not p.get("isAdministrative") and not p.get("hasNoPlayContext")
            ]
            for i, play in enumerate(ordered):
                subtype = str(play.get("eventSubtype") or "")
                down = play.get("down")
                dist = play.get("distance")
                ytg = play.get("yardsToGoal")

                if down == 4 and subtype in GO_FOR_IT_SUBTYPES and isinstance(dist, (int, float)):
                    converted = subtype in {"RUSH_TD", "PASS_TD"}
                    if not converted and i + 1 < len(ordered):
                        nxt = ordered[i + 1]
                        converted = nxt.get("driveId") == play.get("driveId") and nxt.get("down") == 1
                    d = min(int(dist), 15)
                    self.go_stats[d][0] += 1
                    self.go_stats[d][1] += 1 if converted else 0

                elif subtype in FIELD_GOAL_SUBTYPES and isinstance(ytg, (int, float)):
                    kick_distance = float(ytg) + 17.0
                    bucket = _fg_bucket(kick_distance)
                    self.fg_stats[bucket][0] += 1
                    self.fg_stats[bucket][1] += 1 if subtype == "FIELD_GOAL_GOOD" else 0

                elif subtype in PUNT_SUBTYPES and isinstance(ytg, (int, float)):
                    for nxt in ordered[i + 1:]:
                        nxt_ytg = nxt.get("yardsToGoal")
                        if nxt.get("offense") and nxt.get("offense") != play.get("offense") and isinstance(nxt_ytg, (int, float)):
                            bucket = _punt_bucket(float(ytg))
                            self.punt_stats[bucket][0] += 1
                            self.punt_stats[bucket][1] += float(nxt_ytg)
                            break
                        if nxt.get("offense") == play.get("offense"):
                            break

    def go_rate(self, distance: float) -> float | None:
        d = min(int(round(distance)), 15)
        candidates = sorted(self.go_stats.keys(), key=lambda k: abs(k - d))
        pooled_att = pooled_conv = 0
        for k in candidates:
            att, conv = self.go_stats[k]
            pooled_att += att
            pooled_conv += conv
            if pooled_att >= self.min_count:
                break
        return pooled_conv / pooled_att if pooled_att else None

    def fg_rate(self, kick_distance: float) -> float | None:
        bucket = _fg_bucket(kick_distance)
        buckets = sorted(self.fg_stats.keys(), key=lambda k: abs(k - bucket))
        att = make = 0
        for k in buckets:
            a, m = self.fg_stats[k]
            att += a
            make += m
            if k == bucket and att >= self.min_count:
                break
            if att >= self.min_count * 2:
                break
        return make / att if att else None

    def punt_result_ytg(self, ytg: float) -> float | None:
        bucket = _punt_bucket(ytg)
        buckets = sorted(self.punt_stats.keys(), key=lambda k: abs(k - bucket))
        n = total = 0.0
        for k in buckets:
            cnt, s = self.punt_stats[k]
            n += cnt
            total += s
            if n >= self.min_count:
                break
        return total / n if n else None

    def to_json(self) -> dict[str, Any]:
        return {
            "goForIt": {str(k): {"attempts": v[0], "conversions": v[1], "rate": v[1] / v[0] if v[0] else None} for k, v in sorted(self.go_stats.items())},
            "fieldGoal": {str(k): {"attempts": v[0], "makes": v[1], "rate": v[1] / v[0] if v[0] else None} for k, v in sorted(self.fg_stats.items())},
            "punt": {str(k): {"count": v[0], "avgResultYardsToGoal": v[1] / v[0] if v[0] else None} for k, v in sorted(self.punt_stats.items())},
        }


def _synthetic_state(template: dict[str, Any], *, down: int, distance: float, yards_to_goal: float) -> dict[str, Any]:
    state = dict(template)
    state["down"] = down
    state["distance"] = distance
    state["yardsToGoal"] = yards_to_goal
    return state


def grade_fourth_down(
    play: dict[str, Any],
    ep_model: NextScoreExpectedPoints,
    rates: FourthDownRateCurves,
) -> dict[str, Any] | None:
    """Grade one 4th-down decision. ``play`` is the actual snap taken."""
    down, distance, ytg = play.get("down"), play.get("distance"), play.get("yardsToGoal")
    if down != 4 or not isinstance(distance, (int, float)) or not isinstance(ytg, (int, float)):
        return None
    distance, ytg = float(distance), float(ytg)

    subtype = str(play.get("eventSubtype") or "")
    if subtype in GO_FOR_IT_SUBTYPES:
        actual = "go"
    elif subtype in FIELD_GOAL_SUBTYPES:
        actual = "fieldGoal"
    elif subtype in PUNT_SUBTYPES:
        actual = "punt"
    else:
        return None

    ev: dict[str, float | None] = {}

    # Go for it: convert -> 1st-and-10 at (ytg - distance), roughly; fail -> opponent ball at same spot, flipped.
    go_rate = rates.go_rate(distance)
    if go_rate is not None:
        new_ytg_success = max(ytg - distance, 0.0)
        if new_ytg_success <= 0:
            ep_success = 6.5  # scored: fixed value close to a TD, PAT not modeled separately
        else:
            ep_success = ep_model.predict(_synthetic_state(play, down=1, distance=min(10, new_ytg_success), yards_to_goal=new_ytg_success))
        ep_fail = ep_model.predict(_synthetic_state(play, down=1, distance=10, yards_to_goal=100 - ytg))
        if ep_success is not None and ep_fail is not None:
            ev["go"] = go_rate * ep_success + (1 - go_rate) * (-ep_fail)

    # Field goal: 17 added for spot of kick; miss -> opponent ball at spot of kick (same yardsToGoal, flipped), floor at their own 20.
    kick_distance = ytg + 17.0
    fg_rate = rates.fg_rate(kick_distance) if kick_distance <= 66 else None
    if fg_rate is not None:
        opp_ytg_on_miss = min(100 - ytg, 80.0)
        ep_make = 3.0
        ep_miss = ep_model.predict(_synthetic_state(play, down=1, distance=10, yards_to_goal=opp_ytg_on_miss))
        if ep_miss is not None:
            ev["fieldGoal"] = fg_rate * ep_make + (1 - fg_rate) * (-ep_miss)

    # Punt: opponent starts at the historical average resulting field position.
    punt_result = rates.punt_result_ytg(ytg)
    if punt_result is not None:
        ep_after_punt = ep_model.predict(_synthetic_state(play, down=1, distance=10, yards_to_goal=punt_result))
        if ep_after_punt is not None:
            ev["punt"] = -ep_after_punt

    if not ev:
        return None

    recommended = max(ev, key=lambda k: ev[k])
    return {
        "gameId": play.get("gameId"),
        "down": down,
        "distance": distance,
        "yardsToGoal": ytg,
        "actual": actual,
        "actualEv": ev.get(actual),
        "recommended": recommended,
        "recommendedEv": ev[recommended],
        "evLost": (ev[recommended] - ev.get(actual, ev[recommended])) if actual in ev else None,
        "ev": ev,
        "goForItRate": go_rate,
        "fieldGoalMakeRate": fg_rate,
        "definitionVersion": FOURTH_DOWN_MODEL_VERSION,
    }
