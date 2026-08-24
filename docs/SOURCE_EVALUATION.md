# Source evaluation for a public MAP-Q release

Review date: 2026-08-24

## Decision

Use current official school athletics pages for no-key roster verification and CollegeFootballData (CFBD), under a user-owned key, only for the statistical inputs needed by the scoring model. Publish a **derived-output workbook**, not a bulk copy of either source.

The official-source workflow reduces roster acquisition to one current page per school, records a direct URL for every team, respects `robots.txt`, and retains page snapshots only in private ignored storage. Official pages are verification evidence; they do not create a blanket license to republish page content or a raw roster mirror.

CFBD remains the only evaluated source that combines season-level player statistics and player-linked play data with terms that expressly permit publishing independent analyses, rankings, model outputs, and visualizations. Its terms do not permit publishing the API data itself as a standalone dataset or bulk download.

No evaluated source provides all required inputs under an unrestricted open-data license.

## Candidate matrix

| Source | Roster | Season stats | Player PBP | Public release rights | Decision |
|---|---:|---:|---:|---|---|
| [Official school athletics rosters](../sources/official_rosters_2026.csv) | Yes | Limited | No | Facts can be checked; site content and contractual restrictions vary by school | **Primary private roster verification** |
| [CollegeFootballData](https://collegefootballdata.com/terms) | Yes | Yes | Yes | Derived outputs and ordinary reports permitted; bulk API-data redistribution prohibited | **Recommended for derived workbook** |
| [Wikidata](https://www.wikidata.org/wiki/Wikidata:Licensing) | Partial | No | No | Structured data is CC0 | Optional identity cross-check only |
| [Sportradar NCAA Football](https://developer.sportradar.com/football/reference/ncaafb-overview) | Yes | Yes | Yes | Trial is evaluation-only; production display and distribution depend on an order form | Custom contract required |
| [SportsDataIO College Football](https://sportsdata.io/developers/api-documentation/ncaa-football) | Yes | Yes | Yes | [General terms](https://sportsdata.io/terms-of-service) grant a limited, nontransferable license; self-service Discovery Lab data is not licensed for commercial redistribution | Written permission or contract required |
| [NCAA.com](https://www.ncaa.com/tos) | Partial | Yes | Limited | Terms restrict copying, redistribution, publication, and commercial exploitation | Reject for automated public pipeline |
| [`cfbfastR-data`](https://github.com/sportsdataverse/cfbfastR-data) | Historical files | Yes | Yes | No repository-level data license identified | Reject until an applicable license is added |
| ESPN products | Yes | Yes | Limited | Terms restrict automated extraction and dataset compilation | Reject |

## Official roster coverage

The no-key verifier requires player name, current team, quarterback position, hometown city, and state/country. It accepts conventional table, list/card, and structured roster presentations, normalizes common state abbreviations, and produces a team-level parser report. A site that blocks access or omits a required field is routed to direct player-bio review.

The source registry is publishable citation metadata. Downloaded pages, the normalized official roster, and the row-level reconciliation remain private build inputs.

## CFBD statistical field coverage

The current CFBD OpenAPI contract provides the following operations:

| Pipeline requirement | CFBD operation | Required fields |
|---|---|---|
| Current FBS team universe | `GET /teams/fbs?year=2026` | team ID, school, conference, classification |
| Current quarterback roster | `GET /roster?year=2026&classification=fbs` | player ID, name, team, position, height, weight, jersey |
| Selected-season passing totals | `GET /stats/player/season` with `category=passing` | attempts, completions, yards, interceptions, long pass, sacks when available |
| Selected-season rushing totals | `GET /stats/player/season` with `category=rushing` | carries, yards, long rush |
| Player-linked play events | `GET /plays/stats` | athlete ID, play ID, stat type, yards, down, distance |
| Play context when needed | `GET /plays` | play ID, yards gained, scoring flag, play type, text |

The roster response also includes hometown city, state, country, latitude, longitude, and county FIPS. Those fields support a private field-level verification audit of every input QB. See the [player verification protocol](PLAYER_VERIFICATION.md). Verification summaries and derived geographic aggregates may be released; the complete row-level provider comparison remains private.

CFBD's play-stat associations identify completions, incompletions, interceptions thrown, rushes, sacks taken, and touchdowns. Those events are sufficient to reproduce the published DSI, DEI, and EER-proxy definitions, subject to coverage reconciliation and the existing minimum-sample gates.

## Publishable workbook boundary

The public workbook may contain independently calculated outputs such as:

- player, current team, and selected season as report context;
- MAP-Q and component scores;
- DSI, DEI, and EER proxy;
- eligibility status, reliability, ranks, tiers, and cohort counts;
- methodology, model weights, limitations, and source attribution;
- charts and leaderboard views.

The public workbook should not contain:

- a complete raw FBS roster export;
- official pass/rush totals copied across the full cohort;
- raw or normalized API responses;
- play descriptions or a play-by-play table;
- API keys, cache files, or source-system identifiers that are not necessary to interpret the rankings;
- source logos or player photographs.

The private build artifact may retain raw inputs for auditing. It must remain ignored by Git.

## Pipeline release boundary

The acquisition and scoring code may be public. The official-roster pipeline must:

1. use the tracked direct-source registry;
2. check `robots.txt` and never bypass a disallow rule;
3. identify itself with a descriptive user agent;
4. cache page snapshots only in an ignored local directory;
5. retain only factual verification fields; and
6. fail closed on stale-year pages, duplicate teams, incomplete identities, or missing hometowns.

The optional CFBD statistics pipeline must:

1. read `CFBD_API_KEY` from the environment;
2. send the key only in the server-side bearer header;
3. cache raw responses only in an ignored local directory;
4. avoid printing the key or embedding it in URLs;
5. enforce API quotas, bounded retries, and response-size checks;
6. validate player-ID joins, season coverage, and PBP-to-official-attempt reconciliation;
7. separate the private normalized input from the public derived release;
8. attribute the source as “Data provided by CollegeFootballData.com”; and
9. record the model version, retrieval date, and CFBD terms-review date.

The CFBD free tier currently advertises 1,000 calls per month. A team-season or selected-player PBP strategy should stay below that limit for a full refresh; the pipeline must count calls and stop before exceeding a configured budget.

The scheduled workflow restores an encrypted GitHub Actions cache for immutable historical responses, decrypts it only inside the ephemeral runner, force-refreshes 2026 endpoints once per run, and stops at 225 network calls. Before acquisition, it confirms that the published CFBD Terms still carry the reviewed August 12, 2026 effective date; a change blocks publication pending human review.

## Quality risks requiring tests

| Risk | Severity | Required control |
|---|---|---|
| 2026 roster not yet complete or stale | High | Team count, QB count, and per-team coverage checks; retrieval date in release |
| Player ID changes or unmatched transfers | High | Unique roster IDs and explicit unmatched-player report |
| Players with multiple teams in one season | Medium | Aggregate by player ID and season; retain team-season lineage privately |
| PBP response reaches the 2,000-row endpoint limit | High | Detect the limit and automatically partition by week |
| PBP pass attempts disagree with season totals | High | Preserve the 85%–115% eligibility gate and publish coverage counts |
| Stat-type schema changes | High | Fetch the stat-type dictionary and fail on missing required event types |
| Late statistical corrections | Medium | Cache retrieval metadata and make releases immutable by model/data date |
| Unsupported or missing sacks/long-play fields | High | Derive from player-linked plays or leave the affected score null; never silently substitute zero |

## If the complete raw workbook must be public

Obtain written permission that expressly allows GitHub publication of a downloadable workbook containing a complete current FBS roster, official player season totals, and derived metrics. The permission should cover noncommercial and commercial reuse, redistribution by downstream users, historical retention, and public versioned releases.

Suggested request to CFBD:

> We are building an open-source quarterback evaluation project that uses the CFBD API to calculate original rankings. May we publish a versioned XLSX/CSV containing the complete current FBS quarterback roster, selected official season totals, and our derived scores? The files would be downloadable from a public GitHub repository under a clearly stated data license, with CFBD attribution and no raw API responses or play descriptions. Please confirm the fields and redistribution rights you authorize, including downstream reuse and historical retention.

Without that written permission, publish only the derived-output workbook described above.
