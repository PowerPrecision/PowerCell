"""
Helpers para GET /processes/{id}.

Extraído de `routes/processes.py` — latest_activity (PACOTE DA) e
portal_access (PACOTE DC).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def load_process_doc_or_404(process_id: str) -> dict:
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return process


def assert_can_view_process_or_403(user: dict, process: dict, can_view_fn) -> None:
    if not can_view_fn(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")


async def attach_latest_activity(process: dict, process_id: str) -> None:
    """PACOTE DA — injecta latest_activity (última nota com comment)."""
    try:
        latest_act = await db.activities.find_one(
            {"process_id": process_id, "comment": {"$exists": True, "$ne": ""}},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        process["latest_activity"] = latest_act
    except Exception as e:
        logger.warning(
            f"[GET-PROCESS] Erro ao buscar latest_activity para {process_id}: {e}"
        )
        process["latest_activity"] = None


async def attach_portal_access(process: dict, process_id: str) -> None:
    """PACOTE DC — código de acesso + magic link activo."""
    try:
        portal_access_code = None
        client_id = process.get("client_id")
        if client_id:
            client_doc = await db.clients.find_one(
                {"id": client_id}, {"portal_access_code": 1, "_id": 0},
            )
            if client_doc:
                portal_access_code = client_doc.get("portal_access_code")

        active_short_id = None
        active_magic_link = None
        token_doc = await db.portal_tokens.find_one(
            {"process_id": process_id},
            {"_id": 0, "short_id": 1, "created_at": 1},
        )
        if token_doc and token_doc.get("short_id"):
            active_short_id = token_doc["short_id"]
            fe_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            if fe_url:
                active_magic_link = f"{fe_url}/portal/{active_short_id}"

        process["portal_access"] = {
            "portal_access_code": portal_access_code,
            "short_id": active_short_id,
            "magic_link": active_magic_link,
            "has_active_token": active_short_id is not None,
        }
    except Exception as e:
        logger.warning(
            f"[GET-PROCESS] Erro ao buscar portal_access para {process_id}: {e}"
        )
        process["portal_access"] = None


def ensure_client_id_default(process: dict) -> None:
    process.setdefault("client_id", process.get("client_id") or "")


def serialize_process_detail_response(process: dict, process_id: str) -> Any:
    """ProcessResponse ou dict fallback se validação falhar."""
    from models.process import ProcessResponse
    try:
        return ProcessResponse(**process)
    except Exception as e:
        logger.warning(
            f"Erro de validação ProcessResponse para processo {process_id}: {e}"
        )
        return process


def build_portal_access_payload(
    *,
    portal_access_code: Optional[str],
    short_id: Optional[str],
    frontend_url: str,
) -> dict:
    """Constrói o dict portal_access (testável sem DB)."""
    magic_link = None
    fe = (frontend_url or "").rstrip("/")
    if short_id and fe:
        magic_link = f"{fe}/portal/{short_id}"
    return {
        "portal_access_code": portal_access_code,
        "short_id": short_id,
        "magic_link": magic_link,
        "has_active_token": short_id is not None,
    }


async def anexar_permissao_de_ia(process: dict, user: dict, request) -> None:
    """`pode_usar_ia_documentos`: a resposta do SERVIDOR à pergunta «este utilizador
    pode usar a IA manual sobre os documentos deste processo?», calculada ao servir.

    É a MESMA função que as rotas de IA aplicam (`document_ai_access`: só os altos
    perfis, dentro da fronteira de rede), para o botão e o 403 nunca divergirem.
    Nunca levanta. Se a pergunta falha o campo FICA POR PREENCHER: o ecrã então
    decide só pelo cargo (que já exclui os perfis operacionais) — um `False` por
    erro tiraria o botão à gestão por um soluço da base de dados — e o servidor
    continua a ser a parede.
    """
    try:
        from services.document_ai_access import pode_usar_ia_no_processo

        process["pode_usar_ia_documentos"] = await pode_usar_ia_no_processo(
            request, user, process
        )
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning("[DOCS-IA] Não foi possível calcular a permissão de IA: %s", exc)
        process.pop("pode_usar_ia_documentos", None)


async def anexar_permissao_de_documentos(process: dict, user: dict) -> None:
    """`pode_ver_documentos`: a resposta do SERVIDOR à pergunta «este utilizador pode
    ler os documentos (e os pedidos do Portal) deste processo?», calculada ao servir.

    É a MESMA guarda que as rotas de documentos aplicam
    (`assert_can_view_process_documents`): um processo por indexar só mostra os
    documentos a quem o indexa ou está atribuído. Sem isto, o ecrã pedia
    `/documents/portal-requests/{id}` à mesma, levava o 403 que a regra manda dar
    e deixava um erro vermelho na consola (e um aviso ao utilizador) por um pedido
    que não devia ter sido feito. Nunca levanta; se a pergunta falha o campo FICA
    POR PREENCHER e o ecrã pede à mesma (o servidor continua a ser a parede).
    """
    from fastapi import HTTPException

    try:
        from services.document_visibility import assert_can_view_process_documents

        await assert_can_view_process_documents(user, process)
        process["pode_ver_documentos"] = True
    except HTTPException:
        process["pode_ver_documentos"] = False
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning("[DOCS] Não foi possível calcular a visibilidade dos documentos: %s", exc)
        process.pop("pode_ver_documentos", None)


async def run_get_process_detail(
    process_id: str,
    user: dict,
    *,
    can_view_fn,
    decrypt_fn,
    populate_fn,
    request=None,
) -> Any:
    """Orquestra GET /processes/{id}."""
    process = await load_process_doc_or_404(process_id)
    assert_can_view_process_or_403(user, process, can_view_fn)
    process = decrypt_fn(process)
    process = await populate_fn(process)
    ensure_client_id_default(process)
    await attach_latest_activity(process, process_id)
    await attach_portal_access(process, process_id)
    # A empresa dona, para a etiqueta do cabeçalho (processos partilhados B2B).
    from services.process_owner import anexar_empresa_dona

    await anexar_empresa_dona(process, user)
    # Linhagem Parceiro → Y → Z (partilha em cadeia): deriva do registo de partilhas,
    # nunca gravada. Depois da empresa dona, de onde tira o nome da casa dona.
    from services.process_lineage import anexar_linhagem

    await anexar_linhagem(
        process, user,
        casa_dona=str((process.get("empresa_dona") or {}).get("company_name") or ""),
    )
    await anexar_permissao_de_ia(process, user, request)
    await anexar_permissao_de_documentos(process, user)
    return serialize_process_detail_response(process, process_id)


def build_process_alerts_payload(process_id: str, process: dict, alerts: list) -> dict:
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "alerts": alerts,
        "total": len(alerts),
        "has_critical": any(a.get("priority") == "critical" for a in alerts),
        "has_high": any(a.get("priority") == "high" for a in alerts),
    }


async def run_get_process_alerts(
    process_id: str,
    user: dict,
    *,
    can_view_fn,
    get_alerts_fn,
) -> dict:
    """Orquestra GET /processes/{id}/alerts."""
    from fastapi import HTTPException

    from database import db

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    if not can_view_fn(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")

    alerts = await get_alerts_fn(process)
    return build_process_alerts_payload(process_id, process, alerts)
