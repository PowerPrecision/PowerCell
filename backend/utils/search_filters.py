"""
Filtros de pesquisa partilhados (MongoDB).

Centraliza os helpers de pesquisa insensível a acentos e multi-palavra que
antes estavam duplicados em `routes/processes.py`, `routes/clients.py` e
`routes/search.py`. Manter uma única implementação evita divergências de
comportamento entre as várias pesquisas da aplicação.
"""
import re

# Mapeamento de caracteres base para todas as suas variantes acentuadas.
_ACCENT_MAP = {
    'a': '[aàáâãäåAÀÁÂÃÄÅ]',
    'e': '[eèéêëEÈÉÊË]',
    'i': '[iìíîïIÌÍÎÏ]',
    'o': '[oòóôõöOÒÓÔÕÖ]',
    'u': '[uùúûüUÙÚÛÜ]',
    'c': '[cçCÇ]',
    'n': '[nñNÑ]',
    'y': '[yýÿYÝŸ]',
}


def create_accent_insensitive_regex(search_term: str) -> dict:
    """
    Cria um regex MongoDB que ignora acentos e maiúsculas/minúsculas.

    Exemplo: pesquisar 'jose' encontra 'José', 'JOSE', 'josé', 'JÓSÉ'.
    """
    if not search_term:
        return {"$regex": "", "$options": "i"}

    pattern_parts = []
    for char in search_term.lower():
        if char in _ACCENT_MAP:
            pattern_parts.append(_ACCENT_MAP[char])
        elif char.isalpha():
            pattern_parts.append(f'[{char}{char.upper()}]')
        elif char.isalnum():
            pattern_parts.append(char)
        else:
            pattern_parts.append(re.escape(char))

    pattern = ''.join(pattern_parts)
    # Não precisa de 'i' porque as classes já incluem maiúsculas.
    return {"$regex": pattern, "$options": ""}


def build_multiword_search_filter(search_term: str, name_field: str) -> dict:
    """
    Constrói filtro de pesquisa que suporta múltiplas palavras.

    Se o termo contém espaços, divide em palavras e exige que TODAS apareçam
    (em qualquer ordem) no campo indicado (AND lógico).

    Exemplo: 'vera teixeira' encontra 'Vera Lucia Da Costa Teixeira' porque
    'vera' E 'teixeira' existem no nome. Sem espaços, comporta-se como
    `create_accent_insensitive_regex`.
    """
    if not search_term:
        return {}

    words = search_term.strip().split()

    if len(words) <= 1:
        return {name_field: create_accent_insensitive_regex(search_term.strip())}

    word_filters = []
    for word in words:
        if len(word.strip()) >= 1:
            word_filters.append({name_field: create_accent_insensitive_regex(word.strip())})

    if len(word_filters) == 1:
        return word_filters[0]

    return {"$and": word_filters}
