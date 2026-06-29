#!/usr/bin/env python3
"""
====================================================================
SEED MASSIVO DE MOCK DATA V2 — POWERCELL (Pacote F)
====================================================================
Script de PREENCHIMENTO PROFUNDO que ITERA sobre os processos e
clientes JÁ EXISTENTES na BD de DEV e preenche obrigatoriamente os
dados em falta que o Pacote A (seed_massive_dev_data.py) deixou
vazios — causando cartões vazios e dificultando os testes de UI.

O QUE FAZ (por processo existente):
  1. CARTÕES FINANCEIROS E PROFISSIONAIS:
     - Créditos Ativos (bancos_creditos): 1-3 objetos {banco, valor,
       prestacao, tipo} com bancos CURTOS do BANK_LIST do frontend
       (CGD, Millennium bcp, Santander Totta, BPI, Novo Banco, ...) para
       os badges coloridos renderizarem correctamente.
     - Contas de Crédito Abertas (tem_creditos_activos): injeta os
       mesmos bancos dos créditos ativos (sincronização que o frontend
       já faz automaticamente).
     - Simulações de Crédito (bancos_simulacoes + simulacoes_detalhe):
       1-2 simulações com banco, spread, TAEG, prestação.
     - Rendimentos / Situação Financeira: monthly_income,
       rendimento_bruto, rendimento_anual, capital_proprio,
       renda_habitacao_atual, nr_dependentes, efetivo, precisa_vender_casa.
     - Situação Profissional: employment_type (enum válido), employment_duration,
       employer_name, employer_nif, categoria_profissional,subsidiario_alimentacao.

  2. DADOS DO IMÓVEL E VENDEDOR:
     - Estado da Procura: derivado em 3 estados típicos
       ("Em pesquisa", "CPCV Assinado", "Escritura Marcada") — ajusta
       ja_tem_imovel / ja_tem_casa_escolhida / data_cpcv /
       data_escritura_prevista coerentemente + campo novo estado_procura.
     - Dados do Proprietário/Vendedor: proprietario_nome,
       proprietario_contacto, owner_name, owner_email, owner_phone,
       agencia_imobiliaria (fictícia) E process.vendedor
       ({nome, contacto, telefone, agencia}).
     - Todos os dropdowns (enums) recebem valores VÁLIDOS do esquema.

  3. DOCUMENTAÇÃO E PORTAL DO CLIENTE:
     - Garante 3-6 documentos por processo na coleção `documents`.
     - Pelo menos 2 com status=UPLOADED + source=client_portal
       (submetidos pelo cliente via Portal).
     - Pelo menos 1 com status=REQUESTED + source=admin_request
       (pendente/pedido ao cliente).
     - Se o processo já tiver docs suficientes, NÃO duplica — apenas
       completa o que falta para cumprir os mínimos.

EXECUÇÃO SEGURA:
  - Usa MONGO_URL/DB_NAME do backend/.env.
  - Por defeito é IDEMPOTENTE: só preenche campos VAZIOS/NULOS (não
    destrói dados existentes). Use --force para sobrescrever tudo.
  - Não cria nem elimina clientes/processos — apenas atualiza.

USO:
    python backend/scripts/seed_massive_dev_data_v2.py
    python backend/scripts/seed_massive_dev_data_v2.py --force
    python backend/scripts/seed_massive_dev_data_v2.py --limit 50
    python backend/scripts/seed_massive_dev_data_v2.py --skip-docs
    python backend/scripts/seed_massive_dev_data_v2.py --only-status intermediario,aprovado

OPÇÕES:
  --force              Sobrescreve campos mesmo que já tenham valor
  --limit N            Processa apenas os primeiros N processos (default: todos)
  --only-status LIST   Processa apenas processos com estes status (csv)
  --skip-docs          Não garantir documentos do Portal
  --dry-run            Mostra o que faria sem escrever na BD
  --help               Mostra esta ajuda
====================================================================
"""

import asyncio
import os
import random
import string
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from faker import Faker
except ImportError:
    print("Falta a biblioteca Faker. Instale com: pip install Faker")
    sys.exit(1)

load_dotenv(Path(__file__).parent.parent / '.env')

fake = Faker('pt_PT')
SEED_SCRIPT = "seed_massive_dev_data_v2"

# ==============================================================================
# POLOS DE DADOS (alinhados com o frontend ProcessDetails.js)
# ==============================================================================

# NOMES CURTOS exatos do BANK_LIST do frontend (ProcessDetails.js linha 188)
# para os badges coloridos (BANK_COLORS) renderizarem correctamente.
BANK_LIST_SHORT = [
    "ABANCA", "BBVA", "BEST", "BIG", "BPI", "CGD", "Crédito Agrícola",
    "CTT", "Millennium bcp", "Novo Banco", "Popular", "Santander Totta", "Outro"
]

EMPRESAS = [
    "EDP - Energias de Portugal", "Galp Energia", "Sonae", "Jerónimo Martins",
    "Banco Santander", "BNP Paribas", "CGD - Caixa Geral de Depósitos",
    "Millennium BCP", "Bankinter", "Continente", "Pingo Doce",
    "Lidl Portugal", "Vodafone Portugal", "NOS", "Deloitte Portugal",
    "KPMG Portugal", "Delta Cafés", "Teixeira Duarte", "Mota-Engil",
    "Hospital de Santa Maria", "Universidade de Lisboa", "TAP Air Portugal",
]

CATEGORIAS_PROFISSIONAIS = [
    "Técnico Superior", "Especialista", "Técnico", "Operário",
    "Administrativo", "Comercial", "Direção Intermédia", "Quadro Superior",
]

# employment_type — valores EXATOS do Select do frontend (linha 4177-4183)
EMPLOYMENT_TYPES = [
    ("efetivo", "Contrato Efetivo"),
    ("termo_certo", "Termo Certo"),
    ("termo_incerto", "Termo Incerto"),
    ("independente", "Trabalhador Independente"),
    ("empresario", "Empresário"),
    ("reformado", "Reformado"),
]

# Tipos de crédito para o campo "tipo" dos bancos_creditos
TIPOS_CREDITO = ["Crédito Pessoal", "Crédito Automóvel", "Cartão de Crédito", "Outro Crédito"]

# Agências imobiliárias fictícias
AGENCIAS_IMOBILIARIAS = [
    "PowerPrecision Imobiliária", "Casa & Sonho Lda", "Imobiliária Atlântico",
    "Lar Perfeito Mediação", "Premium Homes Portugal", "KeyHunt Properties",
    "Inovação Imobiliária", "Mundo Casa Mediação", "Pró-Imóveis Lda",
    "Imobrasil — Mediação Imobiliária",
]

# Estados da procura típicos (3 buckets coerentes com os dados)
ESTADOS_PROCURA = [
    "Em pesquisa",
    "CPCV Assinado",
    "Escritura Marcada",
]

# Categorias de documentos do Portal (chaves válidas do DOCUMENT_CATEGORY_MAP)
PORTAL_DOC_CATEGORIES = [
    "Cartao_Cidadao", "IRS", "Financeiros", "Recibo_Vencimento",
    "Comprovativo_IBAN", "Atestado_Trabalho", "Mapa_Creditos",
    "Certidao_Permanente", "Contrato_Promessa", "Certificado_Energetico",
    "Plantas_Casa", "Outros",
]

DOC_FILENAME_BY_CATEGORY = {
    "Cartao_Cidadao":      ["cartao_cidadao.pdf", "cc_frente_verso.pdf"],
    "IRS":                 ["irs_2023.pdf", "declaracao_irs.pdf"],
    "Financeiros":         ["extrato_bancario.pdf", "movimentos_conta.pdf"],
    "Recibo_Vencimento":   ["recibo_vencimento_jan.pdf", "recibo_salario.pdf"],
    "Comprovativo_IBAN":   ["comprovativo_iban.pdf"],
    "Atestado_Trabalho":   ["atestado_trabalho.pdf"],
    "Mapa_Creditos":       ["mapa_creditos_banco.pdf"],
    "Certidao_Permanente": ["certidao_permanente.pdf"],
    "Contrato_Promessa":   ["cpcv.pdf", "contrato_promessa.pdf"],
    "Certificado_Energetico": ["certificado_energetico.pdf"],
    "Plantas_Casa":        ["planta_imovel.pdf"],
    "Outros":              ["documento_extra.pdf", "comprovativo.pdf"],
}

# ==============================================================================
# UTILITÁRIOS
# ==============================================================================

def iso(dt: datetime) -> str:
    return dt.isoformat()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def seed_mark() -> dict:
    return {"_seed_data_v2": True, "_seed_script": SEED_SCRIPT}

def gerar_nif_valido() -> str:
    primeiro = random.choice([1, 2, 3, 3, 3, 3, 2, 1, 3])
    digitos = [primeiro] + [random.randint(0, 9) for _ in range(7)]
    soma = sum(digitos[i] * (9 - i) for i in range(8))
    resto = soma % 11
    digitos.append(0 if resto < 2 else 11 - resto)
    return ''.join(map(str, digitos))

def gerar_telefone() -> str:
    return f"{random.choice(['91','93','92','96'])}{''.join(random.choices(string.digits, k=7))}"

def gerar_email(nome: str) -> str:
    nomes = nome.lower().replace("ã", "a").replace("ç", "c").replace("é", "e").split()
    if len(nomes) < 2:
        nomes = [nomes[0] if nomes else "cliente", "dev"]
    fmt = random.choice([
        f"{nomes[0]}.{nomes[-1]}",
        f"{nomes[0]}{nomes[-1]}",
        f"{nomes[0][0]}{nomes[-1]}",
    ])
    return f"{fmt}@{random.choice(['gmail.com','hotmail.com','outlook.pt','sapo.pt'])}"

def calc_prestacao(montante: float, taxa_anual: float, anos: int) -> float:
    """Prestação mensal de um crédito (fórmula francesa)."""
    r = taxa_anual / 100 / 12
    n = anos * 12
    if r <= 0 or n <= 0:
        return round(montante / max(n, 1), 2)
    return round(montante * (r * (1 + r) ** n) / ((1 + r) ** n - 1), 2)

def calc_taeg(spread: float, euribor: float) -> float:
    """TAEG aproximada = euribor + spread + custos (~0.4%)."""
    return round(euribor + spread + 0.4, 2)

def random_past_dt(days_max: int = 60) -> datetime:
    return datetime.now(timezone.utc) - timedelta(
        days=random.randint(0, days_max),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )

# ==============================================================================
# GERADORES DE BLOCOS DE DADOS (devolvem dicts para $set)
# ==============================================================================

def gerar_creditos_ativos() -> list:
    """1-3 objetos {banco, valor, prestacao, tipo} com bancos CURTOS."""
    n = random.randint(1, 3)
    bancos_usados = random.sample(BANK_LIST_SHORT[:-1], k=min(n, len(BANK_LIST_SHORT) - 1))  # exclui "Outro"
    out = []
    for banco in bancos_usados:
        montante = round(random.uniform(3000, 45000), 2)
        taxa = round(random.uniform(4.5, 12.0), 2)
        anos = random.choice([3, 4, 5, 6, 7])
        prestacao = calc_prestacao(montante, taxa, anos)
        out.append({
            "banco": banco,
            "valor": montante,
            "prestacao": prestacao,
            "prestacao_mensal": prestacao,
            "tipo": random.choice(TIPOS_CREDITO),
            "anos_restantes": anos,
            "tempo_restante": f"{anos} anos",
        })
    return out


def gerar_simulacoes_detalhe(valor_imovel: float) -> list:
    """1-2 simulações detalhadas {banco, spread, taeg, prestacao, montante, prazo}."""
    n = random.randint(1, 2)
    bancos = random.sample(BANK_LIST_SHORT[:-1], k=min(n, len(BANK_LIST_SHORT) - 1))
    out = []
    pct = round(random.uniform(0.70, 0.90), 4)
    montante = round(valor_imovel * pct, 2)
    for banco in bancos:
        spread = round(random.uniform(0.80, 2.50), 2)
        euribor = round(random.uniform(2.5, 3.8), 2)
        taeg = calc_taeg(spread, euribor)
        taxa = round(euribor + spread, 2)
        anos = random.choice([25, 30, 35, 40])
        out.append({
            "banco": banco,
            "montante": montante,
            "valor_financiamento": montante,
            "prazo_anos": anos,
            "spread": spread,
            "euribor": euribor,
            "taxa": taxa,
            "taeg": taeg,
            "prestacao": calc_prestacao(montante, taeg, anos),
            "pct_financiamento": round(pct * 100, 1),
            "data_simulacao": random_past_dt(30).strftime("%Y-%m-%d"),
        })
    return out


def gerar_rendimentos_situacao() -> dict:
    """Rendimentos + Situação Financeira (campos do cartão)."""
    salario_liquido = round(random.uniform(850, 4200), 2)
    salario_bruto = round(salario_liquido / 0.72, 2)  # aprox. bruto
    rendimento_anual = round(salario_bruto * 14, 2)
    capital_proprio = round(random.uniform(5000, 75000), 2)
    renda = round(random.uniform(0, 950), 2) if random.random() < 0.45 else 0.0
    dependentes = random.randint(0, 4)
    return {
        "monthly_income": salario_liquido,
        "salario_liquido": salario_liquido,
        "rendimento_bruto": salario_bruto,
        "salario_bruto": salario_bruto,
        "rendimento_anual": rendimento_anual,
        "capital_proprio": capital_proprio,
        "other_income": capital_proprio,
        "valor_financiado": f"{round(random.uniform(70, 90))}%",
        "renda_habitacao_atual": renda,
        "renda_mensal": renda,
        "nr_dependentes": dependentes,
        "number_of_dependents": dependentes,
        "outros_rendimentos": round(random.uniform(0, 600), 2) if random.random() < 0.25 else 0.0,
        "despesas_mensais": round(renda + random.uniform(150, 500), 2),
        # Situação Financeira (Selects sim/nao)
        "efetivo": random.choice(["sim", "sim", "nao"]),
        "precisa_vender_casa": random.choice(["nao", "nao", "nao", "sim"]),
        "fiador": random.choice(["nao", "nao", "nao", "sim"]),
    }


def gerar_situacao_profissional() -> dict:
    """Situação Profissional (cardKey=financial_profissional)."""
    emp_type, _ = random.choice(EMPLOYMENT_TYPES)
    empresa = random.choice(EMPRESAS)
    anos_antig = random.randint(0, 22)
    return {
        "employment_type": emp_type,
        "trabalha_estrangeiro": random.choice(["nao", "nao", "sim"]),
        "employment_duration": f"{anos_antig} ano{'s' if anos_antig != 1 else ''}",
        "employer_name": empresa,
        "emprego_atual": empresa,
        "empresa": empresa,
        "employer_nif": gerar_nif_valido(),
        "categoria_profissional": random.choice(CATEGORIAS_PROFISSIONAIS),
        "subsidiario_alimentacao": round(random.uniform(4.77, 9.60), 2),
        "data_referencia": (datetime.now(timezone.utc).replace(day=1)).strftime("%Y-%m"),
        "tipo_contrato": emp_type,
        "antiguidade_anos": anos_antig,
    }


def gerar_estado_procura_e_vendedor() -> dict:
    """Estado da Procura + Vendedor + Proprietário (real_estate_data + process.vendedor)."""
    estado = random.choice(ESTADOS_PROCURA)
    hoje = datetime.now(timezone.utc)
    base = {"estado_procura": estado}

    # Ajustar flags + datas conforme o estado
    if estado == "Em pesquisa":
        base["ja_tem_imovel"] = False
        base["has_property"] = False
        base["ja_tem_casa_escolhida"] = False
        base["data_cpcv"] = None
        base["data_escritura_prevista"] = None
    elif estado == "CPCV Assinado":
        base["ja_tem_imovel"] = True
        base["has_property"] = True
        base["ja_tem_casa_escolhida"] = True
        base["data_cpcv"] = (hoje - timedelta(days=random.randint(5, 60))).strftime("%Y-%m-%d")
        base["data_escritura_prevista"] = (hoje + timedelta(days=random.randint(45, 150))).strftime("%Y-%m-%d")
    else:  # "Escritura Marcada"
        base["ja_tem_imovel"] = True
        base["has_property"] = True
        base["ja_tem_casa_escolhida"] = True
        base["data_cpcv"] = (hoje - timedelta(days=random.randint(60, 120))).strftime("%Y-%m-%d")
        base["data_escritura_prevista"] = (hoje + timedelta(days=random.randint(10, 40))).strftime("%Y-%m-%d")

    # Dados do Proprietário / Vendedor (fictícios)
    nome_vendedor = fake.name()
    telefone = gerar_telefone()
    email = gerar_email(nome_vendedor)
    agencia = random.choice(AGENCIAS_IMOBILIARIAS)

    base["proprietario_nome"] = nome_vendedor
    base["proprietario_contacto"] = telefone
    base["owner_name"] = nome_vendedor
    base["owner_email"] = email
    base["owner_phone"] = telefone
    base["agencia_imobiliaria"] = agencia
    base["vendedor_nome"] = nome_vendedor
    base["vendedor_contacto"] = telefone
    return base, {
        "nome": nome_vendedor,
        "name": nome_vendedor,
        "contacto": telefone,
        "telefone": telefone,
        "email": email,
        "agencia": agencia,
    }


# ==============================================================================
# DOCUMENTOS DO PORTAL
# ==============================================================================

def gerar_documento_requested(process_id: str, consultor_id: str | None, consultor_name: str) -> dict:
    category = random.choice(PORTAL_DOC_CATEGORIES)
    dt = random_past_dt(45)
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "category": category,
        "filename": None,
        "original_filename": None,
        "status": "REQUESTED",
        "notes": random.choice([
            "Por favor anexe este documento no Portal.",
            "Documento necessário para avançar com o banco.",
            "Solicitei este documento ao cliente via Portal.",
            "",
        ]),
        "custom_label": None,
        "requested_by": consultor_id or SEED_SCRIPT,
        "requested_by_name": consultor_name or "Sistema",
        "source": "admin_request",
        "file_size": None,
        "content_type": None,
        "uploaded_at": None,
        "created_at": iso(dt),
        "updated_at": iso(dt),
        **seed_mark(),
    }


def gerar_documento_uploaded(process_id: str, client_name: str) -> dict:
    category = random.choice(PORTAL_DOC_CATEGORIES)
    filename = random.choice(DOC_FILENAME_BY_CATEGORY.get(category, ["documento.pdf"]))
    file_size = random.randint(45000, 5_500_000)
    s3_path = f"portal-uploads/{process_id}/{uuid.uuid4().hex}/{filename}"
    dt = random_past_dt(30)
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "category": category,
        "filename": filename,
        "original_filename": filename,
        "status": "UPLOADED",
        "notes": "",
        "custom_label": None,
        "s3_path": s3_path,
        "file_key": s3_path,
        "file_size": file_size,
        "content_type": "application/pdf",
        "uploaded_by": "portal_client",
        "source": "client_portal",
        "reviewed_by": "portal_client",
        "reviewed_at": iso(dt),
        "uploaded_at": iso(dt),
        "created_at": iso(dt),
        "updated_at": iso(dt),
        **seed_mark(),
    }


# ==============================================================================
# LÓGICA DE MERGE (idempotente por defeito)
# ==============================================================================

def merge_financial(existing: dict, new_block: dict, force: bool) -> dict:
    """Merge idempotente: só preenche campos vazios/nulos (a menos que --force)."""
    out = {}
    for k, v in new_block.items():
        cur = existing.get(k)
        if force or cur in (None, "", [], {}):
            out[k] = v
    return out


def merge_real_estate(existing: dict, new_block: dict, force: bool) -> dict:
    out = {}
    for k, v in new_block.items():
        cur = existing.get(k)
        if force or cur in (None, "", [], {}):
            out[k] = v
    return out


# ==============================================================================
# PIPELINE PRINCIPAL
# ==============================================================================

async def processar_processo(db, processo: dict, force: bool, dry_run: bool) -> dict:
    """Preenche um processo. Devolve stats {updated_fields, docs_added}."""
    pid = processo["id"]
    stats = {"updated_fields": 0, "docs_added": 0, "docs_total": 0}
    process_set = {}
    real_estate_set = {}
    financial_set = {}

    re_existing = processo.get("real_estate_data") or {}
    fin_existing = processo.get("finance_data") or {}

    # ── 1. Créditos Ativos (bancos_creditos) + Contas (tem_creditos_activos) ──
    cur_creditos = fin_existing.get("bancos_creditos")
    if force or not isinstance(cur_creditos, list) or len(cur_creditos) == 0:
        novos_creditos = gerar_creditos_ativos()
        financial_set["bancos_creditos"] = novos_creditos
        # Contas de Crédito Abertas = bancos dos créditos ativos (sincronizado)
        financial_set["tem_creditos_activos"] = [c["banco"] for c in novos_creditos]

    # ── 2. Simulações de Crédito (bancos_simulacoes + simulacoes_detalhe) ──
    if force or not isinstance(fin_existing.get("bancos_simulacoes"), list) or len(fin_existing.get("bancos_simulacoes") or []) == 0:
        valor_imovel = re_existing.get("valor_imovel") or re_existing.get("valor") or 200000
        sims = gerar_simulacoes_detalhe(float(valor_imovel))
        financial_set["bancos_simulacoes"] = [s["banco"] for s in sims]
        financial_set["simulacoes_detalhe"] = sims

    # ── 3. Rendimentos + Situação Financeira ──
    financial_set.update(merge_financial(fin_existing, gerar_rendimentos_situacao(), force))

    # ── 4. Situação Profissional ──
    financial_set.update(merge_financial(fin_existing, gerar_situacao_profissional(), force))

    # ── 5. Estado da Procura + Vendedor + Proprietário ──
    re_block, vendedor = gerar_estado_procura_e_vendedor()
    real_estate_set.update(merge_real_estate(re_existing, re_block, force))
    # Vendedor no top-level do processo
    cur_vendedor = processo.get("vendedor")
    if force or not cur_vendedor or not cur_vendedor.get("nome"):
        process_set["vendedor"] = vendedor

    # ── Aplicar updates ao processo ──
    if process_set and not dry_run:
        process_set["updated_at"] = now_iso()
        await db.processes.update_one({"id": pid}, {"$set": process_set})
    stats["updated_fields"] += len(process_set)

    # ── Merge finance_data + real_estate_data num único $set ──
    combined_set = {}
    if financial_set:
        for k, v in financial_set.items():
            combined_set[f"finance_data.{k}"] = v
    if real_estate_set:
        for k, v in real_estate_set.items():
            combined_set[f"real_estate_data.{k}"] = v
    if combined_set and not dry_run:
        combined_set["updated_at"] = now_iso()
        await db.processes.update_one({"id": pid}, {"$set": combined_set})
    stats["updated_fields"] += len(financial_set) + len(real_estate_set)

    # ── 6. Sincronizar dados financeiros no cliente principal ──
    if financial_set and not dry_run:
        client_id = processo.get("client_id")
        if client_id:
            client_set = {}
            for k, v in financial_set.items():
                client_set[f"dados_financeiros.{k}"] = v
                client_set[f"financial_data.{k}"] = v
            client_set["updated_at"] = now_iso()
            await db.clients.update_one({"id": client_id}, {"$set": client_set})

    return stats


async def garantir_documentos(db, processo: dict, dry_run: bool) -> dict:
    """Garante 3-6 docs por processo (>=2 UPLOADED via Portal, >=1 REQUESTED)."""
    pid = processo["id"]
    if processo.get("is_deleted"):
        return {"docs_added": 0, "docs_total": 0}

    existentes = await db.documents.find({"process_id": pid}).to_list(100)
    n_uploaded = sum(1 for d in existentes if d.get("status") == "UPLOADED")
    n_requested = sum(1 for d in existentes if d.get("status") == "REQUESTED")
    total = len(existentes)

    min_total = 3
    max_total = 6
    docs_to_add = []

    # Garantir >=2 UPLOADED via Portal
    need_uploaded = max(0, 2 - n_uploaded)
    for _ in range(need_uploaded):
        docs_to_add.append(gerar_documento_uploaded(pid, processo.get("client_name", "Cliente")))

    # Garantir >=1 REQUESTED
    need_requested = max(0, 1 - n_requested)
    consultor_id = processo.get("assigned_consultor_id")
    consultor_name = processo.get("consultor_name") or "Consultor"
    for _ in range(need_requested):
        docs_to_add.append(gerar_documento_requested(pid, consultor_id, consultor_name))

    # Se ainda abaixo do mínimo, completar com mix
    if total + len(docs_to_add) < min_total:
        faltam = min_total - (total + len(docs_to_add))
        for _ in range(faltam):
            if random.random() < 0.6:
                docs_to_add.append(gerar_documento_uploaded(pid, processo.get("client_name", "Cliente")))
            else:
                docs_to_add.append(gerar_documento_requested(pid, consultor_id, consultor_name))

    # Se acima do máximo, não remover — apenas não adicionar mais
    if docs_to_add and not dry_run:
        await db.documents.insert_many(docs_to_add, ordered=False)

    final_total = total + len(docs_to_add)
    return {"docs_added": len(docs_to_add), "docs_total": final_total}


# ==============================================================================
# FUNÇÃO PRINCIPAL
# ==============================================================================

async def seed_v2(
    force: bool = False,
    limit: int | None = None,
    only_status: list | None = None,
    skip_docs: bool = False,
    dry_run: bool = False,
):
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    if not mongo_url or not db_name:
        print("MONGO_URL e DB_NAME devem estar definidos no backend/.env")
        sys.exit(1)

    safe_url = mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url
    print("\n" + "=" * 70)
    print("SEED MASSIVO V2 — PREENCHIMENTO PROFUNDO (Pacote F)")
    print("=" * 70)
    print(f"BD: {db_name} | Ligacao: {safe_url}")
    print(f"Modo: {'DRY-RUN' if dry_run else 'ESCRITA'} | Force: {force}")
    if only_status:
        print(f"Filtro status: {only_status}")
    if limit:
        print(f"Limite: {limit} processos")
    print("=" * 70)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    try:
        # Query de processos
        query = {"is_deleted": {"$ne": True}}
        if only_status:
            query["status"] = {"$in": only_status}

        total_procs = await db.processes.count_documents(query)
        print(f"\nProcessos a processar: {total_procs}")

        cursor = db.processes.find(query)
        if limit:
            cursor = cursor.limit(limit)

        processed = 0
        total_fields = 0
        total_docs_added = 0

        async for processo in cursor:
            processed += 1
            if processed % 10 == 0 or processed == total_procs:
                print(f"  ... {processed}/{total_procs} processos processados")

            stats = await processar_processo(db, processo, force, dry_run)
            total_fields += stats["updated_fields"]

            if not skip_docs:
                dstats = await garantir_documentos(db, processo, dry_run)
                total_docs_added += dstats["docs_added"]

        # ── Resumo ──
        print("\n" + "=" * 70)
        print("RESUMO FINAL")
        print("=" * 70)
        print(f"  Processos processados:        {processed}")
        print(f"  Campos preenchidos (total):   {total_fields}")
        print(f"  Documentos adicionados:       {total_docs_added}")
        if dry_run:
            print("\n  (DRY-RUN: nenhuma escrita foi feita na BD)")

        # Estatísticas de documentos
        if not skip_docs and not dry_run:
            agg = await db.documents.aggregate([
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]).to_list(10)
            print("\nDocumentos por status (global):")
            for a in agg:
                print(f"  {a['_id']}: {a['count']}")

        print("\nPara re-executar sobrescrevendo dados existentes:")
        print("  python backend/scripts/seed_massive_dev_data_v2.py --force")
        print("=" * 70)

    finally:
        mongo_client.close()


# ==============================================================================
# CLI
# ==============================================================================

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="Seed V2 — Preenchimento Profundo de Mock Data (Pacote F)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Itera sobre processos/clientes EXISTENTES e preenche cartoes financeiros,
profissionais, imovel, vendedor e documentos do Portal que estavam vazios.

Exemplos:
  python backend/scripts/seed_massive_dev_data_v2.py
  python backend/scripts/seed_massive_dev_data_v2.py --force
  python backend/scripts/seed_massive_dev_data_v2.py --limit 50 --dry-run
  python backend/scripts/seed_massive_dev_data_v2.py --only-status intermediario,aprovado
        """,
    )
    p.add_argument("--force", action="store_true",
                   help="Sobrescrever campos mesmo que ja tenham valor")
    p.add_argument("--limit", type=int, default=None,
                   help="Processar apenas os primeiros N processos")
    p.add_argument("--only-status", default=None,
                   help="Processar apenas processos com estes status (csv)")
    p.add_argument("--skip-docs", action="store_true",
                   help="Nao garantir documentos do Portal")
    p.add_argument("--dry-run", action="store_true",
                   help="Mostrar o que faria sem escrever na BD")
    args = p.parse_args()

    only_status = None
    if args.only_status:
        only_status = [s.strip() for s in args.only_status.split(",") if s.strip()]

    asyncio.run(seed_v2(
        force=args.force,
        limit=args.limit,
        only_status=only_status,
        skip_docs=args.skip_docs,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
