#!/usr/bin/env python3
"""
====================================================================
SEED COMPLETO - POWERCELL
====================================================================
Popula a BD de dev com dados altamente realistas e completos:
  - Clientes com dados pessoais, financeiros e contactos completos
  - Processos com dados de imóvel, crédito, CPCV, escritura, banco
  - Finanças de processo (comissões, IVA, estado)
  - Atividades / histórico de processo
  - Tarefas e task_logs
  - Prazos (deadlines)
  - Comunicados (announcements)
  - Co-proponentes quando aplicável
  - Vendedor associado

Uso:
    python scripts/seed_completo.py [--clear]
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
from unicodedata import normalize

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from faker import Faker
except ImportError:
    print("❌ Instala o Faker: pip install Faker")
    sys.exit(1)

load_dotenv(Path(__file__).parent.parent / '.env')

fake = Faker('pt_PT')
Faker.seed(42)
random.seed(42)

# ──────────────────────────────────────────────────────────────────
# DADOS BASE PORTUGUESES
# ──────────────────────────────────────────────────────────────────

BANCOS = [
    "Caixa Geral de Depósitos", "Millennium BCP", "Novo Banco",
    "Santander Portugal", "BPI - Banco Português de Investimento",
    "Bankinter Portugal", "Montepio Geral", "Crédito Agrícola",
    "BNI Europa", "Eurobic",
]

PROFISSOES = [
    "Engenheiro Informático", "Enfermeiro", "Professor do Ensino Secundário",
    "Gestor de Conta Bancária", "Técnico Comercial", "Motorista de Pesados",
    "Engenheiro Civil", "Médico de Família", "Advogado", "Contabilista Certificado",
    "Administrativo", "Comercial", "Técnico de Informática", "Arquiteto",
    "Designer Gráfico", "Consultor de Gestão", "Analista de Sistemas",
    "Farmacêutico", "Dentista", "Fisioterapeuta", "Psicólogo Clínico",
    "Economista", "Bancário", "Gestor de Seguros", "Empresário",
    "Comerciante", "Funcionário Público", "Eletricista", "Canalizador",
    "Chef de Cozinha", "Vendedor", "Rececionista", "Jornalista",
    "Assistente Social", "Técnico de Radiologia", "Piloto Comercial",
]

TIPOS_CONTRATO = ["Efetivo", "Termo Certo", "Termo Incerto", "Recibos Verdes", "Empresário em Nome Individual"]
ESTADOS_CIVIS = ["Solteiro", "Casado", "Divorciado", "Viúvo", "União de Facto"]
NACIONALIDADES = [
    "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa",
    "Portuguesa", "Portuguesa", "Brasileira", "Angolana", "Cabo-verdiana",
    "Ucraniana", "Francesa", "Britânica",
]

EMPRESAS = [
    "EDP - Energias de Portugal, S.A.", "Galp Energia, SGPS, S.A.", "Sonae, SGPS, S.A.",
    "Jerónimo Martins, SGPS, S.A.", "Banco Santander Totta, S.A.", "CGD - Caixa Geral de Depósitos",
    "Millennium BCP, S.A.", "Continente Hipermercados, S.A.", "Pingo Doce & Irmão, Lda.",
    "Lidl Portugal, Lda.", "Vodafone Portugal, S.A.", "NOS Comunicações, S.A.",
    "Deloitte & Associados, SROC, S.A.", "KPMG & Associados, SROC, S.A.",
    "TAP Air Portugal, S.A.", "Mota-Engil, SGPS, S.A.", "Teixeira Duarte, S.A.",
    "Hospital CUF Descobertas", "Universidade de Lisboa", "Instituto Superior Técnico",
    "Câmara Municipal de Lisboa", "INEM - Instituto Nacional de Emergência Médica",
    "GNR - Guarda Nacional Republicana", "PSP - Polícia de Segurança Pública",
    "CTT - Correios de Portugal, S.A.", "Ryanair DAC", "Mercadona, S.A.",
    "Auchan Retail Portugal, S.A.",
]

CIDADES_PT = {
    "Lisboa": {"distritos": ["Lisboa"], "concelhos": ["Lisboa", "Sintra", "Cascais", "Oeiras", "Loures", "Amadora"]},
    "Porto": {"distritos": ["Porto"], "concelhos": ["Porto", "Vila Nova de Gaia", "Matosinhos", "Maia", "Gondomar"]},
    "Braga": {"distritos": ["Braga"], "concelhos": ["Braga", "Guimarães", "Barcelos", "Famalicão"]},
    "Setúbal": {"distritos": ["Setúbal"], "concelhos": ["Setúbal", "Almada", "Seixal", "Barreiro", "Moita"]},
    "Faro": {"distritos": ["Faro"], "concelhos": ["Faro", "Portimão", "Albufeira", "Loulé", "Olhão"]},
    "Coimbra": {"distritos": ["Coimbra"], "concelhos": ["Coimbra", "Figueira da Foz", "Lousã"]},
    "Aveiro": {"distritos": ["Aveiro"], "concelhos": ["Aveiro", "Ovar", "Ílhavo", "Espinho"]},
    "Leiria": {"distritos": ["Leiria"], "concelhos": ["Leiria", "Caldas da Rainha", "Nazaré"]},
}

TIPOS_IMOVEL = [
    "Apartamento T1", "Apartamento T2", "Apartamento T2+1", "Apartamento T3",
    "Apartamento T3+1", "Apartamento T4", "Moradia V3", "Moradia V4",
    "Moradia V4 com piscina", "Moradia V3 em banda",
]

TIPOLOGIAS = ["T1", "T2", "T2+1", "T3", "T3+1", "T4", "V3", "V4"]

CERTIFICADOS_ENERGETICOS = ["A+", "A", "B", "B-", "C", "D", "E", "F"]

FINALIDADES_CREDITO = [
    "Aquisição de Habitação Própria e Permanente",
    "Aquisição de Habitação Secundária",
    "Transferência de Crédito",
    "Construção de Habitação",
    "Obras e Beneficiação",
    "Refinanciamento",
]

PROCESS_STATUSES = [
    "clientes_espera", "documentacao", "analise", "pre_aprovacao",
    "credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv",
    "minuta", "escritura", "concluido", "arquivo", "perdido",
    "desistencias", "fila_espera",
]
STATUS_WEIGHTS = [12, 16, 13, 10, 8, 5, 4, 6, 4, 3, 6, 2, 3, 2, 6]

PROCESS_TYPES = [
    "credito_habitacao", "credito_habitacao", "credito_habitacao",
    "refinanciamento", "credito_pessoal", "compra_direta",
]

FONTES = ["Manual", "Website", "Indicação", "Telefone", "Email", "Feira Imobiliária", "Parceiro"]

TITULOS_TAREFAS = [
    "Recolher documentos do cliente",
    "Enviar documentação para o banco",
    "Agendar avaliação do imóvel",
    "Preparar minuta do contrato",
    "Contactar cliente para assinatura",
    "Verificar validade do CC e NIF",
    "Solicitar comprovativo de rendimentos",
    "Enviar CPCV para assinatura",
    "Confirmar dados bancários para transferência",
    "Agendar escritura no notário",
    "Atualizar dados do processo no sistema",
    "Ligar para o mediador",
    "Enviar simulação de crédito ao cliente",
    "Pedir documentos complementares",
    "Submeter proposta ao banco",
    "Confirmar data da vistoria do imóvel",
    "Rever cláusulas contratuais",
    "Contactar seguradora para cotação",
    "Enviar email de acompanhamento",
    "Verificar aprovação de crédito",
]

MOTIVOS_PERDA = [
    "Cliente desistiu — encontrou imóvel mais barato",
    "Banco recusou crédito por insuficiência de rendimentos",
    "Cliente optou por outro intermediário",
    "Negócio não fechou — vendedor retirou imóvel",
    "Taxa de esforço acima do limite bancário",
    "Cliente não conseguiu reunir capital próprio suficiente",
    "Avaliação do imóvel ficou abaixo do valor de compra",
]

NOTAS_PROCESSO = [
    "Cliente muito cooperativo, documentação entregue rapidamente.",
    "Processo urgente — cliente com CPCV assinado.",
    "Segundo titular com rendimentos variáveis (recibos verdes).",
    "Banco CGD como primeira opção do cliente.",
    "Imóvel em construção — escritura prevista após conclusão da obra.",
    "Cliente já teve crédito recusado por outro banco.",
    "Processo de transferência de crédito com spread elevado no banco atual.",
    "Necessário aguardar venda do imóvel atual para capitais próprios.",
    "Cliente expatriado, rendimentos em moeda estrangeira.",
    "Processo prioritário por indicação da direção.",
]

COMUNICADOS = [
    "Bem-vindos à nova versão do PowerCell! Exploram as novas funcionalidades do dashboard.",
    "Lembrete: prazo para submissão de simulações ao Millennium BCP termina sexta-feira.",
    "Novos documentos de RGPD disponíveis na secção de Admin — atualizem os vossos processos.",
    "A CGD lançou nova campanha com spread a partir de 0,75% para HPP. Aproveitem!",
    "Reunião de equipa esta sexta-feira às 17h30 na sala principal. Presença obrigatória.",
    "Atenção: o Banco BPI alterou os requisitos de documentação para não-residentes.",
    "Meta de março: 15 aprovações de crédito. Estamos em 9. Vamos lá!",
    "Novo parceiro imobiliário integrado: RE/MAX Lisboa. Contactem o diretor para detalhes.",
]


# ──────────────────────────────────────────────────────────────────
# FUNÇÕES DE GERAÇÃO
# ──────────────────────────────────────────────────────────────────

def nif():
    primeiro = random.choice([1, 2, 2, 3, 3, 3])
    digitos = [primeiro] + [random.randint(0, 9) for _ in range(7)]
    soma = sum(digitos[i] * (9 - i) for i in range(8))
    resto = soma % 11
    check = 0 if resto < 2 else 11 - resto
    digitos.append(check)
    return ''.join(map(str, digitos))


def cc():
    letras = ''.join(random.choices(string.ascii_uppercase, k=2))
    nums = ''.join(random.choices(string.digits, k=6))
    check = random.choice(string.digits + string.ascii_uppercase[:6])
    return f"{letras}{nums}{check}"


def telefone():
    pref = random.choice(["91", "92", "93", "96"])
    return pref + ''.join(random.choices(string.digits, k=7))


def email_from_name(nome):
    partes = normalize('NFKD', nome.lower()).encode('ASCII', 'ignore').decode().split()
    if len(partes) < 2:
        partes.append(str(random.randint(10, 99)))
    formatos = [
        f"{partes[0]}.{partes[-1]}",
        f"{partes[0]}{partes[-1]}",
        f"{partes[0][0]}.{partes[-1]}",
        f"{partes[0]}.{partes[-1]}{random.randint(1, 99)}",
    ]
    dominios = ["gmail.com", "hotmail.com", "outlook.pt", "sapo.pt", "mail.pt", "yahoo.com"]
    return f"{random.choice(formatos)}@{random.choice(dominios)}"


def data_nascimento(min_idade=22, max_idade=65):
    hoje = datetime.now()
    idade = random.randint(min_idade, max_idade)
    ano = hoje.year - idade
    mes = random.randint(1, 12)
    max_dia = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
    dia = random.randint(1, max_dia)
    return f"{dia:02d}/{mes:02d}/{ano}"


def morada_completa():
    cidade = random.choice(list(CIDADES_PT.keys()))
    info = CIDADES_PT[cidade]
    concelho = random.choice(info["concelhos"])
    distrito = info["distritos"][0]
    rua = fake.street_name()
    num = random.randint(1, 400)
    cp_pre = random.randint(1000, 9999)
    cp_suf = random.randint(100, 999)
    return {
        "morada": f"{rua}, {num}",
        "codigo_postal": f"{cp_pre}-{cp_suf}",
        "localidade": cidade,
        "concelho": concelho,
        "distrito": distrito,
        "morada_completa": f"{rua}, {num}, {cp_pre}-{cp_suf} {cidade}",
    }


def iban_pt():
    banco = random.choice(["0035", "0010", "0036", "0018", "0007", "0045"])
    conta = ''.join(random.choices(string.digits, k=15))
    return f"PT50{banco}{conta}"


def prestacao_mensal(valor, prazo_meses, taxa_anual):
    r = taxa_anual / 100 / 12
    if r == 0:
        return round(valor / prazo_meses, 2)
    return round(valor * (r * (1 + r) ** prazo_meses) / ((1 + r) ** prazo_meses - 1), 2)


def dsti(prestacao, outros_creditos, salario_bruto):
    """Debt Service to Income ratio."""
    return round((prestacao + outros_creditos) / salario_bruto * 100, 1)


def agora():
    return datetime.now(timezone.utc)


def dias_atras(n):
    return agora() - timedelta(days=n)


def dias_a_frente(n):
    return agora() + timedelta(days=n)


# ──────────────────────────────────────────────────────────────────
# GERAÇÃO DE CLIENTE COMPLETO
# ──────────────────────────────────────────────────────────────────

def gerar_cliente_completo():
    cid = str(uuid.uuid4())
    nome = fake.name()
    sexo = "M" if any(n in nome.split()[0] for n in ["José", "João", "Carlos", "Paulo", "Rui", "Pedro", "Miguel", "Luís", "António", "Manuel", "Ricardo", "Hugo", "André", "Bruno", "Nuno", "Diogo", "Tiago", "Filipe", "Rodrigo", "Rafael"]) else "F"
    estado_civil = random.choice(ESTADOS_CIVIS)
    profissao = random.choice(PROFISSOES)
    tipo_contrato = random.choice(TIPOS_CONTRATO)
    empresa = random.choice(EMPRESAS) if tipo_contrato not in ["Recibos Verdes", "Empresário em Nome Individual"] else None
    salario = round(random.uniform(900, 5500), 2)
    salario_liquido = round(salario * random.uniform(0.72, 0.80), 2)
    outros_rendimentos = round(random.uniform(0, 800), 2) if random.random() < 0.25 else 0
    capitais_proprios = round(random.uniform(15_000, 80_000), 2)
    outros_creditos = round(random.uniform(0, 600), 2) if random.random() < 0.45 else 0
    dependentes = random.choices([0, 1, 2, 3], weights=[40, 30, 20, 10])[0]
    nacionalidade = random.choice(NACIONALIDADES)
    morada_info = morada_completa()

    nif_val = nif()
    cc_val = cc()
    dn = data_nascimento()

    validade_cc = None
    if random.random() < 0.75:
        delta = random.randint(-60, 1825)
        validade_cc = (agora() + timedelta(days=delta)).strftime("%d/%m/%Y")

    return {
        "id": cid,
        "nome": nome,
        "contacto": {
            "email": email_from_name(nome),
            "email_secundario": email_from_name(nome) if random.random() < 0.2 else None,
            "telefone": telefone(),
            "telefone_secundario": telefone() if random.random() < 0.3 else None,
        },
        "dados_pessoais": {
            "nif": nif_val,
            "documento_id": cc_val,
            "data_validade_cc": validade_cc,
            "data_nascimento": dn,
            "birth_date": dn,
            "naturalidade": morada_info["localidade"],
            "nacionalidade": nacionalidade,
            "morada_fiscal": morada_info["morada_completa"],
            "codigo_postal": morada_info["codigo_postal"],
            "localidade": morada_info["localidade"],
            "concelho": morada_info["concelho"],
            "distrito": morada_info["distrito"],
            "estado_civil": estado_civil,
            "profissao": profissao,
            "nome_pai": fake.name_male(),
            "nome_mae": fake.name_female(),
            "sexo": sexo,
            "compra_tipo": "HPP",
            "menor_35_anos": True if random.random() < 0.3 else False,
        },
        "dados_financeiros": {
            "salario": salario,
            "salario_liquido": salario_liquido,
            "outros_rendimentos": outros_rendimentos,
            "rendimento_total": round(salario + outros_rendimentos, 2),
            "tipo_contrato": tipo_contrato,
            "empresa": empresa,
            "antiguidade_empresa_anos": random.randint(1, 20) if empresa else None,
            "iban": iban_pt(),
            "despesas_mensais_outros_creditos": outros_creditos,
            "capitais_proprios": capitais_proprios,
            "dependentes": dependentes,
            "tem_fiador": random.random() < 0.1,
        },
        "process_ids": [],
        "portal_access_code": None,
        "fonte": random.choice(FONTES),
        "tags": random.sample(["VIP", "urgente", "retorno", "referência", "online", "expatriado"], k=random.randint(0, 2)),
        "notas": fake.sentence() if random.random() < 0.3 else None,
        "created_at": dias_atras(random.randint(5, 180)).isoformat(),
        "updated_at": agora().isoformat(),
        "_seed_data": True,
        "_seed_script": "seed_completo",
    }


# ──────────────────────────────────────────────────────────────────
# CO-PROPONENTE
# ──────────────────────────────────────────────────────────────────

def gerar_co_proponente():
    nome = fake.name()
    salario = round(random.uniform(800, 3800), 2)
    return {
        "name": nome,
        "nif": nif(),
        "documento_id": cc(),
        "email": email_from_name(nome),
        "phone": telefone(),
        "data_nascimento": data_nascimento(),
        "profissao": random.choice(PROFISSOES),
        "salario": salario,
        "salario_liquido": round(salario * 0.77, 2),
        "tipo_contrato": random.choice(TIPOS_CONTRATO),
        "empresa": random.choice(EMPRESAS),
        "relacao": random.choice(["Cônjuge", "Companheiro(a)", "Familiar"]),
        "estado_civil": random.choice(ESTADOS_CIVIS),
        "nacionalidade": random.choice(NACIONALIDADES),
    }


# ──────────────────────────────────────────────────────────────────
# GERAÇÃO DE PROCESSO COMPLETO
# ──────────────────────────────────────────────────────────────────

def gerar_processo_completo(process_number, cliente, consultores, indexadores, intermediarios, force_status=None):
    pid = str(uuid.uuid4())
    status = force_status or random.choices(PROCESS_STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
    process_type = random.choice(PROCESS_TYPES)

    # Fases terminais
    is_terminal = status in ["concluido", "arquivo", "perdido", "desistencias"]
    is_advanced = status in ["cpcv", "minuta", "escritura", "concluido"]

    # Atribuições
    consultor = random.choice(consultores) if consultores else None
    indexador = random.choice(indexadores) if indexadores else None
    intermediario = random.choice(intermediarios) if intermediarios else None

    # ── Imóvel ──────────────────────────────────────────────────
    cidade_key = random.choice(list(CIDADES_PT.keys()))
    cidade_info = CIDADES_PT[cidade_key]
    concelho_imovel = random.choice(cidade_info["concelhos"])
    distrito_imovel = cidade_info["distritos"][0]
    tipo_imovel = random.choice(TIPOS_IMOVEL)
    tipologia = random.choice(TIPOLOGIAS)
    area_bruta = random.randint(60, 250)
    area_util = round(area_bruta * random.uniform(0.80, 0.92))
    cp_pre = random.randint(1000, 9999)
    cp_suf = random.randint(100, 999)
    valor_imovel = round(random.uniform(120_000, 600_000), 2)
    valor_patrimonial = round(valor_imovel * random.uniform(0.55, 0.80), 2)
    cert_energetico = random.choice(CERTIFICADOS_ENERGETICOS)

    # CPCV / escritura só em fases avançadas
    data_cpcv = None
    data_escritura_prevista = None
    data_entrega_chaves = None
    if status in ["cpcv", "minuta", "escritura", "concluido"]:
        data_cpcv = dias_atras(random.randint(10, 60)).strftime("%Y-%m-%d")
        data_escritura_prevista = dias_a_frente(random.randint(15, 90)).strftime("%Y-%m-%d")
    if status == "concluido":
        data_entrega_chaves = dias_atras(random.randint(1, 30)).strftime("%Y-%m-%d")

    artigo_mat = f"U-{random.randint(100, 9999)}"
    fracao = random.choice(["A", "B", "C", "D", "E", "F", "G", "H"])

    real_estate_data = {
        "ja_tem_imovel": True,
        "has_property": True,
        "ja_tem_casa_escolhida": True,
        "tipo_imovel": tipo_imovel,
        "tipologia": tipologia,
        "num_quartos": int(tipologia[1]) if tipologia[1].isdigit() else 3,
        "area_bruta": area_bruta,
        "area_util": area_util,
        "valor_imovel": valor_imovel,
        "valor_patrimonial": valor_patrimonial,
        "codigo_postal": f"{cp_pre}-{cp_suf}",
        "localidade": cidade_key,
        "freguesia": f"União de Freguesias de {concelho_imovel}",
        "concelho": concelho_imovel,
        "distrito": distrito_imovel,
        "localizacao": f"{concelho_imovel}, {distrito_imovel}",
        "certificado_energetico": cert_energetico,
        "estacionamento": random.choice([True, False]),
        "arrecadacao": random.choice([True, False]),
        "fracao": fracao,
        "artigo_matricial": artigo_mat,
        "conservatoria": f"Conservatória do Registo Predial de {concelho_imovel}",
        "numero_predial": str(random.randint(10000, 99999)),
        "finalidade": random.choice(FINALIDADES_CREDITO),
        "caracteristicas": ", ".join(random.sample([
            "Garagem", "Varanda", "Terraço", "Jardim", "Piscina",
            "Ar condicionado", "Lareira", "Domótica", "Painéis solares",
        ], k=random.randint(1, 4))),
        "descricao_imovel": fake.sentence(nb_words=20),
        "data_cpcv": data_cpcv,
        "data_escritura_prevista": data_escritura_prevista,
        "prazo_escritura_dias": random.choice([30, 45, 60, 90]) if data_escritura_prevista else None,
        "data_entrega_chaves": data_entrega_chaves,
        "condicao_suspensiva": "Sujeito a aprovação de crédito" if status not in ["concluido"] else None,
        "observacoes_cpcv": fake.sentence() if data_cpcv and random.random() < 0.4 else None,
    }

    # ── Crédito ─────────────────────────────────────────────────
    salario = cliente["dados_financeiros"]["salario"]
    outros_rendimentos = cliente["dados_financeiros"].get("outros_rendimentos", 0)
    outros_creditos = cliente["dados_financeiros"]["despesas_mensais_outros_creditos"]
    capitais_proprios = cliente["dados_financeiros"]["capitais_proprios"]

    pct_financiamento = round(random.uniform(0.75, 0.90), 4)
    valor_financiamento = round(valor_imovel * pct_financiamento, 2)
    prazo_meses = random.choice([240, 300, 360, 420, 480])
    prazo_anos = prazo_meses // 12

    spread = round(random.uniform(0.45, 1.90), 2)
    euribor = round(random.uniform(2.20, 3.90), 2)
    taxa_anual = round(euribor + spread, 2)
    tipo_taxa = random.choice(["variável", "mista", "fixa"])
    prestacao = prestacao_mensal(valor_financiamento, prazo_meses, taxa_anual)

    # Taxa de esforço
    rendimento_total = salario + outros_rendimentos
    dsti_val = dsti(prestacao, outros_creditos, rendimento_total)

    banco = random.choice(BANCOS)
    banco_aprovacao_date = None
    banco_notas = None
    if status in ["credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv", "minuta", "escritura", "concluido"]:
        banco_aprovacao_date = dias_atras(random.randint(5, 45)).strftime("%Y-%m-%d")
        banco_notas = f"Aprovação condicionada a avaliação do imóvel. Spread negociado: {spread}%."

    valor_avaliacao = None
    data_avaliacao = None
    banco_avaliacao = None
    if status in ["avaliacao", "cpcv", "minuta", "escritura", "concluido"]:
        valor_avaliacao = round(valor_imovel * random.uniform(0.92, 1.05), 2)
        data_avaliacao = dias_atras(random.randint(3, 30)).strftime("%Y-%m-%d")
        banco_avaliacao = banco

    credit_data = {
        "finalidade": real_estate_data["finalidade"],
        "valor_financiamento": valor_financiamento,
        "requested_amount": valor_financiamento,
        "pct_financiamento": round(pct_financiamento * 100, 1),
        "prazo_meses": prazo_meses,
        "prazo_anos": prazo_anos,
        "loan_term_years": prazo_anos,
        "taxa_anual": taxa_anual,
        "interest_rate": taxa_anual,
        "spread": spread,
        "euribor": euribor,
        "tipo_taxa": tipo_taxa,
        "prestacao_mensal": prestacao,
        "monthly_payment": prestacao,
        "taxa_esforco_dsti": dsti_val,
        "capital_proprio": capitais_proprios,
        "bank_name": banco,
        "bank_approval_date": banco_aprovacao_date,
        "bank_approval_notes": banco_notas,
        "valuation_value": valor_avaliacao,
        "valuation_date": data_avaliacao,
        "valuation_bank": banco_avaliacao,
        "valuation_notes": f"Avaliação realizada por perito credenciado pelo {banco_avaliacao}." if banco_avaliacao else None,
    }

    # ── Co-proponente ────────────────────────────────────────────
    compra_sozinho = random.choices([True, False], weights=[65, 35])[0]
    co_proponente = gerar_co_proponente() if not compra_sozinho else None

    # ── Vendedor ─────────────────────────────────────────────────
    vendedor = None
    if random.random() < 0.6:
        nome_vend = fake.name()
        vendedor = {
            "name": nome_vend,
            "phone": telefone(),
            "email": email_from_name(nome_vend),
            "nif": nif(),
            "banco": random.choice(BANCOS),
            "iban": iban_pt(),
            "notes": fake.sentence() if random.random() < 0.3 else None,
        }

    # Datas do processo (mais antigo = fase mais avançada)
    fase_idx = PROCESS_STATUSES.index(status)
    dias_criacao = max(10, fase_idx * 12 + random.randint(0, 20))
    created_at = dias_atras(dias_criacao).isoformat()

    notas = random.choice(MOTIVOS_PERDA) if status in ["perdido", "desistencias"] else (
        random.choice(NOTAS_PROCESSO) if random.random() < 0.5 else None
    )

    processo = {
        "id": pid,
        "process_number": process_number,

        "client_id": cliente["id"],
        "client_ids": [cliente["id"]],
        "client_name": cliente["nome"],
        "client_email": cliente["contacto"]["email"],
        "client_phone": cliente["contacto"]["telefone"],
        "client_nif": cliente["dados_pessoais"]["nif"],

        "process_type": process_type,
        "type": process_type,
        "status": status,
        "is_active": not is_terminal,

        "assigned_consultor_id": consultor["id"] if consultor else None,
        "assigned_consultor_ids": [consultor["id"]] if consultor else [],
        "consultor_names": [consultor["name"]] if consultor else [],
        "assigned_indexacao_id": indexador["id"] if indexador else None,
        "indexacao_name": indexador["name"] if indexador else None,
        "assigned_mediador_id": intermediario["id"] if intermediario else None,
        "assigned_mediador_ids": [intermediario["id"]] if intermediario else [],
        "mediador_names": [intermediario["name"]] if intermediario else [],

        "personal_data": {**cliente["dados_pessoais"]},
        "finance_data": {**cliente["dados_financeiros"]},

        "real_estate_data": real_estate_data,
        "credit_data": credit_data,

        "compra_sozinho": compra_sozinho,
        "co_buyers": [],
        "co_applicants": [co_proponente] if co_proponente else [],
        "titular2_data": co_proponente,

        "vendedor": vendedor,

        "source": cliente.get("fonte", "Manual"),
        "prioridade": random.choices(["baixa", "normal", "normal", "alta"], weights=[15, 55, 20, 10])[0],
        "labels": random.sample(["prioritário", "banco aprovado", "fiador", "2º titular", "expatriado", "renovação"], k=random.randint(0, 2)),
        "notes": notas,
        "is_indexed": status not in ["clientes_espera", "fila_espera"],

        "created_at": created_at,
        "updated_at": agora().isoformat(),
        "_seed_data": True,
        "_seed_script": "seed_completo",
    }

    return processo


# ──────────────────────────────────────────────────────────────────
# FINANÇAS DE PROCESSO
# ──────────────────────────────────────────────────────────────────

def gerar_financas(processo):
    valor_imovel = processo["real_estate_data"].get("valor_imovel", 200_000)
    valor_credito = processo["credit_data"].get("valor_financiamento", 150_000)
    status_proc = processo["status"]

    # Comissão imobiliária (3-5% do valor do imóvel)
    re_pct = round(random.uniform(2.5, 5.0), 2)
    re_commission = round(valor_imovel * re_pct / 100, 2)

    # Comissão de crédito (0.5-1.5% do crédito ou valor fixo)
    use_fixed_credit = random.random() < 0.4
    if use_fixed_credit:
        credit_fee_value = round(random.uniform(800, 2500), 2)
        credit_commission = credit_fee_value
        credit_fee_type = "fixed"
    else:
        credit_fee_pct = round(random.uniform(0.5, 1.5), 2)
        credit_commission = round(valor_credito * credit_fee_pct / 100, 2)
        credit_fee_value = credit_fee_pct
        credit_fee_type = "percentage"

    total_commission = round(re_commission + credit_commission, 2)
    iva = round(total_commission * 0.23, 2)
    total_com_iva = round(total_commission + iva, 2)

    # Estado financeiro baseado no estado do processo
    if status_proc == "concluido":
        fin_status = random.choices(["paid", "invoiced"], weights=[60, 40])[0]
    elif status_proc in ["escritura", "minuta"]:
        fin_status = random.choices(["invoiced", "pending"], weights=[50, 50])[0]
    elif status_proc in ["perdido", "desistencias"]:
        fin_status = "cancelled"
    else:
        fin_status = "pending"

    invoice_link = None
    if fin_status in ["invoiced", "paid"]:
        invoice_link = f"https://invoices.powercell.pt/fatura-{random.randint(1000, 9999)}.pdf"

    return {
        "id": str(uuid.uuid4()),
        "process_id": processo["id"],
        "client_id": processo["client_id"],
        "company_id": "power_real_estate",

        "real_estate_base_value": valor_imovel,
        "real_estate_fee_type": "percentage",
        "real_estate_fee_value": re_pct,
        "real_estate_commission": re_commission,

        "credit_base_value": valor_credito,
        "credit_fee_type": credit_fee_type,
        "credit_fee_value": credit_fee_value,
        "credit_commission": credit_commission,

        "expected_commission": total_commission,
        "tax_amount": iva,
        "total_with_tax": total_com_iva,

        "base_business_value": valor_imovel,
        "applied_fee_type": "percentage",
        "applied_fee_value": re_pct,

        "status": fin_status,
        "invoice_link": invoice_link,

        "created_at": processo["created_at"],
        "updated_at": agora().isoformat(),
        "_seed_data": True,
        "_seed_script": "seed_completo",
    }


# ──────────────────────────────────────────────────────────────────
# ATIVIDADES / HISTÓRICO
# ──────────────────────────────────────────────────────────────────

ACOES_HISTORICO = [
    ("status_change", "Status alterado para '{}'", "status"),
    ("document_upload", "Documento '{}' carregado", None),
    ("note_added", "Nota adicionada ao processo", None),
    ("bank_submitted", "Proposta submetida ao banco {}", None),
    ("client_contacted", "Cliente contactado por {}", None),
    ("field_update", "Campo '{}' atualizado", None),
]

DOCUMENTOS_TIPICOS = [
    "CC_Frente_Verso.pdf", "NIF_Documento.pdf", "IRS_Declaracao_2023.pdf",
    "Recibo_Vencimento_Jan.pdf", "Recibo_Vencimento_Fev.pdf", "Recibo_Vencimento_Mar.pdf",
    "Extrato_Bancario_3meses.pdf", "Certidao_Permanente.pdf", "Caderneta_Predial.pdf",
    "Seguro_Vida_Simulacao.pdf", "CPCV_Assinado.pdf", "Escritura_Compra.pdf",
    "Declaracao_IRS_Nota_Liquidacao.pdf", "Comprovativo_Morada.pdf",
]

def gerar_atividades(processo, users):
    atividades = []
    fase_idx = PROCESS_STATUSES.index(processo["status"])
    # Gera atividades proporcionais ao progresso
    n_atividades = max(2, fase_idx + random.randint(1, 4))

    created_dt = datetime.fromisoformat(processo["created_at"].replace("Z", "+00:00"))
    intervalo = (agora() - created_dt).days or 1
    step = intervalo / max(n_atividades, 1)

    for i in range(n_atividades):
        user = random.choice(users)
        dt = created_dt + timedelta(days=step * i + random.uniform(0, step * 0.8))
        tipo = random.choice(["status_change", "document_upload", "note_added", "field_update"])

        if tipo == "status_change":
            fase_ant = PROCESS_STATUSES[max(0, PROCESS_STATUSES.index(processo["status"]) - n_atividades + i)]
            comment = f"Estado alterado para «{fase_ant}»"
        elif tipo == "document_upload":
            doc = random.choice(DOCUMENTOS_TIPICOS)
            comment = f"Documento carregado: {doc}"
        elif tipo == "note_added":
            comment = fake.sentence(nb_words=12)
        else:
            campos = ["spread", "valor_imovel", "prazo_anos", "banco", "taxa_anual"]
            comment = f"Campo «{random.choice(campos)}» atualizado"

        atividades.append({
            "id": str(uuid.uuid4()),
            "process_id": processo["id"],
            "user_id": user["id"],
            "user_name": user["name"],
            "user_role": user.get("role", "consultor"),
            "comment": comment,
            "action": tipo,
            "created_at": dt.isoformat(),
            "_seed_data": True,
            "_seed_script": "seed_completo",
        })

    return atividades


# ──────────────────────────────────────────────────────────────────
# TAREFAS
# ──────────────────────────────────────────────────────────────────

def gerar_tarefas(processo, users):
    tarefas = []
    n = random.randint(2, 5)
    consultor_id = processo.get("assigned_consultor_id")
    criador = next((u for u in users if u["id"] == consultor_id), random.choice(users))

    for _ in range(n):
        r = random.random()
        if r < 0.35:
            dias = random.randint(-12, -1)
        elif r < 0.55:
            dias = 0
        else:
            dias = random.randint(1, 21)

        due = (agora() + timedelta(days=dias)).isoformat()
        assigned = random.sample([u["id"] for u in users], k=random.randint(1, min(2, len(users))))
        completed = random.random() < (0.7 if dias < 0 else 0.3)

        tarefas.append({
            "id": str(uuid.uuid4()),
            "title": random.choice(TITULOS_TAREFAS),
            "description": fake.sentence(nb_words=14),
            "assigned_to": assigned,
            "assigned_to_names": [u["name"] for u in users if u["id"] in assigned],
            "process_id": processo["id"],
            "process_name": processo.get("client_name", ""),
            "created_by": criador["id"],
            "created_by_name": criador.get("name", ""),
            "completed": completed,
            "completed_at": (agora() - timedelta(days=random.randint(0, 3))).isoformat() if completed else None,
            "completed_by": random.choice(assigned) if completed else None,
            "due_date": due,
            "is_overdue": dias < 0 and not completed,
            "days_until_due": dias,
            "created_at": dias_atras(random.randint(1, 20)).isoformat(),
            "updated_at": agora().isoformat(),
            "_seed_data": True,
            "_seed_script": "seed_completo",
        })
    return tarefas


# ──────────────────────────────────────────────────────────────────
# PRAZOS (DEADLINES)
# ──────────────────────────────────────────────────────────────────

TITULOS_PRAZOS = [
    "Validade do CPCV", "Prazo para entrega de documentos",
    "Data limite para aprovação bancária", "Escritura agendada",
    "Validade da simulação de crédito", "Reunião com o banco",
    "Entrega de chaves", "Prazo de condicional suspensiva",
]

def gerar_prazo(processo, users):
    dias = random.randint(-5, 60)
    prioridade = random.choice(["low", "medium", "high", "urgent"])
    assigned = random.sample([u["id"] for u in users], k=random.randint(1, 2))
    return {
        "id": str(uuid.uuid4()),
        "process_id": processo["id"],
        "title": random.choice(TITULOS_PRAZOS),
        "description": fake.sentence(nb_words=10),
        "due_date": (agora() + timedelta(days=dias)).isoformat(),
        "priority": prioridade,
        "completed": random.random() < 0.25,
        "assigned_user_ids": assigned,
        "created_by": random.choice(users)["id"],
        "created_at": dias_atras(random.randint(1, 30)).isoformat(),
        "_seed_data": True,
        "_seed_script": "seed_completo",
    }


# ──────────────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL
# ──────────────────────────────────────────────────────────────────

async def seed_completo(clear: bool = False):
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')

    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME não definidos no .env")
        sys.exit(1)

    safe_url = mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url
    print(f"\n📦 Base de Dados: {db_name}")
    print(f"🔗 {safe_url}\n")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    try:
        # ── Limpar dados anteriores ──────────────────────────────
        if clear:
            print("🗑️  A limpar seed anterior...")
            fq = {"_seed_script": "seed_completo"}
            cols = ["clients", "processes", "process_finance", "tasks", "task_logs",
                    "activities", "deadlines", "announcements", "users"]
            for col in cols:
                r = await db[col].delete_many(fq)
                if r.deleted_count:
                    print(f"   ✓ {col}: {r.deleted_count} removidos")
            print()

        # ── Utilizadores ─────────────────────────────────────────
        print("👥 A procurar utilizadores...")
        consultores = await db.users.find({"role": "consultor", "is_active": True}).to_list(50)
        indexadores = await db.users.find({"role": "indexacao", "is_active": True}).to_list(20)
        intermediarios = await db.users.find({"role": {"$in": ["intermediario", "mediador"]}, "is_active": True}).to_list(20)
        admins = await db.users.find({"role": {"$in": ["admin", "ceo", "diretor", "administrativo"]}, "is_active": True}).to_list(20)

        dummy_users = []
        if not consultores:
            print("   ⚠️  Sem consultores — a criar...")
            for nome in ["Ricardo Mendes", "Sofia Ferreira", "Pedro Carvalho", "Ana Rodrigues"]:
                uid = str(uuid.uuid4())
                doc = {
                    "id": uid, "email": f"{nome.split()[0].lower()}@powercell-dev.pt",
                    "name": nome, "phone": telefone(), "role": "consultor",
                    "company": "Power Real Estate", "is_active": True,
                    "base_salary": round(random.uniform(1500, 3000), 2),
                    "created_at": agora().isoformat(),
                    "_seed_data": True, "_seed_script": "seed_completo",
                }
                await db.users.insert_one(doc)
                consultores.append(doc)
                dummy_users.append(doc)

        if not indexadores:
            print("   ⚠️  Sem indexadores — a criar...")
            for nome in ["Ana Costa", "Mariana Silva"]:
                uid = str(uuid.uuid4())
                doc = {
                    "id": uid, "email": f"indexacao.{nome.split()[0].lower()}@powercell-dev.pt",
                    "name": nome, "phone": telefone(), "role": "indexacao",
                    "company": "Power Real Estate", "is_active": True,
                    "created_at": agora().isoformat(),
                    "_seed_data": True, "_seed_script": "seed_completo",
                }
                await db.users.insert_one(doc)
                indexadores.append(doc)
                dummy_users.append(doc)

        todos_users = consultores + indexadores + intermediarios + admins
        seen = set()
        todos_users = [u for u in todos_users if u["id"] not in seen and not seen.add(u["id"])]

        print(f"   ✅ {len(consultores)} consultores | {len(indexadores)} indexadores | "
              f"{len(intermediarios)} intermediários | {len(admins)} admin/gestão\n")

        # ── 40 Clientes ──────────────────────────────────────────
        print("🔄 A gerar 40 clientes completos...")
        clientes = [gerar_cliente_completo() for _ in range(40)]
        await db.clients.insert_many(clientes)
        print(f"   ✅ {len(clientes)} clientes criados\n")

        # ── ~35 Processos ────────────────────────────────────────
        print("🔄 A gerar processos completos...")
        ultimo = await db.processes.find_one(
            {"process_number": {"$exists": True}},
            sort=[("process_number", -1)]
        )
        last_num = ultimo.get("process_number", 0) if ultimo else 0

        clientes_para_proc = random.sample(clientes, k=min(35, len(clientes)))
        processos = []

        # Garantir distribuição: pelo menos 3 por grupo de fases
        grupos = {
            "inicio": ["clientes_espera", "fila_espera", "documentacao"],
            "analise": ["analise", "pre_aprovacao", "credito_aprovado"],
            "avancado": ["pedido_avaliacao", "avaliacao", "cpcv", "minuta"],
            "final": ["escritura", "concluido"],
            "perdidos": ["arquivo", "perdido", "desistencias"],
        }
        status_forcados = []
        for statuses in grupos.values():
            for s in statuses:
                status_forcados.extend([s, s])  # 2 de cada

        random.shuffle(status_forcados)
        # Completar com aleatorios para chegar a 35
        while len(status_forcados) < 35:
            status_forcados.append(random.choices(PROCESS_STATUSES, weights=STATUS_WEIGHTS, k=1)[0])
        status_forcados = status_forcados[:35]

        for i, (cliente, st) in enumerate(zip(clientes_para_proc, status_forcados)):
            proc = gerar_processo_completo(
                process_number=last_num + i + 1,
                cliente=cliente,
                consultores=consultores,
                indexadores=indexadores,
                intermediarios=intermediarios,
                force_status=st,
            )
            processos.append(proc)
            await db.clients.update_one(
                {"id": cliente["id"]},
                {"$push": {"process_ids": proc["id"]}}
            )

        await db.processes.insert_many(processos)
        print(f"   ✅ {len(processos)} processos criados")

        # Distribuição
        dist = {}
        for p in processos:
            dist[p["status"]] = dist.get(p["status"], 0) + 1
        for s, c in sorted(dist.items()):
            print(f"      {s}: {c}")
        print()

        # ── Finanças ─────────────────────────────────────────────
        print("💰 A gerar finanças de processo...")
        financas = [gerar_financas(p) for p in processos]
        await db.process_finance.insert_many(financas)
        print(f"   ✅ {len(financas)} registos financeiros criados\n")

        # ── Atividades ───────────────────────────────────────────
        print("📋 A gerar atividades e histórico...")
        todas_atividades = []
        for p in processos:
            todas_atividades.extend(gerar_atividades(p, todos_users))
        await db.activities.insert_many(todas_atividades)
        print(f"   ✅ {len(todas_atividades)} atividades criadas\n")

        # ── Tarefas ──────────────────────────────────────────────
        print("✅ A gerar tarefas...")
        todas_tarefas = []
        for p in processos:
            todas_tarefas.extend(gerar_tarefas(p, todos_users))
        await db.tasks.insert_many(todas_tarefas)
        completadas = sum(1 for t in todas_tarefas if t["completed"])
        atrasadas = sum(1 for t in todas_tarefas if t.get("is_overdue"))
        print(f"   ✅ {len(todas_tarefas)} tarefas | {completadas} completas | {atrasadas} atrasadas\n")

        # ── Task Logs ────────────────────────────────────────────
        print("📊 A gerar task logs...")
        tipos_log = ["PDF_GEN", "AI_ANALYSIS", "EMAIL_SEND", "DOCUMENT_UPLOAD", "REPORT_GEN"]
        logs = []
        for p in processos:
            for _ in range(random.randint(1, 3)):
                st_log = random.choices(
                    ["COMPLETED", "COMPLETED", "PROCESSING", "FAILED", "PENDING"],
                    weights=[40, 30, 10, 8, 12], k=1
                )[0]
                user = random.choice(todos_users)
                logs.append({
                    "id": str(uuid.uuid4()),
                    "task_id": str(uuid.uuid4()),
                    "user_id": user["id"],
                    "task_type": random.choice(tipos_log),
                    "status": st_log,
                    "title": f"{random.choice(tipos_log)} — {p.get('client_name', '')}",
                    "description": fake.sentence() if random.random() < 0.5 else None,
                    "progress": 100 if st_log == "COMPLETED" else random.randint(0, 90),
                    "process_id": p["id"],
                    "process_name": p.get("client_name", ""),
                    "error_message": fake.sentence() if st_log == "FAILED" else None,
                    "metadata": {},
                    "created_at": agora().isoformat(),
                    "started_at": dias_atras(random.randint(0, 2)).isoformat(),
                    "completed_at": agora().isoformat() if st_log == "COMPLETED" else None,
                    "acknowledge_required": True,
                    "acknowledged_at": None,
                    "_seed_data": True,
                    "_seed_script": "seed_completo",
                })
        await db.task_logs.insert_many(logs)
        print(f"   ✅ {len(logs)} task logs criados\n")

        # ── Prazos ───────────────────────────────────────────────
        print("⏰ A gerar prazos...")
        prazos = []
        for p in random.sample(processos, k=min(20, len(processos))):
            if random.random() < 0.6:
                prazos.append(gerar_prazo(p, todos_users))
        if prazos:
            await db.deadlines.insert_many(prazos)
        print(f"   ✅ {len(prazos)} prazos criados\n")

        # ── Comunicados ──────────────────────────────────────────
        print("📢 A gerar comunicados...")
        comunicados = []
        admin_user = admins[0] if admins else (todos_users[0] if todos_users else None)
        if admin_user:
            for texto in COMUNICADOS:
                likes = random.sample([u["id"] for u in todos_users], k=random.randint(0, min(5, len(todos_users))))
                comunicados.append({
                    "id": str(uuid.uuid4()),
                    "content": texto,
                    "author_id": admin_user["id"],
                    "author_name": admin_user["name"],
                    "likes": likes,
                    "read_by": random.sample([u["id"] for u in todos_users], k=random.randint(1, len(todos_users))),
                    "created_at": dias_atras(random.randint(0, 30)).isoformat(),
                    "_seed_data": True,
                    "_seed_script": "seed_completo",
                })
            await db.announcements.insert_many(comunicados)
        print(f"   ✅ {len(comunicados)} comunicados criados\n")

        # ── RESUMO FINAL ─────────────────────────────────────────
        print("=" * 60)
        print("📊 RESUMO FINAL")
        print("=" * 60)
        for col, label in [
            ("clients", "Clientes"), ("processes", "Processos"),
            ("process_finance", "Registos Financeiros"), ("activities", "Atividades"),
            ("tasks", "Tarefas"), ("task_logs", "Task Logs"),
            ("deadlines", "Prazos"), ("announcements", "Comunicados"),
        ]:
            total = await db[col].count_documents({"_seed_script": "seed_completo"})
            print(f"   {label}: {total}")

        print("\n🔑 Credenciais de acesso:")
        print("   Admin:      admin@powercell.pt  /  Admin123!")
        print("   Utilizadores: PowerPrecision2026!")
        print("\n💡 Para limpar: python scripts/seed_completo.py --clear")
        print("=" * 60)

    finally:
        client.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Seed Completo - PowerCell")
    parser.add_argument("--clear", action="store_true", help="Remove dados anteriores deste seed")
    args = parser.parse_args()

    print("=" * 60)
    print("🎯 SEED COMPLETO - POWERCELL")
    print("   Dados realistas e completos para desenvolvimento")
    print("=" * 60)

    asyncio.run(seed_completo(clear=args.clear))


if __name__ == "__main__":
    main()
