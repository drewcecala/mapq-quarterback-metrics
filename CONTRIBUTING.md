# Contributing

Changes should preserve transparency and reproducibility.

1. Create a focused branch.
2. Add or update tests for every scoring change.
3. Run `python -m unittest discover -s tests -v`.
4. Run `python tools/release_check.py`.
5. Update the methodology and changelog if any formula, threshold, field, or interpretation changes.

Do not commit real-player source data, source-site HTML, private/source-bearing workbooks, access credentials, private URLs, or acquisition code whose use would conflict with a provider's terms. A derived-only workbook belongs in `release/` and must pass the release audit. Examples must be unmistakably fictional.

Metric changes must explain the football rationale, expected tradeoffs, and sensitivity to the comparison cohort. A weight change that can alter scores requires a model-version change.
