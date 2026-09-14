"""Safe subprocess adapter for command-line agent implementations."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
from typing import Mapping

from ..events import EventSink
from .base import AdapterDescription, AdapterExecution, TaskRequest


class CliAdapter:
    """Run a fixed argv command and give it the goal only through a file."""

    def __init__(self, command: list[str], timeout_seconds: float = 900) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must be a non-empty list of non-empty strings")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._command = tuple(command)
        self._timeout_seconds = timeout_seconds
        self._process: subprocess.Popen[bytes] | None = None

    def describe(self) -> AdapterDescription:
        return AdapterDescription(name="cli", version="1.0", transport="cli")

    def prepare(self, config: Mapping[str, object]) -> None:
        del config

    def run(
        self, task: TaskRequest, workspace: Path, event_sink: EventSink
    ) -> AdapterExecution:
        workspace.mkdir(parents=True, exist_ok=True)
        goal_path = workspace / ".mea-eb5-goal.txt"
        goal_path.write_text(task.instruction, encoding="utf-8")
        terminal_path = workspace / "raw-terminal.log"

        try:
            with terminal_path.open("wb") as terminal:
                process = subprocess.Popen(
                    [*self._command, "--goal-file", str(goal_path)],
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=terminal,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                self._process = process
                try:
                    exit_code = process.wait(timeout=self._timeout_seconds)
                except subprocess.TimeoutExpired:
                    self._terminate_process_group(process)
                    result = AdapterExecution(
                        succeeded=False,
                        exit_code=None,
                        timed_out=True,
                        error_kind="timeout",
                    )
                else:
                    result = AdapterExecution(
                        succeeded=exit_code == 0,
                        exit_code=exit_code,
                        error_kind=None if exit_code == 0 else "process_exit",
                    )
        except OSError:
            result = AdapterExecution(succeeded=False, exit_code=None, error_kind="launch_error")
        finally:
            self._process = None

        event_sink.emit(
            "adapter_execution_finished",
            {"adapter": "cli", **result.to_dict()},
            "collector",
            task_id=task.task_id,
        )
        return result

    def cancel(self, reason: str) -> None:
        del reason
        if self._process is not None:
            self._terminate_process_group(self._process)

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except (ProcessLookupError, AttributeError, Exception):
            pass

        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                if hasattr(os, "killpg") and hasattr(signal, "SIGKILL"):
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except (ProcessLookupError, AttributeError, Exception):
                return
            try:
                process.wait()
            except Exception:
                pass
