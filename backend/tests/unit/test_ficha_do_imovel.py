"""`ficha_do_imovel`: o que a IA extrai chega à visita (D-23).

O QUE CORREU MAL
================
O `scraper.py` devolve ~30 campos e o mapeador para `ScrapedData` tinha
uma lista escrita à mão de ONZE. O `estado` do imóvel é extraído pela IA
desde sempre — o prompt pede-o pelo nome — e **nunca chegou a sítio
nenhum**. Mesma forma do `naturalidade` do `AI_SUGGESTION_FIELD_MAP`: o
lado que traduz descarta em silêncio o que não conhece, e a extracção
parece ter corrido bem.

E havia DOIS mapeadores escritos à mão para os mesmos campos — o do CRM
(`visit_helpers`) e o do Portal (`portal_client_visits`) — **já
divergentes**: o do Portal guardava `raw_data`, o do CRM não, pelo que
uma visita criada no CRM perdia também quartos, casas de banho,
certificado energético, ano de construção, descrição e referência.
"""
from __future__ import annotations

import pytest

from services.visit_property_extract import (
    CAMPOS_DA_VISITA,
    VEREDICTO_COMPLETA,
    VEREDICTO_ERRO,
    VEREDICTO_SEM_DADOS,
    ficha_do_imovel,
    raw_data_derivado,
)

AGORA = "2026-10-04T12:00:00+00:00"
URL = "https://www.idealista.pt/imovel/12345/"


class _Consultor:
    def __init__(self):
        self.name = "Rui Agente"
        self.phone = "911111111"
        self.email = "rui@agencia.pt"
        self.agency_name = "Agência X"


class _Scraped:
    """O que `extract_property_data` devolve (forma do `ScrapedData`)."""

    def __init__(self, **kw):
        self.url = URL
        self.title = "T2 em Leiria, com varanda"
        self.price = 185000.0
        self.location = "Leiria"
        self.typology = "T2"
        self.area = 95.0
        self.photo_url = "https://img/1.jpg"
        self.consultant = _Consultor()
        self.source = "idealista"
        self.raw_data = {
            "estado": "usado",
            "quartos": 2,
            "casas_banho": 1,
            "certificado_energetico": "C",
            "ano_construcao": 1998,
            "descricao": "Apartamento remodelado",
            "referencia": "REF-1",
            "orientacao_solar": "sul",
            "_extracted_by": "gemini-2.5-pro",
        }
        for k, v in kw.items():
            setattr(self, k, v)


class TestOCampoQueSePerdia:
    def test_o_ESTADO_do_imovel_chega_a_visita(self):
        """O campo que a IA extraía e o mapeador atirava fora."""
        ficha = ficha_do_imovel(_Scraped(), url=URL, agora=AGORA)
        assert ficha.campos["scraped_estado"] == "usado"

    def test_a_AREA_tem_coluna_propria(self):
        """Antes só existia dentro de `scraped_data`: o quadro não a
        conseguia mostrar sem abrir o objecto inteiro."""
        ficha = ficha_do_imovel(_Scraped(), url=URL, agora=AGORA)
        assert ficha.campos["scraped_area"] == 95.0

    def test_os_seis_campos_pedidos_estao_todos_la(self):
        ficha = ficha_do_imovel(_Scraped(), url=URL, agora=AGORA)
        assert ficha.campos["scraped_price"] == 185000.0
        assert ficha.campos["scraped_typology"] == "T2"
        assert ficha.campos["property_address"]["municipality"] == "Leiria"
        assert ficha.campos["scraped_area"] == 95.0
        assert ficha.campos["scraped_estado"] == "usado"
        assert ficha.campos["scraped_url"] == URL


class TestORawDataDeriva:
    def test_tudo_o_que_nao_tem_nome_proprio_sobrevive(self):
        """DERIVA do dicionário: um campo novo no prompt da IA chega ao
        mesmo destino sem ninguém se lembrar de o acrescentar."""
        extra = raw_data_derivado({
            "estado": "novo", "piso": 3, "inventado_amanha": "x",
            "url": "ignorado", "title": "ignorado", "raw_data": "ignorado",
        })
        assert extra == {"estado": "novo", "piso": 3, "inventado_amanha": "x"}

    def test_as_chaves_PORTUGUESAS_do_scraper_tambem_derivam(self):
        """D23a — a mutação que repôs a lista à mão SOBREVIVEU: o teste de
        cima exercitava o `raw_data_derivado` (chaves inglesas, a segunda
        rede de segurança) e não o `raw_data_do_scraper`, que é a camada
        onde o `estado` se perdia de verdade."""
        from services.visit_property_extract import raw_data_do_scraper

        extra = raw_data_do_scraper({
            # consumidas pelo `ScrapedData`
            "titulo": "T2", "preco": 185000, "localizacao": "Leiria",
            "tipologia": "T2", "area": 95, "foto_principal": "u",
            "agente_nome": "Rui", "agente_telefone": "9", "agente_email": "e",
            "agencia_nome": "A",
            # as que se perdiam
            "estado": "usado", "orientacao_solar": "sul", "condominio": 40,
            "piso": 3, "elevador": True, "varanda": True, "vista": "mar",
            "url_planta": "p", "url_video": "v", "agencia_telefone": "21",
            "quartos": 2, "descricao": "d", "referencia": "R",
            "_extracted_by": "gemini-2.5-pro",
        })
        assert extra["estado"] == "usado"
        assert extra["agencia_telefone"] == "21", (
            "não cabe no ConsultantInfo e era um dos campos perdidos"
        )
        for perdido in ("orientacao_solar", "condominio", "piso", "elevador",
                        "varanda", "vista", "url_planta", "url_video"):
            assert perdido in extra, perdido
        assert extra["_extracted_by"] == "gemini-2.5-pro"
        # E as consumidas não se duplicam.
        for consumida in ("titulo", "preco", "localizacao", "tipologia",
                          "area", "foto_principal", "agente_nome",
                          "agente_telefone", "agente_email", "agencia_nome"):
            assert consumida not in extra, consumida

    def test_um_campo_INVENTADO_AMANHA_chega_sem_ninguem_o_acrescentar(self):
        """É o ponto de derivar: a lista à mão exigia que alguém se
        lembrasse, e foi isso que falhou com o `estado`."""
        from services.visit_property_extract import raw_data_do_scraper

        assert raw_data_do_scraper({"campo_novo_do_prompt": 1}) == {
            "campo_novo_do_prompt": 1
        }

    def test_os_campos_com_nome_proprio_NAO_se_duplicam(self):
        """Senão o `scraped_data` levava o título duas vezes e um leitor
        não saberia qual é a autoridade."""
        ficha = ficha_do_imovel(_Scraped(), url=URL, agora=AGORA)
        assert "title" not in ficha.campos["scraped_data"]["raw_data"]
        assert "price" not in ficha.campos["scraped_data"]["raw_data"]

    def test_o_caminho_do_CRM_passa_a_guardar_o_raw_data(self):
        """Era a divergência concreta entre os dois mapeadores à mão."""
        ficha = ficha_do_imovel(_Scraped(), url=URL, agora=AGORA)
        guardado = ficha.campos["scraped_data"]["raw_data"]
        assert guardado["quartos"] == 2
        assert guardado["certificado_energetico"] == "C"
        assert guardado["ano_construcao"] == 1998

    def test_um_raw_data_ausente_nao_rebenta(self):
        ficha = ficha_do_imovel(
            _Scraped(raw_data=None), url=URL, agora=AGORA,
        )
        assert ficha.campos["scraped_data"]["raw_data"] == {}
        assert "scraped_estado" not in ficha.campos

    def test_quem_extraiu_viaja_no_raw_data(self):
        """`_extracted_by` é o que diz se foi um parser ou a IA — e com que
        modelo (D-22). Sem ele, um custo inesperado não tem origem."""
        ficha = ficha_do_imovel(_Scraped(), url=URL, agora=AGORA)
        assert ficha.campos["scraped_data"]["raw_data"]["_extracted_by"] == (
            "gemini-2.5-pro"
        )


class TestOsTresVeredictos:
    def test_com_dados_e_COMPLETA(self):
        assert ficha_do_imovel(_Scraped(), url=URL, agora=AGORA).veredicto == (
            VEREDICTO_COMPLETA
        )

    def test_um_anuncio_que_responde_VAZIO_nao_e_sucesso(self):
        """O caso do meio, que não existia: um portal que mude o HTML
        devolve 200 com tudo vazio, e isso contava como `completed` — a
        visita ficava sem um único dado, indistinguível de um imóvel sem
        informação."""
        vazio = _Scraped(
            title=None, price=None, location=None, typology=None,
            area=None, photo_url=None, raw_data={},
        )
        ficha = ficha_do_imovel(vazio, url=URL, agora=AGORA)
        assert ficha.veredicto == VEREDICTO_SEM_DADOS
        assert ficha.campos["scraper_status"] == VEREDICTO_SEM_DADOS
        assert ficha.motivo
        assert ficha.tem_dados is False

    def test_o_source_error_do_scraper_e_ERRO_e_leva_o_motivo(self):
        falha = _Scraped(source="error", raw_data={"error": "403 do Idealista"})
        ficha = ficha_do_imovel(falha, url=URL, agora=AGORA)
        assert ficha.veredicto == VEREDICTO_ERRO
        assert ficha.campos["scraper_error"] == "403 do Idealista"

    def test_um_erro_sem_mensagem_tem_mensagem_mesmo_assim(self):
        """Um `scraper_error` vazio no ecrã lê-se como «não há erro»."""
        ficha = ficha_do_imovel(
            _Scraped(source="error", raw_data={}), url=URL, agora=AGORA,
        )
        assert ficha.campos["scraper_error"]

    def test_sem_resultado_nenhum_tambem_e_ERRO(self):
        ficha = ficha_do_imovel(None, url=URL, agora=AGORA)
        assert ficha.veredicto == VEREDICTO_ERRO
        assert ficha.campos["scraper_status"] == VEREDICTO_ERRO

    def test_um_ERRO_nao_apaga_os_campos_do_imovel(self):
        """Só se escreve o estado da leitura: um segundo scraping que
        falhe não pode apagar o título que o primeiro leu."""
        ficha = ficha_do_imovel(
            _Scraped(source="error", raw_data={"error": "x"}),
            url=URL, agora=AGORA,
        )
        for campo in CAMPOS_DA_VISITA:
            assert campo not in ficha.campos


class TestNadaSeSobrescreveComVazio:
    @pytest.mark.parametrize("campo,atributo", [
        ("property_title", "title"),
        ("scraped_price", "price"),
        ("property_photo", "photo_url"),
        ("scraped_typology", "typology"),
        ("scraped_area", "area"),
    ])
    def test_um_campo_vazio_nao_entra_no_set(self, campo, atributo):
        ficha = ficha_do_imovel(
            _Scraped(**{atributo: None}), url=URL, agora=AGORA,
        )
        assert campo not in ficha.campos

    def test_a_localizacao_vazia_nao_grava_um_endereco_em_branco(self):
        """Um `property_address` com `municipality: ""` apagava o endereço
        que já estava lá e mostrava uma linha vazia no quadro."""
        ficha = ficha_do_imovel(_Scraped(location=""), url=URL, agora=AGORA)
        assert "property_address" not in ficha.campos


class TestOsNumerosNaoRebentam:
    @pytest.mark.parametrize("bruto,esperado", [
        (185000, 185000.0),
        ("185000", 185000.0),
        ("185.000 €", 185000.0),
        ("185 000€", 185000.0),
        ("185.000,50", 185000.50),
        ("1.250.000", 1250000.0),
        ("1234.56", 1234.56),
        ("95.5", 95.5),
        ("120.75", 120.75),
        ("95 m²", 95.0),
        ("", None),
        (None, None),
        ("sob consulta", None),
        (True, None),
        ([], None),
    ])
    def test_o_preco_vem_do_scraper_em_varias_formas(self, bruto, esperado):
        """A IA nem sempre converte, e um `float()` cru rebentava o
        pipeline de FUNDO — onde a excepção fica num log que ninguém lê."""
        ficha = ficha_do_imovel(
            _Scraped(price=bruto, area=bruto), url=URL, agora=AGORA,
        )
        if esperado is None:
            assert "scraped_price" not in ficha.campos
        else:
            assert ficha.campos["scraped_price"] == esperado

    def test_uma_AREA_zero_tambem_e_um_valor(self):
        """D23c — a mutação `if area is not None` → `if area` sobreviveu:
        nenhum teste passava uma área de 0. Um terreno com área por
        declarar vem a 0 de alguns portais, e tratá-lo como ausência
        deixava a célula vazia a dizer «não sei» em vez de «zero»."""
        ficha = ficha_do_imovel(_Scraped(area=0), url=URL, agora=AGORA)
        assert ficha.campos["scraped_area"] == 0.0

    def test_um_preco_ZERO_e_um_valor_e_nao_uma_ausencia(self):
        """`if preco:` descartava o zero. É `is not None` de propósito —
        é a armadilha do `|| 30` sobre o `completedDays` do Kanban."""
        ficha = ficha_do_imovel(_Scraped(price=0), url=URL, agora=AGORA)
        assert ficha.campos["scraped_price"] == 0.0


class TestOPontoUnico:
    def test_os_dois_mapeadores_a_mao_desapareceram(self):
        """Guarda de fonte: nenhum dos caminhos volta a traduzir à mão.

        Com contraprova — os dois chamam MESMO o ponto único, senão
        apagar a chamada satisfazia a guarda.
        """
        from services import portal_client_visits, visit_helpers
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        crm = codigo_da_funcao_sem_comentarios(
            visit_helpers._run_scraper_for_visit
        )
        portal = codigo_da_funcao_sem_comentarios(
            portal_client_visits._background_visit_scraper_and_notify
        )
        for nome, codigo in (("CRM", crm), ("Portal", portal)):
            assert "ficha_do_imovel" in codigo, (
                f"o caminho do {nome} deixou de usar o ponto único"
            )
            assert "scraped_typology" not in codigo, (
                f"o caminho do {nome} voltou a traduzir campos à mão"
            )
