from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import pyarrow as _pa
    import pyarrow.parquet as _pq
except ImportError:
    _pa = None
    _pq = None


def write_records(path: Path, rows: list[dict[str, Any]]) -> list[Path]:
    """Write deterministic JSON and Parquet when the optional engine is installed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    json_path = path.with_suffix(".json")
    json_path.write_text(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    written = [json_path]
    if _pa is None or _pq is None:
        return written
    _pq.write_table(_pa.Table.from_pylist(rows), path, compression="zstd")
    written.append(path)
    return written
