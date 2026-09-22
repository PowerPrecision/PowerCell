"""
====================================================================
Extracção de dados por ficheiro, a partir do S3 (Épico 9)
====================================================================
`POST /api/processes/{id}/documents/extract` recebe o CAMINHO S3 de um
ficheiro já arquivado e devolve os dados que a IA leu nele, comparados
com a ficha do processo.

PORQUE NÃO É UM MOTOR NOVO
--------------------------
O motor de visão já existe em `services/ai_document.py`
(`analyze_document_from_base64` → texto primeiro, visão só quando o texto
não chega; `convert_pdf_to_image` para PDFs digitalizados;
`get_document_tool_definition` com JSON Schema por tipo). Este módulo só
resolve o que faltava: ir buscar os bytes ao S3 em vez de os receber num
formulário multipart. A análise e o formato da resposta são os mesmos de
`/documents/ai-analyze` (`document_ai_analyze.run_analysis_on_documents`),
de propósito — é o contrato que o `AIReviewDialog` consome e que o
`/ai-apply-suggestions` sabe aplicar.

REGRA DE OURO
-------------
Isto NÃO escreve nada na ficha do processo. Devolve o que leu e os
conflitos com o que lá está; quem decide é o consultor, no diálogo de
revisão. Uma alucinação sobre um NIF ou um vencimento não pode entrar na
base de dados sem um humano pelo meio.

SEGURANÇA
---------
O caminho vem do cliente, por isso é validado duas vezes antes de tocar
no S3: dentro da raiz de documentos (`assert_path_within_document_root`)
E dentro do prefixo do processo (`assert_s3_file_belongs_to_process`).
Sem a segunda, um utilizador com acesso a um processo poderia ler
documentos de outro cliente pelo caminho.
====================================================================
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import HTTPException

from database import db
from services.document_ai_analyze import run_analysis_on_documents
from services.document_constants import (
    ERROR_PROCESS_NOT_FOUND,
    ERROR_S3_FILE_NOT_FOUND,
    ERROR_S3_NOT_CONFIGURED,
)
from services.document_process_resolve import (
    assert_path_within_document_root,
    assert_s3_file_belongs_to_process,
)
from services.document_s3_paths import s3_path_variations
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

# Formatos que o motor de visão sabe ler. Um .docx ou um .xlsx não são
# recusados por preciosismo: seguiriam para uma chamada PAGA que devolveria
# lixo. Melhor dizer já que não dá.
EXTENSOES_SUPORTADAS = frozenset({"pdf", "jpg", "jpeg", "png", "webp"})

MIME_POR_EXTENSAO = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

# Alinhado com `ai_document.MAX_FILE_SIZE`.
MAX_TAMANHO_BYTES = 20 * 1024 * 1024

ERRO_FORMATO = (
    "Formato não suportado para extracção. A leitura por IA aceita "
    "imagens (JPG, PNG, WEBP) e PDF."
)
ERRO_CAMINHO_VAZIO = "Caminho do ficheiro em falta."
ERRO_FICHEIRO_GRANDE = "Ficheiro demasiado grande para extracção (máximo 20 MB)."
ERRO_FICHEIRO_VAZIO = "O ficheiro está vazio."


def extensao_de(caminho: str) -> str:
    """Extensão em minúsculas, sem ponto. String vazia se não houver."""
    nome = (caminho or "").rsplit("/", 1)[-1]
    if "." not in nome:
        return ""
    return nome.rsplit(".", 1)[-1].strip().lower()


def formato_suportado(caminho: str) -> bool:
    """O motor de visão sabe ler este ficheiro?"""
    return extensao_de(caminho) in EXTENSOES_SUPORTADAS


def mime_de(caminho: str) -> str:
    """MIME a declarar ao motor, deduzido da extensão."""
    return MIME_POR_EXTENSAO.get(extensao_de(caminho), "application/octet-stream")


def nome_de(caminho: str) -> str:
    """Nome do ficheiro isolado do caminho S3."""
    return (caminho or "").rstrip("/").rsplit("/", 1)[-1]


def _get_s3_object(key: str):
    return s3_service.s3_client.get_object(Bucket=s3_service.bucket_name, Key=key)


async def ler_ficheiro_do_s3(caminho: str) -> tuple[bytes, str]:
    """Descarrega o ficheiro do S3 e devolve `(bytes, caminho_usado)`.

    Tenta as mesmas variações de caminho que o proxy de download
    (`s3_path_variations`): o histórico do bucket tem chaves com underscores
    onde a listagem mostra espaços, e uma extracção que falhasse por isso
    seria indistinguível de um ficheiro inexistente.
    """
    if not s3_service.is_configured():
        logger.error("[EXTRACT] S3 não configurado")
        raise HTTPException(status_code=500, detail=ERROR_S3_NOT_CONFIGURED)

    loop = asyncio.get_event_loop()

    for tentativa in s3_path_variations(caminho):
        try:
            resposta = await loop.run_in_executor(
                None, lambda p=tentativa: _get_s3_object(p)
            )
        except ClientError as e:
            codigo = e.response.get("Error", {}).get("Code", "Desconhecido")
            if codigo in ("NoSuchKey", "AccessDenied"):
                logger.debug("[EXTRACT] Sem ficheiro em %s (%s)", tentativa, codigo)
                continue
            logger.error("[EXTRACT] Erro S3 (%s) em %s: %s", codigo, tentativa, e)
            continue
        except NoCredentialsError:
            logger.error("[EXTRACT] Credenciais S3 em falta")
            raise HTTPException(
                status_code=500, detail="Credenciais S3 não configuradas"
            )
        except Exception as e:  # noqa: BLE001 - qualquer transporte pode falhar
            logger.error(
                "[EXTRACT] Erro inesperado em %s: %s: %s",
                tentativa, type(e).__name__, e,
            )
            continue

        try:
            conteudo = await loop.run_in_executor(None, resposta["Body"].read)
        except Exception as e:  # noqa: BLE001
            logger.error("[EXTRACT] Falha a ler o corpo de %s: %s", tentativa, e)
            raise HTTPException(
                status_code=502, detail="Falha ao obter o ficheiro do armazenamento."
            )

        logger.info(
            "[EXTRACT] Ficheiro obtido: %s (%d bytes)", tentativa, len(conteudo)
        )
        return conteudo, tentativa

    logger.warning("[EXTRACT] Ficheiro não encontrado em nenhuma variação: %s", caminho)
    raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)


async def run_extract_document_data(
    process_id: str,
    s3_path: str,
    *,
    user: dict,
) -> dict[str, Any]:
    """Lê UM ficheiro do S3 e devolve os dados extraídos, sem gravar nada.

    Args:
        process_id: Processo a que o ficheiro pertence.
        s3_path: Caminho S3 completo do ficheiro (vem da listagem do
            `S3FileManager`).
        user: Utilizador autenticado, já validado pelo gate de papéis da rota.

    Returns:
        O mesmo contrato de `/documents/ai-analyze` (`extracted_data`,
        `field_confidence`, `conflicts`, `documents`, `titular_matches`,
        `needs_titular_choice`) mais `source_document`, para o diálogo de
        revisão poder dizer de que ficheiro vieram os dados.
    """
    caminho = (s3_path or "").strip()
    if not caminho:
        raise HTTPException(status_code=400, detail=ERRO_CAMINHO_VAZIO)

    if not formato_suportado(caminho):
        raise HTTPException(status_code=400, detail=ERRO_FORMATO)

    processo = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not processo:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    # Duas guardas, não uma: a primeira impede sair da árvore de documentos
    # (backups, logótipos — vivem no MESMO bucket); a segunda impede ler o
    # processo do vizinho.
    assert_path_within_document_root(caminho)
    assert_s3_file_belongs_to_process(caminho, processo)

    conteudo, caminho_usado = await ler_ficheiro_do_s3(caminho)

    if not conteudo:
        raise HTTPException(status_code=400, detail=ERRO_FICHEIRO_VAZIO)
    if len(conteudo) > MAX_TAMANHO_BYTES:
        raise HTTPException(status_code=400, detail=ERRO_FICHEIRO_GRANDE)

    documento = {
        "content": conteudo,
        "name": nome_de(caminho_usado),
        "mime_type": mime_de(caminho_usado),
        "source_path": caminho_usado,
    }

    # `skip_analyzed=False`: o consultor carregou no botão DESTE ficheiro.
    # Devolver "já foi analisado" e nada mais seria incompreensível.
    resultado = await run_analysis_on_documents(
        process_id, [documento], user=user, skip_analyzed=False
    )

    resultado["source_document"] = {
        "name": documento["name"],
        "s3_path": caminho_usado,
        "mime_type": documento["mime_type"],
        "size": len(conteudo),
    }
    return resultado
