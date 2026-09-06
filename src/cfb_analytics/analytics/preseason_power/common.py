"""Shared IO and identity helpers for the preseason power-rating research track.

Isolated research module: reads existing raw/canonical artifacts, writes only
under ``data/research/preseason_power/``. Does not modify any production
pipeline, model, or the 2026 prospective outputs.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
RAW_ROOT = REPO_ROOT / "data" / "raw"
CANONICAL_ROOT = REPO_ROOT / "data" / "canonical"
RESEARCH_OUTPUT_ROOT = REPO_ROOT / "data" / "research" / "preseason_power"
COACHING_HISTORY_ROOT = REPO_ROOT / "data" / "research" / "coaching_history"

# Seasons with a materialized data/canonical/season=Y/team_games.json (i.e. a
# season we can both build a prior *from* and score Week 1 predictions
# *against*). 2020 is intentionally absent repo-wide (COVID season, no
# canonical team_games). 2010-2013 only have fbs_membership, no team_games.
COMPLETE_SEASONS: tuple[int, ...] = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def prior_seasons(target_season: int, n: int = 3) -> list[int]:
    """The n most recent COMPLETE_SEASONS strictly before target_season, most recent first."""
    candidates = [s for s in COMPLETE_SEASONS if s < target_season]
    return sorted(candidates, reverse=True)[:n]


def walkforward_target_seasons(min_priors: int = 1) -> list[int]:
    """Target seasons with at least min_priors prior COMPLETE_SEASONS available."""
    return [s for s in COMPLETE_SEASONS if len(prior_seasons(s, n=min_priors)) >= min_priors]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


@lru_cache(maxsize=None)
def load_team_games(season: int) -> list[dict[str, Any]]:
    path = CANONICAL_ROOT / f"season={season}" / "team_games.json"
    if not path.exists():
        return []
    return _load_json(path)


@lru_cache(maxsize=None)
def load_recruiting_team_ranks(season: int) -> dict[str, dict[str, Any]]:
    """Team-level composite recruiting class rank/points for the class entering `season`."""
    path = RAW_ROOT / "cfbd_directory_history" / f"season={season}" / "recruiting_teams.json"
    if not path.exists():
        return {}
    payload = _load_json(path)
    rows = payload.get("payload", payload) if isinstance(payload, dict) else payload
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        team = row.get("team")
        if not team:
            continue
        out[str(team)] = {"rank": row.get("rank"), "points": row.get("points")}
    return out


@lru_cache(maxsize=None)
def load_roster(season: int) -> list[dict[str, Any]]:
    path = RAW_ROOT / "cfbd_players" / f"season={season}" / "roster.json"
    if not path.exists():
        return []
    return _load_json(path)


@lru_cache(maxsize=None)
def load_recruiting_players(season: int) -> list[dict[str, Any]]:
    """Individual signees for the class entering `season` (CFBD /recruiting/players)."""
    path = RAW_ROOT / "cfbd_players" / f"season={season}" / "recruiting_players.json"
    if not path.exists():
        return []
    payload = _load_json(path)
    rows = payload.get("payload", payload) if isinstance(payload, dict) else payload
    return rows


@lru_cache(maxsize=None)
def load_coaching_history() -> list[dict[str, Any]]:
    """Full FBS head-coach career history (CFBD /coaches): one row per coach, each with a
    `seasons` list of {school, year, ...} entries back to their first FBS HC job.

    Only coach IDENTITY and tenure (school, year) may be read from a season entry here.
    wins/losses/srs/spOverall/spOffense/spDefense on an entry are that season's own final
    result -- or, for the still-unplayed 2026 stub entries, CFBD's SP+ preseason
    projection -- and this research track bans both target-season outcomes and SP+/AP/
    Vegas inputs. See `load_coach_year3plus_records` for the leakage-safe rating fields.
    """
    path = COACHING_HISTORY_ROOT / "fbs_coaches_full_history.json"
    if not path.exists():
        return []
    return _load_json(path)


@lru_cache(maxsize=None)
def load_coach_year3plus_records() -> list[dict[str, Any]]:
    """Coach-season records restricted to yearAtSchool>=3 (an established system, past the
    honeymoon/transition seasons). `offense`/`defense` on each entry are this repo's own
    leakage-safe points-scale ratings (`historical_priors.season_points_ratings(year,
    shrinkage=0.0)`), verified to match that function's live output exactly -- not SP+.
    """
    path = COACHING_HISTORY_ROOT / "coach_year3plus_records_2014_2025.json"
    if not path.exists():
        return []
    return _load_json(path)


@lru_cache(maxsize=None)
def load_player_season_stats(season: int) -> list[dict[str, Any]]:
    path = RAW_ROOT / "cfbd_players" / f"season={season}" / "player_season_stats.json"
    if not path.exists():
        return []
    return _load_json(path)


@lru_cache(maxsize=None)
def load_portal(season: int) -> list[dict[str, Any]]:
    """Transfer-portal moves for the offseason cycle heading into `season`."""
    path = RAW_ROOT / "cfbd_directory_history" / f"season={season}" / "portal.json"
    if not path.exists():
        return []
    payload = _load_json(path)
    rows = payload.get("payload", payload) if isinstance(payload, dict) else payload
    return rows


_NAME_STRIP = re.compile(r"[^a-z ]")


def normalize_name(name: str) -> str:
    """Loose join key for name-based matching (portal has no player id)."""
    lowered = name.lower().strip()
    lowered = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", lowered)
    lowered = _NAME_STRIP.sub("", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def pivot_player_season_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """playerId -> {'category.statType': float, ..., 'team': team, 'player': name, 'position': pos}."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        pid = row.get("playerId")
        if not pid:
            continue
        stat = row.get("stat")
        try:
            value = float(stat)
        except (TypeError, ValueError):
            continue
        entry = out.setdefault(str(pid), {"team": row.get("team"), "player": row.get("player"), "position": row.get("position")})
        key = f"{row.get('category')}.{row.get('statType')}"
        entry[key] = value
    return out


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})
