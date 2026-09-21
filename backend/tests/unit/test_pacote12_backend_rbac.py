"""PACOTE 12 (Eixo 3 — Backend/RBAC): testes unitários.

Cobre os fixes do Eixo 3 sem I/O (fake_async_db do conftest + patch do
`db` no módulo do serviço — padrão test_document_portal_fulfill.py):

1. VISIBILIDADE DE DOCUMENTOS (document_visibility.py) — allow-path por
   relação directa com o CLIENTE do processo (consultor atribuído ao
   cliente ``assigned_to`` / criador do registo ``created_by``) nas
   guardas async; 403 para consultor sem qualquer relação; bypass
   absoluto dos perfis de administração; função pura mantém-se sem I/O.
2. LEAST-BUSY ESTRITO (process_assignment.py) — pool de candidatos
   exclui perfis de gestão (admin/ceo/diretor/…); ramo intermediário
   REMOVIDO do assign_to_least_busy_consultant; slot mediador da dupla
   auto-atribuição continua a funcionar via
   _find_least_busy_user("intermediario"); contagem multi-assignee.
3. DEDUP DO EMAIL DE BOAS-VINDAS (client_portal_email.py +
   process_create.py) — envio idempotente por estado de entrega
   (portal_email_delivery.status == "sent" → NÃO volta a enviar),
   fail-open do lookup, retry ARQ (sem client_id) intacto.
4. CASCATA DO CLEANUP (scripts/cleanup_prod_test_data.py) — as 12
   colecções dependentes (11 por process_id + visits por process_id OU
   client_id) são hard-delete em AMBOS os modos (como task_logs) e
   reportadas no dry-run.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import database as database_module
import scripts.cleanup_prod_test_data as cleanup_script
import services.client_portal_email as portal_email_mod
import services.document_visibility as dv
import services.process_assignment as pa
import services.process_create as pc
from scripts.cleanup_prod_test_data import (
    PROCESS_CHILD_COLLECTIONS,
    cleanup_prod_test_data,
)
from tests.unit.conftest import FakeAsyncDatabase

pytestmark = pytest.mark.asyncio


# ====================================================================
# 1) VISIBILIDADE DE DOCUMENTOS — allow-path por relação com o CLIENTE
# ====================================================================
class TestVisibilidadeDocumentos:
    """PACOTE 12 — consultor responsável pelo CLIENTE lê os documentos
    do processo em tratamento (pré-indexação) mesmo sem estar atribuído
    ao processo."""

    def _processo(self, **overrides):
        base = {
            "id": "p-vis",
            "status": "clientes_espera",
            # pré-indexação: visibilidade RESTRITA (is_indexed != True)
            "is_indexed": False,
            "client_id": "cl-vis",
            # SEM campos de atribuição ao processo (consultor não atribuído)
        }
        base.update(overrides)
        return base

    # ── helper pura ─────────────────────────────────────────────────
    def test_relacao_pura_atribuido_ao_cliente(self):
        user = {"id": "u-cons", "email": "cons@x.pt"}
        assert dv._user_is_related_to_client_doc(
            user, {"assigned_to": "u-cons"}
        ) is True

    def test_relacao_pura_criador_do_cliente(self):
        user = {"id": "u-cons", "email": "criador@x.pt"}
        assert dv._user_is_related_to_client_doc(
            user, {"created_by": "criador@x.pt"}
        ) is True

    def test_relacao_pura_sem_relacao(self):
        user = {"id": "u-cons", "email": "cons@x.pt"}
        client = {"assigned_to": "u-outro", "created_by": "outro@x.pt"}
        assert dv._user_is_related_to_client_doc(user, client) is False

    def test_relacao_pura_guards_none(self):
        # cliente inexistente / None → False (nunca é motivo de bloqueio)
        assert dv._user_is_related_to_client_doc({"id": "u"}, None) is False
        # utilizador sem identidade → False (sem falsos positivos)
        assert dv._user_is_related_to_client_doc(
            {}, {"assigned_to": "u"}
        ) is False
        assert dv._user_is_related_to_client_doc(
            {}, {"created_by": "x@x.pt"}
        ) is False

    # ── função pura com doc do cliente pré-carregado ────────────────
    def test_funcao_pura_com_cliente_atribuido(self):
        user = {"id": "u-cons", "role": "consultor"}
        assert dv.user_can_view_process_documents(
            user, self._processo(), client={"assigned_to": "u-cons"}
        ) is True

    def test_funcao_pura_com_cliente_criador(self):
        user = {"id": "u-cons", "role": "consultor", "email": "c@x.pt"}
        assert dv.user_can_view_process_documents(
            user, self._processo(), client={"created_by": "c@x.pt"}
        ) is True

    def test_funcao_pura_sem_cliente_continua_negada(self):
        # sem doc do cliente, o comportamento histórico mantém-se
        user = {"id": "u-cons", "role": "consultor"}
        assert dv.user_can_view_process_documents(
            user, self._processo()
        ) is False
        assert dv.user_can_view_process_documents(
            user, self._processo(), client={"assigned_to": "u-outro"}
        ) is False

    # ── guarda async — allow ────────────────────────────────────────
    async def test_guarda_permite_consultor_atribuido_ao_cliente(self):
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append({"id": "cl-vis", "assigned_to": "u-cons-9"})

        with patch.object(dv, "db", fake_db):
            # NÃO levanta 403
            await dv.assert_can_view_process_documents(
                {"id": "u-cons-9", "role": "consultor"}, self._processo()
            )

    async def test_guarda_permite_criador_do_cliente(self):
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append(
            {"id": "cl-vis", "created_by": "criador@x.pt"}
        )

        with patch.object(dv, "db", fake_db):
            await dv.assert_can_view_process_documents(
                {"id": "u-cons-8", "role": "consultor", "email": "criador@x.pt"},
                self._processo(),
            )

    # ── guarda async — deny (mensagem 403 inalterada) ───────────────
    async def test_guarda_nega_consultor_sem_relacao(self):
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append(
            {"id": "cl-vis", "assigned_to": "u-outro", "created_by": "outro@x.pt"}
        )

        with patch.object(dv, "db", fake_db), pytest.raises(HTTPException) as exc:
            await dv.assert_can_view_process_documents(
                {"id": "u-cons-x", "role": "consultor", "email": "x@x.pt"},
                self._processo(),
            )
        assert exc.value.status_code == 403
        # mensagem histórica MANTIDA (sem menção ao allow-path novo)
        assert "equipa de indexação" in exc.value.detail
        assert "atribuídos ao processo" in exc.value.detail

    # ── bypass admin absoluto (sem doc de cliente) ──────────────────
    async def test_bypass_admin_sem_doc_cliente(self):
        fake_db = FakeAsyncDatabase()  # clients VAZIO

        with patch.object(dv, "db", fake_db):
            await dv.assert_can_view_process_documents(
                {"id": "u-admin-1", "role": "admin"}, self._processo()
            )

    # ── entrada por ID do processo ─────────────────────────────────
    async def test_by_id_permite_consultor_do_cliente(self):
        fake_db = FakeAsyncDatabase()
        fake_db.processes.docs.append(self._processo(id="p-vis"))
        fake_db.clients.docs.append({"id": "cl-vis", "assigned_to": "u-cons-9"})

        with patch.object(dv, "db", fake_db):
            process = await dv.assert_can_view_process_documents_by_id(
                {"id": "u-cons-9", "role": "consultor"}, "p-vis"
            )
        assert process["id"] == "p-vis"

    async def test_by_id_nega_consultor_sem_relacao(self):
        fake_db = FakeAsyncDatabase()
        fake_db.processes.docs.append(self._processo(id="p-vis"))
        fake_db.clients.docs.append({"id": "cl-vis", "assigned_to": "u-outro"})

        with patch.object(dv, "db", fake_db), pytest.raises(HTTPException) as exc:
            await dv.assert_can_view_process_documents_by_id(
                {"id": "u-cons-x", "role": "consultor"}, "p-vis"
            )
        assert exc.value.status_code == 403

    async def test_by_id_404_processo_inexistente(self):
        fake_db = FakeAsyncDatabase()

        with patch.object(dv, "db", fake_db), pytest.raises(HTTPException) as exc:
            await dv.assert_can_view_process_documents_by_id(
                {"id": "u-cons-9", "role": "consultor"}, "inexistente"
            )
        assert exc.value.status_code == 404


# ====================================================================
# 2) LEAST-BUSY ESTRITO — pool de staff de operações
# ====================================================================
class TestLeastBusyEstrito:
    """PACOTE 12 — a auto-atribuição "menos ocupado" é ESTRITAMENTE para
    staff de operações: perfis de gestão (admin/ceo/diretor/…) NUNCA
    entram no pool, e o ramo intermediário foi removido do
    assign_to_least_busy_consultant."""

    def _seed_users(self, fake_db):
        """Admin (0 carga, additional_roles consultor) PRIMEIRO na lista:
        se a exclusão falhasse, seria sempre o escolhido (menor carga)."""
        fake_db.users.docs.extend([
            {
                "id": "u-gestor", "name": "Gestor Admin", "email": "gestor@x.pt",
                "role": "admin", "is_active": True,
                "additional_roles": ["consultor"],
            },
            {
                "id": "u-interm", "name": "Intermediário Um", "email": "interm@x.pt",
                "role": "intermediario", "is_active": True,
            },
            {
                "id": "u-consultora", "name": "Ana Consultora", "email": "ana@x.pt",
                "role": "consultor", "is_active": True,
            },
        ])

    # ── composição da query (semântica $nin explícita) ──────────────
    def test_candidate_query_exclui_perfis_gestao(self):
        from services.role_query import build_deep_role_query, deep_role_nin_filter

        query = pa._least_busy_candidate_query("consultor")
        clauses = query["$and"]
        assert clauses[0] == build_deep_role_query({"is_active": True}, role="consultor")
        assert clauses[1] == deep_role_nin_filter(pa.LEAST_BUSY_EXCLUDED_ROLES)
        # espelha os _ADMIN_BYPASS_ROLES do document_visibility.py
        assert set(pa.LEAST_BUSY_EXCLUDED_ROLES) == {
            "admin", "ceo", "diretor", "administrativo",
            "system_admin", "super_admin",
        }

    def test_lista_coleccoes_filhas_processo(self):
        # 11 filhos por process_id (+ visits tratada à parte = 12)
        assert PROCESS_CHILD_COLLECTIONS == [
            "rgpd_requests", "document_metadata", "portal_tokens",
            "portal_messages", "deadlines", "process_finances",
            "notifications", "annotations", "temp_links",
            "data_suggestions", "emails",
        ]
        # trilho de auditoria e templates NÃO são tocados por design
        assert "process_activities" not in PROCESS_CHILD_COLLECTIONS
        assert "minutas" not in PROCESS_CHILD_COLLECTIONS

    # ── contagem de carga (multi-assignee) ──────────────────────────
    async def test_count_conta_atribuicoes_activas(self, fake_async_db):
        fake_async_db.processes.docs.extend([
            {"id": "c1", "consultant_id": "u-9", "status": "fase_bancaria"},
            {"id": "c2", "assigned_consultor_id": "u-9", "status": "fase_documental"},
            {"id": "c3", "consultant_id": "u-9", "status": "concluido"},  # inactivo
            {"id": "c4", "consultant_id": "u-outro", "status": "fase_bancaria"},
        ])
        with patch.object(pa, "db", fake_async_db):
            assert await pa._count_active_processes_for_consultant("u-9") == 2

    async def test_count_inclui_campo_multi_assignee_na_query(self):
        """PACOTE 12 — a lista assigned_consultor_ids também entra no $or."""
        mock_db = MagicMock()
        mock_db.processes.count_documents = AsyncMock(return_value=0)

        with patch.object(pa, "db", mock_db):
            await pa._count_active_processes_for_consultant("u-9")

        query = mock_db.processes.count_documents.await_args.args[0]
        assert {"assigned_consultor_id": "u-9"} in query["$or"]
        assert {"consultant_id": "u-9"} in query["$or"]
        assert {"assigned_consultor_ids": "u-9"} in query["$or"]

    # ── assign_to_least_busy_consultant (pool só consultores) ───────
    async def test_assign_escolhe_consultora_nunca_gestor_ou_intermediario(
        self, fake_async_db
    ):
        self._seed_users(fake_async_db)
        fake_async_db.processes.docs.extend([
            # carga da consultora (2 processos) — mesmo assim é a escolhida,
            # porque o gestor (0 carga) está EXCLUÍDO do pool
            {"id": "l1", "status": "fase_bancaria", "consultant_id": "u-consultora"},
            {"id": "l2", "status": "fase_documental", "consultant_id": "u-consultora"},
            # alvo da auto-atribuição (sem consultor)
            {
                "id": "p-alvo", "status": "fase_bancaria",
                "client_name": "Cliente Novo",
            },
        ])

        with patch.object(pa, "db", fake_async_db), patch(
            "services.history.log_history", new=AsyncMock()
        ), patch(
            "services.realtime_notifications.send_realtime_notification",
            new=AsyncMock(),
        ):
            ok, data, msg = await pa.assign_to_least_busy_consultant("p-alvo")

        assert ok is True
        assert data["assigned_consultor_id"] == "u-consultora"
        assert data["consultor_name"] == "Ana Consultora"
        # o doc do processo ficou atribuído À CONSULTORA
        stored = await fake_async_db.processes.find_one({"id": "p-alvo"})
        assert stored["consultant_id"] == "u-consultora"
        assert stored["consultor_name"] == "Ana Consultora"
        # nunca o gestor nem o intermediário
        assert stored["consultant_id"] != "u-gestor"
        assert stored["consultant_id"] != "u-interm"
        assert "Ana Consultora" in msg

    async def test_assign_sem_consultores_avanca_sem_atribuicao(self, fake_async_db):
        # só gestores/intermediários no sistema → pool de consultores VAZIO
        self._seed_users(fake_async_db)
        fake_async_db.processes.docs.append({
            "id": "p-sem", "status": "fase_bancaria", "client_name": "X",
        })
        # remove a consultora do sistema
        fake_async_db.users.docs = [
            u for u in fake_async_db.users.docs if u["id"] != "u-consultora"
        ]

        with patch.object(pa, "db", fake_async_db), patch(
            "services.history.log_history", new=AsyncMock()
        ):
            ok, data, msg = await pa.assign_to_least_busy_consultant("p-sem")

        assert ok is True
        assert data["assigned"] is False
        assert data["reason"] == "no_consultants"
        stored = await fake_async_db.processes.find_one({"id": "p-sem"})
        assert "consultant_id" not in stored  # nem gestor nem intermediário

    # ── _find_least_busy_user (dupla auto-atribuição) ───────────────
    async def test_find_least_busy_consultor_exclui_gestao(self, fake_async_db):
        self._seed_users(fake_async_db)

        with patch.object(pa, "db", fake_async_db):
            chosen = await pa._find_least_busy_user("consultor")

        assert chosen is not None
        assert chosen["id"] == "u-consultora"

    async def test_find_least_busy_intermediario_slot_funciona(self, fake_async_db):
        # gestor com additional_roles=["intermediario"] e 0 carga está
        # PRIMEIRO na lista — a exclusão tem de vencer a ordenação
        fake_async_db.users.docs.extend([
            {
                "id": "u-gestor", "name": "CEO", "email": "ceo@x.pt",
                "role": "ceo", "is_active": True,
                "additional_roles": ["intermediario"],
            },
            {
                "id": "u-interm", "name": "Intermediário Um", "email": "interm@x.pt",
                "role": "intermediario", "is_active": True,
            },
        ])

        with patch.object(pa, "db", fake_async_db):
            chosen = await pa._find_least_busy_user("intermediario")

        assert chosen is not None
        assert chosen["id"] == "u-interm"

    async def test_dual_auto_assign_preenche_ambos_slots_com_staff(
        self, fake_async_db
    ):
        """O slot MEDIADOR da dupla auto-atribuição continua a funcionar
        via _find_least_busy_user('intermediario') — com exclusão de
        perfis de gestão em AMBOS os papéis."""
        self._seed_users(fake_async_db)
        fake_async_db.processes.docs.append({
            "id": "p-dual", "status": "fase_bancaria",
            "client_name": "Cliente Duplo",
        })

        with patch.object(pa, "db", fake_async_db), patch(
            "services.history.log_history", new=AsyncMock()
        ), patch.object(
            pa, "_notify_newly_assigned_users", new=AsyncMock()
        ), patch.object(
            pa, "_create_post_indexing_tasks", new=AsyncMock()
        ):
            result = await pa.dual_auto_assign_on_pre_registo_transition("p-dual")

        assert result["consultant_id"] == "u-consultora"
        assert result["mediador_id"] == "u-interm"
        stored = await fake_async_db.processes.find_one({"id": "p-dual"})
        assert stored["consultant_id"] == "u-consultora"
        assert stored["mediador_id"] == "u-interm"
        # nenhum slot foi para a gestão
        assert stored["consultant_id"] != "u-gestor"
        assert stored["mediador_id"] != "u-gestor"


# ====================================================================
# 3) DEDUP DO EMAIL DE BOAS-VINDAS (idempotência por estado de entrega)
# ====================================================================
class TestDedupEmailBoasVindas:
    """PACOTE 12 — fluxo Pré-Registo (criar cliente → criar processo) já
    não dispara DOIS emails idênticos: estado 'sent' no cliente bloqueia
    o reenvio; 'failed'/ausente → envia; retry ARQ intacto."""

    def _client(self, client_id="cli-dup", status=None):
        doc = {"id": client_id}
        if status is not None:
            doc["portal_email_delivery"] = {"status": status}
        return doc

    # ── deliver_registration_email ──────────────────────────────────
    async def test_deliver_ignora_envio_quando_ja_sent(self):
        """status='sent' + client_id → True SEM invocar o transporte."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append(self._client(status="sent"))

        with patch.object(portal_email_mod, "db", fake_db), patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=True),
        ) as mock_send, patch(
            "services.email_delivery_status.begin_portal_email_task",
            new=AsyncMock(return_value="task-dup"),
        ) as mock_begin:
            sent = await portal_email_mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", portal_access_code="X",
                client_id="cli-dup",
            )

        assert sent is True
        mock_send.assert_not_awaited()
        mock_begin.assert_not_awaited()  # nem a task foi iniciada

    async def test_deliver_envia_quando_status_failed(self):
        """status='failed' → o envio é tentado normalmente."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append(self._client(status="failed"))

        with patch.object(portal_email_mod, "db", fake_db), patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=True),
        ) as mock_send, patch(
            "services.email_delivery_status.begin_portal_email_task",
            new=AsyncMock(return_value="task-f"),
        ), patch(
            "services.email_delivery_status.complete_portal_email_task",
            new=AsyncMock(),
        ):
            sent = await portal_email_mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", portal_access_code="X",
                client_id="cli-dup",
            )

        assert sent is True
        mock_send.assert_awaited_once()

    async def test_deliver_envia_quando_estado_ausente(self):
        """Sem portal_email_delivery (primeira entrega) → envia."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append(self._client())

        with patch.object(portal_email_mod, "db", fake_db), patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=True),
        ) as mock_send, patch(
            "services.email_delivery_status.begin_portal_email_task",
            new=AsyncMock(return_value="task-m"),
        ), patch(
            "services.email_delivery_status.complete_portal_email_task",
            new=AsyncMock(),
        ):
            sent = await portal_email_mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", client_id="cli-dup",
            )

        assert sent is True
        mock_send.assert_awaited_once()

    async def test_deliver_envia_quando_cliente_inexistente(self):
        """client_id dado mas doc não encontrado → envia (fail-open)."""
        fake_db = FakeAsyncDatabase()  # clients vazio

        with patch.object(portal_email_mod, "db", fake_db), patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=True),
        ) as mock_send, patch(
            "services.email_delivery_status.begin_portal_email_task",
            new=AsyncMock(return_value="task-x"),
        ), patch(
            "services.email_delivery_status.complete_portal_email_task",
            new=AsyncMock(),
        ):
            sent = await portal_email_mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", client_id="cli-nao-existe",
            )

        assert sent is True
        mock_send.assert_awaited_once()

    async def test_deliver_fail_open_quando_lookup_levanta_excepcao(self):
        """Falha de leitura do estado NUNCA bloqueia o envio legítimo."""
        fake_db = FakeAsyncDatabase()

        async def _boom(query, projection=None, sort=None):
            raise RuntimeError("leitura indisponível")

        fake_db.clients.find_one = _boom

        with patch.object(portal_email_mod, "db", fake_db), patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=True),
        ) as mock_send, patch(
            "services.email_delivery_status.begin_portal_email_task",
            new=AsyncMock(return_value="task-e"),
        ), patch(
            "services.email_delivery_status.complete_portal_email_task",
            new=AsyncMock(),
        ):
            sent = await portal_email_mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", client_id="cli-erro",
            )

        assert sent is True
        mock_send.assert_awaited_once()

    async def test_retry_arq_sem_client_id_nao_e_afectado(self):
        """O retry do worker ARQ chama SEM client_id → envio normal, mesmo
        havendo um cliente marcado 'sent' na base de dados."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append(self._client(status="sent"))

        with patch.object(portal_email_mod, "db", fake_db), patch(
            "services.email.send_registration_confirmation",
            new=AsyncMock(return_value=True),
        ) as mock_send, patch(
            "services.email_delivery_status.begin_portal_email_task",
            new=AsyncMock(return_value="task-r"),
        ), patch(
            "services.email_delivery_status.complete_portal_email_task",
            new=AsyncMock(),
        ):
            sent = await portal_email_mod.deliver_registration_email(
                "cliente@x.pt", "Cliente", portal_access_code="X",
            )  # client_id=None

        assert sent is True
        mock_send.assert_awaited_once()

    # ── send_portal_welcome_email_from_process ─────────────────────
    async def test_from_process_salta_envio_quando_sent(self):
        """Estado 'sent' no cliente carregado → NÃO delega o envio."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append({
            "id": "cli-s", "portal_access_code": "CODE-S",
            "portal_email_delivery": {"status": "sent"},
        })

        with patch.object(pc, "db", fake_db), patch(
            "services.client_portal_email.deliver_registration_email",
            new=AsyncMock(return_value=True),
        ) as mock_deliver:
            await pc.send_portal_welcome_email_from_process(
                client_id="cli-s", client_email="s@x.pt", client_name="Cliente",
            )

        mock_deliver.assert_not_awaited()

    async def test_from_process_envia_quando_estado_ausente(self):
        """Sem estado de entrega → envia e usa o código do cliente."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append({
            "id": "cli-m", "portal_access_code": "CODE-M",
        })

        with patch.object(pc, "db", fake_db), patch(
            "services.client_portal_email.deliver_registration_email",
            new=AsyncMock(return_value=True),
        ) as mock_deliver:
            await pc.send_portal_welcome_email_from_process(
                client_id="cli-m", client_email="m@x.pt", client_name="Cliente",
            )

        mock_deliver.assert_awaited_once()
        assert mock_deliver.await_args.kwargs["portal_access_code"] == "CODE-M"
        assert mock_deliver.await_args.kwargs["client_id"] == "cli-m"

    async def test_from_process_envia_quando_status_failed(self):
        """Estado 'failed' NÃO salta o envio (nova tentativa legítima)."""
        fake_db = FakeAsyncDatabase()
        fake_db.clients.docs.append({
            "id": "cli-f", "portal_access_code": "CODE-F",
            "portal_email_delivery": {"status": "failed"},
        })

        with patch.object(pc, "db", fake_db), patch(
            "services.client_portal_email.deliver_registration_email",
            new=AsyncMock(return_value=True),
        ) as mock_deliver:
            await pc.send_portal_welcome_email_from_process(
                client_id="cli-f", client_email="f@x.pt", client_name="Cliente",
            )

        mock_deliver.assert_awaited_once()


# ====================================================================
# 4) CASCATA DO CLEANUP — 12 colecções dependentes, zero órfãos
# ====================================================================
class TestCleanupCascataDependentes:
    """PACOTE 12 — os filhos dependentes por process_id/client_id são
    hard-delete em AMBOS os modos (como task_logs) e entram no relatório."""

    def _seed(self, fake_db):
        """Um cliente/processo de teste + um REAL (intacto) + filhos nas
        12 colecções novas + drivers (tasks/documents/task_logs/history/
        activities)."""
        fake_db.clients.docs.extend([
            {"id": "cl-test", "nome": "Cliente Teste",
             "contacto": {"email": "teste@x.pt"}},
            {"id": "cl-real", "nome": "Ana Silva",
             "contacto": {"email": "ana@x.pt"}},
        ])
        fake_db.processes.docs.extend([
            {"id": "p-test", "client_id": "cl-test", "client_name": "Cliente Teste",
             "client_email": "teste@x.pt", "process_number": "T-1",
             "status": "fase_bancaria"},
            {"id": "p-real", "client_id": "cl-real", "client_name": "Ana Silva",
             "client_email": "ana@x.pt", "process_number": "R-1",
             "status": "fase_bancaria"},
        ])
        # drivers clássicos
        fake_db.tasks.docs.extend([
            {"id": "t-test", "title": "Tarefa de teste", "process_id": "p-test"},
            {"id": "t-real", "title": "Tarefa real", "process_id": "p-real"},
        ])
        fake_db.documents.docs.extend([
            {"id": "d-test", "client_id": "cl-test", "process_id": "p-test"},
            {"id": "d-real", "client_id": "cl-real", "process_id": "p-real"},
        ])
        fake_db.task_logs.docs.extend([
            {"id": "tl-test", "process_id": "p-test"},
            {"id": "tl-real", "process_id": "p-real"},
        ])
        fake_db.history.docs.extend([
            {"id": "h-test", "process_id": "p-test"},
            {"id": "h-real", "process_id": "p-real"},
        ])
        fake_db.activities.docs.extend([
            {"id": "a-test", "comment": "comentário de teste", "process_id": "p-test"},
            {"id": "a-real", "comment": "comentário real", "process_id": "p-real"},
        ])
        # 11 filhos por process_id (um de teste + um real por colecção)
        for coll in PROCESS_CHILD_COLLECTIONS:
            child = fake_db.collection(coll)
            child.docs.extend([
                {"id": f"{coll}-test", "process_id": "p-test"},
                {"id": f"{coll}-real", "process_id": "p-real"},
            ])
        # visits: por process_id E por client_id
        fake_db.visits.docs.extend([
            {"id": "v-proc", "process_id": "p-test"},
            {"id": "v-cli", "client_id": "cl-test"},
            {"id": "v-real", "process_id": "p-real"},
        ])

    async def test_dry_run_reporta_as_colecoes_dependentes(
        self, fake_async_db, capsys
    ):
        self._seed(fake_async_db)

        with patch.object(database_module, "db", fake_async_db):
            total = await cleanup_prod_test_data(dry_run=True)

        out = capsys.readouterr().out
        assert "[CASCADE-DEPENDENTES]" in out
        # cada colecção nova aparece no relatório (contagens não nulas)
        assert "rgpd_requests: 1" in out
        assert "document_metadata: 1" in out
        assert "emails: 1" in out
        assert "visits: 2" in out  # por process_id E por client_id
        # o total inclui os 13 registos dependentes (11 + 2 visitas)
        assert "13 registos dependentes em cascata (PACOTE 12)" in out
        # total determinístico: 7 registos de teste próprios/cascata
        # clássica (cliente, processo, atividade, tarefa, documento,
        # task_log, histórico) + 13 dependentes (11 colecções + 2 visitas)
        assert total == 20
        # nada foi apagado em dry-run
        assert len(fake_async_db.rgpd_requests.docs) == 2

    async def test_hard_mode_apaga_os_12_filhos_sem_orfaos(self, fake_async_db, monkeypatch):
        monkeypatch.setattr(cleanup_script, "_confirm_password", lambda: True)
        self._seed(fake_async_db)

        with patch.object(database_module, "db", fake_async_db):
            await cleanup_prod_test_data(dry_run=False, mode="hard")

        # 11 colecções filhas: registos do processo de teste apagados,
        # os do processo REAL intactos (sem falsos positivos)
        for coll in PROCESS_CHILD_COLLECTIONS:
            remaining = fake_async_db.collection(coll).docs
            assert all(d["process_id"] != "p-test" for d in remaining), coll
            assert any(d["process_id"] == "p-real" for d in remaining), coll
        # visits: por process_id E por client_id; a real intacta
        visits = fake_async_db.visits.docs
        assert all(v["id"] != "v-proc" for v in visits)
        assert all(v["id"] != "v-cli" for v in visits)
        assert any(v["id"] == "v-real" for v in visits)
        # drivers + pais hard-deleted; os reais intactos
        assert all(p["id"] != "p-test" for p in fake_async_db.processes.docs)
        assert any(p["id"] == "p-real" for p in fake_async_db.processes.docs)
        assert all(c["id"] != "cl-test" for c in fake_async_db.clients.docs)
        assert any(c["id"] == "cl-real" for c in fake_async_db.clients.docs)
        assert all(t["id"] != "t-test" for t in fake_async_db.tasks.docs)
        assert all(d["id"] != "d-test" for d in fake_async_db.documents.docs)
        assert all(tl["id"] != "tl-test" for tl in fake_async_db.task_logs.docs)
        assert all(h["id"] != "h-test" for h in fake_async_db.history.docs)
        assert all(a["id"] != "a-test" for a in fake_async_db.activities.docs)

    async def test_soft_mode_tambem_apaga_os_filhos(self, fake_async_db, monkeypatch):
        """Modo soft: os filhos dependentes são hard-delete (como os
        task_logs) — os pais é que ficam marcados is_deleted."""
        monkeypatch.setattr(cleanup_script, "_confirm_password", lambda: True)
        self._seed(fake_async_db)

        with patch.object(database_module, "db", fake_async_db):
            await cleanup_prod_test_data(dry_run=False, mode="soft")

        # filhos dependentes APAGADOS em modo soft (sem órfãos escondidos)
        for coll in PROCESS_CHILD_COLLECTIONS:
            remaining = fake_async_db.collection(coll).docs
            assert all(d["process_id"] != "p-test" for d in remaining), coll
            assert any(d["process_id"] == "p-real" for d in remaining), coll
        visits = fake_async_db.visits.docs
        assert all(v["id"] != "v-proc" for v in visits)
        assert all(v["id"] != "v-cli" for v in visits)

        # pais soft-deleted (reversível) — não apagados fisicamente
        p_test = [p for p in fake_async_db.processes.docs if p["id"] == "p-test"]
        assert p_test and p_test[0]["is_deleted"] is True
        assert p_test[0]["deleted_by"] == "cleanup_test_data_script"
        cl_test = [c for c in fake_async_db.clients.docs if c["id"] == "cl-test"]
        assert cl_test and cl_test[0]["is_deleted"] is True
        # os reais intactos
        p_real = [p for p in fake_async_db.processes.docs if p["id"] == "p-real"][0]
        assert p_real.get("is_deleted") is not True
