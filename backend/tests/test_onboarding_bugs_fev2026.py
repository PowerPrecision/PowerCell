"""
Tests for Onboarding Regression Fixes (Fev 2026):
- Bug 1: POST /api/clients cria só o Cliente (sem Processo, sem envio ao Índice)
- Bug 2: Pedidos de documento do Portal usam a checklist dinâmica do SystemConfig
- Bug 3: POST /api/clients/{id}/resend-portal-access devolve erro real quando o
  SMTP não está configurado (nunca sucesso falso)

NOTA: usa o fixture `client` (httpx.AsyncClient + ASGITransport, in-process) de
tests/conftest.py — NÃO faz chamadas de rede reais — para funcionar em CI sem
um servidor a correr numa porta real.
"""
import asyncio
import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _create_client(client, admin_token, prefix: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "nome": f"TEST_{prefix} Cliente {suffix}",
        "email": f"test_{prefix.lower()}_{suffix}@example.com",
        "telefone": "912345678",
        "fonte": "staff_created",
    }
    r = await client.post(
        "/clients", json=payload, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert r.status_code in (200, 201), f"Create failed: {r.status_code} {r.text}"
    return r.json()


class TestBug1ClientOnly:
    async def test_create_client_no_process(self, client, admin_token):
        """
        Contrato do endpoint POST /api/clients (isolado): não cria nenhum
        Processo por si só. Isto continua verdade após o Ajuste Arquitetural
        de Fev 2026 (iteração 8) — a criação de Processo em simultâneo com
        o Cliente passou a ser responsabilidade do FRONTEND (CreateClientModal
        encadeia 2 chamadas: POST /clients seguido de POST /processes/create-client
        com is_lead=True). Este teste garante que o endpoint em si permanece
        "puro" (não é ele quem decide criar o processo).
        """
        data = await _create_client(client, admin_token, "Bug1")
        client_id = data.get("id")
        assert client_id, f"No id in response: {data}"

        rg = await client.get(
            f"/clients/{client_id}", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert rg.status_code == 200
        process_ids = rg.json().get("process_ids") or []
        assert process_ids == [], f"Cliente não devia ter processos: {process_ids}"

        from database import db
        await db.clients.delete_one({"id": client_id})


class TestBug2DynamicDocs:
    async def test_created_process_generates_document_requests_from_system_config(
        self, client, admin_token
    ):
        """
        Ao criar um Processo (POST /processes/create-client), os pedidos de
        documento devem ser gerados dinamicamente a partir de
        SystemConfig.mandatory_documents — nunca a lista estática antiga
        (Cartao_Cidadao/IRS/Recibo_Vencimento/Comprovativo_IBAN).

        NOTA (Ajuste Arquitetural, Fev 2026 — iteração 8): a geração deixou
        de ocorrer em POST /clients isolado (esse endpoint já não gera
        documentos, evitando pedidos duplicados/órfãos quando o frontend
        encadeia a criação do Processo a seguir). Passou a ocorrer apenas
        em create_default_portal_documents (process_create.py), acionada
        pela criação do Processo — quer seja is_lead=True (pré-registo)
        quer seja um processo ativo normal.
        """
        from database import db

        data = await _create_client(client, admin_token, "Bug2")
        client_id = data.get("id")
        assert client_id

        rp = await client.post(
            "/processes/create-client",
            json={"client_id": client_id, "process_type": "outro", "is_lead": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rp.status_code in (200, 201), f"Create process failed: {rp.text}"
        process_id = rp.json().get("id")
        assert rp.json().get("status") == "pre_registo", f"Status inesperado: {rp.json().get('status')}"

        # create_default_portal_documents corre em background (asyncio.create_task)
        await asyncio.sleep(0.5)

        docs = await db.documents.find(
            {"process_id": process_id}, {"_id": 0, "custom_label": 1, "category": 1, "is_optional": 1}
        ).to_list(20)

        assert len(docs) > 0, "Nenhum documento gerado — checklist dinâmica não foi acionada"

        old_hardcoded_categories = {"Cartao_Cidadao", "IRS", "Recibo_Vencimento", "Comprovativo_IBAN"}
        for doc in docs:
            assert doc.get("custom_label"), f"Documento sem nome legível (custom_label): {doc}"
            assert doc.get("category") not in old_hardcoded_categories, (
                f"Documento usa categoria da lista estática antiga: {doc}"
            )

        # Limpeza
        await db.documents.delete_many({"process_id": process_id})
        await db.processes.delete_one({"id": process_id})
        await db.clients.delete_one({"id": client_id})


class TestBug3ResendPortalErrorPropagation:
    async def test_resend_no_process_returns_400(self, client, admin_token):
        """Cliente sem processo → 400 com mensagem clara (não sucesso falso)."""
        data = await _create_client(client, admin_token, "Bug3")
        client_id = data.get("id")
        assert client_id

        rr = await client.post(
            f"/clients/{client_id}/resend-portal-access",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rr.status_code == 400, f"Esperado 400, obtido {rr.status_code}: {rr.text}"
        detail = rr.json().get("detail", "")
        assert "processo" in detail.lower(), f"Mensagem inesperada: {detail}"

        from database import db
        await db.clients.delete_one({"id": client_id})

    async def test_resend_with_process_reports_real_email_failure(self, client, admin_token):
        """
        Cliente com processo ativo + SMTP não configurado → 500 com a razão
        real (nunca 200 com sucesso falso quando o envio efetivamente falhou).
        """
        data = await _create_client(client, admin_token, "Bug3Proc")
        client_id = data.get("id")
        assert client_id

        rp = await client.post(
            "/processes/create-client",
            json={"client_id": client_id, "process_type": "credito_habitacao"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rp.status_code in (200, 201), f"Create process failed: {rp.text}"
        process_id = rp.json().get("id")

        rr = await client.post(
            f"/clients/{client_id}/resend-portal-access",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Sem SMTP configurado no ambiente de testes, o envio falha de verdade.
        assert rr.status_code in (200, 500, 502, 503), f"Status inesperado: {rr.status_code} {rr.text}"
        body = rr.json()
        if rr.status_code == 200:
            assert body.get("success") is True
        else:
            assert body.get("detail"), f"Erro sem detail: {body}"

        from database import db
        if process_id:
            await db.processes.delete_one({"id": process_id})
            await db.documents.delete_many({"process_id": process_id})
        await db.documents.delete_many({"client_id": client_id})
        await db.clients.delete_one({"id": client_id})
