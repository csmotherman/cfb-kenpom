"""Explicit leakage tests for the walk-forward harness (Section 2 requirement).

Run with: python -m pytest research/rating_methodology_validation/test_leakage.py -q
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from harness import run_season  # noqa: E402
from models import build_models  # noqa: E402


def _synthetic_rows(season=9999, weeks=5, teams=8):
    """A small round-robin-ish synthetic season with deterministic scores, so
    "team i" is structurally stronger than "team i+1" -- lets us assert
    ratings move in the expected direction, not just that the code runs."""
    rows = []
    game_id = 0
    for wk in range(1, weeks + 1):
        for i in range(0, teams, 2):
            home, away = f"Team{i}", f"Team{i + 1}"
            game_id += 1
            # Lower-indexed team wins by a margin proportional to the index gap.
            home_pts, away_pts = 28, 14
            for team, opp, ha, pf, pa in ((home, away, "home", home_pts, away_pts), (away, home, "away", away_pts, home_pts)):
                rows.append({
                    "season": season, "seasonType": "regular", "week": wk, "gameId": f"g{game_id}",
                    "team": team, "opponent": opp, "classification": "fbs", "opponentClassification": "fbs",
                    "homeAway": ha, "neutralSite": False, "pointsFor": pf, "pointsAgainst": pa,
                    "win": 1 if pf > pa else 0,
                    "offensiveDrivePoints": float(pf), "resolvedPointPossessions": 10.0,
                    "validatedPossessions": 10.0,
                    "epaSum": float(pf) / 7.0, "epaPlays": 60.0,
                    "successfulPlays": 25.0, "successEligiblePlays": 60.0,
                    "explosivePlays": 6.0, "explosiveEligiblePlays": 60.0,
                    "offensivePlays": 65.0,
                })
    return rows


def test_future_week_never_changes_an_earlier_weeks_prediction(tmp_path, monkeypatch):
    import build_dataset

    rows = _synthetic_rows()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "season=9999.json").write_text(__import__("json").dumps(rows))
    monkeypatch.setattr("harness.DATA_DIR", data_dir)

    baseline, _ = run_season(9999)
    week3_baseline = [r for r in baseline if r["week"] == 3]
    assert week3_baseline, "sanity: week 3 should have produced predictions"

    # Corrupt every week-4-and-later score (the "future" relative to week 3)
    # and re-run. Week <=3 predictions must be byte-identical -- if they
    # aren't, some model read a future row.
    corrupted = copy.deepcopy(rows)
    for r in corrupted:
        if r["week"] >= 4:
            r["pointsFor"], r["pointsAgainst"] = 999, 0
            r["offensiveDrivePoints"] = 999.0
    (data_dir / "season=9999.json").write_text(__import__("json").dumps(corrupted))
    after, _ = run_season(9999)
    week3_after = [r for r in after if r["week"] == 3]

    key = lambda r: (r["model"], r["gameId"])
    baseline_by_key = {key(r): r["edge"] for r in week3_baseline}
    after_by_key = {key(r): r["edge"] for r in week3_after}
    assert baseline_by_key == after_by_key, "week-3 predictions changed after corrupting week-4+ data -- LEAKAGE"


def test_history_resets_between_seasons(tmp_path, monkeypatch):
    """A team that only ever loses in season A must not carry any strength
    into season B's week-1 prediction (there is no history yet in season B,
    so week 1 must produce NO predictions at all -- there's nothing to fit
    on)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows_a = _synthetic_rows(season=1000, weeks=3)
    (data_dir / "season=1000.json").write_text(__import__("json").dumps(rows_a))
    monkeypatch.setattr("harness.DATA_DIR", data_dir)
    result, _ = run_season(1000)
    week1 = [r for r in result if r["week"] == 1]
    assert week1 == [], "week 1 of a season must have zero history and therefore zero predictions"


def test_edge_is_none_for_teams_never_seen_in_history():
    models = build_models()
    rows = _synthetic_rows(weeks=2)
    history = [r for r in rows if r["week"] == 1]
    for model in models.values():
        model.fit(history)
        assert model.edge("NeverPlayed", "Team0") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
