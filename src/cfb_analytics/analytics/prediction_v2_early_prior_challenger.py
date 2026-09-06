"""Predeclared early-season adjacent-prior challenger for Prediction v2.

The primary challenger carries the immediately previous season into the first four
current-season games with a fixed linear decay. The rule is frozen before game-
margin results are inspected:

    games before: 0 -> prior weight 1.00
                  1 -> prior weight 0.75
                  2 -> prior weight 0.50
                  3 -> prior weight 0.25
                  4+-> prior weight 0.00

The previous season is treated as the missing share of a four-game evidence
window. Team state is blended before matchup edges are constructed. Before four
games, a component with no finite current-season estimate keeps its finite prior
value rather than inventing zero evidence. At four or more games there is no prior
fallback. No PBP replay is performed; the command reads saved artifacts only.

This is a development challenger, not Prediction v3. Historical success makes it
a candidate to freeze prospectively for 2026 rather than permission to retune the
same inspected holdouts.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.football_mechanisms import _state, _sum_into, orient_matchup
from cfb_analytics.analytics.iterative_ratings import SPECS, fit_all_ratings
from cfb_analytics.analytics.model_feature_contract import iterative_matchup_value
from cfb_analytics.analytics.model_feature_store import load_saved_feature_store
from cfb_analytics.analytics.prediction_v1_integrity_audit import load_all_prediction_rows
from cfb_analytics.analytics.prediction_v1_site_aware_challenger import (
    fit_generic,
    fit_site_aware_srs,
    partition_key,
    prepare_generic,
    score_generic,
    site_aware_margin,
)
from cfb_analytics.analytics.prediction_v2 import PREDICTION_V2_FEATURES
from cfb_analytics.analytics.prediction_v2_early_prior_audit import (
    EARLY_MAX_WEEK,
    REQUIRED_MECHANISM_FIELDS,
    adjacent_prior_map,
    load_team_games,
)
from cfb_analytics.analytics.sandbox_components import compute_systems_from_components
from cfb_analytics.analytics.site_context_audit import load_raw_site_rows
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS

CHALLENGER_VERSION = "prediction-v2-early-prior-four-game-linear-v1"
PRIOR_WINDOW_GAMES = 4
TEST_SEASONS = (2018, 2019, 2022, 2023, 2024, 2025)
RECENT_TEST_SEASONS = (2023, 2024, 2025)
BASELINE_FEATURES = ("baselineNonNeutral",)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def prior_weight(games_before: int) -> float:
    games = max(0, int(games_before))
    return max(0.0, (PRIOR_WINDOW_GAMES - min(games, PRIOR_WINDOW_GAMES)) / PRIOR_WINDOW_GAMES)


def blend_value(prior: Any, current: Any, games_before: int) -> float | None:
    weight = prior_weight(games_before)
    if weight <= 0.0:
        return float(current) if finite(current) else None
    if not finite(prior):
        return None
    if weight >= 1.0 or not finite(current):
        return float(prior)
    return weight * float(prior) + (1.0 - weight) * float(current)


def is_early_regular(row: dict[str, Any]) -> bool:
    season_type = str(row.get("seasonType") or "regular").lower()
    return season_type in {"regular", "regular_season"} and int(row.get("week") or 0) <= EARLY_MAX_WEEK


def games_before(row: dict[str, Any]) -> tuple[int, int]:
    return (
        int(row.get("homeIterativeGamesPlayedBefore", 0) or 0),
        int(row.get("awayIterativeGamesPlayedBefore", 0) or 0),
    )


def eligible_features(row: dict[str, Any]) -> bool:
    return (
        finite(row.get("target_margin"))
        and row.get("target_homeWin") in (0, 1)
        and all(finite(row.get(feature)) for feature in PREDICTION_V2_FEATURES)
    )


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing saved artifact: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list in {path}")
    return [row for row in payload if isinstance(row, dict)]


def _prefix(matchup: dict[str, Any], team: str) -> str | None:
    if str(matchup.get("team1")) == str(team):
        return "team1"
    if str(matchup.get("team2")) == str(team):
        return "team2"
    return None


def _load_mechanism_matchups(processed_root: Path, season: int) -> dict[str, dict[str, Any]]:
    path = processed_root / "derived" / "football_mechanisms" / f"season={season}" / "matchups.json"
    return {str(row.get("gameId")): row for row in _load_json_list(path) if row.get("gameId") is not None}


def _load_sandbox_matchups(processed_root: Path, season: int) -> dict[str, dict[str, Any]]:
    path = processed_root / "derived" / "sandbox_pregame" / f"season={season}" / "game_matchups.json"
    return {str(row.get("gameId")): row for row in _load_json_list(path) if row.get("gameId") is not None}


def _attach_current_site_state(
    raw_root: Path,
    rows: list[dict[str, Any]],
    season: int,
) -> list[dict[str, Any]]:
    site_rows, _, _ = load_raw_site_rows(raw_root, season)
    attached: list[dict[str, Any]] = []
    for row in rows:
        site = site_rows.get(str(row.get("gameId")))
        if site is None or not isinstance(site.get("isNeutralSite"), bool):
            raise ValueError(f"Missing parseable site context for {season} game {row.get('gameId')}")
        attached.append({**row, "isNeutralSite": site["isNeutralSite"]})

    partitions: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in attached:
        partitions[partition_key(row)].append(row)

    history: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for key in sorted(partitions):
        fitted = fit_site_aware_srs(history)
        if fitted.get("converged") is not True:
            raise RuntimeError(f"Current site-aware SRS failed to converge for {season} partition {key}")
        ratings = fitted.get("ratings", {})
        hfa = float(fitted.get("homeFieldAdvantage", 0.0))
        for base in partitions[key]:
            home = ratings.get(str(base.get("homeTeam")))
            away = ratings.get(str(base.get("awayTeam")))
            edge = float(home) - float(away) if finite(home) and finite(away) else None
            row = dict(base)
            row.update(
                {
                    "currentSiteAwareHomeRating": home,
                    "currentSiteAwareAwayRating": away,
                    "siteAwareSrsEdge": edge,
                    "siteAwareSrsHfaBefore": hfa,
                    "siteAwareSrsMargin": site_aware_margin(edge, hfa, base.get("isNeutralSite")),
                }
            )
            out.append(row)
        history.extend(partitions[key])
    return out


def _prior_state(raw_root: Path, processed_root: Path, prior_season: int) -> dict[str, Any]:
    team_games = load_team_games(raw_root, processed_root, prior_season)
    teams = sorted({str(row.get("team")) for row in team_games if row.get("team")})

    iterative_fit = fit_all_ratings(team_games)
    iterative: dict[str, dict[str, float]] = defaultdict(dict)
    for team in teams:
        for name, *_ in SPECS:
            result = iterative_fit.get(name, {})
            offense = result.get("offense", {}).get(team)
            defense = result.get("defense", {}).get(team)
            if finite(offense):
                iterative[team][f"{name}Offense"] = float(offense)
            if finite(defense):
                iterative[team][f"{name}Defense"] = float(defense)

    totals: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: Counter[str] = Counter()
    for row in team_games:
        team = row.get("team")
        if not team:
            continue
        name = str(team)
        _sum_into(totals[name], row)
        counts[name] += 1
    mechanisms = {team: _state(totals[team], counts[team]) for team in counts}

    component_path = processed_root / "derived" / "sandbox_components" / f"season={prior_season}" / "team_games.json"
    sandbox_ratings = compute_systems_from_components(_load_json_list(component_path))
    mwdr = {
        str(row.get("Team")): {
            "Off": row.get("MWDR_Off"),
            "Def": row.get("MWDR_Def"),
        }
        for row in sandbox_ratings
        if row.get("Team")
    }

    prior_rows = load_saved_feature_store(processed_root, prior_season)
    site_rows, _, _ = load_raw_site_rows(raw_root, prior_season)
    site_attached: list[dict[str, Any]] = []
    for row in prior_rows:
        site = site_rows.get(str(row.get("gameId")))
        if site is None or not isinstance(site.get("isNeutralSite"), bool):
            raise ValueError(f"Missing prior site context for {prior_season} game {row.get('gameId')}")
        site_attached.append({**row, "isNeutralSite": site["isNeutralSite"]})
    site_fit = fit_site_aware_srs(site_attached)
    if site_fit.get("converged") is not True:
        raise RuntimeError(f"Final prior site-aware SRS failed for {prior_season}")

    return {
        "season": prior_season,
        "iterative": dict(iterative),
        "mechanisms": mechanisms,
        "mwdr": mwdr,
        "siteRatings": site_fit.get("ratings", {}),
        "hfa": float(site_fit["homeFieldAdvantage"]),
    }


def _current_mechanism_state(matchup: dict[str, Any], team: str) -> dict[str, Any]:
    prefix = _prefix(matchup, team)
    if prefix is None:
        return {}
    return {field: matchup.get(f"{prefix}_{field}") for field in REQUIRED_MECHANISM_FIELDS}


def _current_mwdr_state(matchup: dict[str, Any], team: str) -> dict[str, Any]:
    prefix = _prefix(matchup, team)
    if prefix is None:
        return {}
    return {
        "Off": matchup.get(f"{prefix}_Off_MWDR"),
        "Def": matchup.get(f"{prefix}_Def_MWDR"),
    }


def _select(prior: Any, current: Any, games: int, mode: str) -> float | None:
    if mode == "prior":
        return float(prior) if finite(prior) else None
    if mode == "blend":
        return blend_value(prior, current, games)
    raise ValueError(f"Unknown early prior mode: {mode}")


def _build_variant_row(
    current: dict[str, Any],
    prior: dict[str, Any],
    mechanism_matchup: dict[str, Any],
    sandbox_matchup: dict[str, Any],
    mode: str,
) -> dict[str, Any] | None:
    home = str(current.get("homeTeam"))
    away = str(current.get("awayTeam"))
    home_games, away_games = games_before(current)
    out = dict(current)

    for name, *_ in SPECS:
        current_ho = current.get(f"home_iterative{name}Offense")
        current_hd = current.get(f"home_iterative{name}Defense")
        current_ao = current.get(f"away_iterative{name}Offense")
        current_ad = current.get(f"away_iterative{name}Defense")
        prior_home = prior["iterative"].get(home, {})
        prior_away = prior["iterative"].get(away, {})
        ho = _select(prior_home.get(f"{name}Offense"), current_ho, home_games, mode)
        hd = _select(prior_home.get(f"{name}Defense"), current_hd, home_games, mode)
        ao = _select(prior_away.get(f"{name}Offense"), current_ao, away_games, mode)
        ad = _select(prior_away.get(f"{name}Defense"), current_ad, away_games, mode)
        if not all(finite(value) for value in (ho, hd, ao, ad)):
            return None
        out[f"home_iterative{name}Edge"] = iterative_matchup_value(ho, ad)
        out[f"away_iterative{name}Edge"] = iterative_matchup_value(ao, hd)

    prior_home_srs = prior["siteRatings"].get(home)
    prior_away_srs = prior["siteRatings"].get(away)
    home_srs = _select(prior_home_srs, current.get("currentSiteAwareHomeRating"), home_games, mode)
    away_srs = _select(prior_away_srs, current.get("currentSiteAwareAwayRating"), away_games, mode)
    if not finite(home_srs) or not finite(away_srs):
        return None
    if mode == "prior":
        hfa = prior.get("hfa")
    else:
        weight = (prior_weight(home_games) + prior_weight(away_games)) / 2.0
        current_hfa = current.get("siteAwareSrsHfaBefore")
        if weight <= 0.0:
            hfa = float(current_hfa) if finite(current_hfa) else None
        elif weight >= 1.0:
            hfa = float(prior["hfa"])
        elif finite(current_hfa):
            hfa = weight * float(prior["hfa"]) + (1.0 - weight) * float(current_hfa)
        else:
            hfa = float(prior["hfa"])
    edge = float(home_srs) - float(away_srs)
    out["siteAwareSrsMargin"] = site_aware_margin(edge, hfa, current.get("isNeutralSite"))
    if not finite(out.get("siteAwareSrsMargin")):
        return None

    current_home_mwdr = _current_mwdr_state(sandbox_matchup, home)
    current_away_mwdr = _current_mwdr_state(sandbox_matchup, away)
    prior_home_mwdr = prior["mwdr"].get(home, {})
    prior_away_mwdr = prior["mwdr"].get(away, {})
    home_mwdr_off = _select(prior_home_mwdr.get("Off"), current_home_mwdr.get("Off"), home_games, mode)
    home_mwdr_def = _select(prior_home_mwdr.get("Def"), current_home_mwdr.get("Def"), home_games, mode)
    away_mwdr_off = _select(prior_away_mwdr.get("Off"), current_away_mwdr.get("Off"), away_games, mode)
    away_mwdr_def = _select(prior_away_mwdr.get("Def"), current_away_mwdr.get("Def"), away_games, mode)
    if not all(finite(value) for value in (home_mwdr_off, home_mwdr_def, away_mwdr_off, away_mwdr_def)):
        return None
    out["home_MWDR_OffenseEdge"] = float(home_mwdr_off) - float(away_mwdr_def)
    out["home_MWDR_DefenseEdge"] = float(home_mwdr_def) - float(away_mwdr_off)

    current_home_mech = _current_mechanism_state(mechanism_matchup, home)
    current_away_mech = _current_mechanism_state(mechanism_matchup, away)
    prior_home_mech = prior["mechanisms"].get(home, {})
    prior_away_mech = prior["mechanisms"].get(away, {})
    synthetic: dict[str, Any] = {"team1": home, "team2": away}
    for field in REQUIRED_MECHANISM_FIELDS:
        home_value = _select(prior_home_mech.get(field), current_home_mech.get(field), home_games, mode)
        away_value = _select(prior_away_mech.get(field), current_away_mech.get(field), away_games, mode)
        if not finite(home_value) or not finite(away_value):
            return None
        synthetic[f"team1_{field}"] = home_value
        synthetic[f"team2_{field}"] = away_value
    oriented = orient_matchup(synthetic, home, away)
    if oriented is None:
        return None
    poss = oriented.get("expectedPossessionsPerTeam")
    success = oriented.get("netSuccessRateEdge")
    explosive = oriented.get("netExplosiveRateEdge")
    turnover = oriented.get("netTurnoverPressureEdge")
    if not all(finite(value) for value in (poss, success, explosive, turnover)):
        return None
    mwdr_edge = float(out["home_MWDR_OffenseEdge"]) + float(out["home_MWDR_DefenseEdge"])
    out["mwdrXExpectedPossessions"] = mwdr_edge * float(poss)
    out["successVolumeEdge"] = float(success) * float(poss)
    out["explosiveVolumeEdge"] = float(explosive) * float(poss)
    out["turnoverVolumeEdge"] = float(turnover) * float(poss)
    out["expectedPossessionsPerTeam"] = float(poss)
    out["priorWeightHome"] = 1.0 if mode == "prior" else prior_weight(home_games)
    out["priorWeightAway"] = 1.0 if mode == "prior" else prior_weight(away_games)
    out["earlyPriorMode"] = mode
    out["earlyPriorVersion"] = CHALLENGER_VERSION
    out["baselineNonNeutral"] = 0.0 if current.get("isNeutralSite") else 1.0
    return out if eligible_features(out) else None


def _current_early_row(row: dict[str, Any]) -> dict[str, Any] | None:
    out = dict(row)
    out["baselineNonNeutral"] = 0.0 if row.get("isNeutralSite") else 1.0
    return out if is_early_regular(out) and eligible_features(out) else None


def build_datasets(raw_root: Path, processed_root: Path) -> dict[str, Any]:
    print("Loading saved Prediction-v2 inputs only; no PBP replay.", flush=True)
    base = load_all_prediction_rows(processed_root)
    current = {
        season: _attach_current_site_state(raw_root, base[season], season)
        for season in DEFAULT_SEASONS
    }
    prior_map = adjacent_prior_map()
    blend: dict[int, list[dict[str, Any]]] = defaultdict(list)
    prior_only: dict[int, list[dict[str, Any]]] = defaultdict(list)
    current_only: dict[int, list[dict[str, Any]]] = defaultdict(list)
    coverage: dict[int, dict[str, int]] = {}
    late_total = 0
    late_mismatches = 0
    late_max_abs = 0.0

    prior_cache: dict[int, dict[str, Any]] = {}
    for season, prior_season in sorted(prior_map.items()):
        print(f" PRIOR STATE {season} <- {prior_season}", flush=True)
        prior_cache[prior_season] = prior_cache.get(prior_season) or _prior_state(raw_root, processed_root, prior_season)
        prior = prior_cache[prior_season]
        mechanisms = _load_mechanism_matchups(processed_root, season)
        sandbox = _load_sandbox_matchups(processed_root, season)
        early_total = 0
        early_blend = 0
        early_prior = 0
        early_current = 0

        for row in current[season]:
            gid = str(row.get("gameId"))
            mechanism = mechanisms.get(gid)
            sandbox_matchup = sandbox.get(gid)
            if mechanism is None or sandbox_matchup is None:
                continue
            hg, ag = games_before(row)

            if is_early_regular(row):
                early_total += 1
                blend_row = _build_variant_row(row, prior, mechanism, sandbox_matchup, "blend")
                prior_row = _build_variant_row(row, prior, mechanism, sandbox_matchup, "prior")
                current_row = _current_early_row(row)
                if blend_row is not None:
                    blend[season].append(blend_row)
                    early_blend += 1
                if prior_row is not None:
                    prior_only[season].append(prior_row)
                    early_prior += 1
                if current_row is not None:
                    current_only[season].append(current_row)
                    early_current += 1

            if hg >= PRIOR_WINDOW_GAMES and ag >= PRIOR_WINDOW_GAMES:
                blended = _build_variant_row(row, prior, mechanism, sandbox_matchup, "blend")
                if blended is None or not eligible_features(row):
                    continue
                late_total += 1
                max_abs = 0.0
                for feature in PREDICTION_V2_FEATURES:
                    delta = abs(float(blended[feature]) - float(row[feature]))
                    max_abs = max(max_abs, delta)
                late_max_abs = max(late_max_abs, max_abs)
                late_mismatches += int(max_abs > 1e-10)

        coverage[season] = {
            "early": early_total,
            "blend": early_blend,
            "prior": early_prior,
            "current": early_current,
        }
        print(
            f"  EARLY {season}: total={early_total} blend={early_blend} prior={early_prior} current_only={early_current}",
            flush=True,
        )

    return {
        "current": current,
        "blend": dict(blend),
        "prior": dict(prior_only),
        "currentOnly": dict(current_only),
        "coverage": coverage,
        "priorMap": prior_map,
        "lateReversionRows": late_total,
        "lateReversionMismatches": late_mismatches,
        "lateReversionMaxAbs": late_max_abs,
    }


def _by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("gameId")): row for row in rows}


def _common_rows(
    left: dict[int, list[dict[str, Any]]],
    right: dict[int, list[dict[str, Any]]],
    seasons: list[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left_out: list[dict[str, Any]] = []
    right_out: list[dict[str, Any]] = []
    for season in seasons:
        a = _by_id(left.get(season, []))
        b = _by_id(right.get(season, []))
        ids = sorted(set(a) & set(b))
        left_out.extend(a[gid] for gid in ids)
        right_out.extend(b[gid] for gid in ids)
    return left_out, right_out


def _fit_model(train: list[dict[str, Any]], features: tuple[str, ...]) -> dict[str, Any]:
    if not train:
        raise ValueError("Empty training sample in early-prior evaluation")
    return fit_generic(prepare_generic(train, features))


def _band(row: dict[str, Any]) -> str:
    week = int(row.get("week") or 0)
    return "W0-2" if week <= 2 else "W3-4"


def _score_subset(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, float] | None:
    return score_generic(model, rows) if rows else None


def evaluate(datasets: dict[str, Any]) -> list[dict[str, Any]]:
    blend = datasets["blend"]
    prior_only = datasets["prior"]
    current_only = datasets["currentOnly"]
    available = sorted(datasets["priorMap"])
    results: list[dict[str, Any]] = []

    for test_season in TEST_SEASONS:
        train_seasons = [season for season in available if season < test_season]
        train_blend, train_prior = _common_rows(blend, prior_only, train_seasons)
        test_blend, test_prior = _common_rows(blend, prior_only, [test_season])
        if {str(row.get("gameId")) for row in test_blend} != {str(row.get("gameId")) for row in test_prior}:
            raise ValueError(f"Blend/prior test sample mismatch for {test_season}")

        blend_model = _fit_model(train_blend, PREDICTION_V2_FEATURES)
        prior_model = _fit_model(train_prior, PREDICTION_V2_FEATURES)
        hfa_model = _fit_model(train_blend, BASELINE_FEATURES)
        blend_score = score_generic(blend_model, test_blend)
        prior_score = score_generic(prior_model, test_prior)
        hfa_score = score_generic(hfa_model, test_blend)

        train_blend_common, train_current = _common_rows(blend, current_only, train_seasons)
        test_blend_common, test_current = _common_rows(blend, current_only, [test_season])
        if test_blend_common and train_blend_common:
            blend_common_model = _fit_model(train_blend_common, PREDICTION_V2_FEATURES)
            current_model = _fit_model(train_current, PREDICTION_V2_FEATURES)
            blend_common_score = score_generic(blend_common_model, test_blend_common)
            current_score = score_generic(current_model, test_current)
        else:
            blend_common_score = None
            current_score = None

        bands: dict[str, dict[str, Any]] = {}
        prior_test_by_id = _by_id(test_prior)
        for label in ("W0-2", "W3-4"):
            b_rows = [row for row in test_blend if _band(row) == label]
            p_rows = [prior_test_by_id[str(row.get("gameId"))] for row in b_rows]
            b_score = _score_subset(blend_model, b_rows)
            p_score = _score_subset(prior_model, p_rows)
            if b_score and p_score:
                bands[label] = {
                    "n": int(b_score["n"]),
                    "deltaMaeVsPrior": b_score["mae"] - p_score["mae"],
                    "deltaRmseVsPrior": b_score["rmse"] - p_score["rmse"],
                }

        row: dict[str, Any] = {
            "season": test_season,
            "n": int(blend_score["n"]),
            "blendMae": blend_score["mae"],
            "blendRmse": blend_score["rmse"],
            "blendWinner": blend_score["winner"],
            "priorMae": prior_score["mae"],
            "priorRmse": prior_score["rmse"],
            "priorWinner": prior_score["winner"],
            "hfaMae": hfa_score["mae"],
            "hfaRmse": hfa_score["rmse"],
            "deltaMaeVsPrior": blend_score["mae"] - prior_score["mae"],
            "deltaRmseVsPrior": blend_score["rmse"] - prior_score["rmse"],
            "deltaWinnerVsPriorPP": (blend_score["winner"] - prior_score["winner"]) * 100.0,
            "deltaMaeVsHfa": blend_score["mae"] - hfa_score["mae"],
            "deltaRmseVsHfa": blend_score["rmse"] - hfa_score["rmse"],
            "bands": bands,
        }
        if blend_common_score and current_score:
            row.update(
                {
                    "currentCommonN": int(blend_common_score["n"]),
                    "deltaMaeVsCurrent": blend_common_score["mae"] - current_score["mae"],
                    "deltaRmseVsCurrent": blend_common_score["rmse"] - current_score["rmse"],
                    "deltaWinnerVsCurrentPP": (blend_common_score["winner"] - current_score["winner"]) * 100.0,
                }
            )
        results.append(row)
    return results


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if finite(row.get(key))]
    return sum(values) / len(values) if values else float("nan")


def summarize(results: list[dict[str, Any]], seasons: tuple[int, ...]) -> dict[str, Any]:
    rows = [row for row in results if int(row["season"]) in seasons]
    return {
        "folds": len(rows),
        "deltaMaeVsPrior": _mean(rows, "deltaMaeVsPrior"),
        "deltaRmseVsPrior": _mean(rows, "deltaRmseVsPrior"),
        "deltaWinnerVsPriorPP": _mean(rows, "deltaWinnerVsPriorPP"),
        "priorMaeWins": sum(float(row["deltaMaeVsPrior"]) < 0.0 for row in rows),
        "priorRmseWins": sum(float(row["deltaRmseVsPrior"]) < 0.0 for row in rows),
        "deltaMaeVsCurrent": _mean(rows, "deltaMaeVsCurrent"),
        "deltaRmseVsCurrent": _mean(rows, "deltaRmseVsCurrent"),
        "deltaWinnerVsCurrentPP": _mean(rows, "deltaWinnerVsCurrentPP"),
        "currentMaeWins": sum(finite(row.get("deltaMaeVsCurrent")) and float(row["deltaMaeVsCurrent"]) < 0.0 for row in rows),
        "currentRmseWins": sum(finite(row.get("deltaRmseVsCurrent")) and float(row["deltaRmseVsCurrent"]) < 0.0 for row in rows),
        "deltaMaeVsHfa": _mean(rows, "deltaMaeVsHfa"),
        "deltaRmseVsHfa": _mean(rows, "deltaRmseVsHfa"),
    }


def summarize_bands(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for label in ("W0-2", "W3-4"):
        rows = [row["bands"][label] for row in results if label in row.get("bands", {})]
        out[label] = {
            "folds": float(len(rows)),
            "deltaMaeVsPrior": _mean(rows, "deltaMaeVsPrior"),
            "deltaRmseVsPrior": _mean(rows, "deltaRmseVsPrior"),
        }
    return out


def promotion_gate(datasets: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    all_summary = summarize(results, TEST_SEASONS)
    recent_summary = summarize(results, RECENT_TEST_SEASONS)
    checks = {
        "late_features_revert_to_v2": datasets["lateReversionRows"] > 0 and datasets["lateReversionMismatches"] == 0,
        "all_mae_better_than_prior_only": all_summary["deltaMaeVsPrior"] < 0.0,
        "all_rmse_better_than_prior_only": all_summary["deltaRmseVsPrior"] < 0.0,
        "blend_mae_wins_vs_prior_at_least_4_of_6": all_summary["priorMaeWins"] >= 4,
        "blend_rmse_wins_vs_prior_at_least_4_of_6": all_summary["priorRmseWins"] >= 4,
        "recent_mae_not_worse_than_prior_only": recent_summary["deltaMaeVsPrior"] <= 0.0,
        "recent_rmse_not_worse_than_prior_only": recent_summary["deltaRmseVsPrior"] <= 0.0,
        "all_mae_better_than_current_only_common": all_summary["deltaMaeVsCurrent"] < 0.0,
        "all_rmse_better_than_current_only_common": all_summary["deltaRmseVsCurrent"] < 0.0,
        "recent_mae_not_worse_than_current_only_common": recent_summary["deltaMaeVsCurrent"] <= 0.0,
        "recent_rmse_not_worse_than_current_only_common": recent_summary["deltaRmseVsCurrent"] <= 0.0,
        "all_mae_better_than_hfa_baseline": all_summary["deltaMaeVsHfa"] < 0.0,
        "all_rmse_better_than_hfa_baseline": all_summary["deltaRmseVsHfa"] < 0.0,
    }
    return {
        "status": "PASS_2026_FREEZE_CANDIDATE" if all(checks.values()) else "NO_PROMOTION",
        "checks": checks,
        "all": all_summary,
        "recent": recent_summary,
        "bands": summarize_bands(results),
    }


def _fmt(value: Any, digits: int = 4) -> str:
    return f"{float(value):+.{digits}f}" if finite(value) else "N/A"


def main() -> None:
    root = project_root()
    datasets = build_datasets(root / "data" / "raw", root / "data" / "processed")
    results = evaluate(datasets)
    gate = promotion_gate(datasets, results)

    print("\nPREDICTION V2 EARLY-SEASON PRIOR CHALLENGER")
    print(f"Version: {CHALLENGER_VERSION}")
    print("Predeclared rule: four-game linear prior decay")
    print("  games before 0/1/2/3/4+ -> prior weight 1.00/0.75/0.50/0.25/0.00")
    print("  missing current component before Game 4 -> retain finite prior component")
    print("  adjacent season only; no 2019 -> 2021 bridge across missing 2020")
    print("  team state blended before matchup construction; HFA uses mean home/away prior weight")

    print("\nCOVERAGE")
    for season in sorted(datasets["coverage"]):
        row = datasets["coverage"][season]
        pct = row["blend"] / row["early"] if row["early"] else 0.0
        print(
            f" {season}: early={row['early']} blend={row['blend']} ({pct:.1%}) "
            f"prior_only={row['prior']} current_only={row['current']}"
        )
    print(
        f" Late v2 reversion rows={datasets['lateReversionRows']:,} "
        f"mismatches={datasets['lateReversionMismatches']:,} "
        f"max_abs={datasets['lateReversionMaxAbs']:.3e}"
    )

    print("\nOUTER FOLDS")
    print(" delta < 0 is better for MAE/RMSE")
    for row in results:
        print(
            f" {row['season']}: n={row['n']:3d} "
            f"blend MAE={row['blendMae']:.3f} RMSE={row['blendRmse']:.3f} "
            f"vs PRIOR dMAE={_fmt(row['deltaMaeVsPrior'])} dRMSE={_fmt(row['deltaRmseVsPrior'])} "
            f"| current-common n={row.get('currentCommonN', 0):3d} "
            f"dMAE={_fmt(row.get('deltaMaeVsCurrent'))} dRMSE={_fmt(row.get('deltaRmseVsCurrent'))} "
            f"| vs HFA dMAE={_fmt(row['deltaMaeVsHfa'])} dRMSE={_fmt(row['deltaRmseVsHfa'])}"
        )

    print("\nSUMMARY")
    for label, summary in (("ALL 6", gate["all"]), ("RECENT 3", gate["recent"])):
        print(
            f" {label}: vs PRIOR dMAE={_fmt(summary['deltaMaeVsPrior'])} "
            f"dRMSE={_fmt(summary['deltaRmseVsPrior'])} "
            f"wins={summary['priorMaeWins']}/{summary['folds']} MAE, {summary['priorRmseWins']}/{summary['folds']} RMSE"
        )
        print(
            f"          vs CURRENT common dMAE={_fmt(summary['deltaMaeVsCurrent'])} "
            f"dRMSE={_fmt(summary['deltaRmseVsCurrent'])} "
            f"| vs HFA dMAE={_fmt(summary['deltaMaeVsHfa'])} dRMSE={_fmt(summary['deltaRmseVsHfa'])}"
        )

    print("\nWEEK BANDS VS PRIOR-ONLY")
    for label, summary in gate["bands"].items():
        print(
            f" {label}: folds={int(summary['folds'])} "
            f"dMAE={_fmt(summary['deltaMaeVsPrior'])} dRMSE={_fmt(summary['deltaRmseVsPrior'])}"
        )

    print("\nPREDECLARED GATE")
    for name, passed in gate["checks"].items():
        print(f" {name}: {'PASS' if passed else 'FAIL'}")
    print(f"\nDECISION: {gate['status']}")
    if gate["status"] == "PASS_2026_FREEZE_CANDIDATE":
        print(
            "Historical development gate passed. Freeze this exact rule/architecture before 2026 outcomes; "
            "do not tune the carryover weights against 2026 if it is used as prospective validation."
        )
    else:
        print(
            "Do not promote or retune this exact four-game decay on the same holdouts. Treat the diagnostics as "
            "evidence for a materially new hypothesis only."
        )


if __name__ == "__main__":
    main()
