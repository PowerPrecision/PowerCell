"""PACOTE 11 — Unit tests de branding de emails + fix RGPD bold.

Eixo 2: logo da empresa nos templates base (email_branding.py /
get_base_template) e correcção do "bold excessivo" no PDF do RGPD
(apenas títulos curtos / tags <b>/<strong> explícitas saem a negrito).
"""
from unittest.mock import patch

from services.email import get_base_template
from services.email_branding import build_email_header_logo_html, resolve_company_logo_url
from services.rgpd_pdf import _is_section_heading, _wrap_plain_text_as_html


class TestResolveCompanyLogoUrl:
    async def test_system_config_tem_prioridade(self, fake_async_db):
        import database as database_module
        fake_async_db.system_config.docs.append({
            "_id": "main", "settings": {"logo_url": "https://cdn.example/logo.png"},
        })
        with patch.object(database_module, "db", fake_async_db):
            assert await resolve_company_logo_url() == "https://cdn.example/logo.png"

    async def test_fallback_para_companies(self, fake_async_db):
        import database as database_module
        fake_async_db.system_config.docs.append({"_id": "main", "settings": {}})
        fake_async_db.companies.docs.append({
            "id": "co1", "is_active": True, "logo_url": "https://cdn.example/co.png",
        })
        with patch.object(database_module, "db", fake_async_db):
            assert await resolve_company_logo_url() == "https://cdn.example/co.png"

    async def test_sem_logo_devolve_none(self, fake_async_db):
        import database as database_module
        fake_async_db.system_config.docs.append({"_id": "main", "settings": {}})
        fake_async_db.companies.docs.append({"id": "co1", "is_active": True})
        with patch.object(database_module, "db", fake_async_db):
            assert await resolve_company_logo_url() is None


class TestBuildEmailHeaderLogoHtml:
    def test_sem_logo_string_vazia(self):
        assert build_email_header_logo_html(None) == ""
        assert build_email_header_logo_html("") == ""

    def test_com_logo_gera_img(self):
        html = build_email_header_logo_html("https://cdn.example/logo.png", alt="X")
        assert html.startswith("<img")
        assert 'src="https://cdn.example/logo.png"' in html
        assert 'alt="X"' in html


class TestGetBaseTemplate:
    def test_sem_logo_header_apenas_texto(self):
        html = get_base_template("<p>Olá</p>", "T")
        assert "<h1>Power Real Estate</h1>" in html
        assert "<img" not in html

    def test_com_logo_injecta_imagem_no_header(self):
        html = get_base_template("<p>Olá</p>", "T", logo_url="https://cdn.example/l.png")
        assert "<img" in html
        assert 'src="https://cdn.example/l.png"' in html
        assert "<h1>Power Real Estate</h1>" in html


class TestRgpdBoldFix:
    def test_titulo_numerado_curto_e_heading(self):
        assert _is_section_heading("1. RESPONSÁVEL PELO TRATAMENTO") is True

    def test_clausula_numerada_longa_nao_e_heading(self):
        # PACOTE 11 — parágrafos legais completos nunca são títulos
        clausula = (
            "1. Os dados pessoais recolhidos são tratados para as seguintes "
            "finalidades: gestão do processo de mediação imobiliária, "
            "cumprimento de obrigações legais e regulatórias aplicáveis."
        )
        assert _is_section_heading(clausula) is False

    def test_linha_de_dados_nao_e_heading(self):
        assert _is_section_heading("Empresa: Precision Crédito, Lda.") is False
        assert _is_section_heading("NIF: 515657514") is False

    def test_wrap_plain_text_bold_apenas_no_titulo(self):
        texto = (
            "1. RESPONSÁVEL PELO TRATAMENTO\n"
            "Empresa: Precision Crédito, Lda.\n"
            "NIF: 515657514"
        )
        html = _wrap_plain_text_as_html(texto)
        # O título (linha) fica <strong>; as linhas de dados NÃO.
        assert "<strong>1. RESPONSÁVEL PELO TRATAMENTO</strong>" in html
        assert "<strong>Empresa:" not in html
        assert "<strong>NIF:" not in html

    def test_wrap_plain_text_linhas_de_dados_regulares(self):
        texto = "2. TITULAR DOS DADOS\nNome Completo: João Silva\nNIF: 123456789"
        html = _wrap_plain_text_as_html(texto)
        assert "<strong>2. TITULAR DOS DADOS</strong>" in html
        # As linhas seguintes ao título ficam regulares (sem bold sintético)
        assert "Nome Completo: João Silva" in html
        assert "<strong>Nome Completo" not in html
