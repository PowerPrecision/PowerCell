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
    if user_can_view_process_documents(user, process):
        return
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
