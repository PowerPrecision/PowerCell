"""Clientes que são 2.º titular têm de aparecer nas listas (Bloco 1, ponto 6).

O DEFEITO
=========
`run_list_clients` constrói a lista A PARTIR DOS PROCESSOS e agrupa por
`proc["client_id"]` — só o 1.º titular. O `second_client_id` e o
`client_ids` são escritos (a criação, a edição e o `add-client` fazem-no),
mas a listagem não os lê. Duas consequências, as duas relatadas:

1. **Quem é apenas 2.º titular não aparece em lista nenhuma** (a menos que
   tenha um processo seu).
2. **Quem é 1.º titular num processo e 2.º noutro desaparece da lista de
   activos quando o processo de 1.º titular é anulado**: o processo de 2.º
   titular, que continua activo, é atribuído à linha do OUTRO cliente.

A CORRECÇÃO
===========
Cada processo com titulares secundários contribui com uma linha por
secundário, construída a partir do DOCUMENTO DO CLIENTE (nome, contacto,
NIF), e entra no mesmo acumulador do 1.º titular — por isso as contagens, o
filtro «tem processo activo» e a fase principal passam a contar os dois
papéis sem código novo.

`TestAExploracao` é o ataque, escrito para morder primeiro.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}
CARLA = {"id": "u-carla", "name": "Carla", "email": "carla@precision.pt", "role": "consultor"}


def _cli(id, nome, **kw):
    base = {
        "id": id, "nome": nome, "contacto": {"email": f"{id}@x.pt", "telefone": "910000000"},
        "dados_pessoais": {"nif": "100000000"}, "company_id": "cmp-power",
        "network_id": REDE_INCUMBENTE, "process_ids": [],
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
    fake_async_db.clients.docs.extend([
        _cli("c-main", "Marta Principal"),
        _cli("c-ines", "Inês Segunda"),
        _cli("c-rui", "Rui Duplo"),
        _cli("c-co", "Carlos Cotitular"),
        _cli("c-domus", "Dália da Domus", company_id="cmp-domus", network_id=REDE_DOMUS),
    ])
    with tenant_db(fake_async_db, cls, clt):
        yield fake_async_db


async def _listar(user=ANA, **kw):
    import services.client_list_search as cls

    kw.setdefault("limit", 100)
    return await cls.run_list_clients(user, **kw)


def _por_id(res):
    return {c["id"]: c for c in res["clients"]}


# ════════════════════════════════════════════════════════════════════
class TestAExploracao:
    """O ataque. Cada um destes falhava antes deste lote."""

    @pytest.mark.asyncio
    async def test_quem_e_apenas_segundo_titular_aparece_na_lista(self, mundo):
        mundo.processes.docs.append(_proc("p1", "c-main", "Marta Principal", second_client_id="c-ines"))
        res = _por_id(await _listar())
        assert "c-ines" in res
        assert res["c-ines"]["nome"] == "Inês Segunda"
        assert res["c-ines"]["active_processes_count"] == 1

    @pytest.mark.asyncio
    async def test_anular_o_processo_de_primeiro_titular_nao_faz_o_cliente_desaparecer(self, mundo):
        """A queixa literal: 1.º titular em P1 (anulado), 2.º titular em P2 (activo)."""
        mundo.processes.docs.extend([
            _proc("p1", "c-rui", "Rui Duplo", status="cancelado"),
            _proc("p2", "c-main", "Marta Principal", second_client_id="c-rui"),
        ])
        res = _por_id(await _listar(has_active_process=True))
        assert "c-rui" in res, "sumiu da lista de activos"
        assert res["c-rui"]["active_processes_count"] == 1

    @pytest.mark.asyncio
    async def test_o_mesmo_com_o_processo_anulado_por_eliminacao(self, mundo):
        mundo.processes.docs.extend([
            _proc("p1", "c-rui", "Rui Duplo", is_deleted=True, status="eliminado"),
            _proc("p2", "c-main", "Marta Principal", second_client_id="c-rui"),
        ])
        res = _por_id(await _listar(exclude_deleted=True, has_active_process=True))
        assert "c-rui" in res


class TestOsTresSitiosDoCliente:
    @pytest.mark.asyncio
    async def test_co_titular_da_lista_n_m(self, mundo):
        mundo.processes.docs.append(
            _proc("p1", "c-main", "Marta Principal", client_ids=["c-main", "c-co"])
        )
        assert "c-co" in _por_id(await _listar())

    @pytest.mark.asyncio
    async def test_o_primeiro_titular_nao_e_duplicado_pelo_client_ids(self, mundo):
        """`client_ids` inclui sempre o 1.º titular: não pode gerar uma segunda linha."""
        mundo.processes.docs.append(
            _proc("p1", "c-main", "Marta Principal", client_ids=["c-main", "c-co"])
        )
        res = await _listar()
        assert [c["id"] for c in res["clients"]].count("c-main") == 1
        assert _por_id(res)["c-main"]["active_processes_count"] == 1

    @pytest.mark.asyncio
    async def test_um_cliente_em_dois_papeis_e_UMA_linha_com_os_dois_processos(self, mundo):
        mundo.processes.docs.extend([
            _proc("p1", "c-rui", "Rui Duplo"),
            _proc("p2", "c-main", "Marta Principal", second_client_id="c-rui"),
        ])
        res = await _listar()
        linhas = [c for c in res["clients"] if c["id"] == "c-rui"]
        assert len(linhas) == 1
        assert {p["id"] for p in linhas[0]["processes"]} == {"p1", "p2"}
        assert linhas[0]["active_processes_count"] == 2

    @pytest.mark.asyncio
    async def test_o_primeiro_titular_continua_a_aparecer_com_o_seu_processo(self, mundo):
        mundo.processes.docs.append(_proc("p1", "c-main", "Marta Principal", second_client_id="c-ines"))
        res = _por_id(await _listar())
        assert [p["id"] for p in res["c-main"]["processes"]] == ["p1"]
        assert res["c-main"]["nome"] == "Marta Principal"

    @pytest.mark.asyncio
    async def test_o_processo_diz_em_que_papel_o_cliente_esta(self, mundo):
        mundo.processes.docs.append(_proc("p1", "c-main", "Marta Principal", second_client_id="c-ines"))
        res = _por_id(await _listar())
        assert res["c-main"]["processes"][0]["titular"] == "titular1"
        assert res["c-ines"]["processes"][0]["titular"] == "titular2"


class TestOsFiltros:
    @pytest.mark.asyncio
    async def test_o_filtro_de_fase_aplica_se_ao_processo_do_segundo_titular(self, mundo):
        mundo.processes.docs.extend([
            _proc("p1", "c-main", "Marta Principal", status="novo", second_client_id="c-ines"),
            _proc("p2", "c-rui", "Rui Duplo", status="em_analise", second_client_id="c-co"),
        ])
        res = _por_id(await _listar(status_filter="novo"))
        assert {"c-main", "c-ines"} <= set(res)
        assert "c-co" not in res and "c-rui" not in res

    @pytest.mark.asyncio
    async def test_pesquisar_pelo_nome_do_segundo_titular_encontra_o_cliente(self, mundo):
        mundo.processes.docs.extend([
            _proc("p1", "c-main", "Marta Principal", second_client_id="c-ines"),
            # Contraprova: um OUTRO 2.º titular, que a pesquisa não casa.
            _proc("p2", "c-rui", "Rui Duplo", second_client_id="c-co"),
        ])
        res = _por_id(await _listar(search="Inês"))
        assert "c-ines" in res
        assert "c-main" not in res, "a pesquisa é pelo cliente, não pelo processo"
        assert "c-co" not in res, "a pesquisa também filtra os segundos titulares"

    @pytest.mark.asyncio
    async def test_um_processo_eliminado_nao_traz_o_segundo_titular_quando_se_excluem_eliminados(self, mundo):
        mundo.processes.docs.append(
            _proc("p1", "c-main", "Marta Principal", is_deleted=True, status="eliminado", second_client_id="c-ines")
        )
        assert "c-ines" not in _por_id(await _listar(exclude_deleted=True))

    @pytest.mark.asyncio
    async def test_o_filtro_de_eliminados_traz_o_segundo_titular_do_processo_eliminado(self, mundo):
        mundo.processes.docs.append(
            _proc("p1", "c-main", "Marta Principal", is_deleted=True, status="eliminado", second_client_id="c-ines")
        )
        assert "c-ines" in _por_id(await _listar(deleted_only=True))

    @pytest.mark.asyncio
    async def test_o_filtro_de_origem_do_cliente_alcanca_o_segundo_titular(self, mundo):
        next(c for c in mundo.clients.docs if c["id"] == "c-ines")["fonte"] = "portal"
        mundo.processes.docs.extend([
            _proc("p1", "c-main", "Marta Principal", second_client_id="c-ines"),
            # Contraprova: um 2.º titular de outra origem (sem `fonte`).
            _proc("p2", "c-rui", "Rui Duplo", second_client_id="c-co"),
        ])
        res = _por_id(await _listar(fonte="portal"))
        assert "c-ines" in res
        assert "c-main" not in res
        assert "c-co" not in res, "o filtro de origem também vale para os segundos titulares"

    @pytest.mark.asyncio
    async def test_o_filtro_tem_processo_activo_false_nao_inclui_quem_tem_processo_activo_como_segundo(self, mundo):
        mundo.processes.docs.extend([
            _proc("p1", "c-rui", "Rui Duplo", status="cancelado"),
            _proc("p2", "c-main", "Marta Principal", second_client_id="c-rui"),
        ])
        assert "c-rui" not in _por_id(await _listar(has_active_process=False))


class TestARede:
    @pytest.mark.asyncio
    async def test_um_segundo_titular_de_outra_rede_nao_aparece(self, mundo):
        """O processo é da Power mas o `second_client_id` aponta para a Domus."""
        mundo.processes.docs.append(_proc("p1", "c-main", "Marta Principal", second_client_id="c-domus"))
        res = await _listar()
        assert "c-domus" not in _por_id(res)
        assert "Dália" not in str(res)

    @pytest.mark.asyncio
    async def test_um_cliente_eliminado_nao_volta_pela_porta_do_segundo_titular(self, mundo):
        next(c for c in mundo.clients.docs if c["id"] == "c-ines")["is_deleted"] = True
        mundo.processes.docs.append(_proc("p1", "c-main", "Marta Principal", second_client_id="c-ines"))
        assert "c-ines" not in _por_id(await _listar())

    @pytest.mark.asyncio
    async def test_processos_de_outra_rede_nao_geram_segundos_titulares(self, mundo):
        mundo.processes.docs.append(_proc(
            "p-domus", "c-domus", "Dália da Domus", company_id="cmp-domus", network_id=REDE_DOMUS,
            second_client_id="c-ines",
        ))
        assert "c-ines" not in _por_id(await _listar())


class TestOutroCaminhoDaListagem:
    """`show_all=False` («só os meus clientes») tem o seu próprio construtor."""

    @pytest.mark.asyncio
    async def test_o_segundo_titular_de_um_processo_meu_aparece(self, mundo):
        mundo.processes.docs.append(_proc(
            "p1", "c-main", "Marta Principal", second_client_id="c-ines",
            company_id="cmp-precision", assigned_consultor_id="u-carla",
        ))
        mundo.clients.docs[0]["company_id"] = "cmp-precision"
        for c in mundo.clients.docs:
            if c["id"] in ("c-main", "c-ines"):
                c["company_id"] = "cmp-precision"
        res = _por_id(await _listar(user=CARLA, show_all=False))
        assert "c-ines" in res
        assert res["c-ines"]["active_processes_count"] == 1

    @pytest.mark.asyncio
    async def test_um_processo_que_nao_e_meu_nao_traz_o_segundo_titular(self, mundo):
        mundo.processes.docs.append(_proc(
            "p1", "c-main", "Marta Principal", second_client_id="c-ines",
            company_id="cmp-precision", assigned_consultor_id="u-outro",
        ))
        res = _por_id(await _listar(user=CARLA, show_all=False))
        assert "c-ines" not in res


BACKEND = Path(__file__).resolve().parents[2]


class TestALigacao:
    def test_a_listagem_usa_o_modulo_dos_titulares_secundarios(self):
        arvore = ast.parse((BACKEND / "services" / "client_list_search.py").read_text(encoding="utf-8"))
        no = next(n for n in arvore.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_list_clients")
        fonte = ast.unparse(no)
        assert fonte.count("linhas_dos_titulares_secundarios(") >= 2, (
            "os DOIS caminhos (show_all e «só os meus») têm de acrescentar os secundários"
        )
