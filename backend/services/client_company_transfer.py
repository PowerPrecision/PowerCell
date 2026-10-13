"""
====================================================================
ALTERAR A EMPRESA DE UM CLIENTE (só Master) — Lote 2, Out 2026
====================================================================
Um cliente registado na empresa errada não tinha como ser movido: o carimbo de
empresa/rede é permanente por desenho (é a fronteira de dados). Esta acção é a
válvula, e é por isso estreita.

O QUE FAZ
  * muda o carimbo (`company_id`, `company_name`, `network_id`) do CLIENTE e dos
    PROCESSOS de que ele é o titular principal;
  * leva atrás o que lista por esse carimbo e diz respeito a esses processos —
    tarefas, prazos e visitas. Sem isto o nome do cliente ficaria no calendário e
    nas tarefas da empresa antiga (a mensagem de uma tarefa leva o nome do
    cliente), ou desapareceria das da nova;
  * a empresa de destino deixa de ser «convidada» dos processos que passa a ter
    como dona (a dona nunca está na lista de convidadas).

O QUE NUNCA FAZ
  * **não mexe no S3.** O `s3_folder` gravado fica tal e qual: o ficheiro não muda
    de sítio, só muda quem o vê. Mover objectos foi o que produziu as 205 ligações
    partidas do Épico 10 — e a posse de um ficheiro deriva do processo/cliente,
    que é o que aqui se carimba;
  * não toca nos processos em que o cliente é só 2.º titular: esses são de outro
    titular (e de outra ficha) e movê-los arrastava o cliente errado;
  * não apaga a ficha de ninguém nem as partilhas B2B a outras redes (o dono é que
    muda; quem já via o processo continua a ver).

REGRAS
  * só a CONTA Master (a rota exige-o) e com a password ACTUAL confirmada, como as
    outras acções que mexem na fronteira (`reauth_password`) — ANTES de qualquer
    escrita;
  * a empresa de destino tem de existir; um destino que não dá carimbo completo
    (empresa + rede) é recusado: meio carimbo é pior do que nenhum;
  * o mesmo destino é uma resposta e não um erro (idempotente, nada se escreve);
  * deixa rasto no trilho de auditoria (de onde, para onde, quantos processos) e
    no histórico de cada processo (honra o interruptor).
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.admin_helpers import _audit_log
from services.reauth_password import exigir_password_actual
from services.tenant_network import CAMPO_REDE, PROJECCAO_DO_CARIMBO, resolve_tenant_stamp

logger = logging.getLogger(__name__)

ERRO_CLIENTE_NAO_ENCONTRADO = "Cliente não encontrado"
ERRO_EMPRESA_NAO_ENCONTRADA = "Empresa de destino não encontrada"
ERRO_EMPRESA_SEM_CARIMBO = (
    "Não foi possível determinar a rede da empresa de destino. "
    "Verifique a configuração da empresa antes de transferir."
)
ERRO_EMPRESA_EM_FALTA = "Indique a empresa de destino."

#: Colecções que listam por carimbo e dizem respeito a um processo (`process_id`).
COLECCOES_QUE_ACOMPANHAM_O_PROCESSO: tuple[str, ...] = ("tasks", "deadlines", "visits")


class TransferirClienteIn(BaseModel):
    """O corpo do pedido. `extra=forbid`: o carimbo vem do SERVIDOR, nunca do corpo."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = Field(min_length=1)
    #: A password ACTUAL de quem pede. Nunca vai para log nem para o rasto.
    password: Optional[str] = Field(default=None, repr=False)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _carimbo_com_empresa_legada(carimbo: dict, documento: dict) -> dict:
    """O `$set` do carimbo; o campo legado `company` (o NOME) acompanha se o documento o tem."""
    atribuir = dict(carimbo)
    if "company" in documento:
        atribuir["company"] = carimbo["company_name"]
    return atribuir


async def _processos_do_titular(cliente: dict) -> list[dict]:
    """Os processos de que o cliente é o titular PRINCIPAL."""
    client_id = cliente["id"]
    ids_da_ficha = [i for i in (cliente.get("process_ids") or []) if i]
    filtro: dict = {"client_id": client_id}
    if ids_da_ficha:
        # Um processo na lista da ficha mas sem titular gravado ainda é dele; um que aponta
        # para OUTRO titular não é.
        filtro = {"$or": [
            {"client_id": client_id},
            {"id": {"$in": ids_da_ficha}, "client_id": {"$in": [None, ""]}},
        ]}
    return await db.processes.find(
        filtro, {"_id": 0, "id": 1, "company": 1, **PROJECCAO_DO_CARIMBO},
    ).to_list(2000)


async def run_transfer_client_company(client_id: str, data: TransferirClienteIn, actor: dict) -> dict:
    """Transfere o cliente (e os processos dele) para outra empresa. Só Master."""
    cliente = await db.clients.find_one(
        {"id": client_id}, {"_id": 0, "id": 1, "process_ids": 1, "company": 1, **PROJECCAO_DO_CARIMBO},
    )
    if not cliente:
        raise HTTPException(status_code=404, detail=ERRO_CLIENTE_NAO_ENCONTRADO)

    destino_id = _texto(data.company_id)
    if not destino_id:
        raise HTTPException(status_code=400, detail=ERRO_EMPRESA_EM_FALTA)
    empresa = await db.companies.find_one(
        {"id": destino_id}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
    )
    if not empresa:
        raise HTTPException(status_code=404, detail=ERRO_EMPRESA_NAO_ENCONTRADA)

    carimbo = await resolve_tenant_stamp(actor, active_company_id=empresa["id"])
    if not carimbo or not all(carimbo.get(k) for k in ("company_id", "company_name", CAMPO_REDE)):
        raise HTTPException(status_code=400, detail=ERRO_EMPRESA_SEM_CARIMBO)

    origem = {k: cliente.get(k) for k in ("company_id", "company_name", CAMPO_REDE)}
    if (
        _texto(cliente.get("company_id")) == carimbo["company_id"]
        and _texto(cliente.get(CAMPO_REDE)) == carimbo[CAMPO_REDE]
    ):
        return {
            "transferido": False,
            "motivo": "O cliente já pertence a esta empresa.",
            "empresa": carimbo,
            "processos_transferidos": 0,
        }

    # A password vem ANTES de qualquer escrita (e do estado: não se diz o que há para mover).
    await exigir_password_actual(actor, data.password)

    processos = await _processos_do_titular(cliente)
    ids_processos = [p["id"] for p in processos if p.get("id")]

    await db.clients.update_one(
        {"id": client_id}, {"$set": _carimbo_com_empresa_legada(carimbo, cliente)},
    )

    for processo in processos:
        await db.processes.update_one(
            {"id": processo["id"]}, {"$set": _carimbo_com_empresa_legada(carimbo, processo)},
        )
    if ids_processos:
        # A dona nunca é «convidada» do que é seu: se o destino já via o processo por uma
        # partilha, a partilha deixa de fazer sentido.
        await db.processes.update_many(
            {"id": {"$in": ids_processos}},
            {"$pull": {
                "partner_network_ids": carimbo[CAMPO_REDE],
                "partner_companies": {CAMPO_REDE: carimbo[CAMPO_REDE]},
            }},
        )
        for colecao in COLECCOES_QUE_ACOMPANHAM_O_PROCESSO:
            await getattr(db, colecao).update_many(
                {"process_id": {"$in": ids_processos}}, {"$set": carimbo},
            )

    await _audit_log(
        "client_company_transferred", "client", client_id, actor,
        details={
            "de": origem,
            "para": carimbo,
            "processos": ids_processos,
            "s3_folder": "inalterado",
        },
    )
    await _historico_dos_processos(ids_processos, actor, origem, carimbo)

    logger.info(
        "[CLIENTE-EMPRESA] %s transferiu o cliente %s de %s para %s (%d processo(s)).",
        (actor or {}).get("id"), client_id, origem.get("company_name"),
        carimbo["company_name"], len(ids_processos),
    )
    return {
        "transferido": True,
        "empresa": carimbo,
        "processos_transferidos": len(ids_processos),
        "s3_folder": "inalterado",
    }


async def _historico_dos_processos(ids: list[str], actor: dict, origem: dict, destino: dict) -> None:
    """Uma linha no histórico de cada processo. Nunca levanta (o rasto não desfaz a acção)."""
    from services.history import log_history

    de = origem.get("company_name") or "—"
    for process_id in ids:
        try:
            await log_history(
                process_id, actor, "Cliente transferido para outra empresa",
                "company_name", de, destino["company_name"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CLIENTE-EMPRESA] Histórico de %s falhou: %s", process_id, exc)


__all__ = ["TransferirClienteIn", "run_transfer_client_company"]
