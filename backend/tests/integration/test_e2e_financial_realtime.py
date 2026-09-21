"""
Bateria e2e — Indexação → Atribuição → Motor Financeiro → Eventos em tempo real.

Exercita a cadeia COMPLETA introduzida pelos Épicos 2 (Motor de Simulação
Financeira) e 4 (Event-Driven via Redis Pub/Sub), num único fluxo por teste,
em vez de validar cada peça isoladamente:

    documentos indexados
        → POST mark-indexed
        → dupla auto-atribuição (consultor + intermediário)
        → motor financeiro em background
        → extracção → DSTI → Euribor → 3 cenários
        → PDF → S3 → separador Documentos
        → eventos `task_*` no canal Redis → WebSocket do dono

CAMINHOS COBERTOS:
  1. Caminho feliz (IRS + recibo legíveis).
  2. Falha de OCR — IRS ilegível: o sistema não encrava, a indexação NÃO é
     revertida e o processo fica marcado para revisão manual.
  3. Falha de serviços — Euribor em baixo (fallback ao spread contratado) e
     S3 em baixo (proposta não arquivada → revisão manual).
  4. Prova de tempo real — os envelopes viajam mesmo pelo Redis e chegam com
     `user_id` e `process_id` correctos, sem cruzar utilizadores.

SEM MONGO: usa a `FakeAsyncDatabase` de `tests/unit/conftest.py`, pelo que
corre em qualquer job. O teste de Pub/Sub usa um Redis REAL quando existe um
em `REDIS_URL`/localhost e é saltado (skip) quando não há — nunca falha por
falta de infra-estrutura.
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

CONSULTOR = {"id": "u-consultor", "name": "Carla Consultora"}
MEDIADOR = {"id": "u-mediador", "name": "Mário Mediador"}
INDEXADOR = {
    "id": "u-indexador",
    "name": "Inês Índice",
    "email": "indice@precisioncredito.pt",
    "role": "indexacao",
}
OUTRO_UTILIZADOR = {"id": "u-intruso", "name": "Intruso"}

PROCESS_ID = "proc-ch-e2e"

# Taxas Euribor de referência usadas quando o cenário não testa a Euribor.
EURIBOR_ESTAVEL = {
    "euribor_1m": 2.30, "euribor_3m": 2.35, "euribor_6m": 2.40,
    "euribor_12m": 2.45, "fetched_at": "2026-09-21T08:00:00+00:00",
    "is_fallback": False, "source": "api",
}


def _processo_credito_habitacao() -> dict:
    """Processo de CH pronto a indexar: com imóvel, crédito e sem atribuição."""
    return {
        "id": PROCESS_ID,
        "process_number": "P-2026-0042",
        "client_name": "Ana Silva",
        "company_id": "empresa-1",
        "process_type": "credito_habitacao",
        "status": "pre_registo",
        "is_indexed": False,
        "assigned_indexacao_id": INDEXADOR["id"],
        "indexacao_name": INDEXADOR["name"],
        "credit_data": {"requested_amount": 200000, "loan_term_years": 30},
        "real_estate_data": {"valor_imovel": 250000, "morada_imovel": "Rua X, Lisboa"},
        "financial_data": {},
    }


def _documento(doc_id: str, filename: str, subcategoria: str, extracted: dict | None):
    """Registo de `document_metadata` como a categorização IA o deixa."""
    return {
        "id": doc_id,
        "process_id": PROCESS_ID,
        "client_name": "Ana Silva",
        "s3_path": f"clientes/ana/Financeiros/{filename}",
        "filename": filename,
        "ai_category": "Financeiros",
        "ai_subcategory": subcategoria,
        "extracted_data": extracted,
        "is_categorized": True,
    }


DOC_IRS = _documento(
    "doc-irs", "irs_2025.pdf", "Irs",
    {"rendimento_anual": 26400, "ano": 2025},
)
DOC_RECIBO = _documento(
    "doc-recibo", "recibo_vencimento_jan.pdf", "Recibo Vencimento",
    {"empresa": "Acme Lda", "salario_bruto": 2600, "salario_liquido": 2200},
)
DOC_IDENTIFICACAO = {
    "id": "doc-cc", "process_id": PROCESS_ID, "filename": "cc.pdf",
    "ai_category": "Identificação", "ai_subcategory": "Cc",
}


@pytest.fixture
def db():
    """BD em memória povoada com o cenário base.

    Os documentos são COPIADOS em profundidade: vários cenários mutam o
    `extracted_data` para simular OCR falhado, e sem a cópia essa mutação
    vazava para os testes seguintes (as constantes são partilhadas pelo
    módulo).
    """
    fake = FakeAsyncDatabase()
    fake.processes.docs.append(_processo_credito_habitacao())
    fake.document_metadata.docs.extend(
        deepcopy([DOC_IRS, DOC_RECIBO, DOC_IDENTIFICACAO])
    )
    fake.users.docs.extend([
        {**INDEXADOR, "is_active": True, "company": "empresa-1"},
        {**CONSULTOR, "role": "consultor", "is_active": True, "company": "empresa-1"},
        {**MEDIADOR, "role": "intermediario", "is_active": True, "company": "empresa-1"},
    ])
    fake.workflow_statuses.docs.extend([
        {"name": "pre_registo", "order": 1},
        {"name": "analise", "order": 2},
    ])
    return fake


@pytest.fixture
def eventos():
    """Recolhe os eventos emitidos (substitui o transporte Redis)."""
    capturados: list[dict] = []

    async def _publish(event_type, payload, *, user_id, company_id=None):
        capturados.append({
            "type": event_type, "payload": payload,
            "user_id": user_id, "company_id": company_id,
        })
        return True

    with patch("services.task_events.publish_event", _publish):
        yield capturados


def _tipos(eventos: list) -> list:
    return [e["type"] for e in eventos]


# ====================================================================
# ARNÊS: correr a indexação e o motor com as dependências certas
# ====================================================================


class _Arnes:
    """Monta os patches partilhados pelos cenários e expõe os spies."""

    def __init__(self, db, euribor=None):
        self.db = db
        # `euribor`: dict (valor devolvido) ou Exception (serviço em baixo).
        # None → taxas estáveis, para os cenários que não testam a Euribor.
        self.euribor = euribor if euribor is not None else dict(EURIBOR_ESTAVEL)
        self.broadcasts = []
        self.s3 = MagicMock()
        self.s3.is_configured = MagicMock(return_value=True)
        self.s3.upload_file = MagicMock(
            return_value="clientes/ana/Propostas/proposta.pdf"
        )
        self._stack = []

    async def broadcast(self, **kwargs):
        self.broadcasts.append(kwargs)

    def __enter__(self):
        from services import (
            financial_engine, process_assignment, process_indexing,
        )

        patches = [
            # Vários helpers fazem `from database import db` DENTRO da função
            # (ex.: `load_workflow_status_pipeline`), pelo que patchar apenas
            # os módulos não basta — é preciso a origem.
            patch("database.db", self.db),
            patch.object(process_indexing, "db", self.db),
            patch.object(process_assignment, "db", self.db),
            patch.object(financial_engine, "db", self.db),
            # Efeitos laterais fora do âmbito desta cadeia
            patch("services.history.log_history", AsyncMock()),
            patch.object(
                process_indexing, "notify_assigned_users_indexing_complete",
                AsyncMock(),
            ),
            patch.object(process_indexing, "trigger_indexer_waitlist", AsyncMock()),
            patch.object(
                process_assignment, "_notify_newly_assigned_users", AsyncMock()
            ),
            patch.object(
                process_assignment, "_create_post_indexing_tasks", AsyncMock()
            ),
            patch.object(
                process_assignment, "_find_least_busy_user",
                AsyncMock(side_effect=[CONSULTOR, MEDIADOR]),
            ),
            patch("services.workflow_engine.process_trigger", AsyncMock()),
            # Armazenamento
            patch("services.s3_storage.s3_service", self.s3),
            # Euribor controlada pelo cenário (nunca I/O de rede real).
            # Tem de ser aplicada AQUI e não num `with` do teste: este
            # arnês entra depois e sobrepor-se-ia ao patch do teste.
            patch(
                "services.euribor_service.get_euribor_rates",
                AsyncMock(side_effect=self.euribor)
                if isinstance(self.euribor, BaseException)
                else AsyncMock(return_value=self.euribor),
            ),
            # Branding do PDF (evita I/O de config/logo)
            patch(
                "services.financial_proposal_pdf.resolve_proposal_branding",
                AsyncMock(return_value={
                    "empresa": {
                        "nome": "Precision Crédito, Lda.", "nif": "500000000",
                        "morada": "Rua A, Porto", "email": "geral@x.pt",
                        "contacto": "220000000",
                    },
                    "logo_bytes": None, "accent": "#0F766E",
                }),
            ),
        ]
        for p in patches:
            p.start()
            self._stack.append(p)
        return self

    def __exit__(self, *exc):
        for p in reversed(self._stack):
            p.stop()
        self._stack.clear()
        return False


async def _marcar_indexado(db, *, euribor=None):
    """POST mark-indexed com o motor financeiro em modo síncrono.

    O motor corre normalmente em `asyncio.create_task`; aqui aguarda-se a
    corrida para que o teste observe o estado final sem sleeps arbitrários.
    """
    from services import financial_engine
    from services.process_indexing import run_mark_process_indexed

    arnes = _Arnes(db, euribor=euribor)
    corridas = []

    def _schedule_sincrono(coro):
        corridas.append(asyncio.create_task(coro))

    with arnes, patch.object(financial_engine, "_schedule", _schedule_sincrono), \
            patch("services.system_config.get_system_config",
                  AsyncMock(side_effect=_config_padrao)):
        resposta = await run_mark_process_indexed(
            PROCESS_ID, INDEXADOR,
            user_role="indexacao", all_roles=["indexacao"],
            broadcast_fn=arnes.broadcast,
        )
        if corridas:
            await asyncio.gather(*corridas)

    return resposta, arnes


async def _config_padrao(company_id="default"):
    from models.system_config import SystemConfig

    return SystemConfig()


# ====================================================================
# CENÁRIO 1 — CAMINHO FELIZ
# ====================================================================


class TestCaminhoFeliz:
    """IRS + recibo legíveis: atribuição, 3 cenários e PDF anexado."""

    async def test_fluxo_completo(self, db, eventos):
        resposta, arnes = await _marcar_indexado(db)

        # ── Indexação ────────────────────────────────────────────
        assert resposta["success"] is True
        processo = await db.processes.find_one({"id": PROCESS_ID})
        assert processo["is_indexed"] is True
        assert processo["status"] == "analise", "devia saltar para a fase seguinte"

        # ── Atribuição (regressão da MISSÃO 1) ───────────────────
        # O cartão lê `consultor_names` → `assigned_consultor_ids` →
        # `assigned_consultor_id`. Antes da correcção só se gravava
        # `consultant_id` e o cartão ficava em branco.
        assert processo["consultor_names"] == [CONSULTOR["name"]]
        assert processo["assigned_consultor_ids"] == [CONSULTOR["id"]]
        assert processo["assigned_consultor_id"] == CONSULTOR["id"]
        assert processo["mediador_names"] == [MEDIADOR["name"]]
        assert processo["assigned_mediador_ids"] == [MEDIADOR["id"]]
        assert processo["assigned_mediador_id"] == MEDIADOR["id"]
        # Campo legado preservado (usado por `process_list_filters`)
        assert processo["consultant_id"] == CONSULTOR["id"]

        # ── Motor financeiro disparado ───────────────────────────
        motor = resposta["financial_engine"]
        assert motor["triggered"] is True
        assert motor["documents"] == 2, "IRS + recibo (o CC não conta)"

        # ── Simulação concluída com 3 cenários ───────────────────
        simulacao = processo["financial_simulation"]
        assert simulacao["status"] == "completed"
        assert [c["key"] for c in simulacao["cenarios"]] == [
            "fixa", "mista", "variavel",
        ]
        for cenario in simulacao["cenarios"]:
            assert cenario["prestacao_mensal"] > 0
            assert cenario["taeg_pct"] > 0

        # ── PDF arquivado e anexado aos Documentos ───────────────
        arnes.s3.upload_file.assert_called_once()
        args = arnes.s3.upload_file.call_args.args
        assert args[3] == "Propostas", "categoria S3 da proposta"
        proposta = await db.document_metadata.find_one(
            {"ai_subcategory": "Proposta Financeira"}
        )
        assert proposta is not None
        assert proposta["process_id"] == PROCESS_ID
        assert proposta["document_type"] == "proposta_financeira"
        assert proposta["mime_type"] == "application/pdf"
        assert proposta["file_size"] > 1000, "PDF real, não um ficheiro vazio"

        # ── Rendimentos consolidados no processo ─────────────────
        assert processo["financial_data"]["rendimento_liquido_total"] == 2200.0

        # ── Timeline ─────────────────────────────────────────────
        acoes = [a["action"] for a in processo.get("activities", [])]
        assert "SIMULACAO_FINANCEIRA_GERADA" in acoes

    async def test_eventos_de_tempo_real(self, db, eventos):
        """`task_started` … `task_completed`, sempre para o dono da tarefa."""
        await _marcar_indexado(db)

        assert _tipos(eventos)[0] == "task_started"
        assert _tipos(eventos)[-1] == "task_completed"
        assert "task_progress" in _tipos(eventos)

        # TENANT-SAFETY + contexto: todos dirigidos ao indexador e ao processo
        for evento in eventos:
            assert evento["user_id"] == INDEXADOR["id"]
            assert evento["payload"]["source"] == "task_log"
        com_processo = [
            e for e in eventos if e["payload"].get("process_id")
        ]
        assert com_processo, "pelo menos um evento transporta o process_id"
        for evento in com_processo:
            assert evento["payload"]["process_id"] == PROCESS_ID

        # O evento final traz o resultado utilizável pela UI
        final = eventos[-1]["payload"]
        assert final["status"] == "completed"
        assert final["progress"] == 100
        assert final["result"]["document_id"]
        assert len(final["result"]["cenarios"]) == 3

    async def test_broadcast_leva_a_atribuicao(self, db, eventos):
        """MISSÃO 1 (2ª metade): o delta WS transporta a atribuição.

        O broadcast de mudança de estado corre ANTES da auto-atribuição;
        sem um segundo delta, outro operador com o processo aberto
        refrescava para dados ainda sem consultor.
        """
        _, arnes = await _marcar_indexado(db)

        com_atribuicao = [
            b for b in arnes.broadcasts if b.get("consultor_names")
        ]
        assert com_atribuicao, "nenhum broadcast transportou a atribuição"
        delta = com_atribuicao[-1]
        assert delta["consultor_names"] == [CONSULTOR["name"]]
        assert delta["assigned_consultor_ids"] == [CONSULTOR["id"]]
        assert delta["mediador_names"] == [MEDIADOR["name"]]
        assert delta["process_id"] == PROCESS_ID


# ====================================================================
# CENÁRIO 2 — FALHA DE OCR / DADOS
# ====================================================================


class TestFalhaDeExtracao:
    """IRS ilegível: o sistema não encrava e pede revisão manual."""

    async def test_irs_ilegivel_nao_reverte_indexacao(self, db, eventos):
        from services import financial_engine

        # Documentos sem `extracted_data` e OCR que não devolve nada
        for doc in db.document_metadata.docs:
            doc["extracted_data"] = None

        with patch.object(
            financial_engine, "_extract_document_data", AsyncMock(return_value=None)
        ):
            resposta, arnes = await _marcar_indexado(db)

        processo = await db.processes.find_one({"id": PROCESS_ID})

        # A INDEXAÇÃO MANTÉM-SE — é o ponto central deste cenário
        assert resposta["success"] is True
        assert processo["is_indexed"] is True
        assert processo["status"] == "analise"
        # A atribuição também não é desfeita
        assert processo["consultor_names"] == [CONSULTOR["name"]]

        # Revisão manual registada
        simulacao = processo["financial_simulation"]
        assert simulacao["status"] == "needs_manual_review"
        assert simulacao["reason"] == "extracao_falhou"
        assert "revisão manual" in simulacao["message"]
        assert "irs_2025.pdf" in simulacao["message"], "nomeia o que falhou"

        # Aviso visível na timeline do consultor
        acoes = [a["action"] for a in processo.get("activities", [])]
        assert "SIMULACAO_FINANCEIRA_REVISAO_MANUAL" in acoes

        # Nenhuma proposta foi gerada nem arquivada
        arnes.s3.upload_file.assert_not_called()
        assert await db.document_metadata.find_one(
            {"ai_subcategory": "Proposta Financeira"}
        ) is None

    async def test_emite_task_failed(self, db, eventos):
        from services import financial_engine

        for doc in db.document_metadata.docs:
            doc["extracted_data"] = None

        with patch.object(
            financial_engine, "_extract_document_data", AsyncMock(return_value=None)
        ):
            await _marcar_indexado(db)

        assert _tipos(eventos)[-1] == "task_failed"
        final = eventos[-1]
        assert final["user_id"] == INDEXADOR["id"]
        assert final["payload"]["status"] == "failed"
        assert final["payload"]["error"]

    async def test_sem_rendimento_legivel_pede_revisao(self, db, eventos):
        """Documentos legíveis mas sem valores → nada de números inventados."""
        for doc in db.document_metadata.docs:
            if doc.get("ai_category") == "Financeiros":
                doc["extracted_data"] = {"observacoes": "página em branco"}

        await _marcar_indexado(db)

        processo = await db.processes.find_one({"id": PROCESS_ID})
        assert processo["is_indexed"] is True
        simulacao = processo["financial_simulation"]
        assert simulacao["status"] == "needs_manual_review"
        assert simulacao["reason"] == "sem_rendimento"
        assert "rendimento" in simulacao["missing"]


# ====================================================================
# CENÁRIO 3 — FALHA DE SERVIÇOS EXTERNOS
# ====================================================================


class TestFalhaDeServicos:
    async def test_euribor_em_baixo_usa_spread_contratado(self, db, eventos):
        """A simulação continua; os cenários indexados ficam só com o spread."""
        resposta, arnes = await _marcar_indexado(
            db, euribor=ConnectionError("API Euribor inacessível")
        )

        processo = await db.processes.find_one({"id": PROCESS_ID})
        simulacao = processo["financial_simulation"]

        # NÃO abortou: a proposta saiu na mesma
        assert simulacao["status"] == "completed"
        assert len(simulacao["cenarios"]) == 3
        arnes.s3.upload_file.assert_called_once()

        # A taxa variável ficou igual ao spread configurado (Euribor = 0)
        from models.system_config import SystemConfig

        spread = SystemConfig().financial_simulator.spread_variavel
        variavel = next(c for c in simulacao["cenarios"] if c["key"] == "variavel")
        assert variavel["taxa_pct"] == pytest.approx(spread)

        # E o PDF avisa que a Euribor não estava disponível
        assert any("Euribor indisponível" in a for a in simulacao["avisos"])

    async def test_euribor_estimada_gera_aviso(self, db, eventos):
        """Cache/fallback do serviço de Euribor → aviso, não silêncio."""
        await _marcar_indexado(db, euribor={
            "euribor_12m": 3.50, "is_fallback": True, "source": "fallback",
            "fetched_at": "2026-09-21T08:00:00+00:00",
        })

        simulacao = (await db.processes.find_one({"id": PROCESS_ID}))[
            "financial_simulation"
        ]
        assert simulacao["status"] == "completed"
        assert any("estimados" in a for a in simulacao["avisos"])

    async def test_s3_em_baixo_pede_revisao_sem_reverter(self, db, eventos):
        resposta, arnes = None, None
        from services import financial_engine

        arnes_holder = {}

        async def _correr():
            nonlocal resposta
            resposta, a = await _marcar_indexado(db)
            arnes_holder["a"] = a

        with patch.object(
            financial_engine, "archive_proposal",
            AsyncMock(side_effect=RuntimeError("S3 não configurado")),
        ):
            await _correr()

        processo = await db.processes.find_one({"id": PROCESS_ID})

        # Indexação e atribuição intactas
        assert resposta["success"] is True
        assert processo["is_indexed"] is True
        assert processo["consultor_names"] == [CONSULTOR["name"]]

        simulacao = processo["financial_simulation"]
        assert simulacao["status"] == "needs_manual_review"
        assert simulacao["reason"] == "pdf_falhou"

        acoes = [a["action"] for a in processo.get("activities", [])]
        assert "SIMULACAO_FINANCEIRA_REVISAO_MANUAL" in acoes
        assert _tipos(eventos)[-1] == "task_failed"

    async def test_motor_desligado_na_configuracao(self, db, eventos):
        """Feature flag off: indexação normal, sem motor e sem ruído."""
        from models.system_config import SystemConfig

        async def _config_off(company_id="default"):
            config = SystemConfig()
            config.financial_simulator.enabled = False
            return config

        from services import financial_engine
        from services.process_indexing import run_mark_process_indexed

        arnes = _Arnes(db)
        with arnes, patch.object(financial_engine, "_schedule", MagicMock()), \
                patch("services.system_config.get_system_config",
                      AsyncMock(side_effect=_config_off)):
            resposta = await run_mark_process_indexed(
                PROCESS_ID, INDEXADOR,
                user_role="indexacao", all_roles=["indexacao"],
                broadcast_fn=arnes.broadcast,
            )

        assert resposta["success"] is True
        assert resposta["financial_engine"]["triggered"] is False
        assert resposta["financial_engine"]["reason"] == "motor_desativado"
        assert eventos == []
        processo = await db.processes.find_one({"id": PROCESS_ID})
        assert processo["is_indexed"] is True
        assert "financial_simulation" not in processo

    async def test_processo_sem_documentos_financeiros(self, db, eventos):
        """Só CC indexado: o motor não dispara (não é falha, é ausência)."""
        db.document_metadata.docs = [DOC_IDENTIFICACAO]

        resposta, arnes = await _marcar_indexado(db)

        assert resposta["financial_engine"]["triggered"] is False
        assert resposta["financial_engine"]["reason"] == "sem_documentos_financeiros"
        arnes.s3.upload_file.assert_not_called()

    async def test_processo_que_nao_e_de_credito(self, db, eventos):
        (await db.processes.find_one({"id": PROCESS_ID}))
        db.processes.docs[0]["process_type"] = "arrendamento"

        resposta, _ = await _marcar_indexado(db)

        assert resposta["financial_engine"]["triggered"] is False
        assert resposta["financial_engine"]["reason"] == "processo_nao_credito"


# ====================================================================
# CENÁRIO 4 — PROVA DE TEMPO REAL (Redis a sério)
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
    """Os eventos viajam MESMO pelo Redis até ao WebSocket do destinatário.

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

    async def test_evento_viaja_pelo_redis_ate_ao_dono(self, redis_vivo, db):
        from services import redis_pubsub, websocket_manager

        entregues = {INDEXADOR["id"]: [], OUTRO_UTILIZADOR["id"]: []}
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
                # Fluxo real: o motor emite, ninguém intercepta a publicação
                await _marcar_indexado(db)
                await asyncio.sleep(1.0)  # propagação pelo canal
            finally:
                await listener.stop()

        recebidos = entregues[INDEXADOR["id"]]
        tipos = [m["type"] for m in recebidos]
        assert "task_started" in tipos
        assert "task_completed" in tipos

        # Contexto correcto no que chegou ao browser
        completos = [m for m in recebidos if m["type"] == "task_completed"]
        assert completos[-1]["data"]["result"]["document_id"]
        com_processo = [m for m in recebidos if m["data"].get("process_id")]
        assert com_processo
        for mensagem in com_processo:
            assert mensagem["data"]["process_id"] == PROCESS_ID

        # TENANT-SAFETY: o outro utilizador não viu nada
        assert entregues[OUTRO_UTILIZADOR["id"]] == []

    async def test_redis_em_baixo_nao_bloqueia_o_motor(self, db, eventos):
        """Sem Redis alcançável, a cadeia completa termina na mesma."""
        from services import redis_pubsub

        with patch.object(
            redis_pubsub, "_get_publisher", AsyncMock(return_value=None)
        ):
            resposta, arnes = await _marcar_indexado(db)

        processo = await db.processes.find_one({"id": PROCESS_ID})
        assert resposta["success"] is True
        assert processo["financial_simulation"]["status"] == "completed"
        arnes.s3.upload_file.assert_called_once()
