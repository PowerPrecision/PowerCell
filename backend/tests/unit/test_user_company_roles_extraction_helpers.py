"""Unit tests for user_company_roles route thinning (user_company_roles_api_*)."""


def test_user_company_roles_api_modules_exist():
    from pathlib import Path

    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "user_company_roles_api_active.py",
        "user_company_roles_api_crud.py",
        "user_company_roles_api_migrate.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(
        p.name for p in services_dir.glob("user_company_roles_api_*.py")
    )
    assert files == expected


def test_user_company_roles_api_export_run_entrypoints():
    from services import (
        user_company_roles_api_crud,
        user_company_roles_api_migrate,
        user_company_roles_api_active,
    )

    assert callable(user_company_roles_api_crud.run_list_user_company_roles)
    assert callable(user_company_roles_api_crud.run_get_user_company_role)
    assert callable(user_company_roles_api_crud.run_create_user_company_role)
    assert callable(user_company_roles_api_crud.run_update_user_company_role)
    assert callable(user_company_roles_api_crud.run_delete_user_company_role)
    assert callable(user_company_roles_api_crud.run_assign_user_company_role)
    assert callable(user_company_roles_api_migrate.run_migrate_company_field)
    assert callable(user_company_roles_api_migrate.run_migrate_email_configs)
    assert callable(user_company_roles_api_active.run_set_active_company)


def test_user_company_roles_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = (
        Path(__file__).resolve().parents[2]
        / "routes"
        / "user_company_roles.py"
    )
    text = routes_path.read_text()
    assert text.count("return await run_") >= 8
    assert len(text.splitlines()) < 120
    assert "db.user_company_roles" not in text
    # Static paths before /{role_id}
    migrate_pos = text.index('/migrate"')
    set_active_pos = text.index('/set-active-company"')
    email_pos = text.index('/migrate-email-configs"')
    id_pos = text.index('/{role_id}"')
    assert migrate_pos < id_pos
    assert set_active_pos < id_pos
    assert email_pos < id_pos


def test_user_role_assign_body_validates_role():
    import pytest
    from pydantic import ValidationError
    from models.user_company_role import UserRoleAssignBody

    body = UserRoleAssignBody(company_id="c1", role="diretor")
    assert body.role == "diretor"
    assert body.is_default is False

    with pytest.raises(ValidationError):
        UserRoleAssignBody(company_id="c1", role="nao-existe")
