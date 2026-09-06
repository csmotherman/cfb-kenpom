from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
PUBLISHED = ROOT / "data" / "published"
ANALYSIS_VERSION = "matchup-full-v1"


@dataclass(frozen=True)
class MatchupMetric:
    label: str
    offense_key: str
    defense_key: str
    offense_higher_better: bool = True
    defense_higher_better: bool = False
    fmt: str = "pct"
    group: str = "efficiency"


MATCHUP_METRICS: tuple[MatchupMetric, ...] = (
    MatchupMetric("Success rate", "successRate", "successRateAllowed", fmt="pct", group="efficiency"),
    MatchupMetric("Rush success rate", "rushSuccessRate", "rushSuccessRateAllowed", fmt="pct", group="run"),
    MatchupMetric("Pass success rate", "passSuccessRate", "passSuccessRateAllowed", fmt="pct", group="pass"),
    MatchupMetric("Explosive play rate", "explosivePlayRate", "explosivePlayRateAllowed", fmt="pct", group="explosiveness"),
    MatchupMetric("Rush explosive rate", "rushExplosivePlayRate", "rushExplosivePlayRateAllowed", fmt="pct", group="run"),
    MatchupMetric("Pass explosive rate", "passExplosivePlayRate", "passExplosivePlayRateAllowed", fmt="pct", group="pass"),
    MatchupMetric("Yards per play", "yardsPerPlay", "yardsPerPlayAllowed", fmt="num", group="efficiency"),
    MatchupMetric("Yards per possession", "yardsPerPossession", "yardsPerPossessionAllowed", fmt="num", group="drives"),
    MatchupMetric("Points per resolved possession", "pointsPerResolvedPossession", "pointsPerResolvedPossessionAllowed", fmt="num", group="drives"),
    MatchupMetric("Scoring rate per possession", "scoringRatePerPossession", "scoringRatePerPossessionAllowed", fmt="pct", group="drives"),
    MatchupMetric("Third-down conversion", "thirdDownConversionRate", "thirdDownConversionRateAllowed", fmt="pct", group="downs"),
    MatchupMetric("Standard-down success", "standardDownSuccessRate", "standardDownSuccessRateAllowed", fmt="pct", group="downs"),
    MatchupMetric("Passing-down success", "passingDownSuccessRate", "passingDownSuccessRateAllowed", fmt="pct", group="downs"),
    MatchupMetric("Red-zone TD rate", "redZonePossessionTouchdownRate", "redZonePossessionTouchdownRateAllowed", fmt="pct", group="finishing"),
    MatchupMetric("Red-zone success", "redZoneSuccessRate", "redZoneSuccessRateAllowed", fmt="pct", group="finishing"),
    MatchupMetric("Points per opportunity", "pointsPerOpportunity", "pointsPerOpportunityAllowed", fmt="num", group="finishing"),
    MatchupMetric("Rush yards per attempt", "rushYardsPerAttempt", "rushYardsPerAttemptAllowed", fmt="num", group="run"),
    MatchupMetric("Net pass yards per dropback", "netPassYardsPerDropback", "netPassYardsPerDropbackAllowed", fmt="num", group="pass"),
    MatchupMetric("Havoc battle", "havocRateAllowed", "havocRate", offense_higher_better=False, defense_higher_better=True, fmt="pct", group="disruption"),
    MatchupMetric("Sack battle", "sackRate", "defensiveSackRate", offense_higher_better=False, defense_higher_better=True, fmt="pct", group="disruption"),
)

PROFILE_METRICS: tuple[tuple[str, str, bool, str], ...] = (
    ("Success rate", "successRate", True, "pct"),
    ("Success rate allowed", "successRateAllowed", False, "pct"),
    ("Rush success rate", "rushSuccessRate", True, "pct"),
    ("Rush success allowed", "rushSuccessRateAllowed", False, "pct"),
    ("Pass success rate", "passSuccessRate", True, "pct"),
    ("Pass success allowed", "passSuccessRateAllowed", False, "pct"),
    ("Explosive play rate", "explosivePlayRate", True, "pct"),
    ("Explosive rate allowed", "explosivePlayRateAllowed", False, "pct"),
    ("Yards per play", "yardsPerPlay", True, "num"),
    ("Yards per play allowed", "yardsPerPlayAllowed", False, "num"),
    ("Points per possession", "pointsPerResolvedPossession", True, "num"),
    ("Points per possession allowed", "pointsPerResolvedPossessionAllowed", False, "num"),
    ("Third-down conversion", "thirdDownConversionRate", True, "pct"),
    ("Third-down conversion allowed", "thirdDownConversionRateAllowed", False, "pct"),
    ("Havoc created", "havocRate", True, "pct"),
    ("Havoc allowed", "havocRateAllowed", False, "pct"),
    ("Points per opportunity", "pointsPerOpportunity", True, "num"),
    ("Points per opportunity allowed", "pointsPerOpportunityAllowed", False, "num"),
)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def _single_row(path: Path) -> dict[str, Any]:
    data = _load_json(path, [])
    if isinstance(data, list):
        return data[0] if data else {}
    return data if isinstance(data, dict) else {}


def _norm(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _team_directory(season: int, team: str) -> tuple[Path, dict[str, Any]]:
    teams_root = PUBLISHED / str(season) / "teams"
    direct = teams_root / _slug(team)
    if direct.exists():
        row = _single_row(direct / "season.json")
        if row:
            return direct, row

    wanted = _norm(team)
    for season_file in teams_root.glob("*/season.json"):
        row = _single_row(season_file)
        if _norm(row.get("team")) == wanted:
            return season_file.parent, row
    raise FileNotFoundError(f"Could not find {team!r} in {teams_root}")


def _all_fbs_season_rows(season: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for season_file in sorted((PUBLISHED / str(season) / "teams").glob("*/season.json")):
        row = _single_row(season_file)
        if row and str(row.get("classification", "")).lower() == "fbs":
            rows.append(row)
    if not rows:
        raise RuntimeError(f"No FBS season rows found for {season}")
    return rows


def _rank_value(rows: Iterable[dict[str, Any]], key: str, target: float | None, *, higher_better: bool) -> dict[str, Any]:
    if target is None:
        return {"rank": None, "fieldSize": 0, "percentile": None}
    values = [_finite(row.get(key)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {"rank": None, "fieldSize": 0, "percentile": None}
    rank = 1 + sum(value > target for value in values) if higher_better else 1 + sum(value < target for value in values)
    field_size = len(values)
    percentile = 1.0 if field_size <= 1 else 1.0 - ((rank - 1) / (field_size - 1))
    return {"rank": rank, "fieldSize": field_size, "percentile": percentile}


def _metric_snapshot(row: dict[str, Any], all_rows: list[dict[str, Any]], key: str, *, higher_better: bool, label: str, fmt: str) -> dict[str, Any]:
    value = _finite(row.get(key))
    return {
        "label": label,
        "key": key,
        "value": value,
        "format": fmt,
        "higherIsBetter": higher_better,
        **_rank_value(all_rows, key, value, higher_better=higher_better),
    }


def _ridge_team(ridge: dict[str, Any], team: str) -> dict[str, Any] | None:
    wanted = _norm(team)
    return next((row for row in ridge.get("teams", []) if _norm(row.get("team")) == wanted), None)


def _record(games: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "wins": sum(int(game.get("win") or 0) for game in games),
        "losses": sum(int(game.get("loss") or 0) for game in games),
        "games": len(games),
    }


def _game_summary(game: dict[str, Any], ridge_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    opponent = str(game.get("opponent") or "Unknown")
    opponent_ridge = ridge_by_name.get(_norm(opponent))
    points_for = game.get("points_for")
    points_against = game.get("points_against")
    return {
        "gameId": str(game.get("gameId") or game.get("game_id") or ""),
        "week": game.get("week"),
        "seasonType": game.get("seasonType") or game.get("season_type"),
        "homeAway": game.get("home_away"),
        "opponent": opponent,
        "result": "W" if game.get("win") else "L" if game.get("loss") else "—",
        "pointsFor": points_for,
        "pointsAgainst": points_against,
        "margin": points_for - points_against if points_for is not None and points_against is not None else None,
        "successRate": game.get("successRate"),
        "successRateAllowed": game.get("successRateAllowed"),
        "rushSuccessRate": game.get("rushSuccessRate"),
        "rushSuccessRateAllowed": game.get("rushSuccessRateAllowed"),
        "passSuccessRate": game.get("passSuccessRate"),
        "passSuccessRateAllowed": game.get("passSuccessRateAllowed"),
        "explosivePlayRate": game.get("explosivePlayRate"),
        "explosivePlayRateAllowed": game.get("explosivePlayRateAllowed"),
        "yardsPerPlay": game.get("yardsPerPlay"),
        "yardsPerPlayAllowed": game.get("yardsPerPlayAllowed"),
        "pointsPerResolvedPossession": game.get("pointsPerResolvedPossession"),
        "pointsPerResolvedPossessionAllowed": game.get("pointsPerResolvedPossessionAllowed"),
        "turnoverMargin": game.get("turnoverMargin"),
        "opponentRidgeOverallRating": opponent_ridge.get("overall", {}).get("rating") if opponent_ridge else None,
        "opponentRidgeOverallRank": opponent_ridge.get("overall", {}).get("rank") if opponent_ridge else None,
    }


def _aggregate_game_form(games: list[dict[str, Any]], recent_games: int) -> dict[str, Any]:
    window = games[-recent_games:] if recent_games > 0 else games
    keys = (
        "points_for", "points_against", "successRate", "successRateAllowed",
        "rushSuccessRate", "rushSuccessRateAllowed", "passSuccessRate", "passSuccessRateAllowed",
        "explosivePlayRate", "explosivePlayRateAllowed", "yardsPerPlay", "yardsPerPlayAllowed",
        "pointsPerResolvedPossession", "pointsPerResolvedPossessionAllowed", "turnoverMargin",
    )
    averages: dict[str, float | None] = {}
    variability: dict[str, float | None] = {}
    for key in keys:
        values = [_finite(game.get(key)) for game in window]
        values = [value for value in values if value is not None]
        averages[key] = mean(values) if values else None
        variability[key] = pstdev(values) if len(values) > 1 else 0.0 if values else None
    return {"games": len(window), "record": _record(window), "averages": averages, "variability": variability}


def _opponent_strength(games: list[dict[str, Any]], ridge_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rated = [(game, ridge_by_name[_norm(game.get("opponent"))]) for game in games if _norm(game.get("opponent")) in ridge_by_name]
    ratings = [_finite(ridge.get("overall", {}).get("rating")) for _, ridge in rated]
    ratings = [value for value in ratings if value is not None]
    top25 = [(game, ridge) for game, ridge in rated if (ridge.get("overall", {}).get("rank") or 999) <= 25]
    wins = [(game, ridge) for game, ridge in rated if game.get("win")]
    best_win = max(wins, key=lambda pair: pair[1].get("overall", {}).get("rating") or -999, default=None)
    return {
        "ratedOpponents": len(rated),
        "averageOpponentRidgeRating": mean(ratings) if ratings else None,
        "top25RidgeOpponents": len(top25),
        "recordVsTop25Ridge": _record([game for game, _ in top25]),
        "bestWin": {
            "opponent": best_win[0].get("opponent"),
            "score": f"{best_win[0].get('points_for')}-{best_win[0].get('points_against')}",
            "opponentRidgeRating": best_win[1].get("overall", {}).get("rating"),
            "opponentRidgeRank": best_win[1].get("overall", {}).get("rank"),
        } if best_win else None,
    }


def _team_style(row: dict[str, Any], games: list[dict[str, Any]]) -> dict[str, Any]:
    rush_attempts = _finite(row.get("rushAttempts")) or 0.0
    dropbacks = _finite(row.get("dropbacks")) or 0.0
    choices = rush_attempts + dropbacks
    possessions = _finite(row.get("possessions"))
    defensive_possessions = _finite(row.get("possessionsAllowed"))
    return {
        "rushShare": rush_attempts / choices if choices else None,
        "passShare": dropbacks / choices if choices else None,
        "possessionsPerGame": row.get("possessionsPerGame"),
        "defensivePossessionsPerGame": row.get("defensivePossessionsPerGame"),
        "averageStartOwnYardLine": row.get("averageStartOwnYardLine"),
        "averageOpponentStartOwnYardLine": row.get("averageStartOwnYardLineAllowed"),
        "threeAndOutRate": (_finite(row.get("threeAndOuts")) or 0.0) / possessions if possessions else None,
        "threeAndOutForcedRate": (_finite(row.get("threeAndOutsForced")) or 0.0) / defensive_possessions if defensive_possessions else None,
        "giveawaysPerGame": (_finite(row.get("giveaways")) or 0.0) / len(games) if games else None,
        "takeawaysPerGame": (_finite(row.get("takeaways")) or 0.0) / len(games) if games else None,
        "turnoverMargin": row.get("turnoverMargin"),
        "sacksAllowed": row.get("sacksAllowed"),
        "sacksMade": row.get("sacks"),
    }


def _team_profile(row: dict[str, Any], games: list[dict[str, Any]], all_rows: list[dict[str, Any]], ridge_row: dict[str, Any] | None, ridge_by_name: dict[str, dict[str, Any]], recent_games: int) -> dict[str, Any]:
    return {
        "team": row.get("team"),
        "teamId": row.get("team_id"),
        "conference": row.get("conference"),
        "games": row.get("games"),
        "record": _record(games),
        "ridge": ridge_row,
        "style": _team_style(row, games),
        "metrics": [_metric_snapshot(row, all_rows, key, higher_better=higher, label=label, fmt=fmt) for label, key, higher, fmt in PROFILE_METRICS],
        "recentForm": _aggregate_game_form(games, recent_games),
        "opponentStrength": _opponent_strength(games, ridge_by_name),
        "gameLog": [_game_summary(game, ridge_by_name) for game in games],
    }


def _offense_vs_defense(offense_row: dict[str, Any], defense_row: dict[str, Any], all_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offense_name = str(offense_row.get("team"))
    defense_name = str(defense_row.get("team"))
    output: list[dict[str, Any]] = []
    for spec in MATCHUP_METRICS:
        offense_value = _finite(offense_row.get(spec.offense_key))
        defense_value = _finite(defense_row.get(spec.defense_key))
        offense_rank = _rank_value(all_rows, spec.offense_key, offense_value, higher_better=spec.offense_higher_better)
        defense_rank = _rank_value(all_rows, spec.defense_key, defense_value, higher_better=spec.defense_higher_better)
        offense_quality = _finite(offense_rank.get("percentile"))
        defense_quality = _finite(defense_rank.get("percentile"))
        edge = offense_quality - defense_quality if offense_quality is not None and defense_quality is not None else None
        if edge is None:
            advantage = "NO DATA"
        elif edge >= 0.15:
            advantage = offense_name
        elif edge <= -0.15:
            advantage = defense_name
        else:
            advantage = "EVEN"
        output.append({
            "group": spec.group,
            "metric": spec.label,
            "format": spec.fmt,
            "offenseTeam": offense_name,
            "defenseTeam": defense_name,
            "offense": {"value": offense_value, **offense_rank},
            "defense": {"value": defense_value, **defense_rank},
            "relativeQualityEdge": edge,
            "advantage": advantage,
        })
    return output


def _common_opponents(games_a: list[dict[str, Any]], games_b: list[dict[str, Any]], ridge_by_name: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_a = {_norm(game.get("opponent")): game for game in games_a}
    by_b = {_norm(game.get("opponent")): game for game in games_b}
    return [{
        "opponent": by_a[key].get("opponent") or by_b[key].get("opponent"),
        "teamA": _game_summary(by_a[key], ridge_by_name),
        "teamB": _game_summary(by_b[key], ridge_by_name),
    } for key in sorted(set(by_a) & set(by_b))]


def _schedule_game(target_season: int, team_a: str, team_b: str) -> dict[str, Any] | None:
    schedule = _load_json(PUBLISHED / str(target_season) / "michigan" / "schedule.json", [])
    wanted = {_norm(team_a), _norm(team_b)}
    for game in schedule:
        if {_norm(game.get("homeTeam")), _norm(game.get("awayTeam"))} == wanted:
            return game
    return None


def _market_game(target_season: int, game_id: str | None, opponent: str) -> dict[str, Any] | None:
    market = _load_json(PUBLISHED / str(target_season) / "michigan" / "market-lines.json", {})
    for game in market.get("games", []):
        if game_id and str(game.get("gameId")) == str(game_id):
            return game
        if _norm(game.get("opponent")) == _norm(opponent):
            return game
    return None


def _ridge_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {"overall": row.get("overall"), "offense": row.get("offense"), "defense": row.get("defense"), "games": row.get("games")}


def _key_signals(team_a: str, team_b: str, ridge_a: dict[str, Any] | None, ridge_b: dict[str, Any] | None, a_offense: list[dict[str, Any]], b_offense: list[dict[str, Any]], market: dict[str, Any] | None) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if ridge_a and ridge_b:
        for category in ("overall", "offense", "defense"):
            a_rating = _finite(ridge_a.get(category, {}).get("rating"))
            b_rating = _finite(ridge_b.get(category, {}).get("rating"))
            if a_rating is not None and b_rating is not None:
                delta = a_rating - b_rating
                leader = team_a if delta >= 0 else team_b
                signals.append({
                    "type": "RIDGE",
                    "category": category,
                    "team": leader,
                    "magnitude": abs(delta),
                    "text": f"{leader} leads by {abs(delta):.1f} Ridge rating points in {category}",
                })

    matchup_rows = [row for row in a_offense + b_offense if _finite(row.get("relativeQualityEdge")) is not None]
    matchup_rows.sort(key=lambda row: abs(float(row["relativeQualityEdge"])), reverse=True)
    for row in matchup_rows[:8]:
        signals.append({
            "type": "MATCHUP",
            "category": row["metric"],
            "team": row["advantage"],
            "magnitude": abs(float(row["relativeQualityEdge"])),
            "text": f"{row['metric']}: {row['advantage']} ({row['offenseTeam']} offense #{row['offense']['rank']} vs {row['defenseTeam']} defense #{row['defense']['rank']})",
        })

    if market:
        spread = _finite(market.get("teamSpread"))
        if spread is not None:
            favored = team_a if spread < 0 else team_b
            signals.append({
                "type": "MARKET",
                "category": "spread",
                "team": favored,
                "magnitude": abs(spread),
                "text": f"Market: {favored} favored by {abs(spread):.1f} at {market.get('sportsbook')}",
            })
    return signals


def build_matchup_analysis(team_a: str = "Michigan", team_b: str = "Western Michigan", *, baseline_season: int = 2025, target_season: int = 2026, recent_games: int = 5, output_path: Path | None = None) -> dict[str, Any]:
    team_a_dir, team_a_season = _team_directory(baseline_season, team_a)
    team_b_dir, team_b_season = _team_directory(baseline_season, team_b)
    team_a_games = _load_json(team_a_dir / "games.json", [])
    team_b_games = _load_json(team_b_dir / "games.json", [])
    all_rows = _all_fbs_season_rows(baseline_season)

    ridge = _load_json(PUBLISHED / str(baseline_season) / "analytics" / "ridge-team-ratings.json", {})
    ridge_by_name = {_norm(row.get("team")): row for row in ridge.get("teams", []) if row.get("team")}
    ridge_a = _ridge_team(ridge, team_a)
    ridge_b = _ridge_team(ridge, team_b)

    game = _schedule_game(target_season, team_a, team_b)
    game_id = str(game.get("id")) if game else None
    market = _market_game(target_season, game_id, team_b)

    a_offense = _offense_vs_defense(team_a_season, team_b_season, all_rows)
    b_offense = _offense_vs_defense(team_b_season, team_a_season, all_rows)

    analysis = {
        "analysisVersion": ANALYSIS_VERSION,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "baselineSeason": baseline_season,
        "targetSeason": target_season,
        "methodology": {
            "baseline": f"{baseline_season} complete-season FBS team data plus opponent-adjusted Ridge ratings. This is a matchup evidence report, not a {target_season} score prediction.",
            "matchupEdge": "Each matchup metric compares the offense's national percentile with the opposing defense's national percentile for the corresponding allowed metric. A gap of at least 15 percentile points is labeled an advantage; smaller gaps are labeled EVEN.",
            "ranking": "National ranks are recomputed across published FBS season rows; rank 1 is best.",
            "limitations": [
                f"Team efficiency statistics are a {baseline_season} baseline and do not automatically account for offseason roster or coaching changes.",
                "Special teams are represented only indirectly through field position and possession outcomes.",
                "Market data is context, not model truth.",
            ],
        },
        "game": game,
        "market": market,
        "ridge": {
            "modelSeason": ridge.get("season"),
            "lambda": ridge.get("lambda"),
            "method": ridge.get("method"),
            "teamA": _ridge_summary(ridge_a),
            "teamB": _ridge_summary(ridge_b),
        },
        "teams": {
            team_a: _team_profile(team_a_season, team_a_games, all_rows, ridge_a, ridge_by_name, recent_games),
            team_b: _team_profile(team_b_season, team_b_games, all_rows, ridge_b, ridge_by_name, recent_games),
        },
        "matchups": {
            f"{_slug(team_a)}-offense-vs-{_slug(team_b)}-defense": a_offense,
            f"{_slug(team_b)}-offense-vs-{_slug(team_a)}-defense": b_offense,
        },
        "commonOpponents": _common_opponents(team_a_games, team_b_games, ridge_by_name),
        "keySignals": _key_signals(team_a, team_b, ridge_a, ridge_b, a_offense, b_offense, market),
    }

    if output_path is None:
        output_path = ROOT / "data" / "analysis" / str(target_season) / f"{_slug(team_a)}-vs-{_slug(team_b)}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    analysis["outputPath"] = str(output_path.relative_to(ROOT))
    output_path.write_text(json.dumps(analysis, indent=2) + "\n")
    return analysis


def _fmt(value: Any, fmt: str = "num") -> str:
    number = _finite(value)
    if number is None:
        return "—"
    if fmt == "pct":
        return f"{number * 100:.1f}%"
    if fmt == "int":
        return str(int(round(number)))
    return f"{number:.2f}"


def _print_ridge(team: str, ridge: dict[str, Any] | None) -> None:
    if not ridge:
        print(f"{team:<22} no Ridge data")
        return
    print(
        f"{team:<22} Overall #{ridge['overall']['rank']:<3} {ridge['overall']['rating']:>6.1f} | "
        f"Off #{ridge['offense']['rank']:<3} {ridge['offense']['rating']:>6.1f} | "
        f"Def #{ridge['defense']['rank']:<3} {ridge['defense']['rating']:>6.1f}"
    )


def _print_matchup(title: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n{title}\n{'-' * len(title)}")
    print(f"{'Metric':29} {'Offense':>18} {'Defense':>18} {'Advantage':>20}")
    for row in rows:
        offense = f"{_fmt(row['offense']['value'], row['format'])} (#{row['offense']['rank']})"
        defense = f"{_fmt(row['defense']['value'], row['format'])} (#{row['defense']['rank']})"
        print(f"{row['metric'][:29]:29} {offense:>18} {defense:>18} {row['advantage'][:20]:>20}")


def _print_recent(team: str, profile: dict[str, Any], recent_games: int) -> None:
    print(f"\n{team} — LAST {recent_games}\n{'-' * (len(team) + 10)}")
    for game in profile["gameLog"][-recent_games:]:
        score = f"{game['pointsFor']}-{game['pointsAgainst']}"
        print(
            f"Wk {str(game['week']):>2} {game['result']} vs {game['opponent']:<22} {score:<8} "
            f"SR {_fmt(game['successRate'], 'pct'):>6} YPP {_fmt(game['yardsPerPlay']):>5} "
            f"PPD {_fmt(game['pointsPerResolvedPossession']):>5} TO {str(game['turnoverMargin']):>2}"
        )


def print_analysis(analysis: dict[str, Any], team_a: str, team_b: str, recent_games: int) -> None:
    print("=" * 88)
    print(f"{team_a.upper()} vs {team_b.upper()} — FULL DATA ANALYSIS")
    print("=" * 88)
    print(f"Baseline: {analysis['baselineSeason']} | Target: {analysis['targetSeason']} | Version: {analysis['analysisVersion']}")

    game = analysis.get("game")
    if game:
        print(f"Game: Week {game.get('week')} | {game.get('startDate')} | {game.get('venue')} | Game ID {game.get('id')}")
    market = analysis.get("market")
    if market:
        spread = _finite(market.get("teamSpread"))
        spread_text = f"{team_a} {spread:+.1f}" if spread is not None else "—"
        print(f"Market: {spread_text} | {market.get('sportsbook')} | as of {market.get('asOf')} | market win chance {_fmt(market.get('marketWinChance'), 'pct')}")

    print("\nOPPONENT-ADJUSTED RIDGE\n-----------------------")
    _print_ridge(team_a, analysis["ridge"]["teamA"])
    _print_ridge(team_b, analysis["ridge"]["teamB"])

    for team in (team_a, team_b):
        profile = analysis["teams"][team]
        record = profile["record"]
        style = profile["style"]
        strength = profile["opponentStrength"]
        print(f"\n{team.upper()} PROFILE\n{'-' * (len(team) + 8)}")
        print(f"Record {record['wins']}-{record['losses']} | Rush share {_fmt(style['rushShare'], 'pct')} | Possessions/game {_fmt(style['possessionsPerGame'])} | Turnover margin {style['turnoverMargin']}")
        print(f"Avg opponent Ridge {_fmt(strength['averageOpponentRidgeRating'])} | vs Ridge top 25 {strength['recordVsTop25Ridge']['wins']}-{strength['recordVsTop25Ridge']['losses']} ({strength['top25RidgeOpponents']} games)")
        if strength.get("bestWin"):
            win = strength["bestWin"]
            print(f"Best win by opponent Ridge: {win['opponent']} {win['score']} (#{win['opponentRidgeRank']}, {win['opponentRidgeRating']:.1f})")

    matchup_keys = list(analysis["matchups"])
    _print_matchup(f"{team_a} OFFENSE vs {team_b} DEFENSE", analysis["matchups"][matchup_keys[0]])
    _print_matchup(f"{team_b} OFFENSE vs {team_a} DEFENSE", analysis["matchups"][matchup_keys[1]])

    _print_recent(team_a, analysis["teams"][team_a], recent_games)
    _print_recent(team_b, analysis["teams"][team_b], recent_games)

    print("\nCOMMON OPPONENTS\n----------------")
    common = analysis.get("commonOpponents") or []
    if not common:
        print("None in the baseline season.")
    for row in common:
        a = row["teamA"]
        b = row["teamB"]
        print(f"{row['opponent']}: {team_a} {a['result']} {a['pointsFor']}-{a['pointsAgainst']} | {team_b} {b['result']} {b['pointsFor']}-{b['pointsAgainst']}")

    print("\nTOP ARTICLE SIGNALS\n-------------------")
    for signal in analysis.get("keySignals", [])[:12]:
        print(f"- {signal['text']}")

    print("\nIMPORTANT\n---------")
    for limitation in analysis["methodology"]["limitations"]:
        print(f"- {limitation}")
    print(f"\nSaved full JSON: {analysis.get('outputPath', '—')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a full evidence-based college football matchup analysis from published repo data.")
    parser.add_argument("--team-a", default="Michigan")
    parser.add_argument("--team-b", default="Western Michigan")
    parser.add_argument("--baseline-season", type=int, default=2025)
    parser.add_argument("--target-season", type=int, default=2026)
    parser.add_argument("--recent-games", type=int, default=5)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--print-json", action="store_true", help="Print the full JSON after the readable report.")
    args = parser.parse_args(argv)

    analysis = build_matchup_analysis(
        args.team_a,
        args.team_b,
        baseline_season=args.baseline_season,
        target_season=args.target_season,
        recent_games=args.recent_games,
        output_path=args.output,
    )
    print_analysis(analysis, args.team_a, args.team_b, args.recent_games)
    if args.print_json:
        print("\nFULL JSON\n---------")
        print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
