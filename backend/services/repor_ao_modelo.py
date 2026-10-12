"""
====================================================================
«REPOR AO MODELO» — descartar a cópia própria da rede (acção DESTRUTIVA)
====================================================================
O workflow e o formulário público são POR REDE com copy-on-write: o documento
sem `network_id` é o MODELO e a rede ganha a sua cópia na primeira escrita.
Repor ao modelo é **apagar a cópia da rede**: a leitura volta a cair no modelo
(`workflow_scope`, `form_config_scope`) e uma nova edição materializa uma
cópia fresca. Nada é escrito no modelo.

PORQUE É QUE EXIGE A PASSWORD
  Perde-se, sem volta, a configuração que a rede construiu (fases, automações
  e modelos de tarefas por fase; campos personalizados e rótulos do
  formulário). O servidor exige a password ACTUAL de quem pede
  (`reauth_password`) e só então executa — o botão pedir confirmação não
  chega: o endpoint é chamável sem o ecrã.

AS REGRAS
  1. **Quem:** Master, Admin e CEO (os que editam o workflow); a rede é a
     EM CONTEXTO (404 fora do âmbito — `workflow_scope`). O Master pode pedir
     outra rede por `network_id`.
  2. **Ordem:** rede (404) → password (403/429) → estado → execução. A password
     verifica-se ANTES de se dizer se a rede tem cópia própria: sem ela, o
     endpoint seria um oráculo do estado da configuração.
  3. **Idempotente:** uma rede que já usa o modelo responde ``reposto: false``
     (nada a fazer), não um erro.
  4. **O workflow não se repõe por cima de processos em curso.** Se algum
     processo ACTIVO da rede está numa fase que o modelo não tem, repor
     deixava-o numa fase que deixa de existir: recusa-se (409) e diz-se QUAIS
     as fases e quantos processos — mover os processos é a eliminação de
     fase, que já o faz com regras próprias. O modelo vazio também se recusa.
  5. **Só se apaga o que tem `network_id` igual ao pedido**, nunca um filtro
     que possa casar com o modelo (um `network_id` vazio apagaria o modelo).
  6. **Deixa rasto** (`audit_logs`), sem a password, e o rasto nunca faz a
     operação falhar.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.admin_helpers import _audit_log
from services.form_config_scope import TIPO as TIPO_DO_FORMULARIO, tem_formulario_proprio
from services.reauth_password import exigir_password_actual
from services.tenant_network import CAMPO_REDE, build_network_scope_condition, com_isolamento, TenantScope, rede_de_omissao
from services.workflow_phases import invalidar_cache_de_fases
from services.workflow_scope import rede_em_contexto, tem_workflow_proprio

logger = logging.getLogger(__name__)

ERRO_MODELO_VAZIO = "O modelo de workflow está vazio: repor deixaria a rede sem fases."


class ReporAoModeloIn(BaseModel):
    """O corpo: a password (nunca registada) e, para o Master, a rede a repor."""

    model_config = ConfigDict(extra="forbid")

    #: `repr=False`: a password nunca aparece num log nem num traceback do Pydantic.
    password: str = Field(..., min_length=1, max_length=256, repr=False)
    network_id: Optional[str] = Field(None, max_length=120)


def _condicao_dos_processos_da_rede(rede: str) -> dict:
    return build_network_scope_condition(TenantScope(
        network_ids=(rede,), inclui_rede_de_omissao=(rede == rede_de_omissao()),
    ))


async def _fases_em_uso_fora_do_modelo(rede: str, nomes_do_modelo: set[str]) -> list[dict]:
    """``[{name, total}]`` das fases da rede com processos ACTIVOS e que o modelo não tem."""
    consulta = com_isolamento(_condicao_dos_processos_da_rede(rede), {"is_deleted": {"$ne": True}})
    usadas = [s for s in await db.processes.distinct("status", consulta) if s and s not in nomes_do_modelo]
    saida = []
    for nome in sorted(usadas):
        total = await db.processes.count_documents({**consulta, "status": nome})
        saida.append({"name": nome, "total": total})
    return saida


async def _registar(user: dict, acao: str, rede: str, detalhes: dict) -> None:
    try:
        await _audit_log(acao, "network_config", rede, user, {"network_id": rede, **detalhes})
    except Exception as exc:  # noqa: BLE001 — o rasto nunca derruba a operação
        logger.warning("[REPOR_AO_MODELO] Falha a registar %s: %s", acao, exc)


async def run_repor_workflow_ao_modelo(data: ReporAoModeloIn, user: dict, request: Optional[Request] = None) -> dict:
    rede = await rede_em_contexto(user, request, rede_pedida=data.network_id)
    await exigir_password_actual(user, data.password)

    if not await tem_workflow_proprio(rede):
        return {"reposto": False, "network_id": rede, "message": "Esta rede já usa o workflow modelo."}

    modelo = await db.workflow_statuses.find(
        {"network_id": {"$in": [None, ""]}}, {"_id": 0, "name": 1},
    ).to_list(500)
    nomes_do_modelo = {m["name"] for m in modelo if m.get("name")}
    if not nomes_do_modelo:
        raise HTTPException(status_code=409, detail=ERRO_MODELO_VAZIO)

    em_uso = await _fases_em_uso_fora_do_modelo(rede, nomes_do_modelo)
    if em_uso:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Há processos em fases que o modelo não tem. Mova-os (ou elimine essas fases, "
                    "o que os move) antes de repor ao modelo."
                ),
                "fases_em_uso": em_uso,
            },
        )

    # Só a cópia desta rede: `rede` é não vazio (resolvido acima) e o filtro nunca casa com o modelo.
    assert rede, "repor: rede vazia apagaria o modelo"
    resultado = await db.workflow_statuses.delete_many({CAMPO_REDE: rede})
    removidas = int(getattr(resultado, "deleted_count", 0) or 0)
    invalidar_cache_de_fases()
    await _registar(user, "workflow_reposto_ao_modelo", rede, {"fases_removidas": removidas})
    logger.info("[REPOR_AO_MODELO] Workflow da rede %s reposto ao modelo (%d fase(s) removidas).", rede, removidas)
    return {
        "reposto": True,
        "network_id": rede,
        "fases_removidas": removidas,
        "message": "Workflow reposto ao modelo.",
    }


async def run_repor_formulario_ao_modelo(data: ReporAoModeloIn, user: dict, request: Optional[Request] = None) -> dict:
    rede = await rede_em_contexto(user, request, rede_pedida=data.network_id)
    await exigir_password_actual(user, data.password)

    if not await tem_formulario_proprio(rede):
        return {"reposto": False, "network_id": rede, "message": "Esta rede já usa o formulário modelo."}

    assert rede, "repor: rede vazia apagaria o modelo"
    resultado = await db.form_config.delete_one({"type": TIPO_DO_FORMULARIO, CAMPO_REDE: rede})
    removido = int(getattr(resultado, "deleted_count", 0) or 0)
    await _registar(user, "formulario_reposto_ao_modelo", rede, {"removido": bool(removido)})
    logger.info("[REPOR_AO_MODELO] Formulário da rede %s reposto ao modelo.", rede)
    return {
        "reposto": bool(removido),
        "network_id": rede,
        "message": "Formulário reposto ao modelo.",
    }


__all__ = [
    "ERRO_MODELO_VAZIO",
    "ReporAoModeloIn",
    "run_repor_formulario_ao_modelo",
    "run_repor_workflow_ao_modelo",
]
