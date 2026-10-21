"""Handlers da API do módulo Index (Lote 12, Fase 3) — `/api/index/*`.

A rota (`routes/index_module.py`) é um stub fino: autoriza o VERBO (`require_roles`),
a fronteira de rede é do router (`exigir_processo_no_ambito`, 404 igual ao de «não existe»)
e o estado fechado do processo também (`exigir_processo_editavel`, nas escritas).

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Nada aqui bloqueia a indexação.** Analisar devolve já (`task_id`); IA em baixo, campos em
   dúvida ou alertas abertos nunca são erro para quem clica.
2. **Listas POSITIVAS** (DTO): a fila e a bancada mostram o que o ecrã precisa, nunca o
   documento do processo (`extra="allow"`, já vazou dados por aí). A fila NÃO leva os
   metadados profissionais; a bancada leva-os, porque é quem os revê.
3. **A fila segue o âmbito de PROCESSOS** (dono + convidadas, `build_tenant_process_condition`):
   um Index da rede A nunca lista nem abre um processo da rede B, e o directório de entidades
   patronais é global PORQUE não leva dados de clientes (só NIF e nome da empresa).
4. **O estado lê-se do documento** (`index_status.derivar_estado`), nunca de um diff.
5. **Um erro de edição é 422 com motivo**, nunca um 500; um alerta que não é DESTE processo
   é 404 (o id de um alerta alheio não se confirma).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from models.task_log import TaskType
from services import index_jobs
from services import index_status as estado_do_index
from services import index_store as store
from services.index_ai import TIPOS_ANALISADOS, tipo_de_analise
from services.tenant_network import build_tenant_process_condition, com_isolamento

logger = logging.getLogger(__name__)

ABAS = ("pending", "reviews")

PROJECCAO_DA_FILA = {
    "_id": 0, "id": 1, "process_number": 1, "client_name": 1, "status": 1, "created_at": 1,
    "updated_at": 1, "index_status": 1, "index_skipped": 1, "is_indexed": 1, "skip_index": 1,
    "assigned_indexacao_id": 1, "has_pending_review": 1, "index_alerts_open": 1,
    "indexed_at": 1, "indexed_by_name": 1,
}
PROJECCAO_DOS_FICHEIROS = {
    "_id": 0, "id": 1, "process_id": 1, "filename": 1, "s3_path": 1, "ai_category": 1,
    "ai_subcategory": 1, "ai_subtype": 1, "analysis_fingerprint": 1, "file_state": 1,
    "in_index_queue": 1, "created_at": 1, "clean_pdf_path": 1, "purge_after": 1, "is_clean_pdf": 1,
    "uploaded_by_index": 1,
}


def _ficheiro_dto(doc: dict) -> dict[str, Any]:
    # o PDF limpo não se analisa: os factos vivem nos originais (senão contavam-se duas vezes)
    tipo = None if doc.get("is_clean_pdf") else tipo_de_analise(
        doc.get("ai_category"), doc.get("ai_subcategory"), doc.get("filename"))
    return {
        "id": doc.get("id"),
        "filename": doc.get("filename"),
        "path": doc.get("s3_path"),
        "category": doc.get("ai_category"),
        "subcategory": doc.get("ai_subcategory"),
        "subtype": doc.get("ai_subtype"),
        "analysis_type": tipo if tipo in TIPOS_ANALISADOS else None,
        "analysed": bool(doc.get("analysis_fingerprint")),
        "file_state": doc.get("file_state") or "original",
        "in_index_queue": bool(doc.get("in_index_queue")),
        "has_clean_pdf": bool(doc.get("clean_pdf_path")),
        "is_clean_pdf": bool(doc.get("is_clean_pdf")),
        "uploaded_by_index": bool(doc.get("uploaded_by_index")),
        "purge_after": doc.get("purge_after"),
        "created_at": doc.get("created_at"),
    }


def _processo_dto(proc: dict, ficheiros: Optional[list[dict]] = None) -> dict[str, Any]:
    estado = estado_do_index.derivar_estado(proc)
    saida = {
        "id": proc.get("id"),
        "process_number": proc.get("process_number"),
        "client_name": proc.get("client_name"),
        "status": proc.get("status"),
        "created_at": proc.get("created_at"),
        "updated_at": proc.get("updated_at"),
        "index_status": estado["index_status"],
        "index_skipped": estado["index_skipped"],
        "has_pending_review": bool(proc.get("has_pending_review")),
        "index_alerts_open": int(proc.get("index_alerts_open") or 0),
        "indexed_at": proc.get("indexed_at"),
        "indexed_by_name": proc.get("indexed_by_name"),
    }
    if ficheiros is not None:
        saida["documents_total"] = len(ficheiros)
        saida["documents_to_analyse"] = sum(
            1 for f in ficheiros if f["analysis_type"] and not f["analysed"] and f["file_state"] != "purgado"
        )
    return saida


async def _carregar_processo(process_id: str, user: dict) -> dict:
    """O processo, já dentro do âmbito (o router o garantiu); 404 se não existe."""
    proc = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0, **{k: 1 for k in (
            "id", "process_number", "client_name", "status", "created_at", "updated_at", "index_status",
            "index_skipped", "is_indexed", "skip_index", "assigned_indexacao_id", "has_pending_review",
            "index_alerts_open", "indexed_at", "indexed_by_name", "network_id")}},
    )
    if not proc:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return proc


# ====================================================================
# A FILA
# ====================================================================
async def run_get_index_queue(
    user: dict, *, tab: str, page: int = 1, size: int = 25, q: Optional[str] = None
) -> dict[str, Any]:
    if tab not in ABAS:
        raise HTTPException(status_code=400, detail="Separador inválido")
    rede = await build_tenant_process_condition(user)
    consulta = com_isolamento(rede, {"is_deleted": {"$ne": True}, **estado_do_index.condicao_da_fila(tab)})
    texto = (q or "").strip()
    if texto:
        import re

        consulta = {"$and": [consulta, {"$or": [
            {"client_name": {"$regex": re.escape(texto), "$options": "i"}},
            {"process_number": {"$regex": re.escape(texto), "$options": "i"}},
        ]}]}
    ordem = [("created_at", 1)] if tab == "pending" else [("indexed_at", -1)]
    total = await db.processes.count_documents(consulta)
    pagina = max(1, page)
    tamanho = max(1, min(size, 100))
    processos = await (
        db.processes.find(consulta, PROJECCAO_DA_FILA).sort(ordem).skip((pagina - 1) * tamanho).limit(tamanho)
    ).to_list(tamanho)

    ids = [p["id"] for p in processos]
    por_processo: dict[str, list[dict]] = {i: [] for i in ids}
    if ids:
        docs = await db.document_metadata.find(
            {"process_id": {"$in": ids}, "file_state": {"$ne": "purgado"}}, PROJECCAO_DOS_FICHEIROS
        ).to_list(5000)
        for d in docs:
            por_processo.setdefault(d.get("process_id"), []).append(_ficheiro_dto(d))
    return {
        "items": [_processo_dto(p, por_processo.get(p["id"], [])) for p in processos],
        "total": total,
        "page": pagina,
        "size": tamanho,
        "tab": tab,
    }


# ====================================================================
# A BANCADA (workstation)
# ====================================================================
async def run_get_index_workstation(user: dict, process_id: str) -> dict[str, Any]:
    proc = await _carregar_processo(process_id, user)
    docs = await db.document_metadata.find(
        {"process_id": process_id, "file_state": {"$ne": "purgado"}}, PROJECCAO_DOS_FICHEIROS
    ).to_list(500)
    ficheiros = [_ficheiro_dto(d) for d in docs]
    metadados = await store.carregar_metadados(process_id)
    alertas = await store.alertas_do_processo(process_id)
    jobs = {}
    for nome, tipo in (("analysis", TaskType.INDEX_ANALYSIS), ("finalize", TaskType.INDEX_FINALIZE),
                       ("sanitize", TaskType.INDEX_SANITIZE)):
        activo = await index_jobs.job_activo(process_id, tipo)
        jobs[nome] = (activo or {}).get("task_id")
    return {
        "process": _processo_dto(proc, ficheiros),
        "files": ficheiros,
        "professional_metadata": {
            "jobs": (metadados or {}).get("jobs") or [],
            "has_pending_review": bool((metadados or {}).get("has_pending_review")),
            "updated_at": (metadados or {}).get("updated_at"),
        },
        "alerts": [
            {"id": a.get("id"), "code": a.get("code"), "severity": a.get("severity"), "message": a.get("message"),
             "refs": a.get("refs") or [], "dismissed": bool(a.get("dismissed_by_human")), "period": a.get("periodo")}
            for a in alertas
        ],
        "active_jobs": jobs,
    }


# ====================================================================
# ACÇÕES
# ====================================================================
async def run_claim_process(user: dict, process_id: str) -> dict[str, Any]:
    await _carregar_processo(process_id, user)
    resultado = await estado_do_index.reivindicar(process_id)
    return {"success": True, **resultado}


async def run_release_process(user: dict, process_id: str) -> dict[str, Any]:
    await _carregar_processo(process_id, user)
    resultado = await estado_do_index.devolver_a_fila(process_id)
    return {"success": True, **resultado}


async def run_analyze_process(user: dict, process_id: str, *, force: bool = False) -> dict[str, Any]:
    """«Analisar» (`force=False`: só o que é novo ou mudou) e «Extrair dados» (`force=True`: tudo)."""
    await _carregar_processo(process_id, user)
    resultado = await index_jobs.iniciar_analise(process_id, user, force=force, gatilho="manual")
    return {
        "success": True,
        "task_id": resultado["task_id"],
        "started": resultado["iniciado"],
        "message": (
            "A análise está a correr em segundo plano; recebe uma notificação no fim."
            if resultado["iniciado"] else "Já há uma análise a correr neste processo."
        ),
    }


async def run_sanitize_process(user: dict, process_id: str) -> dict[str, Any]:
    """«Apagar metadados do PDF»: PDF limpo dos ficheiros que o Index carregou. Corre em segundo plano."""
    from services import index_sanitize

    await _carregar_processo(process_id, user)
    resultado = await index_sanitize.iniciar_sanitizacao(process_id, user)
    return {
        "success": True,
        "task_id": resultado["task_id"],
        "started": resultado["iniciado"],
        "message": (
            "Os PDFs limpos estão a ser gerados em segundo plano; recebe uma notificação no fim. "
            "Os originais só são eliminados passada a margem de segurança."
            if resultado["iniciado"] else "Já há uma limpeza de PDFs a correr neste processo."
        ),
    }


async def run_edit_professional_job(
    user: dict, process_id: str, job_id: str, alteracoes: dict[str, Any]
) -> dict[str, Any]:
    proc = await _carregar_processo(process_id, user)
    try:
        modelo = await store.editar_trabalho(process_id, proc.get("network_id"), job_id, alteracoes)
    except store.EdicaoInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await estado_do_index.gravar_contadores(process_id, has_pending_review=modelo.has_pending_review)
    await _auditar(user, process_id, "Metadados profissionais editados", sorted(alteracoes))
    alvo = next((j for j in modelo.jobs if j.job_id == job_id), None)
    return {
        "success": True,
        "job": alvo.model_dump(mode="json") if alvo else None,
        "has_pending_review": modelo.has_pending_review,
    }


async def run_dismiss_alert(user: dict, process_id: str, alert_id: str) -> dict[str, Any]:
    await _carregar_processo(process_id, user)
    alerta = await store.dispensar_alerta(process_id, alert_id, user.get("id"))
    if alerta is None:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    abertos = await store.contar_alertas_abertos(process_id)
    await estado_do_index.gravar_contadores(process_id, index_alerts_open=abertos)
    await _auditar(user, process_id, "Alerta do Index dispensado", [alerta.get("code") or ""])
    return {"success": True, "alerts_open": abertos}


async def run_search_employers(user: dict, q: str) -> dict[str, Any]:
    return {"items": await store.procurar_entidades(q)}


async def _auditar(user: dict, process_id: str, accao: str, campos: list[str]) -> None:
    """Rasto de auditoria SÓ com nomes de campos/códigos, nunca valores. Nunca levanta."""
    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id=process_id, user=user, action=accao, field=", ".join(campos) or None,
            metadata={"origem": "index"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Auditoria não gravada: %s", type(exc).__name__)
