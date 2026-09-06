"""Match historical team-state snapshots to the 2,000-name archetype ontology.

The matcher is descriptive and post-partition. It scores every eligible v3
snapshot from 2014-2024 against the catalog and keeps the closest candidates.

v4 keeps salience-aware, root-first matching but makes the audit stats-first:
every team-season summary contains its actual averaged football profile before
showing the candidate archetype and the attributes that support or contradict it.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .archetype_catalog import CATALOG, CATALOG_VERSION, ArchetypeCandidate

MATCH_VERSION = "historical-archetype-match-v4-stats-first-2014-2024"
DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024)
SIGNED_FIELDS = {
    "identity_explosive_vs_methodical",
    "identity_offense_vs_defense",
    "identity_run_vs_pass_off",
    "identity_run_vs_pass_def",
    "identity_playcalling_fit",
}
PROFILE_FIELDS = (
    "identity_rushing_attack",
    "identity_passing_attack",
    "identity_rushing_defense",
    "identity_passing_defense",
    "identity_offense_quality",
    "identity_defense_quality",
    "rush_rate",
    "plays_per_possession",
    "identity_explosive_vs_methodical",
    "identity_offense_vs_defense",
    "identity_run_vs_pass_off",
    "identity_run_vs_pass_def",
    "identity_predictability",
    "identity_one_dimensionality",
    "identity_playcalling_fit",
    "identity_scheme_constraint",
)
PROFILE_LABELS = {
    "identity_rushing_attack": "RushAtk",
    "identity_passing_attack": "PassAtk",
    "identity_rushing_defense": "RunDef",
    "identity_passing_defense": "PassDef",
    "identity_offense_quality": "OffQ",
    "identity_defense_quality": "DefQ",
    "rush_rate": "RushTend",
    "plays_per_possession": "DriveLen",
    "identity_explosive_vs_methodical": "Expl-v-Method",
    "identity_offense_vs_defense": "Off-v-Def",
    "identity_run_vs_pass_off": "Run-v-Pass-O",
    "identity_run_vs_pass_def": "Run-v-Pass-D",
    "identity_predictability": "Predict",
    "identity_one_dimensionality": "OneDim",
    "identity_playcalling_fit": "CallFit",
    "identity_scheme_constraint": "Constraint",
}
ROOTS_BY_NAME = {x.root_name: x for x in CATALOG if x.modifier is None}

SALIENCE_WEIGHTS: dict[str, float] = {
    "identity_rushing_attack": 1.00,
    "identity_passing_attack": 1.00,
    "identity_rushing_defense": 0.90,
    "identity_passing_defense": 0.90,
    "identity_offense_quality": 0.80,
    "identity_defense_quality": 0.80,
    "rush_rate": 1.00,
    "plays_per_possession": 0.55,
    "identity_explosive_vs_methodical": 0.65,
    "identity_offense_vs_defense": 0.55,
    "identity_run_vs_pass_off": 0.75,
    "identity_run_vs_pass_def": 0.55,
    "identity_predictability": 0.55,
    "identity_one_dimensionality": 0.55,
    "identity_playcalling_fit": 0.40,
    "identity_scheme_constraint": 0.55,
}


def _value(row: dict[str, Any], key: str) -> float | None:
    if key == "rush_rate":
        raw = row.get("current_rush_rate_percentile", row.get("rush_rate"))
    elif key == "plays_per_possession":
        raw = row.get("current_plays_per_possession_percentile", row.get("plays_per_possession"))
    else:
        raw = row.get(key)
    return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None


def _snapshot_profile(row: dict[str, Any]) -> dict[str, float | None]:
    return {key: _value(row, key) for key in PROFILE_FIELDS}


def _mean_profile(profiles: list[dict[str, float | None]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key in PROFILE_FIELDS:
        vals = [float(x[key]) for x in profiles if isinstance(x.get(key), (int, float))]
        out[key] = mean(vals) if vals else None
    return out


def _profile_row(profile: dict[str, float | None]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in profile.items():
        if key == "rush_rate":
            row["current_rush_rate_percentile"] = value
        elif key == "plays_per_possession":
            row["current_plays_per_possession_percentile"] = value
        else:
            row[key] = value
    return row


def _neutral(key: str) -> float:
    return 0.0 if key in SIGNED_FIELDS else 50.0


def _salience(key: str, actual: float) -> float:
    scale = 100.0 if key in SIGNED_FIELDS else 50.0
    return SALIENCE_WEIGHTS.get(key, 0.0) * min(1.0, abs(actual - _neutral(key)) / scale)


def _profile_coverage(row: dict[str, Any], target_keys: set[str]) -> float:
    total = covered = 0.0
    for key in SALIENCE_WEIGHTS:
        actual = _value(row, key)
        if actual is None:
            continue
        contribution = _salience(key, actual)
        total += contribution
        if key in target_keys:
            covered += contribution
    return min(1.0, covered / total) if total > 1e-12 else 0.0


def _specificity_factor(dimensions: int) -> float:
    return min(1.0, 0.60 + 0.08 * max(0, dimensions))


def _tolerance(key: str) -> float:
    return 36.0 if key in SIGNED_FIELDS else 24.0


def _contradiction(key: str, actual: float, target: float) -> bool:
    if key in SIGNED_FIELDS:
        return (target >= 25.0 and actual <= -10.0) or (target <= -25.0 and actual >= 10.0)
    return (target >= 70.0 and actual <= 40.0) or (target <= 30.0 and actual >= 60.0)


def score_candidate(row: dict[str, Any], candidate: ArchetypeCandidate, *, min_dimensions: int = 3) -> dict[str, Any] | None:
    weighted_sq = weight_sum = 0.0
    used: list[dict[str, float]] = []
    contradictions = 0
    for key, target in candidate.targets.items():
        actual = _value(row, key)
        if actual is None:
            continue
        tolerance = _tolerance(key)
        weight = float(candidate.weights.get(key, 1.0))
        standardized = (actual - float(target)) / tolerance
        weighted_sq += weight * standardized * standardized
        weight_sum += weight
        if _contradiction(key, actual, float(target)):
            contradictions += 1
        used.append({
            "attribute": key,
            "actual": actual,
            "target": float(target),
            "delta": actual - float(target),
            "standardizedDelta": standardized,
        })
    if len(used) < min_dimensions or weight_sum <= 0:
        return None
    rms = math.sqrt(weighted_sq / weight_sum)
    fit_similarity = 100.0 * math.exp(-0.5 * rms * rms)
    if contradictions:
        fit_similarity *= 0.72 ** contradictions
    coverage = _profile_coverage(row, {x["attribute"] for x in used})
    specificity = _specificity_factor(len(used))
    identity_similarity = fit_similarity * (0.45 + 0.55 * coverage) * specificity
    used.sort(key=lambda x: abs(x["standardizedDelta"]))
    return {
        "id": candidate.id,
        "name": candidate.name,
        "family": candidate.family,
        "rootName": candidate.root_name,
        "modifier": candidate.modifier,
        "similarity": identity_similarity,
        "localFitSimilarity": fit_similarity,
        "profileCoverage": coverage,
        "specificityFactor": specificity,
        "dimensionsUsed": len(used),
        "contradictions": contradictions,
        "closestAttributes": used[:4],
        "largestMismatches": list(reversed(used[-3:])),
    }


def match_snapshot(row: dict[str, Any], *, top_n: int = 5, min_dimensions: int = 3) -> list[dict[str, Any]]:
    root_scores: dict[str, dict[str, Any]] = {}
    for root_name, root in ROOTS_BY_NAME.items():
        score = score_candidate(row, root, min_dimensions=min(2, min_dimensions))
        if score is not None:
            root_scores[root_name] = score
    scored = []
    for candidate in CATALOG:
        score = score_candidate(row, candidate, min_dimensions=min_dimensions)
        if score is None:
            continue
        root = root_scores.get(candidate.root_name)
        if root is None:
            continue
        score["variantSimilarity"] = float(score["similarity"])
        score["rootSimilarity"] = float(root["similarity"])
        score["rootLocalFitSimilarity"] = root["localFitSimilarity"]
        score["rootProfileCoverage"] = root["profileCoverage"]
        score["similarity"] = 0.82 * float(root["similarity"]) + 0.18 * float(score["similarity"])
        scored.append(score)
    scored.sort(key=lambda x: (-x["similarity"], x["contradictions"], -x["rootProfileCoverage"], -x["dimensionsUsed"], x["id"]))
    best_by_root: dict[str, dict[str, Any]] = {}
    for score in scored:
        best_by_root.setdefault(str(score["rootName"]), score)
    return sorted(best_by_root.values(), key=lambda x: (-x["similarity"], x["contradictions"], -x["rootProfileCoverage"], -x["dimensionsUsed"], x["id"]))[:top_n]


def match_history(rows: list[dict[str, Any]], *, seasons: tuple[int, ...] = DEFAULT_SEASONS, top_n: int = 5, min_dimensions: int = 3) -> dict[str, Any]:
    wanted = {int(s) for s in seasons}
    matched = []
    for row in rows:
        season = int(row.get("season", -1))
        if season not in wanted:
            continue
        top = match_snapshot(row, top_n=top_n, min_dimensions=min_dimensions)
        if not top:
            continue
        matched.append({
            "season": season,
            "team": row.get("team"),
            "seasonType": row.get("seasonType"),
            "week": row.get("week"),
            "throughGameId": row.get("throughGameId"),
            "gamesPlayed": row.get("gamesPlayed"),
            "profile": _snapshot_profile(row),
            "topMatches": top,
        })

    by_team_season: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for item in matched:
        by_team_season[(int(item["season"]), str(item["team"]))].append(item)

    season_summaries = []
    for (season, team), items in sorted(by_team_season.items()):
        items.sort(key=lambda x: (str(x.get("seasonType") or "regular"), int(x.get("week") or 0), int(x.get("gamesPlayed") or 0)))
        season_profile = _mean_profile([x["profile"] for x in items])
        season_matches = match_snapshot(_profile_row(season_profile), top_n=top_n, min_dimensions=min_dimensions)
        primary = [x["topMatches"][0] for x in items]
        root_counts = Counter(x["rootName"] for x in primary)
        dominant_root, dominant_root_count = root_counts.most_common(1)[0]
        dominant_candidates = [x for x in primary if x["rootName"] == dominant_root]
        best_weekly_variant = max(dominant_candidates, key=lambda x: x["similarity"])
        season_summaries.append({
            "season": season,
            "team": team,
            "snapshotCount": len(items),
            "profile": season_profile,
            "seasonProfileMatches": season_matches,
            "dominantRootName": dominant_root,
            "dominantRootShare": dominant_root_count / len(items),
            "bestDominantRootVariant": best_weekly_variant,
            "finalArchetype": items[-1]["topMatches"][0],
            "meanPrimarySimilarity": mean(x["similarity"] for x in primary),
            "primaryRootCounts": dict(root_counts),
        })

    return {
        "version": MATCH_VERSION,
        "catalogVersion": CATALOG_VERSION,
        "catalogSize": len(CATALOG),
        "seasons": sorted(wanted),
        "snapshotCount": len(matched),
        "teamSeasonCount": len(season_summaries),
        "topN": top_n,
        "matches": matched,
        "teamSeasonSummaries": season_summaries,
    }


def _fmt(v: Any) -> str:
    return "NA" if not isinstance(v, (int, float)) else f"{float(v):.0f}"


def _comparison_text(match: dict[str, Any]) -> str:
    supports = ", ".join(
        f"{PROFILE_LABELS.get(x['attribute'], x['attribute'])} {_fmt(x['actual'])}~{_fmt(x['target'])}"
        for x in match.get("closestAttributes", [])[:3]
    ) or "none"
    mismatches = ", ".join(
        f"{PROFILE_LABELS.get(x['attribute'], x['attribute'])} {_fmt(x['actual'])} vs {_fmt(x['target'])}"
        for x in match.get("largestMismatches", [])[:2]
    ) or "none"
    return f"supports: {supports} | mismatches: {mismatches}"


def concise(report: dict[str, Any], *, examples: int = 20) -> str:
    lines = [
        "HISTORICAL 2K ARCHETYPE MATCHING — STATS FIRST",
        f"Catalog: {report['catalogSize']:,} candidates",
        f"Seasons: {report['seasons'][0]}-{report['seasons'][-1]} (2020 absent by corpus design)",
        f"Matched snapshots: {report['snapshotCount']:,}",
        f"Team-seasons: {report['teamSeasonCount']:,}",
        "",
        "Sample team-season profiles and candidate matches:",
    ]
    for x in report["teamSeasonSummaries"][:examples]:
        p = x["profile"]
        a = x["seasonProfileMatches"][0] if x["seasonProfileMatches"] else x["bestDominantRootVariant"]
        lines.append(f"{x['season']} {x['team']}")
        lines.append(
            "  STATS | "
            f"RushAtk={_fmt(p.get('identity_rushing_attack'))} PassAtk={_fmt(p.get('identity_passing_attack'))} "
            f"OffQ={_fmt(p.get('identity_offense_quality'))} | "
            f"RunDef={_fmt(p.get('identity_rushing_defense'))} PassDef={_fmt(p.get('identity_passing_defense'))} "
            f"DefQ={_fmt(p.get('identity_defense_quality'))}"
        )
        lines.append(
            "        | "
            f"RushTend={_fmt(p.get('rush_rate'))} DriveLen={_fmt(p.get('plays_per_possession'))} "
            f"Expl-v-Method={_fmt(p.get('identity_explosive_vs_methodical'))} "
            f"Off-v-Def={_fmt(p.get('identity_offense_vs_defense'))} "
            f"Predict={_fmt(p.get('identity_predictability'))} Constraint={_fmt(p.get('identity_scheme_constraint'))}"
        )
        lines.append(
            f"  MATCH | {a['name']} (root={a['rootName']}) score={a['similarity']:.1f} "
            f"coverage={a['rootProfileCoverage']:.0%}"
        )
        lines.append(f"        | {_comparison_text(a)}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--min-dimensions", type=int, default=3)
    p.add_argument("--seasons", nargs="+", type=int, default=list(DEFAULT_SEASONS))
    p.add_argument("--examples", type=int, default=20)
    args = p.parse_args()
    source = args.processed_root / "derived" / "profiles" / "identity_snapshots_v3_attack_scheme.json"
    if not source.exists():
        raise FileNotFoundError("build v3 attack/scheme snapshots first: python -m cfb_analytics.profiles.snapshots")
    report = match_history(json.loads(source.read_text()), seasons=tuple(args.seasons), top_n=args.top_n, min_dimensions=args.min_dimensions)
    target = args.processed_root / "derived" / "profiles" / "historical_archetype_matches_2014_2024.json"
    target.write_text(json.dumps(report, separators=(",", ":")))
    print(concise(report, examples=args.examples))


if __name__ == "__main__":
    main()
