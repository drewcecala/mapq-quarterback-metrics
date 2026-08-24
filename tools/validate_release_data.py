#!/usr/bin/env python3
"""Validate a generated JSON/CSV ranking pair before publication."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mapq.model import MODEL_VERSION
from mapq.release import PUBLIC_FIELDS


REQUIRED_VALUES = (
    "mapq_rank",
    "player_name",
    "team",
    "conference",
    "stats_season",
    "mapq",
    "tier",
    "data_status",
    "accuracy_score",
    "arm_proxy_score",
    "mobility_score",
    "escape_score",
    "passing_capability",
    "movement_capability",
    "reliability",
    "advanced_data_status",
)
SCORE_FIELDS = (
    "mapq",
    "accuracy_score",
    "arm_proxy_score",
    "mobility_score",
    "escape_score",
    "passing_capability",
    "movement_capability",
    "defense_stress_index",
    "drive_extension_index",
)


def _number_in_range(value: Any, lower: float, upper: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and lower <= value <= upper
    )


def validate(
    json_path: Path,
    csv_path: Path,
    *,
    minimum_records: int,
    roster_year: int,
    current_season: int,
) -> list[str]:
    errors: list[str] = []
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return ["JSON payload must contain a records array"]

    if payload.get("model_version") != MODEL_VERSION:
        errors.append(
            f"model version mismatch: {payload.get('model_version')!r} != {MODEL_VERSION!r}"
        )
    if payload.get("artifact_type") != "derived rankings and model outputs":
        errors.append("artifact_type is missing or unexpected")
    if payload.get("source_attribution") != "Data provided by CollegeFootballData.com":
        errors.append("source attribution is missing or unexpected")
    if len(records) < minimum_records:
        errors.append(f"only {len(records)} ranked records; expected at least {minimum_records}")

    metadata = payload.get("source_metadata", {})
    quality = metadata.get("quality_checks", {}) if isinstance(metadata, dict) else {}
    if metadata.get("roster_year") != roster_year:
        errors.append(f"roster year is not {roster_year}")
    if current_season not in metadata.get("production_seasons", []):
        errors.append(f"production seasons do not include {current_season}")
    if quality.get("fbs_team_count", 0) < 130:
        errors.append("FBS team coverage is below 130 teams")
    if quality.get("quarterback_count", 0) < 500:
        errors.append("source cohort contains fewer than 500 quarterbacks")
    if quality.get("quarterback_team_coverage", 0) < 0.95:
        errors.append("quarterback team coverage is below 95%")
    if quality.get("unique_quarterback_ids") is not True:
        errors.append("source cohort did not confirm unique quarterback IDs")
    if quality.get("required_play_stat_types_present") is not True:
        errors.append("required play-stat types were not confirmed")

    retrieved_value = metadata.get("retrieved_at")
    try:
        retrieved_at = datetime.fromisoformat(str(retrieved_value))
        if retrieved_at.tzinfo is None:
            raise ValueError("timestamp lacks timezone")
        age = datetime.now(timezone.utc) - retrieved_at.astimezone(timezone.utc)
        if age < -timedelta(minutes=5) or age > timedelta(hours=48):
            errors.append(f"retrieval timestamp is not current: {retrieved_value!r}")
    except (TypeError, ValueError):
        errors.append(f"invalid retrieval timestamp: {retrieved_value!r}")

    identities: set[tuple[str, str]] = set()
    ranks: list[int] = []
    for index, row in enumerate(records, start=1):
        if not isinstance(row, dict):
            errors.append(f"record {index} is not an object")
            continue
        if tuple(row) != PUBLIC_FIELDS:
            errors.append(f"record {index} does not match the public field contract")
        missing = [field for field in REQUIRED_VALUES if row.get(field) in (None, "")]
        if missing:
            errors.append(f"record {index} is missing required values: {', '.join(missing)}")
        identity = (
            str(row.get("player_name", "")).strip().casefold(),
            str(row.get("team", "")).strip().casefold(),
        )
        if identity in identities:
            errors.append(f"duplicate player/team identity at record {index}")
        identities.add(identity)
        rank = row.get("mapq_rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            errors.append(f"invalid MAP-Q rank at record {index}: {rank!r}")
        else:
            ranks.append(rank)
        for field in SCORE_FIELDS:
            value = row.get(field)
            if value is not None and not _number_in_range(value, 0.0, 100.0):
                errors.append(f"{field} is outside 0-100 at record {index}")
        if not _number_in_range(row.get("reliability"), 0.0, 1.0):
            errors.append(f"reliability is outside 0-1 at record {index}")
        rate = row.get("escape_to_explosive_rate_proxy")
        if rate is not None and not _number_in_range(rate, 0.0, 1.0):
            errors.append(f"EER proxy is outside 0-1 at record {index}")
    if ranks != sorted(ranks):
        errors.append("records are not sorted by MAP-Q rank")
    if ranks and ranks[0] != 1:
        errors.append("first MAP-Q rank is not 1")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        csv_rows = list(reader)
        if tuple(reader.fieldnames or ()) != PUBLIC_FIELDS:
            errors.append("CSV header does not match the public field contract")
    if len(csv_rows) != len(records):
        errors.append(
            f"CSV/JSON record counts differ: {len(csv_rows)} != {len(records)}"
        )
    else:
        json_keys = [f"{row['mapq_rank']}|{row['player_name']}|{row['team']}" for row in records]
        csv_keys = [f"{row['mapq_rank']}|{row['player_name']}|{row['team']}" for row in csv_rows]
        if csv_keys != json_keys:
            errors.append("CSV and JSON record ordering or identities differ")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--minimum-records", type=int, default=150)
    parser.add_argument("--roster-year", type=int, required=True)
    parser.add_argument("--current-season", type=int, required=True)
    args = parser.parse_args(argv)
    errors = validate(
        args.json_path,
        args.csv_path,
        minimum_records=args.minimum_records,
        roster_year=args.roster_year,
        current_season=args.current_season,
    )
    if errors:
        print("Weekly release validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    print(f"Weekly release validation passed: {len(payload['records'])} ranked records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
