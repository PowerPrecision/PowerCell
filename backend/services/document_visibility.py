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
      - perfil INDEX (role `indexacao`/`index` — a equipa que trata e
        classifica os documentos);
      - perfil ADMIN;
      - o próprio utilizador atribuído ao processo (consultor,
        intermediário/mediador, indexador — qualquer campo de atribuição).
    Os restantes perfis (ex.: consultores não atribuídos) recebem
    403 Forbidden.

Depois de o processo estar indexado (marcado pelo Índice em
`process_indexing.run_mark_process_indexed` → `is_indexed=True`),
a visibilidade volta ao comportamento normal da aplicação.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from database import db
from services.process_indexing import collect_assigned_user_ids

logger = logging.getLogger(__name__)

# Perfis com acesso universal à documentação em tratamento (pré-indexação)
_PRE_INDEX_ALLOWED_ROLES = {"index", "indexacao", "admin"}

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


def user_can_view_process_documents(user: dict, process: dict) -> bool:
    """
    Verifica a permissão de VER documentos do processo.

    Returns:
        True se o processo já está indexado (visibilidade normal), se o
        utilizador é INDEX/ADMIN, ou se está atribuído ao processo.
    """
    if not is_document_visibility_restricted(process):
        return True  # já indexado — visibilidade normal da aplicação

    roles = _user_allows(user)
    if roles & _PRE_INDEX_ALLOWED_ROLES:
        return True

    assigned_ids = set(collect_assigned_user_ids(process))
    if user.get("id") and user.get("id") in assigned_ids:
        return True

    return False


async def assert_can_view_process_documents(user: dict, process: dict) -> None:
    """
    Guarda de permissão para endpoints de leitura/listagem de documentos.

    Raises:
        HTTPException(403) se o processo não está indexado e o utilizador
        não é INDEX/ADMIN nem está atribuído ao processo.
    """
    if user_can_view_process_documents(user, process):
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
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        from services.document_constants import ERROR_PROCESS_NOT_FOUND

        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    await assert_can_view_process_documents(user, process)
    return process
