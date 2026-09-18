"""
PACOTE 9 — Testes unitários (fake_async_db, sem I/O Mongo).

Cobertura:
1. S3 mapping na criação (helper + hooks em process_create/client_assign)
2. Guards de sobreposição + auto-atribuição ao criador (effective role)
3. Undo Send (fila pending_email_sends + cancel + claim atómico)
4. Cleanup script (padrão \\btest + queries transversais + soft-delete set)
5. Backfill S3 (filtros com valores "lixo" + cobertura processes)
6. Toggle "Indexado" (set-indexed true/false + permissões)

Correr: .venv/bin/python -m pytest tests/unit/test_pacote9_infra_ux_fixes.py -q
"""
import asyncio
import re
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ====================================================================
# 1) S3 MAPPING NA CRIAÇÃO
# ====================================================================

class TestS3MappingOnCreate:
    """services/s3_mapping_on_create.py — pasta + mapeamento na criação."""

    async def test_process_gets_s3_folder_and_client_backfilled(self, fake_async_db):
        from services import s3_mapping_on_create as mod

        await fake_async_db.processes.insert_one({"id": "proc-1", "client_name": "João Silva"})
        await fake_async_db.clients.insert_one({"id": "cli-1", "nome": "João Silva"})  # sem s3_folder

        fake_s3 = MagicMock()
        fake_s3.ensure_client_folder_mapping = MagicMock(
            return_value={"success": True, "s3_folder": "Documentação Clientes/Joao_Silva",
                          "created": True, "reused_existing": False}
        )

        with patch.object(mod, "db", fake_async_db), patch.object(mod, "s3_service", fake_s3):
            outcome = await mod.ensure_s3_mapping_on_process_create(
                process_id="proc-1",
                client_id="cli-1",
                client_name="João Silva",
                second_client_name=None,
            )

        assert outcome["success"] is True
        assert outcome["s3_folder"] == "Documentação Clientes/Joao_Silva"
        assert outcome["client_backfilled"] is True

        proc = await fake_async_db.processes.find_one({"id": "proc-1"})
        cli = await fake_async_db.clients.find_one({"id": "cli-1"})
        assert proc["s3_folder"] == "Documentação Clientes/Joao_Silva"
        assert cli["s3_folder"] == "Documentação Clientes/Joao_Silva"

        # ensure chamado em thread (boto3 síncrono) com os nomes certos
        fake_s3.ensure_client_folder_mapping.assert_called_once_with(
            "proc-1", "João Silva", None, None,
        )

    async def test_client_with_valid_folder_is_not_overwritten(self, fake_async_db):
        from services import s3_mapping_on_create as mod

        await fake_async_db.processes.insert_one({"id": "proc-2"})
        await fake_async_db.clients.insert_one(
            {"id": "cli-2", "s3_folder": "Documentação Clientes/Existente"}
        )

        fake_s3 = MagicMock()
        fake_s3.ensure_client_folder_mapping = MagicMock(
            return_value={"success": True, "s3_folder": "Documentação Clientes/Outra",
                          "created": False, "reused_existing": True}
        )

        with patch.object(mod, "db", fake_async_db), patch.object(mod, "s3_service", fake_s3):
            outcome = await mod.ensure_s3_mapping_on_process_create(
                process_id="proc-2", client_id="cli-2", client_name="Ana",
            )

        assert outcome["client_backfilled"] is False
        cli = await fake_async_db.clients.find_one({"id": "cli-2"})
        assert cli["s3_folder"] == "Documentação Clientes/Existente"

    async def test_s3_failure_degrades_gracefully(self, fake_async_db):
        """Falha S3 nunca rebenta a criação — devolve success False."""
        from services import s3_mapping_on_create as mod

        await fake_async_db.processes.insert_one({"id": "proc-3"})

        fake_s3 = MagicMock()
        fake_s3.ensure_client_folder_mapping = MagicMock(side_effect=RuntimeError("S3 down"))

        with patch.object(mod, "db", fake_async_db), patch.object(mod, "s3_service", fake_s3):
            outcome = await mod.ensure_s3_mapping_on_process_create(
                process_id="proc-3", client_id=None, client_name="Ana",
            )

        assert outcome["success"] is False
        assert outcome["s3_folder"] is None

    async def test_hook_is_wired_in_staff_process_create(self, fake_async_db):
        """persist_and_finalize_staff_create chama o helper S3 após o insert."""
        from services import process_create
        from services import s3_mapping_on_create as s3mod

        bundle = {
            "process_id": "proc-9",
            "process_number": 42,
            "now": datetime.now(timezone.utc).isoformat(),
            "is_lead": True,  # saltar auto-atribuição de indexador
            "skip_index": False,
            "initial_status": "pre_registo",
            "client_id": "cli-9",
            "client_name": "João Silva",
            "client_email": "",  # saltar email de boas-vindas
            "process_doc": {"id": "proc-9", "client_name": "João Silva", "status": "pre_registo"},
            "second_client_id": None,
            "process_type": "credito_habitacao",
        }

        class _StubResponse(dict):
            def __init__(self, **kw):
                super().__init__(**kw)

        ensure_mock = AsyncMock(return_value={"success": True, "s3_folder": "X", "process_persisted": True})

        with patch.object(process_create, "db", fake_async_db), \
             patch.object(process_create, "create_default_portal_documents", AsyncMock()), \
             patch("services.redis_cache.invalidate_stats_cache", AsyncMock()), \
             patch("services.trello_service.sync_process_to_trello", AsyncMock()), \
             patch.object(s3mod, "ensure_s3_mapping_on_process_create", ensure_mock):
            result = await process_create.persist_and_finalize_staff_create(
                bundle,
                user={"id": "u1", "name": "Consultor", "email": "c@x.pt", "role": "consultor"},
                encrypt_fn=lambda d: d,
                decrypt_fn=lambda d: d,
                log_history_fn=AsyncMock(),
                broadcast_fn=AsyncMock(),
                response_cls=_StubResponse,
            )

        assert result["id"] == "proc-9"
        stored = await fake_async_db.processes.find_one({"id": "proc-9"})
        assert stored is not None
        ensure_mock.assert_awaited_once()
        # chamado com o id do processo e o nome plain do cliente
        kwargs = ensure_mock.await_args.kwargs
        assert kwargs["process_id"] == "proc-9"
        assert kwargs["client_name"] == "João Silva"

    async def test_client_assign_uses_real_folder_mapping(self, fake_async_db):
        """run_assign_client_to_user cria a estrutura S3 real (não só o path)."""
        from services import client_assign
        from services import s3_mapping_on_create as s3mod

        await fake_async_db.clients.insert_one({
            "id": "cli-a",
            "nome": "Maria Santos",
            "contacto": {"email": "maria@x.pt", "telefone": ""},
            "dados_pessoais": {},
            "assigned_to": None,
        })
        await fake_async_db.users.insert_one({
            "id": "u-consultor", "name": "Consultor Um", "role": "consultor", "email": "c@x.pt",
        })
        await fake_async_db.workflow_statuses.insert_one({"name": "fase1", "order": 1})

        ensure_mock = AsyncMock(
            return_value={"success": True, "s3_folder": "Documentação Clientes/Maria_Santos"}
        )

        with patch.object(client_assign, "db", fake_async_db), \
             patch.object(client_assign, "decrypt_client_data", lambda c: c), \
             patch.object(client_assign, "get_next_process_number", AsyncMock(return_value=7)), \
             patch("services.process_service.encrypt_sensitive_data", lambda d: d), \
             patch("services.process_assignment.assign_to_indexer",
                   AsyncMock(return_value=(True, {"assigned": True, "indexacao_name": "Idx"}, "ok"))), \
             patch.object(s3mod, "ensure_s3_mapping_on_process_create", ensure_mock):
            result = await client_assign.run_assign_client_to_user(
                "cli-a",
                user={"id": "u-consultor", "name": "Consultor Um", "role": "consultor",
                      "email": "c@x.pt"},
            )

        assert result["success"] is True
        stored = await fake_async_db.processes.find_one({"client_id": "cli-a"})
        assert stored is not None
        # doc tem o fallback gravado E o mapeamento real foi garantido via helper
        assert stored.get("s3_folder")
        ensure_mock.assert_awaited_once()
        assert ensure_mock.await_args.kwargs["process_id"] == stored["id"]
        # campos multi-assignee preenchidos (Pacote 9)
        assert stored.get("assigned_consultor_ids") == ["u-consultor"]
        assert stored.get("consultor_names") == ["Consultor Um"]


# ====================================================================
# 2) GUARDS DE ATRIBUIÇÃO + AUTOR DO CRIADOR
# ====================================================================

class TestAssignmentGuards:

    def test_creator_role_assignment_uses_effective_role(self):
        """Multi-perfil: admin com perfil ACTIVO consultor fica atribuído."""
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc,
            {"id": "u1", "name": "Zé", "role": "admin", "effective_role": "consultor"},
        )
        assert doc["assigned_consultor_id"] == "u1"
        assert doc["consultor_id"] == "u1"
        # PACOTE 9 — plural em sincronia com o singular (multi-assignee)
        assert doc["assigned_consultor_ids"] == ["u1"]
        assert doc["consultor_names"] == ["Zé"]

    def test_creator_role_assignment_intermediario_plural(self):
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc, {"id": "u2", "name": "Ana", "role": "intermediario"},
        )
        assert doc["assigned_mediador_id"] == "u2"
        assert doc["assigned_mediador_ids"] == ["u2"]
        assert doc["mediador_names"] == ["Ana"]
        assert "assigned_consultor_id" not in doc

    def test_creator_without_staff_role_is_not_assigned(self):
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc, {"id": "u3", "name": "Admin", "role": "admin", "effective_role": "admin"},
        )
        assert "assigned_consultor_id" not in doc
        assert "assigned_mediador_id" not in doc

    async def test_least_busy_guard_covers_multi_assignee_list(self, fake_async_db):
        """Processo com apenas assigned_consultor_ids NÃO recebe 2º consultor."""
        from services import process_assignment as pa

        await fake_async_db.processes.insert_one({
            "id": "p-guard",
            "assigned_consultor_id": None,
            "consultant_id": None,
            "assigned_consultor_ids": ["u-existing"],
            "consultor_names": ["Existente"],
        })

        with patch.object(pa, "db", fake_async_db):
            success, data, msg = await pa.assign_to_least_busy_consultant("p-guard")

        assert success is True
        assert data.get("assigned_consultor_id") == "u-existing"
        assert "já tem consultor" in msg
        # nenhum utilizador consultado — nada atribuído por cima
        assert fake_async_db.users.docs == []

    async def test_dual_auto_assign_guard_covers_assigned_fields(self, fake_async_db):
        """dual_auto_assign respeita assigned_consultor_id/assigned_mediador_id."""
        from services import process_assignment as pa

        await fake_async_db.processes.insert_one({
            "id": "p-dual",
            "status": "pre_registo",
            "consultant_id": None,
            "assigned_consultor_id": "u-consultor",
            "assigned_consultor_ids": ["u-consultor"],
            "mediador_id": None,
            "assigned_mediador_id": None,
            "assigned_mediador_ids": [],
        })
        await fake_async_db.users.insert_one({"id": "u-consultor", "name": "Consultor X"})

        with patch.object(pa, "db", fake_async_db), \
             patch("services.history.log_history", AsyncMock()):
            result = await pa.dual_auto_assign_on_pre_registo_transition("p-dual")

        # consultor existente mantido; mediador NÃO é injectado (sem users)
        assert result.get("consultant_id") == "u-consultor"
        assert result.get("consultant_name") == "Consultor X"
        assert "mediador_id" not in result
        # update_one nunca gravou novas atribuições
        stored = await fake_async_db.processes.find_one({"id": "p-dual"})
        assert stored.get("assigned_mediador_id") is None

    async def test_client_assign_guard_blocks_non_manager_reassignment(self, fake_async_db):
        """Consultor não pode (re)atribuir cliente já atribuído a outro (409)."""
        from fastapi import HTTPException
        from services import client_assign

        await fake_async_db.clients.insert_one({
            "id": "cli-guard",
            "nome": "Guard",
            "contacto": {"email": "g@x.pt"},
            "assigned_to": "u-other",
        })
        await fake_async_db.users.insert_one({"id": "u-other", "name": "Outro", "role": "consultor"})

        with patch.object(client_assign, "db", fake_async_db), \
             patch.object(client_assign, "decrypt_client_data", lambda c: c):
            with pytest.raises(HTTPException) as exc:
                await client_assign.run_assign_client_to_user(
                    "cli-guard",
                    user={"id": "u-me", "name": "Eu", "role": "consultor", "email": "me@x.pt"},
                )
        assert exc.value.status_code == 409

    async def test_client_assign_guard_allows_manager_reassignment(self, fake_async_db):
        """Admin pode re-atribuir deliberadamente (sem 409)."""
        from services import client_assign
        from services import s3_mapping_on_create as s3mod

        await fake_async_db.clients.insert_one({
            "id": "cli-mgr",
            "nome": "Maria",
            "contacto": {"email": "maria@x.pt"},
            "assigned_to": "u-old",
        })
        await fake_async_db.users.insert_one(
            {"id": "u-new", "name": "Novo", "role": "consultor", "email": "n@x.pt"}
        )

        with patch.object(client_assign, "db", fake_async_db), \
             patch.object(client_assign, "decrypt_client_data", lambda c: c), \
             patch.object(client_assign, "get_next_process_number", AsyncMock(return_value=9)), \
             patch("services.process_service.encrypt_sensitive_data", lambda d: d), \
             patch("services.process_assignment.assign_to_indexer",
                   AsyncMock(return_value=(True, {"assigned": True}, "ok"))), \
             patch.object(s3mod, "ensure_s3_mapping_on_process_create", AsyncMock()):
            result = await client_assign.run_assign_client_to_user(
                "cli-mgr",
                user={"id": "u-admin", "name": "Admin", "role": "admin", "email": "a@x.pt"},
                assign_to_user_id="u-new",
                create_process=False,
            )

        assert result["success"] is True
        cli = await fake_async_db.clients.find_one({"id": "cli-mgr"})
        assert cli["assigned_to"] == "u-new"

    async def test_client_create_auto_assigns_to_consultor_creator(self, fake_async_db):
        """PACOTE 9: cliente criado por consultor fica assigned_to dele."""
        from models.client import ClientCreate
        from services import client_crud

        user = {
            "id": "u-consultor-9",
            "name": "Consultor",
            "email": "consultor@x.pt",
            "role": "admin",  # role primária DIFERENTE do perfil activo
            "effective_role": "consultor",
        }

        fake_s3 = MagicMock()
        fake_s3.ensure_client_folder_mapping = MagicMock(
            return_value={"success": True, "s3_folder": "Documentação Clientes/Novo",
                          "created": True}
        )

        payload = ClientCreate(
            nome="Novo Cliente",
            email="novo@x.pt",
            skip_welcome_email=True,
        )

        with patch.object(client_crud, "db", fake_async_db), \
             patch.object(client_crud, "s3_service", fake_s3), \
             patch("services.background_tasks.spawn_background_task", MagicMock()):
            created = await client_crud.run_create_client(payload, user)

        stored = await fake_async_db.clients.find_one({"id": created.id})
        # auto-atribuição ao criador (pelo perfil ACTIVO, não pelo JWT)
        assert stored["assigned_to"] == "u-consultor-9"
        assert stored["assigned_at"]
        # created_by mantém a convenção email (compatibilidade)
        assert stored["created_by"] == "consultor@x.pt"

    def test_orphan_leads_query_matches_id_or_email(self):
        """Fix do mismatch: leads visíveis por created_by id OU email."""
        from services.my_clients_api_helpers import build_orphan_leads_query

        q = build_orphan_leads_query("u-1", "consultor@x.pt")
        or_clause = next(
            (c for c in q["$and"] if isinstance(c, dict) and "$or" in c), None
        )
        assert or_clause is not None
        assert {"created_by": "u-1"} in or_clause["$or"]
        assert {"created_by": "consultor@x.pt"} in or_clause["$or"]
        # soft-delete e sem processo continuam a ser condições
        assert {"is_deleted": {"$ne": True}} in q["$and"]


# ====================================================================
# 3) UNDO SEND (fila + cancel + claim atómico)
# ====================================================================

class TestUndoSendQueue:

    def test_build_pending_send_record_shape(self):
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S",
            body="B", body_html=None, cc_emails=None, process_id="p1",
            from_box="personal", from_email="geral@x.pt", company_id="c1",
            created_by="u1", created_by_email="u1@x.pt", attachment_ids=["att1"],
        )
        assert record["status"] == q.STATUS_PENDING
        assert record["undo_window_seconds"] == q.UNDO_SEND_WINDOW_SECONDS
        assert record["id"]
        # send_after = created_at + janela
        created = datetime.fromisoformat(record["created_at"])
        after = datetime.fromisoformat(record["send_after"])
        delta = (after - created).total_seconds()
        assert q.UNDO_SEND_WINDOW_SECONDS - 1 <= delta <= q.UNDO_SEND_WINDOW_SECONDS + 1
        assert record["attachment_ids"] == ["att1"]
        assert record["from_email"] == "geral@x.pt"

    async def test_queue_email_send_inserts_and_schedules(self, fake_async_db):
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, process_id=None, from_box="personal",
            from_email="u@x.pt", company_id=None, created_by="u1",
            created_by_email="u1@x.pt", attachment_ids=[],
        )
        schedule_mock = AsyncMock()

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "schedule_pending_email_send", schedule_mock):
            response = await q.queue_email_send(record)

        assert response["queued"] is True
        assert response["send_id"] == record["id"]
        assert response["undo_window_seconds"] == q.UNDO_SEND_WINDOW_SECONDS
        stored = await fake_async_db.pending_email_sends.find_one({"id": record["id"]})
        assert stored is not None
        schedule_mock.assert_awaited_once_with(record["id"])

    async def test_execute_claims_and_sends_then_deletes(self, fake_async_db):
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, process_id="p1", from_box="personal",
            from_email="u@x.pt", company_id="c1", created_by="u1",
            created_by_email="u1@x.pt", attachment_ids=[],
        )
        await fake_async_db.pending_email_sends.insert_one(dict(record))
        send_mock = AsyncMock(return_value={"success": True})

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "send_email", send_mock):
            result = await q.execute_pending_email_send(record["id"])

        assert result == {"executed": True, "success": True, "reason": "sent"}
        # envio com os campos do registo
        kwargs = send_mock.await_args.kwargs
        assert kwargs["to_emails"] == ["a@b.pt"]
        assert kwargs["from_email"] == "u@x.pt"
        assert kwargs["active_company_id"] == "c1"
        # registo apagado após sucesso (nada fica em pending)
        assert await fake_async_db.pending_email_sends.find_one({"id": record["id"]}) is None

    async def test_execute_after_cancel_never_sends(self, fake_async_db):
        from services import email_send_queue as q

        send_mock = AsyncMock(return_value={"success": True})
        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, process_id=None, from_box=None,
            from_email=None, company_id=None, created_by="u1",
            created_by_email=None, attachment_ids=[],
        )
        await fake_async_db.pending_email_sends.insert_one(dict(record))

        with patch.object(q, "db", fake_async_db):
            # cancel ANTES da janela expirar
            cancel = await q.cancel_pending_email_send(
                record["id"], {"id": "u1", "role": "consultor"}
            )
        assert cancel["cancelled"] is True
        assert cancel["draft"]["to_emails"] == ["a@b.pt"]

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "send_email", send_mock):
            result = await q.execute_pending_email_send(record["id"])

        assert result["executed"] is False
        assert result["reason"] == "not_found"
        send_mock.assert_not_awaited()

    async def test_execute_is_idempotent_when_already_claimed(self, fake_async_db):
        """Claim atómico: segunda execução (ARQ + timer) não duplica envio."""
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, process_id=None, from_box=None,
            from_email=None, company_id=None, created_by="u1",
            created_by_email=None, attachment_ids=[],
        )
        # já reclamado por outro executor
        record["status"] = q.STATUS_CLAIMED
        await fake_async_db.pending_email_sends.insert_one(dict(record))
        send_mock = AsyncMock(return_value={"success": True})

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "send_email", send_mock):
            result = await q.execute_pending_email_send(record["id"])

        assert result["executed"] is False
        assert result["reason"] == "status_claimed"
        send_mock.assert_not_awaited()

    async def test_execute_marks_failed_on_smtp_error(self, fake_async_db):
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, process_id=None, from_box=None,
            from_email=None, company_id=None, created_by="u1",
            created_by_email=None, attachment_ids=[],
        )
        await fake_async_db.pending_email_sends.insert_one(dict(record))

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "send_email", AsyncMock(return_value={"success": False, "error": "SMTP auth fail"})):
            result = await q.execute_pending_email_send(record["id"])

        assert result["executed"] is True
        assert result["success"] is False
        stored = await fake_async_db.pending_email_sends.find_one({"id": record["id"]})
        assert stored["status"] == q.STATUS_FAILED
        assert "SMTP" in stored["error"]

    async def test_cancel_guards(self, fake_async_db):
        from fastapi import HTTPException
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, process_id=None, from_box=None,
            from_email=None, company_id=None, created_by="u-author",
            created_by_email=None, attachment_ids=[],
        )
        await fake_async_db.pending_email_sends.insert_one(dict(record))

        with patch.object(q, "db", fake_async_db):
            # 404 — não existe
            with pytest.raises(HTTPException) as e404:
                await q.cancel_pending_email_send("inexistente", {"id": "u-author"})
            assert e404.value.status_code == 404

            # 403 — outro utilizador
            with pytest.raises(HTTPException) as e403:
                await q.cancel_pending_email_send(
                    record["id"], {"id": "u-estranho", "role": "consultor"}
                )
            assert e403.value.status_code == 403

            # admin pode cancelar por outro utilizador
            cancel_admin = await q.cancel_pending_email_send(
                record["id"], {"id": "u-admin", "role": "admin"}
            )
            assert cancel_admin["cancelled"] is True

        # 409 — janela expirada (claimed)
        record2 = dict(record)
        record2["id"] = "send-claimed"
        record2["status"] = q.STATUS_CLAIMED
        await fake_async_db.pending_email_sends.insert_one(record2)
        with patch.object(q, "db", fake_async_db):
            with pytest.raises(HTTPException) as e409:
                await q.cancel_pending_email_send(
                    "send-claimed", {"id": "u-author", "role": "consultor"}
                )
            assert e409.value.status_code == 409

    async def test_run_send_email_queues_instead_of_immediate_send(self, fake_async_db):
        """POST /emails/send devolve {queued, send_id, undo_window} e NÃO envia já."""
        from models.email import EmailSendRequest
        from services import email_process_crud as crud
        from services import email_send_queue as q

        payload = EmailSendRequest(
            to_emails=["destino@x.pt"], subject="Assunto", body="Corpo",
        )
        request = MagicMock()
        request.headers = {}  # sem x-company-id

        user = {"id": "u1", "email": "u1@x.pt", "role": "consultor"}

        send_mock = AsyncMock(return_value={"success": True})
        schedule_mock = AsyncMock()

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "schedule_pending_email_send", schedule_mock), \
             patch.object(q, "send_email", send_mock), \
             patch("services.email_config_resolver.resolve_email_config_for_sync",
                   AsyncMock(return_value={"email_address": "geral@x.pt"})), \
             patch("services.auth.get_active_company_id_async", AsyncMock(return_value=None)):
            response = await crud.run_send_email(payload, request, user, account="personal")

        # resposta de fila, não de envio
        assert response["success"] is True
        assert response["queued"] is True
        assert response["send_id"]
        assert response["undo_window_seconds"] == q.UNDO_SEND_WINDOW_SECONDS
        # NADA foi enviado à rede neste pedido
        send_mock.assert_not_awaited()
        # registo pending gravado com os campos resolvidos
        stored = await fake_async_db.pending_email_sends.find_one({"id": response["send_id"]})
        assert stored is not None
        assert stored["to_emails"] == ["destino@x.pt"]
        assert stored["from_email"] == "geral@x.pt"
        assert stored["created_by"] == "u1"

    async def test_worker_task_registered(self):
        """A task ARQ do undo send está registada no worker."""
        from worker.tasks import TASK_FUNCTIONS
        from worker.config import WorkerSettings

        from worker.tasks import send_pending_webmail_email_task
        assert send_pending_webmail_email_task in TASK_FUNCTIONS
        assert send_pending_webmail_email_task in WorkerSettings.functions

    async def test_cancel_route_contract(self):
        """A rota /emails/{id}/cancel-send existe e é um thin stub."""
        from routes.emails import router

        paths = {getattr(r, "path", ""): [m.upper() for m in (getattr(r, "methods", None) or [])]
                 for r in router.routes}
        assert "/emails/{send_id}/cancel-send" in paths
        assert "POST" in paths["/emails/{send_id}/cancel-send"]


# ====================================================================
# 4) CLEANUP SCRIPT (padrão + queries + soft-delete)
# ====================================================================

class TestCleanupScript:

    def test_pattern_matches_teste_but_not_false_positives(self):
        from scripts.cleanup_prod_test_data import TEST_PATTERN

        pattern = TEST_PATTERN["$regex"]
        flags = re.IGNORECASE if "i" in (TEST_PATTERN.get("$options") or "") else 0
        matches = lambda s: bool(re.search(pattern, s, flags))

        # match: "teste" (pt-pt), "test", variações
        assert matches("Cliente de Teste")
        assert matches("test@exemplo.pt")
        assert matches("Processo TESTE 123")
        assert matches("teste final")
        assert matches("user test 1")
        assert matches("testes")
        assert matches("cliente test123")
        assert matches("user_test")
        # NÃO match: falsos positivos comuns
        assert not matches("atestado médico")
        assert not matches("testamento")
        assert not matches("testemunho")
        assert not matches("latest updates")
        assert not matches("Contestação de valores")
        assert not matches("protesto")
        assert not matches("contest")

    def test_transversal_queries_cover_requested_collections(self):
        from scripts.cleanup_prod_test_data import (
            build_client_test_query,
            build_process_test_query,
            build_property_lead_test_query,
            build_activity_test_query,
            build_task_test_query,
        )

        q = build_client_test_query()
        for field in ("contacto.email", "email", "nome", "notas"):
            assert any(field in clause for clause in q["$or"])

        pq = build_process_test_query(["cli-1"])
        for field in ("client_email", "client_name", "process_type", "notes", "observations"):
            assert any(field in clause for clause in pq["$or"])
        assert {"client_id": {"$in": ["cli-1"]}} in pq["$or"]

        lq = build_property_lead_test_query()
        for field in ("title", "notes", "client_name", "url"):
            assert any(field in clause for clause in lq["$or"])

        aq = build_activity_test_query(["p1"])
        assert any("comment" in clause for clause in aq["$or"])
        assert {"process_id": {"$in": ["p1"]}} in aq["$or"]

        tq = build_task_test_query(["p1"])
        for field in ("title", "description"):
            assert any(field in clause for clause in tq["$or"])

    def test_soft_delete_set_shape(self):
        from scripts.cleanup_prod_test_data import build_soft_delete_set, DELETED_BY_TAG

        now = "2026-02-01T00:00:00+00:00"
        s = build_soft_delete_set(now, previous_status="fase1")
        assert s["is_deleted"] is True
        assert s["deleted"] is True
        assert s["deleted_at"] == now
        assert s["deleted_by"] == DELETED_BY_TAG
        assert s["previous_status"] == "fase1"

        # sem previous_status — campo omitido
        s2 = build_soft_delete_set(now)
        assert "previous_status" not in s2


# ====================================================================
# 5) BACKFILL S3 (filtros actualizados)
# ====================================================================

class TestBackfillS3Script:

    def test_missing_query_catches_garbage_values(self):
        from scripts.backfill_s3_mappings import _missing_s3_folder_query

        q = _missing_s3_folder_query()
        or_clauses = q["$or"]
        assert {"s3_folder": {"$exists": False}} in or_clauses
        assert {"s3_folder": None} in or_clauses
        assert {"s3_folder": ""} in or_clauses
        # PACOTE 9: valores "lixo" contam como sem mapeamento
        assert {"s3_folder": {"$in": ["undefined", "null", "none", ""]}} in or_clauses

    def test_has_garbage_s3_folder(self):
        from scripts.backfill_s3_mappings import _has_garbage_s3_folder

        assert _has_garbage_s3_folder("undefined") is True
        assert _has_garbage_s3_folder("null") is True
        assert _has_garbage_s3_folder("None") is True
        assert _has_garbage_s3_folder("") is True
        assert _has_garbage_s3_folder(None) is True
        assert _has_garbage_s3_folder(123) is True
        assert _has_garbage_s3_folder("Documentação Clientes/Joao") is False

    def test_not_deleted_query_excludes_soft_deleted(self):
        from scripts.backfill_s3_mappings import _not_deleted_query

        q = _not_deleted_query()
        assert q == {"is_deleted": {"$ne": True}, "status": {"$ne": "eliminado"}}

    async def test_backfill_covers_processes_collection(self, fake_async_db):
        """O backfill processa TAMBÉM processos (não só clients)."""
        from scripts import backfill_s3_mappings as bf

        await fake_async_db.processes.insert_one({
            "id": "p-bf", "client_name": "João Silva", "s3_folder": "undefined",
        })
        await fake_async_db.clients.insert_one({
            "id": "c-bf", "nome": "Maria", "s3_folder": None,
        })

        fake_s3 = MagicMock()
        fake_s3.ensure_client_folder_mapping = MagicMock(
            return_value={"success": True, "s3_folder": "Documentação Clientes/Resolvido",
                          "created": True}
        )

        proc_stats = await bf.backfill_collection(
            fake_async_db, fake_s3, "processes", label="Processo", dry_run=False,
        )
        cli_stats = await bf.backfill_collection(
            fake_async_db, fake_s3, "clients", label="Cliente", dry_run=False,
        )

        assert proc_stats["total"] == 1
        assert proc_stats["restored"] == 1
        assert cli_stats["total"] == 1
        assert cli_stats["restored"] == 1

        proc = await fake_async_db.processes.find_one({"id": "p-bf"})
        cli = await fake_async_db.clients.find_one({"id": "c-bf"})
        assert proc["s3_folder"] == "Documentação Clientes/Resolvido"
        assert cli["s3_folder"] == "Documentação Clientes/Resolvido"
        assert proc["s3_mapping_backfilled_by"] == "backfill_s3_mappings"


# ====================================================================
# 6) TOGGLE "INDEXADO"
# ====================================================================

class TestIndexedToggle:

    def test_unindex_update_set_shape(self):
        from services.process_indexing import build_unindex_update_set

        now = "2026-02-01T00:00:00+00:00"
        s = build_unindex_update_set({"id": "u1", "name": "Zé"}, now)
        assert s["is_indexed"] is False
        assert s["unindexed_by"] == "u1"
        assert s["unindexed_by_name"] == "Zé"
        assert s["updated_at"] == now
        # não mexe no status do workflow (reversão de fase é manual)
        assert "status" not in s

    async def test_toggle_off_reverts_flag_with_history(self, fake_async_db):
        from services import process_indexing as pi

        await fake_async_db.processes.insert_one({
            "id": "p-toggle", "process_number": 12, "status": "fase2",
            "client_name": "João", "is_indexed": True,
        })

        log_history_mock = AsyncMock()
        broadcast_mock = AsyncMock()

        with patch.object(pi, "db", fake_async_db), \
             patch("services.history.log_history", log_history_mock):
            result = await pi.run_set_process_indexed_flag(
                "p-toggle",
                user={"id": "u-idx", "name": "Indexador", "email": "i@x.pt"},
                is_indexed=False,
                user_role="indexacao",
                all_roles=[],
                broadcast_fn=broadcast_mock,
            )

        assert result["success"] is True
        assert result["is_indexed"] is False
        stored = await fake_async_db.processes.find_one({"id": "p-toggle"})
        assert stored["is_indexed"] is False
        assert stored["unindexed_by"] == "u-idx"
        # status do workflow MANTIDO
        assert stored["status"] == "fase2"
        # histórico + broadcast WS
        log_history_mock.assert_awaited()
        broadcast_mock.assert_awaited_once()

    async def test_toggle_off_when_not_indexed_is_idempotent(self, fake_async_db):
        from services import process_indexing as pi

        await fake_async_db.processes.insert_one({
            "id": "p-no", "status": "fase1", "is_indexed": False,
        })

        with patch.object(pi, "db", fake_async_db):
            result = await pi.run_set_process_indexed_flag(
                "p-no",
                user={"id": "u1", "name": "Z", "email": "z@x.pt"},
                is_indexed=False,
                user_role="admin",
                all_roles=[],
                broadcast_fn=AsyncMock(),
            )

        assert result["success"] is True
        assert result["is_indexed"] is False

    async def test_toggle_permission_denied_for_consultor(self, fake_async_db):
        from fastapi import HTTPException
        from services import process_indexing as pi

        with patch.object(pi, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await pi.run_set_process_indexed_flag(
                    "p-x",
                    user={"id": "u1", "name": "C", "email": "c@x.pt"},
                    is_indexed=False,
                    user_role="consultor",
                    all_roles=[],
                    broadcast_fn=AsyncMock(),
                )
        assert exc.value.status_code == 403

    async def test_toggle_on_delegates_to_canonical_mark_indexed(self, fake_async_db):
        from services import process_indexing as pi

        mark_mock = AsyncMock(return_value={"success": True, "is_indexed": True})

        with patch.object(pi, "run_mark_process_indexed", mark_mock):
            result = await pi.run_set_process_indexed_flag(
                "p-on",
                user={"id": "u1", "name": "Z", "email": "z@x.pt"},
                is_indexed=True,
                user_role="indexacao",
                all_roles=[],
                broadcast_fn=AsyncMock(),
            )

        assert result["is_indexed"] is True
        mark_mock.assert_awaited_once()
        assert mark_mock.await_args.args[0] == "p-on"

    async def test_set_indexed_route_registered(self):
        from routes.processes import router

        paths = {
            getattr(r, "path", ""): [m.upper() for m in (getattr(r, "methods", None) or [])]
            for r in router.routes
        }
        assert "/processes/{process_id}/set-indexed" in paths
        assert "POST" in paths["/processes/{process_id}/set-indexed"]
