"""Alterar a empresa de um cliente (só Master) — Lote 2, Out 2026.

Router próprio: `routes/clients.py` é só stubs finos e tem tecto de linhas. Mantém o prefixo
`/clients` e a MESMA dependência de rede (`exigir_cliente_no_ambito`) do router de clientes.
"""
from fastapi import APIRouter, Depends, Query

from models.auth import UserRole
from services.auth import require_roles
from services.by_id_scope import exigir_cliente_no_ambito
from services.client_company_transfer import (
    TransferirClienteIn,
    run_preview_transfer_client_company,
    run_transfer_client_company,
)

router = APIRouter(
    prefix="/clients", tags=["Clients"],
    dependencies=[Depends(exigir_cliente_no_ambito)],
)


@router.post("/{client_id}/transfer-company")
async def transfer_client_company(
    client_id: str,
    data: TransferirClienteIn,
    user: dict = Depends(require_roles([UserRole.MASTER])),
):
    """Mover o cliente (e os processos de que é titular) para outra empresa. Só Master, com password.

    Muda o carimbo; **não** move nada no S3.
    """
    return await run_transfer_client_company(client_id, data, user)


@router.get("/{client_id}/transfer-company/preview")
async def preview_transfer_client_company(
    client_id: str,
    company_id: str = Query(..., min_length=1, description="Empresa de destino"),
    user: dict = Depends(require_roles([UserRole.MASTER])),
):
    """O que a transferência faria (processos a mover, mantidos e impeditivos). Só lê."""
    return await run_preview_transfer_client_company(client_id, company_id, user)
