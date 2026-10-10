"""
====================================================================
REDES (GRUPOS EMPRESARIAIS) — isolamento multi-tenant
====================================================================
Ponto ÚNICO de resolução do âmbito de dados de um utilizador.

O MODELO
  A rede vive na EMPRESA (`companies.network_id`). Empresas com a mesma
  rede partilham visibilidade sem permissões extra (Power + Precision);
  empresas em redes diferentes estão em isolamento absoluto (Domus).
  Uma empresa SEM rede configurada é uma ilha de uma só
  (`rede_implicita`) — omissão segura: uma empresa criada hoje nasce
  isolada. Se caísse na rede de omissão, veria a pilha inteira do grupo
  incumbente, que é exactamente a fuga que isto fecha.

  O âmbito é do UTILIZADOR, não da empresa activa: a empresa activa é
  uma preferência de VISTA (o `company_id` das listagens), a rede é a
  fronteira de SEGURANÇA. Quem trabalha em duas redes vê as duas.

A REDE DE OMISSÃO (`TENANT_DEFAULT_NETWORK_ID`)
  Antes desta mudança nenhum documento era carimbado — `process_create`
  não escrevia sequer `company_id`. Essa pilha existente não tem dono
  legível, e escondê-la de toda a gente no dia do deploy seria partir os
  dados existentes. A variável de ambiente diz a que rede ela pertence:
  em produção, o grupo incumbente. Quem está nessa rede continua a
  ver tudo o que via; quem está noutra (a ilha nova) não vê nada dela.

  Com a variável POR DEFINIR (dev, CI), os documentos por carimbar são
  visíveis a todos — o comportamento de hoje, para não esvaziar as
  listagens de desenvolvimento nem a bateria — e fica um aviso no log.
  Nunca em silêncio.

  Um documento só conta como "por carimbar" quando NÃO TEM MARCA
  NENHUMA: nem `network_id`, nem `company_id`, nem `company`, nem
  `company_name`. Olhar só para o `network_id` deixaria a fuga entrar
  pela cláusula que existe para a evitar — um processo da Domus criado
  entre o carimbo na escrita e a migração tem empresa mas ainda não tem
  rede, e passaria a ser visível ao grupo incumbente.

NUNCA reconstruir esta cadeia em linha numa listagem. Foi tê-la
duplicada que produziu o incidente da conta de envio (2026-09-21); há
uma guarda sobre o código-fonte em `test_tenant_network_isolation.py`.
====================================================================
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from database import db

logger = logging.getLogger(__name__)

# Variável de ambiente (NUNCA hardcoded: dev e produção têm redes distintas).
TENANT_DEFAULT_NETWORK_ENV = "TENANT_DEFAULT_NETWORK_ID"

# Campo canónico do carimbo nos documentos de negócio.
CAMPO_REDE = "network_id"

# Onde a empresa pode estar escrita num documento (o histórico usa os três).
CAMPOS_EMPRESA: tuple[str, ...] = ("company_id", "company", "company_name")

# Valores que significam "sem empresa" — `"default"` é o sentinel que o
# frontend envia quando o utilizador não tem associações (ver `auth.py`).
VALORES_SEM_EMPRESA: tuple[Any, ...] = (None, "", "default")

# Condição que não casa com documento nenhum. É o que um âmbito fechado
# sem rede nenhuma devolve: `None` significaria "sem filtro" e reabria a
# fuga inteira em silêncio.
CONDICAO_IMPOSSIVEL: dict = {CAMPO_REDE: {"$in": []}}

#: As redes CONVIDADAS num processo partilhado (D-25). Vive **só** no
#: documento de processo e **nunca** se confunde com o `network_id`, que é
#: o carimbo de PROPRIEDADE e é permanente: uma partilha acrescenta quem
#: vê, não muda de quem é. Lista, porque um processo pode ser partilhado
#: com mais do que uma rede.
CAMPO_REDES_PARCEIRAS = "partner_network_ids"

#: Todos os campos onde o carimbo pode viver. Uma PROJECÇÃO que os
#: deixe de fora faz a verificação de posse ver um documento sem marca —
#: e "sem marca" é a tolerância do legado, logo a guarda abre em vez de
#: fechar. É a família da lição do `get_file_content`: inspeccionar uma
#: coisa e decidir sobre outra é a forma discreta de a parede não valer
#: nada. Qualquer `find_one` que alimente uma verificação de posse tem de
#: incluir a `PROJECCAO_DO_CARIMBO`.
CAMPOS_DO_CARIMBO: tuple[str, ...] = (CAMPO_REDE, *CAMPOS_EMPRESA)
PROJECCAO_DO_CARIMBO: dict = {campo: 1 for campo in CAMPOS_DO_CARIMBO}

_aviso_de_omissao_dado = False


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def rede_de_omissao() -> Optional[str]:
    """Rede a que pertencem os documentos sem carimbo, ou ``None``."""
    return _texto(os.getenv(TENANT_DEFAULT_NETWORK_ENV)) or None


def rede_implicita(company_id: Any) -> str:
    """Rede de uma empresa sem grupo configurado: uma ilha de uma só."""
    return f"rede:{_texto(company_id)}"


def resolve_network_id(empresa: Optional[dict], *, company_id: Any = None) -> Optional[str]:
    """`network_id` de uma empresa, ou a sua ilha implícita."""
    if empresa:
        explicita = _texto(empresa.get(CAMPO_REDE))
        if explicita:
            return explicita
        identificador = _texto(empresa.get("id")) or _texto(company_id)
    else:
        identificador = _texto(company_id)

    return rede_implicita(identificador) if identificador else None


@dataclass(frozen=True)
class TenantScope:
    """O que um utilizador pode ver, em termos de rede e de empresa."""

    network_ids: tuple[str, ...] = ()
    company_ids: tuple[str, ...] = ()
    company_names: tuple[str, ...] = ()
    # Os documentos por carimbar entram no âmbito deste utilizador?
    inclui_rede_de_omissao: bool = False
    # O Master (único perfil global) não tem fronteira: vê todas as redes.
    # É um campo EXPLÍCITO e não uma lista vazia/`None`: um âmbito sem
    # redes continua a significar «nada» (condição impossível), e só esta
    # bandeira — que só `resolve_tenant_scope` liga, e só para o Master —
    # abre a porta. Ver `services/role_scope.py`.
    sem_fronteira: bool = False


def _sem_marca_de_tenant() -> dict:
    """Documento sem NENHUMA marca de empresa ou rede (a pilha antiga).

    `{"campo": {"$in": [None, ...]}}` no Mongo casa também com o campo
    AUSENTE — é o mesmo predicado para "nulo", "vazio" e "não existe".
    """
    vazios = list(VALORES_SEM_EMPRESA)
    return {
        "$and": [
            {CAMPO_REDE: {"$in": vazios}},
            *({campo: {"$in": vazios}} for campo in CAMPOS_EMPRESA),
        ]
    }


#: «Sem fronteira»: casa com tudo. Só o Master a recebe, e é uma constante
#: com nome para que uma pesquisa por `{}` à mão numa guarda continue a ser
#: sinal de defeito, enquanto ESTA é a excepção declarada.
CONDICAO_SEM_FRONTEIRA: dict = {}


def build_network_scope_condition(scope: TenantScope) -> dict:
    """Condição Mongo que restringe uma listagem ao âmbito do utilizador.

    Pura e testável: não toca na base de dados nem no ambiente.
    """
    if scope.sem_fronteira:
        return dict(CONDICAO_SEM_FRONTEIRA)

    ramos: list[dict] = []

    if scope.network_ids:
        ramos.append({CAMPO_REDE: {"$in": list(scope.network_ids)}})

    # O histórico grava a empresa ora por id ora por nome; aceitamos as
    # duas formas em qualquer um dos três campos.
    empresas = list(dict.fromkeys([*scope.company_ids, *scope.company_names]))
    if empresas:
        ramos.extend({campo: {"$in": empresas}} for campo in CAMPOS_EMPRESA)

    if scope.inclui_rede_de_omissao:
        ramos.append(_sem_marca_de_tenant())

    if not ramos:
        return CONDICAO_IMPOSSIVEL

    return {"$or": ramos}


def build_process_scope_condition(scope: TenantScope) -> dict:
    """Âmbito de PROCESSOS: o do dono **mais** o das redes convidadas (D-25).

    PORQUE É QUE ISTO É UMA FUNÇÃO SEPARADA E NÃO UM RAMO NO GENÉRICO
    ================================================================
    `CAMPO_REDES_PARCEIRAS` existe **só** no documento de processo. Pôr o
    ramo no `build_network_scope_condition` fá-lo-ia viajar para as 33
    superfícies que o usam — clientes, tarefas, imóveis, emails,
    calendário —, onde nenhum documento tem o campo: um `$or` a mais em
    cada consulta, e uma porta aberta no dia em que alguém gravasse o
    campo noutra colecção sem pensar nisto.

    A partilha é uma propriedade do PROCESSO. Quem pergunta «que
    processos vejo?» usa esta; todo o resto continua no genérico.

    DERIVA do genérico em vez de escrever os ramos outra vez: a parte
    comum é a mesma e duas versões dela divergem na primeira mudança (é
    a nota do `build_pool_scope_condition`). A única diferença é o ramo
    que se acrescenta, e é isso que o código diz.

    **Um âmbito sem redes não ganha nada aqui.** Sem redes não há com que
    casar a lista de convidadas, e devolver o ramo com uma lista vazia
    seria `{"$in": []}` — que não casa com nada, mas transformaria a
    condição impossível num `$or` de um ramo impossível. Fica a
    impossível, que é a que se lê.
    """
    base = build_network_scope_condition(scope)

    if scope.sem_fronteira:
        return base

    redes = sorted({_texto(r) for r in scope.network_ids if _texto(r)})
    if not redes:
        return base

    ramo_da_partilha = {CAMPO_REDES_PARCEIRAS: {"$in": redes}}

    if base == CONDICAO_IMPOSSIVEL:
        return ramo_da_partilha

    ramos = list(base.get("$or") or [base])
    return {"$or": [*ramos, ramo_da_partilha]}


async def build_tenant_process_condition(user: dict) -> dict:
    """Atalho: âmbito de PROCESSOS deste utilizador, já em Mongo.

    É esta — e não o `build_tenant_condition` — que todas as superfícies
    que listam ou resolvem PROCESSOS usam. Há um inventário por AST que
    falha por OMISSÃO para uma superfície nova que use a genérica.
    """
    return build_process_scope_condition(await resolve_tenant_scope(user))


def redes_parceiras(doc: Optional[dict]) -> set[str]:
    """As redes convidadas de um processo, normalizadas."""
    valor = (doc or {}).get(CAMPO_REDES_PARCEIRAS)
    if isinstance(valor, (list, tuple, set)):
        return {_texto(v) for v in valor if _texto(v)}
    return {_texto(valor)} if _texto(valor) else set()


def processo_no_ambito(doc: Optional[dict], scope: TenantScope) -> bool:
    """Gémeo em Python do `build_process_scope_condition`.

    O dono **ou** uma rede convidada. A ordem é a do construtor, e há um
    teste de concordância que corre os dois sobre os mesmos documentos.
    """
    if documento_no_ambito(doc, scope):
        return True
    minhas = {_texto(r) for r in scope.network_ids if _texto(r)}
    return bool(minhas and (redes_parceiras(doc) & minhas))


def build_pool_scope_condition(scope: TenantScope) -> dict:
    """Âmbito de uma POOL: por carimbar é de todos, carimbado é da sua rede.

    PORQUE É QUE ISTO NÃO É O `build_network_scope_condition` (Set 2026)
    ====================================================================
    Aquele só inclui a pilha por carimbar quando o utilizador pertence à
    rede de omissão. Para processos está certo — a pilha por carimbar é
    do grupo incumbente e não de toda a gente. Para uma **Pool** está
    errado: um registo público ainda não é de ninguém, e escondê-lo de
    quem não é da rede de omissão faz com que nunca seja reivindicado.

    A regra do produto é a do *claim-based routing*:

      sem carimbo  → é da POOL, visível a TODAS as redes;
      com carimbo  → é de UMA rede, e só essa o vê.

    DERIVA do construtor normal em vez de escrever ramos próprios: duas
    condições de isolamento escritas à mão divergem na primeira mudança,
    e a que divergir não dá erro — devolve dados a mais. Aqui a única
    diferença é forçar `inclui_rede_de_omissao`, e é isso que o código
    diz.

    **Só para listagens que SÃO uma pool** (registos públicos por
    reivindicar). Uma listagem normal continua a usar o
    `build_tenant_condition`: usar esta aqui abriria a pilha por carimbar
    a toda a gente, que é a fuga que o Lote 4 fechou.
    """
    return build_network_scope_condition(
        TenantScope(
            network_ids=scope.network_ids,
            company_ids=scope.company_ids,
            company_names=scope.company_names,
            inclui_rede_de_omissao=True,
            sem_fronteira=scope.sem_fronteira,
        )
    )


async def build_tenant_pool_condition(user: dict) -> dict:
    """Atalho da Pool: âmbito do utilizador já convertido em condição."""
    return build_pool_scope_condition(await resolve_tenant_scope(user))


async def _redes_das_empresas(company_ids: Sequence[str]) -> dict[str, Optional[str]]:
    """Mapa company_id → network_id (ilha implícita quando não há grupo)."""
    identificadores = [c for c in dict.fromkeys(_texto(c) for c in company_ids) if c]
    if not identificadores:
        return {}

    encontradas: dict[str, dict] = {}
    try:
        cursor = db.companies.find(
            {"$or": [
                {"id": {"$in": identificadores}},
                {"name": {"$in": identificadores}},
            ]},
            {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
        )
        for empresa in await cursor.to_list(200):
            for chave in (_texto(empresa.get("id")), _texto(empresa.get("name"))):
                if chave:
                    encontradas[chave] = empresa
    except Exception as exc:
        # Degradação graciosa: sem a colecção de empresas cada empresa
        # vale por si (ilha). Nunca ampliar o âmbito por causa de um erro.
        logger.warning(
            "[tenant_network] Falha a ler `companies` (%s); cada empresa "
            "passa a valer como ilha própria.", exc,
        )

    return {
        cid: resolve_network_id(encontradas.get(cid), company_id=cid)
        for cid in identificadores
    }


async def resolve_tenant_scope(user: dict) -> TenantScope:
    """Âmbito de dados de um utilizador: todas as redes a que pertence."""
    from services.auth import get_user_companies
    from services.role_scope import utilizador_e_global

    if utilizador_e_global(user):
        return TenantScope(inclui_rede_de_omissao=True, sem_fronteira=True)

    user_id = _texto((user or {}).get("id") or (user or {}).get("user_id"))

    associacoes: list[dict] = []
    if user_id:
        try:
            associacoes = await get_user_companies(user_id) or []
        except Exception as exc:
            logger.warning(
                "[tenant_network] Falha a ler as empresas de %s (%s).", user_id, exc,
            )

    company_ids: list[str] = []
    company_names: list[str] = []
    for assoc in associacoes:
        cid = _texto(assoc.get("company_id"))
        nome = _texto(assoc.get("company_name"))
        if cid and cid not in VALORES_SEM_EMPRESA:
            company_ids.append(cid)
        if nome:
            company_names.append(nome)

    # Recurso para contas legadas sem UCR: `user.company` é o NOME.
    legado = _texto((user or {}).get("company"))
    if not company_ids and legado and legado not in VALORES_SEM_EMPRESA:
        company_names.append(legado)
        company_ids.append(legado)

    mapa = await _redes_das_empresas([*company_ids, *company_names])
    network_ids = [rede for rede in mapa.values() if rede]

    omissao = rede_de_omissao()
    if omissao:
        # Utilizador órfão (sem empresa nenhuma) — tipicamente contas de
        # administração antigas. Cegá-las no dia do deploy não ajuda
        # ninguém; a Atribuição Rápida passa a evitar que nasçam novas.
        if not network_ids:
            logger.info(
                "[tenant_network] Utilizador %s sem empresa associada; "
                "atribuído à rede de omissão.", user_id or "?",
            )
            network_ids.append(omissao)
        inclui_omissao = omissao in network_ids
    else:
        _avisar_omissao_por_definir()
        inclui_omissao = True

    return TenantScope(
        network_ids=tuple(dict.fromkeys(network_ids)),
        company_ids=tuple(dict.fromkeys(company_ids)),
        company_names=tuple(dict.fromkeys(company_names)),
        inclui_rede_de_omissao=inclui_omissao,
    )


def _avisar_omissao_por_definir() -> None:
    """Avisa UMA vez que os documentos por carimbar estão visíveis a todos."""
    global _aviso_de_omissao_dado
    if _aviso_de_omissao_dado:
        return
    _aviso_de_omissao_dado = True
    # Em produção isto é um defeito de configuração, não um aviso: com a
    # variável por definir a pilha por carimbar (toda a carteira antiga)
    # fica visível a utilizadores de QUALQUER rede, incluindo uma rede
    # satélite acabada de criar (Bloco A, Out 2026).
    nivel = (
        logging.ERROR
        if (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "").strip().lower()
        in {"production", "prod"}
        else logging.WARNING
    )
    logger.log(
        nivel,
        "[tenant_network] %s por definir: os documentos sem carimbo de "
        "empresa/rede ficam visíveis a TODAS as redes (comportamento "
        "anterior ao isolamento). Em produção, defina-a com a rede do "
        "grupo incumbente.", TENANT_DEFAULT_NETWORK_ENV,
    )


async def build_tenant_condition(user: dict) -> dict:
    """Atalho: âmbito do utilizador já convertido em condição Mongo."""
    return build_network_scope_condition(await resolve_tenant_scope(user))


def com_isolamento(tenant_condition: dict, query: Optional[dict]) -> dict:
    """Junta a condição de Rede a uma query de listagem, sem a alterar.

    Vive aqui, e não em cada serviço, porque já existiam DUAS cópias (uma
    em `client_list_search`, uma fechada dentro de `search_api_global`) e a
    terceira ia nascer nas tarefas. Uma regra de isolamento repetida em
    cada listagem é uma regra que divergirá numa delas — e a listagem que
    divergir não dá erro nenhum: devolve dados a mais.

    O `$and` preserva a query original intacta: os filtros de estado, de
    processo e de responsável continuam a valer, só deixam de atravessar
    redes.
    """
    if not query:
        return dict(tenant_condition)
    return {"$and": [tenant_condition, query]}


async def resolve_tenant_stamp(
    user: dict,
    *,
    active_company_id: Any = None,
) -> Optional[dict]:
    """Carimbo a gravar num documento novo, ou ``None``.

    Devolve ``None`` quando não há contexto de empresa: carimbar uma rede
    errada é pior do que não carimbar, porque o documento passaria a ser
    visível à rede errada para sempre. Sem carimbo, ele cai na pilha por
    carimbar, que a migração resolve depois.
    """
    cid = _texto(active_company_id) or _texto((user or {}).get("active_company_id"))
    if cid in VALORES_SEM_EMPRESA:
        cid = ""

    nome = ""
    if not cid:
        nome = _texto((user or {}).get("company"))
        if nome in VALORES_SEM_EMPRESA:
            nome = ""
        if not nome:
            return None

    chave = cid or nome
    empresa = None
    try:
        empresa = await db.companies.find_one(
            {"$or": [{"id": chave}, {"name": chave}]},
            {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
        )
    except Exception as exc:
        logger.warning("[tenant_network] Falha a ler a empresa %s (%s).", chave, exc)

    rede = resolve_network_id(empresa, company_id=chave)
    if not rede:
        return None

    carimbo = {
        "company_id": _texto(empresa.get("id")) if empresa else cid,
        "company_name": _texto(empresa.get("name")) if empresa else nome,
        CAMPO_REDE: rede,
    }
    return {chave_: valor for chave_, valor in carimbo.items() if valor}


# ====================================================================
# O PREDICADO GÉMEO DA CONDIÇÃO (D-24, Out 2026)
# ====================================================================
# `build_network_scope_condition` responde à pergunta em Mongo, para
# LISTAGENS. Um `find_one({"id": x})` seguido de uma verificação de posse
# precisa da MESMA resposta em Python, e escrevê-la à mão em cada
# serviço era garantir que uma delas divergia — a que divergisse
# deixaria ver (ou esconderia trabalho real) sem dar erro nenhum.
#
# Os dois DERIVAM das mesmas constantes e há um teste de CONCORDÂNCIA
# que os corre sobre os mesmos documentos: é a lição do `sub35`, onde
# foi precisamente esse teste a apanhar que o filtro e a etiqueta
# discordavam numa data no futuro.


def _marca_vazia(valor: Any) -> bool:
    """O campo não identifica empresa nenhuma?"""
    return _texto(valor) in {_texto(v) for v in VALORES_SEM_EMPRESA}


def documento_sem_marca_de_tenant(doc: Optional[dict]) -> bool:
    """Gémeo em Python do `_sem_marca_de_tenant()`.

    "Por carimbar" exige a ausência de TODAS as marcas — não só do
    `network_id`. Olhar apenas para a rede deixaria a fuga entrar pela
    cláusula que existe para a evitar: um imóvel da Domus criado entre o
    carimbo na escrita e a migração tem empresa e ainda não tem rede, e
    contá-lo como "legado" entregava-o ao grupo incumbente.
    """
    doc = doc or {}
    return all(
        _marca_vazia(doc.get(campo)) for campo in (CAMPO_REDE, *CAMPOS_EMPRESA)
    )


def documento_no_ambito(doc: Optional[dict], scope: TenantScope) -> bool:
    """Este documento cai no âmbito deste utilizador?

    Ramo a ramo, o espelho do `$or` que o construtor devolve:

    1. a rede do documento é uma das do utilizador;
    2. a empresa do documento (em qualquer dos três campos) é uma das
       suas — é assim que o histórico, que grava ora o id ora o nome,
       continua a ser alcançável;
    3. o documento não tem marca NENHUMA **e** o utilizador pertence à
       rede de omissão.

    Sem nenhum dos três: **não**. Falha fechada, como o construtor, que
    devolve uma condição impossível em vez de `None`.
    """
    if scope.sem_fronteira:
        return True

    doc = doc or {}

    rede = _texto(doc.get(CAMPO_REDE))
    if rede and rede in {_texto(r) for r in scope.network_ids if _texto(r)}:
        return True

    empresas = {
        _texto(e)
        for e in (*scope.company_ids, *scope.company_names)
        if _texto(e)
    }
    if empresas and any(
        _texto(doc.get(campo)) in empresas for campo in CAMPOS_EMPRESA
    ):
        return True

    return bool(scope.inclui_rede_de_omissao) and documento_sem_marca_de_tenant(doc)


def ambito_de_um_documento(doc: Optional[dict]) -> TenantScope:
    """O âmbito da PONTA de um cruzamento, lido do próprio documento.

    O Smart Match não tem utilizador: `check_and_notify_matches_for_new_property`
    corre em background e manda o resultado por email. A fronteira tem
    por isso de sair dos DOCUMENTOS — um cruzamento liga duas pontas da
    MESMA rede, e a âncora diz qual é.

    Um documento por carimbar pertence à rede de omissão, que é
    exactamente o que a variável de ambiente declara. Sem ela (dev, CI)
    mantém-se o comportamento anterior — todas as redes — com o mesmo
    aviso de sempre, nunca em silêncio.
    """
    rede = _texto((doc or {}).get(CAMPO_REDE))
    omissao = rede_de_omissao()

    if rede:
        return TenantScope(
            network_ids=(rede,),
            inclui_rede_de_omissao=bool(omissao) and rede == omissao,
        )

    if omissao:
        return TenantScope(network_ids=(omissao,), inclui_rede_de_omissao=True)

    _avisar_omissao_por_definir()
    return TenantScope(inclui_rede_de_omissao=True)


async def empresas_das_minhas_redes(scope: TenantScope) -> tuple[str, ...]:
    """Todas as empresas (ids E nomes) das redes deste utilizador.

    PARA QUE SERVE, E PORQUE É QUE NÃO É O CONSTRUTOR NORMAL
    --------------------------------------------------------
    Há colecções que **já** identificam a empresa em cada registo e
    nunca tiveram `network_id`: `process_finances` é a principal (é
    chaveada por `(process_id, company_id)`, que é a própria repartição
    de comissões de uma partilha). Para essas, carimbar a rede exigiria
    uma migração — e até ela correr, filtrar só pelas empresas do
    utilizador **esconderia** da Precision os registos da Power, que
    estão na mesma rede e que ela deve ver. Dados a menos não se notam
    menos do que dados a mais: notam-se pior, porque parecem um bug de
    contabilidade.

    Resolver a rede → empresas fecha a fronteira usando um campo que
    está preenchido em todos os registos, sem migração nenhuma.

    A ilha implícita (`rede:<company_id>`) devolve o seu próprio id: é
    uma empresa sem grupo configurado, e é dela que a rede deriva.
    """
    if scope.sem_fronteira:
        encontradas_todas: list[str] = []
        try:
            cursor = db.companies.find({}, {"_id": 0, "id": 1, "name": 1})
            for empresa in await cursor.to_list(2000):
                encontradas_todas.extend(
                    v for v in (_texto(empresa.get("id")), _texto(empresa.get("name"))) if v
                )
        except Exception as exc:
            logger.warning(
                "[tenant_network] Falha a listar as empresas para o Master (%s).", exc,
            )
        return tuple(dict.fromkeys(encontradas_todas))

    redes = {_texto(r) for r in scope.network_ids if _texto(r)}
    if not redes:
        return ()

    encontradas: list[str] = []

    # A ilha de uma só: a rede É a empresa, e não há linha em `companies`
    # que a declare — o nome deriva do id (`rede_implicita`).
    prefixo = rede_implicita("")
    for rede in redes:
        if rede.startswith(prefixo) and len(rede) > len(prefixo):
            encontradas.append(rede[len(prefixo):])

    try:
        cursor = db.companies.find(
            {CAMPO_REDE: {"$in": sorted(redes)}},
            {"_id": 0, "id": 1, "name": 1},
        )
        for empresa in await cursor.to_list(500):
            encontradas.extend(
                valor for valor in (_texto(empresa.get("id")), _texto(empresa.get("name"))) if valor
            )
    except Exception as exc:
        # Nunca AMPLIAR o âmbito por causa de um erro: sem a colecção de
        # empresas fica o que já se conseguiu derivar das ilhas.
        logger.warning(
            "[tenant_network] Falha a resolver as empresas das redes %s (%s); "
            "o âmbito por empresa fica reduzido ao que se derivou das ilhas.",
            sorted(redes), exc,
        )

    return tuple(dict.fromkeys(e for e in encontradas if e))


def condicao_da_mesma_rede(ancora: Optional[dict]) -> dict:
    """A condição da OUTRA ponta de um cruzamento entre colecções.

    Um cruzamento (imóvel × processo, lead × processo, recomendação do
    Portal) liga duas pontas da MESMA rede, e a âncora é que diz qual é.
    Vive aqui porque são QUATRO módulos a fazer a mesma pergunta
    (`client_match`, `match_api_smart`, `portal_recommendations`,
    `alerts`) — quatro cópias divergiriam, e a que divergisse não daria
    erro nenhum: devolveria resultados a mais.
    """
    return build_network_scope_condition(ambito_de_um_documento(ancora))


def build_company_field_condition(
    empresas: Sequence[str],
    *,
    campo: str = "company_id",
) -> dict:
    """«A empresa deste registo é uma das minhas redes», num campo só.

    Uma lista VAZIA devolve a condição impossível e **nunca** `{}`: é a
    regra do `build_network_scope_condition` e do `ramo_dos_processos`,
    porque um `{}` casa com tudo e é a forma de uma guarda se desligar a
    si mesma em silêncio.
    """
    valores = sorted({_texto(e) for e in empresas if _texto(e)})
    if not valores:
        return CONDICAO_IMPOSSIVEL
    return {campo: {"$in": valores}}
