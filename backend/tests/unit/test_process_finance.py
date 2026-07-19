"""
Testes unitários para services/process_finance — matemática de comissões.
"""
from services.process_finance import _resolve_fee_inputs, _calculate_commissions


class TestResolveFeeInputs:
    def test_uses_finance_config_percentage(self):
        process = {
            "id": "p1",
            "real_estate_data": {"valor_imovel": 200_000},
            "credit_data": {"loan_amount": 160_000},
        }
        config = {
            "fee_type": "percentage",
            "default_value": 2.0,
            "tax_rate": 23.0,
            "real_estate_fee_type": "percentage",
            "real_estate_fee_value": 3.0,
            "credit_fee_type": "percentage",
            "credit_fee_value": 1.5,
        }
        fees = _resolve_fee_inputs(process, "co1", config)
        assert fees["re_base_value"] == 200_000.0
        assert fees["cr_base_value"] == 160_000.0
        assert fees["re_fee_type"] == "percentage"
        assert fees["re_fee_value"] == 3.0
        assert fees["cr_fee_value"] == 1.5
        assert fees["tax_rate"] == 23.0

    def test_legacy_comissao_mediacao_without_config(self):
        process = {
            "id": "p2",
            "financial_data": {"comissao_mediacao": 1500},
        }
        fees = _resolve_fee_inputs(process, "co1", None)
        assert fees["cr_fee_type"] == "fixed"
        assert fees["cr_fee_value"] == 1500.0
        assert fees["base_business_value"] == 1500.0


class TestCalculateCommissions:
    def test_percentage_and_fixed_totals(self):
        fee_inputs = {
            "re_base_value": 200_000.0,
            "re_fee_type": "percentage",
            "re_fee_value": 3.0,
            "cr_base_value": 100_000.0,
            "cr_fee_type": "fixed",
            "cr_fee_value": 500.0,
            "tax_rate": 23.0,
        }
        result = _calculate_commissions(fee_inputs)
        assert result["re_commission"] == 6000.0
        assert result["cr_commission"] == 500.0
        assert result["expected_commission"] == 6500.0
        assert result["tax_amount"] == 1495.0
        assert result["total_with_tax"] == 7995.0

    def test_zeros_when_fee_type_missing(self):
        fee_inputs = {
            "re_base_value": 100.0,
            "re_fee_type": None,
            "re_fee_value": None,
            "cr_base_value": 100.0,
            "cr_fee_type": None,
            "cr_fee_value": None,
            "tax_rate": 23.0,
        }
        result = _calculate_commissions(fee_inputs)
        assert result["expected_commission"] == 0.0
        assert result["total_with_tax"] == 0.0
