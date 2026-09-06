from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .dataset import (
    collect_published_team_games,
    fit_all_metrics,
    fit_metric_from_rows,
    venue_from_team_game,
)
from .game_analysis import VALIDATED_GAME_METRICS
from .specs import METRIC_SPECS, MetricSpec

ANALYTICS_LAB_VERSION = "opponent-adjusted-analytics-lab-v1"
DEFAULT_RIDGE = 40.0
DEFAULT_HOME_RIDGE = 20.0

DEFENSE_WEIGHT_FIELDS: dict[str, str] = {
    "successRate": "successEligiblePlaysAllowed",
    "rushSuccessRate": "rushSuccessEligiblePlaysAllowed",
    "passSuccessRate": "passSuccessEligiblePlaysAllowed",
    "explosivePlayRate": "explosiveEligiblePlaysAllowed",
    "yardsPerPlay": "basicYardagePlaysFaced",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _game_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("gameId", row.get("game_id"))
    return str(value) if value is not None else None


def _team_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("team_id")
    if value is not None and not isinstance(value, bool):
        return str(value)
    name = row.get("team")
    return str(name) if isinstance(name, str) and name.strip() else None


def _opponent_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("opponent_id")
    if value is not None and not isinstance(value, bool):
        return str(value)
    name = row.get("opponent")
    return str(name) if isinstance(name, str) and name.strip() else None


def _phase(row: Mapping[str, Any]) -> int:
    season_type = str(row.get("seasonType", row.get("season_type", "regular")) or "regular").lower()
    return 0 if season_type in {"regular", "regular_season"} else 1


def partition_order(row: Mapping[str, Any]) -> int:
    week = row.get("week")
    resolved_week = int(week) if isinstance(week, int) else 99
    return _phase(row) * 100 + resolved_week


def _raw_metric(row: Mapping[str, Any], spec: MetricSpec) -> tuple[float | None, float | None]:
    numerator = spec.numerator_value(row)
    denominator = _number(row.get(spec.denominator_field))
    if numerator is None or denominator is None or denominator <= 0:
        return None, None
    return float(numerator / denominator), float(denominator)


def _metric_meta(metric_names: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "k": name,
            "l": METRIC_SPECS[name].label,
            "u": METRIC_SPECS[name].unit,
            "f": METRIC_SPECS[name].family,
        }
        for name in metric_names
    ]


def _team_meta(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    teams: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("classification") or "").lower() != "fbs":
            continue
        team_id = _team_id(row)
        if team_id is None:
            continue
        teams.setdefault(
            team_id,
            {
                "id": team_id,
                "n": str(row.get("team") or team_id),
                "s": str(row.get("team_slug") or ""),
                "c": str(row.get("conference") or ""),
            },
        )
    return teams


def _percentile_score(rank: int, field_size: int) -> float:
    if field_size <= 1:
        return 100.0
    return 100.0 * (field_size - rank) / (field_size - 1)


def _full_season_teams(
    rows: Sequence[Mapping[str, Any]],
    *,
    season: int,
    metric_names: Sequence[str],
    ridge: float,
    home_ridge: float,
) -> list[dict[str, Any]]:
    meta = _team_meta(rows)
    if not meta:
        return []

    results = fit_all_metrics(
        rows,
        metric_names,
        season=season,
        ridge=ridge,
        fit_home_field=True,
        home_ridge=home_ridge,
    )

    payload = {team_id: {**team, "m": []} for team_id, team in meta.items()}
    offense_scores: dict[str, list[float]] = defaultdict(list)
    defense_scores: dict[str, list[float]] = defaultdict(list)

    for metric in metric_names:
        result = results[metric]
        offense = [row for row in result.offense_rankings() if row.team in meta]
        defense = [row for row in result.defense_rankings() if row.team in meta]
        off_rank = {row.team: index for index, row in enumerate(offense, 1)}
        def_rank = {row.team: index for index, row in enumerate(defense, 1)}
        off_value = {row.team: row.adjusted_value for row in offense}
        def_value = {row.team: row.adjusted_value for row in defense}

        for team_id in meta:
            orank = off_rank.get(team_id)
            drank = def_rank.get(team_id)
            payload[team_id]["m"].append(
                [
                    _round(off_value.get(team_id)),
                    orank,
                    _round(def_value.get(team_id)),
                    drank,
                ]
            )
            if orank is not None:
                offense_scores[team_id].append(_percentile_score(orank, len(offense)))
            if drank is not None:
                defense_scores[team_id].append(_percentile_score(drank, len(defense)))

    for team_id, row in payload.items():
        oscore = sum(offense_scores[team_id]) / len(offense_scores[team_id]) if offense_scores[team_id] else 0.0
        dscore = sum(defense_scores[team_id]) / len(defense_scores[team_id]) if defense_scores[team_id] else 0.0
        row["os"] = _round(oscore)
        row["ds"] = _round(dscore)
        row["xs"] = _round((oscore + dscore) / 2.0)

    offense_order = sorted(payload.values(), key=lambda row: (-float(row["os"] or 0.0), row["n"]))
    defense_order = sorted(payload.values(), key=lambda row: (-float(row["ds"] or 0.0), row["n"]))
    overall_order = sorted(payload.values(), key=lambda row: (-float(row["xs"] or 0.0), row["n"]))
    for rank, row in enumerate(offense_order, 1):
        row["or"] = rank
    for rank, row in enumerate(defense_order, 1):
        row["dr"] = rank
    for rank, row in enumerate(overall_order, 1):
        row["xr"] = rank

    return sorted(payload.values(), key=lambda row: row["n"])


def _game_metric_array(
    row: Mapping[str, Any],
    result: Any,
    metric: str,
) -> list[Any]:
    spec = METRIC_SPECS[metric]
    team_id = _team_id(row)
    opponent_id = _opponent_id(row)
    if team_id is None or opponent_id is None:
        return [None, None, None, None, 0, None, None, None, None, 0]

    venue = venue_from_team_game(row)
    actual_offense, offense_weight = _raw_metric(row, spec)
    actual_defense = _number(row.get(f"{metric}Allowed"))
    defense_weight = _number(row.get(DEFENSE_WEIGHT_FIELDS[metric]))

    offense_expected = None
    offense_poe = None
    offense_supported = 0
    if actual_offense is not None:
        offense_expected = result.expected_raw(team_id, opponent_id, venue)
        offense_poe = (actual_offense - offense_expected) * spec.orientation
        offense_supported = int(
            result.offense_exposure.get(team_id, 0.0) > 0.0
            and result.defense_exposure.get(opponent_id, 0.0) > 0.0
        )

    defense_expected = None
    defense_poe = None
    defense_supported = 0
    if actual_defense is not None:
        defense_expected = result.expected_raw(opponent_id, team_id, -venue)
        defense_poe = -(actual_defense - defense_expected) * spec.orientation
        defense_supported = int(
            result.defense_exposure.get(team_id, 0.0) > 0.0
            and result.offense_exposure.get(opponent_id, 0.0) > 0.0
        )

    return [
        _round(actual_offense),
        _round(offense_expected),
        _round(offense_poe),
        _round(offense_weight),
        offense_supported,
        _round(actual_defense),
        _round(defense_expected),
        _round(defense_poe),
        _round(defense_weight),
        defense_supported,
    ]


def _game_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    season: int,
    metric_names: Sequence[str],
    ridge: float,
    home_ridge: float,
) -> list[dict[str, Any]]:
    by_game: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("season") != season:
            continue
        game_id = _game_id(row)
        if game_id is not None:
            by_game[game_id].append(row)

    ordered_games = sorted(
        by_game.items(),
        key=lambda item: (
            min((partition_order(row) for row in item[1]), default=999),
            item[0],
        ),
    )
    out: list[dict[str, Any]] = []

    for index, (game_id, game_rows) in enumerate(ordered_games, 1):
        fitted: dict[str, Any] = {}
        for metric in metric_names:
            try:
                fitted[metric] = fit_metric_from_rows(
                    rows,
                    metric,
                    season=season,
                    exclude_game_ids=(game_id,),
                    ridge=ridge,
                    fit_home_field=True,
                    home_ridge=home_ridge,
                )
            except ValueError:
                fitted[metric] = None

        for row in game_rows:
            if str(row.get("classification") or "").lower() != "fbs":
                continue
            team_id = _team_id(row)
            opponent_id = _opponent_id(row)
            if team_id is None or opponent_id is None:
                continue
            metric_rows = [
                _game_metric_array(row, fitted[metric], metric)
                if fitted[metric] is not None
                else [None, None, None, None, 0, None, None, None, None, 0]
                for metric in metric_names
            ]
            out.append(
                {
                    "id": game_id,
                    "w": int(row["week"]) if isinstance(row.get("week"), int) else None,
                    "p": partition_order(row),
                    "st": str(row.get("seasonType", row.get("season_type", "regular")) or "regular"),
                    "t": team_id,
                    "o": opponent_id,
                    "on": str(row.get("opponent") or opponent_id),
                    "ha": str(row.get("home_away") or ""),
                    "n": bool(row.get("neutral_site")),
                    "pf": _round(_number(row.get("points_for"))),
                    "pa": _round(_number(row.get("points_against"))),
                    "m": metric_rows,
                }
            )
        if index % 50 == 0 or index == len(ordered_games):
            print(f"  game analysis {index:,}/{len(ordered_games):,}", flush=True)

    return sorted(out, key=lambda row: (row["p"], row["id"], row["t"]))


def build_analytics_lab(
    rows: Sequence[Mapping[str, Any]],
    *,
    season: int,
    metric_names: Sequence[str] = VALIDATED_GAME_METRICS,
    ridge: float = DEFAULT_RIDGE,
    home_ridge: float = DEFAULT_HOME_RIDGE,
) -> dict[str, Any]:
    return {
        "v": ANALYTICS_LAB_VERSION,
        "season": season,
        "ridge": ridge,
        "homeRidge": home_ridge,
        "metrics": _metric_meta(metric_names),
        "teams": _full_season_teams(
            rows,
            season=season,
            metric_names=metric_names,
            ridge=ridge,
            home_ridge=home_ridge,
        ),
        "games": _game_rows(
            rows,
            season=season,
            metric_names=metric_names,
            ridge=ridge,
            home_ridge=home_ridge,
        ),
    }


def export_season(
    published_root: Path,
    season: int,
    *,
    ridge: float = DEFAULT_RIDGE,
    home_ridge: float = DEFAULT_HOME_RIDGE,
) -> Path:
    rows = collect_published_team_games(published_root, season)
    print(f"{season}: loaded {len(rows):,} team-game rows", flush=True)
    payload = build_analytics_lab(
        rows,
        season=season,
        ridge=ridge,
        home_ridge=home_ridge,
    )
    path = published_root / str(season) / "analytics" / "opponent-adjusted-lab.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    print(
        f"{season}: wrote {len(payload['teams']):,} FBS teams and {len(payload['games']):,} FBS team-games -> {path}",
        flush=True,
    )
    return path


def _discover_seasons(root: Path) -> tuple[int, ...]:
    seasons = []
    for path in root.iterdir():
        if path.is_dir() and path.name.isdigit() and 2010 <= int(path.name) <= 2099:
            seasons.append(int(path.name))
    return tuple(sorted(seasons))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export compact opponent-adjusted analytics-lab artifacts")
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    parser.add_argument("--season", action="append", type=int, help="Season to export; repeatable")
    parser.add_argument("--all", action="store_true", help="Export every discovered published season")
    parser.add_argument("--ridge", type=float, default=DEFAULT_RIDGE)
    parser.add_argument("--home-ridge", type=float, default=DEFAULT_HOME_RIDGE)
    args = parser.parse_args()

    if args.all:
        seasons = _discover_seasons(args.published_root)
    elif args.season:
        seasons = tuple(dict.fromkeys(args.season))
    else:
        seasons = (2025,)

    for season in seasons:
        export_season(
            args.published_root,
            season,
            ridge=args.ridge,
            home_ridge=args.home_ridge,
        )


if __name__ == "__main__":
    main()
