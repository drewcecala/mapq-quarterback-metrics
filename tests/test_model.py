from __future__ import annotations

import json
import unittest
from pathlib import Path

from mapq.model import _midrank, score_records


ROOT = Path(__file__).resolve().parents[1]


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads((ROOT / "examples" / "sample_input.json").read_text())
        cls.scored = score_records(payload["records"])
        cls.by_id = {row["player_id"]: row for row in cls.scored}

    def test_midrank_handles_ties(self) -> None:
        self.assertEqual(_midrank(2.0, [1.0, 2.0, 2.0, 4.0]), 0.5)

    def test_score_and_metric_ranges(self) -> None:
        for row in self.scored:
            for field in ("mapq", "defense_stress_index", "drive_extension_index"):
                value = row.get(field)
                if value is not None:
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 100.0)
            rate = row.get("escape_to_explosive_rate_proxy")
            if rate is not None:
                self.assertGreaterEqual(rate, 0.0)
                self.assertLessEqual(rate, 1.0)

    def test_small_sample_is_provisional_and_shrunk(self) -> None:
        row = self.by_id["syn-007"]
        self.assertEqual(row["data_status"], "Provisional")
        self.assertLess(abs(row["mapq"] - 50), abs(row["raw_mapq"] - 50))
        self.assertIsNone(row["drive_extension_index"])
        self.assertIsNone(row["escape_to_explosive_rate_proxy"])

    def test_missing_stats_are_unscored(self) -> None:
        row = self.by_id["syn-008"]
        self.assertIsNone(row.get("mapq"))
        self.assertEqual(row["data_status"], "No college stats")
        self.assertEqual(row["advanced_data_status"], "Unscored")

    def test_advanced_metrics_clear_for_qualified_example(self) -> None:
        row = self.by_id["syn-001"]
        self.assertIsNotNone(row["defense_stress_index"])
        self.assertIsNotNone(row["drive_extension_index"])
        self.assertIsNotNone(row["escape_to_explosive_rate_proxy"])
        self.assertEqual(row["advanced_data_status"], "All three metrics")

    def test_versioned_regression_values(self) -> None:
        row = self.by_id["syn-001"]
        self.assertAlmostEqual(row["mapq"], 73.774779280306, places=10)
        self.assertAlmostEqual(row["passing_capability"], 80.0, places=10)
        self.assertAlmostEqual(row["movement_capability"], 65.333333333333, places=10)
        self.assertAlmostEqual(row["defense_stress_index"], 70.0, places=10)
        self.assertAlmostEqual(row["drive_extension_index"], 65.0, places=10)
        self.assertAlmostEqual(
            row["escape_to_explosive_rate_proxy"], 0.454545454545, places=10
        )

    def test_input_order_does_not_change_scores(self) -> None:
        reversed_rows = score_records(reversed([
            {key: value for key, value in row.items() if key in {
                "player_id", "player_name", "team", "stats_season", "pass_attempts",
                "completions", "pass_yards", "interceptions", "long_pass", "sacks",
                "rush_attempts", "rush_yards", "long_rush", "pbp_pass_attempts",
                "pbp_qb_rushes", "pbp_sacks", "pbp_explosive_plays",
                "pbp_third_down_qb_plays", "pbp_third_down_dropbacks",
                "pbp_third_down_conversions", "pbp_third_down_tds",
                "pbp_third_down_sacks", "pbp_escape_opportunities",
                "pbp_escape_explosives"
            }}
            for row in self.scored
        ]))
        reversed_by_id = {row["player_id"]: row for row in reversed_rows}
        for player_id, row in self.by_id.items():
            self.assertAlmostEqual(
                row.get("mapq") or 0.0, reversed_by_id[player_id].get("mapq") or 0.0
            )
            self.assertEqual(row["dsi_rank"], reversed_by_id[player_id]["dsi_rank"])

    def test_invalid_counts_fail_fast(self) -> None:
        bad = {
            "player_id": "bad",
            "player_name": "Bad Record",
            "stats_season": 2025,
            "pass_attempts": 10,
            "completions": 11,
        }
        with self.assertRaisesRegex(ValueError, "completions exceed"):
            score_records([bad])


if __name__ == "__main__":
    unittest.main()
