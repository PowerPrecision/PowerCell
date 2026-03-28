"""
====================================================================
AI DOCUMENT ANALYSIS SERVICE - CREDITOIMO
====================================================================
Serviço de análise de documentos com IA (GPT-4o-mini).

OPTIMIZAÇÕES:
1. Tenta extrair texto do PDF com pypdf primeiro
2. Se conseguir texto suficiente, envia apenas texto (mais barato/rápido)
3. Só usa modelo de visão se extracção de texto falhar
4. Redimensiona imagens para max 1024px antes de enviar
5. Processamento paralelo com asyncio.gather para bulk analysis
6. Validação de tamanho de ficheiro antes de carregar para memória

Tipos de documentos suportados:
- CC (Cartão de Cidadão)
- Recibo de Vencimento
- IRS
- Outros
====================================================================
"""
import os
import io
import re
import json
import logging
import base64
import asyncio
import httpx
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone

from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

load_dotenv()

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# Modelo a usar - gpt-4o-mini é mais barato e rápido
AI_MODEL = "gpt-4o-mini"


def sanitize_email(email: str) -> str:
    """
    Limpa emails com formatação markdown ou outros artefactos.
    """
    if not email:
        return ""
    
    email = email.strip()
    
    # Padrão: [texto](mailto:email)
    markdown_link = re.search(r'\[.*?\]\(mailto:([^)]+)\)', email)
    if markdown_link:
        email = markdown_link.group(1)
    
    # Padrão: mailto:email
    if email.startswith('mailto:'):
        email = email.replace('mailto:', '')
    
    # Padrão: <email>
    angle_brackets = re.search(r'<([^>]+@[^>]+)>', email)
    if angle_brackets:
        email = angle_brackets.group(1)
    
    # Remover caracteres markdown
    email = re.sub(r'[\[\]\(\)]', '', email)
    
    return email.strip().lower()


# ====================================================================
# CONSTANTES E FILTROS
# ====================================================================

# Mínimo de caracteres para considerar extracção de texto bem sucedida
MIN_TEXT_LENGTH = 100

# Tamanho máximo de imagem (lado maior)
MAX_IMAGE_SIZE = 1024

# Tamanho máximo de ficheiro (20MB)
MAX_FILE_SIZE = 20 * 1024 * 1024

# ====================================================================
# LIMITES DE SEGURANÇA PARA EXTRAÇÃO DE TEXTO DE PDF
# Mitigação de Prompt Injection
# ====================================================================

# Tamanho máximo de texto extraído de PDF (em caracteres)
# Limita a quantidade de dados que podem ser enviados para a IA
MAX_PDF_TEXT_LENGTH = 50000  # ~50KB de texto

# Tamanho máximo por página de PDF
MAX_PDF_PAGE_TEXT_LENGTH = 10000  # ~10KB por página

# Número máximo de páginas a processar
MAX_PDF_PAGES = 50

# Número máximo de ficheiros a processar em paralelo
MAX_CONCURRENT_ANALYSIS = 5

# Lista de palavras que NÃO devem ser extraídas como nomes de pessoas
# (empresas, seguradoras, bancos, termos genéricos)
INVALID_NAME_WORDS = {
    # Seguradoras e Bancos
    'fidelidade', 'ocidental', 'tranquilidade', 'allianz', 'generali',
    'mapfre', 'ageas', 'logo', 'liberty', 'zurich', 'axa', 'real vida',
    'santander', 'caixa', 'millennium', 'bcp', 'bpi', 'novo banco',
    'montepio', 'bankinter', 'eurobic', 'activobank', 'best',
    # Termos genéricos
    'seguro', 'seguros', 'companhia', 'empresa', 'lda', 'sa', 'unipessoal',
    'comercial', 'industrial', 'capital', 'investimentos', 'holding',
    'portugal', 'portuguesa', 'ibérica', 'europeia', 'internacional',
    # Documentos
    'cartao', 'cidadao', 'identificacao', 'passaporte', 'carta',
    'conducao', 'titulo', 'residencia', 'certificado', 'declaracao',
    # Outros
    'cliente', 'utilizador', 'proprietario', 'titular', 'beneficiario',
    'contrato', 'apolice', 'recibo', 'factura', 'extrato', 'comprovativo',
}


def is_valid_person_name(name: str) -> bool:
    """
    Verifica se uma string parece ser um nome de pessoa válido.
    Retorna False para nomes de empresas, seguradoras, etc.
    """
    if not name or len(name) < 3:
        return False
    
    name_lower = name.lower().strip()
    
    # Verificar contra lista de palavras inválidas
    words = set(name_lower.split())
    if words & INVALID_NAME_WORDS:
        return False
    
    # Verificar se contém palavras inválidas como substring
    for invalid in INVALID_NAME_WORDS:
        if invalid in name_lower:
            return False
    
    # Verificar se parece nome de empresa (contém números, siglas típicas)
    if re.search(r'\b(lda|ltd|sa|s\.a\.|unip|nif|nipc)\b', name_lower, re.IGNORECASE):
        return False
    
    if re.search(r'\d{3,}', name):  # Contém 3+ dígitos seguidos
        return False
    
    # Deve ter pelo menos 2 palavras para um nome completo
    name_parts = [p for p in name_lower.split() if len(p) > 1]
    if len(name_parts) < 2:
        return False
    
    return True

# Configuração de retry para erros 429 (rate limit)
RETRY_MAX_ATTEMPTS = 5
RETRY_MIN_WAIT = 2  # segundos
RETRY_MAX_WAIT = 32  # segundos


class RateLimitError(Exception):
    """Excepção para erros de rate limit (429)."""
    pass


def sanitize_pdf_text(text: str, max_length: int = MAX_PDF_TEXT_LENGTH) -> str:
    """
    Sanitiza texto extraído de PDF para prevenir Prompt Injection.
    
    MITIGAÇÕES IMPLEMENTADAS:
    1. Remove caracteres de controlo perigosos (NULL, SOH, STX, etc.)
    2. Remove sequências de escape ANSI
    3. Remove caracteres Unicode de controlo (C0, C1)
    4. Limita o tamanho total do texto
    5. Remove padrões suspeitos de prompt injection
    6. Normaliza espaços em branco excessivos
    
    Args:
        text: Texto extraído do PDF
        max_length: Tamanho máximo permitido
    
    Returns:
        Texto sanitizado e truncado
    """
    if not text:
        return ""
    
    # 1. Remover caracteres de controlo ASCII perigosos (0x00-0x1F exceto 0x09, 0x0A, 0x0D)
    # Mantém: tab (0x09), newline (0x0A), carriage return (0x0D)
    sanitized = ""
    for char in text:
        code = ord(char)
        # Permitir caracteres imprimíveis, tab, newline, carriage return
        if code >= 0x20 or code in (0x09, 0x0A, 0x0D):
            sanitized += char
        # Substituir caracteres de controlo por espaço
        elif code < 0x20:
            sanitized += " "
    
    # 2. Remover sequências de escape ANSI (comum em PDFs maliciosos)
    # Padrão: ESC [ ... letras/dígitos
    ansi_escape = re.compile(r'\x1B\[[0-9;]*[A-Za-z]')
    sanitized = ansi_escape.sub('', sanitized)
    
    # 3. Remover caracteres Unicode de controlo C1 (0x80-0x9F)
    sanitized = re.sub(r'[\x80-\x9F]', '', sanitized)
    
    # 4. Remover caracteres NULL bytes que possam ter passado
    sanitized = sanitized.replace('\x00', '')
    
    # 5. Padrões suspeitos de prompt injection
    # Detecta tentativas comuns de injeção de prompts
    suspicious_patterns = [
        # Ignorar instruções anteriores
        r'(?i)ignore\s+(previous|above|all|prior)\s+(instructions?|prompts?|context)',
        r'(?i)forget\s+(everything|all|prior|previous)',
        r'(?i)disregard\s+(all|any|previous|above)',
        # Novo system prompt
        r'(?i)(new|fake|alternative)\s+system\s+prompt',
        r'(?i)you\s+are\s+now\s+',
        r'(?i)act\s+as\s+(if|a|an)\s+',
        # Injeção de contexto
        r'(?i)<<[^>]+>>',  # <<CONTEXT>> patterns
        r'(?i)\[\[.+\]\]',  # [[INSTRUCTION]] patterns
        # Delimitadores de secção suspeitos
        r'(?i)---+\s*(system|instruction|context|prompt)\s*---+',
        # Tentativas de override
        r'(?i)override\s+(previous|default|system)',
        # JSON injection
        r'(?i)"role"\s*:\s*"system"',
    ]
    
    for pattern in suspicious_patterns:
        sanitized = re.sub(pattern, '[REDACTED]', sanitized)
    
    # 6. Normalizar espaços em branco excessivos
    # Múltiplos espaços -> um espaço
    sanitized = re.sub(r' {3,}', '  ', sanitized)
    # Múltiplas newlines -> máximo 2
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)
    # Múltiplos tabs -> um tab
    sanitized = re.sub(r'\t{2,}', '\t', sanitized)
    
    # 7. Remover caracteres não imprimíveis restantes
    # Manter apenas caracteres Unicode válidos e imprimíveis
    sanitized = ''.join(c for c in sanitized if c.isprintable() or c in '\n\r\t')
    
    # 8. Truncar se exceder o tamanho máximo
    if len(sanitized) > max_length:
        # Truncar em um limite de palavra se possível
        truncate_at = sanitized.rfind(' ', 0, max_length)
        if truncate_at > max_length * 0.8:  # Se encontrou espaço nos últimos 20%
            sanitized = sanitized[:truncate_at]
        else:
            sanitized = sanitized[:max_length]
        logger.warning(f"Texto de PDF truncado de {len(text)} para {len(sanitized)} caracteres")
    
    # Log de sanitização se houve alterações
    if len(sanitized) != len(text):
        logger.info(f"PDF text sanitized: {len(text)} -> {len(sanitized)} chars")
    
    return sanitized.strip()


def extract_text_from_pdf(pdf_content: bytes, max_pages: int = MAX_PDF_PAGES) -> str:
    """
    Extrair texto de um PDF usando pypdf com limites de segurança.
    
    MITIGAÇÕES DE SEGURANÇA:
    - Limite de páginas processadas (MAX_PDF_PAGES)
    - Limite de tamanho por página (MAX_PDF_PAGE_TEXT_LENGTH)
    - Limite total de texto (MAX_PDF_TEXT_LENGTH)
    - Sanitização de caracteres de controlo
    - Prevenção de Prompt Injection
    
    Args:
        pdf_content: Conteúdo do PDF em bytes
        max_pages: Número máximo de páginas a processar
    
    Returns:
        Texto extraído e sanitizado do PDF
    """
    try:
        from pypdf import PdfReader
        
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        
        total_pages = len(reader.pages)
        pages_to_process = min(total_pages, max_pages)
        
        if total_pages > max_pages:
            logger.warning(f"PDF tem {total_pages} páginas, processando apenas {max_pages}")
        
        text_parts = []
        total_chars = 0
        
        for i, page in enumerate(reader.pages[:pages_to_process]):
            page_text = page.extract_text()
            
            if page_text:
                # Limitar tamanho por página
                if len(page_text) > MAX_PDF_PAGE_TEXT_LENGTH:
                    logger.warning(f"Página {i+1} truncada: {len(page_text)} -> {MAX_PDF_PAGE_TEXT_LENGTH} chars")
                    page_text = page_text[:MAX_PDF_PAGE_TEXT_LENGTH]
                
                text_parts.append(page_text)
                total_chars += len(page_text)
                
                # Parar se já excedemos o limite total
                if total_chars >= MAX_PDF_TEXT_LENGTH:
                    logger.warning(f"Limite de texto total atingido na página {i+1}")
                    break
        
        full_text = "\n".join(text_parts)
        
        # SANITIZAÇÃO: Aplicar antes de retornar
        sanitized_text = sanitize_pdf_text(full_text, MAX_PDF_TEXT_LENGTH)
        
        logger.info(f"PDF text extraction: {len(sanitized_text)} caracteres extraídos de {pages_to_process} páginas")
        return sanitized_text
        
    except Exception as e:
        logger.warning(f"Falha na extracção de texto do PDF: {e}")
        return ""


def convert_pdf_to_image(pdf_content: bytes, page_num: int = 0, dpi: int = 150) -> Tuple[Optional[bytes], str]:
    """
    Converter uma página de PDF para imagem usando PyMuPDF.
    Útil para PDFs que são scans/imagens e não têm texto extraível.
    
    Args:
        pdf_content: Conteúdo do PDF em bytes
        page_num: Número da página a converter (0 = primeira)
        dpi: Resolução da imagem (150 é bom equilíbrio qualidade/tamanho)
    
    Returns:
        Tuple (bytes da imagem PNG, mime_type) ou (None, "") se falhar
    """
    try:
        import fitz  # PyMuPDF
        
        # Abrir PDF
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        
        if page_num >= len(doc):
            page_num = 0
        
        page = doc[page_num]
        
        # Converter para imagem com resolução especificada
        # Matrix para controlar DPI (default é 72)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        
        # Renderizar página como pixmap
        pix = page.get_pixmap(matrix=mat)
        
        # Converter para PNG
        img_bytes = pix.tobytes("png")
        
        doc.close()
        
        logger.info(f"PDF convertido para imagem: página {page_num}, {len(img_bytes)} bytes")
        return img_bytes, "image/png"
        
    except Exception as e:
        logger.error(f"Erro ao converter PDF para imagem: {e}")
        return None, ""


def merge_images_to_pdf(images_data: List[Tuple[bytes, str]]) -> Optional[bytes]:
    """
    Juntar múltiplas imagens num único PDF.
    Útil para juntar CC frente e verso.
    
    Args:
        images_data: Lista de tuples (bytes da imagem, mime_type)
    
    Returns:
        Bytes do PDF resultante ou None se falhar
    """
    try:
        import img2pdf
        from PIL import Image
        
        # Converter todas as imagens para formato compatível
        image_bytes_list = []
        
        for img_bytes, mime_type in images_data:
            # Abrir imagem com PIL para garantir formato correcto
            img = Image.open(io.BytesIO(img_bytes))
            
            # Converter para RGB se necessário (img2pdf não suporta RGBA)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Guardar como JPEG em memória
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=90)
            image_bytes_list.append(output.getvalue())
        
        # Criar PDF com todas as imagens
        pdf_bytes = img2pdf.convert(image_bytes_list)
        
        logger.info(f"Criado PDF com {len(images_data)} imagens: {len(pdf_bytes)} bytes")
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"Erro ao criar PDF a partir de imagens: {e}")
        return None


def resize_image_base64(base64_content: str, mime_type: str, max_size: int = MAX_IMAGE_SIZE) -> Tuple[str, str]:
    """
    Redimensionar imagem para ter no máximo max_size pixels no lado maior.
    
    Args:
        base64_content: Imagem em base64
        mime_type: Tipo MIME da imagem
        max_size: Tamanho máximo do lado maior
    
    Returns:
        Tuple (base64 redimensionado, novo mime_type)
    """
    try:
        from PIL import Image
        
        # Decodificar base64
        image_data = base64.b64decode(base64_content)
        image = Image.open(io.BytesIO(image_data))
        
        # Verificar se precisa redimensionar
        width, height = image.size
        
        if width <= max_size and height <= max_size:
            logger.info(f"Imagem já é pequena ({width}x{height}), não redimensionando")
            return base64_content, mime_type
        
        # Calcular novo tamanho mantendo proporção
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        
        # Redimensionar
        resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Converter para RGB se necessário (para JPEG)
        if resized.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', resized.size, (255, 255, 255))
            if resized.mode == 'P':
                resized = resized.convert('RGBA')
            background.paste(resized, mask=resized.split()[-1] if resized.mode == 'RGBA' else None)
            resized = background
        
        # Guardar em buffer
        buffer = io.BytesIO()
        resized.save(buffer, format='JPEG', quality=85, optimize=True)
        
        # Converter para base64
        new_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        original_size = len(base64_content)
        new_size = len(new_base64)
        logger.info(f"Imagem redimensionada: {width}x{height} -> {new_width}x{new_height}, "
                   f"tamanho: {original_size//1024}KB -> {new_size//1024}KB")
        
        return new_base64, "image/jpeg"
        
    except Exception as e:
        logger.warning(f"Falha ao redimensionar imagem: {e}")
        return base64_content, mime_type


@retry(
    stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    retry=retry_if_exception_type(RateLimitError),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
async def call_openai_api(payload: dict, timeout: float = 60.0) -> dict:
    """
    Chamar API do OpenAI através da biblioteca de integração.
    
    Usa exponential backoff: 2s, 4s, 8s, 16s, 32s
    Máximo 5 tentativas antes de desistir.
    
    Args:
        payload: Payload JSON para enviar (model, messages, etc.)
        timeout: Timeout em segundos (não usado directamente pela lib)
    
    Returns:
        Resposta no formato compatível com OpenAI API
    
    Raises:
        RateLimitError: Se receber erro de rate limit
        Exception: Outros erros
    """
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        messages = payload.get("messages", [])
        model = payload.get("model", "gpt-4o-mini")
        
        # Extrair system message e user message
        system_message = "Você é um assistente de extracção de dados de documentos."
        user_text = ""
        
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", system_message)
            elif msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_text = content
                elif isinstance(content, list):
                    # Para mensagens com imagem (visão)
                    for item in content:
                        if item.get("type") == "text":
                            user_text = item.get("text", "")
                            break
        
        # Criar sessão única para esta análise
        import uuid
        session_id = f"doc-analysis-{uuid.uuid4().hex[:8]}"
        
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_message
        ).with_model("openai", model)
        
        # Enviar mensagem COM TIMEOUT
        user_message = UserMessage(text=user_text)
        try:
            response = await asyncio.wait_for(
                chat.send_message(user_message),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout ({timeout}s) ao chamar OpenAI API")
            raise Exception(f"Timeout na chamada à API ({timeout}s)")
        
        # Formatar resposta no formato esperado
        return {
            "choices": [{
                "message": {
                    "content": response
                }
            }]
        }
        
    except Exception as e:
        error_msg = str(e).lower()
        if "rate" in error_msg or "429" in error_msg or "limit" in error_msg:
            logger.warning(f"Rate limit detectado: {e}")
            raise RateLimitError(f"Rate limit: {e}")
        logger.error(f"Erro ao chamar OpenAI API: {e}")
        raise


async def analyze_with_text(text: str, document_type: str) -> Dict[str, Any]:
    """
    Analisar documento usando apenas texto (sem visão).
    Mais rápido e barato que usar modelo de visão.
    
    Inclui retry automático para erros 429 (rate limit).
    
    Args:
        text: Texto extraído do documento
        document_type: Tipo de documento
    
    Returns:
        Dados extraídos
    """
    system_prompt, user_prompt = get_extraction_prompts(document_type)
    
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"{user_prompt}\n\n--- TEXTO DO DOCUMENTO ---\n{text}"
            }
        ]
        
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "max_tokens": 2000,
            "temperature": 0.1
        }
        
        result = await call_openai_api(payload, timeout=60.0)
        
        ai_response = result["choices"][0]["message"]["content"]
        extracted_data = parse_ai_response(ai_response, document_type)
        
        return {
            "success": True,
            "document_type": document_type,
            "extracted_data": extracted_data,
            "analysis_method": "text",
            "model": AI_MODEL,
            "raw_response": ai_response
        }
        
    except RateLimitError as e:
        logger.error(f"Rate limit excedido após {RETRY_MAX_ATTEMPTS} tentativas: {e}")
        return {
            "success": False,
            "error": "Limite de pedidos excedido. Tente novamente mais tarde.",
            "extracted_data": {}
        }
    except Exception as e:
        logger.error(f"Erro na análise de texto: {e}")
        return {
            "success": False,
            "error": str(e),
            "extracted_data": {}
        }



async def analyze_with_vision(base64_content: str, mime_type: str, document_type: str) -> Dict[str, Any]:
    """
    Analisar documento usando modelo de visão.
    Usado quando extracção de texto não é possível.
    
    Inclui retry automático para erros 429 (rate limit).
    
    Args:
        base64_content: Imagem em base64
        mime_type: Tipo MIME
        document_type: Tipo de documento
    
    Returns:
        Dados extraídos
    """
    system_prompt, user_prompt = get_extraction_prompts(document_type)
    
    # Para documentos de identificação (CC), NÃO redimensionar para preservar qualidade
    # Para outros documentos, redimensionar para economizar tokens
    if document_type in ['cc', 'cpcv']:
        # Manter resolução original para documentos de ID
        resized_base64 = base64_content
        new_mime_type = mime_type
        logger.info(f"Análise com visão: tipo={document_type}, mantendo resolução original")
    else:
        # Redimensionar imagem antes de enviar
        resized_base64, new_mime_type = resize_image_base64(base64_content, mime_type)
    
    # Documentos de identificação (CC) precisam de alta resolução para ler números pequenos
    # Outros documentos podem usar baixa resolução para economizar tokens
    image_detail = "high" if document_type in ['cc', 'cpcv'] else "low"
    logger.info(f"Análise com visão: tipo={document_type}, detail={image_detail}")
    
    try:
        # Usar biblioteca de integração com suporte a imagem
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        import uuid
        
        # Criar sessão única para esta análise
        session_id = f"doc-vision-{uuid.uuid4().hex[:8]}"
        
        # Inicializar chat com system message
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_prompt
        ).with_model("openai", AI_MODEL)
        
        # Criar conteúdo de imagem em base64
        image_content = ImageContent(
            image_base64=resized_base64
        )
        
        # Criar mensagem com texto e imagem
        user_message = UserMessage(
            text=user_prompt,
            file_contents=[image_content]
        )
        
        # Enviar mensagem e obter resposta COM TIMEOUT (120 segundos)
        # Evita bloqueio infinito se a API não responder
        try:
            ai_response = await asyncio.wait_for(
                chat.send_message(user_message),
                timeout=120.0  # 2 minutos máximo por documento
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout ao analisar documento com visão (tipo={document_type})")
            return {
                "success": False,
                "error": "Timeout na análise do documento. O serviço demorou muito a responder.",
                "extracted_data": {}
            }
        
        extracted_data = parse_ai_response(ai_response, document_type)
        
        return {
            "success": True,
            "document_type": document_type,
            "extracted_data": extracted_data,
            "analysis_method": "vision",
            "model": AI_MODEL,
            "raw_response": ai_response
        }
        
    except RateLimitError as e:
        logger.error(f"Rate limit excedido após {RETRY_MAX_ATTEMPTS} tentativas: {e}")
        return {
            "success": False,
            "error": "Limite de pedidos excedido. Tente novamente mais tarde.",
            "extracted_data": {}
        }
    except Exception as e:
        logger.error(f"Erro na análise com visão: {e}")
        return {
            "success": False,
            "error": str(e),
            "extracted_data": {}
        }


async def analyze_document_from_base64(base64_content: str, mime_type: str, document_type: str) -> Dict[str, Any]:
    """
    Analisar documento a partir de conteúdo base64.
    
    ESTRATÉGIA:
    1. Se for PDF, tenta extrair texto primeiro
    2. Se texto suficiente, usa análise de texto (mais barato)
    3. Se não, converte PDF para imagem e usa modelo de visão
    
    Args:
        base64_content: Conteúdo em base64
        mime_type: Tipo MIME
        document_type: Tipo de documento
    
    Returns:
        Dados extraídos
    """
    if not EMERGENT_LLM_KEY:
        logger.error("EMERGENT_LLM_KEY não configurada")
        return {"error": "Serviço AI não configurado", "extracted_data": {}}
    
    # Decodificar base64
    try:
        content_bytes = base64.b64decode(base64_content)
    except Exception as e:
        logger.error(f"Erro ao decodificar base64: {e}")
        return {"error": "Base64 inválido", "extracted_data": {}}
    
    # Se for PDF, tentar extrair texto primeiro
    if mime_type == "application/pdf":
        logger.info("Documento PDF detectado, tentando extrair texto...")
        extracted_text = extract_text_from_pdf(content_bytes)
        
        if len(extracted_text) >= MIN_TEXT_LENGTH:
            logger.info(f"Texto suficiente extraído ({len(extracted_text)} chars), usando análise de texto")
            return await analyze_with_text(extracted_text, document_type)
        else:
            # PDF sem texto (provavelmente scan/imagem) - converter para imagem
            logger.info(f"Texto insuficiente ({len(extracted_text)} chars), convertendo PDF para imagem...")
            
            # Para documentos de identificação (CC), usar DPI mais alto para melhor leitura de números
            conversion_dpi = 300 if document_type in ['cc', 'cpcv'] else 200
            img_bytes, img_mime = convert_pdf_to_image(content_bytes, page_num=0, dpi=conversion_dpi)
            
            if img_bytes:
                # Usar a imagem convertida para análise de visão
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                logger.info(f"PDF convertido para imagem (DPI={conversion_dpi}), usando modelo de visão")
                return await analyze_with_vision(img_base64, img_mime, document_type)
            else:
                logger.warning("Falha ao converter PDF para imagem, tentando com PDF original")
    
    # Usar modelo de visão com o conteúdo original
    return await analyze_with_vision(base64_content, mime_type, document_type)


async def analyze_document_from_url(document_url: str, document_type: str) -> Dict[str, Any]:
    """
    Analisar documento a partir de URL.
    
    Args:
        document_url: URL do documento
        document_type: Tipo de documento
    
    Returns:
        Dados extraídos
    """
    if not EMERGENT_LLM_KEY:
        logger.error("EMERGENT_LLM_KEY não configurada")
        return {"error": "Serviço AI não configurado", "extracted_data": {}}
    
    try:
        import httpx
        
        # Download do documento
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(document_url)
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("content-type", "application/octet-stream")
        
        # Determinar MIME type
        if "pdf" in content_type.lower():
            mime_type = "application/pdf"
        elif "jpeg" in content_type.lower() or "jpg" in content_type.lower():
            mime_type = "image/jpeg"
        elif "png" in content_type.lower():
            mime_type = "image/png"
        else:
            mime_type = content_type.split(";")[0]
        
        # Converter para base64 e analisar
        base64_content = base64.b64encode(content).decode('utf-8')
        return await analyze_document_from_base64(base64_content, mime_type, document_type)
        
    except Exception as e:
        logger.error(f"Erro ao fazer download do documento: {e}")
        return {"success": False, "error": str(e), "extracted_data": {}}


def get_extraction_prompts(document_type: str) -> tuple:
    """Obter prompts de sistema e utilizador baseado no tipo de documento."""
    
    if document_type == "cc":
        system_prompt = """És um assistente especializado em extrair dados de documentos de identificação portugueses (Cartão de Cidadão).

IMPORTANTE - Localização dos dados no Cartão de Cidadão Português:
- O NIF (Número de Identificação Fiscal) tem 9 dígitos e aparece no VERSO do cartão, na secção "Nº DE IDENTIFICAÇÃO FISCAL"
- O número do documento aparece na FRENTE do cartão
- A data de nascimento aparece na FRENTE do cartão no formato DD MM YYYY
- O nome completo aparece na FRENTE do cartão

Extraia TODOS os dados visíveis do documento e retorna em formato JSON estruturado.
Sê MUITO preciso com números - lê cada dígito cuidadosamente.
O NIF português para pessoas singulares começa por 1, 2, 6 ou 9 (NUNCA por 5 que é para empresas).
Se algum campo não for legível ou não existir, usa null."""
        
        user_prompt = """Analisa este Cartão de Cidadão português e extrai os seguintes dados em formato JSON.

ATENÇÃO AO NIF:
- O NIF tem EXACTAMENTE 9 dígitos
- Aparece no VERSO do cartão, na linha "Nº DE IDENTIFICAÇÃO FISCAL" ou "NIF"
- Lê cada dígito cuidadosamente, especialmente o primeiro dígito
- NIFs válidos para pessoas: começam por 1, 2, 6 ou 9

{
    "nome_completo": "Nome completo da pessoa (apelidos + nomes próprios)",
    "nif": "Número de Identificação Fiscal - EXACTAMENTE 9 dígitos, ex: 268494622",
    "numero_documento": "Número do documento CC",
    "data_nascimento": "Data de nascimento (formato YYYY-MM-DD)",
    "data_validade": "Data de validade do documento (formato YYYY-MM-DD)",
    "naturalidade": "Local de nascimento",
    "nacionalidade": "Nacionalidade",
    "sexo": "M ou F",
    "altura": "Altura em metros",
    "pai": "Nome do pai",
    "mae": "Nome da mãe"
}

Retorna APENAS o JSON, sem texto adicional."""

    elif document_type == "recibo_vencimento":
        system_prompt = """És um assistente especializado em extrair dados de recibos de vencimento.
        
Suportas recibos de vários países:
- Portugal: "Recibo de vencimento", valores em EUR
- França: "Bulletin de paie/Fiche de paie", "Salaire brut/net"  
- Espanha: "Nómina", valores em EUR
- Reino Unido: "Payslip", valores em GBP
- Alemanha: "Gehaltsabrechnung", valores em EUR

Extrai TODOS os valores financeiros e dados do funcionário visíveis.
Valores monetários devem ser números decimais (na moeda original).
IMPORTANTE: Identifica o país de origem do documento pelo idioma e formato.
Se algum campo não for legível ou não existir, usa null."""
        
        user_prompt = """Analisa este recibo de vencimento (pode ser de Portugal, França, ou outro país) e extrai os seguintes dados em formato JSON:

{
    "nome_funcionario": "Nome do funcionário/salarié/employee",
    "nif": "NIF/Numéro fiscal/Tax ID do funcionário (se visível)",
    "empresa": "Nome da empresa empregadora",
    "pais_origem": "PT/FR/ES/UK/DE (código do país do documento)",
    "mes_referencia": "Mês de referência (formato YYYY-MM)",
    "salario_bruto": 0.00,
    "salario_liquido": 0.00,
    "moeda": "EUR/GBP",
    "descontos_imposto": 0.00,
    "descontos_ss": 0.00,
    "subsidio_alimentacao": 0.00,
    "outros_abonos": 0.00,
    "tipo_contrato": "Efetivo/CDI/CDD/Termo/Permanent/Outro",
    "categoria_profissional": "Categoria/função/poste"
}

Retorna APENAS o JSON, sem texto adicional."""

    elif document_type == "irs":
        system_prompt = """És um assistente especializado em extrair dados de declarações fiscais de rendimentos.
        
Suportas declarações de vários países:
- Portugal: Declaração de IRS, Mod. 3
- França: "Avis d'impôt sur le revenu", "Déclaration de revenus"
- Espanha: "Declaración de la Renta", IRPF
- Outros países europeus

Extrai os dados fiscais principais visíveis no documento.
Valores monetários devem ser números decimais.
IMPORTANTE: Identifica o país de origem pelo formato e idioma.
Se for uma declaração conjunta (casados/unidos de facto), extrai dados de AMBOS os titulares."""
        
        user_prompt = """Analisa esta declaração de rendimentos/IRS (pode ser de Portugal, França, ou outro país) e extrai os seguintes dados em formato JSON:

{
    "ano_fiscal": 2024,
    "pais_origem": "PT/FR/ES (código do país do documento)",
    "nif_titular": "NIF/Numéro fiscal do titular 1",
    "nome_titular": "Nome do titular 1",
    "nif_titular_2": "NIF do titular 2/cônjuge ou null se individual",
    "nome_titular_2": "Nome do titular 2/cônjuge ou null se individual",
    "estado_civil_fiscal": "Solteiro/Casado/União de facto/Célibataire/Marié",
    "morada_fiscal": "Morada/adresse fiscal",
    "rendimento_bruto_anual": 0.00,
    "rendimento_liquido_anual": 0.00,
    "imposto_pago": 0.00,
    "reembolso_ou_pagamento": 0.00,
    "moeda": "EUR",
    "numero_dependentes": 0,
    "tem_imoveis": true,
    "tem_creditos_habitacao": true
}

Retorna APENAS o JSON, sem texto adicional."""

    elif document_type == "cpcv":
        system_prompt = """És um assistente especializado em extrair dados de Contratos Promessa de Compra e Venda (CPCV) portugueses.

IMPORTANTE: 
- Podem existir MÚLTIPLOS COMPRADORES (proponentes) - extrai dados de TODOS
- Identifica: Primeiro Outorgante (vendedor), Segundo Outorgante (comprador/proponente)
- Se houver casal/parceiros a comprar, extrai dados de ambos
- Extrai TODOS os dados do imóvel: morada completa, tipologia, área, fração, descrição predial
- Extrai TODOS os valores: preço, sinal, reforços, valor restante, comissões
- Extrai todas as datas importantes
- Valores monetários devem ser números decimais."""
        
        user_prompt = """Analisa este CPCV (Contrato Promessa Compra e Venda) e extrai os seguintes dados em formato JSON:

{
    "compradores": [
        {
            "nome_completo": "Nome completo do comprador/proponente 1",
            "nif": "NIF do comprador 1 (9 dígitos)",
            "cc": "Número do Cartão de Cidadão",
            "estado_civil": "Solteiro/Casado/Divorciado/Viúvo/União de Facto",
            "regime_bens": "Comunhão de adquiridos/Separação de bens/etc",
            "profissao": "Profissão",
            "morada": "Morada completa",
            "codigo_postal": "Código postal",
            "localidade": "Localidade/Cidade",
            "email": "Email",
            "telefone": "Telefone"
        }
    ],
    "vendedor": {
        "nome": "Nome completo do vendedor/promitente vendedor",
        "nif": "NIF do vendedor",
        "cc": "Número CC do vendedor",
        "estado_civil": "Estado civil do vendedor",
        "morada": "Morada do vendedor",
        "tipo": "Particular/Empresa/Herança"
    },
    "imovel": {
        "descricao": "Descrição do imóvel (apartamento, moradia, etc)",
        "morada_completa": "Morada completa do imóvel",
        "codigo_postal": "Código postal",
        "localidade": "Localidade/Cidade",
        "freguesia": "Freguesia",
        "concelho": "Concelho",
        "distrito": "Distrito",
        "tipologia": "T0/T1/T2/T3/T4/T5/Moradia",
        "area_bruta": "Área bruta em m2",
        "area_util": "Área útil em m2",
        "fracao": "Fração (ex: A, B, 1º Dto)",
        "artigo_matricial": "Artigo matricial/Número da matriz",
        "descricao_predial": "Descrição predial na Conservatória",
        "conservatoria": "Nome da Conservatória do Registo Predial",
        "numero_predial": "Número de descrição predial",
        "licenca_utilizacao": "Número da licença de utilização",
        "ano_construcao": "Ano de construção",
        "certificado_energetico": "Classe energética (A, B, C, D, E, F)",
        "estacionamento": "Sim/Não - detalhes do lugar de garagem",
        "arrecadacao": "Sim/Não - detalhes da arrecadação"
    },
    "valores": {
        "preco_total": 0.00,
        "sinal": 0.00,
        "data_sinal": "Data do pagamento do sinal (YYYY-MM-DD)",
        "reforco_sinal": 0.00,
        "data_reforco": "Data do reforço (YYYY-MM-DD)",
        "valor_escritura": 0.00,
        "valor_financiamento": 0.00,
        "comissao_mediacao": 0.00,
        "percentagem_comissao": 0.00,
        "quem_paga_comissao": "Comprador/Vendedor/Partilhada"
    },
    "datas": {
        "data_cpcv": "Data do contrato CPCV (YYYY-MM-DD)",
        "data_escritura_prevista": "Data prevista para escritura (YYYY-MM-DD)",
        "prazo_escritura_dias": "Prazo em dias para a escritura",
        "data_entrega_chaves": "Data prevista entrega de chaves (YYYY-MM-DD)"
    },
    "condicoes": {
        "condicao_suspensiva": "Descrever condição suspensiva se existir (ex: aprovação crédito)",
        "prazo_condicao": "Prazo da condição suspensiva",
        "clausula_penalizacao": "Valor/condições de penalização por incumprimento",
        "observacoes": "Outras condições importantes"
    },
    "mediador": {
        "nome_empresa": "Nome da imobiliária/mediador",
        "nif_empresa": "NIF da empresa",
        "licenca_ami": "Número da licença AMI",
        "consultor": "Nome do consultor imobiliário"
    }
}

Se houver apenas 1 comprador, o array "compradores" deve ter apenas 1 elemento.
Extrai o máximo de informação possível do documento.
Retorna APENAS o JSON, sem texto adicional."""

    elif document_type == "simulacao_credito":
        system_prompt = """És um assistente especializado em extrair dados de simulações de crédito habitação portuguesas.

IMPORTANTE: 
- Podem existir MÚLTIPLOS PROPONENTES (casal a pedir crédito junto) - extrai dados de TODOS
- Identifica Proponente 1, Proponente 2, Cônjuge, etc.
- Valores monetários devem ser números decimais."""
        
        user_prompt = """Analisa esta simulação de crédito habitação e extrai os seguintes dados em formato JSON:

{
    "proponentes": [
        {
            "nome": "Nome do proponente 1",
            "nif": "NIF",
            "data_nascimento": "Data nascimento (YYYY-MM-DD)",
            "rendimento_mensal": 0.00,
            "entidade_patronal": "Empresa onde trabalha"
        },
        {
            "nome": "Nome do proponente 2 (cônjuge) ou null se individual",
            "nif": "NIF ou null",
            "data_nascimento": "Data nascimento ou null",
            "rendimento_mensal": 0.00,
            "entidade_patronal": "Empresa"
        }
    ],
    "credito": {
        "montante_financiamento": 0.00,
        "prazo_anos": 0,
        "taxa_juro": 0.00,
        "spread": 0.00,
        "prestacao_mensal": 0.00,
        "taeg": 0.00
    },
    "imovel": {
        "valor_aquisicao": 0.00,
        "localizacao": "Localização do imóvel"
    },
    "banco": "Nome do banco"
}

Se houver apenas 1 proponente, o array deve ter apenas 1 elemento.
Retorna APENAS o JSON, sem texto adicional."""

    elif document_type == "mapa_crc":
        system_prompt = """És um assistente especializado em extrair dados de Mapas da Central de Responsabilidades de Crédito (CRC) do Banco de Portugal.

IMPORTANTE:
- Extrai TODOS os créditos listados no documento
- Valores monetários devem ser números decimais (usar 0.00 se não disponível)
- Datas no formato YYYY-MM-DD
- Inclui o nome da instituição financeira de cada crédito"""
        
        user_prompt = """Analisa este Mapa CRC (Central de Responsabilidades de Crédito) e extrai os seguintes dados em formato JSON:

{
    "titular": {
        "nome": "Nome completo do titular",
        "nif": "NIF do titular"
    },
    "data_referencia": "Data de referência do mapa (YYYY-MM-DD)",
    "resumo": {
        "total_divida": 0.00,
        "total_em_incumprimento": 0.00,
        "total_potencial": 0.00,
        "prestacao_mensal_total": 0.00,
        "numero_instituicoes": 0,
        "numero_produtos": 0
    },
    "creditos": [
        {
            "instituicao": "Nome do banco/instituição financeira",
            "tipo_produto": "Cartão de crédito/Crédito pessoal/Crédito habitação/Crédito automóvel/Outro",
            "valor_em_divida": 0.00,
            "valor_potencial": 0.00,
            "prestacao_mensal": 0.00,
            "data_inicio": "YYYY-MM-DD ou null",
            "data_fim": "YYYY-MM-DD ou null",
            "em_incumprimento": false,
            "numero_devedores": 1
        }
    ]
}

Extrai TODOS os créditos presentes no documento.
Calcula a soma das prestações mensais para "prestacao_mensal_total".
Retorna APENAS o JSON, sem texto adicional."""

    elif document_type == "extrato_bancario":
        system_prompt = """És um assistente especializado em extrair dados de extratos bancários.
Extrai o saldo e movimentos principais. Valores monetários devem ser números decimais."""
        
        user_prompt = """Analisa este extrato bancário e extrai os seguintes dados em formato JSON:

{
    "titular": "Nome do titular da conta",
    "nif": "NIF se disponível",
    "banco": "Nome do banco",
    "numero_conta": "Número da conta (IBAN se disponível)",
    "data_extrato": "Data do extrato (YYYY-MM-DD)",
    "periodo": {
        "inicio": "YYYY-MM-DD",
        "fim": "YYYY-MM-DD"
    },
    "saldos": {
        "inicial": 0.00,
        "final": 0.00,
        "disponivel": 0.00
    },
    "totais": {
        "entradas": 0.00,
        "saidas": 0.00
    },
    "movimentos_relevantes": [
        {
            "data": "YYYY-MM-DD",
            "descricao": "Descrição do movimento",
            "valor": 0.00,
            "tipo": "credito/debito"
        }
    ]
}

Foca nos movimentos regulares como salários, rendas, prestações de crédito.
Retorna APENAS o JSON, sem texto adicional."""

    else:
        system_prompt = """És um assistente especializado em extrair dados de documentos.
Extrai todos os dados relevantes que encontrares no documento.
IMPORTANTE: Se o documento mencionar múltiplas pessoas (compradores, proponentes, cônjuges), extrai dados de TODAS."""
        
        user_prompt = """Analisa este documento e extrai todos os dados relevantes em formato JSON estruturado.
Inclui nomes, datas, valores, números de identificação, e qualquer outra informação importante.
Se existirem múltiplas pessoas mencionadas (compradores, proponentes, cônjuges), cria um array "pessoas" com os dados de cada uma.
Retorna APENAS o JSON, sem texto adicional."""

    return system_prompt, user_prompt


def parse_ai_response(response: str, document_type: str) -> Dict[str, Any]:
    """Fazer parse da resposta da IA e extrair dados JSON."""
    
    try:
        response = response.strip()
        
        # Remover blocos de código markdown se presentes
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        
        response = response.strip()
        
        # Parse JSON
        data = json.loads(response)
        
        # Se a resposta for uma lista, usar o primeiro elemento
        if isinstance(data, list):
            if len(data) > 0:
                data = data[0] if isinstance(data[0], dict) else {"items": data}
            else:
                data = {}
        
        # Garantir que é um dicionário
        if not isinstance(data, dict):
            return {"raw_value": data, "parse_note": "Resposta não era um dicionário"}
        
        # === LOG DETALHADO PARA DEBUG DO NIF ===
        if document_type == 'cc':
            nif_extraido = data.get('nif')
            nome_extraido = data.get('nome_completo')
            logger.info(f"[DEBUG CC] IA extraiu: NIF='{nif_extraido}', Nome='{nome_extraido}'")
            logger.info(f"[DEBUG CC] Dados completos extraídos: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        return data
        
    except json.JSONDecodeError as e:
        logger.warning(f"Falha ao fazer parse da resposta como JSON: {e}")
        return {"raw_text": response, "parse_error": str(e)}


def map_cc_to_personal_data(cc_data: Dict[str, Any]) -> Dict[str, Any]:
    """Mapear dados extraídos do CC para formato personal_data."""
    return {
        "nif": cc_data.get("nif"),
        "documento_id": cc_data.get("numero_documento"),
        "data_nascimento": cc_data.get("data_nascimento"),
        "data_validade_cc": cc_data.get("data_validade"),
        "naturalidade": cc_data.get("naturalidade"),
        "nacionalidade": cc_data.get("nacionalidade"),
        "sexo": cc_data.get("sexo"),
        "altura": cc_data.get("altura"),
        "nome_pai": cc_data.get("pai"),
        "nome_mae": cc_data.get("mae"),
    }


def map_recibo_to_financial_data(recibo_data: Dict[str, Any]) -> Dict[str, Any]:
    """Mapear dados extraídos do recibo para formato financial_data."""
    return {
        "renda_habitacao_atual": recibo_data.get("salario_liquido"),
        "efetivo": "sim" if recibo_data.get("tipo_contrato", "").lower() == "efetivo" else "nao",
    }


def map_irs_to_financial_data(irs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Mapear dados extraídos do IRS para formato financial_data."""
    annual_income = irs_data.get("rendimento_liquido_anual") or irs_data.get("rendimento_bruto_anual")
    monthly_income = annual_income / 14 if annual_income else None  # 14 meses em Portugal
    
    return {
        "renda_habitacao_atual": round(monthly_income, 2) if monthly_income else None,
    }


# ====================================================================
# BULK ANALYSIS SERVICE FUNCTIONS
# ====================================================================

def detect_document_type(filename: str) -> str:
    """
    Detectar tipo de documento pelo nome do ficheiro.
    
    Melhorias (Item 16):
    - Mais padrões de keywords para cada tipo
    - Suporte para abreviaturas comuns
    - Detecção de CC frente/verso
    - Prioridade de padrões mais específicos
    - NOVO: Suporte para documentos em Francês e Espanhol (portugueses emigrados)
    """
    filename_lower = filename.lower()
    
    # Remover extensão para melhor matching
    name_without_ext = filename_lower.rsplit('.', 1)[0] if '.' in filename_lower else filename_lower
    
    # === CC / Cartão de Cidadão (expandido) ===
    cc_patterns = [
        'cc', 'cartao', 'cartão', 'cidadao', 'cidadão', 
        'identificacao', 'identificação', 'bi ', 'b.i.',
        'cc_', 'frente', 'verso', 'identidade',
        'documento_id', 'doc_id', 'id_card',
        # Portugal específico
        'portugal', 'portugues'
    ]
    if any(x in name_without_ext for x in cc_patterns):
        return 'cc'
    
    # === Recibo de Vencimento (expandido + Internacional) ===
    recibo_patterns = [
        # Português
        'recibo', 'vencimento', 'salario', 'salário', 'ordenado',
        'rec', 'venc', 'sal', 'remunera', 'remuneração', 
        'folha_pagamento', 'holerite', 'contracheque',
        # Francês
        'bulletin', 'paie', 'fiche', 'salaire', 'brut', 'net',
        # Espanhol
        'nomina', 'nómina', 'recibo_sueldo',
        # Inglês
        'payslip', 'wage', 'salary_slip', 'pay_statement'
    ]
    if any(x in name_without_ext for x in recibo_patterns):
        return 'recibo_vencimento'
    
    # === IRS / Declaração de Rendimentos (expandido + Internacional) ===
    irs_patterns = [
        # Português
        'irs', 'modelo3', 'modelo 3', 'rendimentos', 'rendimento',
        'decl_irs', 'nota_liquid', 'liquidacao', 'declaracao_rend',
        # Francês
        'avis', 'impot', 'impôt', 'revenu', 'fiscal', 'declaration',
        # Espanhol
        'renta', 'irpf', 'declaracion', 'hacienda',
        # Inglês
        'p60', 'p45', 'tax return', 'hmrc', 'tax_statement'
    ]
    if any(x in name_without_ext for x in irs_patterns):
        return 'irs'
    
    # === Contrato de Trabalho ===
    contrato_patterns = [
        'contrato', 'trabalho', 'vinculo', 'vínculo', 
        'efetividade', 'employment', 'contract',
        'declaracao_emprego', 'decl_trab'
    ]
    if any(x in name_without_ext for x in contrato_patterns):
        return 'contrato_trabalho'
    
    # === Caderneta Predial ===
    caderneta_patterns = [
        'caderneta', 'predial', 'cadpredial', 'cad_pred'
    ]
    if any(x in name_without_ext for x in caderneta_patterns):
        return 'caderneta_predial'
    
    # === Extrato Bancário (expandido) ===
    extrato_patterns = [
        'extrato', 'bancario', 'bancário', 'banco', 
        'ext_', 'mov', 'movimentos', 'conta',
        'multibanco', 'statement', 'bank_statement'
    ]
    if any(x in name_without_ext for x in extrato_patterns):
        return 'extrato_bancario'
    
    # === Simulação de Crédito ===
    simulacao_patterns = [
        'simulacao', 'simulação', 'proposta financ', 
        'credito', 'crédito', 'financiamento',
        'proposta_banco', 'sim_ch', 'simul'
    ]
    if any(x in name_without_ext for x in simulacao_patterns):
        return 'simulacao_credito'
    
    # === Certidão ===
    certidao_patterns = [
        'certidao', 'certidão', 'domicilio', 'domicílio', 
        'fiscal', 'cert_', 'certificado'
    ]
    if any(x in name_without_ext for x in certidao_patterns):
        return 'certidao'
    
    # === Mapa CRC (Central de Responsabilidades de Crédito) ===
    crc_patterns = [
        'crc', 'responsabilidade', 'mapa_crc', 'central',
        'banco_portugal', 'resp_credito'
    ]
    if any(x in name_without_ext for x in crc_patterns):
        return 'mapa_crc'
    
    # === CPCV ===
    cpcv_patterns = [
        'cpcv', 'promessa', 'compra e venda', 'sinal',
        'contrato_promessa', 'cpv'
    ]
    if any(x in name_without_ext for x in cpcv_patterns):
        return 'cpcv'
    
    # === Dados de Imóvel ===
    imovel_patterns = [
        'imovel', 'imóvel', 'casa', 'apartamento', 
        'moradia', 'fracao', 'fração', 'propriedade'
    ]
    if any(x in name_without_ext for x in imovel_patterns):
        return 'dados_imovel'
    
    return 'outro'


def get_mime_type(filename: str) -> str:
    """Obter MIME type pelo nome do ficheiro."""
    ext = filename.lower().split('.')[-1]
    mime_types = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp',
    }
    return mime_types.get(ext, 'application/octet-stream')


def validate_file_size(content: bytes, filename: str) -> Tuple[bool, str]:
    """
    Validar tamanho do ficheiro.
    
    Returns:
        Tuple (is_valid, error_message)
    """
    size = len(content)
    if size > MAX_FILE_SIZE:
        size_mb = size / (1024 * 1024)
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        return False, f"Ficheiro {filename} excede o limite de {max_mb}MB ({size_mb:.1f}MB)"
    return True, ""


async def analyze_single_document(
    content: bytes,
    filename: str,
    client_name: str,
    process_id: str
) -> Dict[str, Any]:
    """
    Analisar um único documento e retornar resultado.
    
    Args:
        content: Conteúdo do ficheiro em bytes
        filename: Nome do ficheiro
        client_name: Nome do cliente
        process_id: ID do processo
    
    Returns:
        Dict com resultado da análise
    """
    result = {
        "client_name": client_name,
        "filename": filename,
        "process_id": process_id,
        "success": False,
        "extracted_data": {},
        "document_type": "",
        "error": None,
        "updated": False
    }
    
    try:
        # Validar tamanho
        is_valid, error_msg = validate_file_size(content, filename)
        if not is_valid:
            result["error"] = error_msg
            return result
        
        # Detectar tipo de documento e MIME type
        document_type = detect_document_type(filename)
        mime_type = get_mime_type(filename)
        result["document_type"] = document_type
        
        # Converter para base64
        base64_content = base64.b64encode(content).decode('utf-8')
        
        logger.info(f"Analisando {filename} ({document_type}) para {client_name}")
        
        # Analisar com IA
        analysis_result = await analyze_document_from_base64(
            base64_content,
            mime_type,
            document_type
        )
        
        if analysis_result.get("success") and analysis_result.get("extracted_data"):
            result["success"] = True
            result["extracted_data"] = analysis_result["extracted_data"]
            result["fields_extracted"] = list(analysis_result["extracted_data"].keys())
        else:
            result["error"] = analysis_result.get("error", "Erro desconhecido na análise")
            
    except Exception as e:
        logger.error(f"Erro ao analisar {filename}: {e}")
        result["error"] = str(e)
    
    return result


async def process_bulk_documents(
    files_data: List[Dict[str, Any]],
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    Processar múltiplos documentos em paralelo.
    
    Args:
        files_data: Lista de dicts com {content, filename, client_name, process_id}
        progress_callback: Função opcional para reportar progresso
    
    Returns:
        Dict com resultados agregados
    """
    total_files = len(files_data)
    results = []
    errors = []
    processed = 0
    
    # Criar semáforo para limitar concorrência
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSIS)
    
    async def analyze_with_semaphore(file_data: Dict) -> Dict:
        async with semaphore:
            result = await analyze_single_document(
                content=file_data["content"],
                filename=file_data["filename"],
                client_name=file_data["client_name"],
                process_id=file_data["process_id"]
            )
            
            # Reportar progresso se callback fornecido
            if progress_callback:
                await progress_callback(file_data["filename"], result["success"])
            
            return result
    
    # Processar todos em paralelo (limitado pelo semáforo)
    tasks = [analyze_with_semaphore(fd) for fd in files_data]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Processar resultados
    successful_results = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
        elif isinstance(r, dict):
            successful_results.append(r)
            if r.get("success"):
                processed += 1
            if r.get("error"):
                errors.append(f"{r.get('client_name', '?')}/{r.get('filename', '?')}: {r['error']}")
    
    return {
        "success": processed > 0,
        "total_files": total_files,
        "processed": processed,
        "errors": errors,
        "results": successful_results
    }


def build_update_data_from_extraction(
    extracted_data: Dict[str, Any],
    document_type: str,
    existing_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Construir dados de actualização a partir dos dados extraídos.
    
    Args:
        extracted_data: Dados extraídos pela IA
        document_type: Tipo de documento
        existing_data: Dados existentes do processo (para merge)
    
    Returns:
        Dict com campos a actualizar no processo
    """
    if existing_data is None:
        existing_data = {}
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    # Função para verificar se é valor placeholder
    def is_placeholder(value):
        if not value:
            return True
        val_str = str(value).strip().upper()
        placeholders = ['YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY', 'N/A', 'NA', 'NULL', 
                       'NONE', '123456789', '000000000', '12345678', '00000000', '0']
        if val_str in placeholders or 'YYYY' in val_str:
            return True
        return False
    
    # Função para limpar valor
    def clean_value(value):
        if value is None or is_placeholder(value):
            return None
        if isinstance(value, str):
            return value.strip() if value.strip() else None
        return value
    
    # Função para validar NIF (pessoas singulares)
    def is_valid_nif(nif):
        if not nif:
            return False
        nif_clean = re.sub(r'\D', '', str(nif))
        if len(nif_clean) != 9:
            return False
        if nif_clean[0] == '5':  # Empresa - rejeitar
            logger.warning(f"NIF {nif_clean} começa por 5 (empresa) - rejeitado")
            return False
        if nif_clean in ['123456789', '000000000']:
            return False
        if nif_clean[0] not in ['1', '2', '6', '9']:
            return False
        return True
    
    # Conjunto para rastrear campos já mapeados
    mapped_fields = set()
    
    def track_mapped(field):
        """Marcar campo como mapeado"""
        mapped_fields.add(field.lower())
    
    if document_type == 'cc':
        # Dados pessoais
        personal_update = {}
        field_mapping = {
            'nif': 'nif',
            'numero_documento': 'documento_id',
            'data_nascimento': 'data_nascimento',
            'data_validade': 'data_validade_cc',
            'naturalidade': 'naturalidade',
            'nacionalidade': 'nacionalidade',
            'sexo': 'sexo',
            'morada': 'morada',
            'codigo_postal': 'codigo_postal',
            'pai': 'nome_pai',
            'mae': 'nome_mae',
            'altura': 'altura',
        }
        
        # === DEBUG: Log de todos os dados extraídos do CC ===
        logger.info(f"[DEBUG build_update CC] extracted_data recebido: {json.dumps(extracted_data, ensure_ascii=False, default=str)}")
        
        for src_key, dest_key in field_mapping.items():
            value = clean_value(extracted_data.get(src_key))
            
            # === DEBUG: Log para cada campo do CC ===
            if src_key == 'nif':
                raw_value = extracted_data.get(src_key)
                logger.info(f"[DEBUG NIF] raw='{raw_value}', após clean='{value}'")
            
            if value:
                # Validação especial para NIF
                if dest_key == 'nif':
                    nif_valid = is_valid_nif(value)
                    logger.info(f"[DEBUG NIF] Validação: valor='{value}', válido={nif_valid}")
                    if not nif_valid:
                        logger.warning(f"CC: NIF {value} inválido - ignorado")
                        continue
                # Validação especial para documento_id
                if dest_key == 'documento_id' and value in ['123456789', '12345678']:
                    logger.warning(f"CC: documento_id {value} é placeholder - ignorado")
                    continue
                personal_update[dest_key] = value
                track_mapped(src_key)
        
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
        
        if extracted_data.get('email'):
            update_data["client_email"] = sanitize_email(extracted_data['email'])
            
    elif document_type in ['recibo_vencimento', 'irs']:
        # Dados financeiros (PT e UK)
        # SUPORTA DADOS DE CÔNJUGE NO IRS
        financial_update = {}
        personal_update = {}
        
        logger.info(f"[RECIBO/IRS] Dados extraídos: {json.dumps(extracted_data, ensure_ascii=False, default=str)[:2000]}")
        
        # Função para converter valor monetário
        def parse_money(value):
            if not value:
                return None
            try:
                if isinstance(value, (int, float)):
                    return float(value)
                val_str = str(value).replace('€', '').replace(',', '.').replace(' ', '').strip()
                return float(val_str)
            except (ValueError, TypeError):
                return None
        
        # Mapeamento direto de campos
        field_mapping = {
            'salario_liquido': 'rendimento_mensal',
            'rendimento_liquido_mensal': 'rendimento_mensal',
            'salario_bruto': 'rendimento_bruto_mensal',
            'empresa': 'empresa',
            'tipo_contrato': 'tipo_contrato',
            'categoria_profissional': 'categoria_profissional',
            'rendimento_liquido_anual': 'rendimento_anual',
            # Campos adicionais do recibo
            'nome_funcionario': '_nome_func',
            'nif': '_nif_func',
            'descontos_irs': 'descontos_irs',
            'descontos_ss': 'descontos_ss',
            'subsidio_alimentacao': 'subsidio_alimentacao',
            # UK fields
            'net_pay': 'rendimento_liquido',
            'total_payments': 'rendimento_bruto',
            'gross_pay': 'rendimento_bruto',
        }
        
        for src_key, dest_key in field_mapping.items():
            value = extracted_data.get(src_key)
            if value:
                # Converter valores monetários
                if dest_key in ['rendimento_mensal', 'rendimento_bruto_mensal', 'rendimento_bruto', 
                               'rendimento_liquido', 'rendimento_anual', 'descontos_irs', 
                               'descontos_ss', 'subsidio_alimentacao']:
                    value = parse_money(value)
                
                if value and not dest_key.startswith('_'):
                    financial_update[dest_key] = value
                elif value and dest_key == '_nif_func':
                    personal_update['nif'] = value
        
        # === PROCESSAR CÔNJUGE DO IRS (se existir) ===
        if extracted_data.get('nif_titular_2') or extracted_data.get('nome_titular_2'):
            co_spouse = {
                "nome": extracted_data.get('nome_titular_2'),
                "nif": extracted_data.get('nif_titular_2')
            }
            co_spouse = {k: v for k, v in co_spouse.items() if v}
            if co_spouse:
                update_data["co_applicants"] = [
                    {
                        "nome": extracted_data.get('nome_titular'),
                        "nif": extracted_data.get('nif_titular')
                    },
                    co_spouse
                ]
                logger.info(f"IRS conjunto detectado: {extracted_data.get('nome_titular')} + {co_spouse.get('nome')}")
        
        # Tentar extrair de estruturas aninhadas (recibos PT e UK)
        funcionario = extracted_data.get('funcionario', {})
        employee = extracted_data.get('employee', {})
        payment = extracted_data.get('payment', extracted_data.get('payment_details', {}))
        recibo = extracted_data.get('recibo', {})
        empresa_raw = extracted_data.get('empresa')
        employer = extracted_data.get('employer', {})
        
        # Normalizar empresa (pode vir como string ou dict)
        empresa = {}
        if isinstance(empresa_raw, str):
            empresa = {'nome': empresa_raw}
        elif isinstance(empresa_raw, dict):
            empresa = empresa_raw
        
        # Normalizar employer (pode vir como string ou dict)
        if isinstance(employer, str):
            employer = {'name': employer}
        
        # Dados do funcionário/employee
        if funcionario.get('nif'):
            personal_update['nif'] = funcionario['nif']
        if funcionario.get('niss'):
            personal_update['niss'] = funcionario['niss']
        if funcionario.get('categoria'):
            financial_update['categoria_profissional'] = funcionario['categoria']
        if funcionario.get('retribuicao_mensal'):
            financial_update['rendimento_mensal'] = funcionario['retribuicao_mensal']
        
        # NIF do titular (IRS)
        if extracted_data.get('nif_titular'):
            personal_update['nif'] = extracted_data['nif_titular']
        
        # Estado civil do IRS
        if extracted_data.get('estado_civil_fiscal'):
            estado = extracted_data['estado_civil_fiscal'].lower()
            if 'casad' in estado:
                personal_update['estado_civil'] = 'casado'
            elif 'soltei' in estado:
                personal_update['estado_civil'] = 'solteiro'
            elif 'uni' in estado or 'facto' in estado:
                personal_update['estado_civil'] = 'uniao_facto'
            elif 'divorc' in estado:
                personal_update['estado_civil'] = 'divorciado'
            elif 'viuv' in estado:
                personal_update['estado_civil'] = 'viuvo'
            else:
                personal_update['estado_civil'] = estado
            
        # UK employee
        if employee.get('national_insurance_number'):
            personal_update['ni_number'] = employee['national_insurance_number']
            
        # Pagamentos
        if payment.get('net_pay'):
            financial_update['rendimento_liquido'] = payment['net_pay']
        if payment.get('total_payments'):
            financial_update['rendimento_bruto'] = payment['total_payments']
        if recibo.get('total_liquido') or recibo.get('valor_total'):
            financial_update['rendimento_liquido'] = recibo.get('total_liquido') or recibo.get('valor_total')
            
        # Empresa/Employer
        if empresa.get('nome'):
            financial_update['empresa'] = empresa['nome']
        if employer.get('name'):
            financial_update['empresa'] = employer['name']
        
        if financial_update:
            existing_financial = existing_data.get("financial_data") or {}
            existing_financial.update(financial_update)
            update_data["financial_data"] = existing_financial
            
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
            
    elif document_type == 'contrato_trabalho':
        # Declaração de efetividade / Contrato de trabalho
        financial_update = {}
        personal_update = {}
        
        colaboradora = extracted_data.get('colaboradora', extracted_data.get('funcionario', {}))
        empresa_raw = extracted_data.get('empresa', {})
        
        # Normalizar empresa (pode vir como string ou dict)
        empresa = {}
        if isinstance(empresa_raw, str):
            empresa = {'nome': empresa_raw}
        elif isinstance(empresa_raw, dict):
            empresa = empresa_raw
        
        if colaboradora.get('tipo_contrato'):
            financial_update['tipo_contrato'] = colaboradora['tipo_contrato']
        if colaboradora.get('data_inicio'):
            financial_update['data_inicio_trabalho'] = colaboradora['data_inicio']
        if colaboradora.get('CC'):
            personal_update['documento_id'] = colaboradora['CC']
        if colaboradora.get('nif'):
            personal_update['nif'] = colaboradora['nif']
            
        if empresa.get('nome'):
            financial_update['empresa'] = empresa['nome']
            
        # UK employment confirmation
        content = extracted_data.get('content', {})
        employment = content.get('employment_status', {})
        if employment.get('establishment'):
            financial_update['empresa'] = employment['establishment']
        if employment.get('start_date'):
            financial_update['data_inicio_trabalho'] = employment['start_date']
        if employment.get('hourly_rate'):
            financial_update['valor_hora'] = employment['hourly_rate']
        if employment.get('hours_per_week'):
            financial_update['horas_semanais'] = employment['hours_per_week']
            
        if financial_update:
            existing_financial = existing_data.get("financial_data") or {}
            existing_financial.update(financial_update)
            update_data["financial_data"] = existing_financial
            
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
            
    elif document_type == 'caderneta_predial':
        # Dados do imóvel
        real_estate_update = {}
        field_mapping = {
            'artigo_matricial': 'artigo_matricial',
            'valor_patrimonial_tributario': 'valor_patrimonial',
            'area_bruta': 'area',
            'localizacao': 'localizacao',
            'tipologia': 'tipologia',
        }
        
        for src_key, dest_key in field_mapping.items():
            if extracted_data.get(src_key):
                real_estate_update[dest_key] = extracted_data[src_key]
        
        if real_estate_update:
            existing_real_estate = existing_data.get("real_estate_data") or {}
            existing_real_estate.update(real_estate_update)
            update_data["real_estate_data"] = existing_real_estate
    
    elif document_type == 'certidao':
        # Certidão de domicílio fiscal - dados pessoais
        personal_update = {}
        
        # Tentar extrair de estrutura aninhada (certidao.domicilio_fiscal, etc.)
        certidao = extracted_data.get('certidao', {})
        domicilio = certidao.get('domicilio_fiscal', {})
        contribuinte = certidao.get('contribuinte', {})
        
        if domicilio.get('endereco'):
            personal_update['morada'] = domicilio['endereco']
        if domicilio.get('codigo_postal'):
            personal_update['codigo_postal'] = domicilio['codigo_postal']
        if contribuinte.get('nif') or contribuinte.get('numero_contribuinte'):
            personal_update['nif'] = contribuinte.get('nif') or contribuinte.get('numero_contribuinte')
        
        # Também verificar campos de nível superior
        if extracted_data.get('nif'):
            personal_update['nif'] = extracted_data['nif']
        if extracted_data.get('morada'):
            personal_update['morada'] = extracted_data['morada']
            
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
            
    elif document_type == 'simulacao_credito':
        # Simulação de crédito - dados financeiros e imobiliários
        # SUPORTA MÚLTIPLOS PROPONENTES
        financial_update = {}
        real_estate_update = {}
        personal_update = {}
        
        # Extrair de estrutura aninhada
        simulacao = extracted_data.get('simulacao_credito_habitacao', extracted_data)
        dados_imovel = simulacao.get('dados_imovel', simulacao.get('imovel', {}))
        resumo = simulacao.get('resumo_simulacao', simulacao.get('credito', {}))
        proponente = simulacao.get('dados_proponente', {})
        
        # === PROCESSAR MÚLTIPLOS PROPONENTES ===
        proponentes = extracted_data.get('proponentes', [])
        if not proponentes and simulacao.get('proponentes'):
            proponentes = simulacao.get('proponentes', [])
        
        # Array para guardar dados de todos os proponentes
        co_applicants = []
        rendimento_total = 0
        
        for i, prop in enumerate(proponentes):
            if not prop or not isinstance(prop, dict):
                continue
            
            applicant_data = {
                "nome": prop.get('nome'),
                "nif": prop.get('nif'),
                "data_nascimento": prop.get('data_nascimento'),
                "rendimento_mensal": prop.get('rendimento_mensal'),
                "entidade_patronal": prop.get('entidade_patronal')
            }
            
            # Remover campos vazios
            applicant_data = {k: v for k, v in applicant_data.items() if v}
            
            if applicant_data.get('nome') or applicant_data.get('nif'):
                co_applicants.append(applicant_data)
                
                # Somar rendimentos
                if applicant_data.get('rendimento_mensal'):
                    try:
                        rendimento_total += float(applicant_data['rendimento_mensal'])
                    except (ValueError, TypeError):
                        pass
                
                # O primeiro proponente vai para personal_data principal
                if i == 0:
                    if applicant_data.get('nif'):
                        personal_update['nif'] = applicant_data['nif']
                    if applicant_data.get('data_nascimento'):
                        personal_update['data_nascimento'] = applicant_data['data_nascimento']
                    if applicant_data.get('rendimento_mensal'):
                        financial_update['rendimento_mensal'] = applicant_data['rendimento_mensal']
        
        # Guardar array de co-proponentes se houver mais de 1
        if len(co_applicants) > 1:
            update_data["co_applicants"] = co_applicants
            # Guardar rendimento agregado
            if rendimento_total > 0:
                financial_update['rendimento_agregado'] = rendimento_total
            logger.info(f"Simulação com {len(co_applicants)} proponentes detectados, rendimento total: {rendimento_total}")
        
        # Dados financeiros do crédito
        if resumo.get('financiamento_total') or resumo.get('montante_financiamento'):
            financial_update['valor_pretendido'] = resumo.get('financiamento_total') or resumo.get('montante_financiamento')
        if resumo.get('prestacao_mensal'):
            financial_update['prestacao_estimada'] = resumo['prestacao_mensal']
        if resumo.get('prazo_anos'):
            financial_update['prazo_anos'] = resumo['prazo_anos']
        if resumo.get('taxa_juro'):
            financial_update['taxa_juro'] = resumo['taxa_juro']
        if resumo.get('spread'):
            financial_update['spread'] = resumo['spread']
        if resumo.get('taeg'):
            financial_update['taeg'] = resumo['taeg']
        if extracted_data.get('montante_financiamento'):
            financial_update['valor_pretendido'] = extracted_data['montante_financiamento']
        if extracted_data.get('banco'):
            financial_update['banco'] = extracted_data['banco']
            
        # Dados do imóvel
        if dados_imovel.get('valor_aquisicao_imovel') or dados_imovel.get('valor_aquisicao'):
            real_estate_update['valor_imovel'] = dados_imovel.get('valor_aquisicao_imovel') or dados_imovel.get('valor_aquisicao')
        if dados_imovel.get('localizacao_imovel') or dados_imovel.get('localizacao'):
            real_estate_update['localizacao'] = dados_imovel.get('localizacao_imovel') or dados_imovel.get('localizacao')
            
        # Dados pessoais do proponente único (fallback)
        if not proponentes and proponente:
            if proponente.get('nif'):
                personal_update['nif'] = proponente['nif']
            if proponente.get('data_nascimento'):
                personal_update['data_nascimento'] = proponente['data_nascimento']
            
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
            
        if financial_update:
            existing_financial = existing_data.get("financial_data") or {}
            existing_financial.update(financial_update)
            update_data["financial_data"] = existing_financial
            
        if real_estate_update:
            existing_real_estate = existing_data.get("real_estate_data") or {}
            existing_real_estate.update(real_estate_update)
            update_data["real_estate_data"] = existing_real_estate
    
    elif document_type == 'mapa_crc':
        # Mapa Central de Responsabilidades de Crédito - NOVO FORMATO
        financial_update = {}
        personal_update = {}
        
        # === NOVO FORMATO: Extrair dados do titular ===
        titular = extracted_data.get('titular', {})
        if titular.get('nome'):
            # Não sobrescrever nome do cliente
            pass
        if titular.get('nif'):
            personal_update['nif'] = titular['nif']
        
        # === NOVO FORMATO: Extrair resumo ===
        resumo = extracted_data.get('resumo', {})
        if resumo:
            if resumo.get('total_divida'):
                financial_update['encargos_totais'] = resumo['total_divida']
                financial_update['divida_total_crc'] = resumo['total_divida']
            if resumo.get('total_em_incumprimento'):
                financial_update['divida_incumprimento'] = resumo['total_em_incumprimento']
            if resumo.get('prestacao_mensal_total'):
                financial_update['prestacao_creditos_mensal'] = resumo['prestacao_mensal_total']
                financial_update['encargos_mensais'] = resumo['prestacao_mensal_total']
            if resumo.get('numero_produtos'):
                financial_update['numero_creditos_ativos'] = resumo['numero_produtos']
        
        # === FORMATO ANTIGO: Fallback ===
        if not resumo:
            resumo_old = extracted_data.get('resumo_responsabilidades_credito', {})
            montante = resumo_old.get('montante_em_divida', {})
            if montante.get('total'):
                financial_update['divida_total_crc'] = montante['total']
            if montante.get('em_incumprimento'):
                financial_update['divida_incumprimento'] = montante['em_incumprimento']
        
        # === EXTRAIR LISTA DE CRÉDITOS ===
        creditos = extracted_data.get('creditos', [])
        if not creditos:
            # Fallback para formato antigo
            creditos = extracted_data.get('responsabilidades_credito', [])
        
        if creditos:
            # Guardar lista de créditos detalhada
            creditos_processados = []
            prestacao_total = 0
            divida_total = 0
            tem_credito_habitacao = False
            
            for credito in creditos:
                if not isinstance(credito, dict):
                    continue
                
                # Normalizar dados do crédito
                credito_info = {
                    'instituicao': credito.get('instituicao') or credito.get('entidade_participante'),
                    'tipo': credito.get('tipo_produto') or credito.get('produto_financeiro', 'Outro'),
                    'valor_divida': credito.get('valor_em_divida') or credito.get('montantes', {}).get('total_em_divida', 0),
                    'prestacao': credito.get('prestacao_mensal') or credito.get('prestacao', {}).get('valor', 0),
                    'data_fim': credito.get('data_fim') or credito.get('fim'),
                    'em_incumprimento': credito.get('em_incumprimento', False)
                }
                
                # Converter valores para float
                try:
                    if credito_info['valor_divida']:
                        credito_info['valor_divida'] = float(str(credito_info['valor_divida']).replace(',', '.').replace('€', '').strip())
                        divida_total += credito_info['valor_divida']
                except (ValueError, TypeError):
                    pass
                    
                try:
                    if credito_info['prestacao']:
                        credito_info['prestacao'] = float(str(credito_info['prestacao']).replace(',', '.').replace('€', '').strip())
                        if credito_info['prestacao'] > 0:
                            prestacao_total += credito_info['prestacao']
                except (ValueError, TypeError):
                    pass
                
                # Verificar se é crédito habitação
                tipo_lower = str(credito_info['tipo']).lower()
                if 'habitação' in tipo_lower or 'habitacao' in tipo_lower or 'hipoteca' in tipo_lower:
                    tem_credito_habitacao = True
                    financial_update['credito_habitacao_existente'] = credito_info['valor_divida']
                    financial_update['prestacao_ch_atual'] = credito_info['prestacao']
                
                creditos_processados.append(credito_info)
            
            # Guardar lista completa de créditos
            if creditos_processados:
                financial_update['creditos_ativos'] = creditos_processados
                financial_update['numero_creditos_ativos'] = len(creditos_processados)
            
            # Calcular totais se não vieram no resumo
            if not financial_update.get('divida_total_crc') and divida_total > 0:
                financial_update['divida_total_crc'] = round(divida_total, 2)
                financial_update['encargos_totais'] = round(divida_total, 2)
            
            if not financial_update.get('prestacao_creditos_mensal') and prestacao_total > 0:
                financial_update['prestacao_creditos_mensal'] = round(prestacao_total, 2)
                financial_update['encargos_mensais'] = round(prestacao_total, 2)
            
            financial_update['tem_credito_habitacao_existente'] = tem_credito_habitacao
        
        logger.info(f"[MAPA CRC] Dados extraídos: {json.dumps(financial_update, ensure_ascii=False, default=str)}")
        
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
                    
        if financial_update:
            existing_financial = existing_data.get("financial_data") or {}
            existing_financial.update(financial_update)
            update_data["financial_data"] = existing_financial
    
    elif document_type == 'cpcv':
        # Contrato Promessa Compra e Venda - dados do negócio
        # SUPORTA MÚLTIPLOS COMPRADORES
        financial_update = {}
        real_estate_update = {}
        personal_update = {}
        
        # === DEBUG: Log de dados extraídos do CPCV ===
        logger.info(f"[DEBUG CPCV] extracted_data keys: {list(extracted_data.keys())}")
        
        # Extrair de estrutura aninhada
        cpcv = extracted_data.get('cpcv', extracted_data)
        imovel = cpcv.get('imovel', cpcv.get('dados_imovel', {}))
        valores = cpcv.get('valores', cpcv.get('condicoes_financeiras', {}))
        datas = cpcv.get('datas', {})
        vendedor = cpcv.get('vendedor', extracted_data.get('vendedor', {}))
        condicoes = cpcv.get('condicoes', {})
        mediador = cpcv.get('mediador', {})
        
        logger.info(f"[DEBUG CPCV] imovel: {imovel}")
        logger.info(f"[DEBUG CPCV] valores: {valores}")
        logger.info(f"[DEBUG CPCV] datas: {datas}")
        
        # === PROCESSAR MÚLTIPLOS COMPRADORES ===
        compradores = extracted_data.get('compradores', [])
        if not compradores and cpcv.get('compradores'):
            compradores = cpcv.get('compradores', [])
        
        # Array para guardar dados de todos os compradores
        co_buyers = []
        
        for i, comprador in enumerate(compradores):
            if not comprador or not isinstance(comprador, dict):
                continue
            
            buyer_data = {
                "nome": comprador.get('nome_completo') or comprador.get('nome'),
                "nif": comprador.get('nif'),
                "cc": comprador.get('cc'),
                "estado_civil": comprador.get('estado_civil'),
                "regime_bens": comprador.get('regime_bens'),
                "profissao": comprador.get('profissao'),
                "morada": comprador.get('morada'),
                "codigo_postal": comprador.get('codigo_postal'),
                "localidade": comprador.get('localidade'),
                "email": comprador.get('email'),
                "telefone": comprador.get('telefone')
            }
            
            # Remover campos vazios
            buyer_data = {k: v for k, v in buyer_data.items() if v}
            
            if buyer_data.get('nome') or buyer_data.get('nif'):
                co_buyers.append(buyer_data)
                
                # O primeiro comprador vai para personal_data principal
                if i == 0:
                    if buyer_data.get('nif'):
                        personal_update['nif'] = buyer_data['nif']
                    if buyer_data.get('cc'):
                        personal_update['documento_id'] = buyer_data['cc']
                    if buyer_data.get('morada'):
                        personal_update['morada'] = buyer_data['morada']
                    if buyer_data.get('codigo_postal'):
                        personal_update['codigo_postal'] = buyer_data['codigo_postal']
                    if buyer_data.get('estado_civil'):
                        personal_update['estado_civil'] = buyer_data['estado_civil']
                    if buyer_data.get('profissao'):
                        personal_update['profissao'] = buyer_data['profissao']
                    if buyer_data.get('email'):
                        update_data['client_email'] = sanitize_email(buyer_data['email'])
                    if buyer_data.get('telefone'):
                        update_data['client_phone'] = buyer_data['telefone']
        
        # Guardar array de co-compradores
        if len(co_buyers) > 0:
            update_data["co_buyers"] = co_buyers
            if len(co_buyers) > 1:
                logger.info(f"CPCV com {len(co_buyers)} compradores detectados")
        
        # === DADOS DO VENDEDOR ===
        if vendedor:
            vendedor_data = {
                "nome": vendedor.get('nome'),
                "nif": vendedor.get('nif'),
                "cc": vendedor.get('cc'),
                "estado_civil": vendedor.get('estado_civil'),
                "morada": vendedor.get('morada'),
                "tipo": vendedor.get('tipo')
            }
            vendedor_data = {k: v for k, v in vendedor_data.items() if v}
            if vendedor_data:
                update_data["vendedor"] = vendedor_data
        
        # === DADOS DO NEGÓCIO / VALORES ===
        # Preço e sinal
        if valores.get('preco_total') or valores.get('valor_venda'):
            real_estate_update['valor_imovel'] = valores.get('preco_total') or valores.get('valor_venda')
        if valores.get('sinal') or valores.get('valor_sinal'):
            financial_update['valor_entrada'] = valores.get('sinal') or valores.get('valor_sinal')
        if valores.get('data_sinal'):
            financial_update['data_sinal'] = valores['data_sinal']
        if valores.get('reforco_sinal'):
            financial_update['reforco_sinal'] = valores['reforco_sinal']
        if valores.get('data_reforco'):
            financial_update['data_reforco'] = valores['data_reforco']
        if valores.get('valor_restante') or valores.get('valor_escritura'):
            financial_update['valor_financiar'] = valores.get('valor_restante') or valores.get('valor_escritura')
        if valores.get('valor_financiamento'):
            financial_update['valor_pretendido'] = valores['valor_financiamento']
        
        # Comissões
        if valores.get('comissao_mediacao'):
            financial_update['comissao_mediacao'] = valores['comissao_mediacao']
        if valores.get('percentagem_comissao'):
            financial_update['percentagem_comissao'] = valores['percentagem_comissao']
        if valores.get('quem_paga_comissao'):
            financial_update['quem_paga_comissao'] = valores['quem_paga_comissao']
            
        # === DATAS IMPORTANTES ===
        if datas.get('data_cpcv'):
            real_estate_update['data_cpcv'] = datas['data_cpcv']
        if datas.get('data_escritura_prevista'):
            real_estate_update['data_escritura_prevista'] = datas['data_escritura_prevista']
        if datas.get('prazo_escritura_dias'):
            real_estate_update['prazo_escritura_dias'] = datas['prazo_escritura_dias']
        if datas.get('data_entrega_chaves'):
            real_estate_update['data_entrega_chaves'] = datas['data_entrega_chaves']
            
        # === DADOS COMPLETOS DO IMÓVEL ===
        imovel_fields = {
            'morada_completa': 'localizacao',
            'localizacao': 'localizacao',
            'morada': 'localizacao',
            'codigo_postal': 'codigo_postal',
            'localidade': 'localidade',
            'freguesia': 'freguesia',
            'concelho': 'concelho',
            'distrito': 'distrito',
            'tipologia': 'tipologia',
            'descricao': 'descricao_imovel',
            'area_bruta': 'area_bruta',
            'area_util': 'area_util',
            'area': 'area',
            'fracao': 'fracao',
            'artigo_matricial': 'artigo_matricial',
            'descricao_predial': 'descricao_predial',
            'conservatoria': 'conservatoria',
            'numero_predial': 'numero_predial',
            'licenca_utilizacao': 'licenca_utilizacao',
            'ano_construcao': 'ano_construcao',
            'certificado_energetico': 'certificado_energetico',
            'estacionamento': 'estacionamento',
            'arrecadacao': 'arrecadacao'
        }
        
        for src_key, dest_key in imovel_fields.items():
            if imovel.get(src_key):
                real_estate_update[dest_key] = imovel[src_key]
        
        # === CONDIÇÕES DO CONTRATO ===
        if condicoes.get('condicao_suspensiva'):
            real_estate_update['condicao_suspensiva'] = condicoes['condicao_suspensiva']
        if condicoes.get('prazo_condicao'):
            real_estate_update['prazo_condicao'] = condicoes['prazo_condicao']
        if condicoes.get('clausula_penalizacao'):
            real_estate_update['clausula_penalizacao'] = condicoes['clausula_penalizacao']
        if condicoes.get('observacoes'):
            real_estate_update['observacoes_cpcv'] = condicoes['observacoes']
        
        # === DADOS DO MEDIADOR ===
        if mediador:
            mediador_data = {
                "nome_empresa": mediador.get('nome_empresa'),
                "nif_empresa": mediador.get('nif_empresa'),
                "licenca_ami": mediador.get('licenca_ami'),
                "consultor": mediador.get('consultor')
            }
            mediador_data = {k: v for k, v in mediador_data.items() if v}
            if mediador_data:
                update_data["mediador"] = mediador_data
            
        # Campos de nível superior (fallback)
        if extracted_data.get('valor_venda'):
            real_estate_update['valor_imovel'] = extracted_data['valor_venda']
        if extracted_data.get('sinal'):
            financial_update['valor_entrada'] = extracted_data['sinal']
        if extracted_data.get('valor_imovel'):
            real_estate_update['valor_imovel'] = extracted_data['valor_imovel']
        if extracted_data.get('entrada') or extracted_data.get('valor_entrada'):
            financial_update['valor_entrada'] = extracted_data.get('entrada') or extracted_data.get('valor_entrada')
        
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
            
        if financial_update:
            existing_financial = existing_data.get("financial_data") or {}
            existing_financial.update(financial_update)
            update_data["financial_data"] = existing_financial
            
        if real_estate_update:
            existing_real_estate = existing_data.get("real_estate_data") or {}
            existing_real_estate.update(real_estate_update)
            update_data["real_estate_data"] = existing_real_estate
        
        # === DEBUG: Log final do CPCV ===
        logger.info(f"[DEBUG CPCV] personal_update: {personal_update}")
        logger.info(f"[DEBUG CPCV] financial_update: {financial_update}")
        logger.info(f"[DEBUG CPCV] real_estate_update: {real_estate_update}")
        logger.info(f"[DEBUG CPCV] update_data keys: {list(update_data.keys())}")
            
    elif document_type == 'dados_imovel':
        # Ficheiros relacionados com o imóvel (fotos, plantas, documentos do imóvel)
        real_estate_update = {}
        
        # Extrair de qualquer estrutura
        imovel = extracted_data.get('imovel', extracted_data.get('dados_imovel', extracted_data))
        
        # Mapeamentos de campos
        field_mapping = {
            'localizacao': 'localizacao',
            'morada': 'localizacao',
            'endereco': 'localizacao',
            'address': 'localizacao',
            'tipologia': 'tipologia',
            'tipo': 'tipologia',
            'area': 'area',
            'area_bruta': 'area',
            'm2': 'area',
            'valor': 'valor_imovel',
            'preco': 'valor_imovel',
            'valor_imovel': 'valor_imovel',
            'valor_aquisicao': 'valor_imovel',
            'artigo': 'artigo_matricial',
            'fracao': 'fracao',
            'andar': 'andar',
            'piso': 'andar',
            'quartos': 'quartos',
            'wc': 'casas_banho',
            'garagem': 'garagem',
            'ano_construcao': 'ano_construcao',
        }
        
        # Procurar campos no objecto imovel
        if isinstance(imovel, dict):
            for src_key, dest_key in field_mapping.items():
                for data_key, data_value in imovel.items():
                    if src_key in data_key.lower() and data_value:
                        real_estate_update[dest_key] = data_value
                        break
        
        # Procurar campos de nível superior
        for src_key, dest_key in field_mapping.items():
            for data_key, data_value in extracted_data.items():
                if src_key in data_key.lower() and data_value and dest_key not in real_estate_update:
                    real_estate_update[dest_key] = data_value
                    break
                    
        if real_estate_update:
            existing_real_estate = existing_data.get("real_estate_data") or {}
            existing_real_estate.update(real_estate_update)
            update_data["real_estate_data"] = existing_real_estate
    
    else:
        # Tipo "outro" - tentar extrair dados genéricos de qualquer estrutura
        personal_update = {}
        financial_update = {}
        real_estate_update = {}
        
        # Função auxiliar para extrair valores de estruturas aninhadas (mais robusta)
        def extract_nested(data, keys_to_find, depth=0):
            if depth > 5:  # Limitar profundidade de recursão
                return {}
            results = {}
            if isinstance(data, dict):
                for key, value in data.items():
                    key_lower = key.lower().replace('_', ' ').replace('-', ' ')
                    for search_key, dest_key in keys_to_find.items():
                        if search_key in key_lower:
                            if isinstance(value, (str, int, float)) and value:
                                # Não sobrescrever se já temos um valor
                                if dest_key not in results:
                                    results[dest_key] = value
                    # Recursão para valores aninhados
                    if isinstance(value, dict):
                        nested = extract_nested(value, keys_to_find, depth + 1)
                        for k, v in nested.items():
                            if k not in results:
                                results[k] = v
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                nested = extract_nested(item, keys_to_find, depth + 1)
                                for k, v in nested.items():
                                    if k not in results:
                                        results[k] = v
            return results
        
        # Mapeamentos para dados pessoais (mais completo)
        personal_keys = {
            'nif': 'nif',
            'numero contribuinte': 'nif',
            'national insurance': 'ni_number',
            'ni number': 'ni_number',
            'data nascimento': 'data_nascimento',
            'date of birth': 'data_nascimento',
            'morada': 'morada',
            'endereco': 'morada',
            'address': 'morada',
            'street': 'morada',
            'codigo postal': 'codigo_postal',
            'postcode': 'codigo_postal',
            'nome': 'nome_completo',
            'name': 'nome_completo',
            'cc': 'documento_id',
        }
        
        # Mapeamentos para dados financeiros (mais completo - inclui UK)
        financial_keys = {
            'salario': 'rendimento_mensal',
            'rendimento': 'rendimento_mensal',
            'vencimento': 'rendimento_mensal',
            'valor total': 'rendimento_mensal',
            'total payments': 'rendimento_mensal',
            'gross pay': 'rendimento_bruto',
            'total gross': 'rendimento_bruto',
            'net pay': 'rendimento_liquido',
            'total liquido': 'rendimento_liquido',
            'valor liquido': 'rendimento_liquido',
            'valor pago': 'rendimento_liquido',
            'total a receber': 'rendimento_liquido',
            'hourly rate': 'valor_hora',
            'valor horario': 'valor_hora',
            'hours': 'horas_trabalho',
            'empresa': 'empresa',
            'employer': 'empresa',
            'organization': 'empresa',
            'entidade empregadora': 'empresa',
            'valor financiamento': 'valor_pretendido',
            'montante financiamento': 'valor_pretendido',
            'financiamento total': 'valor_pretendido',
            'prestacao': 'prestacao_estimada',
            'prestacao mensal': 'prestacao_estimada',
            'tipo contrato': 'tipo_contrato',
            'contract type': 'tipo_contrato',
            'categoria': 'categoria_profissional',
            'position': 'categoria_profissional',
            'cargo': 'categoria_profissional',
            'start date': 'data_inicio_trabalho',
            'data inicio': 'data_inicio_trabalho',
        }
        
        # Mapeamentos para dados imobiliários
        real_estate_keys = {
            'valor imovel': 'valor_imovel',
            'valor aquisicao': 'valor_imovel',
            'valor estimado': 'valor_imovel',
            'area': 'area',
            'tipologia': 'tipologia',
            'localizacao': 'localizacao',
        }
        
        personal_update = extract_nested(extracted_data, personal_keys)
        financial_update = extract_nested(extracted_data, financial_keys)
        real_estate_update = extract_nested(extracted_data, real_estate_keys)
        
        # Validar nome_completo antes de usar
        if personal_update.get("nome_completo"):
            if not is_valid_person_name(personal_update["nome_completo"]):
                # Nome parece ser de empresa/seguradora, remover
                logger.warning(f"Nome rejeitado (parece empresa): {personal_update['nome_completo']}")
                del personal_update["nome_completo"]
        
        if personal_update:
            existing_personal = existing_data.get("personal_data") or {}
            existing_personal.update(personal_update)
            update_data["personal_data"] = existing_personal
        
        if financial_update:
            existing_financial = existing_data.get("financial_data") or {}
            existing_financial.update(financial_update)
            update_data["financial_data"] = existing_financial
            
        if real_estate_update:
            existing_real_estate = existing_data.get("real_estate_data") or {}
            existing_real_estate.update(real_estate_update)
            update_data["real_estate_data"] = existing_real_estate
    
    # Recolher dados não mapeados e guardar nas observações
    unmapped_data = collect_unmapped_data(extracted_data, mapped_fields, document_type)
    if unmapped_data:
        existing_notes = existing_data.get("ai_extracted_notes", "")
        new_notes = format_unmapped_data_for_notes(unmapped_data, document_type)
        if new_notes:
            if existing_notes:
                update_data["ai_extracted_notes"] = existing_notes + "\n\n" + new_notes
            else:
                update_data["ai_extracted_notes"] = new_notes
    
    # === LOG FINAL DO UPDATE_DATA ===
    logger.info(f"[BUILD_UPDATE] Tipo: {document_type}, Campos a actualizar: {list(update_data.keys())}")
    if update_data.get('financial_data'):
        logger.info(f"[BUILD_UPDATE] financial_data: {json.dumps(update_data['financial_data'], ensure_ascii=False, default=str)[:1000]}")
    if update_data.get('personal_data'):
        logger.info(f"[BUILD_UPDATE] personal_data: {json.dumps(update_data['personal_data'], ensure_ascii=False, default=str)[:500]}")
    
    return update_data


def collect_unmapped_data(extracted_data: Dict[str, Any], mapped_fields: set, document_type: str) -> Dict[str, Any]:
    """
    Recolher dados extraídos que não foram mapeados para campos existentes.
    """
    unmapped = {}
    
    # Campos a ignorar (metadados, campos vazios, etc.)
    ignore_fields = {
        'documento', 'tipo', 'tipo_documento', 'document_type', 
        'raw_text', 'confidence', 'source', 'filename',
        'updated_at', 'created_at', '_id', 'id'
    }
    
    def extract_unmapped(data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        result = {}
        if not isinstance(data, dict):
            return result
            
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            key_lower = key.lower()
            
            # Ignorar campos já mapeados ou na lista de ignorar
            if key_lower in mapped_fields or key_lower in ignore_fields:
                continue
            
            # Ignorar valores vazios
            if value is None or value == "" or value == [] or value == {}:
                continue
            
            # Se é um dict, processar recursivamente
            if isinstance(value, dict):
                nested = extract_unmapped(value, full_key)
                result.update(nested)
            elif isinstance(value, list):
                # Converter listas para string
                if all(isinstance(item, (str, int, float)) for item in value):
                    result[full_key] = ", ".join(str(v) for v in value)
                elif value:
                    # Lista de dicts - tentar extrair
                    for i, item in enumerate(value[:3]):  # Limitar a 3 items
                        if isinstance(item, dict):
                            nested = extract_unmapped(item, f"{full_key}[{i}]")
                            result.update(nested)
            else:
                result[full_key] = value
        
        return result
    
    unmapped = extract_unmapped(extracted_data)
    return unmapped


def format_unmapped_data_for_notes(unmapped_data: Dict[str, Any], document_type: str) -> str:
    """
    Formatar dados não mapeados para texto legível nas observações.
    """
    if not unmapped_data:
        return ""
    
    # Traduzir nomes de campos comuns
    field_translations = {
        'nome_completo': 'Nome Completo',
        'data_validade': 'Data de Validade',
        'entidade_emissora': 'Entidade Emissora',
        'numero_seguranca_social': 'Nº Segurança Social',
        'taxa_juro': 'Taxa de Juro',
        'prazo': 'Prazo',
        'spread': 'Spread',
        'euribor': 'Euribor',
        'tan': 'TAN',
        'taeg': 'TAEG',
        'seguro_vida': 'Seguro de Vida',
        'seguro_multirriscos': 'Seguro Multirriscos',
        'comissao': 'Comissão',
        'despesas': 'Despesas',
        'imposto_selo': 'Imposto de Selo',
    }
    
    lines = []
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    lines.append(f"--- Dados extraídos por IA ({document_type}) em {timestamp} ---")
    
    for key, value in unmapped_data.items():
        # Limpar e traduzir nome do campo
        clean_key = key.split('.')[-1].replace('_', ' ').title()
        for orig, trans in field_translations.items():
            if orig in key.lower():
                clean_key = trans
                break
        
        # Formatar valor
        if isinstance(value, (int, float)):
            if 'valor' in key.lower() or 'preco' in key.lower() or 'montante' in key.lower():
                formatted_value = f"€{value:,.2f}".replace(',', ' ')
            elif 'taxa' in key.lower() or 'spread' in key.lower() or 'percentagem' in key.lower():
                formatted_value = f"{value}%"
            else:
                formatted_value = str(value)
        else:
            formatted_value = str(value)
        
        lines.append(f"• {clean_key}: {formatted_value}")
    
    return "\n".join(lines)



# ====================================================================
# TAREFA 2: GESTÃO DE CONFLITOS DE DADOS IA
# ====================================================================

import uuid as uuid_module


def check_data_conflicts(
    existing_data,
    new_data,
    section,
    document_filename=None
):
    """
    TAREFA 2: Verificar conflitos entre dados existentes e dados extraídos pela IA.
    
    Args:
        existing_data: Dados actuais do processo (ex: personal_data)
        new_data: Dados extraídos pela IA
        section: Nome da secção (personal_data, financial_data, etc.)
        document_filename: Nome do documento de onde os dados foram extraídos
    
    Returns:
        Lista de conflitos encontrados
    """
    conflicts = []
    
    if not new_data:
        return conflicts
    
    existing = existing_data or {}
    now = datetime.now(timezone.utc).isoformat()
    
    # Campos que podem gerar conflitos
    conflict_fields = {
        "personal_data": [
            "nif", "documento_id", "naturalidade", "nacionalidade", 
            "morada_fiscal", "birth_date", "data_nascimento", "estado_civil",
            "data_validade_cc", "sexo", "altura", "nome_pai", "nome_mae"
        ],
        "financial_data": [
            "salario_bruto", "salario_liquido", "rendimento_anual",
            "renda_habitacao_atual", "capital_proprio", "acesso_portal_financas"
        ],
        "real_estate_data": [
            "valor_imovel", "localidade", "tipologia", "area_util", 
            "area_bruta", "artigo_matricial", "conservatoria", "numero_predial"
        ]
    }
    
    fields_to_check = conflict_fields.get(section, list(new_data.keys()))
    
    for field in fields_to_check:
        if field not in new_data:
            continue
        
        new_value = new_data[field]
        current_value = existing.get(field)
        
        # Se não há valor actual, não é conflito
        if current_value is None or current_value == "" or current_value == []:
            continue
        
        # Se os valores são iguais, não é conflito
        if str(current_value).strip().lower() == str(new_value).strip().lower():
            continue
        
        # Conflito detectado!
        conflicts.append({
            "id": str(uuid_module.uuid4()),
            "field": field,
            "field_path": f"{section}.{field}",
            "current": current_value,
            "suggested": new_value,
            "document": document_filename,
            "detected_at": now
        })
    
    return conflicts


def merge_data_with_conflicts(process, mapped_data, document_filename=None):
    """
    TAREFA 2: Fundir dados extraídos pela IA com dados existentes,
    gerando sugestões para campos em conflito.
    
    Se is_data_confirmed=True, não extrai dados de perfil (apenas classifica documento).
    
    Args:
        process: Documento do processo actual
        mapped_data: Dados mapeados pela IA
        document_filename: Nome do documento analisado
    
    Returns:
        Dict com update_data, ai_suggestions, skipped
    """
    update_data = {}
    new_suggestions = []
    skipped = False
    
    # Se dados confirmados, não extrair dados de perfil
    if process.get("is_data_confirmed", False):
        skipped = True
        logger.info(f"Processo {process.get('id')} tem dados confirmados - ignorando extracção de perfil")
        return {
            "update_data": update_data,
            "ai_suggestions": new_suggestions,
            "skipped": skipped
        }
    
    # Secções a processar
    sections = ["personal_data", "financial_data", "real_estate_data"]
    
    for section in sections:
        if section not in mapped_data:
            continue
        
        new_data = mapped_data[section]
        existing_data = process.get(section, {})
        
        # Verificar conflitos
        conflicts = check_data_conflicts(existing_data, new_data, section, document_filename)
        
        # Preparar dados para actualização (apenas campos sem conflito)
        conflict_fields = {c["field"] for c in conflicts}
        
        section_update = {}
        for field, value in new_data.items():
            if field in conflict_fields:
                continue  # Este campo tem conflito, não actualizar
            
            current = existing_data.get(field)
            if current is None or current == "" or current == []:
                section_update[field] = value
        
        if section_update:
            update_data[section] = {**existing_data, **section_update}
        
        new_suggestions.extend(conflicts)
    
    # Campos de topo (client_name, etc.)
    if "name" in mapped_data and mapped_data["name"]:
        current_name = process.get("client_name")
        if not current_name or current_name.strip() == "":
            update_data["client_name"] = mapped_data["name"]
        elif current_name.lower().strip() != mapped_data["name"].lower().strip():
            new_suggestions.append({
                "id": str(uuid_module.uuid4()),
                "field": "client_name",
                "field_path": "client_name",
                "current": current_name,
                "suggested": mapped_data["name"],
                "document": document_filename,
                "detected_at": datetime.now(timezone.utc).isoformat()
            })
    
    return {
        "update_data": update_data,
        "ai_suggestions": new_suggestions,
        "skipped": skipped
    }
