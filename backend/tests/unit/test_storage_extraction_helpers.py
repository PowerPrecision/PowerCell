"""Unit tests for storage route thinning (storage_api_*)."""

from pathlib import Path


def test_storage_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "storage_api_checklist.py",
        "storage_api_folder.py",
        "storage_api_status.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("storage_api_*.py"))
    assert files == expected
    # NEVER overwrite core storage modules
    assert (services_dir / "storage_service.py").exists()
    assert (services_dir / "s3_storage.py").exists()


def test_storage_api_export_run_entrypoints():
    from services import (
        storage_api_status,
        storage_api_folder,
        storage_api_checklist,
    )

    assert callable(storage_api_status.run_get_storage_status)
    assert callable(storage_api_folder.run_get_process_folder_url)
    assert callable(storage_api_folder.run_save_process_folder_url)
    assert callable(storage_api_folder.run_delete_process_folder_url)
    assert callable(storage_api_checklist.run_generate_document_checklist)
    assert callable(storage_api_checklist.run_get_document_checklist)


def test_storage_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "storage.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 6
    assert len(text.splitlines()) < 100
    assert "AWS_ACCESS_KEY_ID" not in text
    assert "generate_checklist" not in text
