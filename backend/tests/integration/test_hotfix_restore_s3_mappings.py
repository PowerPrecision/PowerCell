"""
Testes de integração — `backend/scripts/hotfix_restore_s3_mappings.py`

Executa o script de recuperação contra uma base de dados MongoDB real
(local, de teste) para provar, ponta-a-ponta, que:

1. Apenas processos/clientes com `s3_folder` em falta são tocados.
2. A escrita usa ESTRITAMENTE `$set` nas chaves `s3_folder`,
   `s3_mapping_restored_at` e `s3_mapping_restored_by` — nenhum outro
   campo do documento (ex.: `financial_data`, `contacto`) é alterado.
3. O script é idempotente: correr uma segunda vez não volta a escrever
   nos documentos já corrigidos.
4. `--dry-run` não escreve nada na base de dados.

O serviço S3 real (boto3/AWS) é substituído por um stub em memória para
não depender de credenciais/rede externas.
"""
import os
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from scripts.hotfix_restore_s3_mappings import restore_processes, restore_clients

TEST_DB_NAME = "test_hotfix_s3_mappings_db"


class FakeS3Service:
    """Substitui o s3_service real: simula pastas já existentes e criação."""

    def __init__(self, existing_folders=None):
        # Conjunto de pastas "já existentes" no S3 fictício.
        self.existing_folders = set(existing_folders or [])
        self.created_folders = []

    def is_configured(self):
        return True

    def ensure_client_folder_mapping(self, client_id, client_name, second_client_name=None, existing_s3_folder=None):
        if existing_s3_folder and existing_s3_folder in self.existing_folders:
            return {"success": True, "s3_folder": existing_s3_folder, "created": False, "reused_existing": True}

        safe_name = client_name.strip().replace(" ", "_")
        candidate = f"Documentação Clientes/{safe_name}"
        if candidate in self.existing_folders:
            return {"success": True, "s3_folder": candidate, "created": False, "reused_existing": True}

        self.existing_folders.add(candidate)
        self.created_folders.append(candidate)
        return {"success": True, "s3_folder": candidate, "created": True, "reused_existing": False}


@pytest_asyncio.fixture
async def db():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    mongo_client = AsyncIOMotorClient(mongo_url)
    database = mongo_client[TEST_DB_NAME]

    await database.processes.delete_many({})
    await database.clients.delete_many({})

    yield database

    await database.processes.delete_many({})
    await database.clients.delete_many({})
    mongo_client.close()


def _proc_id():
    return f"proc-{uuid.uuid4().hex[:8]}"


def _client_id():
    return f"client-{uuid.uuid4().hex[:8]}"


class TestRestoreProcesses:
    @pytest.mark.asyncio
    async def test_only_missing_mapping_is_restored_other_fields_untouched(self, db):
        missing_id = _proc_id()
        already_mapped_id = _proc_id()

        await db.processes.insert_one({
            "id": missing_id,
            "client_name": "João Silva",
            "s3_folder": None,
            "is_deleted": False,
            "financial_data": {"salario_bruto": 2000},
            "process_ids_untouched_marker": "keep-me",
        })
        await db.processes.insert_one({
            "id": already_mapped_id,
            "client_name": "Maria Santos",
            "s3_folder": "Documentação Clientes/Maria_Santos",
            "is_deleted": False,
            "financial_data": {"salario_bruto": 3000},
        })

        fake_s3 = FakeS3Service()
        stats = await restore_processes(db, fake_s3, dry_run=False)

        assert stats["total"] == 1  # apenas o que tinha mapeamento em falta
        assert stats["restored"] == 1

        fixed = await db.processes.find_one({"id": missing_id})
        assert fixed["s3_folder"] == "Documentação Clientes/João_Silva"
        assert "s3_mapping_restored_at" in fixed
        assert fixed["s3_mapping_restored_by"] == "hotfix_restore_s3_mappings"
        # Campos não relacionados permanecem intactos.
        assert fixed["financial_data"] == {"salario_bruto": 2000}
        assert fixed["process_ids_untouched_marker"] == "keep-me"

        # Documento já mapeado não foi tocado.
        untouched = await db.processes.find_one({"id": already_mapped_id})
        assert untouched["s3_folder"] == "Documentação Clientes/Maria_Santos"
        assert "s3_mapping_restored_at" not in untouched
        assert untouched["financial_data"] == {"salario_bruto": 3000}

    @pytest.mark.asyncio
    async def test_dry_run_never_writes_to_database(self, db):
        proc_id = _proc_id()
        await db.processes.insert_one({
            "id": proc_id,
            "client_name": "Carlos Pereira",
            "s3_folder": "",
            "is_deleted": False,
        })

        fake_s3 = FakeS3Service()
        stats = await restore_processes(db, fake_s3, dry_run=True)

        assert stats["restored"] == 1
        unchanged = await db.processes.find_one({"id": proc_id})
        assert unchanged["s3_folder"] == ""
        assert "s3_mapping_restored_at" not in unchanged

    @pytest.mark.asyncio
    async def test_script_is_idempotent_on_second_run(self, db):
        proc_id = _proc_id()
        await db.processes.insert_one({
            "id": proc_id,
            "client_name": "Ana Costa",
            "s3_folder": "undefined",
            "is_deleted": False,
        })

        fake_s3 = FakeS3Service()
        first_stats = await restore_processes(db, fake_s3, dry_run=False)
        assert first_stats["restored"] == 1

        after_first = await db.processes.find_one({"id": proc_id})
        first_timestamp = after_first["s3_mapping_restored_at"]

        # Segunda execução: já não deve encontrar nada em falta.
        second_stats = await restore_processes(db, fake_s3, dry_run=False)
        assert second_stats["total"] == 0
        assert second_stats["restored"] == 0

        after_second = await db.processes.find_one({"id": proc_id})
        assert after_second["s3_mapping_restored_at"] == first_timestamp

    @pytest.mark.asyncio
    async def test_deleted_processes_are_skipped(self, db):
        proc_id = _proc_id()
        await db.processes.insert_one({
            "id": proc_id,
            "client_name": "Processo Eliminado",
            "s3_folder": None,
            "is_deleted": True,
        })

        fake_s3 = FakeS3Service()
        stats = await restore_processes(db, fake_s3, dry_run=False)
        assert stats["total"] == 0

        doc = await db.processes.find_one({"id": proc_id})
        assert doc["s3_folder"] is None

    @pytest.mark.asyncio
    async def test_process_without_client_name_is_skipped_safely(self, db):
        proc_id = _proc_id()
        await db.processes.insert_one({
            "id": proc_id,
            "client_name": "",
            "s3_folder": None,
            "is_deleted": False,
        })

        fake_s3 = FakeS3Service()
        stats = await restore_processes(db, fake_s3, dry_run=False)
        assert stats["skipped_no_name"] == 1
        assert stats["restored"] == 0


class TestRestoreClients:
    @pytest.mark.asyncio
    async def test_restores_client_without_process(self, db):
        client_id = _client_id()
        await db.clients.insert_one({
            "id": client_id,
            "nome": "Rui Almeida",
            "s3_folder": None,
            "is_active": True,
            "contacto": {"email": "rui@example.com"},
        })

        fake_s3 = FakeS3Service()
        stats = await restore_clients(db, fake_s3, dry_run=False)

        assert stats["restored"] == 1
        fixed = await db.clients.find_one({"id": client_id})
        assert fixed["s3_folder"] == "Documentação Clientes/Rui_Almeida"
        # Dados de contacto não relacionados permanecem intactos.
        assert fixed["contacto"] == {"email": "rui@example.com"}

    @pytest.mark.asyncio
    async def test_inactive_clients_are_skipped(self, db):
        client_id = _client_id()
        await db.clients.insert_one({
            "id": client_id,
            "nome": "Cliente Inativo",
            "s3_folder": None,
            "is_active": False,
        })

        fake_s3 = FakeS3Service()
        stats = await restore_clients(db, fake_s3, dry_run=False)
        assert stats["total"] == 0
