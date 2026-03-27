"""
====================================================================
AI Document Analyzer Service - PowerCell
====================================================================
Serviço para análise de documentos com IA (GPT-4o-mini).
Extrai dados estruturados de documentos e compara com dados do cliente.

Funcionalidades:
- OCR de documentos (CC, IRS, recibos de vencimento, etc.)
- Extração de dados estruturados
- Comparação com dados existentes do cliente
- Sugestão de preenchimento automático
- Organização de documentos em pastas
====================================================================
"""

import os
import logging
import base64
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import uuid
import re

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# Mapeamento de tipos de documento para pastas
DOCUMENT_CATEGORIES = {
    "cc": "Pessoais",
    "bi": "Pessoais",
    "passport": "Pessoais",
    "nif": "Pessoais",
    "comprovativo_morada": "Pessoais",
    "irs": "Financeiros",
    "recibo_vencimento": "Financeiros",
    "declaracao_irs": "Financeiros",
    "nota_liquidacao": "Financeiros",
    "extrato_bancario": "Bancários",
    "comprovativo_poupanca": "Bancários",
    "mapa_responsabilidades": "Bancários",
    "caderneta_predial": "Imóvel",
    "certidao_teor": "Imóvel",
    "licenca_habitacao": "Imóvel",
    "plantas": "Imóvel",
    "contrato": "Outros",
    "procuracao": "Outros",
    "outros": "Outros"
}

# Campos esperados para extração
EXTRACTABLE_FIELDS = {
    "cc": ["nome_completo", "data_nascimento", "nif", "numero_documento", "validade", "nacionalidade", "sexo", "morada"],
    "irs": ["nome", "nif", "ano", "rendimento_bruto", "rendimento_liquido", "agregado_familiar"],
    "recibo_vencimento": ["nome", "nif", "entidade_empregadora", "valor_bruto", "valor_liquido", "data"],
    "extrato_bancario": ["titular", "iban", "saldo", "movimentos_entrada", "movimentos_saida"],
    "caderneta_predial": ["artigo_matricial", "fracao", "area", "valor_patrimonial", "morada_imovel"],
}

# System prompt para análise de documentos
DOCUMENT_ANALYSIS_PROMPT = """Você é um especialista em análise de documentos portugueses para processos de crédito habitação.

Analise o documento fornecido e extraia TODOS os dados relevantes em formato JSON estruturado.

Regras importantes:
1. Extraia APENAS dados que estão claramente visíveis no documento
2. Para campos não encontrados, use null
3. Datas devem estar no formato YYYY-MM-DD
4. Valores monetários devem ser números sem símbolos de moeda
5. NIF deve ter 9 dígitos
6. Seja preciso e não invente dados

Retorne APENAS um JSON válido com a seguinte estrutura:
{
    "tipo_documento": "cc|irs|recibo_vencimento|extrato_bancario|caderneta_predial|comprovativo_morada|outro",
    "confianca": 0.0 a 1.0,
    "dados_extraidos": {
        // campos específicos do documento
    },
    "observacoes": "notas relevantes sobre o documento"
}

Para CC/Cartão de Cidadão:
- nome_completo, data_nascimento (YYYY-MM-DD), nif, numero_documento, validade (YYYY-MM-DD), nacionalidade, sexo, morada

Para IRS/Declaração de Rendimentos:
- nome, nif, ano, rendimento_bruto, rendimento_liquido, agregado_familiar

Para Recibo de Vencimento:
- nome, nif, entidade_empregadora, valor_bruto, valor_liquido, data (YYYY-MM-DD)

Para Extrato Bancário:
- titular, iban, saldo, banco

Para Caderneta Predial:
- artigo_matricial, fracao, area, valor_patrimonial, morada_imovel
"""


def get_llm_client():
    """
    Retorna o cliente LLM apropriado baseado na chave de API configurada.
    Usa emergentintegrations para chaves sk-emerg*, ou OpenAI nativo para sk-*.
    """
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if emergent_key and emergent_key.startswith("sk-emerg"):
        # Usar emergentintegrations para chaves emergent
        try:
            from emergentintegrations.llm.openai import LLM
            return LLM(api_key=emergent_key), "emergent"
        except ImportError as e:
            logger.error(f"Biblioteca emergentintegrations não instalada: {e}")
            return None, None
    elif openai_key:
        # Usar OpenAI nativo
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=openai_key), "openai"
    elif emergent_key:
        # Se emergent_key existe mas não começa com sk-emerg, tentar como OpenAI
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=emergent_key), "openai"
    
    return None, None


async def analyze_document_with_ai(
    file_content: bytes,
    file_name: str,
    mime_type: str
) -> Dict[str, Any]:
    """
    Analisa um documento usando GPT-4o-mini.
    
    Args:
        file_content: Conteúdo binário do ficheiro
        file_name: Nome do ficheiro
        mime_type: Tipo MIME do ficheiro
        
    Returns:
        Dados extraídos do documento
    """
    try:
        client, client_type = get_llm_client()
        
        if not client:
            logger.error("EMERGENT_LLM_KEY ou OPENAI_API_KEY não configurada")
            return {"success": False, "error": "Chave de API não configurada. Configure EMERGENT_LLM_KEY ou OPENAI_API_KEY nas variáveis de ambiente."}
        
        # Converter para base64
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        
        # Verificar se é um tipo de imagem suportado
        supported_types = ["image/jpeg", "image/png", "image/webp", "application/pdf"]
        if mime_type not in supported_types:
            # Tentar converter para PNG se for outro formato de imagem
            if mime_type.startswith("image/"):
                mime_type = "image/png"
            else:
                return {"success": False, "error": f"Tipo de ficheiro não suportado: {mime_type}"}
        
        # Preparar o conteúdo da mensagem
        if mime_type == "application/pdf":
            # Tentar extrair texto do PDF usando PyMuPDF
            try:
                import fitz  # PyMuPDF
                pdf_document = fitz.open(stream=file_content, filetype="pdf")
                text_content = ""
                for page in pdf_document:
                    text_content += page.get_text()
                pdf_document.close()
                
                if text_content.strip():
                    # Usar o texto extraído para análise
                    if client_type == "emergent":
                        response = await client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": DOCUMENT_ANALYSIS_PROMPT},
                                {"role": "user", "content": f"Analise este documento ({file_name}) extraído de um PDF. Conteúdo:\n\n{text_content[:10000]}"}
                            ],
                            max_tokens=2000,
                            temperature=0.1
                        )
                    else:
                        response = await client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": DOCUMENT_ANALYSIS_PROMPT},
                                {"role": "user", "content": f"Analise este documento ({file_name}) extraído de um PDF. Conteúdo:\n\n{text_content[:10000]}"}
                            ],
                            max_tokens=2000,
                            temperature=0.1
                        )
                else:
                    return {"success": False, "error": "Não foi possível extrair texto do PDF"}
            except ImportError:
                return {"success": False, "error": "PyMuPDF não instalado para processamento de PDF"}
        else:
            # Para imagens, usar o vision API
            image_url = f"data:{mime_type};base64,{file_base64}"
            
            if client_type == "emergent":
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": DOCUMENT_ANALYSIS_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Analise este documento ({file_name}) e extraia todos os dados relevantes."},
                                {"type": "image_url", "image_url": {"url": image_url}}
                            ]
                        }
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
            else:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": DOCUMENT_ANALYSIS_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Analise este documento ({file_name}) e extraia todos os dados relevantes."},
                                {"type": "image_url", "image_url": {"url": image_url}}
                            ]
                        }
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
        
        # Obter a resposta
        response_text = response.choices[0].message.content
        logger.info(f"Resposta recebida para {file_name}")
        
        # Parse da resposta JSON
        import json
        
        # Tentar extrair JSON da resposta
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                result = json.loads(json_match.group())
                result["success"] = True
                result["file_name"] = file_name
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"Erro ao fazer parse do JSON: {e}")
                return {
                    "success": True,
                    "tipo_documento": "outro",
                    "confianca": 0.5,
                    "dados_extraidos": {},
                    "observacoes": response_text,
                    "file_name": file_name
                }
        else:
            return {
                "success": True,
                "tipo_documento": "outro",
                "confianca": 0.3,
                "dados_extraidos": {},
                "observacoes": response_text,
                "file_name": file_name
            }
            
    except Exception as e:
        logger.error(f"Erro na análise de documento: {e}", exc_info=True)
        return {"success": False, "error": str(e), "file_name": file_name}


def compare_extracted_with_existing(
    extracted_data: Dict[str, Any],
    existing_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compara dados extraídos com dados existentes do cliente.
    
    Args:
        extracted_data: Dados extraídos do documento
        existing_data: Dados existentes do cliente na BD
        
    Returns:
        Comparação com campos diferentes, iguais e novos
    """
    comparison = {
        "matching": [],      # Campos que coincidem
        "different": [],     # Campos com valores diferentes
        "new_fields": [],    # Campos novos (existem no documento mas não no cliente)
        "empty_fields": []   # Campos vazios no cliente que podem ser preenchidos
    }
    
    # Mapeamento de campos do documento para campos do cliente
    field_mapping = {
        "nome_completo": "client_name",
        "nome": "client_name",
        "data_nascimento": "birth_date",
        "nif": "nif",
        "numero_documento": "cc_number",
        "validade": "cc_validity",
        "nacionalidade": "nationality",
        "sexo": "gender",
        "morada": "address",
        "morada_fiscal": "fiscal_address"
    }
    
    dados = extracted_data.get("dados_extraidos", {})
    
    for doc_field, client_field in field_mapping.items():
        doc_value = dados.get(doc_field)
        if doc_value is None:
            continue
            
        client_value = existing_data.get(client_field)
        
        # Normalizar valores para comparação
        doc_value_normalized = str(doc_value).strip().lower() if doc_value else ""
        client_value_normalized = str(client_value).strip().lower() if client_value else ""
        
        if not client_value or client_value_normalized == "":
            comparison["empty_fields"].append({
                "field": client_field,
                "doc_field": doc_field,
                "suggested_value": doc_value,
                "source": extracted_data.get("file_name", "documento")
            })
        elif doc_value_normalized == client_value_normalized:
            comparison["matching"].append({
                "field": client_field,
                "value": doc_value
            })
        else:
            comparison["different"].append({
                "field": client_field,
                "doc_field": doc_field,
                "current_value": client_value,
                "document_value": doc_value,
                "source": extracted_data.get("file_name", "documento")
            })
    
    return comparison


def get_folder_for_document(document_type: str) -> str:
    """
    Retorna a pasta de destino para um tipo de documento.
    
    Args:
        document_type: Tipo do documento detectado
        
    Returns:
        Nome da pasta de destino
    """
    doc_type_lower = document_type.lower().replace(" ", "_")
    return DOCUMENT_CATEGORIES.get(doc_type_lower, "Outros")


async def analyze_multiple_documents(
    documents: List[Dict[str, Any]],
    existing_client_data: Dict[str, Any],
    log_id: str = None
) -> Dict[str, Any]:
    """
    Analisa múltiplos documentos e compara com dados do cliente.
    
    Args:
        documents: Lista de documentos [{content, name, mime_type}, ...]
        existing_client_data: Dados existentes do cliente
        log_id: ID do log de importação (opcional)
        
    Returns:
        Resultado da análise com comparações e sugestões
    """
    import time
    from routes.ai_import_logs import update_ai_import_log
    
    start_time = time.time()
    
    results = {
        "documents_analyzed": [],
        "comparison": {
            "matching": [],
            "different": [],
            "new_fields": [],
            "empty_fields": []
        },
        "organization_suggestions": [],
        "auto_fill_suggestions": {}
    }
    
    # Analisar cada documento
    for doc in documents:
        doc_start_time = time.time()
        
        analysis = await analyze_document_with_ai(
            file_content=doc["content"],
            file_name=doc["name"],
            mime_type=doc["mime_type"]
        )
        
        doc_processing_time = int((time.time() - doc_start_time) * 1000)
        
        # Preparar resultado do documento para o log
        doc_result = {
            "file_name": doc["name"],
            "file_size": len(doc["content"]),
            "mime_type": doc["mime_type"],
            "processing_time_ms": doc_processing_time
        }
        
        if analysis.get("success"):
            results["documents_analyzed"].append(analysis)
            
            # Comparar com dados existentes
            comparison = compare_extracted_with_existing(analysis, existing_client_data)
            
            # Agregar comparações
            results["comparison"]["matching"].extend(comparison["matching"])
            results["comparison"]["different"].extend(comparison["different"])
            results["comparison"]["new_fields"].extend(comparison["new_fields"])
            results["comparison"]["empty_fields"].extend(comparison["empty_fields"])
            
            # Sugerir organização
            doc_type = analysis.get("tipo_documento", "outro")
            folder = get_folder_for_document(doc_type)
            results["organization_suggestions"].append({
                "file_name": doc["name"],
                "document_type": doc_type,
                "suggested_folder": folder,
                "confidence": analysis.get("confianca", 0.5)
            })
            
            # Auto-fill suggestions (campos vazios)
            for empty in comparison["empty_fields"]:
                field = empty["field"]
                if field not in results["auto_fill_suggestions"]:
                    results["auto_fill_suggestions"][field] = {
                        "value": empty["suggested_value"],
                        "source": empty["source"],
                        "confidence": analysis.get("confianca", 0.5)
                    }
            
            # Actualizar log com sucesso
            doc_result.update({
                "status": "success",
                "document_type": doc_type,
                "confidence": analysis.get("confianca", 0.5),
                "destination_folder": folder,
                "extracted_fields": analysis.get("dados_extraidos", {}),
                "applied_fields": [e["field"] for e in comparison["empty_fields"]]
            })
        else:
            # Actualizar log com erro
            doc_result.update({
                "status": "error",
                "error_message": analysis.get("error", "Erro desconhecido")
            })
        
        # Actualizar log se existir
        if log_id:
            try:
                await update_ai_import_log(log_id, document_result=doc_result)
            except Exception as e:
                logger.warning(f"Erro ao actualizar log: {e}")
    
    # Calcular duração total
    total_duration = int((time.time() - start_time) * 1000)
    results["duration_ms"] = total_duration
    
    return results
