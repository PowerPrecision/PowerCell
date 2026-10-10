"""Revogar uma partilha à mão — a entrada da rota (Bloco 1, remate).

A Via Rápida (D-25) abre um processo à rede de quem foi atribuído, sem
aprovação, e tirar a atribuição **não** revoga (decisão do dono do
produto): o parceiro mantém o histórico e os documentos que produziu.
Sem uma forma de revogar a mão, a abertura era IRREVERSÍVEL sem acesso à
base de dados. Este é o acto manual que faltava.

AS REGRAS
=========
* **Quem**: admin, CEO e diretor (o papel EFECTIVO, não o do JWT). O
  diretor só da casa DONA do processo: o de uma rede convidada vê o
  processo, mas quem decide quem mais o vê é a casa que o detém. Admin e
  CEO reconciliam entre redes, como no resto da fronteira de documentos;
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
    parceiros_do_processo,
    revogar_parceiro,
)
from services.tenant_access_context import resolver_papel_efectivo
from services.tenant_network import (
    PROJECCAO_DO_CARIMBO,
    documento_no_ambito,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

PAPEIS_QUE_REVOGAM = ("master", "admin", "ceo", "diretor")
#: Atravessam redes (reconciliam a pilha inteira).
PAPEIS_SEM_FRONTEIRA = tuple(sorted(PAPEIS_GLOBAIS))

ERRO_PROCESSO_NAO_ENCONTRADO = "Processo não encontrado"
ERRO_SEM_PERMISSAO = "Só a administração e a direcção podem revogar uma partilha."
ERRO_NAO_E_A_CASA_DONA = (
    "Só a empresa dona do processo pode revogar a partilha."
)
ERRO_NAO_E_PARCEIRA = "Esta empresa não é parceira deste processo."


def _pode_revogar(papel: str) -> bool:
    return str(papel or "").strip().lower() in PAPEIS_QUE_REVOGAM


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

    # Vê o processo — mas é a casa DONA que decide quem mais o vê.
    if not atravessa_redes and not documento_no_ambito(processo, scope):
        raise HTTPException(status_code=403, detail=ERRO_NAO_E_A_CASA_DONA)

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
