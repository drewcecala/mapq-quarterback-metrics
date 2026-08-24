# Data rights and source policy

This repository licenses only its original code and documentation. It does not grant rights to third-party statistics, roster information, player names, team names, logos, marks, or website content.

Real-player API responses and normalized source datasets are intentionally excluded from the public release. Acquisition code may be published when it uses an authorized API, protects credentials, and keeps source data in ignored local storage. The example input is fictional and marked synthetic.

## Source-specific cautions

- ESPN-branded products are governed by the [Disney Terms of Use](https://disneytermsofuse.com/english/). Those terms include restrictions on automated access, extraction, database compilation, redistribution, and non-personal use. Do not publish data collected from an ESPN product unless you have a separate right or permission to do so.
- The public [`cfbfastR-data`](https://github.com/sportsdataverse/cfbfastR-data) repository provides useful football data files, but no repository-level license was identified for that repository when this project was prepared. Public accessibility alone does not create redistribution rights. Obtain permission or a clearly applicable license before republishing its data or derived row-level datasets.
- [CollegeFootballData](https://collegefootballdata.com/terms) expressly permits publishing independent analyses, model outputs, rankings, and visualizations, but prohibits publishing its API data as a standalone dataset or bulk download. It is the recommended pipeline source only when the public artifact contains derived outputs rather than a raw-data mirror.
- Official school athletics roster pages can verify factual player identity and hometown fields without a shared API key. Their site terms and content rights vary. The tracked URL registry and original verification code may be published, but page snapshots, copied page content, and the private normalized roster are not automatically cleared for redistribution.

These notes are a release safeguard, not legal advice. A maintainer should review the current source terms again before each public data release because terms and licenses can change.

## Acceptable public inputs

Use one of the following:

1. data you created and can license;
2. data under terms that permit the intended redistribution;
3. data supplied by the end user for local computation; or
4. a provider agreement that expressly permits publication of the resulting dataset.

When publishing scores, include the input provider, retrieval date, applicable license or permission, cohort definition, missing-data rate, and model version.

See the [source evaluation](SOURCE_EVALUATION.md) for the field-level recommendation and release boundary.
