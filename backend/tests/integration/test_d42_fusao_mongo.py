"""D-42/D-40 contra um MongoDB REAL: fundir clientes duplicados e só então construir os índices únicos.

Ponta a ponta, pelo SCRIPT carregado do ficheiro e pelo cifrador de produção. O que se prova:

* a fusão reaponta os processos (`client_id`, `second_client_id`, `client_ids` sem repetidos e
  com a ordem), outras colecções (documentos, rascunhos) e acrescenta a rede ao sobrevivente;
* o absorvido fica ELIMINADO (não apagado) e sem hashes: a seguir os índices únicos constroem-se;
* idempotente: uma segunda passagem não encontra nada;
* os ambíguos nunca se fundem (código de saída 1) e continuam a impedir o índice;
* a simulação (omissão) não escreve nada;
* uma colecção que o inventário não conhecia e que aponta para o absorvido é descoberta e reapontada.
"""
from __future__ import annotations

import copy
import importlib.util
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "resolve_client_duplicates.py"


def _script():
    spec = importlib.util.spec_from_file_location("resolve_d42", SCRIPT)
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
    base = cliente[f"test_fusao_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _cliente(id_, *, rede=None, empresa=None, nif="", email=None, telefone="", morada=None, **extra):
    from services.encryption import encrypt_client_data

    doc = {
        "id": id_, "nome": f"Nome {id_}",
        "contacto": {"email": email or f"{id_}@unico.pt", "telefone": telefone},
        "dados_pessoais": {"nif": nif, **({"morada_fiscal": morada} if morada else {})},
        "process_ids": extra.pop("process_ids", []),
        "created_at": extra.pop("created_at", "2026-01-01"),
        **extra,
    }
    if rede:
        doc["network_id"] = rede
    if empresa:
        doc["company_id"] = empresa
    return encrypt_client_data(doc)


async def _semear_o_caso_do_d42(bd):
    """A mesma pessoa na Power (2 processos) e na Domus (1 processo + 2.º titular), mais um email partilhado."""
    await bd.clients.insert_many([
        _cliente("pw", rede=REDE_INCUMBENTE, empresa="cmp-power", nif="285739461", email="ana@x.pt",
                 telefone="912345678", process_ids=["p1", "p2"], registration_completed=True,
                 s3_folder="Documentação Clientes/pw"),
        _cliente("dm", rede=REDE_DOMUS, empresa="cmp-domus", nif="285739461", email="ana@domus.pt",
                 telefone="912345678", process_ids=["p3"], s3_folder="Documentação Clientes/dm",
                 partner_leads=[{"lead_id": "l1"}], morada="Rua da Domus, 1"),
        _cliente("unico", rede=REDE_INCUMBENTE, nif="500000000", email="u@x.pt"),
    ])
    await bd.processes.insert_many([
        {"id": "p1", "client_id": "pw", "network_id": REDE_INCUMBENTE},
        {"id": "p2", "client_id": "pw", "second_client_id": "dm", "client_ids": ["pw", "dm"], "network_id": REDE_INCUMBENTE},
        {"id": "p3", "client_id": "dm", "network_id": REDE_DOMUS, "client_ids": ["dm"]},
        {"id": "p9", "client_id": "unico", "network_id": REDE_INCUMBENTE},
    ])
    await bd.documents.insert_many([
        {"id": "d1", "client_id": "dm", "process_id": "p3"},
        {"id": "d2", "client_id": "pw"},
    ])
    await bd.partner_drafts.insert_one({"id": "l1", "matched_client_id": "dm"})
    # uma colecção que NENHUM inventário escrito à mão conhecia
    await bd.coisas_do_futuro.insert_one({"id": "f1", "client_id": "dm"})


async def _correr(bd, *argv):
    script = _script()
    with patch("database.db", bd), patch("sys.argv", ["resolve_client_duplicates.py", *argv]):
        return script, await script.principal()


async def _foto(bd):
    return {
        c: sorted([repr(sorted(d.items(), key=str)) async for d in bd[c].find({})])
        for c in await bd.list_collection_names()
    }


@pytest.mark.asyncio
async def test_a_simulacao_nao_escreve_nada(bd, capsys):
    await _semear_o_caso_do_d42(bd)
    antes = await _foto(bd)
    _, codigo = await _correr(bd)
    assert codigo == 0
    assert await _foto(bd) == antes
    saida = capsys.readouterr().out
    assert "SIMULAÇÃO" in saida and "[FUNDIR]" in saida
    assert "285739461" not in saida and "ana@x.pt" not in saida, "por omissão nada de dados pessoais"


@pytest.mark.asyncio
async def test_aplicar_funde_reaponta_e_deixa_o_rasto(bd):
    await _semear_o_caso_do_d42(bd)
    _, codigo = await _correr(bd, "--aplicar")
    assert codigo == 0

    pw = await bd.clients.find_one({"id": "pw"}, {"_id": 0})
    dm = await bd.clients.find_one({"id": "dm"}, {"_id": 0})

    # o sobrevivente (mais processos) ganha as redes, os processos e o que lhe faltava
    assert pw["redes_associadas"] == [REDE_DOMUS]
    assert sorted(pw["process_ids"]) == ["p1", "p2", "p3"]
    assert pw["dados_pessoais"]["morada_fiscal"] == dm["dados_pessoais"]["morada_fiscal"], "copiada tal como estava (cifrada)"
    from services.encryption import decrypt_client_data as _dec

    assert _dec(copy.deepcopy(pw))["dados_pessoais"]["morada_fiscal"] == "Rua da Domus, 1"
    assert pw["partner_leads"] == [{"lead_id": "l1"}]
    assert [f["id"] for f in pw["fundido_de"]] == ["dm"]
    assert pw["fundido_de"][0]["s3_folder"] == "Documentação Clientes/dm", "a pasta fica registada, nada se moveu"
    assert pw["s3_folder"] == "Documentação Clientes/pw"
    # a identidade do sobrevivente não mudou
    from services.encryption import decrypt_client_data

    assert decrypt_client_data(copy.deepcopy(pw))["contacto"]["email"] == "ana@x.pt"

    # o absorvido está eliminado, não apagado, e sem hashes de identidade
    assert dm["is_deleted"] is True and dm["status"] == "eliminado" and dm["merged_into"] == "pw"
    assert "nif_hash" not in dm["dados_pessoais"] and "email_hash" not in dm["contacto"]
    assert dm["merged_identity"]["nif_hash"]

    # os processos: todos apontam para o sobrevivente, sem repetidos e com a ordem
    p2 = await bd.processes.find_one({"id": "p2"})
    assert (p2["client_id"], p2["second_client_id"], p2["client_ids"]) == ("pw", "pw", ["pw"])
    assert (await bd.processes.find_one({"id": "p3"}))["client_id"] == "pw"
    assert (await bd.processes.find_one({"id": "p3"}))["client_ids"] == ["pw"]
    # e a segregação não se perdeu: cada processo continua carimbado com a SUA rede
    assert (await bd.processes.find_one({"id": "p3"}))["network_id"] == REDE_DOMUS

    # outras colecções, incluindo uma que ninguém inventariou
    assert (await bd.documents.find_one({"id": "d1"}))["client_id"] == "pw"
    assert (await bd.partner_drafts.find_one({"id": "l1"}))["matched_client_id"] == "pw"
    assert (await bd.coisas_do_futuro.find_one({"id": "f1"}))["client_id"] == "pw"

    # quem não era duplicado não foi tocado
    assert "fundido_de" not in await bd.clients.find_one({"id": "unico"}, {"_id": 0})


@pytest.mark.asyncio
async def test_e_idempotente(bd):
    await _semear_o_caso_do_d42(bd)
    await _correr(bd, "--aplicar")
    depois_da_primeira = await _foto(bd)
    _, codigo = await _correr(bd, "--aplicar")
    assert codigo == 0
    assert await _foto(bd) == depois_da_primeira


@pytest.mark.asyncio
async def test_retoma_uma_fusao_interrompida(bd):
    """Os processos já reapontados mas o absorvido ainda activo: a segunda passagem acaba o trabalho."""
    await _semear_o_caso_do_d42(bd)
    await bd.processes.update_many({"client_id": "dm"}, {"$set": {"client_id": "pw"}})
    _, codigo = await _correr(bd, "--aplicar")
    assert codigo == 0
    dm = await bd.clients.find_one({"id": "dm"})
    assert dm["is_deleted"] is True
    pw = await bd.clients.find_one({"id": "pw"})
    assert pw["redes_associadas"] == [REDE_DOMUS] and [f["id"] for f in pw["fundido_de"]] == ["dm"]


@pytest.mark.asyncio
async def test_os_indices_unicos_so_se_constroem_depois_da_limpeza(bd):
    await _semear_o_caso_do_d42(bd)
    script, codigo = await _correr(bd, "--criar-indices")
    assert codigo == 1, "numa simulação com grupos por resolver recusa-se a criar índices"
    assert "idx_client_nif_hash_unico" not in await bd.clients.index_information()

    with patch("database.db", bd):
        criados = await script._criar_indices_unicos()
    assert not any("nif_hash_unico" in c for c in criados), "com NIFs duplicados a construção falha (e diz-se)"

    _, codigo = await _correr(bd, "--aplicar", "--criar-indices")
    assert codigo == 0
    nomes = set(await bd.clients.index_information())
    assert {"idx_client_nif_hash_unico", "idx_client_email_hash_unico"} <= nomes


@pytest.mark.asyncio
async def test_os_ambiguos_nunca_se_fundem_e_travam_os_indices(bd, capsys):
    """Dois NIFs diferentes ligados pelo mesmo email: duas pessoas. Decide-se à mão."""
    await bd.clients.insert_many([
        _cliente("c1", rede=REDE_INCUMBENTE, nif="285739461", email="casal@x.pt", process_ids=["p1"]),
        _cliente("c2", rede=REDE_INCUMBENTE, nif="500000000", email="casal@x.pt"),
    ])
    await bd.processes.insert_one({"id": "p1", "client_id": "c1"})
    antes = await _foto(bd)

    _, codigo = await _correr(bd, "--aplicar", "--criar-indices")

    assert codigo == 1
    assert await _foto(bd) == antes, "nada foi tocado"
    saida = capsys.readouterr().out
    assert "AMBÍGUO" in saida and "nifs_diferentes_ligados_por_email" in saida
    assert "idx_client_email_hash_unico" not in await bd.clients.index_information()


@pytest.mark.asyncio
async def test_um_fundivel_e_um_ambiguo_na_mesma_passagem(bd):
    """O inequívoco funde-se; o ambíguo fica. O código de saída avisa que há trabalho humano."""
    await _semear_o_caso_do_d42(bd)
    await bd.clients.insert_many([
        _cliente("c1", rede=REDE_INCUMBENTE, nif="111111111", email="casal@x.pt"),
        _cliente("c2", rede=REDE_INCUMBENTE, nif="222222222", email="casal@x.pt"),
    ])
    _, codigo = await _correr(bd, "--aplicar")
    assert codigo == 1
    assert (await bd.clients.find_one({"id": "dm"}))["is_deleted"] is True
    assert not (await bd.clients.find_one({"id": "c1"})).get("is_deleted")
    assert not (await bd.clients.find_one({"id": "c2"})).get("is_deleted")


@pytest.mark.asyncio
async def test_um_telemovel_partilhado_nao_funde_ninguem(bd):
    await bd.clients.insert_many([
        _cliente("t1", nif="111111111", email="t1@x.pt", telefone="912345678"),
        _cliente("t2", nif="222222222", email="t2@x.pt", telefone="912345678"),
    ])
    antes = await _foto(bd)
    _, codigo = await _correr(bd, "--aplicar")
    assert codigo == 0 and await _foto(bd) == antes


@pytest.mark.asyncio
async def test_a_associacao_dá_a_janela_ao_cliente_fundido(bd):
    """Depois da fusão a Domus abre a ficha pelo caminho normal (redes_associadas) e vê só o seu processo."""
    await _semear_o_caso_do_d42(bd)
    await _correr(bd, "--aplicar")
    from services.by_id_scope import cliente_associado_a_minha_rede
    from services.tenant_network import TenantScope

    pw = await bd.clients.find_one({"id": "pw"}, {"_id": 0})
    assert cliente_associado_a_minha_rede(pw, TenantScope(network_ids=(REDE_DOMUS,)))
    assert not cliente_associado_a_minha_rede(pw, TenantScope(network_ids=("rede:outra",)))
