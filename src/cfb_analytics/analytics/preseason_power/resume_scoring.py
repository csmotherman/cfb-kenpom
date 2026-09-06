"""Thin, non-invasive wrapper around historical_cfp_selection.py for use by the
season simulator. historical_cfp_selection.py is NOT modified -- it is
explicitly documented as a retrospective-only model ("must not be presented as
a preseason simulator"). Its resume-feature machinery is generic and pure
(plain dict rows in, no disk I/O), so it works unmodified on synthetic
(simulated) game results; only THIS module does any simulating.

Ranking only is needed here, not a calibrated probability: the Monte Carlo
aggregate across trials already produces a real empirical selection
probability per team (the field size and AQ rule are applied exactly, every
trial), which is a more meaningful number than a single-season quota-shifted
logistic probability. So this wrapper stops at the raw logistic
decision-function score -- a committee-strength ranking signal -- and skips
historical_cfp_selection's quota-calibration step entirely.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from cfb_analytics.analytics.historical_cfp_selection import ResumeRow, build_resume_rows
from cfb_analytics.pipelines.publish_historical_cfp import CFP_SEASONS, _conference_champions, _selected_teams

from .common import CANONICAL_ROOT, RAW_ROOT, _load_json

HISTORICAL_RAW_ROOT = RAW_ROOT / "cfbd"


@lru_cache(maxsize=None)
def load_historical_resume_rows(seasons: tuple[int, ...] = CFP_SEASONS) -> tuple[ResumeRow, ...]:
    """Real, completed-season resume rows for every CFP-era season in the corpus."""
    rows: list[ResumeRow] = []
    for season in seasons:
        team_games_path = CANONICAL_ROOT / f"season={season}" / "team_games.json"
        selected = _selected_teams(HISTORICAL_RAW_ROOT, season)
        champions = _conference_champions(HISTORICAL_RAW_ROOT, season)
        rows.extend(build_resume_rows(season, _load_json(team_games_path), selected, champions))
    return tuple(rows)


def fit_resume_model(rows: tuple[ResumeRow, ...] | None = None) -> tuple[StandardScaler, LogisticRegression]:
    """Fit once on ALL historical rows pooled -- reused across every simulation trial, never refit per trial."""
    rows = rows if rows is not None else load_historical_resume_rows()
    X = np.asarray([row.features() for row in rows])
    y = np.asarray([row.selected for row in rows])
    scaler = StandardScaler().fit(X)
    model = LogisticRegression(C=1.0, max_iter=2_000, random_state=0)
    model.fit(scaler.transform(X), y)
    return scaler, model


def score_teams(rows: list[ResumeRow], scaler: StandardScaler, model: LogisticRegression) -> dict[str, float]:
    """team -> committee-strength score (higher = stronger resume; ranking only, not a probability)."""
    if not rows:
        return {}
    X = np.asarray([row.features() for row in rows])
    scores = model.decision_function(scaler.transform(X))
    return {row.team: float(score) for row, score in zip(rows, scores.tolist())}


__all__ = ["load_historical_resume_rows", "fit_resume_model", "score_teams", "ResumeRow", "build_resume_rows"]
