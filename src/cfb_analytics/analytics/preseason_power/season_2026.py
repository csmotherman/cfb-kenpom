"""Full 2026 regular-season projections from the frozen preseason power rating.

This holds each team's PRESEASON power fixed for the whole season (it is not
updated week-to-week with 2026 results as they happen -- that would be a
different, in-season model, out of scope for this preseason-only research
track). It is a "what would we have projected before Game 1" view of the
full season, exactly like a preseason win-total, not a live in-season
predictor. Reads the full 2026 schedule read-only from
data/raw/cfbd_directory/season=2026/games.json (public schedule fields only:
teams, week, neutral-site, classification) -- writes nothing there and
nothing under prospective/2026/.
"""
from __future__ import annotations

import json

import numpy as np

from .common import RAW_ROOT, RESEARCH_OUTPUT_ROOT, write_csv, write_json
from .demo_2026 import FINAL_FEATURES, build_2026_ratings
from .model import HOME_FIELD_FEATURE


def load_2026_regular_season_schedule() -> list[dict]:
    path = RAW_ROOT / "cfbd_directory" / "season=2026" / "games.json"
    payload = json.loads(path.read_text())
    rows = payload.get("payload", payload) if isinstance(payload, dict) else payload
    out = []
    for g in rows:
        if g.get("seasonType") != "regular":
            continue
        if g.get("homeClassification") != "fbs" or g.get("awayClassification") != "fbs":
            continue
        out.append({
            "week": g["week"], "home": g["homeTeam"], "away": g["awayTeam"],
            "neutral": bool(g.get("neutralSite")), "gameId": g["id"],
            "homeConference": g.get("homeConference"), "awayConference": g.get("awayConference"),
        })
    return out


def project_team_season(team: str, ratings_by_team: dict[str, dict], coef: dict[str, float], residual_pool: np.ndarray, n_sims: int = 30000, seed: int = 11) -> list[dict]:
    schedule = [g for g in load_2026_regular_season_schedule() if g["home"] == team or g["away"] == team]
    schedule.sort(key=lambda g: g["week"])
    rng = np.random.default_rng(seed)
    out = []
    for g in schedule:
        is_home = g["home"] == team
        opponent = g["away"] if is_home else g["home"]
        team_r = ratings_by_team.get(team)
        opp_r = ratings_by_team.get(opponent)
        if not team_r or not opp_r or team_r["power_score_full_model"] is None or opp_r["power_score_full_model"] is None:
            out.append({"week": g["week"], "opponent": opponent, "gameId": g["gameId"], "site": "neutral" if g["neutral"] else ("home" if is_home else "away"), "data_available": False})
            continue
        team_power = team_r["power_score_full_model"]
        opp_power = opp_r["power_score_full_model"]
        margin_for_team = team_power - opp_power
        if not g["neutral"]:
            margin_for_team += coef[HOME_FIELD_FEATURE] if is_home else -coef[HOME_FIELD_FEATURE]
        sims = margin_for_team - rng.choice(residual_pool, size=n_sims, replace=True)
        win_prob = float((sims > 0).mean())
        out.append({
            "week": g["week"], "opponent": opponent, "gameId": g["gameId"],
            "site": "neutral" if g["neutral"] else ("home" if is_home else "away"),
            "opponent_rank": opp_r.get("rank"),
            "predicted_margin": round(margin_for_team, 1),
            "win_prob": round(win_prob, 3),
            "median_margin": round(float(np.median(sims)), 1),
            "p10_margin": round(float(np.percentile(sims, 10)), 1),
            "p90_margin": round(float(np.percentile(sims, 90)), 1),
            "data_available": True,
        })
    return out


def season_win_distribution(game_projections: list[dict], n_sims: int = 50000, seed: int = 13) -> dict:
    probs = [g["win_prob"] for g in game_projections if g.get("data_available")]
    rng = np.random.default_rng(seed)
    draws = rng.random((n_sims, len(probs))) < np.array(probs)
    win_totals = draws.sum(axis=1)
    values, counts = np.unique(win_totals, return_counts=True)
    dist = {int(v): round(100 * c / n_sims, 1) for v, c in zip(values, counts)}
    return {
        "games_with_data": len(probs),
        "expected_wins": round(float(sum(probs)), 2),
        "win_total_distribution_pct": dist,
        "median_wins": int(np.median(win_totals)),
        "prob_undefeated": round(100 * float((win_totals == len(probs)).mean()), 2) if probs else None,
    }


def main(team: str = "Michigan") -> None:
    print(f"Building 2026 preseason ratings and projecting {team}'s full regular season...")
    ratings, coef = build_2026_ratings()
    ratings_by_team = {r["team"]: r for r in ratings}

    from .backtest_week1 import walk_forward_predict
    from .model import build_feature_registry

    registry = build_feature_registry(shrinkage=0.0)
    preds, _ = walk_forward_predict(FINAL_FEATURES, registry, alpha=5.0)
    residual_pool = np.array([p.predicted_margin - p.actual_margin for p in preds])

    games = project_team_season(team, ratings_by_team, coef, residual_pool)
    slug = team.lower().replace(" ", "-").replace("'", "")
    write_csv(RESEARCH_OUTPUT_ROOT / f"season_2026_{slug}_game_by_game.csv", games, list(games[0].keys()))

    win_dist = season_win_distribution(games)
    write_json(RESEARCH_OUTPUT_ROOT / f"season_2026_{slug}_win_distribution.json", win_dist)

    print(f"\n{team} 2026 projected schedule ({win_dist['games_with_data']} games with data):")
    for g in games:
        if not g.get("data_available"):
            print(f"  Wk{g['week']:>2} vs {g['opponent']:20s} -- no rating available")
            continue
        site = {"home": "vs", "away": "at", "neutral": "vs (N)"}[g["site"]]
        print(f"  Wk{g['week']:>2} {site} {g['opponent']:20s} (#{g['opponent_rank']:<3}) "
              f"proj margin {g['predicted_margin']:+6.1f}  win prob {g['win_prob']*100:5.1f}%")
    print(f"\nExpected wins: {win_dist['expected_wins']} / {win_dist['games_with_data']}")
    print("Win total distribution (%):", win_dist["win_total_distribution_pct"])


if __name__ == "__main__":
    main()
