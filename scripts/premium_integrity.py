"""Shared integrity helpers for premium JSON stored in PostgreSQL jsonb.

Postgres jsonb normalizes number spelling (1.0 -> 1, -0.0 -> 0, trailing
zeroes disappear). Integrity hashes therefore must be based on semantic JSON,
not the byte spelling that happened to be uploaded.
"""
from __future__ import annotations

import hashlib
import json
import math

HASH_PREFIX = "v2:"


def _jsonb_normalize(value):
    if isinstance(value, dict):
        return {str(key): _jsonb_normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonb_normalize(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Premium JSON contains a non-finite number")
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    raise TypeError(f"Unsupported premium JSON value type: {type(value).__name__}")


def payload_hash(payload) -> str:
    normalized = _jsonb_normalize(payload)
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return HASH_PREFIX + hashlib.sha256(canonical).hexdigest()


def is_versioned_hash(value) -> bool:
    return isinstance(value, str) and value.startswith(HASH_PREFIX) and len(value) == len(HASH_PREFIX) + 64
