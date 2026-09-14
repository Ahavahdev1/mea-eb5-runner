"""Event lookup baseline — intentionally quadratic."""

from __future__ import annotations


def lookup_latest(events: list[dict], keys: list[str]) -> dict[str, dict]:
    """Return the most recent event for each key.

    Baseline scans all events once per key.  Correctness gates performance.
    """
    result: dict[str, dict] = {}
    for key in keys:
        latest: dict | None = None
        for event in events:
            if event.get("key") == key:
                if latest is None or event.get("ts", 0) > latest.get("ts", 0):
                    latest = event
        result[key] = latest or {}
    return result
