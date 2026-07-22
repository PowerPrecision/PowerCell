"""Company logo upload handler.

Extraído de `routes/companies_crud.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile

from database import db
from services.companies_crud_api_helpers import resolve_logo_url

logger = logging.getLogger(__name__)


async def run_upload_company_logo(company_id: str, file: UploadFile):
    """Faz upload do logótipo da empresa para o S3."""
    company = await db.companies.find_one({"id": company_id})
    if not company:
        company = await db.companies.find_one({"name": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    real_id = company.get("id", company_id)

    allowed_types = {
        "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tipo de ficheiro não permitido: {file.content_type}. "
                f"Use PNG, JPEG, GIF, WebP ou SVG."
            ),
        )

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="O logótipo não pode exceder 2MB.",
        )

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

    logo_s3_key = s3_key

    await db.companies.update_one(
        {"id": real_id},
        {"$set": {
            "logo_url": logo_s3_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    logo_url = resolve_logo_url(logo_s3_key)

    logger.info(f"[COMPANIES] Logótipo atualizado: {company_id} → {logo_s3_key}")
    return {"logo_url": logo_url, "logo_s3_key": logo_s3_key}
