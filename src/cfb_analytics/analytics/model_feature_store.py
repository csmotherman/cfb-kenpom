"""Persist model-ready football features once; experiments only read these rows."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from cfb_analytics.analytics.authoritative_game_targets import (
    TARGET_SOURCE_VERSION,
    apply_authoritative_targets,
    load_authoritative_games,
)
from cfb_analytics.analytics.iterative_ratings import (
    ENRICHED_DATASET_VERSION,
    ITERATIVE_RATINGS_VERSION,
    SRS_VERSION,
    build_srs_model_dataset,
    materialize_iterative_model_dataset,
)
from cfb_analytics.analytics.cfb_sandbox_systems_aligned import SANDBOX_SYSTEMS_VERSION
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS
from cfb_analytics.derived.sandbox_pregame import (
    MATCHUP_VERSION,
    PREGAME_VERSION,
    SYSTEMS,
    materialize_sandbox_pregame,
)

FEATURE_STORE_VERSION = "model-feature-store-v2-authoritative-targets"


def _root(processed_root: Path, season: int) -> Path:
    return processed_root / "derived" / "model_feature_store" / f"season={season}"


def _orient(row: dict, matchup: dict) -> dict | None:
    home, away = row.get("homeTeam"), row.get("awayTeam")
    if {home, away} != {matchup.get("team1"), matchup.get("team2")}:
        return None
    prefix = "team1" if home == matchup.get("team1") else "team2"
    out = dict(row)
    for system in SYSTEMS:
        out[f"home_{system}_OffenseEdge"] = matchup.get(f"{prefix}_{system}_OffenseEdge")
        out[f"home_{system}_DefenseEdge"] = matchup.get(f"{prefix}_{system}_DefenseEdge")
    out["modelFeatureStoreVersion"] = FEATURE_STORE_VERSION
    out["sandboxSystemsVersion"] = SANDBOX_SYSTEMS_VERSION
    out["sandboxPregameVersion"] = PREGAME_VERSION
    out["sandboxMatchupVersion"] = MATCHUP_VERSION
    return out


def materialize_feature_store(raw_root: Path, processed_root: Path, season: int, refresh: bool = False) -> dict:
    root = _root(processed_root, season)
    path = root / "games.json"
    manifest_path = root / "manifest.json"

    if not refresh and path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest.get("modelFeatureStoreVersion") == FEATURE_STORE_VERSION
            and manifest.get("targetSourceVersion") == TARGET_SOURCE_VERSION
            and manifest.get("iterativeRatingsVersion") == ITERATIVE_RATINGS_VERSION
            and manifest.get("srsVersion") == SRS_VERSION
            and manifest.get("sandboxSystemsVersion") == SANDBOX_SYSTEMS_VERSION
            and manifest.get("sandboxPregameVersion") == PREGAME_VERSION
            and manifest.get("sandboxMatchupVersion") == MATCHUP_VERSION
        ):
            return {
                "season": season,
                "status": "REUSED",
                "rows": manifest.get("recordCount", 0),
                "target_rows_changed": manifest.get("targetRowsChanged", 0),
                "path": str(path),
            }

    # Reuse the expensive iterative football ratings cache. Its non-score
    # features are still valid. Replace targets from raw CFBD games and then
    # recompute SRS because SRS is the score-dependent feature family.
    iterative = materialize_iterative_model_dataset(raw_root, processed_root, season, refresh=refresh)
    if iterative["status"] != "PASS":
        raise RuntimeError(f"season {season} iterative audit failed: {iterative['checks']}")
    sandbox = materialize_sandbox_pregame(raw_root, processed_root, season, refresh=refresh)

    iterative_rows = json.loads((processed_root / "derived" / "iterative_ratings" / f"season={season}" / "games.json").read_text())
    authoritative_games = load_authoritative_games(raw_root, season)
    iterative_rows, target_report = apply_authoritative_targets(iterative_rows, authoritative_games)
    iterative_rows = build_srs_model_dataset(iterative_rows, season)

    matchups = {str(r.get("gameId")): r for r in sandbox["matchups"]}
    rows = []
    for row in iterative_rows:
        matchup = matchups.get(str(row.get("gameId")))
        if not matchup:
            continue
        merged = _orient(row, matchup)
        if merged is not None:
            rows.append(merged)

    if any(row.get("targetSourceVersion") != TARGET_SOURCE_VERSION for row in rows):
        raise RuntimeError(f"season {season} feature store contains a non-authoritative target source")

    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    manifest = {
        "season": season,
        "recordCount": len(rows),
        "modelFeatureStoreVersion": FEATURE_STORE_VERSION,
        "targetSourceVersion": TARGET_SOURCE_VERSION,
        "targetRowsChanged": target_report["changedRows"],
        "enrichedDatasetVersion": ENRICHED_DATASET_VERSION,
        "iterativeRatingsVersion": ITERATIVE_RATINGS_VERSION,
        "srsVersion": SRS_VERSION,
        "sandboxSystemsVersion": SANDBOX_SYSTEMS_VERSION,
        "sandboxPregameVersion": PREGAME_VERSION,
        "sandboxMatchupVersion": MATCHUP_VERSION,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return {
        "season": season,
        "status": "WRITTEN",
        "rows": len(rows),
        "target_rows_changed": target_report["changedRows"],
        "path": str(path),
    }


def load_saved_feature_store(processed_root: Path, season: int) -> list[dict]:
    root = _root(processed_root, season)
    path = root / "games.json"
    manifest_path = root / "manifest.json"
    if not path.exists() or not manifest_path.exists():
        raise FileNotFoundError(
            f"Feature store missing for {season}. Build it once with: "
            f"python -m cfb_analytics.analytics.model_feature_store --season {season}"
        )
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("modelFeatureStoreVersion") != FEATURE_STORE_VERSION:
        raise RuntimeError(f"Feature store for {season} has stale version; rebuild it once.")
    if manifest.get("targetSourceVersion") != TARGET_SOURCE_VERSION:
        raise RuntimeError(f"Feature store for {season} has stale target source; rebuild it once.")
    return json.loads(path.read_text())


def _build_one(args: tuple[str, str, int, bool]) -> dict:
    raw_root, processed_root, season, refresh = args
    return materialize_feature_store(Path(raw_root), Path(processed_root), season, refresh)


def build_all(raw_root: Path, processed_root: Path, seasons=DEFAULT_SEASONS, refresh: bool = False, workers: int = 4) -> list[dict]:
    jobs = [(str(raw_root), str(processed_root), int(season), refresh) for season in seasons]
    out = []
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
        futures = {pool.submit(_build_one, job): job[2] for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            out.append(result)
            print(
                f"FEATURE STORE {result['season']}: {result['status']} rows={result['rows']:,} "
                f"target_changes={result.get('target_rows_changed', 0):,}",
                flush=True,
            )
    return sorted(out, key=lambda r: r["season"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    if args.all:
        build_all(args.raw_root, args.processed_root, refresh=args.refresh, workers=args.workers)
    elif args.season:
        result = materialize_feature_store(args.raw_root, args.processed_root, args.season, args.refresh)
        print(
            f"FEATURE STORE {result['season']}: {result['status']} rows={result['rows']:,} "
            f"target_changes={result.get('target_rows_changed', 0):,}"
        )
    else:
        parser.error("choose --season YYYY or --all")


if __name__ == "__main__":
    main()
