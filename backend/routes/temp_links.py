"""
====================================================================
ROTAS DE LINKS TEMPORÁRIOS - CREDITOIMO
====================================================================
Links temporários para upload e download de documentação.

Funcionalidades:
- Criar links de upload para clientes
- Criar links de download para clientes  
- Página pública para usar links
- Gestão de links (listar, cancelar)
====================================================================
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks

from database import db
from models.auth import UserRole
from models.temp_link import (
    TempLinkType, TempLinkStatus,
    TempLinkCreate, TempLinkResponse
)
from services.auth import get_current_user, require_roles
from services.temp_link_service import temp_link_service

router = APIRouter(prefix="/temp-links", tags=["Temporary Links"])
logger = logging.getLogger(__name__)


# ====================================================================
# ROTAS ADMINISTRATIVAS (requerem autenticação)
# ====================================================================

@router.post("/create", response_model=TempLinkResponse)
async def create_temp_link(
    process_id: str = Form(...),
    link_type: str = Form(...),  # "upload" ou "download"
    expires_in_hours: int = Form(default=72),
    max_uses: int = Form(default=1),
    description: Optional[str] = Form(default=None),
    file_paths: Optional[str] = Form(default=None),  # JSON string ou comma-separated
    notify_email: bool = Form(default=True),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.CONSULTOR, UserRole.MEDIADOR]))
):
    """
    Cria um link temporário para upload ou download de documentação.
    
    Tipos:
    - upload: Permite ao cliente carregar documentação
    - download: Permite ao cliente descarregar documentação
    
    Args:
        process_id: ID do processo/cliente
        link_type: "upload" ou "download"
        expires_in_hours: Horas até expirar (1-168)
        max_uses: Máximo de utilizações (1-10)
        description: Descrição opcional
        file_paths: Lista de paths S3 para download (separados por vírgula)
        notify_email: Se deve enviar email ao cliente
    """
    logger.info(f"Criando link temporário: process_id={process_id}, link_type={link_type}, user={user.get('id')}")
    
    # Validar process_id
    if not process_id or process_id.strip() == "":
        logger.warning("process_id vazio ou inválido")
        raise HTTPException(
            status_code=400,
            detail="ID do processo é obrigatório."
        )
    
    try:
        link_type_enum = TempLinkType(link_type.lower())
    except ValueError:
        logger.warning(f"Tipo de link inválido: {link_type}")
        raise HTTPException(
            status_code=400,
            detail="Tipo de link inválido. Use 'upload' ou 'download'."
        )
    
    # Validar limites
    if expires_in_hours < 1 or expires_in_hours > 168:
        raise HTTPException(
            status_code=400,
            detail="Horas até expirar deve estar entre 1 e 168 (7 dias)."
        )
    
    if max_uses < 1 or max_uses > 10:
        raise HTTPException(
            status_code=400,
            detail="Máximo de utilizações deve estar entre 1 e 10."
        )
    
    # Parse file_paths se fornecido
    files_list = None
    if file_paths:
        if file_paths.startswith('['):
            import json
            try:
                files_list = json.loads(file_paths)
            except:
                files_list = [p.strip() for p in file_paths.split(',') if p.strip()]
        else:
            files_list = [p.strip() for p in file_paths.split(',') if p.strip()]
    
    # Se é link de download, verificar que existem ficheiros
    if link_type_enum == TempLinkType.DOWNLOAD and not files_list:
        raise HTTPException(
            status_code=400,
            detail="Links de download requerem pelo menos um ficheiro."
        )
    
    try:
        link = await temp_link_service.create_link(
            process_id=process_id,
            link_type=link_type_enum,
            user_id=user["id"],
            user_name=user.get("name", "Utilizador"),
            expires_in_hours=expires_in_hours,
            max_uses=max_uses,
            description=description,
            file_paths=files_list,
            notify_email=notify_email
        )
        
        logger.info(f"Link temporário criado com sucesso: {link.id}")
        return link
        
    except ValueError as e:
        logger.warning(f"Erro de validação ao criar link: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar link temporário: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao criar link temporário: {str(e)}")


@router.get("/process/{process_id}")
async def list_process_temp_links(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Lista todos os links temporários de um processo.
    """
    # Verificar acesso ao processo
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Verificar permissões
    user_role = user.get("role")
    if user_role not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]:
        if process.get("assigned_consultor_id") != user.get("id") and \
           process.get("assigned_mediador_id") != user.get("id"):
            raise HTTPException(status_code=403, detail="Acesso não autorizado")
    
    links = await temp_link_service.list_process_links(process_id)
    
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "links": links,
        "total": len(links)
    }


@router.post("/{link_id}/cancel")
async def cancel_temp_link(
    link_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.CONSULTOR, UserRole.MEDIADOR]))
):
    """
    Cancela um link temporário.
    """
    # Verificar se o link existe
    link = await db.temp_links.find_one({"id": link_id})
    if not link:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    # Verificar permissões
    if user.get("role") not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]:
        # Verificar se é o criador do link
        if link.get("created_by") != user.get("id"):
            raise HTTPException(
                status_code=403,
                detail="Só pode cancelar links que criou."
            )
    
    success = await temp_link_service.cancel_link(link_id, user["id"])
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível cancelar o link. Pode já ter sido usado ou expirado."
        )
    
    return {"success": True, "message": "Link cancelado com sucesso"}


@router.delete("/{link_id}")
async def delete_temp_link(
    link_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Elimina um link temporário (apenas admin).
    """
    result = await db.temp_links.delete_one({"id": link_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Link não encontrado")
    
    return {"success": True, "message": "Link eliminado"}


# ====================================================================
# ROTAS PÚBLICAS (sem autenticação)
# ====================================================================

@router.get("/public/{token}")
async def get_public_link_info(token: str):
    """
    Obtém informações públicas sobre um link temporário.
    Não requer autenticação.
    
    Retorna:
    - Dados do link (sem informações sensíveis)
    - Se é válido
    - Informações sobre o que fazer (upload/download)
    """
    validation = await temp_link_service.validate_link(token)
    
    if not validation["valid"]:
        return {
            "valid": False,
            "error": validation.get("error")
        }
    
    link = validation["link"]
    
    # Retornar apenas informações necessárias
    return {
        "valid": True,
        "token": token,
        "link_type": link["link_type"],
        "client_name": link["client_name"],
        "expires_at": link["expires_at"],
        "remaining_uses": validation["remaining_uses"],
        "description": link.get("description"),
        "file_count": len(link.get("file_paths", [])) if link.get("file_paths") else 0
    }


@router.post("/public/{token}/upload")
async def upload_via_temp_link(
    token: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """
    Faz upload de ficheiros através de um link temporário.
    Não requer autenticação.
    
    Aceita múltiplos ficheiros.
    """
    # Validar link
    validation = await temp_link_service.validate_link(token)
    
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation.get("error"))
    
    link = validation["link"]
    
    if link["link_type"] != TempLinkType.UPLOAD.value:
        raise HTTPException(
            status_code=400,
            detail="Este link é para download, não para upload."
        )
    
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum ficheiro enviado")
    
    # Importar serviço S3
    from services.s3_storage import s3_service
    
    process_id = link["process_id"]
    client_name = link["client_name"]
    
    # Obter dados do processo para segundo titular
    process = await db.processes.find_one({"id": process_id})
    second_client_name = None
    s3_folder = None
    if process:
        titular2 = process.get("titular2_data") or {}
        second_client_name = process.get("second_client_name") or titular2.get("nome") or titular2.get("name")
        s3_folder = process.get("s3_folder")
    
    uploaded_files = []
    
    for file in files:
        try:
            # Ler conteúdo
            content = await file.read()
            
            # Determinar categoria (padrão: "Cliente Upload")
            category = "Cliente_Upload"
            
            # Sanitizar nome
            import re
            import unicodedata
            filename = file.filename
            name_part = filename.rsplit('.', 1)[0] if '.' in filename else filename
            ext = filename.rsplit('.', 1)[1] if '.' in filename else 'pdf'
            
            name_normalized = unicodedata.normalize('NFKD', name_part)
            name_normalized = name_normalized.encode('ASCII', 'ignore').decode('ASCII')
            name_normalized = re.sub(r'[^\w\s-]', '', name_normalized)
            name_normalized = re.sub(r'[\s_]+', '_', name_normalized.strip())[:50]
            
            date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            normalized_filename = f"{category}_{date_str}_{name_normalized}.{ext}"
            
            # Upload para S3
            from io import BytesIO
            file_buffer = BytesIO(content)
            
            s3_path = s3_service.upload_file(
                file_buffer,
                process_id,
                client_name,
                category,
                normalized_filename,
                file.content_type,
                second_client_name=second_client_name,
                s3_folder=s3_folder
            )
            
            if s3_path:
                uploaded_files.append({
                    "original_name": file.filename,
                    "normalized_name": normalized_filename,
                    "s3_path": s3_path,
                    "size": len(content),
                    "content_type": file.content_type
                })
                
        except Exception as e:
            logger.error(f"Erro ao fazer upload de {file.filename}: {e}")
    
    if not uploaded_files:
        raise HTTPException(status_code=500, detail="Nenhum ficheiro foi carregado com sucesso")
    
    # Marcar link como usado
    await temp_link_service.use_link(token, uploaded_files)
    
    # Adicionar atividade ao processo
    activity = {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "type": "document_upload",
        "comment": f"Cliente carregou {len(uploaded_files)} documento(s) via link temporário",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": None,  # Sistema
        "metadata": {
            "files": [f["original_name"] for f in uploaded_files],
            "via_temp_link": True
        }
    }
    await db.activities.insert_one(activity)
    
    # Notificar consultor/mediador atribuído
    if process:
        from services.notification_service import notification_service
        assigned_consultor_id = process.get("assigned_consultor_id")
        if assigned_consultor_id:
            try:
                await notification_service.create_notification(
                    user_id=assigned_consultor_id,
                    title="📤 Documentos Carregados",
                    message=f"O cliente {client_name} carregou {len(uploaded_files)} documento(s)",
                    type="document_upload",
                    link=f"/processo/{process_id}"
                )
            except Exception as e:
                logger.warning(f"Erro ao notificar consultor: {e}")
    
    return {
        "success": True,
        "message": f"{len(uploaded_files)} ficheiro(s) carregado(s) com sucesso",
        "files": uploaded_files
    }


@router.get("/public/{token}/download/{file_index}")
async def download_via_temp_link(
    token: str,
    file_index: int = 0
):
    """
    Faz download de um ficheiro através de um link temporário.
    Não requer autenticação.
    """
    # Validar link
    validation = await temp_link_service.validate_link(token)
    
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation.get("error"))
    
    link = validation["link"]
    
    if link["link_type"] != TempLinkType.DOWNLOAD.value:
        raise HTTPException(
            status_code=400,
            detail="Este link é para upload, não para download."
        )
    
    file_paths = link.get("file_paths", [])
    
    if not file_paths:
        raise HTTPException(status_code=404, detail="Nenhum ficheiro disponível")
    
    if file_index < 0 or file_index >= len(file_paths):
        raise HTTPException(status_code=400, detail="Índice de ficheiro inválido")
    
    s3_path = file_paths[file_index]
    
    # Importar serviço S3
    from services.s3_storage import s3_service
    
    url = s3_service.get_presigned_url(s3_path)
    
    if not url:
        raise HTTPException(status_code=500, detail="Erro ao gerar link de download")
    
    # Marcar link como usado
    await temp_link_service.use_link(token)
    
    return {
        "success": True,
        "url": url,
        "filename": s3_path.split("/")[-1]
    }


@router.get("/public/{token}/files")
async def list_temp_link_files(token: str):
    """
    Lista ficheiros disponíveis para download num link temporário.
    """
    validation = await temp_link_service.validate_link(token)
    
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation.get("error"))
    
    link = validation["link"]
    
    if link["link_type"] != TempLinkType.DOWNLOAD.value:
        raise HTTPException(
            status_code=400,
            detail="Este link é para upload, não para download."
        )
    
    file_paths = link.get("file_paths", [])
    
    # Retornar lista de ficheiros
    files = []
    for idx, path in enumerate(file_paths):
        filename = path.split("/")[-1]
        files.append({
            "index": idx,
            "filename": filename,
            "path": path
        })
    
    return {
        "valid": True,
        "files": files,
        "total": len(files)
    }
