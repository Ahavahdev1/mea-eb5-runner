"""Stable, persisted-safe boundary for systems being benchmarked."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from ..events import EventSink
from ..models import JSONValue


@dataclass(frozen=True)
class TaskRequest:
    """The complete repair input shared with every adapter transport."""

    task_id: str
    filename: str
    code: str
    instruction: str
    test_cmd: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id must not be empty")
        if not self.filename:
            raise ValueError("filename must not be empty")
        if not self.instruction:
            raise ValueError("instruction must not be empty")
        if self.test_cmd is not None and not self.test_cmd:
            raise ValueError("test_cmd must not be empty when provided")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "code": self.code,
            "instruction": self.instruction,
            "test_cmd": self.test_cmd,
        }


@dataclass(frozen=True)
class AdapterDescription:
    """A serializable declaration of one adapter implementation."""

    name: str
    version: str
    transport: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("adapter name must not be empty")
        if not self.version:
            raise ValueError("adapter version must not be empty")
        if not self.transport:
            raise ValueError("adapter transport must not be empty")

    def to_dict(self) -> dict[str, JSONValue]:
        return {"name": self.name, "version": self.version, "transport": self.transport}


@dataclass(frozen=True)
class AdapterExecution:
    """A bounded outcome that can be persisted without agent-provided payloads."""

    succeeded: bool
    exit_code: int | None
    timed_out: bool = False
    error_kind: str | None = None
    response_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.timed_out and self.succeeded:
            raise ValueError("a timed-out execution cannot succeed")
        if self.response_bytes is not None and self.response_bytes < 0:
            raise ValueError("response_bytes must be >= 0")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "succeeded": self.succeeded,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "error_kind": self.error_kind,
            "response_bytes": self.response_bytes,
        }


class AgentAdapter(Protocol):
    """Transport boundary owned by the benchmark runner, not the evaluated agent."""

    def describe(self) -> AdapterDescription: ...

    def prepare(self, config: Mapping[str, object]) -> None: ...

    def run(
        self, task: TaskRequest, workspace: Path, event_sink: EventSink
    ) -> AdapterExecution: ...

    def cancel(self, reason: str) -> None: ...
