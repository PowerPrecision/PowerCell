"""Testes unitários dos 5 fixes de regras de negócio/segurança (E2E, Set 2026).

Sem I/O de Mongo (convenção tests/unit — fake_async_db do conftest +
patches do `db` nos módulos do fluxo):

1. Email de boas-vindas no pré-registo (envio directo prioritário —
   a fila ARQ `send_registration_email_task` não tinha consumidor).
2. Privacidade das notificações (payload estritamente para os atribuídos).
3. Lógica de quantidade no Portal (completed só com uploaded_count >=
   expected_count).
4. Transição dinâmica do workflow (sem strings hardcoded de fases).
5. Segurança de visibilidade de documentos (pré-indexação: só
   INDEX/ADMIN/atribuídos).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.conftest import FakeAsyncDatabase

pytestmark = pytest.mark.asyncio


# ====================================================================
# BUG 1 — Email de boas-vindas no pré-registo
# ====================================================================
class TestBug1WelcomeEmail:
    async def test_deliver_registration_email_sends_directly_first(self):
        """Envio DIRECTO prioritário — a task queue só é usada em falha."""
        with patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=True),
        ) as mock_send, patch(
            "services.task_queue.task_queue"
        ) as mock_tq:
            from services.client_portal_email import deliver_registration_email

            sent = await deliver_registration_email(
                client_email="novo@cliente.pt",
                client_name="Novo Cliente",
                portal_access_code="ABC123",
                client_id="cli-1",
            )

        assert sent is True
        mock_send.assert_awaited_once()
        # A fila ARQ NÃO é usada quando o envio directo tem sucesso
        mock_tq.send_registration_email.assert_not_called()

    async def test_deliver_registration_email_queue_retry_on_failure(self):
        """Falha do envio directo → retry via task queue (ARQ)."""
        with patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=False),
        ), patch(
            "services.task_queue.task_queue"
        ) as mock_tq:
            mock_tq.send_registration_email = AsyncMock(return_value="job-123")
            from services.client_portal_email import deliver_registration_email

            sent = await deliver_registration_email(
                client_email="novo@cliente.pt",
                client_name="Novo Cliente",
                client_id="cli-1",
            )

        assert sent is False
        mock_tq.send_registration_email.assert_awaited_once()

    async def test_welcome_email_from_process_uses_client_access_code(self):
        """O email partindo do processo lê/gera o portal_access_code do cliente."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append(
            {"id": "cli-9", "portal_access_code": "CODE-99"}
        )

        with patch("services.process_create.db", fake_db), patch(
            "services.client_portal_email.deliver_registration_email",
            new=AsyncMock(return_value=True),
        ) as mock_deliver:
            from services.process_create import (
                send_portal_welcome_email_from_process,
            )

            await send_portal_welcome_email_from_process(
                client_id="cli-9",
                client_email="novo@cliente.pt",
                client_name="Novo Cliente",
            )

        mock_deliver.assert_awaited_once()
        assert mock_deliver.await_args.kwargs["portal_access_code"] == "CODE-99"

    async def test_welcome_email_generates_missing_access_code(self):
        """Cliente sem portal_access_code → gera e persiste um novo código."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append({"id": "cli-10"})

        generated = {"code": None}

        async def fake_deliver(**kwargs):
            generated["code"] = kwargs.get("portal_access_code")
            return True

        with patch("services.process_create.db", fake_db), patch(
            "services.client_portal_email.deliver_registration_email",
            new=fake_deliver,
        ):
            from services.process_create import (
                send_portal_welcome_email_from_process,
            )

            await send_portal_welcome_email_from_process(
                client_id="cli-10",
                client_email="x@y.pt",
                client_name="Cliente",
            )

        assert generated["code"], "deveria ter gerado um código novo"
        stored = await fake_db.clients.find_one({"id": "cli-10"})
        assert stored["portal_access_code"] == generated["code"]

    async def test_arq_worker_registers_email_tasks(self):
        """As tasks de email enfileiradas pelo task_queue têm handler no worker ARQ."""
        from worker.config import WorkerSettings
        from worker.tasks import (
            TASK_FUNCTIONS,
            send_email_task,
            send_registration_email_task,
        )

        fn_names = [fn.__name__ for fn in WorkerSettings.functions]
        assert "send_registration_email_task" in fn_names
        assert "send_email_task" in fn_names
        task_fn_names = [fn.__name__ for fn in TASK_FUNCTIONS]
        assert "send_registration_email_task" in task_fn_names
        assert "send_email_task" in task_fn_names
        assert send_registration_email_task is not None
        assert send_email_task is not None

    async def test_spawn_background_task_keeps_strong_reference(self):
        """spawn_background_task guarda referência forte até a task terminar."""
        import asyncio

        from services.background_tasks import (
            pending_background_tasks,
            spawn_background_task,
        )

        started = asyncio.Event()
        release = asyncio.Event()

        async def work():
            started.set()
            await release.wait()

        before = pending_background_tasks()
        task = spawn_background_task(work(), name="unit-test-task")
        await started.wait()
        assert pending_background_tasks() == before + 1
        assert task in asyncio.all_tasks() or not task.done()

        release.set()
        await task
        assert pending_background_tasks() == before


# ====================================================================
# BUG 2 — Privacidade das notificações
# ====================================================================
class TestBug2NotificationPrivacy:
    async def test_collect_process_assignee_ids_gathers_all_roles(self):
        from services.realtime_notifications import _collect_process_assignee_ids

        process = {
            "consultor_id": "c-1",
            "assigned_consultor_id": "c-2",
            "assigned_consultor_ids": ["c-3", "c-2"],
            "mediador_id": "m-1",
            "assigned_mediador_id": "m-2",
            "assigned_mediador_ids": ["m-3"],
            "assigned_indexacao_id": "i-1",
        }
        ids = _collect_process_assignee_ids(process)
        assert ids == {"c-1", "c-2", "c-3", "m-1", "m-2", "m-3", "i-1"}

    async def test_status_change_notifies_only_assignees_not_admins(self):
        """Mudança de fase: payload enviado ESTRITAMENTE aos atribuídos (menos o autor)."""
        from services import realtime_notifications as rt

        process = {
            "id": "proc-1",
            "client_name": "Cliente Teste",
            "consultor_id": "c-1",
            "assigned_mediador_id": "m-1",
            "assigned_indexacao_id": "i-1",
        }
        sent_to: list = []

        async def fake_send(user_id, **kwargs):
            sent_to.append(user_id)

        # Armadilha: se o código voltar a queryar admins, este mock rebenta
        trap_db = MagicMock()
        trap_db.users.find = MagicMock(
            side_effect=AssertionError("não deve queryar admins")
        )

        with patch.object(rt, "send_realtime_notification", fake_send), \
             patch.object(rt, "db", trap_db):
            await rt.notify_process_status_change(
                process=process,
                old_status="a",
                new_status="b",
                new_status_label="B",
                changed_by={"id": "c-1", "name": "Consultor"},
            )

        assert set(sent_to) == {"m-1", "i-1"}  # c-1 é o autor → excluído

    async def test_assigned_action_notifies_only_assignees(self):
        """Notificação de atribuição — apenas os atribuídos, nunca admins globais."""
        from services import realtime_notifications as rt

        process = {
            "id": "proc-2",
            "client_name": "Cliente",
            "assigned_consultor_ids": ["c-9"],
        }
        sent_to: list = []

        async def fake_send(user_id, **kwargs):
            sent_to.append(user_id)

        # Armadilha: se o código voltar a queryar admins, rebenta aqui
        trap_db = MagicMock()
        trap_db.processes.find_one = AsyncMock(return_value=dict(process))
        trap_db.users.find = MagicMock(
            side_effect=AssertionError("não deve queryar admins")
        )

        with patch.object(rt, "send_realtime_notification", fake_send), \
             patch.object(rt, "db", trap_db), \
             patch.object(rt, "manager", MagicMock(broadcast=AsyncMock())):
            await rt.notify_process_update(
                process_id="proc-2",
                action="assigned",
                actor_name="Sistema",
            )

        assert sent_to == ["c-9"]


# ====================================================================
# BUG 3 — Lógica de quantidade no Portal
# ====================================================================
class TestBug3PortalDocumentCounts:
    async def test_parse_expected_count_variants(self):
        from services.document_portal_counts import parse_expected_count

        assert parse_expected_count({"quantity": 3}) == 3
        assert parse_expected_count({"expected_count": 5}) == 5
        assert parse_expected_count({}) == 1
        assert parse_expected_count(None) == 1
        assert parse_expected_count({"quantity": "3"}) == 3
        assert parse_expected_count({"quantity": 0}) == 1  # inválido → 1
        assert parse_expected_count({"quantity": -2}) == 1
        assert parse_expected_count({"quantity": "abc"}) == 1

    async def test_partial_upload_keeps_request_pending_until_count(self):
        """Pedido de 3 recibos: 1º upload mantém REQUESTED; só o 3º conclui."""
        from services.document_portal_counts import apply_portal_request_upload

        fake_db = FakeAsyncDatabase()
        fake_db.documents.docs.append(
            {
                "id": "req-1",
                "process_id": "proc-1",
                "status": "REQUESTED",
                "expected_count": 3,
                "attached_files": [],
            }
        )

        with patch("services.document_portal_counts.db", fake_db):
            # 1º upload → parcial
            r1 = await apply_portal_request_upload(
                {"id": "req-1", "process_id": "proc-1"},
                set_fields={"filename": "recibo1.pdf"},
                file_entry={"file_id": "f1", "filename": "recibo1.pdf"},
                now="2026-09-09T00:00:00",
            )
            doc = await fake_db.documents.find_one({"id": "req-1"})
            assert r1["completed"] is False
            assert r1["uploaded_count"] == 1
            assert doc["status"] == "REQUESTED"  # continua pendente
            assert doc["uploaded_count"] == 1

            # 2º upload → ainda parcial
            r2 = await apply_portal_request_upload(
                {"id": "req-1", "process_id": "proc-1"},
                set_fields={"filename": "recibo2.pdf"},
                file_entry={"file_id": "f2", "filename": "recibo2.pdf"},
                now="2026-09-09T00:00:01",
            )
            assert r2["completed"] is False
            assert r2["uploaded_count"] == 2

            # 3º upload → contagem atingida → RECEIVED
            r3 = await apply_portal_request_upload(
                {"id": "req-1", "process_id": "proc-1"},
                set_fields={"filename": "recibo3.pdf"},
                file_entry={"file_id": "f3", "filename": "recibo3.pdf"},
                now="2026-09-09T00:00:02",
            )
            doc = await fake_db.documents.find_one({"id": "req-1"})
            assert r3["completed"] is True
            assert r3["uploaded_count"] == 3
            assert doc["status"] == "RECEIVED"
            # histórico preservado (PACOTE DE)
            assert len(doc["attached_files"]) == 3

    async def test_legacy_request_without_expected_count_completes_first(self):
        """Pedidos legados (sem expected_count) → default 1 (comportamento anterior)."""
        from services.document_portal_counts import apply_portal_request_upload

        fake_db = FakeAsyncDatabase()
        fake_db.documents.docs.append(
            {"id": "req-legacy", "process_id": "p", "status": "REQUESTED"}
        )

        with patch("services.document_portal_counts.db", fake_db):
            result = await apply_portal_request_upload(
                {"id": "req-legacy", "process_id": "p"},
                set_fields={"filename": "doc.pdf"},
                file_entry={"file_id": "f1"},
                now="now",
            )
        assert result["completed"] is True
        assert result["expected_count"] == 1

    async def test_mandatory_requests_store_expected_count(self):
        """Geração de pedidos grava expected_count lido do item (quantity)."""
        from services.portal_documents_notify import (
            _generate_document_requests_for_list,
        )

        fake_db = FakeAsyncDatabase()
        items = [
            {"name": "Recibos", "category": "recibo_vencimento", "quantity": 3},
            {"name": "CC", "category": "identificacao"},
        ]

        with patch("services.portal_documents_notify.db", fake_db):
            result = await _generate_document_requests_for_list(
                items,
                source="mandatory_checklist",
                is_optional=False,
                process_id="proc-9",
                client_id=None,
                requested_by=None,
                requested_by_name="Sistema",
            )

        assert result["created"] == 2
        recibo = await fake_db.documents.find_one({"custom_label": "Recibos"})
        cc = await fake_db.documents.find_one({"custom_label": "CC"})
        assert recibo["expected_count"] == 3
        assert cc["expected_count"] == 1  # default

    async def test_serialize_portal_document_exposes_counts(self):
        from services.document_portal_request import serialize_portal_document

        payload = serialize_portal_document(
            {
                "id": "req-1",
                "process_id": "p",
                "status": "REQUESTED",
                "expected_count": 3,
                "attached_files": [{"file_id": "a"}, {"file_id": "b"}],
            }
        )
        assert payload["expected_count"] == 3
        assert payload["uploaded_count"] == 2


# ====================================================================
# BUG 4 — Transição dinâmica do workflow (sem strings hardcoded)
# ====================================================================
class TestBug4DynamicWorkflowTransition:
    _PIPELINE = ["pre_registo", "clientes_espera", "fase_documental", "entradas"]

    def _patch_pipeline(self, pipeline):
        return patch(
            "services.process_indexing.load_workflow_status_pipeline",
            new=AsyncMock(return_value=pipeline),
        )

    async def test_pre_registo_goes_to_first_real_phase(self):
        from services.process_assignment import _resolve_dynamic_indexer_status

        with self._patch_pipeline(self._PIPELINE):
            target = await _resolve_dynamic_indexer_status(
                {"status": "pre_registo"}
            )
        assert target == "clientes_espera"  # 1ª fase REAL (não pre_registo)

    async def test_mid_pipeline_advances_to_next_sequential_phase(self):
        from services.process_assignment import _resolve_dynamic_indexer_status

        with self._patch_pipeline(["clientes_espera", "fase_documental", "entradas"]):
            target = await _resolve_dynamic_indexer_status(
                {"status": "fase_documental"}
            )
        # Fase seguinte lida da CONFIG (renomear fases já não quebra)
        assert target == "entradas"

    async def test_last_phase_stays(self):
        from services.process_assignment import _resolve_dynamic_indexer_status

        with self._patch_pipeline(["a", "b"]):
            target = await _resolve_dynamic_indexer_status({"status": "b"})
        assert target == "b"

    async def test_unknown_status_falls_back_to_first_real(self):
        from services.process_assignment import _resolve_dynamic_indexer_status

        with self._patch_pipeline(["nova_fase_1", "nova_fase_2"]):
            target = await _resolve_dynamic_indexer_status(
                {"status": "fase_antiga_removida"}
            )
        assert target == "nova_fase_1"

    async def test_empty_workflow_keeps_current_status(self):
        from services.process_assignment import _resolve_dynamic_indexer_status

        with self._patch_pipeline([]):
            target = await _resolve_dynamic_indexer_status(
                {"status": "qualquer"}
            )
        assert target == "qualquer"

    async def test_assign_to_indexer_uses_dynamic_status(self):
        """assign_to_indexer(update_status=True) aplica a fase dinâmica (não fase_documental hardcoded)."""
        from services import process_assignment as pa

        fake_db = FakeAsyncDatabase()
        fake_db.processes.docs.append({"id": "p-1", "status": "clientes_espera"})

        # Coleção de users mockada (find com query deep-role complexa)
        indexador = {"id": "idx-1", "name": "Indexador", "email": "i@x.pt", "role": "indexacao"}
        users_coll = MagicMock()
        users_coll.find.return_value.to_list = AsyncMock(return_value=[indexador])
        fake_db._collections["users"] = users_coll

        with patch.object(pa, "db", fake_db), \
             self._patch_pipeline(["clientes_espera", "tratamento_indice"]), \
             patch.object(pa, "_count_active_processes_for_indexer", AsyncMock(return_value=0)), \
             patch("services.history.log_history", AsyncMock()), \
             patch(
                 "services.notification_service.send_notification_with_preference_check",
                 AsyncMock(return_value=True),
             ), \
             patch(
                 "services.realtime_notifications.send_realtime_notification",
                 AsyncMock(),
             ):
            success, data, msg = await pa.assign_to_indexer("p-1", update_status=True)

        assert success is True
        assert data["assigned"] is True
        # A fase aplicada é a dinâmica (próxima da config), NÃO "fase_documental"
        assert data["status"] == "tratamento_indice"
        proc = await fake_db.processes.find_one({"id": "p-1"})
        assert proc["status"] == "tratamento_indice"
        assert proc["workflow_step"] == "tratamento_indice"
        assert proc["assigned_indexacao_id"] == "idx-1"


# ====================================================================
# BUG 5 — Segurança de visibilidade de documentos (pré-indexação)
# ====================================================================
class TestBug5DocumentVisibility:
    def _process(self, **overrides):
        base = {
            "id": "p-1",
            "status": "clientes_espera",
            "is_indexed": False,
            "assigned_consultor_id": "c-1",
        }
        base.update(overrides)
        return base

    async def test_roles_with_access_before_indexing(self):
        from services.document_visibility import user_can_view_process_documents

        process = self._process()
        assert user_can_view_process_documents(
            {"id": "i-9", "role": "indexacao"}, process
        ) is True
        assert user_can_view_process_documents(
            {"id": "a-9", "role": "admin"}, process
        ) is True
        assert user_can_view_process_documents(
            {"id": "i-8", "role": "index"}, process
        ) is True
        # Utilizador atribuído (qualquer papel)
        assert user_can_view_process_documents(
            {"id": "c-1", "role": "consultor"}, process
        ) is True
        # Consultor NÃO atribuído → bloqueado
        assert user_can_view_process_documents(
            {"id": "c-777", "role": "consultor"}, process
        ) is False
        assert user_can_view_process_documents(
            {"id": "d-1", "role": "diretor"}, process
        ) is False

    async def test_after_indexing_visibility_open(self):
        from services.document_visibility import user_can_view_process_documents

        process = self._process(is_indexed=True)
        assert user_can_view_process_documents(
            {"id": "c-777", "role": "consultor"}, process
        ) is True

    async def test_assert_raises_403_for_unrelated_consultor(self):
        from fastapi import HTTPException

        from services.document_visibility import assert_can_view_process_documents

        with pytest.raises(HTTPException) as exc_info:
            await assert_can_view_process_documents(
                {"id": "c-777", "role": "consultor", "name": "Zé"},
                self._process(),
            )
        assert exc_info.value.status_code == 403
        assert "indexação" in exc_info.value.detail.lower()

    async def test_assert_by_id_404_when_process_missing(self):
        from fastapi import HTTPException

        from services.document_visibility import (
            assert_can_view_process_documents_by_id,
        )

        fake_db = FakeAsyncDatabase()
        with patch("services.document_visibility.db", fake_db), pytest.raises(
            HTTPException
        ) as exc_info:
            await assert_can_view_process_documents_by_id(
                {"id": "u", "role": "consultor"}, "nope"
            )
        assert exc_info.value.status_code == 404

    async def test_assert_by_id_allows_indexer_pre_indexing(self):
        from services.document_visibility import (
            assert_can_view_process_documents_by_id,
        )

        fake_db = FakeAsyncDatabase()
        fake_db.processes.docs.append(self._process(id="p-1"))
        with patch("services.document_visibility.db", fake_db):
            process = await assert_can_view_process_documents_by_id(
                {"id": "i-9", "role": "indexacao"}, "p-1"
            )
        assert process["id"] == "p-1"
