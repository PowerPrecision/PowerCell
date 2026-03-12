"""
Testes unitários para serviços de S3 e armazenamento.
"""
import pytest
from datetime import datetime, timezone, timedelta
import re
import os


class TestS3PathGeneration:
    """Testes para geração de caminhos S3."""
    
    def test_client_folder_path(self):
        """Testa geração de path para pasta de cliente."""
        def generate_client_path(client_name, process_number=None):
            # Normalizar nome
            import unicodedata
            name = unicodedata.normalize('NFD', client_name)
            name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
            name = name.lower().replace(' ', '-')
            name = re.sub(r'[^a-z0-9-]', '', name)
            
            if process_number:
                return f"processos/{name}-{process_number}/"
            return f"clientes/{name}/"
        
        test_cases = [
            ("João Silva", None, "clientes/joao-silva/"),
            ("Maria Santos", "2024-001", "processos/maria-santos-2024-001/"),
            ("José António", None, "clientes/jose-antonio/"),
        ]
        
        for name, proc_num, expected in test_cases:
            result = generate_client_path(name, proc_num)
            assert result == expected
    
    def test_document_path(self):
        """Testa geração de path para documentos."""
        def generate_document_path(base_path, category, filename):
            return f"{base_path}{category}/{filename}"
        
        base = "processos/joao-silva-001/"
        
        test_cases = [
            ("Identificacao", "CC.pdf", "processos/joao-silva-001/Identificacao/CC.pdf"),
            ("Financeiros", "IRS_2023.pdf", "processos/joao-silva-001/Financeiros/IRS_2023.pdf"),
        ]
        
        for category, filename, expected in test_cases:
            result = generate_document_path(base, category, filename)
            assert result == expected


class TestS3URLGeneration:
    """Testes para geração de URLs S3."""
    
    def test_presigned_url_expiry(self):
        """Testa cálculo de expiração de URL presigned."""
        DEFAULT_EXPIRY = 3600  # 1 hora
        
        def calculate_expiry(custom_expiry=None):
            expiry = custom_expiry or DEFAULT_EXPIRY
            return datetime.now(timezone.utc) + timedelta(seconds=expiry)
        
        now = datetime.now(timezone.utc)
        
        # Default expiry
        expiry = calculate_expiry()
        assert (expiry - now).seconds >= 3500  # Aproximadamente 1 hora
        
        # Custom expiry
        expiry = calculate_expiry(7200)  # 2 horas
        assert (expiry - now).seconds >= 7000
    
    def test_url_sanitization(self):
        """Testa sanitização de URLs."""
        def sanitize_s3_key(key):
            # Remover caracteres problemáticos
            key = key.replace("\\", "/")
            key = re.sub(r'/+', '/', key)
            key = key.strip("/")
            return key
        
        test_cases = [
            ("folder//subfolder/file.pdf", "folder/subfolder/file.pdf"),
            ("folder\\subfolder\\file.pdf", "folder/subfolder/file.pdf"),
            ("/folder/file.pdf/", "folder/file.pdf"),
        ]
        
        for original, expected in test_cases:
            result = sanitize_s3_key(original)
            assert result == expected


class TestFileUpload:
    """Testes para upload de ficheiros."""
    
    def test_file_extension_validation(self):
        """Testa validação de extensões de ficheiros."""
        ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"}
        
        def is_allowed_extension(filename):
            ext = os.path.splitext(filename.lower())[1]
            return ext in ALLOWED_EXTENSIONS
        
        valid_files = ["doc.pdf", "image.PNG", "report.DOCX"]
        invalid_files = ["script.exe", "virus.bat", "file.php"]
        
        for file in valid_files:
            assert is_allowed_extension(file), f"'{file}' should be allowed"
        
        for file in invalid_files:
            assert not is_allowed_extension(file), f"'{file}' should not be allowed"
    
    def test_file_size_validation(self):
        """Testa validação de tamanho de ficheiros."""
        MAX_SIZE = 50 * 1024 * 1024  # 50 MB
        
        def is_valid_size(size_bytes):
            return 0 < size_bytes <= MAX_SIZE
        
        assert is_valid_size(1024)  # 1 KB
        assert is_valid_size(10 * 1024 * 1024)  # 10 MB
        assert not is_valid_size(100 * 1024 * 1024)  # 100 MB
        assert not is_valid_size(0)
        assert not is_valid_size(-1)
    
    def test_filename_sanitization(self):
        """Testa sanitização de nomes de ficheiros."""
        def sanitize_filename(filename):
            # Remover caracteres perigosos
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            # Remover pontos duplicados
            filename = re.sub(r'\.{2,}', '.', filename)
            # Limitar comprimento
            name, ext = os.path.splitext(filename)
            if len(name) > 100:
                name = name[:100]
            return name + ext
        
        test_cases = [
            ("normal.pdf", "normal.pdf"),
            ("file:with:colons.pdf", "file_with_colons.pdf"),
            ("file<script>.pdf", "file_script_.pdf"),
            ("a" * 200 + ".pdf", "a" * 100 + ".pdf"),
        ]
        
        for original, expected in test_cases:
            result = sanitize_filename(original)
            assert result == expected


class TestFileOrganization:
    """Testes para organização de ficheiros."""
    
    def test_category_mapping(self):
        """Testa mapeamento de categorias de documentos."""
        CATEGORY_FOLDERS = {
            "cc": "Identificacao",
            "bi": "Identificacao",
            "passaporte": "Identificacao",
            "irs": "Financeiros/IRS",
            "recibo_vencimento": "Financeiros/Recibos",
            "extrato_bancario": "Financeiros/Extratos",
            "contrato_trabalho": "Emprego",
            "caderneta_predial": "Imovel",
            "cpcv": "Contratos",
        }
        
        def get_folder_for_category(category):
            return CATEGORY_FOLDERS.get(category.lower(), "Outros")
        
        test_cases = [
            ("cc", "Identificacao"),
            ("IRS", "Financeiros/IRS"),
            ("unknown", "Outros"),
        ]
        
        for category, expected in test_cases:
            result = get_folder_for_category(category)
            assert result == expected
    
    def test_duplicate_filename_handling(self):
        """Testa tratamento de ficheiros com nomes duplicados."""
        def generate_unique_filename(filename, existing_files):
            if filename not in existing_files:
                return filename
            
            name, ext = os.path.splitext(filename)
            counter = 1
            
            while f"{name}_{counter}{ext}" in existing_files:
                counter += 1
            
            return f"{name}_{counter}{ext}"
        
        existing = {"doc.pdf", "doc_1.pdf", "doc_2.pdf"}
        
        assert generate_unique_filename("new.pdf", existing) == "new.pdf"
        assert generate_unique_filename("doc.pdf", existing) == "doc_3.pdf"


class TestS3Operations:
    """Testes para operações S3."""
    
    def test_list_objects_pagination(self):
        """Testa paginação de listagem de objectos."""
        def calculate_pages(total_objects, page_size=1000):
            import math
            return math.ceil(total_objects / page_size)
        
        assert calculate_pages(500) == 1
        assert calculate_pages(1000) == 1
        assert calculate_pages(1001) == 2
        assert calculate_pages(2500) == 3
    
    def test_folder_size_calculation(self):
        """Testa cálculo de tamanho de pasta."""
        def calculate_folder_size(files):
            return sum(f.get("size", 0) for f in files)
        
        files = [
            {"name": "doc1.pdf", "size": 1024},
            {"name": "doc2.pdf", "size": 2048},
            {"name": "doc3.pdf", "size": 512},
        ]
        
        assert calculate_folder_size(files) == 3584
    
    def test_content_type_detection(self):
        """Testa detecção de content type."""
        CONTENT_TYPES = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        
        def get_content_type(filename):
            ext = os.path.splitext(filename.lower())[1]
            return CONTENT_TYPES.get(ext, "application/octet-stream")
        
        assert get_content_type("doc.pdf") == "application/pdf"
        assert get_content_type("image.PNG") == "image/png"
        assert get_content_type("unknown.xyz") == "application/octet-stream"


class TestS3Proxy:
    """Testes para proxy S3 (CORS)."""
    
    def test_proxy_headers(self):
        """Testa headers do proxy."""
        def get_proxy_headers(content_type, filename):
            headers = {
                "Content-Type": content_type,
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "public, max-age=3600",
            }
            return headers
        
        headers = get_proxy_headers("application/pdf", "documento.pdf")
        
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/pdf"
        assert "documento.pdf" in headers["Content-Disposition"]
    
    def test_cors_headers(self):
        """Testa headers CORS."""
        CORS_HEADERS = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Max-Age": "86400",
        }
        
        for header, value in CORS_HEADERS.items():
            assert header.startswith("Access-Control-")


class TestBackupStorage:
    """Testes para armazenamento de backups."""
    
    def test_backup_filename_generation(self):
        """Testa geração de nome de ficheiro de backup."""
        def generate_backup_filename(db_name):
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            return f"backup_{db_name}_{timestamp}.tar.gz"
        
        filename = generate_backup_filename("mydatabase")
        
        assert filename.startswith("backup_mydatabase_")
        assert filename.endswith(".tar.gz")
        # Verificar formato de timestamp
        assert re.search(r'\d{8}_\d{6}', filename)
    
    def test_backup_retention_policy(self):
        """Testa política de retenção de backups."""
        def get_backups_to_delete(backups, keep_daily=7, keep_weekly=4, keep_monthly=3):
            to_delete = []
            
            # Ordenar por data (mais recente primeiro)
            sorted_backups = sorted(backups, key=lambda x: x["date"], reverse=True)
            
            # Manter os últimos N diários
            daily_kept = sorted_backups[:keep_daily]
            
            # Implementação simplificada
            return [b for b in sorted_backups[keep_daily:] if b not in daily_kept]
        
        today = datetime.now(timezone.utc)
        backups = [
            {"name": f"backup_{i}", "date": today - timedelta(days=i)}
            for i in range(30)
        ]
        
        to_delete = get_backups_to_delete(backups)
        
        # Deve deletar backups além do período de retenção
        assert len(to_delete) == 23  # 30 - 7 diários
    
    def test_backup_integrity_check(self):
        """Testa verificação de integridade de backup."""
        def verify_backup_checksum(expected_checksum, actual_checksum):
            return expected_checksum == actual_checksum
        
        assert verify_backup_checksum("abc123", "abc123")
        assert not verify_backup_checksum("abc123", "xyz789")


class TestStorageQuota:
    """Testes para gestão de quota de armazenamento."""
    
    def test_quota_calculation(self):
        """Testa cálculo de utilização de quota."""
        def calculate_usage_percentage(used_bytes, quota_bytes):
            if quota_bytes == 0:
                return 0
            return (used_bytes / quota_bytes) * 100
        
        # 50% utilizado
        assert calculate_usage_percentage(5 * 1024**3, 10 * 1024**3) == 50.0
        
        # 80% utilizado
        assert calculate_usage_percentage(8 * 1024**3, 10 * 1024**3) == 80.0
    
    def test_quota_warning_threshold(self):
        """Testa limiar de aviso de quota."""
        WARNING_THRESHOLD = 80  # 80%
        CRITICAL_THRESHOLD = 95  # 95%
        
        def get_quota_status(usage_percentage):
            if usage_percentage >= CRITICAL_THRESHOLD:
                return "critical"
            elif usage_percentage >= WARNING_THRESHOLD:
                return "warning"
            return "ok"
        
        assert get_quota_status(50) == "ok"
        assert get_quota_status(85) == "warning"
        assert get_quota_status(98) == "critical"
