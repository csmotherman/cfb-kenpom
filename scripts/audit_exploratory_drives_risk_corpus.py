"""Corpus audit for LEILA Exploratory Wave 2 (drives/risk/scoring metrics).

Run AFTER materializing both propagation CLIs:
    python3 -m cfb_analytics.derived.exploratory_series_propagation_cli materialize --season 2025
    python3 -m cfb_analytics.derived.exploratory_drives_risk_propagation_cli materialize --season 2025

Same shape as audit_exploratory_series_corpus.py, extended to the Wave 2
metrics: coverage, sample-size distribution, league mean/stdev, percentiles,
top/bottom 20 -- for a manual football sanity check before anything gets
published.
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

METRICS = (
    ("cleanDrives", "eligibleDrives", "Clean Drive Rate (offense)"),
    ("cleanDrivesAllowed", "eligibleDrivesFaced", "Clean Drive Rate Allowed (defense)"),
    ("drivesKilled", "drivesWithKillerEvent", "Drive Killer Rate (offense, lower is better)"),
    ("drivesKilledForced", "drivesWithKillerEventForced", "Drive Killer Rate Forced (defense)"),
)

RATIO_METRICS = (
    ("explosivePositiveEpa", "positiveEpa", "Explosive Dependency (descriptive, no direction)"),
    ("negativeEpaMagnitudeSum", "epaEligiblePlays", "Failure Burden (offense, lower is better)"),
    ("opponentNegativeEpaMagnitudeSum", "opponentEpaEligiblePlays", "Failure Pressure (defense, higher is better)"),
    ("scoringOpportunityPoints", "scoringOpportunities", "Points per Scoring Opportunity (offense)"),
    ("opponentScoringOpportunityPoints", "opponentScoringOpportunities", "Opponent Points per Scoring Opportunity (defense, lower is better)"),
    ("nonExplosiveEpa", "nonExplosivePlays", "Non-Explosive EPA/play"),
)


def load_season(season: int) -> list[dict]:
    rows = []
    for path in glob.glob(str(REPO / f"data/processed/derived/exploratory/season={season}/season_type=*/week=*/team_games.json")):
        rows.extend(json.loads(Path(path).read_text()))
    return rows


def season_totals(rows: list[dict], team: str, num_field: str, den_field: str) -> tuple[float, float]:
    team_rows = [r for r in rows if r.get("team") == team]
    return (
        sum(r.get(num_field, 0) or 0 for r in team_rows),
        sum(r.get(den_field, 0) or 0 for r in team_rows),
    )


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    k = (len(sorted_values) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def metric_report(rows: list[dict], num_field: str, den_field: str, label: str) -> dict:
    teams = sorted({r["team"] for r in rows})
    team_stats = []
    for team in teams:
        num, den = season_totals(rows, team, num_field, den_field)
        if den > 0:
            team_stats.append((team, num, den, num / den))
    values = sorted(v for *_rest, v in team_stats)
    sample_sizes = sorted(den for _t, _n, den, _v in team_stats)

    report = {
        "label": label,
        "teamsCovered": len(team_stats),
        "teamsMissing": len(teams) - len(team_stats),
        "sampleSize": {
            "min": sample_sizes[0] if sample_sizes else None,
            "median": statistics.median(sample_sizes) if sample_sizes else None,
            "max": sample_sizes[-1] if sample_sizes else None,
        },
        "leagueMean": statistics.mean(values) if values else None,
        "leagueStdev": statistics.pstdev(values) if len(values) > 1 else None,
        "percentiles": {
            "p05": percentile(values, 0.05), "p25": percentile(values, 0.25),
            "p50": percentile(values, 0.50), "p75": percentile(values, 0.75),
            "p95": percentile(values, 0.95),
        } if values else None,
    }
    ranked = sorted(team_stats, key=lambda t: t[3], reverse=True)
    report["top20"] = [{"team": t, "n": den, "rate": v} for t, _n, den, v in ranked[:20]]
    report["bottom20"] = [{"team": t, "n": den, "rate": v} for t, _n, den, v in ranked[-20:]]
    return report


def full_report(season: int) -> dict:
    rows = load_season(season)
    if not rows:
        raise SystemExit(f"No materialized exploratory drives/risk data for season {season}.")
    metrics = {}
    for num, den, label in METRICS:
        metrics[label] = metric_report(rows, num, den, label)
    for num, den, label in RATIO_METRICS:
        metrics[label] = metric_report(rows, num, den, label)
    return {"season": season, "teamGameRows": len(rows), "metrics": metrics}


def concise(report: dict) -> str:
    lines = [f"EXPLORATORY DRIVES/RISK CORPUS AUDIT -- season {report['season']}", f"Team-game rows: {report['teamGameRows']:,}", ""]
    for label, m in report["metrics"].items():
        lines.append(f"## {label}")
        lines.append(f"Teams covered: {m['teamsCovered']} (missing: {m['teamsMissing']})")
        ss = m["sampleSize"]
        lines.append(f"Sample size (N): min={ss['min']}, median={ss['median']}, max={ss['max']}")
        if m["leagueMean"] is not None:
            unit = "%" if "Points per" not in label else ""
            fmt = (lambda v: f"{v:.1%}") if unit == "%" else (lambda v: f"{v:.3f}")
            lines.append(f"League mean: {fmt(m['leagueMean'])}  stdev: {fmt(m['leagueStdev'])}")
            if m["percentiles"]:
                p = m["percentiles"]
                lines.append(f"Percentiles: p05={fmt(p['p05'])} p25={fmt(p['p25'])} p50={fmt(p['p50'])} p75={fmt(p['p75'])} p95={fmt(p['p95'])}")
            lines.append("Top 5: " + ", ".join(f"{t['team']} {fmt(t['rate'])} (n={t['n']})" for t in m["top20"][:5]))
            lines.append("Bottom 5: " + ", ".join(f"{t['team']} {fmt(t['rate'])} (n={t['n']})" for t in m["bottom20"][-5:]))
        else:
            lines.append("League mean: N/A")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = full_report(args.season)
    print(json.dumps(report, indent=2) if args.json else concise(report))


if __name__ == "__main__":
    main()
