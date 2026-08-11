"""
Rotas RGPD - Regulamento Geral sobre a Proteção de Dados — thin FastAPI stubs.

Logic in services/rgpd_*.py (do **not** collide with existing rgpd_service.py / gdpr.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from models.rgpd import (
    RGPDCreate, RGPDResponse, RGPDStatusResponse,
    RGPDConsentData, RGPDPublicView,
)
from services.auth import get_current_user, require_staff, require_management
# PACOTE DE — serviço de geração de PDF RGPD pré-preenchido
from services.rgpd_pdf import run_generate_prefilled_rgpd_pdf

from services.rgpd_helpers import (
    _add_process_activity,
    _get_rgpd_or_404,
)
from services.rgpd_templates import (
    RGPDTemplateUpdate,
    RGPD_DEFAULT_TEMPLATE,
    RGPD_TEMPLATE_VERSIONS_COLLECTION,
    _get_active_rgpd_template,
    run_get_rgpd_template,
    run_update_rgpd_template,
    run_list_rgpd_template_versions,
    run_get_rgpd_template_version,
)
from services.rgpd_minutas import (
    MinutaTemplateUpdate,
    MINUTA_DEFAULT_TEMPLATE,
    MINUTA_TEMPLATE_VERSIONS_COLLECTION,
    _get_active_minuta_template,
    run_get_minuta_template,
    run_update_minuta_template,
    run_list_minuta_template_versions,
    run_get_minuta_template_version,
)
from services.rgpd_request import run_request_rgpd, run_resend_rgpd_email
from services.rgpd_public import (
    run_validate_rgpd_token,
    run_sign_rgpd_form,
    run_get_rgpd_status,
    run_get_rgpd_form_data,
    run_list_rgpd_requests,
)
from services.rgpd_admin_list import (
    run_list_all_rgpd,
    run_get_rgpd_by_id,
    run_update_rgpd_data,
    run_delete_rgpd,
    run_get_rgpd_stats,
)

router = APIRouter(prefix="/rgpd", tags=["RGPD"])

# Re-exports for rgpd_service / tests that imported from routes.rgpd
__all__ = [
    "router",
    "_add_process_activity",
    "_get_rgpd_or_404",
    "_get_active_rgpd_template",
    "_get_active_minuta_template",
    "RGPD_DEFAULT_TEMPLATE",
    "MINUTA_DEFAULT_TEMPLATE",
    "RGPD_TEMPLATE_VERSIONS_COLLECTION",
    "MINUTA_TEMPLATE_VERSIONS_COLLECTION",
    "RGPDTemplateUpdate",
    "MinutaTemplateUpdate",
]


@router.post("/request", response_model=RGPDResponse)
async def request_rgpd(
    data: RGPDCreate,
    request: Request,
    user: dict = Depends(require_staff())
):
    return await run_request_rgpd(data, request, user)


@router.get("/validate/{token}", response_model=RGPDPublicView)
async def validate_rgpd_token(token: str):
    return await run_validate_rgpd_token(token)


@router.post("/sign/{token}")
async def sign_rgpd_form(
    token: str,
    consent_data: RGPDConsentData,
    request: Request,
):
    return await run_sign_rgpd_form(token, consent_data, request)


@router.get("/status/{process_id}", response_model=RGPDStatusResponse)
async def get_rgpd_status(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_get_rgpd_status(process_id, user)


@router.get("/data/{token}")
async def get_rgpd_form_data(token: str):
    return await run_get_rgpd_form_data(token)


@router.get("/list/{process_id}")
async def list_rgpd_requests(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_list_rgpd_requests(process_id, user)


# PACOTE DE — download de PDF RGPD PRÉ-PREENCHIDO (sem assinatura digital).
# Staff descarrega o PDF com os dados reais do cliente (Nome, NIF, Morada, etc.)
# para impressão + assinatura manual. Reusa `_get_rendered_rgpd_text` +
# `_generate_rgpd_pdf_bytes` de services/rgpd_service.py.
@router.get("/pdf/{process_id}")
async def download_prefilled_rgpd_pdf(
    process_id: str,
    user: dict = Depends(require_staff())
):
    import io
    pdf_bytes, filename = await run_generate_prefilled_rgpd_pdf(process_id, user)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============ ADMIN — static paths before /admin/{request_id} ============

@router.get("/admin/all")
async def list_all_rgpd(
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(require_staff())
):
    return await run_list_all_rgpd(
        user, status=status, search=search, page=page, limit=limit,
    )


@router.get("/admin/template")
async def get_rgpd_template(
    user: dict = Depends(require_management())
):
    return await run_get_rgpd_template(user)


@router.put("/admin/template")
async def update_rgpd_template(
    template_data: RGPDTemplateUpdate,
    user: dict = Depends(require_management())
):
    return await run_update_rgpd_template(template_data, user)


@router.get("/admin/template/versions")
async def list_rgpd_template_versions(
    user: dict = Depends(require_management())
):
    return await run_list_rgpd_template_versions(user)


@router.get("/admin/template/versions/{version_id}")
async def get_rgpd_template_version(
    version_id: str,
    user: dict = Depends(require_management())
):
    return await run_get_rgpd_template_version(version_id, user)


@router.get("/admin/minuta-template")
async def get_minuta_template(
    user: dict = Depends(require_management())
):
    return await run_get_minuta_template(user)


@router.put("/admin/minuta-template")
async def update_minuta_template(
    template_data: MinutaTemplateUpdate,
    user: dict = Depends(require_management())
):
    return await run_update_minuta_template(template_data, user)


@router.get("/admin/minuta-template/versions")
async def list_minuta_template_versions(
    user: dict = Depends(require_management())
):
    return await run_list_minuta_template_versions(user)


@router.get("/admin/minuta-template/versions/{version_id}")
async def get_minuta_template_version(
    version_id: str,
    user: dict = Depends(require_management())
):
    return await run_get_minuta_template_version(version_id, user)


@router.get("/admin/stats/summary")
async def get_rgpd_stats(
    user: dict = Depends(require_staff())
):
    return await run_get_rgpd_stats(user)


@router.get("/admin/{request_id}")
async def get_rgpd_by_id(
    request_id: str,
    user: dict = Depends(require_staff())
):
    return await run_get_rgpd_by_id(request_id, user)


@router.put("/admin/{request_id}")
async def update_rgpd_data(
    request_id: str,
    consent_data: RGPDConsentData,
    user: dict = Depends(require_staff())
):
    return await run_update_rgpd_data(request_id, consent_data, user)


@router.delete("/admin/{request_id}")
async def delete_rgpd(
    request_id: str,
    user: dict = Depends(require_staff())
):
    return await run_delete_rgpd(request_id, user)


@router.post("/admin/{request_id}/resend")
async def resend_rgpd_email(
    request_id: str,
    request: Request,
    user: dict = Depends(require_staff())
):
    return await run_resend_rgpd_email(request_id, request, user)
