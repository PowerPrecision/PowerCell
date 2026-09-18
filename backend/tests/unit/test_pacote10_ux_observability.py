"""
PACOTE 10 — Testes unitários (fake_async_db, sem I/O Mongo real).

Cobertura:
1. Prevenção de clientes duplicados (409 Conflict com payload estruturado
   + exclusão de soft-deleted)
2. Estado de entrega do email de acesso (email_delivery_status: cliente
   + task_logs do monitor global)
3. Alerta crítico "Email de acesso não entregue" (services/alerts.py)
4. Lifecycle de deliver_registration_email (sent/failed/retry_scheduled)
5. Task logs da fila de emails (queue/execute/cancel → monitor global)
6. Task log de upload confirmado (document_direct_upload)

Correr: .venv/bin/python -m pytest tests/unit/test_pacote10_ux_observability.py -q
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ====================================================================
# 1) PREVENÇÃO DE CLIENTES DUPLICADOS (409)
# ====================================================================

class TestDuplicateClient409:
    """run_create_client devolve 409 estruturado; soft-delete não bloqueia."""

    def _make_user(self):
        return {"id": "u1", "email": "staff@powercell.pt", "role": "consultor"}

    async def _run_create(self, fake_async_db, *, nome="Ana Novo", email="ana@novo.pt", nif=None):
        from models.client import ClientCreate
        from services import client_crud as mod

        payload = ClientCreate(nome=nome, email=email, nif=nif, fonte="staff_created")
        with patch.object(mod, "db", fake_async_db), \
             patch.object(mod, "encrypt_client_data", lambda d: d), \
             patch.object(mod, "decrypt_client_data", lambda d: d), \
             patch.object(mod, "s3_service", MagicMock()), \
             patch.object(mod, "_send_portal_welcome_email_safe", AsyncMock()):
            return await mod.run_create_client(payload, self._make_user())

    async def test_duplicate_nif_returns_409_with_structured_detail(self, fake_async_db):
        from services import client_crud as mod
        from services.encryption import generate_nif_hash

        nif = "285739461"
        await fake_async_db.clients.insert_one({
            "id": "cli-existing",
            "nome": "João Existente",
            "dados_pessoais": {"nif": nif, "nif_hash": generate_nif_hash(nif)},
            "contacto": {"email": "joao@existente.pt"},
        })

        with pytest.raises(mod.HTTPException) as exc_info:
            await self._run_create(fake_async_db, email="outro@email.pt", nif=nif)

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert detail["existing_client_id"] == "cli-existing"
        assert detail["existing_client_name"] == "João Existente"
        assert "nif" in detail["matched_fields"]
        assert "email" not in detail["matched_fields"]
        assert "Já existe um cliente" in detail["message"]

    async def test_duplicate_email_returns_409(self, fake_async_db):
        from services import client_crud as mod
        from services.encryption import generate_email_hash

        email = "duplicado@x.pt"
        await fake_async_db.clients.insert_one({
            "id": "cli-email",
            "nome": "Maria Email",
            "contacto": {"email": email, "email_hash": generate_email_hash(email)},
        })

        with pytest.raises(mod.HTTPException) as exc_info:
            await self._run_create(fake_async_db, email=email, nif="987654321")

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["existing_client_id"] == "cli-email"
        assert "email" in exc_info.value.detail["matched_fields"]
        assert "nif" not in exc_info.value.detail["matched_fields"]

    async def test_soft_deleted_duplicate_does_not_block(self, fake_async_db):
        """Cliente eliminado (is_deleted) não bloqueia a recriação."""
        from services import client_crud as mod
        from services.encryption import generate_nif_hash

        nif = "111222333"
        await fake_async_db.clients.insert_one({
            "id": "cli-gone",
            "nome": "Eliminado",
            "is_deleted": True,
            "status": "eliminado",
            "dados_pessoais": {"nif": nif, "nif_hash": generate_nif_hash(nif)},
            "contacto": {"email": "gone@x.pt"},
        })

        client = await self._run_create(
            fake_async_db, email="novo@email.pt", nif=nif
        )
        # criado com sucesso — o duplicado soft-deleted não bloqueia
        assert client.nome == "Ana Novo"
        stored = await fake_async_db.clients.find_one({"id": client.id})
        assert stored is not None

    async def test_no_duplicate_creates_normally(self, fake_async_db):
        client = await self._run_create(fake_async_db, nif="777888999")
        assert client.id
        stored = await fake_async_db.clients.find_one({"id": client.id})
        assert stored["contacto"]["email"] == "ana@novo.pt"


# ====================================================================
# 2) ESTADO DE ENTREGA (email_delivery_status)
# ====================================================================

class TestEmailDeliveryStatus:
    """Registo persistente no cliente + task_logs (monitor global)."""

    async def test_failure_marks_client_and_creates_failed_task_log(self, fake_async_db):
        from services import email_delivery_status as mod
        from services import task_log_service as tls_mod

        await fake_async_db.clients.insert_one({
            "id": "cli-1", "nome": "Cliente", "created_by": "creator@x.pt",
        })
        await fake_async_db.users.insert_one({"id": "u-creator", "email": "creator@x.pt"})

        with patch.object(mod, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db):
            task_id = await mod.begin_portal_email_task(
                "cli-1", "cliente@x.pt", user_id=None, process_id="p1",
            )
            await mod.fail_portal_email_task(task_id, "cli-1", "SMTP down")

        # task_log criado com o user do criador (lookup por email)
        task = await fake_async_db.task_logs.find_one({"task_id": task_id})
        assert task["status"] == "failed"
        assert task["user_id"] == "u-creator"
        assert task["task_type"] == "EMAIL_SEND"
        assert "SMTP down" in task["error_message"]

        # estado persistido no cliente
        cli = await fake_async_db.clients.find_one({"id": "cli-1"})
        assert cli["portal_email_delivery"]["status"] == "failed"
        assert "SMTP down" in cli["portal_email_delivery"]["error"]

    async def test_success_marks_client_sent(self, fake_async_db):
        from services import email_delivery_status as mod
        from services import task_log_service as tls_mod

        await fake_async_db.clients.insert_one({"id": "cli-2", "nome": "C2"})

        with patch.object(mod, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db):
            task_id = await mod.begin_portal_email_task("cli-2", "c2@x.pt", user_id="u9")
            await mod.complete_portal_email_task(task_id, "cli-2")

        task = await fake_async_db.task_logs.find_one({"task_id": task_id})
        assert task["status"] == "completed"
        cli = await fake_async_db.clients.find_one({"id": "cli-2"})
        assert cli["portal_email_delivery"]["status"] == "sent"

    async def test_begin_task_without_user_returns_none(self, fake_async_db):
        from services import email_delivery_status as mod

        # sem client_id e sem user_id → sem task_log (best-effort)
        with patch.object(mod, "db", fake_async_db):
            task_id = await mod.begin_portal_email_task(None, "x@x.pt")
        assert task_id is None


# ====================================================================
# 3) ALERTA CRÍTICO "EMAIL DE ACESSO NÃO ENTREGUE"
# ====================================================================

class TestPortalEmailAlert:
    """check_portal_email_delivery_alert + integração em get_process_alerts."""

    async def test_alert_critical_when_client_delivery_failed(self, fake_async_db):
        from services import alerts as mod

        await fake_async_db.clients.insert_one({
            "id": "cli-fail",
            "contacto": {"email": "cliente@x.pt"},
            "portal_email_delivery": {"status": "failed", "error": "SMTP timeout"},
        })

        with patch.object(mod, "db", fake_async_db):
            alert = await mod.check_portal_email_delivery_alert({"client_id": "cli-fail"})

        assert alert["active"] is True
        assert alert["type"] == "portal_email_undelivered"
        assert alert["priority"] == "critical"
        assert alert["message"] == "Email de acesso não entregue"
        assert "SMTP timeout" in alert["details"]

    async def test_no_alert_when_delivery_ok_or_missing(self, fake_async_db):
        from services import alerts as mod

        await fake_async_db.clients.insert_one({
            "id": "cli-ok",
            "portal_email_delivery": {"status": "sent"},
        })
        with patch.object(mod, "db", fake_async_db):
            ok = await mod.check_portal_email_delivery_alert({"client_id": "cli-ok"})
            missing = await mod.check_portal_email_delivery_alert({"client_id": "cli-none"})
            no_client_field = await mod.check_portal_email_delivery_alert({"status": "em_analise"})

        assert ok["active"] is False
        assert missing["active"] is False
        assert no_client_field["active"] is False

    async def test_get_process_alerts_includes_portal_email_alert(self, fake_async_db):
        from services import alerts as mod

        process = {
            "id": "p1",
            "status": "pre_registo",
            "client_id": "cli-fail2",
        }
        await fake_async_db.clients.insert_one({
            "id": "cli-fail2",
            "contacto": {"email": "c@x.pt"},
            "portal_email_delivery": {"status": "failed", "error": "Resend 500"},
        })

        with patch.object(mod, "db", fake_async_db), \
             patch.object(mod, "check_age_alert", MagicMock(return_value={"active": False})), \
             patch.object(mod, "check_pre_approval_countdown", AsyncMock(return_value={"active": False})), \
             patch.object(mod, "check_document_expiry_alerts", AsyncMock(return_value=[])), \
             patch.object(mod, "check_property_documents", AsyncMock(return_value={"active": False})), \
             patch.object(mod, "check_valuation_alert", MagicMock(return_value={"active": False})):
            alerts = await mod.get_process_alerts(process)

        types = [a.get("type") for a in alerts]
        assert "portal_email_undelivered" in types
        portal_alert = next(a for a in alerts if a.get("type") == "portal_email_undelivered")
        assert portal_alert["priority"] == "critical"


# ====================================================================
# 4) LIFECYCLE DE deliver_registration_email
# ====================================================================

class TestDeliverRegistrationEmailLifecycle:
    """Envio directo → sent; falha total → failed; retry → retry_scheduled."""

    def _client_setup(self, fake_async_db):
        asyncio.get_event_loop()
        await_setup = fake_async_db
        return await_setup

    async def test_success_completes_task_and_marks_sent(self, fake_async_db):
        from services import client_portal_email as mod
        from services import email_delivery_status as eds
        from services import task_log_service as tls_mod

        await fake_async_db.clients.insert_one({"id": "cli-10", "created_by": "staff@x.pt"})
        await fake_async_db.users.insert_one({"id": "u10", "email": "staff@x.pt"})

        fake_tq = MagicMock()
        fake_tq.send_registration_email = AsyncMock(return_value=None)

        with patch.object(eds, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db), \
             patch("services.email.send_registration_confirmation", AsyncMock(return_value=True)), \
             patch("services.task_queue.task_queue", fake_tq):
            sent = await mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", portal_access_code="ABC-123",
                client_id="cli-10", user_id="u10", process_id="p10",
            )

        assert sent is True
        cli = await fake_async_db.clients.find_one({"id": "cli-10"})
        assert cli["portal_email_delivery"]["status"] == "sent"

        tasks = await fake_async_db.task_logs.find(
            {"user_id": "u10", "task_type": "EMAIL_SEND"}
        ).to_list(10)
        assert len(tasks) == 1
        assert tasks[0]["status"] == "completed"
        assert tasks[0]["process_id"] == "p10"
        # retry NUNCA foi tentado (envio directo ok)
        fake_tq.send_registration_email.assert_not_awaited()

    async def test_total_failure_marks_failed_and_creates_alert_source(self, fake_async_db):
        from services import client_portal_email as mod
        from services import email_delivery_status as eds
        from services import task_log_service as tls_mod

        await fake_async_db.clients.insert_one({"id": "cli-11", "created_by": "staff@x.pt"})
        await fake_async_db.users.insert_one({"id": "u10", "email": "staff@x.pt"})

        fake_tq = MagicMock()
        fake_tq.send_registration_email = AsyncMock(return_value=None)  # sem Redis/ARQ

        with patch.object(eds, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db), \
             patch("services.email.send_registration_confirmation", AsyncMock(return_value=False)), \
             patch("services.task_queue.task_queue", fake_tq):
            sent = await mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", client_id="cli-11", user_id="u10",
            )

        assert sent is False
        # falha DEFINITIVA registada no cliente (fonte do alerta crítico)
        cli = await fake_async_db.clients.find_one({"id": "cli-11"})
        assert cli["portal_email_delivery"]["status"] == "failed"
        # task_log failed visível no monitor global
        tasks = await fake_async_db.task_logs.find(
            {"user_id": "u10", "status": "failed"}
        ).to_list(10)
        assert len(tasks) == 1

    async def test_retry_enqueued_marks_retry_scheduled_without_alert(self, fake_async_db):
        from services import client_portal_email as mod
        from services import email_delivery_status as eds
        from services import task_log_service as tls_mod
        from services import alerts as alerts_mod

        await fake_async_db.clients.insert_one({"id": "cli-12", "created_by": "staff@x.pt"})
        await fake_async_db.users.insert_one({"id": "u10", "email": "staff@x.pt"})

        fake_tq = MagicMock()
        fake_tq.send_registration_email = AsyncMock(return_value="job-123")

        with patch.object(eds, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db), \
             patch("services.email.send_registration_confirmation", AsyncMock(return_value=False)), \
             patch("services.task_queue.task_queue", fake_tq):
            sent = await mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", client_id="cli-12", user_id="u10",
            )

        assert sent is False  # não entregue AGORA, mas retry está agendado
        cli = await fake_async_db.clients.find_one({"id": "cli-12"})
        assert cli["portal_email_delivery"]["status"] == "retry_scheduled"

        # NÃO gera alerta crítico (entrega ainda possível via worker)
        with patch.object(alerts_mod, "db", fake_async_db):
            alert = await alerts_mod.check_portal_email_delivery_alert(
                {"client_id": "cli-12"}
            )
        assert alert["active"] is False

        # task_log fica em processing (o worker fecha o ciclo)
        tasks = await fake_async_db.task_logs.find(
            {"user_id": "u10", "status": "processing"}
        ).to_list(10)
        assert len(tasks) == 1


# ====================================================================
# 5) TASK LOGS DA FILA DE EMAILS (webmail — monitor global)
# ====================================================================

class TestSendQueueTaskLogs:
    """queue/execute/cancel propagam ao task_logs (widget da topbar)."""

    def _record(self, **overrides):
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="Assunto",
            body="Corpo", body_html=None, cc_emails=None, process_id="p1",
            from_box="personal", from_email="u@x.pt", company_id="c1",
            created_by="u1", created_by_email="u1@x.pt", attachment_ids=[],
        )
        record.update(overrides)
        return record

    async def test_queue_creates_pending_task_log(self, fake_async_db):
        from services import email_send_queue as q
        from services import task_log_service as tls_mod

        record = self._record()
        schedule_mock = AsyncMock()

        with patch.object(q, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db), \
             patch.object(q, "schedule_pending_email_send", schedule_mock):
            response = await q.queue_email_send(record)

        assert response["queued"] is True
        # task_log pending criado e LIGADO ao registo pending
        task = await fake_async_db.task_logs.find_one({"user_id": "u1"})
        assert task["status"] == "pending"
        assert task["task_type"] == "EMAIL_SEND"
        assert task["metadata"]["send_id"] == record["id"]
        stored = await fake_async_db.pending_email_sends.find_one({"id": record["id"]})
        assert stored["task_log_id"] == task["task_id"]

    async def test_execute_success_completes_task_log(self, fake_async_db):
        from services import email_send_queue as q
        from services import task_log_service as tls_mod

        record = self._record()
        send_mock = AsyncMock(return_value={"success": True})

        with patch.object(q, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db), \
             patch.object(q, "send_email", send_mock):
            # criar com task_log (como o queue_email_send faz em produção)
            task_log_id = await q.attach_task_log_to_pending_record(record)
            record["task_log_id"] = task_log_id
            await fake_async_db.pending_email_sends.insert_one(dict(record))
            result = await q.execute_pending_email_send(record["id"])

        assert result["success"] is True
        task = await fake_async_db.task_logs.find_one({"task_id": task_log_id})
        assert task["status"] == "completed"
        assert task["progress"] == 100

    async def test_execute_failure_fails_task_log(self, fake_async_db):
        from services import email_send_queue as q
        from services import task_log_service as tls_mod

        record = self._record()
        send_mock = AsyncMock(return_value={"success": False, "error": "SMTP refused"})

        with patch.object(q, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db), \
             patch.object(q, "send_email", send_mock):
            task_log_id = await q.attach_task_log_to_pending_record(record)
            record["task_log_id"] = task_log_id
            await fake_async_db.pending_email_sends.insert_one(dict(record))
            result = await q.execute_pending_email_send(record["id"])

        assert result["success"] is False
        task = await fake_async_db.task_logs.find_one({"task_id": task_log_id})
        assert task["status"] == "failed"
        assert "SMTP refused" in task["error_message"]
        # registo pending mantido para auditoria
        stored = await fake_async_db.pending_email_sends.find_one({"id": record["id"]})
        assert stored["status"] == "failed"

    async def test_cancel_cancels_task_log(self, fake_async_db):
        from services import email_send_queue as q
        from services import task_log_service as tls_mod

        record = self._record()

        with patch.object(q, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db):
            task_log_id = await q.attach_task_log_to_pending_record(record)
            record["task_log_id"] = task_log_id
            await fake_async_db.pending_email_sends.insert_one(dict(record))
            cancel = await q.cancel_pending_email_send(
                record["id"], {"id": "u1", "role": "consultor"}
            )

        assert cancel["cancelled"] is True
        task = await fake_async_db.task_logs.find_one({"task_id": task_log_id})
        assert task["status"] == "cancelled"
        assert "Cancelada" in task["progress_message"] or "cancelado" in task["progress_message"].lower()

    async def test_execute_without_task_log_degrades_gracefully(self, fake_async_db):
        """Registo sem task_log (p.ex. criado antes do P10) envia na mesma."""
        from services import email_send_queue as q

        record = self._record()
        send_mock = AsyncMock(return_value={"success": True})

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "send_email", send_mock):
            await fake_async_db.pending_email_sends.insert_one(dict(record))
            result = await q.execute_pending_email_send(record["id"])

        assert result["success"] is True


# ====================================================================
# 7) MERGE DOS TASK_LOGS NO GET /tasks/active (widget da topbar)
# ====================================================================

class TestTasksActiveMerge:
    """run_get_active_background_tasks agrega task_logs + background_jobs."""

    async def test_task_logs_appear_in_unified_active_list(self, fake_async_db):
        from services import task_api_background as mod
        from services import task_log_service as tls_mod

        # job background (formato BackgroundJobService) + task_log da fila
        from datetime import datetime, timezone

        now_iso = datetime.now(timezone.utc).isoformat()
        await fake_async_db.background_jobs.insert_one({
            "id": "job-1", "user_email": "me@x.pt", "status": "processing",
            "type": "pdf_gen", "name": "Relatório PDF", "created_at": now_iso,
        })
        await fake_async_db.task_logs.insert_one({
            "id": "doc-1", "task_id": "task_abc123", "user_id": "u-me",
            "task_type": "EMAIL_SEND", "status": "pending",
            "title": "Envio de Email", "description": "Assunto: Olá",
            "progress": 0, "progress_message": "Aguardando execução...",
            "process_id": None, "process_name": None, "result_url": None,
            "result_data": None, "error_message": None, "metadata": {},
            "created_at": now_iso, "started_at": None,
            "completed_at": None, "acknowledge_required": True,
            "acknowledged_at": None,
        })

        user = {"id": "u-me", "email": "me@x.pt"}
        with patch.object(mod, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db):
            result = await mod.run_get_active_background_tasks(user)

        # ambas as fontes presentes e contabilizadas
        assert result["active_count"] == 2
        ids = {t["task_id"] for t in result["tasks"]}
        assert "task_abc123" in ids
        assert "job-1" in ids
        # task_log mapeado com o formato do widget
        email_task = next(t for t in result["tasks"] if t["task_id"] == "task_abc123")
        assert email_task["task_type"] == "EMAIL_SEND"
        assert email_task["status"] == "pending"
        assert email_task["title"] == "Envio de Email"

    async def test_failed_task_log_counts_as_unacknowledged(self, fake_async_db):
        from datetime import datetime, timezone, timedelta
        from services import task_api_background as mod
        from services import task_log_service as tls_mod

        recent = datetime.now(timezone.utc)
        await fake_async_db.task_logs.insert_one({
            "id": "doc-2", "task_id": "task_fail9", "user_id": "u-me",
            "task_type": "EMAIL_SEND", "status": "failed",
            "title": "Envio de Email", "description": None,
            "progress": 0, "progress_message": None, "process_id": None,
            "process_name": None, "result_url": None, "result_data": None,
            "error_message": "SMTP down", "metadata": {},
            "created_at": (recent - timedelta(minutes=2)).isoformat(),
            "started_at": None,
            "completed_at": (recent - timedelta(minutes=1)).isoformat(),
            "acknowledge_required": True,
            "acknowledged_at": None,
        })

        with patch.object(mod, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db):
            result = await mod.run_get_active_background_tasks(
                {"id": "u-me", "email": "me@x.pt"}
            )

        assert result["active_count"] == 0
        assert result["completed_unacknowledged"] == 1
        failed_task = result["tasks"][0]
        assert failed_task["status"] == "failed"
        assert failed_task["priority"] == "alta"
        assert failed_task["error_message"] == "SMTP down"

    async def test_acknowledge_and_cancel_route_to_task_logs(self, fake_async_db):
        from services import task_api_background as mod
        from services import task_log_service as tls_mod

        await fake_async_db.task_logs.insert_one({
            "id": "doc-3", "task_id": "task_ack1", "user_id": "u-me",
            "task_type": "EMAIL_SEND", "status": "pending",
            "title": "Envio de Email", "description": None,
            "progress": 0, "progress_message": None, "process_id": None,
            "process_name": None, "result_url": None, "result_data": None,
            "error_message": None, "metadata": {},
            "created_at": "2026-01-01T11:00:00", "started_at": None,
            "completed_at": None, "acknowledge_required": True,
            "acknowledged_at": None,
        })

        user = {"id": "u-me", "email": "me@x.pt"}
        with patch.object(mod, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db):
            cancel = await mod.run_cancel_background_task("task_ack1", user)

        assert cancel["success"] is True
        task = await fake_async_db.task_logs.find_one({"task_id": "task_ack1"})
        assert task["status"] == "cancelled"


# ====================================================================
# 6) TASK LOG DE UPLOAD CONFIRMADO (document_direct_upload)
# ====================================================================

class TestConfirmUploadTaskLog:
    """run_confirm_upload cria task_log DOCUMENT_UPLOAD concluído."""

    async def test_confirm_upload_creates_completed_task_log(self, fake_async_db):
        from services import document_direct_upload as mod
        from services import task_log_service as tls_mod

        await fake_async_db.processes.insert_one({
            "id": "p-up", "client_name": "Cliente Upload",
        })

        fake_s3 = MagicMock()
        fake_s3.file_exists = MagicMock(return_value=True)
        fake_s3.get_presigned_url = MagicMock(return_value="https://s3/url")
        fake_s3.get_file_content = MagicMock(return_value=None)

        fake_bg = MagicMock()

        with patch.object(mod, "db", fake_async_db), \
             patch.object(tls_mod, "db", fake_async_db), \
             patch.object(mod, "s3_service", fake_s3), \
             patch.object(mod, "_triage_category_with_ai", AsyncMock(return_value=("Outros", None, None))), \
             patch.object(mod, "log_history", AsyncMock()), \
             patch.object(mod, "_auto_fulfill_portal_request", AsyncMock(return_value={"fulfilled": 0})):
            response = await mod.run_confirm_upload(
                {
                    "process_id": "p-up",
                    "file_key": "Documentação Clientes/Cliente/ficheiro.pdf",
                    "original_filename": "ficheiro.pdf",
                    "category": "Outros",
                },
                background_tasks=fake_bg,
                user={"id": "u-up", "email": "up@x.pt"},
            )

        assert response["success"] is True
        # task_log criado e já concluído (upload terminou quando confirm corre)
        task = await fake_async_db.task_logs.find_one({"user_id": "u-up"})
        assert task["task_type"] == "DOCUMENT_UPLOAD"
        assert task["status"] == "completed"
        assert "ficheiro.pdf" in task["title"]
        assert task["process_id"] == "p-up"
        assert task["metadata"]["s3_path"].endswith("ficheiro.pdf")
