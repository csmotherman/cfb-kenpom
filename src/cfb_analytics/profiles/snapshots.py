"""Build opponent-adjusted in-season team identity snapshots.

Profiles separate four concepts:
- quality: opponent-adjusted offense/defense performance;
- attack composites: broader rushing/passing quality beyond success rate alone;
- style/scheme: descriptive behavior and whether usage fits actual strengths;
- form: recent four-game state versus season-to-date baseline.

Snapshots are descriptive after each played game-time context, not pregame
predictors. Raw CFBD game ``startDate`` is the chronology source of truth;
seasonType/week remain descriptive labels and percentile cohorts only.

The full historical snapshot build is intentionally expensive because it refits
opponent-adjusted ratings at every chronological context. The materializer is
therefore cache-aware: when the existing artifact matches ``SNAPSHOT_VERSION``
and is newer than all raw/derived source partitions, it is reused. Use
``--force`` only when an explicit full rebuild is required.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from .grades import grade_percentile, percentile_rank
from .opponent_adjustment import METRIC_SPECS, fit_context, quality_keys, team_quality

SNAPSHOT_VERSION = "team-identity-snapshots-v4-game-chronology-research"
DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
ORDER = {"regular": 0, "postseason": 1}
DEFAULT_MIN_GAMES = 4
DEFAULT_RECENT_GAMES = 4
SNAPSHOT_FILENAME = "identity_snapshots_v3_attack_scheme.json"
SNAPSHOT_CACHE_FILENAME = "identity_snapshots_v3_attack_scheme.cache.json"


def _rate(n: float, d: float) -> float | None:
    return n / d if d else None


def _sum(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(r.get(key) or 0.0) for r in rows)


def _raw_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    rush_e, rush_s = _sum(rows, "rushSuccessEligiblePlays"), _sum(rows, "rushSuccessfulPlays")
    pass_e, pass_s = _sum(rows, "passSuccessEligiblePlays"), _sum(rows, "passSuccessfulPlays")
    succ_e, succ_s = _sum(rows, "successEligiblePlays"), _sum(rows, "successfulPlays")
    exp_e, exp_n = _sum(rows, "explosiveEligiblePlays"), _sum(rows, "explosivePlays")
    poss, plays = _sum(rows, "validatedPossessions"), _sum(rows, "offensivePlays")
    denom = rush_e + pass_e
    return {
        "run_efficiency_off": _rate(rush_s, rush_e),
        "pass_efficiency_off": _rate(pass_s, pass_e),
        "success_off": _rate(succ_s, succ_e),
        "explosiveness_off": _rate(exp_n, exp_e),
        "rush_rate": _rate(rush_e, denom),
        "pass_rate": _rate(pass_e, denom),
        "plays_per_possession": _rate(plays, poss),
    }


STYLE_KEYS = ("rush_rate", "pass_rate", "plays_per_possession")
RAW_DIAGNOSTIC_KEYS = ("run_efficiency_off", "pass_efficiency_off", "success_off", "explosiveness_off")
DISCOVERY_DIRECTIONS = {**{k: True for k in quality_keys()}, **{k: True for k in STYLE_KEYS}}


def _partition_key(row: dict[str, Any]) -> tuple[int, int]:
    return (ORDER.get(str(row.get("seasonType") or "regular").lower(), 9), int(row.get("week") or 0))


def _context_key(row: dict[str, Any]) -> tuple[str, str]:
    """Return the played-game context used for opponent-adjusted history.

    Production rows loaded by ``load_team_games`` always carry startDate. The
    partition fallback exists only so small synthetic/unit-test rows remain
    usable without raw game metadata.
    """
    start = row.get("startDate")
    if isinstance(start, str) and start:
        return ("startDate", start)
    phase, week = _partition_key(row)
    return ("partition", f"{phase:02d}:{week:03d}")


def _chronology_key(row: dict[str, Any]) -> tuple[str, str, str]:
    kind, value = _context_key(row)
    return (kind, value, str(row.get("gameId") or ""))


def _game_value(row: dict[str, Any], spec) -> tuple[float, float] | None:
    n, d = row.get(spec.numerator), row.get(spec.denominator)
    if isinstance(n, (int, float)) and isinstance(d, (int, float)) and not isinstance(n, bool) and not isinstance(d, bool) and float(d) > 0:
        return float(n) / float(d), float(d)
    return None


def _recent_oa(team: str, recent: list[dict[str, Any]], fits: dict[str, dict[str, Any]], game_rows: dict[tuple[str, str], dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for spec in METRIC_SPECS:
        fit = fits[spec.key]
        mean = fit.get("mean")
        off_num = off_den = def_num = def_den = 0.0
        for row in recent:
            gv = _game_value(row, spec)
            opp = str(row.get("opponent") or "")
            if gv and isinstance(mean, (int, float)):
                value, weight = gv
                opp_def = fit.get("defense", {}).get(opp)
                if isinstance(opp_def, (int, float)):
                    off_num += weight * (value - float(mean) + float(opp_def)); off_den += weight
            opp_row = game_rows.get((str(row.get("gameId")), opp))
            ogv = _game_value(opp_row, spec) if opp_row else None
            if ogv and isinstance(mean, (int, float)):
                value, weight = ogv
                opp_off = fit.get("offense", {}).get(opp)
                if isinstance(opp_off, (int, float)):
                    def_num += weight * (float(mean) + float(opp_off) - value); def_den += weight
        out[f"oa_{spec.key}_off"] = off_num / off_den if off_den else None
        out[f"oa_{spec.key}_def"] = def_num / def_den if def_den else None
    return out


def build_identity_snapshots(team_games: list[dict[str, Any]], *, min_games: int = DEFAULT_MIN_GAMES, recent_games: int = DEFAULT_RECENT_GAMES) -> list[dict[str, Any]]:
    if min_games < 1 or recent_games < 1:
        raise ValueError("min_games and recent_games must be positive")
    valid = [r for r in team_games if r.get("gameValidationStatus") in (None, "PASS")]
    by_team: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    by_season_context: dict[tuple[int, tuple[str, str]], list[dict[str, Any]]] = defaultdict(list)
    game_rows = {(str(r.get("gameId")), str(r.get("team"))): r for r in valid}
    for row in valid:
        season = int(row["season"]); team = str(row["team"])
        by_team[(season, team)].append(row)
        by_season_context[(season, _context_key(row))].append(row)
    for games in by_team.values():
        games.sort(key=_chronology_key)

    fits_by_context: dict[tuple[int, tuple[str, str]], dict[str, dict[str, Any]]] = {}
    for season in sorted({int(r["season"]) for r in valid}):
        history: list[dict[str, Any]] = []
        contexts = sorted(context for s, context in by_season_context if s == season)
        for context in contexts:
            history.extend(by_season_context[(season, context)])
            fits_by_context[(season, context)] = fit_context(history)

    out: list[dict[str, Any]] = []
    for (season, team), games in sorted(by_team.items()):
        for i in range(min_games - 1, len(games)):
            through, recent = games[:i+1], games[max(0, i+1-recent_games):i+1]
            current_game = games[i]; context = _context_key(current_game); fits = fits_by_context[(season, context)]
            baseline_oa = team_quality(fits, team); current_oa = _recent_oa(team, recent, fits, game_rows)
            baseline_raw = _raw_metrics(through); current_raw = _raw_metrics(recent)
            row: dict[str, Any] = {
                "season": season, "team": team, "seasonType": current_game.get("seasonType"),
                "week": current_game.get("week"), "startDate": current_game.get("startDate"),
                "throughGameId": current_game.get("gameId"), "gamesPlayed": len(through),
                "recentGames": len(recent), "snapshotVersion": SNAPSHOT_VERSION,
            }
            for key in quality_keys():
                row[f"baseline_{key}"] = baseline_oa.get(key); row[f"current_{key}"] = current_oa.get(key)
            for key in STYLE_KEYS:
                row[f"baseline_{key}"] = baseline_raw.get(key); row[f"current_{key}"] = current_raw.get(key)
            for key in RAW_DIAGNOSTIC_KEYS:
                row[f"raw_baseline_{key}"] = baseline_raw.get(key); row[f"raw_current_{key}"] = current_raw.get(key)
                row[f"baseline_{key}"] = baseline_raw.get(key); row[f"current_{key}"] = current_raw.get(key)
            out.append(row)
    return out


def _mean_present(values: list[float | None]) -> float | None:
    vals = [float(x) for x in values if isinstance(x, (int, float))]
    return sum(vals) / len(vals) if vals else None


def _identity_shape(enriched: dict[str, Any]) -> None:
    def pct(key: str) -> float | None:
        v = enriched.get(f"current_{key}_percentile")
        return float(v) if isinstance(v, (int, float)) else None
    def gap(a: str, b: str) -> float | None:
        x, y = pct(a), pct(b)
        return x - y if x is not None and y is not None else None

    rushing_attack = _mean_present([
        pct("oa_run_efficiency_off"), pct("oa_run_explosiveness_off"), pct("oa_run_success_yards_off")
    ])
    passing_attack = _mean_present([
        pct("oa_pass_efficiency_off"), pct("oa_pass_explosiveness_off"), pct("oa_pass_success_yards_off")
    ])
    rushing_defense = _mean_present([
        pct("oa_run_efficiency_def"), pct("oa_run_explosiveness_def"), pct("oa_run_success_yards_def")
    ])
    passing_defense = _mean_present([
        pct("oa_pass_efficiency_def"), pct("oa_pass_explosiveness_def"), pct("oa_pass_success_yards_def")
    ])
    offense = [rushing_attack, passing_attack, pct("oa_success_off"), pct("oa_explosiveness_off"), pct("oa_third_down_off"), pct("oa_finishing_off")]
    defense = [rushing_defense, passing_defense, pct("oa_success_def"), pct("oa_explosiveness_def"), pct("oa_third_down_def"), pct("oa_finishing_def")]
    off_q = _mean_present(offense); def_q = _mean_present(defense)
    rush_tendency, pass_tendency = pct("rush_rate"), pct("pass_rate")
    tendency_gap = (rush_tendency - pass_tendency) if rush_tendency is not None and pass_tendency is not None else None
    attack_gap = (rushing_attack - passing_attack) if rushing_attack is not None and passing_attack is not None else None

    enriched["identity_rushing_attack"] = rushing_attack
    enriched["identity_passing_attack"] = passing_attack
    enriched["identity_rushing_defense"] = rushing_defense
    enriched["identity_passing_defense"] = passing_defense
    enriched["identity_run_vs_pass_off"] = attack_gap
    enriched["identity_run_vs_pass_def"] = (rushing_defense - passing_defense) if rushing_defense is not None and passing_defense is not None else None
    enriched["identity_explosive_vs_methodical"] = gap("oa_explosiveness_off", "oa_success_off")
    enriched["identity_finishing_vs_foundation"] = (pct("oa_finishing_off") - off_q) if pct("oa_finishing_off") is not None and off_q is not None else None
    enriched["identity_offense_vs_defense"] = (off_q - def_q) if off_q is not None and def_q is not None else None
    enriched["identity_rush_vs_pass_tendency"] = tendency_gap
    enriched["identity_offense_quality"] = off_q
    enriched["identity_defense_quality"] = def_q
    enriched["identity_predictability"] = abs(tendency_gap) if tendency_gap is not None else None
    enriched["identity_one_dimensionality"] = abs(attack_gap) if attack_gap is not None else None
    enriched["identity_playcalling_fit"] = (tendency_gap * attack_gap / 100.0) if tendency_gap is not None and attack_gap is not None else None
    weak_attack = min(rushing_attack, passing_attack) if rushing_attack is not None and passing_attack is not None else None
    enriched["identity_scheme_constraint"] = (
        abs(tendency_gap) * (100.0 - weak_attack) / 100.0
        if tendency_gap is not None and weak_attack is not None else None
    )


def add_context_percentiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Keep broad week/season-type cross-sections for percentile ranking. Game
    # chronology is handled independently by startDate in build_identity_snapshots.
    groups: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(int(row["season"]), str(row.get("seasonType") or "regular"), int(row.get("week") or 0))].append(row)
    out: list[dict[str, Any]] = []
    for group in groups.values():
        for row in group:
            enriched = dict(row)
            for key, higher in DISCOVERY_DIRECTIONS.items():
                for prefix in ("baseline", "current"):
                    field = f"{prefix}_{key}"; pop = [x.get(field) for x in group if isinstance(x.get(field), (int, float))]
                    p = percentile_rank(row.get(field), pop, higher_is_better=higher)
                    enriched[f"{field}_percentile"] = p; enriched[f"{field}_grade"] = grade_percentile(p)
                a, b = enriched.get(f"current_{key}_percentile"), enriched.get(f"baseline_{key}_percentile")
                enriched[f"trend_{key}"] = (a-b) if isinstance(a,(int,float)) and isinstance(b,(int,float)) else None
            _identity_shape(enriched); out.append(enriched)
    return out


def _raw_game_start_dates(raw_root: Path, seasons: tuple[int, ...]) -> dict[str, str]:
    dates: dict[str, str] = {}
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            path = raw_root / "cfbd" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}" / "games.json"
            games = json.loads(path.read_text())
            for game in games:
                gid = str(game.get("id"))
                start = game.get("startDate")
                if not isinstance(start, str) or not start:
                    raise ValueError(f"missing startDate for raw game {gid} in {path}")
                previous = dates.get(gid)
                if previous is not None and previous != start:
                    raise ValueError(f"conflicting startDate for raw game {gid}: {previous} != {start}")
                dates[gid] = start
    return dates


def load_team_games(processed_root: Path, seasons: tuple[int, ...] = DEFAULT_SEASONS) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []; raw_root = processed_root.parent / "raw"
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            path = derived_game_partition_dir(processed_root, season, season_type, week) / "team_games.json"
            if path.exists(): rows.extend(json.loads(path.read_text()))
    dates = _raw_game_start_dates(raw_root, seasons)
    missing: set[str] = set()
    for row in rows:
        gid = str(row.get("gameId"))
        start = row.get("startDate") or dates.get(gid)
        if not isinstance(start, str) or not start:
            missing.add(gid)
        else:
            row["startDate"] = start
    if missing:
        sample = ", ".join(sorted(missing)[:10])
        raise ValueError(f"missing startDate for {len(missing)} derived games; sample={sample}")
    return rows


def _snapshot_target(processed_root: Path) -> Path:
    return processed_root / "derived" / "profiles" / SNAPSHOT_FILENAME


def _snapshot_cache_path(processed_root: Path) -> Path:
    return processed_root / "derived" / "profiles" / SNAPSHOT_CACHE_FILENAME


def _snapshot_source_files(processed_root: Path, seasons: tuple[int, ...] = DEFAULT_SEASONS) -> list[Path]:
    """Return the inexpensive dependency set used to invalidate the snapshot cache."""
    raw_root = processed_root.parent / "raw"
    files: list[Path] = []
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            raw_games = raw_root / "cfbd" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}" / "games.json"
            if raw_games.exists():
                files.append(raw_games)
            team_games = derived_game_partition_dir(processed_root, season, season_type, week) / "team_games.json"
            if team_games.exists():
                files.append(team_games)
    return files


def _cache_manifest(processed_root: Path, *, min_games: int, recent_games: int) -> dict[str, Any]:
    sources = _snapshot_source_files(processed_root)
    newest_source_mtime_ns = max((p.stat().st_mtime_ns for p in sources), default=0)
    return {
        "snapshotVersion": SNAPSHOT_VERSION,
        "minGames": min_games,
        "recentGames": recent_games,
        "newestSourceMtimeNs": newest_source_mtime_ns,
        "sourceFileCount": len(sources),
    }


def _artifact_matches_version(target: Path) -> tuple[bool, list[dict[str, Any]] | None]:
    if not target.exists():
        return False, None
    try:
        rows = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return False, None
    if not isinstance(rows, list) or not rows:
        return False, None
    first = rows[0]
    if not isinstance(first, dict) or first.get("snapshotVersion") != SNAPSHOT_VERSION:
        return False, None
    return True, rows


def _can_reuse_snapshots(processed_root: Path, *, min_games: int, recent_games: int) -> tuple[bool, list[dict[str, Any]] | None]:
    target = _snapshot_target(processed_root)
    matches, rows = _artifact_matches_version(target)
    if not matches or rows is None:
        return False, None

    expected = _cache_manifest(processed_root, min_games=min_games, recent_games=recent_games)
    cache_path = _snapshot_cache_path(processed_root)
    cached: dict[str, Any] | None = None
    if cache_path.exists():
        try:
            loaded = json.loads(cache_path.read_text())
            cached = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError):
            cached = None

    if cached is not None:
        reusable = all(cached.get(k) == expected.get(k) for k in expected)
        return reusable, rows if reusable else None

    # Backward-compatible bootstrap for the artifact produced before the sidecar
    # cache existed. Historical snapshots have always used the default 4/4
    # parameters. If source data is older than the artifact and the embedded
    # snapshot version matches, safely adopt it without a 10–15 minute rebuild.
    if min_games != DEFAULT_MIN_GAMES or recent_games != DEFAULT_RECENT_GAMES:
        return False, None
    if target.stat().st_mtime_ns < int(expected["newestSourceMtimeNs"]):
        return False, None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(expected, separators=(",", ":")))
    return True, rows


def _print_snapshot_summary(rows: list[dict[str, Any]], *, reused: bool) -> None:
    prefix = "ATTACK/SCHEME SNAPSHOTS REUSED" if reused else "ATTACK/SCHEME SNAPSHOTS"
    print(
        f"{prefix}: {len(rows):,} states | "
        f"seasons={len({r['season'] for r in rows})} | "
        f"teams={len({(r['season'], r['team']) for r in rows})}"
    )


def materialize_identity_snapshots(
    processed_root: Path,
    *,
    min_games: int = DEFAULT_MIN_GAMES,
    recent_games: int = DEFAULT_RECENT_GAMES,
    force: bool = False,
) -> Path:
    target = _snapshot_target(processed_root)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not force:
        reusable, cached_rows = _can_reuse_snapshots(
            processed_root,
            min_games=min_games,
            recent_games=recent_games,
        )
        if reusable and cached_rows is not None:
            _print_snapshot_summary(cached_rows, reused=True)
            return target

    rows = add_context_percentiles(
        build_identity_snapshots(
            load_team_games(processed_root),
            min_games=min_games,
            recent_games=recent_games,
        )
    )
    target.write_text(json.dumps(rows, separators=(",", ":")))
    manifest = _cache_manifest(processed_root, min_games=min_games, recent_games=recent_games)
    _snapshot_cache_path(processed_root).write_text(json.dumps(manifest, separators=(",", ":")))
    _print_snapshot_summary(rows, reused=False)
    return target


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    p.add_argument("--min-games", type=int, default=DEFAULT_MIN_GAMES)
    p.add_argument("--recent-games", type=int, default=DEFAULT_RECENT_GAMES)
    p.add_argument(
        "--force",
        action="store_true",
        help="rebuild all historical snapshots even when the cache is current",
    )
    a = p.parse_args()
    materialize_identity_snapshots(
        a.processed_root,
        min_games=a.min_games,
        recent_games=a.recent_games,
        force=a.force,
    )


if __name__ == "__main__":
    main()
