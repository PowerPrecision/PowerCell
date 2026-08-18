"""Pacote DN.1+2 — filtro UCR do webmail e download de anexos."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services.email_webmail import build_ucr_mailbox_filter, _and_query
from services.email_mailbox_ops import (
    _content_disposition_attachment,
    _match_attachment,
    run_download_webmail_attachment,
)


def test_build_ucr_mailbox_filter_company_and_mailbox():
    filt = build_ucr_mailbox_filter("co-precision", "ana@precision.pt")
    assert "$or" in filt
    clauses = filt["$or"]
    assert {"company_id": "co-precision"} in clauses
    account_clause = next(c for c in clauses if "account" in c)
    assert "ana@precision\\.pt" in account_clause["account"]["$regex"]


def test_build_ucr_mailbox_filter_ignores_default_and_empty():
    assert build_ucr_mailbox_filter(None, None) is None
    assert build_ucr_mailbox_filter("", "") is None
    assert build_ucr_mailbox_filter("default", None) is None
    only_mail = build_ucr_mailbox_filter("default", "ana@power.pt")
    assert only_mail["account"]["$regex"].startswith("^ana@power\\.pt$")


def test_build_ucr_mailbox_filter_does_not_include_empty_company():
    filt = build_ucr_mailbox_filter("co-1", "a@b.pt")
    blob = str(filt)
    assert "$exists" not in blob
    assert "None" not in blob


def test_and_query_wraps_existing_or():
    base = {"$or": [{"created_by": "u1"}]}
    extra = {"company_id": "co-1"}
    merged = _and_query(base, extra)
    assert merged == {"$and": [base, extra]}
    assert _and_query(base, None) is base


def test_content_disposition_utf8_filename():
    header = _content_disposition_attachment("IRS 2024 Ana.pdf")
    assert header.startswith("attachment;")
    assert "filename*=" in header
    assert "UTF-8''" in header


def test_match_attachment_by_id_index_and_filename():
    atts = [
        {"id": "att-a", "filename": "irs.pdf", "size": 10},
        {"filename": "cc.jpg", "size": 20},
    ]
    found, idx = _match_attachment(atts, "att-a")
    assert found["filename"] == "irs.pdf" and idx == 0

    found, idx = _match_attachment(atts, "email-1:1")
    assert found["filename"] == "cc.jpg" and idx == 1

    found, idx = _match_attachment(atts, "cc.jpg")
    assert found["filename"] == "cc.jpg"

    found, idx = _match_attachment(atts, "missing")
    assert found is None and idx is None


@pytest.mark.asyncio
async def test_download_webmail_attachment_not_found():
    request = MagicMock()
    user = {"id": "u1", "role": "consultor", "email": "a@b.pt"}
    with patch("services.email_mailbox_ops.db") as mock_db:
        mock_db.emails.find_one = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await run_download_webmail_attachment("att-missing", user, request)
        assert exc.value.status_code == 404
        assert "não encontrado" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_download_webmail_attachment_streams_db_content():
    request = MagicMock()
    user = {"id": "u1", "role": "consultor", "email": "ana@x.pt"}
    email_doc = {
        "id": "em-1",
        "created_by": "u1",
        "synced_for_user": "u1",
        "attachments": [
            {
                "id": "att-1",
                "filename": "recibo.pdf",
                "content_type": "application/pdf",
                "content": "aGVsbG8=",  # "hello"
            }
        ],
    }
    with patch("services.email_mailbox_ops.db") as mock_db:
        mock_db.emails.find_one = AsyncMock(return_value=email_doc)
        with patch(
            "services.email_mailbox_ops._assert_email_readable",
            new=AsyncMock(return_value=None),
        ):
            resp = await run_download_webmail_attachment(
                "att-1", user, request, email_id="em-1"
            )
    assert resp.media_type == "application/pdf"
    assert "attachment" in resp.headers["Content-Disposition"]
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
    assert b"".join(chunks) == b"hello"
