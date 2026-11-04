"""Configuração do sistema DA EMPRESA certa — ponto único para os leitores.

PORQUE É QUE ISTO EXISTE (Flavio, Nov 2026 — revisão do painel)
=================================================================
O Painel deixava o CEO gravar, por empresa, a Análise DSTI, os Rascunhos
automáticos e os Destinatários de documentação (balcões). Gravava-se sem erro,
mas os leitores iam sempre à configuração GLOBAL (`get_system_config()` sem
argumento): o valor da empresa não fazia nada.

Decisão do Flavio (perguntas 6a e 7a): estas três são POR EMPRESA e lêem-se
pela empresa do processo (ou, sem processo, pela empresa activa de quem pede).
Uma empresa sem configuração própria herda a global — é o que
`get_system_config(<empresa>)` já faz (copy-on-write, nada é gravado).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from services.tenant_network import CAMPOS_EMPRESA, VALORES_SEM_EMPRESA

logger = logging.getLogger(__name__)

EMPRESA_GLOBAL = "default"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


async def id_da_empresa(chave: Any, *, bd=None) -> str:
    """O `id` da empresa a partir do id OU do nome; `default` se não a encontrar.

    A configuração de uma empresa grava-se pelo id (`company:<id>`); os
    processos e os utilizadores antigos guardam às vezes o NOME. Ler pelo nome
    leria um documento que não existe e cairia, calado, na global.
    """
    chave = _texto(chave)
    if not chave or chave in VALORES_SEM_EMPRESA or chave.lower() == EMPRESA_GLOBAL:
        return EMPRESA_GLOBAL
    try:
        empresa = await (bd if bd is not None else db).companies.find_one(
            {"$or": [{"id": chave}, {"name": chave}]}, {"_id": 0, "id": 1},
        )
    except Exception as exc:  # noqa: BLE001 — sem empresa legível, vale a global
        logger.warning("[config_da_empresa] Falha a ler a empresa %r (%s).", chave, exc)
        return EMPRESA_GLOBAL
    return _texto((empresa or {}).get("id")) or EMPRESA_GLOBAL


async def empresa_do_processo(processo: Optional[dict], *, bd=None) -> str:
    """O `id` da empresa do processo para ler a configuração (`default` se não tiver)."""
    processo = processo or {}
    for campo in CAMPOS_EMPRESA:
        valor = processo.get(campo)
        if _texto(valor) and valor not in VALORES_SEM_EMPRESA:
            empresa = await id_da_empresa(valor, bd=bd)
            if empresa != EMPRESA_GLOBAL:
                return empresa
    return EMPRESA_GLOBAL


async def config_do_processo(processo: Optional[dict] = None, *, process_id: Optional[str] = None, bd=None):
    """`SystemConfig` da empresa do processo (dado o documento ou só o id)."""
    from services.system_config import get_system_config

    if processo is None and process_id:
        try:
            processo = await (bd if bd is not None else db).processes.find_one(
                {"id": process_id}, {"_id": 0, **{c: 1 for c in CAMPOS_EMPRESA}},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[config_da_empresa] Falha a ler o processo %s (%s).", process_id, exc)
            processo = None
    return await get_system_config(await empresa_do_processo(processo, bd=bd))


async def config_da_empresa(chave: Any, *, bd=None):
    """`SystemConfig` de uma empresa dada pelo id ou pelo nome."""
    from services.system_config import get_system_config

    return await get_system_config(await id_da_empresa(chave, bd=bd))
