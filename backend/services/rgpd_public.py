"""Public RGPD endpoints: validate, sign, status, form data, process list.

Extraído de `routes/rgpd.py`. Reuses `validate_token` / `sign_rgpd` /
`get_rgpd_by_process` / `get_tipo_documento_label` from existing
`services/rgpd_service.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.rgpd import (
    RGPDConsentData,
    RGPDPublicView,
    RGPDStatusEnum,
    RGPDStatusResponse,
)
from services.rgpd_service import (
    validate_token,
    get_rgpd_by_process,
    sign_rgpd,
    get_tipo_documento_label,
    RGPD_REQUESTS_COLLECTION,
)
from services.rgpd_helpers import _add_process_activity
from services.rgpd_templates import (
    RGPD_TEMPLATE_VERSIONS_COLLECTION,
    RGPD_DEFAULT_TEMPLATE,
    _get_active_rgpd_template,
)
from services.rgpd_minutas import (
    MINUTA_DEFAULT_TEMPLATE,
    _get_active_minuta_template,
)

logger = logging.getLogger(__name__)


async def run_validate_rgpd_token(token: str):
    """Validar token de RGPD e retornar dados para a página pública."""
    request = await validate_token(token)

    if not request:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")

    return RGPDPublicView(
        id=request["id"],
        client_name=request["client_name"],
        status=RGPDStatusEnum.PENDING,
        created_at=request["created_at"],
        expires_at=request["token_expires_at"],
        valid=True,
    )


async def run_sign_rgpd_form(token: str, consent_data: RGPDConsentData, request):
    """Assina digitalmente o consentimento RGPD usando um token temporário."""
    client_ip = request.client.host if request.client else "unknown"
    consent_data_dict = consent_data.model_dump()
    consent_data_dict["client_ip"] = client_ip

    result = await sign_rgpd(token, consent_data_dict)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao assinar RGPD"))

    request_id = result.get("request_id")
    process_id = result.get("process_id")
    if request_id:
        try:
            active_version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
                {"is_active": True},
                {"_id": 0},
            )
            if active_version:
                await db[RGPD_REQUESTS_COLLECTION].update_one(
                    {"id": request_id},
                    {"$set": {
                        "rgpd_template_version_id": active_version["id"],
                        "rgpd_template_version": active_version["version"],
                    }},
                )
                logger.info(
                    f"Versão do template RGPD v{active_version['version']} "
                    f"registada no pedido {request_id}"
                )
            else:
                config_doc = await db.system_config.find_one(
                    {"_id": "rgpd_template"},
                    {"_id": 0, "active_version_id": 1, "active_version": 1},
                )
                if config_doc and config_doc.get("active_version_id"):
                    await db[RGPD_REQUESTS_COLLECTION].update_one(
                        {"id": request_id},
                        {"$set": {
                            "rgpd_template_version_id": config_doc["active_version_id"],
                            "rgpd_template_version": config_doc.get("active_version", 1),
                        }},
                    )
        except Exception as e:
            logger.warning(f"Não foi possível registar versão do template RGPD: {e}")

    if process_id:
        await _add_process_activity(
            process_id=process_id,
            user_id="client",
            user_name=consent_data.nome or "Cliente",
            action="RGPD assinado pelo cliente",
            details=f"Documento RGPD assinado digitalmente. NIF: {consent_data.contribuinte or 'N/A'}.",
        )

    return {
        "success": True,
        "message": "RGPD assinado com sucesso",
        "process_id": result["process_id"],
    }


async def run_get_rgpd_status(process_id: str, user: dict):
    """Verificar estado do RGPD para um processo."""
    try:
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
            request_id=result.get("request_id"),
        )
    except Exception as e:
        logger.error(
            f"Erro ao verificar estado RGPD para processo {process_id}: {e}",
            exc_info=True,
        )
        return RGPDStatusResponse(has_rgpd=False)


async def run_get_rgpd_form_data(token: str):
    """Dados para pré-preencher o formulário RGPD + templates renderizados."""
    request = await validate_token(token)

    if not request:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")

    process = await db.processes.find_one({"id": request["process_id"]})

    if process:
        from services.process_service import decrypt_sensitive_data
        process = decrypt_sensitive_data(process)

    personal_data = process.get("personal_data", {}) if process else {}
    real_estate_data = process.get("real_estate_data", {}) if process else {}

    documento_id = personal_data.get("documento_id", "")
    if isinstance(documento_id, dict):
        tipo_documento = documento_id.get("type", "")
        numero_documento = documento_id.get("number", "")
    else:
        tipo_documento = ""
        numero_documento = str(documento_id) if documento_id else ""

    response_data = {
        "client_name": request["client_name"],
        "client_email": request["client_email"],
        "nif": personal_data.get("nif", ""),
        "morada": personal_data.get("morada_fiscal", ""),
        "localidade": real_estate_data.get("concelho", personal_data.get("naturalidade", "")),
        "numero_documento": numero_documento,
        "tipo_documento": tipo_documento,
        "validade_documento": personal_data.get("data_validade_cc", ""),
        "concelho": real_estate_data.get("concelho", ""),
        "codigo_postal": real_estate_data.get("codigo_postal", ""),
    }

    def _render(template: str) -> str:
        if not template:
            return ""
        rendered = template
        rendered = rendered.replace("{{NOME_CLIENTE}}", str(request.get("client_name") or ""))
        rendered = rendered.replace("{{NOME}}", str(request.get("client_name") or ""))
        rendered = rendered.replace("{{NOME_EMPRESA}}", str(empresa_nome or ""))
        rendered = rendered.replace("{{CONTRIBUINTE}}", str(response_data.get("nif") or ""))
        rendered = rendered.replace("{{MORADA}}", str(response_data.get("morada") or ""))
        rendered = rendered.replace("{{LOCALIDADE}}", str(response_data.get("localidade") or ""))
        rendered = rendered.replace("{{CODIGO_POSTAL}}", str(response_data.get("codigo_postal") or ""))
        rendered = rendered.replace("{{TIPO_DOCUMENTO}}", str(get_tipo_documento_label(tipo_documento)))
        rendered = rendered.replace("{{NUMERO_DOCUMENTO}}", str(numero_documento or ""))
        rendered = rendered.replace("{{VALIDADE_DOCUMENTO}}", str(response_data.get("validade_documento") or ""))
        rendered = rendered.replace("{{DATA_ASSINATURA}}", str(data_assinatura or ""))
        rendered = rendered.replace("{{MORADA_EMPRESA}}", str(empresa_morada or ""))
        rendered = rendered.replace("{{CONTACTO_EMPRESA}}", str(empresa_contacto or ""))
        return rendered

    empresa_nome = "Power Real Estate, Lda."
    empresa_morada = ""
    empresa_contacto = ""
    try:
        config = await db.system_config.find_one(
            {"_id": "main"},
            {
                "_id": 0,
                "settings.empresa_nome": 1,
                "settings.company_address": 1,
                "settings.company_phone": 1,
                "settings.company_name": 1,
            },
        )
        if config:
            settings = config.get("settings", {})
            if settings.get("empresa_nome"):
                empresa_nome = settings["empresa_nome"]
            if settings.get("company_name"):
                empresa_nome = settings["company_name"]
            if settings.get("company_address"):
                empresa_morada = settings["company_address"]
            if settings.get("company_phone"):
                empresa_contacto = settings["company_phone"]
    except Exception:
        pass

    data_assinatura = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    try:
        template_text = await _get_active_rgpd_template()
        if template_text:
            response_data["rgpd_text"] = _render(template_text)
        else:
            logger.warning("[RGPD] Template RGPD vazio — a usar default")
            response_data["rgpd_text"] = _render(RGPD_DEFAULT_TEMPLATE)
    except Exception as e:
        logger.error(f"[RGPD] Erro ao renderizar template RGPD: {e}", exc_info=True)
        response_data["rgpd_text"] = _render(RGPD_DEFAULT_TEMPLATE)

    try:
        minuta_text = await _get_active_minuta_template()
        if minuta_text:
            response_data["minuta_text"] = _render(minuta_text)
        else:
            logger.warning("[RGPD] Template Minuta vazio — a usar default")
            response_data["minuta_text"] = _render(MINUTA_DEFAULT_TEMPLATE)
    except Exception as e:
        logger.error(f"[RGPD] Erro ao renderizar template Minuta: {e}", exc_info=True)
        response_data["minuta_text"] = _render(MINUTA_DEFAULT_TEMPLATE)

    return response_data


async def run_list_rgpd_requests(process_id: str, user: dict):
    """Listar todos os pedidos de RGPD para um processo."""
    requests = await db.rgpd_requests.find(
        {"process_id": process_id},
        {"_id": 0, "token": 0},
    ).sort("created_at", -1).to_list(20)

    return {
        "requests": requests,
        "total": len(requests),
    }
