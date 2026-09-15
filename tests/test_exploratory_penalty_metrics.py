from cfb_analytics.analytics.exploratory.penalty_metrics import (
    build_drive_penalty_record,
    classify_penalty_direction,
    finish_penalty_counts,
    team_penalty_counts,
)


def snap(offense, defense="B", drive_id="d1", is_penalty=False, text_penalty_status=None,
         down=1, distance=10, yards_to_goal=70, analytics_yards=0, period=1, minutes=10, seconds=0, play_number=1):
    return {
        "offense": offense, "defense": defense, "driveId": drive_id,
        "isPenalty": is_penalty, "textPenaltyStatus": text_penalty_status,
        "down": down, "distance": distance, "yardsToGoal": yards_to_goal,
        "analyticsYardsGained": analytics_yards,
        "period": period, "clock": {"minutes": minutes, "seconds": seconds}, "playNumber": play_number,
    }


def drive(game_id, offense, defense, drive_id="d1", valid=True, possession=True):
    return {"gameId": game_id, "driveId": drive_id, "offense": offense, "defense": defense,
            "isPossessionDrive": possession, "driveValidationStatus": "PASS" if valid else "FAIL"}


def test_offensive_penalty_worsens_state_is_against_offense():
    p = snap("A", "B", is_penalty=True, distance=5, yards_to_goal=60, analytics_yards=10)
    nxt = snap("A", "B", distance=15, yards_to_goal=70, play_number=2)  # worse: further to go
    assert classify_penalty_direction(p, nxt) == "against_offense"


def test_defensive_penalty_improves_state_is_against_defense():
    p = snap("A", "B", is_penalty=True, down=4, distance=10, yards_to_goal=70, analytics_yards=5)
    nxt = snap("A", "B", down=1, distance=10, yards_to_goal=65, play_number=2)  # better: closer to goal
    assert classify_penalty_direction(p, nxt) == "against_defense"


def test_declined_penalty_is_excluded():
    p = snap("A", "B", is_penalty=True, text_penalty_status="DECLINED", distance=5, yards_to_goal=60)
    nxt = snap("A", "B", distance=15, yards_to_goal=70, play_number=2)
    assert classify_penalty_direction(p, nxt) is None


def test_offsetting_penalty_is_excluded():
    p = snap("A", "B", is_penalty=True, text_penalty_status="OFFSETTING", distance=5, yards_to_goal=60)
    nxt = snap("A", "B", distance=15, yards_to_goal=70, play_number=2)
    assert classify_penalty_direction(p, nxt) is None


def test_unchanged_state_is_none():
    p = snap("A", "B", is_penalty=True, distance=10, yards_to_goal=70)
    nxt = snap("A", "B", distance=10, yards_to_goal=70, play_number=2)
    assert classify_penalty_direction(p, nxt) is None


def test_no_next_play_is_none():
    p = snap("A", "B", is_penalty=True, distance=5, yards_to_goal=60)
    assert classify_penalty_direction(p, None) is None


def test_offensive_penalty_mirrors_to_defense_penalties_forced():
    d = drive("g1", "A", "B")
    plays = [
        snap("A", "B", is_penalty=True, distance=5, yards_to_goal=60, analytics_yards=10, play_number=1),
        snap("A", "B", distance=15, yards_to_goal=70, play_number=2),
    ]
    record = build_drive_penalty_record(d, plays)
    assert len(record["events"]) == 1
    assert record["events"][0]["faultTeam"] == "A"
    assert record["events"][0]["benefitTeam"] == "B"
    assert record["events"][0]["yards"] == 10

    counts = team_penalty_counts([record])
    off_row = finish_penalty_counts(counts[("g1", "A")])
    def_row = finish_penalty_counts(counts[("g1", "B")])
    assert off_row["offensivePenalties"] == 1
    assert off_row["offensivePenaltyYards"] == 10
    assert def_row["penaltiesForced"] == 1
    assert def_row["penaltyYardsForced"] == 10
    # Direct mirror, same shape as turnovers==takeaways.
    assert off_row["offensivePenalties"] == def_row["penaltiesForced"]


def test_defensive_penalty_mirrors_to_offense_penalties_drawn():
    d = drive("g1", "A", "B")
    plays = [
        snap("A", "B", is_penalty=True, down=4, distance=10, yards_to_goal=70, analytics_yards=15, play_number=1),
        snap("A", "B", down=1, distance=10, yards_to_goal=55, play_number=2),
    ]
    record = build_drive_penalty_record(d, plays)
    assert record["events"][0]["faultTeam"] == "B"
    assert record["events"][0]["benefitTeam"] == "A"

    counts = team_penalty_counts([record])
    off_row = finish_penalty_counts(counts[("g1", "A")])
    def_row = finish_penalty_counts(counts[("g1", "B")])
    assert off_row["penaltiesDrawn"] == 1
    assert off_row["penaltyYardsDrawn"] == 15
    assert def_row["defensivePenalties"] == 1
    assert def_row["defensivePenaltyYards"] == 15
    assert off_row["penaltiesDrawn"] == def_row["defensivePenalties"]


def test_offensive_and_defensive_penalty_pools_are_kept_separate():
    # Same team fouls once on offense, once (in a different drive/role) on
    # defense -- offensivePenalties and defensivePenalties must not conflate.
    d1 = drive("g1", "A", "B", drive_id="d1")
    plays1 = [
        snap("A", "B", drive_id="d1", is_penalty=True, distance=5, yards_to_goal=60, analytics_yards=10, play_number=1),
        snap("A", "B", drive_id="d1", distance=15, yards_to_goal=70, play_number=2),
    ]
    d2 = drive("g1", "B", "A", drive_id="d2")
    plays2 = [
        snap("B", "A", drive_id="d2", is_penalty=True, down=4, distance=10, yards_to_goal=70, analytics_yards=5, play_number=1),
        snap("B", "A", drive_id="d2", down=1, distance=10, yards_to_goal=60, play_number=2),
    ]
    records = [build_drive_penalty_record(d1, plays1), build_drive_penalty_record(d2, plays2)]
    counts = team_penalty_counts(records)
    a_row = finish_penalty_counts(counts[("g1", "A")])
    assert a_row["offensivePenalties"] == 1  # A fouled while on offense in d1
    assert a_row["defensivePenalties"] == 1  # A fouled while on defense in d2 (foul against A's D)
    assert a_row["offensiveDrives"] == 1
    assert a_row["opponentDrives"] == 1


def test_games_field_is_one_per_team_game_row():
    d = drive("g1", "A", "B")
    record = build_drive_penalty_record(d, [snap("A", "B")])
    counts = team_penalty_counts([record])
    off_row = finish_penalty_counts(counts[("g1", "A")])
    assert off_row["games"] == 1


def test_fbs_filter_excludes_drives_with_a_non_fbs_side():
    d = drive("g1", "A", "B")
    plays = [
        snap("A", "B", is_penalty=True, distance=5, yards_to_goal=60, analytics_yards=10, play_number=1),
        snap("A", "B", distance=15, yards_to_goal=70, play_number=2),
    ]
    record = build_drive_penalty_record(d, plays)
    counts = team_penalty_counts([record], fbs_teams={"A"})
    assert ("g1", "A") not in counts
    counts_included = team_penalty_counts([record], fbs_teams={"A", "B"})
    assert ("g1", "A") in counts_included


def test_invalid_drive_returns_none():
    d = drive("g1", "A", "B", valid=False)
    assert build_drive_penalty_record(d, []) is None
