"""Provenance tracking and a numeric-claim guardrail for generated social text.

Generators build caption text and a matching `sources` list side-by-side (see
templates.py) rather than formatting a template against a loosely-typed
context dict, so every value that ends up in the text is already paired with
its origin by construction. assert_numbers_are_sourced() is defense in depth
on top of that: it extracts every digit run in the final text and confirms
each also appears somewhere in the sources' values, so an accidentally
hand-typed or invented number fails generation instead of silently shipping.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

_DIGIT_RUN = re.compile(r"\d+")


@dataclass(frozen=True)
class SourceRef:
    """One factual claim in generated text, traced to the file/field it came from."""

    file: str
    field: str
    value: Any
    team: str | None = None
    game_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"file": self.file, "field": self.field, "value": self.value}
        if self.team is not None:
            out["team"] = self.team
        if self.game_id is not None:
            out["game_id"] = self.game_id
        return out


def _all_digit_runs(*blobs: Any) -> set[str]:
    found: set[str] = set()
    for blob in blobs:
        text = blob if isinstance(blob, str) else json.dumps(blob, default=str)
        found.update(_DIGIT_RUN.findall(text))
    return found


def assert_numbers_are_sourced(
    text: str,
    sources: list[SourceRef],
    *,
    allowed_unsourced: frozenset[str] = frozenset(),
) -> None:
    """Raise ValueError if `text` contains a digit run traceable to nothing in
    `sources`. `allowed_unsourced` is only for fixed structural/brand numbers
    that are not a per-run fact (e.g. "25" in the "PRIME 25" name).
    """
    text_numbers = _all_digit_runs(text)
    source_numbers = _all_digit_runs(*(ref.value for ref in sources))
    unexplained = text_numbers - source_numbers - set(allowed_unsourced)
    if unexplained:
        raise ValueError(
            f"Generated text contains number(s) not traceable to any source: {sorted(unexplained)}. "
            f"text={text!r}"
        )


def content_hash(text_content: str, sources: list[SourceRef]) -> str:
    canonical = json.dumps(
        {"text": text_content, "sources": [ref.to_dict() for ref in sources]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return "v1:" + hashlib.sha256(canonical).hexdigest()
