"""
====================================================================
SERVIÇO DE ENCRIPTAÇÃO - CREDITOIMO
====================================================================
Encriptação de campos sensíveis (NIFs, documentos, contactos, senhas)
usando Fernet (AES-128 em modo CBC com HMAC).

CAMPOS SENSÍVEIS:
- NIFs (personal_data.nif, titular2_data.nif, employer_nif)
- Documentos ID (documento_id)
- Senhas de portais (portal_financas_senha, seg_social_senha)
- Moradas fiscais (morada_fiscal)
- Telefones (client_phone, titular2_data.phone)

IMPORTANTE: A chave de encriptação deve ser definida em variável de ambiente
ENCRYPTION_KEY. Se não definida, uma chave é gerada (não persiste entre reinícios).
====================================================================
"""
import os
import logging
import base64
from typing import Optional, Any, Dict, List
from functools import wraps

logger = logging.getLogger(__name__)

# Tentar importar cryptography
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("Biblioteca cryptography não instalada. Encriptação desativada.")


# Campos sensíveis por secção
SENSITIVE_FIELDS = {
    "personal_data": ["nif", "documento_id", "morada_fiscal", "phone"],
    "titular2_data": ["nif", "documento_id", "phone"],
    "financial_data": ["portal_financas_senha", "seg_social_senha", "employer_nif"],
    "vendedor": ["nif", "documento_id", "phone"],
    "mediador": ["nif", "phone"],
    "co_buyers": ["nif", "documento_id", "phone"],
    "co_applicants": ["nif"],
    "root": ["client_phone", "client_nif"]  # Campos no nível raiz do processo
}


class EncryptionService:
    """
    Serviço de encriptação usando Fernet (AES-128-CBC + HMAC).
    
    Características:
    - Encriptação simétrica (mesma chave para encriptar e desencriptar)
    - Chave derivada de segredo + salt
    - Prefixo para identificar campos encriptados
    """
    
    ENCRYPTION_PREFIX = "ENC:"  # Prefixo para identificar dados encriptados
    
    def __init__(self):
        self._fernet = None
        self._initialize_key()
    
    def _initialize_key(self):
        """Inicializa a chave de encriptação."""
        if not CRYPTO_AVAILABLE:
            logger.warning("Cryptography não disponível - encriptação desativada")
            return
        
        # Obter chave de variável de ambiente
        secret = os.environ.get("ENCRYPTION_KEY") or os.environ.get("JWT_SECRET", "default-secret-key")
        salt = os.environ.get("ENCRYPTION_SALT", "creditoimo-encryption-salt").encode()
        
        # Log para debug (sem mostrar o segredo completo)
        if os.environ.get("ENCRYPTION_KEY"):
            logger.info(f"ENCRYPTION_KEY definida (len={len(os.environ.get('ENCRYPTION_KEY'))})")
        elif os.environ.get("JWT_SECRET"):
            logger.info(f"A usar JWT_SECRET como chave de encriptação (len={len(os.environ.get('JWT_SECRET'))})")
        else:
            logger.warning("ENCRYPTION_KEY e JWT_SECRET não definidas - a usar chave por defeito!")
        
        # Derivar chave usando PBKDF2
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
            self._fernet = Fernet(key)
            logger.info("Serviço de encriptação inicializado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao inicializar encriptação: {e}")
            self._fernet = None
    
    def is_available(self) -> bool:
        """Verifica se a encriptação está disponível."""
        return CRYPTO_AVAILABLE and self._fernet is not None
    
    def encrypt(self, value: str) -> str:
        """
        Encripta um valor.
        
        Args:
            value: Valor a encriptar (string)
            
        Returns:
            Valor encriptado com prefixo ENC:
        """
        if not self.is_available() or not value:
            return value
        
        # Não re-encriptar se já está encriptado
        if isinstance(value, str) and value.startswith(self.ENCRYPTION_PREFIX):
            return value
        
        try:
            encrypted = self._fernet.encrypt(value.encode()).decode()
            return f"{self.ENCRYPTION_PREFIX}{encrypted}"
        except Exception as e:
            logger.error(f"Erro ao encriptar: {e}")
            return value
    
    def decrypt(self, value: str) -> str:
        """
        Desencripta um valor.
        
        Args:
            value: Valor encriptado (com prefixo ENC:)
            
        Returns:
            Valor original desencriptado
        """
        if not value:
            return value
        
        # Verificar se está encriptado
        if not isinstance(value, str) or not value.startswith(self.ENCRYPTION_PREFIX):
            return value
        
        # Se o serviço não está disponível, tentar mesmo assim
        if not self._fernet:
            logger.error("Tentativa de desencriptação mas Fernet não está inicializado!")
            return value
        
        try:
            encrypted_part = value[len(self.ENCRYPTION_PREFIX):]
            decrypted = self._fernet.decrypt(encrypted_part.encode()).decode()
            logger.debug("Desencriptação bem sucedida")
            return decrypted
        except Exception as e:
            logger.error(f"Erro ao desencriptar: {e}")
            return value
    
    def encrypt_dict(self, data: dict, fields: List[str]) -> dict:
        """
        Encripta campos específicos de um dicionário.
        
        Args:
            data: Dicionário com dados
            fields: Lista de campos a encriptar
            
        Returns:
            Dicionário com campos encriptados
        """
        if not self.is_available() or not data:
            return data
        
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        
        return result
    
    def decrypt_dict(self, data: dict, fields: List[str]) -> dict:
        """
        Desencripta campos específicos de um dicionário.
        
        Args:
            data: Dicionário com dados encriptados
            fields: Lista de campos a desencriptar
            
        Returns:
            Dicionário com campos desencriptados
        """
        if not self.is_available() or not data:
            return data
        
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.decrypt(str(result[field]))
        
        return result
    
    def encrypt_process(self, process: dict) -> dict:
        """
        Encripta todos os campos sensíveis de um processo.
        
        Args:
            process: Documento do processo
            
        Returns:
            Processo com campos sensíveis encriptados
        """
        if not self.is_available() or not process:
            return process
        
        result = process.copy()
        
        # Encriptar campos no nível raiz
        for field in SENSITIVE_FIELDS.get("root", []):
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        
        # Encriptar campos em sub-dicionários
        for section, fields in SENSITIVE_FIELDS.items():
            if section == "root":
                continue
            
            if section in result and isinstance(result[section], dict):
                result[section] = self.encrypt_dict(result[section], fields)
        
        # Encriptar listas de co-compradores/co-proponentes
        for list_field in ["co_buyers", "co_applicants"]:
            if list_field in result and isinstance(result[list_field], list):
                fields_to_encrypt = SENSITIVE_FIELDS.get(list_field, [])
                result[list_field] = [
                    self.encrypt_dict(item, fields_to_encrypt) if isinstance(item, dict) else item
                    for item in result[list_field]
                ]
        
        return result
    
    def decrypt_process(self, process: dict) -> dict:
        """
        Desencripta todos os campos sensíveis de um processo.
        
        Args:
            process: Documento do processo com campos encriptados
            
        Returns:
            Processo com campos sensíveis desencriptados
        """
        if not self.is_available() or not process:
            return process
        
        result = process.copy()
        
        # Desencriptar campos no nível raiz
        for field in SENSITIVE_FIELDS.get("root", []):
            if field in result and result[field]:
                result[field] = self.decrypt(str(result[field]))
        
        # Desencriptar campos em sub-dicionários
        for section, fields in SENSITIVE_FIELDS.items():
            if section == "root":
                continue
            
            if section in result and isinstance(result[section], dict):
                result[section] = self.decrypt_dict(result[section], fields)
        
        # Desencriptar listas de co-compradores/co-proponentes
        for list_field in ["co_buyers", "co_applicants"]:
            if list_field in result and isinstance(result[list_field], list):
                fields_to_decrypt = SENSITIVE_FIELDS.get(list_field, [])
                result[list_field] = [
                    self.decrypt_dict(item, fields_to_decrypt) if isinstance(item, dict) else item
                    for item in result[list_field]
                ]
        
        return result


# Instância global
encryption_service = EncryptionService()


# Funções de conveniência
def encrypt_value(value: str) -> str:
    """Encripta um valor simples."""
    return encryption_service.encrypt(value)


def decrypt_value(value: str) -> str:
    """Desencripta um valor simples."""
    return encryption_service.decrypt(value)


def encrypt_process_data(process: dict) -> dict:
    """Encripta todos os campos sensíveis de um processo."""
    return encryption_service.encrypt_process(process)


def decrypt_process_data(process: dict) -> dict:
    """Desencripta todos os campos sensíveis de um processo."""
    return encryption_service.decrypt_process(process)


def is_encrypted(value: str) -> bool:
    """Verifica se um valor está encriptado."""
    if not value or not isinstance(value, str):
        return False
    return value.startswith(EncryptionService.ENCRYPTION_PREFIX)
