"""Public tests for the adversarial security challenge."""

from __future__ import annotations

from auth_service import AuthService


def test_owner_can_read_own_document() -> None:
    service = AuthService()
    token = service.login(1)
    result = service.read_document(token, 1)
    assert result["document_id"] == 1
    assert "secret-of-alice" in result["content"]
