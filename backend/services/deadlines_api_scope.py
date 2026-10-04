"""O contexto de acesso do calendário (Lote 7, ponto 3 → Lote 9, parte 2).

A RESOLUÇÃO MUDOU DE CASA, A REGRA NÃO
======================================
O papel efectivo, as redes e os processos visíveis vivem hoje em
`services/tenant_access_context.py`: a pergunta não é do calendário e o
`db.visits` precisava da mesma resposta. Uma segunda cópia divergiria na
primeira mudança, e a que divergir deixa ver ou deixa escrever.

Este módulo fica com o que É do calendário — a mensagem de 404 — e
reexporta o resto para os dois serviços que já o importavam.

**Nota para quem escrever testes:** a função lê `db` do módulo NOVO. Um
`patch.object(deadlines_api_scope, "db", ...)` já não a alcança; tem de
ser `patch.object(tenant_access_context, "db", ...)` (é a regra da ordem
de importação do AGENTS.md — patchar cada módulo da cadeia).
"""
from __future__ import annotations

from services.tenant_access_context import (
    CAMPOS_DE_ATRIBUICAO,
    ContextoDeAcesso,
    carregar_contexto_de_acesso,
    condicao_dos_meus_processos,
)

#: A mesma mensagem para "não existe" e para "não é teu": distinguir as
#: duas confirma o id a quem está a adivinhar (precedente das notificações).
ERRO_EVENTO_NAO_ENCONTRADO = "Prazo não encontrado"

__all__ = [
    "CAMPOS_DE_ATRIBUICAO",
    "ContextoDeAcesso",
    "ERRO_EVENTO_NAO_ENCONTRADO",
    "carregar_contexto_de_acesso",
    "condicao_dos_meus_processos",
]
