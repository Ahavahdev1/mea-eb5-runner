"""Independent grader execution with negative controls."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from .models import Metric, RunStatus


class Grader(Protocol):
    """Independent evaluator of one solution artifact."""

    def grader_id(self) -> str: ...

    def validate_controls(self) -> bool: ...

    def grade(self, solution: Path, task_id: str) -> "GradingResult": ...


@dataclass(frozen=True)
class ControlCase:
    """One negative or positive control for grader validation."""

    name: str
    solution: Path
    expected_status: RunStatus
    description: str = ""


@dataclass(frozen=True)
class GraderControlResult:
    """Outcome of running a grader against its control cases."""

    valid: bool
    grader_id: str
    failures: tuple[str, ...]


@dataclass(frozen=True)
class GradingResult:
    """Outcome returned by a validated grader for one real attempt."""

    status: RunStatus
    functional_score: float = 0.0
    safety: str = "PASS"
    integrity: str = "PASS"
    rollback: str = "NOT_APPLICABLE"
    grader_id: str = "unknown"
    metrics: tuple[Metric, ...] = ()


def validate_grader(grader: Grader, controls: Mapping[str, ControlCase]) -> GraderControlResult:
    """Run controls and reject graders that pass cases that should fail.

    A grader is INVALID when:
    - any control expected to fail is graded as PASSED;
    - any oracle control expected to pass is graded as failed;
    - the grader raises an exception during a control.
    """
    failures: list[str] = []

    for name, control in controls.items():
        try:
            result = grader.grade(control.solution, f"control-{name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: exception ({exc})")
            continue

        if control.expected_status == RunStatus.PASSED:
            if result.status != RunStatus.PASSED:
                failures.append(
                    f"{name}: oracle expected PASSED but got {result.status.value}"
                )
        else:
            if result.status == RunStatus.PASSED:
                failures.append(
                    f"{name}: expected {control.expected_status.value} but grader PASSED"
                )

    return GraderControlResult(
        valid=len(failures) == 0,
        grader_id=grader.grader_id(),
        failures=tuple(failures),
    )


__all__ = [
    "ControlCase",
    "Grader",
    "GraderControlResult",
    "GradingResult",
    "validate_grader",
]
