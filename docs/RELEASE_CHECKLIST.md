# Public release checklist

## Before the first push

- [ ] Create the repository under the intended owner as private.
- [ ] Confirm the repository name, description, topics, and social image contain no internal authoring or provenance branding.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python tools/release_check.py`.
- [ ] Run `mapq-verify-official --rebuild-current-roster` for the release roster date and confirm `canonical_roster_complete: true`.
- [ ] Review every addition, removal, correction, and rename in `roster_reconciliation_private.csv`; rebuild downstream metrics against the canonical current cohort.
- [ ] Confirm all current official rows have player, team, QB position, hometown, direct source URL, and retrieval date; retain the canonical roster and row-level audit only under ignored `work/` storage.
- [ ] Place only sanitized derived artifacts in `release/`; keep source-bearing workbooks in ignored `outputs/`.
- [ ] Inspect `git status --short --ignored` and confirm `outputs/`, `work/`, and `scripts/` remain ignored.
- [ ] Review every staged path with `git diff --cached --name-status`.
- [ ] Review every staged change with `git diff --cached`.
- [ ] Scan staged text, file paths, metadata, and the proposed commit message for credentials, local absolute paths, internal tooling, and authoring provenance.
- [ ] Confirm the commit contains no real-player source data, private workbook, API cache, source-site snapshot, or unauthorized acquisition utility.
- [ ] Open every release workbook and confirm definitions, source attribution, retrieval date, model version, filters, and charts are legible.

## Before making the repository public

- [ ] Obtain the owner's explicit approval for the visibility change.
- [ ] Recheck the current terms and licenses for every referenced data source.
- [ ] Spot-check the official roster registry and confirm all links still resolve to the stated season.
- [ ] Confirm the verification retrieval date and terms-review date are current for this release.
- [ ] Confirm the example remains fictional and marked `synthetic: true`.
- [ ] Confirm `CITATION.cff`, the changelog, package version, and model version agree.
- [ ] Add the final repository URL to `CITATION.cff` only after the repository exists.
- [ ] Create a signed or annotated release tag matching the package and model version after the reviewed commit is final.

Public repository visibility is not a substitute for data-redistribution permission.
