"""
====================================================================
Quem pode usar as ferramentas de IA sobre os documentos de um processo
====================================================================
(QA, Out 2026.) A IA sobre documentos — «Analisar», «Renomear IA», «Extrair
dados» — estava em `require_roles([MASTER, ADMIN, CEO, DIRETOR])`. O
`require_roles` decide pelo CARGO e não vê o processo, logo não sabe
responder «esta pessoa trata deste processo?». Num processo PARTILHADO entre
redes (B2B) quem trabalha os documentos na rede de destino é a equipa que a
distribuição lhe atribuiu — consultor e intermediário —, e essa equipa não
tinha a ferramenta: o botão não aparecia e o servidor responderia 403.

REGRA (a mesma que o `rename-smart` já aplicava a um ficheiro): GESTÃO **ou**
ATRIBUÍDO ao processo, e sempre DENTRO da fronteira de rede (a rede dona ou
uma rede convidada — `processo_no_ambito`). Não há nenhuma condição «só a rede
primária»: a fronteira é a de qualquer outra operação sobre o processo.

PORQUÊ UM MÓDULO À PARTE
  A pergunta «posso usar a IA neste processo?» é feita em QUATRO sítios (as três
  rotas e a flag que o detalhe do processo devolve ao ecrã). O ecrã não pode ter
  uma cópia da lista de campos de atribuição — divergiria dos escritores sem dar
  erro, e o botão esconder-se-ia a quem tem direito. Por isso o servidor calcula
  a resposta com a MESMA função que usa para recusar (`pode_usar_ia_no_processo`).
====================================================================
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from models.auth import UserRole
from services.auth import (
    authorization_role,
    effective_role_is_allowed,
    get_effective_role_async,
)
from services.document_visibility import _ambito_do_utilizador, processo_fora_da_rede
from services.process_staff_assignment import collect_assigned_ids

logger = logging.getLogger(__name__)

#: Cargos de gestão que usam a IA em qualquer processo do seu âmbito de rede.
#: Aplica-se a hierarquia do `require_roles` (o Admin e o CEO passam por ela).
PAPEIS_DE_GESTAO_DA_IA = [UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]

DETALHE_SEM_PERMISSAO_DE_IA = (
    "A análise de documentos com IA está reservada à gestão e aos utilizadores "
    "atribuídos a este processo."
)


def pode_usar_ia(
    papel_efectivo: Optional[str], user: dict, process: dict, *, scope
) -> bool:
    """Decisão pura. `scope=None` significa «não sei» e NÃO aplica a fronteira
    (como as puras de `document_visibility`); as variantes `async` resolvem-no
    sempre e falham fechadas.
    """
    if processo_fora_da_rede(process, scope):
        return False
    if effective_role_is_allowed(papel_efectivo or "", PAPEIS_DE_GESTAO_DA_IA):
        return True
    uid = str((user or {}).get("id") or "").strip()
    return bool(uid and uid in set(collect_assigned_ids(process)))


async def pode_usar_ia_no_processo(request, user: dict, process: dict) -> bool:
    """A resposta que o servidor aplica e que o ecrã recebe."""
    effective = await get_effective_role_async(request, user)
    papel = authorization_role(effective, user)
    return pode_usar_ia(papel, user, process, scope=await _ambito_do_utilizador(user))


async def exigir_ia_no_processo(request, user: dict, process: dict) -> None:
    """403 quando não é gestão nem está atribuído (ou o processo é de fora do âmbito)."""
    if await pode_usar_ia_no_processo(request, user, process):
        return
    logger.warning(
        "[DOCS-IA] Negado: user=%s ao processo %s (não é gestão nem está atribuído)",
        (user or {}).get("id"), (process or {}).get("id"),
    )
    raise HTTPException(status_code=403, detail=DETALHE_SEM_PERMISSAO_DE_IA)
