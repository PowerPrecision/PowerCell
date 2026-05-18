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
- GET  /portal/messages            → Lista mensagens do processo
- POST /portal/messages            → Envia mensagem do cliente
- GET  /portal/messages/unread     → Conta mensagens não lidas do staff
"""
import uuid
import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from database import db
from services.portal_security import get_current_client, PORTAL_ROLE
from services.auth import get_current_user, require_roles
from services.s3_storage import s3_service
from services.redis_cache import invalidate_stats_cache
from services.notification_service import send_notification_with_preference_check
from services.websocket_manager import manager, WSEventType, create_ws_message

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
    # Buscar todos os statuses (incluindo hidden, para calcular progresso)
    all_statuses = await db.workflow_statuses.find(
        {}, {"_id": 0}
    ).sort("order", 1).to_list(100)

    current_status = process.get("status", "clientes_espera")
    current_status_label = current_status
    current_status_color = "#94a3b8"

    # Determinar label e cor do status atual
    # Usar portal_label se disponível (client-facing)
    for s in all_statuses:
        if s.get("name") == current_status:
            current_status_label = s.get("portal_label") or s.get("label", current_status)
            current_status_color = s.get("color", "#94a3b8")
            break

    # Excluir statuses terminais E ocultos no portal
    terminal_statuses = ["concluidos", "desistencias", "eliminados", "perdido", "arquivo"]
    active_steps = [
        s for s in all_statuses
        if s.get("name") not in terminal_statuses
        and s.get("visible_in_portal", True) is not False
    ]
    total_active_steps = len(active_steps) if active_steps else 1

    # Posição atual e progresso — usar TODOS os active (não apenas visíveis)
    all_active = [s for s in all_statuses if s.get("name") not in terminal_statuses]
    current_order = 0
    for s in all_active:
        if s.get("name") == current_status:
            current_order = s.get("order", 0)
            break

    current_active_index = sum(1 for s in all_active if s.get("order", 0) < current_order)
    if any(s.get("name") == current_status for s in all_active):
        current_active_index = max(current_active_index, 1)

    progress_percent = min(100, int((current_active_index / len(all_active)) * 100)) if all_active else 100

    # ── Stepper data (apenas visíveis no portal) ──
    stepper = []
    for status in active_steps:
        is_current = status.get("name") == current_status
        is_completed = status.get("order", 0) < current_order

        # Usar portal_label se disponível, senão label, senão name
        display_label = status.get("portal_label") or status.get("label", status.get("name"))

        stepper.append({
            "id": status.get("name"),
            "label": display_label,
            "color": status.get("color", "#94a3b8"),
            "description": status.get("portal_description") or status.get("description", ""),
            "is_current": is_current,
            "is_completed": is_completed,
        })

    # ── Documentos solicitados (REQUESTED/PENDING) ──
    requested_docs = []
    requested_cursor = db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]},
            "source": {"$ne": "admin_received"}  # Exclude admin-marked received docs
        },
        {"_id": 0, "file_content": 0}
    ).sort("created_at", 1)

    async for doc in requested_cursor:
        cat = doc.get("category", "Outros")
        # Ensure cat is a string (backend may have stored objects)
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", "Outros"))
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        # Ensure notes is a string (may have been stored as an object)
        raw_notes = doc.get("notes", "")
        if isinstance(raw_notes, dict):
            raw_notes = raw_notes.get("label", raw_notes.get("value", str(raw_notes)))
        notes_str = str(raw_notes) if raw_notes is not None else ""

        requested_docs.append({
            "id": doc.get("id"),
            "category": cat,
            "label": cat_info["label"],
            "icon": cat_info["icon"],
            "notes": notes_str,
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
        # Ensure cat is a string (backend may have stored objects)
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", "Outros"))
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        # Show custom_label for "Outros" category, otherwise use category label
        display_label = doc.get("custom_label") if cat == "Outros" and doc.get("custom_label") else cat_info["label"]
        uploaded_docs.append({
            "id": doc.get("id"),
            "filename": doc.get("original_filename", doc.get("filename", "")),
            "category": cat,
            "category_label": display_label,
            "icon": cat_info["icon"],
            "uploaded_at": doc.get("uploaded_at", ""),
            "file_size": doc.get("file_size"),
            "status": doc.get("status", "UPLOADED"),
        })

    # ── Documentos recebidos pelo admin (marcados como RECEIVED) ──
    received_docs = []
    received_cursor = db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["RECEIVED", "received"]}
        },
        {"_id": 0, "file_content": 0}
    ).sort("updated_at", -1)

    async for doc in received_cursor:
        cat = doc.get("category", "Outros")
        # Ensure cat is a string (backend may have stored objects)
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", "Outros"))
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        received_docs.append({
            "id": doc.get("id"),
            "filename": doc.get("original_filename") or doc.get("filename") or cat_info["label"],
            "category": cat,
            "category_label": cat_info["label"],
            "icon": cat_info["icon"],
            "received_at": doc.get("reviewed_at", doc.get("updated_at", "")),
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

    # ── Equipa atribuída (consultores + mediadores) ──
    team_info = await _get_team_info(process)

    # ── RGPD Status ──
    rgpd_info = await _get_rgpd_status(process_id)

    # ── Welcome message (from portal_settings, rendered with variables) ──
    welcome_message = None
    try:
        from routes.portal_settings import _get_portal_settings_doc, render_welcome_message
        settings_doc = await _get_portal_settings_doc()
        template = settings_doc.get("welcome_message_template", "")
        if template:
            consultor_name = team_info["consultores"][0]["name"] if team_info["consultores"] else "a sua equipa"
            empresa_name = process.get("company", "Power Precision")
            welcome_message = render_welcome_message(
                template=template,
                client_name=process.get("client_name", "Cliente"),
                consultor_name=consultor_name,
                empresa_name=empresa_name,
            )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao gerar welcome message: {type(e).__name__}")

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
            "received": received_docs,
            "has_pending": has_pending,
        },
        "rgpd": rgpd_info,
        "team": team_info,
        "consultor": team_info["consultores"][0] if team_info["consultores"] else None,
        "welcome_message": welcome_message,
    }


# ====================================================================
# HELPER: Consultor Info
# ====================================================================

async def _get_user_contact_info(user_id: str) -> dict:
    """Obtém informações de contacto de um utilizador."""
    if not user_id:
        return None
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "password": 0}
    )
    if not user:
        return None
    return {
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "phone": user.get("phone", ""),
        "role": user.get("role", ""),
    }


async def _get_rgpd_status(process_id: str) -> dict:
    """Obtém o estado do RGPD para o processo.
    
    Returns info about RGPD consent status for the client portal.
    - signed: RGPD was signed by the client
    - pending: RGPD was requested but not yet signed
    - none: No RGPD request exists
    
    Enhanced to also return:
    - requested_at: when the RGPD was requested
    - requested_by_name: who requested it
    - For pending status: whether the token is expired or still valid
    """
    try:
        # Find the most recent RGPD request (signed takes priority)
        rgpd = await db.rgpd_requests.find_one(
            {"process_id": process_id, "status": "signed"},
            {"_id": 0, "token": 0}
        )
        if rgpd:
            return {
                "status": "signed",
                "has_rgpd": True,
                "signed_at": rgpd.get("signed_at"),
                "requested_at": rgpd.get("created_at"),
                "requested_by_name": rgpd.get("created_by_name", ""),
            }
        
        # Check for pending
        rgpd = await db.rgpd_requests.find_one(
            {"process_id": process_id, "status": "pending"},
            {"_id": 0, "token": 0}
        )
        if rgpd:
            # Determine if the token is still valid or expired
            token_expired = False
            expires_at_str = rgpd.get("token_expires_at")
            if expires_at_str:
                try:
                    if expires_at_str.endswith('Z'):
                        expires_at_str_clean = expires_at_str[:-1] + '+00:00'
                    else:
                        expires_at_str_clean = expires_at_str
                    expires_at = datetime.fromisoformat(expires_at_str_clean)
                    token_expired = expires_at < datetime.now(timezone.utc)
                except (ValueError, TypeError):
                    token_expired = True
            
            return {
                "status": "pending",
                "has_rgpd": True,
                "expires_at": rgpd.get("token_expires_at"),
                "requested_at": rgpd.get("created_at"),
                "requested_by_name": rgpd.get("created_by_name", ""),
                "token_expired": token_expired,
                "token_valid": not token_expired,
            }
        
        return {"status": "none", "has_rgpd": False}
    except Exception as e:
        logger.warning(f"Erro ao obter estado RGPD para portal: {e}")
        return {"status": "none", "has_rgpd": False}


async def _get_team_info(process: dict) -> dict:
    """Obtém informações da equipa atribuída ao processo.

    Retorna consultores e mediadores como listas separadas, sem duplicados.
    """
    # Gather consultor IDs
    consultor_ids = list(set(filter(None, (
        process.get("assigned_consultor_ids") or
        ([process["assigned_consultor_id"]] if process.get("assigned_consultor_id") else [])
    ))))

    # Gather mediador IDs (excluding consultor IDs to avoid duplicates)
    mediador_ids = list(set(filter(None, (
        process.get("assigned_mediador_ids") or
        ([process["assigned_mediador_id"]] if process.get("assigned_mediador_id") else [])
    ))))
    mediador_ids = [mid for mid in mediador_ids if mid not in consultor_ids]

    # Fetch all
    consultores = []
    for uid in consultor_ids:
        info = await _get_user_contact_info(uid)
        if info:
            consultores.append(info)

    mediadores = []
    for uid in mediador_ids:
        info = await _get_user_contact_info(uid)
        if info:
            mediadores.append(info)

    # Fallback: if no consultores found, show mediadores as main contacts
    if not consultores and mediadores:
        consultores = mediadores
        mediadores = []

    return {
        "consultores": consultores,
        "mediadores": mediadores,
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
    custom_label = data.get("custom_label")  # Custom label for "Outros" category

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
            category, file_size, content_type, now, custom_label
        )

    # Invalidar cache de estatísticas
    await invalidate_stats_cache()

    # ── Audit Trail — registo de upload pelo cliente no histórico do processo ──
    try:
        from services.history import log_history
        client_name = process.get("client_name", "Cliente")
        await log_history(
            process_id,
            user={"id": None, "name": f"{client_name} (Portal)", "role": "client_portal"},
            action="DOCUMENT_UPLOADED_BY_CLIENT",
            field="documento",
            old_value=None,
            new_value=f"{original_filename} [{category}]"
        )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao registar histórico de upload: {e}")

    # Obter URL temporária para preview
    temporary_url = s3_service.get_presigned_url(file_key) or ""

    # ── Notificar equipa atribuída ──
    await _notify_assigned_team_upload(process, original_filename, category)

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
    file_size: int, content_type: str, now: str,
    custom_label: str = None
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
    if custom_label:
        document["custom_label"] = custom_label
    await db.documents.insert_one(document)


async def _notify_assigned_team_upload(process: dict, filename: str, category: str):
    """Notifica TODOS os utilizadores atribuídos ao processo sobre um novo upload do cliente."""
    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process.get("id", "")[:8]
    
    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user:
                await send_notification_with_preference_check(
                    user.get("email"),
                    "Novo Documento Submetido",
                    f"O cliente {client_name} submeteu '{filename}' ({category}) no processo {process_ref} via Portal.",
                    notification_type="document_upload"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar utilizador {uid} sobre upload: {e}")


# ====================================================================
# MESSAGING — Mensagens entre cliente e staff
# ====================================================================

@router.get("/messages/unread")
async def get_unread_messages_count(
    client_data: dict = Depends(get_current_client),
):
    """
    Conta mensagens não lidas do staff para este cliente.

    Retorna o número de mensagens enviadas pelo staff que o cliente
    ainda não leu (read_by_client=False).
    """
    process_id = client_data["process_id"]

    try:
        count = await db.portal_messages.count_documents({
            "process_id": process_id,
            "sender_type": "staff",
            "read_by_client": False,
        })
        return {"unread_count": count}
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao contar mensagens não lidas: {e}")
        return {"unread_count": 0}


@router.get("/messages")
async def get_portal_messages(
    client_data: dict = Depends(get_current_client),
):
    """
    Lista mensagens do processo para o cliente.

    Retorna as últimas 100 mensagens ordenadas por data de criação
    ascendente (mais antigas primeiro). Ao listar, marca automaticamente
    as mensagens do staff como lidas pelo cliente (read_by_client=True).
    """
    process_id = client_data["process_id"]

    try:
        # Buscar últimas 100 mensagens
        messages = await db.portal_messages.find(
            {"process_id": process_id},
            {"_id": 0}
        ).sort("created_at", 1).limit(100).to_list(100)

        # Marcar mensagens do staff como lidas pelo cliente
        try:
            await db.portal_messages.update_many(
                {
                    "process_id": process_id,
                    "sender_type": "staff",
                    "read_by_client": False,
                },
                {"$set": {"read_by_client": True}}
            )
        except Exception as e:
            logger.warning(f"[PORTAL] Erro ao marcar mensagens como lidas: {e}")

        return {
            "messages": messages,
            "total": len(messages),
        }
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao listar mensagens: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar mensagens. Tente novamente."
        )


@router.post("/messages")
async def send_portal_message(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    """
    Envia uma mensagem do cliente para o staff.

    Body:
    - content: Texto da mensagem (obrigatório)
    """
    process = client_data["process"]
    process_id = client_data["process_id"]

    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="A mensagem não pode estar vazia.")
    if len(content) > 5000:
        raise HTTPException(status_code=400, detail="A mensagem não pode exceder 5000 caracteres.")

    now = datetime.now(timezone.utc).isoformat()
    message_id = str(uuid.uuid4())
    client_name = process.get("client_name", "Cliente")

    message_doc = {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "client",
        "sender_id": "client",
        "sender_name": client_name,
        "content": content,
        "created_at": now,
        "read_by_client": True,
        "read_by_staff": False,
    }

    try:
        await db.portal_messages.insert_one(message_doc)
        logger.info(f"[PORTAL] Mensagem enviada pelo cliente para processo {process_id}")
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao enviar mensagem: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao enviar mensagem. Tente novamente."
        )

    # Notificar TODOS os utilizadores atribuídos sobre a nova mensagem do cliente
    await _notify_assigned_team_message(process, process_id, client_name, message_doc)

    # Return without MongoDB _id
    return {
        "id": message_id,
        "process_id": process_id,
        "sender_type": "client",
        "sender_id": "client",
        "sender_name": client_name,
        "content": content,
        "created_at": now,
        "read_by_client": True,
        "read_by_staff": False,
    }


async def _notify_assigned_team_message(process: dict, process_id: str, client_name: str, message_doc: dict):
    """Notifica TODOS os utilizadores atribuídos ao processo sobre uma nova mensagem do cliente.
    
    Também faz broadcast da mensagem para a sala WebSocket do processo (process_{process_id})
    para que qualquer membro da equipa com o processo aberto veja a mensagem em tempo real.
    """
    # ── Recolher TODOS os IDs de utilizadores atribuídos ──
    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process_id[:8]
    
    # ── Notificar cada utilizador atribuído (email + in-app notification) ──
    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if not user:
                continue
            
            # Email notification (com verificação de preferências)
            await send_notification_with_preference_check(
                user.get("email"),
                "Nova Mensagem do Cliente",
                f"O cliente {client_name} enviou uma mensagem no processo {process_ref}.",
                notification_type="portal_message"
            )
            
            # In-app notification (em tempo real via WebSocket)
            try:
                from services.realtime_notifications import send_realtime_notification
                await send_realtime_notification(
                    user_id=uid,
                    title="Nova Mensagem do Cliente",
                    message=f"O cliente {client_name} enviou uma mensagem no processo {process_ref}.",
                    notification_type="portal_message",
                    link=f"/processes/{process_id}",
                    process_id=process_id,
                )
            except Exception as notif_err:
                logger.debug(f"Erro ao enviar notificação in-app para {uid}: {notif_err}")
                
        except Exception as e:
            logger.warning(f"Erro ao notificar utilizador {uid} sobre mensagem do portal: {e}")
    
    # ── Broadcast para a sala WebSocket do processo ──
    try:
        ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
            "id": message_doc.get("id"),
            "process_id": process_id,
            "sender_type": "client",
            "sender_id": "client",
            "sender_name": client_name,
            "content": message_doc.get("content", "")[:200],
            "created_at": message_doc.get("created_at"),
        })
        await manager.broadcast_to_room(f"process_{process_id}", ws_message)
    except Exception as ws_err:
        logger.debug(f"Erro ao broadcast mensagem do portal via WebSocket: {ws_err}")
    
    logger.info(
        f"[PORTAL] Notificados {len(assigned_ids)} utilizadores sobre mensagem "
        f"do cliente {client_name} no processo {process_ref}"
    )


# ====================================================================
# INTEGRAÇÃO AUTOMÁTICA — Portal das Finanças & Segurança Social
# ====================================================================

@router.get("/scraper-status")
async def check_scraper_status():
    """
    Verifica se o serviço de obtenção automática de documentos está disponível.

    Retorna o estado do Playwright e do browser Chromium, para diagnóstico.
    Endpoint público (não requer autenticação) para permitir verificação prévia.

    Em DEV (ENVIRONMENT != production): retorna mock sem importar Playwright.
    """
    # DEV MODE: Mock — não importar Playwright em DEV para poupar RAM
    if os.environ.get('ENVIRONMENT') != 'production':
        return {
            "available": False,
            "playwright_installed": False,
            "chromium_available": False,
            "dev_mode": True,
            "error": "MOCK DEV: Scraper de portais governamentais desativado em DEV para poupar RAM. Funciona apenas em ENVIRONMENT=production.",
        }

    try:
        from services.gov_scraper import check_playwright_available
        result = await check_playwright_available()
        return {
            "available": result.get("playwright_installed") and result.get("chromium_available"),
            "playwright_installed": result.get("playwright_installed", False),
            "chromium_available": result.get("chromium_available", False),
            "browsers_path": result.get("browsers_path"),
            "browsers_dir_exists": result.get("browsers_dir_exists"),
            "error": result.get("error"),
        }
    except Exception as e:
        return {
            "available": False,
            "playwright_installed": False,
            "chromium_available": False,
            "error": str(e),
        }


@router.post("/fetch-financas")
async def fetch_financas_documents(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    """
    Obtém documentos do Portal das Finanças (IRS, Nota de Liquidação).

    SEGURANÇA: As credenciais (NIF + Password) NUNCA são guardadas na BD.
    São usadas apenas em memória para invocar o scraper e descartadas de imediato.

    Body:
    - nif: NIF do cliente (obrigatório, 9 dígitos)
    - password: Password do Portal das Finanças (obrigatório)

    Fluxo:
    1. Envia email ao cliente: "O nosso sistema começou a reunir os seus documentos..."
    2. Invoca o scraper (ou mock) com as credenciais
    3. Em caso de sucesso: anexa documentos ao processo + email de sucesso
    4. Em caso de erro de credenciais: email de erro

    DEV MODE: Se ENVIRONMENT != 'production', retorna mock de sucesso sem invocar Playwright.
    """
    # DEV MODE: Mock do scraper — SÓ PRODUÇÃO lança o browser
    # REGRA ABSOLUTA: Se ENVIRONMENT != 'production', o Chromium NÃO lança.
    if os.environ.get('ENVIRONMENT') != 'production':
        logger.info("[PORTAL] MOCK DEV: fetch-financas desativado em DEV para poupar RAM.")
        return {
            "success": True,
            "message": "MOCK DEV: Acesso ao Portal das Finanças desativado em DEV para poupar RAM. Funciona apenas em ENVIRONMENT=production.",
            "documents_count": 0,
            "dev_mode": True,
        }

    process = client_data["process"]
    process_id = process["id"]
    client_name = process.get("client_name", "Cliente")
    client_email = process.get("client_email", "")

    nif = data.get("nif", "").strip()
    password = data.get("password", "")

    # Validação básica
    if not nif or len(nif) != 9 or not nif.isdigit():
        raise HTTPException(status_code=400, detail="NIF inválido. Deve conter 9 dígitos.")
    if not password:
        raise HTTPException(status_code=400, detail="A password é obrigatória.")

    # ── 1. Enviar email de início de processo ──
    try:
        await _send_portal_fetch_email(
            client_email, client_name, "financas", "started"
        )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao enviar email de início (Finanças): {e}")

    # ── 2. Invocar scraper (Playwright RPA via gov_scraper.py) ──
    try:
        result = await _run_financas_scraper(nif, password, process_id)

        if result.get("success"):
            # ── 3a. Sucesso — anexar documentos + email de sucesso ──
            docs_count = result.get("documents_count", 0)
            logger.info(
                f"[PORTAL] Finanças: {docs_count} documentos obtidos para processo {process_id}"
            )

            try:
                await _send_portal_fetch_email(
                    client_email, client_name, "financas", "success",
                    docs_count=docs_count
                )
            except Exception as e:
                logger.warning(f"[PORTAL] Erro ao enviar email de sucesso (Finanças): {e}")

            # Notificar equipa
            await _notify_assigned_team_fetch(process, "Portal das Finanças", docs_count)

            return {
                "success": True,
                "message": f"Os documentos foram descarregados e anexados ao seu processo com sucesso. ({docs_count} documento{'s' if docs_count != 1 else ''} obtido{'s' if docs_count != 1 else ''})",
                "documents_count": docs_count,
            }
        else:
            # ── 3b. Erro do scraper — diferenciar credenciais vs. erro do sistema ──
            error_detail = result.get("error", "erro_desconhecido")

            # Credenciais inválidas → 401 (erro do utilizador)
            if error_detail == "credenciais_invalidas":
                try:
                    await _send_portal_fetch_email(
                        client_email, client_name, "financas", "error"
                    )
                except Exception as e:
                    logger.warning(f"[PORTAL] Erro ao enviar email de erro (Finanças): {e}")

                raise HTTPException(
                    status_code=401,
                    detail="As credenciais que introduziu estão incorretas. Verifique o seu NIF e password do Portal das Finanças e tente novamente."
                )

            # Erros do sistema (Playwright não instalado, timeout, etc.) → 503
            logger.error(f"[PORTAL] Erro do scraper Finanças: {error_detail}")
            raise HTTPException(
                status_code=503,
                detail="O serviço de obtenção automática de documentos não está disponível de momento. Por favor, faça download manualmente do Portal das Finanças e envie os documentos através do botão de upload."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORTAL] Erro inesperado no scraper Finanças: {type(e).__name__}")

        try:
            await _send_portal_fetch_email(
                client_email, client_name, "financas", "error"
            )
        except:
            pass

        raise HTTPException(
            status_code=500,
            detail="Ocorreu um erro ao obter os documentos. Tente novamente mais tarde ou contacte o seu consultor."
        )


@router.post("/fetch-seguranca-social")
async def fetch_seguranca_social_documents(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    """
    Obtém documentos da Segurança Social.

    SEGURANÇA: As credenciais (NISS + Password) NUNCA são guardadas na BD.
    São usadas apenas em memória para invocar o scraper e descartadas de imediato.

    Body:
    - niss: NISS do cliente (obrigatório, 11 dígitos)
    - password: Password da Segurança Social (obrigatório)

    Fluxo idêntico ao fetch-financas.

    DEV MODE: Se ENVIRONMENT != 'production', retorna mock de sucesso sem invocar Playwright.
    """
    # DEV MODE: Mock do scraper — SÓ PRODUÇÃO lança o browser
    # REGRA ABSOLUTA: Se ENVIRONMENT != 'production', o Chromium NÃO lança.
    if os.environ.get('ENVIRONMENT') != 'production':
        logger.info("[PORTAL] MOCK DEV: fetch-seguranca-social desativado em DEV para poupar RAM.")
        return {
            "success": True,
            "message": "MOCK DEV: Acesso à Segurança Social desativado em DEV para poupar RAM. Funciona apenas em ENVIRONMENT=production.",
            "documents_count": 0,
            "dev_mode": True,
        }

    process = client_data["process"]
    process_id = process["id"]
    client_name = process.get("client_name", "Cliente")
    client_email = process.get("client_email", "")

    niss = data.get("niss", "").strip()
    password = data.get("password", "")

    # Validação básica
    if not niss or len(niss) != 11 or not niss.isdigit():
        raise HTTPException(status_code=400, detail="NISS inválido. Deve conter 11 dígitos.")
    if not password:
        raise HTTPException(status_code=400, detail="A password é obrigatória.")

    # ── 1. Enviar email de início de processo ──
    try:
        await _send_portal_fetch_email(
            client_email, client_name, "seguranca_social", "started"
        )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao enviar email de início (Seg. Social): {e}")

    # ── 2. Invocar scraper (Playwright RPA via gov_scraper.py) ──
    try:
        result = await _run_seguranca_social_scraper(niss, password, process_id)

        if result.get("success"):
            docs_count = result.get("documents_count", 0)
            logger.info(
                f"[PORTAL] Seg. Social: {docs_count} documentos obtidos para processo {process_id}"
            )

            try:
                await _send_portal_fetch_email(
                    client_email, client_name, "seguranca_social", "success",
                    docs_count=docs_count
                )
            except Exception as e:
                logger.warning(f"[PORTAL] Erro ao enviar email de sucesso (Seg. Social): {e}")

            await _notify_assigned_team_fetch(process, "Segurança Social", docs_count)

            return {
                "success": True,
                "message": f"Os documentos foram descarregados e anexados ao seu processo com sucesso. ({docs_count} documento{'s' if docs_count != 1 else ''} obtido{'s' if docs_count != 1 else ''})",
                "documents_count": docs_count,
            }
        else:
            error_detail = result.get("error", "erro_desconhecido")

            # Credenciais inválidas → 401 (erro do utilizador)
            if error_detail == "credenciais_invalidas":
                try:
                    await _send_portal_fetch_email(
                        client_email, client_name, "seguranca_social", "error"
                    )
                except Exception as e:
                    logger.warning(f"[PORTAL] Erro ao enviar email de erro (Seg. Social): {e}")

                raise HTTPException(
                    status_code=401,
                    detail="As credenciais que introduziu estão incorretas. Verifique o seu NISS e password da Segurança Social e tente novamente."
                )

            # Erros do sistema (Playwright não instalado, timeout, etc.) → 503
            logger.error(f"[PORTAL] Erro do scraper Seg. Social: {error_detail}")
            raise HTTPException(
                status_code=503,
                detail="O serviço de obtenção automática de documentos não está disponível de momento. Por favor, faça download manualmente da Segurança Social e envie os documentos através do botão de upload."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORTAL] Erro inesperado no scraper Seg. Social: {type(e).__name__}")

        try:
            await _send_portal_fetch_email(
                client_email, client_name, "seguranca_social", "error"
            )
        except:
            pass

        raise HTTPException(
            status_code=500,
            detail="Ocorreu um erro ao obter os documentos. Tente novamente mais tarde ou contacte o seu consultor."
        )


# ====================================================================
# HELPERS: Scraper invocation (gov_scraper.py) & email notifications
# ====================================================================

async def _run_financas_scraper(nif: str, password: str, process_id: str) -> dict:
    """
    Invoca o scraper do Portal das Finanças (gov_scraper.py).

    O scraper utiliza Playwright em modo headless para:
    1. Autenticar no Portal das Finanças via acesso.gov.pt
    2. Navegar até à secção de IRS
    3. Descarregar a Declaração de IRS e a Nota de Liquidação
    4. Retornar os PDFs em bytes

    Após obter os documentos, faz upload para o S3 e cria registos na BD.

    SEGURANÇA: As credenciais (NIF + password) são usadas APENAS em memória
    pelo scraper e eliminadas logo após a execução (del + gc.collect).
    NUNCA são persistidas na BD ou impressas no log.
    """
    from services.gov_scraper import fetch_financas_documents

    # Obter informações do processo para upload S3
    process = await db.processes.find_one({"id": process_id})
    client_name = process.get("client_name", "cliente") if process else "cliente"
    s3_folder = process.get("s3_folder") if process else None

    # ── Invocar o scraper real ──
    result = await fetch_financas_documents(nif, password)

    # Neste ponto, o scraper já limpou as credenciais da memória
    # (garantido pelo `finally` em fetch_financas_documents)

    if not result.success:
        error_map = {
            "credenciais_invalidas": "credenciais_invalidas",
            "timeout": "timeout_scraper",
            "sem_documentos": "sem_documentos",
        }
        return {"success": False, "error": error_map.get(result.error, result.error or "erro_desconhecido")}

    # ── Upload dos documentos para o S3 e registo na BD ──
    now = datetime.now(timezone.utc).isoformat()
    docs_registered = 0

    for doc in result.documents:
        try:
            # Upload para o S3
            import io
            file_obj = io.BytesIO(doc.content_bytes)
            s3_path = s3_service.upload_file(
                file_obj=file_obj,
                client_id=process_id,
                client_name=client_name,
                category=doc.category,
                filename=doc.filename,
                content_type=doc.content_type,
                s3_folder=s3_folder,
            )

            if not s3_path:
                logger.warning(f"[PORTAL] Falha no upload S3 para {doc.filename} — a criar registo sem S3 path")

            # Criar registo na BD
            doc_id = str(uuid.uuid4())
            doc_record = {
                "id": doc_id,
                "process_id": process_id,
                "filename": doc.filename,
                "original_filename": doc.filename,
                "category": doc.category,
                "custom_label": doc.label if "captura" in doc.label else None,
                "status": "RECEIVED",
                "source": "auto_financas",
                "uploaded_at": now,
                "uploaded_by": "system_financas_scraper",
                "content_type": doc.content_type,
                "file_size": len(doc.content_bytes),
                "s3_path": s3_path,
                "auto_fetched": True,
            }
            # Remover custom_label se for None
            if not doc_record["custom_label"]:
                del doc_record["custom_label"]

            await db.documents.insert_one(doc_record)
            docs_registered += 1

            logger.info(
                f"[PORTAL] Documento Finanças registado: {doc.filename} "
                f"({len(doc.content_bytes)} bytes, S3: {'sim' if s3_path else 'não'})"
            )

        except Exception as e:
            logger.error(f"[PORTAL] Erro ao registar documento {doc.filename}: {type(e).__name__}")

    return {"success": True, "documents_count": docs_registered}


async def _run_seguranca_social_scraper(niss: str, password: str, process_id: str) -> dict:
    """
    Invoca o scraper da Segurança Social (gov_scraper.py).

    O scraper utiliza Playwright em modo headless para:
    1. Autenticar na Segurança Social Direta
    2. Navegar até à secção de documentos
    3. Descarregar a Situação Contributiva e o Extrato de Remunerações
    4. Retornar os PDFs em bytes

    SEGURANÇA: As credenciais (NISS + password) são usadas APENAS em memória
    pelo scraper e eliminadas logo após a execução (del + gc.collect).
    NUNCA são persistidas na BD ou impressas no log.
    """
    from services.gov_scraper import fetch_seg_social_documents

    # Obter informações do processo para upload S3
    process = await db.processes.find_one({"id": process_id})
    client_name = process.get("client_name", "cliente") if process else "cliente"
    s3_folder = process.get("s3_folder") if process else None

    # ── Invocar o scraper real ──
    result = await fetch_seg_social_documents(niss, password)

    # Neste ponto, o scraper já limpou as credenciais da memória

    if not result.success:
        error_map = {
            "credenciais_invalidas": "credenciais_invalidas",
            "timeout": "timeout_scraper",
            "sem_documentos": "sem_documentos",
        }
        return {"success": False, "error": error_map.get(result.error, result.error or "erro_desconhecido")}

    # ── Upload dos documentos para o S3 e registo na BD ──
    now = datetime.now(timezone.utc).isoformat()
    docs_registered = 0

    for doc in result.documents:
        try:
            # Upload para o S3
            import io
            file_obj = io.BytesIO(doc.content_bytes)
            s3_path = s3_service.upload_file(
                file_obj=file_obj,
                client_id=process_id,
                client_name=client_name,
                category=doc.category,
                filename=doc.filename,
                content_type=doc.content_type,
                s3_folder=s3_folder,
            )

            if not s3_path:
                logger.warning(f"[PORTAL] Falha no upload S3 para {doc.filename} — a criar registo sem S3 path")

            # Criar registo na BD
            doc_id = str(uuid.uuid4())
            doc_record = {
                "id": doc_id,
                "process_id": process_id,
                "filename": doc.filename,
                "original_filename": doc.filename,
                "category": doc.category,
                "custom_label": doc.label if "captura" in doc.label else None,
                "status": "RECEIVED",
                "source": "auto_seguranca_social",
                "uploaded_at": now,
                "uploaded_by": "system_seguranca_social_scraper",
                "content_type": doc.content_type,
                "file_size": len(doc.content_bytes),
                "s3_path": s3_path,
                "auto_fetched": True,
            }
            # Remover custom_label se for None
            if not doc_record["custom_label"]:
                del doc_record["custom_label"]

            await db.documents.insert_one(doc_record)
            docs_registered += 1

            logger.info(
                f"[PORTAL] Documento Seg. Social registado: {doc.filename} "
                f"({len(doc.content_bytes)} bytes, S3: {'sim' if s3_path else 'não'})"
            )

        except Exception as e:
            logger.error(f"[PORTAL] Erro ao registar documento {doc.filename}: {type(e).__name__}")

    return {"success": True, "documents_count": docs_registered}


async def _send_portal_fetch_email(
    to_email: str,
    client_name: str,
    source: str,
    status: str,
    docs_count: int = 0
):
    """
    Envia email de estado ao cliente sobre a obtenção automática de documentos.

    Utiliza o serviço de email principal (send_email) em vez de SMTP directo,
    para suportar tanto Resend API como SMTP, e garantir que os emails são
    registados no histórico do processo.

    Status:
    - started:  "O nosso sistema automático começou a reunir os seus documentos..."
    - error:    "As credenciais que introduziu estão incorretas..."
    - success:  "Os documentos foram descarregados e anexados ao seu processo com sucesso..."
    """
    if not to_email:
        return

    source_label = {
        "financas": "Portal das Finanças",
        "seguranca_social": "Segurança Social",
    }.get(source, source)

    if status == "started":
        subject = f"Obtenção de Documentos — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"O nosso sistema automático começou a reunir os seus documentos "
            f"junto do {source_label}.\n\n"
            f"Iremos notificá-lo(a) assim que o processo esteja concluído.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    elif status == "error":
        subject = f"Credenciais Incorretas — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"As credenciais que introduziu estão incorretas para o {source_label}.\n\n"
            f"Por favor, verifique os seus dados e tente novamente no portal, "
            f"ou contacte o seu consultor para assistência.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    elif status == "success":
        subject = f"Documentos Obtidos com Sucesso — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"Os documentos foram descarregados e anexados ao seu processo com sucesso "
            f"junto do {source_label} ({docs_count} documento{'s' if docs_count != 1 else ''} obtido{'s' if docs_count != 1 else ''}).\n\n"
            f"Não é necessário qualquer ação adicional da sua parte.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    else:
        return

    html_content = f"""
    <html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #0f766e; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0;">Power Precision</h2>
        </div>
        <div style="background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px;">
            <p>{body_text.replace(chr(10), '<br>')}</p>
        </div>
        <p style="text-align: center; font-size: 11px; color: #999; margin-top: 15px;">
            Este email foi enviado automaticamente. Não responda diretamente.
        </p>
    </div>
    </body></html>
    """

    # ── Enviar via serviço de email principal (Resend API ou SMTP) ──
    try:
        from services.email_service import send_email
        await send_email(
            account_name="power",
            to_emails=[to_email],
            subject=subject,
            body=body_text,
            body_html=html_content,
            force_system=True,
        )
        logger.info(f"[PORTAL] Email de estado '{status}' enviado para {to_email} ({source_label})")
    except Exception as e:
        # Fallback para SMTP directo se o serviço principal falhar
        logger.warning(f"[PORTAL] Serviço de email principal falhou, a tentar SMTP directo: {type(e).__name__}")
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            smtp_server = os.environ.get('SMTP_SERVER')
            smtp_port = int(os.environ.get('SMTP_PORT', 465))
            smtp_email = os.environ.get('SMTP_EMAIL')
            smtp_password_env = os.environ.get('SMTP_PASSWORD')

            if not all([smtp_server, smtp_email, smtp_password_env]):
                logger.warning("[PORTAL] SMTP também não configurado — email de estado não enviado")
                return

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = smtp_email
            msg['To'] = to_email
            msg.attach(MIMEText(html_content, 'html'))

            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context, timeout=30) as server:
                server.login(smtp_email, smtp_password_env)
                server.sendmail(smtp_email, to_email, msg.as_string())

            logger.info(f"[PORTAL] Email de estado '{status}' enviado via SMTP fallback para {to_email}")
        except Exception as fallback_err:
            logger.warning(f"[PORTAL] SMTP fallback também falhou: {type(fallback_err).__name__}")


async def _notify_assigned_team_fetch(process: dict, source_name: str, docs_count: int):
    """Notifica a equipa atribuída sobre documentos obtidos automaticamente."""
    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process.get("id", "")[:8]

    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user:
                await send_notification_with_preference_check(
                    user.get("email"),
                    f"Documentos Obtidos — {source_name}",
                    f"O sistema obteve {docs_count} documento{'s' if docs_count != 1 else ''} do {source_name} para o cliente {client_name} no processo {process_ref}.",
                    notification_type="document_auto_fetch"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar {uid} sobre fetch {source_name}: {e}")


def _get_all_assigned_user_ids(process: dict) -> list:
    """Obtém lista deduplicada de TODOS os user_ids atribuídos ao processo.

    Inclui consultores, mediadores, indexação e parceiro.
    Usa os campos novos (_ids) com fallback para os antigos (_id).
    """
    ids = set()
    
    # Consultores (lista nova)
    for uid in (process.get("assigned_consultor_ids") or []):
        if uid:
            ids.add(uid)
    # Consultor singular (fallback)
    uid = process.get("assigned_consultor_id")
    if uid:
        ids.add(uid)
    
    # Mediadores (lista nova)
    for uid in (process.get("assigned_mediador_ids") or []):
        if uid:
            ids.add(uid)
    # Mediador singular (fallback)
    uid = process.get("assigned_mediador_id")
    if uid:
        ids.add(uid)
    
    # Indexação
    uid = process.get("assigned_indexacao_id")
    if uid:
        ids.add(uid)
    
    # Parceiro
    uid = process.get("assigned_parceiro_id")
    if uid:
        ids.add(uid)
    
    return list(ids)


# ====================================================================
# SMART MATCH — Recomendações de Imóveis (Consultor → Portal do Cliente)
# ====================================================================

@router.post("/recommendations")
async def create_recommendations(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Adiciona imóveis recomendados ao perfil do processo/cliente.

    Payload:
    - client_id: ID do cliente (obrigatório)
    - process_id: ID do processo (obrigatório)
    - property_ids: Lista de IDs de imóveis recomendados (obrigatório)

    Os imóveis ficam guardados na lista 'recommended_properties' do processo,
    para serem consumidos pelo Portal do Cliente.
    """
    client_id = data.get("client_id")
    process_id = data.get("process_id")
    property_ids = data.get("property_ids", [])

    if not process_id:
        raise HTTPException(status_code=400, detail="process_id é obrigatório")
    if not property_ids:
        raise HTTPException(status_code=400, detail="property_ids não pode estar vazio")

    # Verificar que o processo existe
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # Buscar detalhes dos imóveis
    properties = await db.properties.find(
        {"id": {"$in": property_ids}},
        {"_id": 0}
    ).to_list(50)

    # Criar entrada de recomendação
    now = datetime.now(timezone.utc).isoformat()
    new_recommendations = []

    for prop in properties:
        prop_price = prop.get("financials", {}).get("asking_price") if prop.get("financials") else None
        photos = prop.get("photos", [])
        main_photo = photos[0] if photos else None

        new_recommendations.append({
            "property_id": prop.get("id"),
            "internal_reference": prop.get("internal_reference"),
            "title": prop.get("title", "Sem título"),
            "price": prop_price,
            "property_type": prop.get("property_type"),
            "bedrooms": prop.get("features", {}).get("bedrooms") if prop.get("features") else None,
            "area": prop.get("features", {}).get("useful_area") if prop.get("features") else None,
            "municipality": (prop.get("address", {}).get("municipality") or "") if prop.get("address") else "",
            "district": (prop.get("address", {}).get("district") or "") if prop.get("address") else "",
            "photo": main_photo,
            "recommended_at": now,
            "recommended_by": user.get("id"),
            "recommended_by_name": user.get("name", "Consultor"),
            "viewed_by_client": False,
        })

    # Adicionar ao processo (append para não sobrescrever recomendações anteriores)
    existing = process.get("recommended_properties", [])

    # Remover duplicados (se já existia uma recomendação para o mesmo imóvel)
    existing_ids = {r.get("property_id") for r in existing}
    unique_new = [r for r in new_recommendations if r["property_id"] not in existing_ids]

    updated_recommendations = existing + unique_new

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "recommended_properties": updated_recommendations,
            "updated_at": now,
        }}
    )

    # Registar no histórico
    try:
        from services.history import log_history
        prop_names = ", ".join([r["title"] for r in unique_new[:5]])
        await log_history(
            process_id,
            user=user,
            action="PROPERTY_RECOMMENDED",
            field="recommended_properties",
            old_value=None,
            new_value=f"{len(unique_new)} imóvel(ns) recomendado(s): {prop_names}"
        )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao registar histórico de recomendação: {e}")

    logger.info(
        f"[SMART MATCH] {len(unique_new)} imóveis recomendados pelo consultor "
        f"{user.get('name', 'N/A')} para o processo {process_id}"
    )

    return {
        "success": True,
        "added_count": len(unique_new),
        "total_recommendations": len(updated_recommendations),
        "recommendations": unique_new,
    }


@router.get("/recommendations")
async def get_recommendations_for_client(
    client_data: dict = Depends(get_current_client)
):
    """
    Obtém a lista de imóveis recomendados pelo consultor para este processo.
    Endpoint consumido pelo Portal do Cliente.

    Também marca as recomendações como visualizadas pelo cliente.
    """
    process = client_data["process"]
    process_id = process["id"]

    recommendations = process.get("recommended_properties", [])

    # Marcar como visualizadas pelo cliente
    if recommendations:
        now = datetime.now(timezone.utc).isoformat()
        updated_recs = []
        for rec in recommendations:
            if not rec.get("viewed_by_client"):
                rec["viewed_by_client"] = True
                rec["viewed_at"] = now
            updated_recs.append(rec)

        await db.processes.update_one(
            {"id": process_id},
            {"$set": {"recommended_properties": updated_recs}}
        )

    return {
        "process_id": process_id,
        "total": len(recommendations),
        "recommendations": recommendations,
    }


# ====================================================================
# DIAGNÓSTICO — Verificar estado do scraper
# ====================================================================

# NOTE: The public scraper-status endpoint is already defined above (line ~985).
# A previous duplicate with auth was removed — the endpoint is intentionally
# public so the client portal can check availability before prompting for
# credentials. See check_scraper_status() above.


# ====================================================================
# VISITS — Pedido de Visita pelo Cliente (bidirecional)
# ====================================================================

@router.post("/visits/request")
async def request_portal_visit(
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    """
    Cliente pede uma visita a um imóvel através do Portal.
    
    Fluxo:
    1. Recebe URL do anúncio do imóvel
    2. Invoca o Scraper para extrair dados (Preço, Tipologia, Morada, Foto)
    3. Cria registo de visita com status 'solicitada'
    4. Notifica a equipa atribuída
    
    Body:
    - url: Link do imóvel (obrigatório)
    - process_id: ID do processo (opcional, usa o do token se não fornecido)
    - notes: Notas adicionais (opcional)
    """
    process = client_data["process"]
    process_id = data.get("process_id") or client_data["process_id"]
    url = data.get("url", "").strip()
    notes = data.get("notes", "").strip()
    
    if not url:
        raise HTTPException(status_code=400, detail="O link do imóvel é obrigatório.")
    
    # ── 1. Invocar Scraper para extrair dados do anúncio ──
    scraped_data = None
    scraper_error = None
    try:
        from services.property_scraper import extract_property_data
        scraped_result = await extract_property_data(url)
        scraped_data = {
            "title": scraped_result.title,
            "price": scraped_result.price,
            "location": scraped_result.location,
            "typology": scraped_result.typology,
            "area": scraped_result.area,
            "photo_url": scraped_result.photo_url,
            "source": scraped_result.source,
            "url": url,
            "consultant": {
                "name": scraped_result.consultant.name if scraped_result.consultant else None,
                "phone": scraped_result.consultant.phone if scraped_result.consultant else None,
                "email": scraped_result.consultant.email if scraped_result.consultant else None,
                "agency_name": scraped_result.consultant.agency_name if scraped_result.consultant else None,
            } if scraped_result.consultant else None,
            "raw_data": scraped_result.raw_data,
        }
        # Se o scraper retornou erro, guardar
        if scraped_result.source == "error":
            scraper_error = scraped_result.raw_data.get("error", "Erro desconhecido no scraper")
    except Exception as e:
        scraper_error = str(e)
        logger.warning(f"[PORTAL] Erro no scraper para URL {url}: {e}")
    
    # ── 2. Criar registo de visita com status 'solicitada' ──
    now = datetime.now(timezone.utc).isoformat()
    visit_id = str(uuid.uuid4())
    client_name = process.get("client_name", "Cliente")
    
    # Dados do imóvel extraídos pelo scraper (ou fallback vazio)
    property_title = scraped_data.get("title") if scraped_data else None
    property_price = scraped_data.get("price") if scraped_data else None
    property_photo = scraped_data.get("photo_url") if scraped_data else None
    property_location = scraped_data.get("location") if scraped_data else None
    property_typology = scraped_data.get("typology") if scraped_data else None
    property_source = scraped_data.get("source") if scraped_data else None
    
    # Se o scraper não conseguiu extrair título, usar o URL
    if not property_title:
        property_title = f"Imóvel de {url.split('//')[-1][:50]}..."
    
    visit_doc = {
        "id": visit_id,
        "property_id": None,  # Sem imóvel interno — veio do scraper
        "property_title": property_title,
        "property_photo": property_photo,
        "property_address": {"municipality": property_location, "district": ""} if property_location else {},
        "client_id": process_id,
        "client_name": client_name,
        "client_email": process.get("client_email", ""),
        "client_phone": process.get("client_phone", ""),
        "consultor_id": None,  # Ainda sem consultor atribuído
        "consultor_name": None,
        "scheduled_date": None,  # Ainda por agendar
        "status": "solicitada",
        "notes": notes,
        "source": "portal_client",  # Marca que veio do portal
        "scraped_data": scraped_data,  # Dados extraídos pelo scraper
        "scraped_url": url,  # URL original colada pelo cliente
        "scraper_error": scraper_error,  # Se houve erro no scraper
        "created_at": now,
        "updated_at": now,
        "created_by": "portal_client",
        "company_id": process.get("company_id"),
    }
    
    await db.visits.insert_one(visit_doc)
    
    # ── 3. Registar no histórico do processo ──
    try:
        from services.history import log_history
        await log_history(
            process_id,
            user={"id": None, "name": f"{client_name} (Portal)", "role": "client_portal"},
            action="VISIT_REQUESTED_BY_CLIENT",
            field="visita",
            old_value=None,
            new_value=f"Pedido de visita a '{property_title}' ({url})"
        )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao registar histórico de visita: {e}")
    
    # ── 4. Notificar equipa atribuída ──
    assigned_ids = _get_all_assigned_user_ids(process)
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process_id[:8]
    
    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user:
                await send_notification_with_preference_check(
                    user.get("email"),
                    "Pedido de Visita do Cliente",
                    f"O cliente {client_name} pediu uma visita a um imóvel no processo {process_ref}.",
                    notification_type="visit_request"
                )
                # In-app notification
                try:
                    from services.realtime_notifications import send_realtime_notification
                    await send_realtime_notification(
                        user_id=uid,
                        title="Pedido de Visita do Cliente",
                        message=f"O cliente {client_name} pediu uma visita a '{property_title}' no processo {process_ref}.",
                        notification_type="visit_request",
                        link=f"/visitas",
                        process_id=process_id,
                    )
                except Exception as notif_err:
                    logger.debug(f"Erro ao enviar notificação in-app para {uid}: {notif_err}")
        except Exception as e:
            logger.warning(f"[PORTAL] Erro ao notificar utilizador {uid} sobre pedido de visita: {e}")
    
    # Broadcast WebSocket
    try:
        ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
            "id": visit_id,
            "process_id": process_id,
            "type": "visit_request",
            "client_name": client_name,
            "property_title": property_title,
            "url": url,
            "created_at": now,
        })
        await manager.broadcast_to_room(f"process_{process_id}", ws_message)
    except Exception as ws_err:
        logger.debug(f"Erro ao broadcast pedido de visita via WebSocket: {ws_err}")
    
    logger.info(
        f"[PORTAL] Pedido de visita criado: {visit_id} — "
        f"Cliente {client_name}, URL {url}, Processo {process_ref}"
    )
    
    visit_doc.pop("_id", None)
    return visit_doc


@router.get("/visits")
async def get_portal_visits(
    client_data: dict = Depends(get_current_client),
):
    """
    Lista todas as visitas ligadas a este processo/cliente.
    Inclui visitas pedidas pelo cliente e visitas agendadas pelo consultor.
    
    Endpoint consumido pelo Portal do Cliente.
    """
    process = client_data["process"]
    process_id = client_data["process_id"]
    
    try:
        visits = await db.visits.find(
            {"client_id": process_id},
            {"_id": 0, "scraped_data.raw_data": 0}  # Não enviar raw_data pesado
        ).sort("created_at", -1).limit(50).to_list(50)
        
        # Mapear status para labels client-friendly
        status_labels = {
            "solicitada": "A aguardar agendamento",
            "agendada": "Agendada",
            "concluida": "Concluída",
            "cancelada": "Cancelada",
        }
        
        for visit in visits:
            visit["status_label"] = status_labels.get(visit.get("status", ""), visit.get("status", ""))
        
        return {
            "visits": visits,
            "total": len(visits),
        }
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao listar visitas: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar visitas. Tente novamente."
        )
