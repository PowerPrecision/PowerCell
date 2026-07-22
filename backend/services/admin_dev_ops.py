"""DB indexes, sync-database, seed realistic data (admin DEV ops).

Extraído de `routes/admin.py`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import hash_password, require_roles, get_current_user
from services.admin_helpers import _safe_float, _audit_log
from services.permissions import (
    get_default_permissions_for_role,
    get_all_available_permissions,
    get_role_display_info,
    validate_permissions,
    DEFAULT_PERMISSIONS_BY_ROLE,
    get_user_capabilities,
    build_permissions_document,
)
from models.permissions import (
    CAPABILITIES,
    CATEGORIES,
    SUPER_ADMIN_ROLES,
    ROLE_CAPABILITY_DEFAULTS,
    get_all_capabilities,
    get_capabilities_by_category,
    get_role_defaults,
    resolve_capability,
    validate_capabilities,
)

logger = logging.getLogger(__name__)


_sync_in_progress = False

_sync_result_cache = {"result": None, "timestamp": None}

class SyncDatabaseRequest(BaseModel):
    """
    Modelo para a requisição de restauro de BD a partir de backup.

    Nota: prod_url e prod_db_name já não são necessários pois a fonte
    é o backup automático no S3 (não a BD de Produção diretamente).
    Mantidos para compatibilidade backward (são ignorados).
    """
    prod_url: Optional[str] = None   # Ignorado (legado — mantido para compatibilidade)
    prod_db_name: Optional[str] = None  # Ignorado (legado)
    dev_url: Optional[str] = None
    dev_db_name: Optional[str] = None


class SeedRequest(BaseModel):
    """Parâmetros para o seed de dados realistas."""
    clear: bool = False
    skip_clients: bool = False
    skip_processes: bool = False
    skip_tasks: bool = False



async def run_get_database_indexes(user: dict):
    """
    Lista todos os índices de todas as colecções principais.
    Útil para diagnóstico de problemas de índices duplicados.
    """
    from services.db_indexes import get_index_stats
    stats = await get_index_stats(db)
    return {"success": True, "indexes": stats}


async def run_repair_database_indexes(user: dict):
    """
    Remove índices antigos/incorretos e recria os correctos.
    Use quando houver erros de duplicate key em índices.
    """
    from services.db_indexes import cleanup_deprecated_indexes, create_indexes
    
    # Primeiro, limpar índices problemáticos
    cleanup_results = await cleanup_deprecated_indexes(db)
    
    # Depois, garantir que os índices correctos existem
    create_results = await create_indexes(db)
    
    return {
        "success": True,
        "cleanup": cleanup_results,
        "indexes": create_results
    }


async def run_drop_specific_index(collection: str, index_name: str, user: dict):
    """
    Remove um índice específico de uma colecção.
    Use com cuidado - apenas para índices problemáticos.
    """
    allowed_collections = ["properties", "processes", "users", "tasks", "leads"]
    if collection not in allowed_collections:
        raise HTTPException(status_code=400, detail=f"Colecção não permitida. Use: {allowed_collections}")
    
    if index_name == "_id_":
        raise HTTPException(status_code=400, detail="Não pode remover o índice _id_")
    
    try:
        coll = db[collection]
        existing = await coll.index_information()
        
        if index_name not in existing:
            raise HTTPException(status_code=404, detail=f"Índice '{index_name}' não existe em '{collection}'")
        
        await coll.drop_index(index_name)
        return {"success": True, "message": f"Índice '{index_name}' removido de '{collection}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover índice: {str(e)}")


async def run_get_sync_status(user: dict):
    """
    Obtém o estado da última sincronização Prod → Dev.
    """
    return {
        "in_progress": _sync_in_progress,
        "last_result": _sync_result_cache["result"],
        "last_timestamp": _sync_result_cache["timestamp"],
    }


async def run_sync_database(request: SyncDatabaseRequest, background_tasks: BackgroundTasks, user: dict):
    """
    Restaura a base de dados de Desenvolvimento a partir do backup de Produção (S3).

    Arquitetura (sem carga no servidor de Produção):
        S3 Backup (ZIP) → Download → Extract JSON → Coleções _temp → Sanitize RGPD
        → Validar integridade → Swap para coleções reais → Cleanup

    SEGURANÇA:
    - Só funciona se ENVIRONMENT != "production" (403 em produção)
    - Só pode ser executado por admin (role = admin)
    - Executa em background (BackgroundTasks) para evitar timeouts
    - FALHA SEGURA: Dev DB NÃO é modificada se o backup estiver corrompido

    Anonimização RGPD aplicada:
    - clients: email → dev_client_{id}@powercell.dev, NIF → falso válido, phone → baralhado
    - processes: remove links S3/AWS, limpa campos financeiros ultra-sensíveis
    - properties: remove links S3, limpa dados financeiros, arredonda coordenadas
    - users: mantém emails e passwords reais para login, anonimiza dados pessoais
    """
    # Nota: `global` não é necessário aqui pois apenas lemos _sync_in_progress.
    # A escrita (atribuição) acontece dentro de _execute_restore() que já
    # declara o seu próprio `global`.

    # ─── SEGURANÇA 1: Bloquear em produção ───
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment in ("production", "prod"):
        logger.warning(f"Tentativa de restore em PRODUÇÃO bloqueada por utilizador {user.get('email')}")
        raise HTTPException(
            status_code=403,
            detail="Este endpoint NÃO pode ser executado em produção. Ação bloqueada por segurança."
        )

    # ─── SEGURANÇA 2: Apenas admin ───
    if user.get("role") != UserRole.ADMIN:
        logger.warning(f"Tentativa de restore por não-admin bloqueada: {user.get('email')}")
        raise HTTPException(
            status_code=403,
            detail="Apenas o administrador pode executar esta operação."
        )

    # ─── PREVENIR CONCORRÊNCIA ───
    if _sync_in_progress:
        raise HTTPException(
            status_code=409,
            detail="Já existe um restauro em curso. Aguarde a conclusão."
        )

    # ─── RESOLVER URI DEV ───
    dev_url = request.dev_url or os.getenv("DEV_MONGO_URL")
    dev_db_name = request.dev_db_name or os.getenv("DEV_DB_NAME")

    if not dev_url or not dev_db_name:
        raise HTTPException(
            status_code=400,
            detail="URL e nome da BD de Desenvolvimento são obrigatórios. Defina DEV_MONGO_URL/DEV_DB_NAME ou envie no body."
        )

    # ─── REGISTAR AUDIT LOG ───
    await _audit_log(
        "restore_dev_from_backup",
        "database",
        "restore",
        user,
        {
            "mode": "backup_restore",
            "dev_db": dev_db_name,
            "environment": environment,
            "anonymization": True,
            "source": "s3_backup",
        }
    )

    # ─── EXECUTAR EM BACKGROUND ───
    async def _execute_restore():
        """Executa o restauro da BD de desenvolvimento a partir do backup S3.

        Esta função interna é executada em background (via BackgroundTasks)
        e coordena todo o pipeline de restauro:

        1. Download do backup ZIP mais recente do S3.
        2. Extração dos ficheiros JSON de cada coleção.
        3. Sanitização RGPD (anonimização de dados pessoais).
        4. Validação de integridade dos dados.
        5. Escrita para coleções temporárias (_temp).
        6. Swap atómico das coleções temporárias para as reais.
        7. Limpeza das coleções temporárias.

        Porquê em background: o restauro pode demorar vários minutos
        dependendo do tamanho da base de dados. Executar de forma
        síncrona causaria timeout no FastAPI.

        Garantias de segurança:
        - FALHA SEGURA: se qualquer etapa falhar, a BD de dev não é
          modificada (usa coleções _temp como intermediário).
        - Regista resultado (sucesso ou erro) em ``_sync_result_cache``.
        - Sempre define ``_sync_in_progress = False`` no finally.

        Raises:
            Exception: Qualquer erro durante o restauro é capturado e
                registado em ``_sync_result_cache`` sem propagar.
        """
        global _sync_in_progress, _sync_result_cache
        _sync_in_progress = True
        try:
            from scripts.restore_dev_from_backup import run_restore
            result = await run_restore(dev_url, dev_db_name)
            _sync_result_cache = {"result": result, "timestamp": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            logger.error(f"Erro crítico no restore Dev from backup: {e}", exc_info=True)
            _sync_result_cache = {
                "result": {
                    "success": False,
                    "error": str(e),
                    "total_documents": 0,
                    "mode": "backup_restore",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            _sync_in_progress = False

    background_tasks.add_task(_execute_restore)

    return {
        "success": True,
        "message": "Restauro a partir de backup iniciado em background. Use GET /admin/sync-database/status para acompanhar.",
        "details": {
            "mode": "backup_restore",
            "source": "s3_latest_backup",
            "dev_db": dev_db_name,
            "anonymization": True,
            "fail_safe": True,
            "environment": environment,
            "started_by": user.get("email"),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    }


async def run_seed_realistic_data(request: Request, current_user: dict, body: SeedRequest = None):
    """
    Executa o seed de dados realistas para popular a BD de dev.
    Apenas disponível para admins. Utiliza Faker pt_PT para gerar
    30 clientes, ~20 processos (3 em FILA_ESPERA), tarefas e task_logs.
    """
    if body is None:
        body = SeedRequest()

    import asyncio
    import random
    import string
    from pathlib import Path

    try:
        from faker import Faker
    except ImportError:
        raise HTTPException(status_code=500, detail="Faker não está instalado. Execute: pip install Faker")

    fake_local = Faker('pt_PT')

    # ── Dados realistas portugueses ──
    PROFISSOES_LOCAL = [
        "Engenheiro Informático", "Enfermeiro", "Professor", "Gestor de Conta",
        "Técnico de Vendas", "Motorista", "Engenheiro Civil", "Médico",
        "Advogado", "Contabilista", "Administrativo", "Comercial",
        "Técnico de Informática", "Arquiteto", "Designer", "Consultor",
    ]
    TIPOS_CONTRATO_LOCAL = ["Efetivo", "Termo Certo", "Recibos Verdes", "Empresário"]
    ESTADOS_CIVIS_LOCAL = ["Solteiro", "Casado", "Divorciado", "Viúvo"]
    PROCESS_STATUSES_LOCAL = [
        "clientes_espera", "documentacao", "analise", "pre_aprovacao",
        "credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv",
        "minuta", "escritura", "concluido", "arquivo", "perdido",
        "desistencias", "fila_espera",
    ]
    PROCESS_TYPES_LOCAL = ["credito_habitacao", "credito_pessoal", "compra_direta",
                           "arrendamento", "consultoria", "refinanciamento"]
    FONTES_LOCAL = ["Manual", "Website", "Indicação", "Telefone", "Email"]
    EMPRESAS_LOCAL = [
        "EDP", "Galp", "Sonae", "Jerónimo Martins", "Millennium BCP",
        "Vodafone Portugal", "NOS", "Deloitte Portugal", "TAP Air Portugal",
    ]
    CIDADES_LOCAL = [
        "Lisboa", "Porto", "Braga", "Coimbra", "Faro", "Aveiro", "Setúbal",
        "Leiria", "Guimarães", "Cascais", "Sintra", "Vila Nova de Gaia",
    ]
    TITULOS_TAREFAS_LOCAL = [
        "Recolher documentos do cliente", "Enviar documentação para o banco",
        "Agendar avaliação do imóvel", "Preparar minuta do contrato",
        "Contactar cliente para assinatura", "Verificar NIF do cliente",
        "Solicitar comprovativo de rendimentos", "Enviar CPCV para assinatura",
        "Confirmar dados bancários", "Agendar escritura no notário",
        "Atualizar dados do processo", "Enviar simulação ao cliente",
        "Pedir documentos complementares", "Submeter proposta ao banco",
    ]

    # ── Opções de Imóvel, Crédito e Financiamento ──
    LOCALIDADES_IMOVEL = ["Lisboa", "Porto", "Braga", "Setúbal", "Faro", "Coimbra"]
    TIPOS_IMOVEL = ["Apartamento T2", "Apartamento T3", "Moradia V3"]
    FINALIDADES_CREDITO = ["Aquisição HPP", "Transferência", "Construção"]
    PRAZOS_FINANCIAMENTO = [360, 420, 480]  # meses (30/35/40 anos)

    def _gerar_nif():
        primeiro = random.choice([1, 2, 3, 3, 3, 2, 1])
        digitos = [primeiro] + [random.randint(0, 9) for _ in range(8)]
        soma = sum(digitos[i] * (9 - i) for i in range(8))
        resto = soma % 11
        digitos.append(0 if resto < 2 else 11 - resto)
        return ''.join(map(str, digitos))

    def _gerar_telefone():
        return f"{random.choice(['91','93','92','96'])}{''.join(random.choices(string.digits, k=7))}"

    def _gerar_email(nome):
        nomes = nome.lower().split()
        fmt = random.choice([
            f"{nomes[0]}.{nomes[-1]}",
            f"{nomes[0]}{nomes[-1]}",
            f"{nomes[0]}.{nomes[-1]}{random.randint(1,99)}",
        ])
        dom = random.choice(["gmail.com", "hotmail.com", "outlook.pt", "sapo.pt"])
        from unicodedata import normalize
        fmt = normalize('NFKD', fmt).encode('ASCII', 'ignore').decode('ASCII')
        return f"{fmt}@{dom}"

    def _gerar_data_nasc():
        hoje = datetime.now()
        idade = random.randint(18, 70)
        return f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{hoje.year - idade}"

    # ── Limpar dados anteriores ──
    if body.clear:
        filter_q = {"_seed_script": "seed_realistic_data"}
        r1 = await db.clients.delete_many(filter_q)
        r2 = await db.processes.delete_many(filter_q)
        r3 = await db.tasks.delete_many(filter_q)
        r4 = await db.task_logs.delete_many(filter_q)
        logger.info(f"Seed clear: {r1.deleted_count} clientes, {r2.deleted_count} processos, "
                     f"{r3.deleted_count} tarefas, {r4.deleted_count} task_logs")

    # ── Buscar utilizadores existentes ──
    consultores = await db.users.find({"role": "consultor", "is_active": True}).to_list(100)
    indexadores = await db.users.find({"role": "indexacao", "is_active": True}).to_list(100)
    intermediarios = await db.users.find({"role": "intermediario", "is_active": True}).to_list(100)
    admins = await db.users.find({"role": {"$in": ["administrativo", "diretor", "ceo", "admin"]}, "is_active": True}).to_list(100)

    # Criar dummies se não existirem
    if not consultores:
        for nome in ["Ricardo Mendes", "Sofia Ferreira"]:
            uid = str(uuid.uuid4())
            doc = {"id": uid, "email": f"{nome.split()[0].lower()}@powercell-dev.pt",
                   "name": nome, "phone": _gerar_telefone(), "role": "consultor",
                   "company": "Power Real Estate", "is_active": True,
                   "created_at": datetime.now(timezone.utc).isoformat(),
                   "_seed_data": True, "_seed_script": "seed_realistic_data"}
            await db.users.insert_one(doc)
            consultores.append(doc)

    if not indexadores:
        uid = str(uuid.uuid4())
        doc = {"id": uid, "email": "indexacao@powercell-dev.pt", "name": "Ana Costa",
               "phone": _gerar_telefone(), "role": "indexacao", "company": "Power Real Estate",
               "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
               "_seed_data": True, "_seed_script": "seed_realistic_data"}
        await db.users.insert_one(doc)
        indexadores.append(doc)

    todos_users = consultores + indexadores + intermediarios + admins
    seen_ids = set()
    todos_users = [u for u in todos_users if u["id"] not in seen_ids and not seen_ids.add(u["id"])]

    stats = {"clientes": 0, "processos": 0, "tarefas": 0, "task_logs": 0, "fila_espera": 0}

    # ── Criar 30 Clientes ──
    clientes = []
    if not body.skip_clients:
        for _ in range(30):
            nome = fake_local.name()
            cid = str(uuid.uuid4())
            email = _gerar_email(nome)
            tel = _gerar_telefone()
            nif = _gerar_nif()
            cidade = random.choice(CIDADES_LOCAL)
            estado_civil = random.choice(ESTADOS_CIVIS_LOCAL)
            profissao = random.choice(PROFISSOES_LOCAL)
            salario = round(random.uniform(850, 4500), 2)
            tipo_contrato = random.choice(TIPOS_CONTRATO_LOCAL)
            empresa = random.choice(EMPRESAS_LOCAL) if random.random() < 0.7 else None
            despesas_mensais_outros = round(random.uniform(0, 400), 2)
            capitais_proprios = round(random.uniform(10_000, 60_000), 2)
            dependentes = random.randint(0, 3)

            cliente = {
                "id": cid, "nome": nome,
                "contacto": {"email": email, "telefone": tel,
                             "email_secundario": _gerar_email(nome) if random.random() < 0.15 else None,
                             "telefone_secundario": _gerar_telefone() if random.random() < 0.3 else None},
                "dados_pessoais": {
                    "nif": nif, "documento_id": ''.join(random.choices(string.ascii_uppercase, k=2)) +
                            ''.join(random.choices(string.digits, k=7)) +
                            random.choice(string.digits + string.ascii_uppercase),
                    "data_nascimento": _gerar_data_nasc(),
                    "naturalidade": cidade, "nacionalidade": random.choice(["Portuguesa"]*5 + ["Brasileira", "Angolana"]),
                    "morada_fiscal": f"{fake_local.street_name()}, {random.randint(1,500)}, {random.randint(1000,9999)}-{random.randint(100,999)} {cidade}",
                    "estado_civil": estado_civil, "profissao": profissao,
                    "nome_pai": fake_local.name_male(), "nome_mae": fake_local.name_female(),
                    "sexo": random.choice(["M", "F"]),
                },
                "process_ids": [],
                "dados_financeiros": {
                    "salario": salario,
                    "tipo_contrato": tipo_contrato,
                    "empresa": empresa,
                    "despesas_mensais_outros_creditos": despesas_mensais_outros,
                    "capitais_proprios": capitais_proprios,
                    "dependentes": dependentes,
                },
                "fonte": random.choice(FONTES_LOCAL),
                "tags": random.sample(["VIP", "urgente", "retorno", "referência", "online"],
                                      k=random.randint(0, 2)),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "_seed_data": True, "_seed_script": "seed_realistic_data",
            }
            clientes.append(cliente)

        if clientes:
            await db.clients.insert_many(clientes)
            stats["clientes"] = len(clientes)
    else:
        existing = await db.clients.find({}).to_list(30)
        clientes = list(existing)

    if not clientes:
        raise HTTPException(status_code=400, detail="Nenhum cliente disponível")

    # ── Criar ~20 Processos (pelo menos 3 em FILA_ESPERA) ──
    processos = []
    if not body.skip_processes:
        ultimo = await db.processes.find_one({"process_number": {"$exists": True}},
                                              sort=[("process_number", -1)])
        ultimo_num = ultimo.get("process_number", 0) if ultimo else 0

        selecionados = random.sample(clientes, k=min(20, len(clientes)))
        status_weights = [15, 18, 14, 10, 8, 5, 4, 5, 4, 3, 5, 2, 2, 2]  # sem fila_espera

        for i, cliente in enumerate(selecionados):
            force_fila = i < 3
            if force_fila:
                status = "fila_espera"
            else:
                choices = [s for s in PROCESS_STATUSES_LOCAL if s != "fila_espera"]
                status = random.choices(choices, weights=status_weights, k=1)[0]

            consultor = random.choice(consultores) if consultores else None
            indexador = random.choice(indexadores) if indexadores else None
            intermediario = random.choice(intermediarios) if intermediarios else None
            process_type = random.choice(PROCESS_TYPES_LOCAL)
            dias_atras = random.randint(1, 90)

            # ── Dados do Imóvel (100%) ──
            valor_imovel = round(random.uniform(120_000, 450_000), 2)
            localidade_imovel = random.choice(LOCALIDADES_IMOVEL)
            tipo_imovel = random.choice(TIPOS_IMOVEL)
            area_imovel = random.randint(55, 200)

            real_estate_data = {
                "ja_tem_imovel": True,
                "valor_imovel": valor_imovel,
                "localidade": localidade_imovel,
                "tipo_imovel": tipo_imovel,
                "area": area_imovel,
            }

            # ── Dados do Crédito / Operação (100%) ──
            finalidade = random.choice(FINALIDADES_CREDITO)
            pct_financiamento = round(random.uniform(0.80, 0.90), 4)
            valor_financiamento = round(valor_imovel * pct_financiamento, 2)
            prazo_meses = random.choice(PRAZOS_FINANCIAMENTO)
            prazo_anos = prazo_meses // 12
            spread = round(random.uniform(0.50, 1.80), 2)
            euribor = round(random.uniform(2.5, 3.8), 2)
            taxa_anual = round(euribor + spread, 2)
            tipo_taxa = random.choice(["variável", "mista", "fixa"])
            taxa_mensal = taxa_anual / 100 / 12
            if taxa_mensal > 0:
                prestacao_mensal = round(
                    valor_financiamento
                    * (taxa_mensal * (1 + taxa_mensal) ** prazo_meses)
                    / ((1 + taxa_mensal) ** prazo_meses - 1), 2)
            else:
                prestacao_mensal = round(valor_financiamento / prazo_meses, 2)

            credit_data = {
                "finalidade": finalidade,
                "valor_financiamento": valor_financiamento,
                "pct_financiamento": round(pct_financiamento * 100, 1),
                "prazo_meses": prazo_meses,
                "prazo_anos": prazo_anos,
                "taxa_anual": taxa_anual,
                "spread": spread,
                "euribor": euribor,
                "tipo_taxa": tipo_taxa,
                "prestacao_mensal": prestacao_mensal,
            }

            # ── Compra Sozinho / 2º Proponente ──
            compra_sozinho = random.choice([True, True, False])  # ~33% com 2º titular
            titular2_data = None
            if not compra_sozinho:
                nome_t2 = fake_local.name()
                titular2_data = {
                    "name": nome_t2,
                    "nif": _gerar_nif(),
                    "email": _gerar_email(nome_t2),
                    "phone": _gerar_telefone(),
                    "profissao": random.choice(PROFISSOES_LOCAL),
                    "salario": round(random.uniform(700, 3500), 2),
                    "tipo_contrato": random.choice(TIPOS_CONTRATO_LOCAL),
                    "relacao": random.choice(["Cônjuge", "Companheiro(a)"]),
                }

            processo = {
                "id": str(uuid.uuid4()),
                "process_number": ultimo_num + i + 1,
                "client_id": cliente["id"], "client_ids": [cliente["id"]],
                "client_name": cliente["nome"],
                "client_email": cliente["contacto"]["email"],
                "client_phone": cliente["contacto"]["telefone"],
                "client_nif": cliente.get("dados_pessoais", {}).get("nif", ""),
                "process_type": process_type, "type": process_type,
                "status": status,
                "is_active": status not in ["concluido", "arquivo", "perdido", "desistencias"],
                "assigned_consultor_id": consultor["id"] if consultor else None,
                "assigned_consultor_ids": [consultor["id"]] if consultor else [],
                "consultor_names": [consultor["name"]] if consultor else [],
                "assigned_indexacao_id": indexador["id"] if indexador else None,
                "assigned_mediador_id": intermediario["id"] if intermediario else None,
                "assigned_mediador_ids": [intermediario["id"]] if intermediario else [],
                "mediador_names": [intermediario["name"]] if intermediario else [],
                "personal_data": cliente.get("dados_pessoais", {}).copy(),
                "finance_data": cliente.get("dados_financeiros", {}),
                "real_estate_data": real_estate_data, "credit_data": credit_data,
                "compra_sozinho": compra_sozinho,
                "titular2_data": titular2_data,
                "co_buyers": [], "co_applicants": [titular2_data] if titular2_data else [],
                "source": cliente.get("fonte", "Manual"),
                "prioridade": random.choice(["baixa", "normal", "normal", "normal", "alta"]),
                "created_at": (datetime.now(timezone.utc) - timedelta(days=dias_atras)).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "_seed_data": True, "_seed_script": "seed_realistic_data",
            }
            processos.append(processo)

            await db.clients.update_one({"id": cliente["id"]}, {"$push": {"process_ids": processo["id"]}})

        if processos:
            await db.processes.insert_many(processos)
            stats["processos"] = len(processos)
            stats["fila_espera"] = sum(1 for p in processos if p["status"] == "fila_espera")
    else:
        existing = await db.processes.find({}).to_list(30)
        processos = list(existing)

    # ── Criar Tarefas e TaskLogs ──
    if not body.skip_tasks and processos:
        tasks = []
        task_logs = []

        for processo in processos:
            consultor_id = processo.get("assigned_consultor_id")
            created_by = next((u for u in todos_users if u["id"] == consultor_id), None)
            if not created_by:
                created_by = random.choice(todos_users) if todos_users else None
            if not created_by:
                continue

            for _ in range(random.randint(2, 4)):
                r = random.random()
                dias_offset = random.randint(-14, -1) if r < 0.4 else (0 if r < 0.6 else random.randint(1, 14))
                titulo = random.choice(TITULOS_TAREFAS_LOCAL)
                assigned_to = random.sample([u["id"] for u in todos_users],
                                            k=random.randint(1, min(2, len(todos_users))))
                assigned_names = [u["name"] for u in todos_users if u["id"] in assigned_to]

                due_date = (datetime.now(timezone.utc) + timedelta(days=dias_offset)).isoformat()
                completed = random.random() < (0.2 if dias_offset < 0 else 0.4 if dias_offset == 0 else 0.5)
                completed_at = (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 3))).isoformat() if completed else None

                due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                days_until = (due_dt - datetime.now(timezone.utc)).days
                is_overdue = days_until < 0 and not completed

                task = {
                    "id": str(uuid.uuid4()), "title": titulo,
                    "description": fake_local.sentence(),
                    "assigned_to": assigned_to, "assigned_to_names": assigned_names,
                    "process_id": processo["id"],
                    "process_name": processo.get("client_name", "N/A"),
                    "created_by": created_by["id"], "created_by_name": created_by.get("name", ""),
                    "completed": completed, "completed_at": completed_at,
                    "completed_by": random.choice(assigned_to) if completed else None,
                    "due_date": due_date, "is_overdue": is_overdue,
                    "days_until_due": days_until,
                    "created_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 14))).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "_seed_data": True, "_seed_script": "seed_realistic_data",
                }
                tasks.append(task)

            # 1-2 task_logs por processo
            for _ in range(random.randint(1, 2)):
                log_status = random.choices(
                    ["COMPLETED", "PROCESSING", "FAILED", "PENDING"],
                    weights=[60, 15, 10, 15], k=1)[0]
                task_type = random.choice(["PDF_GEN", "AI_ANALYSIS", "EMAIL_SEND",
                                          "DOCUMENT_UPLOAD", "CUSTOM"])
                now = datetime.now(timezone.utc)
                task_log = {
                    "id": str(uuid.uuid4()), "task_id": str(uuid.uuid4()),
                    "user_id": created_by["id"], "task_type": task_type,
                    "status": log_status,
                    "title": f"{task_type} - {processo.get('client_name', 'N/A')}",
                    "progress": 100 if log_status == "COMPLETED" else random.randint(0, 95),
                    "process_id": processo["id"],
                    "process_name": processo.get("client_name", "N/A"),
                    "error_message": fake_local.sentence() if log_status == "FAILED" else None,
                    "created_at": now.isoformat(),
                    "started_at": (now - timedelta(minutes=random.randint(1, 30))).isoformat(),
                    "completed_at": (now - timedelta(minutes=random.randint(0, 5))).isoformat()
                    if log_status in ["COMPLETED", "FAILED"] else None,
                    "acknowledge_required": True, "acknowledged_at": None,
                    "_seed_data": True, "_seed_script": "seed_realistic_data",
                }
                task_logs.append(task_log)

        if tasks:
            await db.tasks.insert_many(tasks)
            stats["tarefas"] = len(tasks)
        if task_logs:
            await db.task_logs.insert_many(task_logs)
            stats["task_logs"] = len(task_logs)

    logger.info(f"Seed concluído: {stats}")
    return {
        "success": True,
        "message": "Seed de dados realistas concluído com sucesso!",
        "stats": stats,
    }


