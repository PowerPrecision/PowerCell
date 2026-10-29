"""
====================================================================
CLIENTE DO BOT DO TELEGRAM
====================================================================
A única porta para a Bot API do Telegram. Tudo o resto (ligação de
contas, agrupamento, preferências) vive em `telegram_link` e
`telegram_notifications`.

Variáveis de ambiente:
- TELEGRAM_BOT_TOKEN: token dado pelo @BotFather. Sem ele, o canal
  Telegram fica desligado e nada é enviado (nem erro, nem fila).
- TELEGRAM_WEBHOOK_SECRET: segredo que o Telegram devolve no cabeçalho
  `X-Telegram-Bot-Api-Secret-Token` de cada actualização. O webhook
  rejeita tudo o que não o trouxer.
- TELEGRAM_WEBHOOK_URL (opcional): URL pública do webhook. Por omissão
  usa `RENDER_EXTERNAL_URL` + `/api/telegram/webhook`.
- TELEGRAM_BOT_USERNAME (opcional): evita o `getMe` para montar o link
  `t.me/<bot>?start=<código>`.
====================================================================
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT_SEGUNDOS = 10.0

_username_em_cache: Optional[str] = None


def token_do_bot() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def segredo_do_webhook() -> str:
    return (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()


def telegram_configurado() -> bool:
    return bool(token_do_bot())


def url_do_webhook() -> str:
    explicita = (os.environ.get("TELEGRAM_WEBHOOK_URL") or "").strip()
    if explicita:
        return explicita
    base = (os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    return f"{base}/api/telegram/webhook" if base else ""


@dataclass
class ResultadoDoEnvio:
    ok: bool
    # O destinatário bloqueou o bot ou apagou a conversa: não adianta repetir.
    bloqueado: bool = False
    # Pedido de espera do Telegram (429), em segundos.
    esperar: Optional[int] = None
    erro: str = ""


async def _chamar(metodo: str, dados: dict) -> dict:
    url = f"{API_BASE}/bot{token_do_bot()}/{metodo}"
    async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
        resposta = await cliente.post(url, json=dados)
    try:
        return resposta.json()
    except ValueError:
        return {"ok": False, "error_code": resposta.status_code, "description": resposta.text[:200]}


async def enviar_mensagem(chat_id: str | int, texto: str, *, url_botao: str = "", texto_botao: str = "Abrir no PowerCell") -> ResultadoDoEnvio:
    """Envia uma mensagem de texto simples (HTML) com um botão opcional."""
    if not telegram_configurado():
        return ResultadoDoEnvio(ok=False, erro="telegram_nao_configurado")

    dados: dict = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    # O Telegram só aceita botões com URL https (e nunca localhost).
    if url_botao.startswith("https://"):
        dados["reply_markup"] = {"inline_keyboard": [[{"text": texto_botao, "url": url_botao}]]}

    try:
        corpo = await _chamar("sendMessage", dados)
    except httpx.HTTPError as erro:
        return ResultadoDoEnvio(ok=False, erro=f"rede: {erro.__class__.__name__}")

    if corpo.get("ok"):
        return ResultadoDoEnvio(ok=True)

    codigo = corpo.get("error_code")
    descricao = str(corpo.get("description") or "")
    if codigo == 403 or (codigo == 400 and "chat not found" in descricao.lower()):
        return ResultadoDoEnvio(ok=False, bloqueado=True, erro=descricao)
    if codigo == 429:
        espera = (corpo.get("parameters") or {}).get("retry_after") or 30
        return ResultadoDoEnvio(ok=False, esperar=int(espera), erro=descricao)
    return ResultadoDoEnvio(ok=False, erro=f"{codigo}: {descricao}")


async def nome_do_bot() -> str:
    """Username do bot (sem @), para montar o link de ligação."""
    global _username_em_cache
    configurado = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if configurado:
        return configurado
    if _username_em_cache:
        return _username_em_cache
    if not telegram_configurado():
        return ""
    try:
        corpo = await _chamar("getMe", {})
    except httpx.HTTPError as erro:
        logger.warning("[TELEGRAM] getMe falhou: %s", erro)
        return ""
    _username_em_cache = ((corpo.get("result") or {}).get("username") or "").strip()
    return _username_em_cache


async def configurar_webhook() -> dict:
    """Regista o webhook no Telegram. Idempotente: pode correr em todos os arranques."""
    if not telegram_configurado():
        return {"ok": False, "motivo": "telegram_nao_configurado"}
    url = url_do_webhook()
    segredo = segredo_do_webhook()
    if not url or not segredo:
        return {"ok": False, "motivo": "falta_url_ou_segredo"}
    try:
        corpo = await _chamar(
            "setWebhook",
            {"url": url, "secret_token": segredo, "allowed_updates": ["message"]},
        )
    except httpx.HTTPError as erro:
        return {"ok": False, "motivo": f"rede: {erro.__class__.__name__}"}
    return {"ok": bool(corpo.get("ok")), "motivo": corpo.get("description", "")}
