"""Explicit direction and matchup semantics for model features."""
from __future__ import annotations
HIGHER_IS_BETTER="HIGHER_IS_BETTER";HIGHER_IS_WORSE="HIGHER_IS_WORSE";FEATURE_DIRECTION_VERSION="model-feature-direction-v1"
MATCHUP_FAMILIES=(
("Success","successRate","successRateAllowed","successRateEdge"),
("Explosive","explosivePlayRate","explosivePlayRateAllowed","explosiveRateEdge"),
("YardsPerPlay","yardsPerPlay","yardsAllowedPerPlay","yardsPerPlayEdge"),
("YardsPerPossession","yardsPerPossession","yardsAllowedPerPossession","yardsPerPossessionEdge"),
("Finishing","pointsPerOpportunity","pointsPerOpportunityAllowed","finishingEdge"),
("FieldPosition","averageStartOwnYardLine","averageStartOwnYardLineAllowed","fieldPositionEdge"),
)
MODEL_FEATURE_CONTRACT={name:{"raw_offense":off,"raw_defense":deff,"raw_edge":edge,"raw_offense_direction":HIGHER_IS_BETTER,"raw_defense_direction":HIGHER_IS_WORSE,"raw_matchup_formula":"offense + opponent_allowed","iterative_offense_direction":HIGHER_IS_BETTER,"iterative_defense_direction":HIGHER_IS_BETTER,"iterative_matchup_formula":"offense_rating - opponent_defense_rating"} for name,off,deff,edge in MATCHUP_FAMILIES}
TURNOVER_CONTRACT={"metric":"turnoverMarginPerGame","direction":HIGHER_IS_BETTER,"definition":"takeaways - giveaways per prior game"}
def raw_matchup_value(offense_value,opponent_allowed_value):return float(offense_value)+float(opponent_allowed_value)
def iterative_matchup_value(offense_rating,opponent_defense_rating):return float(offense_rating)-float(opponent_defense_rating)
