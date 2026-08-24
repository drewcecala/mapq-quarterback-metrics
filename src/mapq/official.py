"""No-key verification against current official school football rosters.

Only factual identity fields are retained. Downloaded HTML and row-level audit
files are private build inputs and must stay under ignored ``work/`` storage.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import html as html_lib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping

from .verify import (
    _read_json_records,
    _read_tabular,
    _write_csv,
    apply_manual_overrides,
    normalize_state,
    normalize_text,
    verification_summary,
    verify_records,
)

SOURCE_NAME = "Official school athletics rosters"
SOURCE_REVIEW_DATE = "2026-08-24"
DEFAULT_USER_AGENT = "MAPQ-RosterVerifier/1.0"


@dataclass(frozen=True)
class OfficialSource:
    team: str
    roster_url: str
    roster_year: int


class RosterTableParser(HTMLParser):
    """Collect text cells from HTML tables without third-party dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._table: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "svg"}:
            self._ignored_depth += 1
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif self._cell is not None and tag == "br":
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table_depth == 1:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._table:
                self.tables.append(self._table)
                self._table = []
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._cell is not None and not self._ignored_depth:
            self._cell.append(data)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_roster_name(value: str) -> str:
    name = _clean_text(value)
    if name.count(",") == 1:
        last, first = (_clean_text(part) for part in name.split(",", 1))
        if first and last:
            return f"{first} {last}"
    return name


def _header_key(value: str) -> str:
    return normalize_text(value)


def _column_index(headers: list[str], kind: str) -> int | None:
    keys = [_header_key(value) for value in headers]
    exact = {
        "name": {"name", "fullname", "player", "studentathlete"},
        "first_name": {"firstname", "first"},
        "last_name": {"lastname", "last"},
        "position": {"pos", "position", "playerposition"},
        "hometown": {"hometown", "hometownhighschool", "hometownpreviousschool"},
        "jersey": {"no", "number", "jersey", "jerseynumber"},
    }[kind]
    for index, key in enumerate(keys):
        if key in exact:
            return index
    if kind == "hometown":
        for index, key in enumerate(keys):
            if key.startswith("hometown"):
                return index
    return None


def _is_quarterback(value: str) -> bool:
    key = normalize_text(value)
    return key == "qb" or "quarterback" in key or key.startswith("qb")


def _split_hometown(value: str) -> tuple[str, str, str]:
    raw = _clean_text(value)
    raw = re.split(r"\s*/\s*|\s*\|\s*", raw, maxsplit=1)[0]
    if not raw:
        return "", "", ""
    if "," not in raw:
        return raw, "", ""
    city, region = (_clean_text(part) for part in raw.rsplit(",", 1))
    region_key = normalize_text(region)
    if region_key in {
        "canada", "can", "alberta", "britishcolumbia", "manitoba", "newbrunswick",
        "newfoundlandandlabrador", "novascotia", "ontario", "princeedwardisland",
        "quebec", "saskatchewan",
    }:
        return city, "", "Canada"
    if region_key in {"hawaii", "oahu", "maui", "kauai", "molokai"}:
        return city, "HI", "United States"
    if region_key == "tex":
        return city, "TX", "United States"
    return city, normalize_state(region), "United States"


def _provider_row(
    source: OfficialSource,
    source_url: str,
    name: str,
    hometown: str,
    jersey: str,
    identifier: str,
) -> dict[str, Any]:
    city, state, country = _split_hometown(hometown)
    return {
        "id": "official:" + identifier,
        "name": _clean_text(name),
        "team": source.team,
        "position": "QB",
        "homeCity": city,
        "homeState": state,
        "homeCountry": country,
        "source_url": source.roster_url,
        "fetched_url": source_url,
        "jersey": _clean_text(jersey),
    }


def _parse_embedded_sidearm_players(
    html: str, source: OfficialSource, source_url: str
) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(r'\{"rp_id":', html):
        try:
            item, _ = decoder.raw_decode(html[match.start():])
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict) or not _is_quarterback(_clean_text(item.get("position_short"))):
            continue
        name = _clean_text(f"{item.get('first_name') or ''} {item.get('last_name') or ''}")
        hometown = _clean_text(item.get("hometown"))
        identifier = str(item.get("rp_id") or "")
        if not name or not identifier or identifier in seen:
            continue
        seen.add(identifier)
        output.append(_provider_row(
            source,
            source_url,
            name,
            hometown,
            _clean_text(item.get("jersey_number")),
            f"{normalize_text(source.team)}:{identifier}",
        ))
    return output


def _parse_sidearm_person_cards(
    html: str, source: OfficialSource, source_url: str
) -> list[dict[str, Any]]:
    marker = 'data-test-id="s-person-card-list__root"'
    starts = [match.start() for match in re.finditer(re.escape(marker), html)]
    output: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        block = html[start:starts[index + 1] if index + 1 < len(starts) else start + 30_000]
        identity = re.search(
            r'aria-label="([^"]+?) jersey number ([^"]*?) full bio"',
            block,
            flags=re.IGNORECASE,
        )
        position = re.search(
            r'bio-stats-person-position[^>]*>\s*<span[^>]*>\s*Position\s*</span>\s*([^<]+)',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        hometown = re.search(
            r'content-location-person-hometown[^>]*>.*?<span[^>]*>\s*Hometown\s*</span>\s*([^<]+)</span>',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not identity or not position or not _is_quarterback(html_lib.unescape(position.group(1))):
            continue
        name = _normalize_roster_name(html_lib.unescape(identity.group(1)))
        jersey = _clean_text(html_lib.unescape(identity.group(2)))
        hometown_text = html_lib.unescape(hometown.group(1)) if hometown else ""
        output.append(_provider_row(
            source,
            source_url,
            name,
            hometown_text,
            jersey,
            f"{normalize_text(source.team)}:card:{normalize_text(name)}:{normalize_text(jersey)}",
        ))
    return output


def parse_roster_html(html: str, source: OfficialSource, source_url: str) -> list[dict[str, Any]]:
    page_text = re.sub(r"<[^>]+>", " ", html[:700_000])
    if str(source.roster_year) not in page_text or "roster" not in page_text.casefold():
        raise ValueError(f"page does not identify a {source.roster_year} roster")

    parser = RosterTableParser()
    parser.feed(html)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for table in parser.tables:
        header_at = None
        indexes: dict[str, int | None] = {}
        for row_index, row in enumerate(table[:8]):
            candidate = {
                kind: _column_index(row, kind)
                for kind in ("name", "first_name", "last_name", "position", "hometown", "jersey")
            }
            has_name = candidate["name"] is not None or (
                candidate["first_name"] is not None and candidate["last_name"] is not None
            )
            if has_name and all(candidate[kind] is not None for kind in ("position", "hometown")):
                header_at = row_index
                indexes = candidate
                break
        if header_at is None and len(table) > 1 and len(table[0]) >= 7:
            sample = [row for row in table[1:20] if len(row) == len(table[0])]
            if sample and any(
                len(row) > 6 and normalize_text(row[2]) in {
                    "qb", "wr", "rb", "lb", "db", "dl", "ol", "te", "s", "cb"
                }
                for row in sample
            ):
                header_at = 0
                indexes = {
                    "name": 1, "first_name": None, "last_name": None,
                    "position": 2, "hometown": len(table[0]) - 1, "jersey": 0,
                }
        if header_at is None:
            continue
        for row in table[header_at + 1:]:
            required = [indexes["position"], indexes["hometown"]]
            if any(index is None or index >= len(row) for index in required):
                continue
            if indexes["name"] is not None and indexes["name"] < len(row):
                name = _normalize_roster_name(row[indexes["name"]])
            elif all(indexes[key] is not None and indexes[key] < len(row) for key in ("first_name", "last_name")):
                name = _clean_text(
                    f"{row[indexes['first_name']]} {row[indexes['last_name']]}"  # type: ignore[index]
                )
            else:
                continue
            position = _clean_text(row[indexes["position"]])  # type: ignore[index]
            hometown = _clean_text(row[indexes["hometown"]])  # type: ignore[index]
            if not name or not _is_quarterback(position):
                continue
            jersey_index = indexes["jersey"]
            jersey = _clean_text(row[jersey_index]) if jersey_index is not None and jersey_index < len(row) else ""
            identity = f"{normalize_text(source.team)}:{normalize_text(name)}:{normalize_text(jersey)}"
            if identity in seen:
                continue
            seen.add(identity)
            output.append(_provider_row(source, source_url, name, hometown, jersey, identity))
    supplemental = _parse_sidearm_person_cards(html, source, source_url)
    supplemental.extend(_parse_embedded_sidearm_players(html, source, source_url))
    by_name = {normalize_text(row["name"]): row for row in output}
    for row in supplemental:
        key = normalize_text(row["name"])
        if key in by_name:
            existing = by_name[key]
            if not existing.get("homeCity") and row.get("homeCity"):
                existing.update({
                    "homeCity": row["homeCity"],
                    "homeState": row["homeState"],
                    "homeCountry": row["homeCountry"],
                })
        else:
            output.append(row)
            by_name[key] = row
    if not output:
        raise ValueError("no quarterback rows found in a table with name, position, and hometown")
    return output


def read_source_registry(path: Path) -> list[OfficialSource]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    sources: list[OfficialSource] = []
    for line, row in enumerate(rows, start=2):
        team = _clean_text(row.get("team"))
        url = _clean_text(row.get("roster_url"))
        try:
            year = int(_clean_text(row.get("roster_year")))
        except ValueError as exc:
            raise ValueError(f"{path}:{line}: invalid roster_year") from exc
        parsed = urllib.parse.urlparse(url)
        if not team or parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"{path}:{line}: team and HTTPS roster_url are required")
        sources.append(OfficialSource(team, url, year))
    teams = [normalize_text(source.team) for source in sources]
    if len(teams) != len(set(teams)):
        raise ValueError("official source registry contains duplicate teams")
    return sources


def _fetch_text(url: str, user_agent: str, timeout: int = 35) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(content_type, errors="replace"), response.geturl()


def robots_allows(url: str, user_agent: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    try:
        text, _ = _fetch_text(robots_url, user_agent, timeout=20)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return False, f"robots.txt returned HTTP {exc.code}"
        if exc.code == 404:
            return True, "robots.txt not found"
        return False, f"robots.txt returned HTTP {exc.code}"
    except (OSError, TimeoutError) as exc:
        return False, f"robots.txt could not be checked: {exc}"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(text.splitlines())
    allowed = parser.can_fetch(user_agent, url)
    return allowed, "allowed by robots.txt" if allowed else "disallowed by robots.txt"


def _candidate_urls(url: str) -> list[str]:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not any(key == "view" for key, _ in query):
        query.append(("view", "table"))
    table_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
    candidates = [table_url, url]
    if parsed.path.rstrip("/").endswith("/roster"):
        candidates.append(urllib.parse.urlunparse(parsed._replace(path=parsed.path.rstrip("/") + "/print", query="")))
    return list(dict.fromkeys(candidates))


def _cache_path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    host = re.sub(r"[^a-z0-9.-]+", "_", urllib.parse.urlparse(url).netloc.casefold())
    return cache_dir / f"{host}-{digest}.html"


def fetch_and_parse_source(
    source: OfficialSource,
    cache_dir: Path,
    user_agent: str,
    *,
    offline: bool = False,
    refresh: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    best_partial: tuple[list[dict[str, Any]], dict[str, Any]] | None = None
    for url in _candidate_urls(source.roster_url):
        cache_path = _cache_path(cache_dir, url)
        try:
            if cache_path.exists() and not refresh:
                html = cache_path.read_text(encoding="utf-8")
                final_url = url
                access = "private cache"
            elif offline:
                errors.append(f"{url}: not cached")
                continue
            else:
                allowed, robots_note = robots_allows(url, user_agent)
                if not allowed:
                    errors.append(f"{url}: {robots_note}")
                    continue
                html, final_url = _fetch_text(url, user_agent)
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(html, encoding="utf-8")
                access = robots_note
                time.sleep(0.15)
            players = parse_roster_html(html, source, final_url)
            status_row = {
                "team": source.team,
                "roster_url": source.roster_url,
                "fetched_url": final_url,
                "retrieved_at": started,
                "status": "parsed",
                "qb_count": len(players),
                "access_note": access,
                "error": "",
            }
            missing_hometowns = sum(not player.get("homeCity") for player in players)
            if not missing_hometowns:
                return players, status_row
            status_row["access_note"] = f"{access}; {missing_hometowns} QB hometowns missing"
            status_row["error"] = "roster table omitted one or more QB hometowns"
            if best_partial is None or len(players) > len(best_partial[0]):
                best_partial = players, status_row
            errors.append(f"{url}: {missing_hometowns} QB hometowns missing")
        except (OSError, TimeoutError, ValueError, urllib.error.URLError) as exc:
            errors.append(f"{url}: {exc}")
    if best_partial is not None:
        return best_partial
    return [], {
        "team": source.team,
        "roster_url": source.roster_url,
        "fetched_url": "",
        "retrieved_at": started,
        "status": "manual_review",
        "qb_count": 0,
        "access_note": "",
        "error": " | ".join(errors),
    }


def verify_from_official_sources(
    records: Iterable[Mapping[str, Any]],
    sources: Iterable[OfficialSource],
    *,
    cache_dir: Path,
    user_agent: str = DEFAULT_USER_AGENT,
    offline: bool = False,
    refresh: bool = False,
    workers: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    records_list = [dict(row) for row in records]
    source_list = list(sources)
    input_teams = {normalize_text(row.get("currentTeam") or row.get("team")) for row in records_list}
    registry_teams = {normalize_text(source.team) for source in source_list}
    missing = sorted(input_teams - registry_teams)
    extra = sorted(registry_teams - input_teams)
    if missing or extra:
        raise ValueError(f"source registry team mismatch: missing={missing}, extra={extra}")

    provider_roster: list[dict[str, Any]] = []
    fetch_rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
        futures = {
            executor.submit(
                fetch_and_parse_source,
                source,
                cache_dir,
                user_agent,
                offline=offline,
                refresh=refresh,
            ): source
            for source in source_list
        }
        for future in concurrent.futures.as_completed(futures):
            players, fetch_row = future.result()
            provider_roster.extend(players)
            fetch_rows.append(fetch_row)
    fetch_rows.sort(key=lambda row: row["team"])

    teams = [{"school": source.team, "alternateNames": []} for source in source_list]
    audit = verify_records(
        records_list,
        provider_roster,
        teams,
        roster_year=source_list[0].roster_year if source_list else 0,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        source_name=SOURCE_NAME,
        source_endpoint="official source registry",
        source_terms_url="",
        source_terms_reviewed_at=SOURCE_REVIEW_DATE,
        verified_status="verified_official",
    )
    source_by_team = {normalize_text(source.team): source.roster_url for source in source_list}
    for row in audit:
        if row.get("provider_endpoint") == "official source registry":
            row["provider_endpoint"] = source_by_team.get(normalize_text(row.get("input_team")), "")
    provider_roster.sort(key=lambda row: (row["team"], row["name"]))
    return audit, fetch_rows, provider_roster


def canonical_roster_rows(
    provider_roster: Iterable[Mapping[str, Any]], fetch_rows: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    retrieved_by_team = {row["team"]: row["retrieved_at"] for row in fetch_rows}
    output: list[dict[str, Any]] = []
    for player in provider_roster:
        region = _clean_text(player.get("homeState")) or _clean_text(player.get("homeCountry"))
        hometown = ", ".join(
            part for part in (_clean_text(player.get("homeCity")), region) if part
        )
        output.append({
            "player": _clean_text(player.get("name")),
            "currentTeam": _clean_text(player.get("team")),
            "position": "QB",
            "hometown": hometown,
            "official_source_url": _clean_text(player.get("source_url")),
            "official_source_retrieved_at": retrieved_by_team.get(player.get("team"), ""),
            "official_player_key": _clean_text(player.get("id")),
        })
    return output


def roster_reconciliation_rows(
    audit: Iterable[Mapping[str, Any]], provider_roster: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    audit_rows = [dict(row) for row in audit]
    provider_rows = [dict(row) for row in provider_roster]
    matched_ids = {
        _clean_text(row.get("provider_player_id"))
        for row in audit_rows
        if _clean_text(row.get("provider_player_id"))
    }
    output: list[dict[str, Any]] = []
    for row in audit_rows:
        output.append({
            "change_type": "retained" if row.get("provider_player_id") else "remove_from_current_roster",
            "input_player": row.get("input_player"),
            "input_team": row.get("input_team"),
            "input_hometown": row.get("input_hometown"),
            "official_player": row.get("provider_player"),
            "official_team": row.get("provider_team"),
            "official_hometown": row.get("provider_hometown"),
            "match_status": row.get("overall_status"),
            "official_source_url": row.get("provider_endpoint"),
        })
    for row in provider_rows:
        if _clean_text(row.get("id")) in matched_ids:
            continue
        region = _clean_text(row.get("homeState")) or _clean_text(row.get("homeCountry"))
        output.append({
            "change_type": "add_to_current_roster",
            "input_player": "",
            "input_team": "",
            "input_hometown": "",
            "official_player": row.get("name"),
            "official_team": row.get("team"),
            "official_hometown": ", ".join(
                part for part in (_clean_text(row.get("homeCity")), region) if part
            ),
            "match_status": "official_roster_addition",
            "official_source_url": row.get("source_url"),
        })
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify QBs against official school rosters without an API key.")
    parser.add_argument("input", type=Path, help="Private JSON containing rows or records")
    parser.add_argument("--sources", type=Path, default=Path("sources/official_rosters_2026.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("work/official_verification"))
    parser.add_argument("--cache-dir", type=Path, default=Path("work/official_roster_cache"))
    parser.add_argument("--overrides", type=Path, help="Reviewed official-source overrides, JSON or CSV")
    parser.add_argument("--expected-count", type=int, default=721)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--offline", action="store_true", help="Use private cache only")
    parser.add_argument("--refresh", action="store_true", help="Refetch even when a private cache exists")
    parser.add_argument(
        "--rebuild-current-roster",
        action="store_true",
        help="Succeed when the official canonical roster is complete even if the input roster is stale",
    )
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    args = parser.parse_args(argv)

    records = _read_json_records(args.input)
    if len(records) != args.expected_count:
        raise RuntimeError(f"input contains {len(records)} players; expected {args.expected_count}")
    sources = read_source_registry(args.sources)
    audit, fetch_rows, provider_roster = verify_from_official_sources(
        records,
        sources,
        cache_dir=args.cache_dir,
        user_agent=args.user_agent,
        offline=args.offline,
        refresh=args.refresh,
        workers=args.workers,
    )
    if args.overrides:
        audit = apply_manual_overrides(audit, _read_tabular(args.overrides))
    summary = verification_summary(audit)
    parsed_teams = sum(row["status"] == "parsed" for row in fetch_rows)
    canonical = canonical_roster_rows(provider_roster, fetch_rows)
    reconciliation = roster_reconciliation_rows(audit, provider_roster)
    additions = sum(row["change_type"] == "add_to_current_roster" for row in reconciliation)
    removals = sum(row["change_type"] == "remove_from_current_roster" for row in reconciliation)
    summary["official_source_coverage"] = {
        "registry_team_count": len(sources),
        "parsed_team_count": parsed_teams,
        "manual_source_team_count": len(sources) - parsed_teams,
        "parsed_qb_count": sum(int(row["qb_count"]) for row in fetch_rows),
        "canonical_qb_count": len(canonical),
        "canonical_rows_with_hometown": sum(bool(row["hometown"]) for row in canonical),
        "canonical_roster_complete": (
            parsed_teams == len(sources)
            and len(canonical) == len({row["official_player_key"] for row in canonical})
            and all(row["player"] and row["currentTeam"] and row["hometown"] for row in canonical)
        ),
        "input_rows_retained": len(audit) - removals,
        "input_rows_to_remove": removals,
        "official_rows_to_add": additions,
    }
    manual_queue = [row for row in audit if row["manual_review_required"]]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "player_verification_private.csv", audit)
    _write_csv(args.output_dir / "manual_review_private.csv", manual_queue)
    _write_csv(args.output_dir / "source_fetch_private.csv", fetch_rows)
    _write_csv(args.output_dir / "canonical_official_qb_roster_private.csv", canonical)
    _write_csv(args.output_dir / "roster_reconciliation_private.csv", reconciliation)
    (args.output_dir / "verification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Parsed {parsed_teams}/{len(sources)} official team rosters; "
        f"verified {summary['verified_player_count']}/{summary['input_player_count']} players; "
        f"canonical roster has {len(canonical)} QBs; "
        f"manual review required for {summary['manual_review_count']} input rows"
    )
    accepted = summary["quality_gates"]["release_ready"] or (
        args.rebuild_current_roster
        and summary["official_source_coverage"]["canonical_roster_complete"]
    )
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
