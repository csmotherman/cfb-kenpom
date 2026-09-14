"""Per-game drill-down export for the Advanced page's "click a rate cell"
game-log modal.

For every FBS team-game, publishes (a) that team's own single-game raw
numerator/denominator values for every "rate" stat family the Advanced page
displays, and (b) the SAME full field set for the opponent, but cumulative
through the week BEFORE this game (walk-forward, no lookahead) -- "what has
this opponent's defense/offense typically done up to this point." Which
opponent field is the relevant baseline for a given team field (e.g. this
team's offensive YPP this game vs. the opponent's DEFENSIVE YPP allowed
coming in) is a UI-facing decision, kept in web/app/advanced/page.tsx's
AdvColumn.opponentNum/opponentDen right next to the column definitions that
already say what num/den mean -- this export just publishes both teams' full
field sets and lets the frontend pick.

Field names deliberately match the site's own `wk` per-week raw-count
vocabulary (yppNum/yppDen, successNum/successDen, ...) from build_real_data.py,
just computed per single game (or per single-team running cumulative total)
instead of summed across a week -- so a reader who already knows one knows
the other.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from build_real_data import load_possession_seconds, load_processed_team_games

REPO = Path(__file__).resolve().parent.parent

GAME_LOGS_VERSION = "game-logs-v1"


def num(v):
    return v if isinstance(v, (int, float)) else 0


def extract_raw_fields(row, poss_seconds):
    """One team-game row's raw fields, keyed exactly like build_real_data.py's
    per-week `wr` accumulator -- see the `wr["..."] +=` block there."""
    gid = str(row.get("gameId") or row.get("game_id"))
    game_poss = poss_seconds.get(gid, {})
    own_seconds = game_poss.get(row["team"], 0)
    opp_seconds = game_poss.get(row.get("opponent"), 0)

    out = {
        "successNum": num(row.get("successfulPlays")),
        "successDen": num(row.get("successEligiblePlays")),
        "successNumA": num(row.get("successfulPlaysAllowed")),
        "successDenA": num(row.get("successEligiblePlaysAllowed")),
        "passSuccessNum": num(row.get("passSuccessfulPlays")),
        "passSuccessDen": num(row.get("passSuccessEligiblePlays")),
        "passSuccessNumA": num(row.get("passSuccessfulPlaysAllowed")),
        "passSuccessDenA": num(row.get("passSuccessEligiblePlaysAllowed")),
        "rushSuccessNum": num(row.get("rushSuccessfulPlays")),
        "rushSuccessDen": num(row.get("rushSuccessEligiblePlays")),
        "rushSuccessNumA": num(row.get("rushSuccessfulPlaysAllowed")),
        "rushSuccessDenA": num(row.get("rushSuccessEligiblePlaysAllowed")),
        "explosiveNum": num(row.get("explosivePlays")),
        "explosiveDen": num(row.get("explosiveEligiblePlays")),
        "explosiveNumA": num(row.get("explosivePlaysAllowed")),
        "explosiveDenA": num(row.get("explosiveEligiblePlaysAllowed")),
        "yppNum": num(row.get("offensiveYards")),
        "yppDen": num(row.get("offensivePlays")),
        "yppNumA": num(row.get("defensiveYardsAllowed")),
        "yppDenA": num(row.get("defensivePlays")),
        "finNum": num(row.get("opportunityPoints")),
        "finDen": num(row.get("resolvedPointOpportunities")),
        "finNumA": num(row.get("opportunityPointsAllowed")),
        "finDenA": num(row.get("resolvedPointOpportunitiesAllowed")),
        "havocAllowedNum": num(row.get("havocPlaysAllowed")),
        "havocAllowedDen": num(row.get("havocEligiblePlays")),
        "havocForcedNum": num(row.get("havocPlays")),
        "havocForcedDen": num(row.get("havocEligiblePlaysFaced")),
        "dropbacks": num(row.get("dropbacks")),
        "rushAttempts": num(row.get("rushAttempts")),
        "dropbacksFaced": num(row.get("dropbacksFaced")),
        "rushAttemptsFaced": num(row.get("rushAttemptsFaced")),
        "offPlays": num(row.get("offensivePlays")),
        "offGames": 1 if row.get("offensivePlays") else 0,
        "possessionSeconds": own_seconds,
        "possessionSecondsTotal": own_seconds + opp_seconds,
    }
    if num(row.get("averageStartYardsToGoal")) and row.get("fieldPositionPossessions"):
        out["fieldPosSum"] = row["averageStartYardsToGoal"] * row["fieldPositionPossessions"]
        out["fieldPosCount"] = row["fieldPositionPossessions"]
    else:
        out["fieldPosSum"] = 0
        out["fieldPosCount"] = 0
    if num(row.get("averageStartYardsToGoalAllowed")) and row.get("fieldPositionPossessionsAllowed"):
        out["fieldPosSumA"] = row["averageStartYardsToGoalAllowed"] * row["fieldPositionPossessionsAllowed"]
        out["fieldPosCountA"] = row["fieldPositionPossessionsAllowed"]
    else:
        out["fieldPosSumA"] = 0
        out["fieldPosCountA"] = 0
    return out


def build_year(year):
    games, weeks_present, week_labels = load_processed_team_games(year)
    poss_seconds = load_possession_seconds(year)

    team_meta = {}
    for row in games:
        team_meta[row["team"]] = {
            "slug": row.get("team_slug"),
            "teamId": row.get("team_id"),
            "conf": row.get("conference"),
        }

    # Running cumulative raw totals per team, keyed by the week AFTER which
    # they apply -- cumulative[team][w] = totals through site week w
    # (inclusive). A game in week W looks up the opponent's cumulative[W-1],
    # i.e. strictly before this game, matching the walk-forward convention
    # used everywhere else in this pipeline (see prior-season-baseline and
    # SOS/SOR notes above in build_real_data.py).
    by_team_games = defaultdict(list)
    for row in games:
        by_team_games[row["team"]].append(row)
    for rows in by_team_games.values():
        rows.sort(key=lambda r: r["_siteWeek"])

    cumulative_through = defaultdict(dict)  # team -> week -> totals dict
    for team, rows in by_team_games.items():
        running = defaultdict(float)
        for row in rows:
            wk = row["_siteWeek"]
            fields = extract_raw_fields(row, poss_seconds)
            for k, v in fields.items():
                running[k] += v
            cumulative_through[team][wk] = dict(running)

    def opponent_context(opponent, before_week):
        weeks = [w for w in cumulative_through.get(opponent, {}) if w < before_week]
        if not weeks:
            return None
        latest = max(weeks)
        ctx = dict(cumulative_through[opponent][latest])
        ctx["_gamesThroughWeek"] = latest
        return ctx

    by_team = defaultdict(list)
    for row in games:
        team = row["team"]
        opponent = row.get("opponent")
        wk = row["_siteWeek"]
        meta = team_meta.get(opponent, {})
        by_team[team].append({
            "gameId": str(row.get("gameId") or row.get("game_id")),
            "week": wk,
            "opponent": opponent,
            "opponentSlug": meta.get("slug"),
            "opponentTeamId": meta.get("teamId"),
            "opponentClassification": row.get("opponent_classification"),
            "homeAway": row.get("home_away"),
            "win": bool(row.get("win")),
            "pointsFor": row.get("points_for"),
            "pointsAgainst": row.get("points_against"),
            "own": extract_raw_fields(row, poss_seconds),
            "opponentContext": opponent_context(opponent, wk),
        })

    for rows in by_team.values():
        rows.sort(key=lambda r: r["week"])

    return {
        "version": GAME_LOGS_VERSION,
        "weeks": weeks_present,
        "weekLabels": week_labels,
        "byTeam": by_team,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, action="append", help="Season(s) to build. Repeatable. Default: every season with canonical data.")
    parser.add_argument("--out-dir", default=str(REPO / "web/public/data/gamelogs"))
    args = parser.parse_args()

    if args.season:
        years = args.season
    else:
        years = sorted(
            int(p.name.split("=")[1])
            for p in (REPO / "data/canonical").glob("season=*")
            if (p / "team_games.json").is_file()
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for year in years:
        payload = build_year(year)
        team_count = len(payload["byTeam"])
        game_count = sum(len(v) for v in payload["byTeam"].values())
        out_path = out_dir / f"{year}.json"
        out_path.write_text(json.dumps(payload, separators=(",", ":")))
        print(f"season {year}: {team_count} teams, {game_count} team-games -> {out_path}")


if __name__ == "__main__":
    main()
