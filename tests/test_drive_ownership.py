"""Canonical drive-ownership correction: a turnover play whose native driveId
points at CFBD's separate non-possession "return drive" should be reattached
to the offensive possession drive it actually ended."""
from cfb_analytics.canonical.drive_grouping import derive_partition_drives
from cfb_analytics.canonical.drive_ownership import (
    DRIVE_OWNERSHIP_CORRECTION_VERSION,
    correct_partition_drive_ownership,
)


def offense_play(drive_number, play_number, drive_id, offense, defense, **overrides):
    row = {
        "gameId": "g1", "driveId": drive_id, "driveNumber": drive_number, "playNumber": play_number,
        "id": f"{drive_number}{play_number:03d}",
        "isOffensivePlay": True, "isScrimmagePlay": True, "hasNoPlayContext": False,
        "offense": offense, "defense": defense,
        "eventCategory": "SCRIMMAGE", "eventSubtype": "RUSH",
        "period": 1, "clock": {"minutes": 10, "seconds": 0}, "down": 1, "distance": 10, "yardsToGoal": 50,
        "offenseScore": 0, "defenseScore": 0, "analyticsYardsGained": 4,
    }
    row.update(overrides)
    return row


def return_drive_turnover_play(drive_number, play_number, drive_id, offense, defense, event_subtype, **overrides):
    """A CFBD "return drive" row: no offensive-play evidence, just the
    turnover event itself -- exactly the pattern that gets dropped by every
    drive-anchored propagation module before this fix."""
    row = {
        "gameId": "g1", "driveId": drive_id, "driveNumber": drive_number, "playNumber": play_number,
        "id": f"{drive_number}{play_number:03d}",
        "isOffensivePlay": False, "isScrimmagePlay": False, "hasNoPlayContext": False,
        "offense": offense, "defense": defense,
        "eventCategory": "TURNOVER", "eventSubtype": event_subtype,
        "period": 1, "clock": {"minutes": 5, "seconds": 0}, "down": None, "distance": None, "yardsToGoal": None,
        "offenseScore": 0, "defenseScore": 0, "analyticsYardsGained": None,
    }
    row.update(overrides)
    return row


def test_interception_return_play_reattached_to_preceding_offensive_drive():
    rows = [
        offense_play(1, 1, "d1", "Alpha", "Beta"),
        offense_play(1, 2, "d1", "Alpha", "Beta"),
        return_drive_turnover_play(2, 1, "d2", "Beta", "Alpha", "INTERCEPTION_RETURN"),
        offense_play(3, 1, "d3", "Beta", "Alpha"),
    ]
    corrected, count = correct_partition_drive_ownership(rows, 2025, "regular", 1)
    assert count == 1

    turnover = next(r for r in corrected if r["eventCategory"] == "TURNOVER")
    assert turnover["driveId"] == "d1"
    assert turnover["sourceDriveId"] == "d2"
    assert turnover["driveIdWasCorrected"] is True
    assert turnover["driveIdCorrectionVersion"] == DRIVE_OWNERSHIP_CORRECTION_VERSION
    # driveNumber must move with driveId, or re-deriving drives from the
    # corrected rows would see one drive spanning two drive numbers.
    assert turnover["driveNumber"] == 1
    assert turnover["sourceDriveNumber"] == 2


def test_untouched_plays_keep_their_own_drive_id_and_are_marked_uncorrected():
    rows = [
        offense_play(1, 1, "d1", "Alpha", "Beta"),
        return_drive_turnover_play(2, 1, "d2", "Beta", "Alpha", "FUMBLE_RECOVERY_OPPONENT"),
        offense_play(3, 1, "d3", "Beta", "Alpha"),
    ]
    corrected, _ = correct_partition_drive_ownership(rows, 2025, "regular", 1)

    offensive_rows = [r for r in corrected if r["eventCategory"] != "TURNOVER"]
    for r in offensive_rows:
        assert r["driveIdWasCorrected"] is False
        assert r["sourceDriveId"] == r["driveId"]
        assert r["driveIdCorrectionReason"] is None


def test_no_preceding_possession_drive_leaves_turnover_play_unchanged():
    # A turnover-return group with nothing before it in the game (shouldn't
    # happen in real data -- a turnover requires a prior possession -- but
    # the correction must degrade safely rather than crash or guess).
    rows = [
        return_drive_turnover_play(1, 1, "d1", "Beta", "Alpha", "INTERCEPTION_RETURN"),
        offense_play(2, 1, "d2", "Beta", "Alpha"),
    ]
    corrected, count = correct_partition_drive_ownership(rows, 2025, "regular", 1)
    assert count == 0
    turnover = next(r for r in corrected if r["eventCategory"] == "TURNOVER")
    assert turnover["driveId"] == "d1"
    assert turnover["driveIdWasCorrected"] is False


def test_self_recovered_fumble_on_a_real_offensive_play_is_never_touched():
    # A self-recovered fumble sits on a play that itself carries real
    # offensive-play evidence (a rush/pass attempt), so its drive is never
    # classified as a non-possession return group in the first place -- this
    # fix must not touch it.
    rows = [
        offense_play(1, 1, "d1", "Alpha", "Beta"),
        offense_play(
            1, 2, "d1", "Alpha", "Beta",
            eventCategory="TURNOVER", eventSubtype="FUMBLE_RECOVERY_OWN",
        ),
        offense_play(1, 3, "d1", "Alpha", "Beta"),
    ]
    corrected, count = correct_partition_drive_ownership(rows, 2025, "regular", 1)
    assert count == 0
    fumble = next(r for r in corrected if r["eventSubtype"] == "FUMBLE_RECOVERY_OWN")
    assert fumble["driveIdWasCorrected"] is False
    assert fumble["driveId"] == "d1"


def test_two_separate_turnovers_each_attach_to_their_own_preceding_drive():
    rows = [
        offense_play(1, 1, "d1", "Alpha", "Beta"),
        return_drive_turnover_play(2, 1, "ret1", "Beta", "Alpha", "INTERCEPTION_RETURN"),
        offense_play(3, 1, "d3", "Beta", "Alpha"),
        return_drive_turnover_play(4, 1, "ret2", "Alpha", "Beta", "FUMBLE_RECOVERY_OPPONENT"),
        offense_play(5, 1, "d5", "Alpha", "Beta"),
    ]
    corrected, count = correct_partition_drive_ownership(rows, 2025, "regular", 1)
    assert count == 2

    first_turnover = next(r for r in corrected if r["driveId"] == "d1" and r["eventCategory"] == "TURNOVER")
    assert first_turnover["sourceDriveId"] == "ret1"
    second_turnover = next(r for r in corrected if r["driveId"] == "d3" and r["eventCategory"] == "TURNOVER")
    assert second_turnover["sourceDriveId"] == "ret2"


def test_redriving_drives_from_corrected_rows_never_reintroduces_multiple_drive_numbers():
    # Regression guard for a real bug found against 2025 production data:
    # correcting driveId without also correcting driveNumber made every
    # merged drive look like it spanned two drive numbers once drives were
    # re-derived from the corrected canonical rows.
    rows = [
        offense_play(1, 1, "d1", "Alpha", "Beta"),
        offense_play(1, 2, "d1", "Alpha", "Beta"),
        return_drive_turnover_play(2, 1, "d2", "Beta", "Alpha", "INTERCEPTION_RETURN"),
        offense_play(3, 1, "d3", "Beta", "Alpha"),
    ]
    corrected, _ = correct_partition_drive_ownership(rows, 2025, "regular", 1)
    redrived, _ = derive_partition_drives(corrected, 2025, "regular", 1)

    d1 = next(d for d in redrived if d["driveId"] == "d1")
    assert d1["isPossessionDrive"] is True
    assert d1["driveValidationStatus"] == "PASS"
    assert "MULTIPLE_DRIVE_NUMBERS" not in d1["driveValidationIssues"]
    assert d1["playCount"] == 3  # both offensive plays plus the reattached turnover
