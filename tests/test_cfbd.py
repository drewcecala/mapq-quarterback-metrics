from __future__ import annotations

import unittest

from mapq.cfbd import (
    aggregate_play_stats,
    build_normalized_dataset,
    validate_cohort,
    validate_play_stat_types,
)


class FakeClient:
    network_calls = 0

    def get(self, path: str, **params):
        if path == "/plays/stats/types":
            return [
                {"name": name}
                for name in (
                    "Completion",
                    "Incompletion",
                    "Interception Thrown",
                    "Rush",
                    "Sack Taken",
                    "Touchdown",
                )
            ]
        if path == "/teams/fbs":
            return [
                {"id": 1, "school": "North Valley", "conference": "Test"},
                {"id": 2, "school": "Coastal Tech", "conference": "Test"},
            ]
        if path == "/roster":
            return [
                {"id": "101", "firstName": "River", "lastName": "Hart", "team": "North Valley", "position": "QB"},
                {"id": "102", "firstName": "Cal", "lastName": "Mercer", "team": "Coastal Tech", "position": "QB"},
                {"id": "999", "firstName": "Wide", "lastName": "Receiver", "team": "North Valley", "position": "WR"},
            ]
        if path == "/stats/player/season":
            if params["year"] != 2025:
                return []
            if params["category"] == "passing":
                return [
                    {"season": 2025, "playerId": "101", "player": "River Hart", "position": "QB", "team": "North Valley", "conference": "Test", "category": "passing", "statType": "ATT", "stat": "140"},
                    {"season": 2025, "playerId": "101", "player": "River Hart", "position": "QB", "team": "North Valley", "conference": "Test", "category": "passing", "statType": "COMPLETIONS", "stat": "90"},
                    {"season": 2025, "playerId": "101", "player": "River Hart", "position": "QB", "team": "North Valley", "conference": "Test", "category": "passing", "statType": "YDS", "stat": "1200"},
                    {"season": 2025, "playerId": "101", "player": "River Hart", "position": "QB", "team": "North Valley", "conference": "Test", "category": "passing", "statType": "INT", "stat": "4"},
                ]
            return [
                {"season": 2025, "playerId": "101", "player": "River Hart", "position": "QB", "team": "North Valley", "conference": "Test", "category": "rushing", "statType": "CAR", "stat": "30"},
                {"season": 2025, "playerId": "101", "player": "River Hart", "position": "QB", "team": "North Valley", "conference": "Test", "category": "rushing", "statType": "YDS", "stat": "210"},
            ]
        if path == "/plays/stats":
            return sample_play_rows()
        raise AssertionError((path, params))


def sample_play_rows():
    common = {"gameId": 1, "season": 2025, "week": 1, "team": "North Valley", "conference": "Test"}
    return [
        {**common, "playId": "p1", "down": 3, "distance": 5, "athleteId": "101", "athleteName": "River Hart", "statType": "Completion", "stat": 7},
        {**common, "playId": "p1", "down": 3, "distance": 5, "athleteId": "999", "athleteName": "Wide Receiver", "statType": "Touchdown", "stat": 1},
        {**common, "playId": "p2", "down": 2, "distance": 8, "athleteId": "101", "athleteName": "River Hart", "statType": "Rush", "stat": 16},
        {**common, "playId": "p2", "down": 2, "distance": 8, "athleteId": "101", "athleteName": "River Hart", "statType": "Touchdown", "stat": 1},
        {**common, "playId": "p3", "down": 3, "distance": 10, "athleteId": "101", "athleteName": "River Hart", "statType": "Sack Taken", "stat": -8},
        {**common, "playId": "p4", "down": 3, "distance": 6, "athleteId": "101", "athleteName": "River Hart", "statType": "Incompletion", "stat": 0},
    ]


class CFBDPipelineTests(unittest.TestCase):
    def test_required_play_stat_types_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "sack_taken"):
            validate_play_stat_types([{"name": "Completion"}])

    def test_duplicate_quarterback_ids_fail_closed(self) -> None:
        teams = [{"school": "North Valley"}]
        quarterbacks = [
            {"id": "101", "firstName": "River", "lastName": "Hart", "team": "North Valley"},
            {"id": "101", "firstName": "River", "lastName": "Hart", "team": "North Valley"},
        ]
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            validate_cohort(teams, quarterbacks, minimum_teams=1, minimum_qbs=1)

    def test_play_aggregation(self) -> None:
        row = aggregate_play_stats(sample_play_rows(), {"101"})["101"]
        self.assertEqual(row["pbp_pass_attempts"], 2)
        self.assertEqual(row["pbp_qb_rushes"], 1)
        self.assertEqual(row["pbp_sacks"], 1)
        self.assertEqual(row["pbp_explosive_plays"], 1)
        self.assertEqual(row["pbp_third_down_qb_plays"], 3)
        self.assertEqual(row["pbp_third_down_dropbacks"], 3)
        self.assertEqual(row["pbp_third_down_conversions"], 1)
        self.assertEqual(row["pbp_third_down_tds"], 1)
        self.assertEqual(row["pbp_third_down_sacks"], 1)
        self.assertEqual(row["pbp_escape_opportunities"], 2)
        self.assertEqual(row["pbp_escape_explosives"], 1)

    def test_normalized_dataset_filters_qbs_and_selects_season(self) -> None:
        payload = build_normalized_dataset(
            FakeClient(), minimum_teams=1, minimum_qbs=1, minimum_team_coverage=0.5
        )
        self.assertEqual(len(payload["records"]), 2)
        river = next(row for row in payload["records"] if row["player_id"] == "101")
        self.assertEqual(river["stats_season"], 2025)
        self.assertEqual(river["pass_attempts"], 140)
        self.assertEqual(river["rush_attempts"], 30)
        self.assertEqual(river["sacks"], 1)
        self.assertEqual(river["long_pass"], 7)
        self.assertEqual(river["long_rush"], 16)
        cal = next(row for row in payload["records"] if row["player_id"] == "102")
        self.assertIsNone(cal["stats_season"])


if __name__ == "__main__":
    unittest.main()
