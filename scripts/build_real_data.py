import json
import math
import sys
from pathlib import Path
from collections import defaultdict

from cfb_analytics.analytics.iterative_ratings import fit_all_ratings, fit_srs

REPO = Path(__file__).resolve().parent.parent

# Strength of Record (SOR) -- "wins above an average team on this exact
# schedule," fully decoupled from the team's own rating so it can't just
# recreate AdjEM.
#
# For each game a team played, take the OPPONENT's real pregame walk-forward
# SRS rating (homeSrs/awaySrs from the locked srs-v2 iterative model, already
# used for SOS) and that week's SRS fit residual (srsFitRmse, already
# computed, just not previously consumed downstream). Since SRS is literally
# on a point-margin scale (rating(home) - rating(away) = predicted margin)
# and is zero-centered by construction, plugging in a rating of 0 for "this
# team" gives the probability that an exactly-average FBS team would have
# won that specific game:
#
#     p_ref = ncdf(-opponent_srs / srsFitRmse)
#
# (home/away drops out of the formula once the team's own rating is set to
# 0). Sum p_ref across a team's real schedule for "expected wins," sum
# actual wins over the same games, and SOR = actual wins - expected wins.
# Positive means the record is better than an average team would produce
# against that schedule; negative means worse. Games before any SRS fit
# exists (no srsFitRmse yet) are excluded from both sums, matching how
# early-season SOS/CFF stay null.
SOR_VERSION = "sor-v1-wins-above-average"


def _ncdf(x):
    """Standard normal CDF via erf -- same probit form already used for
    win probability in profiles/historical_tournament.py's _win_prob."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

CONF_ABBR = {
    "ACC": "ACC", "American Athletic": "AAC", "Big 12": "B12", "Big Ten": "B1G",
    "Conference USA": "CUSA", "FBS Independents": "IND", "Mid-American": "MAC",
    "Mountain West": "MWC", "Pac-12": "PAC", "SEC": "SEC", "Sun Belt": "SBC",
}

YEARS = [2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_canonical_games(year):
    """Regular season AND postseason (bowls, CFP) -- both are real, played,
    complete games in the canonical corpus (data/canonical already carries
    both season_types; the core cfb_analytics pipeline never filtered this
    out). Excluding postseason here previously meant a team's displayed
    record, and every locally-summed site stat, stopped updating once the
    regular season ended -- an undefeated team that then won its bowl/CFP
    games still showed its pre-bowl (occasionally its actual final) record,
    and a team that LOST in the playoff could show as still-undefeated."""
    rows = json.loads((REPO / f"data/canonical/season={year}/team_games.json").read_text())
    return [
        r for r in rows
        if r.get("season_type") in ("regular", "postseason") and r.get("classification") == "fbs"
    ]


def load_possession_seconds(year):
    """Real per-game, per-team possession time in seconds, summed from each
    offensive drive's real elapsed clock time (data/raw/cfbd .../drives.json).
    No locked time-of-possession metric exists yet in this project's derived
    pipeline, so this sums the raw per-drive `elapsed` field directly --
    a standard, unambiguous derivation, not a new methodology."""
    import glob
    out = defaultdict(lambda: defaultdict(int))  # gameId -> team -> seconds
    pattern = str(REPO / f"data/raw/cfbd/season={year}/season_type=regular/week=*/drives.json")
    for fp in glob.glob(pattern):
        for d in json.loads(Path(fp).read_text()):
            elapsed = d.get("elapsed")
            if not elapsed:
                continue
            seconds = (elapsed.get("minutes") or 0) * 60 + (elapsed.get("seconds") or 0)
            out[str(d["gameId"])][d["offense"]] += seconds
    return out


def build_site_week_map(year):
    """CFBD's own week numbers lump the early-openers weekend (e.g. Aug
    29-30) and the following week's main slate into a single 'week 1' --
    confirmed against CFBD's official calendar (no week=0 exists) and
    against real 2024/2025/2026 game dates (same two-cluster pattern each
    year). Rather than following that as gospel, this reconstructs real
    chronological regular-season site-weeks: within each CFBD week, a 3+ day
    gap between distinct game dates splits it into separate weeks, numbered
    in order. No CFBD week is invented or renumbered by fiat -- this is
    purely a date-gap read of real game dates.

    Postseason games are grouped differently, by CFBD's own structured
    `playoff` field (round: first_round/quarterfinal/semifinal/championship,
    present and consistent back to 2014) rather than by date gaps -- a bowl
    season date-gap split would arbitrarily fracture "bowl season" into
    several oddly-timed chunks (e.g. around a no-games Christmas Day) with
    no real identity, and would just as arbitrarily lump CFP rounds by
    whatever week number CFBD happened to file them under. Every playoff
    round becomes its own site-week in real chronological order; every
    other postseason game (a real, non-playoff bowl -- `playoff` is null)
    collapses into one final "Bowl Season" site-week, since that's a single
    recognizable stretch of the calendar, not several.

    Returns (site_week_by_game, num_site_weeks, week_labels) where
    week_labels maps a site-week number to a human label (e.g. "CFP
    Semifinal") for any week that isn't just "Week N" -- currently only
    postseason weeks get one."""
    import glob
    from datetime import date

    PLAYOFF_LABELS = {
        "first_round": "CFP First Round",
        "quarterfinal": "CFP Quarterfinal",
        "semifinal": "CFP Semifinal",
        "championship": "National Championship",
    }

    regular_by_week = defaultdict(list)  # cfbd_week -> [(date, gameId)]
    postseason_by_round = defaultdict(list)  # round_key -> [(date, gameId)]
    pattern = str(REPO / f"data/raw/cfbd/season={year}/season_type=*/week=*/games.json")
    for fp in glob.glob(pattern):
        for g in json.loads(Path(fp).read_text()):
            d = date.fromisoformat(g["startDate"][:10])
            gid = str(g["id"])
            if g.get("seasonType") == "postseason":
                playoff = g.get("playoff")
                round_key = playoff["round"] if playoff and playoff.get("round") else "bowl"
                postseason_by_round[round_key].append((d, gid))
            else:
                regular_by_week[g["week"]].append((d, gid))

    clusters = []  # list of [(date, gameId), ...], in final site-week order
    for cfbd_week, entries in regular_by_week.items():
        entries.sort(key=lambda e: e[0])
        current = [entries[0]]
        for d, gid in entries[1:]:
            if (d - current[-1][0]).days >= 3:
                clusters.append(current)
                current = []
            current.append((d, gid))
        clusters.append(current)
    clusters.sort(key=lambda c: c[0][0])

    postseason_clusters = sorted(postseason_by_round.items(), key=lambda kv: min(d for d, _ in kv[1]))
    week_labels = {}
    for round_key, entries in postseason_clusters:
        week_labels[len(clusters)] = "Bowl Season" if round_key == "bowl" else PLAYOFF_LABELS.get(round_key, round_key)
        clusters.append(entries)

    site_week_by_game = {}
    for site_week, cluster in enumerate(clusters):
        for _, gid in cluster:
            site_week_by_game[gid] = site_week

    return site_week_by_game, len(clusters), week_labels


def load_iterative(year):
    path = REPO / f"data/processed/derived/iterative_ratings/season={year}/games.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())
    return {r["gameId"]: r for r in rows}


def side_prefix(iter_row, team_name):
    if iter_row is None:
        return None
    if iter_row.get("homeTeam") == team_name:
        return "home_"
    if iter_row.get("awayTeam") == team_name:
        return "away_"
    return None


def new_acc():
    return {
        "wins": 0, "losses": 0,
        "successNum": 0, "successDen": 0, "explosiveNum": 0, "explosiveDen": 0,
        "yppNum": 0, "yppDen": 0, "yppoNum": 0, "yppoDen": 0,
        "finNum": 0, "finDen": 0, "fieldPosSum": 0.0, "fieldPosCount": 0,
        "passSuccessNum": 0, "passSuccessDen": 0, "rushSuccessNum": 0, "rushSuccessDen": 0,
        "dropbacks": 0, "rushAttempts": 0, "offPlaysTotal": 0,
        "dropbacksFaced": 0, "rushAttemptsFaced": 0,
        "successNumA": 0, "successDenA": 0, "explosiveNumA": 0, "explosiveDenA": 0,
        "yppNumA": 0, "yppDenA": 0, "yppoNumA": 0, "yppoDenA": 0,
        "finNumA": 0, "finDenA": 0, "fieldPosSumA": 0.0, "fieldPosCountA": 0,
        "passSuccessNumA": 0, "passSuccessDenA": 0, "rushSuccessNumA": 0, "rushSuccessDenA": 0,
        "gamesPlayed": 0,
        "opponentSrsSum": 0.0, "opponentSrsCount": 0,
        "sorActualWins": 0.0, "sorExpectedWins": 0.0, "sorGames": 0,
        "slug": None, "teamId": None, "conf": None,
    }


def build_year(year):
    games = load_canonical_games(year)
    iter_by_game = load_iterative(year)
    poss_seconds = load_possession_seconds(year)
    site_week_by_game, _, week_labels = build_site_week_map(year)

    for row in games:
        gid = str(row.get("gameId") or row.get("game_id"))
        row["_siteWeek"] = site_week_by_game.get(gid)
    games = [r for r in games if r["_siteWeek"] is not None]
    games.sort(key=lambda r: r["_siteWeek"])
    weeks_present = sorted(set(r["_siteWeek"] for r in games))
    if not weeks_present:
        return {}, {}
    week_labels = {wk: label for wk, label in week_labels.items() if wk in weeks_present}

    cum = defaultdict(new_acc)
    out_by_week = {}

    # CFF/AdjO/AdjD ("cff"/"off"/"def"/etc. below) come from a fresh,
    # league-wide re-solve at the end of EVERY site-week, using every game
    # played through that week -- not from freezing each team's value at
    # their own last game. SRS and the offense/defense iterative ratings are
    # both simultaneous systems (every team's rating depends on the whole
    # connected schedule graph), so a game between two OTHER teams can and
    # should move a third team's rating too. Freezing at "this team's own
    # last game" silently hid that: a team's numbers looked stale in any
    # week it didn't play, even though the model underneath had moved.
    # Reuses fit_srs/fit_all_ratings directly -- the same locked srs-v2 and
    # iterative-ratings-v2 solvers, just called with "history = every game
    # through this site-week" instead of "history = strictly before this
    # one game" (that per-game, leakage-safe cut is still exactly right for
    # the separate prediction-model dataset in iterative_ratings.py, which
    # this does not touch).
    srs_games_by_id = {}
    metric_history = []

    for wk in weeks_present:
        # Per-week-only (not cumulative) raw counts, so the client can sum an
        # arbitrary [start,end] range correctly. Model-based (schedule-adjusted)
        # values below are NOT summable this way -- they're single fitted
        # snapshots, so those stay cumulative/latest-only.
        wk_raw = defaultdict(lambda: defaultdict(float))

        for row in (r for r in games if r["_siteWeek"] == wk):
            name = row["team"]
            acc = cum[name]
            wr = wk_raw[name]
            wr["wins"] += row.get("win", 0) or 0
            wr["losses"] += row.get("loss", 0) or 0
            wr["successNum"] += row.get("successfulPlays", 0) or 0
            wr["successDen"] += row.get("successEligiblePlays", 0) or 0
            wr["successNumA"] += row.get("successfulPlaysAllowed", 0) or 0
            wr["successDenA"] += row.get("successEligiblePlaysAllowed", 0) or 0
            wr["passSuccessNum"] += row.get("passSuccessfulPlays", 0) or 0
            wr["passSuccessDen"] += row.get("passSuccessEligiblePlays", 0) or 0
            wr["passSuccessNumA"] += row.get("passSuccessfulPlaysAllowed", 0) or 0
            wr["passSuccessDenA"] += row.get("passSuccessEligiblePlaysAllowed", 0) or 0
            wr["rushSuccessNum"] += row.get("rushSuccessfulPlays", 0) or 0
            wr["rushSuccessDen"] += row.get("rushSuccessEligiblePlays", 0) or 0
            wr["rushSuccessNumA"] += row.get("rushSuccessfulPlaysAllowed", 0) or 0
            wr["rushSuccessDenA"] += row.get("rushSuccessEligiblePlaysAllowed", 0) or 0
            wr["dropbacks"] += row.get("dropbacks", 0) or 0
            wr["rushAttempts"] += row.get("rushAttempts", 0) or 0
            wr["dropbacksFaced"] += row.get("dropbacksFaced", 0) or 0
            wr["rushAttemptsFaced"] += row.get("rushAttemptsFaced", 0) or 0
            wr["offPlays"] += row.get("offensivePlays", 0) or 0
            wr["games"] += 1

            game_id = str(row.get("gameId") or row.get("game_id"))
            game_poss = poss_seconds.get(game_id, {})
            own_seconds = game_poss.get(name, 0)
            opp_seconds = game_poss.get(row.get("opponent"), 0)
            wr["possessionSeconds"] += own_seconds
            wr["possessionSecondsTotal"] += (own_seconds + opp_seconds)

            # Feed this game into the cumulative-through-this-week fit inputs.
            # fit_all_ratings wants one row per team per game (exactly this
            # canonical shape); fit_srs wants one row per game, so only the
            # home side's row is kept (deduped by gameId, which also makes
            # this idempotent if a game were ever seen from both sides).
            metric_history.append(row)
            if row.get("home_away") == "home":
                srs_games_by_id[game_id] = {
                    "gameId": game_id,
                    "homeTeam": row["team"],
                    "awayTeam": row.get("opponent"),
                    "target_margin": (row.get("points_for") or 0) - (row.get("points_against") or 0),
                }

            acc["slug"] = row.get("team_slug")
            acc["teamId"] = row.get("team_id")
            acc["conf"] = CONF_ABBR.get(row.get("conference"), (row.get("conference") or "IND")[:4].upper())
            acc["gamesPlayed"] += 1
            acc["wins"] += row.get("win", 0) or 0
            acc["losses"] += row.get("loss", 0) or 0

            acc["successNum"] += row.get("successfulPlays", 0) or 0
            acc["successDen"] += row.get("successEligiblePlays", 0) or 0
            acc["explosiveNum"] += row.get("explosivePlays", 0) or 0
            acc["explosiveDen"] += row.get("explosiveEligiblePlays", 0) or 0
            acc["yppNum"] += row.get("offensiveYards", 0) or 0
            acc["yppDen"] += row.get("offensivePlays", 0) or 0
            acc["yppoNum"] += row.get("possessionYards", 0) or 0
            acc["yppoDen"] += row.get("yardagePossessions", 0) or 0
            acc["finNum"] += row.get("opportunityPoints", 0) or 0
            acc["finDen"] += row.get("resolvedPointOpportunities", 0) or 0
            if num(row.get("averageStartYardsToGoal")) and row.get("fieldPositionPossessions"):
                acc["fieldPosSum"] += row["averageStartYardsToGoal"] * row["fieldPositionPossessions"]
                acc["fieldPosCount"] += row["fieldPositionPossessions"]
            acc["passSuccessNum"] += row.get("passSuccessfulPlays", 0) or 0
            acc["passSuccessDen"] += row.get("passSuccessEligiblePlays", 0) or 0
            acc["rushSuccessNum"] += row.get("rushSuccessfulPlays", 0) or 0
            acc["rushSuccessDen"] += row.get("rushSuccessEligiblePlays", 0) or 0
            acc["dropbacks"] += row.get("dropbacks", 0) or 0
            acc["rushAttempts"] += row.get("rushAttempts", 0) or 0
            acc["offPlaysTotal"] += row.get("offensivePlays", 0) or 0

            acc["successNumA"] += row.get("successfulPlaysAllowed", 0) or 0
            acc["successDenA"] += row.get("successEligiblePlaysAllowed", 0) or 0
            acc["explosiveNumA"] += row.get("explosivePlaysAllowed", 0) or 0
            acc["explosiveDenA"] += row.get("explosiveEligiblePlaysAllowed", 0) or 0
            acc["yppNumA"] += row.get("defensiveYardsAllowed", 0) or 0
            acc["yppDenA"] += row.get("defensivePlays", 0) or 0
            acc["yppoNumA"] += row.get("possessionYardsAllowed", 0) or 0
            acc["yppoDenA"] += row.get("yardagePossessionsAllowed", 0) or 0
            acc["finNumA"] += row.get("opportunityPointsAllowed", 0) or 0
            acc["finDenA"] += row.get("resolvedPointOpportunitiesAllowed", 0) or 0
            if num(row.get("averageStartYardsToGoalAllowed")) and row.get("fieldPositionPossessionsAllowed"):
                acc["fieldPosSumA"] += row["averageStartYardsToGoalAllowed"] * row["fieldPositionPossessionsAllowed"]
                acc["fieldPosCountA"] += row["fieldPositionPossessionsAllowed"]
            acc["passSuccessNumA"] += row.get("passSuccessfulPlaysAllowed", 0) or 0
            acc["passSuccessDenA"] += row.get("passSuccessEligiblePlaysAllowed", 0) or 0
            acc["rushSuccessNumA"] += row.get("rushSuccessfulPlaysAllowed", 0) or 0
            acc["rushSuccessDenA"] += row.get("rushSuccessEligiblePlaysAllowed", 0) or 0
            acc["dropbacksFaced"] += row.get("dropbacksFaced", 0) or 0
            acc["rushAttemptsFaced"] += row.get("rushAttemptsFaced", 0) or 0

            # SOS/SOR still use the per-game walk-forward opponent rating
            # (iter_row, from iterative_ratings.py's own locked per-game
            # dataset) -- that's a genuinely different, correct use of
            # "before this specific game" leakage-safety: schedule strength
            # is about how good the opponent looked AT THE TIME they were
            # played, not revised in hindsight the way cff/off/def now are.
            iter_row = iter_by_game.get(row.get("gameId") or row.get("game_id"))
            prefix = side_prefix(iter_row, name)
            if prefix:
                opp_prefix = "away_" if prefix == "home_" else "home_"
                opp_srs = iter_row.get(opp_prefix[:-1] + "Srs")
                if num(opp_srs):
                    acc["opponentSrsSum"] += opp_srs
                    acc["opponentSrsCount"] += 1
                    wr = wk_raw[name]
                    wr["opponentSrsSum"] += opp_srs
                    wr["opponentSrsCount"] += 1

                    sigma = iter_row.get("srsFitRmse")
                    if num(sigma) and sigma > 0:
                        acc["sorExpectedWins"] += _ncdf(-opp_srs / sigma)
                        acc["sorActualWins"] += row.get("win", 0) or 0
                        acc["sorGames"] += 1

        # League-wide re-solve using every game played through this site-week
        # (see the comment above the loop). One fit_srs + one fit_all_ratings
        # call per week, not per team -- every team's snapshot below reads
        # out of the same shared result.
        srs_ratings = fit_srs(list(srs_games_by_id.values()))["ratings"] if srs_games_by_id else {}
        metric_ratings = fit_all_ratings(metric_history) if metric_history else {}

        def metric(spec, side, team):
            v = metric_ratings.get(spec, {}).get(side, {}).get(team)
            return v if num(v) else None

        week_rows = []
        for name, acc in cum.items():
            if acc["gamesPlayed"] == 0:
                continue

            def rate(n, d):
                return round(n / d, 4) if d else None

            cff = srs_ratings.get(name)
            off_ypp, def_ypp = metric("YardsPerPossession", "offense", name), metric("YardsPerPossession", "defense", name)
            off_yppl, def_yppl = metric("YardsPerPlay", "offense", name), metric("YardsPerPlay", "defense", name)
            off_exp, def_exp = metric("Explosive", "offense", name), metric("Explosive", "defense", name)
            off_fin, def_fin = metric("Finishing", "offense", name), metric("Finishing", "defense", name)
            field_pos = metric("FieldPosition", "offense", name)

            week_rows.append({
                "team": name, "slug": acc["slug"], "teamId": acc["teamId"], "conf": acc["conf"],
                "record": f"{acc['wins']}-{acc['losses']}", "wins": acc["wins"],
                "gamesPlayed": acc["gamesPlayed"],
                "cff": round(cff, 2) if num(cff) else None,
                "sos": round(acc["opponentSrsSum"] / acc["opponentSrsCount"], 2) if acc["opponentSrsCount"] else None,
                "sor": round(acc["sorActualWins"] - acc["sorExpectedWins"], 2) if acc["sorGames"] else None,
                "sorExpectedWins": round(acc["sorExpectedWins"], 2) if acc["sorGames"] else None,
                "fieldPos": round(field_pos, 2) if num(field_pos) else None,
                "pace": round(acc["offPlaysTotal"] / acc["gamesPlayed"], 1),
                "off": round(off_ypp, 2) if num(off_ypp) else None,
                "offSuccess": rate(acc["successNum"], acc["successDen"]),
                "offYardsPerPlay": round(off_yppl, 3) if num(off_yppl) else None,
                "offPassSuccess": rate(acc["passSuccessNum"], acc["passSuccessDen"]),
                "offRushSuccess": rate(acc["rushSuccessNum"], acc["rushSuccessDen"]),
                "offPassRate": rate(acc["dropbacks"], acc["dropbacks"] + acc["rushAttempts"]),
                "offExp": round(off_exp, 2) if num(off_exp) else None,
                "offFin": round(off_fin, 2) if num(off_fin) else None,
                "def": round(def_ypp, 2) if num(def_ypp) else None,
                "defSuccess": rate(acc["successNumA"], acc["successDenA"]),
                "defYardsPerPlay": round(def_yppl, 3) if num(def_yppl) else None,
                "defPassSuccess": rate(acc["passSuccessNumA"], acc["passSuccessDenA"]),
                "defRushSuccess": rate(acc["rushSuccessNumA"], acc["rushSuccessDenA"]),
                "defPassRate": rate(acc["dropbacksFaced"], acc["dropbacksFaced"] + acc["rushAttemptsFaced"]),
                "defExp": round(def_exp, 2) if num(def_exp) else None,
                "defFin": round(def_fin, 2) if num(def_fin) else None,
                # This week's own (non-cumulative) raw counts, for correct
                # client-side summing over an arbitrary [start,end] range.
                "wk": dict(wk_raw.get(name, {})),
            })

        out_by_week[wk] = week_rows  # wk is already a real chronological site-week (see build_site_week_map)

    return out_by_week, week_labels


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    weeks, week_labels = build_year(year)
    print("year", year, "weeks with data:", sorted(weeks.keys()))
    print("week labels:", week_labels)
    last_wk = max(weeks.keys())
    rows = [r for r in weeks[last_wk] if r["cff"] is not None]
    rows.sort(key=lambda r: -r["cff"])
    print(f"-- final week {last_wk} ({week_labels.get(last_wk, 'Week ' + str(last_wk))}) top 10 by CFF (SRS) --")
    for r in rows[:10]:
        print(f"{r['team']:20s} rec={r['record']:6s} cff={r['cff']:>7} sos={r['sos']:>7} off={r['off']} def={r['def']} gp={r['gamesPlayed']}")
    print(f"teams with a CFF value: {len(rows)} / {len(weeks[last_wk])} total teams with games")
