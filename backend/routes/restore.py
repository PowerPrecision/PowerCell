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
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.auth import UserRole
from services.auth import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Restore"])


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
    
    Este endpoint suporta a funcionalidade de Undo no frontend.
    O processo deve ter sido eliminado via soft delete (status = 'eliminado').
    
    Args:
        process_id: ID do processo a restaurar
        
    Returns:
        O processo restaurado
    """
    # Verificar se o processo existe (pode estar "eliminado")
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        # Verificar na coleção de lixo (se existir)
        deleted_process = await db.deleted_processes.find_one({"id": process_id})
        
        if deleted_process:
            # Restaurar da coleção de lixo
            restored_process = deleted_process.copy()
            restored_process["status"] = "clientes_espera"  # Ou o status original
            restored_process["is_active"] = True
            restored_process["restored_at"] = datetime.now(timezone.utc).isoformat()
            restored_process["restored_by"] = user["id"]
            
            # Inserir de volta na coleção principal
            await db.processes.insert_one(restored_process)
            
            # Remover da coleção de lixo
            await db.deleted_processes.delete_one({"id": process_id})
            
            # Log
            await db.history.insert_one({
                "id": str(__import__('uuid').uuid4()),
                "process_id": process_id,
                "user_id": user["id"],
                "user_name": user.get("name"),
                "action": "Processo restaurado (undo)",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            # Remover _id para resposta
            if "_id" in restored_process:
                del restored_process["_id"]
            
            return {
                "success": True,
                "message": "Processo restaurado com sucesso",
                "process": restored_process
            }
        
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Se o processo existe mas está marcado como eliminado
    if process.get("status") == "eliminado" or not process.get("is_active", True):
        # Restaurar
        update_data = {
            "status": "clientes_espera",  # Ou manter o status original
            "is_active": True,
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "restored_by": user["id"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.processes.update_one(
            {"id": process_id},
            {"$set": update_data}
        )
        
        # Log
        await db.history.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "process_id": process_id,
            "user_id": user["id"],
            "user_name": user.get("name"),
            "action": "Processo restaurado (undo)",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        updated = await db.processes.find_one({"id": process_id}, {"_id": 0})
        
        return {
            "success": True,
            "message": "Processo restaurado com sucesso",
            "process": updated
        }
    
    # Processo já está ativo
    raise HTTPException(
        status_code=400, 
        detail="Processo já está ativo e não precisa de restauração"
    )


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
