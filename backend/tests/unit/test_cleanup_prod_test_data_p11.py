"""PACOTE 11 — Unit tests do cleanup_prod_test_data (Eixo 4).

Cobre: pesquisa de 'teste' na colecção companies, cascade forte (leads
por client_id + role-mappings user_company_roles) e modos soft/hard.
"""
from unittest.mock import patch

import database as database_module
from scripts.cleanup_prod_test_data import (
    build_company_test_query,
    build_property_lead_test_query,
    build_user_company_roles_test_query,
    cleanup_prod_test_data,
)


def _seed_all(fake_db):
    fake_db.clients.docs.extend([
        {"id": "cl1", "nome": "Cliente Teste", "contacto": {"email": "teste@x.pt"}},
        {"id": "cl2", "nome": "Ana Silva", "contacto": {"email": "ana@x.pt"}},
    ])
    fake_db.processes.docs.extend([
        {"id": "p1", "client_id": "cl1", "client_name": "Cliente Teste",
         "client_email": "teste@x.pt", "process_number": "1", "status": "fase_bancaria"},
        {"id": "p2", "client_id": "cl2", "client_name": "Ana Silva",
         "client_email": "ana@x.pt", "process_number": "2", "status": "fase_documental"},
    ])
    fake_db.property_leads.docs.extend([
        {"id": "l1", "title": "T3 Lisboa", "client_id": "cl1"},   # órfã do cliente de teste
        {"id": "l2", "title": "T2 Porto", "client_id": "cl2"},
    ])
    fake_db.companies.docs.extend([
        {"id": "co1", "name": "Empresa Teste Lda", "email": "test@empresa.pt"},
        {"id": "co2", "name": "Precision Crédito", "email": "info@precision.pt"},
    ])
    fake_db.users.docs.extend([
        {"id": "u1", "email": "teste@x.pt"},       # user do cliente de teste
        {"id": "u2", "email": "ana@x.pt"},
    ])
    fake_db.user_company_roles.docs.extend([
        {"id": "ucr1", "user_id": "u1", "company_id": "co1"},   # ligação de teste
        {"id": "ucr2", "user_id": "u2", "company_id": "co2"},   # ligação real
    ])


class TestQueries:
    def test_company_test_query_apanha_nome(self):
        query = build_company_test_query()
        assert any("name" in c for c in query["$or"])

    def test_property_lead_query_cascata_por_client_id(self):
        query = build_property_lead_test_query(["cl1"])
        assert {"client_id": {"$in": ["cl1"]}} in query["$or"]

    def test_property_lead_query_sem_ids_nao_tem_cascata(self):
        query = build_property_lead_test_query([])
        assert not any("client_id" in c for c in query["$or"])

    def test_ucr_query_vazia_nao_casa_nada(self):
        query = build_user_company_roles_test_query([], [])
        assert query == {"id_placeholder_never_matches": True}

    def test_ucr_query_por_users_e_empresas(self):
        query = build_user_company_roles_test_query(["u1"], ["co1"])
        assert {"user_id": {"$in": ["u1"]}} in query["$or"]
        assert {"company_id": {"$in": ["co1"]}} in query["$or"]
        assert {"company_name": {"$in": ["co1"]}} in query["$or"]


class TestDryRun:
    async def test_reporta_empresas_e_role_mappings(self, fake_async_db, capsys):
        _seed_all(fake_async_db)
        with patch.object(database_module, "db", fake_async_db):
            total = await cleanup_prod_test_data(dry_run=True)

        out = capsys.readouterr().out
        assert "[EMPRESAS] Empresas de teste encontradas: 1" in out
        assert "[ROLE-MAPPINGS]" in out
        # leads: l1 (cascade client cl1) + nenhuma por título próprio
        assert "[LEADS] Leads de imóveis encontrados: 1" in out
        assert total >= 1


class TestHardMode:
    async def test_apaga_empresas_leads_ucrs_sem_orfaos(self, fake_async_db, monkeypatch):
        import scripts.cleanup_prod_test_data as script
        monkeypatch.setattr(script, "_confirm_password", lambda: True)
        _seed_all(fake_async_db)

        with patch.object(database_module, "db", fake_async_db):
            await cleanup_prod_test_data(dry_run=False, mode="hard")

        companies = [c for c in fake_async_db.companies.docs if c["id"] == "co1"]
        assert companies == []  # empresa de teste apagada
        assert any(c["id"] == "co2" for c in fake_async_db.companies.docs)  # real intacta

        # Lead do cliente de teste apagada (cascade forte — sem órfãos)
        assert all(l["id"] != "l1" for l in fake_async_db.property_leads.docs)
        assert any(l["id"] == "l2" for l in fake_async_db.property_leads.docs)

        # Role-mappings de teste apagados; o real mantém-se
        assert all(u["id"] != "ucr1" for u in fake_async_db.user_company_roles.docs)
        assert any(u["id"] == "ucr2" for u in fake_async_db.user_company_roles.docs)

        # Processo do cliente de teste apagado; o da Ana intacto
        assert all(p["id"] != "p1" for p in fake_async_db.processes.docs)
        assert any(p["id"] == "p2" for p in fake_async_db.processes.docs)


class TestSoftMode:
    async def test_empresas_soft_deleted_ucrs_hard(self, fake_async_db, monkeypatch):
        import scripts.cleanup_prod_test_data as script
        monkeypatch.setattr(script, "_confirm_password", lambda: True)
        _seed_all(fake_async_db)

        with patch.object(database_module, "db", fake_async_db):
            await cleanup_prod_test_data(dry_run=False, mode="soft")

        co1 = [c for c in fake_async_db.companies.docs if c["id"] == "co1"][0]
        assert co1["is_deleted"] is True
        assert co1["deleted_by"] == "cleanup_test_data_script"
        co2 = [c for c in fake_async_db.companies.docs if c["id"] == "co2"][0]
        assert co2.get("is_deleted") is not True

        # UCRs são ligações: hard-delete mesmo em modo soft
        assert all(u["id"] != "ucr1" for u in fake_async_db.user_company_roles.docs)

        # Leads do cliente de teste: soft-deleted (sem órfãos visíveis)
        l1 = [l for l in fake_async_db.property_leads.docs if l["id"] == "l1"][0]
        assert l1["is_deleted"] is True
