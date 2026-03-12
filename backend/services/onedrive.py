"""
OneDrive Service - Integração com Microsoft OneDrive
Suporta contas pessoais Microsoft com OAuth2 delegated permissions.

Funcionalidades:
- Autenticação OAuth2 com contas pessoais
- Listagem de pastas e ficheiros
- Busca de pasta por nome do cliente (fuzzy matching)
- URLs de download/visualização
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from thefuzz import fuzz, process as fuzzy_process
import httpx

logger = logging.getLogger(__name__)

# Configurações do OneDrive
ONEDRIVE_CLIENT_ID = os.environ.get('ONEDRIVE_CLIENT_ID', '')
ONEDRIVE_TENANT_ID = os.environ.get('ONEDRIVE_TENANT_ID', '')
ONEDRIVE_CLIENT_SECRET = os.environ.get('ONEDRIVE_CLIENT_SECRET', '')
ONEDRIVE_REDIRECT_URI = os.environ.get('ONEDRIVE_REDIRECT_URI', '')
ONEDRIVE_BASE_FOLDER = os.environ.get('ONEDRIVE_BASE_FOLDER', '')

# Endpoints Microsoft
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"
AUTH_ENDPOINT = "https://login.microsoftonline.com"

# Scopes necessários para acesso a ficheiros pessoais
SCOPES = [
    "https://graph.microsoft.com/Files.Read",
    "https://graph.microsoft.com/Files.Read.All",
    "https://graph.microsoft.com/User.Read",
    "offline_access"
]


class OneDriveService:
    """
    Serviço de integração com OneDrive para contas pessoais.
    Usa OAuth2 com delegated permissions.
    """
    
    def __init__(self):
        self.client_id = ONEDRIVE_CLIENT_ID
        self.tenant_id = ONEDRIVE_TENANT_ID
        self.client_secret = ONEDRIVE_CLIENT_SECRET
        self.redirect_uri = ONEDRIVE_REDIRECT_URI
        self.base_folder = ONEDRIVE_BASE_FOLDER
        
        # Token cache (em produção usar Redis/DB)
        self._access_token = None
        self._refresh_token = None
        self._token_expires = None
    
    def is_configured(self) -> bool:
        """Verifica se o OneDrive está configurado"""
        return all([self.client_id, self.tenant_id, self.client_secret])
    
    def get_auth_url(self, state: str) -> str:
        """
        Gerar URL de autorização para o utilizador fazer login na Microsoft.
        """
        from urllib.parse import urlencode
        
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "response_mode": "query",
            "scope": " ".join(SCOPES),
            "state": state
        }
        
        # Usar tenant_id para contas de trabalho/escola
        auth_url = f"{AUTH_ENDPOINT}/{self.tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"
        return auth_url
    
    async def exchange_code_for_tokens(self, code: str) -> Dict:
        """
        Trocar código de autorização por tokens de acesso e refresh.
        """
        token_url = f"{AUTH_ENDPOINT}/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(SCOPES)
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, data=data)
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise Exception(f"Falha na autenticação: {response.text}")
            
            tokens = response.json()
            
            # Guardar tokens
            self._access_token = tokens.get("access_token")
            self._refresh_token = tokens.get("refresh_token")
            expires_in = tokens.get("expires_in", 3600)
            self._token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            return {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_in": expires_in
            }
    
    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Usar refresh token para obter novo access token.
        """
        token_url = f"{AUTH_ENDPOINT}/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": " ".join(SCOPES)
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, data=data)
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.text}")
                raise Exception("Falha ao renovar token")
            
            tokens = response.json()
            
            self._access_token = tokens.get("access_token")
            self._refresh_token = tokens.get("refresh_token", refresh_token)
            expires_in = tokens.get("expires_in", 3600)
            self._token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            return {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_in": expires_in
            }
    
    def set_tokens(self, access_token: str, refresh_token: str = None, expires_in: int = 3600):
        """Definir tokens manualmente (carregados da base de dados)"""
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    
    async def get_user_info(self, access_token: str) -> Dict:
        """Obter informação do utilizador autenticado"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{GRAPH_API_ENDPOINT}/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                raise Exception(f"Falha ao obter utilizador: {response.text}")
            
            return response.json()
    
    async def list_folders_in_path(self, access_token: str, path: str = None) -> List[Dict]:
        """
        Listar todas as pastas num caminho específico.
        Se path for None, usa a pasta base configurada.
        """
        folder_path = path or self.base_folder
        
        if not folder_path:
            # Listar raiz
            url = f"{GRAPH_API_ENDPOINT}/me/drive/root/children"
        else:
            # Listar pasta específica
            encoded_path = folder_path.replace(" ", "%20")
            url = f"{GRAPH_API_ENDPOINT}/me/drive/root:/{encoded_path}:/children"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$top": 500}  # Aumentar limite
            )
            
            if response.status_code == 404:
                logger.warning(f"Pasta não encontrada: {folder_path}")
                return []
            
            if response.status_code != 200:
                logger.error(f"Erro ao listar pastas: {response.text}")
                return []
            
            data = response.json()
            folders = []
            
            for item in data.get("value", []):
                if "folder" in item:
                    folders.append({
                        "id": item["id"],
                        "name": item["name"],
                        "path": item.get("parentReference", {}).get("path", ""),
                        "web_url": item.get("webUrl"),
                        "child_count": item.get("folder", {}).get("childCount", 0)
                    })
            
            return folders
    
    async def find_client_folder(
        self, 
        access_token: str, 
        client_name: str,
        threshold: int = 70
    ) -> Optional[Dict]:
        """
        Encontrar pasta do cliente usando fuzzy matching.
        
        Args:
            access_token: Token de acesso
            client_name: Nome do cliente a procurar
            threshold: Limiar mínimo de correspondência (0-100)
        
        Returns:
            Dict com informação da pasta ou None
        """
        folders = await self.list_folders_in_path(access_token)
        
        if not folders:
            logger.warning(f"Nenhuma pasta encontrada para cliente: {client_name}")
            return None
        
        folder_names = [f["name"] for f in folders]
        
        # Usar fuzzy matching para encontrar a melhor correspondência
        # token_set_ratio é melhor para nomes com palavras em ordem diferente
        best_match = fuzzy_process.extractOne(
            client_name,
            folder_names,
            scorer=fuzz.token_set_ratio
        )
        
        if best_match and best_match[1] >= threshold:
            matched_name = best_match[0]
            match_score = best_match[1]
            folder = next(f for f in folders if f["name"] == matched_name)
            
            logger.info(f"Pasta encontrada: '{matched_name}' para cliente '{client_name}' (score: {match_score}%)")
            
            return {
                **folder,
                "match_score": match_score,
                "searched_name": client_name
            }
        
        logger.warning(f"Nenhuma pasta corresponde a '{client_name}' (threshold: {threshold}%)")
        return None
    
    async def list_files_in_folder(self, access_token: str, folder_id: str) -> List[Dict]:
        """
        Listar todos os ficheiros dentro de uma pasta.
        """
        url = f"{GRAPH_API_ENDPOINT}/me/drive/items/{folder_id}/children"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$top": 500}
            )
            
            if response.status_code != 200:
                logger.error(f"Erro ao listar ficheiros: {response.text}")
                return []
            
            data = response.json()
            files = []
            
            for item in data.get("value", []):
                is_folder = "folder" in item
                
                files.append({
                    "id": item["id"],
                    "name": item["name"],
                    "size": item.get("size", 0),
                    "is_folder": is_folder,
                    "mime_type": item.get("file", {}).get("mimeType") if not is_folder else None,
                    "created_at": item.get("createdDateTime"),
                    "modified_at": item.get("lastModifiedDateTime"),
                    "web_url": item.get("webUrl"),
                    "download_url": item.get("@microsoft.graph.downloadUrl")
                })
            
            # Ordenar: pastas primeiro, depois ficheiros por nome
            files.sort(key=lambda x: (not x["is_folder"], x["name"].lower()))
            
            return files
    
    async def get_file_download_url(self, access_token: str, file_id: str) -> Optional[str]:
        """
        Obter URL de download pré-autenticado para um ficheiro.
        O URL é válido por tempo limitado e não requer headers de autorização.
        """
        url = f"{GRAPH_API_ENDPOINT}/me/drive/items/{file_id}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$select": "id,name,@microsoft.graph.downloadUrl,webUrl"}
            )
            
            if response.status_code != 200:
                logger.error(f"Erro ao obter URL de download: {response.text}")
                return None
            
            data = response.json()
            return data.get("@microsoft.graph.downloadUrl") or data.get("webUrl")
    
    async def get_file_preview_url(self, access_token: str, file_id: str) -> Optional[str]:
        """
        Obter URL de preview para documentos Office.
        """
        url = f"{GRAPH_API_ENDPOINT}/me/drive/items/{file_id}/preview"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                # Fallback para URL web normal
                return None
            
            data = response.json()
            return data.get("getUrl")


# Instância global do serviço
onedrive_service = OneDriveService()

# Log do estado da configuração
if onedrive_service.is_configured():
    logger.info("OneDrive: Configuração detectada - a aguardar autenticação OAuth2")
else:
    logger.info("OneDrive: Não configurado - variáveis de ambiente em falta")
