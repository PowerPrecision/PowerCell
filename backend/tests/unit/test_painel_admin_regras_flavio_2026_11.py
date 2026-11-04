"""Regras do Painel de Administração definidas pelo Flavio (Nov 2026).

Respostas: 1a, 2a, 3a, 4b, 5a–14a. As que se testam aqui são as do servidor:

* 4b — o CEO grava tudo da empresa; o Admin já não (dados, honorários, configurações);
* 5a/8a/9a — armazenamento, IA, auditoria e backups automáticos são globais (só Master);
* 6a/7a — DSTI, rascunhos automáticos e balcões lêem-se pela EMPRESA do processo;
* 10a — o email geral grava-se na ficha da empresa e é o que o Webmail lê;
* 13a — alterar o que é da rede avisa a Gestão das OUTRAS empresas da rede;
* 14a — cada gravação do painel fica no Registo de auditoria.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import config_da_empresa as cde
from services import registo_do_painel as reg
from services import system_config as sc


@pytest.fixture(autouse=True)
def _cache_limpa():
    sc._config_cache.clear()
    yield
    sc._config_cache.clear()


def _semear_empresas(db):
    db.companies.docs.extend([
        {"id": "cmp-power", "name": "Power", "network_id": "rede-pp"},
        {"id": "cmp-precision", "name": "Precision", "network_id": "rede-pp"},
        {"id": "cmp-sistema", "name": "Sistema", "network_id": "rede-pp"},
        {"id": "cmp-domus", "name": "Domus", "network_id": "rede-domus"},
    ])


# ---------------------------------------------------------------------------
# 6a / 7a — leitores por empresa
# ---------------------------------------------------------------------------

class TestLeitoresPorEmpresa:
    async def test_a_empresa_do_processo_vem_do_id_ou_do_nome(self, fake_async_db):
        _semear_empresas(fake_async_db)
        assert await cde.empresa_do_processo({"company_id": "cmp-power"}, bd=fake_async_db) == "cmp-power"
        assert await cde.empresa_do_processo({"company_name": "Precision"}, bd=fake_async_db) == "cmp-precision"
        assert await cde.empresa_do_processo({"company_id": "default"}, bd=fake_async_db) == "default"
        assert await cde.empresa_do_processo({}, bd=fake_async_db) == "default"
        assert await cde.empresa_do_processo({"company": "inventada"}, bd=fake_async_db) == "default"

    async def test_o_DSTI_de_um_processo_usa_os_limiares_da_empresa_dele(self, fake_async_db):
        from services import process_dsti

        _semear_empresas(fake_async_db)
        fake_async_db.system_config.docs.extend([
            {"_id": "main", "dsti_analysis": {"enabled": True, "high_risk_threshold": 50}},
            {"_id": "company:cmp-power", "company_id": "cmp-power",
             "dsti_analysis": {"enabled": True, "high_risk_threshold": 33, "critical_risk_threshold": 40}},
        ])
        fake_async_db.processes.docs.append(
            {"id": "p1", "company_id": "cmp-power", "financial_data": {}, "personal_data": {}},
        )
        with patch.object(process_dsti, "db", fake_async_db), patch.object(sc, "db", fake_async_db):
            res = await process_dsti.run_get_process_dsti("p1", {}, can_view_fn=lambda *_: True)
        assert res["high_risk_threshold"] == 33

    async def test_o_DSTI_desligado_numa_empresa_nao_desliga_a_outra(self, fake_async_db):
        from services import process_dsti

        _semear_empresas(fake_async_db)
        fake_async_db.system_config.docs.extend([
            {"_id": "main", "dsti_analysis": {"enabled": True}},
            {"_id": "company:cmp-power", "company_id": "cmp-power", "dsti_analysis": {"enabled": False}},
        ])
        fake_async_db.processes.docs.extend([
            {"id": "p-power", "company_id": "cmp-power"},
            {"id": "p-precision", "company_id": "cmp-precision"},
        ])
        with patch.object(process_dsti, "db", fake_async_db), patch.object(sc, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await process_dsti.run_get_process_dsti("p-power", {}, can_view_fn=lambda *_: True)
            assert exc.value.status_code == 403
            res = await process_dsti.run_get_process_dsti("p-precision", {}, can_view_fn=lambda *_: True)
        assert res["process_id"] == "p-precision"

    async def test_os_rascunhos_automaticos_sao_os_da_empresa_do_processo(self, fake_async_db):
        from services import email_draft_service as eds

        _semear_empresas(fake_async_db)
        fake_async_db.system_config.docs.extend([
            {"_id": "main", "auto_draft": {"enabled": False}},
            {"_id": "company:cmp-precision", "company_id": "cmp-precision",
             "auto_draft": {"enabled": True, "eligible_doc_types": ["irs"]}},
        ])
        fake_async_db.processes.docs.append({"id": "p1", "company_id": "cmp-precision"})
        with patch.object(eds, "db", fake_async_db), patch.object(sc, "db", fake_async_db):
            da_empresa = await eds.get_auto_draft_config("p1")
            global_ = await eds.get_auto_draft_config(None)
        assert da_empresa["enabled"] is True and da_empresa["eligible_doc_types"] == ["irs"]
        assert global_["enabled"] is False

    async def test_os_balcoes_sao_os_da_empresa(self, fake_async_db):
        from services import email_documentation as ed

        _semear_empresas(fake_async_db)
        fake_async_db.system_config.docs.extend([
            {"_id": "main", "document_recipients": {"enabled": False}},
            {"_id": "company:cmp-power", "company_id": "cmp-power",
             "document_recipients": {"enabled": True, "recipients": '[{"name": "Balcão A", "email": "a@b.pt"}]'}},
        ])
        with patch.object(ed, "db", fake_async_db), patch.object(sc, "db", fake_async_db):
            power = await ed.run_get_document_recipients({"id": "u1", "role": "ceo"}, "cmp-power")
            outra = await ed.run_get_document_recipients({"id": "u1", "role": "ceo"}, "cmp-precision")
        assert power["enabled"] is True
        assert any(r.get("email") == "a@b.pt" for r in power["recipients"])
        assert outra["enabled"] is False


# ---------------------------------------------------------------------------
# 4b / 5a / 8a / 9a — quem grava cada secção
# ---------------------------------------------------------------------------

class TestQuemGravaCadaSeccao:
    def _ambito(self, papel, master=False):
        from services.system_config_scope import AmbitoDeConfiguracao
        from services.tenant_network import TenantScope

        return AmbitoDeConfiguracao(
            papel=papel,
            scope=TenantScope(network_ids=("rede-pp",), company_ids=("cmp-power",), company_names=("Power",),
                              inclui_rede_de_omissao=False, sem_fronteira=master),
            conta_master=master,
        )

    @pytest.mark.parametrize("seccao", ["settings", "credit_services", "dsti_analysis", "auto_draft", "document_recipients", "email"])
    def test_o_CEO_grava_a_empresa_e_o_ADMIN_nao(self, seccao):
        from services.system_config_scope import exigir_pode_gravar_seccao

        exigir_pode_gravar_seccao(self._ambito("ceo"), seccao, "cmp-power")
        with pytest.raises(HTTPException) as exc:
            exigir_pode_gravar_seccao(self._ambito("admin"), seccao, "cmp-power")
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            exigir_pode_gravar_seccao(self._ambito("diretor"), seccao, "cmp-power")

    @pytest.mark.parametrize("seccao", ["storage", "ai", "audit_trail", "dashboard_slas"])
    def test_o_que_e_global_so_se_grava_na_global(self, seccao):
        from services.system_config_scope import exigir_pode_gravar_seccao

        for papel, master in (("ceo", False), ("master", True)):
            with pytest.raises(HTTPException) as exc:
                exigir_pode_gravar_seccao(self._ambito(papel, master), seccao, "cmp-power")
            assert exc.value.status_code == 400
        exigir_pode_gravar_seccao(self._ambito("master", True), seccao, "default")

    def test_os_backups_automaticos_caem_numa_gravacao_por_empresa(self):
        from services.system_config_scope import tirar_campos_so_globais

        dados = {"company_subtitle": "x", "auto_backup_enabled": True}
        assert tirar_campos_so_globais("settings", dados, "cmp-power") == {"company_subtitle": "x"}
        assert tirar_campos_so_globais("settings", dados, "default") == dados

    def test_honorarios_so_master_e_ceo(self):
        from models.auth import UserRole
        from routes.finance import PAPEIS_QUE_GRAVAM_HONORARIOS

        assert set(PAPEIS_QUE_GRAVAM_HONORARIOS) == {UserRole.MASTER, UserRole.CEO}


# ---------------------------------------------------------------------------
# 4b / 10a — ficha da empresa
# ---------------------------------------------------------------------------

class TestFichaDaEmpresa:
    async def test_o_ADMIN_nao_altera_os_dados_da_empresa(self):
        from services import companies_crud_api_mutate as m

        with patch("services.tenant_access_context.resolver_papel_efectivo", AsyncMock(return_value="admin")):
            with pytest.raises(HTTPException) as exc:
                await m.exigir_quem_grava_a_empresa({"id": "u1", "role": "admin"})
        assert exc.value.status_code == 403
        with patch("services.tenant_access_context.resolver_papel_efectivo", AsyncMock(return_value="ceo")):
            await m.exigir_quem_grava_a_empresa({"id": "u2", "role": "consultor"})
        await m.exigir_quem_grava_a_empresa({"id": "u3", "role": "master"})

    def test_o_email_geral_da_ficha_vira_o_email_da_configuracao(self):
        from services.companies_crud_api_mutate import email_geral_da_ficha

        assert email_geral_da_ficha({
            "smtp_email": "geral@x.pt", "smtp_password": "", "smtp_host": "smtp.x.pt", "smtp_port": "465",
            "imap_host": "imap.x.pt", "imap_port": None, "name": "X",
        }) == {"smtp_user": "geral@x.pt", "smtp_server": "smtp.x.pt", "smtp_port": 465, "imap_server": "imap.x.pt"}

    async def test_gravar_a_ficha_grava_a_caixa_geral_da_empresa(self, fake_async_db):
        from services import companies_crud_api_mutate as m

        fake_async_db.system_config.docs.append({"_id": "main"})
        with patch.object(sc, "db", fake_async_db):
            await m.espelhar_email_geral("cmp-power", {"smtp_email": "geral@power.pt", "smtp_host": "smtp.power.pt", "smtp_password": "segredo"})
        doc = next(d for d in fake_async_db.system_config.docs if d["_id"] == "company:cmp-power")
        assert doc["email"]["smtp_user"] == "geral@power.pt"
        assert doc["email"]["smtp_server"] == "smtp.power.pt"
        assert doc["email"]["smtp_password"] == "segredo"
        assert doc["email"]["provider"] == "smtp"


# ---------------------------------------------------------------------------
# 13a / 14a — rasto e aviso à rede
# ---------------------------------------------------------------------------

class TestRastoEAviso:
    def test_so_entra_no_rasto_o_que_mudou_e_os_segredos_vao_mascarados(self):
        mudou = reg.campos_alterados(
            {"a": 1, "b": 2, "smtp_password": "velha", "api_key": "k"},
            {"a": 1, "b": 3, "smtp_password": "nova", "api_key": reg.MASCARA},
        )
        assert mudou == {"b": (2, 3), "smtp_password": (reg.MASCARA, reg.MASCARA)}

    async def test_cada_gravacao_fica_no_registo_de_auditoria(self):
        with patch("services.audit_trail_service.log_audit_event", AsyncMock(return_value="id-1")) as log:
            await reg.registar_alteracao(
                {"id": "u1", "name": "Ana"}, None, area="Configurações (dsti_analysis)",
                company_id="cmp-power", antes={"enabled": True}, depois={"enabled": False},
            )
            sem_mudanca = await reg.registar_alteracao(
                {"id": "u1"}, None, area="x", antes={"a": 1}, depois={"a": 1},
            )
        assert sem_mudanca is None
        assert log.await_count == 1
        kwargs = log.await_args.kwargs
        assert kwargs["field"] == "enabled"
        assert kwargs["metadata"]["company_id"] == "cmp-power"

    async def test_alterar_o_que_e_da_rede_avisa_a_gestao_das_outras_empresas(self, fake_async_db):
        _semear_empresas(fake_async_db)
        fake_async_db.user_company_roles.docs.extend([
            {"user_id": "dir-power", "company_id": "cmp-power", "role": "diretor"},
            {"user_id": "ceo-precision", "company_id": "cmp-precision", "role": "ceo"},
            {"user_id": "dir-sistema", "company_id": "cmp-sistema", "role": "diretor"},
            {"user_id": "cons-precision", "company_id": "cmp-precision", "role": "consultor"},
            {"user_id": "ceo-domus", "company_id": "cmp-domus", "role": "ceo"},
            {"user_id": "ex-ceo", "company_id": "cmp-precision", "role": "ceo", "is_active": False},
        ])
        autor = {"id": "admin-power", "name": "Ana", "company": "cmp-power"}
        with patch.object(reg, "db", fake_async_db), \
                patch("services.auth.get_active_company_id_async", AsyncMock(return_value="cmp-power")):
            n = await reg.avisar_alteracao_da_rede(autor, object(), area="o Workflow", descricao="fase «X» alterada")
        assert n == 2
        avisados = {d["user_id"] for d in fake_async_db.notifications.docs}
        assert avisados == {"ceo-precision", "dir-sistema"}
        aviso = fake_async_db.notifications.docs[0]
        assert "Ana (Power)" in aviso["message"] and "o Workflow" in aviso["message"]
        assert aviso["alerta"] is False and aviso["urgente"] is False

    async def test_o_rasto_so_se_deixa_se_a_gravacao_correr_bem(self):
        async def falha():
            raise HTTPException(status_code=403, detail="não")

        with patch.object(reg, "registar_alteracao_da_rede", AsyncMock()) as rasto:
            with pytest.raises(HTTPException):
                await reg.run_com_rasto_da_rede(falha(), {}, None, area="x", descricao="y")
        rasto.assert_not_awaited()
