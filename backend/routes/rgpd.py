"""
Rotas RGPD - Regulamento Geral sobre a Proteção de Dados

Endpoints para gestão de consentimentos RGPD:
- Solicitar RGPD (envio de email com link temporário)
- Validar token e mostrar página de RGPD
- Assinar RGPD
- Verificar estado do RGPD para um processo
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from database import db
from models.rgpd import (
    RGPDCreate, RGPDResponse, RGPDStatusResponse,
    RGPDConsentData, RGPDPublicView, RGPDStatusEnum
)
from services.auth import get_current_user, require_staff
from services.rgpd_service import (
    create_rgpd_request,
    validate_token,
    get_rgpd_by_process,
    sign_rgpd,
    send_rgpd_email,
    RGPD_REQUESTS_COLLECTION,
    TOKEN_EXPIRY_HOURS
)

async def _add_process_activity(process_id: str, user_id: str, user_name: str, action: str, details: str = ""):
    """Insere uma atividade/comentário automático na timeline do processo."""
    try:
        activity = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user_name,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "system"
        }
        await db.processes.update_one(
            {"id": process_id},
            {"$push": {"activities": activity}}
        )
    except Exception as e:
        logger.warning(f"Não foi possível registar atividade RGPD no processo {process_id}: {e}")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rgpd", tags=["RGPD"])


async def _get_rgpd_or_404(request_id: str):
    """
    Função auxiliar para obter um RGPD ou lançar erro 404.
    
    Args:
        request_id: ID do pedido RGPD
        
    Returns:
        Documento do RGPD
        
    Raises:
        HTTPException: Se o RGPD não for encontrado
    """
    rgpd = await db[RGPD_REQUESTS_COLLECTION].find_one({"id": request_id})
    if not rgpd:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")
    return rgpd


@router.post("/request", response_model=RGPDResponse)
async def request_rgpd(
    data: RGPDCreate,
    user: dict = Depends(require_staff())
):
    """
    Solicitar consentimento RGPD para um processo.
    
    Envia um email para o cliente com um link temporário (24h) para assinar o RGPD.
    
    Permissões: Todos os staff podem solicitar.
    """
    try:
        # Verificar se o processo existe
        process = await db.processes.find_one({"id": data.process_id})
        if not process:
            raise HTTPException(status_code=404, detail="Processo não encontrado")
        
        # Criar pedido de RGPD
        result = await create_rgpd_request(
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            user=user
        )
        
        if not result.get("success"):
            logger.error(f"Erro ao criar pedido RGPD: {result}")
            raise HTTPException(status_code=500, detail="Erro ao criar pedido de RGPD")
        
        # Se já existe e está assinado, retornar informação
        if result.get("existing"):
            if result.get("status") == "signed":
                return RGPDResponse(
                    id=result["request_id"],
                    process_id=data.process_id,
                    client_name=data.client_name,
                    client_email=data.client_email,
                    status=RGPDStatusEnum.SIGNED,
                    signed_at=result.get("signed_at"),
                    created_at="",
                    created_by_name=user.get("name", "")
                )
            elif result.get("status") == "pending":
                return RGPDResponse(
                    id=result["request_id"],
                    process_id=data.process_id,
                    client_name=data.client_name,
                    client_email=data.client_email,
                    status=RGPDStatusEnum.PENDING,
                    token_expires_at=result.get("expires_at"),
                    created_at="",
                    created_by_name=user.get("name", "")
                )
        
        # Enviar email com o link
        email_sent = await send_rgpd_email(
            client_email=data.client_email,
            client_name=data.client_name,
            token=result["token"],
            request_id=result["request_id"],
            user_email=user["email"]
        )
        
        if not email_sent:
            logger.warning("RGPD created but email failed to send")
        
        # M8 - Registar atividade no processo
        email_status = "enviado" if email_sent else "falhou"
        await _add_process_activity(
            process_id=data.process_id,
            user_id=user.get("id", "system"),
            user_name=user.get("name", "Sistema"),
            action=f"RGPD solicitado — email {email_status} para {data.client_email}",
            details=f"Link de assinatura enviado para o cliente. Expira em {TOKEN_EXPIRY_HOURS}h."
        )
        
        return RGPDResponse(
            id=result["request_id"],
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            status=RGPDStatusEnum.PENDING,
            token_expires_at=result["expires_at"],
            created_at="",
            created_by_name=user.get("name", "")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado em request_rgpd: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/validate/{token}", response_model=RGPDPublicView)
async def validate_rgpd_token(token: str):
    """
    Validar token de RGPD e retornar dados para a página pública.
    
    Este endpoint é público (sem autenticação) para permitir que
    o cliente aceda à página de RGPD através do link no email.
    """
    request = await validate_token(token)
    
    if not request:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    
    from datetime import datetime, timezone
    
    return RGPDPublicView(
        id=request["id"],
        client_name=request["client_name"],
        status=RGPDStatusEnum.PENDING,
        created_at=request["created_at"],
        expires_at=request["token_expires_at"],
        valid=True
    )


@router.post("/sign/{token}")
async def sign_rgpd_form(
    token: str,
    consent_data: RGPDConsentData
):
    """
    Assinar o RGPD.
    
    Este endpoint é público (sem autenticação) para permitir que
    o cliente assine o RGPD através do link no email.
    """
    result = await sign_rgpd(token, consent_data.model_dump())
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao assinar RGPD"))
    
    # M8 - Registar atividade de assinatura no processo
    process_id = result.get("process_id")
    if process_id:
        await _add_process_activity(
            process_id=process_id,
            user_id="client",
            user_name=consent_data.nome or "Cliente",
            action="RGPD assinado pelo cliente",
            details=f"Documento RGPD assinado digitalmente. NIF: {consent_data.contribuinte or 'N/A'}."
        )
    
    return {
        "success": True,
        "message": "RGPD assinado com sucesso",
        "process_id": result["process_id"]
    }


@router.get("/status/{process_id}", response_model=RGPDStatusResponse)
async def get_rgpd_status(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Verificar estado do RGPD para um processo.
    
    Permissões: Qualquer utilizador autenticado pode verificar.
    """
    try:
        # Validar se process_id é um UUID válido
        import uuid
        try:
            uuid.UUID(process_id)
        except (ValueError, TypeError):
            logger.warning(f"process_id inválido fornecido: {process_id}")
            return RGPDStatusResponse(has_rgpd=False)
        
        result = await get_rgpd_by_process(process_id)
        
        if not result:
            return RGPDStatusResponse(has_rgpd=False)
        
        return RGPDStatusResponse(
            has_rgpd=result.get("has_rgpd", False),
            status=result.get("status"),
            signed_at=result.get("signed_at"),
            pdf_url=result.get("pdf_url"),
            request_id=result.get("request_id")
        )
    except Exception as e:
        logger.error(f"Erro ao verificar estado RGPD para processo {process_id}: {e}", exc_info=True)
        # Retornar resposta vazia em vez de erro
        return RGPDStatusResponse(has_rgpd=False)


@router.get("/data/{token}")
async def get_rgpd_form_data(token: str):
    """
    Obter dados para preencher o formulário de RGPD.
    
    Este endpoint é público e retorna os dados do processo
    para pré-preencher o formulário de RGPD.
    """
    request = await validate_token(token)
    
    if not request:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    
    # Buscar dados do processo
    process = await db.processes.find_one({"id": request["process_id"]})
    
    personal_data = process.get("personal_data", {}) if process else {}
    
    return {
        "client_name": request["client_name"],
        "client_email": request["client_email"],
        "nif": personal_data.get("nif", ""),
        "morada": personal_data.get("morada_fiscal", ""),
        "documento_id": personal_data.get("documento_id", ""),
        "data_validade_cc": personal_data.get("data_validade_cc", "")
    }


@router.get("/list/{process_id}")
async def list_rgpd_requests(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Listar todos os pedidos de RGPD para um processo.

    Permissões: Qualquer utilizador autenticado.
    """
    requests = await db.rgpd_requests.find(
        {"process_id": process_id},
        {"_id": 0, "token": 0}  # Não expor o token
    ).sort("created_at", -1).to_list(20)

    return {
        "requests": requests,
        "total": len(requests)
    }


# ============ ENDPOINTS DE ADMINISTRAÇÃO ============

@router.get("/admin/all")
async def list_all_rgpd(
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(require_staff())
):
    """
    Listar todos os RGPDs (administração).

    Permissões: Apenas staff.
    Query params:
    - status: Filtrar por estado (pending, signed, expired, cancelled)
    - search: Pesquisar por nome ou NIF
    - page: Página (default: 1)
    - limit: Itens por página (default: 20)
    """
    try:
        query = {}

        if status:
            query["status"] = status

        if search:
            query["$or"] = [
                {"client_name": {"$regex": search, "$options": "i"}},
                {"consent_data.contribuinte": {"$regex": search, "$options": "i"}},
                {"consent_data.nome": {"$regex": search, "$options": "i"}}
            ]

        skip = (page - 1) * limit

        total = await db[RGPD_REQUESTS_COLLECTION].count_documents(query)

        requests = await db[RGPD_REQUESTS_COLLECTION].find(
            query,
            {"_id": 0, "token": 0}
        ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

        return {
            "requests": requests,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit
        }
    except Exception as e:
        logger.error(f"Erro ao obter RGPD admin all: {e}")
        return {
            "requests": [],
            "total": 0,
            "page": page,
            "limit": limit,
            "pages": 0
        }


@router.get("/admin/{request_id}")
async def get_rgpd_by_id(
    request_id: str,
    user: dict = Depends(require_staff())
):
    """
    Obter detalhes de um RGPD específico.

    Permissões: Apenas staff.
    """
    request = await db[RGPD_REQUESTS_COLLECTION].find_one(
        {"id": request_id},
        {"_id": 0, "token": 0}
    )

    if not request:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")

    # Buscar dados do processo associado
    process = await db.processes.find_one(
        {"id": request["process_id"]},
        {"_id": 0, "id": 1, "client_name": 1, "status": 1}
    )

    return {
        "rgpd": request,
        "process": process
    }


@router.put("/admin/{request_id}")
async def update_rgpd_data(
    request_id: str,
    consent_data: RGPDConsentData,
    user: dict = Depends(require_staff())
):
    """
    Atualizar dados do RGPD.

    Permissões: Apenas staff.
    """
    # Verificar se o RGPD existe
    existing = await _get_rgpd_or_404(request_id)

    # Atualizar dados
    update_data = consent_data.model_dump()

    # Manter a data de assinatura original se existir
    if existing.get("consent_data", {}).get("data_assinatura"):
        update_data["data_assinatura"] = existing["consent_data"]["data_assinatura"]

    # Manter a assinatura original se existir e não for fornecida nova
    if existing.get("consent_data", {}).get("assinatura") and not update_data.get("assinatura"):
        update_data["assinatura"] = existing["consent_data"]["assinatura"]

    await db[RGPD_REQUESTS_COLLECTION].update_one(
        {"id": request_id},
        {"$set": {"consent_data": update_data}}
    )

    logger.info("RGPD request updated by user")

    return {
        "success": True,
        "message": "RGPD atualizado com sucesso",
        "request_id": request_id
    }


@router.delete("/admin/{request_id}")
async def delete_rgpd(
    request_id: str,
    user: dict = Depends(require_staff())
):
    """
    Eliminar um RGPD.

    Permissões: Apenas staff.
    """
    result = await db[RGPD_REQUESTS_COLLECTION].delete_one({"id": request_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")

    logger.info("RGPD request deleted by user")

    return {
        "success": True,
        "message": "RGPD eliminado com sucesso"
    }


@router.post("/admin/{request_id}/resend")
async def resend_rgpd_email(
    request_id: str,
    user: dict = Depends(require_staff())
):
    """
    Reenviar email de RGPD para o cliente.

    Permissões: Apenas staff.
    Gera um novo token e reenvia o email.
    """
    import uuid
    from datetime import datetime, timezone, timedelta

    # Buscar o RGPD
    rgpd = await _get_rgpd_or_404(request_id)

    if rgpd["status"] == "signed":
        raise HTTPException(status_code=400, detail="Este RGPD já foi assinado")

    # Gerar novo token
    new_token = f"{uuid.uuid4().hex}{uuid.uuid4().hex}"
    new_expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

    # Atualizar
    await db[RGPD_REQUESTS_COLLECTION].update_one(
        {"id": request_id},
        {
            "$set": {
                "token": new_token,
                "token_expires_at": new_expires.isoformat(),
                "status": "pending"
            }
        }
    )

    # Enviar email
    email_sent = await send_rgpd_email(
        client_email=rgpd["client_email"],
        client_name=rgpd["client_name"],
        token=new_token,
        request_id=request_id,
        user_email=user["email"]
    )

    if not email_sent:
        raise HTTPException(status_code=500, detail="Erro ao enviar email")

    logger.info("RGPD email resent by user")

    return {
        "success": True,
        "message": "Email reenviado com sucesso",
        "expires_at": new_expires.isoformat()
    }


@router.get("/admin/stats/summary")
async def get_rgpd_stats(
    user: dict = Depends(require_staff())
):
    """
    Obter estatísticas de RGPD.

    Permissões: Apenas staff.
    """
    try:
        from datetime import datetime, timezone, timedelta

        # Contar por estado
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]

        status_counts = await db[RGPD_REQUESTS_COLLECTION].aggregate(pipeline).to_list(10)

        stats = {
            "pending": 0,
            "signed": 0,
            "expired": 0,
            "cancelled": 0,
            "total": 0
        }

        for item in status_counts:
            if item["_id"]:
                stats[item["_id"]] = item["count"]
                stats["total"] += item["count"]

        # Contar assinados hoje
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        signed_today = await db[RGPD_REQUESTS_COLLECTION].count_documents({
            "status": "signed",
            "signed_at": {"$gte": today.isoformat()}
        })

        stats["signed_today"] = signed_today

        return stats
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas RGPD: {e}")
        return {
            "pending": 0,
            "signed": 0,
            "expired": 0,
            "cancelled": 0,
            "total": 0,
            "signed_today": 0
        }
