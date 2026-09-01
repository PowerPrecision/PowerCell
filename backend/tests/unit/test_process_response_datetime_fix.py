"""
Testes de regressão — ResponseValidationError em ProcessResponse.updated_at.

Bug original: GET /api/processes/{id} devolvia 500 quando `updated_at`
(ou `created_at`) estava gravado no Mongo como um BSON Date nativo (ex.
via `soft_delete_process`, que fazia `{"updated_at": datetime.now(timezone.utc)}`
sem `.isoformat()`), porque o campo estava tipado como `Optional[str]` e o
Pydantic v2 não converte automaticamente um `datetime` para `str`.

Fix: campos tipados como `Optional[datetime]` + `@field_serializer` que
aceita ambos (datetime OU string ISO já persistida) e serializa sempre
para ISO string na resposta da API.
"""
from datetime import datetime, timezone

from models.process import ProcessResponse


class TestProcessResponseDatetimeFix:
    def test_accepts_raw_datetime_object(self):
        """Reprodução exacta do bug: valor vindo do Mongo como datetime nativo."""
        raw_dt = datetime.now(timezone.utc)
        resp = ProcessResponse(id="p1", updated_at=raw_dt, created_at=raw_dt)
        dumped = resp.model_dump()
        assert isinstance(dumped["updated_at"], str)
        assert isinstance(dumped["created_at"], str)
        assert dumped["updated_at"] == raw_dt.isoformat()

    def test_accepts_iso_string(self):
        """Caso normal: valor já persistido como ISO string."""
        iso = "2026-01-01T10:00:00+00:00"
        resp = ProcessResponse(id="p1", updated_at=iso, created_at=iso)
        dumped = resp.model_dump()
        assert dumped["updated_at"] == iso
        assert dumped["created_at"] == iso

    def test_accepts_none(self):
        resp = ProcessResponse(id="p1")
        dumped = resp.model_dump()
        assert dumped["updated_at"] is None
        assert dumped["created_at"] is None
