"""Unit tests for lead route thinning helpers."""


def test_lead_helpers_exports():
    from services.lead_helpers import _log_system_error, _parse_plain_text

    assert callable(_log_system_error)
    assert callable(_parse_plain_text)


def test_parse_plain_text_extracts_common_fields():
    from services.lead_helpers import _parse_plain_text

    text = (
        "Apartamento T2 à venda em Lisboa\n"
        "Preço: 250.000 €\n"
        "Área: 85 m²\n"
        "Ref: AB12345\n"
        "Contacto: 912345678\n"
        "Remax Cascais\n"
        "Este apartamento está localizado numa zona residencial calma com excelente acesso "
        "a transportes e comércio local próximo.\n"
    )
    data = _parse_plain_text(text)
    assert data.get("tipologia") == "T2"
    assert data.get("quartos") == 2
    assert data.get("preco") == 250000
    assert data.get("area") == 85
    assert data.get("agente_telefone") == "912345678"
    assert "agencia_nome" in data or "localizacao" in data or "titulo" in data


def test_lead_modules_export_run_entrypoints():
    from services import (
        lead_helpers,
        lead_list,
        lead_extract,
        lead_crud,
        lead_associate,
    )

    assert callable(lead_helpers._log_system_error)
    assert callable(lead_helpers._parse_plain_text)

    assert callable(lead_list.run_list_leads)
    assert callable(lead_list.run_get_leads_by_status)
    assert callable(lead_list.run_get_consultores_for_filter)

    assert callable(lead_extract.run_extract_url_data)
    assert callable(lead_extract.run_extract_html_data)
    assert callable(lead_extract.run_create_lead_from_url)

    assert callable(lead_crud.run_create_lead)
    assert callable(lead_crud.run_update_lead)
    assert callable(lead_crud.run_update_lead_status)
    assert callable(lead_crud.run_refresh_lead_price)
    assert callable(lead_crud.run_delete_lead)

    assert callable(lead_associate.run_associate_client)


def test_lead_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "leads.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 12
    assert len(text.splitlines()) < 200


def test_lead_no_preexisting_collision():
    """Ensure thinning used lead_* prefix and did not invent colliding names."""
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    lead_files = sorted(p.name for p in services_dir.glob("lead_*.py"))
    assert lead_files == [
        "lead_associate.py",
        "lead_crud.py",
        "lead_extract.py",
        "lead_helpers.py",
        "lead_list.py",
    ]
