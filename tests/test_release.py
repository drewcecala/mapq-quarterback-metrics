from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mapq.release import PUBLIC_FIELDS, _write, public_records


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


if __name__ == "__main__":
    unittest.main()
