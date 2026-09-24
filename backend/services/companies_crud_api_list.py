"""Company list / get handlers.

Extraído de `routes/companies_crud.py`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from database import db
from models.company import CompanyListResponse, CompanyResponse
from services.companies_crud_api_helpers import resolve_logo_url
from services.tenant_network import build_tenant_condition
from utils.input_sanitization import escape_regex

logger = logging.getLogger(__name__)

#: Página por omissão do painel de administração.
DEFAULT_PAGE_SIZE = 25
#: Tecto por pedido. Um `size` enorme reabriria o problema que a
#: paginação veio resolver.
MAX_PAGE_SIZE = 100


async def _count_company_users(company_id, company_name: str) -> int:
    """Conta utilizadores via UCR, com fallback ao campo legado `users.company`."""
    ucr_clauses = []
    if company_id:
        ucr_clauses.append({"company_id": company_id})
    if company_name:
        ucr_clauses.append({"company_name": company_name})
    total_users = 0
    if ucr_clauses:
        total_users = await db.user_company_roles.count_documents(
            {"$or": ucr_clauses}
        )
    if total_users == 0 and company_name:
        total_users = await db.users.count_documents({"company": company_name})
    return total_users


async def contar_utilizadores_por_empresa(empresas: list[dict]) -> dict[str, int]:
    """Quantos utilizadores tem cada empresa — numa agregação SÓ.

    O N+1 que isto mata: `_count_company_users` era chamado DENTRO do
    ciclo da listagem, uma query por empresa. 50 empresas = 51 idas à
    base de dados; 200 = 201.

    Conta pelo `company_id` e também pelo `company_name`, porque os UCRs
    antigos guardam o NOME — ignorá-los diria "0 utilizadores" numa
    empresa cheia.
    """
    if not empresas:
        return {}

    ids = [str(e["id"]) for e in empresas if e.get("id")]
    nomes = [str(e["name"]) for e in empresas if e.get("name")]

    ramos: list[dict] = []
    if ids:
        ramos.append({"company_id": {"$in": ids}})
    if nomes:
        ramos.append({"company_name": {"$in": nomes}})
    if not ramos:
        return {}

    por_id: dict[str, int] = {}
    por_nome: dict[str, int] = {}
    try:
        cursor = db.user_company_roles.aggregate([
            {"$match": {"$or": ramos}},
            {"$group": {
                "_id": {"cid": "$company_id", "cnome": "$company_name"},
                "n": {"$sum": 1},
            }},
        ])
        async for linha in cursor:
            chave = linha.get("_id") or {}
            n = int(linha.get("n") or 0)
            if chave.get("cid"):
                por_id[str(chave["cid"])] = por_id.get(str(chave["cid"]), 0) + n
            elif chave.get("cnome"):
                por_nome[str(chave["cnome"])] = por_nome.get(str(chave["cnome"]), 0) + n
    except Exception as exc:  # noqa: BLE001 — a contagem nunca bloqueia a lista
        logger.warning("[companies] Falha a contar utilizadores: %s", exc)
        return {}

    contagens: dict[str, int] = {}
    for empresa in empresas:
        cid = str(empresa.get("id") or "")
        nome = str(empresa.get("name") or "")
        if not cid:
            continue
        contagens[cid] = por_id.get(cid, 0) + por_nome.get(nome, 0)
    return contagens


async def run_list_companies(
    search: Optional[str] = None,
    *,
    user: Optional[dict] = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
):
    """Empresas que o utilizador pode administrar.

    ISOLAMENTO POR REDE (ponto 11): ser "admin" é ser admin da SUA rede,
    não do sistema. A condição vem do mesmo ponto único das listagens de
    processos (`services/tenant_network.py`).

    PAGINAÇÃO: o `.to_list(200)` que aqui estava truncava em SILÊNCIO —
    à empresa 201 a UI respondia que ela não existe. O `total` é contado
    dentro do âmbito, nunca na colecção inteira: um total global diria à
    Domus quantas empresas a Power tem.
    """
    condicoes: list[dict] = [await build_tenant_condition(user or {})]

    if search:
        escaped = escape_regex(search)
        condicoes.append({"$or": [
            {"name": {"$regex": escaped, "$options": "i"}},
            {"nif": {"$regex": escaped, "$options": "i"}},
        ]})

    query = {"$and": condicoes} if len(condicoes) > 1 else condicoes[0]

    tamanho = max(1, min(int(size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    pagina = max(1, int(page or 1))

    total = await db.companies.count_documents(query)
    companies = (
        await db.companies.find(query, {"_id": 0})
        .sort("name", 1)
        .skip((pagina - 1) * tamanho)
        .limit(tamanho)
        .to_list(tamanho)
    )

    contagens = await contar_utilizadores_por_empresa(companies)

    result = []
    for c in companies:
        doc = {**c, "total_users": contagens.get(str(c.get("id") or ""), 0)}
        doc.setdefault("is_active", True)
        doc["logo_url"] = resolve_logo_url(doc.get("logo_url"))
        result.append(CompanyResponse(**doc).model_dump())

    return CompanyListResponse(companies=result, total=total)


async def run_list_available_companies():
    """Lista nomes das empresas disponíveis (para selects/dropdowns)."""
    cursor = db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1}
    ).sort("name", 1)
    return await cursor.to_list(200)


async def run_get_company(company_id: str):
    """Obtém uma empresa pelo ID (ou por nome como fallback)."""
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        company = await db.companies.find_one({"name": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    if not company.get("id"):
        company["id"] = company.get("name", company_id)
    if not company.get("name"):
        company["name"] = company_id
    company.setdefault("email_sync_enabled", False)
    company.setdefault("is_active", True)
    company["total_users"] = await _count_company_users(
        company.get("id"), company.get("name", ""),
    )
    company["logo_url"] = resolve_logo_url(company.get("logo_url"))
    return CompanyResponse(**company)
