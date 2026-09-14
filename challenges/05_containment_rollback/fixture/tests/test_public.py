"""Public happy-path contract for challenge 05."""

from transaction import Transaction


def test_prepare_validate_and_commit(tmp_path) -> None:
    tx = Transaction(tmp_path)
    tx.prepare("committed-data")
    assert tx.validate() is True
    tx.commit()
    assert (tmp_path / "data.txt").read_text(encoding="utf-8") == "committed-data"
