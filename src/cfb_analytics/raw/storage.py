"""Raw response storage and manifests."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdResponse


def partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / "cfbd" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")


def store_response(
    root: Path,
    *,
    season: int,
    season_type: str,
    week: int,
    entity: str,
    response: CfbdResponse,
    refresh: bool = False,
) -> dict[str, Any]:
    directory = partition_dir(root, season, season_type, week)
    directory.mkdir(parents=True, exist_ok=True)
    data_path = directory / f"{entity}.json"
    manifest_path = directory / f"{entity}.manifest.json"
    if data_path.exists() and manifest_path.exists() and not refresh:
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    # Persist valid JSON exactly as returned by the endpoint. httpx exposes the
    # decoded response body; checksum is over the bytes written to disk.
    written = response.raw_bytes
    data_path.write_bytes(written)
    checksum = hashlib.sha256(written).hexdigest()
    payload = response.payload
    fields: list[str] = []
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        fields = list(payload[0].keys())

    manifest = {
        "source": "cfbd",
        "season": season,
        "season_type": season_type,
        "week": week,
        "entity": entity,
        "request_url": response.url,
        "status_code": response.status_code,
        "stored_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(payload) if isinstance(payload, list) else None,
        "fields_first_record": fields,
        "sha256": checksum,
        "file": data_path.name,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(directory: Path, entity: str) -> bool:
    data_path = directory / f"{entity}.json"
    manifest_path = directory / f"{entity}.manifest.json"
    if not data_path.exists() or not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return hashlib.sha256(data_path.read_bytes()).hexdigest() == manifest.get("sha256")
