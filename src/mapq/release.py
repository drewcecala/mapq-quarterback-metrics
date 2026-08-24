"""Create a derived-only public release from a privately scored cohort."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .model import MODEL_VERSION

SOURCE_TERMS_REVIEW_DATE = "2026-08-24"
METRIC_DEFINITIONS = {
    "mapq": (
        "Mobility, Arm & Precision Quotient: a reliability-adjusted 0-100 geometric "
        "blend of passing capability and movement capability."
    ),
    "defense_stress_index": (
        "Defense Stress Index: a reliability-adjusted blend of deep-ball production, "
        "scramble threat, rushing frequency, and explosive-play rate."
    ),
    "drive_extension_index": (
        "Drive Extension Index: a 0-100 blend of third-down conversions, touchdowns, "
        "and sack avoidance."
    ),
    "escape_to_explosive_rate_proxy": (
        "Escape-to-Explosive Rate proxy: the share of estimated long-yardage escape "
        "opportunities that become a first down, touchdown, or 15-plus-yard QB rush."
    ),
}

PUBLIC_FIELDS = (
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
    "defense_stress_index",
    "dsi_rank",
    "drive_extension_index",
    "dei_rank",
    "escape_to_explosive_rate_proxy",
    "eer_proxy_rank",
    "advanced_data_status",
)


def public_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select only rankings, model outputs, and minimal report context."""

    scored = [row for row in records if row.get("mapq") is not None]
    output = [{field: row.get(field) for field in PUBLIC_FIELDS} for row in scored]
    return sorted(
        output,
        key=lambda row: (
            row["mapq_rank"] if row["mapq_rank"] is not None else 10**9,
            str(row["player_name"]).casefold(),
        ),
    )


def _read_payload(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("input JSON must contain a records array")
    metadata = payload.get("source_metadata", {}) if isinstance(payload, dict) else {}
    return records, metadata if isinstance(metadata, dict) else {}


def _public_source_metadata(source_metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "retrieved_at",
        "roster_year",
        "production_seasons",
        "quality_checks",
    }
    return {key: source_metadata[key] for key in allowed if key in source_metadata}


def _write(
    path: Path, records: list[dict[str, Any]], source_metadata: dict[str, Any] | None = None
) -> None:
    if path.suffix.lower() == ".json":
        payload = {
            "model_version": MODEL_VERSION,
            "source_attribution": "Data provided by CollegeFootballData.com",
            "source_terms_reviewed_at": SOURCE_TERMS_REVIEW_DATE,
            "artifact_type": "derived rankings and model outputs",
            "metric_definitions": METRIC_DEFINITIONS,
            "source_metadata": _public_source_metadata(source_metadata or {}),
            "records": records,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return
    if path.suffix.lower() == ".csv":
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(PUBLIC_FIELDS))
            writer.writeheader()
            writer.writerows(records)
        return
    raise ValueError("public release output must be .json or .csv")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strip private source fields and write a derived-only MAP-Q release."
    )
    parser.add_argument("input", type=Path, help="Privately scored JSON")
    parser.add_argument("output", type=Path, help="Public .json or .csv")
    args = parser.parse_args(argv)
    private_records, source_metadata = _read_payload(args.input)
    records = public_records(private_records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write(args.output, records, source_metadata)
    print(f"Wrote {len(records)} derived player rankings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
