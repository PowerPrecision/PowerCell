"""
OneDrive Routes - Acesso via link partilhado
Como a API Graph requer autenticação mesmo para links públicos de contas empresariais,
esta implementação fornece URLs diretos para o OneDrive web.
"""
import os
import logging
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException

from database import db
from services.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onedrive", tags=["OneDrive"])

# Configurações
ONEDRIVE_SHARED_LINK = os.environ.get('ONEDRIVE_SHARED_LINK', '')
ONEDRIVE_WEB_URL = os.environ.get('ONEDRIVE_WEB_URL', '')


@router.get("/status")
async def get_onedrive_status(user: dict = Depends(get_current_user)):
    """Verificar estado da integração OneDrive."""
    return {
        "configured": bool(ONEDRIVE_SHARED_LINK),
        "method": "direct_link",
        "shared_link": ONEDRIVE_SHARED_LINK,
        "web_url": ONEDRIVE_WEB_URL
    }


@router.get("/process/{process_id}/folder-url")
async def get_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter URL para abrir a pasta do cliente no OneDrive.
    Retorna o link da pasta principal com sugestão de pesquisa.
    """
    if not ONEDRIVE_SHARED_LINK:
        raise HTTPException(status_code=400, detail="OneDrive não configurado")
    
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    client_name = process.get("client_name", "")
    
    # Verificar se o processo tem um link de pasta guardado
    saved_folder_url = process.get("onedrive_folder_url")
    
    if saved_folder_url:
        return {
            "url": saved_folder_url,
            "client_name": client_name,
            "type": "saved",
            "message": "Link guardado no processo"
        }
    
    # Retornar link da pasta principal
    # O utilizador pode navegar manualmente para encontrar a pasta do cliente
    return {
        "url": ONEDRIVE_SHARED_LINK,
        "web_url": ONEDRIVE_WEB_URL,
        "client_name": client_name,
        "type": "main_folder",
        "message": f"Abrir pasta principal e procurar por '{client_name}'"
    }


@router.put("/process/{process_id}/folder-url")
async def save_process_folder_url(
    process_id: str,
    folder_url: str,
    user: dict = Depends(get_current_user)
):
    """
    Guardar o link da pasta do cliente no processo.
    Permite ao utilizador guardar o link específico da pasta após encontrá-la.
    
    Suporta:
    - OneDrive: https://1drv.ms/..., https://onedrive.live.com/...
    - SharePoint: https://....sharepoint.com/...
    - Google Drive: https://drive.google.com/...
    - S3: s3://bucket/path/...
    - Outros links HTTP/HTTPS
    """
    # Verificar se processo existe
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Validar URL (aceitar múltiplos tipos de cloud storage)
    valid_prefixes = (
        # OneDrive
        "https://1drv.ms/",
        "https://onedrive.live.com/",
        "https://onedrive.sharepoint.com/",
        # SharePoint genérico
        ".sharepoint.com/",
        # Google Drive
        "https://drive.google.com/",
        # AWS S3
        "s3://",
        # HTTP/HTTPS genérico
        "https://",
        "http://",
    )
    
    is_valid = False
    for prefix in valid_prefixes:
        if folder_url.startswith(prefix) or prefix in folder_url:
            is_valid = True
            break
    
    if not is_valid:
        raise HTTPException(
            status_code=400, 
            detail="URL inválido. Use um link de Drive, OneDrive, Google Drive, S3 ou outro serviço de cloud."
        )
    
    # Guardar no processo (campo genérico para compatibilidade)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"onedrive_folder_url": folder_url, "cloud_folder_url": folder_url}}
    )
    
    return {
        "success": True,
        "message": "Link da pasta guardado com sucesso"
    }


@router.delete("/process/{process_id}/folder-url")
async def remove_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Remover o link da pasta do processo."""
    result = await db.processes.update_one(
        {"id": process_id},
        {"$unset": {"onedrive_folder_url": ""}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Processo não encontrado ou link já removido")
    
    return {"success": True, "message": "Link removido"}


@router.post("/process/{process_id}/checklist")
async def generate_document_checklist(
    process_id: str,
    files: list[str],  # Lista de nomes de ficheiros da pasta
    user: dict = Depends(get_current_user)
):
    """
    Gerar checklist de documentos baseada nos ficheiros fornecidos.
    
    O frontend envia a lista de ficheiros que estão na pasta do cliente
    (obtidos via interface do OneDrive ou upload manual).
    
    Returns:
        Checklist com status de cada documento esperado.
    """
    from services.document_checklist import generate_checklist
    
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Determinar tipo de processo (por agora, todos são crédito habitação)
    tipo_processo = "credito_habitacao"
    
    # Gerar checklist
    result = generate_checklist(files, tipo_processo)
    result["client_name"] = process.get("client_name", "")
    result["process_id"] = process_id
    
    # Guardar resultado no processo
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"document_checklist": result}}
    )
    
    return result


@router.get("/process/{process_id}/checklist")
async def get_document_checklist(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter checklist de documentos guardada para um processo.
    """
    process = await db.processes.find_one(
        {"id": process_id},
        {"document_checklist": 1, "client_name": 1, "_id": 0}
    )
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    checklist = process.get("document_checklist")
    
    if not checklist:
        return {
            "checklist": [],
            "resumo": {
                "total_documentos": 0,
                "percentagem_conclusao": 0,
            },
            "message": "Checklist ainda não gerada. Envie a lista de ficheiros para gerar."
        }
    
    return checklist


# ============================================
# Endpoints para listagem de ficheiros (S3 Storage)
# ============================================

@router.get("/files/{client_name}")
async def get_client_files_by_name(
    client_name: str,
    subfolder: str = "",
    user: dict = Depends(get_current_user)
):
    """
    Listar ficheiros de um cliente pelo nome.
    Redireciona para o serviço S3 de documentos.
    
    Este endpoint mantém compatibilidade com o frontend que usa o nome do cliente.
    """
    from services.s3_storage import s3_service
    
    # Procurar processo pelo nome do cliente
    process = await db.processes.find_one(
        {"client_name": {"$regex": f"^{client_name}$", "$options": "i"}},
        {"_id": 0, "id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1}
    )
    
    if not process:
        # Tentar busca parcial
        process = await db.processes.find_one(
            {"client_name": {"$regex": client_name, "$options": "i"}},
            {"_id": 0, "id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1}
        )
    
    if not process:
        return {"files": [], "folders": [], "message": f"Cliente '{client_name}' não encontrado"}
    
    client_id = process.get("id")
    real_client_name = process.get("client_name", client_name)
    second_client_name = process.get("second_client_name") or \
                         process.get("titular2_data", {}).get("nome")
    
    # Obter ficheiros do S3
    files_data = s3_service.list_files(client_id, real_client_name, second_client_name)
    
    return files_data


# ============================================
# Endpoints para Links adicionais (OneDrive, Google Drive, S3, etc.)
# ============================================

from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime, timezone

class LinkCreate(BaseModel):
    name: str
    url: str
    description: Optional[str] = ""

class LinkUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None


@router.get("/links/{process_id}")
async def get_process_links(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter todos os links de um processo.
    """
    # Verificar se o processo existe (sem projection para evitar problema de dict vazio)
    process_exists = await db.processes.find_one(
        {"id": process_id},
        {"id": 1}
    )
    
    if not process_exists:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Buscar os links separadamente
    process = await db.processes.find_one(
        {"id": process_id},
        {"onedrive_links": 1, "_id": 0}
    )
    
    return process.get("onedrive_links") if process else []


@router.post("/links/{process_id}")
async def add_process_link(
    process_id: str,
    link_data: LinkCreate,
    user: dict = Depends(get_current_user)
):
    """
    Adicionar um novo link a um processo.
    Suporta OneDrive, Google Drive, S3, SharePoint e outros URLs.
    """
    # Verificar se processo existe
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Validar URL
    valid_prefixes = (
        "https://", "http://", "s3://",
        "https://1drv.ms/", "https://onedrive.live.com/",
        "https://drive.google.com/", ".sharepoint.com/"
    )
    
    is_valid = any(link_data.url.startswith(p) or p in link_data.url for p in valid_prefixes)
    
    if not is_valid:
        raise HTTPException(
            status_code=400, 
            detail="URL inválido. Use um link HTTP/HTTPS válido."
        )
    
    # Criar novo link
    new_link = {
        "id": str(uuid.uuid4()),
        "name": link_data.name,
        "url": link_data.url,
        "description": link_data.description or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.get("id") or user.get("email")
    }
    
    # Adicionar ao array de links
    await db.processes.update_one(
        {"id": process_id},
        {"$push": {"onedrive_links": new_link}}
    )
    
    logger.info(f"Link adicionado ao processo {process_id}: {link_data.name}")
    
    return new_link


@router.delete("/links/{process_id}/{link_id}")
async def delete_process_link(
    process_id: str,
    link_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Remover um link de um processo.
    """
    # Verificar se processo existe
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Remover o link pelo ID
    result = await db.processes.update_one(
        {"id": process_id},
        {"$pull": {"onedrive_links": {"id": link_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    logger.info(f"Link {link_id} removido do processo {process_id}")
    
    return {"success": True, "message": "Link removido com sucesso"}


@router.put("/links/{process_id}/{link_id}")
async def update_process_link(
    process_id: str,
    link_id: str,
    link_data: LinkUpdate,
    user: dict = Depends(get_current_user)
):
    """
    Actualizar um link existente.
    """
    # Verificar se processo existe
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Construir campos para actualizar
    update_fields = {}
    if link_data.name is not None:
        update_fields["onedrive_links.$.name"] = link_data.name
    if link_data.url is not None:
        update_fields["onedrive_links.$.url"] = link_data.url
    if link_data.description is not None:
        update_fields["onedrive_links.$.description"] = link_data.description
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para actualizar")
    
    # Actualizar o link
    result = await db.processes.update_one(
        {"id": process_id, "onedrive_links.id": link_id},
        {"$set": update_fields}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    return {"success": True, "message": "Link actualizado com sucesso"}

