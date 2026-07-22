"""
====================================================================
ROTAS DE TEMPLATES E MINUTAS — thin FastAPI stubs
====================================================================
Logic in services/templates_api_*.py.
Do **not** overwrite services/template_generator.py.
====================================================================
"""
from fastapi import APIRouter, Depends

from services.auth import get_current_user, require_roles
from services.templates_api_helpers import (
    TEMPLATES_ALLOWED_ROLES,
    DocumentRequestData,
)
from services.templates_api_named import (
    run_download_named_template,
    run_get_document_request_template,
    run_get_named_template,
    run_get_webmail_urls,
)
from services.templates_api_checklist import (
    run_get_document_checklist,
    run_get_document_types,
)
from services.templates_api_generic import (
    run_download_template_generic,
    run_generate_template_generic,
    run_get_available_templates,
    run_validate_template_fields,
)

router = APIRouter(
    prefix="/templates",
    tags=["Templates"],
    dependencies=[Depends(require_roles(TEMPLATES_ALLOWED_ROLES))],
)


@router.get("/webmail-urls")
async def get_webmail_urls(user: dict = Depends(get_current_user)):
    """Retorna as URLs dos webmails disponíveis."""
    return await run_get_webmail_urls(user)


@router.get("/process/{process_id}/cpcv")
async def get_cpcv_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Gera o template de CPCV preenchido."""
    return await run_get_named_template(process_id, "cpcv", user)


@router.get("/process/{process_id}/cpcv/download")
async def download_cpcv_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Download do template de CPCV como ficheiro de texto."""
    return await run_download_named_template(process_id, "cpcv", "CPCV", user)


@router.get("/process/{process_id}/valuation-appeal")
async def get_valuation_appeal_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Gera o template de apelação de avaliação bancária."""
    return await run_get_named_template(process_id, "valuation_appeal", user)


@router.get("/process/{process_id}/valuation-appeal/download")
async def download_valuation_appeal_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Download do template de apelação de avaliação."""
    return await run_download_named_template(
        process_id, "valuation_appeal", "Apelacao_Avaliacao", user,
    )


@router.post("/process/{process_id}/document-request")
async def get_document_request_template(
    process_id: str,
    data: DocumentRequestData,
    user: dict = Depends(get_current_user),
):
    """Gera o template de pedido de documentos ao cliente."""
    return await run_get_document_request_template(process_id, data, user)


@router.get("/process/{process_id}/deed-reminder")
async def get_deed_reminder_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Gera o template de lembrete de escritura."""
    return await run_get_named_template(process_id, "deed_reminder", user)


@router.get("/process/{process_id}/deed-reminder/download")
async def download_deed_reminder_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Download do template de lembrete de escritura."""
    return await run_download_named_template(
        process_id, "deed_reminder", "Lembrete_Escritura", user,
    )


@router.get("/process/{process_id}/document-checklist")
async def get_document_checklist(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Retorna a checklist dinâmica de documentos para um processo."""
    return await run_get_document_checklist(process_id, user)


@router.get("/document-types")
async def get_document_types(user: dict = Depends(get_current_user)):
    """Retorna a lista de tipos de documentos disponíveis."""
    return await run_get_document_types(user)


@router.get("/available")
async def get_available_templates(user: dict = Depends(get_current_user)):
    """Lista todos os tipos de templates disponíveis para geração."""
    return await run_get_available_templates(user)


@router.get("/process/{process_id}/generate/{template_type}")
async def generate_template_generic(
    process_id: str,
    template_type: str,
    user: dict = Depends(get_current_user),
):
    """Endpoint genérico para gerar qualquer tipo de template."""
    return await run_generate_template_generic(process_id, template_type, user)


@router.get("/process/{process_id}/generate/{template_type}/download")
async def download_template_generic(
    process_id: str,
    template_type: str,
    user: dict = Depends(get_current_user),
):
    """Download genérico de template como ficheiro de texto."""
    return await run_download_template_generic(process_id, template_type, user)


@router.get("/process/{process_id}/validate/{template_type}")
async def validate_template_fields(
    process_id: str,
    template_type: str,
    user: dict = Depends(get_current_user),
):
    """Valida campos necessários antes de gerar um template."""
    return await run_validate_template_fields(process_id, template_type, user)


@router.get("/process/{process_id}/contrato-mediacao")
async def get_contrato_mediacao_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Gera o template de Contrato de Mediação Imobiliária."""
    return await run_get_named_template(process_id, "contrato_mediacao", user)


@router.get("/process/{process_id}/ficha-visita")
async def get_ficha_visita_template(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Gera o template de Ficha de Visita ao Imóvel."""
    return await run_get_named_template(process_id, "ficha_visita", user)
