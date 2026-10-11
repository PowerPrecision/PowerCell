"""Workflow por rede — a rede EM CONTEXTO de quem edita, e a cópia própria (Out 2026).

O PROBLEMA
  O workflow (fases, flags de propósito, macro-fases, modelos de tarefas) era
  GLOBAL: editá-lo mudava a operação de todas as empresas, e por isso só o
  Master podia. Cada empresa/rede tem a sua operação — a Domus não trabalha
  como a Precision — e quem a gere (Admin/CEO) tem de poder editar o seu
  workflow sem tocar no de ninguém.

A REDE EM CONTEXTO
  O âmbito de DADOS é do utilizador (todas as suas redes); a rede do
  WORKFLOW que ele edita é UMA: a da empresa activa (`X-Company-Id`, o
  ContextSwitcher). Ordem de resolução:

    1. `network_id` pedido, **validado** — o Master pode pedir qualquer rede
       que exista; os outros só as do seu âmbito. Fora disso: 404, igual ao
       de «não existe» (não se confirma que a rede existe);
    2. a rede da empresa activa;
    3. a primeira rede do âmbito (conta com uma só empresa, sem header);
    4. a rede de omissão (`TENANT_DEFAULT_NETWORK_ID`, a pilha antiga).

  Sem nenhuma, 400: editar «o workflow de ninguém» não existe — e a
  alternativa (cair no modelo) era voltar a editar o global.

A CÓPIA PRÓPRIA (copy-on-write)
  Os documentos sem `network_id` são o MODELO. Uma rede lê o modelo enquanto
  não tem fases próprias; **na primeira ESCRITA** materializa-se a cópia da
  rede (`garantir_workflow_da_rede`) e é nela que se escreve. O modelo nunca
  é editado por esta via — é a semente de que as redes novas nascem.
  Materializar é idempotente (um `upsert` por (rede, nome)): dois pedidos
  concorrentes não duplicam fases.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import HTTPException, Request

from database import db
from services.role_scope import utilizador_e_global
from services.tenant_network import (
    CAMPO_REDE,
    TenantScope,
    rede_de_omissao,
    resolve_network_id,
    resolve_tenant_scope,
)
from services.workflow_phases import invalidar_cache_de_fases

logger = logging.getLogger(__name__)

ERRO_REDE_NAO_ENCONTRADA = "Rede não encontrada"
ERRO_SEM_REDE_EM_CONTEXTO = (
    "Não há uma rede em contexto: escolha a empresa no seletor de empresa."
)

#: Campos de uma fase que NÃO se copiam tal e qual para a cópia da rede: o `id` é
#: novo, e `network_id`/`name` já vão no filtro do `upsert` (o Mongo põe-nos no
#: documento criado — repeti-los no `$setOnInsert` era pedir um conflito).
_CAMPOS_DA_COPIA_RENOVADOS = ("_id", "id", "network_id", "name")


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


async def _empresas() -> list[dict]:
    return await db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1, "is_active": 1},
    ).to_list(1000)


async def redes_que_existem() -> dict[str, list[str]]:
    """``rede → nomes das empresas`` de todas as redes conhecidas."""
    redes: dict[str, list[str]] = {}
    for empresa in await _empresas():
        rede = resolve_network_id(empresa, company_id=empresa.get("id"))
        if rede:
            redes.setdefault(rede, [])
            if _texto(empresa.get("name")):
                redes[rede].append(_texto(empresa["name"]))
    return redes


async def rede_da_empresa_activa(user: dict, request: Optional[Request]) -> Optional[str]:
    """A rede da empresa activa (`X-Company-Id`), ou ``None``."""
    if request is None:
        return None
    from services.auth import get_active_company_id_async

    try:
        activa = _texto(await get_active_company_id_async(request, user))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[WORKFLOW] Falha a resolver a empresa activa: %s", exc)
        return None
    if not activa or activa == "default":
        return None
    for empresa in await _empresas():
        if activa in (_texto(empresa.get("id")), _texto(empresa.get("name"))):
            return resolve_network_id(empresa, company_id=empresa.get("id"))
    return None


def _rede_no_ambito(rede: str, scope: TenantScope) -> bool:
    if scope.sem_fronteira:
        return True
    return rede in set(scope.network_ids) or (
        scope.inclui_rede_de_omissao and rede == rede_de_omissao()
    )


async def rede_do_workflow_em_contexto(
    user: dict,
    request: Optional[Request] = None,
    *,
    rede_pedida: Optional[str] = None,
) -> str:
    """A rede cujo workflow este utilizador está a ver/editar (ver o módulo)."""
    scope = await resolve_tenant_scope(user)

    pedida = _texto(rede_pedida)
    if pedida:
        existentes = await redes_que_existem()
        if pedida not in existentes or not _rede_no_ambito(pedida, scope):
            raise HTTPException(status_code=404, detail=ERRO_REDE_NAO_ENCONTRADA)
        return pedida

    activa = await rede_da_empresa_activa(user, request)
    if activa and _rede_no_ambito(activa, scope):
        return activa

    for rede in scope.network_ids:
        if _texto(rede):
            return _texto(rede)

    omissao = rede_de_omissao()
    if omissao:
        return omissao
    raise HTTPException(status_code=400, detail=ERRO_SEM_REDE_EM_CONTEXTO)


async def nomes_da_rede(rede: str) -> list[str]:
    """Os nomes das empresas de uma rede (para o ecrã dizer ONDE está a editar)."""
    return sorted((await redes_que_existem()).get(rede, []), key=str.lower)


async def garantir_workflow_da_rede(rede: str) -> int:
    """Materializa a cópia do workflow da rede a partir do modelo. Devolve quantas fases criou.

    Idempotente: só cria as que a rede ainda não tem (por NOME), com um
    `upsert` por (rede, nome) — uma segunda chamada, ou uma concorrente, não
    duplica nada. **Nunca** altera uma fase que a rede já tenha.
    """
    rede = _texto(rede)
    if not rede:
        raise ValueError("garantir_workflow_da_rede: rede vazia")

    modelo = await db.workflow_statuses.find(
        {"network_id": {"$in": [None, ""]}}, {"_id": 0},
    ).sort("order", 1).to_list(500)
    criadas = 0
    for fase in modelo:
        nome = fase.get("name")
        if not nome:
            continue
        copia = {k: v for k, v in fase.items() if k not in _CAMPOS_DA_COPIA_RENOVADOS}
        resultado = await db.workflow_statuses.update_one(
            {"network_id": rede, "name": nome},
            {"$setOnInsert": {**copia, "id": str(uuid.uuid4()), "network_id": rede}},
            upsert=True,
        )
        # `matched_count == 0` e não `upserted_id`: é a pergunta que o Mongo
        # e o duplo de teste respondem da mesma maneira.
        if getattr(resultado, "matched_count", 1) == 0:
            criadas += 1
    if criadas:
        invalidar_cache_de_fases()
        logger.info("[WORKFLOW] Rede %s: materializadas %d fase(s) a partir do modelo.", rede, criadas)
    return criadas


async def tem_workflow_proprio(rede: str) -> bool:
    return bool(await db.workflow_statuses.find_one({"network_id": _texto(rede)}, {"_id": 0, "id": 1}))


def pode_editar_qualquer_rede(user: dict) -> bool:
    return utilizador_e_global(user)


__all__ = [
    "ERRO_REDE_NAO_ENCONTRADA",
    "ERRO_SEM_REDE_EM_CONTEXTO",
    "garantir_workflow_da_rede",
    "nomes_da_rede",
    "pode_editar_qualquer_rede",
    "rede_da_empresa_activa",
    "rede_do_workflow_em_contexto",
    "redes_que_existem",
    "tem_workflow_proprio",
]
