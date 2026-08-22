"""Pacote FJ — TTL de rascunhos precisa de datetime nativo (updated_at_dt)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.email import EmailCreate, EmailDirection, EmailStatus, EmailUpdate
from services.email_draft_service import is_draft_status, stamp_draft_ttl_fields


def test_is_draft_status_accepts_enum_and_string():
    assert is_draft_status("draft") is True
    assert is_draft_status(EmailStatus.DRAFT) is True
    assert is_draft_status("sent") is False
    assert is_draft_status(EmailStatus.SENT) is False
    assert is_draft_status(None) is False


def test_stamp_draft_ttl_fields_uses_native_datetime():
    target = {}
    now = datetime.now(timezone.utc)
    stamp_draft_ttl_fields(target, now=now)
    assert target["updated_at_dt"] is now
    assert target["created_at_dt"] is now
    assert isinstance(target["updated_at_dt"], datetime)
    assert not isinstance(target["updated_at_dt"], str)


def test_stamp_draft_ttl_update_does_not_overwrite_created():
    created = datetime(2020, 1, 1, tzinfo=timezone.utc)
    target = {"created_at_dt": created}
    stamp_draft_ttl_fields(target, include_created=False)
    assert target["created_at_dt"] is created
    assert isinstance(target["updated_at_dt"], datetime)


@pytest.mark.asyncio
async def test_create_email_record_stamps_ttl_for_drafts(monkeypatch):
    from services import email_process_crud

    inserted = {}

    async def fake_insert(doc):
        inserted.update(doc)
        return MagicMock()

    monkeypatch.setattr(email_process_crud.db.emails, "insert_one", fake_insert)
    monkeypatch.setattr(
        email_process_crud, "enrich_email", AsyncMock(side_effect=lambda email: email)
    )

    data = EmailCreate(
        process_id="p1",
        direction=EmailDirection.SENT,
        from_email="a@x.pt",
        to_emails=["b@x.pt"],
        subject="Rascunho",
        body="Olá",
        status=EmailStatus.DRAFT,
    )
    await email_process_crud.run_create_email_record(data, {"id": "u1"})

    assert inserted["status"] == "draft"
    assert isinstance(inserted["updated_at_dt"], datetime)
    assert isinstance(inserted["created_at_dt"], datetime)
    assert inserted["updated_at_dt"].tzinfo is not None


@pytest.mark.asyncio
async def test_create_email_record_skips_ttl_for_sent(monkeypatch):
    from services import email_process_crud

    inserted = {}

    async def fake_insert(doc):
        inserted.update(doc)
        return MagicMock()

    monkeypatch.setattr(email_process_crud.db.emails, "insert_one", fake_insert)
    monkeypatch.setattr(
        email_process_crud, "enrich_email", AsyncMock(side_effect=lambda email: email)
    )

    data = EmailCreate(
        process_id="p1",
        direction=EmailDirection.SENT,
        from_email="a@x.pt",
        to_emails=["b@x.pt"],
        subject="Enviado",
        body="Olá",
        status=EmailStatus.SENT,
    )
    await email_process_crud.run_create_email_record(data, {"id": "u1"})

    assert inserted["status"] == "sent"
    assert "updated_at_dt" not in inserted


@pytest.mark.asyncio
async def test_update_email_stamps_ttl_when_still_draft(monkeypatch):
    from services import email_process_crud

    existing = {
        "id": "e1",
        "process_id": "p1",
        "direction": "sent",
        "from_email": "a@x.pt",
        "to_emails": ["b@x.pt"],
        "cc_emails": [],
        "bcc_emails": [],
        "subject": "Rascunho",
        "body": "Olá",
        "status": "draft",
        "created_at": "2026-01-01T00:00:00+00:00",
        "created_by": "u1",
    }
    captured_set = {}

    async def fake_find_one(query, *args, **kwargs):
        merged = {**existing, **captured_set}
        return merged

    async def fake_update_one(query, update):
        captured_set.update(update["$set"])
        return MagicMock()

    monkeypatch.setattr(email_process_crud.db.emails, "find_one", fake_find_one)
    monkeypatch.setattr(email_process_crud.db.emails, "update_one", fake_update_one)
    monkeypatch.setattr(
        email_process_crud, "enrich_email", AsyncMock(side_effect=lambda email: email)
    )

    await email_process_crud.run_update_email(
        "e1", EmailUpdate(subject="Novo assunto"), {"id": "u1"}
    )

    assert isinstance(captured_set["updated_at_dt"], datetime)
    assert captured_set["subject"] == "Novo assunto"
