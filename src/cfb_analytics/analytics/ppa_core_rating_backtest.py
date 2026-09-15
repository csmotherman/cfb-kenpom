"""BACKTEST-ONLY, READ-ONLY: does an opponent-adjusted PPA-per-play rating
predict games better than the LIVE points-per-resolved-possession core
rating?

This script never modifies rating_model.py, iterative_ratings.py, or any
pipeline/publish script, and never writes to data/. It performs a real
walk-forward re-solve on real historical data -- not a linear-blend
approximation -- because a prior attempt in this project's history used a
fast approximation for a similar question and got a misleading answer that
did not survive a real re-solve.

Two opponent-adjusted models are compared, each fit with ITS OWN real,
currently-deployed production parameters (never a new/tuned value invented
for this backtest):

  * PossessionPoints -- rating_model.POSSESSION_SPEC =
        ("PossessionPoints", "offensiveDrivePoints", "resolvedPointPossessions")
    fit via iterative_ratings.fit_metric_ratings with
        shrinkage=rating_model.RIDGE_EQUIVALENT_POSSESSIONS (10.0),
        damping=1.0, tolerance=1e-9, max_iterations=10000
    -- the exact call rating_model._fit_possession_efficiency makes today
    for the LIVE published AdjOff/AdjDef/AdjNet rating. prior_weight is
    always 0 here (no tapered prior-season-opponent blend), isolating "which
    per-game metric" as the only variable under test.

  * EPA -- iterative_ratings.SPECS's ("EPA", "epaSum", "epaPlays")
    fit via the SAME fit_metric_ratings with its bare default shrinkage=50.0
    -- the value every real caller of fit_all_ratings/build_iterative_rating_
    snapshots in this repo uses today (grep-confirmed against
    historical_tournament.py, historical_power.py, both
    prediction_v2_early_prior_* scripts, prediction_v2_2026_features.py, and
    scripts/build_real_data.py).

ROW SOURCE. data/canonical/season={season}/team_games.json is used as the
single row source for both specs. It carries classification,
opponent_classification, home_away, neutral_site, points_for/points_against,
and epaSum/epaPlays for every team-game already -- spot-checked byte-
identical to the epaSum/epaPlays iterative_ratings.py's own production EPA
fit consumes via derived/pregame.load_team_games (which reads the separate,
lower-information data/processed/derived/games/... team_games.json layer
that carries no classification field at all). offensiveDrivePoints/
resolvedPointPossessions are not stored anywhere on disk; they are attached
exactly the way rating_model.py's own live pipeline attaches them, by
calling the read-only, cached rating_model._drive_rating_fields(season)
lookup (no rows are ever hand-parsed from raw CFBD data here).

POPULATION CAVEAT. Both specs here are restricted to the closed FBS-vs-FBS
graph (classification == opponent_classification == "fbs"), matching
POSSESSION_SPEC's real production restriction (rating_model.
_validated_model_rows enforces exactly this). iterative_ratings.py's OWN
production EPA fit (the live predictions-model feature) does NOT enforce
this -- derived/games.py's team_games.json carries no classification field,
so that production fit includes FCS opponents' individual rows too. This
backtest deliberately restricts EPA to the same closed graph POSSESSION_SPEC
already uses, so the comparison isolates "which metric" and not "which
population of games." See the report for this caveat spelled out again.

WALK-FORWARD DESIGN. Follows iterative_ratings.build_iterative_rating_
snapshots's own pattern exactly: partition each season's team-games by
derived.pregame._pk (season-type/week), and for every partition IN ORDER,
fit both specs using ONLY strictly-prior partitions ("history"), snapshot
predictions for every game in the current partition, THEN append the
current partition to history. No cross-season carryover; no prior-season
blending (prior_weight=0 always, matching rating_model.py's own
"current-season-only, no taper" configuration).

SCORING. Winner accuracy (the PRIMARY, trusted metric) needs no unit
conversion: each model's rating differential for a game is
    (offense_home + defense_home) - (offense_away + defense_away)
i.e. each team's own AdjNet-equivalent net rating (offense effect plus
defense effect, both already on that spec's own centered scale) minus the
opponent's -- the natural per-model analogue of AdjNet = AdjOff + AdjDef.
Winner accuracy is simply sign(rating_diff) == sign(actual_margin), scored
per model independently.

Margin MAE/RMSE (SECONDARY) requires converting each model's own unitless
rating differential into real points. This is done with a one-parameter,
through-the-origin least-squares scale y = k * rating_diff, refit at EVERY
weekly walk-forward cutoff using an EXPANDING window of (rating_diff,
actual_margin) pairs from that season's own STRICTLY PRIOR games only (the
rating_diff values in that window were themselves computed leakage-safe, at
the time, by this same walk-forward loop) -- so the scaling coefficient
itself never peeks at a future game either. A cutoff needs at least
MIN_SCALING_PAIRS prior pairs before a margin prediction is attempted;
before that, the game contributes to winner accuracy only.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics import rating_model
from cfb_analytics.analytics.iterative_ratings import SPECS, fit_metric_ratings
from cfb_analytics.derived.pregame import _pk

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
EXTRA_SEASONS = (2026,)  # in-progress; included if data exists, never required

POSSESSION_SPEC = rating_model.POSSESSION_SPEC
POSSESSION_SHRINKAGE = rating_model.RIDGE_EQUIVALENT_POSSESSIONS  # 10.0, live production
EPA_SPEC = next(spec for spec in SPECS if spec[0] == "EPA")
EPA_SHRINKAGE = 50.0  # fit_metric_ratings' bare default; every real caller uses it unmodified

MIN_SCALING_PAIRS = 5
BUCKET_ORDER = ("0", "1-2", "3-5", "6+")


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _bucket(min_games_before: int) -> str:
    if min_games_before <= 0:
        return "0"
    if min_games_before <= 2:
        return "1-2"
    if min_games_before <= 5:
        return "3-5"
    return "6+"


def load_canonical_team_games(season: int) -> list[dict[str, Any]]:
    """FBS-vs-FBS, completed, canonical team-game rows for one season.

    Read-only load of data/canonical/season={season}/team_games.json -- the
    validated canonical layer, not a hand-parse of raw CFBD data.
    """
    path = REPO_ROOT / f"data/canonical/season={season}/team_games.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text())
    return [
        r
        for r in rows
        if r.get("classification") == "fbs"
        and r.get("opponent_classification") == "fbs"
        and r.get("completed") is True
        and r.get("home_away") in ("home", "away")
        and str(r.get("season_type") or r.get("seasonType") or "").lower() in ("regular", "postseason")
    ]


def attach_possession_fields(rows: list[dict[str, Any]], season: int) -> tuple[list[dict[str, Any]], int]:
    """Attach offensiveDrivePoints/resolvedPointPossessions the same way
    rating_model.py's live pipeline does: a read-only lookup into
    rating_model._drive_rating_fields(season), never a re-derivation.

    A team-game with no drive-PPD entry gets zero/zero (exactly
    composite_input_row's own fallback), which fit_metric_ratings'
    _observations() skips (weight <= 0) -- present in the graph, zero
    statistical weight. Returns (rows, missing_count) for the caveat report.
    """
    try:
        drive_fields = rating_model._drive_rating_fields(season)
    except rating_model.RatingModelError:
        drive_fields = {}
    missing = 0
    out = []
    for r in rows:
        row = dict(r)
        key = (str(row.get("gameId")), str(row.get("team")))
        df = drive_fields.get(key)
        if df is None:
            row["offensiveDrivePoints"] = 0.0
            row["resolvedPointPossessions"] = 0.0
            missing += 1
        else:
            row.update(df)
        out.append(row)
    return out, missing


def pair_games(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One entry per real, two-sided FBS-vs-FBS game: home row, away row,
    and the actual final margin (home points - away points)."""
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_game[str(r.get("gameId"))].append(r)
    games = {}
    for gid, pair in by_game.items():
        if len(pair) != 2:
            continue
        home = next((r for r in pair if r.get("home_away") == "home"), None)
        away = next((r for r in pair if r.get("home_away") == "away"), None)
        if home is None or away is None:
            continue
        pf, pa = home.get("points_for"), home.get("points_against")
        if not (_num(pf) and _num(pa)):
            continue
        games[gid] = {"home": home, "away": away, "margin": float(pf) - float(pa)}
    return games


def _net_diff(fit: dict[str, Any], home_team: str, away_team: str):
    """(offense+defense)[home] - (offense+defense)[away]: the natural,
    model-agnostic analogue of AdjNet = AdjOff + AdjDef, in that spec's own
    centered units."""
    offense, defense = fit.get("offense", {}), fit.get("defense", {})
    ho, hd = offense.get(home_team), defense.get(home_team)
    ao, ad = offense.get(away_team), defense.get(away_team)
    if not (_num(ho) and _num(hd) and _num(ao) and _num(ad)):
        return None
    return (float(ho) + float(hd)) - (float(ao) + float(ad))


def _fit_k(pairs: list[tuple[float, float]]):
    """Through-the-origin least squares y = k * x."""
    if len(pairs) < MIN_SCALING_PAIRS:
        return None
    sxx = sum(x * x for x, _ in pairs)
    if sxx <= 0:
        return None
    sxy = sum(x * y for x, y in pairs)
    return sxy / sxx


def run_season(season: int) -> dict[str, Any]:
    raw = load_canonical_team_games(season)
    if not raw:
        return {"season": season, "games": [], "missingDriveRows": 0, "nonconvergences": []}
    rows, missing_drive = attach_possession_fields(raw, season)
    games = pair_games(rows)

    partitions: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        partitions[_pk(r)].append(r)

    games_by_pk: dict[tuple[int, int], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for gid, g in games.items():
        games_by_pk[_pk(g["home"])].append((gid, g))

    history: list[dict[str, Any]] = []
    games_played: Counter[str] = Counter()
    poss_pairs: list[tuple[float, float]] = []
    epa_pairs: list[tuple[float, float]] = []
    results: list[dict[str, Any]] = []
    nonconvergences: list[dict[str, Any]] = []

    for key in sorted(partitions):
        poss_fit = (
            fit_metric_ratings(
                history, POSSESSION_SPEC,
                shrinkage=POSSESSION_SHRINKAGE, damping=1.0,
                tolerance=1e-9, max_iterations=10000,
            )
            if history else None
        )
        epa_fit = (
            fit_metric_ratings(history, EPA_SPEC, shrinkage=EPA_SHRINKAGE)
            if history else None
        )
        if poss_fit is not None and not poss_fit.get("converged"):
            nonconvergences.append({"season": season, "pk": key, "spec": "PossessionPoints"})
        if epa_fit is not None and not epa_fit.get("converged"):
            nonconvergences.append({"season": season, "pk": key, "spec": "EPA"})

        k_poss = _fit_k(poss_pairs)
        k_epa = _fit_k(epa_pairs)

        for gid, g in sorted(games_by_pk.get(key, [])):
            home_team, away_team = g["home"]["team"], g["away"]["team"]
            margin = g["margin"]
            home_gp, away_gp = games_played[home_team], games_played[away_team]
            poss_diff = _net_diff(poss_fit, home_team, away_team) if poss_fit else None
            epa_diff = _net_diff(epa_fit, home_team, away_team) if epa_fit else None

            results.append({
                "season": season,
                "gameId": gid,
                "pk": key,
                "minGamesBefore": min(home_gp, away_gp),
                "actualMargin": margin,
                "possDiff": poss_diff,
                "epaDiff": epa_diff,
                "possMarginPred": (k_poss * poss_diff) if (k_poss is not None and poss_diff is not None) else None,
                "epaMarginPred": (k_epa * epa_diff) if (k_epa is not None and epa_diff is not None) else None,
            })

            if poss_diff is not None:
                poss_pairs.append((poss_diff, margin))
            if epa_diff is not None:
                epa_pairs.append((epa_diff, margin))

        for r in partitions[key]:
            games_played[str(r.get("team"))] += 1
        history.extend(partitions[key])

    return {
        "season": season,
        "games": results,
        "missingDriveRows": missing_drive,
        "nonconvergences": nonconvergences,
    }


def _winner_stats(results: list[dict[str, Any]], key: str, require_min_games: bool) -> dict[str, Any]:
    n = correct = 0
    for r in results:
        if require_min_games and r["minGamesBefore"] < 1:
            continue
        diff = r[key]
        margin = r["actualMargin"]
        if diff is None or margin == 0:
            continue
        n += 1
        correct += int((diff > 0) == (margin > 0))
    return {"n": n, "accuracy": (correct / n) if n else None}


def _margin_stats(results: list[dict[str, Any]], key: str, require_min_games: bool) -> dict[str, Any]:
    errs = []
    for r in results:
        if require_min_games and r["minGamesBefore"] < 1:
            continue
        pred = r[key]
        if pred is None:
            continue
        errs.append(pred - r["actualMargin"])
    if not errs:
        return {"n": 0, "mae": None, "rmse": None}
    n = len(errs)
    mae = sum(abs(e) for e in errs) / n
    rmse = math.sqrt(sum(e * e for e in errs) / n)
    return {"n": n, "mae": mae, "rmse": rmse}


def aggregate(all_results: list[dict[str, Any]]) -> dict[str, Any]:
    overall = {
        "possWinner": _winner_stats(all_results, "possDiff", require_min_games=True),
        "epaWinner": _winner_stats(all_results, "epaDiff", require_min_games=True),
        "possMargin": _margin_stats(all_results, "possMarginPred", require_min_games=True),
        "epaMargin": _margin_stats(all_results, "epaMarginPred", require_min_games=True),
        "zeroGamesInformational": {
            "possWinner": _winner_stats([r for r in all_results if r["minGamesBefore"] == 0], "possDiff", False),
            "epaWinner": _winner_stats([r for r in all_results if r["minGamesBefore"] == 0], "epaDiff", False),
        },
    }
    by_bucket = {}
    for bucket in BUCKET_ORDER:
        rows = [r for r in all_results if _bucket(r["minGamesBefore"]) == bucket]
        require = bucket != "0"
        by_bucket[bucket] = {
            "n": len(rows),
            "possWinner": _winner_stats(rows, "possDiff", require),
            "epaWinner": _winner_stats(rows, "epaDiff", require),
            "possMargin": _margin_stats(rows, "possMarginPred", require),
            "epaMargin": _margin_stats(rows, "epaMarginPred", require),
        }
    return {"overall": overall, "byBucket": by_bucket}


def run_backtest(seasons=DEFAULT_SEASONS, extra_seasons=EXTRA_SEASONS) -> dict[str, Any]:
    per_season = []
    all_results: list[dict[str, Any]] = []
    total_missing_drive = 0
    all_nonconvergences = []
    for season in list(seasons) + list(extra_seasons):
        result = run_season(season)
        if not result["games"]:
            continue
        per_season.append(result)
        all_results.extend(result["games"])
        total_missing_drive += result["missingDriveRows"]
        all_nonconvergences.extend(result["nonconvergences"])

    per_season_summary = []
    for result in per_season:
        season = result["season"]
        eligible = [r for r in result["games"] if r["minGamesBefore"] >= 1]
        per_season_summary.append({
            "season": season,
            "totalGames": len(result["games"]),
            "eligibleGames": len(eligible),
            "possWinner": _winner_stats(eligible, "possDiff", False),
            "epaWinner": _winner_stats(eligible, "epaDiff", False),
            "missingDriveRows": result["missingDriveRows"],
            "nonconvergences": len(result["nonconvergences"]),
        })

    return {
        "seasons": [r["season"] for r in per_season],
        "totalGames": len(all_results),
        "perSeason": per_season_summary,
        "aggregate": aggregate(all_results),
        "missingDriveRows": total_missing_drive,
        "nonconvergences": all_nonconvergences,
    }


def _fmt_pct(x):
    return f"{x:.1%}" if x is not None else "n/a"


def _fmt_num(x, nd=2):
    return f"{x:.{nd}f}" if x is not None else "n/a"


def concise(report: dict[str, Any]) -> str:
    lines = [
        "PPA-PER-PLAY vs LIVE POSSESSION-EFFICIENCY: WALK-FORWARD BACKTEST",
        f"Seasons: {report['seasons']}",
        f"Total FBS-vs-FBS games scored: {report['totalGames']:,}",
        f"Team-game rows with no drive-PPD data (zero-weighted): {report['missingDriveRows']:,}",
        f"Solver non-convergences: {len(report['nonconvergences']):,}",
        "",
        "-- Per season (min 1 prior game each side) --",
    ]
    for s in report["perSeason"]:
        lines.append(
            f"{s['season']}: games={s['totalGames']:>4} eligible={s['eligibleGames']:>4} "
            f"poss_acc={_fmt_pct(s['possWinner']['accuracy'])} epa_acc={_fmt_pct(s['epaWinner']['accuracy'])} "
            f"missing_drive={s['missingDriveRows']} nonconv={s['nonconvergences']}"
        )

    agg = report["aggregate"]
    lines += ["", "-- Overall (min 1 prior game each side) --"]
    ov = agg["overall"]
    lines.append(
        f"Winner accuracy: possession n={ov['possWinner']['n']:,} acc={_fmt_pct(ov['possWinner']['accuracy'])} | "
        f"EPA n={ov['epaWinner']['n']:,} acc={_fmt_pct(ov['epaWinner']['accuracy'])}"
    )
    lines.append(
        f"Margin MAE/RMSE: possession n={ov['possMargin']['n']:,} mae={_fmt_num(ov['possMargin']['mae'])} rmse={_fmt_num(ov['possMargin']['rmse'])} | "
        f"EPA n={ov['epaMargin']['n']:,} mae={_fmt_num(ov['epaMargin']['mae'])} rmse={_fmt_num(ov['epaMargin']['rmse'])}"
    )
    zg = ov["zeroGamesInformational"]
    lines.append(
        f"[informational only, 0 prior games either side] poss n={zg['possWinner']['n']} acc={_fmt_pct(zg['possWinner']['accuracy'])} | "
        f"EPA n={zg['epaWinner']['n']} acc={_fmt_pct(zg['epaWinner']['accuracy'])}"
    )

    lines += ["", "-- By games-played-before bucket (min of the two teams) --"]
    for bucket in BUCKET_ORDER:
        b = agg["byBucket"][bucket]
        lines.append(
            f"[{bucket:>4}] n={b['n']:>5} | "
            f"poss acc={_fmt_pct(b['possWinner']['accuracy']):>7} mae={_fmt_num(b['possMargin']['mae']):>6} rmse={_fmt_num(b['possMargin']['rmse']):>6} | "
            f"EPA  acc={_fmt_pct(b['epaWinner']['accuracy']):>7} mae={_fmt_num(b['epaMargin']['mae']):>6} rmse={_fmt_num(b['epaMargin']['rmse']):>6}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, nargs="*", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    seasons = args.seasons if args.seasons else DEFAULT_SEASONS
    extra = () if args.seasons else EXTRA_SEASONS
    report = run_backtest(seasons=seasons, extra_seasons=extra)
    print(concise(report))
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
