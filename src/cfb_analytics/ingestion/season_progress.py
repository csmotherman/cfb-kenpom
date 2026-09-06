"""Durable, resumable progress records for national season ingestion."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROGRESS_VERSION = "national-season-ingestion-v1"


def progress_path(root: Path, season: int) -> Path:
    return root / f"season={season}" / "ingestion_state.json"


def read_progress(root: Path, season: int) -> dict[str, Any] | None:
    path = progress_path(root, season)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if payload.get("version") == PROGRESS_VERSION else None


def write_progress(root: Path, season: int, status: str, **details: Any) -> dict[str, Any]:
    payload = {
        "version": PROGRESS_VERSION,
        "season": season,
        "status": status,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    path = progress_path(root, season)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
