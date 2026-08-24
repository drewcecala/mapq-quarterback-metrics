# Player verification protocol

This protocol verifies every quarterback at the player-team-hometown grain without publishing a raw provider roster. The row-level audit and API cache are private; only derived rankings, aggregate map counts, and the aggregate verification summary are candidates for release.

Review date: 2026-08-24

## Verification standard

A player is verified only when all of these fields agree with an accepted source:

1. player name;
2. current team for the stated roster season;
3. position listed as quarterback; and
4. hometown city plus state or country.

The pipeline assigns one of these statuses:

| Status | Meaning | Release treatment |
|---|---|---|
| `verified_official` | Unique name/team match and all required fields agree with an official school roster or bio | Pass |
| `verified_cfbd` | Optional authorized CFBD cross-check agrees on all required fields | Pass |
| `partial` | Identity matches, but a required hometown field is missing | Block |
| `conflict` | CFBD and the input disagree on team, position, or hometown | Block |
| `needs_review` | A fuzzy name match needs human confirmation | Block |
| `ambiguous` | More than one candidate could be the player | Block |
| `unmatched` | No unique roster candidate was found | Block |
| `conflict_official` / `not_found_official` | Official review confirmed a conflict or could not locate the player | Block |

The release gate is intentionally strict: all expected rows must be `verified_cfbd` or `verified_official` before the cohort is treated as verified.

## Primary no-key verification pass

The tracked source registry contains one current official school athletics roster URL per team. The verifier checks `robots.txt`, uses a descriptive user agent, makes at most a few presentation attempts per team, and stores HTML only in ignored private cache storage. It parses the factual name, QB position, and hometown fields from roster tables, roster cards, or structured roster data without copying biography prose, images, logos, or page design.

No credential is required:

```bash
mapq-verify-official \
  work/map_qb_counties/geocoded_qbs.json \
  --sources sources/official_rosters_2026.csv \
  --output-dir work/official_verification \
  --rebuild-current-roster
```

`--rebuild-current-roster` treats a complete official roster as the canonical current cohort even when the supplied comparison file contains stale players. Without it, the command exits nonzero until the input and official roster agree exactly.

## Private outputs

| File | Purpose |
|---|---|
| `player_verification_private.csv` | One row per input player with field-level evidence and status |
| `manual_review_private.csv` | Only unresolved, incomplete, ambiguous, or conflicting rows |
| `canonical_official_qb_roster_private.csv` | Current official QB cohort with factual hometown and source URL |
| `roster_reconciliation_private.csv` | Retained, removed, added, corrected, and renamed rows |
| `source_fetch_private.csv` | Per-team fetch/parser/robots result |
| `verification_summary.json` | Aggregate status counts and release gates |

Do not commit either private CSV. The aggregate summary can be published after confirming that it contains no row-level provider fields.

## Exception resolution pass

Only rows in `manual_review_private.csv` require individual research when preserving the old cohort. Use the direct current official player biography, not a search-result snippet or third-party aggregator. When rebuilding the cohort, official additions replace players absent from the current roster; hometown disagreements use the official value and remain visible in the reconciliation.

For every reviewed row, record:

- the input player and team exactly as shown in the queue;
- `decision`: `verified`, `conflict`, or `not_found`;
- the direct HTTPS school roster or biography URL;
- retrieval date and reviewer;
- the verified player name, team, position, and hometown; and
- a short factual note when needed.

Do not copy biography prose, photographs, logos, or page design. Record only the factual fields needed for the audit. The template is [verification overrides](../examples/verification_overrides_template.csv).

Apply completed reviews by rerunning:

```bash
mapq-verify-official \
  work/map_qb_counties/geocoded_qbs.json \
  --overrides work/official_verification/official_overrides.csv \
  --output-dir work/official_verification
```

## Automated controls

The verifier fails or blocks release when:

- the input count differs from the expected 721-player cohort;
- an official roster returns duplicate or incomplete QB identities;
- a player-team key is duplicated;
- one provider player ID is matched to multiple input rows;
- any row remains unresolved or conflicting; or
- a manual `verified` decision lacks a direct HTTPS source, review metadata, QB position, or verified hometown.

Because rosters change, every audit records the roster year, retrieval timestamp, direct source URL, and source-registry review date. A new public release requires a fresh audit rather than silently reusing an old verification result.

## Publication boundary

Verification establishes confidence in the facts; it does not grant redistribution rights to source-site content. Publish the original MAP-Q scores, metric definitions, rankings, charts, city-level aggregates, source registry, and verification counts. Keep page snapshots, complete private roster exports, provider keys, and row-level comparison files private unless the intended publication rights have been reviewed.
