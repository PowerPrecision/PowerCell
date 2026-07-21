"""
Constantes de estado de processos e regras de visibilidade partilhadas.

Extraído de `routes/processes.py` para reduzir o tamanho desse módulo e
permitir testes unitários isolados da lógica de visibilidade do pré-registo.
"""
from typing import Optional

from models.auth import UserRole

# ====================================================================
# CONSTANTES DE FILTRO DE ESTADO ATIVO
# ====================================================================
# Status que representam processos terminados (não ativos)
INACTIVE_STATUSES = ["concluidos", "desistencias", "eliminados"]
# Status de processos arquivados (para histórico)
ARCHIVED_STATUSES = ["concluidos", "desistencias"]

# ====================================================================
# PACOTE BK — EXCLUSÃO DO ESTADO pré_registo DOS QUADROS DE TRABALHO
# ====================================================================
# Processos em "pre_registo" (cliente ainda a preencher no portal) NÃO
# devem aparecer nos quadros de trabalho da equipa (Kanban, listagens,
# my-clients) para não gerar ruído. A exclusão aplica-se a TODOS os
# roles, MAS admins/CEO/diretor/administrativo podem contorná-la:
#   1. Pesquisando diretamente (parâmetro `search` ativo).
#   2. Filtrando explicitamente por status="pre_registo".
# ====================================================================
PRE_REGISTO_STATUS = "pre_registo"
# PACOTE DB — Valores de status que representam "Lead" (sem fase do Kanban ativo).
# Inclui "pre_registo" (legacy) e None (novos registos do formulário público).
LEAD_STATUS_VALUES = ["pre_registo", None]
# Roles com privilégios de gestão — podem contornar a exclusão do pré-registo
PRE_REGISTO_BYPASS_ROLES = {
    UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO
}


def _should_hide_pre_registo(role: str, status: Optional[str], search: Optional[str]) -> bool:
    """
    Determina se a exclusão do estado pré_registo deve aplicar-se à query.

    Regras (PACOTE BK):
    1. Admin/CEO/Diretor/Administrativo NÃO têm exclusão automática quando
       estão a pesquisar (search ativo) ou a filtrar explicitamente por
       status — podem encontrar pré-registos diretamente.
    2. Consultores, intermediários e indexação têm SEMPRE a exclusão ativa
       nos quadros de trabalho (nunca veem pré-registos).
    3. Em todos os casos, se status=="pre_registo" for passado explicitamente,
       a exclusão NÃO se aplica (o utilizador quer ver especificamente esse
       estado).

    Args:
        role: Role do utilizador autenticado.
        status: Filtro de status explícito do query string (None se não especificado).
        search: Termo de pesquisa do query string (None ou "" se não especificado).

    Returns:
        True se a query deve excluir pré_registo; False caso contrário.
    """
    # Regra 3: filtro explícito por pré_registo → nunca excluir
    if status == PRE_REGISTO_STATUS:
        return False
    # Regra 1: roles com bypass — excluem pré-registo SÓ quando não há
    # pesquisa ativa nem filtro de status explícito
    if role in PRE_REGISTO_BYPASS_ROLES:
        if search or status:
            return False
        return True
    # Regra 2: consultores, intermediários, indexação, cliente — sempre excluem
    return True
