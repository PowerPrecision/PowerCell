"""Unit tests for websocket route thinning helpers (websocket_api_*)."""

from pathlib import Path


def test_websocket_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "websocket_api_helpers.py",
        "websocket_api_notifications.py",
        "websocket_api_status.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("websocket_api_*.py"))
    assert files == expected
    # Do not overwrite websocket_manager.py
    assert (services_dir / "websocket_manager.py").exists()
    assert (services_dir / "websocket_manager.py").read_text().count("\n") > 50
    assert not (services_dir / "websocket.py").exists()


def test_websocket_api_export_run_entrypoints():
    from services import (
        websocket_api_helpers,
        websocket_api_notifications,
        websocket_api_status,
    )

    assert callable(websocket_api_helpers.verify_websocket_token)
    assert callable(websocket_api_helpers.is_disconnect_error)
    assert callable(websocket_api_notifications.run_websocket_notifications)
    assert callable(websocket_api_status.run_websocket_status)


def test_is_disconnect_error_detects_common_cases():
    from services.websocket_api_helpers import is_disconnect_error

    assert is_disconnect_error(RuntimeError("Cannot call receive once a disconnect"))
    assert is_disconnect_error(ConnectionError("connection reset by peer"))
    assert not is_disconnect_error(ValueError("unrelated"))


def test_websocket_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "websocket.py"
    text = routes_path.read_text()
    assert "await run_websocket_notifications" in text
    assert "return await run_websocket_status" in text
    assert len(text.splitlines()) < 50
    assert "/ws/notifications" in text
    assert "/ws/status" in text
    assert "mark_notification_read" not in text


def test_auth_failure_accepts_before_custom_close_codes():
    """Pacote DX: accept() before close(4001/4002) so browsers get the WS
    close code instead of an HTTP 403 handshake (infinite reconnect as 1006).
    """
    path = Path(__file__).resolve().parents[2] / "services" / "websocket_api_notifications.py"
    text = path.read_text()
    expired_idx = text.find('user == "expired"')
    invalid_idx = text.find('user == "invalid"')
    assert expired_idx != -1
    assert invalid_idx != -1

    expired_block = text[expired_idx:invalid_idx]
    assert "websocket.accept()" in expired_block
    assert "code=4001" in expired_block
    assert expired_block.find("websocket.accept()") < expired_block.find("code=4001")

    invalid_block = text[invalid_idx:]
    assert "websocket.accept()" in invalid_block
    assert "code=4002" in invalid_block
    assert     invalid_block.find("websocket.accept()") < invalid_block.find("code=4002")


def test_websocket_api_export_acl_helpers():
    from services.websocket_api_helpers import (
        process_room_name,
        user_can_join_process_room,
        authorize_process_room_access,
        load_process_for_room_acl,
    )

    assert process_room_name("abc") == "process_abc"
    assert callable(user_can_join_process_room)
    assert callable(authorize_process_room_access)
    assert callable(load_process_for_room_acl)


def test_lock_events_broadcast_to_process_room_not_globally():
    """Pacote FG / C2: process_locked/unlocked go to process_{id} only."""
    path = Path(__file__).resolve().parents[2] / "services" / "websocket_api_notifications.py"
    text = path.read_text()

    locked_idx = text.find('msg_type == "process_locked"')
    unlocked_idx = text.find('msg_type == "process_unlocked"')
    join_idx = text.find('msg_type == "join_process_room"')
    assert locked_idx != -1 and unlocked_idx != -1 and join_idx != -1

    locked_block = text[locked_idx:unlocked_idx]
    unlocked_block = text[unlocked_idx:join_idx]
    for block in (locked_block, unlocked_block):
        assert "broadcast_to_room" in block
        assert "process_room_name" in block
        assert "authorize_process_room_access" in block
        assert "manager.broadcast(" not in block

    # Remaining global broadcasts are presence (admin/ceo online/offline)
    assert text.count("await manager.broadcast(") == 2
    assert "authorize_process_room_access" in text[join_idx:]
    assert "room_join_denied" in text[join_idx:]
    assert "manager.join_room" in text[join_idx:]


class TestUserCanJoinProcessRoom:
    def _process(self, **overrides):
        doc = {
            "id": "p1",
            "client_id": "cli1",
            "status": "documentacao",
            "created_by": "ix@x.com",
        }
        doc.update(overrides)
        return doc

    def test_missing_user_or_process_denied(self):
        from services.websocket_api_helpers import user_can_join_process_room

        assert user_can_join_process_room(None, self._process()) is False
        assert user_can_join_process_room({"id": "u1", "role": "admin"}, None) is False

    def test_gestor_can_join_any(self):
        from services.websocket_api_helpers import user_can_join_process_room

        process = self._process()
        for role in ("admin", "ceo", "diretor", "administrativo"):
            assert user_can_join_process_room({"id": "g1", "role": role}, process) is True

    def test_consultor_only_if_assigned(self):
        from services.websocket_api_helpers import user_can_join_process_room

        consultor = {"id": "c1", "role": "consultor"}
        assert user_can_join_process_room(consultor, self._process()) is False
        assert user_can_join_process_room(
            consultor, self._process(assigned_consultor_id="c1")
        ) is True
        assert user_can_join_process_room(
            consultor, self._process(assigned_consultor_ids=["c1", "c2"])
        ) is True
        assert user_can_join_process_room(
            consultor, self._process(assigned_to="c1")
        ) is True

    def test_intermediario_only_if_assigned(self):
        from services.websocket_api_helpers import user_can_join_process_room

        user = {"id": "m1", "role": "intermediario"}
        assert user_can_join_process_room(user, self._process()) is False
        assert user_can_join_process_room(
            user, self._process(assigned_mediador_id="m1")
        ) is True

    def test_legacy_mediador_role_maps_to_intermediario(self):
        from services.websocket_api_helpers import user_can_join_process_room

        user = {"id": "m1", "role": "mediador"}
        assert user_can_join_process_room(
            user, self._process(assigned_mediador_ids=["m1"])
        ) is True

    def test_indexacao_fila_or_assigned_or_creator(self):
        from services.websocket_api_helpers import user_can_join_process_room

        creator = {"id": "ix1", "role": "indexacao", "email": "ix@x.com"}
        other = {"id": "ix2", "role": "indexacao", "email": "other@x.com"}
        assert user_can_join_process_room(
            creator, self._process(created_by="ix@x.com", status="documentacao")
        ) is True
        assert user_can_join_process_room(
            other, self._process(created_by="ix@x.com", status="documentacao")
        ) is False
        assert user_can_join_process_room(
            other, self._process(created_by="ix@x.com", status="fila_espera")
        ) is True
        assert user_can_join_process_room(
            other, self._process(created_by="ix@x.com", assigned_indexacao_id="ix2")
        ) is True

    def test_cliente_own_process_only(self):
        from services.websocket_api_helpers import user_can_join_process_room

        user = {"id": "cli1", "role": "cliente"}
        assert user_can_join_process_room(user, self._process()) is True
        assert user_can_join_process_room(
            {"id": "cli2", "role": "cliente"}, self._process()
        ) is False

    def test_parceiro_denied(self):
        from services.websocket_api_helpers import user_can_join_process_room

        user = {"id": "par1", "role": "parceiro"}
        assert user_can_join_process_room(
            user, self._process(assigned_consultor_id="par1")
        ) is False

    def test_unknown_role_denied(self):
        from services.websocket_api_helpers import user_can_join_process_room

        assert user_can_join_process_room(
            {"id": "u1", "role": "hacker"}, self._process()
        ) is False

    def test_additional_roles_gestor_grants_access(self):
        from services.websocket_api_helpers import user_can_join_process_room

        user = {
            "id": "c1",
            "role": "consultor",
            "additional_roles": ["diretor"],
        }
        assert user_can_join_process_room(user, self._process()) is True


def test_authorize_process_room_access_uses_db_document(monkeypatch):
    import asyncio
    from services import websocket_api_helpers as helpers

    async def fake_load(process_id):
        assert process_id == "p9"
        return {"id": "p9", "assigned_consultor_id": "c1"}

    monkeypatch.setattr(helpers, "load_process_for_room_acl", fake_load)

    allowed = asyncio.run(
        helpers.authorize_process_room_access({"id": "c1", "role": "consultor"}, "p9")
    )
    denied = asyncio.run(
        helpers.authorize_process_room_access({"id": "c2", "role": "consultor"}, "p9")
    )
    assert allowed is True
    assert denied is False
