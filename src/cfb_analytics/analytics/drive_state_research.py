"""Leakage-safe drive-state rows for a semi-mechanistic simulator.

Version 2 uses the dedicated raw CFBD drive record as the authoritative source
for possession start state and categorical drive outcome. The derived drive
layer is used only as a conservative possession/ownership validator, while
pregame football-mechanism states provide team quality known before kickoff.

Important: raw drive scoreboard deltas are intentionally NOT used as targets.
Forensic audits found that those deltas do not reconcile reliably enough at the
game level. The direct ``driveResult`` label is retained instead and collapsed
into a small football outcome family for modeling.

Prediction v1 and the existing simulator are not modified by this module.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.football_mechanisms import TEAM_FIELDS
from cfb_analytics.analytics.situational_pregame import SEASONS, partition_sort_key
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.storage import partition_dir

DRIVE_STATE_RESEARCH_VERSION = "drive-state-research-v2-raw-drive-outcomes-regulation"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"

# Only fields causally relevant to the offense on the current possession are
# retained. We do not feed the offense's own defensive quality, or the opposing
# defense's offensive quality, into the initial drive model.
OFFENSE_QUALITY_FIELDS = (
    "OffYardsPerPossession",
    "OffSuccessRate",
    "OffExplosiveRate",
    "OffScoringOpportunityRate",
    "OffPointsPerOpportunity",
    "OffEarlyDownSuccessRate",
    "OffGiveawayRate",
)
DEFENSE_QUALITY_FIELDS = (
    "DefYardsPerPossession",
    "DefSuccessRateAllowed",
    "DefExplosiveRateAllowed",
    "DefScoringOpportunityRateAllowed",
    "DefPointsPerOpportunityAllowed",
    "DefEarlyDownSuccessRateAllowed",
    "DefTakeawayRate",
)
QUALITY_FIELDS = OFFENSE_QUALITY_FIELDS + DEFENSE_QUALITY_FIELDS

_RETURN_TD_RESULTS = {
    "INT TD",
    "FUMBLE RETURN TD",
    "PUNT TD",
    "PUNT RETURN TD",
    "FUMBLE TD",
    "MISSED FG TD",
    "DOWNS TD",
    "FG TD",
}
_PERIOD_END_RESULTS = {"END OF GAME", "END OF HALF", "END OF 4TH QUARTER"}


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def matchup_path(processed_root: Path, season: int) -> Path:
    return processed_root / "derived" / "football_mechanisms" / f"season={season}" / "matchups.json"


def output_path(processed_root: Path, season: int) -> Path:
    return processed_root / "derived" / "drive_state_research" / f"season={season}" / "drives.json"


def _team_state_from_matchup(matchup: dict[str, Any], prefix: str) -> dict[str, Any]:
    state = {
        "team": matchup.get(prefix),
        "gamesPlayedBefore": matchup.get(f"{prefix}GamesPlayedBefore", 0),
    }
    for field in TEAM_FIELDS:
        state[field] = matchup.get(f"{prefix}_{field}")
    return state


def matchup_team_states(matchup: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for prefix in ("team1", "team2"):
        state = _team_state_from_matchup(matchup, prefix)
        team = state.get("team")
        if team:
            out[str(team)] = state
    return out


def drive_outcome_family(result: Any) -> str:
    """Collapse raw CFBD driveResult into a stable modeling family."""
    value = str(result or "").strip().upper()
    if value == "TD":
        return "TOUCHDOWN"
    if value == "FG":
        return "FIELD_GOAL"
    if value == "PUNT":
        return "PUNT"
    if value in {"INT", "FUMBLE"}:
        return "TURNOVER"
    if value == "DOWNS":
        return "DOWNS"
    if value in {"MISSED FG", "BLOCKED FG"}:
        return "MISSED_FIELD_GOAL"
    if value in _PERIOD_END_RESULTS:
        return "PERIOD_END"
    if value in _RETURN_TD_RESULTS:
        return "RETURN_TOUCHDOWN"
    if value == "SF":
        return "SAFETY"
    return "OTHER"


def _score_margin(raw_drive: dict[str, Any]) -> float | None:
    off = raw_drive.get("startOffenseScore")
    deff = raw_drive.get("startDefenseScore")
    if _num(off) and _num(deff):
        return float(off) - float(deff)
    return None


def _score_state(margin: float | None) -> str:
    if not _num(margin):
        return "unknown"
    if float(margin) > 0:
        return "leading"
    if float(margin) < 0:
        return "trailing"
    return "tied"


def _clock_seconds(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    minutes = value.get("minutes")
    seconds = value.get("seconds")
    if not (_num(minutes) and _num(seconds)):
        return None
    return int(minutes) * 60 + int(seconds)


def _overtime(raw_drive: dict[str, Any]) -> bool:
    return any(
        _num(raw_drive.get(field)) and float(raw_drive[field]) > 4
        for field in ("startPeriod", "endPeriod")
    )


def build_drive_row(
    raw_drive: dict[str, Any],
    derived_drive: dict[str, Any],
    matchup: dict[str, Any],
    *,
    include_overtime: bool = False,
) -> dict[str, Any] | None:
    """Build one research row from raw state/outcome plus validated ownership.

    The raw drive supplies start-of-possession state and ``driveResult``. The
    derived drive must independently validate as a possession and agree on both
    offense and defense. This prevents source ownership anomalies from entering
    the modeling corpus.
    """
    if not (
        derived_drive.get("isPossessionDrive") is True
        and derived_drive.get("driveValidationStatus") == "PASS"
        and derived_drive.get("offense")
        and derived_drive.get("defense")
    ):
        return None

    raw_offense = str(raw_drive.get("offense") or "")
    raw_defense = str(raw_drive.get("defense") or "")
    if not raw_offense or not raw_defense:
        return None
    if raw_offense != str(derived_drive.get("offense")) or raw_defense != str(derived_drive.get("defense")):
        return None
    if _overtime(raw_drive) and not include_overtime:
        return None

    states = matchup_team_states(matchup)
    off_state = states.get(raw_offense)
    def_state = states.get(raw_defense)
    if off_state is None or def_state is None:
        return None

    result = str(raw_drive.get("driveResult") or "Uncategorized")
    family = drive_outcome_family(result)
    margin = _score_margin(raw_drive)
    period = raw_drive.get("startPeriod")
    ytg = raw_drive.get("startYardsToGoal")

    row: dict[str, Any] = {
        "version": DRIVE_STATE_RESEARCH_VERSION,
        "season": int(derived_drive.get("season")),
        "seasonType": str(derived_drive.get("seasonType")),
        "week": int(derived_drive.get("week")),
        "gameId": str(raw_drive.get("gameId")),
        "driveId": str(raw_drive.get("id")),
        "driveNumber": raw_drive.get("driveNumber"),
        "offense": raw_offense,
        "defense": raw_defense,
        "offenseGamesPlayedBefore": int(off_state.get("gamesPlayedBefore") or 0),
        "defenseGamesPlayedBefore": int(def_state.get("gamesPlayedBefore") or 0),
        "startPeriod": int(period) if _num(period) else None,
        "startClockSeconds": _clock_seconds(raw_drive.get("startTime")),
        "startYardsToGoal": float(ytg) if _num(ytg) else None,
        "startScoreMargin": margin,
        "startScoreState": _score_state(margin),
        "isHomeOffense": bool(raw_drive.get("isHomeOffense")) if raw_drive.get("isHomeOffense") is not None else None,
        "overtime": _overtime(raw_drive),
        "targetDriveResult": result,
        "targetOutcomeFamily": family,
        "targetOffensiveScore": int(family in {"TOUCHDOWN", "FIELD_GOAL"}),
        "targetOpponentScore": int(family in {"RETURN_TOUCHDOWN", "SAFETY"}),
    }

    for field in OFFENSE_QUALITY_FIELDS:
        row[f"offense_{field}"] = off_state.get(field)
    for field in DEFENSE_QUALITY_FIELDS:
        row[f"defense_{field}"] = def_state.get(field)

    return row


def load_matchups(processed_root: Path, season: int) -> dict[str, dict[str, Any]]:
    path = matchup_path(processed_root, season)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing football-mechanism matchups for {season}: {path}. "
            "Run python -m cfb_analytics.analytics.football_mechanisms --all"
        )
    rows = json.loads(path.read_text())
    return {str(r.get("gameId")): r for r in rows if r.get("gameId") is not None}


def materialize_season(
    raw_root: Path,
    processed_root: Path,
    season: int,
    *,
    include_overtime: bool = False,
) -> tuple[Path, list[dict[str, Any]]]:
    matchups = load_matchups(processed_root, season)
    out: list[dict[str, Any]] = []

    for season_type, week in sorted(discover_partitions(raw_root, season), key=partition_sort_key):
        raw_drive_file = partition_dir(raw_root, season, season_type, week) / "drives.json"
        derived_drive_file = derived_drive_partition_dir(processed_root, season, season_type, week) / "drives.json"
        if not raw_drive_file.exists():
            raise FileNotFoundError(f"Missing raw drives: {raw_drive_file}")
        if not derived_drive_file.exists():
            raise FileNotFoundError(f"Missing derived drives: {derived_drive_file}")

        derived = {
            (str(d.get("gameId")), str(d.get("driveId"))): d
            for d in json.loads(derived_drive_file.read_text())
        }
        for raw_drive in json.loads(raw_drive_file.read_text()):
            game_id = str(raw_drive.get("gameId"))
            drive_id = str(raw_drive.get("id"))
            derived_drive = derived.get((game_id, drive_id))
            matchup = matchups.get(game_id)
            if derived_drive is None or matchup is None:
                continue
            row = build_drive_row(
                raw_drive,
                derived_drive,
                matchup,
                include_overtime=include_overtime,
            )
            if row is not None:
                out.append(row)

    path = output_path(processed_root, season)
    _atomic(path, out)
    return path, out


def audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    families = Counter(r.get("targetOutcomeFamily") for r in rows)
    raw_results = Counter(r.get("targetDriveResult") for r in rows)
    periods = Counter(r.get("startPeriod") for r in rows)
    score_states = Counter(r.get("startScoreState") for r in rows)
    ytg_present = sum(_num(r.get("startYardsToGoal")) for r in rows)
    score_present = sum(_num(r.get("startScoreMargin")) for r in rows)
    clock_present = sum(_num(r.get("startClockSeconds")) for r in rows)
    zero_history = sum(
        int(r.get("offenseGamesPlayedBefore", 0)) == 0 or int(r.get("defenseGamesPlayedBefore", 0)) == 0
        for r in rows
    )

    quality_keys = [f"offense_{f}" for f in OFFENSE_QUALITY_FIELDS] + [f"defense_{f}" for f in DEFENSE_QUALITY_FIELDS]
    quality_total = len(rows) * len(quality_keys)
    quality_present = sum(_num(r.get(key)) for r in rows for key in quality_keys)

    return {
        "rows": len(rows),
        "teams": len({r.get("offense") for r in rows} | {r.get("defense") for r in rows}),
        "games": len({r.get("gameId") for r in rows}),
        "outcomeFamilies": dict(sorted(families.items(), key=lambda x: str(x[0]))),
        "rawResults": dict(sorted(raw_results.items(), key=lambda x: str(x[0]))),
        "startPeriods": dict(sorted(periods.items(), key=lambda x: str(x[0]))),
        "scoreStates": dict(sorted(score_states.items(), key=lambda x: str(x[0]))),
        "yardsToGoalCoverage": ytg_present / len(rows) if rows else 0.0,
        "scoreMarginCoverage": score_present / len(rows) if rows else 0.0,
        "startClockCoverage": clock_present / len(rows) if rows else 0.0,
        "qualityCoverage": quality_present / quality_total if quality_total else 0.0,
        "zeroHistoryRows": zero_history,
        "overtimeRows": sum(bool(r.get("overtime")) for r in rows),
        "otherOutcomeRows": families.get("OTHER", 0),
    }


def concise_audit(season: int, path: Path, report: dict[str, Any]) -> str:
    lines = [
        f"DRIVE STATE RESEARCH v2 AUDIT — {season}",
        "=" * 72,
        f"Rows: {report['rows']:,}",
        f"Games: {report['games']:,}",
        f"Teams: {report['teams']:,}",
        f"Start yards-to-goal coverage: {report['yardsToGoalCoverage']*100:.2f}%",
        f"Start score-margin coverage: {report['scoreMarginCoverage']*100:.2f}%",
        f"Start clock coverage: {report['startClockCoverage']*100:.2f}%",
        f"Pregame relevant-quality coverage: {report['qualityCoverage']*100:.2f}%",
        f"Rows with either team at zero prior games: {report['zeroHistoryRows']:,}",
        f"Overtime rows retained: {report['overtimeRows']:,}",
        f"OTHER outcome rows: {report['otherOutcomeRows']:,}",
        "",
        "OUTCOME FAMILY",
    ]
    for key, value in report["outcomeFamilies"].items():
        lines.append(f"  {str(key):>20s}: {value:>8,}")
    lines.append("")
    lines.append("RAW DRIVE RESULT")
    for key, value in sorted(report["rawResults"].items(), key=lambda x: (-x[1], str(x[0]))):
        lines.append(f"  {str(key):>20s}: {value:>8,}")
    lines.append("")
    lines.append("START SCORE STATE")
    for key, value in report["scoreStates"].items():
        lines.append(f"  {str(key):>20s}: {value:>8,}")
    lines.append("")
    lines.append(f"Wrote: {path}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--include-overtime", action="store_true")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    args = parser.parse_args()

    seasons = SEASONS if args.all else ((args.season,) if args.season else ())
    if not seasons:
        parser.error("pass --season YYYY or --all")

    for season in seasons:
        path, rows = materialize_season(
            args.raw_root,
            args.processed_root,
            season,
            include_overtime=args.include_overtime,
        )
        print(concise_audit(season, path, audit_rows(rows)))


if __name__ == "__main__":
    main()
