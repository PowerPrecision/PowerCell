#!/usr/bin/env python
"""
====================================================================
SCRIPT DE MIGRAÇÃO RGPD - ENCRIPTAÇÃO DE CLIENTES
====================================================================
Encripta dados sensíveis de clientes existentes e gera blind indexes.

CAMPOS ENCRIPTADOS:
- dados_pessoais.nif, documento_id, morada_fiscal, telefone
- contacto.telefone, telefone_secundario
- titular2_data.nif, documento_id, telefone

BLIND INDEXES GERADOS:
- dados_pessoais.nif_hash (para pesquisa de NIF)
- contacto.email_hash (para pesquisa de email)
- contacto.telefone_hash (para pesquisa de telefone)
- titular2_data.nif_hash (para pesquisa de NIF do titular 2)

UTILIZAÇÃO:
    cd backend
    python scripts/migrate_client_encryption.py [--dry-run] [--batch-size 100]

OPÇÕES:
    --dry-run      Simula a migração sem alterar a base de dados
    --batch-size   Número de documentos por lote (default: 100)

AUTOR: PowerCell Security Team
====================================================================
"""

import asyncio
import argparse
import logging
import sys
import re
from datetime import datetime

# Configurar path para imports
sys.path.insert(0, '/home/z/PowerCell/backend')

from database import db
from services.encryption import (
    encryption_service,
    encrypt_client_data,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def is_encrypted(value: str) -> bool:
    """Verifica se um valor já está encriptado."""
    if not value or not isinstance(value, str):
        return False
    return value.startswith("ENC:")


def client_needs_migration(client: dict) -> bool:
    """
    Verifica se um cliente precisa de migração.
    
    Um cliente precisa de migração se:
    - Tem NIF em plain text (não encriptado e sem nif_hash)
    - Tem telefone em plain text (não encriptado e sem telefone_hash)
    - Tem email sem email_hash
    """
    # Verificar dados_pessoais
    dados_pessoais = client.get("dados_pessoais", {})
    if isinstance(dados_pessoais, dict):
        nif = dados_pessoais.get("nif")
        if nif and not is_encrypted(nif) not in ["", None]:
            # Tem NIF em plain text
            if not dados_pessoais.get("nif_hash"):
                return True
    
    # Verificar contacto
    contacto = client.get("contacto", {})
    if isinstance(contacto, dict):
        telefone = contacto.get("telefone")
        if telefone and not is_encrypted(telefone):
            if not contacto.get("telefone_hash"):
                return True
        
        email = contacto.get("email")
        if email and not contacto.get("email_hash"):
            return True
    
    # Verificar titular2_data
    titular2 = client.get("titular2_data", {})
    if isinstance(titular2, dict):
        nif2 = titular2.get("nif")
        if nif2 and not is_encrypted(nif2):
            if not titular2.get("nif_hash"):
                return True
    
    return False


def migrate_client(client: dict) -> dict:
    """
    Migra um documento de cliente:
    - Encripta campos sensíveis
    - Gera blind indexes
    
    Retorna o documento atualizado ou None se não houver alterações.
    """
    if not client:
        return None
    
    result = client.copy()
    has_changes = False
    
    # Processar dados_pessoais
    if "dados_pessoais" in result and isinstance(result["dados_pessoais"], dict):
        dp = result["dados_pessoais"]
        
        # Encriptar e gerar hash para NIF
        nif = dp.get("nif")
        if nif and not is_encrypted(nif):
            # Gerar blind index ANTES de encriptar
            nif_clean = re.sub(r'[^\d]', '', str(nif))
            if len(nif_clean) == 9:
                dp["nif_hash"] = generate_nif_hash(nif_clean)
                logger.debug(f"  NIF hash gerado para {nif_clean[:3]}***")
            
            # Encriptar
            if encryption_service.is_available():
                dp["nif"] = encryption_service.encrypt(str(nif))
                has_changes = True
        
        # Encriptar documento_id
        doc_id = dp.get("documento_id")
        if doc_id and not is_encrypted(doc_id) and encryption_service.is_available():
            dp["documento_id"] = encryption_service.encrypt(str(doc_id))
            has_changes = True
        
        # Encriptar morada_fiscal
        morada = dp.get("morada_fiscal")
        if morada and not is_encrypted(morada) and encryption_service.is_available():
            dp["morada_fiscal"] = encryption_service.encrypt(str(morada))
            has_changes = True
        
        # Encriptar telefone/phone
        for field in ["telefone", "phone"]:
            val = dp.get(field)
            if val and not is_encrypted(val) and encryption_service.is_available():
                dp[field] = encryption_service.encrypt(str(val))
                has_changes = True
    
    # Processar contacto
    if "contacto" in result and isinstance(result["contacto"], dict):
        ct = result["contacto"]
        
        # Gerar hash para email (email NÃO é encriptado, apenas hash para pesquisa)
        email = ct.get("email")
        if email and not ct.get("email_hash"):
            ct["email_hash"] = generate_email_hash(email)
            has_changes = True
            logger.debug(f"  Email hash gerado para {email[:3]}***")
        
        # Encriptar e gerar hash para telefone
        telefone = ct.get("telefone")
        if telefone and not is_encrypted(telefone):
            # Gerar blind index
            telefone_clean = re.sub(r'[^\d]', '', str(telefone))
            if len(telefone_clean) >= 9:
                ct["telefone_hash"] = generate_telefone_hash(telefone_clean)
                logger.debug(f"  Telefone hash gerado para {telefone_clean[:3]}***")
            
            # Encriptar
            if encryption_service.is_available():
                ct["telefone"] = encryption_service.encrypt(str(telefone))
                has_changes = True
        
        # Encriptar telefone_secundario
        tel_sec = ct.get("telefone_secundario")
        if tel_sec and not is_encrypted(tel_sec) and encryption_service.is_available():
            ct["telefone_secundario"] = encryption_service.encrypt(str(tel_sec))
            has_changes = True
    
    # Processar titular2_data
    if "titular2_data" in result and isinstance(result["titular2_data"], dict):
        t2 = result["titular2_data"]
        
        # Encriptar e gerar hash para NIF do titular 2
        nif2 = t2.get("nif")
        if nif2 and not is_encrypted(nif2):
            nif2_clean = re.sub(r'[^\d]', '', str(nif2))
            if len(nif2_clean) == 9:
                t2["nif_hash"] = generate_nif_hash(nif2_clean)
                logger.debug(f"  NIF titular2 hash gerado para {nif2_clean[:3]}***")
            
            if encryption_service.is_available():
                t2["nif"] = encryption_service.encrypt(str(nif2))
                has_changes = True
        
        # Encriptar outros campos sensíveis
        for field in ["documento_id", "telefone", "phone"]:
            val = t2.get(field)
            if val and not is_encrypted(val) and encryption_service.is_available():
                t2[field] = encryption_service.encrypt(str(val))
                has_changes = True
    
    # Encriptar campo nif no nível raiz (compatibilidade)
    if "nif" in result and result["nif"] and not is_encrypted(result["nif"]):
        if encryption_service.is_available():
            result["nif"] = encryption_service.encrypt(str(result["nif"]))
            has_changes = True
    
    return result if has_changes else None


async def run_migration(dry_run: bool = False, batch_size: int = 100):
    """
    Executa a migração de encriptação de clientes.
    
    Args:
        dry_run: Se True, apenas simula sem alterar a BD
        batch_size: Número de documentos por lote
    """
    logger.info("=" * 60)
    logger.info("MIGRAÇÃO RGPD - ENCRIPTAÇÃO DE CLIENTES")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("🔴 MODO DRY-RUN - Nenhuma alteração será feita")
    else:
        logger.info("🟢 MODO PRODUÇÃO - Dados serão alterados")
    
    # Verificar se encriptação está disponível
    if not encryption_service.is_available():
        logger.warning("⚠️  Serviço de encriptação NÃO disponível!")
        logger.warning("   Apenas blind indexes serão gerados.")
    else:
        logger.info("✅ Serviço de encriptação disponível")
    
    # Contar clientes
    total_clients = await db.clients.count_documents({})
    logger.info(f"📊 Total de clientes na BD: {total_clients}")
    
    # Contar clientes que precisam de migração
    cursor = db.clients.find({}, {"_id": 1, "id": 1, "nome": 1, "dados_pessoais": 1, "contacto": 1, "titular2_data": 1})
    
    clients_to_migrate = []
    async for client in cursor:
        if client_needs_migration(client):
            clients_to_migrate.append(client)
    
    logger.info(f"📊 Clientes que precisam de migração: {len(clients_to_migrate)}")
    
    if not clients_to_migrate:
        logger.info("✅ Todos os clientes já estão migrados!")
        return
    
    # Processar em lotes
    migrated_count = 0
    error_count = 0
    skipped_count = 0
    
    for i in range(0, len(clients_to_migrate), batch_size):
        batch = clients_to_migrate[i:i + batch_size]
        logger.info(f"\n📦 Processando lote {i//batch_size + 1} ({len(batch)} clientes)...")
        
        for client in batch:
            client_id = client.get("id")
            client_name = client.get("nome", "Sem nome")
            
            try:
                migrated = migrate_client(client)
                
                if migrated:
                    if dry_run:
                        logger.info(f"  [DRY-RUN] Migraria: {client_id} - {client_name}")
                        migrated_count += 1
                    else:
                        # Actualizar na base de dados
                        update_result = await db.clients.update_one(
                            {"id": client_id},
                            {"$set": migrated}
                        )
                        
                        if update_result.modified_count > 0:
                            logger.info(f"  ✅ Migrado: {client_id} - {client_name}")
                            migrated_count += 1
                        else:
                            logger.warning(f"  ⚠️  Sem alterações: {client_id} - {client_name}")
                            skipped_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                logger.error(f"  ❌ Erro ao migrar {client_id}: {e}")
                error_count += 1
        
        # Pequena pausa entre lotes
        if not dry_run and i + batch_size < len(clients_to_migrate):
            await asyncio.sleep(0.5)
    
    # Resumo final
    logger.info("\n" + "=" * 60)
    logger.info("RESUMO DA MIGRAÇÃO")
    logger.info("=" * 60)
    logger.info(f"Total de clientes:        {total_clients}")
    logger.info(f"Clientes elegíveis:       {len(clients_to_migrate)}")
    logger.info(f"✅ Migrados com sucesso:  {migrated_count}")
    logger.info(f"⏭️  Ignorados (sem alterações): {skipped_count}")
    logger.info(f"❌ Erros:                 {error_count}")
    
    if dry_run:
        logger.info("\n🔴 MODO DRY-RUN - Execute sem --dry-run para aplicar alterações")
    else:
        logger.info("\n✅ MIGRAÇÃO CONCLUÍDA!")


async def verify_migration():
    """
    Verifica o estado da migração após execução.
    """
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICAÇÃO PÓS-MIGRAÇÃO")
    logger.info("=" * 60)
    
    # Contar clientes com blind indexes
    with_nif_hash = await db.clients.count_documents({"dados_pessoais.nif_hash": {"$exists": True}})
    with_email_hash = await db.clients.count_documents({"contacto.email_hash": {"$exists": True}})
    with_telefone_hash = await db.clients.count_documents({"contacto.telefone_hash": {"$exists": True}})
    
    # Contar clientes com NIF encriptado
    with_encrypted_nif = await db.clients.count_documents({"dados_pessoais.nif": {"$regex": "^ENC:"}})
    
    # Contar clientes com NIF em plain text
    with_plain_nif = await db.clients.count_documents({
        "dados_pessoais.nif": {"$exists": True, "$ne": None, "$not": {"$regex": "^ENC:"}}
    })
    
    total = await db.clients.count_documents({})
    
    logger.info(f"Total de clientes:               {total}")
    logger.info(f"Com nif_hash:                    {with_nif_hash} ({with_nif_hash/total*100:.1f}%)" if total > 0 else "")
    logger.info(f"Com email_hash:                  {with_email_hash} ({with_email_hash/total*100:.1f}%)" if total > 0 else "")
    logger.info(f"Com telefone_hash:               {with_telefone_hash} ({with_telefone_hash/total*100:.1f}%)" if total > 0 else "")
    logger.info(f"Com NIF encriptado:              {with_encrypted_nif} ({with_encrypted_nif/total*100:.1f}%)" if total > 0 else "")
    logger.info(f"⚠️  Com NIF em plain text:        {with_plain_nif} ({with_plain_nif/total*100:.1f}%)" if total > 0 else "")


def main():
    parser = argparse.ArgumentParser(
        description="Migração RGPD - Encriptação de dados de clientes"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula a migração sem alterar a base de dados"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Número de documentos por lote (default: 100)"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Apenas verifica o estado atual sem migrar"
    )
    
    args = parser.parse_args()
    
    if args.verify_only:
        asyncio.run(verify_migration())
    else:
        asyncio.run(run_migration(dry_run=args.dry_run, batch_size=args.batch_size))
        if not args.dry_run:
            asyncio.run(verify_migration())


if __name__ == "__main__":
    main()
