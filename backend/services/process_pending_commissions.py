"""«Marcar como Pago» na Lista de Processos — o que a listagem precisa de saber.

O PROBLEMA
  As comissões pagam-se no FIM, quando o processo já está «Concluído». A guarda
  do processo fechado (D-34) obrigava o administrativo a reabrir o processo só
  para registar uma entrada de dinheiro. A excepção cirúrgica está em
  `finance_process_records` (só «pago»); este módulo diz à LISTAGEM a quem
  oferecer o atalho.

O QUE ACRESCENTA A CADA LINHA  (calculado ao servir, NUNCA gravado)
  * `processo_fechado`   — a fase é terminal no motor;
  * `comissoes_pendentes` — quantos registos financeiros pendentes/faturados
    o utilizador VÊ nesse processo (as empresas das suas redes: uma partilha
    pode ter um registo por empresa e o das outras redes não é dele).

  O ecrã mostra o botão quando as duas coisas se juntam. Só se calcula para
  quem pode marcar como pago, e só se consulta a BD para processos fechados:
  um valor financeiro não vai a quem não o pode usar, e a listagem dos
  consultores não paga uma consulta que não usa. Quem não pode, nem recebe as
  chaves.

  Uma falha a ler as comissões deixa a contagem a 0: é conveniência, a parede
  é o servidor (o POST de pagamento valida tudo outra vez).
"""
from __future__ import annotations

import logging
from typing import Optional

from database import db
from models.finance import FinanceStatus
from services.finance_helpers import PAPEIS_QUE_MARCAM_COMO_PAGO
from services.finance_scope import carregar_ambito_financeiro
from services.portal_estado import estado_e_terminal
from services.workflow_phases import chave_da_rede, fases_por_rede, rede_do_processo

logger = logging.getLogger(__name__)

CAMPO_FECHADO = "processo_fechado"
CAMPO_PENDENTES = "comissoes_pendentes"

ESTADOS_POR_PAGAR = (FinanceStatus.PENDING.value, FinanceStatus.INVOICED.value)


def papel_pode_marcar_como_pago(papel: Optional[str]) -> bool:
    return str(papel or "").strip() in {str(p) for p in PAPEIS_QUE_MARCAM_COMO_PAGO}


async def enriquecer_comissoes_pendentes(
    processos: list[dict], user: dict, *, papel: Optional[str],
) -> None:
    """Acrescenta `processo_fechado` e `comissoes_pendentes` às linhas."""
    if not processos:
        return
    if str(papel or "") == "__all_roles__":
        from services.property_scope import papel_efectivo

        papel = await papel_efectivo(user, None)
    if not papel_pode_marcar_como_pago(papel):
        return

    try:
        # Cada processo fecha segundo o workflow da rede DONA.
        fases_das_redes = await fases_por_rede(rede_do_processo(p) for p in processos)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FINANCAS] Sem fases para marcar os processos fechados: %s", exc)
        return

    fechados = {
        p["id"] for p in processos
        if p.get("id") and p.get("status") and estado_e_terminal(
            p["status"], fases_das_redes[chave_da_rede(rede_do_processo(p))],
        )
    }
    pendentes: dict[str, int] = {}
    if fechados:
        try:
            ambito = await carregar_ambito_financeiro(user, None, papel=papel)
            consulta: dict = {
                "process_id": {"$in": sorted(fechados)},
                "status": {"$in": list(ESTADOS_POR_PAGAR)},
            }
            if ambito.condicao:
                consulta = {"$and": [consulta, ambito.condicao]}
            registos = await db.process_finances.find(
                consulta, {"_id": 0, "process_id": 1},
            ).to_list(5000)
            for registo in registos:
                pid = registo.get("process_id")
                pendentes[pid] = pendentes.get(pid, 0) + 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[FINANCAS] Não foi possível contar as comissões pendentes: %s", exc)

    for p in processos:
        pid = p.get("id")
        p[CAMPO_FECHADO] = pid in fechados
        p[CAMPO_PENDENTES] = pendentes.get(pid, 0)


__all__ = [
    "CAMPO_FECHADO",
    "CAMPO_PENDENTES",
    "enriquecer_comissoes_pendentes",
    "papel_pode_marcar_como_pago",
]
