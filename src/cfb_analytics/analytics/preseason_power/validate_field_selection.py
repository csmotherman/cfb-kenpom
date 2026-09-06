"""Validates the AQ + seeding + resume-ranking machinery (standings.apply_aq_and_seed)
against REAL, completed seasons -- ground-truth conference champions and the real
12-team CFP field, sourced the same way historical_cfp_selection's own training
labels are. This isolates bugs in the field-selection RULE from noise in the rating
model or the conference-standings simulation (validated separately -- see
PRESEASON_POWER_RATING_RESEARCH.md and test_season_simulator_2026.py).

Validated against 2024 and 2025, NOT 2026: both real completed seasons used the
"pooled top-5 ranked conference champions" AQ rule (confirmed live, Sept 2026 --
see standings.apply_aq_and_seed's docstring for the Duke/2025-ACC case this
surfaced). The 2026 rule (guaranteed P4 auto-bids) was changed specifically
because of that 2025 outcome and has not been used in any completed season, so
it cannot be historically validated the same way -- only the machinery it shares
with the pre-2026 rule (resume scoring, seeding, field-size handling) is checked
here.

The resume model here is fit on ALL historical seasons INCLUDING the one being
validated (not leave-one-out), so this checks the selection MACHINERY, not
out-of-sample predictive accuracy -- that's already validated in
docs/HISTORICAL_CFP_SELECTION_MODEL.md's leave-one-season-out metrics.
"""
from __future__ import annotations

import json

from cfb_analytics.pipelines.publish_historical_cfp import _conference_champions, _selected_teams

from .common import CANONICAL_ROOT, _load_json
from .conference_structure import load_team_conferences
from .resume_scoring import HISTORICAL_RAW_ROOT, build_resume_rows, fit_resume_model, load_historical_resume_rows, score_teams
from .standings import apply_aq_and_seed

VALIDATE_SEASONS = (2024, 2025)


def validate_against_season(season: int) -> dict:
    team_games = _load_json(CANONICAL_ROOT / f"season={season}" / "team_games.json")
    actual_selected = _selected_teams(HISTORICAL_RAW_ROOT, season)
    actual_champions_set = _conference_champions(HISTORICAL_RAW_ROOT, season)
    team_conf = load_team_conferences(season)

    conference_champions: dict[str, str] = {}
    for team in actual_champions_set:
        conf = team_conf.get(team, {}).get("conference")
        if conf:
            conference_champions[conf] = team

    resume_rows = build_resume_rows(season, team_games, actual_selected, actual_champions_set)
    scaler, model = fit_resume_model(load_historical_resume_rows())
    scores = score_teams(list(resume_rows), scaler, model)

    predicted_field = apply_aq_and_seed(scores, conference_champions, team_conf, season=season)
    predicted_teams = {row["team"] for row in predicted_field}

    return {
        "season": season,
        "actual_field": sorted(actual_selected),
        "predicted_field": sorted(predicted_teams),
        "matched": sorted(predicted_teams & actual_selected),
        "missed_by_model": sorted(actual_selected - predicted_teams),
        "false_positives": sorted(predicted_teams - actual_selected),
        "field_size_match": len(predicted_teams) == len(actual_selected),
        "accuracy": len(predicted_teams & actual_selected) / len(actual_selected) if actual_selected else None,
        "predicted_field_detail": predicted_field,
    }


def validate_against_2025() -> dict:
    """Kept for backwards compatibility; see validate_against_season / main() for the full check."""
    return validate_against_season(2025)


def main() -> None:
    for season in VALIDATE_SEASONS:
        print(json.dumps(validate_against_season(season), indent=2))


if __name__ == "__main__":
    main()
