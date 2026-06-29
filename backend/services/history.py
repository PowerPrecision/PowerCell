import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from database import db

logger = logging.getLogger(__name__)


async def log_history(process_id: str, user: dict, action: str, field: str = None, old_value: Any = None, new_value: Any = None):
    """Log a change to process history"""
    # ================================================================
    # PACOTE D — INDEXADOR SILENCIOSO EM DOCUMENTOS
    # ================================================================
    # Barra de bloqueio específica para carregamento/eliminação de
    # documentos: se a ação for de upload_document ou delete_document
    # E o utilizador tiver role de "indexacao", o sistema NÃO cria o
    # registo na coleção de histórico/atividades. O indexador atua de
    # forma totalmente silenciosa no mural do processo.
    #
    # Isto é uma barreira EXPLÍCITA e DOCUMENTADA (Pacote D) — complementa
    # o modo fantasma geral (ver abaixo) que silencia TODAS as ações do
    # indexador. A duplicação é intencional: se alguém remover o modo
    # fantasma geral no futuro, o silêncio em documentos mantém-se.
    # ================================================================
    _DOCUMENT_ACTION_PREFIXES = (
        "Carregou documento",       # upload_document (single + direto)
        "Eliminou documento",       # delete_document (single + massa)
    )
    if (
        user
        and user.get("role") == "indexacao"
        and action
        and action.startswith(_DOCUMENT_ACTION_PREFIXES)
    ):
        logger.debug(
            f"[HISTORY] Indexador silencioso em documento — registo bloqueado: "
            f"action={action!r}, user={user.get('email')}, process={process_id}"
        )
        return

    # ================================================================
    # INDEXAÇÃO - MODO FANTASMA (SEM HISTÓRICO)
    # Utilizadores com role "indexacao" não registam ações no histórico
    # Isto permite que possam trabalhar nos processos sem deixar rasto
    # ================================================================
    if user and user.get("role") == "indexacao":
        logger.debug(f"[HISTORY] Modo fantasma: ignorando registo para indexacao - {action}")
        return
    
    try:
        history_doc = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "user_id": user.get("id") if user else None,
            "user_name": user.get("name") if user else "Sistema",
            "action": action,
            "field": field,
            "old_value": str(old_value) if old_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.history.insert_one(history_doc)
    except Exception as e:
        # Não falhar o upload se o histórico falhar
        import logging
        logging.getLogger(__name__).warning(f"Erro ao registar histórico: {e}")


async def log_data_changes(process_id: str, user: dict, old_data: dict, new_data: dict, section: str):
    """Compare and log changes between old and new data"""
    if old_data is None:
        old_data = {}
    if new_data is None:
        return
    
    for key, new_val in new_data.items():
        old_val = old_data.get(key)
        if old_val != new_val and new_val is not None:
            await log_history(
                process_id, user, 
                f"Alterou {section}", 
                key, old_val, new_val
            )
