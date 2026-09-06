"""Retrospective, out-of-season CFP selection model.

This model measures the strength of a completed regular-season resume. It is not
a preseason simulator and must not be presented as one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

MODEL_VERSION = "historical-cfp-resume-v1"
FEATURE_NAMES = (
    "winPercentage",
    "losses",
    "strengthOfSchedule",
    "qualityWins",
    "scoringMarginPerGame",
    "conferenceChampion",
)


@dataclass(frozen=True)
class ResumeRow:
    season: int
    team_id: int
    team: str
    wins: int
    losses: int
    win_percentage: float
    strength_of_schedule: float
    quality_wins: int
    scoring_margin_per_game: float
    conference_champion: bool
    selected: bool

    def features(self) -> list[float]:
        return [
            self.win_percentage,
            float(self.losses),
            self.strength_of_schedule,
            float(self.quality_wins),
            self.scoring_margin_per_game,
            float(self.conference_champion),
        ]


def build_resume_rows(
    season: int,
    team_games: Iterable[dict],
    selected_teams: set[str],
    conference_champions: set[str],
) -> list[ResumeRow]:
    """Build one final regular-season resume per FBS team."""
    games_by_team: dict[int, list[dict]] = {}
    for game in team_games:
        if game.get("season_type", game.get("seasonType")) != "regular":
            continue
        games_by_team.setdefault(int(game["team_id"]), []).append(game)

    records = {
        team_id: (
            sum(int(game.get("win") or 0) for game in games),
            sum(int(game.get("loss") or 0) for game in games),
        )
        for team_id, games in games_by_team.items()
    }
    win_pct = {
        team_id: wins / (wins + losses) if wins + losses else 0.0
        for team_id, (wins, losses) in records.items()
    }

    rows: list[ResumeRow] = []
    for team_id, games in games_by_team.items():
        wins, losses = records[team_id]
        opponents = [int(game["opponent_id"]) for game in games if int(game["opponent_id"]) in win_pct]
        sos = float(np.mean([win_pct[opponent] for opponent in opponents])) if opponents else 0.0
        quality_wins = sum(
            1
            for game in games
            if int(game.get("win") or 0) == 1 and win_pct.get(int(game["opponent_id"]), 0.0) >= 0.70
        )
        margin = float(np.mean([
            float(game.get("points_for") or 0) - float(game.get("points_against") or 0)
            for game in games
        ]))
        team = str(games[0]["team"])
        rows.append(ResumeRow(
            season=season,
            team_id=team_id,
            team=team,
            wins=wins,
            losses=losses,
            win_percentage=win_pct[team_id],
            strength_of_schedule=sos,
            quality_wins=quality_wins,
            scoring_margin_per_game=margin,
            conference_champion=team in conference_champions,
            selected=team in selected_teams,
        ))
    return sorted(rows, key=lambda row: row.team)


def _quota_calibrated_probabilities(logits: np.ndarray, field_size: int) -> np.ndarray:
    """Shift the intercept until probabilities sum to the known field size."""
    low, high = -50.0, 50.0
    for _ in range(120):
        midpoint = (low + high) / 2.0
        values = np.clip(logits + midpoint, -40.0, 40.0)
        probabilities = 1.0 / (1.0 + np.exp(-values))
        if float(probabilities.sum()) > field_size:
            high = midpoint
        else:
            low = midpoint
    values = np.clip(logits + ((low + high) / 2.0), -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-values))


def leave_one_season_out(rows: Iterable[ResumeRow]) -> tuple[list[dict], dict]:
    """Score every season with a model that was not trained on that season."""
    all_rows = list(rows)
    seasons = sorted({row.season for row in all_rows})
    results: list[dict] = []
    for season in seasons:
        train = [row for row in all_rows if row.season != season]
        holdout = [row for row in all_rows if row.season == season]
        field_size = sum(row.selected for row in holdout)
        if not train or not holdout or field_size <= 0:
            raise ValueError(f"season {season} cannot be scored")
        scaler = StandardScaler().fit(np.asarray([row.features() for row in train]))
        model = LogisticRegression(C=1.0, max_iter=2_000, random_state=0)
        model.fit(scaler.transform(np.asarray([row.features() for row in train])), np.asarray([row.selected for row in train]))
        logits = model.decision_function(scaler.transform(np.asarray([row.features() for row in holdout])))
        probabilities = _quota_calibrated_probabilities(np.asarray(logits), field_size)
        order = np.argsort(-probabilities)
        ranks = {int(index): rank + 1 for rank, index in enumerate(order)}
        for index, (row, probability) in enumerate(zip(holdout, probabilities, strict=True)):
            results.append({
                "season": row.season,
                "teamId": row.team_id,
                "team": row.team,
                "wins": row.wins,
                "losses": row.losses,
                "winPercentage": round(row.win_percentage, 6),
                "strengthOfSchedule": round(row.strength_of_schedule, 6),
                "qualityWins": row.quality_wins,
                "scoringMarginPerGame": round(row.scoring_margin_per_game, 3),
                "conferenceChampion": row.conference_champion,
                "actualSelected": row.selected,
                "selectionChance": round(float(probability), 6),
                "selectionRank": ranks[index],
                "fieldSize": field_size,
                "modelVersion": MODEL_VERSION,
                "valueType": "RETROSPECTIVE",
            })

    actual = np.asarray([float(row["actualSelected"]) for row in results])
    predicted = np.asarray([float(row["selectionChance"]) for row in results])
    clipped = np.clip(predicted, 1e-9, 1 - 1e-9)
    top_k_hits = sum(
        int(row["actualSelected"])
        for season in seasons
        for row in sorted((item for item in results if item["season"] == season), key=lambda item: item["selectionChance"], reverse=True)[:sum(item["actualSelected"] for item in results if item["season"] == season)]
    )
    audit = {
        "modelVersion": MODEL_VERSION,
        "evaluation": "leave-one-season-out",
        "seasons": seasons,
        "teamSeasons": len(results),
        "actualSelections": int(actual.sum()),
        "brierScore": round(float(np.mean((predicted - actual) ** 2)), 6),
        "logLoss": round(float(-np.mean(actual * np.log(clipped) + (1 - actual) * np.log(1 - clipped))), 6),
        "topFieldAccuracy": round(top_k_hits / float(actual.sum()), 6),
        "maxFieldSizeSumError": round(max(abs(sum(item["selectionChance"] for item in results if item["season"] == season) - sum(item["actualSelected"] for item in results if item["season"] == season)) for season in seasons), 6),
        "features": list(FEATURE_NAMES),
    }
    return sorted(results, key=lambda row: (row["season"], row["selectionRank"])), audit


def resume_row_asdict(row: ResumeRow) -> dict:
    return asdict(row)
