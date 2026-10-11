"""
Bloco C, ponto 6 — o separador «Dados do cliente» do Portal do Parceiro.

Usa a MESMA estrutura do registo público (o `form_config` do administrador)
e suporta Segundos Titulares. O que se prova:

  1. o esquema DERIVA do `form_config` (passos 1 e 2; só visíveis; sem
     consentimento nem imóvel/financeiro) — não é uma lista paralela;
  2. a edição é por lista positiva e por TIPO (NIF, email, data, opção…),
     tudo validado antes de escrever o que quer que seja;
  3. o 2.º titular liga-se por `compra_tipo = outra_pessoa`; desligar apaga
     os seus dados; preencher sem ligar é 400;
  4. só se edita o que ainda é do parceiro (rascunho, devolvida, lead sem
     processo) — um processo é da equipa e uma lead expirada não se trabalha;
  5. a PII fica cifrada e os blind indexes são recalculados.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import tenant_db
from tests.unit.test_parceiro_escrita import (  # noqa: F401  (fixtures do mundo do parceiro)
    _corpo,
    _mundo,
    com_bd,
    mundo,
    rede_de_omissao_incumbente,
    s3,
    tarefas,
    veredicto,
)
from tests.unit.test_parceiro_leitura import PT1, PT2


@pytest.fixture
def com_form(com_bd):
    import services.partner_client_form as pcf
    import services.public_form_config as pfc

    with tenant_db(com_bd, pcf, pfc):
        yield com_bd


async def _rascunho(com_form, **extra):
    import services.partner_leads as pl

    r = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(nif="501964843", **extra)))
    return r["id"]


def _guardar(valores):
    import services.partner_client_form as pcf

    return pcf.ClientFormIn(values=valores)


def _doc(com_form, cid):
    return next(d for d in (*com_form.partner_drafts.docs, *com_form.clients.docs) if d["id"] == cid)


@pytest.mark.asyncio
class TestOEsquemaEDoFormularioPublico:
    async def test_so_os_passos_do_titular_e_do_segundo_titular(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        form = await pcf.run_get_client_form(PT1, cid)
        assert [p["step"] for p in form["passos"]] == [1, 2]
        chaves = {f["field_key"] for p in form["passos"] for f in p["fields"]}
        assert {"name", "email", "phone", "nif", "compra_tipo", "titular2_name", "titular2_nif"} <= chaves
        # imóvel, financiamento e consentimento NÃO são da ficha da lead
        assert not chaves & {"finalidade", "salario_liquido", "consent_data", "tipo_imovel"}

    async def test_o_esquema_deriva_do_form_config_do_administrador(self, com_form):
        """Esconder um campo no administrador esconde-o aqui: sem lista paralela."""
        import services.partner_client_form as pcf
        from services.form_config_defaults import DEFAULT_FORM_CONFIG

        campos = [dict(f, is_visible=(f["field_key"] != "naturalidade")) for f in DEFAULT_FORM_CONFIG]
        com_form.form_config.docs.append({"type": "public_form", "fields": campos})
        cid = await _rascunho(com_form)
        form = await pcf.run_get_client_form(PT1, cid)
        chaves = {f["field_key"] for p in form["passos"] for f in p["fields"]}
        assert "naturalidade" not in chaves and "nacionalidade" in chaves

    async def test_os_valores_vem_decifrados_da_ficha(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        form = await pcf.run_get_client_form(PT1, cid)
        assert form["editavel"] is True
        assert form["values"]["name"] == "Joana Cliente" and form["values"]["nif"] == "501964843"
        assert form["values"]["email"] == "joana@cliente.pt"
        assert form["segundo_titular"] is False
        # As opções levam valor E etiqueta (o ecrã mostra a etiqueta).
        estado_civil = next(f for p in form["passos"] for f in p["fields"] if f["field_key"] == "estado_civil")
        assert {"value": "casado", "label": "Casado(a)"} in estado_civil["options"]
        compra = next(f for p in form["passos"] for f in p["fields"] if f["field_key"] == "compra_tipo")
        assert {"value": "outra_pessoa", "label": "outra_pessoa"} in compra["options"]

    async def test_outro_parceiro_nao_abre_o_formulario(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        with pytest.raises(HTTPException) as erro:
            await pcf.run_get_client_form(PT2, cid)
        assert erro.value.status_code == 404

    async def test_um_processo_nao_e_editavel(self, com_form):
        import services.partner_client_form as pcf

        _mundo(com_form)
        form = await pcf.run_get_client_form(PT1, "a-novo")
        assert form["editavel"] is False and form["values"] == {}
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, "a-novo", _guardar({"profissao": "x"}))
        assert erro.value.status_code == 409


@pytest.mark.asyncio
class TestGuardar:
    async def test_guarda_nos_sitios_da_ficha(self, com_form):
        import services.partner_client_form as pcf
        from services.encryption import decrypt_client_data

        cid = await _rascunho(com_form)
        r = await pcf.run_save_client_form(PT1, cid, _guardar({
            "name": "Joana Silva", "phone": "913333333", "profissao": "Engenheira",
            "estado_civil": "casado", "birth_date": "1990-05-17", "morada_fiscal": "Rua A, 1",
        }))
        assert r["success"] is True and "profissao" in r["campos_guardados"]
        ficha = decrypt_client_data(_doc(com_form, cid))
        assert ficha["nome"] == "Joana Silva"
        assert ficha["contacto"]["telefone"] == "913333333"
        assert ficha["dados_pessoais"]["profissao"] == "Engenheira"
        assert ficha["dados_pessoais"]["birth_date"] == "1990-05-17"

    async def test_a_pii_continua_cifrada_e_os_hashes_sao_recalculados(self, com_form):
        import services.partner_client_form as pcf
        from services.encryption import generate_nif_hash

        cid = await _rascunho(com_form)
        antes = _doc(com_form, cid)["dados_pessoais"].get("nif_hash")
        await pcf.run_save_client_form(PT1, cid, _guardar({"nif": "232119867"}))
        ficha = _doc(com_form, cid)
        assert str(ficha["dados_pessoais"]["nif"]).startswith("ENC:") and "232119867" not in repr(ficha)
        assert ficha["dados_pessoais"]["nif_hash"] == generate_nif_hash("232119867") != antes

    async def test_edita_tambem_a_lead_ja_libertada_para_a_equipa(self, com_form):
        import services.partner_client_form as pcf
        from tests.unit.test_parceiro_filtro_de_viabilidade import COMPROVATIVO, _enviar

        cid = await _rascunho(com_form)
        await _enviar(com_form, cid, COMPROVATIVO)
        assert any(c["id"] == cid for c in com_form.clients.docs)
        await pcf.run_save_client_form(PT1, cid, _guardar({"profissao": "Médica"}))
        assert _doc(com_form, cid)["dados_pessoais"]["profissao"] == "Médica"
        assert _doc(com_form, cid)["last_activity_at"]

    async def test_editar_regista_actividade_e_adia_a_expiracao(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        com_form.partner_drafts.docs[0]["last_activity_at"] = "2020-01-01T00:00:00+00:00"
        await pcf.run_save_client_form(PT1, cid, _guardar({"profissao": "x"}))
        assert com_form.partner_drafts.docs[0]["last_activity_at"] > "2026-01-01"

    @pytest.mark.parametrize("campo,valor", [
        ("nif", "123"), ("nif", "123456789"), ("email", "isto-nao-e-email"), ("phone", "abc"),
        ("birth_date", "17/05/1990"), ("birth_date", "1990-02-31"), ("estado_civil", "Inventado"),
    ])
    async def test_valores_invalidos_sao_400_e_nao_gravam_nada(self, com_form, campo, valor):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        antes = dict(_doc(com_form, cid)["dados_pessoais"])
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, cid, _guardar({"profissao": "Nova", campo: valor}))
        assert erro.value.status_code == 400
        assert _doc(com_form, cid)["dados_pessoais"] == antes, "uma validação falhada não grava o resto"

    @pytest.mark.parametrize("campo", ["lead_status", "assigned_to", "network_id", "partner_stage", "id", "finalidade", "consent_data"])
    async def test_campos_fora_do_esquema_sao_400_e_nunca_ignorados(self, com_form, campo):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, cid, _guardar({campo: "x"}))
        assert erro.value.status_code == 400 and campo in erro.value.detail

    async def test_o_corpo_recusa_chaves_a_mais(self):
        import services.partner_client_form as pcf
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            pcf.ClientFormIn(values={}, network_id="x")

    @pytest.mark.parametrize("campo", ["name", "email"])
    async def test_nome_e_email_nao_se_apagam(self, com_form, campo):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, cid, _guardar({campo: ""}))
        assert erro.value.status_code == 400

    async def test_outro_parceiro_nao_edita(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT2, cid, _guardar({"profissao": "x"}))
        assert erro.value.status_code == 404

    async def test_uma_lead_expirada_nao_se_edita(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        com_form.partner_drafts.docs[0]["partner_stage"] = "expirado"
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, cid, _guardar({"profissao": "x"}))
        assert erro.value.status_code == 409
        assert (await pcf.run_get_client_form(PT1, cid))["editavel"] is False


@pytest.mark.asyncio
class TestSegundoTitular:
    async def test_ligar_e_preencher_o_segundo_titular(self, com_form):
        import services.partner_client_form as pcf
        from services.encryption import decrypt_client_data

        cid = await _rascunho(com_form)
        r = await pcf.run_save_client_form(PT1, cid, _guardar({
            "compra_tipo": "outra_pessoa", "titular2_name": "Rui Silva",
            "titular2_nif": "232119867", "titular2_email": "rui@c.pt", "titular2_birth_date": "1988-01-02",
        }))
        assert r["segundo_titular"] is True
        t2 = decrypt_client_data(_doc(com_form, cid))["titular2_data"]
        # As chaves da ficha são as do registo público: sem o prefixo «titular2_».
        assert t2["name"] == "Rui Silva" and t2["nif"] == "232119867" and t2["birth_date"] == "1988-01-02"
        assert str(_doc(com_form, cid)["titular2_data"]["nif"]).startswith("ENC:")
        form = await pcf.run_get_client_form(PT1, cid)
        assert form["segundo_titular"] is True and form["values"]["titular2_name"] == "Rui Silva"

    async def test_preencher_sem_ligar_e_400(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, cid, _guardar({"titular2_name": "Rui"}))
        assert erro.value.status_code == 400
        assert not _doc(com_form, cid).get("titular2_data")

    async def test_ligado_exige_o_nome_do_segundo_titular(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, cid, _guardar({"compra_tipo": "outra_pessoa"}))
        assert erro.value.status_code == 400 and "2.º titular" in erro.value.detail

    async def test_desligar_apaga_os_dados_do_segundo_titular(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        await pcf.run_save_client_form(PT1, cid, _guardar({"compra_tipo": "outra_pessoa", "titular2_name": "Rui"}))
        r = await pcf.run_save_client_form(PT1, cid, _guardar({"compra_tipo": "individual"}))
        assert r["segundo_titular"] is False
        assert _doc(com_form, cid)["titular2_data"] == {}

    async def test_editar_outro_campo_nao_mexe_no_segundo_titular(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        await pcf.run_save_client_form(PT1, cid, _guardar({"compra_tipo": "outra_pessoa", "titular2_name": "Rui"}))
        await pcf.run_save_client_form(PT1, cid, _guardar({"profissao": "x"}))
        assert _doc(com_form, cid)["titular2_data"]["name"] == "Rui"

    async def test_um_nif_de_segundo_titular_invalido_e_400(self, com_form):
        import services.partner_client_form as pcf

        cid = await _rascunho(com_form)
        with pytest.raises(HTTPException) as erro:
            await pcf.run_save_client_form(PT1, cid, _guardar({
                "compra_tipo": "outra_pessoa", "titular2_name": "Rui", "titular2_nif": "123",
            }))
        assert erro.value.status_code == 400
