"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - MIGRAÇÃO RGPD
====================================================================
Endpoints para executar migrações de encriptação de dados.

ACESSO: Apenas Admin, CEO ou Diretor
====================================================================
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Optional

from database import db
from services.auth import get_current_user, require_roles
from models.auth import UserRole
from services.encryption import (
    encryption_service,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)
from services.system_error_logger import system_error_logger

router = APIRouter(prefix="/admin/migration", tags=["Admin Migration"])
logger = logging.getLogger(__name__)


def is_encrypted(value: str) -> bool:
    """Verifica se um valor já está encriptado."""
    if not value or not isinstance(value, str):
        return False
    return value.startswith("ENC:")


async def run_migration_task():
    """
    Tarefa em background para executar a migração.
    """
    import re
    
    logger.info("=" * 60)
    logger.info("INICIANDO MIGRAÇÃO RGPD DE CLIENTES")
    logger.info("=" * 60)
    
    try:
        # Buscar todos os clientes
        cursor = db.clients.find({}, {
            "_id": 1, "id": 1, "nome": 1, 
            "dados_pessoais": 1, "contacto": 1, "titular2_data": 1
        })
        
        clients = await cursor.to_list(length=10000)
        migrated_count = 0
        error_count = 0
        
        for client in clients:
            client_id = client.get("id")
            has_changes = False
            updates = {}
            
            try:
                # Processar dados_pessoais
                dados_pessoais = client.get("dados_pessoais", {})
                if isinstance(dados_pessoais, dict):
                    dp_updates = {}
                    
                    # NIF
                    nif = dados_pessoais.get("nif")
                    if nif and not is_encrypted(nif):
                        nif_clean = re.sub(r'[^\d]', '', str(nif))
                        if len(nif_clean) == 9:
                            dp_updates["nif_hash"] = generate_nif_hash(nif_clean)
                        if encryption_service.is_available():
                            dp_updates["nif"] = encryption_service.encrypt(str(nif))
                    
                    # documento_id
                    doc_id = dados_pessoais.get("documento_id")
                    if doc_id and not is_encrypted(doc_id) and encryption_service.is_available():
                        dp_updates["documento_id"] = encryption_service.encrypt(str(doc_id))
                    
                    # morada_fiscal
                    morada = dados_pessoais.get("morada_fiscal")
                    if morada and not is_encrypted(morada) and encryption_service.is_available():
                        dp_updates["morada_fiscal"] = encryption_service.encrypt(str(morada))
                    
                    if dp_updates:
                        updates["dados_pessoais"] = {**dados_pessoais, **dp_updates}
                        has_changes = True
                
                # Processar contacto
                contacto = client.get("contacto", {})
                if isinstance(contacto, dict):
                    ct_updates = {}
                    
                    # Email hash (email não é encriptado, apenas hash)
                    email = contacto.get("email")
                    if email and not contacto.get("email_hash"):
                        ct_updates["email_hash"] = generate_email_hash(email)
                    
                    # Telefone
                    telefone = contacto.get("telefone")
                    if telefone and not is_encrypted(telefone):
                        telefone_clean = re.sub(r'[^\d]', '', str(telefone))
                        if len(telefone_clean) >= 9:
                            ct_updates["telefone_hash"] = generate_telefone_hash(telefone_clean)
                        if encryption_service.is_available():
                            ct_updates["telefone"] = encryption_service.encrypt(str(telefone))
                    
                    # Telefone secundário
                    tel_sec = contacto.get("telefone_secundario")
                    if tel_sec and not is_encrypted(tel_sec) and encryption_service.is_available():
                        ct_updates["telefone_secundario"] = encryption_service.encrypt(str(tel_sec))
                    
                    if ct_updates:
                        updates["contacto"] = {**contacto, **ct_updates}
                        has_changes = True
                
                # Processar titular2_data
                titular2 = client.get("titular2_data", {})
                if isinstance(titular2, dict) and titular2:
                    t2_updates = {}
                    
                    nif2 = titular2.get("nif")
                    if nif2 and not is_encrypted(nif2):
                        nif2_clean = re.sub(r'[^\d]', '', str(nif2))
                        if len(nif2_clean) == 9:
                            t2_updates["nif_hash"] = generate_nif_hash(nif2_clean)
                        if encryption_service.is_available():
                            t2_updates["nif"] = encryption_service.encrypt(str(nif2))
                    
                    if t2_updates:
                        updates["titular2_data"] = {**titular2, **t2_updates}
                        has_changes = True
                
                # Actualizar cliente se houver alterações
                if has_changes and updates:
                    await db.clients.update_one(
                        {"id": client_id},
                        {"$set": updates}
                    )
                    migrated_count += 1
                    logger.info(f"Migrado: {client_id} - {client.get('nome', 'Sem nome')}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Erro ao migrar {client_id}: {e}")
        
        # Registar sucesso
        await system_error_logger.log_error(
            error_type="migration_complete",
            message=f"Migração RGPD concluída: {migrated_count} clientes migrados, {error_count} erros",
            component="admin_migration",
            details={"migrated": migrated_count, "errors": error_count},
            severity="info",
            request_path="/api/admin/migration/run"
        )
        
        logger.info(f"MIGRAÇÃO CONCLUÍDA: {migrated_count} migrados, {error_count} erros")
        
    except Exception as e:
        logger.error(f"Erro na migração: {e}")
        await system_error_logger.log_error(
            error_type="migration_error",
            message=f"Erro na migração RGPD: {e}",
            component="admin_migration",
            details={"error": str(e)},
            severity="error",
            request_path="/api/admin/migration/run"
        )


@router.get("/status")
async def get_migration_status(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Verifica o estado atual da migração de encriptação.
    
    Retorna estatísticas sobre:
    - Total de clientes
    - Clientes com NIF encriptado
    - Clientes com blind indexes gerados
    - Clientes que ainda precisam de migração
    """
    # Contagens
    total_clients = await db.clients.count_documents({})
    
    with_nif_hash = await db.clients.count_documents({"dados_pessoais.nif_hash": {"$exists": True}})
    with_email_hash = await db.clients.count_documents({"contacto.email_hash": {"$exists": True}})
    with_telefone_hash = await db.clients.count_documents({"contacto.telefone_hash": {"$exists": True}})
    
    with_encrypted_nif = await db.clients.count_documents({"dados_pessoais.nif": {"$regex": "^ENC:"}})
    with_plain_nif = await db.clients.count_documents({
        "dados_pessoais.nif": {"$exists": True, "$ne": None, "$not": {"$regex": "^ENC:"}}
    })
    
    with_encrypted_telefone = await db.clients.count_documents({"contacto.telefone": {"$regex": "^ENC:"}})
    
    encryption_available = encryption_service.is_available()
    
    # Calcular percentagens
    def pct(count, total):
        """Calcula a percentagem arredondada de count/total.

        Usado para gerar estatísticas de migração no formato legível.
        Retorna 0 se total for 0 para evitar divisão por zero.

        Args:
            count: Numerador (quantidade observada).
            total: Denominador (quantidade total).

        Returns:
            float: Percentagem arredondada a 1 casa decimal.
        """
        return round(count / total * 100, 1) if total > 0 else 0
    
    return {
        "encryption_service_available": encryption_available,
        "total_clients": total_clients,
        "blind_indexes": {
            "nif_hash": {
                "count": with_nif_hash,
                "percentage": pct(with_nif_hash, total_clients)
            },
            "email_hash": {
                "count": with_email_hash,
                "percentage": pct(with_email_hash, total_clients)
            },
            "telefone_hash": {
                "count": with_telefone_hash,
                "percentage": pct(with_telefone_hash, total_clients)
            }
        },
        "encryption_status": {
            "nif_encrypted": {
                "count": with_encrypted_nif,
                "percentage": pct(with_encrypted_nif, total_clients)
            },
            "nif_plain_text": {
                "count": with_plain_nif,
                "percentage": pct(with_plain_nif, total_clients)
            },
            "telefone_encrypted": {
                "count": with_encrypted_telefone,
                "percentage": pct(with_encrypted_telefone, total_clients)
            }
        },
        "needs_migration": {
            "count": with_plain_nif,
            "percentage": pct(with_plain_nif, total_clients)
        }
    }


@router.post("/run")
async def run_migration(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Executa a migração de encriptação de dados de clientes.
    
    A migração corre em background e:
    - Encripta NIFs, telefones e dados sensíveis
    - Gera blind indexes para pesquisa
    - Mantém compatibilidade com dados antigos
    
    Acesso: Apenas Admin, CEO ou Diretor
    """
    # Verificar se já há uma migração a correr
    # (poderia usar um flag na BD para controlar)
    
    # Adicionar tarefa em background
    background_tasks.add_task(run_migration_task)
    
    logger.info(f"Migração iniciada por {user.get('email')}")
    
    return {
        "success": True,
        "message": "Migração iniciada em background. Verifique os logs do servidor para acompanhar o progresso.",
        "started_by": user.get("email"),
        "note": "A migração pode demorar alguns minutos dependendo do número de clientes."
    }


@router.post("/run-single/{client_id}")
async def run_migration_single(
    client_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Executa a migração para um único cliente (útil para testes).
    
    Acesso: Apenas Admin, CEO ou Diretor
    """
    import re
    
    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    updates = {}
    changes = []
    
    # Processar dados_pessoais
    dados_pessoais = client.get("dados_pessoais", {})
    if isinstance(dados_pessoais, dict):
        dp_updates = {}
        
        nif = dados_pessoais.get("nif")
        if nif and not is_encrypted(nif):
            nif_clean = re.sub(r'[^\d]', '', str(nif))
            if len(nif_clean) == 9:
                dp_updates["nif_hash"] = generate_nif_hash(nif_clean)
                changes.append(f"nif_hash gerado para {nif_clean[:3]}***")
            if encryption_service.is_available():
                dp_updates["nif"] = encryption_service.encrypt(str(nif))
                changes.append("NIF encriptado")
        
        # documento_id
        doc_id = dados_pessoais.get("documento_id")
        if doc_id and not is_encrypted(doc_id) and encryption_service.is_available():
            dp_updates["documento_id"] = encryption_service.encrypt(str(doc_id))
            changes.append("documento_id encriptado")
        
        # morada_fiscal
        morada = dados_pessoais.get("morada_fiscal")
        if morada and not is_encrypted(morada) and encryption_service.is_available():
            dp_updates["morada_fiscal"] = encryption_service.encrypt(str(morada))
            changes.append("morada_fiscal encriptada")
        
        if dp_updates:
            updates["dados_pessoais"] = {**dados_pessoais, **dp_updates}
    
    # Processar contacto
    contacto = client.get("contacto", {})
    if isinstance(contacto, dict):
        ct_updates = {}
        
        email = contacto.get("email")
        if email and not contacto.get("email_hash"):
            ct_updates["email_hash"] = generate_email_hash(email)
            changes.append(f"email_hash gerado para {email[:3]}***")
        
        telefone = contacto.get("telefone")
        if telefone and not is_encrypted(telefone):
            telefone_clean = re.sub(r'[^\d]', '', str(telefone))
            if len(telefone_clean) >= 9:
                ct_updates["telefone_hash"] = generate_telefone_hash(telefone_clean)
                changes.append(f"telefone_hash gerado para {telefone_clean[:3]}***")
            if encryption_service.is_available():
                ct_updates["telefone"] = encryption_service.encrypt(str(telefone))
                changes.append("Telefone encriptado")
        
        # telefone_secundario
        tel_sec = contacto.get("telefone_secundario")
        if tel_sec and not is_encrypted(tel_sec) and encryption_service.is_available():
            ct_updates["telefone_secundario"] = encryption_service.encrypt(str(tel_sec))
            changes.append("telefone_secundario encriptado")
        
        if ct_updates:
            updates["contacto"] = {**contacto, **ct_updates}
    
    # Processar titular2_data
    titular2 = client.get("titular2_data", {})
    if isinstance(titular2, dict) and titular2:
        t2_updates = {}
        
        nif2 = titular2.get("nif")
        if nif2 and not is_encrypted(nif2):
            nif2_clean = re.sub(r'[^\d]', '', str(nif2))
            if len(nif2_clean) == 9:
                t2_updates["nif_hash"] = generate_nif_hash(nif2_clean)
                changes.append(f"titular2.nif_hash gerado para {nif2_clean[:3]}***")
            if encryption_service.is_available():
                t2_updates["nif"] = encryption_service.encrypt(str(nif2))
                changes.append("NIF titular2 encriptado")
        
        if t2_updates:
            updates["titular2_data"] = {**titular2, **t2_updates}
    
    # Actualizar se houver alterações
    if updates:
        await db.clients.update_one({"id": client_id}, {"$set": updates})
        return {
            "success": True,
            "message": f"Cliente {client_id} migrado com sucesso",
            "client_name": client.get("nome"),
            "changes": changes
        }
    else:
        return {
            "success": True,
            "message": f"Cliente {client_id} já estava migrado",
            "client_name": client.get("nome"),
            "changes": []
        }
