"""Candidate story generation and ranking for a single Michigan game.

Definition version: game-story-v1

This is the layer that turns locked numbers into the handful of stories a
Game Room page actually shows. Two hard rules enforced by construction, not
convention:

1. Headlines come from a fixed set of Python functions, not free-text
   generation -- the set of sentences this module can produce is closed and
   reviewable, which makes an unhedged causal claim structurally impossible
   to emit (there is no code path that writes "X caused Y").
2. Every candidate carries its own `metricStatus` (LOCKED metrics only feed
   this module -- see opponent_baseline.METRIC_SPECS, all of which are
   locked, registry-documented fields) and `signalClass` from signal.py, so
   a thin-sample claim is labeled as such rather than presented flat.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from cfb_analytics.analytics.game_story.opponent_baseline import (
    METRIC_SPECS,
    NATIONALLY_RANKED_METRICS,
    aggregate_rate,
    opponent_baseline_excluding_game,
)
from cfb_analytics.analytics.game_story.deltas import normalized_delta, percentile_within_opponent_season
from cfb_analytics.analytics.game_story.signal import classify_signal
from cfb_analytics.config.constants import DEFAULT_PUBLISHED_ROOT
from pathlib import Path
import json

STORY_VERSION = "game-story-v1"
CONCERN_DELTA_THRESHOLD = -0.05  # a defense/offense side underperforming opponent-normal by 5+ points is a real concern
MAX_STORIES = 6
MIN_STORIES = 3


@dataclass
class Candidate:
    topic: str
    side: str  # "offense" or "defense", from Michigan's perspective
    metric: str
    headline: str
    evidence: list[str]
    context: dict[str, Any]
    why_it_matters: str
    video_angle: str
    signal_class: str
    delta: float | None
    percentile: dict[str, Any]
    metric_status: str = "LOCKED"
    definition_version: str = "opponent-adjusted-delta-v1"

    def polarity(self) -> str:
        if self.delta is None:
            return "neutral"
        return "concern" if self.delta < CONCERN_DELTA_THRESHOLD else "strength" if self.delta > 0.03 else "neutral"

    def score(self) -> float:
        return abs(self.delta) if self.delta is not None else 0.0


def _pct(x: float | None) -> str:
    return f"{x * 100:.1f}%" if x is not None else "n/a"


def _pp(x: float | None) -> str:
    return f"{x * 100:+.1f}" if x is not None else "n/a"


# Metrics whose raw value is a 0-1 rate (format as a percentage). Anything
# not listed here (points-per-possession, yards-per-play, field position)
# is a plain decimal/yardage number, not a rate -- multiplying it by 100
# would be nonsense (5.0 points/opportunity is not "500%").
_RATE_METRICS = {
    "successRate", "successRateAllowed", "rushSuccessRate", "rushSuccessRateAllowed",
    "passSuccessRate", "passSuccessRateAllowed", "explosivePlayRate", "explosivePlayRateAllowed",
    "havocRate", "havocRateAllowed", "standardDownSuccessRate", "standardDownSuccessRateAllowed",
    "passingDownSuccessRate", "passingDownSuccessRateAllowed", "thirdDownConversionRate",
    "thirdDownConversionRateAllowed", "redZonePossessionTouchdownRate", "redZonePossessionTouchdownRateAllowed",
}


def _format_value(metric: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    if metric in _RATE_METRICS:
        return _pct(value)
    return f"{value:.2f}"


def _format_delta(metric: str, delta: float | None) -> str:
    if delta is None:
        return "n/a"
    if metric in _RATE_METRICS:
        return f"{_pp(delta)} points"
    return f"{delta:+.2f}"


def _story(topic: str, side: str, metric: str, mi_game: dict[str, Any], baseline: dict[str, Any], percentile: dict[str, Any], headline: str, why: str, angle: str, extra_evidence: list[str] | None = None) -> Candidate:
    game_value = mi_game.get(metric)
    baseline_value = baseline["rates"].get(metric)
    denom_field = METRIC_SPECS[metric][1]
    sample_size = mi_game.get(denom_field)
    delta = normalized_delta(metric, game_value, baseline_value)
    evidence = [
        f"Michigan this game: {_format_value(metric, game_value)}",
        f"{baseline['opponent'].replace('-', ' ').title()} normal (season, excl. this game, {baseline['gamesUsed']} games): {_format_value(metric, baseline_value)}",
        f"Difference vs. expectation: {_format_delta(metric, delta)}",
    ] + (extra_evidence or [])
    return Candidate(
        topic=topic, side=side, metric=metric,
        headline=headline, evidence=evidence,
        context={"gameValue": game_value, "opponentBaseline": baseline_value, "opponentGamesUsed": baseline["gamesUsed"], "nationallyRanked": metric in NATIONALLY_RANKED_METRICS},
        why_it_matters=why, video_angle=angle,
        signal_class=classify_signal(metric, denom_field, sample_size),
        delta=delta, percentile=percentile,
    )


HALF_SPLIT_NOTABLE_THRESHOLD = 0.15  # 15 points of success-rate swing between halves


def _half_split_candidate(half_split_mi: dict[str, Any] | None) -> Candidate | None:
    """Observation-only, never causal: reports a first-half/second-half swing without attributing a cause."""
    if half_split_mi is None:
        return None
    first = half_split_mi["firstHalf"]["successRate"]
    second = half_split_mi["secondHalf"]["successRate"]
    if first is None or second is None:
        return None
    delta = second - first
    if abs(delta) < HALF_SPLIT_NOTABLE_THRESHOLD:
        return None
    sample_size = min(half_split_mi["firstHalf"]["eligiblePlays"], half_split_mi["secondHalf"]["eligiblePlays"])
    direction = "better" if delta > 0 else "worse"
    headline = f"Michigan's offense got {direction} after halftime"
    why = "This is an observation, not a diagnosis -- the numbers show a swing between halves, not what caused it."
    angle = f"First half: {_pct(first)} success rate. Second half: {_pct(second)}. Worth checking film for what actually changed."
    evidence = [
        f"First-half success rate: {_pct(first)} ({half_split_mi['firstHalf']['eligiblePlays']} plays)",
        f"Second-half success rate: {_pct(second)} ({half_split_mi['secondHalf']['eligiblePlays']} plays)",
        f"Swing: {_pp(delta)} points",
    ]
    return Candidate(
        topic="half_split", side="offense", metric="successRate",
        headline=headline, evidence=evidence,
        context={"gameValue": second, "opponentBaseline": first, "opponentGamesUsed": None, "nationallyRanked": False},
        why_it_matters=why, video_angle=angle,
        signal_class=classify_signal("successRate", "successEligiblePlays", sample_size),
        delta=delta, percentile={"percentile": None, "rank": None, "sampleSize": sample_size, "sampleSizeCaveat": None},
        definition_version="half-split-v1",
    )


def _build_topic_candidates(mi_game: dict[str, Any], opponent_slug: str, season: int, game_id: str, half_split_mi: dict[str, Any] | None = None) -> list[Candidate]:
    baseline = opponent_baseline_excluding_game(opponent_slug, season, game_id)
    candidates: list[Candidate] = []

    def pct_for(metric_allowed: str, game_value: float | None) -> dict[str, Any]:
        if game_value is None:
            return {"percentile": None, "rank": None, "sampleSize": 0, "sampleSizeCaveat": "no value"}
        return percentile_within_opponent_season(opponent_slug, season, metric_allowed, game_value, game_id)

    # --- Efficiency: overall / rush / pass success rate, offense side ---
    best_off_eff = max(
        (("successRate", mi_game.get("successRate")), ("rushSuccessRate", mi_game.get("rushSuccessRate")), ("passSuccessRate", mi_game.get("passSuccessRate"))),
        key=lambda pair: abs(normalized_delta(pair[0], pair[1], baseline["rates"].get(pair[0] + "Allowed")) or 0),
    )
    metric = best_off_eff[0]
    allowed_metric = metric + "Allowed"
    label = {"successRate": "overall", "rushSuccessRate": "rushing", "passSuccessRate": "passing"}[metric]
    delta = normalized_delta(metric, mi_game.get(metric), baseline["rates"].get(allowed_metric))
    pct = pct_for(allowed_metric, mi_game.get(metric))
    if delta is not None and delta > 0.03:
        headline = f"Michigan controlled the {label} down-to-down battle"
        why = f"A higher success rate means Michigan stayed on schedule instead of relying on a few long plays to make up for inconsistency."
    elif delta is not None and delta < -0.03:
        headline = f"Michigan's {label} offense struggled to stay ahead of schedule"
        why = f"A below-normal success rate means Michigan was living in longer, tougher down-and-distance situations than usual."
    else:
        headline = f"Michigan's {label} efficiency was close to normal against {opponent_slug.replace('-', ' ').title()}"
        why = "Neither side had a clear down-to-down efficiency edge."
    angle = f"Michigan's {label} success rate was {_pp(delta)} points {'better' if (delta or 0) >= 0 else 'worse'} than what {opponent_slug.replace('-', ' ').title()} normally allows."
    candidates.append(_story("efficiency", "offense", metric, mi_game, {**baseline, "rates": {metric: baseline["rates"].get(allowed_metric)}, "opponent": opponent_slug, "gamesUsed": baseline["gamesUsed"]}, pct, headline, why, angle))

    # --- Efficiency: defense side (opponent's offense vs their own normal) ---
    opp_own_games = aggregate_rate(
        [g for g in json.loads((DEFAULT_PUBLISHED_ROOT / str(season) / "teams" / opponent_slug / "games.json").read_text()) if str(g.get("gameId")) != str(game_id)],
        "successRate",
    )
    delta_def = normalized_delta("successRateAllowed", mi_game.get("successRateAllowed"), opp_own_games)
    if delta_def is not None:
        pct_def = pct_for("successRate", mi_game.get("successRateAllowed"))
        if delta_def > 0.03:
            headline = f"Michigan's defense held {opponent_slug.replace('-', ' ').title()} below its normal offense"
            why = "Michigan's defense forced a lower success rate than this opponent usually manages."
        elif delta_def < -0.03:
            headline = f"{opponent_slug.replace('-', ' ').title()}'s offense out-performed its own normal success rate"
            why = "Michigan's defense allowed more down-to-down success than this opponent usually generates -- worth a closer look even in a win."
        else:
            headline = f"{opponent_slug.replace('-', ' ').title()}'s offense performed close to its normal level against Michigan"
            why = "No unusual defensive edge either way on down-to-down success."
        angle = f"Michigan's defense allowed a success rate {_pp(delta_def)} points {'better' if delta_def >= 0 else 'worse'} than {opponent_slug.replace('-', ' ').title()}'s own season normal."
        candidates.append(_story("efficiency", "defense", "successRateAllowed", mi_game, {"rates": {"successRateAllowed": opp_own_games}, "opponent": opponent_slug, "gamesUsed": baseline["gamesUsed"]}, pct_def, headline, why, angle))

    # --- Explosiveness ---
    delta_exp = normalized_delta("explosivePlayRate", mi_game.get("explosivePlayRate"), baseline["rates"].get("explosivePlayRateAllowed"))
    if delta_exp is not None:
        pct_exp = pct_for("explosivePlayRateAllowed", mi_game.get("explosivePlayRate"))
        success_delta = normalized_delta("successRate", mi_game.get("successRate"), baseline["rates"].get("successRateAllowed")) or 0
        if delta_exp > 0.03 and success_delta > 0.03:
            headline = "Michigan was efficient AND explosive"
            why = "The offense wasn't living off a few chunk plays -- both down-to-down consistency and big plays were above normal."
        elif delta_exp > 0.03 and success_delta <= 0.03:
            headline = "A few explosive plays may be flattering Michigan's offensive output"
            why = "Explosive-play rate was well above normal while down-to-down success wasn't -- worth checking whether the yardage total overstates how consistent the offense actually was."
        elif delta_exp <= 0.03 and success_delta > 0.03:
            headline = "Michigan won on consistency, not explosive plays"
            why = "The offense stayed ahead of schedule play after play rather than relying on chunk gains."
        else:
            headline = "Michigan's offense was neither especially explosive nor especially consistent"
            why = "Both explosiveness and down-to-down success were close to normal for this opponent."
        angle = f"Explosive-play rate was {_pp(delta_exp)} points vs. what {opponent_slug.replace('-', ' ').title()} normally allows."
        candidates.append(_story("explosiveness", "offense", "explosivePlayRate", mi_game, {**baseline, "rates": {"explosivePlayRate": baseline["rates"].get("explosivePlayRateAllowed")}, "opponent": opponent_slug, "gamesUsed": baseline["gamesUsed"]}, pct_exp, headline, why, angle))

    # --- Situational: standard-down / passing-down ---
    delta_std = normalized_delta("standardDownSuccessRate", mi_game.get("standardDownSuccessRate"), baseline["rates"].get("standardDownSuccessRateAllowed"))
    if delta_std is not None and abs(delta_std) > 0.02:
        pct_std = pct_for("standardDownSuccessRateAllowed", mi_game.get("standardDownSuccessRate"))
        if delta_std > 0:
            headline = "Michigan rarely put itself in obvious passing situations"
            why = "Staying ahead on standard downs means the offense avoided the long-yardage snaps where a pass rush can pin its ears back."
        else:
            headline = "Michigan repeatedly fell behind the chains on standard downs"
            why = "Falling behind schedule on standard downs pushes an offense into predictable, difficult passing-down situations."
        angle = f"Standard-down success rate was {_pp(delta_std)} points vs. {opponent_slug.replace('-', ' ').title()}'s normal."
        candidates.append(_story("situational", "offense", "standardDownSuccessRate", mi_game, {**baseline, "rates": {"standardDownSuccessRate": baseline["rates"].get("standardDownSuccessRateAllowed")}, "opponent": opponent_slug, "gamesUsed": baseline["gamesUsed"]}, pct_std, headline, why, angle))

    # --- Drive quality / finishing drives ---
    delta_fin = normalized_delta("pointsPerOpportunity", mi_game.get("pointsPerOpportunity"), baseline["rates"].get("pointsPerOpportunityAllowed"))
    if delta_fin is not None:
        pct_fin = pct_for("pointsPerOpportunityAllowed", mi_game.get("pointsPerOpportunity"))
        if delta_fin > 0.3:
            headline = "Michigan finished drives at an elite rate"
            why = "Points per scoring opportunity measures whether a team cashes in once it crosses the 40 -- a high rate means few wasted trips."
        elif delta_fin < -0.3:
            headline = "Michigan moved the ball but left points on the field"
            why = "A below-normal points-per-opportunity rate means promising drives too often ended short of a touchdown."
        else:
            headline = "Michigan's drive-finishing was close to normal"
            why = "Points per scoring opportunity was in line with what this opponent usually allows."
        angle = f"Points per scoring opportunity: {mi_game.get('pointsPerOpportunity'):.2f} vs. {opponent_slug.replace('-', ' ').title()}'s normal {baseline['rates'].get('pointsPerOpportunityAllowed'):.2f}." if mi_game.get("pointsPerOpportunity") is not None and baseline["rates"].get("pointsPerOpportunityAllowed") is not None else "Finishing-drives context unavailable."
        candidates.append(_story("drive_quality", "offense", "pointsPerOpportunity", mi_game, {**baseline, "rates": {"pointsPerOpportunity": baseline["rates"].get("pointsPerOpportunityAllowed")}, "opponent": opponent_slug, "gamesUsed": baseline["gamesUsed"]}, pct_fin, headline, why, angle))

    # --- Field position ---
    delta_fp = normalized_delta("averageStartYardsToGoal", mi_game.get("averageStartYardsToGoal"), baseline["rates"].get("averageStartYardsToGoalAllowed"))
    if delta_fp is not None and abs(delta_fp) > 3:
        pct_fp = pct_for("averageStartYardsToGoalAllowed", mi_game.get("averageStartYardsToGoal"))
        if delta_fp > 0:
            headline = f"{opponent_slug.replace('-', ' ').title()} gave Michigan short fields all game"
            why = "Starting closer to the opponent's end zone shortens the distance needed to score, independent of how well the offense actually played."
        else:
            headline = "Michigan earned its yardage the hard way -- field position didn't help"
            why = "Michigan started further from the end zone than this opponent normally allows, meaning any scoring came without a field-position boost."
        angle = f"Average start: Michigan's own {100 - mi_game.get('averageStartYardsToGoal'):.0f}-yard line vs. {opponent_slug.replace('-', ' ').title()}'s normal {100 - baseline['rates'].get('averageStartYardsToGoalAllowed'):.0f}." if mi_game.get("averageStartYardsToGoal") is not None and baseline["rates"].get("averageStartYardsToGoalAllowed") is not None else "Field position context unavailable."
        candidates.append(_story("field_position", "offense", "averageStartYardsToGoal", mi_game, {**baseline, "rates": {"averageStartYardsToGoal": baseline["rates"].get("averageStartYardsToGoalAllowed")}, "opponent": opponent_slug, "gamesUsed": baseline["gamesUsed"]}, pct_fp, headline, why, angle))

    # --- Havoc ---
    delta_hv = normalized_delta("havocRate", mi_game.get("havocRate"), baseline["rates"].get("havocRateAllowed"))
    if delta_hv is not None:
        pct_hv = pct_for("havocRateAllowed", mi_game.get("havocRate"))
        rate = mi_game.get("havocRate")
        one_of = round(1 / rate) if rate else None
        if delta_hv > 0.02:
            headline = f"Michigan's defense blew up about 1 of every {one_of} plays" if one_of else "Michigan's defense created more disruption than usual"
            why = "Havoc rate (TFLs, sacks, and takeaways combined) captures negative or drive-changing plays a simple tackle count misses."
        elif delta_hv < -0.02:
            headline = "Michigan's defense generated less disruption than usual"
            why = "A below-normal havoc rate means fewer negative or drive-changing defensive plays than this opponent usually faces."
        else:
            headline = "Michigan's defensive disruption was close to normal"
            why = "Havoc rate was in line with what this opponent usually faces."
        angle = f"Havoc rate: {_pct(rate)} vs. {opponent_slug.replace('-', ' ').title()}'s normal {_pct(baseline['rates'].get('havocRateAllowed'))}."
        candidates.append(_story("havoc", "defense", "havocRate", mi_game, {**baseline, "rates": {"havocRate": baseline["rates"].get("havocRateAllowed")}, "opponent": opponent_slug, "gamesUsed": baseline["gamesUsed"]}, pct_hv, headline, why, angle))

    half_split_candidate = _half_split_candidate(half_split_mi)
    if half_split_candidate is not None:
        candidates.append(half_split_candidate)

    return candidates


def build_game_stories(mi_game: dict[str, Any], opponent_slug: str, season: int, game_id: str, half_split_mi: dict[str, Any] | None = None) -> dict[str, Any]:
    """The full ranked story set for one Michigan game."""
    candidates = _build_topic_candidates(mi_game, opponent_slug, season, game_id, half_split_mi)
    ranked = sorted(candidates, key=lambda c: c.score(), reverse=True)

    selected: list[Candidate] = []
    seen_topics: set[str] = set()
    for c in ranked:
        if c.topic in seen_topics:
            continue
        selected.append(c)
        seen_topics.add(c.topic)
        if len(selected) >= MAX_STORIES:
            break

    # "Good win, hidden problem": guarantee at least one concern-tagged story
    # is included if one exists, even if the game was a blowout win and the
    # magnitude ranking would have otherwise crowded it out.
    if not any(c.polarity() == "concern" for c in selected):
        concern = next((c for c in ranked if c.polarity() == "concern" and c not in selected), None)
        if concern is not None:
            if len(selected) >= MAX_STORIES:
                selected[-1] = concern
            else:
                selected.append(concern)

    while len(selected) < MIN_STORIES and len(selected) < len(ranked):
        for c in ranked:
            if c not in selected:
                selected.append(c)
                break

    return {
        "gameId": str(game_id),
        "season": season,
        "opponent": opponent_slug,
        "definitionVersion": STORY_VERSION,
        "stories": [
            {
                "id": f"{c.topic}-{c.side}-{c.metric}",
                "topic": c.topic,
                "side": c.side,
                "metric": c.metric,
                "headline": c.headline,
                "evidence": c.evidence,
                "context": c.context,
                "whyItMatters": c.why_it_matters,
                "videoAngle": c.video_angle,
                "signalClass": c.signal_class,
                "polarity": c.polarity(),
                "delta": c.delta,
                "percentile": c.percentile,
                "metricStatus": c.metric_status,
                "definitionVersion": c.definition_version,
            }
            for c in selected
        ],
    }
