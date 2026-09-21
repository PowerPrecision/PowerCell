"""PACOTE 12 — Eixo 2 (Emails/Webmail): testes unitários (fake_async_db).

Cobertura (sem I/O Mongo real — padrão test_document_portal_fulfill.py):
1. Filtro ESTRITO por process_id: emails não associados deixam de ser
   agregados por endereço de participante (Pacote DN.3 removido);
2. BCC end-to-end: EmailSendRequest → pending record → kwargs do send_email
   (+ draft do cancel repõe a cópia oculta no composer);
3. Assinatura HTML sintetizada quando o corpo é só texto (_synthesize_html_body);
4. Branding da empresa activa: resolve_active_company_branding (system_config
   company-scoped → companies por id → fallback global);
5. portal_url no email de confirmação de registo (CTA <a href>);
6. get_base_template com company_name (branding exclusivo, sem dual-brand);
7. Branding da empresa activa no fluxo de envio (run_send_email persiste
   company_name no registo pending — best-effort).

Correr: .venv/bin/python -m pytest tests/unit/test_pacote12_emails_webmail.py -q
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

from tests.unit.conftest import FakeAsyncCollection, FakeAsyncCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class _AggregateStatsEmails(FakeAsyncCollection):
    """Extensão local do fake com ``aggregate`` ($match + $group por
    direction) — o fake do conftest não implementa agregações e o
    conftest é intocável (regra do pacote)."""

    def aggregate(self, pipeline):
        match = (pipeline[0] or {}).get("$match", {})
        docs = [d for d in self.docs if self._matches(d, match)]
        counts: dict = {}
        for doc in docs:
            key = doc.get("direction")
            counts[key] = counts.get(key, 0) + 1
        return FakeAsyncCursor(
            [{"_id": direction, "count": count} for direction, count in counts.items()]
        )


# ====================================================================
# 1) FILTRO ESTRITO POR process_id
# ====================================================================

class TestStrictProcessFilter:
    """A lista de emails do processo mostra APENAS os emails associados."""

    def test_base_conditions_devolve_apenas_condicao_estrita(self):
        from services.email_process_crud import build_process_emails_base_conditions

        # mesmo com endereços de participante, devolve só a condição estrita
        conditions = build_process_emails_base_conditions("P-1", {"cli@x.pt"})
        assert conditions == [{"process_id": "P-1"}]

        # sem endereços (callers históricos) o resultado é idêntico
        assert build_process_emails_base_conditions("P-1") == [{"process_id": "P-1"}]

    async def test_run_get_process_emails_exclui_nao_associados(self, fake_async_db):
        """Email do mesmo cliente SEM process_id não aparece na lista."""
        from services import email_process_crud as crud
        from services import email_enrich as enrich_mod

        await fake_async_db.emails.insert_one({
            "id": "e-linked",
            "process_id": "P-1",
            "direction": "sent",
            "from_email": "staff@x.pt",
            "to_emails": ["cli@x.pt"],
            "subject": "Documentação",
            "body": "Corpo",
            "sent_at": "2026-02-01T10:00:00+00:00",
            "created_at": "2026-02-01T10:00:00+00:00",
            "status": "sent",
        })
        # não associado (process_id ausente) mas do MESMO cliente — antes
        # era agregado pela cláusula de participante do Pacote DN.3
        await fake_async_db.emails.insert_one({
            "id": "e-unassigned",
            "direction": "received",
            "from_email": "cli@x.pt",
            "to_emails": ["staff@x.pt"],
            "subject": "Re: Documentação",
            "body": "Resposta",
            "sent_at": "2026-02-02T10:00:00+00:00",
            "created_at": "2026-02-02T10:00:00+00:00",
            "status": "synced",
        })

        current_user = {"id": "u1", "email": "staff@x.pt", "role": "consultor"}
        with patch.object(crud, "db", fake_async_db), \
             patch.object(enrich_mod, "db", fake_async_db):
            emails = await crud.run_get_process_emails("P-1", current_user)

        ids = [e.id for e in emails]
        assert ids == ["e-linked"]

    async def test_run_get_email_stats_conta_apenas_associados(self, fake_async_db):
        """Estatísticas com o mesmo filtro estrito (query process_id)."""
        from services import email_process_crud as crud

        # o fake do conftest não tem ``aggregate`` — a colecção emails é
        # substituída por uma extensão local antes de inserir os docs
        fake_async_db._collections["emails"] = _AggregateStatsEmails()
        await fake_async_db.emails.insert_many([
            {"id": "e-1", "process_id": "P-1", "direction": "sent",
             "from_email": "staff@x.pt", "to_emails": ["cli@x.pt"],
             "subject": "A", "body": "b", "status": "sent"},
            {"id": "e-2", "process_id": "P-1", "direction": "received",
             "from_email": "cli@x.pt", "to_emails": ["staff@x.pt"],
             "subject": "B", "body": "b", "status": "synced"},
            {"id": "e-unassigned", "direction": "received",
             "from_email": "cli@x.pt", "to_emails": ["staff@x.pt"],
             "subject": "C", "body": "b", "status": "synced"},
        ])

        current_user = {"id": "u1", "email": "staff@x.pt", "role": "consultor"}
        with patch.object(crud, "db", fake_async_db):
            stats = await crud.run_get_email_stats("P-1", current_user)

        assert stats["total"] == 2
        assert stats["sent"] == 1
        assert stats["received"] == 1


# ====================================================================
# 2) BCC END-TO-END
# ====================================================================

class TestBccEndToEnd:
    """Cópia oculta: payload → registo pending → kwargs do send_email."""

    def test_email_send_request_acepta_bcc(self):
        from models.email import EmailSendRequest

        payload = EmailSendRequest(
            to_emails=["destino@x.pt"],
            subject="Assunto",
            body="Corpo",
            bcc_emails=["oculto@x.pt", "outro@x.pt"],
        )
        assert payload.bcc_emails == ["oculto@x.pt", "outro@x.pt"]

        # default: None (estilo do cc_emails — sem breaking change)
        default_payload = EmailSendRequest(to_emails=["d@x.pt"], subject="S", body="B")
        assert default_payload.bcc_emails is None

    def test_build_pending_send_record_persiste_bcc_e_company_name(self):
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=["c@x.pt"], bcc_emails=["oculto@x.pt"],
            process_id="P-1", from_box="personal", from_email="u@x.pt",
            company_id="co-1", company_name="ImoPrime Lda",
            created_by="u1", created_by_email="u1@x.pt", attachment_ids=[],
        )
        assert record["bcc_emails"] == ["oculto@x.pt"]
        assert record["company_name"] == "ImoPrime Lda"
        # sem bcc → None (não lista vazia), coerente com o CC
        record_no_bcc = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, process_id=None, from_box=None,
            from_email=None, company_id=None, created_by="u1",
            created_by_email=None, attachment_ids=[],
        )
        assert record_no_bcc["bcc_emails"] is None
        assert record_no_bcc["company_name"] is None

    async def test_execute_passa_bcc_ao_send_email(self, fake_async_db):
        """O executor passa bcc_emails (e company_name) ao transport."""
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=["cc@x.pt"], bcc_emails=["oculto@x.pt"],
            process_id="P-1", from_box="personal", from_email="u@x.pt",
            company_id="co-1", company_name="ImoPrime Lda",
            created_by="u1", created_by_email="u1@x.pt", attachment_ids=[],
        )
        await fake_async_db.pending_email_sends.insert_one(dict(record))
        send_mock = AsyncMock(return_value={"success": True})

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "send_email", send_mock):
            result = await q.execute_pending_email_send(record["id"])

        assert result["success"] is True
        kwargs = send_mock.await_args.kwargs
        assert kwargs["bcc_emails"] == ["oculto@x.pt"]
        assert kwargs["cc_emails"] == ["cc@x.pt"]
        assert kwargs["company_name"] == "ImoPrime Lda"
        assert kwargs["active_company_id"] == "co-1"

    async def test_cancel_draft_restaura_bcc(self, fake_async_db):
        """O payload do Desfazer inclui a cópia oculta (composer repõe BCC)."""
        from services import email_send_queue as q

        record = q.build_pending_send_record(
            account="personal", to_emails=["a@b.pt"], subject="S", body="B",
            body_html=None, cc_emails=None, bcc_emails=["oculto@x.pt"],
            process_id="P-1", from_box="personal", from_email="u@x.pt",
            company_id=None, created_by="u1", created_by_email=None,
            attachment_ids=[],
        )
        await fake_async_db.pending_email_sends.insert_one(dict(record))

        with patch.object(q, "db", fake_async_db):
            cancel = await q.cancel_pending_email_send(
                record["id"], {"id": "u1", "role": "consultor"}
            )

        assert cancel["cancelled"] is True
        assert cancel["draft"]["bcc_emails"] == ["oculto@x.pt"]

    async def test_run_send_email_sanitiza_e_persiste_bcc(self, fake_async_db):
        """run_send_email sanitiza o BCC (entradas inválidas descartadas)."""
        from models.email import EmailSendRequest
        from services import email_process_crud as crud
        from services import email_send_queue as q

        payload = EmailSendRequest(
            to_emails=["destino@x.pt"],
            subject="Assunto",
            body="Corpo",
            bcc_emails=["oculto@x.pt", "não-é-email"],
        )
        request = MagicMock()
        request.headers = {}  # sem x-company-id → sem branding

        send_mock = AsyncMock(return_value={"success": True})
        schedule_mock = AsyncMock()

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "schedule_pending_email_send", schedule_mock), \
             patch.object(q, "send_email", send_mock), \
             patch("services.email_config_resolver.resolve_email_config_for_sync",
                   AsyncMock(return_value={"email_address": "geral@x.pt"})), \
             patch("services.auth.get_active_company_id_async", AsyncMock(return_value=None)):
            response = await crud.run_send_email(
                payload, request, {"id": "u1", "email": "u1@x.pt", "role": "consultor"},
                account="personal",
            )

        assert response["queued"] is True
        stored = await fake_async_db.pending_email_sends.find_one(
            {"id": response["send_id"]}
        )
        # o endereço inválido foi descartado pelo sanitize_email
        assert stored["bcc_emails"] == ["oculto@x.pt"]


# ====================================================================
# 3) ASSINATURA HTML SINTETIZADA (corpo plain-text + assinatura HTML)
# ====================================================================

class TestSynthesizeHtmlBody:
    """_synthesize_html_body: escape, parágrafos e div da assinatura."""

    def test_escapa_html_e_constroi_paragrafos(self):
        from services.email_service import _synthesize_html_body

        html = _synthesize_html_body(
            "Olá <b>mundo</b>\n\nSegundo parágrafo\ncom quebra",
            "<p>Assinatura da Empresa</p>",
        )
        # corpo escapado (o <b> do texto não vira HTML real)
        assert "&lt;b&gt;mundo&lt;/b&gt;" in html
        # parágrafos (\n\n → </p><p>) e quebra isolada (<br/>)
        assert "<p>Olá" in html
        assert "</p><p>Segundo parágrafo<br/>com quebra</p>" in html
        # separador + assinatura dentro da div segura (mesmo wrapper do body_html)
        assert "<br/><hr/>" in html
        assert '<div style="max-width: 100%; overflow-x: hidden;"><p>Assinatura da Empresa</p></div>' in html

    def test_corpo_vazio_degenera_com_assinatura(self):
        from services.email_service import _synthesize_html_body

        html = _synthesize_html_body("", "<div>Ass.</div>")
        assert html.startswith("<p></p>")
        assert "<div>Ass.</div>" in html

    def test_assinatura_com_imagem_mantem_marco_saudavel(self):
        from services.email_service import _synthesize_html_body

        # o safe_signature do send_email (img com style inline) passa tal-qual
        signature = '<img src="https://cdn.example/logo.png" style="max-width: 100%;">'
        html = _synthesize_html_body("Corpo", signature)
        assert signature in html


# ====================================================================
# 4) BRANDING DA EMPRESA ACTIVA (resolve_active_company_branding)
# ====================================================================

class TestResolveActiveCompanyBranding:
    """system_config company-scoped → companies por id → fallback global."""

    async def test_system_config_por_empresa_ganha(self, fake_async_db):
        import database as database_module
        from services.email_branding import resolve_active_company_branding

        await fake_async_db.system_config.insert_one({
            "_id": "company:co-9",
            "settings": {"company_name": "Imobiliaria Prime", "logo_url": "https://cdn.example/prime.png"},
        })
        # fontes que NÃO devem ser usadas neste ramo
        await fake_async_db.system_config.insert_one({"_id": "main", "settings": {"company_name": "Global Errada"}})
        await fake_async_db.companies.insert_one({"id": "co-9", "name": "Nome Errado"})

        with patch.object(database_module, "db", fake_async_db):
            name, logo = await resolve_active_company_branding("co-9")

        assert name == "Imobiliaria Prime"
        assert logo == "https://cdn.example/prime.png"

    async def test_companies_por_id_como_fallback(self, fake_async_db):
        import database as database_module
        from services.email_branding import resolve_active_company_branding

        # sem config própria da empresa → documento companies pelo id
        await fake_async_db.companies.insert_one({
            "id": "co-7", "name": "Crédito Zero Lda", "logo_url": "https://cdn.example/c0.png",
        })

        with patch.object(database_module, "db", fake_async_db):
            name, logo = await resolve_active_company_branding("co-7")

        assert name == "Crédito Zero Lda"
        assert logo == "https://cdn.example/c0.png"

    async def test_fallback_global_para_empresa_desconhecida(self, fake_async_db):
        import database as database_module
        from services.email_branding import resolve_active_company_branding

        # id desconhecido (sem config nem doc da empresa) → branding GLOBAL:
        # o nome do system_config ``main`` ganha (mesmo sem logo nele)
        await fake_async_db.system_config.insert_one({
            "_id": "main", "settings": {"company_name": "Global Config", "logo_url": None},
        })
        await fake_async_db.companies.insert_one({
            "id": "co-other", "is_active": True, "name": "Outra Empresa",
            "logo_url": "https://cdn.example/other.png",
        })

        with patch.object(database_module, "db", fake_async_db):
            name, logo = await resolve_active_company_branding("co-desconhecida")

        assert name == "Global Config"
        assert logo is None

    async def test_fallback_global_sem_config_usa_primeira_empresa(self, fake_async_db):
        import database as database_module
        from services.email_branding import resolve_active_company_branding

        # ``main`` vazio → primeira empresa activa fornece o branding
        await fake_async_db.system_config.insert_one({"_id": "main", "settings": {}})
        await fake_async_db.companies.insert_one({
            "id": "co-other", "is_active": True, "name": "Outra Empresa",
            "logo_url": "https://cdn.example/other.png",
        })

        with patch.object(database_module, "db", fake_async_db):
            name, logo = await resolve_active_company_branding(None)

        assert name == "Outra Empresa"
        assert logo == "https://cdn.example/other.png"

    async def test_sem_company_id_resolve_global(self, fake_async_db):
        import database as database_module
        from services.email_branding import resolve_active_company_branding

        await fake_async_db.system_config.insert_one({
            "_id": "main", "settings": {"company_name": "Global Config"},
        })

        with patch.object(database_module, "db", fake_async_db):
            name, logo = await resolve_active_company_branding(None)

        assert name == "Global Config"
        assert logo is None

    async def test_nada_configurado_devolve_none_none(self, fake_async_db):
        import database as database_module
        from services.email_branding import resolve_active_company_branding

        with patch.object(database_module, "db", fake_async_db):
            assert await resolve_active_company_branding("co-x") == (None, None)


# ====================================================================
# 5) PORTAL URL NO EMAIL DE CONFIRMAÇÃO DE REGISTO
# ====================================================================

class TestRegistrationConfirmationPortalUrl:
    """portal_url → CTA <a href> no HTML + URL por extenso no texto."""

    async def test_html_contem_cta_e_texto_contem_url(self):
        import services.email as email_mod
        from services.email import send_registration_confirmation

        send_mock = AsyncMock(return_value={"success": True})
        portal_url = "https://portal.exemplo.pt/acesso?c=ABC123"

        with patch.object(email_mod, "resolve_base_template_logo", AsyncMock(return_value=None)), \
             patch("services.email_service.send_email", send_mock):
            ok = await send_registration_confirmation(
                "cli@x.pt",
                "Cliente Exemplo",
                portal_access_code="987654",
                portal_url=portal_url,
                company_name="ImoPrime Lda",
            )

        assert ok is True
        kwargs = send_mock.await_args.kwargs
        html_body = kwargs["body_html"]
        body_text = kwargs["body"]
        # CTA clicável no bloco do Portal
        assert f'<a href="{portal_url}" class="btn">Aceder ao Portal do Cliente</a>' in html_body
        # URL por extenso na versão em texto
        assert f"Aceder ao Portal: {portal_url}" in body_text
        # assunto com o nome efectivo da empresa (não o dual-brand hardcoded)
        assert kwargs["subject"] == "Recebemos o seu pedido - ImoPrime Lda"
        # branding exclusivo no template base
        assert "<h1>ImoPrime Lda</h1>" in html_body

    async def test_sem_portal_url_mantem_comportamento_anterior(self):
        import services.email as email_mod
        from services.email import send_registration_confirmation

        send_mock = AsyncMock(return_value={"success": True})

        with patch.object(email_mod, "resolve_base_template_logo", AsyncMock(return_value=None)), \
             patch("services.email_service.send_email", send_mock):
            ok = await send_registration_confirmation(
                "cli@x.pt", "Cliente Exemplo", portal_access_code="987654",
            )

        assert ok is True
        html_body = send_mock.await_args.kwargs["body_html"]
        body_text = send_mock.await_args.kwargs["body"]
        # sem portal_url: sem CTA e sem URL por extenso
        assert 'class="btn"' not in html_body
        assert "Aceder ao Portal:" not in body_text
        # código de acesso continua presente
        assert "987654" in html_body
        assert "987654" in body_text


# ====================================================================
# 6) get_base_template — BRANDING EXCLUSIVO vs HEADER LEGADO
# ====================================================================

class TestGetBaseTemplateBranding:
    """company_name → header exclusivo; default → header dual-brand legado."""

    def test_com_company_name_header_exclusivo(self):
        from services.email import get_base_template

        html = get_base_template("<p>Corpo</p>", "Título", company_name="ImoPrime Lda")
        header = html.split('<div class="header">')[1].split("</div>")[0]
        assert "<h1>ImoPrime Lda</h1>" in header
        assert "Precision Crédito" not in header  # sem subtítulo dual-brand
        # rodapé com o nome efectivo
        assert '<p class="company">ImoPrime Lda</p>' in html

    def test_sem_company_name_mantem_header_legado(self):
        from services.email import get_base_template

        html = get_base_template("<p>Corpo</p>", "Título")
        assert "<h1>Power Real Estate</h1>" in html
        assert 'class="subtitle">& Precision Crédito' in html


# ====================================================================
# 7) BRANDING DA EMPRESA ACTIVA NO FLUXO DE ENVIO (run_send_email)
# ====================================================================

class TestRunSendBranding:
    """run_send_email resolve o nome da empresa e persiste no registo."""

    async def test_company_name_resolvido_e_persistido(self, fake_async_db):
        from models.email import EmailSendRequest
        from services import email_process_crud as crud
        from services import email_send_queue as q

        payload = EmailSendRequest(
            to_emails=["destino@x.pt"], subject="Assunto", body="Corpo",
        )
        request = MagicMock()
        request.headers = {"x-company-id": "co-1"}  # empresa activa na sessão

        send_mock = AsyncMock(return_value={"success": True})
        schedule_mock = AsyncMock()
        branding_mock = AsyncMock(return_value=("ImoPrime Lda", "https://cdn.example/logo.png"))

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "schedule_pending_email_send", schedule_mock), \
             patch.object(q, "send_email", send_mock), \
             patch("services.email_branding.resolve_active_company_branding", branding_mock), \
             patch("services.email_config_resolver.resolve_email_config_for_sync",
                   AsyncMock(return_value={"email_address": "geral@x.pt"})):
            response = await crud.run_send_email(
                payload, request,
                {"id": "u1", "email": "u1@x.pt", "role": "consultor"},
                account="personal",
            )

        assert response["queued"] is True
        branding_mock.assert_awaited_once_with("co-1")
        stored = await fake_async_db.pending_email_sends.find_one(
            {"id": response["send_id"]}
        )
        assert stored["company_id"] == "co-1"
        assert stored["company_name"] == "ImoPrime Lda"

    async def test_falha_de_branding_degrada_para_default(self, fake_async_db):
        """Branding indisponível → company_name None (envio não é bloqueado)."""
        from models.email import EmailSendRequest
        from services import email_process_crud as crud
        from services import email_send_queue as q

        payload = EmailSendRequest(
            to_emails=["destino@x.pt"], subject="Assunto", body="Corpo",
        )
        request = MagicMock()
        request.headers = {"x-company-id": "co-1"}

        send_mock = AsyncMock(return_value={"success": True})
        schedule_mock = AsyncMock()
        branding_mock = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.object(q, "db", fake_async_db), \
             patch.object(q, "schedule_pending_email_send", schedule_mock), \
             patch.object(q, "send_email", send_mock), \
             patch("services.email_branding.resolve_active_company_branding", branding_mock), \
             patch("services.email_config_resolver.resolve_email_config_for_sync",
                   AsyncMock(return_value={"email_address": "geral@x.pt"})):
            response = await crud.run_send_email(
                payload, request,
                {"id": "u1", "email": "u1@x.pt", "role": "consultor"},
                account="personal",
            )

        assert response["queued"] is True
        stored = await fake_async_db.pending_email_sends.find_one(
            {"id": response["send_id"]}
        )
        assert stored["company_name"] is None
