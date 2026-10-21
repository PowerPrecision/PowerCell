"""P4 — a lista de clientes pagina e ordena no SERVIDOR, e filtra «Por Parceiro».

O que a QA viu: a lista de clientes demorava (o ecrã pedia 500 de uma vez e ordenava no browser),
não havia filtro por parceiro nas listas de Clientes e de Processos, e o filtro de parceiro do
quadro vinha vazio — os dropdowns liam os parceiros da lista de utilizadores (`role == parceiro`),
que desde o QA-9 não os traz, e os parceiros do Portal vivem em `db.partners`.
"""
from __future__ import annotations

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}


def _cli(id, nome, **kw):
    base = {
        "id": id, "nome": nome, "contacto": {"email": f"{id}@x.pt", "telefone": "910000000"},
        "dados_pessoais": {"nif": "100000000"}, "company_id": "cmp-power",
        "network_id": REDE_INCUMBENTE, "process_ids": [], "created_at": "2026-10-01T10:00:00Z",
    }
    base.update(kw)
    return base


def _proc(id, client_id, nome, **kw):
    base = {
        "id": id, "client_id": client_id, "client_name": nome, "status": "em_analise",
        "process_number": 1, "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
        "created_at": "2026-10-01T10:00:00Z",
    }
    base.update(kw)
    return base


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.client_list_search as cls
    import services.client_list_titulares as clt

    semear(fake_async_db)
    fake_async_db.processes.docs.clear()
    fake_async_db.clients.docs.clear()
    nomes = ["Ana", "Bruno", "Carla", "Duarte", "Elsa", "Filipe", "Graça"]
    for i, n in enumerate(nomes):
        fake_async_db.clients.docs.append(_cli(f"c-{n.lower()}", n, created_at=f"2026-10-0{i + 1}T10:00:00Z"))
        fake_async_db.processes.docs.append(_proc(f"p-{n.lower()}", f"c-{n.lower()}", n))
    with tenant_db(fake_async_db, cls, clt):
        yield fake_async_db


async def _listar(**kw):
    import services.client_list_search as cls

    return await cls.run_list_clients(ANA, **kw)


# ───────────────────────── paginação ─────────────────────────
@pytest.mark.asyncio
async def test_a_pagina_traz_so_o_tamanho_pedido_e_o_total(mundo):
    r = await _listar(page=1, size=3, sort_field="nome", sort_order="asc")
    assert [c["nome"] for c in r["clients"]] == ["Ana", "Bruno", "Carla"]
    assert (r["total"], r["page"], r["size"], r["pages"]) == (7, 1, 3, 3)


@pytest.mark.asyncio
async def test_as_paginas_percorrem_tudo_sem_repetir(mundo):
    vistos = []
    for pagina in (1, 2, 3):
        r = await _listar(page=pagina, size=3, sort_field="nome", sort_order="asc")
        vistos += [c["nome"] for c in r["clients"]]
    assert vistos == ["Ana", "Bruno", "Carla", "Duarte", "Elsa", "Filipe", "Graça"]


@pytest.mark.asyncio
async def test_o_tamanho_tem_tecto(mundo):
    from services.client_list_search import TAMANHO_MAXIMO

    r = await _listar(page=1, size=100000)
    assert r["size"] == TAMANHO_MAXIMO


@pytest.mark.asyncio
async def test_sem_page_o_comportamento_antigo_mantem_se(mundo):
    r = await _listar(limit=2, skip=1)
    assert len(r["clients"]) == 2 and r["total"] == 7 and "page" not in r


# ───────────────────────── ordenação no servidor ─────────────────────────
@pytest.mark.asyncio
async def test_ordena_descendente_por_nome(mundo):
    r = await _listar(page=1, size=3, sort_field="nome", sort_order="desc")
    assert [c["nome"] for c in r["clients"]] == ["Graça", "Filipe", "Elsa"]


@pytest.mark.asyncio
async def test_ordena_por_data_de_registo(mundo):
    # A data do cliente na lista é a do seu processo mais antigo (como sempre foi).
    for i, n in enumerate(["ana", "bruno", "carla", "duarte", "elsa", "filipe", "graça"]):
        for p in mundo.processes.docs:
            if p["id"] == f"p-{n}":
                p["created_at"] = f"2026-10-0{i + 1}T10:00:00Z"
    r = await _listar(page=1, size=2, sort_field="created_at", sort_order="desc")
    assert [c["nome"] for c in r["clients"]] == ["Graça", "Filipe"]


@pytest.mark.asyncio
async def test_a_prioridade_alta_continua_a_vir_primeiro(mundo):
    for p in mundo.processes.docs:
        if p["id"] == "p-graça":
            p["prioridade"] = "alta"
    r = await _listar(page=1, size=3, sort_field="nome", sort_order="asc")
    assert r["clients"][0]["nome"] == "Graça"


@pytest.mark.asyncio
async def test_ordenar_por_nif_ordena_pelos_valores_desencriptados(mundo):
    """O NIF está cifrado até à desencriptação: ordenar a lista antes dela ordenava texto cifrado."""
    from services import client_list_search as cls

    nifs = {"c-ana": "300000000", "c-bruno": "100000000", "c-carla": "200000000"}
    for p in mundo.processes.docs:
        if p["client_id"] in nifs:
            p["personal_data"] = {"nif": nifs[p["client_id"]]}
    chamadas = []
    original = cls.decrypt_clients_list

    def espiar(lista):
        chamadas.append(len(lista))
        return original(lista)

    cls.decrypt_clients_list = espiar
    try:
        r = await _listar(page=1, size=3, sort_field="nif", sort_order="asc")
    finally:
        cls.decrypt_clients_list = original
    assert chamadas == [7], "desencripta a lista INTEIRA uma vez (e só uma) para ordenar por NIF"
    assert [c["nome"] for c in r["clients"]][:3] == ["Bruno", "Carla", "Ana"]


@pytest.mark.asyncio
async def test_um_campo_desconhecido_nao_ordena_nem_rebenta(mundo):
    r = await _listar(page=1, size=3, sort_field="password_hash", sort_order="asc")
    assert len(r["clients"]) == 3


def test_quem_nao_tem_valor_vai_sempre_para_o_fim():
    from services.client_list_search import ordenar_clientes

    lista = [{"nome": "B"}, {"nome": ""}, {"nome": "A"}]
    assert [c["nome"] for c in ordenar_clientes(lista, "nome", "asc")] == ["A", "B", ""]
    assert [c["nome"] for c in ordenar_clientes(lista, "nome", "desc")] == ["B", "A", ""]


# ───────────────────────── filtro por parceiro ─────────────────────────
@pytest.mark.asyncio
async def test_filtra_pelos_clientes_que_o_parceiro_trouxe(mundo):
    for c in mundo.clients.docs:
        if c["id"] in ("c-ana", "c-bruno"):
            c["submitted_by_partner_id"] = "pt-1"
        if c["id"] == "c-carla":
            c["submitted_by_partner_id"] = "pt-2"
    r = await _listar(parceiro="pt-1")
    assert {c["nome"] for c in r["clients"]} == {"Ana", "Bruno"}


@pytest.mark.asyncio
async def test_filtra_tambem_pelo_processo_atribuido_ao_parceiro(mundo):
    """O parceiro posto à mão no processo (sem passar pela lead) também conta."""
    for p in mundo.processes.docs:
        if p["id"] == "p-duarte":
            p["assigned_parceiro_id"] = "pt-1"
    r = await _listar(parceiro="pt-1")
    assert {c["nome"] for c in r["clients"]} == {"Duarte"}


@pytest.mark.asyncio
async def test_um_processo_eliminado_nao_traz_o_cliente(mundo):
    for p in mundo.processes.docs:
        if p["id"] == "p-elsa":
            p["assigned_parceiro_id"] = "pt-1"
            p["is_deleted"] = True
    r = await _listar(parceiro="pt-1")
    assert r["clients"] == []


@pytest.mark.asyncio
async def test_o_parceiro_nao_atravessa_a_fronteira_de_rede(mundo):
    """Um cliente da Domus com o mesmo parceiro não aparece a quem é da rede incumbente."""
    mundo.clients.docs.append(_cli("c-dom", "Dália", company_id="cmp-domus", network_id=REDE_DOMUS,
                                   submitted_by_partner_id="pt-1"))
    mundo.processes.docs.append(_proc("p-dom", "c-dom", "Dália", company_id="cmp-domus",
                                      network_id=REDE_DOMUS, assigned_parceiro_id="pt-1"))
    r = await _listar(parceiro="pt-1")
    assert all(c["nome"] != "Dália" for c in r["clients"])


@pytest.mark.asyncio
@pytest.mark.parametrize("valor", [None, "", "all", "none"])
async def test_sem_parceiro_concreto_nao_filtra(mundo, valor):
    r = await _listar(parceiro=valor)
    assert r["total"] == 7


# ───────────────────────── processos: a condição é UMA ─────────────────────────
def test_a_condicao_do_parceiro_e_a_mesma_para_a_lista_e_para_o_quadro():
    from services.process_list_filters import (
        build_kanban_assignee_filters,
        condicao_do_parceiro,
    )

    for valor in ("pt-1", "none"):
        assert condicao_do_parceiro(valor) in build_kanban_assignee_filters(
            consultor_id=None, mediador_id=None, indexacao_id=None, parceiro_id=valor,
        )
    assert condicao_do_parceiro(None) is None and condicao_do_parceiro("all") is None


def test_a_lista_de_processos_aplica_o_filtro_de_parceiro():
    from services.process_list_filters import build_process_list_query

    user = {"id": "u", "role": "diretor"}
    com = build_process_list_query(user, "diretor", show_all=True, parceiro_id="pt-1")
    sem = build_process_list_query(user, "diretor", show_all=True)
    assert "pt-1" in repr(com) and "pt-1" not in repr(sem)


# ───────────────────────── as opções de parceiro ─────────────────────────
@pytest.mark.asyncio
async def test_as_opcoes_trazem_os_parceiros_do_portal_e_os_antigos_sem_duplicar(mundo):
    import services.partner_accounts as pa

    mundo.partners.docs.extend([
        {"id": "pt-1", "name": "Rui", "email": "r@p.pt", "status": "active",
         "redes": [{"network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "status": "active"}]},
        {"id": "pt-3", "name": "Tomé", "email": "t@p.pt", "status": "active",
         "redes": [{"network_id": REDE_DOMUS, "company_id": "cmp-domus", "status": "active"}]},
    ])
    mundo.users.docs.append({"id": "pt-1", "name": "Rui (conta antiga)", "role": "parceiro",
                             "is_active": True, "company": "Power Real Estate"})
    mundo.users.docs.append({"id": "pt-velho", "name": "Ana Velha", "role": "parceiro",
                             "is_active": True, "company": "Power Real Estate"})
    from services import admin_users_scope

    # `empresas_do_scope` lê as empresas pela `db` do seu módulo: sem a patchar, o teste falava com o
    # motor real e rebentava com «Event loop is closed» conforme a ordem de recolha.
    with tenant_db(mundo, pa, admin_users_scope):
        r = await pa.run_list_partner_options({**ANA, "vista_empresa_id": None})
    nomes = {o["id"]: o["name"] for o in r["partners"]}
    assert nomes.get("pt-1") == "Rui"  # o do Portal ganha ao antigo com o mesmo id
    assert "pt-velho" in nomes
    assert "pt-3" not in nomes, "um parceiro de outra rede não aparece"
    assert set(r["partners"][0]) == {"id", "name"}


def test_o_endpoint_de_opcoes_e_para_staff_e_nao_expoe_dados_pessoais():
    import inspect

    from routes import partner_options

    from services import partner_accounts
    from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

    assert "require_staff" in inspect.getsource(partner_options)
    # Só id e nome: nada de email, telefone nem ligações na saída.
    corpo = codigo_da_funcao_sem_comentarios(partner_accounts.run_list_partner_options)
    assert "publico(" not in corpo and "password" not in corpo
    assert "{'id': i, 'name': n}" in corpo


# ───────────────────────── índices ─────────────────────────
def _indices(colecao: str) -> dict[str, list[str]]:
    from services.db_indexes import INDEX_DEFINITIONS

    return {i["name"]: [k for k, _ in i["keys"]] for i in INDEX_DEFINITIONS.get(colecao, [])}


def test_a_colecao_de_clientes_tem_indices_de_rede_e_de_empresa():
    indices = _indices("clients")
    assert indices["idx_client_rede_activos"][:2] == ["network_id", "is_deleted"]
    assert indices["idx_client_empresa_activos"][:2] == ["company_id", "is_deleted"]


def test_a_colecao_de_processos_tem_indice_de_empresa_e_de_ordenacao_por_cliente():
    indices = _indices("processes")
    assert indices["idx_proc_empresa_estado"][0] == "company_id"
    assert indices["idx_proc_rede_cliente"] == ["network_id", "is_deleted", "client_name"]
    # O filtro «Por Parceiro» já tinha o seu (parceiro → rede → não eliminado).
    assert indices["idx_proc_parceiro_rede"][0] == "assigned_parceiro_id"


def test_o_filtro_de_parceiro_chega_a_todas_as_listagens_de_processos():
    """A lição do Sub35 e da partilha: um filtro que só exista numa listagem dá outra a ignorá-lo."""
    import inspect

    from routes import processes

    for nome in ("get_processes", "get_my_processes", "get_processes_paginated", "get_process_neighbours"):
        assert "parceiro_id" in inspect.signature(getattr(processes, nome)).parameters, nome
