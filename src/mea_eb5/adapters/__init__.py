"""Adapters that isolate benchmark lifecycle and evidence from agent transports."""

from .base import AdapterDescription, AdapterExecution, AgentAdapter, TaskRequest
from .cli import CliAdapter
from .container import ContainerCliAdapter
from .http import HttpRepairAdapter
from .noop import NoopAdapter

__all__ = [
    "AdapterDescription",
    "AdapterExecution",
    "AgentAdapter",
    "CliAdapter",
    "ContainerCliAdapter",
    "HttpRepairAdapter",
    "NoopAdapter",
    "TaskRequest",
]
