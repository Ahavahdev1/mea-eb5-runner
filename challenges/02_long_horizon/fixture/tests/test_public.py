"""Public simulator contracts for challenge 02."""

from service_sim import apply_fault, health, init_db, recover


def test_restart_recovers_basic_health(tmp_path) -> None:
    database = tmp_path / "service.db"
    init_db(database)
    apply_fault(database, "invalid_config")
    recover(database)
    assert health(database)["healthy"] is True
