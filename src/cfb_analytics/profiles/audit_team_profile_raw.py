"""Compare raw team production to opponent-adjusted profile percentiles.

Diagnostic only. This does not change profile formulas or archetype matching.
It exposes the raw numerators/denominators behind run/pass profile components so
we can tell whether a surprising percentile originates in raw production or in
the opponent-adjustment/context-ranking layer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.raw.audit import discover_partitions

DEFAULT_SEASON = 2014
DEFAULT_TEAMS = ("Air Force", "Alabama", "Army", "Baylor", "California")


def _num(v: Any) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _rate(n: float, d: float) -> float | None:
    return n / d if d else None


def _avg(rows: list[dict[str, Any]], field: str) -> float | None:
    vals = [float(r[field]) for r in rows if isinstance(r.get(field), (int, float)) and not isinstance(r.get(field), bool)]
    return mean(vals) if vals else None


def _load_team_games(processed_root: Path, season: int) -> list[dict[str, Any]]:
    raw_root = processed_root.parent / "raw"
    rows: list[dict[str, Any]] = []
    for season_type, week in discover_partitions(raw_root, season):
        path = derived_game_partition_dir(processed_root, season, season_type, week) / "team_games.json"
        if path.exists():
            rows.extend(json.loads(path.read_text()))
    return rows


def _raw_family(rows: list[dict[str, Any]], family: str) -> dict[str, float | None]:
    eligible = sum(_num(r.get(f"{family}SuccessEligiblePlays")) for r in rows)
    successes = sum(_num(r.get(f"{family}SuccessfulPlays")) for r in rows)
    explosive_eligible = sum(_num(r.get(f"{family}ExplosiveEligiblePlays")) for r in rows)
    explosives = sum(_num(r.get(f"{family}ExplosivePlays")) for r in rows)
    success_yards = sum(_num(r.get(f"{family}SuccessfulPlayYards")) for r in rows)
    return {
        "eligible": eligible,
        "successes": successes,
        "success_rate": _rate(successes, eligible),
        "explosive_eligible": explosive_eligible,
        "explosives": explosives,
        "explosive_rate": _rate(explosives, explosive_eligible),
        "success_yards": success_yards,
        "yards_per_success": _rate(success_yards, successes),
    }


def summarize(
    snapshots: list[dict[str, Any]],
    team_games: list[dict[str, Any]],
    *,
    season: int,
    team: str,
) -> dict[str, Any]:
    snaps = [r for r in snapshots if int(r.get("season", -1)) == season and str(r.get("team")) == team]
    games = [r for r in team_games if int(r.get("season", -1)) == season and str(r.get("team")) == team and r.get("gameValidationStatus") in (None, "PASS")]
    if not snaps or not games:
        return {"season": season, "team": team, "status": "NO_DATA"}

    rush = _raw_family(games, "rush")
    pas = _raw_family(games, "pass")
    total_family = float(rush["eligible"] or 0.0) + float(pas["eligible"] or 0.0)
    plays = sum(_num(r.get("offensivePlays")) for r in games)
    yards = sum(_num(r.get("offensiveYards")) for r in games)

    out: dict[str, Any] = {
        "season": season,
        "team": team,
        "status": "OK",
        "games": len({str(r.get("gameId")) for r in games}),
        "snapshots": len(snaps),
        "rush": rush,
        "pass": pas,
        "rush_share": _rate(float(rush["eligible"] or 0.0), total_family),
        "pass_share": _rate(float(pas["eligible"] or 0.0), total_family),
        "offensive_plays": plays,
        "offensive_yards": yards,
        "yards_per_play": _rate(yards, plays),
    }
    for key in (
        "oa_run_efficiency_off", "oa_run_explosiveness_off", "oa_run_success_yards_off",
        "oa_pass_efficiency_off", "oa_pass_explosiveness_off", "oa_pass_success_yards_off",
        "rush_rate", "pass_rate",
    ):
        out[key] = _avg(snaps, f"current_{key}_percentile")
    out["identity_rushing_attack"] = _avg(snaps, "identity_rushing_attack")
    out["identity_passing_attack"] = _avg(snaps, "identity_passing_attack")
    return out


def _f(v: Any, digits: int = 1) -> str:
    return "NA" if not isinstance(v, (int, float)) else f"{float(v):.{digits}f}"


def _pct(v: Any) -> str:
    return "NA" if not isinstance(v, (int, float)) else f"{100.0 * float(v):.1f}%"


def concise(items: list[dict[str, Any]]) -> str:
    lines = ["RAW VS OPPONENT-ADJUSTED TEAM PROFILE AUDIT", "No archetype assignment; no formula changes.", ""]
    for x in items:
        if x["status"] != "OK":
            lines.append(f"{x['season']} {x['team']}: NO DATA")
            continue
        r, p = x["rush"], x["pass"]
        lines.append(f"{x['season']} {x['team']} | games={x['games']} snapshots={x['snapshots']}")
        lines.append(
            f"  TOTAL | Plays={_f(x['offensive_plays'],0)} Yards={_f(x['offensive_yards'],0)} YPP={_f(x['yards_per_play'],2)}"
        )
        lines.append(
            "  RUN RAW | "
            f"Elig={_f(r['eligible'],0)} Share={_pct(x['rush_share'])} "
            f"Success={_f(r['successes'],0)}/{_f(r['eligible'],0)} ({_pct(r['success_rate'])}) "
            f"Expl={_f(r['explosives'],0)}/{_f(r['explosive_eligible'],0)} ({_pct(r['explosive_rate'])}) "
            f"Yds/Success={_f(r['yards_per_success'],2)}"
        )
        lines.append(
            "  RUN OA  | "
            f"SuccessPct={_f(x['oa_run_efficiency_off'])} "
            f"ExplPct={_f(x['oa_run_explosiveness_off'])} "
            f"SuccessYdsPct={_f(x['oa_run_success_yards_off'])} "
            f"=> RushAtk={_f(x['identity_rushing_attack'])}"
        )
        lines.append(
            "  PASS RAW| "
            f"Elig={_f(p['eligible'],0)} Share={_pct(x['pass_share'])} "
            f"Success={_f(p['successes'],0)}/{_f(p['eligible'],0)} ({_pct(p['success_rate'])}) "
            f"Expl={_f(p['explosives'],0)}/{_f(p['explosive_eligible'],0)} ({_pct(p['explosive_rate'])}) "
            f"Yds/Success={_f(p['yards_per_success'],2)}"
        )
        lines.append(
            "  PASS OA | "
            f"SuccessPct={_f(x['oa_pass_efficiency_off'])} "
            f"ExplPct={_f(x['oa_pass_explosiveness_off'])} "
            f"SuccessYdsPct={_f(x['oa_pass_success_yards_off'])} "
            f"=> PassAtk={_f(x['identity_passing_attack'])}"
        )
        lines.append(
            f"  STYLE   | Snapshot RushTend={_f(x['rush_rate'])} PassTend={_f(x['pass_rate'])}"
        )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    p.add_argument("--season", type=int, default=DEFAULT_SEASON)
    p.add_argument("--teams", nargs="+", default=list(DEFAULT_TEAMS))
    args = p.parse_args()

    profile_path = args.processed_root / "derived" / "profiles" / "identity_snapshots_v3_attack_scheme.json"
    if not profile_path.exists():
        raise FileNotFoundError("build v3 snapshots first: python -m cfb_analytics.profiles.snapshots")
    snapshots = json.loads(profile_path.read_text())
    team_games = _load_team_games(args.processed_root, args.season)
    items = [summarize(snapshots, team_games, season=args.season, team=team) for team in args.teams]
    print(concise(items))


if __name__ == "__main__":
    main()
