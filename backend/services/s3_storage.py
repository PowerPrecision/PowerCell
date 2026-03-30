"""
S3 Storage Service - Alternativa Robusta ao OneDrive
Usa Amazon S3 (ou Cloudflare R2, MinIO, Google Cloud Storage)
"""
import os
import re
import logging
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Optional, BinaryIO

logger = logging.getLogger(__name__)

# Configurações (Lê das variáveis de ambiente)
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME')
AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-3')

# Categorias de documentos padrão
DEFAULT_CATEGORIES = [
    "Documentos Pessoais",
    "Financeiros", 
    "Imóvel",
    "Bancários",
    "Outros"
]


def sanitize_folder_name(name: str) -> str:
    """Remove caracteres especiais do nome da pasta."""
    if not name:
        return "cliente"
    # Remove acentos e caracteres especiais
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:50] if name else "cliente"


class S3Service:
    def __init__(self):
        self.s3_client = None
        self.bucket_name = AWS_BUCKET_NAME
        if AWS_ACCESS_KEY and AWS_SECRET_KEY:
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=AWS_ACCESS_KEY,
                    aws_secret_access_key=AWS_SECRET_KEY,
                    region_name=AWS_REGION
                )
                logger.info("S3 Service inicializado com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao ligar ao S3: {e}")
        else:
            logger.warning("Credenciais S3 não encontradas. O serviço não funcionará.")

    def is_configured(self) -> bool:
        return self.s3_client is not None and bool(self.bucket_name)

    def _get_client_base_path(
        self, 
        client_id: str, 
        client_name: str,
        second_client_name: str = None
    ) -> str:
        """
        Gera o caminho base para um cliente.
        
        Se houver segundo titular, o nome da pasta incluirá ambos os nomes
        separados por " e " (ex: "João Silva e Maria Santos").
        
        Formato: Documentação Clientes/{nome_completo}
        Se já existir, adiciona incrementador: {nome_completo}_2, {nome_completo}_3, etc.
        
        Args:
            client_id: ID do processo/cliente (usado internamente para verificações)
            client_name: Nome do primeiro titular
            second_client_name: Nome do segundo titular (opcional)
        
        Returns:
            Caminho base no S3
        """
        safe_name = sanitize_folder_name(client_name)
        
        # Incluir segundo titular se existir
        if second_client_name and second_client_name.strip():
            safe_second_name = sanitize_folder_name(second_client_name)
            combined_name = f"{safe_name}_e_{safe_second_name}"
            # Limitar tamanho total para evitar paths muito longos
            if len(combined_name) > 100:
                combined_name = combined_name[:100]
            base_name = combined_name
        else:
            base_name = safe_name
        
        # Verificar se pasta já existe e adicionar incrementador se necessário
        final_name = base_name
        counter = 1
        
        while self._folder_exists(f"Documentação Clientes/{final_name}"):
            counter += 1
            final_name = f"{base_name}_{counter}"
            # Limite de segurança para evitar loop infinito
            if counter > 100:
                # Fallback: usar parte do ID
                final_name = f"{base_name}_{client_id[-6:]}"
                break
        
        return f"Documentação Clientes/{final_name}"
    
    def _get_client_base_path_for_upload(
        self, 
        client_id: str, 
        client_name: str,
        second_client_name: str = None
    ) -> str:
        """
        Gera o caminho base para upload de ficheiros.
        
        IMPORTANTE: Esta função NÃO cria pastas novas com incrementador.
        Se a pasta já existir, usa a existente. Só cria nova se não existir nenhuma.
        
        Args:
            client_id: ID do processo/cliente
            client_name: Nome do primeiro titular
            second_client_name: Nome do segundo titular (opcional)
        
        Returns:
            Caminho base no S3
        """
        # Validar entradas
        if not client_name:
            client_name = "cliente"
        
        try:
            safe_name = sanitize_folder_name(client_name)
        except Exception as e:
            logger.warning(f"Erro ao sanitizar nome do cliente: {e}")
            safe_name = "cliente"
        
        # Incluir segundo titular se existir
        if second_client_name and second_client_name.strip():
            try:
                safe_second_name = sanitize_folder_name(second_client_name)
            except Exception as e:
                logger.warning(f"Erro ao sanitizar nome do segundo titular: {e}")
                safe_second_name = "titular2"
            combined_name = f"{safe_name}_e_{safe_second_name}"
            if len(combined_name) > 100:
                combined_name = combined_name[:100]
            base_name = combined_name
        else:
            base_name = safe_name
        
        # PRIMEIRO: Tentar encontrar pasta existente (case-insensitive)
        # Isto é crucial para evitar criar pastas duplicadas
        try:
            existing_folder = self._find_client_folder_combined(client_name, second_client_name)
            if existing_folder:
                logger.info(f"Pasta existente encontrada para {client_name}: {existing_folder}")
                return existing_folder
        except Exception as e:
            logger.warning(f"Erro ao procurar pasta existente: {e}")
            # Continuar com o nome sanitizado
        
        # Se não existe, usar o nome sanitizado (sem incrementador)
        base_path = f"Documentação Clientes/{base_name}"
        logger.info(f"Nova pasta será usada para {client_name}: {base_path}")
        return base_path
    
    def _find_client_folder_combined(self, client_name: str, second_client_name: str = None) -> Optional[str]:
        """
        Procura a pasta real do cliente no S3, suportando clientes com dois titulares.
        Faz match case-insensitive e flexível para encontrar a pasta correta.
        """
        if not self.is_configured() or not client_name:
            return None
        
        try:
            # Listar pastas em "Documentação Clientes/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="Documentação Clientes/",
                Delimiter="/"
            )
            
            # Se não houver pastas, retornar None
            if not response.get("CommonPrefixes"):
                return None
            
            # Construir nome de busca
            clean_name = client_name.strip() if client_name else ""
            if not clean_name:
                return None
            search_name = clean_name.lower()
            
            # Se há segundo titular, incluir na busca
            if second_client_name and second_client_name.strip():
                clean_second = second_client_name.strip()
                search_name = f"{clean_name.lower()} e {clean_second.lower()}"
                # Também buscar versão com underscore
                safe_name = sanitize_folder_name(client_name)
                safe_second = sanitize_folder_name(second_client_name)
                search_name_underscore = f"{safe_name.lower()}_e_{safe_second.lower()}"
            else:
                search_name_underscore = sanitize_folder_name(client_name).lower()
            
            best_match = None
            best_score = 0
            
            for prefix in response.get("CommonPrefixes", []):
                folder_path = prefix.get("Prefix", "").rstrip("/")
                folder_name = folder_path.replace("Documentação Clientes/", "")
                folder_lower = folder_name.lower()
                
                # Match exato (case-insensitive)
                if folder_lower == search_name or folder_lower == search_name_underscore:
                    return folder_path
                
                # Match flexível - calcular score de similaridade
                # Comparar palavras
                search_words = set(search_name.replace("_", " ").split())
                folder_words = set(folder_lower.replace("_", " ").split())
                
                # Ignorar palavras comuns que não ajudam no match
                common_words = {"de", "da", "do", "dos", "das", "e", "a", "o"}
                search_words_filtered = search_words - common_words
                folder_words_filtered = folder_words - common_words
                
                if search_words_filtered and folder_words_filtered:
                    # Calcular interseção
                    intersection = search_words_filtered & folder_words_filtered
                    max_len = max(len(search_words_filtered), len(folder_words_filtered))
                    if max_len > 0:
                        score = len(intersection) / max_len
                    
                    # Bonus se o primeiro nome está presente
                    first_name_parts = clean_name.split()
                    if first_name_parts:
                        first_name = first_name_parts[0].lower()
                        if first_name in folder_lower:
                            score += 0.2
                    
                    # Bonus se segundo titular está presente
                    if second_client_name and second_client_name.strip():
                        second_parts = second_client_name.strip().split()
                        if second_parts:
                            second_first_name = second_parts[0].lower()
                            if second_first_name in folder_lower:
                                score += 0.2
                    
                    if score > best_score and score >= 0.7:
                        best_score = score
                        best_match = folder_path
            
            if best_match:
                logger.info(f"Encontrada pasta por similaridade ({best_score:.2f}): {best_match}")
                return best_match
                        
        except Exception as e:
            logger.warning(f"Erro ao procurar pasta do cliente: {e}")
        
        return None
    
    def _folder_exists(self, folder_path: str) -> bool:
        """
        Verifica se uma pasta existe no S3.
        Uma pasta "existe" se houver pelo menos um objecto com esse prefixo.
        """
        if not self.is_configured():
            return False
        
        try:
            # Garantir que o path termina com /
            prefix = folder_path if folder_path.endswith('/') else f"{folder_path}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=1
            )
            return response.get('KeyCount', 0) > 0
        except ClientError:
            return False

    def upload_file(
        self, 
        file_obj: BinaryIO, 
        client_id: str,
        client_name: str,
        category: str, 
        filename: str, 
        content_type: str = None,
        second_client_name: str = None,
        s3_folder: str = None
    ) -> Optional[str]:
        """
        Faz upload de um ficheiro para a pasta do cliente numa categoria específica.
        
        Args:
            file_obj: Objeto de ficheiro
            client_id: ID do processo/cliente
            client_name: Nome do cliente
            category: Categoria (ex: "Financeiros", "Documentos Pessoais")
            filename: Nome do ficheiro
            content_type: MIME type do ficheiro
            second_client_name: Nome do segundo titular (opcional)
            s3_folder: Pasta S3 configurada manualmente (prioridade máxima)
            
        Returns:
            Caminho S3 do ficheiro ou None se falhar
        """
        if not self.is_configured():
            logger.error("S3 não configurado")
            return None

        # Usar s3_folder configurado se existir, senão usar path automático
        if s3_folder:
            base_path = s3_folder.rstrip('/')
        else:
            base_path = self._get_client_base_path_for_upload(client_id, client_name, second_client_name)
        
        # Categoria "all" deve ser tratada como "Outros"
        if category.lower() == "all":
            category = "Outros"
        
        safe_category = sanitize_folder_name(category)
        object_name = f"{base_path}/{safe_category}/{filename}"

        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type

        try:
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs=extra_args if extra_args else None
            )
            logger.info(f"Upload S3 sucesso: {object_name}")
            return object_name
        except ClientError as e:
            logger.error(f"Erro no upload para S3: {e}")
            return None

    def list_files(
        self, 
        client_id: str, 
        client_name: str,
        second_client_name: str = None,
        s3_folder: str = None
    ) -> Dict[str, List[Dict]]:
        """
        Lista todos os ficheiros de um cliente organizados por categoria.
        
        Suporta:
        - Ficheiros em subpastas categorizadas (Pessoais/, Financeiros/, etc.)
        - Ficheiros directamente na raiz da pasta do cliente (categoria "Outros")
        - Paths com espaços e com underscores
        - Mapeamento S3 configurado manualmente (s3_folder)
        
        Args:
            client_id: ID do processo/cliente
            client_name: Nome do cliente
            second_client_name: Nome do segundo titular (opcional)
            s3_folder: Pasta S3 configurada manualmente (prioridade máxima)
        
        Returns:
            Dict com categorias como chaves e listas de ficheiros como valores
        """
        if not self.is_configured():
            return {"error": "S3 não configurado", "files": {}}

        # Se temos um s3_folder configurado, usar como primeira opção
        possible_paths = []
        if s3_folder:
            # Remover trailing slash se existir
            s3_folder = s3_folder.rstrip('/')
            possible_paths.append(s3_folder)
        
        # Adicionar paths automáticos como fallback
        possible_paths.extend(self._get_possible_client_paths(client_id, client_name, second_client_name))
        
        files_by_category = {cat: [] for cat in DEFAULT_CATEGORIES}
        found_path = None
        
        for base_path in possible_paths:
            prefix = f"{base_path}/"
            
            try:
                # Usar paginator para lidar com muitos ficheiros
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
                
                for page in pages:
                    if 'Contents' not in page:
                        continue
                    
                    # Se encontrou ficheiros, registar o path
                    if not found_path:
                        found_path = base_path
                        
                    for obj in page['Contents']:
                        key = obj['Key']
                        
                        # Ignorar ficheiros .keep (marcadores de pasta)
                        if key.endswith('.keep'):
                            continue
                        
                        # Extrair categoria do path
                        relative_path = key.replace(prefix, '')
                        parts = relative_path.split('/')
                        
                        # Se ficheiro está na raiz (sem subpasta), colocar em "Outros"
                        if len(parts) == 1:
                            category = "Outros"
                            filename = parts[0]
                        else:
                            # Formato: {categoria}/{ficheiro}
                            category_raw = parts[0].replace('_', ' ')
                            filename = parts[-1]
                            
                            # Categoria "all" deve ser tratada como "Outros"
                            if category_raw.lower() == "all":
                                category = "Outros"
                            else:
                                # Encontrar categoria correspondente
                                category = "Outros"
                                for cat in DEFAULT_CATEGORIES:
                                    if cat.lower().replace(' ', '_') == category_raw.lower().replace(' ', '_'):
                                        category = cat
                                        break
                                    # Match parcial (ex: "Pessoais" match "Documentos Pessoais")
                                    if category_raw.lower() in cat.lower() or cat.lower() in category_raw.lower():
                                        category = cat
                                        break
                        
                        file_info = {
                            "name": filename,
                            "path": key,
                            "size": obj['Size'],
                            "size_formatted": self._format_size(obj['Size']),
                            "last_modified": obj['LastModified'].isoformat(),
                            "category": category,
                            "temporary_url": self.get_presigned_url(key) or ""
                        }
                        
                        if category in files_by_category:
                            files_by_category[category].append(file_info)
                        else:
                            files_by_category["Outros"].append(file_info)
                
                # Se encontrou ficheiros neste path, não precisa continuar
                if found_path:
                    break
                    
            except ClientError as e:
                logger.warning(f"Erro ao listar path {prefix}: {e}")
                continue
        
        # Calcular estatísticas
        total_files = sum(len(files) for files in files_by_category.values())
        total_size = sum(
            f['size'] 
            for files in files_by_category.values() 
            for f in files
        )
        
        return {
            "files": files_by_category,
            "categories": DEFAULT_CATEGORIES,
            "stats": {
                "total_files": total_files,
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size)
            },
            "base_path": found_path
        }
    
    def _get_possible_client_paths(
        self, 
        client_id: str, 
        client_name: str,
        second_client_name: str = None
    ) -> List[str]:
        """
        Retorna lista de possíveis paths para a pasta do cliente.
        Inclui variações de case para compatibilidade com S3 (case-sensitive).
        """
        paths = []
        
        if not client_name:
            return paths
        
        # Nome limpo (sem caracteres especiais perigosos, mas mantendo espaços)
        clean_name = client_name.strip()
        
        # Nome sanitizado (espaços substituídos por underscores)
        safe_name = sanitize_folder_name(client_name)
        
        # Variações de capitalização comuns
        name_variations = [
            clean_name,                          # Original: "Flávio Fonseca Da Silva"
            clean_name.title(),                  # Title: "Flávio Fonseca Da Silva"
            ' '.join(w.capitalize() if len(w) > 2 else w.lower() for w in clean_name.split()),  # "Flávio Fonseca da Silva"
        ]
        # Remover duplicados mantendo ordem
        name_variations = list(dict.fromkeys(name_variations))
        
        # Segundo titular
        if second_client_name and second_client_name.strip():
            clean_second = second_client_name.strip()
            safe_second = sanitize_folder_name(second_client_name)
            
            for name_var in name_variations:
                paths.append(f"Documentação Clientes/{name_var} e {clean_second}")
            paths.append(f"Documentação Clientes/{safe_name}_e_{safe_second}")
        else:
            for name_var in name_variations:
                paths.append(f"Documentação Clientes/{name_var}")
            paths.append(f"Documentação Clientes/{safe_name}")
        
        # Também tentar encontrar pasta real no S3 (case-insensitive search)
        real_folder = self._find_client_folder(clean_name)
        if real_folder and real_folder not in paths:
            paths.insert(0, real_folder)  # Prioridade máxima
        
        return paths
    
    def _find_client_folder(self, client_name: str) -> Optional[str]:
        """
        Procura a pasta real do cliente no S3 fazendo match case-insensitive.
        """
        if not self.is_configured() or not client_name:
            return None
        
        try:
            # Listar pastas em "Documentação Clientes/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="Documentação Clientes/",
                Delimiter="/"
            )
            
            # Procurar pasta que match o nome do cliente (case-insensitive)
            search_name = client_name.lower().strip()
            
            for prefix in response.get("CommonPrefixes", []):
                folder_path = prefix.get("Prefix", "").rstrip("/")
                folder_name = folder_path.replace("Documentação Clientes/", "")
                
                if folder_name.lower() == search_name:
                    return folder_path
                
                # Match parcial (primeiros nomes)
                if search_name.split()[0].lower() in folder_name.lower():
                    # Verificar se é o mesmo cliente comparando mais palavras
                    search_words = set(search_name.lower().split())
                    folder_words = set(folder_name.lower().split())
                    # Se mais de 80% das palavras coincidem
                    if len(search_words & folder_words) >= len(search_words) * 0.8:
                        return folder_path
                        
        except Exception as e:
            logger.warning(f"Erro ao procurar pasta do cliente: {e}")
        
        return None

    def _format_size(self, size_bytes: int) -> str:
        """Formata tamanho em bytes para formato legível."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def file_exists(self, object_name: str) -> bool:
        """
        Verifica se um ficheiro existe no S3.
        
        Args:
            object_name: Caminho S3 do ficheiro
            
        Returns:
            True se existe, False caso contrário
        """
        if not self.is_configured():
            return False
            
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=object_name
            )
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                return False
            logger.error(f"Erro ao verificar ficheiro S3: {e}")
            return False

    def get_presigned_url(self, object_name: str, expiration: int = 3600) -> Optional[str]:
        """
        Gera um link temporário (1 hora por defeito) para download/visualização.
        
        Args:
            object_name: Caminho S3 do ficheiro
            expiration: Tempo de validade em segundos
            
        Returns:
            URL pré-assinado ou None se falhar
        """
        if not self.is_configured():
            return None
            
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_name},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Erro ao gerar link S3: {e}")
            return None

    def delete_file(self, object_name: str) -> bool:
        """
        Elimina um ficheiro do S3.
        
        Args:
            object_name: Caminho S3 do ficheiro
            
        Returns:
            True se eliminado com sucesso
        """
        if not self.is_configured():
            return False
            
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            logger.info(f"Ficheiro eliminado: {object_name}")
            return True
        except ClientError as e:
            logger.error(f"Erro ao eliminar ficheiro S3: {e}")
            return False

    def initialize_client_folders(
        self, 
        client_id: str, 
        client_name: str,
        second_client_name: str = None
    ) -> tuple:
        """
        Cria a estrutura de pastas padrão para um novo cliente.
        No S3, cria-se um ficheiro vazio '.keep' para marcar a pasta.
        
        Args:
            client_id: ID do processo/cliente
            client_name: Nome do cliente
            second_client_name: Nome do segundo titular (opcional)
            
        Returns:
            Tuplo (success: bool, folder_path: str ou None)
            - (True, "Documentação Clientes/Nome_Cliente") se criado com sucesso
            - (False, None) se falhou
        """
        if not self.is_configured():
            return (False, None)
            
        base_path = self._get_client_base_path(client_id, client_name, second_client_name)
        
        try:
            for category in DEFAULT_CATEGORIES:
                safe_category = sanitize_folder_name(category)
                path = f"{base_path}/{safe_category}/.keep"
                self.s3_client.put_object(
                    Bucket=self.bucket_name, 
                    Key=path,
                    Body=b''
                )
            logger.info(f"Estrutura de pastas criada para cliente: {client_id} -> {base_path}")
            return (True, base_path)
        except ClientError as e:
            logger.error(f"Erro ao criar pastas S3: {e}")
            return (False, None)


    def get_file_content(self, object_name: str) -> Optional[bytes]:
        """
        Obtém o conteúdo de um ficheiro do S3.
        Tenta variações do path (underscore <-> espaço) se o original falhar.
        
        Args:
            object_name: Caminho S3 do ficheiro
            
        Returns:
            Bytes do ficheiro ou None se falhar
        """
        if not self.is_configured():
            logger.error("S3 não configurado")
            return None
        
        # Gerar variações do path
        variations = [object_name]
        
        # Variação com underscores -> espaços
        if '_' in object_name:
            variations.append(object_name.replace('_', ' '))
        
        # Variação com espaços -> underscores
        if ' ' in object_name:
            variations.append(object_name.replace(' ', '_'))
        
        # Variação com a pasta base
        if 'Documentação Clientes/' in object_name:
            variations.append(object_name.replace('Documentação Clientes/', 'Documentação_Clientes/'))
        if 'Documentação_Clientes/' in object_name:
            variations.append(object_name.replace('Documentação_Clientes/', 'Documentação Clientes/'))
        
        for path in variations:
            try:
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name, 
                    Key=path
                )
                logger.debug(f"Ficheiro S3 obtido com sucesso: {path}")
                return response['Body'].read()
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'NoSuchKey':
                    logger.debug(f"Path não encontrado no S3: {path}")
                    continue
                else:
                    logger.error(f"Erro S3 ({error_code}) ao obter ficheiro {path}: {e}")
                    return None
        
        logger.warning(f"Ficheiro não encontrado no S3 (tentadas {len(variations)} variações): {object_name}")
        return None

    def move_file(
        self,
        source_path: str,
        client_name: str,
        target_folder: str,
        file_name: str
    ) -> bool:
        """
        Move um ficheiro para uma nova pasta no S3.
        
        Args:
            source_path: Caminho S3 atual do ficheiro
            client_name: Nome do cliente
            target_folder: Nome da pasta destino (ex: "Pessoais", "Financeiros")
            file_name: Nome do ficheiro
            
        Returns:
            True se movido com sucesso
        """
        if not self.s3_client:
            logger.error("S3 não configurado")
            return False
            
        try:
            # Obter pasta base do cliente
            client_folder = self._find_client_folder(client_name)
            if not client_folder:
                logger.error(f"Pasta do cliente não encontrada: {client_name}")
                return False
            
            # Construir caminho destino
            target_path = f"{client_folder}{target_folder}/{file_name}"
            
            # Copiar ficheiro para novo destino
            copy_source = {'Bucket': self.bucket_name, 'Key': source_path}
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=target_path
            )
            
            # Apagar ficheiro original
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=source_path
            )
            
            logger.info(f"Ficheiro movido: {source_path} -> {target_path}")
            return True
            
        except ClientError as e:
            logger.error(f"Erro ao mover ficheiro S3: {e}")
            return False

    def rename_file(self, old_path: str, new_path: str) -> bool:
        """
        Renomeia um ficheiro no S3 (copia para novo caminho + apaga original).
        
        Args:
            old_path: Caminho S3 atual do ficheiro
            new_path: Novo caminho S3 do ficheiro
            
        Returns:
            True se renomeado com sucesso
        """
        if not self.s3_client:
            logger.error("S3 não configurado")
            return False
            
        if old_path == new_path:
            logger.info("Caminhos iguais, nada a fazer")
            return True
            
        try:
            # Copiar ficheiro para novo caminho
            copy_source = {'Bucket': self.bucket_name, 'Key': old_path}
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=new_path
            )
            
            # Apagar ficheiro original
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=old_path
            )
            
            logger.info(f"Ficheiro renomeado: {old_path} -> {new_path}")
            return True
            
        except ClientError as e:
            logger.error(f"Erro ao renomear ficheiro S3: {e}")
            return False


# Instância global
s3_service = S3Service()