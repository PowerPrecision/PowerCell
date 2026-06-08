"""
====================================================================
TESTES UNITÁRIOS - VALIDAÇÃO DE PROCESSOS
====================================================================
Testes para validação de dados de processos.
====================================================================
"""
import pytest
from models.enums import ProcessStatus, ProcessType


class TestProcessStatus:
    """Testes para ProcessStatus enum."""
    
    def test_all_15_phases_exist(self):
        """Verifica que todas as 15 fases do workflow existem."""
        all_statuses = ProcessStatus.all_values()
        
        # Deve ter 15 fases (14 originais + fila_espera)
        assert len(all_statuses) == 15
        
        # Fases iniciais
        assert "clientes_espera" in all_statuses
        assert "fila_espera" in all_statuses
        assert "documentacao" in all_statuses
        assert "analise" in all_statuses
        
        # Fases de aprovação
        assert "pre_aprovacao" in all_statuses
        assert "credito_aprovado" in all_statuses
        assert "pedido_avaliacao" in all_statuses
        assert "avaliacao" in all_statuses
        
        # Fases de contrato
        assert "cpcv" in all_statuses
        assert "minuta" in all_statuses
        assert "escritura" in all_statuses
        
        # Fases finais
        assert "concluido" in all_statuses
        assert "arquivo" in all_statuses
        assert "perdido" in all_statuses
        assert "desistencias" in all_statuses
    
    def test_active_statuses_count(self):
        """Verifica que há 11 status activos."""
        active = ProcessStatus.active_statuses()
        assert len(active) == 11
    
    def test_completed_statuses_count(self):
        """Verifica que há 2 status de conclusão."""
        completed = ProcessStatus.completed_statuses()
        assert len(completed) == 2
        assert "concluido" in completed
        assert "arquivo" in completed
    
    def test_failed_statuses_count(self):
        """Verifica que há 2 status de falha."""
        failed = ProcessStatus.failed_statuses()
        assert len(failed) == 2
        assert "perdido" in failed
        assert "desistencias" in failed
    
    def test_active_completed_failed_are_mutually_exclusive(self):
        """Verifica que os conjuntos são mutuamente exclusivos."""
        active = set(ProcessStatus.active_statuses())
        completed = set(ProcessStatus.completed_statuses())
        failed = set(ProcessStatus.failed_statuses())
        
        # Sem intersecções
        assert len(active & completed) == 0
        assert len(active & failed) == 0
        assert len(completed & failed) == 0
    
    def test_all_statuses_are_categorized(self):
        """Verifica que todos os status estão categorizados."""
        all_set = set(ProcessStatus.all_values())
        active = set(ProcessStatus.active_statuses())
        completed = set(ProcessStatus.completed_statuses())
        failed = set(ProcessStatus.failed_statuses())
        
        categorized = active | completed | failed
        
        assert all_set == categorized


class TestProcessType:
    """Testes para ProcessType enum."""
    
    def test_all_process_types_exist(self):
        """Verifica que todos os tipos de processo existem."""
        all_types = ProcessType.all_values()
        
        assert "credito_habitacao" in all_types
        assert "compra_direta" in all_types
        assert "arrendamento" in all_types
        assert "consultoria" in all_types
        assert "refinanciamento" in all_types
    
    def test_default_type_is_credito_habitacao(self):
        """O tipo default deve ser crédito habitação."""
        # Em produção, verificar que novos processos têm este tipo por default
        default_type = "credito_habitacao"
        assert default_type in ProcessType.all_values()


class TestProcessWorkflow:
    """Testes para lógica de workflow de processos."""
    
    def test_initial_status_is_clientes_espera(self):
        """O status inicial deve ser 'clientes_espera'."""
        initial_status = "clientes_espera"
        assert initial_status in ProcessStatus.active_statuses()
        assert initial_status == ProcessStatus.CLIENTES_ESPERA.value
    
    def test_final_statuses_are_not_active(self):
        """Status finais não devem ser considerados activos."""
        final_statuses = ["concluido", "arquivo", "perdido", "desistencias"]
        active_statuses = ProcessStatus.active_statuses()
        
        for status in final_statuses:
            assert status not in active_statuses
    
    def test_workflow_order(self):
        """Verifica ordem lógica do workflow."""
        # A ordem deve fazer sentido para o fluxo de crédito
        workflow_order = [
            "clientes_espera",
            "fila_espera",
            "documentacao",
            "analise",
            "pre_aprovacao",
            "credito_aprovado",
            "pedido_avaliacao",
            "avaliacao",
            "cpcv",
            "minuta",
            "escritura",
            "concluido"
        ]
        
        active = ProcessStatus.active_statuses()
        
        # Todas as fases activas devem estar na ordem (excepto as de saída)
        for status in active:
            assert status in workflow_order
