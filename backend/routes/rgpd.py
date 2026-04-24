"""
Rotas RGPD - Regulamento Geral sobre a Proteção de Dados

Endpoints para gestão de consentimentos RGPD:
- Solicitar RGPD (envio de email com link temporário)
- Validar token e mostrar página de RGPD
- Assinar RGPD
- Verificar estado do RGPD para um processo
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from database import db
from models.rgpd import (
    RGPDCreate, RGPDResponse, RGPDStatusResponse,
    RGPDConsentData, RGPDPublicView, RGPDStatusEnum
)
from services.auth import get_current_user, require_staff, require_roles, require_management
from models.auth import UserRole
from services.rgpd_service import (
    create_rgpd_request,
    validate_token,
    get_rgpd_by_process,
    sign_rgpd,
    send_rgpd_email,
    get_tipo_documento_label,
    RGPD_REQUESTS_COLLECTION,
    TOKEN_EXPIRY_HOURS
)

async def _add_process_activity(process_id: str, user_id: str, user_name: str, action: str, details: str = ""):
    """Insere uma atividade/comentário automático na timeline do processo."""
    try:
        activity = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user_name,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "system"
        }
        await db.processes.update_one(
            {"id": process_id},
            {"$push": {"activities": activity}}
        )
    except Exception as e:
        logger.warning(f"Não foi possível registar atividade RGPD no processo {process_id}: {e}")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rgpd", tags=["RGPD"])


async def _get_rgpd_or_404(request_id: str):
    """
    Função auxiliar para obter um RGPD ou lançar erro 404.
    
    Args:
        request_id: ID do pedido RGPD
        
    Returns:
        Documento do RGPD
        
    Raises:
        HTTPException: Se o RGPD não for encontrado
    """
    rgpd = await db[RGPD_REQUESTS_COLLECTION].find_one({"id": request_id})
    if not rgpd:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")
    return rgpd


@router.post("/request", response_model=RGPDResponse)
async def request_rgpd(
    data: RGPDCreate,
    user: dict = Depends(require_staff())
):
    """
    Solicita consentimento RGPD para um processo, enviando um email
    com link temporário (24h) para o cliente assinar digitalmente.

    Porquê email com link temporário: o RGPD deve ser assinado pelo titular
    dos dados, não pelo consultor. O link temporário garante que apenas o
    destinatário do email pode aceder ao formulário, e a expiração de 24h
    limita a janela de vulnerabilidade se o email for intercetado.

    Se já existir um pedido RGPD para o processo, retorna o estado atual
    em vez de criar duplicado (idempotência).

    Args:
        data: Dados do pedido contendo process_id, client_name, client_email.
        user: Utilizador staff autenticado (injetado pelo Depends).

    Returns:
        RGPDResponse: Dados do pedido criado ou existente, incluindo
            status, token_expires_at e created_by_name.

    Raises:
        HTTPException: 404 se processo não encontrado, 500 se erro ao criar.
    """
    try:
        # Verificar se o processo existe
        process = await db.processes.find_one({"id": data.process_id})
        if not process:
            raise HTTPException(status_code=404, detail="Processo não encontrado")
        
        # Criar pedido de RGPD
        result = await create_rgpd_request(
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            user=user
        )
        
        if not result.get("success"):
            logger.error(f"Erro ao criar pedido RGPD: {result}")
            raise HTTPException(status_code=500, detail="Erro ao criar pedido de RGPD")
        
        # Se já existe e está assinado, retornar informação
        if result.get("existing"):
            if result.get("status") == "signed":
                return RGPDResponse(
                    id=result["request_id"],
                    process_id=data.process_id,
                    client_name=data.client_name,
                    client_email=data.client_email,
                    status=RGPDStatusEnum.SIGNED,
                    signed_at=result.get("signed_at"),
                    created_at="",
                    created_by_name=user.get("name", "")
                )
            elif result.get("status") == "pending":
                return RGPDResponse(
                    id=result["request_id"],
                    process_id=data.process_id,
                    client_name=data.client_name,
                    client_email=data.client_email,
                    status=RGPDStatusEnum.PENDING,
                    token_expires_at=result.get("expires_at"),
                    created_at="",
                    created_by_name=user.get("name", "")
                )
        
        # Enviar email com o link
        email_sent = await send_rgpd_email(
            client_email=data.client_email,
            client_name=data.client_name,
            token=result["token"],
            request_id=result["request_id"],
            user_email=user["email"]
        )
        
        if not email_sent:
            logger.warning("RGPD created but email failed to send")
        
        # M8 - Registar atividade no processo
        email_status = "enviado" if email_sent else "falhou"
        await _add_process_activity(
            process_id=data.process_id,
            user_id=user.get("id", "system"),
            user_name=user.get("name", "Sistema"),
            action=f"RGPD solicitado — email {email_status} para {data.client_email}",
            details=f"Link de assinatura enviado para o cliente. Expira em {TOKEN_EXPIRY_HOURS}h."
        )
        
        return RGPDResponse(
            id=result["request_id"],
            process_id=data.process_id,
            client_name=data.client_name,
            client_email=data.client_email,
            status=RGPDStatusEnum.PENDING,
            token_expires_at=result["expires_at"],
            created_at="",
            created_by_name=user.get("name", "")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado em request_rgpd: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/validate/{token}", response_model=RGPDPublicView)
async def validate_rgpd_token(token: str):
    """
    Validar token de RGPD e retornar dados para a página pública.
    
    Este endpoint é público (sem autenticação) para permitir que
    o cliente aceda à página de RGPD através do link no email.
    """
    request = await validate_token(token)
    
    if not request:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    
    from datetime import datetime, timezone
    
    return RGPDPublicView(
        id=request["id"],
        client_name=request["client_name"],
        status=RGPDStatusEnum.PENDING,
        created_at=request["created_at"],
        expires_at=request["token_expires_at"],
        valid=True
    )


@router.post("/sign/{token}")
async def sign_rgpd_form(
    token: str,
    consent_data: RGPDConsentData
):
    """
    Assina digitalmente o consentimento RGPD usando um token temporário.

    Porquê registar a versão do template: em caso de litígio, é crucial
    provar qual versão do texto RGPD o cliente assinou. Após a assinatura,
    este endpoint guarda o ID e número da versão ativa do template no
    pedido RGPD para prova legal (audit trail).

    Este endpoint é público (sem autenticação) por design — o token
    temporário é a única proteção necessária.

    Args:
        token: Token temporário enviado por email (UUID composto).
        consent_data: Dados de consentimento do cliente (nome, contribuinte,
            morada, assinatura digital, etc.).

    Returns:
        dict: Resultado com success, message e process_id.

    Raises:
        HTTPException: 400 se token inválido, expirado ou erro na assinatura.
    """
    result = await sign_rgpd(token, consent_data.model_dump())
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao assinar RGPD"))
    
    # Obter a versão ativa do template RGPD e guardar no pedido
    # para prova legal de qual versão o cliente assinou
    request_id = result.get("request_id")
    process_id = result.get("process_id")
    if request_id:
        try:
            # Buscar a versão ativa do template RGPD
            active_version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
                {"is_active": True},
                {"_id": 0}
            )
            if active_version:
                # Guardar versão do template no pedido RGPD para prova legal
                await db[RGPD_REQUESTS_COLLECTION].update_one(
                    {"id": request_id},
                    {"$set": {
                        "rgpd_template_version_id": active_version["id"],
                        "rgpd_template_version": active_version["version"]
                    }}
                )
                logger.info(f"Versão do template RGPD v{active_version['version']} registada no pedido {request_id}")
            else:
                # Fallback: verificar system_config
                config_doc = await db.system_config.find_one(
                    {"_id": "rgpd_template"},
                    {"_id": 0, "active_version_id": 1, "active_version": 1}
                )
                if config_doc and config_doc.get("active_version_id"):
                    await db[RGPD_REQUESTS_COLLECTION].update_one(
                        {"id": request_id},
                        {"$set": {
                            "rgpd_template_version_id": config_doc["active_version_id"],
                            "rgpd_template_version": config_doc.get("active_version", 1)
                        }}
                    )
        except Exception as e:
            logger.warning(f"Não foi possível registar versão do template RGPD: {e}")
    
    # M8 - Registar atividade de assinatura no processo
    if process_id:
        await _add_process_activity(
            process_id=process_id,
            user_id="client",
            user_name=consent_data.nome or "Cliente",
            action="RGPD assinado pelo cliente",
            details=f"Documento RGPD assinado digitalmente. NIF: {consent_data.contribuinte or 'N/A'}."
        )
    
    return {
        "success": True,
        "message": "RGPD assinado com sucesso",
        "process_id": result["process_id"]
    }


@router.get("/status/{process_id}", response_model=RGPDStatusResponse)
async def get_rgpd_status(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Verificar estado do RGPD para um processo.
    
    Permissões: Qualquer utilizador autenticado pode verificar.
    """
    try:
        # Validar se process_id é um UUID válido
        import uuid
        try:
            uuid.UUID(process_id)
        except (ValueError, TypeError):
            logger.warning(f"process_id inválido fornecido: {process_id}")
            return RGPDStatusResponse(has_rgpd=False)
        
        result = await get_rgpd_by_process(process_id)
        
        if not result:
            return RGPDStatusResponse(has_rgpd=False)
        
        return RGPDStatusResponse(
            has_rgpd=result.get("has_rgpd", False),
            status=result.get("status"),
            signed_at=result.get("signed_at"),
            pdf_url=result.get("pdf_url"),
            request_id=result.get("request_id")
        )
    except Exception as e:
        logger.error(f"Erro ao verificar estado RGPD para processo {process_id}: {e}", exc_info=True)
        # Retornar resposta vazia em vez de erro
        return RGPDStatusResponse(has_rgpd=False)


@router.get("/data/{token}")
async def get_rgpd_form_data(token: str):
    """
    Obtém dados para pré-preencher o formulário de RGPD e o texto
    do template renderizado com variáveis dinâmicas do processo.

    Porquê pré-preenchimento: melhora a experiência do cliente ao
    evitar que tenha de introduzir manualmente dados que a empresa
    já possui (NIF, morada, tipo de documento). Apenas pede confirmação.

    Renderiza variáveis como {{NOME_CLIENTE}}, {{CONTRIBUINTE}}, etc.
    no template RGPD ativo para que o cliente veja o texto final antes de
    assinar.

    Args:
        token: Token temporário do pedido RGPD.

    Returns:
        dict: Dados do cliente para pré-preenchimento (client_name,
            nif, morada, numero_documento, etc.) e rgpd_text renderizado.

    Raises:
        HTTPException: 400 se token inválido ou expirado.
    """
    request = await validate_token(token)
    
    if not request:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    
    # Buscar dados do processo
    process = await db.processes.find_one({"id": request["process_id"]})
    
    # Desencriptar dados sensíveis antes de extrair
    if process:
        from services.process_service import decrypt_sensitive_data
        process = decrypt_sensitive_data(process)
    
    personal_data = process.get("personal_data", {}) if process else {}
    real_estate_data = process.get("real_estate_data", {}) if process else {}
    
    # Extrair dados do documento de identificação
    documento_id = personal_data.get("documento_id", "")
    if isinstance(documento_id, dict):
        tipo_documento = documento_id.get("type", "")
        numero_documento = documento_id.get("number", "")
    else:
        tipo_documento = ""
        numero_documento = str(documento_id) if documento_id else ""
    
    response_data = {
        "client_name": request["client_name"],
        "client_email": request["client_email"],
        "nif": personal_data.get("nif", ""),
        "morada": personal_data.get("morada_fiscal", ""),
        "localidade": real_estate_data.get("concelho", personal_data.get("naturalidade", "")),
        "numero_documento": numero_documento,
        "tipo_documento": tipo_documento,
        "validade_documento": personal_data.get("data_validade_cc", ""),
        "concelho": real_estate_data.get("concelho", ""),
        "codigo_postal": real_estate_data.get("codigo_postal", ""),
    }
    
    # Renderizar templates com variáveis dinâmicas
    try:
        template_text = await _get_active_rgpd_template()
        minuta_text = await _get_active_minuta_template()
        
        # Tentar obter nome da empresa da configuração do sistema
        empresa_nome = "Power Real Estate, Lda."
        try:
            config = await db.system_config.find_one(
                {"_id": "main"},
                {"_id": 0, "settings.empresa_nome": 1}
            )
            if config:
                settings = config.get("settings", {})
                if settings.get("empresa_nome"):
                    empresa_nome = settings["empresa_nome"]
        except Exception:
            pass  # Usar nome padrão
        
        # Data atual formatada como DD/MM/YYYY
        data_assinatura = datetime.now(timezone.utc).strftime("%d/%m/%Y")
        
        # Substituir variáveis dinâmicas no template RGPD
        if template_text:
            rendered = template_text
            rendered = rendered.replace("{{NOME_CLIENTE}}", request["client_name"])
            rendered = rendered.replace("{{NOME}}", request["client_name"])
            rendered = rendered.replace("{{NOME_EMPRESA}}", empresa_nome)
            rendered = rendered.replace("{{CONTRIBUINTE}}", response_data["nif"])
            rendered = rendered.replace("{{MORADA}}", response_data["morada"])
            rendered = rendered.replace("{{LOCALIDADE}}", response_data["localidade"])
            rendered = rendered.replace("{{CODIGO_POSTAL}}", response_data["codigo_postal"])
            tipo_documento_label = get_tipo_documento_label(tipo_documento)
            rendered = rendered.replace("{{TIPO_DOCUMENTO}}", tipo_documento_label)
            rendered = rendered.replace("{{NUMERO_DOCUMENTO}}", numero_documento)
            rendered = rendered.replace("{{VALIDADE_DOCUMENTO}}", response_data["validade_documento"])
            rendered = rendered.replace("{{DATA_ASSINATURA}}", data_assinatura)
            response_data["rgpd_text"] = rendered
        else:
            response_data["rgpd_text"] = None
        
        # Substituir variáveis dinâmicas no template Minuta
        if minuta_text:
            rendered_minuta = minuta_text
            rendered_minuta = rendered_minuta.replace("{{NOME_CLIENTE}}", request["client_name"])
            rendered_minuta = rendered_minuta.replace("{{NOME}}", request["client_name"])
            rendered_minuta = rendered_minuta.replace("{{NOME_EMPRESA}}", empresa_nome)
            rendered_minuta = rendered_minuta.replace("{{CONTRIBUINTE}}", response_data["nif"])
            rendered_minuta = rendered_minuta.replace("{{MORADA}}", response_data["morada"])
            rendered_minuta = rendered_minuta.replace("{{LOCALIDADE}}", response_data["localidade"])
            rendered_minuta = rendered_minuta.replace("{{CODIGO_POSTAL}}", response_data["codigo_postal"])
            rendered_minuta = rendered_minuta.replace("{{TIPO_DOCUMENTO}}", get_tipo_documento_label(tipo_documento))
            rendered_minuta = rendered_minuta.replace("{{NUMERO_DOCUMENTO}}", numero_documento)
            rendered_minuta = rendered_minuta.replace("{{VALIDADE_DOCUMENTO}}", response_data["validade_documento"])
            rendered_minuta = rendered_minuta.replace("{{DATA_ASSINATURA}}", data_assinatura)
            response_data["minuta_text"] = rendered_minuta
        else:
            response_data["minuta_text"] = None
            
    except Exception as e:
        logger.warning(f"Não foi possível renderizar templates: {e}")
        response_data["rgpd_text"] = None
        response_data["minuta_text"] = None
    
    return response_data


async def _get_active_rgpd_template() -> Optional[str]:
    """
    Função auxiliar para obter o texto do template RGPD ativo.
    
    Prioridade:
    1. Versão ativa na coleção rgpd_template_versions
    2. Conteúdo em system_config (compatibilidade retroativa)
    3. Template padrão definido no código
    
    Returns:
        Texto do template ou None em caso de erro
    """
    try:
        # Tentar obter da coleção de versões
        active_version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"is_active": True},
            {"_id": 0, "content": 1}
        )
        if active_version and active_version.get("content"):
            return active_version["content"]
        
        # Fallback: system_config (compatibilidade retroativa)
        doc = await db.system_config.find_one(
            {"_id": "rgpd_template"},
            {"_id": 0, "content": 1}
        )
        if doc and doc.get("content"):
            return doc["content"]
        
        # Template padrão
        return RGPD_DEFAULT_TEMPLATE
    except Exception as e:
        logger.error(f"Erro ao obter template RGPD ativo: {e}")
        return RGPD_DEFAULT_TEMPLATE


@router.get("/list/{process_id}")
async def list_rgpd_requests(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Listar todos os pedidos de RGPD para um processo.

    Permissões: Qualquer utilizador autenticado.
    """
    requests = await db.rgpd_requests.find(
        {"process_id": process_id},
        {"_id": 0, "token": 0}  # Não expor o token
    ).sort("created_at", -1).to_list(20)

    return {
        "requests": requests,
        "total": len(requests)
    }


# ============ ENDPOINTS DE ADMINISTRAÇÃO ============

@router.get("/admin/all")
async def list_all_rgpd(
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(require_staff())
):
    """
    Listar todos os RGPDs (administração).

    Permissões: Apenas staff.
    Query params:
    - status: Filtrar por estado (pending, signed, expired, cancelled)
    - search: Pesquisar por nome ou NIF
    - page: Página (default: 1)
    - limit: Itens por página (default: 20)
    """
    try:
        query = {}

        if status:
            query["status"] = status

        if search:
            query["$or"] = [
                {"client_name": {"$regex": search, "$options": "i"}},
                {"consent_data.contribuinte": {"$regex": search, "$options": "i"}},
                {"consent_data.nome": {"$regex": search, "$options": "i"}}
            ]

        skip = (page - 1) * limit

        total = await db[RGPD_REQUESTS_COLLECTION].count_documents(query)

        requests = await db[RGPD_REQUESTS_COLLECTION].find(
            query,
            {"_id": 0, "token": 0}
        ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

        return {
            "requests": requests,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit
        }
    except Exception as e:
        logger.error(f"Erro ao obter RGPD admin all: {e}")
        return {
            "requests": [],
            "total": 0,
            "page": page,
            "limit": limit,
            "pages": 0
        }


# ============ ENDPOINTS DE TEMPLATE RGPD ============

class RGPDTemplateUpdate(BaseModel):
    """Modelo para actualização do template RGPD."""
    content: str
    changelog: Optional[str] = Field(None, description="Descrição opcional da alteração realizada")


# Coleção para guardar o histórico de versões do template Minuta
MINUTA_TEMPLATE_VERSIONS_COLLECTION = "minuta_template_versions"

# Template padrão Minuta
MINUTA_DEFAULT_TEMPLATE = """MINUTA DE EXCLUSIVIDADE

Eu, {{NOME}}, titular do {{TIPO_DOCUMENTO}} n.º {{NUMERO_DOCUMENTO}}, válido até {{VALIDADE_DOCUMENTO}} com o nº de contribuinte {{CONTRIBUINTE}}, residente na {{MORADA}}, {{LOCALIDADE}}, código postal: {{CODIGO_POSTAL}}, venho por este meio solicitar de forma exclusiva e de livre vontade os serviços gratuitos de intermediação de crédito da {{NOME_EMPRESA}}, vinculado sob o registo nº _________ no Banco de Portugal, abdicando dos serviços de outras entidades de intermediação de crédito."""

# Template padrão RGPD
RGPD_DEFAULT_TEMPLATE = """AUTORIZAÇÃO PARA TRATAMENTO DE DADOS PESSOAIS – RGPD

Nos termos do Regulamento (UE) 2016/679 do Parlamento Europeu e do Conselho (Regulamento Geral sobre a Proteção de Dados – "RGPD"), o titular dos dados abaixo identificado autoriza expressamente o tratamento dos seus dados pessoais pela entidade responsável pelo tratamento, nos seguintes termos:

1. RESPONSÁVEL PELO TRATAMENTO
Empresa: Power Real Estate, Lda.
NIF: 516 123 456
Morada: [Morada da Empresa]
Contacto: [Email/Tel da Empresa]

2. TITULAR DOS DADOS
Nome Completo: {{NOME}}
NIF/Contribuinte: {{CONTRIBUINTE}}
Morada: {{MORADA}}
Código Postal: {{CODIGO_POSTAL}}

3. TIPO DE DOCUMENTO DE IDENTIFICAÇÃO
Tipo: {{TIPO_DOCUMENTO}}
Número: {{NUMERO_DOCUMENTO}}
Validade: {{VALIDADE_DOCUMENTO}}

4. FINALIDADE DO TRATAMENTO
Os dados pessoais recolhidos são tratados para as seguintes finalidades:
a) Gestão do processo de mediação imobiliária;
b) Cumprimento de obrigações legais e regulatórias;
c) Comunicação relacionada com o processo em curso;
d) Elaboração de documentação contratual e fiscal.

5. CATEGORIAS DE DADOS PESSOAIS TRATADOS
- Dados de identificação (nome, NIF, documento de identificação);
- Dados de contacto (morada, código postal, telefone, email);
- Dados financeiros (relacionados com o processo imobiliário);
- Dados profissionais (profissão, entidade empregadora).

6. BASE LEGAL PARA O TRATAMENTO
O tratamento dos dados pessoais é realizado com base no consentimento do titular (Art. 6.º, n.º 1, alínea a) do RGPD) e na execução de contrato (Art. 6.º, n.º 1, alínea b) do RGPD).

7. CONSERVAÇÃO DOS DADOS
Os dados pessoais serão conservados durante o período necessário para a execução do processo e durante o prazo legalmente exigido para efeitos de responsabilização, não excedendo o prazo máximo de 10 (dez) anos após a conclusão do processo.

8. DIREITOS DO TITULAR
O titular dos dados tem o direito de:
- Aceder aos seus dados pessoais;
- Retificar dados incorretos ou incompletos;
- Solicitar a eliminação dos dados ("direito ao esquecimento");
- Limitar o tratamento dos dados;
- Solicitar a portabilidade dos dados;
- Opor-se ao tratamento dos dados;
- Retirar o consentimento a qualquer momento, sem comprometer a licitude do tratamento efetuado até essa data.

Para exercer os seus direitos, o titular pode contactar o responsável pelo tratamento através do endereço de email: [Email DPO] ou por escrito para a morada indicada no ponto 1.

9. PARTILHA DE DADOS
Os dados pessoais poderão ser partilhados com:
- Entidades bancárias, no âmbito da solicitação de financiamento;
- Notários e Conservatórias, para efeitos de escritura pública;
- Autoridades fiscais e tributárias;
- Outras entidades legalmente autorizadas.

10. COOKIES E TECNOLOGIAS DE RASTREAMENTO
Informamos que poderão ser utilizadas tecnologias de rastreamento no âmbito do processo, sempre com o conhecimento e consentimento do titular.

11. DECISÕES AUTOMATIZADAS
Informamos que não são tomadas decisões baseadas exclusivamente no tratamento automatizado, incluindo a definição de perfis, que produzam efeitos jurídicos ou de forma similar.

DECLARAÇÃO FINAL:
O titular dos dados declara ter sido informado de forma clara e completa sobre o tratamento dos seus dados pessoais, nos termos do disposto no Regulamento Geral sobre a Proteção de Dados (RGPD), e consente expressamente com o tratamento acima descrito.

Data: {{DATA_ASSINATURA}}
Assinatura: _________________________________"""


@router.get("/admin/template")
async def get_rgpd_template(
    user: dict = Depends(require_management())
):
    """
    Obter o template de texto RGPD.

    PROTEÇÃO: Apenas admin e CEO podem visualizar o template RGPD.
    Retorna o conteúdo atual do template RGPD guardado na base de dados.
    Se não existir um template personalizado, retorna o template padrão.
    Inclui informação da versão ativa quando disponível.
    """
    try:
        doc = await db.system_config.find_one({"_id": "rgpd_template"}, {"_id": 0})

        if doc and doc.get("content"):
            return {
                "content": doc["content"],
                "updated_at": doc.get("updated_at"),
                "updated_by": doc.get("updated_by"),
                "is_default": False,
                "active_version_id": doc.get("active_version_id"),
                "active_version": doc.get("active_version")
            }

        return {
            "content": RGPD_DEFAULT_TEMPLATE,
            "updated_at": None,
            "updated_by": None,
            "is_default": True,
            "active_version_id": None,
            "active_version": None
        }
    except Exception as e:
        logger.error(f"Erro ao obter template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter template RGPD")


# Coleção para guardar o histórico de versões do template RGPD
RGPD_TEMPLATE_VERSIONS_COLLECTION = "rgpd_template_versions"


@router.put("/admin/template")
async def update_rgpd_template(
    template_data: RGPDTemplateUpdate,
    user: dict = Depends(require_management())
):
    """
    Atualizar o template de texto RGPD (com versionamento).

    PROTEÇÃO: Apenas admin e CEO podem alterar o template RGPD.
    Cada atualização cria uma nova versão na coleção rgpd_template_versions,
    marcando todas as versões anteriores como inativas.
    O system_config continua a apontar para a versão ativa para consulta rápida.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        created_by = user.get("name", user.get("email", "unknown"))

        # Calcular próximo número de versão (auto-incrementado: 1.0, 2.0, 3.0...)
        last_version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
            sort=[("version", -1)]
        )
        next_version = (last_version["version"] + 1) if last_version else 1

        # Criar novo documento de versão
        new_version_id = str(uuid.uuid4())
        version_doc = {
            "id": new_version_id,
            "content": template_data.content,
            "version": next_version,
            "changelog": template_data.changelog,
            "created_at": now,
            "created_by": created_by,
            "is_active": True
        }
        await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].insert_one(version_doc)

        # Marcar todas as versões anteriores como inativas
        await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].update_many(
            {"id": {"$ne": new_version_id}},
            {"$set": {"is_active": False}}
        )

        # Actualizar system_config para apontar para a versão ativa
        await db.system_config.update_one(
            {"_id": "rgpd_template"},
            {
                "$set": {
                    "content": template_data.content,
                    "active_version_id": new_version_id,
                    "active_version": next_version,
                    "updated_at": now,
                    "updated_by": created_by
                },
                "$setOnInsert": {
                    "created_at": now
                }
            },
            upsert=True
        )

        logger.info(f"Template RGPD versão {next_version} criada por {created_by}")

        return {
            "success": True,
            "message": f"Template RGPD atualizado com sucesso (versão {next_version})",
            "version": next_version,
            "version_id": new_version_id,
            "updated_at": now
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar template RGPD")


@router.get("/admin/template/versions")
async def list_rgpd_template_versions(
    user: dict = Depends(require_management())
):
    """
    Listar todas as versões do template RGPD (sem conteúdo completo).

    PROTEÇÃO: Apenas admin e CEO podem ver o histórico de versões.
    Retorna metadados de cada versão para consulta rápida.
    """
    try:
        versions = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find(
            {},
            {"_id": 0, "content": 0}  # Excluir conteúdo completo da listagem
        ).sort("version", -1).to_list(100)

        return {
            "versions": versions,
            "total": len(versions)
        }
    except Exception as e:
        logger.error(f"Erro ao listar versões do template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao listar versões do template RGPD")


@router.get("/admin/template/versions/{version_id}")
async def get_rgpd_template_version(
    version_id: str,
    user: dict = Depends(require_management())
):
    """
    Obter o conteúdo completo de uma versão específica do template RGPD.

    PROTEÇÃO: Apenas admin e CEO podem ver versões do template.
    """
    try:
        version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"id": version_id},
            {"_id": 0}
        )

        if not version:
            raise HTTPException(status_code=404, detail="Versão do template RGPD não encontrada")

        return version
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter versão do template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter versão do template RGPD")


@router.get("/admin/{request_id}")
async def get_rgpd_by_id(
    request_id: str,
    user: dict = Depends(require_staff())
):
    """
    Obter detalhes de um RGPD específico.

    Permissões: Apenas staff.
    """
    request = await db[RGPD_REQUESTS_COLLECTION].find_one(
        {"id": request_id},
        {"_id": 0, "token": 0}
    )

    if not request:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")

    # Buscar dados do processo associado
    process = await db.processes.find_one(
        {"id": request["process_id"]},
        {"_id": 0, "id": 1, "client_name": 1, "status": 1}
    )

    return {
        "rgpd": request,
        "process": process
    }


@router.put("/admin/{request_id}")
async def update_rgpd_data(
    request_id: str,
    consent_data: RGPDConsentData,
    user: dict = Depends(require_staff())
):
    """
    Atualizar dados do RGPD.

    Permissões: Apenas staff.
    """
    # Verificar se o RGPD existe
    existing = await _get_rgpd_or_404(request_id)

    # Actualizar dados
    update_data = consent_data.model_dump()

    # Manter a data de assinatura original se existir
    if existing.get("consent_data", {}).get("data_assinatura"):
        update_data["data_assinatura"] = existing["consent_data"]["data_assinatura"]

    # Manter a assinatura original se existir e não for fornecida nova
    if existing.get("consent_data", {}).get("assinatura") and not update_data.get("assinatura"):
        update_data["assinatura"] = existing["consent_data"]["assinatura"]

    await db[RGPD_REQUESTS_COLLECTION].update_one(
        {"id": request_id},
        {"$set": {"consent_data": update_data}}
    )

    logger.info("RGPD request updated by user")

    return {
        "success": True,
        "message": "RGPD atualizado com sucesso",
        "request_id": request_id
    }


@router.delete("/admin/{request_id}")
async def delete_rgpd(
    request_id: str,
    user: dict = Depends(require_staff())
):
    """
    Eliminar um RGPD.

    Permissões: Apenas staff.
    """
    result = await db[RGPD_REQUESTS_COLLECTION].delete_one({"id": request_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="RGPD não encontrado")

    logger.info("RGPD request deleted by user")

    return {
        "success": True,
        "message": "RGPD eliminado com sucesso"
    }


@router.post("/admin/{request_id}/resend")
async def resend_rgpd_email(
    request_id: str,
    user: dict = Depends(require_staff())
):
    """
    Reenviar email de RGPD para o cliente.

    Permissões: Apenas staff.
    Gera um novo token e reenvia o email.
    """
    import uuid
    from datetime import datetime, timezone, timedelta

    # Buscar o RGPD
    rgpd = await _get_rgpd_or_404(request_id)

    if rgpd["status"] == "signed":
        raise HTTPException(status_code=400, detail="Este RGPD já foi assinado")

    # Gerar novo token
    new_token = f"{uuid.uuid4().hex}{uuid.uuid4().hex}"
    new_expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

    # Actualizar
    await db[RGPD_REQUESTS_COLLECTION].update_one(
        {"id": request_id},
        {
            "$set": {
                "token": new_token,
                "token_expires_at": new_expires.isoformat(),
                "status": "pending"
            }
        }
    )

    # Enviar email
    email_sent = await send_rgpd_email(
        client_email=rgpd["client_email"],
        client_name=rgpd["client_name"],
        token=new_token,
        request_id=request_id,
        user_email=user["email"]
    )

    if not email_sent:
        raise HTTPException(status_code=500, detail="Erro ao enviar email")

    logger.info("RGPD email resent by user")

    return {
        "success": True,
        "message": "Email reenviado com sucesso",
        "expires_at": new_expires.isoformat()
    }


@router.get("/admin/stats/summary")
async def get_rgpd_stats(
    user: dict = Depends(require_staff())
):
    """
    Obter estatísticas de RGPD.

    Permissões: Apenas staff.
    """
    try:
        from datetime import datetime, timezone, timedelta

        # Contar por estado
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]

        status_counts = await db[RGPD_REQUESTS_COLLECTION].aggregate(pipeline).to_list(10)

        stats = {
            "pending": 0,
            "signed": 0,
            "expired": 0,
            "cancelled": 0,
            "total": 0
        }

        for item in status_counts:
            if item["_id"]:
                stats[item["_id"]] = item["count"]
                stats["total"] += item["count"]

        # Contar assinados hoje
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        signed_today = await db[RGPD_REQUESTS_COLLECTION].count_documents({
            "status": "signed",
            "signed_at": {"$gte": today.isoformat()}
        })

        stats["signed_today"] = signed_today

        return stats
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas RGPD: {e}")
        return {
            "pending": 0,
            "signed": 0,
            "expired": 0,
            "cancelled": 0,
            "total": 0,
            "signed_today": 0
        }


# ============ ENDPOINTS DE TEMPLATE MINUTA ============

async def _get_active_minuta_template() -> Optional[str]:
    """
    Função auxiliar para obter o texto do template Minuta ativo.
    
    Prioridade:
    1. Versão ativa na coleção minuta_template_versions
    2. Conteúdo em system_config (compatibilidade retroativa)
    3. Template padrão definido no código
    """
    try:
        active_version = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"is_active": True},
            {"_id": 0, "content": 1}
        )
        if active_version and active_version.get("content"):
            return active_version["content"]
        
        doc = await db.system_config.find_one(
            {"_id": "minuta_template"},
            {"_id": 0, "content": 1}
        )
        if doc and doc.get("content"):
            return doc["content"]
        
        return MINUTA_DEFAULT_TEMPLATE
    except Exception as e:
        logger.error(f"Erro ao obter template Minuta ativo: {e}")
        return MINUTA_DEFAULT_TEMPLATE


class MinutaTemplateUpdate(BaseModel):
    """Modelo para actualização do template Minuta."""
    content: str
    changelog: Optional[str] = Field(None, description="Descrição opcional da alteração realizada")


@router.get("/admin/minuta-template")
async def get_minuta_template(
    user: dict = Depends(require_management())
):
    """
    Obter o template de texto da Minuta de Exclusividade.
    """
    try:
        doc = await db.system_config.find_one({"_id": "minuta_template"}, {"_id": 0})

        if doc and doc.get("content"):
            return {
                "content": doc["content"],
                "updated_at": doc.get("updated_at"),
                "updated_by": doc.get("updated_by"),
                "is_default": False,
                "active_version_id": doc.get("active_version_id"),
                "active_version": doc.get("active_version")
            }

        return {
            "content": MINUTA_DEFAULT_TEMPLATE,
            "updated_at": None,
            "updated_by": None,
            "is_default": True,
            "active_version_id": None,
            "active_version": None
        }
    except Exception as e:
        logger.error(f"Erro ao obter template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter template Minuta")


@router.put("/admin/minuta-template")
async def update_minuta_template(
    template_data: MinutaTemplateUpdate,
    user: dict = Depends(require_management())
):
    """
    Atualizar o template de texto da Minuta de Exclusividade (com versionamento).
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        created_by = user.get("name", user.get("email", "unknown"))

        last_version = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find_one(
            sort=[("version", -1)]
        )
        next_version = (last_version["version"] + 1) if last_version else 1

        new_version_id = str(uuid.uuid4())
        version_doc = {
            "id": new_version_id,
            "content": template_data.content,
            "version": next_version,
            "changelog": template_data.changelog,
            "created_at": now,
            "created_by": created_by,
            "is_active": True
        }
        await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].insert_one(version_doc)

        await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].update_many(
            {"id": {"$ne": new_version_id}},
            {"$set": {"is_active": False}}
        )

        await db.system_config.update_one(
            {"_id": "minuta_template"},
            {
                "$set": {
                    "content": template_data.content,
                    "active_version_id": new_version_id,
                    "active_version": next_version,
                    "updated_at": now,
                    "updated_by": created_by
                },
                "$setOnInsert": {
                    "created_at": now
                }
            },
            upsert=True
        )

        logger.info(f"Template Minuta versão {next_version} criada por {created_by}")

        return {
            "success": True,
            "message": f"Template Minuta atualizado com sucesso (versão {next_version})",
            "version": next_version,
            "version_id": new_version_id,
            "updated_at": now
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar template Minuta")


@router.get("/admin/minuta-template/versions")
async def list_minuta_template_versions(
    user: dict = Depends(require_management())
):
    """Listar todas as versões do template Minuta."""
    try:
        versions = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find(
            {},
            {"_id": 0, "content": 0}
        ).sort("version", -1).to_list(100)

        return {
            "versions": versions,
            "total": len(versions)
        }
    except Exception as e:
        logger.error(f"Erro ao listar versões do template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao listar versões")


@router.get("/admin/minuta-template/versions/{version_id}")
async def get_minuta_template_version(
    version_id: str,
    user: dict = Depends(require_management())
):
    """Obter o conteúdo completo de uma versão específica do template Minuta."""
    try:
        version = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"id": version_id},
            {"_id": 0}
        )

        if not version:
            raise HTTPException(status_code=404, detail="Versão do template Minuta não encontrada")

        return version
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter versão do template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter versão")
