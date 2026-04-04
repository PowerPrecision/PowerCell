import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from services.auth import hash_password, require_roles
from utils.input_sanitization import (
    log_sanitization_rejection
)
from services.permissions import (
    get_default_permissions_for_role, 
    get_all_available_permissions,
    get_role_display_info,
    validate_permissions,
    DEFAULT_PERMISSIONS_BY_ROLE
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/admin", tags=["Admin"])


# ============== PERMISSIONS ROUTES ==============

@router.get("/permissions/available")
async def get_available_permissions(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Retorna todas as permissões disponíveis no sistema.
    Usado pelo frontend para exibir opções de permissões.
    """
    return {
        "success": True,
        "data": get_all_available_permissions()
    }


@router.get("/permissions/defaults")
async def get_default_permissions(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Retorna as permissões padrão para cada role.
    Usado pelo frontend para mostrar permissões quando muda o role.
    """
    return {
        "success": True,
        "roles": get_role_display_info(),
        "defaults": DEFAULT_PERMISSIONS_BY_ROLE
    }


@router.get("/permissions/defaults/{role}")
async def get_default_permissions_for_role_endpoint(
    role: str, 
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Retorna as permissões padrão para um role específico.
    """
    if role not in DEFAULT_PERMISSIONS_BY_ROLE:
        raise HTTPException(status_code=400, detail="Role inválido")
    
    return {
        "success": True,
        "role": role,
        "permissions": get_default_permissions_for_role(role)
    }


@router.post("/users/{user_id}/reset-permissions")
async def reset_user_permissions(
    user_id: str, 
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Redefine as permissões de um utilizador para o padrão do seu role.
    """
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    role = target_user.get("role")
    default_perms = get_default_permissions_for_role(role)
    
    await db.users.update_one(
        {"id": user_id}, 
        {"$set": {"permissions": default_perms}}
    )
    
    await _audit_log(
        "permissions_reset", 
        "user", 
        user_id, 
        user, 
        {"role": role, "permissions": default_perms}
    )
    
    return {
        "success": True,
        "message": f"Permissões redefinidas para o padrão do role '{role}'",
        "permissions": default_perms
    }


# ============== WORKFLOW STATUS ROUTES ==============

@router.get("/workflow-statuses", response_model=List[WorkflowStatusResponse])
async def get_workflow_statuses(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.INDEXACAO, UserRole.INTERMEDIARIO, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))):
    """Get all workflow statuses ordered by order field"""
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    return [WorkflowStatusResponse(**s) for s in statuses]


@router.post("/workflow-statuses", response_model=WorkflowStatusResponse)
async def create_workflow_status(data: WorkflowStatusCreate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Create a new workflow status"""
    existing = await db.workflow_statuses.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=400, detail="Estado já existe")
    
    status_doc = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "label": data.label,
        "order": data.order,
        "color": data.color,
        "description": data.description,
        "is_default": False,
        "internal_code": str(data.order).zfill(2)
    }
    
    await db.workflow_statuses.insert_one(status_doc)
    return WorkflowStatusResponse(**{k: v for k, v in status_doc.items() if k != "_id"})


@router.put("/workflow-statuses/{status_id}", response_model=WorkflowStatusResponse)
async def update_workflow_status(status_id: str, data: WorkflowStatusUpdate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Update a workflow status"""
    status = await db.workflow_statuses.find_one({"id": status_id}, {"_id": 0})
    if not status:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    update_data = {}
    if data.label is not None:
        update_data["label"] = data.label
    if data.order is not None:
        update_data["order"] = data.order
    if data.color is not None:
        update_data["color"] = data.color
    if data.description is not None:
        update_data["description"] = data.description
    
    if update_data:
        await db.workflow_statuses.update_one({"id": status_id}, {"$set": update_data})
    
    updated = await db.workflow_statuses.find_one({"id": status_id}, {"_id": 0})
    return WorkflowStatusResponse(**updated)


@router.delete("/workflow-statuses/{status_id}")
async def delete_workflow_status(status_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Elimina uma fase do workflow.
    
    Se houver processos associados, são movidos para "Clientes em Espera" (ou a primeira fase disponível).
    """
    status = await db.workflow_statuses.find_one({"id": status_id})
    if not status:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    status_name = status["name"]
    target_name = None  # Inicializar
    
    # Verificar se há processos associados
    process_count = await db.processes.count_documents({"status": status_name})
    
    if process_count > 0:
        # Encontrar a fase de destino (Clientes em Espera ou primeira fase)
        target_status = await db.workflow_statuses.find_one(
            {"name": "clientes_espera"}, 
            {"_id": 0, "name": 1, "label": 1}
        )
        
        if not target_status:
            # Se não encontrar "clientes_espera", usar a primeira fase por ordem
            target_status = await db.workflow_statuses.find_one(
                {"name": {"$ne": status_name}},
                {"_id": 0, "name": 1, "label": 1},
                sort=[("order", 1)]
            )
        
        if not target_status:
            raise HTTPException(
                status_code=400, 
                detail="Não existe outra fase para onde mover os processos"
            )
        
        target_name = target_status["name"]
        target_label = target_status.get("label", target_name)
        
        # Mover todos os processos para a fase de destino
        result = await db.processes.update_many(
            {"status": status_name},
            {"$set": {"status": target_name, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Registrar no histórico
        moved_count = result.modified_count
        if moved_count > 0:
            await db.history.insert_one({
                "id": str(uuid.uuid4()),
                "process_id": None,
                "user_id": user["id"],
                "user_name": user.get("name", "Admin"),
                "action": f"Fase '{status.get('label', status_name)}' eliminada - {moved_count} processos movidos para '{target_label}'",
                "field": "workflow_status_deleted",
                "old_value": status_name,
                "new_value": target_name,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
    
    # Eliminar a fase
    await db.workflow_statuses.delete_one({"id": status_id})
    
    return {
        "message": f"Fase '{status.get('label', status_name)}' eliminada",
        "processes_moved": process_count,
        "moved_to": target_name if process_count > 0 else None
    }


@router.post("/workflow-statuses/fix-duplicates")
async def fix_duplicate_workflow_statuses(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """
    Remove fases de workflow duplicadas causadas por merge.
    Mantém apenas a primeira ocorrência de cada fase (por nome).
    """
    from collections import defaultdict
    
    # Buscar todos os workflow_statuses
    all_statuses = await db.workflow_statuses.find({}).to_list(length=None)
    
    # Agrupar por nome
    by_name = defaultdict(list)
    for status in all_statuses:
        by_name[status.get('name')].append(status)
    
    # Identificar duplicados
    duplicates_found = False
    ids_to_remove = []
    report = {"analyzed": len(all_statuses), "duplicates": [], "removed": 0}
    
    for name, statuses in by_name.items():
        if len(statuses) > 1:
            duplicates_found = True
            # Ordenar por order para manter o mais relevante
            statuses.sort(key=lambda x: x.get('order', 999))
            
            duplicate_info = {
                "name": name,
                "count": len(statuses),
                "keeping": statuses[0].get('id'),
                "removing": []
            }
            
            # Manter o primeiro, remover os restantes
            for status in statuses[1:]:
                status_id = status.get('id')
                ids_to_remove.append(status_id)
                duplicate_info["removing"].append(status_id)
            
            report["duplicates"].append(duplicate_info)
    
    if not duplicates_found:
        return {
            "success": True,
            "message": "Não foram encontrados duplicados",
            "report": report
        }
    
    # Remover duplicados
    for status_id in ids_to_remove:
        await db.workflow_statuses.delete_one({"id": status_id})
        report["removed"] += 1
    
    # Verificar resultado final
    remaining = await db.workflow_statuses.count_documents({})
    report["remaining_count"] = remaining
    
    return {
        "success": True,
        "message": f"Removidos {report['removed']} duplicados",
        "report": report
    }


@router.post("/processes/fix-duplicates")
async def fix_duplicate_processes(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """
    Remove processos duplicados causados por merge.
    
    Identifica duplicados por:
    1. Mesmo email (client_email)
    2. Mesmo NIF (personal_data.nif)
    
    Mantém o processo mais recente (maior created_at) e remove os mais antigos.
    """
    from collections import defaultdict
    
    # Buscar todos os processos
    all_processes = await db.processes.find({}).to_list(length=None)
    
    # Agrupar por email
    by_email = defaultdict(list)
    # Agrupar por NIF
    by_nif = defaultdict(list)
    
    for proc in all_processes:
        email = proc.get("client_email", "").lower().strip() if proc.get("client_email") else None
        nif = proc.get("personal_data", {}).get("nif") if proc.get("personal_data") else None
        
        if email:
            by_email[email].append(proc)
        if nif:
            by_nif[nif].append(proc)
    
    # Identificar duplicados
    ids_to_remove = set()
    report = {
        "analyzed": len(all_processes),
        "duplicates_by_email": [],
        "duplicates_by_nif": [],
        "removed": 0
    }
    
    # Processar duplicados por email
    for email, procs in by_email.items():
        if len(procs) > 1:
            # Ordenar por created_at descendente (mais recente primeiro)
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            duplicate_info = {
                "key": email,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente, remover os outros
            for proc in procs[1:]:
                proc_id = proc.get("id")
                if proc_id not in ids_to_remove:
                    ids_to_remove.add(proc_id)
                    duplicate_info["removing"].append({
                        "id": proc_id,
                        "name": proc.get("client_name"),
                        "created_at": proc.get("created_at")
                    })
            
            report["duplicates_by_email"].append(duplicate_info)
    
    # Processar duplicados por NIF
    for nif, procs in by_nif.items():
        if len(procs) > 1:
            # Ordenar por created_at descendente
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            duplicate_info = {
                "key": nif,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente, remover os outros (se ainda não marcados)
            for proc in procs[1:]:
                proc_id = proc.get("id")
                if proc_id not in ids_to_remove:
                    ids_to_remove.add(proc_id)
                    duplicate_info["removing"].append({
                        "id": proc_id,
                        "name": proc.get("client_name"),
                        "created_at": proc.get("created_at")
                    })
            
            report["duplicates_by_nif"].append(duplicate_info)
    
    total_duplicates = len(report["duplicates_by_email"]) + len(report["duplicates_by_nif"])
    
    if total_duplicates == 0:
        return {
            "success": True,
            "message": "Não foram encontrados processos duplicados",
            "report": report
        }
    
    # Remover duplicados
    for proc_id in ids_to_remove:
        # Mover documentos associados para o processo mantido? Não, apagar tudo
        await db.documents.delete_many({"process_id": proc_id})
        await db.tasks.delete_many({"process_id": proc_id})
        await db.history.delete_many({"process_id": proc_id})
        await db.processes.delete_one({"id": proc_id})
        report["removed"] += 1
    
    # Registrar no histórico
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": None,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": f"Correção de processos duplicados - {report['removed']} processos removidos",
        "field": "process_duplicates_fixed",
        "old_value": None,
        "new_value": str(report["removed"]),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Verificar resultado final
    remaining = await db.processes.count_documents({})
    report["remaining_count"] = remaining
    
    return {
        "success": True,
        "message": f"Removidos {report['removed']} processos duplicados",
        "report": report
    }


# ============== USER MANAGEMENT ROUTES ==============

@router.get("/users", response_model=List[UserResponse])
async def get_users(role: Optional[str] = None, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.CONSULTOR, UserRole.INTERMEDIARIO]))):
    """Lista utilizadores. Acessível a Admin, CEO, Diretor, Consultor e Intermediário."""
    query = {}
    if role:
        query["role"] = role
    
    users = await db.users.find(query, {"_id": 0, "password": 0}).to_list(1000)
    return [UserResponse(**u) for u in users]


@router.post("/users", response_model=UserResponse)
async def create_user(data: UserCreate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    # Sanitizar inputs (sem validação restritiva — aceitar qualquer valor)
    clean_email = (data.email or "").strip().lower()
    clean_name = (data.name or "").strip()
    clean_phone = (data.phone or "").strip() if data.phone else None
    
    existing = await db.users.find_one({"email": clean_email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    # Validar password (apenas presença — sem validação de força)
    if not data.password:
        raise HTTPException(status_code=400, detail="Password é obrigatória")
    
    # Cliente não é um utilizador do sistema - é um processo
    if data.role == UserRole.CLIENTE:
        raise HTTPException(status_code=400, detail="Cliente não pode ser criado como utilizador. O cliente é representado pelo processo.")
    
    if data.role not in [UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO, UserRole.CEO, UserRole.ADMIN]:
        raise HTTPException(status_code=400, detail="Role inválido")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": clean_email,
        "password": hash_password(data.password),
        "name": clean_name,
        "phone": clean_phone,
        "role": data.role,
        "is_active": True,
        "onedrive_folder": data.onedrive_folder or clean_name,
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    await _audit_log("user_created", "user", user_id, user, {"email": clean_email, "role": data.role, "name": clean_name})
    
    # Enviar email de boas-vindas com dados de acesso
    try:
        from services.email_service import send_email
        
        # Determinar o nome do cargo em português
        role_names = {
            UserRole.CONSULTOR: "Consultor",
            UserRole.MEDIADOR: "Intermediário",
            UserRole.INTERMEDIARIO: "Intermediário",
            UserRole.DIRETOR: "Diretor",
            UserRole.ADMINISTRATIVO: "Administrativo",
            UserRole.INDEXACAO: "Indexação",
            UserRole.CEO: "CEO",
            UserRole.ADMIN: "Administrador"
        }
        role_name = role_names.get(data.role, data.role)
        
        # Criar corpo do email
        email_body = f"""Olá {clean_name},

Bem-vindo(a) ao PowerCell!

A sua conta foi criada com sucesso. Seguem os dados de acesso:

📧 Email: {clean_email}
🔑 Password: {data.password}

Perfil: {role_name}

🔗 Aceda à plataforma em: https://powercell.vercel.app

Recomendamos que altere a sua password após o primeiro acesso.

Se tiver alguma dúvida, não hesite em contactar.

Cumprimentos,
Equipa PowerCell
"""
        
        email_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d253f 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">Bem-vindo ao PowerCell</h1>
            </div>
            <div style="background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; border: 1px solid #e2e8f0; border-top: none;">
                <p style="font-size: 16px; color: #334155;">Olá <strong>{data.name}</strong>,</p>
                <p style="font-size: 16px; color: #334155;">A sua conta foi criada com sucesso. Seguem os dados de acesso:</p>
                
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e2e8f0;">
                    <p style="margin: 10px 0;"><strong>📧 Email:</strong> {data.email}</p>
                    <p style="margin: 10px 0;"><strong>🔑 Password:</strong> <code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">{data.password}</code></p>
                    <p style="margin: 10px 0;"><strong>👤 Perfil:</strong> {role_name}</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://powercell.vercel.app" style="background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); color: white; padding: 12px 30px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">
                        Aceder à Plataforma
                    </a>
                </div>
                
                <p style="font-size: 14px; color: #64748b; background: #fef3c7; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b;">
                    ⚠️ Recomendamos que altere a sua password após o primeiro acesso.
                </p>
                
                <p style="font-size: 14px; color: #64748b; margin-top: 30px;">
                    Se tiver alguma dúvida, não hesite em contactar.<br><br>
                    Cumprimentos,<br>
                    <strong>Equipa PowerCell</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        # Enviar email (usar conta power ou precision)
        email_result = await send_email(
            account_name="power",  # Usar conta Power Real Estate
            to_emails=[clean_email],
            subject="Bem-vindo ao PowerCell - Dados de Acesso",
            body=email_body,
            body_html=email_html
        )
        
        if email_result.get("success"):
            logger.info(f"Email de boas-vindas enviado para {data.email}")
        else:
            logger.warning(f"Não foi possível enviar email para {data.email}: {email_result.get('error')}")
            
    except Exception as e:
        logger.warning(f"Erro ao enviar email de boas-vindas: {e}")
        # Não falhar a criação do utilizador se o email falhar
    
    # Associar automaticamente processos do Trello que têm este utilizador atribuído
    # Verifica se o nome do utilizador corresponde a algum membro atribuído no Trello
    name_lower = clean_name.lower()
    name_parts = [p for p in name_lower.split() if len(p) >= 3]
    
    # Procurar processos com trello_members que corresponda ao nome
    query = {"trello_members": {"$exists": True, "$ne": []}}
    processes_to_update = await db.processes.find(query, {"_id": 0, "id": 1, "trello_members": 1}).to_list(1000)
    
    updated_count = 0
    for proc in processes_to_update:
        members = proc.get("trello_members", [])
        # Verificar se o nome do utilizador está na lista de membros
        for member in members:
            member_lower = member.lower()
            # Verificar se alguma parte do nome corresponde
            if any(part in member_lower for part in name_parts):
                # Determinar qual campo atualizar baseado no role
                if data.role in [UserRole.CONSULTOR]:
                    await db.processes.update_one(
                        {"id": proc["id"]},
                        {"$set": {"assigned_consultor_id": user_id}}
                    )
                    updated_count += 1
                elif data.role in [UserRole.MEDIADOR, UserRole.INTERMEDIARIO]:
                    await db.processes.update_one(
                        {"id": proc["id"]},
                        {"$set": {"assigned_mediador_id": user_id}}
                    )
                    updated_count += 1
                break  # Já encontrou match, passar ao próximo processo
    
    if updated_count > 0:
        logger.info(f"Utilizador {data.name} criado e associado a {updated_count} processos automaticamente")
    
    return UserResponse(
        id=user_id,
        email=clean_email,
        name=clean_name,
        phone=clean_phone,
        role=data.role,
        created_at=now,
        onedrive_folder=data.onedrive_folder or clean_name
    )


async def _audit_log(action: str, entity: str, entity_id: str, performed_by: dict, details: dict = None):
    """O18 - Regista uma acção crítica no audit log."""
    try:
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "performed_by_id": performed_by.get("id"),
            "performed_by_name": performed_by.get("name"),
            "performed_by_email": performed_by.get("email"),
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.warning(f"Audit log falhou: {e}")


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, data: UserUpdate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    from services.permissions import (
        get_default_permissions_for_role, 
        should_sync_permissions,
        validate_permissions
    )
    
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    update_data = {}
    role_changed = False
    old_role = target_user.get("role")
    
    if data.name is not None:
        update_data["name"] = (data.name or "").strip()
    if data.phone is not None:
        update_data["phone"] = (data.phone or "").strip() if data.phone else None
    if data.email is not None:
        clean_email = (data.email or "").strip().lower()
        if clean_email:
            # Verificar se email já existe noutro utilizador
            existing = await db.users.find_one({"email": clean_email, "id": {"$ne": user_id}})
            if existing:
                raise HTTPException(status_code=400, detail="Email já registado noutro utilizador")
            update_data["email"] = clean_email
    if data.role is not None:
        if data.role not in [UserRole.CLIENTE, UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO, UserRole.CEO, UserRole.ADMIN]:
            raise HTTPException(status_code=400, detail="Role inválido")
        if data.role != old_role:
            role_changed = True
        update_data["role"] = data.role
    if data.is_active is not None:
        # Proteger admin de ser desactivado
        if target_user.get("role") == "admin" and data.is_active == False:
            raise HTTPException(status_code=400, detail="Não é possível desactivar o utilizador administrador")
        update_data["is_active"] = data.is_active
    if data.onedrive_folder is not None:
        update_data["onedrive_folder"] = data.onedrive_folder
    # Processar alteração de password (apenas admin pode alterar password de outros)
    if data.password is not None and data.password.strip():
        update_data["password"] = hash_password(data.password)
    
    # Processar permissões - sincronizar automaticamente quando o role muda
    current_permissions = target_user.get("permissions")
    new_role = data.role or old_role
    
    if data.permissions is not None:
        # Se o admin está a definir permissões explicitamente, usar essas
        update_data["permissions"] = validate_permissions(data.permissions)
    elif role_changed:
        # Se o role mudou, sincronizar permissões com o novo role
        # Apenas sincronizar se o utilizador não tinha permissões personalizadas
        if should_sync_permissions(old_role, new_role, current_permissions):
            update_data["permissions"] = get_default_permissions_for_role(new_role)
            logger.info(f"Permissões sincronizadas para utilizador {user_id}: {old_role} -> {new_role}")
        # Se tinha permissões personalizadas, manter (admin pode redefinir manualmente)
    
    if update_data:
        await db.users.update_one({"id": user_id}, {"$set": update_data})
    
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return UserResponse(**updated)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Não pode eliminar a própria conta")
    
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1, "name": 1, "role": 1})
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    await _audit_log("user_deleted", "user", user_id, user, {"deleted_email": target.get("email"), "deleted_name": target.get("name"), "deleted_role": target.get("role")})
    return {"message": "Utilizador eliminado"}


# ============== IMPERSONATE (VER COMO OUTRO UTILIZADOR) ==============

@router.post("/impersonate/{user_id}")
async def impersonate_user(user_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Permite ao admin ver o sistema como outro utilizador.
    Gera um token temporário com os dados do utilizador alvo.
    
    O token inclui informação sobre o admin original para auditoria.
    """
    from services.auth import create_access_token
    
    # Verificar que o utilizador alvo existe
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Não permitir impersonate de outro admin
    if target_user["role"] == UserRole.ADMIN and user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Não pode personificar outro administrador")
    
    # Criar token com dados do utilizador alvo, mas marcar como impersonated
    token_data = {
        "sub": target_user["id"],
        "email": target_user["email"],
        "role": target_user["role"],
        "name": target_user["name"],
        # Informação de auditoria
        "impersonated_by": user["id"],
        "impersonated_by_name": user["name"],
        "is_impersonated": True
    }
    
    access_token = create_access_token(token_data)
    
    # Log da acção
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": None,
        "user_id": user["id"],
        "user_name": user["name"],
        "action": f"Admin impersonou utilizador: {target_user['name']} ({target_user['email']})",
        "field": "impersonate",
        "old_value": None,
        "new_value": target_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": target_user["id"],
            "email": target_user["email"],
            "name": target_user["name"],
            "role": target_user["role"],
            "is_impersonated": True,
            "impersonated_by": user["id"],
            "impersonated_by_name": user["name"]
        }
    }


@router.post("/stop-impersonate")
async def stop_impersonate(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO]))):
    """
    Terminar sessão de impersonate e voltar à conta original.
    Requer o token do admin original.
    """
    from services.auth import create_access_token
    
    if not user.get("impersonated_by"):
        raise HTTPException(status_code=400, detail="Não está em modo de personificação")
    
    # Buscar o admin original
    admin_user = await db.users.find_one({"id": user["impersonated_by"]}, {"_id": 0, "password": 0})
    if not admin_user:
        raise HTTPException(status_code=404, detail="Administrador original não encontrado")
    
    # Criar novo token para o admin
    token_data = {
        "sub": admin_user["id"],
        "email": admin_user["email"],
        "role": admin_user["role"],
        "name": admin_user["name"]
    }
    
    access_token = create_access_token(token_data)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": admin_user["id"],
            "email": admin_user["email"],
            "name": admin_user["name"],
            "role": admin_user["role"]
        }
    }


# ============== PROCESS NUMBER MIGRATION ==============

@router.post("/migrate-process-numbers")
async def migrate_process_numbers(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """
    Atribuir números sequenciais a todos os processos que não têm.
    Os processos são ordenados por data de criação (mais antigos primeiro).
    """
    # Buscar processos sem número, ordenados por data de criação
    processes_without_number = await db.processes.find(
        {"$or": [{"process_number": {"$exists": False}}, {"process_number": None}]},
        {"_id": 0, "id": 1, "created_at": 1, "client_name": 1}
    ).sort("created_at", 1).to_list(10000)
    
    if not processes_without_number:
        return {"message": "Todos os processos já têm número atribuído", "updated": 0}
    
    # Obter o maior número existente
    max_result = await db.processes.find_one(
        {"process_number": {"$exists": True, "$ne": None}},
        {"process_number": 1},
        sort=[("process_number", -1)]
    )
    
    next_number = (max_result["process_number"] + 1) if max_result and max_result.get("process_number") else 1
    
    updated_count = 0
    for process in processes_without_number:
        await db.processes.update_one(
            {"id": process["id"]},
            {"$set": {"process_number": next_number}}
        )
        next_number += 1
        updated_count += 1
    
    return {
        "message": f"Números atribuídos a {updated_count} processos",
        "updated": updated_count,
        "first_number": next_number - updated_count,
        "last_number": next_number - 1
    }


@router.post("/update-process-active-status")
async def update_process_active_status(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """
    Atualizar o campo is_active de todos os processos baseado no status.
    Processos em 'desistencias' ou 'concluidos' são marcados como inativos.
    """
    # Status que devem ser marcados como inativos
    inactive_statuses = ["desistencias", "concluidos"]
    
    # Atualizar processos inativos
    inactive_result = await db.processes.update_many(
        {"status": {"$in": inactive_statuses}},
        {"$set": {"is_active": False}}
    )
    
    # Atualizar processos ativos (todos os outros)
    active_result = await db.processes.update_many(
        {"status": {"$nin": inactive_statuses}},
        {"$set": {"is_active": True}}
    )
    
    return {
        "message": "Status de atividade atualizado",
        "inactive_updated": inactive_result.modified_count,
        "active_updated": active_result.modified_count,
        "total_updated": inactive_result.modified_count + active_result.modified_count
    }


# ============== NOTIFICATION PREFERENCES ==============

# Default notification preferences
DEFAULT_NOTIFICATION_PREFS = {
    "email_new_process": False,  # Novo processo criado
    "email_status_change": False,  # Mudança de status de processo
    "email_document_upload": False,  # Documento carregado
    "email_task_assigned": False,  # Tarefa atribuída
    "email_deadline_reminder": True,  # Lembrete de prazo (importante)
    "email_urgent_only": True,  # Apenas urgentes
    "email_daily_summary": True,  # Resumo diário
    "email_weekly_report": True,  # Relatório semanal
    "inapp_new_process": True,
    "inapp_status_change": True,
    "inapp_document_upload": True,
    "inapp_task_assigned": True,
    "inapp_comments": True,
    "is_test_user": False,  # Se true, não recebe emails
}


# ============== AI TRAINING DATA (Item 4 - Outros erros/melhorias) ==============

@router.get("/ai-training")
async def get_ai_training_data(
    category: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém os dados de treino personalizados do agente IA.
    
    Categorias:
    - document_types: Tipos de documentos e como classificá-los
    - field_mappings: Mapeamento de campos para extração
    - client_patterns: Padrões de nomes de clientes
    - custom_rules: Regras personalizadas
    """
    query = {"type": "ai_training"}
    if category:
        query["category"] = category
    
    entries = await db.ai_training.find(query, {"_id": 0}).to_list(100)
    
    # Agrupar por categoria
    by_category = {}
    for entry in entries:
        cat = entry.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry)
    
    return {
        "total": len(entries),
        "categories": list(by_category.keys()),
        "data": by_category
    }


@router.post("/ai-training")
async def add_ai_training_entry(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Adiciona uma nova entrada de treino para o agente IA.
    
    Body:
    {
        "category": "document_types",  // ou field_mappings, client_patterns, custom_rules
        "title": "Título descritivo",
        "content": "Conteúdo de treino / instruções para a IA",
        "examples": ["exemplo1", "exemplo2"],  // Opcional
        "is_active": true  // Se deve ser usado pelo agente
    }
    """
    required_fields = ["category", "title", "content"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo '{field}' é obrigatório")
    
    valid_categories = ["document_types", "field_mappings", "client_patterns", "custom_rules", "extraction_tips"]
    if data["category"] not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {valid_categories}")
    
    entry = {
        "id": str(uuid.uuid4()),
        "type": "ai_training",
        "category": data["category"],
        "title": data["title"],
        "content": data["content"],
        "examples": data.get("examples", []),
        "is_active": data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.get("email", "admin"),
        "updated_at": None
    }
    
    await db.ai_training.insert_one(entry)
    
    return {
        "success": True,
        "entry": {k: v for k, v in entry.items() if k != "_id"}
    }


@router.put("/ai-training/{entry_id}")
async def update_ai_training_entry(
    entry_id: str,
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Actualiza uma entrada de treino existente.
    """
    existing = await db.ai_training.find_one({"id": entry_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    
    update_data = {}
    if "title" in data:
        update_data["title"] = data["title"]
    if "content" in data:
        update_data["content"] = data["content"]
    if "examples" in data:
        update_data["examples"] = data["examples"]
    if "is_active" in data:
        update_data["is_active"] = data["is_active"]
    if "category" in data:
        valid_categories = ["document_types", "field_mappings", "client_patterns", "custom_rules", "extraction_tips"]
        if data["category"] not in valid_categories:
            raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {valid_categories}")
        update_data["category"] = data["category"]
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("email", "admin")
    
    await db.ai_training.update_one(
        {"id": entry_id},
        {"$set": update_data}
    )
    
    updated = await db.ai_training.find_one({"id": entry_id}, {"_id": 0})
    return {"success": True, "entry": updated}


@router.delete("/ai-training/{entry_id}")
async def delete_ai_training_entry(
    entry_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Remove uma entrada de treino.
    """
    result = await db.ai_training.delete_one({"id": entry_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    
    return {"success": True, "message": "Entrada removida"}


@router.get("/ai-training/prompt")
async def get_ai_training_prompt(
    category: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Gera o prompt de treino consolidado a partir das entradas activas.
    Este prompt é usado pelo agente IA durante a análise de documentos.
    """
    query = {"type": "ai_training", "is_active": True}
    if category:
        query["category"] = category
    
    entries = await db.ai_training.find(query, {"_id": 0}).sort("category", 1).to_list(100)
    
    # Construir prompt por categoria
    prompt_sections = []
    
    # Agrupar por categoria
    by_category = {}
    for entry in entries:
        cat = entry.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry)
    
    category_titles = {
        "document_types": "## Tipos de Documentos",
        "field_mappings": "## Mapeamento de Campos",
        "client_patterns": "## Padrões de Nomes de Clientes",
        "custom_rules": "## Regras Personalizadas",
        "extraction_tips": "## Dicas de Extracção"
    }
    
    for cat, cat_entries in by_category.items():
        section = category_titles.get(cat, f"## {cat.title()}")
        section += "\n"
        
        for entry in cat_entries:
            section += f"\n### {entry['title']}\n"
            section += entry["content"] + "\n"
            
            if entry.get("examples"):
                section += "\nExemplos:\n"
                for ex in entry["examples"]:
                    section += f"- {ex}\n"
        
        prompt_sections.append(section)
    
    full_prompt = "\n\n".join(prompt_sections)
    
    return {
        "prompt": full_prompt,
        "entries_count": len(entries),
        "categories": list(by_category.keys())
    }


@router.post("/ai-training/prompt/execute")
async def record_ai_prompt_execution(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    O23 - Regista uma execução do prompt de treino de IA.
    Incrementa o contador de execuções.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Incrementar contador global de execuções
    await db.ai_config.update_one(
        {"type": "execution_stats"},
        {
            "$inc": {"total_executions": 1},
            "$set": {"last_executed_at": now, "last_executed_by": user.get("name", "unknown")},
            "$setOnInsert": {"type": "execution_stats", "created_at": now}
        },
        upsert=True
    )
    
    # Retornar stats actualizadas
    stats = await db.ai_config.find_one({"type": "execution_stats"}, {"_id": 0})
    return {
        "success": True,
        "total_executions": stats.get("total_executions", 1),
        "last_executed_at": stats.get("last_executed_at"),
        "last_executed_by": stats.get("last_executed_by")
    }


@router.get("/ai-training/stats")
async def get_ai_training_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """O23 - Obtém estatísticas de uso do AI Training."""
    stats = await db.ai_config.find_one({"type": "execution_stats"}, {"_id": 0}) or {}
    entries_count = await db.ai_training.count_documents({"type": "ai_training", "is_active": True})
    
    return {
        "total_executions": stats.get("total_executions", 0),
        "last_executed_at": stats.get("last_executed_at"),
        "last_executed_by": stats.get("last_executed_by"),
        "active_entries": entries_count
    }


@router.get("/notification-preferences/{user_id}")
async def get_notification_preferences(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém as preferências de notificação de um utilizador.
    Admin pode ver/editar de qualquer utilizador.
    """
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Obter preferências da DB ou usar defaults
    prefs = await db.notification_preferences.find_one({"user_id": user_id}, {"_id": 0})
    
    if not prefs:
        prefs = {**DEFAULT_NOTIFICATION_PREFS, "user_id": user_id}
    
    return {
        "user_id": user_id,
        "user_email": target_user.get("email"),
        "user_name": target_user.get("name"),
        "preferences": prefs
    }


@router.put("/notification-preferences/{user_id}")
async def update_notification_preferences(
    user_id: str,
    preferences: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Actualiza as preferências de notificação de um utilizador.
    Admin pode editar de qualquer utilizador.
    """
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Filtrar apenas campos válidos
    valid_keys = set(DEFAULT_NOTIFICATION_PREFS.keys())
    filtered_prefs = {k: v for k, v in preferences.items() if k in valid_keys}
    
    filtered_prefs["user_id"] = user_id
    filtered_prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    filtered_prefs["updated_by"] = user.get("email", "admin")
    
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": filtered_prefs},
        upsert=True
    )
    
    # Invalidar cache de preferências de notificação
    try:
        from services.realtime_notifications import _invalidate_pref_cache
        _invalidate_pref_cache(user_id)
    except ImportError:
        pass
    
    return {"success": True, "preferences": filtered_prefs}


@router.get("/notification-preferences")
async def get_all_notification_preferences(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista preferências de todos os utilizadores."""
    users = await db.users.find({}, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1}).to_list(500)
    
    result = []
    for u in users:
        prefs = await db.notification_preferences.find_one({"user_id": u["id"]}, {"_id": 0})
        if not prefs:
            prefs = {**DEFAULT_NOTIFICATION_PREFS, "user_id": u["id"]}
        
        result.append({
            "user_id": u["id"],
            "email": u.get("email"),
            "name": u.get("name"),
            "role": u.get("role"),
            "receives_email": not prefs.get("is_test_user", False) and (
                prefs.get("email_urgent_only") or 
                prefs.get("email_daily_summary") or
                prefs.get("email_weekly_report")
            ),
            "is_test_user": prefs.get("is_test_user", False)
        })
    
    return result


@router.post("/notification-preferences/bulk-update")
async def bulk_update_notification_preferences(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Actualiza preferências de múltiplos utilizadores de uma vez.
    
    Body:
    {
        "user_ids": ["id1", "id2"],
        "preferences": {"is_test_user": true}
    }
    """
    user_ids = data.get("user_ids", [])
    preferences = data.get("preferences", {})
    
    if not user_ids:
        raise HTTPException(status_code=400, detail="user_ids é obrigatório")
    
    valid_keys = set(DEFAULT_NOTIFICATION_PREFS.keys())
    filtered_prefs = {k: v for k, v in preferences.items() if k in valid_keys}
    filtered_prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    filtered_prefs["updated_by"] = user.get("email", "admin")
    
    updated = 0
    for uid in user_ids:
        result = await db.notification_preferences.update_one(
            {"user_id": uid},
            {"$set": {**filtered_prefs, "user_id": uid}},
            upsert=True
        )
        if result.modified_count > 0 or result.upserted_id:
            updated += 1
    
    # Invalidar cache de preferências de notificação para todos os utilizadores afectados
    try:
        from services.realtime_notifications import _invalidate_pref_cache
        for uid in user_ids:
            _invalidate_pref_cache(uid)
    except ImportError:
        pass
    
    return {"success": True, "updated_count": updated}


# ============== SYSTEM ERROR LOGS ==============

@router.get("/system-logs")
async def get_system_error_logs(
    page: int = 1,
    limit: int = 50,
    severity: str = None,
    component: str = None,
    error_type: str = None,
    resolved: bool = None,
    days: int = 7,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de erros do sistema com filtros e paginação.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - severity: Filtrar por severidade (info, warning, error, critical)
    - component: Filtrar por componente (scraper, auth, processes, etc.)
    - error_type: Filtrar por tipo de erro
    - resolved: True/False para filtrar resolvidos/não resolvidos
    - days: Últimos N dias (default 7)
    """
    from services.system_error_logger import system_error_logger
    return await system_error_logger.get_errors(
        page=page,
        limit=limit,
        severity=severity,
        component=component,
        error_type=error_type,
        resolved=resolved,
        days=days
    )


@router.get("/system-logs/stats")
async def get_system_logs_stats(
    days: int = 7,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém estatísticas de erros dos últimos N dias."""
    from services.system_error_logger import system_error_logger
    return await system_error_logger.get_stats(days)


@router.get("/system-logs/{error_id}")
async def get_system_log_detail(
    error_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém detalhes de um erro específico."""
    from services.system_error_logger import system_error_logger
    error = await system_error_logger.get_error_by_id(error_id)
    if not error:
        raise HTTPException(status_code=404, detail="Erro não encontrado")
    return error


@router.post("/system-logs/mark-read")
async def mark_errors_as_read(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca erros como lidos.
    
    Body: {"error_ids": ["id1", "id2"]}
    """
    error_ids = data.get("error_ids", [])
    if not error_ids:
        raise HTTPException(status_code=400, detail="error_ids é obrigatório")
    
    from services.system_error_logger import system_error_logger
    count = await system_error_logger.mark_as_read(error_ids)
    return {"success": True, "marked_count": count}


@router.post("/system-logs/{error_id}/resolve")
async def resolve_system_error(
    error_id: str,
    data: dict = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca um erro como resolvido.
    
    Body (opcional): {"notes": "Corrigido em versão X"}
    """
    data = data or {}
    notes = data.get("notes")
    
    from services.system_error_logger import system_error_logger
    success = await system_error_logger.mark_as_resolved(
        error_id=error_id,
        resolved_by=user.get("email", "admin"),
        notes=notes
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Erro não encontrado")
    
    return {"success": True, "message": "Erro marcado como resolvido"}


@router.post("/system-logs/bulk-resolve")
async def bulk_resolve_system_errors(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca múltiplos erros como resolvidos em massa.
    
    Body: {"error_ids": ["id1", "id2", ...]}
    """
    error_ids = data.get("error_ids", [])
    
    if not error_ids:
        raise HTTPException(status_code=400, detail="Nenhum ID fornecido")
    
    from services.system_error_logger import system_error_logger
    resolved_count = await system_error_logger.bulk_mark_as_resolved(
        error_ids=error_ids,
        resolved_by=user.get("email", "admin")
    )
    
    return {
        "success": True, 
        "resolved_count": resolved_count,
        "message": f"{resolved_count} erros marcados como resolvidos"
    }


@router.post("/system-logs/resolve-all")
async def resolve_all_system_errors(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca TODOS os erros não resolvidos como resolvidos.
    Útil para limpar o painel de erros depois de uma manutenção.
    """
    from services.system_error_logger import system_error_logger
    resolved_count = await system_error_logger.resolve_all_unresolved(
        resolved_by=user.get("email", "admin")
    )
    
    return {
        "success": True,
        "resolved_count": resolved_count,
        "message": f"Todos os {resolved_count} erros foram marcados como resolvidos"
    }


@router.delete("/system-logs/cleanup")
async def cleanup_old_system_logs(
    days: int = 90,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove logs antigos (mais de N dias)."""
    from services.system_error_logger import system_error_logger
    count = await system_error_logger.cleanup_old_errors(days)
    return {"success": True, "deleted_count": count}



# ============== DATABASE INDEX MANAGEMENT ==============

@router.get("/db/indexes")
async def get_database_indexes(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Lista todos os índices de todas as colecções principais.
    Útil para diagnóstico de problemas de índices duplicados.
    """
    from services.db_indexes import get_index_stats
    stats = await get_index_stats(db)
    return {"success": True, "indexes": stats}


# ============== AI IMPORT LOGS (Item 3 - Outros erros/melhorias) ==============

@router.get("/ai-import-logs")
async def get_ai_import_logs(
    page: int = 1,
    limit: int = 50,
    status: str = None,
    days: int = 7,
    client_name: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de importação massiva IA para integração no menu de Logs do sistema.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - status: Filtrar por estado (success, error, warning)
    - days: Últimos N dias (default 7)
    - client_name: Filtrar por nome de cliente
    """
    skip = (page - 1) * limit
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    query = {"timestamp": {"$gte": cutoff_date}}
    
    if status == "error":
        query["resolved"] = False
    elif status == "success":
        query["resolved"] = True
    
    if client_name:
        query["client_name"] = {"$regex": client_name, "$options": "i"}
    
    # Buscar erros de importação
    errors = await db.import_errors.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
    
    # Contagem total
    total = await db.import_errors.count_documents(query)
    
    # Estatísticas rápidas
    stats = {
        "total_errors": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}}),
        "unresolved": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}, "resolved": False}),
        "resolved": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}, "resolved": True}),
    }
    
    # Formatar logs para UI
    formatted_logs = []
    for error in errors:
        formatted_logs.append({
            "id": error.get("id"),
            "timestamp": error.get("timestamp"),
            "severity": "error" if not error.get("resolved") else "info",
            "component": "ai_bulk_import",
            "error_type": error.get("document_type", "import_error"),
            "message": error.get("error", ""),
            "details": {
                "client_name": error.get("client_name"),
                "filename": error.get("filename"),
                "folder_name": error.get("folder_name"),
                "matching_details": error.get("matching_details")
            },
            "resolved": error.get("resolved", False),
            "user_email": error.get("user_email")
        })
    
    return {
        "logs": formatted_logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit
        },
        "stats": stats
    }


@router.post("/ai-import-logs/{log_id}/resolve")
async def resolve_ai_import_log(
    log_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca um log de importação como resolvido.
    """
    result = await db.import_errors.update_one(
        {"id": log_id},
        {
            "$set": {
                "resolved": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get("email", "admin")
            }
        }
    )
    
    # Também actualizar na colecção ai_import_logs
    await db.ai_import_logs.update_one(
        {"id": log_id},
        {
            "$set": {
                "resolved": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get("email", "admin")
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return {"success": True, "message": "Log marcado como resolvido"}


@router.post("/ai-import-logs/bulk-resolve")
async def bulk_resolve_ai_import_logs(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca múltiplos logs de importação como resolvidos em massa.
    
    Body:
    - log_ids: Lista de IDs a resolver
    """
    log_ids = data.get("log_ids", [])
    if not log_ids:
        raise HTTPException(status_code=400, detail="Nenhum ID fornecido")
    
    now = datetime.now(timezone.utc).isoformat()
    resolved_by = user.get("email", "admin")
    
    # Actualizar na colecção ai_import_logs
    result = await db.ai_import_logs.update_many(
        {"id": {"$in": log_ids}, "resolved": {"$ne": True}},
        {
            "$set": {
                "resolved": True,
                "resolved_at": now,
                "resolved_by": resolved_by
            }
        }
    )
    
    # Também actualizar na colecção import_errors (legacy)
    await db.import_errors.update_many(
        {"id": {"$in": log_ids}},
        {
            "$set": {
                "resolved": True,
                "resolved_at": now,
                "resolved_by": resolved_by
            }
        }
    )
    
    return {
        "success": True,
        "resolved_count": result.modified_count,
        "message": f"{result.modified_count} logs marcados como resolvidos"
    }


@router.get("/ai-import-logs-v2/grouped")
async def get_ai_import_logs_grouped(
    days: int = 7,
    status: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de importação IA agrupados por cliente.
    Mostra resumo de sucesso/erro por cliente.
    
    Query params:
    - days: Últimos N dias (default 7)
    - status: Filtrar por estado (success, error, all)
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    match_stage = {"timestamp": {"$gte": cutoff_date}}
    if status == "error":
        match_stage["status"] = "error"
    elif status == "success":
        match_stage["status"] = "success"
    
    # Agregar por cliente
    pipeline = [
        {"$match": match_stage},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$client_name",
            "total_docs": {"$sum": 1},
            "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
            "error_count": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
            "fields_updated": {"$sum": "$fields_count"},
            "last_import": {"$first": "$timestamp"},
            "logs": {"$push": {
                "id": "$id",
                "status": "$status",
                "filename": "$filename",
                "document_type": "$document_type",
                "timestamp": "$timestamp",
                "fields_count": "$fields_count",
                "error": "$error",
                "resolved": "$resolved"
            }}
        }},
        {"$sort": {"last_import": -1}},
        {"$project": {
            "client_name": "$_id",
            "total_docs": 1,
            "success_count": 1,
            "error_count": 1,
            "fields_updated": 1,
            "last_import": 1,
            "logs": {"$slice": ["$logs", 50]},  # Limitar a 50 logs por cliente
            "_id": 0
        }}
    ]
    
    groups = await db.ai_import_logs.aggregate(pipeline).to_list(100)
    
    # Estatísticas gerais
    stats = {
        "total_clients": len(groups),
        "total_docs": sum(g["total_docs"] for g in groups),
        "total_success": sum(g["success_count"] for g in groups),
        "total_errors": sum(g["error_count"] for g in groups),
        "total_fields": sum(g["fields_updated"] for g in groups)
    }
    
    return {
        "groups": groups,
        "stats": stats
    }


# ============== AI IMPORT LOGS V2 - Com categorização de dados ==============

@router.get("/ai-import-logs-v2")
async def get_ai_import_logs_v2(
    page: int = 1,
    limit: int = 50,
    status: str = None,
    days: int = 7,
    client_name: str = None,
    document_type: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de importação IA com dados categorizados.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - status: Filtrar por estado (success, error, partial, all)
    - days: Últimos N dias (default 7)
    - client_name: Filtrar por nome de cliente
    - document_type: Filtrar por tipo de documento (cc, irs, recibo_vencimento, etc.)
    
    Returns:
    - logs: Lista de logs com dados categorizados
    - stats: Estatísticas de sucesso/erro
    - pagination: Info de paginação
    """
    skip = (page - 1) * limit
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    query = {"created_at": {"$gte": cutoff_date}}
    
    if status == "error":
        query["status"] = "error"
    elif status == "success":
        query["status"] = "success"
    elif status == "partial":
        query["status"] = "partial"
    
    if client_name:
        query["client_name"] = {"$regex": client_name, "$options": "i"}
    
    if document_type:
        query["documents.document_type"] = document_type
    
    # Buscar logs
    logs = await db.ai_import_logs.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    
    # Contagem total
    total = await db.ai_import_logs.count_documents(query)
    
    # Estatísticas
    base_query = {"created_at": {"$gte": cutoff_date}}
    stats = {
        "total": await db.ai_import_logs.count_documents(base_query),
        "success": await db.ai_import_logs.count_documents({**base_query, "status": "success"}),
        "error": await db.ai_import_logs.count_documents({**base_query, "status": "error"}),
        "partial": await db.ai_import_logs.count_documents({**base_query, "status": "partial"}),
        "total_documents": 0,
        "success_documents": 0,
        "error_documents": 0,
    }
    
    # Contar documentos processados
    pipeline = [
        {"$match": base_query},
        {"$group": {
            "_id": None, 
            "total_docs": {"$sum": "$total_documents"},
            "success_docs": {"$sum": "$success_count"},
            "error_docs": {"$sum": "$error_count"}
        }}
    ]
    agg_result = await db.ai_import_logs.aggregate(pipeline).to_list(1)
    if agg_result:
        stats["total_documents"] = agg_result[0].get("total_docs", 0)
        stats["success_documents"] = agg_result[0].get("success_docs", 0)
        stats["error_documents"] = agg_result[0].get("error_docs", 0)
    
    # Taxa de sucesso
    if stats["total_documents"] > 0:
        stats["success_rate"] = round(stats["success_documents"] / stats["total_documents"] * 100, 1)
    else:
        stats["success_rate"] = 0
    
    return {
        "logs": logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        },
        "stats": stats
    }


@router.get("/ai-import-logs-v2/{log_id}")
async def get_ai_import_log_detail(
    log_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém detalhes de um log de importação específico.
    Inclui dados categorizados por tabs.
    """
    log = await db.ai_import_logs.find_one(
        {"id": log_id},
        {"_id": 0}
    )
    
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return log


@router.post("/db/indexes/repair")
async def repair_database_indexes(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Remove índices antigos/incorretos e recria os correctos.
    Use quando houver erros de duplicate key em índices.
    """
    from services.db_indexes import cleanup_deprecated_indexes, create_indexes
    
    # Primeiro, limpar índices problemáticos
    cleanup_results = await cleanup_deprecated_indexes(db)
    
    # Depois, garantir que os índices correctos existem
    create_results = await create_indexes(db)
    
    return {
        "success": True,
        "cleanup": cleanup_results,
        "indexes": create_results
    }


@router.delete("/db/indexes/{collection}/{index_name}")
async def drop_specific_index(
    collection: str,
    index_name: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Remove um índice específico de uma colecção.
    Use com cuidado - apenas para índices problemáticos.
    """
    allowed_collections = ["properties", "processes", "users", "tasks", "leads"]
    if collection not in allowed_collections:
        raise HTTPException(status_code=400, detail=f"Colecção não permitida. Use: {allowed_collections}")
    
    if index_name == "_id_":
        raise HTTPException(status_code=400, detail="Não pode remover o índice _id_")
    
    try:
        coll = db[collection]
        existing = await coll.index_information()
        
        if index_name not in existing:
            raise HTTPException(status_code=404, detail=f"Índice '{index_name}' não existe em '{collection}'")
        
        await coll.drop_index(index_name)
        return {"success": True, "message": f"Índice '{index_name}' removido de '{collection}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover índice: {str(e)}")



# ============== CLEANUP ENDPOINTS ==============

@router.delete("/cleanup/jobs")
async def cleanup_old_jobs(
    days: int = Query(default=7, ge=1, le=90),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Remove jobs de background antigos (concluídos ou falhados).
    """
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    result = await db.background_jobs.delete_many({
        "completed_at": {"$lt": cutoff},
        "status": {"$in": ["completed", "failed"]}
    })
    
    return {"success": True, "deleted_count": result.deleted_count}


@router.delete("/cleanup/error-logs")
async def cleanup_old_error_logs(
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Remove logs de erro antigos.
    """
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    result = await db.system_error_logs.delete_many({
        "timestamp": {"$lt": cutoff}
    })
    
    return {"success": True, "deleted_count": result.deleted_count}



# ============== MONITORIZAÇÃO DE JOBS ==============

@router.get("/jobs/health")
async def get_jobs_health(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Verifica o estado dos jobs em background.
    Detecta jobs travados (em execução há muito tempo).
    """
    from datetime import timedelta
    
    # Definir thresholds
    stuck_threshold_minutes = 30  # Job é considerado travado após 30 minutos
    
    # Buscar jobs recentes
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(hours=24)  # Últimas 24 horas
    
    # Buscar AI import logs (jobs de importação)
    ai_import_logs = await db.ai_import_logs.find(
        {"start_time": {"$gte": cutoff_time.isoformat()}},
        {"_id": 0}
    ).sort("start_time", -1).to_list(100)
    
    # Analisar jobs
    running_jobs = []
    stuck_jobs = []
    completed_jobs = []
    failed_jobs = []
    
    for log in ai_import_logs:
        status = log.get("status", "").lower()
        start_time_str = log.get("start_time")
        
        if status in ["completed", "success", "done"]:
            completed_jobs.append(log)
        elif status in ["failed", "error"]:
            failed_jobs.append(log)
        elif status in ["processing", "running", "in_progress"]:
            # Verificar se está travado
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    duration_minutes = (now - start_time).total_seconds() / 60
                    
                    if duration_minutes > stuck_threshold_minutes:
                        stuck_jobs.append({
                            **log,
                            "duration_minutes": round(duration_minutes, 1)
                        })
                    else:
                        running_jobs.append({
                            **log,
                            "duration_minutes": round(duration_minutes, 1)
                        })
                except Exception:
                    running_jobs.append(log)
            else:
                running_jobs.append(log)
    
    # Calcular estatísticas
    total_jobs = len(ai_import_logs)
    success_rate = (len(completed_jobs) / total_jobs * 100) if total_jobs > 0 else 0
    
    return {
        "timestamp": now.isoformat(),
        "healthy": len(stuck_jobs) == 0,
        "stats": {
            "total_24h": total_jobs,
            "running": len(running_jobs),
            "stuck": len(stuck_jobs),
            "completed": len(completed_jobs),
            "failed": len(failed_jobs),
            "success_rate": round(success_rate, 1)
        },
        "stuck_jobs": stuck_jobs,
        "running_jobs": running_jobs,
        "alerts": [
            {
                "type": "stuck_job",
                "message": f"Job travado há {job.get('duration_minutes', 0)} minutos: {job.get('job_id', 'N/A')}",
                "job_id": job.get("job_id"),
                "severity": "warning"
            }
            for job in stuck_jobs
        ]
    }


@router.post("/jobs/cancel/{job_id}")
async def cancel_stuck_job(
    job_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Cancela/marca um job travado como falhado.
    """
    # Actualizar log para failed
    result = await db.ai_import_logs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "cancelled",
            "end_time": datetime.now(timezone.utc).isoformat(),
            "cancelled_by": user.get("id"),
            "cancelled_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    return {
        "success": True,
        "job_id": job_id,
        "message": "Job cancelado com sucesso"
    }





# ============== CLIENT REGISTRATIONS MANAGEMENT ==============

@router.get("/client-registrations")
async def list_client_registrations(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    source: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Lista registos de clientes do formulário público.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 20)
    - search: Pesquisar por nome, email ou NIF
    - status: Filtrar por estado do processo
    - source: Filtrar por origem (public_form, manual, etc.)
    """
    query = {}
    
    if search:
        query["$or"] = [
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_email": {"$regex": search, "$options": "i"}},
            {"personal_data.nif": {"$regex": search, "$options": "i"}}
        ]
    
    if status:
        query["status"] = status
    
    if source:
        query["source"] = source
    
    skip = (page - 1) * limit
    
    total = await db.processes.count_documents(query)
    
    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "registrations": processes,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@router.get("/client-registrations/{process_id}")
async def get_client_registration(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém detalhes de um registo de cliente.
    """
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0}
    )
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    return {"registration": process}


@router.put("/client-registrations/{process_id}")
async def update_client_registration(
    process_id: str,
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Atualiza dados de um registo de cliente.
    
    Permite editar:
    - Dados pessoais (personal_data)
    - Dados do 2º titular (titular2_data)
    - Dados do imóvel (real_estate_data)
    - Dados financeiros (financial_data)
    - Informações de contacto (client_name, client_email, client_phone)
    """
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    update_data = {}
    
    # Campos simples
    if "client_name" in data:
        update_data["client_name"] = data["client_name"]
    if "client_email" in data:
        update_data["client_email"] = data["client_email"]
    if "client_phone" in data:
        update_data["client_phone"] = data["client_phone"]
    if "second_client_name" in data:
        update_data["second_client_name"] = data["second_client_name"]
    
    # Campos aninhados
    if "personal_data" in data:
        # Manter dados existentes e atualizar apenas os fornecidos
        existing_personal = process.get("personal_data", {})
        existing_personal.update(data["personal_data"])
        update_data["personal_data"] = existing_personal
    
    if "titular2_data" in data:
        existing_titular2 = process.get("titular2_data", {}) or {}
        existing_titular2.update(data["titular2_data"])
        update_data["titular2_data"] = existing_titular2
    
    if "real_estate_data" in data:
        existing_realestate = process.get("real_estate_data", {}) or {}
        existing_realestate.update(data["real_estate_data"])
        update_data["real_estate_data"] = existing_realestate
    
    if "financial_data" in data:
        existing_financial = process.get("financial_data", {}) or {}
        existing_financial.update(data["financial_data"])
        update_data["financial_data"] = existing_financial
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("email", "admin")
    
    await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    # Log da alteração
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": "Dados do registo editados pelo admin",
        "field": "registration_edit",
        "old_value": None,
        "new_value": list(update_data.keys()),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    return {
        "success": True,
        "message": "Registo atualizado com sucesso",
        "registration": updated
    }


@router.delete("/client-registrations/{process_id}")
async def delete_client_registration(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Elimina um registo de cliente.
    
    NOTA: Esta ação é irreversível e remove todos os dados do processo.
    """
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    # Guardar log antes de eliminar
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": f"Registo eliminado: {process.get('client_name', 'N/A')} ({process.get('client_email', 'N/A')})",
        "field": "registration_delete",
        "old_value": process.get("client_name"),
        "new_value": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Eliminar processo
    await db.processes.delete_one({"id": process_id})
    
    # Eliminar histórico associado
    await db.history.delete_many({"process_id": process_id})
    
    # Eliminar RGPDs associados
    await db.rgpd_requests.delete_many({"process_id": process_id})
    
    return {
        "success": True,
        "message": "Registo eliminado com sucesso"
    }


@router.get("/client-registrations/stats/summary")
async def get_client_registrations_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém estatísticas de registos de clientes.
    """
    # Total de registos
    total = await db.processes.count_documents({})
    
    # Registos por origem
    by_source = await db.processes.aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    # Registos por estado
    by_status = await db.processes.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]).to_list(50)
    
    # Registos hoje
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.processes.count_documents({
        "created_at": {"$gte": today.isoformat()}
    })
    
    # Registos esta semana
    week_start = today - timedelta(days=today.weekday())
    week_count = await db.processes.count_documents({
        "created_at": {"$gte": week_start.isoformat()}
    })
    
    # Registos este mês
    month_start = today.replace(day=1)
    month_count = await db.processes.count_documents({
        "created_at": {"$gte": month_start.isoformat()}
    })
    
    return {
        "total": total,
        "today": today_count,
        "this_week": week_count,
        "this_month": month_count,
        "by_source": {item["_id"] or "unknown": item["count"] for item in by_source},
        "by_status": {item["_id"] or "unknown": item["count"] for item in by_status}
    }


# ============== AUDIT LOGS (O18) ==============

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(100, le=500),
    skip: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    entity: Optional[str] = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """O18 - Lista de audit logs para acções críticas do sistema."""
    query = {}
    if action:
        query["action"] = action
    if entity:
        query["entity"] = entity
    
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(length=limit)
    total = await db.audit_logs.count_documents(query)
    
    return {"logs": logs, "total": total, "limit": limit, "skip": skip}


# ============== STALE PROCESSES STATS ==============

@router.get("/stale-processes")
async def get_stale_processes(
    days: int = Query(14, ge=1, le=90),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Obter estatísticas de processos sem atualização.
    Retorna processos agrupados por nível de urgência.
    """
    now = datetime.now(timezone.utc)
    final_statuses = [
        "concluido", "concluidos", "cancelado", "recusado", 
        "desistiu", "desistencia", "desistencias", "desistência",
        "escritura_feita", "arquivado", "perdido", "eliminado"
    ]
    
    cutoff = (now - timedelta(days=days)).isoformat()
    
    stale = await db.processes.find({
        "status": {"$nin": final_statuses},
        "$or": [
            {"updated_at": {"$lte": cutoff}},
            {"updated_at": {"$exists": False}, "created_at": {"$lte": cutoff}}
        ]
    }, {"_id": 0, "id": 1, "client_name": 1, "status": 1, "consultor_name": 1, 
        "mediador_name": 1, "updated_at": 1, "created_at": 1}).to_list(500)
    
    # Calcular dias desde última atualização
    results = []
    for p in stale:
        last = p.get("updated_at") or p.get("created_at", "")
        try:
            last_date = datetime.fromisoformat(last.replace('Z', '+00:00'))
            days_since = (now - last_date).days
        except (ValueError, TypeError, AttributeError):
            days_since = days
        
        results.append({
            "id": p["id"],
            "client_name": p.get("client_name", ""),
            "status": p.get("status", ""),
            "consultor_name": p.get("consultor_name", ""),
            "mediador_name": p.get("mediador_name", ""),
            "days_since_update": days_since,
            "urgency": "critical" if days_since > 21 else "high" if days_since > 14 else "medium"
        })
    
    results.sort(key=lambda x: x["days_since_update"], reverse=True)
    
    return {
        "total": len(results),
        "critical": len([r for r in results if r["urgency"] == "critical"]),
        "high": len([r for r in results if r["urgency"] == "high"]),
        "medium": len([r for r in results if r["urgency"] == "medium"]),
        "processes": results[:100]
    }

