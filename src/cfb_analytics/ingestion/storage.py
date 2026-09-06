"""Storage contract for broad FBS-team fact data."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdResponse

FACT_NAMESPACE = "cfbd_facts"
FACT_UNIVERSE = "games_with_at_least_one_fbs_team"


def fact_partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / FACT_NAMESPACE / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def verify_fact_manifest(directory: Path, entity: str) -> bool:
    data_path = directory / f"{entity}.json"
    manifest_path = directory / f"{entity}.manifest.json"
    if not data_path.exists() or not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text())
    return (
        manifest.get("universe") == FACT_UNIVERSE
        and manifest.get("namespace") == FACT_NAMESPACE
        and hashlib.sha256(data_path.read_bytes()).hexdigest() == manifest.get("sha256")
    )


def store_fact_response(
    root: Path,
    *,
    season: int,
    season_type: str,
    week: int,
    entity: str,
    response: CfbdResponse,
    force: bool = False,
) -> dict[str, Any]:
    directory = fact_partition_dir(root, season, season_type, week)
    directory.mkdir(parents=True, exist_ok=True)
    data_path = directory / f"{entity}.json"
    manifest_path = directory / f"{entity}.manifest.json"
    if not force and verify_fact_manifest(directory, entity):
        return {**json.loads(manifest_path.read_text()), "status": "REUSED"}
    data_path.write_bytes(response.raw_bytes)
    payload = response.payload
    manifest = {
        "source": "cfbd",
        "namespace": FACT_NAMESPACE,
        "universe": FACT_UNIVERSE,
        "season": season,
        "season_type": season_type,
        "week": week,
        "entity": entity,
        "request_url": response.url,
        "status_code": response.status_code,
        "stored_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(payload) if isinstance(payload, list) else None,
        "fields_first_record": list(payload[0]) if isinstance(payload, list) and payload and isinstance(payload[0], dict) else [],
        "sha256": hashlib.sha256(response.raw_bytes).hexdigest(),
        "file": data_path.name,
        "status": "WRITTEN",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest

