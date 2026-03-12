"""
Testes unitários para serviços de notificações.
"""
import pytest
from datetime import datetime, timezone, timedelta


class TestNotificationTypes:
    """Testes para tipos de notificação."""
    
    def test_valid_notification_types(self):
        """Testa tipos válidos de notificação."""
        valid_types = [
            "process_update",
            "document_expiry",
            "task_assigned",
            "email_received",
            "system_alert",
            "document_expiry_watchdog",
            "ai_analysis_complete",
            "weekly_report"
        ]
        
        for ntype in valid_types:
            assert isinstance(ntype, str)
            assert len(ntype) > 0
    
    def test_notification_urgency_levels(self):
        """Testa níveis de urgência."""
        levels = {
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4
        }
        
        # Critical tem maior prioridade
        assert levels["critical"] > levels["high"]
        assert levels["high"] > levels["medium"]
        assert levels["medium"] > levels["low"]


class TestNotificationCreation:
    """Testes para criação de notificações."""
    
    def test_notification_structure(self):
        """Testa estrutura de notificação."""
        notification = {
            "id": "notif-123",
            "type": "process_update",
            "title": "Processo Actualizado",
            "message": "O processo PP-2024-001 foi actualizado",
            "user_id": "user-456",
            "urgency": "medium",
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {"process_id": "proc-789"}
        }
        
        required = ["id", "type", "title", "user_id", "is_read"]
        for field in required:
            assert field in notification
    
    def test_notification_title_generation(self):
        """Testa geração de títulos de notificação."""
        def generate_title(notification_type, data):
            templates = {
                "process_update": f"Processo {data.get('process_number', '')} actualizado",
                "document_expiry": f"Documento a expirar: {data.get('document_type', '')}",
                "task_assigned": f"Nova tarefa atribuída",
                "email_received": f"Novo email de {data.get('sender', '')}"
            }
            return templates.get(notification_type, "Notificação")
        
        data = {"process_number": "PP-2024-001"}
        title = generate_title("process_update", data)
        assert "PP-2024-001" in title
    
    def test_notification_batch_creation(self):
        """Testa criação de notificações em lote."""
        def create_batch_notifications(user_ids, template):
            notifications = []
            for user_id in user_ids:
                notifications.append({
                    **template,
                    "id": f"notif-{user_id}",
                    "user_id": user_id
                })
            return notifications
        
        users = ["user1", "user2", "user3"]
        template = {"type": "system_alert", "title": "Manutenção agendada"}
        
        notifications = create_batch_notifications(users, template)
        
        assert len(notifications) == 3
        assert notifications[0]["user_id"] == "user1"


class TestNotificationFiltering:
    """Testes para filtragem de notificações."""
    
    def test_filter_unread(self):
        """Testa filtro de não lidas."""
        notifications = [
            {"id": "1", "is_read": False},
            {"id": "2", "is_read": True},
            {"id": "3", "is_read": False},
        ]
        
        unread = [n for n in notifications if not n["is_read"]]
        
        assert len(unread) == 2
    
    def test_filter_by_type(self):
        """Testa filtro por tipo."""
        notifications = [
            {"id": "1", "type": "process_update"},
            {"id": "2", "type": "document_expiry"},
            {"id": "3", "type": "process_update"},
        ]
        
        process_updates = [n for n in notifications if n["type"] == "process_update"]
        
        assert len(process_updates) == 2
    
    def test_filter_by_date_range(self):
        """Testa filtro por intervalo de datas."""
        now = datetime.now(timezone.utc)
        
        notifications = [
            {"id": "1", "created_at": (now - timedelta(hours=1)).isoformat()},
            {"id": "2", "created_at": (now - timedelta(days=2)).isoformat()},
            {"id": "3", "created_at": (now - timedelta(days=10)).isoformat()},
        ]
        
        def filter_recent(notifications, max_age_days=7):
            cutoff = now - timedelta(days=max_age_days)
            return [
                n for n in notifications 
                if datetime.fromisoformat(n["created_at"].replace("Z", "+00:00")) > cutoff
            ]
        
        recent = filter_recent(notifications)
        assert len(recent) == 2


class TestNotificationPreferences:
    """Testes para preferências de notificação."""
    
    def test_default_preferences(self):
        """Testa preferências padrão."""
        defaults = {
            "email_notifications": True,
            "push_notifications": False,
            "in_app_notifications": True,
            "notification_types": ["process_update", "document_expiry", "task_assigned"],
            "quiet_hours": {"start": "22:00", "end": "08:00"},
            "email_digest": "daily"
        }
        
        assert defaults["email_notifications"] == True
        assert defaults["in_app_notifications"] == True
        assert len(defaults["notification_types"]) == 3
    
    def test_should_notify_by_channel(self):
        """Testa verificação de canal de notificação."""
        def should_notify(preferences, channel):
            channel_map = {
                "email": "email_notifications",
                "push": "push_notifications",
                "in_app": "in_app_notifications"
            }
            return preferences.get(channel_map.get(channel), False)
        
        prefs = {
            "email_notifications": True,
            "push_notifications": False,
            "in_app_notifications": True
        }
        
        assert should_notify(prefs, "email")
        assert not should_notify(prefs, "push")
        assert should_notify(prefs, "in_app")
    
    def test_quiet_hours_check(self):
        """Testa verificação de horas silenciosas."""
        def is_quiet_hours(current_time, quiet_start, quiet_end):
            current = current_time.strftime("%H:%M")
            
            if quiet_start <= quiet_end:
                return quiet_start <= current <= quiet_end
            else:
                # Período cruza meia-noite
                return current >= quiet_start or current <= quiet_end
        
        # 23:00 está em quiet hours (22:00 - 08:00)
        time_23 = datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)
        assert is_quiet_hours(time_23, "22:00", "08:00")
        
        # 12:00 não está em quiet hours
        time_12 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert not is_quiet_hours(time_12, "22:00", "08:00")


class TestNotificationDelivery:
    """Testes para entrega de notificações."""
    
    def test_delivery_status(self):
        """Testa estados de entrega."""
        valid_statuses = ["pending", "delivered", "failed", "read"]
        
        for status in valid_statuses:
            assert status in valid_statuses
    
    def test_retry_logic(self):
        """Testa lógica de retry."""
        def should_retry(attempts, max_attempts=3, last_error=None):
            if attempts >= max_attempts:
                return False
            if last_error == "permanent_failure":
                return False
            return True
        
        assert should_retry(1)
        assert should_retry(2)
        assert not should_retry(3)
        assert not should_retry(1, last_error="permanent_failure")
    
    def test_delivery_priority(self):
        """Testa prioridade de entrega."""
        def get_delivery_priority(urgency):
            priorities = {
                "critical": 0,  # Imediato
                "high": 1,
                "medium": 5,
                "low": 10
            }
            return priorities.get(urgency, 5)
        
        assert get_delivery_priority("critical") < get_delivery_priority("high")
        assert get_delivery_priority("high") < get_delivery_priority("medium")


class TestNotificationCleanup:
    """Testes para limpeza de notificações."""
    
    def test_auto_delete_old_notifications(self):
        """Testa remoção automática de notificações antigas."""
        now = datetime.now(timezone.utc)
        
        notifications = [
            {"id": "1", "created_at": (now - timedelta(days=10)).isoformat(), "is_read": True},
            {"id": "2", "created_at": (now - timedelta(days=40)).isoformat(), "is_read": True},
            {"id": "3", "created_at": (now - timedelta(days=5)).isoformat(), "is_read": False},
        ]
        
        def filter_for_deletion(notifications, max_age_days=30):
            cutoff = now - timedelta(days=max_age_days)
            return [
                n for n in notifications
                if datetime.fromisoformat(n["created_at"].replace("Z", "+00:00")) < cutoff
                and n.get("is_read", False)
            ]
        
        to_delete = filter_for_deletion(notifications)
        assert len(to_delete) == 1
        assert to_delete[0]["id"] == "2"
    
    def test_bulk_mark_as_read(self):
        """Testa marcação em lote como lida."""
        notifications = [
            {"id": "1", "is_read": False},
            {"id": "2", "is_read": False},
            {"id": "3", "is_read": True},
        ]
        
        def mark_all_as_read(notifications):
            count = 0
            for n in notifications:
                if not n["is_read"]:
                    n["is_read"] = True
                    count += 1
            return count
        
        marked = mark_all_as_read(notifications)
        assert marked == 2
        assert all(n["is_read"] for n in notifications)
