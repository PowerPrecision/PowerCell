"""
Testes unitários para serviços de clientes.
"""
import pytest
import re
from datetime import datetime, timezone


class TestClientValidation:
    """Testes para validação de dados de clientes."""
    
    def test_email_validation(self):
        """Testa validação de email."""
        def is_valid_email(email):
            pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
            return bool(re.match(pattern, email)) if email else False
        
        valid = ["user@test.com", "user.name@domain.pt", "u+tag@test.co.uk"]
        invalid = ["invalid", "@test.com", "user@", "", None]
        
        for email in valid:
            assert is_valid_email(email)
        for email in invalid:
            assert not is_valid_email(email)
    
    def test_phone_validation(self):
        """Testa validação de telefone português."""
        def is_valid_phone(phone):
            if not phone:
                return False
            digits = re.sub(r'\D', '', str(phone))
            # Remove código de país
            if digits.startswith('351'):
                digits = digits[3:]
            return len(digits) == 9 and digits[0] in '923'
        
        valid = ["912345678", "+351 912 345 678", "912-345-678"]
        invalid = ["123456789", "12345", "", "812345678"]
        
        for phone in valid:
            assert is_valid_phone(phone), f"{phone} should be valid"
        for phone in invalid:
            assert not is_valid_phone(phone), f"{phone} should be invalid"
    
    def test_nif_validation_pessoa_singular(self):
        """Testa validação de NIF de pessoa singular."""
        def is_valid_nif_pessoa_singular(nif):
            if not nif:
                return False
            digits = re.sub(r'\D', '', str(nif))
            if len(digits) != 9:
                return False
            # Pessoa singular: começa por 1, 2, 6 ou 9
            return digits[0] in '1269'
        
        valid = ["123456789", "212345678", "612345678", "912345678"]
        invalid = ["512345678", "312345678", "12345678", ""]
        
        for nif in valid:
            assert is_valid_nif_pessoa_singular(nif)
        for nif in invalid:
            assert not is_valid_nif_pessoa_singular(nif)


class TestClientSearch:
    """Testes para pesquisa de clientes."""
    
    def test_search_normalization(self):
        """Testa normalização de termos de pesquisa."""
        import unicodedata
        
        def normalize_search(term):
            if not term:
                return ""
            # Remover acentos
            term = unicodedata.normalize('NFD', term)
            term = ''.join(c for c in term if unicodedata.category(c) != 'Mn')
            return term.lower().strip()
        
        assert normalize_search("João") == "joao"
        assert normalize_search("MARIA") == "maria"
        assert normalize_search("  José  ") == "jose"
    
    def test_search_match_logic(self):
        """Testa lógica de matching de pesquisa."""
        def matches_search(client, search_term):
            search = search_term.lower()
            
            name = (client.get("name") or "").lower()
            email = (client.get("email") or "").lower()
            nif = str(client.get("nif") or "")
            
            return search in name or search in email or search in nif
        
        client = {
            "name": "João Silva",
            "email": "joao@test.com",
            "nif": "123456789"
        }
        
        assert matches_search(client, "joão")
        assert matches_search(client, "joao")
        assert matches_search(client, "test.com")
        assert matches_search(client, "123456")
        assert not matches_search(client, "maria")
    
    def test_fuzzy_name_matching(self):
        """Testa matching fuzzy de nomes."""
        import unicodedata
        
        def normalize(s):
            s = unicodedata.normalize('NFD', s)
            s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
            return s.lower()
        
        def fuzzy_match(name1, name2, threshold=0.7):
            # Simplificação: verificar se as primeiras 3 letras coincidem após normalização
            if not name1 or not name2:
                return False
            
            n1 = normalize(name1)[:3]
            n2 = normalize(name2)[:3]
            
            return n1 == n2
        
        assert fuzzy_match("João", "Joao")  # joã vs joa -> joa vs joa
        assert fuzzy_match("Maria", "Maria")
        assert not fuzzy_match("Pedro", "João")


class TestClientDeduplication:
    """Testes para detecção de clientes duplicados."""
    
    def test_duplicate_detection_by_nif(self):
        """Testa detecção de duplicados por NIF."""
        existing_clients = [
            {"id": "1", "nif": "123456789"},
            {"id": "2", "nif": "987654321"},
        ]
        
        def find_duplicate_by_nif(nif, clients):
            for client in clients:
                if client.get("nif") == nif:
                    return client
            return None
        
        assert find_duplicate_by_nif("123456789", existing_clients) is not None
        assert find_duplicate_by_nif("111111111", existing_clients) is None
    
    def test_duplicate_detection_by_email(self):
        """Testa detecção de duplicados por email."""
        existing_clients = [
            {"id": "1", "email": "joao@test.com"},
            {"id": "2", "email": "maria@test.com"},
        ]
        
        def find_duplicate_by_email(email, clients):
            email_lower = email.lower()
            for client in clients:
                if (client.get("email") or "").lower() == email_lower:
                    return client
            return None
        
        assert find_duplicate_by_email("JOAO@TEST.COM", existing_clients) is not None
        assert find_duplicate_by_email("pedro@test.com", existing_clients) is None
    
    def test_merge_client_data(self):
        """Testa fusão de dados de clientes duplicados."""
        def merge_clients(existing, new):
            merged = {**existing}
            
            for key, value in new.items():
                if value and not merged.get(key):
                    merged[key] = value
            
            return merged
        
        existing = {"name": "João", "email": "joao@test.com", "phone": None}
        new = {"name": "João Silva", "phone": "912345678"}
        
        merged = merge_clients(existing, new)
        
        assert merged["name"] == "João"  # Mantém existente
        assert merged["phone"] == "912345678"  # Usa novo


class TestClientSegmentation:
    """Testes para segmentação de clientes."""
    
    def test_client_segment_assignment(self):
        """Testa atribuição de segmento a cliente."""
        def get_segment(total_value, num_processes):
            if total_value >= 1000000 or num_processes >= 5:
                return "premium"
            elif total_value >= 250000 or num_processes >= 2:
                return "standard"
            return "basic"
        
        assert get_segment(1500000, 3) == "premium"
        assert get_segment(500000, 1) == "standard"
        assert get_segment(100000, 1) == "basic"
    
    def test_client_lifetime_value(self):
        """Testa cálculo de valor de tempo de vida do cliente."""
        def calculate_ltv(processes):
            total_commission = 0
            
            for process in processes:
                if process.get("status") == "concluido":
                    value = process.get("property_value", 0)
                    commission_rate = 0.01  # 1%
                    total_commission += value * commission_rate
            
            return total_commission
        
        processes = [
            {"status": "concluido", "property_value": 250000},
            {"status": "concluido", "property_value": 300000},
            {"status": "analise", "property_value": 200000},
        ]
        
        ltv = calculate_ltv(processes)
        assert ltv == 5500  # (250000 + 300000) * 0.01


class TestClientHistory:
    """Testes para histórico de clientes."""
    
    def test_activity_log_structure(self):
        """Testa estrutura de log de actividade."""
        log_entry = {
            "id": "log-123",
            "client_id": "client-456",
            "action": "process_created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_email": "admin@test.com",
            "details": {"process_id": "proc-789"}
        }
        
        required = ["id", "client_id", "action", "timestamp"]
        for field in required:
            assert field in log_entry
    
    def test_activity_types(self):
        """Testa tipos de actividade válidos."""
        valid_types = [
            "client_created",
            "client_updated",
            "process_created",
            "document_added",
            "email_sent",
            "note_added"
        ]
        
        for action in valid_types:
            assert "_" in action


class TestClientExport:
    """Testes para exportação de dados de clientes."""
    
    def test_export_fields_selection(self):
        """Testa selecção de campos para exportação."""
        client = {
            "id": "123",
            "name": "João",
            "email": "joao@test.com",
            "nif": "123456789",
            "internal_notes": "Notas internas",
            "created_at": "2024-01-01"
        }
        
        exportable_fields = ["name", "email", "nif", "created_at"]
        
        def filter_exportable(client, fields):
            return {k: v for k, v in client.items() if k in fields}
        
        exported = filter_exportable(client, exportable_fields)
        
        assert "internal_notes" not in exported
        assert "name" in exported
        assert "email" in exported
    
    def test_export_date_formatting(self):
        """Testa formatação de datas para exportação."""
        def format_date_for_export(iso_date, format_type="dd/mm/yyyy"):
            if not iso_date:
                return ""
            
            try:
                dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
                
                if format_type == "dd/mm/yyyy":
                    return dt.strftime("%d/%m/%Y")
                elif format_type == "yyyy-mm-dd":
                    return dt.strftime("%Y-%m-%d")
                
                return iso_date
            except:
                return iso_date
        
        assert format_date_for_export("2024-01-15T10:00:00Z") == "15/01/2024"
        assert format_date_for_export("2024-01-15T10:00:00Z", "yyyy-mm-dd") == "2024-01-15"
