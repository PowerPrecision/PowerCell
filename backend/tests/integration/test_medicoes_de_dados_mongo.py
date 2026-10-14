"""D-13 passo 1 e D-15 — as medições contra um MongoDB REAL.

O que um duplo não prova: que `{campo: {$lt: <datetime>}}` só casa datetimes e `{campo: {$lt: <texto>}}`
só casa texto (por isso a condição de idade junta os dois), que `$nor`/`$type` apanha o «sem data», e que
o `collStats` devolve o que o módulo puro lê.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
AGORA = datetime.now(timezone.utc)


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_medicoes_{uuid.uuid4().hex[:8]}"]
    with patch("database.db", base):
        yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _dias(n):
    return AGORA - timedelta(days=n)


async def _linha(bd, nome, medir):
    return {l.nome: l for l in await medir([nome])}[nome]


async def test_idade_conta_datetimes_e_texto_iso_juntos(bd):
    mod = _carregar("medir_colecoes")
    await bd.history.insert_many([
        {"id": "dt-velho", "timestamp": _dias(400)},               # datetime
        {"id": "txt-velho", "timestamp": _dias(400).isoformat()},   # texto ISO
        {"id": "dt-novo", "timestamp": _dias(5)},
        {"id": "txt-novo", "timestamp": _dias(5).isoformat()},
        {"id": "meio", "timestamp": _dias(100).isoformat()},
    ])
    with patch("database.db", bd):
        l = await _linha(bd, "history", mod.medir)
    assert l.documentos == 5
    assert l.campo_de_data == "timestamp"
    assert l.mais_antigos_que[365] == 2     # os DOIS tipos
    assert l.mais_antigos_que[90] == 3
    assert l.mais_antigos_que[30] == 3
    assert l.sem_data == 0


async def test_so_um_tipo_subestimaria(bd):
    """Contraprova: com a condição de UM só tipo, a contagem sai errada — é o que o `$or` evita."""
    await bd.history.insert_many([
        {"timestamp": _dias(400)}, {"timestamp": _dias(400).isoformat()},
    ])
    so_datetime = await bd.history.count_documents({"timestamp": {"$lt": _dias(365)}})
    assert so_datetime == 1


async def test_sem_data_conta_ausentes_nulos_e_tipos_estranhos(bd):
    mod = _carregar("medir_colecoes")
    await bd.history.insert_many([
        {"id": 1, "timestamp": _dias(2)}, {"id": 2, "timestamp": _dias(2)},
        {"id": 3, "timestamp": None}, {"id": 4, "timestamp": 12345}, {"id": 5},
    ])
    with patch("database.db", bd):
        l = await _linha(bd, "history", mod.medir)
    assert l.documentos == 5
    assert l.sem_data == 3


async def test_escolhe_o_primeiro_campo_que_tem_valores(bd):
    mod = _carregar("medir_colecoes")
    # `timestamp_dt` (preferido) não existe nestes documentos; `timestamp` sim.
    await bd.system_error_logs.insert_many([{"timestamp": _dias(40).isoformat()} for _ in range(3)])
    with patch("database.db", bd):
        l = await _linha(bd, "system_error_logs", mod.medir)
    assert l.campo_de_data == "timestamp"
    assert l.mais_antigos_que[30] == 3


async def test_colecao_inexistente_nao_e_zero_bytes(bd):
    mod = _carregar("medir_colecoes")
    with patch("database.db", bd):
        l = await _linha(bd, "chat_messages", mod.medir)
    assert l.existe is False


async def test_collstats_traz_tamanhos(bd):
    mod = _carregar("medir_colecoes")
    await bd.emails.insert_many([{"created_at": _dias(1).isoformat(), "body": "x" * 500} for _ in range(20)])
    with patch("database.db", bd):
        l = await _linha(bd, "emails", mod.medir)
    assert l.documentos == 20
    assert l.bytes_dados > 20 * 500
    assert l.bytes_indices > 0


async def test_d15_conta_claro_cifrado_e_outro(bd):
    mod = _carregar("medir_datas_de_nascimento")
    from services.encryption import EncryptionService
    cifrado = EncryptionService.ENCRYPTION_PREFIX + "abc"
    await bd.clients.insert_many([
        {"id": "c1", "dados_pessoais": {"data_nascimento": "1990-02-03"}},
        {"id": "c2", "dados_pessoais": {"birth_date": cifrado}},
        {"id": "c3", "dados_pessoais": {"data_nascimento": "03/02/1990"}},
        {"id": "c4"},
    ])
    await bd.processes.insert_many([
        {"id": "p1", "personal_data": {"birth_date": "1985-01-01"},
         "co_buyers": [{"data_nascimento": "1980-06-06"}]},
    ])
    with patch("database.db", bd):
        relatorio = await mod.medir()
    from services.birthdate_exposure_audit import resumir
    r = resumir(relatorio)
    assert r["documentos"] == {"processes": 1, "clients": 4}
    assert r["total_em_claro"] == 3
    assert r["total_outro"] == 1
    assert r["por_colecao"]["clients"]["dados_pessoais.birth_date"]["cifrado"] == 1
