"""Base de dados inalcançável responde 503 com a verdade, não 500 «Erro interno» (Out 2026).

Incidente: a lista de IPs do Atlas ficou vazia, todas as ligações deram timeout e o login
respondia `500 Erro interno: ServerSelectionTimeoutError` — uma mensagem que manda procurar na
aplicação ou nas credenciais quando a causa está fora dela.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pymongo.errors import NetworkTimeout, ServerSelectionTimeoutError

import services.auth_login_handlers as login
from services.auth_login_handlers import MENSAGEM_BASE_DE_DADOS_INDISPONIVEL


def _pedido():
    request = MagicMock()
    request.headers = {"User-Agent": "teste"}
    request.client.host = "127.0.0.1"
    return request


def _dados():
    return MagicMock(email="alguem@exemplo.pt", password="x")


class TestLogin:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("erro", [
        ServerSelectionTimeoutError("timed out"),
        NetworkTimeout("timed out"),
    ])
    async def test_falha_de_ligacao_e_503_com_mensagem_verdadeira(self, erro):
        bd = MagicMock()
        bd.users.find_one = AsyncMock(side_effect=erro)
        with patch.object(login, "db", bd):
            with pytest.raises(HTTPException) as exc:
                await login.run_login_v2(_pedido(), _dados(), MagicMock())
        assert exc.value.status_code == 503
        assert exc.value.detail == MENSAGEM_BASE_DE_DADOS_INDISPONIVEL

    @pytest.mark.asyncio
    async def test_um_erro_que_nao_e_de_ligacao_continua_a_ser_500(self):
        """Contraprova: só a falha de LIGAÇÃO vira 503; um defeito nosso não se disfarça."""
        bd = MagicMock()
        bd.users.find_one = AsyncMock(side_effect=ValueError("bug"))
        with patch.object(login, "db", bd):
            with pytest.raises(HTTPException) as exc:
                await login.run_login_v2(_pedido(), _dados(), MagicMock())
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_credenciais_erradas_continuam_401(self):
        bd = MagicMock()
        bd.users.find_one = AsyncMock(return_value=None)
        with patch.object(login, "db", bd):
            with pytest.raises(HTTPException) as exc:
                await login.run_login_v2(_pedido(), _dados(), MagicMock())
        assert exc.value.status_code == 401


class TestHandlerGlobal:
    def test_qualquer_rota_que_deixe_subir_a_falha_de_ligacao_responde_503(self):
        from fastapi.testclient import TestClient

        import server

        @server.app.get("/__teste_bd_inalcancavel")
        async def _rota():
            raise ServerSelectionTimeoutError("timed out")

        resposta = TestClient(server.app, raise_server_exceptions=False).get("/__teste_bd_inalcancavel")
        assert resposta.status_code == 503
        assert resposta.json()["detail"] == MENSAGEM_BASE_DE_DADOS_INDISPONIVEL
        assert resposta.headers.get("retry-after") == "30"

    def test_o_handler_nao_escreve_na_base_de_dados_que_esta_em_baixo(self):
        """A resposta não pode esperar por outro timeout de 30 s para registar o erro."""
        import ast
        import inspect

        import server

        corpo = inspect.getsource(server.database_unreachable_handler)
        arvore = ast.parse(corpo)
        nomes = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
        assert "log_error" not in nomes
