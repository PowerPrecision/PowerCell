"""
====================================================================
ÍNDICES DE BASE DE DADOS - OPTIMIZAÇÃO DE PERFORMANCE
====================================================================
Script para criar índices nas colecções MongoDB mais consultadas.
Melhora significativamente o tempo de resposta para queries frequentes.

Executar manualmente ou na inicialização da aplicação.

NOTA RGPD: Campos encriptados (NIF, telefone, email) são armazenados
encriptados com Fernet. Para pesquisa, usamos BLIND INDEXES (hashes
determinísticos SHA-256). Os índices devem apontar para os campos
de hash (_hash) e NÃO para os campos encriptados.

DATA LIFECYCLE MANAGEMENT (TTL Indexes):
- Índices TTL automatizam a purga de dados efémeros
- Coleções com TTL: refresh_tokens, system_error_logs, email_drafts
- IMPORTANTE: TTL requer campos datetime nativos (NÃO ISO strings)
====================================================================
"""
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)


async def _create_index_safe(collection, idx: dict, collection_name: str, results: dict) -> None:
    """
    Cria um índice MongoDB com tratamento robusto de conflitos.

    Lida com:
    - Índice já existe com o mesmo nome (skip)
    - Índice já existe com nome diferente na mesma key pattern (code 85 — drop & recreate)
    - Índice com o mesmo nome mas key pattern diferente (code 86 — drop & recreate)
    - Outros erros (regista e continua)

    Opções suportadas no dict idx:
    - keys: list of (field, direction) tuples (obrigatório)
    - name: nome do índice (obrigatório)
    - unique: bool
    - sparse: bool
    - expireAfterSeconds: int (para TTL indexes)
    - partialFilterExpression: dict (para partial indexes)
    """
    idx_name = idx["name"]
    idx_key = idx["keys"]
    label = f"{collection_name}.{idx_name}"

    try:
        create_kwargs = {
            "name": idx_name,
            "background": True,
        }
        if idx.get("unique"):
            create_kwargs["unique"] = True
        if idx.get("sparse"):
            create_kwargs["sparse"] = True
        if idx.get("expireAfterSeconds") is not None:
            create_kwargs["expireAfterSeconds"] = idx["expireAfterSeconds"]
        if idx.get("partialFilterExpression"):
            create_kwargs["partialFilterExpression"] = idx["partialFilterExpression"]

        await collection.create_index(idx_key, **create_kwargs)
        results["created"].append(label)
        logger.info(f"Índice criado: {label}")

    except OperationFailure as e:
        error_code = e.code

        # Code 85: Index already exists with different options / different name
        # Code 86: Index already exists with same name but different key pattern
        if error_code in (85, 86):
            logger.warning(
                f"⚠️ Índice {label} já existe com parâmetros diferentes (code {error_code}). "
                f"Tentando remover e recriar..."
            )
            try:
                # Tentar remover o índice pelo nome desejado
                try:
                    await collection.drop_index(idx_name)
                    logger.info(f"🗑️ Índice antigo removido pelo nome: {label}")
                except OperationFailure:
                    # Se não existe pelo nome, procurar pelo key pattern
                    # e remover o índice conflituoso
                    existing = await collection.index_information()
                    for existing_name, existing_info in existing.items():
                        if existing_name == "_id_":
                            continue
                        existing_key = existing_info.get("key", [])
                        # Comparar key patterns (normalizar para comparação)
                        desired_key = [(k, v) for k, v in idx_key] if isinstance(idx_key, list) else [(idx_key[0], idx_key[1])]
                        if existing_key == desired_key:
                            await collection.drop_index(existing_name)
                            logger.info(f"🗑️ Índice conflituoso removido: {collection_name}.{existing_name} (key={existing_key})")
                            break

                # Recriar com os parâmetros correctos
                await collection.create_index(idx_key, **create_kwargs)
                results["created"].append(f"{label} (recriado)")
                logger.info(f"✅ Índice recriado: {label}")

            except Exception as retry_error:
                results["errors"].append(f"{label}: Falha ao recriar: {str(retry_error)}")
                logger.error(f"Erro ao recriar índice {label}: {retry_error}")

        elif "already exists" in str(e).lower():
            results["skipped"].append(label)
        else:
            results["errors"].append(f"{label}: {str(e)}")
            logger.error(f"Erro ao criar índice {label}: {e}")

    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append(label)
        else:
            results["errors"].append(f"{label}: {str(e)}")
            logger.error(f"Erro ao criar índice {label}: {e}")


# Lista de índices antigos/incorretos que devem ser removidos
DEPRECATED_INDEXES = {
    "properties": [
        "idx_internal_ref",  # Nome antigo incorreto - campo era internal_ref
        "idx_location",  # Índice antigo com campos incorretos (distrito, concelho) - deve ser (address.district, address.municipality)
    ],
    # Índices em campos encriptados são INÚTEIS porque os dados estão encriptados
    # Deve usar-se os blind indexes (_hash) em vez destes
    "processes": [
        "idx_nif",  # Aponta para personal_data.nif que está encriptado - usar nif_hash
        # NOTA: idx_text_search inclui personal_data.nif que é inútil, mas texto indexes são complexos de alterar
    ],
    "clients": [
        # Índices em campos encriptados que possam ter sido criados anteriormente
        "idx_nif_plain",  # Se existir algum índice em dados_pessoais.nif plain text
        "idx_nif_hash",   # Nome antigo do blind index de NIF — agora é idx_client_nif_hash (causa code 85)
        "idx_email",      # Nome antigo do índice de email — agora é idx_client_email_hash (causa code 85)
    ],
    "system_error_logs": [
        "idx_ttl",  # Índice TTL antigo (90 dias) em campo ISO string - não funciona. Substituído por ttl_system_error_logs
    ],
    # Pacote EA — unique (user_id, company_id) bloqueava vários cargos na mesma empresa
    "user_company_roles": [
        "idx_user_company_unique",  # unique antigo (user_id, company_id)
        "idx_ucr_unique",           # nome usado em backup_restore
    ],
}

# ====================================================================
# CONFIGURAÇÃO DE ÍNDICES TTL (DATA LIFECYCLE MANAGEMENT)
# ====================================================================
# Os índices TTL automatizam a purga de dados efémeros sem cron-jobs.
# IMPORTANTE: O campo deve ser um BSON Date (datetime nativo), NÃO string ISO!
# ====================================================================
TTL_INDEXES = [
    {
        "collection": "refresh_tokens",
        "field": "created_at_dt",  # Campo datetime nativo (não ISO string)
        "seconds": 86400,  # 24 horas (sessões expiram após 1 dia)
        "name": "ttl_refresh_tokens",
        "description": "Purga refresh tokens após 24h (garantia extra ao expires_at)",
    },
    {
        "collection": "system_error_logs",
        "field": "timestamp_dt",  # Campo datetime nativo para TTL
        "seconds": 2592000,  # 30 dias
        "name": "ttl_system_error_logs",
        "description": "Purga logs de erro antigos após 30 dias",
    },
    {
        "collection": "emails",
        "field": "updated_at_dt",  # Campo datetime nativo para TTL
        "seconds": 604800,  # 7 dias
        "name": "ttl_email_drafts",
        "description": "Purga rascunhos de email antigos após 7 dias de inatividade",
        "partial_filter": {"status": "draft"},  # Só aplica a rascunhos
    },
]


async def cleanup_deprecated_indexes(db) -> dict:
    """
    Remove índices antigos/incorretos que podem causar erros.
    Executa antes de criar novos índices.
    """
    results = {"dropped": [], "errors": [], "not_found": []}
    
    for collection_name, index_names in DEPRECATED_INDEXES.items():
        collection = getattr(db, collection_name)
        
        try:
            # Obter índices existentes
            existing_indexes = await collection.index_information()
            
            for idx_name in index_names:
                if idx_name in existing_indexes:
                    try:
                        await collection.drop_index(idx_name)
                        results["dropped"].append(f"{collection_name}.{idx_name}")
                        logger.info(f"🗑️ Índice removido: {collection_name}.{idx_name}")
                    except OperationFailure as e:
                        # IndexNotFound (code 27) — índice já não existe, não é erro
                        if e.code == 27:
                            results["not_found"].append(f"{collection_name}.{idx_name}")
                            logger.debug(f"Índice {collection_name}.{idx_name} já não existe (code 27)")
                        else:
                            results["errors"].append(f"{collection_name}.{idx_name}: {str(e)}")
                            logger.error(f"Erro ao remover índice {collection_name}.{idx_name}: {e}")
                    except Exception as e:
                        results["errors"].append(f"{collection_name}.{idx_name}: {str(e)}")
                        logger.error(f"Erro ao remover índice {collection_name}.{idx_name}: {e}")
                else:
                    results["not_found"].append(f"{collection_name}.{idx_name}")
        except Exception as e:
            results["errors"].append(f"{collection_name}: {str(e)}")
            logger.error(f"Erro ao verificar índices em {collection_name}: {e}")
    
    if results["dropped"]:
        logger.info(f"✅ Limpeza de índices concluída: {len(results['dropped'])} removidos")
    
    return results


async def create_indexes(db) -> dict:
    """
    Cria índices optimizados nas colecções principais.
    
    Returns:
        dict: Resumo dos índices criados
    """
    # Primeiro, limpar índices antigos/incorretos
    cleanup_results = await cleanup_deprecated_indexes(db)
    
    results = {
        "created": [],
        "errors": [],
        "skipped": [],
        "cleanup": cleanup_results
    }
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'processes'
    # ====================================================================
    process_indexes = [
        # Índice no status - muito usado em filtros e dashboard
        {"keys": [("status", 1)], "name": "idx_status"},
        
        # Índice no nome do cliente - usado em pesquisa
        {"keys": [("client_name", 1)], "name": "idx_client_name"},
        
        # Índice no email do cliente - usado em lookup
        {"keys": [("client_email", 1)], "name": "idx_client_email"},
        
        # Índice na data de criação - usado para ordenação
        {"keys": [("created_at", -1)], "name": "idx_created_at_desc"},
        
        # Índice na data de actualização - usado para ordenação
        {"keys": [("updated_at", -1)], "name": "idx_updated_at_desc"},
        
        # Índice no consultor atribuído - usado em filtros por utilizador
        {"keys": [("assigned_consultor_id", 1)], "name": "idx_consultor"},
        
        # Índice no mediador atribuído
        {"keys": [("assigned_mediador_id", 1)], "name": "idx_mediador"},
        
        # Índice composto status + consultor - queries por utilizador
        {"keys": [("status", 1), ("assigned_consultor_id", 1)], "name": "idx_status_consultor"},
        
        # Índice composto status + mediador - queries por utilizador
        {"keys": [("status", 1), ("assigned_mediador_id", 1)], "name": "idx_status_mediador"},
        
        # Índice composto status + created_at - muito usado em listagens
        {"keys": [("status", 1), ("created_at", -1)], "name": "idx_status_created"},
        
        # Índice composto email + status - usado em lookup de processos
        {"keys": [("client_email", 1), ("status", 1)], "name": "idx_email_status"},
        
        # NOTA: NÃO criar índice em personal_data.nif — o campo está encriptado (Fernet).
        # Para pesquisa por NIF, usar o blind index idx_process_nif_hash (personal_data.nif_hash)
        # que é criado mais abaixo na secção de process_blind_indexes.
        # O idx_nif antigo está na lista DEPRECATED_INDEXES para ser removido.
        
        # Índice no tipo de processo
        {"keys": [("process_type", 1)], "name": "idx_process_type"},
        
        # Índice de texto para pesquisa full-text
        {
            "keys": [
                ("client_name", "text"), 
                ("client_email", "text"),
                ("personal_data.nif", "text")
            ], 
            "name": "idx_text_search"
        },
    ]
    
    for idx in process_indexes:
        await _create_index_safe(db.processes, idx, "processes", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'users'
    # ====================================================================
    user_indexes = [
        # Índice único no email - login
        {"keys": [("email", 1)], "name": "idx_email", "unique": True},
        
        # Índice no ID do utilizador
        {"keys": [("id", 1)], "name": "idx_user_id", "unique": True},
        
        # Índice no role - filtros por tipo de utilizador
        {"keys": [("role", 1)], "name": "idx_role"},
        
        # Índice composto role + is_active
        {"keys": [("role", 1), ("is_active", 1)], "name": "idx_role_active"},
    ]
    
    for idx in user_indexes:
        await _create_index_safe(db.users, idx, "users", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'system_error_logs'
    # ====================================================================
    log_indexes = [
        # Índice no timestamp - queries por período
        {"keys": [("timestamp", -1)], "name": "idx_timestamp_desc"},
        
        # Índice na severidade - filtros
        {"keys": [("severity", 1)], "name": "idx_severity"},
        
        # Índice no componente - filtros
        {"keys": [("component", 1)], "name": "idx_component"},
        
        # Índice composto para queries frequentes
        {"keys": [("timestamp", -1), ("severity", 1)], "name": "idx_time_severity"},
        
        # NOTA: TTL index movido para create_ttl_indexes() 
        # O TTL requer campo datetime nativo (timestamp_dt), não ISO string
    ]
    
    for idx in log_indexes:
        await _create_index_safe(db.system_error_logs, idx, "system_error_logs", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'properties' (Imóveis)
    # ====================================================================
    property_indexes = [
        {"keys": [("internal_reference", 1)], "name": "idx_internal_reference", "unique": True, "sparse": True},
        {"keys": [("status", 1)], "name": "idx_property_status"},
        {"keys": [("address.district", 1), ("address.municipality", 1)], "name": "idx_location"},
        {"keys": [("financials.asking_price", 1)], "name": "idx_asking_price"},
        {"keys": [("created_at", -1)], "name": "idx_created_desc"},
    ]
    
    for idx in property_indexes:
        await _create_index_safe(db.properties, idx, "properties", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'tasks'
    # ====================================================================
    task_indexes = [
        {"keys": [("process_id", 1)], "name": "idx_process_id"},
        {"keys": [("assigned_to", 1)], "name": "idx_assigned_to"},
        {"keys": [("status", 1)], "name": "idx_task_status"},
        {"keys": [("due_date", 1)], "name": "idx_due_date"},
        {"keys": [("status", 1), ("due_date", 1)], "name": "idx_status_due"},
    ]
    
    for idx in task_indexes:
        await _create_index_safe(db.tasks, idx, "tasks", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'chat_messages'
    # ====================================================================
    chat_message_indexes = [
        # Índice no sender_id - mensagens enviadas
        {"keys": [("sender_id", 1)], "name": "idx_sender"},
        
        # Índice no receiver_id - mensagens recebidas
        {"keys": [("receiver_id", 1)], "name": "idx_receiver"},
        
        # Índice no group_id - mensagens de grupo
        {"keys": [("group_id", 1)], "name": "idx_group"},
        
        # Índice na data de criação - ordenação
        {"keys": [("created_at", -1)], "name": "idx_msg_created_desc"},
        
        # Índice composto para conversas diretas
        {"keys": [("sender_id", 1), ("receiver_id", 1), ("created_at", -1)], "name": "idx_direct_conversation"},
        
        # Índice composto para mensagens não lidas
        {"keys": [("receiver_id", 1), ("read", 1)], "name": "idx_unread"},
        
        # Índice de texto para pesquisa
        {
            "keys": [("content", "text")],
            "name": "idx_content_text"
        },
    ]
    
    for idx in chat_message_indexes:
        await _create_index_safe(db.chat_messages, idx, "chat_messages", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'chat_groups'
    # ====================================================================
    chat_group_indexes = [
        # Índice no criador
        {"keys": [("created_by", 1)], "name": "idx_group_creator"},
        
        # Índice nos membros - para encontrar grupos do utilizador
        {"keys": [("members.user_id", 1)], "name": "idx_group_members"},
        
        # Índice na data de criação
        {"keys": [("created_at", -1)], "name": "idx_group_created_desc"},
    ]
    
    for idx in chat_group_indexes:
        await _create_index_safe(db.chat_groups, idx, "chat_groups", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'document_annotations' (Anotações Contextuais)
    # ====================================================================
    annotation_indexes = [
        # Índice no processo - queries por processo
        {"keys": [("process_id", 1)], "name": "idx_ann_process"},
        
        # Índice composto documento + processo - lookup principal
        {"keys": [("document_path", 1), ("process_id", 1)], "name": "idx_ann_document_process"},
        
        # Índice no autor - queries por utilizador
        {"keys": [("author_id", 1)], "name": "idx_ann_author"},
        
        # Índice no estado de resolução
        {"keys": [("resolved", 1)], "name": "idx_ann_resolved"},
        
        # Índice composto processo + página - ordenação por página
        {"keys": [("process_id", 1), ("page", 1)], "name": "idx_ann_process_page"},
    ]
    
    for idx in annotation_indexes:
        await _create_index_safe(db.document_annotations, idx, "document_annotations", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'clients' - BLIND INDEXES (RGPD)
    # ====================================================================
    # IMPORTANTE: Os campos NIF, telefone e email são encriptados com Fernet.
    # Para pesquisar, usamos BLIND INDEXES (hashes SHA-256 determinísticos).
    # Os índices DEVEM apontar para os campos _hash, NUNCA para os encriptados.
    # ====================================================================
    client_indexes = [
        # BLIND INDEXES - Pesquisa de dados encriptados
        # NIF hash - permite encontrar clientes por NIF sem expor o valor real
        {"keys": [("dados_pessoais.nif_hash", 1)], "name": "idx_client_nif_hash", "sparse": True},
        
        # Email hash - permite encontrar clientes por email
        {"keys": [("contacto.email_hash", 1)], "name": "idx_client_email_hash", "sparse": True},
        
        # Telefone hash - permite encontrar clientes por telefone
        {"keys": [("contacto.telefone_hash", 1)], "name": "idx_client_telefone_hash", "sparse": True},
        
        # Titular2 NIF hash - pesquisa do segundo titular
        {"keys": [("titular2_data.nif_hash", 1)], "name": "idx_client_titular2_nif_hash", "sparse": True},
        
        # Índices normais (não encriptados)
        {"keys": [("nome", 1)], "name": "idx_client_nome"},
        {"keys": [("id", 1)], "name": "idx_client_id", "unique": True},
        {"keys": [("assigned_to", 1)], "name": "idx_client_assigned_to", "sparse": True},
        {"keys": [("created_at", -1)], "name": "idx_client_created_desc"},
        {"keys": [("registration_completed", 1)], "name": "idx_client_registration"},
        
        # Índice composto para listagem de registos pendentes
        {"keys": [("registration_completed", 1), ("assigned_to", 1)], "name": "idx_client_pending_assignment"},
    ]
    
    for idx in client_indexes:
        await _create_index_safe(db.clients, idx, "clients", results)
    
    # ====================================================================
    # ÍNDICES ADICIONAIS PARA BLIND INDEXES EM 'processes'
    # ====================================================================
    # Os processos também têm dados encriptados com blind indexes
    process_blind_indexes = [
        # NIF hash no processo - pesquisa por NIF
        {"keys": [("personal_data.nif_hash", 1)], "name": "idx_process_nif_hash", "sparse": True},
        {"keys": [("personal_data.email_hash", 1)], "name": "idx_process_email_hash", "sparse": True},
    ]
    
    for idx in process_blind_indexes:
        await _create_index_safe(db.processes, idx, "processes", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'history' - HISTÓRICO DEDICADO
    # ====================================================================
    # CRÍTICO: Esta coleção armazena o histórico de processos de forma
    # separada do documento principal (Padrão "Dedicated Collection").
    # Isto evita o limite de 16MB do MongoDB e melhora a performance.
    # ====================================================================
    history_indexes = [
        # ÍNDICE PRINCIPAL: process_id + timestamp (ordenado desc)
        # Este é o índice MAIS CRÍTICO para queries de timeline
        # Permite buscar histórico de um processo de forma instantânea
        {"keys": [("process_id", 1), ("created_at", -1)], "name": "idx_history_process_time"},
        
        # Índice para queries por utilizador (atividade de um user)
        {"keys": [("user_id", 1), ("created_at", -1)], "name": "idx_history_user_time", "sparse": True},
        
        # Índice para filtrar por tipo de ação
        {"keys": [("action", 1), ("created_at", -1)], "name": "idx_history_action_time"},
        
        # Índice simples para timestamp (queries de data)
        {"keys": [("created_at", -1)], "name": "idx_history_created_desc"},
        
        # Índice para queries por campo alterado
        {"keys": [("field", 1)], "name": "idx_history_field", "sparse": True},
    ]
    
    for idx in history_indexes:
        await _create_index_safe(db.history, idx, "history", results)
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'announcements'
    # ====================================================================
    announcement_indexes = [
        {"keys": [("created_at", -1)], "name": "idx_announcements_created_desc"},
        {"keys": [("author_id", 1)], "name": "idx_announcements_author"},
    ]
    
    for idx in announcement_indexes:
        await _create_index_safe(db.announcements, idx, "announcements", results)

    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'emails' (Pacote FF — C1/C5)
    # ====================================================================
    # Lookup por id, listagem de mailbox, timeline de processo e
    # deduplicação IMAP (message_id + account).
    email_indexes = [
        {"keys": [("id", 1)], "name": "idx_emails_id", "unique": True},
        {
            "keys": [("company_id", 1), ("direction", 1), ("sent_at", -1)],
            "name": "idx_emails_mailbox",
        },
        {
            "keys": [("process_id", 1), ("sent_at", 1)],
            "name": "idx_emails_process_timeline",
        },
        {
            "keys": [("message_id", 1), ("account", 1)],
            "name": "idx_emails_message_dedup",
        },
    ]
    for idx in email_indexes:
        await _create_index_safe(db.emails, idx, "emails", results)

    # Resumo
    logger.info(
        f"Criação de índices concluída: "
        f"{len(results['created'])} criados, "
        f"{len(results['skipped'])} já existiam, "
        f"{len(results['errors'])} erros"
    )
    
    # ====================================================================
    # CRIAR ÍNDICES TTL (DATA LIFECYCLE MANAGEMENT)
    # ====================================================================
    ttl_results = await create_ttl_indexes(db)
    results["ttl"] = ttl_results
    
    return results


async def create_ttl_indexes(db) -> dict:
    """
    Cria índices TTL para Data Lifecycle Management.
    
    Os índices TTL automatizam a purga de dados efémeros sem necessidade
    de cron-jobs no backend.
    
    IMPORTANTE: TTL indexes requerem campos BSON Date (datetime nativo).
    Se o campo for ISO string, o TTL NÃO funciona!
    
    Returns:
        dict: Resumo dos índices TTL criados/erros
    """
    results = {
        "created": [],
        "skipped": [],
        "errors": [],
        "warnings": [],
    }
    
    for config in TTL_INDEXES:
        collection_name = config["collection"]
        field = config["field"]
        seconds = config["seconds"]
        name = config["name"]
        description = config.get("description", "")
        partial_filter = config.get("partial_filter")
        
        try:
            collection = db[collection_name]
            
            # Verificar se a coleção existe (tentando obter info)
            try:
                await collection.index_information()
            except Exception:
                logger.debug(f"Coleção {collection_name} ainda não existe, TTL será criado no primeiro insert")
                results["skipped"].append(f"{collection_name}.{name} (coleção não existe)")
                continue
            
            # Construir dict de índice para _create_index_safe
            idx_dict = {
                "keys": [(field, 1)],
                "name": name,
                "expireAfterSeconds": seconds,
            }
            if partial_filter:
                idx_dict["partialFilterExpression"] = partial_filter
            
            await _create_index_safe(collection, idx_dict, collection_name, results)
            
            # Log descritivo para TTL indexes
            label = f"{collection_name}.{name}"
            if label in results.get("created", []) or f"{label} (recriado)" in results.get("created", []):
                logger.info(
                    f"⏱️ Índice TTL criado: {label} "
                    f"(campo: {field}, TTL: {seconds}s / {seconds // 86400} dias) - {description}"
                )
                
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"{collection_name}.{name}")
            else:
                results["errors"].append(f"{collection_name}.{name}: {str(e)}")
                logger.error(f"Erro ao criar índice TTL {collection_name}.{name}: {e}")
    
    # Resumo TTL
    if results["created"]:
        logger.info(
            f"⏱️ TTL indexes: {len(results['created'])} criados, "
            f"{len(results['skipped'])} já existiam, "
            f"{len(results['errors'])} erros"
        )
    
    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'oauth_states' (Google OAuth)
    # ====================================================================
    oauth_indexes = [
        # Índice único no state — CSRF protection lookup
        {"keys": [("state", 1)], "name": "idx_oauth_state", "unique": True},
        
        # TTL no created_at — limpar states velhos automaticamente (10 min)
        {
            "keys": [("created_at", 1)],
            "name": "idx_oauth_state_ttl",
            "expireAfterSeconds": 600,
        },
    ]
    
    for idx in oauth_indexes:
        await _create_index_safe(db.oauth_states, idx, "oauth_states", results)

    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'company_email_configs'
    # ====================================================================
    company_email_indexes = [
        {"keys": [("company_name", 1)], "name": "idx_company_name", "unique": True},
    ]
    for idx in company_email_indexes:
        await _create_index_safe(db.company_email_configs, idx, "company_email_configs", results)

    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'user_company_roles' (M:N User-Company)
    # ====================================================================
    # Pacote EA — vários cargos na mesma empresa: unique é (user_id, company_id, role).
    # Drop defensivo de qualquer unique residual só em (user_id, company_id).
    try:
        existing_ucr_indexes = await db.user_company_roles.index_information()
        for existing_name, existing_info in existing_ucr_indexes.items():
            if existing_name == "_id_":
                continue
            existing_key = list(existing_info.get("key", []))
            if existing_info.get("unique") and existing_key == [
                ("user_id", 1),
                ("company_id", 1),
            ]:
                await db.user_company_roles.drop_index(existing_name)
                logger.info(
                    "Índice único restritivo removido (Pacote EA): "
                    f"user_company_roles.{existing_name}"
                )
    except Exception as drop_err:
        logger.warning(
            f"Não foi possível inspeccionar índices UCR para Pacote EA: {drop_err}"
        )

    user_company_role_indexes = [
        # Pacote FF — lookup único pelo id da associação user↔empresa
        {"keys": [("id", 1)], "name": "idx_ucr_id", "unique": True},
        # Índice composto único — um user pode ter vários cargos na mesma
        # empresa; só a combinação exacta user+empresa+cargo é única.
        {
            "keys": [("user_id", 1), ("company_id", 1), ("role", 1)],
            "name": "idx_user_company_role_unique",
            "unique": True,
        },
        # Índice no company_id — queries por empresa
        {"keys": [("company_id", 1)], "name": "idx_company_id"},
        # Índice para lookup rápido da empresa padrão
        {"keys": [("user_id", 1), ("is_default", 1)], "name": "idx_user_default", "sparse": True},
    ]
    for idx in user_company_role_indexes:
        await _create_index_safe(db.user_company_roles, idx, "user_company_roles", results)

    # ====================================================================
    # ÍNDICES PARA COLECÇÃO 'user_email_configs' (Multi-Empresa + Multi-Conta)
    # ====================================================================
    # Unicidade: (user_id, company_id, email_address) — várias contas por perfil.
    try:
        await db.user_email_configs.drop_index("idx_user_company_email_unique")
        logger.info("Índice antigo idx_user_company_email_unique removido (DN.4)")
    except Exception:
        pass
    user_email_config_indexes = [
        {
            "keys": [("user_id", 1), ("company_id", 1), ("email_address", 1)],
            "name": "idx_user_company_email_address_unique",
            "unique": True,
        },
        {"keys": [("user_id", 1)], "name": "idx_user_email_user_id"},
        {"keys": [("company_id", 1)], "name": "idx_user_email_company_id"},
        {
            "keys": [("user_id", 1), ("company_id", 1), ("is_primary", 1)],
            "name": "idx_user_email_primary",
        },
    ]
    for idx in user_email_config_indexes:
        await _create_index_safe(db.user_email_configs, idx, "user_email_configs", results)

    return results


async def get_index_stats(db) -> dict:
    """
    Obtém estatísticas dos índices existentes.
    """
    stats = {}
    
    collections = [
        "processes",
        "clients",
        "users",
        "system_error_logs",
        "properties",
        "tasks",
        "chat_messages",
        "chat_groups",
        "history",
        "compliance_audit_logs",
        "emails",
        "user_company_roles",
        "notifications",
        "companies",
    ]
    
    for collection_name in collections:
        try:
            collection = getattr(db, collection_name)
            indexes = await collection.index_information()
            stats[collection_name] = {
                "count": len(indexes),
                "indexes": list(indexes.keys())
            }
        except Exception as e:
            stats[collection_name] = {"error": str(e)}
    
    return stats
