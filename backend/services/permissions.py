"""
Serviço de Permissões - PowerCell

Define permissões padrão por role e sincronização automática.
"""

from typing import Dict, List, Any


# Páginas disponíveis no sistema
AVAILABLE_PAGES = [
    "dashboard",
    "kanban", 
    "processes",
    "clients",
    "registrations",
    "documents",
    "calendar",
    "notifications",
    "stats",
    "users",
    "workflow",
    "automation",
    "email_search",
    "ai_insights",
    "system_config",
]

# Ações disponíveis no sistema
AVAILABLE_ACTIONS = [
    "create_process",
    "edit_process",
    "delete_process",
    "create_client",
    "edit_client", 
    "delete_client",
    "upload_docs",
    "delete_docs",
    "manage_users",
    "view_financials",
    "export_data",
    "assign_clients",
]

# Permissões padrão por role
# Cada role tem um conjunto de páginas visíveis e ações permitidas
DEFAULT_PERMISSIONS_BY_ROLE: Dict[str, Dict[str, List[str]]] = {
    "admin": {
        "pages": AVAILABLE_PAGES.copy(),  # Acesso total
        "actions": AVAILABLE_ACTIONS.copy(),  # Todas as ações
    },
    "ceo": {
        "pages": AVAILABLE_PAGES.copy(),  # Acesso total
        "actions": AVAILABLE_ACTIONS.copy(),  # Todas as ações
    },
    "diretor": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "stats", "email_search", "ai_insights"
        ],
        "actions": [
            "create_process", "edit_process", "delete_process",
            "create_client", "edit_client", "delete_client",
            "upload_docs", "delete_docs", "view_financials", "export_data", "assign_clients"
        ],
    },
    "consultor": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "ai_insights"
        ],
        "actions": [
            "create_process", "edit_process",
            "create_client", "edit_client",
            "upload_docs", "view_financials", "export_data"
        ],
    },
    "intermediario": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "ai_insights"
        ],
        "actions": [
            "create_process", "edit_process",
            "create_client", "edit_client",
            "upload_docs", "view_financials", "export_data"
        ],
    },
    "mediador": {
        "pages": [
            "dashboard", "kanban", "processes", "clients", "documents",
            "calendar", "notifications", "ai_insights"
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
            "calendar", "notifications", "registrations"
        ],
        "actions": [
            "create_process", "edit_process",
            "create_client", "edit_client",
            "upload_docs", "delete_docs", "export_data"
        ],
    },
    "gestor_documentos": {
        "pages": [
            "dashboard", "processes", "documents", "notifications"
        ],
        "actions": [
            "upload_docs", "delete_docs"
        ],
    },
    "indexacao": {
        "pages": [
            "dashboard", "processes", "documents", "notifications"
        ],
        "actions": [
            "upload_docs", "delete_docs"
        ],
    },
    "cliente": {
        "pages": [],  # Clientes não acedem ao sistema
        "actions": [],
    },
}


def get_default_permissions_for_role(role: str) -> Dict[str, List[str]]:
    """
    Retorna as permissões padrão para um role específico.
    
    Args:
        role: O role do utilizador (admin, ceo, consultor, etc.)
        
    Returns:
        Dict com 'pages' e 'actions' permitidas
    """
    return DEFAULT_PERMISSIONS_BY_ROLE.get(role, DEFAULT_PERMISSIONS_BY_ROLE["cliente"])


def get_all_available_permissions() -> Dict[str, Any]:
    """
    Retorna todas as permissões disponíveis no sistema.
    
    Returns:
        Dict com todas as páginas e ações disponíveis
    """
    return {
        "pages": AVAILABLE_PAGES.copy(),
        "actions": AVAILABLE_ACTIONS.copy(),
    }


def validate_permissions(permissions: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Valida e filtra permissões, removendo entradas inválidas.
    
    Args:
        permissions: Dict com 'pages' e 'actions' a validar
        
    Returns:
        Dict filtrado com apenas permissões válidas
    """
    validated = {
        "pages": [],
        "actions": [],
    }
    
    if permissions:
        # Filtrar páginas válidas
        if "pages" in permissions:
            validated["pages"] = [p for p in permissions["pages"] if p in AVAILABLE_PAGES]
        
        # Filtrar ações válidas
        if "actions" in permissions:
            validated["actions"] = [a for a in permissions["actions"] if a in AVAILABLE_ACTIONS]
    
    return validated


def should_sync_permissions(
    current_role: str, 
    new_role: str, 
    current_permissions: Dict[str, List[str]]
) -> bool:
    """
    Determina se as permissões devem ser sincronizadas com o novo role.
    
    As permissões são sincronizadas quando:
    1. O role mudou
    2. E o utilizador não tem permissões personalizadas (override)
    
    Args:
        current_role: Role atual do utilizador
        new_role: Novo role a atribuir
        current_permissions: Permissões atuais do utilizador
        
    Returns:
        True se as permissões devem ser sincronizadas
    """
    # Se o role não mudou, não sincronizar
    if current_role == new_role:
        return False
    
    # Se não há permissões atuais, sincronizar
    if not current_permissions:
        return True
    
    # Obter permissões padrão do role atual
    default_perms = get_default_permissions_for_role(current_role)
    
    # Se as permissões atuais são iguais às padrão, o utilizador não personalizou
    # Neste caso, sincronizar com o novo role
    if (set(current_permissions.get("pages", [])) == set(default_perms["pages"]) and
        set(current_permissions.get("actions", [])) == set(default_perms["actions"])):
        return True
    
    # Se as permissões foram personalizadas, não alterar automaticamente
    # O admin pode optar por redefinir manualmente
    return False


def get_role_display_info() -> Dict[str, Dict[str, str]]:
    """
    Retorna informações de exibição para cada role.
    
    Returns:
        Dict com label e cor para cada role
    """
    return {
        "admin": {"label": "Administrador", "color": "bg-red-100 text-red-800"},
        "ceo": {"label": "CEO", "color": "bg-purple-100 text-purple-800"},
        "diretor": {"label": "Diretor", "color": "bg-blue-100 text-blue-800"},
        "consultor": {"label": "Consultor", "color": "bg-green-100 text-green-800"},
        "mediador": {"label": "Mediador", "color": "bg-teal-100 text-teal-800"},
        "intermediario": {"label": "Intermediário", "color": "bg-cyan-100 text-cyan-800"},
        "administrativo": {"label": "Administrativo", "color": "bg-amber-100 text-amber-800"},
        "gestor_documentos": {"label": "Gestor Documentos", "color": "bg-slate-100 text-slate-800"},
        "indexacao": {"label": "Indexação", "color": "bg-gray-100 text-gray-800"},
        "cliente": {"label": "Cliente", "color": "bg-neutral-100 text-neutral-800"},
    }
