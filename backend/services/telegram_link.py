"""
====================================================================
LIGAÇÃO DE CONTAS AO TELEGRAM
====================================================================
Como uma pessoa liga a sua conta do PowerCell ao bot:

1. Em Definições › Notificações carrega em «Ligar Telegram». O backend
   cria um código de uso único (10 minutos) e devolve o link
   `https://t.me/<bot>?start=<código>`.
2. No Telegram carrega em «Iniciar». O Telegram envia `/start <código>`
   ao webhook, que consome o código e guarda o `chat_id` da conversa.
3. «Desligar» na app, ou `/parar` no Telegram, desliga (soft: `ativo`
   passa a False e o `chat_id` é esquecido).

Nunca pedimos o número de telefone. O código guarda-se só como hash.
====================================================================
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import db
from services import telegram_bot

logger = logging.getLogger(__name__)

VALIDADE_DO_CODIGO = timedelta(minutes=10)

# Categorias que a pessoa escolhe receber. A ordem é a do ecrã.
CATEGORIAS: dict[str, dict] = {
    "atribuicoes": {"label": "Processos e tarefas atribuídos a mim", "defeito": True},
    "estados": {"label": "Mudanças de estado nos meus processos", "defeito": True},
    "documentos": {"label": "Documentos novos e indexação", "defeito": True},
    "portal": {"label": "Mensagens e pedidos do Portal do Cliente", "defeito": True},
    "prazos": {"label": "Prazos, escrituras e documentos a expirar", "defeito": True},
    "chat": {"label": "Mensagens novas no chat", "defeito": True},
    "outros": {"label": "Outros avisos do sistema", "defeito": False},
}

TEXTO_DE_AJUDA = (
    "Este é o bot de avisos do PowerCell.\n\n"
    "Para ligar a sua conta, abra o PowerCell em Definições › Notificações "
    "e carregue em «Ligar Telegram».\n"
    "Para deixar de receber avisos, envie /parar."
)


def preferencias_por_defeito() -> dict:
    return {chave: info["defeito"] for chave, info in CATEGORIAS.items()}


def _hash(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def ligacao_ativa(user_id: str) -> Optional[dict]:
    if not user_id:
        return None
    return await db.telegram_links.find_one({"user_id": user_id, "ativo": True}, {"_id": 0})


async def run_estado(user: dict) -> dict:
    ligacao = await db.telegram_links.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    preferencias = {**preferencias_por_defeito(), **(ligacao.get("preferencias") or {})}
    return {
        "configurado": telegram_bot.telegram_configurado(),
        "ligado": bool(ligacao.get("ativo")),
        "ligado_em": ligacao.get("ligado_em") if ligacao.get("ativo") else None,
        "so_fora_da_app": bool(ligacao.get("so_fora_da_app", False)),
        "preferencias": preferencias,
        "categorias": [{"chave": c, "label": i["label"]} for c, i in CATEGORIAS.items()],
    }


async def run_criar_link(user: dict) -> dict:
    """Cria um código de uso único e devolve o link para o bot."""
    if not telegram_bot.telegram_configurado():
        return {"ok": False, "motivo": "O Telegram ainda não está configurado no servidor."}
    nome = await telegram_bot.nome_do_bot()
    if not nome:
        return {"ok": False, "motivo": "Não foi possível contactar o bot do Telegram."}

    codigo = secrets.token_urlsafe(24)
    await db.telegram_link_tokens.insert_one({
        "token_hash": _hash(codigo),
        "user_id": user["id"],
        "usado": False,
        "expira_em": _agora() + VALIDADE_DO_CODIGO,
        "criado_em": _agora(),
    })
    return {
        "ok": True,
        "url": f"https://t.me/{nome}?start={codigo}",
        "expira_em_minutos": int(VALIDADE_DO_CODIGO.total_seconds() // 60),
    }


async def run_desligar(user: dict) -> dict:
    await db.telegram_links.update_one(
        {"user_id": user["id"]},
        {"$set": {"ativo": False, "chat_id": None, "desligado_em": _agora().isoformat()}},
    )
    return {"ok": True}


async def run_atualizar_preferencias(user: dict, preferencias: dict, so_fora_da_app: Optional[bool]) -> dict:
    campos: dict = {}
    for chave, valor in (preferencias or {}).items():
        if chave in CATEGORIAS:
            campos[f"preferencias.{chave}"] = bool(valor)
    if so_fora_da_app is not None:
        campos["so_fora_da_app"] = bool(so_fora_da_app)
    if campos:
        await db.telegram_links.update_one(
            {"user_id": user["id"]},
            {"$set": campos, "$setOnInsert": {"ativo": False}},
            upsert=True,
        )
    return await run_estado(user)


async def _ligar(chat_id: int, codigo: str) -> str:
    agora = _agora()
    token = await db.telegram_link_tokens.find_one_and_update(
        {"token_hash": _hash(codigo), "usado": False, "expira_em": {"$gt": agora}},
        {"$set": {"usado": True, "usado_em": agora}},
    )
    if not token:
        return (
            "Este link já foi usado ou expirou. Volte a carregar em «Ligar Telegram» "
            "no PowerCell para gerar um novo."
        )

    user_id = token["user_id"]
    # Uma conversa do Telegram serve uma só conta: se já estava ligada a outra, essa sai.
    await db.telegram_links.update_many(
        {"chat_id": chat_id, "user_id": {"$ne": user_id}},
        {"$set": {"ativo": False, "chat_id": None, "desligado_em": agora.isoformat()}},
    )
    await db.telegram_links.update_one(
        {"user_id": user_id},
        {
            "$set": {"chat_id": chat_id, "ativo": True, "ligado_em": agora.isoformat()},
            "$setOnInsert": {"preferencias": preferencias_por_defeito(), "so_fora_da_app": False},
        },
        upsert=True,
    )
    logger.info("[TELEGRAM] Conta %s ligada ao Telegram", user_id)
    return (
        "✅ Conta ligada. A partir de agora recebe aqui os avisos do PowerCell.\n"
        "Pode escolher que avisos recebe em Definições › Notificações. "
        "Para deixar de receber, envie /parar."
    )


async def _desligar_por_chat(chat_id: int) -> str:
    resultado = await db.telegram_links.update_many(
        {"chat_id": chat_id, "ativo": True},
        {"$set": {"ativo": False, "chat_id": None, "desligado_em": _agora().isoformat()}},
    )
    if resultado.modified_count:
        return "Deixou de receber avisos do PowerCell aqui. Pode voltar a ligar em Definições › Notificações."
    return "Esta conversa não está ligada a nenhuma conta do PowerCell."


async def desativar_por_bloqueio(user_id: str) -> None:
    """O destinatário bloqueou o bot: a ligação deixa de valer."""
    await db.telegram_links.update_one(
        {"user_id": user_id},
        {"$set": {"ativo": False, "chat_id": None, "desligado_em": _agora().isoformat(), "motivo": "bloqueado"}},
    )


async def tratar_atualizacao(atualizacao: dict) -> None:
    """Trata uma actualização vinda do webhook. Nunca levanta."""
    mensagem = atualizacao.get("message") or {}
    chat = mensagem.get("chat") or {}
    chat_id = chat.get("id")
    texto = (mensagem.get("text") or "").strip()
    if not chat_id or chat.get("type") != "private":
        return

    try:
        comando, _, argumento = texto.partition(" ")
        comando = comando.split("@", 1)[0].lower()
        if comando == "/start" and argumento.strip():
            resposta = await _ligar(chat_id, argumento.strip())
        elif comando in ("/parar", "/stop"):
            resposta = await _desligar_por_chat(chat_id)
        else:
            resposta = TEXTO_DE_AJUDA
        await telegram_bot.enviar_mensagem(chat_id, resposta)
    except Exception as erro:  # noqa: BLE001 - o webhook responde sempre 200 ao Telegram
        logger.error("[TELEGRAM] Erro a tratar actualização: %s", erro)
