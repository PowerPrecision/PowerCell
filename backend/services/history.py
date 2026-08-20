import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from database import db

logger = logging.getLogger(__name__)


# ================================================================
# PACOTE BJ — STEALTH MODE (INDEXAÇÃO INVISÍVEL + SWITCH GLOBAL)
# ================================================================
# Utilizadores com role "indexacao" NÃO registam ações no histórico/
# atividades — atuam de forma totalmente silenciosa no mural do processo.
#
# Para além disso, qualquer utilizador pode ser silenciado individualmente
# via a propriedade `track_history` (default True quando a chave não
# existe). Isto permite desligar o rasto de um utilizador específico sem
# afetar o restante comportamento do sistema.
#
# O audit_trail (audit_trail_service.py) é INTENCIONALMENTE EXCLUÍDO deste
# stealth mode: é um trilho de compliance (com IP, justificações e retention
# policy configurável pelo admin) que deve manter rastreabilidade mesmo
# quando o histórico visível ao utilizador é silenciado.
# ================================================================
def _is_stealth_user(user: dict) -> bool:
    """
    Verifica se o utilizador deve ser silenciado no histórico/atividades.

    Regras (PACOTE BJ):
    1. role == "indexacao"  →  sempre silencioso (modo fantasma).
    2. track_history == False  →  silencioso (switch global por utilizador).
    3. track_history ausente  →  assume-se True (default não-silencioso).

    Args:
        user: Dicionário do utilizador autenticado (pode ser None).

    Returns:
        True se o utilizador NÃO deve deixar rasto no histórico; False caso contrário.
    """
    if not user:
        return False
    # Regra 1: indexacao é sempre silenciosa
    if user.get("role") == "indexacao":
        return True
    # Regra 2: switch global track_history (default True quando ausente)
    if user.get("track_history", True) is False:
        return True
    return False


async def log_history(process_id: str, user: dict, action: str, field: str = None, old_value: Any = None, new_value: Any = None):
    """Log a change to process history"""
    # ================================================================
    # PACOTE BJ — STEALTH MODE (early return de segurança)
    # ================================================================
    # Se o utilizador for "indexacao" OU tiver track_history=False,
    # a função retorna IMEDIATAMENTE sem escrever na coleção history.
    # Isto garante que ações do departamento de Indexação (e qualquer
    # utilizador silenciado) não poluam o histórico do cliente.
    # ================================================================
    if _is_stealth_user(user):
        logger.debug(
            f"[HISTORY] Stealth mode — registo bloqueado: "
            f"action={action!r}, user={user.get('email') or user.get('id')}, "
            f"role={user.get('role')}, track_history={user.get('track_history', True)}, "
            f"process={process_id}"
        )
        return

    # ================================================================
    # PACOTE D — INDEXADOR SILENCIOSO EM DOCUMENTOS (legacy, mantido)
    # ================================================================
    # Barra de bloqueio específica para carregamento/eliminação de
    # documentos: se a ação for de upload_document ou delete_document
    # E o utilizador tiver role de "indexacao", o sistema NÃO cria o
    # registo na coleção de histórico/atividades. O indexador atua de
    # forma totalmente silenciosa no mural do processo.
    #
    # NOTA (Pacote BJ): Esta barreira é agora REDUNDANTE porque o early
    # return acima (_is_stealth_user) já bloqueia TODAS as ações do
    # indexacao. Mantém-se intencionalmente como defesa em profundidade:
    # se alguém alterar a regra do stealth mode no futuro, o silêncio em
    # documentos mantém-se.
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
        logging.getLogger(__name__).warning(f"Erro ao registar histórico: {e}")


async def log_data_changes(process_id: str, user: dict, old_data: dict, new_data: dict, section: str):
    """Compare and log changes between old and new data"""
    # ================================================================
    # PACOTE BJ — STEALTH MODE (early return de segurança)
    # ================================================================
    # Mesmo guard do log_history: se o utilizador for "indexacao" OU
    # tiver track_history=False, retorna IMEDIATAMENTE sem percorrer
    # o diff nem chamar log_history. Evita trabalho desnecessário e
    # garante consistência (não faria sentido silenciar o log_history
    # mas deixar o loop de diff correr).
    # ================================================================
    if _is_stealth_user(user):
        logger.debug(
            f"[HISTORY] Stealth mode (log_data_changes) — diff bloqueado: "
            f"section={section!r}, user={user.get('email') or user.get('id')}, "
            f"role={user.get('role')}, track_history={user.get('track_history', True)}, "
            f"process={process_id}"
        )
        return

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


# ================================================================
# PACOTE DS — Histórico rico (quem / o quê / quando / detalhes)
# ================================================================
# Os documentos na coleção `history` guardam action/field/old/new em
# separado. A UI de auditoria precisa de uma frase legível
# (ex: "Fase alterada de X para Y") e de um tipo de evento para ícones.
# Estas funções são puras — usadas pelo GET /history e pela timeline.
# ================================================================

_STATUS_FIELDS = {"status", "estado", "fase"}
_ASSIGNMENT_FIELDS = {
    "consultor", "mediador", "assigned", "assigned_consultor_id",
    "assigned_mediador_id", "assigned_indexacao_id", "assigned_parceiro_id",
}


def _stringify_history_value(value: Any) -> str:
    """Valor de auditoria legível (nunca devolve None)."""
    if value is None or value == "":
        return "—"
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)
    return str(value)


def classify_history_event(item: dict | None) -> str:
    """Classifica um registo de histórico para ícones / filtros da UI."""
    item = item or {}
    action = str(item.get("action") or "").lower()
    field = str(item.get("field") or "").lower()

    if item.get("comment") or "coment" in action:
        return "comment"
    if field in _STATUS_FIELDS or "estado" in action or "fase" in action or action.startswith("moveu processo"):
        return "status_change"
    if any(token in action for token in ("documento", "document", "carregou", "upload", "eliminou documento")):
        return "document"
    if "email" in action or "e-mail" in action:
        return "email"
    if "atribu" in action or field in _ASSIGNMENT_FIELDS:
        return "assignment"
    if "tarefa" in action or field == "tarefa":
        return "task"
    if action.startswith("criou processo"):
        return "created"
    if field:
        return "edit"
    return "other"


def build_history_description(item: dict | None) -> str:
    """Frase humana da alteração — 'Fase alterada de X para Y', etc."""
    item = item or {}
    action = str(item.get("action") or "").strip() or "Atualização"
    field = item.get("field")
    old_value = item.get("old_value")
    new_value = item.get("new_value")
    event_type = classify_history_event(item)
    has_old = old_value not in (None, "")
    has_new = new_value not in (None, "")

    if event_type == "status_change" and (has_old or has_new):
        return (
            f"Fase alterada de {_stringify_history_value(old_value)} "
            f"para {_stringify_history_value(new_value)}"
        )

    if has_old and has_new:
        field_label = field or "valor"
        return f"{action}: {field_label} alterado de {old_value} para {new_value}"

    if has_new and not has_old:
        if field:
            return f"{action}: {field} → {new_value}"
        return f"{action}: {new_value}"

    if has_old and not has_new:
        field_label = field or "valor"
        return f"{action}: {field_label} removido (era {old_value})"

    comment = item.get("comment")
    if comment:
        return str(comment)

    return action


def enrich_history_entry(item: dict | None) -> dict:
    """Normaliza um documento da coleção `history` para a API de auditoria."""
    src = dict(item or {})
    src.pop("_id", None)

    created_at = src.get("created_at")
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        src["created_at"] = created_at.isoformat()
    elif created_at is None:
        src["created_at"] = ""
    else:
        src["created_at"] = str(created_at)

    src["action"] = src.get("action") or "Atualização"
    src["user_name"] = src.get("user_name") or "Sistema"
    src["event_type"] = classify_history_event(src)
    src["description"] = build_history_description(src)
    return src
