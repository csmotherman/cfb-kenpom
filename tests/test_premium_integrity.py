from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from premium_integrity import is_versioned_hash, payload_hash


class PremiumIntegrityTests(unittest.TestCase):
    def test_jsonb_equivalent_number_spellings_hash_identically(self):
        before = {
            "zero": -0.0,
            "one": 1.0,
            "nested": [{"value": 2.0}, 1.25],
        }
        after_jsonb_round_trip = {
            "zero": 0,
            "one": 1,
            "nested": [{"value": 2}, 1.25],
        }
        self.assertEqual(payload_hash(before), payload_hash(after_jsonb_round_trip))

    def test_object_key_order_does_not_change_hash(self):
        self.assertEqual(
            payload_hash({"b": 2, "a": {"y": 1, "x": 0}}),
            payload_hash({"a": {"x": 0.0, "y": 1.0}, "b": 2.0}),
        )

    def test_semantic_change_changes_hash(self):
        self.assertNotEqual(payload_hash({"x": 1}), payload_hash({"x": 2}))

    def test_hash_is_explicitly_versioned(self):
        value = payload_hash({"x": 1})
        self.assertTrue(is_versioned_hash(value))
        self.assertTrue(value.startswith("v2:"))
        self.assertEqual(len(value), 67)

    def test_non_finite_number_is_rejected(self):
        with self.assertRaises(ValueError):
            payload_hash({"x": float("nan")})


if __name__ == "__main__":
    unittest.main()
