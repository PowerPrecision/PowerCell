"""Revogar uma partilha à mão — a entrada da rota (Bloco 1, remate).

A Via Rápida (D-25) abre um processo à rede de quem foi atribuído, sem
aprovação, e tirar a atribuição **não** revoga (decisão do dono do
produto): o parceiro mantém o histórico e os documentos que produziu.
Sem uma forma de revogar a mão, a abertura era IRREVERSÍVEL sem acesso à
base de dados. Este é o acto manual que faltava.

AS REGRAS
=========
* **Quem**: admin, CEO e diretor (o papel EFECTIVO, não o do JWT). A casa
  DONA retira qualquer elo. Uma rede CONVIDADA só retira os elos que ela
  abriu (e os que dela derivam, na cadeia) — não os da casa dona nem os de
  uma convidada irmã (Out 2026, partilha em cadeia). Admin/CEO/Master
  reconciliam entre redes, como no resto da fronteira de documentos;
* **403 e não 404** a quem vê o processo e não pode decidir: já sabe que
  ele existe, e o motivo diz-se. **404** a quem nem sequer o vê, com a
  MESMA mensagem de «não existe» (não se confirma o id);
* só retira a empresa pedida: as outras partilhas e o `network_id` do
  dono ficam intactos;
* deixa rasto no histórico do processo (que honra o interruptor de
  histórico) e no trilho de auditoria — excepto se o actor for
  silenciado (restrição de segurança do perfil Indexação).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from services.role_scope import PAPEIS_GLOBAIS
from services.history import _is_stealth_user, log_history
from services.process_sharing import (
    CAMPO_EMPRESAS_PARCEIRAS,
    CAMPO_REDES_PARCEIRAS,
    DestinoInvalido,
    empresas_da_rede,
    elo_e_meu,
    parceiros_do_processo,
    partilhar_com_rede,
    redes_do_registo,
    revogar_parceiro,
)
from services.tenant_access_context import resolver_papel_efectivo
from services.tenant_network import (
    CAMPO_REDE,
    PROJECCAO_DO_CARIMBO,
    documento_no_ambito,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

PAPEIS_QUE_REVOGAM = ("master", "admin", "ceo", "diretor")
#: Quem envia um processo para outra rede: a gestão e o back-office. Abrir a
#: ficha inteira a outra empresa não é uma decisão de quem trata do cliente.
PAPEIS_QUE_PARTILHAM = ("master", "admin", "ceo", "diretor", "administrativo")
#: Atravessam redes (reconciliam a pilha inteira).
PAPEIS_SEM_FRONTEIRA = tuple(sorted(PAPEIS_GLOBAIS))

ERRO_PROCESSO_NAO_ENCONTRADO = "Processo não encontrado"
ERRO_SEM_PERMISSAO = "Só a administração e a direcção podem revogar uma partilha."
ERRO_NAO_E_PARCEIRA = "Esta empresa não é parceira deste processo."
ERRO_SEM_PERMISSAO_PARTILHAR = (
    "Só a administração, a direcção e o administrativo podem partilhar um processo com outra rede."
)
ERRO_NAO_E_O_SEU_ELO = (
    "Só pode retirar as partilhas que a sua empresa abriu (ou a casa dona do processo)."
)


def _pode_revogar(papel: str) -> bool:
    return str(papel or "").strip().lower() in PAPEIS_QUE_REVOGAM


def _pode_partilhar(papel: str) -> bool:
    return str(papel or "").strip().lower() in PAPEIS_QUE_PARTILHAM


async def _nome_da_rede(rede: str, fallback: str = "") -> str:
    nomes = [str(e.get("name") or "").strip() for e in await empresas_da_rede(rede)]
    return " / ".join(n for n in nomes if n) or fallback


async def _quem_partilha(processo: dict, scope, atravessa_redes: bool) -> dict:
    """A rede (e o nome) em nome da qual se abre o elo.

    A casa dona, se o utilizador é dela (ou é Master); senão a rede CONVIDADA por onde
    ele vê o processo — a primeira do registo que esteja no seu âmbito.
    """
    dona = str(processo.get(CAMPO_REDE) or "").strip()
    if atravessa_redes or documento_no_ambito(processo, scope):
        return {CAMPO_REDE: dona, "company_name": str(processo.get("company_name") or "").strip()
                or await _nome_da_rede(dona)}
    minhas = {str(r).strip() for r in scope.network_ids if str(r).strip()}
    for entrada in parceiros_do_processo(processo):
        rede = str(entrada.get(CAMPO_REDE) or "").strip()
        if rede in minhas:
            return {CAMPO_REDE: rede, "company_name": str(entrada.get("company_name") or "").strip()
                    or await _nome_da_rede(rede)}
    return {CAMPO_REDE: dona, "company_name": ""}


async def _processo_que_posso_partilhar(
    process_id: str, user: dict, request: Optional[Request],
) -> tuple[dict, dict]:
    """Papel e visibilidade — e QUEM abre o elo (a casa dona ou uma convidada).

    Partilha em cadeia (Out 2026): quem VÊ o processo pode passá-lo à frente, sem
    aprovação do parceiro angariador nem da casa dona. 403 a quem não tem o papel;
    404 (igual ao de «não existe») a quem nem o vê.
    """
    papel = await resolver_papel_efectivo(
        user, request, traduzir_todos_os_perfis=_pode_partilhar,
    )
    if not _pode_partilhar(papel):
        raise HTTPException(status_code=403, detail=ERRO_SEM_PERMISSAO_PARTILHAR)

    scope = await resolve_tenant_scope(user)
    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1, "via_verde": 1, "company_name": 1,
         CAMPO_EMPRESAS_PARCEIRAS: 1, CAMPO_REDES_PARCEIRAS: 1, **PROJECCAO_DO_CARIMBO},
    )
    atravessa_redes = str(papel).strip().lower() in PAPEIS_SEM_FRONTEIRA
    if not processo or not (atravessa_redes or processo_no_ambito(processo, scope)):
        raise HTTPException(status_code=404, detail=ERRO_PROCESSO_NAO_ENCONTRADO)
    return processo, await _quem_partilha(processo, scope, atravessa_redes)


async def run_list_share_targets(
    process_id: str, user: dict, request: Optional[Request] = None,
) -> dict:
    """As redes para onde este processo pode ser enviado, com o que o ecrã precisa."""
    from services.network_triage import redes_com_index
    from services.tenant_network import resolve_network_id

    processo, quem = await _processo_que_posso_partilhar(process_id, user, request)
    dono = str(processo.get(CAMPO_REDE) or "").strip()
    ja = set(redes_do_registo(parceiros_do_processo(processo)))
    # A rede de quem partilha nunca é destino (já vê o processo).
    propria = str(quem.get(CAMPO_REDE) or "").strip()
    com_index = await redes_com_index()

    empresas = await db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1, "is_active": 1},
    ).to_list(1000)
    redes: dict[str, list[str]] = {}
    for e in empresas:
        if e.get("is_active") is False:
            continue
        rede = resolve_network_id(e, company_id=e.get("id"))
        if rede and rede != dono and rede != propria and str(e.get("name") or "").strip():
            redes.setdefault(rede, []).append(str(e["name"]).strip())

    destinos = [
        {
            "network_id": rede,
            "empresas": sorted(nomes, key=str.lower),
            "tem_index": rede in com_index,
            "ja_partilhado": rede in ja,
        }
        for rede, nomes in redes.items()
    ]
    destinos.sort(key=lambda d: d["empresas"][0].lower())
    return {
        "process_id": process_id,
        "via_verde": processo.get("via_verde") is True,
        "destinos": destinos,
    }


async def run_share_process(
    process_id: str,
    network_id: str,
    via_verde: Optional[bool],
    user: dict,
    request: Optional[Request] = None,
) -> dict:
    """Envia o processo para a rede de destino escolhida (multi-fornecedor)."""
    _, quem = await _processo_que_posso_partilhar(process_id, user, request)

    async def _historico(texto: str) -> None:
        await log_history(process_id, user, texto, CAMPO_EMPRESAS_PARCEIRAS)

    try:
        resultado = await partilhar_com_rede(
            process_id,
            network_id,
            via_verde=via_verde,
            por_ordem_de=user.get("id") or user.get("email"),
            registar_historico=_historico,
            partilhado_por=quem,
        )
    except DestinoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    actual = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, CAMPO_EMPRESAS_PARCEIRAS: 1, CAMPO_REDES_PARCEIRAS: 1},
    ) or {}
    return {
        "success": True,
        "process_id": process_id,
        **{k: v for k, v in resultado.items() if k != "triagem"},
        "triagem": (resultado.get("triagem") or {}).get("state"),
        "parceiros": parceiros_do_processo(actual),
    }


async def run_revoke_partner(
    process_id: str,
    company_id: str,
    user: dict,
    request: Optional[Request] = None,
) -> dict:
    """Retira UMA empresa convidada de um processo."""
    papel = await resolver_papel_efectivo(
        user, request, traduzir_todos_os_perfis=_pode_revogar,
    )
    if not _pode_revogar(papel):
        raise HTTPException(status_code=403, detail=ERRO_SEM_PERMISSAO)

    scope = await resolve_tenant_scope(user)
    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1,
         CAMPO_EMPRESAS_PARCEIRAS: 1, CAMPO_REDES_PARCEIRAS: 1, **PROJECCAO_DO_CARIMBO},
    )
    atravessa_redes = str(papel).strip().lower() in PAPEIS_SEM_FRONTEIRA
    if not processo or not (atravessa_redes or processo_no_ambito(processo, scope)):
        raise HTTPException(status_code=404, detail=ERRO_PROCESSO_NAO_ENCONTRADO)

    # Vê o processo. A casa DONA retira qualquer elo; uma CONVIDADA só os que abriu
    # (e os que dela derivam). Distingue-se «não é parceira deste processo» (404) de «é,
    # mas o elo não é seu» (403).
    if not atravessa_redes and not documento_no_ambito(processo, scope):
        entrada = next(
            (e for e in parceiros_do_processo(processo) if str(e.get("company_id") or "") == str(company_id)),
            None,
        )
        if entrada is None:
            raise HTTPException(status_code=404, detail=ERRO_NAO_E_PARCEIRA)
        if not elo_e_meu(
            parceiros_do_processo(processo), entrada,
            {str(r).strip() for r in scope.network_ids}, str(processo.get(CAMPO_REDE) or ""),
        ):
            raise HTTPException(status_code=403, detail=ERRO_NAO_E_O_SEU_ELO)

    async def _historico(texto: str) -> None:
        await log_history(process_id, user, texto, CAMPO_EMPRESAS_PARCEIRAS)

    retiradas = await revogar_parceiro(
        process_id,
        company_id=company_id,
        por_ordem_de=user.get("id") or user.get("email"),
        registar_historico=_historico,
        auditar=not _is_stealth_user(user),
    )
    if not retiradas:
        raise HTTPException(status_code=404, detail=ERRO_NAO_E_PARCEIRA)

    actual = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, CAMPO_EMPRESAS_PARCEIRAS: 1, CAMPO_REDES_PARCEIRAS: 1},
    ) or {}
    return {
        "success": True,
        "process_id": process_id,
        "revogadas": [
            r.get("company_name") or r.get("network_id") or "?" for r in retiradas
        ],
        "parceiros_restantes": parceiros_do_processo(actual),
    }
