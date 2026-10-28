"""
MÓDULO INDEX — `/api/index/*` (Lote 12, Fase 3)
================================================
Router fino; a lógica vive em `services/index_api.py` e `services/index_finalize.py`.

* Quem entra: Master, Admin, CEO, Diretor e Indexação (`PAPEIS_DE_IA_DO_INDEX`), pelo perfil
  EFECTIVO. Consultor e Intermediário recebem 403 e o handler nunca corre.
* Dependências do router, por ordem: a REDE (404 igual ao de «não existe») e depois o estado
  fechado do processo (403, só em escritas). A ordem importa: «está fechado» não pode ser um
  oráculo sobre um processo de outra rede.
* Cada rota limitada declara `request` e `response: Response` (o slowapi precisa dele no sucesso).
* Nenhum endpoint bloqueia a indexação: «mark-indexed» responde sempre (salvo permissão).
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from middleware.rate_limit import limiter
from services.auth import get_all_user_roles, get_effective_role, get_effective_role_async, require_roles
from services.index_access import PAPEIS_DE_IA_DO_INDEX
from services.index_advanced_search import TAMANHO_MAXIMO_DA_PAGINA, run_advanced_search
from services.index_document_content import run_conteudo_do_documento, run_conteudo_do_ficheiro_do_processo
from services.index_api import (
    run_assumir_processo,
    run_analyze_process,
    run_dismiss_alert,
    run_edit_professional_job,
    run_exigir_titularidade,
    run_get_index_queue,
    run_get_index_workstation,
    run_start_work,
    run_sanitize_process,
    run_search_employers,
    run_set_file_titular,
)
from services.index_conversa import MensagemDaConversa, run_enviar_do_index, run_ler_conversa_do_index
from services.index_finalize import run_mark_indexed
from services import index_assignment_requests as pedidos_de_atribuicao
from services.process_broadcast import broadcast_process_delta
from services.process_closed_guard import exigir_processo_editavel
from services.process_scope_guard import exigir_processo_no_ambito

router = APIRouter(
    prefix="/index",
    tags=["Index"],
    dependencies=[Depends(exigir_processo_no_ambito), Depends(exigir_processo_editavel)],
)

_acesso = require_roles(PAPEIS_DE_IA_DO_INDEX)
#: «Atribuir a mim» é do indexador (perfil efectivo). A gestão atribui pelo «Gerir» do processo.
PAPEIS_QUE_ASSUMEM = ["indexacao"]
_so_o_index = require_roles(PAPEIS_QUE_ASSUMEM)
#: Quem trata os pedidos de alteração de atribuição do Index: a chefia (o Index só os cria e vê os seus).
PAPEIS_QUE_TRATAM_PEDIDOS = list(pedidos_de_atribuicao.ROLES_DA_CHEFIA)
_so_a_chefia = require_roles(PAPEIS_QUE_TRATAM_PEDIDOS)


async def _so_o_titular(request: Request, process_id: str, user: dict = Depends(_acesso)) -> None:
    """Escritas da bancada: o Index só age nos processos seus ou sem indexador; para o de um colega,
    «Atribuir a mim» primeiro (decisão do cliente, Out 2026). A gestão passa sempre."""
    papel = await get_effective_role_async(request, user)
    await run_exigir_titularidade(user, process_id, papel)


class AnalyzeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False


class TitularDoFicheiroBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titular: str = Field(pattern=r"^titular[12]$")


class EditJobBody(BaseModel):
    """Só os campos do trabalho: o resto (job_id, origem, confiança) nunca vem do cliente."""

    model_config = ConfigDict(extra="forbid")

    fields: dict = Field(default_factory=dict)


class EmployerNif(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    nif: str


class PedidoDeAtribuicaoBody(BaseModel):
    """O motivo é opcional: o Index pode pedir sem explicar."""

    model_config = ConfigDict(extra="forbid")

    motivo: Optional[str] = Field(None, max_length=pedidos_de_atribuicao.MAX_MOTIVO)


class ResolverPedidoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisao: str = Field(pattern=r"^(concluido|recusado)$")
    nota: Optional[str] = Field(None, max_length=pedidos_de_atribuicao.MAX_MOTIVO)


class MarkIndexedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employers: list[EmployerNif] = Field(default_factory=list, max_length=20)


@router.get("/queue")
@limiter.limit("120/minute")
async def get_index_queue(
    request: Request,
    response: Response,
    tab: str = Query("pending"),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    q: Optional[str] = Query(None, max_length=100),
    sort_by: Optional[str] = Query(
        None, max_length=30,
        description="«<campo>_<asc|desc>»: created, indexed (só Revisões), number, client, company, status, alerts."),
    index_status: Optional[str] = Query(None, max_length=20, description="pending | in_review (Fila) · indexed (Revisões)."),
    company_id: Optional[str] = Query(None, max_length=64, description="Só os processos desta empresa."),
    origin: Optional[str] = Query(None, max_length=10, description="own (da minha rede) | shared (partilhados por outra)."),
    mine: bool = Query(False, description="Só os processos atribuídos a quem pergunta («Os Meus Processos» do Index)."),
    user: dict = Depends(_acesso),
):
    """Duas abas: `pending` («Fila de Espera») e `reviews` («Revisões Pendentes»).

    Ordenação e filtros só estreitam a fila (o âmbito de rede vem primeiro); valores fora das listas são 422.
    """
    return await run_get_index_queue(
        user, tab=tab, page=page, size=size, q=q,
        sort_by=sort_by, index_status=index_status, company_id=company_id, origin=origin, mine=mine,
    )


@router.get("/advanced-search")
@limiter.limit("60/minute")
async def advanced_search(
    request: Request,
    response: Response,
    min_salary: Optional[Decimal] = Query(None, ge=0, description="Líquido mínimo do recibo (EUR)."),
    max_salary: Optional[Decimal] = Query(None, ge=0, description="Líquido máximo do recibo (EUR)."),
    contract_type: Optional[list[str]] = Query(
        None, description="efetivo | termo_certo | termo_incerto | outro (repetível)."),
    employer_nif: Optional[str] = Query(None, max_length=20, description="NIF da entidade (prefixo, ≥3 dígitos)."),
    employer_name: Optional[str] = Query(None, max_length=100),
    employer_location: Optional[str] = Query(None, max_length=100, description="Localidade/concelho/distrito da sede."),
    job_title: Optional[str] = Query(None, max_length=100),
    period_from: Optional[str] = Query(None, description="YYYY-MM"),
    period_to: Optional[str] = Query(None, description="YYYY-MM"),
    sort: str = Query("period_desc", description="period_desc | salary_desc | salary_asc"),
    document_type: Optional[str] = Query(
        None, description="recibo | declaracao_efetividade | extrato | todos — pesquisa por DOCUMENTO em vez de por emprego."),
    bank: Optional[str] = Query(None, max_length=80, description="Banco do extrato (só com document_type=extrato ou todos)."),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=TAMANHO_MAXIMO_DA_PAGINA),
    user: dict = Depends(_acesso),
):
    """Pesquisa os metadados profissionais extraídos pela IA — um resultado por emprego.

    Sem `document_type`: um resultado por emprego, todos os filtros valem para o MESMO emprego.
    Com `document_type`: um resultado por DOCUMENTO (recibos isolados por valor, declarações de efetividade
    por localidade, extratos por banco). Só aparecem processos do âmbito de quem pergunta.
    """
    return await run_advanced_search(
        user, min_salary=min_salary, max_salary=max_salary, contract_type=contract_type,
        employer_nif=employer_nif, employer_name=employer_name, employer_location=employer_location,
        job_title=job_title, period_from=period_from, period_to=period_to, sort=sort, page=page, size=size,
        document_type=document_type, bank=bank,
    )


@router.get("/documents/{document_id}/content")
@limiter.limit("120/minute")
async def get_document_content(
    request: Request,
    response: Response,
    document_id: str,
    download: bool = Query(
        False, description="true → `Content-Disposition: attachment` (guardar o ficheiro em vez de o mostrar)."),
    user: dict = Depends(_acesso),
):
    """Os bytes de um documento que a pesquisa devolveu (recibo, declaração, extrato), para o ver no ecrã
    (`inline`) ou para o descarregar (`?download=true`, `attachment`, com rasto de auditoria).

    404 igual ao de «não existe» fora do âmbito de rede; a chave S3 sai do registo, nunca do pedido.
    """
    return await run_conteudo_do_documento(user, document_id, descarregar=download, request=request)


@router.get("/processes/{process_id}/files/{document_id}/content")
@limiter.limit("120/minute")
async def get_process_file_content(
    request: Request,
    response: Response,
    process_id: str,
    document_id: str,
    download: bool = Query(
        False, description="true → `Content-Disposition: attachment` (guardar o ficheiro em vez de o mostrar)."),
    user: dict = Depends(_acesso),
):
    """Um ficheiro da bancada de um processo, para ver (`inline`) ou descarregar (`?download=true`).

    Serve qualquer tipo que a bancada lista; o ficheiro tem de ser do processo do caminho (404 igual ao de
    «não existe» fora do âmbito de rede ou de outro processo). A chave S3 sai do registo, nunca do pedido.
    """
    return await run_conteudo_do_ficheiro_do_processo(user, process_id, document_id, descarregar=download, request=request)


@router.get("/employers")
@limiter.limit("120/minute")
async def search_employers(
    request: Request,
    response: Response,
    q: str = Query("", max_length=100),
    user: dict = Depends(_acesso),
):
    """Directório GLOBAL de entidades patronais (NIF + nome; nunca dados de clientes)."""
    return await run_search_employers(user, q)


@router.get("/processes/{process_id}")
@limiter.limit("120/minute")
async def get_index_workstation(
    request: Request,
    response: Response,
    process_id: str,
    user: dict = Depends(_acesso),
):
    return await run_get_index_workstation(user, process_id)


@router.post("/processes/{process_id}/start")
@limiter.limit("60/minute")
async def start_work(request: Request, response: Response, process_id: str, user: dict = Depends(_acesso)):
    """O indexador atribuído abriu a bancada: `pending → in_review` (substitui o «Reivindicar» manual)."""
    return await run_start_work(user, process_id)


@router.post("/processes/{process_id}/assumir")
@limiter.limit("30/minute")
async def assumir_processo(
    request: Request, response: Response, process_id: str,
    user: dict = Depends(_acesso),
    _papel: dict = Depends(_so_o_index),
):
    """«Atribuir a mim»: o indexador assume um processo «Por indexar» que ninguém começou."""
    return await run_assumir_processo(user, process_id)


@router.post("/processes/{process_id}/analyze", status_code=202)
@limiter.limit("20/minute")
async def analyze_process(
    request: Request,
    response: Response,
    process_id: str,
    data: AnalyzeBody = Body(default_factory=AnalyzeBody),
    user: dict = Depends(_acesso), _titular: None = Depends(_so_o_titular),
):
    """«Analisar»: corre em segundo plano e devolve já; o resultado chega como notificação."""
    return await run_analyze_process(user, process_id, force=data.force)


@router.post("/processes/{process_id}/extract", status_code=202)
@limiter.limit("20/minute")
async def extract_process(
    request: Request, response: Response, process_id: str,
    user: dict = Depends(_acesso), _titular: None = Depends(_so_o_titular),
):
    """«Extrair dados»: volta a extrair TUDO (ignora a impressão digital)."""
    return await run_analyze_process(user, process_id, force=True)


@router.post("/processes/{process_id}/sanitize", status_code=202)
@limiter.limit("10/minute")
async def sanitize_process(
    request: Request, response: Response, process_id: str,
    user: dict = Depends(_acesso), _titular: None = Depends(_so_o_titular),
):
    """«Apagar metadados»: gera o PDF limpo dos ficheiros carregados pelo Index (original mantido na graça)."""
    return await run_sanitize_process(user, process_id)


@router.patch("/processes/{process_id}/professional-metadata/{job_id}")
@limiter.limit("60/minute")
async def edit_professional_job(
    request: Request,
    response: Response,
    process_id: str,
    job_id: str,
    data: EditJobBody,
    user: dict = Depends(_acesso), _titular: None = Depends(_so_o_titular),
):
    """Edição humana de campos de um trabalho: fica `edited_by_human` e sobrevive à reanálise."""
    return await run_edit_professional_job(user, process_id, job_id, data.fields)


@router.post("/processes/{process_id}/alerts/{alert_id}/dismiss")
@limiter.limit("60/minute")
async def dismiss_alert(
    request: Request, response: Response, process_id: str, alert_id: str,
    user: dict = Depends(_acesso), _titular: None = Depends(_so_o_titular),
):
    return await run_dismiss_alert(user, process_id, alert_id)


@router.patch("/processes/{process_id}/files/{document_id}/titular")
@limiter.limit("60/minute")
async def set_file_titular(
    request: Request, response: Response, process_id: str, document_id: str, data: TitularDoFicheiroBody,
    user: dict = Depends(_acesso), _titular: None = Depends(_so_o_titular),
):
    """De quem é o ficheiro (1.º/2.º titular): manda na substituição, no emprego e nos rendimentos."""
    return await run_set_file_titular(user, process_id, document_id, data.titular)


@router.post("/processes/{process_id}/mark-indexed")
@limiter.limit("30/minute")
async def mark_indexed(
    request: Request,
    response: Response,
    process_id: str,
    data: MarkIndexedBody = Body(default_factory=MarkIndexedBody),
    user: dict = Depends(_acesso), _titular: None = Depends(_so_o_titular),
):
    """Marcar como indexado — SEMPRE possível (a IA, os campos em dúvida e os alertas só avisam)."""
    return await run_mark_indexed(
        process_id,
        user,
        user_role=get_effective_role(request, user).lower(),
        all_roles=get_all_user_roles(user),
        broadcast_fn=broadcast_process_delta,
        employers=[e.model_dump() for e in data.employers],
    )


# ====================================================================
# PEDIDOS DE ALTERAÇÃO DE ATRIBUIÇÃO (Out 2026)
# ====================================================================
@router.post("/processes/{process_id}/pedido-atribuicao", status_code=201)
@limiter.limit("20/minute")
async def pedir_alteracao_de_atribuicao(
    request: Request,
    response: Response,
    process_id: str,
    data: PedidoDeAtribuicaoBody = Body(default_factory=PedidoDeAtribuicaoBody),
    user: dict = Depends(_acesso),
    _papel: dict = Depends(_so_o_index),
):
    """O Index pede à chefia que altere a atribuição do processo (motivo opcional). Não muda nada sozinho."""
    return await pedidos_de_atribuicao.run_pedir_alteracao(user, process_id, data.motivo)


@router.get("/pedidos-atribuicao")
@limiter.limit("120/minute")
async def listar_pedidos_de_atribuicao(
    request: Request,
    response: Response,
    estado: Optional[str] = Query("pendente", max_length=20, description="pendente | concluido | recusado."),
    process_id: Optional[str] = Query(None, max_length=64),
    user: dict = Depends(_acesso),
):
    """A chefia vê os pedidos da sua rede; o Index só os seus. Perfil EFECTIVO."""
    papel = (await get_effective_role_async(request, user) or "").lower()
    return await pedidos_de_atribuicao.run_listar_pedidos(
        user, so_meus=papel not in PAPEIS_QUE_TRATAM_PEDIDOS, estado=estado or None, process_id=process_id,
    )


@router.post("/pedidos-atribuicao/{pedido_id}/resolver")
@limiter.limit("60/minute")
async def resolver_pedido_de_atribuicao(
    request: Request,
    response: Response,
    pedido_id: str,
    data: ResolverPedidoBody,
    user: dict = Depends(_acesso),
    _papel: dict = Depends(_so_a_chefia),
):
    """A chefia fecha o pedido: «concluido» (tratado pelo «Gerir» do processo) ou «recusado»."""
    return await pedidos_de_atribuicao.run_resolver_pedido(user, pedido_id, data.decisao, data.nota)


@router.get("/processes/{process_id}/conversa")
@limiter.limit("120/minute")
async def get_conversa(request: Request, response: Response, process_id: str, user: dict = Depends(_acesso)):
    """A conversa do processo com quem o carregou (mensagens do chat interno marcadas com o processo)."""
    return await run_ler_conversa_do_index(user, process_id)


@router.post("/processes/{process_id}/conversa")
@limiter.limit("30/minute")
async def post_conversa(
    request: Request, response: Response, process_id: str, data: MensagemDaConversa,
    user: dict = Depends(_acesso),
):
    """Escrever a quem carregou o processo. Conversar não é agir: não exige ser o indexador atribuído."""
    return await run_enviar_do_index(user, process_id, data)
