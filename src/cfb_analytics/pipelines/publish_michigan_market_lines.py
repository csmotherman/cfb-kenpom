"""Publish sourced 2026 Michigan spreads with historically calibrated win chances."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def fit_logistic(rows: list[dict[str, Any]]) -> tuple[float, float]:
    """Fit home win ~ market home margin with Newton-Raphson."""
    x = [float(row["marketHomeMargin"]) for row in rows]
    y = [1.0 if float(row["actualHomeMargin"]) > 0 else 0.0 for row in rows]
    intercept = slope = 0.0
    for _ in range(30):
        probabilities = [1 / (1 + math.exp(-(intercept + slope * value))) for value in x]
        weights = [max(probability * (1 - probability), 1e-9) for probability in probabilities]
        g0 = sum(target - probability for target, probability in zip(y, probabilities))
        g1 = sum(value * (target - probability) for value, target, probability in zip(x, y, probabilities))
        h00 = sum(weights); h01 = sum(weight * value for weight, value in zip(weights, x)); h11 = sum(weight * value * value for weight, value in zip(weights, x))
        determinant = h00 * h11 - h01 * h01
        delta0 = (g0 * h11 - g1 * h01) / determinant
        delta1 = (g1 * h00 - g0 * h01) / determinant
        intercept += delta0; slope += delta1
        if abs(delta0) + abs(delta1) < 1e-10:
            break
    return intercept, slope


def build(source: dict[str, Any], history: list[dict[str, Any]], schedule: list[dict[str, Any]]) -> dict[str, Any]:
    intercept, slope = fit_logistic(history)
    schedule_by_id = {str(game["id"]): game for game in schedule}
    games = []
    for line in source["lines"]:
        game = schedule_by_id[str(line["gameId"])]
        michigan_home = int(game["homeId"]) == 130
        team_margin = -float(line["teamSpread"])
        home_margin = team_margin if michigan_home else -team_margin
        home_probability = 1 / (1 + math.exp(-(intercept + slope * home_margin)))
        team_probability = home_probability if michigan_home else 1 - home_probability
        games.append({
            **line, "week": game["week"], "marketWinChance": round(team_probability, 4),
            "valueType": "MARKET", "asOf": source["acquiredAt"], "source": source["source"],
            "probabilityMethod": "logistic calibration of 2018-2025 clean closing spread to straight-up home result",
        })
    return {"season": source["season"], "team": source["team"], "valueType": "MARKET", "calibration":{"intercept":intercept,"slope":slope,"games":len(history)}, "games":games}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/raw/market_lines/2026-michigan-preseason.json"))
    parser.add_argument("--history", type=Path, default=Path("data/processed/market_benchmark/prediction-v2-vs-clean-market-games.json"))
    parser.add_argument("--schedule", type=Path, default=Path("data/published/2026/michigan/schedule.json"))
    parser.add_argument("--output", type=Path, default=Path("data/published/2026/michigan/market-lines.json"))
    args = parser.parse_args()
    result = build(json.loads(args.source.read_text()), json.loads(args.history.read_text()), json.loads(args.schedule.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status":"PASS","games":len(result["games"]),"output":str(args.output)}))


if __name__ == "__main__":
    main()
