"""Vulnerable authorization service for challenge 04."""

from __future__ import annotations


class AuthService:
    """Document access service with an IDOR vulnerability."""

    def __init__(self) -> None:
        self._sessions: dict[str, int] = {}
        self._documents: dict[int, dict] = {
            1: {"owner_id": 1, "content": "secret-of-alice"},
            2: {"owner_id": 2, "content": "secret-of-bob"},
        }
        self._next_session = 1000

    def login(self, user_id: int) -> str:
        token = f"session-{self._next_session}"
        self._next_session += 1
        self._sessions[token] = user_id
        return token

    def read_document(self, token: str, document_id: int, owner_id: int | None = None) -> dict:
        """BUG: trusts owner_id from the request instead of server-side storage."""
        if token not in self._sessions:
            raise PermissionError("invalid session")
        if document_id not in self._documents:
            raise ValueError("document not found")

        doc = self._documents[document_id]
        requested_owner = owner_id if owner_id is not None else self._sessions[token]
        if doc["owner_id"] != requested_owner:
            raise PermissionError("not owner")
        return {"document_id": document_id, "content": doc["content"]}


def main() -> None:
    service = AuthService()
    alice = service.login(1)
    print(service.read_document(alice, 1))


if __name__ == "__main__":
    main()
