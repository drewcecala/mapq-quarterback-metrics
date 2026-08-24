# Changelog

## 1.0.0 — 2026-08-24

- Published the MAP-Q scoring contract and reference implementation.
- Added Defense Stress Index, Drive Extension Index, and Escape-to-Explosive Rate proxy.
- Added explicit sample thresholds, play-level coverage gates, recency shrinkage, and deterministic advanced-metric rankings.
- Added input validation, synthetic examples, unit tests, and a release audit.
- Separated source-restricted player data, API caches, and private workbooks from the public package.
- Added an authorized CollegeFootballData acquisition adapter with private caching, call budgets, response-limit partitioning, and player-linked play aggregation.
- Added a derived-only release command that strips official statistics, source identifiers, and unscored roster rows.
