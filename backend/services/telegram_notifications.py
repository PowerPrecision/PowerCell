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

logger = logging.getLogger(__name__)

INTERVALO_DO_CICLO_SEGUNDOS = 15
MAX_TENTATIVAS = 5
RECLAMACAO_EXPIRA = timedelta(minutes=5)
MAX_EVENTOS_GUARDADOS = 50

# tipo de notificação → categoria de preferência
CATEGORIA_DO_TIPO: dict[str, str] = {
    "process_assigned": "atribuicoes",
    "process_created": "atribuicoes",
    "new_process": "atribuicoes",
    "task_assigned": "atribuicoes",
    "task_unassigned": "atribuicoes",
    "task_completed": "atribuicoes",
    "clients_waiting": "atribuicoes",
    "new_registration": "atribuicoes",
    "process_status_change": "estados",
    "status_change": "estados",
    "process_updated": "estados",
    "process_urgent": "estados",
    "urgent": "estados",
    "process_stale": "estados",
    "automation": "estados",
    "valuation_alert": "estados",
    "valuation_below_purchase": "estados",
    "document_upload": "documentos",
    "document_uploaded": "documentos",
    "document_verification": "documentos",
    "document_auto_fetch": "documentos",
    "indexing_complete": "documentos",
    "index_analysis_done": "documentos",
    "index_sanitize_done": "documentos",
    "portal_message": "portal",
    "visit_request": "portal",
    "visit_update": "portal",
    "partner_note": "portal",
    "portal_email_undelivered": "portal",
    "email_failed": "portal",
    "deadline": "prazos",
    "deadline_reminder": "prazos",
    "deadline_approaching": "prazos",
    "deadline_missed": "prazos",
    "event_reminder": "prazos",
    "pre_approval_countdown": "prazos",
    "document_expiry": "prazos",
    "document_expiry_watchdog": "prazos",
    "monthly_document_reminder": "prazos",
    "deed_reminder": "prazos",
    "chat_message": "chat",
    "index_conversa": "chat",
}

# Texto fixo de cada tipo. Nunca o título da notificação: esse pode trazer o nome do cliente.
TITULO_DO_TIPO: dict[str, str] = {
    "process_assigned": "Processo atribuído a si",
    "process_created": "Processo novo",
    "new_process": "Processo novo",
    "task_assigned": "Tarefa nova atribuída a si",
    "task_unassigned": "Tarefa retirada",
    "task_completed": "Tarefa concluída",
    "clients_waiting": "Clientes à espera",
    "new_registration": "Registo novo de cliente",
    "process_status_change": "Mudança de estado",
    "status_change": "Mudança de estado",
    "process_updated": "Processo actualizado",
    "process_urgent": "Processo marcado como urgente",
    "urgent": "Aviso urgente",
    "process_stale": "Processo parado",
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
    "document_expiry": "Documento a expirar",
    "document_expiry_watchdog": "Documento a expirar",
    "monthly_document_reminder": "Lembrete mensal de documentos",
    "deed_reminder": "Escritura a aproximar-se",
    "chat_message": "Mensagem nova no chat",
    "index_conversa": "Mensagem nova do Index",
}


# Avisos dirigidos À PESSOA (a tarefa é dela, o prazo é dela): passam mesmo sem ser
# atribuída ao processo. Tudo o resto que traga processo só passa a quem lá está atribuído.
TIPOS_PESSOAIS: frozenset[str] = frozenset({
    "task_assigned",
    "task_unassigned",
    "task_completed",
    "deadline",
    "deadline_reminder",
    "deadline_approaching",
    "deadline_missed",
    "event_reminder",
    "chat_message",
    "index_conversa",
})

# Ruído: nunca vão para o Telegram, mesmo com a categoria ligada.
TIPOS_SEM_TELEGRAM: frozenset[str] = frozenset({
    "process_updated",       # «alguém mexeu no processo», sem dizer o quê
    "index_sanitize_done",   # manutenção do Index
    "document_auto_fetch",   # recolha automática, sem acção pedida
    "new_registration",      # avisos à gestão da rede, não ao responsável
    "clients_waiting",
})


async def _atribuido_ao_processo(user_id: str, process_id: str) -> bool:
    """O utilizador está atribuído ao processo (consultor, intermediário, Index…)?"""
    from services.alert_audience import ids_atribuidos

    processo = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0}
    )
    return bool(processo) and user_id in ids_atribuidos(processo)


def janela_de_agrupamento() -> timedelta:
    try:
        segundos = int(os.environ.get("TELEGRAM_JANELA_SEGUNDOS", "90"))
    except ValueError:
        segundos = 90
    return timedelta(seconds=max(0, segundos))


def categoria_de(tipo: str) -> str:
    return CATEGORIA_DO_TIPO.get(tipo or "", "outros")


def titulo_de(tipo: str) -> str:
    return TITULO_DO_TIPO.get(tipo or "", "Aviso novo")


def chave_do_grupo(tipo: str, process_id: Optional[str], conversa: Optional[str]) -> str:
    if conversa:
        return f"chat:{conversa}"
    if process_id:
        return f"processo:{process_id}"
    return f"tipo:{tipo or 'info'}"


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
        if tipo not in TIPOS_PESSOAIS:
            if not process_id or not await _atribuido_ao_processo(user_id, process_id):
                return False

        categoria = categoria_de(tipo)
        preferencias = {**telegram_link.preferencias_por_defeito(), **(ligacao.get("preferencias") or {})}
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
            "em": agora,
        }
        filtro = {"user_id": user_id, "chave": chave_do_grupo(tipo, process_id, conversa), "status": "pendente"}
        atualizacao = {
            "$push": {"eventos": {"$each": [evento], "$slice": -MAX_EVENTOS_GUARDADOS}},
            "$inc": {"total": 1},
            "$set": {"atualizado_em": agora},
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "criado_em": agora,
                "enviar_apos": agora + janela_de_agrupamento(),
                "tentativas": 0,
                "process_id": process_id,
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
    """Devolve (texto HTML, url do botão) do grupo."""
    eventos = grupo.get("eventos") or []
    total = int(grupo.get("total") or len(eventos) or 1)
    chave = grupo.get("chave") or ""
    process_id = grupo.get("process_id")
    numero = await _numero_do_processo(process_id)
    referencia = f"processo nº {numero}" if numero else "um processo"

    if chave.startswith("chat:"):
        remetente = next((e.get("remetente") for e in reversed(eventos) if e.get("remetente")), "")
        de = f" de {escape(remetente)}" if remetente else ""
        if total == 1:
            texto = f"💬 <b>Mensagem nova no chat{de}</b>"
        else:
            texto = f"💬 <b>{total} mensagens novas no chat{de}</b>"
        return texto, _url_da_app("/")

    caminho = next((e.get("link") for e in reversed(eventos) if e.get("link")), None)
    if not caminho and process_id:
        caminho = f"/process/{process_id}"

    if total <= 1:
        titulo = escape(titulo_de(eventos[0].get("tipo") if eventos else ""))
        texto = f"🔔 <b>{titulo}</b>"
        if process_id:
            texto += f"\n{referencia.capitalize()}"
        return texto, _url_da_app(caminho)

    if chave.startswith("processo:"):
        contagem = Counter(titulo_de(e.get("tipo")) for e in eventos)
        linhas = [
            f"• {escape(titulo)}" + (f" (×{n})" if n > 1 else "")
            for titulo, n in contagem.most_common()
        ]
        texto = f"🔔 <b>{total} novidades no {referencia}</b>\n" + "\n".join(linhas)
        return texto, _url_da_app(caminho)

    titulo = escape(titulo_de(eventos[-1].get("tipo") if eventos else ""))
    return f"🔔 <b>{titulo}</b> (×{total})", _url_da_app(caminho)


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


async def enviar_grupo(grupo: dict) -> str:
    """Envia um grupo já reclamado. Devolve o estado final."""
    agora = _agora()
    ligacao = await telegram_link.ligacao_ativa(grupo.get("user_id"))
    if not ligacao or not ligacao.get("chat_id"):
        await _marcar(grupo, {"status": "descartado", "motivo": "sem_ligacao", "terminado_em": agora})
        return "descartado"

    texto, url = await compor(grupo)
    resultado = await telegram_bot.enviar_mensagem(ligacao["chat_id"], texto, url_botao=url)

    if resultado.ok:
        await _marcar(grupo, {"status": "enviado", "terminado_em": agora})
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
