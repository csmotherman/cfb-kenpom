"""Live opponent-adjusted rating model behind the published AdjOff/AdjDef/AdjNet.

This is the publication wrapper, not a second solver. The mathematics live in
`analytics/shadow_ratings.py` (unchanged, and still the module the six-season
historical-production replay validated); this module only fixes the reviewed
production configuration, the input contract, and a stable model identity so a
new-methodology rating can never be confused with a legacy one.

Configuration is frozen by the historical-production-replay gate
(`data/processed/shadow_ratings/historical-production-replay/gate.json`):
hierarchical partial pooling with lambda_team=200 and lambda_conference=400, one
unpenalized home-field coefficient per metric, season-specific conference
groups, and garbage-time-filtered canonical inputs. HFA is fitted and reported
as metadata only -- the published ratings are neutral-field.

Two model modes exist and the caller must always name one:

* ``hierarchical_hfa`` -- the migrated methodology. AdjOff/AdjDef are the
  three-metric z-score composite; AdjNet is exactly AdjOff + AdjDef.
* ``legacy`` -- the previously published contract, preserved verbatim for
  rollback: AdjNet is the walk-forward SRS fit and AdjOff/AdjDef are the
  YardsPerPlay edges from `iterative_ratings.fit_all_ratings`. Nothing in this
  module computes those; `legacy` exists here so the identity/metadata surface
  can describe either published state.
"""
from __future__ import annotations

from cfb_analytics.analytics import shadow_ratings as S
from cfb_analytics.derived.games import GARBAGE_TIME_VERSION

MODEL_MODES = ("hierarchical_hfa", "legacy")

# Stable published identities. These never change meaning; a methodology change
# requires a new identifier, not a redefinition of an existing one.
RATING_MODEL_ID = "adj-rating-hierarchical-hfa-v1"
LEGACY_RATING_MODEL_ID = "adj-rating-legacy-srs-ypp-v1"

LAMBDA_TEAM = 200.0
LAMBDA_CONFERENCE = 400.0
HFA_ENABLED = True

# The rating model reads garbage-time-filtered canonical plays. This is the ONLY
# consumer of derived/games.py's opt-in exclude_garbage_time flag; every other
# producer (Advanced page snapshots, weekly `wk` counts, team-stats, the locked
# derived partitions) still aggregates with the flag left False.
RATING_INPUT_VERSION = "canonical-production-garbage-filtered-v1"

# Exactly the numerators/denominators the three composite specs consume.
COMPOSITE_FIELDS = (
    "epaSum",
    "epaPlays",
    "successfulPlays",
    "successEligiblePlays",
    "successfulPlayYards",
)

# Identity/metadata fields carried on the rating rows the solver is handed.
_REQUIRED_ROW_FIELDS = (
    "season", "gameId", "team", "opponent", "conference", "opponent_conference",
    "classification", "opponent_classification", "neutral_site", "home_away",
)


class RatingModelError(RuntimeError):
    """A rating fit that must never reach publication."""


def require_mode(model_mode):
    if model_mode not in MODEL_MODES:
        raise RatingModelError(f"Unknown rating model mode: {model_mode!r}; choose one of {MODEL_MODES}")
    return model_mode


def composite_input_row(row, metric_fields):
    """One rating-model observation: production identity + filtered metrics.

    `row` is the exact team-game row production already hands its solver;
    `metric_fields` is that row's entry from
    ``derived/games.py::metric_fields_by_team_game(plays, exclude_garbage_time=True)``.
    A game with no canonical plays at all has no entry -- pass None and the five
    composite counts become explicit zeros, which every weighted solver drops as
    a zero-weight observation. That is recorded by the caller, never hidden, and
    is mathematically identical to how the validated study stored those rows.
    """
    missing = [f for f in _REQUIRED_ROW_FIELDS if row.get(f) is None]
    if missing:
        raise RatingModelError(f"Rating input row is missing required identity fields: {missing}")
    out = {f: row[f] for f in _REQUIRED_ROW_FIELDS}
    if metric_fields is None:
        out.update({f: 0 for f in COMPOSITE_FIELDS})
        out["garbageTimeMetricsMissing"] = True
    else:
        for field in COMPOSITE_FIELDS:
            if field not in metric_fields:
                raise RatingModelError(f"Filtered metric field {field!r} is missing for {row['team']}")
            out[field] = metric_fields[field]
    return out


def fit_publication_composite(rows, *, season, cutoff, lambda_team=LAMBDA_TEAM,
                              lambda_conf=LAMBDA_CONFERENCE, hfa_enabled=HFA_ENABLED,
                              input_version=RATING_INPUT_VERSION):
    """Fit the three metrics and assemble the neutral-field published composite.

    `cutoff` documents which observations the caller selected; it filters
    nothing. Callers must pass only games available at that cutoff (see
    build_real_data.py's per-site-week accumulation).

    Non-convergence, an unidentified HFA and invalid/degenerate inputs all raise
    rather than returning a usable-looking fit -- a bad fit must block
    publication, not be published.
    """
    if not rows:
        raise RatingModelError("Refusing to fit publication ratings from an empty rating graph")
    try:
        result = S.fit_composite(
            rows,
            model_mode="hierarchical_hfa",
            season=season,
            cutoff=cutoff,
            input_version=input_version,
            lambda_team=lambda_team,
            lambda_conf=lambda_conf,
            hfa_enabled=hfa_enabled,
        )
    except S.ConvergenceError as exc:
        raise RatingModelError(f"Rating solver did not converge at cutoff {cutoff}: {exc}") from exc
    except ValueError as exc:
        raise RatingModelError(f"Rating input rejected at cutoff {cutoff}: {exc}") from exc
    ratings = result["ratings"]
    teams = set(ratings["AdjNet"])
    for label in ("AdjOff", "AdjDef"):
        if set(ratings[label]) != teams:
            raise RatingModelError("Composite sides cover different team universes")
    for team in teams:
        total = ratings["AdjOff"][team] + ratings["AdjDef"][team]
        if abs(ratings["AdjNet"][team] - total) > 1e-9:
            raise RatingModelError(f"AdjNet is not AdjOff + AdjDef for {team}")
    for fit in result["fits"].values():
        if not fit.get("converged"):
            raise RatingModelError("A metric fit reported non-convergence")
    return result


def rating_model_metadata(model_mode, *, season, cutoff, weeks=None, fits=None,
                          rows_with_no_canonical_plays=0, teams=None):
    """Explicit, self-describing identity for a generated rating snapshot.

    Stored in build metadata so old and new ratings can never be silently mixed.
    """
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
        "modelMode": "hierarchical_hfa",
        "modelVersion": S.MODEL_VERSION,
        "netDefinition": "AdjNet = AdjOff + AdjDef",
        "offenseDefinition": "composite",
        "defenseDefinition": "composite",
        "lambdaTeam": LAMBDA_TEAM,
        "lambdaConference": LAMBDA_CONFERENCE,
        "hfaEnabled": HFA_ENABLED,
        "hfaInPublishedRatings": False,
        "garbageTimeExcluded": True,
        "garbageTimeDefinitionVersion": GARBAGE_TIME_VERSION,
        "compositeVersion": S.COMPOSITE_VERSION,
        "compositeWeights": list(S.COMPOSITE_WEIGHTS),
        "compositeMetrics": [spec[0] for spec in S.COMPOSITE_SPECS],
        "normalization": "population-sd-zscore-ddof0-over-fitted-fbs-universe",
        "inputVersion": RATING_INPUT_VERSION,
        "season": season,
        "cutoff": cutoff,
        "weeksRefit": weeks,
        "refitPerSiteWeek": True,
        "rowsWithNoCanonicalPlays": rows_with_no_canonical_plays,
        "teams": teams,
    }
    if fits:
        meta["hfa"] = {name: fit["hfa"] for name, fit in fits.items()}
        meta["hfaAvailable"] = {name: bool(fit["hfaAvailable"]) for name, fit in fits.items()}
        meta["iterations"] = {name: fit["iterations"] for name, fit in fits.items()}
        meta["observations"] = {name: fit["observations"] for name, fit in fits.items()}
        meta["modelKey"] = {name: fit["modelMetadata"]["modelKey"] for name, fit in fits.items()}
    return meta
