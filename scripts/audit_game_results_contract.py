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

VERSION = "team-game-advanced-v3-official-box-score"

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
    "epa_per_play",
    "total_epa",
    "success_rate",
    "passing_epa",
    "epa_per_dropback",
    "pass_success_rate",
    "rushing_epa",
    "epa_per_rush",
    "rush_success_rate",
    "series_conversion_rate",
    "turnover_epa_lost",
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

    require(client, "def game_team_stats_week", str(CLIENT))
    require(client, '"/games/teams"', str(CLIENT))
    require(acquire, 'BOX_SCORE_ENTITY = "game_team_stats"', str(ACQUIRE))
    require(acquire, "client.game_team_stats_week", str(ACQUIRE))

    require(exporter, f'TEAM_GAME_ADVANCED_VERSION = "{VERSION}"', str(EXPORTER))
    require(exporter, "def load_box_score_season", str(EXPORTER))
    require(exporter, "def _normalize_box_team", str(EXPORTER))
    for key in BOX_KEYS | ADVANCED_KEYS:
        require(exporter, f'"{key}":', str(EXPORTER))

    # Official display rows must point only at box_* fields.
    require(frontend, 'column("Official Box Score", BOX_SCORE)', str(FRONTEND))
    require(
        frontend,
        "leftRow?.box_score_available === true && rightRow?.box_score_available === true",
        str(FRONTEND),
    )
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


def main() -> None:
    audit_source()
    checked = audit_published_v3()
    print(
        "GAME RESULTS CONTRACT AUDIT PASS: official box-score/LEILA boundary guarded; "
        f"validated {checked} published v3 season artifact(s)."
    )


if __name__ == "__main__":
    main()
