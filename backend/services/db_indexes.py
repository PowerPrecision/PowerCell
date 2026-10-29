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
from pymongo.errors import AutoReconnect, OperationFailure

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
        elif error_code == 11000 and idx.get("unique"):
            # Há duplicados na base de dados: o índice único não se constrói. NÃO é uma avaria
            # da aplicação — a criação repete-se em cada arranque até a limpeza estar feita.
            results["errors"].append(f"{label}: duplicados existentes — {str(e)[:160]}")
            logger.error(
                "❌ Índice único %s NÃO criado: existem documentos duplicados. Correr "
                "`python -m scripts.resolve_client_duplicates` (descreve) e, depois de rever, "
                "`--aplicar`; o índice nasce no arranque seguinte.", label,
            )
        else:
            results["errors"].append(f"{label}: {str(e)}")
            logger.error(f"Erro ao criar índice {label}: {e}")

    except Exception as e:
        if "already exists" in str(e).lower():
            results["skipped"].append(label)
        else:
            results["errors"].append(f"{label}: {str(e)}")
            logger.error(f"Erro ao criar índice {label}: {e}")
            if isinstance(e, AutoReconnect):
                results["indisponivel"] = True


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
#: Quanto tempo um rascunho de email sobrevive SEM ser tocado (decisão do dono
#: do produto, Out 2026: era 7 dias; no mínimo 15). Os rascunhos automáticos —
#: confirmações de receção de documentos, lembretes — esperam por uma pessoa
#: que pode estar de férias ou ocupada; ao fim de 7 dias desapareciam sem
#: ninguém os ter visto. É UMA constante porque o índice e o diagnóstico
#: (`diagnostics_ttl`) têm de dizer o mesmo número.
RASCUNHOS_TTL_DIAS = 15
RASCUNHOS_TTL_SEGUNDOS = RASCUNHOS_TTL_DIAS * 86400

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
        "seconds": RASCUNHOS_TTL_SEGUNDOS,
        "name": "ttl_email_drafts",
        "description": f"Purga rascunhos de email antigos após {RASCUNHOS_TTL_DIAS} dias de inatividade",
        "partial_filter": {"status": "draft"},  # Só aplica a rascunhos
    },
    {
        # Fila do Processador (Lote 2, ponto 1). Uma fila sem purga cresce
        # para sempre com tarefas já concluídas — e o épico de custos do
        # Mongo (D-13) existe precisamente por colecções assim. `_dt` é
        # datetime NATIVO de propósito: o TTL não funciona sobre uma string
        # ISO (foi o que inutilizou o `idx_ttl` descontinuado).
        "collection": "task_queue",
        "field": "finished_at_dt",
        "seconds": 604800,  # 7 dias
        "name": "ttl_task_queue",
        "description": "Purga tarefas terminadas da fila após 7 dias",
    },
    {
        # Travão do `/portal/{client_id}/verify` (D-31, remate). O `client_id`
        # é escolhido por quem pergunta, logo cada id inventado deixava um
        # documento para sempre. `seconds: 0` = expira no INSTANTE de
        # `expire_at` (o serviço grava-o já com a margem: ver
        # `portal_security.VERIFY_ATTEMPTS_TTL_MINUTES`, maior que o bloqueio).
        # Datetime nativo, nunca a string ISO de `last_attempt_at`.
        "collection": "portal_verify_attempts",
        "field": "expire_at",
        "seconds": 0,
        "name": "ttl_portal_verify_attempts",
        "description": "Purga tentativas de verificação do Portal na data de expiração do registo",
    },
    {
        # O login do Portal por EMAIL (`portal_brute_force`): a identidade é o
        # email, também escolhido por quem pergunta. Mesmo campo e mesmo
        # `seconds: 0` do `verify` — o prazo vive em `expira_em`.
        "collection": "portal_login_attempts",
        "field": "expire_at",
        "seconds": 0,
        "name": "ttl_portal_login_attempts",
        "description": "Purga tentativas de login do Portal por email na data de expiração do registo",
    },
    {
        # Log da IA do processo (`process_ai_log`): 12 meses. `expire_at` é um
        # datetime NATIVO gravado em cada linha (o TTL ignora strings ISO);
        # o prazo vive em `process_ai_log.RETENCAO_DIAS`.
        "collection": "process_ai_log",
        "field": "expire_at",
        "seconds": 0,
        "name": "ttl_process_ai_log",
        "description": "Purga o Log da IA do processo na data de expiração da linha (12 meses)",
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


# ====================================================================
# DEFINIÇÕES DOS ÍNDICES (D-10 fechada, Out 2026)
# ====================================================================
# As definições vivem num REGISTO ao nível do módulo — `INDEX_DEFINITIONS`, colecção →
# lista de índices — e `create_indexes` limita-se a iterá-lo. Antes eram 34 listas locais de
# uma função de ~750 linhas, sem forma de um teste (ou de um script de diagnóstico) as obter
# sem executar a função contra uma base de dados; o `test_db_indexes.py` chegou a manter uma
# CÓPIA escrita à mão, e foi assim que um índice pôde faltar em produção sem um teste vermelho.
#
# Um índice de que a aplicação depende declara-se AQUI, nunca num passo de operações.
# O registo é de ordem estável: dentro de cada colecção, a ordem de declaração.
INDEX_DEFINITIONS: dict[str, list[dict]] = {}


def _definir(colecao: str, indices: list[dict]) -> None:
    """Acrescenta índices à colecção (várias declarações da mesma colecção somam-se)."""
    INDEX_DEFINITIONS.setdefault(colecao, []).extend(indices)


# Pastas de topo criadas à mão no Explorador: dono (rede) de uma pasta que não é de nenhum
# cliente. A leitura é por caminho e o caminho é único (a criação é idempotente).
_definir(
    "s3_explorer_folders",
    [{"keys": [("path", 1)], "name": "idx_s3_explorer_folders_path", "unique": True}],
)

# Telegram: uma ligação por utilizador; a conversa (chat_id) procura-se no /parar e na troca de conta.
_definir(
    "telegram_links",
    [
        {"keys": [("user_id", 1)], "name": "idx_telegram_links_user", "unique": True},
        {"keys": [("chat_id", 1)], "name": "idx_telegram_links_chat"},
    ],
)
# Códigos de ligação de uso único: procuram-se pelo hash e caducam sozinhos.
_definir(
    "telegram_link_tokens",
    [
        {"keys": [("token_hash", 1)], "name": "idx_telegram_tokens_hash", "unique": True},
        {"keys": [("expira_em", 1)], "name": "idx_telegram_tokens_ttl", "expireAfterSeconds": 3600},
    ],
)
# Fila do Telegram: no máximo UM grupo «pendente» por (utilizador, assunto) — é o que junta a
# rajada de avisos de um processo indexado numa só mensagem. A fila é técnica e esvazia-se sozinha.
_definir(
    "telegram_outbox",
    [
        {
            "keys": [("user_id", 1), ("chave", 1)],
            "name": "idx_telegram_outbox_grupo_pendente",
            "unique": True,
            "partialFilterExpression": {"status": "pendente"},
        },
        {"keys": [("status", 1), ("enviar_apos", 1)], "name": "idx_telegram_outbox_envio"},
        {"keys": [("criado_em", 1)], "name": "idx_telegram_outbox_ttl", "expireAfterSeconds": 14 * 86400},
    ],
)

# Log da IA do processo: a única leitura é por `process_id`, mais recente primeiro.
_definir(
    "process_ai_log",
    [{"keys": [("process_id", 1), ("created_at", -1)], "name": "idx_process_ai_log_processo"}],
)

# ====================================================================
# MÓDULO INDEX (Lote 12) — metadados profissionais, entidades, alertas, jobs
# ====================================================================
# Um documento de metadados por processo; a pesquisa por entidade fecha na rede
# (`network_id`) — o trabalhador nunca atravessa redes, só a entidade (Decisão A).
_definir(
    "process_professional_metadata",
    [
        {"keys": [("process_id", 1)], "name": "idx_prof_meta_processo", "unique": True},
        {"keys": [("network_id", 1), ("jobs.employer_nif.value", 1)], "name": "idx_prof_meta_rede_nif"},
        {"keys": [("network_id", 1), ("has_pending_review", 1)], "name": "idx_prof_meta_rede_revisao"},
    ],
)
# Projecção pesquisável por DOCUMENTO (recibos, declarações de efetividade, extratos): uma linha por
# ficheiro analisado. A pesquisa avançada filtra primeiro aqui (tipo + valor/banco/período) e só depois
# resolve o processo e a fronteira de rede, por isso os índices começam sempre pelo `doc_type`.
_definir(
    "process_index_documents",
    [
        {"keys": [("id", 1)], "name": "idx_index_docs_id", "unique": True},
        {"keys": [("process_id", 1)], "name": "idx_index_docs_processo"},
        {"keys": [("doc_type", 1), ("net_salary_num", 1)], "name": "idx_index_docs_valor"},
        {"keys": [("doc_type", 1), ("bank_key", 1)], "name": "idx_index_docs_banco"},
        {"keys": [("doc_type", 1), ("period", -1)], "name": "idx_index_docs_periodo"},
        # arquivo histórico (importação de ZIPs): a pesquisa filtra por rede, o «desfazer» por importação
        {"keys": [("historical", 1), ("network_id", 1), ("doc_type", 1)], "name": "idx_index_docs_historico"},
        {"keys": [("import_id", 1)], "name": "idx_index_docs_importacao", "sparse": True},
    ],
)
# Veredictos negativos já pagos do arquivo histórico (para uma reexecução não repetir a chamada à IA).
_definir(
    "index_historical_seen",
    [
        {"keys": [("id", 1)], "name": "idx_hist_seen_id", "unique": True},
        {"keys": [("import_id", 1)], "name": "idx_hist_seen_importacao"},
    ],
)
# Directório global de entidades patronais: o NIF é a chave.
_definir(
    "employers",
    [
        {"keys": [("nif", 1)], "name": "idx_employers_nif", "unique": True},
        {"keys": [("name_normalizado", 1)], "name": "idx_employers_nome"},
    ],
)
# Alertas da matriz: um documento por alerta; lidos por processo, e substituídos por `run_id`.
_definir(
    "process_index_alerts",
    [
        {"keys": [("process_id", 1), ("created_at", -1)], "name": "idx_index_alerts_processo"},
        {"keys": [("process_id", 1), ("run_id", 1)], "name": "idx_index_alerts_run"},
    ],
)
# Um job do Index activo por (processo, tipo) — a lição do D-29. `index_job_key` só existe
# enquanto o job corre (é retirado ao terminar), logo o índice parcial só vê os activos.
_definir(
    "task_logs",
    [
        {
            "keys": [("index_job_key", 1)],
            "name": "idx_index_job_activo_unico",
            "unique": True,
            "partialFilterExpression": {"index_job_key": {"$type": "string"}},
        },
    ],
)

# Pedidos de alteração de atribuição do Index (Out 2026): a chefia lista os pendentes, mais recentes
# primeiro; o Index procura o seu pendente de um processo (um por pessoa e processo).
_definir(
    "index_assignment_requests",
    [
        {"keys": [("estado", 1), ("created_at", -1)], "name": "idx_pedidos_atribuicao_estado"},
        {"keys": [("process_id", 1), ("requested_by", 1), ("estado", 1)], "name": "idx_pedidos_atribuicao_processo"},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'processes'
# ====================================================================
_definir(
    "processes",
    [
        # Módulo Index (Lote 12): as duas abas do dashboard («Fila de Espera» e «Revisões Pendentes»).
        # Prefixo mais presente primeiro: a rede abre sempre a consulta.
        {"keys": [("network_id", 1), ("index_status", 1), ("created_at", -1)], "name": "idx_index_fila"},
        {"keys": [("network_id", 1), ("has_pending_review", 1), ("indexed_at", -1)], "name": "idx_index_revisoes"},

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
        # Gestor de Ficheiros S3 (Épico 10): a ponte pasta → rede. A
        # listagem da raiz resolve TODAS as pastas da página numa só query
        # `{"s3_folder": {"$in": [...]}}`; sem índice, cada navegação no
        # Explorador varria a colecção inteira (12.450 pastas em produção).
        {"keys": [("s3_folder", 1)], "name": "idx_s3_folder"},
        # O carimbo de rede é lido em quase todas as listagens desde o
        # Lote 4 e nunca teve índice próprio.
        {"keys": [("network_id", 1)], "name": "idx_network_id"},
        # O âmbito COMPLETO do BI: rede + não eliminado + fase. É a
        # combinação com que `stats_funnel`, `stats_branches` e
        # `stats_overview` abrem as agregações, e estava registada no
        # worklog como tarefa MANUAL de produção — que é a forma certa de
        # se esquecer. Declarada aqui, nasce no arranque como as outras.
        # A ordem é do prefixo mais presente para o menos: `network_id`
        # está em todas as consultas, `status` só em algumas, e é isso
        # que deixa o Mongo reaproveitar o índice para as duas primeiras
        # chaves sem precisar de um segundo.
        {
            "keys": [("network_id", 1), ("is_deleted", 1), ("status", 1)],
            "name": "idx_network_scope",
        },
        
        # Índice de texto para pesquisa full-text
        {
            "keys": [
                ("client_name", "text"), 
                ("client_email", "text"),
                ("personal_data.nif", "text")
            ], 
            "name": "idx_text_search"
        },
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'users'
# ====================================================================
_definir(
    "users",
    [
        # Índice único no email - login
        {"keys": [("email", 1)], "name": "idx_email", "unique": True},
        
        # Índice no ID do utilizador
        {"keys": [("id", 1)], "name": "idx_user_id", "unique": True},
        
        # Índice no role - filtros por tipo de utilizador
        {"keys": [("role", 1)], "name": "idx_role"},
        
        # Índice composto role + is_active
        {"keys": [("role", 1), ("is_active", 1)], "name": "idx_role_active"},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'system_error_logs'
# ====================================================================
_definir(
    "system_error_logs",
    [
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
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'properties' (Imóveis)
# ====================================================================
_definir(
    "properties",
    [
        {"keys": [("internal_reference", 1)], "name": "idx_internal_reference", "unique": True, "sparse": True},
        {"keys": [("status", 1)], "name": "idx_property_status"},
        {"keys": [("address.district", 1), ("address.municipality", 1)], "name": "idx_location"},
        {"keys": [("financials.asking_price", 1)], "name": "idx_asking_price"},
        {"keys": [("created_at", -1)], "name": "idx_created_desc"},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'tasks'
# ====================================================================
_definir(
    "tasks",
    [
        {"keys": [("process_id", 1)], "name": "idx_process_id"},
        {"keys": [("assigned_to", 1)], "name": "idx_assigned_to"},
        {"keys": [("status", 1)], "name": "idx_task_status"},
        {"keys": [("due_date", 1)], "name": "idx_due_date"},
        {"keys": [("status", 1), ("due_date", 1)], "name": "idx_status_due"},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'chat_messages'
# ====================================================================
_definir(
    "chat_messages",
    [
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
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'chat_groups'
# ====================================================================
_definir(
    "chat_groups",
    [
        # Índice no criador
        {"keys": [("created_by", 1)], "name": "idx_group_creator"},
        
        # Índice nos membros - para encontrar grupos do utilizador
        {"keys": [("members.user_id", 1)], "name": "idx_group_members"},
        
        # Índice na data de criação
        {"keys": [("created_at", -1)], "name": "idx_group_created_desc"},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'document_annotations' (Anotações Contextuais)
# ====================================================================
_definir(
    "document_annotations",
    [
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
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'clients' - BLIND INDEXES (RGPD)
# ====================================================================
# IMPORTANTE: Os campos NIF, telefone e email são encriptados com Fernet.
# Para pesquisar, usamos BLIND INDEXES (hashes SHA-256 determinísticos).
# Os índices DEVEM apontar para os campos _hash, NUNCA para os encriptados.
# ====================================================================
_definir(
    "clients",
    [
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
    ],
)

# ====================================================================
# IDENTIDADE GLOBAL DO CLIENTE (D-42/D-40, Out 2026)
# ====================================================================
# NIF e Email definem o cliente único em TODA a base de dados (o telemóvel não
# conta). A guarda da aplicação (`client_uniqueness`) evita chegar aqui; estes dois
# índices são a última linha de defesa contra a corrida entre dois pedidos.
#
# PORQUE É PARCIAL: um cliente ELIMINADO não pode bloquear a recriação (`is_deleted`
# `True` fica fora), e só entra quem TEM hash (`$gt: ""` exclui ausente, `null` e
# vazio — `{"$type": "string"}` deixava passar a string vazia). O MongoDB não aceita
# `$ne` num filtro parcial; `$in: [False, None]` cobre ausente, `null` e `False`
# (verificado contra um mongod 7).
#
# PORQUE É UM ÍNDICE À PARTE dos `idx_client_*_hash` acima: o MongoDB admite dois
# índices com a mesma chave e opções diferentes, e substituir o existente passava
# pelo «drop & recreate» do `_create_index_safe` — que, com duplicados na base,
# deixava a colecção SEM índice de pesquisa. Assim, enquanto houver duplicados esta
# criação falha com um erro que diz o que fazer e tudo o resto continua a funcionar.
# Ordem de operação: `scripts/resolve_client_duplicates.py --aplicar` PRIMEIRO, depois
# o arranque seguinte cria os índices.
_FILTRO_DE_CLIENTE_ACTIVO = {"is_deleted": {"$in": [False, None]}}
_definir(
    "clients",
    [
        {
            "keys": [("dados_pessoais.nif_hash", 1)],
            "name": "idx_client_nif_hash_unico",
            "unique": True,
            "partialFilterExpression": {
                **_FILTRO_DE_CLIENTE_ACTIVO,
                "dados_pessoais.nif_hash": {"$gt": ""},
            },
        },
        {
            "keys": [("contacto.email_hash", 1)],
            "name": "idx_client_email_hash_unico",
            "unique": True,
            "partialFilterExpression": {
                **_FILTRO_DE_CLIENTE_ACTIVO,
                "contacto.email_hash": {"$gt": ""},
            },
        },
    ],
)

# ====================================================================
# ÍNDICES ADICIONAIS PARA BLIND INDEXES EM 'processes'
# ====================================================================
# Os processos também têm dados encriptados com blind indexes
_definir(
    "processes",
    [
        # NIF hash no processo - pesquisa por NIF
        {"keys": [("personal_data.nif_hash", 1)], "name": "idx_process_nif_hash", "sparse": True},
        {"keys": [("personal_data.email_hash", 1)], "name": "idx_process_email_hash", "sparse": True},
    ],
)

# ====================================================================
# PACOTE 10 — ÍNDICES PARA COLECÇÃO 'task_logs' (MONITOR GLOBAL)
# ====================================================================
# Os task_logs alimentam o widget "Processos em Segundo Plano"
# (GET /tasks/active faz polling 5s/30s por utilizador). Sem índice,
# cada poll seria um collection scan.
_definir(
    "task_logs",
    [
        # Query principal de get_active_tasks: user + status
        {"keys": [("user_id", 1), ("status", 1)], "name": "idx_task_logs_user_status"},
        # Limpeza TTL (cleanup_old_tasks): status + acknowledged/completed
        {"keys": [
            ("status", 1), ("acknowledged_at", 1), ("completed_at", 1)
        ], "name": "idx_task_logs_cleanup"},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'history' - HISTÓRICO DEDICADO
# ====================================================================
# CRÍTICO: Esta coleção armazena o histórico de processos de forma
# separada do documento principal (Padrão "Dedicated Collection").
# Isto evita o limite de 16MB do MongoDB e melhora a performance.
# ====================================================================
_definir(
    "history",
    [
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
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'announcements'
# ====================================================================
_definir(
    "announcements",
    [
        {"keys": [("created_at", -1)], "name": "idx_announcements_created_desc"},
        {"keys": [("author_id", 1)], "name": "idx_announcements_author"},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'emails' (Pacote FF — C1/C5)
# ====================================================================
# Lookup por id, listagem de mailbox, timeline de processo e
# deduplicação IMAP (message_id + account).
_definir(
    "emails",
    [
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
        # Um rascunho de confirmação de receção PENDENTE por (processo, tipo
        # de documento): fecha a corrida de dois uploads simultâneos. Parcial
        # — só abrange esses rascunhos, pelo que não toca nos emails que já lá
        # estão (nenhum tem `auto_draft_kind`).
        {
            "keys": [("process_id", 1), ("auto_draft_kind", 1), ("auto_draft_doc_type", 1)],
            "name": "idx_emails_receipt_draft_pending",
            "unique": True,
            "partialFilterExpression": {
                "status": "draft", "auto_draft_kind": "document_receipt",
            },
        },
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'oauth_states' (Google OAuth)
# ====================================================================
_definir(
    "oauth_states",
    [
        # Índice único no state — CSRF protection lookup
        {"keys": [("state", 1)], "name": "idx_oauth_state", "unique": True},
        
        # TTL no created_at — limpar states velhos automaticamente (10 min)
        {
            "keys": [("created_at", 1)],
            "name": "idx_oauth_state_ttl",
            "expireAfterSeconds": 600,
        },
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'company_email_configs'
# ====================================================================
_definir(
    "company_email_configs",
    [
        {"keys": [("company_name", 1)], "name": "idx_company_name", "unique": True},
    ],
)

_definir(
    "user_company_roles",
    [
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
    ],
)

_definir(
    "user_email_configs",
    [
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
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'task_queue' (fila do Processador — Lote 2)
# ====================================================================
# Declarados AQUI e não num passo de operações: um índice criado à mão
# em produção deixa dev e CI sem ele, que é onde as consultas se
# escrevem (lição de Set 2026, `idx_network_scope`).
#
# A ordem das chaves do índice da reclamação segue a consulta do
# `get_next_task`: `status` é o prefixo mais selectivo e mais presente,
# `disponivel_em` o intervalo, e `created_at` serve o `sort` FIFO sem
# um segundo índice.
_definir(
    "task_queue",
    [
        {
            "keys": [("status", 1), ("disponivel_em", 1), ("created_at", 1)],
            "name": "idx_task_queue_reclamar",
        },
        # Pedidos de execução forçada por job (painel «Estado do Motor»).
        {"keys": [("type", 1), ("status", 1)], "name": "idx_task_queue_tipo_estado"},
        {"keys": [("id", 1)], "name": "idx_task_queue_id", "unique": True},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'job_schedule_marks' (agenda dos relatórios)
# ====================================================================
# Uma marca por job: é o que impede o relatório semanal de sair 24
# vezes à segunda-feira (Lote 2, ponto 1).
_definir(
    "job_schedule_marks",
    [{"keys": [("chave", 1)], "name": "idx_job_schedule_chave", "unique": True}],
)

# ====================================================================
# ÍNDICES DO RELATÓRIO EXECUTIVO (Bloco 4, pontos 13 e 16)
# ====================================================================
# As agregações de `services/executive_report.py` abrem com um `$match`
# sobre estes campos: sem eles varriam `tasks` inteira a cada clique em
# «Actualizar». O histórico já tem `idx_history_user_time`
# (user_id, created_at), que serve a pergunta «o que fez cada pessoa».
#   - concluídas no período, por quem concluiu;
#   - carga em aberto: atribuídas a X e criadas antes do fim.
_definir(
    "tasks",
    [
        {"keys": [("completed_by", 1), ("completed_at", 1)], "name": "idx_tasks_completed_by_time"},
        {"keys": [("assigned_to", 1), ("created_at", 1)], "name": "idx_tasks_assigned_created"},
    ],
)

# Calendário do Dashboard (ponto 29): as datas de escritura e de CPCV
# vivem no processo e a consulta do mês filtra por elas. `sparse`: a
# maioria dos processos não tem as datas preenchidas.
_definir(
    "processes",
    [
        {"keys": [("real_estate_data.data_escritura_prevista", 1)], "name": "idx_proc_data_escritura", "sparse": True},
        {"keys": [("real_estate_data.data_cpcv", 1)], "name": "idx_proc_data_cpcv", "sparse": True},
    ],
)

# O registo semanal: um por (âmbito, semana). O `unique` impede que dois
# pedidos concorrentes do mesmo CEO deixem dois registos da mesma semana.
_definir(
    "executive_weekly_reports",
    [{
        "keys": [("scope_key", 1), ("week_start", -1)],
        "name": "idx_exec_weekly_scope_week",
        "unique": True,
    }],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'process_financial_origins' (Bloco 4, ponto 7)
# ====================================================================
# Uma origem por processo: o `unique` é o que impede duas escritas
# concorrentes de deixarem duas origens (e o cálculo de comissões de
# escolher uma à sorte).
_definir(
    "process_financial_origins",
    [
        {"keys": [("process_id", 1)], "name": "idx_origin_process", "unique": True},
        {"keys": [("angariador_id", 1)], "name": "idx_origin_angariador", "sparse": True},
    ],
)

# ====================================================================
# ÍNDICES PARA COLECÇÃO 'portal_scraper_jobs' (Bloco 5, pontos 8 e 9)
# ====================================================================
# Tudo o que se pergunta a esta colecção é «os jobs deste processo,
# activos, o mais recente»: o MFA, o job activo antes de criar outro e a
# limpeza dos mortos. Sem o índice, cada polling do ecrã (3 s) varria-a.
_definir(
    "portal_scraper_jobs",
    [
        {"keys": [("process_id", 1), ("created_at", -1)], "name": "idx_scraper_job_process_recente"},
        {"keys": [("id", 1)], "name": "idx_scraper_job_id", "unique": True},
        # D-29: UM job activo por processo, ATÓMICO. `active` existe (verdadeiro) só enquanto o job
        # está em processing/awaiting_mfa — o `partialFilterExpression` não aceita `$in` sobre
        # `status`. Os jobs anteriores a este índice não têm o campo e ficam de fora (envelhecem e
        # `encerrar_jobs_mortos` fecha-os).
        {
            "keys": [("process_id", 1)],
            "name": "idx_scraper_job_activo_unico",
            "unique": True,
            "partialFilterExpression": {"active": True},
        },
    ],
)

# ====================================================================
# PORTAL DO PARCEIRO (Out 2026)
# ====================================================================
# `partners`: o login procura por email e a sessão por id — ambos
# únicos (dois documentos com o mesmo email deixavam o login escolher à
# sorte). O convite procura-se pelo hash do token (`sparse`: só os
# convites pendentes o têm).
_definir(
    "partners",
    [
        {"keys": [("id", 1)], "name": "idx_partner_id", "unique": True},
        {"keys": [("email", 1)], "name": "idx_partner_email", "unique": True},
        {"keys": [("invite.token_hash", 1)], "name": "idx_partner_invite", "sparse": True},
    ],
)

# Leads RETIDAS do lado do parceiro (filtro de viabilidade, Out 2026):
# o id é único (a libertação move o documento com o MESMO id para
# `clients`) e o parceiro lista as suas por (parceiro, estado).
_definir(
    "partner_drafts",
    [
        {"keys": [("id", 1)], "name": "idx_partner_draft_id", "unique": True},
        {"keys": [("submitted_by_partner_id", 1), ("partner_stage", 1)], "name": "idx_partner_draft_parceiro"},
        {"keys": [("partner_stage", 1), ("last_activity_at", 1)], "name": "idx_partner_draft_inactividade"},
    ],
)

# Um controlo «serviço pago pelo parceiro» por processo: o `unique` é o que
# impede duas escritas concorrentes de deixarem dois registos (e a ficha
# de mostrar um ao acaso).
_definir(
    "process_partner_service",
    [{"keys": [("process_id", 1)], "name": "idx_partner_service_process", "unique": True}],
)

# A pergunta de TODAS as listagens e métricas do parceiro: «os meus
# processos, da(s) minha(s) rede(s), não eliminados». O prefixo é o
# campo mais selectivo (um parceiro tem dezenas, a rede milhares).
_definir(
    "processes",
    [{
        "keys": [("assigned_parceiro_id", 1), ("network_id", 1), ("is_deleted", 1)],
        "name": "idx_proc_parceiro_rede",
        "sparse": True,
    }],
)

# As leads que o parceiro submeteu (clientes sem processo).
_definir(
    "clients",
    [{
        "keys": [("submitted_by_partner_id", 1), ("network_id", 1)],
        "name": "idx_client_parceiro_rede",
        "sparse": True,
    }],
)

# P4 — AS LISTAGENS DE CLIENTES E PROCESSOS. Toda a listagem abre com a condição de tenant
# (`network_id` e/ou `company_id`, ver `tenant_network.build_network_scope_condition`) e ordena por
# data ou nome; `clients` não tinha índice nenhum nessas chaves — cada abertura da lista de
# clientes varria a colecção inteira. A ordem das chaves é do prefixo mais presente para o menos
# (rede/empresa → não eliminado → chave de ordenação), para o mesmo índice servir o filtro e o
# `sort` sem um passo de ordenação em memória.
_definir(
    "clients",
    [
        {"keys": [("network_id", 1), ("is_deleted", 1), ("created_at", -1)], "name": "idx_client_rede_activos"},
        {"keys": [("company_id", 1), ("is_deleted", 1), ("created_at", -1)], "name": "idx_client_empresa_activos"},
    ],
)
_definir(
    "processes",
    [
        {"keys": [("company_id", 1), ("is_deleted", 1), ("status", 1)], "name": "idx_proc_empresa_estado"},
        {"keys": [("network_id", 1), ("is_deleted", 1), ("client_name", 1)], "name": "idx_proc_rede_cliente"},
    ],
)

# Workflow POR REDE: `carregar_fases(rede)` lê as fases de UMA rede por
# `order`, e a edição procura por (rede, nome). Não é único de propósito
# (o `scripts/migrar_workflow_por_rede.py` cria o único depois de provar
# que não há duplicados — um índice único que falha no arranque não ajuda).
_definir(
    "workflow_statuses",
    [
        {"keys": [("network_id", 1), ("order", 1)], "name": "idx_workflow_rede_ordem"},
        {"keys": [("network_id", 1), ("name", 1)], "name": "idx_workflow_rede_nome"},
    ],
)

# Formulário público POR REDE: lê-se um documento por (tipo, rede) e o modelo
# é o que não tem rede. Não é único aqui pelo mesmo motivo do workflow: o único
# nasce no `scripts/migrar_formularios_por_rede.py`, depois de provar que não há
# duplicados; o upsert por (tipo, rede) já evita criá-los.
_definir(
    "form_config",
    [
        {"keys": [("type", 1), ("network_id", 1)], "name": "idx_form_config_tipo_rede"},
    ],
)

_definir(
    "form_templates",
    [
        {"keys": [("network_id", 1)], "name": "idx_form_templates_rede", "sparse": True},
    ],
)

# Caixas partilhadas por cargo (D-8): a identidade é (cargo, rede). NÃO é único
# de propósito: as configurações antigas não têm `network_id` e o upsert por
# (cargo, rede) já evita duplicados; o índice serve a consulta de cada
# leitor (cargo + âmbito de rede) e o backfill carimba as antigas.
_definir(
    "shared_role_email_configs",
    [
        {"keys": [("role", 1), ("network_id", 1)], "name": "idx_shared_role_configs_cargo_rede"},
    ],
)


async def _preparar_indices(db) -> None:
    """Remove índices antigos que CONFLITUAM com as definições novas (corre antes de as criar).

    Não são definições: são limpezas de esquema que a criação não consegue fazer sozinha
    (um único restritivo residual só é substituído se for apagado primeiro).
    """
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

    # Unicidade: (user_id, company_id, email_address) — várias contas por perfil.
    try:
        await db.user_email_configs.drop_index("idx_user_company_email_unique")
        logger.info("Índice antigo idx_user_company_email_unique removido (DN.4)")
    except Exception:
        pass


async def _base_de_dados_alcancavel(db) -> bool:
    """Pergunta UMA vez se a base de dados responde (`ping`) antes de começar.

    Sem isto, com o Atlas inalcançável (IP não autorizado, cluster em pausa, rede) cada
    um dos ~100 índices esperava o seu próprio `serverSelectionTimeout` de 30 s e o
    arranque durava mais do que o Render espera por uma porta aberta — o deploy morria
    com «No open ports detected / Timed Out» sem uma única linha a dizer porquê.
    Só uma falha de LIGAÇÃO (`AutoReconnect` e derivadas: seleção de servidor, timeout de
    rede) conta como «inalcançável»; qualquer outro erro (um duplo de teste sem `command`,
    um erro de autorização) não decide nada aqui e a criação segue o seu caminho normal.
    """
    try:
        await db.command("ping")
    except AutoReconnect as exc:
        logger.error(
            "❌ Base de dados INALCANÇÁVEL no arranque — criação de índices ADIADA para o "
            "próximo arranque (verificar Network Access/IP do Atlas, estado do cluster e "
            f"MONGO_URL): {exc}"
        )
        return False
    except Exception:  # noqa: BLE001 — não é uma falha de ligação: não decide nada
        return True
    return True


async def create_indexes(db) -> dict:
    """
    Cria os índices declarados em `INDEX_DEFINITIONS` (e os TTL de `TTL_INDEXES`).

    Returns:
        dict: Resumo dos índices criados (`indisponivel: True` se a base de dados não respondeu)
    """
    if not await _base_de_dados_alcancavel(db):
        return {
            "created": [], "errors": [], "skipped": [], "cleanup": {},
            "indisponivel": True,
        }

    # Primeiro, limpar índices antigos/incorretos
    cleanup_results = await cleanup_deprecated_indexes(db)

    results = {
        "created": [],
        "errors": [],
        "skipped": [],
        "cleanup": cleanup_results
    }

    await _preparar_indices(db)

    for colecao, definicoes in INDEX_DEFINITIONS.items():
        for idx in definicoes:
            if results.get("indisponivel"):
                break
            await _create_index_safe(getattr(db, colecao), idx, colecao, results)
        if results.get("indisponivel"):
            logger.error(
                "❌ A ligação à base de dados caiu a meio da criação de índices — "
                "os restantes ficam para o próximo arranque."
            )
            return results

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

    return results


#: Colecções que o painel de diagnóstico mostra SEMPRE, mesmo sem índices próprios declarados
#: (a observabilidade de uma colecção que ficou sem índices é precisamente a que interessa).
COLECCOES_OBSERVADAS = (
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
)


def colecoes_com_indices() -> list[str]:
    """Todas as colecções que a aplicação indexa — DERIVADAS do registo e dos TTL.

    Antes `get_index_stats` tinha uma segunda lista à mão que divergia da realidade em cada
    índice novo (D-10): uma colecção indexada que não constasse dela nunca aparecia no painel.
    """
    return list(dict.fromkeys([
        *COLECCOES_OBSERVADAS,
        *INDEX_DEFINITIONS,
        *(i["collection"] for i in TTL_INDEXES),
    ]))


async def get_index_stats(db) -> dict:
    """
    Obtém estatísticas dos índices existentes.
    """
    stats = {}

    for collection_name in colecoes_com_indices():
        try:
            collection = getattr(db, collection_name)
            indexes = await collection.index_information()
            stats[collection_name] = {
                "count": len(indexes),
                "indexes": list(indexes.keys())
            }
        except Exception as e:
            # Uma colecção que ainda não existe (nenhum documento escrito) não tem índices: é
            # «vazia», não «avariada». O Mongo responde `NamespaceNotFound` (código 26).
            if getattr(e, "code", None) == 26 or "ns not found" in str(e).lower():
                stats[collection_name] = {"count": 0, "indexes": []}
            else:
                stats[collection_name] = {"error": str(e)}

    return stats
