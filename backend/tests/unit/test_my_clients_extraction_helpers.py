"""Unit tests for my_clients route thinning (my_clients_api_*)."""

from models.auth import UserRole


def test_process_my_clients_not_overwritten():
    from pathlib import Path
    from services import process_my_clients

    core = Path(__file__).resolve().parents[2] / "services" / "process_my_clients.py"
    assert core.exists()
    text = core.read_text()
    assert "Helpers para GET /processes/my-clients" in text
    assert callable(process_my_clients.run_get_my_clients)
    assert callable(process_my_clients.fetch_unread_messages_map)
    # Core must remain substantial (not replaced by route stubs)
    assert text.count("\n") > 300


def test_my_clients_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "my_clients_api_helpers.py",
        "my_clients_api_list.py",
        "my_clients_api_stats.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("my_clients_api_*.py"))
    assert files == expected


def test_my_clients_api_export_run_entrypoints():
    from services import my_clients_api_list, my_clients_api_stats, my_clients_api_helpers

    assert callable(my_clients_api_list.run_get_my_clients)
    assert callable(my_clients_api_stats.run_get_my_clients_stats)
    assert my_clients_api_helpers.INACTIVE_STATUSES == [
        "concluidos", "desistencias", "eliminados",
    ]
    assert None in my_clients_api_helpers.LEAD_STATUS_VALUES


def test_build_query_consultor_active():
    from services.my_clients_api_helpers import (
        INACTIVE_STATUSES,
        apply_pre_registo_exclusion,
        build_my_clients_process_query,
    )

    q = build_my_clients_process_query(
        user_id="u1",
        user_email="a@b.c",
        role=UserRole.CONSULTOR,
        wants_deleted=False,
    )
    assert "$and" in q
    q2 = apply_pre_registo_exclusion(q)
    assert any(
        c.get("status", {}).get("$nin") is not None
        for c in q2["$and"]
        if isinstance(c.get("status"), dict)
    )
    # inactive filter still present
    assert any(
        c.get("status") == {"$nin": INACTIVE_STATUSES}
        for c in q["$and"]
        if isinstance(c.get("status"), dict)
    )


def test_build_query_deleted_admin():
    from services.my_clients_api_helpers import build_my_clients_process_query

    q = build_my_clients_process_query(
        user_id="u1",
        user_email="a@b.c",
        role=UserRole.ADMIN,
        wants_deleted=True,
    )
    assert q == {"is_deleted": True}


def test_format_lead_row():
    from services.my_clients_api_helpers import format_lead_row

    row = format_lead_row({
        "id": "c1",
        "nome": "Ana",
        "contacto": {"email": "a@b.c", "telefone": "910"},
        "created_at": "t1",
        "updated_at": "t2",
    })
    assert row["is_lead"] is True
    assert row["status"] == "lead"
    assert row["client_name"] == "Ana"
    assert row["client_email"] == "a@b.c"
    assert row["pending_tasks"] == 0


def test_my_clients_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "my_clients.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 2
    assert len(text.splitlines()) < 80
    assert "db.processes.find" not in text
    assert "process_my_clients.py" in text  # collision note in docstring
