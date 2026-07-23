"""
Teste de integração ponta-a-ponta — PUT /api/portal/me

Reproduz o bug crítico relatado: o cliente atualiza o seu perfil pelo
Portal e a escrita no MongoDB tinha de deixar intactos os mapeamentos
S3 (`s3_folder`) e as relações com processos (`process_ids`).

Este teste passa pela app FastAPI real (autenticação incluída via JWT
do portal), tal como um pedido real do browser do cliente.
"""
import uuid

import pytest

from services.portal_security import create_access_code_session_token


async def _insert_client_with_s3_mapping(db, client_id: str) -> dict:
    doc = {
        "id": client_id,
        "nome": "Cliente Hotfix Teste",
        "contacto": {"telefone": "911000000", "email": "antigo@example.com"},
        "dados_pessoais": {"profissao": "Motorista", "nif": "123456789"},
        "process_ids": ["proc-hotfix-1", "proc-hotfix-2"],
        "s3_folder": "Documentação Clientes/Cliente_Hotfix_Teste",
        "s3_mapping_updated_at": "2025-01-01T00:00:00+00:00",
        "is_active": True,
        "field_metadata": {
            "dados_pessoais.nif": {"source": "manual", "updated_at": "2025-01-01T00:00:00+00:00"},
        },
    }
    await db.clients.insert_one(doc)
    return doc


class TestPortalMeUpdateNeverTouchesS3Mapping:
    @pytest.mark.asyncio
    async def test_update_profile_preserves_s3_mapping_and_process_ids(self, client):
        from database import get_db
        db = get_db()

        client_id = f"client-hotfix-{uuid.uuid4().hex[:8]}"
        await _insert_client_with_s3_mapping(db, client_id)

        token = create_access_code_session_token(process_id="no_process", client_id=client_id)

        response = await client.put(
            "/portal/me",
            json={
                "contacto": {"telefone": "912999999"},
                "dados_pessoais": {"profissao": "Engenheiro"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert set(body["updated_fields"]) == {"contacto", "dados_pessoais"}

        updated = await db.clients.find_one({"id": client_id})

        # Campos permitidos foram atualizados.
        assert updated["contacto"]["telefone"] == "912999999"
        assert updated["dados_pessoais"]["profissao"] == "Engenheiro"

        # CRÍTICO: mapeamento S3 e relações com processos NUNCA tocados.
        assert updated["s3_folder"] == "Documentação Clientes/Cliente_Hotfix_Teste"
        assert updated["s3_mapping_updated_at"] == "2025-01-01T00:00:00+00:00"
        assert updated["process_ids"] == ["proc-hotfix-1", "proc-hotfix-2"]

        # Histórico de field_metadata anterior preservado + novo entry.
        assert updated["field_metadata"]["dados_pessoais.nif"]["source"] == "manual"
        assert updated["field_metadata"]["contacto.telefone"]["source"] == "client"

        await db.clients.delete_one({"id": client_id})

    @pytest.mark.asyncio
    async def test_update_profile_rejects_disallowed_fields_like_nif(self, client):
        from database import get_db
        db = get_db()

        client_id = f"client-hotfix-{uuid.uuid4().hex[:8]}"
        await _insert_client_with_s3_mapping(db, client_id)
        token = create_access_code_session_token(process_id="no_process", client_id=client_id)

        response = await client.put(
            "/portal/me",
            json={"dados_pessoais": {"nif": "999999999"}},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["updated_fields"] == []

        unchanged = await db.clients.find_one({"id": client_id})
        assert unchanged["dados_pessoais"]["nif"] == "123456789"

        await db.clients.delete_one({"id": client_id})
