"""Load evaluated-system adapter configuration without shell interpolation."""

from __future__ import annotations

from pathlib import Path

import yaml

from .adapters.base import AgentAdapter
from .adapters.cli import CliAdapter
from .adapters.container import ContainerCliAdapter


def load_adapter(path: Path, *, timeout_seconds: int) -> AgentAdapter:
    """Build an adapter from a strict YAML file controlled by the evaluator."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("kind") != "cli":
        raise ValueError("adapter config kind must be 'cli'")
    unknown = set(data).difference(
        {"kind", "image", "command", "cpu", "memory", "pids", "allow_host_execution"}
    )
    if unknown:
        raise ValueError("unknown adapter config keys: " + ", ".join(sorted(unknown)))
    command = data.get("command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(part, str) or not part for part in command)
    ):
        raise ValueError("adapter config command must be a non-empty string list")
    image = data.get("image")
    if image is not None:
        if not isinstance(image, str) or not image:
            raise ValueError("adapter config image must be a non-empty string")
        cpu = data.get("cpu", 1.0)
        memory = data.get("memory", "1g")
        pids = data.get("pids", 128)
        if not isinstance(cpu, (int, float, str)) or isinstance(cpu, bool):
            raise ValueError("adapter config cpu must be a number or Docker CPU string")
        if not isinstance(memory, str) or not memory:
            raise ValueError("adapter config memory must be a non-empty string")
        if not isinstance(pids, int) or isinstance(pids, bool):
            raise ValueError("adapter config pids must be an integer")
        return ContainerCliAdapter(
            image,
            command,
            cpu=cpu,
            memory=memory,
            pids=pids,
            timeout_seconds=timeout_seconds,
        )

    if data.get("allow_host_execution") is not True:
        raise ValueError(
            "adapter config requires a digest-pinned image; host execution must be "
            "explicitly enabled only for local testing"
        )
    return CliAdapter(command, timeout_seconds=timeout_seconds)


__all__ = ["load_adapter"]
