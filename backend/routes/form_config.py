"""
Rotas para configuração dinâmica do formulário público — thin FastAPI stubs.

Logic in services/form_config_*.py.
"""
from fastapi import APIRouter, Depends

from services.auth import require_roles, require_management
from models.auth import UserRole

# Re-export defaults for callers (e.g. routes.public)
from services.form_config_defaults import (  # noqa: F401
    DEFAULT_FORM_CONFIG,
    DEFAULT_STEP_CONFIG,
)
from services.form_config_fields import (
    FormConfigUpdate,
    CustomFieldCreate,
    run_get_form_config,
    run_update_form_config,
    run_create_custom_field,
    run_delete_custom_field,
    run_reset_form_config,
)
from services.form_config_templates import (
    TemplateSave,
    run_list_templates,
    run_preview_template,
    run_save_as_template,
    run_activate_template,
    run_duplicate_template,
    run_delete_template,
)

router = APIRouter(prefix="/admin/form-config", tags=["form-config"])


@router.get("/fields")
async def get_form_config(user: dict = Depends(require_management())):
    """Obter configuração atual do formulário."""
    return await run_get_form_config(user)


@router.put("/fields")
async def update_form_config(
    data: FormConfigUpdate,
    user: dict = Depends(require_management())
):
    """Actualizar configuração do formulário."""
    return await run_update_form_config(data, user)


@router.post("/custom-field")
async def create_custom_field(
    data: CustomFieldCreate,
    user: dict = Depends(require_management())
):
    """Criar um campo personalizado no formulário."""
    return await run_create_custom_field(data, user)


@router.delete("/custom-field/{field_key}")
async def delete_custom_field(
    field_key: str,
    user: dict = Depends(require_management())
):
    """Eliminar campo personalizado do formulário."""
    return await run_delete_custom_field(field_key, user)


@router.post("/reset")
async def reset_form_config(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Repor configuração padrão do formulário (remove campos personalizados)."""
    return await run_reset_form_config(user)


@router.get("/templates")
async def list_templates(user: dict = Depends(require_management())):
    """Listar todos os templates de formulário (sistema + personalizados)."""
    return await run_list_templates(user)


@router.get("/templates/{template_id}/preview")
async def preview_template(
    template_id: str,
    user: dict = Depends(require_management())
):
    """Obter campos de um template para pré-visualização (sem ativar)."""
    return await run_preview_template(template_id, user)


@router.post("/templates")
async def save_as_template(
    data: TemplateSave,
    user: dict = Depends(require_management())
):
    """Guardar a configuração atual como template."""
    return await run_save_as_template(data, user)


@router.post("/templates/{template_id}/activate")
async def activate_template(
    template_id: str,
    user: dict = Depends(require_management())
):
    """Ativar um template, substituindo a configuração atual do formulário."""
    return await run_activate_template(template_id, user)


@router.post("/templates/{template_id}/duplicate")
async def duplicate_template(
    template_id: str,
    user: dict = Depends(require_management())
):
    """Duplicar um template (sistema ou personalizado) como template personalizado."""
    return await run_duplicate_template(template_id, user)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Eliminar template personalizado."""
    return await run_delete_template(template_id, user)
