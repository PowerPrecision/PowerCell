"""Do que o scraper devolve para os campos da visita — `ficha_do_imovel`.

O QUE CORREU MAL (D-23)
=======================
O `scraper.py` devolve ~30 campos (o prompt da IA pede explicitamente
`estado`, `orientacao_solar`, `condominio`, `piso`, `elevador`, `varanda`,
`vista`, `url_planta`, `url_video`, `agencia_telefone`) e o mapeador para
`ScrapedData` tinha uma lista escrita à mão de **onze** — tudo o que não
estava nela era silenciosamente perdido. O `estado` do imóvel
(novo/usado/remodelado/para renovar) é um dos campos que o quadro de
visitas precisa, é extraído pela IA desde sempre, e **nunca chegou a
sítio nenhum**.

Mesma forma de «os dois mapas de campos da IA têm de concordar» (o
`naturalidade` do `AI_SUGGESTION_FIELD_MAP`): o lado que traduz descarta
em silêncio o que não conhece, e a extracção parece ter corrido bem.

E HAVIA DOIS MAPEADORES, JÁ DIVERGENTES
=======================================
`visit_helpers._run_scraper_for_visit` (caminho do CRM) e
`portal_client_visits._background_visit_scraper_and_notify` (caminho do
Portal) traduziam o MESMO resultado para os MESMOS campos, escritos à mão
duas vezes — e já divergiam: o do Portal guardava `raw_data`, o do CRM
não. Ou seja, uma visita criada no CRM perdia também `quartos`,
`casas_banho`, `certificado_energetico`, `ano_construcao`, `descricao` e
`referencia`. Duas cópias de uma tradução divergem na primeira mudança, e
a que divergir não dá erro: devolve menos.

TRÊS VEREDICTOS, NÃO DOIS
=========================
O estado era `completed`/`error`. Falta o caso do meio: um portal que
mude o HTML devolve 200 com **tudo vazio**, e isso contava como sucesso —
a visita ficava com `scraper_status: completed` e sem um único dado,
indistinguível de um imóvel sem informação. `sem_dados` é um veredicto
próprio, para o ecrã poder dizer «não consegui ler este anúncio» e para
alguém poder contar quantos são.

NADA SE SOBRESCREVE COM VAZIO
=============================
Só se emitem os campos que têm valor. Um segundo scraping que falhe
parcialmente não pode apagar o título que o primeiro leu — é a regra do
`_preencher_se_vazio` do RGPD, noutro eixo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

#: `185.000` / `1.250.000`: só pontos a separar grupos de TRÊS dígitos.
_SO_MILHARES = re.compile(r"^\d{1,3}(\.\d{3})+$")

#: O scraper respondeu e trouxe pelo menos um dado útil.
VEREDICTO_COMPLETA = "completed"
#: O scraper respondeu e não trouxe NADA. Não é sucesso.
VEREDICTO_SEM_DADOS = "sem_dados"
#: Falha de leitura (rede, anti-bot, URL morto).
VEREDICTO_ERRO = "error"

#: Os campos de `ScrapedData` que viajam com nome próprio. Tudo o que o
#: scraper devolver FORA desta lista entra em `raw_data` — é o que faz o
#: `raw_data` DERIVAR em vez de ser uma lista à mão.
CAMPOS_PROPRIOS = (
    "url", "title", "price", "location", "typology", "area",
    "photo_url", "consultant", "source", "raw_data",
)

#: Os campos que o ecrã das Visitas mostra em coluna própria. O `estado`
#: entra aqui porque é um dos pedidos do quadro novo e porque é o campo
#: que se perdia.
CAMPOS_DA_VISITA = (
    "property_title",
    "scraped_price",
    "property_photo",
    "property_address",
    "scraped_typology",
    "scraped_area",
    "scraped_estado",
)


@dataclass(frozen=True)
class FichaDoImovel:
    """O resultado da tradução: o que gravar, e o veredicto."""

    veredicto: str
    campos: dict = field(default_factory=dict)
    motivo: str = ""

    @property
    def tem_dados(self) -> bool:
        return self.veredicto == VEREDICTO_COMPLETA


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, (list, tuple, set, dict)):
        return ""
    return str(valor).strip()


def _numero(valor: Any) -> Optional[float]:
    """Um número, ou `None`. Nunca levanta.

    O scraper devolve o preço ora como número ora como texto (`"185.000 €"`
    quando a IA não converteu), e um `float()` cru rebentava o pipeline de
    fundo — onde uma excepção fica num log que ninguém lê.
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    bruto = _texto(valor)
    if not bruto:
        return None
    limpo = (
        bruto.replace("€", "").replace("m²", "").replace("m2", "")
        .replace(" ", "").replace(" ", "")
    )
    # `185.000,50` (PT) e `185000.50` (EN) no mesmo predicado.
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    elif _SO_MILHARES.match(limpo):
        # `185.000` é cento e oitenta e cinco mil, não 185 — e foi assim
        # que o teste apanhou o preço de um anúncio a aparecer como
        # «185 €». A regra é ESTREITA de propósito: só grupos de
        # exactamente três dígitos (`185.000`, `1.250.000`) contam como
        # separador de milhares. `1234.56`, `95.5` e `120.75` continuam
        # decimais, porque adivinhar ali trocava um preço por outro.
        limpo = limpo.replace(".", "")
    try:
        return float(limpo)
    except (TypeError, ValueError):
        return None


def raw_data_derivado(bruto: Optional[dict]) -> dict:
    """Tudo o que o scraper devolveu e não tem nome próprio.

    DERIVA do dicionário em vez de o copiar campo a campo: foi a lista à
    mão que perdeu o `estado`, e qualquer campo novo do prompt da IA
    chegaria ao mesmo destino. As chaves com `_` à cabeça (`_source`,
    `_deep_scraped`, …) são metadados do scraper e entram também — é o que
    permite saber QUEM extraiu sem uma segunda lista.
    """
    if not isinstance(bruto, dict):
        return {}
    return {
        chave: valor
        for chave, valor in bruto.items()
        if chave not in CAMPOS_PROPRIOS
    }


#: As chaves (em português) que o `scraper.py` devolve e que o
#: `property_scraper` já traduz para um campo com nome próprio do
#: `ScrapedData`. Tudo o que NÃO está aqui viaja em `raw_data` — é esta
#: lista, e só esta, que decide o que se perde.
#:
#: `agencia_telefone` está deliberadamente FORA: não cabe no
#: `ConsultantInfo` e era um dos campos que se perdiam. `area_util`
#: também, porque é um valor DIFERENTE do `area` (o mapeador usa um como
#: recurso do outro) e guardar os dois é informação, não duplicação.
CHAVES_JA_COM_NOME_PROPRIO = (
    "titulo",
    "preco",
    "localizacao",
    "tipologia",
    "area",
    "foto_principal",
    "agente_nome",
    "agente_telefone",
    "agente_email",
    "agencia_nome",
)


def raw_data_do_scraper(resultado: Optional[dict]) -> dict:
    """O `raw_data` de um `ScrapedData`, DERIVADO do que o scraper devolveu.

    O `property_scraper` tinha aqui uma lista de ONZE chaves escrita à
    mão, sobre ~30 devolvidas: `estado`, `orientacao_solar`, `condominio`,
    `piso`, `elevador`, `varanda`, `vista`, `url_planta`, `url_video` e
    `agencia_telefone` desapareciam em silêncio, e qualquer campo novo do
    prompt da IA desapareceria pelo mesmo caminho.

    Os metadados do scraper (`_source`, `_deep_scraped`, `_extracted_by`,
    …) entram de propósito: é o que permite saber QUEM extraiu — e com
    que modelo, depois da D-22 — sem uma segunda lista.
    """
    if not isinstance(resultado, dict):
        return {}
    return {
        chave: valor
        for chave, valor in resultado.items()
        if chave not in CHAVES_JA_COM_NOME_PROPRIO
    }


def _consultor(scraped: Any) -> Optional[dict]:
    consultor = getattr(scraped, "consultant", None)
    if not consultor:
        return None
    return {
        "name": getattr(consultor, "name", None),
        "phone": getattr(consultor, "phone", None),
        "email": getattr(consultor, "email", None),
        "agency_name": getattr(consultor, "agency_name", None),
    }


def ficha_do_imovel(scraped: Any, *, url: str, agora: str) -> FichaDoImovel:
    """Traduz o resultado do scraper nos campos a gravar na visita.

    Ponto ÚNICO: serve o caminho do CRM e o do Portal. Pura — não toca na
    base de dados nem no relógio (o `agora` entra por parâmetro, senão
    dois registos da mesma passagem levavam marcas diferentes).
    """
    if scraped is None:
        return FichaDoImovel(
            veredicto=VEREDICTO_ERRO,
            campos={
                "scraped_url": url,
                "scraper_status": VEREDICTO_ERRO,
                "scraper_error": "O scraper não devolveu resultado.",
                "updated_at": agora,
            },
            motivo="sem resultado",
        )

    cru = getattr(scraped, "raw_data", None) or {}
    fonte = _texto(getattr(scraped, "source", "")) or "manual"

    if fonte == "error":
        erro = _texto(cru.get("error")) or "Falha ao extrair dados do imóvel"
        return FichaDoImovel(
            veredicto=VEREDICTO_ERRO,
            campos={
                "scraped_url": url,
                "scraper_status": VEREDICTO_ERRO,
                "scraper_error": erro,
                "updated_at": agora,
            },
            motivo=erro,
        )

    extra = raw_data_derivado(cru)

    titulo = _texto(getattr(scraped, "title", ""))
    preco = _numero(getattr(scraped, "price", None))
    localizacao = _texto(getattr(scraped, "location", ""))
    tipologia = _texto(getattr(scraped, "typology", ""))
    area = _numero(getattr(scraped, "area", None))
    foto = _texto(getattr(scraped, "photo_url", ""))
    # O `estado` NUNCA teve nome próprio no `ScrapedData`: viaja no
    # `raw_data`, e é exactamente por isso que a lista à mão o perdia.
    estado = _texto(extra.get("estado"))

    scraped_data = {
        "title": titulo or None,
        "price": preco,
        "location": localizacao or None,
        "typology": tipologia or None,
        "area": area,
        "photo_url": foto or None,
        "source": fonte,
        "url": url,
        "consultant": _consultor(scraped),
        # `raw_data` entra nos DOIS caminhos: o do CRM não o guardava, e
        # com isso perdia quartos, casas de banho, certificado
        # energético, ano de construção, descrição e referência.
        "raw_data": extra,
    }

    campos: dict = {
        "scraped_data": scraped_data,
        "scraped_url": url,
        "scraper_error": None,
        "updated_at": agora,
    }

    # Nada se sobrescreve com vazio: um segundo scraping parcial não pode
    # apagar o que o primeiro leu.
    if titulo:
        campos["property_title"] = titulo
    if preco is not None:
        campos["scraped_price"] = preco
    if foto:
        campos["property_photo"] = foto
    if localizacao:
        campos["property_address"] = {
            "municipality": localizacao,
            "district": "",
        }
    if tipologia:
        campos["scraped_typology"] = tipologia
    if area is not None:
        campos["scraped_area"] = area
    if estado:
        campos["scraped_estado"] = estado

    tem_algum = any(campo in campos for campo in CAMPOS_DA_VISITA)
    veredicto = VEREDICTO_COMPLETA if tem_algum else VEREDICTO_SEM_DADOS
    campos["scraper_status"] = veredicto

    return FichaDoImovel(
        veredicto=veredicto,
        campos=campos,
        motivo="" if tem_algum else "o anúncio respondeu sem dados legíveis",
    )


__all__ = [
    "CAMPOS_DA_VISITA",
    "CAMPOS_PROPRIOS",
    "CHAVES_JA_COM_NOME_PROPRIO",
    "FichaDoImovel",
    "VEREDICTO_COMPLETA",
    "VEREDICTO_ERRO",
    "VEREDICTO_SEM_DADOS",
    "ficha_do_imovel",
    "raw_data_derivado",
    "raw_data_do_scraper",
]
