"""
«O Meu Perfil» do Portal espelha TODO o registo (Out 2026).

O perfil só mostrava o passo 1 do formulário de registo. O pedido: espelhar a totalidade
dos campos — segundo titular, imóvel pretendido e situação financeira, e o NIF (só para
ver) — e garantir que o `PUT /portal/me` os grava.

O QUE ESTES TESTES FIXAM
  1. O esquema usa o formulário REAL de omissão (`DEFAULT_FORM_CONFIG`), nunca um fixture
     inventado: uma secção que só existe num mock é a armadilha do `/portal/status`.
  2. O que se vê só para ler (NIF mascarado, nome do 2.º titular, listas de bancos) nunca é
     gravável — nem por um pedido forjado.
  3. Cada secção grava no cliente E espelha-se no processo (a cópia que o CRM lê primeiro),
     com os alias que o registo também escreve e a PII cifrada como no registo.
  4. Uma secção do 2.º titular só se escreve a quem declarou ter um.
  5. O registo público passa a guardar a situação financeira (o DTO descartava-a).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import portal_profile
from services import portal_profile_sections as sec
from services.form_config_defaults import DEFAULT_FORM_CONFIG
from services.portal_profile import ClientProfileUpdate
from services.portal_profile_schema import (
    SECCOES_DO_PERFIL,
    build_portal_profile_schema,
    portal_updatable_fields,
)


def _esquema_real():
    return build_portal_profile_schema([f for f in DEFAULT_FORM_CONFIG if f.get("is_visible")])


def _por_chave(esquema):
    return {c["field_key"]: c for c in esquema}


# ====================================================================
# 1. O esquema real
# ====================================================================

class TestOEsquemaReal:
    def test_as_quatro_seccoes_existem_pela_ordem_do_registo(self):
        vistas = []
        for c in _esquema_real():
            if c["section"] not in vistas:
                vistas.append(c["section"])
        assert vistas == [nome for nome, _ in SECCOES_DO_PERFIL]

    def test_a_morada_e_o_estado_civil_continuam_no_perfil(self):
        chaves = _por_chave(_esquema_real())
        assert chaves["morada_fiscal"]["section"] == "titular"
        assert chaves["estado_civil"]["section"] == "titular"

    def test_o_nif_aparece_so_de_leitura_nas_duas_pessoas(self):
        chaves = _por_chave(_esquema_real())
        assert chaves["nif"]["read_only"] and chaves["titular2_nif"]["read_only"]
        assert chaves["titular2_name"]["read_only"]

    def test_o_imovel_e_as_financas_trazem_os_campos_do_registo(self):
        chaves = _por_chave(_esquema_real())
        for esperado in ("finalidade", "tipo_imovel", "valor_maximo_imovel",
                         "salario_liquido", "employment_type", "employer_name", "capital_proprio"):
            assert esperado in chaves, esperado
        assert chaves["finalidade"]["destino"] == ("real_estate_data", "finalidade")
        assert chaves["salario_liquido"]["destino"] == ("financial_data", "salario_liquido")

    def test_as_listas_de_bancos_sao_so_de_leitura(self):
        chaves = _por_chave(_esquema_real())
        for lista in ("bancos_creditos", "tem_creditos_activos", "bancos_simulacoes"):
            assert chaves[lista]["read_only"] is True, lista

    def test_os_consentimentos_ficam_de_fora(self):
        assert "consent_data" not in _por_chave(_esquema_real())
        assert "consent_contact" not in _por_chave(_esquema_real())

    def test_o_que_e_so_de_leitura_nunca_entra_no_allowlist(self):
        permitidos = portal_updatable_fields(_esquema_real())
        assert "nif" not in permitidos["dados_pessoais"]
        assert "nif" not in permitidos["titular2_data"]
        assert "name" not in permitidos["titular2_data"]
        assert "bancos_creditos" not in permitidos["financial_data"]

    def test_o_allowlist_das_novas_secoes_vem_do_esquema(self):
        permitidos = portal_updatable_fields(_esquema_real())
        assert {"documento_id", "morada_fiscal"} <= permitidos["titular2_data"]
        assert {"finalidade", "tipo_imovel"} <= permitidos["real_estate_data"]
        assert {"salario_liquido", "employer_nif"} <= permitidos["financial_data"]

    def test_cada_seccao_tem_campos_a_vista(self):
        # Um cartão inteiro atrás de um acordeão seria pior do que não ter divulgação.
        esquema = _esquema_real()
        for nome, _ in SECCOES_DO_PERFIL:
            da_seccao = [c for c in esquema if c["section"] == nome and not c["read_only"]]
            assert any(c["is_primary"] for c in da_seccao), nome


# ====================================================================
# 2. Máscaras, resumos, tipos
# ====================================================================

class TestMascarasEResumos:
    @pytest.mark.parametrize("nif, esperado", [
        ("123456789", "••••••789"),
        (" 123 456 789 ", "••••••789"),
        ("12", "••"),
        ("", ""),
        (None, ""),
    ])
    def test_mascarar_nif(self, nif, esperado):
        assert sec.mascarar_nif(nif) == esperado

    def test_a_mascara_nunca_contem_mais_de_tres_digitos_do_nif(self):
        assert "456" not in sec.mascarar_nif("123456789")

    def test_resumir_lista_de_bancos(self):
        assert sec.resumir_lista([{"banco": "BPI", "valor": 12000}, "CGD"]) == "BPI (12000 €), CGD"
        assert sec.resumir_lista(None) == "" and sec.resumir_lista([]) == ""


def _campo(tipo, **extra):
    return {"field_key": "x", "field_type": tipo, "options": [], **extra}


class TestTiposDoCampo:
    def test_numero_aceita_virgula_decimal_e_vazio_apaga(self):
        assert sec._coagir(_campo("number"), "1234,5") == (True, 1234.5)
        assert sec._coagir(_campo("number"), "") == (True, None)
        assert sec._coagir(_campo("number"), None) == (True, None)

    @pytest.mark.parametrize("lixo", ["abc", "1e999999", "nan", "inf", [1], {"a": 1}])
    def test_numero_invalido_e_recusado(self, lixo):
        assert sec._coagir(_campo("number"), lixo)[0] is False

    def test_numero_zero_e_um_valor(self):
        # A armadilha do `|| 30`: zero não é «sem valor».
        assert sec._coagir(_campo("number"), 0) == (True, 0.0)
        assert sec._coagir(_campo("number"), "0") == (True, 0.0)

    def test_checkbox_simples_e_booleano(self):
        assert sec._coagir(_campo("checkbox"), True) == (True, True)
        assert sec._coagir(_campo("checkbox"), False) == (True, False)
        assert sec._coagir(_campo("checkbox"), "sim")[0] is False

    def test_checkbox_com_opcoes_e_uma_lista_de_opcoes_validas(self):
        campo = _campo("checkbox", options=["Elevador", "Garagem"])
        assert sec._coagir(campo, ["Garagem"]) == (True, ["Garagem"])
        assert sec._coagir(campo, ["Piscina"])[0] is False
        assert sec._coagir(campo, "Garagem")[0] is False
        assert sec._coagir(campo, []) == (True, None)

    def test_select_so_aceita_opcoes_do_formulario(self):
        campo = _campo("select", options=[{"value": "solteiro", "label": "S"}, "casado"])
        assert sec._coagir(campo, "casado") == (True, "casado")
        assert sec._coagir(campo, "solteiro") == (True, "solteiro")
        assert sec._coagir(campo, "viuvo")[0] is False

    def test_texto_vazio_apaga_e_estruturas_sao_recusadas(self):
        assert sec._coagir(_campo("text"), "   ") == (True, "")
        assert sec._coagir(_campo("text"), {"a": 1})[0] is False
        assert sec._coagir(_campo("text"), ["a"])[0] is False


class TestAliases:
    def test_o_salario_escreve_os_alias_e_o_anual(self):
        escritos = sec.expandir_aliases("financial_data", "salario_liquido", 1500.0)
        assert escritos == {
            "salario_liquido": 1500.0, "monthly_income": 1500.0,
            "rendimento_mensal": 1500.0, "rendimento_anual": 18000.0,
        }

    def test_apagar_o_salario_apaga_tambem_o_anual(self):
        escritos = sec.expandir_aliases("financial_data", "salario_liquido", None)
        assert escritos["rendimento_anual"] is None and escritos["monthly_income"] is None

    def test_emprego_e_imovel(self):
        assert sec.expandir_aliases("financial_data", "employer_name", "ACME")["empresa"] == "ACME"
        assert sec.expandir_aliases("financial_data", "employment_type", "efetivo")["tipo_contrato"] == "efetivo"
        escritos = sec.expandir_aliases("real_estate_data", "ja_tem_casa_escolhida", True)
        assert escritos["ja_tem_imovel"] is True and escritos["has_property"] is True

    def test_um_campo_sem_alias_escreve_so_o_seu_nome(self):
        assert sec.expandir_aliases("real_estate_data", "localizacao", "Lisboa") == {"localizacao": "Lisboa"}


# ====================================================================
# 3. Leitura: o processo manda
# ====================================================================

class TestLeituraDasSeccoes:
    def test_o_processo_manda_e_o_cliente_preenche_o_que_falta(self):
        cliente = {"dados_financeiros": {"salario_liquido": 1000, "capital_proprio": 5000}}
        processo = {"financial_data": {"salario_liquido": 1800}}
        valores = sec.valores_da_seccao("financial_data", cliente, processo)
        assert valores["salario_liquido"] == 1800  # a cópia que a equipa vê
        assert valores["capital_proprio"] == 5000  # só o cliente a tem

    def test_um_vazio_do_processo_nao_apaga_o_valor_do_cliente(self):
        cliente = {"dados_financeiros": {"employer_name": "ACME"}}
        processo = {"financial_data": {"employer_name": ""}}
        assert sec.valores_da_seccao("financial_data", cliente, processo)["employer_name"] == "ACME"

    def test_o_imovel_le_o_pending_e_cai_no_legado(self):
        assert sec.valores_da_seccao(
            "real_estate_data", {"pending_real_estate_data": {"localizacao": "Porto"}}, None
        )["localizacao"] == "Porto"
        assert sec.valores_da_seccao(
            "real_estate_data", {"dados_imobiliarios": {"localizacao": "Faro"}}, None
        )["localizacao"] == "Faro"

    def test_decifra_e_ignora_indices_cegos(self):
        from services.encryption import encrypt_value

        cliente = {"titular2_data": {"documento_id": encrypt_value("CC123"), "nif_hash": "abc"}}
        valores = sec.valores_da_seccao("titular2_data", cliente, None)
        assert valores["documento_id"] == "CC123"
        assert "nif_hash" not in valores

    def test_tem_segundo_titular(self):
        assert sec.tem_segundo_titular({"dados_pessoais": {"compra_tipo": "outra_pessoa"}})
        assert sec.tem_segundo_titular({"titular2_data": {"nif": "x"}})
        assert sec.tem_segundo_titular({}, {"titular2_data": {"name": "Rui"}})
        assert not sec.tem_segundo_titular({"dados_pessoais": {"compra_tipo": "individual"}})
        # «Presente mas vazio» não é um titular (o registo grava as chaves vazias).
        assert not sec.tem_segundo_titular({"titular2_data": {"name": "", "nif": "", "email": ""}})


# ====================================================================
# 4. Escrita
# ====================================================================

CLIENTE_INDIVIDUAL = {"id": "c-1", "dados_pessoais": {"compra_tipo": "individual"}}
CLIENTE_COM_SEGUNDO = {
    "id": "c-1", "dados_pessoais": {"compra_tipo": "outra_pessoa"},
    "titular2_data": {"name": "Rui", "nif": "999888777"},
}


def _construir(pedido, cliente):
    esquema = _esquema_real()
    recusados: list = []
    set_do_cliente, espelhos = sec.construir_update_das_seccoes(
        pedido, cliente=cliente, schema=esquema,
        permitidos=portal_updatable_fields(esquema), agora="2026-10-13T10:00:00+00:00",
        recusados=recusados,
    )
    return set_do_cliente, espelhos, recusados


class TestAEscrita:
    def test_o_salario_grava_o_canonico_os_alias_e_o_anual_no_cliente_e_no_espelho(self):
        set_c, espelhos, recusados = _construir(
            {"financial_data": {"salario_liquido": "1500"}}, CLIENTE_INDIVIDUAL)
        assert recusados == []
        assert set_c["dados_financeiros.salario_liquido"] == 1500.0
        assert set_c["dados_financeiros.monthly_income"] == 1500.0
        assert set_c["dados_financeiros.rendimento_anual"] == 18000.0
        assert espelhos["financial_data"]["rendimento_mensal"] == 1500.0
        assert set_c["updated_at"]

    def test_o_nif_da_entidade_patronal_vai_cifrado(self):
        set_c, espelhos, _ = _construir(
            {"financial_data": {"employer_nif": "501234567"}}, CLIENTE_INDIVIDUAL)
        assert set_c["dados_financeiros.employer_nif"].startswith("ENC:")
        assert espelhos["financial_data"]["employer_nif"].startswith("ENC:")
        assert "501234567" not in str(set_c)

    def test_o_imovel_vai_para_o_pending_do_cliente(self):
        set_c, espelhos, _ = _construir(
            {"real_estate_data": {"localizacao": "Lisboa", "caracteristicas": ["Garagem"]}},
            CLIENTE_INDIVIDUAL)
        assert set_c["pending_real_estate_data.localizacao"] == "Lisboa"
        assert set_c["pending_real_estate_data.caracteristicas"] == ["Garagem"]
        assert espelhos["real_estate_data"]["localizacao"] == "Lisboa"

    def test_o_segundo_titular_grava_cifrando_a_pii(self):
        set_c, espelhos, recusados = _construir(
            {"titular2_data": {"documento_id": "CC999", "naturalidade": "Braga"}},
            CLIENTE_COM_SEGUNDO)
        assert recusados == []
        assert set_c["titular2_data.documento_id"].startswith("ENC:")
        assert set_c["titular2_data.naturalidade"] == "Braga"

    def test_quem_nao_declarou_segundo_titular_nao_o_cria_pelo_perfil(self):
        set_c, espelhos, recusados = _construir(
            {"titular2_data": {"naturalidade": "Braga"}}, CLIENTE_INDIVIDUAL)
        assert set_c == {} and espelhos == {}
        assert recusados == ["naturalidade"]

    @pytest.mark.parametrize("grupo, campo", [
        ("titular2_data", "nif"), ("titular2_data", "name"),
        ("financial_data", "bancos_creditos"), ("financial_data", "tem_creditos_activos"),
        ("financial_data", "iban"), ("real_estate_data", "campo_inventado"),
        ("financial_data", "monthly_income"),  # alias: só se escreve pelo canónico
    ])
    def test_o_que_nao_esta_no_esquema_editavel_e_recusado_e_dito(self, grupo, campo):
        set_c, espelhos, recusados = _construir({grupo: {campo: "x"}}, CLIENTE_COM_SEGUNDO)
        assert set_c == {} and espelhos == {}
        assert recusados == [campo]

    def test_tipo_errado_e_recusado_e_nao_vira_texto(self):
        set_c, _, recusados = _construir(
            {"financial_data": {"salario_liquido": "muito"}}, CLIENTE_INDIVIDUAL)
        assert set_c == {} and recusados == ["salario_liquido"]

    def test_apagar_um_numero_grava_none_e_um_texto_grava_vazio(self):
        set_c, _, _ = _construir(
            {"financial_data": {"capital_proprio": "", "employer_name": ""}}, CLIENTE_INDIVIDUAL)
        assert set_c["dados_financeiros.capital_proprio"] is None
        assert set_c["dados_financeiros.employer_name"] == ""
        assert set_c["dados_financeiros.empresa"] == ""  # o alias apaga-se com o canónico

    def test_um_grupo_que_nao_e_dicionario_e_recusado(self):
        _, _, recusados = _construir({"financial_data": ["x"]}, CLIENTE_INDIVIDUAL)
        assert recusados == ["financial_data"]

    def test_grupos_desconhecidos_sao_ignorados(self):
        set_c, espelhos, recusados = _construir({"contacto": {"email": "x"}}, CLIENTE_INDIVIDUAL)
        assert (set_c, espelhos, recusados) == ({}, {}, [])


# ====================================================================
# 5. Espelho nos processos
# ====================================================================

class TestEspelhoNosProcessos:
    @pytest.mark.asyncio
    async def test_grava_na_copia_do_processo_com_chaves_pontuadas(self, fake_async_db):
        await fake_async_db.processes.insert_one(
            {"id": "p-1", "financial_data": {"salario_liquido": 1000, "outro": 1}})
        tocados = await sec.espelhar_nos_processos(
            fake_async_db, ["p-1"], {"financial_data": {"salario_liquido": 1500.0}})
        assert tocados == 1
        p = await fake_async_db.processes.find_one({"id": "p-1"})
        assert p["financial_data"] == {"salario_liquido": 1500.0, "outro": 1}  # não pisa o resto

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", [{"titular2_data": None}, {}])
    async def test_grupo_nulo_ou_ausente_cria_se_inteiro(self, fake_async_db, estado):
        # O MongoDB recusa `titular2_data.nif` sobre `null`; o grupo nasce inteiro.
        await fake_async_db.processes.insert_one({"id": "p-1", **estado})
        await sec.espelhar_nos_processos(
            fake_async_db, ["p-1"], {"titular2_data": {"naturalidade": "Braga"}})
        p = await fake_async_db.processes.find_one({"id": "p-1"})
        assert p["titular2_data"] == {"naturalidade": "Braga"}

    @pytest.mark.asyncio
    async def test_so_toca_nos_processos_pedidos(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "p-1", "financial_data": {}})
        await fake_async_db.processes.insert_one({"id": "p-2", "financial_data": {}})
        await sec.espelhar_nos_processos(fake_async_db, ["p-1"], {"financial_data": {"a": 1}})
        outro = await fake_async_db.processes.find_one({"id": "p-2"})
        assert outro["financial_data"] == {}

    @pytest.mark.asyncio
    async def test_sem_espelhos_ou_sem_processos_nao_faz_nada(self, fake_async_db):
        assert await sec.espelhar_nos_processos(fake_async_db, [], {"financial_data": {"a": 1}}) == 0
        assert await sec.espelhar_nos_processos(fake_async_db, ["p-1"], {}) == 0


# ====================================================================
# 6. O endpoint (serviço real, fronteiras falseadas)
# ====================================================================

@pytest.fixture
def mundo(fake_async_db):
    esquema = _esquema_real()
    with patch.object(portal_profile, "db", fake_async_db), \
         patch.object(portal_profile, "_esquema_do_cliente", AsyncMock(return_value=esquema)), \
         patch.object(portal_profile, "carregar_campos_editaveis",
                      AsyncMock(return_value=portal_updatable_fields(esquema))), \
         patch("services.history.db", fake_async_db), \
         patch("database.db", fake_async_db):
        yield fake_async_db


async def _semear(bd, cliente=None, processo=None):
    await bd.clients.insert_one({
        "id": "c-1", "nome": "Joana", "process_ids": ["p-1"] if processo is not None else [],
        **(cliente or {}),
    })
    if processo is not None:
        await bd.processes.insert_one({"id": "p-1", "status": None, **processo})


class TestOEndpointGrava:
    @pytest.mark.asyncio
    async def test_a_situacao_financeira_chega_ao_cliente_e_ao_processo(self, mundo):
        await _semear(mundo, {"dados_financeiros": {"salario_liquido": 1000}},
                      {"financial_data": {"salario_liquido": 1000, "monthly_income": 1000}})
        resposta = await portal_profile.run_update_client_profile(
            ClientProfileUpdate(financial_data={"salario_liquido": 2000, "employer_name": "ACME"}),
            {"client_id": "c-1"},
        )
        assert resposta["success"] and resposta["rejected_fields"] == []
        assert "financial_data" in resposta["updated_fields"]
        cliente = await mundo.clients.find_one({"id": "c-1"})
        assert cliente["dados_financeiros"]["salario_liquido"] == 2000.0
        assert cliente["dados_financeiros"]["empresa"] == "ACME"
        processo = await mundo.processes.find_one({"id": "p-1"})
        # É a cópia que o CRM mostra em «Detalhes do Processo».
        assert processo["financial_data"]["salario_liquido"] == 2000.0
        assert processo["financial_data"]["monthly_income"] == 2000.0
        assert processo["financial_data"]["rendimento_anual"] == 24000.0
        assert processo["financial_data"]["employer_name"] == "ACME"

    @pytest.mark.asyncio
    async def test_sem_processo_grava_so_no_cliente(self, mundo):
        await _semear(mundo)
        await portal_profile.run_update_client_profile(
            ClientProfileUpdate(real_estate_data={"localizacao": "Lisboa"}), {"client_id": "c-1"})
        cliente = await mundo.clients.find_one({"id": "c-1"})
        assert cliente["pending_real_estate_data"]["localizacao"] == "Lisboa"

    @pytest.mark.asyncio
    async def test_um_campo_recusado_e_dito_e_o_resto_grava(self, mundo):
        await _semear(mundo)
        resposta = await portal_profile.run_update_client_profile(
            ClientProfileUpdate(financial_data={"salario_liquido": 900, "bancos_creditos": [1]}),
            {"client_id": "c-1"},
        )
        assert resposta["rejected_fields"] == ["bancos_creditos"]
        cliente = await mundo.clients.find_one({"id": "c-1"})
        assert cliente["dados_financeiros"]["salario_liquido"] == 900.0
        assert "bancos_creditos" not in cliente["dados_financeiros"]

    @pytest.mark.asyncio
    async def test_so_seccoes_a_recusar_nao_escreve_nada(self, mundo):
        await _semear(mundo)
        resposta = await portal_profile.run_update_client_profile(
            ClientProfileUpdate(titular2_data={"naturalidade": "Braga"}), {"client_id": "c-1"})
        assert resposta["updated_fields"] == []
        assert resposta["rejected_fields"] == ["naturalidade"]
        cliente = await mundo.clients.find_one({"id": "c-1"})
        assert "titular2_data" not in cliente

    @pytest.mark.asyncio
    async def test_perfil_trancado_nao_grava_as_novas_seccoes(self, mundo):
        from fastapi import HTTPException

        await _semear(mundo, None, {"status": "analise_credito", "portal_submitted_at": "2026-10-01"})
        with patch.object(portal_profile, "_fases_dos_processos_do_cliente", AsyncMock(return_value=[])):
            with pytest.raises(HTTPException) as erro:
                await portal_profile.run_update_client_profile(
                    ClientProfileUpdate(financial_data={"salario_liquido": 5000}),
                    {"client_id": "c-1"},
                )
        assert erro.value.status_code == 403
        processo = await mundo.processes.find_one({"id": "p-1"})
        assert "financial_data" not in processo

    @pytest.mark.asyncio
    async def test_o_historico_regista_nomes_e_nunca_valores(self, mundo):
        await _semear(mundo, {"dados_pessoais": {"compra_tipo": "outra_pessoa"}}, {})
        await portal_profile.run_update_client_profile(
            ClientProfileUpdate(titular2_data={"documento_id": "CC-SEGREDO-9"},
                                financial_data={"salario_liquido": 7777}),
            {"client_id": "c-1"},
        )
        entradas = await mundo.history.find({"process_id": "p-1"}, {"_id": 0}).to_list(10)
        assert entradas
        texto = " ".join(str(v) for e in entradas for v in e.values())
        assert "CC-SEGREDO-9" not in texto and "7777" not in texto
        assert "documento_id" in texto and "salario_liquido" in texto


# ====================================================================
# 7. O GET devolve as secções (e nunca o que é só de leitura em claro)
# ====================================================================

class TestOGetDevolveAsSeccoes:
    @pytest.fixture
    def leitura(self, fake_async_db):
        campos = [f for f in DEFAULT_FORM_CONFIG if f.get("is_visible")]
        with patch.object(portal_profile, "db", fake_async_db), \
             patch("services.public_form_config.load_merged_form_fields",
                   AsyncMock(return_value=campos)), \
             patch.object(portal_profile, "_fases_dos_processos_do_cliente", AsyncMock(return_value=[])), \
             patch("database.db", fake_async_db):
            yield fake_async_db

    @pytest.mark.asyncio
    async def test_devolve_secoes_valores_e_nif_mascarado(self, leitura):
        from services.encryption import encrypt_value

        await _semear(leitura, {
            "dados_pessoais": {"nif": encrypt_value("123456789"), "compra_tipo": "outra_pessoa",
                               "estado_civil": "casado"},
            "titular2_data": {"name": "Rui", "nif": encrypt_value("999888777"),
                              "naturalidade": "Braga"},
            "pending_real_estate_data": {"localizacao": "Lisboa"},
            "dados_financeiros": {"salario_liquido": 1500,
                                  "bancos_creditos": [{"banco": "BPI", "valor": 9000}]},
        }, {"financial_data": {"capital_proprio": 40000}})
        perfil = await portal_profile.run_get_client_profile({"client_id": "c-1"})

        assert [s["id"] for s in perfil["secoes"]] == ["titular", "segundo_titular", "imovel", "financeiro"]
        assert perfil["tem_segundo_titular"] is True
        assert perfil["titular2_data"]["naturalidade"] == "Braga"
        assert perfil["real_estate_data"]["localizacao"] == "Lisboa"
        assert perfil["financial_data"]["salario_liquido"] == 1500
        assert perfil["financial_data"]["capital_proprio"] == 40000  # veio do processo
        assert perfil["somente_leitura"]["nif"] == "••••••789"
        assert perfil["somente_leitura"]["titular2_nif"] == "••••••777"
        assert perfil["somente_leitura"]["titular2_name"] == "Rui"
        assert perfil["somente_leitura"]["bancos_creditos"] == "BPI (9000 €)"

    @pytest.mark.asyncio
    async def test_nenhum_nif_nem_lista_de_bancos_sai_em_claro(self, leitura):
        import json

        from services.encryption import encrypt_value

        await _semear(leitura, {
            "dados_pessoais": {"nif": encrypt_value("123456789"), "compra_tipo": "outra_pessoa"},
            "titular2_data": {"name": "Rui", "nif": encrypt_value("999888777")},
            "dados_financeiros": {"bancos_creditos": [{"banco": "BPI", "valor": 9000}]},
        })
        bruto = json.dumps(await portal_profile.run_get_client_profile({"client_id": "c-1"}),
                           default=str)
        assert "123456789" not in bruto and "999888777" not in bruto
        assert '"banco"' not in bruto  # a lista estruturada só viaja resumida

    @pytest.mark.asyncio
    async def test_sem_segundo_titular_a_seccao_nem_aparece(self, leitura):
        await _semear(leitura, {"dados_pessoais": {"compra_tipo": "individual"}})
        perfil = await portal_profile.run_get_client_profile({"client_id": "c-1"})
        assert perfil["tem_segundo_titular"] is False
        assert "segundo_titular" not in [s["id"] for s in perfil["secoes"]]
        assert not [c for c in perfil["form_schema"] if c["section"] == "segundo_titular"]

    @pytest.mark.asyncio
    async def test_se_as_seccoes_falham_o_perfil_abre_com_os_dados_pessoais(self, leitura):
        await _semear(leitura, {"dados_pessoais": {"estado_civil": "casado"}})
        with patch("services.portal_profile_sections.valores_da_seccao", side_effect=RuntimeError("x")):
            perfil = await portal_profile.run_get_client_profile({"client_id": "c-1"})
        assert perfil["dados_pessoais"]["estado_civil"] == "casado"
        assert {c["section"] for c in perfil["form_schema"]} == {"titular"}


# ====================================================================
# 8. O registo público guarda a situação financeira
# ====================================================================

class TestORegistoGuardaAsFinancas:
    def test_o_dto_declara_financial_data(self):
        from models.process import PublicClientRegistration

        dto = PublicClientRegistration(
            name="Ana Silva", email="ana@x.pt", phone="912345678", process_type="ambos",
            financial_data={"salario_liquido": 1500, "employer_nif": "501234567"},
        )
        assert dto.financial_data == {"salario_liquido": 1500, "employer_nif": "501234567"}

    def test_o_registo_cifra_o_nif_da_entidade_patronal_e_ignora_lixo(self):
        gravado = sec.dados_financeiros_do_registo(
            {"salario_liquido": 1500, "employer_nif": "501234567", "x_hash": "a"})
        assert gravado["salario_liquido"] == 1500
        assert gravado["employer_nif"].startswith("ENC:")
        assert "x_hash" not in gravado
        assert sec.dados_financeiros_do_registo(None) == {}
        assert sec.dados_financeiros_do_registo("x") == {}

    def test_o_servico_usa_o_helper_em_vez_de_um_dicionario_vazio(self):
        import inspect

        from tests.unit.helpers_fonte import codigo_sem_comentarios
        import services.public_registration as modulo

        codigo = codigo_sem_comentarios(inspect.getsource(modulo))
        assert "dados_financeiros_do_registo(data.financial_data)" in codigo
        assert '"dados_financeiros": {}' not in codigo
