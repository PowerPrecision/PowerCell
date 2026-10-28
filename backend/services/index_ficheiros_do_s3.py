"""Os ficheiros da bancada do Index são os MESMOS da aba Documentos do processo (Out 2026).

O defeito: a aba Documentos lê a pasta S3 do processo (`s3_service.list_files`, que une a subpasta do
processo e a raiz do cliente), mas a bancada lia só os registos de `document_metadata` com
`process_id` deste processo. Ficavam de fora, sem erro nenhum:

- o que entrou na fase de LEAD (Portal do cliente, parceiro): vive na raiz do cliente e só tem registo
  quando já há processo (`partner_upload_ops._depois_de_guardar` só regista «com processo»);
- os registos da raiz do cliente gravados com o `process_id` de OUTRO processo do mesmo cliente;
- ficheiros postos na pasta por fora (Explorador S3, importações antigas).

Agora a bancada parte da MESMA listagem: cada chave da pasta liga-se ao seu registo por `s3_path`, e
uma chave sem registo ganha um (com o `process_id` deste processo), para o Index a poder ver, descarregar
e analisar como as outras. Os registos do processo que a listagem não traz continuam (nunca se esconde
o que a bancada já mostrava).

Sem S3 ou sem pasta gravada devolve `None` e quem chama fica com a leitura antiga (só os registos):
um vazio silencioso é a forma de defeito desta casa.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from services.s3_document_root import chave_pertence_a_leitura, leituras_do_mapeamento, pasta_gravada
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

MAXIMO_DE_REGISTOS_NOVOS = 200


def _chaves_da_listagem(listagem: Any) -> list[tuple[str, str, Optional[str]]]:
    """`(chave, nome, categoria)` de cada ficheiro da listagem, pela ordem em que vem e sem repetidos."""
    vistas, saida = set(), []
    por_categoria = (listagem or {}).get("files") if isinstance(listagem, dict) else None
    for categoria, ficheiros in (por_categoria or {}).items():
        for f in ficheiros if isinstance(ficheiros, list) else []:
            chave = (f or {}).get("path")
            if not chave or chave in vistas:
                continue
            vistas.add(chave)
            saida.append((chave, f.get("name") or chave.rsplit("/", 1)[-1], categoria))
    return saida


def chave_e_da_pasta_do_processo(chave: Any, proc: dict) -> bool:
    """A chave está numa das leituras da pasta do processo (a dele ou a raiz do cliente sem `processos/`)?"""
    pasta = pasta_gravada((proc or {}).get("s3_folder"), contexto=f"posse na bancada de {(proc or {}).get('id')}")
    if not pasta or not chave:
        return False
    return any(chave_pertence_a_leitura(chave, leitura) for leitura in leituras_do_mapeamento(pasta))


async def registos_da_pasta_do_processo(proc: dict, projeccao: dict) -> Optional[list[dict]]:
    """Os registos de `document_metadata` de todos os ficheiros que a aba Documentos mostra.

    `None` quando não há listagem (S3 por configurar, processo sem pasta, erro do S3).
    """
    process_id = proc.get("id")
    pasta = pasta_gravada(proc.get("s3_folder"), contexto=f"bancada do Index de {process_id}")
    if not process_id or not pasta or not s3_service.is_configured():
        return None
    try:
        from services.document_process_resolve import extract_second_client_name

        listagem = await asyncio.to_thread(
            s3_service.list_files, process_id, proc.get("client_name") or "",
            extract_second_client_name(proc), pasta,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Listagem S3 da bancada de %s falhou (%s); ficam só os registos", process_id,
                       type(exc).__name__)
        return None
    if not isinstance(listagem, dict) or listagem.get("error") or listagem.get("base_path") is None:
        return None

    chaves = _chaves_da_listagem(listagem)
    if not chaves:
        return []

    caminhos = [c for c, _, _ in chaves]
    encontrados = await db.document_metadata.find(
        {"s3_path": {"$in": caminhos}, "file_state": {"$ne": "purgado"}}, {**projeccao, "s3_path": 1, "process_id": 1}
    ).to_list(len(caminhos) * 2)
    por_chave: dict[str, dict] = {}
    for d in encontrados:
        actual = por_chave.get(d.get("s3_path"))
        # dois registos da mesma chave (raiz do cliente partilhada): ganha o deste processo
        if actual is None or (actual.get("process_id") != process_id and d.get("process_id") == process_id):
            por_chave[d["s3_path"]] = d

    em_falta = [(c, n, cat) for c, n, cat in chaves if c not in por_chave]
    if em_falta:
        agora = datetime.now(timezone.utc).isoformat()
        for chave, nome, categoria in em_falta[:MAXIMO_DE_REGISTOS_NOVOS]:
            # `$setOnInsert`: se outro pedido o criou entretanto, não se toca no que lá está
            await db.document_metadata.update_one(
                {"s3_path": chave},
                {"$setOnInsert": {
                    "id": str(uuid.uuid4()), "process_id": process_id,
                    "client_name": proc.get("client_name"), "s3_path": chave, "filename": nome,
                    "category": categoria, "is_categorized": False, "in_index_queue": False,
                    "registered_from": "bancada_index_s3", "created_at": agora, "updated_at": agora,
                }},
                upsert=True,
            )
        if len(em_falta) > MAXIMO_DE_REGISTOS_NOVOS:
            logger.warning("[INDEX] Bancada de %s: %d ficheiros sem registo ficam para a próxima abertura",
                           process_id, len(em_falta) - MAXIMO_DE_REGISTOS_NOVOS)
        novos = await db.document_metadata.find(
            {"s3_path": {"$in": [c for c, _, _ in em_falta]}, "file_state": {"$ne": "purgado"}},
            {**projeccao, "s3_path": 1, "process_id": 1},
        ).to_list(len(em_falta) * 2)
        for d in novos:
            por_chave.setdefault(d["s3_path"], d)
        logger.info("[INDEX] Bancada de %s: %d ficheiros da pasta sem registo foram registados", process_id,
                    min(len(em_falta), MAXIMO_DE_REGISTOS_NOVOS))

    return [por_chave[c] for c in caminhos if c in por_chave]


__all__ = ["chave_e_da_pasta_do_processo", "registos_da_pasta_do_processo"]
