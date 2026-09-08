"""Testes unitários — PACOTE DG-2: dados legais da empresa no RGPD/Minuta.

Cobre a correção da injeção de variáveis da empresa nos documentos legais
(RGPD + Minuta de Exclusividade), SEM I/O de MongoDB (regra arquitetural
de tests/unit — ver conftest.py):

- ``_get_company_legal_data`` lê ESTRITAMENTE o SystemConfig global
  (``_id: "main"``, secção ``settings``) — a fonte oficial dos dados da
  empresa de intermediação de crédito (Precision Crédito);
- ``_get_rendered_rgpd_text`` / ``_get_rendered_minuta_text`` / fluxo
  público (``run_get_rgpd_form_data``) injetam esses dados nos templates;
- NUNCA a empresa de teste ("Power Real Estate"), mesmo quando o processo
  e o utilizador pertencem a ela (com ``db.companies`` registada — a
  resolução por empresa foi removida dos documentos legais);
- fallback legal ``RGPD_ISSUER`` quando o SystemConfig não existe ou não
  define um campo.
"""
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

import services.rgpd_minutas as rgpd_minutas
import services.rgpd_public as rgpd_public_mod
import services.rgpd_service as rgpd_service
import services.rgpd_templates as rgpd_templates
from models.system_config import SystemSettings
from services.rgpd_service import (
    _get_company_legal_data,
    _get_rendered_minuta_text,
    _get_rendered_rgpd_text,
)
from services.rgpd_templates import RGPD_ISSUER_NAME, RGPD_ISSUER_NIF


# --------------------------------------------------------------------
# Fixtures / dados de teste
# --------------------------------------------------------------------

# Dados oficiais da empresa — tal como gravados no SystemConfig em produção
SYSTEM_CONFIG_MAIN = {
    "_id": "main",
    "settings": {
        "company_name": "Precision Crédito, Lda.",
        "company_nif": "515657514",
        "company_address": "Av. da Liberdade 100, 1250-146 Lisboa",
        "company_email": "geral@precisioncredito.pt",
        "company_phone": "+351 210 000 000",
    },
}

# Processo pertencente à empresa de teste (mediação imobiliária) — a
# fonte de dados ERRADA que o Pacote FR-4 injectava no documento legal
PROCESSO_POWER = {
    "id": "proc-power-1",
    "client_name": "João Silva",
    "company_id": "power-uuid",
    "company_name": "Power Real Estate",
    "personal_data": {
        "nif": "123456789",
        "morada_fiscal": "Rua das Flores 12, Lisboa",
        "documento_id": {"type": "cartao_de_cidadao", "number": "00000000"},
    },
}

# A empresa de teste registada em db.companies — se o serviço a consultar,
# o teste detecta (o documento sairia com "Power Real Estate")
COMPANY_POWER = {
    "id": "power-uuid",
    "name": "Power Real Estate",
    "nif": "500000000",
    "address": "Rua de Teste 1",
    "phone": "+351 900 000 000",
}

CONSENT_DATA = {
    "nome": "João Silva",
    "contribuinte": "123456789",
    "tipo_documento": "cartao_de_cidadao",
    "numero_documento": "00000000",
    "validade_documento": "01/01/2030",
    "morada": "Rua das Flores 12, Lisboa",
    "localidade": "Lisboa",
    "codigo_postal": "1100-000",
    "data_assinatura": "___/___/______",
}

RGPD_REQUEST = {"id": "rgpd-1", "process_id": "proc-power-1", "created_by": "user-power"}


@pytest.fixture
def fake_rgpd_db(fake_async_db):
    """Fake DB partilhada pelos 4 módulos do fluxo RGPD/Minuta.

    Estado: SystemConfig com os dados oficiais + processo da empresa de
    teste + empresa de teste registada em companies (armadilha para
    detectar queries à fonte errada).
    """
    fake_async_db.system_config.docs = [dict(SYSTEM_CONFIG_MAIN)]
    fake_async_db.processes.docs = [dict(PROCESSO_POWER)]
    fake_async_db.companies.docs = [dict(COMPANY_POWER)]
    return fake_async_db


@contextmanager
def _patch_all_dbs(fake_db):
    """Patcha `db` SIMULTANEAMENTE nos módulos do fluxo RGPD/Minuta.

    Nota: um único `with` combinado — aplicar os patches em sequência
    executaria o corpo uma vez por patch e deixaria o Motor real ativo
    nas iterações seguintes (I/O de rede nos testes unitários).
    """
    with patch.object(rgpd_service, "db", fake_db), \
            patch.object(rgpd_templates, "db", fake_db), \
            patch.object(rgpd_minutas, "db", fake_db), \
            patch.object(rgpd_public_mod, "db", fake_db):
        yield


# --------------------------------------------------------------------
# _get_company_legal_data — leitura estrita do SystemConfig
# --------------------------------------------------------------------

class TestGetCompanyLegalData:

    async def test_le_dados_oficiais_do_system_config(self, fake_async_db):
        fake_async_db.system_config.docs = [dict(SYSTEM_CONFIG_MAIN)]
        with _patch_all_dbs(fake_async_db):
            empresa = await _get_company_legal_data()

        assert empresa["nome"] == "Precision Crédito, Lda."
        assert empresa["nif"] == "515657514"
        assert empresa["morada"] == "Av. da Liberdade 100, 1250-146 Lisboa"
        assert empresa["email"] == "geral@precisioncredito.pt"
        assert empresa["contacto"] == "+351 210 000 000"

    async def test_fallback_legal_quando_config_inexistente(self, fake_async_db):
        # Sem documento "main" na BD — fallback RGPD_ISSUER (Precision
        # Crédito, Lda. / NIF 515657514), nunca dados de teste.
        with _patch_all_dbs(fake_async_db):
            empresa = await _get_company_legal_data()

        assert empresa["nome"] == RGPD_ISSUER_NAME
        assert empresa["nif"] == RGPD_ISSUER_NIF
        assert empresa["nome"] != "Power Real Estate"
        assert empresa["morada"] == ""
        assert empresa["email"] == ""
        assert empresa["contacto"] == ""

    async def test_contacto_usa_email_como_fallback_do_telefone(self, fake_async_db):
        fake_async_db.system_config.docs = [{
            "_id": "main",
            "settings": {
                "company_name": "Precision Crédito, Lda.",
                "company_nif": "515657514",
                "company_email": "geral@precisioncredito.pt",
                # sem company_phone
            },
        }]
        with _patch_all_dbs(fake_async_db):
            empresa = await _get_company_legal_data()

        assert empresa["contacto"] == "geral@precisioncredito.pt"

    async def test_bd_indisponivel_nao_levanta_excepcao(self, fake_async_db):
        # O acesso à BD lança — o helper devolve sempre o fallback legal
        # (o documento nunca deixa de ser emitido).
        fake_async_db.system_config.find_one = AsyncMock(
            side_effect=RuntimeError("mongo down")
        )
        with _patch_all_dbs(fake_async_db):
            empresa = await _get_company_legal_data()

        assert empresa["nome"] == RGPD_ISSUER_NAME
        assert empresa["nif"] == RGPD_ISSUER_NIF


# --------------------------------------------------------------------
# _get_rendered_rgpd_text — RGPD com dados do SystemConfig
# --------------------------------------------------------------------

class TestRenderedRgpdText:

    async def test_rgpd_injecta_dados_do_system_config(self, fake_rgpd_db):
        with _patch_all_dbs(fake_rgpd_db):
            rendered = await _get_rendered_rgpd_text(
"proc-power-1", RGPD_REQUEST, CONSENT_DATA
                )

        # Dados oficiais da empresa (SystemConfig) no documento:
        assert "Empresa: Precision Crédito, Lda." in rendered
        assert "NIF: 515657514" in rendered
        assert "Morada: Av. da Liberdade 100, 1250-146 Lisboa" in rendered
        assert "Contacto: +351 210 000 000" in rendered
        # A empresa de teste NUNCA aparece, apesar de o processo e o
        # utilizador pertencerem a ela (e ela estar registada em companies):
        assert "Power Real Estate" not in rendered

    async def test_rgpd_fallback_legal_sem_system_config(self, fake_async_db):
        # Processo da empresa de teste + companies registada, mas SEM
        # SystemConfig — o emissor é o fallback legal, nunca a Power.
        fake_async_db.processes.docs = [dict(PROCESSO_POWER)]
        fake_async_db.companies.docs = [dict(COMPANY_POWER)]
        with _patch_all_dbs(fake_async_db):
            rendered = await _get_rendered_rgpd_text(
"proc-power-1", RGPD_REQUEST, CONSENT_DATA
                )

        assert "Empresa: Precision Crédito, Lda." in rendered
        assert "NIF: 515657514" in rendered
        assert "Power Real Estate" not in rendered

    async def test_rgpd_preserva_placeholders_do_cliente(self, fake_rgpd_db):
        with _patch_all_dbs(fake_rgpd_db):
            rendered = await _get_rendered_rgpd_text(
"proc-power-1", RGPD_REQUEST, CONSENT_DATA
                )

        # Texto legal do cliente intacto (template por defeito):
        assert "Nome Completo: João Silva" in rendered
        assert "NIF/Contribuinte: 123456789" in rendered
        assert "Morada: Rua das Flores 12, Lisboa" in rendered
        assert "{{" not in rendered  # todos os placeholders substituídos


# --------------------------------------------------------------------
# _get_rendered_minuta_text — Minuta com dados do SystemConfig
# --------------------------------------------------------------------

class TestRenderedMinutaText:

    async def test_minuta_injecta_dados_do_system_config(self, fake_rgpd_db):
        with _patch_all_dbs(fake_rgpd_db):
            rendered = await _get_rendered_minuta_text(
"proc-power-1", RGPD_REQUEST, CONSENT_DATA
                )

        # A Minuta menciona a empresa do SystemConfig:
        assert "Precision Crédito, Lda." in rendered
        assert "Power Real Estate" not in rendered
        # Texto legal preservado:
        assert "venho por este meio solicitar" in rendered
        assert "João Silva" in rendered
        assert "{{NOME_EMPRESA}}" not in rendered

    async def test_minuta_fallback_legal_sem_system_config(self, fake_async_db):
        fake_async_db.processes.docs = [dict(PROCESSO_POWER)]
        fake_async_db.companies.docs = [dict(COMPANY_POWER)]
        with _patch_all_dbs(fake_async_db):
            rendered = await _get_rendered_minuta_text(
"proc-power-1", RGPD_REQUEST, CONSENT_DATA
                )

        assert RGPD_ISSUER_NAME in rendered
        assert "Power Real Estate" not in rendered


# --------------------------------------------------------------------
# Fluxo público de assinatura — mesma fonte de dados
# --------------------------------------------------------------------

class TestPublicFormData:

    async def test_fluxo_publico_injecta_dados_do_system_config(self, fake_rgpd_db):
        token_request = {
            "id": "rgpd-1",
            "process_id": "proc-power-1",
            "client_name": "João Silva",
            "client_email": "joao@exemplo.pt",
        }
        with patch.object(
            rgpd_public_mod,
            "validate_token",
            new=AsyncMock(return_value=token_request),
        ), _patch_all_dbs(fake_rgpd_db):
            data = await rgpd_public_mod.run_get_rgpd_form_data("token-ok")

        rgpd_text = data["rgpd_text"]
        minuta_text = data["minuta_text"]
        # Emissor oficial do SystemConfig em ambos os documentos:
        assert "Empresa: Precision Crédito, Lda." in rgpd_text
        assert "Precision Crédito, Lda." in minuta_text
        # A empresa de teste nunca aparece (o processo pertence-lhe):
        assert "Power Real Estate" not in rgpd_text
        assert "Power Real Estate" not in minuta_text


# --------------------------------------------------------------------
# Modelo SystemSettings — novos campos da fonte oficial
# --------------------------------------------------------------------

class TestSystemSettingsCampos:

    def test_aceita_nif_e_email_da_empresa(self):
        settings = SystemSettings(
            company_name="Precision Crédito, Lda.",
            company_nif="515657514",
            company_address="Av. da Liberdade 100, 1250-146 Lisboa",
            company_email="geral@precisioncredito.pt",
            company_phone="+351 210 000 000",
        )
        assert settings.company_nif == "515657514"
        assert settings.company_email == "geral@precisioncredito.pt"

    def test_default_sem_dados_de_teste(self):
        # O default do modelo segue o emissor legal — nunca a empresa de
        # teste "Power Real Estate" (dados fantasma de desenvolvimento).
        settings = SystemSettings()
        assert settings.company_name != "Power Real Estate"
        assert settings.company_name
        assert settings.company_nif is None
        assert settings.company_email is None

    def test_campos_sobrevivem_ao_dump_do_system_config(self):
        # Round-trip Pydantic (o formato gravado/consultado em
        # db.system_config preserva os novos campos):
        settings = SystemSettings(company_nif="515657514", company_email="geral@precisioncredito.pt")
        dumped = settings.model_dump(mode="json")
        restored = SystemSettings(**dumped)
        assert restored.company_nif == "515657514"
        assert restored.company_email == "geral@precisioncredito.pt"
