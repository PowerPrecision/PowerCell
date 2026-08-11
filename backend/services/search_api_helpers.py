"""Search route helpers.

Extraído de `routes/search.py`.
Do **not** overwrite utils/search_filters.py (shared accent/multiword filters).
"""
from __future__ import annotations

import unicodedata


def normalize_text(text: str) -> str:
    """
    Remove acentos e normaliza texto para pesquisa.
    Exemplo: 'José' -> 'Jose', 'São Paulo' -> 'Sao Paulo'
    """
    if not text:
        return ""
    # Normalizar para forma NFD e remover caracteres combinantes (acentos)
    normalized = unicodedata.normalize('NFD', text)
    # Remover caracteres diacríticos (acentos, cedilhas, etc.)
    result = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
    return result.lower()
