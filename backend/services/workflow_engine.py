"""
O22 - Motor de Automação de Workflows "No-Code"
Sistema de regras: "Se X, Então Y"

Triggers (condições):
- process_status_changed: Quando o estado de um processo muda
- process_created: Quando um processo é criado
- document_uploaded: Quando um documento é carregado
- process_stale: Quando um processo não é atualizado há N dias
- client_registered: Quando um novo cliente se regista

Actions (ações):
- send_notification: Enviar notificação a um utilizador/role
- change_status: Alterar o estado do processo
- assign_user: Atribuir processo a um utilizador
- add_comment: Adicionar comentário automático ao processo
- send_email: Enviar email (template)
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from database import db

logger = logging.getLogger(__name__)


# ============== MODELS ==============

VALID_TRIGGERS = [
    "process_status_changed",
    "process_created",
    "document_uploaded",
    "process_stale",
    "client_registered",
]

VALID_ACTIONS = [
    "send_notification",
    "change_status",
    "assign_user",
    "add_comment",
    "send_email",
    "create_task",  # Pacote D — Criar tarefa automaticamente
]


# ============== CRUD ==============

async def list_rules(active_only: bool = False) -> list:
    """Listar todas as regras de automação."""
    query = {"is_active": True} if active_only else {}
    rules = await db.automation_rules.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return rules


async def get_rule(rule_id: str) -> Optional[dict]:
    """Obter uma regra específica."""
    return await db.automation_rules.find_one({"id": rule_id}, {"_id": 0})


async def create_rule(data: dict, user: dict) -> dict:
    """
    Cria uma nova regra de automação no-code no sistema.

    Permite aos utilizadores configurar comportamentos automatizados sem
    escrever código, seguindo o padrão "Se X, Então Y". Cada regra fica
    registada com rastreabilidade (criador, contagem de execuções, última
    execução) para auditoria.

    Args:
        data: Dicionário com a definição da regra, contendo:
            - name (str): Nome descritivo da regra.
            - description (str, opcional): Descrição detalhada.
            - trigger (str): Tipo de trigger (ver VALID_TRIGGERS).
            - trigger_config (dict, opcional): Configuração do trigger
              (ex: target_status, stale_days).
            - action (str): Tipo de ação (ver VALID_ACTIONS).
            - action_config (dict, opcional): Configuração da ação
              (ex: target_role, new_status, message).
            - is_active (bool, opcional): Se a regra fica ativa imediatamente.
        user: Dicionário do utilizador autenticado que cria a regra.

    Returns:
        dict: Regra criada com id, timestamps e contadores inicializados.
    """
    rule = {
        "id": str(uuid.uuid4()),
        "name": data["name"],
        "description": data.get("description", ""),
        "trigger": data["trigger"],
        "trigger_config": data.get("trigger_config", {}),
        "action": data["action"],
        "action_config": data.get("action_config", {}),
        "is_active": data.get("is_active", True),
        "execution_count": 0,
        "last_executed_at": None,
        "created_by": user.get("name", user.get("email", "unknown")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.automation_rules.insert_one(rule)
    rule.pop("_id", None)
    return rule


async def update_rule(rule_id: str, data: dict) -> Optional[dict]:
    """Actualizar uma regra."""
    update = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for field in ["name", "description", "trigger", "trigger_config", "action", "action_config", "is_active"]:
        if field in data:
            update[field] = data[field]
    
    result = await db.automation_rules.find_one_and_update(
        {"id": rule_id},
        {"$set": update},
        return_document=True
    )
    if result:
        result.pop("_id", None)
    return result


async def delete_rule(rule_id: str) -> bool:
    """Eliminar uma regra."""
    result = await db.automation_rules.delete_one({"id": rule_id})
    return result.deleted_count > 0


# ============== ENGINE ==============

async def evaluate_trigger(trigger_type: str, context: dict) -> list:
    """
    Avalia todas as regras de automação ativas para um determinado trigger e retorna
    as regras que devem ser executadas.

    Cada regra é avaliada com filtros específicos por tipo de trigger:
    - process_status_changed: verifica transição de estado (from_status → target_status).
    - process_stale: verifica threshold de dias sem atualização.
    - document_uploaded: verifica categoria do documento.

    As regras são armazenadas na coleção automation_rules e podem ser
    criadas/geridas via interface no-code no frontend.

    Args:
        trigger_type: Tipo de trigger (ex: "process_status_changed").
        context: Dicionário com dados do evento, incluindo:
            - new_status, old_status (para mudanças de estado).
            - process_id, client_name (para registo de histórico).
            - days_since_update (para processos parados).

    Returns:
        list: Lista de regras (dicts) que passaram nos filtros e devem ser executadas.
    """
    rules = await db.automation_rules.find({
        "trigger": trigger_type,
        "is_active": True
    }, {"_id": 0}).to_list(50)
    
    matching_rules = []
    for rule in rules:
        config = rule.get("trigger_config", {})
        
        if trigger_type == "process_status_changed":
            # Verificar se o novo status corresponde ao configurado
            target_status = config.get("target_status")
            if target_status and context.get("new_status") != target_status:
                continue
            # Verificar status anterior
            from_status = config.get("from_status")
            if from_status and context.get("old_status") != from_status:
                continue
        
        elif trigger_type == "process_stale":
            # Verificar se dias sem actualização >= threshold
            threshold = config.get("stale_days", 14)
            if context.get("days_since_update", 0) < threshold:
                continue
        
        elif trigger_type == "document_uploaded":
            # Verificar categoria do documento
            target_category = config.get("document_category")
            if target_category and context.get("category") != target_category:
                continue
        
        matching_rules.append(rule)
    
    return matching_rules


async def execute_action(rule: dict, context: dict) -> bool:
    """
    Executa a ação definida numa regra de automação, aplicando substituição
    de variáveis de contexto no corpo de mensagens e comentários.

    Esta função é o coração do motor de automação: traduz a configuração
    abstrata da regra (criada via UI no-code) em operações concretas na
    base de dados (envio de notificações, alteração de estados, atribuição
    de processos, registo de comentários automáticos).

    Garante rastreabilidade ao:
    - Atualizar a contagem de execuções (execution_count) da regra.
    - Registar o timestamp da última execução.
    - Capturar e registar erros sem propagar exceções (fail-safe).

    Args:
        rule: Dicionário da regra de automação contendo:
            - action (str): Tipo de ação a executar.
            - action_config (dict): Parâmetros da ação.
            - id (str): ID da regra (para atualizar estatísticas).
            - name (str): Nome da regra (para logging e comentários).
        context: Dicionário com dados do evento para substituição de
            variáveis como {client_name}, {status}, {process_id}.

    Returns:
        bool: True se a ação foi executada com sucesso, False em caso
            de erro (nunca levanta exceção — fail-safe).
    """
    action = rule["action"]
    config = rule.get("action_config", {})
    
    try:
        if action == "send_notification":
            message = config.get("message", "Automação executada")
            # Substituir variáveis no message
            message = message.replace("{client_name}", context.get("client_name", "Cliente"))
            message = message.replace("{status}", context.get("new_status", context.get("status", "")))
            message = message.replace("{process_id}", context.get("process_id", ""))
            
            if config.get("target_role"):
                # Notificar todos os utilizadores com esse role
                from services.role_query import deep_role_filter
                users = await db.users.find(
                    {"$and": [deep_role_filter(config["target_role"]), {"is_active": {"$ne": False}}]},
                    {"_id": 0, "id": 1}
                ).to_list(20)
                for user in users:
                    await db.notifications.insert_one({
                        "id": str(uuid.uuid4()),
                        "user_id": user["id"],
                        "message": message,
                        "type": "automation",
                        "process_id": context.get("process_id"),
                        "read": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                    })
            elif config.get("target_user_id"):
                await db.notifications.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": config["target_user_id"],
                    "message": message,
                    "type": "automation",
                    "process_id": context.get("process_id"),
                    "read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                })
        
        elif action == "change_status":
            new_status = config.get("new_status")
            if new_status and context.get("process_id"):
                await db.processes.update_one(
                    {"id": context["process_id"]},
                    {"$set": {
                        "status": new_status,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
        
        elif action == "assign_user":
            user_id = config.get("user_id")
            role_field = config.get("role_field", "assigned_consultor_id")
            if user_id and context.get("process_id"):
                user_data = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1})
                name_field = role_field.replace("_id", "_name")
                await db.processes.update_one(
                    {"id": context["process_id"]},
                    {"$set": {
                        role_field: user_id,
                        name_field: user_data.get("name", "") if user_data else "",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
        
        elif action == "add_comment":
            comment_text = config.get("comment", "Ação automática")
            comment_text = comment_text.replace("{client_name}", context.get("client_name", "Cliente"))
            comment_text = comment_text.replace("{status}", context.get("new_status", context.get("status", "")))
            if context.get("process_id"):
                await db.processes.update_one(
                    {"id": context["process_id"]},
                    {"$push": {"activities": {
                        "id": str(uuid.uuid4()),
                        "type": "comment",
                        "comment": comment_text,
                        "user_name": f"Automacao: {rule['name']}",
                        "source": "automation",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }}}
                )

        elif action == "create_task":
            # Pacote D — Criar tarefa automaticamente
            # config: {title, urgency (low/medium/high), assigned_role, due_in_days (opcional)}
            title = config.get("title", "Tarefa automática")
            # Substituir variáveis de contexto no título
            title = title.replace("{client_name}", context.get("client_name", "Cliente"))
            title = title.replace("{status}", context.get("new_status", context.get("status", "")))
            title = title.replace("{process_id}", context.get("process_id", ""))

            urgency = config.get("urgency", "medium")  # low/medium/high
            assigned_role = config.get("assigned_role")  # ex: "consultor", "diretor"
            due_in_days = config.get("due_in_days")

            # Resolver data de vencimento (opcional)
            due_date_iso = None
            if due_in_days and isinstance(due_in_days, (int, float)) and due_in_days > 0:
                due_date_iso = (datetime.now(timezone.utc) + timedelta(days=int(due_in_days))).isoformat()

            # Resolver utilizador atribuído: se houver assigned_role, procurar
            # o utilizador com esse role associado ao processo (consultor/mediador/
            # indexador). Se não houver, a tarefa fica sem atribuição (admin vê).
            assigned_to = None
            if assigned_role and context.get("process_id"):
                process = await db.processes.find_one(
                    {"id": context["process_id"]},
                    {"_id": 0, "assigned_consultor_id": 1, "assigned_mediador_id": 1, "assigned_indexacao_id": 1}
                )
                if process:
                    role_field_map = {
                        "consultor": "assigned_consultor_id",
                        "intermediario": "assigned_mediador_id",
                        "mediador": "assigned_mediador_id",
                        "indexacao": "assigned_indexacao_id",
                    }
                    role_field = role_field_map.get(assigned_role)
                    if role_field:
                        assigned_to = process.get(role_field)

            task_doc = {
                "id": str(uuid.uuid4()),
                "title": title,
                "description": f"Tarefa criada automaticamente pela regra '{rule['name']}' (urgência: {urgency})",
                "assigned_to": assigned_to,
                "process_id": context.get("process_id"),
                "due_date": due_date_iso,
                "urgency": urgency,
                "source": "automation",
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "created_by": None,  # Sistema
                "completed": False,
                "completed_at": None,
                "completed_by": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.tasks.insert_one(task_doc)
            logger.info(
                f"[AUTOMATION] Tarefa criada: {title} (urgência: {urgency}, "
                f"atribuída a: {assigned_to or 'sem atribuição'}, processo: {context.get('process_id')})"
            )
        
        # Actualizar contagem de execuções
        await db.automation_rules.update_one(
            {"id": rule["id"]},
            {
                "$inc": {"execution_count": 1},
                "$set": {"last_executed_at": datetime.now(timezone.utc).isoformat()}
            }
        )
        
        logger.info(f"Regra '{rule['name']}' executada com sucesso (ação: {action})")
        return True
    
    except Exception as e:
        logger.error(f"Erro ao executar regra '{rule['name']}': {e}")
        return False


async def process_trigger(trigger_type: str, context: dict) -> int:
    """
    Processa um trigger: avalia regras e executa ações. Ponto de entrada
    principal do motor de automação no-code.

    Chamado por outros serviços sempre que um evento relevante ocorre
    (ex: mudança de estado, upload de documento, criação de processo).

    Args:
        trigger_type: Tipo de trigger (ex: "process_status_changed").
        context: Contexto do evento com dados para template de ações
            (ex: {"client_name": "João", "new_status": "em_analise"}).

    Returns:
        int: Número de ações executadas com sucesso.
    """
    matching_rules = await evaluate_trigger(trigger_type, context)
    executed = 0
    
    for rule in matching_rules:
        success = await execute_action(rule, context)
        if success:
            executed += 1
    
    if executed > 0:
        logger.info(f"Trigger '{trigger_type}': {executed}/{len(matching_rules)} regras executadas")
    
    return executed
