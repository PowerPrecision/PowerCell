"""SLA de inactividade do Index, em DOIS níveis (Out 2026) — corre no job horário `scheduled_tasks`.

A atribuição do Index é automática (`assign_to_indexer`) e já não há «Reivindicar»: nada obriga o indexador
atribuído a pegar no processo, e um processo parado numa pessoa ausente é um cliente à espera sem ninguém a
saber. Mas nem todo o processo parado é igual, e tratá-los da mesma maneira seria punir quem trabalha:

* **Nível 1 — intocado.** Atribuído, ainda `pending` (a pessoa nunca lhe mexeu) e passadas
  `INDEX_SLA_UNTOUCHED_HOURS` horas (48) desde a atribuição → **retira-se a atribuição e reatribui-se** a
  outro indexador da equipa (a mesma regra de carga da atribuição normal). Nada se perde: não há trabalho
  em curso.
* **Nível 2 — estagnado.** O indexador já começou (`in_review`) e o processo não tem actividade há mais de
  `INDEX_SLA_STALE_DAYS` dias (5) → **NÃO se retira a atribuição** (há trabalho feito: metadados editados,
  ficheiros, análises — reatribuir deitá-lo fora ou entregá-lo a quem não o conhece). Gera-se um alerta ao
  indexador e à chefia da rede do processo, repetido de `INDEX_SLA_STALE_DAYS` em `INDEX_SLA_STALE_DAYS`
  enquanto continuar parado, e que recomeça se houver actividade e voltar a parar.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **O nível 1 só mexe em quem NUNCA começou.** O filtro da escrita (`index_status: pending`, o mesmo
   indexador, ainda não indexado) é a guarda: se o indexador abre a bancada entre a leitura e a escrita, o
   `update_one` não casa e nada se reatribui — uma corrida resolve-se a favor de quem trabalha.
2. **A actividade vem de `index_status.registar_trabalho`** (só o indexador atribuído a carimba; abrir a
   bancada, analisar, editar, dispensar alertas, carregar ficheiros). Um diretor a espreitar não adia o
   alarme, e uma aba esquecida aberta também não (o GET da bancada não carimba).
3. **Um processo legado sem `index_assigned_at` não é reatribuído em massa no primeiro ciclo:** o relógio
   começa quando o job o vê pela primeira vez (carimbo «se faltar»). Reatribuir de uma vez centenas de
   processos antigos por causa de uma data que nunca existiu seria o contrário de prudente.
4. **Sem candidato não se desatribui.** Se mais ninguém tem vaga, o processo fica com quem está (e volta a
   tentar-se no ciclo seguinte): um processo sem dono não se nota até alguém reparar que ninguém lhe pega.
   Prefere-se, quando há alternativa, quem ainda não teve o processo (`index_sla_anteriores`), para um
   processo não andar em círculo entre dois ausentes.
5. **Só processos activos** (fase não terminal do workflow da rede dona) e nunca os de Via Verde / indexados.
6. **O alerta de estagnação chega a pessoas por id**: o indexador atribuído e a gestão DA REDE do processo
   (`alert_audience`, que falha fechada sem rede determinável) — a chefia de outra rede nunca vê o cliente.
7. **Tudo se pode desligar** (`INDEX_SLA_ENABLED=false`) e todos os limiares são configuráveis; um valor
   inválido ou ≤ 0 cai na omissão (nunca desliga um limiar). O ciclo nunca levanta por causa de um processo.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import db
from services import index_status as estado_do_index

logger = logging.getLogger(__name__)

HORAS_SEM_PEGAR_POR_OMISSAO = 48
DIAS_SEM_ACTIVIDADE_POR_OMISSAO = 5
TECTO_POR_CICLO = 200
CATEGORIA_DO_ALERTA = "index_stagnation"
ROLES_DA_CHEFIA = ("diretor", "ceo", "admin", "master")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _positivo(valor: Any, omissao: int) -> int:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return omissao
    return omissao if n <= 0 else n


def sla_activo(ambiente=None) -> bool:
    fonte = ambiente if ambiente is not None else os.environ
    return str(fonte.get("INDEX_SLA_ENABLED", "true")).strip().lower() not in ("false", "0", "no", "off")


def horas_sem_pegar(ambiente=None) -> int:
    fonte = ambiente if ambiente is not None else os.environ
    return _positivo(fonte.get("INDEX_SLA_UNTOUCHED_HOURS"), HORAS_SEM_PEGAR_POR_OMISSAO)


def dias_sem_actividade(ambiente=None) -> int:
    fonte = ambiente if ambiente is not None else os.environ
    return _positivo(fonte.get("INDEX_SLA_STALE_DAYS"), DIAS_SEM_ACTIVIDADE_POR_OMISSAO)


def _para_datetime(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


# ====================================================================
# PURO
# ====================================================================
def esta_intocado(processo: dict, agora: datetime, horas: int) -> bool:
    """Nível 1: atribuído, nunca começado, e a atribuição já vai além do prazo. Pura."""
    if not processo.get("assigned_indexacao_id") or processo.get("index_status") == estado_do_index.IN_REVIEW:
        return False
    if processo.get("is_indexed") is True or processo.get("skip_index") is True:
        return False
    desde = _para_datetime(processo.get("index_assigned_at"))
    return desde is not None and agora - desde >= timedelta(hours=horas)


def ultima_actividade(processo: dict) -> Optional[datetime]:
    """O momento a partir do qual se conta a estagnação: a última actividade do indexador, senão o arranque,
    senão (legado, anterior a este lote) a última alteração do processo. Pura."""
    for campo in ("index_last_activity_at", "index_work_started_at", "updated_at", "created_at"):
        momento = _para_datetime(processo.get(campo))
        if momento is not None:
            return momento
    return None


def esta_estagnado(processo: dict, agora: datetime, dias: int) -> bool:
    """Nível 2: o indexador começou (`in_review`) e não há actividade há mais de `dias`. Pura."""
    if not processo.get("assigned_indexacao_id") or processo.get("index_status") != estado_do_index.IN_REVIEW:
        return False
    if processo.get("is_indexed") is True or processo.get("skip_index") is True:
        return False
    desde = ultima_actividade(processo)
    return desde is not None and agora - desde > timedelta(days=dias)


def deve_alertar(processo: dict, agora: datetime, dias: int) -> bool:
    """Um processo estagnado pede alerta se nunca o teve neste período de inactividade, ou se o último foi há
    mais de `dias` (lembrete). Actividade posterior ao alerta reabre o ciclo. Pura."""
    if not esta_estagnado(processo, agora, dias):
        return False
    alertado = _para_datetime(processo.get("index_stagnation_alerted_at"))
    if alertado is None:
        return True
    desde = ultima_actividade(processo)
    if desde is not None and desde > alertado:
        return True
    return agora - alertado >= timedelta(days=dias)


def escolher_novo_indexador(disponiveis: list[dict], anteriores: list[str]) -> Optional[dict]:
    """Do menos ocupado, preferindo quem ainda não teve este processo. `disponiveis` vem ordenado por carga. Pura."""
    if not disponiveis:
        return None
    novos = [d for d in disponiveis if d["id"] not in set(anteriores)]
    return (novos or disponiveis)[0]


# ====================================================================
# I/O
# ====================================================================
PROJECCAO = {
    "_id": 0, "id": 1, "process_number": 1, "client_name": 1, "status": 1, "network_id": 1, "is_indexed": 1,
    "skip_index": 1, "index_status": 1, "assigned_indexacao_id": 1, "indexacao_name": 1, "index_assigned_at": 1,
    "index_work_started_at": 1, "index_last_activity_at": 1, "index_stagnation_alerted_at": 1,
    "index_sla_anteriores": 1, "updated_at": 1, "created_at": 1,
}


async def _carimbar_legados(agora: datetime, condicao_activa: dict) -> int:
    """Regra 3: o processo legado (atribuído, ainda por começar, sem `index_assigned_at`) começa a contar hoje."""
    r = await db.processes.update_many(
        {
            "$and": [condicao_activa, {"is_deleted": {"$ne": True}}, {"is_indexed": {"$ne": True}}, {"skip_index": {"$ne": True}}],
            "assigned_indexacao_id": {"$nin": [None, ""]},
            "index_status": {"$ne": estado_do_index.IN_REVIEW},
            "index_assigned_at": {"$exists": False},
        },
        {"$set": {"index_assigned_at": agora.isoformat()}},
    )
    return r.modified_count


async def reatribuir_intocados(agora: datetime, horas: int, condicao_activa: dict) -> dict[str, int]:
    """Nível 1. Devolve `{candidatos, reatribuidos, sem_candidato, corridas}`."""
    from services.history import log_history
    from services.process_assignment import indexadores_disponiveis
    from services.realtime_notifications import send_realtime_notification

    resumo = {"candidatos": 0, "reatribuidos": 0, "sem_candidato": 0, "corridas": 0}
    limite = (agora - timedelta(hours=horas)).isoformat()
    # pré-filtro barato; a decisão final é `esta_intocado` (datas em Python: os formatos ISO podem variar)
    candidatos = await db.processes.find(
        {
            "$and": [condicao_activa, {"is_deleted": {"$ne": True}}, {"is_indexed": {"$ne": True}}, {"skip_index": {"$ne": True}}],
            "assigned_indexacao_id": {"$nin": [None, ""]},
            "index_status": {"$ne": estado_do_index.IN_REVIEW},
            "index_assigned_at": {"$lte": limite},
        },
        PROJECCAO,
    ).sort("index_assigned_at", 1).limit(TECTO_POR_CICLO).to_list(TECTO_POR_CICLO)

    for processo in candidatos:
        if not esta_intocado(processo, agora, horas):
            continue
        resumo["candidatos"] += 1
        actual = processo["assigned_indexacao_id"]
        anteriores = [*(processo.get("index_sla_anteriores") or []), actual]
        try:
            disponiveis = await indexadores_disponiveis(processo, excluir={actual})
            novo = escolher_novo_indexador(disponiveis, anteriores)
            if novo is None:
                resumo["sem_candidato"] += 1
                logger.info("[INDEX-SLA] Processo %s intocado mas sem outro indexador com vaga: fica com o actual.", processo["id"])
                continue
            r = await db.processes.update_one(
                {
                    "id": processo["id"], "assigned_indexacao_id": actual, "index_status": {"$ne": estado_do_index.IN_REVIEW},
                    "is_indexed": {"$ne": True}, "skip_index": {"$ne": True}, "is_deleted": {"$ne": True},
                },
                {
                    "$set": {
                        "assigned_indexacao_id": novo["id"], "indexacao_name": novo["name"],
                        "index_assigned_at": agora.isoformat(), "updated_at": agora.isoformat(),
                        "index_sla_anteriores": anteriores[-10:],
                    },
                    "$inc": {"index_sla_reatribuicoes": 1},
                },
            )
            if not r.modified_count:
                resumo["corridas"] += 1  # o indexador começou entre a leitura e a escrita: ganha quem trabalha
                continue
            resumo["reatribuidos"] += 1
            numero = processo.get("process_number") or str(processo["id"])[:8]
            try:
                await log_history(
                    process_id=processo["id"], user={"id": "system", "name": "Sistema", "role": "admin"},
                    action=f"Reatribuído automaticamente a {novo['name']}: o indexador anterior não começou em {horas}h",
                    field="assigned_indexacao_id", old_value=processo.get("indexacao_name") or actual, new_value=novo["name"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[INDEX-SLA] Histórico do processo %s não gravado: %s", processo["id"], type(exc).__name__)
            await _avisar(
                send_realtime_notification, actual, "Processo retirado por inactividade",
                f"O processo {numero} foi reatribuído: não foi iniciado em {horas}h.", processo["id"], "process_unassigned",
            )
            await _avisar(
                send_realtime_notification, novo["id"], "Novo Processo Atribuído",
                f"Foi-lhe atribuído o processo {numero} (reatribuído por inactividade do indexador anterior).",
                processo["id"], "process_assigned",
            )
        except Exception as exc:  # noqa: BLE001 — um processo a rebentar não pára o ciclo
            logger.warning("[INDEX-SLA] Processo %s não reatribuído: %s", processo.get("id"), type(exc).__name__)
    return resumo


async def _avisar(enviar, user_id: str, titulo: str, mensagem: str, process_id: str, tipo: str) -> bool:
    """Uma notificação in-app para UMA pessoa. Nunca levanta (observa, não intercepta)."""
    try:
        await enviar(user_id=user_id, title=titulo, message=mensagem, notification_type=tipo,
                     link=f"/index/{process_id}", process_id=process_id)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX-SLA] Aviso a %s não enviado: %s", user_id, type(exc).__name__)
        return False


async def alertar_estagnados(agora: datetime, dias: int, condicao_activa: dict) -> dict[str, int]:
    """Nível 2. NÃO mexe na atribuição. Devolve `{estagnados, alertados, avisos}`."""
    from services.alert_audience import gestao_da_rede_do_processo
    from services.realtime_notifications import send_realtime_notification

    resumo = {"estagnados": 0, "alertados": 0, "avisos": 0}
    candidatos = await db.processes.find(
        {
            "$and": [condicao_activa, {"is_deleted": {"$ne": True}}, {"is_indexed": {"$ne": True}}, {"skip_index": {"$ne": True}}],
            "assigned_indexacao_id": {"$nin": [None, ""]},
            "index_status": estado_do_index.IN_REVIEW,
        },
        PROJECCAO,
    ).limit(TECTO_POR_CICLO).to_list(TECTO_POR_CICLO)

    for processo in candidatos:
        if not esta_estagnado(processo, agora, dias):
            continue
        resumo["estagnados"] += 1
        if not deve_alertar(processo, agora, dias):
            continue
        try:
            desde = ultima_actividade(processo)
            parado = max(dias, (agora - desde).days) if desde else dias
            numero = processo.get("process_number") or str(processo["id"])[:8]
            indexador = processo["assigned_indexacao_id"]
            chefia = await gestao_da_rede_do_processo(processo, ROLES_DA_CHEFIA)
            destinatarios = [indexador, *[c for c in chefia if c != indexador]]
            enviados = 0
            for uid in destinatarios:
                mensagem = (
                    f"O processo {numero} está em tratamento no Index mas sem actividade há {parado} dias."
                    if uid != indexador or len(destinatarios) == 1
                    else f"O seu processo {numero} no Index não tem actividade há {parado} dias."
                )
                if uid != indexador:
                    mensagem += f" Indexador: {processo.get('indexacao_name') or 'atribuído'}."
                enviados += int(await _avisar(
                    send_realtime_notification, uid, "Processo parado no Index", mensagem, processo["id"], CATEGORIA_DO_ALERTA,
                ))
            # a marca só avança se alguém foi avisado: um ciclo sem entrega repete-se no seguinte
            if enviados:
                await db.processes.update_one(
                    {"id": processo["id"], "index_status": estado_do_index.IN_REVIEW},
                    {"$set": {"index_stagnation_alerted_at": agora.isoformat()}, "$inc": {"index_stagnation_alerts": 1}},
                )
                resumo["alertados"] += 1
                resumo["avisos"] += enviados
        except Exception as exc:  # noqa: BLE001
            logger.warning("[INDEX-SLA] Alerta do processo %s não enviado: %s", processo.get("id"), type(exc).__name__)
    return resumo


async def correr_sla_do_index(*, agora: Optional[datetime] = None, ambiente=None) -> dict[str, Any]:
    """Um ciclo dos dois níveis. Chamado pelo job horário; devolve o resumo (contagens, nunca nomes)."""
    if not sla_activo(ambiente):
        return {"activo": False}
    from services.index_api import condicao_de_processo_activo

    agora = agora or _agora()
    horas, dias = horas_sem_pegar(ambiente), dias_sem_actividade(ambiente)
    activa = await condicao_de_processo_activo()
    carimbados = await _carimbar_legados(agora, activa)
    nivel1 = await reatribuir_intocados(agora, horas, activa)
    nivel2 = await alertar_estagnados(agora, dias, activa)
    resumo = {"activo": True, "horas": horas, "dias": dias, "legados_carimbados": carimbados, "nivel1": nivel1, "nivel2": nivel2}
    logger.info("[INDEX-SLA] %s", resumo)
    return resumo


__all__ = [
    "correr_sla_do_index", "deve_alertar", "dias_sem_actividade", "escolher_novo_indexador", "esta_estagnado",
    "esta_intocado", "horas_sem_pegar", "sla_activo", "ultima_actividade",
]
