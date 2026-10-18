"""O caminho de uma pasta S3 como uma pessoa o lê — só para o ECRÃ (QA-6).

`Documentação Clientes/9f1c…/processos/3b7a…` não diz nada a quem mapeia pastas. Aqui um segmento
que é um id gerado vira o nome do cliente (o primeiro) ou «Processo n.º X» (o que vem depois de
`processos/`), e o resto perde o `_` dos nomes antigos criados à mão.

REGRA: isto nunca decide nada. O caminho cru continua a ser o que se grava e o que se compara; um
nome legível que fosse usado para operar era a forma discreta de a parede de posse não valer nada
(ver `utils/pastaS3.js`).
"""
from __future__ import annotations

from typing import Any, Optional

from services.s3_document_root import RAIZ, e_id_gerado

SEPARADOR = " › "


def _limpo(texto: Any) -> str:
    return " ".join(str(texto or "").replace("_", " ").split())


def caminho_legivel(
    caminho: Any,
    *,
    nome_do_cliente: Optional[str] = None,
    numero_do_processo: Optional[str] = None,
) -> str:
    """`Cliente › Processo n.º 12` para a pasta; `""` quando não há pasta (um valor que não é texto também)."""
    if not isinstance(caminho, str) or not caminho.strip():
        return ""
    restante = caminho.strip()
    if restante.startswith(RAIZ):
        restante = restante[len(RAIZ):]
    segmentos = [s for s in restante.split("/") if s]
    if not segmentos:
        return ""

    partes: list[str] = []
    depois_de_processos = False
    for indice, segmento in enumerate(segmentos):
        if segmento.lower() == "processos":
            depois_de_processos = True
            continue
        if e_id_gerado(segmento):
            if depois_de_processos:
                partes.append(f"Processo n.º {numero_do_processo}" if numero_do_processo else "Processo")
            elif indice == 0:
                partes.append(_limpo(nome_do_cliente) or "Cliente sem nome")
            else:
                partes.append(segmento)
            continue
        partes.append(_limpo(segmento))
        depois_de_processos = False
    return SEPARADOR.join(p for p in partes if p)
