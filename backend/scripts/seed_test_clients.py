#!/usr/bin/env python3
"""
Script para criar clientes e processos de teste com dados realistas portugueses.

ESTRUTURA DE DADOS:
- Um cliente pode ter vários processos
- Um processo pode ter vários clientes (ex: dois titulares)
- Relação N:M (muitos-para-muitos)

Uso:
    python scripts/seed_test_clients.py [--count 100] [--clear]

Opções:
    --count N    Número de clientes a criar (padrão: 100)
    --clear      Remove dados de teste existentes antes de criar novos
    --help       Mostra esta ajuda
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
    "Afonso", "Duarte", "Gustavo", "Dinis", "Bernardo", "Vasco"
]

NOMES_PROPRIOS_FEMININOS = [
    "Maria", "Ana", "Catarina", "Sofia", "Inês", "Joana", "Mariana", "Laura",
    "Isabel", "Marta", "Patrícia", "Sara", "Rita", "Andreia", "Cláudia", "Teresa",
    "Helena", "Sandra", "Cristina", "Carla", "Fernanda", "Lúcia", "Eva", "Alice",
    "Beatriz", "Leonor", "Matilde", "Mafalda", "Camila", "Bianca", "Carolina",
    "Gabriela", "Luísa", "Bárbara", "Vitória", "Verónica", "Diana", "Érica"
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
    "Eletricista", "Canalizador", "Cozinheiro", "Vendedor",
    "Rececionista", "Secretário", "Jornalista", "Publicitário"
]

EMPRESAS = [
    "EDP - Energias de Portugal", "Galp Energia", "Sonae", "Jerónimo Martins",
    "Banco Santander", "BNP Paribas", "CGD - Caixa Geral de Depósitos", 
    "Millennium BCP", "Bankinter", "Continente", "Pingo Doce",
    "Lidl Portugal", "Aldi Portugal", "Mercadona", "Auchan", "IKEA Portugal",
    "Vodafone Portugal", "NOS", "Deloitte Portugal", "KPMG Portugal", 
    "BPI - Banco Português de Investimento", "Delta Cafés", 
    "Teixeira Duarte", "Mota-Engil", "Renault Portugal", 
    "Hospital de Santa Maria", "Hospital de São José", "IPO Lisboa",
    "Universidade de Lisboa", "Universidade do Porto", "TAP Air Portugal",
    "Ministério da Saúde", "Ministério da Educação", "Metro de Lisboa"
]

ESTADOS_CIVIS = ["Solteiro", "Casado", "Divorciado", "Viúvo", "União de Facto"]

TIPOS_CONTRATO = ["Trabalho Efetivo", "Termo Certo", "Termo Incerto", "Recibos Verdes", "Função Pública"]

NACIONALIDADES = [
    "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa", "Portuguesa",
    "Brasileira", "Angolana", "Cabo-verdiana", "Moçambicana", "Ucraniana",
    "Espanhola", "Francesa", "Italiana"
]

CIDADES_E_MORADAS = [
    ("Lisboa", ["Av. da Liberdade", "Av. da República", "Rua Augusta", "Av. 5 de Outubro", 
                "Rua Castilho", "Av. Duque de Loulé", "Rua Barata Salgueiro"]),
    ("Porto", ["Av. da Boavista", "Rua de Santa Catarina", "Av. Fernão de Magalhães",
               "Rua de Cedofeita", "Av. dos Aliados", "Rua de Camões"]),
    ("Braga", ["Av. da Liberdade", "Rua do Souto", "Av. Central", "Rua D. Diogo de Sousa"]),
    ("Coimbra", ["Av. Emídio Navarro", "Rua Ferreira Borges", "Av. Sá da Bandeira"]),
    ("Faro", ["Av. da República", "Rua de Santo António", "Av. 5 de Outubro"]),
    ("Aveiro", ["Av. Dr. Lourenço Peixinho", "Rua do Clube dos Galitos", "Av. 25 de Abril"]),
    ("Viseu", ["Av. da Europa", "Rua Formosa", "Av. 5 de Outubro"]),
    ("Setúbal", ["Av. Luísa Todi", "Rua do Comércio", "Av. 5 de Outubro"]),
    ("Leiria", ["Av. Marquês de Pombal", "Rua Miguel Bombarda", "Av. 25 de Abril"]),
    ("Guimarães", ["Av. Conde S. Bento", "Rua D. Maria II", "Av. 25 de Abril"]),
    ("Cascais", ["Av. Marginal", "Av. D. Carlos I", "Rua Frederico Arouca"]),
    ("Sintra", ["Av. Dr. Miguel Bombarda", "Rua Dr. Alfredo da Costa"]),
    ("Matosinhos", ["Av. Dom Afonso Henriques", "Rua Roberto Ivens"])
]

TIPOS_PROCESSO = ["credito", "imobiliaria", "ambos"]

FONTES = ["Manual", "Website", "Indicação", "Telefone", "Email", "Feira"]

# Status do workflow (ordem)
WORKFLOW_STATUS = [
    "clientes_espera",
    "fase_contacto",
    "fase_documental",
    "fase_analise",
    "fase_bancaria",
    "ch_aprovado",
    "fase_escritura",
    "escritura_agendada",
    "concluidos",
    "desistencias"
]


# ==============================================================================
# FUNÇÕES DE GERAÇÃO
# ==============================================================================

def gerar_nif_valido():
    """Gera um NIF português válido."""
    primeiro_digito = random.choice([1, 2, 3, 3, 3, 3, 2, 1, 3])
    digitos = [primeiro_digito] + [random.randint(0, 9) for _ in range(8)]
    soma = sum(digitos[i] * (9 - i) for i in range(8))
    resto = soma % 11
    digito_controlo = 0 if resto < 2 else 11 - resto
    digitos.append(digito_controlo)
    return ''.join(map(str, digitos))


def gerar_cc_valido():
    """Gera um número de Cartão de Cidadão."""
    letras = ''.join(random.choices(string.ascii_uppercase, k=2))
    numeros = ''.join(random.choices(string.digits, k=7))
    digito = random.choice(string.digits + string.ascii_uppercase)
    return f"{letras}{numeros}{digito}"


def gerar_telefone_portugues():
    """Gera um número de telemóvel português."""
    prefixos = ["91", "92", "93", "96", "91", "92"]
    prefixo = random.choice(prefixos)
    resto = ''.join(random.choices(string.digits, k=7))
    return f"{prefixo}{resto}"


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


def gerar_morada():
    """Gera uma morada realista."""
    cidade, ruas = random.choice(CIDADES_E_MORADAS)
    rua = random.choice(ruas)
    numero = random.randint(1, 500)
    codigo_postal = f"{random.randint(1000, 9999)}-{random.randint(100, 999)}"
    return f"{rua}, {numero}, {codigo_postal} {cidade}", cidade


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


def gerar_rendimento():
    """Gera dados de rendimento realistas."""
    salarios_base = [
        (850, 1000), (1000, 1500), (1500, 2500), (2500, 4000), (4000, 8000)
    ]
    pesos = [15, 30, 35, 15, 5]
    
    faixa = random.choices(salarios_base, weights=pesos)[0]
    rendimento_mensal = round(random.uniform(*faixa), 2)
    rendimento_anual = round(rendimento_mensal * 14, 2)
    
    outros_rendimentos = None
    if random.random() < 0.3:
        outros_rendimentos = round(random.uniform(100, 2000), 2)
    
    despesas_mensais = round(rendimento_mensal * random.uniform(0.3, 0.6), 2)
    
    return {
        "rendimento_mensal": rendimento_mensal,
        "rendimento_bruto": rendimento_mensal,
        "rendimento_anual": rendimento_anual,
        "outros_rendimentos": outros_rendimentos,
        "despesas_mensais": despesas_mensais
    }


def gerar_cliente(client_id: str):
    """Gera um cliente completo com dados realistas.
    
    Um cliente é uma entidade separada que pode ter múltiplos processos.
    """
    
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
    
    # Dados pessoais
    nif = gerar_nif_valido()
    cc = gerar_cc_valido()
    data_nascimento = gerar_data_nascimento()
    morada, cidade = gerar_morada()
    nacionalidade = random.choice(NACIONALIDADES)
    estado_civil = random.choice(ESTADOS_CIVIS)
    profissao = random.choice(PROFISSOES)
    
    nome_pai = f"{random.choice(NOMES_PROPRIOS_MASCULINOS)} {' '.join(random.sample(APELLIDOS, 2))}"
    nome_mae = f"{random.choice(NOMES_PROPRIOS_FEMININOS)} {' '.join(random.sample(APELLIDOS, 2))}"
    
    # Dados financeiros
    rendimentos = gerar_rendimento()
    empresa = random.choice(EMPRESAS) if random.random() < 0.7 else None
    tipo_contrato = random.choice(TIPOS_CONTRATO)
    antiguidade = f"{random.randint(1, 25)} anos" if random.random() < 0.6 else f"{random.randint(1, 11)} meses"
    
    # Dados de crédito (opcional)
    tem_creditos = random.random() < 0.4
    valor_creditos = round(random.uniform(5000, 100000), 2) if tem_creditos else None
    
    # Fonte
    fonte = random.choice(FONTES)
    
    cliente = {
        "id": client_id,
        "nome": nome_completo,
        "contacto": {
            "email": email,
            "telefone": telefone
        },
        "dados_pessoais": {
            "nif": nif,
            "documento_id": cc,
            "data_nascimento": data_nascimento,
            "naturalidade": cidade,
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
            "valor_creditos_activos": valor_creditos
        },
        "process_ids": [],  # Lista de processos associados
        "fonte": fonte,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "_test_data": True  # Marcar como dado de teste
    }
    
    return cliente


def gerar_processo(process_number: int, clientes: list, is_multi_titular: bool = False):
    """Gera um processo que pode ter um ou mais clientes (titulares).
    
    Um processo pode ter múltiplos clientes (ex: dois titulares num empréstimo).
    """
    
    # Se for multi-titular, usar 2 clientes, senão usar 1
    num_titulares = 2 if is_multi_titular else 1
    titulares = clientes[:num_titulares] if len(clientes) >= num_titulares else clientes
    
    # Cliente principal é o primeiro titular
    cliente_principal = titulares[0]
    
    # Status do processo (distribuição realista)
    status_weights = [15, 20, 15, 15, 10, 8, 5, 5, 5, 2]  # Mais clientes nas primeiras fases
    status = random.choices(WORKFLOW_STATUS, weights=status_weights)[0]
    
    # Tipo de processo
    process_type = random.choice(TIPOS_PROCESSO)
    
    # Dados imobiliários (opcional)
    ja_tem_imovel = random.random() < 0.3
    cidade = cliente_principal.get("dados_pessoais", {}).get("naturalidade", "Lisboa")
    valor_imovel = round(random.uniform(100000, 500000), 2) if ja_tem_imovel else None
    
    # Criar estrutura do processo
    processo = {
        "id": str(uuid.uuid4()),
        "process_number": process_number,
        
        # Suporte a múltiplos clientes (N:M)
        "client_ids": [c["id"] for c in titulares],  # Lista de IDs de clientes
        "client_id": cliente_principal["id"],  # Mantém compatibilidade com código existente
        
        # Dados do cliente principal (para compatibilidade)
        "client_name": cliente_principal["nome"],
        "client_email": cliente_principal["contacto"]["email"],
        "client_phone": cliente_principal["contacto"]["telefone"],
        "client_nif": cliente_principal["dados_pessoais"]["nif"],
        
        # Dados dos titulares adicionais
        "co_buyers": [],  # 2º Titular / Fiador
        "co_applicants": [],  # 2º Titular / Fiador
        
        "process_type": process_type,
        "status": status,
        "is_active": status not in ["desistencias", "concluidos"],
        
        # Dados pessoais do titular principal
        "personal_data": cliente_principal["dados_pessoais"].copy(),
        
        # Dados financeiros
        "financial_data": cliente_principal.get("dados_financeiros", {}).copy(),
        
        # Dados imobiliários
        "real_estate_data": {
            "ja_tem_imovel": ja_tem_imovel,
            "valor_imovel": valor_imovel,
            "localizacao": cidade if ja_tem_imovel else None
        } if ja_tem_imovel else None,
        
        "credit_data": None,
        "assigned_consultor_id": None,
        "assigned_mediador_id": None,
        "source": cliente_principal.get("fonte", "Manual"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "_test_data": True  # Marcar como dado de teste
    }
    
    # Adicionar segundo titular como co_buyer se aplicável
    if len(titulares) > 1:
        segundo_titular = titulares[1]
        processo["co_buyers"] = [{
            "name": segundo_titular["nome"],
            "email": segundo_titular["contacto"]["email"],
            "nif": segundo_titular["dados_pessoais"]["nif"],
            "phone": segundo_titular["contacto"]["telefone"],
            "relacao": "co-titular"
        }]
        # Adicionar dados do segundo titular ao processo
        processo["titular2_data"] = {
            "name": segundo_titular["nome"],
            "email": segundo_titular["contacto"]["email"],
            "nif": segundo_titular["dados_pessoais"]["nif"],
            "phone": segundo_titular["contacto"]["telefone"]
        }
    
    return processo


async def criar_dados_teste(count: int = 100, clear: bool = False):
    """Cria clientes e processos de teste na base de dados.
    
    Estrutura:
    - Clientes: entidades independentes
    - Processos: podem ter múltiplos clientes (titulares)
    - Relação N:M entre clientes e processos
    """
    
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    
    if not mongo_url or not db_name:
        print("❌ Erro: MONGO_URL e DB_NAME devem estar definidos no .env")
        sys.exit(1)
    
    # Mostrar informação da base de dados
    print(f"\n📦 Base de Dados: {db_name}")
    print(f"🔗 Ligação: {mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url}")
    print(f"📋 Coleções: clients (clientes), processes (processos)\n")
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    try:
        # Buscar o último process_number
        ultimo_processo = await db.processes.find_one(
            {"process_number": {"$exists": True}},
            sort=[("process_number", -1)]
        )
        ultimo_numero = ultimo_processo.get("process_number", 0) if ultimo_processo else 0
        print(f"📊 Último número de processo: {ultimo_numero}")
        
        # Limpar dados de teste existentes se pedido
        if clear:
            result_clients = await db.clients.delete_many({"_test_data": True})
            result_processes = await db.processes.delete_many({"_test_data": True})
            print(f"🗑️  Removidos {result_clients.deleted_count} clientes de teste")
            print(f"🗑️  Removidos {result_processes.deleted_count} processos de teste")
        
        # Verificar quantos registos já existem
        total_clientes_antes = await db.clients.count_documents({})
        total_processos_antes = await db.processes.count_documents({})
        
        # ============================================================
        # PASSO 1: Criar clientes
        # ============================================================
        print(f"\n🔄 A gerar {count} clientes de teste...")
        clientes = []
        for i in range(count):
            client_id = str(uuid.uuid4())
            clientes.append(gerar_cliente(client_id))
        
        # Inserir clientes
        result_clientes = await db.clients.insert_many(clientes)
        print(f"✅ {len(result_clientes.inserted_ids)} clientes criados!")
        
        # ============================================================
        # PASSO 2: Criar processos (alguns com múltiplos titulares)
        # ============================================================
        print(f"\n🔄 A gerar processos...")
        processos = []
        clientes_atualizados = []  # Para atualizar process_ids dos clientes
        
        # 70% dos processos com 1 titular, 30% com 2 titulares
        num_processos = count  # Um processo por cliente principal
        num_multi_titular = int(num_processos * 0.3)  # 30% com dois titulares
        
        # Embaralhar clientes para distribuir
        random.shuffle(clientes)
        
        for i in range(num_processos):
            process_number = ultimo_numero + i + 1
            
            # Determinar se este processo terá dois titulares
            is_multi_titular = i < num_multi_titular
            
            if is_multi_titular:
                # Usar dois clientes diferentes
                idx1 = i
                idx2 = (i + 1) % len(clientes)
                clientes_processo = [clientes[idx1], clientes[idx2]]
            else:
                # Apenas um titular
                clientes_processo = [clientes[i]]
            
            processo = gerar_processo(process_number, clientes_processo, is_multi_titular)
            processos.append(processo)
            
            # Actualizar lista de process_ids dos clientes
            for c in clientes_processo:
                c["process_ids"].append(processo["id"])
        
        # Inserir processos
        result_processos = await db.processes.insert_many(processos)
        print(f"✅ {len(result_processos.inserted_ids)} processos criados!")
        print(f"   📊 {num_multi_titular} processos com 2 titulares")
        print(f"   📊 {num_processos - num_multi_titular} processos com 1 titular")
        
        # ============================================================
        # PASSO 3: Actualizar process_ids nos clientes
        # ============================================================
        print(f"\n🔄 A atualizar referências cliente-processo...")
        update_ops = []
        for cliente in clientes:
            if cliente["process_ids"]:
                update_ops.append(
                    db.clients.update_one(
                        {"id": cliente["id"]},
                        {"$set": {"process_ids": cliente["process_ids"]}}
                    )
                )
        
        if update_ops:
            await asyncio.gather(*update_ops)
            print(f"✅ {len(update_ops)} clientes atualizados com process_ids")
        
        # ============================================================
        # ESTATÍSTICAS FINAIS
        # ============================================================
        total_clientes_depois = await db.clients.count_documents({})
        total_processos_depois = await db.processes.count_documents({})
        
        print(f"\n📊 Resumo:")
        print(f"   Clientes: {total_clientes_antes} → {total_clientes_depois}")
        print(f"   Processos: {total_processos_antes} → {total_processos_depois}")
        
        # Distribuição por status
        print("\n📈 Distribuição por fase:")
        pipeline = [
            {"$match": {"_test_data": True}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        distribuicao = await db.processes.aggregate(pipeline).to_list(20)
        for d in distribuicao:
            print(f"   {d['_id']}: {d['count']} processos")
        
        # Mostrar exemplos de processos com múltiplos titulares
        print("\n📝 Exemplos de processos criados:")
        print("-" * 80)
        
        # Exemplo com 1 titular (sem co_buyers ou co_buyers vazio)
        exemplo1 = await db.processes.find_one(
            {"_test_data": True, "$or": [{"co_buyers": {"$exists": False}}, {"co_buyers": {"$size": 0}}]},
            sort=[("created_at", -1)]
        )
        if exemplo1:
            print(f"\n👤 Processo com 1 titular:")
            print(f"   Nome: {exemplo1['client_name']} (Processo #{exemplo1.get('process_number', 'N/A')})")
            print(f"   📧 Email: {exemplo1['client_email']}")
            print(f"   🪪 NIF: {exemplo1.get('client_nif', 'N/A')}")
            print(f"   📍 Status: {exemplo1['status']}")
        
        # Exemplo com 2 titulares
        exemplo2 = await db.processes.find_one(
            {"_test_data": True, "co_buyers.0": {"$exists": True}},
            sort=[("created_at", -1)]
        )
        if exemplo2:
            print(f"\n👥 Processo com 2 titulares:")
            print(f"   Titular 1: {exemplo2['client_name']}")
            print(f"   📧 Email: {exemplo2['client_email']}")
            if exemplo2.get('co_buyers'):
                co_buyer = exemplo2['co_buyers'][0]
                print(f"   Titular 2: {co_buyer.get('name', 'N/A')}")
                print(f"   📧 Email: {co_buyer.get('email', 'N/A')}")
            print(f"   📍 Status: {exemplo2['status']}")
        
        print("\n" + "-" * 80)
        print("💡 Para remover estes dados, execute:")
        print("   python scripts/seed_test_clients.py --clear")
        
    finally:
        client.close()


def main():
    """Função principal."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Cria clientes e processos de teste com dados realistas portugueses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Estrutura de dados:
  - Um cliente pode ter vários processos
  - Um processo pode ter vários clientes (ex: dois titulares)
  - Relação N:M (muitos-para-muitos)

Exemplos:
  python scripts/seed_test_clients.py              # Cria 100 clientes e processos
  python scripts/seed_test_clients.py --count 50   # Cria 50 clientes e processos
  python scripts/seed_test_clients.py --clear      # Remove dados de teste existentes
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
        help="Remove dados de teste existentes antes de criar novos"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 SEED DE CLIENTES E PROCESSOS DE TESTE - POWERCELL")
    print("   (Relação N:M: cliente pode ter vários processos,")
    print("    processo pode ter vários clientes/titulares)")
    print("=" * 60)
    
    asyncio.run(criar_dados_teste(count=args.count, clear=args.clear))


if __name__ == "__main__":
    main()
