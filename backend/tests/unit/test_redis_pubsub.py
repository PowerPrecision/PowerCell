"""Testes unitários da camada Pub/Sub de eventos (ÉPICO Event-Driven).

Cobre ``services/redis_pubsub.py`` (envelope, publicação, listener),
``services/task_events.py`` (tradução estado → evento) e o router de
``services/websocket_manager.py``.

FOCO EM DUAS GARANTIAS NÃO-NEGOCIÁVEIS:
  1. **Tenant-safety** — um evento do utilizador A nunca chega ao
     utilizador B. Um envelope sem destinatário é DESCARTADO, nunca
     difundido (falha fechada).
  2. **Resiliência** — Redis em baixo nunca quebra a tarefa que originou o
     evento; degrada para entrega in-process e, no limite, para polling.

REGRA DE ARQUITETURA (tests/unit/conftest.py): sem MongoDB vivo e sem
Redis vivo. O cliente Redis é sempre substituído por duplos de teste.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import redis_pubsub
from services.redis_pubsub import (
    MAX_PAYLOAD_BYTES,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_PROGRESS,
    TASK_STARTED,
    SystemEventListener,
    build_event_envelope,
    is_deliverable,
    parse_envelope,
    publish_envelope,
    publish_event,
    serialize_envelope,
)


@pytest.fixture(autouse=True)
def _reset_publisher_state():
    """Cada teste começa com o circuit breaker do publicador limpo."""
    redis_pubsub._publisher = None
    redis_pubsub._publisher_available = None
    yield
    redis_pubsub._publisher = None
    redis_pubsub._publisher_available = None


@pytest.fixture
def fake_redis():
    """Cliente Redis mínimo: regista o que foi publicado."""
    client = MagicMock()
    client.publish = AsyncMock(return_value=1)
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock()
    return client


# ====================================================================
# ENVELOPE
# ====================================================================


class TestEnvelope:
    def test_envelope_transporta_destinatario_e_contexto(self):
        envelope = build_event_envelope(
            TASK_PROGRESS,
            {"task_id": "t1", "progress": 40},
            user_id="user-a",
            company_id="empresa-1",
        )
        assert envelope["type"] == TASK_PROGRESS
        assert envelope["user_id"] == "user-a"
        assert envelope["company_id"] == "empresa-1"
        assert envelope["payload"] == {"task_id": "t1", "progress": 40}
        assert envelope["id"] and envelope["published_at"]

    def test_cada_envelope_tem_id_unico(self):
        """O `id` permite ao cliente descartar duplicados numa reconexão."""
        primeiro = build_event_envelope("x", {}, user_id="u")
        segundo = build_event_envelope("x", {}, user_id="u")
        assert primeiro["id"] != segundo["id"]

    def test_company_id_e_opcional(self):
        envelope = build_event_envelope("x", {}, user_id="u")
        assert envelope["company_id"] is None

    @pytest.mark.parametrize(
        "envelope,expected",
        [
            ({"type": "task_progress", "user_id": "u1"}, True),
            ({"type": "task_progress", "user_id": ""}, False),
            ({"type": "task_progress"}, False),
            ({"user_id": "u1"}, False),
            ({"type": "", "user_id": "u1"}, False),
            ({}, False),
            (None, False),
            ("nem sequer um dict", False),
        ],
    )
    def test_entregavel_exige_destinatario_e_tipo(self, envelope, expected):
        assert is_deliverable(envelope) is expected


class TestSerializacao:
    def test_ida_e_volta_preserva_o_envelope(self):
        envelope = build_event_envelope(
            TASK_COMPLETED, {"task_id": "t1"}, user_id="u1"
        )
        assert parse_envelope(serialize_envelope(envelope)) == envelope

    def test_payload_gigante_e_recusado(self):
        """Um evento é um sinal, não um transporte de dados."""
        envelope = build_event_envelope(
            TASK_COMPLETED, {"blob": "x" * (MAX_PAYLOAD_BYTES + 100)}, user_id="u1"
        )
        assert serialize_envelope(envelope) is None

    def test_valores_nao_serializaveis_degradam_para_string(self):
        class Opaco:
            def __repr__(self):
                return "<opaco>"

        envelope = build_event_envelope("x", {"v": Opaco()}, user_id="u1")
        assert "opaco" in serialize_envelope(envelope)

    @pytest.mark.parametrize(
        "raw", ["", "   ", "não é json", "[]", "null", b"\xff\xfe", 42, None]
    )
    def test_mensagens_corrompidas_devolvem_none(self, raw):
        """Uma mensagem má não pode derrubar o listener."""
        assert parse_envelope(raw) is None

    def test_aceita_bytes_do_redis(self):
        envelope = build_event_envelope("x", {"a": 1}, user_id="u1")
        raw = serialize_envelope(envelope).encode("utf-8")
        assert parse_envelope(raw) == envelope

    def test_mensagem_sem_destinatario_e_descartada(self):
        """TENANT-SAFETY: sem user_id o evento morre aqui."""
        import json

        raw = json.dumps({"type": "task_progress", "payload": {}})
        assert parse_envelope(raw) is None


# ====================================================================
# PUBLICAÇÃO
# ====================================================================


class TestPublicacao:
    async def test_publica_no_canal_dedicado(self, fake_redis):
        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=fake_redis)
        ):
            ok = await publish_event(
                TASK_PROGRESS, {"task_id": "t1"}, user_id="user-a"
            )

        assert ok is True
        canal, raw = fake_redis.publish.await_args.args
        assert canal == redis_pubsub.SYSTEM_EVENTS_CHANNEL
        assert parse_envelope(raw)["user_id"] == "user-a"

    async def test_sem_user_id_nao_publica_nada(self, fake_redis):
        """TENANT-SAFETY: nunca difundir um evento sem destinatário."""
        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=fake_redis)
        ), patch.object(redis_pubsub, "_deliver_locally", AsyncMock()) as local:
            ok = await publish_event(TASK_PROGRESS, {"task_id": "t1"}, user_id="")

        assert ok is False
        fake_redis.publish.assert_not_awaited()
        local.assert_not_awaited()

    async def test_envelope_sem_destinatario_e_recusado(self, fake_redis):
        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=fake_redis)
        ):
            ok = await publish_envelope({"type": "task_progress", "payload": {}})

        assert ok is False
        fake_redis.publish.assert_not_awaited()

    async def test_redis_em_baixo_degrada_para_entrega_local(self):
        """RESILIÊNCIA: sem Redis, as ligações deste worker ainda recebem."""
        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=None)
        ), patch.object(redis_pubsub, "_deliver_locally", AsyncMock()) as local:
            ok = await publish_event(
                TASK_PROGRESS, {"task_id": "t1"}, user_id="user-a"
            )

        assert ok is False  # não houve fan-out entre workers
        local.assert_awaited_once()
        assert local.await_args.args[0]["user_id"] == "user-a"

    async def test_entrega_local_pode_ser_desligada(self):
        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=None)
        ), patch.object(redis_pubsub, "_deliver_locally", AsyncMock()) as local:
            await publish_event(
                TASK_PROGRESS, {}, user_id="u1", deliver_locally=False
            )
        local.assert_not_awaited()

    async def test_excepcao_do_redis_nao_propaga(self, fake_redis):
        """A tarefa que emitiu o evento não pode falhar por causa dele."""
        fake_redis.publish = AsyncMock(side_effect=ConnectionError("redis down"))

        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=fake_redis)
        ), patch.object(redis_pubsub, "_deliver_locally", AsyncMock()):
            ok = await publish_event(TASK_PROGRESS, {}, user_id="u1")

        assert ok is False
        # Circuit breaker armado: o evento seguinte não paga o timeout
        assert redis_pubsub._publisher_available is False

    async def test_falha_da_entrega_local_tambem_e_engolida(self):
        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=None)
        ), patch(
            "services.websocket_manager.route_system_event",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            assert await publish_event(TASK_PROGRESS, {}, user_id="u1") is False


# ====================================================================
# LISTENER
# ====================================================================


class TestListener:
    async def test_entrega_eventos_validos_ao_handler(self):
        recebidos = []
        listener = SystemEventListener(
            lambda env: _collect(recebidos, env)
        )
        envelope = build_event_envelope(TASK_COMPLETED, {"t": 1}, user_id="u1")

        await listener._dispatch(serialize_envelope(envelope))

        assert recebidos == [envelope]
        assert listener.events_received == 1

    async def test_mensagem_corrompida_nao_chega_ao_handler(self):
        recebidos = []
        listener = SystemEventListener(lambda env: _collect(recebidos, env))

        await listener._dispatch("{lixo")
        await listener._dispatch(None)

        assert recebidos == []
        assert listener.events_received == 0

    async def test_evento_sem_destinatario_nao_chega_ao_handler(self):
        """TENANT-SAFETY na recepção, não só na emissão."""
        import json

        recebidos = []
        listener = SystemEventListener(lambda env: _collect(recebidos, env))

        await listener._dispatch(json.dumps({"type": "task_progress"}))

        assert recebidos == []

    async def test_handler_que_rebenta_nao_mata_o_listener(self):
        listener = SystemEventListener(AsyncMock(side_effect=RuntimeError("boom")))
        envelope = build_event_envelope(TASK_PROGRESS, {}, user_id="u1")

        await listener._dispatch(serialize_envelope(envelope))  # não levanta

        assert listener.events_received == 1

    def test_nao_arranca_sem_redis_configurado(self):
        """Sem REDIS_URL o sistema degrada, não estoira."""
        listener = SystemEventListener(AsyncMock())
        with patch.object(redis_pubsub, "is_configured", return_value=False):
            assert listener.start() is False
        assert listener.is_running is False

    def test_arranque_e_idempotente(self):
        listener = SystemEventListener(AsyncMock())
        with patch.object(
            redis_pubsub, "is_configured", return_value=True
        ), patch("asyncio.create_task", MagicMock()) as create:
            assert listener.start() is True
            assert listener.start() is True
        assert create.call_count == 1

    async def test_stop_limpa_o_estado(self):
        listener = SystemEventListener(AsyncMock())
        with patch.object(
            redis_pubsub, "is_configured", return_value=True
        ), patch("asyncio.create_task", MagicMock()):
            listener.start()
        await listener.stop()
        assert listener.is_running is False
        assert listener.is_connected is False


# ====================================================================
# ROUTER (websocket_manager) — o coração da tenant-safety
# ====================================================================


class TestRouterTenantSafety:
    @pytest.fixture
    def manager_espiao(self):
        from services import websocket_manager

        espiao = MagicMock()
        espiao.is_user_connected = MagicMock(return_value=True)
        espiao.send_personal_message = AsyncMock()
        with patch.object(websocket_manager, "manager", espiao):
            yield espiao

    async def test_entrega_apenas_ao_destinatario(self, manager_espiao):
        from services.websocket_manager import route_system_event

        envelope = build_event_envelope(
            TASK_PROGRESS, {"task_id": "t1"}, user_id="user-a"
        )
        assert await route_system_event(envelope) is True

        mensagem, destinatario = manager_espiao.send_personal_message.await_args.args
        assert destinatario == "user-a"
        assert mensagem["type"] == TASK_PROGRESS
        assert mensagem["data"] == {"task_id": "t1"}
        assert mensagem["event_id"] == envelope["id"]

    async def test_nunca_difunde_sem_destinatario(self, manager_espiao):
        """A garantia central: sem user_id não há entrega NEM broadcast."""
        from services.websocket_manager import route_system_event

        assert await route_system_event(
            {"type": TASK_PROGRESS, "payload": {"task_id": "t1"}}
        ) is False

        manager_espiao.send_personal_message.assert_not_awaited()
        # `broadcast` nunca é sequer tocado por este caminho
        manager_espiao.broadcast.assert_not_called()

    async def test_evento_de_a_nao_vai_para_b(self, manager_espiao):
        from services.websocket_manager import route_system_event

        await route_system_event(
            build_event_envelope(TASK_PROGRESS, {}, user_id="user-a")
        )
        destinatarios = [
            call.args[1]
            for call in manager_espiao.send_personal_message.await_args_list
        ]
        assert destinatarios == ["user-a"]
        assert "user-b" not in destinatarios

    async def test_utilizador_noutro_worker_nao_e_erro(self, manager_espiao):
        """Normal em multi-worker: o socket vive noutro processo."""
        from services.websocket_manager import route_system_event

        manager_espiao.is_user_connected.return_value = False
        envelope = build_event_envelope(TASK_PROGRESS, {}, user_id="user-a")

        assert await route_system_event(envelope) is False
        manager_espiao.send_personal_message.assert_not_awaited()

    async def test_envelope_invalido_nao_rebenta(self, manager_espiao):
        from services.websocket_manager import route_system_event

        assert await route_system_event(None) is False
        assert await route_system_event("string") is False
        assert await route_system_event({}) is False

    async def test_falha_de_envio_nao_propaga(self, manager_espiao):
        from services.websocket_manager import route_system_event

        manager_espiao.send_personal_message = AsyncMock(
            side_effect=RuntimeError("socket morto")
        )
        envelope = build_event_envelope(TASK_PROGRESS, {}, user_id="u1")

        assert await route_system_event(envelope) is False


# ====================================================================
# TRADUÇÃO ESTADO → EVENTO (task_events)
# ====================================================================


class TestResolveEventType:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("processing", TASK_PROGRESS),
            ("running", TASK_PROGRESS),
            ("in_progress", TASK_PROGRESS),
            ("pending", TASK_STARTED),
            ("queued", TASK_STARTED),
            ("completed", TASK_COMPLETED),
            ("success", TASK_COMPLETED),
            ("failed", TASK_FAILED),
            ("error", TASK_FAILED),
            ("cancelled", TASK_FAILED),
            ("COMPLETED", TASK_COMPLETED),
            ("  Failed  ", TASK_FAILED),
            ("estado_desconhecido", TASK_PROGRESS),
            (None, TASK_PROGRESS),
        ],
    )
    def test_mapeia_estados_para_eventos(self, status, expected):
        from services.task_events import resolve_event_type

        assert resolve_event_type(status) == expected

    def test_criacao_e_sempre_task_started(self):
        from services.task_events import resolve_event_type

        assert resolve_event_type("pending", is_creation=True) == TASK_STARTED
        assert resolve_event_type(None, is_creation=True) == TASK_STARTED

    def test_criacao_nao_mascara_estado_terminal(self):
        """Um job criado já falhado é `task_failed`, não `task_started`."""
        from services.task_events import resolve_event_type

        assert resolve_event_type("failed", is_creation=True) == TASK_FAILED

    def test_enum_de_estado_e_desembrulhado(self):
        """`TaskStatus.COMPLETED` não pode virar "taskstatus.completed"."""
        from models.task_log import TaskStatus
        from services.task_events import resolve_event_type

        assert resolve_event_type(TaskStatus.COMPLETED) == TASK_COMPLETED
        assert resolve_event_type(TaskStatus.FAILED) == TASK_FAILED
        assert resolve_event_type(TaskStatus.PROCESSING) == TASK_PROGRESS


class TestPayload:
    def test_omite_campos_ausentes(self):
        """Eventos de progresso não reenviam título/tipo — o cliente faz merge."""
        from services.task_events import SOURCE_TASK_LOG, build_task_payload

        payload = build_task_payload(
            task_id="t1", source=SOURCE_TASK_LOG, progress=50
        )
        assert payload == {"task_id": "t1", "source": SOURCE_TASK_LOG, "progress": 50}

    def test_progresso_e_limitado_a_0_100(self):
        from services.task_events import SOURCE_TASK_LOG, build_task_payload

        acima = build_task_payload(task_id="t", source=SOURCE_TASK_LOG, progress=150)
        abaixo = build_task_payload(task_id="t", source=SOURCE_TASK_LOG, progress=-5)
        assert acima["progress"] == 100
        assert abaixo["progress"] == 0

    def test_progresso_zero_nao_e_omitido(self):
        """0% é informação; `None` é que é ausência."""
        from services.task_events import SOURCE_TASK_LOG, build_task_payload

        payload = build_task_payload(
            task_id="t", source=SOURCE_TASK_LOG, progress=0
        )
        assert payload["progress"] == 0

    def test_enums_saem_como_strings(self):
        from models.task_log import TaskStatus, TaskType
        from services.task_events import SOURCE_TASK_LOG, build_task_payload

        payload = build_task_payload(
            task_id="t", source=SOURCE_TASK_LOG,
            status=TaskStatus.COMPLETED, task_type=TaskType.PDF_GEN,
        )
        assert payload["status"] == "completed"
        assert payload["task_type"] == "PDF_GEN"


class TestEmissao:
    async def test_emite_para_o_dono_da_tarefa(self):
        from services.task_events import SOURCE_TASK_LOG, emit_task_event

        with patch(
            "services.task_events.publish_event", AsyncMock(return_value=True)
        ) as publish:
            ok = await emit_task_event(
                task_id="t1", user_id="user-a", source=SOURCE_TASK_LOG,
                status="processing", progress=30,
            )

        assert ok is True
        assert publish.await_args.args[0] == TASK_PROGRESS
        assert publish.await_args.kwargs["user_id"] == "user-a"

    async def test_tarefa_sem_dono_nao_emite(self):
        """TENANT-SAFETY na origem."""
        from services.task_events import SOURCE_TASK_LOG, emit_task_event

        with patch("services.task_events.publish_event", AsyncMock()) as publish:
            ok = await emit_task_event(
                task_id="t1", user_id=None, source=SOURCE_TASK_LOG, status="processing"
            )

        assert ok is False
        publish.assert_not_awaited()

    async def test_sem_task_id_nao_emite(self):
        from services.task_events import SOURCE_TASK_LOG, emit_task_event

        with patch("services.task_events.publish_event", AsyncMock()) as publish:
            assert await emit_task_event(
                task_id="", user_id="u1", source=SOURCE_TASK_LOG
            ) is False
        publish.assert_not_awaited()

    async def test_falha_de_publicacao_nao_propaga(self):
        from services.task_events import SOURCE_TASK_LOG, emit_task_event

        with patch(
            "services.task_events.publish_event",
            AsyncMock(side_effect=RuntimeError("redis morreu")),
        ):
            assert await emit_task_event(
                task_id="t1", user_id="u1", source=SOURCE_TASK_LOG
            ) is False

    async def test_documento_de_task_log_vira_evento(self):
        from services.task_events import SOURCE_TASK_LOG, emit_task_log_event

        doc = {
            "task_id": "task_abc", "user_id": "user-a", "status": "completed",
            "title": "Motor financeiro", "task_type": "PDF_GEN",
            "progress": 100, "progress_message": "Pronto",
            "process_id": "p1", "result_data": {"document_id": "d1"},
        }
        with patch(
            "services.task_events.publish_event", AsyncMock(return_value=True)
        ) as publish:
            await emit_task_log_event(doc)

        event_type, payload = publish.await_args.args
        assert event_type == TASK_COMPLETED
        assert publish.await_args.kwargs["user_id"] == "user-a"
        assert payload["task_id"] == "task_abc"
        assert payload["source"] == SOURCE_TASK_LOG
        assert payload["progress"] == 100
        assert payload["result"] == {"document_id": "d1"}

    async def test_documento_vazio_nao_emite(self):
        from services.task_events import emit_task_log_event

        with patch("services.task_events.publish_event", AsyncMock()) as publish:
            assert await emit_task_log_event(None) is False
        publish.assert_not_awaited()

    async def test_modelo_pydantic_e_aceite(self):
        """`TaskLogService` devolve `TaskLogResponse`, não dicts."""
        from models.task_log import TaskLogResponse
        from services.task_events import emit_task_log_event

        modelo = TaskLogResponse(
            id="uuid-1", task_id="task_abc", user_id="user-a",
            task_type="PDF_GEN", status="processing", title="Proposta",
            progress=45, created_at="2026-09-21T10:00:00+00:00",
        )
        with patch(
            "services.task_events.publish_event", AsyncMock(return_value=True)
        ) as publish:
            await emit_task_log_event(modelo)

        event_type, payload = publish.await_args.args
        assert event_type == TASK_PROGRESS
        assert payload["status"] == "processing"
        assert payload["progress"] == 45


# ====================================================================
# HELPERS
# ====================================================================


async def _collect(bucket: list, envelope: dict) -> None:
    bucket.append(envelope)
