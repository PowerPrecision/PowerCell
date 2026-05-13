"""
====================================================================
SERVIÇO DE PERMISSÕES — POWERCELL CRM
====================================================================
Fonte canónica de permissões com suporte a capabilities granulares.

ARQUITETURA DUAL:
- Formato LEGADO: { pages: [], actions: [] } — mantido para compatibilidade
- Formato NOVO:   { capabilities: { CAP_KEY: bool } } — sistema granular

A função resolve_capability() no models/permissions.py é a fonte de
verdade para verificação de acesso. Este serviço fornece funções
de alto nível para gestão (CRUD, sincronização, validação).
====================================================================
"""

from typing import Dict, List, Any, Optional
from models.permissions import (
    CAPABILITIES,
    CATEGORIES,
    SUPER_ADMIN_ROLES,
    ROLE_CAPABILITY_DEFAULTS,
    ACTION_TO_CAPABILITY_MAP,
    get_all_capabilities,
    get_capabilities_by_category,
    get_role_defaults,
    resolve_capability,
    validate_capabilities,
    migrate_legacy_permissions,
)


# ====================================================================
# LEGACY: Páginas e Ações (mantido para compatibilidade)
# ====================================================================

AVAILABLE_PAGES = [
    "dashboard", "kanban", "processes", "clients", "registrations",
    "documents", "calendar", "notifications", "stats", "users",
    "workflow", "automation", "email_search", "ai_insights", "system_config",
    "properties", "minutas", "validades", "rgpd", "backups",
    "logs", "diagnostics", "background_jobs", "leads", "permissions",
    "form_manager", "my_clients", "webmail", "rascunhos",
]

AVAILABLE_ACTIONS = [
    "create_process", "edit_process", "delete_process",
    "create_client", "edit_client", "delete_client",
    "upload_docs", "delete_docs", "manage_users",
    "view_financials", "export_data", "assign_clients",
    "manage_backups", "view_logs", "manage_properties",
    "manage_minutas", "manage_leads", "manage_rgpd",
    "manage_workflow", "manage_automation", "view_reports",
    "manage_ai", "manage_tasks", "use_chat",
    "assign_process_users", "download_docs", "view_drafts", "manage_drafts",
]

# Permissões padrão por role (formato legado)
DEFAULT_PERMISSIONS_BY_ROLE: Dict[str, Dict[str, List[str]]] = {
    "admin": {
        "pages": AVAILABLE_PAGES.copy(),
        "actions": AVAILABLE_ACTIONS.copy(),
    },
    "ceo": {
        "pages": AVAILABLE_PAGES.copy(),
        "actions": AVAILABLE_ACTIONS.copy(),
    },
    "diretor": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "stats", "email_search", "ai_insights",
            "properties", "minutas", "validades", "leads", "rascunhos"
        ],
        "actions": [
            "create_process", "edit_process", "delete_process",
            "create_client", "edit_client", "delete_client",
            "upload_docs", "delete_docs", "view_financials", "export_data", "assign_clients",
            "manage_properties", "manage_minutas", "manage_leads", "view_reports",
            "view_drafts", "manage_drafts"
        ],
    },
    "consultor": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "ai_insights",
            "properties", "minutas", "leads"
        ],
        "actions": [
            "create_process", "edit_process",
            "create_client", "edit_client",
            "upload_docs", "view_financials", "export_data",
            "manage_properties", "manage_minutas"
        ],
    },
    "intermediario": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "ai_insights", "minutas"
        ],
        "actions": [
            "create_process", "edit_process",
            "create_client", "edit_client",
            "upload_docs", "view_financials", "export_data"
        ],
    },
    "administrativo": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "registrations", "validades", "rascunhos"
        ],
        "actions": [
            "create_process", "edit_process",
            "create_client", "edit_client",
            "upload_docs", "delete_docs", "export_data",
            "view_drafts", "manage_drafts"
        ],
    },
    "indexacao": {
        "pages": [
            "kanban", "processes", "clients", "documents",
            "notifications", "webmail"
        ],
        "actions": [
            "download_docs", "assign_clients", "manage_tasks", "use_chat",
            "assign_process_users", "view_financials", "create_client", "edit_client"
        ],
    },
    "cliente": {
        "pages": [],
        "actions": [],
    },
    "parceiro": {
        "pages": [],
        "actions": [],
    },
}


# ====================================================================
# FUNÇÕES LEGADAS (compatibilidade com código existente)
# ====================================================================

def get_default_permissions_for_role(role: str) -> Dict[str, List[str]]:
    """Retorna as permissões padrão para um role (formato legado)."""
    return DEFAULT_PERMISSIONS_BY_ROLE.get(role, DEFAULT_PERMISSIONS_BY_ROLE["cliente"])


def get_all_available_permissions() -> Dict[str, Any]:
    """Retorna todas as permissões disponíveis (formato legado + capabilities)."""
    return {
        "pages": AVAILABLE_PAGES.copy(),
        "actions": AVAILABLE_ACTIONS.copy(),
        "capabilities": get_all_capabilities(),
        "categories": CATEGORIES,
    }


def validate_permissions(permissions: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Valida e filtra permissões legadas, removendo entradas inválidas."""
    validated = {"pages": [], "actions": []}
    if permissions:
        if "pages" in permissions:
            validated["pages"] = [p for p in permissions["pages"] if p in AVAILABLE_PAGES]
        if "actions" in permissions:
            validated["actions"] = [a for a in permissions["actions"] if a in AVAILABLE_ACTIONS]
    return validated


def should_sync_permissions(
    current_role: str, 
    new_role: str, 
    current_permissions: Dict[str, List[str]]
) -> bool:
    """Determina se as permissões devem ser sincronizadas com o novo role."""
    if current_role == new_role:
        return False
    if not current_permissions:
        return True
    default_perms = get_default_permissions_for_role(current_role)
    if (set(current_permissions.get("pages", [])) == set(default_perms["pages"]) and
        set(current_permissions.get("actions", [])) == set(default_perms["actions"])):
        return True
    # Também sincronizar se não há capabilities (utilizador legado)
    caps = current_permissions.get("capabilities", {})
    if not caps:
        return True
    return False


def sync_permissions_with_role_defaults(
    user_permissions: Dict[str, List[str]],
    role: str
) -> Dict[str, Any]:
    """Sincroniza permissões legadas + capabilities com os padrões do role."""
    if not user_permissions or not role:
        result = get_default_permissions_for_role(role)
        result["capabilities"] = get_role_defaults(role)
        return result
    
    default_perms = get_default_permissions_for_role(role)
    
    # Mesclar legado
    merged_pages = list(set(
        default_perms.get("pages", []) + user_permissions.get("pages", [])
    ))
    merged_actions = list(set(
        default_perms.get("actions", []) + user_permissions.get("actions", [])
    ))
    
    result = validate_permissions({"pages": merged_pages, "actions": merged_actions})
    
    # Mesclar capabilities: defaults do role + overrides do utilizador
    role_caps = get_role_defaults(role)
    user_caps = user_permissions.get("capabilities") or {}
    if user_caps:
        # Manter overrides do utilizador apenas se não forem iguais ao default
        for cap_key, cap_val in user_caps.items():
            if cap_key in role_caps:
                role_caps[cap_key] = cap_val
    result["capabilities"] = role_caps
    
    return result


def get_role_display_info() -> Dict[str, Dict[str, str]]:
    """Retorna informações de exibição para cada role."""
    return {
        "admin": {"label": "Administrador do Sistema", "color": "bg-red-100 text-red-800"},
        "ceo": {"label": "CEO", "color": "bg-yellow-100 text-yellow-950"},
        "diretor": {"label": "Diretor(a)", "color": "bg-purple-100 text-purple-800"},
        "consultor": {"label": "Consultor(a)", "color": "bg-blue-100 text-blue-800"},
        "intermediario": {"label": "Intermediário de Crédito", "color": "bg-cyan-100 text-cyan-800"},
        "administrativo": {"label": "Apoio Administrativo", "color": "bg-orange-100 text-orange-800"},
        "indexacao": {"label": "Indexação de Dados", "color": "bg-slate-100 text-slate-800"},
        "cliente": {"label": "Cliente", "color": "bg-gray-100 text-gray-800"},
        "parceiro": {"label": "Parceiro", "color": "bg-violet-100 text-violet-800"},
    }


# ====================================================================
# FUNÇÕES DE CAPABILITIES (novo formato granular)
# ====================================================================

def get_user_capabilities(user: dict) -> Dict[str, bool]:
    """
    Retorna as capabilities efetivas de um utilizador (resolvidas).
    Combina role defaults + user overrides.
    """
    role = user.get("role", "")
    
    # Super Admin: tudo true
    if role in SUPER_ADMIN_ROLES:
        return {key: True for key in CAPABILITIES.keys()}
    
    # Começar com defaults do role
    effective = get_role_defaults(role)
    
    # Aplicar overrides do utilizador
    permissions = user.get("permissions") or {}
    user_caps = permissions.get("capabilities") or {}
    
    # Se não há capabilities, tentar migrar do formato legado
    if not user_caps:
        user_caps = migrate_legacy_permissions(permissions)
    
    for cap_key, cap_val in user_caps.items():
        if cap_key in CAPABILITIES:
            effective[cap_key] = bool(cap_val)
    
    return effective


def build_permissions_document(
    role: str,
    capabilities_override: Optional[Dict[str, bool]] = None
) -> Dict[str, Any]:
    """
    Constrói o documento completo de permissões para guardar no MongoDB.
    Inclui formato legado (pages/actions) e novo (capabilities).
    """
    legacy_perms = get_default_permissions_for_role(role)
    cap_defaults = get_role_defaults(role)
    
    # Aplicar overrides de capabilities
    if capabilities_override:
        validated_overrides = validate_capabilities(capabilities_override)
        cap_defaults.update(validated_overrides)
    
    return {
        "pages": legacy_perms.get("pages", []),
        "actions": legacy_perms.get("actions", []),
        "capabilities": cap_defaults,
    }
