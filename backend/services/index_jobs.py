"""Jobs do módulo Index (Lote 12, Fase 2): a análise corre em background e avisa no fim.

NÃO HÁ FILA NOVA. Cada corrida é um `TaskLog` (tipos `INDEX_*`): os eventos
`task_started/progress/completed/failed` que o frontend já escuta dão o tempo
real, e o polling continua a ser o recuo.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Zero bloqueios.** Nada do que se passa aqui (IA em baixo, campo em dúvida,
   alerta da matriz, S3 indisponível) devolve erro a quem clicou nem impede
   «Marcar como Indexado». O pedido devolve já, com o `task_id`; o resultado
   chega como notificação.
2. **Um job activo por (processo, tipo)** — índice único parcial em
   `task_logs.index_job_key` (a lição do D-29: «um activo por processo» tem de ser
   atómico, não um `find_one` seguido de `insert`). A chave só existe enquanto o
   job corre; um job morto a meio liberta-se sozinho passado `PRAZO_DO_JOB_MINUTOS`.
3. **Uma vez por ficheiro.** O ficheiro é lido do S3 (barato) e a impressão digital
   do CONTEÚDO decide se há chamada ao modelo (paga). Um ficheiro substituído no
   mesmo caminho volta a ser analisado; um idêntico, não — `force` ignora isto.
4. **A IA nunca grava na ficha.** Só em `document_metadata`, `process_professional_metadata`,
   `employers` e `process_index_alerts`.
5. **Uma falha de um ficheiro não pára os outros**, e vira um alerta informativo
   (`analise_falhou`) + uma linha no Log da IA com um CÓDIGO (nunca o texto do erro).
6. A notificação final leva números, nunca nomes nem valores.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

from database import db
from models.task_log import TaskStatus, TaskType
from services import index_store as store
from services.background_tasks import spawn_background_task
from services.index_ai import (
    TIPOS_ANALISADOS,
    analisar_documento,
    impressao_digital,
    impressao_do_conjunto,
    tem_a_impressao_atual,
    tipo_de_analise,
)
from services.index_matrix import avaliar
from services.index_status import gravar_contadores
from services.process_ai_log import classificar_falha, registar_accao_ia
from services.task_log_service import TASK_LOG_COLLECTION, TaskLogService

logger = logging.getLogger(__name__)

#: Um job «activo» há mais do que isto está morto (o worker caiu): liberta a chave.
PRAZO_DO_JOB_MINUTOS = 30
#: Acima disto o ficheiro não vai à IA (a leitura é para memória e o custo é por página).
TAMANHO_MAXIMO = 20 * 1024 * 1024

TITULOS = {
    TaskType.INDEX_ANALYSIS: "Index — análise de documentos",
    TaskType.INDEX_SANITIZE: "Index — PDF limpo",
    TaskType.INDEX_FINALIZE: "Index — fecho da indexação",
}


# ====================================================================
# O JOB ACTIVO (atómico)
# ====================================================================
def chave_do_job(process_id: str, tipo: TaskType) -> str:
    return f"{process_id}:{tipo.value}"


async def job_activo(process_id: str, tipo: TaskType) -> Optional[dict]:
    """O job em curso deste processo e tipo, ou `None`."""
    return await db[TASK_LOG_COLLECTION].find_one(
        {"index_job_key": chave_do_job(process_id, tipo)}, {"_id": 0, "task_id": 1, "created_at": 1, "user_id": 1}
    )


async def _libertar_mortos(chave: str) -> None:
    limite = (datetime.now(timezone.utc) - timedelta(minutes=PRAZO_DO_JOB_MINUTOS)).isoformat()
    await db[TASK_LOG_COLLECTION].update_many(
        {"index_job_key": chave, "created_at": {"$lt": limite}}, {"$unset": {"index_job_key": ""}}
    )


async def reivindicar_job(
    process_id: str, tipo: TaskType, user_id: str, *, metadata: Optional[dict] = None
) -> tuple[Optional[str], Optional[str]]:
    """`(task_id, existente)`: `task_id` se criou o job; `existente` se já havia um a correr.

    Nunca os dois. O `$set` da chave é o árbitro: dois pedidos em simultâneo criam
    cada um o seu `TaskLog`, mas só um fica com a chave — o outro cancela o seu.
    """
    chave = chave_do_job(process_id, tipo)
    await _libertar_mortos(chave)
    ja = await job_activo(process_id, tipo)
    if ja:
        return None, ja["task_id"]

    tarefa = await TaskLogService.create_task(
        tipo, user_id or "system", TITULOS[tipo], process_id=process_id, metadata=metadata or {},
        acknowledge_required=False,
    )
    try:
        await db[TASK_LOG_COLLECTION].update_one({"task_id": tarefa.task_id}, {"$set": {"index_job_key": chave}})
    except DuplicateKeyError:
        await TaskLogService.update_task(tarefa.task_id, status=TaskStatus.CANCELLED,
                                         progress_message="Já havia uma análise a correr.")
        ja = await job_activo(process_id, tipo)
        return None, (ja or {}).get("task_id")
    return tarefa.task_id, None


async def libertar_job(task_id: str) -> None:
    """Retira a chave: o job terminou (bem ou mal) e outro pode nascer. Nunca levanta."""
    try:
        await db[TASK_LOG_COLLECTION].update_one({"task_id": task_id}, {"$unset": {"index_job_key": ""}})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Chave do job %s não libertada: %s", task_id, type(exc).__name__)


# ====================================================================
# A NOTIFICAÇÃO FINAL
# ====================================================================
def mensagem_do_resumo(process: dict, resumo: dict) -> tuple[str, str]:
    """`(título, mensagem)` — só números e o nº do processo; nunca nomes nem valores."""
    numero = process.get("process_number")
    ref = f"#{numero}" if numero else str(process.get("id", ""))[:8]
    partes = [f"{resumo.get('analisados', 0)} documento(s) analisado(s)"]
    if resumo.get("saltados"):
        partes.append(f"{resumo['saltados']} já analisado(s)")
    if resumo.get("falhas"):
        partes.append(f"{resumo['falhas']} com falha")
    if resumo.get("alertas"):
        partes.append(f"{resumo['alertas']} alerta(s)")
    if resumo.get("campos_a_rever"):
        partes.append(f"{resumo['campos_a_rever']} campo(s) a rever")
    return f"Análise do processo {ref} concluída", "; ".join(partes) + "."


async def notificar_fim(process: dict, user_id: Optional[str], resumo: dict) -> None:
    """Notificação in-app ao indexador. Nunca levanta (o job já acabou bem)."""
    if not user_id:
        return
    try:
        from services.realtime_notifications import send_realtime_notification

        titulo, mensagem = mensagem_do_resumo(process, resumo)
        await send_realtime_notification(
            user_id=user_id, title=titulo, message=mensagem,
            notification_type="index_analysis_done",
            link=f"/index/{process.get('id')}", process_id=process.get("id"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Notificação final não enviada: %s", type(exc).__name__)


# ====================================================================
# A ANÁLISE
# ====================================================================
async def _ler_ficheiro(s3_path: str) -> tuple[Optional[bytes], Optional[str]]:
    """`(bytes, motivo)`. O motivo é um código de `MOTIVOS`; nunca levanta."""
    try:
        from services.document_vision_extract import ler_ficheiro_do_s3

        conteudo, _ = await ler_ficheiro_do_s3(s3_path)
    except Exception as exc:  # noqa: BLE001 — HTTPException, S3 em baixo…
        logger.warning("[INDEX] Ficheiro %s não lido (%s)", s3_path, type(exc).__name__)
        return None, "ilegivel"
    if len(conteudo) > TAMANHO_MAXIMO:
        return None, "demasiado_grande"
    return conteudo, None


def _mime(filename: str) -> str:
    from services.document_vision_extract import mime_de

    return mime_de(filename)


async def analisar_ficheiros(
    process: dict, *, force: bool, gatilho: str, user: Optional[dict], progresso=None
) -> dict[str, Any]:
    """Analisa os ficheiros do processo que o Index lê. Devolve `{analisados, saltados, falhas, falhados, ignorados}`."""
    process_id = process["id"]
    docs = await db.document_metadata.find(
        {"process_id": process_id, "file_state": {"$ne": "purgado"}}, {"_id": 0}
    ).to_list(500)

    resumo = {"analisados": 0, "saltados": 0, "falhas": 0, "ignorados": 0, "falhados": []}
    candidatos = []
    for doc in docs:
        tipo = tipo_de_analise(doc.get("ai_category"), doc.get("ai_subcategory"), doc.get("filename"))
        if tipo in TIPOS_ANALISADOS and doc.get("s3_path"):
            candidatos.append((doc, tipo))
        else:
            resumo["ignorados"] += 1

    for n, (doc, tipo) in enumerate(candidatos, start=1):
        if progresso:
            await progresso(int(100 * (n - 1) / max(1, len(candidatos))), f"A analisar {n} de {len(candidatos)}…")
        nome = doc.get("filename")
        base = dict(process_id=process_id, accao="analisar", gatilho=gatilho, user=user,
                    ficheiro=nome, s3_path=doc.get("s3_path"), documento_id=doc.get("id"))

        conteudo, motivo = await _ler_ficheiro(doc["s3_path"])
        if conteudo is None:
            resumo["falhas" if motivo == "ilegivel" else "saltados"] += 1
            if motivo == "ilegivel":
                resumo["falhados"].append(doc.get("id"))
            await registar_accao_ia(estado="falha" if motivo == "ilegivel" else "saltado", motivo=motivo, **base)
            continue

        impressao = impressao_digital(conteudo)
        if not force and tem_a_impressao_atual(doc.get("analysis_fingerprint")) and doc["analysis_fingerprint"] == impressao:
            resumo["saltados"] += 1
            await registar_accao_ia(estado="saltado", motivo="ja_analisado", **base)
            continue

        resultado = await analisar_documento(
            tipo=tipo, conteudo=conteudo, filename=nome or "", mime=_mime(nome or ""), document_id=doc.get("id"),
        )
        if not resultado.ok:
            resumo["falhas"] += 1
            resumo["falhados"].append(doc.get("id"))
            await registar_accao_ia(estado="falha", motivo=resultado.motivo or classificar_falha(None), **base)
            continue

        await store.registar_ficheiro(doc["id"], resultado, impressao)
        resumo["analisados"] += 1
        await registar_accao_ia(
            estado="sucesso", categoria=store.CATEGORIA_DO_TIPO[tipo],
            campos=list(resultado.factos.keys()), origem=resultado.origem,
            motivo="sem_contexto" if resultado.sem_contexto else None, **base,
        )
    return resumo


async def concluir_resultados(process: dict, resumo: dict) -> dict[str, Any]:
    """Recalcula metadados, directório e matriz a partir de TUDO o que o processo tem analisado."""
    process_id, rede = process["id"], process.get("network_id")
    docs = await db.document_metadata.find(
        {"process_id": process_id, "file_state": {"$ne": "purgado"}},
        {"_id": 0, "analysis_fingerprint": 1},
    ).to_list(500)
    impressao = impressao_do_conjunto([d.get("analysis_fingerprint") for d in docs])

    metadados = await store.recalcular_metadados(process_id, rede, impressao)
    novas = await store.registar_entidades(metadados.jobs)

    factos = await store.factos_do_processo(process_id)
    conhecidas = await store.entidades_conhecidas(f.get("employer_name") for f in factos)
    achados = avaliar(factos, entidades=conhecidas)
    if resumo.get("falhados"):
        achados.append({"code": "analise_falhou", "refs": [{"document_id": d, "page": None} for d in resumo["falhados"]],
                        "periodo": None})
    run_id = str(uuid.uuid4())
    alertas = await store.substituir_alertas(process_id, rede, run_id, achados)

    campos_a_rever = sum(len(j.campos_a_rever()) for j in metadados.jobs)
    abertos = await store.contar_alertas_abertos(process_id)
    await gravar_contadores(process_id, has_pending_review=metadados.has_pending_review, index_alerts_open=abertos)
    return {"alertas": abertos, "alertas_novos": alertas["inseridos"], "campos_a_rever": campos_a_rever,
            "entidades_novas": novas, "run_id": run_id}


async def analisar_e_concluir(
    process: dict, *, force: bool, gatilho: str, user: Optional[dict], progresso=None
) -> dict[str, Any]:
    """Analisa os ficheiros e recalcula metadados/matriz. Devolve o resumo PÚBLICO (sem ids de falhados).

    Partilhada pela análise manual e pelo fecho da indexação (`index_finalize`): são dois
    jobs diferentes sobre o mesmo trabalho, e duas cópias do corpo divergiriam.
    """
    resumo = await analisar_ficheiros(process, force=force, gatilho=gatilho, user=user, progresso=progresso)
    resumo.update(await concluir_resultados(process, resumo))
    return {k: v for k, v in resumo.items() if k != "falhados"}


async def correr_analise(
    task_id: str, process_id: str, user: Optional[dict], *, force: bool, gatilho: str
) -> dict[str, Any]:
    """O trabalho do job. Termina SEMPRE o TaskLog e liberta a chave; nunca levanta."""
    try:
        await TaskLogService.update_task(task_id, status=TaskStatus.PROCESSING, progress=1,
                                         progress_message="A preparar a análise…")
        process = await db.processes.find_one({"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0})
        if not process:
            await TaskLogService.update_task(task_id, status=TaskStatus.FAILED, error_message="Processo não encontrado.")
            return {}

        async def progresso(pct: int, msg: str) -> None:
            await TaskLogService.update_task(task_id, progress=max(1, min(95, pct)), progress_message=msg)

        publico = await analisar_e_concluir(process, force=force, gatilho=gatilho, user=user, progresso=progresso)
        await TaskLogService.update_task(task_id, status=TaskStatus.COMPLETED, progress=100,
                                         progress_message="Análise concluída.", result_data=publico)
        await notificar_fim(process, (user or {}).get("id"), publico)
        return publico
    except Exception:  # noqa: BLE001 — um job nunca morre calado, nem faz barulho ao cliente
        logger.exception("[INDEX] A análise do processo %s falhou", process_id)
        try:
            await TaskLogService.update_task(task_id, status=TaskStatus.FAILED,
                                             error_message="A análise não terminou. Os documentos não foram alterados.")
        except Exception:  # noqa: BLE001
            pass
        return {}
    finally:
        await libertar_job(task_id)


async def iniciar_analise(
    process_id: str, user: Optional[dict], *, force: bool = False, gatilho: str = "manual"
) -> dict[str, Any]:
    """Cria o job e DEVOLVE JÁ. `{"task_id", "iniciado"}`; `iniciado=False` se já havia um a correr."""
    task_id, existente = await reivindicar_job(
        process_id, TaskType.INDEX_ANALYSIS, (user or {}).get("id") or "system",
        metadata={"force": bool(force), "gatilho": gatilho},
    )
    if task_id is None:
        return {"task_id": existente, "iniciado": False}
    spawn_background_task(
        correr_analise(task_id, process_id, user, force=force, gatilho=gatilho),
        name=f"index-analise-{process_id}",
    )
    return {"task_id": task_id, "iniciado": True}
