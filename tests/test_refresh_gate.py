import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_new_games import completed_source_games, known_game_ids, partition_key, schedule_metadata_changed
from cfb_analytics.pipelines.ingest import parse_partition
from cfb_analytics.sources.cfbd.client import CfbdResponse


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, path, params):
        self.calls.append((path, params))
        return CfbdResponse("https://example.test", 200, self.payload, b"[]", {})


class RefreshGateTests(unittest.TestCase):
    def test_known_game_ids_accepts_canonical_game_id_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team_games.json"
            path.write_text(json.dumps([
                {"game_id": "101", "team": "A"},
                {"game_id": "101", "team": "B"},
                {"gameId": "202", "team": "C"},
            ]))
            self.assertEqual(known_game_ids(path), {"101", "202"})

    def test_detection_uses_only_completed_games_with_an_fbs_participant(self):
        client = FakeClient([
            {"id": 1, "completed": True, "homeClassification": "fbs", "awayClassification": "fbs"},
            {"id": 2, "completed": False, "homeClassification": "fbs", "awayClassification": "fbs"},
            {"id": 3, "completed": True, "homeClassification": "fcs", "awayClassification": "fcs"},
            {"id": 4, "completed": True, "homeClassification": "fbs", "awayClassification": "fcs"},
        ])
        games = completed_source_games(client, 2026)
        self.assertEqual([game["id"] for game in games], [1, 4])
        self.assertEqual(client.calls, [("/games", {"year": 2026, "classification": "fbs"})])

    def test_partition_key_and_ingest_parser_agree(self):
        game = {"id": 1, "seasonType": "REGULAR", "week": 3}
        self.assertEqual(partition_key(game), "regular:3")
        self.assertEqual(parse_partition("regular:3"), ("regular", 3))

    def test_newly_known_schedule_fields_trigger_refresh(self):
        local = {
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "venue": None,
            "homeTeamId": None,
            "awayTeamId": None,
            "completed": False,
        }
        remote = {
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "venue": {"name": "Michigan Stadium"},
            "homeId": 130,
            "awayId": 2638,
            "completed": False,
        }
        self.assertTrue(schedule_metadata_changed(remote, local))

    def test_unchanged_schedule_metadata_does_not_trigger_refresh(self):
        local = {
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "venue": "Michigan Stadium",
            "homeTeamId": 130,
            "awayTeamId": 2638,
            "completed": False,
        }
        remote = {
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "venue": {"name": "Michigan Stadium"},
            "homeId": 130,
            "awayId": 2638,
            "completed": False,
        }
        self.assertFalse(schedule_metadata_changed(remote, local))

    def test_transient_remote_null_does_not_erase_known_schedule_fields(self):
        local = {
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "venue": "Michigan Stadium",
            "homeTeamId": 130,
            "awayTeamId": 2638,
            "completed": False,
        }
        remote = {
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "venue": None,
            "homeId": None,
            "awayId": None,
            "completed": False,
        }
        self.assertFalse(schedule_metadata_changed(remote, local))


if __name__ == "__main__":
    unittest.main()
