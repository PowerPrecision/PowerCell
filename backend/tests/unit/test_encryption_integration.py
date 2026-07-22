"""
Testes de Integração de Encriptação

Testa se a encriptação de campos sensíveis está a funcionar corretamente
nos endpoints de processos e clientes.
"""
import pytest
import os
import sys

# Adicionar o diretório backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.encryption import encryption_service, encrypt_value, decrypt_value, is_encrypted


class TestEncryptionService:
    """Testes do serviço de encriptação."""
    
    def test_encrypt_decrypt_string(self):
        """Testa encriptação e desencriptação de uma string."""
        original = "123456789"  # NIF exemplo
        
        encrypted = encrypt_value(original)
        
        # Verificar que foi encriptado
        assert encrypted != original
        assert is_encrypted(encrypted)
        
        # Verificar que pode ser desencriptado
        decrypted = decrypt_value(encrypted)
        assert decrypted == original
    
    def test_encrypt_empty_value(self):
        """Testa encriptação de valor vazio."""
        assert encrypt_value("") == ""
        assert encrypt_value(None) is None
    
    def test_encrypt_already_encrypted(self):
        """Testa que não re-encripta valores já encriptados."""
        original = "987654321"
        encrypted1 = encrypt_value(original)
        encrypted2 = encrypt_value(encrypted1)
        
        # Devem ser iguais (não re-encriptados)
        assert encrypted1 == encrypted2
    
    def test_decrypt_unencrypted_value(self):
        """Testa que desencripta valores não encriptados retorna o mesmo."""
        original = "plain_text"
        decrypted = decrypt_value(original)
        
        assert decrypted == original
    
    def test_encryption_prefix(self):
        """Testa que o prefixo de encriptação está presente."""
        original = "123456789"
        encrypted = encrypt_value(original)
        
        assert encrypted.startswith("ENC:")


class TestProcessEncryption:
    """Testes de encriptação em processos."""
    
    def test_encrypt_process_data(self):
        """Testa encriptação de dados de processo."""
        from services.process_service import encrypt_sensitive_data, decrypt_sensitive_data
        
        process = {
            "id": "test-123",
            "client_name": "João Silva",
            "client_phone": "912345678",
            "personal_data": {
                "nif": "123456789",
                "nome": "João Silva",
                "morada_fiscal": "Rua Teste 123"
            },
            "financial_data": {
                "portal_financas_senha": "senha123"
            }
        }
        
        # Encriptar
        encrypted = encrypt_sensitive_data(process)
        
        # Verificar que campos sensíveis foram encriptados
        assert is_encrypted(encrypted["client_phone"])
        assert is_encrypted(encrypted["personal_data"]["nif"])
        assert is_encrypted(encrypted["personal_data"]["morada_fiscal"])
        assert is_encrypted(encrypted["financial_data"]["portal_financas_senha"])
        
        # Verificar que campos não sensíveis não foram alterados
        assert encrypted["client_name"] == "João Silva"
        assert encrypted["personal_data"]["nome"] == "João Silva"
        
        # Desencriptar
        decrypted = decrypt_sensitive_data(encrypted)
        
        # Verificar que os valores originais foram recuperados
        assert decrypted["client_phone"] == "912345678"
        assert decrypted["personal_data"]["nif"] == "123456789"
        assert decrypted["personal_data"]["morada_fiscal"] == "Rua Teste 123"
        assert decrypted["financial_data"]["portal_financas_senha"] == "senha123"
    
    def test_encrypt_co_buyers(self):
        """Testa encriptação de 2º Titular / Fiador."""
        from services.process_service import encrypt_sensitive_data, decrypt_sensitive_data
        
        process = {
            "id": "test-456",
            "co_buyers": [
                {"nome": "Maria Silva", "nif": "987654321", "phone": "923456789"}
            ]
        }
        
        encrypted = encrypt_sensitive_data(process)
        
        # Verificar encriptação
        assert is_encrypted(encrypted["co_buyers"][0]["nif"])
        assert is_encrypted(encrypted["co_buyers"][0]["phone"])
        
        # Desencriptar e verificar
        decrypted = decrypt_sensitive_data(encrypted)
        assert decrypted["co_buyers"][0]["nif"] == "987654321"
        assert decrypted["co_buyers"][0]["phone"] == "923456789"


class TestClientEncryption:
    """Testes de encriptação em clientes."""
    
    def test_encrypt_client_data(self):
        """Testa encriptação de dados de cliente."""
        # Logic lives in services.encryption (routes/clients.py is thin stubs only)
        from services.encryption import encrypt_client_data, decrypt_client_data
        
        client = {
            "id": "client-123",
            "nome": "João Silva",
            "contacto": {
                "email": "joao@email.com",
                "telefone": "912345678"
            },
            "dados_pessoais": {
                "nif": "123456789",
                "morada_fiscal": "Rua Teste 123"
            }
        }
        
        # Encriptar
        encrypted = encrypt_client_data(client)
        
        # Verificar encriptação
        assert is_encrypted(encrypted["contacto"]["telefone"])
        assert is_encrypted(encrypted["dados_pessoais"]["nif"])
        assert is_encrypted(encrypted["dados_pessoais"]["morada_fiscal"])
        
        # Desencriptar
        decrypted = decrypt_client_data(encrypted)
        
        # Verificar valores originais
        assert decrypted["contacto"]["telefone"] == "912345678"
        assert decrypted["dados_pessoais"]["nif"] == "123456789"
        assert decrypted["dados_pessoais"]["morada_fiscal"] == "Rua Teste 123"


class TestEncryptionAvailability:
    """Testes de disponibilidade do serviço de encriptação."""
    
    def test_encryption_service_available(self):
        """Testa se o serviço de encriptação está disponível."""
        # O serviço deve estar disponível (biblioteca cryptography instalada)
        assert encryption_service.is_available()
    
    def test_encrypt_decrypt_consistency(self):
        """Testa consistência de encriptação/desencriptação múltiplas vezes."""
        original = "123456789"
        
        for _ in range(10):
            encrypted = encrypt_value(original)
            decrypted = decrypt_value(encrypted)
            assert decrypted == original, f"Falhou na iteração: original={original}, decrypted={decrypted}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
