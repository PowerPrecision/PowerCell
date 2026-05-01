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
- GET  /portal/resolve/{short_id}  → Resolve short_id para JWT
- GET  /portal/status              → Status do processo + stepper + documentos
- POST /portal/upload-url          → Gera pre-signed URL para upload
- POST /portal/confirm-upload      → Confirma upload após PUT para S3
- POST /portal/authenticate        → Valida magic link e retorna info
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from database import db
from services.portal_security import get_current_client, PORTAL_ROLE
from services.s3_storage import s3_service
from services.redis_cache import invalidate_stats_cache
from services.notification_service import send_notification_with_preference_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Client Portal"])


# ====================================================================
# DOCUMENT CATEGORIES — Mapeamento de categorias client-facing
# ====================================================================
DOCUMENT_CATEGORY_MAP = {
    "Cartao_Cidadao": {"label": "Cartão de Cidadão", "icon": "🪪"},
    "IRS": {"label": "Declaração de IRS", "icon": "📋"},
    "Recibo_Vencimento": {"label": "Recibo de Vencimento", "icon": "💰"},
    "Comprovativo_IBAN": {"label": "Comprovativo de IBAN", "icon": "🏦"},
    "Certidao_Nascimento": {"label": "Certidão de Nascimento", "icon": "📄"},
    "Atestado_Trabalho": {"label": "Atestado de Trabalho", "icon": "🏢"},
    "Mapa_Creditos": {"label": "Mapa de Créditos", "icon": "📊"},
    "Declaracao_Imposto_Renda": {"label": "Declaração de Imposto de Renda", "icon": "📑"},
    "Certidao_Permanente": {"label": "Certidão Permanente", "icon": "📜"},
    "Contrato_Promessa": {"label": "Contrato de Promessa", "icon": "📝"},
    "Plantas_Casa": {"label": "Plantas da Casa", "icon": "🏠"},
    "Certificado_Energetico": {"label": "Certificado Energético", "icon": "⚡"},
    "Outros": {"label": "Outro Documento", "icon": "📎"},
}

# Fallback categories usadas quando o admin não criou docs REQUESTED
DEFAULT_PENDING_CATEGORIES = [
    "Cartao_Cidadao",
    "IRS",
    "Recibo_Vencimento",
    "Comprovativo_IBAN",
]


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


# ====================================================================
# AUTENTICAÇÃO DO PORTAL
# ====================================================================

@router.post("/authenticate")
async def authenticate_portal(client_data: dict = Depends(get_current_client)):
    """
    Valida o magic link JWT e retorna informações básicas do processo.
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
    Retorna o status completo do processo para o Portal do Cliente.

    Dados incluídos:
    - Informações do processo (sem dados sensíveis)
    - Stepper dinâmico baseado no workflow (vindo da BD)
    - Documentos solicitados (status REQUESTED/PENDING)
    - Documentos já submetidos (status UPLOADED)
    - Contactos do consultor

    Documentos pendentes:
    - Primário: Docs com status REQUESTED/PENDING na BD (o admin solicitou)
    - Fallback: Se não existem docs solicitados, mostra categorias padrão
      que ainda não têm qualquer documento submetido
    """
    process = client_data["process"]
    process_id = process["id"]

    # ── Workflow statuses para o stepper ──
    statuses = await db.workflow_statuses.find(
        {}, {"_id": 0}
    ).sort("order", 1).to_list(100)

    current_status = process.get("status", "clientes_espera")
    current_status_label = current_status
    current_status_color = "#94a3b8"

    for s in statuses:
        if s.get("name") == current_status:
            current_status_label = s.get("label", current_status)
            current_status_color = s.get("color", "#94a3b8")
            break

    # Excluir statuses terminais para progresso
    terminal_statuses = ["concluidos", "desistencias", "eliminados", "perdido", "arquivo"]
    active_steps = [s for s in statuses if s.get("name") not in terminal_statuses]
    total_active_steps = len(active_steps) if active_steps else 1

    # Posição atual e progresso
    current_order = 0
    for s in active_steps:
        if s.get("name") == current_status:
            current_order = s.get("order", 0)
            break

    current_active_index = sum(1 for s in active_steps if s.get("order", 0) < current_order)
    if any(s.get("name") == current_status for s in active_steps):
        current_active_index = max(current_active_index, 1)

    progress_percent = min(100, int((current_active_index / total_active_steps) * 100))

    # ── Stepper data ──
    stepper = []
    for status in active_steps:
        is_current = status.get("name") == current_status
        is_completed = status.get("order", 0) < current_order

        stepper.append({
            "id": status.get("name"),
            "label": status.get("label", status.get("name")),
            "color": status.get("color", "#94a3b8"),
            "description": status.get("description", ""),
            "is_current": is_current,
            "is_completed": is_completed,
        })

    # ── Documentos solicitados (REQUESTED/PENDING) ──
    requested_docs = []
    requested_cursor = db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]}
        },
        {"_id": 0, "file_content": 0}
    ).sort("created_at", 1)

    async for doc in requested_cursor:
        cat = doc.get("category", "Outros")
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        requested_docs.append({
            "id": doc.get("id"),
            "category": cat,
            "label": cat_info["label"],
            "icon": cat_info["icon"],
            "notes": doc.get("notes", ""),
            "requested_at": doc.get("created_at", doc.get("uploaded_at", "")),
        })

    # ── Documentos submetidos (UPLOADED/SUBMITTED) ──
    uploaded_docs = []
    uploaded_cursor = db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["UPLOADED", "SUBMITTED", "uploaded", "submitted"]}
        },
        {"_id": 0, "file_content": 0}
    ).sort("uploaded_at", -1)

    async for doc in uploaded_cursor:
        cat = doc.get("category", "Outros")
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        uploaded_docs.append({
            "id": doc.get("id"),
            "filename": doc.get("original_filename", doc.get("filename", "")),
            "category": cat,
            "category_label": cat_info["label"],
            "icon": cat_info["icon"],
            "uploaded_at": doc.get("uploaded_at", ""),
            "file_size": doc.get("file_size"),
            "status": doc.get("status", "UPLOADED"),
        })

    # ── Fallback: se não há docs REQUESTED, calcular pendentes por categoria ──
    has_pending = len(requested_docs) > 0
    if not has_pending:
        # Buscar TODOS os docs para saber quais categorias já foram submetidas
        all_docs_cursor = db.documents.find(
            {"process_id": process_id},
            {"_id": 0, "category": 1}
        )
        submitted_categories = set()
        async for doc in all_docs_cursor:
            if doc.get("category"):
                submitted_categories.add(doc["category"])

        for cat_key in DEFAULT_PENDING_CATEGORIES:
            if cat_key not in submitted_categories:
                cat_info = DOCUMENT_CATEGORY_MAP.get(cat_key, {"label": cat_key, "icon": "📎"})
                requested_docs.append({
                    "id": None,
                    "category": cat_key,
                    "label": cat_info["label"],
                    "icon": cat_info["icon"],
                    "notes": "",
                    "requested_at": None,
                })

        has_pending = len(requested_docs) > 0

    # ── Consultor atribuído ──
    consultor_info = await _get_consultor_info(process)

    return {
        "process": {
            "id": process_id,
            "client_name": process.get("client_name", ""),
            "status": current_status,
            "status_label": current_status_label,
            "status_color": current_status_color,
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
            "requested": requested_docs,
            "uploaded": uploaded_docs,
            "has_pending": has_pending,
        },
        "consultor": consultor_info,
    }


# ====================================================================
# HELPER: Consultor Info
# ====================================================================

async def _get_consultor_info(process: dict) -> dict:
    """Obtém informações de contacto do consultor/mediador atribuído."""
    user_ids = (
        process.get("assigned_consultor_ids") or
        ([process["assigned_consultor_id"]] if process.get("assigned_consultor_id") else [])
    )

    if not user_ids:
        user_ids = (
            process.get("assigned_mediador_ids") or
            ([process["assigned_mediador_id"]] if process.get("assigned_mediador_id") else [])
        )

    for user_id in user_ids:
        if not user_id:
            continue
        user = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "password": 0}
        )
        if user:
            return {
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "phone": user.get("phone", ""),
                "role": user.get("role", ""),
            }

    return None


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

    O cliente só pode fazer upload para o seu próprio processo.
    Usa a mesma lógica de S3 que o staff (s3_storage.py).

    Body:
    - filename: Nome original (obrigatório)
    - content_type: MIME type (obrigatório)
    - category: Categoria do documento (obrigatório)
    - document_id: ID do doc REQUESTED que este upload satisfaz (opcional)
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

    # Normalizar nome
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
        expiration=300
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar link de upload. Tente novamente."
        )

    logger.info(f"[PORTAL] Upload URL gerada para {safe_filename} (processo {process_id}, cat: {category})")

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
    Confirma upload para S3 e regista na base de dados.

    O documento fica com status=UPLOADED para aparecer no CRM do admin.
    Se for fornecido document_id (de um doc REQUESTED), esse registo é atualizado
    em vez de criar um novo.

    Body:
    - file_key: Caminho S3 (obrigatório)
    - original_filename: Nome original (obrigatório)
    - category: Categoria (obrigatório)
    - file_size: Tamanho em bytes (opcional)
    - content_type: MIME type (opcional)
    - document_id: ID do doc REQUESTED a satisfazer (opcional)
    """
    import uuid

    process = client_data["process"]
    process_id = process["id"]

    file_key = data.get("file_key")
    original_filename = data.get("original_filename")
    category = data.get("category", "Outros")
    file_size = data.get("file_size")
    content_type = data.get("content_type", "application/octet-stream")
    document_id = data.get("document_id")  # ID do doc REQUESTED a satisfazer

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

    now = datetime.now(timezone.utc).isoformat()

    # ── Se temos document_id, atualizar o registo REQUESTED ──
    if document_id:
        update_result = await db.documents.update_one(
            {"id": document_id, "process_id": process_id},
            {
                "$set": {
                    "status": "UPLOADED",
                    "filename": original_filename,
                    "original_filename": original_filename,
                    "file_size": file_size,
                    "content_type": content_type,
                    "s3_path": file_key,
                    "uploaded_at": now,
                    "uploaded_by": "portal_client",
                    "source": "client_portal",
                    "updated_at": now,
                }
            }
        )

        if update_result.matched_count > 0:
            doc_id = document_id
            logger.info(f"[PORTAL] Doc REQUESTED atualizado para UPLOADED: {document_id}")
        else:
            # document_id não encontrado — criar novo
            doc_id = str(uuid.uuid4())
            await _create_document_record(
                doc_id, process_id, file_key, original_filename,
                category, file_size, content_type, now
            )
    else:
        # Sem document_id — criar novo registo
        doc_id = str(uuid.uuid4())
        await _create_document_record(
            doc_id, process_id, file_key, original_filename,
            category, file_size, content_type, now
        )

    # Invalidar cache de estatísticas
    await invalidate_stats_cache()

    # Obter URL temporária para preview
    temporary_url = s3_service.get_presigned_url(file_key) or ""

    # ── Notificar consultor ──
    await _notify_consultor_upload(process, original_filename, category)

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


# ====================================================================
# HELPERS: Document Creation & Notification
# ====================================================================

async def _create_document_record(
    doc_id: str, process_id: str, file_key: str,
    original_filename: str, category: str,
    file_size: int, content_type: str, now: str
):
    """Cria um registo de documento na BD com status UPLOADED."""
    document = {
        "id": doc_id,
        "process_id": process_id,
        "filename": original_filename,
        "original_filename": original_filename,
        "category": category,
        "file_size": file_size,
        "content_type": content_type,
        "s3_path": file_key,
        "status": "UPLOADED",
        "uploaded_at": now,
        "uploaded_by": "portal_client",
        "source": "client_portal",
    }
    await db.documents.insert_one(document)


async def _notify_consultor_upload(process: dict, filename: str, category: str):
    """Notifica o consultor sobre um novo upload do cliente."""
    assigned_consultor_id = process.get("assigned_consultor_id")
    if not assigned_consultor_id:
        return

    try:
        consultor = await db.users.find_one(
            {"id": assigned_consultor_id}, {"name": 1, "email": 1}
        )
        if consultor:
            client_name = process.get("client_name", "Cliente")
            await send_notification_with_preference_check(
                consultor.get("email"),
                "Novo Documento Submetido",
                f"O cliente {client_name} submeteu '{filename}' ({category}) via Portal.",
                notification_type="document_upload"
            )
    except Exception as e:
        logger.warning(f"Erro ao notificar consultor: {e}")
