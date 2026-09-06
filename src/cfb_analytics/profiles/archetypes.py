from __future__ import annotations

ARCHETYPES = (
    ("AIR_IT_OUT", "Air It Out", lambda p: p.get("pass_rate", 0) >= 80 and p.get("explosiveness_off", 0) >= 70 and p.get("turnover_avoidance", 100) <= 45 and p.get("drive_suppression_def", 100) <= 45,
     "Pass-heavy, explosive and willing to live with chaos while the defense struggles to get stops."),
    ("GROUND_AND_POUND", "Ground & Pound", lambda p: p.get("rush_rate", 0) >= 75 and p.get("run_efficiency_off", 0) >= 65 and p.get("tempo", 50) <= 45,
     "Leans on the run game, controls pace and tries to make opponents survive long, physical possessions."),
    ("DEATH_BY_A_THOUSAND_CUTS", "Death by a Thousand Cuts", lambda p: p.get("success_off", 0) >= 80 and p.get("explosiveness_off", 100) <= 60 and p.get("plays_per_possession", 0) >= 70,
     "Wins snap after snap, sustains drives and rarely needs one huge play to move the football."),
    ("TRACK_MEET", "Track Meet", lambda p: p.get("tempo", 0) >= 75 and p.get("explosiveness_off", 0) >= 75 and p.get("drive_suppression_def", 100) <= 40,
     "Creates possessions, creates explosives and often turns Saturdays into a race to the scoreboard."),
    ("ROCK_FIGHT", "Rock Fight", lambda p: p.get("drive_suppression_def", 0) >= 75 and p.get("drive_scoring_off", 100) <= 45 and p.get("tempo", 50) <= 50,
     "Defense-first, low-tempo football where every possession feels expensive."),
    ("BOOM_OR_BUST", "Boom or Bust", lambda p: p.get("explosiveness_off", 0) >= 80 and p.get("success_off", 100) <= 50,
     "The ceiling is huge, but consistent down-to-down offense is not the point."),
    ("BRICK_WALL", "Brick Wall", lambda p: p.get("drive_suppression_def", 0) >= 85 and p.get("run_efficiency_def", 0) >= 70 and p.get("pass_efficiency_def", 0) >= 70,
     "Opponents struggle to move the ball or turn possessions into points."),
    ("CHAOS_MERCHANT", "Chaos Merchant", lambda p: p.get("havoc_def", 0) >= 85 and p.get("turnover_creation", 0) >= 75,
     "Lives on sacks, negative plays and takeaways that knock games off schedule."),
    ("POSSESSION_VAMPIRE", "Possession Vampire", lambda p: p.get("plays_per_possession", 0) >= 85 and p.get("rush_rate", 0) >= 60 and p.get("tempo", 100) <= 40,
     "Drains possessions, owns the ball and makes the opposing offense watch from the sideline."),
    ("RED_ZONE_ASSASSIN", "Red Zone Assassin", lambda p: p.get("finishing_off", 0) >= 90 and p.get("success_off", 50) <= 75,
     "May not dominate every snap, but becomes lethal once scoring opportunities appear."),
    ("BETWEEN_THE_20S", "Between-the-20s Merchant", lambda p: p.get("success_off", 0) >= 70 and p.get("finishing_off", 100) <= 40,
     "Moves the ball better than the scoreboard suggests and too often leaves points unfinished."),
    ("METRONOME", "Metronome", lambda p: p.get("drive_consistency", 0) >= 90 and p.get("success_off", 0) >= 65,
     "Steady, repeatable offense with very little drive-to-drive drama."),
)


def classify_archetypes(percentiles: dict[str, float], *, max_results: int = 2) -> list[dict[str, str]]:
    """Return primary/secondary fan-facing identities from analytical percentiles."""
    matches = []
    for key, name, rule, description in ARCHETYPES:
        if rule(percentiles):
            matches.append({"key": key, "name": name, "description": description})
    if not matches:
        return [{"key": "NO_STRONG_ARCHETYPE", "name": "No Strong Archetype", "description": "Balanced profile without one extreme identity signal yet."}]
    return matches[:max_results]
