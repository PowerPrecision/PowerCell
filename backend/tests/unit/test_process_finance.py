"""
Testes unitários para services.process_finance (cálculo de comissões).
"""
from services.process_finance import calculate_commissions, resolve_fee_inputs


class TestResolveFeeInputs:
    def test_from_finance_config_percentage(self):
        process = {
            "real_estate_data": {"valor_imovel": 200_000},
            "credit_data": {"loan_amount": 150_000},
        }
        config = {
            "fee_type": "percentage",
            "default_value": 3.0,
            "tax_rate": 23.0,
        }
        fees = resolve_fee_inputs(process, config)
        assert fees["re_base_value"] == 200_000.0
        assert fees["cr_base_value"] == 150_000.0
        assert fees["re_fee_type"] == "percentage"
        assert fees["re_fee_value"] == 3.0
        assert fees["cr_fee_type"] == "percentage"
        assert fees["cr_fee_value"] == 3.0
        assert fees["tax_rate"] == 23.0
        assert fees["base_business_value"] == 150_000.0

    def test_separate_re_and_credit_fees(self):
        process = {
            "real_estate_data": {"valor_imovel": 100_000},
            "credit_data": {"requested_amount": 80_000},
        }
        config = {
            "fee_type": "percentage",
            "default_value": 2.0,
            "real_estate_fee_type": "percentage",
            "real_estate_fee_value": 5.0,
            "credit_fee_type": "fixed",
            "credit_fee_value": 500.0,
        }
        fees = resolve_fee_inputs(process, config)
        assert fees["re_fee_type"] == "percentage"
        assert fees["re_fee_value"] == 5.0
        assert fees["cr_fee_type"] == "fixed"
        assert fees["cr_fee_value"] == 500.0
        assert fees["cr_base_value"] == 80_000.0

    def test_legacy_comissao_mediacao_without_config(self):
        process = {
            "financial_data": {"comissao_mediacao": 2500},
        }
        fees = resolve_fee_inputs(process, None)
        assert fees["cr_fee_type"] == "fixed"
        assert fees["cr_fee_value"] == 2500.0
        assert fees["cr_base_value"] == 2500.0
        assert fees["applied_fee_type"] == "fixed"
        assert fees["base_business_value"] == 2500.0

    def test_empty_process_zeros(self):
        fees = resolve_fee_inputs({}, None)
        assert fees["re_base_value"] == 0.0
        assert fees["cr_base_value"] == 0.0
        assert fees["re_fee_type"] is None
        assert fees["tax_rate"] == 23.0


class TestCalculateCommissions:
    def test_percentage_both(self):
        result = calculate_commissions(
            re_base_value=200_000,
            re_fee_type="percentage",
            re_fee_value=3.0,
            cr_base_value=100_000,
            cr_fee_type="percentage",
            cr_fee_value=2.0,
            tax_rate=23.0,
        )
        assert result["re_commission"] == 6000.0
        assert result["cr_commission"] == 2000.0
        assert result["expected_commission"] == 8000.0
        assert result["tax_amount"] == 1840.0
        assert result["total_with_tax"] == 9840.0

    def test_fixed_fees(self):
        result = calculate_commissions(
            re_base_value=0,
            re_fee_type="fixed",
            re_fee_value=1500.0,
            cr_base_value=0,
            cr_fee_type="fixed",
            cr_fee_value=500.0,
            tax_rate=23.0,
        )
        assert result["re_commission"] == 1500.0
        assert result["cr_commission"] == 500.0
        assert result["expected_commission"] == 2000.0
        assert result["tax_amount"] == 460.0
        assert result["total_with_tax"] == 2460.0

    def test_missing_fee_type_yields_zero(self):
        result = calculate_commissions(
            re_base_value=100_000,
            re_fee_type=None,
            re_fee_value=3.0,
            cr_base_value=50_000,
            cr_fee_type=None,
            cr_fee_value=2.0,
        )
        assert result["re_commission"] == 0.0
        assert result["cr_commission"] == 0.0
        assert result["expected_commission"] == 0.0
        assert result["tax_amount"] == 0.0
        assert result["total_with_tax"] == 0.0

    def test_percentage_with_zero_base(self):
        result = calculate_commissions(
            re_base_value=0,
            re_fee_type="percentage",
            re_fee_value=3.0,
            cr_base_value=0,
            cr_fee_type="percentage",
            cr_fee_value=2.0,
        )
        assert result["expected_commission"] == 0.0
