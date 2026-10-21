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
        estrita = build_network_scope_condition(_scope(rede))
        with patch.object(modulo, "db", fake_async_db), \
                patch.object(
                    modulo, "build_tenant_pool_condition",
                    AsyncMock(return_value=condicao),
                ), \
                patch.object(
                    modulo, "build_tenant_condition",
                    AsyncMock(return_value=estrita),
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


class TestUmClienteComProcessoJaNaoEDaPool:
    """QA-6: o Registo de Clientes mostrava clientes de todas as empresas.

    Clientes criados no CRM antes de o carimbo existir não têm rede; com a regra da Pool
    («sem carimbo é de todos») apareciam a TODAS as redes, mesmo tendo já um processo.
    A Pool é para o que ainda não foi reivindicado — o que tem processo segue o âmbito normal.
    """

    async def _ids(self, fake_async_db, rede):
        from services import client_registered as modulo

        pool = build_pool_scope_condition(_scope(rede))
        estrita = build_network_scope_condition(_scope(rede))
        with patch.object(modulo, "db", fake_async_db), \
                patch.object(modulo, "build_tenant_pool_condition", AsyncMock(return_value=pool)), \
                patch.object(modulo, "build_tenant_condition", AsyncMock(return_value=estrita)):
            resultado = await modulo.run_list_registered_clients(
                {"id": "u", "role": "consultor", "email": "u@x.pt"}, has_process=True,
            )
        return {c.get("id") for c in resultado["clients"]}

    async def _semear(self, fake_async_db):
        # cliente antigo, por carimbar, JÁ com processo (não é da Pool)
        await fake_async_db.clients.insert_one({
            "id": "c-antigo", "nome": "Antigo", "registration_completed": True,
            "process_ids": ["p-1"],
        })
        await fake_async_db.processes.insert_one({"id": "p-1", "client_id": "c-antigo"})
        # cliente com processo, carimbado na Power
        await fake_async_db.clients.insert_one({
            "id": "c-power", "nome": "Power", "registration_completed": True,
            CAMPO_REDE: REDE_POWER, "process_ids": ["p-2"],
        })
        await fake_async_db.processes.insert_one({"id": "p-2", "client_id": "c-power"})

    async def test_a_domus_nao_ve_clientes_com_processo_por_carimbar(self, fake_async_db):
        await self._semear(fake_async_db)
        assert "c-antigo" not in await self._ids(fake_async_db, REDE_DOMUS)

    async def test_nem_o_carimbado_na_power(self, fake_async_db):
        await self._semear(fake_async_db)
        assert "c-power" not in await self._ids(fake_async_db, REDE_DOMUS)

    async def test_a_power_continua_a_ver_o_seu(self, fake_async_db):
        """Contraprova: sem ela, «a Domus não vê nada» passava."""
        await self._semear(fake_async_db)
        assert "c-power" in await self._ids(fake_async_db, REDE_POWER)

    async def test_o_lead_sem_processo_continua_na_pool(self, fake_async_db):
        from services import client_registered as modulo

        await fake_async_db.clients.insert_one(
            {"id": "c-lead", "nome": "Lead", "registration_completed": True}
        )
        pool = build_pool_scope_condition(_scope(REDE_DOMUS))
        estrita = build_network_scope_condition(_scope(REDE_DOMUS))
        with patch.object(modulo, "db", fake_async_db), \
                patch.object(modulo, "build_tenant_pool_condition", AsyncMock(return_value=pool)), \
                patch.object(modulo, "build_tenant_condition", AsyncMock(return_value=estrita)):
            resultado = await modulo.run_list_registered_clients(
                {"id": "u", "role": "consultor", "email": "u@x.pt"},
            )
        assert "c-lead" in {c["id"] for c in resultado["clients"]}


class TestVerOProcessoEmVezDeCriarOutro:
    """QA-6: o `process_ids` do cliente nem sempre está mantido. Um cliente com processo mas
    sem a lista aparecia «Sem Processo» e só oferecia «Criar Processo»."""

    async def _listar(self, fake_async_db, rede=REDE_POWER):
        from services import client_registered as modulo

        pool = build_pool_scope_condition(_scope(rede))
        estrita = build_network_scope_condition(_scope(rede))
        proc = build_network_scope_condition(_scope(rede))
        with patch.object(modulo, "db", fake_async_db), \
                patch.object(modulo, "build_tenant_pool_condition", AsyncMock(return_value=pool)), \
                patch.object(modulo, "build_tenant_condition", AsyncMock(return_value=estrita)), \
                patch.object(modulo, "build_tenant_process_condition", AsyncMock(return_value=proc)):
            resultado = await modulo.run_list_registered_clients(
                {"id": "u", "role": "consultor", "email": "u@x.pt"},
            )
        return {c["id"]: c for c in resultado["clients"]}

    async def test_o_processo_recuperado_pelo_client_id_aparece(self, fake_async_db):
        await fake_async_db.clients.insert_one({
            "id": "c-1", "nome": "Sem lista", "registration_completed": True, CAMPO_REDE: REDE_POWER,
        })
        await fake_async_db.processes.insert_one({
            "id": "p-1", "client_id": "c-1", "status": "pre_registo", "process_number": "PROC-9",
            CAMPO_REDE: REDE_POWER,
        })
        cliente = (await self._listar(fake_async_db))["c-1"]
        assert cliente["has_process"] is True
        assert [p["id"] for p in cliente["processes"]] == ["p-1"]

    async def test_um_processo_de_outra_rede_nao_e_recuperado(self, fake_async_db):
        await fake_async_db.clients.insert_one({
            "id": "c-2", "nome": "Outro", "registration_completed": True, CAMPO_REDE: REDE_POWER,
        })
        await fake_async_db.processes.insert_one({
            "id": "p-2", "client_id": "c-2", "status": "pre_registo", CAMPO_REDE: REDE_DOMUS,
        })
        cliente = (await self._listar(fake_async_db))["c-2"]
        assert cliente["has_process"] is False
        assert cliente["processes"] == []

    async def test_sem_processo_nenhum_continua_sem_processo(self, fake_async_db):
        """Contraprova: a recuperação não inventa processos."""
        await fake_async_db.clients.insert_one({
            "id": "c-3", "nome": "Lead", "registration_completed": True, CAMPO_REDE: REDE_POWER,
        })
        assert (await self._listar(fake_async_db))["c-3"]["has_process"] is False


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


class TestOsProcessosDaLinhaSaoDoAmbito:
    """«Registos Clientes» devolvia, em cada linha, processos de OUTRA rede (404 ao abrir).

    O QA-6 escopou só a recuperação por `client_id`; o ramo principal — os `process_ids` do
    próprio cliente — lia `db.processes` pelo id, sem condição de rede. Um cliente da Power cujo
    processo foi movido para a Domus («Alterar Empresa» move processos, não a ficha) mostrava
    esse processo na linha, e o clique ia para `/process/{id}`, que responde 404 uniforme.
    """

    async def _listar(self, fake_async_db, rede=REDE_POWER, **kwargs):
        from services import client_registered as modulo

        pool = build_pool_scope_condition(_scope(rede))
        estrita = build_network_scope_condition(_scope(rede))
        proc = build_network_scope_condition(_scope(rede))
        with patch.object(modulo, "db", fake_async_db), \
                patch.object(modulo, "build_tenant_pool_condition", AsyncMock(return_value=pool)), \
                patch.object(modulo, "build_tenant_condition", AsyncMock(return_value=estrita)), \
                patch.object(modulo, "build_tenant_process_condition", AsyncMock(return_value=proc)):
            resultado = await modulo.run_list_registered_clients(
                {"id": "u", "role": "consultor", "email": "u@x.pt"}, **kwargs,
            )
        return {c["id"]: c for c in resultado["clients"]}

    async def _semear(self, fake_async_db, *, ids, processos):
        await fake_async_db.clients.insert_one({
            "id": "c-1", "nome": "Cliente Power", "registration_completed": True,
            CAMPO_REDE: REDE_POWER, "process_ids": ids,
        })
        for p in processos:
            await fake_async_db.processes.insert_one({"client_id": "c-1", **p})

    async def test_um_processo_de_outra_rede_nao_aparece_na_linha(self, fake_async_db):
        await self._semear(fake_async_db, ids=["p-pow", "p-dom"], processos=[
            {"id": "p-pow", "status": "pre_registo", CAMPO_REDE: REDE_POWER},
            {"id": "p-dom", "status": "pre_registo", CAMPO_REDE: REDE_DOMUS},
        ])
        linha = (await self._listar(fake_async_db))["c-1"]
        assert [p["id"] for p in linha["processes"]] == ["p-pow"]

    async def test_se_so_ha_processos_de_outra_rede_a_linha_diz_sem_processo(self, fake_async_db):
        """Sem isto a linha dizia «Com processo» e não havia nada para abrir (nem para criar).

        Vê-se com `include_ghosts`: sem processo principal VISÍVEL o cliente é, por regra, um
        «fantasma» e a lista normal já o esconde (o seu único negócio é de outra rede).
        """
        await self._semear(fake_async_db, ids=["p-dom"], processos=[
            {"id": "p-dom", "status": "pre_registo", CAMPO_REDE: REDE_DOMUS},
        ])
        linha = (await self._listar(fake_async_db, include_ghosts=True))["c-1"]
        assert linha["processes"] == []
        assert linha["has_process"] is False
        assert linha["process_count"] == 0

    async def test_o_cliente_so_com_processo_alheio_sai_da_lista_normal(self, fake_async_db):
        await self._semear(fake_async_db, ids=["p-dom"], processos=[
            {"id": "p-dom", "status": "pre_registo", CAMPO_REDE: REDE_DOMUS},
        ])
        assert "c-1" not in await self._listar(fake_async_db)

    async def test_um_processo_avancado_de_outra_rede_nao_esconde_o_lead(self, fake_async_db):
        """A regra «já passou da fase inicial → sai dos Registos» olhava para o processo ALHEIO."""
        await self._semear(fake_async_db, ids=["p-pow", "p-dom"], processos=[
            {"id": "p-pow", "status": "pre_registo", CAMPO_REDE: REDE_POWER},
            {"id": "p-dom", "status": "concluido", CAMPO_REDE: REDE_DOMUS},
        ])
        linha = (await self._listar(fake_async_db)).get("c-1")
        assert linha is not None
        assert [p["id"] for p in linha["processes"]] == ["p-pow"]

    async def test_contraprova_o_processo_avancado_da_PROPRIA_rede_continua_a_esconder(self, fake_async_db):
        await self._semear(fake_async_db, ids=["p-pow"], processos=[
            {"id": "p-pow", "status": "concluido", CAMPO_REDE: REDE_POWER},
        ])
        assert "c-1" not in await self._listar(fake_async_db)

    async def test_a_triagem_nao_conta_processos_de_outra_rede(self, fake_async_db):
        """A consulta da triagem (tecto de 500) varria os processos de TODAS as redes."""
        await fake_async_db.clients.insert_one({
            "id": "c-2", "nome": "Alheio", "registration_completed": True, CAMPO_REDE: REDE_POWER,
        })
        await fake_async_db.processes.insert_one({
            "id": "p-x", "client_id": "c-2", "status": "pre_registo", CAMPO_REDE: REDE_DOMUS,
        })
        linha = (await self._listar(fake_async_db, triage_mode=True)).get("c-2")
        assert linha is None or linha["triage_status"] is None

    async def test_a_consulta_dos_processos_leva_a_condicao_de_rede(self, fake_async_db):
        """Nível abaixo: afirma sobre o FILTRO que sai para a colecção, não só sobre o resultado."""
        from services import client_registered as modulo

        vistos = []
        original = fake_async_db.processes.find

        def espia(filtro, *a, **k):
            vistos.append(filtro)
            return original(filtro, *a, **k)

        fake_async_db.processes.find = espia
        await self._semear(fake_async_db, ids=["p-pow"], processos=[
            {"id": "p-pow", "status": "pre_registo", CAMPO_REDE: REDE_POWER},
        ])
        await self._listar(fake_async_db, triage_mode=True)
        assert vistos, "nenhuma consulta a processos foi observada"
        sem_rede = [f for f in vistos if CAMPO_REDE not in repr(f)]
        assert not sem_rede, f"consultas a processos SEM condição de rede: {sem_rede}"
