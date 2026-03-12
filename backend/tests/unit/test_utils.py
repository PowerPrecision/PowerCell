"""
Testes unitários para utilitários diversos.
"""
import pytest
import re
from datetime import datetime, timezone, timedelta
import hashlib


class TestDateUtils:
    """Testes para utilitários de datas."""
    
    def test_iso_date_parsing(self):
        """Testa parsing de datas ISO."""
        def parse_iso_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except:
                return None
        
        valid_dates = [
            "2024-01-15T10:30:00Z",
            "2024-01-15T10:30:00+00:00",
            "2024-01-15"
        ]
        
        for date in valid_dates:
            result = parse_iso_date(date)
            assert result is not None
        
        assert parse_iso_date("invalid") is None
        assert parse_iso_date(None) is None
    
    def test_date_formatting(self):
        """Testa formatação de datas."""
        def format_date(dt, format_str="%d/%m/%Y"):
            if not dt:
                return ""
            return dt.strftime(format_str)
        
        dt = datetime(2024, 1, 15, 10, 30)
        
        assert format_date(dt) == "15/01/2024"
        assert format_date(dt, "%Y-%m-%d") == "2024-01-15"
        assert format_date(dt, "%d %b %Y") == "15 Jan 2024"
    
    def test_relative_time(self):
        """Testa cálculo de tempo relativo."""
        def get_relative_time(dt, reference=None):
            if reference is None:
                reference = datetime.now(timezone.utc)
            
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            
            diff = reference - dt
            
            if diff.days > 365:
                return f"{diff.days // 365} anos"
            elif diff.days > 30:
                return f"{diff.days // 30} meses"
            elif diff.days > 0:
                return f"{diff.days} dias"
            elif diff.seconds > 3600:
                return f"{diff.seconds // 3600} horas"
            elif diff.seconds > 60:
                return f"{diff.seconds // 60} minutos"
            return "agora"
        
        now = datetime.now(timezone.utc)
        
        assert get_relative_time(now - timedelta(days=5), now) == "5 dias"
        assert get_relative_time(now - timedelta(hours=3), now) == "3 horas"
        assert get_relative_time(now - timedelta(minutes=30), now) == "30 minutos"
    
    def test_business_days_calculation(self):
        """Testa cálculo de dias úteis."""
        def add_business_days(start_date, days):
            current = start_date
            added = 0
            
            while added < days:
                current += timedelta(days=1)
                # Sábado = 5, Domingo = 6
                if current.weekday() < 5:
                    added += 1
            
            return current
        
        # Segunda-feira + 5 dias úteis = Segunda seguinte
        monday = datetime(2024, 1, 15)  # Segunda-feira
        result = add_business_days(monday, 5)
        assert result.weekday() == 0  # Segunda-feira


class TestStringUtils:
    """Testes para utilitários de strings."""
    
    def test_slug_generation(self):
        """Testa geração de slugs."""
        import unicodedata
        
        def slugify(text):
            if not text:
                return ""
            # Remover acentos
            text = unicodedata.normalize('NFD', text)
            text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
            # Converter para minúsculas
            text = text.lower()
            # Substituir espaços e caracteres especiais
            text = re.sub(r'[^\w\s-]', '', text)
            text = re.sub(r'[-\s]+', '-', text)
            return text.strip('-')
        
        assert slugify("João Silva") == "joao-silva"
        assert slugify("Processo N 123") == "processo-n-123"
        assert slugify("  Teste  ") == "teste"
    
    def test_truncation(self):
        """Testa truncagem de strings."""
        def truncate(text, max_length, suffix="..."):
            if not text or len(text) <= max_length:
                return text
            return text[:max_length - len(suffix)] + suffix
        
        assert truncate("Hello World", 20) == "Hello World"
        assert truncate("Hello World", 8) == "Hello..."
        assert truncate("Hello World", 8, "…") == "Hello W…"
    
    def test_capitalize_words(self):
        """Testa capitalização de palavras."""
        def capitalize_words(text, exceptions=None):
            if not text:
                return ""
            
            exceptions = exceptions or ["de", "da", "do", "e", "em"]
            words = text.lower().split()
            
            result = []
            for i, word in enumerate(words):
                if i == 0 or word not in exceptions:
                    result.append(word.capitalize())
                else:
                    result.append(word)
            
            return " ".join(result)
        
        assert capitalize_words("joao da silva") == "Joao da Silva"
        assert capitalize_words("MARIA DE SANTOS") == "Maria de Santos"


class TestNumberUtils:
    """Testes para utilitários de números."""
    
    def test_currency_formatting(self):
        """Testa formatação de moeda."""
        def format_currency(value, currency="EUR"):
            if value is None:
                return ""
            
            formatted = f"{value:,.2f}"
            formatted = formatted.replace(",", " ").replace(".", ",")
            
            if currency == "EUR":
                return f"{formatted} €"
            return f"{formatted} {currency}"
        
        assert format_currency(1234567.89) == "1 234 567,89 €"
        assert format_currency(1000) == "1 000,00 €"
        assert format_currency(99.9) == "99,90 €"
    
    def test_percentage_calculation(self):
        """Testa cálculo de percentagem."""
        def calculate_percentage(part, total, decimal_places=1):
            if total == 0:
                return 0
            return round((part / total) * 100, decimal_places)
        
        assert calculate_percentage(25, 100) == 25.0
        assert calculate_percentage(1, 3) == 33.3
        assert calculate_percentage(0, 100) == 0
        assert calculate_percentage(50, 0) == 0
    
    def test_size_formatting(self):
        """Testa formatação de tamanhos de ficheiros."""
        def format_size(bytes_size):
            if bytes_size == 0:
                return "0 B"
            
            units = ['B', 'KB', 'MB', 'GB', 'TB']
            i = 0
            
            while bytes_size >= 1024 and i < len(units) - 1:
                bytes_size /= 1024
                i += 1
            
            return f"{bytes_size:.1f} {units[i]}"
        
        assert format_size(500) == "500.0 B"
        assert format_size(1024) == "1.0 KB"
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"


class TestHashUtils:
    """Testes para utilitários de hash."""
    
    def test_md5_hash(self):
        """Testa geração de hash MD5."""
        def md5_hash(data):
            if isinstance(data, str):
                data = data.encode()
            return hashlib.md5(data, usedforsecurity=False).hexdigest()
        
        hash1 = md5_hash("test")
        hash2 = md5_hash("test")
        hash3 = md5_hash("different")
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 32
    
    def test_sha256_hash(self):
        """Testa geração de hash SHA256."""
        def sha256_hash(data):
            if isinstance(data, str):
                data = data.encode()
            return hashlib.sha256(data).hexdigest()
        
        hash1 = sha256_hash("test")
        assert len(hash1) == 64
    
    def test_unique_id_generation(self):
        """Testa geração de IDs únicos."""
        import uuid
        
        def generate_id(prefix=""):
            id_str = str(uuid.uuid4())
            if prefix:
                return f"{prefix}-{id_str}"
            return id_str
        
        id1 = generate_id()
        id2 = generate_id()
        id3 = generate_id("proc")
        
        assert id1 != id2
        assert id3.startswith("proc-")


class TestValidationUtils:
    """Testes para utilitários de validação."""
    
    def test_url_validation(self):
        """Testa validação de URLs."""
        def is_valid_url(url):
            pattern = r'^https?://[^\s<>"\{\}|\\^`\[\]]+$'
            return bool(re.match(pattern, url)) if url else False
        
        valid = [
            "https://example.com",
            "http://test.com/path?query=1",
            "https://sub.domain.co.uk/path"
        ]
        
        invalid = ["invalid", "ftp://test.com", "//missing-protocol.com"]
        
        for url in valid:
            assert is_valid_url(url)
        for url in invalid:
            assert not is_valid_url(url)
    
    def test_postal_code_validation(self):
        """Testa validação de código postal português."""
        def is_valid_postal_code(code):
            pattern = r'^\d{4}-\d{3}$'
            return bool(re.match(pattern, code)) if code else False
        
        valid = ["1000-001", "4000-123", "9999-999"]
        invalid = ["1000001", "100-001", "1000-01"]
        
        for code in valid:
            assert is_valid_postal_code(code)
        for code in invalid:
            assert not is_valid_postal_code(code)
    
    def test_iban_validation(self):
        """Testa validação básica de IBAN."""
        def is_valid_iban_format(iban):
            if not iban:
                return False
            # Remover espaços
            iban = iban.replace(" ", "").upper()
            # IBAN português: PT50 + 23 dígitos = 25 caracteres
            return iban.startswith("PT") and len(iban) == 25
        
        valid = ["PT50 0002 0123 1234 5678 9015 4", "PT50000201231234567890154"]
        invalid = ["PT12345", "ES50000201231234567890154", ""]
        
        for iban in valid:
            assert is_valid_iban_format(iban)
        for iban in invalid:
            assert not is_valid_iban_format(iban)


class TestSanitizationUtils:
    """Testes para utilitários de sanitização."""
    
    def test_html_escape(self):
        """Testa escape de HTML."""
        def escape_html(text):
            if not text:
                return ""
            
            replacements = [
                ("&", "&amp;"),
                ("<", "&lt;"),
                (">", "&gt;"),
                ('"', "&quot;"),
                ("'", "&#x27;")
            ]
            
            for old, new in replacements:
                text = text.replace(old, new)
            
            return text
        
        assert escape_html("<script>alert('xss')</script>") == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
        assert escape_html('Test "quoted"') == 'Test &quot;quoted&quot;'
    
    def test_strip_html_tags(self):
        """Testa remoção de tags HTML."""
        def strip_html(text):
            if not text:
                return ""
            return re.sub(r'<[^>]+>', '', text)
        
        assert strip_html("<p>Hello</p>") == "Hello"
        assert strip_html("<b>Bold</b> text") == "Bold text"
        assert strip_html("No tags") == "No tags"
    
    def test_normalize_whitespace(self):
        """Testa normalização de espaços em branco."""
        def normalize_whitespace(text):
            if not text:
                return ""
            return ' '.join(text.split())
        
        assert normalize_whitespace("  Hello   World  ") == "Hello World"
        assert normalize_whitespace("Tab\there") == "Tab here"
        assert normalize_whitespace("Line\nbreak") == "Line break"
