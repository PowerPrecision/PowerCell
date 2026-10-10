"""Extracção de um anúncio sem depender das classes CSS do portal (Bloco 5, ponto 1).

O PROBLEMA
==========
Os parsers por portal (`_parse_imovirtual`, `_parse_casasapo`, `_parse_remax`,
`_parse_kw`…) assentam em `data-cy="adPageHeaderPrice"`, `class="priceValue"`,
`class="details-price"`: nomes que o portal muda sem aviso numa publicação do
front-end. Quando mudam o parser não dá erro — devolve um dicionário vazio, o
scraper cai na IA (uma chamada paga) ou, pior, grava uma visita sem nada. Havia
ainda defeitos que nada têm a ver com o DOM:

* o JSON-LD era lido com `json_data.get('offers', {}).get('price')`, e `offers`
  é muitas vezes uma **lista** — `AttributeError`, não apanhado, e o scrape
  inteiro rebentava;
* só se lia um JSON-LD que fosse um dicionário na raiz (nem listas, nem
  `@graph`);
* `re.sub(r'[^\\d]', '', texto)` fundia `250.000 – 300.000` em `250000300000`;
* uma página de desafio anti-bot (HTTP 200) era tratada como anúncio.

A REGRA
=======
Esta camada lê as três fontes que o portal **não pode** mudar sem prejudicar o
seu próprio SEO e as partilhas — pela ordem em que são fiáveis:

1. **JSON-LD** (`schema.org`): contrato público, lido pelo Google;
2. **JSON embebido** (`__NEXT_DATA__`, que é como as aplicações Next.js — o
   Imovirtual — entregam o anúncio ao browser), procurado por **nomes de
   campo** e nunca por caminho fixo;
3. **meta tags** (`og:*`, `product:price:*`) e, no fim, **texto rotulado**
   («Área útil: 85 m²», «3 quartos»).

Corre **depois** do parser do portal e só **preenche o que lá falta**: o que o
parser específico leu continua a ganhar (conhece o portal). É puro — recebe o
HTML, devolve um dicionário com as chaves que o resto do scraper já usa
(`titulo`, `preco`, `area`, `quartos`…) — e **nunca levanta**.

DUAS DECISÕES
=============
* **Um preço duvidoso é pior do que nenhum.** Intervalos («250.000 – 300.000»),
  valores fora de [`PRECO_MINIMO`, `PRECO_MAXIMO`] e «sob consulta» dão `None`:
  um preço errado vai para o quadro de visitas com ar de certo.
* **Nada de «o primeiro número da página».** O texto só é lido com a etiqueta ao
  lado («Área útil», «quartos»); o único recurso sem etiqueta é o primeiro valor
  em euros, e só para o preço, e só quando as fontes estruturadas não o têm.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

#: Fora disto não é o preço de venda de um imóvel (rendas, lixo, ano da obra).
PRECO_MINIMO = 1_000
PRECO_MAXIMO = 100_000_000

#: Área plausível em m² (uma arrecadação… até uma quinta).
AREA_MINIMA = 5
AREA_MAXIMA = 1_000_000

#: Tipos schema.org de que se lê o anúncio.
_TIPOS_DE_ANUNCIO = {
    "product", "realestatelisting", "offer", "aggregateoffer", "residence",
    "house", "apartment", "singlefamilyresidence", "accommodation", "place",
    "singlefamilyhome", "room", "suite",
}

# ====================================================================
# NÚMEROS — o que `re.sub(r'[^\d]', '', …)` fazia mal
# ====================================================================
_RE_INTERVALO = re.compile(r"\d\s*(?:[-–—]|\ba\b|\bat[ée]\b)\s*\d", re.IGNORECASE)
_RE_NUMERO = re.compile(r"\d[\d.\s ]*(?:,\d+)?|\d+(?:\.\d+)?")


def numero_pt(valor: Any) -> Optional[float]:
    """Um número em formato português ou internacional, ou `None`.

    Aceita `185.000`, `185 000`, `1.250.000,50`, `85,5`, `85.5`, `€ 250 000`,
    inteiros e decimais. Recusa intervalos: «250.000 – 300.000» não é nenhum dos
    dois extremos.
    """
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, (list, tuple)):
        return numero_pt(valor[0]) if len(valor) == 1 else None
    if isinstance(valor, dict):
        for chave in ("value", "amount", "valor"):
            if chave in valor:
                return numero_pt(valor[chave])
        return None
    texto = str(valor).strip()
    if not texto or _RE_INTERVALO.search(texto):
        return None
    achado = _RE_NUMERO.search(texto)
    if not achado:
        return None
    numero = achado.group(0).strip().replace(" ", "").replace(" ", "")
    if "," in numero:
        numero = numero.replace(".", "").replace(",", ".")
    elif numero.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", numero):
        numero = numero.replace(".", "")  # só milhares: 185.000 → 185000
    try:
        return float(numero)
    except ValueError:
        return None


def _inteiro(valor: Any) -> Optional[int]:
    numero = numero_pt(valor)
    return int(round(numero)) if numero is not None else None


def preco(valor: Any) -> Optional[int]:
    numero = numero_pt(valor)
    if numero is None or not (PRECO_MINIMO <= numero <= PRECO_MAXIMO):
        return None
    return int(round(numero))


def area(valor: Any) -> Optional[float]:
    numero = numero_pt(valor)
    if numero is None or not (AREA_MINIMA <= numero <= AREA_MAXIMA):
        return None
    return int(numero) if float(numero).is_integer() else round(numero, 1)


def _contagem(valor: Any) -> Optional[int]:
    """Quartos / casas de banho: 0–30."""
    numero = _inteiro(valor)
    return numero if numero is not None and 0 <= numero <= 30 else None


def _ano(valor: Any) -> Optional[int]:
    numero = _inteiro(valor)
    return numero if numero is not None and 1700 <= numero <= 2100 else None


def _texto(valor: Any, maximo: int = 5000) -> Optional[str]:
    if isinstance(valor, str):
        limpo = re.sub(r"\s+", " ", valor).strip()
        return limpo[:maximo] or None
    return None


# ====================================================================
# JSON-LD
# ====================================================================
def _blocos_json(soup) -> Iterable[Any]:
    """Todos os JSON-LD da página, mal formados ignorados um a um."""
    for script in soup.find_all("script", type="application/ld+json"):
        bruto = script.string or script.get_text() or ""
        if not bruto.strip():
            continue
        try:
            yield json.loads(bruto)
        except (ValueError, TypeError):
            # Um JSON-LD com vírgula a mais não pode esconder os outros.
            logger.debug("[SCRAPER-EST] JSON-LD ilegível ignorado")


def _dicionarios(no: Any) -> Iterable[dict]:
    """Percorre listas, `@graph` e dicionários aninhados."""
    pilha = [no]
    while pilha:
        actual = pilha.pop(0)
        if isinstance(actual, dict):
            yield actual
            pilha.extend(v for v in actual.values() if isinstance(v, (dict, list)))
        elif isinstance(actual, list):
            pilha.extend(actual)


def _tipos(dicionario: dict) -> set[str]:
    tipo = dicionario.get("@type")
    tipos = tipo if isinstance(tipo, list) else [tipo]
    return {str(t).rsplit("/", 1)[-1].lower() for t in tipos if t}


def _primeira_imagem(valor: Any) -> Optional[str]:
    if isinstance(valor, str):
        return valor if valor.startswith(("http://", "https://", "//")) else None
    if isinstance(valor, list):
        for item in valor:
            achada = _primeira_imagem(item)
            if achada:
                return achada
    if isinstance(valor, dict):
        return _primeira_imagem(valor.get("url") or valor.get("contentUrl"))
    return None


def _preco_da_oferta(oferta: Any) -> Optional[int]:
    """`offers` é um dicionário, uma lista ou um `AggregateOffer`."""
    for item in oferta if isinstance(oferta, list) else [oferta]:
        if not isinstance(item, dict):
            continue
        for chave in ("price", "lowPrice", "highPrice"):
            achado = preco(item.get(chave))
            if achado:
                return achado
        especificacao = item.get("priceSpecification")
        if isinstance(especificacao, (dict, list)):
            achado = _preco_da_oferta(especificacao)
            if achado:
                return achado
    return None


def _localizacao(endereco: Any) -> tuple[Optional[str], Optional[str]]:
    """(localização, código postal) de um `PostalAddress` ou de um texto."""
    if isinstance(endereco, str):
        return _texto(endereco, 300), None
    if not isinstance(endereco, dict):
        return None, None
    partes = [
        _texto(endereco.get(c), 120)
        for c in ("streetAddress", "addressLocality", "addressRegion")
    ]
    codigo = _texto(endereco.get("postalCode"), 20)
    texto = ", ".join(p for p in partes if p)
    return (texto or None), codigo


def extrair_json_ld(soup) -> dict:
    """Os campos do anúncio a partir do JSON-LD."""
    saida: dict = {}
    for bloco in _blocos_json(soup):
        for d in _dicionarios(bloco):
            tipos = _tipos(d)
            if not (tipos & _TIPOS_DE_ANUNCIO) and "offers" not in d:
                continue
            preco_ld = _preco_da_oferta(d.get("offers")) if "offers" in d else None
            if preco_ld is None and "price" in d:
                preco_ld = preco(d.get("price"))
            candidatos = {
                "titulo": _texto(d.get("name"), 300),
                "descricao": _texto(d.get("description")),
                "preco": preco_ld,
                "foto_principal": _primeira_imagem(d.get("image")),
                "area": area(d.get("floorSize")),
                "quartos": _contagem(d.get("numberOfBedrooms") if d.get("numberOfBedrooms") is not None else d.get("numberOfRooms")),
                "casas_banho": _contagem(d.get("numberOfBathroomsTotal") if d.get("numberOfBathroomsTotal") is not None else d.get("numberOfBathrooms")),
                "ano_construcao": _ano(d.get("yearBuilt")),
            }
            localizacao, codigo_postal = _localizacao(d.get("address"))
            candidatos["localizacao"] = localizacao
            candidatos["codigo_postal"] = codigo_postal
            for chave, valor in candidatos.items():
                if valor not in (None, "") and chave not in saida:
                    saida[chave] = valor
    return saida


# ====================================================================
# JSON EMBEBIDO (`__NEXT_DATA__`) — por NOMES de campo, nunca por caminho
# ====================================================================
# Cada grupo: chave de saída → (nomes aceites em minúsculas, validador).
_GRUPOS_NEXT = {
    "preco": (("price", "totalprice", "pricevalue", "askingprice", "saleprice"), preco),
    "area": (("area", "usablearea", "livingarea", "floorsize", "areautil", "usable_area"), area),
    "quartos": (("rooms_num", "roomsnumber", "numberofrooms", "bedrooms", "numberofbedrooms", "rooms", "bedrooms_num"), _contagem),
    "casas_banho": (("bathrooms_num", "bathrooms", "numberofbathrooms"), _contagem),
    "ano_construcao": (("build_year", "yearbuilt", "constructionyear", "construction_year"), _ano),
    "certificacao_energetica": (("energy_certificate", "energycertificate", "energyclass", "energy_class"), None),
}
_TEXTOS_NEXT = {
    "titulo": ("title", "adtitle"),
    "descricao": ("description",),
}


def _valor_escalar(valor: Any) -> Any:
    """Os portais devolvem `['3']`, `{'value': 85}` ou `85`."""
    if isinstance(valor, list) and len(valor) == 1:
        valor = valor[0]
    if isinstance(valor, dict):
        for chave in ("value", "label", "name"):
            if chave in valor:
                return valor[chave]
        return None
    if isinstance(valor, (list, dict)):
        return None
    return valor


def _classe_energetica(valor: Any) -> Optional[str]:
    texto = str(valor or "").strip().upper().replace("_PLUS", "+")
    achado = re.fullmatch(r"(?:CLASSE\s*)?([A-G][+\-]?)", texto)
    return achado.group(1) if achado else None


def extrair_json_embebido(soup) -> dict:
    """Os campos do anúncio a partir do `__NEXT_DATA__` (e JSON equivalente)."""
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        return {}
    try:
        dados = json.loads(script.string or script.get_text() or "")
    except (ValueError, TypeError):
        logger.debug("[SCRAPER-EST] __NEXT_DATA__ ilegível")
        return {}

    def valores_do_dicionario(d: dict) -> dict:
        achados = {}
        minusculas = {str(k).lower(): v for k, v in d.items()}
        for saida, (nomes, validar) in _GRUPOS_NEXT.items():
            for nome in nomes:
                if nome in minusculas:
                    bruto = _valor_escalar(minusculas[nome])
                    valor = _classe_energetica(bruto) if saida == "certificacao_energetica" else (validar(bruto) if validar else bruto)
                    if valor not in (None, ""):
                        achados[saida] = valor
                        break
        return achados

    # O dicionário do ANÚNCIO é o mais raso que traz pelo menos dois dados
    # numéricos (preço + área, preço + quartos…): é assim que as «listas de
    # imóveis semelhantes», mais fundas, não contaminam a ficha.
    melhor: dict = {}
    for d in _dicionarios(dados):
        encontrados = valores_do_dicionario(d)
        if len(encontrados) >= 2 and len(encontrados) > len(melhor):
            melhor = encontrados
            if len(melhor) >= 4:
                break
    saida = dict(melhor)

    for d in _dicionarios(dados):
        minusculas = {str(k).lower(): v for k, v in d.items()}
        for chave, nomes in _TEXTOS_NEXT.items():
            if chave in saida:
                continue
            for nome in nomes:
                texto = _texto(minusculas.get(nome), 300 if chave == "titulo" else 5000)
                if texto and len(texto) >= 6:
                    saida[chave] = texto
                    break
        if all(k in saida for k in _TEXTOS_NEXT):
            break
    return saida


# ====================================================================
# META TAGS
# ====================================================================
def _meta(soup, **atributos) -> Optional[str]:
    elemento = soup.find("meta", attrs=atributos)
    return _texto(elemento.get("content")) if elemento else None


def extrair_meta(soup) -> dict:
    saida: dict = {}
    titulo = _meta(soup, property="og:title") or _meta(soup, name="twitter:title")
    if titulo:
        saida["titulo"] = titulo[:300]
    descricao = _meta(soup, property="og:description") or _meta(soup, name="description")
    if descricao:
        saida["descricao"] = descricao
    imagem = _primeira_imagem(_meta(soup, property="og:image") or _meta(soup, name="twitter:image"))
    if imagem:
        saida["foto_principal"] = imagem
    for atributos in ({"property": "product:price:amount"}, {"property": "og:price:amount"}, {"itemprop": "price"}):
        valor = preco(_meta(soup, **atributos))
        if valor:
            saida["preco"] = valor
            break
    return saida


# ====================================================================
# TEXTO ROTULADO — só com a etiqueta ao lado
# ====================================================================
_NUMERO_M2 = r"(\d[\d.\s,]*)\s*m(?:2|²)"
_PADROES_DE_TEXTO: tuple[tuple[str, re.Pattern, Any], ...] = (
    ("area", re.compile(r"[áa]rea\s*(?:[úu]til|habit[áa]vel|interior)\s*[:\-]?\s*" + _NUMERO_M2, re.IGNORECASE), area),
    ("area_bruta", re.compile(r"[áa]rea\s*(?:bruta|de\s*constru[çc][ãa]o|total)\s*[:\-]?\s*" + _NUMERO_M2, re.IGNORECASE), area),
    ("area_terreno", re.compile(r"(?:[áa]rea\s*(?:do\s*)?terreno|terreno)\s*[:\-]?\s*" + _NUMERO_M2, re.IGNORECASE), area),
    ("quartos", re.compile(r"(?:quartos?|assoalhadas?|dormit[óo]rios?)\s*[:\-]?\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:quartos?|dormit[óo]rios?)", re.IGNORECASE), _contagem),
    ("casas_banho", re.compile(r"(?:casas?\s*de\s*banho|wc)\s*[:\-]?\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:casas?\s*de\s*banho|wc)\b", re.IGNORECASE), _contagem),
    ("ano_construcao", re.compile(r"(?:ano\s*de\s*constru[çc][ãa]o|constru[íi]d[oa]\s*em)\s*[:\-]?\s*((?:17|18|19|20)\d{2})", re.IGNORECASE), _ano),
    ("certificacao_energetica", re.compile(r"(?:certificado|classe|certifica[çc][ãa]o)\s*energ[ée]tic[ao]\s*[:\-]?\s*([A-G][+\-]?)(?![A-Za-z])", re.IGNORECASE), _classe_energetica),
    ("referencia", re.compile(r"\brefer[êe]ncia\s*(?:do\s*(?:im[óo]vel|an[úu]ncio))?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/.]{2,30})", re.IGNORECASE), None),
)
_RE_TIPOLOGIA = re.compile(r"\b(T[0-9](?:\s*\+\s*[0-9])?|V[0-9](?:\s*\+\s*[0-9])?)\b")
_RE_PRECO_ROTULADO = re.compile(r"pre[çc]o\s*[:\-]?\s*(\d[\d.\s ]*(?:,\d+)?)\s*€", re.IGNORECASE)
_RE_PRIMEIRO_EURO = re.compile(r"(\d{1,3}(?:[.\s ]\d{3})+|\d{4,9})\s*€")


def texto_visivel(soup) -> str:
    """O texto da página sem scripts, estilos nem `<noscript>`."""
    copia = soup
    for etiqueta in copia.find_all(["script", "style", "noscript", "template"]):
        etiqueta.extract()
    return copia.get_text("\n", strip=True)


def extrair_texto_rotulado(texto: str, *, titulo: Optional[str] = None) -> dict:
    """Os campos que têm a etiqueta ao lado no texto visível."""
    saida: dict = {}
    for chave, padrao, validar in _PADROES_DE_TEXTO:
        achado = padrao.search(texto)
        if not achado:
            continue
        bruto = next((g for g in achado.groups() if g), None)
        valor = validar(bruto) if validar else bruto
        if valor not in (None, ""):
            saida[chave] = valor
    for fonte in (titulo or "", texto[:600]):
        achado = _RE_TIPOLOGIA.search(fonte)
        if achado:
            saida["tipologia"] = re.sub(r"\s+", "", achado.group(1))
            break
    rotulado = _RE_PRECO_ROTULADO.search(texto)
    if rotulado and preco(rotulado.group(1)):
        saida["preco"] = preco(rotulado.group(1))
    return saida


# ====================================================================
# PONTO ÚNICO
# ====================================================================
#: Ordem de confiança: o primeiro a ter o campo ganha.
ORDEM_DAS_FONTES = ("json_ld", "json_embebido", "meta", "texto")


def extrair_estruturados(soup, html: str = "") -> dict:
    """Os campos do anúncio lidos sem classes CSS; nunca levanta.

    Cada fonte falha sozinha: um JSON-LD partido não impede o `__NEXT_DATA__`.
    Os campos vêm com as chaves que o resto do scraper já usa.
    """
    if soup is None:
        return {}
    fontes: dict[str, dict] = {}
    for nome, leitor in (
        ("json_ld", extrair_json_ld),
        ("json_embebido", extrair_json_embebido),
        ("meta", extrair_meta),
    ):
        try:
            fontes[nome] = leitor(soup)
        except Exception as exc:
            logger.warning("[SCRAPER-EST] Fonte %s falhou: %s", nome, type(exc).__name__)
            fontes[nome] = {}
    topo_da_pagina = ""
    try:
        titulo = fontes["json_ld"].get("titulo") or fontes["json_embebido"].get("titulo") or fontes["meta"].get("titulo")
        # `texto_visivel` extrai nós: trabalha numa CÓPIA para não mexer na
        # sopa do chamador (que ainda vai ser lida pelos parsers por portal).
        texto = texto_visivel(BeautifulSoup(str(soup), "html.parser"))
        topo_da_pagina = texto[:6000]
        fontes["texto"] = extrair_texto_rotulado(texto, titulo=titulo)
    except Exception as exc:
        logger.warning("[SCRAPER-EST] Texto rotulado falhou: %s", type(exc).__name__)
        fontes["texto"] = {}

    saida: dict = {}
    for nome in ORDEM_DAS_FONTES:
        for chave, valor in fontes.get(nome, {}).items():
            if valor not in (None, "") and chave not in saida:
                saida[chave] = valor

    # Último recurso para o preço, sem etiqueta: o primeiro valor em euros do
    # topo da página. Só se NENHUMA fonte estruturada o tem.
    if "preco" not in saida:
        for achado in _RE_PRIMEIRO_EURO.finditer(topo_da_pagina):
            valor = preco(achado.group(1))
            if valor:
                saida["preco"] = valor
                saida["_preco_sem_etiqueta"] = True
                break
    return saida


def completar(principal: dict, adicional: dict) -> dict:
    """Preenche o que falta em `principal` com `adicional`; o parser do portal ganha.

    «Falta» é ausente, `None`, vazio ou `N/A` (o marcador que a IA devolve).
    Devolve o próprio `principal` (alterado) e regista as chaves acrescentadas
    em `_completado_por_estruturados`, para o log e para os testes.
    """
    acrescentadas = []
    for chave, valor in (adicional or {}).items():
        if chave.startswith("_") or valor in (None, ""):
            continue
        actual = principal.get(chave)
        if actual in (None, "", "N/A", 0) and not (actual == 0 and valor == 0):
            principal[chave] = valor
            acrescentadas.append(chave)
    if acrescentadas:
        principal["_completado_por_estruturados"] = sorted(acrescentadas)
    return principal


# ====================================================================
# PÁGINA DE BLOQUEIO ANTI-BOT (HTTP 200 com um desafio em vez do anúncio)
# ====================================================================
_SINAIS_DE_BLOQUEIO = (
    "just a moment", "attention required", "access denied", "pardon our interruption",
    "captcha-delivery.com", "px-captcha", "cf-challenge", "challenge-platform",
    "please verify you are a human", "verifique que é humano", "são necessárias verificações",
)


def e_pagina_de_bloqueio(html: Optional[str]) -> bool:
    """Um desafio anti-bot servido com 200, em vez do anúncio.

    Conta como bloqueio quando há um sinal conhecido E a página é pequena ou
    sem `<h1>`: um anúncio verdadeiro pode mencionar «captcha» num script, mas
    tem título e é grande.
    """
    if not html:
        return False
    amostra = html[:200_000].lower()
    if not any(sinal in amostra for sinal in _SINAIS_DE_BLOQUEIO):
        return False
    return len(html) < 60_000 or "<h1" not in amostra


#: Os campos cuja presença dá a um scrape o direito de ir para a cache.
CAMPOS_MINIMOS_PARA_CACHE = ("titulo", "preco", "area", "localizacao", "tipologia", "quartos")


def tem_dados_para_guardar(resultado: dict) -> bool:
    """Um resultado vazio nunca vai para a cache.

    Uma página lida mal (DOM novo, desafio anti-bot) ficava em cache sete dias:
    o consultor corrigia o portal… e continuava a receber o vazio.
    """
    return any((resultado or {}).get(c) not in (None, "", "N/A") for c in CAMPOS_MINIMOS_PARA_CACHE)
