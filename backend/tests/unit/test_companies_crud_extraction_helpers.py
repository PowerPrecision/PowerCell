"""Unit tests for companies_crud route thinning helpers (companies_crud_api_*)."""
import pytest


def test_companies_crud_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "companies_crud_api_helpers.py",
        "companies_crud_api_list.py",
        "companies_crud_api_logo.py",
        "companies_crud_api_mutate.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("companies_crud_api_*.py"))
    assert files == expected


def test_companies_crud_api_export_run_entrypoints():
    from services import (
        companies_crud_api_helpers,
        companies_crud_api_list,
        companies_crud_api_mutate,
        companies_crud_api_logo,
    )

    assert callable(companies_crud_api_helpers.resolve_logo_url)
    assert callable(companies_crud_api_list.run_list_companies)
    assert callable(companies_crud_api_list.run_list_available_companies)
    assert callable(companies_crud_api_list.run_get_company)
    assert callable(companies_crud_api_mutate.run_create_company)
    assert callable(companies_crud_api_mutate.run_update_company)
    assert callable(companies_crud_api_mutate.run_delete_company)
    assert callable(companies_crud_api_logo.run_upload_company_logo)


def test_resolve_logo_url_passthrough():
    from services.companies_crud_api_helpers import resolve_logo_url

    assert resolve_logo_url(None) is None
    assert resolve_logo_url("") is None
    assert resolve_logo_url("https://cdn.example/logo.png") == (
        "https://cdn.example/logo.png"
    )
    assert resolve_logo_url("http://cdn.example/logo.png") == (
        "http://cdn.example/logo.png"
    )


def test_companies_crud_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = (
        Path(__file__).resolve().parents[2] / "routes" / "companies_crud.py"
    )
    text = routes_path.read_text()
    assert text.count("return await run_") >= 7
    assert len(text.splitlines()) < 120
    assert "s3_service.s3_client.put_object" not in text
    # Static /available before /{company_id}
    available_pos = text.index('/available"')
    id_pos = text.index('/{company_id}"')
    assert available_pos < id_pos


def test_company_models_include_is_active():
    from models.company import CompanyCreate, CompanyUpdate, CompanyResponse

    created = CompanyCreate(name="Precision Crédito")
    assert created.is_active is True
    updated = CompanyUpdate(is_active=False)
    assert updated.is_active is False
    response = CompanyResponse(id="1", name="Precision Crédito")
    assert response.is_active is True


def test_company_models_include_imap_fields():
    """PACOTE — Webmail: schemas de Company devem suportar IMAP, não só SMTP."""
    from models.company import CompanyCreate, CompanyUpdate, CompanyResponse

    created = CompanyCreate(
        name="Precision Crédito",
        imap_host="imap.exemplo.pt",
        imap_port=993,
        imap_email="geral@exemplo.pt",
        imap_password="segredo",
    )
    assert created.imap_host == "imap.exemplo.pt"
    assert created.imap_port == 993

    updated = CompanyUpdate(imap_host="imap2.exemplo.pt", imap_port=143)
    assert updated.imap_host == "imap2.exemplo.pt"
    assert updated.imap_port == 143

    response = CompanyResponse(id="1", name="Precision Crédito", imap_host="imap.exemplo.pt", imap_port=993)
    assert response.imap_host == "imap.exemplo.pt"
    assert response.imap_port == 993


def test_create_company_persists_imap_fields():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "companies_crud_api_mutate.py"
    ).read_text()
    assert '"imap_host": data.imap_host' in text
    assert '"imap_port": data.imap_port' in text
    assert '"imap_email": data.imap_email' in text
    assert '"imap_password": data.imap_password' in text


def test_list_companies_escapes_regex_search():
    """Pacote FF — pesquisa de empresas não injeta $regex cru."""
    import asyncio
    from unittest.mock import MagicMock, patch

    from services import companies_crud_api_list as listing

    class _Cursor:
        def sort(self, *args, **kwargs):
            return self

        async def to_list(self, n):
            return []

    mock_db = MagicMock()
    mock_db.companies.find = MagicMock(return_value=_Cursor())

    with patch.object(listing, "db", mock_db):
        asyncio.run(listing.run_list_companies(search="Power.*(+"))

    query = mock_db.companies.find.call_args[0][0]
    name_regex = query["$or"][0]["name"]["$regex"]
    nif_regex = query["$or"][1]["nif"]["$regex"]
    assert name_regex == r"Power\.\*\(\+"
    assert nif_regex == name_regex
    assert name_regex != "Power.*(+"


def test_list_companies_search_imports_escape_regex():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "companies_crud_api_list.py"
    ).read_text()
    assert "from utils.input_sanitization import escape_regex" in text
    assert "escape_regex(search)" in text


def test_create_company_strips_mongo_objectid():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "companies_crud_api_mutate.py"
    ).read_text()
    assert 'doc.pop("_id"' in text
    assert 'updated.pop("_id"' in text


def test_company_create_validates_nif_checksum():
    from pydantic import ValidationError
    from models.company import CompanyCreate, CompanyUpdate

    created = CompanyCreate(name="Precision Crédito")
    assert created.nif is None

    ok = CompanyCreate(name="Precision Crédito", nif="501442600")
    assert ok.nif == "501442600"

    spaced = CompanyCreate(name="X", nif="501 442 600")
    assert spaced.nif == "501442600"

    with pytest.raises(ValidationError):
        CompanyCreate(name="X", nif="123456780")

    with pytest.raises(ValidationError):
        CompanyCreate(name="X", nif="12")

    with pytest.raises(ValidationError):
        CompanyUpdate(nif="000000000")
