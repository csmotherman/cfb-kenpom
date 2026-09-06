"""Hierarchical discovery of recurring historical football identities.

Stage 1 finds broad families. Stage 2 splits each family into sub-archetypes.
Identity clustering uses opponent-adjusted quality plus style/shape contrasts so
bad, one-dimensional, defense-only and otherwise unusual teams can form real
archetypes instead of collapsing into generic low-quality clusters.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

DISCOVERY_VERSION = "historical-archetype-discovery-v2-hierarchical-oa"
QUALITY_FIELDS = (
    "current_oa_run_efficiency_off_percentile", "current_oa_pass_efficiency_off_percentile",
    "current_oa_success_off_percentile", "current_oa_explosiveness_off_percentile",
    "current_oa_third_down_off_percentile", "current_oa_finishing_off_percentile",
    "current_oa_run_efficiency_def_percentile", "current_oa_pass_efficiency_def_percentile",
    "current_oa_success_def_percentile", "current_oa_explosiveness_def_percentile",
    "current_oa_third_down_def_percentile", "current_oa_finishing_def_percentile",
)
STYLE_FIELDS = (
    "current_rush_rate_percentile", "current_pass_rate_percentile", "current_plays_per_possession_percentile",
)
SHAPE_FIELDS = (
    "identity_run_vs_pass_off", "identity_run_vs_pass_def", "identity_explosive_vs_methodical",
    "identity_finishing_vs_foundation", "identity_offense_vs_defense", "identity_rush_vs_pass_tendency",
)


def _coverage(rows: list[dict[str, Any]], field: str) -> float:
    return sum(isinstance(r.get(field), (int, float)) for r in rows) / len(rows) if rows else 0.0


def _features(rows: list[dict[str, Any]], min_coverage: float) -> list[str]:
    ordered = list(QUALITY_FIELDS + STYLE_FIELDS + SHAPE_FIELDS)
    return [f for f in ordered if _coverage(rows, f) >= min_coverage]


def _matrix(rows: list[dict[str, Any]], features: list[str]):
    kept, x = [], []
    for r in rows:
        vals = [r.get(f) for f in features]
        if all(isinstance(v, (int, float)) for v in vals):
            kept.append(r)
            x.append([float(v) for v in vals])
    return kept, np.asarray(x, dtype=float)


def _team_season_weights(rows: list[dict[str, Any]]) -> np.ndarray:
    counts: dict[tuple[int, str], int] = {}
    for r in rows:
        key = (int(r["season"]), str(r["team"]))
        counts[key] = counts.get(key, 0) + 1
    return np.asarray([1.0 / counts[(int(r["season"]), str(r["team"]))] for r in rows], dtype=float)


def _best_k(z: np.ndarray, k_values: range, *, random_state: int, min_cluster: int) -> tuple[int, list[dict[str, Any]]]:
    trials = []
    for k in k_values:
        if k >= len(z):
            break
        labels = KMeans(n_clusters=k, n_init=20, random_state=random_state).fit_predict(z)
        counts = np.bincount(labels, minlength=k)
        sil = silhouette_score(z, labels, sample_size=min(5000, len(z)), random_state=random_state)
        small = int(counts.min())
        penalty = max(0.0, (min_cluster - small) / max(1, min_cluster)) * 0.08
        # Small complexity reward prevents silhouette from always collapsing to the coarsest answer.
        score = float(sil) - penalty + 0.003 * k
        trials.append({"k": k, "silhouette": float(sil), "smallestCluster": small, "score": score})
    if not trials:
        raise ValueError("no valid cluster counts")
    return max(trials, key=lambda x: x["score"])["k"], trials


def _describe_cluster(cluster_id: str, idx: np.ndarray, rows: list[dict[str, Any]], features: list[str], center_raw: np.ndarray, distances: np.ndarray) -> dict[str, Any]:
    center = {features[i]: float(center_raw[i]) for i in range(len(features))}
    traits = sorted(center.items(), key=lambda kv: abs(kv[1] - 50.0), reverse=True)[:10]
    nearest = idx[np.argsort(distances[idx])[:6]]
    exemplars = [
        {
            "season": int(rows[i]["season"]),
            "team": rows[i]["team"],
            "week": rows[i].get("week"),
            "gamesPlayed": rows[i].get("gamesPlayed"),
            "distance": float(distances[i]),
        }
        for i in nearest
    ]
    return {
        "id": cluster_id,
        "snapshotCount": int(len(idx)),
        "signatureTraits": [{"metric": k, "value": v} for k, v in traits],
        "exemplars": exemplars,
        "fanName": None,
        "fanDescription": None,
    }


def discover_archetypes(
    rows: list[dict[str, Any]], *, family_k: int = 6, sub_k_min: int = 2,
    sub_k_max: int = 5, min_coverage: float = 0.82, min_cluster: int = 120,
    min_snapshots: int = 500, random_state: int = 20260815,
) -> dict[str, Any]:
    """Discover broad families and sub-archetypes from opponent-adjusted snapshots.

    ``min_snapshots`` is a production safety guard. The default remains 500 for
    corpus runs; unit tests may lower it for synthetic fixtures without weakening
    the production CLI behavior.
    """
    features = _features(rows, min_coverage)
    kept, x = _matrix(rows, features)
    if len(features) < 8:
        raise ValueError("insufficient opponent-adjusted identity dimensions")
    if len(kept) < min_snapshots:
        raise ValueError(f"not enough historical snapshots: {len(kept)} < {min_snapshots}")
    if family_k < 2 or family_k >= len(kept):
        raise ValueError("family_k must be at least 2 and smaller than the snapshot count")

    scaler = StandardScaler()
    z = scaler.fit_transform(x)
    weights = _team_season_weights(kept)

    family_model = KMeans(n_clusters=family_k, n_init=50, random_state=random_state)
    family_labels = family_model.fit_predict(z, sample_weight=weights)
    assignments = []
    families = []
    total_archetypes = 0
    for family in range(family_k):
        idx = np.flatnonzero(family_labels == family)
        family_z = z[idx]
        max_sub = min(sub_k_max, max(sub_k_min, len(idx) // max(1, min_cluster)))
        candidate = range(sub_k_min, max_sub + 1)
        sub_k, trials = _best_k(
            family_z,
            candidate,
            random_state=random_state + family,
            min_cluster=max(20, min_cluster // family_k),
        )
        sub_model = KMeans(n_clusters=sub_k, n_init=40, random_state=random_state + 100 + family)
        sub_labels = sub_model.fit_predict(family_z, sample_weight=weights[idx])
        centers = []
        for sub in range(sub_k):
            local = np.flatnonzero(sub_labels == sub)
            global_idx = idx[local]
            center_z = sub_model.cluster_centers_[sub]
            center_raw = scaler.inverse_transform(center_z.reshape(1, -1))[0]
            dist = np.linalg.norm(z - center_z, axis=1)
            cid = f"F{family:02d}-A{sub:02d}"
            desc = _describe_cluster(cid, global_idx, kept, features, center_raw, dist)
            desc["share"] = float(len(global_idx) / len(kept))
            centers.append(desc)
            total_archetypes += 1
            for gi in global_idx:
                assignments.append({
                    "season": kept[gi]["season"],
                    "team": kept[gi]["team"],
                    "seasonType": kept[gi].get("seasonType"),
                    "week": kept[gi].get("week"),
                    "gamesPlayed": kept[gi].get("gamesPlayed"),
                    "family": family,
                    "archetype": cid,
                })
        families.append({
            "family": family,
            "snapshotCount": int(len(idx)),
            "share": float(len(idx) / len(kept)),
            "selectedSubclusters": sub_k,
            "subclusterTrials": trials,
            "archetypes": centers,
        })

    return {
        "version": DISCOVERY_VERSION,
        "snapshotCount": len(kept),
        "availableSnapshotCount": len(rows),
        "features": features,
        "familyCount": family_k,
        "archetypeCount": total_archetypes,
        "families": families,
        "assignments": assignments,
        "weighting": "equal total weight per team-season",
        "qualityPolicy": "quality dimensions opponent-adjusted; style dimensions descriptive; identity includes quality contrasts",
    }


def concise(r: dict[str, Any]) -> str:
    lines = [
        "HISTORICAL ARCHETYPE DISCOVERY v2",
        f"Snapshots used: {r['snapshotCount']:,}/{r['availableSnapshotCount']:,}",
        f"Dimensions: {len(r['features'])}",
        f"Broad families: {r['familyCount']}",
        f"Final archetypes: {r['archetypeCount']}",
        "",
    ]
    for fam in r["families"]:
        lines.append(f"F{fam['family']:02d} | {fam['share']:.1%} | sub-archetypes={fam['selectedSubclusters']}")
        for a in fam["archetypes"]:
            traits = ", ".join(
                f"{x['metric'].replace('current_', '').replace('_percentile', '')}={x['value']:.0f}"
                for x in a["signatureTraits"][:5]
            )
            ex = "; ".join(f"{x['season']} {x['team']} W{x['week']}" for x in a["exemplars"][:3])
            lines.append(f"  {a['id']} | {a['share']:.1%} | {traits} | {ex}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    p.add_argument("--family-k", type=int, default=6)
    p.add_argument("--sub-k-min", type=int, default=2)
    p.add_argument("--sub-k-max", type=int, default=5)
    p.add_argument("--min-coverage", type=float, default=0.82)
    a = p.parse_args()
    source = a.processed_root / "derived" / "profiles" / "identity_snapshots_v2_oa.json"
    if not source.exists():
        raise FileNotFoundError("build OA identity snapshots first: python -m cfb_analytics.profiles.snapshots")
    report = discover_archetypes(
        json.loads(source.read_text()),
        family_k=a.family_k,
        sub_k_min=a.sub_k_min,
        sub_k_max=a.sub_k_max,
        min_coverage=a.min_coverage,
    )
    target = a.processed_root / "derived" / "profiles" / "archetype_discovery_v2_oa.json"
    target.write_text(json.dumps(report, indent=2))
    print(concise(report))


if __name__ == "__main__":
    main()
