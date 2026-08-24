"""Private, field-level verification of a quarterback roster.

Provider responses and row-level audit files are source data. They belong only in
ignored private storage. Public releases should contain derived outputs and an
aggregate verification summary, not this audit table.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .cfbd import API_BASE, CFBDClient, TERMS_URL

SOURCE_NAME = "CollegeFootballData.com"
TERMS_REVIEW_DATE = "2026-08-24"
VERIFIED_STATUSES = frozenset({"verified_cfbd", "verified_official"})
SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})

STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
STATE_CODES.update({code.casefold(): code for code in tuple(STATE_CODES.values())})
STATE_CODES.update({
    "ala": "AL", "ariz": "AZ", "ark": "AR", "calif": "CA", "colo": "CO",
    "conn": "CT", "del": "DE", "fla": "FL", "ga": "GA", "ill": "IL",
    "ind": "IN", "kan": "KS", "ky": "KY", "la": "LA", "md": "MD",
    "mass": "MA", "mich": "MI", "minn": "MN", "miss": "MS", "mo": "MO",
    "mont": "MT", "neb": "NE", "nev": "NV", "nh": "NH", "nj": "NJ",
    "nm": "NM", "ny": "NY", "nc": "NC", "nd": "ND", "okla": "OK",
    "ore": "OR", "pa": "PA", "ri": "RI", "sc": "SC", "sd": "SD",
    "tenn": "TN", "vt": "VT", "va": "VA", "wash": "WA", "wva": "WV",
    "wis": "WI", "wyo": "WY",
})

TEAM_ALIASES = {
    "appstate": "Appalachian State",
    "appalachianstate": "Appalachian State",
    "cal": "California",
    "uconn": "Connecticut",
    "umass": "Massachusetts",
    "miamifl": "Miami",
    "miamiflorida": "Miami",
    "miamioh": "Miami (OH)",
    "miamiohio": "Miami (OH)",
    "olemiss": "Ole Miss",
    "ncstate": "NC State",
    "northcarolinastate": "NC State",
    "usf": "South Florida",
    "southerncalifornia": "USC",
    "utahstate": "Utah State",
    "utsa": "UTSA",
    "utep": "UTEP",
    "niu": "Northern Illinois",
    "fiu": "Florida International",
    "fau": "Florida Atlantic",
    "louisianalafayette": "Louisiana",
    "ulmonroe": "Louisiana Monroe",
    "louisianamonroe": "Louisiana Monroe",
    "hawaii": "Hawai'i",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode()
    text = text.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", text)


def _name_tokens(value: Any) -> list[str]:
    text = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    return [token for token in tokens if token not in SUFFIXES]


def strict_name_key(value: Any) -> str:
    return "".join(_name_tokens(value))


def edge_name_key(value: Any) -> str:
    tokens = _name_tokens(value)
    if not tokens:
        return ""
    return tokens[0] + (tokens[-1] if len(tokens) > 1 else "")


def normalize_city(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode()
    text = re.sub(r"\bsaint\b", "st", text, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def normalize_state(value: Any) -> str:
    text = _text(value).casefold().replace(".", "")
    return STATE_CODES.get(text, _text(value).upper())


def normalize_country(value: Any) -> str:
    key = normalize_text(value)
    if key in {"us", "usa", "unitedstates", "unitedstatesofamerica"}:
        return "United States"
    if key in {"ca", "can", "canada"}:
        return "Canada"
    return _text(value)


def parse_hometown(value: Any) -> tuple[str, str, str]:
    raw = _text(value)
    if not raw:
        return "", "", ""
    if "," not in raw:
        return raw, "", ""
    city, region = (part.strip() for part in raw.rsplit(",", 1))
    if normalize_text(region) in {"canada", "can"}:
        return city, "", "Canada"
    return city, normalize_state(region), "United States"


def player_name(row: Mapping[str, Any]) -> str:
    direct = _text(row.get("player") or row.get("player_name") or row.get("name"))
    if direct:
        return direct
    return " ".join(
        part for part in (_text(row.get("firstName")), _text(row.get("lastName"))) if part
    )


def player_team(row: Mapping[str, Any]) -> str:
    return _text(row.get("currentTeam") or row.get("team"))


def player_hometown(row: Mapping[str, Any]) -> str:
    return _text(row.get("hometown"))


def build_team_aliases(teams: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for team in teams:
        school = _text(team.get("school"))
        if not school:
            continue
        values = [school, team.get("abbreviation"), *(team.get("alternateNames") or [])]
        for value in values:
            if _text(value):
                aliases[normalize_text(value)] = school
    for alias, school in TEAM_ALIASES.items():
        aliases.setdefault(normalize_text(alias), school)
    return aliases


def canonical_team(value: Any, aliases: Mapping[str, str]) -> str:
    raw = _text(value)
    return aliases.get(normalize_text(raw), TEAM_ALIASES.get(normalize_text(raw), raw))


def validate_provider_roster(roster: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    quarterbacks = [
        dict(row) for row in roster if _text(row.get("position")).upper() == "QB"
    ]
    ids = [_text(row.get("id")) for row in quarterbacks]
    if any(not player_id for player_id in ids):
        raise RuntimeError("provider roster contains a quarterback without a player ID")
    duplicates = [player_id for player_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise RuntimeError(f"provider roster contains {len(duplicates)} duplicate quarterback IDs")
    if any(not player_name(row) or not player_team(row) for row in quarterbacks):
        raise RuntimeError("provider roster contains a quarterback with incomplete identity fields")
    return quarterbacks


def _provider_indexes(
    quarterbacks: Iterable[Mapping[str, Any]], aliases: Mapping[str, str]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in quarterbacks:
        row = dict(item)
        row["_canonical_team"] = canonical_team(player_team(row), aliases)
        row["_strict_name"] = strict_name_key(player_name(row))
        row["_edge_name"] = edge_name_key(player_name(row))
        by_team[normalize_text(row["_canonical_team"])].append(row)
        by_name[row["_strict_name"]].append(row)
    return by_team, by_name


def _unique(candidates: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    rows = list(candidates)
    return rows[0] if len(rows) == 1 else None


def _match_player(
    record: Mapping[str, Any],
    aliases: Mapping[str, str],
    by_team: Mapping[str, list[dict[str, Any]]],
    by_name: Mapping[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str, float, str]:
    input_name = player_name(record)
    input_team = canonical_team(player_team(record), aliases)
    team_candidates = list(by_team.get(normalize_text(input_team), []))
    strict = strict_name_key(input_name)
    edge = edge_name_key(input_name)

    exact = _unique(row for row in team_candidates if row["_strict_name"] == strict)
    if exact:
        return exact, "exact_name_team", 1.0, ""

    edge_match = _unique(row for row in team_candidates if row["_edge_name"] == edge)
    if edge_match:
        return edge_match, "first_last_team", 0.98, ""

    scored = sorted(
        [
            (SequenceMatcher(None, strict, row["_strict_name"]).ratio(), row)
            for row in team_candidates
            if strict and row["_strict_name"]
        ],
        key=lambda item: item[0],
    )
    if scored:
        best_score, best = scored[-1]
        runner_up = scored[-2][0] if len(scored) > 1 else 0.0
        if best_score >= 0.93 and best_score - runner_up >= 0.04:
            return best, "fuzzy_name_team", round(best_score, 4), "manual name confirmation required"

    global_exact = _unique(by_name.get(strict, []))
    if global_exact:
        return global_exact, "exact_name_other_team", 1.0, "provider team differs from input team"

    if len([row for row in team_candidates if row["_edge_name"] == edge]) > 1:
        return None, "ambiguous", 0.0, "multiple same-team candidates share first and last name"
    return None, "unmatched", 0.0, "no unique provider roster match"


def _field_statuses(record: Mapping[str, Any], provider: Mapping[str, Any]) -> dict[str, str]:
    input_city, input_region, input_country = parse_hometown(player_hometown(record))
    provider_city = _text(provider.get("homeCity"))
    provider_region = normalize_state(provider.get("homeState"))
    provider_country = normalize_country(provider.get("homeCountry"))

    if not input_city:
        city_status = "missing_input"
    elif not provider_city:
        city_status = "missing_provider"
    elif normalize_city(input_city) == normalize_city(provider_city):
        city_status = "verified"
    else:
        city_status = "conflict"

    if input_country == "Canada":
        if not provider_country:
            region_status = "missing_provider"
        elif provider_country == "Canada":
            region_status = "verified_country"
        else:
            region_status = "conflict"
    elif not input_region:
        region_status = "missing_input"
    elif not provider_region:
        region_status = "missing_provider"
    elif input_region == provider_region:
        region_status = "verified"
    else:
        region_status = "conflict"

    return {"hometown_city_status": city_status, "hometown_region_status": region_status}


def _overall_status(
    match_method: str,
    team_status: str,
    position_status: str,
    city_status: str,
    region_status: str,
    verified_status: str = "verified_cfbd",
) -> tuple[str, str]:
    if match_method in {"unmatched", "ambiguous"}:
        return match_method, "identity could not be uniquely verified"
    if match_method == "fuzzy_name_team":
        return "needs_review", "name match is fuzzy"
    if team_status == "conflict" or position_status == "conflict":
        return "conflict", "identity fields disagree"
    if city_status == "conflict" or region_status == "conflict":
        return "conflict", "hometown fields disagree"
    if city_status.startswith("missing") or region_status.startswith("missing"):
        return "partial", "provider or input is missing a hometown field"
    return verified_status, ""


def verify_records(
    records: Iterable[Mapping[str, Any]],
    provider_roster: Iterable[Mapping[str, Any]],
    teams: Iterable[Mapping[str, Any]],
    *,
    roster_year: int,
    retrieved_at: str,
    source_name: str = SOURCE_NAME,
    source_endpoint: str | None = None,
    source_terms_url: str = TERMS_URL,
    source_terms_reviewed_at: str = TERMS_REVIEW_DATE,
    verified_status: str = "verified_cfbd",
) -> list[dict[str, Any]]:
    records_list = [dict(row) for row in records]
    aliases = build_team_aliases(teams)
    quarterbacks = validate_provider_roster(provider_roster)
    by_team, by_name = _provider_indexes(quarterbacks, aliases)
    endpoint = source_endpoint or f"{API_BASE}/roster?year={roster_year}&classification=fbs"
    audit: list[dict[str, Any]] = []

    for index, record in enumerate(records_list, start=1):
        provider, method, similarity, reason = _match_player(
            record, aliases, by_team, by_name
        )
        input_team = canonical_team(player_team(record), aliases)
        base = {
            "input_row": index,
            "input_player": player_name(record),
            "input_team": player_team(record),
            "input_hometown": player_hometown(record),
            "provider": source_name,
            "provider_endpoint": endpoint,
            "provider_retrieved_at": retrieved_at,
            "provider_terms_url": source_terms_url,
            "provider_terms_reviewed_at": source_terms_reviewed_at,
            "name_match_method": method,
            "name_similarity": similarity,
        }
        if provider is None:
            audit.append({
                **base,
                "provider_player_id": None,
                "provider_player": None,
                "provider_team": None,
                "provider_position": None,
                "provider_hometown": None,
                "name_status": "unverified",
                "team_status": "unverified",
                "position_status": "unverified",
                "hometown_city_status": "unverified",
                "hometown_region_status": "unverified",
                "overall_status": method,
                "manual_review_required": True,
                "review_reason": reason,
            })
            continue

        provider_team = canonical_team(player_team(provider), aliases)
        team_status = "verified" if normalize_text(input_team) == normalize_text(provider_team) else "conflict"
        position_status = "verified" if _text(provider.get("position")).upper() == "QB" else "conflict"
        fields = _field_statuses(record, provider)
        overall, status_reason = _overall_status(
            method,
            team_status,
            position_status,
            fields["hometown_city_status"],
            fields["hometown_region_status"],
            verified_status,
        )
        provider_hometown = ", ".join(
            part for part in (
                _text(provider.get("homeCity")),
                _text(provider.get("homeState")) or _text(provider.get("homeCountry")),
            ) if part
        )
        audit.append({
            **base,
            "provider_endpoint": _text(provider.get("source_url")) or endpoint,
            "provider_player_id": _text(provider.get("id")),
            "provider_player": player_name(provider),
            "provider_team": player_team(provider),
            "provider_position": _text(provider.get("position")),
            "provider_hometown": provider_hometown or None,
            "name_status": "verified" if method != "fuzzy_name_team" else "needs_review",
            "team_status": team_status,
            "position_status": position_status,
            **fields,
            "overall_status": overall,
            "manual_review_required": overall not in VERIFIED_STATUSES,
            "review_reason": status_reason or reason,
        })
    return audit


def _override_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return strict_name_key(row.get("input_player")), normalize_text(row.get("input_team"))


def apply_manual_overrides(
    audit: Iterable[Mapping[str, Any]], overrides: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    override_map = {_override_key(row): dict(row) for row in overrides}
    output: list[dict[str, Any]] = []
    for item in audit:
        row = dict(item)
        override = override_map.get(_override_key(row))
        if not override:
            output.append(row)
            continue
        decision = _text(override.get("decision")).casefold()
        source_url = _text(override.get("official_source_url"))
        reviewed_at = _text(override.get("reviewed_at"))
        reviewer = _text(override.get("reviewer"))
        if decision not in {"verified", "conflict", "not_found"}:
            raise ValueError(f"invalid manual decision for {row['input_player']}: {decision}")
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc or not reviewed_at or not reviewer:
            raise ValueError(
                f"manual override for {row['input_player']} requires an HTTPS source URL, reviewed_at, and reviewer"
            )
        verified_player = _text(override.get("verified_player"))
        verified_team = _text(override.get("verified_team"))
        verified_position = _text(override.get("verified_position"))
        verified_hometown = _text(override.get("verified_hometown"))
        if decision == "verified" and (
            not verified_player
            or not verified_team
            or verified_position.upper() != "QB"
            or not verified_hometown
        ):
            raise ValueError(
                f"verified manual override for {row['input_player']} requires verified player, team, QB position, and hometown fields"
            )
        row.update({
            "manual_decision": decision,
            "official_source_url": source_url,
            "official_source_retrieved_at": reviewed_at,
            "official_reviewer": reviewer,
            "official_verified_player": verified_player,
            "official_verified_team": verified_team,
            "official_verified_position": verified_position,
            "official_verified_hometown": verified_hometown,
            "manual_notes": _text(override.get("notes")),
            "overall_status": {
                "verified": "verified_official",
                "conflict": "conflict_official",
                "not_found": "not_found_official",
            }[decision],
            "manual_review_required": decision != "verified",
            "review_reason": "" if decision == "verified" else f"official source decision: {decision}",
        })
        output.append(row)
    return output


def verification_summary(audit: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in audit]
    status_counts = Counter(_text(row.get("overall_status")) for row in rows)
    verified = sum(status_counts[status] for status in VERIFIED_STATUSES)
    unique_inputs = len({
        (strict_name_key(row.get("input_player")), normalize_text(row.get("input_team")))
        for row in rows
    })
    provider_ids = [
        _text(row.get("provider_player_id")) for row in rows if _text(row.get("provider_player_id"))
    ]
    providers = sorted({_text(row.get("provider")) for row in rows if _text(row.get("provider"))})
    terms_urls = sorted({
        _text(row.get("provider_terms_url"))
        for row in rows
        if _text(row.get("provider_terms_url"))
    })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": providers[0] if len(providers) == 1 else providers,
        "provider_terms_url": terms_urls[0] if len(terms_urls) == 1 else terms_urls,
        "provider_terms_reviewed_at": TERMS_REVIEW_DATE,
        "input_player_count": len(rows),
        "unique_input_player_team_keys": unique_inputs,
        "verified_player_count": verified,
        "verified_player_rate": round(verified / len(rows), 6) if rows else 0.0,
        "manual_review_count": sum(bool(row.get("manual_review_required")) for row in rows),
        "status_counts": dict(sorted(status_counts.items())),
        "field_counts": {
            field: dict(sorted(Counter(_text(row.get(field)) for row in rows).items()))
            for field in (
                "name_status",
                "team_status",
                "position_status",
                "hometown_city_status",
                "hometown_region_status",
            )
        },
        "quality_gates": {
            "all_input_rows_accounted_for": len(rows) == unique_inputs,
            "provider_player_ids_unique_among_matches": len(provider_ids) == len(set(provider_ids)),
            "all_players_verified": verified == len(rows),
            "release_ready": verified == len(rows),
        },
        "publication_status": "aggregate summary may be published; row-level audit remains private",
    }


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("rows") or payload.get("records")
    else:
        records = None
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"{path} must contain a rows or records array")
    return records


def _read_tabular(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        return _read_json_records(path)
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    raise ValueError("manual overrides must be JSON or CSV")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Privately verify each QB against the authorized CFBD FBS roster."
    )
    parser.add_argument("input", type=Path, help="Private JSON containing rows or records")
    parser.add_argument("--output-dir", type=Path, default=Path("work/player_verification"))
    parser.add_argument("--roster-year", type=int, default=2026)
    parser.add_argument("--cache-dir", type=Path, default=Path("work/cfbd_cache"))
    parser.add_argument("--provider-roster", type=Path, help="Offline CFBD roster JSON fixture")
    parser.add_argument("--provider-teams", type=Path, help="Offline CFBD team JSON fixture")
    parser.add_argument("--overrides", type=Path, help="Reviewed official-source overrides, JSON or CSV")
    parser.add_argument("--expected-count", type=int, default=721)
    args = parser.parse_args(argv)

    records = _read_json_records(args.input)
    if len(records) != args.expected_count:
        raise RuntimeError(f"input contains {len(records)} players; expected {args.expected_count}")

    if bool(args.provider_roster) != bool(args.provider_teams):
        raise ValueError("--provider-roster and --provider-teams must be supplied together")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    if args.provider_roster:
        roster = _read_json_records(args.provider_roster)
        teams = _read_json_records(args.provider_teams)
    else:
        client = CFBDClient(cache_dir=args.cache_dir, call_budget=4)
        teams = client.get("/teams/fbs", year=args.roster_year)
        roster = client.get("/roster", year=args.roster_year, classification="fbs")

    audit = verify_records(
        records,
        roster,
        teams,
        roster_year=args.roster_year,
        retrieved_at=retrieved_at,
    )
    if args.overrides:
        audit = apply_manual_overrides(audit, _read_tabular(args.overrides))
    summary = verification_summary(audit)
    manual_queue = [row for row in audit if row["manual_review_required"]]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "player_verification_private.csv", audit)
    _write_csv(args.output_dir / "manual_review_private.csv", manual_queue)
    (args.output_dir / "verification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Verified {summary['verified_player_count']}/{summary['input_player_count']} players; "
        f"manual review required for {summary['manual_review_count']}"
    )
    return 0 if summary["quality_gates"]["release_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
