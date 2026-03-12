"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - MAPEAMENTO DE STORAGE (S3)
====================================================================
Extraído de admin.py para melhor organização.
Inclui: Mapeamento de utilizadores e clientes/processos para pastas S3.
====================================================================
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body

from database import db
from models.auth import UserRole
from services.auth import require_roles


router = APIRouter(prefix="/admin", tags=["Admin - Storage"])
logger = logging.getLogger(__name__)


# ============== ALIAS PARA RETROCOMPATIBILIDADE ==============
# O frontend usa "client-s3-mappings" mas o backend usa "process-s3-mappings"

@router.get("/client-s3-mappings")
async def get_client_s3_mappings_alias(
    search: str = Query(None),
    process_id: str = Query(None),
    s3_folder: str = Query(None),
    include_closed: bool = Query(False, description="Incluir processos concluídos e desistências"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Alias para process-s3-mappings (retrocompatibilidade)."""
    return await get_process_s3_mappings(
        search=search,
        status=None,
        has_mapping=None,
        include_closed=include_closed,
        page=page,
        limit=limit,
        user=user
    )


@router.post("/client-s3-mappings")
async def update_client_s3_mapping_alias(
    process_id: str = Query(...),
    s3_folder: str = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Alias para process-s3-mappings (retrocompatibilidade)."""
    return await update_process_s3_mapping(process_id=process_id, s3_folder=s3_folder, user=user)


@router.post("/client-s3-mappings/bulk")
async def batch_update_client_s3_mappings_alias(
    mappings: List[dict] = Body(...),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Alias para batch update (retrocompatibilidade)."""
    return await batch_update_process_s3_mappings(mappings=mappings, user=user)


@router.post("/client-s3-mappings/auto-map")
async def auto_map_client_s3_folders(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Mapeamento automático de pastas S3 para processos baseado em nome."""
    from services.s3_storage import s3_service
    
    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")
    
    results = {"mapped": 0, "skipped": 0, "errors": []}
    
    try:
        # Listar pastas S3
        response = s3_service.s3_client.list_objects_v2(
            Bucket=s3_service.bucket_name,
            Prefix="Documentação Clientes/",
            Delimiter="/"
        )
        
        folders = []
        for prefix in response.get("CommonPrefixes", []):
            folder_path = prefix.get("Prefix", "").rstrip("/")
            folder_name = folder_path.replace("Documentação Clientes/", "")
            if folder_name:
                folders.append({"path": folder_path, "name": folder_name})
        
        # Para cada pasta, tentar encontrar processo correspondente
        for folder in folders:
            folder_name = folder["name"]
            
            # Procurar processo pelo nome do cliente
            process = await db.processes.find_one(
                {"client_name": {"$regex": f"^{folder_name}$", "$options": "i"}},
                {"_id": 0, "id": 1, "s3_folder": 1}
            )
            
            if process and not process.get("s3_folder"):
                await db.processes.update_one(
                    {"id": process["id"]},
                    {"$set": {"s3_folder": folder["path"]}}
                )
                results["mapped"] += 1
            else:
                results["skipped"] += 1
                
    except Exception as e:
        results["errors"].append(str(e))
    
    return results


# ============== MAPEAMENTO UTILIZADORES-S3 ==============

@router.get("/user-s3-mappings")
async def get_user_s3_mappings(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista mapeamentos de utilizadores para pastas S3."""
    users = await db.users.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "s3_folder": 1, "role": 1}
    ).to_list(500)
    
    from services.s3_storage import s3_service
    available_folders = []
    
    if s3_service.is_configured():
        try:
            response = s3_service.s3_client.list_objects_v2(
                Bucket=s3_service.bucket_name,
                Prefix="Documentação Clientes/",
                Delimiter="/"
            )
            
            for prefix in response.get("CommonPrefixes", []):
                folder_path = prefix.get("Prefix", "")
                folder_name = folder_path.replace("Documentação Clientes/", "").rstrip("/")
                if folder_name:
                    available_folders.append({
                        "path": folder_path.rstrip("/"),
                        "name": folder_name
                    })
        except Exception as e:
            logger.warning(f"Erro ao listar pastas S3: {e}")
    
    return {
        "users": users,
        "available_folders": available_folders,
        "s3_configured": s3_service.is_configured()
    }


@router.post("/user-s3-mappings")
async def update_user_s3_mapping(
    user_id: str = Query(...),
    s3_folder: str = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Atualiza o mapeamento de um utilizador para uma pasta S3."""
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    update_data = {
        "s3_folder": s3_folder,
        "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
        "s3_mapping_updated_by": user["id"]
    }
    
    await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )
    
    await db.activity_logs.insert_one({
        "type": "user_s3_mapping_updated",
        "user_id": user_id,
        "updated_by": user["id"],
        "s3_folder": s3_folder,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    return {"success": True, "user_id": user_id, "s3_folder": s3_folder}


@router.get("/user-s3-mappings/{user_id}")
async def get_user_s3_mapping(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém mapeamento S3 de um utilizador específico."""
    target_user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "s3_folder": 1, "role": 1}
    )
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    return target_user


# ============== MAPEAMENTO CLIENTES/PROCESSOS-S3 ==============

@router.get("/process-s3-mappings")
async def get_process_s3_mappings(
    search: str = Query(None, description="Pesquisar por nome ou email"),
    status: str = Query(None, description="Filtrar por status"),
    has_mapping: bool = Query(None, description="Filtrar por ter/não ter mapeamento"),
    include_closed: bool = Query(False, description="Incluir processos concluídos e desistências"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista mapeamentos de processos para pastas S3."""
    query = {}
    
    # Por defeito, excluir processos concluídos e desistências
    if not include_closed:
        query["status"] = {"$nin": ["concluidos", "desistencias"]}
    
    if search:
        query["$or"] = [
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_email": {"$regex": search, "$options": "i"}},
            {"process_number": {"$regex": search, "$options": "i"}}
        ]
    
    if status:
        query["status"] = status
    
    if has_mapping is not None:
        if has_mapping:
            query["s3_folder"] = {"$exists": True, "$nin": [None, ""]}
        else:
            query["$or"] = [
                {"s3_folder": {"$exists": False}},
                {"s3_folder": None},
                {"s3_folder": ""}
            ]
    
    skip = (page - 1) * limit
    
    total = await db.processes.count_documents(query)
    
    # Contar processos com e sem mapeamento S3
    mapped_count = await db.processes.count_documents({
        **query,
        "s3_folder": {"$exists": True, "$ne": None, "$ne": ""}
    })
    unmapped_count = total - mapped_count
    
    processes = await db.processes.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_number": 1,
            "client_name": 1,
            "client_email": 1,
            "status": 1,
            "s3_folder": 1,
            "created_at": 1
        }
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    from services.s3_storage import s3_service
    available_folders = []
    
    if s3_service.is_configured():
        try:
            response = s3_service.s3_client.list_objects_v2(
                Bucket=s3_service.bucket_name,
                Prefix="Documentação Clientes/",
                Delimiter="/"
            )
            
            for prefix in response.get("CommonPrefixes", []):
                folder_path = prefix.get("Prefix", "")
                folder_name = folder_path.replace("Documentação Clientes/", "").rstrip("/")
                if folder_name:
                    available_folders.append({
                        "path": folder_path.rstrip("/"),
                        "name": folder_name
                    })
        except Exception as e:
            logger.warning(f"Erro ao listar pastas S3: {e}")
    
    return {
        "processes": processes,
        "available_folders": available_folders,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "s3_configured": s3_service.is_configured(),
        "stats": {
            "total": total,
            "mapped": mapped_count,
            "unmapped": unmapped_count
        }
    }


@router.post("/process-s3-mappings")
async def update_process_s3_mapping(
    process_id: str = Query(...),
    s3_folder: str = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Atualiza o mapeamento de um processo para uma pasta S3."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Validar s3_folder - não guardar "undefined", "null" ou strings inválidas
    clean_s3_folder = s3_folder
    if s3_folder in [None, "", "undefined", "null", "None"]:
        clean_s3_folder = None
    
    update_data = {
        "s3_folder": clean_s3_folder,
        "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
        "s3_mapping_updated_by": user["id"]
    }
    
    await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    await db.activity_logs.insert_one({
        "type": "process_s3_mapping_updated",
        "process_id": process_id,
        "updated_by": user["id"],
        "s3_folder": clean_s3_folder,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    return {"success": True, "process_id": process_id, "s3_folder": clean_s3_folder, "client_name": process.get("client_name")}


@router.post("/process-s3-mappings/batch")
async def batch_update_process_s3_mappings(
    mappings: List[dict] = Body(...),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Atualiza mapeamentos S3 em batch para múltiplos processos."""
    results = {"updated": 0, "failed": 0, "errors": []}
    
    for mapping in mappings:
        process_id = mapping.get("process_id")
        s3_folder = mapping.get("s3_folder")
        
        if not process_id:
            results["failed"] += 1
            results["errors"].append({"error": "process_id é obrigatório"})
            continue
        
        try:
            process = await db.processes.find_one({"id": process_id})
            if not process:
                results["failed"] += 1
                results["errors"].append({"process_id": process_id, "error": "Processo não encontrado"})
                continue
            
            # Validar s3_folder - não guardar "undefined", "null" ou strings inválidas
            clean_s3_folder = s3_folder
            if s3_folder in [None, "", "undefined", "null", "None"]:
                clean_s3_folder = None
            
            update_data = {
                "s3_folder": clean_s3_folder,
                "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
                "s3_mapping_updated_by": user["id"]
            }
            
            await db.processes.update_one(
                {"id": process_id},
                {"$set": update_data}
            )
            
            results["updated"] += 1
            
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"process_id": process_id, "error": str(e)})
    
    # Retornar formato esperado pelo frontend
    return {
        "success": results["failed"] == 0 or results["updated"] > 0,
        "updated": results["updated"],
        "failed": results["failed"],
        "errors": results["errors"]
    }


@router.get("/s3-folder-contents")
async def get_s3_folder_contents(
    folder_path: str = Query(...),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista conteúdo de uma pasta S3."""
    from services.s3_storage import s3_service
    
    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")
    
    try:
        response = s3_service.s3_client.list_objects_v2(
            Bucket=s3_service.bucket_name,
            Prefix=folder_path if folder_path.endswith("/") else f"{folder_path}/",
            Delimiter="/"
        )
        
        subfolders = []
        for prefix in response.get("CommonPrefixes", []):
            subfolder_path = prefix.get("Prefix", "")
            parts = subfolder_path.rstrip("/").split("/")
            subfolder_name = parts[-1] if parts else ""
            if subfolder_name:
                subfolders.append({
                    "path": subfolder_path.rstrip("/"),
                    "name": subfolder_name
                })
        
        files = []
        for obj in response.get("Contents", []):
            key = obj.get("Key", "")
            if key != folder_path and not key.endswith("/"):
                file_name = key.split("/")[-1]
                files.append({
                    "path": key,
                    "name": file_name,
                    "size": obj.get("Size", 0),
                    "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None
                })
        
        return {
            "folder_path": folder_path,
            "subfolders": subfolders,
            "files": files,
            "total_items": len(subfolders) + len(files)
        }
        
    except Exception as e:
        logger.error(f"Erro ao listar conteúdo S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar pasta: {str(e)}")
