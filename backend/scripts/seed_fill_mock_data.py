#!/usr/bin/env python3
"""
====================================================================
SEED DE MOCK DATA PARA CLIENTES E PROCESSOS EXISTENTES - POWERCELL
====================================================================
Script para PREENCHER dados em falta em clientes e processos JÁ
EXISTENTES na base de dados. Não cria novos registos — apenas
actualiza campos vazios com dados aleatórios mas realistas.

OBJECTIVO: Permitir testar Dashboards de Desempenho e simulações
financeiras no ambiente DEV.

FUNCIONAMENTO:
1. Itera sobre TODOS os Clientes e TODOS os Processos existentes
2. Se campos estiverem vazios/nulos, injecta dados aleatórios realistas
3. Se campos já tiverem dados, NÃO os sobrepõe (preserva dados reais)

DADOS PREENCHIDOS:
- Cliente (perfil): Data Nascimento, Estado Civil, Dependentes,
  Profissão, Vínculo Laboral
- Processo (financeiros): Rendimento Base Mensal, Outros Créditos
- Processo (imóvel): Valor Aquisição, Valor Financiamento,
  Tipo Imóvel, Estado (Novo/Usado)

Uso:
    python scripts/seed_fill_mock_data.py [--dry-run] [--company-id=XXX]

Opções:
    --dry-run         Mostra o que seria alterado sem gravar na BD
    --company-id=XXX  Filtrar por empresa (company_id) específica
    --help            Mostra esta ajuda
====================================================================
"""

import asyncio
import random
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Adicionar o directório backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv(Path(__file__).parent.parent / '.env')


# ==============================================================================
# DADOS REALISTAS PORTUGUESES
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

VINCULOS_LABORAIS = ["Efetivo", "Efetivo", "Efetivo", "Recibos Verdes", "Termo Certo"]

ESTADOS_CIVIS = ["Solteiro", "Casado", "Casado", "Divorciado", "Viúvo"]

TIPOS_IMOVEL = ["apartamento", "apartamento", "apartamento", "moradia"]

TIPOLOGIAS = ["T1", "T2", "T2", "T3", "T3", "T4", "T5"]

ESTADOS_IMOVEL = ["Novo", "Usado", "Usado", "Usado"]  # Maioria usados

LOCALIDADES = [
    "Lisboa", "Porto", "Braga", "Setúbal", "Faro", "Coimbra",
    "Aveiro", "Leiria", "Viseu", "Guimarães", "Cascais", "Sintra",
    "Matosinhos", "Vila Nova de Gaia", "Amadora", "Almada", "Oeiras"
]

BANCOS_CREDITO = [
    "CGD", "Santander Totta", "Millennium bcp", "Novo Banco",
    "Bankinter", "Abanca", "BPI", "Popular", "CTT", "Ubi"
]

EMPRESAS = [
    "EDP - Energias de Portugal", "Galp Energia", "Sonae", "Jerónimo Martins",
    "Banco Santander", "BNP Paribas", "CGD - Caixa Geral de Depósitos",
    "Millennium BCP", "Bankinter", "Continente", "Pingo Doce",
    "Lidl Portugal", "Vodafone Portugal", "NOS", "Deloitte Portugal",
    "KPMG Portugal", "Delta Cafés", "Teixeira Duarte", "Mota-Engil",
    "Hospital de Santa Maria", "Universidade de Lisboa", "TAP Air Portugal",
]

NACIONALIDADES = [
    "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa",
    "Brasileira", "Angolana", "Cabo-verdiana", "Ucraniana"
]

CIDADES = LOCALIDADES.copy()


# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def gerar_data_nascimento(idade_min=25, idade_max=60):
    """Gera data de nascimento como string DD/MM/YYYY para uma idade aleatória."""
    hoje = datetime.now()
    idade = random.randint(idade_min, idade_max)
    ano = hoje.year - idade
    mes = random.randint(1, 12)
    if mes in [1, 3, 5, 7, 8, 10, 12]:
        dia = random.randint(1, 31)
    elif mes == 2:
        dia = random.randint(1, 28)
    else:
        dia = random.randint(1, 30)
    return f"{dia:02d}/{mes:02d}/{ano}"


def gerar_morada():
    """Gera uma morada realista portuguesa."""
    ruas = [
        "Rua da Liberdade", "Avenida da República", "Rua de Santa Catarina",
        "Rua Augusto Rosa", "Travessa do Ouro", "Rua do Ouro",
        "Avenida dos Aliados", "Rua de Cedofeita", "Rua da Boavista",
        "Rua da Constituição", "Avenida da Boavista", "Rua de Camões",
        "Rua Sousa Viterbo", "Rua do Bonjardim", "Rua de Santo Ildefonso",
        "Avenida dos Combatentes", "Rua Domingos Sequeira",
        "Rua Actor Taborda", "Rua da Esperança", "Rua do Possolo"
    ]
    rua = random.choice(ruas)
    numero = random.randint(1, 300)
    cidade = random.choice(CIDADES)
    codigo_postal = f"{random.randint(1000, 9999)}-{random.randint(100, 999)}"
    return f"{rua}, {numero}, {codigo_postal} {cidade}"


def gerar_rendimento_base():
    """Rendimento Base Mensal entre 1.200€ e 4.500€."""
    return round(random.uniform(1200, 4500), 2)


def gerar_outros_creditos_mensal():
    """Outros Créditos activos: 0€ a 500€/mês."""
    if random.random() < 0.45:
        return 0.0  # 45% sem outros créditos
    return round(random.uniform(50, 500), 2)


def gerar_valor_imovel():
    """Valor de Aquisição/Imóvel: 150.000€ a 450.000€."""
    return round(random.uniform(150000, 450000), 2)


def gerar_valor_financiamento(valor_imovel):
    """Valor do Financiamento: 80% a 90% do valor de aquisição."""
    pct = random.uniform(0.80, 0.90)
    return round(valor_imovel * pct, 2)


def is_vazio(valor):
    """Verifica se um valor está vazio (None, '', [], {})."""
    if valor is None:
        return True
    if isinstance(valor, str) and valor.strip() == '':
        return True
    if isinstance(valor, (list, dict)) and len(valor) == 0:
        return True
    return False


def ensure_nested_parents(update_nested: dict, doc: dict, parent_fields: list):
    """
    Garante que campos-pai que são null no documento sejam inicializados
    como {} antes de definirmos campos filhos com notação de ponto.
    
    MongoDB não permite criar campo 'x' dentro de {parent: null}.
    Precisamos primeiro setar parent={} e depois parent.x=val.
    
    Args:
        update_nested: dicionário de updates com notação de ponto (modificado in-place)
        doc: documento original da BD
        parent_fields: lista de campos-pai a verificar (ex: ["financial_data", "credit_data"])
    """
    for parent in parent_fields:
        # Verificar se algum update_nested começa com este parent
        has_nested_updates = any(k.startswith(f"{parent}.") for k in update_nested)
        if not has_nested_updates:
            continue
        
        # Verificar se o parent é null no documento original
        parent_val = doc.get(parent)
        if parent_val is None:
            # Inicializar como dict vazio para que os campos filhos possam ser criados
            update_nested[parent] = {}


def build_safe_update(doc: dict, update_nested: dict) -> dict:
    """
    Constrói um update $set seguro que funciona mesmo quando campos-pai são null.
    
    Em vez de usar notação de ponto em $set (que falha se o parent é null),
    construímos o objecto completo e fazemos set do parent inteiro.
    
    Args:
        doc: documento original da BD
        update_nested: dicionário de updates com notação de ponto
        
    Returns:
        dicionário de $set seguro para MongoDB
    """
    # Agrupar updates por campo de topo
    top_level = {}
    nested_updates = {}
    
    for key, value in update_nested.items():
        if '.' in key:
            parent, _, child = key.partition('.')
            if parent not in nested_updates:
                nested_updates[parent] = {}
            nested_updates[parent][child] = value
        else:
            top_level[key] = value
    
    # Para cada parent com nested updates, merge com dados existentes
    result = dict(top_level)
    for parent, children in nested_updates.items():
        existing = doc.get(parent)
        if existing is None:
            existing = {}
        elif not isinstance(existing, dict):
            existing = {}
        # Merge: dados existentes + novos campos (novos sobrepõem se necessário)
        merged = dict(existing)
        merged.update(children)
        result[parent] = merged
    
    return result


# ==============================================================================
# FUNÇÃO PRINCIPAL
# ==============================================================================

async def seed_fill_mock_data(dry_run: bool = False, company_id: str = None):
    """
    Preenche dados em falta em clientes e processos existentes.
    Não cria novos registos — apenas actualiza campos vazios.
    """

    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')

    if not mongo_url or not db_name:
        print("❌ Erro: MONGO_URL e DB_NAME devem estar definidos no .env")
        sys.exit(1)

    safe_url = mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url
    print(f"\n{'=' * 60}")
    print(f"🎯 SEED FILL MOCK DATA - POWERCELL")
    print(f"   Preencher dados em falta em registos existentes")
    print(f"{'=' * 60}")
    print(f"📦 Base de Dados: {db_name}")
    print(f"🔗 Ligação: {safe_url}")
    if dry_run:
        print(f"🏃 MODO DRY-RUN: Não serão gravadas alterações")
    if company_id:
        print(f"🏢 Empresa: {company_id}")
    print()

    mongo_client = AsyncIOMotorClient(mongo_url)
    database = mongo_client[db_name]

    try:
        # ==================================================================
        # PASSO 1: PREENCHER DADOS DE CLIENTE (Perfil)
        # ==================================================================
        print("=" * 60)
        print("📋 PASSO 1: Preencher Dados de Cliente (Perfil)")
        print("=" * 60)

        # Filtro base
        client_filter = {}
        if company_id:
            client_filter["$or"] = [
                {"company_id": company_id},
                {"company_id": {"$exists": False}},
            ]

        total_clientes = await database.clients.count_documents(client_filter)
        print(f"👥 Total de clientes encontrados: {total_clientes}")

        clientes_actualizados = 0
        clientes_skipped = 0

        cursor = database.clients.find(client_filter, {"_id": 0, "id": 1, "nome": 1,
                                                         "dados_pessoais": 1, "contacto": 1})
        async for cliente in cursor:
            client_id = cliente.get("id")
            nome = cliente.get("nome", "Sem nome")
            dp = cliente.get("dados_pessoais") or {}
            contacto = cliente.get("contacto") or {}

            update_fields = {}
            update_nested = {}  # Para campos nested em dados_pessoais e contacto

            # ── dados_pessoais ──────────────────────────────────────
            dp_updates = {}

            if is_vazio(dp.get("data_nascimento")) and is_vazio(dp.get("birth_date")):
                data_nasc = gerar_data_nascimento()
                dp_updates["data_nascimento"] = data_nasc
                dp_updates["birth_date"] = data_nasc

            if is_vazio(dp.get("estado_civil")):
                dp_updates["estado_civil"] = random.choice(ESTADOS_CIVIS)

            if is_vazio(dp.get("profissao")):
                dp_updates["profissao"] = random.choice(PROFISSOES)

            if is_vazio(dp.get("nacionalidade")):
                dp_updates["nacionalidade"] = random.choice(NACIONALIDADES)

            if is_vazio(dp.get("naturalidade")):
                dp_updates["naturalidade"] = random.choice(CIDADES)

            if is_vazio(dp.get("morada_fiscal")):
                dp_updates["morada_fiscal"] = gerar_morada()

            if is_vazio(dp.get("sexo")):
                dp_updates["sexo"] = random.choice(["M", "F"])

            # Aplicar updates a dados_pessoais
            for key, value in dp_updates.items():
                update_nested[f"dados_pessoais.{key}"] = value

            # ── Verificar menor_35_anos ────────────────────────────
            data_nasc_final = dp_updates.get("data_nascimento") or dp.get("data_nascimento")
            if data_nasc_final and is_vazio(dp.get("menor_35_anos")):
                try:
                    partes = data_nasc_final.split("/")
                    ano_nasc = int(partes[2])
                    idade = datetime.now().year - ano_nasc
                    update_nested["dados_pessoais.menor_35_anos"] = idade < 35
                except (ValueError, IndexError):
                    pass

            if not update_nested:
                clientes_skipped += 1
                continue

            # Montar update seguro (lida com campos-pai null)
            safe_set = build_safe_update(cliente, update_nested)
            update_data = {"$set": safe_set}

            if dry_run:
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   🔄 [DRY-RUN] Cliente '{nome}' → campos a preencher: {', '.join(campos)}")
            else:
                await database.clients.update_one({"id": client_id}, update_data)
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   ✅ Cliente '{nome}' actualizado com sucesso ({', '.join(campos)})")

            clientes_actualizados += 1

        print(f"\n   📊 Clientes: {clientes_actualizados} actualizados, "
              f"{clientes_skipped} já com dados completos\n")

        # ==================================================================
        # PASSO 2: PREENCHER DADOS FINANCEIROS (Processo/Cliente)
        # ==================================================================
        print("=" * 60)
        print("💰 PASSO 2: Preencher Dados Financeiros (Processos)")
        print("=" * 60)

        # Filtro base para processos
        process_filter = {}
        if company_id:
            process_filter["$or"] = [
                {"company_id": company_id},
                {"company_id": {"$exists": False}},
            ]

        total_processos = await database.processes.count_documents(process_filter)
        print(f"📁 Total de processos encontrados: {total_processos}")

        processos_actualizados = 0
        processos_skipped = 0

        cursor = database.processes.find(process_filter, {
            "_id": 0, "id": 1, "process_number": 1, "client_name": 1,
            "financial_data": 1, "personal_data": 1, "finance_data": 1,
        })
        async for processo in cursor:
            proc_id = processo.get("id")
            proc_num = processo.get("process_number", "?")
            client_name = processo.get("client_name", "Sem nome")

            # financial_data é o campo principal usado pelo frontend
            fd = processo.get("financial_data") or {}
            # finance_data é o campo legado do seed antigo
            fi = processo.get("finance_data") or {}
            # personal_data pode ter dados financeiros também
            pd = processo.get("personal_data") or {}

            update_nested = {}

            # ── Rendimento Base Mensal ──────────────────────────────
            # Verificar múltiplos campos possíveis para rendimento
            rendimento_vazio = (
                is_vazio(fd.get("rendimento_bruto_mensal")) and
                is_vazio(fd.get("rendimento_bruto")) and
                is_vazio(fd.get("monthly_income")) and
                is_vazio(fd.get("salario_bruto")) and
                is_vazio(fi.get("salario"))
            )
            if rendimento_vazio:
                rendimento = gerar_rendimento_base()
                update_nested["financial_data.rendimento_bruto_mensal"] = rendimento
                update_nested["financial_data.rendimento_bruto"] = rendimento
                update_nested["financial_data.monthly_income"] = rendimento

            # ── Rendimento Anual (calculado a partir do mensal) ─────
            rendimento_mensal = (
                fd.get("rendimento_bruto_mensal") or
                fd.get("rendimento_bruto") or
                fd.get("monthly_income") or
                update_nested.get("financial_data.rendimento_bruto_mensal")
            )
            if is_vazio(fd.get("rendimento_anual")) and rendimento_mensal:
                rend_anual = round(rendimento_mensal * 14, 2)  # 14 meses em PT
                update_nested["financial_data.rendimento_anual"] = rend_anual

            # ── Rendimento Agregado ─────────────────────────────────
            if is_vazio(fd.get("rendimento_agregado")) and rendimento_mensal:
                # Aleatoriamente mais alto (cônjuge) ou igual
                factor = random.choice([1.0, 1.3, 1.5, 1.8, 2.0])
                rend_agreg = round(rendimento_mensal * factor, 2)
                update_nested["financial_data.rendimento_agregado"] = rend_agreg

            # ── Nº de Dependentes ──────────────────────────────────
            if is_vazio(fd.get("nr_dependentes")) and is_vazio(fd.get("dependentes")):
                nr_deps = random.randint(0, 3)
                update_nested["financial_data.nr_dependentes"] = nr_deps
                update_nested["financial_data.dependentes"] = nr_deps

            # ── Vínculo Laboral ────────────────────────────────────
            if is_vazio(fd.get("efetivo")) and is_vazio(fd.get("vinculo_laboral")):
                vinculo = random.choice(VINCULOS_LABORAIS)
                update_nested["financial_data.vinculo_laboral"] = vinculo
                update_nested["financial_data.efetivo"] = vinculo == "Efetivo"

            # ── Outros Créditos Mensais ────────────────────────────
            outros_creditos_vazio = (
                is_vazio(fd.get("creditos_existentes")) and
                is_vazio(fd.get("prestacao_creditos_mensal")) and
                is_vazio(fd.get("despesas_mensais_outros_creditos"))
            )
            if outros_creditos_vazio:
                outros = gerar_outros_creditos_mensal()
                update_nested["financial_data.creditos_existentes"] = outros
                update_nested["financial_data.prestacao_creditos_mensal"] = outros

            # ── Estado Civil (no financial_data para simulações) ───
            if is_vazio(fd.get("estado_civil")):
                update_nested["financial_data.estado_civil"] = random.choice(ESTADOS_CIVIS)

            # ── Profissão (no financial_data para simulações) ──────
            if is_vazio(fd.get("profissao")):
                update_nested["financial_data.profissao"] = random.choice(PROFISSOES)

            # ── Empresa ────────────────────────────────────────────
            if is_vazio(fd.get("empresa")) and is_vazio(fi.get("empresa")):
                update_nested["financial_data.empresa"] = random.choice(EMPRESAS)

            # ── Capital Próprio ────────────────────────────────────
            if is_vazio(fd.get("capital_proprio")) and is_vazio(fd.get("capitais_proprios")):
                cap_proprio = round(random.uniform(10000, 60000), 2)
                update_nested["financial_data.capital_proprio"] = cap_proprio
                update_nested["financial_data.capitais_proprios"] = cap_proprio

            # ── Bancos de Crédito (tem_creditos_activos) ───────────
            if is_vazio(fd.get("tem_creditos_activos")) and is_vazio(fd.get("bancos_creditos")):
                # 40% têm créditos activos
                if random.random() < 0.4:
                    num_bancos = random.randint(1, 2)
                    bancos = random.sample(BANCOS_CREDITO, k=num_bancos)
                    update_nested["financial_data.tem_creditos_activos"] = bancos
                    update_nested["financial_data.bancos_creditos"] = [
                        {"banco": b, "valor": round(random.uniform(50, 300), 2)}
                        for b in bancos
                    ]

            if not update_nested:
                processos_skipped += 1
                continue

            # Montar update seguro (lida com campos-pai null como financial_data)
            safe_set = build_safe_update(processo, update_nested)
            update_data = {"$set": safe_set}

            if dry_run:
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   🔄 [DRY-RUN] Processo #{proc_num} '{client_name}' → "
                      f"financeiro: {', '.join(campos)}")
            else:
                await database.processes.update_one({"id": proc_id}, update_data)
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   ✅ Processo #{proc_num} '{client_name}' actualizado com sucesso "
                      f"({', '.join(campos)})")

            processos_actualizados += 1

        print(f"\n   📊 Processos (financeiro): {processos_actualizados} actualizados, "
              f"{processos_skipped} já com dados completos\n")

        # ==================================================================
        # PASSO 3: PREENCHER DADOS DO IMÓVEL (Processo)
        # ==================================================================
        print("=" * 60)
        print("🏠 PASSO 3: Preencher Dados do Imóvel (Processos)")
        print("=" * 60)

        imoveis_actualizados = 0
        imoveis_skipped = 0

        cursor = database.processes.find(process_filter, {
            "_id": 0, "id": 1, "process_number": 1, "client_name": 1,
            "real_estate_data": 1, "credit_data": 1,
        })
        async for processo in cursor:
            proc_id = processo.get("id")
            proc_num = processo.get("process_number", "?")
            client_name = processo.get("client_name", "Sem nome")

            red = processo.get("real_estate_data") or {}
            cd = processo.get("credit_data") or {}

            update_nested = {}

            # ── Já tem imóvel ──────────────────────────────────────
            if is_vazio(red.get("ja_tem_imovel")) and is_vazio(red.get("has_property")):
                update_nested["real_estate_data.ja_tem_imovel"] = True
                update_nested["real_estate_data.has_property"] = True

            # ── Tipo de Imóvel ─────────────────────────────────────
            if is_vazio(red.get("tipo_imovel")):
                tipo = random.choice(TIPOS_IMOVEL)
                update_nested["real_estate_data.tipo_imovel"] = tipo

            # ── Tipologia ──────────────────────────────────────────
            if is_vazio(red.get("tipologia")) and is_vazio(red.get("num_quartos")):
                tipologia = random.choice(TIPOLOGIAS)
                update_nested["real_estate_data.tipologia"] = tipologia
                update_nested["real_estate_data.num_quartos"] = tipologia

            # ── Valor do Imóvel / Aquisição ────────────────────────
            valor_imovel_existente = red.get("valor_imovel") or red.get("valor_patrimonial")
            if is_vazio(valor_imovel_existente):
                valor_imovel = gerar_valor_imovel()
                update_nested["real_estate_data.valor_imovel"] = valor_imovel
                update_nested["real_estate_data.valor_patrimonial"] = round(
                    valor_imovel * random.uniform(0.40, 0.70), 2
                )
            else:
                valor_imovel = float(valor_imovel_existente)

            # ── Estado do Imóvel (Novo/Usado) ──────────────────────
            if is_vazio(red.get("caracteristicas")):
                estado = random.choice(ESTADOS_IMOVEL)
                # Armazenar nas características ou como campo próprio
                update_nested["real_estate_data.caracteristicas"] = [estado]

            # ── Localidade ─────────────────────────────────────────
            if is_vazio(red.get("localidade")) and is_vazio(red.get("localizacao")):
                localidade = random.choice(LOCALIDADES)
                update_nested["real_estate_data.localidade"] = localidade
                update_nested["real_estate_data.localizacao"] = localidade

            # ── Área ───────────────────────────────────────────────
            if is_vazio(red.get("area_bruta")) and is_vazio(red.get("area_util")):
                area_bruta = random.randint(55, 200)
                area_util = int(area_bruta * random.uniform(0.75, 0.90))
                update_nested["real_estate_data.area_bruta"] = str(area_bruta)
                update_nested["real_estate_data.area_util"] = str(area_util)

            # ── CPCV: Concelho e Freguesia ─────────────────────────
            if is_vazio(red.get("concelho")):
                update_nested["real_estate_data.concelho"] = random.choice(LOCALIDADES)
            if is_vazio(red.get("freguesia")):
                update_nested["real_estate_data.freguesia"] = f"Freguesia de {random.choice(LOCALIDADES)}"

            # ── Certificado Energético ─────────────────────────────
            if is_vazio(red.get("certificado_energetico")):
                update_nested["real_estate_data.certificado_energetico"] = random.choice(
                    ["A", "A+", "B", "B-", "C", "C-", "D", "E"]
                )

            # ── Estacionamento ─────────────────────────────────────
            if is_vazio(red.get("estacionamento")):
                update_nested["real_estate_data.estacionamento"] = random.choice(
                    ["1 lugar", "2 lugares", "Garagem box", "Sem estacionamento"]
                )

            # ── Valor do Financiamento (credit_data) ───────────────
            if is_vazio(cd.get("requested_amount")):
                valor_financiamento = gerar_valor_financiamento(valor_imovel)
                update_nested["credit_data.requested_amount"] = valor_financiamento

                # Prazo
                prazo_anos = random.choice([25, 30, 35, 40])
                update_nested["credit_data.loan_term_years"] = prazo_anos

                # Taxa de juro realista PT 2024-2025
                spread = round(random.uniform(0.50, 1.80), 2)
                euribor = round(random.uniform(2.5, 3.8), 2)
                taxa_anual = round(euribor + spread, 2)
                update_nested["credit_data.interest_rate"] = taxa_anual

                # Prestação mensal (fórmula francesa)
                taxa_mensal = taxa_anual / 100 / 12
                prazo_meses = prazo_anos * 12
                if taxa_mensal > 0:
                    prestacao = round(
                        valor_financiamento
                        * (taxa_mensal * (1 + taxa_mensal) ** prazo_meses)
                        / ((1 + taxa_mensal) ** prazo_meses - 1),
                        2,
                    )
                else:
                    prestacao = round(valor_financiamento / prazo_meses, 2)
                update_nested["credit_data.monthly_payment"] = prestacao

            # ── Banco (credit_data) ────────────────────────────────
            if is_vazio(cd.get("bank_name")):
                update_nested["credit_data.bank_name"] = random.choice(BANCOS_CREDITO)

            # ── Valor Financiado (no financial_data também) ────────
            fd = processo.get("financial_data") or {}
            if is_vazio(fd.get("valor_financiado")) and not is_vazio(cd.get("requested_amount")):
                update_nested["financial_data.valor_financiado"] = cd.get("requested_amount")

            if not update_nested:
                imoveis_skipped += 1
                continue

            # Montar update seguro (lida com campos-pai null como real_estate_data, credit_data)
            safe_set = build_safe_update(processo, update_nested)
            update_data = {"$set": safe_set}

            if dry_run:
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   🔄 [DRY-RUN] Processo #{proc_num} '{client_name}' → "
                      f"imóvel: {', '.join(campos)}")
            else:
                await database.processes.update_one({"id": proc_id}, update_data)
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   ✅ Processo #{proc_num} '{client_name}' actualizado com sucesso "
                      f"({', '.join(campos)})")

            imoveis_actualizados += 1

        print(f"\n   📊 Processos (imóvel): {imoveis_actualizados} actualizados, "
              f"{imoveis_skipped} já com dados completos\n")

        # ==================================================================
        # PASSO 4: PREENCHER DADOS DO 2º TITULAR (se existir)
        # ==================================================================
        print("=" * 60)
        print("👫 PASSO 4: Preencher Dados do 2º Titular (Processos)")
        print("=" * 60)

        titular2_actualizados = 0
        titular2_skipped = 0

        cursor = database.processes.find(
            {"$and": [
                process_filter,
                {"$or": [
                    {"compra_sozinho": False},
                    {"titular2_data": {"$exists": True, "$ne": None}},
                    {"co_applicants": {"$exists": True, "$ne": []}},
                    {"second_client_id": {"$exists": True, "$ne": None}},
                ]}
            ]},
            {
                "_id": 0, "id": 1, "process_number": 1, "client_name": 1,
                "compra_sozinho": 1, "titular2_data": 1, "co_applicants": 1,
                "financial_data": 1,
            }
        )
        async for processo in cursor:
            proc_id = processo.get("id")
            proc_num = processo.get("process_number", "?")
            client_name = processo.get("client_name", "Sem nome")

            t2 = processo.get("titular2_data") or {}
            fd = processo.get("financial_data") or {}

            update_nested = {}

            # ── Rendimento do 2º titular ──────────────────────────
            if is_vazio(t2.get("salario")) and is_vazio(t2.get("rendimento")):
                rend_t2 = round(random.uniform(700, 3500), 2)
                update_nested["titular2_data.salario"] = rend_t2
                update_nested["titular2_data.rendimento"] = rend_t2

            # ── Profissão do 2º titular ───────────────────────────
            if is_vazio(t2.get("profissao")):
                update_nested["titular2_data.profissao"] = random.choice(PROFISSOES)

            # ── Vínculo do 2º titular ─────────────────────────────
            if is_vazio(t2.get("tipo_contrato")) and is_vazio(t2.get("vinculo")):
                vinculo = random.choice(VINCULOS_LABORAIS)
                update_nested["titular2_data.tipo_contrato"] = vinculo
                update_nested["titular2_data.vinculo"] = vinculo

            # ── Rendimento Co-Titular (financial_data) ─────────────
            if is_vazio(fd.get("rendimento_co_titular")):
                rend_t2_val = (
                    t2.get("salario") or
                    update_nested.get("titular2_data.salario")
                )
                if rend_t2_val:
                    update_nested["financial_data.rendimento_co_titular"] = rend_t2_val

            if not update_nested:
                titular2_skipped += 1
                continue

            # Montar update seguro (lida com campos-pai null como titular2_data, financial_data)
            safe_set = build_safe_update(processo, update_nested)
            update_data = {"$set": safe_set}

            if dry_run:
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   🔄 [DRY-RUN] Processo #{proc_num} '{client_name}' → "
                      f"2º titular: {', '.join(campos)}")
            else:
                await database.processes.update_one({"id": proc_id}, update_data)
                campos = [k.split(".")[-1] for k in update_nested.keys()]
                print(f"   ✅ Processo #{proc_num} '{client_name}' 2º titular actualizado "
                      f"({', '.join(campos)})")

            titular2_actualizados += 1

        print(f"\n   📊 Processos (2º titular): {titular2_actualizados} actualizados, "
              f"{titular2_skipped} sem dados em falta\n")

        # ==================================================================
        # RESUMO FINAL
        # ==================================================================
        print("=" * 60)
        print("📊 RESUMO FINAL")
        print("=" * 60)
        print(f"   👤 Clientes (perfil):       {clientes_actualizados} actualizados")
        print(f"   💰 Processos (financeiro):  {processos_actualizados} actualizados")
        print(f"   🏠 Processos (imóvel):      {imoveis_actualizados} actualizados")
        print(f"   👫 Processos (2º titular):  {titular2_actualizados} actualizados")

        if dry_run:
            print(f"\n   ⚠️  MODO DRY-RUN: Nenhuma alteração foi gravada na BD")
            print(f"   Execute sem --dry-run para gravar as alterações")
        else:
            print(f"\n   ✅ Todas as alterações foram gravadas na BD")

        print("\n" + "=" * 60)

    finally:
        mongo_client.close()


def main():
    """Função principal."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed Fill Mock Data - Preencher dados em falta em registos existentes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Dados preenchidos:
  - Cliente (perfil): Data Nascimento, Estado Civil, Dependentes,
    Profissão, Vínculo Laboral
  - Processo (financeiro): Rendimento Base Mensal, Outros Créditos,
    Capital Próprio, Bancos de Crédito
  - Processo (imóvel): Valor Aquisição, Valor Financiamento,
    Tipo Imóvel, Estado (Novo/Usado), Tipologia, Localidade

Regras:
  - Apenas preenche campos VAZIOS (preserva dados existentes)
  - Não cria novos registos
  - Dados são aleatórios mas realistas (contexto PT)

Exemplos:
  python scripts/seed_fill_mock_data.py                    # Preenche tudo
  python scripts/seed_fill_mock_data.py --dry-run          # Ver o que seria alterado
  python scripts/seed_fill_mock_data.py --company-id=XXX   # Filtrar por empresa
        """
    )

    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostra o que seria alterado sem gravar na BD"
    )
    parser.add_argument(
        "--company-id", type=str, default=None,
        help="Filtrar por company_id específico"
    )

    args = parser.parse_args()

    asyncio.run(seed_fill_mock_data(
        dry_run=args.dry_run,
        company_id=args.company_id,
    ))


if __name__ == "__main__":
    main()
