"""
====================================================================
NOTIFICAÇÕES NO TELEGRAM — fila, agrupamento e envio
====================================================================
Cada aviso que chega a um utilizador com o Telegram ligado entra numa
fila (`telegram_outbox`) agrupada por assunto:

- `processo:<id>` — tudo o que acontece ao mesmo processo. Quando o
  Index marca um processo como indexado nascem de rajada atribuições,
  mudanças de estado e documentos; isso sai numa SÓ mensagem
  («5 novidades no processo nº 1234»).
- `chat:<conversa>` — mensagens do chat da mesma conversa.
- `tipo:<tipo>` — avisos sem processo, agrupados por tipo.

O grupo abre com o primeiro aviso e fecha `TELEGRAM_JANELA_SEGUNDOS`
depois (90 s por omissão). A janela é FIXA a partir do primeiro aviso:
uma rajada que não pára não adia a mensagem para sempre.

Mensagens mínimas (RGPD — os servidores do Telegram ficam fora da UE):
nunca vai NIF, valores, nome do cliente nem o texto da notificação.
Só o tipo de aviso, o número do processo e um link que obriga a login.
Por isso a fila nem guarda o título/mensagem original.
====================================================================
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from database import db
from services import telegram_bot, telegram_link
from services.notification_policy import TIPOS_RUIDO, deve_notificar

logger = logging.getLogger(__name__)

INTERVALO_DO_CICLO_SEGUNDOS = 15
MAX_TENTATIVAS = 5
RECLAMACAO_EXPIRA = timedelta(minutes=5)
MAX_EVENTOS_GUARDADOS = 50

# tipo de notificação → categoria de preferência (ver `telegram_link.CATEGORIAS`)
CATEGORIA_DO_TIPO: dict[str, str] = {
    "process_assigned": "atribuicoes",
    "task_assigned": "atribuicoes",
    "portal_message": "portal",
    "visit_request": "portal",
    "visit_update": "portal",
    "chat_message": "chat",
    "index_conversa": "chat",
    "chat_group_message": "chat_grupo",
    "deadline_missed": "prazos_urgentes",
    "process_created": "estados",
    "new_process": "estados",
    "process_unassigned": "estados",
    "task_unassigned": "estados",
    "task_completed": "estados",
    "process_status_change": "estados",
    "status_change": "estados",
    "process_updated": "estados",
    "urgent": "estados",
    "automation": "estados",
    "valuation_alert": "estados",
    "valuation_below_purchase": "estados",
    "partner_note": "estados",
    "portal_email_undelivered": "estados",
    "email_failed": "estados",
    "document_upload": "documentos",
    "document_uploaded": "documentos",
    "document_verification": "documentos",
    "document_auto_fetch": "documentos",
    "indexing_complete": "documentos",
    "index_analysis_done": "documentos",
    "index_sanitize_done": "documentos",
    "deadline": "prazos",
    "deadline_reminder": "prazos",
    "deadline_approaching": "prazos",
    "event_reminder": "prazos",
    "pre_approval_countdown": "prazos",
    "deed_reminder": "prazos",
    "task_due_soon": "prazos",
    "task_due_tomorrow": "prazos",
    "task_due_today": "prazos",
    "task_overdue": "prazos",
}

# Texto fixo de cada tipo. Nunca o título da notificação: esse pode trazer o nome do cliente.
TITULO_DO_TIPO: dict[str, str] = {
    "process_assigned": "Processo atribuído a si",
    "process_created": "Processo novo",
    "new_process": "Processo novo",
    "process_unassigned": "Processo retirado",
    "task_assigned": "Tarefa nova atribuída a si",
    "task_unassigned": "Tarefa retirada",
    "task_completed": "Tarefa concluída",
    "process_status_change": "Mudança de estado",
    "status_change": "Mudança de estado",
    "process_updated": "Processo actualizado",
    "urgent": "Aviso urgente",
    "automation": "Aviso de automação",
    "valuation_alert": "Alerta de avaliação",
    "valuation_below_purchase": "Avaliação abaixo do valor de compra",
    "document_upload": "Documento novo",
    "document_uploaded": "Documento novo",
    "document_verification": "Documento para verificar",
    "document_auto_fetch": "Documento obtido automaticamente",
    "indexing_complete": "Indexação concluída",
    "index_analysis_done": "Análise do Index concluída",
    "index_sanitize_done": "Limpeza do Index concluída",
    "portal_message": "Mensagem nova do cliente no Portal",
    "visit_request": "Pedido de visita",
    "visit_update": "Visita alterada",
    "partner_note": "Nota nova do parceiro",
    "portal_email_undelivered": "Email do Portal não entregue",
    "email_failed": "Email não enviado",
    "deadline": "Prazo",
    "deadline_reminder": "Prazo a aproximar-se",
    "deadline_approaching": "Prazo a aproximar-se",
    "deadline_missed": "Prazo ultrapassado",
    "event_reminder": "Lembrete da agenda",
    "pre_approval_countdown": "Pré-aprovação a expirar",
    "deed_reminder": "Escritura a aproximar-se",
    "task_due_soon": "Tarefa a vencer",
    "task_due_tomorrow": "Tarefa vence amanhã",
    "task_due_today": "Tarefa vence hoje",
    "task_overdue": "Tarefa atrasada",
    "chat_message": "Mensagem nova no chat",
    "chat_group_message": "Mensagem nova num grupo",
    "index_conversa": "Mensagem nova do Index",
}


# Nunca vão para o Telegram, mesmo com a categoria ligada: o ruído, os avisos à gestão
# e os avisos automáticos de rotina (processos parados, documentos a expirar, lembrete
# mensal), que ficam só na app (Flavio, Nov 2026). O resto (pessoais vs. só a quem está
# atribuído) é a política comum, `notification_policy`.
TIPOS_SEM_TELEGRAM: frozenset[str] = TIPOS_RUIDO | frozenset({
    "new_registration",
    "clients_waiting",
    "process_stale",
    "process_urgent",
    "processos_parados",
    "processos_parados_gestao",
    "document_expiry",
    "document_expiry_watchdog",
    "documentos_a_expirar",
    "monthly_document_reminder",
})

#: Chave única do grupo: tudo o que chega a uma pessoa enquanto espera sai numa só mensagem.
CHAVE_DA_PESSOA = "pessoa"


def intervalo_minimo() -> timedelta:
    """No máximo uma mensagem por pessoa neste intervalo (15 min por omissão)."""
    try:
        segundos = int(os.environ.get("TELEGRAM_INTERVALO_MINIMO_SEGUNDOS", "900"))
    except ValueError:
        segundos = 900
    return timedelta(seconds=max(0, segundos))


def janela_de_agrupamento() -> timedelta:
    try:
        segundos = int(os.environ.get("TELEGRAM_JANELA_SEGUNDOS", "90"))
    except ValueError:
        segundos = 90
    return timedelta(seconds=max(0, segundos))


def categoria_de(tipo: str, *, urgente: bool = False) -> str:
    categoria = CATEGORIA_DO_TIPO.get(tipo or "", "outros")
    if urgente and categoria == "prazos":
        return "prazos_urgentes"
    return categoria


def titulo_de(tipo: str) -> str:
    return TITULO_DO_TIPO.get(tipo or "", "Aviso novo")


def chave_do_grupo(tipo: str, process_id: Optional[str], conversa: Optional[str]) -> str:
    """Um só grupo por pessoa (Flavio, Nov 2026: no máximo uma mensagem a cada 15 minutos,
    com tudo o que chegou). Os argumentos ficam para quem os passa."""
    return CHAVE_DA_PESSOA


def _com_fuso(valor) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, str) and valor:
        try:
            return _com_fuso(datetime.fromisoformat(valor.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _proximo_envio_permitido(ligacao: dict) -> Optional[datetime]:
    ultimo = _com_fuso((ligacao or {}).get("ultimo_envio_em"))
    return ultimo + intervalo_minimo() if ultimo else None


def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def agendar(
    user_id: str,
    tipo: str,
    *,
    process_id: Optional[str] = None,
    link: Optional[str] = None,
    conversa: Optional[str] = None,
    remetente: Optional[str] = None,
    urgente: bool = False,
) -> bool:
    """Põe um aviso na fila do Telegram, se a pessoa o quer receber. Nunca levanta.

    Devolve True quando o aviso entrou na fila.
    """
    try:
        if not user_id or not telegram_bot.telegram_configurado():
            return False
        ligacao = await telegram_link.ligacao_ativa(user_id)
        if not ligacao or not ligacao.get("chat_id"):
            return False

        # Só o que é da pessoa: avisos da gestão da rede sobre processos de outros
        # (registos novos, automações por cargo, processos parados) ficam na app.
        if tipo in TIPOS_SEM_TELEGRAM:
            return False
        if not await deve_notificar(user_id, tipo, process_id, canal="telegram", bd=db):
            return False

        categoria = categoria_de(tipo, urgente=urgente)
        preferencias = telegram_link.preferencias_efectivas(ligacao)
        if not preferencias.get(categoria, False):
            return False

        if ligacao.get("so_fora_da_app"):
            from services.presenca import esta_online

            if await esta_online(user_id):
                return False

        agora = _agora()
        evento = {
            "tipo": tipo,
            "categoria": categoria,
            "link": link if isinstance(link, str) and link.startswith("/") else None,
            "process_id": process_id,
            "remetente": remetente,
            "conversa": conversa,
            "em": agora,
        }
        enviar_apos = agora + janela_de_agrupamento()
        permitido = _proximo_envio_permitido(ligacao)
        if permitido and permitido > enviar_apos:
            enviar_apos = permitido
        filtro = {"user_id": user_id, "chave": chave_do_grupo(tipo, process_id, conversa), "status": "pendente"}
        atualizacao = {
            "$push": {"eventos": {"$each": [evento], "$slice": -MAX_EVENTOS_GUARDADOS}},
            "$inc": {"total": 1},
            "$set": {"atualizado_em": agora},
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "criado_em": agora,
                "enviar_apos": enviar_apos,
                "tentativas": 0,
            },
        }
        for _ in range(2):
            try:
                await db.telegram_outbox.update_one(filtro, atualizacao, upsert=True)
                return True
            except DuplicateKeyError:
                # Dois avisos em simultâneo abriram o mesmo grupo: o segundo junta-se ao primeiro.
                continue
        return False
    except Exception as erro:  # noqa: BLE001 - o Telegram nunca pode partir quem notifica
        logger.warning("[TELEGRAM] Não foi possível pôr o aviso na fila (%s): %s", user_id, erro)
        return False


async def agendar_de_notificacao(notificacao: dict) -> bool:
    """Atalho para quem grava directamente em `db.notifications`."""
    return await agendar(
        notificacao.get("user_id"),
        notificacao.get("type") or "info",
        process_id=notificacao.get("process_id"),
        link=notificacao.get("link"),
        urgente=bool(notificacao.get("urgente")),
    )


# ====================================================================
# Composição da mensagem
# ====================================================================

def _url_da_app(caminho: Optional[str]) -> str:
    base = (os.environ.get("FRONTEND_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}{caminho or '/'}"


async def _numero_do_processo(process_id: Optional[str]) -> str:
    if not process_id:
        return ""
    processo = await db.processes.find_one({"id": process_id}, {"_id": 0, "process_number": 1})
    numero = (processo or {}).get("process_number")
    return str(numero) if numero not in (None, "") else ""


async def compor(grupo: dict) -> tuple[str, str]:
    """Devolve (texto HTML, url do botão) do grupo: tudo o que chegou à pessoa."""
    # Grupos de antes de Nov 2026 (um por processo / conversa) guardavam o assunto no grupo.
    chave_antiga = grupo.get("chave") or ""
    eventos = [
        {
            **e,
            "process_id": e.get("process_id") or grupo.get("process_id"),
            "conversa": e.get("conversa") or (chave_antiga[5:] if chave_antiga.startswith("chat:") else None),
        }
        for e in (grupo.get("eventos") or [])
    ]
    total = int(grupo.get("total") or len(eventos) or 1)

    numeros: dict[str, str] = {}
    for evento in eventos:
        pid = evento.get("process_id")
        if pid and pid not in numeros:
            numeros[pid] = await _numero_do_processo(pid)

    def referencia(pid: Optional[str]) -> str:
        if not pid:
            return ""
        return f"processo nº {numeros[pid]}" if numeros.get(pid) else "um processo"

    processos = {e.get("process_id") for e in eventos if e.get("process_id")}
    links = [e.get("link") for e in eventos if e.get("link")]
    so_chat = bool(eventos) and all(e.get("conversa") for e in eventos)
    if so_chat:
        caminho = "/"
    elif len(processos) == 1 and all(e.get("process_id") for e in eventos):
        pid = next(iter(processos))
        caminho = next((l for l in reversed(links)), None) or f"/process/{pid}"
    elif len(set(links)) == 1 and len(links) == len(eventos):
        caminho = links[0]
    else:
        caminho = "/"

    def linha_do_chat(remetente: str, n: int, tipo: str) -> str:
        de = f" de {escape(remetente)}" if remetente else ""
        onde = "num grupo" if tipo == "chat_group_message" else "no chat"
        if n == 1:
            return f"Mensagem nova {onde}{de}"
        return f"{n} mensagens novas {onde}{de}"

    if total <= 1 and eventos:
        evento = eventos[0]
        if evento.get("conversa"):
            return f"💬 <b>{linha_do_chat(evento.get('remetente') or '', 1, evento.get('tipo'))}</b>", _url_da_app(caminho)
        texto = f"🔔 <b>{escape(titulo_de(evento.get('tipo')))}</b>"
        if evento.get("process_id"):
            texto += f"\n{referencia(evento.get('process_id')).capitalize()}"
        return texto, _url_da_app(caminho)

    contagem: Counter = Counter()
    ordem: list = []
    for evento in eventos:
        if evento.get("conversa"):
            chave = ("chat", evento.get("tipo"), evento.get("remetente") or "")
        else:
            chave = ("aviso", titulo_de(evento.get("tipo")), evento.get("process_id") or "")
        if chave not in contagem:
            ordem.append(chave)
        contagem[chave] += 1

    linhas = []
    for chave in ordem:
        n = contagem[chave]
        if chave[0] == "chat":
            linhas.append(f"• {linha_do_chat(chave[2], n, chave[1])}")
        else:
            onde = referencia(chave[2])
            linhas.append(
                f"• {escape(chave[1])}" + (f" — {onde}" if onde else "") + (f" (×{n})" if n > 1 else "")
            )
    if len(processos) == 1 and not any(e.get("conversa") for e in eventos):
        cabecalho = f"{total} novidades no {referencia(next(iter(processos)))}"
    else:
        cabecalho = f"{total} novidades"
    return f"🔔 <b>{cabecalho}</b>\n" + "\n".join(linhas), _url_da_app(caminho)


# ====================================================================
# Envio
# ====================================================================

async def _reclamar_proximo(agora: datetime) -> Optional[dict]:
    return await db.telegram_outbox.find_one_and_update(
        {
            "$or": [
                {"status": {"$in": ["pendente", "a_repetir"]}, "enviar_apos": {"$lte": agora}},
                {"status": "a_enviar", "reclamado_em": {"$lte": agora - RECLAMACAO_EXPIRA}},
            ]
        },
        {"$set": {"status": "a_enviar", "reclamado_em": agora}},
        sort=[("enviar_apos", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def _marcar(grupo: dict, campos: dict) -> None:
    await db.telegram_outbox.update_one({"id": grupo["id"]}, {"$set": campos})


async def _adiar(grupo: dict, quando: datetime) -> str:
    """Ainda não passou o intervalo mínimo desde a última mensagem: o grupo volta a esperar
    e continua a juntar avisos. Se entretanto abriu outro grupo pendente, junta-se a ele."""
    try:
        await db.telegram_outbox.update_one(
            {"id": grupo["id"]}, {"$set": {"status": "pendente", "enviar_apos": quando}}
        )
        return "adiado"
    except DuplicateKeyError:
        await db.telegram_outbox.update_one(
            {"user_id": grupo["user_id"], "chave": grupo.get("chave"), "status": "pendente"},
            {
                "$push": {"eventos": {"$each": grupo.get("eventos") or [], "$position": 0, "$slice": MAX_EVENTOS_GUARDADOS}},
                "$inc": {"total": int(grupo.get("total") or 0)},
                "$min": {"criado_em": grupo.get("criado_em") or _agora()},
                "$max": {"enviar_apos": quando},
            },
        )
        await _marcar(grupo, {"status": "fundido", "terminado_em": _agora()})
        return "adiado"


async def enviar_grupo(grupo: dict) -> str:
    """Envia um grupo já reclamado. Devolve o estado final."""
    agora = _agora()
    ligacao = await telegram_link.ligacao_ativa(grupo.get("user_id"))
    if not ligacao or not ligacao.get("chat_id"):
        await _marcar(grupo, {"status": "descartado", "motivo": "sem_ligacao", "terminado_em": agora})
        return "descartado"

    permitido = _proximo_envio_permitido(ligacao)
    if permitido and permitido > agora:
        return await _adiar(grupo, permitido)

    texto, url = await compor(grupo)
    resultado = await telegram_bot.enviar_mensagem(ligacao["chat_id"], texto, url_botao=url)

    if resultado.ok:
        await _marcar(grupo, {"status": "enviado", "terminado_em": agora})
        await db.telegram_links.update_one(
            {"user_id": grupo.get("user_id")}, {"$set": {"ultimo_envio_em": agora}}
        )
        return "enviado"
    if resultado.bloqueado:
        await telegram_link.desativar_por_bloqueio(grupo["user_id"])
        await _marcar(grupo, {"status": "descartado", "motivo": "bloqueado", "terminado_em": agora})
        return "descartado"
    if resultado.esperar:
        await _marcar(grupo, {"status": "a_repetir", "enviar_apos": agora + timedelta(seconds=resultado.esperar)})
        return "a_repetir"

    tentativas = int(grupo.get("tentativas") or 0) + 1
    if tentativas >= MAX_TENTATIVAS:
        await _marcar(grupo, {"status": "falhou", "tentativas": tentativas, "motivo": resultado.erro, "terminado_em": agora})
        logger.error("[TELEGRAM] Desisti do grupo %s: %s", grupo["id"], resultado.erro)
        return "falhou"
    await _marcar(grupo, {
        "status": "a_repetir",
        "tentativas": tentativas,
        "motivo": resultado.erro,
        "enviar_apos": agora + timedelta(seconds=30 * (2 ** tentativas)),
    })
    return "a_repetir"


async def enviar_pendentes(limite: int = 50) -> int:
    """Envia os grupos cuja janela já fechou. Devolve quantos tratou."""
    tratados = 0
    while tratados < limite:
        grupo = await _reclamar_proximo(_agora())
        if not grupo:
            break
        try:
            await enviar_grupo(grupo)
        except Exception as erro:  # noqa: BLE001 - um grupo não pode parar a fila
            logger.error("[TELEGRAM] Erro a enviar o grupo %s: %s", grupo.get("id"), erro)
            await _marcar(grupo, {"status": "a_repetir", "enviar_apos": _agora() + timedelta(minutes=1)})
        tratados += 1
        # O Telegram aceita ~30 mensagens/s no total; folga larga.
        await asyncio.sleep(0.05)
    return tratados


async def ciclo_de_envio() -> None:
    """Laço do processo web. Corre em todos os workers: a reclamação é atómica."""
    logger.info("📨 Envio de avisos para o Telegram activo (a cada %ss)", INTERVALO_DO_CICLO_SEGUNDOS)
    while True:
        try:
            await asyncio.sleep(INTERVALO_DO_CICLO_SEGUNDOS)
            await enviar_pendentes()
        except asyncio.CancelledError:
            raise
        except Exception as erro:  # noqa: BLE001
            logger.error("[TELEGRAM] Erro no ciclo de envio: %s", erro)
