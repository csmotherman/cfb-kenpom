"""Model A2: the EXACT production Adj. Net, called through the real
production function (analytics.rating_model.fit_publication_composite),
not a reimplementation -- so this model's numbers are provably identical
to what would ship, not merely "in the same spirit."

Requires the prior season's own final possession ratings (fit once, on
that prior season's full closed dataset) to feed the current season's
weeks 1-3 opponent taper. This is the one place in this project a "future"
season legitimately touches an earlier one: the PRIOR season is fully
complete and closed by the time the target season starts, so this is not
leakage -- it mirrors exactly what production does today.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics.rating_model import (  # noqa: E402
    RIDGE_EQUIVALENT_POSSESSIONS,
    fit_publication_composite,
    prior_season_weight,
)


def _to_production_row(r: dict) -> dict:
    return {
        "season": r["season"],
        "gameId": r["gameId"],
        "team": r["team"],
        "opponent": r["opponent"],
        "classification": r.get("classification"),
        "opponent_classification": r.get("opponentClassification"),
        "neutral_site": r.get("neutralSite"),
        "home_away": r.get("homeAway"),
        "offensiveDrivePoints": r.get("offensiveDrivePoints"),
        "resolvedPointPossessions": r.get("resolvedPointPossessions"),
    }


def _fbs_rows(rows):
    return [r for r in rows if r.get("classification") == "fbs" and r.get("opponentClassification") == "fbs"]


def fit_prior_season_final_ratings(prior_season_rows: list[dict]) -> tuple[dict, dict] | tuple[None, None]:
    """Fit the prior season's COMPLETE (closed) dataset, no taper of its own
    (prior_weight=0 -- matches production, which only ever chains one level
    back). Returns internal-unit (offense, defense) dicts, i.e. already
    divided by RATING_SCALE=10, matching what fit_publication_composite's
    prior_offense/prior_defense arguments expect."""
    rows = _fbs_rows(prior_season_rows)
    if not rows:
        return None, None
    prod_rows = [_to_production_row(r) for r in rows if r.get("resolvedPointPossessions") is not None and r.get("offensiveDrivePoints") is not None]
    if not prod_rows:
        return None, None
    season = prod_rows[0]["season"]
    result = fit_publication_composite(prod_rows, season=season, cutoff="final", prior_weight=0.0)
    off = {t: v / 10.0 for t, v in result["ratings"]["AdjOff"].items()}
    deff = {t: v / 10.0 for t, v in result["ratings"]["AdjDef"].items()}
    return off, deff


class ProductionAdjNetModel:
    """Model A2. Unlike the other models in this project, `.fit()` here
    needs `site_week` (for the taper) and `prior_offense`/`prior_defense`
    (the prior season's final ratings, or None for a season with no usable
    prior season e.g. 2021 following the excluded 2020) -- the harness sets
    these per-week/per-season before calling fit()."""

    def __init__(self):
        self.name = "A2_AdjPPP_production_faithful"
        self.ratings: dict[str, float] = {}

    def fit(self, history_rows, site_week=None, prior_offense=None, prior_defense=None):
        rows = _fbs_rows(history_rows)
        prod_rows = [_to_production_row(r) for r in rows if r.get("resolvedPointPossessions") is not None and r.get("offensiveDrivePoints") is not None]
        if not prod_rows:
            self.ratings = {}
            return
        season = prod_rows[0]["season"]
        weight = prior_season_weight(site_week) if (prior_offense and prior_defense) else 0.0
        try:
            result = fit_publication_composite(
                prod_rows, season=season, cutoff=site_week,
                prior_offense=prior_offense, prior_defense=prior_defense, prior_weight=weight,
            )
        except Exception:
            self.ratings = {}
            return
        self.ratings = result["ratings"]["AdjNet"]

    def edge(self, home, away):
        h, a = self.ratings.get(home), self.ratings.get(away)
        return (h - a) if h is not None and a is not None else None

    def rating(self, team):
        return self.ratings.get(team)


class NoTaperAdjNetModel(ProductionAdjNetModel):
    """Same production function, same ridge, but prior_weight forced to 0 --
    isolates exactly what the prior-season-opponent taper contributes
    (Section 5's explicit question), holding everything else identical."""

    def __init__(self):
        super().__init__()
        self.name = "A3_AdjPPP_no_taper"

    def fit(self, history_rows, site_week=None, prior_offense=None, prior_defense=None):
        super().fit(history_rows, site_week=site_week, prior_offense=None, prior_defense=None)
