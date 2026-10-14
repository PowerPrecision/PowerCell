"""
====================================================================
ALTERAR A EMPRESA DE UM OU MAIS PROCESSOS DE UM CLIENTE (só Master) — Lote 6, Out 2026
====================================================================
(Reescrito no Lote 6. Até aí a acção movia o CLIENTE inteiro — Lote 2 —, e a regra de negócio
é outra: **um cliente pode pertencer a várias empresas; o que transita de uma rede para a
outra, quando a triagem se enganou, é o PROCESSO.**)

O QUE FAZ
  * recebe a lista EXPLÍCITA de processos a mover (`process_ids`, pelo menos um) e a empresa de
    destino, e muda o carimbo (`company_id`, `company_name`, `network_id`) desses processos;
  * leva atrás o que lista por esse carimbo e diz respeito a eles — tarefas, prazos e visitas.
    Sem isto o nome do cliente ficava no calendário e nas tarefas da empresa antiga (a mensagem
    de uma tarefa leva o nome do cliente), ou desaparecia das da nova;
  * a empresa de destino deixa de ser «convidada» dos processos que passa a ter como dona (a
    dona nunca está na lista de convidadas).

O QUE NUNCA FAZ
  * **não toca na ficha do cliente.** Ela fica onde está, com o carimbo que tinha: o cliente
    continua a ser da empresa de origem e passa a ter processos noutra. Quem recebe o processo
    vê-o inteiro e vê a ficha pela JANELA (`client_window`: só os processos da sua rede, nunca
    os outros nem o acesso do cliente ao Portal). A identidade do cliente continua a ser POR
    REDE (D-38) — o mesmo NIF numa segunda empresa é uma segunda ficha, que a empresa de destino
    cria quando quiser; nada se funde nem se duplica aqui;
  * **não mexe no S3.** O `s3_folder` gravado fica tal e qual: o ficheiro não muda de sítio,
    só muda quem o vê. Mover objectos foi o que produziu as 205 ligações partidas do Épico 10;
  * não apaga as partilhas B2B a outras redes (o dono é que muda; quem já via o processo
    continua a ver).

REGRAS
  * só a CONTA Master (a rota exige-o) e com a password ACTUAL confirmada, como as outras
    acções que mexem na fronteira (`reauth_password`) — ANTES de qualquer escrita;
  * os processos pedidos têm de ser do cliente (titular principal) e não estar eliminados; um
    id que não é dele recusa o pedido INTEIRO (400): mover «o que sobrar» seria adivinhar;
  * a empresa de destino tem de existir; um destino que não dá carimbo completo (empresa +
    rede) é recusado: meio carimbo é pior do que nenhum;
  * um processo que já pertence à empresa de destino é uma resposta e não um erro
    (idempotente: nada se escreve, e a resposta di-lo);
  * deixa rasto no trilho de auditoria (de onde, para onde, quais) e no histórico de cada
    processo movido (honra o interruptor).
  * o preview (`GET …/transfer-company/preview`) lista os processos movíveis e, com destino,
    quais já lá estão — sem escrever nada, para o ecrã deixar escolher ANTES da password.
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
ERRO_SEM_PROCESSOS = "Escolha pelo menos um processo a transferir."
ERRO_PROCESSOS_QUE_NAO_SAO_DO_CLIENTE = (
    "Há processos escolhidos que não pertencem a este cliente. Nada foi transferido."
)

#: Colecções que listam por carimbo e dizem respeito a um processo (`process_id`).
COLECCOES_QUE_ACOMPANHAM_O_PROCESSO: tuple[str, ...] = ("tasks", "deadlines", "visits")


class TransferirClienteIn(BaseModel):
    """O corpo do pedido. `extra=forbid`: o carimbo vem do SERVIDOR, nunca do corpo."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = Field(min_length=1)
    #: Os processos a mover. Obrigatório e explícito: «o cliente todo» já não é uma opção.
    process_ids: list[str] = Field(min_length=1)
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
        filtro,
        {"_id": 0, "id": 1, "company": 1, "status": 1, "is_deleted": 1, "process_number": 1,
         "partner_network_ids": 1, **PROJECCAO_DO_CARIMBO},
    ).to_list(2000)


def _ja_pertence(processo: dict, carimbo: dict) -> bool:
    return (
        _texto(processo.get("company_id")) == carimbo["company_id"]
        and _texto(processo.get(CAMPO_REDE)) == carimbo[CAMPO_REDE]
    )


async def _terminados(processos: list[dict]) -> set[str]:
    """Os ids dos processos em fase TERMINAL no workflow da rede DONA (informativo)."""
    from services.workflow_phases import fases_dos_processos, nomes_terminais

    if not processos:
        return set()
    por_rede, rede_de = await fases_dos_processos(processos)
    terminais = {rede: set(nomes_terminais(fases)) for rede, fases in por_rede.items()}
    return {
        str(p.get("id")) for p in processos
        if p.get("status") in terminais.get(rede_de.get(str(p.get("id")), ""), set())
    }


def _resumo(processo: dict, *, terminado: bool = False, ja_no_destino: bool = False) -> dict:
    """O mínimo que o ecrã precisa para dizer de que processo se fala (nunca o documento)."""
    return {
        "id": processo.get("id"),
        "process_number": processo.get("process_number"),
        "status": processo.get("status"),
        "company_name": processo.get("company_name") or processo.get("company"),
        "terminado": terminado,
        "ja_no_destino": ja_no_destino,
    }


async def _carregar_cliente(client_id: str) -> dict:
    cliente = await db.clients.find_one(
        {"id": client_id}, {"_id": 0, "id": 1, "process_ids": 1, "company": 1, **PROJECCAO_DO_CARIMBO},
    )
    if not cliente:
        raise HTTPException(status_code=404, detail=ERRO_CLIENTE_NAO_ENCONTRADO)
    return cliente


async def run_preview_transfer_client_company(
    client_id: str, company_id: Optional[str], actor: dict,
) -> dict:
    """Os processos que se podem mover — e, com destino, quais já lá estão. Só lê, sem password."""
    cliente = await _carregar_cliente(client_id)
    carimbo = None
    destino = _texto(company_id)
    if destino:
        empresa = await db.companies.find_one({"id": destino}, {"_id": 0, "id": 1})
        if not empresa:
            raise HTTPException(status_code=404, detail=ERRO_EMPRESA_NAO_ENCONTRADA)
        carimbo = await resolve_tenant_stamp(actor, active_company_id=empresa["id"])

    processos = [p for p in await _processos_do_titular(cliente) if not p.get("is_deleted")]
    terminados = await _terminados(processos)
    return {
        "company_id": destino or None,
        "processos": [
            _resumo(
                p,
                terminado=str(p.get("id")) in terminados,
                ja_no_destino=bool(carimbo and carimbo.get("company_id") and _ja_pertence(p, carimbo)),
            )
            for p in processos
        ],
    }


async def run_transfer_client_company(client_id: str, data: TransferirClienteIn, actor: dict) -> dict:
    """Move os processos escolhidos de um cliente para outra empresa. Só Master."""
    cliente = await _carregar_cliente(client_id)

    destino_id = _texto(data.company_id)
    if not destino_id:
        raise HTTPException(status_code=400, detail=ERRO_EMPRESA_EM_FALTA)
    pedidos = list(dict.fromkeys(_texto(i) for i in data.process_ids if _texto(i)))
    if not pedidos:
        raise HTTPException(status_code=400, detail=ERRO_SEM_PROCESSOS)

    empresa = await db.companies.find_one(
        {"id": destino_id}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
    )
    if not empresa:
        raise HTTPException(status_code=404, detail=ERRO_EMPRESA_NAO_ENCONTRADA)

    carimbo = await resolve_tenant_stamp(actor, active_company_id=empresa["id"])
    if not carimbo or not all(carimbo.get(k) for k in ("company_id", "company_name", CAMPO_REDE)):
        raise HTTPException(status_code=400, detail=ERRO_EMPRESA_SEM_CARIMBO)

    # A password vem ANTES de qualquer escrita (e do estado: não se diz o que há para mover).
    await exigir_password_actual(actor, data.password)

    do_cliente = {str(p["id"]): p for p in await _processos_do_titular(cliente) if p.get("id")}
    # Um id que não é deste cliente (ou está eliminado) recusa o pedido INTEIRO.
    if any(i not in do_cliente or do_cliente[i].get("is_deleted") for i in pedidos):
        raise HTTPException(status_code=400, detail=ERRO_PROCESSOS_QUE_NAO_SAO_DO_CLIENTE)

    escolhidos = [do_cliente[i] for i in pedidos]
    a_mover = [p for p in escolhidos if not _ja_pertence(p, carimbo)]
    ja_la = [p for p in escolhidos if _ja_pertence(p, carimbo)]
    if not a_mover:
        return {
            "transferido": False,
            "motivo": "Os processos escolhidos já pertencem a esta empresa.",
            "empresa": carimbo,
            "processos_transferidos": 0,
            "processos_ja_no_destino": [_resumo(p, ja_no_destino=True) for p in ja_la],
        }

    ids_a_mover = [p["id"] for p in a_mover]
    for processo in a_mover:
        await db.processes.update_one(
            {"id": processo["id"]}, {"$set": _carimbo_com_empresa_legada(carimbo, processo)},
        )
    # A dona nunca é «convidada» do que é seu: se o destino já via o processo por uma partilha,
    # a partilha deixa de fazer sentido.
    await db.processes.update_many(
        {"id": {"$in": ids_a_mover}},
        {"$pull": {
            "partner_network_ids": carimbo[CAMPO_REDE],
            "partner_companies": {CAMPO_REDE: carimbo[CAMPO_REDE]},
        }},
    )
    for colecao in COLECCOES_QUE_ACOMPANHAM_O_PROCESSO:
        await getattr(db, colecao).update_many(
            {"process_id": {"$in": ids_a_mover}}, {"$set": carimbo},
        )

    origens = {
        p["id"]: {k: p.get(k) for k in ("company_id", "company_name", CAMPO_REDE)} for p in a_mover
    }
    await _audit_log(
        "process_company_transferred", "client", client_id, actor,
        details={
            "para": carimbo,
            "processos": ids_a_mover,
            "de": origens,
            "ja_no_destino": [p.get("id") for p in ja_la],
            "ficha_do_cliente": "inalterada",
            "s3_folder": "inalterado",
        },
    )
    await _historico_dos_processos(a_mover, actor, carimbo)

    logger.info(
        "[PROCESSO-EMPRESA] %s moveu %d processo(s) do cliente %s para %s.",
        (actor or {}).get("id"), len(ids_a_mover), client_id, carimbo["company_name"],
    )
    return {
        "transferido": True,
        "empresa": carimbo,
        "processos_transferidos": len(ids_a_mover),
        "processos_ja_no_destino": [_resumo(p, ja_no_destino=True) for p in ja_la],
        "ficha_do_cliente": "inalterada",
        "s3_folder": "inalterado",
    }


async def _historico_dos_processos(processos: list[dict], actor: dict, destino: dict) -> None:
    """Uma linha no histórico de cada processo. Nunca levanta (o rasto não desfaz a acção)."""
    from services.history import log_history

    for processo in processos:
        de = processo.get("company_name") or processo.get("company") or "—"
        try:
            await log_history(
                processo["id"], actor, "Processo transferido para outra empresa",
                "company_name", de, destino["company_name"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PROCESSO-EMPRESA] Histórico de %s falhou: %s", processo.get("id"), exc)


__all__ = [
    "TransferirClienteIn",
    "run_preview_transfer_client_company", "run_transfer_client_company",
]
