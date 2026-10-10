"""Visibilidade de documentos por fase de indexação (permissões de leitura).

BUGFIX (E2E — segurança de visibilidade de documentos, Set 2026, CRÍTICO):
os documentos carregados pelo cliente via Portal ficavam imediatamente
visíveis para QUALQUER utilizador autenticado (os endpoints de
listagem/leitura apenas exigiam `get_current_user`, sem filtro de
permissão por processo) — um consultor sem qualquer relação com o
processo via a documentação pessoal do cliente (CC, recibos, extractos)
antes sequer de a equipa de indexação a tratar e classificar.

Regra de negócio (aplicada nas rotas de leitura/listagem de
`routes/documents.py`):
    Enquanto o processo associado NÃO estiver classificado como Indexado
    (`is_indexed` != True), os documentos SÓ podem ser vistos por:
      - os perfis de administração (bypass ABSOLUTO — ver abaixo);
      - perfil INDEX (role `indexacao`/`index` — a equipa que trata e
        classifica os documentos);
      - o próprio utilizador atribuído ao processo (consultor,
        intermediário/mediador, indexador — qualquer campo de atribuição).
    Os restantes perfis (ex.: consultores não atribuídos) recebem
    403 Forbidden.

PACOTE 5 (auditoria de visibilidade — bypass absoluto dos admins):
verificados os nomes EXACTOS das roles na base de dados (fonte canónica
`models/permissions.py` / `models/enums.py` — lista definitiva de perfis:
admin, ceo, diretor, administrativo, consultor, intermediario, indexacao,
parceiro, cliente). Os perfis de administração/gestão:
      - `admin` e `ceo` — SUPER_ADMIN_ROLES (bypass total de capabilities);
      - `diretor` — gestão (DOCUMENT_VIEW_ALL=True por defeito);
      - `administrativo` — administração (DOCUMENT_VIEW_ALL=True por defeito);
      - variantes históricas defensivas (`system_admin`, `super_admin`),
        para ambientes cuja BD ainda contenha roles legadas.
    …têm agora BYPASS ABSOLUTO à regra `is_indexed`: a verificação admin é
    a PRIMEIRA de todas (antes mesmo de avaliar a restrição) e nunca é
    bloqueada em nenhuma circunstância. Um admin deixa de poder ficar
    cego à documentação em tratamento por config/estado do processo.

Depois de o processo estar indexado (marcado pelo Índice em
`process_indexing.run_mark_process_indexed` → `is_indexed=True`),
a visibilidade volta ao comportamento normal da aplicação.

PACOTE 12 (Eixo 3 — RBAC): um CONSULTOR com relação directa com o
CLIENTE do processo — atribuído ao cliente (`client.assigned_to` ==
user id) ou criador do cliente (`client.created_by` == user email) —
também vê a documentação em tratamento (allow-path adicional nas
guardas async, avaliado após a atribuição ao processo). Antes, um
consultor responsável pelo cliente mas não atribuído ao processo
recebia 403 nas rotas de leitura (GET /api/documents/client/{id}/files
e simétricas) — sem sequer conseguir abrir os documentos do próprio
cliente dele. A leitura deixa de bloquear; as operações de ESCRITA
(delete/unlink do cliente) mantêm as regras de gestão originais.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from database import db
from models.permissions import SUPER_ADMIN_ROLES
from services.process_indexing import collect_assigned_user_ids

logger = logging.getLogger(__name__)

# PACOTE 5 — perfis de administração com BYPASS ABSOLUTO à regra is_indexed.
# Nomes exactos verificados na BD (models/permissions.py: SUPER_ADMIN_ROLES
# = ["admin", "ceo"]; models/enums.py: management = diretor/ceo/admin;
# administrativo tem DOCUMENT_VIEW_ALL=True). Inclui variantes legadas
# defensivas para BDs com roles históricas não migradas.
_ADMIN_BYPASS_ROLES = {
    *SUPER_ADMIN_ROLES,   # admin, ceo — bypass total de capabilities
    "diretor",            # gestão — DOCUMENT_VIEW_ALL=True
    "administrativo",     # administração — DOCUMENT_VIEW_ALL=True
    # Variantes históricas/defensivas (não existem na lista definitiva,
    # mas garantem que nenhuma role admin fica bloqueada em BDs legadas)
    "system_admin",
    "super_admin",
}

# Perfis com acesso à documentação em tratamento (pré-indexação):
# equipa de indexação + os perfis admin acima (bypass absoluto).
_PRE_INDEX_ALLOWED_ROLES = {"index", "indexacao"} | _ADMIN_BYPASS_ROLES

_ERROR_DETAIL = (
    "Os documentos deste processo ainda estão em tratamento pela "
    "equipa de indexação e só são visíveis para o Índice, Admin ou "
    "utilizadores atribuídos ao processo."
)


def is_document_visibility_restricted(process: Optional[dict]) -> bool:
    """
    True enquanto o processo ainda não estiver indexado (documentos em
    tratamento) — altura em que a visibilidade é restrita.
    """
    if not process:
        return False
    return process.get("is_indexed") is not True


def _user_allows(user: dict) -> set:
    """Roles do utilizador (role principal + additional_roles + effective)."""
    roles = set()
    for key in ("role", "effective_role"):
        value = user.get(key)
        if isinstance(value, str) and value:
            roles.add(value.lower())
    additional = user.get("additional_roles") or []
    if isinstance(additional, list):
        roles.update(str(r).lower() for r in additional if r)
    return roles


def _user_is_related_to_client_doc(user: dict, client: Optional[dict]) -> bool:
    """
    PACOTE 12 — relação directa entre o utilizador e o CLIENTE (pura,
    sem I/O): consultor atribuído ao cliente (``client.assigned_to`` ==
    user id) ou criador do registo do cliente (``client.created_by`` ==
    user email).
    """
    if not client:
        return False
    if user.get("id") and client.get("assigned_to") == user.get("id"):
        return True
    if user.get("email") and client.get("created_by") == user.get("email"):
        return True
    return False


async def _user_related_to_client(user: dict, client_id: Optional[str]) -> bool:
    """
    PACOTE 12 — carrega o doc do cliente e avalia a relação (async, I/O).

    Devolve False quando não há ``client_id`` ou o cliente não existe
    (guardas contra None) — a verificação é apenas um allow-path
    adicional, nunca um novo motivo de bloqueio.
    """
    if not client_id:
        return False
    client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    return _user_is_related_to_client_doc(user, client)


def user_can_view_process_documents(
    user: dict,
    process: dict,
    client: Optional[dict] = None,
    *,
    scope=None,
) -> bool:
    """
    Verifica a permissão de VER documentos do processo.

    PACOTE 5 — bypass ABSOLUTO dos perfis de administração: a verificação
    admin é a PRIMEIRA de todas (antes mesmo de avaliar se o processo está
    indexado) — um admin/ceo/diretor/administrativo nunca é bloqueado,
    independentemente do estado do processo ou de qualquer outra condição.

    PACOTE 12 — argumento opcional ``client`` (doc do cliente JÁ
    carregado pelo caller): allow-path por relação com o cliente
    (``_user_is_related_to_client_doc``). Esta função mantém-se PURA —
    nunca faz I/O; quem precisa da verificação com carga do doc usa as
    guardas async (``assert_*`` → ``_user_related_to_client``).

    Returns:
        True se o utilizador é um perfil de administração (bypass absoluto),
        se o processo já está indexado (visibilidade normal), se o
        utilizador é INDEX, se está atribuído ao processo ou se tem
        relação directa com o cliente (doc pré-carregado).
    """
    # 0. FRONTEIRA DE REDE — antes do bypass (D-26). O bypass de cargo é
    #    absoluto DENTRO da rede; um bypass que corra primeiro é um
    #    bypass de rede. Conta a rede convidada de um processo
    #    partilhado (D-25), que é a porta que a decisão de produto abre.
    if processo_fora_da_rede(process, scope):
        return False

    # 1. BYPASS ABSOLUTO — perfis de administração (admin, ceo, diretor,
    #    administrativo): verificado primeiro, incondicionalmente.
    roles = _user_allows(user)
    if roles & _ADMIN_BYPASS_ROLES:
        return True

    # 2. Processo já indexado — visibilidade normal da aplicação.
    if not is_document_visibility_restricted(process):
        return True

    # 3. Equipa de indexação (trata/classifica os documentos em pré-indexação).
    if roles & _PRE_INDEX_ALLOWED_ROLES:
        return True

    # 4. Utilizador atribuído ao processo (consultor, mediador, indexador…).
    assigned_ids = set(collect_assigned_user_ids(process))
    if user.get("id") and user.get("id") in assigned_ids:
        return True

    # 5. PACOTE 12 — relação directa com o CLIENTE do processo (doc
    #    opcional pré-carregado; sem I/O nesta função).
    if _user_is_related_to_client_doc(user, client):
        return True

    return False


# ====================================================================
# A FRONTEIRA DE REDE (D-26, fechada com a D-25 — Out 2026)
# ====================================================================
# Esta função não conhecia redes NENHUMAS, e abria por duas linhas:
#
#   1. bypass ABSOLUTO para {admin, ceo, diretor, administrativo},
#      verificado antes de tudo. O diretor de uma ilha é diretor da SUA
#      rede — é a regra 2 do `deadline_scope` e a mesma do `visit_scope`.
#   2. `if not is_document_visibility_restricted(process): return True`
#      — um processo JÁ INDEXADO era visível a qualquer sessão
#      autenticada. A restrição foi escrita para a PRÉ-indexação (o
#      indexador trata os documentos antes de haver equipa), não como
#      fronteira de tenant; e indexado é o caso NORMAL, não o raro. É a
#      forma do `run_get_my_tasks` ao contrário — foi o ramo COMUM não
#      ter guarda nenhuma que escondeu isto.
#
# Do outro lado não eram nomes: era a pasta documental do cliente —
# cartão de cidadão, IRS, recibos, extractos. Bastava um `process_id`.
#
# A fronteira entra ANTES do bypass, e não depois: um bypass de cargo
# que corre primeiro é um bypass de rede.
#
# PORQUE É QUE SÓ FECHA AGORA
# ---------------------------
# A guarda certa É a resposta da D-25: num processo em PARTILHA o lado
# convidado **tem de ver os documentos** (decisão de produto: «a ficha
# inteira»). Escrever aqui uma fronteira de rede pura fechava a porta
# que a partilha precisa de abrir — e alargar uma parede depois para
# caber a correcção é como o Incidente P0 do Portal começou. Por isso
# usa o `processo_no_ambito`, que já conta a rede convidada.
#
# O `scope` é um PARÂMETRO e não uma leitura: estas funções são puras, e
# é isso que as torna testáveis sem Mongo no `backend-fast`. Quem o
# resolve são as guardas `async`, que é o que os endpoints chamam — e há
# uma guarda sobre a fonte a afirmar que o resolvem mesmo.


def processo_fora_da_rede(process: dict, scope) -> bool:
    """O processo está FORA do âmbito de rede deste utilizador?

    `scope=None` significa «não sei» e **não** aplica a fronteira — é o
    que mantém as puras utilizáveis por quem não a tem (e o que não
    partiu os chamadores legados). A parede real está nas guardas
    `async`, que resolvem o âmbito sempre.
    """
    if scope is None:
        return False
    from services.tenant_network import processo_no_ambito

    return not processo_no_ambito(process, scope)


def can_manage_process_documents(
    user: dict, process: dict, *, scope=None,
) -> bool:
    """Pode OPERAR sobre os documentos do processo (renomear, organizar)?

    Gestão OU atribuído — decisão de produto (Set 2026). O
    `rename-smart` estava em `require_roles([ADMIN, CEO, DIRETOR])`, que
    é a regra antiga do `AGENTS.md`, e por isso recusava o consultor
    **dono** do processo: "não faz sentido o dono do processo não poder
    organizar os próprios ficheiros".

    O `require_roles` nunca poderia resolver isto: decide pelo CARGO e
    não vê o processo, logo não sabe responder "está atribuído?". Daí
    esta guarda viver aqui, onde o processo já está carregado.

    A atribuição vem de `collect_assigned_ids`, o PONTO ÚNICO: foi a
    divergência entre listas de campos escritas à mão que produziu o 403
    falso positivo na listagem, e repeti-la aqui reproduzia o defeito
    numa operação de ESCRITA.

    PURA: não toca na base de dados.
    """
    from services.process_staff_assignment import collect_assigned_ids

    # 0. FRONTEIRA DE REDE — antes do bypass de cargo (D-26).
    if processo_fora_da_rede(process, scope):
        return False

    if _user_allows(user) & _ADMIN_BYPASS_ROLES:
        return True

    uid = (user or {}).get("id")
    return bool(uid and uid in set(collect_assigned_ids(process)))


async def exigir_gestao_de_documentos(user: dict, process: dict) -> None:
    """Variante `async`: resolve a FRONTEIRA DE REDE e delega (D-26).

    É esta que os serviços chamam. A versão sem âmbito fica como
    primitivo puro (e para os testes), mas uma operação de ESCRITA sobre
    os documentos de um processo de outra rede não pode passar por ela.
    """
    assert_can_manage_process_documents(
        user, process, scope=await _ambito_do_utilizador(user),
    )


def assert_can_manage_process_documents(
    user: dict, process: dict, *, scope=None,
) -> None:
    """Levanta 403 quando `can_manage_process_documents` recusa."""
    if can_manage_process_documents(user, process, scope=scope):
        return
    logger.warning(
        "[DOCS-MANAGE] Operação negada: user=%s role=%s ao processo %s "
        "(não é gestão nem está atribuído)",
        (user or {}).get("id"), (user or {}).get("role"), (process or {}).get("id"),
    )
    raise HTTPException(
        status_code=403,
        detail=(
            "Só os utilizadores atribuídos a este processo (ou a gestão) "
            "podem reorganizar os documentos."
        ),
    )


async def _ambito_do_utilizador(user: dict):
    """O âmbito de rede de quem pede. Falha **FECHADA**.

    Sem âmbito resolvido devolve um `TenantScope()` vazio, que não casa
    com rede nenhuma — logo `processo_no_ambito` recusa. Devolver `None`
    era a saída cómoda e desligava a fronteira por causa de um soluço da
    rede, que é o oposto do que esta guarda existe para fazer.
    """
    from services.tenant_network import TenantScope, resolve_tenant_scope

    try:
        return await resolve_tenant_scope(user or {})
    except Exception as exc:
        logger.warning(
            "[DOCS-VISIBILITY] Falha a resolver o âmbito de %s (%s); a "
            "fronteira de rede passa a recusar.",
            (user or {}).get("id"), exc,
        )
        return TenantScope()


async def assert_can_view_process_documents(user: dict, process: dict) -> None:
    """
    Guarda de permissão para endpoints de leitura/listagem de documentos.

    PACOTE 12 — allow-path adicional (após a verificação pura, antes do
    raise): utilizador com relação directa com o CLIENTE do processo
    (atribuído ao cliente / criador do registo) também pode ler.

    Raises:
        HTTPException(403) se o processo não está indexado e o utilizador
        não é INDEX/ADMIN nem está atribuído ao processo nem tem relação
        com o cliente.
    """
    scope = await _ambito_do_utilizador(user)

    if user_can_view_process_documents(user, process, scope=scope):
        return

    # A fronteira de REDE não tem allow-path: um processo de outra rede
    # não se abre por relação com o cliente — o cliente também não é
    # desta rede. Recusa-se aqui, antes do `_user_related_to_client`,
    # que faz I/O e responderia a «este cliente existe?».
    if processo_fora_da_rede(process, scope):
        logger.warning(
            "[DOCS-VISIBILITY] Fronteira de rede: user=%s papel=%s ao "
            "processo %s (rede=%r, parceiras=%r) fora do seu âmbito",
            (user or {}).get("id"), (user or {}).get("role"),
            (process or {}).get("id"), (process or {}).get("network_id"),
            (process or {}).get("partner_network_ids"),
        )
        raise HTTPException(status_code=403, detail=_ERROR_DETAIL)
    # PACOTE 12 — consultor responsável pelo cliente (assigned_to) ou
    # criador do registo (created_by): allow-path assíncrono, avaliado
    # apenas no caminho de negação (sem I/O extra quando já é permitido).
    if await _user_related_to_client(user, process.get("client_id")):
        return
    logger.warning(
        f"[DOCS-VISIBILITY] Acesso negado: user={user.get('id')} "
        f"role={user.get('role')} ao processo {process.get('id')} "
        f"(não indexado, status={process.get('status')!r})"
    )
    raise HTTPException(status_code=403, detail=_ERROR_DETAIL)


async def assert_can_view_process_documents_by_id(
    user: dict,
    process_id: str,
) -> Optional[dict]:
    """
    Carrega o processo por ID e aplica a guarda de visibilidade.

    Returns:
        O documento do processo (para reutilização pelo caller).

    Raises:
        HTTPException(404) se o processo não existir;
        HTTPException(403) se a visibilidade estiver restrita.

    PACOTE 12 — a delegação em ``assert_can_view_process_documents``
    herda automaticamente o allow-path por relação com o cliente.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        from services.document_constants import ERROR_PROCESS_NOT_FOUND

        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    await assert_can_view_process_documents(user, process)
    return process


# ====================================================================
# ESCREVER NA PASTA DE UM PROCESSO (Bloco 2, Lote 12)
# ====================================================================
# O upload (multipart, URL pré-assinado, confirmação, verificação de
# conflito e o «Arquivar no Processo» do Webmail) carregava o processo com
# `resolve_process_from_flexible_id` e MAIS NADA: bastava um `process_id`
# para escrever na pasta documental de um cliente de OUTRA rede. A D-26
# fechou a LEITURA; esta fecha a escrita, que é pior (planta um ficheiro na
# ficha de outra casa e, se o processo estiver por indexar, põe-no na fila
# da IA dela).
#
# Quem escreve é quem pode ver. Um perfil que a D-26 deixa LER mantém a
# capacidade de ESCREVER (administração e gestão dentro da rede, a equipa
# de indexação, o atribuído) — e a rede convidada de um processo partilhado
# (D-25) conta, porque `assert_can_view_process_documents` já a conta.
# `parceiro` e `cliente` não carregam ficheiros pela API do CRM: o Portal
# tem o seu próprio caminho, com a sua própria parede.
_PAPEIS_QUE_NAO_CARREGAM = frozenset({"parceiro", "cliente"})


async def assert_can_upload_to_process(user: dict, process: dict) -> None:
    """Levanta 403 se o utilizador não pode carregar ficheiros para o processo."""
    roles = _user_allows(user)
    if roles and roles <= _PAPEIS_QUE_NAO_CARREGAM:
        logger.warning(
            "[DOCS-UPLOAD] Upload recusado ao perfil %s no processo %s",
            sorted(roles), (process or {}).get("id"),
        )
        raise HTTPException(status_code=403, detail=_ERROR_DETAIL)
    await assert_can_view_process_documents(user, process)

