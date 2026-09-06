"""Audit the actual statistical components behind fan-facing team profile fields.

This is a diagnostic tool. It does not assign or modify archetypes. The purpose
is to make the data visible before changing profile formulas or naming rules.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

DEFAULT_SEASONS = (2014,)
DEFAULT_TEAMS = ("Air Force", "Alabama", "Army", "Baylor", "California")

COMPONENTS = (
    "oa_run_efficiency_off",
    "oa_run_explosiveness_off",
    "oa_run_success_yards_off",
    "oa_pass_efficiency_off",
    "oa_pass_explosiveness_off",
    "oa_pass_success_yards_off",
    "oa_success_off",
    "oa_explosiveness_off",
    "oa_third_down_off",
    "oa_finishing_off",
    "rush_rate",
    "pass_rate",
    "plays_per_possession",
)

IDENTITY_FIELDS = (
    "identity_rushing_attack",
    "identity_passing_attack",
    "identity_offense_quality",
    "identity_rushing_defense",
    "identity_passing_defense",
    "identity_defense_quality",
    "identity_run_vs_pass_off",
    "identity_explosive_vs_methodical",
    "identity_predictability",
    "identity_one_dimensionality",
    "identity_playcalling_fit",
    "identity_scheme_constraint",
)


def _avg(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(r[field]) for r in rows if isinstance(r.get(field), (int, float)) and not isinstance(r.get(field), bool)]
    return mean(values) if values else None


def _pct_field(key: str) -> str:
    return f"current_{key}_percentile"


def summarize_team(rows: list[dict[str, Any]], *, season: int, team: str) -> dict[str, Any]:
    selected = [r for r in rows if int(r.get("season", -1)) == int(season) and str(r.get("team")) == team]
    if not selected:
        return {"season": season, "team": team, "status": "NO_DATA"}
    selected.sort(key=lambda r: (str(r.get("seasonType") or "regular"), int(r.get("week") or 0), int(r.get("gamesPlayed") or 0)))
    out: dict[str, Any] = {
        "season": season,
        "team": team,
        "status": "OK",
        "snapshotCount": len(selected),
        "firstWeek": selected[0].get("week"),
        "lastWeek": selected[-1].get("week"),
    }
    for key in COMPONENTS:
        out[key] = _avg(selected, _pct_field(key))
    for key in IDENTITY_FIELDS:
        out[key] = _avg(selected, key)
    return out


def _fmt(value: Any) -> str:
    return "NA" if not isinstance(value, (int, float)) else f"{float(value):.1f}"


def concise(items: list[dict[str, Any]]) -> str:
    lines = ["TEAM PROFILE COMPONENT AUDIT", "Stats first; no archetype assignment.", ""]
    for x in items:
        if x["status"] != "OK":
            lines.append(f"{x['season']} {x['team']}: NO DATA")
            continue
        lines.append(f"{x['season']} {x['team']} | snapshots={x['snapshotCount']} W{x['firstWeek']}-W{x['lastWeek']}")
        lines.append(
            "  RUN  | "
            f"Success={_fmt(x['oa_run_efficiency_off'])} "
            f"Explosive={_fmt(x['oa_run_explosiveness_off'])} "
            f"SuccessYards={_fmt(x['oa_run_success_yards_off'])} "
            f"=> RushAtk={_fmt(x['identity_rushing_attack'])}"
        )
        lines.append(
            "  PASS | "
            f"Success={_fmt(x['oa_pass_efficiency_off'])} "
            f"Explosive={_fmt(x['oa_pass_explosiveness_off'])} "
            f"SuccessYards={_fmt(x['oa_pass_success_yards_off'])} "
            f"=> PassAtk={_fmt(x['identity_passing_attack'])}"
        )
        lines.append(
            "  OFF  | "
            f"OverallSuccess={_fmt(x['oa_success_off'])} Explosive={_fmt(x['oa_explosiveness_off'])} "
            f"3rdDown={_fmt(x['oa_third_down_off'])} Finish={_fmt(x['oa_finishing_off'])} "
            f"OffQ={_fmt(x['identity_offense_quality'])}"
        )
        lines.append(
            "  STYLE| "
            f"RushTend={_fmt(x['rush_rate'])} PassTend={_fmt(x['pass_rate'])} DriveLen={_fmt(x['plays_per_possession'])} "
            f"Predict={_fmt(x['identity_predictability'])} OneDim={_fmt(x['identity_one_dimensionality'])}"
        )
        lines.append(
            "  DEF  | "
            f"RunDef={_fmt(x['identity_rushing_defense'])} PassDef={_fmt(x['identity_passing_defense'])} "
            f"DefQ={_fmt(x['identity_defense_quality'])}"
        )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    p.add_argument("--seasons", nargs="+", type=int, default=list(DEFAULT_SEASONS))
    p.add_argument("--teams", nargs="+", default=list(DEFAULT_TEAMS))
    args = p.parse_args()

    source = args.processed_root / "derived" / "profiles" / "identity_snapshots_v3_attack_scheme.json"
    if not source.exists():
        raise FileNotFoundError("build v3 snapshots first: python -m cfb_analytics.profiles.snapshots")
    rows = json.loads(source.read_text())
    items = [summarize_team(rows, season=season, team=team) for season in args.seasons for team in args.teams]
    print(concise(items))


if __name__ == "__main__":
    main()
