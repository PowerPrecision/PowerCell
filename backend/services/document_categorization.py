"""
====================================================================
SERVIÇO DE CATEGORIZAÇÃO DE DOCUMENTOS COM IA - CREDITOIMO
====================================================================
Categoriza documentos automaticamente usando GPT-4o-mini.
A IA analisa o conteúdo e atribui categorias dinamicamente.

Funcionalidades:
- Extracção de texto de PDFs
- Categorização automática com IA
- Geração de resumo e tags
- Pesquisa por conteúdo

Autor: PowerCell Development Team
====================================================================
"""
import os
import io
import re
import json
import uuid
import logging
import base64
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')


def extract_text_from_pdf(pdf_content: bytes, max_chars: int = 10000) -> str:
    """
    Extrair texto de um PDF usando pypdf.
    
    Args:
        pdf_content: Conteúdo do PDF em bytes
        max_chars: Máximo de caracteres a extrair
    
    Returns:
        Texto extraído do PDF (limitado)
    """
    try:
        from pypdf import PdfReader
        
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        
        text_parts = []
        total_chars = 0
        
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
                total_chars += len(page_text)
                if total_chars >= max_chars:
                    break
        
        full_text = "\n".join(text_parts).strip()
        
        # Limitar tamanho
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "..."
        
        logger.info(f"PDF text extraction: {len(full_text)} caracteres extraídos")
        return full_text
        
    except Exception as e:
        logger.warning(f"Falha na extracção de texto do PDF: {e}")
        return ""


async def categorize_document_with_ai(
    text_content: str,
    filename: str,
    existing_categories: List[str] = None
) -> Dict[str, Any]:
    """
    Categorizar documento usando IA.
    A IA analisa o conteúdo e cria/atribui categorias dinamicamente.
    Também extrai data de validade para documentos relevantes.
    
    Args:
        text_content: Texto extraído do documento
        filename: Nome do ficheiro
        existing_categories: Categorias já existentes no sistema (para consistência)
    
    Returns:
        Dict com categoria, subcategoria, tags, resumo, confiança e expiry_date
    """
    if not EMERGENT_LLM_KEY:
        logger.error("EMERGENT_LLM_KEY não configurada")
        return {
            "success": False,
            "error": "Serviço AI não configurado",
            "category": None
        }
    
    # Construir prompt
    categories_hint = ""
    if existing_categories:
        categories_hint = f"""
Categorias já existentes no sistema (usar preferencialmente para consistência):
{', '.join(existing_categories)}

Se nenhuma categoria existente for adequada, podes criar uma nova.
"""
    
    system_prompt = """És um assistente especializado em categorizar documentos para um CRM de crédito habitação e imobiliário.

Analisa o conteúdo do documento e determina:
1. CATEGORIA: Categoria principal do documento (ex: "Identificação", "Rendimentos", "Imóvel", "Crédito", "Contratos", "Fiscais", etc.)
2. SUBCATEGORIA: Tipo específico de documento (ex: "Cartão de Cidadão", "Recibo de Vencimento", "CPCV", etc.)
3. TAGS: 3-5 palavras-chave relevantes
4. RESUMO: Uma frase curta (max 100 caracteres) descrevendo o documento
5. CONFIANÇA: Nível de certeza da categorização (0.0 a 1.0)
6. DATA DE VALIDADE: Se o documento tem data de validade/expiração, extrair no formato YYYY-MM-DD

Categorias típicas em crédito habitação:
- Identificação: CC, Passaporte, Carta de Condução, CNI
- Rendimentos: Recibos de Vencimento, Declaração IRS, Notas de Liquidação
- Emprego: Contratos de Trabalho, Declarações de Efetividade
- Bancários: Extratos Bancários, Mapas CRC, Declarações de Encargos
- Imóvel: Cadernetas Prediais, Certidões de Registo, Plantas, Licença de Habitação
- Contratos: CPCV, Escrituras, Minutas
- Fiscais: Declarações de IRS, IMI, Certidões
- Simulações: Propostas de Crédito, Simulações Bancárias
- Outros: Documentos não categorizados

IMPORTANTE - Documentos com data de validade:
- Cartão de Cidadão (CC): Procura "Válido até" ou "Data de validade"
- Passaporte: Procura "Date of expiry" ou "Válido até"
- CNI (Cartão Nacional de Identidade): Procura data de validade
- Certidão Predial: Procura data de emissão (válida por 6 meses)
- Licença de Habitação: Pode ter data de validade
- Carta de Condução: Procura "Válida até"

Se não encontrares data de validade ou o documento não tiver validade, usar null."""

    user_prompt = f"""Analisa este documento e categoriza-o.

Nome do ficheiro: {filename}

{categories_hint}

Conteúdo do documento:
---
{text_content[:5000]}
---

Responde APENAS em formato JSON válido:
{{
    "category": "Categoria Principal",
    "subcategory": "Tipo Específico do Documento",
    "tags": ["tag1", "tag2", "tag3"],
    "summary": "Descrição curta do documento",
    "confidence": 0.95,
    "expiry_date": "YYYY-MM-DD ou null se não aplicável"
}}"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        session_id = f"doc-cat-{uuid.uuid4().hex[:8]}"
        
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_prompt
        ).with_model("openai", "gpt-4o-mini")
        
        user_message = UserMessage(text=user_prompt)
        # PACOTE DJ — Nota: LlmChat (emergentintegrations) não expõe
        # `response_format={"type": "json_object"}` como o client OpenAI
        # cru (ver ai_document_analyzer.py:419). O prompt já pede JSON
        # estrito e `parse_categorization_response` faz strip de markdown
        # + fallback seguro ("Outros"/0.3) — pelo que nos apoiamos nesse
        # parser. Refactor para client OpenAI directo ficaria para outro
        # pacote (não estritamente necessário para o fluxo HITL DJ).
        response = await chat.send_message(user_message)
        
        # Parse da resposta JSON
        result = parse_categorization_response(response)
        result["success"] = True
        
        logger.info(f"Documento categorizado: {filename} -> {result.get('category')}/{result.get('subcategory')}, expiry: {result.get('expiry_date')}")
        
        return result
        
    except Exception as e:
        logger.error(f"Erro ao categorizar documento: {e}")
        return {
            "success": False,
            "error": str(e),
            "category": None
        }


def parse_categorization_response(response: str) -> Dict[str, Any]:
    """Parse da resposta JSON da IA com validação robusta."""
    try:
        response = response.strip()
        
        # Remover blocos de código markdown
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        
        response = response.strip()
        
        data = json.loads(response)
        
        # Validar que é um dict
        if not isinstance(data, dict):
            logger.warning(f"Resposta não é um dict: {type(data)}")
            return {
                "category": None,
                "subcategory": None,
                "tags": [],
                "summary": "",
                "confidence": 0.0,
                "expiry_date": None
            }
        
        # Processar expiry_date
        expiry_date = data.get("expiry_date")
        if expiry_date and expiry_date.lower() in ["null", "none", ""]:
            expiry_date = None
        
        # Validar formato da data se existir
        if expiry_date:
            try:
                datetime.strptime(expiry_date, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Formato de data inválido: {expiry_date}")
                expiry_date = None
        
        return {
            "category": data.get("category"),
            "subcategory": data.get("subcategory"),
            "tags": data.get("tags", []),
            "summary": data.get("summary", ""),
            "confidence": float(data.get("confidence", 0.5)),
            "expiry_date": expiry_date
        }
        
    except json.JSONDecodeError as e:
        logger.warning(f"Falha ao fazer parse da resposta: {e}")
        return {
            "category": "Outros",
            "subcategory": "Documento",
            "tags": [],
            "summary": "",
            "confidence": 0.3,
            "expiry_date": None
        }


async def search_documents_by_content(
    query: str,
    process_id: Optional[str],
    documents: List[Dict[str, Any]],
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Pesquisar documentos por conteúdo usando correspondência de texto.
    
    Args:
        query: Termo de pesquisa
        process_id: ID do processo (opcional)
        documents: Lista de documentos com metadados
        limit: Número máximo de resultados
    
    Returns:
        Lista de documentos correspondentes ordenados por relevância
    """
    results = []
    query_lower = query.lower()
    query_words = set(query_lower.split())
    
    for doc in documents:
        # Filtrar por processo se especificado
        if process_id and doc.get("process_id") != process_id:
            continue
        
        score = 0.0
        matched_text = None
        
        # Pesquisar no nome do ficheiro
        filename = (doc.get("filename") or "").lower()
        if query_lower in filename:
            score += 5.0
            matched_text = doc.get("filename")
        
        # Pesquisar na categoria
        category = (doc.get("ai_category") or "").lower()
        if query_lower in category:
            score += 3.0
        
        # Pesquisar na subcategoria
        subcategory = (doc.get("ai_subcategory") or "").lower()
        if query_lower in subcategory:
            score += 3.0
        
        # Pesquisar no resumo
        summary = (doc.get("ai_summary") or "").lower()
        if query_lower in summary:
            score += 2.0
            matched_text = matched_text or doc.get("ai_summary")
        
        # Pesquisar nas tags
        tags = doc.get("ai_tags") or []
        for tag in tags:
            if query_lower in tag.lower():
                score += 2.0
                break
        
        # Pesquisar no texto extraído
        extracted_text = (doc.get("extracted_text") or "").lower()
        if extracted_text:
            # Contar ocorrências
            occurrences = extracted_text.count(query_lower)
            if occurrences > 0:
                score += min(occurrences * 0.5, 5.0)  # Max 5 pontos por ocorrências
                
                # Extrair trecho correspondente
                if not matched_text:
                    idx = extracted_text.find(query_lower)
                    if idx >= 0:
                        start = max(0, idx - 50)
                        end = min(len(extracted_text), idx + len(query_lower) + 50)
                        matched_text = "..." + doc.get("extracted_text", "")[start:end] + "..."
        
        # Pesquisa por palavras individuais
        for word in query_words:
            if len(word) >= 3:
                if word in filename:
                    score += 0.5
                if word in extracted_text:
                    score += 0.3
        
        if score > 0:
            results.append({
                "id": doc.get("id"),
                "process_id": doc.get("process_id"),
                "client_name": doc.get("client_name"),
                "s3_path": doc.get("s3_path"),
                "filename": doc.get("filename"),
                "ai_category": doc.get("ai_category"),
                "ai_subcategory": doc.get("ai_subcategory"),
                "ai_summary": doc.get("ai_summary"),
                "relevance_score": round(score, 2),
                "matched_text": matched_text
            })
    
    # Ordenar por relevância
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    
    return results[:limit]


async def get_unique_categories(documents: List[Dict[str, Any]]) -> List[str]:
    """
    Obter lista de categorias únicas dos documentos.
    
    Args:
        documents: Lista de documentos com metadados
    
    Returns:
        Lista de categorias únicas ordenadas
    """
    categories = set()
    
    for doc in documents:
        if doc.get("ai_category"):
            categories.add(doc["ai_category"])
    
    return sorted(list(categories))
