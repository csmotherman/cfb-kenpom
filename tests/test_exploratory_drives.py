"""Deterministic tests for Clean Drive Rate / Drive Killer Rate.

Covers the exact example sequences from the Exploratory Wave 2 spec. See
src/cfb_analytics/analytics/exploratory/drives.py for the methodology.
"""
import unittest

from cfb_analytics.analytics.exploratory.drives import build_drive_record, team_drive_counts, finish_drive_rates

DRIVE = {"gameId": "g1", "driveId": "d1", "offense": "Home", "defense": "Away",
         "isPossessionDrive": True, "driveValidationStatus": "PASS"}


def snap(down, distance, yards, offense="Home", defense="Away", text="run",
         source_type="Rush", event_category="SCRIMMAGE", event_subtype="RUSH",
         is_scrimmage=True, is_offensive=True, is_penalty=False, has_no_play=False,
         yards_to_goal=50, extra=None):
    row = {
        "gameId": "g1", "driveId": "d1", "down": down, "distance": distance,
        "analyticsYardsGained": yards, "yardsToGoal": yards_to_goal,
        "isScrimmagePlay": is_scrimmage, "isOffensivePlay": is_offensive,
        "hasNoPlayContext": has_no_play, "hasStateTransitionModifier": False,
        "offense": offense, "defense": defense, "playText": text,
        "sourcePlayType": source_type, "eventCategory": event_category,
        "eventSubtype": event_subtype, "isPenalty": is_penalty, "isTurnover": False,
        "period": 1,
    }
    if extra:
        row.update(extra)
    return row


def numbered(plays):
    out = []
    for i, p in enumerate(plays, start=1):
        p = dict(p)
        p["playNumber"] = i
        p["id"] = str(2000 + i)
        out.append(p)
    return out


class CleanDriveTests(unittest.TestCase):
    def test_td_drive_no_mistakes_is_clean(self):
        plays = numbered([snap(1, 5, 5, source_type="Rushing Touchdown", text="run for a TOUCHDOWN")])
        record = build_drive_record(DRIVE, plays, set())
        self.assertTrue(record["clean"])

    def test_sack_then_td_is_not_clean(self):
        plays = numbered([
            snap(1, 10, -7, event_subtype="SACK"),
            snap(2, 17, 20, source_type="Rushing Touchdown", text="run for a TOUCHDOWN"),
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertFalse(record["clean"])
        self.assertEqual(record["driveSacks"], 1)

    def test_defensive_penalty_only_is_clean(self):
        # DPI-style penalty that HELPS the offense (state improves): distance
        # and yardsToGoal both decrease on the next same-drive snap.
        plays = numbered([
            snap(1, 10, 0, is_penalty=True, source_type="Penalty", event_category="PENALTY",
                 event_subtype="PENALTY", yards_to_goal=65, extra={"distance": 10}),
            snap(1, 5, 8, yards_to_goal=50),
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertTrue(record["clean"])
        self.assertEqual(record["driveOffensivePenalties"], 0)

    def test_declined_offensive_penalty_is_clean(self):
        plays = numbered([
            snap(1, 10, 0, is_penalty=True, source_type="Penalty", event_category="PENALTY",
                 event_subtype="PENALTY", yards_to_goal=65,
                 extra={"textPenaltyStatus": "DECLINED"}),
            snap(1, 10, 6, yards_to_goal=59),
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertTrue(record["clean"])

    def test_accepted_holding_is_not_clean(self):
        plays = numbered([
            snap(1, 10, 0, is_penalty=True, source_type="Penalty", event_category="PENALTY",
                 event_subtype="PENALTY", yards_to_goal=65),
            snap(1, 20, 4, yards_to_goal=75),
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertFalse(record["clean"])
        self.assertEqual(record["driveOffensivePenalties"], 1)

    def test_self_recovered_fumble_still_clean_in_v1(self):
        plays = numbered([
            snap(1, 10, 5, event_category="TURNOVER", event_subtype="FUMBLE_RECOVERY_OWN",
                 is_scrimmage=False, is_offensive=False, text="fumbled, recovered by Home"),
            snap(1, 10, 12, source_type="Rushing Touchdown", text="run for a TOUCHDOWN"),
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertTrue(record["clean"])
        self.assertEqual(record["driveSelfRecoveredFumbles"], 1)


class DriveKillerTests(unittest.TestCase):
    def test_sack_then_later_first_down_not_killed(self):
        plays = numbered([
            snap(1, 10, -7, event_subtype="SACK"),
            snap(2, 17, 20),  # 20 >= 17 -> converts
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertEqual(record["killerCandidateCount"], 1)
        self.assertFalse(record["killed"])

    def test_sack_then_punt_no_recovery_is_killed(self):
        plays = numbered([snap(1, 10, -7, event_subtype="SACK")])
        record = build_drive_record(DRIVE, plays, set())
        self.assertEqual(record["killerCandidateCount"], 1)
        self.assertTrue(record["killed"])

    def test_tfl_then_later_td_not_killed(self):
        plays = numbered([
            snap(1, 10, -3),  # TFL: negative yards, clean rush
            snap(2, 13, 13, source_type="Rushing Touchdown", text="run for a TOUCHDOWN"),
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertEqual(record["driveTFLs"], 1)
        self.assertFalse(record["killed"])

    def test_interception_is_killed(self):
        plays = numbered([
            snap(1, 10, 5, event_category="TURNOVER", event_subtype="INTERCEPTION",
                 is_scrimmage=False, is_offensive=False, text="pass intercepted"),
        ])
        record = build_drive_record(DRIVE, plays, set())
        self.assertEqual(record["driveInterceptions"], 1)
        self.assertTrue(record["killed"])

    def test_failed_fourth_down_is_killed(self):
        plays = numbered([snap(4, 3, 1)])  # 1 < 3, no conversion
        record = build_drive_record(DRIVE, plays, set())
        self.assertEqual(record["driveFailedFourthDowns"], 1)
        self.assertTrue(record["killed"])


class ExclusionTests(unittest.TestCase):
    def test_kneel_only_drive_excluded(self):
        plays = numbered([snap(1, 10, -1, text="QB kneels to end the game")])
        record = build_drive_record(DRIVE, plays, set())
        self.assertEqual(record["excludedReason"], "kneel_out")

    def test_no_clean_snaps_excluded(self):
        plays = numbered([snap(1, 10, 0, is_scrimmage=False, is_offensive=False,
                                event_category="ADMINISTRATIVE", event_subtype="TIMEOUT",
                                text="Timeout Home")])
        record = build_drive_record(DRIVE, plays, set())
        self.assertEqual(record["excludedReason"], "no_clean_snaps")


class AggregationTests(unittest.TestCase):
    def test_team_drive_counts_offense_and_defense(self):
        clean = build_drive_record(DRIVE, numbered([
            snap(1, 5, 5, source_type="Rushing Touchdown", text="run for a TOUCHDOWN"),
        ]), set())
        killed = build_drive_record(DRIVE, numbered([snap(1, 10, -7, event_subtype="SACK")]), set())
        counts = team_drive_counts([clean, killed])
        home = finish_drive_rates(counts[("g1", "Home")])
        away = finish_drive_rates(counts[("g1", "Away")])
        self.assertEqual(home["eligibleDrives"], 2)
        self.assertEqual(home["cleanDrives"], 1)
        self.assertEqual(home["cleanDriveRate"], 0.5)
        self.assertEqual(home["drivesWithKillerEvent"], 1)
        self.assertEqual(home["drivesKilled"], 1)
        self.assertEqual(home["driveKillerRate"], 1.0)
        self.assertEqual(away["eligibleDrivesFaced"], 2)
        self.assertEqual(away["cleanDrivesAllowed"], 1)
        self.assertEqual(away["cleanDriveRateAllowed"], 0.5)


if __name__ == "__main__":
    unittest.main()
