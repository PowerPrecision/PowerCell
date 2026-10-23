"""O diagnóstico de duplicados (D-38 → D-42, identidade global) contra um MongoDB REAL.

O oráculo é a GUARDA DE PRODUÇÃO: tudo o que o relatório diz ser duplicado, o
`encontrar_cliente_duplicado` tem de achar também — e o que o relatório diz ser
único, a guarda tem de deixar passar. Duas regras escritas à parte divergem; esta
é a prova de que não divergem. Usa o cifrador REAL (`encrypt_client_data`), o
projector do script e o script carregado do ficheiro.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, tenant_db

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_client_duplicates.py"


def _script():
    spec = importlib.util.spec_from_file_location("diag_d38", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    base = cliente[f"test_diag_dup_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _cliente(id_, *, rede=None, empresa=None, nif="", email=None, telefone="", **extra):
    from services.encryption import encrypt_client_data

    doc = {
        "id": id_, "nome": f"Nome {id_}",
        "contacto": {"email": email or f"{id_}@unico.pt", "telefone": telefone},
        "dados_pessoais": {"nif": nif},
        **extra,
    }
    if rede:
        doc["network_id"] = rede
    if empresa:
        doc["company_id"] = empresa
    return encrypt_client_data(doc)


async def _semear(bd):
    await bd.clients.insert_many([
        # Power: a MESMA pessoa duas vezes, com o telemóvel escrito de outra forma.
        _cliente("a", rede=REDE_INCUMBENTE, empresa="cmp-power", nif="200000004",
                 email="ana@x.pt", telefone="912345678"),
        _cliente("b", rede=REDE_INCUMBENTE, empresa="cmp-precision", nif="200000004",
                 email="ANA@x.pt", telefone="+351 912 345 678"),
        # Pilha por carimbar (rede de omissão) a partilhar o telemóvel com o "a".
        _cliente("leg", telefone="00351912345678"),
        # Único.
        _cliente("c", rede=REDE_INCUMBENTE, nif="500000000", telefone="966666666"),
        # Mesmo NIF que o "a", mas na Domus: com a identidade global (D-42) é UM grupo que atravessa redes.
        _cliente("f", rede=REDE_DOMUS, empresa="cmp-domus", nif="200000004"),
        # Só com a empresa gravada (sem rede): é da rede dela. Partilha o email com "g".
        _cliente("g", empresa="cmp-domus", email="comum@domus.pt"),
        _cliente("h", rede=REDE_DOMUS, email="comum@domus.pt"),
        # Eliminado: não bloqueia, logo não conta.
        _cliente("gone", rede=REDE_INCUMBENTE, nif="500000000", is_deleted=True),
        _cliente("gone2", rede=REDE_INCUMBENTE, telefone="966666666", status="eliminado"),
        # Telemóvel curto: não identifica ninguém.
        _cliente("s1", rede=REDE_INCUMBENTE, telefone="12345"),
        _cliente("s2", rede=REDE_INCUMBENTE, telefone="12345"),
    ])
    await bd.processes.insert_many([
        {"id": "p1", "client_id": "a"}, {"id": "p2", "client_id": "a"},
        {"id": "p3", "client_id": "b", "is_deleted": True},
    ])


@pytest.mark.asyncio
async def test_o_relatorio_bate_certo_com_um_mongo_real(bd):
    await _semear(bd)
    script = _script()
    with patch("database.db", bd):
        registos = await script._carregar_registos()
        rel = script.auditar(registos)
        processos = await script._processos_por_cliente(["a", "b"])

    assert sorted(r.id for r in registos) == ["a", "b", "c", "f", "g", "h", "leg", "s1", "s2"], (
        "os eliminados não entram"
    )
    grupos = {(g.campo, g.redes): g.membros for g in rel.grupos}
    assert grupos[("nif", (REDE_DOMUS, REDE_INCUMBENTE))] == ("a", "b", "f"), (
        "o mesmo NIF na Domus É um duplicado (identidade global) e o grupo diz as duas redes"
    )
    assert grupos[("email", (REDE_INCUMBENTE,))] == ("a", "b")
    assert grupos[("email", (REDE_DOMUS,))] == ("g", "h"), "a empresa sem rede gravada pertence à rede da empresa"
    assert not any(c == "telefone" for c, _ in grupos), "o telemóvel já não identifica ninguém"
    assert "leg" not in {m for membros in grupos.values() for m in membros}
    assert rel.casos == [("a", "b", "f"), ("g", "h")]
    assert rel.grupos_entre_redes == {"nif": 1}
    assert processos == {"a": 2}, "os processos eliminados não contam"


@pytest.mark.asyncio
async def test_a_guarda_de_producao_concorda_com_o_relatorio(bd):
    """Tudo o que o relatório diz repetido, a guarda recusa; o resto, deixa passar."""
    await _semear(bd)
    script = _script()
    import services.client_uniqueness as cu

    with patch("database.db", bd), tenant_db(bd, cu):
        registos = await script._carregar_registos()
        rel = script.auditar(registos)
        em_conflito = {c for g in rel.grupos for c in g.membros}
        valores = {r.id: r for r in registos}

        for r in registos:
            doc = await bd.clients.find_one({"id": r.id})
            from services.encryption import decrypt_client_data

            claro = decrypt_client_data(doc)
            achado = await cu.encontrar_cliente_duplicado(
                (claro["dados_pessoais"] or {}).get("nif") or None,
                (claro["contacto"] or {}).get("email"),
                excluir_id=r.id,
            )
            assert bool(achado) == (r.id in em_conflito), (
                f"{r.id} ({valores[r.id].rede}): relatório e guarda discordam"
            )


@pytest.mark.asyncio
async def test_base_sem_duplicados_diz_que_o_indice_e_viavel(bd):
    await bd.clients.insert_many([
        _cliente("x", rede=REDE_INCUMBENTE, nif="200000004", telefone="911111111"),
        _cliente("y", rede=REDE_INCUMBENTE, nif="500000000", telefone="922222222"),
    ])
    script = _script()
    with patch("database.db", bd):
        rel = script.auditar(await script._carregar_registos())
    assert script.resumir(rel)["indice_unico_viavel"] is True


@pytest.mark.asyncio
async def test_o_script_nao_escreve_nada(bd):
    """Antes e depois: a base de dados fica byte a byte igual."""
    await _semear(bd)
    script = _script()

    async def foto():
        return {
            c: sorted([repr(sorted(d.items(), key=str)) async for d in bd[c].find({})])
            for c in ("clients", "companies", "processes")
        }

    antes = await foto()
    with patch("database.db", bd):
        registos = await script._carregar_registos()
        await script._processos_por_cliente(["a", "b"])
        script.auditar(registos)
    assert await foto() == antes
    assert sorted(await bd.list_collection_names()) == sorted({"clients", "companies", "processes"})


@pytest.mark.asyncio
async def test_a_execucao_completa_imprime_e_sai_com_zero(bd, capsys, monkeypatch):
    await _semear(bd)
    script = _script()
    monkeypatch.setattr("sys.argv", ["diagnose_client_duplicates.py", "--csv", os.devnull])
    with patch("database.db", bd):
        codigo = await script.principal()
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "CASOS A DECIDIR À MÃO: 2" in saida
    assert "GRUPOS QUE ATRAVESSAM REDES" in saida
    assert "200000004" not in saida and "ana@x.pt" not in saida, "por omissão nada de dados pessoais"
    assert "*****0004" in saida
    assert "NÃO se constroem" in saida
