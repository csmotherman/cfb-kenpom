"""Submit LEILA's early-season predictions to CFBD's Model Pick'em.

CFBD's Pick'em is a separate API from the main CFBD data API (different
host, different key -- CFBD_MODEL_KEY, not CFBD_API_KEY) where registered
models submit a predicted point margin for a curated slate of games each
week. https://blog.collegefootballdata.com/submitting-predictions-with/
documents the GET response shape accurately but its POST example (a bare
`{"gameId", "pick"}` object) is out of date and returns 400 "Invalid
request" -- confirmed empirically. The real shape, also confirmed
empirically, is a single batched request: {"picks": [{"gameId", "pick"},
...]}.

Sign convention: CFBD's `pick`/`spread` fields are home-team-relative,
NEGATIVE when the home team is favored (standard Vegas convention). LEILA's
own prospective/<season>/predictions/week-NN.json snapshots (written by
early_season_predictions.py) store `predictedMargin` in the OPPOSITE
sign -- POSITIVE when the home team is favored (see that file's own
`pred > 0 => home favored` convention). So cfbd_pick = -predictedMargin,
exactly.

Only games LEILA's early-season model actually scored are submitted --
CFBD's slate can include games this model deliberately has no prediction
for (an FCS opponent, a newly-FBS team with no prior-season baseline,
etc.); those are skipped rather than filled with an improvised number,
since a competition submission is a real, graded claim, not the "context
only" caption the site itself shows for ungraded games.
"""
from __future__ import annotations

import argparse
import json
import ssl
from pathlib import Path

import certifi
import httpx

from cfb_analytics.sources.cfbd.client import _env_file_value

REPO = Path(__file__).resolve().parent.parent
BASE_URL = "https://predictionsapi.collegefootballdata.com"
# The API sits behind Cloudflare and 403s (error code 1010) requests with no
# / a suspicious User-Agent -- a real browser UA is required, not optional.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def load_key() -> str:
    import os

    key = os.environ.get("CFBD_MODEL_KEY")
    if key:
        return key
    key = _env_file_value(REPO / ".env", "CFBD_MODEL_KEY")
    if key:
        return key
    raise RuntimeError("CFBD_MODEL_KEY is not set in the process environment or .env")


def make_client(key: str) -> httpx.Client:
    ctx = ssl.create_default_context(cafile=certifi.where())
    return httpx.Client(
        base_url=BASE_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        verify=ctx,
        timeout=20.0,
    )


def latest_prediction_week(season: int) -> int:
    pred_dir = REPO / "prospective" / str(season) / "predictions"
    weeks = sorted(int(p.stem.split("-")[1]) for p in pred_dir.glob("week-*.json"))
    if not weeks:
        raise RuntimeError(f"No prediction snapshots found under {pred_dir}")
    return weeks[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, default=None, help="Defaults to the latest scored week's snapshot.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be submitted without POSTing.")
    args = parser.parse_args()

    season = args.season
    week = args.week if args.week is not None else latest_prediction_week(season)

    snapshot_path = REPO / "prospective" / str(season) / "predictions" / f"week-{week:02d}.json"
    if not snapshot_path.exists():
        raise SystemExit(f"No LEILA prediction snapshot at {snapshot_path}")
    snapshot = json.loads(snapshot_path.read_text())
    our_predictions = {str(p["gameId"]): p for p in snapshot["predictions"]}

    client = make_client(load_key())
    response = client.get("/api/picks")
    if response.status_code != 200:
        raise SystemExit(f"GET /api/picks failed: {response.status_code} {response.text[:500]}")
    cfbd_games = [g for g in response.json() if g["week"] == week]

    matched: list[tuple[dict, dict, float]] = []
    already_picked: list[dict] = []
    unmatched: list[dict] = []
    for g in cfbd_games:
        gid = str(g["id"])
        pred = our_predictions.get(gid)
        if pred is None:
            unmatched.append(g)
            continue
        if g.get("pick") is not None:
            already_picked.append(g)
            continue
        cfbd_pick = round(-pred["predictedMargin"], 1)
        matched.append((g, pred, cfbd_pick))

    print(
        f"Season {season} week {week}: {len(cfbd_games)} CFBD games, {len(matched)} to submit, "
        f"{len(already_picked)} already picked, {len(unmatched)} with no LEILA prediction."
    )
    for g in unmatched:
        print(f"  SKIP (no LEILA prediction): {g['awayTeam']} @ {g['homeTeam']} (id {g['id']})")

    for g, pred, cfbd_pick in matched:
        tag = "DRY RUN" if args.dry_run else "SUBMIT "
        print(
            f"  {tag}: {g['awayTeam']} @ {g['homeTeam']} -> pick={cfbd_pick:+.1f} "
            f"(LEILA: {pred['predictedWinner']} by {abs(pred['predictedMargin']):.1f}, "
            f"conf {pred['confidence']:.0%}; CFBD spread {g.get('spread')})"
        )

    if args.dry_run:
        print("\nDry run -- nothing was submitted.")
        return

    # The API takes a single batched request: {"picks": [{"gameId", "pick"}, ...]}.
    # A bare, unwrapped object (as an older blog post describing this API
    # showed) returns 400 "Invalid request" -- confirmed empirically.
    payload = {"picks": [{"gameId": g["id"], "pick": cfbd_pick} for g, _pred, cfbd_pick in matched]}
    resp = client.post("/api/picks", json=payload)
    if resp.status_code in (200, 201, 204):
        print(f"\nSubmitted {len(matched)}/{len(matched)} picks successfully in one batch request.")
    else:
        raise SystemExit(f"Batch submit failed: {resp.status_code} {resp.text[:500]}")


if __name__ == "__main__":
    main()
