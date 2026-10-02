"""
====================================================================
O22 - API de Automação de Workflows — thin FastAPI stubs
====================================================================
Logic in services/automation_api_*.py.
====================================================================
"""
from fastapi import APIRouter, Depends, Request, Response

from middleware.rate_limit import limiter
from models.auth import UserRole
from services.auth import require_roles
from services.automation_api_rules import (
    RuleCreate,
    RuleUpdate,
    run_get_rules,
    run_get_rule_by_id,
    run_create_rule,
    run_update_rule,
    run_delete_rule,
)
from services.automation_api_engine import (
    run_forcar_execucao_de_job,
    run_get_automations_status,
)
from services.automation_api_meta import (
    run_list_triggers,
    run_list_actions,
)

router = APIRouter(prefix="/admin/automation", tags=["Automation"])

# Monitor de Sinais Vitais (Lote 4, ponto 14). Router SEPARADO porque o
# prefixo é outro: as regras são configuração de administração, o estado
# do motor é telemetria de leitura para quem gere a operação.
engine_router = APIRouter(prefix="/automations", tags=["Automation"])


@engine_router.get("")
async def get_automations_status(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Sinais vitais dos jobs de background (leitura)."""
    return await run_get_automations_status()


@engine_router.post("/{chave}/executar")
@limiter.limit("10/minute")
async def forcar_execucao_de_job(
    chave: str,
    request: Request,
    response: Response,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """Corre um job agora (Lote 2, ponto 1).

    O motor vive em dois processos do `render.yaml`: um job do processo
    web corre aqui mesmo, um job do Processador fica como PEDIDO na fila
    persistente e é reclamado no ciclo seguinte. A resposta diz qual dos
    dois aconteceu.

    Mais restrito do que a leitura (ADMIN/CEO, sem DIRETOR): ler o estado
    do motor é telemetria, forçar um ciclo é uma operação.

    `response: Response` na assinatura é obrigatório por causa do
    `@limiter.limit` — o slowapi precisa de um objecto `Response` para
    escrever os cabeçalhos `X-RateLimit-*` e, sem ele, o caminho de
    SUCESSO devolve 500 (Set 2026, onze endpoints).
    """
    return await run_forcar_execucao_de_job(chave, user=user)


@router.get("/rules")
async def get_rules(
    active_only: bool = False,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Listar todas as regras de automação."""
    return await run_get_rules(active_only, user)


@router.get("/rules/{rule_id}")
async def get_rule_by_id(
    rule_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obter uma regra específica."""
    return await run_get_rule_by_id(rule_id, user)


@router.post("/rules")
async def create_rule_endpoint(
    data: RuleCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Criar nova regra de automação."""
    return await run_create_rule(data, user)


@router.put("/rules/{rule_id}")
async def update_rule_endpoint(
    rule_id: str,
    data: RuleUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Actualizar uma regra."""
    return await run_update_rule(rule_id, data, user)


@router.delete("/rules/{rule_id}")
async def delete_rule_endpoint(
    rule_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Eliminar uma regra."""
    return await run_delete_rule(rule_id, user)


@router.get("/triggers")
async def list_triggers(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Listar triggers disponíveis com descrição."""
    return await run_list_triggers()


@router.get("/actions")
async def list_actions(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Listar ações disponíveis com descrição."""
    return await run_list_actions()
