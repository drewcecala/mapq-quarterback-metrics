from __future__ import annotations

import unittest

from mapq.official import OfficialSource, _candidate_urls, parse_roster_html


class OfficialRosterTests(unittest.TestCase):
    def test_parses_only_quarterbacks_from_current_roster_table(self) -> None:
        html = """
        <html><head><title>2026 Football Roster</title></head><body>
        <table>
          <tr><th>No.</th><th>Full Name</th><th>Pos.</th><th>Hometown / High School</th></tr>
          <tr><td>4</td><td>Alex Example</td><td>QB</td><td>Los Angeles, Calif. / Central</td></tr>
          <tr><td>8</td><td>Pat Receiver</td><td>WR</td><td>Austin, Texas / West</td></tr>
        </table></body></html>
        """
        source = OfficialSource("Example State", "https://example.edu/sports/football/roster", 2026)
        rows = parse_roster_html(html, source, source.roster_url + "?view=table")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alex Example")
        self.assertEqual(rows[0]["homeCity"], "Los Angeles")
        self.assertEqual(rows[0]["homeState"], "CA")
        self.assertEqual(rows[0]["homeCountry"], "United States")

    def test_full_position_label_and_canadian_hometown_parse(self) -> None:
        html = """
        <h1>2026 Football Roster</h1>
        <table><tr><th>Name</th><th>Position</th><th>Hometown</th></tr>
        <tr><td>Chris North</td><td>Quarterback</td><td>Toronto, Canada</td></tr></table>
        """
        source = OfficialSource("Example", "https://example.edu/sports/football/roster", 2026)
        rows = parse_roster_html(html, source, source.roster_url)
        self.assertEqual(rows[0]["homeCity"], "Toronto")
        self.assertEqual(rows[0]["homeCountry"], "Canada")

    def test_split_first_and_last_name_columns_parse(self) -> None:
        html = """
        <h1>2026 Football Roster</h1><table>
        <tr><th>First Name</th><th>Last Name</th><th>Position</th><th>Hometown</th></tr>
        <tr><td>Alex</td><td>Example</td><td>Quarterback</td><td>Denver, Colo.</td></tr>
        </table>
        """
        source = OfficialSource("Example", "https://example.edu/sports/football/roster", 2026)
        rows = parse_roster_html(html, source, source.roster_url)
        self.assertEqual(rows[0]["name"], "Alex Example")
        self.assertEqual(rows[0]["homeState"], "CO")

    def test_last_comma_first_name_is_canonicalized(self) -> None:
        html = """
        <h1>2026 Football Roster</h1><table>
        <tr><th>Name</th><th>Position</th><th>Hometown</th></tr>
        <tr><td>Example Jr., Alex</td><td>QB</td><td>Dallas, Tex.</td></tr>
        </table>
        """
        source = OfficialSource("Example", "https://example.edu/sports/football/roster", 2026)
        rows = parse_roster_html(html, source, source.roster_url)
        self.assertEqual(rows[0]["name"], "Alex Example Jr.")
        self.assertEqual(rows[0]["homeState"], "TX")

    def test_embedded_sidearm_player_json_is_a_fallback(self) -> None:
        html = """<h1>2026 Football Roster</h1><script>
        window.players=[{"rp_id":12,"first_name":"Alex","last_name":"Example",
        "hometown":"Laramie, Wyo.","position_short":"QB","jersey_number":"7",
        "image":{"title":"nested"},"socials":{}}];</script>"""
        source = OfficialSource("Example", "https://example.edu/sports/football/roster", 2026)
        rows = parse_roster_html(html, source, source.roster_url)
        self.assertEqual(rows[0]["name"], "Alex Example")
        self.assertEqual(rows[0]["homeState"], "WY")

    def test_sidearm_list_card_supplies_hometown_when_table_omits_it(self) -> None:
        html = """
        <h1>2026 Football Roster</h1>
        <table><tr><th>Name</th><th>Position</th><th>Hometown</th></tr>
        <tr><td>Alex Example</td><td>QB</td><td></td></tr></table>
        <div data-test-id="s-person-card-list__root">
          <a aria-label="Alex Example jersey number 7 full bio"></a>
          <span data-test-id="s-person-details__bio-stats-person-position-short"><span>Position</span> QB </span>
          <span data-test-id="s-person-card-list__content-location-person-hometown"><span>Hometown</span> Reno, Nev.</span>
        </div>
        """
        source = OfficialSource("Example", "https://example.edu/sports/football/roster", 2026)
        rows = parse_roster_html(html, source, source.roster_url)
        self.assertEqual(rows[0]["homeCity"], "Reno")
        self.assertEqual(rows[0]["homeState"], "NV")

    def test_table_view_is_requested_without_dropping_existing_query(self) -> None:
        urls = _candidate_urls("https://example.edu/sports/football/roster?path=football")
        self.assertIn("path=football", urls[0])
        self.assertIn("view=table", urls[0])

    def test_old_roster_page_is_rejected(self) -> None:
        source = OfficialSource("Example", "https://example.edu/sports/football/roster", 2026)
        with self.assertRaisesRegex(ValueError, "2026"):
            parse_roster_html("<h1>2025 Football Roster</h1>", source, source.roster_url)


if __name__ == "__main__":
    unittest.main()
