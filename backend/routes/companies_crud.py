"""
====================================================================
ROTAS: Companies — CRUD de Empresas (Multi-Tenant)
====================================================================
Gestão de empresas configuradas no sistema.

A autenticação requer role admin ou CEO.

PREFIX: /admin/companies
====================================================================
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

from database import db
from models.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanyListResponse,
)
from services.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/companies",
    tags=["Companies"],
    dependencies=[Depends(require_admin())]
)


def _resolve_logo_url(logo_value) -> Optional[str]:
    """
    Resolve o campo ``logo_url`` para um URL carregável pelo browser.

    O campo ``logo_url`` pode conter:
    - ``None`` / vazio → devolve ``None``.
    - Um URL absoluto (``http://`` / ``https://``) → devolve como está
      (ex.: logótipos configurados manualmente via API).
    - Uma chave S3 (ex.: ``companies/{id}/logo_image.png``) → gera um
      URL pré-assinado com validade de 7 dias.

    O URL pré-assinado é gerado em tempo de leitura (nunca guardado na BD)
    para evitar que expire. O frontend recebe sempre um link fresco e válido.
    """
    if not logo_value or not isinstance(logo_value, str):
        return None
    if logo_value.startswith(("http://", "https://")):
        return logo_value
    # Tratar como chave S3 — gerar URL pré-assinado
    try:
        from services.s3_storage import s3_service
        if s3_service.is_configured():
            # 7 dias (604800s) — máximo para credenciais de longa duração
            url = s3_service.get_presigned_url(logo_value, expiration=7 * 24 * 3600)
            if url:
                return url
    except Exception as e:
        logger.warning(f"[COMPANIES] Erro ao gerar pre-signed URL para logo '{logo_value}': {e}")
    # Fallback: devolver a chave (o frontend mostra placeholder se falhar)
    return None


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    search: Optional[str] = Query(None, description="Pesquisa por nome ou NIF"),
):
    """
    Lista todas as empresas configuradas no sistema.
    Inclui contagem de utilizadores por empresa.
    """
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"nif": {"$regex": search, "$options": "i"}},
        ]

    companies = await db.companies.find(
        query, {"_id": 0}
    ).sort("name", 1).to_list(200)

    result = []
    for c in companies:
        # Contar utilizadores associados a esta empresa
        total_users = await db.users.count_documents({
            "company": c.get("name", "")
        })
        doc = {**c, "total_users": total_users}
        # Resolver logo_url (chave S3 → URL pré-assinado fresco)
        doc["logo_url"] = _resolve_logo_url(doc.get("logo_url"))
        result.append(CompanyResponse(**doc).model_dump())

    return CompanyListResponse(companies=result, total=len(result))


@router.get("/available", response_model=list)
async def list_available_companies():
    """
    Lista nomes das empresas disponíveis (para selects/dropdowns).
    Retorna apenas id + name.
    """
    cursor = db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1}
    ).sort("name", 1)
    return await cursor.to_list(200)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str):
    """Obtém uma empresa pelo ID (ou por nome como fallback)."""
    # Tentar por ID primeiro
    company = await db.companies.find_one(
        {"id": company_id}, {"_id": 0}
    )
    # PACOTE AR: fallback — procurar por nome (algumas empresas migradas
    # têm o nome como ID em vez de UUID)
    if not company:
        company = await db.companies.find_one(
            {"name": company_id}, {"_id": 0}
        )
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    # Garantir campos obrigatórios para CompanyResponse
    if not company.get("id"):
        company["id"] = company.get("name", company_id)
    if not company.get("name"):
        company["name"] = company_id
    company.setdefault("email_sync_enabled", False)
    company.setdefault("total_users", 0)

    total_users = await db.users.count_documents({
        "company": company.get("name", "")
    })
    company["total_users"] = total_users
    # Resolver logo_url (chave S3 → URL pré-assinado fresco)
    company["logo_url"] = _resolve_logo_url(company.get("logo_url"))
    return CompanyResponse(**company)


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(data: CompanyCreate):
    """Cria uma nova empresa."""
    # Verificar nome duplicado
    existing = await db.companies.find_one({"name": data.name})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma empresa com o nome '{data.name}'"
        )

    now = datetime.now(timezone.utc).isoformat()
    company_id = str(uuid.uuid4())

    doc = {
        "id": company_id,
        "name": data.name,
        "nif": data.nif,
        "address": data.address,
        "phone": data.phone,
        "email": data.email,
        "website": data.website,
        "logo_url": data.logo_url,
        "email_sync_enabled": data.email_sync_enabled,
        "created_at": now,
        "updated_at": now,
    }

    await db.companies.insert_one(doc)
    logger.info(f"[COMPANIES] Empresa criada: {data.name} ({company_id})")

    return CompanyResponse(**doc)


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(company_id: str, data: CompanyUpdate):
    """Atualiza os dados de uma empresa."""
    # PACOTE AR: tentar por ID ou por nome (fallback para empresas migradas)
    existing = await db.companies.find_one({"id": company_id})
    if not existing:
        existing = await db.companies.find_one({"name": company_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    # Usar o ID real do documento encontrado (pode ser diferente do company_id)
    real_id = existing.get("id", company_id)

    # Se o nome mudou, verificar duplicado
    if data.name and data.name != existing.get("name"):
        dup = await db.companies.find_one({"name": data.name})
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe uma empresa com o nome '{data.name}'"
            )
        # Atualizar referência em utilizadores se o nome mudou
        old_name = existing.get("name")
        if old_name:
            await db.users.update_many(
                {"company": old_name},
                {"$set": {"company": data.name}}
            )
            logger.info(
                f"[COMPANIES] Nome da empresa '{old_name}' → '{data.name}' "
                f"atualizado em utilizadores"
            )

    update_fields = data.model_dump(exclude_unset=True)
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.companies.update_one(
        {"id": real_id},
        {"$set": update_fields}
    )

    updated = await db.companies.find_one({"id": real_id}, {"_id": 0})
    if not updated:
        updated = existing
        updated.update(update_fields)
    total_users = await db.users.count_documents({
        "company": updated.get("name", "")
    })
    updated["total_users"] = total_users
    if not updated.get("id"):
        updated["id"] = real_id
    if not updated.get("name"):
        updated["name"] = company_id

    logger.info(f"[COMPANIES] Empresa atualizada: {real_id}")
    return CompanyResponse(**updated)


@router.delete("/{company_id}")
async def delete_company(company_id: str):
    """Remove uma empresa e gere utilizadores associados.

    COMPORTAMENTO MULTI-EMPRESA (Pacote AS):
    - Users com APENAS esta empresa → BLOQUEAR (não podem ficar sem empresa)
    - Users com OUTRAS empresas (UCR) → DESASSOCIAR esta empresa (remover
      o UCR, limpar user_email_configs, manter as outras empresas)
    - Se o user tem `company` (campo legacy) = nome da empresa eliminada,
      e tem UCRs para outras empresas → mudar `company` para a primeira UCR
    """
    # PACOTE AR: tentar por ID ou por nome
    company = await db.companies.find_one({"id": company_id})
    if not company:
        company = await db.companies.find_one({"name": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    real_id = company.get("id", company_id)
    company_name = company.get("name", company_id)

    # ── 1. Verificar utilizadores com APENAS esta empresa (bloquear) ──
    # Users cujo campo `company` = nome da empresa E não têm UCRs para outras
    users_with_this_company = await db.users.find(
        {"company": company_name},
        {"_id": 0, "id": 1, "name": 1, "email": 1}
    ).to_list(1000)

    blocked_users = []
    reassigned_users = []

    for u in users_with_this_company:
        # Verificar se tem UCRs para OUTRAS empresas
        other_ucrs = await db.user_company_roles.find({
            "user_id": u["id"],
            "company_id": {"$ne": real_id},
        }).to_list(10)

        if other_ucrs:
            # Tem outras empresas → desassociar esta e mudar company default
            first_other = other_ucrs[0]
            new_company = first_other.get("company_name", first_other.get("company_id", "default"))
            await db.users.update_one(
                {"id": u["id"]},
                {"$set": {"company": new_company}}
            )
            reassigned_users.append({"id": u["id"], "name": u.get("name", ""), "new_company": new_company})
        else:
            # Só tem esta empresa → bloquear
            blocked_users.append({"id": u["id"], "name": u.get("name", ""), "email": u.get("email", "")})

    if blocked_users:
        names = ", ".join([f"{u['name']} ({u['email']})" for u in blocked_users[:5]])
        suffix = f" e mais {len(blocked_users)-5}" if len(blocked_users) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível eliminar: {len(blocked_users)} utilizador(es) "
                   f"têm apenas esta empresa: {names}{suffix}. "
                   f"Atribua outra empresa a estes utilizadores primeiro."
        )

    # ── 2. Desassociar UCRs desta empresa ──
    deleted_ucrs = await db.user_company_roles.delete_many({"company_id": real_id})

    # ── 3. Remover configs de email da empresa ──
    await db.company_email_configs.delete_one({"company_name": company_name})
    await db.user_email_configs.delete_many({"company_id": real_id})

    # ── 4. Eliminar a empresa ──
    await db.companies.delete_one({"id": real_id})

    logger.info(
        f"[COMPANIES] Empresa eliminada: {company_name} ({real_id}). "
        f"UCRs removidos: {deleted_ucrs.deleted_count}. "
        f"Users reatribuídos: {len(reassigned_users)}."
    )
    return {
        "detail": "Empresa eliminada com sucesso",
        "affected_users": len(reassigned_users),
        "reassigned_users": reassigned_users,
        "ucrs_removed": deleted_ucrs.deleted_count,
    }


@router.post("/{company_id}/logo")
async def upload_company_logo(
    company_id: str,
    file: UploadFile = File(...),
):
    """Faz upload do logótipo da empresa para o S3."""
    # PACOTE AR: tentar por ID ou por nome
    company = await db.companies.find_one({"id": company_id})
    if not company:
        company = await db.companies.find_one({"name": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    real_id = company.get("id", company_id)

    # Validar tipo de ficheiro
    allowed_types = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de ficheiro não permitido: {file.content_type}. "
                   f"Use PNG, JPEG, GIF, WebP ou SVG."
        )

    # Limitar tamanho a 2MB
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="O logótipo não pode exceder 2MB."
        )

    # Fazer upload para S3
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    s3_key = f"companies/{real_id}/logo_{file.filename or 'image.png'}"
    s3_service.s3_client.put_object(
        Bucket=s3_service.bucket_name,
        Key=s3_key,
        Body=content,
        ContentType=file.content_type,
    )

    # CORREÇÃO (F821): antes era `logo_url = file_key` (variável inexistente).
    # Guarda-se a CHAVE S3 no campo logo_url da BD; o URL pré-assinado é
    # gerado em tempo de leitura pelos endpoints GET (list/get) via
    # _resolve_logo_url(). Isto evita que o link expire na BD.
    logo_s3_key = s3_key

    # Atualizar a empresa
    await db.companies.update_one(
        {"id": real_id},
        {"$set": {
            "logo_url": logo_s3_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    # Devolver um URL pré-assinado para o frontend mostrar de imediato
    logo_url = _resolve_logo_url(logo_s3_key)

    logger.info(f"[COMPANIES] Logótipo atualizado: {company_id} → {logo_s3_key}")
    return {"logo_url": logo_url, "logo_s3_key": logo_s3_key}