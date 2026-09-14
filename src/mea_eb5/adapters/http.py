"""Bounded HTTPS adapter for remote repair systems."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..events import EventSink
from .base import AdapterDescription, AdapterExecution, TaskRequest


_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class HttpRepairAdapter:
    """Submit a repair task to an approved endpoint without leaking credentials."""

    def __init__(
        self, endpoint: str, *, auth_env: str | None = None, timeout_seconds: float = 900
    ) -> None:
        parsed = urlparse(endpoint)
        hostname = parsed.hostname.lower() if parsed.hostname else None
        allowed = parsed.scheme == "https" and hostname is not None
        allowed = allowed or (parsed.scheme == "http" and hostname == "localhost")
        if not allowed or parsed.username is not None or parsed.password is not None:
            raise ValueError("endpoint must use HTTPS or HTTP on localhost without URL credentials")
        if auth_env is not None and not auth_env:
            raise ValueError("auth_env must not be empty when provided")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._endpoint = endpoint
        self._auth_env = auth_env
        self._timeout_seconds = timeout_seconds

    def describe(self) -> AdapterDescription:
        return AdapterDescription(name="http-repair", version="1.0", transport="http")

    def prepare(self, config: Mapping[str, object]) -> None:
        del config

    def run(
        self, task: TaskRequest, workspace: Path, event_sink: EventSink
    ) -> AdapterExecution:
        del workspace
        body = json.dumps(
            {
                "filename": task.filename,
                "code": task.code,
                "instruction": task.instruction,
                "test_cmd": task.test_cmd,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._auth_env is not None and (credential := os.environ.get(self._auth_env)):
            headers["Authorization"] = credential
        request = Request(self._endpoint, data=body, headers=headers, method="POST")

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read(_MAX_RESPONSE_BYTES + 1)
                status = getattr(response, "status", 200)
        except HTTPError:
            result = AdapterExecution(succeeded=False, exit_code=None, error_kind="protocol_error")
        except URLError:
            result = AdapterExecution(succeeded=False, exit_code=None, error_kind="network_error")
        except OSError:
            result = AdapterExecution(succeeded=False, exit_code=None, error_kind="network_error")
        else:
            if len(response_body) > _MAX_RESPONSE_BYTES:
                result = AdapterExecution(
                    succeeded=False,
                    exit_code=None,
                    error_kind="response_too_large",
                    response_bytes=len(response_body),
                )
            elif not 200 <= status < 300:
                result = AdapterExecution(
                    succeeded=False,
                    exit_code=None,
                    error_kind="protocol_error",
                    response_bytes=len(response_body),
                )
            else:
                result = AdapterExecution(
                    succeeded=True,
                    exit_code=0,
                    response_bytes=len(response_body),
                )

        event_sink.emit(
            "adapter_execution_finished",
            {"adapter": "http-repair", **result.to_dict()},
            "collector",
            task_id=task.task_id,
        )
        return result

    def cancel(self, reason: str) -> None:
        del reason
