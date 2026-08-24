# MAP-Q quarterback metric engine

MAP-Q (Mobility, Arm & Precision Quotient) is an original 0–100 quarterback evaluation framework. It rewards quarterbacks who combine passing capability with movement capability, then reduces the influence of small or older samples.

The repository also defines three situational metrics:

- **Defense Stress Index (DSI):** a reliability-adjusted blend of deep-ball production, scramble threat, rushing frequency, and explosive-play rate.
- **Drive Extension Index (DEI):** a blend of third-down conversions, touchdowns, and sack avoidance.
- **Escape-to-Explosive Rate (EER proxy):** the share of estimated long-yardage escape opportunities that become a first down, touchdown, or 15-plus-yard quarterback rush.

This public package contains the scoring engine, complete formulas, validation rules, tests, a fictional example, a no-key official-roster verifier, and an optional CollegeFootballData acquisition adapter. It intentionally excludes real-player source data, page caches, API caches, and private generated workbooks. See [Data rights](docs/DATA_RIGHTS.md) before combining the engine with third-party data.

## Current derived rankings

The 2026 roster refresh produced 228 MAP-Q-eligible quarterbacks from a private 721-player FBS quarterback cohort. Download the sanitized [JSON](release/mapq_derived_rankings_2026-08-24.json) or [CSV](release/mapq_derived_rankings_2026-08-24.csv) release. The files contain model outputs and report context, not raw provider statistics.

The release was retrieved on August 24, 2026 and selects each current quarterback's most recent qualifying production season from 2023–2025. Situational metrics remain blank when play-by-play coverage or the minimum sample is insufficient.

## Weekly in-season refresh

The [weekly refresh workflow](.github/workflows/weekly-refresh.yml) runs Wednesdays at 11:17 UTC from September 2026 through January 2027 and can also be started manually. It refreshes the 2026 roster and statistics, reuses encrypted historical caches to conserve API calls, validates the full cohort, and publishes only the derived [latest JSON](release/mapq_derived_rankings_latest.json) and [latest CSV](release/mapq_derived_rankings_latest.csv). An explicit season-window guard prevents the 2026 configuration from running on a future season.

The workflow requires a repository Actions secret named `CFBD_API_KEY`; a separate `CFBD_CACHE_KEY` encrypts cached API responses at rest. Each secret is provided only to the step that needs it and is never written to a release file or log. The job stops if the CFBD Terms effective date changes, source coverage falls below its quality gates, the per-run 225-call budget is reached, or release validation fails.

## Why MAP-Q is different

The headline score is geometric rather than additive:

```text
Raw MAP-Q = 100 × (Passing / 100)^0.60 × (Movement / 100)^0.40
MAP-Q     = 50 + (Raw MAP-Q − 50) × Reliability
```

The geometric blend makes balance matter: one elite dimension cannot fully erase a weak one. Every component begins with a transparent midrank percentile against a defined comparison cohort.

## Quick start

Python 3.11 or newer is required. The engine has no runtime dependencies.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
mapq examples/sample_input.json scored.json
# equivalent: python -m mapq examples/sample_input.json scored.json
python -m unittest discover -s tests -v
python tools/release_check.py
```

The command accepts JSON or CSV and writes JSON or CSV based on the output extension. Input field definitions are in the [data dictionary](docs/DATA_DICTIONARY.md).

## No-key official-roster verification

The tracked [official source registry](sources/official_rosters_2026.csv) points to one current school athletics roster per team. The verifier checks each site's `robots.txt`, requests a table/list/print presentation, stores page snapshots only under ignored `work/`, and retains only the factual fields needed for the audit.

```bash
mapq-verify-official \
  work/map_qb_counties/geocoded_qbs.json \
  --sources sources/official_rosters_2026.csv \
  --output-dir work/official_verification \
  --rebuild-current-roster
```

The command produces a private canonical roster, a reconciliation showing additions/removals/corrections, a row-level audit, and an aggregate summary. A source blocked by `robots.txt` is not bypassed; it is routed to manual official-page review. See the [player verification protocol](docs/PLAYER_VERIFICATION.md).

## Optional CFBD statistics pipeline

The source adapter uses a user-owned CollegeFootballData key and writes all source fields to ignored private storage. The final release command removes official statistics, source identifiers, and unscored roster rows before publication.

```bash
export CFBD_API_KEY="$YOUR_SECURE_KEY"
mapq-cfbd \
  --output work/cfbd_normalized.json \
  --seasons 2026 2025 2024 2023 \
  --refresh-year 2026
mapq work/cfbd_normalized.json work/cfbd_scored.json
mapq-release work/cfbd_scored.json outputs/mapq_derived_rankings.json
```

The CFBD adapter is for authorized season statistics and player-linked plays. It is no longer required for current-roster verification.

Only the final derived rankings are candidates for public release. Sanitized JSON, CSV, and XLSX release artifacts belong in `release/`; private build products remain in ignored directories. Review the [source evaluation](docs/SOURCE_EVALUATION.md) and the current CFBD terms before every refresh.

## Interpretation

- Scores are relative to the supplied cohort, not absolute scouting grades.
- The arm component is a vertical-production proxy, not measured ball velocity.
- Official college rushing totals may include sacks and kneels.
- DSI describes observed production stress, not coverage geometry.
- DEI measures third-down production; penalty-only conversions are excluded.
- EER is explicitly a proxy because universal pressure and avoided-sack charting are not part of the input contract.
- Scheme, supporting cast, opponent strength, pressure rate, and play calling remain important context.

See the full [methodology](docs/METHODOLOGY.md), [data dictionary](docs/DATA_DICTIONARY.md), [source evaluation](docs/SOURCE_EVALUATION.md), and [contribution guide](CONTRIBUTING.md).

Maintainers should complete the [public release checklist](docs/RELEASE_CHECKLIST.md) before a push or visibility change.

## Versioning

Metric weights and eligibility thresholds are part of the public model contract. Any change that can alter a score requires a model-version change and a documented regression test.

## License

Original code and documentation are available under the [MIT License](LICENSE). That license does not grant rights to third-party data, names, logos, marks, or source-site content.
