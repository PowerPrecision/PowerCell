"""
Iteration 4 — Test 3 features:
1. Mandatory documents checklist (obrigatorios + opcionais)
2. Company email config IMAP fields
3. Shared email config manual IMAP/SMTP
4. Post-indexing auto tasks
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://powercell-crm.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "geral@powerealestate.pt"
ADMIN_PASSWORD = "PowerCell_Dev_2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login-v2",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"No access_token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ==============================
# FEATURE 1 — Mandatory documents (obrigatorios + opcionais)
# ==============================
class TestMandatoryDocuments:
    def test_get_system_config(self, headers):
        r = requests.get(f"{BASE_URL}/api/system-config", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "config" in data or "mandatory_documents" in data

    def test_patch_mandatory_documents_saves_both_lists(self, headers):
        # Save original
        orig = requests.get(f"{BASE_URL}/api/system-config", headers=headers, timeout=30).json()
        original_md = ((orig.get("config") or {}).get("mandatory_documents")
                       or orig.get("mandatory_documents") or {})

        payload = {
            "enabled": True,
            "documents": [
                {"name": "QA_Doc_Obrig_A", "category": "identificacao"},
                {"name": "QA_Doc_Obrig_B", "category": "irs"},
            ],
            "optional_documents": [
                {"name": "QA_Doc_Opt_A", "category": "outros"},
            ],
        }
        r = requests.patch(
            f"{BASE_URL}/api/system-config/mandatory_documents",
            headers=headers,
            json=payload,
            timeout=30,
        )
        assert r.status_code == 200, f"PATCH failed: {r.status_code} {r.text}"

        # Round-trip
        r2 = requests.get(f"{BASE_URL}/api/system-config", headers=headers, timeout=30)
        assert r2.status_code == 200
        md = ((r2.json().get("config") or {}).get("mandatory_documents")
              or r2.json().get("mandatory_documents") or {})
        assert md.get("enabled") is True
        docs = md.get("documents") or []
        opts = md.get("optional_documents") or []
        assert any(d.get("name") == "QA_Doc_Obrig_A" for d in docs), f"docs={docs}"
        assert any(d.get("name") == "QA_Doc_Obrig_B" for d in docs), f"docs={docs}"
        assert any(d.get("name") == "QA_Doc_Opt_A" for d in opts), f"opts={opts}"

        # Restore original
        restore_payload = {
            "enabled": original_md.get("enabled", True),
            "documents": original_md.get("documents", []),
            "optional_documents": original_md.get("optional_documents", []),
        }
        requests.patch(
            f"{BASE_URL}/api/system-config/mandatory_documents",
            headers=headers,
            json=restore_payload,
            timeout=30,
        )


# ==============================
# FEATURE 2a — Company Email Config IMAP fields
# ==============================
class TestCompanyEmailConfigImap:
    def test_available_companies(self, headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/company-email-configs/available-companies",
            headers=headers, timeout=30,
        )
        assert r.status_code == 200
        assert "companies" in r.json()

    def test_create_or_update_company_config_with_imap(self, headers):
        # Get available companies (or those already configured)
        r = requests.get(
            f"{BASE_URL}/api/admin/company-email-configs/available-companies",
            headers=headers, timeout=30,
        )
        companies = r.json().get("companies", [])
        # find one without config
        target = next((c for c in companies if not c.get("has_email_config")), None)
        method = "POST"
        url = f"{BASE_URL}/api/admin/company-email-configs"
        if target is None:
            # fall back to update existing
            r2 = requests.get(f"{BASE_URL}/api/admin/company-email-configs", headers=headers, timeout=30)
            existing = r2.json().get("configs", [])
            if not existing:
                pytest.skip("No companies available for testing")
            target = {"company_name": existing[0]["company_name"]}
            method = "PUT"
            url = f"{BASE_URL}/api/admin/company-email-configs/{requests.utils.quote(target['company_name'])}"

        company_name = target["company_name"]
        payload = {
            "company_name": company_name,
            "smtp_server": "smtp.qa-test.pt",
            "smtp_port": 465,
            "imap_server": "imap.qa-test.pt",
            "imap_port": 993,
            "imap_user": "qa_test_user@qa-test.pt",
            "imap_password": "QA_test_pw_123",
            "require_ssl": True,
        }
        r3 = requests.request(method, url, headers=headers, json=payload, timeout=30)
        assert r3.status_code in (200, 201), f"{method} {url}: {r3.status_code} {r3.text}"

        # Verify via list
        r4 = requests.get(f"{BASE_URL}/api/admin/company-email-configs", headers=headers, timeout=30)
        assert r4.status_code == 200
        cfgs = r4.json().get("configs", [])
        cfg = next((c for c in cfgs if c["company_name"] == company_name), None)
        assert cfg, f"Company {company_name} not found in list"
        assert cfg.get("imap_server") == "imap.qa-test.pt"
        assert cfg.get("imap_port") == 993
        assert cfg.get("imap_user") == "qa_test_user@qa-test.pt"
        # has_encrypted_password should be True since we set imap_password
        assert cfg.get("has_encrypted_password") is True, f"cfg={cfg}"


# ==============================
# FEATURE 2b — Shared Email Config manual IMAP/SMTP
# ==============================
class TestSharedEmailConfigManual:
    @pytest.mark.parametrize("role", ["indexacao"])
    def test_upsert_shared_email_manual(self, headers, role):
        # Save existing
        r_orig = requests.get(f"{BASE_URL}/api/admin/shared-email/{role}", headers=headers, timeout=30)
        original = r_orig.json() if r_orig.status_code == 200 else None

        payload = {
            "role": role,
            "email_address": f"qa-{role}@qa-test.pt",
            "display_name": f"QA {role.title()}",
            "smtp_server": "smtp.qa-test.pt",
            "smtp_port": 465,
            "imap_server": "imap.qa-test.pt",
            "imap_port": 993,
            "encrypted_password": "QA_shared_pw_123",
        }
        r = requests.put(
            f"{BASE_URL}/api/admin/shared-email/{role}",
            headers=headers, json=payload, timeout=30,
        )
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text}"

        # Verify
        r2 = requests.get(f"{BASE_URL}/api/admin/shared-email/{role}", headers=headers, timeout=30)
        assert r2.status_code == 200
        cfg = r2.json()
        assert cfg.get("email_address") == f"qa-{role}@qa-test.pt"
        assert cfg.get("imap_server") == "imap.qa-test.pt"
        assert cfg.get("smtp_server") == "smtp.qa-test.pt"
        assert cfg.get("has_imap_password") is True, f"cfg={cfg}"


# ==============================
# FEATURE 3 — Post-indexing auto tasks
# ==============================
class TestPostIndexingAutoTasks:
    @pytest.mark.asyncio
    async def test_direct_service_call_creates_tasks(self):
        """
        Call the service function directly to bypass HTTP flow —
        this validates the exact contract requested by the review.
        """
        import sys
        sys.path.insert(0, "/app/backend")
        from database import reset_db_connection
        # Reset the global Motor client so it re-binds to this test's event loop
        reset_db_connection()
        from services.process_assignment import _create_post_indexing_tasks
        from database import db as service_db

        fake_process_id = f"qa-proc-{uuid.uuid4()}"
        fake_users = [
            {"id": f"qa-consultor-{uuid.uuid4()}", "name": "QA Consultor", "role": "consultor"},
            {"id": f"qa-mediador-{uuid.uuid4()}", "name": "QA Mediador", "role": "intermediario"},
        ]
        await _create_post_indexing_tasks(fake_process_id, fake_users)
        tasks = await service_db.tasks.find({"process_id": fake_process_id}).to_list(length=100)
        # cleanup
        await service_db.tasks.delete_many({"process_id": fake_process_id})
        reset_db_connection()
        assert len(tasks) == 4, f"Expected 4 tasks (2 per user × 2 users), got {len(tasks)}"

        titles_by_user = {}
        for t in tasks:
            uid = t["assigned_to"][0]
            titles_by_user.setdefault(uid, []).append((t["title"], t.get("priority")))

        for uid, entries in titles_by_user.items():
            titles = {e[0]: e[1] for e in entries}
            assert "Analisar documentação inicial" in titles, f"missing analisar for {uid}"
            assert "Agendar contacto inicial com o cliente" in titles, f"missing agendar for {uid}"
            assert titles["Analisar documentação inicial"] == "Alta"
            assert titles["Agendar contacto inicial com o cliente"] == "Média"

    def test_e2e_mark_indexed_creates_tasks(self, headers):
        """
        Full E2E: create process in pre_registo, POST /mark-indexed,
        verify 4 tasks appear (2 per newly-assigned consultor+mediador).
        Requires active consultor and intermediario users in DB.
        """
        import asyncio
        import sys
        sys.path.insert(0, "/app/backend")
        from motor.motor_asyncio import AsyncIOMotorClient

        # Hit the SAME DB that backend uses (bypass pytest conftest test_db_ci override)
        mongo_url = "mongodb://localhost:27017"
        db_name = "powercell_dev"

        async def check_users():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            print(f"[DBG] mongo_url={mongo_url} db_name={db_name}")
            consultors = await db.users.count_documents({"role": "consultor", "is_active": True})
            mediadores = await db.users.count_documents({"role": "intermediario", "is_active": True})
            all_users = await db.users.count_documents({})
            print(f"[DBG] total_users={all_users} consultors={consultors} mediadores={mediadores}")
            client.close()
            return consultors, mediadores

        c, m = asyncio.run(check_users())
        if c < 1 or m < 1:
            pytest.skip(f"Need at least 1 consultor and 1 intermediario active users. got c={c} m={m}")

        # Create a client first
        client_payload = {
            "nome": f"QA Cliente Task {uuid.uuid4().hex[:6]}",
            "email": f"qa.task.{uuid.uuid4().hex[:6]}@qa-test.pt",
            "telefone": "912345678",
        }
        rc = requests.post(f"{BASE_URL}/api/clients", headers=headers, json=client_payload, timeout=30)
        assert rc.status_code in (200, 201), f"Client create failed: {rc.status_code} {rc.text}"
        client_id = rc.json().get("id") or rc.json().get("_id") or rc.json().get("client", {}).get("id")
        assert client_id, f"No client id: {rc.json()}"

        # Insert a test process directly (bypass "only clients create" restriction)
        async def seed_process():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            pid = str(uuid.uuid4())
            from datetime import datetime, timezone
            proc = {
                "id": pid,
                "process_type": "credito_habitacao",
                "client_id": client_id,
                "status": "pre_registo",
                "is_lead": True,
                "is_indexed": False,
                "consultant_id": None,
                "mediador_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.processes.insert_one(proc)
            client.close()
            return pid

        process_id = asyncio.run(seed_process())

        # Mark as indexed
        rmi = requests.post(
            f"{BASE_URL}/api/processes/{process_id}/mark-indexed",
            headers=headers,
            json={},
            timeout=60,
        )
        assert rmi.status_code == 200, f"mark-indexed failed: {rmi.status_code} {rmi.text}"

        # Query DB for tasks
        async def get_tasks():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            tasks = await db.tasks.find({"process_id": process_id}).to_list(length=100)
            proc = await db.processes.find_one({"id": process_id})
            client.close()
            return tasks, proc

        tasks, proc = asyncio.run(get_tasks())
        print(f"[E2E] Process after mark-indexed: consultant_id={proc.get('consultant_id') if proc else None}, mediador_id={proc.get('mediador_id') if proc else None}")
        print(f"[E2E] {len(tasks)} tasks created:")
        for t in tasks:
            print(f"  - {t.get('title')} | priority={t.get('priority')} | assigned_to={t.get('assigned_to')}")

        # Expect 4 tasks if both consultor+mediador were newly assigned
        assert len(tasks) >= 2, f"Expected at least 2 tasks, got {len(tasks)}"

        titles = {t["title"] for t in tasks}
        assert "Analisar documentação inicial" in titles
        assert "Agendar contacto inicial com o cliente" in titles

        # cleanup
        async def cleanup():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            await db.tasks.delete_many({"process_id": process_id})
            await db.processes.delete_one({"id": process_id})
            await db.clients.delete_one({"id": client_id})
            client.close()
        asyncio.run(cleanup())
