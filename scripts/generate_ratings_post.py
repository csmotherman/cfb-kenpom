"""Generate the weekly PRIME Power Ratings social candidate.

Source of truth: web/public/data/rankings/{season}.json.
The latest published ratings week is used, and the top 25 are ordered by the
file's own rank field (PRIME Net Rating rank). This script only creates the
candidate + PNG; the Sunday workflow performs Storage upload and Buffer
scheduling.

Unlike Composite Rankings, Power Ratings update continuously with the current
week, so the workflow intentionally waits until Sunday midday before calling
this generator. Dedupe is one row per season/week.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cfb_analytics.social import db, policy, scheduling
from cfb_analytics.social.images.rankings_card import RankingsCardRow, render_rankings_card
from cfb_analytics.social.provenance import content_hash
from cfb_analytics.social.season import resolve_active_season
from cfb_analytics.social.templates import (
    RATINGS_WEEKLY_CAPTION_VERSION,
    build_ratings_weekly_caption,
)

REPO = Path(__file__).resolve().parent.parent
RENDER_VERSION = "power_ratings_card_v1"
TOP_N = 25
BUFFER_CHANNEL_ID = "6ab6f59cea19ca0bdeec86d2"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _emit_github_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO / "build" / "social",
    )
    args = parser.parse_args(argv)

    season = args.season if args.season is not None else resolve_active_season()
    ratings_path_abs = REPO / "web" / "public" / "data" / "rankings" / f"{season}.json"
    ratings_path_rel = f"web/public/data/rankings/{season}.json"
    ratings = _load_json(ratings_path_abs)

    weeks = [int(w) for w in ratings.get("weeks") or []]
    if not weeks:
        raise ValueError(f"{ratings_path_abs} has no ratings weeks")
    week = max(weeks)

    rows = ratings.get("byWeek", {}).get(str(week)) or []
    teams = sorted(
        [row for row in rows if row.get("rank") is not None and row.get("adjEM") is not None],
        key=lambda row: row["rank"],
    )[:TOP_N]
    if not teams:
        raise ValueError(f"{ratings_path_abs} has no rated teams for Week {week}")

    dedupe_key = f"ratings_weekly:{season}:{week}"
    base_url, secret = db.config()
    existing = db.get_by_dedupe_key(base_url, secret, dedupe_key)
    if existing is not None:
        print(
            f"Already generated for {dedupe_key} "
            f"(social_posts id={existing['id']}, status={existing['status']}). Nothing to do."
        )
        _emit_github_output("social_post_id", existing["id"])
        return

    card_rows = [
        RankingsCardRow(
            rank=t["rank"],
            team=t["team"],
            conference=t.get("conf"),
            record=t.get("record", "—"),
            team_id=t.get("teamId"),
            display_value=f"{float(t['adjEM']):+.1f} NET",
        )
        for t in teams
    ]

    output_path = args.output_dir / str(season) / f"power-ratings-week-{week:02d}.png"
    render_rankings_card(
        season=season,
        week=week,
        rows=card_rows,
        output_path=output_path,
        title_prefix="POWER ",
        title_accent="RATINGS",
        methodology_text="NET RATING  •  OPPONENT ADJUSTED",
        tagline_text="Current team strength based on opponent-adjusted performance.",
        footer_note_text="Composite Rankings are separate: 50% Net Rating + 50% SOR.",
    )
    print(f"Rendered {output_path}")

    top_teams = [
        (int(t["rank"]), t["team"], float(t["adjEM"]))
        for t in teams[:3]
    ]
    text, sources = build_ratings_weekly_caption(
        season=season,
        week=week,
        top_teams=top_teams,
        ratings_path=ratings_path_rel,
    )
    print(f"Caption ({len(text)} chars):\n{text}")

    alt_text = (
        f"PRIME Power Ratings for Week {week} of the {season} college football season, "
        "showing the top 25 teams by opponent-adjusted Net Rating."
    )

    target = scheduling.intended_ratings_publication_target(scheduling.utc_now())
    if target.missed_window:
        print(
            "NOTE: generated after the 2:00 PM ET Sunday publish window "
            f"(scheduled_at={target.scheduled_at.isoformat()})."
        )

    row = {
        "platform": "twitter",
        "event_type": "ratings_weekly",
        "season": season,
        "week": week,
        "game_ids": None,
        "team_slugs": [t["slug"] for t in teams],
        "dedupe_key": dedupe_key,
        "status": "candidate",
        "publish_policy": policy.resolve_policy("ratings_weekly").value,
        "text_content": text,
        "alt_text": alt_text,
        "image_storage_path": output_path.relative_to(REPO).as_posix(),
        "image_url": None,
        "caption_version": RATINGS_WEEKLY_CAPTION_VERSION,
        "render_version": RENDER_VERSION,
        "content_hash": content_hash(text, sources),
        "sources": [s.to_dict() for s in sources],
        "source_snapshot": {
            "ratings": {
                "season": season,
                "week": week,
                "teams": teams,
            }
        },
        "metadata": {
            "generator": "scripts/generate_ratings_post.py",
            "team_count": len(teams),
            "ratings_week": week,
            "missed_publish_window": target.missed_window,
            "git_sha": os.environ.get("GITHUB_SHA"),
        },
        "buffer_post_id": None,
        "buffer_channel_id": BUFFER_CHANNEL_ID,
        "scheduled_at": target.scheduled_at.isoformat(),
    }

    inserted = db.insert_post(base_url, secret, row)
    print(
        f"Inserted social_posts id={inserted['id']} "
        f"status={inserted['status']} dedupe_key={dedupe_key}"
    )
    _emit_github_output("social_post_id", inserted["id"])


if __name__ == "__main__":
    main()
