"""Build one cached per-team-game research row per season, joining:

  - Possession-efficiency inputs (offensiveDrivePoints, resolvedPointPossessions)
    from the exact same locked Drive Efficiency v1 + Finishing Drives v2
    foundation production Adj. Net uses (analytics/drive_ppd.py's
    build_team_game_drive_rows -- not re-derived, the identical function).
  - EPA / Success Rate / Explosiveness raw counts from canonical
    team_games.json (data/canonical/season=Y/team_games.json), the same
    locked classify_epa/classify_success/classify_explosive populations
    already used everywhere else in this repo.
  - Final score (points_for/points_against) for MOV and win/loss targets.
  - FBS-vs-FBS classification filter.

This is the ONE dataset every model in this research project reads from --
no model gets its own bespoke data path, so a difference in results reflects
the grading philosophy, not a difference in what games/possessions were
counted. Output: research/rating_methodology_validation/data/season=Y.json,
one row per (season, week, seasonType, gameId, team).
"""
from __future__ import annotations

import json
from pathlib import Path

from cfb_analytics.analytics.drive_ppd import build_team_game_drive_rows
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "data"

# Matches this repo's own DEFAULT_SEASONS convention (walk_forward_baseline.py):
# 2020 intentionally excluded (abbreviated COVID season, never processed by
# this pipeline -- see the historical-backfill audit from this project's
# earlier work). 2026 excluded here too: still in progress, reserved for the
# Nebraska case study only, not the historical walk-forward evidence.
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load_canonical_season(season: int) -> dict[tuple[str, str], dict]:
    path = REPO / f"data/canonical/season={season}/team_games.json"
    rows = json.loads(path.read_text())
    return {(str(r.get("gameId") or r.get("game_id")), r.get("team")): r for r in rows}


def load_drive_ppd_season(season: int) -> dict[tuple[str, str], dict]:
    drives, plays = [], []
    for st, week in discover_partitions(REPO / "data/raw", season):
        dpath = derived_drive_partition_dir(REPO / "data/processed", season, st, week) / "drives.json"
        ppath = canonical_partition_dir(REPO / "data/processed", season, st, week) / "plays.json"
        drives.extend(json.loads(dpath.read_text()))
        plays.extend(json.loads(ppath.read_text()))
    rows = build_team_game_drive_rows(drives, plays)
    return {(str(r["gameId"]), r["team"]): r for r in rows}


def build_row(canon: dict, ppd: dict | None) -> dict:
    # Matches production's own fallback exactly (rating_model.py's
    # _drive_rating_fields docstring: "Missing drive data must never be
    # replaced with scoreboard points or another proxy" -- a genuine, rare
    # gap on one side of a game (confirmed e.g. Ole Miss's offense in
    # 2014 week 1's Boise State game) gets zero-weight placeholder values,
    # never None, so the game stays paired (exactly two rows) with zero
    # influence on the fit, instead of silently vanishing from one side.
    if ppd is None:
        ppd = {"offensiveDrivePoints": 0.0, "resolvedPointPossessions": 0.0, "validatedPossessions": 0.0}
    return {
        "season": canon.get("season"),
        "seasonType": canon.get("season_type"),
        "week": canon.get("week"),
        "gameId": str(canon.get("gameId") or canon.get("game_id")),
        "team": canon.get("team"),
        "opponent": canon.get("opponent"),
        "classification": canon.get("classification"),
        "opponentClassification": canon.get("opponent_classification"),
        "homeAway": canon.get("home_away"),
        "neutralSite": canon.get("neutral_site"),
        "pointsFor": _num(canon.get("points_for")),
        "pointsAgainst": _num(canon.get("points_against")),
        "win": canon.get("win"),
        # Possession efficiency (production foundation)
        "offensiveDrivePoints": _num(ppd.get("offensiveDrivePoints")),
        "resolvedPointPossessions": _num(ppd.get("resolvedPointPossessions")),
        "validatedPossessions": _num(ppd.get("validatedPossessions")) or _num(canon.get("validatedPossessions")),
        # EPA
        "epaSum": _num(canon.get("epaSum")),
        "epaPlays": _num(canon.get("epaPlays")),
        # Success Rate
        "successfulPlays": _num(canon.get("successfulPlays")),
        "successEligiblePlays": _num(canon.get("successEligiblePlays")),
        # Explosiveness
        "explosivePlays": _num(canon.get("explosivePlays")),
        "explosiveEligiblePlays": _num(canon.get("explosiveEligiblePlays")),
        "offensivePlays": _num(canon.get("offensivePlays")),
    }


def build_season(season: int) -> list[dict]:
    canon = load_canonical_season(season)
    ppd = load_drive_ppd_season(season)
    rows = [build_row(canon_row, ppd.get(key)) for key, canon_row in canon.items()]
    rows.sort(key=lambda r: (r["week"] or 0, r["gameId"], r["team"]))
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for season in SEASONS + (2026,):
        rows = build_season(season)
        fbs_vs_fbs = sum(1 for r in rows if r["classification"] == "fbs" and r["opponentClassification"] == "fbs")
        path = OUT_DIR / f"season={season}.json"
        path.write_text(json.dumps(rows, separators=(",", ":")))
        print(f"season {season}: {len(rows)} rows ({fbs_vs_fbs} FBS-vs-FBS) -> {path}")


if __name__ == "__main__":
    main()
