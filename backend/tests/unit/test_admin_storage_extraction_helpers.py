"""Unit tests for admin_storage route thinning helpers."""
from services.admin_s3_explorer import (
    S3_EXPLORER_BASE_PATH,
    _resolve_explorer_path,
)
from services.admin_s3_process_mappings import _clean_s3_folder


def test_resolve_explorer_path_empty_returns_base():
    assert _resolve_explorer_path("") == S3_EXPLORER_BASE_PATH
    assert _resolve_explorer_path("   ") == S3_EXPLORER_BASE_PATH


def test_resolve_explorer_path_already_prefixed():
    path = f"{S3_EXPLORER_BASE_PATH}/Foo_Bar"
    assert _resolve_explorer_path(path) == path


def test_resolve_explorer_path_relative_gets_prefixed():
    assert _resolve_explorer_path("Foo_Bar") == f"{S3_EXPLORER_BASE_PATH}/Foo_Bar"


def test_clean_s3_folder():
    assert _clean_s3_folder(None) is None
    assert _clean_s3_folder("") is None
    assert _clean_s3_folder("undefined") is None
    assert _clean_s3_folder("null") is None
    assert _clean_s3_folder("None") is None
    assert _clean_s3_folder("Documentação Clientes/X") == "Documentação Clientes/X"


def test_admin_s3_modules_export_run_entrypoints():
    from services import (
        admin_s3_client_mappings,
        admin_s3_user_mappings,
        admin_s3_process_mappings,
        admin_s3_explorer,
    )

    assert callable(admin_s3_client_mappings.run_auto_map_client_s3_folders)
    assert callable(admin_s3_user_mappings.run_get_user_s3_mappings)
    assert callable(admin_s3_user_mappings.run_update_user_s3_mapping)
    assert callable(admin_s3_user_mappings.run_get_user_s3_mapping)
    assert callable(admin_s3_process_mappings.run_get_process_s3_mappings)
    assert callable(admin_s3_process_mappings.run_update_process_s3_mapping)
    assert callable(admin_s3_process_mappings.run_fix_missing_client_names)
    assert callable(admin_s3_process_mappings.run_batch_update_process_s3_mappings)
    assert callable(admin_s3_explorer.run_get_s3_folder_contents)
    assert callable(admin_s3_explorer.run_s3_rename)
    assert callable(admin_s3_explorer.run_s3_delete)
    assert callable(admin_s3_explorer.run_s3_create_folder)
    assert callable(admin_s3_explorer.run_s3_upload)
    assert callable(admin_s3_explorer.run_s3_download)
    assert hasattr(admin_s3_explorer, "S3RenameRequest")
    assert hasattr(admin_s3_explorer, "FILE_OPS_ROLES")


def test_admin_storage_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "admin_storage.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 15
    assert len(text.splitlines()) < 280
    # Must not create services/admin_storage.py (route name collision)
    assert not (Path(__file__).resolve().parents[2] / "services" / "admin_storage.py").exists()
