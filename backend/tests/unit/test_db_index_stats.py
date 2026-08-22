"""Pacote FJ — observabilidade de índices inclui coleções em falta."""
import pytest

from services.db_indexes import get_index_stats

REQUIRED_INDEX_STAT_COLLECTIONS = (
    "processes",
    "clients",
    "users",
    "system_error_logs",
    "properties",
    "tasks",
    "chat_messages",
    "chat_groups",
    "history",
    "compliance_audit_logs",
    "emails",
    "user_company_roles",
    "notifications",
    "companies",
)


class _FakeCollection:
    def __init__(self, name):
        self.name = name

    async def index_information(self):
        return {"_id_": {}, f"idx_{self.name}": {}}


class _FakeDB:
    def __getattr__(self, name):
        return _FakeCollection(name)


@pytest.mark.asyncio
async def test_get_index_stats_includes_fj_collections():
    stats = await get_index_stats(_FakeDB())
    for collection_name in REQUIRED_INDEX_STAT_COLLECTIONS:
        assert collection_name in stats, f"missing {collection_name}"
        assert stats[collection_name]["count"] >= 1
        assert "_id_" in stats[collection_name]["indexes"]


@pytest.mark.asyncio
async def test_get_index_stats_records_collection_errors():
    class BrokenCollection:
        async def index_information(self):
            raise RuntimeError("boom")

    class BrokenDB:
        def __getattr__(self, name):
            return BrokenCollection()

    stats = await get_index_stats(BrokenDB())
    assert "emails" in stats
    assert "error" in stats["emails"]
