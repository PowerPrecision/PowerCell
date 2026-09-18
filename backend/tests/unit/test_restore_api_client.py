"""PACOTE 11 — Unit tests do restore de clientes (Eixo 4).

POST /api/clients/{id}/restore — fecha a assimetria do client_delete.py
(que anunciava o endpoint mas a rota não existia). Cascata simétrica:
cliente + processos do 1º titular + documentos + tarefas + RGPD.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.restore_api_client import run_restore_client


USER = {"id": "u1", "name": "Admin", "role": "admin"}


def _seed(fake_db, *, client_doc, processes=None, docs=None, tasks=None, rgpd=None, workflow=None):
    fake_db.clients.docs.append(dict(client_doc))
    for p in (processes or []):
        fake_db.processes.docs.append(dict(p))
    for d in (docs or []):
        fake_db.documents.docs.append(dict(d))
    for t in (tasks or []):
        fake_db.tasks.docs.append(dict(t))
    for r in (rgpd or []):
        fake_db.rgpd_requests.docs.append(dict(r))
    for w in (workflow or []):
        fake_db.workflow_statuses.docs.append(dict(w))


class TestRestoreClient:
    async def test_404_quando_cliente_nao_existe(self, fake_async_db):
        import services.restore_api_client as svc
        with patch.object(svc, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await run_restore_client("missing", USER)
        assert exc.value.status_code == 404

    async def test_400_quando_cliente_nao_esta_eliminado(self, fake_async_db):
        _seed(fake_async_db, client_doc={"id": "c1", "nome": "Ana", "is_deleted": False})
        import services.restore_api_client as svc
        with patch.object(svc, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await run_restore_client("c1", USER)
        assert exc.value.status_code == 400

    async def test_restaura_cliente_com_previous_status(self, fake_async_db):
        _seed(
            fake_async_db,
            client_doc={
                "id": "c1", "nome": "Ana", "is_deleted": True, "deleted": True,
                "status": "eliminado", "is_active": False,
                "previous_status": "fase_documental",
            },
        )
        import services.restore_api_client as svc
        with patch.object(svc, "db", fake_async_db):
            result = await run_restore_client("c1", USER)

        assert result["success"] is True
        restored = fake_async_db.clients.docs[0]
        assert restored["is_deleted"] is False
        assert restored["deleted"] is False
        assert restored["status"] == "fase_documental"
        assert restored["is_active"] is True
        assert restored["restored_by"] == "u1"

    async def test_restaura_com_fase_dinamica_sem_previous(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        _seed(
            fake_async_db,
            client_doc={"id": "c1", "nome": "Ana", "is_deleted": True, "status": "eliminado"},
            workflow=[{"id": "w1", "name": "clientes_espera", "order": 1, "is_active": True}],
        )
        import services.restore_api_client as svc
        with patch.object(svc, "db", fake_async_db):
            result = await run_restore_client("c1", USER)

        assert result["restored_status"] == "clientes_espera"
        assert fake_async_db.clients.docs[0]["status"] == "clientes_espera"

    async def test_cascata_processos_documentos_tarefas_rgpd(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        _seed(
            fake_async_db,
            client_doc={
                "id": "c1", "nome": "Ana", "is_deleted": True, "status": "eliminado",
                "previous_status": "fase_documental",
            },
            processes=[
                {"id": "p1", "client_id": "c1", "is_deleted": True,
                 "status": "eliminado", "previous_status": "fase_bancaria"},
            ],
            docs=[{"id": "d1", "process_id": "p1", "is_deleted": True, "deleted": True}],
            tasks=[{"id": "t1", "process_id": "p1", "is_deleted": True, "deleted": True}],
            rgpd=[{"id": "r1", "process_id": "p1", "is_deleted": True}],
            workflow=[{"id": "w1", "name": "fase_bancaria", "order": 8, "is_active": True}],
        )
        import services.restore_api_client as svc
        with patch.object(svc, "db", fake_async_db):
            result = await run_restore_client("c1", USER)

        assert result["restored_processes"] == ["p1"]
        proc = fake_async_db.processes.docs[0]
        assert proc["is_deleted"] is False
        assert proc["status"] == "fase_bancaria"
        assert proc["is_active"] is True
        assert fake_async_db.documents.docs[0]["is_deleted"] is False
        assert fake_async_db.tasks.docs[0]["is_deleted"] is False
        assert fake_async_db.rgpd_requests.docs[0]["is_deleted"] is False

    async def test_modelo_unificado_processo_como_cliente(self, fake_async_db, monkeypatch):
        """Cliente em `processes` (modelo unificado do client_delete.py)."""
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        _seed(
            fake_async_db,
            client_doc={},  # sem cliente em clients
            processes=[
                {"id": "c9", "client_id": "c9", "client_name": "Bruno",
                 "is_deleted": True, "status": "eliminado",
                 "previous_status": "clientes_espera"},
            ],
        )
        fake_async_db.clients.docs.clear()
        import services.restore_api_client as svc
        with patch.object(svc, "db", fake_async_db):
            result = await run_restore_client("c9", USER)

        assert result["success"] is True
        proc = fake_async_db.processes.docs[0]
        assert proc["is_deleted"] is False
        assert proc["status"] == "clientes_espera"

    async def test_regista_auditoria_client_restored(self, fake_async_db):
        _seed(
            fake_async_db,
            client_doc={"id": "c1", "nome": "Ana", "is_deleted": True,
                        "status": "eliminado", "previous_status": "fase_documental"},
        )
        import services.restore_api_client as svc
        with patch.object(svc, "db", fake_async_db):
            await run_restore_client("c1", USER)

        activities = fake_async_db.process_activities.docs
        assert any(a.get("type") == "client_restored" for a in activities)
