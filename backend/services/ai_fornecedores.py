"""Vários fornecedores de IA, por ordem: quando um fica sem créditos, passa-se ao seguinte (Nov 2026).

O PEDIDO (Flavio): «Consigo ter mais que uma IA a trabalhar? Quando esgoto os créditos de uma IA, passa
para outra e assim sucessivamente.»

COMO
====
* Todas as chamadas ao modelo passam por `ai_document.call_openai_api`, no formato de chat da OpenAI
  (texto + `image_url` em base64 + function calling). A Google (Gemini) e a Anthropic (Claude) aceitam
  esse MESMO formato nos seus endpoints compatíveis com o SDK da OpenAI, por isso a troca é só de
  `base_url`, chave e modelo — os pedidos e o tratamento das respostas não mudam.
* A ordem é `openai → gemini → anthropic`, e entra quem tem chave configurada no Render:
  `OPENAI_API_KEY` (ou `EMERGENT_LLM_KEY`), `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`.
* `AI_FALLBACK_PROVIDERS` muda a ordem ou desliga a troca: `gemini,openai` (outra ordem), `openai`
  (só a OpenAI, sem troca), `none` (igual a `openai`).
* Modelos dos suplentes: `GEMINI_FALLBACK_MODEL` (omissão `gemini-2.5-flash`) e
  `ANTHROPIC_FALLBACK_MODEL` (omissão `claude-sonnet-5-5`). A OpenAI usa o modelo do painel de IA.
* Só se troca por FALTA DE CRÉDITOS. Um limite de pedidos (espera-se e repete-se), um timeout ou um
  erro do pedido não mudam de fornecedor: o mesmo documento num fornecedor diferente a cada tentativa
  tornava os resultados imprevisíveis.

PRIVACIDADE: os documentos dos clientes vão para o fornecedor que responder. Use chaves de contas
PAGAS (a Google usa os dados do plano gratuito para treino; o pago e a Anthropic não).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

OPENAI = "openai"
GEMINI = "gemini"
ANTHROPIC = "anthropic"
ORDEM_POR_OMISSAO = (OPENAI, GEMINI, ANTHROPIC)

NOME_PARA_O_ECRA = {OPENAI: "OpenAI", GEMINI: "Google Gemini", ANTHROPIC: "Anthropic Claude"}

_BASE_URL = {
    GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai/",
    ANTHROPIC: "https://api.anthropic.com/v1/",
}
_CHAVE = {GEMINI: "GEMINI_API_KEY", ANTHROPIC: "ANTHROPIC_API_KEY"}
_MODELO = {
    GEMINI: ("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash"),
    ANTHROPIC: ("ANTHROPIC_FALLBACK_MODEL", "claude-sonnet-5-5"),
}


@dataclass(frozen=True)
class Fornecedor:
    nome: str
    base_url: Optional[str] = None
    chave: Optional[str] = None  # None na OpenAI: o cliente canónico resolve a sua
    modelo: Optional[str] = None  # None na OpenAI: modelo do painel de IA


def _tem_chave(nome: str) -> bool:
    if nome == OPENAI:
        return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY"))
    return bool(os.environ.get(_CHAVE[nome]))


def ordem_configurada() -> list[str]:
    bruto = (os.environ.get("AI_FALLBACK_PROVIDERS") or "").strip().lower()
    if bruto in {"none", "nenhum", "off", "0"}:
        return [OPENAI]
    if not bruto:
        return list(ORDEM_POR_OMISSAO)
    vistos: list[str] = []
    for parte in bruto.split(","):
        nome = parte.strip()
        if nome in ORDEM_POR_OMISSAO and nome not in vistos:
            vistos.append(nome)
    return vistos or [OPENAI]


def fornecedores() -> list[Fornecedor]:
    """Os fornecedores a tentar, por ordem. A OpenAI entra sempre que está na ordem (é o caminho de sempre)."""
    lista: list[Fornecedor] = []
    for nome in ordem_configurada():
        if nome == OPENAI:
            lista.append(Fornecedor(OPENAI))
        elif _tem_chave(nome):
            var, omissao = _MODELO[nome]
            lista.append(Fornecedor(nome, _BASE_URL[nome], os.environ.get(_CHAVE[nome]),
                                    os.environ.get(var) or omissao))
    return lista


_clientes: dict[str, object] = {}


def cliente(fornecedor: Fornecedor):
    """Cliente `AsyncOpenAI` do fornecedor (cacheado). A OpenAI usa o construtor canónico."""
    if fornecedor.nome == OPENAI:
        from services.ai_document import get_openai_client

        return get_openai_client()
    existente = _clientes.get(fornecedor.nome)
    if existente is None:
        from openai import AsyncOpenAI

        existente = AsyncOpenAI(api_key=fornecedor.chave, base_url=fornecedor.base_url, max_retries=1)
        _clientes[fornecedor.nome] = existente
    return existente
