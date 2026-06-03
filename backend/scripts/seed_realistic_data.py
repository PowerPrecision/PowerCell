#!/usr/bin/env python3
"""
====================================================================
SEED DE DADOS REALISTAS - POWERCELL
====================================================================
Script para popular a base de dados de dev com clientes, processos,
tarefas e task_logs altamente realistas para testar os dashboards
e o kanban.

Utiliza a biblioteca Faker com locale pt_PT para dados portugueses.

ESTRUTURA DE DADOS:
- 30 Clientes com dados pessoais portugueses completos
- ~20 Processos distribuídos pelos estados do workflow (15 fases)
- Pelo menos 3 processos no estado FILA_ESPERA
- Tasks (Tarefas) associadas a processos e utilizadores
- TaskLogs com datas variadas (última semana, atrasadas, etc.)

Uso:
    python scripts/seed_realistic_data.py [--clear] [--skip-clients] [--skip-processes] [--skip-tasks]

Opções:
    --clear           Remove dados de teste existentes antes de criar novos
    --skip-clients    Não criar clientes
    --skip-processes  Não criar processos
    --skip-tasks      Não criar tarefas e task_logs
    --help            Mostra esta ajuda
====================================================================
"""

import asyncio
import random
import string
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Adicionar o diretório backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from faker import Faker
except ImportError:
    print("❌ Erro: Biblioteca Faker não encontrada!")
    print("   Instale com: pip install Faker")
    print("   Ou adicione 'Faker' ao requirements.txt")
    sys.exit(1)

# Carregar variáveis de ambiente
load_dotenv(Path(__file__).parent.parent / '.env')

# Inicializar Faker com locale português
fake = Faker('pt_PT')

# ==============================================================================
# DADOS REALISTAS PORTUGUESES (suplemento ao Faker pt_PT)
# ==============================================================================

PROFISSOES = [
    "Engenheiro Informático", "Enfermeiro", "Professor", "Gestor de Conta",
    "Técnico de Vendas", "Motorista", "Engenheiro Civil", "Médico",
    "Advogado", "Contabilista", "Administrativo", "Comercial",
    "Técnico de Informática", "Arquiteto", "Designer", "Consultor",
    "Analista de Sistemas", "Farmacêutico", "Dentista", "Fisioterapeuta",
    "Psicólogo", "Economista", "Bancário", "Segurador", "Empresário",
    "Comerciante", "Funcionário Público", "Eletricista", "Canalizador",
    "Cozinheiro", "Vendedor", "Rececionista", "Jornalista"
]

TIPOS_CONTRATO = ["Efetivo", "Termo Certo", "Recibos Verdes", "Empresário"]

ESTADOS_CIVIS = ["Solteiro", "Casado", "Divorciado", "Viúvo"]

# ProcessStatus — 15 fases do workflow (models/enums.py)
PROCESS_STATUSES = [
    "clientes_espera",   # Fase 1
    "documentacao",      # Fase 2
    "analise",           # Fase 3
    "pre_aprovacao",     # Fase 4
    "credito_aprovado",  # Fase 5
    "pedido_avaliacao",  # Fase 6
    "avaliacao",         # Fase 7
    "cpcv",              # Fase 8
    "minuta",            # Fase 9
    "escritura",         # Fase 10
    "concluido",         # Fase 11
    "arquivo",           # Fase 12
    "perdido",           # Fase 13
    "desistencias",      # Fase 14
    "fila_espera",       # Fase 15
]

# Pesos para distribuição realista (mais processos nas fases iniciais)
STATUS_WEIGHTS = [
    15,  # clientes_espera
    18,  # documentacao
    14,  # analise
    10,  # pre_aprovacao
     8,  # credito_aprovado
     5,  # pedido_avaliacao
     4,  # avaliacao
     5,  # cpcv
     4,  # minuta
     3,  # escritura
     5,  # concluido
     2,  # arquivo
     2,  # perdido
     2,  # desistencias
     3,  # fila_espera  ← garantimos pelo menos 3 no código
]

PROCESS_TYPES = ["credito_habitacao", "credito_pessoal", "compra_direta",
                 "arrendamento", "consultoria", "refinanciamento"]

FONTES = ["Manual", "Website", "Indicação", "Telefone", "Email", "Feira"]

EMPRESAS = [
    "EDP - Energias de Portugal", "Galp Energia", "Sonae", "Jerónimo Martins",
    "Banco Santander", "BNP Paribas", "CGD - Caixa Geral de Depósitos",
    "Millennium BCP", "Bankinter", "Continente", "Pingo Doce",
    "Lidl Portugal", "Vodafone Portugal", "NOS", "Deloitte Portugal",
    "KPMG Portugal", "Delta Cafés", "Teixeira Duarte", "Mota-Engil",
    "Hospital de Santa Maria", "Universidade de Lisboa", "TAP Air Portugal",
]

CIDADES = [
    "Lisboa", "Porto", "Braga", "Coimbra", "Faro", "Aveiro", "Viseu",
    "Setúbal", "Leiria", "Guimarães", "Cascais", "Sintra", "Matosinhos",
    "Vila Nova de Gaia", "Amadora", "Almada", "Oeiras", "Loures"
]

TITULOS_TAREFAS = [
    "Recolher documentos do cliente",
    "Enviar documentação para o banco",
    "Agendar avaliação do imóvel",
    "Preparar minuta do contrato",
    "Contactar cliente para assinatura",
    "Verificar NIF do cliente",
    "Solicitar comprovativo de rendimentos",
    "Enviar CPCV para assinatura",
    "Confirmar dados bancários",
    "Agendar escritura no notário",
    "Atualizar dados do processo",
    "Ligar para o mediador",
    "Enviar simulação ao cliente",
    "Pedir documentos complementares",
    "Verificar validade do CC",
    "Submeter proposta ao banco",
    "Confirmar vistoria do imóvel",
    "Rever cláusulas do contrato",
    "Contactar seguradora",
    "Enviar email de acompanhamento",
]

DESCRICOES_TAREFAS = [
    "Recolher os documentos em falta para dar continuidade ao processo.",
    "Enviar toda a documentação necessária para a análise bancária.",
    "Agendar a avaliação do imóvel com a empresa de avaliações.",
    "Preparar a minuta do contrato de compra e venda.",
    "Contactar o cliente para agendar a assinatura dos documentos.",
    "Verificar se o NIF do cliente está correto e ativo.",
    "Solicitar os últimos 3 meses de comprovativo de rendimentos.",
    "Enviar o CPCV para assinatura digital do vendedor e comprador.",
    "Confirmar os dados bancários do cliente para a transferência.",
    "Agendar a escritura no notário e informar todas as partes.",
    "Atualizar os dados do processo no sistema após alterações.",
    "Ligar para o mediador para confirmar detalhes da transação.",
    "Enviar a simulação de crédito atualizada ao cliente por email.",
    "Pedir ao cliente documentos complementares solicitados pelo banco.",
    "Verificar se o Cartão de Cidadão está dentro da validade.",
    "Submeter a proposta de crédito ao banco parceiro.",
    "Confirmar a data e hora da vistoria do imóvel.",
    "Rever as cláusulas contratuais com o departamento jurídico.",
    "Contactar a seguradora para obter cotação do seguro de vida.",
    "Enviar email de acompanhamento semanal ao cliente.",
]


# ==============================================================================
# FUNÇÕES DE GERAÇÃO
# ==============================================================================

def gerar_nif_valido():
    """Gera um NIF português válido (9 dígitos, a começar por 1, 2 ou 3)."""
    primeiro_digito = random.choice([1, 2, 3, 3, 3, 3, 2, 1, 3])
    digitos = [primeiro_digito] + [random.randint(0, 9) for _ in range(8)]
    soma = sum(digitos[i] * (9 - i) for i in range(8))
    resto = soma % 11
    digito_controlo = 0 if resto < 2 else 11 - resto
    digitos.append(digito_controlo)
    return ''.join(map(str, digitos))


def gerar_telefone_portugues():
    """Gera um número de telemóvel português (91, 92, 93 ou 96 + 7 dígitos)."""
    prefixo = random.choice(["91", "93", "92", "96"])
    resto = ''.join(random.choices(string.digits, k=7))
    return f"{prefixo}{resto}"


def gerar_cc_valido():
    """Gera um número de Cartão de Cidadão."""
    letras = ''.join(random.choices(string.ascii_uppercase, k=2))
    numeros = ''.join(random.choices(string.digits, k=7))
    digito = random.choice(string.digits + string.ascii_uppercase)
    return f"{letras}{numeros}{digito}"


def gerar_morada():
    """Gera uma morada realista portuguesa."""
    rua = fake.street_name()
    numero = random.randint(1, 500)
    cidade = random.choice(CIDADES)
    codigo_postal = f"{random.randint(1000, 9999)}-{random.randint(100, 999)}"
    return f"{rua}, {numero}, {codigo_postal} {cidade}", cidade


def gerar_email(nome_completo):
    """Gera um email baseado no nome."""
    nomes = nome_completo.lower().split()
    formatos = [
        f"{nomes[0]}.{nomes[-1]}",
        f"{nomes[0]}{nomes[-1]}",
        f"{nomes[0][0]}{nomes[-1]}",
        f"{nomes[0]}.{nomes[-1]}{random.randint(1, 99)}",
    ]
    dominios = ["gmail.com", "hotmail.com", "outlook.pt", "sapo.pt", "mail.pt"]
    formato = random.choice(formatos)
    dominio = random.choice(dominios)
    from unicodedata import normalize
    formato = normalize('NFKD', formato).encode('ASCII', 'ignore').decode('ASCII')
    return f"{formato}@{dominio}"


def gerar_data_nascimento():
    """Gera uma data de nascimento (18-70 anos)."""
    hoje = datetime.now()
    idade = random.randint(18, 70)
    ano = hoje.year - idade
    mes = random.randint(1, 12)
    if mes in [1, 3, 5, 7, 8, 10, 12]:
        dia = random.randint(1, 31)
    elif mes == 2:
        dia = random.randint(1, 28)
    else:
        dia = random.randint(1, 30)
    return f"{dia:02d}/{mes:02d}/{ano}"


# ==============================================================================
# GERAÇÃO DE CLIENTES
# ==============================================================================

def gerar_cliente(client_id: str) -> dict:
    """
    Gera um cliente completo com dados realistas portugueses.
    Utiliza Faker pt_PT como base e complementa com dados específicos.
    """
    # Nome completo via Faker pt_PT
    nome_completo = fake.name()

    # Contactos
    email = gerar_email(nome_completo)
    telefone = gerar_telefone_portugues()
    telefone_secundario = gerar_telefone_portugues() if random.random() < 0.3 else None
    email_secundario = gerar_email(nome_completo) if random.random() < 0.15 else None

    # Dados pessoais
    nif = gerar_nif_valido()
    cc = gerar_cc_valido()
    data_nascimento = gerar_data_nascimento()
    morada, cidade = gerar_morada()
    nacionalidade = random.choice(
        ["Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa",
         "Brasileira", "Angolana", "Cabo-verdiana", "Ucraniana"]
    )
    estado_civil = random.choice(ESTADOS_CIVIS)
    profissao = random.choice(PROFISSOES)
    sexo = random.choice(["M", "F"])

    nome_pai = fake.name_male()
    nome_mae = fake.name_female()

    # Dados financeiros
    salario = round(random.uniform(850, 4500), 2)
    tipo_contrato = random.choice(TIPOS_CONTRATO)
    empresa = random.choice(EMPRESAS) if random.random() < 0.7 else None

    # Validade CC
    data_validade_cc = None
    if random.random() < 0.7:
        validade = datetime.now(timezone.utc) + timedelta(days=random.randint(-180, 1825))
        data_validade_cc = validade.strftime("%d/%m/%Y")

    cliente = {
        "id": client_id,
        "nome": nome_completo,
        "contacto": {
            "email": email,
            "email_secundario": email_secundario,
            "telefone": telefone,
            "telefone_secundario": telefone_secundario,
        },
        "dados_pessoais": {
            "nif": nif,
            "documento_id": cc,
            "data_validade_cc": data_validade_cc,
            "data_nascimento": data_nascimento,
            "birth_date": data_nascimento,
            "naturalidade": cidade,
            "nacionalidade": nacionalidade,
            "morada_fiscal": morada,
            "estado_civil": estado_civil,
            "profissao": profissao,
            "nome_pai": nome_pai,
            "nome_mae": nome_mae,
            "sexo": sexo,
        },
        "process_ids": [],
        "portal_access_code": None,
        "fonte": random.choice(FONTES),
        "tags": random.sample(["VIP", "urgente", "retorno", "referência", "online"],
                              k=random.randint(0, 2)),
        "notas": fake.sentence() if random.random() < 0.25 else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "_seed_data": True,
        "_seed_script": "seed_realistic_data",
    }

    return cliente


# ==============================================================================
# GERAÇÃO DE PROCESSOS
# ==============================================================================

def gerar_processo(
    process_number: int,
    cliente: dict,
    consultores: list,
    indexadores: list,
    intermediarios: list,
    force_fila_espera: bool = False,
) -> dict:
    """
    Gera um processo com dados realistas associado a um cliente.
    """
    # Status do processo
    if force_fila_espera:
        status = "fila_espera"
    else:
        # Distribuição realista: excluímos fila_espera da escolha aleatória
        # (garantimos pelo menos 3 separadamente)
        status_choices = [s for s in PROCESS_STATUSES if s != "fila_espera"]
        weights = STATUS_WEIGHTS[:-1]  # sem o peso de fila_espera
        status = random.choices(status_choices, weights=weights, k=1)[0]

    # Atribuir consultor
    consultor = random.choice(consultores) if consultores else None
    indexador = random.choice(indexadores) if indexadores else None
    intermediario = random.choice(intermediarios) if intermediarios else None

    # Tipo de processo
    process_type = random.choice(PROCESS_TYPES)

    # Dados imobiliários (50% dos processos)
    real_estate_data = None
    if random.random() < 0.5:
        valor_imovel = round(random.uniform(120000, 650000), 2)
        real_estate_data = {
            "ja_tem_imovel": True,
            "valor_imovel": valor_imovel,
            "localizacao": cliente.get("dados_pessoais", {}).get("naturalidade", "Lisboa"),
            "tipo_imovel": random.choice(["Apartamento", "Moradia", "T2", "T3", "T4", "Studio", "Loft"]),
            "area": random.randint(45, 250),
        }

    # Dados de crédito (60% dos processos)
    credit_data = None
    if random.random() < 0.6:
        valor_credito = round(random.uniform(80000, 400000), 2)
        credit_data = {
            "valor_credito": valor_credito,
            "prazo_anos": random.choice([15, 20, 25, 30, 35]),
            "taxa": round(random.uniform(2.5, 4.5), 2),
            "spread": round(random.uniform(0.5, 1.8), 2),
            "tipo_taxa": random.choice(["fixa", "variável", "mista"]),
            "prestacao_mensal": round(valor_credito * 0.004, 2),
        }

    # Datas — processos mais antigos nas fases mais avançadas
    dias_atras = random.randint(1, 90)
    created_at = (datetime.now(timezone.utc) - timedelta(days=dias_atras)).isoformat()
    updated_at = datetime.now(timezone.utc).isoformat()

    processo = {
        "id": str(uuid.uuid4()),
        "process_number": process_number,

        # Cliente associado
        "client_id": cliente["id"],
        "client_ids": [cliente["id"]],
        "client_name": cliente["nome"],
        "client_email": cliente["contacto"]["email"],
        "client_phone": cliente["contacto"]["telefone"],
        "client_nif": cliente["dados_pessoais"]["nif"],

        # Tipo e status
        "process_type": process_type,
        "type": process_type,
        "status": status,
        "is_active": status not in ["concluido", "arquivo", "perdido", "desistencias"],

        # Atribuições
        "assigned_consultor_id": consultor["id"] if consultor else None,
        "assigned_consultor_ids": [consultor["id"]] if consultor else [],
        "consultor_names": [consultor["name"]] if consultor else [],
        "assigned_indexacao_id": indexador["id"] if indexador else None,
        "assigned_mediador_id": intermediario["id"] if intermediario else None,
        "assigned_mediador_ids": [intermediario["id"]] if intermediario else [],
        "mediador_names": [intermediario["name"]] if intermediario else [],

        # Dados do cliente principal (denormalizado para rápido acesso)
        "personal_data": cliente.get("dados_pessoais", {}).copy(),

        # Dados imobiliários e de crédito
        "real_estate_data": real_estate_data,
        "credit_data": credit_data,

        # Co-compradores (15% dos processos)
        "co_buyers": [],
        "co_applicants": [],

        # Fonte e metadados
        "source": cliente.get("fonte", "Manual"),
        "prioridade": random.choice(["baixa", "normal", "normal", "normal", "alta"]),
        "labels": random.sample(["prioritário", "banco X", "fiador", "2º titular", "expatriado"],
                                k=random.randint(0, 1)),
        "notes": fake.sentence() if random.random() < 0.2 else None,
        "created_at": created_at,
        "updated_at": updated_at,

        # Marca de seed
        "_seed_data": True,
        "_seed_script": "seed_realistic_data",
    }

    return processo


# ==============================================================================
# GERAÇÃO DE TAREFAS
# ==============================================================================

def gerar_task(
    processo: dict,
    utilizadores: list,
    created_by_user: dict,
    dias_offset: int = 0,
) -> dict:
    """
    Gera uma tarefa associada a um processo e utilizadores.
    """
    titulo = random.choice(TITULOS_TAREFAS)
    descricao = random.choice(DESCRICOES_TAREFAS)

    # Assign a 1-2 utilizadores
    assigned_to = random.sample([u["id"] for u in utilizadores], k=random.randint(1, min(2, len(utilizadores))))
    assigned_names = [u["name"] for u in utilizadores if u["id"] in assigned_to]

    # Data de vencimento (algumas no passado = atrasadas)
    if dias_offset < 0:
        # Tarefa atrasada (due_date no passado)
        due_date = (datetime.now(timezone.utc) + timedelta(days=dias_offset)).isoformat()
        completed = random.random() < 0.2  # 20% das atrasadas foram completadas
    elif dias_offset == 0:
        # Tarefa para hoje
        due_date = datetime.now(timezone.utc).isoformat()
        completed = random.random() < 0.3
    else:
        # Tarefa futura
        due_date = (datetime.now(timezone.utc) + timedelta(days=dias_offset)).isoformat()
        completed = random.random() < 0.5

    completed_at = None
    completed_by = None
    if completed:
        completed_at = (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 3))).isoformat()
        completed_by = random.choice(assigned_to)

    # Verificar se está atrasada
    is_overdue = False
    days_until_due = None
    if due_date:
        try:
            due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
            delta = (due_dt - datetime.now(timezone.utc)).days
            days_until_due = delta
            is_overdue = delta < 0 and not completed
        except (ValueError, TypeError):
            pass

    created_at = (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 14))).isoformat()

    task = {
        "id": str(uuid.uuid4()),
        "title": titulo,
        "description": descricao,
        "assigned_to": assigned_to,
        "assigned_to_names": assigned_names,
        "process_id": processo["id"],
        "process_name": processo.get("client_name", "N/A"),
        "created_by": created_by_user["id"],
        "created_by_name": created_by_user.get("name", "Sistema"),
        "completed": completed,
        "completed_at": completed_at,
        "completed_by": completed_by,
        "due_date": due_date,
        "is_overdue": is_overdue,
        "days_until_due": days_until_due,
        "created_at": created_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),

        # Marca de seed
        "_seed_data": True,
        "_seed_script": "seed_realistic_data",
    }

    return task


# ==============================================================================
# GERAÇÃO DE TASK LOGS
# ==============================================================================

def gerar_task_log(
    processo: dict,
    user_id: str,
    status: str = "COMPLETED",
) -> dict:
    """
    Gera um TaskLog associado a um processo e utilizador.
    """
    task_types = ["PDF_GEN", "AI_ANALYSIS", "EMAIL_SEND", "DOCUMENT_UPLOAD",
                  "BULK_IMPORT", "REPORT_GEN", "DATA_EXPORT", "CUSTOM"]
    task_type = random.choice(task_types)

    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(minutes=random.randint(1, 30))).isoformat()

    completed_at = None
    if status in ["COMPLETED", "FAILED", "CANCELLED"]:
        completed_at = (now - timedelta(minutes=random.randint(0, 5))).isoformat()

    progress = 100 if status == "COMPLETED" else random.randint(0, 95)

    task_log = {
        "id": str(uuid.uuid4()),
        "task_id": str(uuid.uuid4()),
        "user_id": user_id,
        "task_type": task_type,
        "status": status,
        "title": f"{task_type} - {processo.get('client_name', 'N/A')}",
        "description": fake.sentence() if random.random() < 0.5 else None,
        "progress": progress,
        "progress_message": f"A processar {random.randint(1, 100)} itens..." if status == "PROCESSING" else None,
        "process_id": processo["id"],
        "process_name": processo.get("client_name", "N/A"),
        "result_url": f"/api/documents/{uuid.uuid4()}" if status == "COMPLETED" and random.random() < 0.5 else None,
        "result_data": None,
        "error_message": fake.sentence() if status == "FAILED" else None,
        "metadata": {},
        "created_at": now.isoformat(),
        "started_at": started_at,
        "completed_at": completed_at,
        "acknowledge_required": True,
        "acknowledged_at": None,

        # Marca de seed
        "_seed_data": True,
        "_seed_script": "seed_realistic_data",
    }

    return task_log


# ==============================================================================
# FUNÇÃO PRINCIPAL
# ==============================================================================

async def seed_realistic_data(
    clear: bool = False,
    skip_clients: bool = False,
    skip_processes: bool = False,
    skip_tasks: bool = False,
):
    """Cria dados de teste realistas na base de dados."""

    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')

    if not mongo_url or not db_name:
        print("❌ Erro: MONGO_URL e DB_NAME devem estar definidos no .env")
        sys.exit(1)

    # Mostrar informação da ligação
    safe_url = mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url
    print(f"\n📦 Base de Dados: {db_name}")
    print(f"🔗 Ligação: {safe_url}\n")

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    try:
        # ==============================================================
        # PASSO 0: Limpar dados de teste existentes se pedido
        # ==============================================================
        if clear:
            print("🗑️  A limpar dados de seed anteriores...")
            filter_query = {"_seed_script": "seed_realistic_data"}
            r_clients = await db.clients.delete_many(filter_query)
            r_processes = await db.processes.delete_many(filter_query)
            r_tasks = await db.tasks.delete_many(filter_query)
            r_tasklogs = await db.task_logs.delete_many(filter_query)
            print(f"   ✅ Removidos: {r_clients.deleted_count} clientes, "
                  f"{r_processes.deleted_count} processos, "
                  f"{r_tasks.deleted_count} tarefas, "
                  f"{r_tasklogs.deleted_count} task_logs\n")

        # ==============================================================
        # PASSO 1: Buscar utilizadores existentes (consultores, indexadores, etc.)
        # ==============================================================
        print("👥 A procurar utilizadores existentes...")

        consultores = await db.users.find({"role": "consultor", "is_active": True}).to_list(100)
        indexadores = await db.users.find({"role": "indexacao", "is_active": True}).to_list(100)
        intermediarios = await db.users.find({"role": "intermediario", "is_active": True}).to_list(100)
        administrativos = await db.users.find({"role": {"$in": ["administrativo", "diretor", "ceo", "admin"]}, "is_active": True}).to_list(100)

        # Se não existirem consultores/indexadores, criar utilizadores dummy
        if not consultores:
            print("   ⚠️  Nenhum consultor encontrado. A criar consultores dummy...")
            for nome in ["Ricardo Mendes", "Sofia Ferreira"]:
                uid = str(uuid.uuid4())
                doc = {
                    "id": uid, "email": f"{nome.split()[0].lower()}@powercell-dev.pt",
                    "name": nome, "phone": gerar_telefone_portugues(),
                    "role": "consultor", "company": "Power Real Estate",
                    "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
                    "_seed_data": True, "_seed_script": "seed_realistic_data",
                }
                await db.users.insert_one(doc)
                consultores.append(doc)
            print(f"   ✅ Criados {len(consultores)} consultores dummy")

        if not indexadores:
            print("   ⚠️  Nenhum indexador encontrado. A criar indexador dummy...")
            uid = str(uuid.uuid4())
            doc = {
                "id": uid, "email": "indexacao@powercell-dev.pt",
                "name": "Ana Costa", "phone": gerar_telefone_portugues(),
                "role": "indexacao", "company": "Power Real Estate",
                "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
                "_seed_data": True, "_seed_script": "seed_realistic_data",
            }
            await db.users.insert_one(doc)
            indexadores.append(doc)
            print(f"   ✅ Criado {len(indexadores)} indexador dummy")

        todos_utilizadores = consultores + indexadores + intermediarios + administrativos
        # Deduplicar por id
        seen = set()
        todos_utilizadores = [u for u in todos_utilizadores if u["id"] not in seen and not seen.add(u["id"])]
        print(f"   ✅ {len(consultores)} consultores, {len(indexadores)} indexadores, "
              f"{len(intermediarios)} intermediários, {len(administrativos)} admin/gestão\n")

        # ==============================================================
        # PASSO 2: Criar 30 Clientes
        # ==============================================================
        clientes = []
        if not skip_clients:
            print("🔄 A gerar 30 clientes com Faker pt_PT...")
            for i in range(30):
                client_id = str(uuid.uuid4())
                cliente = gerar_cliente(client_id)
                clientes.append(cliente)

            # Inserir clientes
            result = await db.clients.insert_many(clientes)
            print(f"   ✅ {len(result.inserted_ids)} clientes criados!\n")
        else:
            # Buscar clientes existentes para associar a processos
            print("⏭️  A usar clientes existentes (skip-clients)...")
            existing = await db.clients.find({}).to_list(30)
            clientes = list(existing)
            print(f"   ✅ {len(clientes)} clientes existentes carregados\n")

        if not clientes:
            print("❌ Nenhum cliente disponível para criar processos!")
            mongo_client.close()
            return

        # ==============================================================
        # PASSO 3: Criar ~20 Processos (pelo menos 3 em FILA_ESPERA)
        # ==============================================================
        processos = []
        if not skip_processes:
            print("🔄 A gerar ~20 processos...")

            # Buscar o último process_number
            ultimo_processo = await db.processes.find_one(
                {"process_number": {"$exists": True}},
                sort=[("process_number", -1)]
            )
            ultimo_numero = ultimo_processo.get("process_number", 0) if ultimo_processo else 0
            print(f"   📊 Último número de processo: {ultimo_numero}")

            # Selecionar 20 clientes aleatórios para ter processos
            clientes_para_processo = random.sample(clientes, k=min(20, len(clientes)))

            # Os primeiros 3 vão para FILA_ESPERA
            for i, cliente in enumerate(clientes_para_processo):
                force_fila = i < 3  # Primeiros 3 em fila_espera
                processo = gerar_processo(
                    process_number=ultimo_numero + i + 1,
                    cliente=cliente,
                    consultores=consultores,
                    indexadores=indexadores,
                    intermediarios=intermediarios,
                    force_fila_espera=force_fila,
                )
                processos.append(processo)

                # Atualizar process_ids do cliente
                await db.clients.update_one(
                    {"id": cliente["id"]},
                    {"$push": {"process_ids": processo["id"]}}
                )

            # Inserir processos
            result = await db.processes.insert_many(processos)
            print(f"   ✅ {len(result.inserted_ids)} processos criados!")

            # Contar fila_espera
            fila_count = sum(1 for p in processos if p["status"] == "fila_espera")
            print(f"   📊 {fila_count} processos em FILA_ESPERA\n")
        else:
            print("⏭️  A usar processos existentes (skip-processes)...")
            existing = await db.processes.find({}).to_list(30)
            processos = list(existing)
            print(f"   ✅ {len(processos)} processos existentes carregados\n")

        if not processos:
            print("⚠️  Nenhum processo disponível para criar tarefas!")
            mongo_client.close()
            return

        # ==============================================================
        # PASSO 4: Criar Tarefas e TaskLogs
        # ==============================================================
        if not skip_tasks:
            tasks = []
            task_logs = []

            print("🔄 A gerar tarefas e task_logs...")

            for processo in processos:
                # 2-4 tarefas por processo
                num_tasks = random.randint(2, 4)

                # Utilizador que cria (consultor ou admin)
                consultor_id = processo.get("assigned_consultor_id")
                created_by = None
                if consultor_id:
                    created_by = next((u for u in todos_utilizadores if u["id"] == consultor_id), None)
                if not created_by:
                    created_by = random.choice(todos_utilizadores) if todos_utilizadores else None

                if not created_by:
                    continue  # Sem utilizadores disponíveis

                for _ in range(num_tasks):
                    # Distribuição de datas:
                    # - 40% atrasadas (dias_offset negativo)
                    # - 20% para hoje
                    # - 40% futuras
                    r = random.random()
                    if r < 0.4:
                        dias_offset = random.randint(-14, -1)  # Atrasada 1-14 dias
                    elif r < 0.6:
                        dias_offset = 0  # Para hoje
                    else:
                        dias_offset = random.randint(1, 14)  # Futura 1-14 dias

                    task = gerar_task(
                        processo=processo,
                        utilizadores=todos_utilizadores,
                        created_by_user=created_by,
                        dias_offset=dias_offset,
                    )
                    tasks.append(task)

                # 1-2 task_logs por processo
                num_logs = random.randint(1, 2)
                for _ in range(num_logs):
                    log_status = random.choices(
                        ["COMPLETED", "COMPLETED", "COMPLETED", "PROCESSING", "FAILED", "PENDING"],
                        weights=[30, 25, 20, 10, 5, 10],
                        k=1
                    )[0]
                    user_id = created_by["id"]
                    task_log = gerar_task_log(
                        processo=processo,
                        user_id=user_id,
                        status=log_status,
                    )
                    task_logs.append(task_log)

            # Inserir tarefas
            if tasks:
                result = await db.tasks.insert_many(tasks)
                print(f"   ✅ {len(result.inserted_ids)} tarefas criadas!")

                # Estatísticas
                completadas = sum(1 for t in tasks if t["completed"])
                atrasadas = sum(1 for t in tasks if t.get("is_overdue"))
                pendentes = sum(1 for t in tasks if not t["completed"] and not t.get("is_overdue"))
                print(f"      ✅ {completadas} completadas, ⚠️ {atrasadas} atrasadas, 🕐 {pendentes} pendentes")

            # Inserir task_logs
            if task_logs:
                result = await db.task_logs.insert_many(task_logs)
                print(f"   ✅ {len(result.inserted_ids)} task_logs criados!\n")
        else:
            print("⏭️  Tarefas e task_logs ignorados (skip-tasks)\n")

        # ==============================================================
        # ESTATÍSTICAS FINAIS
        # ==============================================================
        print("=" * 60)
        print("📊 RESUMO FINAL")
        print("=" * 60)

        total_clientes = await db.clients.count_documents({"_seed_script": "seed_realistic_data"})
        total_processos = await db.processes.count_documents({"_seed_script": "seed_realistic_data"})
        total_tarefas = await db.tasks.count_documents({"_seed_script": "seed_realistic_data"})
        total_tasklogs = await db.task_logs.count_documents({"_seed_script": "seed_realistic_data"})

        print(f"   👤 Clientes:    {total_clientes}")
        print(f"   📁 Processos:   {total_processos}")
        print(f"   ✅ Tarefas:     {total_tarefas}")
        print(f"   📋 Task Logs:   {total_tasklogs}")

        # Distribuição por status
        print("\n📈 Distribuição de processos por fase:")
        pipeline = [
            {"$match": {"_seed_script": "seed_realistic_data"}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        distribuicao = await db.processes.aggregate(pipeline).to_list(20)
        for d in distribuicao:
            print(f"   {d['_id']}: {d['count']} processos")

        # Estatísticas de tarefas
        pipeline_tasks = [
            {"$match": {"_seed_script": "seed_realistic_data"}},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "completadas": {"$sum": {"$cond": [{"$eq": ["$completed", True]}, 1, 0]}},
                "atrasadas": {"$sum": {"$cond": [{"$eq": ["$is_overdue", True]}, 1, 0]}},
            }}
        ]
        stats = await db.tasks.aggregate(pipeline_tasks).to_list(1)
        if stats:
            s = stats[0]
            pendentes = s["total"] - s["completadas"] - s["atrasadas"]
            print(f"\n📊 Estatísticas de tarefas:")
            print(f"   Total: {s['total']} | Completadas: {s['completadas']} | "
                  f"Atrasadas: {s['atrasadas']} | Pendentes: {max(pendentes, 0)}")

        print("\n" + "=" * 60)
        print("💡 Para remover estes dados, execute:")
        print("   python scripts/seed_realistic_data.py --clear")
        print("=" * 60)

    finally:
        mongo_client.close()


def main():
    """Função principal."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed de Dados Realistas - PowerCell (Faker pt_PT)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Dados gerados:
  - 30 clientes com dados portugueses realistas
  - ~20 processos distribuídos por 15 fases do workflow
  - Pelo menos 3 processos em FILA_ESPERA
  - Tarefas com datas variadas (completadas, atrasadas, pendentes)
  - TaskLogs para o Dashboard do CEO

Exemplos:
  python scripts/seed_realistic_data.py                    # Cria tudo
  python scripts/seed_realistic_data.py --clear            # Remove dados anteriores e cria novos
  python scripts/seed_realistic_data.py --skip-tasks       # Não cria tarefas
        """
    )

    parser.add_argument(
        "--clear", action="store_true",
        help="Remove dados de seed anteriores antes de criar novos"
    )
    parser.add_argument(
        "--skip-clients", action="store_true",
        help="Não criar clientes (usa existentes)"
    )
    parser.add_argument(
        "--skip-processes", action="store_true",
        help="Não criar processos (usa existentes)"
    )
    parser.add_argument(
        "--skip-tasks", action="store_true",
        help="Não criar tarefas e task_logs"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🎯 SEED DE DADOS REALISTAS - POWERCELL")
    print("   Faker pt_PT + Dados Portugueses Realistas")
    print("=" * 60)

    asyncio.run(seed_realistic_data(
        clear=args.clear,
        skip_clients=args.skip_clients,
        skip_processes=args.skip_processes,
        skip_tasks=args.skip_tasks,
    ))


if __name__ == "__main__":
    main()
