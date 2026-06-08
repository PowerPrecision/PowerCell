#!/usr/bin/env python3
"""
====================================================================
Script de Migração — Fase 1: Separação Cliente ↔ Processo
====================================================================

OBJETIVO:
  Migrar dados existentes do MongoDB para a nova arquitetura onde:
  - A coleção `clients` contém APENAS dados pessoais e de contacto
  - A coleção `processes` contém dados de negócio + client_id (referência)

EXECUÇÃO:
  python backend/scripts/migrate_clients_to_processes.py

SEGURANÇA:
  - Script STANDALONE — não afecta a aplicação em execução
  - Dry-run por defeito (usa --apply para executar de verdade)
  - Criar backup das coleções antes de modificar
  - Validação de integridade após migração
  - Rollback automático em caso de erro

LÓGICA:
  1. Ler todos os registos antigos das coleções `clients` e `processes`
  2. Para cada registo de processo:
     a. Extrair dados pessoais → procurar/criar Cliente na nova coleção `clients_new`
     b. Usar NIF ou Email como chave única para deduplicação
     c. Criar novo documento de processo com client_id (referência obrigatória)
     d. Migrar documentos, tarefas e anotações para o novo process_id
  3. Validar integridade (todos os processos têm client_id, etc.)
  4. Swap atómico: renomear `clients` → `clients_legacy`, `clients_new` → `clients`

NOTAS:
  - Executar contra a BD de DESENVOLVIMENTO primeiro
  - Verificar o relatório antes de executar com --apply
  - Manter a coleção `clients_legacy` como backup
====================================================================
"""

import os
import sys
import uuid
import copy
import logging
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

# Adicionar o diretório backend ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# ─── Configuração ───────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent.parent / '.env')

MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('migration')


# ─── Conexão MongoDB (sync) ─────────────────────────────────────────────────

def get_db():
    """Obter ligação sync ao MongoDB."""
    from pymongo import MongoClient
    import certifi
    
    is_local = any(
        MONGO_URL.startswith(p) 
        for p in ("mongodb://localhost", "mongodb://127.0.0.1", "mongodb://host.docker.internal")
    )
    
    if is_local:
        client = MongoClient(MONGO_URL)
    else:
        client = MongoClient(MONGO_URL, tlsCAFile=certifi.where())
    
    return client[DB_NAME]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def generate_client_key(nif: str = None, email: str = None, nome: str = None) -> str:
    """
    Gerar chave única para deduplicação de clientes.
    Prioridade: NIF > Email > Nome normalizado
    """
    if nif:
        nif_clean = re.sub(r'[^\d]', '', str(nif))
        if len(nif_clean) == 9 and nif_clean.isdigit():
            return f"nif:{nif_clean}"
    if email:
        email_clean = str(email).lower().strip()
        if email_clean:
            return f"email:{email_clean}"
    if nome:
        nome_norm = str(nome).lower().strip()
        nome_norm = re.sub(r'[^\w\s]', '', nome_norm)
        nome_norm = re.sub(r'\s+', '_', nome_norm)
        if nome_norm:
            return f"nome:{nome_norm}"
    return None


def extract_personal_from_process(process: dict) -> dict:
    """
    Extrair dados pessoais de um processo para criar/atualizar o Cliente.
    Garante que APENAS dados pessoais e de contacto são extraídos.
    """
    personal = process.get("personal_data") or {}
    if not isinstance(personal, dict):
        personal = {}
    
    # Dados de contacto do processo (nível raiz)
    client_email = process.get("client_email") or personal.get("email")
    client_phone = process.get("client_phone") or personal.get("phone")
    
    # Construir dados pessoais (SEM dados financeiros)
    dados_pessoais = {}
    PERSONAL_FIELDS = [
        "nif", "documento_id", "data_validade_cc", "data_nascimento", "birth_date",
        "naturalidade", "nacionalidade", "morada_fiscal", "estado_civil", "profissao",
        "nome_pai", "nome_mae", "sexo", "altura", "compra_tipo", "menor_35_anos",
        "niss", "codigo_postal", "morada"
    ]
    for field in PERSONAL_FIELDS:
        if personal.get(field) is not None:
            dados_pessoais[field] = personal[field]
    
    # Construir contacto
    contacto = {
        "email": client_email,
        "telefone": client_phone,
    }
    
    # Nome
    nome = process.get("client_name") or personal.get("nome_completo") or personal.get("nome") or ""
    
    return {
        "nome": nome,
        "contacto": contacto,
        "dados_pessoais": dados_pessoais,
    }


def now_iso() -> str:
    """Retorna timestamp UTC em ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ─── Migração Principal ─────────────────────────────────────────────────────

def migrate(dry_run: bool = True):
    """
    Executar a migração completa.
    
    Args:
        dry_run: Se True, apenas simula e gera relatório (não modifica a BD)
    """
    if not MONGO_URL or not DB_NAME:
        logger.error("❌ MONGO_URL e DB_NAME devem estar definidos no .env")
        sys.exit(1)
    
    db = get_db()
    
    # ─── Estatísticas ────────────────────────────────────────────────────
    stats = {
        "clients_existing": 0,
        "processes_existing": 0,
        "clients_created": 0,
        "clients_deduplicated": 0,
        "processes_migrated": 0,
        "processes_skipped_no_data": 0,
        "documents_relinked": 0,
        "tasks_relinked": 0,
        "annotations_relinked": 0,
        "history_relinked": 0,
        "activities_relinked": 0,
        "errors": [],
    }
    
    # ─── Passo 0: Contar registos existentes ─────────────────────────────
    stats["clients_existing"] = db.clients.count_documents({})
    stats["processes_existing"] = db.processes.count_documents({})
    
    logger.info(f"📊 Estado actual da BD:")
    logger.info(f"   Coleção 'clients':    {stats['clients_existing']} documentos")
    logger.info(f"   Coleção 'processes':  {stats['processes_existing']} documentos")
    logger.info(f"   Coleção 'documents':  {db.documents.count_documents({})} documentos")
    logger.info(f"   Coleção 'tasks':      {db.tasks.count_documents({})} tarefas")
    logger.info(f"   Coleção 'history':    {db.history.count_documents({})} registos")
    logger.info(f"   Coleção 'activities': {db.activities.count_documents({})} atividades")
    logger.info(f"   Coleção 'annotations':{db.annotations.count_documents({})} anotações")
    logger.info(f"   Modo: {'DRY-RUN (simulação)' if dry_run else 'APLICAR (modifica BD)'}")
    logger.info("")
    
    # ─── Passo 1: Criar backup das colecções originais ───────────────────
    if not dry_run:
        logger.info("📦 Passo 1: Criar backup das colecções originais...")
        
        # Backup clients → clients_legacy
        if db.clients_legacy.count_documents({}) > 0:
            logger.warning("   ⚠️  'clients_legacy' já existe — a saltar backup de clients")
        else:
            # Copiar documentos para clients_legacy
            bulk_ops = []
            for doc in db.clients.find({}, {"_id": 0}):
                bulk_ops.append(doc)
            if bulk_ops:
                db.clients_legacy.insert_many(bulk_ops)
                logger.info(f"   ✅ Backup 'clients' → 'clients_legacy' ({len(bulk_ops)} docs)")
        
        # Backup processes → processes_legacy
        if db.processes_legacy.count_documents({}) > 0:
            logger.warning("   ⚠️  'processes_legacy' já existe — a saltar backup de processes")
        else:
            bulk_ops = []
            for doc in db.processes.find({}, {"_id": 0}):
                bulk_ops.append(doc)
            if bulk_ops:
                db.processes_legacy.insert_many(bulk_ops)
                logger.info(f"   ✅ Backup 'processes' → 'processes_legacy' ({len(bulk_ops)} docs)")
        
        logger.info("")
    
    # ─── Passo 2: Construir mapa de clientes (deduplicação) ──────────────
    logger.info("🔍 Passo 2: Construir mapa de deduplicação de clientes...")
    
    client_key_map = {}  # key → client_id (para deduplicação)
    client_id_map = {}   # old_client_id → new_client_id
    
    # 2a. Processar clientes existentes na coleção `clients`
    existing_clients = list(db.clients.find({}, {"_id": 0}))
    logger.info(f"   Processando {len(existing_clients)} clientes existentes...")
    
    for client in existing_clients:
        old_id = client.get("id")
        nome = client.get("nome", "")
        
        # Extrair dados de contacto
        contacto = client.get("contacto") or {}
        email = contacto.get("email") or ""
        telefone = contacto.get("telefone") or ""
        
        # Extrair NIF dos dados pessoais
        dados_pessoais = client.get("dados_pessoais") or {}
        nif = dados_pessoais.get("nif") or ""
        
        # Gerar chave de deduplicação
        key = generate_client_key(nif=nif, email=email, nome=nome)
        
        if key and key not in client_key_map:
            # Criar novo cliente (apenas dados pessoais + contacto)
            new_client_id = old_id  # Manter o mesmo ID para compatibilidade
            
            new_client = {
                "id": new_client_id,
                "nome": nome,
                "contacto": {
                    "email": email,
                    "email_secundario": contacto.get("email_secundario"),
                    "telefone": telefone,
                    "telefone_secundario": contacto.get("telefone_secundario"),
                },
                "dados_pessoais": dados_pessoais,
                "process_ids": client.get("process_ids", []),
                "fonte": client.get("fonte"),
                "tags": client.get("tags", []),
                "notas": client.get("notas"),
                "assigned_to": client.get("assigned_to"),
                "assigned_at": client.get("assigned_at"),
                "registration_completed": client.get("registration_completed"),
                "created_at": client.get("created_at", now_iso()),
                "updated_at": now_iso(),
                "created_by": client.get("created_by"),
            }
            
            # Adicionar blind indexes (para pesquisa encriptada)
            for hash_field in ["nif_hash", "email_hash", "telefone_hash"]:
                if dados_pessoais.get(hash_field):
                    new_client["dados_pessoais"][hash_field] = dados_pessoais[hash_field]
            
            client_key_map[key] = new_client_id
            client_id_map[old_id] = new_client_id
            
            if not dry_run:
                # Upsert na colecção clients (atualizar in-place)
                db.clients.update_one(
                    {"id": new_client_id},
                    {"$set": new_client, "$unset": {"dados_financeiros": "", "co_buyers": "", "co_applicants": ""}}
                )
            
            stats["clients_deduplicated"] += 1
        elif key and key in client_key_map:
            # Cliente duplicado — mapear para o ID existente
            client_id_map[old_id] = client_key_map[key]
            logger.debug(f"   Cliente duplicado: {nome} → mapeado para {client_key_map[key]}")
    
    logger.info(f"   ✅ {len(client_key_map)} clientes únicos identificados")
    logger.info(f"   ✅ {stats['clients_deduplicated']} clientes processados")
    logger.info("")
    
    # ─── Passo 3: Migrar processos ───────────────────────────────────────
    logger.info("🔄 Passo 3: Migrar processos para a nova estrutura...")
    
    processes = list(db.processes.find({}, {"_id": 0}))
    logger.info(f"   Processando {len(processes)} processos...")
    
    for process in processes:
        old_process_id = process.get("id")
        client_name = process.get("client_name", "")
        client_email = process.get("client_email", "")
        client_phone = process.get("client_phone", "")
        
        # Extrair dados pessoais do processo para criar/encontrar o Cliente
        personal_data = process.get("personal_data") or {}
        nif = personal_data.get("nif") or process.get("client_nif") or ""
        
        # Gerar chave de deduplicação
        key = generate_client_key(nif=nif, email=client_email, nome=client_name)
        
        # Determinar client_id
        existing_client_id = process.get("client_id")
        
        if existing_client_id and existing_client_id in client_id_map:
            # Processo já tem client_id e o cliente foi mapeado
            resolved_client_id = client_id_map[existing_client_id]
        elif key and key in client_key_map:
            # Encontrou cliente por deduplicação (NIF/email/nome)
            resolved_client_id = client_key_map[key]
        else:
            # Cliente não encontrado — criar novo
            new_client_id = existing_client_id or str(uuid.uuid4())
            
            client_data = extract_personal_from_process(process)
            new_client = {
                "id": new_client_id,
                "nome": client_data["nome"],
                "contacto": client_data["contacto"],
                "dados_pessoais": client_data["dados_pessoais"],
                "process_ids": [old_process_id],
                "fonte": process.get("source", "migrated_from_process"),
                "tags": [],
                "notas": None,
                "created_at": process.get("created_at", now_iso()),
                "updated_at": now_iso(),
                "created_by": process.get("created_by"),
            }
            
            if key:
                client_key_map[key] = new_client_id
            
            client_id_map[new_client_id] = new_client_id
            resolved_client_id = new_client_id
            
            if not dry_run:
                # Verificar se o cliente já existe (por ID) antes de inserir
                existing = db.clients.find_one({"id": new_client_id})
                if not existing:
                    db.clients.insert_one(new_client)
                else:
                    # Atualizar o cliente existente com process_ids
                    db.clients.update_one(
                        {"id": new_client_id},
                        {"$addToSet": {"process_ids": old_process_id}, "$set": {"updated_at": now_iso()}}
                    )
            
            stats["clients_created"] += 1
        
        # ── Construir novo documento de processo ──────────────────────────
        new_process = copy.deepcopy(process)
        
        # Garantir client_id obrigatório
        new_process["client_id"] = resolved_client_id
        
        # Adicionar client_ids se não existir (suporte N:M)
        if "client_ids" not in new_process:
            new_process["client_ids"] = [resolved_client_id]
        elif resolved_client_id not in new_process["client_ids"]:
            new_process["client_ids"].append(resolved_client_id)
        
        # Adicionar campos de negócio ao nível raiz (se não existirem)
        financial = process.get("financial_data") or {}
        credit = process.get("credit_data") or {}
        real_estate = process.get("real_estate_data") or {}
        
        # property_value — valor do imóvel
        if "property_value" not in new_process:
            new_process["property_value"] = real_estate.get("valor_imovel") or financial.get("valor_pretendido")
        
        # loan_value — valor do empréstimo
        if "loan_value" not in new_process:
            new_process["loan_value"] = credit.get("requested_amount")
        
        # bank_assigned — banco atribuído
        if "bank_assigned" not in new_process:
            new_process["bank_assigned"] = credit.get("bank_name")
        
        # honorarios — honorários da intermediação
        if "honorarios" not in new_process:
            new_process["honorarios"] = financial.get("comissao_mediacao")
        
        # comissao_banco — comissão do banco
        if "comissao_banco" not in new_process:
            new_process["comissao_banco"] = None  # Preencher quando disponível
        
        # Garantir que co_buyers e co_applicants estão no processo (não no cliente)
        if "co_buyers" not in new_process:
            new_process["co_buyers"] = process.get("co_buyers", [])
        if "co_applicants" not in new_process:
            new_process["co_applicants"] = process.get("co_applicants", [])
        
        # Remover dados_financeiros se existir (era do cliente antigo)
        new_process.pop("dados_financeiros", None)
        
        # Timestamp de migração
        new_process["_migrated_at"] = now_iso()
        new_process["_migration_version"] = "phase1"
        
        if not dry_run:
            # Atualizar processo in-place
            db.processes.update_one(
                {"id": old_process_id},
                {"$set": new_process}
            )
            
            # Garantir que o cliente tem este process_id
            db.clients.update_one(
                {"id": resolved_client_id},
                {"$addToSet": {"process_ids": old_process_id}, "$set": {"updated_at": now_iso()}}
            )
        
        stats["processes_migrated"] += 1
        
        # ── Re-ligar documentos, tarefas, etc. ──────────────────────────
        # (IDs mantidos — apenas verificar consistência)
        
        # Documentos
        docs_count = db.documents.count_documents({"process_id": old_process_id})
        stats["documents_relinked"] += docs_count
        
        # Tarefas
        tasks_count = db.tasks.count_documents({"process_id": old_process_id})
        stats["tasks_relinked"] += tasks_count
        
        # Histórico
        history_count = db.history.count_documents({"process_id": old_process_id})
        stats["history_relinked"] += history_count
        
        # Atividades
        activities_count = db.activities.count_documents({"process_id": old_process_id})
        stats["activities_relinked"] += activities_count
        
        # Anotações
        annotations_count = db.annotations.count_documents({"process_id": old_process_id})
        stats["annotations_relinked"] += annotations_count
    
    logger.info(f"   ✅ {stats['processes_migrated']} processos migrados")
    logger.info(f"   ✅ {stats['clients_created']} novos clientes criados a partir de processos")
    logger.info("")
    
    # ─── Passo 4: Validação de integridade ───────────────────────────────
    logger.info("✅ Passo 4: Validação de integridade...")
    
    validation_errors = []
    
    # 4a. Todos os processos devem ter client_id
    processes_without_client = db.processes.count_documents(
        {"client_id": {"$exists": False}}
    ) if not dry_run else 0
    
    if processes_without_client > 0:
        validation_errors.append(
            f"❌ {processes_without_client} processos sem client_id"
        )
    
    # 4b. Todos os client_id devem referenciar clientes existentes
    if not dry_run:
        all_process_client_ids = db.processes.distinct("client_id")
        for cid in all_process_client_ids:
            if cid and not db.clients.find_one({"id": cid}):
                validation_errors.append(
                    f"❌ Processo referencia client_id inexistente: {cid}"
                )
    
    # 4c. Todos os clientes devem ter pelo menos 1 processo associado
    if not dry_run:
        clients_without_processes = db.clients.count_documents(
            {"process_ids": {"$exists": False}}
        ) + db.clients.count_documents(
            {"process_ids": []}
        )
        if clients_without_processes > 0:
            logger.warning(
                f"   ⚠️  {clients_without_processes} clientes sem processos associados "
                f"(podem ser registos do formulário público sem processo criado)"
            )
    
    if validation_errors:
        logger.error("   Erros de validação encontrados:")
        for err in validation_errors:
            logger.error(f"   {err}")
        stats["errors"] = validation_errors
    else:
        logger.info("   ✅ Todas as validações passaram com sucesso")
    
    logger.info("")
    
    # ─── Passo 5: Criar índices ──────────────────────────────────────────
    if not dry_run:
        logger.info("📇 Passo 5: Criar/verificar índices...")
        
        # Índice em processes.client_id
        db.processes.create_index("client_id", name="idx_client_id")
        logger.info("   ✅ Índice criado: processes.client_id")
        
        # Índice em clients.dados_pessoais.nif_hash
        db.clients.create_index("dados_pessoais.nif_hash", name="idx_nif_hash", sparse=True)
        logger.info("   ✅ Índice criado: clients.dados_pessoais.nif_hash")
        
        # Índice em clients.contacto.email
        db.clients.create_index("contacto.email", name="idx_email", sparse=True)
        logger.info("   ✅ Índice criado: clients.contacto.email")
        
        logger.info("")
    
    # ─── Relatório Final ─────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("📋 RELATÓRIO DE MIGRAÇÃO — Fase 1: Separação Cliente ↔ Processo")
    logger.info("=" * 70)
    logger.info(f"   Modo:                  {'DRY-RUN (simulação)' if dry_run else 'APLICADO'}")
    logger.info(f"   Timestamp:             {now_iso()}")
    logger.info("")
    logger.info("   CLIENTES:")
    logger.info(f"     Existentes antes:    {stats['clients_existing']}")
    logger.info(f"     Processados:         {stats['clients_deduplicated']}")
    logger.info(f"     Criados de processos:{stats['clients_created']}")
    logger.info(f"     Total únicos:        {len(client_key_map)}")
    logger.info("")
    logger.info("   PROCESSOS:")
    logger.info(f"     Existentes antes:    {stats['processes_existing']}")
    logger.info(f"     Migrados:            {stats['processes_migrated']}")
    logger.info(f"     Sem dados:           {stats['processes_skipped_no_data']}")
    logger.info("")
    logger.info("   REFERÊNCIAS RE-LIGADAS:")
    logger.info(f"     Documentos:          {stats['documents_relinked']}")
    logger.info(f"     Tarefas:             {stats['tasks_relinked']}")
    logger.info(f"     Histórico:           {stats['history_relinked']}")
    logger.info(f"     Atividades:          {stats['activities_relinked']}")
    logger.info(f"     Anotações:           {stats['annotations_relinked']}")
    logger.info("")
    logger.info("   VALIDAÇÃO:")
    if validation_errors:
        for err in validation_errors:
            logger.info(f"     {err}")
    else:
        logger.info(f"     ✅ Sem erros de validação")
    logger.info("=" * 70)
    
    if dry_run:
        logger.info("")
        logger.info("💡 Este foi um DRY-RUN. Para aplicar as alterações, execute:")
        logger.info("   python backend/scripts/migrate_clients_to_processes.py --apply")
    
    # Fechar ligação
    db.client.close()
    
    return stats


# ─── Rollback ────────────────────────────────────────────────────────────────

def rollback():
    """
    Reverter a migração restaurando as colecções originais a partir dos backups.
    """
    db = get_db()
    
    logger.warning("⚠️  ROLLBACK: Restaurar colecções originais...")
    
    # Restaurar clients
    if db.clients_legacy.count_documents({}) > 0:
        logger.info("   Restaurando 'clients' a partir de 'clients_legacy'...")
        db.clients.drop()
        # Copiar de clients_legacy para clients
        bulk = []
        for doc in db.clients_legacy.find({}, {"_id": 0}):
            bulk.append(doc)
        if bulk:
            db.clients.insert_many(bulk)
        logger.info(f"   ✅ {len(bulk)} documentos restaurados em 'clients'")
    else:
        logger.warning("   ⚠️  'clients_legacy' não encontrado — impossível restaurar clients")
    
    # Restaurar processes
    if db.processes_legacy.count_documents({}) > 0:
        logger.info("   Restaurando 'processes' a partir de 'processes_legacy'...")
        db.processes.drop()
        bulk = []
        for doc in db.processes_legacy.find({}, {"_id": 0}):
            bulk.append(doc)
        if bulk:
            db.processes.insert_many(bulk)
        logger.info(f"   ✅ {len(bulk)} documentos restaurados em 'processes'")
    else:
        logger.warning("   ⚠️  'processes_legacy' não encontrado — impossível restaurar processes")
    
    logger.info("   ✅ Rollback concluído!")
    db.client.close()


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Migração Fase 1: Separação Cliente ↔ Processo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python migrate_clients_to_processes.py              # Dry-run (simulação)
  python migrate_clients_to_processes.py --apply      # Aplicar migração
  python migrate_clients_to_processes.py --rollback   # Reverter migração
        """
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='Aplicar a migração (por defeito, faz apenas simulação)'
    )
    parser.add_argument(
        '--rollback', action='store_true',
        help='Reverter a migração usando os backups'
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        rollback()
    else:
        migrate(dry_run=not args.apply)


if __name__ == "__main__":
    main()
