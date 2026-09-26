"""Generate the Sunday PRIME 25 rankings social_posts candidate.

Idempotent: computes a dedupe_key from season+week and checks Supabase
social_posts for it before doing any rendering or writing. A second run for
a season/week that has already been generated is a no-op.

Bootstrap: the first automated run ever for a season (no prior
rankings_weekly row exists) does not generate a post from whatever release
happens to be current -- it records that release as a baseline
(status="rejected", metadata.baseline=true) and returns. This is what makes
deploying this automation mid-season safe: without it, the first Sunday run
would immediately post an already-stale release simply because nothing had
been recorded yet. Normal generation resumes once a later run sees a
strictly newer releasedAt than the baseline. --force generates from the
current release immediately, bootstrap or not.

Every event type is pinned to DRAFT_ONLY (see cfb_analytics.social.policy):
this script renders the PNG to a local directory, writes one social_posts
row with status="candidate", and does nothing else. It never uploads to
Storage and never calls Buffer.

The card and caption show only fields prime-rankings/{season}.json (the
official PRIME 25) itself carries -- rank, team, conference, record, and its
own primeScore. They never show rankings/{season}.json's rankChange: that
field describes week-over-week movement in the broader power-rating order,
not in the PRIME 25, and prime-rankings/{season}.json has no history of its
own from week to week to compute real PRIME 25 movement from.

Usage:
    python scripts/generate_rankings_post.py [--season YEAR] [--output-dir DIR]

--season is optional. When omitted, the active season is resolved
dynamically from web/public/data/meta.json (mirroring the web app's own
getLatestYear()) -- this script never hardcodes a season year.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cfb_analytics.social import db, freshness, policy, scheduling
from cfb_analytics.social.images.rankings_card import RankingsCardRow, render_rankings_card
from cfb_analytics.social.provenance import content_hash
from cfb_analytics.social.season import resolve_active_season
from cfb_analytics.social.templates import (
    RANKINGS_WEEKLY_CAPTION_VERSION,
    RankedTeam,
    build_rankings_weekly_caption,
)

REPO = Path(__file__).resolve().parent.parent
RENDER_VERSION = "rankings_card_v2"
TOP_N = 25

# PrimeCFB_ on Buffer (confirmed via Buffer's list_channels). Recorded on the
# row as the intended destination only -- DRAFT_ONLY never calls Buffer, so
# this is metadata, not an action.
BUFFER_CHANNEL_ID = "6ab6f59cea19ca0bdeec86d2"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _emit_github_output(key: str, value: str) -> None:
    """Write key=value to $GITHUB_OUTPUT for a later workflow step to
    reference (e.g. steps.generate.outputs.social_post_id) -- a no-op
    outside GitHub Actions. Lets a caller capture the row id deterministically
    instead of parsing it back out of the human-readable print statements."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--season", type=int, default=None,
        help="Season year; defaults to the active season resolved from meta.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=REPO / "build" / "social",
        help="Local directory to render the PNG into (never uploaded anywhere by this script)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help=(
            "Bypass the PRIME 25 freshness guard (for a manual/backfill run only). "
            "dedupe_key still applies -- this cannot recreate a candidate that already exists."
        ),
    )
    args = parser.parse_args(argv)

    season = args.season if args.season is not None else resolve_active_season()
    print(f"Season: {season}" + ("" if args.season is not None else " (resolved dynamically from meta.json)"))

    prime_rankings_path_abs = REPO / "web" / "public" / "data" / "prime-rankings" / f"{season}.json"
    prime_rankings_rel = f"web/public/data/prime-rankings/{season}.json"

    prime = _load_json(prime_rankings_path_abs)
    week = prime["throughWeek"]
    teams = (prime.get("teams") or [])[:TOP_N]
    if not teams:
        raise ValueError(f"{prime_rankings_path_abs} has no teams; nothing to post")

    dedupe_key = f"rankings_weekly:{season}:{week}"

    base_url, secret = db.config()
    existing = db.get_by_dedupe_key(base_url, secret, dedupe_key)
    if existing is not None:
        print(
            f"Already generated for {dedupe_key} "
            f"(social_posts id={existing['id']}, status={existing['status']}). Nothing to do."
        )
        _emit_github_output("social_post_id", existing["id"])
        return

    # Freshness guard: prime-rankings/{season}.json is the source of truth
    # for whether a *new* PRIME 25 has actually been released. A dedupe_key
    # miss above only means this exact season+week hasn't been posted --
    # it says nothing about whether the underlying release is actually new,
    # since throughWeek can lag other data for hours. Compare against the
    # release we last actually turned into a candidate for this season.
    current_released_at = prime.get("releasedAt")
    latest_prior = db.get_latest_by_event_type(base_url, secret, "rankings_weekly", season)
    prior_released_at = (
        (latest_prior.get("source_snapshot") or {}).get("primeRankings", {}).get("releasedAt")
        if latest_prior else None
    )

    if latest_prior is None and not args.force:
        # Bootstrap: this season has no rankings_weekly row at all yet, so
        # there is nothing to compare freshness against. Treating that as
        # "fresh" would let deploying this automation mid-season immediately
        # post whatever release happens to be sitting in prime-rankings.json
        # at that moment, however old. Instead, record the current release
        # as a baseline (same dedupe_key, so this exact week can never later
        # be posted retroactively either) without generating a real
        # candidate. Normal generation resumes once a strictly newer release
        # appears on a later run.
        baseline_row = {
            "platform": "twitter",
            "event_type": "rankings_weekly",
            "season": season,
            "week": week,
            "game_ids": None,
            "team_slugs": [t["slug"] for t in teams],
            "dedupe_key": dedupe_key,
            "status": "rejected",
            "publish_policy": policy.resolve_policy("rankings_weekly").value,
            "text_content": (
                f"[baseline] No prior rankings_weekly row existed for season {season} when this "
                "automation ran. Recording this release as the starting baseline instead of posting "
                "it, so deploying mid-season cannot immediately post an already-stale release."
            ),
            "alt_text": None,
            "image_storage_path": None,
            "image_url": None,
            "caption_version": None,
            "render_version": None,
            "content_hash": None,
            "sources": [],
            "source_snapshot": {
                "primeRankings": {
                    "season": prime.get("season"), "throughWeek": week,
                    "releasedAt": current_released_at, "teams": teams,
                },
            },
            "metadata": {
                "baseline": True,
                "reason": "no_prior_rankings_weekly_row_for_season",
                "team_count": len(teams),
                "freshness_override": False,
                "prior_release_compared_against": None,
                "generator": "scripts/generate_rankings_post.py",
                "git_sha": os.environ.get("GITHUB_SHA"),
            },
            "buffer_post_id": None,
            "buffer_channel_id": BUFFER_CHANNEL_ID,
            "scheduled_at": None,
        }
        inserted = db.insert_post(base_url, secret, baseline_row)
        print(
            f"No prior rankings_weekly row for season {season}; recorded baseline "
            f"id={inserted['id']} at releasedAt={current_released_at!r}. Not generating a post -- "
            "a later run will generate once a newer release appears. Use --force to generate from "
            "this release instead."
        )
        return

    if args.force:
        print(f"--force: bypassing the freshness guard (current releasedAt={current_released_at!r}, prior={prior_released_at!r}).")
    else:
        fresh = freshness.is_release_fresh(current_released_at, prior_released_at)
        if not fresh:
            print(
                f"PRIME 25 releasedAt={current_released_at!r} is not newer than the last "
                f"generated release ({prior_released_at!r}); this is not a new release. "
                "Skipping. Use --force for a manual/backfill run."
            )
            return

    card_rows = [
        RankingsCardRow(
            rank=t["rank"], team=t["team"], conference=t.get("conf"),
            record=t.get("record", "—"), prime_score=t["primeScore"],
        )
        for t in teams
    ]

    output_dir = args.output_dir / str(season)
    output_path = output_dir / f"rankings-week-{week:02d}.png"
    render_rankings_card(season=season, week=week, rows=card_rows, output_path=output_path)
    print(f"Rendered {output_path}")

    top_teams = [RankedTeam(rank=t["rank"], team=t["team"], record=t.get("record", "—")) for t in teams[:3]]
    text, sources = build_rankings_weekly_caption(
        season=season, week=week, top_teams=top_teams, prime_rankings_path=prime_rankings_rel,
    )
    print(f"Caption ({len(text)} chars):\n{text}")

    alt_text = (
        f"Table of the PRIME 25 college football rankings for Week {week} of the {season} season: "
        "rank, team, conference, record, and PRIME score for each ranked team."
    )

    target = scheduling.intended_publication_target(scheduling.utc_now())
    if target.missed_window:
        print(f"NOTE: generated after the 3:00 PM ET Sunday publish window (scheduled_at={target.scheduled_at.isoformat()}).")

    row = {
        "platform": "twitter",
        "event_type": "rankings_weekly",
        "season": season,
        "week": week,
        "game_ids": None,
        "team_slugs": [t["slug"] for t in teams],
        "dedupe_key": dedupe_key,
        "status": "candidate",
        "publish_policy": policy.resolve_policy("rankings_weekly").value,
        "text_content": text,
        "alt_text": alt_text,
        "image_storage_path": output_path.relative_to(REPO).as_posix(),
        "image_url": None,
        "caption_version": RANKINGS_WEEKLY_CAPTION_VERSION,
        "render_version": RENDER_VERSION,
        "content_hash": content_hash(text, sources),
        "sources": [s.to_dict() for s in sources],
        # Only the records actually used to build this candidate (the top-N
        # PRIME 25 teams) plus the season/week/release metadata they came
        # with -- not the broader rankings dataset.
        "source_snapshot": {
            "primeRankings": {
                "season": prime.get("season"), "throughWeek": week,
                "releasedAt": prime.get("releasedAt"), "teams": teams,
            },
        },
        "metadata": {
            "team_count": len(teams),
            "missed_publish_window": target.missed_window,
            "freshness_override": args.force,
            "prior_release_compared_against": prior_released_at,
            "generator": "scripts/generate_rankings_post.py",
            "git_sha": os.environ.get("GITHUB_SHA"),
        },
        "buffer_post_id": None,
        "buffer_channel_id": BUFFER_CHANNEL_ID,
        "scheduled_at": target.scheduled_at.isoformat(),
    }

    inserted = db.insert_post(base_url, secret, row)
    print(f"Inserted social_posts row id={inserted['id']} status={inserted['status']} dedupe_key={inserted['dedupe_key']}")
    _emit_github_output("social_post_id", inserted["id"])


if __name__ == "__main__":
    main()
