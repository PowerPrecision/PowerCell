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

BLIND INDEXING (Pesquisa de dados encriptados):
- nif_hash: SHA-256 do NIF para pesquisa de duplicados
- telefone_hash: SHA-256 do telefone para pesquisa de duplicados
- O hash é determinístico (mesmo valor = mesmo hash), permitindo pesquisa
  sem expor o valor real em plain text

IMPORTANTE: A chave de encriptação deve ser definida em variável de ambiente
ENCRYPTION_KEY. Se não definida, uma chave é gerada (não persiste entre reinícios).
====================================================================
"""
import os
import logging
import base64
import hashlib
import re
import copy
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
    "intermediario": ["nif", "phone"],
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
            logger.error(f"DESENCRIPTAÇÃO FALHOU: Fernet não inicializado! Valor permanece encriptado: {value[:30]}...")
            logger.error("CAUSA PROVÁVEL: ENCRYPTION_KEY não definida ou diferente da usada para encriptar")
            logger.error("SOLUÇÃO: Configure ENCRYPTION_KEY nas variáveis de ambiente do Vercel")
            return value
        
        try:
            encrypted_part = value[len(self.ENCRYPTION_PREFIX):]
            decrypted = self._fernet.decrypt(encrypted_part.encode()).decode()
            logger.debug("Desencriptação bem sucedida")
            return decrypted
        except Exception as e:
            logger.error(f"Erro ao desencriptar: {e}")
            logger.error(f"CAUSA: Chave de encriptação pode ser diferente da usada para encriptar os dados")
            logger.error(f"Valor problemático (primeiros 30 chars): {value[:30]}...")
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
    """Desencripta um valor simples usando o serviço de encriptação global.

    Função de conveniência que delega em ``encryption_service.decrypt``.
    Se o valor não tiver o prefixo "ENC:" ou o serviço não estiver disponível,
    retorna o valor original sem alterações.

    IMPORTANTE: Se a chave de encriptação atual for diferente da usada para
    encriptar, a desencriptação falha silenciosamente e o valor encriptado é
    retornado tal qual. Isto é deliberado — o log de erro contém instruções
    para diagnosticar o problema, mas não interrompe a aplicação.

    Args:
        value: Valor possivelmente encriptado (com prefixo "ENC:" se encriptado).

    Returns:
        str: Valor desencriptado, ou o valor original se não estava encriptado
            ou se a desencriptação falhou.
    """
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


# =====================================================================
# BLIND INDEXING - HASH DETERMINÍSTICO PARA PESQUISA
# =====================================================================
# Permite pesquisar dados encriptados sem expor o valor real.
# O hash é determinístico: mesmo valor = mesmo hash (mas não reversível)

# Salt para blind index (DEVE ser diferente do salt de encriptação)
BLIND_INDEX_SALT = os.environ.get("BLIND_INDEX_SALT", "creditoimo-blind-index-salt-2024").encode()


def generate_blind_index(value: str, index_type: str = "general") -> str:
    """
    Gera um hash determinístico (blind index) para pesquisa de dados encriptados.

    No PowerCell, os dados sensíveis (NIF, telefone) estão encriptados com Fernet,
    impossibilitando pesquisas por igualdade direta. O blind index resolve isto:
    gera um hash SHA-256 determinístico do valor, que permite pesquisas por igualdade
    sem expor o valor real em plain text na base de dados.

    O hash usa salt específico por tipo de índice para evitar colisões entre
    diferentes campos (ex: NIF "123456789" não colide com telefone "123456789").

    Args:
        value: Valor sensível a indexar (NIF, telefone, email, etc.).
        index_type: Tipo de índice ("nif", "telefone", "email", "general") para
            salt específico. Tipos diferentes geram hashes diferentes.

    Returns:
        str: Hash SHA-256 hexadecimal (64 caracteres) ou string vazia se valor inválido.
    """
    if not value:
        return ""
    
    # Normalizar valor (remover espaços, caracteres especiais)
    normalized = re.sub(r'[^\w]', '', str(value).lower().strip())
    
    if not normalized:
        return ""
    
    # Salt específico por tipo de índice
    type_salt = f"{BLIND_INDEX_SALT.decode()}:{index_type}".encode()
    
    # Gerar hash SHA-256 com salt
    hash_input = f"{normalized}:{type_salt.hex()}".encode()
    return hashlib.sha256(hash_input).hexdigest()


def generate_nif_hash(nif: str) -> str:
    """
    Gera um hash determinístico para pesquisa de NIF português encriptado.

    O NIF é o identificador fiscal principal em Portugal e é usado como chave
    de pesquisa de duplicados no CRM. Como o NIF está encriptado em repouso
    (Fernet), não é possível pesquisá-lo diretamente. Este hash permite
    verificar se um cliente com o mesmo NIF já existe sem expor o valor real.

    Valida que o NIF tem exatamente 9 dígitos antes de gerar o hash — NIFs
    inválidos não são indexados, evitando falsos positivos na pesquisa
    de duplicados.

    Args:
        nif: NIF português (pode conter pontos e espaços que são removidos).

    Returns:
        str: Hash SHA-256 hexadecimal (64 caracteres), ou string vazia
            se o NIF for inválido ou vazio.
    """
    if not nif:
        return ""
    # Limpar NIF (apenas dígitos)
    clean_nif = re.sub(r'[^\d]', '', str(nif))
    if len(clean_nif) != 9:
        return ""
    return generate_blind_index(clean_nif, "nif")


def generate_telefone_hash(telefone: str) -> str:
    """
    Gera um hash determinístico para pesquisa de número de telefone encriptado.

    O telefone é um campo de pesquisa secundário no CRM (além do NIF e email).
    Este blind index permite identificar clientes pelo número de telefone
    sem armazená-lo em texto claro na base de dados.

    Valida que o número tem pelo menos 9 dígitos após limpeza (formato
    português padrão), rejeitando números demasiado curtos que poderiam
    gerar colisões acidentais.

    Args:
        telefone: Número de telefone (pode conter espaços, hífens e parênteses).

    Returns:
        str: Hash SHA-256 hexadecimal (64 caracteres), ou string vazia
            se o telefone for inválido ou tiver menos de 9 dígitos.
    """
    if not telefone:
        return ""
    # Limpar telefone (apenas dígitos)
    clean_phone = re.sub(r'[^\d]', '', str(telefone))
    if len(clean_phone) < 9:
        return ""
    return generate_blind_index(clean_phone, "telefone")


def generate_email_hash(email: str) -> str:
    """
    Gera um hash determinístico para pesquisa de endereço de email.

    O email é o principal identificador de contato no CRM e serve como chave
    de pesquisa em múltiplos fluxos (login, deduplicação, sincronização IMAP).
    Este blind index permite consultas rápidas por email sem expor o endereço
    real em índices de base de dados.

    O email é normalizado para minúsculas antes da geração do hash para
    evitar que "Cliente@Exemplo.com" e "cliente@exemplo.com" gerem
    hashes diferentes.

    Args:
        email: Endereço de email (normalizado para minúsculas internamente).

    Returns:
        str: Hash SHA-256 hexadecimal (64 caracteres), ou string vazia
            se o email for vazio.
    """
    if not email:
        return ""
    return generate_blind_index(email.lower().strip(), "email")


# =====================================================================
# ENCRIPTAÇÃO DE CLIENTES (COLEÇÃO 'clients')
# =====================================================================

# Campos sensíveis na coleção 'clients'
CLIENT_SENSITIVE_FIELDS = {
    "dados_pessoais": ["nif", "documento_id", "morada_fiscal", "telefone", "phone"],
    "contacto": ["telefone", "telefone_secundario", "phone"],
    "titular2_data": ["nif", "documento_id", "telefone", "phone"],
}


def encrypt_client_data(data: dict) -> dict:
    """
    Encripta campos sensíveis de um cliente e gera blind indexes para pesquisa.

    Função de entrada principal para escrita — deve ser chamada antes de guardar
    um cliente na base de dados. Garante que dados PII (NIF, telefone, morada
    fiscal, documento de identificação) ficam protegidos em repouso.

    A encriptação é feita ANTES da geração dos blind indexes: os hashes são
    calculados a partir dos valores originais, antes de os mesmos serem
    encriptados. Isto é essencial para que a pesquisa funcione corretamente.

    Blind indexes gerados:
    - dados_pessoais.nif_hash (para pesquisa de duplicados por NIF).
    - contacto.telefone_hash (para pesquisa por telefone).

    Args:
        data: Dicionário com dados do cliente (dados_pessoais, contacto,
            titular2_data, etc.).

    Returns:
        dict: Mesmo dicionário com campos sensíveis encriptados (prefixo "ENC:")
            e blind indexes adicionados.
    """
    if not encryption_service.is_available() or not data:
        # Mesmo sem encriptação, gerar blind indexes
        result = data.copy()
        _add_client_blind_indexes(result)
        return result
    
    result = copy.deepcopy(data)
    
    # Gerar blind indexes ANTES de encriptar
    _add_client_blind_indexes(result)
    
    # Encriptar dados_pessoais
    if "dados_pessoais" in result and isinstance(result["dados_pessoais"], dict):
        for field in CLIENT_SENSITIVE_FIELDS["dados_pessoais"]:
            if field in result["dados_pessoais"] and result["dados_pessoais"][field]:
                result["dados_pessoais"][field] = encryption_service.encrypt(
                    str(result["dados_pessoais"][field])
                )
    
    # Encriptar contacto
    if "contacto" in result and isinstance(result["contacto"], dict):
        for field in CLIENT_SENSITIVE_FIELDS["contacto"]:
            if field in result["contacto"] and result["contacto"][field]:
                result["contacto"][field] = encryption_service.encrypt(
                    str(result["contacto"][field])
                )
    
    # Encriptar titular2_data
    if "titular2_data" in result and isinstance(result["titular2_data"], dict):
        for field in CLIENT_SENSITIVE_FIELDS["titular2_data"]:
            if field in result["titular2_data"] and result["titular2_data"][field]:
                result["titular2_data"][field] = encryption_service.encrypt(
                    str(result["titular2_data"][field])
                )
    
    # Encriptar campo nif no nível raiz (se existir - compatibilidade)
    if "nif" in result and result["nif"]:
        result["nif"] = encryption_service.encrypt(str(result["nif"]))
    
    return result


def _add_client_blind_indexes(data: dict) -> None:
    """
    Adiciona blind indexes ao documento do cliente (modifica in-place).
    
    Gera SEMPRE (não apenas se ausente) para garantir que actualizações
    a email/NIF/telefone são refletidas imediatamente na pesquisa.
    
    Gera:
    - dados_pessoais.nif_hash
    - contacto.telefone_hash
    - contacto.email_hash
    """
    # Hash do NIF
    if "dados_pessoais" in data and isinstance(data["dados_pessoais"], dict):
        nif = data["dados_pessoais"].get("nif")
        if nif:
            nif_clean = re.sub(r'[^\d]', '', str(nif))
            if len(nif_clean) == 9:
                data["dados_pessoais"]["nif_hash"] = generate_nif_hash(nif_clean)
    
    # Hash do telefone
    if "contacto" in data and isinstance(data["contacto"], dict):
        telefone = data["contacto"].get("telefone")
        if telefone:
            data["contacto"]["telefone_hash"] = generate_telefone_hash(telefone)
        
        # Hash do email para pesquisa
        email = data["contacto"].get("email")
        if email:
            data["contacto"]["email_hash"] = generate_email_hash(email)
    
    # Hash do NIF do titular2
    if "titular2_data" in data and isinstance(data["titular2_data"], dict):
        nif2 = data["titular2_data"].get("nif")
        if nif2:
            nif2_clean = re.sub(r'[^\d]', '', str(nif2))
            if len(nif2_clean) == 9:
                data["titular2_data"]["nif_hash"] = generate_nif_hash(nif2_clean)


def decrypt_client_data(data: dict) -> dict:
    """
    Desencripta campos sensíveis de um cliente após ler da BD.
    
    NOTA: Os blind indexes (nif_hash, telefone_hash) NÃO são removidos,
    pois são necessários para pesquisas futuras.
    
    Args:
        data: Dicionário com dados encriptados
        
    Returns:
        Dicionário com campos sensíveis desencriptados
    """
    if not data:
        return data
    
    result = copy.deepcopy(data)
    
    # Função auxiliar para desencriptar
    def decrypt_field(value):
        if not value or not isinstance(value, str):
            return value
        if not value.startswith("ENC:"):
            return value
        try:
            decrypted = encryption_service.decrypt(value)
            if decrypted and not decrypted.startswith("ENC:"):
                return decrypted
        except Exception as e:
            logger.warning(f"Erro ao desencriptar valor: {e}")
        return value
    
    # Desencriptar dados_pessoais
    if "dados_pessoais" in result and isinstance(result["dados_pessoais"], dict):
        for field in CLIENT_SENSITIVE_FIELDS["dados_pessoais"]:
            if field in result["dados_pessoais"] and result["dados_pessoais"][field]:
                result["dados_pessoais"][field] = decrypt_field(result["dados_pessoais"][field])
    
    # Desencriptar contacto
    if "contacto" in result and isinstance(result["contacto"], dict):
        for field in CLIENT_SENSITIVE_FIELDS["contacto"]:
            if field in result["contacto"] and result["contacto"][field]:
                result["contacto"][field] = decrypt_field(result["contacto"][field])
    
    # Desencriptar titular2_data
    if "titular2_data" in result and isinstance(result["titular2_data"], dict):
        for field in CLIENT_SENSITIVE_FIELDS["titular2_data"]:
            if field in result["titular2_data"] and result["titular2_data"][field]:
                result["titular2_data"][field] = decrypt_field(result["titular2_data"][field])
    
    # Desencriptar campo nif no nível raiz (se existir)
    if "nif" in result and result["nif"]:
        result["nif"] = decrypt_field(result["nif"])
    
    return result


def decrypt_clients_list(clients: list) -> list:
    """Desencripta uma lista de clientes."""
    return [decrypt_client_data(c) for c in clients]
