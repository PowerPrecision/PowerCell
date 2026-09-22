"""
Pedidos do portal na aba Documentos do CRM (Missão de Limpeza, ponto 5).

O DEFEITO
---------
Os documentos obrigatórios/opcionais pedidos ao cliente não apareciam do
lado do CRM. Duas causas independentes, e corrigir só uma não chegava:

  (a) O registo público cria os pedidos por `client_id`, antes de existir
      processo. Só `onboarding_mandatory_config` (o caminho
      "checklist completa") os ancora ao processo depois — `client_assign`
      e `process_create` não. Um processo criado pela Sala de Triagem
      deixava-os órfãos para sempre.

  (b) Mesmo ancorados, a consulta do CRM filtrava por uma ALLOW-LIST de
      `source` que não conhecia `mandatory_checklist` nem
      `mandatory_checklist_optional`.

Resultado: o consultor não via o que tinha sido pedido ao cliente, e o
cliente via pedidos que o consultor não sabia que existiam.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import document_portal_request
from services.document_portal_request import (
    PORTAL_REQUEST_SOURCES,
    build_portal_requests_query,
    run_get_portal_document_requests,
)


# ====================================================================
# A CONSULTA
# ====================================================================


class TestAllowListDeOrigens:
    def test_conhece_a_checklist_obrigatoria(self):
        assert "mandatory_checklist" in PORTAL_REQUEST_SOURCES

    def test_conhece_a_checklist_opcional(self):
        assert "mandatory_checklist_optional" in PORTAL_REQUEST_SOURCES

    def test_mantem_as_origens_antigas(self):
        # Nenhum pedido existente pode desaparecer da lista.
        for origem in ("client_portal", "admin_request", "auto_default"):
            assert origem in PORTAL_REQUEST_SOURCES


class TestConsulta:
    def test_aceita_pedidos_ancorados_ao_processo(self):
        consulta = build_portal_requests_query("proc-1", client_ids=[])
        ramos = consulta["$or"]
        assert any(ramo.get("process_id") == "proc-1" for ramo in ramos)

    def test_aceita_pedidos_orfaos_do_cliente(self):
        # O caso (a): pedidos criados no registo público, antes do processo.
        consulta = build_portal_requests_query("proc-1", client_ids=["cli-1"])
        ramos = consulta["$or"]
        ramo_cliente = next(
            (r for r in ramos if "client_id" in r), None
        )
        assert ramo_cliente is not None
        assert ramo_cliente["client_id"] == {"$in": ["cli-1"]}

    def test_sem_clientes_nao_inventa_ramo(self):
        consulta = build_portal_requests_query("proc-1", client_ids=[])
        assert all("client_id" not in ramo for ramo in consulta["$or"])

    def test_o_ramo_do_cliente_exige_pedido_sem_processo(self):
        # Sem esta condição, um pedido do MESMO cliente mas de OUTRO
        # processo entrava nesta lista — dados do processo errado.
        consulta = build_portal_requests_query("proc-1", client_ids=["cli-1"])
        ramo_cliente = next(r for r in consulta["$or"] if "client_id" in r)
        assert "$or" in ramo_cliente or "process_id" in ramo_cliente

    def test_filtra_por_origem_conhecida_ou_ausente(self):
        consulta = build_portal_requests_query("proc-1", client_ids=[])
        origens = consulta["$and"][0]["$or"] if "$and" in consulta else None
        assert origens is not None, consulta


# ====================================================================
# O ENDPOINT
# ====================================================================


PEDIDOS = [
    {
        "id": "d-1",
        "process_id": "proc-1",
        "category": "Identificação",
        "status": "REQUESTED",
        "source": "mandatory_checklist",
        "created_at": "2026-09-01",
    },
    {
        "id": "d-2",
        "client_id": "cli-1",
        "category": "Financeiros",
        "status": "REQUESTED",
        "source": "mandatory_checklist_optional",
        "created_at": "2026-09-02",
    },
]


def _db(processo, pedidos):
    fake = MagicMock()
    fake.processes.find_one = AsyncMock(return_value=processo)

    class Cursor:
        def __init__(self, docs):
            self._docs = docs

        def __aiter__(self):
            async def gen():
                for d in self._docs:
                    yield d
            return gen()

    fake.documents.find = MagicMock(return_value=Cursor(pedidos))
    return fake


class TestListagem:
    @pytest.mark.asyncio
    async def test_a_checklist_obrigatoria_aparece_no_crm(self):
        processo = {"id": "proc-1", "client_id": "cli-1"}
        with patch.object(document_portal_request, "db", _db(processo, PEDIDOS)):
            resultado = await run_get_portal_document_requests("proc-1")

        ids = [d["id"] for d in resultado["documents"]]
        assert "d-1" in ids, "pedido obrigatório em falta"
        assert "d-2" in ids, "pedido opcional órfão em falta"

    @pytest.mark.asyncio
    async def test_procura_tambem_pelos_clientes_do_processo(self):
        processo = {
            "id": "proc-1",
            "client_id": "cli-1",
            "second_client_id": "cli-2",
            "client_ids": ["cli-1", "cli-3"],
        }
        fake = _db(processo, [])
        with patch.object(document_portal_request, "db", fake):
            await run_get_portal_document_requests("proc-1")

        consulta = fake.documents.find.call_args[0][0]
        ramo_cliente = next(r for r in consulta["$or"] if "client_id" in r)
        # Os dois titulares e os clientes ligados, sem repetições.
        assert set(ramo_cliente["client_id"]["$in"]) == {"cli-1", "cli-2", "cli-3"}

    @pytest.mark.asyncio
    async def test_processo_inexistente_nao_rebenta_a_listagem(self):
        # Degradação: sem processo, lista só o que estiver ancorado.
        fake = _db(None, [PEDIDOS[0]])
        with patch.object(document_portal_request, "db", fake):
            resultado = await run_get_portal_document_requests("proc-x")
        assert resultado["success"] is True
