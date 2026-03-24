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
from datetime import datetime, timezone
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
    """Criar uma nova regra de automação."""
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
    """Atualizar uma regra."""
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
    Avaliar todas as regras ativas para um determinado trigger.
    Retorna lista de regras que devem ser executadas.
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
            # Verificar se dias sem atualização >= threshold
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
    """Executar a ação de uma regra."""
    action = rule["action"]
    config = rule.get("action_config", {})
    
    try:
        if action == "send_notification":
            target = config.get("target_user_id") or config.get("target_role")
            message = config.get("message", "Automação executada")
            # Substituir variáveis no message
            message = message.replace("{client_name}", context.get("client_name", "Cliente"))
            message = message.replace("{status}", context.get("new_status", context.get("status", "")))
            message = message.replace("{process_id}", context.get("process_id", ""))
            
            if config.get("target_role"):
                # Notificar todos os utilizadores com esse role
                users = await db.users.find(
                    {"role": config["target_role"], "is_active": {"$ne": False}},
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
        
        # Atualizar contagem de execuções
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
    Processar um trigger: avaliar regras e executar ações.
    Ponto de entrada principal do motor de automação.
    
    Returns: número de ações executadas com sucesso
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
