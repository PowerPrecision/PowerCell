"""Unit tests for minutas route thinning helpers (minutas_api_*)."""


def test_minutas_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "minutas_api_crud.py",
        "minutas_api_import.py",
        "minutas_api_models.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("minutas_api_*.py"))
    assert files == expected
    # Must not overwrite RGPD minutas service
    assert (services_dir / "rgpd_minutas.py").exists()


def test_minutas_api_export_run_entrypoints():
    from services import minutas_api_models, minutas_api_crud, minutas_api_import

    assert minutas_api_models.MinutaCreate is not None
    assert minutas_api_models.MinutaUpdate is not None
    assert callable(minutas_api_crud.run_list_minutas)
    assert callable(minutas_api_crud.run_create_minuta)
    assert callable(minutas_api_crud.run_get_minuta)
    assert callable(minutas_api_crud.run_update_minuta)
    assert callable(minutas_api_crud.run_delete_minuta)
    assert callable(minutas_api_import.run_import_minuta)
    assert callable(minutas_api_import._detect_categoria)


def test_detect_categoria_keywords():
    from services.minutas_api_import import _detect_categoria

    assert _detect_categoria("Contrato Promessa") == "contrato"
    assert _detect_categoria("Procuração Especial") == "procuracao"
    assert _detect_categoria("Declaração de Rendimentos") == "declaracao"
    assert _detect_categoria("Carta de Apresentação") == "carta"
    assert _detect_categoria("Outro Documento") == "outro"


def test_rgpd_minutas_not_overwritten():
    from pathlib import Path
    from services import rgpd_minutas

    core = Path(__file__).resolve().parents[2] / "services" / "rgpd_minutas.py"
    assert core.exists()
    text = core.read_text()
    assert "run_list_minutas" not in text
    assert "MinutaCreate" not in text


def test_minutas_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "minutas.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 100
    assert "sanitize_html" not in text
    # Static /import before /{minuta_id}
    import_pos = text.index('/import"')
    id_pos = text.index('/{minuta_id}"')
    assert import_pos < id_pos
