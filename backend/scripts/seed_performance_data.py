#!/usr/bin/env python3
"""
====================================================================
SEED DE MOCK DATA DE DESEMPENHO — POWERCELL
====================================================================
Script para gerar histórico de trabalho simulado que alimenta os
Dashboards de "Desempenho da Equipa".

FUNCIONAMENTO:
1. Procura utilizadores ativos com roles: consultor, intermediario,
   indexacao (e respetiva company_id).
2. Para cada utilizador, escolhe 5-10 processos aleatórios da empresa
   e cria 15-30 tarefas com distribuição de status realista:
     - ~70% concluídas (completed=True) com completed_at nos últimos 30 dias
     - ~15% pendentes com due_date nos próximos dias
     - ~15% ATRASADAS: status pendente/em_andamento com due_date no passado
3. Simula tempos de transição recuando created_at dos processos e
   injetando registos na coleção history (processos movidos).
4. Insere registos na coleção activities para simular interacções.

Uso:
    python scripts/seed_performance_data.py [--dry-run] [--company-id=XXX]

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
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Adicionar o directório backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Carregar .env do directório backend
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)


# ==============================================================================
# DADOS REALISTAS PARA TAREFAS
# ==============================================================================

TITULOS_TAREFAS_CONSULTOR = [
    "Recolher documentos do cliente",
    "Enviar documentação para o banco",
    "Agendar avaliação do imóvel",
    "Contactar cliente para assinatura",
    "Verificar validade do CC e NIF",
    "Solicitar comprovativo de rendimentos",
    "Enviar CPCV para assinatura",
    "Confirmar dados bancários para transferência",
    "Atualizar dados do processo no sistema",
    "Enviar simulação de crédito ao cliente",
    "Pedir documentos complementares",
    "Submeter proposta ao banco",
    "Confirmar data da vistoria do imóvel",
    "Rever cláusulas contratuais",
    "Contactar seguradora para cotação",
    "Enviar email de acompanhamento",
    "Verificar aprovação de crédito",
    "Preparar dossier completo do cliente",
    "Agendar reunião com o cliente",
    "Solicitar declaração de IRS",
]

TITULOS_TAREFAS_INTERMEDIARIO = [
    "Preparar minuta do contrato",
    "Agendar escritura no notário",
    "Ligar para o mediador imobiliário",
    "Enviar proposta ao proprietário",
    "Verificar certidão permanente do imóvel",
    "Agendar visita ao imóvel",
    "Negociar condições de compra",
    "Confirmar dados do vendedor",
    "Solicitar planta do imóvel",
    "Verificar licença de utilização",
    "Contactar administradora do condomínio",
    "Enviar email com detalhes da visita",
    "Verificar certificado energético",
    "Preparar documentação para escritura",
    "Confirmar valor de reserva",
    "Agendar levantamento topográfico",
    "Verificar registo predial",
    "Contactar banco para avaliação",
    "Preparar caderno de encargos",
    "Enviar planta de localização",
]

TITULOS_TAREFAS_INDEXACAO = [
    "Indexar documentos do processo",
    "Classificar documento — CC frente",
    "Classificar documento — CC verso",
    "Classificar documento — Comprovativo IBAN",
    "Classificar documento — Declaração IRS",
    "Verificar indexação de processos pendentes",
    "Rever classificação de documentos",
    "Indexar documentos — Extrato bancário",
    "Classificar documento — Mapa de responsabilidade",
    "Indexar documentos do co-titular",
    "Verificar documentos em falta no processo",
    "Classificar documento — Certidão permanente",
    "Indexar novos documentos carregados",
    "Rever tags de documentos",
    "Classificar documento — Caderneta predial",
    "Indexar documento — Avaliação do imóvel",
    "Classificar documento — Apólice seguro vida",
    "Verificar integridade da indexação",
    "Indexar documento — CPCV assinado",
    "Classificar documento — Declaração rendimentos",
]

DESCRICOES_TAREFAS = [
    "Verificar prazos e garantir que todos os documentos estão em ordem.",
    "Contacto urgente — cliente solicitou actualização.",
    "Concluir até ao final do dia útil de hoje.",
    "Prioridade alta — processo em fase avançada.",
    "Confirmar com o gestor antes de prosseguir.",
    "Ligação já tentada 2x — insistir.",
    "Enviar email de confirmação após conclusão.",
    "Arquivar documentação após validação.",
    "Marcar como concluído após validação do banco.",
    "Seguir template standard do processo.",
    None,  # Sem descrição para algumas tarefas
    None,
    None,
]

# Status de processo para simular transições (ordem aproximada do pipeline)
PIPELINE_STATUSES = [
    "clientes_espera", "fase_documental", "fase_documental_ii",
    "enviado_bruno", "enviado_luis", "enviado_bcp_rui",
    "entradas_precision", "fase_bancaria", "fase_visitas",
    "ch_aprovado", "fase_escritura", "escritura_agendada",
    "concluidos", "fila_espera", "desistencias",
]

# Comentários típicos em actividades
COMENTARIOS_ACTIVIDADES = [
    "Cliente contactado para agendar entrega de documentos.",
    "Documentação enviada para análise bancária.",
    "Proposta submetida ao banco — aguardando resposta.",
    "Avaliação do imóvel agendada para a próxima semana.",
    "Cliente confirmou interesse em prosseguir.",
    "Spread negociado com o banco — condições favoráveis.",
    "Documentação complementar solicitada ao cliente.",
    "Reunião com cliente realizada — dúvidas esclarecidas.",
    "Simulação de crédito atualizada e enviada ao cliente.",
    "CPCV enviado para assinatura — prazo de 15 dias.",
    "Banco solicitou documentos adicionais para aprovação.",
    "Aprovação de crédito recebida — conditions standard.",
    "Cliente pediu reconsideração das condições propostas.",
    "Vistoria do imóvel concluída — sem problemas reportados.",
    "Escritura agendada com o notário.",
    "Seguro vida submetido — aguardando validação.",
    "Comprovativo de IBAN recebido e validado.",
    "Declaração de IRS validada — tudo em ordem.",
    "Processo transferido para fase seguinte.",
    "Contacto com mediador imobiliário — imóvel disponível.",
]


# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def agora_utc():
    """Retorna datetime UTC actual."""
    return datetime.now(timezone.utc)


def dias_atras(n):
    """Retorna datetime UTC de N dias atrás."""
    return agora_utc() - timedelta(days=n)


def dias_a_frente(n):
    """Retorna datetime UTC de N dias no futuro."""
    return agora_utc() + timedelta(days=n)


def iso_str(dt):
    """Converte datetime para string ISO format."""
    return dt.isoformat()


def escolher_titulo_tarefa(role):
    """Escolhe título de tarefa adequado ao role do utilizador."""
    if role == "consultor":
        return random.choice(TITULOS_TAREFAS_CONSULTOR)
    elif role in ("intermediario", "mediador"):
        return random.choice(TITULOS_TAREFAS_INTERMEDIARIO)
    elif role == "indexacao":
        return random.choice(TITULOS_TAREFAS_INDEXACAO)
    else:
        return random.choice(TITULOS_TAREFAS_CONSULTOR)


def gerar_tarefa(user_id, user_name, role, process_id, process_name, task_index):
    """
    Gera uma tarefa para o utilizador com distribuição de status:
    - ~70% concluídas (completed=True) com completed_at nos últimos 30 dias
    - ~15% pendentes com due_date nos próximos dias
    - ~15% ATRASADAS: completed=False com due_date no passado
    """
    task_id = str(uuid.uuid4())
    title = escolher_titulo_tarefa(role)
    # Adicionar nome do processo ao título se disponível
    if process_name and process_name not in title:
        title = f"[{process_name}] {title}"

    description = random.choice(DESCRICOES_TAREFAS)
    created_at = dias_atras(random.randint(5, 35))
    updated_at = created_at + timedelta(hours=random.randint(1, 72))

    # ── Distribuição de status ──
    r = random.random()

    if r < 0.70:
        # 70% — CONCLUÍDA
        completed = True
        completed_at = created_at + timedelta(days=random.randint(1, 10))
        completed_by = user_id
        due_date = iso_str(created_at + timedelta(days=random.randint(3, 14)))
        is_overdue = False
        days_until_due = None
    elif r < 0.85:
        # 15% — PENDENTE (futura)
        completed = False
        completed_at = None
        completed_by = None
        due_date = iso_str(dias_a_frente(random.randint(1, 7)))
        is_overdue = False
        days_until_due = random.randint(1, 7)
    else:
        # 15% — ATRASADA (due_date no passado, não concluída)
        completed = False
        completed_at = None
        completed_by = None
        dias_atraso = random.choice([3, 5, 7, 10, 14])
        due_date = iso_str(dias_atras(dias_atraso))
        is_overdue = True
        days_until_due = -dias_atraso

    tarefa = {
        "id": task_id,
        "title": title,
        "description": description,
        "assigned_to": [user_id],
        "assigned_to_names": [user_name],
        "process_id": process_id,
        "process_name": process_name or "",
        "created_by": user_id,
        "created_by_name": user_name,
        "completed": completed,
        "completed_at": iso_str(completed_at) if completed_at else None,
        "completed_by": completed_by,
        "due_date": due_date,
        "is_overdue": is_overdue,
        "days_until_due": days_until_due,
        "created_at": iso_str(created_at),
        "updated_at": iso_str(updated_at),
        "_seed_data": True,
        "_seed_script": "seed_performance_data",
    }
    return tarefa


def gerar_historico_transicao(process_id, user_id, user_name, role,
                               status_origem, status_destino, data_transicao):
    """Gera um registo de history para simular a transição de status."""
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user_id,
        "user_name": user_name,
        "action": "Moveu processo",
        "field": "status",
        "old_value": status_origem,
        "new_value": status_destino,
        "created_at": iso_str(data_transicao),
        "_seed_data": True,
        "_seed_script": "seed_performance_data",
    }


def gerar_actividade(process_id, user_id, user_name, role, data):
    """Gera uma actividade/comentário no processo."""
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user_id,
        "user_name": user_name,
        "user_role": role,
        "comment": random.choice(COMENTARIOS_ACTIVIDADES),
        "created_at": iso_str(data),
        "_seed_data": True,
        "_seed_script": "seed_performance_data",
    }


def calcular_transicoes_simuladas(status_actual, created_at_original, user_id, user_name, role, process_id):
    """
    Simula transições de status para o processo, recuando o created_at
    e gerando registos de history.

    Retorna:
        - lista de registos de history
        - novo created_at (recuado)
        - transitioned_at (data da última transição)
    """
    history_entries = []

    # Tentar encontrar a posição do status actual no pipeline
    try:
        status_idx = PIPELINE_STATUSES.index(status_actual)
    except ValueError:
        # Status personalizado — simular 2-3 transições genéricas
        status_idx = random.randint(2, 6)

    # Recuar o created_at proporcionalmente à fase
    dias_criacao_original = max(5, status_idx * 8 + random.randint(5, 15))
    novo_created_at = dias_atras(dias_criacao_original)

    # Gerar transições intermediárias (não todas, apenas as mais significativas)
    n_transicoes = min(status_idx, random.randint(2, 5))
    step_dias = dias_criacao_original / max(n_transicoes + 1, 1)

    for i in range(n_transicoes):
        origem_idx = max(0, status_idx - n_transicoes + i)
        destino_idx = origem_idx + 1

        # Não ultrapassar o status actual
        if destino_idx > status_idx:
            break

        status_origem = PIPELINE_STATUSES[origem_idx]
        status_destino = PIPELINE_STATUSES[destino_idx]

        # Data da transição: distribuída entre created_at e now
        data_transicao = dias_atras(dias_criacao_original - int(step_dias * (i + 1)))

        history_entries.append(
            gerar_historico_transicao(
                process_id, user_id, user_name, role,
                status_origem, status_destino, data_transicao
            )
        )

    # Última transição (para o status actual, se não já coberta)
    if n_transicoes > 0:
        ultimo_destino = PIPELINE_STATUSES[min(status_idx - n_transicoes + n_transicoes, status_idx)]
        if ultimo_destino != status_actual and status_actual in PIPELINE_STATUSES:
            data_ultima = dias_atras(random.randint(3, 10))
            history_entries.append(
                gerar_historico_transicao(
                    process_id, user_id, user_name, role,
                    ultimo_destino, status_actual, data_ultima
                )
            )
            transitioned_at = data_ultima
        else:
            transitioned_at = dias_atras(random.randint(3, 10))
    else:
        transitioned_at = dias_atras(random.randint(3, 10))

    return history_entries, novo_created_at, transitioned_at


# ==============================================================================
# FUNÇÃO PRINCIPAL
# ==============================================================================

async def seed_performance_data(dry_run: bool = False, company_id: str = None):
    """
    Gera histórico de trabalho simulado para alimentar os Dashboards
    de Desempenho da Equipa.
    """

    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')

    if not mongo_url or not db_name:
        print("❌ Erro: MONGO_URL e DB_NAME devem estar definidos no .env")
        sys.exit(1)

    safe_url = mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url
    print(f"\n{'=' * 60}")
    print(f"🚀 SEED PERFORMANCE DATA — POWERCELL")
    print(f"   Gerar histórico de trabalho simulado")
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
        # PASSO 0: LIMPAR DADOS ANTERIORES DESTE SCRIPT
        # ==================================================================
        if not dry_run:
            print("=" * 60)
            print("🗑️  PASSO 0: Limpar dados anteriores deste seed")
            print("=" * 60)

            seed_filter = {"_seed_script": "seed_performance_data"}
            for col in ["tasks", "history", "activities"]:
                result = await database[col].delete_many(seed_filter)
                if result.deleted_count:
                    print(f"   ✓ {col}: {result.deleted_count} registos removidos")
            print()

        # ==================================================================
        # PASSO 1: PROCURAR UTILIZADORES DA EQUIPA
        # ==================================================================
        print("=" * 60)
        print("👥 PASSO 1: Procurar Utilizadores da Equipa")
        print("=" * 60)

        # Procurar users com os roles desejados
        target_roles = ["consultor", "intermediario", "mediador", "indexacao"]

        # Opção A: Usar user_company_roles (sistema multi-tenant)
        ucr_filter = {"role": {"$in": target_roles}}
        if company_id:
            ucr_filter["company_id"] = company_id

        ucr_cursor = database.user_company_roles.find(
            ucr_filter, {"_id": 0, "user_id": 1, "role": 1, "company_id": 1, "company_name": 1}
        )
        user_roles = await ucr_cursor.to_list(500)

        # Agrupar por user_id para obter nome e dados
        user_ids = list(set(ucr["user_id"] for ucr in user_roles))

        # Buscar dados dos utilizadores
        users_cursor = database.users.find(
            {"id": {"$in": user_ids}, "is_active": {"$ne": False}},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "company_id": 1}
        )
        users_data = await users_cursor.to_list(500)
        users_map = {u["id"]: u for u in users_data}

        # Montar lista de equipa com role e company_id do UCR
        equipa = []
        for ucr in user_roles:
            uid = ucr["user_id"]
            if uid in users_map:
                user = users_map[uid]
                equipa.append({
                    "id": uid,
                    "name": user.get("name", user.get("email", "Desconhecido")),
                    "email": user.get("email", ""),
                    "role": ucr["role"],  # Role nesta empresa específica
                    "company_id": ucr.get("company_id", user.get("company_id")),
                    "company_name": ucr.get("company_name", ""),
                })

        # Opção B: Fallback — se não há UCR, usar users directamente
        if not equipa:
            print("   ⚠️  Sem registos em user_company_roles — a usar users directamente...")
            fallback_filter = {
                "role": {"$in": target_roles},
                "is_active": {"$ne": False},
            }
            if company_id:
                fallback_filter["$or"] = [
                    {"company_id": company_id},
                    {"company_id": {"$exists": False}},
                ]

            users_cursor = database.users.find(
                fallback_filter,
                {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "company_id": 1}
            )
            fallback_users = await users_cursor.to_list(500)
            equipa = [
                {
                    "id": u["id"],
                    "name": u.get("name", u.get("email", "Desconhecido")),
                    "email": u.get("email", ""),
                    "role": u["role"],
                    "company_id": u.get("company_id"),
                    "company_name": "",
                }
                for u in fallback_users
            ]

        if not equipa:
            print("   ❌ Nenhum utilizador encontrado com os roles pretendidos!")
            return

        # Agrupar por role para display
        by_role = {}
        for m in equipa:
            by_role.setdefault(m["role"], []).append(m)

        for role, members in by_role.items():
            print(f"   {role.capitalize()}: {len(members)} utilizadores")
            for m in members:
                print(f"      • {m['name']} ({m['email']}) — empresa: {m.get('company_name') or m.get('company_id') or 'N/A'}")
        print()

        # ==================================================================
        # PASSO 2: GERAR TAREFAS POR UTILIZADOR
        # ==================================================================
        print("=" * 60)
        print("📋 PASSO 2: Gerar Tarefas por Utilizador")
        print("=" * 60)

        todas_tarefas = []
        total_tarefas_concluidas = 0
        total_tarefas_pendentes = 0
        total_tarefas_atrasadas = 0

        for membro in equipa:
            user_id = membro["id"]
            user_name = membro["name"]
            role = membro["role"]
            comp_id = membro.get("company_id")

            # Procurar processos da empresa deste utilizador
            process_filter = {"is_deleted": {"$ne": True}}
            if comp_id:
                process_filter["$or"] = [
                    {"company_id": comp_id},
                    {"company_id": {"$exists": False}},
                ]

            # Filtrar processos onde o utilizador está atribuído
            role_assignment = []
            if role == "consultor":
                role_assignment = [
                    {"assigned_consultor_id": user_id},
                    {"assigned_consultor_ids": user_id},
                ]
            elif role in ("intermediario", "mediador"):
                role_assignment = [
                    {"assigned_mediador_id": user_id},
                    {"assigned_mediador_ids": user_id},
                ]
            elif role == "indexacao":
                role_assignment = [
                    {"assigned_indexacao_id": user_id},
                ]

            if role_assignment:
                # Se temos filtro de empresa + filtro de atribuição, combinamos com $and
                if comp_id:
                    process_filter = {
                        "$and": [
                            {"is_deleted": {"$ne": True}},
                            {"$or": [
                                {"company_id": comp_id},
                                {"company_id": {"$exists": False}},
                            ]},
                            {"$or": role_assignment},
                        ]
                    }
                else:
                    process_filter = {
                        "is_deleted": {"$ne": True},
                        "$or": role_assignment,
                    }

            processos = await database.processes.find(
                process_filter,
                {"_id": 0, "id": 1, "client_name": 1, "status": 1,
                 "process_number": 1, "created_at": 1}
            ).to_list(200)

            if not processos:
                # Fallback: usar processos da empresa sem filtro de atribuição
                fallback_filter = {"is_deleted": {"$ne": True}}
                if comp_id:
                    fallback_filter["$or"] = [
                        {"company_id": comp_id},
                        {"company_id": {"$exists": False}},
                    ]
                processos = await database.processes.find(
                    fallback_filter,
                    {"_id": 0, "id": 1, "client_name": 1, "status": 1,
                     "process_number": 1, "created_at": 1}
                ).to_list(200)

            if not processos:
                print(f"   ⚠️  {user_name} ({role}): sem processos disponíveis — saltado")
                continue

            # Escolher 5-10 processos aleatórios
            n_processos = min(random.randint(5, 10), len(processos))
            processos_escolhidos = random.sample(processos, n_processos)

            # Gerar 15-30 tarefas para este utilizador
            n_tarefas = random.randint(15, 30)

            for i in range(n_tarefas):
                # Associar a um processo aleatório dos escolhidos
                proc = random.choice(processos_escolhidos)
                tarefa = gerar_tarefa(
                    user_id, user_name, role,
                    proc["id"], proc.get("client_name", ""),
                    i
                )
                todas_tarefas.append(tarefa)

                if tarefa["completed"]:
                    total_tarefas_concluidas += 1
                elif tarefa["is_overdue"]:
                    total_tarefas_atrasadas += 1
                else:
                    total_tarefas_pendentes += 1

            print(f"   ✅ Geradas {n_tarefas} tarefas para {role.capitalize()} "
                  f"{user_name} (em {n_processos} processos)")

        print(f"\n   📊 Total de tarefas geradas: {len(todas_tarefas)}")
        if todas_tarefas:
            print(f"      ✅ Concluídas: {total_tarefas_concluidas} "
                  f"({round(total_tarefas_concluidas / len(todas_tarefas) * 100)}%)")
            print(f"      ⏳ Pendentes: {total_tarefas_pendentes} "
                  f"({round(total_tarefas_pendentes / len(todas_tarefas) * 100)}%)")
            print(f"      🔴 Atrasadas: {total_tarefas_atrasadas} "
                  f"({round(total_tarefas_atrasadas / len(todas_tarefas) * 100)}%)")
        print()

        # ==================================================================
        # PASSO 3: SIMULAR TRANSIÇÕES DE PROCESSO E TEMPOS
        # ==================================================================
        print("=" * 60)
        print("🔄 PASSO 3: Simular Transições de Processo (Histórico)")
        print("=" * 60)

        todo_historico = []
        todo_actividades = []
        processos_actualizados = 0

        # Para cada membro da equipa, escolher processos e simular transições
        for membro in equipa:
            user_id = membro["id"]
            user_name = membro["name"]
            role = membro["role"]
            comp_id = membro.get("company_id")

            # Buscar processos onde o utilizador está atribuído (mesma lógica do passo 2)
            role_assignment = []
            if role == "consultor":
                role_assignment = [
                    {"assigned_consultor_id": user_id},
                    {"assigned_consultor_ids": user_id},
                ]
            elif role in ("intermediario", "mediador"):
                role_assignment = [
                    {"assigned_mediador_id": user_id},
                    {"assigned_mediador_ids": user_id},
                ]
            elif role == "indexacao":
                role_assignment = [
                    {"assigned_indexacao_id": user_id},
                ]

            if role_assignment:
                if comp_id:
                    process_filter = {
                        "$and": [
                            {"is_deleted": {"$ne": True}},
                            {"$or": [
                                {"company_id": comp_id},
                                {"company_id": {"$exists": False}},
                            ]},
                            {"$or": role_assignment},
                        ]
                    }
                else:
                    process_filter = {
                        "is_deleted": {"$ne": True},
                        "$or": role_assignment,
                    }
            else:
                process_filter = {"is_deleted": {"$ne": True}}

            processos = await database.processes.find(
                process_filter,
                {"_id": 0, "id": 1, "client_name": 1, "status": 1,
                 "process_number": 1, "created_at": 1, "updated_at": 1}
            ).to_list(200)

            if not processos:
                continue

            # Escolher subconjunto para simular transições (3-7 por utilizador)
            n_proc_simular = min(random.randint(3, 7), len(processos))
            processos_simular = random.sample(processos, n_proc_simular)

            membro_history_count = 0

            for proc in processos_simular:
                proc_id = proc["id"]
                proc_name = proc.get("client_name", "Sem nome")
                status_actual = proc.get("status", "clientes_espera")

                # Calcular transições simuladas
                history_entries, novo_created_at, transitioned_at = calcular_transicoes_simuladas(
                    status_actual, proc.get("created_at"),
                    user_id, user_name, role, proc_id
                )

                todo_historico.extend(history_entries)
                membro_history_count += len(history_entries)

                # Gerar 2-5 actividades por processo
                n_actividades = random.randint(2, 5)
                for _ in range(n_actividades):
                    data_act = dias_atras(random.randint(1, 30))
                    todo_actividades.append(
                        gerar_actividade(proc_id, user_id, user_name, role, data_act)
                    )

                # Actualizar created_at do processo (recuar data)
                if not dry_run:
                    await database.processes.update_one(
                        {"id": proc_id},
                        {"$set": {
                            "created_at": iso_str(novo_created_at),
                            "updated_at": iso_str(transitioned_at),
                        }}
                    )

                processos_actualizados += 1

            print(f"   ✅ Histórico simulado para {role.capitalize()} "
                  f"{user_name}: {n_proc_simular} processos, "
                  f"{membro_history_count} transições")

        print(f"\n   📊 Total de processos actualizados: {processos_actualizados}")
        print(f"   📊 Total de registos de histórico: {len(todo_historico)}")
        print(f"   📊 Total de actividades geradas: {len(todo_actividades)}")
        print()

        # ==================================================================
        # PASSO 4: INSERIR DADOS NA BD
        # ==================================================================
        if dry_run:
            print("=" * 60)
            print("🏃 MODO DRY-RUN — Nenhum dado gravado")
            print("=" * 60)
            print(f"   Tarefas que seriam inseridas: {len(todas_tarefas)}")
            print(f"   Registos de histórico: {len(todo_historico)}")
            print(f"   Actividades: {len(todo_actividades)}")
            print(f"   Processos com datas recuadas: {processos_actualizados}")
            print()
            return

        print("=" * 60)
        print("💾 PASSO 4: Inserir Dados na Base de Dados")
        print("=" * 60)

        # Inserir tarefas em batches
        if todas_tarefas:
            batch_size = 50
            for i in range(0, len(todas_tarefas), batch_size):
                batch = todas_tarefas[i:i + batch_size]
                await database.tasks.insert_many(batch)
            print(f"   ✅ {len(todas_tarefas)} tarefas inseridas na coleção 'tasks'")

        # Inserir histórico em batches
        if todo_historico:
            batch_size = 50
            for i in range(0, len(todo_historico), batch_size):
                batch = todo_historico[i:i + batch_size]
                await database.history.insert_many(batch)
            print(f"   ✅ {len(todo_historico)} registos inseridos na coleção 'history'")

        # Inserir actividades em batches
        if todo_actividades:
            batch_size = 50
            for i in range(0, len(todo_actividades), batch_size):
                batch = todo_actividades[i:i + batch_size]
                await database.activities.insert_many(batch)
            print(f"   ✅ {len(todo_actividades)} registos inseridos na coleção 'activities'")

        print()

        # ==================================================================
        # RESUMO FINAL
        # ==================================================================
        print("=" * 60)
        print("📊 RESUMO FINAL")
        print("=" * 60)
        print(f"   👥 Utilizadores da equipa: {len(equipa)}")
        for role, members in by_role.items():
            print(f"      {role.capitalize()}: {len(members)}")
        print(f"   📋 Tarefas criadas: {len(todas_tarefas)}")
        print(f"      ✅ Concluídas: {total_tarefas_concluidas}")
        print(f"      ⏳ Pendentes: {total_tarefas_pendentes}")
        print(f"      🔴 Atrasadas: {total_tarefas_atrasadas}")
        print(f"   🔄 Registos de histórico: {len(todo_historico)}")
        print(f"   💬 Actividades: {len(todo_actividades)}")
        print(f"   📁 Processos com datas recuadas: {processos_actualizados}")
        print()

    finally:
        mongo_client.close()


# ==============================================================================
# PONTO DE ENTRADA
# ==============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed de Mock Data de Desempenho para PowerCell"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria alterado sem gravar na BD"
    )
    parser.add_argument(
        "--company-id",
        type=str,
        default=None,
        help="Filtrar por empresa (company_id) específica"
    )
    args = parser.parse_args()

    asyncio.run(seed_performance_data(
        dry_run=args.dry_run,
        company_id=args.company_id,
    ))
