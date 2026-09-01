"""
Testes de integracao - Auditoria Stealth do Indice + Notificacao de
Atribuicao pos-indexacao.

Cobre a Fase 2 (pontos 4 e 5) do pacote "Fix: Resolve process 500/404
errors and implement core onboarding backend logic":

- log_mark_indexed_history: quando o actor que marcou a indexacao tem
  role "indexacao", NENHUM registo (incl. os sinteticos "Sistema" de
  salto de estado / limpeza do indexador) fica no historico do processo.
  Actores com outras roles (ex. admin) continuam a gerar historico normal.
- dual_auto_assign_on_pre_registo_transition: dispara notificacao
  (email + in-app) para consultor/mediador RECEM-atribuidos, e mantem o
  mesmo comportamento stealth (actor_role="indexacao" -> sem historico).
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from database import db
from services.process_indexing import log_mark_indexed_history
from services.process_assignment import dual_auto_assign_on_pre_registo_transition

pytestmark = pytest.mark.integration


@pytest.fixture
async def qa_process():
    from database import reset_db_connection
    reset_db_connection()
    process_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.processes.insert_one({
        "id": process_id,
        "process_number": 900001,
        "client_name": "QA Stealth Client",
        "status": "pre_registo",
        "is_active": True,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    })
    yield process_id
    await db.processes.delete_one({"id": process_id})
    await db.history.delete_many({"process_id": process_id})


class TestIndexStealthHistory:
    @pytest.mark.asyncio
    async def test_indexacao_actor_leaves_no_history(self, qa_process):
        index_user = {"id": "idx-qa", "name": "Indexador QA", "role": "indexacao"}
        await log_mark_indexed_history(
            qa_process, index_user,
            {"assigned_indexacao_id": "idx-qa", "indexacao_name": "Indexador QA"},
            current_status="pre_registo", next_status="novo_lead",
        )
        count = await db.history.count_documents({"process_id": qa_process})
        assert count == 0

    @pytest.mark.asyncio
    async def test_non_index_actor_still_logs_history(self, qa_process):
        admin_user = {"id": "adm-qa", "name": "Admin QA", "role": "admin"}
        await log_mark_indexed_history(
            qa_process, admin_user,
            {"assigned_indexacao_id": "idx-qa", "indexacao_name": "Indexador QA"},
            current_status="pre_registo", next_status="novo_lead",
        )
        count = await db.history.count_documents({"process_id": qa_process})
        # INDEXACAO_CONCLUIDA, DADOS_CONFIRMADOS_INDEXACAO, salto de estado,
        # limpeza do indexador = 4 entradas
        assert count == 4


class TestDualAssignNotification:
    @pytest.fixture
    async def qa_users(self):
        company_id = "qa-company-" + uuid.uuid4().hex[:8]
        consultor_id, mediador_id = str(uuid.uuid4()), str(uuid.uuid4())
        await db.users.insert_many([
            {"id": consultor_id, "name": "Consultor QA", "email": "consultor.qa@test.pt",
             "role": "consultor", "is_active": True, "company_id": company_id},
            {"id": mediador_id, "name": "Mediador QA", "email": "mediador.qa@test.pt",
             "role": "intermediario", "is_active": True, "company_id": company_id},
        ])
        yield company_id
        await db.users.delete_many({"id": {"$in": [consultor_id, mediador_id]}})

    @pytest.mark.asyncio
    async def test_notifies_newly_assigned_users_and_stays_silent_for_index_actor(
        self, qa_process, qa_users
    ):
        company_id = qa_users
        with patch(
            "services.notification_service.send_notification_with_preference_check",
            new_callable=AsyncMock,
        ) as mock_email, patch(
            "services.realtime_notifications.send_realtime_notification",
            new_callable=AsyncMock,
        ) as mock_inapp:
            result = await dual_auto_assign_on_pre_registo_transition(
                process_id=qa_process,
                company_id=company_id,
                indexador_user_id="idx-qa",
                actor_role="indexacao",
            )

        assert result.get("consultant_id")
        assert result.get("mediador_id")
        assert mock_email.await_count == 2
        assert mock_inapp.await_count == 2

        # Auditoria Stealth: actor era "indexacao" -> sem historico
        history_count = await db.history.count_documents({"process_id": qa_process})
        assert history_count == 0

    @pytest.mark.asyncio
    async def test_non_index_actor_dual_assign_logs_history(self, qa_process, qa_users):
        company_id = qa_users
        with patch(
            "services.notification_service.send_notification_with_preference_check",
            new_callable=AsyncMock,
        ), patch(
            "services.realtime_notifications.send_realtime_notification",
            new_callable=AsyncMock,
        ):
            await dual_auto_assign_on_pre_registo_transition(
                process_id=qa_process,
                company_id=company_id,
                indexador_user_id="adm-qa",
                actor_role="admin",
            )
        history_count = await db.history.count_documents({"process_id": qa_process})
        assert history_count == 1
