#!/usr/bin/env python3
"""
====================================================================
SEED MASSIVO DE MOCK DATA — POWERCELL (Pacote A)
====================================================================
Script de injeção de dados massivo e super detalhado para testar o
CRM e o Portal do Cliente ao LIMITE em ambiente DEV.

O QUE GERA (por defeito):
  - ~120 clientes principais (perfil completo: NIF válido, morada,
    data nascimento, estado civil, dependentes, profissão, vínculo
    laboral, contactos, código de acesso ao Portal).
  - 1 processo por cliente principal (~120 processos).
  - Em ~30% dos processos: SEGUNDO cliente criado e associado como
    2º titular (second_client_id + titular2_data + financeiros).
  - Dados financeiros COMPLETOS de ambos os titulares (rendimentos,
    despesas, IRS, capitais próprios, dependentes, outros créditos).
  - Dados do Imóvel simulado COMPLETOS (valor, financiamento
    pretendido, tipologia, concelho, área, certificado energético,
    datas CPCV/escritura).
  - Distribuição de estados do processo conforme percentagens pedidas:
      pre_registo 10%, clientes_espera 15%, triagem 15%,
      intermediario 30%, aprovado 10%, concluido 10%,
      desistencia 5%, eliminado (is_deleted=True) 5%.
  - Portal — Documentos: 3-5 registos em `documents` por processo,
    mistura de 'REQUESTED' (pedidos pelo consultor) e 'UPLOADED'
    (já carregados pelo cliente).
  - Portal — Mensagens: 2-4 mensagens em `portal_messages` por
    processo, simulando conversa consultor <-> cliente.
  - Tarefas: 5-10 por processo (completadas no passado, pendentes no
    futuro, e atrasadas).
  - Histórico/Atividades: 5 logs em `history` + 1-2 em `activities`
    por processo, datas aleatórias nos últimos 60 dias (mudança de
    fase, validação de documentos, comentários).

EXECUÇÃO SEGURA:
  - Usa o motor da BD local (MONGO_URL/DB_NAME do .env).
  - Por defeito ADICIONA aos existentes (não limpa). Use --clear para
    remover apenas os dados deste script antes de criar novos.
  - Inserções em batches via asyncio.gather (não rebenta com a memória).

USO:
    python backend/scripts/seed_massive_dev_data.py
    python backend/scripts/seed_massive_dev_data.py --num-clients 120 --clear
    python backend/scripts/seed_massive_dev_data.py --no-ensure-statuses
    python backend/scripts/seed_massive_dev_data.py --company-id <ID> --company-name "Power Real Estate"

OPÇÕES:
  --num-clients N           Nº de clientes principais (default 120)
  --clear                   Remove dados anteriores deste script antes de criar
  --no-ensure-statuses      Não fazer upsert dos workflow_statuses (por defeito faz)
  --company-id ID           Forçar company_id (auto-detecta se omitido)
  --company-name NOME       Forçar company_name (auto-detecta se omitido)
  --batch-size N            Tamanho do batch de insert (default 50)
  --skip-docs               Não gerar documentos do portal
  --skip-messages           Não gerar mensagens do portal
  --skip-tasks              Não gerar tarefas
  --skip-history            Não gerar histórico/atividades
  --help                    Mostra esta ajuda
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
from unicodedata import normalize

# Adicionar o diretório backend ao path (para imports de modelos)
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from faker import Faker
except ImportError:
    print("❌ Biblioteca Faker não encontrada! Instale com: pip install Faker")
    sys.exit(1)

# Tentar importar o gerador de código de acesso ao portal do modelo
try:
    from models.client import generate_portal_access_code
except Exception:
    def generate_portal_access_code() -> str:
        chars = (string.ascii_uppercase.replace('O', '').replace('I', '').replace('L', '')
                 + string.digits.replace('0', '').replace('1', ''))
        return f"{''.join(random.choice(chars) for _ in range(3))}-{''.join(random.choice(chars) for _ in range(3))}"


# Carregar variáveis de ambiente do backend/.env
load_dotenv(Path(__file__).parent.parent / '.env')

fake = Faker('pt_PT')
SEED_SCRIPT = "seed_massive_dev_data"

# ==============================================================================
# CONFIGURAÇÃO PRINCIPAL
# ==============================================================================

NUM_CLIENTS_DEFAULT = 120
SECOND_TITULAR_PCT = 0.30   # 30% dos processos têm 2º titular
BATCH_SIZE_DEFAULT = 50

# ── Distribuição de estados (percentagens somam 1.0) ──────────────────────────
# Nomes EXATOS pedidos pelo user. São upserted em workflow_statuses para
# garantirem visibilidade no Kanban (a menos que --no-ensure-statuses).
# (bucket_label, percentagem, status_string, is_active, is_deleted)
STATUS_PLAN = [
    ("pre_registo",     0.10, "pre_registo",     True,  False),
    ("clientes_espera", 0.15, "clientes_espera", True,  False),
    ("triagem",         0.15, "triagem",         True,  False),
    ("intermediario",   0.30, "intermediario",   True,  False),
    ("aprovado",        0.10, "aprovado",        True,  False),
    ("concluido",       0.10, "concluido",       False, False),
    ("desistencia",     0.05, "desistencia",     False, False),
    ("eliminado",       0.05, "desistencia",     False, True),   # is_deleted=True
]

# Workflow statuses a garantir (upsert por name)
WORKFLOW_STATUSES_TO_ENSURE = [
    {"name": "pre_registo",     "label": "Pré-Registo",        "order": 0, "color": "#94a3b8", "is_default": False, "visible_in_portal": True},
    {"name": "clientes_espera", "label": "Clientes em Espera", "order": 1, "color": "#f59e0b", "is_default": False, "visible_in_portal": True},
    {"name": "triagem",         "label": "Triagem",            "order": 2, "color": "#6B7280", "is_default": False, "visible_in_portal": True},
    {"name": "intermediario",   "label": "Intermediário",      "order": 3, "color": "#3b82f6", "is_default": False, "visible_in_portal": True},
    {"name": "aprovado",        "label": "Aprovado",           "order": 4, "color": "#10B981", "is_default": False, "visible_in_portal": True},
    {"name": "concluido",       "label": "Concluído",          "order": 5, "color": "#8B5CF6", "is_default": False, "visible_in_portal": True},
    {"name": "desistencia",     "label": "Desistência",        "order": 6, "color": "#ef4444", "is_default": False, "visible_in_portal": True},
]

# ==============================================================================
# POLOS DE DADOS REALISTAS PORTUGUESES
# ==============================================================================

PROFISSOES = [
    "Engenheiro Informático", "Enfermeiro", "Professor", "Gestor de Conta",
    "Técnico de Vendas", "Motorista", "Engenheiro Civil", "Médico",
    "Advogado", "Contabilista", "Administrativo", "Comercial",
    "Técnico de Informática", "Arquiteto", "Designer", "Consultor",
    "Analista de Sistemas", "Farmacêutico", "Dentista", "Fisioterapeuta",
    "Psicólogo", "Economista", "Bancário", "Segurador", "Empresário",
    "Comerciante", "Funcionário Público", "Eletricista", "Canalizador",
    "Cozinheiro", "Vendedor", "Rececionista", "Jornalista",
]

TIPOS_CONTRATO = ["Efetivo", "Termo Certo", "Recibos Verdes", "Empresário"]

ESTADOS_CIVIS = ["Solteiro", "Casado", "Divorciado", "Viúvo", "União de Facto"]

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
    "Vila Nova de Gaia", "Amadora", "Almada", "Oeiras", "Loures",
]

CONCELHOS = [
    "Lisboa", "Porto", "Cascais", "Sintra", "Oeiras", "Vila Nova de Gaia",
    "Matosinhos", "Braga", "Guimarães", "Coimbra", "Faro", "Setúbal",
    "Loures", "Amadora", "Almada", "Leiria", "Aveiro", "Viseu",
]

FREGUESIAS = [
    "Parque das Nações", "Belém", "Alvalade", "Campo de Ourique", "Estrela",
    "Cedofeita", "Bonjardim", "Ramalde", "São Mamede de Infesta", "Senhora da Hora",
    "São Domingos de Rana", "Alcabideche", "Massamá", "Agualva", "Queluz",
]

TIPOLOGIAS = ["T1", "T2", "T3", "T4", "T5+"]

TIPOS_IMOVEL = ["Apartamento", "Moradia", "Moradia Geminada", "Cobertura"]

BANCOS = [
    "CGD - Caixa Geral de Depósitos", "Millennium BCP", "Banco Santander",
    "Novo Banco", "Bankinter", "BPI", "ActivoBank", "Crédito Agrícola",
    "Banco CTT", "Abanca",
]

FONTES = ["Manual", "Website", "Indicação", "Telefone", "Email", "Feira", "Facebook", "Instagram"]

# Categorias de documentos do Portal (chaves válidas em DOCUMENT_CATEGORY_MAP do portal)
PORTAL_DOC_CATEGORIES = [
    "Cartao_Cidadao", "IRS", "Financeiros", "Recibo_Vencimento",
    "Comprovativo_IBAN", "Atestado_Trabalho", "Mapa_Creditos",
    "Certidao_Permanente", "Contrato_Promessa", "Certificado_Energetico",
    "Plantas_Casa", "Outros",
]

# Extensões/filenames realistas por categoria
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

# Templates de conversas Portal (consultor <-> cliente)
PORTAL_CONVERSATIONS = [
    [
        ("staff", "Bom dia! Obrigado por iniciar o seu processo. Vou precisar de alguns documentos para avançar."),
        ("client", "Bom dia! Já tenho o Cartão de Cidadão e o IRS. Onde posso entregar?"),
        ("staff", "Pode anexar diretamente aqui no Portal, na secção de Documentos. Comece pelo Cartão de Cidadão e IRS."),
        ("client", "Perfeito, já anexei. Avisam quando receberam?"),
        ("staff", "Recebido! Falta ainda o recibo de vencimento dos últimos 3 meses. Obrigado!"),
        ("client", "Já anexei o recibo, obrigado."),
    ],
    [
        ("staff", "Olá! Para avançar com a análise bancária preciso do comprovativo de IBAN e do mapa de créditos."),
        ("client", "Boa tarde! O comprovativo já está anexado. O mapa de créditos peço hoje ao banco."),
        ("staff", "Sem problema. Assim que tiver o mapa, anexe no Portal que eu avanço com a proposta."),
        ("client", "Mapa de créditos anexado. Obrigado pelo acompanhamento!"),
    ],
    [
        ("staff", "O banco solicitou o atestado de trabalho. Consegue pedir à sua empresa?"),
        ("client", "Sim, já pedi. Deve ficar pronto amanhã."),
        ("staff", "Ótimo. Assim que tiver, anexe que eu reencaminho ao banco. Estamos quase!"),
        ("client", "Anexado! Já está tudo entregue?"),
        ("staff", "Sim, está tudo entregue. Aprovada a avaliação do imóvel, marcamos a escritura. Parabéns!"),
    ],
    [
        ("staff", "Bom dia! Precisamos de atualizar alguns dados do processo. Consegue confirmar a sua morada fiscal?"),
        ("client", "Bom dia! A morada está correta no Portal. Mais alguma coisa em falta?"),
        ("staff", "Está tudo certo. Vou avançar com a submissão ao banco. Obrigado!"),
    ],
]

# Templates de comentários de atividade
ACTIVITY_COMMENTS = [
    "Processo atualizado com nova documentação.",
    "Cliente contactado para esclarecimento de dúvidas.",
    "Documentos validados e enviados para o banco.",
    "Avaliação do imóvel agendada.",
    "Proposta submetida ao banco parceiro.",
    "Cliente manifestou interesse em avançar.",
    "Reunião de acompanhamento realizada.",
    "Dados financeiros confirmados com o cliente.",
    "Agendada visita ao imóvel com o cliente.",
    "Documentação complementar solicitada.",
]

# Templates de ações de histórico (audit log)
HISTORY_ACTIONS = [
    ("Processo criado", "process_created", None, None),
    ("Estado atualizado", "status_changed", "pre_registo", "triagem"),
    ("Estado atualizado", "status_changed", "triagem", "intermediario"),
    ("Estado atualizado", "status_changed", "intermediario", "aprovado"),
    ("Documento solicitado via portal", "portal_document_requested", None, "Recibo_Vencimento"),
    ("Documento validado", "document_validated", None, "IRS"),
    ("Documento validado", "document_validated", None, "Cartao_Cidadao"),
    ("2º titular associado", "second_client_linked", None, None),
    ("Dados do imóvel atualizados", "real_estate_updated", None, None),
    ("Proposta de crédito submetida", "credit_proposal_submitted", None, None),
    ("Avaliação do imóvel concluída", "valuation_completed", None, None),
    ("Comentário adicionado", "note_added", None, None),
]


# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================

def gerar_nif_valido() -> str:
    """Gera um NIF português válido (9 dígitos, check digit correto).

    Algoritmo: 9 dígitos no total. Primeiro dígito (1/2/3 = pessoa singular)
    + 7 dígitos aleatórios + 1 dígito de controlo. O check digit é calculado
    sobre os primeiros 8 dígitos com pesos 9..2.
    """
    primeiro_digito = random.choice([1, 2, 3, 3, 3, 3, 2, 1, 3])
    digitos = [primeiro_digito] + [random.randint(0, 9) for _ in range(7)]  # 8 dígitos
    soma = sum(digitos[i] * (9 - i) for i in range(8))  # pesos 9..2 sobre 8 dígitos
    resto = soma % 11
    digito_controlo = 0 if resto < 2 else 11 - resto
    digitos.append(digito_controlo)  # 9 dígitos no total
    return ''.join(map(str, digitos))


def gerar_telefone_portugues() -> str:
    prefixo = random.choice(["91", "93", "92", "96"])
    resto = ''.join(random.choices(string.digits, k=7))
    return f"{prefixo}{resto}"


def gerar_cc_valido() -> str:
    letras = ''.join(random.choices(string.ascii_uppercase, k=2))
    numeros = ''.join(random.choices(string.digits, k=7))
    digito = random.choice(string.digits + string.ascii_uppercase)
    return f"{letras}{numeros}{digito}"


def gerar_codigo_postal() -> str:
    return f"{random.randint(1000, 9999)}-{random.randint(100, 999)}"


def gerar_morada() -> tuple:
    rua = fake.street_name()
    numero = random.randint(1, 500)
    cidade = random.choice(CIDADES)
    codigo_postal = gerar_codigo_postal()
    return f"{rua}, {numero}, {codigo_postal} {cidade}", cidade


def gerar_email(nome_completo: str) -> str:
    nomes = nome_completo.lower().split()
    if len(nomes) < 2:
        nomes = [nomes[0] if nomes else "cliente", "powercell"]
    formatos = [
        f"{nomes[0]}.{nomes[-1]}",
        f"{nomes[0]}{nomes[-1]}",
        f"{nomes[0][0]}{nomes[-1]}",
        f"{nomes[0]}.{nomes[-1]}{random.randint(1, 99)}",
    ]
    dominios = ["gmail.com", "hotmail.com", "outlook.pt", "sapo.pt", "mail.pt"]
    formato = normalize('NFKD', random.choice(formatos)).encode('ASCII', 'ignore').decode('ASCII')
    return f"{formato}@{random.choice(dominios)}"


def gerar_data_nascimento() -> str:
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


def random_past_datetime(days_max: int = 60) -> datetime:
    """Datetime aleatório nos últimos `days_max` dias."""
    delta = timedelta(
        days=random.randint(0, days_max),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return datetime.now(timezone.utc) - delta


def iso(dt: datetime) -> str:
    return dt.isoformat()


def seed_mark() -> dict:
    return {"_seed_data": True, "_seed_script": SEED_SCRIPT}


# ==============================================================================
# GERADORES DE DADOS
# ==============================================================================

def gerar_finance_data() -> dict:
    """Dados financeiros completos de um titular (rendimentos, despesas, IRS)."""
    salario_base = round(random.uniform(850, 4500), 2)
    outros_rendimentos = round(random.uniform(0, 800), 2) if random.random() < 0.3 else 0.0
    rendimento_total = round(salario_base + outros_rendimentos, 2)
    taxa_retencao = round(random.uniform(8.5, 28.5), 2)
    irs_retido_mensal = round(rendimento_total * taxa_retencao / 100, 2)
    escalao_irs = random.choice([
        "1º escalão (até 7.116€)", "2º escalão (7.116-10.732€)",
        "3º escalão (10.732-20.261€)", "4º escalão (>20.261€)",
    ])
    renda_mensal = round(random.uniform(0, 900), 2) if random.random() < 0.5 else 0.0
    prestacao_auto = round(random.uniform(0, 450), 2) if random.random() < 0.25 else 0.0
    outros_creditos = round(random.uniform(0, 400), 2) if random.random() < 0.3 else 0.0
    despesas_total = round(renda_mensal + prestacao_auto + outros_creditos, 2)
    capitais_proprios = round(random.uniform(10000, 80000), 2)
    dependentes = random.randint(0, 4)
    tipo_contrato = random.choice(TIPOS_CONTRATO)
    empresa = random.choice(EMPRESAS) if random.random() < 0.75 else None
    antiguidade_anos = random.randint(0, 25) if empresa else None
    return {
        "salario": salario_base,
        "vencimento_mensal": salario_base,
        "outros_rendimentos": outros_rendimentos,
        "rendimento_total": rendimento_total,
        "tipo_contrato": tipo_contrato,
        "empresa": empresa,
        "antiguidade_anos": antiguidade_anos,
        "irs_taxa_retencao": taxa_retencao,
        "irs_retido_mensal": irs_retido_mensal,
        "escalao_irs": escalao_irs,
        "renda_mensal": renda_mensal,
        "prestacao_automovel": prestacao_auto,
        "outros_creditos_mensais": outros_creditos,
        "despesas_mensais_outros_creditos": outros_creditos,
        "despesas_mensais_total": despesas_total,
        "capitais_proprios": capitais_proprios,
        "dependentes": dependentes,
    }


def gerar_real_estate_data() -> dict:
    """Dados completos do Imóvel simulado."""
    valor_imovel = round(random.uniform(120000, 650000), 2)
    concelho = random.choice(CONCELHOS)
    tipologia = random.choice(TIPOLOGIAS)
    tipo_imovel = random.choice(TIPOS_IMOVEL)
    area_bruta = random.randint(55, 220)
    area_util = round(area_bruta * random.uniform(0.82, 0.92), 1)
    return {
        "ja_tem_imovel": True,
        "has_property": True,
        "ja_tem_casa_escolhida": True,
        "valor_imovel": valor_imovel,
        "valor_maximo_imovel": valor_imovel,
        "valor_patrimonial": round(valor_imovel * random.uniform(0.55, 0.75), 2),
        "tipo_imovel": tipo_imovel,
        "tipologia": tipologia,
        "num_quartos": tipologia,
        "localizacao": concelho,
        "localidade": concelho,
        "concelho": concelho,
        "freguesia": random.choice(FREGUESIAS),
        "codigo_postal": gerar_codigo_postal(),
        "area_bruta": str(area_bruta),
        "area_util": str(area_util),
        "area_pretendida": float(area_util),
        "certificado_energetico": random.choice(["A", "B", "B-", "C", "D", "E"]),
        "estacionamento": str(random.randint(0, 2)),
        "arrecadacao": str(random.randint(0, 1)) if random.random() < 0.4 else "0",
        "finalidade": random.choice(["Habitação Própria Permanente", "Aquisição HPP", "Construção", "Transferência de Crédito"]),
        "data_cpcv": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d"),
        "data_escritura_prevista": (datetime.now(timezone.utc) + timedelta(days=random.randint(30, 180))).strftime("%Y-%m-%d"),
        "prazo_escritura_dias": random.randint(30, 120),
        "condicao_suspensiva": random.choice(["Obtenção de financiamento bancário", "Sem condições suspensivas"]),
        "descricao_imovel": f"{tipo_imovel} {tipologia} em {concelho}, com {area_bruta}m² de área bruta.",
    }


def gerar_credit_data(valor_imovel: float) -> dict:
    """Dados completos de crédito / financiamento pretendido."""
    pct = round(random.uniform(0.70, 0.90), 4)
    requested_amount = round(valor_imovel * pct, 2)
    loan_term_years = random.choice([20, 25, 30, 35, 40])
    interest_rate = round(random.uniform(2.8, 4.5), 2)
    euribor = round(random.uniform(2.5, 3.8), 2)
    spread = round(max(0.40, interest_rate - euribor), 2)
    r = interest_rate / 100 / 12
    n = loan_term_years * 12
    monthly_payment = round(requested_amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1), 2) if r > 0 else round(requested_amount / n, 2)
    return {
        "finalidade": "Aquisição HPP",
        "requested_amount": requested_amount,
        "valor_financiamento": requested_amount,
        "loan_amount": requested_amount,
        "loan_term_years": loan_term_years,
        "prazo_anos": loan_term_years,
        "prazo_meses": loan_term_years * 12,
        "interest_rate": interest_rate,
        "taxa_anual": interest_rate,
        "spread": spread,
        "euribor": euribor,
        "tipo_taxa": random.choice(["variável", "mista", "fixa"]),
        "monthly_payment": monthly_payment,
        "prestacao_mensal": monthly_payment,
        "bank_name": random.choice(BANCOS),
        "pct_financiamento": round(pct * 100, 1),
        "bank_approval_date": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d")
                               if random.random() < 0.3 else None,
    }


def gerar_cliente(client_id: str, company_id: str, company_name: str, created_dt: datetime) -> dict:
    """Cliente principal com perfil COMPLETO."""
    nome_completo = fake.name()
    email = gerar_email(nome_completo)
    telefone = gerar_telefone_portugues()
    telefone_secundario = gerar_telefone_portugues() if random.random() < 0.3 else None
    email_secundario = gerar_email(nome_completo) if random.random() < 0.15 else None
    nif = gerar_nif_valido()
    cc = gerar_cc_valido()
    data_nascimento = gerar_data_nascimento()
    morada, cidade = gerar_morada()
    nacionalidade = random.choice(
        ["Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa",
         "Brasileira", "Angolana", "Cabo-verdiana", "Ucraniana"]
    )
    sexo = random.choice(["M", "F"])
    data_validade_cc = None
    if random.random() < 0.7:
        validade = datetime.now(timezone.utc) + timedelta(days=random.randint(-180, 1825))
        data_validade_cc = validade.strftime("%d/%m/%Y")
    finance = gerar_finance_data()
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
            "estado_civil": random.choice(ESTADOS_CIVIS),
            "profissao": random.choice(PROFISSOES),
            "nome_pai": fake.name_male(),
            "nome_mae": fake.name_female(),
            "sexo": sexo,
        },
        "process_ids": [],
        "portal_access_code": generate_portal_access_code(),
        "dados_financeiros": finance,
        "financial_data": finance,
        "fonte": random.choice(FONTES),
        "tags": random.sample(["VIP", "urgente", "retorno", "referência", "online"], k=random.randint(0, 2)),
        "notas": fake.sentence() if random.random() < 0.25 else None,
        "created_at": iso(created_dt),
        "updated_at": iso(created_dt),
        "created_by": SEED_SCRIPT,
        "company_id": company_id,
        "company_name": company_name,
        **seed_mark(),
    }
    return cliente


def gerar_segundo_titular(client_id: str, company_id: str, company_name: str, created_dt: datetime) -> dict:
    """Segundo titular — cliente completo com dados financeiros próprios."""
    # Garantir género coerente com cônjuge/companheiro
    nome_completo = fake.name()
    email = gerar_email(nome_completo)
    telefone = gerar_telefone_portugues()
    nif = gerar_nif_valido()
    cc = gerar_cc_valido()
    data_nascimento = gerar_data_nascimento()
    morada, cidade = gerar_morada()
    data_validade_cc = None
    if random.random() < 0.7:
        validade = datetime.now(timezone.utc) + timedelta(days=random.randint(-180, 1825))
        data_validade_cc = validade.strftime("%d/%m/%Y")
    finance = gerar_finance_data()
    return {
        "id": client_id,
        "nome": nome_completo,
        "contacto": {
            "email": email,
            "telefone": telefone,
        },
        "dados_pessoais": {
            "nif": nif,
            "documento_id": cc,
            "data_validade_cc": data_validade_cc,
            "data_nascimento": data_nascimento,
            "birth_date": data_nascimento,
            "naturalidade": cidade,
            "nacionalidade": "Portuguesa",
            "morada_fiscal": morada,
            "estado_civil": random.choice(["Casado", "União de Facto"]),
            "profissao": random.choice(PROFISSOES),
            "nome_pai": fake.name_male(),
            "nome_mae": fake.name_female(),
            "sexo": random.choice(["M", "F"]),
        },
        "process_ids": [],
        "portal_access_code": generate_portal_access_code(),
        "dados_financeiros": finance,
        "financial_data": finance,
        "fonte": "segundo_titular",
        "tags": [],
        "created_at": iso(created_dt),
        "updated_at": iso(created_dt),
        "created_by": SEED_SCRIPT,
        "company_id": company_id,
        "company_name": company_name,
        **seed_mark(),
    }


def gerar_titular2_data(segundo_cliente: dict) -> dict:
    """Denormaliza titular2_data a partir do 2º cliente (lido pelo frontend)."""
    sc_contacto = segundo_cliente.get("contacto", {})
    sc_dados = segundo_cliente.get("dados_pessoais", {})
    sc_finance = segundo_cliente.get("dados_financeiros", {})
    return {
        "name": segundo_cliente.get("nome", ""),
        "nome": segundo_cliente.get("nome", ""),
        "email": sc_contacto.get("email", ""),
        "phone": sc_contacto.get("telefone", ""),
        "telefone": sc_contacto.get("telefone", ""),
        "nif": sc_dados.get("nif", ""),
        "documento_id": sc_dados.get("documento_id"),
        "data_nascimento": sc_dados.get("data_nascimento"),
        "birth_date": sc_dados.get("birth_date") or sc_dados.get("data_nascimento"),
        "morada_fiscal": sc_dados.get("morada_fiscal"),
        "estado_civil": sc_dados.get("estado_civil", ""),
        "profissao": sc_dados.get("profissao", ""),
        "nacionalidade": sc_dados.get("nacionalidade", ""),
        "naturalidade": sc_dados.get("naturalidade", ""),
        "sexo": sc_dados.get("sexo", ""),
        "relacao": random.choice(["Cônjuge", "Companheiro(a)"]),
        "salario": sc_finance.get("salario"),
        "tipo_contrato": sc_finance.get("tipo_contrato"),
        "empresa": sc_finance.get("empresa"),
        "rendimento_total": sc_finance.get("rendimento_total"),
        "irs_taxa_retencao": sc_finance.get("irs_taxa_retencao"),
        "dependentes": sc_finance.get("dependentes"),
    }


def gerar_processo(
    process_number: int,
    cliente: dict,
    segundo_titular: dict | None,
    consultor: dict | None,
    indexador: dict | None,
    intermediario: dict | None,
    status_string: str,
    is_active: bool,
    is_deleted: bool,
    company_id: str,
    company_name: str,
    created_dt: datetime,
) -> dict:
    """Gera um processo completo com imóvel, crédito e (opcional) 2º titular."""
    process_type = random.choice([
        "credito_habitacao", "credito_habitacao", "credito_habitacao",
        "credito_pessoal", "compra_direta", "arrendamento", "refinanciamento",
    ])
    real_estate = gerar_real_estate_data()
    credit = gerar_credit_data(real_estate["valor_imovel"])
    cliente_finance = cliente.get("dados_financeiros", {})

    titular2_data = gerar_titular2_data(segundo_titular) if segundo_titular else None
    second_client_id = segundo_titular["id"] if segundo_titular else None
    second_client_name = segundo_titular["nome"] if segundo_titular else None

    updated_dt = created_dt + timedelta(days=random.randint(1, 59), hours=random.randint(0, 23))
    if updated_dt > datetime.now(timezone.utc):
        updated_dt = datetime.now(timezone.utc)

    processo = {
        "id": str(uuid.uuid4()),
        "process_number": process_number,
        "client_id": cliente["id"],
        "client_ids": [cliente["id"]],
        "client_name": cliente["nome"],
        "client_email": cliente["contacto"]["email"],
        "client_phone": cliente["contacto"]["telefone"],
        "client_nif": cliente["dados_pessoais"]["nif"],
        "second_client_id": second_client_id,
        "second_client_name": second_client_name,
        "process_type": process_type,
        "type": process_type,
        "status": status_string,
        "is_active": is_active,
        "is_deleted": is_deleted,
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
        "mediador_names": [intermediario["name"]] if intermediario else None,
        # Dados do cliente principal (denormalizado)
        "personal_data": cliente.get("dados_pessoais", {}).copy(),
        "finance_data": cliente_finance,
        # Dados do imóvel e crédito
        "real_estate_data": real_estate,
        "credit_data": credit,
        # 2º titular
        "compra_sozinho": segundo_titular is None,
        "titular2_data": titular2_data,
        "co_buyers": [],
        "co_applicants": [titular2_data] if titular2_data else [],
        # Metadados
        "source": cliente.get("fonte", "Manual"),
        "prioridade": random.choice(["baixa", "normal", "normal", "normal", "alta"]),
        "labels": random.sample(["prioritário", "banco X", "fiador", "2º titular", "expatriado"], k=random.randint(0, 2)),
        "notes": fake.sentence() if random.random() < 0.3 else None,
        "company_id": company_id,
        "company_name": company_name,
        "created_at": iso(created_dt),
        "updated_at": iso(updated_dt),
        **seed_mark(),
    }
    return processo


def gerar_documento_requested(process_id: str, consultor: dict | None, created_dt: datetime) -> dict:
    """Documento PEDIDO pelo consultor (status REQUESTED) — visível no Portal."""
    category = random.choice(PORTAL_DOC_CATEGORIES)
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
        "requested_by": consultor["id"] if consultor else SEED_SCRIPT,
        "requested_by_name": consultor["name"] if consultor else "Sistema",
        "source": "admin_request",
        "file_size": None,
        "content_type": None,
        "uploaded_at": None,
        "created_at": iso(created_dt),
        "updated_at": iso(created_dt),
        **seed_mark(),
    }


def gerar_documento_uploaded(process_id: str, client_name: str, uploaded_dt: datetime) -> dict:
    """Documento JÁ CARREGADO pelo cliente (status UPLOADED) — visível no Portal."""
    category = random.choice(PORTAL_DOC_CATEGORIES)
    filename = random.choice(DOC_FILENAME_BY_CATEGORY.get(category, ["documento.pdf"]))
    file_size = random.randint(45000, 5_500_000)
    content_type = "application/pdf"
    s3_path = f"portal-uploads/{process_id}/{uuid.uuid4().hex}/{filename}"
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
        "content_type": content_type,
        "uploaded_by": "portal_client",
        "source": "client_portal",
        "uploaded_at": iso(uploaded_dt),
        "created_at": iso(uploaded_dt),
        "updated_at": iso(uploaded_dt),
        **seed_mark(),
    }


def gerar_mensagem_portal(process_id: str, sender_type: str, sender_name: str, content: str, created_dt: datetime) -> dict:
    """Mensagem do Portal (consultor <-> cliente)."""
    is_client = sender_type == "client"
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "sender_type": sender_type,
        "sender_id": "client" if is_client else SEED_SCRIPT,
        "sender_name": sender_name,
        "content": content,
        "created_at": iso(created_dt),
        "read_by_client": is_client,        # cliente lê as suas
        "read_by_staff": not is_client,     # staff lê as suas
        **seed_mark(),
    }


def gerar_tarefa(
    processo: dict,
    utilizadores: list,
    created_by_user: dict | None,
    kind: str,  # "completed" | "pending" | "overdue"
    created_dt: datetime,
) -> dict:
    """Gera uma tarefa (completed no passado / pending no futuro / overdue atrasada)."""
    titulo = random.choice(TITULOS_TAREFAS)
    descricao = random.choice(DESCRICOES_TAREFAS)
    assigned_to = random.sample(
        [u["id"] for u in utilizadores], k=random.randint(1, min(2, len(utilizadores)))
    )
    assigned_names = [u["name"] for u in utilizadores if u["id"] in assigned_to]
    now = datetime.now(timezone.utc)

    if kind == "completed":
        due_date = (now - timedelta(days=random.randint(1, 30))).isoformat()
        completed = True
        completed_at = (now - timedelta(days=random.randint(0, 3))).isoformat()
        completed_by = random.choice(assigned_to)
    elif kind == "pending":
        due_date = (now + timedelta(days=random.randint(1, 21))).isoformat()
        completed = False
        completed_at = None
        completed_by = None
    else:  # overdue
        due_date = (now - timedelta(days=random.randint(1, 14))).isoformat()
        completed = False
        completed_at = None
        completed_by = None

    is_overdue = False
    days_until_due = None
    try:
        due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
        delta = (due_dt - now).days
        days_until_due = delta
        is_overdue = delta < 0 and not completed
    except (ValueError, TypeError):
        pass

    created_by_id = created_by_user["id"] if created_by_user else SEED_SCRIPT
    created_by_name = created_by_user.get("name", "Sistema") if created_by_user else "Sistema"

    return {
        "id": str(uuid.uuid4()),
        "title": titulo,
        "description": descricao,
        "assigned_to": assigned_to,
        "assigned_to_names": assigned_names,
        "process_id": processo["id"],
        "process_name": processo.get("client_name", "N/A"),
        "created_by": created_by_id,
        "created_by_name": created_by_name,
        "completed": completed,
        "completed_at": completed_at,
        "completed_by": completed_by,
        "due_date": due_date,
        "is_overdue": is_overdue,
        "days_until_due": days_until_due,
        "created_at": iso(created_dt),
        "updated_at": iso(now),
        **seed_mark(),
    }


def gerar_historico(process_id: str, user: dict | None, action_template: tuple, created_dt: datetime) -> dict:
    """Registo de histórico/audit log."""
    action, field, old_value, new_value = action_template
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"] if user else SEED_SCRIPT,
        "user_name": user.get("name", "Sistema") if user else "Sistema",
        "action": action,
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "created_at": iso(created_dt),
        **seed_mark(),
    }


def gerar_activity(process_id: str, user: dict | None, comment: str, created_dt: datetime) -> dict:
    """Atividade/comentário num processo."""
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"] if user else SEED_SCRIPT,
        "user_name": user.get("name", "Sistema") if user else "Sistema",
        "user_role": user.get("role", "consultor") if user else "consultor",
        "comment": comment,
        "created_at": iso(created_dt),
        **seed_mark(),
    }


# ==============================================================================
# HELPERS DE EXECUÇÃO
# ==============================================================================

def chunk(lst: list, size: int) -> list:
    """Parte uma lista em chunks de tamanho `size`."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


async def batch_insert(db, collection_name: str, docs: list, batch_size: int) -> int:
    """Insere documentos em batches usando asyncio.gather (não estoura a memória)."""
    if not docs:
        return 0
    collection = db[collection_name]
    batches = chunk(docs, batch_size)
    inserted = 0

    async def _insert_one_batch(batch):
        result = await collection.insert_many(batch, ordered=False)
        return len(result.inserted_ids)

    results = await asyncio.gather(*[_insert_one_batch(b) for b in batches])
    inserted = sum(results)
    return inserted


def build_status_counts(total: int) -> list:
    """Reparte `total` processos pelos buckets do STATUS_PLAN conforme percentagens."""
    counts = []
    remaining = total
    for i, (label, pct, status_string, is_active, is_deleted) in enumerate(STATUS_PLAN):
        if i == len(STATUS_PLAN) - 1:
            n = remaining  # último bucket fica com o resto (garante soma = total)
        else:
            n = round(total * pct)
            remaining -= n
        counts.append((label, n, status_string, is_active, is_deleted))
    return counts


async def resolve_company(db, forced_id: str | None, forced_name: str | None) -> tuple:
    """Detecta a empresa ativa (company_id, company_name)."""
    if forced_id:
        name = forced_name or forced_id
        return forced_id, name

    # 1. user_company_roles: empresa mais comum marcada como is_default
    try:
        pipeline = [
            {"$match": {"is_default": True}},
            {"$group": {"_id": {"cid": "$company_id", "cname": "$company_name"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        rows = await db.user_company_roles.aggregate(pipeline).to_list(10)
        if rows:
            cid = rows[0]["_id"].get("cid")
            cname = rows[0]["_id"].get("cname") or cid
            if cid:
                return cid, cname
    except Exception:
        pass

    # 2. user_company_roles: empresa mais comum (sem is_default)
    try:
        pipeline = [
            {"$group": {"_id": {"cid": "$company_id", "cname": "$company_name"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        rows = await db.user_company_roles.aggregate(pipeline).to_list(10)
        if rows and rows[0]["_id"].get("cid"):
            cid = rows[0]["_id"]["cid"]
            cname = rows[0]["_id"].get("cname") or cid
            return cid, cname
    except Exception:
        pass

    # 3. company_email_configs: primeira config
    try:
        cfg = await db.company_email_configs.find_one({}, {"company_name": 1, "id": 1})
        if cfg:
            return cfg.get("id") or cfg.get("company_name"), cfg.get("company_name", "Power Real Estate")
    except Exception:
        pass

    # 4. users: empresa (campo `company`) mais comum
    try:
        pipeline = [
            {"$match": {"company": {"$exists": True, "$nin": ["", None]}}},
            {"$group": {"_id": "$company", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        rows = await db.users.aggregate(pipeline).to_list(10)
        if rows and rows[0]["_id"]:
            cname = rows[0]["_id"]
            return cname, cname
    except Exception:
        pass

    # 5. Fallback
    return "power-real-estate", "Power Real Estate"


async def resolve_users(db) -> dict:
    """Busca utilizadores existentes por role; cria dummies se faltarem."""
    consultores = await db.users.find({"role": "consultor", "is_active": {"$ne": False}}).to_list(100)
    indexadores = await db.users.find({"role": "indexacao", "is_active": {"$ne": False}}).to_list(100)
    intermediarios = await db.users.find({"role": "intermediario", "is_active": {"$ne": False}}).to_list(100)
    gestores = await db.users.find(
        {"role": {"$in": ["administrativo", "diretor", "ceo", "admin"]}, "is_active": {"$ne": False}}
    ).to_list(100)

    async def _create_dummy(name: str, role: str) -> dict:
        uid = str(uuid.uuid4())
        doc = {
            "id": uid,
            "email": f"{name.split()[0].lower()}@powercell-dev.pt",
            "name": name,
            "phone": gerar_telefone_portugues(),
            "role": role,
            "company": "Power Real Estate",
            "is_active": True,
            "created_at": iso(datetime.now(timezone.utc)),
            **seed_mark(),
        }
        await db.users.insert_one(doc)
        return doc

    if not consultores:
        consultores = [
            await _create_dummy("Ricardo Mendes", "consultor"),
            await _create_dummy("Sofia Ferreira", "consultor"),
            await _create_dummy("João Pereira", "consultor"),
        ]
    if not indexadores:
        indexadores = [await _create_dummy("Ana Costa", "indexacao")]
    if not intermediarios:
        intermediarios = [await _create_dummy("Carlos Santos", "intermediario")]

    todos = consultores + indexadores + intermediarios + gestores
    seen = set()
    todos = [u for u in todos if u["id"] not in seen and not seen.add(u["id"])]

    print(f"   ✅ {len(consultores)} consultores, {len(indexadores)} indexadores, "
          f"{len(intermediarios)} intermediários, {len(gestores)} gestão")
    return {
        "consultores": consultores,
        "indexadores": indexadores,
        "intermediarios": intermediarios,
        "gestores": gestores,
        "todos": todos,
    }


async def ensure_workflow_statuses(db) -> None:
    """Upsert dos workflow_statuses usados pelo seed (garante visibilidade no Kanban)."""
    for s in WORKFLOW_STATUSES_TO_ENSURE:
        existing = await db.workflow_statuses.find_one({"name": s["name"]})
        if existing:
            # Atualiza label/color/order se vazio, sem destruir config existente
            updates = {}
            for k in ("label", "color", "order", "visible_in_portal"):
                if existing.get(k) in (None, "") and s.get(k) is not None:
                    updates[k] = s[k]
            if updates:
                await db.workflow_statuses.update_one({"name": s["name"]}, {"$set": updates})
        else:
            doc = {
                "id": str(uuid.uuid4()),
                **s,
                "description": f"Estado {s['label']} (criado pelo seed massivo)",
                "is_default": s.get("is_default", False),
                "internal_code": s["name"],
                "created_at": iso(datetime.now(timezone.utc)),
                **seed_mark(),
            }
            await db.workflow_statuses.insert_one(doc)


# ==============================================================================
# FUNÇÃO PRINCIPAL
# ==============================================================================

async def seed_massive(
    num_clients: int = NUM_CLIENTS_DEFAULT,
    clear: bool = False,
    ensure_statuses: bool = True,
    company_id_forced: str | None = None,
    company_name_forced: str | None = None,
    batch_size: int = BATCH_SIZE_DEFAULT,
    skip_docs: bool = False,
    skip_messages: bool = False,
    skip_tasks: bool = False,
    skip_history: bool = False,
):
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos no backend/.env")
        sys.exit(1)

    safe_url = mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url
    print("\n" + "=" * 70)
    print("🚀 SEED MASSIVO DE MOCK DATA — POWERCELL (Pacote A)")
    print("=" * 70)
    print(f"📦 Base de Dados: {db_name}")
    print(f"🔗 Ligação: {safe_url}")
    print(f"🎯 Clientes a gerar: {num_clients}")
    print(f"🔀 2º titular em ~{int(SECOND_TITULAR_PCT * 100)}% dos processos")
    print(f"📦 Batch size: {batch_size}")
    print("=" * 70)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    try:
        # ── PASSO 0: Limpar dados anteriores deste script ──
        if clear:
            print("\n🗑️  A remover dados anteriores deste script...")
            f = {"_seed_script": SEED_SCRIPT}
            res_c = await db.clients.delete_many(f)
            res_p = await db.processes.delete_many(f)
            res_d = await db.documents.delete_many(f)
            res_m = await db.portal_messages.delete_many(f)
            res_t = await db.tasks.delete_many(f)
            res_h = await db.history.delete_many(f)
            res_a = await db.activities.delete_many(f)
            print(f"   ✅ Removidos: {res_c.deleted_count} clientes, "
                  f"{res_p.deleted_count} processos, {res_d.deleted_count} documentos, "
                  f"{res_m.deleted_count} mensagens, {res_t.deleted_count} tarefas, "
                  f"{res_h.deleted_count} históricos, {res_a.deleted_count} atividades")

        # ── PASSO 1: Resolver empresa ativa ──
        print("\n🏢 A detetar empresa ativa...")
        company_id, company_name = await resolve_company(db, company_id_forced, company_name_forced)
        print(f"   ✅ Empresa: {company_name} (id={company_id})")

        # ── PASSO 2: Garantir workflow_statuses ──
        if ensure_statuses:
            print("\n📋 A garantir workflow_statuses...")
            await ensure_workflow_statuses(db)
            print(f"   ✅ {len(WORKFLOW_STATUSES_TO_ENSURE)} estados garantidos no Kanban")
        else:
            print("\n⏭️  --no-ensure-statuses: workflow_statuses não verificados")

        # ── PASSO 3: Resolver utilizadores ──
        print("\n👥 A procurar utilizadores (consultores/indexadores/intermediários)...")
        users = await resolve_users(db)

        # ── PASSO 4: Gerar clientes principais ──
        print(f"\n🔄 A gerar {num_clients} clientes principais (perfil completo)...")
        clientes = []
        for i in range(num_clients):
            cid = str(uuid.uuid4())
            created_dt = random_past_datetime(60)
            cliente = gerar_cliente(cid, company_id, company_name, created_dt)
            clientes.append(cliente)
        n_clientes = await batch_insert(db, "clients", clientes, batch_size)
        print(f"   ✅ {n_clientes} clientes principais inseridos")

        # ── PASSO 5: Distribuir estados e gerar processos ──
        print("\n🔄 A gerar processos (1 por cliente) + 2º titular em ~30%...")
        status_counts = build_status_counts(num_clients)

        # Construir lista de (status_string, is_active, is_deleted) por posição
        status_assignments = []
        for label, n, status_string, is_active, is_deleted in status_counts:
            status_assignments.extend([(status_string, is_active, is_deleted)] * n)
        random.shuffle(status_assignments)

        # Último process_number
        ultimo = await db.processes.find_one(
            {"process_number": {"$exists": True}}, sort=[("process_number", -1)]
        )
        proximo_num = (ultimo.get("process_number", 0) or 0) + 1 if ultimo else 1

        processos = []
        segundos_titulares = []
        for i, cliente in enumerate(clientes):
            status_string, is_active, is_deleted = status_assignments[i]
            created_dt = random_past_datetime(60)
            # ~30% têm 2º titular
            segundo = None
            if random.random() < SECOND_TITULAR_PCT:
                sid = str(uuid.uuid4())
                segundo = gerar_segundo_titular(sid, company_id, company_name, created_dt)
                segundos_titulares.append(segundo)

            consultor = random.choice(users["consultores"]) if users["consultores"] else None
            indexador = random.choice(users["indexadores"]) if users["indexadores"] else None
            intermediario = random.choice(users["intermediarios"]) if users["intermediarios"] else None

            processo = gerar_processo(
                process_number=proximo_num + i,
                cliente=cliente,
                segundo_titular=segundo,
                consultor=consultor,
                indexador=indexador,
                intermediario=intermediario,
                status_string=status_string,
                is_active=is_active,
                is_deleted=is_deleted,
                company_id=company_id,
                company_name=company_name,
                created_dt=created_dt,
            )
            processos.append(processo)

            # Ligar cliente principal ao processo
            cliente["process_ids"] = [processo["id"]]
            if segundo:
                segundo["process_ids"] = [processo["id"]]

        # Inserir 2ºs titulares
        if segundos_titulares:
            n_seg = await batch_insert(db, "clients", segundos_titulares, batch_size)
            print(f"   ✅ {n_seg} 2ºs titulares inseridos")

        # Inserir processos
        n_procs = await batch_insert(db, "processes", processos, batch_size)
        print(f"   ✅ {n_procs} processos inseridos")

        # Atualizar process_ids nos clientes principais (batch)
        print("   🔗 A ligar clientes aos processos...")
        update_tasks = []
        for cliente in clientes:
            pid = cliente["process_ids"][0] if cliente["process_ids"] else None
            if pid:
                update_tasks.append(
                    db.clients.update_one({"id": cliente["id"]}, {"$set": {"process_ids": cliente["process_ids"]}})
                )
        for segundo in segundos_titulares:
            pid = segundo["process_ids"][0] if segundo["process_ids"] else None
            if pid:
                update_tasks.append(
                    db.clients.update_one({"id": segundo["id"]}, {"$set": {"process_ids": segundo["process_ids"]}})
                )
        if update_tasks:
            # Executar updates em batches para não saturar
            for batch in chunk(update_tasks, batch_size):
                await asyncio.gather(*batch, return_exceptions=True)
        print("   ✅ Ligações atualizadas")

        # ── Distribuição de estados (report) ──
        print("\n📊 Distribuição de processos por estado:")
        from collections import Counter
        status_counter = Counter(p["status"] for p in processos)
        for label, n, status_string, is_active, is_deleted in status_counts:
            real = status_counter.get(status_string, 0)
            extra = " (soft-deleted)" if is_deleted else ""
            print(f"   {label:18s} → {status_string:18s}: {real:3d}{extra}")

        # ── PASSO 6: Portal — Documentos ──
        all_docs = []
        if not skip_docs:
            print("\n📄 A gerar documentos do Portal (3-5 por processo: REQUESTED + UPLOADED)...")
            for processo in processos:
                if processo.get("is_deleted"):
                    continue  # não gerar docs para processos eliminados
                n_docs = random.randint(3, 5)
                n_requested = random.randint(1, 2)
                for _ in range(n_requested):
                    dt = random_past_datetime(45)
                    consultor = next((u for u in users["consultores"] if u["id"] == processo.get("assigned_consultor_id")), None)
                    all_docs.append(gerar_documento_requested(processo["id"], consultor, dt))
                for _ in range(n_docs - n_requested):
                    dt = random_past_datetime(30)
                    all_docs.append(gerar_documento_uploaded(processo["id"], processo.get("client_name", "Cliente"), dt))
            n_docs = await batch_insert(db, "documents", all_docs, batch_size)
            print(f"   ✅ {n_docs} documentos do Portal inseridos")

        # ── PASSO 7: Portal — Mensagens ──
        all_msgs = []
        if not skip_messages:
            print("\n💬 A gerar mensagens do Portal (2-4 por processo, conversa consultor <-> cliente)...")
            for processo in processos:
                if processo.get("is_deleted"):
                    continue
                conversa = random.choice(PORTAL_CONVERSATIONS)
                # 2-4 mensagens (primeiras da conversa)
                n_msgs = random.randint(2, 4)
                base_dt = random_past_datetime(30)
                consultor_name = processo.get("consultor_name") or "Consultor"
                client_name = processo.get("client_name", "Cliente")
                for j in range(min(n_msgs, len(conversa))):
                    sender_type, content = conversa[j]
                    sender_name = consultor_name if sender_type == "staff" else client_name
                    msg_dt = base_dt + timedelta(hours=j * random.randint(2, 12))
                    if msg_dt > datetime.now(timezone.utc):
                        msg_dt = datetime.now(timezone.utc)
                    all_msgs.append(gerar_mensagem_portal(processo["id"], sender_type, sender_name, content, msg_dt))
            n_msgs = await batch_insert(db, "portal_messages", all_msgs, batch_size)
            print(f"   ✅ {n_msgs} mensagens do Portal inseridas")

        # ── PASSO 8: Tarefas (5-10 por processo) ──
        all_tasks = []
        if not skip_tasks:
            print("\n✅ A gerar tarefas (5-10 por processo: completadas/pendentes/atrasadas)...")
            for processo in processos:
                if processo.get("is_deleted"):
                    continue
                n_tasks = random.randint(5, 10)
                # ~40% completadas, ~30% pendentes, ~30% atrasadas
                kinds = (
                    ["completed"] * round(n_tasks * 0.4)
                    + ["pending"] * round(n_tasks * 0.3)
                    + ["overdue"] * (n_tasks - round(n_tasks * 0.4) - round(n_tasks * 0.3))
                )
                random.shuffle(kinds)
                created_by = next(
                    (u for u in users["todos"] if u["id"] == processo.get("assigned_consultor_id")), None
                )
                if not created_by:
                    created_by = random.choice(users["todos"]) if users["todos"] else None
                for k in kinds:
                    dt = random_past_datetime(20)
                    all_tasks.append(gerar_tarefa(processo, users["todos"], created_by, k, dt))
            n_tasks = await batch_insert(db, "tasks", all_tasks, batch_size)
            print(f"   ✅ {n_tasks} tarefas inseridas")

        # ── PASSO 9: Histórico + Atividades (5 logs por processo, últimos 60 dias) ──
        all_history = []
        all_activities = []
        if not skip_history:
            print("\n📋 A gerar histórico/atividades (5 logs por processo, últimos 60 dias)...")
            for processo in processos:
                if processo.get("is_deleted"):
                    continue
                n_logs = random.randint(4, 6)
                templates = random.sample(HISTORY_ACTIONS, k=min(n_logs, len(HISTORY_ACTIONS)))
                user_for_logs = next(
                    (u for u in users["todos"] if u["id"] == processo.get("assigned_consultor_id")), None
                )
                if not user_for_logs:
                    user_for_logs = random.choice(users["todos"]) if users["todos"] else None
                # Datas crescentes (timeline coerente)
                base = random_past_datetime(60)
                for j, tmpl in enumerate(templates):
                    dt = base + timedelta(days=j * random.randint(2, 8))
                    if dt > datetime.now(timezone.utc):
                        dt = datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 48))
                    all_history.append(gerar_historico(processo["id"], user_for_logs, tmpl, dt))
                # 1-2 atividades/comentários
                n_acts = random.randint(1, 2)
                for _ in range(n_acts):
                    dt = random_past_datetime(45)
                    all_activities.append(
                        gerar_activity(processo["id"], user_for_logs, random.choice(ACTIVITY_COMMENTS), dt)
                    )
            n_hist = await batch_insert(db, "history", all_history, batch_size)
            n_acts = await batch_insert(db, "activities", all_activities, batch_size)
            print(f"   ✅ {n_hist} registos de histórico + {n_acts} atividades inseridos")

        # ── PASSO 10: Resumo final ──
        print("\n" + "=" * 70)
        print("📊 RESUMO FINAL")
        print("=" * 70)
        total_clientes = await db.clients.count_documents({"_seed_script": SEED_SCRIPT})
        total_processos = await db.processes.count_documents({"_seed_script": SEED_SCRIPT})
        total_docs = await db.documents.count_documents({"_seed_script": SEED_SCRIPT})
        total_msgs = await db.portal_messages.count_documents({"_seed_script": SEED_SCRIPT})
        total_tasks = await db.tasks.count_documents({"_seed_script": SEED_SCRIPT})
        total_hist = await db.history.count_documents({"_seed_script": SEED_SCRIPT})
        total_acts = await db.activities.count_documents({"_seed_script": SEED_SCRIPT})
        print(f"   👤 Clientes (total, inc. 2ºs titulares): {total_clientes}")
        print(f"   📁 Processos:                          {total_processos}")
        print(f"   📄 Documentos do Portal:               {total_docs}")
        print(f"   💬 Mensagens do Portal:                {total_msgs}")
        print(f"   ✅ Tarefas:                            {total_tasks}")
        print(f"   📋 Histórico (audit logs):             {total_hist}")
        print(f"   🔔 Atividades:                         {total_acts}")

        # Distribuição por status
        print("\n📈 Distribuição final por estado:")
        pipeline = [
            {"$match": {"_seed_script": SEED_SCRIPT}},
            {"$group": {"_id": {"status": "$status", "deleted": "$is_deleted"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        dist = await db.processes.aggregate(pipeline).to_list(20)
        for d in dist:
            status = d["_id"].get("status", "?")
            deleted = d["_id"].get("deleted", False)
            extra = " [eliminado]" if deleted else ""
            print(f"   {status}{extra}: {d['count']} processos")

        # Estatísticas de tarefas
        pipeline_tasks = [
            {"$match": {"_seed_script": SEED_SCRIPT}},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "completadas": {"$sum": {"$cond": [{"$eq": ["$completed", True]}, 1, 0]}},
                "atrasadas": {"$sum": {"$cond": [{"$eq": ["$is_overdue", True]}, 1, 0]}},
            }},
        ]
        stats = await db.tasks.aggregate(pipeline_tasks).to_list(1)
        if stats:
            s = stats[0]
            pendentes = s["total"] - s["completadas"] - s["atrasadas"]
            print(f"\n📊 Tarefas: {s['total']} total | {s['completadas']} completadas | "
                  f"{s['atrasadas']} atrasadas | {max(pendentes, 0)} pendentes")

        print("\n" + "=" * 70)
        print("💡 Para remover TODOS os dados deste script:")
        print("   python backend/scripts/seed_massive_dev_data.py --clear")
        print("=" * 70)

    finally:
        mongo_client.close()


# ==============================================================================
# CLI
# ==============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed Massivo de Mock Data — PowerCell (Pacote A)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Gera ~120 clientes + processos + 2ºs titulares + documentos/mensagens do Portal
+ tarefas + histórico, para testar o CRM e o Portal do Cliente ao limite em DEV.

Exemplos:
  python backend/scripts/seed_massive_dev_data.py
  python backend/scripts/seed_massive_dev_data.py --num-clients 120 --clear
  python backend/scripts/seed_massive_dev_data.py --no-ensure-statuses
        """,
    )
    parser.add_argument("--num-clients", type=int, default=NUM_CLIENTS_DEFAULT,
                        help=f"Nº de clientes principais (default {NUM_CLIENTS_DEFAULT})")
    parser.add_argument("--clear", action="store_true",
                        help="Remove dados anteriores deste script antes de criar novos")
    parser.add_argument("--no-ensure-statuses", action="store_true",
                        help="Não fazer upsert dos workflow_statuses")
    parser.add_argument("--company-id", default=None, help="Forçar company_id")
    parser.add_argument("--company-name", default=None, help="Forçar company_name")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT,
                        help=f"Tamanho do batch de insert (default {BATCH_SIZE_DEFAULT})")
    parser.add_argument("--skip-docs", action="store_true", help="Não gerar documentos do Portal")
    parser.add_argument("--skip-messages", action="store_true", help="Não gerar mensagens do Portal")
    parser.add_argument("--skip-tasks", action="store_true", help="Não gerar tarefas")
    parser.add_argument("--skip-history", action="store_true", help="Não gerar histórico/atividades")

    args = parser.parse_args()

    asyncio.run(seed_massive(
        num_clients=args.num_clients,
        clear=args.clear,
        ensure_statuses=not args.no_ensure_statuses,
        company_id_forced=args.company_id,
        company_name_forced=args.company_name,
        batch_size=args.batch_size,
        skip_docs=args.skip_docs,
        skip_messages=args.skip_messages,
        skip_tasks=args.skip_tasks,
        skip_history=args.skip_history,
    ))


if __name__ == "__main__":
    main()
