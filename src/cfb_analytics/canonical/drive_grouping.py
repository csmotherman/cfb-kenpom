"""Pure drive-grouping logic, shared by `derived/drives.py` (which persists
drive records to disk) and `canonical/drive_ownership.py` (which needs the
same fully-resolved provisional drive groupings in-memory, before any file
exists to read). Lives in `canonical/` rather than `derived/` specifically
so `canonical/materialize.py` can depend on it without a circular import
back through `derived/drives.py` (which itself depends on
`canonical/materialize.py` for `canonical_partition_dir`).

No behavior here changed by extracting it -- see `derived/drives.py`'s
module docstring for what this logic does and why.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from cfb_analytics.raw.sequence import _candidate_sort_key

DRIVE_SCHEMA_VERSION = "drive-v4"


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _mode(values: list[Any]) -> Any:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    counts = Counter(clean)
    best = counts.most_common(1)[0][1]
    winners = {v for v, n in counts.items() if n == best}
    return next(v for v in clean if v in winners)


def _ownership_rows(rows):
    return [r for r in rows if r.get("isOffensivePlay") is True and r.get("isScrimmagePlay") is True and not r.get("hasNoPlayContext", False)]


def _fallback_offensive_rows(rows):
    return [r for r in rows if r.get("isOffensivePlay") is True and not r.get("hasNoPlayContext", False) and r.get("offense") is not None and r.get("defense") is not None]


def _non_possession_profile(rows: list[dict[str, Any]]) -> str | None:
    if any(r.get("isOffensivePlay") is True for r in rows):
        return None
    cats = Counter(str(r.get("eventCategory") or "UNKNOWN") for r in rows)
    if rows and all(r.get("isAdministrative") for r in rows):
        return "ADMINISTRATIVE_ONLY"
    if rows and all(r.get("isSpecialTeams") for r in rows):
        return "SPECIAL_TEAMS_ONLY"
    if cats.get("TURNOVER", 0):
        return "TURNOVER_RETURN_OR_NON_OFFENSE"
    if cats.get("SCORING", 0) or cats.get("CONVERSION", 0):
        return "SCORING_OR_CONVERSION_ONLY"
    return "NO_OFFENSIVE_PLAY"


def derive_drive(game_id, drive_id, rows, season, season_type, week):
    ordered = sorted(rows, key=_candidate_sort_key)
    first, last = ordered[0], ordered[-1]
    drive_numbers = [r.get("driveNumber") for r in ordered if r.get("driveNumber") is not None]
    ownership = _ownership_rows(ordered)
    fallback = _fallback_offensive_rows(ordered)
    po = [r.get("offense") for r in ownership if r.get("offense") is not None]
    pd = [r.get("defense") for r in ownership if r.get("defense") is not None]
    fo = [r.get("offense") for r in fallback if r.get("offense") is not None]
    fd = [r.get("defense") for r in fallback if r.get("defense") is not None]
    offense = _mode(po) if po else _mode(fo)
    defense = _mode(pd) if pd else _mode(fd)
    source = "clean_offensive_scrimmage_plays" if po and pd else ("other_offensive_plays" if fo and fd else "unresolved")
    nonpos = _non_possession_profile(ordered)
    offensive = [r for r in ordered if r.get("isOffensivePlay") is True and not r.get("hasNoPlayContext", False)]
    scrimmage = [r for r in ordered if r.get("isScrimmagePlay") is True and not r.get("hasNoPlayContext", False)]
    yards = [r.get("analyticsYardsGained") for r in offensive if _num(r.get("analyticsYardsGained"))]
    issues = []
    if po and len(set(po)) > 1: issues.append("MULTIPLE_OWNERSHIP_OFFENSES")
    if pd and len(set(pd)) > 1: issues.append("MULTIPLE_OWNERSHIP_DEFENSES")
    if not po and fo and len(set(fo)) > 1: issues.append("MULTIPLE_FALLBACK_OFFENSES")
    if not pd and fd and len(set(fd)) > 1: issues.append("MULTIPLE_FALLBACK_DEFENSES")
    if len(set(drive_numbers)) > 1: issues.append("MULTIPLE_DRIVE_NUMBERS")
    if offense is None and nonpos is None: issues.append("MISSING_OWNERSHIP_OFFENSE")
    if defense is None and nonpos is None: issues.append("MISSING_OWNERSHIP_DEFENSE")
    return {
        "season": season, "seasonType": season_type, "week": week, "gameId": game_id, "driveId": drive_id, "driveNumber": _mode(drive_numbers),
        "offense": offense, "defense": defense, "isPossessionDrive": nonpos is None, "nonPossessionProfile": nonpos,
        "ownershipEvidencePlayCount": len(ownership), "fallbackOwnershipEvidencePlayCount": len(fallback), "playCount": len(ordered),
        "offensivePlayCount": len(offensive), "scrimmagePlayCount": len(scrimmage), "analyticsYardsGained": sum(yards),
        "correctedPlayCount": sum(bool(r.get("analyticsYardsWasCorrected")) for r in ordered),
        "startPeriod": first.get("period"), "startClock": first.get("clock"), "startDown": first.get("down"), "startDistance": first.get("distance"), "startYardsToGoal": first.get("yardsToGoal"),
        "endPeriod": last.get("period"), "endClock": last.get("clock"), "endDown": last.get("down"), "endDistance": last.get("distance"), "endYardsToGoal": last.get("yardsToGoal"),
        "startOffenseScore": first.get("offenseScore"), "startDefenseScore": first.get("defenseScore"), "endOffenseScoreObserved": last.get("offenseScore"), "endDefenseScoreObserved": last.get("defenseScore"),
        "firstPlayId": first.get("id"), "lastPlayId": last.get("id"), "driveSchemaVersion": DRIVE_SCHEMA_VERSION, "driveOwnershipSource": source,
        "driveValidationStatus": "PASS" if not issues else "REVIEW", "driveValidationIssues": issues,
    }


def _game_teams(game_drives):
    teams = {d.get("offense") for d in game_drives if d.get("offense")} | {d.get("defense") for d in game_drives if d.get("defense")}
    teams.discard(None)
    return teams


def _resolve_game_ownership(drives):
    by_game = defaultdict(list)
    for d in drives:
        by_game[str(d["gameId"])].append(d)
    for game in by_game.values():
        game.sort(key=lambda d: (d.get("driveNumber") if isinstance(d.get("driveNumber"), (int, float)) else 10**9, str(d.get("driveId"))))
        teams = _game_teams(game)
        if len(teams) != 2:
            continue
        a, b = sorted(teams)
        # Event-only groups are not possessions and intentionally have no owner.
        for d in game:
            if not d.get("isPossessionDrive"):
                d["offense"] = None; d["defense"] = None; d["driveOwnershipSource"] = "non_possession_event_group"; d["driveValidationIssues"] = []; d["driveValidationStatus"] = "PASS"
        # Resolve missing possession ownership from adjacent possession drives only.
        possessions = [d for d in game if d.get("isPossessionDrive")]
        for i, d in enumerate(possessions):
            if d.get("offense") is not None and d.get("defense") is not None:
                continue
            candidates = []
            for neighbor in (possessions[i - 1] if i > 0 else None, possessions[i + 1] if i + 1 < len(possessions) else None):
                if neighbor and neighbor.get("offense") in teams:
                    candidates.append(b if neighbor["offense"] == a else a)
            if candidates and len(set(candidates)) == 1:
                off = candidates[0]; d["offense"] = off; d["defense"] = b if off == a else a; d["driveOwnershipSource"] = "neighbor_possession_inference"
                d["driveValidationIssues"] = [x for x in d["driveValidationIssues"] if x not in {"MISSING_OWNERSHIP_OFFENSE", "MISSING_OWNERSHIP_DEFENSE"}]
        # Conflicts: accept only a strict >=2-vote majority whose opponent is the other game team.
        for d in possessions:
            if "MULTIPLE_OWNERSHIP_OFFENSES" not in d.get("driveValidationIssues", []):
                continue
            # Stored mode already reflects the majority candidate; require at least 3 evidence plays and infer confidence from count dominance later in materialization.
            if d.get("ownershipEvidencePlayCount", 0) < 3 or d.get("offense") not in teams:
                continue
            off = d["offense"]; deff = b if off == a else a
            # Surrounding resolved possessions may not contradict candidate ownership.
            idx = possessions.index(d); neighbors = [x for x in (possessions[idx - 1] if idx > 0 else None, possessions[idx + 1] if idx + 1 < len(possessions) else None) if x]
            if any(n.get("offense") == off for n in neighbors if n.get("offense") is not None):
                continue
            d["defense"] = deff; d["driveOwnershipSource"] = "scrimmage_majority_with_game_context"
            d["driveValidationIssues"] = [x for x in d["driveValidationIssues"] if x not in {"MULTIPLE_OWNERSHIP_OFFENSES", "MULTIPLE_OWNERSHIP_DEFENSES"}]
        for d in game:
            d["driveValidationStatus"] = "PASS" if not d.get("driveValidationIssues") else "REVIEW"


def derive_partition_drives(canonical_rows, season, season_type, week):
    groups = defaultdict(list)
    missing = 0
    for r in canonical_rows:
        if r.get("gameId") is None or r.get("driveId") is None:
            missing += 1
            continue
        groups[(str(r["gameId"]), str(r["driveId"]))].append(r)
    drives = [derive_drive(g, d, rows, season, season_type, week) for (g, d), rows in groups.items()]
    _resolve_game_ownership(drives)
    drives.sort(key=lambda x: (x["gameId"], x["driveNumber"] if isinstance(x["driveNumber"], (int, float)) else 10**9, x["driveId"]))
    return drives, {"plays_without_drive_id": missing, "plays_with_drive_id": len(canonical_rows) - missing}
