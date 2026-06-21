"""
====================================================================
ROTAS DE RESTAURAÇÃO (UNDO) - CREDITOIMO
====================================================================
Endpoints para restaurar itens eliminados, suportando a 
funcionalidade de Undo no frontend.

Endpoints:
- POST /processes/{id}/restore - Restaurar processo eliminado
- POST /documents/{id}/restore - Restaurar documento eliminado
====================================================================
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.auth import UserRole
from services.auth import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Restore"])


# Estados considerados terminais — um processo restaurado com um destes
# status fica is_active=False; qualquer outro status fica is_active=True.
_TERMINAL_STATUSES = ("concluido", "desistencia", "desistencias", "arquivo", "perdido")


# ====================================================================
# RESTAURAR PROCESSO
# ====================================================================

@router.post("/processes/{process_id}/restore")
async def restore_process(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR]))
):
    """
    Restaura um processo que foi eliminado (soft delete).

    Inverte o ``DELETE /api/processes/{process_id}``:
      - Coloca ``is_deleted: False`` (o bug crítico que impedia o processo
        de reaparecer nas queries com ``{"is_deleted": {"$ne": True}}``).
      - Restaura o ``previous_status`` guardado no delete (ou fall-back
        ``clientes_espera`` se não existir — processos eliminados antes
        do Pacote K não têm previous_status).
      - Recalcula ``is_active`` com base no status restaurado.
      - Cascade: restaura documentos e tarefas do processo que foram
        soft-deletados no mesmo delete.
      - Regista atividade em ``process_activities`` (tipo ``process_restored``)
        para simetria com o ``process_deleted`` do delete.

    Args:
        process_id: ID do processo a restaurar.

    Returns:
        Dict com success, message e o processo restaurado.
    """
    # Procurar o processo (inclui eliminados — NÃO filtrar is_deleted aqui)
    process = await db.processes.find_one({"id": process_id})

    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # Só restaurar se o processo está realmente eliminado
    is_deleted = process.get("is_deleted", False)
    status = process.get("status", "")
    if not is_deleted and status != "eliminado":
        raise HTTPException(
            status_code=400,
            detail="Processo não está eliminado — não precisa de restauração"
        )

    now = datetime.now(timezone.utc)

    # Restaurar o status anterior se guardado, senão usar clientes_espera
    previous_status = process.get("previous_status") or "clientes_espera"
    # Se o previous_status era "eliminado" (caso de double-delete), usar fallback
    if previous_status == "eliminado":
        previous_status = "clientes_espera"

    restored_is_active = previous_status not in _TERMINAL_STATUSES

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "is_deleted": False,
            "status": previous_status,
            "is_active": restored_is_active,
            "restored_at": now,
            "restored_by": user.get("id", ""),
            "updated_at": now,
        }}
    )

    # Cascade: restaurar documentos e tarefas que foram soft-deletados
    # juntamente com o processo (o delete faz cascade com is_deleted=True).
    await db.documents.update_many(
        {"process_id": process_id, "is_deleted": True},
        {"$set": {
            "deleted": False,
            "is_deleted": False,
            "deleted_at": None,
        }}
    )
    await db.tasks.update_many(
        {"process_id": process_id, "is_deleted": True},
        {"$set": {
            "deleted": False,
            "is_deleted": False,
            "deleted_at": None,
        }}
    )

    # Log de atividade (simétrico ao process_deleted do delete endpoint)
    await db.process_activities.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "type": "process_restored",
        "description": f"Processo restaurado por {user.get('name', 'Utilizador')}",
        "created_at": now,
        "user_id": user.get("id", ""),
        "user_name": user.get("name", ""),
    })

    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})

    return {
        "success": True,
        "message": "Processo restaurado com sucesso",
        "process": updated
    }



# ====================================================================
# RESTAURAR DOCUMENTO
# ====================================================================

@router.post("/documents/{document_id}/restore")
async def restore_document(
    document_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO]))
):
    """
    Restaura um documento que foi eliminado.
    
    Este endpoint suporta a funcionalidade de Undo no frontend.
    
    Args:
        document_id: ID do documento a restaurar
        
    Returns:
        O documento restaurado
    """
    # Verificar se o documento existe na coleção principal
    document = await db.documents.find_one({"id": document_id})
    
    if document:
        if not document.get("deleted", False):
            raise HTTPException(
                status_code=400,
                detail="Documento não está eliminado"
            )
        
        # Restaurar documento
        await db.documents.update_one(
            {"id": document_id},
            {"$set": {
                "deleted": False,
                "deleted_at": None,
                "restored_at": datetime.now(timezone.utc).isoformat(),
                "restored_by": user["id"]
            }}
        )
        
        # Log
        await db.history.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "process_id": document.get("process_id"),
            "user_id": user["id"],
            "user_name": user.get("name"),
            "action": f"Documento restaurado: {document.get('filename', document_id)}",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        updated = await db.documents.find_one({"id": document_id}, {"_id": 0})
        
        return {
            "success": True,
            "message": "Documento restaurado com sucesso",
            "document": updated
        }
    
    # Verificar na coleção de lixo
    deleted_doc = await db.deleted_documents.find_one({"id": document_id})
    
    if deleted_doc:
        # Restaurar da coleção de lixo
        restored_doc = deleted_doc.copy()
        restored_doc["deleted"] = False
        restored_doc["restored_at"] = datetime.now(timezone.utc).isoformat()
        restored_doc["restored_by"] = user["id"]
        
        # Inserir de volta na coleção principal
        await db.documents.insert_one(restored_doc)
        
        # Remover da coleção de lixo
        await db.deleted_documents.delete_one({"id": document_id})
        
        # Log
        await db.history.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "process_id": deleted_doc.get("process_id"),
            "user_id": user["id"],
            "user_name": user.get("name"),
            "action": f"Documento restaurado do lixo: {deleted_doc.get('filename', document_id)}",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        if "_id" in restored_doc:
            del restored_doc["_id"]
        
        return {
            "success": True,
            "message": "Documento restaurado com sucesso",
            "document": restored_doc
        }
    
    raise HTTPException(status_code=404, detail="Documento não encontrado")


# ====================================================================
# RESTAURAR TAREFA
# ====================================================================

@router.post("/tasks/{task_id}/restore")
async def restore_task(
    task_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO]))
):
    """
    Restaura uma tarefa eliminada.
    """
    # Similar ao documento
    task = await db.tasks.find_one({"id": task_id})
    
    if task:
        if not task.get("deleted", False):
            raise HTTPException(
                status_code=400,
                detail="Tarefa não está eliminada"
            )
        
        await db.tasks.update_one(
            {"id": task_id},
            {"$set": {
                "deleted": False,
                "deleted_at": None,
                "restored_at": datetime.now(timezone.utc).isoformat(),
                "restored_by": user["id"]
            }}
        )
        
        updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
        
        return {
            "success": True,
            "message": "Tarefa restaurada com sucesso",
            "task": updated
        }
    
    raise HTTPException(status_code=404, detail="Tarefa não encontrada")


# ====================================================================
# HISTÓRICO DE ELIMINAÇÕES (para undo)
# ====================================================================

@router.get("/deleted/items")
async def list_deleted_items(
    item_type: str = "all",  # all, processes, documents, tasks
    limit: int = 50,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Lista itens eliminados recentemente que podem ser restaurados.
    """
    items = []
    
    if item_type in ["all", "processes"]:
        # Processos eliminados
        deleted_processes = await db.processes.find(
            {"status": "eliminado", "is_active": False},
            {"_id": 0}
        ).sort("updated_at", -1).limit(limit).to_list(limit)
        
        for p in deleted_processes:
            items.append({
                "type": "process",
                "id": p["id"],
                "name": p.get("client_name", "Sem nome"),
                "deleted_at": p.get("updated_at"),
                "can_restore": True
            })
    
    if item_type in ["all", "documents"]:
        # Documentos eliminados
        deleted_docs = await db.documents.find(
            {"deleted": True},
            {"_id": 0}
        ).sort("deleted_at", -1).limit(limit).to_list(limit)
        
        for d in deleted_docs:
            items.append({
                "type": "document",
                "id": d["id"],
                "name": d.get("filename", "Sem nome"),
                "deleted_at": d.get("deleted_at"),
                "can_restore": True
            })
    
    if item_type in ["all", "tasks"]:
        # Tarefas eliminadas
        deleted_tasks = await db.tasks.find(
            {"deleted": True},
            {"_id": 0}
        ).sort("deleted_at", -1).limit(limit).to_list(limit)
        
        for t in deleted_tasks:
            items.append({
                "type": "task",
                "id": t["id"],
                "name": t.get("title", "Sem título"),
                "deleted_at": t.get("deleted_at"),
                "can_restore": True
            })
    
    return {
        "items": items,
        "total": len(items)
    }
