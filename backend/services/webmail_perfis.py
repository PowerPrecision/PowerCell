"""
====================================================================
QUEM TEM WEBMAIL: O PERFIL INDEX NÃO (Lote 7.1, Out 2026)
====================================================================
O perfil `indexacao` («Index») trabalha o Kanban e os documentos; o correio
da empresa não é dele. A decisão de produto é «o Index NÃO tem acesso ao
Webmail» — e a parede tem de ser o SERVIDOR: esconder o item do menu e a rota
do ecrã não fecha a API (o menu e as rotas têm de concordar, e a API é a rota).

COMO
  Uma dependência do router `/emails`, que recusa (403) qualquer pedido cujo
  perfil EFECTIVO seja `indexacao`, EXCEPTO as leituras de correio ligado a UM
  processo (`/process/{id}`, `/timeline/{id}`, `/stats/{id}`,
  `/sync-status/{id}`) e o contador de não lidas do cabeçalho: não são o
  cliente de correio, são parte do ecrã do processo, que a posse do processo
  (`process_scope_guard`) e `email_access` já decidem. A lista é ESCRITA e há
  um teste que a afirma por igualdade — uma rota nova de `/emails` nasce
  fechada ao Index por omissão, que é o sentido seguro.

O PERFIL É O EFECTIVO
  Quem tem outro cargo na empresa activa (por exemplo, consultor) e escolhe
  esse chapéu tem Webmail: decide-se por `effective_role`
  (`role_scope.papel_concreto_do_utilizador`), não pelo cargo da conta.
====================================================================
"""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request

from services.auth import get_current_user
from services.role_scope import papel_concreto_do_utilizador

logger = logging.getLogger(__name__)

PAPEIS_SEM_WEBMAIL = frozenset({"indexacao"})

ERRO_SEM_WEBMAIL = "O perfil Index não tem acesso ao Webmail."

#: Sufixos (depois de `/emails`) que o Index continua a poder chamar.
ROTAS_DE_PROCESSO_QUE_FICAM = frozenset({
    "/process/{process_id}",
    "/timeline/{process_id}",
    "/stats/{process_id}",
    "/sync-status/{process_id}",
    "/notifications/unread",
})


def _sufixo_da_rota(request: Request) -> str:
    rota = request.scope.get("route")
    caminho = getattr(rota, "path", "") or request.url.path
    return caminho.split("/emails", 1)[1] if "/emails" in caminho else caminho


def papel_tem_webmail(papel) -> bool:
    return str(papel or "").strip().lower() not in PAPEIS_SEM_WEBMAIL


async def exigir_perfil_com_webmail(
    request: Request, user: dict = Depends(get_current_user),
) -> None:
    """Dependência do router `/emails`: 403 ao perfil Index fora do ecrã do processo."""
    if papel_tem_webmail(papel_concreto_do_utilizador(user)):
        return
    if _sufixo_da_rota(request) in ROTAS_DE_PROCESSO_QUE_FICAM:
        return
    logger.warning(
        "[WEBMAIL] %s (Index) pediu %s %s: sem acesso ao Webmail.",
        (user or {}).get("id"), request.method, request.url.path,
    )
    raise HTTPException(status_code=403, detail=ERRO_SEM_WEBMAIL)
