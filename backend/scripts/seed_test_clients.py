#!/usr/bin/env python3
"""
Script para criar clientes de teste com dados realistas portugueses.

Uso:
    python scripts/seed_test_clients.py [--count 100] [--clear]

Opções:
    --count N    Número de clientes a criar (padrão: 100)
    --clear      Remove clientes de teste existentes antes de criar novos
    --help       Mostra esta ajuda
"""

import asyncio
import random
import string
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Adicionar o diretório backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv(Path(__file__).parent.parent / '.env')

# ==============================================================================
# DADOS REALISTAS PORTUGUESES
# ==============================================================================

NOMES_PROPRIOS_MASCULINOS = [
    "João", "José", "António", "Manuel", "Francisco", "Paulo", "Pedro", "Luís",
    "Carlos", "Miguel", "Rui", "André", "Tiago", "Bruno", "Ricardo", "Daniel",
    "Nuno", "Hugo", "Diogo", "Rafael", "Vítor", "Marco", "Alexandre", "Sérgio",
    "Fernando", "Jorge", "Gonçalo", "Filipe", "Rodrigo", "Eduardo", "Tomás",
    "Simão", "Samuel", "Davi", "Gabriel", "Mateus", "Martim", "Salvador", "Santiago",
    "Francisco", "Afonso", "Duarte", "Gustavo", "Dinis", "Bernardo", "Vasco"
]

NOMES_PROPRIOS_FEMININOS = [
    "Maria", "Ana", "Catarina", "Sofia", "Inês", "Joana", "Mariana", "Laura",
    "Isabel", "Marta", "Patrícia", "Sara", "Rita", "Andreia", "Cláudia", "Teresa",
    "Helena", "Sandra", "Cristina", "Carla", "Fernanda", "Lúcia", "Eva", "Alice",
    "Beatriz", "Leonor", "Matilde", "Mafalda", "Camila", "Bianca", "Carolina",
    "Gabriela", "Luísa", "Bárbara", "Vitória", "Verónica", "Diana", "Ema", "Érica",
    "Mélanie", "Juliana", "Raquel", "Daniela", "Nádia", "Soraia", "Tatiana"
]

APELLIDOS = [
    "Silva", "Santos", "Oliveira", "Sousa", "Rodrigues", "Ferreira", "Pereira",
    "Costa", "Carvalho", "Martins", "Almeida", "Lopes", "Soares", "Fernandes",
    "Gonçalves", "Pinto", "Araújo", "Ribeiro", "Teixeira", "Moreira", "Correia",
    "Nunes", "Mendes", "Rocha", "Vieira", "Monteiro", "Morais", "Carneiro",
    "Cunha", "Cruz", "Pinheiro", "Torres", "Fonseca", "Barbosa", "Cardoso",
    "Baptista", "Dias", "Tavares", "Freitas", "Reis", "Simões", "Matos",
    "Sá", "Borges", "Antunes", "Machado", "Vaz", "Ramos", "Branco", "Lima"
]

PROFISSOES = [
    "Engenheiro Civil", "Engenheiro Informático", "Médico", "Enfermeiro",
    "Professor", "Advogado", "Contabilista", "Gestor", "Administrativo",
    "Comercial", "Técnico de Informática", "Arquiteto", "Designer",
    "Consultor", "Analista de Sistemas", "Farmacêutico", "Dentista",
    "Fisioterapeuta", "Psicólogo", "Economista", "Bancário", "Segurador",
    "Empresário", "Comerciante", "Funcionário Público", "Motorista",
    "Eletricista", "Canalizador", "Carpinteiro", "Cozinheiro", "Vendedor",
    "Rececionista", "Secretário", "Técnico de Laboratório", "Investigador",
    "Jornalista", "Publicitário", "Recursos Humanos", "Turismo", "Tradutor"
]

EMPRESAS = [
    "EDP - Energias de Portugal", "Galp Energia", "Portugal Telecom",
    "Sonae", "Jerónimo Martins", "Grupo CB", "Banco Santander", "BNP Paribas",
    "CGD - Caixa Geral de Depósitos", "Millennium BCP", "Bankinter",
    "Fábrica Nacional de Cerveja", "Sumol + Compal", "Nestlé Portugal",
    "Siemens Portugal", "Nokia Portugal", "Continente", "Pingo Doce",
    "Lidl Portugal", "Aldi Portugal", "Mercadona", "Auchan", "IKEA Portugal",
    "FNAC Portugal", "Vodafone Portugal", "NOS", "NOWO Communications",
    "Deloitte Portugal", "Ernst & Young", "KPMG Portugal", "PwC Portugal",
    "BPI - Banco Português de Investimento", "Bascol - Automóveis", "Siva",
    "Delta Cafés", "Delta Cafés", "Nutrinveste", " Grupo Lena", "Teixeira Duarte",
    "Mota-Engil", "Cimpor", "Secil", "Portucel Soporcel", "Navigator Company",
    "Renault Portugal", "Volkswagen Portugal", "Toyota Caetano Portugal",
    "Hospital de Santa Maria", "Hospital de São José", "CHULN", "IPO Lisboa",
    "Universidade de Lisboa", "Universidade do Porto", "Universidade de Coimbra",
    "Ministério da Saúde", "Ministério da Educação", "TAP Air Portugal",
    "ANA - Aeroportos de Portugal", "Refer", "Comboios de Portugal", "Metro de Lisboa",
    "Metro do Porto", "Carris", "STCP", "EMEL", "Parque Escolar", "Águas de Portugal"
]

ESTADOS_CIVIS = ["Solteiro", "Casado", "Divorciado", "Viúvo", "União de Facto"]

TIPOS_CONTRATO = ["Trabalho Efetivo", "Termo Certo", "Termo Incerto", "Verde", "Recibos Verdes", "Função Pública"]

NACIONALIDADES = [
    "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa",
    "Brasileira", "Angolana", "Cabo-verdiana", "Moçambicana", "Ucraniana",
    "Espanhola", "Francesa", "Italiana", "Britânica", "Alemã"
]

CIDADES_E_MORADAS = [
    ("Lisboa", ["Av. da Liberdade", "Av. da República", "Rua Augusta", "Av. 5 de Outubro", 
                "Rua Castilho", "Av. Duque de Loulé", "Rua Barata Salgueiro", "Av. Fontes Pereira de Melo",
                "Rua do Salitre", "Av. Defensores de Chaves", "Rua D. João V", "Rua Saraiva de Carvalho"]),
    ("Porto", ["Av. da Boavista", "Rua de Santa Catarina", "Av. Fernão de Magalhães",
               "Rua de Cedofeita", "Av. dos Aliados", "Rua de Camões", "Rua de Sá da Bandeira",
               "Av. D. Afonso Henriques", "Rua do Bolhão", "Rua Formosa"]),
    ("Braga", ["Av. da Liberdade", "Rua do Souto", "Av. Central", "Rua D. Diogo de Sousa",
               "Av. General Carrilho da Silva", "Rua dos Biscainhos"]),
    ("Coimbra", ["Av. Emídio Navarro", "Rua Ferreira Borges", "Av. Sá da Bandeira",
                 "Rua da Sofia", "Av. Dias da Silva", "Rua Pedro Monteiro"]),
    ("Faro", ["Av. da República", "Rua de Santo António", "Av. 5 de Outubro",
              "Rua Miguel Bombarda", "Rua Infante D. Henrique"]),
    ("Aveiro", ["Av. Dr. Lourenço Peixinho", "Rua do Clube dos Galitos", "Av. 25 de Abril",
                "Rua dos Combatentes", "Rua João Mendonça"]),
    ("Viseu", ["Av. da Europa", "Rua Formosa", "Av. 5 de Outubro", "Rua D. Almeida Pessanha",
               "Av. da Bola"]),
    ("Setúbal", ["Av. Luísa Todi", "Rua do Comércio", "Av. 5 de Outubro",
                 "Rua D. Manuel I", "Av. José Mourinho Félix"]),
    ("Leiria", ["Av. Marquês de Pombal", "Rua Miguel Bombarda", "Av. 25 de Abril",
                "Rua da Graça", "Rua D. Afonso Henriques"]),
    ("Vila Nova de Gaia", ["Av. da República", "Rua de Manuel Pinto de Azevedo",
                           "Av. D. Afonso Henriques", "Rua Camilo Castelo Branco"]),
    ("Amadora", ["Av. Guerra Junqueiro", "Av. Santos Matos", "Rua Elias Garcia",
                 "Av. D. Amélia", "Rua Gama Barros"]),
    ("Guimarães", ["Av. Conde S. Bento", "Rua D. Maria II", "Av. 25 de Abril",
                   "Rua D. Afonso Henriques", "Rua Paio Galvão"]),
    ("Cascais", ["Av. Marginal", "Av. D. Carlos I", "Rua Frederico Arouca",
                 "Av. 25 de Abril", "Rua Almeida Garrett"]),
    ("Sintra", ["Av. Dr. Miguel Bombarda", "Rua Dr. Alfredo da Costa",
                "Av. D. Francisco Gomes", "Rua Consiglieri Pedroso"]),
    ("Matosinhos", ["Av. Dom Afonso Henriques", "Rua Roberto Ivens", 
                    "Av. Engenheiro Duarte Pacheco", "Rua Godinho de Faria"])
]

FONTES_CLIENTE = ["Manual", "Website", "Indicação", "Facebook", "Google", "Instagram", "Telefone", "Email", "Feira", "Outros"]

TAGS_POSSIVEIS = ["VIP", "Cliente Frequente", "Primeira Compra", "Investidor", "Crédito Habitação", 
                  "Crédito Pessoal", "Transferência Crédito", "Conta à Ordem", "Poupança"]


# ==============================================================================
# FUNÇÕES DE GERAÇÃO
# ==============================================================================

def gerar_nif_valido():
    """Gera um NIF português válido."""
    # Primeiro dígito: 1, 2, 3 (pessoa singular), 5 (pessoa coletiva), 6, 8, 9
    primeiro_digito = random.choice([1, 2, 3, 3, 3, 3, 2, 1, 3])  # Maioria pessoas singulares
    
    # Gerar 8 dígitos aleatórios
    digitos = [primeiro_digito] + [random.randint(0, 9) for _ in range(8)]
    
    # Calcular dígito de controlo
    soma = sum(digitos[i] * (9 - i) for i in range(8))
    resto = soma % 11
    digito_controlo = 0 if resto < 2 else 11 - resto
    
    digitos.append(digito_controlo)
    
    return ''.join(map(str, digitos))


def gerar_cc_valido():
    """Gera um número de Cartão de Cidadão (formato, não necessariamente válido)."""
    letras = ''.join(random.choices(string.ascii_uppercase, k=2))
    numeros = ''.join(random.choices(string.digits, k=7))
    digito = random.choice(string.digits + string.ascii_uppercase)
    return f"{letras}{numeros}{digito}"


def gerar_telefone_portugues():
    """Gera um número de telemóvel português válido."""
    prefixos = ["91", "92", "93", "96", "91", "92"]  # MEO, NOS, Vodafone, NOWO
    prefixo = random.choice(prefixos)
    resto = ''.join(random.choices(string.digits, k=7))
    return f"{prefixo}{resto}"


def gerar_telefone_fixo():
    """Gera um número de telefone fixo português."""
    indicativos = ["21", "22", "23", "24", "25", "26", "27", "28", "29"]  # Várias zonas
    indicativo = random.choice(indicativos)
    resto = ''.join(random.choices(string.digits, k=7))
    return f"{indicativo}{resto}"


def gerar_email(nome_completo):
    """Gera um email baseado no nome."""
    nomes = nome_completo.lower().split()
    
    # Vários formatos de email
    formatos = [
        f"{nomes[0]}.{nomes[-1]}",
        f"{nomes[0]}{nomes[-1]}",
        f"{nomes[0][0]}{nomes[-1]}",
        f"{nomes[0]}.{nomes[-1]}{random.randint(1, 99)}",
        f"{nomes[0]}_{nomes[-1]}",
        f"{nomes[0]}{random.randint(100, 999)}",
    ]
    
    dominios = ["gmail.com", "hotmail.com", "outlook.pt", "sapo.pt", "mail.pt", 
                "meo.pt", "live.com.pt", "yahoo.com"]
    
    formato = random.choice(formatos)
    dominio = random.choice(dominios)
    
    # Remover acentos
    from unicodedata import normalize
    formato = normalize('NFKD', formato).encode('ASCII', 'ignore').decode('ASCII')
    
    return f"{formato}@{dominio}"


def gerar_morada():
    """Gera uma morada realista."""
    cidade, ruas = random.choice(CIDADES_E_MORADAS)
    rua = random.choice(ruas)
    numero = random.randint(1, 500)
    andar = random.choice(["", f" {random.randint(1, 8)}º", f" {random.randint(1, 8)}ºEsq", f" {random.randint(1, 8)}ºDto"])
    
    codigo_postal = f"{random.randint(1000, 9999)}-{random.randint(100, 999)}"
    
    morada = f"{rua}, {numero}{andar}, {codigo_postal} {cidade}"
    
    return morada, cidade


def gerar_data_nascimento():
    """Gera uma data de nascimento realista (18-70 anos)."""
    hoje = datetime.now()
    idade_min, idade_max = 18, 70
    
    idade = random.randint(idade_min, idade_max)
    ano = hoje.year - idade
    
    # Dia e mês aleatórios
    mes = random.randint(1, 12)
    if mes in [1, 3, 5, 7, 8, 10, 12]:
        dia = random.randint(1, 31)
    elif mes == 2:
        dia = random.randint(1, 28)
    else:
        dia = random.randint(1, 30)
    
    return f"{dia:02d}/{mes:02d}/{ano}"


def gerar_rendimento():
    """Gera dados de rendimento realistas."""
    # Salários em Portugal (aproximadamente)
    salarios_base = [
        (850, 1000),    # Salário mínimo
        (1000, 1500),   # Baixo
        (1500, 2500),   # Médio
        (2500, 4000),   # Médio-alto
        (4000, 8000),   # Alto
        (8000, 15000),  # Muito alto
    ]
    
    # Pesos para cada faixa (mais comum: 1000-2500)
    pesos = [15, 30, 35, 15, 4, 1]
    
    faixa = random.choices(salarios_base, weights=pesos)[0]
    rendimento_mensal = round(random.uniform(*faixa), 2)
    
    # Rendimento bruto anual (14 meses em Portugal)
    rendimento_anual = round(rendimento_mensal * 14, 2)
    
    # Outros rendimentos (opcional)
    outros_rendimentos = None
    if random.random() < 0.3:  # 30% têm outros rendimentos
        outros_rendimentos = round(random.uniform(100, 2000), 2)
    
    # Despesas (aproximadamente 30-60% do rendimento)
    despesas_mensais = round(rendimento_mensal * random.uniform(0.3, 0.6), 2)
    
    return {
        "rendimento_mensal": rendimento_mensal,
        "rendimento_bruto": rendimento_mensal,
        "rendimento_anual": rendimento_anual,
        "outros_rendimentos": outros_rendimentos,
        "despesas_mensais": despesas_mensais
    }


def gerar_cliente():
    """Gera um cliente completo com dados realistas."""
    
    # Nome
    sexo = random.choice(["M", "F"])
    if sexo == "M":
        primeiro_nome = random.choice(NOMES_PROPRIOS_MASCULINOS)
    else:
        primeiro_nome = random.choice(NOMES_PROPRIOS_FEMININOS)
    
    apelidos = random.sample(APELLIDOS, random.randint(2, 3))
    nome_completo = f"{primeiro_nome} {' '.join(apelidos)}"
    
    # Contactos
    email = gerar_email(nome_completo)
    telefone = gerar_telefone_portugues()
    telefone_secundario = gerar_telefone_fixo() if random.random() < 0.3 else None
    email_secundario = None
    if random.random() < 0.2:
        email_secundario = gerar_email(nome_completo)
    
    # Dados pessoais
    nif = gerar_nif_valido()
    cc = gerar_cc_valido()
    data_nascimento = gerar_data_nascimento()
    morada, cidade = gerar_morada()
    nacionalidade = random.choice(NACIONALIDADES)
    naturalidade = cidade  # Natural da cidade da morada
    estado_civil = random.choice(ESTADOS_CIVIS)
    profissao = random.choice(PROFISSOES)
    
    # Nomes dos pais
    nome_pai = f"{random.choice(NOMES_PROPRIOS_MASCULINOS)} {' '.join(random.sample(APELLIDOS, 2))}"
    nome_mae = f"{random.choice(NOMES_PROPRIOS_FEMININOS)} {' '.join(random.sample(APELLIDOS, 2))}"
    
    # Dados financeiros
    rendimentos = gerar_rendimento()
    empresa = random.choice(EMPRESAS) if random.random() < 0.7 else None
    tipo_contrato = random.choice(TIPOS_CONTRATO)
    antiguidade = f"{random.randint(1, 30)} anos" if random.random() < 0.6 else f"{random.randint(1, 11)} meses"
    
    # Créditos ativos
    tem_creditos = random.random() < 0.4  # 40% têm créditos
    valor_creditos = round(random.uniform(5000, 150000), 2) if tem_creditos else None
    
    # Tags
    num_tags = random.randint(0, 3)
    tags = random.sample(TAGS_POSSIVEIS, num_tags)
    
    # Fonte
    fonte = random.choice(FONTES_CLIENTE)
    
    # Notas
    notas = None
    if random.random() < 0.2:
        notas_options = [
            "Cliente muito interessado em crédito habitação.",
            "Prefere contacto por email.",
            "Cliente referido por amigo.",
            "Já teve crédito habitação anterior.",
            "Primeira vez que compra imóvel.",
            "Interessado em apartamento T2.",
            "Busca moradia com terreno.",
            "Investidor com vários imóveis.",
        ]
        notas = random.choice(notas_options)
    
    # Criar estrutura do cliente
    cliente = {
        "id": f"test_client_{gerar_nif_valido()}",  # ID único
        "nome": nome_completo,
        "contacto": {
            "email": email,
            "email_secundario": email_secundario,
            "telefone": telefone,
            "telefone_secundario": telefone_secundario
        },
        "dados_pessoais": {
            "nif": nif,
            "documento_id": cc,
            "data_nascimento": data_nascimento,
            "naturalidade": naturalidade,
            "nacionalidade": nacionalidade,
            "morada_fiscal": morada,
            "estado_civil": estado_civil,
            "profissao": profissao,
            "nome_pai": nome_pai,
            "nome_mae": nome_mae
        },
        "dados_financeiros": {
            "rendimento_mensal": rendimentos["rendimento_mensal"],
            "rendimento_bruto": rendimentos["rendimento_bruto"],
            "rendimento_anual": rendimentos["rendimento_anual"],
            "outros_rendimentos": rendimentos["outros_rendimentos"],
            "despesas_mensais": rendimentos["despesas_mensais"],
            "tipo_contrato": tipo_contrato,
            "empresa": empresa,
            "antiguidade_emprego": antiguidade,
            "tem_creditos_activos": tem_creditos,
            "valor_creditos_activos": valor_creditos,
            "data_actualizacao": datetime.now(timezone.utc).isoformat()
        },
        "process_ids": [],
        "co_buyers": [],
        "co_applicants": [],
        "fonte": fonte,
        "tags": tags,
        "notas": notas,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "seed_script",
        "_test_data": True  # Marcar como dado de teste
    }
    
    return cliente


async def criar_clientes_teste(count: int = 100, clear: bool = False):
    """Cria clientes de teste na base de dados."""
    
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    
    if not mongo_url or not db_name:
        print("❌ Erro: MONGO_URL e DB_NAME devem estar definidos no .env")
        sys.exit(1)
    
    # Mostrar informação da base de dados
    print(f"\n📦 Base de Dados: {db_name}")
    print(f"🔗 Ligação: {mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url}")
    print(f"📋 Coleção: clients\n")
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    try:
        # Limpar dados de teste existentes se pedido
        if clear:
            result = await db.clients.delete_many({"_test_data": True})
            print(f"🗑️  Removidos {result.deleted_count} clientes de teste existentes")
        
        # Verificar quantos clientes já existem
        total_antes = await db.clients.count_documents({})
        
        # Gerar clientes
        print(f"\n🔄 A gerar {count} clientes de teste...")
        clientes = [gerar_cliente() for _ in range(count)]
        
        # Inserir na base de dados
        result = await db.clients.insert_many(clientes)
        
        # Estatísticas
        total_depois = await db.clients.count_documents({})
        
        print(f"\n✅ {len(result.inserted_ids)} clientes criados com sucesso!")
        print(f"📊 Total de clientes: {total_antes} → {total_depois}")
        
        # Mostrar alguns exemplos
        print("\n📝 Exemplos de clientes criados:")
        print("-" * 80)
        
        exemplos = await db.clients.find({"_test_data": True}).limit(3).to_list(3)
        for cliente in exemplos:
            print(f"\n👤 {cliente['nome']}")
            print(f"   📧 Email: {cliente['contacto']['email']}")
            print(f"   📱 Telefone: {cliente['contacto']['telefone']}")
            print(f"   🪪 NIF: {cliente['dados_pessoais']['nif']}")
            print(f"   💼 Profissão: {cliente['dados_pessoais']['profissao']}")
            print(f"   💰 Rendimento: {cliente['dados_financeiros']['rendimento_mensal']:.2f}€/mês")
            print(f"   📍 {cliente['dados_pessoais']['morada_fiscal']}")
        
        print("\n" + "-" * 80)
        print("💡 Para remover estes clientes, execute:")
        print("   python scripts/seed_test_clients.py --clear")
        
    finally:
        client.close()


def main():
    """Função principal."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Cria clientes de teste com dados realistas portugueses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python scripts/seed_test_clients.py              # Cria 100 clientes
  python scripts/seed_test_clients.py --count 50   # Cria 50 clientes
  python scripts/seed_test_clients.py --clear      # Remove clientes de teste existentes
        """
    )
    
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=100,
        help="Número de clientes a criar (padrão: 100)"
    )
    
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove clientes de teste existentes antes de criar novos"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 SEED DE CLIENTES DE TESTE - POWERCELL")
    print("=" * 60)
    
    asyncio.run(criar_clientes_teste(count=args.count, clear=args.clear))


if __name__ == "__main__":
    main()
