"""Command-line interface for cohort scoring."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .model import MODEL_VERSION, score_records


def _read_payload(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records") if isinstance(payload, dict) else payload
        if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
            raise ValueError("JSON input must be an array of objects or contain a records array")
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        return records, metadata if isinstance(metadata, dict) else {}
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle)), {}
    raise ValueError("input must use a .json or .csv extension")


def _read_records(path: Path) -> list[dict[str, Any]]:
    return _read_payload(path)[0]


def _write_records(
    path: Path, records: list[dict[str, Any]], source_metadata: dict[str, Any] | None = None
) -> None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = {"model_version": MODEL_VERSION, "records": records}
        if source_metadata:
            payload["source_metadata"] = source_metadata
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    if suffix == ".csv":
        fieldnames: list[str] = []
        for record in records:
            for field in record:
                if field not in fieldnames:
                    fieldnames.append(field)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
        return
    raise ValueError("output must use a .json or .csv extension")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a full quarterback cohort with MAP-Q model 1.1.0."
    )
    parser.add_argument("input", type=Path, help="Input .json or .csv file")
    parser.add_argument("output", type=Path, help="Output .json or .csv file")
    args = parser.parse_args(argv)

    records, source_metadata = _read_payload(args.input)
    scored = score_records(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_records(args.output, scored, source_metadata)
    print(f"Scored {len(scored)} quarterbacks with MAP-Q model {MODEL_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
