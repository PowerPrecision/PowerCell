"""
====================================================================
OPENAI PRIVACY COMPLIANCE SERVICE - PowerCell
====================================================================
Serviço para garantir conformidade PII com a API OpenAI.

IMPORTANTE - OPT-OUT DE TREINO DE DADOS:
Para garantir que os dados PII (NIFs, rendimentos, dados pessoais) 
dos clientes NÃO são usados para treinar modelos públicos da OpenAI:

1. CONTA OPENAI CORPORATIVA:
   - Aceda a: https://platform.openai.com/account/organization
   - Em "Data Controls" > "Training Data"
   - Desative "Improve our models with your data"
   
2. VERIFICAÇÃO AUTOMÁTICA:
   - Este módulo verifica se o opt-out está configurado
   - Regista alertas se houver risco de treino de dados

3. BOAS PRÁTICAS:
   - Use uma conta Enterprise da OpenAI (treino desativado por defeito)
   - Configure OPENAI_ORGANIZATION_ID para identificação
   - Verifique regularmente a conformidade

Referências:
- https://platform.openai.com/docs/models/how-we-use-your-data
- https://openai.com/enterprise-privacy
====================================================================
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ====================================================================
# CONFIGURAÇÕES DE PRIVACIDADE (importadas do config.py)
# ====================================================================

# Importar configurações do config central
try:
    from config import (
        OPENAI_ORGANIZATION_ID,
        OPENAI_DATA_TRAINING_OPT_OUT,
        OPENAI_API_KEY,
        EMERGENT_LLM_KEY
    )
except ImportError:
    # Fallback se config não estiver disponível
    OPENAI_ORGANIZATION_ID = os.environ.get('OPENAI_ORGANIZATION_ID', '')
    OPENAI_DATA_TRAINING_OPT_OUT = os.environ.get('OPENAI_DATA_TRAINING_OPT_OUT', 'true').lower() == 'true'
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# Tipos de dados PII que são enviados para a IA
PII_DATA_TYPES = [
    "nif",                    # Número de Identificação Fiscal
    "nome_completo",          # Nome completo
    "data_nascimento",        # Data de nascimento
    "morada",                 # Morada
    "telefone",               # Telefone
    "email",                  # Email
    "rendimento",             # Rendimentos (salários, IRS)
    "iban",                   # IBAN
    "numero_documento",       # Número de CC/Passaporte
    "renda",                  # Renda mensal
    "valor_imovel",           # Valor de imóveis
    "saldo_bancario",         # Saldos bancários
]

# ====================================================================
# VERIFICAÇÃO DE CONFORMIDADE
# ====================================================================

async def verify_openai_privacy_compliance() -> Dict[str, Any]:
    """
    Verifica se a conta OpenAI está em conformidade com as políticas de privacidade.
    
    Returns:
        Dict com estado de conformidade e recomendações
    """
    result = {
        "compliant": True,
        "warnings": [],
        "recommendations": [],
        "checks": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # 1. Verificar se há API key configurada
    has_api_key = bool(OPENAI_API_KEY or EMERGENT_LLM_KEY)
    result["checks"]["api_key_configured"] = has_api_key
    
    if not has_api_key:
        result["warnings"].append("Nenhuma chave API OpenAI configurada")
        return result
    
    # 2. Verificar se o opt-out está declarado
    result["checks"]["opt_out_declared"] = OPENAI_DATA_TRAINING_OPT_OUT
    
    if not OPENAI_DATA_TRAINING_OPT_OUT:
        result["compliant"] = False
        result["warnings"].append(
            "CRÍTICO: OPENAI_DATA_TRAINING_OPT_OUT não está configurado como 'true'. "
            "Os dados PII podem estar a ser usados para treino de modelos."
        )
        result["recommendations"].append(
            "Configure OPENAI_DATA_TRAINING_OPT_OUT=true nas variáveis de ambiente "
            "E verifique em https://platform.openai.com/account/organization"
        )
    
    # 3. Verificar se há Organization ID (conta corporativa)
    result["checks"]["organization_id_configured"] = bool(OPENAI_ORGANIZATION_ID)
    
    if not OPENAI_ORGANIZATION_ID:
        result["warnings"].append(
            "OPENAI_ORGANIZATION_ID não configurado. "
            "Recomenda-se usar uma conta corporativa para garantir privacidade."
        )
        result["recommendations"].append(
            "Configure OPENAI_ORGANIZATION_ID com o ID da sua organização OpenAI "
            "(encontrado em https://platform.openai.com/account/organization)"
        )
    
    # 4. Verificar tipo de chave (chaves sk-emerg são de terceiros)
    is_emergent_key = EMERGENT_LLM_KEY.startswith('sk-emerg') if EMERGENT_LLM_KEY else False
    result["checks"]["uses_emergent_key"] = is_emergent_key
    
    if is_emergent_key:
        result["warnings"].append(
            "A usar chave Emergent (sk-emerg). Verifique a política de privacidade "
            "do provider Emergent em https://emergent.ai/privacy"
        )
        result["recommendations"].append(
            "Para máxima privacidade, considere usar uma chave OpenAI diretamente "
            "com uma conta Enterprise."
        )
    
    # 5. Verificar se a chave OpenAI direta está configurada
    result["checks"]["direct_openai_key"] = bool(OPENAI_API_KEY)
    
    # 6. Teste de conectividade com verificação de headers
    try:
        connectivity = await test_openai_api_with_privacy_headers()
        result["checks"]["api_connectivity"] = connectivity.get("success", False)
        
        if connectivity.get("warning"):
            result["warnings"].append(connectivity["warning"])
    except Exception as e:
        result["checks"]["api_connectivity"] = False
        result["warnings"].append(f"Erro ao testar conectividade: {str(e)}")
    
    # Resumo final
    result["summary"] = {
        "total_checks": len(result["checks"]),
        "passed_checks": sum(1 for v in result["checks"].values() if v is True),
        "warning_count": len(result["warnings"]),
        "critical_count": sum(1 for w in result["warnings"] if "CRÍTICO" in w)
    }
    
    # Se houver críticos, marcar como não conforme
    if result["summary"]["critical_count"] > 0:
        result["compliant"] = False
    
    return result


async def test_openai_api_with_privacy_headers() -> Dict[str, Any]:
    """
    Testa a API OpenAI com headers de privacidade.
    
    Returns:
        Dict com resultado do teste
    """
    result = {
        "success": False,
        "warning": None,
        "model_used": None
    }
    
    try:
        # Tentar com OpenAI direta primeiro
        if OPENAI_API_KEY:
            from openai import AsyncOpenAI
            
            # Criar cliente com organization ID se disponível
            client_kwargs = {"api_key": OPENAI_API_KEY}
            if OPENAI_ORGANIZATION_ID:
                client_kwargs["organization"] = OPENAI_ORGANIZATION_ID
            
            client = AsyncOpenAI(**client_kwargs)
            
            # Fazer uma chamada de teste mínima
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5,
                temperature=0
            )
            
            result["success"] = True
            result["model_used"] = "gpt-4o-mini"
            result["provider"] = "openai_direct"
            
            # Verificar se a organização foi usada
            if OPENAI_ORGANIZATION_ID:
                result["organization_used"] = True
            else:
                result["warning"] = (
                    "Chamada feita sem Organization ID. "
                    "Configure OPENAI_ORGANIZATION_ID para garantir rastreabilidade corporativa."
                )
            
            return result
        
        # Fallback para Emergent
        if EMERGENT_LLM_KEY:
            try:
                from emergentintegrations.llm.chat import LlmChat, UserMessage
                import uuid
                
                session_id = f"privacy-test-{uuid.uuid4().hex[:8]}"
                
                chat = LlmChat(
                    api_key=EMERGENT_LLM_KEY,
                    session_id=session_id,
                    system_message="Test"
                ).with_model("openai", "gpt-4o-mini")
                
                response = await asyncio.wait_for(
                    chat.send_message(UserMessage(text="Test")),
                    timeout=10.0
                )
                
                result["success"] = True
                result["model_used"] = "gpt-4o-mini"
                result["provider"] = "emergent"
                result["warning"] = (
                    "Usando provider Emergent. Verifique a política de privacidade "
                    "deles em https://emergent.ai/privacy para garantir que dados "
                    "PII não são usados para treino."
                )
                
            except ImportError:
                result["warning"] = "Biblioteca emergentintegrations não instalada"
            except asyncio.TimeoutError:
                result["warning"] = "Timeout ao conectar à API"
        
        return result
        
    except Exception as e:
        result["warning"] = f"Erro na API: {str(e)}"
        return result


def get_privacy_headers() -> Dict[str, str]:
    """
    Retorna headers de privacidade para chamadas OpenAI.
    
    Nota: A OpenAI não suporta headers específicos de opt-out por request.
    O opt-out deve ser configurado no nível da organização.
    
    Returns:
        Dict com headers relevantes
    """
    headers = {}
    
    # Adicionar organization header se disponível
    if OPENAI_ORGANIZATION_ID:
        headers["OpenAI-Organization"] = OPENAI_ORGANIZATION_ID
    
    return headers


def get_openai_client_with_privacy(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
):
    """
    Cria um cliente OpenAI com configurações de privacidade.
    
    Args:
        api_key: Chave API (opcional, usa variável de ambiente se não fornecida)
        base_url: URL base (opcional, para endpoints compatíveis)
    
    Returns:
        Cliente AsyncOpenAI configurado
    """
    from openai import AsyncOpenAI
    
    if not api_key:
        api_key = OPENAI_API_KEY
        if not api_key:
            api_key = EMERGENT_LLM_KEY
            if api_key and api_key.startswith('sk-emerg'):
                base_url = os.environ.get('EMERGENT_BASE_URL', 'https://api.emergent.ai/v1')
    
    if not api_key:
        raise ValueError("Nenhuma chave API OpenAI configurada")
    
    client_kwargs = {"api_key": api_key}
    
    if base_url:
        client_kwargs["base_url"] = base_url
    
    # Adicionar organization para contas corporativas
    if OPENAI_ORGANIZATION_ID and not base_url:
        client_kwargs["organization"] = OPENAI_ORGANIZATION_ID
    
    return AsyncOpenAI(**client_kwargs)


def log_pii_access(data_type: str, operation: str, process_id: Optional[str] = None):
    """
    Regista acesso a dados PII para auditoria.
    
    Args:
        data_type: Tipo de dado PII (nif, rendimento, etc.)
        operation: Operação realizada (extract, analyze, store)
        process_id: ID do processo (opcional)
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_type": data_type,
        "operation": operation,
        "process_id": process_id,
        "ai_opt_out": OPENAI_DATA_TRAINING_OPT_OUT
    }
    
    logger.info(f"[PII_ACCESS] {log_entry}")


# ====================================================================
# MASCARAMENTO DE PII (OPCIONAL)
# ====================================================================

def mask_pii_for_logging(text: str) -> str:
    """
    Mascara dados PII para logs seguros.
    
    Args:
        text: Texto que pode conter PII
    
    Returns:
        Texto com PII mascarado
    """
    import re
    
    masked = text
    
    # Mascarar NIFs (9 dígitos consecutivos)
    masked = re.sub(r'\b\d{9}\b', '*********', masked)
    
    # Mascarar emails
    masked = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***', masked)
    
    # Mascarar IBANs (PT50 + 21 dígitos)
    masked = re.sub(r'\bPT50\d{21}\b', 'PT50*********************', masked)
    
    # Mascarar números de telefone
    masked = re.sub(r'\b(\+351\s?)?[29]\d{8}\b', '*********', masked)
    
    return masked


# ====================================================================
# VALIDAÇÃO DE CONFORMIDADE NA INICIALIZAÇÃO
# ====================================================================

def validate_privacy_config_on_startup():
    """
    Valida configuração de privacidade durante inicialização.
    Deve ser chamado no startup da aplicação.
    """
    warnings = []
    
    if not OPENAI_DATA_TRAINING_OPT_OUT:
        warnings.append(
            "⚠️  AVISO DE PRIVACIDADE: OPENAI_DATA_TRAINING_OPT_OUT não está configurado. "
            "Dados PII podem ser usados para treino de modelos OpenAI. "
            "Configure esta variável como 'true' e verifique as settings da sua conta OpenAI."
        )
    
    if not OPENAI_ORGANIZATION_ID:
        warnings.append(
            "ℹ️  INFO: OPENAI_ORGANIZATION_ID não configurado. "
            "Para contas corporativas, configure o ID da organização para garantir rastreabilidade."
        )
    
    # Verificar tipo de chave
    emergent_key = os.environ.get('EMERGENT_LLM_KEY', '')
    if emergent_key.startswith('sk-emerg'):
        warnings.append(
            "ℹ️  INFO: A usar chave Emergent (sk-emerg). "
            "Verifique a política de privacidade do provider."
        )
    
    for warning in warnings:
        print(warning, file=__import__('sys').stderr)
    
    return warnings
