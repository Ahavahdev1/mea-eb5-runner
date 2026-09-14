"""Deterministic negative control that intentionally takes no action."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..events import EventSink
from .base import AdapterDescription, AdapterExecution, TaskRequest


class NoopAdapter:
    """A control adapter whose run path neither writes nor emits events."""

    def describe(self) -> AdapterDescription:
        return AdapterDescription(name="noop", version="1.0", transport="local")

    def prepare(self, config: Mapping[str, object]) -> None:
        del config

    def run(
        self, task: TaskRequest, workspace: Path, event_sink: EventSink
    ) -> AdapterExecution:
        del task, workspace, event_sink
        return AdapterExecution(succeeded=True, exit_code=0)

    def cancel(self, reason: str) -> None:
        del reason
