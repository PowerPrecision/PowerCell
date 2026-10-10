"""Registo semanal executivo (Bloco 4, ponto 13).

Para o CEO: o progresso da semana (mudanças de fase) e as tarefas
concluídas/pendentes de cada colaborador da SUA rede, numa vista que se
abre depressa — e que fica como REGISTO.

SEMANA FECHADA = REGISTO; SEMANA A DECORRER = VISTA
  * Uma semana já terminada (domingo anterior a hoje) calcula-se UMA vez e
    guarda-se em `executive_weekly_reports`, por (âmbito, segunda-feira).
    Reabri-la daqui a um mês não volta a agregar `history` e `tasks` — é
    também o que protege a base de dados em instâncias grandes — e mostra
    o que o CEO viu na altura. A «carga em aberto» é reconstruída no fim da
    semana (ver `executive_report`), por isso o registo é reproduzível.
  * A semana a decorrer calcula-se ao vivo (com a cache de 60 s do motor) e
    NÃO se guarda: um registo de uma semana incompleta seria uma mentira
    que parece definitiva.
  * Semana futura: recusada.

O QUE O REGISTO NÃO GUARDA
  Nomes de clientes. O registo leva o número do processo e as fases; o nome
  resolve-se na LEITURA, com os dados de hoje — um cliente anonimizado por
  RGPD depois da semana não pode continuar a aparecer pelo nome num registo.

CRIAÇÃO LAZY
  O registo nasce na primeira abertura da semana fechada, não num job:
  um job por rede acoplava o agendador à topologia de redes. A semana
  reconstrói-se identicamente, por isso o resultado é o mesmo.
  `forcar=True` (só pedido explícito) regenera e substitui.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from database import db
from services import executive_report as er

logger = logging.getLogger(__name__)

COLECAO = "executive_weekly_reports"
SEMANAS_NA_LISTA = 12
ORIGEM_MANUAL = "manual"


def semana_pedida(referencia: Optional[str], *, hoje: Optional[date] = None) -> tuple[date, date]:
    """Segunda e domingo da semana de `referencia` (omissão: a anterior, fechada)."""
    hoje = hoje or datetime.now(timezone.utc).date()
    if referencia:
        dia = er.parse_data(referencia, "week")
    else:
        dia = hoje - timedelta(days=7)
    segunda, domingo = er.semana_de(dia)
    if segunda > hoje:
        raise er.PeriodoInvalido("Não há relatório de uma semana que ainda não começou")
    return segunda, domingo


def semana_esta_fechada(domingo: date, *, hoje: Optional[date] = None) -> bool:
    return domingo < (hoje or datetime.now(timezone.utc).date())


def semanas_recentes(n: int = SEMANAS_NA_LISTA, *, hoje: Optional[date] = None) -> list[date]:
    """As segundas-feiras das últimas `n` semanas, a actual primeiro."""
    atual = er.segunda_da_semana(hoje or datetime.now(timezone.utc).date())
    return [atual - timedelta(weeks=i) for i in range(n)]


async def _com_nomes_dos_clientes(base, relatorio: dict, ambito: er.Ambito) -> dict:
    """Junta o nome do cliente aos movimentos, lido AGORA (nunca guardado)."""
    movimentos = relatorio.get("movimentos") or []
    if not movimentos:
        return relatorio
    processos = await er._ler_processos(base, sorted({m["process_id"] for m in movimentos if m.get("process_id")}))
    saida = dict(relatorio)
    saida["movimentos"] = [
        {**m, "client_name": (processos.get(m.get("process_id")) or {}).get("client_name") or ""}
        for m in movimentos
    ]
    return saida


async def obter_semana(
    user: dict,
    referencia: Optional[str] = None,
    *,
    forcar: bool = False,
    base=None,
    hoje: Optional[date] = None,
) -> dict:
    """O relatório da semana, do registo se existir (e a semana estiver fechada)."""
    base = base if base is not None else db
    segunda, domingo = semana_pedida(referencia, hoje=hoje)
    fechada = semana_esta_fechada(domingo, hoje=hoje)
    ambito = await er.resolver_ambito(user)
    colecao = getattr(base, COLECAO)
    chave = {"scope_key": ambito.chave, "week_start": segunda.isoformat()}

    if fechada and not forcar:
        guardado = await colecao.find_one(chave, {"_id": 0})
        if guardado and guardado.get("report"):
            relatorio = await _com_nomes_dos_clientes(base, guardado["report"], ambito)
            relatorio["registo"] = {
                "guardado": True,
                "gerado_em": guardado.get("generated_at"),
                "gerado_por": guardado.get("generated_by_name"),
                "origem": guardado.get("origem"),
            }
            return relatorio

    filtros = er.Filtros(er.Periodo(segunda, domingo), com_movimentos=True)
    relatorio = await er.gerar_relatorio(ambito, filtros, usar_cache=not forcar, base=base)

    registo: dict[str, Any] = {"guardado": False, "gerado_em": relatorio.get("gerado_em")}
    if fechada:
        agora = datetime.now(timezone.utc).isoformat()
        documento = {
            **chave,
            "week_end": domingo.isoformat(),
            "redes": list(ambito.redes),
            "generated_at": agora,
            "generated_by_id": user.get("id"),
            "generated_by_name": user.get("name"),
            "origem": ORIGEM_MANUAL,
            # Sem nomes de clientes: ver a docstring do módulo.
            "report": relatorio,
        }
        try:
            await colecao.update_one(chave, {"$set": documento}, upsert=True)
            registo = {"guardado": True, "gerado_em": agora, "gerado_por": user.get("name"), "origem": ORIGEM_MANUAL}
        except Exception as erro:  # o registo falhar não pode esconder o relatório
            logger.warning("[RELATORIO-SEMANAL] Registo não guardado (%s): %s", segunda, erro)

    saida = await _com_nomes_dos_clientes(base, relatorio, ambito)
    saida["registo"] = registo
    return saida


async def listar_semanas(user: dict, *, base=None, hoje: Optional[date] = None) -> list[dict]:
    """As últimas semanas, com a indicação de qual já tem registo."""
    base = base if base is not None else db
    hoje = hoje or datetime.now(timezone.utc).date()
    segundas = semanas_recentes(hoje=hoje)
    ambito = await er.resolver_ambito(user)
    existentes = await getattr(base, COLECAO).find(
        {"scope_key": ambito.chave, "week_start": {"$in": [s.isoformat() for s in segundas]}},
        {"_id": 0, "week_start": 1},
    ).to_list(len(segundas))
    com_registo = {e["week_start"] for e in existentes}
    return [
        {
            "week_start": s.isoformat(),
            "week_end": (s + timedelta(days=6)).isoformat(),
            "fechada": semana_esta_fechada(s + timedelta(days=6), hoje=hoje),
            "tem_registo": s.isoformat() in com_registo,
        }
        for s in segundas
    ]
