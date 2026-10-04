"""Testes unitários — navegação multi-nível até à página do anunciante.

`TestAExploracao` é o DEFEITO: escrito para passar contra o código novo e
para falhar contra o antigo. Documenta o que o motor não conseguia fazer.

O DEFEITO (LOTE 10)
===================
1. **O Idealista estava excluído por construção.** `_find_agency_links`
   descartava toda a ligação do mesmo domínio na primeira linha, e no
   Idealista o perfil do anunciante É uma página do Idealista (`/pro/...`).
   O portal que o cliente mais usa era exactamente o que nunca podia ser
   seguido.

2. **A admissão era uma lista à mão.** `AGENCY_DOMAINS` decide quem é
   agência; uma agência que não esteja lá nunca é seguida, e isso devolve
   uma visita sem contacto, indistinguível de um anúncio que não traz o
   comercial. Hoje a ROTA (`/pro/`, `/agencia/`, `/consultor/`) é o
   primeiro sinal e o domínio é o recurso.

3. **Existia um segundo motor completo e sem chamador.**
   `_deep_link_contacts` tinha uma ocorrência no ficheiro — o seu `def` — e
   chamava `self._get_next_proxy()`/`self._proxies` (inexistentes na classe)
   e `httpx` (importado só quando o `curl_cffi` falta), tudo dentro de um
   `except Exception: continue`. Religá-lo devolvia `{}` sem um erro no log.

4. **Sem pausa entre o 1.º e o 2.º pedido.** O único atraso do motor é o
   que corre DEPOIS de um 403. Dois GET consecutivos ao mesmo portal em
   milissegundos é o padrão que o Cloudflare procura — e o custo de ser
   apanhado não é este anúncio, é o IP ficar marcado para os seguintes.
"""
from __future__ import annotations

import pytest

from services.scraper_anunciante import (
    ORCAMENTO_DO_ANUNCIANTE,
    TEXTOS_DO_ANUNCIANTE,
    TEXTOS_RECUSADOS_DE_PROPOSITO,
    ORCAMENTO_DO_ANUNCIO,
    ROTULO_DO_ANUNCIANTE,
    ROTULO_DO_ANUNCIO,
    alvos_do_anunciante,
    contexto_para_a_ia,
    pagina_do_anunciante,
    pagina_do_anuncio,
    telefone_pt,
    tem_bloco_do_anunciante,
)

#: A lista de domínios do motor antigo, para provar que o reconhecimento
#: por ROTA não depende dela.
DOMINIOS_LEGADOS = ("remax", "era.pt", "century21", "zome")

URL_DO_ANUNCIO = "https://www.idealista.pt/imovel/33445566/"


class TestAExploracao:
    """O que o motor não conseguia fazer."""

    def test_o_perfil_do_anunciante_no_PROPRIO_portal_e_alcancavel(self):
        """DEFEITO 1 — no Idealista o anunciante vive no mesmo domínio.

        O motor antigo fazia `continue` para toda a ligação cujo domínio
        coincidisse com o do anúncio, pelo que este alvo era deitado fora
        antes de qualquer reconhecimento.
        """
        alvos = alvos_do_anunciante(
            [
                ("/imovel/33445566/#fotos", "Ver fotografias"),
                ("/pro/predial-atlantico-lda/", "Ver todos os imóveis desta agência"),
            ],
            url_de_origem=URL_DO_ANUNCIO,
            dominios_de_agencia=DOMINIOS_LEGADOS,
        )

        assert [alvo.url for alvo in alvos] == [
            "https://www.idealista.pt/pro/predial-atlantico-lda/"
        ]
        assert alvos[0].interno is True, "é o MESMO domínio do anúncio — e é esse o ponto"

    def test_uma_agencia_fora_da_lista_de_dominios_tambem_e_seguida(self):
        """DEFEITO 2 — a admissão não pode ser uma enumeração à mão."""
        alvos = alvos_do_anunciante(
            [("https://www.imoveis-da-marta.pt/consultor/marta-nunes", "Marta Nunes")],
            url_de_origem=URL_DO_ANUNCIO,
            dominios_de_agencia=DOMINIOS_LEGADOS,
        )

        assert len(alvos) == 1
        assert "rota /consultor" in alvos[0].motivo

    def test_o_motor_morto_desapareceu_do_scraper(self):
        """DEFEITO 3 — apagado, não religado.

        Código adormecido atrás de um caminho que ninguém percorre é um
        convite a religá-lo; e este, religado, devolvia `{}` em silêncio.
        """
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2] / "services" / "scraper.py"
        ).read_text(encoding="utf-8")

        assert "_deep_link_contacts" not in fonte
        assert "_get_next_proxy" not in fonte, "chamava um método que não existe"
        assert "self._proxies" not in fonte


class TestQualAlvoSeSegue:
    """A decisão, sobre dados e sem HTML."""

    def test_sem_nenhum_dos_tres_sinais_nao_e_alvo(self):
        alvos = alvos_do_anunciante(
            [
                ("https://www.idealista.pt/mapa", "Ver no mapa"),
                ("https://www.exemplo.pt/qualquer-coisa", "clica aqui"),
            ],
            url_de_origem=URL_DO_ANUNCIO,
            dominios_de_agencia=DOMINIOS_LEGADOS,
        )
        assert alvos == []

    def test_sair_do_portal_desempata_com_a_mesma_rota(self):
        """Na agência o telefone é o directo; no portal é o formulário."""
        alvos = alvos_do_anunciante(
            [
                ("/pro/casa-boa/", "Casa Boa"),
                ("https://www.casaboa.pt/agencia/lisboa", "Casa Boa"),
            ],
            url_de_origem=URL_DO_ANUNCIO,
            dominios_de_agencia=DOMINIOS_LEGADOS,
        )
        assert alvos[0].url == "https://www.casaboa.pt/agencia/lisboa"
        assert alvos[0].interno is False

    def test_a_rota_pesa_mais_do_que_o_dominio_conhecido(self):
        alvos = alvos_do_anunciante(
            [
                ("https://www.remax.pt/", "Remax"),
                ("https://www.remax.pt/agencia/alvalade", "Remax Alvalade"),
            ],
            url_de_origem=URL_DO_ANUNCIO,
            dominios_de_agencia=DOMINIOS_LEGADOS,
        )
        assert alvos[0].url == "https://www.remax.pt/agencia/alvalade"

    @pytest.mark.parametrize(
        "caminho",
        [
            "/pro/termos-e-condicoes",
            "/agencia/precos",
            "/consultores/recrutamento",
            "/imobiliaria/blog/mercado-2026",
        ],
    )
    def test_as_paginas_legais_e_de_marketing_nao_gastam_o_salto(self, caminho):
        alvos = alvos_do_anunciante(
            [(caminho, "ver")], url_de_origem=URL_DO_ANUNCIO
        )
        assert alvos == []

    @pytest.mark.parametrize(
        "href",
        [
            "tel:+351912345678",
            "mailto:geral@exemplo.pt",
            "javascript:void(0)",
            "data:text/html,<p>/pro/x</p>",
            "#pro/agencia",
            "",
        ],
    )
    def test_o_que_nao_e_uma_pagina_nao_se_segue(self, href):
        assert alvos_do_anunciante([(href, "página da agência")],
                                   url_de_origem=URL_DO_ANUNCIO) == []

    def test_a_propria_pagina_do_anuncio_nunca_e_alvo(self):
        """Seguir-se a si mesmo gasta o salto e não traz nada de novo."""
        alvos = alvos_do_anunciante(
            [(URL_DO_ANUNCIO, "site do anunciante")],
            url_de_origem=URL_DO_ANUNCIO,
        )
        assert alvos == []

    def test_a_ancora_nao_duplica_o_mesmo_perfil(self):
        alvos = alvos_do_anunciante(
            [
                ("/pro/casa-boa/#contactos", "Casa Boa"),
                ("/pro/casa-boa/#imoveis", "Casa Boa"),
                ("/pro/casa-boa/", "Casa Boa"),
            ],
            url_de_origem=URL_DO_ANUNCIO,
        )
        assert len(alvos) == 1

    def test_a_ordem_e_estavel_com_pesos_iguais(self):
        """Senão o alvo seguido depende da ordem do HTML e o mesmo anúncio
        dá resultados diferentes em duas passagens."""
        ligacoes = [
            ("/agencia/b-imoveis", "B"),
            ("/agencia/a-imoveis", "A"),
        ]
        primeira = alvos_do_anunciante(ligacoes, url_de_origem=URL_DO_ANUNCIO)
        segunda = alvos_do_anunciante(list(reversed(ligacoes)),
                                      url_de_origem=URL_DO_ANUNCIO)
        assert [a.url for a in primeira] == [a.url for a in segunda]

    def test_aceita_dicionarios_como_o_scraper_os_tem(self):
        alvos = alvos_do_anunciante(
            [{"href": "/pro/casa-boa/", "texto": "Casa Boa"}],
            url_de_origem=URL_DO_ANUNCIO,
        )
        assert len(alvos) == 1

    def test_um_subdominio_do_portal_continua_interno(self):
        """`pro.idealista.pt` é o mesmo portal que `www.idealista.pt`.

        Comparar o `netloc` cru dava-lhe o bónus de «sai do portal», que
        existe para a página da AGÊNCIA (onde o telefone é o directo do
        consultor) e não para outro subdomínio do mesmo agregador. A
        primeira versão deste teste afirmava `== [] or interno is True`:
        podia passar sem provar nada, o que as regras do projecto
        proíbem.
        """
        alvos = alvos_do_anunciante(
            [("https://pro.idealista.pt/agencia/x", "x")],
            url_de_origem="https://www.idealista.pt/imovel/1/",
        )
        assert len(alvos) == 1
        assert alvos[0].interno is True
        assert "sai do portal" not in alvos[0].motivo


class TestOsTextosQueSeReconhecem:
    """A lista herdada do `AGENCY_LINK_TEXTS`, e o que ficou de fora.

    Ao extrair a decisão para o módulo puro deixei cair NOVE dos treze
    textos do original, e não foi o teste que o apanhou — foi um
    inventário de constantes ÓRFÃS feito na revisão do meu próprio diff
    (`AGENCY_LINK_TEXTS` passou a ter uma única ocorrência: a definição).
    Quatro foram repostos, cinco ficam recusados de propósito, e os dois
    testes abaixo fixam a diferença para ela ser uma decisão e não um
    esquecimento.
    """

    @pytest.mark.parametrize("texto", TEXTOS_DO_ANUNCIANTE)
    def test_cada_texto_reconhecido_produz_um_alvo(self, texto):
        alvos = alvos_do_anunciante(
            [("https://www.agencia-qualquer.pt/p/9988", texto)],
            url_de_origem=URL_DO_ANUNCIO,
        )
        assert len(alvos) == 1, f"«{texto}» devia ser reconhecido"

    @pytest.mark.parametrize("texto", TEXTOS_RECUSADOS_DE_PROPOSITO)
    def test_os_rotulos_genericos_nao_gastam_o_salto(self, texto):
        """«Ver detalhes» aparece em cada cartão de uma lista de
        resultados: com UM salto por anúncio, um alvo errado custa o
        mesmo que o certo e não traz nada."""
        alvos = alvos_do_anunciante(
            [("https://www.agencia-qualquer.pt/p/9988", texto)],
            url_de_origem=URL_DO_ANUNCIO,
        )
        assert alvos == [], f"«{texto}» é navegação genérica"

    def test_as_duas_listas_nao_se_cruzam(self):
        """Contraprova: um texto nas duas listas tornaria um dos testes
        acima impossível de satisfazer, e o conflito passaria como um
        falhanço misterioso em vez de uma contradição."""
        assert not (
            set(TEXTOS_DO_ANUNCIANTE) & set(TEXTOS_RECUSADOS_DE_PROPOSITO)
        )


class TestOContextoQueVaiAIA:
    """Duas páginas, uma chamada, orçamentos separados."""

    def test_os_dois_blocos_vao_rotulados(self):
        contexto = contexto_para_a_ia([
            pagina_do_anuncio("T3 em Cascais, 450.000 €", URL_DO_ANUNCIO),
            pagina_do_anunciante("Marta Nunes 912 345 678",
                                 "https://www.idealista.pt/pro/x/"),
        ])
        assert ROTULO_DO_ANUNCIO in contexto
        assert ROTULO_DO_ANUNCIANTE in contexto
        assert contexto.index(ROTULO_DO_ANUNCIO) < contexto.index(ROTULO_DO_ANUNCIANTE)

    def test_a_pagina_do_anunciante_NUNCA_rouba_espaco_ao_anuncio(self):
        """O orçamento é POR bloco.

        Com um orçamento único e uma concatenação, uma página de
        anunciante enorme (são quase todas: navegação + listas de imóveis)
        empurrava o preço e a área para fora da janela. Um upgrade de
        contactos que piorasse o preço era um mau negócio.
        """
        # `Z`/`W` e não `A`/`B`: os RÓTULOS contêm «A» («PÁGINA DO
        # ANÚNCIO»), pelo que contar «A» no contexto inteiro media o
        # cabeçalho a par do corpo — a primeira versão deste teste falhou
        # por isso, e era o teste que estava errado.
        anuncio = "Z" * (ORCAMENTO_DO_ANUNCIO + 5000)
        anunciante = "W" * (ORCAMENTO_DO_ANUNCIANTE + 90000)

        contexto = contexto_para_a_ia([
            pagina_do_anuncio(anuncio, URL_DO_ANUNCIO),
            pagina_do_anunciante(anunciante, "https://x.pt/pro/y"),
        ])

        assert contexto.count("Z") == ORCAMENTO_DO_ANUNCIO
        assert contexto.count("W") == ORCAMENTO_DO_ANUNCIANTE

    def test_uma_pagina_vazia_nao_produz_rotulo(self):
        """Um rótulo com nada debaixo convida o modelo a inventar."""
        contexto = contexto_para_a_ia([
            pagina_do_anuncio("T3 em Cascais", URL_DO_ANUNCIO),
            pagina_do_anunciante("   ", "https://x.pt/pro/y"),
        ])
        assert ROTULO_DO_ANUNCIANTE not in contexto
        assert tem_bloco_do_anunciante(contexto) is False

    def test_so_o_anuncio_continua_a_ser_um_contexto_valido(self):
        contexto = contexto_para_a_ia([pagina_do_anuncio("T2", URL_DO_ANUNCIO)])
        assert ROTULO_DO_ANUNCIO in contexto
        assert tem_bloco_do_anunciante(contexto) is False

    def test_o_url_de_cada_bloco_viaja_com_ele(self):
        contexto = contexto_para_a_ia([
            pagina_do_anuncio("x", URL_DO_ANUNCIO),
            pagina_do_anunciante("y", "https://www.idealista.pt/pro/abc/"),
        ])
        assert URL_DO_ANUNCIO in contexto
        assert "https://www.idealista.pt/pro/abc/" in contexto


class TestOTelefone:
    """Um telefone que não é um telefone é pior do que nenhum."""

    @pytest.mark.parametrize(
        "bruto,esperado",
        [
            ("912345678", "912345678"),
            ("912 345 678", "912345678"),
            ("+351 912 345 678", "912345678"),
            ("+351912345678", "912345678"),
            ("00351 912345678", "912345678"),
            ("351912345678", "912345678"),
            ("(+351) 912-345-678", "912345678"),
            ("tel:+351912345678", "912345678"),
            ("213456789", "213456789"),
            ("+351 21 345 67 89", "213456789"),
        ],
    )
    def test_normaliza_o_que_e_valido(self, bruto, esperado):
        assert telefone_pt(bruto) == esperado

    @pytest.mark.parametrize(
        "bruto",
        [
            None,
            "",
            "   ",
            "N/A",
            "12345",
            "9123456789",          # um dígito a mais
            "91234567",            # um dígito a menos
            "812345678",           # 8 não é prefixo português
            "994345678",           # 99 não é gama de telemóvel
            "201345678",           # 20 não é indicativo válido
            "+34 612 345 678",     # Espanha
            True,
        ],
    )
    def test_recusa_em_vez_de_adivinhar(self, bruto):
        assert telefone_pt(bruto) is None

    def test_um_preco_nao_passa_por_telefone(self):
        """`450.000 €` tem nove dígitos quando se tiram os pontos."""
        assert telefone_pt("450.000") is None
