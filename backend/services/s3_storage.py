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
from services.s3_document_root import pasta_gravada

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
    "RGPD",
    "Outros"
]

# Mapping from portal document categories to S3 admin categories.
# When a client uploads via the portal with a portal category (e.g. "Cartao_Cidadao"),
# the file is stored in the corresponding S3 admin category folder (e.g. "Documentos_Pessoais").
PORTAL_TO_S3_CATEGORY = {
    "Cartao_Cidadao": "Documentos Pessoais",
    "Certidao_Nascimento": "Documentos Pessoais",
    "Atestado_Trabalho": "Documentos Pessoais",
    "Certidao_Permanente": "Documentos Pessoais",
    "IRS": "Financeiros",
    "Recibo_Vencimento": "Financeiros",
    "Declaracao_Imposto_Renda": "Financeiros",
    "Mapa_Creditos": "Financeiros",
    "Comprovativo_IBAN": "Bancários",
    "Contrato_Promessa": "Imóvel",
    "Plantas_Casa": "Imóvel",
    "Certificado_Energetico": "Imóvel",
    "Outros": "Outros",
}


def sanitize_folder_name(name: str) -> str:
    """Remove caracteres especiais do nome da pasta."""
    if not name:
        return "cliente"
    # Remove acentos e caracteres especiais
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:50] if name else "cliente"


class S3Service:
    """
    Serviço de armazenamento de documentos em Amazon S3 para o CRM de crédito habitação.

    Gestiona toda a documentação dos clientes (pessoal, financeira, imobiliária, RGPD)
    numa estrutura hierárquica organizada por cliente e categoria. O S3 substitui
    o OneDrive como repositório principal, oferecendo melhor integração com pre-signed
    URLs (uploads diretos do frontend sem passar pelo backend) e maior fiabilidade.

    Caminhos seguem o formato: ``Documentação Clientes/{Nome_Cliente}/{Categoria}/{Ficheiro}``

    Categorias padrão: Documentos Pessoais, Financeiros, Imóvel, Bancários, RGPD, Outros.
    """

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
                self._ensure_cors_configured()
            except Exception as e:
                logger.error(f"Erro ao ligar ao S3: {e}")
        else:
            logger.warning("Credenciais S3 não encontradas. O serviço não funcionará.")

    def reconfigure(self, access_key: str, secret_key: str, bucket_name: str, region: str = "eu-west-3"):
        """Reinitialize S3 client with new credentials (e.g., from UI config)."""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region
            )
            self.bucket_name = bucket_name
            logger.info(f"S3 Service reconfigurado com sucesso. Bucket: {bucket_name}, Region: {region}")
            self._ensure_cors_configured()
            return True
        except Exception as e:
            logger.error(f"Erro ao reconfigurar S3: {e}")
            self.s3_client = None
            return False

    def _ensure_cors_configured(self):
        """
        Garante que o bucket S3 tem CORS configurado para uploads diretos do browser.

        Necessário para pre-signed URL uploads do Portal do Cliente e do CRM.
        Sem CORS, o browser bloqueia o PUT request ao S3 com erro:
        'No Access-Control-Allow-Origin header is present'.

        IMPORTANTE: Sempre substitui a config CORS existente para garantir
        que as origens correctas estão incluídas.

        Estratégia de CORS:
        - Regra 1: Origens explícitas (produção, dev, Render)
        - Regra 2: * (curinga) para Vercel previews e outros domínios dinâmicos
          Isto é seguro porque o bucket é privado e todo acesso requer
          URLs pre-assinadas com assinatura criptográfica + expiração.
          CORS é apenas um mecanismo do browser, não adiciona segurança real.
        """
        if not self.s3_client or not self.bucket_name:
            return

        # Ler origens do config.py (falha graciosamente se não disponível).
        #
        # BUGFIX (Set 2026): o import era `from backend.config import ...`, mas a
        # aplicação corre com `backend/` como raiz do sys.path — o pacote
        # `backend` NUNCA existe em runtime. O ImportError caía sempre no
        # `except`, pelo que o bucket recebia a lista hardcoded de PRODUÇÃO
        # independentemente do ambiente: o bucket de dev era configurado com as
        # origens de prod e a variável CORS_ORIGINS não tinha qualquer efeito.
        explicit_origins = []
        try:
            from config import CORS_ORIGINS
            explicit_origins = list(CORS_ORIGINS)
        except Exception as exc:
            # Fallback para origens hardcoded se config não estiver disponível
            logger.warning(
                f"CORS_ORIGINS indisponível ({exc}); a usar a lista de origens por omissão. "
                "Defina CORS_ORIGINS no ambiente para controlar as origens do bucket."
            )
            explicit_origins = [
                'https://powercell.pt',
                'https://www.powercell.pt',
                'https://powercell-1.onrender.com',
                'https://powercell.onrender.com',
                'http://localhost:3000',
                'http://localhost:5173',
                'http://localhost:5000',
                'http://127.0.0.1:3000',
                'http://127.0.0.1:5173',
            ]

        cors_config = {
            'CORSRules': [
                # Regra 1: Origens explícitas
                {
                    'AllowedHeaders': ['Content-Type', 'x-amz-*'],
                    'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
                    'AllowedOrigins': explicit_origins,
                    'ExposeHeaders': [
                        'ETag',
                        'x-amz-request-id',
                        'x-amz-id-2',
                    ],
                    'MaxAgeSeconds': 3600,
                },
                # Regra 2: Curinga para Vercel previews e domínios dinâmicos
                # Seguro: bucket privado, URLs pre-assinadas com expiração
                {
                    'AllowedHeaders': ['Content-Type', 'x-amz-*'],
                    'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
                    'AllowedOrigins': ['*'],
                    'ExposeHeaders': [
                        'ETag',
                        'x-amz-request-id',
                        'x-amz-id-2',
                    ],
                    'MaxAgeSeconds': 3600,
                },
            ]
        }

        try:
            self.s3_client.put_bucket_cors(
                Bucket=self.bucket_name,
                CORSConfiguration=cors_config
            )
            logger.info(f"✅ S3 CORS configurado com sucesso ({len(explicit_origins)} origens explícitas + curinga).")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"❌ Erro ao configurar CORS no S3 [{error_code}]: {error_msg}")
            logger.error("   A IAM key pode não ter permissão s3:PutBucketCORS.")
            logger.error("   Configure manualmente na AWS Console > S3 > Bucket > Permissions > CORS.")
            logger.error("   CORS config pretendida:")
            for rule in cors_config['CORSRules']:
                logger.error(f"     Origens: {rule['AllowedOrigins']}")

    def is_configured(self) -> bool:
        """Verifica se o serviço S3 está pronto para operações.

        Returns:
            bool: True se o cliente S3 foi inicializado com sucesso e
                ``bucket_name`` está definido.
        """
        return self.s3_client is not None and bool(self.bucket_name)

    def _get_client_base_path_for_upload(
        self,
        client_id: str,
        client_name: str = None,
        second_client_name: str = None,
        *,
        owner_client_id: str = None,
    ) -> Optional[str]:
        """
        O caminho base da pasta de uma entidade — derivado do ID, nunca do nome.

        LOTE 6, ponto 1 — A COLISÃO DE IDENTIDADE
        =========================================
        Esta função derivava o caminho do NOME e, antes de o usar, procurava
        uma pasta parecida (`_find_client_folder_combined`, score >= 0.7). Os
        documentos de uma cliente nova ("Carolina Agostinho da Silva") foram
        por isso servidos na pasta de uma existente ("Carolina Silva"):
        2/3 de palavras em comum + 0.2 de bónus pelo primeiro nome = 0.867.

        E não havia rede: a única função que acrescentava `_2` a um nome
        repetido (`_get_client_base_path`) **não tinha um único chamador** e
        foi apagada com esta correcção — dois clientes com o mesmo nome nunca
        tiveram pastas separadas, por muito que o `s3_folder_relink`
        documentasse o contrário.

        Hoje a identidade é o id, e o ponto único é `services.s3_document_root`.

        `client_name` fica na assinatura porque todos os chamadores o passam
        (e é útil no log), mas **não participa no caminho**. Devolver `None`
        quando o id não serve é deliberado: um caminho adivinhado grava-se uma
        vez e vale para sempre.

        Args:
            client_id: id da entidade a mapear (cliente OU processo).
            client_name: só para o log.
            second_client_name: ignorado (vivia no nome da pasta).
            owner_client_id: quando dado e diferente, `client_id` é um
                PROCESSO e a pasta nasce sob a do cliente.
        """
        from services.s3_document_root import pasta_do_cliente, pasta_do_processo

        if owner_client_id and owner_client_id != client_id:
            caminho = pasta_do_processo(client_id, client_id=owner_client_id)
        else:
            caminho = pasta_do_cliente(client_id)

        if caminho is None:
            logger.error(
                "[S3-PATH] Id inutilizável como pasta (%r, cliente=%r) — "
                "recusado em vez de derivar do nome.",
                client_id, client_name,
            )
            return None
        return caminho

    def _find_client_folder_combined(
        self, client_name: str, second_client_name: str = None
    ) -> Optional[str]:
        """
        Procura a pasta de um cliente por nome EXACTO (ignorando maiúsculas).

        LOTE 6 — O SCORE SAIU DAQUI
        ===========================
        Havia um match flexível: palavras em comum / palavras totais, mais 0.2
        se o primeiro nome aparecesse na pasta, aceitando a partir de 0.7.
        "Carolina Agostinho da Silva" contra a pasta `carolina_silva` dava
        **0.867** e as duas fichas passavam a partilhar documentação. A
        assinatura era "mesmo primeiro nome + um conjunto de nomes contido no
        outro" — mãe e filha, dois irmãos, e sobretudo a MESMA pessoa inserida
        com nome curto e com nome completo.

        O que fica é o match EXACTO, nas duas grafias que o sistema produz
        (com espaços e com underscores). Serve para:
          * **ler** a pasta de um processo legado sem `s3_folder` gravado
            (`_get_possible_client_paths`), onde não devolver nada esconderia
            documentos que existem;
          * **sugerir** uma pasta ao administrador no religamento manual.

        NUNCA para decidir onde um upload NOVO vai: essa identidade sai do id
        (`_get_client_base_path_for_upload`). Homónimos exactos continuam a
        colidir na LEITURA legada — é residual, está em `TECHNICAL_DEBT.md` e
        a saída é o religamento manual.
        """
        if not self.is_configured() or not client_name:
            return None

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="Documentação Clientes/",
                Delimiter="/",
            )
            if not response.get("CommonPrefixes"):
                return None

            for alvo in self._nomes_de_pasta_candidatos(
                client_name, second_client_name
            ):
                for prefix in response.get("CommonPrefixes", []):
                    folder_path = prefix.get("Prefix", "").rstrip("/")
                    folder_name = folder_path.replace("Documentação Clientes/", "")
                    if folder_name.lower() == alvo:
                        return folder_path
        except Exception as e:
            logger.warning(f"Erro ao procurar pasta do cliente: {e}")

        return None

    def _nomes_de_pasta_candidatos(
        self, client_name: str, second_client_name: str = None
    ) -> List[str]:
        """As grafias EXACTAS que o sistema já produziu para este nome.

        Duas, porque houve dois escritores: com espaços (`João Silva e Maria`)
        e sanitizado (`Joao_Silva_e_Maria`). Em minúsculas, para a comparação
        ser insensível a maiúsculas sem ser insensível a palavras.
        """
        nome = (client_name or "").strip()
        if not nome:
            return []
        segundo = (second_client_name or "").strip()
        if segundo:
            candidatos = [
                f"{nome} e {segundo}",
                f"{sanitize_folder_name(nome)}_e_{sanitize_folder_name(segundo)}",
            ]
        else:
            candidatos = [nome, sanitize_folder_name(nome)]
        vistos: List[str] = []
        for c in candidatos:
            baixo = c.lower()
            if baixo and baixo not in vistos:
                vistos.append(baixo)
        return vistos

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
        Carrega um ficheiro para a pasta do cliente numa categoria específica no S3.

        Este é o método principal de persistência de documentos do CRM. Todos os
        ficheiros enviados pelos consultores ou extraídos por IA passam por aqui.
        A organização por categoria (Pessoais, Financeiros, etc.) reflete a
        estrutura exigida pelos bancos no processo de crédito habitação.

        Se ``s3_folder`` for fornecido, é utilizado como caminho base (prioridade
        máxima), permitindo sobrescrever a localização automática quando o
        consultor configura manualmente a pasta do cliente.

        Args:
            file_obj: Objeto de ficheiro aberto em modo binário.
            client_id: ID do processo/cliente (usado para resolução de conflitos).
            client_name: Nome do primeiro titular para construção do caminho.
            category: Categoria de destino (ex: "Financeiros", "Documentos Pessoais").
            filename: Nome do ficheiro (ex: "recibo_vencimento_dez2024.pdf").
            content_type: Tipo MIME do ficheiro (ex: "application/pdf").
            second_client_name: Nome do segundo titular (para compras conjuntas).
            s3_folder: Caminho S3 configurado manualmente (substitui path automático).

        Returns:
            str: Caminho S3 completo do ficheiro carregado, ou ``None`` se
                o serviço não estiver configurado ou ocorrer um erro de upload.
        """
        if not self.is_configured():
            logger.error("S3 não configurado")
            return None

        # Usar s3_folder configurado se existir, senão usar path automático.
        # `pasta_gravada` porque uma lista é truthy: o `if` passava e o
        # `.rstrip` rebentava na linha seguinte (Lote 8). Um valor
        # ilegível vira `None` e o caminho deriva do ID, nunca do nome.
        pasta_do_mapeamento = pasta_gravada(
            s3_folder, contexto=f"upload de {client_id}"
        )
        if pasta_do_mapeamento:
            base_path = pasta_do_mapeamento.rstrip('/')
        else:
            base_path = self._get_client_base_path_for_upload(client_id, client_name, second_client_name)
        if not base_path:
            # Id inutilizável: recusa-se em vez de escrever num caminho
            # adivinhado a partir do nome (Lote 6, ponto 1).
            return None
        
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
        except Exception as e:
            logger.error(f"Erro inesperado no upload para S3: {e}", exc_info=True)
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

        # CRÍTICO: Se temos um s3_folder configurado, usar APENAS esse mapeamento.
        # NÃO adicionar fallbacks por nome — isso listaria ficheiros de outro
        # cliente de nome parecido depois de a pasta ficar vazia.
        #
        # LOTE 6: com a pasta do processo a viver DENTRO da do cliente, um
        # mapeamento de processo lê-se como UNIÃO (a subpasta do processo + a
        # raiz do cliente sem a subárvore `processos/`). Sem isso, tudo o que o
        # cliente enviou antes de o processo existir — o onboarding do Portal
        # inteiro — desaparecia do separador Documentos, e um documento que
        # desaparece não produz erro nenhum.
        #
        # `parar_no_primeiro` distingue as duas intenções: a união TEM de varrer
        # todos os prefixos; o recurso por nome continua a parar no primeiro que
        # dê ficheiros (é uma lista de palpites de grafia, não um conjunto).
        from services.s3_document_root import (
            Leitura,
            chave_pertence_a_leitura,
            leituras_do_mapeamento,
        )

        # Ver a nota em `upload_file`: o tipo vem primeiro que a verdade.
        # Com mapeamento ilegível cai-se no recurso por nome, que é o
        # degradado certo para uma LEITURA (os documentos podem estar lá).
        s3_folder = pasta_gravada(
            s3_folder, contexto=f"listagem de {client_id}"
        )
        if s3_folder:
            s3_folder = s3_folder.rstrip('/')
            leituras = leituras_do_mapeamento(s3_folder)
            parar_no_primeiro = False
        else:
            leituras = [
                Leitura(prefixo=caminho)
                for caminho in self._get_possible_client_paths(
                    client_id, client_name, second_client_name
                )
            ]
            parar_no_primeiro = True

        files_by_category = {cat: [] for cat in DEFAULT_CATEGORIES}
        found_path = None

        for leitura in leituras:
            base_path = leitura.prefixo
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

                        # Na raiz do CLIENTE, os documentos dos processos ficam
                        # de fora: são do processo do lado, não deste.
                        if not chave_pertence_a_leitura(key, leitura):
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
                
                # Recurso por nome: o primeiro path que dê ficheiros ganha.
                # Na união (mapeamento por id) varrem-se TODOS os prefixos.
                if found_path and parar_no_primeiro:
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
                
                # Só match EXACTO (ver `_find_client_folder_combined`): o
                # ramo dos 80% de palavras em comum ligava "Ana Costa" à
                # pasta "Ana Maria Costa" e vice-versa.
                if folder_name.lower() == search_name:
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

    # ================================================================
    # QUARENTENA DE CONTEÚDO — primitivas de CHAVE EXACTA
    # ================================================================
    # Estas duas existem para a validação pós-upload do Portal
    # (`services/s3_content_quarantine.py`) e têm duas diferenças
    # deliberadas em relação ao `get_file_content`:
    #
    #   1. **Chave EXACTA, sem variações.** O `get_file_content` tenta
    #      variantes do caminho (underscore <-> espaço) para sobreviver a
    #      dados legados. Numa parede de segurança isso seria fatal:
    #      inspeccionar-se-iam os bytes de UMA chave e gravava-se OUTRA no
    #      registo. O que se valida tem de ser exactamente o que se guarda.
    #   2. **Nunca descarregam o ficheiro inteiro.** O `head` traz só
    #      metadados e o `prefixo` traz N bytes por `Range`. Um upload de
    #      5 GB não pode passar pela RAM do worker só para se lerem os
    #      primeiros 2 KB.

    def head_object_metadata(self, object_name: str) -> tuple[str, Optional[dict]]:
        """Metadados REAIS do objecto (tamanho e tipo declarado no S3).

        Devolve um estado de TRÊS valores porque a pergunta tem três
        respostas e confundi-las é o que transforma uma falha de
        infraestrutura numa acusação ao utilizador:

            ("ok", {"tamanho": int, "tipo": str, "etag": str})
            ("ausente", None)   -> o objecto não existe (404)
            ("erro", None)      -> falha transitória (rede, credenciais, 5xx)

        Quem chama trata "ausente" e "erro" de maneira DIFERENTE: o
        primeiro é culpa do upload, o segundo não é culpa de ninguém — e
        apagar o objecto por causa do segundo destruiria um ficheiro
        legítimo.
        """
        if not self.is_configured():
            return "erro", None

        try:
            resposta = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=object_name,
            )
        except ClientError as e:
            codigo = str(e.response.get('Error', {}).get('Code', ''))
            if codigo in ('404', 'NoSuchKey', 'NotFound'):
                return "ausente", None
            logger.error(f"Erro no head_object de {object_name}: {e}")
            return "erro", None
        except Exception as e:
            logger.error(f"Erro inesperado no head_object de {object_name}: {e}")
            return "erro", None

        return "ok", {
            "tamanho": resposta.get('ContentLength'),
            "tipo": resposta.get('ContentType') or "",
            "etag": (resposta.get('ETag') or "").strip('"'),
        }

    def get_object_prefix(self, object_name: str, num_bytes: int) -> Optional[bytes]:
        """Primeiros `num_bytes` do objecto, por `Range` — chave EXACTA.

        Devolve `None` em qualquer falha (incluindo objecto inexistente):
        quem chama já sabe, pelo `head_object_metadata`, se o objecto lá
        está, pelo que um `None` aqui é sempre um problema de leitura.

        Um objecto MENOR do que `num_bytes` devolve o que tem — o S3
        satisfaz o `Range` parcialmente e não é erro. Um objecto VAZIO
        devolve `b""`, que o chamador tem de tratar como reprovação (um
        ficheiro sem bytes não tem assinatura nenhuma para validar).
        """
        if not self.is_configured() or num_bytes <= 0:
            return None

        try:
            resposta = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=object_name,
                Range=f"bytes=0-{num_bytes - 1}",
            )
            return resposta['Body'].read()
        except ClientError as e:
            codigo = str(e.response.get('Error', {}).get('Code', ''))
            # Um objecto vazio faz o S3 recusar o Range (416): não é falha
            # de leitura, é um ficheiro sem conteúdo.
            if codigo in ('416', 'InvalidRange', 'RequestedRangeNotSatisfiable'):
                return b""
            logger.error(f"Erro ao ler o prefixo de {object_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado ao ler o prefixo de {object_name}: {e}")
            return None

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
        client_name: str = None,
        second_client_name: str = None,
        *,
        base_path: str = None,
        owner_client_id: str = None,
    ) -> tuple:
        """
        Cria a estrutura de pastas padrão para um novo cliente no S3.

        Chamado automaticamente quando um novo processo é criado. A estrutura
        pré-definida (Pessoais, Financeiros, Imóvel, Bancários, RGPD, Outros)
        espelha os requisitos documentais do processo de crédito habitação,
        permitindo ao consultor organizar documentos desde o primeiro dia.

        O S3 não tem o conceito de "pastas" — cada categoria é representada
        por um ficheiro marcador ``.keep`` vazio. A função verifica primeiro
        se já existe pasta para o cliente (matching case-insensitive) para
        evitar duplicados quando o mesmo cliente tem múltiplos processos.

        Args:
            client_id: ID do processo/cliente.
            client_name: Nome do primeiro titular.
            second_client_name: Nome do segundo titular (opcional).

        Returns:
            tuple: ``(success, folder_path)`` onde:
                - success (bool): True se as pastas foram criadas/verificadas.
                - folder_path (str | None): Caminho base S3
                    (ex: "Documentação Clientes/Joao_Silva").
        """
        if not self.is_configured():
            return (False, None)

        # LOTE 6: a procura por nome saiu daqui. Era ela que fazia um cliente
        # novo herdar a pasta de um cliente de nome parecido — e aqui o efeito
        # era permanente, porque o caminho devolvido é o que se grava em
        # `s3_folder`. Quem quiser reaproveitar uma pasta existente passa-a em
        # `base_path` (é o que o religamento manual faz); por omissão, a pasta
        # deriva do id.
        if base_path is None:
            base_path = self._get_client_base_path_for_upload(
                client_id, client_name, second_client_name,
                owner_client_id=owner_client_id,
            )
        if not base_path:
            logger.error(
                "[S3-INIT] Sem caminho utilizável para %s (%s) — pastas não criadas.",
                client_id, client_name,
            )
            return (False, None)
        logger.info(f"Estrutura de pastas em {base_path} para {client_id}")

        try:
            for category in DEFAULT_CATEGORIES:
                safe_category = sanitize_folder_name(category)
                path = f"{base_path}/{safe_category}/.keep"
                # Verificar se já existe antes de criar
                try:
                    self.s3_client.head_object(
                        Bucket=self.bucket_name,
                        Key=path
                    )
                    # Já existe, não precisa criar
                except Exception:
                    # Não existe, criar
                    self.s3_client.put_object(
                        Bucket=self.bucket_name, 
                        Key=path,
                        Body=b''
                    )
            logger.info(f"Estrutura de pastas criada/verificada para cliente: {client_id} -> {base_path}")
            return (True, base_path)
        except ClientError as e:
            logger.error(f"Erro ao criar pastas S3: {e}")
            return (False, None)


    def ensure_client_folder_mapping(
        self,
        client_id: str,
        client_name: str = None,
        second_client_name: str = None,
        existing_s3_folder: str = None,
        *,
        owner_client_id: str = None,
    ) -> Dict:
        """
        Garante, de forma robusta e idempotente, que existe um mapeamento
        de pasta S3 válido para um cliente/processo.

        Usado tanto pelos fluxos normais de criação (onboarding, criação de
        processo) como pelo script de recuperação
        ``backend/scripts/hotfix_restore_s3_mappings.py`` para reparar
        mapeamentos em falta em clientes já existentes.

        Ordem de resolução (LOTE 6 — a procura por nome saiu do meio):
        1. Se ``existing_s3_folder`` for fornecido e a pasta ainda existir
           no S3, é reutilizado sem qualquer alteração (não recria nada).
           É isto que mantém intactos os 12.450 mapeamentos já gravados.
        2. Caso contrário, a pasta deriva do **ID** e a estrutura é criada
           (``Documentação Clientes/{client_id}[/processos/{process_id}]``).

        O passo do meio — "procurar uma pasta parecida por nome" — era a
        colisão de identidade: 0.867 de score punha "Carolina Agostinho da
        Silva" na pasta da "Carolina Silva". Reaproveitar uma pasta por nome
        passou a ser uma decisão HUMANA (religamento manual), nunca um
        palpite automático gravado para sempre.

        Esta função NUNCA escreve na base de dados — apenas devolve o
        caminho resolvido/criado no S3. A persistência (via ``$set``
        estrito na chave `s3_folder`) é responsabilidade de quem chama.

        Args:
            client_id: ID do processo/cliente (usado como referência interna).
            client_name: Nome do primeiro titular.
            second_client_name: Nome do segundo titular (opcional).
            existing_s3_folder: Mapeamento atual guardado na BD, se existir.

        Returns:
            dict com:
            - success (bool): True se há um caminho S3 válido para usar.
            - s3_folder (str | None): Caminho da pasta base no S3.
            - created (bool): True se uma pasta NOVA foi criada agora.
            - reused_existing (bool): True se o mapeamento existente foi
              validado e reutilizado sem alterações.
        """
        result = {
            "success": False,
            "s3_folder": None,
            "created": False,
            "reused_existing": False,
        }

        if not self.is_configured():
            logger.error("S3 não configurado — não é possível garantir mapeamento.")
            return result

        # 1. Reutilizar mapeamento existente se ainda for válido
        clean_existing = pasta_gravada(
            existing_s3_folder, contexto=f"mapeamento de {client_id}"
        )
        if clean_existing and clean_existing.lower() not in ("undefined", "null", "none"):
            try:
                if self._folder_exists(clean_existing):
                    result.update(success=True, s3_folder=clean_existing, reused_existing=True)
                    return result
            except Exception as e:
                logger.warning(f"Erro ao validar mapeamento S3 existente para {client_id}: {e}")

        # 2. A pasta deriva do ID. (Era aqui que vivia a procura por nome com
        #    score >= 0.7 — o ponto exacto onde a cliente nova herdava a pasta
        #    da cliente antiga. Reaproveitar uma pasta por nome deixou de ser
        #    automático: é uma decisão humana, no religamento manual.)
        try:
            success, folder_path = self.initialize_client_folders(
                client_id, client_name, second_client_name,
                owner_client_id=owner_client_id,
            )
            if success and folder_path:
                logger.info(f"[ENSURE-S3-MAPPING] Pasta criada para {client_name}: {folder_path}")
                result.update(success=True, s3_folder=folder_path, created=True)
            else:
                logger.error(f"[ENSURE-S3-MAPPING] Falha ao criar pasta S3 para cliente {client_id}")
        except Exception as e:
            logger.error(f"[ENSURE-S3-MAPPING] Erro inesperado ao criar pasta S3 para {client_id}: {e}", exc_info=True)

        return result

    def get_file_content(self, object_name: str, max_size_mb: int = 20) -> Optional[bytes]:
        """
        Obtém o conteúdo de um ficheiro do S3.
        Tenta variações do path (underscore <-> espaço) se o original falhar.
        
        Args:
            object_name: Caminho S3 do ficheiro
            max_size_mb: Tamanho máximo em MB (default 20MB). Ficheiros maiores
                         são rejeitados para evitar OOM em instâncias com pouca RAM.
            
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
                # Verificar tamanho ANTES de carregar para evitar OOM
                try:
                    head = self.s3_client.head_object(Bucket=self.bucket_name, Key=path)
                    size_mb = head.get('ContentLength', 0) / (1024 * 1024)
                    if size_mb > max_size_mb:
                        logger.warning(
                            f"Ficheiro S3 demasiado grande ({size_mb:.1f}MB > {max_size_mb}MB): {path}"
                        )
                        return None
                except ClientError:
                    pass  # Se head_object falhar, tentar get_object na mesma
                
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
            target_path = f"{client_folder}/{target_folder}/{file_name}"
            
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

    # ====================================================================
    # DIRECT S3 UPLOAD - PRE-SIGNED URLs
    # ====================================================================
    
    def generate_upload_presigned_url(
        self,
        client_id: str,
        client_name: str,
        category: str,
        filename: str,
        content_type: str = "application/octet-stream",
        second_client_name: str = None,
        s3_folder: str = None,
        expiration: int = 300
    ) -> Optional[Dict]:
        """
        Gera uma pre-signed URL para upload direto do frontend para o S3.
        
        Isto permite que o frontend faça upload diretamente para o S3,
        evitando que o ficheiro passe pelo backend (reduz RAM e timeouts).
        
        Args:
            client_id: ID do processo/cliente
            client_name: Nome do cliente
            category: Categoria (ex: "Financeiros", "Documentos Pessoais")
            filename: Nome do ficheiro
            content_type: MIME type do ficheiro
            second_client_name: Nome do segundo titular (opcional)
            s3_folder: Pasta S3 configurada manualmente (prioridade máxima)
            expiration: Tempo de validade em segundos (default: 5 minutos)
            
        Returns:
            Dict com:
            - upload_url: URL assinada para PUT request
            - file_key: Caminho S3 onde o ficheiro será armazenado
            - expires_at: Timestamp de expiração
            Ou None se falhar
        """
        if not self.is_configured():
            logger.error("S3 não configurado")
            return None
        
        # Usar s3_folder configurado se existir, senão usar path automático.
        # `pasta_gravada` porque uma lista é truthy: o `if` passava e o
        # `.rstrip` rebentava na linha seguinte (Lote 8). Um valor
        # ilegível vira `None` e o caminho deriva do ID, nunca do nome.
        pasta_do_mapeamento = pasta_gravada(
            s3_folder, contexto=f"upload de {client_id}"
        )
        if pasta_do_mapeamento:
            base_path = pasta_do_mapeamento.rstrip('/')
        else:
            base_path = self._get_client_base_path_for_upload(client_id, client_name, second_client_name)
        if not base_path:
            # Id inutilizável: recusa-se em vez de escrever num caminho
            # adivinhado a partir do nome (Lote 6, ponto 1).
            return None
        
        # Categoria "all" deve ser tratada como "Outros"
        if category.lower() == "all":
            category = "Outros"
        
        # Map portal categories (e.g. "Cartao_Cidadao") to S3 admin categories (e.g. "Documentos Pessoais")
        mapped_category = PORTAL_TO_S3_CATEGORY.get(category, category)
        
        safe_category = sanitize_folder_name(mapped_category)
        file_key = f"{base_path}/{safe_category}/{filename}"
        
        try:
            # Gerar pre-signed URL para PUT object
            upload_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_key,
                    'ContentType': content_type
                },
                ExpiresIn=expiration,
                HttpMethod='PUT'
            )
            
            from datetime import datetime, timezone, timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiration)
            
            logger.info(f"Pre-signed URL gerada para upload: {file_key}")
            
            return {
                "upload_url": upload_url,
                "file_key": file_key,
                "expires_at": expires_at.isoformat(),
                "expires_in_seconds": expiration,
                "bucket": self.bucket_name
            }
            
        except ClientError as e:
            logger.error(f"Erro ao gerar pre-signed URL para upload: {e}")
            return None
    
    def generate_upload_presigned_post(
        self,
        client_id: str,
        client_name: str,
        category: str,
        filename: str,
        content_type: str = "application/octet-stream",
        second_client_name: str = None,
        s3_folder: str = None,
        expiration: int = 300,
        max_size: int = 100 * 1024 * 1024  # 100MB default
    ) -> Optional[Dict]:
        """
        Gera uma pre-signed POST para upload direto via FormData.
        
        Alternativa ao generate_upload_presigned_url que usa POST em vez de PUT.
        Útil para uploads via FormData em browsers mais antigos.
        
        Args:
            client_id: ID do processo/cliente
            client_name: Nome do cliente
            category: Categoria (ex: "Financeiros", "Documentos Pessoais")
            filename: Nome do ficheiro
            content_type: MIME type do ficheiro
            second_client_name: Nome do segundo titular (opcional)
            s3_folder: Pasta S3 configurada manualmente (prioridade máxima)
            expiration: Tempo de validade em segundos (default: 5 minutos)
            max_size: Tamanho máximo do ficheiro em bytes (default: 100MB)
            
        Returns:
            Dict com:
            - url: URL do endpoint POST
            - fields: Campos a incluir no FormData
            - file_key: Caminho S3 onde o ficheiro será armazenado
            Ou None se falhar
        """
        if not self.is_configured():
            logger.error("S3 não configurado")
            return None
        
        # Usar s3_folder configurado se existir, senão usar path automático.
        # `pasta_gravada` porque uma lista é truthy: o `if` passava e o
        # `.rstrip` rebentava na linha seguinte (Lote 8). Um valor
        # ilegível vira `None` e o caminho deriva do ID, nunca do nome.
        pasta_do_mapeamento = pasta_gravada(
            s3_folder, contexto=f"upload de {client_id}"
        )
        if pasta_do_mapeamento:
            base_path = pasta_do_mapeamento.rstrip('/')
        else:
            base_path = self._get_client_base_path_for_upload(client_id, client_name, second_client_name)
        if not base_path:
            # Id inutilizável: recusa-se em vez de escrever num caminho
            # adivinhado a partir do nome (Lote 6, ponto 1).
            return None
        
        # Categoria "all" deve ser tratada como "Outros"
        if category.lower() == "all":
            category = "Outros"
        
        safe_category = sanitize_folder_name(category)
        file_key = f"{base_path}/{safe_category}/{filename}"
        
        try:
            # Gerar pre-signed POST
            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=file_key,
                Fields={
                    'Content-Type': content_type
                },
                Conditions=[
                    {'Content-Type': content_type},
                    ['content-length-range', 0, max_size]
                ],
                ExpiresIn=expiration
            )
            
            from datetime import datetime, timezone, timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiration)
            
            logger.info(f"Pre-signed POST gerada para upload: {file_key}")
            
            return {
                "url": response['url'],
                "fields": response['fields'],
                "file_key": file_key,
                "expires_at": expires_at.isoformat(),
                "expires_in_seconds": expiration
            }
            
        except ClientError as e:
            logger.error(f"Erro ao gerar pre-signed POST para upload: {e}")
            return None


# Instância global
s3_service = S3Service()


async def sync_s3_from_db_config():
    """
    Sync S3Service with database config on startup.
    Called after database is available.
    If DB has S3 credentials and S3Service is not yet configured,
    this reconfigures it.
    """
    try:
        from database import db
        config_doc = await db.system_config.find_one({"_id": "main"})
        if not config_doc:
            return

        storage = config_doc.get("storage", {})
        provider = storage.get("provider", "none")

        if provider == "aws_s3":
            access_key = storage.get("aws_access_key_id")
            secret_key = storage.get("aws_secret_access_key")
            bucket_name = storage.get("aws_bucket_name")
            region = storage.get("aws_region", "eu-west-3")

            if access_key and secret_key and bucket_name:
                if not s3_service.is_configured():
                    s3_service.reconfigure(access_key, secret_key, bucket_name, region)
                    logger.info(f"S3Service inicializado a partir da config da BD — Bucket: {bucket_name}")
                # Even if already configured from env, DB config takes precedence if bucket differs
                elif s3_service.bucket_name != bucket_name:
                    s3_service.reconfigure(access_key, secret_key, bucket_name, region)
                    logger.info(f"S3Service atualizado com config da BD — Bucket: {bucket_name}")
    except Exception as e:
        logger.debug(f"Sync S3 from DB config falhou (normal se BD não disponível): {e}")