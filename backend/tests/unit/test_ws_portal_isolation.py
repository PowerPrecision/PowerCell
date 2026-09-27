"""
Testes — WebSocket do CLIENTE do Portal: o que ele ouve, e o que NUNCA ouve.

O namespace dos WebSockets era interno. O que impedia um token do Portal de
entrar era uma COINCIDÊNCIA — o `sub` de um token de Portal é um `process_id`,
que não existe em `db.users` — e não uma regra: o `verify_websocket_token`
decifrava com o MESMO `JWT_SECRET` e nunca olhava para a claim `type`.

Estes testes são as duas provas que o dono do produto pediu:

  1. **O cliente A não consegue escutar o processo do cliente B.**
  2. **O cliente A não ouve os eventos internos do SEU PRÓPRIO processo.**

A segunda é a que não é óbvia: o cliente TEM de estar na sala
`process_<id>` para receber as mensagens do consultor, e essa sala é de staff
— transporta deltas do processo (com `client_name` e `process_number`),
bloqueios de edição e o progresso interno dos scrapers. Estar na sala não é ter
direito a tudo o que a sala transporta.

Tudo o que é falseado aqui são as FRONTEIRAS (o socket, o Redis, a BD). O
`ConnectionManager`, o `route_system_event`, o `_route_por_sala` e a barreira do
`ws_client_identity` são os REAIS — é o que faz destes testes uma prova.
"""
from unittest.mock import patch

import jwt
import pytest

from config import JWT_SECRET, JWT_ALGORITHM
from services import ws_client_identity as wci
from services.websocket_manager import (
    WSEventType,
    manager,
    route_system_event,
)
from services.realtime_delivery import sala_do_processo


PROC_A = "processo-do-cliente-A"
PROC_B = "processo-do-cliente-B"


class SocketFalso:
    """Socket que guarda tudo o que lhe foi escrito. É o microfone do teste."""

    def __init__(self, etiqueta: str):
        self.etiqueta = etiqueta
        self.recebido: list[dict] = []
        self.aceito = False
        self.fechado_com: tuple | None = None

    async def accept(self):
        self.aceito = True

    async def send_json(self, mensagem: dict):
        self.recebido.append(mensagem)

    async def close(self, code: int = 1000, reason: str = ""):
        self.fechado_com = (code, reason)

    # --- ajudas de leitura ---
    def tipos(self) -> list[str]:
        return [m.get("type") for m in self.recebido]

    def ouviu(self, event_type: str) -> bool:
        return event_type in self.tipos()


def token_do_portal(process_id: str, tipo: str = "magic_link") -> str:
    """Um token de Portal legítimo, assinado com o segredo REAL da app."""
    return jwt.encode(
        {"sub": process_id, "role": "client_portal", "type": tipo},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def token_de_staff(user_id: str = "user-staff-1", tipo: str | None = "REAL") -> str:
    """Um token do CRM.

    Por omissão vem do produtor de PRODUÇÃO (o do `/auth/login-v2`), e não
    forjado — forjar era o que escondia o defeito que o `backend-full` apanhou:
    estes testes passavam com um `type` inventado enquanto o validador recusava
    o tipo real, e 401 em cada chamada de cada utilizador.

    `tipo=None` forja de propósito um token SEM claim `type`, para exercitar a
    tolerância ao legado; um valor explícito forja esse valor.
    """
    if tipo == "REAL":
        from services.refresh_token_service import create_access_token

        return create_access_token(user_id, "a@b.pt", "admin")

    corpo = {"sub": user_id, "email": "a@b.pt", "role": "admin"}
    if tipo is not None:
        corpo["type"] = tipo
    return jwt.encode(corpo, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture(autouse=True)
def manager_limpo():
    """O `manager` é um singleton de módulo — isolar cada teste é obrigatório."""
    manager.active_connections.clear()
    manager.websocket_to_user.clear()
    manager.rooms.clear() if hasattr(manager, "rooms") else None
    manager.user_rooms.clear()
    manager.user_scopes.clear()
    yield
    manager.active_connections.clear()
    manager.websocket_to_user.clear()
    manager.user_rooms.clear()
    manager.user_scopes.clear()


@pytest.fixture
def processos_na_bd(fake_async_db):
    """Os dois processos existem e não estão eliminados."""
    return fake_async_db


async def _ligar_cliente(process_id: str, fake_db, *, etiqueta: str = "cliente"):
    """Liga um cliente do Portal pelo caminho REAL do endpoint."""
    from services import websocket_api_portal as wap
    from services import websocket_api_helpers as wah

    socket = SocketFalso(etiqueta)

    async def _presenca(_uid):
        return True

    with patch.object(wah, "db", fake_db), \
         patch("services.presenca.marcar_online", _presenca):
        await wap.run_portal_websocket(socket, token_do_portal(process_id))

    return socket


async def _ligar_cliente_sem_fechar(process_id: str, fake_db, etiqueta: str):
    """Liga um cliente e deixa a ligação ABERTA no manager.

    O `run_portal_websocket` corre um laço até o socket desligar; para termos a
    ligação viva enquanto disparamos eventos, reproduzimos só a parte do
    handshake que o endpoint faz — e, para que isso não se torne uma
    reimplementação que possa divergir, há uma guarda de código-fonte em
    `TestOEndpointFazMesmoOQueOTesteAssume`.
    """
    from services import websocket_api_helpers as wah
    from services.websocket_api_helpers import verify_portal_websocket_token

    with patch.object(wah, "db", fake_db):
        verificado = await verify_portal_websocket_token(token_do_portal(process_id))

    assert isinstance(verificado, tuple), f"handshake recusado: {verificado}"
    pid, _tipo = verificado

    socket = SocketFalso(etiqueta)
    identidade = wci.identidade_de_socket_do_cliente(pid)
    await manager.connect(socket, identidade)
    manager.join_room(sala_do_processo(pid), identidade)
    # DELIBERADAMENTE sem `register_scope` — é a regra 2.
    return socket, identidade


async def _ligar_staff(user_id: str, process_id: str, etiqueta: str = "staff"):
    socket = SocketFalso(etiqueta)
    await manager.connect(socket, user_id)
    manager.join_room(sala_do_processo(process_id), user_id)
    return socket


async def _emitir_na_sala(process_id: str, event_type: str, payload: dict | None = None):
    """Publica um evento na sala pelo caminho REAL do router."""
    return await route_system_event({
        "id": f"ev-{event_type}",
        "type": event_type,
        "room": sala_do_processo(process_id),
        "payload": payload or {"process_id": process_id},
        "published_at": "2026-09-26T12:00:00+00:00",
    })


# ====================================================================
# PROVA 1 — O CLIENTE A NÃO ESCUTA O PROCESSO DO CLIENTE B
# ====================================================================

class TestUmClienteNaoEscutaOProcessoDeOutro:

    @pytest.mark.asyncio
    async def test_a_mensagem_do_processo_B_nao_chega_ao_cliente_A(
        self, processos_na_bd
    ):
        """A prova central da fronteira entre clientes."""
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})
        await processos_na_bd.processes.insert_one({"id": PROC_B, "is_deleted": False})

        socket_a, _ = await _ligar_cliente_sem_fechar(PROC_A, processos_na_bd, "A")
        socket_b, _ = await _ligar_cliente_sem_fechar(PROC_B, processos_na_bd, "B")

        # Uma mensagem do consultor no processo de B — evento PERMITIDO,
        # para não haver dúvida de que o que separa os dois é a SALA.
        await _emitir_na_sala(PROC_B, WSEventType.PORTAL_MESSAGE, {
            "process_id": PROC_B, "message": "Documento aprovado, Sr. B.",
        })

        assert socket_b.ouviu(WSEventType.PORTAL_MESSAGE), (
            "o destinatário legítimo TEM de receber — senão este teste passava "
            "por a entrega estar simplesmente quebrada"
        )
        assert socket_a.recebido == [], (
            f"FUGA: o cliente A recebeu {socket_a.recebido}"
        )

    @pytest.mark.asyncio
    async def test_o_cliente_esta_apenas_na_sala_do_SEU_processo(
        self, processos_na_bd
    ):
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        _socket, identidade = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "A"
        )

        assert manager.is_in_room(sala_do_processo(PROC_A), identidade) is True
        assert manager.is_in_room(sala_do_processo(PROC_B), identidade) is False
        assert manager.user_rooms[identidade] == {sala_do_processo(PROC_A)}

    @pytest.mark.asyncio
    async def test_a_sala_sai_do_TOKEN_e_nao_do_pedido(self, processos_na_bd):
        """Um token de A nunca coloca o socket na sala de B.

        O `sub` do token É o `process_id`; a sala é calculada no servidor. Não
        há caminho por onde o cliente indique a sala.
        """
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        from services import websocket_api_helpers as wah
        from services.websocket_api_helpers import verify_portal_websocket_token

        with patch.object(wah, "db", processos_na_bd):
            pid, _ = await verify_portal_websocket_token(token_do_portal(PROC_A))

        assert pid == PROC_A


# ====================================================================
# PROVA 2 — O CLIENTE NÃO OUVE OS EVENTOS INTERNOS DO SEU PROCESSO
# ====================================================================

class TestUmClienteNaoOuveOsEventosInternosDoSeuProcesso:
    """A prova que não é óbvia.

    O cliente TEM de estar na sala `process_<id>` — é por lá que a mensagem do
    consultor chega. Mas essa sala é de STAFF: transporta deltas com
    `client_name` e `process_number`, bloqueios de edição e o progresso interno
    dos scrapers. **Estar na sala não é ter direito a tudo o que a sala
    transporta.**
    """

    EVENTOS_INTERNOS = [
        WSEventType.PROCESS_UPDATED,
        WSEventType.PROCESS_STATUS_CHANGED,
        WSEventType.PROCESS_ASSIGNED,
        WSEventType.PROCESS_MOVED,
        WSEventType.PROCESS_LOCKED,
        WSEventType.PROCESS_UNLOCKED,
        WSEventType.DOCUMENT_UPLOADED,
        WSEventType.DOCUMENT_EXPIRING,
        WSEventType.NEW_CHAT_MESSAGE,
        WSEventType.CHAT_TYPING,
        WSEventType.NEW_EMAIL,
        WSEventType.NEW_NOTIFICATION,
        WSEventType.DEADLINE_CREATED,
        WSEventType.DEADLINE_REMINDER,
        WSEventType.TASK_STARTED,
        WSEventType.TASK_PROGRESS,
        WSEventType.TASK_COMPLETED,
        WSEventType.TASK_FAILED,
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evento", EVENTOS_INTERNOS)
    async def test_cada_evento_interno_e_retido(self, processos_na_bd, evento):
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        socket_cliente, _ = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "cliente"
        )
        socket_staff = await _ligar_staff("consultor-1", PROC_A)

        await _emitir_na_sala(PROC_A, evento, {
            "process_id": PROC_A,
            "client_name": "Ana Silva",
            "process_number": 1234,
        })

        assert socket_staff.ouviu(evento), (
            "o STAFF na mesma sala tem de receber — senão este teste passava "
            "por a sala estar vazia e não pela barreira"
        )
        assert socket_cliente.recebido == [], (
            f"FUGA: o cliente recebeu '{evento}' → {socket_cliente.recebido}"
        )

    @pytest.mark.asyncio
    async def test_o_delta_do_processo_nao_leva_o_nome_do_cliente_ao_socket(
        self, processos_na_bd
    ):
        """O delta transporta `client_name` e `process_number`.

        Num processo com dois titulares, o cliente veria o nome do outro; e o
        delta é emitido por sete módulos diferentes.
        """
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})
        socket_cliente, _ = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "cliente"
        )

        await _emitir_na_sala(PROC_A, WSEventType.PROCESS_UPDATED, {
            "process_id": PROC_A,
            "client_name": "Ana Silva",
            "second_client_name": "Bruno Costa",
            "process_number": 1234,
            "status": "analise_interna",
        })

        assert socket_cliente.recebido == []

    @pytest.mark.asyncio
    async def test_o_que_o_cliente_PODE_ouvir_chega_mesmo(self, processos_na_bd):
        """A contraprova. Sem ela, uma barreira que bloqueia TUDO passava
        todos os testes acima e o Portal ficava sem tempo real nenhum."""
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})
        socket_cliente, _ = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "cliente"
        )

        await _emitir_na_sala(PROC_A, WSEventType.PORTAL_MESSAGE, {
            "process_id": PROC_A, "message": "Bom dia",
        })
        await _emitir_na_sala(PROC_A, WSEventType.PORTAL_GOV_PROGRESS, {
            "process_id": PROC_A, "source": "auto_financas",
            "estado": "concluido", "documents_count": 3,
        })

        assert socket_cliente.tipos() == [
            WSEventType.PORTAL_MESSAGE,
            WSEventType.PORTAL_GOV_PROGRESS,
        ]

    @pytest.mark.asyncio
    async def test_a_lista_de_permissao_e_fechada_por_omissao(self, processos_na_bd):
        """Um evento INVENTADO — que nenhuma lista de bloqueio previa — é retido.

        É a diferença entre lista de permissão e de bloqueio, e é o que faz
        esta barreira sobreviver a um emissor novo.
        """
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})
        socket_cliente, _ = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "cliente"
        )

        await _emitir_na_sala(PROC_A, "relatorio_de_risco_interno", {
            "process_id": PROC_A, "score": 0.91,
        })

        assert socket_cliente.recebido == []


# ====================================================================
# O ÂMBITO DE TENANT — a exclusão é estrutural
# ====================================================================

class TestUmSocketDeClienteNaoTemAmbitoDeRede:
    """Um cliente não tem UCRs; o `resolve_tenant_scope` dar-lhe-ia a REDE DE
    OMISSÃO — a do grupo incumbente — e o encaminhamento por audiência casa por
    `network_id`. Todos os deltas de processo dessa rede chegariam ao browser
    de um cliente.
    """

    @pytest.mark.asyncio
    async def test_o_manager_nao_tem_ambito_para_o_socket_do_cliente(
        self, processos_na_bd
    ):
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})
        _socket, identidade = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "cliente"
        )

        assert manager.get_scope(identidade) is None

    @pytest.mark.asyncio
    async def test_um_evento_por_audiencia_nunca_alcanca_o_cliente(
        self, processos_na_bd
    ):
        """E é estrutural, não uma verificação que alguém tenha de lembrar:
        o `_route_por_audiencia` salta quem não tem âmbito."""
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})
        socket_cliente, _ = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "cliente"
        )

        entregue = await route_system_event({
            "id": "ev-audiencia",
            "type": WSEventType.PROCESS_UPDATED,
            "audience": {"network_ids": ["rede_incumbente"]},
            "payload": {"process_id": PROC_A, "client_name": "Ana Silva"},
        })

        assert socket_cliente.recebido == []
        assert entregue is False

    @pytest.mark.asyncio
    async def test_nenhum_evento_dirigido_pode_alcancar_o_cliente(
        self, processos_na_bd
    ):
        """Os envelopes por `user_id` usam ids de `db.users`; a identidade de um
        cliente é `cliente:<process_id>` e nenhum emissor a escreve. Mesmo
        assim, a lista de permissão guarda também este caminho."""
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})
        socket_cliente, identidade = await _ligar_cliente_sem_fechar(
            PROC_A, processos_na_bd, "cliente"
        )

        entregue = await route_system_event({
            "id": "ev-dirigido",
            "type": WSEventType.NEW_EMAIL,
            "user_id": identidade,
            "payload": {"subject": "Proposta interna do banco"},
        })

        assert socket_cliente.recebido == []
        assert entregue is False


# ====================================================================
# O ENDPOINT REAL — apanhado por mutação
# ====================================================================
# Duas mutações sobreviveram à primeira ronda: acrescentar `register_scope` ao
# socket do cliente, e tirar-lhe o `join_room`. Sobreviveram porque o
# `_ligar_cliente_sem_fechar` acima REIMPLEMENTA o handshake (para deixar a
# ligação aberta enquanto se disparam eventos) — e mutar o endpoint real era
# invisível para ele.
#
# É a mesma lição do lote da quarentena, noutra roupa: um duplo de teste que
# reimplementa a lógica valida o duplo. A correcção é a mesma: um teste um
# nível ABAIXO, que corre o endpoint VERDADEIRO e afirma sobre as CHAMADAS que
# ele faz ao `ConnectionManager`.

class SocketComGuiao(SocketFalso):
    """Socket que devolve um guião de mensagens e depois desliga.

    Permite correr o `run_portal_websocket` até ao fim — handshake, laço e
    `finally` — dentro de um teste.
    """

    def __init__(self, etiqueta: str, guiao: list[dict] | None = None):
        super().__init__(etiqueta)
        import json as _json

        self._fila = [
            {"type": "websocket.receive", "text": _json.dumps(m)}
            for m in (guiao or [])
        ]
        self._fila.append({"type": "websocket.disconnect"})

    async def receive(self):
        return self._fila.pop(0)


class EspiaoDoManager:
    """Registo do que o endpoint pediu ao `ConnectionManager`."""

    def __init__(self):
        self.ambitos: list[tuple] = []
        self.salas: list[tuple[str, str]] = []
        self.presencas: list[str] = []


async def _correr_endpoint_real(
    process_id: str,
    fake_db,
    *,
    guiao: list[dict] | None = None,
    token: str | None = None,
) -> tuple[SocketComGuiao, EspiaoDoManager]:
    """Corre o `run_portal_websocket` VERDADEIRO, espiando o manager."""
    from services import websocket_api_portal as wap
    from services import websocket_api_helpers as wah

    socket = SocketComGuiao("cliente", guiao)
    espiao = EspiaoDoManager()

    register_real = manager.register_scope
    join_real = manager.join_room

    def _register(user_id, scope, *, role=""):
        espiao.ambitos.append((user_id, scope, role))
        return register_real(user_id, scope, role=role)

    def _join(room_name, user_id):
        espiao.salas.append((room_name, user_id))
        return join_real(room_name, user_id)

    async def _presenca(uid):
        espiao.presencas.append(uid)
        return True

    with patch.object(wah, "db", fake_db), \
         patch.object(manager, "register_scope", _register), \
         patch.object(manager, "join_room", _join), \
         patch("services.presenca.marcar_online", _presenca):
        await wap.run_portal_websocket(
            socket, token or token_do_portal(process_id)
        )

    return socket, espiao


class TestOEndpointRealNaoDaAmbitoDeRede:
    """M3: acrescentar `register_scope` ao endpoint tem de ficar vermelho."""

    @pytest.mark.asyncio
    async def test_o_endpoint_nunca_chama_register_scope(self, processos_na_bd):
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        _socket, espiao = await _correr_endpoint_real(PROC_A, processos_na_bd)

        assert espiao.ambitos == [], (
            "um socket de cliente com âmbito de rede receberia os deltas de "
            f"processo de toda a rede de omissão — chamadas: {espiao.ambitos}"
        )


class TestOEndpointRealPoeOClienteNaSalaDoTOKEN:
    """M5: tirar o `join_room` — ou tirá-lo do token — tem de ficar vermelho."""

    @pytest.mark.asyncio
    async def test_entra_exactamente_na_sala_derivada_do_token(
        self, processos_na_bd
    ):
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        _socket, espiao = await _correr_endpoint_real(PROC_A, processos_na_bd)

        assert espiao.salas == [(
            sala_do_processo(PROC_A),
            wci.identidade_de_socket_do_cliente(PROC_A),
        )]

    @pytest.mark.asyncio
    async def test_um_join_room_enviado_pelo_cliente_e_IGNORADO(
        self, processos_na_bd
    ):
        """A sala é ditada pelo servidor: um pedido do cliente não acrescenta
        nada. Se fosse honrado, o cliente A entrava na sala de B com uma
        mensagem de uma linha."""
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        _socket, espiao = await _correr_endpoint_real(
            PROC_A, processos_na_bd,
            guiao=[
                {"type": "join_process_room", "process_id": PROC_B},
                {"type": "join_process_room", "process_id": PROC_A},
            ],
        )

        # Uma só entrada: a do handshake, derivada do token.
        assert espiao.salas == [(
            sala_do_processo(PROC_A),
            wci.identidade_de_socket_do_cliente(PROC_A),
        )]
        assert sala_do_processo(PROC_B) not in [s for s, _ in espiao.salas]

    @pytest.mark.asyncio
    async def test_o_ping_e_a_UNICA_mensagem_com_efeito(self, processos_na_bd):
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        socket, espiao = await _correr_endpoint_real(
            PROC_A, processos_na_bd,
            guiao=[
                {"type": "ping"},
                {"type": "mark_all_read"},
                {"type": "process_locked", "process_id": PROC_A},
            ],
        )

        assert socket.ouviu(WSEventType.HEARTBEAT)
        # Duas renovações de presença: a da ligação e a do único `ping`.
        assert len(espiao.presencas) == 2


class TestAPresencaDoClienteTemNamespace:
    """Ponto 4: o ZSET é UM só e os clientes não podem aparecer como staff."""

    @pytest.mark.asyncio
    async def test_a_presenca_e_marcada_com_o_prefixo_cliente(
        self, processos_na_bd
    ):
        await processos_na_bd.processes.insert_one({"id": PROC_A, "is_deleted": False})

        _socket, espiao = await _correr_endpoint_real(PROC_A, processos_na_bd)

        assert espiao.presencas == [f"cliente:{PROC_A}"]
        assert all(wci.e_socket_de_cliente(p) for p in espiao.presencas)

    def test_sem_clientes_retira_os_sockets_do_portal(self):
        misturado = {"user-1", f"cliente:{PROC_A}", "user-2", f"cliente:{PROC_B}"}
        assert wci.sem_clientes(misturado) == {"user-1", "user-2"}

    @pytest.mark.asyncio
    async def test_todos_online_nao_devolve_clientes(self):
        """O "quem está online" interno lê o ZSET inteiro.

        Sem o filtro, um cliente do Portal aparecia na lista de consultores
        activos do Chat da equipa.
        """
        from services import presenca

        async def _sem_redis():
            return None

        with patch.object(presenca, "_cliente", _sem_redis), \
             patch.object(
                 presenca, "_local_todos",
                 lambda: {"user-1", f"cliente:{PROC_A}"},
             ):
            assert await presenca.todos_online() == {"user-1"}


class TestOEndpointFazMesmoOQueOTesteAssume:
    """Guarda de código-fonte: o `_ligar_cliente_sem_fechar` deste ficheiro
    reproduz o handshake do endpoint, e um duplo que divirja do original torna
    todos os testes acima decorativos.

    Afirma sobre o CÓDIGO do endpoint as três coisas que o duplo assume —
    identidade com prefixo, `join_room` da sala do token e ausência de
    `register_scope` —, com a contraprova de que as chamadas existem mesmo.
    """

    @staticmethod
    def _fonte_do_endpoint() -> str:
        import inspect

        from services import websocket_api_portal as wap
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        return codigo_da_funcao_sem_comentarios(wap.run_portal_websocket)

    def test_o_endpoint_nao_menciona_register_scope(self):
        assert "register_scope" not in self._fonte_do_endpoint()

    def test_o_endpoint_usa_a_identidade_com_prefixo(self):
        fonte = self._fonte_do_endpoint()
        assert "identidade_de_socket_do_cliente(process_id)" in fonte

    def test_o_endpoint_junta_a_sala_do_processo_do_token(self):
        fonte = self._fonte_do_endpoint()
        assert "sala_do_processo(process_id)" in fonte
        assert "manager.join_room(sala, identidade)" in fonte

    def test_a_contraprova_o_endpoint_liga_mesmo_o_socket(self):
        """Sem isto, um endpoint VAZIO satisfazia os três guardas acima."""
        fonte = self._fonte_do_endpoint()
        assert "manager.connect(websocket, identidade)" in fonte
        assert "verify_portal_websocket_token(token)" in fonte


# ====================================================================
# O `type` AUTORITATIVO — a coincidência passa a regra
# ====================================================================

class TestUmTokenDePortalNaoAbreOSocketDeStaff:
    """Até este lote, o que os separava era o `sub` de um token de Portal ser
    um `process_id` que não existe em `db.users`. Agora é a claim `type`.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", list(wci.TIPOS_DO_PORTAL))
    async def test_os_tres_tipos_do_portal_sao_recusados(
        self, fake_async_db, tipo
    ):
        from services import websocket_api_helpers as wah

        with patch.object(wah, "db", fake_async_db):
            resultado = await wah.verify_websocket_token(token_do_portal(PROC_A, tipo))

        assert resultado == "invalid"

    @pytest.mark.asyncio
    async def test_recusado_MESMO_que_o_sub_case_com_um_utilizador(
        self, fake_async_db
    ):
        """A prova de que a recusa é pelo TIPO e não pela ausência do utilizador.

        Sem isto, o teste acima passava só porque o `process_id` não está em
        `db.users` — exactamente a coincidência que este lote vem substituir.
        """
        from services import websocket_api_helpers as wah

        await fake_async_db.users.insert_one({
            "id": PROC_A, "name": "Colisão", "is_active": True,
        })

        with patch.object(wah, "db", fake_async_db):
            resultado = await wah.verify_websocket_token(token_do_portal(PROC_A))

        assert resultado == "invalid", (
            "com o `sub` a casar com um utilizador, só a claim `type` pode "
            "recusar — e é ela que tem de recusar"
        )

    @pytest.mark.asyncio
    async def test_um_token_gov_tambem_e_recusado(self, fake_async_db):
        from services import websocket_api_helpers as wah

        gov = jwt.encode(
            {"sub": "u1", "type": wci.TIPO_GOV, "verified_by_gov": True},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        await fake_async_db.users.insert_one({"id": "u1", "is_active": True})

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_websocket_token(gov) == "invalid"

    @pytest.mark.asyncio
    async def test_o_token_de_staff_continua_a_entrar(self, fake_async_db):
        """Contraprova — sem ela, recusar tudo passava os testes acima."""
        from services import websocket_api_helpers as wah

        await fake_async_db.users.insert_one({
            "id": "user-staff-1", "name": "Ana", "is_active": True,
        })

        with patch.object(wah, "db", fake_async_db):
            user = await wah.verify_websocket_token(token_de_staff())

        assert isinstance(user, dict) and user["id"] == "user-staff-1"

    @pytest.mark.asyncio
    async def test_um_token_de_staff_LEGADO_sem_type_continua_a_entrar(
        self, fake_async_db
    ):
        """`None` é aceite de propósito.

        O `create_token` só passou a estampar `type` neste lote; recusar `None`
        invalidava TODAS as sessões abertas no momento do deploy. A segurança
        vem do outro lado: um tipo ESTRANHO é recusado.
        """
        from services import websocket_api_helpers as wah

        await fake_async_db.users.insert_one({"id": "user-staff-1", "is_active": True})

        with patch.object(wah, "db", fake_async_db):
            user = await wah.verify_websocket_token(token_de_staff(tipo=None))

        assert isinstance(user, dict)


class TestUmTokenDeStaffNaoAbreOSocketDoPortal:
    """A simetria: a separação é afirmada dos DOIS lados."""

    @pytest.mark.asyncio
    async def test_token_de_staff_recusado_no_ws_portal(self, fake_async_db):
        from services import websocket_api_helpers as wah

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_portal_websocket_token(token_de_staff()) == "invalid"

    @pytest.mark.asyncio
    async def test_token_com_role_de_portal_mas_tipo_inventado_e_recusado(
        self, fake_async_db
    ):
        """Lista de PERMISSÃO: um `type` novo não entra até ser declarado."""
        from services import websocket_api_helpers as wah

        forjado = jwt.encode(
            {"sub": PROC_A, "role": "client_portal", "type": "sessao_nova"},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        await fake_async_db.processes.insert_one({"id": PROC_A, "is_deleted": False})

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_portal_websocket_token(forjado) == "invalid"

    @pytest.mark.asyncio
    async def test_token_sem_type_e_recusado_no_portal(self, fake_async_db):
        """Ao contrário do lado do staff, aqui `None` NÃO passa: os tokens do
        Portal sempre declararam tipo, logo não há legado a proteger."""
        from services import websocket_api_helpers as wah

        sem_tipo = jwt.encode(
            {"sub": PROC_A, "role": "client_portal"},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        await fake_async_db.processes.insert_one({"id": PROC_A, "is_deleted": False})

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_portal_websocket_token(sem_tipo) == "invalid"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", list(wci.TIPOS_DO_PORTAL))
    async def test_os_tres_tipos_oficiais_entram(self, fake_async_db, tipo):
        from services import websocket_api_helpers as wah

        await fake_async_db.processes.insert_one({"id": PROC_A, "is_deleted": False})

        with patch.object(wah, "db", fake_async_db):
            resultado = await wah.verify_portal_websocket_token(
                token_do_portal(PROC_A, tipo)
            )

        assert resultado == (PROC_A, tipo)

    @pytest.mark.asyncio
    async def test_um_processo_eliminado_recusa_a_ligacao(self, fake_async_db):
        """Um magic link continua válido depois de o processo ser apagado.

        Sem esta verificação o cliente entrava na sala de um processo morto —
        e o `ProcessDetails` do Lote 3 mostrou o que custa um recurso que
        desapareceu e cujos consumidores não sabem.
        """
        from services import websocket_api_helpers as wah

        await fake_async_db.processes.insert_one({"id": PROC_A, "is_deleted": True})

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_portal_websocket_token(
                token_do_portal(PROC_A)
            ) is None

    @pytest.mark.asyncio
    async def test_um_processo_inexistente_recusa_a_ligacao(self, fake_async_db):
        from services import websocket_api_helpers as wah

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_portal_websocket_token(
                token_do_portal("nao-existe")
            ) is None

    @pytest.mark.asyncio
    async def test_o_endpoint_fecha_com_4002_quando_recusa(self, fake_async_db):
        from services import websocket_api_portal as wap
        from services import websocket_api_helpers as wah

        socket = SocketComGuiao("intruso")
        with patch.object(wah, "db", fake_async_db):
            await wap.run_portal_websocket(socket, token_de_staff())

        assert socket.aceito is True, (
            "aceitar primeiro é o que faz o browser ler o código de fecho em "
            "vez de reconectar para sempre com 1006"
        )
        assert socket.fechado_com == (4002, "Acesso inválido")
        assert socket.recebido == []


class TestOsProdutoresEstampamOTipoDoCRM:
    @pytest.mark.asyncio
    async def test_create_token_estampa_o_tipo_canonico(self):
        from services.auth import create_token

        corpo = jwt.decode(
            create_token("u1", "a@b.pt", "admin"),
            JWT_SECRET, algorithms=[JWT_ALGORITHM],
        )
        assert corpo["type"] == wci.TIPO_DO_STAFF

    def test_o_valor_vem_do_ponto_unico_e_nao_de_um_literal(self):
        """Duplicar o literal era a forma de os produtores divergirem sem
        ninguém dar por isso — e foi exactamente o que aconteceu, com o
        `"access"` escondido no `refresh_token_service`."""
        import inspect

        from services import auth
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(inspect.getsource(auth.tipo_de_token_do_crm))
        assert "TIPO_DO_STAFF" in fonte
        assert "'access'" not in fonte and '"access"' not in fonte


# ====================================================================
# TRÊS LACUNAS APANHADAS POR MUTAÇÃO
# ====================================================================
# Sobreviveram à segunda ronda e nenhuma era mutante equivalente — eram todas
# testes fracos meus:
#   M9  — tirar a verificação do `role` no socket do Portal não matava nada,
#         porque o token de staff do meu teste também falha o `type`.
#   M11 — `todos_online` a devolver clientes não matava nada, porque o meu teste
#         só cobria o ramo SEM Redis e a mutação estava no ramo COM Redis.
#   M12 — o `get_current_user` não tinha teste nenhum. Endureci-o e não o provei.

class TestAVerificacaoDoRoleNoSocketDoPortal:
    """Duas verificações, e cada uma apanha uma coisa diferente.

    Hoje só o `portal_security` emite tokens com os três tipos do Portal, e ele
    põe sempre `role: client_portal` — logo o `role` parece redundante. Não é:
    é a guarda contra um emissor FUTURO (ou um `create_access_token` distraído)
    que estampe um tipo de Portal sem o role. As duas verificações cobrem os
    dois eixos do token e é por isso que são duas.
    """

    @pytest.mark.asyncio
    async def test_tipo_do_portal_com_role_de_staff_e_recusado(self, fake_async_db):
        from services import websocket_api_helpers as wah

        forjado = jwt.encode(
            {"sub": PROC_A, "role": "admin", "type": "magic_link"},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        await fake_async_db.processes.insert_one({"id": PROC_A, "is_deleted": False})

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_portal_websocket_token(forjado) == "invalid"

    @pytest.mark.asyncio
    async def test_tipo_do_portal_sem_role_nenhum_e_recusado(self, fake_async_db):
        from services import websocket_api_helpers as wah

        forjado = jwt.encode(
            {"sub": PROC_A, "type": "verified_session"},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        await fake_async_db.processes.insert_one({"id": PROC_A, "is_deleted": False})

        with patch.object(wah, "db", fake_async_db):
            assert await wah.verify_portal_websocket_token(forjado) == "invalid"


class RedisFalsoDePresenca:
    """Cliente Redis ao nível da CHAMADA, para cobrir o ramo COM Redis.

    O meu primeiro teste de presença falseava `_cliente` para `None`, o que
    exercitava só o recurso local — e a mutação vivia no outro ramo.
    """

    def __init__(self, membros: list[str]):
        self.membros = membros

    async def zrangebyscore(self, chave, minimo, maximo):
        return list(self.membros)

    async def zadd(self, chave, mapa):
        return 1


class TestTodosOnlineNosDoisRamos:

    @pytest.mark.asyncio
    async def test_com_redis_os_clientes_sao_excluidos(self):
        from services import presenca

        redis = RedisFalsoDePresenca(
            ["user-1", f"cliente:{PROC_A}", "user-2", f"cliente:{PROC_B}"]
        )

        async def _com_redis():
            return redis

        with patch.object(presenca, "_cliente", _com_redis), \
             patch.object(presenca, "_local_todos", lambda: set()):
            assert await presenca.todos_online() == {"user-1", "user-2"}

    @pytest.mark.asyncio
    async def test_sem_redis_os_clientes_tambem_sao_excluidos(self):
        from services import presenca

        async def _sem_redis():
            return None

        with patch.object(presenca, "_cliente", _sem_redis), \
             patch.object(
                 presenca, "_local_todos",
                 lambda: {"user-1", f"cliente:{PROC_A}"},
             ):
            assert await presenca.todos_online() == {"user-1"}

    @pytest.mark.asyncio
    async def test_a_uniao_dos_dois_ramos_tambem_filtra(self):
        """O ramo normal soma o Redis com o local — e o cliente pode vir de
        qualquer um dos dois."""
        from services import presenca

        redis = RedisFalsoDePresenca(["user-1", f"cliente:{PROC_A}"])

        async def _com_redis():
            return redis

        with patch.object(presenca, "_cliente", _com_redis), \
             patch.object(
                 presenca, "_local_todos",
                 lambda: {"user-2", f"cliente:{PROC_B}"},
             ):
            assert await presenca.todos_online() == {"user-1", "user-2"}

    @pytest.mark.asyncio
    async def test_a_presenca_de_um_cliente_continua_LEGIVEL_por_id(self):
        """Filtrar a LISTA não é cegar a consulta.

        O `esta_online` responde para qualquer identidade — é o que permitirá
        ao CRM mostrar "o cliente está no Portal agora" sem alargar o
        `todos_online`.
        """
        from services import presenca

        redis = RedisFalsoDePresenca([f"cliente:{PROC_A}"])

        async def _com_redis():
            return redis

        with patch.object(presenca, "_cliente", _com_redis):
            vivos = await presenca.online_entre([f"cliente:{PROC_A}", "user-9"])

        assert vivos == {f"cliente:{PROC_A}"}


class TestGetCurrentUserRecusaTokensEstranhos:
    """A metade REST da decisão do `type` autoritativo — e a mais importante.

    Um token do Portal que chegasse ao `get_current_user` dava a um cliente
    externo a API de staff. Como no WebSocket, o que o impedia era o `sub` ser
    um `process_id` que não existe em `db.users`: uma coincidência.
    """

    @staticmethod
    def _credenciais(token: str):
        from fastapi.security import HTTPAuthorizationCredentials

        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    @staticmethod
    def _pedido():
        class _Req:
            headers: dict = {}
        return _Req()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", list(wci.TIPOS_DO_PORTAL) + [wci.TIPO_GOV])
    async def test_um_tipo_estranho_da_401(self, fake_async_db, tipo):
        from fastapi import HTTPException
        from services import auth

        # O `sub` CASA com um utilizador real: só a claim `type` pode recusar.
        await fake_async_db.users.insert_one({
            "id": "colisao", "name": "Colisão", "is_active": True, "role": "admin",
        })
        forjado = jwt.encode(
            {"sub": "colisao", "role": "client_portal", "type": tipo},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )

        with patch.object(auth, "db", fake_async_db), \
             pytest.raises(HTTPException) as erro:
            await auth.get_current_user(
                self._pedido(), self._credenciais(forjado)
            )

        assert erro.value.status_code == 401

    @pytest.mark.asyncio
    async def test_o_token_de_staff_continua_a_passar(self, fake_async_db):
        """Contraprova: sem ela, recusar tudo passava o teste acima e a API
        inteira ficava fechada."""
        from services import auth

        await fake_async_db.users.insert_one({
            "id": "user-staff-1", "name": "Ana", "is_active": True, "role": "admin",
        })

        with patch.object(auth, "db", fake_async_db):
            user = await auth.get_current_user(
                self._pedido(), self._credenciais(token_de_staff())
            )

        assert user["id"] == "user-staff-1"

    @pytest.mark.asyncio
    async def test_um_token_de_staff_LEGADO_sem_type_continua_a_passar(
        self, fake_async_db
    ):
        from services import auth

        await fake_async_db.users.insert_one({
            "id": "user-staff-1", "name": "Ana", "is_active": True, "role": "admin",
        })

        with patch.object(auth, "db", fake_async_db):
            user = await auth.get_current_user(
                self._pedido(), self._credenciais(token_de_staff(tipo=None))
            )

        assert user["id"] == "user-staff-1"


# ====================================================================
# O PROGRESSO DOS SCRAPERS — o único evento de estado que o cliente vê
# ====================================================================
# M16 sobreviveu: mandar o classificador interno CRU para o cliente não matava
# nenhum teste. Era uma quarta lacuna minha — escrevi um mapa fechado com
# omissão segura e não o provei.

class TestOMotivoQueOClienteVe:
    """O classificador interno não vai cru para o ecrã do cliente.

    Os motivos que ele PODE ver são os que dizem respeito a acções DELE: as
    credenciais que introduziu e o código de confirmação que lhe foi pedido.
    `scraper_unavailable` e `unexpected_error` são nossos — o cliente não os
    sabe ler e não pode agir sobre eles.
    """

    @pytest.mark.parametrize("interno,esperado", [
        ("credenciais_invalidas", "credenciais_invalidas"),
        ("mfa_requerido", "confirmacao_necessaria"),
        ("mfa_timeout", "confirmacao_expirada"),
        ("mfa_codigo_incorreto", "confirmacao_incorreta"),
    ])
    def test_os_motivos_accionaveis_passam_traduzidos(self, interno, esperado):
        from services.portal_gov_fetch import motivo_para_o_cliente

        assert motivo_para_o_cliente(interno) == esperado

    @pytest.mark.parametrize("interno", [
        "scraper_unavailable", "unexpected_error", "mfa_error",
        "erro_novo_que_ninguem_previu", "", None,
    ])
    def test_tudo_o_mais_colapsa_em_indisponivel(self, interno):
        """Omissão SEGURA: um motivo novo do lado do scraper aparece como
        "indisponível" até alguém decidir que o cliente o deve ver."""
        from services.portal_gov_fetch import motivo_para_o_cliente, MOTIVO_GENERICO

        assert motivo_para_o_cliente(interno) == MOTIVO_GENERICO

    def test_o_mapa_nao_deixa_passar_nada_por_acidente(self):
        from services.portal_gov_fetch import (
            MOTIVOS_VISIVEIS_AO_CLIENTE,
            motivo_para_o_cliente,
        )

        # Nenhum valor traduzido é um nome interno que não esteja no mapa.
        for interno in MOTIVOS_VISIVEIS_AO_CLIENTE:
            assert motivo_para_o_cliente(interno) != interno or interno in (
                "credenciais_invalidas",
            )


class TestOsDoisEventosDaRecolha:
    """A equipa e o cliente recebem eventos DIFERENTES do mesmo acontecimento."""

    @staticmethod
    async def _capturar(**kwargs):
        from services import portal_gov_fetch as pgf

        emitidos: list[tuple[str, str, dict]] = []

        async def _falso(sala, event_type, payload, **_):
            emitidos.append((sala, event_type, payload))
            return True

        with patch.object(pgf, "entregar_na_sala", _falso):
            await pgf._notificar_recolha(PROC_A, "auto_financas", **kwargs)
        return emitidos

    @pytest.mark.asyncio
    async def test_sucesso_emite_para_a_equipa_e_para_o_cliente(self):
        emitidos = await self._capturar(docs_count=3)

        tipos = [t for _, t, _ in emitidos]
        assert tipos == [
            WSEventType.DOCUMENT_UPLOADED,
            WSEventType.PORTAL_GOV_PROGRESS,
        ]

        _, _, do_cliente = emitidos[1]
        assert do_cliente["estado"] == "concluido"
        assert do_cliente["documents_count"] == 3

    @pytest.mark.asyncio
    async def test_a_falha_leva_o_motivo_TRADUZIDO_ao_cliente(self):
        emitidos = await self._capturar(error_type="scraper_unavailable")

        _, _, da_equipa = emitidos[0]
        _, _, do_cliente = emitidos[1]

        assert da_equipa["error"] == "scraper_unavailable", (
            "a equipa continua a receber o classificador interno"
        )
        assert do_cliente["motivo"] == "indisponivel"
        assert "error" not in do_cliente, (
            "o classificador interno não pode ir no evento do cliente"
        )

    @pytest.mark.asyncio
    async def test_o_evento_do_cliente_nao_leva_nomes_nem_ids_internos(self):
        """Contrato do `PORTAL_GOV_PROGRESS`: uma lista FECHADA de chaves.

        Uma procura por substring passaria com uma chave nova a mais — é a
        forma de o contrato crescer sem ninguém decidir.
        """
        emitidos = await self._capturar(docs_count=2)
        _, _, do_cliente = emitidos[1]

        assert set(do_cliente) == {
            "process_id", "source", "estado", "documents_count",
        }

    @pytest.mark.asyncio
    async def test_uma_falha_de_entrega_nao_propaga(self):
        """Uma notificação perdida degrada a UI para polling; nunca pode fazer
        falhar a recolha que já correu."""
        from services import portal_gov_fetch as pgf

        async def _explode(*a, **k):
            raise RuntimeError("Redis em baixo")

        with patch.object(pgf, "entregar_na_sala", _explode):
            await pgf._notificar_recolha(PROC_A, "auto_financas", docs_count=1)

    @pytest.mark.asyncio
    async def test_apenas_o_evento_do_cliente_esta_na_lista_de_permissao(self):
        """A razão de existirem dois eventos, afirmada em código."""
        assert wci.evento_permitido_ao_cliente(WSEventType.PORTAL_GOV_PROGRESS) is True
        assert wci.evento_permitido_ao_cliente(WSEventType.DOCUMENT_UPLOADED) is False


# ====================================================================
# O INVENTÁRIO DOS PRODUTORES — o teste que faltava
# ====================================================================
# Este ficheiro foi escrito com uma premissa ERRADA: que "os tokens de staff não
# declaram `type`". Cheguei lá depois de ler o `services/auth.create_token` — e
# essa função NÃO é a que o `/auth/login-v2` usa. O login de produção mina por
# `refresh_token_service.create_access_token`, que estampa `"type": "access"`
# desde sempre.
#
# Resultado: o validador nasceu a recusar o tipo REAL, e todos os testes deste
# ficheiro passavam porque eu FORJAVA os tokens com o tipo que tinha inventado.
# 401 em cada chamada de cada utilizador — apanhado pelo `backend-full` do CI,
# que passa pelo login a sério, e não pelos unitários.
#
# É a falha do Lote 5 do lado da escrita: inventariar UM produtor e concluir
# sobre a regra. A correcção não é só o valor certo — é este inventário, que
# corre CADA produtor real contra o validador real. Um produtor novo que não
# estampe o tipo canónico fica vermelho aqui.

class TestTodosOsProdutoresDeTokenDoCRM:
    """Cada produtor REAL de tokens do CRM tem de passar o `get_current_user`.

    Os tokens são criados pelas funções de PRODUÇÃO, nunca forjados — forjar era
    exactamente o que escondia o defeito.
    """

    @staticmethod
    def _produtores() -> dict:
        from services.auth import create_access_token, create_token
        from services.refresh_token_service import (
            create_access_token as minar_do_login,
        )

        return {
            # `/auth/login-v2` e `/auth/refresh` — a origem de TODOS os tokens
            # de sessão em circulação.
            "login-v2/refresh": minar_do_login("user-1", "a@b.pt", "admin"),
            # `/auth/register`.
            "register": create_token("user-1", "a@b.pt", "consultor"),
            # "Ver como Cliente" (impersonate), em `admin_users`.
            "impersonate": create_access_token({
                "sub": "user-1",
                "email": "a@b.pt",
                "role": "admin",
                "is_impersonated": True,
                "impersonated_by": "admin-1",
            }),
        }

    @pytest.mark.parametrize("origem", ["login-v2/refresh", "register", "impersonate"])
    def test_o_tipo_estampado_e_aceito_pelo_validador(self, origem):
        corpo = jwt.decode(
            self._produtores()[origem], JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        assert wci.tipo_de_token_e_de_staff(corpo.get("type")) is True, (
            f"o produtor '{origem}' estampa type={corpo.get('type')!r}, que o "
            "validador do CRM recusa — seria 401 em cada chamada"
        )

    @pytest.mark.parametrize("origem", ["login-v2/refresh", "register", "impersonate"])
    def test_os_tres_estampam_o_MESMO_tipo(self, origem):
        """Três produtores com três nomes seria a mesma armadilha adiada."""
        corpo = jwt.decode(
            self._produtores()[origem], JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        assert corpo.get("type") == wci.TIPO_DO_STAFF

    @pytest.mark.asyncio
    @pytest.mark.parametrize("origem", ["login-v2/refresh", "register", "impersonate"])
    async def test_o_get_current_user_aceita_o_token_de_cada_produtor(
        self, fake_async_db, origem
    ):
        """Ponta a ponta pelo `get_current_user` REAL, e não só pelo predicado.

        É esta a asserção que o CI fez por mim: entre o predicado e o endpoint
        há uma chamada, e é na chamada que o defeito vivia.
        """
        from services import auth

        await fake_async_db.users.insert_one({
            "id": "user-1", "name": "Ana", "email": "a@b.pt",
            "is_active": True, "role": "admin",
        })

        class _Req:
            headers: dict = {}

        from fastapi.security import HTTPAuthorizationCredentials

        credenciais = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=self._produtores()[origem]
        )

        with patch.object(auth, "db", fake_async_db):
            utilizador = await auth.get_current_user(_Req(), credenciais)

        assert utilizador["id"] == "user-1"

    def test_o_valor_canonico_e_o_que_a_producao_ja_estampava(self):
        """`"access"`, e não um nome inventado.

        Escolher um nome novo obrigava a migrar todos os tokens em circulação —
        e foi ao inventar `"staff"` que parti o login inteiro.
        """
        assert wci.TIPO_DO_STAFF == "access"

    def test_nenhum_produtor_do_CRM_usa_um_literal_proprio(self):
        """Guarda sobre o código-fonte: o valor vem do ponto único.

        O literal `"access"` vivia escondido no `refresh_token_service`,
        invisível a quem lesse o `services/auth` — e foi essa invisibilidade que
        produziu o defeito. Com os três a ler a mesma constante, divergirem
        deixa de ser possível em silêncio.
        """
        import inspect

        from services import refresh_token_service
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(
            refresh_token_service.create_access_token
        )
        assert "tipo_de_token_do_crm" in fonte
        assert "'access'" not in fonte and '"access"' not in fonte

    def test_a_contraprova_o_produtor_estampa_mesmo_um_type(self):
        """Sem isto, um produtor que deixasse de estampar satisfazia o guarda."""
        corpo = jwt.decode(
            self._produtores()["login-v2/refresh"],
            JWT_SECRET, algorithms=[JWT_ALGORITHM],
        )
        assert "type" in corpo
