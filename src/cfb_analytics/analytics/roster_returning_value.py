from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdClient

DEFAULT_SEASON = 2026

OFFENSE_PPA_POSITIONS = {"QB", "RB", "HB", "FB", "WR", "TE"}

# Research-grade defensive production composite. CFBD has no play-level PPA
# attribution for defenders, so this stands in for "defensive PPA" using
# box-score counting stats. Weights favor disruptive/coverage plays over
# raw tackle volume. Not audited to this repo's production-lock standard.
DEFENSIVE_VALUE_WEIGHTS = {
    "TOT": 0.10,
    "TFL": 1.50,
    "SACKS": 1.00,
    "PD": 1.25,
    "QB HUR": 0.50,
    "INT": 3.00,
    "TD": 3.00,
}
DEFINITION_VERSION = "roster-returning-value-v1"
DEFENSIVE_VALUE_VERSION = "defensive-value-score-v1"

# Standard 11-personnel offense (1 QB, 1 RB, 1 TE, 3 WR, 5 OL) and a base 4-3
# defense (4 DL, 3 LB, 4 DB). CFBD has no player-level production for OL, so
# those five slots are always reported with no data rather than being filled.
OFFENSE_SLOT_GROUPS: list[tuple[str, set[str], int]] = [
    ("QB", {"QB"}, 1),
    ("RB", {"RB", "HB", "FB"}, 1),
    ("WR", {"WR"}, 3),
    ("TE", {"TE"}, 1),
]
OFFENSE_OL_SLOTS = 5
DEFENSE_SLOT_GROUPS: list[tuple[str, set[str], int]] = [
    ("DL", {"DL", "DE", "DT", "NT", "EDGE"}, 4),
    ("LB", {"LB"}, 3),
    ("DB", {"DB", "CB", "S"}, 4),
]


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _roster_name(row: dict[str, Any]) -> str:
    first = str(row.get("firstName") or "").strip()
    last = str(row.get("lastName") or "").strip()
    combined = f"{first} {last}".strip()
    return combined or str(row.get("name") or "").strip()


def fetch_fbs_teams(client: CfbdClient, season: int) -> dict[str, str]:
    """Return {normalized team name -> canonical team name} for current FBS members."""
    teams = client.get_json("/teams/fbs", {"year": season}).payload
    return {_norm(row["school"]): row["school"] for row in teams if row.get("school")}


def build_current_roster(
    roster_rows: list[dict[str, Any]], fbs_lookup: dict[str, str]
) -> tuple[dict[str, set[str]], dict[tuple[str, str], str]]:
    """Returns (team -> {normalized names on roster}, (team, normalized name) -> roster position)."""
    names_by_team: dict[str, set[str]] = {}
    position_by_key: dict[tuple[str, str], str] = {}
    for row in roster_rows:
        team = row.get("team")
        if not team or _norm(team) not in fbs_lookup:
            continue
        canonical = fbs_lookup[_norm(team)]
        name = _norm(_roster_name(row))
        if not name:
            continue
        names_by_team.setdefault(canonical, set()).add(name)
        position = str(row.get("position") or "").upper().strip()
        if position and position != "?":
            position_by_key[(canonical, name)] = position
    return names_by_team, position_by_key


def build_offense_prior_production(
    ppa_rows: list[dict[str, Any]], fbs_lookup: dict[str, str]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_team: dict[str, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in ppa_rows:
        team = row.get("team")
        if not team or _norm(team) not in fbs_lookup:
            continue
        position = str(row.get("position") or "").upper().strip()
        if position not in OFFENSE_PPA_POSITIONS:
            continue
        block = row.get("totalPPA") or {}
        total = _finite(block.get("all")) if isinstance(block, dict) else None
        if total is None:
            continue
        canonical = fbs_lookup[_norm(team)]
        display_name = str(row.get("name") or "").strip()
        norm_name = _norm(display_name)
        if not norm_name:
            continue
        entry = {"normName": norm_name, "name": display_name, "position": position, "value": total, "team": canonical}
        by_team.setdefault(canonical, []).append(entry)
        by_name.setdefault(norm_name, []).append(entry)
    return by_team, by_name


def build_defense_prior_production(
    defensive_rows: list[dict[str, Any]],
    interception_rows: list[dict[str, Any]],
    fbs_lookup: dict[str, str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    scores: dict[tuple[str, str], dict[str, Any]] = {}

    def _accumulate(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            team = row.get("team")
            stat_type = row.get("statType")
            weight = DEFENSIVE_VALUE_WEIGHTS.get(stat_type)
            if not team or weight is None or _norm(team) not in fbs_lookup:
                continue
            value = _finite(row.get("stat"))
            if value is None:
                continue
            display_name = str(row.get("player") or "").strip()
            norm_name = _norm(display_name)
            if not norm_name:
                continue
            canonical = fbs_lookup[_norm(team)]
            key = (canonical, norm_name)
            record = scores.setdefault(
                key,
                {"normName": norm_name, "name": display_name, "position": str(row.get("position") or "").upper().strip(), "value": 0.0, "team": canonical},
            )
            record["value"] += weight * value

    _accumulate(defensive_rows)
    _accumulate(interception_rows)

    by_team: dict[str, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for entry in scores.values():
        by_team.setdefault(entry["team"], []).append(entry)
        by_name.setdefault(entry["normName"], []).append(entry)
    return by_team, by_name


def _dedupe_portal(portal_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in portal_rows:
        destination = str(row.get("destination") or "").strip()
        origin = str(row.get("origin") or "").strip()
        if not destination or not origin or _norm(destination) == _norm(origin):
            continue
        first = str(row.get("firstName") or "").strip()
        last = str(row.get("lastName") or "").strip()
        key = (_norm(f"{first} {last}"), _norm(origin), _norm(destination))
        if not key[0]:
            continue
        existing = latest.get(key)
        if existing is None or str(row.get("transferDate") or "") >= str(existing.get("transferDate") or ""):
            latest[key] = row
    return list(latest.values())


def compute_transfer_added_value(
    portal_rows: list[dict[str, Any]],
    fbs_lookup: dict[str, str],
    offense_by_name: dict[str, list[dict[str, Any]]],
    defense_by_name: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, float], dict[str, float], list[dict[str, Any]]]:
    offense_added: dict[str, float] = {}
    defense_added: dict[str, float] = {}
    matched: list[dict[str, Any]] = []

    for row in _dedupe_portal(portal_rows):
        destination = str(row.get("destination") or "").strip()
        origin = str(row.get("origin") or "").strip()
        if _norm(destination) not in fbs_lookup:
            continue
        dest_canonical = fbs_lookup[_norm(destination)]
        origin_norm = _norm(origin)
        first = str(row.get("firstName") or "").strip()
        last = str(row.get("lastName") or "").strip()
        name = _norm(f"{first} {last}")
        display_name = f"{first} {last}".strip()
        portal_position = str(row.get("position") or "").upper().strip()

        offense_match = next((e for e in offense_by_name.get(name, []) if _norm(e["team"]) == origin_norm), None)
        defense_match = next((e for e in defense_by_name.get(name, []) if _norm(e["team"]) == origin_norm), None)

        if offense_match is not None:
            offense_added[dest_canonical] = offense_added.get(dest_canonical, 0.0) + offense_match["value"]
        if defense_match is not None:
            defense_added[dest_canonical] = defense_added.get(dest_canonical, 0.0) + defense_match["value"]
        if offense_match is not None or defense_match is not None:
            matched.append(
                {
                    "name": display_name,
                    "position": portal_position,
                    "origin": origin,
                    "destination": dest_canonical,
                    "priorOffensePPA": offense_match["value"] if offense_match else None,
                    "priorOffensePosition": offense_match["position"] if offense_match else None,
                    "priorDefenseScore": defense_match["value"] if defense_match else None,
                    "priorDefensePosition": defense_match["position"] if defense_match else None,
                }
            )

    return offense_added, defense_added, matched


def _zscores(values: dict[str, float]) -> dict[str, float]:
    nums = list(values.values())
    if len(nums) < 2:
        return {team: 0.0 for team in values}
    mean = statistics.fmean(nums)
    stdev = statistics.pstdev(nums)
    if stdev < 1e-9:
        return {team: 0.0 for team in values}
    return {team: (value - mean) / stdev for team, value in values.items()}


def _resolve_position(
    canonical: str, norm_name: str, roster_positions: dict[tuple[str, str], str], fallback: str
) -> str:
    return roster_positions.get((canonical, norm_name)) or fallback


def _build_held_pool(
    canonical: str,
    *,
    returning_entries: list[dict[str, Any]],
    names_now: set[str],
    roster_positions: dict[tuple[str, str], str],
    transfer_rows: list[dict[str, Any]],
    value_key: str,
    position_key: str,
) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    for entry in returning_entries:
        if entry["normName"] not in names_now:
            continue
        position = _resolve_position(canonical, entry["normName"], roster_positions, entry["position"])
        pool.append({"name": entry["name"], "position": position, "value": entry["value"], "source": "returning", "origin": None})
    for row in transfer_rows:
        if row["destination"] != canonical or row[value_key] is None:
            continue
        norm_name = _norm(row["name"])
        position = _resolve_position(canonical, norm_name, roster_positions, row[position_key] or row["position"])
        pool.append(
            {"name": row["name"], "position": position, "value": row[value_key], "source": "transfer", "origin": row["origin"]}
        )
    return pool


def _select_slots(pool: list[dict[str, Any]], slot_groups: list[tuple[str, set[str], int]]) -> list[dict[str, Any]]:
    used_ids: set[int] = set()
    result: list[dict[str, Any]] = []
    for label, valid_positions, count in slot_groups:
        candidates = sorted(
            (p for p in pool if p["position"] in valid_positions and id(p) not in used_ids),
            key=lambda p: -p["value"],
        )
        chosen = candidates[:count]
        for i, p in enumerate(chosen, start=1):
            used_ids.add(id(p))
            result.append(
                {
                    "slot": f"{label}{i}" if count > 1 else label,
                    "name": p["name"],
                    "position": p["position"],
                    "value": round(p["value"], 2),
                    "source": p["source"],
                    "origin": p["origin"],
                }
            )
        for i in range(len(chosen) + 1, count + 1):
            result.append(
                {
                    "slot": f"{label}{i}" if count > 1 else label,
                    "name": None,
                    "position": None,
                    "value": None,
                    "source": None,
                    "origin": None,
                    "note": "no eligible player with production data at this position",
                }
            )
    return result


def build_top11_offense(
    canonical: str,
    offense_by_team: dict[str, list[dict[str, Any]]],
    names_now: set[str],
    roster_positions: dict[tuple[str, str], str],
    transfer_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pool = _build_held_pool(
        canonical,
        returning_entries=offense_by_team.get(canonical, []),
        names_now=names_now,
        roster_positions=roster_positions,
        transfer_rows=transfer_matches,
        value_key="priorOffensePPA",
        position_key="priorOffensePosition",
    )
    lineup = _select_slots(pool, OFFENSE_SLOT_GROUPS)
    for i in range(1, OFFENSE_OL_SLOTS + 1):
        lineup.append(
            {
                "slot": f"OL{i}",
                "name": None,
                "position": None,
                "value": None,
                "source": None,
                "origin": None,
                "note": "CFBD has no player-level production data for offensive linemen",
            }
        )
    return lineup


def build_top11_defense(
    canonical: str,
    defense_by_team: dict[str, list[dict[str, Any]]],
    names_now: set[str],
    roster_positions: dict[tuple[str, str], str],
    transfer_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pool = _build_held_pool(
        canonical,
        returning_entries=defense_by_team.get(canonical, []),
        names_now=names_now,
        roster_positions=roster_positions,
        transfer_rows=transfer_matches,
        value_key="priorDefenseScore",
        position_key="priorDefensePosition",
    )
    return _select_slots(pool, DEFENSE_SLOT_GROUPS)


def build_report(
    *,
    season: int,
    fbs_lookup: dict[str, str],
    roster_names: dict[str, set[str]],
    roster_positions: dict[tuple[str, str], str],
    offense_by_team: dict[str, list[dict[str, Any]]],
    defense_by_team: dict[str, list[dict[str, Any]]],
    offense_by_name: dict[str, list[dict[str, Any]]],
    defense_by_name: dict[str, list[dict[str, Any]]],
    portal_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    offense_added, defense_added, matched_transfers = compute_transfer_added_value(
        portal_rows, fbs_lookup, offense_by_name, defense_by_name
    )

    offense_held: dict[str, float] = {}
    defense_held: dict[str, float] = {}
    teams: dict[str, dict[str, Any]] = {}

    for canonical in sorted(fbs_lookup.values()):
        names_now = roster_names.get(canonical, set())

        off_players = offense_by_team.get(canonical, [])
        off_prior_total = sum(e["value"] for e in off_players)
        off_returning = sum(e["value"] for e in off_players if e["normName"] in names_now)
        off_transfer = offense_added.get(canonical, 0.0)
        off_held = off_returning + off_transfer

        def_players = defense_by_team.get(canonical, [])
        def_prior_total = sum(e["value"] for e in def_players)
        def_returning = sum(e["value"] for e in def_players if e["normName"] in names_now)
        def_transfer = defense_added.get(canonical, 0.0)
        def_held = def_returning + def_transfer

        offense_held[canonical] = off_held
        defense_held[canonical] = def_held

        teams[canonical] = {
            "team": canonical,
            "offense": {
                "priorSeasonTotalPPA": off_prior_total,
                "returningPPA": off_returning,
                "returningShare": (off_returning / off_prior_total) if abs(off_prior_total) > 1e-9 else None,
                "transferAddedPPA": off_transfer,
                "totalHeldPPA": off_held,
            },
            "defense": {
                "priorSeasonTotalScore": def_prior_total,
                "returningScore": def_returning,
                "returningShare": (def_returning / def_prior_total) if abs(def_prior_total) > 1e-9 else None,
                "transferAddedScore": def_transfer,
                "totalHeldScore": def_held,
            },
            "topOffense11": build_top11_offense(canonical, offense_by_team, names_now, roster_positions, matched_transfers),
            "topDefense11": build_top11_defense(canonical, defense_by_team, names_now, roster_positions, matched_transfers),
        }

    offense_z = _zscores(offense_held)
    defense_z = _zscores(defense_held)
    for canonical, record in teams.items():
        oz = offense_z.get(canonical, 0.0)
        dz = defense_z.get(canonical, 0.0)
        record["offenseZ"] = oz
        record["defenseZ"] = dz
        record["combinedZ"] = oz + dz

    ranked = sorted(teams.values(), key=lambda r: -r["combinedZ"])
    for i, record in enumerate(ranked, start=1):
        record["combinedRank"] = i

    offense_ranked = sorted(teams.values(), key=lambda r: -r["offenseZ"])
    for i, record in enumerate(offense_ranked, start=1):
        record["offenseRank"] = i

    defense_ranked = sorted(teams.values(), key=lambda r: -r["defenseZ"])
    for i, record in enumerate(defense_ranked, start=1):
        record["defenseRank"] = i

    return {
        "definitionVersion": DEFINITION_VERSION,
        "defensiveValueVersion": DEFENSIVE_VALUE_VERSION,
        "defensiveValueWeights": DEFENSIVE_VALUE_WEIGHTS,
        "season": season,
        "productionSeason": season - 1,
        "fbsTeamCount": len(fbs_lookup),
        "matchedTransfers": len(matched_transfers),
        "transferMatches": sorted(
            matched_transfers, key=lambda r: -((r["priorOffensePPA"] or 0) + (r["priorDefenseScore"] or 0))
        ),
        "teams": sorted(teams.values(), key=lambda r: r["combinedRank"]),
        "notes": [
            "Offense value is player-attributed PPA from /ppa/players/season for QB/RB/FB/HB/WR/TE, matched by name to the current roster.",
            "Defense has no CFBD play-level PPA, so defenseValue is a weighted box-score composite (see defensiveValueWeights); it is a research proxy, not an audited production metric.",
            "Transfer-added value is the incoming player's prior-season value at their origin school (matched by name+origin), added on top of organic returners; it is not itself 'returning' production.",
            "combinedZ standardizes offense totalHeldPPA and defense totalHeldScore separately across FBS (z-scores) before summing, since the two are on different native scales.",
            "topOffense11/topDefense11 fill a standard 11-personnel offense (1 QB, 1 RB, 3 WR, 1 TE, 5 OL) and base 4-3 defense (4 DL, 3 LB, 4 DB) with the highest-value eligible held player per slot; a slot with no eligible player, and all 5 OL slots (CFBD has no lineman production data), report null with a note instead of being filled.",
            "Name-based matching (no stable player id available from the transfer portal endpoint) will miss players whose name formatting differs across endpoints, and JUCO/non-FBS transfers have no prior-production match by design.",
        ],
    }


def _print_report(report: dict[str, Any], top: int, lineup_teams: int) -> None:
    print("=" * 100)
    print(f"FBS {report['season']} RETURNING + TRANSFER-ADDED VALUE (offense PPA + defensive composite)")
    print("=" * 100)
    print(f"Production season:   {report['productionSeason']}")
    print(f"FBS teams:           {report['fbsTeamCount']}")
    print(f"Matched transfers:   {report['matchedTransfers']} (prior-production found at origin school)")

    print(f"\nTOP {top} — COMBINED (offense Z + defense Z)")
    print("-" * 100)
    print(f"{'#':<4}{'TEAM':<28}{'OFF HELD PPA':>14}{'OFF SHARE':>11}{'DEF HELD':>12}{'DEF SHARE':>11}{'COMBINED Z':>12}")
    for row in report["teams"][:top]:
        off = row["offense"]
        de = row["defense"]
        off_share = "n/a" if off["returningShare"] is None else f"{100*off['returningShare']:.0f}%"
        def_share = "n/a" if de["returningShare"] is None else f"{100*de['returningShare']:.0f}%"
        print(
            f"{row['combinedRank']:<4}{row['team']:<28}{off['totalHeldPPA']:>14.1f}{off_share:>11}"
            f"{de['totalHeldScore']:>12.1f}{def_share:>11}{row['combinedZ']:>12.2f}"
        )

    print(f"\nTOP-11 LINEUPS — TOP {lineup_teams} COMBINED TEAMS")
    print("-" * 100)
    for row in report["teams"][:lineup_teams]:
        print(f"\n{row['team']} — OFFENSE (11 personnel)")
        for slot in row["topOffense11"]:
            if slot["name"]:
                print(f"  {slot['slot']:<5} {slot['name']:<24} {slot['position']:<4} value={slot['value']:>7.1f}  ({slot['source']}{' from ' + slot['origin'] if slot['origin'] else ''})")
            else:
                print(f"  {slot['slot']:<5} -- {slot['note']}")
        print(f"{row['team']} — DEFENSE (base 4-3)")
        for slot in row["topDefense11"]:
            if slot["name"]:
                print(f"  {slot['slot']:<5} {slot['name']:<24} {slot['position']:<4} value={slot['value']:>7.1f}  ({slot['source']}{' from ' + slot['origin'] if slot['origin'] else ''})")
            else:
                print(f"  {slot['slot']:<5} -- {slot['note']}")


def _write_csv(path: Path, teams: list[dict[str, Any]]) -> None:
    fieldnames = [
        "combinedRank", "team", "combinedZ",
        "offenseRank", "offenseZ", "offense_priorSeasonTotalPPA", "offense_returningPPA",
        "offense_returningShare", "offense_transferAddedPPA", "offense_totalHeldPPA",
        "defenseRank", "defenseZ", "defense_priorSeasonTotalScore", "defense_returningScore",
        "defense_returningShare", "defense_transferAddedScore", "defense_totalHeldScore",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in teams:
            writer.writerow(
                {
                    "combinedRank": row["combinedRank"],
                    "team": row["team"],
                    "combinedZ": row["combinedZ"],
                    "offenseRank": row["offenseRank"],
                    "offenseZ": row["offenseZ"],
                    "offense_priorSeasonTotalPPA": row["offense"]["priorSeasonTotalPPA"],
                    "offense_returningPPA": row["offense"]["returningPPA"],
                    "offense_returningShare": row["offense"]["returningShare"],
                    "offense_transferAddedPPA": row["offense"]["transferAddedPPA"],
                    "offense_totalHeldPPA": row["offense"]["totalHeldPPA"],
                    "defenseRank": row["defenseRank"],
                    "defenseZ": row["defenseZ"],
                    "defense_priorSeasonTotalScore": row["defense"]["priorSeasonTotalScore"],
                    "defense_returningScore": row["defense"]["returningScore"],
                    "defense_returningShare": row["defense"]["returningShare"],
                    "defense_transferAddedScore": row["defense"]["transferAddedScore"],
                    "defense_totalHeldScore": row["defense"]["totalHeldScore"],
                }
            )


def _write_lineup_csv(path: Path, teams: list[dict[str, Any]]) -> None:
    fieldnames = ["team", "side", "slot", "name", "position", "value", "source", "origin"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in teams:
            for side, key in (("offense", "topOffense11"), ("defense", "topDefense11")):
                for slot in row[key]:
                    writer.writerow(
                        {
                            "team": row["team"],
                            "side": side,
                            "slot": slot["slot"],
                            "name": slot["name"],
                            "position": slot["position"],
                            "value": slot["value"],
                            "source": slot["source"],
                            "origin": slot["origin"],
                        }
                    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank FBS rosters by returning + transfer-added value on offense (PPA) and defense (box-score composite), with position-valid top-11 lineups."
    )
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--lineup-teams", type=int, default=5, help="How many top combined teams to print full lineups for.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/research/roster-returning-value"))
    args = parser.parse_args()

    prior_season = args.season - 1
    with CfbdClient() as client:
        fbs_lookup = fetch_fbs_teams(client, args.season)
        roster_rows = client.get_json("/roster", {"year": args.season}).payload
        ppa_rows = client.get_json("/ppa/players/season", {"year": prior_season}).payload
        defensive_rows = client.get_json("/stats/player/season", {"year": prior_season, "category": "defensive"}).payload
        interception_rows = client.get_json(
            "/stats/player/season", {"year": prior_season, "category": "interceptions"}
        ).payload
        portal_rows = client.get_json("/player/portal", {"year": args.season}).payload

    roster_names, roster_positions = build_current_roster(roster_rows, fbs_lookup)
    offense_by_team, offense_by_name = build_offense_prior_production(ppa_rows, fbs_lookup)
    defense_by_team, defense_by_name = build_defense_prior_production(defensive_rows, interception_rows, fbs_lookup)

    report = build_report(
        season=args.season,
        fbs_lookup=fbs_lookup,
        roster_names=roster_names,
        roster_positions=roster_positions,
        offense_by_team=offense_by_team,
        defense_by_team=defense_by_team,
        offense_by_name=offense_by_name,
        defense_by_name=defense_by_name,
        portal_rows=portal_rows,
    )
    _print_report(report, args.top, args.lineup_teams)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{args.season}-fbs-roster-returning-value.json"
    csv_path = args.output_dir / f"{args.season}-fbs-roster-returning-value.csv"
    lineup_csv_path = args.output_dir / f"{args.season}-fbs-roster-returning-value-top11.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, report["teams"])
    _write_lineup_csv(lineup_csv_path, report["teams"])
    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote CSV:  {csv_path}")
    print(f"Wrote CSV:  {lineup_csv_path}")


if __name__ == "__main__":
    main()
