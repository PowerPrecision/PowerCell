"""
Endpoints auxiliares de documentos (check-file, NIF empregador, download URL, init folders).

Extraído de `routes/documents.py`.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from fastapi import HTTPException, UploadFile

from database import db
from services.s3_document_root import (
    RAIZ,
    PastaGravadaInvalida,
    dentro_da_pasta,
    normalizar,
    pasta_do_cliente,
    pasta_gravada,
    pasta_para_gravar,
)
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    ERROR_DOWNLOAD_URL,
    ERROR_S3_FILE_NOT_FOUND,
)
from services.document_process_resolve import (
    assert_path_within_document_root,
    assert_s3_file_belongs_to_process,
    extract_second_client_name,
    resolve_process_from_flexible_id,
)
from services.document_path_scope import exigir_ficheiro_no_ambito
from services.document_s3_paths import s3_path_variations
# Módulo (e não o nome) e no TOPO: o `db` do `s3_relink` não pode ser capturado por um import
# preguiçoso dentro de um `patch("database.db")`; e o teste patcha o atributo do módulo.
from services import s3_relink
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


async def run_check_file_upload(file: UploadFile) -> dict[str, Any]:
    """Pré-valida ficheiro (tipo detectado + conversão possível)."""
    from services.file_converter import can_convert_file, detect_file_type

    try:
        file_content = await file.read()
        filename = file.filename
        if not file_content or len(file_content) == 0:
            return {
                "can_upload": False,
                "reason": "Ficheiro vazio",
                "filename": filename,
            }

        detected_mime, detected_ext, confidence = detect_file_type(file_content)
        conversion_check = can_convert_file(file_content, filename)
        file_size_mb = len(file_content) / (1024 * 1024)
        return {
            "can_upload": conversion_check["can_convert"] is not False,
            "filename": filename,
            "file_size_mb": round(file_size_mb, 2),
            "detected_type": detected_mime,
            "detected_extension": detected_ext,
            "confidence": confidence,
            "conversion_info": conversion_check,
            "recommendation": conversion_check.get(
                "suggested_action", "Pode fazer upload diretamente"
            ),
        }
    except Exception as e:
        logger.error(f"[CHECK-FILE] Erro: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao verificar ficheiro: {str(e)}"
        )


async def run_initialize_folders(
    client_id: str, user: Optional[dict] = None
) -> dict[str, Any]:
    """«Forçar criação de pasta» / «Religar S3» (Lote 6, ponto 4).

    A válvula de quem não tem a pasta documental: cria a estrutura no S3 e
    actualiza o registo — do PROCESSO, ou do CLIENTE quando ele ainda não tem
    processo (a Pool). Idempotente: uma pasta que existe devolve-se tal e qual.

    O caminho NUNCA vem do pedido. Três casos, por ordem:

    1. o registo aponta para uma pasta VÁLIDA (dentro da raiz documental) e ela
       existe no S3 → nada a fazer (`already_exists`);
    2. aponta para uma pasta válida que JÁ NÃO existe → recria-se a estrutura
       NO MESMO caminho, sem mexer no ponteiro (`recreated`): mover o ponteiro
       aqui seria decidir sozinho que a documentação mudou de sítio;
    3. não aponta para nada, ou aponta para algo inutilizável (tipo errado, fora
       da raiz, a própria raiz) → deriva do ID e grava o ponteiro (`created`).

    O S3 em baixo é um 503 que se lê no ecrã, não um `success: false` num 200
    que o botão engolia.
    """
    process, effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[INIT-FOLDERS]",
        allow_client_without_process=True,
    )
    if process:
        tipo, coleccao, entity_id, doc = "processo", db.processes, effective_id, process
    else:
        client = await db.clients.find_one({"id": client_id})
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        tipo, coleccao, entity_id, doc = "cliente", db.clients, client_id, client

    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="O armazenamento de documentos (S3) não está disponível. Tente novamente dentro de instantes.",
        )

    gravada = pasta_gravada(doc.get("s3_folder"), contexto=f"init-folders de {entity_id}")
    # Uma pasta fora da raiz (ou a própria raiz) é um ponteiro ENVENENADO: não se
    # reaproveita — substitui-se pelo derivado do id.
    utilizavel = (
        gravada
        if gravada
        and normalizar(gravada) != normalizar(RAIZ)
        and dentro_da_pasta(gravada, RAIZ)
        else None
    )

    base_path = None
    if utilizavel:
        if await asyncio.to_thread(s3_service._folder_exists, utilizavel):
            logger.info("[INIT-FOLDERS] Pasta S3 já existe para %s %s: %s", tipo, entity_id, utilizavel)
            return {
                "success": True,
                "entidade": tipo,
                "s3_folder": utilizavel,
                "already_exists": True,
                "created": False,
                "recreated": False,
            }
        base_path = utilizavel
    elif tipo == "cliente":
        base_path = pasta_do_cliente(entity_id)

    nome = (
        doc.get("client_name") if tipo == "processo" else doc.get("nome")
    ) or DEFAULT_CLIENT_NAME
    try:
        success, s3_folder_path = await asyncio.to_thread(
            lambda: s3_service.initialize_client_folders(
                entity_id,
                nome,
                extract_second_client_name(doc) if tipo == "processo" else None,
                base_path=base_path,
                owner_client_id=doc.get("client_id") if tipo == "processo" else None,
            )
        )
    except Exception as exc:  # noqa: BLE001 - o S3 a falhar é um aviso legível, não um 500 mudo
        logger.error("[INIT-FOLDERS] Falha a criar a pasta de %s %s: %s", tipo, entity_id, exc)
        success, s3_folder_path = False, None

    # `initialize_client_folders` devolve o par `(sucesso, caminho)` e foi o
    # par gravado inteiro que produziu as 10 anomalias de produção. Aqui o
    # desempacotamento está certo; o primitivo é a rede que o mantém assim.
    try:
        caminho = pasta_para_gravar(
            s3_folder_path, contexto=f"init-folders de {tipo} {entity_id}"
        )
    except PastaGravadaInvalida as erro:
        logger.error("[INIT-FOLDERS] %s", erro)
        raise HTTPException(status_code=500, detail=str(erro))

    if not (success and caminho):
        raise HTTPException(
            status_code=503,
            detail="Não foi possível criar a pasta no armazenamento. Tente novamente; se persistir, contacte a administração.",
        )

    recriada = bool(utilizavel)
    if not recriada:
        # O ponteiro só se grava quando mudou (ausente ou inutilizável).
        await coleccao.update_one({"id": entity_id}, {"$set": {"s3_folder": caminho}})
        await s3_relink.registar_na_auditoria(
            tipo=tipo, entity_id=entity_id, anterior=doc.get("s3_folder") if isinstance(doc.get("s3_folder"), str) else None,
            novo=caminho, user=user or {}, papel_efectivo=None,
        )
    return {
        "success": True,
        "entidade": tipo,
        "s3_folder": caminho,
        "already_exists": False,
        "created": not recriada,
        "recreated": recriada,
    }


async def base_path_do_cliente_sem_processo(client: dict) -> Optional[str]:
    """A pasta do cliente que ainda não tem processo, SE existir no armazenamento.

    `None` = não há pasta (sem ponteiro utilizável, ou o ponteiro aponta para o vazio): é o sinal
    que mostra o botão «Forçar criação de pasta». Uma falha do S3 também dá `None` — o botão
    aparece e, se o S3 estiver mesmo em baixo, o 503 di-lo; esconder o botão por um soluço
    deixaria a ficha sem saída.
    """
    pasta = pasta_gravada(client.get("s3_folder"), contexto=f"cliente {client.get('id')}")
    if not pasta or not s3_service.is_configured():
        return None
    try:
        existe = await asyncio.to_thread(s3_service._folder_exists, pasta)
    except Exception:  # noqa: BLE001 - ver docstring
        return None
    return pasta if existe else None


async def run_get_download_url(client_id: str, file_path: str) -> dict[str, Any]:
    process, _effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[DOWNLOAD]",
        client_without_process_detail=(
            "Cliente encontrado mas sem processo associado. "
            "Não é possível gerar link de download."
        ),
    )
    assert_s3_file_belongs_to_process(file_path, process)
    url = s3_service.get_presigned_url(file_path)
    if not url:
        raise HTTPException(status_code=500, detail=ERROR_DOWNLOAD_URL)
    return {"success": True, "url": url}


async def run_get_download_url_by_path(file_path: str, *, user: dict) -> dict[str, Any]:
    # SEGURANÇA (IDOR/path-scope): impede gerar pre-signed URLs para chaves
    # S3 fora da árvore de documentos de clientes (ex.: backups/*.zip).
    assert_path_within_document_root(file_path)
    # D-31: e dentro da árvore, só as pastas da rede de quem pede (404).
    await exigir_ficheiro_no_ambito(file_path, user)

    loop = asyncio.get_event_loop()
    for path in s3_path_variations(file_path):
        exists = await loop.run_in_executor(
            None, lambda p=path: s3_service.file_exists(p)
        )
        if exists:
            url = s3_service.get_presigned_url(path)
            if url:
                logger.info(f"[DOWNLOAD-URL] URL gerado para: {path}")
                return {"url": url, "path": path}
    logger.warning(
        f"[DOWNLOAD-URL] Ficheiro não encontrado "
        f"(tentadas variações): {file_path}"
    )
    raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)


async def run_check_employer_nif(nif: str, user: Optional[dict] = None) -> dict[str, Any]:
    if not re.match(r"^\d{9}$", nif):
        raise HTTPException(
            status_code=400,
            detail="NIF inválido. Deve conter exatamente 9 dígitos.",
        )

    # Se o NIF fornecido tiver o prefixo de pessoa colectiva ("5"), também
    # procurar processos onde esse NIF esteja guardado como personal_data.nif
    # (caso de erro de preenchimento comum: NIF da entidade empregadora
    # colocado no campo do próprio titular).
    or_conditions = [{"personal_data.employer_nif": nif}]
    if re.match(r"^5", nif):
        or_conditions.append({"personal_data.nif": nif})

    # Fronteira de rede (Bloco A): «este NIF já existe?» respondia com o
    # nome de clientes de qualquer rede.
    from services.tenant_network import build_tenant_process_condition, com_isolamento
    processes = await db.processes.find(
        com_isolamento(
            await build_tenant_process_condition(user or {}),
            {"$or": or_conditions},
        ),
        {
            "_id": 0,
            "id": 1,
            "client_name": 1,
            "status": 1,
            "created_at": 1,
            "personal_data.employer_name": 1,
            "personal_data.employer_nif": 1,
            "consultor_name": 1,
            "mediador_name": 1,
        },
    ).to_list(100)

    from services.workflow_phases import fases_do_utilizador

    workflow_statuses = await fases_do_utilizador(user or {})
    status_map = {s["name"]: s for s in workflow_statuses}

    results = []
    for proc in processes:
        status_info = status_map.get(proc.get("status"), {})
        results.append(
            {
                "id": proc.get("id"),
                "client_name": proc.get("client_name"),
                "employer_name": proc.get("personal_data", {}).get("employer_name"),
                "status": proc.get("status"),
                "status_label": status_info.get("label", proc.get("status")),
                "status_color": status_info.get("color", "#6B7280"),
                "consultor_name": proc.get("consultor_name"),
                "mediador_name": proc.get("mediador_name"),
                "created_at": proc.get("created_at"),
            }
        )

    return {
        "nif": nif,
        "exists": len(results) > 0,
        "total_count": len(results),
        "processes": results,
    }
