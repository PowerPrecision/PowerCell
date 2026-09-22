"""
Endpoint de upload da nota de voz — Épico 7, Eixo 3.

Faz o mínimo possível de forma síncrona: valida, guarda o áudio, regista a
tarefa e **devolve**. Tudo o que demora (transcrição, IA, escrita na
timeline, criação de tarefas) corre em background — ver
``voice_note_engine.run_voice_note_pipeline``.

PORQUÊ ESTA SEPARAÇÃO
---------------------
Transcrever dois minutos de áudio leva segundos a dezenas de segundos. Um
pedido HTTP que espere por isso ocupa o *worker*, arrisca o timeout do
proxy e deixa o consultor a olhar para um botão bloqueado. Foi exactamente
o erro do envio de email awaited no registo público (incidente CI
2026-09-21): a lição está aplicada aqui desde o primeiro dia.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile

from database import db
from services.background_tasks import spawn_background_task
from services.voice_note_engine import registar_nota, run_voice_note_pipeline
from services.voice_transcription import formato_suportado

logger = logging.getLogger(__name__)

# Papéis que NÃO podem ditar notas: o cliente não tem acesso ao CRM e o
# parceiro é um utilizador fantasma, só de leitura (ver `block_parceiro`).
PAPEIS_BLOQUEADOS = frozenset({"cliente", "parceiro"})

# Categoria/pasta S3 onde o áudio fica arquivado, ao lado dos documentos do
# processo. Fica num sítio previsível para efeitos de RGPD (apagar a pasta
# do cliente apaga também as notas de voz).
PASTA_S3 = "Notas de Voz"

MAX_MB_OMISSAO = 25.0


def limite_de_tamanho_mb(ambiente=None) -> float:
    """Tamanho máximo aceite, em MB (``VOICE_NOTE_MAX_MB``).

    Um valor inválido ou não-positivo cai no valor por omissão: sem limite,
    um upload grande bastava para esgotar a memória do *worker*.
    """
    env = ambiente if ambiente is not None else os.environ
    bruto = (env.get("VOICE_NOTE_MAX_MB") or "").strip()
    if not bruto:
        return MAX_MB_OMISSAO
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        logger.warning(f"[NOTA-VOZ] VOICE_NOTE_MAX_MB='{bruto}' inválido")
        return MAX_MB_OMISSAO
    return valor if valor > 0 else MAX_MB_OMISSAO


async def _arquivar_audio(
    *,
    conteudo: bytes,
    filename: str,
    mime_type: str,
    processo: dict,
) -> Optional[str]:
    """Guarda o áudio no S3, na pasta do processo. Falhar aqui não é fatal.

    O pipeline recebe os bytes em memória, pelo que o arquivo serve para o
    consultor poder voltar a ouvir a nota — não é uma dependência do
    processamento. Um S3 mal configurado em dev não pode impedir a nota.
    """
    try:
        import asyncio
        import io

        from services.s3_storage import s3_service

        if not s3_service.is_configured():
            logger.info("[NOTA-VOZ] S3 não configurado — áudio não arquivado")
            return None

        return await asyncio.to_thread(
            s3_service.upload_file,
            io.BytesIO(conteudo),
            processo.get("id") or "",
            processo.get("client_name") or "",
            PASTA_S3,
            filename,
            mime_type,
        )
    except Exception as e:
        logger.warning(f"[NOTA-VOZ] Áudio não arquivado no S3: {e}")
        return None


async def run_create_voice_note(
    process_id: str,
    ficheiro: UploadFile,
    current_user: dict,
) -> dict:
    """Recebe a gravação e lança o processamento em background.

    Returns:
        ``{"voice_note_id", "task_id", "process_id", "status", "s3_path"}``
        — o ``task_id`` é o que o frontend usa para seguir o progresso pelos
        eventos ``task_*`` que já escuta.
    """
    if str(current_user.get("role") or "").lower() in PAPEIS_BLOQUEADOS:
        raise HTTPException(
            status_code=403,
            detail="O seu perfil não permite registar notas de voz.",
        )

    processo = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, "id": 1, "client_name": 1, "process_ref": 1}
    )
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    mime_type = (ficheiro.content_type or "").strip()
    if not formato_suportado(mime_type):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato de áudio não suportado ({mime_type or 'desconhecido'}). "
                "Use webm, ogg, mp3, m4a ou wav."
            ),
        )

    conteudo = await ficheiro.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="O ficheiro de áudio está vazio.")

    limite_bytes = int(limite_de_tamanho_mb() * 1024 * 1024)
    if len(conteudo) > limite_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"A gravação excede o limite de {limite_de_tamanho_mb():.0f} MB. "
                "Grave uma nota mais curta."
            ),
        )

    nota_id = str(uuid.uuid4())
    filename = (ficheiro.filename or "").strip() or f"nota-de-voz-{nota_id}.webm"

    s3_path = await _arquivar_audio(
        conteudo=conteudo, filename=filename, mime_type=mime_type, processo=processo
    )

    # ── Tarefa de acompanhamento (dá o tempo real de graça) ───────────
    task_id = None
    try:
        from models.task_log import TaskType
        from services.task_log_service import TaskLogService

        tarefa = await TaskLogService.create_task(
            TaskType.VOICE_NOTE,
            current_user.get("id") or "system",
            "Nota de voz — transcrição e extracção",
            description=(
                "Transcrição do áudio, resumo para o histórico e extracção "
                "das tarefas mencionadas."
            ),
            process_id=process_id,
            metadata={"voice_note_id": nota_id, "filename": filename},
        )
        task_id = tarefa.task_id
    except Exception as e:  # pragma: no cover — TaskLog indisponível
        logger.warning(f"[NOTA-VOZ] Tarefa de acompanhamento não criada: {e}")

    await registar_nota(
        nota_id=nota_id,
        process_id=process_id,
        user=current_user,
        filename=filename,
        mime_type=mime_type,
        tamanho=len(conteudo),
        s3_path=s3_path,
        task_id=task_id,
    )

    spawn_background_task(
        run_voice_note_pipeline(
            nota_id=nota_id,
            process_id=process_id,
            user=current_user,
            audio=conteudo,
            filename=filename,
            mime_type=mime_type,
            task_id=task_id,
        ),
        name=f"voice-note:{nota_id}",
    )

    logger.info(
        f"[NOTA-VOZ] Nota {nota_id} recebida para o processo {process_id} "
        f"({len(conteudo)} bytes, tarefa {task_id})"
    )
    return {
        "voice_note_id": nota_id,
        "task_id": task_id,
        "process_id": process_id,
        "status": "processing",
        "s3_path": s3_path,
    }


async def run_list_voice_notes(process_id: str, current_user: dict) -> list:
    """Notas de voz já registadas no processo (mais recentes primeiro)."""
    if str(current_user.get("role") or "").lower() in PAPEIS_BLOQUEADOS:
        raise HTTPException(status_code=403, detail="Acesso negado")

    notas = await db.voice_notes.find(
        {"process_id": process_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return notas
