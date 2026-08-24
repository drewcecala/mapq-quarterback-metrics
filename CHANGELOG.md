# Changelog

## 1.1.0 — 2026-08-24

- Added 2026 production-season support and rolled recency weights forward while retaining 2023 as a reduced-weight fallback.
- Added explicit current-year cache refreshes so weekly pulls reuse historical responses without serving stale in-season statistics.
- Added an in-season GitHub Actions workflow for authorized acquisition, scoring, release validation, and derived-only publication.
- Added fail-closed checks for source-terms changes, cohort coverage, freshness, field contracts, duplicate identities, score ranges, and JSON/CSV parity.

## 1.0.0 — 2026-08-24

- Published the MAP-Q scoring contract and reference implementation.
- Added Defense Stress Index, Drive Extension Index, and Escape-to-Explosive Rate proxy.
- Added explicit sample thresholds, play-level coverage gates, recency shrinkage, and deterministic advanced-metric rankings.
- Added input validation, synthetic examples, unit tests, and a release audit.
- Separated source-restricted player data, API caches, and private workbooks from the public package.
- Added an authorized CollegeFootballData acquisition adapter with private caching, call budgets, response-limit partitioning, and player-linked play aggregation.
- Added a derived-only release command that strips official statistics, source identifiers, and unscored roster rows.
- Added the August 24, 2026 derived-ranking release in JSON and CSV formats: 228 eligible quarterbacks selected from a 721-player, 138-team FBS cohort.
