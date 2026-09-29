"""A Pool de registos: por carimbar é de todos, carimbado é da sua rede.

O QUE ESTAVA MAL (P0, Set 2026)
===============================
`GET /clients/registered` — a página "Registos de Clientes", aberta a
`STAFF_ROLES` — não tinha filtro de rede NENHUM. Um utilizador da Domus,
que é uma ilha, via os clientes da Power. O `client_registered.py` tinha
zero ocorrências de `build_tenant_condition`/`network_id`, e a docstring
dizia "ACESSO: Todos os utilizadores".

É a quinta instância da mesma lição: fez-se ponto único para a CONDIÇÃO
(Lote 4) e não se inventariaram os sítios que LISTAM. Dos quinze serviços
de clientes, só o `client_list_search.py` filtrava.

PORQUE É QUE NÃO SE USA O `build_tenant_condition` NORMAL
=========================================================
Porque esta listagem é uma **Pool** e a regra é outra. O
`build_network_scope_condition` só inclui a pilha por carimbar quando o
utilizador pertence à rede de omissão (`inclui_rede_de_omissao`) — o que
é certo para processos e **errado** para a Pool: um registo público ainda
não pertence a ninguém e tem de ser visível a todas as redes, senão nunca
é reivindicado.

A regra do produto (decisão do dono):

  sem carimbo  → é da POOL, visível a TODOS;
  com carimbo  → é de UMA rede, e só essa o vê.

O carimbo é aplicado no momento da REIVINDICAÇÃO, com a rede de quem
passa a ser dono — não a empresa. Power e Precision partilham rede e têm
de continuar a colaborar; a Domus é a ilha.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.tenant_network import (
    CAMPO_REDE,
    TenantScope,
    build_network_scope_condition,
    build_pool_scope_condition,
)

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "rede_domus"


def _scope(rede: str) -> TenantScope:
    return TenantScope(
        network_ids=(rede,),
        company_ids=(),
        company_names=(),
        inclui_rede_de_omissao=False,
    )


def _casa(condicao: dict, doc: dict) -> bool:
    """Avalia a condição contra um documento com o matcher do duplo.

    Usar o matcher partilhado em vez de reimplementar `$or`/`$and` aqui:
    uma terceira implementação da semântica do Mongo divergiria, e seria
    ela — não a condição — o que o teste estaria a provar.
    """
    from tests.unit.conftest import FakeAsyncCollection

    return FakeAsyncCollection._matches(doc, condicao)


class TestACondicaoDaPool:
    def test_o_registo_por_carimbar_e_visivel_a_QUALQUER_rede(self):
        """É isto que faz dela uma Pool: ninguém é dono ainda."""
        por_carimbar = {"id": "c-1", "registration_completed": True}
        for rede in (REDE_POWER, REDE_DOMUS):
            assert _casa(build_pool_scope_condition(_scope(rede)), por_carimbar)

    def test_o_registo_carimbado_so_e_visivel_a_SUA_rede(self):
        da_power = {"id": "c-2", CAMPO_REDE: REDE_POWER}
        assert _casa(build_pool_scope_condition(_scope(REDE_POWER)), da_power)
        assert not _casa(build_pool_scope_condition(_scope(REDE_DOMUS)), da_power)

    def test_a_DOMUS_nao_ve_o_que_e_da_power(self):
        """O caso relatado em produção, escrito como teste."""
        condicao = build_pool_scope_condition(_scope(REDE_DOMUS))
        assert not _casa(condicao, {"id": "c-3", CAMPO_REDE: REDE_POWER})

    def test_uma_marca_de_EMPRESA_tambem_tira_da_pool(self):
        """Por carimbar exige ausência de TODAS as marcas.

        Olhar só para a rede deixaria a fuga entrar pela cláusula que a
        evita — um documento com `company_id` e sem `network_id` contaria
        como Pool e seria visível a toda a gente.
        """
        condicao = build_pool_scope_condition(_scope(REDE_DOMUS))
        assert not _casa(condicao, {"id": "c-4", "company_id": "empresa-power"})
        assert not _casa(condicao, {"id": "c-5", "company_name": "Power"})

    def test_DERIVA_do_construtor_normal_e_nao_o_reescreve(self):
        """Contraprova de forma: a única diferença é a pilha por carimbar.

        Se a Pool tivesse ramos próprios escritos à mão, divergiria do
        isolamento normal na primeira mudança — o defeito do Lote 5 com
        outro nome.
        """
        scope = _scope(REDE_DOMUS)
        esperado = build_network_scope_condition(
            TenantScope(
                network_ids=scope.network_ids,
                company_ids=scope.company_ids,
                company_names=scope.company_names,
                inclui_rede_de_omissao=True,
            )
        )
        assert build_pool_scope_condition(scope) == esperado

    def test_um_ambito_vazio_nao_abre_a_pool_toda(self):
        """Sem rede nenhuma continua a ver a Pool, mas nada carimbado."""
        vazio = TenantScope((), (), (), inclui_rede_de_omissao=False)
        condicao = build_pool_scope_condition(vazio)
        assert _casa(condicao, {"id": "c-6"})
        assert not _casa(condicao, {"id": "c-7", CAMPO_REDE: REDE_POWER})


class TestAListagemDeRegistosAplicaAPool:
    """O construtor certo não vale nada se a listagem não o chamar."""

    async def _listar(self, fake_async_db, rede: str):
        from services import client_registered as modulo

        condicao = build_pool_scope_condition(_scope(rede))
        with patch.object(modulo, "db", fake_async_db), \
                patch.object(
                    modulo, "build_tenant_pool_condition",
                    AsyncMock(return_value=condicao),
                ):
            return await modulo.run_list_registered_clients(
                {"id": "u-domus", "role": "consultor", "email": "d@x.pt"},
            )

    @pytest.fixture
    def _semeado(self, fake_async_db):
        async def _seed():
            await fake_async_db.clients.insert_one({
                "id": "c-power", "nome": "Cliente Power",
                "registration_completed": True, CAMPO_REDE: REDE_POWER,
            })
            await fake_async_db.clients.insert_one({
                "id": "c-pool", "nome": "Cliente Pool",
                "registration_completed": True,
            })
        return _seed

    async def test_a_domus_NAO_ve_o_cliente_da_power(self, fake_async_db, _semeado):
        await _semeado()
        resultado = await self._listar(fake_async_db, REDE_DOMUS)
        ids = {c.get("id") for c in (resultado.get("clients") or resultado)}
        assert "c-power" not in ids

    async def test_mas_CONTINUA_a_ver_a_pool(self, fake_async_db, _semeado):
        """Contraprova: sem isto, "não vê nada" passava o teste de cima."""
        await _semeado()
        resultado = await self._listar(fake_async_db, REDE_DOMUS)
        ids = {c.get("id") for c in (resultado.get("clients") or resultado)}
        assert "c-pool" in ids

    async def test_a_power_ve_os_dois(self, fake_async_db, _semeado):
        await _semeado()
        resultado = await self._listar(fake_async_db, REDE_POWER)
        ids = {c.get("id") for c in (resultado.get("clients") or resultado)}
        assert {"c-power", "c-pool"} <= ids


class TestReivindicarCarimbaARede:
    """O carimbo nasce na reivindicação — é o outro meio da correcção.

    Filtrar a leitura sem carimbar a escrita deixava a Pool a crescer para
    sempre: tudo por carimbar é de todos, portanto nada ficaria isolado. É
    a lição do `assigned_to`: corrigir só a leitura torna a correcção
    invisível para o trabalho novo.
    """

    def test_a_fonte_do_carimbo_e_quem_fica_DONO_e_nao_quem_clica(self):
        """Um admin que atribui a um consultor da Domus carimba DOMUS.

        O acto é do admin; o dono é o consultor. Carimbar a rede de quem
        clica poria o cliente na rede errada sempre que a Direcção fizesse
        a triagem — e um carimbo errado é permanente.
        """
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
        from services.client_assign import run_assign_client_to_user

        fonte = codigo_da_funcao_sem_comentarios(run_assign_client_to_user)
        assert "resolve_tenant_stamp(target_user" in fonte

    def test_o_processo_criado_na_reivindicacao_leva_o_carimbo(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
        from services.client_assign import run_assign_client_to_user

        fonte = codigo_da_funcao_sem_comentarios(run_assign_client_to_user)
        assert "process_doc.update(carimbo" in fonte or "**carimbo" in fonte
