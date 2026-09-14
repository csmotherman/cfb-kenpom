"""Live opponent-adjusted rating model behind published AdjOff/AdjDef/AdjNet.

The publication model is intentionally simple and current-season-only:

    EPA/play = national mean + offense(team) - defense(opponent) + error

It is the efficiency analogue of SRS. Every completed FBS-vs-FBS team-game is
fit simultaneously from garbage-time-filtered current-season EPA. There is no
prior-season team strength, no preseason prior, no conference-strength term, no
team/conference ridge shrinkage, no z-score re-expansion, and no home-field
coefficient in the published fit.

The historical ``hierarchical_hfa`` CLI mode name is retained only as a build
compatibility route because ``build_real_data.py`` already uses that branch to
materialize the garbage-time-filtered input population. The emitted metadata
identifies the actual methodology as ``flat_epa``.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from typing import Any

from cfb_analytics.derived.games import GARBAGE_TIME_VERSION

MODEL_MODES = ("hierarchical_hfa", "legacy")

RATING_MODEL_ID = "adj-rating-flat-epa-v1"
LEGACY_RATING_MODEL_ID = "adj-rating-legacy-srs-ypp-v1"
MODEL_VERSION = "flat-epa-srs-style-v1"

# Compatibility constants: the new publication model deliberately uses none of
# these terms. Keeping the names prevents accidental import breakage elsewhere.
LAMBDA_TEAM = 0.0
LAMBDA_CONFERENCE = 0.0
HFA_ENABLED = False

SEASON_SCOPE = "current-season-only"
USES_PRIOR_SEASON_TEAM_STRENGTH = False
USES_PRESEASON_TEAM_PRIOR = False
USES_CONFERENCE_STRENGTH = False

RATING_INPUT_VERSION = "canonical-production-garbage-filtered-v1"
RATING_SCALE = 100.0  # EPA/play effect -> EPA per 100 plays.

# build_real_data already asks the canonical derived layer for these fields.
# The publication rating itself consumes EPA only; the remaining fields stay in
# the input contract so this build route remains backward-compatible.
COMPOSITE_FIELDS = (
    "epaSum",
    "epaPlays",
    "successfulPlays",
    "successEligiblePlays",
    "successfulPlayYards",
)

_REQUIRED_ROW_FIELDS = (
    "season",
    "gameId",
    "team",
    "opponent",
    "classification",
    "opponent_classification",
    "neutral_site",
    "home_away",
)


class RatingModelError(RuntimeError):
    """A rating fit that must never reach publication."""


def require_mode(model_mode):
    if model_mode not in MODEL_MODES:
        raise RatingModelError(
            f"Unknown rating model mode: {model_mode!r}; choose one of {MODEL_MODES}"
        )
    return model_mode


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def composite_input_row(row, metric_fields):
    """One rating-model observation with garbage-time-filtered metric counts.

    Conference fields are intentionally not required or consumed. If they are
    present they are copied for audit/debugging only.
    """
    missing = [field for field in _REQUIRED_ROW_FIELDS if row.get(field) is None]
    if missing:
        raise RatingModelError(
            f"Rating input row is missing required identity fields: {missing}"
        )

    out = {field: row[field] for field in _REQUIRED_ROW_FIELDS}
    for optional in ("conference", "opponent_conference"):
        if row.get(optional) is not None:
            out[optional] = row[optional]

    if metric_fields is None:
        out.update({field: 0 for field in COMPOSITE_FIELDS})
        out["garbageTimeMetricsMissing"] = True
    else:
        for field in COMPOSITE_FIELDS:
            if field not in metric_fields:
                raise RatingModelError(
                    f"Filtered metric field {field!r} is missing for {row['team']}"
                )
            out[field] = metric_fields[field]
    return out


def _eligible_epa_rows(rows: list[dict[str, Any]], season: int):
    seen: set[tuple[str, str]] = set()
    eligible: list[tuple[str, str, float, float, str]] = []

    for row in rows:
        if row.get("season") != season:
            raise RatingModelError(
                f"Publication ratings are {SEASON_SCOPE}: expected season {season}, "
                f"found {row.get('season')!r}"
            )
        if str(row.get("classification", "")).lower() != "fbs":
            raise RatingModelError("Publication rating input contains a non-FBS team row")
        if str(row.get("opponent_classification", "")).lower() != "fbs":
            raise RatingModelError("Publication rating input contains a non-FBS opponent")

        team = str(row.get("team") or "")
        opponent = str(row.get("opponent") or "")
        game_id = str(row.get("gameId") or "")
        if not team or not opponent or team == opponent or not game_id:
            raise RatingModelError("Publication rating input has invalid team/game identity")

        key = (game_id, team)
        if key in seen:
            raise RatingModelError(f"Duplicate team-game rating row: {game_id} / {team}")
        seen.add(key)

        epa_sum = row.get("epaSum")
        epa_plays = row.get("epaPlays")
        if not _finite(epa_sum) or not _finite(epa_plays):
            raise RatingModelError(f"Non-finite EPA input for {game_id} / {team}")
        weight = float(epa_plays)
        if weight <= 0:
            continue
        eligible.append((team, opponent, float(epa_sum) / weight, weight, game_id))

    if not eligible:
        raise RatingModelError("No eligible EPA observations for publication ratings")
    return eligible


def _factor_components(
    teams: list[str],
    observations: list[tuple[str, str, float, float, str]],
):
    """Connected components of the offense-vs-defense factor graph.

    Each observation joins O(team) to D(opponent). A disconnected factor
    component has its own additive gauge; centering each component independently
    is the same minimum-information convention SRS uses for disconnected
    schedule components.
    """
    nodes = [("O", team) for team in teams] + [("D", team) for team in teams]
    adjacency: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for team, opponent, *_ in observations:
        left, right = ("O", team), ("D", opponent)
        adjacency[left].add(right)
        adjacency[right].add(left)

    remaining = set(nodes)
    components: list[list[tuple[str, str]]] = []
    while remaining:
        root = min(remaining)
        remaining.remove(root)
        component = [root]
        queue = deque([root])
        while queue:
            node = queue.popleft()
            for neighbor in adjacency.get(node, ()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.append(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def _fit_flat_epa(
    rows: list[dict[str, Any]],
    *,
    season: int,
    cutoff: Any,
    input_version: str,
    tolerance: float = 1e-10,
    max_iterations: int = 10000,
):
    observations = _eligible_epa_rows(rows, season)
    teams = sorted(
        {team for team, _, _, _, _ in observations}
        | {opponent for _, opponent, _, _, _ in observations}
    )

    total_weight = sum(weight for _, _, _, weight, _ in observations)
    national_mean = (
        sum(value * weight for _, _, value, weight, _ in observations) / total_weight
    )

    by_offense: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    by_defense: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for team, opponent, value, weight, _ in observations:
        by_offense[team].append((opponent, value, weight))
        by_defense[opponent].append((team, value, weight))

    offense = {team: 0.0 for team in teams}
    defense = {team: 0.0 for team in teams}
    components = _factor_components(teams, observations)

    converged = False
    max_delta = float("inf")
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        previous_offense = dict(offense)
        previous_defense = dict(defense)

        new_offense = dict(offense)
        for team, games in by_offense.items():
            weight = sum(w for _, _, w in games)
            new_offense[team] = (
                sum(
                    w * (value - national_mean + defense[opponent])
                    for opponent, value, w in games
                )
                / weight
            )

        new_defense = dict(defense)
        for team, games in by_defense.items():
            weight = sum(w for _, _, w in games)
            new_defense[team] = (
                sum(
                    w * (national_mean + new_offense[opponent] - value)
                    for opponent, value, w in games
                )
                / weight
            )

        # Fix each independent additive gauge without changing any fitted edge.
        for component in components:
            values = [
                new_offense[team] if side == "O" else new_defense[team]
                for side, team in component
            ]
            shift = sum(values) / len(values)
            for side, team in component:
                if side == "O":
                    new_offense[team] -= shift
                else:
                    new_defense[team] -= shift

        offense, defense = new_offense, new_defense
        max_delta = max(
            max(abs(offense[t] - previous_offense[t]) for t in teams),
            max(abs(defense[t] - previous_defense[t]) for t in teams),
        )
        if max_delta <= tolerance:
            converged = True
            break

    if not converged:
        raise RatingModelError(
            f"Flat EPA solver did not converge at cutoff {cutoff} after "
            f"{max_iterations} iterations (max delta {max_delta:.3g})"
        )

    # Center offense and defense independently around average FBS while
    # preserving every prediction by moving the intercept accordingly.
    off_mean = sum(offense.values()) / len(offense)
    def_mean = sum(defense.values()) / len(defense)
    offense = {team: value - off_mean for team, value in offense.items()}
    defense = {team: value - def_mean for team, value in defense.items()}
    fitted_mean = national_mean + off_mean - def_mean

    weighted_sse = 0.0
    for team, opponent, value, weight, _ in observations:
        prediction = fitted_mean + offense[team] - defense[opponent]
        weighted_sse += weight * (value - prediction) ** 2
    weighted_rmse = math.sqrt(weighted_sse / total_weight)

    ratings = {
        "AdjOff": {team: RATING_SCALE * offense[team] for team in teams},
        "AdjDef": {team: RATING_SCALE * defense[team] for team in teams},
    }
    ratings["AdjNet"] = {
        team: ratings["AdjOff"][team] + ratings["AdjDef"][team] for team in teams
    }

    ordered_rows = sorted(
        (
            {
                "team": team,
                "opponent": opponent,
                "value": value,
                "weight": weight,
                "gameId": game_id,
            }
            for team, opponent, value, weight, game_id in observations
        ),
        key=lambda row: (row["gameId"], row["team"]),
    )
    identity = {
        "modelVersion": MODEL_VERSION,
        "season": season,
        "cutoff": cutoff,
        "inputVersion": input_version,
        "scale": RATING_SCALE,
        "usesConferenceStrength": False,
        "usesPriorSeasonTeamStrength": False,
        "usesPreseasonTeamPrior": False,
        "hfaEnabled": False,
        "shrinkage": 0.0,
        "rows": ordered_rows,
    }
    model_key = hashlib.sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()

    fit = {
        "converged": True,
        "iterations": iteration,
        "maxDelta": max_delta,
        "observations": len(observations),
        "teams": len(teams),
        "factorComponents": len(components),
        "leagueMeanEpaPerPlay": fitted_mean,
        "weightedRmseEpaPerPlay": weighted_rmse,
        "offense": offense,
        "defense": defense,
        "hfa": 0.0,
        "hfaAvailable": False,
        "modelMetadata": {"modelKey": model_key},
    }
    return {"fits": {"EPA": fit}, "ratings": ratings}


def fit_publication_composite(
    rows,
    *,
    season,
    cutoff,
    lambda_team=LAMBDA_TEAM,
    lambda_conf=LAMBDA_CONFERENCE,
    hfa_enabled=HFA_ENABLED,
    input_version=RATING_INPUT_VERSION,
):
    """Fit current-season, flat opponent-adjusted EPA offense and defense.

    The legacy keyword arguments remain in the signature only so existing build
    callers cannot break silently. Any attempt to re-introduce shrinkage,
    conference strength, or HFA is rejected.
    """
    if not rows:
        raise RatingModelError(
            "Refusing to fit publication ratings from an empty rating graph"
        )
    if lambda_team not in (None, 0, 0.0):
        raise RatingModelError("Flat EPA publication ratings do not use team shrinkage")
    if lambda_conf not in (None, 0, 0.0):
        raise RatingModelError("Flat EPA publication ratings do not use conference strength")
    if hfa_enabled not in (False, None):
        raise RatingModelError("Flat EPA publication ratings do not use an HFA coefficient")

    result = _fit_flat_epa(
        rows,
        season=season,
        cutoff=cutoff,
        input_version=input_version,
    )
    ratings = result["ratings"]
    teams = set(ratings["AdjNet"])
    for label in ("AdjOff", "AdjDef"):
        if set(ratings[label]) != teams:
            raise RatingModelError("Rating sides cover different team universes")
    for team in teams:
        if abs(
            ratings["AdjNet"][team]
            - (ratings["AdjOff"][team] + ratings["AdjDef"][team])
        ) > 1e-9:
            raise RatingModelError(f"AdjNet is not AdjOff + AdjDef for {team}")
    return result


def rating_model_metadata(
    model_mode,
    *,
    season,
    cutoff,
    weeks=None,
    fits=None,
    rows_with_no_canonical_plays=0,
    teams=None,
):
    """Explicit, self-describing identity for a generated rating snapshot."""
    require_mode(model_mode)
    if model_mode == "legacy":
        return {
            "modelId": LEGACY_RATING_MODEL_ID,
            "modelMode": "legacy",
            "modelVersion": "iterative-ratings-v2-directional",
            "netDefinition": "srs-v2-scoring-margin",
            "offenseDefinition": "YardsPerPlay-edge",
            "defenseDefinition": "YardsPerPlay-edge",
            "garbageTimeExcluded": False,
            "hfaEnabled": False,
            "season": season,
            "cutoff": cutoff,
            "weeksRefit": weeks,
        }

    meta = {
        "modelId": RATING_MODEL_ID,
        "modelMode": "flat_epa",
        "compatibilityBuildRoute": "hierarchical_hfa",
        "modelVersion": MODEL_VERSION,
        "netDefinition": "AdjNet = AdjOff + AdjDef",
        "offenseDefinition": "100 * opponent-adjusted EPA/play offense effect",
        "defenseDefinition": "100 * opponent-adjusted EPA/play defense effect (higher is better)",
        "ratingScale": "EPA per 100 plays above/below average FBS",
        "metric": "EPA/play",
        "opponentAdjustment": "simultaneous flat least-squares-style offense-defense solve",
        "teamShrinkage": 0.0,
        "conferenceStrengthUsed": False,
        "hfaEnabled": False,
        "hfaInPublishedRatings": False,
        "seasonScope": SEASON_SCOPE,
        "usesPriorSeasonTeamStrength": USES_PRIOR_SEASON_TEAM_STRENGTH,
        "usesPreseasonTeamPrior": USES_PRESEASON_TEAM_PRIOR,
        "garbageTimeExcluded": True,
        "garbageTimeDefinitionVersion": GARBAGE_TIME_VERSION,
        "normalization": "none",
        "inputVersion": RATING_INPUT_VERSION,
        "season": season,
        "cutoff": cutoff,
        "weeksRefit": weeks,
        "refitPerSiteWeek": True,
        "rowsWithNoCanonicalPlays": rows_with_no_canonical_plays,
        "teams": teams,
    }
    if fits:
        epa_fit = fits.get("EPA")
        if epa_fit:
            meta["iterations"] = epa_fit["iterations"]
            meta["observations"] = epa_fit["observations"]
            meta["factorComponents"] = epa_fit["factorComponents"]
            meta["leagueMeanEpaPerPlay"] = epa_fit["leagueMeanEpaPerPlay"]
            meta["weightedRmseEpaPerPlay"] = epa_fit["weightedRmseEpaPerPlay"]
            meta["modelKey"] = epa_fit["modelMetadata"]["modelKey"]
    return meta
