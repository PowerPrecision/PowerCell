"""Storage status handler.

Extraído de `routes/storage.py`.
Do **not** overwrite s3_storage.py / storage_service.py — use storage_api_*.
"""
from __future__ import annotations

import os


async def run_get_storage_status():
    """Obter status do armazenamento configurado."""
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    aws_bucket = os.environ.get("AWS_BUCKET_NAME", "")
    aws_region = os.environ.get("AWS_REGION", "")

    s3_configured = bool(aws_key and aws_bucket)

    onedrive_link = os.environ.get("ONEDRIVE_SHARED_LINK", "")
    onedrive_configured = bool(onedrive_link)

    if s3_configured:
        return {
            "configured": True,
            "provider": "AWS S3",
            "provider_icon": "cloud",
            "bucket": aws_bucket,
            "region": aws_region,
            "message": f"Armazenamento AWS S3 configurado ({aws_bucket})"
        }
    elif onedrive_configured:
        return {
            "configured": True,
            "provider": "OneDrive",
            "provider_icon": "folder",
            "shared_link": onedrive_link[:50] + "..." if len(onedrive_link) > 50 else onedrive_link,
            "message": "Armazenamento OneDrive configurado"
        }
    else:
        return {
            "configured": False,
            "provider": None,
            "message": "Nenhum armazenamento configurado"
        }
