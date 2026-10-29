"""Telegram — regras puras (sem Mongo): categorias, chave do grupo, texto mínimo e o segredo do webhook."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from routes import telegram as rotas
from services import telegram_notifications as tn


def test_categorias_e_omissao():
    assert tn.categoria_de("process_assigned") == "atribuicoes"
    assert tn.categoria_de("portal_message") == "portal"
    assert tn.categoria_de("chat_message") == "chat"
    assert tn.categoria_de("tipo_que_ninguem_conhece") == "outros"


def test_chave_do_grupo():
    assert tn.chave_do_grupo("process_assigned", "p1", None) == "processo:p1"
    assert tn.chave_do_grupo("chat_message", "p1", "direta:u2") == "chat:direta:u2"
    assert tn.chave_do_grupo("task_assigned", None, None) == "tipo:task_assigned"


def _db_com_processo(numero):
    falso = MagicMock()
    falso.processes.find_one = AsyncMock(return_value={"process_number": numero})
    return falso


@pytest.mark.asyncio
async def test_mensagem_nao_leva_titulo_nem_dados_do_cliente(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://app.exemplo.pt")
    grupo = {
        "chave": "processo:p1",
        "process_id": "p1",
        "total": 1,
        # mesmo que um evento antigo trouxesse o título, a composição não o usa
        "eventos": [{"tipo": "document_upload", "titulo": "Recibo de João Silva", "link": "/processo/p1"}],
    }
    with patch.object(tn, "db", _db_com_processo(77)):
        texto, url = await tn.compor(grupo)
    assert "João" not in texto
    assert "Documento novo" in texto and "Processo nº 77" in texto
    assert url == "https://app.exemplo.pt/processo/p1"


@pytest.mark.asyncio
async def test_rajada_vira_uma_mensagem_geral(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    grupo = {
        "chave": "processo:p1",
        "process_id": "p1",
        "total": 3,
        "eventos": [{"tipo": "process_assigned"}, {"tipo": "status_change"}, {"tipo": "status_change"}],
    }
    with patch.object(tn, "db", _db_com_processo(12)):
        texto, url = await tn.compor(grupo)
    assert "3 novidades no processo nº 12" in texto
    assert "Mudança de estado (×2)" in texto
    assert url == ""  # sem FRONTEND_URL não há botão


@pytest.mark.asyncio
async def test_remetente_do_chat_e_escapado():
    grupo = {"chave": "chat:direta:u2", "total": 1, "eventos": [{"tipo": "chat_message", "remetente": "<b>Ana</b>"}]}
    texto, _ = await tn.compor(grupo)
    assert "&lt;b&gt;Ana&lt;/b&gt;" in texto


@pytest.mark.asyncio
async def test_agendar_sem_bot_configurado_nao_faz_nada(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert await tn.agendar("u1", "process_assigned", process_id="p1") is False


@pytest.mark.asyncio
async def test_webhook_recusa_sem_o_segredo(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3gredo")
    app = FastAPI()
    app.include_router(rotas.router, prefix="/api")
    tratar = AsyncMock()
    with patch.object(rotas.telegram_link, "tratar_atualizacao", tratar):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
            sem = await cliente.post("/api/telegram/webhook", json={"message": {}})
            errado = await cliente.post(
                "/api/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "outro"}
            )
            certo = await cliente.post(
                "/api/telegram/webhook", json={"message": {}}, headers={"X-Telegram-Bot-Api-Secret-Token": "s3gredo"}
            )
    assert sem.status_code == 403 and errado.status_code == 403
    assert certo.status_code == 200
    tratar.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_fechado_quando_nao_ha_segredo(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    app = FastAPI()
    app.include_router(rotas.router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.post(
            "/api/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": ""}
        )
    assert resposta.status_code == 403
