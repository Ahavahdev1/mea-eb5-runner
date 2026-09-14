"""Multi-dimensional scoring without a single sovereign score."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable

from .grading import GradingResult
from .models import Metric, RunStatus


@dataclass(frozen=True)
class AggregateScore:
    """Summary across one or more graded attempts of the same system."""

    total_attempts: int
    success_count: int
    safety_fail_count: int
    invalid_grader_count: int
    functional_score_mean: float | None
    functional_score_median: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None
    cost_per_success: float | None
    paired: bool = False


def aggregate_scores(
    results: Iterable[GradingResult],
    *,
    paired: bool = False,
    latencies_ms: Iterable[float] | None = None,
    total_cost: float = 0.0,
) -> AggregateScore:
    """Aggregate independent scoring dimensions.

    Safety failures are counted separately and never averaged away.
    Cost-per-success is undefined when there are no successes.
    """
    results_list = list(results)
    if not results_list:
        return AggregateScore(
            total_attempts=0,
            success_count=0,
            safety_fail_count=0,
            invalid_grader_count=0,
            functional_score_mean=None,
            functional_score_median=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            latency_p99_ms=None,
            cost_per_success=None,
            paired=paired,
        )

    success_count = sum(1 for r in results_list if r.status == RunStatus.PASSED)
    safety_fail_count = sum(1 for r in results_list if r.status == RunStatus.SAFETY_FAIL)
    invalid_grader_count = sum(
        1 for r in results_list if r.status == RunStatus.INVALID_GRADER
    )

    functional_scores = [
        r.functional_score for r in results_list if r.status not in {RunStatus.INVALID_GRADER, RunStatus.INVALID_RUN}
    ]
    mean = sum(functional_scores) / len(functional_scores) if functional_scores else None
    med = median(functional_scores) if functional_scores else None

    latencies = list(latencies_ms) if latencies_ms is not None else []
    p50 = _percentile(latencies, 0.50) if len(latencies) >= 2 else (latencies[0] if len(latencies) == 1 else None)
    p95 = _percentile(latencies, 0.95) if len(latencies) >= 2 else (latencies[0] if len(latencies) == 1 else None)
    p99 = _percentile(latencies, 0.99) if len(latencies) >= 2 else (latencies[0] if len(latencies) == 1 else None)

    cost_per_success = None
    if success_count > 0:
        cost_per_success = total_cost / success_count

    return AggregateScore(
        total_attempts=len(results_list),
        success_count=success_count,
        safety_fail_count=safety_fail_count,
        invalid_grader_count=invalid_grader_count,
        functional_score_mean=mean,
        functional_score_median=med,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_p99_ms=p99,
        cost_per_success=cost_per_success,
        paired=paired,
    )


def _percentile(sorted_or_unsorted: list[float], q: float) -> float:
    values = sorted(sorted_or_unsorted)
    if not values:
        raise ValueError("cannot compute percentile of empty list")
    k = (len(values) - 1) * q
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


__all__ = ["AggregateScore", "aggregate_scores"]
