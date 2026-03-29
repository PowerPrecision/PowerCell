"""
====================================================================
FILE CONVERTER SERVICE - CONVERSÃO AUTOMÁTICA DE FICHEIROS
====================================================================
Serviço para converter ficheiros inválidos para formatos aceites.

Funcionalidades:
- Detecta o tipo real do ficheiro (magic bytes)
- Converte imagens para PDF
- Converte texto para PDF
- Analisa ficheiros desconhecidos com IA
- Rejeita ficheiros perigosos (executáveis, scripts)

Formatos de entrada suportados:
- Imagens: JPEG, PNG, GIF, BMP, TIFF, WEBP, HEIC/HEIF
- Documentos: PDF, texto plano, RTF
- Office: DOCX, XLSX (conversão para PDF)
- Ficheiros embrulhados: Java serialization, base64

Formatos de saída:
- PDF (preferencial para documentos)
- JPEG/PNG (como fallback)

====================================================================
"""
import io
import os
import logging
import base64
import tempfile
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Tentar importar bibliotecas de conversão
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("[CONVERTER] PIL não disponível - conversão de imagens limitada")

try:
    import img2pdf
    IMG2PDF_AVAILABLE = True
except ImportError:
    IMG2PDF_AVAILABLE = False
    logger.warning("[CONVERTER] img2pdf não disponível")

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("[CONVERTER] reportlab não disponível")

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logger.warning("[CONVERTER] python-magic não disponível")

# Magic bytes para identificação de formatos
MAGIC_BYTES = {
    # Imagens
    b'\xff\xd8\xff': ('image/jpeg', 'jpeg'),
    b'\x89PNG\r\n\x1a\n': ('image/png', 'png'),
    b'GIF87a': ('image/gif', 'gif'),
    b'GIF89a': ('image/gif', 'gif'),
    b'BM': ('image/bmp', 'bmp'),
    b'II*\x00': ('image/tiff', 'tiff'),
    b'MM\x00*': ('image/tiff', 'tiff'),
    b'RIFF': ('image/webp', 'webp'),  # WebP começa com RIFF
    
    # Documentos
    b'%PDF': ('application/pdf', 'pdf'),
    b'PK\x03\x04': ('application/zip', 'zip'),  # ZIP, DOCX, XLSX
    
    # Texto
    b'%!PS': ('application/postscript', 'ps'),
    
    # Java serialization
    b'\xac\xed\x00\x05': ('application/java-serialization', 'java-ser'),
    
    # Áudio/Vídeo (não convertíveis)
    b'\x00\x00\x00\x1c': ('video/quicktime', 'mov'),  # HEIC pode começar assim
    b'\x00\x00\x00\x20ftyp': ('video/quicktime', 'mov'),
}

# Tipos de ficheiros que podem ser convertidos
CONVERTIBLE_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 
    'image/tiff', 'image/webp', 'image/heic', 'image/heif',
    'text/plain', 'text/html', 'text/rtf',
    'application/rtf',
}

# Tipos perigosos que nunca devem ser convertidos
DANGEROUS_TYPES = {
    'application/x-executable', 'application/x-msdos-program',
    'application/x-msdownload', 'application/x-sh',
    'application/x-shellscript', 'application/x-bat',
    'application/javascript', 'text/javascript',
    'application/x-python-code', 'application/x-php',
}


def detect_file_type(content: bytes) -> Tuple[str, str, float]:
    """
    Detecta o tipo de ficheiro baseado em magic bytes.
    
    Args:
        content: Conteúdo binário do ficheiro
        
    Returns:
        Tuple (mime_type, extension, confidence)
    """
    if not content or len(content) < 4:
        return 'application/octet-stream', 'bin', 0.0
    
    # Verificar magic bytes conhecidos
    for magic, (mime_type, ext) in MAGIC_BYTES.items():
        if content.startswith(magic):
            return mime_type, ext, 0.95
    
    # Usar python-magic se disponível
    if MAGIC_AVAILABLE:
        try:
            detected = magic.from_buffer(content, mime=True)
            if detected and detected != 'application/octet-stream':
                return detected, detected.split('/')[-1], 0.85
        except Exception as e:
            logger.debug(f"[CONVERTER] Erro no magic: {e}")
    
    # Verificar se é texto (ASCII/UTF-8 válido)
    try:
        text = content.decode('utf-8')
        # Se decodifica como UTF-8 válido, provavelmente é texto
        if text.isprintable() or '\n' in text or '\t' in text:
            return 'text/plain', 'txt', 0.7
    except UnicodeDecodeError:
        pass
    
    # Verificar se é base64 válido
    try:
        text = content.decode('ascii').strip()
        if len(text) % 4 == 0 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in text):
            return 'application/base64', 'b64', 0.6
    except (UnicodeDecodeError, AttributeError):
        pass
    
    return 'application/octet-stream', 'bin', 0.3


def is_convertible(mime_type: str) -> bool:
    """Verifica se o tipo de ficheiro pode ser convertido."""
    return mime_type in CONVERTIBLE_TYPES or mime_type.startswith('image/')


def is_dangerous(mime_type: str) -> bool:
    """Verifica se o tipo de ficheiro é perigoso."""
    return mime_type in DANGEROUS_TYPES


def image_to_pdf(image_content: bytes, filename: str = None) -> Tuple[bytes, str]:
    """
    Converte uma imagem para PDF.
    
    Args:
        image_content: Conteúdo binário da imagem
        filename: Nome original do ficheiro
        
    Returns:
        Tuple (pdf_bytes, new_filename)
    """
    if not PIL_AVAILABLE and not IMG2PDF_AVAILABLE:
        raise RuntimeError("Nenhuma biblioteca de conversão disponível (PIL ou img2pdf)")
    
    # Método 1: Usar img2pdf (mais rápido e mantém qualidade)
    if IMG2PDF_AVAILABLE:
        try:
            pdf_bytes = img2pdf.convert(image_content)
            new_name = filename.rsplit('.', 1)[0] + '.pdf' if filename else 'converted.pdf'
            logger.info(f"[CONVERTER] Imagem convertida com img2pdf: {filename}")
            return pdf_bytes, new_name
        except Exception as e:
            logger.warning(f"[CONVERTER] img2pdf falhou: {e}")
    
    # Método 2: Usar PIL + reportlab
    if PIL_AVAILABLE and REPORTLAB_AVAILABLE:
        try:
            # Abrir imagem
            img = Image.open(io.BytesIO(image_content))
            
            # Converter para RGB se necessário
            if img.mode in ('RGBA', 'P', 'LA'):
                # Criar fundo branco
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Calcular tamanho da página
            img_width, img_height = img.size
            
            # Criar PDF
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            
            # Ajustar imagem à página A4 mantendo proporção
            page_width, page_height = A4
            margin = 0.5 * inch
            
            available_width = page_width - 2 * margin
            available_height = page_height - 2 * margin
            
            # Calcular escala
            scale_w = available_width / img_width
            scale_h = available_height / img_height
            scale = min(scale_w, scale_h, 1.0)  # Não ampliar
            
            new_width = img_width * scale
            new_height = img_height * scale
            
            # Centralizar na página
            x = (page_width - new_width) / 2
            y = (page_height - new_height) / 2
            
            # Guardar imagem temporariamente
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                img.save(tmp.name, 'JPEG', quality=95)
                tmp_path = tmp.name
            
            try:
                c.drawImage(tmp_path, x, y, new_width, new_height)
                c.save()
                pdf_bytes = buffer.getvalue()
            finally:
                os.unlink(tmp_path)
            
            new_name = filename.rsplit('.', 1)[0] + '.pdf' if filename else 'converted.pdf'
            logger.info(f"[CONVERTER] Imagem convertida com PIL+reportlab: {filename}")
            return pdf_bytes, new_name
            
        except Exception as e:
            logger.error(f"[CONVERTER] PIL+reportlab falhou: {e}")
            raise
    
    raise RuntimeError("Não foi possível converter a imagem - bibliotecas não disponíveis")


def text_to_pdf(text_content: str, filename: str = None) -> Tuple[bytes, str]:
    """
    Converte texto para PDF.
    
    Args:
        text_content: Conteúdo de texto
        filename: Nome original do ficheiro
        
    Returns:
        Tuple (pdf_bytes, new_filename)
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab não disponível para conversão de texto")
    
    # Criar PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    # Configurações de texto
    page_width, page_height = A4
    margin = 1 * inch
    font_size = 10
    line_height = font_size + 4
    
    # Configurar fonte
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    
    # Tentar usar fonte que suporte caracteres especiais
    try:
        # Registrar fonte padrão
        c.setFont("Helvetica", font_size)
    except Exception:
        c.setFont("Courier", font_size)
    
    # Dividir texto em linhas
    lines = text_content.split('\n')
    
    y = page_height - margin
    max_chars = int((page_width - 2 * margin) / (font_size * 0.5))  # Aproximação
    
    for line in lines:
        # Quebrar linhas longas
        while len(line) > max_chars:
            chunk = line[:max_chars]
            line = line[max_chars:]
            
            try:
                c.drawString(margin, y, chunk)
            except Exception:
                # Remover caracteres problemáticos
                chunk = chunk.encode('latin-1', errors='replace').decode('latin-1')
                c.drawString(margin, y, chunk)
            
            y -= line_height
            
            # Nova página se necessário
            if y < margin:
                c.showPage()
                c.setFont("Helvetica", font_size)
                y = page_height - margin
        
        try:
            c.drawString(margin, y, line)
        except Exception:
            line = line.encode('latin-1', errors='replace').decode('latin-1')
            c.drawString(margin, y, line)
        
        y -= line_height
        
        # Nova página se necessário
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", font_size)
            y = page_height - margin
    
    c.save()
    pdf_bytes = buffer.getvalue()
    
    new_name = filename.rsplit('.', 1)[0] + '.pdf' if filename else 'converted.pdf'
    logger.info(f"[CONVERTER] Texto convertido para PDF: {filename}")
    return pdf_bytes, new_name


def analyze_with_ai(content: bytes, filename: str, detected_type: str) -> Dict[str, Any]:
    """
    Usa IA para analisar ficheiros desconhecidos e tentar extrair conteúdo útil.
    
    Args:
        content: Conteúdo binário
        filename: Nome do ficheiro
        detected_type: Tipo detectado
        
    Returns:
        Dict com análise e sugestões
    """
    from openai import AsyncOpenAI
    import asyncio
    
    async def _analyze():
        try:
            client = AsyncOpenAI()
            
            # Preparar conteúdo para análise
            # Limitar tamanho para não exceder tokens
            sample = content[:10000]  # Primeiros 10KB
            
            # Tentar extrair texto representativo
            text_sample = None
            try:
                text_sample = sample.decode('utf-8', errors='ignore')[:2000]
            except Exception:
                pass
            
            # Preparar prompt
            prompt = f"""Analisa este ficheiro e determina:

1. Tipo real do ficheiro (não apenas a extensão)
2. Se é possível converter para PDF
3. Se contém dados úteis (texto, imagem, etc.)
4. Se é seguro processar

Nome do ficheiro: {filename}
Tipo detectado: {detected_type}
Tamanho: {len(content)} bytes

Amostra de texto (se disponível):
{text_sample[:500] if text_sample else 'N/A'}

Hex dump dos primeiros bytes:
{content[:100].hex()}

Responde em JSON com esta estrutura:
{{
    "real_type": "tipo real do ficheiro",
    "can_convert": true/false,
    "conversion_method": "image_to_pdf/text_to_pdf/not_possible",
    "contains_useful_data": true/false,
    "is_safe": true/false,
    "recommendation": "mensagem para o utilizador",
    "extracted_text": "texto extraído se disponível"
}}"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "És um especialista em análise de ficheiros. Responde apenas em JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"[CONVERTER] Erro na análise IA: {e}")
            return {
                "real_type": detected_type,
                "can_convert": False,
                "contains_useful_data": False,
                "is_safe": True,
                "recommendation": f"Não foi possível analisar o ficheiro: {str(e)}"
            }
    
    # Executar análise assíncrona
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Se já estamos num loop async, criar task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _analyze())
                return future.result(timeout=30)
        else:
            return asyncio.run(_analyze())
    except Exception as e:
        logger.error(f"[CONVERTER] Erro ao executar análise: {e}")
        return {
            "real_type": detected_type,
            "can_convert": False,
            "contains_useful_data": False,
            "is_safe": True,
            "recommendation": f"Erro na análise: {str(e)}"
        }


def convert_file(
    content: bytes,
    filename: str,
    target_format: str = 'pdf'
) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    Converte um ficheiro para o formato especificado.
    
    Este é o ponto de entrada principal para conversão de ficheiros.
    
    Args:
        content: Conteúdo binário do ficheiro
        filename: Nome do ficheiro
        target_format: Formato de destino ('pdf', 'jpeg', 'png')
        
    Returns:
        Tuple (converted_content, new_filename, metadata)
        metadata inclui:
        - original_type: tipo original detectado
        - converted: se foi convertido
        - method: método de conversão usado
        - ai_analysis: análise IA (se usada)
    """
    metadata = {
        "original_type": None,
        "converted": False,
        "method": None,
        "ai_analysis": None,
        "error": None
    }
    
    if not content or len(content) == 0:
        metadata["error"] = "Ficheiro vazio"
        return content, filename, metadata
    
    # 1. Detectar tipo do ficheiro
    detected_mime, detected_ext, confidence = detect_file_type(content)
    metadata["original_type"] = detected_mime
    
    logger.info(f"[CONVERTER] Tipo detectado: {detected_mime} (confiança: {confidence})")
    
    # 2. Verificar se é perigoso
    if is_dangerous(detected_mime):
        metadata["error"] = f"Ficheiro perigoso detectado: {detected_mime}. Conversão não permitida por segurança."
        return content, filename, metadata
    
    # 3. Se já é PDF, não precisa converter
    if detected_mime == 'application/pdf':
        metadata["converted"] = False
        metadata["method"] = "already_pdf"
        return content, filename, metadata
    
    # 4. Se é imagem, converter para PDF
    if detected_mime.startswith('image/'):
        try:
            pdf_content, new_name = image_to_pdf(content, filename)
            metadata["converted"] = True
            metadata["method"] = "image_to_pdf"
            logger.info(f"[CONVERTER] Imagem convertida: {filename} -> {new_name}")
            return pdf_content, new_name, metadata
        except Exception as e:
            metadata["error"] = f"Erro ao converter imagem: {str(e)}"
            logger.error(f"[CONVERTER] Erro ao converter imagem: {e}")
    
    # 5. Se é texto, converter para PDF
    if detected_mime.startswith('text/'):
        try:
            text = content.decode('utf-8', errors='replace')
            pdf_content, new_name = text_to_pdf(text, filename)
            metadata["converted"] = True
            metadata["method"] = "text_to_pdf"
            logger.info(f"[CONVERTER] Texto convertido: {filename} -> {new_name}")
            return pdf_content, new_name, metadata
        except Exception as e:
            metadata["error"] = f"Erro ao converter texto: {str(e)}"
            logger.error(f"[CONVERTER] Erro ao converter texto: {e}")
    
    # 6. Se é base64, tentar decodificar e converter
    if detected_mime == 'application/base64':
        try:
            decoded = base64.b64decode(content)
            # Recursivamente tentar converter o conteúdo decodificado
            return convert_file(decoded, filename, target_format)
        except Exception as e:
            metadata["error"] = f"Erro ao decodificar base64: {str(e)}"
    
    # 7. Tipo desconhecido - usar IA para analisar
    if confidence < 0.5 or detected_mime == 'application/octet-stream':
        logger.info(f"[CONVERTER] Tipo desconhecido, usando análise IA")
        
        ai_result = analyze_with_ai(content, filename, detected_mime)
        metadata["ai_analysis"] = ai_result
        
        if ai_result.get("can_convert") and ai_result.get("is_safe"):
            # Tentar método sugerido pela IA
            method = ai_result.get("conversion_method")
            extracted_text = ai_result.get("extracted_text")
            
            if method == "image_to_pdf" and PIL_AVAILABLE:
                try:
                    pdf_content, new_name = image_to_pdf(content, filename)
                    metadata["converted"] = True
                    metadata["method"] = "ai_guided_image_to_pdf"
                    return pdf_content, new_name, metadata
                except Exception:
                    pass
            
            if extracted_text:
                try:
                    pdf_content, new_name = text_to_pdf(extracted_text, filename)
                    metadata["converted"] = True
                    metadata["method"] = "ai_extracted_text_to_pdf"
                    return pdf_content, new_name, metadata
                except Exception:
                    pass
        
        metadata["error"] = ai_result.get("recommendation", "Não foi possível converter o ficheiro")
    
    # 8. Não foi possível converter
    if not metadata["error"]:
        metadata["error"] = f"Tipo de ficheiro não suportado para conversão: {detected_mime}"
    
    return content, filename, metadata


def can_convert_file(content: bytes, filename: str) -> Dict[str, Any]:
    """
    Verifica se um ficheiro pode ser convertido sem efetivamente converter.
    
    Útil para dar feedback ao utilizador antes de tentar a conversão.
    
    Args:
        content: Conteúdo binário
        filename: Nome do ficheiro
        
    Returns:
        Dict com informações sobre possibilidade de conversão
    """
    if not content or len(content) == 0:
        return {
            "can_convert": False,
            "reason": "Ficheiro vazio",
            "detected_type": None,
            "suggested_action": None
        }
    
    detected_mime, detected_ext, confidence = detect_file_type(content)
    
    if is_dangerous(detected_mime):
        return {
            "can_convert": False,
            "reason": f"Ficheiro perigoso: {detected_mime}",
            "detected_type": detected_mime,
            "suggested_action": "Não tente converter este ficheiro"
        }
    
    if detected_mime == 'application/pdf':
        return {
            "can_convert": False,
            "reason": "Já é um PDF",
            "detected_type": detected_mime,
            "suggested_action": "O ficheiro já está no formato correto"
        }
    
    if is_convertible(detected_mime):
        return {
            "can_convert": True,
            "reason": f"Conversão possível de {detected_mime} para PDF",
            "detected_type": detected_mime,
            "suggested_action": "Converter automaticamente para PDF",
            "confidence": confidence
        }
    
    # Tipo desconhecido
    return {
        "can_convert": "maybe",  # String para indicar que depende de análise IA
        "reason": "Tipo desconhecido - necessita análise",
        "detected_type": detected_mime,
        "suggested_action": "Analisar com IA para determinar possibilidade de conversão",
        "confidence": confidence
    }
