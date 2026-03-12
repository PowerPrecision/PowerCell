import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.auth import UserRole
from models.deadline import DeadlineCreate, DeadlineUpdate, DeadlineResponse
from services.auth import get_current_user, require_roles
from services.notification_service import send_notification_with_preference_check, send_deadline_reminder
from services.history import log_history


router = APIRouter(prefix="/deadlines", tags=["Deadlines"])


@router.post("", response_model=DeadlineResponse)
async def create_deadline(data: DeadlineCreate, user: dict = Depends(get_current_user)):
    """
    Criar um novo evento/prazo no calendário.
    
    - Todos os utilizadores (exceto clientes) podem criar eventos
    - O evento é sempre atribuído ao próprio utilizador
    - Pode também ser atribuído a outros utilizadores (lista)
    """
    if user["role"] == UserRole.CLIENTE:
        raise HTTPException(status_code=403, detail="Clientes não podem criar prazos")
    
    process = None
    if data.process_id:
        process = await db.processes.find_one({"id": data.process_id}, {"_id": 0})
        if not process:
            raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    deadline_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Lista de utilizadores atribuídos - inclui sempre o criador
    assigned_users = data.assigned_user_ids or []
    if user["id"] not in assigned_users:
        assigned_users.append(user["id"])
    
    deadline_doc = {
        "id": deadline_id,
        "process_id": data.process_id,
        "title": data.title,
        "description": data.description,
        "due_date": data.due_date,
        "priority": data.priority,
        "completed": False,
        "created_by": user["id"],
        "created_at": now,
        "assigned_user_ids": assigned_users,
        # Campos legacy para compatibilidade
        "assigned_consultor_id": data.assigned_consultor_id,
        "assigned_mediador_id": data.assigned_mediador_id
    }
    
    await db.deadlines.insert_one(deadline_doc)
    
    if data.process_id:
        await log_history(data.process_id, user, "Criou prazo", "deadline", None, data.title)
    
    # Notificar todos os utilizadores atribuídos (exceto o criador) - com verificação de preferências
    for assigned_id in assigned_users:
        if assigned_id != user["id"]:
            assigned_user = await db.users.find_one({"id": assigned_id}, {"_id": 0})
            if assigned_user:
                await send_notification_with_preference_check(
                    assigned_user["email"],
                    f"Novo Prazo Atribuído: {data.title}",
                    f"Foi-lhe atribuído um novo prazo por {user['name']}:\n\n"
                    f"Título: {data.title}\n"
                    f"Data limite: {data.due_date}\n"
                    f"Prioridade: {data.priority}",
                    notification_type="task_assigned"
                )
    
    return DeadlineResponse(**{k: v for k, v in deadline_doc.items() if k != "_id"})


@router.get("", response_model=List[DeadlineResponse])
async def get_deadlines(process_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """
    Obter prazos/eventos do utilizador.
    
    - Cada utilizador vê eventos onde está atribuído OU dos seus clientes/processos
    - Admin e CEO vêem todos os eventos
    """
    query = {}
    
    if process_id:
        query["process_id"] = process_id
    elif user["role"] == UserRole.CLIENTE:
        # Clientes vêem eventos dos seus processos
        processes = await db.processes.find({"client_id": user["id"]}, {"id": 1, "_id": 0}).to_list(1000)
        process_ids = [p["id"] for p in processes]
        query["process_id"] = {"$in": process_ids}
    elif user["role"] in [UserRole.ADMIN, UserRole.CEO]:
        # Admin e CEO vêem todos
        pass
    else:
        # Consultores/Intermediários vêem:
        # 1. Eventos onde estão diretamente atribuídos
        # 2. Eventos criados por eles
        # 3. Eventos dos processos dos seus clientes
        my_processes = await db.processes.find({
            "$or": [
                {"assigned_consultor_id": user["id"]},
                {"consultor_id": user["id"]},
                {"assigned_mediador_id": user["id"]},
                {"intermediario_id": user["id"]}
            ]
        }, {"id": 1, "_id": 0}).to_list(1000)
        my_process_ids = [p["id"] for p in my_processes]
        
        query["$or"] = [
            {"assigned_user_ids": user["id"]},
            {"created_by": user["id"]},
            {"assigned_consultor_id": user["id"]},
            {"assigned_mediador_id": user["id"]},
            {"process_id": {"$in": my_process_ids}} if my_process_ids else {"process_id": None}
        ]
    
    deadlines = await db.deadlines.find(query, {"_id": 0}).to_list(1000)
    return [DeadlineResponse(**d) for d in deadlines]


@router.get("/my-deadlines", response_model=List[DeadlineResponse])
async def get_my_deadlines(user: dict = Depends(get_current_user)):
    """
    Obter APENAS prazos onde o utilizador tem acesso ao processo.
    
    Diferente do endpoint /deadlines, este endpoint:
    - NÃO inclui prazos onde o utilizador é apenas participante mas não tem acesso ao processo
    - Inclui apenas prazos dos processos onde o utilizador está atribuído
    """
    # Status de processos finalizados (não mostrar alertas/prazos)
    FINISHED_STATUS = ["concluido", "desistido", "cancelado", "arquivado"]
    
    if user["role"] in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO]:
        # Admin, CEO e Administrativo vêem todos os prazos (excepto de processos finalizados)
        # Buscar IDs de processos finalizados para excluir
        finished_processes = await db.processes.find(
            {"status": {"$in": FINISHED_STATUS}}, 
            {"id": 1, "_id": 0}
        ).to_list(10000)
        finished_ids = [p["id"] for p in finished_processes]
        
        query = {}
        if finished_ids:
            query["process_id"] = {"$nin": finished_ids}
        
        deadlines = await db.deadlines.find(query, {"_id": 0}).to_list(1000)
    elif user["role"] == UserRole.CLIENTE:
        # Clientes vêem eventos dos seus processos (excepto finalizados)
        processes = await db.processes.find({
            "client_id": user["id"],
            "status": {"$nin": FINISHED_STATUS}
        }, {"id": 1, "_id": 0}).to_list(1000)
        process_ids = [p["id"] for p in processes]
        deadlines = await db.deadlines.find({"process_id": {"$in": process_ids}}, {"_id": 0}).to_list(1000)
    else:
        # Consultores/Intermediários/Diretores vêem apenas prazos dos processos que lhes estão atribuídos
        my_processes = await db.processes.find({
            "$and": [
                {"status": {"$nin": FINISHED_STATUS}},
                {"$or": [
                    {"assigned_consultor_id": user["id"]},
                    {"consultor_id": user["id"]},
                    {"assigned_mediador_id": user["id"]},
                    {"intermediario_id": user["id"]}
                ]}
            ]
        }, {"id": 1, "_id": 0}).to_list(1000)
        my_process_ids = [p["id"] for p in my_processes]
        
        # Prazos dos processos atribuídos OU criados pelo utilizador OU onde está directamente atribuído ao prazo
        query = {
            "$or": [
                {"process_id": {"$in": my_process_ids}} if my_process_ids else {"process_id": None},
                {"created_by": user["id"]},
            ]
        }
        
        # Filtrar para incluir apenas prazos onde tem acesso ao processo
        deadlines = await db.deadlines.find(query, {"_id": 0}).to_list(1000)
        
        # Segunda verificação: remover prazos cujo process_id não está em my_process_ids
        # (excepto se foi criado pelo utilizador e não tem processo associado)
        filtered_deadlines = []
        for d in deadlines:
            process_id = d.get("process_id")
            if not process_id:
                # Prazo sem processo - mostrar apenas se foi criado pelo utilizador
                if d.get("created_by") == user["id"]:
                    filtered_deadlines.append(d)
            elif process_id in my_process_ids:
                # Prazo de um processo atribuído
                filtered_deadlines.append(d)
        
        deadlines = filtered_deadlines
    
    return [DeadlineResponse(**d) for d in deadlines]


@router.get("/calendar")
async def get_calendar_deadlines(
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Obter eventos para o calendário.
    
    - Cada utilizador vê os seus próprios eventos e eventos dos seus clientes
    - Admin/CEO podem filtrar por consultor/mediador ou ver todos
    """
    deadline_query = {}
    
    if user["role"] in [UserRole.ADMIN, UserRole.CEO]:
        # Admin/CEO podem filtrar ou ver todos
        if consultor_id:
            # Filtrar por consultor específico
            consultor_processes = await db.processes.find({
                "$or": [
                    {"assigned_consultor_id": consultor_id},
                    {"consultor_id": consultor_id}
                ]
            }, {"id": 1, "_id": 0}).to_list(1000)
            consultor_process_ids = [p["id"] for p in consultor_processes]
            
            deadline_query["$or"] = [
                {"assigned_user_ids": consultor_id},
                {"created_by": consultor_id},
                {"assigned_consultor_id": consultor_id},
                {"process_id": {"$in": consultor_process_ids}} if consultor_process_ids else {"process_id": None}
            ]
        elif mediador_id:
            # Filtrar por intermediário específico
            mediador_processes = await db.processes.find({
                "$or": [
                    {"assigned_mediador_id": mediador_id},
                    {"intermediario_id": mediador_id}
                ]
            }, {"id": 1, "_id": 0}).to_list(1000)
            mediador_process_ids = [p["id"] for p in mediador_processes]
            
            deadline_query["$or"] = [
                {"assigned_user_ids": mediador_id},
                {"created_by": mediador_id},
                {"assigned_mediador_id": mediador_id},
                {"process_id": {"$in": mediador_process_ids}} if mediador_process_ids else {"process_id": None}
            ]
        # Se não houver filtro, retorna todos (query vazio)
    else:
        # Outros utilizadores vêem apenas os seus eventos e dos seus clientes
        my_processes = await db.processes.find({
            "$or": [
                {"assigned_consultor_id": user["id"]},
                {"consultor_id": user["id"]},
                {"assigned_mediador_id": user["id"]},
                {"intermediario_id": user["id"]}
            ]
        }, {"id": 1, "_id": 0}).to_list(1000)
        my_process_ids = [p["id"] for p in my_processes]
        
        deadline_query["$or"] = [
            {"assigned_user_ids": user["id"]},
            {"created_by": user["id"]},
            {"assigned_consultor_id": user["id"]},
            {"assigned_mediador_id": user["id"]},
            {"process_id": {"$in": my_process_ids}} if my_process_ids else {"process_id": None}
        ]
    
    # Get deadlines
    deadlines = await db.deadlines.find(deadline_query, {"_id": 0}).to_list(1000)
    
    # Get all processes for reference
    processes = await db.processes.find({}, {"_id": 0}).to_list(1000)
    process_map = {p["id"]: p for p in processes}
    
    # Enrich deadlines with process info
    result = []
    for d in deadlines:
        process = process_map.get(d.get("process_id"), {})
        if not process and d.get("process_id"):
            process = await db.processes.find_one({"id": d["process_id"]}, {"_id": 0}) or {}
        
        result.append({
            **d,
            "client_name": process.get("client_name", "Evento Geral"),
            "client_email": process.get("client_email", ""),
            "process_status": process.get("status", ""),
            "assigned_consultor_id": d.get("assigned_consultor_id") or process.get("assigned_consultor_id"),
            "assigned_mediador_id": d.get("assigned_mediador_id") or process.get("assigned_mediador_id"),
        })
    
    return result


@router.put("/{deadline_id}", response_model=DeadlineResponse)
async def update_deadline(deadline_id: str, data: DeadlineUpdate, user: dict = Depends(get_current_user)):
    if user["role"] == UserRole.CLIENTE:
        raise HTTPException(status_code=403, detail="Clientes não podem editar prazos")
    
    deadline = await db.deadlines.find_one({"id": deadline_id}, {"_id": 0})
    if not deadline:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    
    update_data = {}
    if data.title is not None:
        update_data["title"] = data.title
    if data.description is not None:
        update_data["description"] = data.description
    if data.due_date is not None:
        update_data["due_date"] = data.due_date
    if data.priority is not None:
        update_data["priority"] = data.priority
    if data.completed is not None:
        update_data["completed"] = data.completed
        if data.completed and deadline.get("process_id"):
            await log_history(deadline["process_id"], user, "Concluiu prazo", "deadline", deadline["title"], "concluído")
    if data.assigned_consultor_id is not None:
        update_data["assigned_consultor_id"] = data.assigned_consultor_id
    if data.assigned_mediador_id is not None:
        update_data["assigned_mediador_id"] = data.assigned_mediador_id
    
    if update_data:
        await db.deadlines.update_one({"id": deadline_id}, {"$set": update_data})
    
    updated = await db.deadlines.find_one({"id": deadline_id}, {"_id": 0})
    return DeadlineResponse(**updated)


@router.delete("/{deadline_id}")
async def delete_deadline(deadline_id: str, user: dict = Depends(require_roles([UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.ADMIN]))):
    result = await db.deadlines.delete_one({"id": deadline_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    return {"message": "Prazo eliminado"}
