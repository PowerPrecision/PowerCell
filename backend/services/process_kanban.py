"""
====================================================================
SERVIÇO KANBAN DE PROCESSOS - CREDITOIMO
====================================================================
Lógica de negócio específica para visualização e movimentação
no quadro Kanban.
====================================================================
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict

from database import db
from services.process_service import build_query_filter, get_user_name

logger = logging.getLogger(__name__)


# ==== CONFIGURAÇÃO DO KANBAN ====

# Workflow de 14 fases definidas
KANBAN_COLUMNS = [
    {"id": "clientes_espera", "name": "Clientes em Espera", "color": "#6B7280"},
    {"id": "fase_documental", "name": "Fase Documental", "color": "#F59E0B"},
    {"id": "fase_documental_ii", "name": "Fase Documental II", "color": "#EAB308"},
    {"id": "enviado_bruno", "name": "Enviado ao Bruno", "color": "#8B5CF6"},
    {"id": "enviado_luis", "name": "Enviado ao Luís", "color": "#A855F7"},
    {"id": "enviado_bcp_rui", "name": "Enviado BCP Rui", "color": "#EC4899"},
    {"id": "entradas_precision", "name": "Entradas Precision", "color": "#3B82F6"},
    {"id": "fase_bancaria", "name": "Fase Bancária", "color": "#0EA5E9"},
    {"id": "fase_visitas", "name": "Fase de Visitas", "color": "#14B8A6"},
    {"id": "ch_aprovado", "name": "CH Aprovado", "color": "#22C55E"},
    {"id": "fase_escritura", "name": "Fase de Escritura", "color": "#84CC16"},
    {"id": "escritura_agendada", "name": "Escritura Agendada", "color": "#10B981"},
    {"id": "concluidos", "name": "Concluídos", "color": "#059669"},
    {"id": "desistencias", "name": "Desistências", "color": "#EF4444"},
]

VALID_STATUSES = {col["id"] for col in KANBAN_COLUMNS}


def get_kanban_columns() -> List[dict]:
    """Retorna a configuração das colunas do Kanban."""
    return KANBAN_COLUMNS.copy()


def is_valid_status(status: str) -> bool:
    """Verifica se um status é válido."""
    return status in VALID_STATUSES


# ==== DADOS PARA O QUADRO KANBAN ====

async def get_kanban_data(
    user: dict,
    include_user_names: bool = True
) -> Dict[str, List[dict]]:
    """
    Obtém dados organizados para o quadro Kanban.
    
    Args:
        user: Utilizador actual
        include_user_names: Se deve incluir nomes de consultores/mediadores
        
    Returns:
        Dict com colunas como chaves e listas de processos como valores
    """
    query = build_query_filter(user)
    
    cursor = db.processes.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_ref": 1,
            "client_name": 1,
            "client_email": 1,
            "client_phone": 1,
            "status": 1,
            "priority": 1,
            "consultant_id": 1,
            "mediador_id": 1,
            "process_type": 1,
            "service_type": 1,
            "updated_at": 1,
            "created_at": 1,
            "notes": 1,
            "tags": 1,
        }
    ).sort("updated_at", -1)
    
    processes = await cursor.to_list(length=1000)
    
    # Organizar por coluna
    kanban_data = defaultdict(list)
    
    # Cache de nomes de utilizadores
    user_cache = {}
    
    for process in processes:
        status = process.get("status", "clientes_espera")
        
        # Garantir que o status é válido
        if status not in VALID_STATUSES:
            status = "clientes_espera"
        
        # Adicionar nomes se necessário
        if include_user_names:
            consultant_id = process.get("consultant_id")
            mediador_id = process.get("mediador_id")
            
            if consultant_id:
                if consultant_id not in user_cache:
                    user_cache[consultant_id] = await get_user_name(consultant_id)
                process["consultant_name"] = user_cache[consultant_id]
            
            if mediador_id:
                if mediador_id not in user_cache:
                    user_cache[mediador_id] = await get_user_name(mediador_id)
                process["mediador_name"] = user_cache[mediador_id]
        
        kanban_data[status].append(process)
    
    return dict(kanban_data)


async def get_kanban_response(user: dict) -> dict:
    """
    Prepara resposta completa para o frontend do Kanban.
    
    Args:
        user: Utilizador actual
        
    Returns:
        Dict com columns (config) e processes (dados por coluna)
    """
    kanban_data = await get_kanban_data(user)
    
    return {
        "columns": get_kanban_columns(),
        "processes": kanban_data,
        "total_count": sum(len(v) for v in kanban_data.values())
    }


# ==== MOVIMENTAÇÃO NO KANBAN ====

async def move_process(
    process_id: str,
    new_status: str,
    user: dict,
    position: Optional[int] = None
) -> Tuple[bool, dict, str]:
    """
    Move um processo para uma nova coluna do Kanban.
    
    Args:
        process_id: ID do processo
        new_status: Novo status/coluna
        user: Utilizador que está a mover
        position: Posição na nova coluna (opcional)
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    # Validar status
    if not is_valid_status(new_status):
        return False, {}, f"Status inválido: {new_status}"
    
    # Obter processo atual
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return False, {}, "Processo não encontrado"
    
    old_status = process.get("status", "clientes_espera")
    
    if old_status == new_status:
        return True, {"status": new_status}, "Processo já está nesta coluna"
    
    # Preparar atualização
    update_data = {
        "status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Adicionar entrada no histórico
    history_entry = {
        "action": "status_change",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user.get("id"),
        "user_name": user.get("name", "Sistema"),
        "details": f"Movido de '{old_status}' para '{new_status}'"
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {
            "$set": update_data,
            "$push": {"history": history_entry}
        }
    )
    
    if result.modified_count == 0:
        return False, {}, "Erro ao mover processo"
    
    # Obter nomes das colunas para mensagem
    old_name = next((c["name"] for c in KANBAN_COLUMNS if c["id"] == old_status), old_status)
    new_name = next((c["name"] for c in KANBAN_COLUMNS if c["id"] == new_status), new_status)
    
    return True, {
        "old_status": old_status,
        "new_status": new_status,
        "old_column_name": old_name,
        "new_column_name": new_name
    }, f"Processo movido de '{old_name}' para '{new_name}'"


# ==== ESTATÍSTICAS DO KANBAN ====

async def get_kanban_stats(user: dict) -> dict:
    """
    Obtém estatísticas do Kanban.
    
    Args:
        user: Utilizador actual
        
    Returns:
        Dict com contagens por coluna e totais
    """
    query = build_query_filter(user)
    
    # Agregar por status
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    
    cursor = db.processes.aggregate(pipeline)
    results = await cursor.to_list(length=50)
    
    # Organizar resultados
    stats_by_status = {r["_id"]: r["count"] for r in results}
    
    # Construir resposta com todas as colunas
    column_stats = []
    total = 0
    
    for column in KANBAN_COLUMNS:
        count = stats_by_status.get(column["id"], 0)
        total += count
        column_stats.append({
            "id": column["id"],
            "name": column["name"],
            "count": count,
            "color": column["color"]
        })
    
    return {
        "columns": column_stats,
        "total": total
    }
