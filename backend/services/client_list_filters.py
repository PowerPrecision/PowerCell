"""
Builders de query MongoDB para filtros da entidade Cliente.

PACOTE FK — listagem de clientes independente dos processos.
Os filtros aqui só tocam campos do documento `clients` (fonte, tipo, estado).
"""
from __future__ import annotations

import re
from typing import Any, Optional


def _blank(value: Optional[str]) -> bool:
    return not value or str(value).strip() in ("", "all")


def build_client_fonte_condition(fonte: Optional[str]) -> Optional[dict]:
    """Origem do cliente — match case-insensitive no campo ``fonte``."""
    if _blank(fonte):
        return None
    value = str(fonte).strip()
    return {"fonte": {"$regex": f"^{re.escape(value)}$", "$options": "i"}}


def _titular2_present_clauses() -> list[dict]:
    nonempty = {"$regex": ".+"}
    return [
        {"titular2_data.nif": nonempty},
        {"titular2_data.name": nonempty},
        {"titular2_data.nome": nonempty},
        {"titular2_name": nonempty},
    ]


def _titular2_present_condition() -> dict:
    return {"$or": _titular2_present_clauses()}


def _titular2_absent_condition() -> dict:
    return {"$nor": _titular2_present_clauses()}


def build_client_tipo_condition(tipo: Optional[str]) -> Optional[dict]:
    """
    Tipo de cliente (não é o tipo de processo).

    - particular: sem 2º titular
    - dois_titulares: tem titular2_data / titular2_name
    - empresa: campo ``tipo`` / ``tipo_cliente`` == empresa
    Outros valores: match directo em tipo / tipo_cliente / pending_process_type.
    """
    if _blank(tipo):
        return None
    value = str(tipo).strip().lower()
    if value in ("particular", "individual"):
        return _titular2_absent_condition()
    if value in ("dois_titulares", "conjunto", "casal"):
        return _titular2_present_condition()
    if value == "empresa":
        return {"$or": [
            {"tipo": {"$regex": "^empresa$", "$options": "i"}},
            {"tipo_cliente": {"$regex": "^empresa$", "$options": "i"}},
        ]}
    return {"$or": [
        {"tipo": value},
        {"tipo_cliente": value},
        {"pending_process_type": value},
    ]}


def build_client_status_condition(status: Optional[str]) -> Optional[dict]:
    """
    Estado da ficha de cliente (não a fase do processo).

    - active / ativo: não eliminado e não marcado inactivo
    - inactive / inativo: is_active=False e não eliminado
    - deleted / eliminado: is_deleted=True
    """
    if _blank(status):
        return None
    value = str(status).strip().lower()
    if value in ("deleted", "eliminado", "eliminados"):
        return {"is_deleted": True}
    if value in ("inactive", "inativo", "inativos"):
        return {
            "is_deleted": {"$ne": True},
            "is_active": False,
        }
    if value in ("active", "ativo", "ativos"):
        return {
            "is_deleted": {"$ne": True},
            "is_active": {"$ne": False},
        }
    return None


def build_client_entity_query(
    *,
    fonte: Optional[str] = None,
    tipo: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Query MongoDB sobre a colecção ``clients``. None se nenhum filtro activo."""
    conditions: list[dict] = []
    fonte_cond = build_client_fonte_condition(fonte)
    if fonte_cond:
        conditions.append(fonte_cond)
    tipo_cond = build_client_tipo_condition(tipo)
    if tipo_cond:
        conditions.append(tipo_cond)
    status_cond = build_client_status_condition(status)
    if status_cond:
        conditions.append(status_cond)

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def client_doc_to_list_item(doc: dict) -> dict:
    """Normaliza um documento ``clients`` para o formato da listagem."""
    titular2 = doc.get("titular2_data") or {}
    has_titular2 = bool(
        (isinstance(titular2, dict) and (titular2.get("nif") or titular2.get("name") or titular2.get("nome")))
        or doc.get("titular2_name")
    )
    return {
        "id": doc.get("id"),
        "nome": doc.get("nome"),
        "contacto": doc.get("contacto") or {},
        "dados_pessoais": doc.get("dados_pessoais") or {},
        "process_ids": doc.get("process_ids") or [],
        "fonte": doc.get("fonte"),
        "tipo_cliente": doc.get("tipo") or doc.get("tipo_cliente") or (
            "dois_titulares" if has_titular2 else "particular"
        ),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "is_active": doc.get("is_active", True),
        "is_deleted": doc.get("is_deleted", False),
        "prioridade": doc.get("prioridade") or doc.get("priority") or "",
        "active_processes_count": 0,
    }
