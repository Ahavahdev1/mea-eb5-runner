"""Public correctness contract for challenge 03."""

from event_index import lookup_latest


def test_latest_event_and_missing_keys() -> None:
    events = [
        {"key": "a", "ts": 1, "payload": "old"},
        {"key": "a", "ts": 3, "payload": "new"},
        {"key": "b", "ts": 2, "payload": "only"},
    ]
    result = lookup_latest(events, ["a", "b", "missing"])
    assert result["a"]["payload"] == "new"
    assert result["b"]["payload"] == "only"
    assert result["missing"] == {}
