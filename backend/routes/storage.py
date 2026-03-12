"""
====================================================================
ROTAS DE STORAGE GENÉRICO
====================================================================
Endpoints para gestão de links de armazenamento.
Funciona independentemente do provider configurado (S3, OneDrive, 
Google Drive, Dropbox).

A ideia é que cada processo pode ter um link de pasta associado
para facilitar a navegação do utilizador.
====================================================================
"""
import os
from fastapi import APIRouter, Depends, HTTPException

from database import db
from routes.auth import get_current_user

router = APIRouter(prefix="/storage", tags=["Storage"])


@router.get("/status")
async def get_storage_status(user: dict = Depends(get_current_user)):
    """
    Obter status do armazenamento configurado.
    
    Verifica qual provider de storage está activo (S3, OneDrive, etc.)
    e retorna informações sobre a configuração.
    """
    # Verificar S3
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    aws_bucket = os.environ.get("AWS_BUCKET_NAME", "")
    aws_region = os.environ.get("AWS_REGION", "")
    
    s3_configured = bool(aws_key and aws_bucket)
    
    # Verificar OneDrive
    onedrive_link = os.environ.get("ONEDRIVE_SHARED_LINK", "")
    onedrive_configured = bool(onedrive_link)
    
    # Determinar provider activo
    if s3_configured:
        return {
            "configured": True,
            "provider": "AWS S3",
            "provider_icon": "cloud",
            "bucket": aws_bucket,
            "region": aws_region,
            "message": f"Armazenamento AWS S3 configurado ({aws_bucket})"
        }
    elif onedrive_configured:
        return {
            "configured": True,
            "provider": "OneDrive",
            "provider_icon": "folder",
            "shared_link": onedrive_link[:50] + "..." if len(onedrive_link) > 50 else onedrive_link,
            "message": "Armazenamento OneDrive configurado"
        }
    else:
        return {
            "configured": False,
            "provider": None,
            "message": "Nenhum armazenamento configurado"
        }


@router.get("/process/{process_id}/folder-url")
async def get_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter URL da pasta do cliente no storage configurado.
    
    Retorna o link guardado no processo, se existir.
    Funciona com qualquer provider de storage.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    client_name = process.get("client_name", "")
    
    # Verificar se o processo tem um link de pasta guardado
    # Tentar diferentes campos (para compatibilidade com dados antigos)
    saved_folder_url = (
        process.get("storage_folder_url") or 
        process.get("onedrive_folder_url") or
        process.get("drive_folder_url")
    )
    
    if saved_folder_url:
        return {
            "url": saved_folder_url,
            "client_name": client_name,
            "type": "saved",
            "message": "Link guardado no processo"
        }
    
    # Não há link guardado
    return {
        "url": None,
        "client_name": client_name,
        "type": "none",
        "message": "Nenhum link de pasta configurado para este processo"
    }


@router.put("/process/{process_id}/folder-url")
async def save_process_folder_url(
    process_id: str,
    folder_url: str,
    user: dict = Depends(get_current_user)
):
    """
    Guardar o link da pasta do cliente no processo.
    
    Permite ao utilizador guardar o link específico da pasta.
    Suporta qualquer URL válido (OneDrive, Google Drive, S3, etc.).
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Validar URL básico
    if not folder_url or len(folder_url) < 5:
        raise HTTPException(status_code=400, detail="URL inválido")
    
    # Guardar no campo genérico
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"storage_folder_url": folder_url}}
    )
    
    return {
        "success": True,
        "message": "Link da pasta guardado com sucesso",
        "url": folder_url
    }


@router.delete("/process/{process_id}/folder-url")
async def delete_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Remover o link da pasta do processo.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Remover todos os campos de folder URL (para limpeza)
    await db.processes.update_one(
        {"id": process_id},
        {"$unset": {
            "storage_folder_url": "",
            "onedrive_folder_url": "",
            "drive_folder_url": ""
        }}
    )
    
    return {
        "success": True,
        "message": "Link da pasta removido"
    }


@router.post("/process/{process_id}/checklist")
async def generate_document_checklist(
    process_id: str,
    files: list[str],
    user: dict = Depends(get_current_user)
):
    """
    Gerar checklist de documentos baseada nos ficheiros fornecidos.
    
    O frontend envia a lista de ficheiros que estão na pasta do cliente.
    """
    from services.document_checklist import generate_checklist
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    tipo_processo = "credito_habitacao"
    
    result = generate_checklist(files, tipo_processo)
    result["client_name"] = process.get("client_name", "")
    result["process_id"] = process_id
    
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
            "client_name": process.get("client_name", ""),
            "process_id": process_id
        }
    
    return checklist
