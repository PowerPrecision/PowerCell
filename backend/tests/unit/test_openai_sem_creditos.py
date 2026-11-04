"""Conta OpenAI sem créditos ≠ limite de pedidos (logs do Render, Nov 2026).

A OpenAI responde 429 aos dois. O limite passa com espera; o «sem créditos» (`insufficient_quota` /
`credit_balance_exhausted`) só passa quando alguém carregar créditos. Antes: 5 tentativas com backoff por
pedido, um `RetryError` no fim e o Index a ver «A IA não conseguiu analisar este documento». Agora: falha
logo, os pedidos seguintes nem saem durante uns minutos, e o motivo dito é `sem_creditos`.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tenacity import RetryError, wait_none

from services import ai_document as modulo
from services.process_ai_log import MOTIVOS, classificar_falha

FERRAMENTA = {"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}
ERRO_SEM_CREDITOS = (
    "Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the "
    "API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', "
    "'param': None, 'code': 'credit_balance_exhausted'}}"
)


@pytest.fixture(autouse=True)
def _sem_pausa():
    modulo._sem_creditos_desde = None
    with patch("services.ai_disponibilidade.registar_sem_creditos", AsyncMock()), \
         patch("services.ai_disponibilidade.registar_resposta_ok", AsyncMock()):
        yield
    modulo._sem_creditos_desde = None


def _cliente(*efeitos):
    cliente = MagicMock()
    cliente.chat.completions.create = AsyncMock(side_effect=list(efeitos))
    return cliente


def _resposta_ok():
    chamada = SimpleNamespace(function=SimpleNamespace(name="f", arguments='{"a": 1}'))
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(tool_calls=[chamada], content=None))])


@pytest.mark.asyncio
async def test_sem_creditos_falha_a_primeira_sem_novas_tentativas():
    cliente = _cliente(Exception(ERRO_SEM_CREDITOS), _resposta_ok())
    with patch.object(modulo, "get_openai_client", return_value=cliente):
        with pytest.raises(modulo.SemCreditosError) as erro:
            await modulo.call_openai_api([], FERRAMENTA, model="m")
    assert cliente.chat.completions.create.await_count == 1
    assert classificar_falha(erro.value) == "sem_creditos"


@pytest.mark.asyncio
async def test_depois_de_sem_creditos_os_pedidos_seguintes_nem_saem():
    cliente = _cliente(Exception(ERRO_SEM_CREDITOS), _resposta_ok())
    with patch.object(modulo, "get_openai_client", return_value=cliente):
        with pytest.raises(modulo.SemCreditosError):
            await modulo.call_openai_api([], FERRAMENTA, model="m")
        with pytest.raises(modulo.SemCreditosError):
            await modulo.call_openai_api([], FERRAMENTA, model="m")
        assert cliente.chat.completions.create.await_count == 1
        # passada a pausa, volta a tentar — e uma resposta boa limpa o estado
        modulo._sem_creditos_desde -= modulo.PAUSA_SEM_CREDITOS + 1
        r = await modulo.call_openai_api([], FERRAMENTA, model="m")
    assert r["data"] == {"a": 1} and modulo._sem_creditos_desde is None


@pytest.mark.asyncio
async def test_limite_de_pedidos_continua_a_repetir_e_levanta_o_erro_verdadeiro():
    erro = Exception("Error code: 429 - Rate limit reached for requests")
    cliente = _cliente(*([erro] * modulo.RETRY_MAX_ATTEMPTS))
    sem_espera = modulo.call_openai_api.retry_with(wait=wait_none())
    with patch.object(modulo, "get_openai_client", return_value=cliente):
        with pytest.raises(modulo.RateLimitError) as apanhado:  # não um RetryError opaco
            await sem_espera([], FERRAMENTA, model="m")
    assert cliente.chat.completions.create.await_count == modulo.RETRY_MAX_ATTEMPTS
    assert classificar_falha(apanhado.value) == "limite_do_fornecedor"


def test_classificar_um_retry_error_olha_para_o_erro_de_dentro():
    tentativa = SimpleNamespace(exception=lambda: modulo.RateLimitError("Rate limit: 429"))
    assert classificar_falha(RetryError(tentativa)) == "limite_do_fornecedor"


def test_ha_mensagem_para_o_ecra():
    assert "créditos" in MOTIVOS["sem_creditos"]
