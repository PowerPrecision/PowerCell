"""O contexto de acesso de um utilizador — papel efectivo, redes, processos.

PORQUE É QUE SAIU DO `deadlines_api_scope` (Lote 9, parte 2)
===========================================================
Nasceu no Lote 7 para o calendário e a pergunta que responde não é do
calendário: «que papel tem este utilizador AGORA, que redes vê, e que
processos lhe pertencem?». O `db.visits` precisava da mesma resposta, e a
alternativa era uma segunda cópia — que divergiria na primeira mudança, e
a que divergir deixa ver ou deixa escrever (é a lição do `com_isolamento`,
que já tinha vivido em duas cópias antes de assentar no `tenant_network`).

O PREDICADO DE EQUIPA É UM PARÂMETRO, NÃO UMA CONSTANTE
=======================================================
A versão do calendário tinha o `e_papel_de_equipa` (ADMIN/CEO/DIRETOR)
escrito por dentro. Nas VISITAS o conjunto é outro — o `administrativo`
coordena visitas e perdê-las-ia de vista —, e usar o do calendário
devolvia a este perfil só os processos atribuídos a ele, estreitando a
vista de equipa sem dar erro. Quem pergunta diz qual é o seu conjunto;
o que não muda é a FRONTEIRA DE REDE, que se aplica a todos menos a
ADMIN/CEO.

O CONJUNTO DE PROCESSOS FALHA FECHADO
=====================================
Carrega-se uma vez por pedido (a alternativa era um `find_one` por
registo — o N+1 que o `enrich_emails` já tinha substituído) e, se a
leitura falhar, devolve-se o conjunto VAZIO. Devolver "todos" era a saída
cómoda e abria a colecção inteira por causa de um soluço da rede.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import Request

from database import db
from services.tenant_network import (
    build_network_scope_condition,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

#: Um registo liga-se a um processo; e um processo liga-se a uma pessoa por
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


async def _processos_visiveis(
    user: dict,
    condicao_de_rede: dict,
    *,
    e_equipa: Callable[[Any], bool],
) -> frozenset[str]:
    """Os ids dos processos que este utilizador vê, dentro da sua rede.

    A condição de rede entra SEMPRE, mesmo para quem está atribuído: uma
    atribuição a um processo de outra rede é um desfasamento de dados
    (`assignment_drift`) e não uma autorização. Para a gestão, o âmbito é a
    rede inteira.
    """
    from services.deadline_scope import e_papel_sem_fronteira

    papel = (user or {}).get("_papel_efectivo") or (user or {}).get("role") or ""
    if e_papel_sem_fronteira(papel):
        consulta: dict = {}
    elif e_equipa(papel):
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
            "[ACESSO] Falha a resolver os processos visíveis de %s: %s",
            (user or {}).get("id"), exc,
        )
        # Falha FECHADA: sem conjunto de processos, a posse passa a
        # depender só da pessoa e da rede. Devolver "todos" era a saída
        # cómoda e abria a colecção inteira por causa de um soluço.
        return frozenset()
    return frozenset(str(d["id"]) for d in docs if d.get("id"))


async def carregar_contexto_de_acesso(
    user: dict,
    request: Optional[Request] = None,
    *,
    e_equipa: Optional[Callable[[Any], bool]] = None,
) -> ContextoDeAcesso:
    """Resolve o papel efectivo, as redes e os processos visíveis.

    `e_equipa` diz quais os papéis que vêem o âmbito da REDE em vez de só
    o que lhes está atribuído. Por omissão é o do calendário, para o
    chamador que já existia não mudar de comportamento.
    """
    from services.auth import get_all_user_roles, get_effective_role_async
    from services.deadline_scope import e_papel_de_equipa

    equipa = e_equipa or e_papel_de_equipa

    papel = (user or {}).get("role") or ""
    if request is not None:
        try:
            papel = await get_effective_role_async(request, user) or papel
        except Exception as exc:
            logger.warning("[ACESSO] Falha a resolver o papel efectivo: %s", exc)

    # `__all_roles__` é o modo "todos os perfis" e não um nome de papel:
    # traduzi-lo é o que impede o `exigir_capacidade` de recusar tudo, e
    # aqui o que impede um diretor em modo global de cair na vista pessoal.
    # A tradução usa o MESMO predicado de equipa que o resto da função —
    # com dois, um perfil podia entrar na vista de equipa e receber o
    # conjunto de processos da vista pessoal.
    if str(papel).strip().lower() == "__all_roles__":
        papeis = get_all_user_roles(user or {})
        de_equipa = next((p for p in papeis if equipa(p)), "")
        papel = de_equipa or ((user or {}).get("role") or "")

    scope = await resolve_tenant_scope(user)
    condicao = build_network_scope_condition(scope)
    utilizador_com_papel = {**(user or {}), "_papel_efectivo": papel}
    processos = await _processos_visiveis(
        utilizador_com_papel, condicao, e_equipa=equipa
    )

    return ContextoDeAcesso(
        papel=str(papel or ""),
        redes=tuple(scope.network_ids),
        processos=processos,
        condicao_de_rede=condicao,
    )


__all__ = [
    "CAMPOS_DE_ATRIBUICAO",
    "ContextoDeAcesso",
    "carregar_contexto_de_acesso",
    "condicao_dos_meus_processos",
]
