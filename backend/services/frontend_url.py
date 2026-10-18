"""A base dos links que o CRM manda por email — nunca um domínio de marca escrito no código.

Um link para o Portal, para o RGPD ou para um carregamento sai em nome da REDE do cliente. Um
domínio de uma marca como recurso (`precisioncredito.pt`, `powercell.pt`) mandava o cliente da
Domus para o site da Power sem erro nenhum. Sem `FRONTEND_URL` e sem uma base explícita
(`Origin` do pedido), a base é VAZIA e quem chama decide o que fazer — nunca adivinha uma marca.
"""
import os
from typing import Optional


def base_do_frontend(preferida: Optional[str] = None) -> str:
    """A base pedida ou `FRONTEND_URL`, sem barra final; `""` quando nenhuma está definida."""
    for candidata in (preferida, os.environ.get("FRONTEND_URL")):
        texto = (candidata or "").strip().rstrip("/")
        if texto:
            return texto
    return ""
