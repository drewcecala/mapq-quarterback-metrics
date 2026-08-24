"""Reference implementation of MAP-Q and its advanced quarterback metrics."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Iterable, Mapping

MODEL_VERSION = "1.1.1"


@dataclass(frozen=True)
class ModelConfig:
    score_min_pass_attempts: int = 20
    score_min_offensive_opportunities: int = 40
    benchmark_min_pass_attempts: int = 100
    benchmark_min_offensive_opportunities: int = 125
    full_reliability_pass_attempts: int = 250
    full_reliability_offensive_opportunities: int = 300
    season_weights: tuple[tuple[int, float], ...] = (
        (2026, 1.00),
        (2025, 0.85),
        (2024, 0.70),
        (2023, 0.55),
    )
    pbp_coverage_min: float = 0.85
    pbp_coverage_max: float = 1.15
    dsi_min_qb_plays: int = 40
    dei_min_third_down_qb_plays: int = 15
    dei_min_third_down_dropbacks: int = 8
    eer_min_escape_opportunities: int = 8


DEFAULT_CONFIG = ModelConfig()

_COUNT_FIELDS = (
    "pass_attempts",
    "completions",
    "interceptions",
    "long_pass",
    "rush_attempts",
    "long_rush",
    "pbp_pass_attempts",
    "pbp_qb_rushes",
    "pbp_sacks",
    "pbp_explosive_plays",
    "pbp_third_down_qb_plays",
    "pbp_third_down_dropbacks",
    "pbp_third_down_conversions",
    "pbp_third_down_tds",
    "pbp_third_down_sacks",
    "pbp_escape_opportunities",
    "pbp_escape_explosives",
)
_OPTIONAL_COUNT_FIELDS = ("sacks",)
_YARD_FIELDS = ("pass_yards", "rush_yards")
_BASE_PERCENTILE_METRICS = {
    "completion_percentile": "completion_rate",
    "interception_avoidance_percentile": "interception_avoidance",
    "yards_per_attempt_percentile": "yards_per_attempt",
    "yards_per_completion_percentile": "yards_per_completion",
    "long_pass_percentile": "long_pass",
    "sack_avoidance_percentile": "sack_avoidance",
    "rush_yards_per_opportunity_percentile": "rush_yards_per_opportunity",
    "non_sack_rush_share_percentile": "non_sack_rush_share",
    "long_rush_percentile": "long_rush",
}


def _as_int(record: Mapping[str, Any], field: str) -> int:
    value = record.get(field, 0)
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a whole number, not a boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric; received {value!r}") from exc
    if not number.is_integer():
        raise ValueError(f"{field} must be a whole number; received {value!r}")
    return int(number)


def _rate(numerator: float, denominator: float, *, zero_value: float | None = None) -> float | None:
    if denominator == 0:
        return zero_value
    return numerator / denominator


def _midrank(value: float, cohort: list[float]) -> float:
    if not cohort:
        raise ValueError("cannot calculate a percentile from an empty cohort")
    below = sum(candidate < value for candidate in cohort)
    equal = sum(candidate == value for candidate in cohort)
    return (below + 0.5 * equal) / len(cohort)


def _is_scoreable(row: Mapping[str, Any], config: ModelConfig) -> bool:
    return (
        row["pass_attempts"] >= config.score_min_pass_attempts
        and row["offensive_opportunities"] >= config.score_min_offensive_opportunities
        and row["stats_season"] is not None
        and row["sacks"] is not None
    )


def _is_benchmark(row: Mapping[str, Any], config: ModelConfig) -> bool:
    return (
        row["pass_attempts"] >= config.benchmark_min_pass_attempts
        and row["offensive_opportunities"] >= config.benchmark_min_offensive_opportunities
        and row["stats_season"] is not None
        and row["sacks"] is not None
    )


def _coverage_ok(row: Mapping[str, Any], config: ModelConfig) -> bool:
    coverage = row["pbp_coverage"]
    return (
        coverage is not None
        and config.pbp_coverage_min <= coverage <= config.pbp_coverage_max
    )


def _prepare_record(record: Mapping[str, Any], config: ModelConfig) -> dict[str, Any]:
    row = dict(record)
    player_id = str(row.get("player_id", "")).strip()
    player_name = str(row.get("player_name", "")).strip()
    if not player_id or not player_name:
        raise ValueError("each record requires nonblank player_id and player_name")
    row["player_id"] = player_id
    row["player_name"] = player_name

    season_value = row.get("stats_season")
    if season_value in (None, ""):
        season = None
    else:
        season = _as_int({"stats_season": season_value}, "stats_season")
        supported = dict(config.season_weights)
        if season not in supported:
            raise ValueError(
                f"{player_name}: stats_season {season} is unsupported; "
                f"expected one of {sorted(supported)} or null"
            )
    row["stats_season"] = season

    for field in _COUNT_FIELDS + _YARD_FIELDS:
        row[field] = _as_int(row, field)
    for field in _OPTIONAL_COUNT_FIELDS:
        value = row.get(field)
        row[field] = None if value in (None, "") else _as_int(row, field)
    for field in _COUNT_FIELDS:
        if row[field] < 0:
            raise ValueError(f"{player_name}: {field} cannot be negative")
    for field in _OPTIONAL_COUNT_FIELDS:
        if row[field] is not None and row[field] < 0:
            raise ValueError(f"{player_name}: {field} cannot be negative")

    if row["completions"] > row["pass_attempts"]:
        raise ValueError(f"{player_name}: completions exceed pass attempts")
    if row["interceptions"] > row["pass_attempts"]:
        raise ValueError(f"{player_name}: interceptions exceed pass attempts")
    if row["pbp_third_down_conversions"] > row["pbp_third_down_qb_plays"]:
        raise ValueError(f"{player_name}: third-down conversions exceed QB plays")
    if row["pbp_third_down_tds"] > row["pbp_third_down_qb_plays"]:
        raise ValueError(f"{player_name}: third-down touchdowns exceed QB plays")
    if row["pbp_third_down_sacks"] > row["pbp_third_down_dropbacks"]:
        raise ValueError(f"{player_name}: third-down sacks exceed dropbacks")
    if row["pbp_escape_explosives"] > row["pbp_escape_opportunities"]:
        raise ValueError(f"{player_name}: escape successes exceed opportunities")

    row["offensive_opportunities"] = row["pass_attempts"] + row["rush_attempts"]
    row["pbp_qb_plays"] = (
        row["pbp_pass_attempts"] + row["pbp_qb_rushes"] + row["pbp_sacks"]
    )
    if row["pbp_explosive_plays"] > row["pbp_qb_plays"]:
        raise ValueError(f"{player_name}: explosive plays exceed PBP QB plays")

    row["completion_rate"] = _rate(row["completions"], row["pass_attempts"], zero_value=0.0)
    row["interception_avoidance"] = 1.0 - _rate(
        row["interceptions"], row["pass_attempts"], zero_value=0.0
    )
    row["yards_per_attempt"] = _rate(row["pass_yards"], row["pass_attempts"], zero_value=0.0)
    row["yards_per_completion"] = _rate(
        row["pass_yards"], row["completions"], zero_value=0.0
    )
    row["sack_avoidance"] = (
        None
        if row["sacks"] is None
        else 1.0
        - _rate(
            row["sacks"], row["pass_attempts"] + row["sacks"], zero_value=0.0
        )
    )
    row["non_sack_rush_attempts"] = (
        None
        if row["sacks"] is None
        else max(0, row["rush_attempts"] - row["sacks"])
    )
    row["rush_yards_per_opportunity"] = _rate(
        row["rush_yards"], row["offensive_opportunities"], zero_value=0.0
    )
    row["non_sack_rush_share"] = (
        None
        if row["non_sack_rush_attempts"] is None
        else _rate(
            row["non_sack_rush_attempts"],
            row["offensive_opportunities"],
            zero_value=0.0,
        )
    )

    row["pbp_coverage"] = _rate(row["pbp_pass_attempts"], row["pass_attempts"])
    row["explosive_play_rate"] = _rate(
        row["pbp_explosive_plays"], row["pbp_qb_plays"]
    )
    row["third_down_conversion_rate"] = _rate(
        row["pbp_third_down_conversions"], row["pbp_third_down_qb_plays"]
    )
    row["third_down_td_rate"] = _rate(
        row["pbp_third_down_tds"], row["pbp_third_down_qb_plays"]
    )
    row["third_down_sack_avoidance"] = (
        None
        if row["pbp_third_down_dropbacks"] == 0
        else 1.0
        - row["pbp_third_down_sacks"] / row["pbp_third_down_dropbacks"]
    )
    return row


def _assign_rank(
    rows: list[dict[str, Any]], field: str, output_field: str, *, alphabetical_ties: bool
) -> None:
    eligible = [row for row in rows if row.get(field) is not None]
    if alphabetical_ties:
        ordered = sorted(eligible, key=lambda row: (-row[field], row["player_name"].casefold()))
        for rank, row in enumerate(ordered, start=1):
            row[output_field] = rank
    else:
        values = [row[field] for row in eligible]
        for row in eligible:
            row[output_field] = 1 + sum(value > row[field] for value in values)
    for row in rows:
        row.setdefault(output_field, None)


def score_records(
    records: Iterable[Mapping[str, Any]], config: ModelConfig = DEFAULT_CONFIG
) -> list[dict[str, Any]]:
    """Score an entire quarterback cohort and return auditable enriched records.

    Percentiles are cohort-relative, so callers must pass the full comparison
    population in one call. Input order does not affect scores or ranks.
    """

    rows = [_prepare_record(record, config) for record in records]
    if not rows:
        raise ValueError("at least one quarterback record is required")
    ids = [row["player_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("player_id values must be unique within the cohort")

    benchmark = [row for row in rows if _is_benchmark(row, config)]
    scoreable = [row for row in rows if _is_scoreable(row, config)]
    current_season = max(dict(config.season_weights))
    if scoreable and not benchmark:
        raise ValueError("scoreable players exist but the stable benchmark cohort is empty")

    for row in rows:
        if not _is_scoreable(row, config):
            for output_field in _BASE_PERCENTILE_METRICS:
                row[output_field] = None
            continue
        for output_field, metric_field in _BASE_PERCENTILE_METRICS.items():
            cohort_values = [candidate[metric_field] for candidate in benchmark]
            row[output_field] = _midrank(row[metric_field], cohort_values)

        row["accuracy_score"] = 100 * (
            0.75 * row["completion_percentile"]
            + 0.25 * row["interception_avoidance_percentile"]
        )
        row["arm_proxy_score"] = 100 * (
            0.45 * row["yards_per_attempt_percentile"]
            + 0.35 * row["yards_per_completion_percentile"]
            + 0.20 * row["long_pass_percentile"]
        )
        row["mobility_score"] = 100 * (
            0.50 * row["rush_yards_per_opportunity_percentile"]
            + 0.30 * row["non_sack_rush_share_percentile"]
            + 0.20 * row["long_rush_percentile"]
        )
        row["escape_score"] = 100 * row["sack_avoidance_percentile"]
        row["passing_capability"] = (
            0.60 * row["accuracy_score"] + 0.40 * row["arm_proxy_score"]
        )
        row["movement_capability"] = (
            0.60 * row["mobility_score"] + 0.40 * row["escape_score"]
        )
        row["raw_mapq"] = 100 * (row["passing_capability"] / 100) ** 0.60 * (
            row["movement_capability"] / 100
        ) ** 0.40
        season_weight = dict(config.season_weights)[row["stats_season"]]
        row["reliability"] = min(
            1.0,
            sqrt(
                min(
                    row["pass_attempts"] / config.full_reliability_pass_attempts,
                    row["offensive_opportunities"]
                    / config.full_reliability_offensive_opportunities,
                )
            ),
        ) * season_weight
        row["mapq"] = 50 + (row["raw_mapq"] - 50) * row["reliability"]

    for row in rows:
        if row.get("mapq") is None:
            row["tier"] = "Unscored"
            row["data_status"] = (
                "No college stats"
                if row["stats_season"] is None
                else "Missing sack data"
                if row["sacks"] is None
                else "Insufficient sample"
            )
        else:
            score = row["mapq"]
            row["tier"] = (
                "Elite"
                if score >= 80
                else "Impact"
                if score >= 70
                else "Starter"
                if score >= 60
                else "Developmental"
                if score >= 45
                else "Limited production"
            )
            if _is_benchmark(row, config):
                row["data_status"] = (
                    "Qualified"
                    if row["stats_season"] == current_season
                    else "Qualified - older season"
                )
            else:
                row["data_status"] = "Provisional"

    _assign_rank(rows, "mapq", "mapq_rank", alphabetical_ties=False)

    dsi_benchmark = [
        row
        for row in benchmark
        if _coverage_ok(row, config) and row["pbp_qb_plays"] >= config.dsi_min_qb_plays
    ]
    dsi_candidates = [
        row
        for row in scoreable
        if _coverage_ok(row, config) and row["pbp_qb_plays"] >= config.dsi_min_qb_plays
    ]
    dsi_rates = [row["explosive_play_rate"] for row in dsi_benchmark]
    if dsi_candidates and not dsi_rates:
        raise ValueError("DSI-eligible players exist but the stable DSI benchmark is empty")
    for row in rows:
        row["explosive_play_rate_percentile"] = None
        row["deep_ball_ability"] = None
        row["scramble_threat"] = None
        row["raw_defense_stress_index"] = None
        row["defense_stress_index"] = None
    for row in dsi_candidates:
        row["explosive_play_rate_percentile"] = _midrank(
            row["explosive_play_rate"], dsi_rates
        )
        row["deep_ball_ability"] = 100 * (
            0.60 * row["yards_per_completion_percentile"]
            + 0.40 * row["long_pass_percentile"]
        )
        row["scramble_threat"] = 100 * (
            0.60 * row["rush_yards_per_opportunity_percentile"]
            + 0.40 * row["sack_avoidance_percentile"]
        )
        row["raw_defense_stress_index"] = (
            0.30 * row["deep_ball_ability"]
            + 0.25 * row["scramble_threat"]
            + 0.20 * 100 * row["non_sack_rush_share_percentile"]
            + 0.25 * 100 * row["explosive_play_rate_percentile"]
        )
        row["defense_stress_index"] = 50 + (
            row["raw_defense_stress_index"] - 50
        ) * row["reliability"]

    dei_candidates = [
        row
        for row in scoreable
        if _coverage_ok(row, config)
        and row["pbp_third_down_qb_plays"] >= config.dei_min_third_down_qb_plays
        and row["pbp_third_down_dropbacks"] >= config.dei_min_third_down_dropbacks
    ]
    for row in rows:
        row["third_down_conversion_percentile"] = None
        row["third_down_td_rate_percentile"] = None
        row["third_down_sack_avoidance_percentile"] = None
        row["drive_extension_index"] = None
    if dei_candidates:
        conversion_rates = [row["third_down_conversion_rate"] for row in dei_candidates]
        td_rates = [row["third_down_td_rate"] for row in dei_candidates]
        sack_avoidance_rates = [row["third_down_sack_avoidance"] for row in dei_candidates]
        for row in dei_candidates:
            row["third_down_conversion_percentile"] = _midrank(
                row["third_down_conversion_rate"], conversion_rates
            )
            row["third_down_td_rate_percentile"] = _midrank(
                row["third_down_td_rate"], td_rates
            )
            row["third_down_sack_avoidance_percentile"] = _midrank(
                row["third_down_sack_avoidance"], sack_avoidance_rates
            )
            row["drive_extension_index"] = 100 * (
                0.70 * row["third_down_conversion_percentile"]
                + 0.20 * row["third_down_td_rate_percentile"]
                + 0.10 * row["third_down_sack_avoidance_percentile"]
            )

    for row in rows:
        row["escape_to_explosive_rate_proxy"] = (
            row["pbp_escape_explosives"] / row["pbp_escape_opportunities"]
            if _is_scoreable(row, config)
            and _coverage_ok(row, config)
            and row["pbp_escape_opportunities"] >= config.eer_min_escape_opportunities
            else None
        )
        if row.get("mapq") is None:
            row["advanced_data_status"] = "Unscored"
        elif row["defense_stress_index"] is None:
            row["advanced_data_status"] = "PBP coverage/sample gap"
        elif row["drive_extension_index"] is not None and row["escape_to_explosive_rate_proxy"] is not None:
            row["advanced_data_status"] = "All three metrics"
        elif row["drive_extension_index"] is not None:
            row["advanced_data_status"] = "DSI + DEI"
        elif row["escape_to_explosive_rate_proxy"] is not None:
            row["advanced_data_status"] = "DSI + EER proxy"
        else:
            row["advanced_data_status"] = "DSI only"

    _assign_rank(rows, "defense_stress_index", "dsi_rank", alphabetical_ties=True)
    _assign_rank(rows, "drive_extension_index", "dei_rank", alphabetical_ties=True)
    _assign_rank(
        rows,
        "escape_to_explosive_rate_proxy",
        "eer_proxy_rank",
        alphabetical_ties=True,
    )
    return rows
