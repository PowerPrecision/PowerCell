"""Encryption and PII compliance diagnostics.

Extraído de `routes/diagnostics.py`.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)


async def run_check_encryption_status():
    """
    Verifica o estado do serviço de encriptação.

    Testa se a encriptação/desencriptação está a funcionar corretamente.
    """
    from services.encryption import encryption_service

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "crypto_available": False,
        "fernet_initialized": False,
        "encryption_key_source": None,
        "test_encryption": None,
        "test_decryption": None,
        "can_decrypt_existing": None,
        "errors": []
    }

    # Verificar se cryptography está disponível
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        result["crypto_available"] = True
    except ImportError:
        result["errors"].append("Biblioteca cryptography não instalada")
        return result

    # Verificar se Fernet está inicializado
    result["fernet_initialized"] = encryption_service._fernet is not None

    # Verificar origem da chave
    if os.environ.get("ENCRYPTION_KEY"):
        result["encryption_key_source"] = "ENCRYPTION_KEY"
        result["encryption_key_length"] = len(os.environ.get("ENCRYPTION_KEY"))
    elif os.environ.get("JWT_SECRET"):
        result["encryption_key_source"] = "JWT_SECRET"
        result["encryption_key_length"] = len(os.environ.get("JWT_SECRET"))
    else:
        result["encryption_key_source"] = "default"
        result["encryption_key_length"] = 0
        result["errors"].append("ENCRYPTION_KEY e JWT_SECRET não definidas - usando chave por defeito!")

    # Testar encriptação/desencriptação
    if encryption_service._fernet:
        try:
            test_value = "123456789"
            encrypted = encryption_service.encrypt(test_value)
            result["test_encryption"] = {
                "success": encrypted.startswith("ENC:"),
                "encrypted_length": len(encrypted)
            }

            # Testar desencriptação
            decrypted = encryption_service.decrypt(encrypted)
            result["test_decryption"] = {
                "success": decrypted == test_value,
                "decrypted_value": decrypted[:3] + "..." if decrypted else None
            }
        except Exception as e:
            result["errors"].append(f"Erro no teste de encriptação: {str(e)}")

    # Tentar desencriptar um valor existente da base de dados
    try:
        # Buscar um cliente com NIF encriptado
        client = await db.clients.find_one(
            {"dados_pessoais.nif": {"$regex": "^ENC:"}},
            {"_id": 0, "id": 1, "nome": 1, "dados_pessoais.nif": 1}
        )

        if client:
            encrypted_nif = client.get("dados_pessoais", {}).get("nif", "")
            if encrypted_nif and encrypted_nif.startswith("ENC:"):
                decrypted_nif = encryption_service.decrypt(encrypted_nif)
                result["can_decrypt_existing"] = {
                    "found": True,
                    "client_id": client.get("id"),
                    "client_name": client.get("nome"),
                    "encrypted_prefix": encrypted_nif[:20] + "...",
                    "decrypted_length": len(decrypted_nif) if decrypted_nif else 0,
                    "decryption_success": not decrypted_nif.startswith("ENC:") if decrypted_nif else False
                }
        else:
            result["can_decrypt_existing"] = {"found": False, "message": "Nenhum cliente com NIF encriptado encontrado"}
    except Exception as e:
        result["errors"].append(f"Erro ao testar desencriptação de dados existentes: {str(e)}")

    return result


async def run_check_pii_compliance():
    """
    Verifica a conformidade PII (Personally Identifiable Information) com a OpenAI.

    IMPORTANTE: Este endpoint verifica se os dados sensíveis dos clientes
    (NIFs, rendimentos, dados pessoais) estão protegidos de serem usados
    para treino de modelos públicos.

    Para garantir conformidade:
    1. Configure OPENAI_DATA_TRAINING_OPT_OUT=true nas variáveis de ambiente
    2. Verifique em https://platform.openai.com/account/organization que
       "Improve our models with your data" está DESATIVADO
    3. Configure OPENAI_ORGANIZATION_ID com o ID da sua organização corporativa

    Retorna:
    - Estado de conformidade
    - Verificações realizadas
    - Avisos e recomendações
    """
    from services.openai_privacy import verify_openai_privacy_compliance

    try:
        compliance_result = await verify_openai_privacy_compliance()

        # Adicionar documentação
        compliance_result["documentation"] = {
            "how_to_configure_opt_out": [
                "1. Aceda a https://platform.openai.com/account/organization",
                "2. Navegue para 'Data Controls' > 'Training Data'",
                "3. Desative 'Improve our models with your data'",
                "4. Configure OPENAI_DATA_TRAINING_OPT_OUT=true nas variáveis de ambiente",
                "5. Configure OPENAI_ORGANIZATION_ID com o ID da sua organização"
            ],
            "enterprise_accounts": (
                "Contas Enterprise da OpenAI têm o treino de dados desativado por defeito. "
                "Se tem uma conta Enterprise, confirme que o opt-out está ativo nas settings."
            ),
            "data_types_protected": [
                "NIF (Número de Identificação Fiscal)",
                "Rendimentos (salários, IRS)",
                "Dados pessoais (nome, morada, telefone)",
                "Dados bancários (IBAN, saldos)",
                "Número de documento (CC, passaporte)"
            ],
            "reference_links": [
                "https://platform.openai.com/docs/models/how-we-use-your-data",
                "https://openai.com/enterprise-privacy",
                "https://platform.openai.com/account/organization"
            ]
        }

        return compliance_result

    except Exception as e:
        logger.error(f"Erro ao verificar conformidade PII: {e}")
        return {
            "compliant": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


async def run_test_openai_api_privacy():
    """
    Testa a conectividade com a API OpenAI verificando configurações de privacidade.

    Este endpoint faz uma chamada de teste à API para verificar:
    - Se a conectividade está funcional
    - Se o Organization ID está a ser usado
    - Se há avisos de privacidade
    """
    from services.openai_privacy import test_openai_api_with_privacy_headers

    try:
        result = await test_openai_api_with_privacy_headers()
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as e:
        logger.error(f"Erro ao testar API OpenAI: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
