"""Publish national, conference, and lightweight team artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cfb_analytics.aggregations.conference import summarize_conferences
from cfb_analytics.aggregations.rankings import METRICS, add_national_and_conference_rankings
from cfb_analytics.config.constants import DEFAULT_CANONICAL_ROOT, DEFAULT_PROCESSED_ROOT, DEFAULT_PUBLISHED_ROOT
from cfb_analytics.config.seasons import classify_season
from cfb_analytics.config.teams import slugify
from cfb_analytics.pipelines.io import write_records
from cfb_analytics.validation.integrity import validate_team_games, validate_team_seasons


def _read(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def _soar_namespaced(row: dict) -> dict:
    out = dict(row)
    for metric in METRICS:
        if metric.name in row:
            out[f"soar_{metric.name}"] = row[metric.name]
    return out


def publish(season: int, canonical_root: Path = DEFAULT_CANONICAL_ROOT, processed_root: Path = DEFAULT_PROCESSED_ROOT, published_root: Path = DEFAULT_PUBLISHED_ROOT) -> dict:
    canonical_dir = canonical_root / f"season={season}"
    teams = _read(canonical_dir / "teams.json")
    team_games = _read(canonical_dir / "team_games.json")
    memberships = {row["team"]: row for row in teams if row.get("classification") == "fbs"}
    locked = _read(processed_root / "derived" / "seasons" / f"season={season}" / "team_seasons.json")
    team_seasons = []
    for row in locked:
        identity = memberships.get(row["team"])
        if identity is None:
            continue
        enriched = {
            **row,
            **{key: identity[key] for key in ("team_id", "conference", "classification", "slug")},
            "season_state": "COMPLETE",
            "value_type": "ACTUAL",
        }
        team_seasons.append(_soar_namespaced(enriched))
    ranked = add_national_and_conference_rankings(team_seasons)
    team_audit = validate_team_seasons(ranked)
    game_audit = validate_team_games(team_games)
    conferences = summarize_conferences(ranked)
    root = published_root / str(season)
    paths = []
    paths += write_records(root / "national" / "teams.parquet", ranked)
    paths += write_records(root / "national" / "rankings.parquet", ranked)
    paths += write_records(root / "national" / "conferences.parquet", conferences)
    for conference in sorted({row["conference"] for row in ranked}):
        subset = [row for row in ranked if row["conference"] == conference]
        directory = root / "conferences" / slugify(conference)
        paths += write_records(directory / "teams.parquet", subset)
        paths += write_records(directory / "rankings.parquet", subset)
    for row in ranked:
        slug = row["slug"]
        paths += write_records(root / "teams" / slug / "season.parquet", [row])
        paths += write_records(root / "teams" / slug / "games.parquet", [game for game in team_games if game["team_id"] == row["team_id"]])
    digest = hashlib.sha256(b"".join(path.read_bytes() for path in sorted(paths))).hexdigest()
    season_status = classify_season(season, team_games)
    manifest = {
        "season": season,
        "season_state": season_status.state,
        "season_state_evidence": season_status.evidence,
        "value_type": "ACTUAL",
        "team_season_rows": len(ranked),
        "team_game_rows": len(team_games),
        "conferences": len(conferences),
        "metrics_ranked": [metric.name for metric in METRICS],
        "team_audit": team_audit,
        "team_game_audit": game_audit,
        "artifact_sha256": digest,
        "format_note": "JSON is always emitted; Parquet is also emitted when pyarrow is installed.",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--published-root", type=Path, default=DEFAULT_PUBLISHED_ROOT)
    args = parser.parse_args()
    print(json.dumps(publish(args.season, args.canonical_root, args.processed_root, args.published_root), indent=2))


if __name__ == "__main__":
    main()
