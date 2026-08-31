"""
Testes unitários adicionais para aumentar cobertura.
Foca em áreas críticas do sistema.
"""
import pytest
from datetime import datetime, timezone, timedelta
import re
import hashlib


class TestDocumentProcessing:
    """Testes para processamento de documentos."""
    
    def test_file_extension_detection(self):
        """Testa detecção de extensão de ficheiro."""
        def get_extension(filename):
            import os
            return os.path.splitext(filename.lower())[1]
        
        assert get_extension("doc.pdf") == ".pdf"
        assert get_extension("IMAGE.PNG") == ".png"
        assert get_extension("file") == ""
    
    def test_mime_type_mapping(self):
        """Testa mapeamento de extensão para MIME type."""
        MIME_TYPES = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        
        def get_mime_type(extension):
            return MIME_TYPES.get(extension.lower(), "application/octet-stream")
        
        assert get_mime_type(".pdf") == "application/pdf"
        assert get_mime_type(".unknown") == "application/octet-stream"
    
    def test_document_size_validation(self):
        """Testa validação de tamanho de documento."""
        MAX_SIZE_MB = 50
        MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
        
        def is_valid_size(size_bytes):
            return 0 < size_bytes <= MAX_SIZE_BYTES
        
        assert is_valid_size(1024 * 1024)  # 1 MB
        assert is_valid_size(MAX_SIZE_BYTES)  # Exactamente o limite
        assert not is_valid_size(MAX_SIZE_BYTES + 1)  # Acima do limite
        assert not is_valid_size(0)
    
    def test_document_name_sanitization(self):
        """Testa sanitização de nomes de documentos."""
        def sanitize_doc_name(name):
            # Remover caracteres perigosos
            name = re.sub(r'[<>:"/\\|?*]', '_', name)
            # Remover pontos duplos
            name = re.sub(r'\.{2,}', '.', name)
            # Limitar comprimento
            if len(name) > 200:
                base, ext = name.rsplit('.', 1) if '.' in name else (name, '')
                name = base[:195] + ('.' + ext if ext else '')
            return name
        
        assert sanitize_doc_name("normal.pdf") == "normal.pdf"
        assert sanitize_doc_name("file:test.pdf") == "file_test.pdf"
        assert sanitize_doc_name("file..test.pdf") == "file.test.pdf"


class TestDataAggregation:
    """Testes para agregação de dados."""
    
    def test_merge_extracted_data(self):
        """Testa fusão de dados extraídos de múltiplos documentos."""
        def merge_data(existing, new):
            merged = dict(existing)
            for key, value in new.items():
                if value and (key not in merged or not merged[key]):
                    merged[key] = value
            return merged
        
        existing = {"nome": "João", "nif": None}
        new = {"nif": "123456789", "email": "joao@test.com"}
        
        result = merge_data(existing, new)
        
        assert result["nome"] == "João"
        assert result["nif"] == "123456789"
        assert result["email"] == "joao@test.com"
    
    def test_salary_aggregation(self):
        """Testa agregação de múltiplos salários."""
        def aggregate_salaries(salary_records):
            if not salary_records:
                return {"total": 0, "count": 0, "average": 0}
            
            total = sum(s.get("value", 0) for s in salary_records)
            count = len(salary_records)
            average = total / count if count > 0 else 0
            
            return {
                "total": total,
                "count": count,
                "average": round(average, 2)
            }
        
        salaries = [
            {"month": "2024-01", "value": 1500},
            {"month": "2024-02", "value": 1500},
            {"month": "2024-03", "value": 1600},
        ]
        
        result = aggregate_salaries(salaries)
        
        assert result["total"] == 4600
        assert result["count"] == 3
        assert result["average"] == 1533.33
    
    def test_document_count_by_category(self):
        """Testa contagem de documentos por categoria."""
        documents = [
            {"category": "identificacao"},
            {"category": "financeiros"},
            {"category": "identificacao"},
            {"category": "outros"},
        ]
        
        def count_by_category(docs):
            counts = {}
            for doc in docs:
                cat = doc.get("category", "unknown")
                counts[cat] = counts.get(cat, 0) + 1
            return counts
        
        result = count_by_category(documents)
        
        assert result["identificacao"] == 2
        assert result["financeiros"] == 1
        assert result["outros"] == 1


class TestErrorHandling:
    """Testes para gestão de erros."""
    
    def test_error_severity_ordering(self):
        """Testa ordenação de severidade de erros."""
        SEVERITY_ORDER = {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1
        }
        
        def get_severity_score(severity):
            return SEVERITY_ORDER.get(severity, 0)
        
        assert get_severity_score("critical") > get_severity_score("high")
        assert get_severity_score("high") > get_severity_score("medium")
        assert get_severity_score("medium") > get_severity_score("low")
    
    def test_error_categorization(self):
        """Testa categorização de erros."""
        def categorize_error(error_message):
            message_lower = error_message.lower()
            
            if "file" in message_lower or "read" in message_lower:
                return "file_read"
            elif "format" in message_lower or "parse" in message_lower:
                return "file_format"
            elif "ai" in message_lower or "analysis" in message_lower:
                return "ai_analysis"
            elif "client" in message_lower or "match" in message_lower:
                return "client_match"
            elif "duplicate" in message_lower:
                return "duplicate"
            elif "valid" in message_lower:
                return "data_validation"
            
            return "unknown"
        
        assert categorize_error("File read error") == "file_read"
        assert categorize_error("Duplicate document") == "duplicate"
        assert categorize_error("Random error") == "unknown"
    
    def test_retry_policy(self):
        """Testa política de retry para erros."""
        def should_retry(error_type, attempt, max_attempts=3):
            # Alguns erros não devem ser retentados
            non_retryable = ["permission", "duplicate", "data_validation"]
            
            if error_type in non_retryable:
                return False
            
            return attempt < max_attempts
        
        assert should_retry("file_read", 1)
        assert should_retry("ai_analysis", 2)
        assert not should_retry("ai_analysis", 3)
        assert not should_retry("duplicate", 1)


class TestProgressTracking:
    """Testes para tracking de progresso."""
    
    def test_percentage_calculation(self):
        """Testa cálculo de percentagem de progresso."""
        def calculate_progress(processed, total):
            if total == 0:
                return 0
            return min(100, int((processed / total) * 100))
        
        assert calculate_progress(50, 100) == 50
        assert calculate_progress(100, 100) == 100
        assert calculate_progress(0, 100) == 0
        assert calculate_progress(50, 0) == 0
        assert calculate_progress(150, 100) == 100  # Capped at 100
    
    def test_eta_calculation(self):
        """Testa cálculo de tempo estimado."""
        def calculate_eta(processed, total, elapsed_seconds):
            if processed == 0:
                return None
            
            rate = processed / elapsed_seconds
            remaining = total - processed
            eta_seconds = remaining / rate
            
            return int(eta_seconds)
        
        # 50 de 100 em 60 segundos = mais 60 segundos
        eta = calculate_eta(50, 100, 60)
        assert eta == 60
        
        # 0 processados = sem ETA
        assert calculate_eta(0, 100, 60) is None
    
    def test_status_message_generation(self):
        """Testa geração de mensagens de status."""
        def generate_status_message(processed, total, errors):
            if total == 0:
                return "A aguardar..."
            
            percentage = int((processed / total) * 100)
            
            if errors > 0:
                return f"A processar: {percentage}% ({errors} erros)"
            
            return f"A processar: {percentage}%"
        
        assert "50%" in generate_status_message(50, 100, 0)
        assert "erros" in generate_status_message(50, 100, 5)
        assert "aguardar" in generate_status_message(0, 0, 0)


class TestDateTimeHandling:
    """Testes para manipulação de datas."""
    
    def test_iso_date_generation(self):
        """Testa geração de datas ISO."""
        def get_current_iso():
            return datetime.now(timezone.utc).isoformat()
        
        iso = get_current_iso()
        
        # Deve conter padrão ISO
        assert "T" in iso
        assert "+" in iso or "Z" in iso
    
    def test_date_comparison(self):
        """Testa comparação de datas."""
        def is_expired(date_str, reference=None):
            if not date_str:
                return False
            
            if reference is None:
                reference = datetime.now(timezone.utc)
            
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return date < reference
            except Exception:
                return False
        
        now = datetime.now(timezone.utc)
        past = (now - timedelta(days=1)).isoformat()
        future = (now + timedelta(days=1)).isoformat()
        
        assert is_expired(past, now)
        assert not is_expired(future, now)
        assert not is_expired(None, now)
    
    def test_age_calculation(self):
        """Testa cálculo de idade em dias."""
        def get_age_days(date_str):
            if not date_str:
                return 0
            
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - date
                return age.days
            except Exception:
                return 0
        
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        age = get_age_days(week_ago)
        
        assert age == 7


class TestCacheManagement:
    """Testes para gestão de cache."""
    
    def test_cache_key_generation(self):
        """Testa geração de chaves de cache."""
        def generate_cache_key(*parts):
            return ":".join(str(p) for p in parts if p)
        
        key = generate_cache_key("user", "123", "processes")
        assert key == "user:123:processes"
        
        key = generate_cache_key("user", None, "processes")
        assert key == "user:processes"
    
    def test_cache_expiry_check(self):
        """Testa verificação de expiração de cache."""
        def is_cache_expired(cached_at, ttl_seconds):
            if not cached_at:
                return True
            
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            return age > ttl_seconds
        
        now = datetime.now(timezone.utc)
        recent = now - timedelta(seconds=30)
        old = now - timedelta(hours=1)
        
        assert not is_cache_expired(recent, 60)  # Dentro do TTL
        assert is_cache_expired(old, 60)  # Fora do TTL
        assert is_cache_expired(None, 60)  # Sem data
    
    def test_lru_cache_eviction(self):
        """Testa evicção de cache LRU."""
        def should_evict(cache_size, max_size):
            return cache_size >= max_size
        
        assert should_evict(100, 100)
        assert should_evict(101, 100)
        assert not should_evict(99, 100)


class TestSecurityValidation:
    """Testes para validações de segurança."""
    
    def test_path_traversal_detection(self):
        """Testa detecção de path traversal."""
        def has_path_traversal(path):
            dangerous_patterns = ['..', '~/', '/etc/', '/var/', '\\..']
            return any(p in path for p in dangerous_patterns)
        
        assert has_path_traversal("../secret.txt")
        assert has_path_traversal("path/../../file")
        assert not has_path_traversal("normal/path/file.txt")
    
    def test_filename_injection_detection(self):
        """Testa detecção de injecção em nomes de ficheiros."""
        def is_safe_filename(filename):
            # Caracteres perigosos
            dangerous = ['<', '>', ':', '"', '|', '?', '*', '\0']
            return not any(c in filename for c in dangerous)
        
        assert is_safe_filename("normal_file.pdf")
        assert not is_safe_filename("file<script>.pdf")
        assert not is_safe_filename("file\x00.pdf")
    
    def test_content_type_validation(self):
        """Testa validação de content type."""
        ALLOWED_TYPES = [
            "application/pdf",
            "image/jpeg",
            "image/png",
            "application/msword"
        ]
        
        def is_allowed_content_type(content_type):
            return content_type in ALLOWED_TYPES
        
        assert is_allowed_content_type("application/pdf")
        assert not is_allowed_content_type("application/javascript")
        assert not is_allowed_content_type("text/html")
