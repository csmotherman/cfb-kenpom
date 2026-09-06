"""Rank historical team-seasons by results and opponent-adjusted performance.

This is a quality ranking, not an archetype matcher.

Backbone:
- full-season SRS from actual scoring margins and schedule graph;
- full-season iterative opponent-adjusted offense/defense ratings across the six
  validated metric families already used by the prediction research;
- within-season z-scores so teams from different scoring environments can be
  compared by how dominant they were relative to that season.

The consensus PowerScore is deliberately transparent: 50% SRS z-score and 50%
iterative composite z-score. Raw components are retained so the consensus can
be audited or replaced later without losing information.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from cfb_analytics.analytics.iterative_ratings import SPECS, fit_all_ratings, fit_srs
from cfb_analytics.derived.pregame import game_contexts, load_team_games

POWER_VERSION = "historical-power-v1-srs-iterative-2014-2025"
DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _zmap(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    vals = list(values.values())
    mu = mean(vals)
    var = mean((v - mu) ** 2 for v in vals)
    sd = math.sqrt(var)
    if sd <= 1e-12:
        return {k: 0.0 for k in values}
    return {k: (v - mu) / sd for k, v in values.items()}


def _rank_desc(rows: list[dict[str, Any]], field: str, out_field: str) -> None:
    ranked = [r for r in rows if _num(r.get(field))]
    ranked.sort(key=lambda r: (-float(r[field]), int(r["season"]), str(r["team"])))
    for i, row in enumerate(ranked, 1):
        row[out_field] = i


def _contexts_to_srs_rows(contexts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for gid, c in contexts.items():
        hs, as_ = c.get("homeScore"), c.get("awayScore")
        if not c.get("homeTeam") or not c.get("awayTeam") or not _num(hs) or not _num(as_):
            continue
        rows.append({
            "gameId": gid,
            "homeTeam": c["homeTeam"],
            "awayTeam": c["awayTeam"],
            "target_margin": float(hs) - float(as_),
        })
    return rows


def rank_season(team_games: list[dict[str, Any]], contexts: dict[str, dict[str, Any]], season: int) -> list[dict[str, Any]]:
    games = [r for r in team_games if int(r.get("season", -1)) == int(season)]
    srs = fit_srs(_contexts_to_srs_rows(contexts))
    fitted = fit_all_ratings(games)

    teams = sorted(
        set(srs.get("ratings", {}))
        | {str(r.get("team")) for r in games if r.get("team")}
    )

    # Raw iterative offense/defense effects, standardized separately per metric.
    off_z_by_metric: dict[str, dict[str, float]] = {}
    def_z_by_metric: dict[str, dict[str, float]] = {}
    net_z_by_metric: dict[str, dict[str, float]] = {}
    raw_by_team: dict[str, dict[str, float | None]] = {t: {} for t in teams}

    for name, *_ in SPECS:
        result = fitted.get(name, {})
        offense = {t: float(v) for t, v in result.get("offense", {}).items() if _num(v)}
        defense = {t: float(v) for t, v in result.get("defense", {}).items() if _num(v)}
        net = {t: offense[t] + defense[t] for t in offense.keys() & defense.keys()}
        off_z_by_metric[name] = _zmap(offense)
        def_z_by_metric[name] = _zmap(defense)
        net_z_by_metric[name] = _zmap(net)
        for team in teams:
            raw_by_team[team][f"iterative{name}Offense"] = offense.get(team)
            raw_by_team[team][f"iterative{name}Defense"] = defense.get(team)
            raw_by_team[team][f"iterative{name}Net"] = net.get(team)

    srs_ratings = {t: float(v) for t, v in srs.get("ratings", {}).items() if _num(v)}
    srs_z = _zmap(srs_ratings)

    rows: list[dict[str, Any]] = []
    for team in teams:
        off_components = [m.get(team) for m in off_z_by_metric.values() if _num(m.get(team))]
        def_components = [m.get(team) for m in def_z_by_metric.values() if _num(m.get(team))]
        net_components = [m.get(team) for m in net_z_by_metric.values() if _num(m.get(team))]
        offense_z = mean(off_components) if off_components else None
        defense_z = mean(def_components) if def_components else None
        iterative_z = mean(net_components) if net_components else None
        sz = srs_z.get(team)
        consensus_parts = [x for x in (sz, iterative_z) if _num(x)]
        power_z = mean(consensus_parts) if len(consensus_parts) == 2 else None
        rows.append({
            "season": season,
            "team": team,
            "games": sum(1 for r in games if r.get("team") == team),
            "srs": srs_ratings.get(team),
            "srsZ": sz,
            "iterativeOffenseZ": offense_z,
            "iterativeDefenseZ": defense_z,
            "iterativeCompositeZ": iterative_z,
            "iterativeMetricCount": len(net_components),
            "powerZ": power_z,
            "PowerScore": 50.0 + 10.0 * power_z if _num(power_z) else None,
            **raw_by_team[team],
        })

    _rank_desc(rows, "srs", "srsSeasonRank")
    _rank_desc(rows, "iterativeCompositeZ", "iterativeSeasonRank")
    _rank_desc(rows, "PowerScore", "powerSeasonRank")
    return rows


def build_historical_power(raw_root: Path, processed_root: Path, seasons: tuple[int, ...] = DEFAULT_SEASONS) -> dict[str, Any]:
    all_rows: list[dict[str, Any]] = []
    season_diagnostics: list[dict[str, Any]] = []
    for season in seasons:
        games = load_team_games(raw_root, processed_root, season)
        contexts = game_contexts(raw_root, processed_root, season)
        rows = rank_season(games, contexts, season)
        all_rows.extend(rows)
        season_diagnostics.append({
            "season": season,
            "teamCount": len(rows),
            "gameCount": len(contexts),
            "rankedCount": sum(_num(r.get("PowerScore")) for r in rows),
        })

    _rank_desc(all_rows, "PowerScore", "allTimeRank")
    _rank_desc(all_rows, "srsZ", "allTimeSrsDominanceRank")
    _rank_desc(all_rows, "iterativeCompositeZ", "allTimeIterativeDominanceRank")

    ranked = sorted(
        [r for r in all_rows if _num(r.get("PowerScore"))],
        key=lambda r: (int(r["allTimeRank"])),
    )
    return {
        "version": POWER_VERSION,
        "seasons": list(seasons),
        "seasonCount": len(seasons),
        "teamSeasonCount": len(all_rows),
        "rankedTeamSeasonCount": len(ranked),
        "method": {
            "srsWeight": 0.5,
            "iterativeWeight": 0.5,
            "crossSeasonNormalization": "within-season population z-score",
            "iterativeMetrics": [name for name, *_ in SPECS],
            "PowerScore": "50 + 10 * mean(SRS_z, iterativeComposite_z)",
        },
        "seasonDiagnostics": season_diagnostics,
        "rankings": ranked,
    }


def concise(report: dict[str, Any], *, top_n: int = 30, per_season: int = 3) -> str:
    lines = [
        "HISTORICAL STATISTICAL POWER RANKINGS",
        f"Seasons: {report['seasons'][0]}-{report['seasons'][-1]} (2020 absent by corpus design)",
        f"Ranked team-seasons: {report['rankedTeamSeasonCount']:,}",
        "PowerScore = 50% full-season SRS dominance + 50% iterative opponent-adjusted dominance",
        "Cross-season comparison uses within-season z-scores.",
        "",
        f"TOP {top_n} ALL-TIME:",
    ]
    for r in report["rankings"][:top_n]:
        lines.append(
            f"#{r['allTimeRank']:>2} {r['season']} {r['team']} | Power={r['PowerScore']:.2f} "
            f"SRS={r['srs']:.2f} (z={r['srsZ']:.2f}) | IterZ={r['iterativeCompositeZ']:.2f} "
            f"OffZ={r['iterativeOffenseZ']:.2f} DefZ={r['iterativeDefenseZ']:.2f}"
        )
    lines += ["", f"TOP {per_season} BY SEASON:"]
    by_season: dict[int, list[dict[str, Any]]] = {}
    for r in report["rankings"]:
        by_season.setdefault(int(r["season"]), []).append(r)
    for season in report["seasons"]:
        top = sorted(by_season.get(int(season), []), key=lambda r: int(r["powerSeasonRank"]))[:per_season]
        txt = "; ".join(f"{r['powerSeasonRank']}. {r['team']} {r['PowerScore']:.1f}" for r in top)
        lines.append(f"{season}: {txt}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    p.add_argument("--seasons", nargs="+", type=int, default=list(DEFAULT_SEASONS))
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--per-season", type=int, default=3)
    args = p.parse_args()
    report = build_historical_power(args.raw_root, args.processed_root, tuple(args.seasons))
    target = args.processed_root / "derived" / "profiles" / "historical_power_rankings_2014_2025.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, separators=(",", ":")))
    print(concise(report, top_n=args.top, per_season=args.per_season))


if __name__ == "__main__":
    main()
