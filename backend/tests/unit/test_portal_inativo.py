"""Portal do Cliente bloqueado quando o processo está INATIVO (Bloco 3, ponto 14).

A REGRA
  Fase terminal do motor (`is_active: False`) → o Portal recusa o cliente, em
  CADA pedido, nos logins e no WebSocket. Voltar a uma fase activa reactiva-o
  sozinho. A autoridade é a fase gravada lida pelo motor — não a flag
  `processes.is_active`, que é derivada e já se desfasou.

COMO ESTES TESTES SE PROTEGEM DO PRÓPRIO DUPLO
  Os tokens são emitidos pelos produtores REAIS do `portal_security` (nunca
  forjados) e a guarda testada é a `get_current_client` real. O único duplo é
  a base de dados em memória.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services import (
    portal_auth,
    portal_estado,
    portal_security,
    websocket_api_helpers,
    workflow_phases,
)
from services.portal_security import (
    create_access_code_session_token,
    create_client_magic_token,
    create_verified_session_token,
    get_current_client,
)

FASES = [
    {"name": "clientes_espera", "order": 1, "is_active": True},
    {"name": "fase_bancaria", "order": 2, "is_active": True},
    {"name": "concluidos", "order": 3, "is_active": False},
    {"name": "desistencias", "order": 4, "is_active": False},
]


def _credenciais(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
async def mundo(fake_async_db):
    """Cliente com um processo; as fases são as de cima."""
    for fase in FASES:
        await fake_async_db.workflow_statuses.insert_one(dict(fase))
    await fake_async_db.processes.insert_one(
        {"id": "p-1", "client_id": "c-1", "status": "fase_bancaria", "is_deleted": False}
    )
    await fake_async_db.clients.insert_one(
        {"id": "c-1", "nome": "Joana", "process_ids": ["p-1"]}
    )
    with patch.object(portal_security, "db", fake_async_db), \
         patch.object(workflow_phases, "db", fake_async_db), \
         patch.object(portal_auth, "db", fake_async_db), \
         patch.object(websocket_api_helpers, "db", fake_async_db):
        yield fake_async_db


async def _mudar_fase(db, process_id: str, status):
    await db.processes.update_one({"id": process_id}, {"$set": {"status": status}})


# ─────────────────────────────────────────────────────────────────────
# A decisão pura
# ─────────────────────────────────────────────────────────────────────

class TestAFaseTerminalDecide:
    @pytest.mark.parametrize("status", ["concluidos", "desistencias"])
    def test_fase_terminal_do_motor_e_inativa(self, status):
        assert portal_estado.estado_e_terminal(status, FASES) is True

    @pytest.mark.parametrize("status", ["clientes_espera", "fase_bancaria"])
    def test_fase_activa_nao_e_inativa(self, status):
        assert portal_estado.estado_e_terminal(status, FASES) is False

    @pytest.mark.parametrize("status", [None, "", "pre_registo"])
    def test_lead_nao_e_inativo(self, status):
        """Um processo ainda sem fase não pode ser bloqueado: é o onboarding."""
        assert portal_estado.estado_e_terminal(status, FASES) is False

    def test_um_alias_da_fase_terminal_tambem_bloqueia(self):
        """Gravado como `concluido` quando a fase do motor é `concluidos`."""
        assert portal_estado.estado_e_terminal("concluido", FASES) is True

    def test_uma_gralha_na_fase_terminal_tambem_bloqueia(self):
        assert portal_estado.estado_e_terminal("Concluidos ", FASES) is True

    @pytest.mark.parametrize("status", ["cancelado", "arquivo", "perdido"])
    def test_nomes_legados_que_nao_sao_fases_contam_como_terminais(self, status):
        """Existem em dados reais; deixá-los de fora deixava o Portal aberto."""
        assert portal_estado.estado_e_terminal(status, FASES) is True

    def test_uma_fase_desconhecida_nao_bloqueia_o_cliente(self):
        """O Portal não fecha por dados sujos: não se sabe que é terminal."""
        assert portal_estado.estado_e_terminal("fase_que_ninguem_conhece", FASES) is False

    def test_a_flag_do_motor_manda_sobre_o_nome(self):
        """Uma fase com um nome qualquer mas `is_active: False` é terminal."""
        fases = FASES + [{"name": "em_pausa", "order": 5, "is_active": False}]
        assert portal_estado.estado_e_terminal("em_pausa", fases) is True
        assert portal_estado.estado_e_terminal("em_pausa", FASES) is False


# ─────────────────────────────────────────────────────────────────────
# A guarda de TODAS as rotas autenticadas
# ─────────────────────────────────────────────────────────────────────

class TestAGuardaDeCadaPedido:
    async def test_processo_activo_passa(self, mundo):
        token = create_verified_session_token("p-1", "c-1")
        resultado = await get_current_client(_credenciais(token))
        assert resultado["process_id"] == "p-1"

    @pytest.mark.parametrize("criar", [
        lambda: create_verified_session_token("p-1", "c-1"),
        lambda: create_access_code_session_token("p-1", "c-1"),
        lambda: create_client_magic_token("p-1"),
    ])
    async def test_os_tres_tipos_de_token_sao_recusados(self, mundo, criar):
        await _mudar_fase(mundo, "p-1", "concluidos")
        with pytest.raises(HTTPException) as exc:
            await get_current_client(_credenciais(criar()))
        assert exc.value.status_code == 403
        assert exc.value.detail["codigo"] == portal_estado.CODIGO_PORTAL_INATIVO

    async def test_a_sessao_ja_aberta_deixa_de_funcionar_no_pedido_seguinte(self, mundo):
        """«Imediatamente»: o mesmo token que passava deixa de passar."""
        token = create_verified_session_token("p-1", "c-1")
        await get_current_client(_credenciais(token))
        await _mudar_fase(mundo, "p-1", "desistencias")
        with pytest.raises(HTTPException) as exc:
            await get_current_client(_credenciais(token))
        assert exc.value.status_code == 403

    async def test_voltar_a_uma_fase_activa_reactiva_o_portal(self, mundo):
        token = create_verified_session_token("p-1", "c-1")
        await _mudar_fase(mundo, "p-1", "concluidos")
        with pytest.raises(HTTPException):
            await get_current_client(_credenciais(token))
        await _mudar_fase(mundo, "p-1", "fase_bancaria")
        assert (await get_current_client(_credenciais(token)))["process_id"] == "p-1"

    async def test_a_flag_derivada_do_processo_nao_decide(self, mundo):
        """`is_active: False` numa fase activa (desfasamento) NÃO bloqueia;
        `is_active: True` numa fase terminal bloqueia. A fase manda."""
        token = create_verified_session_token("p-1", "c-1")
        await mundo.processes.update_one(
            {"id": "p-1"}, {"$set": {"is_active": False, "status": "fase_bancaria"}}
        )
        assert (await get_current_client(_credenciais(token)))["process_id"] == "p-1"
        await mundo.processes.update_one(
            {"id": "p-1"}, {"$set": {"is_active": True, "status": "concluidos"}}
        )
        with pytest.raises(HTTPException):
            await get_current_client(_credenciais(token))

    async def test_um_cliente_com_outro_processo_activo_usa_esse(self, mundo):
        """`no_process` escolhia o primeiro não eliminado; sendo um processo
        concluído, trancava o cliente tendo outro em curso."""
        await mundo.processes.insert_one(
            {"id": "p-0", "client_id": "c-1", "status": "concluidos", "is_deleted": False}
        )
        await mundo.clients.update_one(
            {"id": "c-1"}, {"$set": {"process_ids": ["p-0", "p-1"]}}
        )
        token = create_access_code_session_token("no_process", "c-1")
        resultado = await get_current_client(_credenciais(token))
        assert resultado["process_id"] == "p-1"

    async def test_so_bloqueia_quando_TODOS_os_processos_estao_inativos(self, mundo):
        await mundo.processes.insert_one(
            {"id": "p-0", "client_id": "c-1", "status": "desistencias", "is_deleted": False}
        )
        await _mudar_fase(mundo, "p-1", "concluidos")
        await mundo.clients.update_one(
            {"id": "c-1"}, {"$set": {"process_ids": ["p-0", "p-1"]}}
        )
        token = create_access_code_session_token("no_process", "c-1")
        with pytest.raises(HTTPException) as exc:
            await get_current_client(_credenciais(token))
        assert exc.value.status_code == 403

    async def test_cliente_sem_processo_continua_a_entrar(self, mundo):
        """O onboarding: ainda não há processo, logo nada a bloquear."""
        await mundo.clients.update_one({"id": "c-1"}, {"$set": {"process_ids": []}})
        token = create_access_code_session_token("no_process", "c-1")
        resultado = await get_current_client(_credenciais(token))
        assert resultado["process_id"] is None

    async def test_um_token_de_um_processo_nao_salta_para_outro(self, mundo):
        """O `sub` continua a ser do processo que nomeia, mesmo que o cliente
        tenha outro activo: contraprova da escolha do `no_process`."""
        await mundo.processes.insert_one(
            {"id": "p-9", "client_id": "c-1", "status": "concluidos", "is_deleted": False}
        )
        token = create_verified_session_token("p-9", "c-1")
        with pytest.raises(HTTPException) as exc:
            await get_current_client(_credenciais(token))
        assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# Quem EMITE tokens
# ─────────────────────────────────────────────────────────────────────

def _cliente_com_codigo(codigo="ABC123"):
    return {
        "id": "c-1", "nome": "Joana", "process_ids": ["p-1"],
        "portal_access_code": codigo, "contacto": {"email": "joana@exemplo.pt"},
    }


@pytest.fixture
def login_sem_travao():
    """O travão de tentativas não é o assunto: desliga-se a leitura/escrita."""
    with patch.object(portal_auth, "exigir_sem_bloqueio", AsyncMock()), \
         patch.object(portal_auth, "registar_falha", AsyncMock()), \
         patch.object(portal_auth, "limpar", AsyncMock()):
        yield


class TestOsLoginsRecusam:
    async def _login(self, codigo="ABC123"):
        pedido = portal_auth.PortalLoginRequest(email="joana@exemplo.pt", access_code=codigo)
        return await portal_auth.run_portal_login(pedido)

    async def test_login_com_codigo_correcto_e_processo_activo_entra(self, mundo, login_sem_travao):
        await mundo.clients.update_one({"id": "c-1"}, {"$set": _cliente_com_codigo()})
        resposta = await self._login()
        assert resposta.status_code == 200

    async def test_login_com_codigo_correcto_e_processo_inativo_e_recusado(self, mundo, login_sem_travao):
        await mundo.clients.update_one({"id": "c-1"}, {"$set": _cliente_com_codigo()})
        await _mudar_fase(mundo, "p-1", "concluidos")
        with pytest.raises(HTTPException) as exc:
            await self._login()
        assert exc.value.status_code == 403
        assert exc.value.detail["codigo"] == portal_estado.CODIGO_PORTAL_INATIVO

    async def test_credencial_errada_continua_a_ser_401_mesmo_com_processo_inativo(
        self, mundo, login_sem_travao
    ):
        """A CREDENCIAL vem primeiro: quem não a tem não descobre o estado
        do processo (oráculo). Se a ordem se invertesse, isto seria 403."""
        await mundo.clients.update_one({"id": "c-1"}, {"$set": _cliente_com_codigo()})
        await _mudar_fase(mundo, "p-1", "concluidos")
        with pytest.raises(HTTPException) as exc:
            await self._login(codigo="ZZZ999")
        assert exc.value.status_code == 401

    async def test_link_curto_de_processo_inativo_e_recusado(self, mundo):
        token = create_client_magic_token("p-1")
        await mundo.portal_tokens.insert_one(
            {"short_id": "abc12345", "jwt_token": token, "process_id": "p-1", "client_id": "c-1"}
        )
        assert (await portal_auth.run_resolve_portal_token("abc12345"))["process_id"] == "p-1"
        await _mudar_fase(mundo, "p-1", "desistencias")
        with pytest.raises(HTTPException) as exc:
            await portal_auth.run_resolve_portal_token("abc12345")
        assert exc.value.status_code == 403

    async def test_verificacao_por_nif_so_bloqueia_depois_da_credencial(self, mundo):
        await _mudar_fase(mundo, "p-1", "concluidos")
        bom = AsyncMock(return_value={
            "client_id": "c-1", "process_id": "p-1",
            "client_name": "Joana", "process_number": 7,
        })
        with patch.object(portal_auth, "verify_client_credentials", bom):
            with pytest.raises(HTTPException) as exc:
                await portal_auth.run_verify_portal_login(
                    "c-1", {"nif": "123456789", "process_number": 7}
                )
        assert exc.value.status_code == 403

        falha = AsyncMock(side_effect=HTTPException(status_code=401, detail="Credenciais inválidas."))
        with patch.object(portal_auth, "verify_client_credentials", falha):
            with pytest.raises(HTTPException) as exc:
                await portal_auth.run_verify_portal_login(
                    "c-1", {"nif": "000000000", "process_number": 7}
                )
        assert exc.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Tempo real
# ─────────────────────────────────────────────────────────────────────

class TestOSocketDoPortal:
    async def test_ligacao_recusada_com_processo_inativo(self, mundo):
        token = create_verified_session_token("p-1", "c-1")
        assert (await websocket_api_helpers.verify_portal_websocket_token(token)) == (
            "p-1", "verified_session",
        )
        await _mudar_fase(mundo, "p-1", "concluidos")
        assert await websocket_api_helpers.verify_portal_websocket_token(token) is None

    async def test_cortar_fecha_so_os_sockets_desse_processo(self):
        from services.websocket_manager import manager
        from services.ws_client_identity import identidade_de_socket_do_cliente

        meu, de_outro = MagicMock(), MagicMock()
        meu.close = AsyncMock()
        de_outro.close = AsyncMock()
        manager.active_connections[identidade_de_socket_do_cliente("p-1")] = {meu}
        manager.websocket_to_user[meu] = identidade_de_socket_do_cliente("p-1")
        manager.active_connections[identidade_de_socket_do_cliente("p-2")] = {de_outro}
        manager.websocket_to_user[de_outro] = identidade_de_socket_do_cliente("p-2")
        try:
            assert await portal_estado.cortar_sessoes_em_tempo_real("p-1") == 1
            meu.close.assert_awaited_once()
            assert meu.close.await_args.kwargs["code"] == 4002
            de_outro.close.assert_not_called()
        finally:
            manager.active_connections.pop(identidade_de_socket_do_cliente("p-1"), None)
            manager.active_connections.pop(identidade_de_socket_do_cliente("p-2"), None)
            manager.websocket_to_user.pop(meu, None)
            manager.websocket_to_user.pop(de_outro, None)

    async def test_cortar_nunca_levanta(self):
        with patch("services.websocket_manager.manager") as manager:
            manager.active_connections.get.side_effect = RuntimeError("estado partido")
            assert await portal_estado.cortar_sessoes_em_tempo_real("p-1") == 0


class _SocketFalso:
    """WebSocket mínimo: devolve as mensagens dadas e regista o que sai."""

    def __init__(self, mensagens):
        self._mensagens = list(mensagens)
        self.fechado_com = None
        self.enviadas = []

    async def accept(self):
        return None

    async def receive(self):
        if self._mensagens:
            return {"type": "websocket.receive", "text": self._mensagens.pop(0)}
        return {"type": "websocket.disconnect"}

    async def send_json(self, mensagem):
        self.enviadas.append(mensagem)

    async def close(self, code=1000, reason=""):
        self.fechado_com = code


class TestOBatimentoDescobreOBloqueio:
    """O gancho imediato cobre os escritores principais; o batimento cobre
    TODOS — é a razão de existir da releitura no `ping`."""

    async def test_o_ping_de_um_processo_activo_recebe_pong(self, mundo):
        from services import websocket_api_portal as ws

        socket = _SocketFalso(['{"type": "ping"}'])
        token = create_verified_session_token("p-1", "c-1")
        with patch("services.presenca.marcar_online", AsyncMock()):
            await ws.run_portal_websocket(socket, token)
        assert socket.fechado_com is None
        assert any(m.get("data", m).get("status") == "pong" for m in socket.enviadas if isinstance(m, dict))

    async def test_o_ping_depois_de_o_processo_ficar_inativo_fecha_o_socket(self, mundo):
        from services import websocket_api_portal as ws

        class _MudaNoPrimeiroPing(_SocketFalso):
            async def receive(self_inner):
                # A fase muda ENTRE a ligação e o batimento, por um escritor
                # que não passou por nenhum gancho.
                await _mudar_fase(mundo, "p-1", "concluidos")
                return await super().receive()

        socket = _MudaNoPrimeiroPing(['{"type": "ping"}'])
        token = create_verified_session_token("p-1", "c-1")
        with patch("services.presenca.marcar_online", AsyncMock()), \
             patch("database.db", mundo):
            await ws.run_portal_websocket(socket, token)
        assert socket.fechado_com == 4002
        assert not any(
            isinstance(m, dict) and m.get("data", {}).get("status") == "pong"
            for m in socket.enviadas
        )

    async def test_uma_leitura_falhada_nao_fecha_o_socket(self):
        from services import websocket_api_portal as ws

        with patch("database.db") as db_partida:
            db_partida.processes.find_one = AsyncMock(side_effect=RuntimeError("mongo em baixo"))
            assert await ws._processo_do_socket_ficou_inativo("p-1") is False

    async def test_um_processo_eliminado_fecha_o_socket(self, mundo):
        from services import websocket_api_portal as ws

        await mundo.processes.update_one({"id": "p-1"}, {"$set": {"is_deleted": True}})
        with patch("database.db", mundo):
            assert await ws._processo_do_socket_ficou_inativo("p-1") is True


# ─────────────────────────────────────────────────────────────────────
# Inventário: nenhuma rota autenticada do Portal escapa
# ─────────────────────────────────────────────────────────────────────

ROUTES = Path(__file__).resolve().parents[2] / "routes" / "portal.py"

#: Rotas SEM `get_current_client`, cada uma com o motivo escrito. Uma rota
#: nova que não use a dependência e não esteja aqui falha o teste.
SEM_GUARDA_DO_CLIENTE = {
    "portal_login": "emite token; recusa dentro de `run_portal_login` (depois da credencial)",
    "verify_portal_login": "emite token; recusa dentro de `run_verify_portal_login`",
    "resolve_portal_token": "emite token; recusa dentro de `run_resolve_portal_token`",
    "impersonate_client_portal": "staff (`require_staff`), não é o cliente",
    "create_recommendations": "staff (`get_current_user`)",
    "get_scraper_job_status": "consulta pública de um job por id opaco; não devolve dados do processo",
}


def _handlers_do_router() -> dict[str, str]:
    arvore = ast.parse(ROUTES.read_text())
    handlers = {}
    for no in ast.walk(arvore):
        if isinstance(no, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
                for d in no.decorator_list
            ):
                handlers[no.name] = ast.get_source_segment(ROUTES.read_text(), no) or ""
    return handlers


class TestNenhumaRotaEscapa:
    def test_o_leitor_leu_as_rotas(self):
        """Contraprova do inventário: um leitor cego passava sempre."""
        handlers = _handlers_do_router()
        assert len(handlers) >= 15
        assert "get_portal_status" in handlers

    def test_cada_rota_ou_usa_a_guarda_ou_esta_justificada(self):
        sem_guarda = {
            nome for nome, fonte in _handlers_do_router().items()
            if "get_current_client" not in fonte
        }
        assert sem_guarda == set(SEM_GUARDA_DO_CLIENTE), (
            "Rota do Portal sem `get_current_client` e sem justificação: "
            f"{sorted(sem_guarda ^ set(SEM_GUARDA_DO_CLIENTE))}"
        )

    def test_a_guarda_chama_a_decisao_do_estado(self):
        """Sem isto, apagar a chamada dentro da `get_current_client` deixava
        o inventário de cima verde e o Portal aberto."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(get_current_client)
        assert "exigir_processo_activo" in fonte
        assert "escolher_processo_do_cliente" in fonte
