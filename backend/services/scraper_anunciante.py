"""Quem anuncia o imóvel: que página seguir, e o que mandar à IA.

Módulo PURO — não faz rede, não toca na base de dados, não lê o relógio.
Só decide. O `scraper.py` executa.

O QUE CORREU MAL (LOTE 10)
==========================
O motor tinha deep scraping e **não conseguia alcançar o Idealista**, que é
o portal que o cliente mais usa. `_find_agency_links` começa por descartar
tudo o que seja do mesmo domínio::

    if current_domain in link_domain or link_domain in current_domain:
        continue

No Idealista o perfil do anunciante **É** uma página do Idealista
(`idealista.pt/pro/<agencia>`): o ramo certo era eliminado na primeira
linha, antes de qualquer reconhecimento. Não é um link que falte na lista
— é o único link que havia a ser deitado fora.

E a lista a que o reconhecimento recorria (`AGENCY_DOMAINS`) é uma lista de
ADMISSÃO escrita à mão: uma agência que não esteja lá nunca é seguida, e
isso não produz erro nenhum — devolve uma visita sem contacto, que se lê
como «o anúncio não tinha o comercial». É a forma do `INACTIVE_STATUSES`
(D-6) e da lista de `source` dos pedidos do Portal: o que decide é uma
enumeração que ninguém mantém.

Havia AINDA um segundo motor, completo e sem chamador
-----------------------------------------------------
`_deep_link_contacts` (73 linhas, a seguir links e a extrair nome, telefone
e email do anunciante) tinha UMA ocorrência no ficheiro: o seu próprio
`def`. E estava partido de três maneiras — chamava `self._get_next_proxy()`
e `self._proxies`, que não existem na classe, e usava `httpx`, que só é
importado quando o `curl_cffi` FALTA. Tudo dentro de um
`except Exception: continue`, logo revivê-lo devolvia `{}` sem um erro no
log. Mecanismo documentado que não existe — o `_get_client_base_path` da
D-19 com outro nome. Foi APAGADO, não religado: código adormecido é um
convite a religá-lo.

A ROTA É O SINAL, O DOMÍNIO É O RECURSO
=======================================
A pergunta «esta ligação leva ao anunciante?» responde-se primeiro pelo
CAMINHO (`/pro/`, `/agencia/`, `/imobiliaria/`, `/consultor/`), que é o que
um portal usa para o perfil de quem anuncia, e só depois pelo domínio
conhecido. Assim o Idealista entra pelo caminho e a Remax continua a entrar
pelo domínio, sem que uma agência nova precise de entrar numa lista.

UM SALTO, E SÓ UM
=================
`alvos_do_anunciante` devolve a lista ORDENADA, e quem executa segue **um**
alvo. Dois saltos dobram o risco de bloqueio por um ganho que não existe
(o contacto está no perfil, não a dois cliques dele) e multiplicam o tempo
de um trabalho de fundo que o cliente está a ver em «a ler o anúncio».
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

#: Segmentos de caminho que um portal usa para a página de quem anuncia.
#: É isto que alcança o Idealista (`/pro/...`), onde o anunciante vive no
#: MESMO domínio do anúncio.
ROTAS_DO_ANUNCIANTE = (
    "/pro/",
    "/pro-",
    "/agencia",
    "/agencias",
    "/imobiliaria",
    "/imobiliarias",
    "/anunciante",
    "/consultor",
    "/consultores",
    "/mediador",
    "/agente",
    "/agent/",
    "/agents/",
    "/broker",
    "/equipa/",
    "/team/",
    "/profissional",
)

#: Textos de ligação que anunciam o perfil de quem publica. Serve o caso em
#: que a rota não diz nada (`/p/12345`) mas o rótulo diz tudo.
TEXTOS_DO_ANUNCIANTE = (
    # Perfil do anunciante DENTRO do portal.
    "ver todos os imóveis",
    "todos os imóveis desta",
    "imóveis do anunciante",
    "perfil do anunciante",
    "ficha da agência",
    "ver anunciante",
    "sobre o anunciante",
    "mais sobre a agência",
    "página da agência",
    "contactar agência",
    "contactar anunciante",
    # Saída para o site PRÓPRIO da agência — é a forma com que os
    # agregadores rotulam a ligação externa, e é o alvo de maior valor
    # (é lá que está o directo do consultor, e não o formulário do
    # portal). Herdados do `AGENCY_LINK_TEXTS`, que era a lista do
    # `_find_agency_links`.
    "ver no site",
    "site do anunciante",
    "link externo",
    "visitar site",
    "ir para o site",
    "ver original",
    "contacto direto",
    "contacto directo",
)

#: O que o `AGENCY_LINK_TEXTS` reconhecia e aqui se RECUSA, de propósito.
#:
#: Ao extrair a decisão para este módulo deixei cair nove dos treze
#: textos do original — e o meu próprio inventário de constantes órfãs é
#: que o denunciou. Quatro foram repostos acima; estes cinco ficam FORA
#: porque são rótulos de navegação genérica que qualquer página tem
#: («Ver detalhes» aparece em cada cartão de uma lista de resultados), e
#: com UM salto por anúncio um alvo errado custa o mesmo que o certo e
#: não traz nada. É a mesma razão do `ROTAS_RECUSADAS`.
#:
#: Está escrito em vez de simplesmente ausente para que a diferença seja
#: uma DECISÃO e não um esquecimento — a próxima pessoa que quiser
#: alargar o reconhecimento tem aqui o que já foi pesado.
TEXTOS_RECUSADOS_DE_PROPOSITO = (
    "ver anúncio",
    "ver detalhes",
    "mais informação",
    "website",
    "ver mais",
)

#: Caminhos que NUNCA são o anunciante, por muito que casem com o resto.
#: Sem isto, `/pro/` apanhava `/pro/termos-e-condicoes` e o salto era gasto
#: numa página legal — um alvo errado custa o mesmo que o certo e não traz
#: nada.
ROTAS_RECUSADAS = (
    "/termos",
    "/privacidade",
    "/cookies",
    "/ajuda",
    "/apoio",
    "/login",
    "/registo",
    "/favoritos",
    "/alertas",
    "/publicar",
    "/anunciar",
    "/preco",
    "/precos",
    "/blog",
    "/noticias",
    "/carreiras",
    "/recrutamento",
)

#: Esquemas que se seguem. Um `tel:`/`mailto:`/`javascript:` não é uma
#: página, e um `data:` é conteúdo a fingir que é um endereço.
ESQUEMAS_ACEITES = ("http", "https")

#: Quantos candidatos se consideram antes de escolher. Não é quantos se
#: SEGUEM (isso é um, e decide-o quem executa): é o tamanho da lista que
#: se pondera, para um anúncio com cinquenta ligações não produzir uma
#: ordenação de cinquenta elementos que ninguém vai ler.
MAXIMO_DE_ALVOS_CONSIDERADOS = 5

#: Uma ligação DECLARADA pelo parser do portal vence tudo. O
#: `_parse_idealista` gasta seis estratégias (selectores, JSON-LD,
#: atributos `data-*`, o texto da descrição) a encontrar o site da
#: agência e grava-o em `agency_link` — e o navegador nunca o lia: o
#: Cenário 1 varria os `<a>` da página outra vez, com menos informação do
#: que a que já estava em mãos. O sinal existia e quem navega não o
#: consultava, que é a forma do `under_35` lido por três componentes e
#: escrito por nenhum.
PESO_DO_DECLARADO = 200

PESO_DA_ROTA = 100
PESO_DO_DOMINIO_CONHECIDO = 50
PESO_DO_TEXTO = 25
#: O mesmo domínio do anúncio vale MENOS do que sair para a agência (lá o
#: telefone costuma ser o directo do consultor), mas não é descartado —
#: era o descarte que fechava o Idealista.
PESO_DE_SAIR_DO_DOMINIO = 10


@dataclass(frozen=True)
class AlvoDoAnunciante:
    """Uma página candidata a ter o contacto de quem anuncia."""

    url: str
    peso: int
    motivo: str
    #: `True` quando o alvo está no domínio do próprio anúncio (Idealista).
    interno: bool


def _caminho(url: str) -> str:
    try:
        partes = urlparse(url)
    except ValueError:
        return ""
    return (partes.path or "").lower()


def _dominio(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""


def _dominio_base(dominio: str) -> str:
    """`www.idealista.pt` e `pro.idealista.pt` → `idealista.pt`.

    Comparar o `netloc` cru fazia `pro.idealista.pt` contar como «sai do
    portal» e ganhar o bónus que existe para a página da AGÊNCIA, onde o
    telefone é o directo do consultor. O perfil do anunciante num
    subdomínio do próprio portal é a mesma casa.
    """
    partes = [parte for parte in (dominio or "").split(".") if parte]
    if len(partes) <= 2:
        return ".".join(partes)
    return ".".join(partes[-2:])


def _e_endereco_seguivel(href: str) -> bool:
    bruto = (href or "").strip()
    if not bruto or bruto.startswith("#"):
        return False
    try:
        esquema = (urlparse(bruto).scheme or "").lower()
    except ValueError:
        return False
    # Um href relativo não tem esquema e é legítimo: resolve-se contra a
    # origem. O que se recusa é um esquema PRESENTE e não navegável.
    return esquema == "" or esquema in ESQUEMAS_ACEITES


def _tem_rota_recusada(caminho: str) -> bool:
    return any(recusada in caminho for recusada in ROTAS_RECUSADAS)


def _rota_do_anunciante(caminho: str) -> str:
    for rota in ROTAS_DO_ANUNCIANTE:
        if rota in caminho:
            return rota
    return ""


def _texto_do_anunciante(texto: str) -> str:
    limpo = re.sub(r"\s+", " ", (texto or "")).strip().lower()
    if not limpo:
        return ""
    for marca in TEXTOS_DO_ANUNCIANTE:
        if marca in limpo:
            return marca
    return ""


def _dominio_conhecido(dominio: str, dominios_de_agencia) -> str:
    for marca in dominios_de_agencia or ():
        alvo = str(marca).strip().lower()
        if alvo and alvo in dominio:
            return alvo
    return ""


def alvos_do_anunciante(
    ligacoes,
    *,
    url_de_origem: str,
    dominios_de_agencia=(),
    declarados=(),
    maximo: int = MAXIMO_DE_ALVOS_CONSIDERADOS,
):
    """As páginas candidatas a ter o contacto do anunciante, ordenadas.

    `ligacoes` é uma sequência de pares `(href, texto)` — ou de dicionários
    com essas chaves —, tal como saem de um `<a href>`. Fica assim porque a
    decisão é sobre DADOS e não sobre uma `BeautifulSoup`: é o que permite
    testá-la sem HTML e sem rede.

    Três sinais, somados, nunca exclusivos: a ROTA (o que alcança o
    Idealista), o DOMÍNIO conhecido (o que já funcionava) e o TEXTO da
    ligação. Um alvo precisa de pelo menos um dos três — sem nenhum, seguir
    a ligação é seguir uma ligação qualquer.
    """
    origem = str(url_de_origem or "")
    dominio_de_origem = _dominio(origem)
    vistos: set[str] = set()
    alvos: list[AlvoDoAnunciante] = []

    # Os declarados entram na MESMA fila e passam pelas MESMAS recusas
    # (esquema, página legal, ser a própria origem): uma ligação que o
    # parser declarou continua a ser uma ligação, e dar-lhe um caminho
    # paralelo sem verificações era abrir uma segunda porta para o lado
    # de dentro. O que ganham é peso, não dispensa.
    candidatas = [(href, "página da agência", True) for href in (declarados or ())]
    for ligacao in ligacoes or ():
        if isinstance(ligacao, dict):
            href = ligacao.get("href") or ligacao.get("url") or ""
            texto = ligacao.get("texto") or ligacao.get("text") or ""
        else:
            try:
                href, texto = ligacao
            except (TypeError, ValueError):
                continue
        candidatas.append((href, texto, False))

    for href, texto, declarado in candidatas:
        if not _e_endereco_seguivel(href):
            continue

        absoluto = urljoin(origem, str(href).strip()) if origem else str(href).strip()
        if not absoluto.lower().startswith(("http://", "https://")):
            continue
        # A âncora não muda a página; sem a cortar, o mesmo perfil entra
        # cinco vezes e gasta o único salto que temos.
        absoluto = absoluto.split("#", 1)[0]
        if absoluto in vistos:
            continue

        caminho = _caminho(absoluto)
        if _tem_rota_recusada(caminho):
            continue

        dominio = _dominio(absoluto)
        # A página do próprio anúncio nunca é o alvo.
        if absoluto.split("#", 1)[0].rstrip("/") == origem.split("#", 1)[0].rstrip("/"):
            continue

        rota = _rota_do_anunciante(caminho)
        conhecido = _dominio_conhecido(dominio, dominios_de_agencia)
        marca = _texto_do_anunciante(texto)
        if not declarado and not rota and not conhecido and not marca:
            continue

        base_de_origem = _dominio_base(dominio_de_origem)
        interno = bool(base_de_origem and _dominio_base(dominio) == base_de_origem)

        peso = 0
        motivos = []
        if declarado:
            peso += PESO_DO_DECLARADO
            motivos.append("declarado pelo parser")
        if rota:
            peso += PESO_DA_ROTA
            motivos.append(f"rota {rota}")
        if conhecido:
            peso += PESO_DO_DOMINIO_CONHECIDO
            motivos.append(f"domínio {conhecido}")
        if marca:
            peso += PESO_DO_TEXTO
            motivos.append(f"texto «{marca}»")
        if not interno:
            peso += PESO_DE_SAIR_DO_DOMINIO
            motivos.append("sai do portal")

        vistos.add(absoluto)
        alvos.append(
            AlvoDoAnunciante(
                url=absoluto,
                peso=peso,
                motivo=", ".join(motivos),
                interno=interno,
            )
        )

    # `-peso` primeiro e o URL como desempate: duas candidaturas com o mesmo
    # peso têm de sair sempre na mesma ordem, senão o alvo seguido depende
    # da ordem do HTML e o mesmo anúncio dá resultados diferentes.
    alvos.sort(key=lambda alvo: (-alvo.peso, alvo.url))
    return alvos[: max(0, int(maximo))]


# ====================================================================
# O CONTEXTO QUE VAI À IA
# ====================================================================
# DUAS PÁGINAS, UMA CHAMADA. As alternativas foram pesadas:
#
#   (a) duas chamadas independentes — paga-se duas vezes e, pior, a
#       segunda página sozinha não tem o imóvel: o modelo não consegue
#       decidir se o 21X que lá está é o directo do consultor que vende
#       ESTE imóvel ou a central da agência. A pergunta que queremos
#       responder é um CRUZAMENTO, logo não se parte em duas.
#
#   (b) concatenar os dois HTML — o orçamento de 15k caracteres é gasto
#       pela página do anunciante (que é quase toda navegação e listas de
#       imóveis) e o anúncio, que é a autoridade do preço e da área, fica
#       truncado. Um upgrade de contactos que piorasse o preço seria um
#       mau negócio.
#
# Fica (c): UMA chamada, com os dois blocos ROTULADOS e cada um com
# orçamento PRÓPRIO. O rótulo não é cosmética — é o que permite ao prompt
# dizer «os contactos só podem vir do bloco do anunciante» e ao modelo
# saber de onde veio cada número. E o orçamento próprio é o que garante
# que a segunda página nunca pode roubar espaço à primeira.

#: O anúncio é a autoridade do imóvel e leva a maior fatia.
ORCAMENTO_DO_ANUNCIO = 11000
#: A página do anunciante só precisa de dar nome, telefone e email.
ORCAMENTO_DO_ANUNCIANTE = 5000

ROTULO_DO_ANUNCIO = "PÁGINA DO ANÚNCIO (origem dos dados do imóvel)"
ROTULO_DO_ANUNCIANTE = "PÁGINA DO ANUNCIANTE (seguida a partir do anúncio)"


@dataclass(frozen=True)
class PaginaDoContexto:
    """Um bloco de texto já limpo, com a sua etiqueta e o seu orçamento."""

    rotulo: str
    url: str
    texto: str
    orcamento: int


def pagina_do_anuncio(texto: str, url: str) -> PaginaDoContexto:
    return PaginaDoContexto(
        rotulo=ROTULO_DO_ANUNCIO,
        url=str(url or ""),
        texto=str(texto or ""),
        orcamento=ORCAMENTO_DO_ANUNCIO,
    )


def pagina_do_anunciante(texto: str, url: str) -> PaginaDoContexto:
    return PaginaDoContexto(
        rotulo=ROTULO_DO_ANUNCIANTE,
        url=str(url or ""),
        texto=str(texto or ""),
        orcamento=ORCAMENTO_DO_ANUNCIANTE,
    )


def contexto_para_a_ia(paginas) -> str:
    """Os blocos rotulados e truncados, prontos para o prompt.

    Cada página é cortada no SEU orçamento, nunca no total: é isso que
    impede a página do anunciante de empurrar o anúncio para fora da
    janela. Uma página sem texto não produz bloco — um rótulo com nada
    debaixo convida o modelo a inventar o que falta.
    """
    blocos = []
    for pagina in paginas or ():
        texto = (getattr(pagina, "texto", "") or "").strip()
        if not texto:
            continue
        limite = max(0, int(getattr(pagina, "orcamento", 0) or 0))
        recortado = texto[:limite] if limite else texto
        if not recortado:
            continue
        url = getattr(pagina, "url", "") or ""
        cabecalho = f"=== {getattr(pagina, 'rotulo', '')} ==="
        if url:
            cabecalho += f"\nURL: {url}"
        blocos.append(f"{cabecalho}\n{recortado}")
    return "\n\n".join(blocos)


def tem_bloco_do_anunciante(contexto: str) -> bool:
    """Se o contexto inclui a segunda página. O prompt muda por causa disto."""
    return ROTULO_DO_ANUNCIANTE in (contexto or "")


# ====================================================================
# O PROMPT — UM, PARA OS DOIS MOTORES
# ====================================================================
# Havia DOIS prompts escritos à mão: um no `_extract_with_gemini` e outro
# no `_extract_with_openai`, com listas de campos DIFERENTES (o do OpenAI
# vinha comprimido e sem as instruções de validação). Qual corre depende
# do que o administrador configurou no painel, logo um upgrade feito num
# deles é um upgrade que metade dos clientes não recebe — e nada dá erro.
# É a forma de «os dois mapas de campos da IA têm de concordar» e dos dois
# mapeadores da D-23. Hoje é UM, e a divergência deixou de ser possível.

_INSTRUCOES_COMUNS = """IMPORTANTE:
1. Responde APENAS com o JSON, sem explicações e sem markdown.
2. Extrai o máximo de informação possível.
3. Para preços, remove símbolos e converte para número.
4. Para áreas, extrai apenas o número.
5. NÃO INVENTES CONTACTOS. Um telefone ou email que não esteja no
   conteúdo é `null`. Um número errado faz o consultor ligar a quem não
   tem nada a ver com o imóvel — é pior do que não haver número.
6. Distingue o COMERCIAL da AGÊNCIA: um nome de pessoa vai para
   `agente_nome`, um nome de empresa vai para `agencia_nome`. Nunca
   ponhas o nome da agência em `agente_nome`.
7. Um telemóvel português começa por 9 (91/92/93/96) e um fixo por 2. Se
   o que estiver junto do contacto for um preço, uma área ou uma
   referência, é `null`."""

#: As instruções do cruzamento SÓ entram quando há segundo bloco. Um
#: parágrafo a falar de uma página que não foi enviada convida o modelo a
#: inventá-la — é a mesma regra do rótulo com nada debaixo.
_INSTRUCOES_DO_CRUZAMENTO = """
CRUZAMENTO DAS DUAS PÁGINAS (o conteúdo vem em blocos rotulados):
8. Os dados do IMÓVEL (preço, área, tipologia, localização, estado) saem
   do bloco «PÁGINA DO ANÚNCIO». É esse o anúncio deste imóvel.
9. Os CONTACTOS podem sair de qualquer bloco, mas quando os dois
   indicarem contactos DIFERENTES vence o bloco «PÁGINA DO ANUNCIANTE»:
   é a página de quem publica, e é lá que está o directo do comercial.
10. A página do anunciante lista OUTROS imóveis dele. Ignora-os: o imóvel
   a extrair é o do primeiro bloco, e nenhum preço ou área pode vir do
   segundo."""

_CAMPOS_PEDIDOS = """DADOS DO IMÓVEL:
- titulo: título/nome completo do imóvel
- preco: preço em número (sem €, sem pontos de milhar)
- preco_m2: preço por m² se disponível
- localizacao: localização completa (rua, freguesia, concelho, distrito)
- codigo_postal: código postal se visível
- tipologia: tipo (T0, T1, T2, T3, T4, T5+, moradia V1-V5+, terreno, loja, armazém)
- area: área útil em m² (apenas número)
- area_bruta: área bruta em m² se disponível
- area_terreno: área do terreno em m²
- quartos: número de quartos
- suites: número de suites
- casas_banho: número de casas de banho
- garagem: número de lugares de garagem
- piso: andar/piso do imóvel
- elevador: true/false se tem elevador
- varanda: true/false se tem varanda/terraço
- vista: tipo de vista (mar, rio, cidade, jardim)

CARACTERÍSTICAS:
- descricao: descrição do imóvel (texto completo)
- caracteristicas: lista de características (piscina, ar condicionado, lareira, etc)
- certificacao_energetica: certificado energético (A+, A, B, B-, C, D, E, F, G)
- ano_construcao: ano de construção
- estado: estado do imóvel (novo, usado, remodelado, para renovar, em construção)
- orientacao_solar: orientação (norte, sul, este, oeste)
- condominio: valor do condomínio mensal se aplicável

CONTACTO (PRIORIDADE MÁXIMA — é por aqui que se marca a visita):
- agente_nome: nome PRÓPRIO do comercial/consultor responsável por este imóvel
- agente_telefone: telefone DIRECTO do comercial (formato +351 XXX XXX XXX)
- agente_email: email do comercial
- agencia_nome: nome da agência/imobiliária que anuncia
- agencia_telefone: telefone geral/central da agência
- referencia: código de referência do anúncio

LINKS:
- foto_principal: URL da foto principal
- url_planta: URL da planta do imóvel se disponível
- url_video: URL do vídeo se disponível"""


def prompt_da_extraccao(contexto: str, *, url: str) -> str:
    """O prompt da extracção, igual para o Gemini e para o OpenAI."""
    cruzamento = _INSTRUCOES_DO_CRUZAMENTO if tem_bloco_do_anunciante(contexto) else ""
    return (
        "Analisa este conteúdo de uma página imobiliária portuguesa e "
        "extrai TODOS os dados disponíveis em formato JSON estrito.\n\n"
        f"URL: {url}\n\n"
        "Extrai os seguintes campos (usa null se não encontrares):\n\n"
        f"{_CAMPOS_PEDIDOS}\n\n"
        f"{_INSTRUCOES_COMUNS}{cruzamento}\n\n"
        f"Conteúdo:\n{contexto}"
    )


# ====================================================================
# NORMALIZAR UM TELEFONE PORTUGUÊS
# ====================================================================
# Um telefone que não é um telefone é PIOR do que nenhum: o consultor
# liga, fala com quem não tem nada a ver com o imóvel, e o ecrã continua a
# dizer que aquele é o contacto. Por isso isto RECUSA em vez de adivinhar.

_SO_DIGITOS = re.compile(r"\D+")
#: Telemóvel português: 9 seguido de 1/2/3/6. Fixo: 2 seguido de 1–9.
_TELEFONE_PT = re.compile(r"^(9[1236]\d{7}|2[1-9]\d{7})$")


def telefone_pt(valor) -> str | None:
    """`+351 912 345 678` → `912345678`. O que não for válido dá `None`.

    O indicativo só se retira quando o que SOBRA é um número português
    válido. Cortar à cega transformava os primeiros dígitos de um número
    estrangeiro num português plausível — e um número plausível é
    precisamente o que ninguém vai verificar antes de ligar.
    """
    if valor is None or isinstance(valor, bool):
        return None
    bruto = str(valor).strip()
    if not bruto:
        return None
    digitos = _SO_DIGITOS.sub("", bruto)
    if not digitos:
        return None
    if _TELEFONE_PT.match(digitos):
        return digitos
    for indicativo in ("00351", "351"):
        if digitos.startswith(indicativo):
            resto = digitos[len(indicativo):]
            if _TELEFONE_PT.match(resto):
                return resto
    return None


__all__ = [
    "AlvoDoAnunciante",
    "MAXIMO_DE_ALVOS_CONSIDERADOS",
    "PESO_DO_DECLARADO",
    "ESQUEMAS_ACEITES",
    "ORCAMENTO_DO_ANUNCIANTE",
    "ORCAMENTO_DO_ANUNCIO",
    "PaginaDoContexto",
    "ROTAS_DO_ANUNCIANTE",
    "ROTAS_RECUSADAS",
    "ROTULO_DO_ANUNCIANTE",
    "ROTULO_DO_ANUNCIO",
    "TEXTOS_DO_ANUNCIANTE",
    "TEXTOS_RECUSADOS_DE_PROPOSITO",
    "alvos_do_anunciante",
    "contexto_para_a_ia",
    "pagina_do_anuncio",
    "prompt_da_extraccao",
    "pagina_do_anunciante",
    "telefone_pt",
    "tem_bloco_do_anunciante",
]
