"""
System config connection tests (email, storage, AI, MongoDB, system-smtp).

Extraído de `routes/system_config.py`.
Reuses `services.system_config.get_system_config` — do not overwrite that module.
"""
from __future__ import annotations

import logging

from services.system_config import get_system_config

logger = logging.getLogger(__name__)


async def run_test_service_connection(service: str) -> dict:
    """Testar ligação a um serviço (email, storage, etc.)."""
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
                import ssl

                smtp_user = str(sys_smtp.smtp_username)
                smtp_password = str(sys_smtp.smtp_password)
                smtp_port = int(sys_smtp.smtp_port or 587)

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
