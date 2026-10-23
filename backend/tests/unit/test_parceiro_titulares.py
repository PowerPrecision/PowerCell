"""Portal do Parceiro — documentos do 1.º e do 2.º titular (Out 2026).

O parceiro via os documentos de um processo com dois compradores todos misturados («Cartão de Cidadão» três
vezes, sem saber de quem). O que se prova:

  1. só há titulares a distinguir quando há 2.º titular — com um comprador só nenhuma etiqueta;
  2. o parceiro diz de quem é o documento ao enviar (`titular`) e o servidor guarda-o POR FICHEIRO (um pedido
     pode receber ficheiros dos dois); `titular2` num caso de um só é 400;
  3. sem marcador, o `client_id` do 2.º cliente é do 2.º titular; um pedido sem marcador não se atribui a ninguém
     (a checklist serve os dois), um ficheiro solto cai no 1.º;
  4. o detalhe devolve o nome do 2.º titular e NADA mais da ficha dele (a lista é positiva).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.test_parceiro_escrita import (  # noqa: F401  (fixtures do mundo do parceiro)
    CHAVE_BOA,
    _confirmar,
    _mundo,
    com_bd,
    mundo,
    rede_de_omissao_incumbente,
    s3,
    tarefas,
    veredicto,
)
from services.partner_visibility import AUTORIA_DO_CLIENTE
from tests.unit.test_parceiro_leitura import PT1


def _com_segundo_titular(m, **extra):
    """O processo `a-novo` passa a ter dois compradores (o 2.º com ficha própria)."""
    proc = next(p for p in m.processes.docs if p["id"] == "a-novo")
    proc.update({
        "second_client_id": "cli-2",
        "titular2_data": {"name": "Rui Segundo", "nif": "ENC:segredo", "email": "t2@x.pt", "documento_id": "ENC:cc"},
        **extra,
    })
    return proc


def _pedido(m, pid="req-1", **extra):
    m.documents.docs.append({
        "id": pid, "process_id": "a-novo", "client_id": "cli-a-novo", "status": "REQUESTED",
        "source": "mandatory_checklist", "category": "Identificação", "expected_count": 1,
        "created_at": "2026-10-04T10:00:00+00:00", **extra,
    })


@pytest.mark.asyncio
class TestSoHaTitularesComDoisCompradores:
    async def test_com_um_comprador_nao_ha_etiquetas(self, com_bd):
        import services.partner_portal_read as ppr
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _pedido(com_bd)
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops))
        d = await ppr.run_get_case(PT1, "a-novo")
        assert d["titulares"] == []
        assert d["ficheiros"][0]["titular"] is None and d["ficheiros"][0]["titular_label"] is None
        assert d["pedidos"][0]["titular"] is None

    async def test_com_dois_compradores_o_detalhe_diz_quem_sao(self, com_bd):
        import services.partner_portal_read as ppr

        _mundo(com_bd)
        _com_segundo_titular(com_bd)
        d = await ppr.run_get_case(PT1, "a-novo")
        assert d["titulares"] == [
            {"id": "titular1", "label": "1.º titular", "nome": "Cliente a-novo"},
            {"id": "titular2", "label": "2.º titular", "nome": "Rui Segundo"},
        ]

    async def test_do_segundo_titular_sai_o_nome_e_mais_nada(self, com_bd):
        import services.partner_portal_read as ppr

        _mundo(com_bd)
        _com_segundo_titular(com_bd)
        blob = repr(await ppr.run_get_case(PT1, "a-novo"))
        for segredo in ("ENC:segredo", "t2@x.pt", "ENC:cc", "nif", "documento_id", "cli-2"):
            assert segredo not in blob, segredo

    async def test_uma_lead_com_outra_pessoa_tem_dois_titulares(self, com_bd):
        import services.partner_portal_read as ppr

        _mundo(com_bd)
        lead = next(c for c in com_bd.clients.docs if c["id"] == "lead-1")
        lead["dados_pessoais"] = {"compra_tipo": "outra_pessoa"}
        lead["titular2_data"] = {"name": "Maria Segunda"}
        d = await ppr.run_get_case(PT1, "lead-1")
        assert [t["id"] for t in d["titulares"]] == ["titular1", "titular2"]
        assert d["titulares"][1]["nome"] == "Maria Segunda"

    async def test_uma_lead_individual_nao_tem(self, com_bd):
        import services.partner_portal_read as ppr

        _mundo(com_bd)
        lead = next(c for c in com_bd.clients.docs if c["id"] == "lead-1")
        lead["dados_pessoais"] = {"compra_tipo": "individual"}
        assert (await ppr.run_get_case(PT1, "lead-1"))["titulares"] == []


@pytest.mark.asyncio
class TestOParceiroDizDeQuemE:
    async def test_o_ficheiro_solto_guarda_e_devolve_o_titular(self, com_bd):
        import services.partner_portal_read as ppr
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _com_segundo_titular(com_bd)
        r = await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, titular="titular2"))
        doc = next(d for d in com_bd.documents.docs if d["id"] == r["id"])
        assert doc["titular"] == "titular2"
        f = (await ppr.run_get_case(PT1, "a-novo"))["ficheiros"][0]
        assert (f["titular"], f["titular_label"]) == ("titular2", "2.º titular")

    async def test_um_pedido_recebe_ficheiros_dos_dois_cada_um_com_o_seu_titular(self, com_bd):
        import services.partner_portal_read as ppr
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _com_segundo_titular(com_bd)
        _pedido(com_bd, expected_count=2)
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, key=CHAVE_BOA, nome="t1.pdf", request_id="req-1", titular="titular1"))
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, key=CHAVE_BOA.replace(".pdf", "-b.pdf"), nome="t2.pdf", request_id="req-1", titular="titular2"))
        pedido = (await ppr.run_get_case(PT1, "a-novo"))["pedidos"][0]
        por_nome = {f["filename"]: f["titular"] for f in pedido["ficheiros"]}
        assert por_nome == {"t1.pdf": "titular1", "t2.pdf": "titular2"}
        # o pedido em si não é de ninguém: serve os dois
        assert pedido["titular"] is None and pedido["titular_label"] is None

    async def test_titular2_num_caso_de_um_comprador_e_400_e_nao_grava(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, titular="titular2"))
        assert erro.value.status_code == 400 and "2.º titular" in erro.value.detail
        assert com_bd.documents.docs == []

    async def test_o_marcador_so_aceita_os_dois_valores(self, com_bd):
        import services.partner_upload_ops as ops

        with pytest.raises(Exception):
            _confirmar(ops, titular="titular3")
        with pytest.raises(Exception):
            _confirmar(ops, titular="<script>")

    async def test_titular1_num_caso_de_um_comprador_nao_deixa_marcador(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        r = await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, titular="titular1"))
        assert "titular" not in next(d for d in com_bd.documents.docs if d["id"] == r["id"])


@pytest.mark.asyncio
class TestSemMarcadorDecideOClienteDoDocumento:
    async def test_um_envio_do_proprio_segundo_titular_chega_como_dele(self, com_bd):
        import services.partner_portal_read as ppr

        _mundo(com_bd)
        _com_segundo_titular(com_bd)
        com_bd.documents.docs.append({
            "id": "d-t2", "process_id": "a-novo", "client_id": "cli-2", "source": "client_portal", "status": "RECEIVED",
            "category": "Identificação", "filename": "cc-t2.pdf", "s3_path": "Documentação Clientes/cli-a-novo/Index/cc-t2.pdf",
            "uploaded_by": AUTORIA_DO_CLIENTE, "uploaded_at": "2026-10-05T10:00:00+00:00",
        })
        com_bd.documents.docs.append({
            "id": "d-t1", "process_id": "a-novo", "client_id": "cli-a-novo", "source": "client_portal", "status": "RECEIVED",
            "category": "Identificação", "filename": "cc-t1.pdf", "s3_path": "Documentação Clientes/cli-a-novo/Index/cc-t1.pdf",
            "uploaded_by": AUTORIA_DO_CLIENTE, "uploaded_at": "2026-10-05T11:00:00+00:00",
        })
        por_nome = {f["filename"]: f["titular"] for f in (await ppr.run_get_case(PT1, "a-novo"))["ficheiros"]}
        assert por_nome == {"cc-t2.pdf": "titular2", "cc-t1.pdf": "titular1"}

    async def test_o_marcador_explicito_vence_o_cliente_do_documento(self, com_bd):
        import services.partner_portal_read as ppr

        _mundo(com_bd)
        _com_segundo_titular(com_bd)
        com_bd.documents.docs.append({
            "id": "d-x", "process_id": "a-novo", "client_id": "cli-2", "titular": "titular1", "source": "partner_portal",
            "status": "RECEIVED", "category": "Identificação", "filename": "x.pdf",
            "s3_path": "Documentação Clientes/cli-a-novo/Index/x.pdf", "uploaded_by": "partner:pt-1",
        })
        assert (await ppr.run_get_case(PT1, "a-novo"))["ficheiros"][0]["titular"] == "titular1"

    async def test_um_pedido_do_segundo_cliente_e_do_segundo_titular(self, com_bd):
        import services.partner_portal_read as ppr

        _mundo(com_bd)
        _com_segundo_titular(com_bd)
        _pedido(com_bd, pid="req-t2", client_id="cli-2")
        _pedido(com_bd, pid="req-livre")
        por_id = {p["id"]: p["titular"] for p in (await ppr.run_get_case(PT1, "a-novo"))["pedidos"]}
        assert por_id == {"req-t2": "titular2", "req-livre": None}


class TestARegraPura:
    def test_o_valor_que_liga_o_segundo_titular_e_o_do_formulario(self):
        import services.partner_client_form as pcf
        import services.partner_titulares as pt

        assert pt._VALOR_DE_COMPRA_COM_OUTRA_PESSOA == pcf.VALOR_DO_SEGUNDO_TITULAR

    @pytest.mark.parametrize("valor", [None, "", "titular3", "TITULAR2", 2, {}])
    def test_so_os_dois_valores_conhecidos_sao_marcadores(self, valor):
        import services.partner_titulares as pt

        assert pt.titular_marcado(valor) is None

    def test_os_dois_valores_conhecidos(self):
        import services.partner_titulares as pt

        assert pt.titular_marcado(" titular2 ") == "titular2" and pt.titular_marcado("titular1") == "titular1"
