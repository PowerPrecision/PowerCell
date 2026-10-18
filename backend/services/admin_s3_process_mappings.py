"""Process ↔ S3 folder mapping ops (list/update/fix-missing/batch).

Do NOT name this module `admin_storage.py` (collides with routes/admin_storage.py).
Extraído de `routes/admin_storage.py`.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException

from database import db
from services.s3_document_root import RAIZ, e_id_gerado
from services.s3_folder_display import caminho_legivel
from services.process_status import ARCHIVED_STATUSES, DELETED_STATUS_VALUES
from services.s3_document_root import (
    PastaGravadaInvalida,
    pasta_gravada,
    pasta_para_gravar,
)

logger = logging.getLogger(__name__)


def _clean_s3_folder(s3_folder: Optional[str]) -> Optional[str]:
    """Validar s3_folder — nem sentinelas de texto, nem valores de outro TIPO.

    A TORNEIRA DO LOTE 8
    Os endpoints em lote (`/process-s3-mappings/batch` e o alias
    `/client-s3-mappings/bulk`) recebem `List[dict]`, e um `dict` não é
    validado pelo FastAPI: os valores entram como vierem. A versão
    anterior desta função perguntava só

        if s3_folder in [None, "", "undefined", "null", "None"]

    e `["a"] in [...]` é `False` — logo a lista era devolvida tal e qual
    e gravada no Mongo. Foi assim que o campo passou a ter valores que
    rebentam o `list_files` com `AttributeError`.

    Corrigir os leitores e deixar isto aberto era esfregar o chão com a
    torneira aberta (regra do `assignment_drift`): a ordem é sempre o
    escritor primeiro.

    LOTE 9 — FECHAR A TORNEIRA A APAGAR NÃO É FECHÁ-LA
    A primeira versão usava o `pasta_gravada` (o primitivo da LEITURA),
    que devolve `None`. O `$set` corria à mesma e escrevia `None` por
    cima de um mapeamento válido: um lote com um valor do tipo errado
    deixava de gravar lixo e passava a APAGAR a pasta da ficha. Hoje
    usa-se o primitivo da ESCRITA, que recusa — e a recusa chega a quem
    gravou (400 no endpoint singular, entrada em `errors` no lote).
    """
    limpo = pasta_para_gravar(s3_folder, contexto="escrita de mapeamento")
    if limpo is None or limpo.lower() in ("undefined", "null", "none"):
        return None
    return limpo


async def run_get_process_s3_mappings(
    search: Optional[str],
    status: Optional[str],
    has_mapping: Optional[bool],
    include_closed: bool,
    include_deleted: bool,
    page: int,
    limit: int,
    user: dict,
    request=None,
):
    """Lista mapeamentos de processos para pastas S3."""
    query = {}

    # Por defeito, excluir processos concluídos e desistências
    # Fix: Normalize process status filters — inclui as variações legadas
    # singular/plural (ver services/process_status.py).
    if not include_closed:
        query["status"] = {"$nin": list(ARCHIVED_STATUSES)}

    # Por defeito, excluir processos eliminados (soft delete)
    if not include_deleted:
        query["is_active"] = {"$ne": False}
        # Também excluir por status "eliminado"/"eliminados" para compatibilidade
        if "status" in query:
            query["status"]["$nin"] = list(
                set(query["status"].get("$nin", [])) | set(DELETED_STATUS_VALUES)
            )
        else:
            query["status"] = {"$nin": list(DELETED_STATUS_VALUES)}

    # Condições que precisam de um `$or` próprio juntam-se por `$and`: a pesquisa e o filtro de
    # «sem mapeamento» escreviam ambos em `query["$or"]` e o segundo apagava o primeiro.
    condicoes_or: list = []
    if search:
        procura = re.escape(search)
        condicoes_or.append({"$or": [
            {"client_name": {"$regex": procura, "$options": "i"}},
            {"client_email": {"$regex": procura, "$options": "i"}},
            {"process_number": {"$regex": procura, "$options": "i"}}
        ]})

    if status:
        query["status"] = status

    if condicoes_or:
        query["$and"] = condicoes_or

    skip = (page - 1) * limit

    # Fronteira de rede (adenda de RBAC): o alias `/client-s3-mappings` é
    # lido por Admin/CEO/Diretor, que só vêem a sua rede. `{}` para o Master.
    from services.tenant_network import build_tenant_process_condition, com_isolamento

    query = com_isolamento(await build_tenant_process_condition(user or {}), query)

    # As contagens são SEMPRE sobre o conjunto sem o filtro de mapeamento: com «só sem pasta»
    # ligado, o cartão «Com mapeamento» dizia 0 e o «Total» igualava o «Sem mapeamento».
    com_pasta = {"s3_folder": {"$exists": True, "$nin": [None, ""]}}
    sem_pasta = {"$or": [{"s3_folder": {"$exists": False}}, {"s3_folder": None}, {"s3_folder": ""}]}
    total = await db.processes.count_documents(query)
    mapped_count = await db.processes.count_documents({"$and": [query, com_pasta]})
    unmapped_count = total - mapped_count

    if has_mapping is True:
        query = {"$and": [query, com_pasta]}
    elif has_mapping is False:
        query = {"$and": [query, sem_pasta]}
    total_filtrado = await db.processes.count_documents(query) if has_mapping is not None else total

    processes = await db.processes.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_number": 1,
            "client_name": 1,
            "client_email": 1,
            "status": 1,
            "s3_folder": 1,
            "client_id": 1,
            "created_at": 1
        }
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    # Só para o ECRÃ: o caminho cru (`…/<uuid>/processos/<uuid>`) não diz nada a quem mapeia.
    # O `s3_folder` continua intacto — é ele que se compara e que se grava.
    for processo in processes:
        processo["s3_folder_display"] = caminho_legivel(
            pasta_gravada(processo.get("s3_folder"), contexto=f"processo {processo.get('id')}"),
            nome_do_cliente=processo.get("client_name"),
            numero_do_processo=processo.get("process_number"),
        )

    from services.s3_storage import s3_service
    available_folders = []

    if s3_service.is_configured():
        try:
            response = s3_service.s3_client.list_objects_v2(
                Bucket=s3_service.bucket_name,
                Prefix="Documentação Clientes/",
                Delimiter="/"
            )

            for prefix in response.get("CommonPrefixes", []):
                folder_path = prefix.get("Prefix", "")
                folder_name = folder_path.replace("Documentação Clientes/", "").rstrip("/")
                if folder_name:
                    available_folders.append({
                        "path": folder_path.rstrip("/"),
                        "name": folder_name
                    })
        except Exception as e:
            logger.warning(f"Erro ao listar pastas S3: {e}")

        available_folders = await _pastas_visiveis_com_nome(available_folders, request, user)

    return {
        "processes": processes,
        "available_folders": available_folders,
        "total": total_filtrado,
        "page": page,
        "limit": limit,
        "pages": (total_filtrado + limit - 1) // limit,
        "s3_configured": s3_service.is_configured(),
        "stats": {
            "total": total,
            "mapped": mapped_count,
            "unmapped": unmapped_count
        }
    }


async def _pastas_visiveis_com_nome(pastas: list, request, user: dict) -> list:
    """As pastas que quem pede pode ver, cada uma com o `display_name` (nome do cliente em vez do uuid).

    Com `request` aplica a mesma parede do Explorador (`filtrar_subpastas`): a lista de pastas de
    topo é a carteira de clientes do bucket inteiro e este endpoint também é lido por Admin/CEO/
    Diretor, que só vêem a sua rede. Sem `request` (chamadores internos) só se acrescenta o nome.
    Falha FECHADA: se a parede não consegue decidir, não se devolve nenhuma pasta.
    """
    if not pastas:
        return []
    try:
        if request is not None:
            from services.s3_explorer_scope import ambito_do_utilizador, filtrar_subpastas
            scope, papel = await ambito_do_utilizador(request, user, vista=True)
            return await filtrar_subpastas(pastas, scope, role=papel)
        from services.s3_explorer_scope import carregar_pastas, nome_legivel
        mapa = await carregar_pastas([p["path"] for p in pastas])
        return [{**p, "display_name": nome_legivel(mapa.get(p["path"]), p.get("name") or "")} for p in pastas]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[S3-MAPPINGS] Não foi possível resolver as pastas visíveis (%s).", exc)
        return [] if request is not None else pastas


async def run_update_process_s3_mapping(process_id: str, s3_folder: Optional[str], user: dict):
    """Actualiza o mapeamento de um processo para uma pasta S3."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    try:
        clean_s3_folder = _clean_s3_folder(s3_folder)
    except PastaGravadaInvalida as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    update_data = {
        "s3_folder": clean_s3_folder,
        "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
        "s3_mapping_updated_by": user["id"]
    }

    await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )

    await db.activity_logs.insert_one({
        "type": "process_s3_mapping_updated",
        "process_id": process_id,
        "updated_by": user["id"],
        "s3_folder": clean_s3_folder,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {
        "success": True,
        "process_id": process_id,
        "s3_folder": clean_s3_folder,
        "client_name": process.get("client_name"),
    }


async def run_fix_missing_client_names(user: dict):
    """
    Corrige processos que não têm client_name definido.
    Extrai o nome da pasta S3 mapeada ou do email do cliente.
    """
    fixed_count = 0

    # Processos sem nome ou com nome "Sem nome"
    processes_without_name = await db.processes.find({
        "$or": [
            {"client_name": None},
            {"client_name": ""},
            {"client_name": "Sem nome"},
            {"client_name": {"$exists": False}}
        ]
    }).to_list(1000)

    for process in processes_without_name:
        new_name = None

        # 1. Tentar extrair da pasta S3
        s3_folder = pasta_gravada(
            process.get("s3_folder"), contexto=f"processo {process.get('id')}"
        )
        if s3_folder:
            # Extrair nome da pasta: "Documentação Clientes/Nome_Cliente" -> "Nome Cliente"
            folder_name = s3_folder.replace(RAIZ, "").rstrip("/")
            # LOTE 6: desde que a pasta deriva do ID, o primeiro segmento é um
            # uuid — e um uuid NÃO é um nome. Sem esta guarda, este reparador
            # gravava o id como `client_name`, que depois sai em emails, PDFs e
            # documentos RGPD. As outras fontes (email, `personal_data`) são
            # melhores do que uma pasta, e é para lá que o caso cai.
            primeiro_segmento = folder_name.split("/")[0]
            if folder_name and not e_id_gerado(primeiro_segmento):
                new_name = folder_name.replace("_", " ").replace("  ", " ")

        # 2. Tentar extrair do email
        if not new_name:
            email = process.get("client_email")
            if email and "@" in email:
                email_name = email.split("@")[0]
                new_name = email_name.replace(".", " ").replace("_", " ").replace("-", " ").title()

        # 3. Tentar extrair de personal_data
        if not new_name:
            personal = process.get("personal_data", {})
            new_name = (
                personal.get("nome_completo") or
                personal.get("nome") or
                personal.get("name")
            )

        # 4. Se ainda não temos nome, usar "Cliente" com número do processo
        if not new_name:
            process_num = process.get("process_number", "Desconhecido")
            new_name = f"Cliente #{process_num}"

        # Actualizar o processo
        if new_name:
            await db.processes.update_one(
                {"id": process["id"]},
                {"$set": {"client_name": new_name, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            fixed_count += 1

    return {
        "success": True,
        "message": f"Corrigidos {fixed_count} processos sem nome",
        "fixed_count": fixed_count,
        "total_found": len(processes_without_name)
    }


async def run_batch_update_process_s3_mappings(mappings: List[dict], user: dict):
    """Actualiza mapeamentos S3 em batch para múltiplos processos."""
    results = {"updated": 0, "failed": 0, "errors": []}

    for mapping in mappings:
        process_id = mapping.get("process_id")
        s3_folder = mapping.get("s3_folder")

        if not process_id:
            results["failed"] += 1
            results["errors"].append({"error": "process_id é obrigatório"})
            continue

        try:
            process = await db.processes.find_one({"id": process_id})
            if not process:
                results["failed"] += 1
                results["errors"].append({"process_id": process_id, "error": "Processo não encontrado"})
                continue

            clean_s3_folder = _clean_s3_folder(s3_folder)

            update_data = {
                "s3_folder": clean_s3_folder,
                "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
                "s3_mapping_updated_by": user["id"]
            }

            await db.processes.update_one(
                {"id": process_id},
                {"$set": update_data}
            )

            results["updated"] += 1

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"process_id": process_id, "error": str(e)})

    # Retornar formato esperado pelo frontend
    return {
        "success": results["failed"] == 0 or results["updated"] > 0,
        "updated": results["updated"],
        "failed": results["failed"],
        "errors": results["errors"]
    }
