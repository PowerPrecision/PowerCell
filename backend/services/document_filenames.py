"""
Helpers de nomes de ficheiros / sanitização de logs para documentos.

Extraído de `routes/documents.py`.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional

from services.document_constants import DEFAULT_CLIENT_NAME


def sanitize_for_log(value: str, max_length: int = 50) -> str:
    """Sanitiza dados controlados pelo utilizador antes de logar."""
    if not value:
        return "[empty]"
    sanitized = str(value)[:max_length].replace("\n", " ").replace("\r", "")
    return sanitized if sanitized else "[sanitized]"


def normalize_filename(filename: str, category: str = None) -> str:
    """
    Sanitiza o nome do ficheiro para armazenamento seguro no S3.

    NOTA: NÃO altera o nome original - apenas remove caracteres perigosos.
    `category` é ignorado (compatibilidade).
    """
    if not filename:
        return f"documento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    if "." in filename:
        name_part, ext = filename.rsplit(".", 1)
        ext = ext.lower()
    else:
        name_part = filename
        ext = "pdf"

    name_sanitized = re.sub(r'[/\\:*?"<>|]', "", name_part)
    name_sanitized = re.sub(r"[\x00-\x1f\x7f]", "", name_sanitized)

    if len(name_sanitized) > 200:
        name_sanitized = name_sanitized[:200]

    if not name_sanitized.strip():
        name_sanitized = f"documento_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    return f"{name_sanitized}.{ext}"


def is_image_file(filename: str, content_type: str = None) -> bool:
    """Verifica se o ficheiro é uma imagem suportada para conversão."""
    image_extensions = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
    image_mimes = {"image/jpeg", "image/png", "image/tiff"}

    if filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in image_extensions:
            return True

    if content_type and content_type.lower() in image_mimes:
        return True

    return False


def _normalize_smart_text(text: str, max_len: int = 20) -> str:
    """Remove acentos e caracteres especiais para smart rename."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.encode("ASCII", "ignore").decode("ASCII")
    normalized = re.sub(r"[^\w]", "", normalized)
    return normalized[:max_len]


def generate_smart_filename(
    category: str,
    subcategory: str,
    client_name: str,
    expiry_date: Optional[str] = None,
    original_extension: str = "pdf",
) -> str:
    """
    Gera nome inteligente: {Categoria}_{Subcategoria}_{Cliente}_{Validade}.{ext}
    Exemplo: Identificacao_CC_JoaoSilva_2028-03-15.pdf
    """
    cat_norm = _normalize_smart_text(category, 15) or "Doc"
    subcat_norm = _normalize_smart_text(subcategory, 15) or "Geral"
    client_norm = _normalize_smart_text(client_name, 20) or DEFAULT_CLIENT_NAME

    parts = [cat_norm, subcat_norm, client_norm]
    if expiry_date:
        parts.append(expiry_date)

    smart_name = "_".join(parts)
    ext = original_extension.lower().lstrip(".")
    return f"{smart_name}.{ext}"
