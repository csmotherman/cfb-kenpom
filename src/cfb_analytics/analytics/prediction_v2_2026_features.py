"""Outcome-free 2026 feature materializer for the frozen early-prior model.

Historical Prediction-v2 datasets are intentionally target-bearing. Prospective
2026 scoring must instead construct the same 19-feature vector from information
available strictly before the target partition.

The target matchup identity and neutral-site flag come from the saved raw games
schedule. Current-season Iterative, Football Mechanisms, MWDR, and site-aware SRS
state are rebuilt from strictly earlier partitions only. The frozen 2025 state is
then blended with the unchanged four-game linear carryover rule.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.authoritative_game_targets import normalize_authoritative_game
from cfb_analytics.analytics.football_mechanisms import _state, _sum_into, orient_matchup
from cfb_analytics.analytics.iterative_ratings import SPECS, fit_all_ratings
from cfb_analytics.analytics.model_feature_contract import iterative_matchup_value
from cfb_analytics.analytics.prediction_v1_site_aware_challenger import (
    fit_site_aware_srs,
    site_aware_margin,
)
from cfb_analytics.analytics.prediction_v2 import PREDICTION_V2_FEATURES
from cfb_analytics.analytics.prediction_v2_2026_freeze import (
    TARGET_SEASON,
    write_immutable_json,
)
from cfb_analytics.analytics.prediction_v2_early_prior_audit import (
    EARLY_MAX_WEEK,
    REQUIRED_MECHANISM_FIELDS,
    partition_key,
)
from cfb_analytics.analytics.prediction_v2_early_prior_challenger import (
    CHALLENGER_VERSION,
    _prior_state,
    blend_value,
    finite,
    prior_weight,
)
from cfb_analytics.analytics.sandbox_components import compute_systems_from_components
from cfb_analytics.analytics.site_context_audit import extract_neutral_site
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.storage import partition_dir

FEATURE_MATERIALIZER_VERSION = "prediction-v2-2026-outcome-free-features-v1"
PRIOR_SEASON = 2025


def _partition_before(season_type: Any, week: Any, target_type: Any, target_week: Any) -> bool:
    return partition_key(season_type, week) < partition_key(target_type, target_week)


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing saved artifact: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list: {path}")
    return [row for row in payload if isinstance(row, dict)]


def _resolve_target_partition(raw_root: Path, season: int, week: int) -> tuple[str, int]:
    matches = [
        (season_type, int(found_week))
        for season_type, found_week in discover_partitions(raw_root, season)
        if partition_key(season_type, found_week) == (0, int(week))
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one regular-season raw partition for {season} week {week}; "
            f"found {matches}"
        )
    return matches[0]


def _target_schedule(raw_root: Path, season: int, season_type: str, week: int) -> list[dict[str, Any]]:
    path = partition_dir(raw_root, season, season_type, week) / "games.json"
    rows: list[dict[str, Any]] = []
    scored: list[str] = []
    for raw in _load_json_list(path):
        game = normalize_authoritative_game(raw)
        if game is None:
            continue
        gid = str(game["gameId"])
        if finite(game.get("homeScore")) or finite(game.get("awayScore")):
            scored.append(gid)
        _, neutral = extract_neutral_site(raw)
        rows.append(
            {
                "season": season,
                "seasonType": season_type,
                "week": int(week),
                "gameId": gid,
                "homeTeam": game.get("homeTeam"),
                "awayTeam": game.get("awayTeam"),
                "isNeutralSite": neutral,
            }
        )
    if scored:
        raise ValueError(
            f"Target partition {season} {season_type} week {week} already contains scores for "
            f"{len(scored)} game(s). Refusing to create a pregame snapshot after outcomes exist: "
            + ", ".join(scored[:10])
        )
    return rows


def _history_team_games(
    raw_root: Path,
    processed_root: Path,
    season: int,
    target_type: str,
    target_week: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for season_type, week in sorted(
        discover_partitions(raw_root, season),
        key=lambda item: partition_key(*item),
    ):
        if not _partition_before(season_type, week, target_type, target_week):
            continue
        path = derived_game_partition_dir(processed_root, season, season_type, week) / "team_games.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing prior-partition team-game artifact required for prospective state: {path}"
            )
        rows.extend(_load_json_list(path))
    return rows


def _complete_history_game_ids(history: list[dict[str, Any]]) -> set[str]:
    """Return the authoritative completed-game sample represented by two team rows.

    The frozen historical model states are built from derived/model games, not every
    final score present in the raw games endpoint. Raw data supplies authoritative
    score and site context for this sample; it must not enlarge the sample.
    """
    missing_id_rows = sum(row.get("gameId") is None for row in history)
    if missing_id_rows:
        raise ValueError(
            f"Completed derived history contains {missing_id_rows} team row(s) without gameId"
        )
    counts: Counter[str] = Counter(str(row["gameId"]) for row in history)
    malformed = sorted(game_id for game_id, count in counts.items() if count != 2)
    if malformed:
        raise ValueError(
            "Completed derived history must contain exactly two team rows per game; "
            f"malformed game IDs={malformed[:10]}"
        )
    return set(counts)


def _history_components(
    processed_root: Path,
    season: int,
    target_type: str,
    target_week: int,
    *,
    history_required: bool,
) -> list[dict[str, Any]]:
    path = processed_root / "derived" / "sandbox_components" / f"season={season}" / "team_games.json"
    if not path.exists():
        if history_required:
            raise FileNotFoundError(
                f"Missing current-season sandbox component cache: {path}. "
                f"Build the normal saved component cache before creating the prospective snapshot."
            )
        return []
    return [
        row
        for row in _load_json_list(path)
        if _partition_before(row.get("seasonType"), row.get("week"), target_type, target_week)
    ]


def _history_site_games(
    raw_root: Path,
    season: int,
    target_type: str,
    target_week: int,
    *,
    required_game_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Load raw score/site context without letting raw finals enlarge model history.

    When ``required_game_ids`` is supplied, only those completed derived/model games
    are admitted. Every required game must have exactly one finite raw final and a
    parseable neutral-site flag. Extra raw finals are intentionally ignored because
    they were not part of the frozen historical state sample.
    """
    required = None if required_game_ids is None else {str(gid) for gid in required_game_ids}
    rows: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for season_type, week in sorted(
        discover_partitions(raw_root, season),
        key=lambda item: partition_key(*item),
    ):
        if not _partition_before(season_type, week, target_type, target_week):
            continue
        path = partition_dir(raw_root, season, season_type, week) / "games.json"
        for raw in _load_json_list(path):
            game = normalize_authoritative_game(raw)
            if game is None:
                continue
            gid = str(game["gameId"])
            if required is not None and gid not in required:
                continue
            home_score = game.get("homeScore")
            away_score = game.get("awayScore")
            if not finite(home_score) or not finite(away_score):
                continue
            _, neutral = extract_neutral_site(raw)
            if not isinstance(neutral, bool):
                raise ValueError(f"Missing parseable site context for prior game {gid}")
            seen[gid] += 1
            rows.append(
                {
                    "gameId": game["gameId"],
                    "homeTeam": game.get("homeTeam"),
                    "awayTeam": game.get("awayTeam"),
                    "target_margin": float(home_score) - float(away_score),
                    "isNeutralSite": neutral,
                }
            )
    if required is not None:
        missing = sorted(required - set(seen))
        duplicates = sorted(game_id for game_id, count in seen.items() if count != 1)
        if missing or duplicates:
            details: list[str] = []
            if missing:
                details.append(f"missing raw final/site games={missing[:10]}")
            if duplicates:
                details.append(f"duplicate raw final/site games={duplicates[:10]}")
            raise ValueError(
                "Raw score/site history does not exactly cover completed derived game sample; "
                + "; ".join(details)
            )
    return rows


def _iterative_state(history: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    fitted = fit_all_ratings(history)
    teams = {str(row.get("team")) for row in history if row.get("team")}
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for team in teams:
        for name, *_ in SPECS:
            result = fitted.get(name, {})
            offense = result.get("offense", {}).get(team)
            defense = result.get("defense", {}).get(team)
            if finite(offense):
                out[team][f"{name}Offense"] = float(offense)
            if finite(defense):
                out[team][f"{name}Defense"] = float(defense)
    return dict(out)


def _mechanism_state(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    totals: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: Counter[str] = Counter()
    for row in history:
        team = row.get("team")
        if not team:
            continue
        name = str(team)
        _sum_into(totals[name], row)
        counts[name] += 1
    return {team: _state(totals[team], counts[team]) for team in counts}


def _mwdr_state(history_components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ratings = compute_systems_from_components(history_components) if history_components else []
    return {
        str(row["Team"]): {"Off": row.get("MWDR_Off"), "Def": row.get("MWDR_Def")}
        for row in ratings
        if row.get("Team")
    }


def _site_state(history_games: list[dict[str, Any]]) -> tuple[dict[str, Any], float]:
    fitted = fit_site_aware_srs(history_games)
    if fitted.get("converged") is not True:
        raise RuntimeError("Current-season site-aware SRS failed to converge")
    return dict(fitted.get("ratings", {})), float(fitted.get("homeFieldAdvantage", 0.0))


def _current_row(
    game: dict[str, Any],
    iterative: dict[str, dict[str, float]],
    games_played: Counter[str],
    site_ratings: dict[str, Any],
    hfa: float,
) -> dict[str, Any]:
    home = str(game.get("homeTeam"))
    away = str(game.get("awayTeam"))
    row = dict(game)
    row["homeIterativeGamesPlayedBefore"] = games_played[home]
    row["awayIterativeGamesPlayedBefore"] = games_played[away]
    row["currentSiteAwareHomeRating"] = site_ratings.get(home)
    row["currentSiteAwareAwayRating"] = site_ratings.get(away)
    row["siteAwareSrsHfaBefore"] = hfa
    for name, *_ in SPECS:
        home_state = iterative.get(home, {})
        away_state = iterative.get(away, {})
        row[f"home_iterative{name}Offense"] = home_state.get(f"{name}Offense")
        row[f"home_iterative{name}Defense"] = home_state.get(f"{name}Defense")
        row[f"away_iterative{name}Offense"] = away_state.get(f"{name}Offense")
        row[f"away_iterative{name}Defense"] = away_state.get(f"{name}Defense")
    return row


def build_early_prior_feature_row(
    current: dict[str, Any],
    prior: dict[str, Any],
    current_mechanisms: dict[str, dict[str, Any]],
    current_mwdr: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Construct the frozen blend without consulting target/outcome fields."""
    home = str(current.get("homeTeam"))
    away = str(current.get("awayTeam"))
    home_games = int(current.get("homeIterativeGamesPlayedBefore", 0) or 0)
    away_games = int(current.get("awayIterativeGamesPlayedBefore", 0) or 0)
    out = dict(current)

    for name, *_ in SPECS:
        prior_home = prior["iterative"].get(home, {})
        prior_away = prior["iterative"].get(away, {})
        ho = blend_value(
            prior_home.get(f"{name}Offense"),
            current.get(f"home_iterative{name}Offense"),
            home_games,
        )
        hd = blend_value(
            prior_home.get(f"{name}Defense"),
            current.get(f"home_iterative{name}Defense"),
            home_games,
        )
        ao = blend_value(
            prior_away.get(f"{name}Offense"),
            current.get(f"away_iterative{name}Offense"),
            away_games,
        )
        ad = blend_value(
            prior_away.get(f"{name}Defense"),
            current.get(f"away_iterative{name}Defense"),
            away_games,
        )
        if not all(finite(value) for value in (ho, hd, ao, ad)):
            return None
        out[f"home_iterative{name}Edge"] = iterative_matchup_value(ho, ad)
        out[f"away_iterative{name}Edge"] = iterative_matchup_value(ao, hd)

    home_srs = blend_value(
        prior["siteRatings"].get(home),
        current.get("currentSiteAwareHomeRating"),
        home_games,
    )
    away_srs = blend_value(
        prior["siteRatings"].get(away),
        current.get("currentSiteAwareAwayRating"),
        away_games,
    )
    if not finite(home_srs) or not finite(away_srs):
        return None
    weight = (prior_weight(home_games) + prior_weight(away_games)) / 2.0
    current_hfa = current.get("siteAwareSrsHfaBefore")
    if weight <= 0.0:
        hfa = float(current_hfa) if finite(current_hfa) else None
    elif weight >= 1.0:
        hfa = float(prior["hfa"])
    elif finite(current_hfa):
        hfa = weight * float(prior["hfa"]) + (1.0 - weight) * float(current_hfa)
    else:
        hfa = float(prior["hfa"])
    edge = float(home_srs) - float(away_srs)
    out["siteAwareSrsMargin"] = site_aware_margin(edge, hfa, current.get("isNeutralSite"))
    if not finite(out.get("siteAwareSrsMargin")):
        return None

    prior_home_mwdr = prior["mwdr"].get(home, {})
    prior_away_mwdr = prior["mwdr"].get(away, {})
    current_home_mwdr = current_mwdr.get(home, {})
    current_away_mwdr = current_mwdr.get(away, {})
    home_mwdr_off = blend_value(prior_home_mwdr.get("Off"), current_home_mwdr.get("Off"), home_games)
    home_mwdr_def = blend_value(prior_home_mwdr.get("Def"), current_home_mwdr.get("Def"), home_games)
    away_mwdr_off = blend_value(prior_away_mwdr.get("Off"), current_away_mwdr.get("Off"), away_games)
    away_mwdr_def = blend_value(prior_away_mwdr.get("Def"), current_away_mwdr.get("Def"), away_games)
    if not all(finite(value) for value in (home_mwdr_off, home_mwdr_def, away_mwdr_off, away_mwdr_def)):
        return None
    out["home_MWDR_OffenseEdge"] = float(home_mwdr_off) - float(away_mwdr_def)
    out["home_MWDR_DefenseEdge"] = float(home_mwdr_def) - float(away_mwdr_off)

    prior_home_mech = prior["mechanisms"].get(home, {})
    prior_away_mech = prior["mechanisms"].get(away, {})
    current_home_mech = current_mechanisms.get(home, {})
    current_away_mech = current_mechanisms.get(away, {})
    synthetic: dict[str, Any] = {"team1": home, "team2": away}
    for field in REQUIRED_MECHANISM_FIELDS:
        home_value = blend_value(prior_home_mech.get(field), current_home_mech.get(field), home_games)
        away_value = blend_value(prior_away_mech.get(field), current_away_mech.get(field), away_games)
        if not finite(home_value) or not finite(away_value):
            return None
        synthetic[f"team1_{field}"] = home_value
        synthetic[f"team2_{field}"] = away_value
    oriented = orient_matchup(synthetic, home, away)
    if oriented is None:
        return None
    poss = oriented.get("expectedPossessionsPerTeam")
    success = oriented.get("netSuccessRateEdge")
    explosive = oriented.get("netExplosiveRateEdge")
    turnover = oriented.get("netTurnoverPressureEdge")
    if not all(finite(value) for value in (poss, success, explosive, turnover)):
        return None

    mwdr_edge = float(out["home_MWDR_OffenseEdge"]) + float(out["home_MWDR_DefenseEdge"])
    out["mwdrXExpectedPossessions"] = mwdr_edge * float(poss)
    out["successVolumeEdge"] = float(success) * float(poss)
    out["explosiveVolumeEdge"] = float(explosive) * float(poss)
    out["turnoverVolumeEdge"] = float(turnover) * float(poss)
    out["expectedPossessionsPerTeam"] = float(poss)
    out["priorWeightHome"] = prior_weight(home_games)
    out["priorWeightAway"] = prior_weight(away_games)
    out["earlyPriorMode"] = "blend"
    out["earlyPriorVersion"] = CHALLENGER_VERSION
    out["prospectiveFeatureVersion"] = FEATURE_MATERIALIZER_VERSION
    out["baselineNonNeutral"] = 0.0 if current.get("isNeutralSite") else 1.0

    if any(key.startswith("target_") and value is not None for key, value in out.items()):
        raise ValueError("Prospective feature builder received outcome-bearing target fields")
    return out if all(finite(out.get(feature)) for feature in PREDICTION_V2_FEATURES) else None


def materialize_week(
    raw_root: Path,
    processed_root: Path,
    *,
    season: int,
    week: int,
    as_of: str,
) -> dict[str, Any]:
    if int(season) != TARGET_SEASON:
        raise ValueError(f"Prospective feature materializer is frozen to season {TARGET_SEASON}")
    if int(week) < 0 or int(week) > EARLY_MAX_WEEK:
        raise ValueError(f"Early-prior prospective materializer supports regular weeks 0-{EARLY_MAX_WEEK}")
    parsed_as_of = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    if parsed_as_of.tzinfo is None:
        raise ValueError("--as-of must be an offset-aware ISO-8601 timestamp")

    season_type, resolved_week = _resolve_target_partition(raw_root, season, week)
    schedule = _target_schedule(raw_root, season, season_type, resolved_week)
    history = _history_team_games(raw_root, processed_root, season, season_type, resolved_week)
    required_history_game_ids = _complete_history_game_ids(history)
    history_components = _history_components(
        processed_root,
        season,
        season_type,
        resolved_week,
        history_required=bool(history),
    )
    history_site = _history_site_games(
        raw_root,
        season,
        season_type,
        resolved_week,
        required_game_ids=required_history_game_ids,
    )

    games_played: Counter[str] = Counter(
        str(row.get("team")) for row in history if row.get("team")
    )
    iterative = _iterative_state(history)
    mechanisms = _mechanism_state(history)
    current_mwdr = _mwdr_state(history_components)
    site_ratings, current_hfa = _site_state(history_site)
    prior = _prior_state(raw_root, processed_root, PRIOR_SEASON)

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for game in schedule:
        gid = str(game.get("gameId"))
        if not game.get("homeTeam") or not game.get("awayTeam"):
            excluded.append({"gameId": gid, "reason": "missing home/away team"})
            continue
        if not isinstance(game.get("isNeutralSite"), bool):
            excluded.append({"gameId": gid, "reason": "missing parseable neutral-site flag"})
            continue
        current = _current_row(game, iterative, games_played, site_ratings, current_hfa)
        row = build_early_prior_feature_row(current, prior, mechanisms, current_mwdr)
        if row is None:
            excluded.append({"gameId": gid, "reason": "incomplete frozen early-prior feature vector"})
            continue
        row["featureAsOf"] = parsed_as_of.isoformat()
        rows.append(row)

    return {
        "schemaVersion": 1,
        "featureMaterializerVersion": FEATURE_MATERIALIZER_VERSION,
        "earlyPriorVersion": CHALLENGER_VERSION,
        "season": season,
        "seasonType": season_type,
        "week": int(resolved_week),
        "asOf": parsed_as_of.isoformat(),
        "scheduleGames": len(schedule),
        "historyTeamGameRows": len(history),
        "historyComponentRows": len(history_components),
        "historySiteGames": len(history_site),
        "featureRows": len(rows),
        "excluded": excluded,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize outcome-free 2026 features for the frozen early-prior model"
    )
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    result = materialize_week(
        args.raw_root,
        args.processed_root,
        season=TARGET_SEASON,
        week=args.week,
        as_of=args.as_of,
    )
    if not result["rows"]:
        raise RuntimeError("No scoreable prospective rows were produced; inspect exclusions")

    write_immutable_json(args.output, result["rows"])
    audit_output = args.audit_output or args.output.with_name(args.output.stem + ".audit.json")
    audit_payload = {key: value for key, value in result.items() if key != "rows"}
    write_immutable_json(audit_output, audit_payload)
    print(
        f"PROSPECTIVE FEATURES season={result['season']} week={result['week']} "
        f"rows={result['featureRows']}/{result['scheduleGames']} "
        f"excluded={len(result['excluded'])} output={args.output}"
    )


if __name__ == "__main__":
    main()
