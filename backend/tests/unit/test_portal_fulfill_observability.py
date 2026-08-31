"""Unit tests for observability warning log in `_auto_fulfill_portal_request`.

Validates that when the portal fulfill engine returns `reason=weak_match` or
`reason=no_match`, `_auto_fulfill_portal_request` emits a structured
`logger.warning` with the '[PORTAL-FULFILL] Falha de correspondência automática'
prefix (part of this iteration's observability improvement).

Conversely: for a successful match (reason=None / fulfilled=1) it must NOT
emit that warning — only the INFO REQUESTED→RECEIVED already emitted by
`fulfill_portal_requests_on_staff_upload` itself.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from services.document_upload import _auto_fulfill_portal_request


@pytest.mark.asyncio
async def test_warning_emitted_on_no_match(caplog):
    caplog.set_level(logging.WARNING, logger="services.document_upload")

    fake_result = {"fulfilled": 0, "document_ids": [], "reason": "no_match"}
    with patch(
        "services.document_portal_fulfill.fulfill_portal_requests_on_staff_upload",
        AsyncMock(return_value=fake_result),
    ):
        result = await _auto_fulfill_portal_request(
            "proc-nomatch",
            {
                "category": "Plantas_Casa",
                "filename": "planta_nao_solicitada.pdf",
                "s3_path": "s3://bucket/proc-nomatch/planta_nao_solicitada.pdf",
                "content_type": "application/pdf",
                "file_size": 1024,
            },
            user={"id": "user-1", "name": "Equipa"},
        )

    assert result == fake_result
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "[PORTAL-FULFILL] Falha de correspondência automática" in r.getMessage()
    ]
    assert len(warnings) == 1, f"Expected exactly 1 warning, got {[r.getMessage() for r in caplog.records]}"
    msg = warnings[0].getMessage()
    assert "reason=no_match" in msg
    assert "process_id=proc-nomatch" in msg
    assert "Plantas_Casa" in msg
    assert "planta_nao_solicitada.pdf" in msg
    assert "user=user-1" in msg


@pytest.mark.asyncio
async def test_warning_emitted_on_weak_match(caplog):
    caplog.set_level(logging.WARNING, logger="services.document_upload")

    fake_result = {"fulfilled": 0, "document_ids": [], "reason": "weak_match"}
    with patch(
        "services.document_portal_fulfill.fulfill_portal_requests_on_staff_upload",
        AsyncMock(return_value=fake_result),
    ):
        result = await _auto_fulfill_portal_request(
            "proc-weak",
            {
                "category": "Outros",
                "filename": "ficheiro_ambiguo.pdf",
            },
            user={"id": "user-42", "name": "Equipa"},
        )

    assert result == fake_result
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "[PORTAL-FULFILL] Falha de correspondência automática" in r.getMessage()
    ]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "reason=weak_match" in msg
    assert "process_id=proc-weak" in msg


@pytest.mark.asyncio
async def test_no_warning_on_successful_match(caplog):
    """
    Fluxo normal (match forte, `reason` ausente ou vazio): NÃO deve emitir
    o warning de falha de correspondência.
    """
    caplog.set_level(logging.WARNING, logger="services.document_upload")

    fake_result = {"fulfilled": 1, "document_ids": ["doc-req-1"]}
    with patch(
        "services.document_portal_fulfill.fulfill_portal_requests_on_staff_upload",
        AsyncMock(return_value=fake_result),
    ):
        result = await _auto_fulfill_portal_request(
            "proc-ok",
            {
                "category": "IRS",
                "filename": "irs_2024.pdf",
            },
            user={"id": "user-1", "name": "Equipa"},
        )

    assert result == fake_result
    warnings = [
        r for r in caplog.records
        if "[PORTAL-FULFILL] Falha de correspondência automática" in r.getMessage()
    ]
    assert warnings == [], f"Unexpected warning emitted: {[r.getMessage() for r in warnings]}"


@pytest.mark.asyncio
async def test_no_warning_on_index_skip(caplog):
    """`reason=index_skip` (pasta Index) não é uma falha de correspondência."""
    caplog.set_level(logging.WARNING, logger="services.document_upload")

    fake_result = {"fulfilled": 0, "document_ids": [], "reason": "index_skip"}
    with patch(
        "services.document_portal_fulfill.fulfill_portal_requests_on_staff_upload",
        AsyncMock(return_value=fake_result),
    ):
        await _auto_fulfill_portal_request(
            "proc-index",
            {"category": "Index", "filename": "anything.pdf"},
            user={"id": "user-1", "name": "Equipa"},
        )

    warnings = [
        r for r in caplog.records
        if "[PORTAL-FULFILL] Falha de correspondência automática" in r.getMessage()
    ]
    assert warnings == []
