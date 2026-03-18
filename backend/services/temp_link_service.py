"""
====================================================================
SERVIÇO DE LINKS TEMPORÁRIOS - CREDITOIMO
====================================================================
Gere links temporários para:
- Upload de documentação pelo cliente
- Download de documentação pelo cliente

Características:
- Tokens únicos e seguros (UUID v4)
- Expiração configurável
- Limite de utilizações
- Notificação por email
====================================================================
"""
import uuid
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from database import db
from models.temp_link import (
    TempLinkType, TempLinkStatus, 
    TempLinkCreate, TempLinkResponse
)

logger = logging.getLogger(__name__)


class TempLinkService:
    """Serviço para gestão de links temporários."""

    @staticmethod
    def generate_secure_token() -> str:
        """Gera um token seguro e único."""
        # Combinar UUID + secrets para maior segurança
        unique_id = str(uuid.uuid4())
        random_bytes = secrets.token_hex(16)
        return f"{unique_id.replace('-', '')[:16]}{random_bytes[:16]}"

    @staticmethod
    async def create_link(
        process_id: str,
        link_type: TempLinkType,
        user_id: str,
        user_name: str,
        expires_in_hours: int = 72,
        max_uses: int = 1,
        description: str = None,
        file_paths: List[str] = None,
        notify_email: bool = True
    ) -> TempLinkResponse:
        """
        Cria um novo link temporário.

        Args:
            process_id: ID do processo/cliente
            link_type: Tipo de link (upload/download)
            user_id: ID do utilizador que cria o link
            user_name: Nome do utilizador que cria o link
            expires_in_hours: Horas até expirar (default 72h)
            max_uses: Máximo de utilizações (default 1)
            description: Descrição opcional
            file_paths: Lista de ficheiros para download
            notify_email: Se deve enviar email ao cliente

        Returns:
            TempLinkResponse com dados do link criado
        """
        # Obter dados do processo
        process = await db.processes.find_one({"id": process_id})
        if not process:
            raise ValueError("Processo não encontrado")

        client_name = process.get("client_name", "Cliente")
        client_email = process.get("client_email")

        # Gerar token único
        token = TempLinkService.generate_secure_token()

        # Verificar que o token é único
        existing = await db.temp_links.find_one({"token": token})
        while existing:
            token = TempLinkService.generate_secure_token()
            existing = await db.temp_links.find_one({"token": token})

        # Calcular data de expiração
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_in_hours)

        # Criar documento
        link_doc = {
            "id": str(uuid.uuid4()),
            "token": token,
            "process_id": process_id,
            "client_name": client_name,
            "client_email": client_email,
            "link_type": link_type.value,
            "status": TempLinkStatus.PENDING.value,
            "expires_at": expires_at.isoformat(),
            "created_at": now.isoformat(),
            "created_by": user_id,
            "created_by_name": user_name,
            "max_uses": max_uses,
            "current_uses": 0,
            "description": description,
            "file_paths": file_paths or [],
            "used_at": None,
            "uploaded_files": [],
            "notified": False,
            "notify_email": notify_email
        }

        # Guardar na base de dados
        await db.temp_links.insert_one(link_doc)

        # Construir URL
        base_url = "https://powercell.vercel.app"  # TODO: usar variável de ambiente
        if link_type == TempLinkType.UPLOAD:
            url = f"{base_url}/upload/{token}"
        else:
            url = f"{base_url}/download/{token}"

        # Enviar email se solicitado
        if notify_email and client_email:
            await TempLinkService._send_notification_email(
                link_doc, process, url
            )
            link_doc["notified"] = True
            await db.temp_links.update_one(
                {"id": link_doc["id"]},
                {"$set": {"notified": True}}
            )

        logger.info(f"Link temporário criado: {link_type.value} para {client_name}")

        return TempLinkResponse(
            id=link_doc["id"],
            token=token,
            process_id=process_id,
            client_name=client_name,
            client_email=client_email,
            link_type=link_type,
            status=TempLinkStatus.PENDING,
            url=url,
            expires_at=expires_at.isoformat(),
            created_at=now.isoformat(),
            created_by=user_id,
            max_uses=max_uses,
            current_uses=0,
            description=description,
            file_paths=file_paths,
            used_at=None,
            uploaded_files=[]
        )

    @staticmethod
    async def get_link_by_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Obtém um link pelo token.

        Args:
            token: Token do link

        Returns:
            Dados do link ou None se não encontrado
        """
        link = await db.temp_links.find_one({"token": token}, {"_id": 0})
        return link

    @staticmethod
    async def validate_link(token: str) -> Dict[str, Any]:
        """
        Valida se um link pode ser usado.

        Args:
            token: Token do link

        Returns:
            Dict com validade e mensagem de erro se aplicável
        """
        link = await db.temp_links.find_one({"token": token}, {"_id": 0})

        if not link:
            return {"valid": False, "error": "Link não encontrado"}

        # Verificar estado
        if link["status"] == TempLinkStatus.USED.value:
            return {"valid": False, "error": "Link já foi utilizado"}
        
        if link["status"] == TempLinkStatus.CANCELLED.value:
            return {"valid": False, "error": "Link foi cancelado"}

        # Verificar expiração
        expires_at = datetime.fromisoformat(link["expires_at"].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            # Atualizar estado para expirado
            await db.temp_links.update_one(
                {"token": token},
                {"$set": {"status": TempLinkStatus.EXPIRED.value}}
            )
            return {"valid": False, "error": "Link expirado"}

        # Verificar limite de utilizações
        if link["current_uses"] >= link["max_uses"]:
            await db.temp_links.update_one(
                {"token": token},
                {"$set": {"status": TempLinkStatus.USED.value}}
            )
            return {"valid": False, "error": "Link atingiu o limite de utilizações"}

        return {
            "valid": True,
            "link": link,
            "remaining_uses": link["max_uses"] - link["current_uses"]
        }

    @staticmethod
    async def use_link(
        token: str, 
        uploaded_files: List[dict] = None
    ) -> Dict[str, Any]:
        """
        Marca um link como utilizado.

        Args:
            token: Token do link
            uploaded_files: Lista de ficheiros carregados (para upload links)

        Returns:
            Dict com resultado da operação
        """
        # Validar primeiro
        validation = await TempLinkService.validate_link(token)
        if not validation["valid"]:
            return validation

        link = validation["link"]
        now = datetime.now(timezone.utc)

        # Incrementar utilizações
        new_uses = link["current_uses"] + 1
        update_data = {
            "current_uses": new_uses,
            "used_at": now.isoformat()
        }

        # Se foram carregados ficheiros, adicionar à lista
        if uploaded_files:
            existing_files = link.get("uploaded_files", [])
            existing_files.extend(uploaded_files)
            update_data["uploaded_files"] = existing_files

        # Se atingiu limite, marcar como usado
        if new_uses >= link["max_uses"]:
            update_data["status"] = TempLinkStatus.USED.value

        await db.temp_links.update_one(
            {"token": token},
            {"$set": update_data}
        )

        logger.info(f"Link temporário utilizado: {token[:16]}...")

        return {
            "success": True,
            "message": "Link utilizado com sucesso",
            "process_id": link["process_id"],
            "client_name": link["client_name"]
        }

    @staticmethod
    async def cancel_link(link_id: str, user_id: str) -> bool:
        """
        Cancela um link temporário.

        Args:
            link_id: ID do link
            user_id: ID do utilizador que cancela

        Returns:
            True se cancelado com sucesso
        """
        result = await db.temp_links.update_one(
            {"id": link_id, "status": TempLinkStatus.PENDING.value},
            {
                "$set": {
                    "status": TempLinkStatus.CANCELLED.value,
                    "cancelled_at": datetime.now(timezone.utc).isoformat(),
                    "cancelled_by": user_id
                }
            }
        )

        return result.modified_count > 0

    @staticmethod
    async def list_process_links(process_id: str) -> List[Dict[str, Any]]:
        """
        Lista todos os links de um processo.

        Args:
            process_id: ID do processo

        Returns:
            Lista de links
        """
        links = await db.temp_links.find(
            {"process_id": process_id},
            {"_id": 0}
        ).sort("created_at", -1).to_list(100)

        # Adicionar URLs
        base_url = "https://powercell.vercel.app"
        for link in links:
            if link["link_type"] == TempLinkType.UPLOAD.value:
                link["url"] = f"{base_url}/upload/{link['token']}"
            else:
                link["url"] = f"{base_url}/download/{link['token']}"

        return links

    @staticmethod
    async def cleanup_expired_links() -> int:
        """
        Remove ou atualiza links expirados.

        Returns:
            Número de links atualizados
        """
        now = datetime.now(timezone.utc).isoformat()

        result = await db.temp_links.update_many(
            {
                "status": TempLinkStatus.PENDING.value,
                "expires_at": {"$lt": now}
            },
            {"$set": {"status": TempLinkStatus.EXPIRED.value}}
        )

        logger.info(f"Links expirados atualizados: {result.modified_count}")
        return result.modified_count

    @staticmethod
    async def _send_notification_email(
        link_doc: Dict[str, Any],
        process: Dict[str, Any],
        url: str
    ) -> bool:
        """
        Envia email de notificação ao cliente.

        Args:
            link_doc: Dados do link
            process: Dados do processo
            url: URL do link

        Returns:
            True se enviado com sucesso
        """
        try:
            from services.email_service import send_email

            client_name = link_doc["client_name"]
            client_email = link_doc["client_email"]
            link_type = link_doc["link_type"]
            description = link_doc.get("description", "")

            if link_type == TempLinkType.UPLOAD.value:
                subject = "📎 PowerCell - Carregue a sua Documentação"
                body_text = f"""Olá {client_name},

Foi solicitado que carregue documentação para o seu processo.

Para carregar os documentos, aceda ao seguinte link:
{url}

{f'Notas: {description}' if description else ''}

Este link expira em 72 horas. Se não conseguir aceder dentro deste prazo, contacte o seu consultor.

Cumprimentos,
Equipa PowerCell
"""
                body_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d253f 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="color: white; margin: 0;">📎 Carregamento de Documentação</h1>
                    </div>
                    <div style="background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; border: 1px solid #e2e8f0; border-top: none;">
                        <p style="font-size: 16px; color: #334155;">Olá <strong>{client_name}</strong>,</p>
                        <p style="font-size: 16px; color: #334155;">Foi solicitado que carregue documentação para o seu processo.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{url}" style="background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); color: white; padding: 14px 35px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block; font-size: 16px;">
                                Carregar Documentos
                            </a>
                        </div>
                        
                        {f'<p style="font-size: 14px; color: #64748b;"><strong>Notas:</strong> {description}</p>' if description else ''}
                        
                        <div style="background: #fef3c7; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b; margin-top: 20px;">
                            <p style="font-size: 14px; color: #92400e; margin: 0;">
                                ⏰ Este link expira em <strong>72 horas</strong>. Se não conseguir aceder dentro deste prazo, contacte o seu consultor.
                            </p>
                        </div>
                        
                        <p style="font-size: 14px; color: #64748b; margin-top: 30px;">
                            Cumprimentos,<br>
                            <strong>Equipa PowerCell</strong>
                        </p>
                    </div>
                </body>
                </html>
                """
            else:
                # Download link
                subject = "📥 PowerCell - Documentação Disponível"
                body_text = f"""Olá {client_name},

Tem documentação disponível para download.

Para aceder aos documentos, clique no seguinte link:
{url}

{f'Notas: {description}' if description else ''}

Este link expira em 72 horas.

Cumprimentos,
Equipa PowerCell
"""
                body_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d253f 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="color: white; margin: 0;">📥 Documentação Disponível</h1>
                    </div>
                    <div style="background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; border: 1px solid #e2e8f0; border-top: none;">
                        <p style="font-size: 16px; color: #334155;">Olá <strong>{client_name}</strong>,</p>
                        <p style="font-size: 16px; color: #334155;">Tem documentação disponível para download.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{url}" style="background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); color: white; padding: 14px 35px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block; font-size: 16px;">
                                Descarregar Documentos
                            </a>
                        </div>
                        
                        {f'<p style="font-size: 14px; color: #64748b;"><strong>Notas:</strong> {description}</p>' if description else ''}
                        
                        <p style="font-size: 14px; color: #64748b; margin-top: 30px;">
                            Cumprimentos,<br>
                            <strong>Equipa PowerCell</strong>
                        </p>
                    </div>
                </body>
                </html>
                """

            result = await send_email(
                account_name="power",
                to_emails=[client_email],
                subject=subject,
                body=body_text,
                body_html=body_html
            )

            if result.get("success"):
                logger.info(f"Email de notificação enviado para {client_email}")
                return True
            else:
                logger.warning(f"Erro ao enviar email: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Erro ao enviar email de notificação: {e}")
            return False


# Instância global
temp_link_service = TempLinkService()
