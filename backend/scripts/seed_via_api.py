#!/usr/bin/env python3
"""
Script para popular a BD de dev via API REST existente.
Não depende de acesso direto ao MongoDB - usa os endpoints do backend.
"""

import requests
import random
import string
import uuid
import json
import sys
from datetime import datetime, timezone, timedelta

# Config
BASE_URL = "https://powercell.onrender.com"
ADMIN_EMAIL = "geral@powerealestate.pt"
ADMIN_PASSWORD = "admin2026"

# Dados realistas
PROFISSOES = [
    "Engenheiro Informático", "Enfermeiro", "Professor", "Gestor de Conta",
    "Técnico de Vendas", "Motorista", "Engenheiro Civil", "Médico",
    "Advogado", "Contabilista", "Administrativo", "Comercial",
    "Técnico de Informática", "Arquiteto", "Designer", "Consultor",
]
TIPOS_CONTRATO = ["Efetivo", "Termo Certo", "Recibos Verdes", "Empresário"]
ESTADOS_CIVIS = ["Solteiro", "Casado", "Divorciado", "Viúvo"]
CIDADES = [
    "Lisboa", "Porto", "Braga", "Coimbra", "Faro", "Aveiro", "Setúbal",
    "Leiria", "Guimarães", "Cascais", "Sintra", "Vila Nova de Gaia",
]
FONTES = ["Manual", "Website", "Indicação", "Telefone", "Email"]
NOMES_M = [
    "João", "José", "António", "Manuel", "Francisco", "Paulo", "Pedro", "Luís",
    "Carlos", "Miguel", "Rui", "André", "Tiago", "Bruno", "Ricardo", "Daniel",
    "Nuno", "Hugo", "Diogo", "Rafael", "Vítor", "Marco", "Alexandre", "Sérgio",
]
NOMES_F = [
    "Maria", "Ana", "Catarina", "Sofia", "Inês", "Joana", "Mariana", "Laura",
    "Isabel", "Marta", "Patrícia", "Sara", "Rita", "Andreia", "Cláudia", "Teresa",
    "Helena", "Sandra", "Cristina", "Carla", "Fernanda", "Lúcia", "Eva", "Alice",
]
APELLIDOS = [
    "Silva", "Santos", "Oliveira", "Sousa", "Rodrigues", "Ferreira", "Pereira",
    "Costa", "Carvalho", "Martins", "Almeida", "Lopes", "Soares", "Fernandes",
    "Gonçalves", "Pinto", "Araújo", "Ribeiro", "Teixeira", "Moreira", "Correia",
    "Nunes", "Mendes", "Rocha", "Vieira", "Monteiro", "Morais", "Carneiro",
]
PROCESS_STATUSES = [
    "clientes_espera", "documentacao", "analise", "pre_aprovacao",
    "credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv",
    "minuta", "escritura", "concluido", "arquivo", "perdido",
    "desistencias", "fila_espera",
]
STATUS_WEIGHTS_NO_FILA = [15, 18, 14, 10, 8, 5, 4, 5, 4, 3, 5, 2, 2, 2]
TITULOS_TAREFAS = [
    "Recolher documentos do cliente", "Enviar documentação para o banco",
    "Agendar avaliação do imóvel", "Preparar minuta do contrato",
    "Contactar cliente para assinatura", "Verificar NIF do cliente",
    "Solicitar comprovativo de rendimentos", "Enviar CPCV para assinatura",
    "Confirmar dados bancários", "Agendar escritura no notário",
    "Atualizar dados do processo", "Enviar simulação ao cliente",
    "Pedir documentos complementares", "Submeter proposta ao banco",
]


def gerar_nif():
    """Gera NIF português válido (9 dígitos)."""
    primeiro = random.choice([1, 2, 3, 3, 3, 2, 1])
    digitos = [primeiro] + [random.randint(0, 9) for _ in range(7)]  # 8 digits
    soma = sum(digitos[i] * (9 - i) for i in range(8))
    resto = soma % 11
    digitos.append(0 if resto < 2 else 11 - resto)  # 9th check digit
    return ''.join(map(str, digitos))


def gerar_telefone():
    return f"{random.choice(['91','93','92','96'])}{''.join(random.choices(string.digits, k=7))}"


def gerar_nome():
    sexo = random.choice(["M", "F"])
    primeiro = random.choice(NOMES_M if sexo == "M" else NOMES_F)
    apps = random.sample(APELLIDOS, random.randint(2, 3))
    return f"{primeiro} {' '.join(apps)}"


def gerar_email(nome):
    from unicodedata import normalize
    nomes = nome.lower().split()
    fmt = random.choice([
        f"{nomes[0]}.{nomes[-1]}",
        f"{nomes[0]}{nomes[-1]}",
        f"{nomes[0]}.{nomes[-1]}{random.randint(1,99)}",
    ])
    dom = random.choice(["gmail.com", "hotmail.com", "outlook.pt", "sapo.pt"])
    fmt = normalize('NFKD', fmt).encode('ASCII', 'ignore').decode('ASCII')
    return f"{fmt}@{dom}"


def gerar_data_nasc():
    hoje = datetime.now()
    idade = random.randint(18, 70)
    return f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{hoje.year - idade}"


def login():
    """Login and return JWT token + user info."""
    resp = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    })
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.text}")
        sys.exit(1)
    data = resp.json()
    return data["access_token"], data["user"]


def get_users(token):
    """Get all users."""
    resp = requests.get(f"{BASE_URL}/api/admin/users",
                        headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        print(f"❌ Failed to get users: {resp.text}")
        return []
    return resp.json()


def create_client(token, user_id):
    """Create a client via API."""
    nome = gerar_nome()
    nif = gerar_nif()
    tel = gerar_telefone()
    email = gerar_email(nome)
    cidade = random.choice(CIDADES)
    estado_civil = random.choice(ESTADOS_CIVIS)
    profissao = random.choice(PROFISSOES)
    salario = round(random.uniform(850, 4500), 2)
    tipo_contrato = random.choice(TIPOS_CONTRATO)

    # ClientCreate schema: flat fields, not nested
    payload = {
        "nome": nome,
        "email": email,
        "telefone": tel,
        "nif": nif,
        "fonte": random.choice(FONTES),
        "estado_civil": estado_civil,
        "profissao": profissao,
        "morada_fiscal": f"Rua {random.choice(APELLIDOS)}, {random.randint(1,500)}, {random.randint(1000,9999)}-{random.randint(100,999)} {cidade}",
        "data_nascimento": gerar_data_nasc(),
    }

    resp = requests.post(f"{BASE_URL}/api/clients",
                         json=payload,
                         headers={"Authorization": f"Bearer {token}"})

    if resp.status_code in [200, 201]:
        return resp.json()
    else:
        print(f"   ⚠️  Erro ao criar cliente {nome}: {resp.status_code} - {resp.text[:100]}")
        return None


def create_process(token, client_id, client_name, consultores, indexadores, intermediarios, force_fila=False):
    """Create a process via API using /clients/{id}/create-process, then update status."""
    consultor = random.choice(consultores) if consultores else None
    indexador = random.choice(indexadores) if indexadores else None
    intermediario = random.choice(intermediarios) if intermediarios else None

    if force_fila:
        target_status = "fila_espera"
    else:
        choices = [s for s in PROCESS_STATUSES if s != "fila_espera"]
        target_status = random.choices(choices, weights=STATUS_WEIGHTS_NO_FILA, k=1)[0]

    process_type = random.choice(["credito_habitacao", "credito_pessoal", "compra_direta",
                                   "arrendamento", "consultoria", "refinanciamento"])

    # Step 1: Create process via client endpoint
    resp = requests.post(
        f"{BASE_URL}/api/clients/{client_id}/create-process",
        params={"process_type": process_type},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )

    if resp.status_code in [200, 201]:
        result = resp.json()
        process_id = result.get("process_id")

        # Step 2: Update status + assignments via PUT
        update_payload = {"status": target_status}
        if consultor:
            update_payload["assigned_consultor_id"] = consultor["id"]
        if indexador:
            update_payload["assigned_indexacao_id"] = indexador["id"]
        if intermediario:
            update_payload["assigned_mediador_id"] = intermediario["id"]

        if process_id and target_status != "clientes_espera":
            update_resp = requests.put(
                f"{BASE_URL}/api/processes/{process_id}",
                json=update_payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )

        result["status"] = target_status
        result["assigned_consultor_id"] = consultor["id"] if consultor else None
        return result
    else:
        print(f"   ⚠️  Erro ao criar processo para {client_name}: {resp.status_code} - {resp.text[:120]}")
        return None


def create_task(token, process_id, process_name, users, created_by_id):
    """Create a task via API."""
    assigned_to = random.sample([u["id"] for u in users], k=random.randint(1, min(2, len(users))))
    r = random.random()
    dias_offset = random.randint(-14, -1) if r < 0.4 else (0 if r < 0.6 else random.randint(1, 14))
    due_date = (datetime.now(timezone.utc) + timedelta(days=dias_offset)).strftime("%Y-%m-%d")

    payload = {
        "title": random.choice(TITULOS_TAREFAS),
        "description": f"Tarefa para o processo de {process_name}",
        "assigned_to": assigned_to,
        "process_id": process_id,
        "due_date": due_date,
    }

    resp = requests.post(f"{BASE_URL}/api/tasks",
                         json=payload,
                         headers={"Authorization": f"Bearer {token}"})

    if resp.status_code in [200, 201]:
        return resp.json()
    else:
        return None


def main():
    print("=" * 60)
    print("🎯 SEED VIA API REST - POWERCELL")
    print("=" * 60)

    # Login
    print("\n🔐 A fazer login...")
    token, admin_user = login()
    print(f"   ✅ Login OK: {admin_user['name']} ({admin_user['role']})")

    # Test auth works
    test_resp = requests.get(f"{BASE_URL}/api/admin/users?limit=1",
                             headers={"Authorization": f"Bearer {token}"})
    if test_resp.status_code != 200:
        print(f"   ❌ Auth test failed: {test_resp.status_code}")
        sys.exit(1)
    print("   ✅ Auth validada")

    # Get users
    print("\n👥 A carregar utilizadores...")
    users = get_users(token)
    consultores = [u for u in users if u["role"] == "consultor" and u.get("is_active", True)]
    indexadores = [u for u in users if u["role"] == "indexacao" and u.get("is_active", True)]
    intermediarios = [u for u in users if u["role"] == "intermediario" and u.get("is_active", True)]
    print(f"   ✅ {len(consultores)} consultores, {len(indexadores)} indexadores, {len(intermediarios)} intermediários")

    if not consultores:
        print("❌ Nenhum consultor encontrado!")
        sys.exit(1)

    # ── Criar 30 Clientes ──
    print(f"\n🔄 A criar 30 clientes...")

    # Check existing seed clients first
    existing_resp = requests.get(f"{BASE_URL}/api/clients",
                                  headers={"Authorization": f"Bearer {token}"},
                                  timeout=15)
    existing_clients = existing_resp.json() if existing_resp.status_code == 200 else []

    clientes = list(existing_clients) if len(existing_clients) >= 20 else []
    if len(clientes) >= 20:
        print(f"   ⏭️  Já existem {len(clientes)} clientes, a saltar criação")
    else:
        clientes = []
        for i in range(30):
            # Refresh token every 10 requests to avoid expiry
            if i > 0 and i % 10 == 0:
                print("   🔑 A renovar token...")
                token, admin_user = login()

            cliente = create_client(token, admin_user["id"])
            if cliente:
                clientes.append(cliente)
                print(f"   [{i+1}/30] ✅ {cliente.get('nome', 'N/A')}")
            else:
                print(f"   [{i+1}/30] ❌ Falhou")

    print(f"\n   ✅ {len(clientes)} clientes criados")

    if not clientes:
        print("❌ Nenhum cliente criado com sucesso!")
        sys.exit(1)

    # ── Criar ~20 Processos ──
    print(f"\n🔄 A criar ~20 processos (3 em FILA_ESPERA)...")
    processos = []
    selecionados = random.sample(clientes, k=min(20, len(clientes)))

    # Refresh token for process creation
    token, admin_user = login()

    for i, cliente in enumerate(selecionados):
        client_id = cliente.get("id") or cliente.get("_id", "")
        client_name = cliente.get("nome", "N/A")
        force_fila = i < 3

        processo = create_process(token, client_id, client_name,
                                  consultores, indexadores, intermediarios,
                                  force_fila=force_fila)
        if processo:
            processos.append(processo)
            status_mark = "🔄 FILA_ESPERA" if force_fila else "📋"
            print(f"   [{i+1}/20] {status_mark} {client_name} → {processo.get('status', 'N/A')}")
        else:
            print(f"   [{i+1}/20] ❌ Falhou para {client_name}")

    print(f"\n   ✅ {len(processos)} processos criados")
    fila_count = sum(1 for p in processos if p.get("status") == "fila_espera")
    print(f"   📊 {fila_count} em FILA_ESPERA")

    # ── Criar Tarefas ──
    print(f"\n🔄 A criar tarefas...")
    tasks_created = 0
    for processo in processos:
        process_id = processo.get("id") or processo.get("_id", "")
        process_name = processo.get("client_name", "N/A")

        for _ in range(random.randint(2, 3)):
            task = create_task(token, process_id, process_name, users, admin_user["id"])
            if task:
                tasks_created += 1

    print(f"   ✅ {tasks_created} tarefas criadas")

    # ── Resumo ──
    print("\n" + "=" * 60)
    print("📊 RESUMO FINAL")
    print("=" * 60)
    print(f"   👤 Clientes:    {len(clientes)}")
    print(f"   📁 Processos:   {len(processos)}")
    print(f"   ✅ Tarefas:     {tasks_created}")
    print(f"   🔄 Fila Espera: {fila_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
