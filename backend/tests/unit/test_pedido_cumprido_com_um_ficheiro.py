"""
A quantidade de um pedido do Portal é uma RECOMENDAÇÃO (decisão da direcção, Out 2026).

«Últimos 3 recibos» cumpre-se com 1 ficheiro — o processo avança — e o ecrã convida a
juntar mais. Inverte a regra rígida de Set 2026. Os ficheiros seguintes juntam-se ao
mesmo pedido sem o reabrir, e apagar no CRM só o reabre quando ficam ZERO ficheiros.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from services import document_portal_counts as contagens
from services.document_portal_counts import apply_portal_request_upload
from services.document_portal_revoke import rebuild_after_removal
from tests.unit.helpers_fonte import codigo_sem_comentarios


@pytest.fixture
def pedido_de_tres(fake_async_db):
    fake_async_db.documents.docs.append(
        {"id": "req", "process_id": "p", "status": "REQUESTED", "expected_count": 3, "attached_files": []}
    )
    return fake_async_db


@pytest.mark.asyncio
async def test_o_primeiro_ficheiro_cumpre_o_pedido(pedido_de_tres):
    with patch.object(contagens, "db", pedido_de_tres):
        r = await apply_portal_request_upload(
            {"id": "req", "process_id": "p"},
            set_fields={"filename": "a.pdf"},
            file_entry={"file_id": "1", "filename": "a.pdf"},
            now="2026-10-21T10:00:00",
        )
    assert r["completed"] is True and r["status"] == "RECEIVED"
    assert r["expected_count"] == 3  # a recomendação segue para o ecrã


@pytest.mark.asyncio
async def test_a_recomendacao_nao_se_perde_nem_decide(pedido_de_tres):
    with patch.object(contagens, "db", pedido_de_tres):
        await apply_portal_request_upload(
            {"id": "req", "process_id": "p"}, set_fields={}, file_entry={"file_id": "1"}, now="t",
        )
    doc = await pedido_de_tres.documents.find_one({"id": "req"})
    assert doc["expected_count"] == 3 and doc["status"] == "RECEIVED"


def test_apagar_um_de_tres_nao_reabre_mas_apagar_o_ultimo_sim():
    base = {"status": "RECEIVED", "expected_count": 3}
    tres = [{"s3_path": "a"}, {"s3_path": "b"}, {"s3_path": "c"}]
    assert rebuild_after_removal({**base, "attached_files": tres}, removidos=["a"])["status"] == "RECEIVED"
    assert rebuild_after_removal({**base, "attached_files": tres[:1]}, removidos=["a"])["status"] == "REQUESTED"


def _fonte(caminho: str) -> str:
    return codigo_sem_comentarios(Path(__file__).resolve().parents[2].joinpath(caminho).read_text(encoding="utf-8"))


def test_a_regra_vive_numa_constante_que_o_upload_e_a_revogacao_partilham():
    assert contagens.FICHEIROS_PARA_CUMPRIR == 1
    for modulo in ("services/document_portal_counts.py", "services/document_portal_revoke.py"):
        assert "FICHEIROS_PARA_CUMPRIR" in _fonte(modulo)
    # O pedido nunca volta a decidir pela quantidade recomendada.
    assert "uploaded >= expected" not in _fonte("services/document_portal_counts.py")
