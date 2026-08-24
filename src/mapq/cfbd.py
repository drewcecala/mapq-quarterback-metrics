"""Authorized CollegeFootballData acquisition for private MAP-Q inputs.

The raw and normalized outputs of this module are source data and must remain
private. Use :mod:`mapq.release` to create a derived-only public artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .model import DEFAULT_CONFIG

API_BASE = "https://api.collegefootballdata.com"
TERMS_URL = "https://collegefootballdata.com/terms"
DEFAULT_SEASONS = (2026, 2025, 2024, 2023)
PLAY_STATS_LIMIT = 2_000
REQUIRED_PLAY_STAT_TYPES = frozenset(
    {
        "completion",
        "incompletion",
        "interception_thrown",
        "rush",
        "sack_taken",
        "touchdown",
    }
)


def _whole_number(value: Any) -> int:
    if value in (None, "", "--"):
        return 0
    return int(float(value))


def _normalize_type(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")


def validate_play_stat_types(rows: Iterable[Any]) -> set[str]:
    """Fail if CFBD no longer exposes an event type required by the model."""

    available: set[str] = set()
    for row in rows:
        if isinstance(row, Mapping):
            value = row.get("name") or row.get("statType") or row.get("type")
        else:
            value = row
        normalized = _normalize_type(value)
        if normalized:
            available.add(normalized)
    missing = REQUIRED_PLAY_STAT_TYPES - available
    if missing:
        raise RuntimeError(
            "CFBD play-stat schema is missing required types: "
            + ", ".join(sorted(missing))
        )
    return available


def validate_cohort(
    teams: Iterable[Mapping[str, Any]],
    quarterbacks: Iterable[Mapping[str, Any]],
    *,
    minimum_teams: int = 120,
    minimum_qbs: int = 500,
    minimum_team_coverage: float = 0.90,
) -> dict[str, Any]:
    """Validate identity joins and minimum coverage before source data is scored."""

    team_rows = list(teams)
    qb_rows = list(quarterbacks)
    team_names = {str(row.get("school", "")).strip() for row in team_rows}
    team_names.discard("")
    if len(team_names) < minimum_teams:
        raise RuntimeError(
            f"CFBD returned {len(team_names)} FBS teams; expected at least {minimum_teams}"
        )
    if len(qb_rows) < minimum_qbs:
        raise RuntimeError(
            f"CFBD returned {len(qb_rows)} quarterbacks; expected at least {minimum_qbs}"
        )

    ids = [str(row.get("id", "")).strip() for row in qb_rows]
    if any(not player_id for player_id in ids):
        raise RuntimeError("CFBD roster contains a quarterback without a player ID")
    if len(ids) != len(set(ids)):
        raise RuntimeError("CFBD roster contains duplicate quarterback player IDs")

    incomplete = [
        player_id
        for player_id, row in zip(ids, qb_rows)
        if not str(row.get("team", "")).strip()
        or not " ".join(
            part for part in (row.get("firstName"), row.get("lastName")) if part
        ).strip()
    ]
    if incomplete:
        raise RuntimeError(
            f"CFBD roster contains {len(incomplete)} quarterbacks with incomplete identity fields"
        )

    covered_teams = {
        str(row.get("team", "")).strip()
        for row in qb_rows
        if str(row.get("team", "")).strip() in team_names
    }
    coverage = len(covered_teams) / len(team_names) if team_names else 0.0
    if coverage < minimum_team_coverage:
        raise RuntimeError(
            "CFBD quarterback team coverage is "
            f"{coverage:.1%}; expected at least {minimum_team_coverage:.1%}"
        )
    return {
        "fbs_team_count": len(team_names),
        "quarterback_count": len(qb_rows),
        "teams_with_quarterbacks": len(covered_teams),
        "quarterback_team_coverage": round(coverage, 6),
        "unique_quarterback_ids": True,
    }


class CFBDClient:
    """Small standard-library CFBD client with private caching and a call budget."""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | str = Path("work/cfbd_cache"),
        call_budget: int = 900,
        retries: int = 3,
        refresh_years: Iterable[int] = (),
    ) -> None:
        self.api_key = (api_key or os.environ.get("CFBD_API_KEY", "")).strip()
        if not self.api_key:
            raise RuntimeError(
                "CFBD_API_KEY is missing. Request a key from "
                "https://collegefootballdata.com/key and store it only in the environment."
            )
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.call_budget = call_budget
        self.retries = retries
        self.refresh_years = frozenset(int(year) for year in refresh_years)
        self._refreshed_cache_keys: set[str] = set()
        self.network_calls = 0

    def _refresh_requested(self, params: Mapping[str, Any]) -> bool:
        value = params.get("year")
        if value is None:
            return False
        try:
            return int(value) in self.refresh_years
        except (TypeError, ValueError):
            return False

    def get(self, path: str, **params: Any) -> Any:
        clean_params = {key: value for key, value in params.items() if value is not None}
        query = urllib.parse.urlencode(sorted(clean_params.items()))
        url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        refresh_requested = self._refresh_requested(clean_params)
        if cache_path.exists() and (
            not refresh_requested or cache_key in self._refreshed_cache_keys
        ):
            return json.loads(cache_path.read_text(encoding="utf-8"))

        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.network_calls >= self.call_budget:
                raise RuntimeError(
                    f"CFBD network-call budget of {self.call_budget} would be exceeded"
                )
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "User-Agent": "mapq-quarterback-metrics/1.1",
                },
            )
            try:
                self.network_calls += 1
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                if refresh_requested:
                    self._refreshed_cache_keys.add(cache_key)
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 401:
                    raise RuntimeError("CFBD rejected the API key") from exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    raise RuntimeError(f"CFBD request failed with HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.75 * (attempt + 1)
                time.sleep(min(delay, 10.0))
            except (OSError, ValueError) as exc:
                last_error = exc
                time.sleep(0.75 * (attempt + 1))
        raise RuntimeError(f"CFBD request failed after {self.retries} attempts") from last_error


def _aggregate_season_stats(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for item in rows:
        player_id = str(item.get("playerId", "")).strip()
        if not player_id:
            continue
        season = _whole_number(item.get("season"))
        key = (player_id, season)
        bucket = output.setdefault(
            key,
            {
                "stats_season": season,
                "stats_teams": set(),
                "pass_attempts": 0,
                "completions": 0,
                "pass_yards": 0,
                "interceptions": 0,
                "long_pass": 0,
                "sacks": None,
                "rush_attempts": 0,
                "rush_yards": 0,
                "long_rush": 0,
            },
        )
        if item.get("team"):
            bucket["stats_teams"].add(str(item["team"]))
        category = str(item.get("category", "")).casefold()
        stat_type = str(item.get("statType", "")).upper()
        value = _whole_number(item.get("stat"))
        field: str | None = None
        if category == "passing":
            field = {
                "ATT": "pass_attempts",
                "COMPLETIONS": "completions",
                "YDS": "pass_yards",
                "INT": "interceptions",
                "LONG": "long_pass",
                "SACK": "sacks",
                "SACKS": "sacks",
            }.get(stat_type)
        elif category == "rushing":
            field = {
                "CAR": "rush_attempts",
                "YDS": "rush_yards",
                "LONG": "long_rush",
            }.get(stat_type)
        if field is None:
            continue
        if field in {"long_pass", "long_rush"}:
            bucket[field] = max(bucket[field], value)
        else:
            if bucket[field] is None:
                bucket[field] = 0
            bucket[field] += value
    return output


def _new_pbp_bucket() -> dict[str, int]:
    return {
        "pbp_pass_attempts": 0,
        "pbp_qb_rushes": 0,
        "pbp_sacks": 0,
        "pbp_explosive_plays": 0,
        "pbp_third_down_qb_plays": 0,
        "pbp_third_down_dropbacks": 0,
        "pbp_third_down_conversions": 0,
        "pbp_third_down_tds": 0,
        "pbp_third_down_sacks": 0,
        "pbp_escape_opportunities": 0,
        "pbp_escape_explosives": 0,
        "pbp_long_pass": 0,
        "pbp_long_rush": 0,
    }


def aggregate_play_stats(
    rows: Iterable[Mapping[str, Any]], quarterback_ids: set[str]
) -> dict[str, dict[str, int]]:
    """Aggregate player-linked CFBD play-stat rows for selected quarterbacks."""

    plays: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (str(row.get("gameId", "")), str(row.get("playId", "")))
        plays[key].append(row)

    output: dict[str, dict[str, int]] = defaultdict(_new_pbp_bucket)
    pass_types = ("completion", "incompletion", "interception_thrown")
    for associations in plays.values():
        typed: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in associations:
            typed[_normalize_type(row.get("statType"))].append(row)
        touchdown = bool(typed.get("touchdown"))
        down = _whole_number(associations[0].get("down"))
        distance = _whole_number(associations[0].get("distance"))

        passer_id: str | None = None
        pass_kind: str | None = None
        pass_yards = 0
        for kind in pass_types:
            for row in typed.get(kind, []):
                athlete_id = str(row.get("athleteId", ""))
                if athlete_id in quarterback_ids:
                    passer_id = athlete_id
                    pass_kind = kind
                    pass_yards = _whole_number(row.get("stat")) if kind == "completion" else 0
                    break
            if passer_id:
                break

        sack_id = next(
            (
                str(row.get("athleteId", ""))
                for row in typed.get("sack_taken", [])
                if str(row.get("athleteId", "")) in quarterback_ids
            ),
            None,
        )
        rush_row = next(
            (
                row
                for row in typed.get("rush", [])
                if str(row.get("athleteId", "")) in quarterback_ids
            ),
            None,
        )
        rush_id = str(rush_row.get("athleteId")) if rush_row else None
        rush_yards = _whole_number(rush_row.get("stat")) if rush_row else 0

        if sack_id:
            bucket = output[sack_id]
            bucket["pbp_sacks"] += 1
            if down == 3:
                bucket["pbp_third_down_qb_plays"] += 1
                bucket["pbp_third_down_dropbacks"] += 1
                bucket["pbp_third_down_sacks"] += 1
            if down in {2, 3, 4} and distance >= 5:
                bucket["pbp_escape_opportunities"] += 1
            continue

        if passer_id:
            bucket = output[passer_id]
            bucket["pbp_pass_attempts"] += 1
            if pass_kind == "completion":
                bucket["pbp_long_pass"] = max(bucket["pbp_long_pass"], pass_yards)
                if pass_yards >= 15:
                    bucket["pbp_explosive_plays"] += 1
            if down == 3:
                bucket["pbp_third_down_qb_plays"] += 1
                bucket["pbp_third_down_dropbacks"] += 1
                if pass_kind == "completion" and (pass_yards >= distance or touchdown):
                    bucket["pbp_third_down_conversions"] += 1
                if pass_kind == "completion" and touchdown:
                    bucket["pbp_third_down_tds"] += 1
            continue

        if rush_id:
            bucket = output[rush_id]
            bucket["pbp_qb_rushes"] += 1
            bucket["pbp_long_rush"] = max(bucket["pbp_long_rush"], rush_yards)
            if rush_yards >= 15:
                bucket["pbp_explosive_plays"] += 1
            if down == 3:
                bucket["pbp_third_down_qb_plays"] += 1
                if rush_yards >= distance or touchdown:
                    bucket["pbp_third_down_conversions"] += 1
                if touchdown:
                    bucket["pbp_third_down_tds"] += 1
            if down in {2, 3, 4} and distance >= 5:
                bucket["pbp_escape_opportunities"] += 1
                if rush_yards >= 15 or rush_yards >= distance or touchdown:
                    bucket["pbp_escape_explosives"] += 1

    return dict(output)


def _fetch_team_play_stats(client: Any, year: int, team: str) -> list[dict[str, Any]]:
    rows = client.get(
        "/plays/stats", year=year, team=team, seasonType="both"
    )
    if len(rows) < PLAY_STATS_LIMIT:
        return rows
    partitioned: list[dict[str, Any]] = []
    for week in range(1, 19):
        partitioned.extend(
            client.get(
                "/plays/stats",
                year=year,
                week=week,
                team=team,
                seasonType="both",
            )
        )
    deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in partitioned:
        key = (
            row.get("gameId"),
            row.get("playId"),
            row.get("athleteId"),
            row.get("statType"),
            row.get("stat"),
        )
        deduplicated[key] = row
    return list(deduplicated.values())


def build_normalized_dataset(
    client: Any,
    roster_year: int = 2026,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    include_pbp: bool = True,
    minimum_teams: int = 120,
    minimum_qbs: int = 500,
    minimum_team_coverage: float = 0.90,
) -> dict[str, Any]:
    """Fetch and normalize a private cohort file compatible with ``score_records``."""

    teams = client.get("/teams/fbs", year=roster_year)
    roster = client.get("/roster", year=roster_year, classification="fbs")
    quarterbacks = [
        player for player in roster if str(player.get("position", "")).upper() == "QB"
    ]
    quality_checks = validate_cohort(
        teams,
        quarterbacks,
        minimum_teams=minimum_teams,
        minimum_qbs=minimum_qbs,
        minimum_team_coverage=minimum_team_coverage,
    )
    team_conference = {
        str(team.get("school")): team.get("conference") for team in teams
    }

    if include_pbp:
        available_types = validate_play_stat_types(client.get("/plays/stats/types"))
        quality_checks["required_play_stat_types_present"] = True
        quality_checks["play_stat_type_count"] = len(available_types)

    stat_rows: list[dict[str, Any]] = []
    for season in seasons:
        for category in ("passing", "rushing"):
            stat_rows.extend(
                client.get(
                    "/stats/player/season",
                    year=season,
                    seasonType="both",
                    category=category,
                )
            )
    stats = _aggregate_season_stats(stat_rows)

    records: list[dict[str, Any]] = []
    for player in quarterbacks:
        player_id = str(player["id"])
        selected: dict[str, Any] | None = None
        for season in seasons:
            candidate = stats.get((player_id, season))
            if not candidate:
                continue
            opportunities = candidate["pass_attempts"] + candidate["rush_attempts"]
            if candidate["pass_attempts"] >= 20 and opportunities >= 40:
                selected = candidate
                break
        if selected is None:
            for season in seasons:
                candidate = stats.get((player_id, season))
                if candidate and candidate["pass_attempts"] + candidate["rush_attempts"] > 0:
                    selected = candidate
                    break

        current_team = str(player.get("team", ""))
        record = {
            "player_id": player_id,
            "player_name": " ".join(
                part for part in (player.get("firstName"), player.get("lastName")) if part
            ).strip(),
            "team": current_team,
            "conference": team_conference.get(current_team),
            "stats_season": selected["stats_season"] if selected else None,
            "stats_teams": sorted(selected["stats_teams"]) if selected else [],
            "pass_attempts": selected["pass_attempts"] if selected else 0,
            "completions": selected["completions"] if selected else 0,
            "pass_yards": selected["pass_yards"] if selected else 0,
            "interceptions": selected["interceptions"] if selected else 0,
            "long_pass": selected["long_pass"] if selected else 0,
            "sacks": selected["sacks"] if selected else None,
            "sacks_source": (
                "season" if selected and selected["sacks"] is not None else None
            ),
            "rush_attempts": selected["rush_attempts"] if selected else 0,
            "rush_yards": selected["rush_yards"] if selected else 0,
            "long_rush": selected["long_rush"] if selected else 0,
            **_new_pbp_bucket(),
        }
        records.append(record)

    if include_pbp:
        ids_by_team_season: dict[tuple[int, str], set[str]] = defaultdict(set)
        for record in records:
            if record["stats_season"] is None:
                continue
            for stats_team in record["stats_teams"] or [record["team"]]:
                ids_by_team_season[(record["stats_season"], stats_team)].add(
                    record["player_id"]
                )

        record_by_id = {record["player_id"]: record for record in records}
        for (season, team), player_ids in sorted(ids_by_team_season.items()):
            play_rows = _fetch_team_play_stats(client, season, team)
            aggregates = aggregate_play_stats(play_rows, player_ids)
            for player_id, values in aggregates.items():
                target = record_by_id[player_id]
                for field, value in values.items():
                    if field in {"pbp_long_pass", "pbp_long_rush"}:
                        target[field] = max(target[field], value)
                    else:
                        target[field] += value

        for record in records:
            if record["pbp_pass_attempts"] or record["pbp_qb_rushes"] or record["pbp_sacks"]:
                pass_attempts = record["pass_attempts"]
                coverage = (
                    record["pbp_pass_attempts"] / pass_attempts
                    if pass_attempts
                    else None
                )
                coverage_ok = (
                    coverage is not None
                    and DEFAULT_CONFIG.pbp_coverage_min
                    <= coverage
                    <= DEFAULT_CONFIG.pbp_coverage_max
                )
                if record["sacks"] is None and coverage_ok:
                    record["sacks"] = record["pbp_sacks"]
                    record["sacks_source"] = "play-by-play"
                record["long_pass"] = max(record["long_pass"], record["pbp_long_pass"])
                record["long_rush"] = max(record["long_rush"], record["pbp_long_rush"])

    for record in records:
        record.pop("pbp_long_pass", None)
        record.pop("pbp_long_rush", None)
    records.sort(key=lambda row: (row["team"], row["player_name"], row["player_id"]))
    return {
        "metadata": {
            "source": "CollegeFootballData.com",
            "terms_url": TERMS_URL,
            "roster_year": roster_year,
            "production_seasons": list(seasons),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "network_calls": getattr(client, "network_calls", None),
            "quality_checks": quality_checks,
            "publication_status": "private normalized input - do not publish",
        },
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a private normalized MAP-Q input from CollegeFootballData."
    )
    parser.add_argument("--output", type=Path, default=Path("work/cfbd_normalized.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("work/cfbd_cache"))
    parser.add_argument("--roster-year", type=int, default=2026)
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=list(DEFAULT_SEASONS),
        help="Production seasons in newest-to-oldest selection order",
    )
    parser.add_argument(
        "--refresh-year",
        type=int,
        action="append",
        dest="refresh_years",
        default=[],
        help="Bypass existing cache entries for this year; repeat as needed",
    )
    parser.add_argument("--call-budget", type=int, default=900)
    parser.add_argument("--skip-pbp", action="store_true")
    args = parser.parse_args(argv)

    seasons = tuple(args.seasons)
    if len(seasons) != len(set(seasons)):
        parser.error("--seasons cannot contain duplicates")
    if seasons != tuple(sorted(seasons, reverse=True)):
        parser.error("--seasons must be ordered from newest to oldest")

    client = CFBDClient(
        cache_dir=args.cache_dir,
        call_budget=args.call_budget,
        refresh_years=args.refresh_years,
    )
    payload = build_normalized_dataset(
        client,
        roster_year=args.roster_year,
        seasons=seasons,
        include_pbp=not args.skip_pbp,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(payload['records'])} private normalized records; "
        f"network calls: {client.network_calls}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
