"""Materialize dynamic season identities for every historical team-season."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .contract import PROFILE_BY_KEY, PROFILE_METRICS
from .dynamic_identity import DYNAMIC_IDENTITY_VERSION, build_dynamic_identity
from .grades import grade_percentile, percentile_rank
from .layered_archetypes import (
    _season_identity_from_snapshot,
    closing_form_profile,
    final_snapshot,
)
from .snapshots import DEFAULT_SEASONS

OUTPUT_VERSION = "dynamic-team-profiles-v7-website-complete-grades"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"

STYLE_METRIC_MAP = {
    "identity_success_quality": "oa_success_off",
    "identity_explosiveness_quality": "oa_explosiveness_off",
    "identity_finishing_quality": "oa_finishing_off",
    "identity_third_down_quality": "oa_third_down_off",
}

# Composite identity fields are already expressed on a 0-100 season-relative
# scale because they combine season-relative component percentiles.
COMPOSITE_GRADE_FIELDS = {
    "identity_rushing_attack": ("offense", "Rushing Attack"),
    "identity_passing_attack": ("offense", "Passing Attack"),
    "identity_offense_quality": ("offense", "Offensive Quality"),
    "identity_rushing_defense": ("defense", "Rushing Defense"),
    "identity_passing_defense": ("defense", "Passing Defense"),
    "identity_defense_quality": ("defense", "Defensive Quality"),
}

# Derived scheme values are useful profile scores, but they are not themselves
# percentiles. Rank them across each season before assigning a letter grade.
DERIVED_PROFILE_GRADE_DIRECTIONS = {
    "identity_predictability": False,
    "identity_one_dimensionality": False,
    "identity_playcalling_fit": True,
    "identity_scheme_constraint": False,
}

DISPLAY_LABEL_OVERRIDES = {
    "oa_success_def": "Overall Success Defense",
}

# These metrics are available in snapshots even where the older profile contract
# only exposed the broader composite. They are useful fan-facing split grades.
EXTRA_GRADE_METRICS = (
    ("oa_run_explosiveness_def", "defense", "Run Explosive Prevention", "RESEARCH"),
    ("oa_pass_explosiveness_def", "defense", "Pass Explosive Prevention", "RESEARCH"),
    ("oa_run_success_yards_def", "defense", "Run Successful-Play Suppression", "RESEARCH"),
    ("oa_pass_success_yards_def", "defense", "Pass Successful-Play Suppression", "RESEARCH"),
)


def _enrich_style_metrics(
    profile: dict[str, float | None],
    snapshot: dict[str, Any],
    *,
    prefix: str,
) -> dict[str, float | None]:
    """Attach direct percentile evidence used to distinguish offensive mechanisms."""
    out = dict(profile)
    for target, source in STYLE_METRIC_MAP.items():
        value = snapshot.get(f"{prefix}_{source}_percentile")
        out[target] = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return out


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _grade_row(
    *, key: str, section: str, label: str, status: str,
    percentile: float | None, grade: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "section": section,
        "label": label,
        "status": status,
        "percentile": percentile,
        "grade": grade if grade is not None else grade_percentile(percentile),
        "available": percentile is not None,
        "description": description,
    }


def _gradebook(profile: dict[str, float | None], final: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for key, (section, label) in COMPOSITE_GRADE_FIELDS.items():
        percentile = _number(profile.get(key))
        rows.append(_grade_row(
            key=key, section=section, label=label, status="RESEARCH",
            percentile=percentile,
            description="Season-relative composite percentile used by the team identity model.",
        ))
        seen.add(key)

    for metric in PROFILE_METRICS:
        if metric.key in seen:
            continue
        percentile = _number(final.get(f"baseline_{metric.key}_percentile"))
        grade = final.get(f"baseline_{metric.key}_grade")
        rows.append(_grade_row(
            key=metric.key,
            section=metric.section,
            label=DISPLAY_LABEL_OVERRIDES.get(metric.key, metric.label),
            status=metric.status,
            percentile=percentile,
            grade=str(grade) if isinstance(grade, str) else None,
            description=metric.description,
        ))
        seen.add(metric.key)

    for key, section, label, status in EXTRA_GRADE_METRICS:
        if key in seen:
            continue
        percentile = _number(final.get(f"baseline_{key}_percentile"))
        grade = final.get(f"baseline_{key}_grade")
        rows.append(_grade_row(
            key=key, section=section, label=label, status=status,
            percentile=percentile,
            grade=str(grade) if isinstance(grade, str) else None,
            description="Season-relative opponent-adjusted split grade.",
        ))
        seen.add(key)

    return rows


def _attach_derived_profile_grades(items: list[dict[str, Any]]) -> None:
    """Grade derived scheme fields against each season's team population."""
    by_season: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_season[int(item["season"])].append(item)

    for season_items in by_season.values():
        populations = {
            key: [
                value
                for item in season_items
                if (value := _number((item.get("profile") or {}).get(key))) is not None
            ]
            for key in DERIVED_PROFILE_GRADE_DIRECTIONS
        }
        for item in season_items:
            grade_rows = {str(row.get("key")): row for row in item.get("grades") or []}
            profile = item.get("profile") or {}
            for key, higher_is_better in DERIVED_PROFILE_GRADE_DIRECTIONS.items():
                value = _number(profile.get(key))
                pct = percentile_rank(value, populations[key], higher_is_better=higher_is_better)
                metric = PROFILE_BY_KEY[key]
                replacement = _grade_row(
                    key=key,
                    section=metric.section,
                    label=metric.label,
                    status=metric.status,
                    percentile=pct,
                    description=metric.description,
                )
                if key in grade_rows:
                    grade_rows[key].update(replacement)
                else:
                    item.setdefault("grades", []).append(replacement)


def build_dynamic_profiles(
    rows: list[dict[str, Any]],
    *,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
) -> dict[str, Any]:
    wanted = {int(x) for x in seasons}
    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        season = int(row.get("season", -1))
        team = str(row.get("team") or "")
        if season in wanted and team:
            groups[(season, team)].append(row)

    items: list[dict[str, Any]] = []
    for (season, team), selected in sorted(groups.items()):
        selected.sort(
            key=lambda row: (
                int(row.get("gamesPlayed") or 0),
                str(row.get("startDate") or ""),
                str(row.get("throughGameId") or ""),
            )
        )
        final = final_snapshot(selected)
        season_profiles = [
            _enrich_style_metrics(_season_identity_from_snapshot(row), row, prefix="baseline")
            for row in selected
        ]
        profile = season_profiles[-1]
        closing = _enrich_style_metrics(closing_form_profile(selected), final, prefix="current")
        identity = build_dynamic_identity(
            profile,
            closing_form=closing,
            season_profiles=season_profiles,
        )
        items.append(
            {
                "season": season,
                "team": team,
                "identityName": identity["name"],
                "identityTags": identity["tags"],
                "identitySummary": identity["summary"],
                "identityStyle": identity["style"],
                "identityVersion": identity["version"],
                "profileBasis": "FINAL_SEASON_TO_DATE_BASELINE",
                "closingFormBasis": "RECENT_FOUR_GAMES",
                "gradeBasis": "SEASON_RELATIVE_FINAL_BASELINE_PERCENTILES",
                "finalGamesPlayed": int(final.get("gamesPlayed") or 0),
                "finalSeasonType": final.get("seasonType"),
                "finalWeek": final.get("week"),
                "finalStartDate": final.get("startDate"),
                "finalThroughGameId": final.get("throughGameId"),
                "profile": profile,
                "closingFormProfile": closing,
                "consistency": identity["consistency"],
                "grades": _gradebook(profile, final),
            }
        )

    _attach_derived_profile_grades(items)

    return {
        "version": OUTPUT_VERSION,
        "identityVersion": DYNAMIC_IDENTITY_VERSION,
        "namingBasis": "NEUTRAL_STYLE_PLUS_MECHANISM_PLUS_EARNED_EFFECTIVENESS_PLUS_CONSISTENCY",
        "gradeBasis": "SEASON_RELATIVE_FINAL_BASELINE_PERCENTILES",
        "seasons": sorted(wanted),
        "teamSeasonCount": len(items),
        "teamSeasons": items,
    }


def concise(report: dict[str, Any], *, examples: int = 20) -> str:
    lines = [
        "DYNAMIC TEAM IDENTITIES — WEBSITE-READY",
        f"Team-seasons: {report['teamSeasonCount']:,}",
        f"Seasons: {', '.join(str(x) for x in report['seasons'])}",
        "Neutral style describes behavior; strength words are earned by quality.",
        "Commitment, consistency, and volatility use shared structured classifiers.",
        "Grades are season-relative percentiles with A+ through F letter grades.",
        "",
    ]
    for item in report["teamSeasons"][:examples]:
        tags = " · ".join(item.get("identityTags") or []) or "No strong tags"
        style = item.get("identityStyle") or {}
        lines.append(f"{item['season']} {item['team']} — {item['identityName']}")
        lines.append(
            "  STYLE | "
            f"usage={style.get('usage')} | method={style.get('method')} | pace={style.get('paceShape')} | "
            f"efficiency={style.get('efficiencyShape')} | driver={style.get('attackDriver')} | "
            f"commitment={style.get('commitment')} | structure={style.get('teamStructure')} | "
            f"effectiveness={style.get('effectiveness')} | "
            f"offConsistency={style.get('offenseConsistency')} | defConsistency={style.get('defenseConsistency')}"
        )
        lines.append(f"  TAGS  | {tags}")
        lines.append(f"  {item['identitySummary']}")
        lines.append("")
    return "\n".join(lines)


def materialize(
    processed_root: Path,
    *,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
) -> Path:
    source = processed_root / "derived" / "profiles" / "identity_snapshots_v3_attack_scheme.json"
    if not source.exists():
        raise FileNotFoundError(
            f"identity snapshots not found at {source}; run python -m cfb_analytics.profiles.snapshots from any directory"
        )
    rows = json.loads(source.read_text())
    report = build_dynamic_profiles(rows, seasons=seasons)
    target = processed_root / "derived" / "profiles" / "dynamic_team_identities.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, separators=(",", ":")))
    return target


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    p.add_argument("--seasons", nargs="+", type=int, default=list(DEFAULT_SEASONS))
    p.add_argument("--examples", type=int, default=20)
    args = p.parse_args()
    target = materialize(args.processed_root, seasons=tuple(args.seasons))
    report = json.loads(target.read_text())
    print(concise(report, examples=args.examples))
    print(f"WROTE {target}")


if __name__ == "__main__":
    main()
