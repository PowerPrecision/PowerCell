"""
Testes unitários para serviços de processos.
"""
import pytest
from datetime import datetime, timezone, timedelta


class TestProcessStatus:
    """Testes para lógica de status de processos."""
    
    def test_valid_status_values(self):
        """Testa valores válidos de status."""
        valid_statuses = [
            "triagem",
            "documentacao",
            "analise",
            "aprovado",
            "recusado",
            "concluido",
            "desistido",
            "cancelado"
        ]
        
        for status in valid_statuses:
            assert status.islower()
            assert "_" not in status or status in ["em_analise"]
    
    def test_status_transitions(self):
        """Testa transições de status válidas."""
        VALID_TRANSITIONS = {
            "triagem": ["documentacao", "cancelado", "desistido"],
            "documentacao": ["analise", "triagem", "cancelado", "desistido"],
            "analise": ["aprovado", "recusado", "documentacao", "cancelado"],
            "aprovado": ["concluido", "cancelado"],
            "recusado": ["triagem", "cancelado"],
            "concluido": [],
            "desistido": ["triagem"],
            "cancelado": ["triagem"]
        }
        
        def is_valid_transition(from_status, to_status):
            return to_status in VALID_TRANSITIONS.get(from_status, [])
        
        # Transições válidas
        assert is_valid_transition("triagem", "documentacao")
        assert is_valid_transition("documentacao", "analise")
        assert is_valid_transition("analise", "aprovado")
        
        # Transições inválidas
        assert not is_valid_transition("triagem", "concluido")
        assert not is_valid_transition("concluido", "triagem")
    
    def test_final_status_detection(self):
        """Testa detecção de status final."""
        FINAL_STATUSES = ["concluido", "cancelado"]
        
        def is_final_status(status):
            return status in FINAL_STATUSES
        
        assert is_final_status("concluido")
        assert is_final_status("cancelado")
        assert not is_final_status("aprovado")
        assert not is_final_status("documentacao")


class TestProcessPriority:
    """Testes para cálculo de prioridade de processos."""
    
    def test_priority_calculation(self):
        """Testa cálculo de prioridade baseado em múltiplos factores."""
        def calculate_priority(days_since_creation, documents_pending, value):
            score = 0
            
            # Antiguidade (mais antigo = maior prioridade)
            if days_since_creation > 30:
                score += 30
            elif days_since_creation > 14:
                score += 20
            elif days_since_creation > 7:
                score += 10
            
            # Documentos pendentes
            score += min(documents_pending * 5, 30)
            
            # Valor do processo
            if value >= 500000:
                score += 20
            elif value >= 250000:
                score += 10
            
            if score >= 60:
                return "alta"
            elif score >= 30:
                return "media"
            return "baixa"
        
        # Processo urgente (30 + 25 + 20 = 75)
        assert calculate_priority(35, 5, 600000) == "alta"
        
        # Processo médio (10 + 10 + 10 = 30)
        assert calculate_priority(10, 2, 250000) == "media"
        
        # Processo baixa prioridade (0 + 0 + 0 = 0)
        assert calculate_priority(3, 0, 100000) == "baixa"
    
    def test_sla_calculation(self):
        """Testa cálculo de SLA."""
        SLA_DAYS = {
            "triagem": 2,
            "documentacao": 5,
            "analise": 7,
            "aprovado": 3
        }
        
        def get_sla_deadline(status, created_at):
            days = SLA_DAYS.get(status, 5)
            return created_at + timedelta(days=days)
        
        now = datetime.now(timezone.utc)
        
        deadline = get_sla_deadline("triagem", now)
        assert (deadline - now).days == 2
        
        deadline = get_sla_deadline("analise", now)
        assert (deadline - now).days == 7
    
    def test_sla_breach_detection(self):
        """Testa detecção de violação de SLA."""
        def is_sla_breached(deadline, current_time=None):
            if current_time is None:
                current_time = datetime.now(timezone.utc)
            return current_time > deadline
        
        now = datetime.now(timezone.utc)
        
        # SLA não violado
        future_deadline = now + timedelta(days=2)
        assert not is_sla_breached(future_deadline, now)
        
        # SLA violado
        past_deadline = now - timedelta(days=1)
        assert is_sla_breached(past_deadline, now)


class TestProcessAssignment:
    """Testes para atribuição de processos."""
    
    def test_consultant_workload(self):
        """Testa cálculo de carga de trabalho de consultor."""
        def calculate_workload(active_processes, max_processes=20):
            return (active_processes / max_processes) * 100
        
        assert calculate_workload(10) == 50.0
        assert calculate_workload(20) == 100.0
        assert calculate_workload(5) == 25.0
    
    def test_auto_assignment_logic(self):
        """Testa lógica de atribuição automática."""
        consultants = [
            {"id": "c1", "active_processes": 15, "max_processes": 20},
            {"id": "c2", "active_processes": 8, "max_processes": 20},
            {"id": "c3", "active_processes": 18, "max_processes": 20},
        ]
        
        def find_least_loaded_consultant(consultants):
            available = [c for c in consultants 
                        if c["active_processes"] < c["max_processes"]]
            if not available:
                return None
            return min(available, key=lambda c: c["active_processes"])
        
        best = find_least_loaded_consultant(consultants)
        assert best["id"] == "c2"  # Menos carregado
    
    def test_assignment_validation(self):
        """Testa validação de atribuição."""
        def can_assign(consultant, process_type, consultant_specialties):
            if not consultant.get("is_active", True):
                return False
            if consultant.get("active_processes", 0) >= consultant.get("max_processes", 20):
                return False
            if consultant_specialties and process_type not in consultant_specialties:
                return False
            return True
        
        consultant = {
            "is_active": True,
            "active_processes": 10,
            "max_processes": 20,
            "specialties": ["credito_habitacao", "credito_pessoal"]
        }
        
        assert can_assign(consultant, "credito_habitacao", consultant["specialties"])
        assert not can_assign(consultant, "seguro", consultant["specialties"])


class TestProcessTimeline:
    """Testes para timeline de processos."""
    
    def test_timeline_event_structure(self):
        """Testa estrutura de evento de timeline."""
        event = {
            "id": "evt-123",
            "process_id": "proc-456",
            "type": "status_change",
            "description": "Status alterado para documentacao",
            "user_email": "admin@test.com",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "old_status": "triagem",
                "new_status": "documentacao"
            }
        }
        
        required_fields = ["id", "process_id", "type", "timestamp"]
        for field in required_fields:
            assert field in event
    
    def test_timeline_event_types(self):
        """Testa tipos de eventos de timeline."""
        valid_types = [
            "status_change",
            "document_added",
            "document_removed",
            "comment_added",
            "assignment_changed",
            "data_updated",
            "email_sent",
            "email_received"
        ]
        
        for event_type in valid_types:
            assert "_" in event_type
    
    def test_timeline_ordering(self):
        """Testa ordenação de eventos de timeline."""
        events = [
            {"timestamp": "2024-01-03T10:00:00Z"},
            {"timestamp": "2024-01-01T10:00:00Z"},
            {"timestamp": "2024-01-02T10:00:00Z"},
        ]
        
        sorted_events = sorted(events, key=lambda e: e["timestamp"], reverse=True)
        
        assert sorted_events[0]["timestamp"] == "2024-01-03T10:00:00Z"
        assert sorted_events[-1]["timestamp"] == "2024-01-01T10:00:00Z"


class TestProcessDocuments:
    """Testes para gestão de documentos de processos."""
    
    def test_required_documents_by_status(self):
        """Testa documentos requeridos por status."""
        REQUIRED_DOCS = {
            "documentacao": ["cc", "comprovativo_residencia", "recibo_vencimento"],
            "analise": ["irs", "contrato_trabalho", "extrato_bancario"],
            "aprovado": ["cpcv", "caderneta_predial"]
        }
        
        def get_required_documents(status):
            return REQUIRED_DOCS.get(status, [])
        
        assert "cc" in get_required_documents("documentacao")
        assert "irs" in get_required_documents("analise")
        assert len(get_required_documents("triagem")) == 0
    
    def test_document_completion_percentage(self):
        """Testa cálculo de percentagem de documentos completos."""
        def calculate_completion(uploaded_docs, required_docs):
            if not required_docs:
                return 100
            
            uploaded_types = set(d.get("type") for d in uploaded_docs)
            required_types = set(required_docs)
            
            completed = uploaded_types & required_types
            return int((len(completed) / len(required_types)) * 100)
        
        uploaded = [
            {"type": "cc"},
            {"type": "recibo_vencimento"}
        ]
        required = ["cc", "recibo_vencimento", "comprovativo_residencia"]
        
        completion = calculate_completion(uploaded, required)
        assert completion == 66  # 2/3
    
    def test_missing_documents_detection(self):
        """Testa detecção de documentos em falta."""
        def get_missing_documents(uploaded_docs, required_docs):
            uploaded_types = set(d.get("type") for d in uploaded_docs)
            required_types = set(required_docs)
            
            return list(required_types - uploaded_types)
        
        uploaded = [{"type": "cc"}, {"type": "irs"}]
        required = ["cc", "irs", "contrato_trabalho"]
        
        missing = get_missing_documents(uploaded, required)
        assert "contrato_trabalho" in missing
        assert "cc" not in missing


class TestProcessNotifications:
    """Testes para notificações de processos."""
    
    def test_notification_trigger_conditions(self):
        """Testa condições para disparo de notificações."""
        def should_notify(event_type, user_preferences):
            default_notifications = ["status_change", "document_expiry", "assignment"]
            
            if not user_preferences.get("notifications_enabled", True):
                return False
            
            allowed = user_preferences.get("notification_types", default_notifications)
            return event_type in allowed
        
        prefs = {
            "notifications_enabled": True,
            "notification_types": ["status_change", "document_expiry"]
        }
        
        assert should_notify("status_change", prefs)
        assert should_notify("document_expiry", prefs)
        assert not should_notify("comment_added", prefs)
    
    def test_notification_channels(self):
        """Testa canais de notificação."""
        channels = ["email", "in_app", "push"]
        
        def get_notification_channels(user_preferences, event_type):
            default_channels = ["in_app"]
            
            if event_type == "status_change":
                return user_preferences.get("status_channels", ["in_app", "email"])
            elif event_type == "document_expiry":
                return user_preferences.get("expiry_channels", ["in_app", "email", "push"])
            
            return default_channels
        
        prefs = {"status_channels": ["email"], "expiry_channels": ["in_app"]}
        
        assert "email" in get_notification_channels(prefs, "status_change")
        assert "in_app" in get_notification_channels(prefs, "document_expiry")
