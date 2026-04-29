"""
CLIENT PORTAL - Routes
======================
Endpoints públicos para o Portal do Cliente (Magic Link / Passwordless).

SEGURANÇA:
- Todos os endpoints usam get_current_client (role="client_portal")
- NUNCA devolvem dados sensíveis (notas internas, NIF, dados financeiros)
- Upload restrito ao process_id do token
- Sem acesso a endpoints de staff

ENDPOINTS:
- GET  /portal/status          → Status do processo + documentos pendentes
- POST /portal/upload-url      → Gera pre-signed URL para upload
- POST /portal/confirm-upload  → Confirma upload após PUT para S3
- POST /portal/authenticate    → (Opcional) Valida magic link e retorna info
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from database import db
from services.portal_security import get_current_client, get_portal_client_process, PORTAL_ROLE
from services.s3_storage import s3_service
from services.redis_cache import invalidate_stats_cache
from services.notification_service import send_notification_with_preference_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Client Portal"])


# ====================================================================
# RESOLUÇÃO DE SHORT TOKEN
# ====================================================================

@router.get("/resolve/{short_id}")
async def resolve_portal_token(short_id: str):
    """
    Resolve um short_id (8 chars) para o JWT completo do portal.

    O frontend detecta que o token não é um JWT (não contém '.')
    e chama este endpoint para obter o JWT real antes de
    autenticar nas restantes rotas do portal.

    Returns:
    - token: JWT completo
    - process_id: ID do processo
    """
    import re

    # Validar formato do short_id (apenas alfanumérico + -_)
    if not re.match(r'^[A-Za-z0-9_-]+$', short_id) or len(short_id) > 20:
        raise HTTPException(status_code=400, detail="Token inválido")

    # Buscar na BD
    token_doc = await db.portal_tokens.find_one(
        {"short_id": short_id},
        {"_id": 0}
    )

    if not token_doc:
        raise HTTPException(
            status_code=404,
            detail="Link não encontrado. Pode ter expirado ou sido desactivado."
        )

    # Validar JWT internamente (verificar se ainda é válido / não expirou)
    try:
        import jwt as jwt_lib
        from config import JWT_SECRET, JWT_ALGORITHM
        jwt_lib.decode(
            token_doc["jwt_token"],
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
    except jwt_lib.ExpiredSignatureError:
        raise HTTPException(
            status_code=410,
            detail="Este link expirou. Contacte o seu consultor para receber um novo link."
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Link inválido.")

    return {
        "token": token_doc["jwt_token"],
        "process_id": token_doc.get("process_id"),
    }


# Documentos que o cliente precisa submeter (categorias comuns)
REQUIRED_DOCUMENT_CATEGORIES = [
    {"category": "Cartao_Cidadao", "label": "Cartão de Cidadão", "icon": "🪪"},
    {"category": "IRS", "label": "Declaração de IRS", "icon": "📋"},
    {"category": "Recibo_Vencimento", "label": "Recibo de Vencimento", "icon": "💰"},
    {"category": "Comprovativo_IBAN", "label": "Comprovativo de IBAN", "icon": "🏦"},
    {"category": "Certidao_Nascimento", "label": "Certidão de Nascimento", "icon": "📄"},
    {"category": "Outros", "label": "Outro Documento", "icon": "📎"},
]


# ====================================================================
# AUTENTICAÇÃO DO PORTAL
# ====================================================================

@router.post("/authenticate")
async def authenticate_portal(client_data: dict = Depends(get_current_client)):
    """
    Valida o magic link JWT e retorna informações básicas do processo.

    Usado pelo frontend para verificar se o token é válido antes de
    renderizar a interface do portal.

    Returns:
    - valid: true
    - process_id: ID do processo
    - client_name: Nome do cliente
    - token_expires: Data de expiração do token (ISO format)
    """
    process = client_data["process"]
    token_payload = client_data["token_payload"]

    return JSONResponse(content={
        "valid": True,
        "process_id": process["id"],
        "client_name": process.get("client_name", ""),
        "process_type": process.get("process_type", "credito_habitacao"),
        "token_expires": token_payload.get("exp"),
    })


# ====================================================================
# STATUS DO PROCESSO
# ====================================================================

@router.get("/status")
async def get_portal_status(
    client_data: dict = Depends(get_current_client)
):
    """
    Retorna o status do processo para o Portal do Cliente.

    Inclui apenas dados públicos/seguros:
    - Nome do cliente
    - Status atual + label
    - Progresso (fase actual no workflow)
    - Lista de workflow statuses (para stepper)
    - Lista de documentos do processo (sem conteúdo)
    - Contactos do consultor atribuído

    NUNCA devolve:
    - Notas internas
    - Dados financeiros
    - NIF ou dados pessoais sensíveis
    - Dados de outros processos
    """
    process = client_data["process"]
    process_id = process["id"]

    # Buscar workflow statuses ordenados (para stepper)
    statuses = await db.workflow_statuses.find(
        {}, {"_id": 0}
    ).sort("order", 1).to_list(100)

    # Determinar a posição atual no workflow
    current_status = process.get("status", "clientes_espera")
    current_step_index = 0
    current_status_label = current_status

    for i, status in enumerate(statuses):
        if status.get("name") == current_status:
            current_step_index = i
            current_status_label = status.get("label", current_status)
            break

    # Total de steps (excluir statuses terminais da contagem de progresso)
    # Progress bar calculada com base nos steps "ativos" (excluir Concluídos/Desistências)
    terminal_statuses = ["concluidos", "desistencias", "eliminados", "perdido", "arquivo"]
    active_steps = [s for s in statuses if s.get("name") not in terminal_statuses]
    total_active_steps = len(active_steps) if active_steps else 1

    # Progresso percentual (fase actual / total de fases activas)
    current_active_index = 0
    for i, s in enumerate(active_steps):
        if s.get("name") == current_status:
            current_active_index = i + 1
            break

    progress_percent = min(100, int((current_active_index / total_active_steps) * 100))

    # Buscar documentos do processo (apenas metadados, sem conteúdo)
    documents = []
    doc_cursor = db.documents.find(
        {"process_id": process_id},
        {"_id": 0, "file_content": 0}
    ).sort("uploaded_at", -1)

    async for doc in doc_cursor:
        documents.append({
            "id": doc.get("id"),
            "filename": doc.get("original_filename", doc.get("filename", "")),
            "category": doc.get("category", "Outros"),
            "uploaded_at": doc.get("uploaded_at"),
            "file_size": doc.get("file_size"),
        })

    # Documentos pendentes: categorias que ainda não foram submetidas
    submitted_categories = {d.get("category") for d in documents}
    pending_documents = [
        cat for cat in REQUIRED_DOCUMENT_CATEGORIES
        if cat["category"] not in submitted_categories
    ]

    # Contactos do consultor atribuído
    assigned_consultor_id = (
        process.get("assigned_consultor_id") or
        (process.get("assigned_consultor_ids", [None])[0] if process.get("assigned_consultor_ids") else None)
    )

    consultor_info = None
    if assigned_consultor_id:
        consultor = await db.users.find_one(
            {"id": assigned_consultor_id},
            {"_id": 0, "password": 0}
        )
        if consultor:
            consultor_info = {
                "name": consultor.get("name", ""),
                "email": consultor.get("email", ""),
                "phone": consultor.get("phone", ""),
            }

    # Se não há consultor, buscar info do mediador
    if not consultor_info:
        assigned_mediador_id = (
            process.get("assigned_mediador_id") or
            (process.get("assigned_mediador_ids", [None])[0] if process.get("assigned_mediador_ids") else None)
        )
        if assigned_mediador_id:
            mediador = await db.users.find_one(
                {"id": assigned_mediador_id},
                {"_id": 0, "password": 0}
            )
            if mediador:
                consultor_info = {
                    "name": mediador.get("name", ""),
                    "email": mediador.get("email", ""),
                    "phone": mediador.get("phone", ""),
                }

    # Stepper data: fases simplificadas para o cliente
    stepper = []
    for status in active_steps:
        is_current = status.get("name") == current_status
        is_completed = False

        # Uma fase está "completada" se o processo já passou dela
        # (o status actual está numa fase com order maior)
        current_order = 0
        for s in active_steps:
            if s.get("name") == current_status:
                current_order = s.get("order", 0)
                break

        if status.get("order", 0) < current_order:
            is_completed = True

        stepper.append({
            "id": status.get("name"),
            "label": status.get("label", status.get("name")),
            "color": status.get("color", "#94a3b8"),
            "is_current": is_current,
            "is_completed": is_completed,
        })

    return {
        "process": {
            "id": process_id,
            "client_name": process.get("client_name", ""),
            "status": current_status,
            "status_label": current_status_label,
            "process_type": process.get("process_type", "credito_habitacao"),
            "created_at": process.get("created_at"),
            "updated_at": process.get("updated_at"),
        },
        "progress": {
            "percent": progress_percent,
            "current_step": current_active_index,
            "total_steps": total_active_steps,
        },
        "stepper": stepper,
        "documents": {
            "uploaded": documents,
            "pending": pending_documents,
            "has_pending": len(pending_documents) > 0,
        },
        "consultor": consultor_info,
    }


# ====================================================================
# UPLOAD DE DOCUMENTOS
# ====================================================================

@router.post("/upload-url")
async def generate_portal_upload_url(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    """
    Gera uma pre-signed URL para upload direto ao S3.

    Restrito ao process_id do token — o cliente só pode
    fazer upload para o seu próprio processo.

    Reutiliza a mesma lógica de Direct S3 Upload que o staff usa,
    mas sem necessidade de autenticação de staff.

    Body:
    - filename: Nome original do ficheiro (obrigatório)
    - content_type: MIME type (obrigatório)
    - category: Categoria do documento (default: "Outros")
    """
    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Serviço de armazenamento indisponível. Contacte o seu consultor."
        )

    process = client_data["process"]
    process_id = process["id"]

    filename = data.get("filename", "")
    content_type = data.get("content_type", "application/octet-stream")
    category = data.get("category", "Outros")

    if not filename:
        raise HTTPException(status_code=400, detail="Nome do ficheiro é obrigatório")
    if not content_type:
        raise HTTPException(status_code=400, detail="Tipo do ficheiro é obrigatório")

    # Normalizar nome do ficheiro (sanitizar)
    safe_filename = filename.replace(" ", "_").replace("/", "-").replace("\\", "-")

    client_name = process.get("client_name", "cliente")
    s3_folder = process.get("s3_folder")

    result = s3_service.generate_upload_presigned_url(
        client_id=process_id,
        client_name=client_name,
        category=category,
        filename=safe_filename,
        content_type=content_type,
        s3_folder=s3_folder,
        expiration=300  # 5 minutos
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar link de upload. Tente novamente."
        )

    logger.info(f"[PORTAL] Upload URL gerada para {safe_filename} (processo {process_id})")

    return {
        "success": True,
        "upload_url": result["upload_url"],
        "file_key": result["file_key"],
        "expires_at": result["expires_at"],
        "expires_in_seconds": result["expires_in_seconds"],
        "method": "PUT",
        "headers": {"Content-Type": content_type},
    }


@router.post("/confirm-upload")
async def confirm_portal_upload(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    """
    Confirma um upload direto para o S3 e regista na base de dados.

    Chamado pelo frontend APÓS o PUT para o S3 ter sucesso.

    Body:
    - file_key: Caminho S3 (obrigatório, retornado pelo /upload-url)
    - original_filename: Nome original (obrigatório)
    - category: Categoria (obrigatório)
    - file_size: Tamanho em bytes (opcional)
    - content_type: MIME type (opcional)
    """
    import uuid
    from datetime import datetime, timezone

    process = client_data["process"]
    process_id = process["id"]

    file_key = data.get("file_key")
    original_filename = data.get("original_filename")
    category = data.get("category", "Outros")
    file_size = data.get("file_size")
    content_type = data.get("content_type", "application/octet-stream")

    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório")
    if not original_filename:
        raise HTTPException(status_code=400, detail="original_filename é obrigatório")

    # Verificar que o ficheiro existe no S3
    if not s3_service.file_exists(file_key):
        raise HTTPException(
            status_code=400,
            detail="Ficheiro não encontrado. O upload pode ter falhado. Tente novamente."
        )

    # Registar documento na base de dados
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    document = {
        "id": doc_id,
        "process_id": process_id,
        "filename": original_filename,
        "original_filename": original_filename,
        "category": category,
        "file_size": file_size,
        "content_type": content_type,
        "s3_path": file_key,
        "uploaded_at": now,
        "uploaded_by": "portal_client",
        "source": "client_portal",
    }

    await db.documents.insert_one(document)

    # Invalidar cache de estatísticas (novo documento)
    await invalidate_stats_cache()

    # Obter URL temporária
    temporary_url = s3_service.get_presigned_url(file_key) or ""

    # Notificar consultor sobre novo documento
    assigned_consultor_id = process.get("assigned_consultor_id")
    if assigned_consultor_id:
        try:
            from services.history import log_history
            consultor = await db.users.find_one(
                {"id": assigned_consultor_id}, {"name": 1, "email": 1}
            )
            if consultor:
                client_name = process.get("client_name", "Cliente")
                await send_notification_with_preference_check(
                    consultor.get("email"),
                    "Novo Documento Submetido",
                    f"O cliente {client_name} submeteu '{original_filename}' via Portal.",
                    notification_type="document_upload"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar consultor: {e}")

    logger.info(
        f"[PORTAL] Upload confirmado: {original_filename} "
        f"({category}) para processo {process_id}"
    )

    return {
        "success": True,
        "document_id": doc_id,
        "filename": original_filename,
        "category": category,
        "s3_path": file_key,
        "temporary_url": temporary_url,
    }
