"""
Resolve ID flexível (processo OU cliente) → documento de processo.

Extraído da lógica duplicada em list/upload/download/delete de `routes/documents.py`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.document_constants import (
    ERROR_CLIENT_NOT_FOUND,
    ERROR_CLIENT_WITHOUT_PROCESS,
)
from services.s3_document_root import pasta_gravada

logger = logging.getLogger(__name__)


async def resolve_process_from_flexible_id(
    flexible_id: str,
    *,
    log_prefix: str = "[DOCS]",
    allow_client_without_process: bool = False,
    raise_on_client_without_process: bool = True,
    client_without_process_detail: Optional[str] = None,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Resolve `flexible_id` para (process, effective_process_id).

    Ordem:
    1. processes.id
    2. clients.id → process_ids[0] / processes.client_id
    3. processes.client_id directo

    Returns:
        (process, effective_id)

    Raises:
        HTTPException(404) se não encontrado (ou cliente sem processo quando
        `raise_on_client_without_process` e não `allow_client_without_process`).

    Quando `allow_client_without_process=True` e o cliente existe sem processo:
        devolve (None, None) sem raise.
    """
    without_process_detail = (
        client_without_process_detail or ERROR_CLIENT_WITHOUT_PROCESS
    )

    process = await db.processes.find_one({"id": flexible_id})
    if process:
        logger.debug(f"{log_prefix} Encontrado processo por ID: {flexible_id}")
        return process, process["id"]

    client = await db.clients.find_one({"id": flexible_id})
    if client:
        logger.debug(f"{log_prefix} Encontrado cliente por ID: {flexible_id}")
        process_ids = client.get("process_ids", []) or []
        if process_ids:
            process = await db.processes.find_one({"id": process_ids[0]})
            if process:
                logger.debug(
                    f"{log_prefix} Processo encontrado via process_ids: {process['id']}"
                )
                return process, process["id"]

        process = await db.processes.find_one({"client_id": flexible_id})
        if process:
            logger.debug(
                f"{log_prefix} Processo encontrado via client_id: {process['id']}"
            )
            return process, process["id"]

        if allow_client_without_process:
            logger.info(
                f"{log_prefix} Cliente {flexible_id} existe mas sem processo associado"
            )
            return None, None

        if raise_on_client_without_process:
            raise HTTPException(status_code=404, detail=without_process_detail)

    process = await db.processes.find_one({"client_id": flexible_id})
    if process:
        logger.debug(
            f"{log_prefix} Processo encontrado via client_id (fallback): {process['id']}"
        )
        return process, process["id"]

    logger.warning(
        f"{log_prefix} Nenhum processo ou cliente encontrado para ID: {flexible_id}"
    )
    raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)


def extract_second_client_name(process: dict) -> Optional[str]:
    """Nome do 2º titular a partir do process doc."""
    titular2 = process.get("titular2_data") or {}
    return (
        process.get("second_client_name")
        or titular2.get("nome")
        or titular2.get("name")
    )


# Raiz S3 canónica de todos os documentos de clientes/processos
# (mesma constante usada pelo Explorador de Ficheiros — `admin_s3_explorer.S3_EXPLORER_BASE_PATH`).
# Qualquer outro prefixo do bucket (ex.: "backups/", "companies/") é fora do
# âmbito destes endpoints e NUNCA deve ser servido por eles.
DOCUMENT_S3_ROOT_PREFIX = "Documentação Clientes/"


def assert_path_within_document_root(file_path: str) -> None:
    """
    Garante que `file_path` está contido na árvore de documentos de clientes.

    Os endpoints genéricos de download/proxy (`/documents/proxy/{file_path}`,
    `/documents/download-url/{file_path}`, `/documents/bulk-download`) recebem
    um path S3 arbitrário vindo do cliente e, historicamente, não validavam
    o prefixo — permitindo aceder a QUALQUER chave do bucket S3, incluindo
    backups completos da base de dados (`backups/*.zip`) ou logótipos de
    empresas (`companies/*`), que vivem no MESMO bucket sob outros prefixos.

    Raises:
        HTTPException(403) se o path estiver fora da raiz de documentos.
    """
    from services.document_constants import ERROR_FILE_ACCESS_DENIED

    normalized = (file_path or "").lstrip("/")
    if not normalized.startswith(DOCUMENT_S3_ROOT_PREFIX):
        logger.warning(
            "[SECURITY] Tentativa de acesso fora do âmbito de documentos: %s",
            file_path,
        )
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)


def assert_s3_file_belongs_to_process(file_path: str, process: dict) -> None:
    """
    Garante que `file_path` pertence ao prefixo S3 do processo.

    A comparação é por SEGMENTO de caminho (`s3_document_root.dentro_da_pasta`),
    nunca por texto. Com um `startswith` cru sobre
    `Documentação Clientes/Carolina Silva`, a chave
    `Documentação Clientes/Carolina Silva Agostinho/Financeiros/irs.pdf`
    passava: um processo autorizava a pasta inteira de quem tem o nome mais
    longo. O buraco não precisava do `fuzzy match` nenhum — bastava um nome
    ser prefixo do outro — e é alcançável do PORTAL (ver
    `portal_upload_ops.assert_portal_file_key_e_do_cliente`), para um cliente
    que ainda não tenha `s3_folder`. É a mesma regra que o
    `s3_folder_relink.reescrever_prefixo` já aplicava.

    Sem `s3_folder` E sem nome não há posse que se prove, e recusa-se: o
    degradado antigo produzia o prefixo `Documentação Clientes/` e aceitava a
    árvore de documentos inteira.

    Raises:
        HTTPException(403) se o path estiver fora do scope do cliente/processo.
    """
    from services.document_constants import ERROR_FILE_ACCESS_DENIED
    from services.s3_document_root import dentro_da_pasta

    for prefixo in build_s3_valid_prefixes(process):
        if dentro_da_pasta(file_path, prefixo):
            return
    raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)


def build_s3_valid_prefixes(process: dict) -> list[str]:
    """Prefixos S3 válidos para um processo (batch delete / list checks).

    Ponto único dos prefixos de posse: `assert_s3_file_belongs_to_process`
    deriva daqui em vez de repetir a lista. Duas cópias da mesma lista
    divergem sem dar erro — foi assim que a eliminação em massa ficou com um
    degradado e a verificação individual com outro.

    Devolve prefixos SEM barra final: quem compara usa
    `s3_document_root.dentro_da_pasta`, que trata a fronteira. Uma lista
    VAZIA significa "não há posse demonstrável" e recusa tudo.

    LOTE 8 — O NOME SAIU DAQUI (a última metade da D-19)
    ====================================================
    Sem `s3_folder`, o degradado derivava os prefixos do NOME do cliente
    (`Documentação Clientes/{nome}` e a grafia sanitizada). Dois
    homónimos EXACTOS produziam o MESMO prefixo, logo cada um autorizava
    os ficheiros do outro — e isto é alcançável do **Portal**, por
    `portal_upload_ops._dono_do_prefixo_s3`. Era a D-19 na guarda de
    posse, e não só na leitura.

    O que fica no lugar é o ID: `pasta_do_processo` / `pasta_do_cliente`,
    que é a identidade canónica desde o Lote 6. Não alarga nada (a pasta
    derivada do id de uma ficha é, por construção, a pasta dela) e um id
    que não sirva como segmento não produz prefixo — a lista fica vazia e
    recusa tudo, que é a regra que já existia.
    """
    from services.s3_document_root import (
        normalizar,
        pasta_do_cliente,
        pasta_do_processo,
    )

    s3_folder = pasta_gravada(process.get("s3_folder"))
    if s3_folder and normalizar(s3_folder):
        return [normalizar(s3_folder)]

    # O id serve as duas colecções: um processo e um cliente da Pool
    # (onboarding do Portal, sem processo) derivam da mesma raiz
    # documental. `pasta_do_processo` sem `client_id` dá `RAIZ/{id}`,
    # que é o que `pasta_do_cliente` daria para o mesmo id — logo uma
    # chamada basta, e a outra fica aqui nomeada de propósito para
    # ninguém a reintroduzir como um segundo prefixo.
    assert pasta_do_processo("x" * 8) == pasta_do_cliente("x" * 8)
    derivada = pasta_do_processo(process.get("id"))
    return [derivada] if derivada else []
