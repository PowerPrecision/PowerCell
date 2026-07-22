"""Minuta file-import handler.

Extraído de `routes/minutas.py`.
Do **not** overwrite services/rgpd_minutas.py.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile

from database import db
from utils.input_sanitization import sanitize_html, sanitize_string

logger = logging.getLogger(__name__)


def _detect_categoria(titulo: str) -> str:
    """Infer minuta category from filename/title keywords."""
    titulo_lower = titulo.lower()
    if "contrato" in titulo_lower or "promessa" in titulo_lower:
        return "contrato"
    if "procuração" in titulo_lower or "procuracao" in titulo_lower:
        return "procuracao"
    if "declaração" in titulo_lower or "declaracao" in titulo_lower:
        return "declaracao"
    if "carta" in titulo_lower:
        return "carta"
    return "outro"


def _extract_text_from_bytes(contents: bytes, ext: str) -> str:
    """Extract plain text from uploaded file bytes by extension."""
    if ext == "txt":
        return contents.decode("utf-8", errors="ignore")

    if ext in ["docx", "doc"]:
        try:
            import docx
            from io import BytesIO

            doc = docx.Document(BytesIO(contents))
            paragraphs = [
                para.text for para in doc.paragraphs if para.text.strip()
            ]
            return "\n\n".join(paragraphs)
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="Biblioteca python-docx não instalada",
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Erro ao ler ficheiro Word: {str(e)}",
            )

    if ext == "pdf":
        try:
            from pypdf import PdfReader
            from io import BytesIO

            reader = PdfReader(BytesIO(contents))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n\n".join(pages_text)
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="Biblioteca pypdf não instalada",
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Erro ao ler ficheiro PDF: {str(e)}",
            )

    raise HTTPException(
        status_code=400,
        detail="Formato não suportado. Use: .docx, .doc, .pdf, .txt",
    )


async def run_import_minuta(file: UploadFile, user: dict):
    """Importar uma minuta a partir de um ficheiro (.docx, .doc, .pdf, .txt)."""
    filename = file.filename or "documento.txt"
    ext = filename.lower().split(".")[-1]

    if ext not in ["docx", "doc", "pdf", "txt"]:
        raise HTTPException(
            status_code=400,
            detail="Formato não suportado. Use: .docx, .doc, .pdf, .txt",
        )

    try:
        contents = await file.read()
        text_content = _extract_text_from_bytes(contents, ext)

        if not text_content.strip():
            raise HTTPException(
                status_code=400,
                detail="Ficheiro vazio ou não foi possível extrair texto",
            )

        now = datetime.now(timezone.utc).isoformat()
        titulo = os.path.splitext(filename)[0]
        categoria = _detect_categoria(titulo)

        minuta_doc = {
            "id": str(uuid.uuid4()),
            "titulo": sanitize_string(titulo, max_length=300),
            "categoria": categoria,
            "descricao": sanitize_string(
                f"Importado de: {filename}", max_length=2000,
            ),
            "conteudo": sanitize_html(
                text_content, allow_basic_formatting=True,
            ),
            "tags": [],
            "created_by": user.get("id"),
            "created_by_name": user.get("name") or user.get("email"),
            "created_at": now,
            "updated_at": now,
        }

        await db.minutas.insert_one(minuta_doc)

        logger.info(f"Minuta importada: {titulo} por {user.get('email')}")

        return {
            "success": True,
            "message": "Minuta importada com sucesso",
            "minuta": {
                "id": minuta_doc["id"],
                "titulo": minuta_doc["titulo"],
                "categoria": minuta_doc["categoria"],
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao importar minuta: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao importar: {str(e)}"
        )
