"""
====================================================================
EMAIL SERVICE - CREDITOIMO
====================================================================
Serviço de envio de emails com templates HTML profissionais.

ARQUITECTURA v2.0:
- Usa API transacional (SendGrid/Resend) como primário
- SMTP como fallback de emergência
- Totalmente assíncrono (não-bloqueante)

Templates disponíveis:
1. Confirmação de registo (para o cliente)
2. Lista de documentos necessários
3. Aprovação de crédito
4. Notificação de novo cliente (para staff)
5. Actualização de estado
====================================================================
"""
import logging
from typing import Optional, List

# Importar novo serviço de email
from services.email_v2 import (
    EmailService,
    EmailMessage,
    EmailResult,
    email_service,
    send_email_notification,
    is_email_configured,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    COMPANY_NAME,
    COMPANY_WEBSITE,
    COMPANY_PHONE
)

logger = logging.getLogger(__name__)


# ====================================================================
# Funções de retrocompatibilidade
# ====================================================================
def is_smtp_configured() -> bool:
    """Retrocompatibilidade - verifica se email está configurado."""
    return is_email_configured()


# ====================================================================
# TEMPLATE HTML BASE
# ====================================================================
def get_base_template(content: str, title: str = "") -> str:
    """Template HTML base com estilos consistentes."""
    return f"""
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .wrapper {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .container {{
            background: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
            color: white;
            padding: 30px 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .header .subtitle {{
            margin-top: 8px;
            font-size: 14px;
            color: #f5c518;
            font-weight: 500;
        }}
        .content {{
            padding: 30px;
        }}
        .greeting {{
            font-size: 18px;
            margin-bottom: 20px;
        }}
        .info-box {{
            background: #f8f9fa;
            border-left: 4px solid #1e3a5f;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }}
        .info-box h3 {{
            margin: 0 0 10px 0;
            color: #1e3a5f;
            font-size: 16px;
        }}
        .info-box p {{
            margin: 5px 0;
            color: #555;
        }}
        .highlight-box {{
            background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
            border: 1px solid #4caf50;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: center;
        }}
        .highlight-box h2 {{
            color: #2e7d32;
            margin: 0 0 10px 0;
        }}
        .checklist {{
            background: #fff;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .checklist h3 {{
            margin: 0 0 15px 0;
            color: #1e3a5f;
        }}
        .checklist ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .checklist li {{
            padding: 8px 0;
            border-bottom: 1px dashed #e0e0e0;
        }}
        .checklist li:last-child {{
            border-bottom: none;
        }}
        .btn {{
            display: inline-block;
            background: #f5c518;
            color: #1e3a5f;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            margin: 10px 0;
        }}
        .btn:hover {{
            background: #e6b800;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            border-top: 1px solid #e0e0e0;
        }}
        .footer p {{
            margin: 5px 0;
            font-size: 12px;
            color: #666;
        }}
        .footer .company {{
            font-weight: 600;
            color: #1e3a5f;
        }}
        .social-links {{
            margin-top: 15px;
        }}
        .social-links a {{
            color: #1e3a5f;
            text-decoration: none;
            margin: 0 10px;
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="container">
            <div class="header">
                <h1>Power Real Estate</h1>
                <p class="subtitle">& Precision Crédito</p>
            </div>
            <div class="content">
                {content}
            </div>
            <div class="footer">
                <p class="company">{COMPANY_NAME}</p>
                <p>Intermediação de Crédito • Consultoria Imobiliária</p>
                <p style="margin-top: 15px; font-size: 11px; color: #999;">
                    Este email foi enviado automaticamente. Por favor não responda diretamente a este email.
                </p>
            </div>
        </div>
    </div>
</body>
</html>
"""


# ====================================================================
# TEMPLATES DE EMAIL
# ====================================================================

async def send_registration_confirmation(client_email: str, client_name: str, portal_access_code: str = None) -> bool:
    """
    Email de confirmação de registo para o cliente.
    Enviado imediatamente após submissão do formulário.
    
    Se portal_access_code for fornecido, inclui informações de acesso ao Portal.
    """
    subject = "Recebemos o seu pedido - Power Real Estate & Precision"
    
    # Bloco opcional com credenciais do portal
    portal_section_text = ""
    portal_section_html = ""
    if portal_access_code:
        portal_section_text = f"""

Os seus dados de acesso ao Portal do Cliente:
- Email: {client_email}
- Código de Acesso: {portal_access_code}

Através do Portal poderá acompanhar o estado do seu processo e carregar documentação.
"""
        portal_section_html = f"""
<div class="info-box" style="border-left-color: #0d9488; background: linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%);">
    <h3 style="color: #0f766e;">Acesso ao Portal do Cliente</h3>
    <p><strong>Email:</strong> {client_email}</p>
    <p><strong>Código de Acesso:</strong> <span style="font-family: 'Courier New', monospace; font-size: 18px; font-weight: bold; color: #0f766e; letter-spacing: 3px;">{portal_access_code}</span></p>
    <p style="font-size: 13px; color: #64748b; margin-top: 10px;">Através do Portal poderá acompanhar o estado do seu processo e carregar documentação.</p>
</div>
"""
    
    body = f"""
Olá {client_name},

Recebemos o seu pedido de análise de crédito habitação.

A nossa equipa irá analisar a sua informação e entrará em contacto consigo brevemente, 
normalmente dentro de 24-48 horas úteis.
{portal_section_text}
Enquanto aguarda, pode preparar os seguintes documentos:
- Cartão de Cidadão (frente e verso)
- Últimos 3 recibos de vencimento
- Declaração de IRS do último ano
- Extratos bancários dos últimos 3 meses

Se tiver alguma questão urgente, não hesite em contactar-nos.

Cumprimentos,
{COMPANY_NAME}
"""
    
    content = f"""
<p class="greeting">Olá <strong>{client_name}</strong>,</p>

<div class="highlight-box">
    <h2>Pedido Recebido com Sucesso!</h2>
    <p>A sua solicitação foi registada no nosso sistema.</p>
</div>

<p>A nossa equipa irá analisar a sua informação e entrará em contacto consigo 
<strong>brevemente</strong>, normalmente dentro de <strong>24-48 horas úteis</strong>.</p>

{portal_section_html}

<div class="info-box">
    <h3>O que acontece a seguir?</h3>
    <p>1. A nossa equipa analisa o seu perfil</p>
    <p>2. Entramos em contacto para esclarecer dúvidas</p>
    <p>3. Solicitamos documentação necessária</p>
    <p>4. Apresentamos as melhores soluções de crédito</p>
</div>

<div class="checklist">
    <h3>Documentos a Preparar</h3>
    <ul>
        <li>Cartão de Cidadão (frente e verso)</li>
        <li>Últimos 3 recibos de vencimento</li>
        <li>Declaração de IRS do último ano</li>
        <li>Extratos bancários dos últimos 3 meses</li>
        <li>Comprovativo de morada</li>
    </ul>
</div>

<p>Se tiver alguma questão urgente, não hesite em contactar-nos.</p>

<p>Cumprimentos,<br>
<strong>Equipa {COMPANY_NAME}</strong></p>
"""
    
    html_body = get_base_template(content, "Pedido Recebido")
    return await send_email_notification(client_email, subject, body, html_body)


async def send_documents_checklist(client_email: str, client_name: str, documents: List[str] = None) -> bool:
    """
    Email com lista de documentos necessários para crédito habitação.
    """
    subject = "Lista de Documentos Necessários - Crédito Habitação"
    
    default_documents = [
        "Cartão de Cidadão (frente e verso) de todos os titulares",
        "Últimos 3 recibos de vencimento",
        "Declaração de IRS do último ano (Modelo 3)",
        "Nota de liquidação do IRS",
        "Extratos bancários dos últimos 3 meses (todas as contas)",
        "Declaração da entidade patronal (antiguidade e tipo de contrato)",
        "Comprovativo de morada atual",
        "Mapa de responsabilidades do Banco de Portugal",
        "Se tiver créditos: contratos e comprovativos de prestações",
    ]
    
    docs_list = documents or default_documents
    docs_text = "\n".join([f"- {doc}" for doc in docs_list])
    
    body = f"""
Olá {client_name},

Para avançarmos com a análise do seu crédito habitação, necessitamos dos seguintes documentos:

{docs_text}

Por favor, envie os documentos digitalizados ou fotografados com boa qualidade.

Pode responder a este email com os documentos em anexo ou entregar presencialmente.

Estamos ao dispor para qualquer esclarecimento.

Cumprimentos,
{COMPANY_NAME}
"""
    
    docs_html = "".join([f"<li>{doc}</li>" for doc in docs_list])
    
    content = f"""
<p class="greeting">Olá <strong>{client_name}</strong>,</p>

<p>Para avançarmos com a análise do seu crédito habitação, necessitamos dos seguintes documentos:</p>

<div class="checklist">
    <h3>Documentos Necessários</h3>
    <ul>
        {docs_html}
    </ul>
</div>

<div class="info-box">
    <h3>Dicas Importantes</h3>
    <p>• Digitalize ou fotografe com boa qualidade e iluminação</p>
    <p>• Certifique-se que todos os dados estão legíveis</p>
    <p>• Envie ficheiros em PDF, JPG ou PNG</p>
    <p>• Pode enviar por email ou entregar presencialmente</p>
</div>

<p>Quanto mais rapidamente nos enviar a documentação, mais depressa poderemos avançar com a sua proposta.</p>

<p>Estamos ao dispor para qualquer esclarecimento.</p>

<p>Cumprimentos,<br>
<strong>Equipa {COMPANY_NAME}</strong></p>
"""
    
    html_body = get_base_template(content, "Documentos Necessários")
    return await send_email_notification(client_email, subject, body, html_body)


async def send_credit_approved(
    client_email: str, 
    client_name: str, 
    bank_name: str,
    approved_amount: str,
    interest_rate: str = None,
    monthly_payment: str = None
) -> bool:
    """
    Email de notificação de aprovação de crédito.
    """
    subject = "Parabéns! O seu Crédito foi Aprovado!"
    
    details = f"Banco: {bank_name}\nValor Aprovado: {approved_amount}"
    if interest_rate:
        details += f"\nTaxa de Juro: {interest_rate}"
    if monthly_payment:
        details += f"\nPrestação Mensal: {monthly_payment}"
    
    body = f"""
Olá {client_name},

PARABÉNS! Temos excelentes notícias!

O seu crédito habitação foi APROVADO!

{details}

A nossa equipa irá entrar em contacto consigo para explicar os próximos passos 
e agendar a assinatura da documentação.

Obrigado por confiar em nós para este momento tão importante da sua vida!

Cumprimentos,
{COMPANY_NAME}
"""
    
    details_html = f"""
<p><strong>Banco:</strong> {bank_name}</p>
<p><strong>Valor Aprovado:</strong> {approved_amount}</p>
"""
    if interest_rate:
        details_html += f"<p><strong>Taxa de Juro:</strong> {interest_rate}</p>"
    if monthly_payment:
        details_html += f"<p><strong>Prestação Mensal:</strong> {monthly_payment}</p>"
    
    content = f"""
<p class="greeting">Olá <strong>{client_name}</strong>,</p>

<div class="highlight-box" style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-color: #2196f3;">
    <h2 style="color: #1565c0;">PARABÉNS!</h2>
    <p style="font-size: 18px; color: #1565c0;"><strong>O seu Crédito foi Aprovado!</strong></p>
</div>

<div class="info-box" style="border-left-color: #4caf50;">
    <h3 style="color: #2e7d32;">Detalhes da Aprovação</h3>
    {details_html}
</div>

<p>A nossa equipa irá entrar em contacto consigo para explicar os <strong>próximos passos</strong> 
e agendar a assinatura da documentação.</p>

<div class="info-box">
    <h3>Próximos Passos</h3>
    <p>1. Reunião para revisão das condições</p>
    <p>2. Assinatura do contrato de crédito</p>
    <p>3. Agendamento da escritura</p>
    <p>4. Entrega das chaves da sua nova casa!</p>
</div>

<p>Obrigado por confiar em nós para este momento tão importante da sua vida!</p>

<p>Cumprimentos,<br>
<strong>Equipa {COMPANY_NAME}</strong></p>
"""
    
    html_body = get_base_template(content, "Crédito Aprovado")
    return await send_email_notification(client_email, subject, body, html_body)


async def send_new_client_notification(
    client_name: str,
    client_email: str,
    client_phone: str,
    process_type: str,
    staff_email: str,
    staff_name: str
) -> bool:
    """Notificação para staff sobre novo cliente registado."""
    
    subject = f"Novo Cliente: {client_name}"
    
    body = f"""
Olá {staff_name},

Foi registado um novo cliente no sistema:

Nome: {client_name}
Email: {client_email}
Telefone: {client_phone}
Tipo de Processo: {process_type}

Aceda à plataforma para ver todos os detalhes e dar seguimento.

Cumprimentos,
Sistema Precision Crédito
"""
    
    content = f"""
<p class="greeting">Olá <strong>{staff_name}</strong>,</p>

<p>Foi registado um <strong>novo cliente</strong> no sistema:</p>

<div class="info-box">
    <h3>Dados do Cliente</h3>
    <p><strong>Nome:</strong> {client_name}</p>
    <p><strong>Email:</strong> <a href="mailto:{client_email}">{client_email}</a></p>
    <p><strong>Telefone:</strong> <a href="tel:{client_phone}">{client_phone}</a></p>
    <p><strong>Tipo de Processo:</strong> {process_type}</p>
</div>

<p style="text-align: center; margin-top: 25px;">
    <a href="#" class="btn">Aceder à Plataforma</a>
</p>

<p>Cumprimentos,<br>
<strong>Sistema Precision Crédito</strong></p>
"""
    
    html_body = get_base_template(content, "Novo Cliente")
    return await send_email_notification(staff_email, subject, body, html_body)


async def send_status_update_notification(
    client_email: str,
    client_name: str,
    new_status: str,
    message: str = ""
) -> bool:
    """Notificação de actualização de estado para o cliente."""
    
    subject = f"Atualização do seu Processo - {new_status}"
    
    body = f"""
Olá {client_name},

O estado do seu processo foi atualizado para: {new_status}

{message if message else ''}

Para mais informações, entre em contacto connosco.

Cumprimentos,
{COMPANY_NAME}
"""
    
    message_html = f"<p>{message}</p>" if message else ""
    
    content = f"""
<p class="greeting">Olá <strong>{client_name}</strong>,</p>

<div class="info-box">
    <h3>Atualização do Processo</h3>
    <p>O estado do seu processo foi atualizado para:</p>
    <p style="font-size: 18px; font-weight: bold; color: #1e3a5f;">{new_status}</p>
</div>

{message_html}

<p>Para mais informações, não hesite em contactar-nos.</p>

<p>Cumprimentos,<br>
<strong>Equipa {COMPANY_NAME}</strong></p>
"""
    
    html_body = get_base_template(content, "Atualização do Processo")
    return await send_email_notification(client_email, subject, body, html_body)


# =====================================================================
# SYSTEM EMAIL TRANSPORTER — Obtém config SMTP para emails do sistema
# =====================================================================

VALID_SYSTEM_EMAIL_PURPOSES = ["DOCUMENTS", "RGPD", "SYSTEM_ALERTS", "NOTIFICATIONS", "CUSTOM"]


async def get_system_transporter(purpose: str) -> dict:
    """
    Obtém configuração SMTP para um propósito específico do sistema.

    Prioridade:
    1. Configuração na DB (system_email_configs) para esse purpose, se is_active=True
    2. Fallback: contas globais do sistema (env vars POWER_EMAIL, etc.)

    Returns:
        dict com chaves: host, port, user, password, from_name, from_email, use_ssl, use_tls, source
        ou dict com "error" se nenhuma config disponível

    Raises:
        ValueError: se purpose não for válido
    """
    if purpose not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise ValueError(
            f"Purpose inválido: '{purpose}'. "
            f"Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}"
        )

    from database import db as _db

    # === PRIORIDADE 1: Config na DB ===
    try:
        doc = await _db.system_email_configs.find_one(
            {"purpose": purpose, "is_active": True}
        )
        if doc:
            from services.email_config_resolver import decrypt_email_secret
            encrypted_pw = doc.get("encrypted_password", "")
            smtp_user = doc.get("user", "")
            password = decrypt_email_secret(
                encrypted_pw,
                f"system_email_configs purpose={purpose} user={smtp_user}",
            )
            if not password:
                logger.warning(
                    "[get_system_transporter] Password vazia ou não desencriptável "
                    "para '%s' (user=%s). A tentar fallback.",
                    purpose, smtp_user,
                )
            else:
                logger.info(
                    f"[get_system_transporter] Config DB encontrada para '{purpose}' "
                    f"(host={doc.get('host')}, user={smtp_user}, source=db)"
                )
                return {
                    "host": doc.get("host", ""),
                    "port": int(doc.get("port", 465)),
                    "user": smtp_user,
                    "password": password,
                    "from_name": doc.get("from_name") or "",
                    "from_email": doc.get("from_email") or smtp_user or "",
                    "use_ssl": doc.get("use_ssl", True),
                    "use_tls": doc.get("use_tls", False),
                    "source": "db",
                }
    except Exception as e:
        logger.warning(
            f"[get_system_transporter] Erro ao buscar config DB para '{purpose}': {e}"
        )

    # === PRIORIDADE 2: Fallback para env vars (get_email_accounts) ===
    try:
        from services.email_service import get_email_accounts
        accounts = get_email_accounts()
        if accounts:
            account = accounts[0]
            logger.info(
                f"[get_system_transporter] Fallback para env var: "
                f"'{account.name}' ({account.smtp_server}) para purpose '{purpose}'"
            )
            return {
                "host": account.smtp_server,
                "port": account.smtp_port,
                "user": account.email,
                "password": account.password,
                "from_name": account.name,
                "from_email": account.email,
                "use_ssl": True,
                "use_tls": False,
                "source": "env_fallback",
            }
    except Exception as e:
        logger.warning(
            f"[get_system_transporter] Erro no fallback env vars para '{purpose}': {e}"
        )

    # === NENHUMA CONFIG DISPONÍVEL ===
    logger.error(
        f"[get_system_transporter] Nenhuma config disponível para '{purpose}' "
        f"(DB ou env vars)"
    )
    return {
        "error": "Nenhuma configuração de email disponível",
        "source": "none",
    }
