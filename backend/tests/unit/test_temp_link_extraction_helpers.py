"""Unit tests for temp_links route thinning helpers (temp_link_api_*)."""

from pathlib import Path


def test_temp_link_api_modules_export_run_entrypoints():
    from services import temp_link_api_staff, temp_link_api_public

    assert callable(temp_link_api_staff.run_create_temp_link)
    assert callable(temp_link_api_staff.run_list_process_temp_links)
    assert callable(temp_link_api_staff.run_cancel_temp_link)
    assert callable(temp_link_api_staff.run_delete_temp_link)

    assert callable(temp_link_api_public.run_get_public_link_info)
    assert callable(temp_link_api_public.run_upload_via_temp_link)
    assert callable(temp_link_api_public.run_download_via_temp_link)
    assert callable(temp_link_api_public.run_download_all_via_temp_link)
    assert callable(temp_link_api_public.run_list_temp_link_files)


def test_temp_link_upload_helpers():
    from services.temp_link_api_public import (
        validate_upload_extension,
        content_matches_extension,
        ALLOWED_EXTENSIONS,
    )

    assert "pdf" in ALLOWED_EXTENSIONS
    assert validate_upload_extension("doc.pdf") == "pdf"
    assert validate_upload_extension("evil.exe") is None
    assert content_matches_extension(b"%PDF-1.4...", "pdf") is True
    assert content_matches_extension(b"not-a-pdf", "pdf") is False
    assert content_matches_extension(b"\xFF\xD8\xFF\xE0", "jpg") is True
    assert content_matches_extension(b"\x89PNG\r\n", "png") is True


def test_temp_links_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "temp_links.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 9
    assert "/public/{token}" in text
    assert "/create" in text
    assert len(text.splitlines()) < 160


def test_temp_link_service_not_overwritten():
    """CRITICAL: thinning must use temp_link_api_* and keep temp_link_service.py."""
    from services import temp_link_service
    from services.temp_link_service import TempLinkService, temp_link_service as svc

    services_dir = Path(__file__).resolve().parents[2] / "services"
    api_files = sorted(p.name for p in services_dir.glob("temp_link_api_*.py"))
    assert api_files == [
        "temp_link_api_public.py",
        "temp_link_api_staff.py",
    ]
    assert (services_dir / "temp_link_service.py").exists()
    assert hasattr(TempLinkService, "generate_secure_token")
    assert hasattr(TempLinkService, "create_link")
    assert hasattr(svc, "create_link")
    assert hasattr(temp_link_service, "__file__")
    # Core service file should still be substantial
    core_lines = (services_dir / "temp_link_service.py").read_text().count("\n")
    assert core_lines > 200
