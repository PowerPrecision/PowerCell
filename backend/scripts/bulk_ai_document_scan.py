#!/usr/bin/env python3
"""
====================================================================
BULK AI DOCUMENT SCAN — PowerCell CRM (Pacote CU)
====================================================================
Script de background que percorre os documentos legados associados a
processos ativos e extrai dados com IA, preenchendo campos vazios e
marcando a proveniência no objeto `field_metadata` (source: "ai").

CONTEXTO
--------
A conta da API (OpenAI gpt-4o-mini via EMERGENT_LLM_KEY) é GRATUITA,
pelo que o rate-limit é extremamente conservador:

  • Após cada extração COM SUCESSO  → pausa de 60 segundos (1 min)
  • Após erro de RATE LIMIT (429)   → pausa de 300 segundos (5 min)
                                       ("castigo" da API) + continue
                                       para o próximo documento

O script é IMUNE a falhas: qualquer exceção de rate-limit é capturada,
logada, e o processamento continua para o documento seguinte. Outras
exceções (ficheiro corrupto, S3 indisponível, etc.) são logadas mas
não rebentam o script.

LÓGICA DE PESQUISA
------------------
1. Processos com `is_deleted != True` E estado não-terminal
   (não concluído/desistido/cancelado/arquivado).
2. Para cada processo, verifica se tem campos-chave vazios:
     • Cliente:  dados_pessoais.nif, dados_pessoais.documento_id
     • Processo: financial_data.salario_bruto (e aliases),
                 financial_data.valor_financiado,
                 real_estate_data.valor_imovel,
                 real_estate_data.valor_patrimonial,
                 credit_data.requested_amount, credit_data.interest_rate,
                 credit_data.monthly_payment
3. Processos que tenham pelo menos 1 campo vazio E documentos
   associados (coleção `document_metadata` com s3_path, ou `documents`
   com status UPLOADED/RECEIVED e s3_path) são candidatos.
4. Para cada documento candidato: lê bytes do S3, envia à IA
   (`analyze_single_document`), mapeia extração → campos, atualiza
   BD + field_metadata (source: "ai", updated_at, confidence).

USO
---
    cd backend
    python scripts/bulk_ai_document_scan.py --dry-run
    python scripts/bulk_ai_document_scan.py --limit 10
    python scripts/bulk_ai_document_scan.py --process-id <uuid>
    python scripts/bulk_ai_document_scan.py --sleep-success 60 --sleep-rate-limit 300

DEPENDÊNCIAS
------------
    motor, python-dotenv, openai>=1.99.9, boto3 (via services.s3_storage)
    + serviços internos: services.ai_document, services.s3_storage

NOTAS
-----
- Reutiliza `analyze_single_document` de services/ai_document.py (já tem
  tenacity retry em RateLimitError com backoff exponencial 2-32s, 5 tentativas).
- Este script adiciona uma camada EXTRA de segurança: mesmo após o tenacity
  esgotar as 5 retries, o script faz sleep de 5 min e continua (não rebenta).
- Respeita `manually_edited_fields` do processo (campos editados manualmente
  pelo Consultor não são sobrescritos pela IA).
- Respeita `field_metadata` existente: campos já marcados como "manual" não
  são sobrescritos (o Consultor tem prioridade sobre a IA).
====================================================================
"""
import asyncio
import os
import sys
import argparse
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set

# Bootstrap — adicionar backend/ ao path para imports de serviços
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Imports de serviços do backend (possíveis graças ao sys.path.insert acima)
from services.ai_document import (
    analyze_single_document,
    build_update_data_from_extraction,
    RateLimitError,
)
from services.s3_storage import s3_service

# Carregar .env do backend/
load_dotenv(Path(__file__).parent.parent / '.env')

# ── Constantes ────────────────────────────────────────────────────────
SCRIPT_NAME = "bulk_ai_document_scan"

# Travões de segurança (CRÍTICO — conta gratuita)
DEFAULT_SLEEP_SUCCESS = 60     # 1 minuto após cada extração com sucesso
DEFAULT_SLEEP_RATE_LIMIT = 300  # 5 minutos após erro de rate limit (429)

# Estados terminais — não processar (dados congelados)
TERMINAL_STATUSES = {"concluido", "desistencias", "desistido",
                     "cancelado", "arquivado", "eliminado"}

# Campos-chave a verificar se estão vazios.
# Formato: (mongo_collection, dotted_path, field_metadata_key)
# NOTA: NIF/CC vivem no CLIENT (dados_pessoais); restantes no PROCESS.
KEY_FIELDS_CLIENT = [
    ("dados_pessoais.nif", "dados_pessoais.nif"),
    ("dados_pessoais.documento_id", "dados_pessoais.documento_id"),
]
KEY_FIELDS_PROCESS = [
    ("financial_data.salario_bruto", "financial_data.salario_bruto"),
    ("financial_data.monthly_income", "financial_data.monthly_income"),
    ("financial_data.valor_financiado", "financial_data.valor_financiado"),
    ("real_estate_data.valor_imovel", "real_estate_data.valor_imovel"),
    ("real_estate_data.valor_patrimonial", "real_estate_data.valor_patrimonial"),
    ("credit_data.requested_amount", "credit_data.requested_amount"),
    ("credit_data.interest_rate", "credit_data.interest_rate"),
    ("credit_data.monthly_payment", "credit_data.monthly_payment"),
]


# ── Helpers ───────────────────────────────────────────────────────────
def is_empty(value) -> bool:
    """True se None ou string vazia/whitespace. (0 é NÃO-vazio.)"""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def get_nested(doc: Dict[str, Any], dotted_path: str):
    """Lê caminho pontuado de um dict aninhado. Retorna None se faltar."""
    current = doc
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_document_type_from_filename(filename: str) -> str:
    """Heurística simples baseada no nome do ficheiro (fallback)."""
    name = (filename or "").lower()
    if any(k in name for k in ["cc", "cidadao", "cartao_cidadao", "bi"]):
        return "cc"
    if any(k in name for k in ["recibo", "vencimento", "salario"]):
        return "recibo_vencimento"
    if any(k in name for k in ["irs", "imposto"]):
        return "irs"
    if any(k in name for k in ["cpcv", "contrato_promessa"]):
        return "cpcv"
    if any(k in name for k in ["simulacao", "simulacro"]):
        return "simulacao_credito"
    if any(k in name for k in ["caderneta", "predial"]):
        return "caderneta_predial"
    return "outro"


def get_mime_type(filename: str) -> str:
    """Mapeamento extensão → MIME."""
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    return {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "application/octet-stream")


def is_rate_limit_exception(exc: BaseException) -> bool:
    """Detecta se uma exceção é de rate-limit (429 ou mensagem genérica).

    Cobre:
    - RateLimitError custom de services.ai_document (já levantada pela lib)
    - openai.RateLimitError (se importada)
    - Exceções genéricas cuja mensagem contenha '429', 'rate limit',
      'too many requests', 'quota', 'throttle'
    """
    # Caso 1: exceção do tipo RateLimitError do nosso serviço
    if isinstance(exc, RateLimitError):
        return True
    # Caso 2: openai.RateLimitError (se o SDK o lançar diretamente)
    try:
        from openai import RateLimitError as OpenAIRateLimitError
        if isinstance(exc, OpenAIRateLimitError):
            return True
    except ImportError:
        pass
    # Caso 3: heuristic by message
    msg = str(exc).lower()
    markers = ["429", "rate limit", "rate_limit", "too many requests",
               "quota", "throttle", "tpm", "rpm limit"]
    return any(m in msg for m in markers)


# ── Lógica principal ──────────────────────────────────────────────────
async def find_candidate_documents(db, process_id: Optional[str] = None) -> List[Dict]:
    """Encontra documentos candidatos ao scan.

    Retorna lista de dicts: {process_id, client_id, client_name, s3_path,
    filename, source_collection, doc_id}.
    """
    # 1. Processos ativos não-terminais
    process_query = {
        "is_deleted": {"$ne": True},
        "status": {"$nin": list(TERMINAL_STATUSES)},
    }
    if process_id:
        process_query["id"] = process_id

    processes = await db.processes.find(
        process_query,
        {"_id": 0, "id": 1, "client_id": 1, "client_name": 1,
         "personal_data": 1, "financial_data": 1, "real_estate_data": 1,
         "credit_data": 1, "manually_edited_fields": 1,
         "field_metadata": 1, "status": 1}
    ).to_list(length=None)

    if not processes:
        return []

    # 2. Carregar clientes associados (para verificar dados_pessoais)
    client_ids = [p.get("client_id") for p in processes if p.get("client_id")]
    clients_map = {}
    if client_ids:
        clients_cursor = db.clients.find(
            {"id": {"$in": client_ids}},
            {"_id": 0, "id": 1, "nome": 1, "dados_pessoais": 1,
             "field_metadata": 1, "manually_edited_fields": 1}
        )
        async for c in clients_cursor:
            clients_map[c["id"]] = c

    # 3. Para cada processo, verificar se tem campos-chave vazios
    candidates: List[str] = []  # process_ids com campos vazios
    for p in processes:
        client = clients_map.get(p.get("client_id"), {})
        has_empty = False
        # Campos do cliente (NIF, CC)
        for _, fm_key in KEY_FIELDS_CLIENT:
            # Respeitar manual_edited e field_metadata=manual
            if _is_field_locked(client, p, fm_key):
                continue
            val = get_nested(client, "dados_pessoais." + fm_key.split(".")[-1])
            if is_empty(val):
                has_empty = True
                break
        if not has_empty:
            # Campos do processo
            for path, fm_key in KEY_FIELDS_PROCESS:
                if _is_field_locked(client, p, fm_key):
                    continue
                val = get_nested(p, path)
                if is_empty(val):
                    has_empty = True
                    break
        if has_empty:
            candidates.append(p["id"])

    if not candidates:
        return []

    # 4. Para cada processo candidato, procurar documentos com ficheiro em S3
    docs: List[Dict] = []
    # 4a. Coleção document_metadata (ficheiros categorizados/uploaded)
    dm_cursor = db.document_metadata.find(
        {"process_id": {"$in": candidates}, "s3_path": {"$exists": True, "$ne": None}},
        {"_id": 0, "id": 1, "process_id": 1, "s3_path": 1, "filename": 1,
         "client_name": 1, "mime_type": 1}
    )
    async for d in dm_cursor:
        docs.append({
            "process_id": d["process_id"],
            "s3_path": d["s3_path"],
            "filename": d.get("filename") or "documento.pdf",
            "doc_id": d.get("id"),
            "source_collection": "document_metadata",
        })

    # 4b. Coleção documents (portal — UPLOADED/RECEIVED com s3_path)
    docs_cursor = db.documents.find(
        {"process_id": {"$in": candidates},
         "status": {"$in": ["UPLOADED", "RECEIVED", "SUBMITTED"]},
         "s3_path": {"$exists": True, "$ne": None}},
        {"_id": 0, "id": 1, "process_id": 1, "s3_path": 1, "filename": 1,
         "original_filename": 1, "category": 1, "content_type": 1}
    )
    async for d in docs_cursor:
        docs.append({
            "process_id": d["process_id"],
            "s3_path": d["s3_path"],
            "filename": d.get("original_filename") or d.get("filename") or "documento.pdf",
            "doc_id": d.get("id"),
            "source_collection": "documents",
        })

    # Anexar client_id/client_name a cada doc (para passar à IA)
    proc_map = {p["id"]: p for p in processes}
    for d in docs:
        p = proc_map.get(d["process_id"], {})
        d["client_id"] = p.get("client_id")
        d["client_name"] = p.get("client_name") or "Cliente"

    return docs


def _is_field_locked(client: Dict, process: Dict, fm_key: str) -> bool:
    """True se o campo está bloqueado para escrita pela IA.

    Bloqueia se:
    - Está em manually_edited_fields (lista do processo)
    - Tem field_metadata[source]="manual" (no processo ou no cliente)
    """
    manually_edited = set(process.get("manually_edited_fields") or [])
    if fm_key in manually_edited:
        return True
    # field_metadata pode estar no processo ou no cliente
    for src in (process.get("field_metadata"), client.get("field_metadata")):
        if src and isinstance(src, dict):
            entry = src.get(fm_key)
            if isinstance(entry, dict) and entry.get("source") == "manual":
                return True
    return False


def map_extraction_to_field_metadata(
    update_data: Dict[str, Any], confidence: Optional[float] = None
) -> Dict[str, Dict[str, Any]]:
    """Constrói entradas de field_metadata (source="ai") para cada campo preenchido.

    Mapeia:
      - update_data["personal_data"][field]  → "dados_pessoais.<field>" (vai p/ cliente)
      - update_data["financial_data"][field] → "financial_data.<field>"
      - update_data["real_estate_data"][field] → "real_estate_data.<field>"
      - update_data["credit_data"][field]    → "credit_data.<field>"
    """
    fm: Dict[str, Dict[str, Any]] = {}
    now = now_iso()
    entry = {"source": "ai", "updated_at": now}
    if confidence is not None:
        entry["confidence"] = float(confidence)

    group_mapping = [
        ("personal_data", "dados_pessoais"),       # → cliente
        ("financial_data", "financial_data"),
        ("real_estate_data", "real_estate_data"),
        ("credit_data", "credit_data"),
    ]
    for src_group, fm_prefix in group_mapping:
        group = update_data.get(src_group)
        if isinstance(group, dict):
            for field, value in group.items():
                if is_empty(value):
                    continue
                fm[f"{fm_prefix}.{field}"] = dict(entry)
    return fm


def split_metadata_client_process(
    fm: Dict[str, Dict[str, Any]]
) -> tuple[Dict, Dict]:
    """Separa field_metadata entre o que vai para o cliente vs processo.

    Convenção (Pacote CS/CT): chaves "dados_pessoais.*" e "contacto.*"
    pertencem ao cliente; restantes ao processo.
    """
    client_fm = {}
    process_fm = {}
    for k, v in fm.items():
        if k.startswith("dados_pessoais.") or k.startswith("contacto.") or k == "nome":
            client_fm[k] = v
        else:
            process_fm[k] = v
    return client_fm, process_fm


async def process_single_document(
    db, doc: Dict, dry_run: bool, sleep_success: int
) -> Dict[str, Any]:
    """Processa um documento: lê S3, envia à IA, atualiza BD + field_metadata.

    Retorna um relatório da operação.
    """
    report = {
        "doc_id": doc.get("doc_id"),
        "process_id": doc.get("process_id"),
        "filename": doc.get("filename"),
        "source": doc.get("source_collection"),
        "status": "pending",
        "fields_filled": [],
        "error": None,
    }

    # 1. Verificar S3 configurado
    if not s3_service.is_configured():
        report["status"] = "skipped"
        report["error"] = "S3 não configurado"
        return report

    # 2. Ler bytes do S3 (método síncrono → usar to_thread p/ não bloquear event loop)
    try:
        content = await asyncio.to_thread(
            s3_service.get_file_content, doc["s3_path"]
        )
    except Exception as e:
        report["status"] = "error"
        report["error"] = f"Falha S3: {e}"
        return report

    if not content:
        report["status"] = "skipped"
        report["error"] = "S3 devolveu vazio (ficheiro não encontrado?)"
        return report

    # 3. Carregar processo + cliente atuais (para merge + respeitar locks)
    process = await db.processes.find_one(
        {"id": doc["process_id"]},
        {"_id": 0}
    )
    if not process:
        report["status"] = "skipped"
        report["error"] = "Processo não encontrado"
        return report

    client = None
    if process.get("client_id"):
        client = await db.clients.find_one(
            {"id": process["client_id"]}, {"_id": 0}
        )

    existing_data = {
        "personal_data": {**(process.get("personal_data") or {}),
                          **((client or {}).get("dados_pessoais") or {})},
        "financial_data": process.get("financial_data") or {},
        "real_estate_data": process.get("real_estate_data") or {},
        "credit_data": process.get("credit_data") or {},
    }

    # 4. Chamar a IA — BLOCO CRÍTICO com travão de rate-limit
    try:
        analysis = await analyze_single_document(
            content=content,
            filename=doc["filename"],
            client_name=doc.get("client_name") or "Cliente",
            process_id=doc["process_id"],
        )
    except RateLimitError as e:
        # Rate limit explícito do nosso serviço (após tenacity esgotar retries)
        report["status"] = "rate_limited"
        report["error"] = f"RateLimitError: {e}"
        return report
    except Exception as e:
        # Caso seja rate-limit disfarçado noutra exceção genérica
        if is_rate_limit_exception(e):
            report["status"] = "rate_limited"
            report["error"] = f"Rate-limit detectado: {e}"
            return report
        report["status"] = "error"
        report["error"] = f"Exceção IA: {e}"
        return report

    if not analysis.get("success"):
        err = analysis.get("error", "erro desconhecido")
        # A IA pode devolver success=False por rate-limit interno
        if is_rate_limit_exception(Exception(err)):
            report["status"] = "rate_limited"
            report["error"] = f"IA devolveu rate-limit: {err}"
        else:
            report["status"] = "failed"
            report["error"] = err
        return report

    extracted_data = analysis.get("extracted_data") or {}
    document_type = analysis.get("document_type") or detect_document_type_from_filename(doc["filename"])
    if not extracted_data:
        report["status"] = "empty"
        report["error"] = "IA não extraiu campos"
        return report

    # 5. Mapear extração → formato de update do processo
    update_data = build_update_data_from_extraction(
        extracted_data=extracted_data,
        document_type=document_type,
        existing_data=existing_data,
    )

    # 6. Construir field_metadata (source="ai") para cada campo preenchido
    confidence = analysis.get("confidence")
    new_fm = map_extraction_to_field_metadata(update_data, confidence)

    # Filtrar: respeitar manual_edited_fields e field_metadata=manual existente
    manually_edited = set(process.get("manually_edited_fields") or [])
    existing_process_fm = process.get("field_metadata") or {}
    existing_client_fm = (client or {}).get("field_metadata") or {}
    locked_keys: Set[str] = set()
    for k in new_fm.keys():
        if k in manually_edited:
            locked_keys.add(k)
            continue
        for src_fm in (existing_process_fm, existing_client_fm):
            entry = src_fm.get(k)
            if isinstance(entry, dict) and entry.get("source") == "manual":
                locked_keys.add(k)
                break
    for k in locked_keys:
        new_fm.pop(k, None)
        # Remover também do update_data correspondente
        group, _, field = k.partition(".")
        # Normalizar dados_pessoais → personal_data para update_data
        ud_group = "personal_data" if group == "dados_pessoais" else group
        if ud_group in update_data and isinstance(update_data[ud_group], dict):
            update_data[ud_group].pop(field, None)

    if not new_fm:
        report["status"] = "skipped"
        report["error"] = "Todos os campos extraídos estão bloqueados (manual)"
        return report

    # 7. Separar updates entre cliente e processo
    client_fm, process_fm = split_metadata_client_process(new_fm)

    # Construir $set para processo (financial/real_estate/credit + field_metadata)
    process_set: Dict[str, Any] = {}
    for group in ("financial_data", "real_estate_data", "credit_data"):
        if update_data.get(group):
            for field, value in update_data[group].items():
                if not is_empty(value):
                    process_set[f"{group}.{field}"] = value
    # personal_data no processo é synthetic — NÃO escrever aqui.
    # Dados pessoais (NIF/CC) vão para o cliente abaixo.
    if update_data.get("client_email"):
        process_set["client_email"] = update_data["client_email"]
    if update_data.get("client_phone"):
        process_set["client_phone"] = update_data["client_phone"]
    if process_fm:
        # Merge seguro com field_metadata existente (não apaga outras chaves)
        merged_process_fm = {**existing_process_fm, **process_fm}
        process_set["field_metadata"] = merged_process_fm
    process_set["updated_at"] = now_iso()
    # Registar no histórico de extração IA
    process_set["ai_extraction_history"] = (process.get("ai_extraction_history") or []) + [{
        "doc_id": doc.get("doc_id"),
        "filename": doc.get("filename"),
        "document_type": document_type,
        "fields": list(new_fm.keys()),
        "analyzed_at": now_iso(),
        "source_collection": doc.get("source_collection"),
    }]

    # Construir $set para cliente (dados_pessoais + field_metadata)
    client_set: Dict[str, Any] = {}
    personal = update_data.get("personal_data") or {}
    for field, value in personal.items():
        if not is_empty(value):
            client_set[f"dados_pessoais.{field}"] = value
    if client_fm:
        merged_client_fm = {**existing_client_fm, **client_fm}
        client_set["field_metadata"] = merged_client_fm
    if client_set:
        client_set["updated_at"] = now_iso()

    report["fields_filled"] = list(new_fm.keys())

    # 8. Aplicar na BD (a menos que --dry-run)
    if dry_run:
        report["status"] = "dry_run"
        return report

    if process_set:
        await db.processes.update_one(
            {"id": doc["process_id"]},
            {"$set": process_set}
        )
    if client_set and process.get("client_id"):
        await db.clients.update_one(
            {"id": process["client_id"]},
            {"$set": client_set}
        )

    report["status"] = "success"
    return report


async def run_scan(
    db,
    dry_run: bool,
    limit: int,
    process_id: Optional[str],
    sleep_success: int,
    sleep_rate_limit: int,
) -> None:
    """Loop principal: descobre documentos, processa um a um com pausas."""
    print(f"\n{'='*70}")
    print(f"  {SCRIPT_NAME} — PowerCell CRM (Pacote CU)")
    print(f"  Início: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  BD: {db.name}")
    print(f"  Dry-run: {dry_run}  |  Limite: {limit or 'sem limite'}")
    print(f"  Pausa sucesso: {sleep_success}s  |  Pausa rate-limit: {sleep_rate_limit}s")
    if process_id:
        print(f"  Processo-alvo: {process_id}")
    print(f"{'='*70}\n")

    # 1. Verificar EMERGENT_LLM_KEY (IA)
    if not os.environ.get("EMERGENT_LLM_KEY"):
        print("⚠️  EMERGENT_LLM_KEY não configurada — a IA vai falhar em todos os docs.")
        print("   Continuar mesmo assim (para ver a lógica de descoberta)? A abortar.")
        return

    # 2. Descobrir documentos candidatos
    print("🔎 A descobrir documentos candidatos...")
    docs = await find_candidate_documents(db, process_id=process_id)
    print(f"   Encontrados: {len(docs)} documento(s) candidato(s).")

    if not docs:
        print("ℹ️  Nenhum documento para processar. A sair.")
        return

    # 3. Aplicar limite
    if limit and limit > 0:
        docs = docs[:limit]
        print(f"   Aplicado limite: processar {len(docs)} documento(s).")

    # 4. Loop principal — MUITO DESFASEADO
    stats = {"success": 0, "dry_run": 0, "failed": 0, "error": 0,
             "skipped": 0, "empty": 0, "rate_limited": 0}
    print(f"\n🚀 A iniciar processamento ({len(docs)} docs)...\n")

    for i, doc in enumerate(docs, 1):
        print(f"\n── [{i}/{len(docs)}] {doc['filename']}  "
              f"(proc {doc['process_id'][:8]}..., src={doc['source_collection']})")

        try:
            report = await process_single_document(db, doc, dry_run, sleep_success)
        except RateLimitError as e:
            # Safety net: se escapar do helper interno
            report = {"status": "rate_limited", "error": str(e),
                      "fields_filled": [], "doc_id": doc.get("doc_id"),
                      "process_id": doc.get("process_id"),
                      "filename": doc.get("filename")}
        except Exception as e:
            report = {"status": "error", "error": f"{type(e).__name__}: {e}",
                      "fields_filled": [], "doc_id": doc.get("doc_id"),
                      "process_id": doc.get("process_id"),
                      "filename": doc.get("filename")}
            print(f"   ❌ EXCEÇÃO INESPERADA:\n{traceback.format_exc()}")

        status = report.get("status", "error")
        stats[status] = stats.get(status, 0) + 1

        # ── Relatório do documento ──
        if status == "success":
            print(f"   ✅ Sucesso — campos preenchidos: "
                  f"{', '.join(report.get('fields_filled', [])) or 'nenhum'}")
            print(f"   😴 A pausar {sleep_success}s (rate-limit gratuito)...")
            await asyncio.sleep(sleep_success)

        elif status == "dry_run":
            print(f"   🟡 [DRY-RUN] Campos que seriam preenchidos: "
                  f"{', '.join(report.get('fields_filled', [])) or 'nenhum'}")
            # Em dry-run não há pausa (não houve chamada real à API)

        elif status == "rate_limited":
            print(f"   ⚠️  RATE LIMIT DETETADO: {report.get('error')}")
            print(f"   🛑 A aplicar pausa de 'castigo' de {sleep_rate_limit}s "
                  f"(5 min) e a continuar para o próximo documento...")
            await asyncio.sleep(sleep_rate_limit)
            # continue explícito para o próximo documento
            continue

        elif status == "skipped":
            print(f"   ⏭️  Ignorado: {report.get('error')}")

        elif status == "empty":
            print(f"   ⚪ Sem dados extraídos: {report.get('error')}")

        elif status == "failed":
            print(f"   ❌ Falhou: {report.get('error')}")

        else:  # error
            print(f"   ❌ Erro: {report.get('error')}")

    # 5. Resumo final
    print(f"\n{'='*70}")
    print(f"  RESUMO FINAL — {SCRIPT_NAME}")
    print(f"  Fim: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*70}")
    print(f"  Total documentos processados: {len(docs)}")
    print(f"    ✅ Sucesso:      {stats.get('success', 0)}")
    print(f"    🟡 Dry-run:      {stats.get('dry_run', 0)}")
    print(f"    ⚠️  Rate-limited: {stats.get('rate_limited', 0)}")
    print(f"    ⏭️  Ignorados:    {stats.get('skipped', 0)}")
    print(f"    ⚪ Sem dados:    {stats.get('empty', 0)}")
    print(f"    ❌ Falhas:       {stats.get('failed', 0)}")
    print(f"    💥 Erros:        {stats.get('error', 0)}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description=f"{SCRIPT_NAME} — Scan de documentos legados com IA (Pacote CU)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simular sem escrever na BD (e sem chamar a IA)"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limitar N documentos a processar (0 = sem limite)"
    )
    parser.add_argument(
        "--process-id", type=str, default=None,
        help="Processar apenas documentos de um processo específico"
    )
    parser.add_argument(
        "--sleep-success", type=int, default=DEFAULT_SLEEP_SUCCESS,
        help=f"Pausa após sucesso em segundos (default: {DEFAULT_SLEEP_SUCCESS})"
    )
    parser.add_argument(
        "--sleep-rate-limit", type=int, default=DEFAULT_SLEEP_RATE_LIMIT,
        help=f"Pausa após rate-limit em segundos (default: {DEFAULT_SLEEP_RATE_LIMIT})"
    )
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos no backend/.env")
        sys.exit(1)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    try:
        asyncio.run(run_scan(
            db=db,
            dry_run=args.dry_run,
            limit=args.limit,
            process_id=args.process_id,
            sleep_success=args.sleep_success,
            sleep_rate_limit=args.sleep_rate_limit,
        ))
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrompido pelo utilizador (Ctrl+C). A sair...")
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
