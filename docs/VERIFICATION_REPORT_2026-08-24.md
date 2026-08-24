# 2026 FBS quarterback roster verification report

Verification date: 2026-08-24
Roster season: 2026

## Result

The no-key verifier parsed all 138 official athletics roster pages in the tracked [source registry](../sources/official_rosters_2026.csv) and built a complete current cohort of 719 quarterbacks. Every canonical row contains player name, current team, QB position, hometown, direct official source URL, and retrieval timestamp.

The prior private 721-row comparison file is not the same cohort:

| Check | Count |
|---|---:|
| Official team rosters parsed | 138 of 138 |
| Canonical official QBs | 719 |
| Canonical QBs with hometown | 719 |
| Prior rows matched to an official QB | 701 |
| Prior rows absent from the official current roster | 20 |
| Official current QBs absent from the prior file | 18 |
| Exact name/team/position/hometown agreements | 687 |
| Hometown disagreements requiring correction | 13 |
| Name variation requiring review | 1 |

The canonical-roster quality gate passed. The old 721-row cohort gate did not, which is the expected signal that downstream workbooks and metrics must be rebuilt against the 719-row current roster.

## Evidence and controls

- Each team has one direct official roster URL, including [Air Force](https://goairforcefalcons.com/sports/football/roster), [Jacksonville State](https://jaxstatesports.com/sports/football/roster), [Stanford](https://gostanford.com/sports/football/roster), and [Syracuse](https://cuse.com/sports/football/roster?sort=position).
- The fetcher checks `robots.txt`, uses bounded presentation fallbacks, and never bypasses a disallow rule.
- Pages must identify the requested season and expose a unique player name, QB position, and hometown.
- Common table, list/card, and structured roster presentations are parsed and normalized.
- Page snapshots, official player keys, the canonical row-level roster, and reconciliation details remain in ignored private storage.
- Public release artifacts contain original scores and aggregate reporting, not copied page content or a raw official-site mirror.

## Interpretation

This audit verifies the point-in-time current roster facts used to construct the cohort. It does not verify statistical production fields, grant redistribution rights to source-site content, or guarantee that a roster will remain unchanged after the retrieval date. Re-run the audit before each release and review every reconciliation change before joining historical statistics or publishing updated scores.
