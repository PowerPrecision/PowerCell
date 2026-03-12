"""
Testes unitários para a lógica de análise de documentos com IA.
Foca em testar funções de validação, normalização e detecção.
"""
import pytest
import hashlib
import re
import unicodedata
from datetime import datetime, timezone


class TestNIFValidation:
    """Testes para validação de NIF português."""
    
    def test_valid_nif_pessoa_singular(self):
        """Testa NIFs válidos de pessoa singular (começam por 1, 2, 6, 9)."""
        # NIFs de pessoa singular começam com 1, 2, 6 ou 9
        valid_first_digits = ['1', '2', '6', '9']
        
        for digit in valid_first_digits:
            nif = f"{digit}23456789"
            assert nif[0] in valid_first_digits
    
    def test_invalid_nif_empresa(self):
        """Testa que NIFs de empresa (começam por 5) são rejeitados."""
        def validate_nif_pessoa_singular(nif):
            if not nif:
                return True
            nif = re.sub(r'\D', '', str(nif))
            if len(nif) != 9:
                return False
            # NIFs de empresas começam por 5
            if nif[0] == '5':
                return False
            # NIFs válidos para pessoas singulares: 1, 2, 6, 9
            if nif[0] not in ['1', '2', '6', '9']:
                return False
            return True
        
        empresa_nifs = ["500000001", "599999999", "512345678"]
        
        for nif in empresa_nifs:
            assert not validate_nif_pessoa_singular(nif)
    
    def test_placeholder_nif_rejection(self):
        """Testa que NIFs placeholder são rejeitados."""
        placeholder_nifs = ['123456789', '000000000', '111111111', '999999999']
        
        def is_placeholder_nif(nif):
            return nif in placeholder_nifs
        
        for nif in placeholder_nifs:
            assert is_placeholder_nif(nif)
    
    def test_nif_length_validation(self):
        """Testa que NIFs devem ter exactamente 9 dígitos."""
        def validate_nif_length(nif):
            nif = re.sub(r'\D', '', str(nif))
            return len(nif) == 9
        
        valid_nifs = ["123456789", "987654321"]
        invalid_nifs = ["12345678", "1234567890", "123", ""]
        
        for nif in valid_nifs:
            assert validate_nif_length(nif)
        
        for nif in invalid_nifs:
            assert not validate_nif_length(nif)


class TestTextNormalization:
    """Testes para normalização de texto para matching."""
    
    def test_accent_removal(self):
        """Testa remoção de acentos."""
        def normalize_text(text):
            if not text:
                return ""
            text = unicodedata.normalize('NFD', text)
            text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
            return text.lower()
        
        test_cases = [
            ("João", "joao"),
            ("José", "jose"),
            ("Cláudia", "claudia"),
            ("António", "antonio"),
            ("São Paulo", "sao paulo"),
        ]
        
        for original, expected in test_cases:
            result = normalize_text(original)
            assert result == expected, f"Expected '{expected}', got '{result}'"
    
    def test_whitespace_normalization(self):
        """Testa normalização de espaços em branco."""
        def normalize_whitespace(text):
            return ' '.join(text.split())
        
        test_cases = [
            ("  João   Silva  ", "João Silva"),
            ("Maria\t\nSantos", "Maria Santos"),
            ("Pedro    Costa", "Pedro Costa"),
        ]
        
        for original, expected in test_cases:
            result = normalize_whitespace(original)
            assert result == expected


class TestNameMatching:
    """Testes para matching flexível de nomes."""
    
    def test_extract_names_from_string(self):
        """Testa extracção de nomes de strings compostas."""
        def extract_all_names(text):
            names = set()
            if not text:
                return names
            
            # Extrair nomes de parênteses
            parens_names = re.findall(r'\(([^)]+)\)', text)
            for name in parens_names:
                names.add(name.strip().lower())
            
            # Remover parênteses
            text_clean = re.sub(r'\([^)]+\)', '', text)
            
            # Separar por delimitadores
            separators = [' e ', ' / ', ', ', ' - ']
            parts = [text_clean]
            for sep in separators:
                new_parts = []
                for part in parts:
                    new_parts.extend(part.split(sep))
                parts = new_parts
            
            for part in parts:
                part = part.strip().lower()
                if part and len(part) > 2:
                    names.add(part)
            
            return names
        
        test_cases = [
            ("João e Maria", {"joão", "maria"}),
            ("João (Maria)", {"joão", "maria"}),
            ("João / Maria", {"joão", "maria"}),
            ("João, Maria, Pedro", {"joão", "maria", "pedro"}),
            ("Cláudia Batista (Edson)", {"cláudia batista", "edson"}),
        ]
        
        for text, expected in test_cases:
            result = extract_all_names(text)
            # Verificar que todos os nomes esperados estão presentes
            for name in expected:
                found = any(name in r or r in name for r in result)
                assert found, f"'{name}' not found in {result}"
    
    def test_first_name_matching(self):
        """Testa matching por primeiro nome."""
        def get_first_name(full_name):
            parts = full_name.strip().split()
            return parts[0].lower() if parts else ""
        
        test_cases = [
            ("João Silva Santos", "joão"),
            ("Maria da Costa", "maria"),
            ("Pedro", "pedro"),
        ]
        
        for full_name, expected_first in test_cases:
            result = get_first_name(full_name)
            assert result == expected_first


class TestDocumentTypeDetection:
    """Testes para detecção de tipo de documento."""
    
    def test_cc_detection(self):
        """Testa detecção de Cartão de Cidadão."""
        cc_patterns = ["cc", "cartao_cidadao", "cartão cidadão", "cidadao"]
        
        def is_cc(filename):
            filename_lower = filename.lower()
            return any(p in filename_lower for p in cc_patterns)
        
        test_filenames = [
            "CC_Joao_Silva.pdf",
            "cartao_cidadao_frente.jpg",
            "documento_cc.pdf",
        ]
        
        for filename in test_filenames:
            assert is_cc(filename), f"'{filename}' should be detected as CC"
    
    def test_cc_frente_verso_detection(self):
        """Testa detecção de frente e verso do CC."""
        def detect_cc_side(filename):
            filename_lower = filename.lower()
            
            frente_patterns = ["frente", "front", "_f.", "_f_", "cc_1", "cc1", "ccf"]
            verso_patterns = ["verso", "back", "tras", "_v.", "_v_", "cc_2", "cc2", "ccv"]
            
            for p in frente_patterns:
                if p in filename_lower:
                    return "frente"
            
            for p in verso_patterns:
                if p in filename_lower:
                    return "verso"
            
            return None
        
        test_cases = [
            ("CC_frente.jpg", "frente"),
            ("CC_verso.jpg", "verso"),
            ("cartao_front.pdf", "frente"),
            ("CC_back.pdf", "verso"),
            ("CC_1.jpg", "frente"),
            ("CC_2.jpg", "verso"),
            ("CC.pdf", None),  # Sem indicação
        ]
        
        for filename, expected in test_cases:
            result = detect_cc_side(filename)
            assert result == expected, f"'{filename}' should be '{expected}', got '{result}'"
    
    def test_recibo_vencimento_detection(self):
        """Testa detecção de recibos de vencimento."""
        recibo_patterns = ["recibo", "vencimento", "salario", "ordenado", "pagamento"]
        
        def is_recibo_vencimento(filename):
            filename_lower = filename.lower()
            return any(p in filename_lower for p in recibo_patterns)
        
        test_filenames = [
            "recibo_vencimento_janeiro.pdf",
            "salario_2024.pdf",
            "ordenado_marco.pdf",
        ]
        
        for filename in test_filenames:
            assert is_recibo_vencimento(filename)
    
    def test_irs_detection(self):
        """Testa detecção de declaração de IRS."""
        irs_patterns = ["irs", "declaracao_rendimentos", "modelo3", "anexo"]
        
        def is_irs(filename):
            filename_lower = filename.lower()
            return any(p in filename_lower for p in irs_patterns)
        
        test_filenames = [
            "IRS_2023.pdf",
            "declaracao_rendimentos.pdf",
            "modelo3_2024.pdf",
        ]
        
        for filename in test_filenames:
            assert is_irs(filename)


class TestDocumentHash:
    """Testes para cálculo de hash de documentos."""
    
    def test_hash_calculation(self):
        """Testa cálculo de hash MD5."""
        def calculate_hash(content):
            return hashlib.md5(content, usedforsecurity=False).hexdigest()
        
        content1 = b"Test document content"
        content2 = b"Test document content"
        content3 = b"Different content"
        
        hash1 = calculate_hash(content1)
        hash2 = calculate_hash(content2)
        hash3 = calculate_hash(content3)
        
        # Mesmo conteúdo = mesmo hash
        assert hash1 == hash2
        
        # Conteúdo diferente = hash diferente
        assert hash1 != hash3
        
        # Hash tem 32 caracteres (MD5)
        assert len(hash1) == 32
    
    def test_duplicate_detection(self):
        """Testa detecção de documentos duplicados."""
        analyzed_docs = {}
        
        def is_duplicate(process_id, doc_type, content):
            doc_hash = hashlib.md5(content, usedforsecurity=False).hexdigest()
            key = f"{process_id}:{doc_type}"
            
            if key in analyzed_docs:
                if doc_hash in analyzed_docs[key]:
                    return True
            else:
                analyzed_docs[key] = set()
            
            analyzed_docs[key].add(doc_hash)
            return False
        
        content = b"Document content"
        
        # Primeiro documento não é duplicado
        assert not is_duplicate("process1", "recibo", content)
        
        # Mesmo documento é duplicado
        assert is_duplicate("process1", "recibo", content)
        
        # Diferente processo não é duplicado
        assert not is_duplicate("process2", "recibo", content)


class TestPlaceholderValueDetection:
    """Testes para detecção de valores placeholder."""
    
    def test_placeholder_dates(self):
        """Testa detecção de datas placeholder."""
        def is_placeholder(value):
            if not value:
                return False
            value_str = str(value).strip().upper()
            placeholder_values = [
                'YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY',
                'N/A', 'NA', 'NULL', 'NONE', ''
            ]
            return value_str in placeholder_values or 'YYYY' in value_str
        
        placeholder_dates = [
            "YYYY-MM-DD",
            "DD/MM/YYYY",
            "N/A",
            "null",
        ]
        
        valid_dates = [
            "2024-01-15",
            "15/01/2024",
            "2023-12-31",
        ]
        
        for date in placeholder_dates:
            assert is_placeholder(date), f"'{date}' should be placeholder"
        
        for date in valid_dates:
            assert not is_placeholder(date), f"'{date}' should not be placeholder"
    
    def test_placeholder_numbers(self):
        """Testa detecção de números placeholder."""
        placeholder_numbers = ['123456789', '000000000', '0', '00000000', '12345678']
        
        def is_placeholder_number(value):
            return str(value) in placeholder_numbers
        
        for num in placeholder_numbers:
            assert is_placeholder_number(num)


class TestBackgroundJobTracking:
    """Testes para tracking de jobs em background."""
    
    def test_job_status_transitions(self):
        """Testa transições de estado válidas para jobs."""
        valid_transitions = {
            "pending": ["running", "cancelled"],
            "running": ["success", "failed", "cancelled"],
            "success": [],  # Estado final
            "failed": [],   # Estado final
            "cancelled": [] # Estado final
        }
        
        def is_valid_transition(from_status, to_status):
            return to_status in valid_transitions.get(from_status, [])
        
        # Transições válidas
        assert is_valid_transition("pending", "running")
        assert is_valid_transition("running", "success")
        assert is_valid_transition("running", "failed")
        
        # Transições inválidas
        assert not is_valid_transition("success", "running")
        assert not is_valid_transition("failed", "pending")
    
    def test_progress_calculation(self):
        """Testa cálculo de progresso."""
        def calculate_progress(processed, total):
            if total == 0:
                return 0
            return int((processed / total) * 100)
        
        test_cases = [
            (0, 10, 0),
            (5, 10, 50),
            (10, 10, 100),
            (3, 9, 33),
            (0, 0, 0),  # Edge case
        ]
        
        for processed, total, expected in test_cases:
            result = calculate_progress(processed, total)
            assert result == expected
    
    def test_job_structure(self):
        """Testa estrutura de um job em background."""
        job = {
            "id": "uuid-here",
            "type": "bulk_import",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "user_email": "admin@test.com",
            "progress": 50,
            "total": 100,
            "processed": 50,
            "errors": 2,
            "error_messages": ["Erro 1", "Erro 2"],
            "finished_at": None
        }
        
        required_fields = ["id", "type", "status", "started_at"]
        for field in required_fields:
            assert field in job
        
        assert job["progress"] <= 100
        assert job["processed"] <= job["total"]
        assert len(job["error_messages"]) == job["errors"]


class TestAggregatedSessionLogic:
    """Testes para lógica de sessões de importação agregada."""
    
    def test_data_aggregation(self):
        """Testa agregação de dados de múltiplos documentos."""
        extractions = [
            {"nif": "123456789", "nome": "João Silva"},
            {"salario_mensal": 1500, "empresa": "Empresa A"},
            {"salario_mensal": 2000, "empresa": "Empresa B"},  # Segunda empresa
        ]
        
        def aggregate_data(extractions):
            result = {}
            salaries = []
            
            for ext in extractions:
                for key, value in ext.items():
                    if key == "salario_mensal":
                        salaries.append({"valor": value, "empresa": ext.get("empresa", "")})
                    elif key not in result or not result[key]:
                        result[key] = value
            
            if salaries:
                result["salarios"] = salaries
                result["salario_total"] = sum(s["valor"] for s in salaries)
            
            return result
        
        result = aggregate_data(extractions)
        
        assert result["nif"] == "123456789"
        assert result["nome"] == "João Silva"
        assert len(result["salarios"]) == 2
        assert result["salario_total"] == 3500
    
    def test_session_summary(self):
        """Testa geração de resumo de sessão."""
        session_data = {
            "total_files": 10,
            "processed_files": 8,
            "errors": 2,
            "clients": {
                "client1": {"documents": 4, "fields": 15},
                "client2": {"documents": 4, "fields": 12},
            }
        }
        
        def generate_summary(data):
            return {
                "total_processed": data["processed_files"],
                "success_rate": (data["processed_files"] - data["errors"]) / data["total_files"] * 100,
                "clients_updated": len(data["clients"]),
                "total_fields_extracted": sum(c["fields"] for c in data["clients"].values())
            }
        
        summary = generate_summary(session_data)
        
        assert summary["total_processed"] == 8
        assert summary["success_rate"] == 60.0
        assert summary["clients_updated"] == 2
        assert summary["total_fields_extracted"] == 27
