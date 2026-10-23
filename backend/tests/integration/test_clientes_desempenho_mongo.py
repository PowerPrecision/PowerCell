"""«Clientes Registados» não pode custar uma ida à base de dados POR CLIENTE (Out 2026) — MongoDB real.

O defeito: para quem não é Master, `so_o_que_a_janela_deixa_ver` resolvia o âmbito (duas consultas) por cada
cliente da lista antes de paginar. Com 15 mil clientes eram 30 mil pedidos: 31 segundos num servidor local, e a
página «a bloquear» em produção. O que se afirma aqui é a PROPRIEDADE (o nº de comandos não cresce com a carteira),
medida com um `CommandListener` do driver — um duplo não contaria os pedidos que o código faz de facto.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import monitoring

from services import client_list_search as cls
from services import workflow_phases as fases
from services.encryption import encryption_service as enc

pytestmark = pytest.mark.asyncio

DIRETOR = {"id": "u-dir", "role": "diretor", "email": "d@x.pt", "name": "Dir", "company": "Power"}


class Contador(monitoring.CommandListener):
    def __init__(self):
        self.comandos: list[dict] = []

    def started(self, event):
        if event.command_name in ("find", "aggregate", "count", "distinct", "getMore"):
            self.comandos.append({"nome": event.command_name, "colecao": event.command.get(event.command_name),
                                  "comando": dict(event.command)})

    def succeeded(self, event): ...
    def failed(self, event): ...

    def limpar(self):
        self.comandos.clear()

    @property
    def pedidos(self) -> int:
        """Pedidos «novos» à base de dados (`find`, `aggregate`…), sem os `getMore` que só continuam um cursor."""
        return len([c for c in self.comandos if c["nome"] != "getMore"])

    def de(self, colecao):
        return [c for c in self.comandos if c["colecao"] == colecao and c["nome"] == "find"]


@pytest_asyncio.fixture
async def ambiente(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    contador = Contador()
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000, event_listeners=[contador])
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_clientes_perf_{uuid.uuid4().hex[:8]}"]
    import database

    for nome, modulo in list(sys.modules.items()):
        if nome.startswith("services.") and getattr(modulo, "db", None) is database.db:
            monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
    fases.invalidar_cache_de_fases()
    await base.workflow_statuses.insert_many([
        {"name": "novo", "label": "Novo", "order": 0, "is_active": True},
        {"name": "concluido", "label": "Concluído", "order": 1, "is_active": False},
    ])
    await base.companies.insert_one({"id": "c1", "name": "Power", "network_id": "rede-A", "is_active": True})
    await base.users.insert_one({"id": "u-dir", "name": "Dir", "email": "d@x.pt", "role": "diretor", "is_active": True, "company": "Power"})
    await base.user_company_roles.insert_one({"user_id": "u-dir", "company_id": "c1", "company_name": "Power", "role": "diretor", "is_active": True})
    fases.invalidar_cache_de_fases()
    yield base, contador
    fases.invalidar_cache_de_fases()
    await cliente.drop_database(base.name)
    cliente.close()


async def _semear(base, n_clientes, processos_por_cliente=2):
    clientes, processos = [], []
    for i in range(n_clientes):
        cid = f"c-{i:05d}"
        nif = str(500000000 + i)
        clientes.append({"id": cid, "nome": f"Cliente {i:05d}", "contacto": {"email": enc.encrypt(f"c{i}@x.pt")},
                         "dados_pessoais": {"nif": enc.encrypt(nif)}, "process_ids": [], "network_id": "rede-A",
                         "fonte": "web", "created_at": "2026-01-01"})
        for k in range(processos_por_cliente):
            pid = f"p-{i:05d}-{k}"
            clientes[-1]["process_ids"].append(pid)
            processos.append({
                "id": pid, "client_id": cid, "client_name": f"Cliente {i:05d}", "process_number": i * 10 + k,
                "client_email": enc.encrypt(f"c{i}@x.pt"), "status": "novo" if k == 0 else "concluido",
                "network_id": "rede-A", "is_deleted": False, "created_at": "2026-01-02", "updated_at": "2026-02-01",
                "personal_data": {"nif": enc.encrypt(nif), "nome": f"Cliente {i:05d}", "birth_year": 1990,
                                  "morada_fiscal": enc.encrypt("Rua X"), "k": k},
            })
    await base.clients.insert_many(clientes)
    await base.processes.insert_many(processos)


async def _lista(**kw):
    return await cls.run_list_clients(DIRETOR, page=1, size=50, **kw)


class TestONumeroDePedidosNaoCrescePorCliente:
    async def test_com_dez_vezes_mais_clientes_o_numero_de_comandos_e_o_mesmo(self, ambiente):
        base, contador = ambiente
        await _semear(base, 40)
        await _lista()          # aquece caches (workflow, âmbito)
        contador.limpar()
        await _lista()
        pequena = contador.pedidos

        await _semear_mais(base, 40, 440)
        contador.limpar()
        r = await _lista()
        grande = contador.pedidos

        assert r["total"] > 0
        assert grande == pequena, f"{pequena} pedidos com 40 clientes, {grande} com 440: cresce com a carteira"
        assert grande <= 12, f"{grande} pedidos para listar uma página"

    async def test_so_um_pedido_aos_processos_e_um_aos_clientes_da_janela(self, ambiente):
        base, contador = ambiente
        await _semear(base, 60)
        await _lista()
        contador.limpar()
        await _lista()
        # processos: a lista toda + a leitura dos dados pessoais da PÁGINA (um só `find` com `$in`)
        assert len(contador.de("processes")) <= 4
        assert len(contador.de("clients")) <= 4


async def _semear_mais(base, ja, ate):
    # acrescenta clientes de `ja` a `ate`
    for i in range(ja, ate):
        await _semear_um(base, i)


async def _semear_um(base, i):
    """Metade dos clientes acrescentados são «visitados»: da rede B, com o processo (movido) na rede A.

    São os que a janela tem de classificar um a um — sem eles o teste não distinguia resolver o âmbito UMA vez
    de o resolver por cliente (a consulta dos clientes de fora vinha vazia).
    """
    cid = f"c-{i:05d}"
    nif = str(500000000 + i)
    rede_do_cliente = "rede-B" if i % 2 else "rede-A"
    await base.clients.insert_one({"id": cid, "nome": f"Cliente {i:05d}", "contacto": {"email": enc.encrypt(f"c{i}@x.pt")},
                                   "dados_pessoais": {"nif": enc.encrypt(nif)}, "process_ids": [f"p-{i:05d}-0"],
                                   "network_id": rede_do_cliente, "fonte": "web", "created_at": "2026-01-01"})
    await base.processes.insert_one({
        "id": f"p-{i:05d}-0", "client_id": cid, "client_name": f"Cliente {i:05d}", "process_number": i * 10,
        "client_email": enc.encrypt(f"c{i}@x.pt"), "status": "novo", "network_id": "rede-A", "is_deleted": False,
        "created_at": "2026-01-02", "updated_at": "2026-02-01",
        "personal_data": {"nif": enc.encrypt(nif), "nome": f"Cliente {i:05d}", "birth_year": 1990},
    })


class TestOsDadosPessoaisSoDaPagina:
    async def test_a_leitura_grande_nao_traz_dados_pessoais(self, ambiente):
        base, contador = ambiente
        await _semear(base, 30)
        contador.limpar()
        await _lista()
        com_filtro_de_ids = [c for c in contador.de("processes") if "'id': {'$in'" in repr(c["comando"].get("filter", {}))]
        assert com_filtro_de_ids, "a página lê os dados pessoais por id"
        lista_toda = [c for c in contador.de("processes") if c not in com_filtro_de_ids]
        assert lista_toda
        for c in lista_toda:
            assert "personal_data" not in (c["comando"].get("projection") or {}), c["comando"].get("projection")

    async def test_a_leitura_grande_nao_pede_ordenacao_ao_mongo(self, ambiente):
        base, contador = ambiente
        await _semear(base, 30)
        contador.limpar()
        await _lista()
        for c in contador.de("processes"):
            assert "sort" not in c["comando"], "a ordenação por nome faz-se em memória, estável"

    async def test_as_linhas_da_pagina_trazem_os_dados_pessoais_do_primeiro_processo(self, ambiente):
        base, _ = ambiente
        await _semear(base, 30)
        r = await _lista()
        assert r["clients"]
        for linha in r["clients"]:
            assert "_processo_dos_dados_pessoais" not in linha        # a marca de trabalho nunca sai
            esperado = str(500000000 + int(linha["nome"].split()[-1]))
            assert linha["nif"] == esperado
            assert linha["dados_pessoais"]["nif"] == esperado
            assert linha["dados_pessoais"]["nome"] == linha["nome"]

    async def test_ordenar_por_nif_exige_a_lista_inteira_com_dados_pessoais(self, ambiente):
        base, contador = ambiente
        await _semear(base, 30)
        contador.limpar()
        r = await _lista(sort_field="nif", sort_order="desc")
        lista_toda = [c for c in contador.de("processes") if "'id': {'$in'" not in repr(c["comando"].get("filter", {}))]
        assert any("personal_data" in (c["comando"].get("projection") or {}) for c in lista_toda)
        nifs = [l["nif"] for l in r["clients"]]
        assert nifs == sorted(nifs, reverse=True) and len(nifs) == 30

    async def test_a_origem_e_o_tipo_so_se_leem_para_a_pagina(self, ambiente):
        base, contador = ambiente
        await _semear(base, 120)
        contador.limpar()
        r = await _lista()
        assert len(r["clients"]) == 50
        leituras = [c for c in contador.de("clients") if "$nor" not in c["comando"].get("filter", {})]
        assert leituras, "a origem lê-se para a página"
        for c in leituras:
            # nenhuma leitura de clientes por `$in` com mais ids do que a página (a da JANELA tem `$nor`: lê só
            # os clientes que NÃO são da minha rede, e é a outra consulta)
            ids = c["comando"]["filter"]["id"]["$in"]
            assert len(ids) <= 50, f"{len(ids)} ids"

    async def test_a_origem_chega_as_linhas_da_pagina(self, ambiente):
        base, _ = ambiente
        await _semear(base, 20)
        r = await _lista()
        assert all(l.get("fonte") == "web" for l in r["clients"])


class TestAJanelaLeSoOsClientesDeFora:
    """`so_o_que_a_janela_deixa_ver` pede só os clientes que NÃO são da minha rede (a gémea Mongo do predicado)."""

    AMOSTRA = [
        {"id": "k-minha-rede", "network_id": "rede-A"},
        {"id": "k-minha-empresa", "company_id": "c1"},
        {"id": "k-minha-empresa-nome", "company": "Power"},
        {"id": "k-outra-rede", "network_id": "rede-B"},
        {"id": "k-outra-empresa", "company_id": "c-outra", "network_id": "rede-B"},
        {"id": "k-sem-carimbo-com-processo", "process_ids": ["x"]},
        {"id": "k-pool", "lead_status": "new"},
        {"id": "k-sem-carimbo-convertido", "lead_status": "converted"},
    ]

    async def test_a_condicao_mongo_e_o_predicado_em_python_dizem_o_mesmo(self, ambiente):
        from services.tenant_network import build_network_scope_condition, documento_no_ambito, resolve_tenant_scope

        base, _ = ambiente
        await base.clients.insert_many([{**d, "nome": d["id"]} for d in self.AMOSTRA])
        scope = await resolve_tenant_scope(DIRETOR)
        fora_no_mongo = {
            d["id"] async for d in base.clients.find({"$nor": [build_network_scope_condition(scope)]}, {"_id": 0, "id": 1})
        }
        fora_em_python = {
            d["id"] async for d in base.clients.find({}, {"_id": 0}) if not documento_no_ambito(d, scope)
        }
        assert fora_no_mongo == fora_em_python
        assert "k-outra-rede" in fora_no_mongo and "k-minha-rede" not in fora_no_mongo     # a amostra morde

    async def test_a_janela_continua_a_esconder_o_que_esconde(self, ambiente):
        """Cliente de outra rede visto por um processo partilhado: só esse processo entra; o antigo, sem carimbo, não."""
        from services.client_window import so_o_que_a_janela_deixa_ver

        base, _ = ambiente
        await base.clients.insert_many([
            {"id": "cl-a", "nome": "Da Minha Rede", "network_id": "rede-A", "process_ids": ["pa"]},
            {"id": "cl-b", "nome": "De Outra Rede", "network_id": "rede-B", "process_ids": ["pb", "pb2"]},
            {"id": "cl-pool", "nome": "Da Pool", "lead_status": "new"},
        ])
        linhas = [
            {"id": "pa", "client_id": "cl-a", "network_id": "rede-A"},
            {"id": "pb", "client_id": "cl-b", "network_id": "rede-B", "partner_network_ids": ["rede-A"]},   # partilhado
            {"id": "pb2", "client_id": "cl-b"},                                                              # antigo, sem carimbo
            {"id": "pp", "client_id": "cl-pool"},
            {"id": "px", "client_id": "cl-desconhecido"},
            {"id": "ps"},                                                                                    # sem cliente
        ]
        ficam = [p["id"] for p in await so_o_que_a_janela_deixa_ver(linhas, DIRETOR)]
        assert ficam == ["pa", "pb", "pp", "px", "ps"]

    async def test_a_listagem_nunca_traz_clientes_de_outra_rede(self, ambiente):
        base, _ = ambiente
        await base.clients.insert_many([
            {"id": "cl-a", "nome": "Da Minha Rede", "network_id": "rede-A", "process_ids": ["pa"]},
            {"id": "cl-b", "nome": "De Outra Rede", "network_id": "rede-B", "process_ids": ["pb"]},
        ])
        await base.processes.insert_many([
            {"id": "pa", "client_id": "cl-a", "client_name": "Da Minha Rede", "status": "novo", "network_id": "rede-A", "is_deleted": False},
            {"id": "pb", "client_id": "cl-b", "client_name": "De Outra Rede", "status": "novo", "network_id": "rede-B",
             "partner_network_ids": ["rede-A"], "is_deleted": False},
        ])
        r = await _lista()
        assert [c["nome"] for c in r["clients"]] == ["Da Minha Rede"]


class TestOPrimeiroProcessoDoClienteContinuaASerODeMenorNome:
    async def test_o_cliente_mostra_os_dados_do_processo_que_vem_primeiro_por_nome(self, ambiente):
        """Era o `sort("client_name")` do Mongo que decidia qual processo dava a linha: agora é o sort em memória."""
        base, _ = ambiente
        await base.clients.insert_one({"id": "cl-x", "nome": "X", "network_id": "rede-A", "process_ids": ["p1", "p2"]})
        await base.processes.insert_many([
            {"id": "p1", "client_id": "cl-x", "client_name": "Zeca Silva", "status": "novo", "network_id": "rede-A",
             "is_deleted": False, "personal_data": {"nif": enc.encrypt("111111111"), "origem": "do-zeca"}},
            {"id": "p2", "client_id": "cl-x", "client_name": "Ana Silva", "status": "novo", "network_id": "rede-A",
             "is_deleted": False, "personal_data": {"nif": enc.encrypt("222222222"), "origem": "da-ana"}},
        ])
        (linha,) = (await _lista())["clients"]
        assert linha["nome"] == "Ana Silva"
        assert linha["nif"] == "222222222" and linha["dados_pessoais"]["origem"] == "da-ana"
        assert linha["process_ids"] == ["p2", "p1"]


class TestAOrdemPorNomeJaNaoVemDoMongo:
    def test_sem_nome_primeiro_e_depois_ordem_binaria(self):
        linhas = [{"client_name": "b"}, {"client_name": None}, {"client_name": "B"}, {}, {"client_name": "a"}, {"client_name": ""}]
        ordenadas = sorted(linhas, key=cls._por_nome_do_cliente)
        nomes = [l.get("client_name") for l in ordenadas]
        # `null` e ausente primeiro (como o sort do Mongo), depois "", "B" < "a" < "b" (binário)
        assert nomes[:2] == [None, None] and nomes[2:] == ["", "B", "a", "b"]

    def test_e_estavel_para_o_mesmo_nome(self):
        a, b = {"client_name": "x", "id": 1}, {"client_name": "x", "id": 2}
        assert sorted([a, b], key=cls._por_nome_do_cliente) == [a, b]
