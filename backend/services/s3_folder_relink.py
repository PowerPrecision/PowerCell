"""O `rename` move a chave **e** o mapeamento (Épico 10, Gestor S3, Passo 4).

A CEGUEIRA AUTO-INFLIGIDA
=========================
`run_s3_rename` copiava os objectos para o prefixo novo, apagava os antigos,
e não tocava em nada na base de dados. Três consequências, por ordem de
gravidade:

1. **`processes.s3_folder`** continuava a apontar para o nome ANTIGO. Com o
   isolamento do Passo 3, a pasta passa a ser **órfã** — invisível a toda a
   gente excepto ADMIN/CEO. Renomear passou a ser apagar do mundo.
2. **`document_metadata.s3_path`** também. É ele que sustenta o separador
   Documentos do processo, o badge IA, as validades e a análise; os
   ficheiros desapareciam da ficha.
3. **`documents.s3_path`** e `attached_files` são os pedidos do Portal. O
   cliente ficava a ver um documento que já não está onde diz.

A medição de produção provou-o: **205 ligações partidas**, cada uma um
`rename` antigo.

FRONTEIRA DE SEGMENTO, SEMPRE
=============================
`Joao_Silva_2` começa pelo mesmo texto que `Joao_Silva` e é OUTRO cliente —
e o sufixo `_2` é precisamente como o sistema desambigua homónimos, pelo que
é o caso comum e não o raro. Reescrever por prefixo de texto arrastaria o
vizinho.

NUNCA BLOQUEIA
==============
Quando isto corre, os objectos JÁ se moveram no S3. Levantar aqui mostraria
um erro sobre uma operação bem sucedida e deixaria o estado pior do que
relatar a falha. Mesma lei do `document_portal_revoke`.
"""
from __future__ import annotations

import logging
from typing import Optional

from database import db

logger = logging.getLogger(__name__)


def reescrever_prefixo(caminho: Optional[str], antigo: str, novo: str) -> Optional[str]:
    """Troca `antigo` por `novo` no início do caminho, por SEGMENTO.

    Devolve o caminho intacto quando ele não pertence ao prefixo — incluindo
    o caso em que apenas se parece com ele (`Joao_Silva_2`).
    """
    if not caminho:
        return caminho
    antigo = (antigo or "").rstrip("/")
    novo = (novo or "").rstrip("/")
    if not antigo:
        return caminho
    if caminho == antigo:
        return novo
    if caminho.startswith(f"{antigo}/"):
        return novo + caminho[len(antigo):]
    return caminho


def _condicao_do_prefixo(campo: str, antigo: str) -> dict:
    """Documentos exactamente na pasta, ou abaixo dela — e mais nada."""
    antigo = antigo.rstrip("/")
    return {"$or": [
        {campo: antigo},
        {campo: {"$regex": f"^{_escapar(antigo)}/"}},
    ]}


def _escapar(texto: str) -> str:
    import re
    return re.escape(texto)


async def religar_apos_rename(antigo: str, novo: str) -> dict:
    """Reaponta tudo o que guardava o caminho antigo.

    Returns:
        ``{"processos", "documentos", "pedidos_portal", "erro"}``. O
        ``erro`` é informativo: o chamador não reage, porque o S3 já mudou.
    """
    antigo = (antigo or "").rstrip("/")
    novo = (novo or "").rstrip("/")
    resultado = {"processos": 0, "documentos": 0, "pedidos_portal": 0, "erro": False}

    if not antigo or not novo or antigo == novo:
        return resultado

    try:
        # 1. O mapeamento pasta → processo. Só casa a pasta do CLIENTE:
        # renomear uma subpasta (`Financeiros`) não muda o `s3_folder`.
        cursor = db.processes.find(
            {"s3_folder": antigo}, {"_id": 0, "id": 1, "s3_folder": 1}
        )
        for processo in await cursor.to_list(10000):
            await db.processes.update_one(
                {"id": processo.get("id")},
                {"$set": {"s3_folder": novo}},
            )
            resultado["processos"] += 1

        # 2. Os metadados de cada documento (separador Documentos, IA,
        # validades). Aqui sim, tudo o que está ABAIXO do prefixo.
        cursor = db.document_metadata.find(
            _condicao_do_prefixo("s3_path", antigo), {"_id": 0, "id": 1, "s3_path": 1}
        )
        for documento in await cursor.to_list(100000):
            await db.document_metadata.update_one(
                {"id": documento.get("id")},
                {"$set": {"s3_path": reescrever_prefixo(
                    documento.get("s3_path"), antigo, novo
                )}},
            )
            resultado["documentos"] += 1

        # 3. Os pedidos do Portal: campo de topo e o histórico anexado.
        cursor = db.documents.find(
            {"$or": [
                _condicao_do_prefixo("s3_path", antigo),
                _condicao_do_prefixo("attached_files.s3_path", antigo),
            ]},
            {"_id": 0, "id": 1, "s3_path": 1, "attached_files": 1},
        )
        for pedido in await cursor.to_list(100000):
            anexos = []
            for anexo in pedido.get("attached_files") or []:
                if isinstance(anexo, dict):
                    anexo = dict(anexo)
                    anexo["s3_path"] = reescrever_prefixo(
                        anexo.get("s3_path"), antigo, novo
                    )
                anexos.append(anexo)

            await db.documents.update_one(
                {"id": pedido.get("id")},
                {"$set": {
                    "s3_path": reescrever_prefixo(pedido.get("s3_path"), antigo, novo),
                    "attached_files": anexos,
                }},
            )
            resultado["pedidos_portal"] += 1

    except Exception as exc:
        # Os objectos já se moveram no S3: relatar é melhor do que falhar.
        resultado["erro"] = True
        logger.error(
            "[S3-RELINK] Falha a reapontar '%s' → '%s' (%s). Os objectos já "
            "foram movidos; este mapeamento fica partido e aparecerá no "
            "relatório de cobertura.", antigo, novo, exc,
        )

    return resultado
