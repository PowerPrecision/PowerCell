"""Leitura e gravação das Configurações pelo Painel — quem pode o quê.

Extraído de `routes/system_config.py` (o router fica fino). A regra é a do
Flavio (Nov 2026, revisão do painel): ver `services/system_config_scope.py`
(`SECCOES_SO_GLOBAIS`, `PAPEIS_QUE_GRAVAM_A_EMPRESA`) — o CEO grava a empresa,
o Admin já não, o que é global é só do Master. Cada gravação fica no Registo
de auditoria (`services/registo_do_painel.py`). O `ambito` vem já resolvido
pelo router (`carregar_ambito_de_configuracao`), que é a guarda que os testes
procuram em cada handler.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

from services.registo_do_painel import registar_alteracao
from services.system_config_admin_ops import run_reveal_secrets
from services.system_config_api import run_get_config, run_update_config
from services.system_config_scope import (
    CAMPOS_SO_GLOBAIS,
    ERRO_SO_O_CEO,
    SECCOES_SO_GLOBAIS,
    exigir_empresa_configuravel,
    exigir_pode_gravar_seccao,
    pode_gravar_a_empresa,
    tirar_campos_so_globais,
)


async def run_get_config_do_painel(ambito, company_id: Optional[str]) -> dict:
    company_id = await exigir_empresa_configuravel(ambito, company_id)
    resposta = await run_get_config(company_id=company_id)
    # O ecrã desenha só o que este perfil pode gravar (o servidor continua a ser a parede).
    resposta["permissoes"] = {
        "pode_gravar": pode_gravar_a_empresa(ambito),
        "seccoes_so_globais": sorted(SECCOES_SO_GLOBAIS),
        "campos_so_globais": {k: sorted(v) for k, v in CAMPOS_SO_GLOBAIS.items()},
    }
    return resposta


async def _seccao_actual(section: str, company_id: str) -> dict:
    """O valor da secção antes de gravar (para o rasto); `{}` se não se ler."""
    from services.system_config import get_system_config

    try:
        valor = getattr(await get_system_config(company_id), section, None)
        return valor.model_dump() if hasattr(valor, "model_dump") else dict(valor or {})
    except Exception:  # noqa: BLE001 — o rasto não impede a gravação
        return {}


async def run_update_config_do_painel(
    ambito, user: dict, request: Any, section: str, data: Dict[str, Any], company_id: Optional[str],
) -> dict:
    company_id = await exigir_empresa_configuravel(ambito, company_id)
    exigir_pode_gravar_seccao(ambito, section, company_id)
    data = tirar_campos_so_globais(section, data, company_id)

    antes = await _seccao_actual(section, company_id)
    resultado = await run_update_config(section=section, data=data, company_id=company_id, user=user)
    # Flavio, Nov 2026 (14a): cada gravação fica no Registo de auditoria.
    await registar_alteracao(
        user, request, area=f"Configurações ({section})", company_id=company_id,
        antes=antes, depois=data,
    )
    return resultado


async def run_reveal_secrets_do_painel(ambito, section: Optional[str], company_id: Optional[str]) -> dict:
    company_id = await exigir_empresa_configuravel(ambito, company_id)
    # Só quem GRAVA a empresa vê os segredos dela (o Admin já não: pergunta 4b).
    if not pode_gravar_a_empresa(ambito):
        raise HTTPException(status_code=403, detail=ERRO_SO_O_CEO)
    return await run_reveal_secrets(section=section, company_id=company_id)
