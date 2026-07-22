"""Unit tests for finance route thinning helpers."""


def test_finance_helpers_safe_float_and_credito():
    from services.finance_helpers import _safe_float, _is_credito, _month_label

    assert _safe_float(None) == 0.0
    assert _safe_float("12.5") == 12.5
    assert _safe_float("x") == 0.0
    assert _safe_float(3) == 3.0
    assert _is_credito("crédito habitação") is True
    assert _is_credito("compra imovel") is False
    assert _month_label(7) == "Jul"
    assert _month_label(0) == ""


def test_finance_modules_export_run_entrypoints():
    from services import (
        finance_helpers,
        finance_dashboard,
        finance_commissions,
        finance_configs,
        finance_pool,
        finance_process_records,
    )

    assert callable(finance_helpers._safe_float)
    assert callable(finance_helpers._is_credito)
    assert callable(finance_helpers._month_label)
    assert callable(finance_helpers._get_finance_config)
    assert callable(finance_helpers._get_pct)
    assert callable(finance_helpers._get_processes)
    assert callable(finance_helpers._calc_area_metrics)
    assert finance_helpers.DashboardFinanceConfigUpdate is not None

    assert callable(finance_dashboard.run_get_finance_config)
    assert callable(finance_dashboard.run_update_finance_config)
    assert callable(finance_dashboard.run_get_finance_summary)
    assert callable(finance_dashboard.run_get_finance_monthly)
    assert callable(finance_dashboard.run_get_finance_performance)

    assert callable(finance_commissions._calc_commissions_data)
    assert callable(finance_commissions.run_get_finance_commissions)
    assert callable(finance_commissions.run_export_commissions_csv)

    assert callable(finance_configs._doc_to_config_response)
    assert callable(finance_configs.run_create_finance_config)
    assert callable(finance_configs.run_list_finance_configs)
    assert callable(finance_configs.run_get_finance_config_by_id)
    assert callable(finance_configs.run_update_finance_config_by_id)
    assert callable(finance_configs.run_delete_finance_config)

    assert callable(finance_pool.run_get_pool_distribution)
    assert callable(finance_pool.run_export_pool_distribution_csv)

    assert callable(finance_process_records._doc_to_process_finance_response)
    assert callable(finance_process_records.run_get_process_finance_summary)
    assert callable(finance_process_records.run_create_process_finance)
    assert callable(finance_process_records.run_list_process_finances)
    assert callable(finance_process_records.run_get_process_finance_by_id)
    assert callable(finance_process_records.run_update_process_finance)
    assert callable(finance_process_records.run_update_process_finance_status)
    assert callable(finance_process_records.run_delete_process_finance)


def test_finance_router_is_thin_stubs_only():
    from pathlib import Path

    routes_path = Path(__file__).resolve().parents[2] / "routes" / "finance.py"
    text = routes_path.read_text()
    assert text.count("return await run_") >= 20
    assert len(text.splitlines()) < 320


def test_process_finance_not_overwritten():
    """Ensure thinning did not collide with existing process_finance service."""
    from services import process_finance

    assert callable(process_finance.calculate_commissions)
    assert callable(process_finance.resolve_fee_inputs)
