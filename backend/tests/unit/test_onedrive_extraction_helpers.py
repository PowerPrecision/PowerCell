"""Unit tests for onedrive route thinning helpers (onedrive_*)."""


def test_onedrive_core_service_not_overwritten():
    from pathlib import Path
    from services import onedrive

    core = Path(__file__).resolve().parents[2] / "services" / "onedrive.py"
    assert core.exists()
    text = core.read_text()
    assert "class OneDriveService" in text
    assert "run_get_onedrive_status" not in text
    assert text.count("\n") > 200
    assert hasattr(onedrive, "OneDriveService")


def test_onedrive_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "onedrive_checklist.py",
        "onedrive_files.py",
        "onedrive_folder_url.py",
        "onedrive_links.py",
        "onedrive_status.py",
        "onedrive_url_validation.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("onedrive_*.py"))
    assert files == expected


def test_onedrive_modules_export_run_entrypoints():
    from services import (
        onedrive_status,
        onedrive_folder_url,
        onedrive_checklist,
        onedrive_files,
        onedrive_links,
    )

    assert callable(onedrive_status.run_get_onedrive_status)
    assert callable(onedrive_folder_url.run_get_process_folder_url)
    assert callable(onedrive_folder_url.run_save_process_folder_url)
    assert callable(onedrive_folder_url.run_remove_process_folder_url)
    assert callable(onedrive_checklist.run_generate_document_checklist)
    assert callable(onedrive_checklist.run_get_document_checklist)
    assert callable(onedrive_files.run_get_client_files_by_name)
    assert callable(onedrive_links.run_get_process_links)
    assert callable(onedrive_links.run_add_process_link)
    assert callable(onedrive_links.run_delete_process_link)
    assert callable(onedrive_links.run_update_process_link)
    assert onedrive_links.LinkCreate is not None
    assert onedrive_links.LinkUpdate is not None


def test_url_validation_helpers():
    from services.onedrive_url_validation import (
        is_valid_folder_url,
        is_valid_link_url,
    )

    assert is_valid_folder_url("https://1drv.ms/f/abc")
    assert is_valid_folder_url("https://company.sharepoint.com/sites/x")
    assert is_valid_folder_url("s3://bucket/path")
    assert not is_valid_folder_url("ftp://bad")
    assert is_valid_link_url("https://drive.google.com/drive/folders/x")
    assert not is_valid_link_url("not-a-url")


def test_onedrive_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "onedrive.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 11
    assert len(text.splitlines()) < 160
    assert "db.processes" not in text
    assert "services/onedrive.py" in text
