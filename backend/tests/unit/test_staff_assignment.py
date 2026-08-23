"""Pacote DT / FL — filtro global de staff para atribuições."""
from services.staff_assignment import (
    ASSIGNMENT_ALLOWED_ROLES,
    ASSIGNMENT_EXCLUDED_PRIMARY_ROLES,
    apply_assignment_staff_filter,
    assignment_staff_mongo_filter,
    filter_assignment_staff,
    is_assignment_eligible_user,
)


def test_allowed_roles_exclude_admin_include_indexacao():
    assert "admin" not in ASSIGNMENT_ALLOWED_ROLES
    assert "cliente" not in ASSIGNMENT_ALLOWED_ROLES
    assert "parceiro" not in ASSIGNMENT_ALLOWED_ROLES
    for role in ("consultor", "intermediario", "diretor", "ceo", "indexacao", "index"):
        assert role in ASSIGNMENT_ALLOWED_ROLES
    assert "admin" in ASSIGNMENT_EXCLUDED_PRIMARY_ROLES
    assert "indexacao" not in ASSIGNMENT_EXCLUDED_PRIMARY_ROLES
    assert "index" not in ASSIGNMENT_EXCLUDED_PRIMARY_ROLES


def test_mongo_filter_nins_admin_and_requires_allowed_role():
    query = assignment_staff_mongo_filter()
    assert "$and" in query
    nin = query["$and"][0]["role"]["$nin"]
    assert "admin" in nin
    assert "indexacao" not in nin
    or_clause = query["$and"][1]["$or"]
    assert {"role": {"$in": list(ASSIGNMENT_ALLOWED_ROLES)}} in or_clause or any(
        "role" in part for part in or_clause
    )


def test_apply_filter_noop_when_disabled():
    base = {"is_active": True}
    assert apply_assignment_staff_filter(base, False) == base


def test_apply_filter_wraps_existing_query():
    wrapped = apply_assignment_staff_filter({"is_active": True}, True)
    assert wrapped["$and"][0] == {"is_active": True}


def test_is_assignment_eligible_user_matrix():
    assert is_assignment_eligible_user({"role": "consultor"}) is True
    assert is_assignment_eligible_user({"role": "intermediario"}) is True
    assert is_assignment_eligible_user({"role": "diretor"}) is True
    assert is_assignment_eligible_user({"role": "ceo"}) is True
    assert is_assignment_eligible_user({"role": "mediador"}) is True
    assert is_assignment_eligible_user({"role": "indexacao"}) is True
    assert is_assignment_eligible_user({"role": "index"}) is True
    assert is_assignment_eligible_user({"role": "admin"}) is False
    assert is_assignment_eligible_user({"role": "administrativo"}) is False
    assert is_assignment_eligible_user({"role": "cliente"}) is False
    # Cargo actual admin, mesmo com consultor adicional, fica de fora.
    assert is_assignment_eligible_user({
        "role": "admin",
        "additional_roles": ["consultor"],
    }) is False
    # Consultor com indexação adicional continua elegível.
    assert is_assignment_eligible_user({
        "role": "consultor",
        "additional_roles": ["indexacao"],
    }) is True


def test_filter_assignment_staff_keeps_indexacao_drops_admin():
    users = [
        {"id": "1", "role": "admin", "name": "Admin"},
        {"id": "2", "role": "indexacao", "name": "Index"},
        {"id": "3", "role": "consultor", "name": "Ana"},
        {"id": "4", "role": "ceo", "name": "Pedro"},
    ]
    filtered = filter_assignment_staff(users)
    assert [u["id"] for u in filtered] == ["2", "3", "4"]
