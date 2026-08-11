"""Unit tests for annotations route thinning helpers (annotations_api_*)."""

from pathlib import Path


def test_annotations_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "annotations_api_crud.py",
        "annotations_api_list.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("annotations_api_*.py"))
    assert files == expected
    assert (services_dir / "annotation_service.py").exists()
    assert (services_dir / "annotation_service.py").read_text().count("\n") > 50
    assert not (services_dir / "annotations.py").exists()


def test_annotations_api_export_run_entrypoints():
    from services import annotations_api_crud, annotations_api_list

    assert callable(annotations_api_crud.run_create_annotation)
    assert callable(annotations_api_crud.run_update_annotation)
    assert callable(annotations_api_crud.run_delete_annotation)
    assert callable(annotations_api_crud.run_resolve_annotation)
    assert callable(annotations_api_list.run_get_document_annotations)
    assert callable(annotations_api_list.run_get_process_annotations)
    assert callable(annotations_api_list.run_get_annotation_stats)


def test_annotations_api_still_imports_annotation_service():
    import inspect

    from services import annotations_api_crud, annotations_api_list

    assert "annotation_service" in inspect.getsource(annotations_api_crud)
    assert "annotation_service" in inspect.getsource(annotations_api_list)


def test_annotations_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "annotations.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 7
    assert len(text.splitlines()) < 120
    # Path order among decorators: static /process paths before /{annotation_id}
    assert '@router.get("/document")' in text
    assert '@router.get("/process/{process_id}/stats")' in text
    assert text.index('@router.get("/process/{process_id}/stats")') < text.index(
        '@router.get("/process/{process_id}")'
    )
    assert text.index('@router.get("/process/{process_id}")') < text.index(
        '@router.put("/{annotation_id}"'
    )
