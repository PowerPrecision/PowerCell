"""Unit tests for client route thinning helpers."""


def test_client_modules_export_run_entrypoints():
    from services import (
        client_portal_email,
        client_me,
        client_registered,
        client_assign,
        client_list_search,
        client_crud,
        client_process_ops,
        client_portal_access,
        client_find_or_create,
        client_delete,
    )

    assert callable(client_portal_email._send_portal_welcome_email_safe)
    assert callable(client_me.run_get_my_assigned_clients)
    assert callable(client_registered.run_list_registered_clients)
    assert callable(client_assign.run_assign_client_to_user)
    assert callable(client_list_search.run_search_clients)
    assert callable(client_list_search.run_list_clients)
    assert callable(client_crud.run_get_client)
    assert callable(client_crud.run_create_client)
    assert callable(client_crud.run_update_client)
    assert callable(client_process_ops.run_link_process_to_client)
    assert callable(client_process_ops.run_unlink_process_from_client)
    assert callable(client_process_ops.run_create_process_for_client)
    assert callable(client_process_ops.run_get_client_processes)
    assert callable(client_portal_access.run_resend_portal_access)
    assert callable(client_find_or_create.run_find_or_create_client)
    assert callable(client_delete.run_delete_client)


def test_client_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "clients.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 15
    assert len(text.splitlines()) < 250
