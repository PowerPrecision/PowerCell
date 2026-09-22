"""
RGPD do 2.º titular: o PDF tem de vir preenchido (Missão de Limpeza, ponto 4).

O DEFEITO
---------
Três instâncias da MESMA confusão — tratar "presente mas vazio" como
"presente":

  1. `_titular_fallback_data` fazia `fallback.setdefault("nif", ...)` sobre
     o `titular2_data`. O formulário público grava esse dicionário com as
     chaves PRESENTES E VAZIAS (`{"nif": ""}`), pelo que o `setdefault` era
     um no-op e os dados do cliente ligado nunca chegavam lá.

  2. O render fazia `consent_data.get("contribuinte", personal_data[...])`.
     `dict.get(k, default)` só devolve o default quando a chave FALTA — um
     `""` submetido pelo formulário vence o fallback.

  3. `{{CODIGO_POSTAL}}`, `{{TIPO_DOCUMENTO}}` e `{{NUMERO_DOCUMENTO}}` não
     tinham fallback nenhum, e o `documento_id` que o fallback recolhia
     nunca era usado.

Resultado: o PDF do 2.º titular saía com linhas em branco mesmo com o
cliente ligado e totalmente preenchido na base de dados.

PORQUE IMPORTA
--------------
É um documento legal que o cliente assina. Um RGPD em branco não é um
inconveniente estético: é um consentimento que não identifica quem o deu.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import rgpd_service
from services.rgpd_service import (
    TITULAR_FIRST,
    TITULAR_SECOND,
    _titular_fallback_data,
    partes_do_documento,
    primeiro_preenchido,
)

CLIENTE_2 = {
    "id": "cli-2",
    "nome": "Bruno Costa",
    "dados_pessoais": {
        "nif": "234567891",
        "morada_fiscal": "Rua B, 22, Porto",
        "documento_id": "11112222 3 ZZ4",
        "data_validade_cc": "2031-05-10",
        "codigo_postal": "4000-100",
    },
}

PROCESSO_BASE = {
    "id": "proc-1",
    "client_name": "Ana Martins",
    "personal_data": {"nif": "111111111", "morada_fiscal": "Rua A, 1, Lisboa"},
    "second_client_id": "cli-2",
}


def _com_cliente(cliente=CLIENTE_2):
    fake = MagicMock()
    fake.clients.find_one = AsyncMock(return_value=dict(cliente) if cliente else None)
    return fake


async def _fallback(processo, titular=TITULAR_SECOND, cliente=CLIENTE_2):
    with patch.object(rgpd_service, "db", _com_cliente(cliente)), \
         patch("services.encryption.decrypt_client_data", lambda d: d):
        return await _titular_fallback_data(processo, titular)


# ====================================================================
# 1. O CAMPO VAZIO NÃO PODE BLOQUEAR O ENRIQUECIMENTO
# ====================================================================


class TestCamposVaziosNoTitular2Data:
    @pytest.mark.asyncio
    async def test_nif_vazio_e_preenchido_pelo_cliente_ligado(self):
        # O CASO DO DEFEITO: o formulário público grava as chaves vazias, e
        # `setdefault` não as substituía.
        processo = {**PROCESSO_BASE, "titular2_data": {"nif": "", "nome": "Bruno Costa"}}
        dados = await _fallback(processo)
        assert dados["nif"] == "234567891"

    @pytest.mark.asyncio
    async def test_morada_vazia_e_preenchida(self):
        processo = {**PROCESSO_BASE, "titular2_data": {"morada_fiscal": ""}}
        dados = await _fallback(processo)
        assert dados["morada_fiscal"] == "Rua B, 22, Porto"

    @pytest.mark.asyncio
    async def test_none_conta_como_vazio(self):
        processo = {**PROCESSO_BASE, "titular2_data": {"nif": None}}
        dados = await _fallback(processo)
        assert dados["nif"] == "234567891"

    @pytest.mark.asyncio
    async def test_espacos_contam_como_vazio(self):
        processo = {**PROCESSO_BASE, "titular2_data": {"nif": "   "}}
        dados = await _fallback(processo)
        assert dados["nif"] == "234567891"

    @pytest.mark.asyncio
    async def test_valor_real_no_processo_vence_o_do_cliente(self):
        # O que está no processo foi escrito mais tarde: é mais recente.
        processo = {**PROCESSO_BASE, "titular2_data": {"nif": "999999999"}}
        dados = await _fallback(processo)
        assert dados["nif"] == "999999999"


# ====================================================================
# 2. O FALLBACK TEM DE TRAZER O QUE O PDF PRECISA
# ====================================================================


class TestCoberturaDosCampos:
    @pytest.mark.asyncio
    async def test_traz_a_validade_do_documento(self):
        # Não vinha: o fallback só recolhia nif/morada/documento.
        dados = await _fallback({**PROCESSO_BASE, "titular2_data": {}})
        assert dados.get("data_validade_cc") == "2031-05-10"

    @pytest.mark.asyncio
    async def test_traz_o_numero_do_documento(self):
        dados = await _fallback({**PROCESSO_BASE, "titular2_data": {}})
        assert dados.get("documento_id") == "11112222 3 ZZ4"

    @pytest.mark.asyncio
    async def test_traz_o_nome_do_titular(self):
        dados = await _fallback({**PROCESSO_BASE, "titular2_data": {}})
        assert dados.get("nome") == "Bruno Costa"

    @pytest.mark.asyncio
    async def test_traz_o_codigo_postal(self):
        dados = await _fallback({**PROCESSO_BASE, "titular2_data": {}})
        assert dados.get("codigo_postal") == "4000-100"


# ====================================================================
# 3. O 1.º TITULAR NÃO PODE SER AFECTADO
# ====================================================================


class TestPrimeiroTitularIntacto:
    @pytest.mark.asyncio
    async def test_devolve_o_personal_data_do_processo(self):
        dados = await _fallback(PROCESSO_BASE, titular=TITULAR_FIRST)
        assert dados["nif"] == "111111111"

    @pytest.mark.asyncio
    async def test_nunca_mistura_dados_do_segundo(self):
        # O erro oposto seria pior: assinar o RGPD do 1.º com o NIF do 2.º.
        dados = await _fallback(PROCESSO_BASE, titular=TITULAR_FIRST)
        assert dados.get("nif") != "234567891"


# ====================================================================
# 4. DEGRADAÇÃO
# ====================================================================


class TestDegradacao:
    @pytest.mark.asyncio
    async def test_sem_cliente_ligado_usa_o_que_ha_no_processo(self):
        processo = {
            "id": "p",
            "titular2_data": {"nif": "555555555", "nome": "Bruno"},
        }
        dados = await _fallback(processo, cliente=None)
        assert dados["nif"] == "555555555"

    @pytest.mark.asyncio
    async def test_sem_nada_devolve_dicionario_vazio_e_nao_rebenta(self):
        dados = await _fallback({"id": "p"}, cliente=None)
        assert dados == {} or all(not v for v in dados.values())


# ====================================================================
# 5. O RENDER: "" SUBMETIDO NÃO PODE VENCER O DADO REAL
# ====================================================================


TEMPLATE = (
    "Eu, {{NOME_CLIENTE}}, titular do {{TIPO_DOCUMENTO}} n.o "
    "{{NUMERO_DOCUMENTO}}, valido ate {{VALIDADE_DOCUMENTO}}, contribuinte "
    "{{CONTRIBUINTE}}, residente em {{MORADA}}, {{CODIGO_POSTAL}}."
)


async def _render(processo, consent_data, titular=TITULAR_SECOND, cliente=CLIENTE_2):
    fake = _com_cliente(cliente)
    fake.processes.find_one = AsyncMock(return_value=dict(processo))
    with patch.object(rgpd_service, "db", fake), \
         patch("services.encryption.decrypt_client_data", lambda d: d), \
         patch("services.process_service.decrypt_sensitive_data", lambda d: d), \
         patch(
             "services.rgpd_templates._get_active_rgpd_template",
             AsyncMock(return_value=TEMPLATE),
         ), \
         patch.object(
             rgpd_service,
             "_get_company_legal_data",
             AsyncMock(
                 return_value={
                     "nome": "E", "nif": "5", "morada": "M",
                     "email": "e@e.pt", "contacto": "C",
                 }
             ),
         ):
        return await rgpd_service._get_rendered_rgpd_text(
            "proc-1", {}, consent_data, titular=titular
        )


class TestRenderDoSegundoTitular:
    @pytest.mark.asyncio
    async def test_contribuinte_vazio_no_formulario_cai_no_dado_real(self):
        # `consent_data.get("contribuinte", fallback)` devolvia "" porque a
        # chave EXISTE. O fallback nunca chegava a ser avaliado.
        texto = await _render(
            {**PROCESSO_BASE, "titular2_data": {}}, {"contribuinte": ""}
        )
        assert "234567891" in texto

    @pytest.mark.asyncio
    async def test_morada_vazia_cai_no_dado_real(self):
        texto = await _render({**PROCESSO_BASE, "titular2_data": {}}, {"morada": ""})
        assert "Rua B, 22, Porto" in texto

    @pytest.mark.asyncio
    async def test_numero_do_documento_passa_a_ter_fallback(self):
        # Não tinha nenhum: saía sempre em branco no PDF do 2.º titular.
        texto = await _render({**PROCESSO_BASE, "titular2_data": {}}, {})
        assert "11112222 3 ZZ4" in texto

    @pytest.mark.asyncio
    async def test_codigo_postal_passa_a_ter_fallback(self):
        texto = await _render({**PROCESSO_BASE, "titular2_data": {}}, {})
        assert "4000-100" in texto

    @pytest.mark.asyncio
    async def test_validade_do_documento_passa_a_ter_fallback(self):
        texto = await _render({**PROCESSO_BASE, "titular2_data": {}}, {})
        assert "2031-05-10" in texto

    @pytest.mark.asyncio
    async def test_o_nome_e_o_do_segundo_titular_e_nunca_o_do_primeiro(self):
        # O erro mais grave possível: o RGPD do 2.º titular identificar o 1.º.
        texto = await _render({**PROCESSO_BASE, "titular2_data": {}}, {})
        assert "Bruno Costa" in texto
        assert "Ana Martins" not in texto

    @pytest.mark.asyncio
    async def test_o_que_o_titular_escreveu_vence_a_ficha(self):
        # Um valor REAL no formulário é uma correcção deliberada.
        texto = await _render(
            {**PROCESSO_BASE, "titular2_data": {}}, {"contribuinte": "999999999"}
        )
        assert "999999999" in texto
        assert "234567891" not in texto

    @pytest.mark.asyncio
    async def test_o_primeiro_titular_continua_a_render_os_seus_dados(self):
        texto = await _render(
            PROCESSO_BASE, {}, titular=TITULAR_FIRST
        )
        assert "111111111" in texto
        assert "Ana Martins" in texto


# ====================================================================
# 6. OS HELPERS, ISOLADOS
# ====================================================================


class TestHelpers:
    def test_primeiro_preenchido_salta_vazios(self):
        assert primeiro_preenchido("", None, "   ", "valor") == "valor"

    def test_primeiro_preenchido_devolve_a_omissao(self):
        assert primeiro_preenchido("", None, omissao="—") == "—"

    def test_primeiro_preenchido_aceita_zero_como_valor(self):
        # 0 é um dado, não uma ausência.
        assert primeiro_preenchido(0, "x") == 0

    def test_documento_plano(self):
        assert partes_do_documento("12345678") == ("", "12345678")

    def test_documento_estruturado(self):
        assert partes_do_documento(
            {"type": "cartao_de_cidadao", "number": "999"}
        ) == ("cartao_de_cidadao", "999")

    def test_documento_ausente(self):
        assert partes_do_documento(None) == ("", "")
