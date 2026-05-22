"""
Rotas para Configurações do Sistema
Permite ao admin configurar o sistema via interface
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from services.auth import get_current_user, require_roles
from models.auth import UserRole
from models.system_config import (
    SystemConfig, ConfigUpdateRequest, ConfigField,
    StorageProvider, EmailProvider, AIProvider
)
from services.system_config import (
    get_system_config, update_config_section, 
    mark_setup_completed, invalidate_config_cache,
    list_available_companies
)

router = APIRouter(prefix="/system-config", tags=["System Configuration"])
logger = logging.getLogger(__name__)


# Definição dos campos de configuração para o frontend
CONFIG_FIELDS = {
    "storage": {
        "title": "Armazenamento de Ficheiros",
        "description": "Configurar o serviço para guardar documentos dos clientes",
        "fields": [
            ConfigField(
                key="provider",
                label="Serviço de Armazenamento",
                type="select",
                required=True,
                options=[
                    {"value": "none", "label": "Nenhum (Desactivado)"},
                    {"value": "aws_s3", "label": "Amazon S3 (Recomendado)"},
                    {"value": "onedrive", "label": "Microsoft OneDrive"},
                    {"value": "google_drive", "label": "Google Drive"},
                    {"value": "dropbox", "label": "Dropbox"},
                ],
                help_text="Escolha onde guardar os documentos dos clientes"
            ),
            # AWS S3
            ConfigField(
                key="aws_access_key_id",
                label="AWS Access Key ID",
                type="text",
                placeholder="AKIA...",
                depends_on={"provider": "aws_s3"},
                help_text="ID da chave de acesso AWS"
            ),
            ConfigField(
                key="aws_secret_access_key",
                label="AWS Secret Access Key",
                type="password",
                depends_on={"provider": "aws_s3"},
                help_text="Chave secreta AWS"
            ),
            ConfigField(
                key="aws_bucket_name",
                label="Nome do Bucket S3",
                type="text",
                placeholder="meu-bucket-documentos",
                depends_on={"provider": "aws_s3"},
                help_text="Nome do bucket S3 para documentos"
            ),
            ConfigField(
                key="aws_region",
                label="Região AWS",
                type="text",
                placeholder="eu-west-1",
                depends_on={"provider": "aws_s3"},
                help_text="Região do bucket S3 (ex: eu-west-1, us-east-1)"
            ),
            # OneDrive
            ConfigField(
                key="onedrive_client_id",
                label="Client ID (OneDrive)",
                type="text",
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                depends_on={"provider": "onedrive"},
                help_text="ID da aplicação Azure AD"
            ),
            ConfigField(
                key="onedrive_client_secret",
                label="Client Secret (OneDrive)",
                type="password",
                depends_on={"provider": "onedrive"},
                help_text="Segredo da aplicação Azure AD"
            ),
            ConfigField(
                key="onedrive_shared_url",
                label="URL da Pasta Partilhada (OneDrive)",
                type="text",
                placeholder="https://onedrive.live.com/?...",
                depends_on={"provider": "onedrive"},
                help_text="URL de partilha da pasta raiz dos clientes"
            ),
            # Google Drive
            ConfigField(
                key="google_client_id",
                label="Client ID (Google)",
                type="text",
                depends_on={"provider": "google_drive"},
                help_text="ID do cliente OAuth do Google Cloud"
            ),
            ConfigField(
                key="google_client_secret",
                label="Client Secret (Google)",
                type="password",
                depends_on={"provider": "google_drive"},
                help_text="Segredo do cliente OAuth"
            ),
            ConfigField(
                key="google_folder_id",
                label="ID da Pasta Raiz (Google Drive)",
                type="text",
                depends_on={"provider": "google_drive"},
                help_text="ID da pasta no Google Drive onde estão os clientes"
            ),
        ]
    },
    "email": {
        "title": "Configuração de Email",
        "description": "Configurar servidores de email para envio e recepção (2 contas suportadas)",
        "fields": [
            ConfigField(
                key="provider",
                label="Tipo de Servidor",
                type="select",
                options=[
                    {"value": "none", "label": "Desactivado"},
                    {"value": "smtp", "label": "SMTP/IMAP Tradicional"},
                ],
            ),
            # === CONTA 1: POWER REAL ESTATE ===
            ConfigField(
                key="_divider_power",
                label="Conta 1: Power Real Estate (geral@powerealestate.pt)",
                type="divider",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_server",
                label="Servidor SMTP",
                type="text",
                placeholder="webmail2.hcpro.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_port",
                label="Porta SMTP",
                type="number",
                placeholder="465",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_user",
                label="Email/Utilizador SMTP",
                type="text",
                placeholder="geral@powerealestate.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_password",
                label="Password SMTP",
                type="password",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_server",
                label="Servidor IMAP",
                type="text",
                placeholder="webmail2.hcpro.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_port",
                label="Porta IMAP",
                type="number",
                placeholder="993",
                depends_on={"provider": "smtp"},
            ),
            # === CONTA 2: PRECISION CRÉDITO ===
            ConfigField(
                key="_divider_precision",
                label="Conta 2: Precision Crédito (geral@precisioncredito.pt)",
                type="divider",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_server_2",
                label="Servidor SMTP (Precision)",
                type="text",
                placeholder="mail.precisioncredito.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_port_2",
                label="Porta SMTP (Precision)",
                type="number",
                placeholder="465",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_user_2",
                label="Email/Utilizador SMTP (Precision)",
                type="text",
                placeholder="geral@precisioncredito.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_password_2",
                label="Password SMTP (Precision)",
                type="password",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_server_2",
                label="Servidor IMAP (Precision)",
                type="text",
                placeholder="mail.precisioncredito.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_port_2",
                label="Porta IMAP (Precision)",
                type="number",
                placeholder="993",
                depends_on={"provider": "smtp"},
            ),
        ]
    },
    "ai": {
        "title": "Inteligência Artificial",
        "description": "Configurar o serviço de IA para análise de documentos",
        "fields": [
            ConfigField(
                key="provider",
                label="Fornecedor de IA",
                type="select",
                options=[
                    {"value": "openai", "label": "OpenAI"},
                    {"value": "emergent", "label": "Emergent"},
                ],
            ),
            ConfigField(
                key="api_key",
                label="Chave API",
                type="password",
                help_text="Chave da API do fornecedor escolhido",
            ),
            ConfigField(
                key="model",
                label="Modelo",
                type="select",
                options=[
                    {"value": "gpt-4o-mini", "label": "GPT-4o Mini (Rápido e económico)"},
                    {"value": "gpt-4o", "label": "GPT-4o (Mais preciso)"},
                ],
            ),
        ]
    },
    "credit_services": {
        "title": "Serviços de Crédito Imobiliário",
        "description": "Configurar serviços parceiros para envio de simulações",
        "fields": [
            ConfigField(
                key="primary_provider",
                label="Serviço Principal",
                type="select",
                required=True,
                options=[
                    {"value": "hcpro", "label": "HCPro (Webmail2)"},
                    {"value": "decisoes_e_solucoes", "label": "Decisões e Soluções"},
                    {"value": "doutorfinancas", "label": "Doutor Finanças"},
                    {"value": "maxfinance", "label": "MaxFinance"},
                    {"value": "multiplo", "label": "Múltiplo / UCI"},
                    {"value": "credibom", "label": "Credibom"},
                    {"value": "custom", "label": "Personalizado"},
                ],
                help_text="Escolha o serviço principal para simulações de crédito"
            ),
            ConfigField(
                key="hcpro_url",
                label="URL HCPro",
                type="text",
                placeholder="https://webmail2.hcpro.pt/Mondo/lang/sys/login.aspx",
                depends_on={"primary_provider": "hcpro"},
            ),
            ConfigField(
                key="hcpro_user",
                label="Utilizador HCPro",
                type="text",
                depends_on={"primary_provider": "hcpro"},
            ),
            ConfigField(
                key="hcpro_password",
                label="Password HCPro",
                type="password",
                depends_on={"primary_provider": "hcpro"},
            ),
            ConfigField(
                key="decisoes_url",
                label="URL Portal Decisões e Soluções",
                type="text",
                placeholder="https://portal.decisoes-e-solucoes.pt",
                depends_on={"primary_provider": "decisoes_e_solucoes"},
            ),
            ConfigField(
                key="decisoes_user",
                label="Utilizador D&S",
                type="text",
                depends_on={"primary_provider": "decisoes_e_solucoes"},
            ),
            ConfigField(
                key="decisoes_password",
                label="Password D&S",
                type="password",
                depends_on={"primary_provider": "decisoes_e_solucoes"},
            ),
            ConfigField(
                key="doutorfinancas_url",
                label="URL Doutor Finanças",
                type="text",
                placeholder="https://backoffice.dfredes.com",
                depends_on={"primary_provider": "doutorfinancas"},
            ),
            ConfigField(
                key="doutorfinancas_user",
                label="Utilizador DF",
                type="text",
                depends_on={"primary_provider": "doutorfinancas"},
            ),
            ConfigField(
                key="doutorfinancas_password",
                label="Password DF",
                type="password",
                depends_on={"primary_provider": "doutorfinancas"},
            ),
            ConfigField(
                key="custom_portal_name",
                label="Nome do Portal",
                type="text",
                placeholder="Nome do serviço personalizado",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="custom_portal_url",
                label="URL do Portal",
                type="text",
                placeholder="https://...",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="custom_portal_user",
                label="Utilizador",
                type="text",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="custom_portal_password",
                label="Password",
                type="password",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="secondary_provider",
                label="Serviço Secundário (Opcional)",
                type="select",
                options=[
                    {"value": "none", "label": "Nenhum"},
                    {"value": "hcpro", "label": "HCPro"},
                    {"value": "decisoes_e_solucoes", "label": "Decisões e Soluções"},
                    {"value": "doutorfinancas", "label": "Doutor Finanças"},
                    {"value": "maxfinance", "label": "MaxFinance"},
                ],
                help_text="Serviço alternativo para comparação de propostas"
            ),
        ]
    },
    "trello": {
        "title": "Integração Trello",
        "description": "Sincronizar processos com um quadro Trello",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Trello",
                type="boolean",
            ),
            ConfigField(
                key="api_key",
                label="API Key",
                type="text",
                depends_on={"enabled": True},
                help_text="Obter em https://trello.com/power-ups/admin"
            ),
            ConfigField(
                key="api_token",
                label="API Token",
                type="password",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="board_id",
                label="ID do Quadro",
                type="text",
                depends_on={"enabled": True},
                help_text="ID do quadro Trello a sincronizar"
            ),
        ]
    },
    "settings": {
        "title": "Definições Gerais",
        "description": "Personalizar a aparência e comportamento do sistema",
        "fields": [
            ConfigField(
                key="company_name",
                label="Nome da Empresa",
                type="text",
                required=True,
            ),
            ConfigField(
                key="company_subtitle",
                label="Subtítulo",
                type="text",
            ),
            ConfigField(
                key="company_address",
                label="Morada da Empresa",
                type="text",
                help_text="Usada no template RGPD como {{MORADA_EMPRESA}}",
            ),
            ConfigField(
                key="company_phone",
                label="Telefone/Email da Empresa",
                type="text",
                help_text="Usada no template RGPD como {{CONTACTO_EMPRESA}}",
            ),
            ConfigField(
                key="primary_color",
                label="Cor Principal",
                type="text",
                placeholder="#0F766E",
                help_text="Código hexadecimal da cor"
            ),
            ConfigField(
                key="timezone",
                label="Fuso Horário",
                type="select",
                options=[
                    {"value": "Europe/Lisbon", "label": "Lisboa (Portugal)"},
                    {"value": "Europe/London", "label": "Londres (UK)"},
                    {"value": "Atlantic/Azores", "label": "Açores"},
                ],
            ),
            ConfigField(
                key="language",
                label="Idioma",
                type="select",
                options=[
                    {"value": "pt-PT", "label": "Português (Portugal)"},
                    {"value": "en-GB", "label": "English (UK)"},
                ],
            ),
            ConfigField(
                key="_divider_security",
                label="Segurança e Permissões",
                type="divider",
            ),
            ConfigField(
                key="allow_excel_export",
                label="Permitir Exportação para Excel (Global)",
                type="boolean",
                help_text="Quando desativado, os botões de exportação para Excel ficam ocultos para todos os utilizadores excepto Admin e CEO",
            ),
        ]
    },
    "document_recipients": {
        "title": "Destinatários de Documentação",
        "description": "Configurar balcões/bancos para envio de documentação de clientes",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Envio de Documentação",
                type="boolean",
                help_text="Permitir envio de documentação para balcões"
            ),
            ConfigField(
                key="recipients",
                label="Lista de Destinatários (JSON)",
                type="textarea",
                placeholder='[{"name": "Millennium BCP", "email": "millennium@exemplo.pt", "active": true}, ...]',
                help_text="Lista de balcões/bancos em formato JSON. Cada entrada deve ter: name, email, active (true/false)"
            ),
            ConfigField(
                key="email_template",
                label="Template de Email",
                type="textarea",
                placeholder="Prezados,\n\nSegue em anexo a documentação do cliente {client_name}...",
                help_text="Template do email. Variáveis disponíveis: {client_name}, {client_nif}, {process_number}, {documents_list}"
            ),
            ConfigField(
                key="default_to",
                label="Destinatário TO (Email Principal)",
                type="text",
                placeholder="geral@powerealestate.pt",
                help_text="Email principal que aparecerá no campo TO"
            ),
            ConfigField(
                key="default_to_name",
                label="Nome do Destinatário TO",
                type="text",
                placeholder="Power Real Estate",
                help_text="Nome do destinatário principal"
            ),
            ConfigField(
                key="default_to_emails",
                label="Emails TO Múltiplos (JSON)",
                type="textarea",
                placeholder='["geral@powerealestate.pt", "geral@precisioncredito.pt"]',
                help_text="Lista de emails TO em formato JSON. Gerido automaticamente pelo formulário de Destinatários."
            ),
        ]
    },
    "dsti_analysis": {
        "title": "Análise DSTI Automática",
        "description": "Cálculo automático da taxa de esforço (DSTI) a partir dos dados extraídos pela IA. Sinaliza instantaneamente processos de alto risco.",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Análise DSTI Automática",
                type="boolean",
                help_text="Calcula automaticamente o DSTI e mostra alertas de risco nos processos"
            ),
            ConfigField(
                key="high_risk_threshold",
                label="Limiar de Risco Elevado (%)",
                type="number",
                placeholder="40",
                help_text="DSTI acima deste valor é considerado de alto risco (default: 40%)"
            ),
            ConfigField(
                key="critical_risk_threshold",
                label="Limiar de Risco Crítico (%)",
                type="number",
                placeholder="50",
                help_text="DSTI acima deste valor ultrapassa o limite do Banco de Portugal (default: 50%)"
            ),
        ]
    },
    "auto_draft": {
        "title": "Rascunhos Automáticos de E-mails",
        "description": "Gerar automaticamente rascunhos de e-mails solicitando documentos em falta",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Rascunhos Automáticos",
                type="boolean",
                help_text="Gera automaticamente rascunhos de e-mail quando documentos em falta são detetados pela IA"
            ),
            ConfigField(
                key="base_prompt",
                label="Prompt Base para IA",
                type="textarea",
                placeholder="Escreve um e-mail profissional em português...",
                help_text="Prompt utilizado pela IA para gerar o conteúdo do e-mail. Variáveis: {client_name}, {document_type}, {process_number}, {company_name}",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="eligible_doc_types",
                label="Tipos de Documento Elegíveis",
                type="text",
                placeholder="irs, recibo_vencimento, extrato_bancario, cc",
                help_text="Tipos de documento separados por vírgula que geram rascunhos automáticos quando em falta",
                depends_on={"enabled": True},
            ),
        ]
    },
    "audit_trail": {
        "title": "Auditoria (Audit Trail)",
        "description": "Configurar o sistema de registo de auditoria que rastreia todas as alterações aos dados",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Audit Trail",
                type="boolean",
                help_text="Regista todas as alterações aos processos com detalhes (IP, origem, justificação)"
            ),
            ConfigField(
                key="log_ip_address",
                label="Registar Endereço IP",
                type="boolean",
                help_text="Inclui o endereço IP do utilizador nos registos de auditoria",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="log_ai_approvals",
                label="Registar Aprovações de IA",
                type="boolean",
                help_text="Regista quando um utilizador aprova ou rejeita sugestões de IA",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="require_reason_for_critical_fields",
                label="Exigir Justificação em Campos Críticos",
                type="boolean",
                help_text="Quando activo, alterações a campos críticos devem incluir justificação",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="critical_fields",
                label="Campos Críticos (JSON)",
                type="textarea",
                placeholder='["financial_data", "credit_data", "status"]',
                help_text="Lista JSON de campos que exigem justificação quando alterados",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="retention_days",
                label="Dias de Retenção",
                type="number",
                placeholder="365",
                help_text="Número de dias para manter os registos de auditoria (default: 365)",
                depends_on={"enabled": True},
            ),
        ]
    },
}


@router.get("")
async def get_config(
    company_id: Optional[str] = Query("default", description="ID da empresa (default = global)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obter todas as configurações do sistema.
    Apenas admin e CEO podem aceder.

    MULTI-EMPRESA: Use o parâmetro company_id para obter a config de uma empresa específica.
    Se não for fornecido, retorna a config global (retrocompatível).
    """
    config = await get_system_config(company_id)
    
    # Mascarar passwords para segurança
    config_dict = config.model_dump()
    
    # Mascarar campos sensíveis
    sensitive_fields = [
        "aws_secret_access_key", "onedrive_client_secret", "google_client_secret", 
        "dropbox_app_secret", "smtp_password", "imap_password",
        "smtp_password_2", "imap_password_2",
        "api_key", "api_token", "dropbox_access_token",
        "hcpro_password", "decisoes_password", "doutorfinancas_password", "custom_portal_password",
        "resend_api_key",
    ]
    
    def mask_sensitive(obj, parent_key=""):
        """Mascara campos sensíveis de um dicionário de configuração.

        Substitui valores de campos sensíveis (API keys, tokens, passwords)
        por "••••••••" antes de devolver ao frontend, para evitar
        exposição de credenciais em respostas HTTP.

        A recursão permite mascarar campos em dicionários aninhados.

        Args:
            obj: Dicionário a mascarar (modificado in-place).
            parent_key: Chave do pai (para logging, não usado na lógica).

        Returns:
            dict: Mesmo dicionário com valores sensíveis mascarados.
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in sensitive_fields and value:
                    obj[key] = "••••••••" if value else None
                elif isinstance(value, dict):
                    mask_sensitive(value, key)
        return obj
    
    masked_config = mask_sensitive(config_dict)
    
    return {
        "config": masked_config,
        "fields": CONFIG_FIELDS,
    }


@router.get("/public/export-permission")
async def get_excel_export_permission(
    company_id: Optional[str] = Query("default", description="ID da empresa"),
    user: dict = Depends(get_current_user),
):
    """
    Verificar se a exportação para Excel está permitida.
    Endpoint público (qualquer utilizador autenticado) — usado pelo frontend
    para mostrar/ocultar os botões de exportação.
    """
    config = await get_system_config(company_id)
    return {"allow_excel_export": config.settings.allow_excel_export}


@router.get("/fields")
async def get_config_fields(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Obter definição dos campos de configuração.
    Útil para o frontend construir os formulários.
    """
    return CONFIG_FIELDS


@router.get("/companies")
async def get_available_companies(user: dict = Depends(get_current_user)):
    """
    Listar empresas com configuração própria no sistema.

    MULTI-EMPRESA: Retorna a lista de company_ids disponíveis para o dropdown
    no frontend (Definições Gerais + ProfilePage). Leitura permitida para
    todos os utilizadores autenticados — apenas a escrita requer ADMIN/CEO.
    """
    companies = await list_available_companies()
    return {"companies": companies, "total": len(companies)}


@router.patch("/{section}")
async def update_config(
    section: str,
    data: Dict[str, Any],
    company_id: Optional[str] = Query("default", description="ID da empresa (default = global)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Actualizar uma secção da configuração.

    MULTI-EMPRESA: Use o parâmetro company_id para actualizar a config de uma empresa específica.
    """
    # Secções válidas: definidas em CONFIG_FIELDS + secções de integração
    EXTRA_SECTIONS = {"system_smtp", "system_webmail"}
    if section not in CONFIG_FIELDS and section not in EXTRA_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Secção inválida: {section}")
    
    try:
        await update_config_section(section, data, company_id)
        logger.info(f"Configuração '{section}' actualizada por {user.get('email')} (company_id={company_id})")
        
        return {
            "success": True,
            "message": f"Configuração '{section}' actualizada com sucesso",
            "section": section,
        }
    except Exception as e:
        import traceback
        logger.error(f"Erro ao actualizar configuração '{section}': {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-connection/{service}")
async def test_service_connection(
    service: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Testar ligação a um serviço (email, storage, etc.).
    """
    config = await get_system_config()
    
    if service == "email":
        # Testar ligação SMTP principal
        try:
            import smtplib
            import ssl
            smtp = config.email
            if smtp.provider == "none":
                return {"success": False, "message": "Email não configurado"}
            
            # Verificar se as credenciais SMTP estão preenchidas
            if not smtp.smtp_server:
                return {"success": False, "message": "Servidor SMTP não configurado"}
            if not smtp.smtp_user:
                return {"success": False, "message": "Utilizador SMTP não configurado (preencha o campo 'Utilizador SMTP')"}
            if not smtp.smtp_password:
                return {"success": False, "message": "Password SMTP não configurada"}
            
            # Garantir que as credenciais são strings (não None)
            smtp_user = str(smtp.smtp_user) if smtp.smtp_user else ""
            smtp_password = str(smtp.smtp_password) if smtp.smtp_password else ""
            
            # Tentar ligação com contexto SSL seguro
            context = ssl.create_default_context()
            if smtp.smtp_use_ssl:
                server = smtplib.SMTP_SSL(smtp.smtp_server, smtp.smtp_port or 465, timeout=10, context=context)
            else:
                server = smtplib.SMTP(smtp.smtp_server, smtp.smtp_port or 587, timeout=10)
                server.starttls(context=context)
            
            server.login(smtp_user, smtp_password)
            server.quit()
            return {"success": True, "message": f"Ligação SMTP bem sucedida ({smtp.smtp_server})"}
        except smtplib.SMTPAuthenticationError:
            return {"success": False, "message": "Erro de autenticação: utilizador ou password incorrectos"}
        except smtplib.SMTPConnectError:
            return {"success": False, "message": "Não foi possível conectar ao servidor SMTP"}
        except TimeoutError:
            return {"success": False, "message": "Timeout: servidor SMTP não respondeu"}
        except UnicodeEncodeError as e:
            return {"success": False, "message": f"Erro de codificação: caracteres especiais na password. Tente uma password sem acentos ou caracteres especiais. Detalhe: {str(e)}"}
        except Exception as e:
            error_msg = str(e)
            # Traduzir erros comuns
            if "ascii" in error_msg.lower() or "encode" in error_msg.lower():
                return {"success": False, "message": "Erro de codificação: a password contém caracteres especiais não suportados pelo servidor de email"}
            return {"success": False, "message": f"Erro: {error_msg}"}

    elif service == "system-smtp":
        # Testar envio de email do sistema (Bloco A — system_smtp)
        # Prioridade: Resend API > SMTP directo (legado)
        try:
            sys_smtp = config.system_smtp

            # --- MODO RESEND API (recomendado) ---
            if sys_smtp.resend_api_key:
                import resend

                if not sys_smtp.smtp_from_email:
                    return {"success": False, "message": "Email do Remetente (From) não configurado. Preencha o campo 'Email do Remetente'."}

                try:
                    resend.api_key = sys_smtp.resend_api_key

                    from_header = sys_smtp.smtp_from_email
                    if sys_smtp.smtp_from_name:
                        from_header = f"{sys_smtp.smtp_from_name} <{sys_smtp.smtp_from_email}>"

                    # Enviar email de teste via Resend
                    test_params = {
                        "from": from_header,
                        "to": [sys_smtp.smtp_from_email],  # enviar para o próprio remetente
                        "subject": "✅ Teste de Conexão — PowerCell CRM (Resend API)",
                        "text": "Este é um email de teste automático enviado pelo PowerCell CRM via Resend API.\n\nSe recebeu este email, a configuração está correcta.\n\n— PowerCell CRM",
                    }

                    logger.info(f"[Test Resend] A testar Resend API com from={from_header}")
                    result = resend.Emails.send(test_params)
                    email_id = result.get("id", "N/A")
                    logger.info(f"[Test Resend] Email de teste enviado com sucesso: id={email_id}")
                    return {"success": True, "message": f"Resend API conectado com sucesso! Email de teste enviado (id: {email_id})"}

                except resend.exceptions.InvalidApiKeyError as e:
                    error_msg = str(e)
                    logger.error(f"[Test Resend] InvalidApiKeyError: {error_msg}")
                    return {"success": False, "message": f"Resend API Key inválida ou expirada. Verifique a chave no dashboard do Resend (https://resend.com/api-keys). Detalhe: {error_msg}"}
                except resend.exceptions.ApplicationError as e:
                    error_msg = str(e)
                    logger.error(f"[Test Resend] ApplicationError: {error_msg}")
                    return {"success": False, "message": f"Erro da API Resend (possível limite de envio ou domínio não verificado). Verifique o seu plano e domínios em https://resend.com. Detalhe: {error_msg}"}
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"[Test Resend] Erro inesperado: {type(e).__name__}: {error_msg}")
                    error_lower = error_msg.lower()
                    if "domain" in error_lower or "dns" in error_lower or "verification" in error_lower:
                        return {"success": False, "message": f"Domínio não verificado no Resend. Adicione e verifique o domínio '{sys_smtp.smtp_from_email.split('@')[1] if '@' in sys_smtp.smtp_from_email else '?'}' em https://resend.com/domains. Detalhe: {error_msg}"}
                    if "from" in error_lower and ("invalid" in error_lower or "required" in error_lower):
                        return {"success": False, "message": f"Endereço 'From' inválido. Verifique se o email do remetente '{sys_smtp.smtp_from_email}' está correcto e o domínio verificado no Resend. Detalhe: {error_msg}"}
                    return {"success": False, "message": f"Erro Resend API: {type(e).__name__}: {error_msg}"}

            # --- MODO SMTP DIRECTO (LEGADO) ---
            elif sys_smtp.smtp_host and sys_smtp.smtp_username:
                import smtplib
                import socket
                import ssl
                import os

                smtp_user = str(sys_smtp.smtp_username)
                smtp_password = str(sys_smtp.smtp_password)
                smtp_port = int(sys_smtp.smtp_port or 587)

                is_render = os.environ.get("RENDER", "") or "render.com" in os.environ.get("RENDER_SERVICE_NAME", "")

                if sys_smtp.smtp_use_tls and smtp_port == 465:
                    return {"success": False, "message": "Atenção: Porta 465 requer SSL implícito (desative TLS para usar porta 465, ou mude para porta 587 com TLS activo)"}
                if not sys_smtp.smtp_use_tls and smtp_port == 587:
                    return {"success": False, "message": "Atenção: Porta 587 requer STARTTLS (active TLS para usar porta 587, ou mude para porta 465 com TLS desactivado)"}

                context = ssl.create_default_context()
                if sys_smtp.smtp_use_tls:
                    server = smtplib.SMTP(sys_smtp.smtp_host, smtp_port, timeout=10)
                    server.starttls(context=context)
                else:
                    server = smtplib.SMTP_SSL(sys_smtp.smtp_host, smtp_port, timeout=10, context=context)

                server.login(smtp_user, smtp_password)
                server.quit()
                return {"success": True, "message": f"Ligação SMTP do sistema bem sucedida ({sys_smtp.smtp_host}:{smtp_port}). NOTA: SMTP pode falhar em ambientes como o Render — recomenda-se usar Resend API."}

            else:
                return {"success": False, "message": "Email de Sistema não configurado. Preencha a 'Resend API Key' (recomendado) ou configure SMTP (legado)."}
        except Exception as e:
            logger.error(f"[Test System SMTP] Erro inesperado: {type(e).__name__}: {e}")
            return {"success": False, "message": f"Erro ao testar email do sistema: {type(e).__name__}: {str(e)}"}

    elif service == "storage":
        storage = config.storage
        # Converter para string para comparação segura (enum ou string)
        provider_value = str(storage.provider.value) if hasattr(storage.provider, 'value') else str(storage.provider)
        
        if provider_value == "none":
            return {"success": False, "message": "Armazenamento não configurado"}
        elif provider_value == "aws_s3":
            # Testar ligação AWS S3
            try:
                from services.s3_storage import s3_service
                if s3_service.is_configured():
                    # Tentar verificar acesso ao bucket
                    try:
                        s3_service.s3_client.head_bucket(Bucket=s3_service.bucket_name)
                        return {"success": True, "message": f"AWS S3 conectado com sucesso! Bucket: {s3_service.bucket_name}"}
                    except s3_service.s3_client.exceptions.ClientError as e:
                        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                        if error_code == '403':
                            return {"success": False, "message": "Acesso negado ao bucket S3 - verifique as permissões"}
                        elif error_code == '404':
                            return {"success": False, "message": f"Bucket '{s3_service.bucket_name}' não encontrado"}
                        else:
                            return {"success": False, "message": f"Erro ao aceder bucket: {str(e)}"}
                    except Exception as e:
                        return {"success": False, "message": f"Erro ao aceder bucket: {str(e)}"}
                else:
                    # S3 não configurado via variáveis de ambiente, tentar com config da DB
                    if storage.aws_access_key_id and storage.aws_secret_access_key and storage.aws_bucket_name:
                        return {"success": True, "message": f"AWS S3 configurado via UI (Bucket: {storage.aws_bucket_name}). Configure as variáveis AWS no ambiente para activar."}
                    else:
                        return {"success": False, "message": "AWS S3 não está configurado. Preencha as credenciais ou configure as variáveis de ambiente."}
            except ImportError:
                return {"success": False, "message": "Módulo boto3 não instalado"}
            except Exception as e:
                return {"success": False, "message": f"Erro AWS S3: {str(e)}"}
        elif provider_value == "onedrive":
            # Verificar se tem as credenciais básicas
            if storage.onedrive_shared_url:
                return {"success": True, "message": "OneDrive configurado (via link partilhado)"}
            else:
                return {"success": False, "message": "URL de partilha não configurado"}
        elif provider_value == "google_drive":
            if storage.google_client_id and storage.google_folder_id:
                return {"success": True, "message": "Google Drive configurado"}
            else:
                return {"success": False, "message": "Credenciais do Google Drive em falta"}
        elif provider_value == "dropbox":
            if storage.dropbox_access_token:
                return {"success": True, "message": "Dropbox configurado"}
            else:
                return {"success": False, "message": "Token de acesso Dropbox não configurado"}
        elif provider_value == "local":
            return {"success": True, "message": "Armazenamento local activo"}
        
        return {"success": False, "message": f"Provider '{provider_value}' não suportado para teste"}
    
    elif service == "ai":
        ai = config.ai
        if not ai.api_key:
            return {"success": False, "message": "Chave API não configurada"}
        
        # Testar chamada simples
        try:
            provider = ai.provider or "openai"
            
            if provider == "emergent":
                # Usar biblioteca de integração para chaves Emergent
                from emergentintegrations.llm.chat import LlmChat, UserMessage
                chat = LlmChat(
                    api_key=ai.api_key,
                    session_id="test-config",
                    system_message="Responde brevemente."
                )
                response = await chat.send_message(UserMessage(text="Diz OK"))
                return {"success": True, "message": f"Ligação à IA Emergent bem sucedida. Resposta: {response}"}
            else:
                # Usar OpenAI directamente para chaves próprias
                from openai import OpenAI
                client = OpenAI(api_key=ai.api_key)
                response = client.chat.completions.create(
                    model=ai.model,
                    messages=[{"role": "user", "content": "Diz OK"}],
                    max_tokens=5
                )
                return {"success": True, "message": "Ligação à IA OpenAI bem sucedida"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}
    
    elif service == "trello":
        trello = config.trello
        if not trello.enabled:
            return {"success": False, "message": "Trello não activado"}
        
        try:
            import httpx
            url = f"https://api.trello.com/1/boards/{trello.board_id}?key={trello.api_key}&token={trello.api_token}"
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    board = response.json()
                    return {"success": True, "message": f"Ligado ao quadro: {board.get('name')}"}
                else:
                    return {"success": False, "message": f"Erro: {response.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}
    
    elif service == "mongodb" or service == "database":
        # Testar ligação MongoDB
        try:
            from database import db
            # Fazer uma query simples para testar a ligação
            result = await db.command("ping")
            if result.get("ok") == 1:
                # Obter estatísticas
                stats = await db.command("dbStats")
                collections = stats.get("collections", 0)
                return {"success": True, "message": f"MongoDB conectado. {collections} colecções."}
            else:
                return {"success": False, "message": "MongoDB não respondeu ao ping"}
        except Exception as e:
            return {"success": False, "message": f"Erro: {str(e)}"}
    
    return {"success": False, "message": "Serviço desconhecido"}


@router.post("/complete-setup")
async def complete_setup(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Marcar a configuração inicial como concluída.
    """
    await mark_setup_completed()
    return {"success": True, "message": "Configuração inicial concluída"}


@router.get("/storage-info")
async def get_storage_info(user: dict = Depends(get_current_user)):
    """
    Obter informação sobre o sistema de armazenamento configurado.
    Disponível para todos os utilizadores autenticados.
    
    Retorna:
    - provider: Tipo de storage (aws_s3, google_drive, onedrive, dropbox, none)
    - provider_label: Nome amigável do provider
    - configured: Se está configurado correctamente
    - base_url: URL base para aceder aos ficheiros (se aplicável)
    """
    config = await get_system_config()
    storage = config.storage
    
    # Converter para string para comparação segura
    provider_value = str(storage.provider.value) if hasattr(storage.provider, 'value') else str(storage.provider)
    
    # Mapear provider para label amigável
    provider_labels = {
        "none": "Não configurado",
        "aws_s3": "Amazon S3",
        "google_drive": "Google Drive",
        "onedrive": "OneDrive",
        "dropbox": "Dropbox"
    }
    
    result = {
        "provider": provider_value,
        "provider_label": provider_labels.get(provider_value, provider_value),
        "configured": False,
        "base_url": None,
        "can_browse": False  # Se permite navegação de pastas
    }
    
    if provider_value == "none":
        return result
    
    elif provider_value == "aws_s3":
        from services.s3_storage import s3_service
        result["configured"] = s3_service.is_configured()
        result["can_browse"] = True  # S3 permite listar ficheiros
        # Não retornar URL s3:// - browsers não suportam este esquema
        # O acesso a ficheiros S3 é feito via URLs pré-assinadas geradas pela API
        result["base_url"] = None
    
    elif provider_value == "onedrive":
        result["configured"] = bool(storage.onedrive_shared_url)
        result["base_url"] = storage.onedrive_shared_url
        result["can_browse"] = False  # OneDrive usa links externos
    
    elif provider_value == "google_drive":
        result["configured"] = bool(storage.google_folder_id)
        if storage.google_folder_id:
            result["base_url"] = f"https://drive.google.com/drive/folders/{storage.google_folder_id}"
        result["can_browse"] = False
    
    elif provider_value == "dropbox":
        result["configured"] = bool(storage.dropbox_access_token)
        result["can_browse"] = False
    
    return result


@router.post("/reset-cache")
async def reset_cache(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """
    Forçar recarga das configurações do sistema.
    """
    invalidate_config_cache()
    return {"success": True, "message": "Cache de configurações limpo"}


@router.get("/reveal-secrets")
async def reveal_secrets(
    section: Optional[str] = Query(None, description="Secção a revelar (email, ai, storage, trello, credit_services)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Revelar valores sensíveis (passwords, API keys) de uma secção de configuração.
    Apenas para Admin e CEO.
    """
    config = await get_system_config()
    config_dict = config.model_dump()
    
    # Todos os campos sensíveis
    sensitive_fields = [
        "aws_secret_access_key", "onedrive_client_secret", "google_client_secret", 
        "dropbox_app_secret", "smtp_password", "imap_password",
        "smtp_password_2", "imap_password_2",
        "api_key", "api_token", "dropbox_access_token",
        "hcpro_password", "decisoes_password", "doutorfinancas_password", "custom_portal_password",
        "resend_api_key",
    ]
    
    # Filtrar apenas a secção pedida
    if section:
        section_data = config_dict.get(section, {})
        if not section_data:
            raise HTTPException(status_code=400, detail=f"Secção '{section}' não encontrada")
        result = {k: v for k, v in section_data.items() if k in sensitive_fields and v}
    else:
        # Revelar todos os campos sensíveis de todas as secções
        result = {}
        for sec_name in ["storage", "email", "ai", "trello", "credit_services"]:
            sec_data = config_dict.get(sec_name, {})
            sec_secrets = {k: v for k, v in sec_data.items() if k in sensitive_fields and v}
            if sec_secrets:
                result[sec_name] = sec_secrets
    
    return {"secrets": result}


# =====================================================================
# SYSTEM EMAIL CONFIGS — CRUD para emails do sistema (DOCUMENTS, RGPD, etc.)
# =====================================================================

VALID_SYSTEM_EMAIL_PURPOSES = ["DOCUMENTS", "RGPD", "SYSTEM_ALERTS", "NOTIFICATIONS", "CUSTOM"]


class SystemEmailConfigCreate(BaseModel):
    purpose: str  # e.g. "DOCUMENTS", "RGPD", "SYSTEM_ALERTS"
    host: str
    port: int = 465
    user: str
    password: str
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    use_ssl: bool = True
    use_tls: bool = False


class SystemEmailConfigUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None  # if empty, keep existing
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    use_ssl: Optional[bool] = None
    use_tls: Optional[bool] = None
    is_active: Optional[bool] = None


def _mask_system_email_config(doc: dict) -> dict:
    """Remove encrypted_password, add has_password boolean."""
    doc = dict(doc)
    doc.pop("encrypted_password", None)
    doc["has_password"] = bool(doc.pop("_has_password", False))
    return doc


@router.get("/system-emails")
async def list_system_email_configs(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Listar todas as configurações de email do sistema.
    Passwords são substituídas por has_password: true/false.
    """
    from database import db
    cursor = db.system_email_configs.find({}, {"encrypted_password": 0})
    results = []
    async for doc in cursor:
        has_pwd = False
        pw = await db.system_email_configs.find_one(
            {"purpose": doc["purpose"]},
            {"encrypted_password": 1}
        )
        if pw and pw.get("encrypted_password"):
            has_pwd = True
        doc = dict(doc)
        doc["has_password"] = has_pwd
        results.append(doc)
    return {"configs": results, "valid_purposes": VALID_SYSTEM_EMAIL_PURPOSES}


@router.get("/system-emails/{purpose}")
async def get_system_email_config(
    purpose: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obter configuração de email do sistema por propósito.
    """
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    purpose_upper = purpose.upper()
    doc = await db.system_email_configs.find_one({"purpose": purpose_upper})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")
    has_pwd = bool(doc.get("encrypted_password"))
    return _mask_system_email_config({**doc, "_has_password": has_pwd})


@router.post("/system-emails")
async def create_system_email_config(
    payload: SystemEmailConfigCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Criar nova configuração de email do sistema.
    A password é encriptada antes de guardar.
    """
    if payload.purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {payload.purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    from services.encryption import encryption_service

    purpose = payload.purpose.upper()
    existing = await db.system_email_configs.find_one({"purpose": purpose})
    if existing:
        raise HTTPException(status_code=409, detail=f"Configuração para '{purpose}' já existe. Use PUT para actualizar.")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": purpose,
        "purpose": purpose,
        "host": payload.host,
        "port": payload.port,
        "user": payload.user,
        "encrypted_password": encryption_service.encrypt(payload.password) if payload.password else "",
        "from_name": payload.from_name,
        "from_email": payload.from_email,
        "use_ssl": payload.use_ssl,
        "use_tls": payload.use_tls,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.system_email_configs.insert_one(doc)
    logger.info(f"System email config criada para '{purpose}' por {user.get('email')}")
    return _mask_system_email_config({**doc, "_has_password": bool(payload.password)})


@router.put("/system-emails/{purpose}")
async def update_system_email_config(
    purpose: str,
    payload: SystemEmailConfigUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Actualizar configuração de email do sistema.
    Se password for enviada, é encriptada; se vazia, mantém a existente.
    """
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    from services.encryption import encryption_service

    purpose_upper = purpose.upper()
    existing = await db.system_email_configs.find_one({"purpose": purpose_upper})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    update_fields = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "password":
            if value:  # non-empty string → encrypt and update
                update_fields["encrypted_password"] = encryption_service.encrypt(value)
            # if empty or None → keep existing password (do nothing)
        else:
            update_fields[field] = value

    if not update_fields:
        return {"message": "Nenhum campo para actualizar", "purpose": purpose_upper}

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.system_email_configs.update_one(
        {"purpose": purpose_upper},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    logger.info(f"System email config actualizada para '{purpose_upper}' por {user.get('email')}")
    updated = await db.system_email_configs.find_one({"purpose": purpose_upper})
    has_pwd = bool(updated.get("encrypted_password")) if updated else False
    return _mask_system_email_config({**updated, "_has_password": has_pwd})


@router.delete("/system-emails/{purpose}")
async def delete_system_email_config(
    purpose: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Eliminar configuração de email do sistema.
    """
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db

    purpose_upper = purpose.upper()
    result = await db.system_email_configs.delete_one({"purpose": purpose_upper})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    logger.info(f"System email config eliminada para '{purpose_upper}' por {user.get('email')}")
    return {"success": True, "message": f"Configuração '{purpose_upper}' eliminada"}


@router.post("/system-emails/{purpose}/test")
async def test_system_email_config(
    purpose: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Testar ligação SMTP para um propósito específico.
    """
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    from services.encryption import encryption_service

    purpose_upper = purpose.upper()
    doc = await db.system_email_configs.find_one({"purpose": purpose_upper})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    if not doc.get("is_active", True):
        return {"success": False, "message": f"Configuração '{purpose_upper}' está inactiva"}

    encrypted_pw = doc.get("encrypted_password", "")
    password = encryption_service.decrypt(encrypted_pw) if encrypted_pw else ""

    host = doc.get("host", "")
    port = int(doc.get("port", 465))
    smtp_user = doc.get("user", "")
    use_ssl = doc.get("use_ssl", True)
    use_tls = doc.get("use_tls", False)

    if not host or not smtp_user:
        return {"success": False, "message": "Host ou utilizador não configurado"}

    try:
        import smtplib
        import ssl

        context = ssl.create_default_context()
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                server.starttls(context=context)

        server.login(smtp_user, password)
        server.quit()
        logger.info(f"[System Email Test] Ligação SMTP bem sucedida para '{purpose_upper}' ({host}:{port})")
        return {"success": True, "message": f"Ligação SMTP bem sucedida para '{purpose_upper}' ({host}:{port})"}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "Erro de autenticação: utilizador ou password incorrectos"}
    except smtplib.SMTPConnectError:
        return {"success": False, "message": "Não foi possível conectar ao servidor SMTP"}
    except TimeoutError:
        return {"success": False, "message": "Timeout: servidor SMTP não respondeu"}
    except Exception as e:
        logger.error(f"[System Email Test] Erro para '{purpose_upper}': {type(e).__name__}: {e}")
        return {"success": False, "message": f"Erro: {type(e).__name__}: {str(e)}"}
