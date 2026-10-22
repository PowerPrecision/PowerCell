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
from services.auth import get_all_user_roles, get_effective_role, require_roles
from services.index_access import PAPEIS_DE_IA_DO_INDEX
from services.index_advanced_search import TAMANHO_MAXIMO_DA_PAGINA, run_advanced_search
from services.index_document_content import run_conteudo_do_documento
from services.index_api import (
    run_analyze_process,
    run_claim_process,
    run_dismiss_alert,
    run_edit_professional_job,
    run_get_index_queue,
    run_get_index_workstation,
    run_release_process,
    run_sanitize_process,
    run_search_employers,
)
from services.index_finalize import run_mark_indexed
from services.process_broadcast import broadcast_process_delta
from services.process_closed_guard import exigir_processo_editavel
from services.process_scope_guard import exigir_processo_no_ambito

router = APIRouter(
    prefix="/index",
    tags=["Index"],
    dependencies=[Depends(exigir_processo_no_ambito), Depends(exigir_processo_editavel)],
)

_acesso = require_roles(PAPEIS_DE_IA_DO_INDEX)


class AnalyzeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False


class EditJobBody(BaseModel):
    """Só os campos do trabalho: o resto (job_id, origem, confiança) nunca vem do cliente."""

    model_config = ConfigDict(extra="forbid")

    fields: dict = Field(default_factory=dict)


class EmployerNif(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    nif: str


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
    user: dict = Depends(_acesso),
):
    """Duas abas: `pending` («Fila de Espera») e `reviews` («Revisões Pendentes»).

    Ordenação e filtros só estreitam a fila (o âmbito de rede vem primeiro); valores fora das listas são 422.
    """
    return await run_get_index_queue(
        user, tab=tab, page=page, size=size, q=q,
        sort_by=sort_by, index_status=index_status, company_id=company_id, origin=origin,
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
        None, description="recibo | declaracao_efetividade | extrato — pesquisa por DOCUMENTO em vez de por emprego."),
    bank: Optional[str] = Query(None, max_length=80, description="Banco do extrato (só com document_type=extrato)."),
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


@router.post("/processes/{process_id}/claim")
@limiter.limit("60/minute")
async def claim_process(request: Request, response: Response, process_id: str, user: dict = Depends(_acesso)):
    return await run_claim_process(user, process_id)


@router.post("/processes/{process_id}/release")
@limiter.limit("60/minute")
async def release_process(request: Request, response: Response, process_id: str, user: dict = Depends(_acesso)):
    return await run_release_process(user, process_id)


@router.post("/processes/{process_id}/analyze", status_code=202)
@limiter.limit("20/minute")
async def analyze_process(
    request: Request,
    response: Response,
    process_id: str,
    data: AnalyzeBody = Body(default_factory=AnalyzeBody),
    user: dict = Depends(_acesso),
):
    """«Analisar»: corre em segundo plano e devolve já; o resultado chega como notificação."""
    return await run_analyze_process(user, process_id, force=data.force)


@router.post("/processes/{process_id}/extract", status_code=202)
@limiter.limit("20/minute")
async def extract_process(request: Request, response: Response, process_id: str, user: dict = Depends(_acesso)):
    """«Extrair dados»: volta a extrair TUDO (ignora a impressão digital)."""
    return await run_analyze_process(user, process_id, force=True)


@router.post("/processes/{process_id}/sanitize", status_code=202)
@limiter.limit("10/minute")
async def sanitize_process(request: Request, response: Response, process_id: str, user: dict = Depends(_acesso)):
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
    user: dict = Depends(_acesso),
):
    """Edição humana de campos de um trabalho: fica `edited_by_human` e sobrevive à reanálise."""
    return await run_edit_professional_job(user, process_id, job_id, data.fields)


@router.post("/processes/{process_id}/alerts/{alert_id}/dismiss")
@limiter.limit("60/minute")
async def dismiss_alert(
    request: Request, response: Response, process_id: str, alert_id: str, user: dict = Depends(_acesso)
):
    return await run_dismiss_alert(user, process_id, alert_id)


@router.post("/processes/{process_id}/mark-indexed")
@limiter.limit("30/minute")
async def mark_indexed(
    request: Request,
    response: Response,
    process_id: str,
    data: MarkIndexedBody = Body(default_factory=MarkIndexedBody),
    user: dict = Depends(_acesso),
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
