"""Testes unitários — o motor navega, pausa e manda as duas páginas à IA.

Estes testes são AO NÍVEL DA CHAMADA, não do resultado: afirmam sobre os
PEDIDOS que saem (o segundo URL, o `Referer`, a pausa que foi pedida) e
sobre o CONTEXTO que entra no prompt. É a regra do «duplo demasiado
esperto»: um falso que reimplemente a navegação validaria o falso.

O que se mede aqui e não no módulo puro: a LIGAÇÃO. O
`test_extracao_profunda_do_anunciante.py` prova a decisão; este prova que
o `scrape_url` a usa, que a pausa acontece ENTRE os dois pedidos e que o
HTML da segunda página chega ao prompt.
"""
from __future__ import annotations

import pytest

from services.scraper_anunciante import (
    ROTULO_DO_ANUNCIANTE,
    ROTULO_DO_ANUNCIO,
)

HTML_DO_ANUNCIO = """
<html><body>
  <h1 class="main-info__title">T3 em Cascais</h1>
  <span class="info-data-price">450.000 €</span>
  <a href="/imovel/33445566/#fotos">Ver fotografias</a>
  <a href="/pro/predial-atlantico/">Ver todos os imóveis desta agência</a>
</body></html>
"""

HTML_DO_ANUNCIANTE = """
<html><body>
  <h1>Predial Atlântico</h1>
  <div class="agent-name">Marta Nunes</div>
  <a href="tel:+351912345678">912 345 678</a>
  <a href="mailto:marta.nunes@predial-atlantico.pt">Email</a>
</body></html>
"""

URL = "https://www.idealista.pt/imovel/33445566/"


class _MotorInstrumentado:
    """Registo de tudo o que o motor PEDE, sem rede e sem relógio."""

    def __init__(self, scraper):
        self.scraper = scraper
        self.pedidos: list[dict] = []
        self.pausas: list[float] = []
        self.prompts: list[str] = []

    async def fetch(self, url, retries=3, *, referer=None):
        self.pedidos.append({"url": url, "referer": referer})
        if "/pro/" in url:
            return HTML_DO_ANUNCIANTE
        return HTML_DO_ANUNCIO

    async def dormir(self, segundos):
        self.pausas.append(segundos)

    async def ia(self, html_content, url, *, html_do_anunciante=None,
                 url_do_anunciante=None):
        from services.scraper_anunciante import (
            contexto_para_a_ia,
            pagina_do_anunciante,
            pagina_do_anuncio,
            prompt_da_extraccao,
        )

        paginas = [pagina_do_anuncio(html_content, url)]
        if html_do_anunciante:
            paginas.append(pagina_do_anunciante(html_do_anunciante,
                                                url_do_anunciante or ""))
        self.prompts.append(
            prompt_da_extraccao(contexto_para_a_ia(paginas), url=url)
        )
        return {"agente_nome": "Marta Nunes", "agente_telefone": "+351 912 345 678"}


@pytest.fixture
def motor(monkeypatch):
    from services import scraper as modulo

    scraper = modulo.PropertyScraper()
    instrumentado = _MotorInstrumentado(scraper)

    monkeypatch.setattr(scraper, "_fetch_url", instrumentado.fetch)
    monkeypatch.setattr(scraper, "_extract_with_gemini", instrumentado.ia)
    monkeypatch.setattr(modulo.asyncio, "sleep", instrumentado.dormir)
    # Sem cache: é a BD, e estes testes não a têm.
    monkeypatch.setattr(scraper, "_get_cached_result", lambda url: _nada())
    monkeypatch.setattr(scraper, "_save_to_cache", lambda url, r: _nada())
    return instrumentado


async def _nada():
    return None


@pytest.mark.asyncio
class TestOSegundoPedido:
    async def test_o_motor_segue_para_a_pagina_do_anunciante(self, motor):
        """O defeito de origem: no Idealista este salto era impossível."""
        await motor.scraper.scrape_url(URL, use_cache=False)

        assert len(motor.pedidos) == 2, "um pedido por página, e só dois"
        assert motor.pedidos[0]["url"] == URL
        assert motor.pedidos[1]["url"] == (
            "https://www.idealista.pt/pro/predial-atlantico/"
        )

    async def test_ha_uma_pausa_ENTRE_os_dois_pedidos(self, motor):
        """O único atraso do motor corria DEPOIS de um 403 — tarde."""
        from services import scraper as modulo

        await motor.scraper.scrape_url(URL, use_cache=False)

        assert len(motor.pausas) == 1
        assert (
            modulo.PAUSA_ENTRE_PAGINAS_MIN
            <= motor.pausas[0]
            <= modulo.PAUSA_ENTRE_PAGINAS_MAX
        )

    async def test_a_pausa_tem_JITTER(self, monkeypatch):
        """Um valor fixo é ele próprio uma assinatura."""
        from services import scraper as modulo

        valores = set()
        for _ in range(12):
            scraper = modulo.PropertyScraper()
            instrumentado = _MotorInstrumentado(scraper)
            monkeypatch.setattr(scraper, "_fetch_url", instrumentado.fetch)
            monkeypatch.setattr(scraper, "_extract_with_gemini", instrumentado.ia)
            monkeypatch.setattr(modulo.asyncio, "sleep", instrumentado.dormir)
            monkeypatch.setattr(scraper, "_get_cached_result", lambda url: _nada())
            monkeypatch.setattr(scraper, "_save_to_cache", lambda url, r: _nada())
            await scraper.scrape_url(URL, use_cache=False)
            valores.update(instrumentado.pausas)

        assert len(valores) > 1, "doze passagens com a MESMA pausa não é jitter"

    async def test_o_segundo_pedido_leva_o_referer_do_anuncio(self, motor):
        """Um browser que segue uma ligação envia `Referer`.

        É o único cabeçalho que se acrescenta: o `_get_headers()` inteiro
        contradiria o fingerprint que o `curl_cffi` gera para o profile, e
        é por isso que o `_fetch_url` não passa headers nenhuns.
        """
        await motor.scraper.scrape_url(URL, use_cache=False)

        assert motor.pedidos[0]["referer"] is None
        assert motor.pedidos[1]["referer"] == URL

    async def test_um_so_salto_por_anuncio(self, motor):
        """Dois saltos dobram o risco de bloqueio por um ganho que não existe."""
        from services import scraper as modulo

        assert modulo.MAXIMO_DE_SALTOS == 1
        await motor.scraper.scrape_url(URL, use_cache=False)
        seguidos = [p for p in motor.pedidos if p["referer"]]
        assert len(seguidos) == 1

    async def test_sem_alvo_nao_ha_segundo_pedido(self, motor, monkeypatch):
        sem_ligacoes = """<html><body>
            <h1 class="main-info__title">T2 no Porto</h1>
            <span class="info-data-price">200.000 €</span>
        </body></html>"""

        async def fetch(url, retries=3, *, referer=None):
            motor.pedidos.append({"url": url, "referer": referer})
            return sem_ligacoes

        monkeypatch.setattr(motor.scraper, "_fetch_url", fetch)
        await motor.scraper.scrape_url(URL, use_cache=False)

        assert len(motor.pedidos) == 1
        assert motor.pausas == [], "sem navegação não há pausa a pagar"


@pytest.mark.asyncio
class TestOQueChegaAIA:
    async def test_o_prompt_leva_os_DOIS_blocos_rotulados(self, motor):
        await motor.scraper.scrape_url(URL, use_cache=False)

        assert len(motor.prompts) == 1, "UMA chamada, não duas"
        prompt = motor.prompts[0]
        assert ROTULO_DO_ANUNCIO in prompt
        assert ROTULO_DO_ANUNCIANTE in prompt
        assert "Marta Nunes" in prompt, "o HTML do anunciante tem de chegar lá"

    async def test_as_instrucoes_do_cruzamento_so_existem_com_dois_blocos(self, motor):
        await motor.scraper.scrape_url(URL, use_cache=False)
        assert "CRUZAMENTO DAS DUAS PÁGINAS" in motor.prompts[0]

    async def test_sem_segunda_pagina_nao_se_fala_de_cruzamento(self, monkeypatch):
        """Um parágrafo sobre uma página que não foi enviada convida o
        modelo a inventá-la."""
        from services import scraper as modulo

        scraper = modulo.PropertyScraper()
        instrumentado = _MotorInstrumentado(scraper)

        async def fetch(url, retries=3, *, referer=None):
            instrumentado.pedidos.append({"url": url, "referer": referer})
            return "<html><body><p>site desconhecido</p></body></html>"

        monkeypatch.setattr(scraper, "_fetch_url", fetch)
        monkeypatch.setattr(scraper, "_extract_with_gemini", instrumentado.ia)
        monkeypatch.setattr(modulo.asyncio, "sleep", instrumentado.dormir)
        monkeypatch.setattr(scraper, "_get_cached_result", lambda url: _nada())
        monkeypatch.setattr(scraper, "_save_to_cache", lambda url, r: _nada())

        await scraper.scrape_url("https://www.sitequalquer.pt/imovel/1", use_cache=False)

        assert instrumentado.prompts, "o parser genérico chama a IA"
        assert "CRUZAMENTO DAS DUAS PÁGINAS" not in instrumentado.prompts[0]
        assert ROTULO_DO_ANUNCIANTE not in instrumentado.prompts[0]

    async def test_a_IA_e_chamada_por_haver_segunda_pagina(self, motor):
        """Mesmo com o parser a acertar no título e no preço.

        É a condição nova: a IA faz aqui o que nenhum parser faz —
        CRUZA as duas páginas e decide se o número é o directo de quem
        vende este imóvel ou a central da agência.
        """
        resultado = await motor.scraper.scrape_url(URL, use_cache=False)

        assert resultado.get("titulo"), "o parser acertou no título"
        assert len(motor.prompts) == 1, "e a IA correu mesmo assim"


@pytest.mark.asyncio
class TestOTelefoneQueSaiDoMotor:
    async def test_o_telefone_sai_normalizado(self, motor):
        resultado = await motor.scraper.scrape_url(URL, use_cache=False)
        assert resultado.get("agente_telefone") == "912345678"

    async def test_um_telefone_invalido_sai_a_None(self, motor, monkeypatch):
        """Um telefone que não é um telefone é pior do que nenhum.

        A página do anunciante deste caso NÃO tem telefone de propósito:
        com o `tel:` do fixture normal, o deep scraping apanha-o antes da
        IA e o merge mantém-no, pelo que o valor inventado nunca chegava
        ao campo — o teste passava a medir outra coisa.
        """
        async def fetch(url, retries=3, *, referer=None):
            motor.pedidos.append({"url": url, "referer": referer})
            if "/pro/" in url:
                return "<html><body><h1>Predial Atlântico</h1></body></html>"
            return HTML_DO_ANUNCIO

        async def ia(html_content, url, **kwargs):
            return {"agente_telefone": "450.000", "agente_nome": "Marta"}

        monkeypatch.setattr(motor.scraper, "_fetch_url", fetch)
        monkeypatch.setattr(motor.scraper, "_extract_with_gemini", ia)
        resultado = await motor.scraper.scrape_url(URL, use_cache=False)

        assert resultado.get("agente_telefone") is None
        assert resultado.get("agente_nome") == "Marta", "o nome não se perde com ele"


@pytest.mark.asyncio
class TestOAgencyLinkDeclaradoPeloParser:
    """O `_parse_idealista` gasta seis estratégias a encontrá-lo.

    E o navegador nunca o lia: o Cenário 1 varria os `<a>` outra vez, com
    menos informação do que já estava em mãos. A mutação que desligou a
    passagem dos `declarados` ao módulo puro **sobreviveu** à primeira
    medição — não por o teste ser fraco, mas por eu ter acrescentado o
    parâmetro e nunca o ter exercitado. Uma funcionalidade sem teste.
    """

    #: O `agency_link` DENTRO do texto da descrição e em sítio nenhum
    #: mais — nenhum `<a href>` aponta para ele. É assim que uma agência
    #: o deixa num anúncio do Idealista (um encurtador no texto), e é o
    #: único fixture em que o declarado é OBSERVÁVEL.
    HTML_COM_O_LINK_SO_NA_DESCRICAO = """
    <html><body>
      <h1 class="main-info__title">T3 em Cascais</h1>
      <span class="info-data-price">450.000 €</span>
      <a href="/pro/perfil-no-portal/">Perfil no portal</a>
      <div class="comment">
        Excelente T3 com vista mar. Visite https://dez.pt/ab12cd para
        marcar visita.
      </div>
    </body></html>
    """

    async def test_o_alvo_seguido_e_o_que_o_parser_declarou(self, monkeypatch):
        """A primeira versão deste teste deixou a mutação VIVA duas vezes.

        O fixture tinha um `<a class="advertiser-logo">` para a agência:
        o varrimento do DOM encontrava-o sozinho (rota `/agencia` = 100,
        mais 10 por sair do portal) e já vencia o `/pro/` interno (100).
        Com os dois caminhos a dar o MESMO alvo, desligar a passagem dos
        `declarados` não mudava nada — **não era uma mutação perdida, era
        um teste a medir uma coincidência**.

        Aqui o `agency_link` existe SÓ no texto da descrição, onde o
        varrimento dos `<a>` não chega: é o que o parser do portal sabe
        fazer e o navegador não, e é por isso que ele tem de o ouvir.
        """
        from services import scraper as modulo

        scraper = modulo.PropertyScraper()
        instrumentado = _MotorInstrumentado(scraper)

        async def fetch(url, retries=3, *, referer=None):
            instrumentado.pedidos.append({"url": url, "referer": referer})
            if url == URL:
                return self.HTML_COM_O_LINK_SO_NA_DESCRICAO
            return "<html><body><div class='agent-name'>Marta</div></body></html>"

        monkeypatch.setattr(scraper, "_fetch_url", fetch)
        monkeypatch.setattr(scraper, "_extract_with_gemini", instrumentado.ia)
        monkeypatch.setattr(modulo.asyncio, "sleep", instrumentado.dormir)
        monkeypatch.setattr(scraper, "_get_cached_result", lambda url: _nada())
        monkeypatch.setattr(scraper, "_save_to_cache", lambda url, r: _nada())

        await scraper.scrape_url(URL, use_cache=False)

        assert len(instrumentado.pedidos) == 2
        assert instrumentado.pedidos[1]["url"] == "https://dez.pt/ab12cd", (
            "o alvo seguido tem de ser o `agency_link` que o parser "
            "declarou; o varrimento dos `<a>` só encontra o `/pro/` interno"
        )

    async def test_a_CONTRAPROVA_sem_declarado_segue_o_do_DOM(self, monkeypatch):
        """Sem o `agency_link` na descrição, o alvo é o do varrimento.

        Sem esta contraprova, o teste acima passaria com um motor que
        IGNORASSE o DOM e seguisse só declarados — e isso perderia todos
        os portais em que o perfil do anunciante é uma ligação normal.
        """
        from services import scraper as modulo

        sem_link_na_descricao = self.HTML_COM_O_LINK_SO_NA_DESCRICAO.replace(
            "https://dez.pt/ab12cd", "o nosso escritório"
        )

        scraper = modulo.PropertyScraper()
        instrumentado = _MotorInstrumentado(scraper)

        async def fetch(url, retries=3, *, referer=None):
            instrumentado.pedidos.append({"url": url, "referer": referer})
            if url == URL:
                return sem_link_na_descricao
            return "<html><body><div class='agent-name'>Marta</div></body></html>"

        monkeypatch.setattr(scraper, "_fetch_url", fetch)
        monkeypatch.setattr(scraper, "_extract_with_gemini", instrumentado.ia)
        monkeypatch.setattr(modulo.asyncio, "sleep", instrumentado.dormir)
        monkeypatch.setattr(scraper, "_get_cached_result", lambda url: _nada())
        monkeypatch.setattr(scraper, "_save_to_cache", lambda url, r: _nada())

        await scraper.scrape_url(URL, use_cache=False)

        assert instrumentado.pedidos[1]["url"] == (
            "https://www.idealista.pt/pro/perfil-no-portal/"
        )


class TestODeclaradoNaDecisaoPura:
    """O peso e as recusas do alvo declarado, sem HTML e sem rede."""

    def test_o_declarado_vence_tudo(self):
        from services.scraper_anunciante import alvos_do_anunciante

        alvos = alvos_do_anunciante(
            [("/pro/perfil/", "Perfil")],
            url_de_origem=URL,
            declarados=["https://www.casaboa.pt/sobre-nos"],
        )
        assert alvos[0].url == "https://www.casaboa.pt/sobre-nos"
        assert "declarado pelo parser" in alvos[0].motivo

    def test_um_declarado_sem_rota_nem_dominio_conhecido_ENTRA(self):
        """É o que o parser afirmou; não precisa dos outros sinais."""
        from services.scraper_anunciante import alvos_do_anunciante

        alvos = alvos_do_anunciante(
            [], url_de_origem=URL, declarados=["https://www.xyz.pt/p/12345"]
        )
        assert len(alvos) == 1

    def test_o_declarado_passa_pelas_MESMAS_recusas(self):
        """Ganha peso, não dispensa.

        Dar-lhe um caminho paralelo sem verificações era abrir uma segunda
        porta para o lado de dentro — e o `agency_link` sai de texto de
        descrição de um anúncio, que é conteúdo de terceiros.
        """
        from services.scraper_anunciante import alvos_do_anunciante

        for recusado in (
            "javascript:alert(1)",
            "/pro/termos",
            URL,
            "",
        ):
            assert alvos_do_anunciante(
                [], url_de_origem=URL, declarados=[recusado]
            ) == [], recusado

    def test_um_declarado_repetido_nao_duplica(self):
        from services.scraper_anunciante import alvos_do_anunciante

        alvos = alvos_do_anunciante(
            [("https://www.casaboa.pt/agencia/x", "Casa Boa")],
            url_de_origem=URL,
            declarados=["https://www.casaboa.pt/agencia/x"],
        )
        assert len(alvos) == 1
        assert "declarado pelo parser" in alvos[0].motivo


class TestAChaveDosSelectores:
    """A tradução que faltava, e que falhava em silêncio."""

    @pytest.mark.parametrize(
        "marca,esperado",
        [
            # Formas de DOMÍNIO (o que o `AGENCY_DOMAINS` devolve).
            ("era.pt", "era"),
            ("kw.com", "kw"),
            ("kwportugal", "kw"),
            ("iadportugal", "iad"),
            ("easygest.com.pt", "easygest"),
            ("remax", "remax"),
            ("zome", "zome"),
            ("century21", "century21"),
            # Formas de NOME VISÍVEL (o que o `_extract_agency_name_from_page`
            # e o `AGENCY_NAME_MAPPING` devolvem). **São estas que a tabela
            # de tradução existe para resolver** — e o meu primeiro teste
            # não as tinha, pelo que a mutação que apagou a tabela
            # SOBREVIVEU: o recurso por prefixo já resolve as formas de
            # domínio (`era.pt`.startswith(`era`)) e eu só testava essas.
            # Não era uma mutação perdida, era um teste fraco a cobrir
            # metade de um mecanismo.
            ("re/max", "remax"),
            ("century 21", "century21"),
            ("keller", "kw"),
            ("mais consultores", "maisconsultores"),
        ],
    )
    def test_a_marca_reconhecida_resolve_para_a_chave_dos_selectores(
        self, marca, esperado
    ):
        from services.scraper import AGENCY_PHONE_SELECTORS, PropertyScraper

        chave = PropertyScraper()._chave_da_agencia(marca)
        assert chave == esperado
        assert chave in AGENCY_PHONE_SELECTORS

    def test_uma_marca_desconhecida_devolve_VAZIO_e_nao_unknown(self):
        """`unknown` ia como chave para a tabela de selectores e dava
        sempre miss: um sentinela a fingir que é uma chave."""
        from services.scraper import PropertyScraper

        assert PropertyScraper()._chave_da_agencia("unknown") == ""
        assert PropertyScraper()._chave_da_agencia("") == ""

    def test_as_marcas_do_reconhecimento_tem_todas_traducao_OU_nenhuma(self):
        """Guarda de inventário: qualquer marca do `AGENCY_DOMAINS` que
        TENHA selectores próprios tem de os alcançar.

        Falha por OMISSÃO quando alguém acrescentar uma agência com
        selectores e esquecer a tradução — que é exactamente o defeito
        que esta função existe para fechar.
        """
        from services.scraper import (
            AGENCY_DOMAINS,
            AGENCY_PHONE_SELECTORS,
            PropertyScraper,
        )

        scraper = PropertyScraper()
        for marca in AGENCY_DOMAINS:
            chave = scraper._chave_da_agencia(marca)
            if chave:
                assert chave in AGENCY_PHONE_SELECTORS, (
                    f"'{marca}' resolve para '{chave}', que não é uma chave "
                    "de AGENCY_PHONE_SELECTORS"
                )
