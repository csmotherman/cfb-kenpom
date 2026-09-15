"""RESEARCH-ONLY, READ-ONLY: "MATCHUP VALUE VALIDATION" pass for LEILA
Exploratory Tier 1 metrics.

Two prior backtests (exploratory_predictive_value.py, exploratory_wave2_
predictive_value.py) already showed NONE of the Tier 1 / Wave 2 metrics add
predictive value over the live Adj Net rating for generic game-margin
prediction. That is a real, validated negative result -- it does not mean
these metrics are useless, it means "does this metric predict who wins" was
the wrong question for metrics that describe OPPOSING TENDENCIES (an
offense's tendency to reach a situation vs. a defense's tendency to force
it). This module asks a different, narrower question for three specific
offense/defense metric pairings: does the offense's own tendency and the
defense's own tendency, taken together (additively, and via an interaction
term), predict the ACTUAL REALIZED RATE of that exact situation when the two
teams play each other -- beyond what either tendency alone predicts?

This script never modifies rating_model.py, iterative_ratings.py, ASM, the
exploratory package, or any publish/pipeline script; never writes to data/;
and is not wired into any pipeline or the site.

THREE PAIRINGS (this pass only; a future pass covers pairings 4-6):
  1. Long-Down Matchup:
       offense = Offensive Long-Down Exposure = longDownSeries/eligibleSeries
       defense = Long-Down Creation Rate = longDownsCreated/longDownCreationOpportunities
       target  = that team's own longDownSeries/eligibleSeries IN THAT GAME
  2. Recovery vs Closeout:
       offense = Recovery Rate = recoveredSeries/recoveryOpportunities
       defense = Closeout Rate = closeouts/closeoutOpportunities
       target  = that team's own recoveredSeries/recoveryOpportunities IN THAT GAME
       + series-level binary model (one row per series with an early-down failure)
  3. Series Conversion vs Series Stop:
       offense = Series Conversion Rate = seriesConversions/seriesOpportunities
       defense = Series Stop Rate = seriesStops/seriesStopOpportunities
       target  = that team's own seriesConversions/seriesOpportunities IN THAT GAME
       + series-level binary model (one row per eligible series)

ROW SOURCES (all already materialized; read-only).
  * Adj Net / AdjOff / AdjDef optional control + downstream-effect variables:
    data/canonical/season={season}/team_games.json (FBS-vs-FBS, completed),
    loaded via ppa_core_rating_backtest.load_canonical_team_games/
    attach_possession_fields verbatim (never re-derived), fit with
    rating_model.POSSESSION_SPEC via iterative_ratings.fit_metric_ratings
    (shrinkage=10.0), the exact live production call.
  * Tier 1 raw counts: data/processed/derived/exploratory/season={season}/
    season_type=*/week=*/team_games.json (already materialized for every
    season). Each row already carries `team` AND `opponent`, so offense/
    defense tendencies and the in-game target are read directly off it --
    no separate game-pairing step is needed the way the prior two backtests
    needed one for their home/away-diff framing.
  * Real chronological week: scripts.build_real_data.build_site_week_map(season)
    (site_week_by_game), the same remap export_exploratory_data.py already
    uses -- CFBD's own `week` lumps two real weeks together in week 1.
  * Series-level (Pairings 2 & 3 only): raw per-series records are NOT
    persisted to disk (only aggregated counts are). This module re-derives
    them, read-only, by calling exploratory.series.build_series(drive,
    drive_plays) UNCHANGED against data/processed/derived/drives/
    season={season}/season_type=*/week=*/drives.json (pre-filtered to
    isPossessionDrive is True and driveValidationStatus == "PASS", the same
    gate every other derived module uses) paired with canonical plays at
    data/processed/canonical/season={season}/season_type=*/week=*/plays.json
    grouped by driveId. Series reconstruction is not re-implemented here.

WALK-FORWARD DESIGN (game-level and series-level alike). Every season is
processed independently, RESET AT EACH SEASON START -- no cross-season
training-set carryover, no preseason prior, matching this pass's explicit
instruction. Within a season, partition rows by real site-week (ascending)
and for every site-week, IN ORDER:
  1. Fit Adj Net (POSSESSION_SPEC, shrinkage=10.0) on strictly-prior
     site-weeks' canonical rows only.
  2. Snapshot every team's season-to-date offense-metric and defense-metric
     RAW rate (sum numerator/sum denominator across strictly-prior weeks
     only, this season only) -- the site's own "always sum raw counts, never
     average percentages" convention.
  3. Fit Models A-D (game-level, OLS; walk_forward_baseline/_solve-based
     generic machinery reused from exploratory_predictive_value.py) and
     Models A-E (series-level, logistic; same machinery) using ONLY
     strictly-prior, feature-complete observations THIS SEASON.
  4. Score every observation in the current site-week with all fitted
     models (using only fits/rates available before that observation), THEN
     append the site-week's newly-eligible observations to training data for
     the next site-week.

ELIGIBILITY / MIN-SAMPLE FLOORS. Season-to-date offense/defense cumulative
denominators must each clear a floor set from this pairing's own field's
corpus-wide (2023-2025) per-team-game distribution 25th percentile:
25 for series/eligible/long-down-creation denominators (seriesOpportunities,
seriesStopOpportunities, eligibleSeries, longDownCreationOpportunities), 16
for recovery/closeout denominators (recoveryOpportunities,
closeoutOpportunities) -- see MIN_CUM_DEN_BY_FIELD's own comment. The
in-game TARGET's own denominator must be >= TARGET_MIN_DEN=5 (a corpus check
shows <0.02% of team-games fall below 5 for any of these six fields, i.e.
this excludes only pathological near-zero-snap rows, not a real population).
MIN_TRAIN_GAME=20 / MIN_TRAIN_SERIES=50 strictly-prior, feature-complete
observations are required before a season's regressions are trusted enough
to generate predictions (ridge-regularized OLS / L2-regularized logistic, so
these are soundness floors, not large-sample requirements).

Generic OLS/logistic machinery (_fit_ols/_predict_ols/_fit_logistic/
_predict_logistic/_standardize) is imported, unmodified, from
exploratory_predictive_value.py -- the same "explicit feature-key list"
generalization of walk_forward_baseline.py's algorithm already used and
documented there.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings
from cfb_analytics.analytics.ppa_core_rating_backtest import (
    POSSESSION_SHRINKAGE,
    POSSESSION_SPEC,
    _net_diff,
    _num,
    attach_possession_fields,
    load_canonical_team_games,
    pair_games,
)
from cfb_analytics.analytics.exploratory_predictive_value import (
    _fit_ols,
    _fit_logistic,
    _predict_ols,
    _predict_logistic,
    _standardize,
    _pearson,
)
from cfb_analytics.analytics.exploratory.series import build_series
from cfb_analytics.derived.pregame import _pk

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from build_real_data import build_site_week_map  # noqa: E402

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)

# 25th-percentile-of-per-team-game-denominator floors, computed from this
# module's own 2023-2025 corpus audit (see module docstring). Season-to-date
# CUMULATIVE denominators (offense and defense side, independently) must
# clear these before a metric is trusted as a walk-forward feature.
MIN_CUM_DEN_SERIES_FIELDS = 25   # seriesOpportunities/seriesStopOpportunities/eligibleSeries/longDownCreationOpportunities
MIN_CUM_DEN_RECOVERY_FIELDS = 16  # recoveryOpportunities/closeoutOpportunities

# In-game target denominator floor -- <0.02% of team-games fall below 5 on
# any of the six fields in play (corpus audit), so this excludes only the
# pathological near-zero-snap tail, not a real population.
TARGET_MIN_DEN = 5

GAME_MIN_TRAIN = 20
SERIES_MIN_TRAIN = 50
# Series-Conversion-vs-Stop eligibility is "every non-excluded series" --
# tens of thousands per season league-wide (a real, intentional large
# sample per the user's own request). A random-sample cap on each weekly
# refit's TRAINING set bounds pure-Python logistic-regression cost
# regardless of corpus size while still evaluating every eligible series in
# that week for the reported metrics (the cap applies to fitting only, never
# to scoring/evaluation). Documented here per this project's own precedent
# of disclosing runtime-driven cadence/threshold choices (see
# exploratory_predictive_value.py's MIN_METRIC_DEN comment).
SERIES_MAX_TRAIN_ROWS = 6000
_LOGIT_EPOCHS = 150
_RNG_SEED = 20260915

PAIRINGS: dict[str, dict[str, Any]] = {
    "long_down": {
        "label": "Long-Down Matchup",
        "offenseMetric": "Offensive Long-Down Exposure (1 - Long-Down Avoidance Rate)",
        "defenseMetric": "Long-Down Creation Rate",
        "targetLabel": "Team's own in-game Long-Down Rate (longDownSeries/eligibleSeries)",
        "off_num": "longDownSeries", "off_den": "eligibleSeries",
        "def_num": "longDownsCreated", "def_den": "longDownCreationOpportunities",
        "target_num": "longDownSeries", "target_den": "eligibleSeries",
        "off_min_cum_den": MIN_CUM_DEN_SERIES_FIELDS, "def_min_cum_den": MIN_CUM_DEN_SERIES_FIELDS,
        "seriesLevel": False,
    },
    "recovery_closeout": {
        "label": "Recovery vs Closeout",
        "offenseMetric": "Recovery Rate",
        "defenseMetric": "Closeout Rate",
        "targetLabel": "Team's own in-game Recovery Rate (recoveredSeries/recoveryOpportunities)",
        "off_num": "recoveredSeries", "off_den": "recoveryOpportunities",
        "def_num": "closeouts", "def_den": "closeoutOpportunities",
        "target_num": "recoveredSeries", "target_den": "recoveryOpportunities",
        "off_min_cum_den": MIN_CUM_DEN_RECOVERY_FIELDS, "def_min_cum_den": MIN_CUM_DEN_RECOVERY_FIELDS,
        "seriesLevel": True,
        "seriesRequiresEarlyDownFailure": True,
    },
    "series_conversion": {
        "label": "Series Conversion vs Series Stop",
        "offenseMetric": "Series Conversion Rate",
        "defenseMetric": "Series Stop Rate",
        "targetLabel": "Team's own in-game Series Conversion Rate (seriesConversions/seriesOpportunities)",
        "off_num": "seriesConversions", "off_den": "seriesOpportunities",
        "def_num": "seriesStops", "def_den": "seriesStopOpportunities",
        "target_num": "seriesConversions", "target_den": "seriesOpportunities",
        "off_min_cum_den": MIN_CUM_DEN_SERIES_FIELDS, "def_min_cum_den": MIN_CUM_DEN_SERIES_FIELDS,
        "seriesLevel": True,
        "seriesRequiresEarlyDownFailure": False,
    },
}

PAIRING_ORDER = ("long_down", "recovery_closeout", "series_conversion")


# ---------------------------------------------------------------------------
# Shared per-season loading
# ---------------------------------------------------------------------------

def load_exploratory_rows(season: int) -> list[dict[str, Any]]:
    base = REPO_ROOT / "data/processed/derived/exploratory" / f"season={season}"
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if not base.exists():
        return []
    for path in sorted(base.glob("season_type=*/week=*/team_games.json")):
        for r in json.loads(path.read_text()):
            out[(str(r.get("gameId")), str(r.get("team")))] = r
    return list(out.values())


def load_season_shared(season: int) -> dict[str, Any] | None:
    raw = load_canonical_team_games(season)
    if not raw:
        return None
    rows, missing_drive = attach_possession_fields(raw, season)
    canonical_by_team = {(str(r.get("gameId")), str(r.get("team"))): r for r in rows}
    site_week_by_game, _num_weeks, _week_labels = build_site_week_map(season)

    canon_partitions: dict[int, list[dict[str, Any]]] = defaultdict(list)
    unmapped_canon = 0
    for r in rows:
        sw = site_week_by_game.get(str(r.get("gameId")))
        if sw is None:
            unmapped_canon += 1
            continue
        canon_partitions[sw].append(r)

    expl_rows = load_exploratory_rows(season)
    expl_partitions: dict[int, list[dict[str, Any]]] = defaultdict(list)
    unmapped_expl = 0
    for r in expl_rows:
        sw = site_week_by_game.get(str(r.get("gameId")))
        if sw is None:
            unmapped_expl += 1
            continue
        expl_partitions[sw].append(r)

    return {
        "season": season,
        "canonical_by_team": canonical_by_team,
        "canon_partitions": canon_partitions,
        "expl_partitions": expl_partitions,
        "site_week_by_game": site_week_by_game,
        "missing_drive": missing_drive,
        "unmapped_canon": unmapped_canon,
        "unmapped_expl": unmapped_expl,
    }


def build_season_series(season: int) -> list[dict[str, Any]]:
    """Re-derive individual series records for one season, read-only, via
    exploratory.series.build_series (unchanged). Drives pre-filtered to
    isPossessionDrive is True and driveValidationStatus == 'PASS'."""
    out: list[dict[str, Any]] = []
    drives_base = REPO_ROOT / f"data/processed/derived/drives/season={season}"
    plays_base = REPO_ROOT / f"data/processed/canonical/season={season}"
    if not drives_base.exists():
        return out
    for drives_path in sorted(drives_base.glob("season_type=*/week=*/drives.json")):
        rel = drives_path.relative_to(drives_base).parent
        plays_path = plays_base / rel / "plays.json"
        if not plays_path.exists():
            continue
        drives = json.loads(drives_path.read_text())
        plays = json.loads(plays_path.read_text())
        by_drive: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in plays:
            by_drive[str(p.get("driveId"))].append(p)
        for d in drives:
            if d.get("isPossessionDrive") is not True or d.get("driveValidationStatus") != "PASS":
                continue
            dp = by_drive.get(str(d.get("driveId")), [])
            if not dp:
                continue
            for s in build_series(d, dp):
                out.append({
                    "season": season,
                    "gameId": str(s["gameId"]),
                    "offense": s["offense"],
                    "defense": s["defense"],
                    "converted": bool(s["converted"]),
                    "hadEarlyDownFailure": bool(s["hadEarlyDownFailure"]),
                    "excludedReason": s["excludedReason"],
                })
    return out


def _team_adjnet(poss_fit, team: str):
    if poss_fit is None:
        return None
    off = poss_fit.get("offense", {}).get(team)
    dfn = poss_fit.get("defense", {}).get(team)
    if not (_num(off) and _num(dfn)):
        return None
    return float(off) + float(dfn)


def _downstream_vars(canon_row: dict[str, Any] | None) -> dict[str, Any] | None:
    if canon_row is None:
        return None
    pf, pa = canon_row.get("points_for"), canon_row.get("points_against")
    poss = canon_row.get("validatedPossessions")
    return {
        "epaPerPlay": canon_row.get("epaPerPlay") if _num(canon_row.get("epaPerPlay")) else None,
        "successRate": canon_row.get("successRate") if _num(canon_row.get("successRate")) else None,
        "pointsFor": float(pf) if _num(pf) else None,
        "margin": (float(pf) - float(pa)) if (_num(pf) and _num(pa)) else None,
        "pointsPerPossession": (float(pf) / float(poss)) if (_num(pf) and _num(poss) and float(poss) > 0) else None,
    }


# ---------------------------------------------------------------------------
# Game-level walk-forward
# ---------------------------------------------------------------------------

def _augment_game_rows(rows: list[dict[str, Any]]):
    means_od, scales_od = _standardize(rows, ("offRate", "defRate"))
    out = []
    for r in rows:
        zoff = (r["offRate"] - means_od[0]) / scales_od[0]
        zdef = (r["defRate"] - means_od[1]) / scales_od[1]
        out.append({**r, "rawProd": r["offRate"] * r["defRate"], "zProd": zoff * zdef})
    return out, means_od, scales_od


GAME_MODEL_FEATURES = {
    "A_offenseOnly": ("offRate",),
    "B_defenseOnly": ("defRate",),
    "C_additive": ("offRate", "defRate"),
    "D_rawProduct": ("offRate", "defRate", "rawProd"),
    "D_zProduct": ("offRate", "defRate", "zProd"),
}


def _fit_game_models(train_rows: list[dict[str, Any]]):
    if len(train_rows) < GAME_MIN_TRAIN:
        return None
    aug, means_od, scales_od = _augment_game_rows(train_rows)
    fits = {}
    for name, feats in GAME_MODEL_FEATURES.items():
        w, means, scales = _fit_ols(aug, feats, "target")
        fits[name] = (w, feats, means, scales)
    return fits, means_od, scales_od


def _score_game_row(off_rate: float, def_rate: float, fits, means_od, scales_od) -> dict[str, float | None]:
    zoff = (off_rate - means_od[0]) / scales_od[0]
    zdef = (def_rate - means_od[1]) / scales_od[1]
    row = {"offRate": off_rate, "defRate": def_rate, "rawProd": off_rate * def_rate, "zProd": zoff * zdef}
    out = {}
    for name, (w, feats, means, scales) in fits.items():
        out[name] = _predict_ols(row, w, feats, means, scales) if w is not None else None
    return out


def run_pairing_game_level(pairing_key: str, shared: dict[int, dict[str, Any]]) -> dict[str, Any]:
    pairing = PAIRINGS[pairing_key]
    all_obs: list[dict[str, Any]] = []
    pregame_feat_all: dict[int, dict[tuple[str, str], dict[str, Any]]] = {}
    dropped_unmapped = 0
    dropped_no_pregame_feat = 0
    dropped_ineligible = 0

    for season in SEASONS:
        ctx = shared.get(season)
        if ctx is None:
            continue
        site_weeks = sorted(set(ctx["canon_partitions"]) | set(ctx["expl_partitions"]))
        history_canon: list[dict[str, Any]] = []
        cum: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"off": [0.0, 0.0], "def": [0.0, 0.0]})
        train_rows: list[dict[str, Any]] = []
        pregame_feat: dict[tuple[str, str], dict[str, Any]] = {}

        for sw in site_weeks:
            poss_fit = (
                fit_metric_ratings(history_canon, POSSESSION_SPEC, shrinkage=POSSESSION_SHRINKAGE,
                                    damping=1.0, tolerance=1e-9, max_iterations=10000)
                if history_canon else None
            )
            fit_bundle = _fit_game_models(train_rows)
            baseline0_pred = (sum(r["target"] for r in train_rows) / len(train_rows)) if train_rows else None

            week_expl_rows = ctx["expl_partitions"].get(sw, [])
            # 1) snapshot pregame season-to-date rates for every team appearing this week
            for r in week_expl_rows:
                team = str(r.get("team")); gid = str(r.get("gameId"))
                off_num, off_den = cum[team]["off"]
                def_num, def_den = cum[team]["def"]
                off_rate = (off_num / off_den) if off_den > 0 else None
                def_rate = (def_num / def_den) if def_den > 0 else None
                canon_row = ctx["canonical_by_team"].get((gid, team))
                home = None
                if canon_row is not None:
                    home = 1.0 if canon_row.get("home_away") == "home" else 0.0
                pregame_feat[(gid, team)] = {
                    "offRate": off_rate, "offDen": off_den,
                    "defRate": def_rate, "defDen": def_den,
                    "adjnet": _team_adjnet(poss_fit, team),
                    "home": home,
                }

            # 2) build + score this week's observations
            week_obs: list[dict[str, Any]] = []
            for r in week_expl_rows:
                team = str(r.get("team")); opp = str(r.get("opponent")); gid = str(r.get("gameId"))
                off_feat = pregame_feat.get((gid, team))
                def_feat = pregame_feat.get((gid, opp))
                if off_feat is None or def_feat is None:
                    dropped_no_pregame_feat += 1
                    continue
                tnum, tden = r.get(pairing["target_num"]), r.get(pairing["target_den"])
                eligible = (
                    off_feat["offRate"] is not None and off_feat["offDen"] >= pairing["off_min_cum_den"]
                    and def_feat["defRate"] is not None and def_feat["defDen"] >= pairing["def_min_cum_den"]
                    and isinstance(tden, (int, float)) and tden >= TARGET_MIN_DEN
                )
                if not eligible:
                    dropped_ineligible += 1
                    continue
                off_adj, def_adj = off_feat["adjnet"], def_feat["adjnet"]
                obs = {
                    "season": season, "gameId": gid, "team": team, "opponent": opp, "siteWeek": sw,
                    "offRate": off_feat["offRate"], "defRate": def_feat["defRate"],
                    "target": float(tnum) / float(tden),
                    "adjnetDiff": (off_adj - def_adj) if (_num(off_adj) and _num(def_adj)) else None,
                    "home": off_feat["home"],
                    "baseline0Pred": baseline0_pred,
                    "downstream": _downstream_vars(ctx["canonical_by_team"].get((gid, team))),
                }
                if fit_bundle is not None:
                    fits, means_od, scales_od = fit_bundle
                    obs.update(_score_game_row(off_feat["offRate"], def_feat["defRate"], fits, means_od, scales_od))
                else:
                    obs.update({name: None for name in GAME_MODEL_FEATURES})
                week_obs.append(obs)

            all_obs.extend(week_obs)
            train_rows.extend(week_obs)

            # 3) roll cumulative sums forward with this week's realized raw counts
            for r in week_expl_rows:
                team = str(r.get("team"))
                cum[team]["off"][0] += float(r.get(pairing["off_num"]) or 0)
                cum[team]["off"][1] += float(r.get(pairing["off_den"]) or 0)
                cum[team]["def"][0] += float(r.get(pairing["def_num"]) or 0)
                cum[team]["def"][1] += float(r.get(pairing["def_den"]) or 0)
            history_canon.extend(ctx["canon_partitions"].get(sw, []))

        pregame_feat_all[season] = pregame_feat
        dropped_unmapped += ctx["unmapped_canon"] + ctx["unmapped_expl"]

    return {
        "pairing": pairing_key,
        "observations": all_obs,
        "pregameFeatBySeason": pregame_feat_all,
        "droppedUnmapped": dropped_unmapped,
        "droppedNoPregameFeat": dropped_no_pregame_feat,
        "droppedIneligible": dropped_ineligible,
    }


# ---------------------------------------------------------------------------
# Series-level walk-forward (logistic), Pairings 2 & 3
# ---------------------------------------------------------------------------

SERIES_MODEL_FEATURES = {
    "A_controlsOnly": ("home", "adjnetDiff"),
    "B_offenseOnly": ("home", "adjnetDiff", "offRate"),
    "C_defenseOnly": ("home", "adjnetDiff", "defRate"),
    "D_additive": ("home", "adjnetDiff", "offRate", "defRate"),
    "E_interaction": ("home", "adjnetDiff", "offRate", "defRate", "zProd"),
}


def run_pairing_series_level(pairing_key: str, series_by_season: dict[int, list[dict[str, Any]]],
                              pregame_feat_all: dict[int, dict[tuple[str, str], dict[str, Any]]],
                              shared: dict[int, dict[str, Any]]) -> dict[str, Any]:
    pairing = PAIRINGS[pairing_key]
    rng = random.Random(_RNG_SEED)
    all_obs: list[dict[str, Any]] = []
    dropped_excluded = 0
    dropped_not_early_failure = 0
    dropped_no_pregame_feat = 0
    dropped_ineligible = 0

    for season in SEASONS:
        ctx = shared.get(season)
        series = series_by_season.get(season)
        pregame_feat = pregame_feat_all.get(season)
        if ctx is None or not series or pregame_feat is None:
            continue
        swmap = ctx["site_week_by_game"]

        rows: list[dict[str, Any]] = []
        for s in series:
            if s["excludedReason"] is not None:
                dropped_excluded += 1
                continue
            if pairing.get("seriesRequiresEarlyDownFailure") and not s["hadEarlyDownFailure"]:
                dropped_not_early_failure += 1
                continue
            sw = swmap.get(s["gameId"])
            if sw is None:
                continue
            off_feat = pregame_feat.get((s["gameId"], s["offense"]))
            def_feat = pregame_feat.get((s["gameId"], s["defense"]))
            if off_feat is None or def_feat is None:
                dropped_no_pregame_feat += 1
                continue
            off_adj, def_adj = off_feat["adjnet"], def_feat["adjnet"]
            eligible = (
                off_feat["offRate"] is not None and off_feat["offDen"] >= pairing["off_min_cum_den"]
                and def_feat["defRate"] is not None and def_feat["defDen"] >= pairing["def_min_cum_den"]
                and off_feat["home"] is not None and _num(off_adj) and _num(def_adj)
            )
            if not eligible:
                dropped_ineligible += 1
                continue
            rows.append({
                "season": season, "gameId": s["gameId"], "siteWeek": sw,
                "offRate": off_feat["offRate"], "defRate": def_feat["defRate"],
                "home": off_feat["home"], "adjnetDiff": off_adj - def_adj,
                "target": 1.0 if s["converted"] else 0.0,
            })

        by_week: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            by_week[r["siteWeek"]].append(r)

        train: list[dict[str, Any]] = []
        for sw in sorted(by_week):
            fit_bundle = None
            if len(train) >= SERIES_MIN_TRAIN:
                fit_pool = train if len(train) <= SERIES_MAX_TRAIN_ROWS else rng.sample(train, SERIES_MAX_TRAIN_ROWS)
                means_od, scales_od = _standardize(fit_pool, ("offRate", "defRate"))
                aug = []
                for r in fit_pool:
                    zoff = (r["offRate"] - means_od[0]) / scales_od[0]
                    zdef = (r["defRate"] - means_od[1]) / scales_od[1]
                    aug.append({**r, "zProd": zoff * zdef})
                fits = {}
                for name, feats in SERIES_MODEL_FEATURES.items():
                    means, scales = _standardize(aug, feats)
                    w = _fit_logistic(aug, feats, "target", means, scales, epochs=_LOGIT_EPOCHS)
                    fits[name] = (w, feats, means, scales)
                fit_bundle = (fits, means_od, scales_od)

            base_pred = (sum(r["target"] for r in train) / len(train)) if train else None
            for r in by_week[sw]:
                r["baseline0Pred"] = base_pred
                if fit_bundle is not None:
                    fits, means_od, scales_od = fit_bundle
                    zoff = (r["offRate"] - means_od[0]) / scales_od[0]
                    zdef = (r["defRate"] - means_od[1]) / scales_od[1]
                    row = dict(r); row["zProd"] = zoff * zdef
                    for name, (w, feats, means, scales) in fits.items():
                        r[name] = _predict_logistic(row, w, feats, means, scales) if w is not None else None
                else:
                    for name in SERIES_MODEL_FEATURES:
                        r[name] = None
                all_obs.append(r)
            train.extend(by_week[sw])

    return {
        "pairing": pairing_key,
        "observations": all_obs,
        "droppedExcluded": dropped_excluded,
        "droppedNotEarlyFailure": dropped_not_early_failure,
        "droppedNoPregameFeat": dropped_no_pregame_feat,
        "droppedIneligible": dropped_ineligible,
    }


# ---------------------------------------------------------------------------
# Aggregation / reporting helpers
# ---------------------------------------------------------------------------

def _mae_rmse(pairs: list[tuple[float, float]]):
    if not pairs:
        return None, None
    errs = [p - a for p, a in pairs]
    n = len(errs)
    return sum(abs(e) for e in errs) / n, math.sqrt(sum(e * e for e in errs) / n)


def _rank(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman(pairs: list[tuple[float, float]]):
    if len(pairs) < 2:
        return None
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    rx, ry = _rank(xs), _rank(ys)
    return _pearson(list(zip(rx, ry)))


def game_model_stats(obs: list[dict[str, Any]], model_key: str) -> dict[str, Any]:
    rows = [o for o in obs if o.get(model_key) is not None]
    n = len(rows)
    if n == 0:
        return {"n": 0}
    pairs = [(o[model_key], o["target"]) for o in rows]
    mae, rmse = _mae_rmse(pairs)
    pear = _pearson(pairs)
    spear = _spearman(pairs)
    ss_res = sum((p - a) ** 2 for p, a in pairs)
    base_pairs = [(o["baseline0Pred"], o["target"]) for o in rows if o.get("baseline0Pred") is not None]
    ss_res_base = sum((p - a) ** 2 for p, a in base_pairs) if len(base_pairs) == n else None
    r2 = (1 - ss_res / ss_res_base) if (ss_res_base is not None and ss_res_base > 0) else None
    return {"n": n, "mae": mae, "rmse": rmse, "pearsonR": pear, "spearmanR": spear, "r2VsBaseline0": r2}


def game_pairing_report(bundle: dict[str, Any]) -> dict[str, Any]:
    obs = bundle["observations"]
    matched = [o for o in obs if all(o.get(k) is not None for k in GAME_MODEL_FEATURES) and o.get("baseline0Pred") is not None]
    models_report = {name: game_model_stats(matched, name) for name in GAME_MODEL_FEATURES}
    baseline0_rows = [o for o in matched]
    base_pairs = [(o["baseline0Pred"], o["target"]) for o in baseline0_rows]
    mae0, rmse0 = _mae_rmse(base_pairs)
    models_report["Baseline0_leagueMean"] = {
        "n": len(base_pairs), "mae": mae0, "rmse": rmse0,
        "pearsonR": _pearson(base_pairs), "spearmanR": _spearman(base_pairs), "r2VsBaseline0": 0.0 if base_pairs else None,
    }

    # downstream effect: realized target vs same-game offensive efficiency
    dstream_rows = [o for o in obs if o.get("downstream") is not None]
    downstream = {}
    for key in ("epaPerPlay", "successRate", "pointsPerPossession", "pointsFor", "margin"):
        pairs = [(o["target"], o["downstream"][key]) for o in dstream_rows if o["downstream"].get(key) is not None]
        downstream[key] = {"n": len(pairs), "corr": _pearson(pairs)}

    # bucket analysis: full-sample z-score median split on offRate/defRate
    elig = [o for o in obs if o.get("offRate") is not None and o.get("defRate") is not None]
    off_med = sorted(o["offRate"] for o in elig)[len(elig) // 2] if elig else None
    def_med = sorted(o["defRate"] for o in elig)[len(elig) // 2] if elig else None
    buckets = {"LOW_LOW": [], "LOW_HIGH": [], "HIGH_LOW": [], "HIGH_HIGH": []}
    for o in elig:
        ob = "HIGH" if o["offRate"] >= off_med else "LOW"
        db = "HIGH" if o["defRate"] >= def_med else "LOW"
        buckets[f"{ob}_{db}"].append(o["target"])
    bucket_report = {
        k: {"n": len(v), "meanRealizedRate": (sum(v) / len(v)) if v else None}
        for k, v in buckets.items()
    }

    return {
        "pairing": bundle["pairing"],
        "n_eligible_observations": len(obs),
        "n_matched_all_models": len(matched),
        "droppedUnmapped": bundle["droppedUnmapped"],
        "droppedNoPregameFeat": bundle["droppedNoPregameFeat"],
        "droppedIneligible": bundle["droppedIneligible"],
        "models": models_report,
        "downstream": downstream,
        "buckets": bucket_report,
        "offMedian": off_med, "defMedian": def_med,
    }


def _log_loss(rows, key):
    eps = 1e-9
    vals = []
    for r in rows:
        p = r.get(key)
        if p is None:
            continue
        p = min(max(p, eps), 1 - eps)
        y = r["target"]
        vals.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    return sum(vals) / len(vals) if vals else None


def _brier(rows, key):
    vals = [(r[key] - r["target"]) ** 2 for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def _accuracy(rows, key):
    vals = [int((r[key] >= 0.5) == bool(r["target"])) for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def _auc(rows, key):
    pos = [r[key] for r in rows if r.get(key) is not None and r["target"] == 1]
    neg = [r[key] for r in rows if r.get(key) is not None and r["target"] == 0]
    if not pos or not neg:
        return None
    combined_vals = [v for v in neg] + [v for v in pos]
    labels = [0] * len(neg) + [1] * len(pos)
    ranks = _rank(combined_vals)
    rank_sum_pos = sum(r for r, lbl in zip(ranks, labels) if lbl == 1)
    n1, n0 = len(pos), len(neg)
    u = rank_sum_pos - n1 * (n1 + 1) / 2
    return u / (n1 * n0)


def _calibration_gap(rows, key, n_buckets: int = 10):
    scored = sorted((r for r in rows if r.get(key) is not None), key=lambda r: r[key])
    if len(scored) < n_buckets * 5:
        return None
    size = len(scored) // n_buckets
    gaps = []
    for i in range(n_buckets):
        chunk = scored[i * size:(i + 1) * size] if i < n_buckets - 1 else scored[i * size:]
        if not chunk:
            continue
        mean_pred = sum(r[key] for r in chunk) / len(chunk)
        mean_actual = sum(r["target"] for r in chunk) / len(chunk)
        gaps.append(abs(mean_pred - mean_actual))
    return (sum(gaps) / len(gaps)) if gaps else None


def series_model_stats(rows, key) -> dict[str, Any]:
    scored = [r for r in rows if r.get(key) is not None]
    n = len(scored)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "logLoss": _log_loss(scored, key),
        "brier": _brier(scored, key),
        "auc": _auc(scored, key),
        "accuracy": _accuracy(scored, key),
        "meanCalibrationGap": _calibration_gap(scored, key),
    }


def series_pairing_report(bundle: dict[str, Any]) -> dict[str, Any]:
    obs = bundle["observations"]
    matched = [o for o in obs if all(o.get(k) is not None for k in SERIES_MODEL_FEATURES) and o.get("baseline0Pred") is not None]
    models_report = {name: series_model_stats(matched, name) for name in SERIES_MODEL_FEATURES}
    models_report["Baseline0_leagueMean"] = series_model_stats(matched, "baseline0Pred")
    return {
        "pairing": bundle["pairing"],
        "n_eligible_series": len(obs),
        "n_matched_all_models": len(matched),
        "droppedExcluded": bundle["droppedExcluded"],
        "droppedNotEarlyFailure": bundle["droppedNotEarlyFailure"],
        "droppedNoPregameFeat": bundle["droppedNoPregameFeat"],
        "droppedIneligible": bundle["droppedIneligible"],
        "models": models_report,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all(seasons=SEASONS) -> dict[str, Any]:
    shared: dict[int, dict[str, Any]] = {}
    for s in seasons:
        ctx = load_season_shared(s)
        if ctx is not None:
            shared[s] = ctx

    series_by_season: dict[int, list[dict[str, Any]]] = {}
    seasons_needing_series = {s for key in PAIRING_ORDER if PAIRINGS[key].get("seriesLevel") for s in seasons}
    for s in seasons_needing_series:
        if s in shared:
            series_by_season[s] = build_season_series(s)

    report: dict[str, Any] = {"seasons": sorted(shared), "pairings": {}}
    for key in PAIRING_ORDER:
        pairing = PAIRINGS[key]
        game_bundle = run_pairing_game_level(key, shared)
        game_report = game_pairing_report(game_bundle)
        entry = {"config": {k: v for k, v in pairing.items()}, "gameLevel": game_report}
        if pairing.get("seriesLevel"):
            series_bundle = run_pairing_series_level(key, series_by_season, game_bundle["pregameFeatBySeason"], shared)
            entry["seriesLevel"] = series_pairing_report(series_bundle)
        report["pairings"][key] = entry
    return report


def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "n/a"


def concise(report: dict[str, Any]) -> str:
    lines = ["MATCHUP VALUE VALIDATION", f"Seasons: {report['seasons']}", ""]
    for key in PAIRING_ORDER:
        entry = report["pairings"].get(key)
        if entry is None:
            continue
        gl = entry["gameLevel"]
        lines += [f"=== {PAIRINGS[key]['label']} (game-level) ===",
                  f"eligible obs={gl['n_eligible_observations']} matched-all-models={gl['n_matched_all_models']} "
                  f"droppedUnmapped={gl['droppedUnmapped']} droppedNoPregame={gl['droppedNoPregameFeat']} droppedIneligible={gl['droppedIneligible']}"]
        for name, m in gl["models"].items():
            lines.append(f"  {name:>22}: n={m.get('n',0):>6} mae={_fmt(m.get('mae'),3)} rmse={_fmt(m.get('rmse'),3)} "
                         f"r={_fmt(m.get('pearsonR'))} rho={_fmt(m.get('spearmanR'))} r2vB0={_fmt(m.get('r2VsBaseline0'))}")
        lines.append("  buckets: " + ", ".join(f"{k}={v['meanRealizedRate'] and round(v['meanRealizedRate'],3)}(n={v['n']})" for k, v in gl["buckets"].items()))
        lines.append("  downstream corr(target, X): " + ", ".join(f"{k}={_fmt(v['corr'])}(n={v['n']})" for k, v in gl["downstream"].items()))
        if "seriesLevel" in entry:
            sl = entry["seriesLevel"]
            lines += [f"--- {PAIRINGS[key]['label']} (series-level) ---",
                      f"eligible series={sl['n_eligible_series']} matched-all-models={sl['n_matched_all_models']} "
                      f"droppedExcluded={sl['droppedExcluded']} droppedNotEarlyFailure={sl['droppedNotEarlyFailure']} "
                      f"droppedNoPregame={sl['droppedNoPregameFeat']} droppedIneligible={sl['droppedIneligible']}"]
            for name, m in sl["models"].items():
                lines.append(f"  {name:>22}: n={m.get('n',0):>6} logloss={_fmt(m.get('logLoss'),4)} brier={_fmt(m.get('brier'),4)} "
                             f"auc={_fmt(m.get('auc'))} acc={_fmt(m.get('accuracy'))} calGap={_fmt(m.get('meanCalibrationGap'),4)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, nargs="*", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    seasons = args.seasons if args.seasons else SEASONS
    report = run_all(seasons=seasons)
    print(concise(report))
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
