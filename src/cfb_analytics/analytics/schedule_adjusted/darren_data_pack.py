from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .dataset import collect_published_team_games, fit_metric_from_rows, venue_from_team_game
from .game_analysis import VALIDATED_GAME_METRICS
from .model import ScheduleAdjustedResult
from .specs import METRIC_SPECS, MetricSpec

DARREN_DATA_PACK_VERSION = "darren-data-pack-v1"
DEFAULT_RIDGE = 40.0
DEFAULT_HOME_RIDGE = 20.0

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PUBLISHED_ROOT = REPO_ROOT / "data" / "published"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "exports" / "darren"

# These five metrics have the strongest historical schedule-adjusted validation in
# this repository and should be used for primary strength claims.
VALIDATED_METRICS: tuple[str, ...] = tuple(VALIDATED_GAME_METRICS)

# Useful opponent-adjusted context for a scouting packet. These are intentionally
# labeled research-only in every output because they have not completed the same
# historical validation suite as VALIDATED_METRICS.
RESEARCH_METRICS: tuple[str, ...] = (
    "rushExplosivePlayRate",
    "passExplosivePlayRate",
    "rushYardsPerAttempt",
    "netPassYardsPerDropback",
    "standardDownSuccessRate",
    "passingDownSuccessRate",
    "thirdDownConversionRate",
    "sackRate",
    "havocRateAllowed",
)

ALL_PACK_METRICS: tuple[str, ...] = VALIDATED_METRICS + RESEARCH_METRICS

DEFENSE_VALUE_FIELDS: dict[str, str] = {
    "successRate": "successRateAllowed",
    "rushSuccessRate": "rushSuccessRateAllowed",
    "passSuccessRate": "passSuccessRateAllowed",
    "explosivePlayRate": "explosivePlayRateAllowed",
    "yardsPerPlay": "yardsPerPlayAllowed",
}


@dataclass(frozen=True)
class TeamRef:
    id: str
    name: str
    slug: str
    conference: str
    classification: str


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _team_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("team_id")
    if value is not None and not isinstance(value, bool):
        return str(value)
    name = row.get("team")
    return str(name) if isinstance(name, str) and name.strip() else None


def _opponent_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("opponent_id")
    if value is not None and not isinstance(value, bool):
        return str(value)
    name = row.get("opponent")
    return str(name) if isinstance(name, str) and name.strip() else None


def _game_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("gameId", row.get("game_id"))
    return str(value) if value is not None else None


def _phase_order(row: Mapping[str, Any]) -> int:
    season_type = str(row.get("seasonType", row.get("season_type", "regular")) or "regular").lower()
    phase = 0 if season_type in {"regular", "regular_season"} else 1
    week = row.get("week")
    resolved_week = int(week) if isinstance(week, int) else 99
    return phase * 100 + resolved_week


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "team"


def _team_catalog(rows: Iterable[Mapping[str, Any]]) -> dict[str, TeamRef]:
    catalog: dict[str, TeamRef] = {}
    for row in rows:
        team_id = _team_id(row)
        if team_id is None:
            continue
        name = str(row.get("team") or team_id)
        catalog.setdefault(
            team_id,
            TeamRef(
                id=team_id,
                name=name,
                slug=str(row.get("team_slug") or _slug(name)),
                conference=str(row.get("conference") or ""),
                classification=str(row.get("classification") or ""),
            ),
        )
    return catalog


def resolve_team(rows: Sequence[Mapping[str, Any]], query: str) -> TeamRef:
    query = str(query).strip()
    if not query:
        raise ValueError("team query cannot be empty")
    catalog = _team_catalog(rows)
    lowered = query.lower()

    exact = [
        team
        for team in catalog.values()
        if lowered in {team.id.lower(), team.name.lower(), team.slug.lower()}
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [
        team
        for team in catalog.values()
        if lowered in team.name.lower() or lowered in team.slug.lower()
    ]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ValueError(f"could not resolve team {query!r}")
    options = ", ".join(sorted(team.name for team in partial[:12]))
    raise ValueError(f"team query {query!r} is ambiguous: {options}")


def _valid_team_rows(rows: Iterable[Mapping[str, Any]], team_id: str) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for row in rows:
        if _team_id(row) != team_id:
            continue
        if row.get("gameValidationStatus") not in (None, "PASS"):
            continue
        out.append(row)
    return sorted(out, key=lambda row: (_phase_order(row), _game_id(row) or ""))


def _sum(rows: Iterable[Mapping[str, Any]], field: str) -> float:
    total = 0.0
    for row in rows:
        value = _number(row.get(field))
        if value is not None:
            total += value
    return total


def _ratio(rows: Sequence[Mapping[str, Any]], numerator: str, denominator: str) -> float | None:
    den = _sum(rows, denominator)
    if den <= 0:
        return None
    return _sum(rows, numerator) / den


def _per_game(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    return _sum(rows, field) / len(rows)


def _decision_share(
    rows: Sequence[Mapping[str, Any]],
    rush_field: str,
    dropback_field: str,
) -> tuple[float | None, float | None]:
    rushes = _sum(rows, rush_field)
    dropbacks = _sum(rows, dropback_field)
    total = rushes + dropbacks
    if total <= 0:
        return None, None
    return rushes / total, dropbacks / total


def build_tendencies(rows: Sequence[Mapping[str, Any]], team_id: str) -> dict[str, Any]:
    games = _valid_team_rows(rows, team_id)
    rush_share, dropback_share = _decision_share(games, "rushAttempts", "dropbacks")
    opp_rush_share, opp_dropback_share = _decision_share(games, "rushAttemptsFaced", "dropbacksFaced")

    standard = _sum(games, "standardDownPlays")
    passing = _sum(games, "passingDownPlays")
    down_total = standard + passing
    standard_share = standard / down_total if down_total > 0 else None
    passing_share = passing / down_total if down_total > 0 else None

    wins = int(round(_sum(games, "win")))
    losses = int(round(_sum(games, "loss")))

    return {
        "games": len(games),
        "wins": wins,
        "losses": losses,
        "offense": {
            "pointsPerGame": _per_game(games, "points_for"),
            "playsPerGame": _per_game(games, "offensivePlays"),
            "possessionsPerGame": _per_game(games, "possessions"),
            "rushAttemptsPerGame": _per_game(games, "rushAttempts"),
            "dropbacksPerGame": _per_game(games, "dropbacks"),
            "rushDecisionRate": rush_share,
            "dropbackRate": dropback_share,
            "standardDownShare": standard_share,
            "passingDownShare": passing_share,
            "successRate": _ratio(games, "successfulPlays", "successEligiblePlays"),
            "rushSuccessRate": _ratio(games, "rushSuccessfulPlays", "rushSuccessEligiblePlays"),
            "passSuccessRate": _ratio(games, "passSuccessfulPlays", "passSuccessEligiblePlays"),
            "explosivePlayRate": _ratio(games, "explosivePlays", "explosiveEligiblePlays"),
            "rushExplosivePlayRate": _ratio(games, "rushExplosivePlays", "rushExplosiveEligiblePlays"),
            "passExplosivePlayRate": _ratio(games, "passExplosivePlays", "passExplosiveEligiblePlays"),
            "yardsPerPlay": _ratio(games, "basicYardageYards", "basicYardagePlays"),
            "rushYardsPerAttempt": _ratio(games, "rushYards", "rushAttempts"),
            "netPassYardsPerDropback": _ratio(games, "netPassYards", "dropbacks"),
            "standardDownSuccessRate": _ratio(games, "standardDownSuccesses", "standardDownPlays"),
            "passingDownSuccessRate": _ratio(games, "passingDownSuccesses", "passingDownPlays"),
            "thirdDownConversionRate": _ratio(games, "thirdDownConversions", "thirdDownAttempts"),
            "sackRateAllowed": _ratio(games, "sacksAllowed", "dropbacks"),
            "havocRateAllowed": _ratio(games, "havocPlaysAllowed", "havocEligiblePlays"),
        },
        "defense": {
            "pointsAllowedPerGame": _per_game(games, "points_against"),
            "playsFacedPerGame": _per_game(games, "defensivePlays"),
            "possessionsFacedPerGame": _per_game(games, "possessionsAllowed"),
            "opponentRushAttemptsPerGame": _per_game(games, "rushAttemptsFaced"),
            "opponentDropbacksPerGame": _per_game(games, "dropbacksFaced"),
            "opponentRushDecisionRate": opp_rush_share,
            "opponentDropbackRate": opp_dropback_share,
            "successRateAllowed": _ratio(games, "successfulPlaysAllowed", "successEligiblePlaysAllowed"),
            "rushSuccessRateAllowed": _ratio(games, "rushSuccessfulPlaysAllowed", "rushSuccessEligiblePlaysAllowed"),
            "passSuccessRateAllowed": _ratio(games, "passSuccessfulPlaysAllowed", "passSuccessEligiblePlaysAllowed"),
            "explosivePlayRateAllowed": _ratio(games, "explosivePlaysAllowed", "explosiveEligiblePlaysAllowed"),
            "rushExplosivePlayRateAllowed": _ratio(games, "rushExplosivePlaysAllowed", "rushExplosiveEligiblePlaysAllowed"),
            "passExplosivePlayRateAllowed": _ratio(games, "passExplosivePlaysAllowed", "passExplosiveEligiblePlaysAllowed"),
            "yardsPerPlayAllowed": _ratio(games, "basicYardageYardsAllowed", "basicYardagePlaysFaced"),
            "rushYardsPerAttemptAllowed": _ratio(games, "rushYardsAllowed", "rushAttemptsFaced"),
            "netPassYardsPerDropbackAllowed": _ratio(games, "netPassYardsAllowed", "dropbacksFaced"),
            "thirdDownConversionRateAllowed": _ratio(games, "thirdDownConversionsAllowed", "thirdDownAttemptsAllowed"),
            "sackRateGenerated": _ratio(games, "sacks", "dropbacksFaced"),
            "havocRateGenerated": _ratio(games, "havocPlays", "havocEligiblePlaysFaced"),
        },
    }


def _fbs_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        team.id
        for team in _team_catalog(rows).values()
        if team.classification.lower() == "fbs"
    }


def _rankings(
    result: ScheduleAdjustedResult,
    fbs_ids: set[str],
    perspective: str,
) -> tuple[dict[str, int], int]:
    ordered = result.offense_rankings() if perspective == "offense" else result.defense_rankings()
    filtered = [row for row in ordered if row.team in fbs_ids]
    return {row.team: rank for rank, row in enumerate(filtered, 1)}, len(filtered)


def _metric_entry(
    result: ScheduleAdjustedResult,
    metric: str,
    subject: TeamRef,
    comparison: TeamRef | None,
    fbs_ids: set[str],
) -> dict[str, Any]:
    off_ranks, off_n = _rankings(result, fbs_ids, "offense")
    def_ranks, def_n = _rankings(result, fbs_ids, "defense")

    def team_values(team: TeamRef | None) -> dict[str, Any] | None:
        if team is None:
            return None
        return {
            "id": team.id,
            "name": team.name,
            "offense": {
                "adjustedValue": result.adjusted_offense_value(team.id) if team.id in result.teams else None,
                "rank": off_ranks.get(team.id),
                "fieldSize": off_n,
                "exposure": result.offense_exposure.get(team.id),
            },
            "defense": {
                "adjustedValue": result.adjusted_defense_value(team.id) if team.id in result.teams else None,
                "rank": def_ranks.get(team.id),
                "fieldSize": def_n,
                "exposure": result.defense_exposure.get(team.id),
            },
        }

    spec = METRIC_SPECS[metric]
    return {
        "metric": metric,
        "label": spec.label,
        "unit": spec.unit,
        "family": spec.family,
        "validation": "validated" if metric in VALIDATED_METRICS else "research-only",
        "leagueAverageRaw": result.league_average_raw(),
        "subject": team_values(subject),
        "comparison": team_values(comparison),
        "model": {
            "definitionVersion": result.definition_version,
            "ridge": result.ridge,
            "homeRidge": result.home_ridge,
            "homeFieldEffect": result.home_field_effect,
            "converged": result.converged,
            "observations": result.n_observations,
        },
    }


def fit_pack_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    season: int,
    subject: TeamRef,
    comparison: TeamRef | None,
    ridge: float,
    home_ridge: float,
    metric_names: Sequence[str] = ALL_PACK_METRICS,
) -> tuple[list[dict[str, Any]], dict[str, ScheduleAdjustedResult]]:
    fbs_ids = _fbs_ids(rows)
    entries: list[dict[str, Any]] = []
    results: dict[str, ScheduleAdjustedResult] = {}
    for metric in metric_names:
        print(f"  fitting {metric}", flush=True)
        result = fit_metric_from_rows(
            rows,
            metric,
            season=season,
            ridge=ridge,
            fit_home_field=True,
            home_ridge=home_ridge,
        )
        results[metric] = result
        entries.append(_metric_entry(result, metric, subject, comparison, fbs_ids))
    return entries, results


def _percentile(rank: int | None, field_size: int) -> float | None:
    if rank is None or field_size <= 0:
        return None
    if field_size == 1:
        return 100.0
    return 100.0 * (field_size - rank) / (field_size - 1)


def build_composites(
    rows: Sequence[Mapping[str, Any]],
    results: Mapping[str, ScheduleAdjustedResult],
) -> dict[str, dict[str, Any]]:
    catalog = _team_catalog(rows)
    fbs = {team_id: team for team_id, team in catalog.items() if team.classification.lower() == "fbs"}
    accum: dict[str, dict[str, list[float]]] = {
        team_id: {"offense": [], "defense": []} for team_id in fbs
    }

    for metric in VALIDATED_METRICS:
        result = results[metric]
        off_ranks, off_n = _rankings(result, set(fbs), "offense")
        def_ranks, def_n = _rankings(result, set(fbs), "defense")
        for team_id in fbs:
            off_score = _percentile(off_ranks.get(team_id), off_n)
            def_score = _percentile(def_ranks.get(team_id), def_n)
            if off_score is not None:
                accum[team_id]["offense"].append(off_score)
            if def_score is not None:
                accum[team_id]["defense"].append(def_score)

    profiles: dict[str, dict[str, Any]] = {}
    for team_id, team in fbs.items():
        offense_values = accum[team_id]["offense"]
        defense_values = accum[team_id]["defense"]
        oscore = sum(offense_values) / len(offense_values) if offense_values else None
        dscore = sum(defense_values) / len(defense_values) if defense_values else None
        overall = (oscore + dscore) / 2 if oscore is not None and dscore is not None else None
        profiles[team_id] = {
            "id": team_id,
            "name": team.name,
            "conference": team.conference,
            "offenseScore": oscore,
            "defenseScore": dscore,
            "overallScore": overall,
        }

    for score_key, rank_key, field_key in (
        ("offenseScore", "offenseRank", "offenseFieldSize"),
        ("defenseScore", "defenseRank", "defenseFieldSize"),
        ("overallScore", "overallRank", "overallFieldSize"),
    ):
        ordered = sorted(
            (row for row in profiles.values() if row[score_key] is not None),
            key=lambda row: (-float(row[score_key]), row["name"]),
        )
        for rank, row in enumerate(ordered, 1):
            row[rank_key] = rank
            row[field_key] = len(ordered)
    return profiles


def _raw_metric(row: Mapping[str, Any], spec: MetricSpec) -> float | None:
    numerator = spec.numerator_value(row)
    denominator = _number(row.get(spec.denominator_field))
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _loo_metric_for_game(
    row: Mapping[str, Any],
    result: ScheduleAdjustedResult,
    metric: str,
) -> dict[str, Any]:
    spec = METRIC_SPECS[metric]
    team_id = _team_id(row)
    opponent_id = _opponent_id(row)
    if team_id is None or opponent_id is None:
        return {"offense": None, "defense": None}
    venue = venue_from_team_game(row)

    offense_actual = _raw_metric(row, spec)
    offense_expected = (
        result.expected_raw(team_id, opponent_id, venue)
        if offense_actual is not None
        else None
    )
    offense_poe = (
        (offense_actual - offense_expected) * spec.orientation
        if offense_actual is not None and offense_expected is not None
        else None
    )

    defense_actual = _number(row.get(DEFENSE_VALUE_FIELDS[metric]))
    defense_expected = (
        result.expected_raw(opponent_id, team_id, -venue)
        if defense_actual is not None
        else None
    )
    defense_poe = (
        -(defense_actual - defense_expected) * spec.orientation
        if defense_actual is not None and defense_expected is not None
        else None
    )

    return {
        "offense": {
            "actual": offense_actual,
            "expected": offense_expected,
            "poe": offense_poe,
            "supported": (
                result.offense_exposure.get(team_id, 0.0) > 0
                and result.defense_exposure.get(opponent_id, 0.0) > 0
            ),
        },
        "defense": {
            "actual": defense_actual,
            "expected": defense_expected,
            "poe": defense_poe,
            "supported": (
                result.defense_exposure.get(team_id, 0.0) > 0
                and result.offense_exposure.get(opponent_id, 0.0) > 0
            ),
        },
    }


def build_game_breakdown(
    rows: Sequence[Mapping[str, Any]],
    *,
    season: int,
    subject: TeamRef,
    composites: Mapping[str, Mapping[str, Any]],
    ridge: float,
    home_ridge: float,
) -> list[dict[str, Any]]:
    games = _valid_team_rows(rows, subject.id)
    out: list[dict[str, Any]] = []

    for index, row in enumerate(games, 1):
        game_id = _game_id(row)
        opponent_id = _opponent_id(row)
        if game_id is None or opponent_id is None:
            continue
        print(f"  LOO game {index}/{len(games)}: {row.get('opponent')} ({game_id})", flush=True)
        metric_payload: dict[str, Any] = {}
        for metric in VALIDATED_METRICS:
            result = fit_metric_from_rows(
                rows,
                metric,
                season=season,
                exclude_game_ids=(game_id,),
                ridge=ridge,
                fit_home_field=True,
                home_ridge=home_ridge,
            )
            metric_payload[metric] = _loo_metric_for_game(row, result, metric)

        opponent_profile = composites.get(opponent_id)
        pf = _number(row.get("points_for"))
        pa = _number(row.get("points_against"))
        if pf is None or pa is None:
            result_text = ""
        elif pf > pa:
            result_text = "W"
        elif pf < pa:
            result_text = "L"
        else:
            result_text = "T"

        out.append(
            {
                "gameId": game_id,
                "week": row.get("week"),
                "seasonType": str(row.get("seasonType", row.get("season_type", "regular")) or "regular"),
                "homeAway": str(row.get("home_away") or ""),
                "neutralSite": bool(row.get("neutral_site")),
                "opponent": {
                    "id": opponent_id,
                    "name": str(row.get("opponent") or opponent_id),
                    "classification": str(row.get("opponent_classification") or ""),
                    "conference": str(row.get("opponent_conference") or ""),
                    "adjustedProfile": dict(opponent_profile) if opponent_profile is not None else None,
                },
                "score": {
                    "result": result_text,
                    "pointsFor": pf,
                    "pointsAgainst": pa,
                },
                "metrics": metric_payload,
            }
        )
    return out


def _format_value(value: Any, unit: str = "") -> str:
    number = _number(value)
    if number is None:
        return "—"
    if unit == "rate":
        return f"{number * 100:.1f}%"
    return f"{number:.2f}"


def _format_rank(rank: Any, field_size: Any) -> str:
    if not isinstance(rank, int) or not isinstance(field_size, int):
        return "—"
    return f"#{rank}/{field_size}"


def _flat_tendency_rows(
    subject: TeamRef,
    comparison: TeamRef | None,
    subject_t: Mapping[str, Any],
    comparison_t: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    definitions = (
        ("offense", "pointsPerGame", "Points/game", "number"),
        ("offense", "playsPerGame", "Offensive plays/game", "number"),
        ("offense", "possessionsPerGame", "Possessions/game", "number"),
        ("offense", "rushAttemptsPerGame", "Rush attempts/game", "number"),
        ("offense", "dropbacksPerGame", "Dropbacks/game", "number"),
        ("offense", "rushDecisionRate", "Rush decision rate", "rate"),
        ("offense", "dropbackRate", "Dropback rate", "rate"),
        ("offense", "standardDownShare", "Standard-down share", "rate"),
        ("offense", "passingDownShare", "Passing-down share", "rate"),
        ("offense", "successRate", "Raw success rate", "rate"),
        ("offense", "rushSuccessRate", "Raw rush success rate", "rate"),
        ("offense", "passSuccessRate", "Raw pass success rate", "rate"),
        ("offense", "explosivePlayRate", "Raw explosive rate", "rate"),
        ("offense", "rushExplosivePlayRate", "Raw rush explosive rate", "rate"),
        ("offense", "passExplosivePlayRate", "Raw pass explosive rate", "rate"),
        ("offense", "yardsPerPlay", "Raw yards/play", "number"),
        ("offense", "rushYardsPerAttempt", "Raw rush YPA", "number"),
        ("offense", "netPassYardsPerDropback", "Raw net pass Y/dropback", "number"),
        ("offense", "thirdDownConversionRate", "Raw third-down conversion", "rate"),
        ("offense", "sackRateAllowed", "Sack rate allowed", "rate"),
        ("offense", "havocRateAllowed", "Havoc rate allowed", "rate"),
        ("defense", "pointsAllowedPerGame", "Points allowed/game", "number"),
        ("defense", "playsFacedPerGame", "Defensive plays/game", "number"),
        ("defense", "opponentRushDecisionRate", "Opponent rush decision rate", "rate"),
        ("defense", "opponentDropbackRate", "Opponent dropback rate", "rate"),
        ("defense", "successRateAllowed", "Raw success rate allowed", "rate"),
        ("defense", "rushSuccessRateAllowed", "Raw rush success allowed", "rate"),
        ("defense", "passSuccessRateAllowed", "Raw pass success allowed", "rate"),
        ("defense", "explosivePlayRateAllowed", "Raw explosive rate allowed", "rate"),
        ("defense", "rushExplosivePlayRateAllowed", "Raw rush explosive allowed", "rate"),
        ("defense", "passExplosivePlayRateAllowed", "Raw pass explosive allowed", "rate"),
        ("defense", "yardsPerPlayAllowed", "Raw yards/play allowed", "number"),
        ("defense", "rushYardsPerAttemptAllowed", "Raw rush YPA allowed", "number"),
        ("defense", "netPassYardsPerDropbackAllowed", "Raw net pass Y/dropback allowed", "number"),
        ("defense", "thirdDownConversionRateAllowed", "Raw third-down conversion allowed", "rate"),
        ("defense", "sackRateGenerated", "Sack rate generated", "rate"),
        ("defense", "havocRateGenerated", "Havoc rate generated", "rate"),
    )
    output = []
    for section, key, label, unit in definitions:
        output.append(
            {
                "section": section,
                "metric": key,
                "label": label,
                "unit": unit,
                "subjectTeam": subject.name,
                "subjectValue": subject_t[section].get(key),
                "comparisonTeam": comparison.name if comparison else None,
                "comparisonValue": comparison_t[section].get(key) if comparison_t else None,
            }
        )
    return output


def _markdown(
    payload: Mapping[str, Any],
    adjusted: Sequence[Mapping[str, Any]],
    tendency_rows: Sequence[Mapping[str, Any]],
    game_rows: Sequence[Mapping[str, Any]],
) -> str:
    subject = payload["subject"]
    comparison = payload.get("comparison")
    season = payload["season"]
    compare_name = comparison["name"] if comparison else "Comparison"
    lines = [
        f"# Darren Data Pack — {subject['name']} ({season})",
        "",
        f"Generated by `{DARREN_DATA_PACK_VERSION}` from the repository's published team-game contracts.",
        f"Schedule-adjusted model: `schedule-adjusted-ratings-v1`, ridge {payload['ridge']:.0f}, home ridge {payload['homeRidge']:.0f}.",
        "",
        "## How to read this file",
        "",
        "- **Validated** = metric has passed the repository's historical schedule-adjusted validation suite and is appropriate for primary strength claims.",
        "- **Research-only** = same opponent-adjusted model and locked production definition, but not yet validated to the same standard. Use as supporting context, not as the lone proof of a claim.",
        "- **Adjusted offense value** = expected raw production for this offense against an average defense at a neutral site.",
        "- **Adjusted defense value** = expected raw production by an average offense against this defense at a neutral site. The national defense rank is oriented so #1 is best defense.",
        "- **Rush decision rate** uses `rushAttempts / (rushAttempts + dropbacks)`. Dropbacks include sacks; this is intentionally not labeled official pass-attempt rate.",
        "- **Game POE** is strict leave-one-game-out: the target game is removed before fitting expected performance. Positive POE is good for the selected team on both offense and defense.",
        "- Rate metrics are weighted from locked numerators/denominators, never averaged game-by-game.",
        "",
        "## Team",
        "",
        f"- Team: **{subject['name']}**",
        f"- Conference: {subject.get('conference') or '—'}",
        f"- Comparison: **{comparison['name']}**" if comparison else "- Comparison: none",
        f"- Games in raw tendency sample: {payload['tendencies']['subject']['games']}",
        f"- Record in sample: {payload['tendencies']['subject']['wins']}-{payload['tendencies']['subject']['losses']}",
        "",
        "## Raw tendencies and production",
        "",
        f"| Split | Metric | {subject['name']} | {compare_name} |",
        "|---|---|---:|---:|",
    ]
    for row in tendency_rows:
        unit = "rate" if row["unit"] == "rate" else ""
        lines.append(
            f"| {row['section'].title()} | {row['label']} | {_format_value(row['subjectValue'], unit)} | {_format_value(row['comparisonValue'], unit)} |"
        )

    adjusted_header = (
        f"| Tier | Metric | {subject['name']} offense | Off rank | {subject['name']} defense | Def rank |"
    )
    adjusted_rule = "|---|---|---:|---:|---:|---:|"
    if comparison:
        adjusted_header += f" {comparison['name']} offense | Off rank | {comparison['name']} defense | Def rank |"
        adjusted_rule += "---:|---:|---:|---:|"
    lines.extend(["", "## Opponent-adjusted strengths", "", adjusted_header, adjusted_rule])

    for entry in adjusted:
        spec_unit = entry["unit"]
        sub = entry["subject"]
        comp = entry.get("comparison")
        cells = [
            entry["validation"],
            entry["label"],
            _format_value(sub["offense"]["adjustedValue"], spec_unit),
            _format_rank(sub["offense"]["rank"], sub["offense"]["fieldSize"]),
            _format_value(sub["defense"]["adjustedValue"], spec_unit),
            _format_rank(sub["defense"]["rank"], sub["defense"]["fieldSize"]),
        ]
        if comparison and comp:
            cells.extend(
                [
                    _format_value(comp["offense"]["adjustedValue"], spec_unit),
                    _format_rank(comp["offense"]["rank"], comp["offense"]["fieldSize"]),
                    _format_value(comp["defense"]["adjustedValue"], spec_unit),
                    _format_rank(comp["defense"]["rank"], comp["defense"]["fieldSize"]),
                ]
            )
        lines.append("| " + " | ".join(cells) + " |")

    subject_profile = payload["composites"].get(subject["id"])
    comparison_profile = payload["composites"].get(comparison["id"]) if comparison else None
    lines.extend(["", "## Validated-five composite context", ""])
    if subject_profile:
        lines.extend(
            [
                f"- {subject['name']} offense composite: {subject_profile['offenseScore']:.1f}/100, national rank #{subject_profile['offenseRank']}.",
                f"- {subject['name']} defense composite: {subject_profile['defenseScore']:.1f}/100, national rank #{subject_profile['defenseRank']}.",
                f"- {subject['name']} overall composite: {subject_profile['overallScore']:.1f}/100, national rank #{subject_profile['overallRank']}.",
            ]
        )
    if comparison_profile:
        lines.extend(
            [
                f"- {comparison['name']} offense composite: {comparison_profile['offenseScore']:.1f}/100, national rank #{comparison_profile['offenseRank']}.",
                f"- {comparison['name']} defense composite: {comparison_profile['defenseScore']:.1f}/100, national rank #{comparison_profile['defenseRank']}.",
                f"- {comparison['name']} overall composite: {comparison_profile['overallScore']:.1f}/100, national rank #{comparison_profile['overallRank']}.",
            ]
        )

    lines.extend(
        [
            "",
            "## Schedule and opponent strength",
            "",
            "| Week | Opponent | Site | Score | Opp adj offense | Opp adj defense | Opp overall |",
            "|---:|---|---|---:|---:|---:|---:|",
        ]
    )
    for game in game_rows:
        opp = game["opponent"]
        profile = opp.get("adjustedProfile")
        if game.get("neutralSite"):
            site = "N"
        else:
            site = {"home": "H", "away": "A"}.get(str(game.get("homeAway")).lower(), "—")
        score = game["score"]
        score_text = (
            f"{score['result']} {int(score['pointsFor'])}-{int(score['pointsAgainst'])}"
            if score["pointsFor"] is not None and score["pointsAgainst"] is not None
            else "—"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(game.get("week") if game.get("week") is not None else "—"),
                    opp["name"],
                    site,
                    score_text,
                    f"#{profile['offenseRank']}" if profile and profile.get("offenseRank") else "—",
                    f"#{profile['defenseRank']}" if profile and profile.get("defenseRank") else "—",
                    f"#{profile['overallRank']}" if profile and profile.get("overallRank") else "—",
                ]
            )
            + " |"
        )

    if game_rows and any(game.get("metrics") for game in game_rows):
        label_map = {
            "successRate": "Success",
            "rushSuccessRate": "Rush SR",
            "passSuccessRate": "Pass SR",
            "explosivePlayRate": "Explosive",
            "yardsPerPlay": "YPP",
        }
        lines.extend(
            [
                "",
                "## Game-by-game leave-one-out offense POE",
                "",
                "| Week | Opponent | " + " | ".join(label_map[m] for m in VALIDATED_METRICS) + " |",
                "|---:|---|" + "|".join("---:" for _ in VALIDATED_METRICS) + "|",
            ]
        )
        for game in game_rows:
            values = []
            for metric in VALIDATED_METRICS:
                item = game["metrics"].get(metric, {}).get("offense")
                value = item.get("poe") if item else None
                values.append(_format_value(value, METRIC_SPECS[metric].unit))
            lines.append(
                f"| {game.get('week', '—')} | {game['opponent']['name']} | " + " | ".join(values) + " |"
            )

        lines.extend(
            [
                "",
                "## Game-by-game leave-one-out defense POE",
                "",
                "| Week | Opponent | " + " | ".join(label_map[m] for m in VALIDATED_METRICS) + " |",
                "|---:|---|" + "|".join("---:" for _ in VALIDATED_METRICS) + "|",
            ]
        )
        for game in game_rows:
            values = []
            for metric in VALIDATED_METRICS:
                item = game["metrics"].get(metric, {}).get("defense")
                value = item.get("poe") if item else None
                values.append(_format_value(value, METRIC_SPECS[metric].unit))
            lines.append(
                f"| {game.get('week', '—')} | {game['opponent']['name']} | " + " | ".join(values) + " |"
            )

    lines.extend(
        [
            "",
            "## Data-quality guardrails",
            "",
            "- Only team-game rows with `gameValidationStatus` absent or `PASS` enter the raw tendency sample.",
            "- Primary opponent-adjusted claims should use the five validated metrics.",
            "- Research-only adjusted metrics are deliberately labeled and should be corroborated before publication.",
            "- No staff, roster, scheme, transfer, injury, or depth-chart claims are generated here. Those require dated external sourcing and should be merged into the final scouting dossier separately.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def write_pack(
    *,
    output_root: Path,
    season: int,
    subject: TeamRef,
    comparison: TeamRef | None,
    tendencies_subject: Mapping[str, Any],
    tendencies_comparison: Mapping[str, Any] | None,
    adjusted: Sequence[Mapping[str, Any]],
    composites: Mapping[str, Mapping[str, Any]],
    games: Sequence[Mapping[str, Any]],
    ridge: float,
    home_ridge: float,
) -> dict[str, Path]:
    output_dir = output_root / str(season) / subject.slug
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": DARREN_DATA_PACK_VERSION,
        "season": season,
        "ridge": ridge,
        "homeRidge": home_ridge,
        "subject": {
            "id": subject.id,
            "name": subject.name,
            "slug": subject.slug,
            "conference": subject.conference,
            "classification": subject.classification,
        },
        "comparison": (
            {
                "id": comparison.id,
                "name": comparison.name,
                "slug": comparison.slug,
                "conference": comparison.conference,
                "classification": comparison.classification,
            }
            if comparison
            else None
        ),
        "validation": {
            "validatedMetrics": list(VALIDATED_METRICS),
            "researchOnlyMetrics": list(RESEARCH_METRICS),
        },
        "tendencies": {
            "subject": tendencies_subject,
            "comparison": tendencies_comparison,
        },
        "adjustedMetrics": list(adjusted),
        "composites": dict(composites),
        "games": list(games),
    }

    tendency_rows = _flat_tendency_rows(
        subject,
        comparison,
        tendencies_subject,
        tendencies_comparison,
    )

    json_path = output_dir / "darren-data-pack.json"
    md_path = output_dir / "darren-data-pack.md"
    tendency_path = output_dir / "tendencies.csv"
    adjusted_path = output_dir / "adjusted-metrics.csv"
    games_path = output_dir / "game-poe.csv"
    schedule_path = output_dir / "schedule-strength.csv"

    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    md_path.write_text(_markdown(payload, adjusted, tendency_rows, games))

    _write_csv(
        tendency_path,
        tendency_rows,
        (
            "section",
            "metric",
            "label",
            "unit",
            "subjectTeam",
            "subjectValue",
            "comparisonTeam",
            "comparisonValue",
        ),
    )

    adjusted_rows: list[dict[str, Any]] = []
    for entry in adjusted:
        sub = entry["subject"]
        comp = entry.get("comparison") or {}
        adjusted_rows.append(
            {
                "validation": entry["validation"],
                "metric": entry["metric"],
                "label": entry["label"],
                "unit": entry["unit"],
                "leagueAverageRaw": entry["leagueAverageRaw"],
                "subjectTeam": sub["name"],
                "subjectOffenseAdjustedValue": sub["offense"]["adjustedValue"],
                "subjectOffenseRank": sub["offense"]["rank"],
                "subjectDefenseAdjustedValue": sub["defense"]["adjustedValue"],
                "subjectDefenseRank": sub["defense"]["rank"],
                "comparisonTeam": comp.get("name"),
                "comparisonOffenseAdjustedValue": (comp.get("offense") or {}).get("adjustedValue"),
                "comparisonOffenseRank": (comp.get("offense") or {}).get("rank"),
                "comparisonDefenseAdjustedValue": (comp.get("defense") or {}).get("adjustedValue"),
                "comparisonDefenseRank": (comp.get("defense") or {}).get("rank"),
            }
        )
    _write_csv(
        adjusted_path,
        adjusted_rows,
        (
            "validation",
            "metric",
            "label",
            "unit",
            "leagueAverageRaw",
            "subjectTeam",
            "subjectOffenseAdjustedValue",
            "subjectOffenseRank",
            "subjectDefenseAdjustedValue",
            "subjectDefenseRank",
            "comparisonTeam",
            "comparisonOffenseAdjustedValue",
            "comparisonOffenseRank",
            "comparisonDefenseAdjustedValue",
            "comparisonDefenseRank",
        ),
    )

    game_csv_rows: list[dict[str, Any]] = []
    schedule_csv_rows: list[dict[str, Any]] = []
    for game in games:
        opp = game["opponent"]
        profile = opp.get("adjustedProfile") or {}
        schedule_csv_rows.append(
            {
                "week": game.get("week"),
                "seasonType": game.get("seasonType"),
                "opponent": opp["name"],
                "opponentConference": opp.get("conference"),
                "homeAway": game.get("homeAway"),
                "neutralSite": game.get("neutralSite"),
                "result": game["score"].get("result"),
                "pointsFor": game["score"].get("pointsFor"),
                "pointsAgainst": game["score"].get("pointsAgainst"),
                "opponentAdjustedOffenseRank": profile.get("offenseRank"),
                "opponentAdjustedDefenseRank": profile.get("defenseRank"),
                "opponentAdjustedOverallRank": profile.get("overallRank"),
                "opponentAdjustedOffenseScore": profile.get("offenseScore"),
                "opponentAdjustedDefenseScore": profile.get("defenseScore"),
                "opponentAdjustedOverallScore": profile.get("overallScore"),
            }
        )
        for metric in VALIDATED_METRICS:
            metric_row = game.get("metrics", {}).get(metric, {})
            for perspective in ("offense", "defense"):
                item = metric_row.get(perspective)
                if not item:
                    continue
                game_csv_rows.append(
                    {
                        "week": game.get("week"),
                        "gameId": game.get("gameId"),
                        "opponent": opp["name"],
                        "perspective": perspective,
                        "metric": metric,
                        "actual": item.get("actual"),
                        "expectedLOO": item.get("expected"),
                        "poe": item.get("poe"),
                        "supported": item.get("supported"),
                    }
                )

    _write_csv(
        games_path,
        game_csv_rows,
        ("week", "gameId", "opponent", "perspective", "metric", "actual", "expectedLOO", "poe", "supported"),
    )
    _write_csv(
        schedule_path,
        schedule_csv_rows,
        (
            "week",
            "seasonType",
            "opponent",
            "opponentConference",
            "homeAway",
            "neutralSite",
            "result",
            "pointsFor",
            "pointsAgainst",
            "opponentAdjustedOffenseRank",
            "opponentAdjustedDefenseRank",
            "opponentAdjustedOverallRank",
            "opponentAdjustedOffenseScore",
            "opponentAdjustedDefenseScore",
            "opponentAdjustedOverallScore",
        ),
    )

    return {
        "markdown": md_path,
        "json": json_path,
        "tendenciesCsv": tendency_path,
        "adjustedMetricsCsv": adjusted_path,
        "gamePoeCsv": games_path,
        "scheduleStrengthCsv": schedule_path,
    }


def _basic_game_rows(
    rows: Sequence[Mapping[str, Any]],
    subject: TeamRef,
    composites: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for row in _valid_team_rows(rows, subject.id):
        opponent_id = _opponent_id(row)
        if opponent_id is None:
            continue
        pf = _number(row.get("points_for"))
        pa = _number(row.get("points_against"))
        if pf is None or pa is None:
            result_text = ""
        elif pf > pa:
            result_text = "W"
        elif pf < pa:
            result_text = "L"
        else:
            result_text = "T"
        games.append(
            {
                "gameId": _game_id(row),
                "week": row.get("week"),
                "seasonType": str(row.get("seasonType", row.get("season_type", "regular")) or "regular"),
                "homeAway": str(row.get("home_away") or ""),
                "neutralSite": bool(row.get("neutral_site")),
                "opponent": {
                    "id": opponent_id,
                    "name": str(row.get("opponent") or opponent_id),
                    "classification": str(row.get("opponent_classification") or ""),
                    "conference": str(row.get("opponent_conference") or ""),
                    "adjustedProfile": dict(composites[opponent_id]) if opponent_id in composites else None,
                },
                "score": {"result": result_text, "pointsFor": pf, "pointsAgainst": pa},
                "metrics": {},
            }
        )
    return games


def generate_pack(
    *,
    published_root: Path,
    output_root: Path,
    season: int,
    team_query: str,
    comparison_query: str | None = "Michigan",
    ridge: float = DEFAULT_RIDGE,
    home_ridge: float = DEFAULT_HOME_RIDGE,
    include_game_poe: bool = True,
) -> dict[str, Path]:
    rows = collect_published_team_games(published_root, season)
    print(f"{season}: loaded {len(rows):,} published team-game rows", flush=True)
    subject = resolve_team(rows, team_query)
    comparison = resolve_team(rows, comparison_query) if comparison_query else None
    if comparison and comparison.id == subject.id:
        comparison = None

    print(f"subject: {subject.name} ({subject.id})", flush=True)
    if comparison:
        print(f"comparison: {comparison.name} ({comparison.id})", flush=True)

    tendencies_subject = build_tendencies(rows, subject.id)
    tendencies_comparison = build_tendencies(rows, comparison.id) if comparison else None

    print("fitting full-season opponent-adjusted metrics", flush=True)
    adjusted, results = fit_pack_metrics(
        rows,
        season=season,
        subject=subject,
        comparison=comparison,
        ridge=ridge,
        home_ridge=home_ridge,
    )
    composites = build_composites(rows, results)

    if include_game_poe:
        print("building strict leave-one-game-out game breakdown", flush=True)
        games = build_game_breakdown(
            rows,
            season=season,
            subject=subject,
            composites=composites,
            ridge=ridge,
            home_ridge=home_ridge,
        )
    else:
        games = _basic_game_rows(rows, subject, composites)

    paths = write_pack(
        output_root=output_root,
        season=season,
        subject=subject,
        comparison=comparison,
        tendencies_subject=tendencies_subject,
        tendencies_comparison=tendencies_comparison,
        adjusted=adjusted,
        composites=composites,
        games=games,
        ridge=ridge,
        home_ridge=home_ridge,
    )
    for label, path in paths.items():
        print(f"{label}: {path}", flush=True)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a creator-ready numerical scouting pack from locked raw team-game "
            "contracts and schedule-adjusted ratings."
        )
    )
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--team", required=True, help="Team name, slug, or team id")
    parser.add_argument("--compare", default="Michigan", help="Comparison team; use '' for none")
    parser.add_argument("--published-root", type=Path, default=DEFAULT_PUBLISHED_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--ridge", type=float, default=DEFAULT_RIDGE)
    parser.add_argument("--home-ridge", type=float, default=DEFAULT_HOME_RIDGE)
    parser.add_argument(
        "--skip-game-poe",
        action="store_true",
        help="Skip strict leave-one-game-out game fits for a faster full-season-only export",
    )
    args = parser.parse_args()

    generate_pack(
        published_root=args.published_root,
        output_root=args.output_root,
        season=args.season,
        team_query=args.team,
        comparison_query=args.compare or None,
        ridge=args.ridge,
        home_ridge=args.home_ridge,
        include_game_poe=not args.skip_game_poe,
    )


if __name__ == "__main__":
    main()
