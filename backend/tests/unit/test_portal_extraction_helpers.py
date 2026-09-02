"""Unit tests for portal route thinning helpers (batch 1)."""
from services.portal_assigned_users import get_all_assigned_user_ids
from services.portal_doc_categories import (
    DOCUMENT_CATEGORY_MAP,
    PORTAL_HIDDEN_CATEGORIES,
)
from services.portal_profile import (
    ClientProfileUpdate,
    _decrypt_if_needed,
    _get_client_id_from_token,
)


def test_get_all_assigned_user_ids_dedupes():
    process = {
        "assigned_consultor_id": "c1",
        "assigned_consultor_ids": ["c1", "c2"],
        "assigned_mediador_id": "m1",
        "assigned_mediador_ids": ["m1"],
        "assigned_indexacao_id": "i1",
        "assigned_parceiro_id": "p1",
    }
    ids = get_all_assigned_user_ids(process)
    assert set(ids) == {"c1", "c2", "m1", "i1", "p1"}


def test_portal_doc_categories_include_financeiros():
    assert "Financeiros" in DOCUMENT_CATEGORY_MAP
    assert "Index" in PORTAL_HIDDEN_CATEGORIES


def test_decrypt_if_needed_passthrough():
    assert _decrypt_if_needed(None) is None
    assert _decrypt_if_needed("plain") == "plain"
    assert _decrypt_if_needed(123) == 123


def test_get_client_id_from_token():
    assert _get_client_id_from_token({"client_id": "x"}) == "x"
    assert _get_client_id_from_token({"process": {"client_id": "y"}}) == "y"
    assert _get_client_id_from_token({}) is None


def test_client_profile_update_model():
    m = ClientProfileUpdate(contacto={"email": "a@b.c"}, dados_pessoais={"profissao": "Dev"})
    assert m.contacto["email"] == "a@b.c"


def test_portal_modules_export_status_and_onboarding():
    from services import portal_status_helpers as sh
    from services import portal_onboarding_advance as oa

    assert callable(sh._get_rgpd_status)
    assert callable(oa._trigger_onboarding_check)
    assert callable(oa._auto_advance_from_pre_registo)


def test_portal_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "portal.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 20
    assert len(text.splitlines()) < 400


def test_portal_domain_modules_export_run_entrypoints():
    from services import portal_auth, portal_status, portal_upload_ops, portal_gov_fetch

    assert callable(portal_auth.run_portal_login)
    assert callable(portal_status.run_get_portal_status)
    assert callable(portal_upload_ops.run_confirm_portal_upload)
    assert callable(portal_gov_fetch.run_fetch_financas_documents)
