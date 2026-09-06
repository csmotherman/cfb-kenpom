"""Human-in-the-loop validation harness for fan-facing team identities.

Calibration output now separates broad rushing/passing attack quality from
single-component success rate and reports scheme signals such as predictability,
one-dimensionality and playcalling fit. Labels remain research-only.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .grades import grade_percentile

DEFAULT_SEASONS = (2021, 2022, 2023, 2024, 2025)

QUALITY_FIELDS = (
    "oa_run_efficiency_off", "oa_pass_efficiency_off",
    "oa_run_explosiveness_off", "oa_pass_explosiveness_off",
    "oa_run_success_yards_off", "oa_pass_success_yards_off",
    "oa_success_off", "oa_explosiveness_off", "oa_third_down_off", "oa_finishing_off",
    "oa_run_efficiency_def", "oa_pass_efficiency_def",
    "oa_run_explosiveness_def", "oa_pass_explosiveness_def",
    "oa_run_success_yards_def", "oa_pass_success_yards_def",
    "oa_success_def", "oa_explosiveness_def", "oa_third_down_def", "oa_finishing_def",
)
STYLE_FIELDS = ("rush_rate", "pass_rate", "plays_per_possession")
SHAPE_FIELDS = (
    "identity_rushing_attack", "identity_passing_attack",
    "identity_rushing_defense", "identity_passing_defense",
    "identity_run_vs_pass_off", "identity_run_vs_pass_def",
    "identity_explosive_vs_methodical", "identity_finishing_vs_foundation",
    "identity_offense_vs_defense", "identity_rush_vs_pass_tendency",
    "identity_predictability", "identity_one_dimensionality",
    "identity_playcalling_fit", "identity_scheme_constraint",
    "identity_offense_quality", "identity_defense_quality",
)


def _avg(rows: list[dict[str, Any]], field: str) -> float | None:
    vals = [float(r[field]) for r in rows if isinstance(r.get(field), (int, float))]
    return mean(vals) if vals else None


def _pct(row: dict[str, Any], key: str) -> float | None:
    value = row.get(f"current_{key}_percentile")
    return float(value) if isinstance(value, (int, float)) else None


def _shape(row: dict[str, Any], key: str, fallback: float = 50.0) -> float:
    value = row.get(key)
    return float(value) if isinstance(value, (int, float)) else fallback


def _mean_available(*values: float | None, fallback: float = 50.0) -> float:
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    return mean(vals) if vals else fallback


def provisional_name(row: dict[str, Any]) -> tuple[str, str]:
    """Return a calibration-only nickname with v2-compatible fallbacks.

    Real v3 snapshots provide composite rushing/passing attack and defense fields.
    Older synthetic fixtures and saved validation data may not. In that case,
    derive the composite from the available opponent-adjusted component
    percentiles rather than silently defaulting the whole concept to average.
    """
    run_eff = _pct(row, "oa_run_efficiency_off")
    pass_eff = _pct(row, "oa_pass_efficiency_off")
    run_exp = _pct(row, "oa_run_explosiveness_off")
    pass_exp = _pct(row, "oa_pass_explosiveness_off")
    run_yards = _pct(row, "oa_run_success_yards_off")
    pass_yards = _pct(row, "oa_pass_success_yards_off")

    rush_attack = _shape(
        row,
        "identity_rushing_attack",
        _mean_available(run_eff, run_exp, run_yards),
    )
    pass_attack = _shape(
        row,
        "identity_passing_attack",
        _mean_available(pass_eff, pass_exp, pass_yards),
    )

    run_def_eff = _pct(row, "oa_run_efficiency_def")
    pass_def_eff = _pct(row, "oa_pass_efficiency_def")
    run_def_exp = _pct(row, "oa_run_explosiveness_def")
    pass_def_exp = _pct(row, "oa_pass_explosiveness_def")
    run_def_yards = _pct(row, "oa_run_success_yards_def")
    pass_def_yards = _pct(row, "oa_pass_success_yards_def")
    rush_defense = _shape(
        row,
        "identity_rushing_defense",
        _mean_available(run_def_eff, run_def_exp, run_def_yards),
    )
    pass_defense = _shape(
        row,
        "identity_passing_defense",
        _mean_available(pass_def_eff, pass_def_exp, pass_def_yards),
    )

    success_o = _pct(row, "oa_success_off") or 50.0
    explosive_o = _pct(row, "oa_explosiveness_off") or 50.0
    finish_o = _pct(row, "oa_finishing_off") or 50.0
    success_d = _pct(row, "oa_success_def")
    explosive_d = _pct(row, "oa_explosiveness_def")

    off_quality = _shape(
        row,
        "identity_offense_quality",
        _mean_available(rush_attack, pass_attack, success_o, explosive_o, finish_o),
    )
    def_quality = _shape(
        row,
        "identity_defense_quality",
        _mean_available(rush_defense, pass_defense, success_d, explosive_d),
    )

    rush = _pct(row, "rush_rate") or 50.0
    pass_rate = _pct(row, "pass_rate") or 50.0
    drive_len = _pct(row, "plays_per_possession") or 50.0
    predictability = _shape(row, "identity_predictability", 0.0)
    scheme_constraint = _shape(row, "identity_scheme_constraint", 0.0)
    attack_gap = rush_attack - pass_attack
    explosive_gap = explosive_o - success_o

    if def_quality >= 72 and pass_attack <= 35 and off_quality <= 48:
        return "Defense or Bust", "Defense is the clear strength while a severely limited passing attack constrains the offense."
    if rush >= 75 and rush_attack >= 58 and pass_attack <= 35 and attack_gap >= 25:
        return "Run or Die", "The offense is strongly run-dependent because the rushing attack is far more functional than the passing attack."
    if def_quality >= 82 and rush_defense >= 75 and pass_defense >= 75:
        return "Brick Wall", "High-end opponent-adjusted defense with few obvious ways for opponents to attack it."
    if rush >= 72 and rush_attack >= 65 and drive_len >= 65:
        return "Possession Vampire", "Run-leaning, efficient and built to stack plays and possessions."
    if rush >= 68 and rush_attack >= 62:
        return "Ground & Pound", "The rushing attack is the offense's foundation and a clear opponent-adjusted strength."
    if pass_rate >= 78 and pass_attack >= 65 and pass_attack - rush_attack >= 18:
        return "Air It Out", "Passing is both the preferred mode and the clear opponent-adjusted offensive strength."
    if explosive_gap >= 20 and success_o <= 55:
        return "Boom or Bust", "Explosive upside is much stronger than the offense's down-to-down consistency."
    if success_o >= 78 and explosive_o <= 62 and drive_len >= 62:
        return "Death by a Thousand Cuts", "Wins with repeatable efficiency and sustained drives more than chunk-play dependence."
    if success_o >= 82 and rush_attack >= 70 and pass_attack >= 70:
        return "Pick Your Poison", "Both rushing and passing attacks are strong enough that defenses lack an easy answer."
    if success_o >= 70 and finish_o <= 38:
        return "Between-the-20s Merchant", "The offense moves the ball better than it finishes scoring opportunities."
    if scheme_constraint >= 50 and predictability >= 55:
        return "One-Dimensional", "Extreme tendency plus a weak complementary attack makes the offense structurally predictable."
    if off_quality >= 75 and def_quality >= 70:
        return "Complete Team", "Strong opponent-adjusted performance on both sides without one extreme dependency."
    if off_quality >= 72:
        return "Offensive Machine", "Broad opponent-adjusted offensive quality matters more than a single stylistic extreme."
    if def_quality >= 72:
        return "Defense First", "The defense is the team's clearest opponent-adjusted strength."
    if off_quality <= 30 and def_quality <= 30:
        return "Searching for Answers", "Both sides grade poorly after opponent adjustment, with no stable strength to lean on."
    return "No Single Identity", "The snapshot is relatively balanced or does not cross a strong calibration threshold."


def _cluster_lookup(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for family in report.get("families", []):
        for archetype in family.get("archetypes", []):
            out[str(archetype["id"])] = archetype
    return out


def _resolve_team(snapshots: list[dict[str, Any]], requested: str) -> str:
    names = sorted({str(r.get("team")) for r in snapshots if r.get("team")})
    if requested in names:
        return requested
    ci = [n for n in names if n.lower() == requested.lower()]
    if len(ci) == 1:
        return ci[0]
    contains = [n for n in names if requested.lower() in n.lower()]
    return contains[0] if len(contains) == 1 else requested


def validate_team(snapshots: list[dict[str, Any]], discovery: dict[str, Any], *, team: str, seasons: tuple[int, ...] = DEFAULT_SEASONS) -> dict[str, Any]:
    wanted = {int(s) for s in seasons}
    resolved_team = _resolve_team(snapshots, team)
    team_snaps = [r for r in snapshots if int(r.get("season", -1)) in wanted and str(r.get("team")) == resolved_team]
    by_full = {(int(r["season"]), str(r.get("throughGameId"))): r for r in team_snaps if r.get("throughGameId") is not None}
    by_fallback = {(int(r["season"]), int(r.get("week") or 0), int(r.get("gamesPlayed") or 0)): r for r in team_snaps}
    assignments = [a for a in discovery.get("assignments", []) if int(a.get("season", -1)) in wanted and str(a.get("team")) == resolved_team]
    by_season: dict[int, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for a in assignments:
        snap = by_full.get((int(a["season"]), str(a.get("throughGameId")))) if a.get("throughGameId") is not None else None
        if snap is None:
            snap = by_fallback.get((int(a["season"]), int(a.get("week") or 0), int(a.get("gamesPlayed") or 0)))
        if snap is not None:
            by_season[int(a["season"])].append((a, snap))

    clusters = _cluster_lookup(discovery)
    seasons_out = []
    for season in sorted(wanted):
        pairs = sorted(by_season.get(season, []), key=lambda x: (int(x[1].get("week") or 0), str(x[1].get("throughGameId"))))
        if not pairs:
            seasons_out.append({"season": season, "status": "NO_DATA"}); continue
        names = [provisional_name(s)[0] for _, s in pairs]
        name_counts = Counter(names); dominant_name, dominant_count = name_counts.most_common(1)[0]
        cluster_counts = Counter(str(a.get("archetype")) for a, _ in pairs); dominant_cluster, cluster_count = cluster_counts.most_common(1)[0]
        summary: dict[str, Any] = {}
        for key in QUALITY_FIELDS + STYLE_FIELDS:
            summary[key] = _avg([s for _, s in pairs], f"current_{key}_percentile")
            summary[f"{key}_grade"] = grade_percentile(summary[key])
        for key in SHAPE_FIELDS:
            summary[key] = _avg([s for _, s in pairs], key)
        for key in ("identity_rushing_attack", "identity_passing_attack", "identity_rushing_defense", "identity_passing_defense"):
            summary[f"{key}_grade"] = grade_percentile(summary.get(key))

        timeline = []
        last = None
        for a, snap in pairs:
            name, why = provisional_name(snap)
            state = {"week": snap.get("week"), "gamesPlayed": snap.get("gamesPlayed"), "archetype": a.get("archetype"), "candidateName": name, "why": why}
            if last != (a.get("archetype"), name):
                timeline.append(state); last = (a.get("archetype"), name)
        cluster_info = clusters.get(dominant_cluster, {})
        seasons_out.append({"season": season, "status": "OK", "snapshotCount": len(pairs), "dominantCandidateName": dominant_name, "dominantCandidateShare": dominant_count / len(pairs), "dominantCluster": dominant_cluster, "dominantClusterShare": cluster_count / len(pairs), "candidateNameCounts": dict(name_counts), "clusterCounts": dict(cluster_counts), "summary": summary, "timeline": timeline, "clusterExemplars": cluster_info.get("exemplars", [])[:4]})
    return {"team": resolved_team, "requestedTeam": team, "seasons": seasons_out, "labelStatus": "CALIBRATION_ONLY"}


def _fmt(v: float | None) -> str:
    return "NA" if not isinstance(v, (int, float)) else f"{v:.0f}"


def concise(report: dict[str, Any]) -> str:
    title = f"TEAM ARCHETYPE VALIDATION — {report['team']}"
    if report.get("requestedTeam") != report.get("team"):
        title += f" (matched from {report['requestedTeam']})"
    lines = [title, "Labels are calibration-only, not production archetype names.", ""]
    for season in report["seasons"]:
        if season["status"] != "OK":
            lines.append(f"{season['season']}: NO DATA"); continue
        s = season["summary"]
        lines.append(f"{season['season']}: {season['dominantCandidateName']} ({season['dominantCandidateShare']:.0%} of snapshots) | cluster {season['dominantCluster']} ({season['dominantClusterShare']:.0%})")
        lines.append(f"  Attack: Rush {s.get('identity_rushing_attack_grade')} ({_fmt(s.get('identity_rushing_attack'))}) | Pass {s.get('identity_passing_attack_grade')} ({_fmt(s.get('identity_passing_attack'))})")
        lines.append(f"  Pass components: Success {s.get('oa_pass_efficiency_off_grade')} ({_fmt(s.get('oa_pass_efficiency_off'))}) | Explosive {s.get('oa_pass_explosiveness_off_grade')} ({_fmt(s.get('oa_pass_explosiveness_off'))}) | Successful-play yards {s.get('oa_pass_success_yards_off_grade')} ({_fmt(s.get('oa_pass_success_yards_off'))})")
        lines.append(f"  Defense: Run {s.get('identity_rushing_defense_grade')} ({_fmt(s.get('identity_rushing_defense'))}) | Pass {s.get('identity_passing_defense_grade')} ({_fmt(s.get('identity_passing_defense'))}) | Overall {_fmt(s.get('identity_defense_quality'))}")
        lines.append(f"  Style: Rush tendency {_fmt(s.get('rush_rate'))} | Pass tendency {_fmt(s.get('pass_rate'))} | Drive length {_fmt(s.get('plays_per_possession'))}")
        lines.append(f"  Scheme: Predictability {_fmt(s.get('identity_predictability'))} | One-dimensionality {_fmt(s.get('identity_one_dimensionality'))} | Playcalling fit {_fmt(s.get('identity_playcalling_fit'))} | Constraint {_fmt(s.get('identity_scheme_constraint'))}")
        lines.append(f"  Shape: Run-vs-pass O {s.get('identity_run_vs_pass_off', 0):+.0f} | Offense-vs-defense {s.get('identity_offense_vs_defense', 0):+.0f} | Explosive-vs-methodical {s.get('identity_explosive_vs_methodical', 0):+.0f}")
        if season["timeline"]:
            changes = " -> ".join(f"W{x['week']} {x['candidateName']} [{x['archetype']}]" for x in season["timeline"])
            lines.append(f"  Timeline: {changes}")
        if season["clusterExemplars"]:
            ex = "; ".join(f"{x['season']} {x['team']} W{x['week']}" for x in season["clusterExemplars"][:3])
            lines.append(f"  Cluster examples: {ex}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--processed-root", type=Path, default=Path("data/processed")); p.add_argument("--team", default="Michigan"); p.add_argument("--seasons", nargs="+", type=int, default=list(DEFAULT_SEASONS)); args = p.parse_args()
    profile_root = args.processed_root / "derived" / "profiles"
    snapshot_path = profile_root / "identity_snapshots_v3_attack_scheme.json"
    discovery_path = profile_root / "archetype_discovery_v2_oa.json"
    if not snapshot_path.exists():
        raise FileNotFoundError("build attack/scheme snapshots first: python -m cfb_analytics.profiles.snapshots")
    if not discovery_path.exists():
        raise FileNotFoundError("build archetype discovery before validation")
    report = validate_team(json.loads(snapshot_path.read_text()), json.loads(discovery_path.read_text()), team=args.team, seasons=tuple(args.seasons))
    print(concise(report))


if __name__ == "__main__":
    main()
