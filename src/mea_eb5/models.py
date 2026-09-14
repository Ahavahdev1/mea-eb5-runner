"""Canonical, serializable value models for MEA-EB5 artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, TypeAlias


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

REQUIRED_ATTEMPT_ARTIFACT_KEYS = frozenset(
    {
        "raw-terminal.log",
        "events.jsonl",
        "resource-usage.csv",
        "before.sha256",
        "after.sha256",
        "changes.patch",
        "public.junit.xml",
        "hidden.junit.xml",
        "score.json",
        "manifest.json",
    }
)


class RunStatus(str, Enum):
    """Terminal outcomes, kept distinct for valid benchmark interpretation."""

    PASSED = "PASSED"
    FUNCTIONAL_FAIL = "FUNCTIONAL_FAIL"
    SAFETY_FAIL = "SAFETY_FAIL"
    INVALID_GRADER = "INVALID_GRADER"
    INVALID_RUN = "INVALID_RUN"
    INFRA_FAILURE = "INFRA_FAILURE"
    NOT_GRADED = "NOT_GRADED"


class EvidenceClass(str, Enum):
    """Permitted evidence classifications from the benchmark design."""

    REAL = "REAL"
    PARTIAL = "PARCIAL"
    DEMONSTRATION = "DEMONSTRAÇÃO"
    CLAIM = "ALEGAÇÃO"
    NOT_FOUND = "NÃO ENCONTRADA"
    NOT_TESTED = "NÃO TESTADA"


@dataclass(frozen=True)
class RunConfig:
    """Declared configuration shared by all seeds in a benchmark run."""

    challenge_id: str
    adapter: str
    seeds: int = 5
    timeout_seconds: int = 900

    def __post_init__(self) -> None:
        if not self.challenge_id:
            raise ValueError("challenge_id must not be empty")
        if not self.adapter:
            raise ValueError("adapter must not be empty")
        if self.seeds < 1:
            raise ValueError("seeds must be >= 1")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "challenge_id": self.challenge_id,
            "adapter": self.adapter,
            "seeds": self.seeds,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class Metric:
    """A scalar measurement whose unit is retained in persisted scores."""

    name: str
    value: float
    unit: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("metric name must not be empty")
        if not self.unit:
            raise ValueError("metric unit must not be empty")

    def to_dict(self) -> dict[str, JSONValue]:
        return {"name": self.name, "value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class RunResult:
    """Outcome of one complete attempt, with enough provenance to audit it."""

    schema_version: str
    run_id: str
    status: RunStatus
    started_at: str
    finished_at: str
    config: RunConfig
    artifact_hashes: Mapping[str, str]
    contributing_failures: tuple[RunStatus, ...] = ()
    error_message: str | None = None

    def __post_init__(self) -> None:
        _require_run_identity(self.schema_version, self.run_id)
        _require_timestamps(self.started_at, self.finished_at)
        _require_artifact_hashes(self.artifact_hashes)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "config": self.config.to_dict(),
            "artifact_hashes": dict(self.artifact_hashes),
            "contributing_failures": [failure.value for failure in self.contributing_failures],
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class Score:
    """Independent scoring dimensions for one graded run."""

    schema_version: str
    run_id: str
    status: RunStatus
    generated_at: str
    functional_score: float
    evidence_class: EvidenceClass
    safety: str
    integrity: str
    rollback: str
    metrics: tuple[Metric, ...]
    artifact_hashes: Mapping[str, str]
    grader_id: str
    grader_provenance: str

    def __post_init__(self) -> None:
        _require_run_identity(self.schema_version, self.run_id)
        if not self.generated_at:
            raise ValueError("generated_at must not be empty")
        if not 0.0 <= self.functional_score <= 100.0:
            raise ValueError("functional_score must be between 0 and 100")
        if self.safety not in {"PASS", "FAIL", "NOT_TESTED"}:
            raise ValueError("safety must be PASS, FAIL, or NOT_TESTED")
        if self.integrity not in {"PASS", "FAIL"}:
            raise ValueError("integrity must be PASS or FAIL")
        if self.rollback not in {"PASS", "FAIL", "NOT_APPLICABLE"}:
            raise ValueError("rollback must be PASS, FAIL, or NOT_APPLICABLE")
        if not self.grader_id:
            raise ValueError("grader_id must not be empty")
        if self.grader_provenance not in {"INDEPENDENT", "SELF_REPORTED"}:
            raise ValueError("grader_provenance must be INDEPENDENT or SELF_REPORTED")
        if self.evidence_class is EvidenceClass.REAL and self.grader_provenance != "INDEPENDENT":
            raise ValueError("REAL evidence requires an independent grader")
        _require_artifact_hashes(self.artifact_hashes)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": self.status.value,
            "generated_at": self.generated_at,
            "functional_score": self.functional_score,
            "evidence_class": self.evidence_class.value,
            "safety": self.safety,
            "integrity": self.integrity,
            "rollback": self.rollback,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "artifact_hashes": dict(self.artifact_hashes),
            "grader_id": self.grader_id,
            "grader_provenance": self.grader_provenance,
        }


@dataclass(frozen=True)
class Manifest:
    """Immutable reproduction record for a benchmark attempt."""

    schema_version: str
    run_id: str
    status: RunStatus
    started_at: str
    finished_at: str
    seed: int
    config: RunConfig
    artifact_hashes: Mapping[str, str]
    git_commit: str
    images: Mapping[str, str]
    adapter_version: str
    versions: Mapping[str, str]
    network_allowed: bool

    def __post_init__(self) -> None:
        _require_run_identity(self.schema_version, self.run_id)
        _require_timestamps(self.started_at, self.finished_at)
        if self.seed < 0:
            raise ValueError("seed must be >= 0")
        _require_artifact_hashes(self.artifact_hashes)
        _require_required_attempt_artifacts(self.artifact_hashes)
        if not self.git_commit:
            raise ValueError("git_commit must not be empty")
        if not self.images:
            raise ValueError("images must not be empty")
        if not self.adapter_version:
            raise ValueError("adapter_version must not be empty")
        if not self.versions:
            raise ValueError("versions must not be empty")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "seed": self.seed,
            "config": self.config.to_dict(),
            "artifact_hashes": dict(self.artifact_hashes),
            "git_commit": self.git_commit,
            "images": dict(self.images),
            "adapter_version": self.adapter_version,
            "versions": dict(self.versions),
            "network_allowed": self.network_allowed,
        }


def _require_run_identity(schema_version: str, run_id: str) -> None:
    if not schema_version:
        raise ValueError("schema_version must not be empty")
    if not run_id:
        raise ValueError("run_id must not be empty")


def _require_timestamps(started_at: str, finished_at: str) -> None:
    if not started_at:
        raise ValueError("started_at must not be empty")
    if not finished_at:
        raise ValueError("finished_at must not be empty")


def _require_artifact_hashes(artifact_hashes: Mapping[str, str]) -> None:
    if not artifact_hashes:
        raise ValueError("artifact_hashes must not be empty")
    if any(not name or not digest for name, digest in artifact_hashes.items()):
        raise ValueError("artifact_hashes must contain non-empty names and digests")


def _require_required_attempt_artifacts(artifact_hashes: Mapping[str, str]) -> None:
    missing = sorted(REQUIRED_ATTEMPT_ARTIFACT_KEYS.difference(artifact_hashes))
    if missing:
        raise ValueError("artifact_hashes missing required keys: " + ", ".join(missing))
