from __future__ import annotations

import unittest

from mapq.verify import apply_manual_overrides, parse_hometown, verification_summary, verify_records


TEAMS = [
    {
        "school": "Appalachian State",
        "abbreviation": "APP",
        "alternateNames": ["App State"],
    },
    {
        "school": "Miami",
        "abbreviation": "MIA",
        "alternateNames": ["Miami (FL)"],
    },
]

ROSTER = [
    {
        "id": "101",
        "firstName": "A.J.",
        "lastName": "Rivera Jr.",
        "team": "Appalachian State",
        "position": "QB",
        "homeCity": "St. Louis",
        "homeState": "Missouri",
        "homeCountry": "USA",
    },
    {
        "id": "102",
        "firstName": "Cal",
        "lastName": "Mercer",
        "team": "Miami",
        "position": "QB",
        "homeCity": "Tampa",
        "homeState": "FL",
        "homeCountry": "United States",
    },
    {
        "id": "103",
        "firstName": "Noah",
        "lastName": "North",
        "team": "Miami",
        "position": "QB",
        "homeCity": None,
        "homeState": None,
        "homeCountry": None,
    },
]


class VerificationTests(unittest.TestCase):
    def test_california_abbreviation_is_not_treated_as_canada(self) -> None:
        self.assertEqual(parse_hometown("Tampa, CA"), ("Tampa", "CA", "United States"))

    def test_exact_identity_and_hometown_aliases_verify(self) -> None:
        rows = [{"player": "AJ Rivera", "currentTeam": "App State", "hometown": "Saint Louis, MO"}]
        audit = verify_records(rows, ROSTER, TEAMS, roster_year=2026, retrieved_at="2026-08-24T00:00:00Z")
        self.assertEqual(audit[0]["overall_status"], "verified_cfbd")
        self.assertEqual(audit[0]["provider_player_id"], "101")
        self.assertEqual(audit[0]["team_status"], "verified")
        self.assertEqual(audit[0]["hometown_city_status"], "verified")

    def test_hometown_conflict_is_not_verified(self) -> None:
        rows = [{"player": "Cal Mercer", "currentTeam": "Miami (FL)", "hometown": "Orlando, FL"}]
        audit = verify_records(rows, ROSTER, TEAMS, roster_year=2026, retrieved_at="2026-08-24T00:00:00Z")
        self.assertEqual(audit[0]["overall_status"], "conflict")
        self.assertEqual(audit[0]["hometown_city_status"], "conflict")
        self.assertTrue(audit[0]["manual_review_required"])

    def test_missing_provider_hometown_is_partial(self) -> None:
        rows = [{"player": "Noah North", "currentTeam": "Miami", "hometown": "Austin, TX"}]
        audit = verify_records(rows, ROSTER, TEAMS, roster_year=2026, retrieved_at="2026-08-24T00:00:00Z")
        self.assertEqual(audit[0]["overall_status"], "partial")
        self.assertEqual(audit[0]["hometown_city_status"], "missing_provider")

    def test_unique_name_on_other_team_surfaces_team_conflict(self) -> None:
        rows = [{"player": "Cal Mercer", "currentTeam": "App State", "hometown": "Tampa, FL"}]
        audit = verify_records(rows, ROSTER, TEAMS, roster_year=2026, retrieved_at="2026-08-24T00:00:00Z")
        self.assertEqual(audit[0]["name_match_method"], "exact_name_other_team")
        self.assertEqual(audit[0]["team_status"], "conflict")
        self.assertEqual(audit[0]["overall_status"], "conflict")

    def test_official_override_can_close_a_manual_review(self) -> None:
        rows = [{"player": "Unknown QB", "currentTeam": "Miami", "hometown": "Miami, FL"}]
        audit = verify_records(rows, ROSTER, TEAMS, roster_year=2026, retrieved_at="2026-08-24T00:00:00Z")
        overridden = apply_manual_overrides(audit, [{
            "input_player": "Unknown QB",
            "input_team": "Miami",
            "decision": "verified",
            "official_source_url": "https://miamihurricanes.com/sports/football/roster/unknown-qb/1",
            "reviewed_at": "2026-08-24",
            "reviewer": "Drew Cecala",
            "verified_player": "Unknown QB",
            "verified_team": "Miami",
            "verified_position": "QB",
            "verified_hometown": "Miami, FL",
        }])
        self.assertEqual(overridden[0]["overall_status"], "verified_official")
        self.assertFalse(overridden[0]["manual_review_required"])
        summary = verification_summary(overridden)
        self.assertTrue(summary["quality_gates"]["release_ready"])


if __name__ == "__main__":
    unittest.main()
