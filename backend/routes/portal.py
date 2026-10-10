"""
CLIENT PORTAL - Routes
======================
Thin FastAPI stubs — logic lives in services/portal_*.py

SEGURANÇA:
- Endpoints de cliente usam get_current_client (role="client_portal")
- NUNCA devolvem dados sensíveis (notas internas, NIF, dados financeiros)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Response, Query
from fastapi.responses import JSONResponse

from middleware.rate_limit import limiter

from services.portal_security import get_current_client
from services.auth import get_current_user, require_staff

from services.portal_doc_categories import (
    DOCUMENT_CATEGORY_MAP,
    PORTAL_HIDDEN_CATEGORIES,
)
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.portal_profile import (
    ClientProfileUpdate,
    run_get_client_profile,
    run_update_client_profile,
)
from services.portal_auth import (
    PortalLoginRequest,
    run_portal_login,
    run_verify_portal_login,
    run_resolve_portal_token,
    run_impersonate_client_portal,
    run_authenticate_portal,
)
from services.portal_status import run_get_portal_status
from services.portal_upload_ops import (
    run_generate_portal_upload_url,
    run_confirm_portal_upload,
    run_get_portal_download_url,
)
from services.portal_client_messages import (
    run_get_unread_messages_count,
    run_get_portal_messages,
    run_send_portal_message,
)
from services.portal_gov_fetch import (
    run_check_scraper_status,
    run_fetch_financas_documents,
    run_fetch_seguranca_social_documents,
    run_submit_mfa_code,
    run_get_scraper_job_status,
)
from services.portal_recommendations import (
    run_create_recommendations,
    run_get_recommendations_for_client,
)
from services.portal_client_visits import (
    run_request_portal_visit,
    run_get_portal_visits,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Client Portal"])


# ====================================================================
# LOTE 10 — D-4: OS NOVE POST DO PORTAL SEM LIMITE
# ====================================================================
# O Portal é a ÚNICA superfície externa do sistema e tinha nove POST sem
# limite nenhum, ao lado de um `/public/client-registration` com `5/hour`
# desde sempre. Três notas que não se podem perder:
#
# 1. **A chave do limite depende de haver JWT.** O `_get_rate_limit_key`
#    decodifica o token e devolve `user:<sub>`; no Portal o `sub` é o
#    `process_id`, logo nos endpoints AUTENTICADOS o limite é por
#    processo, que é o âmbito certo. Nos dois de PRÉ-autenticação
#    (`/auth/login` e `/{client_id}/verify`) não há token, a chave cai no
#    IP — e o IP sai do `X-Forwarded-For`, que é um cabeçalho que o
#    cliente envia. **Quem ataca muda-o a cada pedido e o limite não
#    morde.** Por isso a força bruta desses dois é travada por
#    IDENTIDADE, no `portal_brute_force`, e o limite aqui é a primeira
#    linha e não a parede. Fica registado na D-4 em vez de dar a questão
#    por fechada.
#
# 2. **`response: Response` não é decorativo.** O limiter corre com
#    `headers_enabled=True` e, sem esse parâmetro, o caminho de SUCESSO
#    devolve 500 (incidente de Set 2026: onze dos catorze endpoints
#    limitados estavam assim). A bateria de rejeições não o apanha —
#    num caminho de erro a excepção sobe antes da injecção dos
#    cabeçalhos.
#
# 3. **O limite do middleware por papel NÃO serve aqui.** O
#    `user_rate_limit_middleware` dá 400–600 pedidos/minuto a um cliente,
#    o que é um travão de DDoS; 400 tentativas por minuto contra um
#    número de processo sequencial não é travão nenhum. (E o papel do
#    Portal, `client_portal`, não está no `RATE_LIMITS_BY_ROLE`, pelo que
#    cai no `default` de 600 — mais alto do que o de `cliente`.)
# ====================================================================


@router.post("/auth/login")
@limiter.limit("10/minute")
async def portal_login(
    request: Request,
    response: Response,
    data: PortalLoginRequest,
):
    return await run_portal_login(data)


@router.post("/{client_id}/verify")
@limiter.limit("10/minute")
async def verify_portal_login(
    request: Request,
    response: Response,
    client_id: str,
    data: dict,
):
    return await run_verify_portal_login(client_id, data)


@router.get("/resolve/{short_id}")
async def resolve_portal_token(short_id: str):
    return await run_resolve_portal_token(short_id)


@router.get("/impersonate/{process_id}")
async def impersonate_client_portal(
    process_id: str,
    request: Request,
    user: dict = Depends(require_staff()),
):
    return await run_impersonate_client_portal(process_id, request, user)


# 30/minuto: é chamado no arranque do Portal e numa navegação normal
# pode repetir-se; o que se fecha é o ciclo automático.
@router.post("/authenticate")
@limiter.limit("30/minute")
async def authenticate_portal(
    request: Request,
    response: Response,
    client_data: dict = Depends(get_current_client),
):
    return await run_authenticate_portal(client_data)


@router.get("/me")
async def get_client_profile(client_data: dict = Depends(get_current_client)):
    return await run_get_client_profile(client_data)


@router.put("/me")
@limiter.limit("20/minute")
async def update_client_profile(
    request: Request,
    response: Response,
    data: ClientProfileUpdate,
    client_data: dict = Depends(get_current_client),
):
    return await run_update_client_profile(data, client_data)


@router.get("/status")
async def get_portal_status(client_data: dict = Depends(get_current_client)):
    return await run_get_portal_status(client_data)


# INCIDENTE P0 (Set 2026) — estes três endpoints não tinham limite NENHUM.
# O `/public/client-registration`, ao lado, tem `5/hour`; aqui, a exploração
# do `confirm-upload` podia ser repetida à vontade para varrer o bucket chave
# a chave. O `_get_rate_limit_key` do limiter resolve a chave pelo `sub` do
# JWT — e no Portal o `sub` É o `process_id`, pelo que o limite fica por
# processo (não por IP partilhado), que é exactamente o âmbito certo.
# 20/minuto deixa passar um lote de ficheiros do cliente e fecha o varrimento.
@router.post("/upload-url")
@limiter.limit("20/minute")
async def generate_portal_upload_url(
    request: Request,
    response: Response,
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_generate_portal_upload_url(data, client_data)


@router.post("/confirm-upload")
@limiter.limit("20/minute")
async def confirm_portal_upload(
    request: Request,
    response: Response,
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_confirm_portal_upload(data, client_data)


@router.get("/download-url")
@limiter.limit("60/minute")
async def get_portal_download_url(
    request: Request,
    response: Response,
    file_key: str,
    client_data: dict = Depends(get_current_client),
):
    return await run_get_portal_download_url(file_key, client_data)


@router.get("/messages/unread")
async def get_unread_messages_count(client_data: dict = Depends(get_current_client)):
    return await run_get_unread_messages_count(client_data)


@router.get("/messages")
async def get_portal_messages(client_data: dict = Depends(get_current_client)):
    return await run_get_portal_messages(client_data)


# Escreve na conversa e NOTIFICA a equipa atribuída: sem tecto, é um
# canal para enxurrada de notificações a quem trata do processo.
@router.post("/messages")
@limiter.limit("20/minute")
async def send_portal_message(
    request: Request,
    response: Response,
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_send_portal_message(data, client_data)


@router.get("/scraper-status")
async def check_scraper_status(client_data: dict = Depends(get_current_client)):
    return await run_check_scraper_status(client_data)


# 5/minuto nos dois scrapers governamentais: cada pedido abre uma
# ligação de SAÍDA para o portal das Finanças / Segurança Social com
# credenciais do cliente e mantém uma sessão à espera de MFA. É o par de
# endpoints de maior consequência da D-4 — um ciclo aqui faz o nosso IP
# bater num serviço do Estado.
@router.post("/fetch-financas")
@limiter.limit("5/minute")
async def fetch_financas_documents(
    request: Request,
    response: Response,
    data: dict,
    background_tasks: BackgroundTasks,
    client_data: dict = Depends(get_current_client),
):
    return await run_fetch_financas_documents(data, background_tasks, client_data)


@router.post("/fetch-seguranca-social")
@limiter.limit("5/minute")
async def fetch_seguranca_social_documents(
    request: Request,
    response: Response,
    data: dict,
    background_tasks: BackgroundTasks,
    client_data: dict = Depends(get_current_client),
):
    return await run_fetch_seguranca_social_documents(data, background_tasks, client_data)


# Um código de MFA é CURTO. Sem tecto, o espaço de busca percorre-se
# depressa — e aqui o limite por processo é o eixo certo, porque é o
# processo que tem a sessão governamental aberta.
@router.post("/submit-mfa")
@limiter.limit("10/minute")
async def submit_mfa_code(
    request: Request,
    response: Response,
    data: dict,
    client_data: dict = Depends(get_current_client),
):
    return await run_submit_mfa_code(data, client_data)


@router.get("/scraper-job/{job_id}")
async def get_scraper_job_status(job_id: str, client_data: dict = Depends(get_current_client)):
    return await run_get_scraper_job_status(job_id, client_data)


# Este é de STAFF (`get_current_user`), não do cliente: a chave do
# limite é o `sub` do utilizador, e por isso o tecto é mais largo.
@router.post("/recommendations")
@limiter.limit("30/minute")
async def create_recommendations(
    request: Request,
    response: Response,
    data: dict,
    user: dict = Depends(get_current_user),
):
    return await run_create_recommendations(data, user)


@router.get("/recommendations")
async def get_recommendations_for_client(
    client_data: dict = Depends(get_current_client),
):
    return await run_get_recommendations_for_client(client_data)


# LOTE 9 (Fase B) — este endpoint faz o servidor ir BUSCAR um URL que o
# cliente escolhe, com anti-bot e seguimento de links, e ainda escreve um
# registo e notifica a equipa. O SSRF está validado no `scraper.py` (IPs
# privados recusados), logo não é pivô para a rede interna — mas sem
# limite era amplificação e custo de IA sem tecto, na única superfície
# externa. No Portal o `sub` do JWT é o `process_id`, logo o limite é POR
# PROCESSO.
#
# O `response: Response` na assinatura NÃO é decorativo: o limiter corre
# com `headers_enabled=True` e, sem ele, o caminho de SUCESSO devolve 500
# (incidente de Set 2026, onze dos catorze endpoints limitados).
@router.post("/visits/request")
@limiter.limit("10/minute")
async def request_portal_visit(
    request: Request,
    response: Response,
    data: dict,
    background_tasks: BackgroundTasks,
    client_data: dict = Depends(get_current_client),
):
    return await run_request_portal_visit(data, background_tasks, client_data)


@router.get("/visits")
async def get_portal_visits(client_data: dict = Depends(get_current_client)):
    return await run_get_portal_visits(client_data)


@router.get("/events")
async def get_portal_events(
    include_past: bool = Query(False, description="PACOTE DO.2 — incluir datas anteriores no calendário"),
    client_data: dict = Depends(get_current_client),
):
    """PACOTE DH — Eventos/prazos visíveis ao cliente no Portal."""
    from services.portal_events import run_get_portal_events
    return await run_get_portal_events(client_data, include_past=include_past)
