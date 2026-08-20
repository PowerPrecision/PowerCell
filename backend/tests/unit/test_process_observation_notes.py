"""PACOTE DU — feed de notas de observação."""
from services.process_observation_notes import (
    append_observation_note,
    build_observation_note,
    coalesce_observation_notes,
)


def test_build_observation_note_shape():
    note = build_observation_note("  Olá  ", {"id": "u1", "name": "Ana"})
    assert note["text"] == "Olá"
    assert note["user_id"] == "u1"
    assert note["user_name"] == "Ana"
    assert note["id"]
    assert note["created_at"]


def test_coalesce_uses_array_when_present():
    notes = coalesce_observation_notes({
        "observation_notes": [{"id": "n1", "text": "nova"}],
        "observations": "legado",
    })
    assert notes == [{"id": "n1", "text": "nova"}]


def test_coalesce_falls_back_to_legacy_string():
    notes = coalesce_observation_notes({"observations": "nota antiga", "created_at": "t0"})
    assert len(notes) == 1
    assert notes[0]["text"] == "nota antiga"
    assert notes[0]["id"] == "legacy"


def test_append_preserves_legacy_then_adds():
    process = {"observations": "antiga", "created_at": "t0"}
    note = {"id": "n2", "text": "nova"}
    out = append_observation_note(process, note)
    assert [n["text"] for n in out] == ["antiga", "nova"]


def test_append_to_existing_array():
    process = {"observation_notes": [{"id": "n1", "text": "a"}]}
    out = append_observation_note(process, {"id": "n2", "text": "b"})
    assert [n["id"] for n in out] == ["n1", "n2"]
