import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.auth import UserRole
from models.activity import ActivityCreate, ActivityResponse, HistoryResponse
from services.auth import get_current_user
from services.history import log_history


router = APIRouter(tags=["Activities"])


# ============== ACTIVITY/COMMENTS ROUTES ==============

@router.post("/activities", response_model=ActivityResponse)
async def create_activity(data: ActivityCreate, user: dict = Depends(get_current_user)):
    """Create a new activity/comment on a process"""
    process = await db.processes.find_one({"id": data.process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if user["role"] == UserRole.CLIENTE and process["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    activity_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    activity_doc = {
        "id": activity_id,
        "process_id": data.process_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "user_role": user["role"],
        "comment": data.comment,
        "created_at": now
    }
    
    await db.activities.insert_one(activity_doc)
    await log_history(data.process_id, user, "Adicionou comentário")
    
    return ActivityResponse(**{k: v for k, v in activity_doc.items() if k != "_id"})


@router.get("/activities", response_model=List[ActivityResponse])
async def get_activities(process_id: str, user: dict = Depends(get_current_user)):
    """Get all activities for a process"""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if user["role"] == UserRole.CLIENTE and process["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    activities = await db.activities.find({"process_id": process_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    # Filtrar atividades com dados válidos (podem existir registos antigos incompletos)
    valid_activities = []
    for a in activities:
        # Garantir que tem os campos obrigatórios
        if all(k in a for k in ["id", "user_id", "user_name", "user_role", "comment", "created_at"]):
            valid_activities.append(ActivityResponse(**a))
        elif "comment" in a:
            # Tentar recuperar atividade com dados parciais
            a.setdefault("user_id", "system")
            a.setdefault("user_name", "Sistema")
            a.setdefault("user_role", "admin")
            valid_activities.append(ActivityResponse(**a))
    
    return valid_activities


@router.delete("/activities/{activity_id}")
async def delete_activity(activity_id: str, user: dict = Depends(get_current_user)):
    """Delete an activity (only owner or admin)"""
    activity = await db.activities.find_one({"id": activity_id})
    if not activity:
        raise HTTPException(status_code=404, detail="Comentário não encontrado")
    
    if activity["user_id"] != user["id"] and user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Só pode eliminar os seus próprios comentários")
    
    await db.activities.delete_one({"id": activity_id})
    return {"message": "Comentário eliminado"}


# ============== HISTORY ROUTES ==============

@router.get("/history", response_model=List[HistoryResponse])
async def get_history(process_id: str, user: dict = Depends(get_current_user)):
    """Get history for a process"""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    if user["role"] == UserRole.CLIENTE and process["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    history = await db.history.find({"process_id": process_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [HistoryResponse(**h) for h in history]
