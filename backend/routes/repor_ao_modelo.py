"""«Repor ao Modelo» (workflow e formulário de uma rede) — thin FastAPI stubs.

Lógica em `services/repor_ao_modelo.py`; a password é validada no servidor
(`services/reauth_password.py`). Router próprio porque `routes/admin.py` está no tecto de linhas
dos stubs finos.
"""
from fastapi import APIRouter, Depends, Request, Response

from middleware.rate_limit import limiter
from services.admin_workflow import PAPEIS_QUE_EDITAM_O_WORKFLOW
from services.auth import require_roles
from services.repor_ao_modelo import (
    ReporAoModeloIn,
    run_repor_formulario_ao_modelo,
    run_repor_workflow_ao_modelo,
)

router = APIRouter(prefix="/admin", tags=["repor-ao-modelo"])


@router.post("/workflow-statuses/reset-to-model")
@limiter.limit("10/minute")
async def reset_workflow_to_model(request: Request, response: Response, data: ReporAoModeloIn, user: dict = Depends(require_roles(PAPEIS_QUE_EDITAM_O_WORKFLOW))):
    """Descarta o workflow próprio da rede em contexto. Exige a password actual."""
    return await run_repor_workflow_ao_modelo(data, user, request)


@router.post("/form-config/reset-to-model")
@limiter.limit("10/minute")
async def reset_form_config_to_model(request: Request, response: Response, data: ReporAoModeloIn, user: dict = Depends(require_roles(PAPEIS_QUE_EDITAM_O_WORKFLOW))):
    """Descarta o formulário próprio da rede em contexto. Exige a password actual."""
    return await run_repor_formulario_ao_modelo(data, user, request)
