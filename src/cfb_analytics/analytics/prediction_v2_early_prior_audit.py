"""Audit previous-season state coverage for an early-season Prediction v2 challenger.

This command does not fit a game-margin challenger and does not replay PBP. It
reconstructs final prior-season team state from already-saved derived artifacts,
then measures how many early current-season games could receive a complete prior
for every Prediction-v2 information family.

The audit intentionally requires an immediately adjacent historical season. The
2021 season therefore has no prior because 2020 is absent from the project corpus;
2019 is never substituted silently.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.football_mechanisms import _state, _sum_into
from cfb_analytics.analytics.iterative_ratings import SPECS, fit_all_ratings
from cfb_analytics.analytics.model_feature_store import load_saved_feature_store
from cfb_analytics.analytics.prediction_v1_site_aware_challenger import fit_site_aware_srs
from cfb_analytics.analytics.sandbox_components import compute_systems_from_components
from cfb_analytics.analytics.site_context_audit import load_raw_site_rows
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.raw.audit import discover_partitions

AUDIT_VERSION = "prediction-v2-early-prior-audit-v1"
EARLY_MAX_WEEK = 4
REQUIRED_MECHANISM_FIELDS = (
    "OffSuccessRate",
    "DefSuccessRateAllowed",
    "OffExplosiveRate",
    "DefExplosiveRateAllowed",
    "OffGiveawayRate",
    "DefTakeawayRate",
    "OffPossessionsPerGame",
    "DefPossessionsPerGame",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def adjacent_prior_map(seasons: tuple[int, ...] = DEFAULT_SEASONS) -> dict[int, int]:
    available = {int(season) for season in seasons}
    return {
        int(season): int(season) - 1
        for season in seasons
        if int(season) - 1 in available
    }


def partition_key(season_type: Any, week: Any) -> tuple[int, int]:
    text = str(season_type or "regular").lower()
    return (0 if text in {"regular", "regular_season"} else 1, int(week or 0))


def is_early_regular_game(row: dict[str, Any]) -> bool:
    season_type = str(row.get("seasonType") or "regular").lower()
    return season_type in {"regular", "regular_season"} and int(row.get("week") or 0) <= EARLY_MAX_WEEK


def current_games_before(row: dict[str, Any]) -> tuple[int, int]:
    return (
        int(row.get("homeIterativeGamesPlayedBefore", 0) or 0),
        int(row.get("awayIterativeGamesPlayedBefore", 0) or 0),
    )


def load_team_games(raw_root: Path, processed_root: Path, season: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for season_type, week in sorted(discover_partitions(raw_root, season), key=lambda item: partition_key(*item)):
        path = derived_game_partition_dir(processed_root, season, season_type, week) / "team_games.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing saved derived team-game file: {path}")
        payload = json.loads(path.read_text())
        if not isinstance(payload, list):
            raise ValueError(f"Derived team-game payload is not a list: {path}")
        rows.extend(row for row in payload if isinstance(row, dict))
    return rows


def final_iterative_teams(team_games: list[dict[str, Any]]) -> set[str]:
    fitted = fit_all_ratings(team_games)
    teams = {
        str(row.get("team"))
        for row in team_games
        if row.get("team")
    }
    complete: set[str] = set()
    for team in teams:
        ok = True
        for name, *_ in SPECS:
            result = fitted.get(name, {})
            ok = ok and finite(result.get("offense", {}).get(team)) and finite(result.get("defense", {}).get(team))
        if ok:
            complete.add(team)
    return complete


def final_mechanism_teams(team_games: list[dict[str, Any]]) -> set[str]:
    totals: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    games: Counter[str] = Counter()
    for row in team_games:
        team = row.get("team")
        if not team:
            continue
        name = str(team)
        _sum_into(totals[name], row)
        games[name] += 1
    complete: set[str] = set()
    for team in games:
        state = _state(totals[team], games[team])
        if all(finite(state.get(field)) for field in REQUIRED_MECHANISM_FIELDS):
            complete.add(team)
    return complete


def final_mwdr_teams(processed_root: Path, season: int) -> set[str]:
    path = processed_root / "derived" / "sandbox_components" / f"season={season}" / "team_games.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing saved sandbox components for {season}: {path}. "
            "Do not rebuild PBP for this audit; restore/build the normal saved component cache first."
        )
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError(f"Sandbox component payload is not a list: {path}")
    ratings = compute_systems_from_components([row for row in payload if isinstance(row, dict)])
    return {
        str(row["Team"])
        for row in ratings
        if row.get("Team") and finite(row.get("MWDR_Off")) and finite(row.get("MWDR_Def"))
    }


def final_site_srs_teams(raw_root: Path, processed_root: Path, season: int) -> tuple[set[str], float | None]:
    rows = load_saved_feature_store(processed_root, season)
    site_rows, _, _ = load_raw_site_rows(raw_root, season)
    attached: list[dict[str, Any]] = []
    for row in rows:
        site = site_rows.get(str(row.get("gameId")))
        if site is None or not isinstance(site.get("isNeutralSite"), bool):
            raise ValueError(f"Missing site flag for prior-season game {season} {row.get('gameId')}")
        attached.append({**row, "isNeutralSite": site["isNeutralSite"]})
    fitted = fit_site_aware_srs(attached)
    if fitted.get("converged") is not True:
        raise RuntimeError(f"Final site-aware SRS did not converge for {season}")
    ratings = fitted.get("ratings", {})
    teams = {str(team) for team, value in ratings.items() if finite(value)}
    hfa = fitted.get("homeFieldAdvantage")
    return teams, float(hfa) if finite(hfa) else None


def model_teams(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(team)
        for row in rows
        for team in (row.get("homeTeam"), row.get("awayTeam"))
        if team
    }


def covered_game(row: dict[str, Any], complete_prior_teams: set[str]) -> bool:
    return (
        str(row.get("homeTeam")) in complete_prior_teams
        and str(row.get("awayTeam")) in complete_prior_teams
    )


def audit_season(raw_root: Path, processed_root: Path, season: int, prior_season: int) -> dict[str, Any]:
    current_rows = load_saved_feature_store(processed_root, season)
    prior_rows = load_saved_feature_store(processed_root, prior_season)
    prior_team_games = load_team_games(raw_root, processed_root, prior_season)

    current_team_set = model_teams(current_rows)
    prior_team_set = model_teams(prior_rows)
    iterative = final_iterative_teams(prior_team_games)
    mechanisms = final_mechanism_teams(prior_team_games)
    mwdr = final_mwdr_teams(processed_root, prior_season)
    site_srs, prior_final_hfa = final_site_srs_teams(raw_root, processed_root, prior_season)
    complete = iterative & mechanisms & mwdr & site_srs

    early = [row for row in current_rows if is_early_regular_game(row)]
    covered_early = [row for row in early if covered_game(row, complete)]
    min3_unavailable = [row for row in early if min(current_games_before(row)) < 3]
    min4_unavailable = [row for row in early if min(current_games_before(row)) < 4]
    rescued3 = [row for row in min3_unavailable if covered_game(row, complete)]
    rescued4 = [row for row in min4_unavailable if covered_game(row, complete)]

    return {
        "season": season,
        "priorSeason": prior_season,
        "currentTeams": len(current_team_set),
        "priorTeams": len(prior_team_set),
        "sharedTeams": len(current_team_set & prior_team_set),
        "iterativeTeams": len(iterative & current_team_set),
        "mechanismTeams": len(mechanisms & current_team_set),
        "mwdrTeams": len(mwdr & current_team_set),
        "siteSrsTeams": len(site_srs & current_team_set),
        "completePriorTeams": len(complete & current_team_set),
        "priorFinalHfa": prior_final_hfa,
        "earlyGames": len(early),
        "earlyCovered": len(covered_early),
        "min3UnavailableEarly": len(min3_unavailable),
        "min3PriorCoverable": len(rescued3),
        "min4UnavailableEarly": len(min4_unavailable),
        "min4PriorCoverable": len(rescued4),
    }


def audit(raw_root: Path, processed_root: Path) -> dict[str, Any]:
    prior_map = adjacent_prior_map()
    seasons = [audit_season(raw_root, processed_root, season, prior) for season, prior in sorted(prior_map.items())]
    total_early = sum(row["earlyGames"] for row in seasons)
    total_covered = sum(row["earlyCovered"] for row in seasons)
    min3_unavailable = sum(row["min3UnavailableEarly"] for row in seasons)
    min3_coverable = sum(row["min3PriorCoverable"] for row in seasons)
    min4_unavailable = sum(row["min4UnavailableEarly"] for row in seasons)
    min4_coverable = sum(row["min4PriorCoverable"] for row in seasons)
    ready = (
        bool(seasons)
        and total_covered > 0
        and min3_coverable > 0
        and all(row["priorFinalHfa"] is not None for row in seasons)
    )
    excluded = {
        int(season): (
            "no earlier corpus season" if int(season) == min(DEFAULT_SEASONS)
            else f"immediately prior season {int(season)-1} absent from corpus"
        )
        for season in DEFAULT_SEASONS
        if int(season) not in prior_map
    }
    return {
        "version": AUDIT_VERSION,
        "status": "READY" if ready else "REVIEW",
        "priorMap": prior_map,
        "excluded": excluded,
        "seasons": seasons,
        "earlyGames": total_early,
        "earlyCovered": total_covered,
        "min3UnavailableEarly": min3_unavailable,
        "min3PriorCoverable": min3_coverable,
        "min4UnavailableEarly": min4_unavailable,
        "min4PriorCoverable": min4_coverable,
    }


def pct(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator):.1%}" if denominator else "N/A"


def main() -> None:
    root = project_root()
    result = audit(root / "data" / "raw", root / "data" / "processed")
    print("PREDICTION V2 EARLY-SEASON PRIOR FEASIBILITY AUDIT")
    print(f"Version: {result['version']}")
    print(f"Status: {result['status']}")
    print("Adjacent prior seasons: " + ", ".join(f"{season}<-{prior}" for season, prior in result["priorMap"].items()))
    print("Excluded seasons:")
    for season, reason in result["excluded"].items():
        print(f" {season}: {reason}")

    print("\nBY CURRENT SEASON")
    for row in result["seasons"]:
        hfa = f"{row['priorFinalHfa']:+.3f}" if row["priorFinalHfa"] is not None else "N/A"
        print(
            f" {row['season']} <- {row['priorSeason']}: teams shared={row['sharedTeams']}/{row['currentTeams']} | "
            f"complete prior={row['completePriorTeams']}/{row['currentTeams']} | "
            f"iter={row['iterativeTeams']} mech={row['mechanismTeams']} mwdr={row['mwdrTeams']} srs={row['siteSrsTeams']} | "
            f"prior final HFA={hfa}"
        )
        print(
            f"   early games={row['earlyGames']} covered={row['earlyCovered']} ({pct(row['earlyCovered'], row['earlyGames'])}) | "
            f"min3 unavailable={row['min3UnavailableEarly']} coverable={row['min3PriorCoverable']} | "
            f"min4 unavailable={row['min4UnavailableEarly']} coverable={row['min4PriorCoverable']}"
        )

    print("\nTOTAL")
    print(f"Early regular games (week <= {EARLY_MAX_WEEK}): {result['earlyGames']:,}")
    print(f"Complete prior coverage: {result['earlyCovered']:,}/{result['earlyGames']:,} ({pct(result['earlyCovered'], result['earlyGames'])})")
    print(
        f"Currently below min3: {result['min3UnavailableEarly']:,} | "
        f"prior-coverable: {result['min3PriorCoverable']:,} ({pct(result['min3PriorCoverable'], result['min3UnavailableEarly'])})"
    )
    print(
        f"Currently below min4: {result['min4UnavailableEarly']:,} | "
        f"prior-coverable: {result['min4PriorCoverable']:,} ({pct(result['min4PriorCoverable'], result['min4UnavailableEarly'])})"
    )

    print("\nINTERPRETATION")
    if result["status"] == "READY":
        print(
            "Saved artifacts can support a full-family adjacent-season prior challenger without PBP replay. "
            "Use this coverage result to predeclare a development-only carryover/decay rule before evaluating game-margin outcomes."
        )
    else:
        print(
            "Do not fit the early-season challenger yet. Resolve the reported prior-state coverage/cache gaps first."
        )


if __name__ == "__main__":
    main()
