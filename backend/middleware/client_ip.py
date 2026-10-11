"""
====================================================================
O IP REAL DO CLIENTE — contado a partir da DIREITA (D-4, Out 2026)
====================================================================
O PROBLEMA
  O `_get_client_ip` lia o PRIMEIRO elemento do `X-Forwarded-For`. Esse é o
  elemento que o CLIENTE envia: cada proxy acrescenta o que viu ao FIM da
  lista. Quem ataca mudava-o a cada pedido e o limite por IP (login por
  email, registo público, magic link — tudo o que é pré-autenticação e não
  tem JWT de onde tirar uma identidade) nunca mordia. Era o placebo do
  `build_company_scope_condition`: a verificação corre, parece fechada, e o
  valor que compara é escolhido por quem se quer verificar.

A REGRA
  `TRUSTED_PROXY_HOPS` = quantos proxies NOSSOS estão entre a internet e o
  backend. O IP em que se confia é o elemento que o proxy MAIS PRÓXIMO da
  internet acrescentou: o `hops`-ésimo a contar do fim.

    hops = 1 (Render sozinho):      XFF = "<forjado>, <real>"       → <real>
    hops = 2 (Cloudflare + Render): XFF = "<forjado>, <real>, <cf>" → <real>

  Tudo à esquerda do elemento de confiança é do cliente e é ignorado.

  * **Por omissão 1** — o deploy actual é o Render, com um proxy à frente do
    backend (decisão do dono do produto). Um valor inválido volta ao 1 com
    `warning`; `0` é legítimo e quer dizer «sem proxy» (o cabeçalho é todo
    do cliente e ignora-se: usa-se o peer do socket).
  * **Lista mais curta do que `hops`** → o cabeçalho não passou pelos
    proxies que dizemos ter (pedido directo ao serviço, ou topologia
    errada). Não se adivinha: usa-se o peer do socket, que não é
    falsificável.
  * **O elemento tem de ser um IP** — texto livre num cabeçalho de que
    depende uma chave de limite é uma chave que o cliente escolhe.
  * **`X-Real-IP` NÃO se lê**: é igualmente um cabeçalho do cliente e nenhum
    dos nossos proxies o garante.

O QUE CORRE MAL SE `TRUSTED_PROXY_HOPS` ESTIVER ERRADO
  * Demasiado BAIXO (1 com Cloudflare à frente): a chave passa a ser o IP do
    Cloudflare e os clientes todos colapsam num só — o limite tranca o
    sistema. É o motivo para a variável existir e ser explícita.
  * Demasiado ALTO: cai no peer (ver acima), com o mesmo colapso.
  Em ambos os casos o limite falha FECHADO (agrupa), nunca ABERTO (deixar
  forjar), que é o sentido seguro.
====================================================================
"""
from __future__ import annotations

import ipaddress
import logging
import os
from typing import Optional

from starlette.requests import Request

logger = logging.getLogger(__name__)

ENV_DOS_PROXIES = "TRUSTED_PROXY_HOPS"
PROXIES_POR_OMISSAO = 1
SEM_IP = "unknown"


def proxies_de_confianca() -> int:
    """Quantos proxies nossos precedem o backend. Lido a cada pedido."""
    bruto = os.environ.get(ENV_DOS_PROXIES)
    if bruto is None or not str(bruto).strip():
        return PROXIES_POR_OMISSAO
    try:
        valor = int(str(bruto).strip())
    except ValueError:
        valor = -1
    if valor < 0:
        logger.warning(
            "[CLIENT-IP] %s=%r não é um inteiro >= 0; a usar %d.",
            ENV_DOS_PROXIES, bruto, PROXIES_POR_OMISSAO,
        )
        return PROXIES_POR_OMISSAO
    return valor


def _e_ip(texto: str) -> bool:
    try:
        ipaddress.ip_address(texto)
        return True
    except ValueError:
        return False


def _peer(request: Request) -> str:
    cliente = getattr(request, "client", None)
    host = getattr(cliente, "host", None) if cliente else None
    return host if isinstance(host, str) and host else SEM_IP


def _elementos_do_encaminhamento(request: Request) -> list[str]:
    """Todos os elementos do `X-Forwarded-For`, pela ordem em que chegaram.

    Um cliente pode mandar o cabeçalho repetido; os proxies acrescentam ao
    fim da última ocorrência (ou como ocorrência nova), logo a junção pela
    ordem recebida preserva «o último é o mais recente».
    """
    try:
        headers = request.headers
        if hasattr(headers, "getlist"):
            brutos = list(headers.getlist("x-forwarded-for"))
        else:
            # Um mapeamento simples (testes, ASGI crus): as chaves não são
            # insensíveis a maiúsculas como as do Starlette.
            brutos = [
                valor for chave, valor in dict(headers).items()
                if str(chave).lower() == "x-forwarded-for"
            ]
    except Exception:
        return []
    elementos: list[str] = []
    for bruto in brutos:
        if not isinstance(bruto, str):
            continue
        elementos.extend(p.strip() for p in bruto.split(","))
    return [e for e in elementos if e]


def ip_do_cliente(request: Request, proxies: Optional[int] = None) -> str:
    """O IP do cliente em que se pode confiar (ver o módulo)."""
    hops = proxies_de_confianca() if proxies is None else proxies
    if hops <= 0:
        return _peer(request)

    elementos = _elementos_do_encaminhamento(request)
    if len(elementos) < hops:
        return _peer(request)

    candidato = elementos[-hops]
    return candidato if _e_ip(candidato) else _peer(request)


__all__ = ["ENV_DOS_PROXIES", "PROXIES_POR_OMISSAO", "ip_do_cliente", "proxies_de_confianca"]
