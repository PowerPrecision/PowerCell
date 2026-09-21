"""
Bateria e2e — IMAP simulado → sync → Pub/Sub → resposta com threading.

Exercita a cadeia COMPLETA do Épico 5 (Webmail Pro & Live Sync) num único
fluxo por teste, em vez de validar cada peça isoladamente:

    email novo no servidor IMAP (falso)
        → sync_user_emails grava-o em db.emails
        → notify_new_email publica no canal Redis
        → route_system_event entrega SÓ ao dono da caixa
        → "Responder" constrói In-Reply-To/References correctos
        → send_email escreve os cabeçalhos RFC 5322 na mensagem

CAMINHOS COBERTOS:
  1. Recepção — o email é gravado e o evento sai para o utilizador certo.
  2. Tenant-safety — o evento de A nunca chega ao WebSocket de B.
  3. Resiliência — Redis em baixo não impede a sincronização.
  4. Threading — a resposta entra na conversa (o bug que este épico fecha).
  5. Agrupamento — original + respostas colapsam numa conversa.
  6. Prova de tempo real — envelopes a viajar por um Redis REAL.

EM `dev` AS LIGAÇÕES IMAP/SMTP SÃO FALSAS, como o enunciado pede: o
servidor IMAP é substituído em `_fetch_all_from_folder_sync` (a fronteira
de rede do sync) e o SMTP em `smtplib`. Tudo o resto é código de produção.

SEM MONGO: usa a `FakeAsyncDatabase` de `tests/unit/conftest.py`. O teste
de Pub/Sub usa um Redis REAL quando existe e é saltado quando não há —
falta de infra-estrutura nunca vira falso negativo.
"""

import asyncio
import os
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.conftest import FakeAsyncDatabase

pytestmark = pytest.mark.integration


# ====================================================================
# CENÁRIO BASE
# ====================================================================

DONO = {
    "id": "u-ana",
    "name": "Ana Consultora",
    "email": "ana@precisioncredito.pt",
    "role": "consultor",
}
OUTRO = {
    "id": "u-bruno",
    "name": "Bruno Intruso",
    "email": "bruno@precisioncredito.pt",
    "role": "consultor",
}

CLIENTE = "cliente@exemplo.pt"
MSG_ID_CLIENTE = "<cliente-001@exemplo.pt>"

CONFIG_EMAIL = {
    "is_configured": True,
    "email_address": DONO["email"],
    "encrypted_password": "cifrada",
    "imap_server": "imap.exemplo.pt",
    "imap_port": 993,
    "smtp_server": "smtp.exemplo.pt",
    "smtp_port": 465,
}


def _email_imap(
    message_id: str = MSG_ID_CLIENTE,
    subject: str = "Pedido de simulação de crédito",
    in_reply_to: str | None = None,
    references: list | None = None,
) -> dict:
    """Um email como o `_fetch_all_from_folder_sync` o devolve."""
    return {
        "message_id": message_id,
        "from_email": CLIENTE,
        "to_emails": [DONO["email"]],
        "cc_emails": [],
        "subject": subject,
        "body": "Bom dia, gostaria de simular um crédito habitação.",
        "body_html": "",
        "attachments": [],
        "date": "2026-09-21T09:00:00+00:00",
        "direction": "received",
        "source": "webmail_sync",
        "account": "user_u-ana",
        "in_reply_to": in_reply_to,
        "references": references or [],
    }


@pytest.fixture
def db():
    base = FakeAsyncDatabase()
    # deepcopy: os dicts de cenário são de módulo e não podem vazar
    # mutações de um teste para o seguinte.
    base.users.docs.extend(deepcopy([DONO, OUTRO]))
    return base


@pytest.fixture
def eventos():
    """Intercepta `publish_event` e devolve os envelopes emitidos."""
    capturados = []

    async def _publish(event_type, payload, *, user_id, company_id=None):
        capturados.append(
            {
                "type": event_type,
                "user_id": user_id,
                "company_id": company_id,
                "payload": payload,
            }
        )
        return True

    return capturados, _publish


class _ArnesSync:
    """Substitui a rede (IMAP + cifra) e deixa o resto do sync intacto."""

    def __init__(self, db, caixa_imap=None, publish=None, erro_ligacao=None):
        self.db = db
        self.caixa_imap = caixa_imap if caixa_imap is not None else [_email_imap()]
        self.publish = publish
        self.erro_ligacao = erro_ligacao
        self._patches = []

    def __enter__(self):
        from services import email_realtime, email_service

        def _fetch(account, folder="INBOX", since_days=30, max_emails=100):
            if self.erro_ligacao:
                return {"emails": [], "connection_error": self.erro_ligacao}
            # Só a INBOX traz mensagens: Enviados/Rascunhos/Lixo vazios.
            if folder.upper() != "INBOX":
                return {"emails": [], "connection_error": None}
            return {"emails": deepcopy(self.caixa_imap), "connection_error": None}

        alvos = [
            patch("database.db", self.db),
            patch.object(email_service, "db", self.db),
            patch.object(email_service, "_fetch_all_from_folder_sync", _fetch),
            # `encryption_service` é importado DENTRO da função de sync
            # (`from services.encryption import ...`), por isso patchar o
            # módulo email_service não chegaria — tem de ser na origem.
            patch(
                "services.encryption.encryption_service.decrypt",
                lambda _v: "segredo",
            ),
        ]
        if self.publish is not None:
            alvos.append(patch.object(email_realtime, "publish_event", self.publish))

        for alvo in alvos:
            alvo.start()
            self._patches.append(alvo)

        # Kill switch do sync: em `dev` está desligado por defeito.
        self._env_anterior = os.environ.get("EMAIL_SYNC_ENABLED")
        os.environ["EMAIL_SYNC_ENABLED"] = "true"
        return self

    def __exit__(self, *exc):
        for alvo in reversed(self._patches):
            alvo.stop()
        self._patches.clear()
        if self._env_anterior is None:
            os.environ.pop("EMAIL_SYNC_ENABLED", None)
        else:
            os.environ["EMAIL_SYNC_ENABLED"] = self._env_anterior
        return False


async def _sincronizar(db, **kwargs):
    """Corre o sync real do utilizador dono da caixa."""
    from services.email_service import sync_user_emails

    with _ArnesSync(db, **kwargs) as arnes:
        resultado = await sync_user_emails(
            DONO["id"], days=7, max_emails=50, resolved_config=dict(CONFIG_EMAIL)
        )
    return resultado, arnes


# ====================================================================
# CENÁRIO 1 — RECEPÇÃO: email gravado + evento para o dono
# ====================================================================


class TestRecepcaoEmTempoReal:
    async def test_email_do_imap_e_gravado_e_anuncia_se(self, db, eventos):
        capturados, publish = eventos

        resultado, _ = await _sincronizar(db, publish=publish)

        assert resultado["success"] is True
        assert resultado["total_synced"] == 1

        gravado = await db.emails.find_one({"message_id": MSG_ID_CLIENTE})
        assert gravado is not None, "o email tem de ficar na BD"
        assert gravado["from_email"] == CLIENTE
        assert gravado["synced_for_user"] == DONO["id"]
        assert gravado["is_read"] is False, "um email recebido chega por ler"

        # O evento saiu — e para o dono da caixa.
        assert len(capturados) == 1
        evento = capturados[0]
        assert evento["type"] == "new_email"
        assert evento["user_id"] == DONO["id"]

    async def test_payload_traz_o_suficiente_para_a_lista(self, db, eventos):
        """O evento é um sinal — mas com o que a linha precisa de mostrar."""
        capturados, publish = eventos

        await _sincronizar(db, publish=publish)

        payload = capturados[0]["payload"]
        assert payload["from_email"] == CLIENTE
        assert payload["subject"] == "Pedido de simulação de crédito"
        assert payload["folder"] == "inbox"
        assert payload["is_read"] is False, "o contador incrementa sem ir ao servidor"
        assert payload["email_id"], "sem id a lista não sabe deduplicar"

    async def test_email_ja_conhecido_nao_volta_a_anunciar(self, db, eventos):
        """Sincronizar duas vezes não pode duplicar linhas nem eventos."""
        capturados, publish = eventos

        await _sincronizar(db, publish=publish)
        segunda, _ = await _sincronizar(db, publish=publish)

        assert segunda["total_synced"] == 0
        assert segunda["total_duplicates"] == 1
        assert len(capturados) == 1, "o segundo sync não anuncia nada de novo"

        todos = [e async for e in db.emails.find({"message_id": MSG_ID_CLIENTE})]
        assert len(todos) == 1

    async def test_caixa_vazia_nao_gera_ruido(self, db, eventos):
        capturados, publish = eventos

        resultado, _ = await _sincronizar(db, caixa_imap=[], publish=publish)

        assert resultado["total_synced"] == 0
        assert capturados == []


# ====================================================================
# CENÁRIO 2 — TENANT-SAFETY
# ====================================================================


class TestIsolamentoEntreUtilizadores:
    async def test_evento_nunca_e_endereçado_a_outro_utilizador(self, db, eventos):
        capturados, publish = eventos

        await _sincronizar(db, publish=publish)

        destinatarios = {e["user_id"] for e in capturados}
        assert destinatarios == {DONO["id"]}
        assert OUTRO["id"] not in destinatarios

    async def test_router_descarta_envelope_sem_destinatario(self):
        """Fail-closed: sem `user_id` o evento é deitado fora, não difundido."""
        from services import websocket_manager

        gestor = MagicMock()
        gestor.is_user_connected = MagicMock(return_value=True)
        gestor.send_personal_message = AsyncMock()
        gestor.broadcast = AsyncMock()

        with patch.object(websocket_manager, "manager", gestor):
            entregue = await websocket_manager.route_system_event(
                {"id": "x", "type": "new_email", "payload": {"email_id": "e1"}}
            )

        assert entregue is False
        gestor.send_personal_message.assert_not_awaited()
        gestor.broadcast.assert_not_awaited()

    async def test_router_entrega_apenas_ao_dono(self):
        from services import redis_pubsub, websocket_manager

        entregues = {DONO["id"]: [], OUTRO["id"]: []}
        gestor = MagicMock()
        gestor.is_user_connected = MagicMock(side_effect=lambda uid: uid in entregues)
        gestor.send_personal_message = AsyncMock(
            side_effect=lambda msg, uid: entregues[uid].append(msg)
        )

        envelope = redis_pubsub.build_event_envelope(
            "new_email", {"email_id": "e1", "subject": "Privado"}, user_id=DONO["id"]
        )

        with patch.object(websocket_manager, "manager", gestor):
            assert await websocket_manager.route_system_event(envelope) is True

        assert len(entregues[DONO["id"]]) == 1
        assert entregues[DONO["id"]][0]["data"]["subject"] == "Privado"
        assert entregues[OUTRO["id"]] == [], "o Bruno não pode ver o email da Ana"


# ====================================================================
# CENÁRIO 3 — RESILIÊNCIA
# ====================================================================


class TestResiliencia:
    async def test_redis_em_baixo_nao_impede_a_sincronizacao(self, db):
        """Sem Redis o email grava-se na mesma — só se perde o tempo real."""
        from services import redis_pubsub

        with patch.object(redis_pubsub, "_get_publisher", AsyncMock(return_value=None)):
            resultado, _ = await _sincronizar(db)

        assert resultado["success"] is True
        assert resultado["total_synced"] == 1
        assert await db.emails.find_one({"message_id": MSG_ID_CLIENTE}) is not None

    async def test_falha_a_publicar_nao_rebenta_o_sync(self, db):
        """Uma excepção no transporte não pode propagar para o sync."""

        async def _publish_rebenta(*_a, **_kw):
            raise RuntimeError("canal morto")

        resultado, _ = await _sincronizar(db, publish=_publish_rebenta)

        assert resultado["total_synced"] == 1
        assert await db.emails.find_one({"message_id": MSG_ID_CLIENTE}) is not None

    async def test_imap_inacessivel_reporta_sem_encravar(self, db, eventos):
        capturados, publish = eventos

        resultado, _ = await _sincronizar(
            db, erro_ligacao="Connection refused", publish=publish
        )

        assert resultado["total_synced"] == 0
        assert capturados == [], "sem email novo não há nada a anunciar"


# ====================================================================
# CENÁRIO 4 — THREADING (o bug que o épico fecha)
# ====================================================================


class TestRespostaEntraNaConversa:
    async def test_responder_preenche_in_reply_to_e_references(self, db, eventos):
        """O fluxo do enunciado: receber → responder → verificar cabeçalhos."""
        from services.email_threading import build_reference_chain, normalize_message_id

        _capturados, publish = eventos
        await _sincronizar(db, publish=publish)

        original = await db.emails.find_one({"message_id": MSG_ID_CLIENTE})

        # O compositor responde ao email recebido (mesma regra do frontend
        # em utils/emailThreads.buildReplyThreadHeaders).
        in_reply_to = normalize_message_id(original["message_id"])
        references = build_reference_chain(in_reply_to, original.get("references"))

        assert in_reply_to == MSG_ID_CLIENTE
        assert references == [MSG_ID_CLIENTE], "a resposta aponta ao pai"

    async def test_send_email_escreve_os_cabecalhos_rfc5322(self, db):
        """Prova no fio: a mensagem SMTP sai com In-Reply-To e Message-ID."""
        from services import email_service

        enviadas = []

        class _SMTPFalso:
            """Servidor SMTP falso — captura a mensagem tal como sai para a rede.

            O `send_email` usa `sendmail(from, to, msg.as_string())`, pelo
            que o que aqui se lê é a mensagem SERIALIZADA. Reparsá-la é o
            teste mais honesto disponível sem um servidor a sério: prova
            que os cabeçalhos sobrevivem à serialização, não apenas que
            foram postos no objecto.
            """

            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def login(self, *a, **kw):
                pass

            def send_message(self, msg, *a, **kw):
                enviadas.append(msg)

            def sendmail(self, _de, _para, raw, *a, **kw):
                import email as _email

                enviadas.append(_email.message_from_string(raw))

            def quit(self):
                pass

            def starttls(self, *a, **kw):
                pass

        conta = email_service.EmailAccount(
            name="user_ana",
            imap_server="imap.exemplo.pt",
            imap_port=993,
            smtp_server="smtp.exemplo.pt",
            smtp_port=465,
            email=DONO["email"],
            password="segredo",
        )

        with patch("database.db", db), \
             patch.object(email_service, "db", db), \
             patch.object(email_service.smtplib, "SMTP_SSL", _SMTPFalso), \
             patch.object(email_service.smtplib, "SMTP", _SMTPFalso), \
             patch.object(
                 email_service, "_get_email_account_for_email",
                 AsyncMock(return_value=conta)
             ), \
             patch.object(
                 email_service, "get_email_accounts_async",
                 AsyncMock(return_value=[conta])
             ):
            resultado = await email_service.send_email(
                account_name="user_ana",
                to_emails=[CLIENTE],
                subject="Re: Pedido de simulação de crédito",
                body="Com certeza. Envio em anexo a simulação.",
                from_email=DONO["email"],
                account_override=conta,
                # O `send_email` só arquiva em db.emails quando o envio
                # está ligado a um processo (sem processo, a mensagem
                # volta pelo sync da pasta Enviados). Uma resposta do CRM
                # ao cliente tem processo — é o caso que interessa provar.
                process_id="proc-ch-001",
                created_by=DONO["id"],
                in_reply_to=MSG_ID_CLIENTE,
                references=[MSG_ID_CLIENTE],
            )

        assert resultado.get("success") is True, resultado
        assert enviadas, "nenhuma mensagem chegou ao SMTP"
        msg = enviadas[-1]

        assert msg["In-Reply-To"] == MSG_ID_CLIENTE, (
            "sem In-Reply-To a resposta nasce fora da conversa"
        )
        assert MSG_ID_CLIENTE in (msg["References"] or "")
        assert msg["Message-ID"], (
            "sem Message-ID próprio, a resposta do cliente não tem a que "
            "se agarrar — a conversa parte-se na volta seguinte"
        )
        assert msg["Message-ID"].endswith("@precisioncredito.pt>")

        # E o que ficou gravado permite threading na volta seguinte.
        gravado = await db.emails.find_one({"direction": "sent"})
        assert gravado["message_id"] == msg["Message-ID"]
        assert gravado["in_reply_to"] == MSG_ID_CLIENTE

    async def test_resposta_do_cliente_reata_a_conversa(self, db, eventos):
        """A volta completa: recebemos, respondemos, o cliente responde."""
        from services.email_threading import thread_key

        _capturados, publish = eventos
        await _sincronizar(db, publish=publish)

        nossa_resposta = "<nossa-001@precisioncredito.pt>"
        resposta_cliente = _email_imap(
            message_id="<cliente-002@exemplo.pt>",
            subject="Re: Pedido de simulação de crédito",
            in_reply_to=nossa_resposta,
            references=[MSG_ID_CLIENTE, nossa_resposta],
        )
        await _sincronizar(db, caixa_imap=[resposta_cliente], publish=publish)

        original = await db.emails.find_one({"message_id": MSG_ID_CLIENTE})
        seguimento = await db.emails.find_one({"message_id": "<cliente-002@exemplo.pt>"})

        assert thread_key(seguimento) == thread_key(original) == MSG_ID_CLIENTE, (
            "as duas mensagens têm de cair na MESMA conversa"
        )

    async def test_conversa_colapsa_em_uma_linha(self, db, eventos):
        """5 mensagens da mesma troca = 1 linha na caixa de entrada."""
        from services.email_threading import thread_key

        _capturados, publish = eventos

        troca = [_email_imap()]
        anterior = MSG_ID_CLIENTE
        for i in range(2, 6):
            msg_id = f"<cliente-00{i}@exemplo.pt>"
            troca.append(
                _email_imap(
                    message_id=msg_id,
                    subject="Re: Pedido de simulação de crédito",
                    in_reply_to=anterior,
                    references=[MSG_ID_CLIENTE, anterior] if anterior != MSG_ID_CLIENTE else [MSG_ID_CLIENTE],
                )
            )
            anterior = msg_id

        await _sincronizar(db, caixa_imap=troca, publish=publish)

        gravados = [e async for e in db.emails.find({})]
        assert len(gravados) == 5

        chaves = {thread_key(e) for e in gravados}
        assert chaves == {MSG_ID_CLIENTE}, (
            f"5 mensagens deviam dar 1 conversa, deram {len(chaves)}"
        )


# ====================================================================
# CENÁRIO 5 — PROVA DE TEMPO REAL (Redis a sério)
# ====================================================================


def _redis_url() -> str:
    return os.environ.get("REDIS_URL") or "redis://localhost:6379"


async def _redis_disponivel() -> bool:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(_redis_url(), socket_connect_timeout=1)
        await asyncio.wait_for(client.ping(), timeout=2)
        await client.aclose()
        return True
    except Exception:
        return False


class TestTempoRealComRedis:
    """O evento viaja MESMO pelo Redis até ao WebSocket do destinatário.

    Saltado quando não há Redis alcançável — a ausência de infra-estrutura
    não pode transformar-se num falso negativo.
    """

    @pytest.fixture
    async def redis_vivo(self):
        if not await _redis_disponivel():
            pytest.skip("Redis indisponível — prova de tempo real saltada")
        from services import redis_pubsub

        redis_pubsub._publisher = None
        redis_pubsub._publisher_available = None
        os.environ.setdefault("REDIS_URL", _redis_url())
        yield
        await redis_pubsub.reset_publisher()

    async def test_email_novo_chega_ao_browser_do_dono(self, redis_vivo, db):
        from services import redis_pubsub, websocket_manager

        entregues = {DONO["id"]: [], OUTRO["id"]: []}
        gestor = MagicMock()
        gestor.is_user_connected = MagicMock(side_effect=lambda uid: uid in entregues)
        gestor.send_personal_message = AsyncMock(
            side_effect=lambda msg, uid: entregues[uid].append(msg)
        )

        with patch.object(websocket_manager, "manager", gestor):
            listener = redis_pubsub.SystemEventListener(
                websocket_manager.route_system_event
            )
            assert listener.start()
            await asyncio.sleep(1.0)  # dar tempo ao SUBSCRIBE
            assert listener.is_connected

            try:
                # Fluxo real: o sync emite, ninguém intercepta a publicação.
                await _sincronizar(db)
                await asyncio.sleep(1.0)  # propagação pelo canal
            finally:
                await listener.stop()

        recebidos = entregues[DONO["id"]]
        assert recebidos, "o evento não chegou pelo Redis"

        tipos = [m["type"] for m in recebidos]
        assert "new_email" in tipos

        dados = [m["data"] for m in recebidos if m["type"] == "new_email"]
        assert any(d.get("from_email") == CLIENTE for d in dados)
        assert all(d.get("folder") == "inbox" for d in dados)

        # TENANT-SAFETY sobre infra-estrutura real, não sobre um duplo.
        assert entregues[OUTRO["id"]] == [], (
            "o email da Ana apareceu no WebSocket do Bruno"
        )
