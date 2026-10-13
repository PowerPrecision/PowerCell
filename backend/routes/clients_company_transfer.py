"""Alterar a empresa de um cliente (só Master) — Lote 2, Out 2026.

Router próprio: `routes/clients.py` é só stubs finos e tem tecto de linhas. Mantém o prefixo
`/clients` e a MESMA dependência de rede (`exigir_cliente_no_ambito`) do router de clientes.
"""
from fastapi import APIRouter, Depends

from models.auth import UserRole
from services.auth import require_roles
from services.by_id_scope import exigir_cliente_no_ambito
from services.client_company_transfer import TransferirClienteIn, run_transfer_client_company

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
