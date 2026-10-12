"""
Colisão B2B (cross-network): a lead do parceiro encontra um cliente que já existe no destino.

A REGRA (adenda de Out 2026)
  1. Hierarquia: NIF primeiro; só sem NIF se procura pelo email.
  2. Match → associa-se ao cliente existente e a rede de destino NÃO vê os seus
     contactos (email/telemóvel/NIF/nome) alterados.

O QUE ESTES TESTES PROVAM
  * a hierarquia (um NIF presente que não coincide NÃO cai para o email);
  * a soberania do destino (o documento do cliente existente fica igual, salvo a
    entrada acrescentada em `partner_leads`, que não leva dados pessoais);
  * o parceiro não aprende nada (nem o id do cliente existente) e fica com um
    registo submetido e fechado;
  * a procura falhar nunca perde a lead.
"""
from __future__ import annotations

import copy
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE
from tests.unit.test_parceiro_escrita import (  # noqa: F401  (fixtures do mundo do parceiro)
    com_bd,
    mundo,
    rede_de_omissao_incumbente,
    s3,
    tarefas,
    veredicto,
)
from tests.unit.test_parceiro_filtro_de_viabilidade import COMPROVATIVO, _enviar, _lead_retida
from tests.unit.test_parceiro_leitura import PT1

NIF_DA_LEAD = "501964843"
EMAIL_DA_LEAD = "joana@cliente.pt"
TELEFONE_DA_LEAD = "912345678"


def _existente(com_bd, *, id="c-existente", rede=REDE_INCUMBENTE, nif=NIF_DA_LEAD,
               email="antigo@destino.pt", telefone="933333333", **extra):
    """Um cliente JÁ gravado no destino (cifrado, com blind indexes), como em produção."""
    from services.encryption import encrypt_client_data

    doc = {
        "id": id, "nome": "Joana do Destino", "lead_status": "converted",
        "contacto": {"email": email, "telefone": telefone},
        "dados_pessoais": {"nif": nif} if nif else {},
        "process_ids": [], **extra,
    }
    if rede:
        doc["network_id"] = rede
        doc["company_id"] = "cmp-domus" if rede == REDE_DOMUS else "cmp-power"
    doc = encrypt_client_data(doc)
    com_bd.clients.docs.append(doc)
    return doc


def _cliente(com_bd, id_):
    return next(c for c in com_bd.clients.docs if c["id"] == id_)


async def _submeter_e_libertar(com_bd, **corpo):
    cid = await _lead_retida(com_bd, **corpo)
    resposta = await _enviar(com_bd, cid, COMPROVATIVO)
    return cid, resposta


# ════════════════════════════════════════════════════════════════════
#  1. A HIERARQUIA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAHierarquia:
    async def test_o_nif_igual_e_o_mesmo_cliente_mesmo_com_contactos_diferentes(self, com_bd):
        _existente(com_bd)
        cid, resposta = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        assert resposta["lead_submetida"] is True
        assert not [c for c in com_bd.clients.docs if c["id"] == cid], "não nasceu um cliente novo"
        entrada = _cliente(com_bd, "c-existente")["partner_leads"][0]
        assert entrada["lead_id"] == cid and entrada["associada_por"] == "nif"

    async def test_sem_nif_procura_pelo_email(self, com_bd):
        _existente(com_bd, nif=None, email=EMAIL_DA_LEAD)
        cid, _ = await _submeter_e_libertar(com_bd)

        assert not [c for c in com_bd.clients.docs if c["id"] == cid]
        assert _cliente(com_bd, "c-existente")["partner_leads"][0]["associada_por"] == "email"

    async def test_um_nif_presente_que_nao_coincide_nao_cai_para_o_email(self, com_bd):
        """O mesmo email com outro NIF é outra pessoa (uma família partilha o email)."""
        _existente(com_bd, id="c-outra-pessoa", nif="123456789", email=EMAIL_DA_LEAD)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        novo = _cliente(com_bd, cid)
        assert novo["lead_status"] == "new", "nasceu um cliente novo"
        assert "partner_leads" not in _cliente(com_bd, "c-outra-pessoa")
        # A triagem fica a saber (como antes): é um possível duplicado, não um match.
        assert "c-outra-pessoa" in novo.get("possible_duplicate_of", [])

    async def test_o_telemovel_sozinho_nunca_identifica(self, com_bd):
        _existente(com_bd, id="c-mesmo-telemovel", nif="123456789", email="x@y.pt", telefone=TELEFONE_DA_LEAD)
        cid, _ = await _submeter_e_libertar(com_bd)

        assert _cliente(com_bd, cid)["lead_status"] == "new"
        assert "partner_leads" not in _cliente(com_bd, "c-mesmo-telemovel")

    async def test_sem_correspondencia_nasce_um_cliente_novo(self, com_bd):
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert _cliente(com_bd, cid)["lead_status"] == "new"


# ════════════════════════════════════════════════════════════════════
#  2. A REDE DE DESTINO É SOBERANA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestASoberaniaDoDestino:
    async def test_o_cliente_existente_fica_igual_salvo_a_entrada_acrescentada(self, com_bd):
        _existente(com_bd, email="antigo@destino.pt", telefone="933333333")
        antes = copy.deepcopy(_cliente(com_bd, "c-existente"))

        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        depois = copy.deepcopy(_cliente(com_bd, "c-existente"))
        entradas = depois.pop("partner_leads")
        assert len(entradas) == 1
        assert depois == antes, "nem email, nem telemóvel, nem NIF, nem nome, nem estado de lead"

    async def test_os_contactos_gravados_continuam_os_do_destino(self, com_bd):
        from services.encryption import decrypt_client_data

        _existente(com_bd, email="antigo@destino.pt", telefone="933333333")
        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        legivel = decrypt_client_data(copy.deepcopy(_cliente(com_bd, "c-existente")))
        assert legivel["contacto"]["email"] == "antigo@destino.pt"
        assert legivel["contacto"]["telefone"] == "933333333"

    async def test_a_entrada_diz_quais_os_contactos_divergentes_sem_os_valores(self, com_bd):
        _existente(com_bd, email="antigo@destino.pt", telefone="933333333")
        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        entrada = _cliente(com_bd, "c-existente")["partner_leads"][0]
        assert entrada["campos_divergentes"] == ["email", "telefone"]
        bruto = json.dumps(entrada)
        for valor in (EMAIL_DA_LEAD, TELEFONE_DA_LEAD, "Joana Cliente", NIF_DA_LEAD):
            assert valor not in bruto, f"a entrada não pode levar dados pessoais ({valor})"

    async def test_contactos_iguais_nao_divergem(self, com_bd):
        _existente(com_bd, email=EMAIL_DA_LEAD, telefone=TELEFONE_DA_LEAD)
        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert _cliente(com_bd, "c-existente")["partner_leads"][0]["campos_divergentes"] == []

    async def test_so_o_telemovel_diverge(self, com_bd):
        _existente(com_bd, email=EMAIL_DA_LEAD, telefone="933333333")
        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert _cliente(com_bd, "c-existente")["partner_leads"][0]["campos_divergentes"] == ["telefone"]

    async def test_um_cliente_ja_convertido_nao_volta_a_ser_lead_nova(self, com_bd):
        _existente(com_bd, lead_status="converted")
        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert _cliente(com_bd, "c-existente")["lead_status"] == "converted"

    async def test_o_parceiro_nao_passa_a_ser_o_dono_do_cliente_existente(self, com_bd):
        _existente(com_bd)
        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert not _cliente(com_bd, "c-existente").get("submitted_by_partner_id")


# ════════════════════════════════════════════════════════════════════
#  3. SÓ A REDE DE DESTINO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestSoADestinoConta:
    async def test_um_cliente_de_outra_rede_com_o_mesmo_nif_nao_e_match(self, com_bd):
        _existente(com_bd, id="c-domus", rede=REDE_DOMUS)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        assert _cliente(com_bd, cid)["lead_status"] == "new"
        assert "partner_leads" not in _cliente(com_bd, "c-domus")

    async def test_um_cliente_eliminado_nao_e_match(self, com_bd):
        _existente(com_bd, is_deleted=True, status="eliminado")
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert _cliente(com_bd, cid)["lead_status"] == "new"

    async def test_a_pilha_por_carimbar_conta_para_a_rede_de_omissao(self, com_bd):
        _existente(com_bd, rede=None)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert not [c for c in com_bd.clients.docs if c["id"] == cid]


# ════════════════════════════════════════════════════════════════════
#  4. O PARCEIRO NÃO APRENDE NADA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOParceiroNaoApreendeNada:
    async def test_o_registo_aparece_como_submetido_sem_o_id_do_cliente_existente(self, com_bd):
        import services.partner_portal_read as ppr

        _existente(com_bd)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        itens = (await ppr.run_list_cases(PT1))["items"]
        assert [(i["id"], i["etapa"], i["editavel"]) for i in itens] == [(cid, "lead", False)]
        caso = await ppr.run_get_case(PT1, cid)
        assert caso["etapa"] == "lead" and caso["editavel"] is False
        todo = json.dumps([itens, caso], default=str)
        assert "c-existente" not in todo and "partner_leads" not in todo and "matched_client_id" not in todo

    async def test_a_resposta_do_envio_e_igual_a_de_uma_lead_normal(self, com_bd):
        _existente(com_bd)
        _, associada = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        _, normal = await _submeter_e_libertar(com_bd, nif="999999990", email="outra@cliente.pt")
        assert set(associada) == set(normal)
        assert associada["lead_submetida"] is normal["lead_submetida"] is True

    async def test_depois_de_associada_o_parceiro_ja_nao_a_mexe(self, com_bd):
        import services.form_config_scope as fcs
        import services.partner_client_form as form
        from tests.unit.helpers_tenant import tenant_db

        # O formulário do parceiro lê o `form_config` por módulos que o `com_bd` não patcha:
        # sem isto o teste falava com o `db` real e passava ou falhava conforme a ordem.
        with tenant_db(com_bd, form, fcs):
            await self._corpo_do_teste(com_bd, form)

    async def _corpo_do_teste(self, com_bd, form):

        _existente(com_bd)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        with pytest.raises(HTTPException) as erro:
            await _enviar(com_bd, cid, "Outros", nome="mais.pdf")
        from services.partner_upload_ops import ERRO_LEAD_ASSOCIADA

        assert erro.value.status_code == 409 and erro.value.detail == ERRO_LEAD_ASSOCIADA
        # Os DOIS passos do envio recusam: nem o URL pré-assinado se emite.
        from services.partner_upload_ops import PartnerUploadUrlIn, run_partner_upload_url

        with pytest.raises(HTTPException) as erro_url:
            await run_partner_upload_url(PT1, cid, PartnerUploadUrlIn(filename="mais.pdf", category="Outros"))
        assert erro_url.value.status_code == 409 and erro_url.value.detail == ERRO_LEAD_ASSOCIADA
        assert (await form.run_get_client_form(PT1, cid))["editavel"] is False
        with pytest.raises(HTTPException) as erro_form:
            await form.run_save_client_form(PT1, cid, form.ClientFormIn(values={"name": "Outro Nome"}))
        assert erro_form.value.status_code == 409 and erro_form.value.detail == form.ERRO_NAO_EDITAVEL

    async def test_so_a_equipa_sabe_a_que_cliente_foi_associada(self, com_bd):
        _existente(com_bd)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        rascunho = next(d for d in com_bd.partner_drafts.docs if d["id"] == cid)
        assert rascunho["partner_stage"] == "associada" and rascunho["matched_client_id"] == "c-existente"


# ════════════════════════════════════════════════════════════════════
#  5. A EQUIPA É AVISADA, E NADA SE PERDE
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAvisoEResiliencia:
    async def test_o_aviso_diz_que_foi_associada(self, com_bd):
        from services.partner_leads import avisar_gestao_da_lead

        _existente(com_bd)
        await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        entrada = _cliente(com_bd, "c-existente")["partner_leads"][0]
        assert entrada["partner_id"] == "pt-1"

        notificar = AsyncMock()
        with patch("services.alerts.notify_new_client_registration", notificar):
            await avisar_gestao_da_lead(
                PT1, {"id": "c-existente", "nome": "Joana do Destino", "_associada": True},
                {"network_id": REDE_INCUMBENTE},
            )
        assert "associada" in notificar.await_args.kwargs["origem"]

    async def test_o_aviso_de_uma_lead_normal_nao_diz_associada(self, com_bd):
        from services.partner_leads import avisar_gestao_da_lead

        notificar = AsyncMock()
        with patch("services.alerts.notify_new_client_registration", notificar):
            await avisar_gestao_da_lead(PT1, {"id": "c-1", "nome": "X"}, {"network_id": REDE_INCUMBENTE})
        assert "associada" not in notificar.await_args.kwargs["origem"]

    async def test_se_a_procura_falhar_a_lead_segue_o_caminho_normal(self, com_bd):
        _existente(com_bd)
        with patch("services.b2b_client_match.encontrar_cliente_de_destino", AsyncMock(side_effect=RuntimeError("bd"))):
            cid, resposta = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert resposta["lead_submetida"] is True
        assert _cliente(com_bd, cid)["lead_status"] == "new", "a lead não se perde"

    async def test_associar_e_idempotente(self, com_bd):
        import services.partner_drafts as drafts

        _existente(com_bd)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        assert await drafts.libertar_se_tiver_comprovativo(cid) is None
        assert len(_cliente(com_bd, "c-existente")["partner_leads"]) == 1

    async def test_o_rascunho_associado_nao_expira_nem_volta_a_ser_pendente(self, com_bd):
        import services.partner_drafts as drafts

        _existente(com_bd)
        cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        rascunho = next(d for d in com_bd.partner_drafts.docs if d["id"] == cid)
        assert drafts.estado_do_rascunho(rascunho) == "associada"
        assert drafts.pode_ser_editado(rascunho) is False
        resultado = await drafts.expirar_leads_inactivas(dias=0, bd=com_bd)
        assert resultado["rascunhos"] == 0


# ════════════════════════════════════════════════════════════════════
#  6. A REGRA PURA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestARegraPura:
    async def test_a_hierarquia_chama_a_procura_so_pelo_campo_que_decide(self):
        from services import b2b_client_match as m

        chamadas = []

        async def procura(nif, email, telefone=None, *, rede=None, excluir_id=None):
            chamadas.append((nif, email, telefone))
            return {"id": "x"} if (nif or email) else None

        with patch.object(m, "encontrar_cliente_duplicado", procura):
            await m.encontrar_cliente_de_destino(
                {"dados_pessoais": {"nif": "501964843"}, "contacto": {"email": "a@b.pt", "telefone": "912345678"}}, rede="r",
            )
            await m.encontrar_cliente_de_destino(
                {"dados_pessoais": {"nif": ""}, "contacto": {"email": "a@b.pt", "telefone": "912345678"}}, rede="r",
            )
            await m.encontrar_cliente_de_destino({"dados_pessoais": {}, "contacto": {"telefone": "912345678"}}, rede="r")

        assert chamadas == [("501964843", None, None), (None, "a@b.pt", None)], (
            "com NIF só o NIF; sem NIF só o email; só com telemóvel não se procura"
        )

    async def test_um_nif_presente_sem_match_nao_tenta_o_email(self):
        from services import b2b_client_match as m

        chamadas = []

        async def procura(nif, email, telefone=None, *, rede=None, excluir_id=None):
            chamadas.append((nif, email))
            return None

        with patch.object(m, "encontrar_cliente_duplicado", procura):
            resultado = await m.encontrar_cliente_de_destino(
                {"dados_pessoais": {"nif": "501964843"}, "contacto": {"email": "a@b.pt"}}, rede="r",
            )
        assert resultado == (None, None) and chamadas == [("501964843", None)]
