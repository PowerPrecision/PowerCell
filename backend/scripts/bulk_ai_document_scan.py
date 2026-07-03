#!/usr/bin/env python3
"""
====================================================================
BULK AI DOCUMENT SCAN — PowerCell CRM (Pacote CV)
====================================================================
Script de background OMNICANAL que percorre TODOS os documentos da
coleção `db.documents` (is_deleted != True), descarrega o binário do
S3, envia à OpenAI (gpt-4o-mini via analyze_document_from_base64) para
extrair dados, e atualiza o processo + field_metadata (source: "ai").

SUBSTITUI o Pacote CU (versão anterior) por uma implementação mais
robusta e estrita, com regras explícitas:

  1. Conexão: motor_asyncio (MONGO_URL, DB_NAME) + boto3 direto
     (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION default
     'eu-north-1', AWS_BUCKET_NAME).
  2. Omnicanal: para cada documento, tenta ler os campos s3_key,
     file_key, key, path, url. Se o valor contiver 'amazonaws.com/',
     faz split e agarra apenas o sufixo (chave limpa). Se nenhuma
     chave for encontrada, faz continue.
  3. Pipeline: descarrega binário do S3 → base64 →
     analyze_document_from_base64(content, mime_type, 'outro').
  4. Rastreabilidade: se a extração for bem-sucedida, marca o
     documento com ai_processed: True. Depois chama
     build_update_data_from_extraction(extracted_data, tipo_detetado,
     process_obj). Se gerar payload, injeta
     field_metadata["secção.campo"] = {"source": "ai",
     "updated_at": data_ISO} e faz $set no processo.
  5. Rate-limiting conservador (conta gratuita):
     • Erro 429 / rate limit → print + await asyncio.sleep(300)
       (5 min de "castigo") + continua.
     • S3 404 / NoSuchKey → aviso + continue (sem pausa).
     • Sucesso → await asyncio.sleep(25) entre documentos.

USO
---
    cd backend
    python scripts/bulk_ai_document_scan.py --dry-run
    python scripts/bulk_ai_document_scan.py --limit 20
    python scripts/bulk_ai_document_scan.py --sleep-success 25 --sleep-rate-limit 300

DEPENDÊNCIAS
------------
    motor, python-dotenv, boto3==1.42.21, botocore (já no requirements.txt)
    + serviços internos: services.ai_document
====================================================================
"""
import asyncio
import os
import sys
import base64
import argparse
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from urllib.parse import unquote

# Bootstrap — adicionar backend/ ao path para imports de serviços
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from botocore.exceptions import ClientError
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Serviços internos do backend
from services.ai_document import (
    analyze_document_from_base64,
    build_update_data_from_extraction,
    RateLimitError,
)

# Carregar .env do backend/
load_dotenv(Path(__file__).parent.parent / '.env')

# ── Constantes ────────────────────────────────────────────────────────
SCRIPT_NAME = "bulk_ai_document_scan"

# Travões de segurança (CRÍTICO — conta gratuita)
DEFAULT_SLEEP_SUCCESS = 25     # 25 segundos entre documentos (sucesso)
DEFAULT_SLEEP_RATE_LIMIT = 300  # 5 minutos após rate limit (429)

# Campos a tentar para encontrar a chave S3 (ordem de prioridade)
S3_KEY_FIELDS = ("s3_key", "file_key", "key", "path", "url")

# Marcador de URL pública S3 — para extrair apenas a chave (sufixo)
S3_URL_MARKER = "amazonaws.com/"

# Grupos de dados que build_update_data_from_extraction pode produzir
PROCESS_DATA_GROUPS = ("personal_data", "financial_data",
                       "real_estate_data", "credit_data")


# ── Helpers ───────────────────────────────────────────────────────────
def now_iso() -> str:
    """Data ISO 8601 atual em UTC (para updated_at e ai_processed_at)."""
    return datetime.now(timezone.utc).isoformat()


def is_empty(value) -> bool:
    """True se None ou string vazia/whitespace. (0 é NÃO-vazio.)"""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def get_mime_type(filename: Optional[str], fallback_content_type: Optional[str] = None) -> str:
    """Mapeia extensão do ficheiro → MIME type.

    Usa primeiro o content_type do documento (se presente), depois a
    extensão do filename. Fallback: application/pdf (porque a maioria
    dos documentos do CRM são PDFs).
    """
    if fallback_content_type and isinstance(fallback_content_type, str) \
            and fallback_content_type.strip():
        return fallback_content_type.strip()
    ext = (filename or "").lower().rsplit(".", 1)[-1] if filename else ""
    return {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "tiff": "image/tiff",
        "bmp": "image/bmp",
    }.get(ext, "application/pdf")


def resolve_s3_key(doc: Dict[str, Any]) -> Optional[str]:
    """Resolução OMNICANAL da chave S3 de um documento.

    Tenta os campos em ordem: s3_key, file_key, key, path, url.
    Se o valor contiver 'amazonaws.com/', faz split e agarra apenas
    o sufixo (a chave limpa). URL-decode o resultado (caso tenha %20
    etc.). Retorna None se nenhuma chave for encontrada.
    """
    for field in S3_KEY_FIELDS:
        raw = doc.get(field)
        if not raw or not isinstance(raw, str):
            continue
        val = raw.strip()
        if not val:
            continue
        # Extrair sufixo se for URL pública do S3
        if S3_URL_MARKER in val:
            val = val.split(S3_URL_MARKER, 1)[-1]
            # O sufixo pode incluir o bucket + chave; remover bucket inicial
            # se começar por '/'
            val = val.lstrip("/")
        # URL-decode (espaços como %20, etc.)
        val = unquote(val)
        if val:
            return val
    return None


def is_rate_limit_exception(exc: BaseException) -> bool:
    """Detecta se uma exceção é de rate-limit (429 ou genérica).

    Cobre:
    - RateLimitError custom de services.ai_document
    - openai.RateLimitError (SDK)
    - botocore ClientError com código Throttling/RequestThrottled
    - Exceções genéricas cuja mensagem contenha marcadores de rate-limit
    """
    # 1. RateLimitError do nosso serviço
    if isinstance(exc, RateLimitError):
        return True
    # 2. openai.RateLimitError
    try:
        from openai import RateLimitError as OpenAIRateLimitError
        if isinstance(exc, OpenAIRateLimitError):
            return True
    except ImportError:
        pass
    # 3. botocore ClientError com código de throttle
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("Throttling", "RequestThrottled", "SlowDown",
                    "ThrottlingException"):
            return True
    # 4. Heurística por mensagem
    msg = str(exc).lower()
    markers = ["429", "rate limit", "rate_limit", "too many requests",
               "quota", "throttle", "tpm", "rpm limit",
               "limite de pedidos", "tente novamente mais tarde"]
    return any(m in msg for m in markers)


def is_s3_not_found_exception(exc: BaseException) -> bool:
    """Detecta se uma exceção é de ficheiro S3 inexistente (404/NoSuchKey)."""
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404", "NoSuchBucket"):
            return True
        # Também HTTP status 404
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if status == 404:
            return True
    msg = str(exc).lower()
    return any(m in msg for m in ["nosuchkey", "not found", "404",
                                  "não encontrado", "nao encontrado"])


# ── Configuração S3 ───────────────────────────────────────────────────
def init_s3_client() -> Tuple[Optional[Any], Optional[str], Optional[str]]:
    """Inicializa cliente boto3 S3 a partir de variáveis de ambiente.

    Retorna (client, bucket_name, error_message).
    Se faltar configuração, retorna (None, None, msg_erro).
    """
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_REGION", "eu-north-1")
    bucket = os.environ.get("AWS_BUCKET_NAME")

    if not aws_key or not aws_secret:
        return None, None, ("AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY "
                            "não configurados")
    if not bucket:
        return None, None, "AWS_BUCKET_NAME não configurado"

    try:
        client = boto3.client(
            "s3",
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            region_name=aws_region,
        )
        return client, bucket, None
    except Exception as e:
        return None, None, f"Falha ao inicializar boto3 S3 client: {e}"


def _download_s3_object_sync(s3_client, bucket: str, key: str) -> bytes:
    """Download síncrono do objeto S3. Levanta ClientError se 404/NoSuchKey."""
    resp = s3_client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


# ── Lógica principal ──────────────────────────────────────────────────
async def process_single_document(
    db,
    s3_client,
    bucket: str,
    doc: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    """Processa um documento: resolve chave S3, descarrega, envia à IA,
    atualiza BD (documento + processo + field_metadata).

    Retorna um relatório da operação.
    """
    doc_id = doc.get("id") or str(doc.get("_id", ""))
    report = {
        "doc_id": doc_id,
        "process_id": doc.get("process_id"),
        "filename": doc.get("original_filename") or doc.get("filename") or "?",
        "status": "pending",
        "fields_filled": [],
        "error": None,
    }

    # 1. Resolver chave S3 (omnicanal)
    s3_key = resolve_s3_key(doc)
    if not s3_key:
        report["status"] = "skipped"
        report["error"] = "Sem chave S3 (s3_key/file_key/key/path/url)"
        return report

    # 2. Descarregar binário do S3 (síncrono → asyncio.to_thread)
    try:
        content = await asyncio.to_thread(
            _download_s3_object_sync, s3_client, bucket, s3_key
        )
    except ClientError as e:
        if is_s3_not_found_exception(e):
            report["status"] = "not_found"
            report["error"] = f"S3 404/NoSuchKey: {s3_key}"
        elif is_rate_limit_exception(e):
            report["status"] = "rate_limited"
            report["error"] = f"S3 Throttle: {e}"
        else:
            report["status"] = "error"
            code = e.response.get("Error", {}).get("Code", "?")
            report["error"] = f"S3 ClientError {code}: {e}"
        return report
    except Exception as e:
        if is_s3_not_found_exception(e):
            report["status"] = "not_found"
            report["error"] = f"S3 404: {s3_key}"
        else:
            report["status"] = "error"
            report["error"] = f"S3 download: {type(e).__name__}: {e}"
        return report

    if not content:
        report["status"] = "empty"
        report["error"] = "S3 devolveu conteúdo vazio"
        return report

    # 3. Converter para base64 + determinar mime_type
    content_b64 = base64.b64encode(content).decode("utf-8")
    filename = doc.get("original_filename") or doc.get("filename") or "documento.pdf"
    mime_type = get_mime_type(filename, doc.get("content_type"))

    # 4. Invocar analyze_document_from_base64 (tipo 'outro' como pedido)
    try:
        result = await analyze_document_from_base64(
            base64_content=content_b64,
            mime_type=mime_type,
            document_type="outro",
        )
    except RateLimitError as e:
        report["status"] = "rate_limited"
        report["error"] = f"RateLimitError: {e}"
        return report
    except Exception as e:
        if is_rate_limit_exception(e):
            report["status"] = "rate_limited"
            report["error"] = f"Rate-limit: {e}"
        else:
            report["status"] = "error"
            report["error"] = f"IA: {type(e).__name__}: {e}"
        return report

    # 5. Verificar sucesso da extração
    if not result.get("success"):
        err = result.get("error", "erro desconhecido")
        if is_rate_limit_exception(Exception(err)):
            report["status"] = "rate_limited"
            report["error"] = f"IA rate-limit: {err}"
        else:
            report["status"] = "failed"
            report["error"] = err
        return report

    extracted_data = result.get("extracted_data") or {}
    detected_type = result.get("document_type") or "outro"

    if not extracted_data:
        report["status"] = "empty"
        report["error"] = "IA não extraiu campos"
        return report

    # 6. Marcar documento como ai_processed: True
    if not dry_run and doc_id:
        await db.documents.update_one(
            {"id": doc_id},
            {"$set": {
                "ai_processed": True,
                "ai_processed_at": now_iso(),
                "ai_document_type": detected_type,
            }}
        )

    # 7. Buscar processo atual para passar ao build_update_data_from_extraction
    process_id = doc.get("process_id")
    if not process_id:
        report["status"] = "success_no_process"
        report["error"] = "Documento sem process_id (só doc marcado)"
        report["fields_filled"] = list(extracted_data.keys())
        return report

    process = await db.processes.find_one({"id": process_id})
    if not process:
        report["status"] = "success_no_process"
        report["error"] = "Processo não encontrado"
        report["fields_filled"] = list(extracted_data.keys())
        return report

    # 8. Construir payload de atualização
    existing_data = {
        "personal_data": process.get("personal_data") or {},
        "financial_data": process.get("financial_data") or {},
        "real_estate_data": process.get("real_estate_data") or {},
        "credit_data": process.get("credit_data") or {},
    }
    update_data = build_update_data_from_extraction(
        extracted_data=extracted_data,
        document_type=detected_type,
        existing_data=existing_data,
    )

    # 9. Construir field_metadata (source: "ai") para cada campo preenchido
    now = now_iso()
    field_metadata_new: Dict[str, Dict[str, Any]] = {}
    process_set: Dict[str, Any] = {}
    for group in PROCESS_DATA_GROUPS:
        group_data = update_data.get(group)
        if not isinstance(group_data, dict):
            continue
        for field, value in group_data.items():
            if is_empty(value):
                continue
            field_metadata_new[f"{group}.{field}"] = {
                "source": "ai",
                "updated_at": now,
            }
            process_set[f"{group}.{field}"] = value

    # Emails/telefone podem vir em chaves top-level do update_data
    if not is_empty(update_data.get("client_email")):
        process_set["client_email"] = update_data["client_email"]
        field_metadata_new["client_email"] = {"source": "ai", "updated_at": now}
    if not is_empty(update_data.get("client_phone")):
        process_set["client_phone"] = update_data["client_phone"]
        field_metadata_new["client_phone"] = {"source": "ai", "updated_at": now}

    if not field_metadata_new:
        report["status"] = "success_no_fields"
        report["error"] = "Extração não gerou campos para atualizar"
        report["fields_filled"] = list(extracted_data.keys())
        return report

    # 10. Merge seguro de field_metadata + $set no processo
    if dry_run:
        report["status"] = "dry_run"
        report["fields_filled"] = list(field_metadata_new.keys())
        return report

    existing_fm = process.get("field_metadata") or {}
    merged_fm = {**existing_fm, **field_metadata_new}
    process_set["field_metadata"] = merged_fm
    process_set["updated_at"] = now

    await db.processes.update_one(
        {"id": process_id},
        {"$set": process_set}
    )

    report["status"] = "success"
    report["fields_filled"] = list(field_metadata_new.keys())
    return report


async def run_scan(
    db,
    s3_client,
    bucket: str,
    dry_run: bool,
    limit: int,
    sleep_success: int,
    sleep_rate_limit: int,
) -> None:
    """Loop principal: query db.documents, processa cada um com pausas."""
    print(f"\n{'='*70}")
    print(f"  {SCRIPT_NAME} — PowerCell CRM (Pacote CV — Omnichannel)")
    print(f"  Início: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  BD: {db.name}  |  Bucket S3: {bucket}")
    print(f"  Dry-run: {dry_run}  |  Limite: {limit or 'sem limite'}")
    print(f"  Pausa sucesso: {sleep_success}s  |  Pausa rate-limit: {sleep_rate_limit}s")
    print(f"{'='*70}\n")

    # 1. Verificar EMERGENT_LLM_KEY (IA)
    if not os.environ.get("EMERGENT_LLM_KEY"):
        print("⚠️  EMERGENT_LLM_KEY não configurada — a IA vai falhar em todos os docs.")

    # 2. Query OMNICANAL: todos os documentos não apagados
    print("🔎 A procurar documentos em db.documents (is_deleted != True)...")
    query = {"is_deleted": {"$ne": True}}
    docs = await db.documents.find(query, {"_id": 0}).to_list(length=None)
    print(f"   Encontrados: {len(docs)} documento(s).")

    if not docs:
        print("ℹ️  Nenhum documento para processar. A sair.")
        return

    # 3. Aplicar limite
    if limit and limit > 0:
        docs = docs[:limit]
        print(f"   Aplicado limite: processar {len(docs)} documento(s).")

    # 4. Loop principal — MUITO DESFASEADO
    stats = {"success": 0, "dry_run": 0, "failed": 0, "error": 0,
             "skipped": 0, "empty": 0, "rate_limited": 0, "not_found": 0,
             "success_no_process": 0, "success_no_fields": 0}
    print(f"\n🚀 A iniciar processamento ({len(docs)} docs)...\n")

    for i, doc in enumerate(docs, 1):
        filename = doc.get("original_filename") or doc.get("filename") or "?"
        print(f"\n── [{i}/{len(docs)}] {filename}  "
              f"(doc {str(doc.get('id', '?'))[:8]}..., "
              f"proc {str(doc.get('process_id', '?'))[:8]}...)")

        try:
            report = await process_single_document(
                db, s3_client, bucket, doc, dry_run
            )
        except RateLimitError as e:
            # Safety net: rate-limit que escape do helper interno
            report = {"status": "rate_limited", "error": str(e),
                      "fields_filled": [],
                      "doc_id": doc.get("id"),
                      "process_id": doc.get("process_id"),
                      "filename": filename}
        except Exception as e:
            report = {"status": "error",
                      "error": f"{type(e).__name__}: {e}",
                      "fields_filled": [],
                      "doc_id": doc.get("id"),
                      "process_id": doc.get("process_id"),
                      "filename": filename}
            print(f"   ❌ EXCEÇÃO INESPERADA:\n{traceback.format_exc()}")

        status = report.get("status", "error")
        stats[status] = stats.get(status, 0) + 1

        # ── Relatório do documento + travões ──
        if status == "success":
            print(f"   ✅ Sucesso — campos preenchidos: "
                  f"{', '.join(report.get('fields_filled', [])) or 'nenhum'}")
            print(f"   😴 A pausar {sleep_success}s (travão de segurança)...")
            await asyncio.sleep(sleep_success)

        elif status == "dry_run":
            print(f"   🟡 [DRY-RUN] Campos que seriam preenchidos: "
                  f"{', '.join(report.get('fields_filled', [])) or 'nenhum'}")
            # Em dry-run não há pausa (não houve chamada real à API)

        elif status == "rate_limited":
            print(f"   ⚠️  RATE LIMIT (429) DETETADO: {report.get('error')}")
            print(f"   🛑 A aplicar pausa de 'castigo' de {sleep_rate_limit}s "
                  f"(5 min) e a continuar para o próximo documento...")
            await asyncio.sleep(sleep_rate_limit)
            continue

        elif status == "not_found":
            print(f"   🚫 S3 404/NoSuchKey: {report.get('error')}")
            print("   ⏭️  A continuar (ficheiro inexistente, sem pausa)...")

        elif status == "skipped":
            print(f"   ⏭️  Ignorado: {report.get('error')}")

        elif status == "empty":
            print(f"   ⚪ Sem dados extraídos: {report.get('error')}")

        elif status == "success_no_process":
            print(f"   ✅ Doc marcado, mas sem processo: {report.get('error')}")

        elif status == "success_no_fields":
            print(f"   ✅ Doc marcado, mas sem campos para atualizar: "
                  f"{report.get('error')}")

        elif status == "failed":
            print(f"   ❌ Falhou: {report.get('error')}")

        else:  # error
            print(f"   ❌ Erro: {report.get('error')}")

    # 5. Resumo final
    print(f"\n{'='*70}")
    print(f"  RESUMO FINAL — {SCRIPT_NAME} (Pacote CV)")
    print(f"  Fim: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*70}")
    print(f"  Total documentos processados: {len(docs)}")
    print(f"    ✅ Sucesso:             {stats.get('success', 0)}")
    print(f"    ✅ Sucesso s/ processo: {stats.get('success_no_process', 0)}")
    print(f"    ✅ Sucesso s/ campos:   {stats.get('success_no_fields', 0)}")
    print(f"    🟡 Dry-run:             {stats.get('dry_run', 0)}")
    print(f"    ⚠️  Rate-limited:        {stats.get('rate_limited', 0)}")
    print(f"    🚫 S3 404 (not found):  {stats.get('not_found', 0)}")
    print(f"    ⏭️  Ignorados (s/ key):  {stats.get('skipped', 0)}")
    print(f"    ⚪ Sem dados extraídos: {stats.get('empty', 0)}")
    print(f"    ❌ Falhas:              {stats.get('failed', 0)}")
    print(f"    💥 Erros:               {stats.get('error', 0)}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description=f"{SCRIPT_NAME} — Bulk AI Document Scanner (Pacote CV, Omnichannel)"
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
        "--sleep-success", type=int, default=DEFAULT_SLEEP_SUCCESS,
        help=f"Pausa após sucesso em segundos (default: {DEFAULT_SLEEP_SUCCESS})"
    )
    parser.add_argument(
        "--sleep-rate-limit", type=int, default=DEFAULT_SLEEP_RATE_LIMIT,
        help=f"Pausa após rate-limit em segundos (default: {DEFAULT_SLEEP_RATE_LIMIT})"
    )
    args = parser.parse_args()

    # 1. Validar MongoDB
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos no backend/.env")
        sys.exit(1)

    # 2. Inicializar cliente S3 (boto3 direto)
    s3_client, bucket, s3_err = init_s3_client()
    if s3_err:
        print(f"❌ Configuração S3 insuficiente: {s3_err}")
        print("   Necessário: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, "
              "AWS_REGION (default 'eu-north-1'), AWS_BUCKET_NAME")
        sys.exit(1)

    # 3. Ligar à BD
    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    try:
        asyncio.run(run_scan(
            db=db,
            s3_client=s3_client,
            bucket=bucket,
            dry_run=args.dry_run,
            limit=args.limit,
            sleep_success=args.sleep_success,
            sleep_rate_limit=args.sleep_rate_limit,
        ))
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrompido pelo utilizador (Ctrl+C). A sair...")
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
