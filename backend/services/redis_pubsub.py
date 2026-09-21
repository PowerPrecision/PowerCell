"""
Camada Pub/Sub de eventos de sistema (Redis) — arquitectura Event-Driven.

ÉPICO "Refatorização para Event-Driven": tarefas pesadas (importações,
análises IA, envio de emails, extracção de documentos, motor financeiro)
deixam de escrever apenas na base de dados e passam a **publicar eventos**
num canal Redis. O ``websocket_manager`` subscreve esse canal e retransmite
cada evento, em tempo real, apenas para as ligações WebSocket do destinatário.

PORQUÊ UM MÓDULO NOVO E NÃO ``redis_cache.py``:
    ``redis_cache`` fala com o Upstash pela **API REST** (``upstash_redis``),
    que é request/response: não mantém ligação aberta, logo **não suporta
    SUBSCRIBE**. Além disso, fora de produção devolve um ``InMemoryCache``.
    Pub/Sub exige uma ligação persistente, por isso este módulo usa
    ``redis.asyncio`` (já em ``requirements.txt``) contra o ``REDIS_URL`` —
    o mesmo Redis real que o ARQ já utiliza (``worker/config.py``).
    Os dois coexistem: cache no Upstash REST, eventos no Redis real.

O PROBLEMA QUE ISTO RESOLVE (além do polling):
    ``ConnectionManager`` é um dicionário **em memória, por processo**. Com
    mais do que um worker Uvicorn, uma tarefa a correr no worker A não
    consegue alcançar um WebSocket aberto no worker B — hoje esses eventos
    perdem-se em silêncio. O canal Redis é o barramento que liga os workers.
    Por isso o listener arranca em **todos** os workers (ao contrário dos
    schedulers, que são exclusivos do worker primário).

ISOLAMENTO DE DADOS (TENANT-SAFETY):
    Todo o envelope transporta ``user_id`` — o destinatário. O router
    (``websocket_manager.route_system_event``) entrega exclusivamente às
    ligações desse utilizador. Um envelope **sem** ``user_id`` é
    **descartado**, nunca difundido: falha fechada, nunca aberta. O
    ``company_id`` viaja como contexto para filtros no cliente e auditoria,
    nunca como critério de entrega mais largo.

DEGRADAÇÃO GRACIOSA (RESILIÊNCIA):
    Nada aqui levanta excepção para o chamador. Se o Redis estiver em baixo,
    ausente ou por configurar:
      - ``publish_event`` entrega o evento **directamente ao manager local**
        (entrega in-process), devolve ``False`` e segue;
      - o listener fica em retry com backoff exponencial, sem ruído de logs;
      - o frontend detecta a ausência de WebSocket e retoma o polling.
    As operações HTTP core nunca falham por causa desta camada.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# ====================================================================
# CONFIGURAÇÃO
# ====================================================================

# Canal dedicado aos eventos de sistema (configurável por ambiente para
# permitir isolar staging/produção no mesmo Redis).
SYSTEM_EVENTS_CHANNEL = os.environ.get(
    "SYSTEM_EVENTS_CHANNEL", "powercell_system_events"
)

# Ligação: reutiliza o REDIS_URL do ARQ (uma única infra-estrutura Redis).
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Timeouts curtos: publicar um evento nunca pode segurar um pedido HTTP.
PUBLISH_TIMEOUT_SECONDS = float(os.environ.get("PUBSUB_PUBLISH_TIMEOUT", "2"))
CONNECT_TIMEOUT_SECONDS = float(os.environ.get("PUBSUB_CONNECT_TIMEOUT", "5"))

# Backoff do listener quando o Redis está inacessível.
RECONNECT_INITIAL_SECONDS = 1.0
RECONNECT_MAX_SECONDS = 30.0

# Limite defensivo do payload (um evento é um sinal, não um transporte de
# dados; payloads grandes pertencem a um GET subsequente).
MAX_PAYLOAD_BYTES = 32 * 1024


# ====================================================================
# TIPOS DE EVENTO DE TAREFA (contrato com o frontend)
# ====================================================================

TASK_STARTED = "task_started"
TASK_PROGRESS = "task_progress"
TASK_COMPLETED = "task_completed"
TASK_FAILED = "task_failed"

TASK_EVENT_TYPES = frozenset(
    {TASK_STARTED, TASK_PROGRESS, TASK_COMPLETED, TASK_FAILED}
)


# ====================================================================
# TIPOS DE EVENTO DE EMAIL (contrato com o Webmail)
# ====================================================================
# O nome do evento na rede é `new_email` e NÃO `email_received`: o
# dispatcher do frontend (`useWebSocket` → `onNewEmail`) já escuta este
# tipo desde o Pacote EC. Inventar um segundo nome para o mesmo facto
# obrigaria os dois lados a conhecer ambos, sem ganho nenhum.
#
# O que muda com o Épico 5 não é o nome — é o TRANSPORTE: este evento
# passava só pelo ConnectionManager em memória (logo, morria no worker
# onde a sincronização IMAP corria) e passa agora por este canal, que
# todos os workers escutam.

NEW_EMAIL = "new_email"

EMAIL_EVENT_TYPES = frozenset({NEW_EMAIL})


# ====================================================================
# ESTADO (singleton por processo)
# ====================================================================

_publisher = None                      # redis.asyncio.Redis | None
_publisher_available: Optional[bool] = None   # None = por determinar
_publisher_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """Lock criado preguiçosamente (o event loop pode não existir no import)."""
    global _publisher_lock
    if _publisher_lock is None:
        _publisher_lock = asyncio.Lock()
    return _publisher_lock


def is_configured() -> bool:
    """True se há um ``REDIS_URL`` utilizável configurado no ambiente.

    Um ``REDIS_URL`` ausente é tratado como "Pub/Sub desligado": o sistema
    funciona na mesma, com entrega in-process (suficiente num só worker,
    que é o caso típico em desenvolvimento).
    """
    return bool(os.environ.get("REDIS_URL"))


async def _get_publisher():
    """Cliente Redis para publicação (singleton, com circuit breaker).

    Returns:
        Cliente ``redis.asyncio.Redis`` ou ``None`` quando indisponível.
        Nunca levanta excepção.
    """
    global _publisher, _publisher_available

    if _publisher_available is False:
        return None
    if _publisher is not None:
        return _publisher

    if not is_configured():
        if _publisher_available is None:
            logger.info(
                "[PUBSUB] REDIS_URL não configurado — eventos entregues "
                "apenas in-process (sem fan-out entre workers)"
            )
        _publisher_available = False
        return None

    async with _get_lock():
        if _publisher is not None:
            return _publisher
        if _publisher_available is False:
            return None
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
                socket_timeout=PUBLISH_TIMEOUT_SECONDS,
                health_check_interval=30,
            )
            await asyncio.wait_for(
                client.ping(), timeout=CONNECT_TIMEOUT_SECONDS
            )
            _publisher = client
            _publisher_available = True
            logger.info(
                f"[PUBSUB] Publicador ligado ao Redis "
                f"(canal '{SYSTEM_EVENTS_CHANNEL}')"
            )
            return _publisher
        except Exception as e:
            logger.warning(
                f"[PUBSUB] Redis indisponível para publicação "
                f"({type(e).__name__}: {e}) — entrega in-process apenas"
            )
            _publisher_available = False
            return None


async def reset_publisher() -> None:
    """Fecha o publicador e limpa o circuit breaker (usado no shutdown/testes)."""
    global _publisher, _publisher_available
    client, _publisher = _publisher, None
    _publisher_available = None
    if client is not None:
        try:
            await client.aclose()
        except Exception:  # pragma: no cover — fecho best-effort
            pass


# ====================================================================
# ENVELOPE
# ====================================================================


def build_event_envelope(
    event_type: str,
    payload: dict,
    *,
    user_id: str,
    company_id: Optional[str] = None,
) -> dict:
    """Constrói o envelope canónico de um evento de sistema.

    O ``user_id`` é o **destinatário**, não o autor: é por ele que o router
    decide para que ligações WebSocket o evento vai. Sem ele o evento não é
    entregável e será descartado a jusante.

    Returns:
        ``{"id", "type", "user_id", "company_id", "payload", "published_at"}``
    """
    return {
        "id": uuid.uuid4().hex,
        "type": event_type,
        "user_id": str(user_id) if user_id else None,
        "company_id": str(company_id) if company_id else None,
        "payload": payload or {},
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def is_deliverable(envelope: dict) -> bool:
    """True se o envelope tem destinatário e tipo — requisito de tenant-safety.

    Um envelope sem ``user_id`` não é difundido para todos: é descartado.
    Esta é a garantia de que um evento do utilizador A nunca aparece no
    WebSocket do utilizador B por omissão de campo.
    """
    if not isinstance(envelope, dict):
        return False
    return bool(envelope.get("user_id")) and bool(envelope.get("type"))


def serialize_envelope(envelope: dict) -> Optional[str]:
    """Serializa o envelope para JSON, recusando payloads desproporcionados.

    Returns:
        String JSON, ou ``None`` se não for serializável ou exceder
        ``MAX_PAYLOAD_BYTES`` (o evento é um sinal; dados grandes vêm por
        um GET subsequente).
    """
    try:
        raw = json.dumps(envelope, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        logger.warning(f"[PUBSUB] Envelope não serializável: {e}")
        return None
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        logger.warning(
            f"[PUBSUB] Evento '{envelope.get('type')}' excede "
            f"{MAX_PAYLOAD_BYTES} bytes — descartado"
        )
        return None
    return raw


def parse_envelope(raw: Any) -> Optional[dict]:
    """Desserializa uma mensagem vinda do canal Redis.

    Returns:
        Envelope válido e entregável, ou ``None`` (mensagem corrompida, de
        outro produtor, ou sem destinatário). Nunca levanta excepção — uma
        mensagem má não pode derrubar o listener.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        envelope = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.debug("[PUBSUB] Mensagem ignorada (JSON inválido)")
        return None
    if not is_deliverable(envelope):
        logger.warning(
            "[PUBSUB] Evento descartado por falta de destinatário "
            f"(type={envelope.get('type') if isinstance(envelope, dict) else '?'})"
        )
        return None
    return envelope


# ====================================================================
# PUBLICAÇÃO
# ====================================================================


async def publish_envelope(envelope: dict) -> bool:
    """Publica um envelope já construído no canal de eventos.

    Returns:
        ``True`` se foi publicado no Redis (fan-out entre workers),
        ``False`` se o Redis não estava disponível ou o envelope era
        inválido. **Nunca levanta excepção** — publicar um evento não pode
        fazer falhar a operação de negócio que o originou.
    """
    if not is_deliverable(envelope):
        logger.warning(
            "[PUBSUB] Publicação recusada: envelope sem user_id/type "
            "(tenant-safety)"
        )
        return False

    raw = serialize_envelope(envelope)
    if raw is None:
        return False

    client = await _get_publisher()
    if client is None:
        return False

    try:
        await asyncio.wait_for(
            client.publish(SYSTEM_EVENTS_CHANNEL, raw),
            timeout=PUBLISH_TIMEOUT_SECONDS,
        )
        return True
    except Exception as e:
        # Uma falha de publicação marca o circuit breaker para que os
        # eventos seguintes não paguem o timeout outra vez.
        global _publisher_available
        logger.warning(
            f"[PUBSUB] Falha ao publicar '{envelope.get('type')}' "
            f"({type(e).__name__}: {e})"
        )
        _publisher_available = False
        return False


async def publish_event(
    event_type: str,
    payload: dict,
    *,
    user_id: str,
    company_id: Optional[str] = None,
    deliver_locally: bool = True,
) -> bool:
    """Publica um evento de sistema para um destinatário.

    Este é o ponto de entrada usado pelos emissores (TaskLog, background
    jobs, importações). É deliberadamente tolerante: um evento perdido
    degrada a UI para polling, nunca quebra a tarefa.

    Args:
        event_type: Tipo do evento (``task_started``/``task_progress``/…).
        payload: Dados do evento (pequeno — é um sinal, não um transporte).
        user_id: **Destinatário**. Obrigatório (tenant-safety).
        company_id: Empresa associada, para contexto/filtros no cliente.
        deliver_locally: Quando ``True`` (defeito) e o Redis não estiver
            disponível, entrega o evento directamente ao manager deste
            processo — garante tempo real num único worker sem Redis.

    Returns:
        ``True`` se seguiu pelo Redis; ``False`` se degradou (entrega local
        ou perdido). O chamador não precisa de reagir ao resultado.
    """
    if not user_id:
        logger.warning(
            f"[PUBSUB] Evento '{event_type}' sem user_id — descartado "
            "(um evento sem destinatário nunca é difundido)"
        )
        return False

    envelope = build_event_envelope(
        event_type, payload, user_id=user_id, company_id=company_id
    )

    published = await publish_envelope(envelope)
    if published:
        return True

    if deliver_locally:
        # Redis em baixo / por configurar: as ligações WebSocket deste
        # processo ainda são alcançáveis. Melhor tempo real parcial do que
        # nenhum. Noutros workers, o frontend cai para polling.
        await _deliver_locally(envelope)

    return False


async def _deliver_locally(envelope: dict) -> None:
    """Entrega directa ao manager deste processo (bypass do Redis)."""
    try:
        from services.websocket_manager import route_system_event

        await route_system_event(envelope)
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.debug(f"[PUBSUB] Entrega in-process falhou: {e}")


# ====================================================================
# SUBSCRIÇÃO (listener com reconexão)
# ====================================================================


class SystemEventListener:
    """Subscritor do canal de eventos, com reconexão e backoff exponencial.

    Corre como background task no arranque do servidor, **em cada worker**
    (cada um tem as suas próprias ligações WebSocket para servir).

    O ciclo nunca termina por erro: uma queda do Redis leva a esperar e
    tentar de novo, com backoff até ``RECONNECT_MAX_SECONDS``. Só um
    ``stop()`` explícito (shutdown) encerra o listener.
    """

    def __init__(
        self,
        handler: Callable[[dict], Awaitable[None]],
        *,
        channel: str = SYSTEM_EVENTS_CHANNEL,
    ):
        self._handler = handler
        self._channel = channel
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False
        self._events_received = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def events_received(self) -> int:
        return self._events_received

    def start(self) -> bool:
        """Arranca o listener em background. Idempotente.

        Returns:
            ``True`` se arrancou (ou já corria); ``False`` se não há Redis
            configurado — nesse caso o sistema fica em entrega in-process.
        """
        if self._running:
            return True
        if not is_configured():
            logger.info(
                "[PUBSUB] Listener não arrancou: REDIS_URL por configurar "
                "(entrega in-process continua activa)"
            )
            return False
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"[PUBSUB] Listener arrancado no canal '{self._channel}'")
        return True

    async def stop(self) -> None:
        """Pára o listener e liberta a ligação (shutdown do servidor)."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self._connected = False
        logger.info("[PUBSUB] Listener parado")

    async def _run(self) -> None:
        """Ciclo de subscrição com reconexão (nunca termina por erro)."""
        delay = RECONNECT_INITIAL_SECONDS
        while self._running:
            try:
                await self._listen_once()
                delay = RECONNECT_INITIAL_SECONDS  # ligação saudável
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._connected = False
                logger.warning(
                    f"[PUBSUB] Listener desligado ({type(e).__name__}: {e}); "
                    f"nova tentativa em {delay:.0f}s"
                )
            if not self._running:
                break
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)

    async def _listen_once(self) -> None:
        """Uma sessão de subscrição — retorna quando a ligação cai."""
        import redis.asyncio as aioredis

        client = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
            health_check_interval=30,
        )
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        try:
            await pubsub.subscribe(self._channel)
            self._connected = True
            logger.info(f"[PUBSUB] Subscrito a '{self._channel}'")

            async for message in pubsub.listen():
                if not self._running:
                    break
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "message":
                    continue
                await self._dispatch(message.get("data"))
        finally:
            self._connected = False
            try:
                await pubsub.aclose()
            except Exception:  # pragma: no cover
                pass
            try:
                await client.aclose()
            except Exception:  # pragma: no cover
                pass

    async def _dispatch(self, raw: Any) -> None:
        """Faz parse e entrega ao handler; um erro nunca mata o listener."""
        envelope = parse_envelope(raw)
        if envelope is None:
            return
        self._events_received += 1
        try:
            await self._handler(envelope)
        except Exception as e:
            logger.warning(
                f"[PUBSUB] Handler falhou para '{envelope.get('type')}': "
                f"{type(e).__name__}: {e}"
            )


# Listener global (arrancado no startup do servidor, um por worker)
_listener: Optional[SystemEventListener] = None


def get_listener() -> SystemEventListener:
    """Listener singleton deste processo, ligado ao router do WebSocket."""
    global _listener
    if _listener is None:
        from services.websocket_manager import route_system_event

        _listener = SystemEventListener(route_system_event)
    return _listener


async def start_system_event_listener() -> bool:
    """Arranca o listener deste worker (chamado no startup do servidor)."""
    return get_listener().start()


async def stop_system_event_listener() -> None:
    """Pára o listener e fecha o publicador (shutdown do servidor)."""
    global _listener
    if _listener is not None:
        await _listener.stop()
        _listener = None
    await reset_publisher()


async def health_check() -> dict:
    """Estado da camada Pub/Sub, para diagnósticos."""
    listener = _listener
    return {
        "configured": is_configured(),
        "channel": SYSTEM_EVENTS_CHANNEL,
        "publisher_available": bool(_publisher_available),
        "listener_running": bool(listener and listener.is_running),
        "listener_connected": bool(listener and listener.is_connected),
        "events_received": listener.events_received if listener else 0,
    }
