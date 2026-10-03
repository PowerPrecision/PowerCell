"""O contexto de acesso de um utilizador ao calendário (Lote 7, ponto 3).

Vive separado do `deadline_scope` (puro) porque este TOCA na base de dados:
resolve o papel efectivo, as redes do utilizador e os processos que ele vê.
Vive separado do `deadlines_api_crud` porque as três superfícies precisam
dele — `GET /deadlines`, `PUT /deadlines/{id}` e `DELETE /deadlines/{id}` —
e três cópias da mesma resolução divergem na primeira mudança. A que
divergir não dá erro: deixa ver, ou deixa escrever.

O PAPEL É O EFECTIVO, NUNCA O DO JWT
====================================
`run_get_deadlines` e `run_get_my_deadlines` decidiam por `user["role"]` —
o cargo do token. Quem tem perfil base de consultor e entra COMO diretor
via a agenda pessoal em vez da agenda da equipa; e, ao contrário,
`run_get_deadlines` isentava ADMIN/CEO do JWT mesmo com outro perfil activo.
É a quarta ocorrência da forma do `history._is_stealth_user`: duas noções de
papel no mesmo caminho dão as duas respostas erradas.

OS PROCESSOS VISÍVEIS SÃO UM CONJUNTO, NÃO UMA CONSULTA POR EVENTO
=================================================================
Carregam-se uma vez por pedido (ids, projecção mínima) porque a alternativa
era um `find_one` por evento — o padrão N+1 que o `enrich_emails` já tinha
substituído. E o conjunto é o mesmo que decide a leitura e a escrita: um
utilizador que vê um processo na listagem vê (e gere) os eventos dele.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import Request

from database import db
from services.tenant_network import (
    build_network_scope_condition,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

#: A mesma mensagem para "não existe" e para "não é teu": distinguir as
#: duas confirma o id a quem está a adivinhar (precedente das notificações).
ERRO_EVENTO_NAO_ENCONTRADO = "Prazo não encontrado"

#: Um evento liga-se a um processo; e um processo liga-se a uma pessoa por
#: estes campos. Os plurais entram porque um processo pode ter dois
#: consultores e o segundo era ignorado por listas escritas à mão (é a
#: lição do `alert_audience`).
CAMPOS_DE_ATRIBUICAO = (
    "assigned_consultor_id",
    "assigned_consultor_ids",
    "consultor_id",
    "consultant_id",
    "assigned_mediador_id",
    "assigned_mediador_ids",
    "mediador_id",
    "intermediario_id",
)


@dataclass(frozen=True)
class ContextoDeAcesso:
    """Papel efectivo, redes e processos visíveis — resolvidos uma vez."""

    papel: str = ""
    redes: tuple[str, ...] = ()
    processos: frozenset[str] = field(default_factory=frozenset)
    condicao_de_rede: dict = field(default_factory=dict)


def condicao_dos_meus_processos(user_id: Any) -> dict:
    """`$or` sobre os campos de atribuição, singulares E plurais.

    No Mongo, `{"campo": valor}` casa tanto com o escalar como com o array
    que o contém — é o que permite a mesma cláusula servir as duas formas.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return {}
    return {"$or": [{campo: uid} for campo in CAMPOS_DE_ATRIBUICAO]}


async def _processos_visiveis(user: dict, condicao_de_rede: dict) -> frozenset[str]:
    """Os ids dos processos que este utilizador vê, dentro da sua rede.

    A condição de rede entra SEMPRE, mesmo para quem está atribuído: uma
    atribuição a um processo de outra rede é um desfasamento de dados
    (`assignment_drift`) e não uma autorização. Para a gestão, o âmbito é a
    rede inteira.
    """
    from services.deadline_scope import e_papel_de_equipa, e_papel_sem_fronteira

    papel = (user or {}).get("_papel_efectivo") or (user or {}).get("role") or ""
    if e_papel_sem_fronteira(papel):
        consulta: dict = {}
    elif e_papel_de_equipa(papel):
        consulta = dict(condicao_de_rede)
    else:
        minha = condicao_dos_meus_processos((user or {}).get("id"))
        if not minha:
            return frozenset()
        consulta = {"$and": [condicao_de_rede, minha]} if condicao_de_rede else minha

    try:
        docs = await db.processes.find(consulta, {"_id": 0, "id": 1}).to_list(20000)
    except Exception as exc:
        logger.warning(
            "[DEADLINES] Falha a resolver os processos visíveis de %s: %s",
            (user or {}).get("id"), exc,
        )
        # Falha FECHADA: sem conjunto de processos, a posse passa a
        # depender só da pessoa e da rede. Devolver "todos" era a saída
        # cómoda e abria o calendário inteiro por causa de um soluço.
        return frozenset()
    return frozenset(str(d["id"]) for d in docs if d.get("id"))


async def carregar_contexto_de_acesso(
    user: dict, request: Optional[Request] = None,
) -> ContextoDeAcesso:
    """Resolve o papel efectivo, as redes e os processos visíveis."""
    from services.auth import get_effective_role_async
    from services.deadlines_api_helpers import sees_team_calendar

    papel = (user or {}).get("role") or ""
    if request is not None:
        try:
            papel = await get_effective_role_async(request, user) or papel
        except Exception as exc:
            logger.warning("[DEADLINES] Falha a resolver o papel efectivo: %s", exc)

    # `__all_roles__` é o modo "todos os perfis" e não um nome de papel:
    # traduzi-lo é o que impede o `exigir_capacidade` de recusar tudo, e
    # aqui o que impede um diretor em modo global de cair na agenda pessoal.
    if str(papel).strip().lower() == "__all_roles__":
        papel = "diretor" if sees_team_calendar(papel, user) else (
            (user or {}).get("role") or ""
        )

    scope = await resolve_tenant_scope(user)
    condicao = build_network_scope_condition(scope)
    utilizador_com_papel = {**(user or {}), "_papel_efectivo": papel}
    processos = await _processos_visiveis(utilizador_com_papel, condicao)

    return ContextoDeAcesso(
        papel=str(papel or ""),
        redes=tuple(scope.network_ids),
        processos=processos,
        condicao_de_rede=condicao,
    )


__all__ = [
    "CAMPOS_DE_ATRIBUICAO",
    "ContextoDeAcesso",
    "ERRO_EVENTO_NAO_ENCONTRADO",
    "carregar_contexto_de_acesso",
    "condicao_dos_meus_processos",
]
