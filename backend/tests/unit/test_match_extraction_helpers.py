"""Unit tests for match route thinning helpers (match_api_*)."""


def test_match_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "match_api_client.py",
        "match_api_property.py",
        "match_api_smart.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("match_api_*.py"))
    assert files == expected
    # Do not overwrite client_match.py or invent services/match.py
    assert (services_dir / "client_match.py").exists()
    assert not (services_dir / "match.py").exists()


def test_match_api_export_run_entrypoints():
    from services import (
        match_api_smart,
        match_api_client,
        match_api_property,
    )

    assert callable(match_api_smart.run_smart_match_for_process)
    assert callable(match_api_client.run_get_all_matches_for_client)
    assert callable(match_api_client.run_get_matching_properties)
    assert callable(match_api_client.run_get_matching_leads)
    assert callable(match_api_client.run_get_client_match_summary)
    assert callable(match_api_property.run_get_matching_clients_for_property)
    assert callable(match_api_property.run_get_matching_clients_for_lead)


def test_match_api_still_imports_client_match():
    """Wrappers must keep delegating to the existing client_match service."""
    import inspect

    from services import match_api_client, match_api_property

    client_src = inspect.getsource(match_api_client)
    prop_src = inspect.getsource(match_api_property)
    assert "from services.client_match import" in client_src
    assert "from services.client_match import" in prop_src
    assert "find_all_matches_for_client" in client_src
    assert "find_matching_clients_for_property" in prop_src


def test_match_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "match.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 7
    assert len(text.splitlines()) < 120
    assert "financials.asking_price" not in text
    assert "desired_bedrooms" not in text
    # Path order: /process before /client before /property before /lead
    assert text.index("/process/{process_id}") < text.index("/client/{process_id}/all")
    assert text.index("/client/{process_id}/all") < text.index(
        "/property/{property_id}/clients"
    )
    assert text.index("/property/{property_id}/clients") < text.index(
        "/lead/{lead_id}/clients"
    )
