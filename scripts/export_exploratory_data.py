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

from cfb_analytics.analytics.exploratory.series_metrics import COUNT_FIELDS  # noqa: E402

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)


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
        for field in COUNT_FIELDS:
            wk[field] += r.get(field, 0)

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
        team_week_rows = sum(len(v) for v in payload["byWeek"].values())
        print(
            f"season {season}: {len(payload['weeks'])} weeks, {team_week_rows} team-week rows "
            f"(skipped: {meta['skippedNonFbsRows']} non-FBS, {meta['skippedUnmappedGameRows']} unmapped-game) "
            f"-> web/public/data/exploratory/{season}.json"
        )


if __name__ == "__main__":
    main()
