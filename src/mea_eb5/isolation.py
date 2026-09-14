"""Immutable container policy specification for isolated benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

_IMAGE_REF_RE = re.compile(r"^[^@]+@sha256:[a-f0-9]{64}$")


@dataclass(frozen=True)
class ContainerSpec:
    """Policy for a single digest-pinned, sandboxed container execution."""

    image: str
    cpu: float | str
    memory: str
    pids: int
    workspace: Path
    timeout_seconds: int
    network: str = "none"
    readonly_root: bool = True
    cap_drop: list[str] = field(default_factory=lambda: ["ALL"])

    def __post_init__(self) -> None:
        if not _IMAGE_REF_RE.fullmatch(self.image):
            raise ValueError(
                "image must be digest-pinned as name@sha256:<64 hex chars>"
            )
        if isinstance(self.cpu, (int, float)) and self.cpu <= 0:
            raise ValueError("cpu must be positive")
        if not self.memory:
            raise ValueError("memory must not be empty")
        if (
            not isinstance(self.pids, int)
            or isinstance(self.pids, bool)
            or self.pids < 1
        ):
            raise ValueError("pids must be a positive integer")
        if (
            not isinstance(self.timeout_seconds, int)
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds < 1
        ):
            raise ValueError("timeout_seconds must be a positive integer")

        if not isinstance(self.workspace, Path):
            object.__setattr__(self, "workspace", Path(self.workspace))


def docker_argv(spec: ContainerSpec) -> list[str]:
    """Return a ``docker run`` argv list for *spec* with no shell involved."""
    argv: list[str] = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--network",
        spec.network,
        "--user",
        "65534:65534",
        "--workdir",
        "/workspace",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--pids-limit",
        str(spec.pids),
        "--cpus",
        str(spec.cpu),
        "--memory",
        spec.memory,
        "--stop-timeout",
        str(spec.timeout_seconds),
        "--security-opt",
        "no-new-privileges",
        "-v",
        f"{spec.workspace.expanduser().absolute()}:/workspace",
    ]

    for cap in spec.cap_drop:
        argv.extend(["--cap-drop", cap])

    if spec.readonly_root:
        argv.append("--read-only")

    argv.append(spec.image)
    return argv


__all__ = ["ContainerSpec", "docker_argv"]
