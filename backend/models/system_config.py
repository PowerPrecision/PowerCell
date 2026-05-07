"""
Modelo de dados para Configurações do Sistema
Permite configurar o sistema via interface de admin
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class StorageProvider(str, Enum):
    """Provedores de armazenamento suportados"""
    AWS_S3 = "aws_s3"
    ONEDRIVE = "onedrive"
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    LOCAL = "local"
    NONE = "none"


class EmailProvider(str, Enum):
    """Provedores de email suportados"""
    SMTP = "smtp"
    SENDGRID = "sendgrid"
    NONE = "none"


class AIProvider(str, Enum):
    """Provedores de IA suportados"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    EMERGENT = "emergent"


class IntegrationConfig(BaseModel):
    """Configuração de uma integração"""
    enabled: bool = False
    provider: Optional[str] = None
    credentials: Dict[str, Any] = {}
    settings: Dict[str, Any] = {}


class StorageConfig(BaseModel):
    """Configuração do serviço de armazenamento"""
    provider: StorageProvider = StorageProvider.NONE
    # AWS S3
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_bucket_name: Optional[str] = None
    aws_region: Optional[str] = None
    # OneDrive
    onedrive_client_id: Optional[str] = None
    onedrive_client_secret: Optional[str] = None
    onedrive_tenant_id: Optional[str] = None
    onedrive_redirect_uri: Optional[str] = None
    onedrive_shared_url: Optional[str] = None
    # Google Drive
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: Optional[str] = None
    google_folder_id: Optional[str] = None
    # Dropbox
    dropbox_app_key: Optional[str] = None
    dropbox_app_secret: Optional[str] = None
    dropbox_access_token: Optional[str] = None


class EmailConfig(BaseModel):
    """Configuração do serviço de email - Suporta duas contas"""
    provider: EmailProvider = EmailProvider.NONE
    
    # Conta Principal (Power Real Estate)
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = 465
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_ssl: bool = True
    imap_server: Optional[str] = None
    imap_port: Optional[int] = 993
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    
    # Conta Secundária (Precision Crédito)
    smtp_server_2: Optional[str] = None
    smtp_port_2: Optional[int] = 465
    smtp_user_2: Optional[str] = None
    smtp_password_2: Optional[str] = None
    smtp_use_ssl_2: bool = True
    imap_server_2: Optional[str] = None
    imap_port_2: Optional[int] = 993
    imap_user_2: Optional[str] = None
    imap_password_2: Optional[str] = None


class AIConfig(BaseModel):
    """Configuração do serviço de IA"""
    provider: AIProvider = AIProvider.OPENAI
    api_key: Optional[str] = None
    model: Optional[str] = "gpt-4o-mini"
    max_tokens: int = 4000


class TrelloConfig(BaseModel):
    """Configuração do Trello"""
    enabled: bool = False
    api_key: Optional[str] = None
    api_token: Optional[str] = None
    board_id: Optional[str] = None
    webhook_base_url: Optional[str] = None


class ReportFrequency(str, Enum):
    """Frequência de envio do relatório de IA"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    DISABLED = "disabled"


class AIReportConfig(BaseModel):
    """Configuração do relatório automático de IA"""
    enabled: bool = True
    frequency: ReportFrequency = ReportFrequency.WEEKLY
    send_day: int = 0  # 0=Segunda, 1=Terça, ... 6=Domingo (para semanal)
    send_hour: int = 9  # Hora do envio (0-23)
    recipients_type: str = "admins"  # "admins", "all_staff", "custom"
    custom_recipients: List[str] = []  # Lista de user IDs se recipients_type="custom"
    include_insights: bool = True
    include_charts: bool = True


class CreditServicesConfig(BaseModel):
    """Configuração dos serviços de crédito"""
    primary_provider: str = "hcpro"  # "hcpro", "decisoes_e_solucoes", "doutorfinancas", etc.
    enabled_providers: List[str] = ["hcpro", "bcp"]
    auto_assign_mediator: bool = True
    default_interest_rate: Optional[float] = None
    max_loan_to_value: float = 90.0
    min_income_ratio: float = 35.0
    default_term_years: int = 30
    simulation_validity_days: int = 30
    
    # HCPro
    hcpro_url: Optional[str] = None
    hcpro_user: Optional[str] = None
    hcpro_password: Optional[str] = None
    
    # Decisões e Soluções
    decisoes_url: Optional[str] = None
    decisoes_user: Optional[str] = None
    decisoes_password: Optional[str] = None
    
    # Doutor Finanças
    doutorfinancas_url: Optional[str] = None
    doutorfinancas_user: Optional[str] = None
    doutorfinancas_password: Optional[str] = None
    
    # Portal Personalizado
    custom_portal_name: Optional[str] = None
    custom_portal_url: Optional[str] = None
    custom_portal_user: Optional[str] = None
    custom_portal_password: Optional[str] = None
    
    # Serviço secundário
    secondary_provider: Optional[str] = None


class SystemSettings(BaseModel):
    """Configurações gerais do sistema"""
    company_name: str = "Power Real Estate"
    company_subtitle: str = "& Precision Crédito"
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: str = "#0F766E"
    secondary_color: str = "#FCD34D"
    timezone: str = "Europe/Lisbon"
    language: str = "pt-PT"
    currency: str = "EUR"
    date_format: str = "dd/MM/yyyy"


class DocumentRecipientsConfig(BaseModel):
    """Configuração de destinatários para envio de documentação"""
    enabled: bool = False
    recipients: Optional[str] = None  # JSON string com lista de destinatários
    email_template: Optional[str] = None  # Template do email com variáveis
    default_to: Optional[str] = None  # Email principal (TO) — mantido para compatibilidade
    default_to_name: Optional[str] = None  # Nome do destinatário TO
    default_to_emails: Optional[str] = None  # JSON string com lista de emails TO (múltiplos destinatários principais)


class DSTIConfig(BaseModel):
    """Configuração da análise DSTI automática"""
    enabled: bool = True
    # Limiar para alerta de risco elevado (percentagem, default 40%)
    high_risk_threshold: float = 40.0
    # Limiar para alerta de risco muito elevado (percentagem, default 50% - limite BdP)
    critical_risk_threshold: float = 50.0


class AutoDraftConfig(BaseModel):
    """Configuração de rascunhos automáticos de e-mails"""
    enabled: bool = False
    base_prompt: Optional[str] = None  # Prompt base para geração de rascunhos pela IA
    eligible_doc_types: List[str] = [
        "irs",
        "recibo_vencimento",
        "declaracao_irs",
        "extrato_bancario",
        "mapa_responsabilidades",
        "comprovativo_morada",
        "cc",
        "caderneta_predial",
        "certidao_teor",
        "licenca_habitacao",
    ]


class AuditTrailConfig(BaseModel):
    """Configuração do sistema de auditoria (Audit Trail)"""
    enabled: bool = True
    log_ip_address: bool = True
    log_ai_approvals: bool = True
    require_reason_for_critical_fields: bool = True
    critical_fields: List[str] = ["financial_data", "credit_data", "status"]
    retention_days: int = 365


class SystemSMTPConfig(BaseModel):
    """Configuração de email transacional do sistema (Bloco A).

    Suporta dois modos de envio:
      1. Resend API (recomendado) — usa resend_api_key para enviar via HTTP.
         Não requer host/porta/username. Funciona em ambientes como Render
         que bloqueiam portas SMTP de saída.
      2. SMTP directo (legado) — usa smtp_host/smtp_port/smtp_username/smtp_password.
         Mantido para compatibilidade mas descontinuado.

    NOTA: Emails enviados via esta configuração são ESTRITAMENTE unidirecionais (one-way).
    Nenhum cabeçalho Reply-To é injetado — por política administrativa.
    """
    # === Resend API (recomendado) ===
    resend_api_key: Optional[str] = None

    # === Campos de remetente (usados por ambos os modos) ===
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None  # Nome do remetente (ex: Power Real Estate)

    # === SMTP directo (legado — mantido para compatibilidade) ===
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True

    # === Assinatura de Email ===
    email_signature: Optional[str] = None  # HTML da assinatura (anexada automaticamente)


class SystemWebmailConfig(BaseModel):
    """Configuração de conta global de indexação (Bloco C) - Webmail partilhado"""
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993
    email_user: Optional[str] = None
    app_password: Optional[str] = None


class SystemConfig(BaseModel):
    """Configuração completa do sistema"""
    storage: StorageConfig = StorageConfig()
    email: EmailConfig = EmailConfig()
    ai: AIConfig = AIConfig()
    trello: TrelloConfig = TrelloConfig()
    settings: SystemSettings = SystemSettings()
    credit_services: CreditServicesConfig = CreditServicesConfig()
    document_recipients: DocumentRecipientsConfig = DocumentRecipientsConfig()
    dsti_analysis: DSTIConfig = DSTIConfig()
    auto_draft: AutoDraftConfig = AutoDraftConfig()
    audit_trail: AuditTrailConfig = AuditTrailConfig()
    system_smtp: SystemSMTPConfig = SystemSMTPConfig()
    system_webmail: SystemWebmailConfig = SystemWebmailConfig()
    setup_completed: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    """Request para actualizar configuração"""
    section: str  # "storage", "email", "ai", "trello", "settings"
    data: Dict[str, Any]


class ConfigField(BaseModel):
    """Definição de um campo de configuração para o frontend"""
    key: str
    label: str
    type: str  # "text", "password", "number", "select", "boolean", "textarea"
    required: bool = False
    placeholder: Optional[str] = None
    options: Optional[List[Dict[str, str]]] = None  # Para select
    help_text: Optional[str] = None
    depends_on: Optional[Dict[str, Any]] = None  # Mostrar apenas se outra opção tiver valor X
