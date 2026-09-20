"""Fail CI when completed-game Results mix box-score facts with LEILA metrics.

The public Results page has a hard source boundary:
- CFBD /games/teams is authoritative for base box-score facts.
- LEILA canonical/exploratory pipelines are authoritative for advanced metrics.

This audit guards both the source wiring and any regenerated v3 payload.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLIENT = REPO / "src/cfb_analytics/sources/cfbd/client.py"
ACQUIRE = REPO / "src/cfb_analytics/raw/acquire.py"
EXPORTER = REPO / "scripts/export_team_game_advanced.py"
FRONTEND = REPO / "web/lib/team-game-advanced.ts"
RESULTS_SHEET = REPO / "web/components/GameResultsSheet.tsx"
PUBLIC_DIR = REPO / "web/public/data/team-game-advanced"

VERSION = "team-game-advanced-v4-cfbd-advanced-source"
CFBD_CLIENT = REPO / "src/cfb_analytics/sources/cfbd/client.py"
CFBD_CANONICAL = REPO / "src/cfb_analytics/canonical/cfbd_advanced.py"

BOX_KEYS = {
    "box_score_available",
    "box_points",
    "box_first_downs",
    "box_total_plays",
    "box_total_yards",
    "box_yards_per_play",
    "box_completions",
    "box_pass_attempts",
    "box_net_pass_yards",
    "box_yards_per_pass_attempt",
    "box_rush_attempts",
    "box_rush_yards",
    "box_yards_per_rush_attempt",
    "box_third_down_conversions",
    "box_third_down_attempts",
    "box_third_down_rate",
    "box_fourth_down_conversions",
    "box_fourth_down_attempts",
    "box_fourth_down_rate",
    "box_penalties",
    "box_penalty_yards",
    "box_turnovers",
    "box_interceptions",
    "box_fumbles_lost",
    "box_possession_seconds",
    "box_possession_share",
}

ADVANCED_KEYS = {
    "ppa_per_play",
    "total_ppa",
    "success_rate",
    "passing_total_ppa",
    "passing_ppa_per_play",
    "pass_success_rate",
    "rushing_total_ppa",
    "rushing_ppa_per_play",
    "rush_success_rate",
    "series_conversion_rate",
    "turnover_epa_lost",
}

# Fields that must never be present under their old, pre-migration names --
# these were literally CFBD's own PPA/game facts mislabeled as a PRIME EPA
# model or a PRIME-reconstructed drive/field-position fact. Their presence
# would mean the migration to CFBD's advanced endpoints regressed.
FORBIDDEN_LEGACY_KEYS = {
    "epa_per_play",
    "total_epa",
    "passing_epa",
    "epa_per_dropback",
    "rushing_epa",
    "epa_per_rush",
    "epa_plays",
    "epa_without_explosives",
}

# Confirmed directly against a fresh, uncached CFBD /games/teams call (not a
# downstream acquisition/parsing bug): the vendor has never returned a box
# score for this game. Fail-closed stays in force for every other FBS-vs-FBS
# game; this is a documented, verified exception, not a general escape hatch.
KNOWN_BOX_SCORE_SOURCE_GAPS = {
    "400868914",  # 2016 week 6, Army at Duke
}


def fail(message: str) -> None:
    raise SystemExit(f"GAME RESULTS CONTRACT AUDIT FAILED: {message}")


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        fail(f"missing {needle!r} in {where}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        fail(f"forbidden {needle!r} found in {where}")


def close(a, b, tolerance=1e-9) -> bool:
    return abs(float(a) - float(b)) <= tolerance


def audit_source() -> None:
    client = CLIENT.read_text(encoding="utf-8")
    acquire = ACQUIRE.read_text(encoding="utf-8")
    exporter = EXPORTER.read_text(encoding="utf-8")
    frontend = FRONTEND.read_text(encoding="utf-8")
    results_sheet = RESULTS_SHEET.read_text(encoding="utf-8")
    cfbd_canonical = CFBD_CANONICAL.read_text(encoding="utf-8")

    require(client, "def game_team_stats_week", str(CLIENT))
    require(client, '"/games/teams"', str(CLIENT))
    require(client, "def game_advanced_stats", str(CLIENT))
    require(client, '"/stats/game/advanced"', str(CLIENT))
    require(client, "def advanced_box_score", str(CLIENT))
    require(client, '"/game/box/advanced"', str(CLIENT))
    require(acquire, 'BOX_SCORE_ENTITY = "game_team_stats"', str(ACQUIRE))
    require(acquire, "client.game_team_stats_week", str(ACQUIRE))

    require(cfbd_canonical, "CFBD_STATS_GAME_ADVANCED_VERSION", str(CFBD_CANONICAL))
    require(cfbd_canonical, "CFBD_GAME_BOX_ADVANCED_VERSION", str(CFBD_CANONICAL))

    require(exporter, f'TEAM_GAME_ADVANCED_VERSION = "{VERSION}"', str(EXPORTER))
    require(exporter, "def load_box_score_season", str(EXPORTER))
    require(exporter, "def _normalize_box_team", str(EXPORTER))
    require(exporter, "load_stats_game_advanced_season", str(EXPORTER))
    require(exporter, "load_game_box_advanced_season", str(EXPORTER))
    for key in BOX_KEYS | ADVANCED_KEYS:
        require(exporter, f'"{key}":', str(EXPORTER))
    for key in FORBIDDEN_LEGACY_KEYS:
        forbid(exporter, f'"{key}":', str(EXPORTER))

    # Official display rows must point only at box_* fields.
    require(frontend, 'column("Official Box Score", BOX_SCORE)', str(FRONTEND))
    require(frontend, 'label: "Plays", key: "box_total_plays"', str(FRONTEND))
    require(frontend, 'label: "3rd Down"', str(FRONTEND))
    require(frontend, '"box_third_down_conversions"', str(FRONTEND))
    require(frontend, '"box_third_down_attempts"', str(FRONTEND))
    require(frontend, 'label: "Penalties", key: "box_penalties"', str(FRONTEND))
    require(frontend, 'label: "Turnovers", key: "box_turnovers"', str(FRONTEND))
    require(frontend, 'label: "Possession", key: "box_possession_seconds"', str(FRONTEND))

    # These were the misleading labels/mappings that triggered the audit.
    forbid(frontend, 'label: "3rd Down Conversion", key: "series_conversion_rate"', str(FRONTEND))
    forbid(frontend, 'label: "Possession Share"', str(FRONTEND))
    forbid(frontend, 'label: "Penalty Rate"', str(FRONTEND))
    forbid(frontend, 'label: "Turnover Rate"', str(FRONTEND))
    forbid(frontend, 'label: "Points / Drive"', str(FRONTEND))

    require(results_sheet, "export function postgameRecord", str(RESULTS_SHEET))
    require(results_sheet, "leftPostgameRecord", str(RESULTS_SHEET))
    require(results_sheet, "rightPostgameRecord", str(RESULTS_SHEET))


def _validate_rate(row: dict, num_key: str, den_key: str, rate_key: str, label: str) -> None:
    num = row.get(num_key)
    den = row.get(den_key)
    rate = row.get(rate_key)
    if rate is None:
        return
    if not isinstance(num, (int, float)) or not isinstance(den, (int, float)) or den <= 0:
        fail(f"{label} rate present without valid numerator/denominator for {row.get('game_id')} {row.get('team')}")
    if not close(rate, num / den, 1e-12):
        fail(f"{label} rate mismatch for {row.get('game_id')} {row.get('team')}")


def audit_published_v3() -> int:
    checked = 0
    if not PUBLIC_DIR.exists():
        return checked

    for path in sorted(PUBLIC_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != VERSION:
            continue
        checked += 1
        rows = payload.get("rows")
        if not isinstance(rows, list):
            fail(f"{path} v3 payload has no rows list")

        by_game: dict[str, list[dict]] = defaultdict(list)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                fail(f"{path} row {index} is not an object")
            missing = (BOX_KEYS | ADVANCED_KEYS).difference(row)
            if missing:
                fail(f"{path} row {index} missing contract keys: {sorted(missing)}")
            legacy = FORBIDDEN_LEGACY_KEYS.intersection(row)
            if legacy:
                fail(f"{path} row {index} carries forbidden pre-migration keys: {sorted(legacy)}")

            game_id = str(row.get("game_id"))
            by_game[game_id].append(row)

            # Results are published for FBS-vs-FBS games; fail closed if the
            # authoritative box-score feed is missing for one of those rows.
            if row.get("classification") == "fbs" and row.get("opponent_classification") == "fbs":
                if row.get("box_score_available") is not True and game_id not in KNOWN_BOX_SCORE_SOURCE_GAPS:
                    fail(f"{path} missing official box score for {game_id} {row.get('team')}")

            if row.get("box_score_available") is not True:
                continue

            if row.get("box_points") is not None and row.get("points") is not None:
                if row["box_points"] != row["points"]:
                    fail(f"{path} score mismatch for {game_id} {row.get('team')}")

            rush = row.get("box_rush_attempts")
            passes = row.get("box_pass_attempts")
            plays = row.get("box_total_plays")
            if all(isinstance(v, (int, float)) for v in (rush, passes, plays)):
                if plays != rush + passes:
                    fail(f"{path} play-count mismatch for {game_id} {row.get('team')}")

            _validate_rate(
                row,
                "box_third_down_conversions",
                "box_third_down_attempts",
                "box_third_down_rate",
                "third down",
            )
            _validate_rate(
                row,
                "box_fourth_down_conversions",
                "box_fourth_down_attempts",
                "box_fourth_down_rate",
                "fourth down",
            )

            turnovers = row.get("box_turnovers")
            interceptions = row.get("box_interceptions")
            fumbles = row.get("box_fumbles_lost")
            if all(isinstance(v, (int, float)) for v in (turnovers, interceptions, fumbles)):
                if turnovers != interceptions + fumbles:
                    fail(f"{path} turnover components mismatch for {game_id} {row.get('team')}")

            share = row.get("box_possession_share")
            if share is not None and not 0 <= share <= 1:
                fail(f"{path} possession share outside [0,1] for {game_id} {row.get('team')}")

        for game_id, game_rows in by_game.items():
            box_rows = [row for row in game_rows if row.get("box_score_available") is True]
            if len(box_rows) != 2:
                continue
            shares = [row.get("box_possession_share") for row in box_rows]
            if all(isinstance(v, (int, float)) for v in shares):
                if not close(sum(shares), 1.0, 1e-9):
                    fail(f"{path} possession shares do not sum to 1 for {game_id}")

            left, right = box_rows
            if left.get("points") is not None and right.get("opponent_points") is not None:
                if left["points"] != right["opponent_points"]:
                    fail(f"{path} score mirror mismatch for {game_id}")
            if right.get("points") is not None and left.get("opponent_points") is not None:
                if right["points"] != left["opponent_points"]:
                    fail(f"{path} score mirror mismatch for {game_id}")

    return checked


RAW_ROOT = REPO / "data/raw/cfbd"


def audit_cfbd_advanced_cross_check() -> int:
    """Spot-check exported CFBD-sourced fields directly against the raw
    /stats/game/advanced response (Phase 12: SOURCE RAW VALUE -> SITE EXPORT
    VALUE must be an explicit, tested chain for CFBD-sourced fields)."""
    checked = 0
    if not PUBLIC_DIR.exists():
        return checked
    for path in sorted(PUBLIC_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != VERSION:
            continue
        season = payload.get("season")
        raw_by_game_team: dict[tuple[str, str], dict] = {}
        for raw_path in sorted(RAW_ROOT.glob(f"season={season}/season_type=*/week=*/advanced_game_stats.json")):
            for row in json.loads(raw_path.read_text(encoding="utf-8")):
                raw_by_game_team[(str(row.get("gameId")), row.get("team"))] = row
        if not raw_by_game_team:
            continue
        for row in payload.get("rows", []):
            key = (str(row.get("game_id")), row.get("team"))
            raw = raw_by_game_team.get(key)
            if raw is None:
                continue
            checked += 1
            raw_success = (raw.get("offense") or {}).get("successRate")
            if raw_success is not None and row.get("success_rate") is not None:
                if not close(raw_success, row["success_rate"], 1e-9):
                    fail(
                        f"{path} success_rate for {key} does not match raw advanced_game_stats.json "
                        f"({row['success_rate']} vs {raw_success})"
                    )
            raw_ppa = (raw.get("offense") or {}).get("totalPPA")
            if raw_ppa is not None and row.get("total_ppa") is not None:
                if not close(raw_ppa, row["total_ppa"], 1e-9):
                    fail(
                        f"{path} total_ppa for {key} does not match raw advanced_game_stats.json "
                        f"({row['total_ppa']} vs {raw_ppa})"
                    )
    return checked


def main() -> None:
    audit_source()
    checked = audit_published_v3()
    cross_checked = audit_cfbd_advanced_cross_check()
    print(
        "GAME RESULTS CONTRACT AUDIT PASS: official box-score/CFBD-advanced/PRIME boundary guarded; "
        f"validated {checked} published v4 season artifact(s), cross-checked {cross_checked} "
        "CFBD-sourced team-game rows directly against raw advanced_game_stats.json."
    )


if __name__ == "__main__":
    main()
