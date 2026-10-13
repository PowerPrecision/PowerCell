"""
====================================================================
Quem pode usar as ferramentas de IA sobre os documentos de um processo
====================================================================
REGRA ACTUAL (decisão da direcção, Out 2026): as ferramentas MANUAIS de IA —
«Analisar», «Renomear IA», «Extrair dados» — são exclusivas dos ALTOS PERFIS
(Master, Admin, CEO, Diretor), pelo perfil EFECTIVO e sempre DENTRO da
fronteira de rede (a rede dona ou uma rede convidada — `processo_no_ambito`).
**Estar atribuído ao processo NÃO dá acesso**: cada clique é uma chamada paga
ao modelo e o controlo de custos da API é a razão da regra. O trabalho normal
não depende do clique — a IA corre sozinha quando um documento cai na `Index`
(`document_ai_trigger`).

HISTÓRICO: numa iteração anterior (QA, Out 2026) abriu-se a ferramenta a
«gestão OU atribuído» para a equipa da rede satélite num processo partilhado.
A direcção revogou-o; o teste que o afirmava foi INVERTIDO, não apagado.

PORQUÊ UM MÓDULO À PARTE
  A pergunta «posso usar a IA neste processo?» é feita em QUATRO sítios (as três
  rotas e a flag que o detalhe do processo devolve ao ecrã). O ecrã não calcula
  a resposta: o servidor decide com a MESMA função que usa para recusar
  (`pode_usar_ia_no_processo`) e o ecrã só mostra o botão a quem ela autoriza.
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

logger = logging.getLogger(__name__)

#: Os ÚNICOS cargos que usam a IA manual, em qualquer processo do seu âmbito de rede.
#: É também a lista que as rotas passam ao `require_roles`.
PAPEIS_DE_GESTAO_DA_IA = [UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]

DETALHE_SEM_PERMISSAO_DE_IA = (
    "A análise de documentos com IA está reservada à gestão "
    "(Master, Admin, CEO e Diretor)."
)


def pode_usar_ia(
    papel_efectivo: Optional[str], user: dict, process: dict, *, scope
) -> bool:
    """Decisão pura. `scope=None` significa «não sei» e NÃO aplica a fronteira
    (como as puras de `document_visibility`); as variantes `async` resolvem-no
    sempre e falham fechadas.

    `user` e `process` mantêm-se na assinatura (a fronteira lê o processo) mas
    NENHUM campo de atribuição conta: estar atribuído não abre a ferramenta.
    """
    if processo_fora_da_rede(process, scope):
        return False
    return effective_role_is_allowed(papel_efectivo or "", PAPEIS_DE_GESTAO_DA_IA)


async def pode_usar_ia_no_processo(request, user: dict, process: dict) -> bool:
    """A resposta que o servidor aplica e que o ecrã recebe."""
    effective = await get_effective_role_async(request, user)
    papel = authorization_role(effective, user)
    return pode_usar_ia(papel, user, process, scope=await _ambito_do_utilizador(user))


async def exigir_ia_no_processo(request, user: dict, process: dict) -> None:
    """403 quando não é um alto perfil (ou o processo é de fora do âmbito)."""
    if await pode_usar_ia_no_processo(request, user, process):
        return
    logger.warning(
        "[DOCS-IA] Negado: user=%s ao processo %s (só os altos perfis usam a IA manual)",
        (user or {}).get("id"), (process or {}).get("id"),
    )
    raise HTTPException(status_code=403, detail=DETALHE_SEM_PERMISSAO_DE_IA)
