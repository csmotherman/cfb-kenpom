"""Grading-philosophy model definitions (Section 3 of the request).

Every opponent-adjusted model here is the SAME production solver
(`iterative_ratings.fit_metric_ratings`, the exact function production
Adj. Net calls) pointed at a different (numerator, denominator) spec, or
`iterative_ratings.fit_srs` for the MOV/SRS family. No model gets a
bespoke, hand-rolled fitting routine -- a difference in results reflects
the grading philosophy (what gets measured), not a difference in how the
opponent network gets solved.

Every model exposes the same two-method interface:
  fit(history_rows) -> None        (uses ONLY rows strictly before cutoff)
  edge(home, away) -> float | None (this model's predicted home-minus-away
                                     rating differential; NOT yet converted
                                     to a point-margin prediction -- that
                                     conversion is fit separately, on
                                     training data only, per Section 7)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings, fit_srs  # noqa: E402

RIDGE_EQUIVALENT_POSSESSIONS = 10.0  # production value


def _fbs_rows(rows):
    return [r for r in rows if r.get("classification") == "fbs" and r.get("opponentClassification") == "fbs"]


class MetricSpecModel:
    """Opponent-adjusted rating for any (numerator, denominator) spec via the
    production `fit_metric_ratings` solver -- covers Models A (possession
    PPP), D (EPA), E (Success Rate), F (Explosiveness) uniformly."""

    def __init__(self, name: str, num_field: str, den_field: str, shrinkage: float = RIDGE_EQUIVALENT_POSSESSIONS):
        self.name = name
        self.num_field = num_field
        self.den_field = den_field
        self.shrinkage = shrinkage
        self.offense: dict[str, float] = {}
        self.defense: dict[str, float] = {}
        self.converged = True
        self.teams = 0

    def fit(self, history_rows):
        rows = [
            {"team": r["team"], "opponent": r["opponent"], self.num_field: r.get(self.num_field), self.den_field: r.get(self.den_field)}
            for r in _fbs_rows(history_rows)
        ]
        fitted = fit_metric_ratings(rows, (self.name, self.num_field, self.den_field), shrinkage=self.shrinkage)
        self.offense = fitted.get("offense", {})
        self.defense = fitted.get("defense", {})
        self.converged = bool(fitted.get("converged", True))
        self.teams = len(self.offense)

    def net(self, team):
        if team not in self.offense or team not in self.defense:
            return None
        return self.offense[team] + self.defense[team]

    rating = net  # uniform accessor across model classes

    def edge(self, home, away):
        h, a = self.net(home), self.net(away)
        return (h - a) if h is not None and a is not None else None


class SRSModel:
    """Model B: opponent-adjusted scoring margin (SRS), via the production
    `fit_srs` solver. `margin_cap` (points) optionally clips each game's
    margin before fitting -- tests the "reasonable capped MOV" variant."""

    def __init__(self, name: str = "SRS", margin_cap: float | None = None):
        self.name = name
        self.margin_cap = margin_cap
        self.ratings: dict[str, float] = {}
        self.converged = True

    def fit(self, history_rows):
        rows = []
        for r in _fbs_rows(history_rows):
            if r.get("homeAway") not in ("home", "away"):
                continue
            pf, pa = r.get("pointsFor"), r.get("pointsAgainst")
            if pf is None or pa is None:
                continue
            margin = pf - pa
            if r["homeAway"] == "away":
                continue  # avoid double-counting; SRS games are built from one row per game below
            if self.margin_cap is not None:
                margin = max(-self.margin_cap, min(self.margin_cap, margin))
            rows.append({
                "gameId": r["gameId"], "homeTeam": r["team"], "awayTeam": r["opponent"], "target_margin": margin,
            })
        fitted = fit_srs(rows)
        self.ratings = fitted.get("ratings", {})
        self.converged = bool(fitted.get("converged", True))

    def edge(self, home, away):
        h, a = self.ratings.get(home), self.ratings.get(away)
        return (h - a) if h is not None and a is not None else None

    def rating(self, team):
        return self.ratings.get(team)


class RawPPPModel:
    """Model C: raw net points per resolved possession, NO opponent
    adjustment -- each team's own (offense PPP - defense PPP allowed), no
    recursive solve. Isolates how much value the opponent adjustment itself
    adds (compare against Model A, the identical spec WITH adjustment)."""

    def __init__(self, name: str = "RawPPP"):
        self.name = name
        self.net_rating: dict[str, float] = {}

    def fit(self, history_rows):
        off_pts, off_poss = {}, {}
        def_pts, def_poss = {}, {}
        for r in _fbs_rows(history_rows):
            team, opp = r["team"], r["opponent"]
            pts, poss = r.get("offensiveDrivePoints"), r.get("resolvedPointPossessions")
            if pts is None or poss is None or poss <= 0:
                continue
            off_pts[team] = off_pts.get(team, 0.0) + pts
            off_poss[team] = off_poss.get(team, 0.0) + poss
            def_pts[opp] = def_pts.get(opp, 0.0) + pts
            def_poss[opp] = def_poss.get(opp, 0.0) + poss
        teams = set(off_poss) | set(def_poss)
        self.net_rating = {}
        for t in teams:
            o = off_pts.get(t, 0.0) / off_poss[t] if off_poss.get(t) else None
            d = def_pts.get(t, 0.0) / def_poss[t] if def_poss.get(t) else None
            if o is not None and d is not None:
                self.net_rating[t] = o - d

    def edge(self, home, away):
        h, a = self.net_rating.get(home), self.net_rating.get(away)
        return (h - a) if h is not None and a is not None else None

    def rating(self, team):
        return self.net_rating.get(team)


def build_models() -> dict[str, object]:
    return {
        "A_AdjPPP": MetricSpecModel("PossessionPoints", "offensiveDrivePoints", "resolvedPointPossessions"),
        "B_SRS_uncapped": SRSModel("SRS_uncapped", margin_cap=None),
        "B_SRS_cap28": SRSModel("SRS_cap28", margin_cap=28.0),
        "C_RawPPP": RawPPPModel(),
        "D_AdjEPA": MetricSpecModel("EPA", "epaSum", "epaPlays"),
        "E_AdjSuccess": MetricSpecModel("Success", "successfulPlays", "successEligiblePlays"),
        "F_AdjExplosive": MetricSpecModel("Explosive", "explosivePlays", "explosiveEligiblePlays"),
    }
