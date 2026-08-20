"""Automation triggers / actions catalog handlers.

Extraído de `routes/automation.py`.
"""
from __future__ import annotations


async def run_list_triggers():
    return {
        "triggers": [
            {"id": "process_status_changed", "label": "Estado do processo alterado", "config_fields": [
                {"key": "from_status", "label": "De estado (opcional)", "type": "select_status"},
                {"key": "target_status", "label": "Para estado", "type": "select_status"},
            ]},
            {"id": "process_created", "label": "Novo processo criado", "config_fields": []},
            {"id": "document_uploaded", "label": "Documento carregado", "config_fields": [
                {"key": "document_category", "label": "Categoria do documento", "type": "text"},
            ]},
            {"id": "process_stale", "label": "Processo sem atualização", "config_fields": [
                {"key": "stale_days", "label": "Dias sem atualização", "type": "number", "default": 14},
            ]},
            {"id": "client_registered", "label": "Novo cliente registado", "config_fields": []},
        ]
    }


async def run_list_actions():
    return {
        "actions": [
            {"id": "send_notification", "label": "Enviar notificação", "config_fields": [
                {"key": "target_role", "label": "Para role (ex: admin, consultor)", "type": "select_role"},
                {"key": "target_user_id", "label": "Ou para utilizador específico", "type": "select_user"},
                {"key": "message", "label": "Mensagem (usar {client_name}, {status})", "type": "textarea"},
            ]},
            {"id": "change_status", "label": "Alterar estado do processo", "config_fields": [
                {"key": "new_status", "label": "Novo estado", "type": "select_status"},
            ]},
            {"id": "assign_user", "label": "Atribuir utilizador", "config_fields": [
                {"key": "user_id", "label": "Utilizador", "type": "select_user"},
                {"key": "role_field", "label": "Campo (assigned_consultor_id ou assigned_mediador_id)", "type": "select", "options": ["assigned_consultor_id", "assigned_mediador_id"]},
            ]},
            {"id": "add_comment", "label": "Adicionar comentário", "config_fields": [
                {"key": "comment", "label": "Texto do comentário", "type": "textarea"},
            ]},
            {"id": "send_email", "label": "Enviar email (template)", "config_fields": [
                {"key": "template", "label": "Template do email", "type": "select_email_template"},
            ]},
            {"id": "create_task", "label": "Criar tarefa", "config_fields": [
                {"key": "title", "label": "Título da tarefa (usar {client_name}, {status})", "type": "text", "default": "Contactar {client_name}"},
                {"key": "urgency", "label": "Urgência", "type": "select", "options": ["low", "medium", "high"], "default": "medium", "option_labels": {"low": "Baixa", "medium": "Média", "high": "Alta"}},
                {"key": "assigned_role", "label": "Atribuída a (role)", "type": "select", "options": ["consultor", "intermediario", "indexacao"], "option_labels": {"consultor": "Consultor", "intermediario": "Intermediário", "indexacao": "Indexação"}},
                {"key": "due_in_days", "label": "Prazo (dias, opcional)", "type": "number", "default": 7},
            ]},
        ]
    }
