# Public release artifacts

This directory is reserved for sanitized, derived-only MAP-Q releases. A release may include player and team names as report context, model scores, ranks, tiers, reliability, metric definitions, retrieval date, model version, and the attribution “Data provided by CollegeFootballData.com.”

Do not place official statistical totals, source-system identifiers, raw or normalized API responses, play-by-play rows, API caches, or credentials here. Build those materials only in ignored private directories, then run `mapq-release` and `python tools/release_check.py` before staging an artifact.
