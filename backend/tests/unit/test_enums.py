"""
====================================================================
TESTES UNITÁRIOS - ENUMS
====================================================================
Testes para enumerações centralizadas.
====================================================================
"""
import pytest
from models.enums import (
    ProcessStatus,
    ProcessType,
    UserRoleEnum,
    NotificationType,
    LeadStatus,
    DocumentCategory,
)


class TestProcessStatus:
    """Testes para ProcessStatus enum."""
    
    def test_active_statuses(self):
        """Verifica que status activos estão correctos."""
        active = ProcessStatus.active_statuses()
        assert "clientes_espera" in active
        assert "documentacao" in active
        assert "escritura" in active
        # Status finais não devem estar em active
        assert "concluido" not in active
        assert "perdido" not in active
    
    def test_completed_statuses(self):
        """Verifica que status concluídos estão correctos."""
        completed = ProcessStatus.completed_statuses()
        assert "concluido" in completed
        assert "arquivo" in completed
        assert len(completed) == 2
    
    def test_failed_statuses(self):
        """Verifica que status falhados estão correctos."""
        failed = ProcessStatus.failed_statuses()
        assert "perdido" in failed
        assert "desistencias" in failed
    
    def test_all_values_unique(self):
        """Todos os valores devem ser únicos."""
        all_vals = ProcessStatus.all_values()
        assert len(all_vals) == len(set(all_vals))


class TestUserRoleEnum:
    """Testes para UserRoleEnum."""
    
    def test_staff_roles_excludes_cliente(self):
        """Staff roles não deve incluir cliente."""
        staff = UserRoleEnum.staff_roles()
        assert "cliente" not in staff
        assert "admin" in staff
        assert "consultor" in staff
    
    def test_management_roles(self):
        """Management roles deve ter apenas gestão."""
        management = UserRoleEnum.management_roles()
        assert "admin" in management
        assert "ceo" in management
        assert "diretor" in management
        assert "consultor" not in management


class TestNotificationType:
    """Testes para NotificationType."""
    
    def test_high_priority_types(self):
        """Verifica tipos de alta prioridade."""
        high = NotificationType.high_priority_types()
        assert "system_error" in high
        assert "deadline_missed" in high


class TestLeadStatus:
    """Testes para LeadStatus."""
    
    def test_active_statuses(self):
        """Status activos de leads."""
        active = LeadStatus.active_statuses()
        assert "novo" in active
        assert "proposta" in active
        assert "ganho" not in active
        assert "perdido" not in active
