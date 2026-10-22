"""Reanálise retroactiva LENTA do Index (Out 2026): o banco dos extratos e a localidade dos recibos.

Os extratos analisados antes de o banco ser obrigatório não o têm, e os recibos antigos não têm a localidade da
entidade — logo a pesquisa avançada não os encontra por banco nem por zona. Reanalisar tudo de uma vez seria
milhares de chamadas pagas (a direcção decidiu que não há reanálise em massa: `ESQUEMA_VERSAO` não mudou).
Este módulo preenche o que falta **aos poucos**: um lote pequeno por execução, pensado para um cron.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Contido por construção.** Um lote por execução (`SLOW_BACKFILL_BATCH_SIZE`, 20 por omissão, tecto
   `TECTO_DO_LOTE`); um valor inválido ou ≤ 0 cai na omissão — nunca desliga o tecto. Uma pausa entre chamadas.
2. **Só acrescenta o campo que falta.** Não se reescreve o `index_facts` nem o `index_job` do documento: uma
   segunda leitura do modelo mudaria, sem ninguém ver, valores que uma pessoa já conferiu. O patch é UM campo
   (`index_facts.bank`/`bank_key` ou `index_job.employer_location`) e só quando a releitura o encontrou.
3. **A impressão digital não se toca.** `analysis_fingerprint` fica como está — é ela que faz a análise normal
   saltar este ficheiro. E se o conteúdo do ficheiro já NÃO bate com ela (foi substituído), este job não lhe
   toca: não se misturam factos de dois ficheiros; a análise normal tratará dele (marca terminal `conteudo_alterado`).
4. **Nunca entra em ciclo.** Cada documento tem uma marca (`slow_backfill_ia`): `preenchido` (achou), `sem_valor`
   (o documento realmente não diz — não se volta a pagar), `conteudo_alterado`, `demasiado_grande`, `sem_processo`
   ou `falhou` (3 falhas transitórias). Uma falha transitória (S3, IA em baixo) só conta tentativas: não bloqueia a
   cabeça da fila, porque os candidatos saem ordenados por tentativas.
5. **Uma execução de cada vez por documento**: reserva atómica (`reservado_ate`) antes de gastar a chamada — dois
   crons sobrepostos não pagam duas vezes o mesmo ficheiro.
6. **IA simulada nunca corre** (`INDEX_AI_PROVIDER` ≠ openai): escreveria dados simulados por cima de leituras
   reais. O script recusa (código de saída 3).
7. **Só o que tem bytes**: um original `purgado` não se relê (os dados lidos dele continuam verdadeiros, e o PDF
   limpo não é analisado). O PDF limpo (`is_clean_pdf`) também não.
8. Depois do lote recalcula-se cada processo afectado pelo MESMO caminho da análise (`concluir_resultados`): os
   metadados profissionais (a localidade do emprego), a pesquisa por documento e a matriz — sem notificações.
9. **O progresso só leva ids e contagens** — nunca nomes de ficheiros, de entidades nem valores.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from database import db
from services import index_jobs
from services.index_ai import (
    PROVIDER_OPENAI,
    TIPO_EXTRATO,
    TIPO_RECIBO,
    ORIGEM_IA,
    analisar_documento,
    impressao_digital,
    resolver_provider,
    tem_a_impressao_atual,
)
from services.index_store import CATEGORIA_DO_TIPO
from services.process_ai_log import classificar_falha, registar_accao_ia

logger = logging.getLogger(__name__)

LOTE_POR_OMISSAO = 20
TECTO_DO_LOTE = 200
PAUSA_POR_OMISSAO_SEGUNDOS = 1.0
TENTATIVAS_MAXIMAS = 3
RESERVA_MINUTOS = 15
CAMPO_DA_MARCA = "slow_backfill_ia"

#: tipo de análise → (o que falta, `doc_type` legível para o relatório)
CAMPOS_EM_FALTA = {TIPO_EXTRATO: "banco", TIPO_RECIBO: "localidade"}
ESTADOS_TERMINAIS = ("preenchido", "sem_valor", "conteudo_alterado", "demasiado_grande", "sem_processo", "falhou")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _inteiro_positivo(valor: Any, omissao: int, tecto: int) -> int:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return omissao
    return omissao if n <= 0 else min(n, tecto)


def tamanho_do_lote(ambiente=None, *, pedido: Optional[int] = None) -> int:
    """`--batch-size` (se vier) ou `SLOW_BACKFILL_BATCH_SIZE`; inválido/≤0 → 20; nunca acima do tecto."""
    if pedido is not None:
        return _inteiro_positivo(pedido, LOTE_POR_OMISSAO, TECTO_DO_LOTE)
    fonte = ambiente if ambiente is not None else os.environ
    return _inteiro_positivo(fonte.get("SLOW_BACKFILL_BATCH_SIZE"), LOTE_POR_OMISSAO, TECTO_DO_LOTE)


def pausa_entre_chamadas(ambiente=None) -> float:
    fonte = ambiente if ambiente is not None else os.environ
    try:
        valor = float(str(fonte.get("SLOW_BACKFILL_PAUSE_SECONDS", PAUSA_POR_OMISSAO_SEGUNDOS)).strip())
    except (TypeError, ValueError):
        return PAUSA_POR_OMISSAO_SEGUNDOS
    return PAUSA_POR_OMISSAO_SEGUNDOS if valor < 0 else min(valor, 60.0)


def condicao_dos_candidatos(tipos: Optional[tuple[str, ...]] = None, *, agora: Optional[datetime] = None) -> dict:
    """Os documentos a que falta o banco (extratos) ou a localidade (recibos), ainda sem marca terminal. Pura.

    `$in: [None, ""]` casa também com o campo AUSENTE (o que as análises antigas deixaram).
    """
    agora = agora or _agora()
    ramos: list[dict] = []
    if TIPO_EXTRATO in (tipos or CAMPOS_EM_FALTA):
        ramos.append({"index_facts.tipo": TIPO_EXTRATO, "index_facts.bank_key": {"$in": [None, ""]}})
    if TIPO_RECIBO in (tipos or CAMPOS_EM_FALTA):
        ramos.append({
            "index_facts.tipo": TIPO_RECIBO,
            "index_job": {"$type": "object"},
            "index_job.employer_location": {"$in": [None, ""]},
        })
    if not ramos:
        return {"id": {"$in": []}}
    return {
        "is_clean_pdf": {"$ne": True},
        "file_state": {"$ne": "purgado"},
        "s3_path": {"$nin": [None, ""]},
        "analysis_fingerprint": {"$nin": [None, ""]},
        f"{CAMPO_DA_MARCA}.estado": {"$exists": False},
        "$and": [
            {"$or": ramos},
            {"$or": [
                {f"{CAMPO_DA_MARCA}.reservado_ate": {"$exists": False}},
                {f"{CAMPO_DA_MARCA}.reservado_ate": {"$lte": agora}},
            ]},
        ],
    }


ORDEM_DOS_CANDIDATOS = [(f"{CAMPO_DA_MARCA}.tentativas", 1), ("index_analyzed_at", 1), ("id", 1)]
PROJECCAO_DO_CANDIDATO = {
    "_id": 0, "id": 1, "process_id": 1, "filename": 1, "s3_path": 1, "analysis_fingerprint": 1,
    "index_origin": 1, "index_facts.tipo": 1, f"{CAMPO_DA_MARCA}.tentativas": 1,
}


async def contar_candidatos(tipos: Optional[tuple[str, ...]] = None) -> dict[str, int]:
    """Quantos documentos faltam, por tipo. Só lê."""
    saida: dict[str, int] = {}
    for tipo, campo in CAMPOS_EM_FALTA.items():
        if tipos and tipo not in tipos:
            continue
        saida[campo] = await db.document_metadata.count_documents(condicao_dos_candidatos((tipo,)))
    return saida


def patch_do_campo(tipo: str, resultado) -> Optional[dict[str, Any]]:
    """O `$set` de UM campo a partir da releitura, ou `None` se o documento continua a não o dizer. Puro."""
    if tipo == TIPO_EXTRATO:
        chave = (resultado.factos or {}).get("bank_key")
        nome = (resultado.factos or {}).get("bank")
        return {"index_facts.bank": nome, "index_facts.bank_key": chave} if chave and nome else None
    localidade = getattr(resultado.job, "employer_location", None) if resultado.job is not None else None
    return {"index_job.employer_location": localidade} if localidade else None


async def _reservar(doc_id: str) -> bool:
    """Reserva atómica do documento: só quem a ganha gasta a chamada."""
    agora = _agora()
    r = await db.document_metadata.update_one(
        {
            "id": doc_id,
            f"{CAMPO_DA_MARCA}.estado": {"$exists": False},
            "$or": [
                {f"{CAMPO_DA_MARCA}.reservado_ate": {"$exists": False}},
                {f"{CAMPO_DA_MARCA}.reservado_ate": {"$lte": agora}},
            ],
        },
        {"$set": {f"{CAMPO_DA_MARCA}.reservado_ate": agora + timedelta(minutes=RESERVA_MINUTOS)}},
    )
    return r.modified_count == 1


async def _marcar(doc_id: str, estado: str, **extra: Any) -> None:
    await db.document_metadata.update_one(
        {"id": doc_id},
        {"$set": {f"{CAMPO_DA_MARCA}.estado": estado, f"{CAMPO_DA_MARCA}.em": _agora(), **{f"{CAMPO_DA_MARCA}.{k}": v for k, v in extra.items()}},
         "$unset": {f"{CAMPO_DA_MARCA}.reservado_ate": ""}},
    )


async def _falha_transitoria(doc: dict, motivo: str) -> str:
    """Conta a tentativa e liberta a reserva; à terceira passa a terminal. Devolve o estado do resumo."""
    tentativas = int((doc.get(CAMPO_DA_MARCA) or {}).get("tentativas") or 0) + 1
    if tentativas >= TENTATIVAS_MAXIMAS:
        await _marcar(doc["id"], "falhou", tentativas=tentativas, motivo=motivo)
        return "falhou"
    await db.document_metadata.update_one(
        {"id": doc["id"]},
        {"$set": {f"{CAMPO_DA_MARCA}.tentativas": tentativas, f"{CAMPO_DA_MARCA}.motivo": motivo},
         "$unset": {f"{CAMPO_DA_MARCA}.reservado_ate": ""}},
    )
    return "adiado"


async def _processar(doc: dict, tipo: str, *, permitir_simulado: bool = False) -> str:
    """Um documento. Devolve o estado para o resumo: um terminal, `adiado` ou `reservado_por_outro`."""
    if not await _reservar(doc["id"]):
        return "reservado_por_outro"
    campo = CAMPOS_EM_FALTA[tipo]
    base = dict(process_id=doc.get("process_id"), accao="analisar", gatilho="automatico", ficheiro=doc.get("filename"),
                s3_path=doc.get("s3_path"), documento_id=doc["id"])

    processo = await db.processes.find_one({"id": doc.get("process_id"), "is_deleted": {"$ne": True}}, {"_id": 0, "id": 1})
    if not processo:
        await _marcar(doc["id"], "sem_processo")
        return "sem_processo"

    conteudo, motivo = await index_jobs._ler_ficheiro(doc["s3_path"])
    if conteudo is None:
        if motivo == "demasiado_grande":
            await _marcar(doc["id"], "demasiado_grande")
            await registar_accao_ia(estado="saltado", motivo=motivo, **base)
            return "demasiado_grande"
        await registar_accao_ia(estado="falha", motivo=motivo, **base)
        return await _falha_transitoria(doc, motivo or "ilegivel")

    # o ficheiro tem de ser AQUELE que foi analisado: com outro conteúdo, os factos guardados já não lhe pertencem
    if not tem_a_impressao_atual(doc.get("analysis_fingerprint")) or impressao_digital(conteudo) != doc["analysis_fingerprint"]:
        await _marcar(doc["id"], "conteudo_alterado")
        await registar_accao_ia(estado="saltado", motivo="ja_analisado", **base)
        return "conteudo_alterado"

    resultado = await analisar_documento(
        tipo=tipo, conteudo=conteudo, filename=doc.get("filename") or "", mime=index_jobs._mime(doc.get("filename") or ""),
        document_id=doc["id"],
    )
    if not resultado.ok or (resultado.origem != ORIGEM_IA and not permitir_simulado):
        codigo = resultado.motivo or classificar_falha(None)
        await registar_accao_ia(estado="falha", motivo=codigo, **base)
        return await _falha_transitoria(doc, codigo)

    patch = patch_do_campo(tipo, resultado)
    if patch is None:
        await _marcar(doc["id"], "sem_valor", campo=campo, modelo=resultado.modelo)
        await registar_accao_ia(estado="sucesso", campos=[], origem=resultado.origem,
                                categoria=CATEGORIA_DO_TIPO[tipo], **base)
        return "sem_valor"

    await db.document_metadata.update_one(
        {"id": doc["id"]},
        {"$set": {**patch, "updated_at": _agora().isoformat(),
                  f"{CAMPO_DA_MARCA}.estado": "preenchido", f"{CAMPO_DA_MARCA}.em": _agora(),
                  f"{CAMPO_DA_MARCA}.campo": campo, f"{CAMPO_DA_MARCA}.modelo": resultado.modelo},
         "$unset": {f"{CAMPO_DA_MARCA}.reservado_ate": ""}},
    )
    await registar_accao_ia(estado="sucesso", campos=sorted(k.rsplit(".", 1)[-1] for k in patch), origem=resultado.origem,
                            categoria=CATEGORIA_DO_TIPO[tipo], **base)
    return "preenchido"


class IASimulada(RuntimeError):
    """O motor de IA configurado é o simulado: não se reanalisa histórico com dados inventados."""


async def correr_lote(
    *,
    tamanho: int,
    tipos: Optional[tuple[str, ...]] = None,
    pausa: float = 0.0,
    escrever: Callable[[str], None] = print,
    permitir_simulado: bool = False,
    dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    """Processa UM lote e devolve o resumo. Nunca excede `tamanho` documentos nem `TECTO_DO_LOTE`."""
    if resolver_provider() != PROVIDER_OPENAI and not permitir_simulado:
        raise IASimulada("INDEX_AI_PROVIDER não é 'openai': a reanálise retroactiva só corre com o motor real.")
    tamanho = min(max(1, int(tamanho)), TECTO_DO_LOTE)
    consulta = condicao_dos_candidatos(tipos)
    candidatos = await (
        db.document_metadata.find(consulta, PROJECCAO_DO_CANDIDATO).sort(ORDEM_DOS_CANDIDATOS).limit(tamanho)
    ).to_list(tamanho)

    resumo: dict[str, Any] = {
        "lote": tamanho, "candidatos": len(candidatos), "por_estado": {}, "processos": set(),
    }
    for n, doc in enumerate(candidatos, start=1):
        tipo = ((doc.get("index_facts") or {}).get("tipo"))
        if tipo not in CAMPOS_EM_FALTA:
            continue
        try:
            estado = await _processar(doc, tipo, permitir_simulado=permitir_simulado)
        except Exception as exc:  # noqa: BLE001 — um documento a rebentar não pára o lote
            logger.warning("[SLOW-BACKFILL] %s: %s", doc.get("id"), type(exc).__name__)
            estado = "erro_interno"
            try:
                estado = await _falha_transitoria(doc, "erro_interno")
            except Exception:  # noqa: BLE001
                pass
        resumo["por_estado"][estado] = resumo["por_estado"].get(estado, 0) + 1
        if estado in ("preenchido", "sem_valor") and doc.get("process_id"):
            resumo["processos"].add(doc["process_id"])
        escrever(f"[slow-backfill] {n}/{len(candidatos)} doc={doc['id']} tipo={CAMPOS_EM_FALTA[tipo]} → {estado}")
        if pausa > 0 and n < len(candidatos) and estado not in ("reservado_por_outro", "sem_processo"):
            await dormir(pausa)

    resumo["recalculados"] = await recalcular_processos(resumo["processos"], escrever=escrever)
    resumo["processos"] = len(resumo["processos"])
    return resumo


async def recalcular_processos(ids, *, escrever: Callable[[str], None] = print) -> int:
    """Metadados, pesquisa por documento e matriz de cada processo tocado — pelo caminho da análise normal."""
    feitos = 0
    for process_id in sorted(ids):
        try:
            processo = await db.processes.find_one({"id": process_id}, {"_id": 0, "id": 1, "network_id": 1})
            if processo:
                await index_jobs.concluir_resultados(processo, {"falhados": []})
                feitos += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[SLOW-BACKFILL] Processo %s não recalculado: %s", process_id, type(exc).__name__)
            escrever(f"[slow-backfill] processo={process_id} recálculo falhou ({type(exc).__name__})")
    return feitos


__all__ = [
    "CAMPOS_EM_FALTA", "CAMPO_DA_MARCA", "ESTADOS_TERMINAIS", "IASimulada", "LOTE_POR_OMISSAO", "TECTO_DO_LOTE",
    "condicao_dos_candidatos", "contar_candidatos", "correr_lote", "pausa_entre_chamadas", "patch_do_campo",
    "recalcular_processos", "tamanho_do_lote",
]
