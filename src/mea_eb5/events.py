"""Canonical, redacted, tamper-evident event collection for MEA-EB5 runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Mapping, TypeAlias

from .models import JSONValue, RunStatus


EventScalar: TypeAlias = str | int | float | bool | None | RunStatus
EventValue: TypeAlias = EventScalar | list["EventValue"] | dict[str, "EventValue"]
EventPayload: TypeAlias = Mapping[str, EventValue]

_REDACTED = "[REDACTED]"
_SECRET_KEY = re.compile(
    r"authorization|api[_-]?key|secret|token|password|cookie", re.IGNORECASE
)
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_RFC3339_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_PROVENANCE = frozenset({"native", "collector", "inferred", "grader"})
_SENSITIVITY = frozenset({"PUBLIC", "PRIVATE", "REDACTED"})
_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "sequence",
        "timestamp",
        "monotonic_ns",
        "source",
        "type",
        "payload",
        "task_id",
        "parent_run_id",
        "provenance",
        "sensitivity",
        "previous_hash",
        "event_hash",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {"schema_version", "run_id", "event_count", "final_sequence", "terminal_hash"}
)


@dataclass(frozen=True)
class ChainVerification:
    """Result of checking canonical event ordering and hash continuity."""

    valid: bool
    event_count: int
    first_invalid_sequence: int | None


class EventSink:
    """Append redacted events to one deterministic, hash-linked JSONL log."""

    def __init__(self, path: Path | str, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id must not be empty")

        self._path = Path(path)
        self._run_id = run_id
        self._sequence = 0
        self._previous_hash: str | None = None
        self._resume_existing_chain()

    def emit(
        self,
        type: str,
        payload: EventPayload,
        provenance: str,
        task_id: str | None = None,
    ) -> dict[str, JSONValue]:
        """Redact, hash, persist, and return one canonical event envelope."""
        if not type:
            raise ValueError("event type must not be empty")
        if provenance not in _PROVENANCE:
            raise ValueError("provenance must be native, collector, inferred, or grader")
        if task_id is not None and not task_id:
            raise ValueError("task_id must not be empty when provided")

        redacted_payload, was_redacted = _redact_mapping(payload)
        event: dict[str, JSONValue] = {
            "schema_version": "1.0",
            "run_id": self._run_id,
            "sequence": self._sequence + 1,
            "timestamp": _utc_timestamp(),
            "monotonic_ns": time.monotonic_ns(),
            "source": provenance,
            "type": type,
            "payload": redacted_payload,
            "task_id": task_id,
            "parent_run_id": None,
            "provenance": provenance,
            "sensitivity": "REDACTED" if was_redacted else "PUBLIC",
            "previous_hash": self._previous_hash,
        }
        event["event_hash"] = _event_hash(event)
        serialized = _canonical_json(event)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized + "\n")
            stream.flush()
            os.fsync(stream.fileno())

        _write_terminal_commitment(
            self._path,
            {
                "schema_version": "1.0",
                "run_id": self._run_id,
                "event_count": self._sequence + 1,
                "final_sequence": self._sequence + 1,
                "terminal_hash": event["event_hash"],
            },
        )

        self._sequence = event["sequence"]
        self._previous_hash = event["event_hash"]
        return event

    def _resume_existing_chain(self) -> None:
        if not self._path.exists() or not self._path.read_text(encoding="utf-8"):
            return

        verification = verify_event_chain(self._path)
        if not verification.valid:
            raise ValueError("cannot append to an invalid event chain")

        events = [json.loads(line) for line in self._path.read_text(encoding="utf-8").splitlines()]
        last_event = events[-1]
        if last_event["run_id"] != self._run_id:
            raise ValueError("existing event chain belongs to a different run_id")
        self._sequence = last_event["sequence"]
        self._previous_hash = last_event["event_hash"]


def verify_event_chain(path: Path | str) -> ChainVerification:
    """Verify strict event envelopes, canonical hashes, and contiguous linking."""
    event_count = 0
    expected_sequence = 1
    previous_hash: str | None = None

    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ChainVerification(False, event_count, None)

    for line in lines:
        if not line:
            return ChainVerification(False, event_count, None)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return ChainVerification(False, event_count, None)
        if not isinstance(event, dict):
            return ChainVerification(False, event_count, None)

        event_count += 1
        sequence = event.get("sequence")
        invalid_sequence = sequence if _is_nonnegative_integer(sequence) else None
        if not _is_valid_event_shape(event):
            return ChainVerification(False, event_count, invalid_sequence)
        if line != _canonical_json(event):
            return ChainVerification(False, event_count, sequence)
        if sequence != expected_sequence or event["previous_hash"] != previous_hash:
            return ChainVerification(False, event_count, sequence)
        if event["event_hash"] != _event_hash_without_hash(event):
            return ChainVerification(False, event_count, sequence)
        redacted_payload, _ = _redact_mapping(event["payload"])
        if redacted_payload != event["payload"]:
            return ChainVerification(False, event_count, sequence)

        previous_hash = event["event_hash"]
        expected_sequence += 1

    event_path = Path(path)
    if not event_count:
        return ChainVerification(not _checkpoint_path(event_path).exists(), 0, None)

    if not _terminal_commitment_matches(
        event_path,
        event_count=event_count,
        final_sequence=expected_sequence - 1,
        terminal_hash=previous_hash,
        run_id=event["run_id"],
    ):
        return ChainVerification(False, event_count, None)

    return ChainVerification(True, event_count, None)


def _redact_mapping(value: Mapping[str, EventValue]) -> tuple[dict[str, JSONValue], bool]:
    redacted: dict[str, JSONValue] = {}
    was_redacted = False
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("event payload keys must be strings")
        if _SECRET_KEY.search(key):
            redacted[key] = _REDACTED
            was_redacted = True
        else:
            normalized, nested_redaction = _redact_value(item)
            redacted[key] = normalized
            was_redacted = was_redacted or nested_redaction
    return redacted, was_redacted


def _redact_value(value: EventValue) -> tuple[JSONValue, bool]:
    if isinstance(value, RunStatus):
        return value.value, False
    if value is None or isinstance(value, (str, bool, int)):
        return value, False
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("event payload floats must be finite")
        return value, False
    if isinstance(value, list):
        values: list[JSONValue] = []
        was_redacted = False
        for item in value:
            normalized, nested_redaction = _redact_value(item)
            values.append(normalized)
            was_redacted = was_redacted or nested_redaction
        return values, was_redacted
    if isinstance(value, dict):
        return _redact_mapping(value)
    raise ValueError("event payload must contain only JSON values")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: Mapping[str, JSONValue]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _event_hash(event: Mapping[str, JSONValue]) -> str:
    return _event_hash_without_hash(event)


def _event_hash_without_hash(event: Mapping[str, JSONValue]) -> str:
    unhashed = {key: value for key, value in event.items() if key != "event_hash"}
    return hashlib.sha256(_canonical_json(unhashed).encode("utf-8")).hexdigest()


def _checkpoint_path(path: Path) -> Path:
    return path.with_name(path.name + ".checkpoint.json")


def _write_terminal_commitment(path: Path, checkpoint: Mapping[str, JSONValue]) -> None:
    checkpoint_path = _checkpoint_path(path)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{checkpoint_path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_canonical_json(checkpoint) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, checkpoint_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _terminal_commitment_matches(
    path: Path,
    *,
    event_count: int,
    final_sequence: int,
    terminal_hash: str | None,
    run_id: object,
) -> bool:
    try:
        serialized = _checkpoint_path(path).read_text(encoding="utf-8")
        checkpoint = json.loads(serialized)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False

    if not isinstance(checkpoint, dict) or serialized != _canonical_json(checkpoint) + "\n":
        return False
    if set(checkpoint) != _CHECKPOINT_FIELDS:
        return False
    return (
        checkpoint["schema_version"] == "1.0"
        and checkpoint["run_id"] == run_id
        and _is_nonnegative_integer(checkpoint["event_count"])
        and checkpoint["event_count"] == event_count
        and _is_nonnegative_integer(checkpoint["final_sequence"])
        and checkpoint["final_sequence"] == final_sequence
        and checkpoint["terminal_hash"] == terminal_hash
        and isinstance(checkpoint["terminal_hash"], str)
        and bool(_HASH.fullmatch(checkpoint["terminal_hash"]))
    )


def _is_valid_event_shape(event: dict[object, object]) -> bool:
    if set(event) != _EVENT_FIELDS:
        return False
    if not all(isinstance(event[field], str) and event[field] for field in ("schema_version", "run_id", "timestamp", "source", "type")):
        return False
    if not _is_rfc3339_timestamp(event["timestamp"]):
        return False
    if not _is_nonnegative_integer(event["sequence"]) or event["sequence"] < 1:
        return False
    if not _is_nonnegative_integer(event["monotonic_ns"]):
        return False
    if not isinstance(event["payload"], dict) or not _is_json_value(event["payload"]):
        return False
    if event["task_id"] is not None and (not isinstance(event["task_id"], str) or not event["task_id"]):
        return False
    if event["parent_run_id"] is not None and (not isinstance(event["parent_run_id"], str) or not event["parent_run_id"]):
        return False
    if event["provenance"] not in _PROVENANCE or event["sensitivity"] not in _SENSITIVITY:
        return False
    if event["previous_hash"] is not None and (not isinstance(event["previous_hash"], str) or not _HASH.fullmatch(event["previous_hash"])):
        return False
    return isinstance(event["event_hash"], str) and bool(_HASH.fullmatch(event["event_hash"]))


def _is_nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_rfc3339_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not _RFC3339_TIMESTAMP.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False
