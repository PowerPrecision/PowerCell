"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - MAPEAMENTO DE STORAGE (S3)
====================================================================
Extraído de admin.py para melhor organização.
Inclui: Mapeamento de utilizadores e clientes/processos para pastas S3.
Inclui: Operações de ficheiros S3 (upload, rename, delete, create folder, download).
====================================================================
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io

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


@router.post("/client-s3-mappings/fix-missing-names")
async def fix_missing_client_names_alias(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Alias para fix-missing-names (retrocompatibilidade)."""
    return await fix_missing_client_names(user=user)


@router.post("/client-s3-mappings/auto-map")
async def auto_map_client_s3_folders(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Mapeamento automático de pastas S3 para processos baseado em nome.
    
    Se o processo não tiver client_name, o nome da pasta é usado para preencher.
    """
    from services.s3_storage import s3_service
    
    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")
    
    results = {"mapped": 0, "skipped": 0, "updated_names": 0, "errors": []}
    
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
            
            # Tentar converter nome da pasta para formato legível (underscores -> espaços)
            folder_name_readable = folder_name.replace("_", " ").replace("  ", " ")
            
            # Procurar processo pelo nome do cliente (exact match case-insensitive)
            process = await db.processes.find_one(
                {"client_name": {"$regex": f"^{folder_name}$", "$options": "i"}},
                {"_id": 0, "id": 1, "s3_folder": 1, "client_name": 1}
            )
            
            # Se não encontrou, tentar com nome legível
            if not process:
                process = await db.processes.find_one(
                    {"client_name": {"$regex": f"^{folder_name_readable}$", "$options": "i"}},
                    {"_id": 0, "id": 1, "s3_folder": 1, "client_name": 1}
                )
            
            # Se ainda não encontrou, tentar match parcial
            if not process:
                # Procurar por processos que contenham o nome da pasta ou vice-versa
                name_parts = folder_name.replace("_", " ").split()
                if len(name_parts) >= 2:
                    # Usar primeiros nomes para match mais flexível
                    first_name = name_parts[0]
                    last_name = name_parts[-1]
                    process = await db.processes.find_one(
                        {"client_name": {"$regex": f"{first_name}.*{last_name}", "$options": "i"}},
                        {"_id": 0, "id": 1, "s3_folder": 1, "client_name": 1}
                    )
            
            if process:
                update_fields = {"s3_folder": folder["path"]}
                
                # Se o processo não tem client_name, usar o nome da pasta
                if not process.get("client_name") or process.get("client_name") == "Sem nome":
                    update_fields["client_name"] = folder_name_readable
                    results["updated_names"] += 1
                
                if not process.get("s3_folder"):
                    await db.processes.update_one(
                        {"id": process["id"]},
                        {"$set": update_fields}
                    )
                    results["mapped"] += 1
                else:
                    results["skipped"] += 1
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
    """Actualiza o mapeamento de um utilizador para uma pasta S3."""
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
    include_deleted: bool = Query(False, description="Incluir processos eliminados"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista mapeamentos de processos para pastas S3."""
    query = {}
    
    # Por defeito, excluir processos concluídos e desistências
    if not include_closed:
        query["status"] = {"$nin": ["concluidos", "desistencias"]}
    
    # Por defeito, excluir processos eliminados (soft delete)
    if not include_deleted:
        query["is_active"] = {"$ne": False}
        # Também excluir por status "eliminado" para compatibilidade
        if "status" in query:
            query["status"]["$nin"] = list(set(query["status"].get("$nin", []) + ["eliminado"]))
        else:
            query["status"] = {"$ne": "eliminado"}
    
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
    """Actualiza o mapeamento de um processo para uma pasta S3."""
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


@router.post("/process-s3-mappings/fix-missing-names")
async def fix_missing_client_names(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Corrige processos que não têm client_name definido.
    Extrai o nome da pasta S3 mapeada ou do email do cliente.
    """
    fixed_count = 0
    
    # Processos sem nome ou com nome "Sem nome"
    processes_without_name = await db.processes.find({
        "$or": [
            {"client_name": None},
            {"client_name": ""},
            {"client_name": "Sem nome"},
            {"client_name": {"$exists": False}}
        ]
    }).to_list(1000)
    
    for process in processes_without_name:
        new_name = None
        
        # 1. Tentar extrair da pasta S3
        s3_folder = process.get("s3_folder")
        if s3_folder:
            # Extrair nome da pasta: "Documentação Clientes/Nome_Cliente" -> "Nome Cliente"
            folder_name = s3_folder.replace("Documentação Clientes/", "").rstrip("/")
            if folder_name:
                new_name = folder_name.replace("_", " ").replace("  ", " ")
        
        # 2. Tentar extrair do email
        if not new_name:
            email = process.get("client_email")
            if email and "@" in email:
                email_name = email.split("@")[0]
                new_name = email_name.replace(".", " ").replace("_", " ").replace("-", " ").title()
        
        # 3. Tentar extrair de personal_data
        if not new_name:
            personal = process.get("personal_data", {})
            new_name = (
                personal.get("nome_completo") or 
                personal.get("nome") or 
                personal.get("name")
            )
        
        # 4. Se ainda não temos nome, usar "Cliente" com número do processo
        if not new_name:
            process_num = process.get("process_number", "Desconhecido")
            new_name = f"Cliente #{process_num}"
        
        # Actualizar o processo
        if new_name:
            await db.processes.update_one(
                {"id": process["id"]},
                {"$set": {"client_name": new_name, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            fixed_count += 1
    
    return {
        "success": True,
        "message": f"Corrigidos {fixed_count} processos sem nome",
        "fixed_count": fixed_count,
        "total_found": len(processes_without_name)
    }


@router.post("/process-s3-mappings/batch")
async def batch_update_process_s3_mappings(
    mappings: List[dict] = Body(...),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Actualiza mapeamentos S3 em batch para múltiplos processos."""
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
    folder_path: str = Query("", description="Caminho da pasta S3 (vazio = raiz)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO]))
):
    """Lista conteúdo de uma pasta S3. Se folder_path vazio, lista a raiz do bucket (Documentação Clientes/)."""
    from services.s3_storage import s3_service
    
    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")
    
    # Se folder_path vazio, usar a pasta principal "Documentação Clientes/" como raiz
    prefix = folder_path.strip()
    if not prefix:
        # Listar "Documentação Clientes/" como pasta raiz do explorador
        prefix = "Documentação Clientes"
    
    try:
        list_prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        response = s3_service.s3_client.list_objects_v2(
            Bucket=s3_service.bucket_name,
            Prefix=list_prefix,
            Delimiter="/"
        )
        
        subfolders = []
        for common_prefix in response.get("CommonPrefixes", []):
            subfolder_path = common_prefix.get("Prefix", "")
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
            if key != list_prefix and not key.endswith("/"):
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


# ============== S3 FILE OPERATIONS ==============
# Endpoints for the File Explorer (rename, delete, create folder, upload, download)

# Roles that can perform file operations
FILE_OPS_ROLES = [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
# Roles that can view/download files (broader access)
FILE_VIEW_ROLES = [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO]


class S3RenameRequest(BaseModel):
    old_path: str
    new_name: str
    is_folder: bool = False


class S3DeleteRequest(BaseModel):
    path: str
    is_folder: bool = False


class S3CreateFolderRequest(BaseModel):
    folder_path: str


@router.post("/s3-rename")
async def s3_rename(
    data: S3RenameRequest,
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    """Renomeia um ficheiro ou pasta no S3 (copy + delete)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    old_path = data.old_path
    new_name = data.new_name.strip()

    if not old_path or not new_name:
        raise HTTPException(status_code=400, detail="Caminho original e novo nome são obrigatórios")

    # Build the new path: replace the last segment with the new name
    path_parts = old_path.rstrip("/").split("/")
    path_parts[-1] = new_name
    new_path = "/".join(path_parts)

    # If it's a folder, we need to rename all objects with the old prefix
    if data.is_folder:
        try:
            old_prefix = old_path.rstrip("/") + "/"
            new_prefix = new_path.rstrip("/") + "/"

            # List all objects under the old prefix
            response = s3_service.s3_client.list_objects_v2(
                Bucket=s3_service.bucket_name,
                Prefix=old_prefix
            )

            moved_count = 0
            for obj in response.get("Contents", []):
                old_key = obj["Key"]
                # Replace old prefix with new prefix
                new_key = new_prefix + old_key[len(old_prefix):]

                # Copy to new location
                copy_source = {'Bucket': s3_service.bucket_name, 'Key': old_key}
                s3_service.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=s3_service.bucket_name,
                    Key=new_key
                )

                # Delete from old location
                s3_service.s3_client.delete_object(
                    Bucket=s3_service.bucket_name,
                    Key=old_key
                )
                moved_count += 1

            logger.info(f"Pasta renomeada: {old_path} -> {new_path} ({moved_count} objetos movidos)")
            return {"success": True, "old_path": old_path, "new_path": new_path, "objects_moved": moved_count}

        except Exception as e:
            logger.error(f"Erro ao renomear pasta S3: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao renomear pasta: {str(e)}")
    else:
        # Rename a single file
        success = s3_service.rename_file(old_path, new_path)
        if success:
            return {"success": True, "old_path": old_path, "new_path": new_path}
        else:
            raise HTTPException(status_code=500, detail="Erro ao renomear ficheiro")


@router.post("/s3-delete")
async def s3_delete(
    data: S3DeleteRequest,
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    """Elimina um ficheiro ou pasta (e todo o seu conteúdo) do S3."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    path = data.path
    if not path:
        raise HTTPException(status_code=400, detail="Caminho é obrigatório")

    if data.is_folder:
        try:
            prefix = path.rstrip("/") + "/"

            # List all objects under the prefix
            deleted_count = 0
            continuation_token = None

            while True:
                kwargs = {
                    "Bucket": s3_service.bucket_name,
                    "Prefix": prefix,
                }
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token

                response = s3_service.s3_client.list_objects_v2(**kwargs)

                for obj in response.get("Contents", []):
                    s3_service.s3_client.delete_object(
                        Bucket=s3_service.bucket_name,
                        Key=obj["Key"]
                    )
                    deleted_count += 1

                if response.get("IsTruncated"):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    break

            logger.info(f"Pasta eliminada: {path} ({deleted_count} objetos removidos)")
            return {"success": True, "path": path, "objects_deleted": deleted_count}

        except Exception as e:
            logger.error(f"Erro ao eliminar pasta S3: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao eliminar pasta: {str(e)}")
    else:
        # Delete a single file
        success = s3_service.delete_file(path)
        if success:
            return {"success": True, "path": path}
        else:
            raise HTTPException(status_code=500, detail="Erro ao eliminar ficheiro")


@router.post("/s3-create-folder")
async def s3_create_folder(
    data: S3CreateFolderRequest,
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    """Cria uma pasta no S3 (cria um ficheiro marcador .keep vazio)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    folder_path = data.folder_path.strip()
    if not folder_path:
        raise HTTPException(status_code=400, detail="Caminho da pasta é obrigatório")

    # Ensure path ends with /
    if not folder_path.endswith("/"):
        folder_path += "/"

    # Create a .keep marker file to represent the folder
    marker_path = folder_path + ".keep"

    try:
        s3_service.s3_client.put_object(
            Bucket=s3_service.bucket_name,
            Key=marker_path,
            Body=b"",
            ContentType="application/x-directory"
        )
        logger.info(f"Pasta criada no S3: {folder_path}")
        return {"success": True, "folder_path": folder_path, "marker": marker_path}
    except Exception as e:
        logger.error(f"Erro ao criar pasta S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar pasta: {str(e)}")


@router.post("/s3-upload")
async def s3_upload(
    file: UploadFile = File(...),
    folder_path: str = Form(""),
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    """Faz upload de um ficheiro para uma pasta S3 (usado pelo File Explorer)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Ficheiro é obrigatório")

    # Build the S3 key
    base_path = folder_path.strip()
    if base_path and not base_path.endswith("/"):
        base_path += "/"

    s3_key = f"{base_path}{file.filename}"

    try:
        content = await file.read()
        content_type = file.content_type or "application/octet-stream"

        s3_service.s3_client.put_object(
            Bucket=s3_service.bucket_name,
            Key=s3_key,
            Body=content,
            ContentType=content_type
        )

        logger.info(f"Ficheiro enviado para S3: {s3_key} ({len(content)} bytes)")
        return {
            "success": True,
            "path": s3_key,
            "filename": file.filename,
            "size": len(content),
            "content_type": content_type
        }
    except Exception as e:
        logger.error(f"Erro ao fazer upload para S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar ficheiro: {str(e)}")


@router.get("/s3-download")
async def s3_download(
    path: str = Query(..., description="Caminho S3 do ficheiro"),
    user: dict = Depends(require_roles(FILE_VIEW_ROLES))
):
    """Faz download de um ficheiro do S3 (streaming response)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    if not path:
        raise HTTPException(status_code=400, detail="Caminho é obrigatório")

    try:
        response = s3_service.s3_client.get_object(
            Bucket=s3_service.bucket_name,
            Key=path
        )

        filename = path.split("/")[-1]
        content_type = response.get("ContentType", "application/octet-stream")

        def iterfile():
            chunk_size = 8192
            stream = response["Body"]
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        }

        return StreamingResponse(
            iterfile(),
            media_type=content_type,
            headers=headers
        )
    except Exception as e:
        logger.error(f"Erro ao fazer download do S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao fazer download: {str(e)}")
