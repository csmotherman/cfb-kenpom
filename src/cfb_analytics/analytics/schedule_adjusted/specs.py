from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

ModelFamily = Literal["binomial", "gaussian"]


@dataclass(frozen=True)
class MetricSpec:
    """One schedule-adjusted matchup metric.

    Observations are always defined from the team-as-offense perspective.
    The model internally orients every metric so a larger latent value is
    better for the offense. This gives every fitted metric the same semantics:
    positive offensive effects are good offense and positive defensive effects
    are good defense.

    Most production metrics have one materialized numerator field. A small
    number are defined as the sum of multiple locked count fields; those extra
    fields live in ``additional_numerator_fields`` so the schedule-adjusted
    layer reconstructs the exact production definition rather than substituting
    a similarly named proxy.
    """

    name: str
    numerator_field: str
    denominator_field: str
    family: ModelFamily
    higher_is_better_offense: bool
    label: str
    unit: str
    additional_numerator_fields: tuple[str, ...] = ()

    @property
    def orientation(self) -> float:
        return 1.0 if self.higher_is_better_offense else -1.0

    @property
    def numerator_fields(self) -> tuple[str, ...]:
        return (self.numerator_field, *self.additional_numerator_fields)

    def numerator_value(self, row: Mapping[str, Any]) -> float | None:
        """Reconstruct the authoritative numerator from locked count fields."""
        total = 0.0
        for field in self.numerator_fields:
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            total += float(value)
        return total


# Research-only v1 registry. Every numerator/denominator pair is already
# materialized on the team-game contract. We fit one offense-facing version of
# a concept; the fitted defense effect is the schedule-adjusted defensive
# counterpart, so mirror "Allowed" metrics do not need a second model.
METRIC_SPECS: dict[str, MetricSpec] = {
    "successRate": MetricSpec("successRate", "successfulPlays", "successEligiblePlays", "binomial", True, "Success rate", "rate"),
    "rushSuccessRate": MetricSpec("rushSuccessRate", "rushSuccessfulPlays", "rushSuccessEligiblePlays", "binomial", True, "Rush success rate", "rate"),
    "passSuccessRate": MetricSpec("passSuccessRate", "passSuccessfulPlays", "passSuccessEligiblePlays", "binomial", True, "Pass success rate", "rate"),
    "standardDownSuccessRate": MetricSpec("standardDownSuccessRate", "standardDownSuccesses", "standardDownPlays", "binomial", True, "Standard-down success rate", "rate"),
    "passingDownSuccessRate": MetricSpec("passingDownSuccessRate", "passingDownSuccesses", "passingDownPlays", "binomial", True, "Passing-down success rate", "rate"),
    "thirdDownConversionRate": MetricSpec("thirdDownConversionRate", "thirdDownConversions", "thirdDownAttempts", "binomial", True, "Third-down conversion rate", "rate"),
    "fourthDownConversionRate": MetricSpec("fourthDownConversionRate", "fourthDownConversions", "fourthDownAttempts", "binomial", True, "Fourth-down conversion rate", "rate"),
    "down1SuccessRate": MetricSpec("down1SuccessRate", "down1SuccessfulPlays", "down1SuccessEligiblePlays", "binomial", True, "First-down success rate", "rate"),
    "down2SuccessRate": MetricSpec("down2SuccessRate", "down2SuccessfulPlays", "down2SuccessEligiblePlays", "binomial", True, "Second-down success rate", "rate"),
    "down3SuccessRate": MetricSpec("down3SuccessRate", "down3SuccessfulPlays", "down3SuccessEligiblePlays", "binomial", True, "Third-down play success rate", "rate"),
    "goalToGoSuccessRate": MetricSpec("goalToGoSuccessRate", "goalToGoSuccesses", "goalToGoPlays", "binomial", True, "Goal-to-go success rate", "rate"),
    "redZoneSuccessRate": MetricSpec("redZoneSuccessRate", "redZoneSuccesses", "redZonePlays", "binomial", True, "Red-zone play success rate", "rate"),
    "explosivePlayRate": MetricSpec("explosivePlayRate", "explosivePlays", "explosiveEligiblePlays", "binomial", True, "Explosive-play rate", "rate"),
    "rushExplosivePlayRate": MetricSpec("rushExplosivePlayRate", "rushExplosivePlays", "rushExplosiveEligiblePlays", "binomial", True, "Rush explosive-play rate", "rate"),
    "passExplosivePlayRate": MetricSpec("passExplosivePlayRate", "passExplosivePlays", "passExplosiveEligiblePlays", "binomial", True, "Pass explosive-play rate", "rate"),
    "scoringRatePerPossession": MetricSpec(
        "scoringRatePerPossession",
        "possessionTouchdowns",
        "possessions",
        "binomial",
        True,
        "Scoring rate per possession",
        "rate",
        additional_numerator_fields=("possessionFieldGoals", "otherScoringPossessions"),
    ),
    "touchdownRatePerPossession": MetricSpec("touchdownRatePerPossession", "possessionTouchdowns", "possessions", "binomial", True, "Touchdown rate per possession", "rate"),
    "touchdownRatePerOpportunity": MetricSpec("touchdownRatePerOpportunity", "opportunityTouchdowns", "scoringOpportunities", "binomial", True, "Touchdown rate per scoring opportunity", "rate"),
    "fieldGoalRatePerOpportunity": MetricSpec("fieldGoalRatePerOpportunity", "opportunityFieldGoals", "scoringOpportunities", "binomial", True, "Field-goal rate per scoring opportunity", "rate"),
    "emptyRatePerOpportunity": MetricSpec("emptyRatePerOpportunity", "emptyOpportunities", "scoringOpportunities", "binomial", False, "Empty scoring-opportunity rate", "rate"),
    "redZonePossessionTouchdownRate": MetricSpec("redZonePossessionTouchdownRate", "redZonePossessionTouchdowns", "redZonePossessions", "binomial", True, "Red-zone touchdown rate", "rate"),
    "sackRate": MetricSpec("sackRate", "sacksAllowed", "dropbacks", "binomial", False, "Sack rate allowed", "rate"),
    "havocRateAllowed": MetricSpec("havocRateAllowed", "havocPlaysAllowed", "havocEligiblePlays", "binomial", False, "Havoc rate allowed", "rate"),
    "yardsPerPlay": MetricSpec("yardsPerPlay", "basicYardageYards", "basicYardagePlays", "gaussian", True, "Yards per play", "yards"),
    "rushYardsPerAttempt": MetricSpec("rushYardsPerAttempt", "rushYards", "rushAttempts", "gaussian", True, "Rush yards per attempt", "yards"),
    "netPassYardsPerDropback": MetricSpec("netPassYardsPerDropback", "netPassYards", "dropbacks", "gaussian", True, "Net pass yards per dropback", "yards"),
    "yardsPerSuccessfulPlay": MetricSpec("yardsPerSuccessfulPlay", "successfulPlayYards", "successfulPlays", "gaussian", True, "Yards per successful play", "yards"),
    "rushYardsPerSuccessfulPlay": MetricSpec("rushYardsPerSuccessfulPlay", "rushSuccessfulPlayYards", "rushSuccessfulPlays", "gaussian", True, "Rush yards per successful play", "yards"),
    "passYardsPerSuccessfulPlay": MetricSpec("passYardsPerSuccessfulPlay", "passSuccessfulPlayYards", "passSuccessfulPlays", "gaussian", True, "Pass yards per successful play", "yards"),
    "yardsPerPossession": MetricSpec("yardsPerPossession", "possessionYards", "yardagePossessions", "gaussian", True, "Yards per possession", "yards"),
    "pointsPerResolvedPossession": MetricSpec("pointsPerResolvedPossession", "possessionPoints", "resolvedPointPossessions", "gaussian", True, "Points per resolved possession", "points"),
    "pointsPerOpportunity": MetricSpec("pointsPerOpportunity", "opportunityPoints", "resolvedPointOpportunities", "gaussian", True, "Points per scoring opportunity", "points"),
    "redZonePointsPerResolvedPossession": MetricSpec("redZonePointsPerResolvedPossession", "redZonePossessionPoints", "redZoneResolvedPointPossessions", "gaussian", True, "Red-zone points per resolved possession", "points"),
    "averageStartYardsToGoal": MetricSpec("averageStartYardsToGoal", "startYardsToGoalTotal", "possessions", "gaussian", False, "Average starting yards to goal", "yards"),
}

CORE_METRICS: tuple[str, ...] = (
    "successRate",
    "rushSuccessRate",
    "passSuccessRate",
    "explosivePlayRate",
    "yardsPerPlay",
    "pointsPerResolvedPossession",
    "pointsPerOpportunity",
    "thirdDownConversionRate",
    "redZonePossessionTouchdownRate",
    "sackRate",
    "havocRateAllowed",
)
