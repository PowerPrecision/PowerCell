"""`call_openai_api` distingue «a resposta bateu no tecto de tokens» de «a IA não percebeu» (QA Index, Out 2026).

Um extrato BPI de um mês (50+ movimentos) passava os 4096 tokens: o JSON vinha cortado, o parse falhava e o
ficheiro ficava «Por analisar» com um alerta genérico. Agora o tecto é configurável por chamada e a resposta
cortada volta marcada (`truncated`), para o Index dizer o motivo certo.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import ai_document as modulo

FERRAMENTA = {"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}


def _cliente(argumentos: str, finish_reason: str):
    chamada = SimpleNamespace(function=SimpleNamespace(name="f", arguments=argumentos))
    resposta = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason, message=SimpleNamespace(tool_calls=[chamada], content=None))])
    cliente = MagicMock()
    cliente.chat.completions.create = AsyncMock(return_value=resposta)
    return cliente


@pytest.mark.asyncio
async def test_o_tecto_de_tokens_e_o_pedido_e_por_omissao_continua_4096():
    cliente = _cliente('{"a": 1}', "stop")
    with patch.object(modulo, "get_openai_client", return_value=cliente):
        await modulo.call_openai_api([], FERRAMENTA, model="m", max_tokens=16000)
        assert cliente.chat.completions.create.await_args.kwargs["max_tokens"] == 16000
        r = await modulo.call_openai_api([], FERRAMENTA, model="m")
    assert cliente.chat.completions.create.await_args.kwargs["max_tokens"] == 4096
    assert r["data"] == {"a": 1} and not r.get("truncated")


@pytest.mark.asyncio
async def test_resposta_cortada_volta_marcada_e_sem_dados():
    with patch.object(modulo, "get_openai_client", return_value=_cliente('{"movements": [{"amount": 1', "length")):
        r = await modulo.call_openai_api([], FERRAMENTA, model="m")
    assert r["truncated"] is True and r["data"] == {}
