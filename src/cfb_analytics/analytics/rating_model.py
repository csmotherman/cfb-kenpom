"""Live opponent-adjusted possession-efficiency model for AdjOff/AdjDef/AdjNet.

APR treats a possession as the fundamental unit of football efficiency. Raw
drive points are first adjusted for the possession's starting field position:

    drive value = actual offensive points - expected points(starting field position)

and then the opponent-adjusted model solves:

    drive value / resolved possession
        = national mean + offense(team) - defense(opponent) + error

Every completed FBS-vs-FBS team-game from the current season is solved
simultaneously. The resulting offense and defense effects therefore recurse
through the entire schedule graph, in the same spirit that SRS recursively
adjusts scoring margin for opponent strength.

The possession points are reconstructed from the repository's validated drive
layer and Finishing Drives touchdown/field-goal adjudication. They are offensive
drive points only, rather than scoreboard points that could include defensive or
special-teams scores. Starting-field expected points are estimated only from the
resolved drives available at the current rating cutoff, preventing later-season
field-position outcomes from leaking backward into earlier snapshots.

The published rating imports no preseason prior, recruiting information,
conference-strength term, home-field coefficient, or z-score normalization. A
small zero-centered ridge penalty is retained only to stabilize separate
offense/defense effects while the early-season graph is sparse. It contains no
team-specific information and naturally loses influence as each team
accumulates possessions.

The one exception, added for weeks 1-3: a team's OWN rating is still fit
purely from its own current-season games, never blended with its own prior
year -- but the OPPONENT-strength term used to adjust for who a team played is
tapered toward that opponent's final rating from the prior season (50% at
site-week <= 2, linearly down to 0% by site-week 4), since with only 1-2 games
played neither team's in-season number is trustworthy yet as a description of
who the opponent actually was. This does not seed any team's own identity with
last year's number; it only stabilizes what "a tough opponent" means before
this season's schedule graph has connected enough to say for itself. See
prior_season_weight() and _refine_with_prior_season_opponents() below.

The historical ``hierarchical_hfa`` CLI mode name remains as a compatibility
route for the site build. Published metadata identifies the actual methodology
as ``possession_efficiency``.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.drive_ppd import (
    DRIVE_PPD_POINTS_FOUNDATION,
    DRIVE_PPD_VERSION,
    adjudicated_drive_points,
    build_team_game_drive_rows,
)
from cfb_analytics.analytics.field_position import valid_start_yards_to_goal
from cfb_analytics.analytics.field_position_adjustment import (
    FIELD_POSITION_EP_VERSION,
    field_position_adjusted_drive_value,
    fit_starting_field_position_ep,
)
from cfb_analytics.analytics.iterative_ratings import _observations, fit_metric_ratings

MODEL_MODES = ("hierarchical_hfa", "legacy")

RATING_MODEL_ID = "adj-rating-possession-field-position-v5"
LEGACY_RATING_MODEL_ID = "adj-rating-legacy-srs-ypp-v1"
MODEL_VERSION = "possession-efficiency-field-position-adjusted-v5"

# Approximately one game's worth of offensive possessions. This is a neutral,
# zero-effect stabilizer, not an external estimate of any team's strength.
RIDGE_EQUIVALENT_POSSESSIONS = 10.0
LAMBDA_TEAM = RIDGE_EQUIVALENT_POSSESSIONS
LAMBDA_CONFERENCE = 0.0
HFA_ENABLED = False

# How much weight the prior season's final opponent rating carries in the
# refinement pass below, by site-week. Walk-forward validated (2021-2026,
# next-week-out): a real, if modest, accuracy/MAE improvement at week 1-2 that
# fades to noise by week 3, so the taper reaches zero by week 4 on purpose --
# past that point this season's own schedule graph is trusted alone, exactly
# as before this feature existed.
PRIOR_SEASON_TAPER_FULL_WEEK = 2
PRIOR_SEASON_TAPER_ZERO_WEEK = 4
PRIOR_SEASON_TAPER_START_WEIGHT = 0.5

SEASON_SCOPE = "current-season-primary-with-tapered-prior-season-opponent-baseline"
USES_PRIOR_SEASON_TEAM_STRENGTH = True
USES_PRESEASON_TEAM_PRIOR = False
USES_CONFERENCE_STRENGTH = False


def prior_season_weight(site_week):
    """0.5 at site_week<=2, linearly down to 0.0 by site_week>=4. See the
    module docstring and PRIOR_SEASON_TAPER_* above for why these specific
    values."""
    if site_week is None:
        return 0.0
    if site_week <= PRIOR_SEASON_TAPER_FULL_WEEK:
        return PRIOR_SEASON_TAPER_START_WEIGHT
    if site_week >= PRIOR_SEASON_TAPER_ZERO_WEEK:
        return 0.0
    span = PRIOR_SEASON_TAPER_ZERO_WEEK - PRIOR_SEASON_TAPER_FULL_WEEK
    remaining = PRIOR_SEASON_TAPER_ZERO_WEEK - site_week
    return PRIOR_SEASON_TAPER_START_WEIGHT * remaining / span

RATING_INPUT_VERSION = "validated-drive-field-position-adjusted-v2"
RATING_SCALE = 10.0  # adjusted points/drive effect -> points per 10 resolved possessions.
POSSESSION_SPEC = (
    "PossessionPoints",
    "fieldPositionAdjustedDriveValue",
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
    "offensiveDrivePoints",
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=8)
def _drive_rating_fields(season: int) -> dict[tuple[str, str], dict[str, Any]]:
    """Materialize authoritative offensive drive points for one season.

    The normal site-build row is the canonical team-game contract, which does
    not carry the research drive-PPD fields. The raw ingredients have already
    been produced earlier in the refresh workflow, so load those validated
    drive and canonical-play partitions once and reuse the locked drive-PPD
    aggregation instead of recreating possession scoring inside this model.
    """
    repo = _repo_root()
    play_paths = sorted(
        (repo / f"data/processed/canonical/season={season}").glob(
            "season_type=*/week=*/plays.json"
        )
    )
    drive_paths = sorted(
        (repo / f"data/processed/derived/drives/season={season}").glob(
            "season_type=*/week=*/drives.json"
        )
    )
    if not play_paths or not drive_paths:
        raise RatingModelError(
            f"Season {season}: possession ratings require canonical plays and "
            "validated derived drives from the current refresh"
        )

    plays = [play for path in play_paths for play in json.loads(path.read_text())]
    drives = [drive for path in drive_paths for drive in json.loads(path.read_text())]
    derived = build_team_game_drive_rows(drives, plays)

    plays_by_drive: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    plays_by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for play in plays:
        game_id = str(play.get("gameId") or "")
        drive_id = str(play.get("driveId") or "")
        plays_by_game[game_id].append(play)
        plays_by_drive[(game_id, drive_id)].append(play)

    resolved_observations: dict[tuple[str, str], list[dict[str, float | None]]] = defaultdict(list)
    for drive in drives:
        if not (
            drive.get("isPossessionDrive") is True
            and drive.get("driveValidationStatus") == "PASS"
            and drive.get("offense")
        ):
            continue
        game_id = str(drive.get("gameId") or "")
        drive_id = str(drive.get("driveId") or "")
        team = str(drive.get("offense") or "")
        if not game_id or not team:
            continue
        points = adjudicated_drive_points(
            drive,
            plays_by_drive[(game_id, drive_id)],
            plays_by_game[game_id],
        )
        if points is None:
            continue
        resolved_observations[(game_id, team)].append(
            {
                "points": float(points),
                "startYardsToGoal": valid_start_yards_to_goal(drive),
            }
        )

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in derived:
        game_id = str(row.get("gameId") or "")
        team = str(row.get("team") or "")
        if not game_id or not team:
            continue
        key = (game_id, team)
        if key in out:
            raise RatingModelError(
                f"Duplicate drive-efficiency row for {game_id} / {team}"
            )
        observations = resolved_observations.get(key, [])
        resolved_count = float(row.get("resolvedPointPossessions") or 0.0)
        if observations and len(observations) != int(resolved_count):
            raise RatingModelError(
                f"Resolved drive observation mismatch for {game_id} / {team}: "
                f"{len(observations)} observations vs {resolved_count:g} possessions"
            )
        out[key] = {
            "offensiveDrivePoints": float(row.get("offensiveDrivePoints") or 0.0),
            "resolvedPointPossessions": resolved_count,
            "resolvedDriveObservations": observations,
        }
    return out


def composite_input_row(row, metric_fields):
    """Build one current-season possession-rating observation.

    Drive scoring is taken from the locked validated-drive PPD foundation. For
    synthetic/unit-test callers the two fields may be supplied directly on the
    row. Conference fields, when present, are copied only for audit/debug
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

    direct_points = row.get("offensiveDrivePoints")
    direct_possessions = row.get("resolvedPointPossessions")
    if direct_points is not None and direct_possessions is not None:
        drive_fields = {
            "offensiveDrivePoints": direct_points,
            "resolvedPointPossessions": direct_possessions,
            "resolvedDriveObservations": list(row.get("resolvedDriveObservations") or []),
        }
    else:
        key = (str(row["gameId"]), str(row["team"]))
        drive_fields = _drive_rating_fields(int(row["season"])).get(key)
        if drive_fields is None:
            # Keep the symmetric game row for graph/audit integrity but give it
            # zero statistical weight. Missing drive data must never be replaced
            # with scoreboard points or another proxy.
            drive_fields = {
                "offensiveDrivePoints": 0.0,
                "resolvedPointPossessions": 0.0,
                "resolvedDriveObservations": [],
            }
            out["driveMetricsMissing"] = True
    out.update(drive_fields)

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

        points = row.get("offensiveDrivePoints")
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

        drive_observations = row.get("resolvedDriveObservations") or []
        if not isinstance(drive_observations, list):
            raise RatingModelError(
                f"Resolved drive observations must be a list for {game_id} / {team}"
            )
        if drive_observations and len(drive_observations) != int(float(possessions)):
            raise RatingModelError(
                f"Resolved drive observations do not reconcile for {game_id} / {team}"
            )

        model_rows.append(
            {
                "team": team,
                "opponent": opponent,
                "offensiveDrivePoints": float(points),
                "resolvedPointPossessions": float(possessions),
                "resolvedDriveObservations": drive_observations,
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


def _refine_with_prior_season_opponents(
    model_rows: list[dict[str, Any]],
    *,
    offense: dict[str, float],
    defense: dict[str, float],
    league_mean: float,
    shrinkage: float,
    prior_offense: dict[str, float],
    prior_defense: dict[str, float],
    weight: float,
):
    """One refinement pass on top of an already-converged current-season-only
    fit: recompute each team's OWN offense/defense using a WEIGHT-blended
    opponent baseline (that opponent's prior-season final rating blended with
    their own converged current-season value) as the fixed reference point,
    instead of the free-standing current-season-only value. Reuses the exact
    per-team update formula fit_metric_ratings' own coordinate descent uses
    (see its `raw`/`target` lines), just evaluated once instead of iterated
    to convergence, since only the opponent side is being re-anchored -- a
    team's own side never re-reads its own prior-season number.

    Weight 0 must return (offense, defense) unchanged -- callers rely on this
    to make "no prior season available" and "taper has reached zero" both
    exact no-ops, not just approximately so.
    """
    if weight <= 0:
        return offense, defense

    blended_offense = {
        team: weight * prior_offense[team] + (1 - weight) * value
        if team in prior_offense
        else value
        for team, value in offense.items()
    }
    blended_defense = {
        team: weight * prior_defense[team] + (1 - weight) * value
        if team in prior_defense
        else value
        for team, value in defense.items()
    }

    observations = _observations(model_rows, POSSESSION_SPEC)
    by_offense: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    by_defense: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for team, opponent, value, obs_weight in observations:
        by_offense[team].append((opponent, value, obs_weight))
        by_defense[opponent].append((team, value, obs_weight))

    refined_offense = dict(offense)
    for team, games in by_offense.items():
        total_weight = sum(w for _, _, w in games)
        raw = sum(
            w * (value - league_mean + blended_defense.get(opponent, 0.0))
            for opponent, value, w in games
        )
        refined_offense[team] = raw / (total_weight + shrinkage)

    refined_defense = dict(defense)
    for team, games in by_defense.items():
        total_weight = sum(w for _, _, w in games)
        raw = sum(
            w * (league_mean + blended_offense.get(opponent, 0.0) - value)
            for opponent, value, w in games
        )
        refined_defense[team] = raw / (total_weight + shrinkage)

    return refined_offense, refined_defense


def _fit_possession_efficiency(
    rows: list[dict[str, Any]],
    *,
    season: int,
    cutoff: Any,
    input_version: str,
    ridge_equivalent_possessions: float,
    prior_offense: dict[str, float] | None = None,
    prior_defense: dict[str, float] | None = None,
    prior_weight: float = 0.0,
):
    model_rows = _validated_model_rows(rows, season)

    all_drive_observations = [
        observation
        for row in model_rows
        for observation in row.get("resolvedDriveObservations", [])
    ]
    field_position_baseline = fit_starting_field_position_ep(all_drive_observations)
    adjusted_model_rows: list[dict[str, Any]] = []
    for row in model_rows:
        observations = row.get("resolvedDriveObservations", [])
        if field_position_baseline.get("enabled") and observations:
            adjusted = field_position_adjusted_drive_value(
                observations,
                field_position_baseline,
            )
            if abs(
                adjusted["resolvedPointPossessions"]
                - float(row["resolvedPointPossessions"])
            ) > 1e-9:
                raise RatingModelError(
                    f"Field-position adjusted possession count does not reconcile "
                    f"for {row['team']} vs {row['opponent']}"
                )
            adjusted_value = adjusted["fieldPositionAdjustedDriveValue"]
        else:
            # Synthetic/unit-test rows may not carry drive-level starting
            # position. Preserve the historical raw-points behavior only for
            # that explicit fallback; production rows carry drive observations.
            adjusted_value = float(row["offensiveDrivePoints"])
        adjusted_model_rows.append(
            {
                **row,
                "fieldPositionAdjustedDriveValue": float(adjusted_value),
            }
        )

    fit = fit_metric_ratings(
        adjusted_model_rows,
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

    prior_weight = float(prior_weight)
    if not (0.0 <= prior_weight <= 1.0):
        raise RatingModelError(f"prior_weight must be in [0, 1], got {prior_weight}")
    used_prior_season = bool(prior_weight > 0 and prior_offense and prior_defense)
    if used_prior_season:
        offense, defense = _refine_with_prior_season_opponents(
            adjusted_model_rows,
            offense=offense,
            defense=defense,
            league_mean=float(fit["leagueMean"]),
            shrinkage=ridge_equivalent_possessions,
            prior_offense=prior_offense,
            prior_defense=prior_defense,
            weight=prior_weight,
        )

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
    for row in adjusted_model_rows:
        weight = float(row["resolvedPointPossessions"])
        if weight <= 0:
            continue
        value = float(row["fieldPositionAdjustedDriveValue"]) / weight
        raw_value = float(row["offensiveDrivePoints"]) / weight
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
                "rawPointsPerResolvedPossession": raw_value,
                "fieldPositionAdjustedPointsPerResolvedPossession": value,
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
        "drivePpdVersion": DRIVE_PPD_VERSION,
        "fieldPositionEpVersion": FIELD_POSITION_EP_VERSION,
        "fieldPositionBaseline": field_position_baseline,
        "usesConferenceStrength": False,
        "usesPriorSeasonTeamStrength": used_prior_season,
        "priorSeasonOpponentWeight": prior_weight,
        "usesPreseasonTeamPrior": False,
        "hfaEnabled": False,
        "rows": sorted(
            source_rows,
            key=lambda row: (
                row["team"],
                row["opponent"],
                row["fieldPositionAdjustedPointsPerResolvedPossession"],
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
        "scheduleComponents": _schedule_components(adjusted_model_rows),
        "parameterCount": 2 * len(teams),
        "ridgeEquivalentPossessions": ridge_equivalent_possessions,
        "leagueMeanPointsPerPossession": league_mean,
        "leagueMeanFieldPositionAdjustedPointsPerPossession": league_mean,
        "weightedRmsePointsPerPossession": weighted_rmse,
        "weightedRmseFieldPositionAdjustedPointsPerPossession": weighted_rmse,
        "fieldPositionAdjustment": field_position_baseline,
        "usesPriorSeasonTeamStrength": used_prior_season,
        "priorSeasonOpponentWeight": prior_weight,
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
    prior_offense=None,
    prior_defense=None,
    prior_weight=0.0,
):
    """Fit current-season recursive possession offense and defense.

    `prior_offense`/`prior_defense` are the PRIOR season's final AdjOff/AdjDef
    (already divided back down by RATING_SCALE, i.e. in this function's own
    internal units -- see _fit_possession_efficiency), keyed by team name.
    `prior_weight` (from prior_season_weight(site_week), 0 by default) tapers
    how much they blend into the OPPONENT side of the adjustment only -- see
    _refine_with_prior_season_opponents. Omit prior_offense/prior_defense or
    pass prior_weight=0 to fit exactly as before this feature existed.
    """
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
        prior_offense=prior_offense,
        prior_defense=prior_defense,
        prior_weight=prior_weight,
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
            "10 * recursively opponent-adjusted offensive points above starting-field "
            "expectation/resolved possession"
        ),
        "defenseDefinition": (
            "10 * recursively opponent-adjusted points above starting-field expectation "
            "prevented/resolved possession (higher is better)"
        ),
        "ratingScale": (
            "field-position-adjusted points per 10 resolved possessions above/below average FBS"
        ),
        "metric": (
            "offensive points above starting-field-position expectation/resolved possession"
        ),
        "opponentAdjustment": (
            "simultaneous recursive current-season offense-defense solve"
        ),
        "pointsFoundation": DRIVE_PPD_POINTS_FOUNDATION,
        "drivePpdVersion": DRIVE_PPD_VERSION,
        "fieldPositionAdjustment": (
            "cutoff-safe monotone expected-points curve from drive startYardsToGoal"
        ),
        "fieldPositionEpVersion": FIELD_POSITION_EP_VERSION,
        "stabilization": "zero-centered ridge to current-season FBS average",
        "ridgeEquivalentPossessions": RIDGE_EQUIVALENT_POSSESSIONS,
        "externalTeamStrengthInputsUsed": False,
        "conferenceStrengthUsed": False,
        "hfaEnabled": False,
        "hfaInPublishedRatings": False,
        "seasonScope": SEASON_SCOPE,
        "usesPriorSeasonTeamStrength": USES_PRIOR_SEASON_TEAM_STRENGTH,
        "usesPreseasonTeamPrior": USES_PRESEASON_TEAM_PRIOR,
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
            meta["fieldPositionAdjustmentFit"] = possession_fit[
                "fieldPositionAdjustment"
            ]
            meta["modelKey"] = possession_fit["modelMetadata"]["modelKey"]
            # Overrides the static, "does this model support it at all" flag
            # above with what actually happened for this specific cutoff --
            # e.g. false again once the taper reaches zero by
            # PRIOR_SEASON_TAPER_ZERO_WEEK, even though the model supports it.
            meta["usesPriorSeasonTeamStrength"] = possession_fit[
                "usesPriorSeasonTeamStrength"
            ]
            meta["priorSeasonOpponentWeight"] = possession_fit[
                "priorSeasonOpponentWeight"
            ]
    return meta
