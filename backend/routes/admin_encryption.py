"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - ENCRIPTAÇÃO
====================================================================
Endpoints para gerir a encriptação de campos sensíveis.

Inclui:
- Status da encriptação
- Migração de dados existentes
- Verificação de encriptação
====================================================================
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from database import db
from models.auth import UserRole
from services.auth import require_roles
from services.encryption import encryption_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/encryption", tags=["Admin - Encryption"])


@router.get("/status")
async def get_encryption_status(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém o status atual da encriptação.
    
    Retorna:
    - Se a encriptação está disponível
    - Contagem de processos com dados encriptados
    - Contagem de processos pendentes de encriptação
    """
    # Contar processos totais
    total_processes = await db.processes.count_documents({})
    
    # Verificar se há campos encriptados (procurar pelo prefixo)
    # Isto é uma aproximação - não conta todos os campos
    encrypted_count = 0
    sample_processes = await db.processes.find({}, {
        "_id": 0, 
        "id": 1, 
        "personal_data.nif": 1,
        "personal_data.documento_id": 1
    }).limit(100).to_list(100)
    
    for proc in sample_processes:
        personal = proc.get("personal_data", {})
        nif = personal.get("nif", "")
        if nif and encryption_service.is_encrypted(nif):
            encrypted_count += 1
    
    # Estimar total encriptado
    estimated_encrypted = int((encrypted_count / 100) * total_processes) if sample_processes else 0
    
    return {
        "encryption_available": encryption_service.is_available(),
        "total_processes": total_processes,
        "estimated_encrypted": estimated_encrypted,
        "estimated_pending": total_processes - estimated_encrypted,
        "fields_protected": [
            "NIFs (personal_data.nif, titular2_data.nif, employer_nif)",
            "Documentos de Identidade (documento_id)",
            "Senhas de portais (portal_financas_senha, seg_social_senha)",
            "Moradas fiscais (morada_fiscal)",
            "Telefones (client_phone, titular2_data.phone)"
        ]
    }


@router.post("/migrate")
async def migrate_encryption(
    background_tasks: BackgroundTasks,
    dry_run: bool = False,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Executa a migração de encriptação em background.
    
    Args:
        dry_run: Se True, simula sem guardar alterações
    
    Returns:
        ID da tarefa de migração
    """
    if not encryption_service.is_available():
        raise HTTPException(
            status_code=503, 
            detail="Serviço de encriptação não disponível. Configure ENCRYPTION_KEY."
        )
    
    # Executar migração em background
    from services.migrate_encryption import migrate_processes_encryption
    
    async def run_migration():
        """Executa a migração de encriptação de dados sensíveis dos processos.

        Porquê este endpoint existe: durante o desenvolvimento, os campos
        sensíveis (NIF, email, telefone) foram armazenados em texto claro.
        Este endpoint migra esses dados para encriptação AES-256, criando
        blind indexes para pesquisa.

        O dry_run=True permite validar sem modificar dados.

        Args:
            Nenhum parâmetro direto — usa variáveis do closure
            (dry_run, user).
        """
        try:
            stats = await migrate_processes_encryption(dry_run=dry_run, batch_size=50)
            logger.info(f"Migração concluída: {stats}")
            
            # Guardar log da migração
            await db.activity_logs.insert_one({
                "type": "encryption_migration",
                "user_id": user["id"],
                "user_name": user.get("name"),
                "stats": stats,
                "dry_run": dry_run,
                "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Erro na migração: {e}")
    
    background_tasks.add_task(run_migration)
    
    return {
        "message": "Migração iniciada em background",
        "dry_run": dry_run,
        "check_status_at": "/api/admin/encryption/status"
    }


@router.post("/migrate-sync")
async def migrate_encryption_sync(
    dry_run: bool = False,
    batch_size: int = 50,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Executa a migração de encriptação síncrona (para conjuntos pequenos).
    
    Args:
        dry_run: Se True, simula sem guardar alterações
        batch_size: Número de documentos por batch
    
    Returns:
        Estatísticas da migração
    """
    if not encryption_service.is_available():
        raise HTTPException(
            status_code=503, 
            detail="Serviço de encriptação não disponível. Configure ENCRYPTION_KEY."
        )
    
    from services.migrate_encryption import migrate_processes_encryption
    
    stats = await migrate_processes_encryption(dry_run=dry_run, batch_size=batch_size)
    
    return stats


@router.post("/verify/{process_id}")
async def verify_process_encryption(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Verifica se um processo específico tem dados encriptados.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    results = {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "encrypted_fields": [],
        "unencrypted_fields": []
    }
    
    # Verificar campos principais
    fields_to_check = {
        "personal_data.nif": process.get("personal_data", {}).get("nif"),
        "personal_data.documento_id": process.get("personal_data", {}).get("documento_id"),
        "personal_data.morada_fiscal": process.get("personal_data", {}).get("morada_fiscal"),
        "client_phone": process.get("client_phone"),
        "financial_data.portal_financas_senha": process.get("financial_data", {}).get("portal_financas_senha"),
    }
    
    for field_path, value in fields_to_check.items():
        if value:
            if encryption_service.is_encrypted(str(value)):
                results["encrypted_fields"].append(field_path)
            else:
                results["unencrypted_fields"].append(field_path)
    
    return results


@router.post("/encrypt-process/{process_id}")
async def encrypt_single_process(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Encripta os dados sensíveis de um processo específico.
    """
    if not encryption_service.is_available():
        raise HTTPException(
            status_code=503, 
            detail="Serviço de encriptação não disponível"
        )
    
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Encriptar dados
    encrypted_process = encryption_service.encrypt_process(process)
    
    # Remover _id para evitar erro de actualização
    if "_id" in encrypted_process:
        del encrypted_process["_id"]
    
    # Guardar
    await db.processes.update_one(
        {"id": process_id},
        {"$set": encrypted_process}
    )
    
    return {
        "success": True,
        "message": f"Processo {process_id} encriptado com sucesso"
    }
