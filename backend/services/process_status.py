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
# Fix: Normalize process status filters to handle legacy singular and
# plural values.
#
# O schema de `status` evoluiu ao longo do tempo sem migração retroactiva,
# pelo que a BD tem uma mistura de valores singular/plural para o mesmo
# estado "lógico" (ex.: "eliminado" vs "eliminados", "concluido" vs
# "concluidos"). Uma comparação de igualdade estrita ou uma lista `$nin`/`$in`
# com apenas UMA das variações falha SILENCIOSAMENTE para documentos legados
# — não há erro, apenas processos a aparecer/desaparecer do filtro errado
# (ex.: "Processos Ativos" a mostrar processos "eliminado" (singular) porque
# só "eliminados" (plural) estava excluído; "Eliminados" a não mostrar nada
# porque a query só procurava "eliminados" (plural) e os documentos tinham
# "eliminado" (singular), ou vice-versa).
#
# `STATUS_VALUE_ALIASES` documenta TODAS as variações legadas conhecidas
# para cada estado terminal e é a fonte única de verdade para qualquer
# filtro `$in`/`$nin` sobre estes estados — nunca hard-code apenas uma
# variação num novo filtro.
STATUS_VALUE_ALIASES: dict[str, list[str]] = {
    "eliminado": ["eliminado", "eliminados"],
    "eliminados": ["eliminado", "eliminados"],
    "concluido": ["concluido", "concluidos"],
    "concluidos": ["concluido", "concluidos"],
    "desistencia": ["desistencia", "desistencias", "desistido"],
    "desistencias": ["desistencia", "desistencias", "desistido"],
    "desistido": ["desistencia", "desistencias", "desistido"],
    "cancelado": ["cancelado"],
    "perdido": ["perdido"],
    "arquivo": ["arquivo"],
}

# Todas as variações (singular + plural) do estado "eliminado". Usado por
# qualquer filtro que precise de reconhecer processos soft-deleted através
# do campo `status` (defesa em profundidade a par da flag `is_deleted`).
DELETED_STATUS_VALUES = STATUS_VALUE_ALIASES["eliminados"]


def expand_status_values(status: Optional[str]) -> list[str]:
    """
    Devolve todas as variações legadas conhecidas para um valor de status.

    Se `status` não tiver variações documentadas (ex.: fases activas do
    Kanban como "escritura"), devolve `[status]` — um filtro `$in` com uma
    única entrada é equivalente a uma comparação de igualdade.
    """
    if not status:
        return []
    return STATUS_VALUE_ALIASES.get(status, [status])


# Status que representam processos terminados (não ativos). Inclui TODAS
# as variações singular/plural documentadas em `STATUS_VALUE_ALIASES` para
# cada estado terminal — o filtro "Ativos" (`$nin`) tem de excluir qualquer
# uma delas, nunca apenas a forma canónica.
INACTIVE_STATUSES = [
    "eliminado", "eliminados",
    "concluido", "concluidos",
    "desistencia", "desistencias", "desistido",
    "cancelado",
    "perdido",
    "arquivo",
]
# Status de processos arquivados (para histórico) — concluídos/desistências,
# incluindo variações singular/plural. Não inclui "eliminado(s)": esse é um
# estado de soft-delete gerido separadamente pela flag `is_deleted`.
ARCHIVED_STATUSES = [
    "concluido", "concluidos",
    "desistencia", "desistencias", "desistido",
]

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
