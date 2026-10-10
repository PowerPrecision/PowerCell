"""
VALIDAÇÃO FINANCEIRA — rotas (`/api/financial-validation/*`)
============================================================
Stubs finos: a lógica vive em `services/financial_validation.py`.

Um AVISO e nunca um travão: validar/rejeitar muda o estado e, na rejeição,
devolve a lead ao parceiro — mas nenhuma rota do sistema recusa uma
operação por o processo estar «não validado».

O caminho usa `{item_id}` e não `{process_id}` de propósito: isto não é uma
escrita do processo no sentido do `process_closed_guard` (decidir sobre um
processo fechado é legítimo) e o inventário das rotas com `{process_id}`
não tem de a conhecer.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from services.auth import get_current_user
from services.financial_validation import run_decidir, run_url_do_comprovativo

router = APIRouter(prefix="/financial-validation", tags=["Validação Financeira"])


class DecisaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["validate", "reject"]
    #: Obrigatório na rejeição (é enviado ao parceiro).
    reason: Optional[str] = Field(None, max_length=600)


@router.post("/{kind}/{item_id}/decision")
async def decide_financial_validation(
    kind: str,
    item_id: str,
    data: DecisaoIn,
    request: Request,
    user: dict = Depends(get_current_user),
):
    return await run_decidir(kind, item_id, data.decision, data.reason, user, request=request)


@router.get("/{kind}/{item_id}/proof-url")
async def get_financial_validation_proof(
    kind: str,
    item_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    return await run_url_do_comprovativo(kind, item_id, user, request=request)
