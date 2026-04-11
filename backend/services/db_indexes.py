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
    ],
    "system_error_logs": [
        "idx_ttl",  # Índice TTL antigo (90 dias) em campo ISO string - não funciona. Substituído por ttl_system_error_logs
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
        
        # Índice no NIF para pesquisa rápida
        {"keys": [("personal_data.nif", 1)], "name": "idx_nif", "sparse": True},
        
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
        try:
            await db.processes.create_index(
                idx["keys"],
                name=idx["name"],
                sparse=idx.get("sparse", False),
                background=True  # Não bloqueia operações durante criação
            )
            results["created"].append(f"processes.{idx['name']}")
            logger.info(f"Índice criado: processes.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"processes.{idx['name']}")
            else:
                results["errors"].append(f"processes.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice processes.{idx['name']}: {e}")
    
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
        try:
            await db.users.create_index(
                idx["keys"],
                name=idx["name"],
                unique=idx.get("unique", False),
                sparse=idx.get("sparse", False),
                background=True
            )
            results["created"].append(f"users.{idx['name']}")
            logger.info(f"Índice criado: users.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"users.{idx['name']}")
            else:
                results["errors"].append(f"users.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice users.{idx['name']}: {e}")
    
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
        try:
            create_options = {
                "name": idx["name"],
                "background": True
            }
            if "expireAfterSeconds" in idx:
                create_options["expireAfterSeconds"] = idx["expireAfterSeconds"]
            
            await db.system_error_logs.create_index(idx["keys"], **create_options)
            results["created"].append(f"system_error_logs.{idx['name']}")
            logger.info(f"Índice criado: system_error_logs.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"system_error_logs.{idx['name']}")
            else:
                results["errors"].append(f"system_error_logs.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice system_error_logs.{idx['name']}: {e}")
    
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
        try:
            await db.properties.create_index(
                idx["keys"],
                name=idx["name"],
                unique=idx.get("unique", False),
                sparse=idx.get("sparse", False),
                background=True
            )
            results["created"].append(f"properties.{idx['name']}")
            logger.info(f"Índice criado: properties.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"properties.{idx['name']}")
            else:
                results["errors"].append(f"properties.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice properties.{idx['name']}: {e}")
    
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
        try:
            await db.tasks.create_index(
                idx["keys"],
                name=idx["name"],
                background=True
            )
            results["created"].append(f"tasks.{idx['name']}")
            logger.info(f"Índice criado: tasks.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"tasks.{idx['name']}")
            else:
                results["errors"].append(f"tasks.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice tasks.{idx['name']}: {e}")
    
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
        try:
            await db.chat_messages.create_index(
                idx["keys"],
                name=idx["name"],
                sparse=idx.get("sparse", False),
                background=True
            )
            results["created"].append(f"chat_messages.{idx['name']}")
            logger.info(f"Índice criado: chat_messages.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"chat_messages.{idx['name']}")
            else:
                results["errors"].append(f"chat_messages.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice chat_messages.{idx['name']}: {e}")
    
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
        try:
            await db.chat_groups.create_index(
                idx["keys"],
                name=idx["name"],
                background=True
            )
            results["created"].append(f"chat_groups.{idx['name']}")
            logger.info(f"Índice criado: chat_groups.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"chat_groups.{idx['name']}")
            else:
                results["errors"].append(f"chat_groups.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice chat_groups.{idx['name']}: {e}")
    
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
        try:
            await db.document_annotations.create_index(
                idx["keys"],
                name=idx["name"],
                background=True
            )
            results["created"].append(f"document_annotations.{idx['name']}")
            logger.info(f"Índice criado: document_annotations.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"document_annotations.{idx['name']}")
            else:
                results["errors"].append(f"document_annotations.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice document_annotations.{idx['name']}: {e}")
    
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
        try:
            await db.clients.create_index(
                idx["keys"],
                name=idx["name"],
                unique=idx.get("unique", False),
                sparse=idx.get("sparse", False),
                background=True
            )
            results["created"].append(f"clients.{idx['name']}")
            logger.info(f"Índice criado: clients.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"clients.{idx['name']}")
            else:
                results["errors"].append(f"clients.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice clients.{idx['name']}: {e}")
    
    # ====================================================================
    # ÍNDICES ADICIONAIS PARA BLIND INDEXES EM 'processes'
    # ====================================================================
    # Os processos também têm dados encriptados com blind indexes
    process_blind_indexes = [
        # NIF hash no processo - pesquisa por NIF
        {"keys": [("personal_data.nif_hash", 1)], "name": "idx_process_nif_hash", "sparse": True},
    ]
    
    for idx in process_blind_indexes:
        try:
            await db.processes.create_index(
                idx["keys"],
                name=idx["name"],
                sparse=idx.get("sparse", False),
                background=True
            )
            results["created"].append(f"processes.{idx['name']}")
            logger.info(f"Índice criado: processes.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"processes.{idx['name']}")
            else:
                results["errors"].append(f"processes.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice processes.{idx['name']}: {e}")
    
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
        try:
            await db.history.create_index(
                idx["keys"],
                name=idx["name"],
                sparse=idx.get("sparse", False),
                background=True
            )
            results["created"].append(f"history.{idx['name']}")
            logger.info(f"Índice criado: history.{idx['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                results["skipped"].append(f"history.{idx['name']}")
            else:
                results["errors"].append(f"history.{idx['name']}: {str(e)}")
                logger.error(f"Erro ao criar índice history.{idx['name']}: {e}")
    
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
            
            # Construir opções do índice
            index_options = {
                "name": name,
                "expireAfterSeconds": seconds,
                "background": True,
            }
            
            # Adicionar partial filter expression se especificado
            if partial_filter:
                index_options["partialFilterExpression"] = partial_filter
            
            # Criar índice TTL
            await collection.create_index(
                [(field, 1)],
                **index_options
            )
            
            results["created"].append(f"{collection_name}.{name}")
            logger.info(
                f"⏱️ Índice TTL criado: {collection_name}.{name} "
                f"(campo: {field}, TTL: {seconds}s / {seconds // 86400} dias) - {description}"
            )
            
        except OperationFailure as e:
            error_code = e.code
            
            # Código 85: Index already exists with different options
            # Código 86: Index already exists with same name but different key
            if error_code == 85 or error_code == 86:
                # O índice já existe mas com parâmetros diferentes
                logger.warning(
                    f"⚠️ Índice TTL {collection_name}.{name} já existe com parâmetros diferentes. "
                    f"Tentando remover e recriar..."
                )
                
                try:
                    # Remover índice antigo e recriar
                    await collection.drop_index(name)
                    logger.info(f"🗑️ Índice antigo removido: {collection_name}.{name}")
                    
                    # Recriar com novos parâmetros
                    await collection.create_index(
                        [(field, 1)],
                        **index_options
                    )
                    results["created"].append(f"{collection_name}.{name} (recriado)")
                    logger.info(f"✅ Índice TTL recriado: {collection_name}.{name}")
                    
                except Exception as retry_error:
                    results["errors"].append(
                        f"{collection_name}.{name}: Falha ao recriar: {str(retry_error)}"
                    )
                    logger.error(
                        f"Erro ao recriar índice TTL {collection_name}.{name}: {retry_error}"
                    )
            elif "already exists" in str(e).lower():
                results["skipped"].append(f"{collection_name}.{name}")
            else:
                results["errors"].append(f"{collection_name}.{name}: {str(e)}")
                logger.error(f"Erro ao criar índice TTL {collection_name}.{name}: {e}")
                
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
    
    return results


async def get_index_stats(db) -> dict:
    """
    Obtém estatísticas dos índices existentes.
    """
    stats = {}
    
    collections = ["processes", "clients", "users", "system_error_logs", "properties", "tasks", "chat_messages", "chat_groups", "history", "compliance_audit_logs"]
    
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
