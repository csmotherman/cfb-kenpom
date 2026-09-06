import json
import sys
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent

CONF_ABBR = {
    "ACC": "ACC", "American Athletic": "AAC", "Big 12": "B12", "Big Ten": "B1G",
    "Conference USA": "CUSA", "FBS Independents": "IND", "Mid-American": "MAC",
    "Mountain West": "MWC", "Pac-12": "PAC", "SEC": "SEC", "Sun Belt": "SBC",
}

YEARS = [2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_canonical_games(year):
    rows = json.loads((REPO / f"data/canonical/season={year}/team_games.json").read_text())
    return [r for r in rows if r.get("season_type") == "regular" and r.get("classification") == "fbs"]


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
    chronological site-weeks: within each CFBD week, a 3+ day gap between
    distinct game dates splits it into separate weeks, numbered in order
    across the whole season. No CFBD week is invented or renumbered by
    fiat -- this is purely a date-gap read of real game dates."""
    import glob
    from datetime import date

    games_by_cfbd_week = defaultdict(list)  # cfbd_week -> [(date, gameId)]
    pattern = str(REPO / f"data/raw/cfbd/season={year}/season_type=regular/week=*/games.json")
    for fp in glob.glob(pattern):
        for g in json.loads(Path(fp).read_text()):
            d = date.fromisoformat(g["startDate"][:10])
            games_by_cfbd_week[g["week"]].append((d, str(g["id"])))

    clusters = []  # list of (earliest_date, {gameId,...})
    for cfbd_week, entries in games_by_cfbd_week.items():
        entries.sort(key=lambda e: e[0])
        current = [entries[0]]
        for d, gid in entries[1:]:
            if (d - current[-1][0]).days >= 3:
                clusters.append(current)
                current = []
            current.append((d, gid))
        clusters.append(current)

    clusters.sort(key=lambda c: c[0][0])

    site_week_by_game = {}
    for site_week, cluster in enumerate(clusters):
        for _, gid in cluster:
            site_week_by_game[gid] = site_week

    return site_week_by_game, len(clusters)


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
        "latestSrs": None, "latestOff": {}, "latestDef": {},
        "opponentSrsSum": 0.0, "opponentSrsCount": 0,
        "slug": None, "teamId": None, "conf": None,
    }


SPECS = ("Success", "Explosive", "YardsPerPlay", "YardsPerPossession", "Finishing", "FieldPosition")


def build_year(year):
    games = load_canonical_games(year)
    iter_by_game = load_iterative(year)
    poss_seconds = load_possession_seconds(year)
    site_week_by_game, _ = build_site_week_map(year)

    for row in games:
        gid = str(row.get("gameId") or row.get("game_id"))
        row["_siteWeek"] = site_week_by_game.get(gid)
    games = [r for r in games if r["_siteWeek"] is not None]
    games.sort(key=lambda r: r["_siteWeek"])
    weeks_present = sorted(set(r["_siteWeek"] for r in games))
    if not weeks_present:
        return {}

    cum = defaultdict(new_acc)
    out_by_week = {}

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

            iter_row = iter_by_game.get(row.get("gameId") or row.get("game_id"))
            prefix = side_prefix(iter_row, name)
            if prefix:
                srs_val = iter_row.get(prefix[:-1] + "Srs")
                if num(srs_val):
                    acc["latestSrs"] = srs_val
                for spec in SPECS:
                    off_v = iter_row.get(f"{prefix}iterative{spec}Offense")
                    def_v = iter_row.get(f"{prefix}iterative{spec}Defense")
                    if num(off_v):
                        acc["latestOff"][spec] = off_v
                    if num(def_v):
                        acc["latestDef"][spec] = def_v
                opp_prefix = "away_" if prefix == "home_" else "home_"
                opp_srs = iter_row.get(opp_prefix[:-1] + "Srs")
                if num(opp_srs):
                    acc["opponentSrsSum"] += opp_srs
                    acc["opponentSrsCount"] += 1
                    wr = wk_raw[name]
                    wr["opponentSrsSum"] += opp_srs
                    wr["opponentSrsCount"] += 1

        week_rows = []
        for name, acc in cum.items():
            if acc["gamesPlayed"] == 0:
                continue

            def rate(n, d):
                return round(n / d, 4) if d else None

            week_rows.append({
                "team": name, "slug": acc["slug"], "teamId": acc["teamId"], "conf": acc["conf"],
                "record": f"{acc['wins']}-{acc['losses']}", "wins": acc["wins"],
                "gamesPlayed": acc["gamesPlayed"],
                "cff": round(acc["latestSrs"], 2) if num(acc["latestSrs"]) else None,
                "sos": round(acc["opponentSrsSum"] / acc["opponentSrsCount"], 2) if acc["opponentSrsCount"] else None,
                "fieldPos": round(acc["latestOff"].get("FieldPosition"), 2) if "FieldPosition" in acc["latestOff"] else None,
                "pace": round(acc["offPlaysTotal"] / acc["gamesPlayed"], 1),
                "off": round(acc["latestOff"].get("YardsPerPossession"), 2) if "YardsPerPossession" in acc["latestOff"] else None,
                "offSuccess": rate(acc["successNum"], acc["successDen"]),
                "offYardsPerPlay": round(acc["latestOff"].get("YardsPerPlay"), 3) if "YardsPerPlay" in acc["latestOff"] else None,
                "offPassSuccess": rate(acc["passSuccessNum"], acc["passSuccessDen"]),
                "offRushSuccess": rate(acc["rushSuccessNum"], acc["rushSuccessDen"]),
                "offPassRate": rate(acc["dropbacks"], acc["dropbacks"] + acc["rushAttempts"]),
                "offExp": round(acc["latestOff"].get("Explosive"), 2) if "Explosive" in acc["latestOff"] else None,
                "offFin": round(acc["latestOff"].get("Finishing"), 2) if "Finishing" in acc["latestOff"] else None,
                "def": round(acc["latestDef"].get("YardsPerPossession"), 2) if "YardsPerPossession" in acc["latestDef"] else None,
                "defSuccess": rate(acc["successNumA"], acc["successDenA"]),
                "defYardsPerPlay": round(acc["latestDef"].get("YardsPerPlay"), 3) if "YardsPerPlay" in acc["latestDef"] else None,
                "defPassSuccess": rate(acc["passSuccessNumA"], acc["passSuccessDenA"]),
                "defRushSuccess": rate(acc["rushSuccessNumA"], acc["rushSuccessDenA"]),
                "defPassRate": rate(acc["dropbacksFaced"], acc["dropbacksFaced"] + acc["rushAttemptsFaced"]),
                "defExp": round(acc["latestDef"].get("Explosive"), 2) if "Explosive" in acc["latestDef"] else None,
                "defFin": round(acc["latestDef"].get("Finishing"), 2) if "Finishing" in acc["latestDef"] else None,
                # This week's own (non-cumulative) raw counts, for correct
                # client-side summing over an arbitrary [start,end] range.
                "wk": dict(wk_raw.get(name, {})),
            })

        out_by_week[wk] = week_rows  # wk is already a real chronological site-week (see build_site_week_map)

    return out_by_week


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    weeks = build_year(year)
    print("year", year, "weeks with data:", sorted(weeks.keys()))
    last_wk = max(weeks.keys())
    rows = [r for r in weeks[last_wk] if r["cff"] is not None]
    rows.sort(key=lambda r: -r["cff"])
    print(f"-- final week {last_wk} top 10 by CFF (SRS) --")
    for r in rows[:10]:
        print(f"{r['team']:20s} rec={r['record']:6s} cff={r['cff']:>7} sos={r['sos']:>7} off={r['off']} def={r['def']} gp={r['gamesPlayed']}")
    print(f"teams with a CFF value: {len(rows)} / {len(weeks[last_wk])} total teams with games")
