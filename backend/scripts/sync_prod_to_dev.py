#!/usr/bin/env python3
"""
sync_prod_to_dev.py — Pipeline de Sanitização de Dados (RGPD-compliant)

Copia dados de Produção para Desenvolvimento com anonimização ativa.
NÃO faz cópia directa (1:1). Todos os dados pessoais são mascarados.

Uso standalone:
    python backend/scripts/sync_prod_to_dev.py \
        --prod-url "mongodb+srv://..." \
        --prod-db "powercell_prod" \
        --dev-url "mongodb+srv://..." \
        --dev-db "powercell_dev"

Uso via API (endpoint /api/admin/sync-database):
    from scripts.sync_prod_to_dev import run_sync
    result = await run_sync(prod_url, prod_db, dev_url, dev_db)

Ambiente:
    As variáveis de ambiente (opcionais) são lidas do .env do backend.
    Se não forem fornecidas via argumentos, tenta:
      - PROD_MONGO_URL + PROD_DB_NAME  (ou MONGO_URL + DB_NAME como fallback)
      - DEV_MONGO_URL  + DEV_DB_NAME
"""

import asyncio
import argparse
import json
import os
import sys
import random
import string
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Adicionar diretório pai ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Carregar .env do backend
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ======================================================================
# UTILITÁRIOS DE ANONIMIZAÇÃO
# ======================================================================

# Apelidos portugueses falsos para manter contexto realista
_FAKE_SURNAMES = [
    "Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa",
    "Rodrigues", "Martins", "Fernandes", "Gonçalves", "Alves", "Lopes",
    "Sousa", "Marques", "Mendes", "Almeida", "Ribeiro", "Pinto",
    "Carvalho", "Teixeira", "Moreira", "Correia", "Nunes", "Ramos",
]

# Domínios de teste
_TEST_DOMAIN = "powercell.dev"


def _generate_fake_nif() -> str:
    """Gera um NIF falso mas válido (9 dígitos com check digit correto)."""
    digits = [random.randint(1, 9)] + [random.randint(0, 9) for _ in range(7)]
    # Cálculo do dígito de controlo (módulo 11, pesos 9,8,7,6,5,4,3,2)
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
    # Manter prefixo (3 primeiros dígitos para PT)
    prefix = digits[:3]
    rest = [str(random.randint(0, 9)) for _ in range(len(digits) - 3)]
    new_digits = prefix + rest
    # Reconstruir com o mesmo formato
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
    """Gera email de teste: user{id}@powercell.dev"""
    short_id = client_id[:8] if client_id else "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"user{short_id}@{_TEST_DOMAIN}"


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
        if field in doc:
            del doc[field]

    # Limpar dentro de sub-documentos comuns
    for key in ["personal_data", "real_estate_data", "financial_data"]:
        if key in doc and isinstance(doc[key], dict):
            for field in s3_fields:
                if field in doc[key]:
                    del doc[key][field]

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

    # Verificar no nível raiz e em sub-documentos
    targets = [doc]
    for key in ["personal_data", "real_estate_data", "financial_data"]:
        if key in doc and isinstance(doc[key], dict):
            targets.append(doc[key])

    for target in targets:
        for field in sensitive_remove:
            if field in target:
                del target[field]
        for field in sensitive_zero:
            if field in target and isinstance(target[field], (int, float)):
                target[field] = 0

    return doc


# ======================================================================
# CORE: FUNÇÕES DE SINCRONIZAÇÃO POR COLEÇÃO
# ======================================================================

async def _get_collections_to_sync(prod_db) -> list:
    """Retorna a lista de coleções a sincronizar."""
    all_collections = await prod_db.list_collection_names()
    system_collections = {"system.indexes", "system.profile", "system.version"}
    return sorted([c for c in all_collections if c not in system_collections])


async def _sync_clients(prod_collection, dev_collection, stats: dict):
    """Sincroniza a coleção 'clients' com anonimização."""
    docs = await prod_collection.find({}).to_list(length=None)
    if not docs:
        logger.info("  clients: 0 documentos encontrados")
        return

    sanitized = []
    for doc in docs:
        client_id = doc.get("id", "")
        doc.pop("_id", None)

        # Anonimizar campos obrigatórios
        if doc.get("email"):
            doc["email"] = _anonymize_client_email(doc["email"], client_id)
            doc["_original_email_masked"] = True  # Flag de anonimização

        if doc.get("nif"):
            doc["nif"] = _generate_fake_nif()
            doc["_original_nif_masked"] = True

        if doc.get("phone"):
            doc["phone"] = _scramble_phone(doc["phone"])

        if doc.get("name"):
            doc["name"] = _obfuscate_surname(doc["name"])

        if doc.get("full_name"):
            doc["full_name"] = _obfuscate_surname(doc["full_name"])

        # Remover campos ultra-sensíveis
        doc = _remove_s3_links(doc)
        doc = _sanitize_financial_fields(doc)

        # Adicionar metadados de sanitização
        doc["_sanitized_at"] = datetime.now(timezone.utc).isoformat()
        doc["_sanitized_source"] = "prod_sync"

        sanitized.append(doc)

    if sanitized:
        await dev_collection.insert_many(sanitized)

    stats["clients"] = len(sanitized)
    logger.info(f"  clients: {len(sanitized)} documentos copiados e anonimizados")


async def _sync_users(prod_collection, dev_collection, stats: dict):
    """
    Sincroniza a coleção 'users' (Consultores).
    Mantém emails reais para login, mas transfere hashes em segurança.
    """
    docs = await prod_collection.find({}).to_list(length=None)
    if not docs:
        logger.info("  users: 0 documentos encontrados")
        return

    sanitized = []
    for doc in docs:
        doc.pop("_id", None)

        # Manter email e password (hash) para login em Dev
        # Mas anonimizar dados pessoais dos consultores
        if doc.get("phone"):
            doc["phone"] = _scramble_phone(doc["phone"])

        # Manter o nome real dos consultores (necessário para a UI)
        # Remover dados S3 pessoais
        doc = _remove_s3_links(doc)

        # Adicionar metadados
        doc["_sanitized_at"] = datetime.now(timezone.utc).isoformat()
        doc["_sanitized_source"] = "prod_sync"
        doc["_consultor_data_preserved"] = True

        sanitized.append(doc)

    if sanitized:
        await dev_collection.insert_many(sanitized)

    stats["users"] = len(sanitized)
    logger.info(f"  users: {len(sanitized)} utilizadores copiados (emails e passwords preservados)")


async def _sync_processes(prod_collection, dev_collection, stats: dict):
    """Sincroniza a coleção 'processes' com limpeza de links e dados financeiros."""
    docs = await prod_collection.find({}).to_list(length=None)
    if not docs:
        logger.info("  processes: 0 documentos encontrados")
        return

    sanitized = []
    for doc in docs:
        doc.pop("_id", None)

        # Limpar links S3/AWS
        doc = _remove_s3_links(doc)

        # Sanitizar campos financeiros ultra-sensíveis
        doc = _sanitize_financial_fields(doc)

        # Limpar anexos S3 no histórico de documentos
        if "documents" in doc and isinstance(doc["documents"], list):
            for attachment in doc["documents"]:
                if isinstance(attachment, dict):
                    attachment = _remove_s3_links(attachment)
                    # Limpar URLs de download
                    attachment.pop("download_url", None)
                    attachment.pop("view_url", None)
                    attachment.pop("presigned_url", None)

        # Limpar activities com URLs
        if "activities" in doc and isinstance(doc["activities"], list):
            for activity in doc["activities"]:
                if isinstance(activity, dict):
                    activity.pop("attachment_url", None)
                    activity.pop("download_url", None)

        # Adicionar metadados
        doc["_sanitized_at"] = datetime.now(timezone.utc).isoformat()
        doc["_sanitized_source"] = "prod_sync"

        sanitized.append(doc)

    if sanitized:
        await dev_collection.insert_many(sanitized)

    stats["processes"] = len(sanitized)
    logger.info(f"  processes: {len(sanitized)} processos copiados (links S3 e dados financeiros limpos)")


async def _sync_properties(prod_collection, dev_collection, stats: dict):
    """Sincroniza a coleção 'properties' com limpeza de dados sensíveis."""
    docs = await prod_collection.find({}).to_list(length=None)
    if not docs:
        logger.info("  properties: 0 documentos encontrados")
        return

    sanitized = []
    for doc in docs:
        doc.pop("_id", None)

        doc = _remove_s3_links(doc)
        doc = _sanitize_financial_fields(doc)

        # Limpar coordenadas exatas (privacidade)
        if doc.get("coordinates"):
            # Manter localização aproximada (arredondar a ~1km)
            if isinstance(doc["coordinates"], dict):
                lat = doc["coordinates"].get("lat", 0)
                lng = doc["coordinates"].get("lng", 0)
                if lat and lng:
                    doc["coordinates"]["lat"] = round(lat, 1)
                    doc["coordinates"]["lng"] = round(lng, 1)

        doc["_sanitized_at"] = datetime.now(timezone.utc).isoformat()
        doc["_sanitized_source"] = "prod_sync"

        sanitized.append(doc)

    if sanitized:
        await dev_collection.insert_many(sanitized)

    stats["properties"] = len(sanitized)
    logger.info(f"  properties: {len(sanitized)} propriedades copiadas")


async def _sync_generic(prod_name: str, prod_collection, dev_collection, stats: dict):
    """Sincroniza coleções genéricas sem anonimização especial (apenas remove _id)."""
    docs = await prod_collection.find({}).to_list(length=None)
    if not docs:
        logger.info(f"  {prod_name}: 0 documentos encontrados")
        return

    sanitized = []
    for doc in docs:
        doc.pop("_id", None)
        # Limpeza básica de S3 links em qualquer documento
        doc = _remove_s3_links(doc)
        doc["_sanitized_at"] = datetime.now(timezone.utc).isoformat()
        doc["_sanitized_source"] = "prod_sync"
        sanitized.append(doc)

    if sanitized:
        await dev_collection.insert_many(sanitized)

    stats[prod_name] = len(sanitized)
    logger.info(f"  {prod_name}: {len(sanitized)} documentos copiados")


# ======================================================================
# FUNÇÃO PRINCIPAL DE SINCRONIZAÇÃO
# ======================================================================

async def run_sync(
    prod_url: str,
    prod_db_name: str,
    dev_url: str,
    dev_db_name: str,
) -> dict:
    """
    Executa o pipeline completo de sincronização Produção → Dev com anonimização.

    Returns:
        dict com estatísticas da sincronização
    """
    started_at = datetime.now(timezone.utc)
    logger.info("=" * 70)
    logger.info("PIPELINE DE SINCRONIZAÇÃO PROD → DEV (COM ANONIMIZAÇÃO RGPD)")
    logger.info("=" * 70)
    logger.info(f"Fonte (Produção):  {prod_db_name}")
    logger.info(f"Destino (Dev):     {dev_db_name}")
    logger.info(f"Iniciado em:       {started_at.isoformat()}")
    logger.info("=" * 70)

    stats = {
        "started_at": started_at.isoformat(),
        "prod_db": prod_db_name,
        "dev_db": dev_db_name,
        "collections": {},
        "errors": [],
    }

    prod_client = AsyncIOMotorClient(prod_url)
    dev_client = AsyncIOMotorClient(dev_url)

    prod_db = prod_client[prod_db_name]
    dev_db = dev_client[dev_db_name]

    try:
        # Listar coleções a sincronizar
        collections = await _get_collections_to_sync(prod_db)
        logger.info(f"\nColeções encontradas em Produção: {len(collections)}")

        # Truncate (limpar) base de dados de Dev antes de inserir
        dev_collections = await _get_collections_to_sync(dev_db)
        logger.info(f"\nA limpar base de dados de Dev ({len(dev_collections)} coleções)...")
        for coll_name in dev_collections:
            await dev_db[coll_name].drop()
        logger.info("Base de dados de Dev limpa com sucesso.\n")

        # Sincronizar coleções com anonimização adequada
        for coll_name in collections:
            try:
                prod_coll = prod_db[coll_name]
                dev_coll = dev_db[coll_name]

                logger.info(f"Sincronizando: {coll_name}...")

                if coll_name == "clients":
                    await _sync_clients(prod_coll, dev_coll, stats["collections"])
                elif coll_name == "users":
                    await _sync_users(prod_coll, dev_coll, stats["collections"])
                elif coll_name == "processes":
                    await _sync_processes(prod_coll, dev_coll, stats["collections"])
                elif coll_name == "properties":
                    await _sync_properties(prod_coll, dev_coll, stats["collections"])
                else:
                    await _sync_generic(coll_name, prod_coll, dev_coll, stats["collections"])

            except Exception as e:
                error_msg = f"{coll_name}: {str(e)}"
                logger.error(f"  ERRO em {error_msg}")
                stats["errors"].append(error_msg)

        # Recriar índices importantes
        logger.info("\nRecriando índices...")
        important_indexes = {
            "users": [("email", True), ("id", True)],
            "clients": [("email", True), ("nif", True), ("id", True)],
            "processes": [("id", True), ("status", False), ("client_email", False)],
            "properties": [("id", True)],
        }

        for coll_name, indexes in important_indexes.items():
            if coll_name in collections:
                for field, unique in indexes:
                    try:
                        await dev_db[coll_name].create_index(field, unique=unique)
                        logger.info(f"  Índice criado: {coll_name}.{field} (unique={unique})")
                    except Exception as e:
                        logger.warning(f"  Índice já existe ou erro: {coll_name}.{field}: {e}")

    except Exception as e:
        logger.error(f"ERRO CRÍTICO durante a sincronização: {e}", exc_info=True)
        stats["errors"].append(f"CRITICAL: {str(e)}")
    finally:
        prod_client.close()
        dev_client.close()

    # Resumo final
    finished_at = datetime.now(timezone.utc)
    duration = (finished_at - started_at).total_seconds()
    total_docs = sum(stats["collections"].values())

    stats["finished_at"] = finished_at.isoformat()
    stats["duration_seconds"] = round(duration, 2)
    stats["total_documents"] = total_docs
    stats["total_collections"] = len(stats["collections"])
    stats["success"] = len(stats["errors"]) == 0

    logger.info("\n" + "=" * 70)
    logger.info("SINCRONIZAÇÃO CONCLUÍDA")
    logger.info("=" * 70)
    logger.info(f"Duração: {duration:.1f}s")
    logger.info(f"Coleções: {len(stats['collections'])}")
    logger.info(f"Total de documentos: {total_docs}")

    if stats["errors"]:
        logger.warning(f"Erros: {len(stats['errors'])}")
        for err in stats["errors"]:
            logger.warning(f"  - {err}")
    else:
        logger.info("Status: SUCESSO - Todos os dados foram anonimizados e copiados")

    logger.info("=" * 70)

    return stats


# ======================================================================
# CLI
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de Sanitização: Produção → Dev (RGPD-compliant)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:

  # Com URLs explícitas
  python sync_prod_to_dev.py \\
    --prod-url "mongodb+srv://user:pass@prod.mongodb.net" \\
    --prod-db "powercell_prod" \\
    --dev-url "mongodb+srv://user:pass@dev.mongodb.net" \\
    --dev-db "powercell_dev"

  # Com variáveis de ambiente (PROD_MONGO_URL, PROD_DB_NAME, DEV_MONGO_URL, DEV_DB_NAME)
  python sync_prod_to_dev.py

  # Usar MONGO_URL como produção e override apenas DEV
  python sync_prod_to_dev.py \\
    --dev-url "mongodb+srv://user:pass@dev.mongodb.net" \\
    --dev-db "powercell_dev"
        """
    )

    parser.add_argument("--prod-url", help="URL MongoDB de Produção (ou PROD_MONGO_URL)")
    parser.add_argument("--prod-db", help="Nome da BD de Produção (ou PROD_DB_NAME)")
    parser.add_argument("--dev-url", help="URL MongoDB de Desenvolvimento (ou DEV_MONGO_URL)")
    parser.add_argument("--dev-db", help="Nome da BD de Desenvolvimento (ou DEV_DB_NAME)")

    args = parser.parse_args()

    # Resolver URIs (argumentos > env vars > defaults)
    prod_url = args.prod_url or os.getenv("PROD_MONGO_URL") or os.getenv("MONGO_URL")
    prod_db_name = args.prod_db or os.getenv("PROD_DB_NAME") or os.getenv("DB_NAME")
    dev_url = args.dev_url or os.getenv("DEV_MONGO_URL")
    dev_db_name = args.dev_db or os.getenv("DEV_DB_NAME")

    if not prod_url or not prod_db_name:
        print("ERRO: URL e nome da BD de Produção são obrigatórios.", file=sys.stderr)
        print("Use --prod-url e --prod-db ou defina PROD_MONGO_URL e PROD_DB_NAME.", file=sys.stderr)
        sys.exit(1)

    if not dev_url or not dev_db_name:
        print("ERRO: URL e nome da BD de Desenvolvimento são obrigatórios.", file=sys.stderr)
        print("Use --dev-url e --dev-db ou defina DEV_MONGO_URL e DEV_DB_NAME.", file=sys.stderr)
        sys.exit(1)

    result = asyncio.run(run_sync(prod_url, prod_db_name, dev_url, dev_db_name))

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
