"""Scraper de visitas: um portal que muda o DOM não pode deixar a visita vazia (Bloco 5, ponto 1).

Os fixtures simulam o que um portal faz numa publicação do front-end: os nomes
de classe e os `data-cy` mudam, o conteúdo e os dados estruturados (que o portal
precisa para o SEO) não. O oráculo é o `scrape_url` REAL, com a rede, a IA e a
navegação para agências falseadas.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from services import scraper_estruturado as est
from services.scraper import PropertyScraper


def pagina(corpo: str, cabeca: str = "") -> str:
    return f"<html><head>{cabeca}</head><body>{corpo}</body></html>"


def json_ld(dado) -> str:
    return f'<script type="application/ld+json">{json.dumps(dado)}</script>'


def next_data(dado) -> str:
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(dado)}</script>'


@pytest.fixture
def raspador():
    r = PropertyScraper()
    with patch.object(r, "_extract_with_gemini", AsyncMock(return_value=None)) as ia, \
         patch.object(r, "_scrape_agency_direct", AsyncMock(return_value={})), \
         patch.object(r, "_deep_scrape_agency", AsyncMock(return_value={})), \
         patch.object(r, "_search_agency_by_reference", AsyncMock(return_value={})), \
         patch.object(r, "_save_to_cache", AsyncMock()) as guardar:
        r.ia = ia
        r.guardar = guardar
        yield r


async def correr(raspador, url, html):
    with patch.object(raspador, "_fetch_url", AsyncMock(return_value=html)):
        return await raspador.scrape_url(url, use_cache=True if False else False)


# ── o caso do Imovirtual: classes mudadas, __NEXT_DATA__ intacto ───────────

IMOVIRTUAL_DOM_NOVO = pagina(
    '<h1 class="css-9xyz">Apartamento T3 em Alvalade</h1><div class="css-77"><span class="css-1ab">285 000 €</span></div>',
    next_data({"props": {"pageProps": {
        "ad": {
            "title": "Apartamento T3 em Alvalade, Lisboa",
            "description": "Excelente apartamento remodelado, junto ao metro.",
            "target": {"Price": 285000, "Area": 96.5, "Rooms_num": ["3"], "Bathrooms_num": ["2"], "Build_year": 1998},
        },
        "similarAds": [{"title": "Outro imóvel qualquer na Amadora", "target": {"Price": 99000, "Area": 40, "Rooms_num": ["1"]}}],
    }}}),
)


@pytest.mark.asyncio
async def test_imovirtual_com_classes_novas_ainda_devolve_o_anuncio(raspador):
    r = await correr(raspador, "https://www.imovirtual.com/pt/anuncio/apartamento-t3-ID123.html", IMOVIRTUAL_DOM_NOVO)
    assert r["preco"] == 285000
    assert r["area"] == 96.5
    assert r["quartos"] == 3
    assert r["casas_banho"] == 2
    assert r["ano_construcao"] == 1998
    assert r["titulo"].startswith("Apartamento T3 em Alvalade")
    assert "metro" in r["descricao"]


@pytest.mark.asyncio
async def test_os_imoveis_semelhantes_nao_contaminam_a_ficha(raspador):
    r = await correr(raspador, "https://www.imovirtual.com/pt/anuncio/x.html", IMOVIRTUAL_DOM_NOVO)
    assert r["preco"] != 99000 and r["area"] != 40 and r["quartos"] != 1


@pytest.mark.asyncio
async def test_o_que_o_parser_do_portal_leu_continua_a_ganhar(raspador):
    html = pagina(
        '<h1 data-cy="adPageAdTitle">Título do parser</h1><strong data-cy="adPageHeaderPrice">300 000 €</strong>',
        json_ld({"@type": "Product", "name": "Título do JSON-LD", "offers": {"price": 111111}}),
    )
    r = await correr(raspador, "https://www.imovirtual.com/pt/anuncio/x.html", html)
    assert r["titulo"] == "Título do parser" and r["preco"] == 300000


# ── JSON-LD que rebentava ou era ignorado ──────────────────────────────────

@pytest.mark.asyncio
async def test_json_ld_com_offers_em_lista_nao_rebenta_e_da_o_preco(raspador):
    """`offers` como lista levantava AttributeError e o scrape inteiro caía."""
    html = pagina("<h1>Moradia</h1>", json_ld({
        "@type": "Product", "name": "Moradia V4 com piscina",
        "offers": [{"@type": "Offer", "price": "450000", "priceCurrency": "EUR"}],
    }))
    r = await correr(raspador, "https://www.agencia-desconhecida.pt/imovel/1", html)
    assert r["preco"] == 450000 and r["titulo"] == "Moradia V4 com piscina"
    assert "error" not in r


@pytest.mark.asyncio
async def test_json_ld_em_lista_e_graph(raspador):
    html = pagina("", json_ld([{"@type": "WebSite", "name": "Portal"}, {"@graph": [
        {"@type": "RealEstateListing", "name": "T2 no Porto", "offers": {"@type": "AggregateOffer", "lowPrice": "190.000"},
         "address": {"streetAddress": "Rua A, 3", "addressLocality": "Porto", "postalCode": "4000-001"},
         "floorSize": {"@type": "QuantitativeValue", "value": 72}, "numberOfBedrooms": 2},
    ]}]))
    r = await correr(raspador, "https://www.outro-portal.pt/x", html)
    assert (r["titulo"], r["preco"], r["area"], r["quartos"]) == ("T2 no Porto", 190000, 72, 2)
    assert r["localizacao"] == "Rua A, 3, Porto" and r["codigo_postal"] == "4000-001"


@pytest.mark.asyncio
async def test_um_json_ld_partido_nao_esconde_os_outros(raspador):
    html = pagina("<h1>X</h1>", '<script type="application/ld+json">{ isto não é json }</script>'
                  + json_ld({"@type": "Product", "name": "Bom", "offers": {"price": 150000}}))
    r = await correr(raspador, "https://www.outro-portal.pt/x", html)
    assert r["preco"] == 150000


# ── meta e texto rotulado ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_so_com_meta_tags(raspador):
    cabeca = ('<meta property="og:title" content="Vivenda T4 em Cascais">'
              '<meta property="og:description" content="Vista mar.">'
              '<meta property="og:image" content="https://cdn.exemplo.pt/f.jpg">'
              '<meta property="product:price:amount" content="1250000">')
    r = await correr(raspador, "https://www.outro-portal.pt/x", pagina("<h1>Vivenda</h1>", cabeca))
    assert r["preco"] == 1250000 and r["foto_principal"] == "https://cdn.exemplo.pt/f.jpg"
    assert r["titulo"] == "Vivenda T4 em Cascais"


@pytest.mark.asyncio
async def test_so_com_texto_rotulado(raspador):
    corpo = ("<h1>T3 em Setúbal</h1><ul><li>Área útil: 110 m²</li><li>Área bruta: 130 m²</li>"
             "<li>Quartos: 3</li><li>2 casas de banho</li><li>Ano de construção: 2005</li>"
             "<li>Certificado energético: B-</li></ul><p>Preço: 235.000 €</p>")
    r = await correr(raspador, "https://www.outro-portal.pt/x", pagina(corpo))
    assert (r["area"], r["quartos"], r["casas_banho"], r["ano_construcao"]) == (110, 3, 2, 2005)
    assert r["area_bruta"] == 130 and r["certificacao_energetica"] == "B-"
    assert r["preco"] == 235000 and r["tipologia"] == "T3"


# ── números ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "entrada,esperado",
    [("185.000", 185000), ("1.250.000,50", 1250000.5), ("85,5", 85.5), ("85.5", 85.5), ("€ 250 000", 250000),
     ("250 000 €", 250000), (285000, 285000), ("3", 3), ([ "3" ], 3), ({"value": "85"}, 85),
     ("250.000 – 300.000", None), ("250.000 a 300.000", None), ("sob consulta", None), ("", None), (None, None), (True, None), ([1, 2], None)],
)
def test_numero_pt(entrada, esperado):
    assert est.numero_pt(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [(285000, 285000), ("500", None), (150_000_000, None), ("250.000 – 300.000", None), ("€ 1.200", 1200), (-5, None)])
def test_preco_so_aceita_valores_plausiveis(entrada, esperado):
    assert est.preco(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [(96.5, 96.5), ("85 m²", 85), (2, None), (5_000_000, None)])
def test_area_so_aceita_valores_plausiveis(entrada, esperado):
    assert est.area(entrada) == esperado


def test_o_intervalo_de_preco_nao_funde_os_extremos():
    """A versão antiga fazia `re.sub(r'[^\\d]', '', ...)`: 250.000–300.000 → 250000300000."""
    assert est.numero_pt("250.000 – 300.000 €") is None


def test_o_preco_sem_etiqueta_so_entra_sem_fontes_estruturadas():
    com_estrutura = BeautifulSoup(pagina("<h1>X</h1><p>500 000 €</p>", json_ld({"@type": "Product", "name": "X", "offers": {"price": 300000}})), "html.parser")
    assert est.extrair_estruturados(com_estrutura)["preco"] == 300000
    sem = BeautifulSoup(pagina("<h1>X</h1><p>Entrada de 25 000 € e total de 500 000 €</p>"), "html.parser")
    achado = est.extrair_estruturados(sem)
    assert achado["preco"] == 25000 and achado["_preco_sem_etiqueta"] is True


# ── robustez ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_um_parser_do_portal_que_rebenta_nao_mata_o_scrape(raspador):
    html = pagina("<h1>Anúncio</h1>", json_ld({"@type": "Product", "name": "Anúncio bom", "offers": {"price": 210000}}))
    with patch.object(raspador, "_parse_remax", side_effect=AttributeError("'NoneType' object has no attribute 'get_text'")):
        r = await correr(raspador, "https://www.remax.pt/imoveis/x", html)
    assert r["preco"] == 210000 and r["titulo"] == "Anúncio bom"


@pytest.mark.asyncio
async def test_a_camada_estruturada_que_rebenta_nao_mata_o_scrape(raspador):
    html = pagina('<h1 data-cy="adPageAdTitle">T1 em Braga</h1><strong data-cy="adPageHeaderPrice">120 000 €</strong>')
    with patch("services.scraper.extrair_estruturados", side_effect=RuntimeError("boom")):
        r = await correr(raspador, "https://www.imovirtual.com/pt/anuncio/x.html", html)
    assert r["preco"] == 120000


def test_extrair_estruturados_nunca_levanta():
    assert est.extrair_estruturados(None) == {}
    assert est.extrair_estruturados(BeautifulSoup("", "html.parser")) == {}
    assert est.extrair_estruturados(BeautifulSoup("<script id='__NEXT_DATA__'>{</script>", "html.parser")) == {}


def test_extrair_estruturados_nao_altera_a_sopa_do_chamador():
    sopa = BeautifulSoup(pagina("<h1>X</h1><script>var a=1;</script><p>texto</p>"), "html.parser")
    est.extrair_estruturados(sopa)
    assert sopa.find("script") is not None


def test_completar_nao_sobrescreve_e_regista_o_que_acrescentou():
    principal = {"titulo": "do parser", "preco": None, "area": "N/A", "quartos": 0}
    est.completar(principal, {"titulo": "outro", "preco": 100000, "area": 80, "quartos": 3, "_interno": 1})
    assert principal["titulo"] == "do parser"
    assert principal["preco"] == 100000 and principal["area"] == 80 and principal["quartos"] == 3
    assert principal["_completado_por_estruturados"] == ["area", "preco", "quartos"]
    assert "_interno" not in principal


# ── anti-bot e cache ───────────────────────────────────────────────────────

DESAFIO = "<html><head><title>Just a moment...</title></head><body><div id='cf-challenge'>Checking your browser</div></body></html>"


@pytest.mark.parametrize(
    "html,esperado",
    [
        (DESAFIO, True),
        ("<html><body>Access Denied</body></html>", True),
        ("<html><head></head><body><script src='https://geo.captcha-delivery.com/c.js'></script></body></html>", True),
        (pagina("<h1>T2 em Lisboa</h1>" + "<p>texto</p>" * 8000 + "<script>var x='px-captcha'</script>"), False),
        (pagina("<h1>Anúncio normal</h1><p>nada de especial</p>"), False),
        ("", False),
        (None, False),
    ],
)
def test_pagina_de_bloqueio(html, esperado):
    assert est.e_pagina_de_bloqueio(html) is esperado


@pytest.mark.asyncio
async def test_um_desafio_anti_bot_e_um_erro_claro_e_nao_um_anuncio_vazio(raspador):
    with patch("services.scraper.SCRAPERAPI_KEY", ""):
        r = await correr(raspador, "https://www.imovirtual.com/pt/anuncio/x.html", DESAFIO)
    assert "error" in r and "bloque" in r["error"].lower()


@pytest.mark.asyncio
async def test_um_desafio_tenta_o_scraperapi_antes_de_desistir(raspador):
    with patch("services.scraper.SCRAPERAPI_KEY", "chave"), \
         patch.object(raspador, "_fetch_with_scraperapi", AsyncMock(return_value=IMOVIRTUAL_DOM_NOVO)) as via_api:
        r = await correr(raspador, "https://www.imovirtual.com/pt/anuncio/x.html", DESAFIO)
    via_api.assert_awaited_once()
    assert r["preco"] == 285000


@pytest.mark.asyncio
async def test_resultado_sem_dados_nao_vai_para_a_cache(raspador):
    with patch.object(raspador, "_fetch_url", AsyncMock(return_value=pagina("<p>nada</p>"))):
        await raspador.scrape_url("https://www.outro-portal.pt/x", use_cache=True)
    raspador.guardar.assert_not_awaited()


@pytest.mark.asyncio
async def test_resultado_com_dados_vai_para_a_cache(raspador):
    with patch.object(raspador, "_fetch_url", AsyncMock(return_value=IMOVIRTUAL_DOM_NOVO)), \
         patch.object(raspador, "_get_cached_result", AsyncMock(return_value=None)):
        await raspador.scrape_url("https://www.imovirtual.com/pt/anuncio/x.html", use_cache=True)
    raspador.guardar.assert_awaited_once()


@pytest.mark.parametrize("resultado,esperado", [({}, False), ({"titulo": "N/A"}, False), ({"_url": "x", "_source": "y"}, False), ({"preco": 1000}, True), ({"quartos": 0}, True)])
def test_tem_dados_para_guardar(resultado, esperado):
    assert est.tem_dados_para_guardar(resultado) is esperado


# ── casos que as mutações mostraram por cobrir ─────────────────────────────

@pytest.mark.asyncio
async def test_offers_em_lista_sem_tipo_tambem_da_o_preco(raspador):
    html = pagina("<h1>X</h1>", json_ld({"@type": "Product", "name": "Moradia V3 em Sintra", "offers": [{"price": 330000}]}))
    r = await correr(raspador, "https://www.outro-portal.pt/x", html)
    assert r["preco"] == 330000


@pytest.mark.asyncio
async def test_com_o_mesmo_numero_de_campos_vence_o_dicionario_mais_raso(raspador):
    """O anúncio é o dicionário mais raso; um «semelhante» com tantos campos como ele não o substitui."""
    html = pagina("", next_data({"props": {"pageProps": {
        "ad": {"target": {"Price": 200000, "Area": 80}},
        "similarAds": [{"target": {"Price": 99000, "Area": 33}}],
    }}}))
    r = await correr(raspador, "https://www.imovirtual.com/pt/anuncio/x.html", html)
    assert (r["preco"], r["area"]) == (200000, 80)


@pytest.mark.asyncio
async def test_sem_mais_nenhuma_fonte_o_titulo_vem_do_h1(raspador):
    r = await correr(raspador, "https://www.outro-portal.pt/x", pagina("<h1>T2 junto ao rio</h1><p>texto</p>"))
    assert r["titulo"] == "T2 junto ao rio"
