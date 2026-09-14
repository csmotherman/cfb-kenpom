"""Live opponent-adjusted rating model behind published AdjOff/AdjDef/AdjNet.

The publication model is current-season-only and intentionally flat:

    EPA/play = national mean + offense(team) - defense(opponent) + error

Every completed FBS-vs-FBS team-game is fit simultaneously from
current-season, garbage-time-filtered EPA. There is no prior-season team
strength, preseason prior, recruiting input, conference-strength term, z-score
normalization, or home-field coefficient.

Separating offense and defense doubles the number of team parameters compared
with ordinary SRS. Early in a season the FBS-vs-FBS schedule graph does not yet
contain enough independent matchups to identify all of those parameters by pure
least squares. A small zero-centered ridge penalty therefore stabilizes the
solve. It imports no external team-strength information: it only pulls weakly
identified offense/defense effects toward the current-season FBS average, and
its influence naturally fades as each team accumulates more EPA plays.

The historical ``hierarchical_hfa`` CLI mode name is retained only as a build
compatibility route because ``build_real_data.py`` already uses that branch to
materialize the garbage-time-filtered input population. Published metadata
identifies the actual methodology as ``flat_epa``.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from typing import Any

from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings
from cfb_analytics.derived.games import GARBAGE_TIME_VERSION

MODEL_MODES = ("hierarchical_hfa", "legacy")

RATING_MODEL_ID = "adj-rating-flat-epa-v2"
LEGACY_RATING_MODEL_ID = "adj-rating-legacy-srs-ypp-v1"
MODEL_VERSION = "flat-epa-current-season-ridge-v2"

# Roughly one game's worth of EPA opportunities. This is not prior-season
# information; it is a zero-effect penalty used only to make the current-season
# offense/defense decomposition identifiable and stable while the graph is sparse.
RIDGE_EQUIVALENT_PLAYS = 50.0
LAMBDA_TEAM = RIDGE_EQUIVALENT_PLAYS
LAMBDA_CONFERENCE = 0.0
HFA_ENABLED = False

SEASON_SCOPE = "current-season-only"
USES_PRIOR_SEASON_TEAM_STRENGTH = False
USES_PRESEASON_TEAM_PRIOR = False
USES_CONFERENCE_STRENGTH = False

RATING_INPUT_VERSION = "canonical-production-garbage-filtered-v1"
RATING_SCALE = 100.0  # EPA/play effect -> EPA per 100 plays.
EPA_SPEC = ("EPA", "epaSum", "epaPlays")

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

    Conference fields are intentionally not required or consumed. If present,
    they are copied for audit/debugging only and never enter the fit.
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


def _validated_model_rows(rows: list[dict[str, Any]], season: int):
    """Validate the current-season FBS graph and return EPA-only solver rows."""
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

        epa_sum = row.get("epaSum")
        epa_plays = row.get("epaPlays")
        if not _finite(epa_sum) or not _finite(epa_plays):
            raise RatingModelError(f"Non-finite EPA input for {game_id} / {team}")
        if float(epa_plays) < 0:
            raise RatingModelError(f"Negative EPA play count for {game_id} / {team}")

        # Deliberately strip conference/site fields before the numerical solve.
        model_rows.append(
            {
                "team": team,
                "opponent": opponent,
                "epaSum": float(epa_sum),
                "epaPlays": float(epa_plays),
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

    if not any(row["epaPlays"] > 0 for row in model_rows):
        raise RatingModelError("No eligible EPA observations for publication ratings")
    return model_rows


def _schedule_components(model_rows: list[dict[str, Any]]) -> int:
    adjacency: dict[str, set[str]] = defaultdict(set)
    teams: set[str] = set()
    for row in model_rows:
        if row["epaPlays"] <= 0:
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


def _fit_flat_epa(
    rows: list[dict[str, Any]],
    *,
    season: int,
    cutoff: Any,
    input_version: str,
    ridge_equivalent_plays: float,
):
    model_rows = _validated_model_rows(rows, season)

    fit = fit_metric_ratings(
        model_rows,
        EPA_SPEC,
        shrinkage=ridge_equivalent_plays,
        damping=1.0,
        tolerance=1e-9,
        max_iterations=10000,
    )
    if not fit.get("converged"):
        raise RatingModelError(
            f"Flat EPA solver did not converge at cutoff {cutoff}; "
            f"max delta {fit.get('maxDelta')}"
        )

    offense = fit.get("offense", {})
    defense = fit.get("defense", {})
    teams = sorted(set(offense) & set(defense))
    if not teams:
        raise RatingModelError("Flat EPA solver returned no rated teams")
    if set(offense) != set(defense):
        raise RatingModelError("Flat EPA offense and defense universes differ")

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
        weight = float(row["epaPlays"])
        if weight <= 0:
            continue
        value = float(row["epaSum"]) / weight
        prediction = league_mean + float(offense[row["team"]]) - float(defense[row["opponent"]])
        weighted_sse += weight * (value - prediction) ** 2
        total_weight += weight
        observations += 1
        source_rows.append(
            {
                "team": row["team"],
                "opponent": row["opponent"],
                "value": value,
                "weight": weight,
            }
        )
    weighted_rmse = math.sqrt(weighted_sse / total_weight)

    identity = {
        "modelVersion": MODEL_VERSION,
        "season": season,
        "cutoff": cutoff,
        "inputVersion": input_version,
        "scale": RATING_SCALE,
        "ridgeEquivalentPlays": ridge_equivalent_plays,
        "usesConferenceStrength": False,
        "usesPriorSeasonTeamStrength": False,
        "usesPreseasonTeamPrior": False,
        "hfaEnabled": False,
        "rows": sorted(source_rows, key=lambda row: (row["team"], row["opponent"], row["value"])),
    }
    model_key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()

    wrapped_fit = {
        **fit,
        "observations": observations,
        "teams": len(teams),
        "scheduleComponents": _schedule_components(model_rows),
        "parameterCount": 2 * len(teams),
        "ridgeEquivalentPlays": ridge_equivalent_plays,
        "leagueMeanEpaPerPlay": league_mean,
        "weightedRmseEpaPerPlay": weighted_rmse,
        "modelMetadata": {"modelKey": model_key},
    }
    return {"fits": {"EPA": wrapped_fit}, "ratings": ratings}


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
    """Fit current-season flat opponent-adjusted EPA offense and defense.

    ``lambda_team`` is a zero-centered within-season stability penalty measured
    in equivalent EPA plays. It does not contain any historical/team-strength
    data. Conference strength and HFA remain forbidden.
    """
    if not rows:
        raise RatingModelError("Refusing to fit publication ratings from an empty rating graph")
    if not _finite(lambda_team) or float(lambda_team) != RIDGE_EQUIVALENT_PLAYS:
        raise RatingModelError(
            f"Flat EPA publication ratings require the frozen current-season "
            f"ridge of {RIDGE_EQUIVALENT_PLAYS:g} equivalent plays"
        )
    if lambda_conf not in (None, 0, 0.0):
        raise RatingModelError("Flat EPA publication ratings do not use conference strength")
    if hfa_enabled not in (False, None):
        raise RatingModelError("Flat EPA publication ratings do not use an HFA coefficient")

    result = _fit_flat_epa(
        rows,
        season=season,
        cutoff=cutoff,
        input_version=input_version,
        ridge_equivalent_plays=float(lambda_team),
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
        "opponentAdjustment": "simultaneous flat current-season offense-defense solve",
        "stabilization": "zero-centered ridge to current-season FBS average",
        "ridgeEquivalentPlays": RIDGE_EQUIVALENT_PLAYS,
        "externalTeamStrengthInputsUsed": False,
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
            meta["scheduleComponents"] = epa_fit["scheduleComponents"]
            meta["parameterCount"] = epa_fit["parameterCount"]
            meta["leagueMeanEpaPerPlay"] = epa_fit["leagueMeanEpaPerPlay"]
            meta["weightedRmseEpaPerPlay"] = epa_fit["weightedRmseEpaPerPlay"]
            meta["modelKey"] = epa_fit["modelMetadata"]["modelKey"]
    return meta
