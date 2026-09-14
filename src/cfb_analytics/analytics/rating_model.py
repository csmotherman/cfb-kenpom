"""Live opponent-adjusted possession-efficiency model for AdjOff/AdjDef/AdjNet.

LEILA now treats a possession as the fundamental unit of football efficiency:

    points / resolved possession
        = national mean + offense(team) - defense(opponent) + error

Every completed FBS-vs-FBS team-game from the current season is solved
simultaneously. The resulting offense and defense effects therefore recurse
through the entire schedule graph, in the same spirit that SRS recursively
adjusts scoring margin for opponent strength.

The published rating imports no prior-season strength, preseason prior,
recruiting information, conference-strength term, home-field coefficient, or
z-score normalization. A small zero-centered ridge penalty is retained only to
stabilize separate offense/defense effects while the early-season graph is
sparse. It contains no team-specific information and naturally loses influence
as each team accumulates possessions.

The historical ``hierarchical_hfa`` CLI mode name remains as a compatibility
route for the site build. Published metadata identifies the actual methodology
as ``possession_efficiency``.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from typing import Any

from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings

MODEL_MODES = ("hierarchical_hfa", "legacy")

RATING_MODEL_ID = "adj-rating-possession-v3"
LEGACY_RATING_MODEL_ID = "adj-rating-legacy-srs-ypp-v1"
MODEL_VERSION = "possession-efficiency-current-season-ridge-v3"

# Approximately one game's worth of offensive possessions. This is a neutral,
# zero-effect stabilizer, not an external estimate of any team's strength.
RIDGE_EQUIVALENT_POSSESSIONS = 10.0
LAMBDA_TEAM = RIDGE_EQUIVALENT_POSSESSIONS
LAMBDA_CONFERENCE = 0.0
HFA_ENABLED = False

SEASON_SCOPE = "current-season-only"
USES_PRIOR_SEASON_TEAM_STRENGTH = False
USES_PRESEASON_TEAM_PRIOR = False
USES_CONFERENCE_STRENGTH = False

RATING_INPUT_VERSION = "canonical-possession-team-game-v1"
RATING_SCALE = 10.0  # effect in points/drive -> points per 10 resolved possessions.
POSSESSION_SPEC = (
    "PossessionPoints",
    "possessionPoints",
    "resolvedPointPossessions",
)

# These play-level fields remain on the composite-input row for compatibility
# with the existing site-build route and its audit trail. They are not inputs to
# the possession rating itself.
COMPOSITE_FIELDS = (
    "epaSum",
    "epaPlays",
    "successfulPlays",
    "successEligiblePlays",
    "successfulPlayYards",
)
POSSESSION_FIELDS = (
    "possessionPoints",
    "resolvedPointPossessions",
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
    """Build one current-season possession-rating observation.

    Possession scoring comes from the locked canonical team-game/drive
    contract. Conference fields, when present, are copied only for audit/debug
    visibility and never enter the numerical fit.
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

    for field in POSSESSION_FIELDS:
        if field not in row or row.get(field) is None:
            raise RatingModelError(
                f"Possession rating field {field!r} is missing for {row['team']}"
            )
        out[field] = row[field]

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


def _validated_model_rows(rows: list[dict[str, Any]], season: int):
    """Validate the current-season closed FBS graph and return possession rows."""
    seen: set[tuple[str, str]] = set()
    games: dict[str, list[tuple[str, str]]] = defaultdict(list)
    model_rows: list[dict[str, Any]] = []

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
        games[game_id].append((team, opponent))

        points = row.get("possessionPoints")
        possessions = row.get("resolvedPointPossessions")
        if not _finite(points) or not _finite(possessions):
            raise RatingModelError(
                f"Non-finite possession input for {game_id} / {team}"
            )
        if float(points) < 0:
            raise RatingModelError(
                f"Negative possession points for {game_id} / {team}"
            )
        if float(possessions) < 0:
            raise RatingModelError(
                f"Negative resolved possession count for {game_id} / {team}"
            )

        # Deliberately strip conference/site fields before the numerical solve.
        model_rows.append(
            {
                "team": team,
                "opponent": opponent,
                "possessionPoints": float(points),
                "resolvedPointPossessions": float(possessions),
            }
        )

    if not model_rows:
        raise RatingModelError("No rating observations were supplied")

    for game_id, pair in games.items():
        if len(pair) != 2:
            raise RatingModelError(f"Game {game_id} must have exactly two team rows")
        (team_a, opp_a), (team_b, opp_b) = pair
        if team_a != opp_b or team_b != opp_a:
            raise RatingModelError(f"Game {game_id} has conflicting opponents")

    if not any(row["resolvedPointPossessions"] > 0 for row in model_rows):
        raise RatingModelError("No resolved possession observations for publication ratings")
    return model_rows


def _schedule_components(model_rows: list[dict[str, Any]]) -> int:
    adjacency: dict[str, set[str]] = defaultdict(set)
    teams: set[str] = set()
    for row in model_rows:
        if row["resolvedPointPossessions"] <= 0:
            continue
        team, opponent = row["team"], row["opponent"]
        teams.update((team, opponent))
        adjacency[team].add(opponent)
        adjacency[opponent].add(team)

    remaining = set(teams)
    count = 0
    while remaining:
        count += 1
        root = remaining.pop()
        queue = deque([root])
        while queue:
            team = queue.popleft()
            for opponent in adjacency.get(team, ()):
                if opponent in remaining:
                    remaining.remove(opponent)
                    queue.append(opponent)
    return count


def _fit_possession_efficiency(
    rows: list[dict[str, Any]],
    *,
    season: int,
    cutoff: Any,
    input_version: str,
    ridge_equivalent_possessions: float,
):
    model_rows = _validated_model_rows(rows, season)

    fit = fit_metric_ratings(
        model_rows,
        POSSESSION_SPEC,
        shrinkage=ridge_equivalent_possessions,
        damping=1.0,
        tolerance=1e-9,
        max_iterations=10000,
    )
    if not fit.get("converged"):
        raise RatingModelError(
            f"Possession-efficiency solver did not converge at cutoff {cutoff}; "
            f"max delta {fit.get('maxDelta')}"
        )

    offense = fit.get("offense", {})
    defense = fit.get("defense", {})
    teams = sorted(set(offense) & set(defense))
    if not teams:
        raise RatingModelError("Possession-efficiency solver returned no rated teams")
    if set(offense) != set(defense):
        raise RatingModelError("Possession offense and defense universes differ")

    ratings = {
        "AdjOff": {team: RATING_SCALE * float(offense[team]) for team in teams},
        "AdjDef": {team: RATING_SCALE * float(defense[team]) for team in teams},
    }
    ratings["AdjNet"] = {
        team: ratings["AdjOff"][team] + ratings["AdjDef"][team] for team in teams
    }

    league_mean = float(fit["leagueMean"])
    weighted_sse = 0.0
    total_weight = 0.0
    observations = 0
    source_rows = []
    for row in model_rows:
        weight = float(row["resolvedPointPossessions"])
        if weight <= 0:
            continue
        value = float(row["possessionPoints"]) / weight
        prediction = (
            league_mean
            + float(offense[row["team"]])
            - float(defense[row["opponent"]])
        )
        weighted_sse += weight * (value - prediction) ** 2
        total_weight += weight
        observations += 1
        source_rows.append(
            {
                "team": row["team"],
                "opponent": row["opponent"],
                "pointsPerResolvedPossession": value,
                "resolvedPossessions": weight,
            }
        )
    weighted_rmse = math.sqrt(weighted_sse / total_weight)

    identity = {
        "modelVersion": MODEL_VERSION,
        "season": season,
        "cutoff": cutoff,
        "inputVersion": input_version,
        "scale": RATING_SCALE,
        "ridgeEquivalentPossessions": ridge_equivalent_possessions,
        "usesConferenceStrength": False,
        "usesPriorSeasonTeamStrength": False,
        "usesPreseasonTeamPrior": False,
        "hfaEnabled": False,
        "rows": sorted(
            source_rows,
            key=lambda row: (
                row["team"],
                row["opponent"],
                row["pointsPerResolvedPossession"],
            ),
        ),
    }
    model_key = hashlib.sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()

    wrapped_fit = {
        **fit,
        "observations": observations,
        "teams": len(teams),
        "scheduleComponents": _schedule_components(model_rows),
        "parameterCount": 2 * len(teams),
        "ridgeEquivalentPossessions": ridge_equivalent_possessions,
        "leagueMeanPointsPerPossession": league_mean,
        "weightedRmsePointsPerPossession": weighted_rmse,
        "modelMetadata": {"modelKey": model_key},
    }
    return {"fits": {"PossessionPoints": wrapped_fit}, "ratings": ratings}


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
    """Fit current-season recursive possession offense and defense."""
    if not rows:
        raise RatingModelError(
            "Refusing to fit publication ratings from an empty rating graph"
        )
    if not _finite(lambda_team) or float(lambda_team) != RIDGE_EQUIVALENT_POSSESSIONS:
        raise RatingModelError(
            "Possession publication ratings require the frozen current-season "
            f"ridge of {RIDGE_EQUIVALENT_POSSESSIONS:g} equivalent possessions"
        )
    if lambda_conf not in (None, 0, 0.0):
        raise RatingModelError(
            "Possession publication ratings do not use conference strength"
        )
    if hfa_enabled not in (False, None):
        raise RatingModelError(
            "Possession publication ratings do not use an HFA coefficient"
        )

    result = _fit_possession_efficiency(
        rows,
        season=season,
        cutoff=cutoff,
        input_version=input_version,
        ridge_equivalent_possessions=float(lambda_team),
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
        "modelMode": "possession_efficiency",
        "compatibilityBuildRoute": "hierarchical_hfa",
        "modelVersion": MODEL_VERSION,
        "netDefinition": "AdjNet = AdjOff + AdjDef",
        "offenseDefinition": (
            "10 * opponent-adjusted points/resolved-possession offense effect"
        ),
        "defenseDefinition": (
            "10 * opponent-adjusted points/resolved-possession defense effect "
            "(higher is better)"
        ),
        "ratingScale": "points per 10 resolved possessions above/below average FBS",
        "metric": "points/resolved possession",
        "opponentAdjustment": (
            "simultaneous recursive current-season offense-defense solve"
        ),
        "stabilization": "zero-centered ridge to current-season FBS average",
        "ridgeEquivalentPossessions": RIDGE_EQUIVALENT_POSSESSIONS,
        "externalTeamStrengthInputsUsed": False,
        "conferenceStrengthUsed": False,
        "hfaEnabled": False,
        "hfaInPublishedRatings": False,
        "seasonScope": SEASON_SCOPE,
        "usesPriorSeasonTeamStrength": USES_PRIOR_SEASON_TEAM_STRENGTH,
        "usesPreseasonTeamPrior": USES_PRESEASON_TEAM_PRIOR,
        # Drive scoring uses complete validated possessions; unlike the former
        # EPA/play input it is not a garbage-time-filtered play statistic.
        "garbageTimeExcluded": False,
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
        possession_fit = fits.get("PossessionPoints")
        if possession_fit:
            meta["iterations"] = possession_fit["iterations"]
            meta["observations"] = possession_fit["observations"]
            meta["scheduleComponents"] = possession_fit["scheduleComponents"]
            meta["parameterCount"] = possession_fit["parameterCount"]
            meta["leagueMeanPointsPerPossession"] = possession_fit[
                "leagueMeanPointsPerPossession"
            ]
            meta["weightedRmsePointsPerPossession"] = possession_fit[
                "weightedRmsePointsPerPossession"
            ]
            meta["modelKey"] = possession_fit["modelMetadata"]["modelKey"]
    return meta
