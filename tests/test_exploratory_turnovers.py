from cfb_analytics.analytics.exploratory.turnovers import (
    build_drive_turnover_record,
    classify_turnover_play,
    finish_turnover_counts,
    team_turnover_counts,
)


def snap(offense, event_category=None, event_subtype=None, is_scrimmage=True, is_offensive=True,
         no_play=False, down=1, distance=10, analytics_yards=5, ppa=None, play_id=1):
    return {
        "offense": offense, "eventCategory": event_category, "eventSubtype": event_subtype,
        "isScrimmagePlay": is_scrimmage, "isOffensivePlay": is_offensive,
        "hasNoPlayContext": no_play, "down": down, "distance": distance,
        "analyticsYardsGained": analytics_yards, "ppa": ppa, "id": play_id,
    }


def drive(game_id, offense, defense, valid=True, possession=True):
    return {"gameId": game_id, "offense": offense, "defense": defense,
            "isPossessionDrive": possession, "driveValidationStatus": "PASS" if valid else "FAIL"}


def test_classify_turnover_play_interception():
    p = snap("A", event_category="TURNOVER", event_subtype="INTERCEPTION_RETURN")
    assert classify_turnover_play(p) == "interception"


def test_classify_turnover_play_lost_fumble():
    p = snap("A", event_category="TURNOVER", event_subtype="FUMBLE_RECOVERY_OPPONENT")
    assert classify_turnover_play(p) == "lost_fumble"


def test_classify_turnover_play_self_recovered_fumble_is_its_own_kind():
    p = snap("A", event_category="TURNOVER", event_subtype="FUMBLE_RECOVERY_OWN")
    assert classify_turnover_play(p) == "self_recovered_fumble"


def test_classify_turnover_play_non_turnover_play_is_none():
    p = snap("A", event_subtype="PASS_COMPLETION")
    assert classify_turnover_play(p) is None


def test_self_recovered_fumble_never_counted_as_turnover():
    d = drive("g1", "A", "B")
    plays = [
        snap("A", event_subtype="PASS_COMPLETION", play_id=1),
        snap("A", event_category="TURNOVER", event_subtype="FUMBLE_RECOVERY_OWN", play_id=2),
        snap("A", event_subtype="RUSH", is_scrimmage=True, play_id=3),
    ]
    record = build_drive_turnover_record(d, plays)
    assert record["lostFumbles"] == 0
    assert record["interceptions"] == 0
    assert record["selfRecoveredFumbles"] == 1
    counts = team_turnover_counts([record])
    row = finish_turnover_counts(counts[("g1", "A")])
    assert row["turnovers"] == 0
    assert row["selfRecoveredFumbles"] == 1


def test_lost_fumble_counts_as_turnover_and_offensive_drive():
    d = drive("g1", "A", "B")
    plays = [snap("A", event_category="TURNOVER", event_subtype="FUMBLE_RECOVERY_OPPONENT", ppa=-3.2, play_id=1)]
    record = build_drive_turnover_record(d, plays)
    assert record["lostFumbles"] == 1
    assert record["turnoverEpaSum"] == -3.2
    counts = team_turnover_counts([record])
    off_row = finish_turnover_counts(counts[("g1", "A")])
    assert off_row["turnovers"] == 1
    assert off_row["lostFumbles"] == 1
    assert off_row["offensiveDrives"] == 1
    assert off_row["turnoverEpaSum"] == -3.2


def test_interception_mirrors_correctly_to_defense_row():
    d = drive("g1", "A", "B")
    plays = [snap("A", event_category="TURNOVER", event_subtype="INTERCEPTION", ppa=-2.5, play_id=1)]
    record = build_drive_turnover_record(d, plays)
    counts = team_turnover_counts([record])
    off_row = finish_turnover_counts(counts[("g1", "A")])
    def_row = finish_turnover_counts(counts[("g1", "B")])
    assert off_row["interceptions"] == 1
    assert off_row["turnovers"] == 1
    assert def_row["interceptionsForced"] == 1
    assert def_row["takeaways"] == 1
    assert def_row["opponentDrives"] == 1
    assert def_row["opponentTurnoverEpaSum"] == -2.5
    # League-wide reconciliation, at the smallest possible scale: offense's
    # turnover exactly equals the defense's takeaway.
    assert off_row["turnovers"] == def_row["takeaways"]
    assert off_row["interceptions"] == def_row["interceptionsForced"]


def test_pass_attempts_include_interceptions_but_not_sacks_or_rushes():
    d = drive("g1", "A", "B")
    plays = [
        snap("A", event_subtype="PASS_COMPLETION", play_id=1),
        snap("A", event_subtype="PASS_INCOMPLETE", play_id=2),
        snap("A", event_subtype="SACK", play_id=3),
        snap("A", event_subtype="RUSH", play_id=4),
        snap("A", event_category="TURNOVER", event_subtype="INTERCEPTION", play_id=5),
    ]
    record = build_drive_turnover_record(d, plays)
    # 2 clean pass plays + 1 interception = 3 pass attempts; sack and rush excluded.
    assert record["passAttempts"] == 3


def test_merged_turnover_row_not_double_counted_in_pass_attempts():
    # A merged interception+return row is isScrimmagePlay=False by
    # construction (see epa.py's docstring) -- confirm it's excluded from
    # the clean-snap pass-family count and only added once via the explicit
    # interception addend.
    d = drive("g1", "A", "B")
    plays = [snap("A", event_category="TURNOVER", event_subtype="INTERCEPTION_RETURN", is_scrimmage=False, play_id=1)]
    record = build_drive_turnover_record(d, plays)
    assert record["passAttempts"] == 1


def test_invalid_drive_returns_none():
    d = drive("g1", "A", "B", valid=False)
    assert build_drive_turnover_record(d, []) is None


def test_non_possession_drive_returns_none():
    d = drive("g1", "A", "B", possession=False)
    assert build_drive_turnover_record(d, []) is None


def test_only_offenses_own_plays_count_toward_its_turnovers():
    # A defensive-side row (e.g. a penalty on the defense) must never be
    # attributed to the offense's turnover count even if malformed data
    # somehow tagged it TURNOVER/INTERCEPTION.
    d = drive("g1", "A", "B")
    plays = [snap("B", event_category="TURNOVER", event_subtype="INTERCEPTION", play_id=1)]
    record = build_drive_turnover_record(d, plays)
    assert record["interceptions"] == 0
    assert record["turnoverEpaSum"] == 0.0


def test_games_field_is_one_per_team_game_row():
    d = drive("g1", "A", "B")
    record = build_drive_turnover_record(d, [snap("A", event_subtype="PASS_COMPLETION", play_id=1)])
    counts = team_turnover_counts([record])
    off_row = finish_turnover_counts(counts[("g1", "A")])
    def_row = finish_turnover_counts(counts[("g1", "B")])
    assert off_row["games"] == 1
    assert def_row["games"] == 1


def test_fbs_filter_excludes_drives_with_a_non_fbs_side():
    d = drive("g1", "A", "B")
    plays = [snap("A", event_category="TURNOVER", event_subtype="INTERCEPTION", play_id=1)]
    record = build_drive_turnover_record(d, plays)
    counts = team_turnover_counts([record], fbs_teams={"A"})
    assert ("g1", "A") not in counts
    assert ("g1", "B") not in counts

    counts_included = team_turnover_counts([record], fbs_teams={"A", "B"})
    assert ("g1", "A") in counts_included
