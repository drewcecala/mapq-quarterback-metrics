# MAP-Q methodology

Model version: **1.1.1**

## Cohorts and eligibility

The engine expects one selected season per quarterback.

| Rule | Threshold |
|---|---:|
| Minimum sample to score | 20 pass attempts and 40 offensive opportunities |
| Stable benchmark cohort | 100 pass attempts and 125 offensive opportunities |
| Full-reliability anchors | 250 pass attempts and 300 offensive opportunities |
| Supported seasons | 2023, 2024, 2025, 2026 |
| Season weights | 2026: 1.00; 2025: 0.85; 2024: 0.70; 2023: 0.55 |

Offensive opportunities are pass attempts plus official quarterback rush attempts. A scored player may fall below the benchmark threshold; that player's percentiles are still measured against the stable benchmark cohort and the final score is pulled toward 50.

Every percentile is a midrank percentile:

```text
(count below the player + 0.5 × count equal to the player) / cohort size
```

This gives tied values the same placement and avoids assigning an exact zero or one in finite cohorts.

## Base rates

```text
Completion Rate          = Completions / Pass Attempts
Interception Avoidance   = 1 − Interceptions / Pass Attempts
Yards per Attempt        = Pass Yards / Pass Attempts
Yards per Completion     = Pass Yards / Completions
Sack Avoidance           = 1 − Sacks / (Pass Attempts + Sacks)
Non-sack Rush Attempts   = max(0, Rush Attempts − Sacks)
Net Rush Yards per Opp   = Rush Yards / Offensive Opportunities
Non-sack Rush Share      = Non-sack Rush Attempts / Offensive Opportunities
```

The model converts the following values to percentiles against the stable benchmark cohort: completion rate, interception avoidance, yards per attempt, yards per completion, long pass, sack avoidance, net rush yards per opportunity, non-sack rush share, and long rush.

## Component scores

```text
Accuracy = 75% Completion Rate percentile
         + 25% Interception Avoidance percentile

Arm Proxy = 45% Yards per Attempt percentile
          + 35% Yards per Completion percentile
          + 20% Long Pass percentile

Mobility = 50% Net Rush Yards per Opportunity percentile
         + 30% Non-sack Rush Share percentile
         + 20% Long Rush percentile

Escape = 100% Sack Avoidance percentile

Passing Capability  = 60% Accuracy + 40% Arm Proxy
Movement Capability = 60% Mobility + 40% Escape
```

The arm score is deliberately named a proxy. It measures realized vertical production and therefore includes the effects of scheme, protection, receiver separation, and yards after catch. It does not measure throwing velocity.

## MAP-Q

```text
Raw MAP-Q = 100 × (Passing Capability / 100)^0.60
                × (Movement Capability / 100)^0.40

Reliability = min(1, sqrt(min(Pass Attempts / 250,
                              Offensive Opportunities / 300)))
              × Season Weight

MAP-Q = 50 + (Raw MAP-Q − 50) × Reliability
```

Suggested descriptive bands are Elite (80+), Impact (70–79.9), Starter (60–69.9), Developmental (45–59.9), and Limited production (below 45). These are labels for the index, not depth-chart or draft projections.

## Defense Stress Index

**Definition:** a 0–100 score estimating how much of the field a quarterback's observed production forces a defense to protect.

Eligibility requires a MAP-Q score, play-level pass-attempt coverage between 85% and 115% of official attempts, and at least 40 play-level quarterback plays. The explosive-play percentile uses stable-benchmark quarterbacks who meet the same coverage and play thresholds.

```text
Explosive Play Rate = 15+ yard completed passes and QB rushes / PBP QB Plays

Deep-Ball Ability = 60% Yards per Completion percentile
                  + 40% Long Pass percentile

Scramble Threat = 60% Net Rush Yards per Opportunity percentile
                + 40% Sack Avoidance percentile

Raw DSI = 30% Deep-Ball Ability
        + 25% Scramble Threat
        + 20% Non-sack Rush Share percentile
        + 25% Explosive Play Rate percentile

DSI = 50 + (Raw DSI − 50) × Reliability
```

DSI uses production proxies. It is not a direct measurement of arm strength, defensive spacing, or coverage rules.

## Drive Extension Index

**Definition:** a 0–100 score for first downs and touchdowns created on third down through completed passes or quarterback rushes, with credit for avoiding sacks.

Eligibility requires a MAP-Q score, 85%–115% play-level pass-attempt coverage, at least 15 third-down quarterback plays, and at least eight third-down dropbacks. The comparison cohort is all players meeting those gates.

```text
Third-Down Conversion Rate = Conversions / Third-Down QB Plays
Third-Down TD Rate         = Touchdowns / Third-Down QB Plays
Third-Down Sack Avoidance  = 1 − Sacks / Third-Down Dropbacks

DEI = 70% Conversion Rate percentile
    + 20% TD Rate percentile
    + 10% Sack Avoidance percentile
```

A conversion requires a completed pass or quarterback rush that reaches the line to gain or scores. Penalty-only first downs are not credited to the quarterback.

## Escape-to-Explosive Rate proxy

**Definition:** the share of estimated long-yardage escape opportunities that become a first down, touchdown, or 15-plus-yard quarterback rush.

```text
Estimated Escape Opportunities = sacks
                               + QB rushes on downs 2–4 with 5+ yards to go

EER Proxy = Successful Estimated Escapes / Estimated Escape Opportunities
```

Eligibility requires a MAP-Q score, 85%–115% play-level pass-attempt coverage, and at least eight estimated escape opportunities.

This is not a true pressure-to-explosive rate. It cannot identify every pressure, distinguish designed runs from scrambles, or capture escapes that end in a pass. Use charted pressure and scramble data when available.

## Ranking and missing data

- MAP-Q uses competition ranking: one plus the number of higher scores.
- DSI, DEI, and EER use deterministic ordinal ranking; exact ties break alphabetically by player name.
- Ineligible metrics are null, never zero.
- “Unscored” means insufficient information, not poor performance.

## Validation expectations

A publishable analysis should disclose the cohort, selected-season rule, source rights, retrieval date, eligible count for every metric, missing-data rate, and any modification to these weights or thresholds. Scores should be recomputed as a cohort; appending one player can change every percentile.
