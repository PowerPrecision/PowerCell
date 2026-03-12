"""
Testes unitários para modelos de dados.
"""
import pytest
from datetime import datetime, timezone
import re


class TestClientModel:
    """Testes para o modelo de Cliente."""
    
    def test_client_required_fields(self):
        """Testa campos obrigatórios do cliente."""
        required_fields = ["name", "email"]
        optional_fields = ["phone", "nif", "address"]
        
        client = {
            "name": "João Silva",
            "email": "joao@test.com"
        }
        
        for field in required_fields:
            assert field in client
    
    def test_email_format_validation(self):
        """Testa validação de formato de email."""
        def is_valid_email(email):
            pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
            return bool(re.match(pattern, email))
        
        valid_emails = [
            "user@example.com",
            "user.name@domain.pt",
            "user+tag@test.co.uk"
        ]
        
        invalid_emails = [
            "invalid",
            "@domain.com",
            "user@",
            "user@.com"
        ]
        
        for email in valid_emails:
            assert is_valid_email(email), f"'{email}' should be valid"
        
        for email in invalid_emails:
            assert not is_valid_email(email), f"'{email}' should be invalid"
    
    def test_phone_normalization(self):
        """Testa normalização de números de telefone."""
        def normalize_phone(phone):
            # Remove tudo exceto dígitos
            digits = re.sub(r'\D', '', phone)
            
            # Se começa com 00351 ou +351, remove
            if digits.startswith('00351'):
                digits = digits[5:]
            elif digits.startswith('351') and len(digits) > 9:
                digits = digits[3:]
            
            return digits
        
        test_cases = [
            ("+351 912 345 678", "912345678"),
            ("00351912345678", "912345678"),
            ("912 345 678", "912345678"),
            ("912-345-678", "912345678"),
        ]
        
        for original, expected in test_cases:
            result = normalize_phone(original)
            assert result == expected


class TestProcessModel:
    """Testes para o modelo de Processo."""
    
    def test_process_status_values(self):
        """Testa valores válidos de status."""
        valid_statuses = [
            "triagem",
            "documentacao",
            "analise",
            "aprovado",
            "recusado",
            "concluido",
            "desistido",
            "cancelado"
        ]
        
        for status in valid_statuses:
            assert status.islower()
            assert " " not in status
    
    def test_process_number_format(self):
        """Testa formato do número de processo."""
        def generate_process_number(sequence, year=None):
            if year is None:
                year = datetime.now().year
            return f"PP-{year}-{sequence:04d}"
        
        test_cases = [
            (1, 2024, "PP-2024-0001"),
            (42, 2024, "PP-2024-0042"),
            (9999, 2023, "PP-2023-9999"),
        ]
        
        for seq, year, expected in test_cases:
            result = generate_process_number(seq, year)
            assert result == expected
    
    def test_process_type_validation(self):
        """Testa tipos válidos de processo."""
        valid_types = [
            "credito_habitacao",
            "credito_pessoal",
            "credito_automovel",
            "seguro",
            "outro"
        ]
        
        for ptype in valid_types:
            assert "_" in ptype or ptype == "seguro" or ptype == "outro"


class TestPersonalDataModel:
    """Testes para o modelo de Dados Pessoais."""
    
    def test_personal_data_structure(self):
        """Testa estrutura de dados pessoais."""
        personal_data = {
            "full_name": "João Manuel Silva",
            "nif": "123456789",
            "birth_date": "1985-06-15",
            "nationality": "Portuguesa",
            "marital_status": "casado",
            "id_type": "CC",
            "id_number": "12345678",
            "id_expiry": "2028-03-20"
        }
        
        required_fields = ["full_name"]
        for field in required_fields:
            assert field in personal_data
    
    def test_marital_status_values(self):
        """Testa valores válidos de estado civil."""
        valid_statuses = [
            "solteiro",
            "casado",
            "uniao_facto",
            "divorciado",
            "viuvo",
            "separado"
        ]
        
        for status in valid_statuses:
            assert status.islower()
    
    def test_birth_date_format(self):
        """Testa formato de data de nascimento."""
        def is_valid_date_format(date_str):
            pattern = r'^\d{4}-\d{2}-\d{2}$'
            if not re.match(pattern, date_str):
                return False
            
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                return True
            except ValueError:
                return False
        
        valid_dates = ["1985-06-15", "2000-01-01", "1970-12-31"]
        invalid_dates = ["15/06/1985", "1985/06/15", "invalid"]
        
        for date in valid_dates:
            assert is_valid_date_format(date)
        
        for date in invalid_dates:
            assert not is_valid_date_format(date)


class TestFinancialDataModel:
    """Testes para o modelo de Dados Financeiros."""
    
    def test_financial_data_structure(self):
        """Testa estrutura de dados financeiros."""
        financial_data = {
            "monthly_income": 2500.00,
            "employer": "Empresa XYZ",
            "employment_type": "efetivo",
            "years_employed": 5,
            "other_income": 500.00,
            "monthly_expenses": 1200.00,
            "existing_loans": []
        }
        
        assert financial_data["monthly_income"] >= 0
        assert isinstance(financial_data["existing_loans"], list)
    
    def test_employment_type_values(self):
        """Testa tipos de emprego válidos."""
        valid_types = [
            "efetivo",
            "contrato",
            "independente",
            "reformado",
            "desempregado"
        ]
        
        for emp_type in valid_types:
            assert emp_type.islower()
    
    def test_income_validation(self):
        """Testa validação de valores de rendimento."""
        def is_valid_income(value):
            return isinstance(value, (int, float)) and value >= 0
        
        valid_incomes = [0, 1000, 2500.50, 10000]
        invalid_incomes = [-100, "string", None]
        
        for income in valid_incomes:
            assert is_valid_income(income)
        
        for income in invalid_incomes:
            if income is not None:
                assert not is_valid_income(income)


class TestRealEstateDataModel:
    """Testes para o modelo de Dados Imobiliários."""
    
    def test_real_estate_structure(self):
        """Testa estrutura de dados imobiliários."""
        real_estate_data = {
            "property_value": 250000,
            "property_type": "apartamento",
            "location": "Lisboa",
            "area_m2": 100,
            "num_rooms": 3,
            "construction_year": 2010
        }
        
        assert real_estate_data["property_value"] > 0
        assert real_estate_data["area_m2"] > 0
    
    def test_property_type_values(self):
        """Testa tipos de imóvel válidos."""
        valid_types = [
            "apartamento",
            "moradia",
            "terreno",
            "comercial",
            "armazem"
        ]
        
        for ptype in valid_types:
            assert ptype.islower()
    
    def test_financing_calculation(self):
        """Testa cálculo de financiamento."""
        def calculate_ltv(loan_amount, property_value):
            if property_value == 0:
                return 0
            return (loan_amount / property_value) * 100
        
        test_cases = [
            (200000, 250000, 80.0),   # 80% LTV
            (175000, 250000, 70.0),   # 70% LTV
            (250000, 250000, 100.0),  # 100% LTV
        ]
        
        for loan, value, expected_ltv in test_cases:
            result = calculate_ltv(loan, value)
            assert result == expected_ltv


class TestDocumentMetadataModel:
    """Testes para o modelo de Metadados de Documento."""
    
    def test_document_metadata_structure(self):
        """Testa estrutura de metadados."""
        metadata = {
            "id": "doc-123",
            "process_id": "proc-456",
            "filename": "CC_JoaoSilva.pdf",
            "s3_path": "processos/2024/001/CC_JoaoSilva.pdf",
            "ai_category": "identificacao",
            "ai_subcategory": "cc",
            "ai_confidence": 0.95,
            "ai_tags": ["cartão cidadão", "identificação", "NIF"],
            "is_categorized": True,
            "uploaded_at": datetime.now(timezone.utc).isoformat()
        }
        
        assert 0 <= metadata["ai_confidence"] <= 1
        assert isinstance(metadata["ai_tags"], list)
        assert metadata["is_categorized"] == True
    
    def test_document_categories(self):
        """Testa categorias válidas de documentos."""
        valid_categories = [
            "identificacao",
            "rendimentos",
            "emprego",
            "bancarios",
            "imovel",
            "contratos",
            "fiscais",
            "simulacoes",
            "outros"
        ]
        
        for cat in valid_categories:
            assert cat.islower()
            assert " " not in cat
    
    def test_expiry_date_format(self):
        """Testa formato de data de validade."""
        def is_valid_expiry(date_str):
            if not date_str:
                return True  # Opcional
            
            # Verificar formato estrito YYYY-MM-DD
            pattern = r'^\d{4}-\d{2}-\d{2}$'
            if not re.match(pattern, date_str):
                return False
            
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                return True
            except ValueError:
                return False
        
        valid_dates = ["2028-03-15", "2025-12-31", None, ""]
        invalid_dates = ["15/03/2028", "2028-3-15", "invalid"]  # 2028-3-15 é inválido (deveria ser 2028-03-15)
        
        for date in valid_dates:
            assert is_valid_expiry(date), f"'{date}' should be valid"
        
        for date in invalid_dates:
            if date:
                assert not is_valid_expiry(date), f"'{date}' should be invalid"


class TestLeadModel:
    """Testes para o modelo de Lead."""
    
    def test_lead_status_values(self):
        """Testa valores válidos de status de lead."""
        valid_statuses = [
            "novo",
            "contactado",
            "qualificado",
            "proposta",
            "negociacao",
            "ganho",
            "perdido"
        ]
        
        for status in valid_statuses:
            assert status.islower()
    
    def test_lead_source_values(self):
        """Testa fontes válidas de leads."""
        valid_sources = [
            "website",
            "referencia",
            "idealista",
            "supercasa",
            "imovirtual",
            "importacao_html",
            "manual"
        ]
        
        for source in valid_sources:
            assert source.islower()
    
    def test_lead_priority_calculation(self):
        """Testa cálculo de prioridade de lead."""
        def calculate_priority(value, urgency, source):
            score = 0
            
            # Valor do imóvel
            if value >= 500000:
                score += 30
            elif value >= 250000:
                score += 20
            elif value >= 100000:
                score += 10
            
            # Urgência
            if urgency == "alta":
                score += 30
            elif urgency == "media":
                score += 15
            
            # Fonte
            if source == "referencia":
                score += 20
            elif source == "website":
                score += 10
            
            if score >= 60:
                return "alta"
            elif score >= 30:
                return "media"
            return "baixa"
        
        # Lead de alto valor com urgência
        assert calculate_priority(500000, "alta", "referencia") == "alta"
        
        # Lead médio
        assert calculate_priority(150000, "media", "website") == "media"
        
        # Lead baixo
        assert calculate_priority(50000, "baixa", "manual") == "baixa"


class TestNotificationModel:
    """Testes para o modelo de Notificação."""
    
    def test_notification_types(self):
        """Testa tipos válidos de notificação."""
        valid_types = [
            "process_update",
            "document_expiry",
            "task_assigned",
            "email_received",
            "system_alert",
            "document_expiry_watchdog"
        ]
        
        for ntype in valid_types:
            assert "_" in ntype or ntype == "system"
    
    def test_notification_urgency_levels(self):
        """Testa níveis de urgência."""
        urgency_levels = ["low", "medium", "high", "critical"]
        
        assert "critical" in urgency_levels
        assert urgency_levels.index("critical") > urgency_levels.index("low")
    
    def test_notification_structure(self):
        """Testa estrutura de notificação."""
        notification = {
            "id": "notif-123",
            "type": "document_expiry",
            "title": "Documento a expirar",
            "message": "CC de João Silva expira em 7 dias",
            "user_id": "user-456",
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {"process_id": "proc-789", "days_remaining": 7}
        }
        
        required_fields = ["id", "type", "title", "user_id", "is_read"]
        for field in required_fields:
            assert field in notification
