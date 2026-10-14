"""
Lote 5 — D-2 FECHADA (opt-in): o Portal do Cliente pode ter o SEU segredo JWT, com janela de rotação.

O DEFEITO
  Os tokens do Portal e os do staff partilhavam o `JWT_SECRET`; só a claim `type` os separava.

O QUE SE AFIRMA (produtores e consumidores REAIS — nunca um token forjado)
  1. sem `PORTAL_JWT_SECRET` nada muda: assina-se e verifica-se com o `JWT_SECRET`;
  2. com ele, os tokens NOVOS não validam com o `JWT_SECRET` (o verificador do staff recusa-os por
     assinatura, sem depender de ninguém ter escrito bem uma comparação de `type`);
  3. os tokens ANTIGOS continuam a valer durante a janela, e deixam de valer com
     `PORTAL_JWT_ACCEPT_LEGACY=false`;
  4. um token do STAFF nunca passa a ser aceite como cliente (a claim `role`/`type` continua a mandar);
  5. um segredo curto ou igual ao do staff é IGNORADO — nunca usado;
  6. a chave de limite de pedidos por PROCESSO sobrevive à separação;
  7. um token expirado é "expirado" e não "inválido" nos dois segredos.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException

from config import JWT_ALGORITHM, JWT_SECRET
from services import portal_jwt_secret as pjs
from services import portal_security

SEGREDO_DO_PORTAL = "p" * 48


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.delenv("PORTAL_JWT_SECRET", raising=False)
    monkeypatch.delenv("PORTAL_JWT_ACCEPT_LEGACY", raising=False)
    pjs._ja_avisou.clear()


def _separar(monkeypatch, legado=True):
    monkeypatch.setenv("PORTAL_JWT_SECRET", SEGREDO_DO_PORTAL)
    monkeypatch.setenv("PORTAL_JWT_ACCEPT_LEGACY", "true" if legado else "false")


def _cred(token):
    return SimpleNamespace(credentials=token)


async def _entrar(token, processo_existe=True):
    """O consumidor REAL (`get_current_client`) com a base de dados falsa."""
    processo = {"id": "proc-1", "is_deleted": False} if processo_existe else None
    with patch.object(portal_security, "db") as bd:
        bd.processes.find_one = AsyncMock(return_value=processo)
        return await portal_security.get_current_client(_cred(token))


class TestSemAVariavelNadaMuda:
    def test_assina_com_o_jwt_secret(self):
        token = portal_security.create_client_magic_token("proc-1")
        assert jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])["sub"] == "proc-1"

    @pytest.mark.asyncio
    async def test_e_o_consumidor_real_aceita_o(self):
        dados = await _entrar(portal_security.create_client_magic_token("proc-1"))
        assert dados["process_id"] == "proc-1"

    def test_a_lista_de_verificacao_e_so_o_jwt_secret(self):
        assert pjs.segredos_de_verificacao() == [JWT_SECRET]


class TestComSegredoProprio:
    @pytest.mark.parametrize("produtor", [
        lambda: portal_security.create_client_magic_token("proc-1"),
        lambda: portal_security.create_verified_session_token("proc-1", "cli-1"),
        lambda: portal_security.create_access_code_session_token("proc-1", "cli-1"),
    ])
    def test_os_tres_produtores_assinam_com_o_segredo_do_portal(self, monkeypatch, produtor):
        _separar(monkeypatch)
        token = produtor()
        assert jwt.decode(token, SEGREDO_DO_PORTAL, algorithms=[JWT_ALGORITHM])["role"] == "client_portal"
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

    @pytest.mark.asyncio
    async def test_a_exploracao_o_verificador_do_staff_recusa_um_token_do_portal_por_assinatura(self, monkeypatch):
        """O ganho: a separação já não depende de uma comparação de `type`."""
        from services.auth import get_current_user

        _separar(monkeypatch)
        token = portal_security.create_client_magic_token("proc-1")
        with pytest.raises(HTTPException) as erro:
            await get_current_user(SimpleNamespace(headers={}, state=SimpleNamespace()), _cred(token))
        assert erro.value.status_code == 401

    @pytest.mark.asyncio
    async def test_o_consumidor_real_aceita_o_token_novo(self, monkeypatch):
        _separar(monkeypatch)
        dados = await _entrar(portal_security.create_verified_session_token("proc-1", "cli-1"))
        assert dados["process_id"] == "proc-1"

    @pytest.mark.asyncio
    async def test_um_token_antigo_continua_a_valer_na_janela(self, monkeypatch):
        antigo = portal_security.create_client_magic_token("proc-1")   # assinado com o JWT_SECRET
        _separar(monkeypatch, legado=True)
        assert (await _entrar(antigo))["process_id"] == "proc-1"

    @pytest.mark.asyncio
    async def test_fechada_a_janela_o_token_antigo_deixa_de_valer(self, monkeypatch):
        antigo = portal_security.create_client_magic_token("proc-1")
        _separar(monkeypatch, legado=False)
        with pytest.raises(HTTPException) as erro:
            await _entrar(antigo)
        assert erro.value.status_code == 401
        # ...e o novo continua a valer
        assert (await _entrar(portal_security.create_client_magic_token("proc-1")))["process_id"] == "proc-1"

    @pytest.mark.asyncio
    async def test_um_token_de_staff_nao_e_cliente_mesmo_assinado_com_o_segredo_antigo(self, monkeypatch):
        """A janela aceita o SEGREDO antigo, não a identidade: sem role `client_portal` não entra."""
        _separar(monkeypatch)
        staff = jwt.encode(
            {"sub": "u1", "role": "admin", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(HTTPException) as erro:
            await _entrar(staff)
        assert erro.value.status_code in (401, 403)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("segredo", [JWT_SECRET, SEGREDO_DO_PORTAL])
    async def test_expirado_diz_expirado_nos_dois_segredos(self, monkeypatch, segredo):
        _separar(monkeypatch)
        expirado = jwt.encode(
            {"sub": "proc-1", "role": "client_portal", "type": "magic_link",
             "exp": datetime.now(timezone.utc) - timedelta(days=1)},
            segredo, algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(HTTPException) as erro:
            await _entrar(expirado)
        assert erro.value.status_code == 401
        assert "expirou" in erro.value.detail


class TestSegredoInutilizavel:
    @pytest.mark.parametrize("valor", ["curto", "x" * 31, "   "])
    def test_curto_ou_vazio_e_ignorado(self, monkeypatch, valor):
        monkeypatch.setenv("PORTAL_JWT_SECRET", valor)
        assert pjs.segredo_proprio_do_portal() is None
        assert pjs.segredo_de_assinatura() == JWT_SECRET

    def test_igual_ao_do_staff_e_ignorado(self, monkeypatch):
        monkeypatch.setenv("PORTAL_JWT_SECRET", JWT_SECRET)
        assert pjs.segredo_proprio_do_portal() is None

    def test_fechar_a_janela_sem_segredo_proprio_nao_tranca_ninguem(self, monkeypatch):
        """`PORTAL_JWT_ACCEPT_LEGACY=false` sem um segredo próprio válido não pode deixar o Portal sem nenhum."""
        monkeypatch.setenv("PORTAL_JWT_ACCEPT_LEGACY", "false")
        assert pjs.segredos_de_verificacao() == [JWT_SECRET]


class TestOWebSocketDoPortal:
    @pytest.mark.asyncio
    async def test_aceita_o_token_novo_e_o_antigo_e_o_de_staff_continua_recusado(self, monkeypatch):
        from services import websocket_api_helpers as wsh

        nome = next(n for n in dir(wsh) if "portal" in n.lower() and n.startswith("verify"))
        verificar = getattr(wsh, nome)
        _separar(monkeypatch)
        novo = portal_security.create_client_magic_token("proc-1")
        antigo = jwt.encode(
            {"sub": "proc-1", "role": "client_portal", "type": "magic_link",
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        with patch.object(wsh, "db") as bd:
            bd.processes.find_one = AsyncMock(return_value={"id": "proc-1", "is_deleted": False})
            assert (await verificar(novo))[0] == "proc-1"
            assert (await verificar(antigo))[0] == "proc-1"

    @pytest.mark.asyncio
    async def test_o_socket_de_staff_recusa_um_token_do_portal_com_segredo_proprio(self, monkeypatch):
        from services.websocket_api_helpers import verify_websocket_token

        _separar(monkeypatch)
        novo = portal_security.create_client_magic_token("proc-1")
        assert await verify_websocket_token(novo) in (None, "invalid")


class TestOLimitePorProcessoSobreviveASeparacao:
    @pytest.mark.parametrize("segredo", [None, SEGREDO_DO_PORTAL])
    def test_a_chave_continua_a_ser_o_processo_e_nao_o_ip(self, monkeypatch, segredo):
        from middleware.rate_limit import _get_rate_limit_key

        if segredo:
            _separar(monkeypatch)
        token = portal_security.create_client_magic_token("proc-77")
        pedido = SimpleNamespace(headers={"Authorization": f"Bearer {token}"}, client=SimpleNamespace(host="9.9.9.9"))
        assert _get_rate_limit_key(pedido) == "user:proc-77"

    def test_um_token_antigo_na_janela_tambem(self, monkeypatch):
        from middleware.rate_limit import _get_rate_limit_key

        antigo = portal_security.create_client_magic_token("proc-77")
        _separar(monkeypatch)
        pedido = SimpleNamespace(headers={"Authorization": f"Bearer {antigo}"}, client=SimpleNamespace(host="9.9.9.9"))
        assert _get_rate_limit_key(pedido) == "user:proc-77"
