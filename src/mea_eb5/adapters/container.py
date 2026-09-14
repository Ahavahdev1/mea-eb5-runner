"""Digest-pinned container adapter for untrusted CLI systems."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
from typing import Mapping

from ..events import EventSink
from ..isolation import ContainerSpec, docker_argv
from .base import AdapterDescription, AdapterExecution, TaskRequest


class ContainerCliAdapter:
    """Run the evaluated CLI inside a resource-limited Docker container."""

    def __init__(
        self,
        image: str,
        command: list[str],
        *,
        cpu: float | str = 1.0,
        memory: str = "1g",
        pids: int = 128,
        timeout_seconds: int = 900,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must be a non-empty list of non-empty strings")
        self._image = image
        self._command = tuple(command)
        self._cpu = cpu
        self._memory = memory
        self._pids = pids
        self._timeout_seconds = timeout_seconds
        self._process: subprocess.Popen[bytes] | None = None

        # Validate the complete policy immediately, before a benchmark begins.
        self._spec(Path("."))

    @property
    def image(self) -> str:
        """Return the immutable evaluated-system image reference."""
        return self._image

    def describe(self) -> AdapterDescription:
        return AdapterDescription(name="container-cli", version="1.0", transport="docker")

    def prepare(self, config: Mapping[str, object]) -> None:
        if config.get("network_allowed") is True:
            raise ValueError("container CLI adapter does not permit network access")

    def build_argv(self, workspace: Path) -> list[str]:
        """Build the auditable argv without invoking a shell."""
        return [
            *docker_argv(self._spec(workspace)),
            *self._command,
            "--goal-file",
            "/workspace/.mea-eb5-goal.txt",
        ]

    def run(
        self, task: TaskRequest, workspace: Path, event_sink: EventSink
    ) -> AdapterExecution:
        workspace.mkdir(parents=True, exist_ok=True)
        self._make_container_writable(workspace)
        goal_path = workspace / ".mea-eb5-goal.txt"
        goal_path.write_text(task.instruction, encoding="utf-8")
        terminal_path = workspace.parent / "raw-terminal.log"

        try:
            with terminal_path.open("wb") as terminal:
                process = subprocess.Popen(
                    self.build_argv(workspace),
                    cwd=workspace.parent,
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
            goal_path.unlink(missing_ok=True)

        event_sink.emit(
            "adapter_execution_finished",
            {"adapter": "container-cli", **result.to_dict()},
            "collector",
            task_id=task.task_id,
        )
        return result

    def cancel(self, reason: str) -> None:
        del reason
        if self._process is not None:
            self._terminate_process_group(self._process)

    def _spec(self, workspace: Path) -> ContainerSpec:
        return ContainerSpec(
            image=self._image,
            cpu=self._cpu,
            memory=self._memory,
            pids=self._pids,
            workspace=workspace,
            timeout_seconds=self._timeout_seconds,
        )

    @staticmethod
    def _make_container_writable(workspace: Path) -> None:
        """Allow the fixed unprivileged container UID to edit only its bind mount."""
        for dirpath, dirnames, filenames in os.walk(workspace):
            current = Path(dirpath)
            current.chmod(0o777)
            for dirname in dirnames:
                (current / dirname).chmod(0o777)
            for filename in filenames:
                path = current / filename
                if not path.is_symlink():
                    path.chmod(0o666)

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            process.wait()


__all__ = ["ContainerCliAdapter"]
