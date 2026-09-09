import argparse
import json
import math
import sys
from pathlib import Path
from collections import defaultdict

from cfb_analytics.analytics import rating_model as rating_models
from cfb_analytics.analytics.iterative_ratings import fit_all_ratings, fit_srs
from cfb_analytics.derived.games import metric_fields_by_team_game

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

# Generic FCS opponent strength for SOS/SOR -- not a per-team FCS rating (no
# FCS team ever enters the core FBS rating graph; see the metric_history/
# srs_games_by_id guard below), just a single scalar "how good is a typical
# FCS opponent" on the same SRS point-margin scale (0 = average FBS team).
# Recalibrated fresh every site-week from that week's own games: solve for
# the constant fcs_baseline such that, averaged across every FBS-vs-FCS
# result played so far this season, "fbs_srs - fcs_baseline" reproduces the
# FBS team's real margin. Requires at least this many graded results
# league-wide before trusting the average -- below that, FCS games are
# excluded from SOS/SOR exactly like any other not-enough-data-yet case.
FCS_BASELINE_MIN_GAMES = 10


def _ncdf(x):
    """Standard normal CDF via erf -- same probit form already used for
    win probability in profiles/historical_tournament.py's _win_prob."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def calibrate_fcs_baseline(fcs_games_log, srs_ratings, min_games=FCS_BASELINE_MIN_GAMES):
    """Solve for the single scalar fcs_baseline (see FCS_BASELINE_MIN_GAMES
    above) from every {"team", "margin"} result an FBS team has posted
    against an FCS/lower-division opponent so far. Returns None below
    min_games, same as any other not-enough-data-yet case in this file."""
    errors = [
        srs_ratings[g["team"]] - g["margin"]
        for g in fcs_games_log
        if num(srs_ratings.get(g["team"]))
    ]
    if len(errors) < min_games:
        return None
    return sum(errors) / len(errors)


# EPA (games.py's epa-v1-cfbd-ppa) and the pass/rush-by-down Success Rate
# splits: (accumulator prefix, raw numerator field on the row, raw
# denominator field on the row). Overall pass/rush Success already has its
# own accumulator (passSuccessNum/rushSuccessNum below) from earlier work,
# so it's not duplicated here.
EPA_SUCCESS_SPLIT_FIELDS = (
    ("epa", "epaSum", "epaPlays"),
    ("passEpa", "passEpaSum", "passEpaPlays"),
    ("rushEpa", "rushEpaSum", "rushEpaPlays"),
    ("passDown1Epa", "passDown1EpaSum", "passDown1EpaPlays"),
    ("passDown2Epa", "passDown2EpaSum", "passDown2EpaPlays"),
    ("passDown3Epa", "passDown3EpaSum", "passDown3EpaPlays"),
    ("rushDown1Epa", "rushDown1EpaSum", "rushDown1EpaPlays"),
    ("rushDown2Epa", "rushDown2EpaSum", "rushDown2EpaPlays"),
    ("rushDown3Epa", "rushDown3EpaSum", "rushDown3EpaPlays"),
    ("passDown1Success", "passDown1SuccessfulPlays", "passDown1SuccessEligiblePlays"),
    ("passDown2Success", "passDown2SuccessfulPlays", "passDown2SuccessEligiblePlays"),
    ("passDown3Success", "passDown3SuccessfulPlays", "passDown3SuccessEligiblePlays"),
    ("rushDown1Success", "rushDown1SuccessfulPlays", "rushDown1SuccessEligiblePlays"),
    ("rushDown2Success", "rushDown2SuccessfulPlays", "rushDown2SuccessEligiblePlays"),
    ("rushDown3Success", "rushDown3SuccessfulPlays", "rushDown3SuccessEligiblePlays"),
)


def adjustment_confidence(games_played, ramp_games=None):
    """0.0 at games_played<=1 (no opponent baseline yet), ramping linearly
    to 1.0 by ramp_games (EPA_ADJUSTMENT_RAMP_GAMES if not given)."""
    ramp_games = EPA_ADJUSTMENT_RAMP_GAMES if ramp_games is None else ramp_games
    if games_played <= 1:
        return 0.0
    if ramp_games <= 1:
        return 1.0
    return min(1.0, (games_played - 1) / (ramp_games - 1))


def blend_edge(edge, league_mean, raw_rate, games_played, ramp_games=None):
    """See adjustment_confidence. Below full confidence, the remainder of
    the blend is raw_rate minus league_mean -- the team's own raw rate
    expressed on the same deviation-from-average scale as the fitted edge,
    not a fabricated partial adjustment."""
    if not num(edge) or not num(league_mean) or not num(raw_rate):
        return None
    confidence = adjustment_confidence(games_played, ramp_games)
    unadjusted_edge = raw_rate - league_mean
    return confidence * edge + (1.0 - confidence) * unadjusted_edge


def _accumulate_epa_success_splits(target, row):
    for prefix, num_field, den_field in EPA_SUCCESS_SPLIT_FIELDS:
        target[f"{prefix}Num"] += row.get(num_field, 0) or 0
        target[f"{prefix}Den"] += row.get(den_field, 0) or 0
        target[f"{prefix}NumA"] += row.get(num_field + "Allowed", 0) or 0
        target[f"{prefix}DenA"] += row.get(den_field + "Allowed", 0) or 0


# Games played before an opponent-adjusted EPA/Success edge is trusted at
# full strength. At 1 game played the blend below is 0% adjusted (no
# opponent baseline exists yet -- effectively raw); it ramps linearly to
# 100% adjusted by this many games, then holds there.
EPA_ADJUSTMENT_RAMP_GAMES = 5

# (site-facing key prefix, iterative_ratings SPEC name, raw accumulator
# prefix -- resolves to acc[f"{prefix}Num"]/f"{prefix}Den"/NumA/DenA).
EPA_SUCCESS_METRICS = (
    # "Success" has been fit since before this table existed (see SPECS
    # above) but never actually consumed anywhere on the site until now.
    ("success", "Success", "success"),
    ("epa", "EPA", "epa"),
    ("passEpa", "PassEPA", "passEpa"),
    ("rushEpa", "RushEPA", "rushEpa"),
    ("passEpaDown1", "PassEPADown1", "passDown1Epa"),
    ("passEpaDown2", "PassEPADown2", "passDown2Epa"),
    ("passEpaDown3", "PassEPADown3", "passDown3Epa"),
    ("rushEpaDown1", "RushEPADown1", "rushDown1Epa"),
    ("rushEpaDown2", "RushEPADown2", "rushDown2Epa"),
    ("rushEpaDown3", "RushEPADown3", "rushDown3Epa"),
    ("passSuccess", "PassSuccess", "passSuccess"),
    ("rushSuccess", "RushSuccess", "rushSuccess"),
    ("passSuccessDown1", "PassSuccessDown1", "passDown1Success"),
    ("passSuccessDown2", "PassSuccessDown2", "passDown2Success"),
    ("passSuccessDown3", "PassSuccessDown3", "passDown3Success"),
    ("rushSuccessDown1", "RushSuccessDown1", "rushDown1Success"),
    ("rushSuccessDown2", "RushSuccessDown2", "rushDown2Success"),
    ("rushSuccessDown3", "RushSuccessDown3", "rushDown3Success"),
)


CONF_ABBR = {
    "ACC": "ACC", "American Athletic": "AAC", "Big 12": "B12", "Big Ten": "B1G",
    "Conference USA": "CUSA", "FBS Independents": "IND", "Mid-American": "MAC",
    "Mountain West": "MWC", "Pac-12": "PAC", "SEC": "SEC", "Sun Belt": "SBC",
}

YEARS = [2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


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


def load_canonical_plays(year):
    """Every canonical play for a season, in partition order.

    Same corpus `derived/games.py` already materializes team-game metrics from
    -- this only re-reads it so the rating model can request the
    garbage-time-filtered aggregation that its validated study is defined on.
    """
    paths = sorted((REPO / f"data/processed/canonical/season={year}").glob("season_type=*/week=*/plays.json"))
    if not paths:
        raise rating_models.RatingModelError(
            f"Season {year}: the hierarchical rating model requires canonical plays at "
            f"data/processed/canonical/season={year}/; none were found. Materialize them or "
            "build this season with --rating-model legacy."
        )
    return [play for path in paths for play in json.loads(path.read_text())]


def load_possession_seconds(year):
    """Real per-game, per-team possession time in seconds, summed from each
    offensive drive's real elapsed clock time (data/raw/cfbd .../drives.json).
    No locked time-of-possession metric exists yet in this project's derived
    pipeline, so this sums the raw per-drive `elapsed` field directly --
    a standard, unambiguous derivation, not a new methodology."""
    import glob
    out = defaultdict(lambda: defaultdict(int))  # gameId -> team -> seconds
    pattern = str(REPO / f"data/raw/cfbd/season={year}/season_type=*/week=*/drives.json")
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
    is grouped into chronological bowl blocks between playoff rounds. A
    late bowl must never enter a snapshot preceding an earlier playoff game.

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

    postseason_entries = sorted((d, gid, key) for key, entries in postseason_by_round.items() for d, gid in entries)
    week_labels = {}
    last_round = None
    for d, gid, round_key in postseason_entries:
        if round_key != last_round:
            week_labels[len(clusters)] = "Bowl Season" if round_key == "bowl" else PLAYOFF_LABELS.get(round_key, round_key)
            clusters.append([])
            last_round = round_key
        clusters[-1].append((d, gid))

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
    return {str(r["gameId"]): r for r in rows}


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
        "havocAllowedNum": 0, "havocAllowedDen": 0, "havocForcedNum": 0, "havocForcedDen": 0,
        "gamesPlayed": 0,
        "slug": None, "teamId": None, "conf": None,
        **{f"{prefix}Num": 0 for prefix, _, _ in EPA_SUCCESS_SPLIT_FIELDS},
        **{f"{prefix}Den": 0 for prefix, _, _ in EPA_SUCCESS_SPLIT_FIELDS},
        **{f"{prefix}NumA": 0 for prefix, _, _ in EPA_SUCCESS_SPLIT_FIELDS},
        **{f"{prefix}DenA": 0 for prefix, _, _ in EPA_SUCCESS_SPLIT_FIELDS},
    }


def build_year(year, rating_model):
    rating_models.require_mode(rating_model)
    hierarchical = rating_model == "hierarchical_hfa"
    games = load_canonical_games(year)
    source = {str(g["id"]): g for path in (REPO / f"data/raw/cfbd/season={year}").glob("season_type=*/week=*/games.json") for g in json.loads(path.read_text())}
    completed = {gid for gid, g in source.items() if g.get("completed") is True}
    games = [r for r in games if str(r.get("gameId") or r.get("game_id")) in completed]
    from cfb_analytics.canonical.team_games import build_team_games
    from cfb_analytics.canonical.teams import build_season_teams
    source_games = list(source.values())
    games = build_team_games(games, source_games, build_season_teams(source_games, year))
    canonical_ids = {str(r.get("gameId") or r.get("game_id")) for r in games}
    if completed != canonical_ids:
        raise ValueError(f"Season {year}: {len(completed - canonical_ids)} completed source games lack canonical metrics")
    from cfb_analytics.validation.integrity import validate_team_games
    validate_team_games(games)
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
        return {}, {}, rating_models.rating_model_metadata(rating_model, season=year, cutoff=None, weeks=[])
    week_labels = {wk: label for wk, label in week_labels.items() if wk in weeks_present}

    # Garbage-time-filtered metric counts for the rating model ONLY. This is the
    # single opt-in caller of derived/games.py's exclude_garbage_time flag; the
    # unfiltered `games` rows above still feed every published Advanced field,
    # every `wk` raw counter and the legacy solver, exactly as before.
    filtered_metrics = metric_fields_by_team_game(load_canonical_plays(year), True) if hierarchical else {}
    rows_with_no_canonical_plays = 0

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
    # Parallel, never-substituted rating-model history: the same FBS-vs-FBS
    # team-game rows, carrying garbage-time-filtered EPA/Success/Explosiveness
    # counts instead of the unfiltered ones. Accumulated week by week exactly
    # like metric_history, so each site week's refit sees only games played
    # through that week -- no full-season information ever reaches an earlier
    # weekly snapshot.
    composite_history = []
    composite_fits = {}

    # SOS/SOR opponent strength for the ratings page: (opponent, won) for
    # every game a team has played, resolved at the END of each site-week
    # against that week's fully-updated ratings -- not frozen at whatever
    # the opponent looked like when the game was actually played. A week-3
    # win over a team that turns out to make the playoff should look like a
    # good win once we know that, not stay judged on a three-games-old
    # rating. This isn't lookahead: a week-14 snapshot already knows
    # everything through week 14, including how week-3 opponents turned
    # out. (The separate per-game iterative_ratings.py dataset used for
    # actual game predictions keeps its strict before-this-game cut --
    # that one really would leak if it looked ahead.)
    team_game_log = defaultdict(list)

    # Every FBS team's result against an FCS/lower-division opponent this
    # season, walk-forward like team_game_log above. Used only to calibrate
    # a generic FCS opponent strength for SOS/SOR below -- never enters the
    # core rating graph.
    fcs_games_log = []

    for wk in weeks_present:
        # Per-week-only (not cumulative) raw counts, so the client can sum an
        # arbitrary [start,end] range correctly. Model-based (schedule-adjusted)
        # values below are NOT summable this way -- they're single fitted
        # snapshots, so those stay cumulative/latest-only.
        wk_raw = defaultdict(lambda: defaultdict(float))

        for row in (r for r in games if r["_siteWeek"] == wk):
            if row.get("classification") != "fbs":
                # This is the FCS/lower-division opponent's OWN row for an
                # FBS-vs-FCS game -- present here because validate_team_games
                # above requires both symmetric sides of every game, but this
                # site only ever tracks FBS teams as first-class rows. The
                # FBS side's row for this same game (below) is what records
                # the result and feeds fcs_games_log/team_game_log.
                continue
            name = row["team"]
            is_fbs_opponent = row.get("opponent_classification") == "fbs"
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
            wr["explosiveNum"] += row.get("explosivePlays", 0) or 0
            wr["explosiveDen"] += row.get("explosiveEligiblePlays", 0) or 0
            wr["explosiveNumA"] += row.get("explosivePlaysAllowed", 0) or 0
            wr["explosiveDenA"] += row.get("explosiveEligiblePlaysAllowed", 0) or 0
            wr["yppNum"] += row.get("offensiveYards", 0) or 0
            wr["yppDen"] += row.get("offensivePlays", 0) or 0
            wr["yppNumA"] += row.get("defensiveYardsAllowed", 0) or 0
            wr["yppDenA"] += row.get("defensivePlays", 0) or 0
            wr["finNum"] += row.get("opportunityPoints", 0) or 0
            wr["finDen"] += row.get("resolvedPointOpportunities", 0) or 0
            wr["finNumA"] += row.get("opportunityPointsAllowed", 0) or 0
            wr["finDenA"] += row.get("resolvedPointOpportunitiesAllowed", 0) or 0
            if num(row.get("averageStartYardsToGoal")) and row.get("fieldPositionPossessions"):
                wr["fieldPosSum"] += row["averageStartYardsToGoal"] * row["fieldPositionPossessions"]
                wr["fieldPosCount"] += row["fieldPositionPossessions"]
            if num(row.get("averageStartYardsToGoalAllowed")) and row.get("fieldPositionPossessionsAllowed"):
                wr["fieldPosSumA"] += row["averageStartYardsToGoalAllowed"] * row["fieldPositionPossessionsAllowed"]
                wr["fieldPosCountA"] += row["fieldPositionPossessionsAllowed"]
            wr["dropbacks"] += row.get("dropbacks", 0) or 0
            wr["rushAttempts"] += row.get("rushAttempts", 0) or 0
            wr["dropbacksFaced"] += row.get("dropbacksFaced", 0) or 0
            wr["rushAttemptsFaced"] += row.get("rushAttemptsFaced", 0) or 0
            wr["offPlays"] += row.get("offensivePlays", 0) or 0
            wr["games"] += 1
            # An FBS-vs-FCS game only has one FBS-team row (see the
            # classification skip above), unlike FBS-vs-FBS which has two --
            # so summing every team's "games" and halving it (validate_site_
            # data.py's season game count) would undercount real games
            # unless FCS games are tracked separately and added back once,
            # not halved.
            wr["gamesVsNonFbs"] += int(not is_fbs_opponent)
            wr["offGames"] += int(bool(row.get("offensivePlays")))
            wr["havocAllowedNum"] += row.get("havocPlaysAllowed", 0) or 0
            wr["havocAllowedDen"] += row.get("havocEligiblePlays", 0) or 0
            wr["havocForcedNum"] += row.get("havocPlays", 0) or 0
            wr["havocForcedDen"] += row.get("havocEligiblePlaysFaced", 0) or 0
            _accumulate_epa_success_splits(wr, row)

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
            #
            # FBS-vs-FCS games are deliberately excluded from both fits: the
            # FCS opponent is skipped above and never has its own row here,
            # so it would enter these graphs as a single-observation phantom
            # node. fit_metric_ratings recenters every team's rating around
            # the mean of ALL graph nodes each iteration, so a handful of
            # 1-game FCS nodes would measurably shift every real FBS team's
            # offense/defense edges and CFF/SRS -- contamination, not signal.
            # Record-keeping and SOS/SOR still see these games below; only
            # the core opponent-adjusted rating graph stays a closed
            # FBS-vs-FBS universe.
            if is_fbs_opponent:
                metric_history.append(row)
                if hierarchical:
                    fields = filtered_metrics.get((game_id, name))
                    rows_with_no_canonical_plays += fields is None
                    composite_history.append(rating_models.composite_input_row(row, fields))
                if row.get("home_away") == "home":
                    srs_games_by_id[game_id] = {
                        "gameId": game_id,
                        "homeTeam": row["team"],
                        "awayTeam": row.get("opponent"),
                        "target_margin": (row.get("points_for") or 0) - (row.get("points_against") or 0),
                    }
            else:
                fcs_games_log.append({
                    "team": name,
                    "margin": (row.get("points_for") or 0) - (row.get("points_against") or 0),
                })

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
            # Locked Havoc v1: havocPlaysAllowed/havocEligiblePlays is a
            # TFL/sack/takeaway forced against THIS team's own offense --
            # an offensive liability, so it belongs in this offense-side
            # block even though the "A" (Allowed) name looks defense-ish
            # at a glance. havocPlays/havocEligiblePlaysFaced (this team's
            # defense forcing it against the opponent) is accumulated
            # below in the defensive block. See havoc_propagation_cli.py.
            acc["havocAllowedNum"] += row.get("havocPlaysAllowed", 0) or 0
            acc["havocAllowedDen"] += row.get("havocEligiblePlays", 0) or 0

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
            acc["havocForcedNum"] += row.get("havocPlays", 0) or 0
            acc["havocForcedDen"] += row.get("havocEligiblePlaysFaced", 0) or 0
            _accumulate_epa_success_splits(acc, row)

            # The Advanced page's SOS still reports a per-week raw rate (so
            # an arbitrary [start,end] range can be summed client-side) --
            # that one keeps the walk-forward, at-the-time opponent rating,
            # from iterative_ratings.py's own locked per-game dataset.
            iter_row = iter_by_game.get(str(row.get("gameId") or row.get("game_id")))
            prefix = side_prefix(iter_row, name)
            if prefix:
                opp_prefix = "away_" if prefix == "home_" else "home_"
                opp_srs = iter_row.get(opp_prefix[:-1] + "Srs")
                if num(opp_srs):
                    wr = wk_raw[name]
                    wr["opponentSrsSum"] += opp_srs
                    wr["opponentSrsCount"] += 1

            # The ratings page's cumulative SOS/SOR are resolved below, once
            # per site-week, against every game logged here.
            team_game_log[name].append((row.get("opponent"), bool(row.get("win", 0)), is_fbs_opponent))

        # League-wide re-solve using every game played through this site-week
        # (see the comment above the loop). One fit_srs + one fit_all_ratings
        # call per week, not per team -- every team's snapshot below reads
        # out of the same shared result.
        srs_fit = fit_srs(list(srs_games_by_id.values())) if srs_games_by_id else None
        srs_ratings = srs_fit["ratings"] if srs_fit else {}
        metric_ratings = fit_all_ratings(metric_history) if metric_history else {}

        # The published AdjOff/AdjDef/AdjNet refit, using only the games played
        # through this site week. z-scores are computed from THIS week's own
        # fits (see shadow_ratings.composite_from_fits), so no full-season
        # normalization leaks backward into a historical weekly snapshot. HFA is
        # estimated but never enters these neutral-field values.
        composite = None
        if hierarchical and composite_history:
            fitted = rating_models.fit_publication_composite(
                composite_history, season=year,
                cutoff={"siteWeek": wk, "scope": "through-site-week"},
            )
            composite, composite_fits = fitted["ratings"], fitted["fits"]

        # Same degeneracy guard as before, just evaluated once for the whole
        # week's fit instead of once per game: with fewer games played so far
        # than teams involved, the least-squares system is underdetermined
        # and can drive the residual to ~0 (a near-perfect in-sample fit with
        # no statistical meaning), which would make _ncdf collapse to a hard
        # 0/1 "certainty" for every game. Require the fit to be
        # over-determined before trusting its sigma for SOR at all.
        sigma = srs_fit.get("fitRmse") if srs_fit else None
        well_determined = bool(srs_fit) and srs_fit["games"] > srs_fit["teams"] and num(sigma) and sigma > 0

        fcs_baseline = calibrate_fcs_baseline(fcs_games_log, srs_ratings) if well_determined else None

        def metric(spec, side, team):
            v = metric_ratings.get(spec, {}).get(side, {}).get(team)
            return v if num(v) else None

        def metric_blend(spec, side, team, raw_rate, games_played):
            fit = metric_ratings.get(spec, {})
            return blend_edge(fit.get(side, {}).get(team), fit.get("leagueMean"), raw_rate, games_played)

        week_rows = []
        for name, acc in cum.items():
            if acc["gamesPlayed"] == 0:
                continue

            def rate(n, d):
                return round(n / d, 4) if d else None

            cff = srs_ratings.get(name)

            srs_sum = srs_count = 0.0
            sor_actual = sor_expected = sor_games = 0.0
            if well_determined:
                for opponent, won, is_fbs_opp in team_game_log[name]:
                    opp_srs = srs_ratings.get(opponent) if is_fbs_opp else fcs_baseline
                    if not num(opp_srs):
                        continue
                    srs_sum += opp_srs
                    srs_count += 1
                    sor_expected += _ncdf(-opp_srs / sigma)
                    sor_actual += 1 if won else 0
                    sor_games += 1
            # Only the blended/adjusted value is a snapshot field here -- the
            # matching raw rate is already summable client-side from wk[...]
            # (via _accumulate_epa_success_splits above), exactly like every
            # other raw/adjusted pair on this page, so it isn't duplicated.
            games_played = acc["gamesPlayed"]
            epa_success_fields = {}
            for out_prefix, spec_name, acc_prefix in EPA_SUCCESS_METRICS:
                raw_off = acc[f"{acc_prefix}Num"] / acc[f"{acc_prefix}Den"] if acc[f"{acc_prefix}Den"] else None
                raw_def = acc[f"{acc_prefix}NumA"] / acc[f"{acc_prefix}DenA"] if acc[f"{acc_prefix}DenA"] else None
                adj_off = metric_blend(spec_name, "offense", name, raw_off, games_played) if num(raw_off) else None
                adj_def = metric_blend(spec_name, "defense", name, raw_def, games_played) if num(raw_def) else None
                epa_success_fields[f"{out_prefix}Adj"] = round(adj_off, 4) if num(adj_off) else None
                epa_success_fields[f"{out_prefix}AdjAllowed"] = round(adj_def, 4) if num(adj_def) else None

            off_ypp, def_ypp = metric("YardsPerPossession", "offense", name), metric("YardsPerPossession", "defense", name)
            off_yppl, def_yppl = metric("YardsPerPlay", "offense", name), metric("YardsPerPlay", "defense", name)
            off_exp, def_exp = metric("Explosive", "offense", name), metric("Explosive", "defense", name)
            off_fin, def_fin = metric("Finishing", "offense", name), metric("Finishing", "defense", name)
            field_pos = metric("FieldPosition", "offense", name)
            # Swapped on purpose -- see the Havoc SPECS comment. The fitted
            # "offense" side is this team's defense forcing havoc; "defense"
            # is this team's offense avoiding it.
            def_havoc, off_havoc = metric("Havoc", "offense", name), metric("Havoc", "defense", name)

            # Published AdjOff/AdjDef/AdjNet. Both sides are rounded first and
            # AdjNet is then their exact sum, so the published contract
            # AdjNet == AdjOff + AdjDef holds exactly in the shipped numbers and
            # not merely before rounding.
            adj_off = composite["AdjOff"].get(name) if composite else None
            adj_def = composite["AdjDef"].get(name) if composite else None
            if num(adj_off) and num(adj_def):
                adj_off, adj_def = round(adj_off, 3), round(adj_def, 3)
                adj_net = round(adj_off + adj_def, 3)
            else:
                adj_off = adj_def = adj_net = None

            week_rows.append({
                "team": name, "slug": acc["slug"], "teamId": acc["teamId"], "conf": acc["conf"],
                "record": f"{acc['wins']}-{acc['losses']}", "wins": acc["wins"],
                "gamesPlayed": acc["gamesPlayed"],
                "cff": round(cff, 2) if num(cff) else None,
                "adjOff": adj_off, "adjDef": adj_def, "adjNet": adj_net,
                "sos": round(srs_sum / srs_count, 2) if srs_count else None,
                "sor": round(sor_actual - sor_expected, 2) if sor_games else None,
                "sorExpectedWins": round(sor_expected, 2) if sor_games else None,
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
                "offHavoc": round(off_havoc, 4) if num(off_havoc) else None,
                "def": round(def_ypp, 2) if num(def_ypp) else None,
                "defSuccess": rate(acc["successNumA"], acc["successDenA"]),
                "defYardsPerPlay": round(def_yppl, 3) if num(def_yppl) else None,
                "defPassSuccess": rate(acc["passSuccessNumA"], acc["passSuccessDenA"]),
                "defRushSuccess": rate(acc["rushSuccessNumA"], acc["rushSuccessDenA"]),
                "defPassRate": rate(acc["dropbacksFaced"], acc["dropbacksFaced"] + acc["rushAttemptsFaced"]),
                "defExp": round(def_exp, 2) if num(def_exp) else None,
                "defFin": round(def_fin, 2) if num(def_fin) else None,
                "defHavoc": round(def_havoc, 4) if num(def_havoc) else None,
                **epa_success_fields,
                # This week's own (non-cumulative) raw counts, for correct
                # client-side summing over an arbitrary [start,end] range.
                "wk": dict(wk_raw.get(name, {})),
            })

        out_by_week[wk] = week_rows  # wk is already a real chronological site-week (see build_site_week_map)

    model_metadata = rating_models.rating_model_metadata(
        rating_model, season=year,
        cutoff={"siteWeek": weeks_present[-1], "scope": "through-site-week"},
        weeks=weeks_present, fits=composite_fits or None,
        rows_with_no_canonical_plays=rows_with_no_canonical_plays,
        teams=len({r["team"] for r in composite_history}) if hierarchical else None,
    )
    return out_by_week, week_labels, model_metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("year", nargs="?", type=int, default=2025)
    parser.add_argument("--rating-model", required=True, choices=rating_models.MODEL_MODES)
    args = parser.parse_args()
    year = args.year
    weeks, week_labels, model_metadata = build_year(year, rating_model=args.rating_model)
    print("rating model:", model_metadata["modelId"])
    print("year", year, "weeks with data:", sorted(weeks.keys()))
    print("week labels:", week_labels)
    last_wk = max(weeks.keys())
    rows = [r for r in weeks[last_wk] if r["cff"] is not None]
    rows.sort(key=lambda r: -r["cff"])
    print(f"-- final week {last_wk} ({week_labels.get(last_wk, 'Week ' + str(last_wk))}) top 10 by CFF (SRS) --")
    for r in rows[:10]:
        print(f"{r['team']:20s} rec={r['record']:6s} cff={r['cff']:>7} sos={r['sos']:>7} off={r['off']} def={r['def']} gp={r['gamesPlayed']}")
    print(f"teams with a CFF value: {len(rows)} / {len(weeks[last_wk])} total teams with games")
