from __future__ import annotations

from dataclasses import dataclass

PROFILE_VERSION = "team-profile-v3-attack-scheme-research"


@dataclass(frozen=True)
class ProfileMetric:
    key: str
    section: str
    label: str
    higher_is_better: bool
    role: str
    status: str
    description: str


PROFILE_METRICS = (
    ProfileMetric("identity_rushing_attack", "offense", "Rushing Attack", True, "opponent_adjusted_composite", "RESEARCH", "Composite of opponent-adjusted rushing success, rushing explosiveness, and yards on successful rushes."),
    ProfileMetric("identity_passing_attack", "offense", "Passing Attack", True, "opponent_adjusted_composite", "RESEARCH", "Composite of opponent-adjusted passing success, passing explosiveness, and yards on successful pass plays."),
    ProfileMetric("oa_run_efficiency_off", "offense", "Run Success", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted rushing success strength."),
    ProfileMetric("oa_pass_efficiency_off", "offense", "Pass Success", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted passing success strength."),
    ProfileMetric("oa_run_explosiveness_off", "offense", "Run Explosiveness", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted rushing explosive-play creation strength."),
    ProfileMetric("oa_pass_explosiveness_off", "offense", "Pass Explosiveness", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted passing explosive-play creation strength."),
    ProfileMetric("oa_run_success_yards_off", "offense", "Run Successful-Play Yards", True, "opponent_adjusted_quality", "RESEARCH", "Opponent-adjusted yards gained on successful rushing plays."),
    ProfileMetric("oa_pass_success_yards_off", "offense", "Pass Successful-Play Yards", True, "opponent_adjusted_quality", "RESEARCH", "Opponent-adjusted yards gained on successful pass plays."),
    ProfileMetric("oa_success_off", "offense", "Overall Efficiency", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted down-and-distance success strength."),
    ProfileMetric("oa_explosiveness_off", "offense", "Explosiveness", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted explosive-play creation strength."),
    ProfileMetric("oa_third_down_off", "offense", "Third-Down Efficiency", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted third-down success strength."),
    ProfileMetric("oa_finishing_off", "offense", "Finishing", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted points per scoring opportunity strength."),
    ProfileMetric("drive_scoring_off", "offense", "Drive Scoring Efficiency", True, "opponent_adjusted_quality", "RESEARCH", "Opponent-adjusted offensive points per drive from the dedicated PPD model."),
    ProfileMetric("turnover_avoidance", "offense", "Turnover Avoidance", True, "quality", "DEFERRED", "No profile rate until a turnover opportunity denominator is independently validated."),

    ProfileMetric("identity_rushing_defense", "defense", "Rushing Defense", True, "opponent_adjusted_composite", "RESEARCH", "Composite opponent-adjusted rushing suppression profile."),
    ProfileMetric("identity_passing_defense", "defense", "Passing Defense", True, "opponent_adjusted_composite", "RESEARCH", "Composite opponent-adjusted passing suppression profile."),
    ProfileMetric("oa_run_efficiency_def", "defense", "Run Success Defense", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted rushing suppression strength."),
    ProfileMetric("oa_pass_efficiency_def", "defense", "Pass Success Defense", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted passing suppression strength."),
    ProfileMetric("oa_success_def", "defense", "Overall Defense", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted down-and-distance suppression strength."),
    ProfileMetric("oa_explosiveness_def", "defense", "Explosive Prevention", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted explosive-play prevention strength."),
    ProfileMetric("oa_third_down_def", "defense", "Third-Down Defense", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted third-down suppression strength."),
    ProfileMetric("oa_finishing_def", "defense", "Finishing Defense", True, "opponent_adjusted_quality", "READY", "Opponent-adjusted scoring-opportunity suppression strength."),
    ProfileMetric("drive_suppression_def", "defense", "Drive Suppression", True, "opponent_adjusted_quality", "RESEARCH", "Opponent-adjusted points prevented per drive from the dedicated PPD model."),
    ProfileMetric("havoc_def", "defense", "Havoc", True, "quality", "PARTIAL", "Production havoc exists, but profile opponent adjustment is not wired into discovery yet."),
    ProfileMetric("turnover_creation", "defense", "Turnover Creation", True, "quality", "DEFERRED", "No profile rate until a takeaway opportunity denominator is independently validated."),

    ProfileMetric("rush_rate", "style", "Run Tendency", True, "behavior", "READY", "How run-heavy the offense is; descriptive rather than opponent-adjusted because it measures choice/style."),
    ProfileMetric("plays_per_possession", "style", "Drive Length", True, "behavior", "READY", "How many plays the offense sustains per possession."),
    ProfileMetric("identity_predictability", "scheme", "Predictability", False, "behavior", "RESEARCH", "How extreme the offense's run/pass tendency is relative to peers."),
    ProfileMetric("identity_one_dimensionality", "scheme", "One-Dimensionality", False, "behavior", "RESEARCH", "Absolute gap between rushing-attack and passing-attack composite quality."),
    ProfileMetric("identity_playcalling_fit", "scheme", "Playcalling Fit", True, "behavior", "RESEARCH", "Whether run/pass usage leans toward the attack mode the offense is actually better at."),
    ProfileMetric("identity_scheme_constraint", "scheme", "Scheme Constraint", False, "behavior", "RESEARCH", "Combination of extreme tendency and weakness in the complementary attack mode."),
    ProfileMetric("tempo", "style", "Tempo", True, "behavior", "PARTIAL", "Game-clock tempo remains incomplete across the full historical corpus."),
    ProfileMetric("aggressiveness", "style", "Aggressiveness", True, "behavior", "PLANNED", "Fourth-down and situational willingness to attack."),
    ProfileMetric("drive_consistency", "form", "Drive Consistency", True, "behavior", "PLANNED", "How stable drive-to-drive offensive output is."),
    ProfileMetric("drive_volatility", "form", "Drive Volatility", True, "behavior", "PLANNED", "How variable drive-to-drive output is."),
)

PROFILE_KEYS = tuple(metric.key for metric in PROFILE_METRICS)
PROFILE_BY_KEY = {metric.key: metric for metric in PROFILE_METRICS}
