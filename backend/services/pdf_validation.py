"""Validação mínima de que um conteúdo descarregado é mesmo um PDF.

Módulo sem dependências, partilhado pelo scraper (que decide se tenta o
recurso seguinte) e pelo arquivo (que decide se grava): as duas decisões
têm de coincidir, senão o scraper dá o documento por obtido, não tenta o
recurso e o arquivo recusa-o — documento perdido sem segunda tentativa.
"""
from __future__ import annotations

from typing import Optional

# Abaixo disto um PDF do portal é uma página de erro.
TAMANHO_MINIMO_DE_UM_PDF = 200

# A especificação do PDF admite lixo antes de `%PDF-` dentro do 1.º KB.
JANELA_DO_CABECALHO = 1024


def parece_pdf(conteudo: Optional[bytes]) -> bool:
    """Um PDF tem `%PDF-` nos primeiros 1024 bytes e um tamanho plausível."""
    if not conteudo or len(conteudo) < TAMANHO_MINIMO_DE_UM_PDF:
        return False
    return b"%PDF-" in conteudo[:JANELA_DO_CABECALHO]
