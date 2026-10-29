"""
====================================================================
ROTAS TELEGRAM — thin FastAPI stubs
====================================================================
Lógica em services/telegram_link.py e services/telegram_notifications.py.
====================================================================
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from services import telegram_bot, telegram_link
from services.auth import get_current_user

router = APIRouter(prefix="/telegram", tags=["Telegram"])


class PreferenciasTelegram(BaseModel):
    preferencias: dict[str, bool] = {}
    so_fora_da_app: Optional[bool] = None


@router.get("/estado")
async def estado(current_user: dict = Depends(get_current_user)):
    """Estado da ligação do utilizador actual e as suas preferências."""
    return await telegram_link.run_estado(current_user)


@router.post("/ligar")
async def ligar(current_user: dict = Depends(get_current_user)):
    """Gera o link de uso único para ligar a conta ao bot."""
    return await telegram_link.run_criar_link(current_user)


@router.post("/desligar")
async def desligar(current_user: dict = Depends(get_current_user)):
    return await telegram_link.run_desligar(current_user)


@router.put("/preferencias")
async def atualizar_preferencias(
    corpo: PreferenciasTelegram,
    current_user: dict = Depends(get_current_user),
):
    return await telegram_link.run_atualizar_preferencias(
        current_user, corpo.preferencias, corpo.so_fora_da_app
    )


@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    """Recebe as actualizações do Telegram. Só aceita pedidos com o segredo combinado."""
    segredo = telegram_bot.segredo_do_webhook()
    if not segredo or not x_telegram_bot_api_secret_token or not secrets.compare_digest(
        segredo, x_telegram_bot_api_secret_token
    ):
        raise HTTPException(status_code=403, detail="Segredo inválido")
    try:
        atualizacao = await request.json()
    except ValueError:
        return {"ok": True}
    if isinstance(atualizacao, dict):
        await telegram_link.tratar_atualizacao(atualizacao)
    return {"ok": True}
