"""
Anexar a um email ficheiros que JÁ estão no PowerCell (documentos do processo
e do cliente no S3), sem os descarregar e voltar a carregar.

Duas operações, ambas atrás do router `/emails` (portanto sem o perfil Index,
que não tem Webmail):

* `run_listar_documentos_para_anexar` — os ficheiros do processo que o
  utilizador pode ver, numa lista plana para o seletor do compositor.
* `run_anexar_documentos_do_processo` — COPIA os ficheiros escolhidos para a
  pasta temporária de anexos (`temp/attachments/{user_id}/...`) e cria o
  registo em `temp_attachments`. A partir daí o envio é o de sempre:
  `email_send_queue._prepare_temp_attachments` lê-os e
  `_finalize_attachments` move a CÓPIA para `Emails/{email_id}/`.

Porquê copiar e não referenciar: o `_finalize_attachments` faz `rename_file`
(copiar + APAGAR a origem) do `temp_key`. Se o `temp_key` fosse a chave do
documento do cliente, enviar um email apagava o documento do processo.

Guardas, por esta ordem (o caminho vem do browser, não se confia nele):
1. o processo existe, não está eliminado e o utilizador pode ver os documentos
   dele (`exigir_processo_legivel`: fronteira de REDE + pré-indexação);
2. a chave está na raiz documental (`assert_path_within_document_root`, que
   recusa `backups/`, `companies/`, `temp/`...);
3. a chave pertence a ESTE processo (`assert_s3_file_belongs_to_process`, ou
   a raiz do cliente que a listagem do processo também mostra);
4. a pasta `Index` só para quem a vê (`pode_ver_o_index`);
5. o objecto existe e cabe no limite de anexo (25MB, o mesmo do upload).
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request

from database import db

logger = logging.getLogger(__name__)

MAX_FICHEIROS_POR_PEDIDO = 10
MAX_TAMANHO_ANEXO = 25 * 1024 * 1024  # igual ao upload (`run_upload_attachments`)

ERRO_PROCESSO_NAO_ENCONTRADO = "Processo não encontrado"
ERRO_SEM_FICHEIROS = "Escolha pelo menos um ficheiro"
ERRO_DEMASIADOS = f"Máximo de {MAX_FICHEIROS_POR_PEDIDO} ficheiros de cada vez"


async def _processo_legivel(process_id: str, user: dict) -> dict:
    """O processo, se o utilizador o pode ler. 404 se não existe ou está eliminado."""
    from services.email_access import exigir_processo_legivel

    if not isinstance(process_id, str) or not process_id.strip():
        raise HTTPException(status_code=400, detail="Processo em falta")
    process = await exigir_processo_legivel(process_id.strip(), user)
    if not process or process.get("is_deleted") is True:
        raise HTTPException(status_code=404, detail=ERRO_PROCESSO_NAO_ENCONTRADO)
    return process


def _achatar(listagem: Any) -> list[dict]:
    """A listagem por pastas do `s3_service.list_files` numa lista plana e leve.

    Fica de fora o `temporary_url`: o seletor não precisa de abrir o ficheiro,
    e não se espalham URLs pré-assinados sem necessidade.
    """
    if not isinstance(listagem, dict):
        return []
    por_categoria = listagem.get("files")
    if not isinstance(por_categoria, dict):
        return []
    ficheiros: list[dict] = []
    vistos: set[str] = set()
    for categoria, lista in por_categoria.items():
        if not isinstance(lista, list):
            continue
        for f in lista:
            if not isinstance(f, dict) or f.get("superseded"):
                continue
            caminho = f.get("path")
            if not caminho or caminho in vistos:
                continue
            vistos.add(caminho)
            ficheiros.append({
                "path": caminho,
                "name": f.get("name") or caminho.rsplit("/", 1)[-1],
                "size": f.get("size") or 0,
                "category": f.get("category") or categoria,
                "last_modified": f.get("last_modified"),
            })
    ficheiros.sort(key=lambda f: (str(f["category"]).lower(), str(f["name"]).lower()))
    return ficheiros


async def run_listar_documentos_para_anexar(process_id: str, request: Request, user: dict) -> dict:
    """Ficheiros do processo (e da pasta do cliente) que o utilizador pode anexar.

    Usa a mesma listagem do separador Documentos, com as mesmas paredes
    (substituídos e pasta `Index`), mas NÃO marca os documentos como vistos:
    escolher um anexo não é abrir o que o cliente enviou.
    """
    from services.auth import get_effective_role_async
    from services.document_constants import DEFAULT_CLIENT_NAME
    from services.document_intake import retirar_o_index_da_listagem
    from services.document_process_resolve import extract_second_client_name
    from services.index_substituicao import aplicar_a_listagem
    from services.s3_storage import s3_service

    process = await _processo_legivel(process_id, user)
    effective_id = process["id"]

    loop = asyncio.get_running_loop()
    listagem = await loop.run_in_executor(
        None,
        lambda: s3_service.list_files(
            effective_id,
            process.get("client_name", DEFAULT_CLIENT_NAME),
            extract_second_client_name(process),
            process.get("s3_folder"),
        ),
    )

    papel = await get_effective_role_async(request, user)
    listagem = await aplicar_a_listagem(listagem, effective_id, papel, False)
    listagem = retirar_o_index_da_listagem(listagem, user)

    return {
        "process_id": effective_id,
        "process_number": process.get("process_number"),
        "client_name": process.get("client_name"),
        "files": _achatar(listagem),
        "em_indexacao": (listagem or {}).get("em_indexacao", 0) if isinstance(listagem, dict) else 0,
    }


def _na_leitura_do_processo(caminho: str, process: dict) -> bool:
    """A chave está numa das leituras da listagem deste processo?"""
    from services.s3_document_root import (
        chave_pertence_a_leitura,
        leituras_do_mapeamento,
        pasta_gravada,
    )

    pasta = pasta_gravada(process.get("s3_folder"))
    if not pasta:
        return False
    return any(chave_pertence_a_leitura(caminho, leitura) for leitura in leituras_do_mapeamento(pasta))


def _validar_caminho(caminho: Any, process: dict, user: dict) -> str:
    """Aplica as guardas 2 a 4 a um caminho vindo do cliente. Devolve-o normalizado."""
    from services.document_constants import ERROR_FILE_ACCESS_DENIED
    from services.document_intake import chave_esta_na_index, pode_ver_o_index
    from services.document_process_resolve import (
        assert_path_within_document_root,
        assert_s3_file_belongs_to_process,
    )

    if not isinstance(caminho, str) or not caminho.strip():
        raise HTTPException(status_code=400, detail="Caminho de ficheiro inválido")
    caminho = caminho.strip().lstrip("/")
    segmentos = caminho.split("/")
    if any(s in ("..", ".") for s in segmentos):
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)

    assert_path_within_document_root(caminho)
    try:
        assert_s3_file_belongs_to_process(caminho, process)
    except HTTPException:
        # A listagem do separador Documentos de um processo com pasta
        # `.../{cliente}/processos/{id}` mostra TAMBÉM a raiz do cliente (sem
        # a subárvore dos outros processos): é o onboarding do Portal. O que se
        # vê no seletor tem de se poder anexar — mesma regra, mesmo módulo
        # (`leituras_do_mapeamento`), nada mais largo do que a listagem.
        if not _na_leitura_do_processo(caminho, process):
            raise
    if chave_esta_na_index(caminho) and not pode_ver_o_index(user):
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)
    return caminho


async def run_anexar_documentos_do_processo(
    process_id: Optional[str],
    file_paths: Any,
    user: dict,
) -> dict:
    """Copia ficheiros do processo para anexos temporários do utilizador.

    Devolve o mesmo formato do upload (`{attachments, errors}`), para o
    compositor tratar os dois da mesma maneira e o envio usar `attachment_ids`.
    Valida TODOS os caminhos antes de copiar o primeiro: um caminho de outro
    processo recusa o pedido inteiro (não é um erro de utilizador, é uma
    tentativa).
    """
    from services.s3_storage import s3_service

    if not isinstance(file_paths, list) or not file_paths:
        raise HTTPException(status_code=400, detail=ERRO_SEM_FICHEIROS)
    if len(file_paths) > MAX_FICHEIROS_POR_PEDIDO:
        raise HTTPException(status_code=400, detail=ERRO_DEMASIADOS)

    process = await _processo_legivel(process_id or "", user)

    caminhos: list[str] = []
    for caminho in file_paths:
        normalizado = _validar_caminho(caminho, process, user)
        if normalizado not in caminhos:
            caminhos.append(normalizado)

    user_id = user["id"]
    loop = asyncio.get_running_loop()
    anexados: list[dict] = []
    erros: list[str] = []

    for caminho in caminhos:
        nome = caminho.rsplit("/", 1)[-1] or "anexo"
        estado, meta = await loop.run_in_executor(
            None, lambda c=caminho: s3_service.head_object_metadata(c)
        )
        if estado == "ausente":
            erros.append(f"{nome}: o ficheiro já não existe")
            continue
        if estado != "ok" or not meta:
            erros.append(f"{nome}: não foi possível ler o ficheiro")
            continue
        tamanho = int(meta.get("tamanho") or 0)
        if tamanho <= 0:
            erros.append(f"{nome}: ficheiro vazio")
            continue
        if tamanho > MAX_TAMANHO_ANEXO:
            erros.append(f"{nome}: ficheiro excede 25MB")
            continue

        file_id = str(uuid.uuid4())
        temp_key = f"temp/attachments/{user_id}/{file_id}_{nome}"
        copiado = await loop.run_in_executor(
            None, lambda o=caminho, d=temp_key: s3_service.copy_object_exact(o, d)
        )
        if not copiado:
            erros.append(f"{nome}: erro ao preparar o anexo")
            continue

        mime = (
            meta.get("tipo")
            or mimetypes.guess_type(nome)[0]
            or "application/octet-stream"
        )
        registo = {
            "id": file_id,
            "file_name": nome,
            "file_size": tamanho,
            "mime_type": mime,
            "temp_key": temp_key,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            # De onde veio: auditoria e para o ecrã distinguir do upload.
            "source": "documentos",
            "source_process_id": process["id"],
            "source_s3_path": caminho,
        }
        await db.temp_attachments.insert_one(dict(registo))
        anexados.append({
            "id": file_id,
            "file_name": nome,
            "file_size": tamanho,
            "mime_type": mime,
            "temp_key": temp_key,
            "source": "documentos",
        })
        logger.info(
            "[EMAIL-DOCS] %s anexou %s (processo %s) -> %s",
            user_id, caminho, process["id"], temp_key,
        )

    if not anexados:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum ficheiro anexado: {'; '.join(erros)}" if erros else ERRO_SEM_FICHEIROS,
        )

    return {"attachments": anexados, "errors": erros or None}
