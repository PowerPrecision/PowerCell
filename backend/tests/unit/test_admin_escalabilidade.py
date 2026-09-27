"""
Escalabilidade e isolamento do Painel de Administração (ponto 11).

A DECISÃO DO DONO (ALERTA VERMELHO)
  "O facto de um utilizador ser 'Admin' significa que é Admin da sua
  REDE, não do sistema global. Um Admin da Domus só pode ver a(s)
  empresa(s) que partilham o seu `network_id` e os utilizadores que
  pertencem a essas empresas."

O N+1 QUE ISTO MATA
  `run_list_companies` chamava `_count_company_users(...)` DENTRO do
  ciclo: uma query por empresa. 50 empresas = 51 idas à base; 200 = 201.
  Passa a uma agregação só, com `$group`.

O TECTO SILENCIOSO
  `.to_list(200)` sem paginação e sem dizer que truncou: à empresa 201 a
  UI respondia que ela não existe. Agora há `page`/`size` e um `total`
  contado à parte — o cliente sabe que há mais.

A PESQUISA DOS UTILIZADORES ERA NO CLIENTE
  `filteredUsers` filtrava em memória sobre `name`/`email`, depois de
  trazer a tabela inteira. Não pesquisava por EMPRESA, que é como um
  admin procura alguém.

PORQUE É QUE O UTILIZADOR SE FILTRA PELAS EMPRESAS, E NÃO PELA REDE
  `users` não tem `network_id`. O que os liga à rede são os UCRs
  (`user_company_roles.company_id`) e o campo legado `users.company`,
  que é o NOME. O âmbito resolve-se em dois passos: rede → empresas →
  utilizadores dessas empresas. Filtrar `users` por `network_id`
  directamente devolveria SEMPRE vazio — e um painel vazio parece uma
  base de dados vazia, não um filtro errado.
"""
import pytest


class TestContagemDeUtilizadoresSemNMaisUm:
    @pytest.mark.asyncio
    async def test_conta_por_empresa_numa_so_agregacao(self, fake_async_db, monkeypatch):
        from services import companies_crud_api_list as mod

        await fake_async_db.user_company_roles.insert_one({"company_id": "c1"})
        await fake_async_db.user_company_roles.insert_one({"company_id": "c1"})
        await fake_async_db.user_company_roles.insert_one({"company_id": "c2"})
        monkeypatch.setattr(mod, "db", fake_async_db)

        contagens = await mod.contar_utilizadores_por_empresa(
            [{"id": "c1", "name": "Power"}, {"id": "c2", "name": "Domus"}]
        )
        assert contagens["c1"] == 2
        assert contagens["c2"] == 1

    @pytest.mark.asyncio
    async def test_uma_empresa_sem_ninguem_conta_zero(self, fake_async_db, monkeypatch):
        from services import companies_crud_api_list as mod

        monkeypatch.setattr(mod, "db", fake_async_db)
        contagens = await mod.contar_utilizadores_por_empresa([{"id": "c1", "name": "X"}])
        assert contagens.get("c1", 0) == 0

    @pytest.mark.asyncio
    async def test_conta_tambem_pelo_NOME_legado(self, fake_async_db, monkeypatch):
        """Os UCRs antigos guardam `company_name` em vez de `company_id`.
        Ignorá-los diria "0 utilizadores" numa empresa cheia."""
        from services import companies_crud_api_list as mod

        await fake_async_db.user_company_roles.insert_one({"company_name": "Power"})
        monkeypatch.setattr(mod, "db", fake_async_db)

        contagens = await mod.contar_utilizadores_por_empresa([{"id": "c1", "name": "Power"}])
        assert contagens["c1"] == 1

    @pytest.mark.asyncio
    async def test_sem_empresas_nao_vai_a_base(self, fake_async_db, monkeypatch):
        from services import companies_crud_api_list as mod

        monkeypatch.setattr(mod, "db", fake_async_db)
        assert await mod.contar_utilizadores_por_empresa([]) == {}


class TestIsolamentoDasEmpresas:
    @pytest.mark.asyncio
    async def test_um_admin_so_ve_as_empresas_da_sua_rede(
        self, fake_async_db, monkeypatch
    ):
        from services import companies_crud_api_list as mod

        await fake_async_db.companies.insert_one(
            {"id": "c-power", "name": "Power", "network_id": "grupo_power_precision"}
        )
        await fake_async_db.companies.insert_one(
            {"id": "c-domus", "name": "Domus", "network_id": "rede_domus"}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "build_tenant_condition", _condicao("rede_domus"))

        resposta = await mod.run_list_companies(user={"id": "admin-domus"})
        assert [c.name for c in resposta.companies] == ["Domus"]

    @pytest.mark.asyncio
    async def test_contraprova_a_outra_rede_ve_a_sua(self, fake_async_db, monkeypatch):
        from services import companies_crud_api_list as mod

        await fake_async_db.companies.insert_one(
            {"id": "c-power", "name": "Power", "network_id": "grupo_power_precision"}
        )
        await fake_async_db.companies.insert_one(
            {"id": "c-domus", "name": "Domus", "network_id": "rede_domus"}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(
            mod, "build_tenant_condition", _condicao("grupo_power_precision")
        )

        resposta = await mod.run_list_companies(user={"id": "admin-power"})
        assert [c.name for c in resposta.companies] == ["Power"]

    @pytest.mark.asyncio
    async def test_a_pesquisa_nao_atravessa_a_rede(self, fake_async_db, monkeypatch):
        """O caso perigoso: pesquisar pelo nome exacto da empresa da
        outra rede não a pode fazer aparecer."""
        from services import companies_crud_api_list as mod

        await fake_async_db.companies.insert_one(
            {"id": "c-power", "name": "Power", "network_id": "grupo_power_precision"}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "build_tenant_condition", _condicao("rede_domus"))

        resposta = await mod.run_list_companies(search="Power", user={"id": "admin-domus"})
        assert resposta.companies == []


class TestPaginacaoDasEmpresas:
    @pytest.mark.asyncio
    async def test_devolve_a_pagina_pedida_e_o_total_real(
        self, fake_async_db, monkeypatch
    ):
        """O `.to_list(200)` truncava em silêncio: à empresa 201 a UI
        respondia que ela não existe."""
        from services import companies_crud_api_list as mod

        for i in range(25):
            await fake_async_db.companies.insert_one(
                {"id": f"c{i:02d}", "name": f"Empresa {i:02d}", "network_id": "r"}
            )
        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "build_tenant_condition", _condicao("r"))

        resposta = await mod.run_list_companies(page=2, size=10, user={"id": "a"})
        assert len(resposta.companies) == 10
        assert resposta.total == 25
        assert resposta.companies[0].name == "Empresa 10"

    @pytest.mark.asyncio
    async def test_o_total_e_o_do_AMBITO_e_nao_o_da_coleccao(
        self, fake_async_db, monkeypatch
    ):
        """Um total global diria à Domus quantas empresas a Power tem."""
        from services import companies_crud_api_list as mod

        await fake_async_db.companies.insert_one(
            {"id": "c1", "name": "Domus", "network_id": "rede_domus"}
        )
        for i in range(5):
            await fake_async_db.companies.insert_one(
                {"id": f"p{i}", "name": f"Power {i}", "network_id": "outra"}
            )
        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "build_tenant_condition", _condicao("rede_domus"))

        resposta = await mod.run_list_companies(user={"id": "a"})
        assert resposta.total == 1


class TestAmbitoDosUtilizadores:
    @pytest.mark.asyncio
    async def test_resolve_as_empresas_da_rede_antes_de_filtrar(
        self, fake_async_db, monkeypatch
    ):
        """`users` não tem `network_id`: o que os liga à rede são os UCRs
        e o campo legado `users.company`, que é o NOME. Filtrar `users`
        por `network_id` devolveria sempre vazio."""
        from services import admin_users_scope as mod

        await fake_async_db.companies.insert_one(
            {"id": "c-domus", "name": "Domus", "network_id": "rede_domus"}
        )
        await fake_async_db.companies.insert_one(
            {"id": "c-power", "name": "Power", "network_id": "outra"}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        # `empresas_do_ambito` resolve o âmbito COMPLETO (precisa do
        # `inclui_rede_de_omissao` para as contas órfãs), por isso
        # falseia-se o scope e não só a condição.
        from services.tenant_network import TenantScope

        async def scope(_user):
            return TenantScope(
                network_ids=("rede_domus",), inclui_rede_de_omissao=False
            )

        monkeypatch.setattr(mod, "resolve_tenant_scope", scope)
        monkeypatch.setattr(
            mod, "build_network_scope_condition",
            lambda _s: {"network_id": {"$in": ["rede_domus"]}},
        )

        ambito = await mod.empresas_do_ambito({"id": "admin-domus"})
        assert ambito.ids == ["c-domus"]
        assert ambito.nomes == ["Domus"]

    @pytest.mark.asyncio
    async def test_a_query_apanha_o_UCR_e_o_campo_legado(
        self, fake_async_db, monkeypatch
    ):
        from services import admin_users_scope as mod

        await fake_async_db.user_company_roles.insert_one(
            {"user_id": "u-ucr", "company_id": "c-domus"}
        )
        await fake_async_db.users.insert_one({"id": "u-ucr", "name": "Ana", "email": "a@x.pt"})
        await fake_async_db.users.insert_one(
            {"id": "u-legado", "name": "Bruno", "email": "b@x.pt", "company": "Domus"}
        )
        await fake_async_db.users.insert_one(
            {"id": "u-fora", "name": "Carla", "email": "c@x.pt", "company": "Power"}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        query = await mod.build_users_scope_query(
            mod.EmpresasDoAmbito(ids=["c-domus"], nomes=["Domus"], fechado=True, inclui_sem_empresa=False)
        )
        encontrados = await fake_async_db.users.find(query).to_list(50)
        ids = sorted(u["id"] for u in encontrados)
        assert ids == ["u-legado", "u-ucr"]

    @pytest.mark.asyncio
    async def test_um_ambito_sem_empresas_nao_devolve_tudo(
        self, fake_async_db, monkeypatch
    ):
        """Fail-closed: um âmbito vazio tem de devolver ZERO, não a
        colecção inteira. É a regra do `CONDICAO_IMPOSSIVEL` do Lote 4."""
        from services import admin_users_scope as mod

        await fake_async_db.users.insert_one({"id": "u1", "name": "Ana"})
        monkeypatch.setattr(mod, "db", fake_async_db)

        query = await mod.build_users_scope_query(
            mod.EmpresasDoAmbito(ids=[], nomes=[], fechado=True, inclui_sem_empresa=False)
        )
        assert await fake_async_db.users.find(query).to_list(50) == []

    @pytest.mark.asyncio
    async def test_um_ambito_aberto_ve_tudo(self, fake_async_db, monkeypatch):
        """Contraprova: sem `TENANT_DEFAULT_NETWORK_ID` definido (dev/CI),
        o comportamento anterior mantém-se — senão um deploy esvaziava o
        painel de administração de toda a gente."""
        from services import admin_users_scope as mod

        await fake_async_db.users.insert_one({"id": "u1", "name": "Ana"})
        monkeypatch.setattr(mod, "db", fake_async_db)

        query = await mod.build_users_scope_query(
            mod.EmpresasDoAmbito(ids=[], nomes=[], fechado=False, inclui_sem_empresa=False)
        )
        assert len(await fake_async_db.users.find(query).to_list(50)) == 1


class TestPesquisaServerSide:
    def test_pesquisa_por_nome_email_e_empresa(self):
        from services.admin_users_scope import build_users_search_condition

        cond = build_users_search_condition("ana")
        campos = str(cond)
        assert "name" in campos and "email" in campos and "company" in campos

    def test_sem_termo_nao_ha_condicao(self):
        from services.admin_users_scope import build_users_search_condition

        assert build_users_search_condition("") is None
        assert build_users_search_condition("   ") is None
        assert build_users_search_condition(None) is None

    def test_o_termo_e_escapado(self):
        """Um `.` ou `(` num termo de pesquisa é regex, não texto — sem
        escape, pesquisar "a.b" devolvia "axb"."""
        from services.admin_users_scope import build_users_search_condition

        cond = build_users_search_condition("a.b(")
        assert "\\\\." in str(cond) or "\\." in str(cond)


def _condicao(rede: str):
    async def _build(_user):
        return {"network_id": {"$in": [rede]}}

    return _build


class TestContasOrfasNaoDesaparecem:
    """Uma conta SEM empresa nenhuma não pode sumir do painel.

    Lacuna do meu próprio desenho, apanhada antes de sair: filtrar
    `users` pelas empresas do âmbito deixava de fora quem não tem
    empresa — tipicamente contas de administração antigas, exactamente
    as que a Atribuição Rápida do Lote 4 veio impedir de nascer. E o
    defeito fechava-se sobre si mesmo: uma conta que desaparece do
    painel nunca mais pode ser associada a uma empresa, porque deixa de
    se ver.

    A pilha por carimbar segue a MESMA regra dos documentos: pertence a
    quem detém a rede de omissão.
    """

    @pytest.mark.asyncio
    async def test_quem_detem_a_rede_de_omissao_ve_as_contas_orfas(
        self, fake_async_db, monkeypatch
    ):
        from services import admin_users_scope as mod

        await fake_async_db.users.insert_one({"id": "u-orfa", "name": "Sem empresa"})
        await fake_async_db.users.insert_one(
            {"id": "u-domus", "name": "Ana", "company": "Domus"}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        query = await mod.build_users_scope_query(
            mod.EmpresasDoAmbito(
                ids=["c-domus"], nomes=["Domus"], fechado=True, inclui_sem_empresa=True
            )
        )
        ids = sorted(u["id"] for u in await fake_async_db.users.find(query).to_list(50))
        assert ids == ["u-domus", "u-orfa"]

    @pytest.mark.asyncio
    async def test_quem_NAO_a_detem_nao_ve_as_orfas(self, fake_async_db, monkeypatch):
        """Contraprova: se as órfãs fossem visíveis a toda a gente, o
        ramo seria um buraco na parede em vez de uma regra."""
        from services import admin_users_scope as mod

        await fake_async_db.users.insert_one({"id": "u-orfa", "name": "Sem empresa"})
        await fake_async_db.users.insert_one(
            {"id": "u-domus", "name": "Ana", "company": "Domus"}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        query = await mod.build_users_scope_query(
            mod.EmpresasDoAmbito(
                ids=["c-domus"], nomes=["Domus"], fechado=True, inclui_sem_empresa=False
            )
        )
        ids = [u["id"] for u in await fake_async_db.users.find(query).to_list(50)]
        assert ids == ["u-domus"]

    @pytest.mark.asyncio
    async def test_um_ambito_vazio_que_inclua_orfas_devolve_so_orfas(
        self, fake_async_db, monkeypatch
    ):
        """Em dev/CI sem `TENANT_DEFAULT_NETWORK_ID` é este o caso: nada
        está carimbado e o painel continua a mostrar toda a gente."""
        from services import admin_users_scope as mod

        await fake_async_db.users.insert_one({"id": "u1", "name": "Ana"})
        await fake_async_db.users.insert_one({"id": "u2", "name": "Bruno"})
        monkeypatch.setattr(mod, "db", fake_async_db)

        query = await mod.build_users_scope_query(
            mod.EmpresasDoAmbito(ids=[], nomes=[], fechado=True, inclui_sem_empresa=True)
        )
        assert len(await fake_async_db.users.find(query).to_list(50)) == 2
