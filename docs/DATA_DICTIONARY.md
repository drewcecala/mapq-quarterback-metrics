# Data dictionary

The scorer accepts a JSON array, a JSON object with a `records` array, or a CSV file. Unknown columns pass through unchanged. Count fields must be nonnegative whole numbers.

## Required identity fields

| Field | Type | Definition |
|---|---|---|
| `player_id` | string | Unique identifier within the input cohort |
| `player_name` | string | Display name used for deterministic tie-breaking |
| `stats_season` | integer or null | Selected production season; supported values are 2023–2026 |

## Official-season inputs

| Field | Type | Definition |
|---|---|---|
| `pass_attempts` | integer | Official passing attempts |
| `completions` | integer | Official pass completions |
| `pass_yards` | integer | Official passing yards; may be negative |
| `interceptions` | integer | Interceptions thrown |
| `long_pass` | integer | Longest completed pass in yards |
| `sacks` | integer or null | Sacks taken under the source's accounting. A null value makes MAP-Q ineligible unless complete play-by-play coverage can supply it. |
| `rush_attempts` | integer | Official quarterback rush attempts |
| `rush_yards` | integer | Official quarterback rushing yards; may be negative |
| `long_rush` | integer | Longest quarterback rush in yards |

## Play-level aggregate inputs

These fields may be zero when play-level data are unavailable. The corresponding advanced metrics will remain null.

| Field | Type | Definition |
|---|---|---|
| `pbp_pass_attempts` | integer | Pass attempts identified in play-level data |
| `pbp_qb_rushes` | integer | Quarterback rushes identified in play-level data |
| `pbp_sacks` | integer | Sacks identified in play-level data |
| `pbp_explosive_plays` | integer | Completed passes or QB rushes gaining at least 15 yards |
| `pbp_third_down_qb_plays` | integer | Third-down attempts, QB rushes, and sacks |
| `pbp_third_down_dropbacks` | integer | Third-down pass attempts plus sacks |
| `pbp_third_down_conversions` | integer | Completed passes or QB rushes reaching the line to gain or scoring |
| `pbp_third_down_tds` | integer | Third-down passing or QB-rushing touchdowns |
| `pbp_third_down_sacks` | integer | Sacks taken on third down |
| `pbp_escape_opportunities` | integer | Estimated escape opportunities under the published proxy |
| `pbp_escape_explosives` | integer | Estimated opportunities becoming a first down, touchdown, or 15-plus-yard rush |

`pbp_qb_plays` is computed as play-level pass attempts plus QB rushes plus sacks. `offensive_opportunities` is computed as official pass attempts plus official rush attempts.

## Principal outputs

| Field | Scale | Definition |
|---|---:|---|
| `mapq` | 0–100 | Reliability-adjusted headline score |
| `mapq_rank` | integer | Competition rank among scored players |
| `passing_capability` | 0–100 | Accuracy and arm-proxy blend |
| `movement_capability` | 0–100 | Mobility and sack-avoidance blend |
| `reliability` | 0–1 | Sample-size and recency weight |
| `defense_stress_index` | 0–100 or null | Reliability-adjusted field-stress score |
| `drive_extension_index` | 0–100 or null | Third-down conversion/TD/sack-avoidance score |
| `escape_to_explosive_rate_proxy` | 0–1 or null | Successful estimated escapes divided by opportunities |
| `data_status` | text | Qualified, provisional, insufficient sample, missing sack data, or no college stats |
| `advanced_data_status` | text | Which advanced metrics meet coverage and sample gates |

The engine also returns all intermediate rates, percentiles, component scores, and ranks needed to audit the final values.
