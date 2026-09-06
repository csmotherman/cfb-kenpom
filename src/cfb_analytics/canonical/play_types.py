"""Canonical play-type taxonomy for CFBD source records.

Every observed source play type must be explicitly classified before it can
participate in processed analytics. Raw source fields are always preserved.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PlayTypeRule:
    category: str
    subtype: str
    is_scrimmage: bool = False
    is_offensive_play: bool = False
    is_administrative: bool = False
    is_special_teams: bool = False
    is_penalty: bool = False
    is_turnover: bool = False
    force_analytics_yards_zero: bool = False

RULES: dict[str, PlayTypeRule] = {
    "Rush": PlayTypeRule("SCRIMMAGE", "RUSH", True, True),
    "Rushing Touchdown": PlayTypeRule("SCRIMMAGE", "RUSH_TD", True, True),
    "Pass Reception": PlayTypeRule("SCRIMMAGE", "PASS_COMPLETION", True, True),
    "Pass Completion": PlayTypeRule("SCRIMMAGE", "PASS_COMPLETION", True, True),
    "Pass Incompletion": PlayTypeRule("SCRIMMAGE", "PASS_INCOMPLETE", True, True),
    "Passing Touchdown": PlayTypeRule("SCRIMMAGE", "PASS_TD", True, True),
    "Pass": PlayTypeRule("SCRIMMAGE", "PASS_UNSPECIFIED", True, True),
    "Sack": PlayTypeRule("SCRIMMAGE", "SACK", True, True),
    "Two Point Pass": PlayTypeRule("CONVERSION", "TWO_POINT_PASS", True, True),
    "Two Point Rush": PlayTypeRule("CONVERSION", "TWO_POINT_RUSH", True, True),
    "Defensive 2pt Conversion": PlayTypeRule("CONVERSION", "DEFENSIVE_TWO_POINT", is_turnover=True),
    "Interception": PlayTypeRule("TURNOVER", "INTERCEPTION", True, True, is_turnover=True),
    "Pass Interception Return": PlayTypeRule("TURNOVER", "INTERCEPTION_RETURN", is_turnover=True),
    "Interception Return Touchdown": PlayTypeRule("TURNOVER", "INTERCEPTION_RETURN_TD", is_turnover=True),
    "Fumble": PlayTypeRule("TURNOVER", "FUMBLE", True, True, is_turnover=True),
    "Fumble Recovery (Own)": PlayTypeRule("TURNOVER", "FUMBLE_RECOVERY_OWN", is_turnover=True),
    "Fumble Recovery (Opponent)": PlayTypeRule("TURNOVER", "FUMBLE_RECOVERY_OPPONENT", is_turnover=True),
    "Fumble Return Touchdown": PlayTypeRule("TURNOVER", "FUMBLE_RETURN_TD", is_turnover=True),
    "Safety": PlayTypeRule("SCORING", "SAFETY"),
    "Penalty": PlayTypeRule("PENALTY", "PENALTY", is_penalty=True),
    "Kickoff": PlayTypeRule("SPECIAL_TEAMS", "KICKOFF", is_special_teams=True),
    "Kickoff Return (Offense)": PlayTypeRule("SPECIAL_TEAMS", "KICKOFF_RETURN", is_special_teams=True),
    "Kickoff Return Touchdown": PlayTypeRule("SPECIAL_TEAMS", "KICKOFF_RETURN_TD", is_special_teams=True),
    "Punt": PlayTypeRule("SPECIAL_TEAMS", "PUNT", is_special_teams=True),
    "Punt Return": PlayTypeRule("SPECIAL_TEAMS", "PUNT_RETURN", is_special_teams=True),
    "Punt Return Touchdown": PlayTypeRule("SPECIAL_TEAMS", "PUNT_RETURN_TD", is_special_teams=True),
    "Blocked Punt": PlayTypeRule("SPECIAL_TEAMS", "BLOCKED_PUNT", is_special_teams=True),
    "Blocked Punt Touchdown": PlayTypeRule("SPECIAL_TEAMS", "BLOCKED_PUNT_TD", is_special_teams=True),
    "Field Goal Good": PlayTypeRule("SPECIAL_TEAMS", "FIELD_GOAL_GOOD", is_special_teams=True),
    "Field Goal Missed": PlayTypeRule("SPECIAL_TEAMS", "FIELD_GOAL_MISSED", is_special_teams=True),
    "Blocked Field Goal": PlayTypeRule("SPECIAL_TEAMS", "BLOCKED_FIELD_GOAL", is_special_teams=True),
    "Blocked Field Goal Touchdown": PlayTypeRule("SPECIAL_TEAMS", "BLOCKED_FIELD_GOAL_TD", is_special_teams=True),
    "Missed Field Goal Return": PlayTypeRule("SPECIAL_TEAMS", "MISSED_FIELD_GOAL_RETURN", is_special_teams=True),
    "Missed Field Goal Return Touchdown": PlayTypeRule("SPECIAL_TEAMS", "MISSED_FIELD_GOAL_RETURN_TD", is_special_teams=True),
    "Timeout": PlayTypeRule("ADMINISTRATIVE", "TIMEOUT", is_administrative=True, force_analytics_yards_zero=True),
    "End Period": PlayTypeRule("ADMINISTRATIVE", "END_PERIOD", is_administrative=True, force_analytics_yards_zero=True),
    "End of Half": PlayTypeRule("ADMINISTRATIVE", "END_HALF", is_administrative=True, force_analytics_yards_zero=True),
    "End of Game": PlayTypeRule("ADMINISTRATIVE", "END_GAME", is_administrative=True, force_analytics_yards_zero=True),
    "End of Regulation": PlayTypeRule("ADMINISTRATIVE", "END_REGULATION", is_administrative=True, force_analytics_yards_zero=True),
    "Uncategorized": PlayTypeRule("OTHER", "UNCATEGORIZED"),
    "placeholder": PlayTypeRule("OTHER", "PLACEHOLDER", is_administrative=True, force_analytics_yards_zero=True),
}

def classify_play_type(play_type: str | None) -> PlayTypeRule:
    if play_type not in RULES:
        raise KeyError(f"Unclassified CFBD playType: {play_type!r}")
    return RULES[play_type]
