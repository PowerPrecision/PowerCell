"""Property document upload / list / delete.

Extraído de `routes/properties.py`.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile

from database import db
from models.property import PropertyHistory

logger = logging.getLogger(__name__)


async def run_upload_property_document(
    property_id: str,
    file: UploadFile,
    user: dict,
    document_type: str = 'outro',
    description: str = None
):
    """
    Upload de documento para um imóvel da empresa.
    
    Tipos de documento:
    - caderneta_predial
    - certidao_registo
    - licenca_utilizacao
    - planta
    - cpcv
    - contrato
    - outro
    """
    from services.s3_service import upload_file_to_s3
    
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Validar tipo de documento
    valid_types = [
        "caderneta_predial", "certidao_registo", "licenca_utilizacao",
        "planta", "cpcv", "contrato", "foto", "outro"
    ]
    if document_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {valid_types}")
    
    # Validar ficheiro
    allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx']
    file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Tipo de ficheiro não permitido. Use: {allowed_extensions}")
    
    # Ler conteúdo
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB max
        raise HTTPException(status_code=400, detail="Ficheiro muito grande (máx 20MB)")
    
    try:
        # Upload para S3
        s3_path = f"properties/{property_id}/documents/{document_type}_{file.filename}"
        result = await upload_file_to_s3(content, s3_path, file.content_type)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Erro no upload: {result.get('error')}")
        
        # Criar registo do documento
        doc_record = {
            "id": str(uuid.uuid4()),
            "filename": file.filename,
            "document_type": document_type,
            "description": description,
            "s3_key": result.get("key"),
            "url": result.get("url"),
            "size": len(content),
            "mime_type": file.content_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_by": user.get("email")
        }
        
        # Adicionar ao array de documentos do imóvel
        await db.properties.update_one(
            {"id": property_id},
            {
                "$push": {"documents": doc_record},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )
        
        # Registar no histórico
        await db.properties.update_one(
            {"id": property_id},
            {
                "$push": {
                    "history": PropertyHistory(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        event=f"Documento adicionado: {file.filename} ({document_type})",
                        user=user.get("email")
                    ).model_dump()
                }
            }
        )
        
        return {
            "success": True,
            "document": doc_record,
            "message": f"Documento {file.filename} carregado com sucesso"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao carregar documento para imóvel {property_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao carregar documento: {str(e)}")


async def run_get_property_documents(
    property_id: str,
    user: dict,
    document_type: str = None
):
    """
    Listar documentos de um imóvel.
    """
    prop = await db.properties.find_one(
        {"id": property_id},
        {"_id": 0, "documents": 1}
    )
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    documents = prop.get("documents", [])
    
    # Filtrar por tipo se especificado
    if document_type:
        documents = [d for d in documents if d.get("document_type") == document_type]
    
    return {
        "property_id": property_id,
        "total": len(documents),
        "documents": documents
    }


async def run_delete_property_document(
    property_id: str,
    document_id: str,
    user: dict
):
    """
    Remover documento de um imóvel.
    """
    from services.s3_service import delete_file_from_s3
    
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Encontrar documento
    document = None
    for doc in prop.get("documents", []):
        if doc.get("id") == document_id:
            document = doc
            break
    
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    
    # Remover do S3
    if document.get("s3_key"):
        try:
            await delete_file_from_s3(document["s3_key"])
        except Exception as e:
            logger.warning(f"Erro ao remover do S3: {e}")
    
    # Remover do array
    await db.properties.update_one(
        {"id": property_id},
        {
            "$pull": {"documents": {"id": document_id}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    # Registar no histórico
    await db.properties.update_one(
        {"id": property_id},
        {
            "$push": {
                "history": PropertyHistory(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event=f"Documento removido: {document.get('filename')}",
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Documento removido"}
