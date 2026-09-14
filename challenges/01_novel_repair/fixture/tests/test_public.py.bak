"""Public tests for the novel repair challenge."""

from __future__ import annotations

import pytest

from src.orders import normalize_and_sort_orders


def test_sorts_strings_ascending() -> None:
    rows = [
        {"name": "c", "customer": "Zoe"},
        {"name": "a", "customer": "Ada"},
        {"name": "b", "customer": "Bob"},
    ]
    result = normalize_and_sort_orders(rows, "customer")
    assert [r["customer"] for r in result] == ["Ada", "Bob", "Zoe"]


def test_sorts_strings_descending() -> None:
    rows = [
        {"name": "c", "customer": "Zoe"},
        {"name": "a", "customer": "Ada"},
    ]
    result = normalize_and_sort_orders(rows, "customer", descending=True)
    assert [r["customer"] for r in result] == ["Zoe", "Ada"]
