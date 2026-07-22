"""Unit tests for property route thinning helpers."""


def test_property_helpers_get_next_reference_export():
    from services.property_helpers import get_next_reference

    assert callable(get_next_reference)


def test_property_modules_export_run_entrypoints():
    from services import (
        property_helpers,
        property_list,
        property_crud,
        property_engagement,
        property_excel_import,
        property_documents,
    )

    assert callable(property_helpers.get_next_reference)

    assert callable(property_list.run_list_properties)
    assert callable(property_list.run_get_property_stats)
    assert callable(property_list.run_get_properties_by_process)

    assert callable(property_crud.run_create_property)
    assert callable(property_crud.run_get_property)
    assert callable(property_crud.run_update_property)
    assert callable(property_crud.run_update_property_status)
    assert callable(property_crud.run_delete_property)

    assert callable(property_engagement.run_add_interested_client)
    assert callable(property_engagement.run_get_interested_clients)
    assert callable(property_engagement.run_register_visit)
    assert callable(property_engagement.run_upload_property_photo)
    assert callable(property_engagement.run_remove_property_photo)

    assert callable(property_excel_import.run_import_properties_from_excel)
    assert callable(property_excel_import._process_excel_import)
    assert callable(property_excel_import.run_get_import_job_status)
    assert callable(property_excel_import.run_get_user_import_jobs)
    assert callable(property_excel_import.run_get_import_template)

    assert callable(property_documents.run_upload_property_document)
    assert callable(property_documents.run_get_property_documents)
    assert callable(property_documents.run_delete_property_document)


def test_property_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "properties.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 18
    assert len(text.splitlines()) < 320


def test_property_scraper_not_overwritten():
    """Ensure thinning did not collide with existing property_scraper service."""
    from services import property_scraper

    assert callable(property_scraper.extract_property_data)
