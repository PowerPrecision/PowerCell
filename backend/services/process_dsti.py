"""
Orquestração DSTI (GET /dsti/{id} e /dsti-alerts).

Extraído de `routes/processes.py`.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from database import db


async def run_get_process_dsti(
    process_id: str,
    user: dict,
    *,
    can_view_fn,
) -> dict[str, Any]:
    """Calcula DSTI de um processo (ou 403 se feature desligada)."""
    from services.config_da_empresa import config_do_processo
    from services.dsti_service import calculate_dsti, get_risk_label

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    if not can_view_fn(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Os limiares são da EMPRESA do processo (Flavio, Nov 2026, pergunta 6a).
    config = await config_do_processo(process, bd=db)
    if not config.dsti_analysis.enabled:
        raise HTTPException(
            status_code=403,
            detail="Análise DSTI automática desactivada pela empresa",
        )

    result = calculate_dsti(process)
    result["process_id"] = process_id
    result["process_number"] = process.get("process_number")
    result["client_name"] = process.get("client_name")
    result["high_risk_threshold"] = config.dsti_analysis.high_risk_threshold
    result["critical_risk_threshold"] = config.dsti_analysis.critical_risk_threshold
    result["risk_label"] = get_risk_label(result["risk_level"])
    return result


def build_dsti_high_risk_row(proc: dict, dsti_result: dict) -> dict[str, Any]:
    return {
        "process_id": proc.get("id"),
        "process_number": proc.get("process_number"),
        "client_name": proc.get("client_name"),
        "status": proc.get("status"),
        "dsti_pct": dsti_result["dsti_pct"],
        "effort_rate_pct": dsti_result["effort_rate_pct"],
        "risk_level": dsti_result["risk_level"],
        "risk_color": dsti_result["risk_color"],
        "prestacao_creditos": dsti_result["components"]["prestacao_creditos_mensal"],
        "rendimento_bruto": dsti_result["components"]["rendimento_bruto_total"],
    }


async def run_get_dsti_high_risk_processes(user: Optional[dict] = None) -> dict[str, Any]:
    """Lista processos acima do limiar DSTI configurado."""
    from services.config_da_empresa import empresa_do_processo
    from services.dsti_service import calculate_dsti, is_high_risk
    from services.system_config import get_system_config
    from services.tenant_network import CAMPOS_EMPRESA

    # Cada processo usa os limiares da SUA empresa (pergunta 6a). O limiar
    # devolvido no topo é o da global, só para o ecrã ter um número de referência.
    config = await get_system_config()
    threshold = config.dsti_analysis.high_risk_threshold
    # Fronteira de rede (Bloco A).
    from services.tenant_network import build_tenant_process_condition, com_isolamento
    processes = await db.processes.find(
        com_isolamento(
            await build_tenant_process_condition(user or {}),
            {"financial_data.rendimento_bruto_mensal": {"$gt": 0}},
        ),
        {
            "_id": 0, "id": 1, "process_number": 1, "client_name": 1,
            "financial_data": 1, "personal_data": 1, "status": 1,
            **{c: 1 for c in CAMPOS_EMPRESA},
        },
    ).to_list(length=500)

    configs: dict[str, Any] = {}
    algum_activo = False
    high_risk = []
    for proc in processes:
        empresa = await empresa_do_processo(proc, bd=db)
        if empresa not in configs:
            configs[empresa] = (await get_system_config(empresa)).dsti_analysis
        dsti_cfg = configs[empresa]
        if not dsti_cfg.enabled:
            continue
        algum_activo = True
        dsti_result = calculate_dsti(proc)
        if is_high_risk(dsti_result, dsti_cfg.high_risk_threshold):
            high_risk.append(build_dsti_high_risk_row(proc, dsti_result))

    if not algum_activo and not config.dsti_analysis.enabled:
        return {"enabled": False, "processes": [], "total": 0}

    high_risk.sort(key=lambda x: x["dsti_pct"], reverse=True)
    return {
        "enabled": True,
        "threshold": threshold,
        "processes": high_risk,
        "total": len(high_risk),
    }
