"""
====================================================================
ENUMS CENTRALIZADOS - CREDITOIMO
====================================================================
Enumerações centralizadas para todo o sistema.
Evita magic strings e garante consistência.
====================================================================
"""
from enum import Enum
from typing import List


class ProcessStatus(str, Enum):
    """
    Status do processo no workflow de 14 fases.
    Valores correspondem aos nomes das colunas do Kanban.
    """
    # Fase 1-3: Início
    CLIENTES_ESPERA = "clientes_espera"
    DOCUMENTACAO = "documentacao"
    ANALISE = "analise"
    
    # Fase 4-7: Aprovação
    PRE_APROVACAO = "pre_aprovacao"
    CREDITO_APROVADO = "credito_aprovado"
    PEDIDO_AVALIACAO = "pedido_avaliacao"
    AVALIACAO = "avaliacao"
    
    # Fase 8-10: Contrato
    CPCV = "cpcv"
    MINUTA = "minuta"
    ESCRITURA = "escritura"
    
    # Fase 11-14: Conclusão
    CONCLUIDO = "concluido"
    ARQUIVO = "arquivo"
    PERDIDO = "perdido"
    DESISTENCIAS = "desistencias"

    # Fila de Espera — sem indexador disponível
    FILA_ESPERA = "fila_espera"
    
    @classmethod
    def active_statuses(cls) -> List[str]:
        """Retorna status que representam processos activos."""
        return [
            cls.CLIENTES_ESPERA.value,
            cls.DOCUMENTACAO.value,
            cls.ANALISE.value,
            cls.PRE_APROVACAO.value,
            cls.CREDITO_APROVADO.value,
            cls.PEDIDO_AVALIACAO.value,
            cls.AVALIACAO.value,
            cls.CPCV.value,
            cls.MINUTA.value,
            cls.ESCRITURA.value,
            cls.FILA_ESPERA.value,
        ]
    
    @classmethod
    def completed_statuses(cls) -> List[str]:
        """Retorna status que representam processos concluídos."""
        return [cls.CONCLUIDO.value, cls.ARQUIVO.value]
    
    @classmethod
    def failed_statuses(cls) -> List[str]:
        """Retorna status que representam processos falhados/perdidos."""
        return [cls.PERDIDO.value, cls.DESISTENCIAS.value]
    
    @classmethod
    def all_values(cls) -> List[str]:
        """Retorna todos os valores possíveis."""
        return [status.value for status in cls]


class ProcessType(str, Enum):
    """Tipo de processo/serviço."""
    CREDITO_HABITACAO = "credito_habitacao"
    CREDITO_PESSOAL = "credito_pessoal"
    COMPRA_DIRETA = "compra_direta"
    ARRENDAMENTO = "arrendamento"
    CONSULTORIA = "consultoria"
    REFINANCIAMENTO = "refinanciamento"
    SEGUROS = "seguros"
    OUTRO = "outro"
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [t.value for t in cls]


class UserRoleEnum(str, Enum):
    """
    Roles de utilizador do sistema — lista DEFINITIVA de 8 perfis.
    Sincronizado com models/auth.py.
    
    NOTA: 'mediador' e 'consultor_intermediario' foram removidos.
    """
    CLIENTE = "cliente"
    CONSULTOR = "consultor"
    INTERMEDIARIO = "intermediario"
    ADMINISTRATIVO = "administrativo"
    INDEXACAO = "indexacao"
    DIRETOR = "diretor"
    CEO = "ceo"
    ADMIN = "admin"
    PARCEIRO = "parceiro"
    
    @classmethod
    def staff_roles(cls) -> List[str]:
        """Roles que são staff (não cliente e não parceiro - utilizador fantasma)."""
        return [r.value for r in cls if r not in [cls.CLIENTE, cls.PARCEIRO]]
    
    @classmethod
    def management_roles(cls) -> List[str]:
        """Roles de gestão."""
        return [cls.DIRETOR.value, cls.CEO.value, cls.ADMIN.value]
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [r.value for r in cls]


class NotificationType(str, Enum):
    """Tipos de notificação do sistema."""
    # Processo
    PROCESS_ASSIGNED = "process_assigned"
    PROCESS_STATUS_CHANGED = "process_status_changed"
    PROCESS_CREATED = "process_created"
    PROCESS_UPDATED = "process_updated"
    
    # Documentos
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_EXPIRY_WARNING = "document_expiry_warning"
    DOCUMENT_EXPIRY_WATCHDOG = "document_expiry_watchdog"
    
    # Tarefas
    TASK_ASSIGNED = "task_assigned"
    TASK_DUE_SOON = "task_due_soon"
    TASK_OVERDUE = "task_overdue"
    TASK_COMPLETED = "task_completed"
    
    # Prazos
    DEADLINE_APPROACHING = "deadline_approaching"
    DEADLINE_MISSED = "deadline_missed"
    
    # Emails
    EMAIL_RECEIVED = "email_received"
    EMAIL_ASSOCIATED = "email_associated"
    
    # Sistema
    SYSTEM_ALERT = "system_alert"
    SYSTEM_ERROR = "system_error"
    JOB_STUCK = "job_stuck"
    
    # Chat
    CHAT_MESSAGE = "chat_message"
    CHAT_MENTION = "chat_mention"
    
    # IA
    AI_ANALYSIS_COMPLETE = "ai_analysis_complete"
    AI_CONFLICT_DETECTED = "ai_conflict_detected"
    
    @classmethod
    def high_priority_types(cls) -> List[str]:
        """Notificações de alta prioridade."""
        return [
            cls.SYSTEM_ERROR.value,
            cls.DOCUMENT_EXPIRY_WARNING.value,
            cls.DEADLINE_MISSED.value,
            cls.TASK_OVERDUE.value,
        ]
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [n.value for n in cls]


class LeadStatus(str, Enum):
    """Status de leads no Kanban de visitas."""
    NOVO = "novo"
    CONTACTADO = "contactado"
    VISITA_AGENDADA = "visita_agendada"
    VISITADO = "visitado"
    PROPOSTA = "proposta"
    GANHO = "ganho"
    PERDIDO = "perdido"
    
    @classmethod
    def active_statuses(cls) -> List[str]:
        return [cls.NOVO.value, cls.CONTACTADO.value, cls.VISITA_AGENDADA.value, cls.VISITADO.value, cls.PROPOSTA.value]
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [s.value for s in cls]


class DocumentCategory(str, Enum):
    """Categorias de documentos detectadas pela IA."""
    IDENTIFICACAO = "Identificação"
    RENDIMENTOS = "Rendimentos"
    EMPREGO = "Emprego"
    BANCARIOS = "Bancários"
    IMOVEL = "Imóvel"
    CONTRATOS = "Contratos"
    FISCAIS = "Fiscais"
    SIMULACOES = "Simulações"
    MINUTAS = "Minutas"
    INDEX = "Index"
    OUTROS = "Outros"
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [c.value for c in cls]


class ActivityType(str, Enum):
    """Tipos de actividade para histórico."""
    PROCESS_CREATED = "process_created"
    PROCESS_UPDATED = "process_updated"
    STATUS_CHANGED = "status_changed"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_DELETED = "document_deleted"
    NOTE_ADDED = "note_added"
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    ASSIGNMENT_CHANGED = "assignment_changed"
    AI_ANALYSIS = "ai_analysis"
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [a.value for a in cls]


class TaskPriority(str, Enum):
    """Prioridade de tarefas."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [p.value for p in cls]


class EmailStatus(str, Enum):
    """Status de email no sistema."""
    RECEIVED = "received"
    PROCESSED = "processed"
    ASSOCIATED = "associated"
    FAILED = "failed"
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [s.value for s in cls]


class FeeType(str, Enum):
    """Tipo de comissão/honorário."""
    FIXED = "fixed"
    PERCENTAGE = "percentage"
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [t.value for t in cls]


class FinanceStatus(str, Enum):
    """Status do registo financeiro do processo."""
    PENDING = "pending"
    INVOICED = "invoiced"
    PAID = "paid"
    CANCELLED = "cancelled"
    
    @classmethod
    def active_statuses(cls) -> List[str]:
        """Status que representam registos activos (não cancelados)."""
        return [cls.PENDING.value, cls.INVOICED.value, cls.PAID.value]
    
    @classmethod
    def completed_statuses(cls) -> List[str]:
        """Status que representam registos finalizados."""
        return [cls.PAID.value, cls.CANCELLED.value]
    
    @classmethod
    def all_values(cls) -> List[str]:
        return [s.value for s in cls]


# Exportar todos os enums
__all__ = [
    "ProcessStatus",
    "ProcessType",
    "UserRoleEnum",
    "NotificationType",
    "LeadStatus",
    "DocumentCategory",
    "ActivityType",
    "TaskPriority",
    "EmailStatus",
    "FeeType",
    "FinanceStatus",
]
