"""
Testes de integração — Checklist de Onboarding (Obrigatórios vs Opcionais).

Cobre a Fase 2 (ponto 6) do pacote "Fix: Resolve process 500/404 errors and
implement core onboarding backend logic":

- `generate_mandatory_document_requests` cria pedidos separados para a
  lista `documents` (Obrigatórios, source=mandatory_checklist) e
  `optional_documents` (Opcionais, source=mandatory_checklist_optional,
  is_optional=True), sem qualquer lista hardcoded — tudo vem de
  `SystemConfig.mandatory_documents`.
- `is_mandatory_checklist_complete` só bloqueia por documentos obrigatórios
  pendentes; documentos opcionais pendentes NUNCA bloqueiam.
"""
import uuid
from datetime import datetime, timezone

import pytest

from database import db
from services.portal_documents_notify import generate_mandatory_document_requests
from services.onboarding_mandatory_config import (
    is_mandatory_checklist_complete,
    count_pending_mandatory_requests,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def qa_client():
    from database import reset_db_connection
    reset_db_connection()
    client_id = str(uuid.uuid4())
    await db.clients.insert_one({
        "id": client_id,
        "nome": "Cliente Teste Checklist",
        "lead_status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield client_id
    await db.clients.delete_one({"id": client_id})
    await db.documents.delete_many({"client_id": client_id})


class TestOnboardingChecklistSplit:
    @pytest.mark.asyncio
    async def test_generates_mandatory_and_optional_lists_separately(self, qa_client):
        result = await generate_mandatory_document_requests(
            process_id=None,
            client_id=qa_client,
            requested_by="qa_test",
            requested_by_name="QA",
        )
        assert result["mandatory"]["created"] == 3
        assert result["optional"]["created"] == 3

        mandatory_docs = await db.documents.find(
            {"client_id": qa_client, "source": "mandatory_checklist"},
            {"_id": 0, "category": 1, "is_optional": 1},
        ).to_list(10)
        optional_docs = await db.documents.find(
            {"client_id": qa_client, "source": "mandatory_checklist_optional"},
            {"_id": 0, "category": 1, "is_optional": 1},
        ).to_list(10)

        assert {d["category"] for d in mandatory_docs} == {
            "identificacao", "extrato_bancario", "mapa_responsabilidades",
        }
        assert all(d["is_optional"] is False for d in mandatory_docs)

        assert {d["category"] for d in optional_docs} == {
            "recibo_vencimento", "irs", "declaracao_patronal",
        }
        assert all(d["is_optional"] is True for d in optional_docs)

    @pytest.mark.asyncio
    async def test_optional_pending_never_blocks_completion(self, qa_client):
        await generate_mandatory_document_requests(
            process_id=None, client_id=qa_client, requested_by="qa_test",
        )
        # Todos pendentes ainda (obrigatórios + opcionais) → incompleto
        assert await is_mandatory_checklist_complete(client_id=qa_client) is False

        # Cliente só submete os OBRIGATÓRIOS — opcionais ficam pendentes
        await db.documents.update_many(
            {"client_id": qa_client, "source": "mandatory_checklist"},
            {"$set": {"status": "RECEIVED"}},
        )

        assert await count_pending_mandatory_requests(client_id=qa_client) == 0
        assert await is_mandatory_checklist_complete(client_id=qa_client) is True

    @pytest.mark.asyncio
    async def test_idempotent_per_source(self, qa_client):
        """Chamar duas vezes não duplica pedidos (idempotência por source)."""
        await generate_mandatory_document_requests(process_id=None, client_id=qa_client)
        second = await generate_mandatory_document_requests(process_id=None, client_id=qa_client)
        assert second["mandatory"]["reason"] == "already_generated"
        assert second["optional"]["reason"] == "already_generated"

        total = await db.documents.count_documents({"client_id": qa_client})
        assert total == 6
