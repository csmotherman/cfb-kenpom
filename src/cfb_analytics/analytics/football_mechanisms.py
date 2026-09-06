"""Leakage-safe football mechanism research features from saved team-game rows.

This layer is intentionally separate from production metrics. It aggregates additive
team-game counts through the prior partition only, then exposes matchup-shaped
features tied to football mechanisms: drive quality, finishing, sustainability,
disruption, early downs, run/pass usage-matchup interactions, and possession scale.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.raw.audit import discover_partitions

FOOTBALL_MECHANISMS_VERSION = "football-mechanisms-v1-research"

TEAM_FIELDS = (
    "OffYardsPerPossession", "DefYardsPerPossession",
    "OffSuccessRate", "DefSuccessRateAllowed",
    "OffExplosiveRate", "DefExplosiveRateAllowed",
    "OffScoringOpportunityRate", "DefScoringOpportunityRateAllowed",
    "OffPointsPerOpportunity", "DefPointsPerOpportunityAllowed",
    "OffTouchdownOpportunityRate", "DefTouchdownOpportunityRateAllowed",
    "OffPlaysPerPossession", "DefPlaysPerPossession",
    "OffEarlyDownSuccessRate", "DefEarlyDownSuccessRateAllowed",
    "OffGiveawayRate", "DefTakeawayRate",
    "OffTflAllowedRate", "DefTflRate",
    "RushRate", "PassRate",
    "RushSuccessRate", "RushSuccessRateAllowed",
    "PassSuccessRate", "PassSuccessRateAllowed",
    "OffPossessionsPerGame", "DefPossessionsPerGame",
)

FAMILY_FEATURES = {
    "DRIVE_QUALITY": (
        "netYardsPerPossessionEdge", "netSuccessRateEdge", "netExplosiveRateEdge",
    ),
    "FINISHING": (
        "netScoringOpportunityRateEdge", "netPointsPerOpportunityEdge", "netTouchdownOpportunityRateEdge",
    ),
    "SUSTAINABILITY": ("netPlaysPerPossessionEdge",),
    "DISRUPTION": ("netTurnoverPressureEdge", "netTflPressureEdge"),
    "EARLY_DOWNS": ("netEarlyDownSuccessEdge",),
    "RUN_PASS_USAGE": ("netRushMatchupImpact", "netPassMatchupImpact"),
    "POSSESSION_SCALE": ("expectedPossessionsPerTeam",),
}
ALL_MATCHUP_FEATURES = tuple(x for family in FAMILY_FEATURES.values() for x in family)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _pk(st, w):
    s = str(st or "regular").lower()
    return (0 if s in {"regular", "regular_season"} else 1, int(w or 0))


def _load(root: Path, season: int, st: str, w: int):
    return json.loads((derived_game_partition_dir(root, season, st, w) / "team_games.json").read_text())


def _rate(n, d):
    return float(n) / float(d) if _num(n) and _num(d) and float(d) != 0 else None


def _avg(a, b):
    return (float(a) + float(b)) / 2.0 if _num(a) and _num(b) else None


def _sum_into(z, g):
    keys = (
        "validatedPossessions", "validatedDefensivePossessions", "offensivePlays", "defensivePlays",
        "offensiveYards", "defensiveYardsAllowed",
        "successfulPlays", "successEligiblePlays", "successfulPlaysAllowed", "successEligiblePlaysAllowed",
        "explosivePlays", "explosiveEligiblePlays", "explosivePlaysAllowed", "explosiveEligiblePlaysAllowed",
        "scoringOpportunities", "scoringOpportunitiesAllowed", "opportunityPoints", "opportunityPointsAllowed",
        "resolvedPointOpportunities", "resolvedPointOpportunitiesAllowed", "opportunityTouchdowns", "opportunityTouchdownsAllowed",
        "down1SuccessfulPlays", "down1SuccessEligiblePlays", "down2SuccessfulPlays", "down2SuccessEligiblePlays",
        "down1SuccessfulPlaysAllowed", "down1SuccessEligiblePlaysAllowed", "down2SuccessfulPlaysAllowed", "down2SuccessEligiblePlaysAllowed",
        "giveaways", "turnoverResolvedPossessions", "takeaways", "takeawayResolvedPossessions",
        "tacklesForLoss", "tacklesForLossAllowed",
        "rushSuccessEligiblePlays", "passSuccessEligiblePlays", "rushSuccessfulPlays", "passSuccessfulPlays",
        "rushSuccessEligiblePlaysAllowed", "passSuccessEligiblePlaysAllowed", "rushSuccessfulPlaysAllowed", "passSuccessfulPlaysAllowed",
    )
    for k in keys:
        v = g.get(k)
        if _num(v):
            z[k] += float(v)


def _state(z, games):
    if games <= 0:
        return {k: None for k in TEAM_FIELDS}
    early_n = z["down1SuccessfulPlays"] + z["down2SuccessfulPlays"]
    early_d = z["down1SuccessEligiblePlays"] + z["down2SuccessEligiblePlays"]
    early_an = z["down1SuccessfulPlaysAllowed"] + z["down2SuccessfulPlaysAllowed"]
    early_ad = z["down1SuccessEligiblePlaysAllowed"] + z["down2SuccessEligiblePlaysAllowed"]
    rush = z["rushSuccessEligiblePlays"]
    pas = z["passSuccessEligiblePlays"]
    return {
        "OffYardsPerPossession": _rate(z["offensiveYards"], z["validatedPossessions"]),
        "DefYardsPerPossession": _rate(z["defensiveYardsAllowed"], z["validatedDefensivePossessions"]),
        "OffSuccessRate": _rate(z["successfulPlays"], z["successEligiblePlays"]),
        "DefSuccessRateAllowed": _rate(z["successfulPlaysAllowed"], z["successEligiblePlaysAllowed"]),
        "OffExplosiveRate": _rate(z["explosivePlays"], z["explosiveEligiblePlays"]),
        "DefExplosiveRateAllowed": _rate(z["explosivePlaysAllowed"], z["explosiveEligiblePlaysAllowed"]),
        "OffScoringOpportunityRate": _rate(z["scoringOpportunities"], z["validatedPossessions"]),
        "DefScoringOpportunityRateAllowed": _rate(z["scoringOpportunitiesAllowed"], z["validatedDefensivePossessions"]),
        "OffPointsPerOpportunity": _rate(z["opportunityPoints"], z["resolvedPointOpportunities"]),
        "DefPointsPerOpportunityAllowed": _rate(z["opportunityPointsAllowed"], z["resolvedPointOpportunitiesAllowed"]),
        "OffTouchdownOpportunityRate": _rate(z["opportunityTouchdowns"], z["scoringOpportunities"]),
        "DefTouchdownOpportunityRateAllowed": _rate(z["opportunityTouchdownsAllowed"], z["scoringOpportunitiesAllowed"]),
        "OffPlaysPerPossession": _rate(z["offensivePlays"], z["validatedPossessions"]),
        "DefPlaysPerPossession": _rate(z["defensivePlays"], z["validatedDefensivePossessions"]),
        "OffEarlyDownSuccessRate": _rate(early_n, early_d),
        "DefEarlyDownSuccessRateAllowed": _rate(early_an, early_ad),
        "OffGiveawayRate": _rate(z["giveaways"], z["turnoverResolvedPossessions"]),
        "DefTakeawayRate": _rate(z["takeaways"], z["takeawayResolvedPossessions"]),
        "OffTflAllowedRate": _rate(z["tacklesForLossAllowed"], z["offensivePlays"]),
        "DefTflRate": _rate(z["tacklesForLoss"], z["defensivePlays"]),
        "RushRate": _rate(rush, rush + pas),
        "PassRate": _rate(pas, rush + pas),
        "RushSuccessRate": _rate(z["rushSuccessfulPlays"], z["rushSuccessEligiblePlays"]),
        "RushSuccessRateAllowed": _rate(z["rushSuccessfulPlaysAllowed"], z["rushSuccessEligiblePlaysAllowed"]),
        "PassSuccessRate": _rate(z["passSuccessfulPlays"], z["passSuccessEligiblePlays"]),
        "PassSuccessRateAllowed": _rate(z["passSuccessfulPlaysAllowed"], z["passSuccessEligiblePlaysAllowed"]),
        "OffPossessionsPerGame": _rate(z["validatedPossessions"], games),
        "DefPossessionsPerGame": _rate(z["validatedDefensivePossessions"], games),
    }


def build_pregame(raw_root: Path, processed_root: Path, season: int):
    totals = defaultdict(lambda: defaultdict(float))
    games = defaultdict(int)
    out = []
    for st, w in sorted(discover_partitions(raw_root, season), key=lambda x: _pk(*x)):
        current = _load(processed_root, season, st, w)
        for g in current:
            team = str(g.get("team"))
            row = {
                "season": season, "seasonType": st, "week": w,
                "gameId": str(g.get("gameId")), "team": g.get("team"), "opponent": g.get("opponent"),
                "gamesPlayedBefore": games[team], "footballMechanismsVersion": FOOTBALL_MECHANISMS_VERSION,
            }
            row.update(_state(totals[team], games[team]))
            out.append(row)
        for g in current:
            team = str(g.get("team"))
            _sum_into(totals[team], g)
            games[team] += 1
    return out


def build_matchups(snaps, season):
    by = defaultdict(list)
    for r in snaps:
        if r.get("season") == season:
            by[str(r.get("gameId"))].append(r)
    out = []
    for gid, pair in sorted(by.items()):
        if len(pair) != 2:
            continue
        a, b = pair
        row = {
            "season": season, "seasonType": a.get("seasonType"), "week": a.get("week"), "gameId": gid,
            "team1": a.get("team"), "team2": b.get("team"), "footballMechanismsVersion": FOOTBALL_MECHANISMS_VERSION,
        }
        for prefix, r in (("team1", a), ("team2", b)):
            row[f"{prefix}GamesPlayedBefore"] = r.get("gamesPlayedBefore", 0)
            for f in TEAM_FIELDS:
                row[f"{prefix}_{f}"] = r.get(f)
        out.append(row)
    return out


def orient_matchup(m, home, away):
    if {home, away} != {m.get("team1"), m.get("team2")}:
        return None
    hp = "team1" if home == m.get("team1") else "team2"
    ap = "team2" if hp == "team1" else "team1"
    h = lambda f: m.get(f"{hp}_{f}")
    a = lambda f: m.get(f"{ap}_{f}")

    def matchup_net(off_field, def_field):
        home_edge = float(h(off_field)) - float(a(def_field)) if _num(h(off_field)) and _num(a(def_field)) else None
        away_edge = float(a(off_field)) - float(h(def_field)) if _num(a(off_field)) and _num(h(def_field)) else None
        return float(home_edge) - float(away_edge) if _num(home_edge) and _num(away_edge) else None

    home_poss = _avg(h("OffPossessionsPerGame"), a("DefPossessionsPerGame"))
    away_poss = _avg(a("OffPossessionsPerGame"), h("DefPossessionsPerGame"))
    expected = _avg(home_poss, away_poss)

    home_to_pressure = _avg(a("OffGiveawayRate"), h("DefTakeawayRate"))
    away_to_pressure = _avg(h("OffGiveawayRate"), a("DefTakeawayRate"))
    home_tfl_pressure = _avg(a("OffTflAllowedRate"), h("DefTflRate"))
    away_tfl_pressure = _avg(h("OffTflAllowedRate"), a("DefTflRate"))

    rush_home = (float(h("RushRate")) * (float(h("RushSuccessRate")) - float(a("RushSuccessRateAllowed")))) if all(_num(x) for x in (h("RushRate"), h("RushSuccessRate"), a("RushSuccessRateAllowed"))) else None
    rush_away = (float(a("RushRate")) * (float(a("RushSuccessRate")) - float(h("RushSuccessRateAllowed")))) if all(_num(x) for x in (a("RushRate"), a("RushSuccessRate"), h("RushSuccessRateAllowed"))) else None
    pass_home = (float(h("PassRate")) * (float(h("PassSuccessRate")) - float(a("PassSuccessRateAllowed")))) if all(_num(x) for x in (h("PassRate"), h("PassSuccessRate"), a("PassSuccessRateAllowed"))) else None
    pass_away = (float(a("PassRate")) * (float(a("PassSuccessRate")) - float(h("PassSuccessRateAllowed")))) if all(_num(x) for x in (a("PassRate"), a("PassSuccessRate"), h("PassSuccessRateAllowed"))) else None

    return {
        "netYardsPerPossessionEdge": matchup_net("OffYardsPerPossession", "DefYardsPerPossession"),
        "netSuccessRateEdge": matchup_net("OffSuccessRate", "DefSuccessRateAllowed"),
        "netExplosiveRateEdge": matchup_net("OffExplosiveRate", "DefExplosiveRateAllowed"),
        "netScoringOpportunityRateEdge": matchup_net("OffScoringOpportunityRate", "DefScoringOpportunityRateAllowed"),
        "netPointsPerOpportunityEdge": matchup_net("OffPointsPerOpportunity", "DefPointsPerOpportunityAllowed"),
        "netTouchdownOpportunityRateEdge": matchup_net("OffTouchdownOpportunityRate", "DefTouchdownOpportunityRateAllowed"),
        "netPlaysPerPossessionEdge": matchup_net("OffPlaysPerPossession", "DefPlaysPerPossession"),
        "netEarlyDownSuccessEdge": matchup_net("OffEarlyDownSuccessRate", "DefEarlyDownSuccessRateAllowed"),
        "netTurnoverPressureEdge": float(home_to_pressure) - float(away_to_pressure) if _num(home_to_pressure) and _num(away_to_pressure) else None,
        "netTflPressureEdge": float(home_tfl_pressure) - float(away_tfl_pressure) if _num(home_tfl_pressure) and _num(away_tfl_pressure) else None,
        "netRushMatchupImpact": float(rush_home) - float(rush_away) if _num(rush_home) and _num(rush_away) else None,
        "netPassMatchupImpact": float(pass_home) - float(pass_away) if _num(pass_home) and _num(pass_away) else None,
        "expectedPossessionsPerTeam": expected,
    }


def audit(snaps, rows):
    checks = {
        "unique_team_game": len({(r["gameId"], r["team"]) for r in snaps}) == len(snaps),
        "zero_history_missing": all(r["gamesPlayedBefore"] != 0 or all(r[f] is None for f in TEAM_FIELDS) for r in snaps),
        "versions_present": all(r.get("footballMechanismsVersion") == FOOTBALL_MECHANISMS_VERSION for r in snaps + rows),
    }
    return {"status": "PASS" if all(checks.values()) else "REVIEW", "checks": checks}


def materialize(raw_root: Path, processed_root: Path, season: int):
    snaps = build_pregame(raw_root, processed_root, season)
    rows = build_matchups(snaps, season)
    res = audit(snaps, rows)
    root = processed_root / "derived" / "football_mechanisms" / f"season={season}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "pregame.json").write_text(json.dumps(snaps, ensure_ascii=False, separators=(",", ":")))
    (root / "matchups.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    return {"season": season, "status": res["status"], "snapshots": len(snaps), "matchups": len(rows), "checks": res["checks"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    a = p.parse_args()
    seasons = DEFAULT_SEASONS if a.all else ([a.season] if a.season else [])
    if not seasons:
        p.error("choose --season YYYY or --all")
    for season in seasons:
        r = materialize(a.raw_root, a.processed_root, season)
        print(f"FOOTBALL MECHANISMS {season}: {r['status']} snapshots={r['snapshots']:,} matchups={r['matchups']:,}")
        for k, v in r["checks"].items():
            if not v:
                print(f"  FAIL {k}")


if __name__ == "__main__":
    main()
