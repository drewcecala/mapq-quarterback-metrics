from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mapq.release import PUBLIC_FIELDS, _write, public_records
from tools.validate_release_data import validate


class ReleaseTests(unittest.TestCase):
    def test_private_source_fields_are_removed(self) -> None:
        source = [{
            "player_name": "River Hart",
            "team": "North Valley",
            "conference": "Test",
            "stats_season": 2025,
            "mapq": 72.5,
            "mapq_rank": 1,
            "pass_attempts": 300,
            "pass_yards": 3000,
            "player_id": "private-id",
            "stats_teams": ["North Valley"],
        }]
        released = public_records(source)
        self.assertEqual(set(released[0]), set(PUBLIC_FIELDS))
        for private_field in ("pass_attempts", "pass_yards", "player_id", "stats_teams"):
            self.assertNotIn(private_field, released[0])

    def test_unscored_roster_rows_are_not_released(self) -> None:
        source = [
            {"player_name": "Scored", "mapq": 55.0, "mapq_rank": 1},
            {"player_name": "Unscored", "mapq": None, "mapq_rank": None},
        ]
        self.assertEqual([row["player_name"] for row in public_records(source)], ["Scored"])

    def test_public_metadata_is_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            _write(
                path,
                [],
                {
                    "retrieved_at": "2026-08-24T00:00:00+00:00",
                    "roster_year": 2026,
                    "quality_checks": {"quarterback_count": 700},
                    "publication_status": "private normalized input - do not publish",
                    "network_calls": 50,
                },
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["source_metadata"]["roster_year"], 2026)
        self.assertNotIn("publication_status", payload["source_metadata"])
        self.assertNotIn("network_calls", payload["source_metadata"])
        self.assertIn("defense_stress_index", payload["metric_definitions"])

    def test_weekly_json_and_csv_pair_passes_quality_gates(self) -> None:
        record = {field: None for field in PUBLIC_FIELDS}
        record.update(
            {
                "mapq_rank": 1,
                "player_name": "River Hart",
                "team": "North Valley",
                "conference": "Test",
                "stats_season": 2026,
                "mapq": 70.0,
                "tier": "Impact",
                "data_status": "Qualified",
                "accuracy_score": 70.0,
                "arm_proxy_score": 70.0,
                "mobility_score": 70.0,
                "escape_score": 70.0,
                "passing_capability": 70.0,
                "movement_capability": 70.0,
                "reliability": 1.0,
                "advanced_data_status": "PBP coverage/sample gap",
            }
        )
        metadata = {
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "roster_year": 2026,
            "production_seasons": [2026, 2025, 2024, 2023],
            "quality_checks": {
                "fbs_team_count": 138,
                "quarterback_count": 700,
                "quarterback_team_coverage": 1.0,
                "unique_quarterback_ids": True,
                "required_play_stat_types_present": True,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "release.json"
            csv_path = Path(directory) / "release.csv"
            _write(json_path, [record], metadata)
            _write(csv_path, [record], metadata)
            errors = validate(
                json_path,
                csv_path,
                minimum_records=1,
                roster_year=2026,
                current_season=2026,
            )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
