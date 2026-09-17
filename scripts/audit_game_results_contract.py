"""Fail CI when the completed-game Results contract becomes semantically misleading.

This audit is intentionally narrow.  The general cross-artifact audit validates
IDs, scores, symmetry, schemas, and schedule integrity; this one protects the
human-facing meaning of fields used by Game Results.

Rules:
* filtered PBP populations may not be exported under official-box-score names;
* 3rd-down success may never fall back to series conversion;
* drive share may not be called possession/time of possession;
* per-drive penalty/turnover counts may not be rendered as percentages;
* final Results must advance the leakage-safe pregame record exactly once;
* any already-published v2 artifact must satisfy the same row-level contract.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXPORTER = REPO / "scripts/export_team_game_advanced.py"
FRONTEND = REPO / "web/lib/team-game-advanced.ts"
RESULTS_SHEET = REPO / "web/components/GameResultsSheet.tsx"
PUBLIC_DIR = REPO / "web/public/data/team-game-advanced"

FORBIDDEN_EXPORT_KEYS = {
    "offensive_plays",
    "rush_attempts",
    "pass_attempts",
    "possession_share",
    "penalty_rate",
    "points_per_drive",
}
REQUIRED_EXPORT_KEYS = {
    "analytics_plays",
    "graded_rush_plays",
    "drive_share",
    "third_down_success_attempts",
    "third_down_successes",
    "third_down_success_rate",
    "fourth_down_success_attempts",
    "fourth_down_successes",
    "fourth_down_success_rate",
    "turnovers_per_drive",
    "offensive_penalties",
    "offensive_penalty_yards",
    "penalties_per_drive",
}


def fail(message: str) -> None:
    raise SystemExit(f"GAME RESULTS CONTRACT AUDIT FAILED: {message}")


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        fail(f"missing {needle!r} in {where}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        fail(f"forbidden {needle!r} found in {where}")


def audit_source() -> None:
    exporter = EXPORTER.read_text(encoding="utf-8")
    frontend = FRONTEND.read_text(encoding="utf-8")
    results_sheet = RESULTS_SHEET.read_text(encoding="utf-8")

    require(exporter, 'TEAM_GAME_ADVANCED_VERSION = "team-game-advanced-v2-results-contract"', str(EXPORTER))
    for key in REQUIRED_EXPORT_KEYS:
        require(exporter, f'"{key}":', str(EXPORTER))
    for key in FORBIDDEN_EXPORT_KEYS:
        # The old identifiers may appear in explanatory prose/tests elsewhere,
        # but they may not be materialized as primary export dictionary keys.
        forbid(exporter, f'"{key}":', str(EXPORTER))

    require(frontend, 'label: "3rd Down Success", key: "third_down_success_rate"', str(FRONTEND))
    forbid(frontend, 'label: "3rd Down Conversion"', str(FRONTEND))
    # Series conversion remains a valid separate exploratory metric; this guard
    # specifically prevents it from being used as a fallback for 3rd down.
    third_down_start = frontend.find('label: "3rd Down Success"')
    fourth_down_start = frontend.find('label: "4th Down Success"', third_down_start)
    if third_down_start < 0 or fourth_down_start < 0:
        fail("unable to locate 3rd/4th-down frontend specs")
    third_down_spec = frontend[third_down_start:fourth_down_start]
    forbid(third_down_spec, "series_conversion_rate", "3rd Down Success frontend spec")
    forbid(third_down_spec, "fallbackKeys", "3rd Down Success frontend spec")

    require(frontend, 'label: "Drive Share", key: "drive_share"', str(FRONTEND))
    forbid(frontend, 'label: "Possession Share"', str(FRONTEND))
    require(frontend, 'label: "Penalties / Drive"', str(FRONTEND))
    require(frontend, 'label: "Turnovers / Drive"', str(FRONTEND))
    forbid(frontend, 'label: "Penalty Rate"', str(FRONTEND))
    forbid(frontend, 'label: "Turnover Rate"', str(FRONTEND))
    forbid(frontend, 'label: "Points / Drive"', str(FRONTEND))
    forbid(frontend, 'label: "Rushes"', str(FRONTEND))
    forbid(frontend, 'label: "Plays"', str(FRONTEND))

    require(results_sheet, "export function postgameRecord", str(RESULTS_SHEET))
    require(results_sheet, "leftPostgameRecord", str(RESULTS_SHEET))
    require(results_sheet, "rightPostgameRecord", str(RESULTS_SHEET))
    forbid(results_sheet, "<small>{leftTeam.record}</small>", str(RESULTS_SHEET))
    forbid(results_sheet, "<small>{rightTeam.record}</small>", str(RESULTS_SHEET))


def audit_published_v2() -> int:
    """Validate any regenerated v2 artifacts without forcing v1 data to change in this PR.

    The branch can merge safely before the next live-data refresh because the
    frontend has exact-definition compatibility aliases for v1.  Once an
    artifact is regenerated as v2, CI validates its row shape here.
    """
    checked = 0
    if not PUBLIC_DIR.exists():
        return checked

    for path in sorted(PUBLIC_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != "team-game-advanced-v2-results-contract":
            continue
        checked += 1
        rows = payload.get("rows")
        if not isinstance(rows, list):
            fail(f"{path} v2 payload has no rows list")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                fail(f"{path} row {index} is not an object")
            overlap = FORBIDDEN_EXPORT_KEYS.intersection(row)
            if overlap:
                fail(f"{path} row {index} contains forbidden aliases: {sorted(overlap)}")
            missing = REQUIRED_EXPORT_KEYS.difference(row)
            if missing:
                fail(f"{path} row {index} is missing v2 keys: {sorted(missing)}")

            # Rows with missing exploratory data are allowed to carry nulls,
            # but never invented zeroes; key presence is the contract.
            if row.get("third_down_success_rate") is not None:
                attempts = row.get("third_down_success_attempts")
                successes = row.get("third_down_successes")
                if not isinstance(attempts, (int, float)) or attempts <= 0:
                    fail(f"{path} row {index} has 3rd-down rate without positive attempts")
                expected = successes / attempts
                if abs(expected - row["third_down_success_rate"]) > 1e-12:
                    fail(f"{path} row {index} has inconsistent 3rd-down success rate")

            if row.get("fourth_down_success_rate") is not None:
                attempts = row.get("fourth_down_success_attempts")
                successes = row.get("fourth_down_successes")
                if not isinstance(attempts, (int, float)) or attempts <= 0:
                    fail(f"{path} row {index} has 4th-down rate without positive attempts")
                expected = successes / attempts
                if abs(expected - row["fourth_down_success_rate"]) > 1e-12:
                    fail(f"{path} row {index} has inconsistent 4th-down success rate")

    return checked


def main() -> None:
    audit_source()
    checked = audit_published_v2()
    print(
        "GAME RESULTS CONTRACT AUDIT PASS: source semantics guarded; "
        f"validated {checked} published v2 season artifact(s)."
    )


if __name__ == "__main__":
    main()
