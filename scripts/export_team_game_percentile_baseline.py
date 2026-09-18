"""Build the compact historical FBS single-game percentile baseline used by
completed-game conditional formatting.

Historical team_game_advanced payloads stay private in Supabase. This script
reads those private season payloads plus an optional freshly-built local current
season, reduces them to p10/p30/p70/p90 cut points, and writes only those
aggregate thresholds into the public Next.js source tree. Raw historical rows
are never published to the browser.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from urllib.parse import urlencode

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from hydrate_premium_data import config, fetch_json  # noqa: E402

OUTPUT = REPO / "web" / "lib" / "team-game-percentile-baseline.ts"
LOCAL_TEAM_GAME_DIR = REPO / "web" / "public" / "data" / "team-game-advanced"

# The direction belongs to the metric definition, not to an individual UI row.
# That prevents accidental inversions such as treating a negative EPA loss as
# "lower is better" when values closer to zero are actually better.
METRICS: dict[str, bool] = {
    "epa_per_play": False,
    "success_rate": False,
    "total_epa": False,
    "passing_epa": False,
    "epa_per_dropback": False,
    "pass_success_rate": False,
    "yards_per_dropback": False,
    "rushing_epa": False,
    "epa_per_rush": False,
    "rush_success_rate": False,
    "yards_per_rush": False,
    "down1_epa": False,
    "down1_epa_pass": False,
    "down1_epa_rush": False,
    "down2_epa": False,
    "down2_epa_pass": False,
    "down2_epa_rush": False,
    "down3_epa": False,
    "down3_epa_pass": False,
    "down3_epa_rush": False,
    "yards_per_drive": False,
    "points_per_opportunity": False,
    "series_conversion_rate": False,
    "recovery_rate": False,
    "third_long_exposure": True,
    "scoring_opportunity_touchdown_rate": False,
    "explosive_play_rate": False,
    "explosive_pass_rate": False,
    "explosive_rush_rate": False,
    "epa_without_explosives": False,
    "clean_drive_rate": False,
    "drive_killer_rate": True,
    "failure_rate": True,
    "avg_failure_damage": True,
    "failure_burden": True,
    # Failure Pressure is the opponent's offensive failure damage mirrored
    # onto this team, so more pressure created is better.
    "failure_pressure": False,
    "havoc_allowed": True,
    "turnover_rate": True,
    # Stored as negative EPA lost. -3 is better than -15, so higher is better.
    "turnover_epa_lost": False,
    "penalty_rate": True,
    "penalty_yards_per_drive": True,
}


def percentile_cont(values: list[float], q: float) -> float:
    """PostgreSQL percentile_cont-compatible linear interpolation."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile_cont requires at least one value")
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def private_catalog(base_url: str, secret: str) -> list[int]:
    query = urlencode(
        {
            "select": "season",
            "dataset_type": "eq.team_game_advanced",
            "week": "eq.0",
            "order": "season.asc",
        },
        safe=",.",
    )
    rows = fetch_json(base_url, secret, f"/rest/v1/premium_datasets?{query}")
    return sorted({int(row["season"]) for row in rows})


def fetch_private_payload(base_url: str, secret: str, season: int) -> dict:
    query = urlencode(
        {
            "select": "payload",
            "dataset_type": "eq.team_game_advanced",
            "season": f"eq.{season}",
            "week": "eq.0",
            "limit": "1",
        },
        safe=",.",
    )
    rows = fetch_json(base_url, secret, f"/rest/v1/premium_datasets?{query}")
    if len(rows) != 1 or not isinstance(rows[0].get("payload"), dict):
        raise RuntimeError(f"Expected one team_game_advanced payload for {season}")
    return rows[0]["payload"]


def load_local_payload(season: int) -> dict | None:
    path = LOCAL_TEAM_GAME_DIR / f"{season}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid local team_game_advanced payload: {path}")
    return payload


def build_baseline(payloads: dict[int, dict]) -> dict:
    values: dict[str, list[float]] = {key: [] for key in METRICS}
    fbs_team_games = 0

    for payload in payloads.values():
        for row in payload.get("rows", []):
            if not isinstance(row, dict):
                continue
            if row.get("classification") != "fbs" or row.get("opponent_classification") != "fbs":
                continue
            fbs_team_games += 1
            for key in METRICS:
                value = row.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    values[key].append(float(value))

    metrics = {}
    for key, lower_better in METRICS.items():
        population = values[key]
        if not population:
            continue
        metric = {
            "n": len(population),
            "p10": percentile_cont(population, 0.10),
            "p30": percentile_cont(population, 0.30),
            "p70": percentile_cont(population, 0.70),
            "p90": percentile_cont(population, 0.90),
        }
        if lower_better:
            metric["lowerBetter"] = True
        metrics[key] = metric

    return {
        "seasons": sorted(payloads),
        "fbsTeamGames": fbs_team_games,
        "fbsGames": fbs_team_games // 2,
        "metrics": metrics,
    }


def render_typescript(baseline: dict) -> str:
    body = json.dumps(baseline, indent=2, sort_keys=False, allow_nan=False)
    return f'''export type TeamGamePercentileBaselineMetric = {{
  n: number;
  p10: number;
  p30: number;
  p70: number;
  p90: number;
  lowerBetter?: boolean;
}};

/**
 * Generated historical single-game conditional-formatting baseline.
 * Raw historical team-game rows remain private; only aggregate percentile
 * cut points are committed here.
 */
export const TEAM_GAME_PERCENTILE_BASELINE = {body} as const satisfies {{
  seasons: readonly number[];
  fbsTeamGames: number;
  fbsGames: number;
  metrics: Record<string, TeamGamePercentileBaselineMetric>;
}};

export type TeamGamePercentileBaselineKey = keyof typeof TEAM_GAME_PERCENTILE_BASELINE.metrics;
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--current-season",
        type=int,
        help="Use this season's freshly exported local payload in place of the stored Supabase copy.",
    )
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    base_url, secret = config()
    seasons = private_catalog(base_url, secret)
    payloads: dict[int, dict] = {}
    for season in seasons:
        if args.current_season == season:
            local = load_local_payload(season)
            if local is None:
                raise FileNotFoundError(
                    f"Current-season team_game_advanced export is missing: {LOCAL_TEAM_GAME_DIR / f'{season}.json'}"
                )
            payloads[season] = local
        else:
            payloads[season] = fetch_private_payload(base_url, secret, season)

    if args.current_season is not None and args.current_season not in payloads:
        local = load_local_payload(args.current_season)
        if local is None:
            raise FileNotFoundError(
                f"Current-season team_game_advanced export is missing: {LOCAL_TEAM_GAME_DIR / f'{args.current_season}.json'}"
            )
        payloads[args.current_season] = local

    baseline = build_baseline(payloads)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_typescript(baseline))
    print(
        f"Historical game percentile baseline: {baseline['fbsTeamGames']:,} FBS team-games "
        f"across {len(baseline['seasons'])} seasons -> {args.out}"
    )


if __name__ == "__main__":
    main()
