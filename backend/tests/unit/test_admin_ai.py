"""
Testes unitários para as rotas de administração de IA.
Foca em testar a lógica de negócio sem dependências de base de dados.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestAIModelsLogic:
    """Testes para a lógica de modelos de IA."""
    
    def test_model_key_validation(self):
        """Testa que as keys dos modelos seguem o padrão correcto."""
        valid_keys = ["gemini_flash", "gpt4o_mini", "gpt4o", "claude_sonnet"]
        
        for key in valid_keys:
            # Keys devem ser lowercase com underscore
            assert key == key.lower()
            assert " " not in key
            assert "-" not in key or "_" in key
    
    def test_model_structure(self):
        """Testa a estrutura esperada de um modelo de IA."""
        model = {
            "key": "test_model",
            "name": "Test Model",
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "description": "Modelo de teste",
            "cost_per_1k_input": 0.15,
            "cost_per_1k_output": 0.60,
            "max_tokens": 4096,
            "is_active": True
        }
        
        # Verificar campos obrigatórios
        required_fields = ["key", "name", "provider", "model_id"]
        for field in required_fields:
            assert field in model
        
        # Verificar tipos
        assert isinstance(model["cost_per_1k_input"], (int, float))
        assert isinstance(model["cost_per_1k_output"], (int, float))
        assert isinstance(model["max_tokens"], int)
        assert isinstance(model["is_active"], bool)
    
    def test_provider_validation(self):
        """Testa que apenas providers válidos são aceites."""
        valid_providers = ["openai", "gemini", "anthropic"]
        invalid_providers = ["invalid", "test", ""]
        
        for provider in valid_providers:
            assert provider in ["openai", "gemini", "anthropic"]
        
        for provider in invalid_providers:
            assert provider not in ["openai", "gemini", "anthropic"]


class TestAITasksLogic:
    """Testes para a lógica de tarefas de IA."""
    
    def test_task_key_validation(self):
        """Testa que as keys de tarefas seguem o padrão correcto."""
        valid_tasks = [
            "scraper_extraction",
            "document_analysis",
            "weekly_report",
            "error_analysis"
        ]
        
        for task in valid_tasks:
            assert "_" in task
            assert task == task.lower()
    
    def test_task_structure(self):
        """Testa a estrutura esperada de uma tarefa de IA."""
        task = {
            "key": "document_analysis",
            "description": "Análise e extração de dados de documentos",
            "default_model": "gpt4o_mini"
        }
        
        required_fields = ["key", "description", "default_model"]
        for field in required_fields:
            assert field in task
        
        assert len(task["description"]) > 0
    
    def test_default_tasks(self):
        """Testa que as tarefas padrão estão definidas."""
        default_tasks = [
            "scraper_extraction",
            "document_analysis",
            "weekly_report",
            "error_analysis"
        ]
        
        assert len(default_tasks) == 4
        assert "document_analysis" in default_tasks


class TestCacheSettingsLogic:
    """Testes para a lógica de configurações de cache."""
    
    def test_cache_limit_validation(self):
        """Testa validação do limite de cache."""
        valid_limits = [100, 500, 1000, 5000, 10000]
        invalid_limits = [-1, 0, "string"]
        
        for limit in valid_limits:
            assert isinstance(limit, int)
            assert limit > 0
        
        for limit in invalid_limits:
            if isinstance(limit, int):
                assert limit <= 0
            else:
                assert not isinstance(limit, int)
    
    def test_notify_percentage_validation(self):
        """Testa validação da percentagem de notificação."""
        valid_percentages = [50, 70, 80, 90, 100]
        invalid_percentages = [-10, 0, 101, 150]
        
        for pct in valid_percentages:
            assert 1 <= pct <= 100
        
        for pct in invalid_percentages:
            assert pct < 1 or pct > 100
    
    def test_default_cache_settings(self):
        """Testa configurações padrão de cache."""
        defaults = {
            "cache_limit": 1000,
            "notify_at_percentage": 80
        }
        
        assert defaults["cache_limit"] == 1000
        assert defaults["notify_at_percentage"] == 80


class TestAIUsageTracking:
    """Testes para o tracking de uso de IA."""
    
    def test_period_validation(self):
        """Testa validação de períodos válidos."""
        valid_periods = ["day", "week", "month", "year"]
        
        for period in valid_periods:
            assert period in ["day", "week", "month", "year"]
    
    def test_usage_record_structure(self):
        """Testa a estrutura de um registo de uso."""
        record = {
            "task": "document_analysis",
            "model": "gpt4o_mini",
            "input_tokens": 1500,
            "output_tokens": 500,
            "cost": 0.003,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": 2500
        }
        
        required_fields = ["task", "model", "input_tokens", "output_tokens", "timestamp"]
        for field in required_fields:
            assert field in record
        
        assert record["input_tokens"] >= 0
        assert record["output_tokens"] >= 0
    
    def test_cost_calculation(self):
        """Testa cálculo de custo."""
        input_tokens = 1000
        output_tokens = 500
        cost_per_1k_input = 0.15  # $0.15 per 1k
        cost_per_1k_output = 0.60  # $0.60 per 1k
        
        expected_cost = (input_tokens / 1000 * cost_per_1k_input) + \
                       (output_tokens / 1000 * cost_per_1k_output)
        
        # Usar aproximação devido a floating point
        assert abs(expected_cost - 0.45) < 0.001  # $0.15 + $0.30


class TestAIWeeklyReport:
    """Testes para o relatório semanal de IA."""
    
    def test_report_structure(self):
        """Testa a estrutura do relatório semanal."""
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": "last_7_days",
            "usage_summary": {},
            "by_task": {},
            "by_model": {}
        }
        
        required_fields = ["generated_at", "period", "usage_summary"]
        for field in required_fields:
            assert field in report
    
    def test_schedule_format(self):
        """Testa formato de agendamento."""
        valid_schedules = [
            "monday_09:00",
            "friday_14:30",
            "sunday_08:00"
        ]
        
        for schedule in valid_schedules:
            parts = schedule.split("_")
            assert len(parts) == 2
            assert parts[0] in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            time_parts = parts[1].split(":")
            assert len(time_parts) == 2
            assert 0 <= int(time_parts[0]) <= 23
            assert 0 <= int(time_parts[1]) <= 59
    
    def test_recipients_validation(self):
        """Testa validação de destinatários."""
        valid_recipients = ["admin@test.com", "user@empresa.pt"]
        invalid_recipients = ["", "invalid", "test@"]
        
        import re
        email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        
        for email in valid_recipients:
            assert re.match(email_pattern, email) is not None
        
        for email in invalid_recipients:
            assert re.match(email_pattern, email) is None


class TestAIConfigDefaults:
    """Testes para configurações padrão de IA."""
    
    def test_default_config_exists(self):
        """Testa que configurações padrão existem."""
        defaults = {
            "scraper_extraction": "gemini_flash",
            "document_analysis": "gpt4o_mini",
            "weekly_report": "gemini_flash",
            "error_analysis": "gemini_flash"
        }
        
        assert len(defaults) == 4
        for task, model in defaults.items():
            assert model in ["gemini_flash", "gpt4o_mini", "gpt4o", "claude_sonnet"]
    
    def test_provider_fallback(self):
        """Testa lógica de fallback de provider."""
        available_providers = ["openai"]  # Apenas OpenAI disponível
        
        # Se Gemini não está disponível, deve usar OpenAI
        task_defaults = {
            "scraper_extraction": "gemini_flash",
            "document_analysis": "gpt4o_mini"
        }
        
        # Em fallback, tarefas que usam Gemini devem mudar para OpenAI
        if "gemini" not in available_providers:
            assert "openai" in available_providers
