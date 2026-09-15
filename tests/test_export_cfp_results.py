"""Deterministic tests for CFP field/champion/runner-up extraction.

Uses synthetic playoff-tagged game dicts (matching CFBD's real `playoff`
field shape) rather than real raw files, so these stay fast and independent
of what season data happens to be on disk.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import export_cfp_results as cfp  # noqa: E402


def _game(home_id, home_team, away_id, away_team, round_, home_points=None, away_points=None, completed=True):
    return {
        "homeId": home_id,
        "homeTeam": home_team,
        "awayId": away_id,
        "awayTeam": away_team,
        "homePoints": home_points,
        "awayPoints": away_points,
        "completed": completed,
        "playoff": {"round": round_},
    }


def _write_season(tmp_path, season, games):
    directory = tmp_path / f"data/raw/cfbd/season={season}/season_type=postseason/week=01"
    directory.mkdir(parents=True)
    (directory / "games.json").write_text(json.dumps(games))


def test_participants_are_union_of_every_playoff_tagged_game(tmp_path, monkeypatch):
    monkeypatch.setattr(cfp, "REPO", tmp_path)
    games = [
        _game(1, "A", 2, "B", "quarterfinal", 30, 10),
        _game(3, "C", 4, "D", "quarterfinal", 20, 24),
        _game(4, "D", 1, "A", "semifinal", 17, 21),
        _game(1, "A", 5, "E", "championship", 28, 14),
    ]
    _write_season(tmp_path, 2030, games)
    payload = cfp.build_season_payload(2030)
    assert payload is not None
    team_ids = {p["teamId"] for p in payload["participants"]}
    assert team_ids == {1, 2, 3, 4, 5}
    assert payload["fieldSize"] == 5


def test_champion_and_runner_up_come_from_championship_score():
    games = [_game(1, "Home Team", 2, "Away Team", "championship", 28, 14)]
    champion, runner_up = cfp._championship_result(games[0])
    assert champion == {"teamId": 1, "team": "Home Team"}
    assert runner_up == {"teamId": 2, "team": "Away Team"}


def test_away_winner_is_still_correctly_identified_as_champion():
    games = [_game(1, "Home Team", 2, "Away Team", "championship", 14, 28)]
    champion, runner_up = cfp._championship_result(games[0])
    assert champion == {"teamId": 2, "team": "Away Team"}
    assert runner_up == {"teamId": 1, "team": "Home Team"}


def test_champion_is_null_when_championship_not_yet_played(tmp_path, monkeypatch):
    monkeypatch.setattr(cfp, "REPO", tmp_path)
    games = [
        _game(1, "A", 2, "B", "semifinal", 30, 10),
        _game(3, "C", 4, "D", "semifinal", 20, 24),
        _game(1, "A", 3, "C", "championship", None, None, completed=False),
    ]
    _write_season(tmp_path, 2031, games)
    payload = cfp.build_season_payload(2031)
    assert payload is not None
    assert payload["champion"] is None
    assert payload["runnerUp"] is None
    # The field itself is still populated even though the title game hasn't happened.
    assert {p["teamId"] for p in payload["participants"]} == {1, 2, 3, 4}


def test_season_with_no_raw_postseason_directory_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cfp, "REPO", tmp_path)
    assert cfp.build_season_payload(2099) is None


def test_non_playoff_bowl_games_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(cfp, "REPO", tmp_path)
    games = [
        {"homeId": 1, "homeTeam": "A", "awayId": 2, "awayTeam": "B", "homePoints": 30, "awayPoints": 10, "completed": True, "playoff": None},
        _game(3, "C", 4, "D", "championship", 21, 20),
    ]
    _write_season(tmp_path, 2032, games)
    payload = cfp.build_season_payload(2032)
    assert payload is not None
    assert {p["teamId"] for p in payload["participants"]} == {3, 4}
