"""PACOTE FK — testes unitários dos filtros da entidade Cliente."""
from services.client_list_filters import (
    build_client_fonte_condition,
    build_client_tipo_condition,
    build_client_status_condition,
    build_client_entity_query,
    client_doc_to_list_item,
)


class TestFonteCondition:
    def test_blank(self):
        assert build_client_fonte_condition(None) is None
        assert build_client_fonte_condition("all") is None
        assert build_client_fonte_condition("") is None

    def test_case_insensitive_regex(self):
        cond = build_client_fonte_condition("Website")
        assert cond["fonte"]["$options"] == "i"
        assert cond["fonte"]["$regex"] == "^Website$"


class TestTipoCondition:
    def test_blank(self):
        assert build_client_tipo_condition(None) is None
        assert build_client_tipo_condition("all") is None

    def test_particular_uses_nor(self):
        cond = build_client_tipo_condition("particular")
        assert "$nor" in cond
        assert any("titular2_data.nif" in c for c in cond["$nor"])

    def test_dois_titulares_uses_or(self):
        cond = build_client_tipo_condition("dois_titulares")
        assert "$or" in cond
        assert any("titular2_data.name" in c for c in cond["$or"])

    def test_empresa(self):
        cond = build_client_tipo_condition("empresa")
        assert "$or" in cond
        blob = str(cond)
        assert "tipo_cliente" in blob
        assert "empresa" in blob


class TestStatusCondition:
    def test_blank(self):
        assert build_client_status_condition(None) is None
        assert build_client_status_condition("all") is None

    def test_active(self):
        cond = build_client_status_condition("active")
        assert cond["is_deleted"] == {"$ne": True}
        assert cond["is_active"] == {"$ne": False}

    def test_inactive(self):
        cond = build_client_status_condition("inativo")
        assert cond["is_active"] is False
        assert cond["is_deleted"] == {"$ne": True}

    def test_deleted(self):
        assert build_client_status_condition("eliminado") == {"is_deleted": True}


class TestEntityQuery:
    def test_none_when_empty(self):
        assert build_client_entity_query() is None
        assert build_client_entity_query(fonte="all", tipo="", status=None) is None

    def test_single_filter(self):
        q = build_client_entity_query(fonte="Manual")
        assert "fonte" in q

    def test_combined_and(self):
        q = build_client_entity_query(fonte="Website", status="active")
        assert "$and" in q
        assert len(q["$and"]) == 2


class TestClientDocToListItem:
    def test_particular_without_titular2(self):
        item = client_doc_to_list_item({
            "id": "c1",
            "nome": "Ana",
            "fonte": "Website",
        })
        assert item["tipo_cliente"] == "particular"
        assert item["fonte"] == "Website"
        assert item["process_ids"] == []

    def test_dois_titulares(self):
        item = client_doc_to_list_item({
            "id": "c2",
            "nome": "Bruno",
            "titular2_data": {"name": "Carla", "nif": "123"},
        })
        assert item["tipo_cliente"] == "dois_titulares"
