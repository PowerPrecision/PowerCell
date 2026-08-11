"""Unit tests for public route thinning helpers (public_*)."""


def test_euribor_core_service_not_overwritten():
    """Ensure thinning did not collide with existing services/euribor_service.py."""
    from pathlib import Path
    from services import euribor_service

    assert callable(euribor_service.get_euribor_rates)
    core = Path(__file__).resolve().parents[2] / "services" / "euribor_service.py"
    assert core.exists()
    text = core.read_text()
    assert "CACHE_TTL_SECONDS" in text
    assert "run_get_euribor_rates" not in text


def test_public_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "public_euribor.py",
        "public_form_config.py",
        "public_health.py",
        "public_registration.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    public_files = sorted(p.name for p in services_dir.glob("public_*.py"))
    assert public_files == expected


def test_public_modules_export_run_entrypoints():
    from services import (
        public_registration,
        public_health,
        public_form_config,
        public_euribor,
    )

    assert callable(public_registration.run_public_client_registration)
    assert callable(public_health.run_public_health)
    assert callable(public_form_config.run_get_public_form_config)
    assert callable(public_euribor.run_get_euribor_rates)


def test_public_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "public.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 4
    assert len(text.splitlines()) < 80
    # Rate limits preserved on stubs
    assert '@limiter.limit("5/hour")' in text
    assert '@limiter.limit("30/minute")' in text
    assert '@limiter.limit("60/minute")' in text
    assert "/client-registration" in text
    assert "/form-config" in text
    assert "/euribor" in text


def test_public_form_config_uses_form_config_defaults():
    """Public form-config imports defaults from form_config_defaults (avoids routes circular import)."""
    from pathlib import Path
    from routes.form_config import DEFAULT_FORM_CONFIG, DEFAULT_STEP_CONFIG
    from services.form_config_defaults import (
        DEFAULT_FORM_CONFIG as D2,
        DEFAULT_STEP_CONFIG as S2,
    )

    assert DEFAULT_FORM_CONFIG is D2
    assert DEFAULT_STEP_CONFIG is S2

    src = (
        Path(__file__).resolve().parents[2] / "services" / "public_form_config.py"
    ).read_text()
    assert "from services.form_config_defaults import" in src
    assert "DEFAULT_FORM_CONFIG" in src
    assert "DEFAULT_STEP_CONFIG" in src


def test_public_health_returns_ok():
    import asyncio
    from fastapi.responses import JSONResponse
    from services.public_health import run_public_health

    class _Req:
        pass

    result = asyncio.run(run_public_health(_Req()))
    assert isinstance(result, JSONResponse)
    assert result.status_code == 200
