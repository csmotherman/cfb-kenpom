"""Season-level national-percentile offensive profile ("radar chart" data).

Computes, for every FBS team in a season, a set of advanced offensive metrics
and ranks/percentiles them against that same season's FBS population. Reuses
this repository's existing canonical play classification wherever one exists
(success rate, explosive play, dropback, ranking/percentile math) rather than
reinventing it, per repo convention. Only genuinely new metrics -- PPA-family
aggregates, Line Yards, Opportunity Rate, Stuff Rate -- are computed fresh
here, since no existing module in this repo produces them.

--------------------------------------------------------------------------
METRIC DEFINITIONS (exact formula + source for every value in the output)
--------------------------------------------------------------------------

All twelve metrics are OFFENSE-side (this is an offensive profile). Eight are
computed fresh from play-by-play in this module; four are read directly from
the repo's own locked `team_seasons.json` aggregate (no recomputation, exact
reuse).

Fresh (this module), eligibility base rule reused verbatim from
`analytics/success.py`'s `classify_success` gate -- `isScrimmagePlay and
isOffensivePlay and not hasStateTransitionModifier and not hasNoPlayContext`
-- so PPA-based metrics are excluded from exactly the same penalty/no-play/
turnover-text-flagged plays that success rate already excludes, keeping
methodology consistent across the site rather than inventing a second filter:

  ppa_play            -- CFBD's PPA (predicted points added), mean over all
                          eligible offensive scrimmage plays (rush+pass+sack).
                          Source: raw play `ppa` field (CFBD's own model).
                          Labeled PPA, not EPA -- CFBD's own term for this
                          field; this repo has never independently computed
                          EPA, so PPA is reported honestly as PPA.
  early_down_ppa_play -- same eligibility, restricted to down in {1, 2}.
  late_down_success_rate -- `classify_success()` (success.py, unmodified),
                          restricted to down in {3, 4}: 3rd/4th down gain
                          must be >=100% of distance to gain.
  rush_ppa_play       -- same eligibility, restricted to eventSubtype in
                          {RUSH, RUSH_TD} (designed/scrambled rush attempts;
                          CFBD's raw feed does not separately flag scrambles).
  stuff_rate          -- share of the same rush population with
                          analyticsYardsGained <= 0. Lower is better.
  line_yards          -- Football Outsiders Adjusted Line Yards banding
                          applied to the same rush population:
                            yards <  0        -> yards * 1.2
                            0 <= yards <= 4    -> yards * 1.0
                            4 <  yards <= 10   -> 4 + (yards-4) * 0.5
                            yards > 10         -> 4 + 6*0.5 = 7 (flat)
                          reported as the mean (line yards per carry).
  opportunity_rate    -- share of the same rush population reaching
                          analyticsYardsGained >= 4 (the standard threshold
                          for "the line did its job").
  pass_ppa_dropback   -- mean PPA over plays where
                          `classify_standard_dropback()` (dropback_v1_candidate.py,
                          unmodified) returns PASS_COMPLETION, PASS_INCOMPLETE,
                          PASS_TD, INTERCEPTION, or SACK.

Reused as-is from `data/processed/derived/seasons/season={year}/team_seasons.json`
(already locked, versioned team-season aggregates -- not recomputed):

  explosive_play_rate -- `explosivePlayRate` (explosiveness.py: rush gain
                          >=10 yards or pass gain >=20 yards is explosive).
  pass_success_rate   -- `passSuccessRate` (success.py, restricted to pass
                          plays by the existing seasons pipeline).
  havoc_rate_allowed  -- `havocRateAllowed` (havoc.py: share of this team's
                          offensive plays on which the opponent's defense
                          produced a non-sack TFL, a sack, a validated
                          interception, or a validated fumble lost). Lower is
                          better -- it is bad for the offense.
  yards_per_dropback  -- `netPassYardsPerDropback` (dropbacks.py's locked
                          `dropbacks-v1` definition; net passing yards divided
                          by the same standard-dropback population as above).

REJECTED metrics (asked for, not included -- see final report for why):
Average 3rd Down Distance and Rush/Pass Explosive Rate splits were left out
to keep the axis count at 12 per the brief's own "10-12, don't force 15"
guidance; the 12 above were chosen as the least redundant, most distinct
picture of offensive identity (efficiency, explosiveness, the run game, the
pass game, and how much the defense disrupts it).

--------------------------------------------------------------------------
NATIONAL COMPARISON POPULATION
--------------------------------------------------------------------------
Every season is ranked against ONLY that season's own FBS field (never mixed
across years), joined the same way `pipelines/publish.py` does it: read that
season's `teams.json`, keep only `classification == "fbs"`, inner-join onto
the per-team metrics row. Field size = number of FBS teams with at least one
qualifying rush or dropback (varies slightly by season, typically 130-136).

--------------------------------------------------------------------------
2020 HANDLING
--------------------------------------------------------------------------
This repo's canonical pipeline has never processed 2020 (COVID season,
documented as intentionally absent in docs/TEAM_PROFILES.md), and 2020 is
missing from `data/raw/cfbd/` (the exact raw source the canonical pipeline
reads and that every other season in this module reads from, via
`raw.audit.discover_partitions` + `canonical.materialize.canonical_partition_dir`).
2020 real play-by-play DOES exist, ingested separately, at
`data/raw/cfbd_facts/season=2020/...` (570 games, 14172 drives, confirmed
non-empty). For 2020 ONLY, this module reads that source directly and calls
`canonical.plays.normalize_play()` itself (the exact same enrichment every
other season already has baked in via the standard canonical pipeline) to
get `isScrimmagePlay`/`eventSubtype`/etc., then applies the same FBS-vs-FBS
filter manually via that season's `fbs_membership.json` (since `cfbd_facts`,
unlike `cfbd`, includes non-FBS games that need to be excluded by hand). No
shared/locked repository artifact is modified by this -- the 2020 profile is
computed in isolation, inside this module only.
2020 was an 8-11 game regular season with no clean non-conference schedule
for most teams (many conferences played conference-only slates); this is a
smaller, noisier per-team sample than a normal season and is labeled as such
in the published output (`"sampleSizeCaveat"` field).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.aggregations.rankings import Metric, add_rankings
from cfb_analytics.analytics.dropback_v1_candidate import VALID_CLASSES as DROPBACK_VALID_CLASSES
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback
from cfb_analytics.analytics.explosiveness import classify_explosive
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.tfl import classify_tfl, high_confidence_kneel_ids
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.canonical.plays import normalize_play
from cfb_analytics.raw.audit import discover_partitions

PROFILE_VERSION = "offensive-profile-v1"
RUSH_SUBTYPES = {"RUSH", "RUSH_TD"}
PASS_SUBTYPES = {"PASS_COMPLETION", "PASS_INCOMPLETE", "PASS_TD", "PASS_UNSPECIFIED"}
SACK_SUBTYPE = "SACK"
SCRIMMAGE_OFFENSE_SUBTYPES = RUSH_SUBTYPES | PASS_SUBTYPES | {SACK_SUBTYPE}

SEASONS_2020_ONLY_RAW = {2020}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _eligible_offense_play(play: dict[str, Any]) -> bool:
    """The exact gate reused from success.py's classify_success, minus the down restriction."""
    return bool(
        play.get("isScrimmagePlay")
        and play.get("isOffensivePlay")
        and not play.get("hasStateTransitionModifier")
        and not play.get("hasNoPlayContext")
    )


def _season_plays(raw_root: Path, processed_root: Path, season: int):
    """Yield normalized play dicts for every partition of a season.

    Non-2020 seasons: read the already-canonicalized plays.json this repo's
    own pipeline already produced (byte-identical to what every other
    analytics feature on the site uses).
    2020: normalize the separately-ingested cfbd_facts raw plays ourselves.
    """
    if season in SEASONS_2020_ONLY_RAW:
        season_dir = raw_root / "cfbd_facts" / f"season={season}"
        for type_dir in sorted(season_dir.glob("season_type=*")):
            season_type = type_dir.name.split("=", 1)[1]
            for week_dir in sorted(type_dir.glob("week=*")):
                path = week_dir / "plays.json"
                if not path.exists():
                    continue
                payload = json.loads(path.read_text())
                rows = payload.get("payload", payload) if isinstance(payload, dict) else payload
                for row in rows:
                    yield normalize_play(row)
        return

    for season_type, week in discover_partitions(raw_root, season):
        path = canonical_partition_dir(processed_root, season, season_type, week) / "plays.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text()):
            yield row


def _fbs_teams(canonical_root: Path, season: int) -> set[str]:
    path = canonical_root / f"season={season}" / "fbs_membership.json"
    rows = json.loads(path.read_text())
    return {row["team"] for row in rows if row.get("classification") == "fbs"}


def _line_yards(yards: float) -> float:
    if yards < 0:
        return yards * 1.2
    if yards <= 4:
        return yards * 1.0
    if yards <= 10:
        return 4.0 + (yards - 4) * 0.5
    return 7.0


def compute_national_offensive_metrics(raw_root: Path, processed_root: Path, canonical_root: Path, season: int) -> dict[str, dict[str, Any]]:
    """Per-team raw offensive metrics for every FBS team in a season, from play-by-play."""
    fbs_teams = _fbs_teams(canonical_root, season)

    acc: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "ppa_sum": 0.0, "ppa_n": 0,
        "early_ppa_sum": 0.0, "early_ppa_n": 0,
        "late_success": 0, "late_n": 0,
        "rush_ppa_sum": 0.0, "rush_ppa_n": 0,
        "rush_stuffs": 0, "rush_n": 0,
        "line_yards_sum": 0.0,
        "opportunity_hits": 0,
        "pass_ppa_sum": 0.0, "pass_ppa_n": 0,
    })

    for play in _season_plays(raw_root, processed_root, season):
        offense = play.get("offense")
        defense = play.get("defense")
        if offense not in fbs_teams or defense not in fbs_teams:
            continue

        subtype = play.get("eventSubtype")
        ppa = play.get("ppa")
        down = play.get("down")
        yards = play.get("analyticsYardsGained")

        eligible = _eligible_offense_play(play)

        if eligible and subtype in SCRIMMAGE_OFFENSE_SUBTYPES and _num(ppa):
            row = acc[offense]
            row["ppa_sum"] += ppa
            row["ppa_n"] += 1
            if down in (1, 2):
                row["early_ppa_sum"] += ppa
                row["early_ppa_n"] += 1

        if eligible and down in (3, 4):
            result = classify_success(play)
            if result is not None:
                row = acc[offense]
                row["late_n"] += 1
                row["late_success"] += int(result)

        if eligible and subtype in RUSH_SUBTYPES and _num(yards):
            row = acc[offense]
            row["rush_n"] += 1
            row["rush_stuffs"] += int(yards <= 0)
            row["line_yards_sum"] += _line_yards(float(yards))
            row["opportunity_hits"] += int(yards >= 4)
            if _num(ppa):
                row["rush_ppa_sum"] += ppa
                row["rush_ppa_n"] += 1

        dropback_cls = classify_standard_dropback(play)
        if dropback_cls in DROPBACK_VALID_CLASSES and _num(ppa):
            row = acc[offense]
            row["pass_ppa_sum"] += ppa
            row["pass_ppa_n"] += 1

    out: dict[str, dict[str, Any]] = {}
    for team, row in acc.items():
        out[team] = {
            "ppa_play": row["ppa_sum"] / row["ppa_n"] if row["ppa_n"] else None,
            "early_down_ppa_play": row["early_ppa_sum"] / row["early_ppa_n"] if row["early_ppa_n"] else None,
            "late_down_success_rate": row["late_success"] / row["late_n"] if row["late_n"] else None,
            "rush_ppa_play": row["rush_ppa_sum"] / row["rush_ppa_n"] if row["rush_ppa_n"] else None,
            "stuff_rate": row["rush_stuffs"] / row["rush_n"] if row["rush_n"] else None,
            "line_yards": row["line_yards_sum"] / row["rush_n"] if row["rush_n"] else None,
            "opportunity_rate": row["opportunity_hits"] / row["rush_n"] if row["rush_n"] else None,
            "pass_ppa_dropback": row["pass_ppa_sum"] / row["pass_ppa_n"] if row["pass_ppa_n"] else None,
            "sample": {
                "offensivePlays": row["ppa_n"], "rushAttempts": row["rush_n"], "dropbacks": row["pass_ppa_n"],
            },
        }
    return out


def _season_2020_reused_metrics(raw_root: Path, canonical_root: Path) -> dict[str, dict[str, Any]]:
    """2020-only fallback for the four metrics normally reused from team_seasons.json,
    which was never built for 2020. Computed directly from the same normalized plays
    using this repo's own play-level classifiers (classify_success, classify_explosive,
    classify_tfl), NOT the drive-validated havoc.py pipeline -- that pipeline also
    needs drive-level `isPossessionDrive`/`driveValidationStatus` fields that only
    exist after a canonicalization step this repo has never built for 2020's drives.
    Havoc here is therefore a play-level approximation: non-sack TFL, sack, or a
    play flagged `isTurnover` on an eligible offensive snap -- everything except the
    extra "confirmed via drive continuity" refinement the rest of the site has.
    """
    fbs_teams = _fbs_teams(canonical_root, 2020)
    plays = list(_season_plays(raw_root, Path("data/processed"), 2020))
    kneel_ids = high_confidence_kneel_ids(plays)

    acc: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "explosive_eligible": 0, "explosive_hits": 0,
        "pass_eligible": 0, "pass_success": 0,
        "offense_snaps": 0, "havoc_hits": 0,
        "dropback_yards": 0.0, "dropbacks": 0,
    })
    for play in plays:
        offense, defense = play.get("offense"), play.get("defense")
        if offense not in fbs_teams or defense not in fbs_teams:
            continue
        row = acc[offense]
        eligible = _eligible_offense_play(play)
        ex = classify_explosive(play)

        if eligible:
            row["offense_snaps"] += 1
            if play.get("eventSubtype") == "SACK" or classify_tfl(play, kneel_ids) or play.get("isTurnover"):
                row["havoc_hits"] += 1

        success = classify_success(play)
        if success is not None and play.get("eventSubtype") in PASS_SUBTYPES:
            row["pass_eligible"] += 1
            row["pass_success"] += int(success)

        if ex is not None:
            row["explosive_eligible"] += 1
            row["explosive_hits"] += int(ex)

        cls = classify_standard_dropback(play)
        if cls in DROPBACK_VALID_CLASSES:
            yards = play.get("analyticsYardsGained")
            row["dropbacks"] += 1
            if _num(yards):
                row["dropback_yards"] += yards

    out = {}
    for team, row in acc.items():
        # keys match team_seasons.json's own camelCase naming so build_offensive_profile
        # can merge either source through the same lookup, regardless of season.
        out[team] = {
            "explosivePlayRate": row["explosive_hits"] / row["explosive_eligible"] if row["explosive_eligible"] else None,
            "passSuccessRate": row["pass_success"] / row["pass_eligible"] if row["pass_eligible"] else None,
            "havocRateAllowed": row["havoc_hits"] / row["offense_snaps"] if row["offense_snaps"] else None,
            "netPassYardsPerDropback": row["dropback_yards"] / row["dropbacks"] if row["dropbacks"] else None,
        }
    return out


def compute_national_unit_metrics(raw_root: Path, processed_root: Path, canonical_root: Path, season: int) -> dict[str, dict[str, dict[str, Any]]]:
    """Per-team OFFENSE and DEFENSE raw metrics for every FBS team, in one play pass.

    Mirrors compute_national_offensive_metrics's PPA/stuff/line-yards/opportunity
    work but credits both sides of every play at once: a stuffed run counts
    against the ball-carrier's OFFENSE accumulator and, on the same play, in
    favor of the tackling team's DEFENSE accumulator. Adds one new raw metric
    neither this module nor team_seasons.json had before: average 3rd down
    distance (offense: distance faced: lower is better; defense: distance
    forced onto the opponent -- higher is better).

    This is a second, separate full-season play scan from
    compute_national_offensive_metrics (used only by the radar) rather than a
    shared one, so the already-tested radar path is never touched by this
    unit-detail-page work.
    """
    fbs_teams = _fbs_teams(canonical_root, season)

    def _blank():
        return {
            "ppa_sum": 0.0, "ppa_n": 0,
            "early_ppa_sum": 0.0, "early_ppa_n": 0,
            "late_success": 0, "late_n": 0,
            "rush_ppa_sum": 0.0, "rush_ppa_n": 0,
            "rush_stuffs": 0, "rush_n": 0,
            "line_yards_sum": 0.0,
            "opportunity_hits": 0,
            "pass_ppa_sum": 0.0, "pass_ppa_n": 0,
            "third_down_distance_sum": 0.0, "third_down_distance_n": 0,
        }

    off_acc: dict[str, dict[str, Any]] = defaultdict(_blank)
    def_acc: dict[str, dict[str, Any]] = defaultdict(_blank)

    for play in _season_plays(raw_root, processed_root, season):
        offense = play.get("offense")
        defense = play.get("defense")
        if offense not in fbs_teams or defense not in fbs_teams:
            continue

        subtype = play.get("eventSubtype")
        ppa = play.get("ppa")
        down = play.get("down")
        distance = play.get("distance")
        yards = play.get("analyticsYardsGained")
        eligible = _eligible_offense_play(play)
        o, d = off_acc[offense], def_acc[defense]

        if eligible and subtype in SCRIMMAGE_OFFENSE_SUBTYPES and _num(ppa):
            o["ppa_sum"] += ppa; o["ppa_n"] += 1
            d["ppa_sum"] += ppa; d["ppa_n"] += 1
            if down in (1, 2):
                o["early_ppa_sum"] += ppa; o["early_ppa_n"] += 1
                d["early_ppa_sum"] += ppa; d["early_ppa_n"] += 1

        if eligible and down == 3 and _num(distance) and distance > 0:
            o["third_down_distance_sum"] += distance; o["third_down_distance_n"] += 1
            d["third_down_distance_sum"] += distance; d["third_down_distance_n"] += 1

        if eligible and down in (3, 4):
            result = classify_success(play)
            if result is not None:
                o["late_n"] += 1; o["late_success"] += int(result)
                d["late_n"] += 1; d["late_success"] += int(result)

        if eligible and subtype in RUSH_SUBTYPES and _num(yards):
            for row in (o, d):
                row["rush_n"] += 1
                row["rush_stuffs"] += int(yards <= 0)
                row["line_yards_sum"] += _line_yards(float(yards))
                row["opportunity_hits"] += int(yards >= 4)
            if _num(ppa):
                o["rush_ppa_sum"] += ppa; o["rush_ppa_n"] += 1
                d["rush_ppa_sum"] += ppa; d["rush_ppa_n"] += 1

        dropback_cls = classify_standard_dropback(play)
        if dropback_cls in DROPBACK_VALID_CLASSES and _num(ppa):
            o["pass_ppa_sum"] += ppa; o["pass_ppa_n"] += 1
            d["pass_ppa_sum"] += ppa; d["pass_ppa_n"] += 1

    def _finalize(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "ppa_play": row["ppa_sum"] / row["ppa_n"] if row["ppa_n"] else None,
            "early_down_ppa_play": row["early_ppa_sum"] / row["early_ppa_n"] if row["early_ppa_n"] else None,
            "late_down_success_rate": row["late_success"] / row["late_n"] if row["late_n"] else None,
            "rush_ppa_play": row["rush_ppa_sum"] / row["rush_ppa_n"] if row["rush_ppa_n"] else None,
            "stuff_rate": row["rush_stuffs"] / row["rush_n"] if row["rush_n"] else None,
            "line_yards": row["line_yards_sum"] / row["rush_n"] if row["rush_n"] else None,
            "opportunity_rate": row["opportunity_hits"] / row["rush_n"] if row["rush_n"] else None,
            "pass_ppa_dropback": row["pass_ppa_sum"] / row["pass_ppa_n"] if row["pass_ppa_n"] else None,
            "third_down_distance": row["third_down_distance_sum"] / row["third_down_distance_n"] if row["third_down_distance_n"] else None,
        }

    teams = set(off_acc) | set(def_acc)
    return {team: {"offense": _finalize(off_acc[team]), "defense": _finalize(def_acc[team])} for team in teams}


PROFILE_METRICS = (
    Metric("ppa_play", "PPA / Play", "ppa", True, "efficiency", "offense"),
    Metric("early_down_ppa_play", "Early Down PPA / Play", "ppa", True, "efficiency", "offense"),
    Metric("late_down_success_rate", "Late Down Success Rate", "rate", True, "efficiency", "offense"),
    Metric("rush_ppa_play", "Rush PPA / Play", "ppa", True, "rushing", "offense"),
    Metric("stuff_rate", "Stuff Rate Allowed", "rate", False, "rushing", "offense"),
    Metric("line_yards", "Line Yards", "yards", True, "rushing", "offense"),
    Metric("opportunity_rate", "Opportunity Rate", "rate", True, "rushing", "offense"),
    Metric("explosive_play_rate", "Explosive Play Rate", "rate", True, "explosiveness", "offense"),
    Metric("pass_ppa_dropback", "Pass PPA / Dropback", "ppa", True, "passing", "offense"),
    Metric("yards_per_dropback", "Yards / Dropback", "yards", True, "passing", "offense"),
    Metric("pass_success_rate", "Pass Success Rate", "rate", True, "passing", "offense"),
    Metric("havoc_rate_allowed", "Havoc Rate Allowed", "rate", False, "havoc", "offense"),
)

METRIC_UNITS = {m.name: m.unit for m in PROFILE_METRICS}


def build_offensive_profile(raw_root: Path, processed_root: Path, canonical_root: Path, published_root: Path, season: int, team: str = "Michigan") -> dict[str, Any]:
    fresh = compute_national_offensive_metrics(raw_root, processed_root, canonical_root, season)

    team_seasons_path = processed_root / "derived" / "seasons" / f"season={season}" / "team_seasons.json"
    if team_seasons_path.exists():
        team_seasons = {row["team"]: row for row in json.loads(team_seasons_path.read_text())}
    else:
        team_seasons = _season_2020_reused_metrics(raw_root, canonical_root)

    fbs_teams = _fbs_teams(canonical_root, season)

    rows: list[dict[str, Any]] = []
    for name in sorted(fbs_teams):
        f = fresh.get(name)
        ts = team_seasons.get(name)
        if f is None or ts is None:
            continue
        row = {
            "team": name,
            "ppa_play": f["ppa_play"],
            "early_down_ppa_play": f["early_down_ppa_play"],
            "late_down_success_rate": f["late_down_success_rate"],
            "rush_ppa_play": f["rush_ppa_play"],
            "stuff_rate": f["stuff_rate"],
            "line_yards": f["line_yards"],
            "opportunity_rate": f["opportunity_rate"],
            "pass_ppa_dropback": f["pass_ppa_dropback"],
            "explosive_play_rate": ts.get("explosivePlayRate"),
            "yards_per_dropback": ts.get("netPassYardsPerDropback"),
            "pass_success_rate": ts.get("passSuccessRate"),
            "havoc_rate_allowed": ts.get("havocRateAllowed"),
            "_sample": f["sample"],
        }
        rows.append(row)

    ranked = add_rankings(rows, metrics=PROFILE_METRICS, prefix="")
    field_size = len(rows)

    target = next((r for r in ranked if r["team"] == team), None)
    if target is None:
        raise ValueError(f"{team} not found in {season} FBS field (field_size={field_size})")

    metrics_out = []
    for metric in PROFILE_METRICS:
        value = target.get(metric.name)
        rank = target.get(f"{metric.name}_rank")
        pct01 = target.get(f"{metric.name}_percentile")
        metrics_out.append({
            "key": metric.name,
            "label": metric.display_name,
            "value": round(value, 4) if isinstance(value, float) else value,
            "unit": metric.unit,
            "rank": rank,
            "fieldSize": field_size,
            "percentile": round(pct01 * 100, 1) if isinstance(pct01, float) else None,
            "higherIsBetter": metric.higher_is_better,
        })

    return {
        "version": PROFILE_VERSION,
        "season": season,
        "team": team,
        "fieldSize": field_size,
        "sample": target["_sample"],
        "sampleSizeCaveat": (
            "2020 was an abbreviated, largely conference-only COVID season (8-13 games per team); "
            "treat this profile as a smaller, noisier sample than a normal season."
        ) if season in SEASONS_2020_ONLY_RAW else None,
        "metrics": metrics_out,
    }


def publish(raw_root: Path, processed_root: Path, canonical_root: Path, published_root: Path, seasons: list[int], team: str = "Michigan") -> list[dict[str, Any]]:
    manifest = []
    for season in seasons:
        profile = build_offensive_profile(raw_root, processed_root, canonical_root, published_root, season, team)
        target = published_root / str(season) / "analytics" / "offensive-profile.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
        manifest.append({"season": season, "fieldSize": profile["fieldSize"], "path": str(target)})
        print(f"season {season}: field_size={profile['fieldSize']} -> {target}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--seasons", type=int, nargs="+", default=None, help="Explicit season list; overrides --start-year/--end-year")
    parser.add_argument("--team", type=str, default="Michigan")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--canonical-root", type=Path, default=Path("data/canonical"))
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    args = parser.parse_args()
    seasons = args.seasons if args.seasons is not None else list(range(args.start_year, args.end_year + 1))
    publish(args.raw_root, args.processed_root, args.canonical_root, args.published_root, seasons, args.team)


if __name__ == "__main__":
    main()
