"""A descrição de um «outro documento» tem de chegar ao cliente (Bloco 3, ponto 17).

O que acontecia: a equipa pede um «Outro documento», escreve o nome
(«Certidão de Casamento») e uma nota («tem de estar legalizada»). O Portal
mostrava o nome e a nota na lista de PENDENTES — e só aí. As outras três
serializações do `/portal/status` (submetido, recebido e a do cliente ainda
SEM processo, que é a primeira que ele vê) não levavam a nota; a de recebidos
mostrava «Outro Documento» em vez do nome; e a do pré-processo nem sequer
levava `label`, pelo que o ecrã escrevia «Documento» em todas as linhas.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import portal_status
from services.portal_status_helpers import nota_do_pedido, rotulo_do_pedido

CAT = {"label": "Outro Documento", "icon": "📎"}


class TestNotaDoPedido:
    def test_devolve_o_texto_aparado(self):
        assert nota_do_pedido({"notes": "  tem de estar legalizada  "}) == "tem de estar legalizada"

    @pytest.mark.parametrize("doc", [None, {}, {"notes": None}, {"notes": ""}, {"notes": "   "}])
    def test_sem_nota_e_texto_vazio_nunca_none(self, doc):
        assert nota_do_pedido(doc) == ""

    def test_aceita_o_objecto_que_registos_antigos_guardaram(self):
        assert nota_do_pedido({"notes": {"label": "Original"}}) == "Original"
        assert nota_do_pedido({"notes": {"value": "Valor"}}) == "Valor"

    def test_uma_nota_numerica_vira_texto(self):
        assert nota_do_pedido({"notes": 42}) == "42"


class TestRotuloDoPedido:
    def test_prefere_o_nome_especifico_ao_da_categoria(self):
        assert rotulo_do_pedido({"custom_label": "Certidão de Casamento"}, CAT) == "Certidão de Casamento"

    def test_a_ordem_dos_campos_e_a_do_ecra(self):
        doc = {"custom_label": "A", "custom_name": "B", "description": "C", "title": "D"}
        assert rotulo_do_pedido(doc, CAT) == "A"
        assert rotulo_do_pedido({k: v for k, v in doc.items() if k != "custom_label"}, CAT) == "B"
        assert rotulo_do_pedido({"description": "C", "title": "D"}, CAT) == "C"
        assert rotulo_do_pedido({"title": "D"}, CAT) == "D"

    @pytest.mark.parametrize("vazio", ["", "   ", None, 7, [], {}])
    def test_um_nome_vazio_ou_nao_textual_cai_na_categoria(self, vazio):
        assert rotulo_do_pedido({"custom_label": vazio}, CAT) == "Outro Documento"

    def test_sem_nada_nunca_devolve_vazio(self):
        assert rotulo_do_pedido({}, {}) == "Documento"
        assert rotulo_do_pedido({"category": "IRS"}, {}) == "IRS"


@pytest.fixture
async def mundo(fake_async_db):
    await fake_async_db.processes.insert_one(
        {"id": "p-1", "client_id": "c-1", "client_name": "Joana", "status": "fase_x"}
    )
    base = {"process_id": "p-1", "category": "Outros",
            "custom_label": "Certidão de Casamento", "notes": "tem de estar legalizada"}
    await fake_async_db.documents.insert_one(
        {**base, "id": "d-pedido", "status": "REQUESTED", "created_at": "2026-10-01"})
    await fake_async_db.documents.insert_one(
        {**base, "id": "d-submetido", "status": "UPLOADED", "filename": "a.pdf",
         "uploaded_at": "2026-10-02"})
    await fake_async_db.documents.insert_one(
        {**base, "id": "d-recebido", "status": "RECEIVED", "filename": "b.pdf",
         "updated_at": "2026-10-03"})
    with patch.object(portal_status, "db", fake_async_db):
        yield fake_async_db


async def _estado(mundo, **extra):
    processo = await mundo.processes.find_one({"id": "p-1"}, {"_id": 0})
    with patch.object(portal_status, "_get_rgpd_status", side_effect=lambda *_: _ok({"status": "none"})), \
         patch.object(portal_status, "_get_user_contact_info", side_effect=lambda *_: _ok(None)):
        return await portal_status.run_get_portal_status({"process": processo, **extra})


async def _ok(valor):
    return valor


class TestAsQuatroListasLevamANota:
    async def test_pendentes_submetidos_e_recebidos_levam_o_nome_e_a_nota(self, mundo):
        docs = (await _estado(mundo))["documents"]
        (pedido,) = [d for d in docs["requested"] if d["id"] == "d-pedido"]
        (submetido,) = [d for d in docs["uploaded"] if d["id"] == "d-submetido"]
        (recebido,) = [d for d in docs["received"] if d["id"] == "d-recebido"]

        assert pedido["label"] == "Certidão de Casamento"
        assert submetido["category_label"] == "Certidão de Casamento"
        assert recebido["category_label"] == "Certidão de Casamento"  # era «Outro Documento»
        for item in (pedido, submetido, recebido):
            assert item["notes"] == "tem de estar legalizada"

    async def test_a_lista_do_cliente_sem_processo_leva_label_icone_e_nota(self, mundo):
        """A PRIMEIRA que o cliente vê. Sem `label` o ecrã escrevia «Documento»."""
        await mundo.documents.insert_one({
            "id": "d-pre", "client_id": "c-1", "category": "Outros", "status": "REQUESTED",
            "source": "mandatory_checklist", "custom_label": "Certidão de Casamento",
            "notes": "tem de estar legalizada",
        })
        resposta = await portal_status.run_get_portal_status(
            {"process": None, "client_id": "c-1", "client": {"nome": "Joana"}}
        )
        (pre,) = [d for d in resposta["documents"]["requested"] if d["id"] == "d-pre"]
        assert pre["label"] == "Certidão de Casamento"
        assert pre["notes"] == "tem de estar legalizada"
        assert pre["icon"]

    async def test_sem_nota_a_chave_existe_e_e_vazia(self, mundo):
        """O ecrã decide por «tem nota?»; uma chave ausente e uma vazia não
        podem comportar-se de maneira diferente em nenhuma das listas."""
        await mundo.documents.update_many({}, {"$unset": {"notes": ""}})
        docs = (await _estado(mundo))["documents"]
        for lista in ("requested", "uploaded", "received"):
            assert all(d["notes"] == "" for d in docs[lista] if d["id"].startswith("d-")), lista

    async def test_o_nome_especifico_vale_para_qualquer_categoria(self, mundo):
        await mundo.documents.insert_one({
            "id": "d-irs", "process_id": "p-1", "category": "IRS", "status": "REQUESTED",
            "custom_label": "IRS de 2024 (anexo B)", "created_at": "2026-10-04",
        })
        docs = (await _estado(mundo))["documents"]
        (irs,) = [d for d in docs["requested"] if d["id"] == "d-irs"]
        assert irs["label"] == "IRS de 2024 (anexo B)"
