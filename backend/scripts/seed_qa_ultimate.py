#!/usr/bin/env python3
"""
====================================================================
SEED QA ULTIMATE — PowerCell CRM
====================================================================
Script de seeding definitivo para QA. Gera 15-20 processos com dados
100% realistas e todos os campos preenchidos, cobrindo:

1. 4 processos em pre_registo (Triagem — apenas nome/email/telefone)
2. Diversidade de titulares (solteiros + casais com 2º titular)
3. 8+ processos ativos com personal_data, financial_data, real_estate_data,
   credit_data 100% preenchidos (para DSTI funcionar)
4. 2+ atividades/notas por processo ativo
5. Atribuições mistas (consultores, intermediários, indexação)

USO:
    cd backend
    python scripts/seed_qa_ultimate.py                    # seed com defaults
    python scripts/seed_qa_ultimate.py --clear            # limpar dados seed anteriores
    python scripts/seed_qa_ultimate.py --num-processes 25 # customizar quantidade
    python scripts/seed_qa_ultimate.py --dry-run          # simular sem escrever

REQUISITOS:
    - backend/.env com MONGO_URL e DB_NAME definidos
    - pip install faker motor python-dotenv cryptography

PACOTE BY — The Ultimate QA Seed Script
====================================================================
"""
import asyncio
import os
import sys
import uuid
import random
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Bootstrap — adicionar backend/ ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from faker import Faker
    fake = Faker('pt_PT')
except ImportError:
    print("❌ faker não instalado. Instale com: pip install faker")
    sys.exit(1)

# Carregar .env do backend/
load_dotenv(Path(__file__).parent.parent / '.env')

SEED_SCRIPT = "seed_qa_ultimate"

# ====================================================================
# HELPERS
# ====================================================================

def iso(dt=None) -> str:
    """ISO 8601 string com timezone UTC."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

def seed_mark() -> dict:
    """Marca para identificar dados de seed (permite --clear seletivo)."""
    return {"_seed_data": True, "_seed_script": SEED_SCRIPT}

def gerar_nif() -> str:
    """Gera um NIF português válido (9 dígitos com dígito de controlo)."""
    while True:
        nif = str(random.randint(100000000, 999999999))
        # Validação do dígito de controlo
        total = 0
        for i, digit in enumerate(nif[:8]):
            total += int(digit) * (9 - i)
        resto = total % 11
        check = 11 - resto if resto >= 2 else 0
        if int(nif[8]) == check:
            return nif

def gerar_telefone() -> str:
    """Gera número de telefone português (9X XXX XXXX)."""
    return f"9{random.randint(10, 69)} {random.randint(100, 999)} {random.randint(1000, 9999)}"

def gerar_cc() -> str:
    """Gera número de Cartão de Cidadão (8 dígitos + 1 alfanumérico)."""
    return f"{random.randint(10000000, 99999999)}{random.choice('TRSW')}"


# ====================================================================
# DADOS REALISTAS (catálogos estáticos para maxima verosimilhança)
# ====================================================================

NOMES_PT_MASCULINO = [
    "João Silva", "Pedro Borges", "Tiago Santos", "Rui Costa", "Miguel Oliveira",
    "André Pereira", "Bruno Carvalho", "Hugo Fernandes", "Nuno Rodrigues", "Paulo Martins",
    "Diogo Sousa", "Filipe Ribeiro", "Carlos Almeida", "Rafael Gomes", "Eduardo Lopes",
]

NOMES_PT_FEMININO = [
    "Maria Santos", "Ana Silva", "Catarina Costa", "Sofia Pereira", "Rita Oliveira",
    "Patrícia Carvalho", "Inês Fernandes", "Sara Rodrigues", "Marta Gomes", "Joana Lopes",
    "Helena Sousa", "Teresa Ribeiro", "Carla Almeida", "Diana Martins", "Beatriz Correia",
]

PROFISSOES = [
    "Engenheiro Civil", "Médica", "Professor", "Advogada", "Contabilista",
    "Enfermeiro", "Arquiteta", "Gestor de Vendas", "Programador", "Psicóloga",
    "Farmacêutico", "Designer", "Comercial", "Fisioterapeuta", "Economista",
]

BANCOS = ["BCP", "Novo Banco", "Santander", "CGD", "ActivoBank", "Bankinter", "Abanca", "Crédito Agrícola"]
TIPOS_IMOVEL = ["Apartamento", "Moradia", "Terreno", "Loja", "Escritório"]
TIPOLOGIAS = ["T1", "T2", "T3", "T4", "T5+"]
ESTADOS_CIVIS = ["Solteiro", "Casado", "União de Facto", "Divorciado"]
CONCELHOS = ["Lisboa", "Sintra", "Cascais", "Oeiras", "Loures", "Amadora", "Porto", "Vila Nova de Gaia", "Matosinhos", "Coimbra"]

DISTRIBUICAO_STATUS = [
    # (status, is_active, quantidade, descrição)
    ("pre_registo",          True,  4, "Triagem — cliente a preencher portal"),
    ("clientes_espera",      True,  2, "Clientes em espera"),
    ("documentacao",         True,  2, "Fase documental"),
    ("analise",              True,  2, "Análise do processo"),
    ("pre_aprovacao",        True,  1, "Pré-aprovação"),
    ("credito_aprovado",     True,  2, "Crédito aprovado"),
    ("cpcv",                 True,  1, "CPCV"),
    ("escritura",            True,  2, "Escritura agendada"),
    ("concluido",            False, 1, "Concluído"),
    ("desistencias",         False, 1, "Desistência"),
]
# Total: 4 + 2 + 2 + 2 + 1 + 2 + 1 + 2 + 1 + 1 = 18 processos

STATUS_ATIVOS_COMPLETOS = [
    "documentacao", "analise", "pre_aprovacao", "credito_aprovado",
    "cpcv", "escritura"
]  # Nestes, preencher TODOS os dados

NOTAS_EXEMPLO = [
    "Cliente enviou todos os documentos via portal. A aguardar validação do indexador.",
    "Contactado por telefone — confirmou interesse no imóvel T3 em Sintra.",
    "Banco solicitou comprovativo adicional de rendimentos. Já foi submetido pelo cliente.",
    "Avaliação do imóvel concluída — valor confirmado em 285.000€.",
    "Cliente pediu para adiar a escritura para meados do próximo mês.",
    "Spread negociado a 0,85% com o BCP. A aguardar aprovação formal.",
    "DSTI calculado em 31,2% — dentro dos limites. Processo segue para análise bancária.",
    "Cliente referiu ter outro crédito automóvel com prestação de 320€/mês.",
    "Imóvel visitado no fim de semana. Cliente satisfeito, quer avançar com proposta.",
    "Documentação complementar enviada: IRS 2023 + 3 últimos recibos de vencimento.",
]


# ====================================================================
# GERAÇÃO DE CLIENTES
# ====================================================================

def gerar_cliente(idx: int, genero: str = None) -> dict:
    """Gera um cliente completo com dados realistas."""
    if genero is None:
        genero = random.choice(["M", "F"])

    if genero == "M":
        nome = random.choice(NOMES_PT_MASCULINO)
    else:
        nome = random.choice(NOMES_PT_FEMININO)

    primeiro_nome = nome.split()[0].lower()
    email = f"{primeiro_nome}.{idx}@emailpt.pt"
    telefone = gerar_telefone()
    nif = gerar_nif()

    estado_civil = random.choice(ESTADOS_CIVIS)
    profissao = random.choice(PROFISSOES)
    concelho = random.choice(CONCELHOS)

    cliente = {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "contacto": {
            "email": email,
            "email_secundario": None,
            "telefone": telefone,
            "telefone_secundario": None,
        },
        "dados_pessoais": {
            "nif": nif,
            "documento_id": gerar_cc(),
            "data_validade_cc": fake.date_between(start_date='+1y', end_date='+10y').strftime("%d/%m/%Y"),
            "data_nascimento": fake.date_between(start_date='-55y', end_date='-25y').strftime("%d/%m/%Y"),
            "birth_date": None,
            "naturalidade": concelho,
            "nacionalidade": "Portuguesa",
            "morada_fiscal": f"Rua {fake.street_name()}, {random.randint(1, 200)}, {concelho}",
            "estado_civil": estado_civil,
            "profissao": profissao,
            "nome_pai": fake.name_male(),
            "nome_mae": fake.name_female(),
            "sexo": genero,
        },
        "dados_financeiros": {},
        "financial_data": {},
        "process_ids": [],
        "portal_access_code": f"{random.choice('ABCDEFGHJKMNPQRSTUVWXYZ')}{''.join(random.choices('0123456789', k=2))}-{random.choice('ABCDEFGHJKMNPQRSTUVWXYZ')}{''.join(random.choices('0123456789', k=2))}",
        "fonte": random.choice(["Manual", "Website", "Indicação", "Portal"]),
        "tags": [],
        "notas": None,
        "lead_status": "converted",
        "registration_completed": True,
        "assigned_to": None,
        "assigned_at": None,
        "created_at": iso(datetime.now(timezone.utc) - timedelta(days=random.randint(1, 60))),
        "updated_at": iso(),
        "created_by": SEED_SCRIPT,
        "is_active": True,
        **seed_mark(),
    }
    return cliente


def gerar_cliente_pre_registo(idx: int) -> dict:
    """Gera um cliente minimalista (apenas nome/email/telefone) para pré-registo."""
    genero = random.choice(["M", "F"])
    if genero == "M":
        nome = random.choice(NOMES_PT_MASCULINO)
    else:
        nome = random.choice(NOMES_PT_FEMININO)

    primeiro_nome = nome.split()[0].lower()
    email = f"{primeiro_nome}.{idx}@emailpt.pt"

    return {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "contacto": {
            "email": email,
            "email_secundario": None,
            "telefone": gerar_telefone(),
            "telefone_secundario": None,
        },
        "dados_pessoais": {},  # Vazio — simula cliente que ainda não preencheu o portal
        "dados_financeiros": {},
        "financial_data": {},
        "process_ids": [],
        "portal_access_code": None,
        "fonte": "Portal",
        "tags": [],
        "notas": None,
        "lead_status": "new",
        "registration_completed": False,
        "assigned_to": None,
        "assigned_at": None,
        "created_at": iso(datetime.now(timezone.utc) - timedelta(days=random.randint(1, 10))),
        "updated_at": iso(),
        "created_by": SEED_SCRIPT,
        "is_active": True,
        **seed_mark(),
    }


# ====================================================================
# GERAÇÃO DE DADOS DE PROCESSO
# ====================================================================

def gerar_personal_data(cliente: dict) -> dict:
    """Copia e enriquece dados pessoais do cliente para o processo."""
    dp = cliente.get("dados_pessoais", {})
    return {
        "nome": cliente["nome"],
        "nif": dp.get("nif", ""),
        "email": cliente["contacto"]["email"],
        "telefone": cliente["contacto"]["telefone"],
        "documento_id": dp.get("documento_id", ""),
        "data_validade_cc": dp.get("data_validade_cc", ""),
        "data_nascimento": dp.get("data_nascimento", ""),
        "birth_date": dp.get("birth_date", dp.get("data_nascimento", "")),
        "naturalidade": dp.get("naturalidade", "Portugal"),
        "nacionalidade": dp.get("nacionalidade", "Portuguesa"),
        "morada_fiscal": dp.get("morada_fiscal", ""),
        "estado_civil": dp.get("estado_civil", "Solteiro"),
        "profissao": dp.get("profissao", ""),
        "sexo": dp.get("sexo", "M"),
        "dependentes": random.randint(0, 3),
    }


def gerar_financial_data() -> dict:
    """Gera dados financeiros completos para cálculo de DSTI."""
    salario_bruto = random.choice([1800, 2200, 2800, 3500, 4200, 5500, 6800])
    salario_liquido = round(salario_bruto * random.uniform(0.72, 0.82), 2)
    renda_mensal = random.choice([0, 350, 600, 850, 1200])
    prestacao_auto = random.choice([0, 180, 250, 320, 450])
    outros_creditos = random.choice([0, 100, 200, 350])
    capital_proprio = random.choice([0, 15000, 30000, 50000, 75000, 100000])
    valor_entrada = round(capital_proprio * random.uniform(0.8, 1.0), 2)

    return {
        "salario_bruto": salario_bruto,
        "salario_liquido": salario_liquido,
        "vencimento_mensal": salario_bruto,
        "outros_rendimentos": random.choice([0, 150, 300, 500]),
        "rendimento_total": salario_bruto + random.choice([0, 150, 300, 500]),
        "tipo_contrato": random.choice(["efetivo", "termo_certo", "cdi"]),
        "empresa": fake.company(),
        "antiguidade_anos": random.randint(1, 20),
        "irs_taxa_retencao": random.choice([0.18, 0.23, 0.28, 0.35]),
        "irs_retido_mensal": round(salario_bruto * random.choice([0.18, 0.23, 0.28]), 2),
        "renda_mensal": renda_mensal,
        "prestacao_auto": prestacao_auto,
        "outros_creditos": outros_creditos,
        "despesas_total": renda_mensal + prestacao_auto + outros_creditos,
        "capitais_proprios": capital_proprio,
        "valor_entrada": valor_entrada,
        "dependentes": random.randint(0, 3),
    }


def gerar_real_estate_data() -> dict:
    """Gera dados do imóvel completos."""
    valor_imovel = random.choice([145000, 180000, 220000, 285000, 350000, 420000, 550000])
    concelho = random.choice(CONCELHOS)
    return {
        "tipo_imovel": random.choice(TIPOS_IMOVEL),
        "num_quartos": random.randint(1, 5),
        "localizacao": concelho,
        "ja_tem_imovel": True,
        "has_property": True,
        "valor_imovel": valor_imovel,
        "codigo_postal": f"{random.randint(1000, 4999)}-{random.randint(100, 999)}",
        "localidade": concelho,
        "freguesia": f"União de Freguesias de {concelho}",
        "concelho": concelho,
        "tipologia": random.choice(TIPOLOGIAS),
        "area_bruta": random.randint(75, 250),
        "area_util": random.randint(60, 200),
        "fracao": f"{random.choice('ABCDEFGH')}",
        "artigo_matricial": f"{random.randint(1000, 9999)}/{random.randint(1900, 2024)}",
        "conservatoria": f"Conservatória do Registo Predial de {concelho}",
        "numero_predial": f"{random.randint(1000, 9999)}",
        "certificado_energetico": random.choice(["A", "B", "B-", "C", "D", "E"]),
        "estacionamento": random.randint(0, 2),
        "arrecadacao": random.choice([0, 1]),
        "descricao_imovel": f"{random.choice(TIPOLOGIAS)} em {concelho}, com {random.randint(75, 250)}m², excelente estado.",
        "valor_patrimonial": round(valor_imovel * 0.85, 2),
        "data_cpcv": fake.date_between(start_date='-30d', end_date='+30d').strftime("%Y-%m-%d") if random.random() > 0.5 else None,
        "data_escritura_prevista": fake.date_between(start_date='+30d', end_date='+120d').strftime("%Y-%m-%d") if random.random() > 0.5 else None,
        "prazo_escritura_dias": random.choice([30, 45, 60, 90]),
        "data_entrega_chaves": fake.date_between(start_date='+60d', end_date='+180d').strftime("%Y-%m-%d") if random.random() > 0.5 else None,
        "condicao_suspensiva": "Obtenção de financiamento bancário" if random.random() > 0.5 else None,
        "observacoes_cpcv": None,
        "link_idealista": f"https://www.idealista.pt/imovel/{random.randint(100000, 999999)}",
    }


def gerar_credit_data(financial: dict, real_estate: dict) -> dict:
    """Gera dados de crédito completos (para DSTI funcionar)."""
    valor_imovel = real_estate.get("valor_imovel", 250000)
    capital_proprio = financial.get("capitais_proprios", 0)
    montante_financiado = max(valor_imovel - capital_proprio, 50000)
    prazo_anos = random.choice([15, 20, 25, 30, 35])
    spread = round(random.uniform(0.5, 1.5), 2)
    taxa_euribor = round(random.uniform(0.5, 3.5), 2)
    taxa_anual = round(taxa_euribor + spread, 2)
    taxa_mensal = taxa_anual / 100 / 12
    num_prestacoes = prazo_anos * 12
    prestacao_mensal = round(montante_financiado * (taxa_mensal * (1 + taxa_mensal) ** num_prestacoes) / ((1 + taxa_mensal) ** num_prestacoes - 1), 2)

    return {
        "requested_amount": montante_financiado,
        "montante_financiado": montante_financiado,
        "loan_term_years": prazo_anos,
        "prazo_meses": num_prestacoes,
        "interest_rate": taxa_anual,
        "taxa_anual": taxa_anual,
        "spread": spread,
        "euribor": taxa_euribor,
        "tipo_taxa": random.choice(["Fixa", "Variável", "Mista"]),
        "taxa_fixa": taxa_anual if random.random() > 0.5 else None,
        "monthly_payment": prestacao_mensal,
        "prestacao_mensal": prestacao_mensal,
        "bank_name": random.choice(BANCOS),
        "banco": random.choice(BANCOS),
        "bank_branch": random.choice(["Centro", "Alvalade", "Cascais", "Sintra", "Porto Boavista"]),
        "bank_approval_date": fake.date_between(start_date='-30d', end_date='+30d').strftime("%Y-%m-%d") if random.random() > 0.4 else None,
        "bank_approval_notes": "Aprovado sujeito a avaliação do imóvel" if random.random() > 0.5 else None,
        "valuation_value": round(valor_imovel * random.uniform(0.90, 1.05), 2),
        "valuation_date": fake.date_between(start_date='-60d', end_date='now').strftime("%Y-%m-%d"),
        "valuation_bank": random.choice(BANCOS),
        "valuation_notes": None,
        "admission_year": random.randint(2010, 2024),
        "is_ppe": random.random() < 0.05,
        "is_fpe": random.random() < 0.03,
        "credit_incidents": None,
    }


def gerar_titular2_data() -> dict:
    """Gera dados completos do 2º titular (cônjuge/companheiro)."""
    genero = random.choice(["M", "F"])
    if genero == "M":
        nome = random.choice(NOMES_PT_MASCULINO)
    else:
        nome = random.choice(NOMES_PT_FEMININO)

    salario = random.choice([1500, 1800, 2200, 2800, 3500])

    return {
        "name": nome,
        "nome": nome,
        "email": f"{nome.split()[0].lower()}.{random.randint(1, 99)}@emailpt.pt",
        "phone": gerar_telefone(),
        "telefone": gerar_telefone(),
        "nif": gerar_nif(),
        "documento_id": gerar_cc(),
        "data_nascimento": fake.date_between(start_date='-55y', end_date='-25y').strftime("%d/%m/%Y"),
        "birth_date": None,
        "morada_fiscal": f"Rua {fake.street_name()}, {random.randint(1, 200)}, {random.choice(CONCELHOS)}",
        "estado_civil": random.choice(ESTADOS_CIVIS),
        "profissao": random.choice(PROFISSOES),
        "nacionalidade": "Portuguesa",
        "naturalidade": random.choice(CONCELHOS),
        "sexo": genero,
        "relacao": random.choice(["Cônjuge", "Companheiro(a)"]),
        "salario": salario,
        "tipo_contrato": random.choice(["efetivo", "termo_certo"]),
        "empresa": fake.company(),
        "rendimento_total": salario,
        "irs_taxa_retencao": random.choice([0.18, 0.23, 0.28]),
        "dependentes": random.randint(0, 2),
    }


def gerar_co_buyer(titular2: dict) -> dict:
    """Gera entrada de co_buyer a partir do titular2_data."""
    return {
        "name": titular2["name"],
        "email": titular2["email"],
        "nif": titular2["nif"],
        "phone": titular2["phone"],
        "client_id": str(uuid.uuid4()),
        "relacao": titular2["relacao"],
    }


def gerar_atividade(process_id: str, user: dict, dias_atras: int = None) -> dict:
    """Gera uma atividade/nota para o processo."""
    if dias_atras is None:
        dias_atras = random.randint(0, 30)
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user.get("id", "system") if user else "system",
        "user_name": user.get("name", "Sistema") if user else "Sistema",
        "user_role": user.get("role", "consultor") if user else "system",
        "comment": random.choice(NOTAS_EXEMPLO),
        "created_at": iso(datetime.now(timezone.utc) - timedelta(days=dias_atras)),
        **seed_mark(),
    }


def gerar_historico(process_id: str, user: dict, status: str, dias_atras: int = None) -> dict:
    """Gera entrada de histórico (status change)."""
    if dias_atras is None:
        dias_atras = random.randint(1, 30)
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user.get("id", "system") if user else "system",
        "user_name": user.get("name", "Sistema") if user else "Sistema",
        "action": f"Processo movido para {status}",
        "field": "status",
        "old_value": random.choice(["clientes_espera", "documentacao", "analise"]),
        "new_value": status,
        "created_at": iso(datetime.now(timezone.utc) - timedelta(days=dias_atras)),
        **seed_mark(),
    }


# ====================================================================
# WORKFLOW STATUSES (alinhados com o enum canónico ProcessStatus)
# ====================================================================

WORKFLOW_STATUSES = [
    {"name": "pre_registo",      "label": "Pré-Registo",            "order": 0,  "color": "slate",   "is_active": True,  "visible_in_portal": True},
    {"name": "clientes_espera",  "label": "Clientes em Espera",     "order": 1,  "color": "amber",   "is_active": True,  "visible_in_portal": True},
    {"name": "documentacao",     "label": "Documentação",           "order": 2,  "color": "blue",    "is_active": True,  "visible_in_portal": True},
    {"name": "analise",          "label": "Análise",                "order": 3,  "color": "indigo",  "is_active": True,  "visible_in_portal": True},
    {"name": "pre_aprovacao",    "label": "Pré-Aprovação",          "order": 4,  "color": "cyan",    "is_active": True,  "visible_in_portal": True},
    {"name": "credito_aprovado", "label": "Crédito Aprovado",       "order": 5,  "color": "green",   "is_active": True,  "visible_in_portal": True},
    {"name": "pedido_avaliacao", "label": "Pedido de Avaliação",    "order": 6,  "color": "teal",    "is_active": True,  "visible_in_portal": True},
    {"name": "avaliacao",        "label": "Avaliação",              "order": 7,  "color": "teal",    "is_active": True,  "visible_in_portal": True},
    {"name": "cpcv",             "label": "CPCV",                   "order": 8,  "color": "violet",  "is_active": True,  "visible_in_portal": True},
    {"name": "minuta",           "label": "Minuta",                 "order": 9,  "color": "purple",  "is_active": True,  "visible_in_portal": True},
    {"name": "escritura",        "label": "Escritura",              "order": 10, "color": "emerald", "is_active": True,  "visible_in_portal": True},
    {"name": "concluido",        "label": "Concluído",              "order": 11, "color": "gray",    "is_active": False, "visible_in_portal": False},
    {"name": "arquivo",          "label": "Arquivo",                "order": 12, "color": "gray",    "is_active": False, "visible_in_portal": False},
    {"name": "perdido",          "label": "Perdido",                "order": 13, "color": "red",     "is_active": False, "visible_in_portal": False},
    {"name": "desistencias",     "label": "Desistências",           "order": 14, "color": "red",     "is_active": False, "visible_in_portal": False},
    {"name": "fila_espera",      "label": "Fila de Espera",         "order": 15, "color": "orange",  "is_active": True,  "visible_in_portal": False},
]


async def ensure_workflow_statuses(db):
    """Garante que os 16 workflow_statuses existem na BD."""
    for ws in WORKFLOW_STATUSES:
        existing = await db.workflow_statuses.find_one({"name": ws["name"]})
        if existing:
            # Atualizar campos em falta
            updates = {}
            for key in ("label", "color", "order", "is_active", "visible_in_portal"):
                if key not in existing or existing[key] is None:
                    updates[key] = ws[key]
            if updates:
                await db.workflow_statuses.update_one({"name": ws["name"]}, {"$set": updates})
        else:
            doc = {
                "id": str(uuid.uuid4()),
                "name": ws["name"],
                "label": ws["label"],
                "order": ws["order"],
                "color": ws["color"],
                "description": ws["label"],
                "is_default": ws["name"] == "clientes_espera",
                "internal_code": str(ws["order"]).zfill(2),
                "is_active": ws["is_active"],
                "visible_in_portal": ws["visible_in_portal"],
                "portal_label": ws["label"] if ws["visible_in_portal"] else None,
                "created_at": iso(),
                **seed_mark(),
            }
            await db.workflow_statuses.insert_one(doc)


# ====================================================================
# RESOLVER UTILIZADORES (criar dummies se não existirem)
# ====================================================================

async def resolve_users(db) -> dict:
    """Resolve utilizadores por role. Cria dummies se não existirem."""
    result = {"consultores": [], "indexadores": [], "intermediarios": [], "gestores": []}

    for role_key, role_name in [
        ("consultores", "consultor"),
        ("indexadores", "indexacao"),
        ("intermediarios", "intermediario"),
    ]:
        users = await db.users.find({"role": role_name, "is_active": {"$ne": False}}).to_list(100)
        if not users:
            # Criar 2 dummies por role
            for i in range(2):
                nome = fake.name()
                user_doc = {
                    "id": str(uuid.uuid4()),
                    "email": f"{nome.split()[0].lower()}.{role_name}{i}@powercell-dev.pt",
                    "name": nome,
                    "phone": gerar_telefone(),
                    "role": role_name,
                    "company": "Power Real Estate",
                    "is_active": True,
                    "created_at": iso(),
                    **seed_mark(),
                }
                await db.users.insert_one(user_doc)
                users.append(user_doc)
        result[role_key] = users

    # Gestores (admin/ceo/diretor)
    gestores = await db.users.find({"role": {"$in": ["admin", "ceo", "diretor"]}, "is_active": {"$ne": False}}).to_list(100)
    if not gestores:
        nome = fake.name()
        admin_doc = {
            "id": str(uuid.uuid4()),
            "email": f"admin@powercell-dev.pt",
            "name": nome,
            "phone": gerar_telefone(),
            "role": "admin",
            "company": "Power Real Estate",
            "is_active": True,
            "created_at": iso(),
            **seed_mark(),
        }
        await db.users.insert_one(admin_doc)
        gestores = [admin_doc]
    result["gestores"] = gestores

    return result


# ====================================================================
# LIMPEZA DE DADOS DE SEED ANTERIORES
# ====================================================================

async def clear_seed_data(db):
    """Remove todos os documentos marcados com _seed_script == SEED_SCRIPT."""
    filtro = {"_seed_script": SEED_SCRIPT}
    collections = ["processes", "clients", "activities", "history", "users", "workflow_statuses"]
    total_removed = 0
    for col_name in collections:
        result = await db[col_name].delete_many(filtro)
        total_removed += result.deleted_count
        if result.deleted_count > 0:
            print(f"  🗑️  {col_name}: {result.deleted_count} documentos removidos")
    print(f"  ✅ Total removido: {total_removed} documentos\n")


# ====================================================================
# GERAÇÃO E INSERÇÃO DE PROCESSOS
# ====================================================================

async def run_seed(db, num_processes: int = 18, dry_run: bool = False):
    """Executa o seeding completo."""
    print("=" * 60)
    print(f"🚀 SEED QA ULTIMATE — {SEED_SCRIPT}")
    print(f"   Alvo: {num_processes} processos")
    print(f"   Dry run: {dry_run}")
    print("=" * 60)

    if not dry_run:
        # 1. Garantir workflow_statuses
        print("\n📋 A garantir workflow_statuses...")
        await ensure_workflow_statuses(db)
        print(f"   ✅ {len(WORKFLOW_STATUSES)} estados garantidos")

        # 2. Resolver utilizadores
        print("\n👥 A resolver utilizadores (consultores, indexadores, intermediários)...")
        users = await resolve_users(db)
        print(f"   ✅ {len(users['consultores'])} consultores, {len(users['indexadores'])} indexadores, "
              f"{len(users['intermediarios'])} intermediários, {len(users['gestores'])} gestores")

    # 3. Calcular próximo process_number
    last_process = await db.processes.find_one({}, sort=[("process_number", -1)])
    next_number = (last_process.get("process_number", 0) if last_process else 0) + 1
    print(f"\n🔢 Próximo número de processo: {next_number}")

    # 4. Gerar clientes e processos
    clientes_criados = []
    processos_criados = []
    atividades_criadas = []
    historico_criado = []
    cliente_idx = 0

    for status, is_active, qtd, descricao in DISTRIBUICAO_STATUS:
        for _ in range(qtd):
            if len(processos_criados) >= num_processes:
                break

            is_pre_registo = (status == "pre_registo")
            is_ativo_completo = status in STATUS_ATIVOS_COMPLETOS

            # Gerar cliente
            if is_pre_registo:
                cliente = gerar_cliente_pre_registo(cliente_idx)
            else:
                cliente = gerar_cliente(cliente_idx)
            cliente_idx += 1

            # Determinar se é casal (20% de probabilidade, exceto pre_registo)
            is_casal = not is_pre_registo and random.random() < 0.25

            # Gerar 2º titular se for casal
            titular2 = None
            co_buyers = []
            segundo_cliente = None
            if is_casal:
                titular2 = gerar_titular2_data()
                co_buyers = [gerar_co_buyer(titular2)]
                # Criar 2º cliente na BD
                segundo_cliente = gerar_cliente(cliente_idx)
                cliente_idx += 1
                segundo_cliente["nome"] = titular2["nome"]
                segundo_cliente["contacto"]["email"] = titular2["email"]
                segundo_cliente["contacto"]["telefone"] = titular2["telefone"]
                segundo_cliente["dados_pessoais"]["nif"] = titular2["nif"]
                segundo_cliente["dados_pessoais"]["estado_civil"] = titular2["estado_civil"]
                segundo_cliente["dados_pessoais"]["profissao"] = titular2["profissao"]

            # Atribuição mista
            if not dry_run:
                consultor = random.choice(users["consultores"]) if users["consultores"] else None
                intermediario = random.choice(users["intermediarios"]) if random.random() > 0.5 and users["intermediarios"] else None
                indexador = random.choice(users["indexadores"]) if (not is_pre_registo and status not in ["concluido", "desistencias"] and random.random() > 0.3 and users["indexadores"]) else None
            else:
                consultor = {"id": "dummy-consultor", "name": "Consultor Dummy", "role": "consultor"}
                intermediario = {"id": "dummy-intermed", "name": "Intermediário Dummy", "role": "intermediario"}
                indexador = {"id": "dummy-index", "name": "Indexador Dummy", "role": "indexacao"}

            # Personal/Financial/RealEstate/Credit data
            personal_data = gerar_personal_data(cliente) if not is_pre_registo else {}
            financial_data = gerar_financial_data() if is_ativo_completo else {}
            real_estate_data = gerar_real_estate_data() if is_ativo_completo else {}
            credit_data = gerar_credit_data(financial_data, real_estate_data) if is_ativo_completo else {}

            # Construir processo
            processo = {
                "id": str(uuid.uuid4()),
                "process_number": next_number,
                "client_id": cliente["id"],
                "client_ids": [cliente["id"]] + ([segundo_cliente["id"]] if segundo_cliente else []),
                "client_name": cliente["nome"],
                "client_email": cliente["contacto"]["email"],
                "client_phone": cliente["contacto"]["telefone"],
                "client_nif": cliente.get("dados_pessoais", {}).get("nif", ""),
                "second_client_id": segundo_cliente["id"] if segundo_cliente else None,
                "second_client_name": titular2["nome"] if titular2 else None,
                "process_type": "credito_habitacao",
                "type": "credito_habitacao",
                "status": status,
                "is_active": is_active,
                "is_deleted": False,
                "is_indexed": True if status in ["credito_aprovado", "cpcv", "escritura", "concluido"] else (False if not is_pre_registo else None),
                # Atribuições
                "assigned_consultor_id": consultor["id"] if consultor else None,
                "assigned_consultor_ids": [consultor["id"]] if consultor else [],
                "consultor_name": consultor["name"] if consultor else None,
                "consultor_names": [consultor["name"]] if consultor else [],
                "consultor_id": consultor["id"] if consultor else None,
                "assigned_indexacao_id": indexador["id"] if indexador else None,
                "indexacao_name": indexador["name"] if indexador else None,
                "assigned_mediador_id": intermediario["id"] if intermediario else None,
                "assigned_mediador_ids": [intermediario["id"]] if intermediario else [],
                "mediador_name": intermediario["name"] if intermediario else None,
                "mediador_names": [intermediario["name"]] if intermediario else [],
                "assigned_parceiro_id": None,
                "parceiro_name": None,
                # Dados de negócio
                "personal_data": personal_data,
                "financial_data": financial_data,
                "finance_data": financial_data,
                "real_estate_data": real_estate_data,
                "credit_data": credit_data,
                # 2º Titular
                "compra_sozinho": not is_casal,
                "titular2_data": titular2,
                "co_buyers": co_buyers if co_buyers else None,
                "co_applicants": [titular2] if titular2 else [],
                "vendedor": None,
                "mediador": None,
                # Metadados
                "source": cliente.get("fonte", "Manual"),
                "prioridade": random.choice(["baixa", "normal", "alta"]),
                "labels": [],
                "notes": random.choice(NOTAS_EXEMPLO) if not is_pre_registo else None,
                "monitored_emails": None,
                "onedrive_links": None,
                "s3_folder": f"Documentação Clientes/{cliente['nome'].replace(' ', '_')}/",
                "company_id": "default",
                "company_name": "Power Real Estate",
                "created_at": iso(datetime.now(timezone.utc) - timedelta(days=random.randint(1, 60))),
                "updated_at": iso(),
                **seed_mark(),
            }
            next_number += 1

            # Adicionar às listas
            clientes_criados.append(cliente)
            if segundo_cliente:
                clientes_criados.append(segundo_cliente)
            processos_criados.append(processo)

            # Atualizar process_ids do cliente
            cliente["process_ids"].append(processo["id"])
            if segundo_cliente:
                segundo_cliente["process_ids"].append(processo["id"])

            # Gerar atividades (2+ por processo ativo)
            if not is_pre_registo:
                num_atividades = random.randint(2, 4)
                for i in range(num_atividades):
                    user_ref = consultor if i % 2 == 0 else (indexador if indexador else consultor)
                    atividades_criadas.append(gerar_atividade(
                        processo["id"], user_ref,
                        dias_atras=random.randint(0, 30) - i
                    ))
                # Histórico
                historico_criado.append(gerar_historico(
                    processo["id"], consultor, status,
                    dias_atras=random.randint(1, 15)
                ))

    # 5. Inserir na BD
    if dry_run:
        print(f"\n🔍 DRY RUN — {len(processos_criados)} processos seriam criados:")
        for p in processos_criados:
            casal_str = " (casal)" if p.get("titular2_data") else ""
            completo_str = " [COMPLETO]" if p["status"] in STATUS_ATIVOS_COMPLETOS else ""
            print(f"   #{p['process_number']} — {p['client_name']} — {p['status']}{casal_str}{completo_str}")
        print(f"\n   Clientes: {len(clientes_criados)}")
        print(f"   Atividades: {len(atividades_criadas)}")
        print(f"   Histórico: {len(historico_criado)}")
        return

    # Inserir clientes
    if clientes_criados:
        print(f"\n📥 A inserir {len(clientes_criados)} clientes...")
        await db.clients.insert_many(clientes_criados, ordered=False)
        print(f"   ✅ {len(clientes_criados)} clientes inseridos")

    # Inserir processos
    if processos_criados:
        print(f"\n📥 A inserir {len(processos_criados)} processos...")
        await db.processes.insert_many(processos_criados, ordered=False)
        print(f"   ✅ {len(processos_criados)} processos inseridos")

    # Inserir atividades
    if atividades_criadas:
        print(f"\n📥 A inserir {len(atividades_criadas)} atividades...")
        await db.activities.insert_many(atividades_criadas, ordered=False)
        print(f"   ✅ {len(atividades_criadas)} atividades inseridas")

    # Inserir histórico
    if historico_criado:
        print(f"\n📥 A inserir {len(historico_criado)} entradas de histórico...")
        await db.history.insert_many(historico_criado, ordered=False)
        print(f"   ✅ {len(historico_criado)} entradas inseridas")

    # Resumo final
    print("\n" + "=" * 60)
    print("✅ SEED QA ULTIMATE CONCLUÍDO!")
    print(f"   Processos: {len(processos_criados)}")
    print(f"   Clientes: {len(clientes_criados)}")
    print(f"   Atividades: {len(atividades_criadas)}")
    print(f"   Histórico: {len(historico_criado)}")
    print(f"\n   Distribuição por status:")
    for status, _, _, desc in DISTRIBUICAO_STATUS:
        count = sum(1 for p in processos_criados if p["status"] == status)
        if count > 0:
            casais = sum(1 for p in processos_criados if p["status"] == status and p.get("titular2_data"))
            completos = sum(1 for p in processos_criados if p["status"] in STATUS_ATIVOS_COMPLETOS)
            print(f"     {status:25s} → {count:2d} ({casais} casais, {completos} completos)")
    print("=" * 60)


# ====================================================================
# MAIN
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="Seed QA Ultimate — PowerCell CRM")
    parser.add_argument("--clear", action="store_true", help="Limpar dados de seed anteriores")
    parser.add_argument("--num-processes", type=int, default=18, help="Número de processos a gerar (default: 18)")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem escrever na BD")
    args = parser.parse_args()

    # Validar variáveis de ambiente
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos no backend/.env")
        sys.exit(1)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    async def _run():
        if args.clear:
            print("\n🧹 A limpar dados de seed anteriores...")
            await clear_seed_data(db)

        await run_seed(db, num_processes=args.num_processes, dry_run=args.dry_run)

    asyncio.run(_run())
    mongo_client.close()


if __name__ == "__main__":
    main()
