"""Materialize canonical play partitions from immutable raw CFBD data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from cfb_analytics.canonical.corrections import CORRECTION_VERSION, promote_partition_yardage
from cfb_analytics.canonical.play_text_normalizer import TEXT_PARSE_VERSION
from cfb_analytics.canonical.play_types import RULES
from cfb_analytics.canonical.plays import normalize_play
from cfb_analytics.raw.audit import discover_partitions, partition_dir


def canonical_partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / "canonical" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def _taxonomy_fingerprint() -> str:
    payload = {
        "play_text_parse_version": TEXT_PARSE_VERSION,
        "yardage_correction_version": CORRECTION_VERSION,
        "play_type_rules": {
            name: {
                "category": rule.category,
                "subtype": rule.subtype,
                "is_scrimmage": rule.is_scrimmage,
                "is_offensive_play": rule.is_offensive_play,
                "is_administrative": rule.is_administrative,
                "is_special_teams": rule.is_special_teams,
                "is_penalty": rule.is_penalty,
                "is_turnover": rule.is_turnover,
                "force_analytics_yards_zero": rule.force_analytics_yards_zero,
            }
            for name, rule in sorted(RULES.items())
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def materialize_partition(raw_root: Path, processed_root: Path, season: int, season_type: str, week: int, refresh: bool = False) -> dict:
    source_dir = partition_dir(raw_root, season, season_type, week)
    source_path = source_dir / "plays.json"
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    target_dir = canonical_partition_dir(processed_root, season, season_type, week)
    target_path = target_dir / "plays.json"
    manifest_path = target_dir / "plays.manifest.json"
    source_bytes = source_path.read_bytes()
    source_sha = _sha256_bytes(source_bytes)
    taxonomy_sha = _taxonomy_fingerprint()

    if not refresh and target_path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_sha256") == source_sha and manifest.get("taxonomy_sha256") == taxonomy_sha:
            return {**manifest, "status": "REUSED"}

    source_rows = json.loads(source_bytes)
    canonical_rows = [normalize_play(row) for row in source_rows]
    canonical_rows = promote_partition_yardage(canonical_rows)
    canonical_bytes = json.dumps(canonical_rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    canonical_sha = _sha256_bytes(canonical_bytes)
    corrected_count = sum(bool(row.get("analyticsYardsWasCorrected")) for row in canonical_rows)
    manifest = {
        "entity": "plays",
        "layer": "canonical",
        "season": season,
        "season_type": season_type,
        "week": week,
        "record_count": len(canonical_rows),
        "source_record_count": len(source_rows),
        "source_path": str(source_path),
        "source_sha256": source_sha,
        "canonical_sha256": canonical_sha,
        "taxonomy_sha256": taxonomy_sha,
        "play_text_parse_version": TEXT_PARSE_VERSION,
        "yardage_correction_version": CORRECTION_VERSION,
        "yardage_corrections_applied": corrected_count,
        "format": "json",
        "raw_immutable": True,
    }
    _atomic_write(target_path, canonical_bytes)
    _atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
    return {**manifest, "status": "WRITTEN"}


def materialize_corpus(raw_root: Path, processed_root: Path, seasons: Iterable[int], refresh: bool = False) -> list[dict]:
    results = []
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            results.append(materialize_partition(raw_root, processed_root, season, season_type, week, refresh=refresh))
    return results


def verify_canonical_partition(raw_root: Path, processed_root: Path, season: int, season_type: str, week: int) -> dict:
    source_path = partition_dir(raw_root, season, season_type, week) / "plays.json"
    target_dir = canonical_partition_dir(processed_root, season, season_type, week)
    target_path = target_dir / "plays.json"
    manifest_path = target_dir / "plays.manifest.json"
    checks = {
        "source_exists": source_path.exists(),
        "canonical_exists": target_path.exists(),
        "manifest_exists": manifest_path.exists(),
    }
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if all(checks.values()):
        source_rows = json.loads(source_path.read_text())
        canonical_rows = json.loads(target_path.read_text())
        corrected_count = sum(bool(row.get("analyticsYardsWasCorrected")) for row in canonical_rows)
        checks.update({
            "record_count_matches_source": len(source_rows) == len(canonical_rows),
            "manifest_record_count_matches": manifest.get("record_count") == len(canonical_rows),
            "source_hash_matches": manifest.get("source_sha256") == _sha256_bytes(source_path.read_bytes()),
            "canonical_hash_matches": manifest.get("canonical_sha256") == _sha256_bytes(target_path.read_bytes()),
            "taxonomy_hash_matches": manifest.get("taxonomy_sha256") == _taxonomy_fingerprint(),
            "play_text_parse_version_matches": manifest.get("play_text_parse_version") == TEXT_PARSE_VERSION,
            "yardage_correction_version_matches": manifest.get("yardage_correction_version") == CORRECTION_VERSION,
            "yardage_correction_count_matches": manifest.get("yardage_corrections_applied") == corrected_count,
            "all_source_ids_preserved": [str(x.get("id")) for x in source_rows] == [str(x.get("id")) for x in canonical_rows],
        })
    return {"season": season, "season_type": season_type, "week": week, "status": "PASS" if checks and all(checks.values()) else "REVIEW", "checks": checks}
