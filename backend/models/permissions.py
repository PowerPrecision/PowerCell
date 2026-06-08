"""
====================================================================
MODELO DE PERMISSÕES GRANULARES — POWERCELL CRM
====================================================================
Fonte canónica de capabilities, categorias e defaults por cargo.

LISTA DEFINITIVA DE 8 PERFIS: admin, ceo, diretor, administrativo,
consultor, intermediario, indexacao, parceiro.

ARQUITETURA:
- CAPABILITIES: Dict[str, CapabilityMeta] — registo de todas as
  ações atómicas do sistema, agrupadas por categoria.
- CATEGORIES: Lista de categorias com metadados visuais.
- ROLE_CAPABILITY_DEFAULTS: Dict[role, Dict[capability, bool]] —
  mapeamento de quais capabilities cada cargo tem por padrão.
- SUPER_ADMIN_ROLES: Roles com bypass total (sempre true).
- Resolução: has_capability(user, cap) = bypass? → true,
  override? → override, fallback → role_default.

COMPATIBILIDADE:
- O campo legado permissions.actions é mapeado para capabilities
  via ACTION_TO_CAPABILITY_MAP para migração suave.
====================================================================
"""

from typing import Dict, List, Any, Optional


# ====================================================================
# SUPER ADMIN BYPASS
# ====================================================================

SUPER_ADMIN_ROLES = ["admin", "ceo"]


# ====================================================================
# CATEGORIAS DE PERMISSÕES
# ====================================================================

CATEGORIES: List[Dict[str, str]] = [
    {"id": "processos",     "label": "Processos",              "icon": "FileText",     "color": "blue"},
    {"id": "clientes",      "label": "Clientes",               "icon": "Users",        "color": "emerald"},
    {"id": "documentos",    "label": "Documentos",             "icon": "FolderOpen",   "color": "amber"},
    {"id": "financeiro",    "label": "Financeiro",             "icon": "DollarSign",   "color": "green"},
    {"id": "comunicacoes",  "label": "Comunicações",           "icon": "Mail",         "color": "cyan"},
    {"id": "estatisticas",  "label": "Estatísticas",           "icon": "BarChart3",    "color": "purple"},
    {"id": "sistema",       "label": "Sistema",                "icon": "Settings",     "color": "red"},
    {"id": "utilizadores",  "label": "Gestão de Utilizadores", "icon": "UserCog",      "color": "orange"},
]


# ====================================================================
# CAPABILITIES — Registo Canónico
# ====================================================================

class CapabilityMeta:
    """Metadados de uma capability."""
    def __init__(self, label: str, category: str, icon: str, description: str):
        self.label = label
        self.category = category
        self.icon = icon
        self.description = description
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "label": self.label,
            "category": self.category,
            "icon": self.icon,
            "description": self.description,
        }


CAPABILITIES: Dict[str, CapabilityMeta] = {
    # ── PROCESSOS ──
    "PROCESS_CREATE":       CapabilityMeta("Criar Processos",         "processos",     "FilePlus",    "Criar novos processos no pipeline"),
    "PROCESS_EDIT":         CapabilityMeta("Editar Processos",        "processos",     "FileEdit",    "Editar dados de processos existentes"),
    "PROCESS_DELETE":       CapabilityMeta("Apagar Processos",        "processos",     "FileX",       "Eliminar processos permanentemente"),
    "PROCESS_VIEW_ALL":     CapabilityMeta("Ver Todos os Processos",  "processos",     "Files",       "Ver processos de outros consultores"),
    "PROCESS_EXPORT":       CapabilityMeta("Exportar Processos",      "processos",     "Download",    "Exportar lista de processos (CSV/Excel)"),
    "PROCESS_ASSIGN":       CapabilityMeta("Atribuir Processos",      "processos",     "UserPlus",    "Atribuir consultores/intermediários a processos"),
    
    # ── CLIENTES ──
    "CLIENT_CREATE":        CapabilityMeta("Criar Clientes",          "clientes",      "UserPlus",    "Registar novos clientes no sistema"),
    "CLIENT_EDIT":          CapabilityMeta("Editar Clientes",         "clientes",      "UserCog",     "Editar dados de clientes"),
    "CLIENT_DELETE":        CapabilityMeta("Apagar Clientes",         "clientes",      "UserX",       "Eliminar clientes do sistema"),
    "CLIENT_VIEW_ALL":      CapabilityMeta("Ver Todos os Clientes",   "clientes",      "Users",       "Ver clientes de outros consultores"),
    "CLIENT_EXPORT":        CapabilityMeta("Exportar Clientes",       "clientes",      "Download",    "Exportar lista de clientes (CSV/Excel)"),
    
    # ── DOCUMENTOS ──
    "DOCUMENT_UPLOAD":      CapabilityMeta("Upload Documentos",       "documentos",    "Upload",      "Carregar documentos para processos"),
    "DOCUMENT_DELETE":      CapabilityMeta("Apagar Documentos",       "documentos",    "FileX",       "Eliminar documentos do sistema"),
    "DOCUMENT_DOWNLOAD":    CapabilityMeta("Descarregar Documentos",  "documentos",    "Download",    "Descarregar documentos de processos"),
    "DOCUMENT_VIEW_ALL":    CapabilityMeta("Ver Todos os Documentos", "documentos",    "FolderOpen",  "Ver documentos de qualquer processo"),
    
    # ── FINANCEIRO ──
    "FINANCE_VIEW":         CapabilityMeta("Ver Financeiro",          "financeiro",    "DollarSign",  "Aceder à página de dados financeiros"),
    "FINANCE_EDIT":         CapabilityMeta("Editar Financeiro",       "financeiro",    "Pencil",      "Editar valores e dados financeiros"),
    "FINANCE_EXPORT":       CapabilityMeta("Exportar Financeiro",     "financeiro",    "Download",    "Exportar relatórios financeiros"),
    
    # ── COMUNICAÇÕES ──
    "EMAIL_SEND":           CapabilityMeta("Enviar Emails",           "comunicacoes",  "Send",        "Enviar emails através do webmail"),
    "EMAIL_VIEW_ALL":       CapabilityMeta("Ver Todos os Emails",     "comunicacoes",  "Mail",        "Ver emails de outros utilizadores"),
    "CHAT_ACCESS":          CapabilityMeta("Chat Interno",            "comunicacoes",  "MessageSquare","Aceder ao chat interno da equipa"),
    "DRAFT_VIEW":           CapabilityMeta("Ver Rascunhos",           "comunicacoes",  "FileText",    "Aceder à página de Rascunhos (ver e consultar)"),
    "DRAFT_MANAGE":         CapabilityMeta("Gerir Rascunhos",         "comunicacoes",  "FileEdit",    "Criar, editar e eliminar rascunhos"),
    
    # ── ESTATÍSTICAS ──
    "STATS_VIEW":           CapabilityMeta("Ver Estatísticas",        "estatisticas",  "BarChart3",   "Ver dashboard de estatísticas gerais"),
    "STATS_FINANCIAL":      CapabilityMeta("Estatísticas Financeiras","estatisticas",  "TrendingUp",  "Ver relatórios financeiros detalhados"),
    "STATS_EXPORT":         CapabilityMeta("Exportar Relatórios",     "estatisticas",  "Download",    "Exportar relatórios e análise"),
    
    # ── SISTEMA ──
    "SETTINGS_EDIT":        CapabilityMeta("Editar Configurações",    "sistema",       "Settings",    "Alterar configurações do sistema"),
    "BACKUP_MANAGE":        CapabilityMeta("Gerir Backups",           "sistema",       "Shield",      "Criar e restaurar backups da BD"),
    "LOGS_VIEW":            CapabilityMeta("Ver Logs",                "sistema",       "ScrollText",  "Aceder aos logs de diagnóstico do sistema"),
    
    # ── UTILIZADORES ──
    "USER_CREATE":          CapabilityMeta("Criar Utilizadores",      "utilizadores",  "UserPlus",    "Criar novas contas de utilizador"),
    "USER_EDIT":            CapabilityMeta("Editar Utilizadores",     "utilizadores",  "UserCog",     "Editar dados e cargos de utilizadores"),
    "USER_DELETE":          CapabilityMeta("Apagar Utilizadores",     "utilizadores",  "UserX",       "Eliminar contas de utilizador"),
    "USER_IMPERSONATE":     CapabilityMeta("Ver Como Utilizador",     "utilizadores",  "Eye",         "Impersonar outro utilizador para debug"),
}


# ====================================================================
# ROLE CAPABILITY DEFAULTS — Padrão por Cargo
# ====================================================================

ROLE_CAPABILITY_DEFAULTS: Dict[str, Dict[str, bool]] = {
    "admin": {},   # SUPER_ADMIN_BYPASS — todas as capabilities são true
    "ceo": {},     # SUPER_ADMIN_BYPASS — todas as capabilities são true
    
    "diretor": {
        "PROCESS_CREATE": True,  "PROCESS_EDIT": True,    "PROCESS_DELETE": True,
        "PROCESS_VIEW_ALL": True, "PROCESS_EXPORT": True, "PROCESS_ASSIGN": True,
        "CLIENT_CREATE": True,   "CLIENT_EDIT": True,     "CLIENT_DELETE": True,
        "CLIENT_VIEW_ALL": True, "CLIENT_EXPORT": True,
        "DOCUMENT_UPLOAD": True, "DOCUMENT_DELETE": True,  "DOCUMENT_DOWNLOAD": True, "DOCUMENT_VIEW_ALL": True,
        "FINANCE_VIEW": True,    "FINANCE_EDIT": True,     "FINANCE_EXPORT": True,
        "EMAIL_SEND": True,      "EMAIL_VIEW_ALL": True,   "CHAT_ACCESS": True,
        "DRAFT_VIEW": True,      "DRAFT_MANAGE": True,
        "STATS_VIEW": True,      "STATS_FINANCIAL": True,  "STATS_EXPORT": True,
        "SETTINGS_EDIT": False,  "BACKUP_MANAGE": False,   "LOGS_VIEW": False,
        "USER_CREATE": False,    "USER_EDIT": False,       "USER_DELETE": False,  "USER_IMPERSONATE": False,
    },
    
    "administrativo": {
        "PROCESS_CREATE": True,  "PROCESS_EDIT": True,     "PROCESS_DELETE": False,
        "PROCESS_VIEW_ALL": True, "PROCESS_EXPORT": True,  "PROCESS_ASSIGN": True,
        "CLIENT_CREATE": True,   "CLIENT_EDIT": True,      "CLIENT_DELETE": False,
        "CLIENT_VIEW_ALL": True, "CLIENT_EXPORT": True,
        "DOCUMENT_UPLOAD": True, "DOCUMENT_DELETE": True,   "DOCUMENT_DOWNLOAD": True, "DOCUMENT_VIEW_ALL": True,
        "FINANCE_VIEW": False,   "FINANCE_EDIT": False,     "FINANCE_EXPORT": False,
        "EMAIL_SEND": True,      "EMAIL_VIEW_ALL": False,   "CHAT_ACCESS": True,
        "DRAFT_VIEW": True,      "DRAFT_MANAGE": True,
        "STATS_VIEW": True,      "STATS_FINANCIAL": False,  "STATS_EXPORT": False,
        "SETTINGS_EDIT": False,  "BACKUP_MANAGE": False,    "LOGS_VIEW": False,
        "USER_CREATE": False,    "USER_EDIT": False,        "USER_DELETE": False,  "USER_IMPERSONATE": False,
    },
    
    "consultor": {
        "PROCESS_CREATE": True,  "PROCESS_EDIT": True,      "PROCESS_DELETE": False,
        "PROCESS_VIEW_ALL": False, "PROCESS_EXPORT": False,  "PROCESS_ASSIGN": False,
        "CLIENT_CREATE": True,   "CLIENT_EDIT": True,       "CLIENT_DELETE": False,
        "CLIENT_VIEW_ALL": False, "CLIENT_EXPORT": False,
        "DOCUMENT_UPLOAD": True, "DOCUMENT_DELETE": False,   "DOCUMENT_DOWNLOAD": True, "DOCUMENT_VIEW_ALL": False,
        "FINANCE_VIEW": True,    "FINANCE_EDIT": False,      "FINANCE_EXPORT": False,
        "EMAIL_SEND": True,      "EMAIL_VIEW_ALL": False,    "CHAT_ACCESS": True,
        "DRAFT_VIEW": False,     "DRAFT_MANAGE": False,
        "STATS_VIEW": False,     "STATS_FINANCIAL": False,   "STATS_EXPORT": False,
        "SETTINGS_EDIT": False,  "BACKUP_MANAGE": False,     "LOGS_VIEW": False,
        "USER_CREATE": False,    "USER_EDIT": False,         "USER_DELETE": False,  "USER_IMPERSONATE": False,
    },
    
    "intermediario": {
        "PROCESS_CREATE": True,  "PROCESS_EDIT": True,      "PROCESS_DELETE": False,
        "PROCESS_VIEW_ALL": False, "PROCESS_EXPORT": False,  "PROCESS_ASSIGN": False,
        "CLIENT_CREATE": True,   "CLIENT_EDIT": True,       "CLIENT_DELETE": False,
        "CLIENT_VIEW_ALL": False, "CLIENT_EXPORT": False,
        "DOCUMENT_UPLOAD": True, "DOCUMENT_DELETE": False,   "DOCUMENT_DOWNLOAD": True, "DOCUMENT_VIEW_ALL": False,
        "FINANCE_VIEW": True,    "FINANCE_EDIT": False,      "FINANCE_EXPORT": False,
        "EMAIL_SEND": True,      "EMAIL_VIEW_ALL": False,    "CHAT_ACCESS": True,
        "DRAFT_VIEW": False,     "DRAFT_MANAGE": False,
        "STATS_VIEW": False,     "STATS_FINANCIAL": False,   "STATS_EXPORT": False,
        "SETTINGS_EDIT": False,  "BACKUP_MANAGE": False,     "LOGS_VIEW": False,
        "USER_CREATE": False,    "USER_EDIT": False,         "USER_DELETE": False,  "USER_IMPERSONATE": False,
    },
    
    "indexacao": {
        "PROCESS_CREATE": False, "PROCESS_EDIT": False,      "PROCESS_DELETE": False,
        "PROCESS_VIEW_ALL": True, "PROCESS_EXPORT": False,   "PROCESS_ASSIGN": True,
        "CLIENT_CREATE": True,   "CLIENT_EDIT": True,        "CLIENT_DELETE": False,
        "CLIENT_VIEW_ALL": True, "CLIENT_EXPORT": False,
        "DOCUMENT_UPLOAD": False, "DOCUMENT_DELETE": False,   "DOCUMENT_DOWNLOAD": True, "DOCUMENT_VIEW_ALL": True,
        "FINANCE_VIEW": False,   "FINANCE_EDIT": False,       "FINANCE_EXPORT": False,
        "EMAIL_SEND": False,     "EMAIL_VIEW_ALL": False,     "CHAT_ACCESS": True,
        "DRAFT_VIEW": False,     "DRAFT_MANAGE": False,
        "STATS_VIEW": False,     "STATS_FINANCIAL": False,    "STATS_EXPORT": False,
        "SETTINGS_EDIT": False,  "BACKUP_MANAGE": False,      "LOGS_VIEW": False,
        "USER_CREATE": False,    "USER_EDIT": False,          "USER_DELETE": False,  "USER_IMPERSONATE": False,
    },
    
    "parceiro": {},  # Utilizador fantasma — sem acesso
    "cliente": {},   # Pseudo-role — sem acesso ao sistema
}


# ====================================================================
# MAPEAMENTO LEGADO: actions → capabilities
# ====================================================================

ACTION_TO_CAPABILITY_MAP: Dict[str, str] = {
    "create_process": "PROCESS_CREATE",
    "edit_process": "PROCESS_EDIT",
    "delete_process": "PROCESS_DELETE",
    "create_client": "CLIENT_CREATE",
    "edit_client": "CLIENT_EDIT",
    "delete_client": "CLIENT_DELETE",
    "upload_docs": "DOCUMENT_UPLOAD",
    "delete_docs": "DOCUMENT_DELETE",
    "download_docs": "DOCUMENT_DOWNLOAD",
    "manage_users": "USER_CREATE",
    "view_financials": "FINANCE_VIEW",
    "export_data": "PROCESS_EXPORT",
    "assign_clients": "PROCESS_ASSIGN",
    "manage_backups": "BACKUP_MANAGE",
    "view_logs": "LOGS_VIEW",
    "manage_properties": "PROCESS_EDIT",
    "manage_minutas": "PROCESS_EDIT",
    "manage_leads": "PROCESS_EDIT",
    "manage_rgpd": "SETTINGS_EDIT",
    "manage_workflow": "SETTINGS_EDIT",
    "manage_automation": "SETTINGS_EDIT",
    "view_reports": "STATS_VIEW",
    "manage_ai": "SETTINGS_EDIT",
    "manage_tasks": "PROCESS_ASSIGN",
    "use_chat": "CHAT_ACCESS",
    "assign_process_users": "PROCESS_ASSIGN",
    "view_drafts": "DRAFT_VIEW",
    "manage_drafts": "DRAFT_MANAGE",
}


# ====================================================================
# FUNÇÕES HELPER
# ====================================================================

def get_all_capabilities() -> Dict[str, Dict[str, str]]:
    """Retorna todas as capabilities com metadados."""
    return {key: meta.to_dict() for key, meta in CAPABILITIES.items()}


def get_capabilities_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """Retorna capabilities agrupadas por categoria, com metadados."""
    result = {}
    for cat in CATEGORIES:
        cat_id = cat["id"]
        result[cat_id] = []
    
    for cap_key, meta in CAPABILITIES.items():
        if meta.category in result:
            result[meta.category].append({
                "key": cap_key,
                **meta.to_dict()
            })
    
    return result


def get_role_defaults(role: str) -> Dict[str, bool]:
    """
    Retorna as capabilities padrão para um role.
    Admin/CEO retornam todas como True (bypass).
    """
    if role in SUPER_ADMIN_ROLES:
        return {key: True for key in CAPABILITIES.keys()}
    return ROLE_CAPABILITY_DEFAULTS.get(role, {}).copy()


def resolve_capability(user: dict, capability: str) -> bool:
    """
    Resolve se um utilizador tem uma capability.
    
    Algoritmo:
    1. Se role ∈ SUPER_ADMIN_ROLES → True (bypass)
    2. Se user.permissions.capabilities[capability] existe → usar esse valor
    3. Fallback → ROLE_CAPABILITY_DEFAULTS[role][capability]
    4. Se não existe → False
    """
    if not user:
        return False
    
    role = user.get("role", "")
    
    # 1. Super Admin Bypass
    if role in SUPER_ADMIN_ROLES:
        return True
    
    # 2. User override
    permissions = user.get("permissions") or {}
    capabilities_override = permissions.get("capabilities") or {}
    if capability in capabilities_override:
        return bool(capabilities_override[capability])
    
    # 3. Role default
    role_defaults = ROLE_CAPABILITY_DEFAULTS.get(role, {})
    if capability in role_defaults:
        return bool(role_defaults[capability])
    
    # 4. Unknown capability → False
    return False


def validate_capabilities(capabilities: Dict[str, bool]) -> Dict[str, bool]:
    """Filtra capabilities inválidas, mantendo apenas as reconhecidas."""
    return {k: bool(v) for k, v in capabilities.items() if k in CAPABILITIES}


def migrate_legacy_permissions(permissions: dict) -> Dict[str, bool]:
    """
    Converte permissões legadas (pages/actions) para o formato capabilities.
    Não sobrescreve capabilities já existentes.
    """
    if not permissions:
        return {}
    
    existing_capabilities = permissions.get("capabilities") or {}
    if existing_capabilities:
        return existing_capabilities
    
    # Mapear actions legadas para capabilities
    legacy_actions = permissions.get("actions") or []
    migrated = {}
    for action in legacy_actions:
        cap = ACTION_TO_CAPABILITY_MAP.get(action)
        if cap:
            migrated[cap] = True
    
    return migrated
