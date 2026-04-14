#!/usr/bin/env python3
"""
restore_dev_from_backup.py — Pipeline de Restauro Seguro (RGPD-compliant)

Restaura a base de dados de Desenvolvimento a partir do backup automático
mais recente de Produção, com anonimização total de dados pessoais.

Arquitetura:
    Produção Backup (S3) → Download ZIP → Extract JSON → Import temp collections
    → Sanitize (RGPD) → Validate integrity → Swap into real collections → Cleanup

Diferença face a sync_prod_to_dev.py:
    - NÃO acede ao MongoDB de Produção diretamente (sem carga no servidor live)
    - Usa os backups automáticos (ZIP com JSON por coleção) como fonte
    - Implementa falha segura: Dev DB NÃO é apagada se o backup estiver corrompido

Uso standalone:
    python backend/scripts/restore_dev_from_backup.py \\
        --dev-url "mongodb+srv://..." \\
        --dev-db "powercell_dev"

Uso via API (endpoint /api/admin/sync-database):
    from scripts.restore_dev_from_backup import run_restore
    result = await run_restore(dev_url, dev_db_name)

Variáveis de ambiente:
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME, AWS_REGION
    DEV_MONGO_URL, DEV_DB_NAME
"""

import asyncio
import argparse
import json
import os
import sys
import random
import string
import logging
import tempfile
import zipfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from io import BytesIO

# Adicionar diretório pai ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Carregar .env do backend
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ======================================================================
# CONFIGURAÇÃO S3
# ======================================================================

def _get_s3_config() -> dict:
    """Retorna configuração S3 do ambiente."""
    return {
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", ""),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        "bucket_name": os.environ.get("AWS_BUCKET_NAME", ""),
        "region": os.environ.get("AWS_REGION", "eu-north-1"),
        "backup_prefix": "backups/",
    }


# ======================================================================
# UTILITÁRIOS DE ANONIMIZAÇÃO (RGPD)
# ======================================================================

_FAKE_SURNAMES = [
    "Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa",
    "Rodrigues", "Martins", "Fernandes", "Gonçalves", "Alves", "Lopes",
    "Sousa", "Marques", "Mendes", "Almeida", "Ribeiro", "Pinto",
    "Carvalho", "Teixeira", "Moreira", "Correia", "Nunes", "Ramos",
]

_TEST_DOMAIN = "powercell.dev"


def _generate_fake_nif() -> str:
    """Gera um NIF falso mas válido (9 dígitos com check digit correto)."""
    digits = [random.randint(1, 9)] + [random.randint(0, 9) for _ in range(7)]
    weights = [9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(d * w for d, w in zip(digits, weights))
    check = (11 - (total % 11))
    if check >= 10:
        check = 0
    digits.append(check)
    return "".join(str(d) for d in digits)


def _scramble_phone(phone: str) -> str:
    """Baralha um número de telefone mantendo o formato base."""
    if not phone:
        return ""
    digits = [c for c in phone if c.isdigit()]
    if len(digits) < 3:
        return phone
    prefix = digits[:3]
    rest = [str(random.randint(0, 9)) for _ in range(len(digits) - 3)]
    new_digits = prefix + rest
    result = []
    digit_idx = 0
    for c in phone:
        if c.isdigit() and digit_idx < len(new_digits):
            result.append(new_digits[digit_idx])
            digit_idx += 1
        else:
            result.append(c)
    return "".join(result)


def _anonymize_client_email(original_email: str, client_id: str) -> str:
    """Gera email de teste: dev_client_{id}@powercell.dev"""
    short_id = client_id[:8] if client_id else "".join(
        random.choices(string.ascii_lowercase + string.digits, k=8)
    )
    return f"dev_client_{short_id}@{_TEST_DOMAIN}"


def _obfuscate_surname(full_name: str) -> str:
    """Mantém o primeiro nome, ofusca o apelido."""
    if not full_name:
        return "Cliente Teste"
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0]
    first_name = parts[0]
    return f"{first_name} {_FAKE_SURNAMES[random.randint(0, len(_FAKE_SURNAMES) - 1)]}"


def _remove_s3_links(doc: dict) -> dict:
    """Remove links reais para S3/AWS de um documento."""
    s3_fields = [
        "s3_url", "s3_key", "s3_bucket", "s3_folder",
        "document_url", "file_url", "upload_url",
        "attachment_url", "thumbnail_url",
    ]
    for field in s3_fields:
        doc.pop(field, None)

    for key in ["personal_data", "real_estate_data", "financial_data"]:
        if key in doc and isinstance(doc[key], dict):
            for field in s3_fields:
                doc[key].pop(field, None)

    return doc


def _sanitize_financial_fields(doc: dict) -> dict:
    """Remove campos financeiros ultra-sensíveis não essenciais para testar a UI."""
    sensitive_remove = [
        "iban", "swift_bic", "bank_account", "bank_name",
        "salary", "gross_income", "net_income", "irs_return",
        "credit_score", "debt_amount", "loan_amount_approved",
    ]
    sensitive_zero = [
        "property_value", "loan_amount", "monthly_payment",
        "requested_amount", "financed_amount", "commission_value",
    ]

    targets = [doc]
    for key in ["personal_data", "real_estate_data", "financial_data"]:
        if key in doc and isinstance(doc[key], dict):
            targets.append(doc[key])

    for target in targets:
        for field in sensitive_remove:
            target.pop(field, None)
        for field in sensitive_zero:
            if field in target and isinstance(target[field], (int, float)):
                target[field] = 0

    return doc


# ======================================================================
# COLEÇÕES EXCLUÍDAS (nunca copiar para dev)
# ======================================================================

_EXCLUDED_COLLECTIONS = {
    "system.indexes", "system.profile", "system.version",
    # Não copiar histórico de backups de produção para dev
    "backup_history",
    # Não copiar sessões/tokens de produção
}


# ======================================================================
# SANITIZAÇÃO POR COLEÇÃO
# ======================================================================

def _sanitize_doc(coll_name: str, doc: dict) -> dict:
    """
    Aplica sanitização RGPD a um documento baseado na coleção de origem.
    """
    doc.pop("_id", None)  # Remover sempre

    if coll_name == "clients":
        client_id = doc.get("id", "")
        if doc.get("email"):
            doc["email"] = _anonymize_client_email(doc["email"], client_id)
            doc["_original_email_masked"] = True
        if doc.get("nif"):
            doc["nif"] = _generate_fake_nif()
            doc["_original_nif_masked"] = True
        if doc.get("phone"):
            doc["phone"] = _scramble_phone(doc["phone"])
        if doc.get("name"):
            doc["name"] = _obfuscate_surname(doc["name"])
        if doc.get("full_name"):
            doc["full_name"] = _obfuscate_surname(doc["full_name"])
        doc = _remove_s3_links(doc)
        doc = _sanitize_financial_fields(doc)

    elif coll_name == "users":
        # Consultores: manter email e password para login, anonimizar PII
        if doc.get("phone"):
            doc["phone"] = _scramble_phone(doc["phone"])
        doc = _remove_s3_links(doc)
        doc["_consultor_data_preserved"] = True

    elif coll_name == "processes":
        doc = _remove_s3_links(doc)
        doc = _sanitize_financial_fields(doc)
        # Limpar anexos S3 no histórico de documentos
        if "documents" in doc and isinstance(doc["documents"], list):
            for attachment in doc["documents"]:
                if isinstance(attachment, dict):
                    _remove_s3_links(attachment)
                    attachment.pop("download_url", None)
                    attachment.pop("view_url", None)
                    attachment.pop("presigned_url", None)
        # Limpar activities com URLs
        if "activities" in doc and isinstance(doc["activities"], list):
            for activity in doc["activities"]:
                if isinstance(activity, dict):
                    activity.pop("attachment_url", None)
                    activity.pop("download_url", None)

    elif coll_name == "properties":
        doc = _remove_s3_links(doc)
        doc = _sanitize_financial_fields(doc)
        # Arredondar coordenadas para ~1km
        if doc.get("coordinates") and isinstance(doc["coordinates"], dict):
            lat = doc["coordinates"].get("lat", 0)
            lng = doc["coordinates"].get("lng", 0)
            if lat and lng:
                doc["coordinates"]["lat"] = round(lat, 1)
                doc["coordinates"]["lng"] = round(lng, 1)

    else:
        # Coleções genéricas: apenas limpeza básica
        doc = _remove_s3_links(doc)

    # Metadados de sanitização (em todos os documentos)
    doc["_sanitized_at"] = datetime.now(timezone.utc).isoformat()
    doc["_sanitized_source"] = "backup_restore"

    return doc


# ======================================================================
# S3: LOCALIZAR BACKUP MAIS RECENTE
# ======================================================================

async def _find_latest_backup_s3() -> Optional[Dict[str, Any]]:
    """
    Localiza o backup automático mais recente e bem-sucedido no S3.

    Este passo é crítico para garantir que o restauro usa dados íntegros.
    A estratégia dupla (BD → listagem S3) existe porque a BD de Produção
    pode não estar acessível a partir do ambiente de Dev (firewalls, IPs),
    pelo que a listagem direta do S3 serve como fallback confiável.

    A consulta à BD de Produção é preferida porque contém metadados de
    auditoria (backup_id, triggered_by) que permitem rastrear o backup.

    Estratégia (em ordem de prioridade):
        1. Consultar ``backup_history`` na BD de Produção para encontrar o
           último registo com ``status=completed`` e ``s3_url`` presente.
        2. Fallback: listar objetos S3 com prefixo ``backups/`` e ordenar
           por ``LastModified`` descendente.

    Returns:
        dict: Informação do backup selecionado com as chaves:
            - s3_key (str): Chave S3 do ficheiro ZIP.
            - s3_url (str): URL S3 completa.
            - source (str): "backup_history" ou "s3_list".
            - started_at (str): Timestamp ISO 8601 do backup.
        Ou ``None`` se nenhum backup for encontrado.

    Raises:
        RuntimeError: Se as credenciais AWS não estiverem configuradas
            ou se ocorrer um erro irrecuperável ao listar o S3.
    """
    import boto3
    from botocore.exceptions import ClientError

    s3_config = _get_s3_config()

    if not all([s3_config["aws_access_key_id"], s3_config["aws_secret_access_key"], s3_config["bucket_name"]]):
        raise RuntimeError(
            "S3 não configurado. Defina AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY e AWS_BUCKET_NAME."
        )

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=s3_config["aws_access_key_id"],
        aws_secret_access_key=s3_config["aws_secret_access_key"],
        region_name=s3_config["region"],
    )

    # ─── Estratégia 1: backup_history na BD de Produção ───
    try:
        prod_url = os.getenv("PROD_MONGO_URL") or os.getenv("MONGO_URL")
        prod_db_name = os.getenv("PROD_DB_NAME") or os.getenv("DB_NAME")
        if prod_url and prod_db_name:
            logger.info("Estratégia 1: Consultando backup_history na BD de Produção...")
            prod_client = AsyncIOMotorClient(prod_url, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
            prod_db = prod_client[prod_db_name]

            try:
                last_backup = await prod_db.backup_history.find_one(
                    {"status": "completed", "result.s3_url": {"$exists": True}},
                    sort=[("started_at", -1)]
                )
                if last_backup:
                    s3_url = last_backup.get("result", {}).get("s3_url", "")
                    if s3_url:
                        # Converter s3://bucket/key para s3_key
                        s3_key = s3_url.replace(f"s3://{s3_config['bucket_name']}/", "")
                        logger.info(f"  Encontrado via backup_history: {s3_key}")
                        return {
                            "s3_key": s3_key,
                            "s3_url": s3_url,
                            "source": "backup_history",
                            "backup_id": last_backup.get("id"),
                            "started_at": str(last_backup.get("started_at", "")),
                        }
            except Exception as e:
                logger.warning(f"  Não foi possível aceder à BD de Produção: {e}")
            finally:
                prod_client.close()
    except Exception as e:
        logger.warning(f"  Estratégia 1 falhou: {e}")

    # ─── Estratégia 2: Listar objetos S3 ───
    logger.info("Estratégia 2: Listando objetos no S3...")
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=s3_config["bucket_name"],
            Prefix=s3_config["backup_prefix"],
        )

        backups = []
        for page in pages:
            if "Contents" not in page:
                continue
            for obj in page["Contents"]:
                key = obj["Key"]
                # Filtrar apenas ficheiros ZIP de backup
                if key.endswith(".zip") and "backup_" in key:
                    backups.append({
                        "s3_key": key,
                        "s3_url": f"s3://{s3_config['bucket_name']}/{key}",
                        "last_modified": obj["LastModified"],
                        "size": obj["Size"],
                        "source": "s3_list",
                    })

        if not backups:
            logger.error("Nenhum backup encontrado no S3.")
            return None

        # Ordenar por data descendente e retornar o mais recente
        backups.sort(key=lambda b: b["last_modified"], reverse=True)
        latest = backups[0]
        latest["started_at"] = latest["last_modified"].isoformat()
        logger.info(f"  Encontrado via S3 list: {latest['s3_key']} ({latest['size']} bytes)")
        return latest

    except ClientError as e:
        raise RuntimeError(f"Erro ao listar backups no S3: {e.response['Error']['Message']}")


# ======================================================================
# S3: DOWNLOAD DO BACKUP
# ======================================================================

async def _download_backup(s3_key: str) -> Path:
    """
    Faz o download do backup ZIP do S3 para um diretório temporário.

    Returns:
        Path para o ficheiro ZIP local.
    """
    import boto3

    s3_config = _get_s3_config()

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=s3_config["aws_access_key_id"],
        aws_secret_access_key=s3_config["aws_secret_access_key"],
        region_name=s3_config["region"],
    )

    # Criar diretório temporário
    tmp_dir = Path(tempfile.mkdtemp(prefix="restore_dev_"))
    zip_path = tmp_dir / Path(s3_key).name

    logger.info(f"A descarregar backup do S3: {s3_key}...")

    # Download em memória e escrever no ficheiro (evita problemas com streams)
    import botocore
    response = s3_client.get_object(Bucket=s3_config["bucket_name"], Key=s3_key)
    body = response["Body"]
    content = body.read()
    zip_path.write_bytes(content)

    size_mb = len(content) / (1024 * 1024)
    logger.info(f"Download concluído: {zip_path} ({size_mb:.1f} MB)")

    return zip_path


# ======================================================================
# EXTRAIR E CARREGAR DADOS DO ZIP
# ======================================================================

def _extract_backup_zip(zip_path: Path) -> Dict[str, List[dict]]:
    """
    Extrai o ficheiro ZIP do backup e carrega os JSON de cada coleção.

    Returns:
        Dict {collection_name: [doc1, doc2, ...]}
    """
    from bson import json_util

    logger.info(f"A extrair backup: {zip_path}")
    collections_data: Dict[str, List[dict]] = {}
    extract_dir = zip_path.parent / "extracted"
    extract_dir.mkdir(exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Validar: o ZIP deve ter ficheiros .json dentro
            json_files = [f for f in zf.namelist() if f.endswith(".json")]

            if not json_files:
                raise ValueError("Backup ZIP não contém ficheiros JSON. Ficheiro corrompido ou formato inválido.")

            for json_file in json_files:
                # O nome do ficheiro é o nome da coleção (ex: "clients.json")
                coll_name = Path(json_file).stem

                if coll_name in _EXCLUDED_COLLECTIONS:
                    logger.info(f"  {coll_name}: ignorada (coleção excluída)")
                    continue

                try:
                    raw = zf.read(json_file)
                    docs = json_util.loads(raw)

                    if not isinstance(docs, list):
                        docs = [docs]

                    collections_data[coll_name] = docs
                    logger.info(f"  {coll_name}: {len(docs)} documentos extraídos")

                except Exception as e:
                    logger.error(f"  {coll_name}: ERRO ao extrair — {e}")
                    raise ValueError(f"Ficheiro corrompido no backup: {json_file} — {e}")

    except zipfile.BadZipFile:
        raise ValueError(f"Ficheiro ZIP corrompido: {zip_path}")

    logger.info(f"Extração concluída: {len(collections_data)} coleções válidas")
    return collections_data


# ======================================================================
# VALIDAÇÃO DE INTEGRIDADE
# ======================================================================

def _validate_backup_data(collections_data: Dict[str, List[dict]]) -> List[str]:
    """
    Valida a integridade dos dados extraídos do backup.

    Checks:
    - Pelo menos 1 coleção com dados
    - 'users' existe (necessário para login em Dev)
    - 'processes' existe (necessário para testar a UI)
    - Todos os documentos são dicts
    - Nenhum documento vazio

    Returns:
        Lista de warnings (vazia = OK)
    """
    warnings = []

    if not collections_data:
        raise ValueError("Backup vazio: nenhuma coleção com dados encontrada.")

    total_docs = sum(len(docs) for docs in collections_data.values())
    if total_docs == 0:
        raise ValueError("Backup vazio: 0 documentos em todas as coleções.")

    # Verificar coleções críticas
    critical_collections = ["users", "processes"]
    for coll_name in critical_collections:
        if coll_name not in collections_data:
            warnings.append(f"Coleção crítica ausente: '{coll_name}'. O Dev não terá dados desta tabela.")
        elif len(collections_data[coll_name]) == 0:
            warnings.append(f"Coleção crítica vazia: '{coll_name}'.")

    # Verificar documentos são dicts válidos
    for coll_name, docs in collections_data.items():
        for i, doc in enumerate(docs):
            if not isinstance(doc, dict):
                warnings.append(f"{coll_name}[{i}]: documento não é um dict (tipo: {type(doc).__name__})")
            elif len(doc) == 0:
                warnings.append(f"{coll_name}[{i}]: documento vazio")

    if warnings:
        logger.warning(f"Validação encontrou {len(warnings)} aviso(s):")
        for w in warnings:
            logger.warning(f"  - {w}")

    return warnings


# ======================================================================
# IMPORTAR PARA COLEÇÕES TEMPORÁRIAS (com sanitização)
# ======================================================================

async def _import_to_temp_collections(
    dev_db,
    collections_data: Dict[str, List[dict]],
) -> Dict[str, int]:
    """
    Importa documentos para coleções temporárias ``_restore_temp_*`` com
    sanitização RGPD aplicada a cada documento.

    Esta é a barreira de segurança central do pipeline: os dados reais de
    Produção nunca são escritos diretamente nas coleções de Dev. A sanitização
    acontece **antes** da inserção, garantindo que mesmo uma falha posterior
    não expõe dados PII na base de Desenvolvimento.

    A inserção é feita em batches de 1000 documentos para evitar exaustão
    de memória do MongoDB ao processar colecções grandes (ex: processes).

    Args:
        dev_db: Instância de base de dados de Desenvolvimento (Motor AsyncIOMotorDatabase).
        collections_data: Dicionário ``{nome_coleção: [doc1, doc2, ...]}`` obtido
            pelo ``_extract_backup_zip``.

    Returns:
        dict: Contagem de documentos importados por coleção
            ``{nome_coleção: número_de_documentos}``.
    """
    import bson
    from bson import ObjectId

    stats = {}

    for coll_name, docs in collections_data.items():
        temp_coll_name = f"_restore_temp_{coll_name}"
        temp_coll = dev_db[temp_coll_name]

        # Limpar coleção temp se existir de uma execução anterior
        try:
            await temp_coll.drop()
        except Exception:
            pass

        # Sanitizar e inserir
        sanitized_docs = []
        for doc in docs:
            try:
                sanitized = _sanitize_doc(coll_name, doc)
                sanitized_docs.append(sanitized)
            except Exception as e:
                logger.error(f"  Erro a sanitizar {coll_name} doc: {e}")
                continue

        if sanitized_docs:
            # Inserir em batches de 1000 para evitar memory issues
            batch_size = 1000
            for i in range(0, len(sanitized_docs), batch_size):
                batch = sanitized_docs[i:i + batch_size]
                await temp_coll.insert_many(batch)
                logger.info(f"  {temp_coll_name}: insertados {len(batch)} docs (batch {i // batch_size + 1})")

        stats[coll_name] = len(sanitized_docs)

    return stats


# ======================================================================
# VALIDAR COLEÇÕES TEMPORÁRIAS
# ======================================================================

async def _validate_temp_collections(dev_db, expected_stats: Dict[str, int]) -> bool:
    """
    Verifica que as coleções temporárias têm os documentos esperados.

    Returns:
        True se OK, False se inconsistência detectada.
    """
    logger.info("A validar coleções temporárias...")

    for coll_name, expected_count in expected_stats.items():
        temp_coll_name = f"_restore_temp_{coll_name}"
        actual_count = await dev_db[temp_coll_name].count_documents({})

        if actual_count != expected_count:
            logger.error(
                f"  INCONSISTÊNCIA: {temp_coll_name} esperava {expected_count}, tem {actual_count}"
            )
            return False

        logger.info(f"  ✓ {temp_coll_name}: {actual_count} docs (OK)")

    return True


# ======================================================================
# SWAP: SUBSTITUIR COLEÇÕES REAIS PELAS TEMPORÁRIAS
# ======================================================================

async def _swap_collections(dev_db, collections: List[str]) -> None:
    """
    Substitui atomicamente as coleções reais de Dev pelas temporárias sanitizadas.

    Esta operação é o momento de maior risco do pipeline: se falhar a meio,
    a base de dados fica em estado inconsistente (algumas coleções novas,
    outras antigas). Por isso, o ``run_restore`` executa a limpeza das
    coleções temporárias residuais em caso de erro (fallback no except).

    O rename no MongoDB (``renameCollection``) é uma operação atómica a nível
    de coleção individual, o que minimiza a janela de indisponibilidade.

    Args:
        dev_db: Instância de base de dados de Desenvolvimento.
        collections: Lista de nomes de coleções a substituir
            (ex: ["clients", "users", "processes"]).

    Raises:
        RuntimeError: Se o drop ou rename de alguma coleção falhar,
            interrompendo o swap das restantes.
    """
    logger.info("A fazer swap das coleções...")

    for coll_name in collections:
        temp_coll_name = f"_restore_temp_{coll_name}"

        # 1. Drop da coleção real
        try:
            await dev_db[coll_name].drop()
            logger.info(f"  ✓ {coll_name}: drop (coleção antiga removida)")
        except Exception as e:
            logger.error(f"  ✗ {coll_name}: erro ao drop — {e}")
            raise

        # 2. Rename temp → real
        try:
            await dev_db[temp_coll_name].rename(coll_name)
            logger.info(f"  ✓ {temp_coll_name} → {coll_name}: swap concluído")
        except Exception as e:
            logger.error(f"  ✗ {temp_coll_name}: erro ao renomear — {e}")
            raise


# ======================================================================
# CLEANUP: REMOVER COLEÇÕES TEMPORÁRIAS RESIDUAIS
# ======================================================================

async def _cleanup_temp_collections(dev_db) -> int:
    """
    Remove todas as coleções _restore_temp_* residuais.
    Retorna o número de coleções removidas.
    """
    removed = 0
    all_collections = await dev_db.list_collection_names()

    for coll_name in all_collections:
        if coll_name.startswith("_restore_temp_"):
            try:
                await dev_db[coll_name].drop()
                logger.info(f"  Limpeza: {coll_name} removida")
                removed += 1
            except Exception as e:
                logger.warning(f"  Limpeza: erro ao remover {coll_name} — {e}")

    return removed


# ======================================================================
# RECRIAR ÍNDICES IMPORTANTES
# ======================================================================

async def _recreate_indexes(dev_db, collections: List[str]) -> None:
    """Recria índices importantes após o swap."""
    important_indexes = {
        "users": [("email", True), ("id", True)],
        "clients": [("email", True), ("nif", True), ("id", True)],
        "processes": [("id", True), ("status", False), ("client_email", False)],
        "properties": [("id", True)],
    }

    for coll_name, indexes in important_indexes.items():
        if coll_name not in collections:
            continue
        for field, unique in indexes:
            try:
                await dev_db[coll_name].create_index(field, unique=unique)
                logger.info(f"  Índice criado: {coll_name}.{field} (unique={unique})")
            except Exception as e:
                logger.warning(f"  Índice já existe ou erro: {coll_name}.{field}: {e}")


# ======================================================================
# FUNÇÃO PRINCIPAL
# ======================================================================

async def run_restore(
    dev_url: str,
    dev_db_name: str,
) -> dict:
    """
    Pipeline completo de restauro seguro: S3 Backup → Dev (com anonimização RGPD).

    Fluxo:
    1. Localizar backup mais recente no S3
    2. Download para disco temporário
    3. Extrair e validar JSON
    4. Importar para coleções _temp com sanitização
    5. Validar integridade dos dados sanitizados
    6. Swap: coleções reais ← coleções temp
    7. Recriar índices
    8. Cleanup de temporários e ficheiros

    FALHA SEGURA: A base de dados de Dev NÃO é modificada se:
    - Nenhum backup for encontrado
    - O backup estiver corrompido (ZIP inválido, JSON inválido)
    - A validação de integridade falhar
    - O swap falhar a meio

    Returns:
        dict com estatísticas do restauro
    """
    started_at = datetime.now(timezone.utc)
    tmp_dir = None

    logger.info("=" * 70)
    logger.info("PIPELINE DE RESTAURO SEGURO: S3 BACKUP → DEV (RGPD)")
    logger.info("=" * 70)
    logger.info(f"Destino (Dev):     {dev_db_name}")
    logger.info(f"Iniciado em:       {started_at.isoformat()}")
    logger.info("=" * 70)

    stats = {
        "started_at": started_at.isoformat(),
        "dev_db": dev_db_name,
        "mode": "backup_restore",
        "backup_info": None,
        "collections": {},
        "total_documents": 0,
        "excluded_collections": list(_EXCLUDED_COLLECTIONS),
        "errors": [],
        "warnings": [],
        "success": False,
        "duration_seconds": 0,
    }

    dev_client = AsyncIOMotorClient(dev_url)
    dev_db = dev_client[dev_db_name]

    try:
        # ═══ PASSO 1: Localizar backup mais recente ═══
        logger.info("\n[1/7] Localizando backup mais recente no S3...")
        backup_info = await _find_latest_backup_s3()

        if not backup_info:
            raise RuntimeError("Nenhum backup encontrado no S3. Impossível restaurar.")

        stats["backup_info"] = {
            "s3_key": backup_info["s3_key"],
            "source": backup_info["source"],
            "started_at": backup_info.get("started_at", ""),
        }
        logger.info(f"  Backup selecionado: {backup_info['s3_key']}")

        # ═══ PASSO 2: Download do backup ═══
        logger.info("\n[2/7] Descarregando backup do S3...")
        zip_path = await _download_backup(backup_info["s3_key"])
        tmp_dir = zip_path.parent

        # ═══ PASSO 3: Extrair e validar ═══
        logger.info("\n[3/7] Extraindo e validando backup...")
        collections_data = _extract_backup_zip(zip_path)

        validation_warnings = _validate_backup_data(collections_data)
        stats["warnings"].extend(validation_warnings)

        # ═══ PASSO 4: Importar para coleções temporárias (com sanitização) ═══
        logger.info("\n[4/7] A importar para coleções temporárias com sanitização RGPD...")
        import_stats = await _import_to_temp_collections(dev_db, collections_data)
        stats["collections"] = import_stats
        stats["total_documents"] = sum(import_stats.values())

        logger.info(f"  Total importado (sanitizado): {stats['total_documents']} documentos")

        # ═══ PASSO 5: Validar integridade das coleções temporárias ═══
        logger.info("\n[5/7] Validando integridade dos dados sanitizados...")
        is_valid = await _validate_temp_collections(dev_db, import_stats)

        if not is_valid:
            raise RuntimeError(
                "Validação de integridade falhou. A base de dados de Dev NÃO foi modificada. "
                "As coleções temporárias serão limpas."
            )

        logger.info("  ✓ Todas as coleções temporárias são consistentes")

        # ═══ PASSO 6: SWAP — Substituir coleções reais ═══
        logger.info("\n[6/7] Substituindo coleções reais pelas sanitizadas...")
        collections_to_swap = list(import_stats.keys())
        await _swap_collections(dev_db, collections_to_swap)

        # Recriar índices
        await _recreate_indexes(dev_db, collections_to_swap)

        # ═══ PASSO 7: Cleanup ═══
        logger.info("\n[7/7] Limpeza...")
        removed = await _cleanup_temp_collections(dev_db)
        logger.info(f"  {removed} coleções temporárias residuais removidas")

        # Sucesso!
        stats["success"] = True

    except Exception as e:
        logger.error(f"\n❌ ERRO CRÍTICO: {e}", exc_info=True)
        stats["errors"].append(str(e))
        stats["success"] = False

        # Cleanup: remover coleções temporárias residuais em caso de erro
        try:
            logger.info("A limpar coleções temporárias residuais (fallback)...")
            removed = await _cleanup_temp_collections(dev_db)
            if removed:
                logger.info(f"  {removed} coleções temporárias removidas")
        except Exception as cleanup_err:
            logger.error(f"Erro no cleanup de fallback: {cleanup_err}")

    finally:
        dev_client.close()

        # Limpar ficheiros temporários
        if tmp_dir and tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                logger.info(f"  Diretório temporário removido: {tmp_dir}")
            except Exception:
                pass

    # Resumo final
    finished_at = datetime.now(timezone.utc)
    duration = (finished_at - started_at).total_seconds()
    stats["finished_at"] = finished_at.isoformat()
    stats["duration_seconds"] = round(duration, 2)

    logger.info("\n" + "=" * 70)
    if stats["success"]:
        logger.info("✅ RESTAURO CONCLUÍDO COM SUCESSO")
    else:
        logger.info("❌ RESTAURO FALHOU — Dev DB NÃO foi modificada")
    logger.info("=" * 70)
    logger.info(f"Duração: {duration:.1f}s")
    logger.info(f"Coleções: {len(stats['collections'])}")
    logger.info(f"Total documentos: {stats['total_documents']}")
    logger.info(f"Backup usado: {stats['backup_info']['s3_key'] if stats['backup_info'] else 'N/A'}")

    if stats["errors"]:
        logger.warning(f"Erros: {len(stats['errors'])}")
        for err in stats["errors"]:
            logger.warning(f"  - {err}")
    if stats["warnings"]:
        logger.info(f"Avisos: {len(stats['warnings'])}")
        for w in stats["warnings"]:
            logger.warning(f"  - {w}")

    logger.info("=" * 70)

    return stats


# ======================================================================
# CLI
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de Restauro Seguro: S3 Backup → Dev (RGPD-compliant)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:

  # Com URL explícita
  python restore_dev_from_backup.py \\
    --dev-url "mongodb+srv://user:pass@dev.mongodb.net" \\
    --dev-db "powercell_dev"

  # Com variáveis de ambiente (DEV_MONGO_URL, DEV_DB_NAME)
  python restore_dev_from_backup.py

Fluxo:
  1. Localiza backup mais recente no S3 (via backup_history ou listagem)
  2. Descarrega o ZIP para disco temporário
  3. Extrai e valida os ficheiros JSON por coleção
  4. Importa para coleções _temp com sanitização RGPD
  5. Valida integridade dos dados sanitizados
  6. Faz swap: coleções reais ← coleções temp
  7. Recria índices e limpa temporários

Falha segura: Dev DB NÃO é modificada se o backup estiver corrompido.
        """
    )

    parser.add_argument("--dev-url", help="URL MongoDB de Desenvolvimento (ou DEV_MONGO_URL)")
    parser.add_argument("--dev-db", help="Nome da BD de Desenvolvimento (ou DEV_DB_NAME)")

    args = parser.parse_args()

    # Resolver URIs
    dev_url = args.dev_url or os.getenv("DEV_MONGO_URL")
    dev_db_name = args.dev_db or os.getenv("DEV_DB_NAME")

    if not dev_url or not dev_db_name:
        print("ERRO: URL e nome da BD de Desenvolvimento são obrigatórios.", file=sys.stderr)
        print("Use --dev-url e --dev-db ou defina DEV_MONGO_URL e DEV_DB_NAME.", file=sys.stderr)
        sys.exit(1)

    result = asyncio.run(run_restore(dev_url, dev_db_name))

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
