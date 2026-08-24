# Public release artifacts

This directory is reserved for sanitized, derived-only MAP-Q releases. A release may include player and team names as report context, model scores, ranks, tiers, reliability, metric definitions, retrieval date, model version, and the attribution “Data provided by CollegeFootballData.com.”

## Latest in-season release

- [Latest JSON](mapq_derived_rankings_latest.json) — stable machine-readable URL with definitions and retrieval metadata.
- [Latest CSV](mapq_derived_rankings_latest.csv) — stable spreadsheet-ready URL.

The latest files are updated by the validated weekly workflow during September–January and appear after its first successful run. Git history preserves prior weekly versions.

## August 24, 2026

- [JSON release](mapq_derived_rankings_2026-08-24.json) — includes definitions, source attribution, retrieval metadata, and 228 ranked records.
- [CSV release](mapq_derived_rankings_2026-08-24.csv) — the same 228 ranked records in spreadsheet-ready form.

The source cohort contains 721 quarterbacks across all 138 FBS teams. Only quarterbacks meeting MAP-Q's published eligibility rules appear in the derived release. DSI, DEI, or EER-proxy fields may be blank when play-by-play coverage or metric-specific sample requirements are not met.

Do not place official statistical totals, source-system identifiers, raw or normalized API responses, play-by-play rows, API caches, or credentials here. Build those materials only in ignored private directories, then run `mapq-release` and `python tools/release_check.py` before staging an artifact.
