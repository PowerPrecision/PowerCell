"""
Testes unitários — um endpoint com `@limiter.limit` tem de poder devolver 200.

O DEFEITO (produção, Set 2026) — 500 SÓ no caminho de SUCESSO
=============================================================
O `POST /api/portal/upload-url` respondia **500** a todos os clientes do
Portal, com esta excepção:

    Exception: parameter `response` must be an instance of
    starlette.responses.Response
      slowapi/extension.py:382, em _inject_headers

O limiter deste projecto é criado com ``headers_enabled=True``
(`middleware/rate_limit.py`), o que faz o slowapi acrescentar os
cabeçalhos ``X-RateLimit-*`` DEPOIS de o handler devolver. Para isso ele
precisa de um objecto `Response`, e procura-o em dois sítios, por esta
ordem (ver `slowapi/extension.py::async_wrapper`):

  1. o VALOR DEVOLVIDO, se já for uma `Response`;
  2. o parâmetro chamado ``response`` da assinatura do endpoint, que o
     FastAPI injecta quando declarado.

Um endpoint que devolva um ``dict`` (ou um modelo Pydantic) e NÃO declare
``response: Response`` não tem nenhum dos dois: o slowapi levanta, e o
que o cliente recebe é 500.

PORQUE É QUE A BATERIA INTEIRA FICOU VERDE
  A injecção de cabeçalhos corre **apenas quando o handler devolve**. Num
  caminho de erro (403, 404, 503, 429) a excepção sobe antes e o defeito
  não aparece. O `test_portal_upload_path_traversal.py` é, por desenho,
  uma bateria de REJEIÇÕES — provava o ataque fechado e nunca provou que
  um upload legítimo funcionava. Três endpoints do Portal ficaram
  inutilizáveis sem um único teste vermelho.

  É a mesma forma do `build_company_scope_condition`: cada camada
  validava, a combinação não. E é a terceira vez que "só o caminho felizes
  está descoberto" — daí a guarda de INVENTÁRIO no fim deste ficheiro, que
  falha por omissão para qualquer endpoint limitado que apareça a seguir.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address


RAIZ_DAS_ROTAS = Path(__file__).resolve().parents[2] / "routes"

# Os nomes que este projecto usa para limitar um endpoint. `limiter.limit`
# é o caso directo; os `limit_*` são os atalhos de `middleware/rate_limit`.
DECORADORES_DE_LIMITE = {
    "limit",          # @limiter.limit("20/minute")
    "limit_auth",
    "limit_write",
    "limit_read",
    "limit_upload",
    "limit_public",
    "limit_ai",
}


# ====================================================================
# 1. O MECANISMO — com um limiter REAL, não com um duplo
# ====================================================================
# Um duplo do slowapi reimplementaria exactamente a lógica que falhou
# (a escolha do objecto onde injectar), e validaria o duplo. Estes dois
# testes montam o `Limiter` verdadeiro, com `headers_enabled=True` como
# em produção, e medem a diferença que a assinatura faz.


def _app_com_limiter(declara_response: bool) -> FastAPI:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[],
        headers_enabled=True,
        strategy="fixed-window",
    )
    app = FastAPI()
    app.state.limiter = limiter

    if declara_response:

        @app.post("/coisa")
        @limiter.limit("20/minute")
        async def com_response(request: Request, response: Response):
            return {"success": True}

    else:

        @app.post("/coisa")
        @limiter.limit("20/minute")
        async def sem_response(request: Request):
            return {"success": True}

    return app


def test_sem_response_na_assinatura_o_sucesso_devolve_500():
    """A contraprova: sem `response`, devolver um dict rebenta.

    Este teste é o defeito de produção reduzido ao mínimo. Se algum dia
    ficar verde (uma versão do slowapi que deixe de levantar), a regra
    deste ficheiro deixa de ser necessária — e é melhor descobri-lo aqui
    do que por um 500 num cliente.
    """
    cliente = TestClient(_app_com_limiter(declara_response=False), raise_server_exceptions=False)
    resposta = cliente.post("/coisa")
    assert resposta.status_code == 500


def test_com_response_na_assinatura_o_sucesso_devolve_200_e_os_cabecalhos():
    cliente = TestClient(_app_com_limiter(declara_response=True))
    resposta = cliente.post("/coisa")

    assert resposta.status_code == 200
    assert resposta.json() == {"success": True}
    # Os cabeçalhos são o motivo de o slowapi precisar do objecto: se
    # faltarem, o `response` declarado não está a ser usado e o teste
    # acima passaria por acidente.
    assert resposta.headers.get("x-ratelimit-limit") == "20"
    assert "x-ratelimit-remaining" in resposta.headers


# ====================================================================
# 2. O INVENTÁRIO — toda a rota limitada, em todos os ficheiros
# ====================================================================


def _endpoints_limitados():
    """Percorre `routes/` por AST e devolve (ficheiro, função, parâmetros).

    Lê o ficheiro em vez de importar a app de propósito: um endpoint
    limitado num módulo que o `server.py` deixe de incluir continua a ser
    um endpoint limitado, e a guarda tem de o ver.
    """
    encontrados = []
    for caminho in sorted(RAIZ_DAS_ROTAS.rglob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _tem_decorador_de_limite(no):
                continue
            argumentos = no.args
            nomes = [a.arg for a in (*argumentos.posonlyargs, *argumentos.args, *argumentos.kwonlyargs)]
            encontrados.append((caminho.name, no.name, nomes))
    return encontrados


def _tem_decorador_de_limite(no) -> bool:
    for decorador in no.decorator_list:
        alvo = decorador.func if isinstance(decorador, ast.Call) else decorador
        nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
        if nome in DECORADORES_DE_LIMITE:
            # `@router.limit` não existe; só contam os limiters.
            if isinstance(alvo, ast.Attribute) and nome == "limit":
                dono = getattr(alvo.value, "id", "")
                if dono != "limiter":
                    continue
            return True
    return False


def test_o_leitor_encontra_mesmo_os_endpoints_limitados():
    """Contraprova do leitor de AST.

    Sem isto, uma expressão que não casasse com nada faria a guarda
    seguinte passar com a lista VAZIA — verde a afirmar nada. Os números
    são mínimos deliberadamente folgados; o que se prova é que o leitor
    vê vários ficheiros e não zero.
    """
    encontrados = _endpoints_limitados()
    assert len(encontrados) >= 10, f"o leitor só viu {len(encontrados)} endpoints limitados"
    ficheiros = {f for f, _, _ in encontrados}
    assert len(ficheiros) >= 4, f"esperava limites em vários ficheiros, vi {ficheiros}"
    # Âncoras conhecidas: se estas deixarem de aparecer, o leitor mudou de
    # comportamento e não é o código que melhorou.
    nomes = {n for _, n, _ in encontrados}
    assert "generate_portal_upload_url" in nomes
    assert "login_v2" in nomes


@pytest.mark.parametrize("ficheiro,funcao,parametros", _endpoints_limitados())
def test_endpoint_limitado_declara_request_e_response(ficheiro, funcao, parametros):
    """A regra: `request` (exigido pelo slowapi) E `response` (para os cabeçalhos).

    Não se verifica o tipo devolvido pelo handler. Podia — devolver uma
    `JSONResponse` também satisfaz o slowapi — mas isso faria a regra
    depender do corpo de cada serviço, que muda por outros motivos, e o
    `run_*` de hoje devolve `JSONResponse` num ramo e `dict` noutro. Um
    parâmetro na assinatura vale para TODOS os ramos, e é o que o slowapi
    documenta.
    """
    assert "request" in parametros, (
        f"{ficheiro}::{funcao} está limitado mas não declara `request` — o slowapi levanta."
    )
    assert "response" in parametros, (
        f"{ficheiro}::{funcao} está limitado e não declara `response: Response`: "
        "o slowapi não tem onde pôr os cabeçalhos X-RateLimit-* e o caminho "
        "de SUCESSO responde 500. Acrescenta `response: Response` à assinatura."
    )
