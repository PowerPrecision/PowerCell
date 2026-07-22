"""Unit tests for automation route thinning (automation_api_*)."""

from pathlib import Path


def test_automation_api_modules_exist():
    services_dir = Path(__file__).resolve().parents[2] / "services"
    expected = [
        "automation_api_meta.py",
        "automation_api_rules.py",
    ]
    for name in expected:
        assert (services_dir / name).exists(), f"missing {name}"
    files = sorted(p.name for p in services_dir.glob("automation_api_*.py"))
    assert files == expected


def test_automation_api_export_run_entrypoints():
    from services import automation_api_rules, automation_api_meta

    assert callable(automation_api_rules.run_get_rules)
    assert callable(automation_api_rules.run_get_rule_by_id)
    assert callable(automation_api_rules.run_create_rule)
    assert callable(automation_api_rules.run_update_rule)
    assert callable(automation_api_rules.run_delete_rule)
    assert callable(automation_api_meta.run_list_triggers)
    assert callable(automation_api_meta.run_list_actions)
    assert automation_api_rules.RuleCreate is not None
    assert automation_api_rules.RuleUpdate is not None


def test_automation_router_is_thin_stubs_only():
    routes_path = Path(__file__).resolve().parents[2] / "routes" / "automation.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 7
    assert len(text.splitlines()) < 110
    assert "VALID_TRIGGERS" not in text
    assert "create_task" not in text
