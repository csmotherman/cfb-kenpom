"""Leakage-safe opponent-adjusted points-per-drive research model.

Drive points use the repository's locked Drive Efficiency v1 foundation:
validated possession drives plus Finishing Drives v2 ``possession_outcome``
adjudication. Pregame ratings use strictly prior partitions. Postgame residuals
are target-side diagnostics and must never be used as pregame features.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.finishing_drives import possession_outcome
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.derived.pregame import _pk
from cfb_analytics.raw.audit import discover_partitions

DRIVE_PPD_VERSION = "drive-ppd-v1-research"
DRIVE_PPD_POINTS_FOUNDATION = "drive-efficiency-v1+finishing-drives-v2"
DEFAULT_SHRINKAGE_POSSESSIONS = 25.0


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def adjudicated_drive_points(
    drive: dict[str, Any], drive_plays: list[dict[str, Any]], game_plays: list[dict[str, Any]]
) -> float | None:
    """Return locked-adjudication offensive points for one possession."""
    if not (
        drive.get("isPossessionDrive") is True
        and drive.get("driveValidationStatus") == "PASS"
        and drive.get("offense")
    ):
        return None
    result = possession_outcome(drive, drive_plays, game_plays)
    return float(result["points"]) if result.get("pointsResolved") else None


def build_team_game_drive_rows(
    drives: list[dict[str, Any]], plays: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Aggregate locked-adjudication possession points into team-game PPD."""
    by_drive: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in plays:
        gid = str(p.get("gameId"))
        by_drive[(gid, str(p.get("driveId")))].append(p)
        by_game[gid].append(p)

    valid: Counter[tuple[int, str, int, str, str, str]] = Counter()
    resolved: dict[tuple[int, str, int, str, str, str], list[float]] = defaultdict(list)
    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus") == "PASS"):
            continue
        offense, defense = d.get("offense"), d.get("defense")
        season, week, gid = int(d.get("season") or 0), int(d.get("week") or 0), str(d.get("gameId"))
        if not season or not gid or not offense or not defense:
            continue
        key = (season, str(d.get("seasonType") or "regular"), week, gid, str(offense), str(defense))
        valid[key] += 1
        points = adjudicated_drive_points(d, by_drive[(gid, str(d.get("driveId")))], by_game[gid])
        if points is not None:
            resolved[key].append(points)

    out = []
    for key in sorted(valid):
        season, season_type, week, gid, offense, defense = key
        values = resolved.get(key, [])
        points = sum(values)
        n = len(values)
        out.append({
            "season": season,
            "seasonType": season_type,
            "week": week,
            "gameId": gid,
            "team": offense,
            "opponent": defense,
            "validatedPossessions": valid[key],
            "resolvedPointPossessions": n,
            "unresolvedPointPossessions": valid[key] - n,
            "offensiveDrivePoints": points,
            "offensivePPD": points / n if n else None,
            "drivePpdPointsFoundation": DRIVE_PPD_POINTS_FOUNDATION,
            "drivePpdVersion": DRIVE_PPD_VERSION,
        })
    return out


def fit_ppd_ratings(
    rows: list[dict[str, Any]],
    shrinkage_possessions: float = DEFAULT_SHRINKAGE_POSSESSIONS,
    damping: float = 1.0,
    tolerance: float = 1e-8,
    max_iterations: int = 2000,
) -> dict[str, Any]:
    """Fit ``PPD = mean + offense - defense`` weighted by resolved drives."""
    if shrinkage_possessions < 0 or not 0 < damping <= 1 or tolerance <= 0 or max_iterations < 1:
        raise ValueError("invalid drive PPD fit settings")
    obs = []
    for r in rows:
        t, o, y, w = r.get("team"), r.get("opponent"), r.get("offensivePPD"), r.get("resolvedPointPossessions")
        if t and o and t != o and _num(y) and _num(w) and float(w) > 0:
            obs.append((str(t), str(o), float(y), float(w)))
    if not obs:
        return {"leagueMean": None, "offense": {}, "defense": {}, "iterations": 0, "converged": True,
                "maxDelta": 0.0, "observations": 0, "possessions": 0.0, "version": DRIVE_PPD_VERSION}

    total_w = sum(w for _, _, _, w in obs)
    mean = sum(y * w for _, _, y, w in obs) / total_w
    teams = sorted({t for t, _, _, _ in obs} | {o for _, o, _, _ in obs})
    offense = {t: 0.0 for t in teams}
    defense = {t: 0.0 for t in teams}
    by_off, by_def = defaultdict(list), defaultdict(list)
    for t, o, y, w in obs:
        by_off[t].append((o, y, w)); by_def[o].append((t, y, w))

    converged, max_delta = False, float("inf")
    for iteration in range(1, max_iterations + 1):
        no = dict(offense)
        for t, games in by_off.items():
            w = sum(x[2] for x in games)
            target = sum(wi * (y - mean + defense[o]) for o, y, wi in games) / (w + shrinkage_possessions)
            no[t] = offense[t] + damping * (target - offense[t])
        nd = dict(defense)
        for t, games in by_def.items():
            w = sum(x[2] for x in games)
            target = sum(wi * (mean + no[o] - y) for o, y, wi in games) / (w + shrinkage_possessions)
            nd[t] = defense[t] + damping * (target - defense[t])
        max_delta = max(max(abs(no[t] - offense[t]) for t in teams), max(abs(nd[t] - defense[t]) for t in teams))
        offense, defense = no, nd
        if max_delta <= tolerance:
            converged = True; break

    off_mean = sum(offense.values()) / len(offense)
    def_mean = sum(defense.values()) / len(defense)
    offense = {t: v - off_mean for t, v in offense.items()}
    defense = {t: v - def_mean for t, v in defense.items()}
    mean += off_mean - def_mean
    return {"leagueMean": mean, "offense": offense, "defense": defense, "iterations": iteration,
            "converged": converged, "maxDelta": max_delta, "observations": len(obs),
            "possessions": total_w, "version": DRIVE_PPD_VERSION}


def expected_ppd(fitted: dict[str, Any], offense: str, defense: str) -> float | None:
    m = fitted.get("leagueMean"); o = fitted.get("offense", {}).get(str(offense)); d = fitted.get("defense", {}).get(str(defense))
    return float(m) + float(o) - float(d) if all(_num(x) for x in (m, o, d)) else None


def _raw_prior_ppd(history: list[dict[str, Any]], team: str, defensive: bool = False):
    rows = [r for r in history if (r.get("opponent") if defensive else r.get("team")) == team]
    pts = sum(float(r.get("offensiveDrivePoints") or 0) for r in rows)
    poss = sum(int(r.get("resolvedPointPossessions") or 0) for r in rows)
    games = len({str(r.get("gameId")) for r in rows})
    return (pts / poss if poss else None, games, float(poss))


def build_pregame_ppd_snapshots(rows: list[dict[str, Any]], season: int, **fit_kwargs: Any):
    parts = defaultdict(list)
    for r in rows:
        if r.get("season") == season: parts[_pk(r)].append(r)
    history, out = [], []
    for key in sorted(parts):
        fitted = fit_ppd_ratings(history, **fit_kwargs); mean = fitted.get("leagueMean")
        for g in parts[key]:
            team = str(g.get("team")); off = fitted.get("offense", {}).get(team); deff = fitted.get("defense", {}).get(team)
            raw_o, games_o, poss_o = _raw_prior_ppd(history, team, False)
            raw_d, games_d, poss_d = _raw_prior_ppd(history, team, True)
            out.append({
                "season": season, "seasonType": g.get("seasonType"), "week": g.get("week"), "gameId": g.get("gameId"),
                "team": team, "opponent": g.get("opponent"), "gamesPlayedBefore": games_o,
                "defensiveGamesPlayedBefore": games_d, "resolvedOffensivePossessionsBefore": poss_o,
                "resolvedDefensivePossessionsBefore": poss_d, "rawOffensivePPDBefore": raw_o,
                "rawDefensivePPDAllowedBefore": raw_d, "ppdLeagueMeanBefore": mean,
                "opponentAdjustedOffensePPDAboveAverage": off,
                "opponentAdjustedDefensePPDPreventedAboveAverage": deff,
                "expectedOffensivePPDVsAverageDefense": float(mean)+float(off) if _num(mean) and _num(off) else None,
                "expectedDefensivePPDAllowedVsAverageOffense": float(mean)-float(deff) if _num(mean) and _num(deff) else None,
                "ppdFitIterations": fitted.get("iterations"), "ppdFitConverged": fitted.get("converged"),
                "ppdFitObservations": fitted.get("observations"), "ppdFitPossessions": fitted.get("possessions"),
                "drivePpdPointsFoundation": DRIVE_PPD_POINTS_FOUNDATION, "drivePpdVersion": DRIVE_PPD_VERSION,
            })
        history.extend(parts[key])
    return out


def build_matchup_ppd(snapshots: list[dict[str, Any]], season: int):
    by_game = defaultdict(list)
    for r in snapshots:
        if r.get("season") == season: by_game[str(r.get("gameId"))].append(r)
    out = []
    for gid, pair in sorted(by_game.items()):
        if len(pair) != 2 or pair[0].get("team") == pair[1].get("team"): continue
        a, b = pair; mean = a.get("ppdLeagueMeanBefore")
        if not _num(mean): mean = b.get("ppdLeagueMeanBefore")
        ao, ad = a.get("opponentAdjustedOffensePPDAboveAverage"), a.get("opponentAdjustedDefensePPDPreventedAboveAverage")
        bo, bd = b.get("opponentAdjustedOffensePPDAboveAverage"), b.get("opponentAdjustedDefensePPDPreventedAboveAverage")
        ae = float(mean)+float(ao)-float(bd) if all(_num(x) for x in (mean, ao, bd)) else None
        be = float(mean)+float(bo)-float(ad) if all(_num(x) for x in (mean, bo, ad)) else None
        out.append({
            "season": season, "seasonType": a.get("seasonType"), "week": a.get("week"), "gameId": gid,
            "team1": a.get("team"), "team2": b.get("team"),
            "team1OpponentAdjustedOffensePPDAboveAverage": ao, "team1OpponentAdjustedDefensePPDPreventedAboveAverage": ad,
            "team2OpponentAdjustedOffensePPDAboveAverage": bo, "team2OpponentAdjustedDefensePPDPreventedAboveAverage": bd,
            "team1ExpectedOffensivePPD": ae, "team1ExpectedDefensivePPDAllowed": be,
            "team2ExpectedOffensivePPD": be, "team2ExpectedDefensivePPDAllowed": ae,
            "expectedPPDDifferenceTeam1MinusTeam2": float(ae)-float(be) if _num(ae) and _num(be) else None,
            "ppdLeagueMeanBefore": mean, "team1GamesPlayedBefore": a.get("gamesPlayedBefore"),
            "team2GamesPlayedBefore": b.get("gamesPlayedBefore"), "drivePpdPointsFoundation": DRIVE_PPD_POINTS_FOUNDATION,
            "drivePpdVersion": DRIVE_PPD_VERSION,
        })
    return out


def orient_matchup_ppd(matchup: dict[str, Any], home_team: str, away_team: str):
    t1, t2 = matchup.get("team1"), matchup.get("team2")
    if {t1, t2} != {home_team, away_team}: return None
    hp, ap = ("team1", "team2") if t1 == home_team else ("team2", "team1")
    he, ae = matchup.get(f"{hp}ExpectedOffensivePPD"), matchup.get(f"{ap}ExpectedOffensivePPD")
    return {
        "homeOpponentAdjustedOffensePPDAboveAverage": matchup.get(f"{hp}OpponentAdjustedOffensePPDAboveAverage"),
        "homeOpponentAdjustedDefensePPDPreventedAboveAverage": matchup.get(f"{hp}OpponentAdjustedDefensePPDPreventedAboveAverage"),
        "awayOpponentAdjustedOffensePPDAboveAverage": matchup.get(f"{ap}OpponentAdjustedOffensePPDAboveAverage"),
        "awayOpponentAdjustedDefensePPDPreventedAboveAverage": matchup.get(f"{ap}OpponentAdjustedDefensePPDPreventedAboveAverage"),
        "homeExpectedOffensivePPD": he, "homeExpectedDefensivePPDAllowed": ae,
        "awayExpectedOffensivePPD": ae, "awayExpectedDefensivePPDAllowed": he,
        "expectedPPDEdge": float(he)-float(ae) if _num(he) and _num(ae) else None,
        "ppdLeagueMeanBefore": matchup.get("ppdLeagueMeanBefore"), "drivePpdVersion": DRIVE_PPD_VERSION,
    }


def expected_score(ppd: float | None, possessions: float | None):
    return float(ppd)*float(possessions) if _num(ppd) and _num(possessions) else None


def attach_postgame_residuals(matchups, team_games):
    observed = defaultdict(dict)
    for r in team_games: observed[str(r.get("gameId"))][str(r.get("team"))] = r
    out = []
    for m in matchups:
        gid = str(m.get("gameId")); t1, t2 = str(m.get("team1")), str(m.get("team2"))
        r1, r2 = observed.get(gid, {}).get(t1), observed.get(gid, {}).get(t2)
        if not r1 or not r2: continue
        e1, e2, a1, a2 = m.get("team1ExpectedOffensivePPD"), m.get("team2ExpectedOffensivePPD"), r1.get("offensivePPD"), r2.get("offensivePPD")
        row = dict(m); row.update({
            "team1ActualOffensivePPD": a1, "team2ActualOffensivePPD": a2,
            "team1OffensivePPDAboveExpectation": float(a1)-float(e1) if _num(a1) and _num(e1) else None,
            "team2OffensivePPDAboveExpectation": float(a2)-float(e2) if _num(a2) and _num(e2) else None,
            "team1DefensivePPDAboveExpectation": float(e2)-float(a2) if _num(a2) and _num(e2) else None,
            "team2DefensivePPDAboveExpectation": float(e1)-float(a1) if _num(a1) and _num(e1) else None,
            "postgameTargetDiagnostic": True,
        }); out.append(row)
    return out


def load_season_corpus(raw_root: Path, processed_root: Path, season: int):
    drives, plays = [], []
    for st, week in discover_partitions(raw_root, season):
        dpath = derived_drive_partition_dir(processed_root, season, st, week) / "drives.json"
        ppath = canonical_partition_dir(processed_root, season, st, week) / "plays.json"
        if not dpath.exists() or not ppath.exists(): raise FileNotFoundError(f"Missing derived/canonical partition for {season} {st} week {week}")
        drives.extend(json.loads(dpath.read_text())); plays.extend(json.loads(ppath.read_text()))
    return drives, plays


def materialize_season(raw_root: Path, processed_root: Path, season: int, shrinkage_possessions=DEFAULT_SHRINKAGE_POSSESSIONS):
    drives, plays = load_season_corpus(raw_root, processed_root, season)
    team_games = build_team_game_drive_rows(drives, plays)
    snapshots = build_pregame_ppd_snapshots(team_games, season, shrinkage_possessions=shrinkage_possessions)
    matchups = build_matchup_ppd(snapshots, season); postgame = attach_postgame_residuals(matchups, team_games)
    root = processed_root / "derived" / "drive_ppd" / f"season={season}"; root.mkdir(parents=True, exist_ok=True)
    for name, rows in (("team_games", team_games), ("pregame", snapshots), ("matchups", matchups), ("postgame_diagnostics", postgame)):
        (root / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    resolved = sum(int(r.get("resolvedPointPossessions") or 0) for r in team_games)
    unresolved = sum(int(r.get("unresolvedPointPossessions") or 0) for r in team_games)
    points = sum(float(r.get("offensiveDrivePoints") or 0) for r in team_games)
    checks = {
        "one_snapshot_per_team_game": len(snapshots) == len(team_games),
        "matchups_have_two_distinct_teams": all(r.get("team1") != r.get("team2") for r in matchups),
        "no_postgame_targets_in_matchups": all("Actual" not in k and "AboveExpectation" not in k for r in matchups for k in r),
        "points_foundation_locked": all(r.get("drivePpdPointsFoundation") == DRIVE_PPD_POINTS_FOUNDATION for r in team_games),
        "resolved_possessions_positive": resolved > 0,
    }
    manifest = {"season": season, "version": DRIVE_PPD_VERSION, "pointsFoundation": DRIVE_PPD_POINTS_FOUNDATION,
                "shrinkagePossessions": shrinkage_possessions, "teamGameRows": len(team_games), "snapshotRows": len(snapshots),
                "matchupRows": len(matchups), "postgameRows": len(postgame), "resolvedPointPossessions": resolved,
                "unresolvedPointPossessions": unresolved, "offensiveDrivePoints": points,
                "pointsPerResolvedPossession": points/resolved if resolved else None, "checks": checks,
                "status": "PASS" if all(checks.values()) else "REVIEW"}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)); return manifest


def main():
    from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS
    p = argparse.ArgumentParser(); p.add_argument("--season", type=int); p.add_argument("--all", action="store_true")
    p.add_argument("--shrinkage-possessions", type=float, default=DEFAULT_SHRINKAGE_POSSESSIONS)
    p.add_argument("--raw-root", type=Path, default=Path("data/raw")); p.add_argument("--processed-root", type=Path, default=Path("data/processed")); a = p.parse_args()
    seasons = list(DEFAULT_SEASONS) if a.all else ([a.season] if a.season else [])
    if not seasons: p.error("choose --season YYYY or --all")
    for s in seasons:
        r = materialize_season(a.raw_root, a.processed_root, int(s), a.shrinkage_possessions)
        print(f"DRIVE PPD {s}: {r['status']} | rows={r['teamGameRows']:,} | resolved poss={r['resolvedPointPossessions']:,} | PPD={r['pointsPerResolvedPossession']:.3f}")


if __name__ == "__main__": main()
