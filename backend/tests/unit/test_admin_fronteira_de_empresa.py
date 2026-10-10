"""
O Admin e o CEO só vêem a sua rede — superfície a superfície (adenda de RBAC).

`require_roles([ADMIN, CEO])` autoriza o VERBO («este perfil pode abrir o
painel do RGPD»), nunca o OBJECTO («este processo é meu?»). Com o Admin a
perfil local, cada superfície onde o Admin/CEO operava sobre dados por
`id` ou sobre uma colecção inteira tem de provar a sua fronteira. Este
ficheiro percorre-as: o ataque primeiro (uma empresa lê/escreve na outra),
depois a contraprova (a sua própria rede e o Master continuam a funcionar).

Cenário: Power e Precision na mesma rede, Domus numa ilha (`helpers_tenant`).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    casa,
    por_id,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ADMIN_POWER = {"id": "u-adm-power", "name": "Admin Power", "email": "adm@power.pt",
               "role": "admin", "effective_role": "admin"}
CEO_DOMUS = {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt",
             "role": "ceo", "effective_role": "ceo"}
MASTER = {"id": "u-master", "name": "Master", "email": "m@x.pt",
          "role": "master", "effective_role": "master"}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-adm-power", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin", "is_default": True},
        {"user_id": "u-ceo-domus", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "ceo", "is_default": True},
    ])
    fake_async_db.users.docs.extend([
        {"id": "u-adm-power", "name": "Admin Power", "email": "adm@power.pt", "role": "admin", "company": "Power Real Estate"},
        {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt", "role": "ceo", "company": "Domus"},
        {"id": "u-cons-power", "name": "Cons Power", "email": "c@power.pt", "role": "consultor", "company": "Power Real Estate"},
        {"id": "u-cons-domus", "name": "Cons Domus", "email": "c@domus.pt", "role": "consultor", "company": "Domus"},
    ])
    return fake_async_db


def _cadeia(mundo, *modulos):
    return tenant_db(mundo, *modulos)


# ════════════════════════════════════════════════════════════════════
#  RGPD — anonimizar e exportar são irreversíveis / exfiltram dados pessoais
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestRGPD:
    async def test_um_CEO_nao_anonimiza_um_processo_de_outra_rede_nem_o_simula(self, mundo):
        import services.gdpr_api_mutate as mut
        from services.gdpr_api_models import AnonymizeRequest

        with _cadeia(mundo, mut):
            for dry in (True, False):
                with pytest.raises(HTTPException) as erro:
                    await mut.run_anonymize_single(
                        AnonymizeRequest(process_id="p-power", dry_run=dry), CEO_DOMUS,
                    )
                assert erro.value.status_code == 404, f"dry_run={dry}: o dry-run já confirmava que existe"
        assert not mundo.gdpr_audit.docs, "ficou registo de uma anonimização recusada"

    async def test_um_CEO_nao_exporta_os_dados_pessoais_de_outra_rede(self, mundo):
        import services.gdpr_api_mutate as mut

        with _cadeia(mundo, mut):
            with pytest.raises(HTTPException) as erro:
                await mut.run_export_data("p-power", CEO_DOMUS)
        assert erro.value.status_code == 404

    async def test_um_Admin_nao_anonimiza_um_utilizador_de_outra_rede(self, mundo):
        import services.admin_users_scope as sc
        import services.gdpr_api_mutate as mut
        import services.user_management_scope as ums
        from services.gdpr_api_models import AnonymizeRequest

        with _cadeia(mundo, mut, sc, ums):
            with pytest.raises(HTTPException) as erro:
                await mut.run_anonymize_single(
                    AnonymizeRequest(user_id="u-cons-domus", dry_run=True), ADMIN_POWER,
                )
        assert erro.value.status_code == 404

    async def test_o_Admin_exporta_o_processo_da_sua_rede(self, mundo):
        import services.gdpr as core
        import services.gdpr_api_mutate as mut

        with _cadeia(mundo, mut, core):
            r = await mut.run_export_data("p-power", ADMIN_POWER)
        assert r["data"]["process"]["id"] == "p-power"

    async def test_o_Master_exporta_qualquer_processo(self, mundo):
        import services.gdpr as core
        import services.gdpr_api_mutate as mut

        with _cadeia(mundo, mut, core):
            r = await mut.run_export_data("p-domus", MASTER)
        assert r["data"]["process"]["id"] == "p-domus"

    async def test_a_condicao_dos_elegiveis_e_das_estatisticas_vem_da_rede(self, mundo):
        import services.gdpr_api_read as rd

        with _cadeia(mundo, rd):
            cond_admin = await rd._condicao_de_rede(ADMIN_POWER)
            cond_master = await rd._condicao_de_rede(MASTER)
        assert por_id(p for p in mundo.processes.docs if casa(p, cond_admin)) == {"p-power", "p-legado"}
        assert cond_master == {}, "o Master não tem condição (vê tudo)"

    async def test_o_registo_gdpr_mostra_so_as_accoes_do_ambito(self, mundo):
        import services.admin_users_scope as sc
        import services.gdpr_api_read as rd
        import services.user_management_scope as ums
        from datetime import datetime, timezone

        agora = datetime.now(timezone.utc)
        mundo.gdpr_audit.docs.extend([
            {"action": "manual_anonymize", "performed_by": "u-cons-power", "timestamp": agora},
            {"action": "manual_anonymize", "performed_by": "u-cons-domus", "timestamp": agora},
        ])
        with _cadeia(mundo, rd, sc, ums):
            admin = await rd.run_get_audit_log(30, None, 100, ADMIN_POWER)
            master = await rd.run_get_audit_log(30, None, 100, MASTER)
        assert {e["performed_by"] for e in admin["entries"]} == {"u-cons-power"}
        assert {e["performed_by"] for e in master["entries"]} == {"u-cons-power", "u-cons-domus"}


# ════════════════════════════════════════════════════════════════════
#  Registos de clientes (formulário público), estatísticas e parados
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestRegistosDeClientes:
    async def test_a_listagem_so_traz_os_registos_da_rede(self, mundo):
        import services.admin_observability as obs

        with _cadeia(mundo, obs):
            r = await obs.run_list_client_registrations(ADMIN_POWER)
        ids = {p["id"] for p in r["registrations"]}
        assert "p-power" in ids
        assert "p-domus" not in ids and "p-domus-sem-rede" not in ids

    async def test_o_Master_lista_todos(self, mundo):
        import services.admin_observability as obs

        with _cadeia(mundo, obs):
            r = await obs.run_list_client_registrations(MASTER)
        assert {"p-power", "p-domus"} <= {p["id"] for p in r["registrations"]}

    async def test_ler_editar_e_apagar_um_registo_alheio_da_404(self, mundo):
        import services.admin_observability as obs

        with _cadeia(mundo, obs):
            for chamada in (
                lambda: obs.run_get_client_registration("p-domus", ADMIN_POWER),
                lambda: obs.run_update_client_registration("p-domus", {"client_name": "X"}, ADMIN_POWER),
                lambda: obs.run_delete_client_registration("p-domus", ADMIN_POWER),
            ):
                with pytest.raises(HTTPException) as erro:
                    await chamada()
                assert erro.value.status_code == 404
        domus = next(p for p in mundo.processes.docs if p["id"] == "p-domus")
        assert domus["client_name"] == "Cliente da Domus" and not domus.get("is_deleted")

    async def test_o_404_de_um_alheio_e_igual_ao_de_um_inexistente(self, mundo):
        import services.admin_observability as obs

        with _cadeia(mundo, obs):
            with pytest.raises(HTTPException) as alheio:
                await obs.run_get_client_registration("p-domus", ADMIN_POWER)
            with pytest.raises(HTTPException) as nada:
                await obs.run_get_client_registration("nao-existe", ADMIN_POWER)
        assert alheio.value.status_code == nada.value.status_code
        assert alheio.value.detail == nada.value.detail

    async def test_o_Admin_gere_um_registo_da_sua_rede(self, mundo):
        import services.admin_observability as obs

        with _cadeia(mundo, obs):
            r = await obs.run_get_client_registration("p-power", ADMIN_POWER)
        assert r["registration"]["id"] == "p-power"

    async def test_as_estatisticas_contam_so_a_rede(self, mundo):
        import services.admin_observability as obs

        with _cadeia(mundo, obs):
            local = await obs.run_get_client_registrations_stats(ADMIN_POWER)
            global_ = await obs.run_get_client_registrations_stats(MASTER)
        assert local["total"] < global_["total"]
        assert global_["total"] == len(mundo.processes.docs)

    async def test_os_processos_parados_so_da_rede(self, mundo):
        import services.admin_observability as obs

        for p in mundo.processes.docs:
            p["updated_at"] = "2020-01-01T00:00:00+00:00"
        with _cadeia(mundo, obs):
            local = await obs.run_get_stale_processes(ADMIN_POWER, 14)
            tudo = await obs.run_get_stale_processes(MASTER, 14)
        assert {p["id"] for p in local["processes"]} == {"p-power", "p-legado"}
        assert {"p-domus"} <= {p["id"] for p in tudo["processes"]}


# ════════════════════════════════════════════════════════════════════
#  Auditoria — o registo leva o autor, não a rede
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAuditoria:
    async def test_o_audit_logs_so_mostra_as_accoes_dos_utilizadores_do_ambito(self, mundo):
        import services.admin_observability as obs
        import services.admin_users_scope as sc
        import services.user_management_scope as ums

        mundo.audit_logs.docs.extend([
            {"id": "a1", "action": "user_created", "performed_by_id": "u-cons-power", "timestamp": "2026-10-01"},
            {"id": "a2", "action": "user_deleted", "performed_by_id": "u-cons-domus", "timestamp": "2026-10-02"},
        ])
        with _cadeia(mundo, obs, sc, ums):
            local = await obs.run_get_audit_logs(ADMIN_POWER)
            tudo = await obs.run_get_audit_logs(MASTER)
        assert {l["id"] for l in local["logs"]} == {"a1"}
        assert {l["id"] for l in tudo["logs"]} == {"a1", "a2"}

    async def test_o_trilho_de_auditoria_filtra_por_autor(self, mundo):
        import services.audit_trail_service as at

        mundo.audit_trail.docs.extend([
            {"id": "t1", "user_id": "u-cons-power", "action": "x", "created_at": "2026-10-01"},
            {"id": "t2", "user_id": "u-cons-domus", "action": "x", "created_at": "2026-10-02"},
        ])
        from unittest.mock import patch

        with patch.object(at, "db", mundo):
            local = await at.get_audit_trail(autores=["u-cons-power", "u-adm-power"])
            tudo = await at.get_audit_trail(autores=None)
            # um filtro `user_id` pedido por quem consulta NÃO alarga o âmbito
            cruzado = await at.get_audit_trail(user_id="u-cons-domus", autores=["u-cons-power"])
        assert {i["id"] for i in local["items"]} == {"t1"}
        assert {i["id"] for i in tudo["items"]} == {"t1", "t2"}
        assert cruzado["items"] == [], "pedir o user_id de outra rede furou o âmbito"

    async def test_as_estatisticas_de_auditoria_respeitam_os_autores(self, mundo):
        import services.audit_trail_service as at
        from datetime import datetime, timezone
        from unittest.mock import patch

        agora = datetime.now(timezone.utc).isoformat()
        mundo.audit_trail.docs.extend([
            {"id": "t1", "user_id": "u-cons-power", "created_at": agora, "ai_suggested": True, "source": "web", "user_name": "A"},
            {"id": "t2", "user_id": "u-cons-domus", "created_at": agora, "ai_suggested": True, "source": "web", "user_name": "B"},
        ])
        async def _cfg():
            return {"critical_fields": ["status"]}

        class _Cursor:
            def __init__(self, docs): self.docs = docs
            async def to_list(self, n): return self.docs

        async def _sem_agg(pipeline):  # pragma: no cover
            return []

        with patch.object(at, "db", mundo), patch.object(at, "get_audit_config", _cfg), \
             patch.object(mundo.audit_trail, "aggregate", lambda p: _Cursor([]), create=True):
            local = await at.get_audit_stats(autores=["u-cons-power"])
            tudo = await at.get_audit_stats(autores=None)
        assert local["total_today"] == 1 and tudo["total_today"] == 2


# ════════════════════════════════════════════════════════════════════
#  Finanças
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestFinancas:
    async def test_o_Admin_nao_consulta_comissoes_nem_pool_de_outra_empresa(self, mundo):
        import services.admin_users_scope as sc
        import services.finance_commissions as com
        import services.finance_pool as pool

        with _cadeia(mundo, sc, com, pool):
            for chamada in (
                lambda: com.run_get_finance_commissions(2026, "cmp-domus", ADMIN_POWER),
                lambda: com.run_export_commissions_csv(2026, "cmp-domus", ADMIN_POWER),
                lambda: pool.run_get_pool_distribution(10, 2026, "cmp-domus", ADMIN_POWER),
                lambda: pool.run_export_pool_distribution_csv(10, 2026, "cmp-domus", ADMIN_POWER),
            ):
                with pytest.raises(HTTPException) as erro:
                    await chamada()
                assert erro.value.status_code == 404

    async def test_a_configuracao_financeira_de_outra_empresa_nao_se_le_nem_edita_nem_apaga(self, mundo):
        import services.finance_configs as cfg
        from models.finance import FinanceConfigUpdate

        mundo.finance_configs.docs.append({
            "id": "fc-domus", "company_id": "cmp-domus", "fee_type": "percentage", "default_value": 5,
        })
        with _cadeia(mundo, cfg):
            for chamada in (
                lambda: cfg.run_get_finance_config_by_id("fc-domus", ADMIN_POWER),
                lambda: cfg.run_update_finance_config_by_id("fc-domus", FinanceConfigUpdate(default_value=99), ADMIN_POWER),
                lambda: cfg.run_delete_finance_config("fc-domus", ADMIN_POWER),
            ):
                with pytest.raises(HTTPException) as erro:
                    await chamada()
                assert erro.value.status_code == 404
        assert mundo.finance_configs.docs[0]["default_value"] == 5

    async def test_a_listagem_de_configuracoes_so_traz_as_da_rede(self, mundo):
        import services.finance_configs as cfg

        mundo.finance_configs.docs.extend([
            {"id": "fc-power", "company_id": "cmp-power"},
            {"id": "fc-domus", "company_id": "cmp-domus"},
        ])
        with _cadeia(mundo, cfg):
            local = await cfg.run_list_finance_configs(None, ADMIN_POWER)
            tudo = await cfg.run_list_finance_configs(None, MASTER)
        assert {c["id"] for c in local["configs"]} == {"fc-power"}
        assert {c["id"] for c in tudo["configs"]} == {"fc-power", "fc-domus"}

    async def test_ninguem_cria_uma_configuracao_para_outra_empresa(self, mundo):
        import services.finance_configs as cfg
        from models.finance import FinanceConfigCreate

        corpo = FinanceConfigCreate(company_id="cmp-domus", fee_type="percentage", default_value=5)
        with _cadeia(mundo, cfg):
            with pytest.raises(HTTPException) as erro:
                await cfg.run_create_finance_config(corpo, ADMIN_POWER)
        assert erro.value.status_code == 404
        assert not mundo.finance_configs.docs

    async def test_os_processos_do_painel_financeiro_vem_com_a_condicao_de_rede(self, mundo):
        import services.finance_helpers as fh

        for p in mundo.processes.docs:
            p["status"] = "concluido"
        from services.tenant_network import build_tenant_process_condition

        with _cadeia(mundo, fh):
            cond = await build_tenant_process_condition(CEO_DOMUS)
            local = await fh._get_processes(None, cond)
            tudo = await fh._get_processes(None, await build_tenant_process_condition(MASTER))
        assert {p["id"] for p in local} == {"p-domus", "p-domus-sem-rede"}
        assert {p["id"] for p in tudo} == {p["id"] for p in mundo.processes.docs}

    def test_a_configuracao_financeira_GLOBAL_e_so_master(self):
        import ast
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "routes" / "finance.py").read_text(encoding="utf-8")
        i = fonte.index('@router.put("/finance/config")')
        assert "require_roles([UserRole.MASTER])" in fonte[i:i + 400]
        assert ast.parse(fonte)


# ════════════════════════════════════════════════════════════════════
#  Empresas, configs de email por empresa, restauro, mapeamentos S3
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestEmpresasEOutros:
    async def test_a_lista_de_empresas_disponiveis_e_so_da_rede(self, mundo):
        import services.companies_crud_api_list as lst

        with _cadeia(mundo, lst):
            local = await lst.run_list_available_companies(actor=CEO_DOMUS)
            tudo = await lst.run_list_available_companies(actor=MASTER)
        assert {c["id"] for c in local} == {"cmp-domus"}
        assert {c["id"] for c in tudo} == {"cmp-power", "cmp-precision", "cmp-domus"}

    async def test_ler_uma_empresa_alheia_da_404(self, mundo):
        import services.admin_users_scope as sc
        import services.companies_crud_api_list as lst
        import services.user_management_scope as ums

        with _cadeia(mundo, lst, sc, ums):
            with pytest.raises(HTTPException) as erro:
                await lst.run_get_company("cmp-domus", actor=ADMIN_POWER)
        assert erro.value.status_code == 404

    async def test_as_configs_de_email_por_empresa_sao_da_rede(self, mundo):
        import services.admin_users_scope as sc
        import services.companies_api_list as lst
        import services.user_management_scope as ums

        mundo.company_email_configs.docs.extend([
            {"id": "e1", "company_name": "Power Real Estate", "imap_server": "x"},
            {"id": "e2", "company_name": "Domus", "imap_server": "y"},
        ])
        with _cadeia(mundo, lst, sc, ums):
            local = await lst.run_list_company_configs(actor=ADMIN_POWER)
            tudo = await lst.run_list_company_configs(actor=MASTER)
            with pytest.raises(HTTPException) as erro:
                await lst.run_get_company_config("Domus", actor=ADMIN_POWER)
        assert {c.company_name for c in local.configs} == {"Power Real Estate"}
        assert {c.company_name for c in tudo.configs} == {"Power Real Estate", "Domus"}
        assert erro.value.status_code == 404

    async def test_ninguem_reescreve_a_config_de_email_de_outra_empresa(self, mundo):
        import services.admin_users_scope as sc
        import services.companies_api_mutate as mut
        import services.user_management_scope as ums
        from models.company_email_config import CompanyEmailConfigCreate

        mundo.company_email_configs.docs.append({"id": "e2", "company_name": "Domus", "imap_user": "orig"})
        corpo = CompanyEmailConfigCreate(company_name="Domus", imap_server="evil", imap_user="evil")
        with _cadeia(mundo, mut, sc, ums):
            for chamada in (
                lambda: mut.run_update_company_config("Domus", corpo, actor=ADMIN_POWER),
                lambda: mut.run_delete_company_config("Domus", actor=ADMIN_POWER),
                lambda: mut.run_create_company_config(corpo, actor=ADMIN_POWER),
            ):
                with pytest.raises(HTTPException) as erro:
                    await chamada()
                assert erro.value.status_code == 404
        assert mundo.company_email_configs.docs[0]["imap_user"] == "orig"

    async def test_os_itens_eliminados_so_da_rede(self, mundo):
        import services.restore_api_list as rl

        for p in mundo.processes.docs:
            p["status"] = "eliminado"
            p["is_active"] = False
        with _cadeia(mundo, rl):
            local = await rl.run_list_deleted_items("processes", 50, ADMIN_POWER)
            tudo = await rl.run_list_deleted_items("processes", 50, MASTER)
        assert {i["id"] for i in local["items"]} == {"p-power", "p-legado"}
        assert {i["id"] for i in tudo["items"]} == {p["id"] for p in mundo.processes.docs}

    async def test_a_listagem_de_mapeamentos_s3_so_traz_a_rede(self, mundo):
        import services.admin_s3_process_mappings as m
        from unittest.mock import patch

        for p in mundo.processes.docs:
            p["s3_folder"] = f"Documentação Clientes/{p['id']}"
            p["created_at"] = "2026-01-01"
        class _S3:
            def is_configured(self):
                return False

        with _cadeia(mundo, m), patch("services.s3_storage.s3_service", _S3()):
            local = await m.run_get_process_s3_mappings(None, None, None, True, False, 1, 50, CEO_DOMUS)
            tudo = await m.run_get_process_s3_mappings(None, None, None, True, False, 1, 50, MASTER)
        assert {p["id"] for p in local["processes"]} == {"p-domus", "p-domus-sem-rede"}
        assert local["total"] == 2
        assert len(tudo["processes"]) == len(mundo.processes.docs)
