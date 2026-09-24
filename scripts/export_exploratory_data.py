"""Export LEILA Exploratory Tier 1 data to web/public/data/exploratory/{season}.json.

Reads data/processed/derived/exploratory/season=Y/... (written by
exploratory_series_propagation_cli.py). CFBD's own week field is NOT the
site's real week numbering (week 1 lumps two real chronological weeks
together -- see build_site_week_map's docstring), so every row is remapped
by gameId through build_real_data.build_site_week_map, the same function
Rankings/Advanced use, rather than trusting the raw week partition directly.

Output is shaped like AdvancedSeason so the frontend's existing num/den
week-range-sum convention (sum raw counts across selected weeks, then
divide) applies unchanged: {weeks, weekLabels, byWeek: {week: [{team, slug,
teamId, conf, wk: {...raw counts...}}]}}.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from build_real_data import build_site_week_map  # noqa: E402

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)

# Every computed rate on a materialized row -- these must be RECOMPUTED
# client-side from summed raw counts across the selected week range, never
# summed or averaged themselves. Identity/version fields are excluded
# separately below. Everything else numeric on a row is a raw, summable
# count (series/drives/risk/scoring-opportunity ingredients).
_RATE_FIELDS = {
    "seriesConversionRate", "seriesStopRate", "recoveryRate", "closeoutRate",
    "longDownRate", "longDownAvoidanceRate", "longDownCreationRate",
    "cleanDriveRate", "driveKillerRate", "killerRecoveryRate",
    "cleanDriveRateAllowed", "driveKillerRateForced",
    "explosiveDependency", "nonExplosiveEpaPerPlay", "explosiveYardDependency",
    "failureRate", "averageFailureDamage", "failureBurden", "failurePressure",
    "pointsPerScoringOpportunity", "opponentPointsPerScoringOpportunity",
}
_IDENTITY_FIELDS = {
    "season", "seasonType", "week", "gameId", "team", "opponent",
    "seriesDefinitionVersion", "seriesMetricsVersion", "exploratoryDrivesRiskVersion",
}


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def load_team_identity(season: int) -> dict[str, dict]:
    teams = json.loads((REPO / f"data/canonical/season={season}/teams.json").read_text())
    return {
        t["team"]: {"slug": t["slug"], "teamId": t["team_id"], "conf": t.get("conference")}
        for t in teams
        if t.get("classification") == "fbs"
    }


def load_exploratory_rows(season: int) -> list[dict]:
    rows = []
    pattern = str(REPO / f"data/processed/derived/exploratory/season={season}/season_type=*/week=*/team_games.json")
    for path in glob.glob(pattern):
        rows.extend(json.loads(Path(path).read_text()))
    return rows


def build_season_payload(season: int) -> dict:
    site_week_by_game, _num_weeks, week_labels = build_site_week_map(season)
    identity = load_team_identity(season)
    rows = load_exploratory_rows(season)

    by_week: dict[int, dict[str, dict]] = defaultdict(dict)
    skipped_unmapped_game = 0
    skipped_non_fbs = 0
    for r in rows:
        team = r["team"]
        if team not in identity:
            skipped_non_fbs += 1
            continue
        site_week = site_week_by_game.get(str(r["gameId"]))
        if site_week is None:
            skipped_unmapped_game += 1
            continue
        bucket = by_week[site_week]
        if team not in bucket:
            info = identity[team]
            bucket[team] = {
                "team": team,
                "slug": info["slug"],
                "teamId": info["teamId"],
                "conf": info["conf"],
                "wk": defaultdict(int),
            }
        wk = bucket[team]["wk"]
        for field, value in r.items():
            if field in _IDENTITY_FIELDS or field in _RATE_FIELDS:
                continue
            if _num(value):
                wk[field] = wk.get(field, 0) + value

    weeks = sorted(by_week)
    return {
        "weeks": weeks,
        "weekLabels": {str(w): lbl for w, lbl in week_labels.items() if w in by_week},
        "byWeek": {
            str(w): sorted(
                ({**row, "wk": dict(row["wk"])} for row in by_week[w].values()),
                key=lambda row: row["team"],
            )
            for w in weeks
        },
        "skippedNonFbsRows": skipped_non_fbs,
        "skippedUnmappedGameRows": skipped_unmapped_game,
    }


GAMES_VERSION = "exploratory-custom-sample-v1"


def build_games_payload(season: int) -> dict:
    """Per-team, per-game raw counts behind the Exploratory "custom sample" feature.

    Every published Exploratory number is (sum of raw counts) / (sum of raw
    counts), so a chosen subset of a team's games is just a subset of the sums.
    This uses exactly the row filters and field rules of build_season_payload, so
    summing every game reproduces the published week counts (tests pin this).
    Private artifact: published to Supabase, never committed (see
    publish_premium_data.py and docs/advanced_custom_samples.md).
    """
    from build_real_data import load_processed_team_games

    site_week_by_game, _num_weeks, _labels = build_site_week_map(season)
    identity = load_team_identity(season)
    by_slug_name = {name: info for name, info in identity.items()}
    processed, _weeks, _week_labels = load_processed_team_games(season)
    meta_by = {(str(r.get("gameId") or r.get("game_id")), r["team"]): r for r in processed}

    rows = []
    fields: set[str] = set()
    for r in load_exploratory_rows(season):
        if r["team"] not in identity or site_week_by_game.get(str(r["gameId"])) is None:
            continue
        rows.append(r)
        for field, value in r.items():
            if field not in _IDENTITY_FIELDS and field not in _RATE_FIELDS and _num(value):
                fields.add(field)
    ordered = sorted(fields)

    teams: dict[str, dict] = {}
    for r in sorted(rows, key=lambda x: (x["team"], site_week_by_game[str(x["gameId"])], str(x["gameId"]))):
        gid, team = str(r["gameId"]), r["team"]
        info = identity[team]
        game = meta_by.get((gid, team)) or {}
        opp = game.get("opponent") or r.get("opponent")
        opp_info = by_slug_name.get(opp)
        entry = {
            "g": gid, "w": site_week_by_game[gid], "o": opp,
            "oi": opp_info["teamId"] if opp_info else None,
            "fbs": bool(opp_info) and game.get("opponent_classification") == "fbs",
            "ha": "N" if game.get("neutral_site") else ("H" if game.get("home_away") == "home" else "A"),
            "pf": game.get("points_for"), "pa": game.get("points_against"), "win": bool(game.get("win")),
            "x": [round(float(r[f]), 6) if _num(r.get(f)) else 0 for f in ordered],
        }
        teams.setdefault(f"t{info['teamId']}", {"slug": info["slug"], "team": team, "teamId": info["teamId"], "games": []})["games"].append(entry)

    return {
        "meta": {"version": GAMES_VERSION, "season": season, "weekThrough": max(site_week_by_game.values(), default=0), "fields": ordered},
        "teams": teams,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, help="Export only one season")
    args = parser.parse_args()
    seasons = (args.season,) if args.season else SEASONS
    out_dir = REPO / "web" / "public" / "data" / "exploratory"

    for season in seasons:
        source_dir = REPO / f"data/processed/derived/exploratory/season={season}"
        if not source_dir.exists():
            continue
        payload = build_season_payload(season)
        if not payload["weeks"]:
            continue
        meta = {k: payload.pop(k) for k in ("skippedNonFbsRows", "skippedUnmappedGameRows")}
        _atomic_write(out_dir / f"{season}.json", json.dumps(payload, separators=(",", ":")))
        try:  # optional per-game companion for custom samples; never blocks the export
            games_payload = build_games_payload(season)
            games_dir = REPO / "web" / "public" / "data" / "exploratory-games"
            _atomic_write(games_dir / f"{season}.json", json.dumps(games_payload, separators=(",", ":"), allow_nan=False))
            print(f"season {season}: exploratory custom-sample artifact, {len(games_payload['teams'])} teams")
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::exploratory custom-sample artifact for {season} failed: {exc}")
        team_week_rows = sum(len(v) for v in payload["byWeek"].values())
        print(
            f"season {season}: {len(payload['weeks'])} weeks, {team_week_rows} team-week rows "
            f"(skipped: {meta['skippedNonFbsRows']} non-FBS, {meta['skippedUnmappedGameRows']} unmapped-game) "
            f"-> web/public/data/exploratory/{season}.json"
        )


if __name__ == "__main__":
    main()
