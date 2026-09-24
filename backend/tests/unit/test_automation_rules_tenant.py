"""
Regras de automação pertencem à REDE (Lote 5, Secção B, ponto 13).

A DECISÃO DO DONO
  "A Domus é uma ilha. O Administrador da Domus nunca pode ver nem tocar
  nas regras do grupo Power/Precision, e vice-versa."

O QUE ESTAVA
  `list_rules` fazia `db.automation_rules.find(query)` sem filtro
  nenhum, e `create_rule` não carimbava nada. Ser "admin" significava
  ser admin do SISTEMA INTEIRO.

  E o efeito atravessa mesmo a fronteira: uma regra não é um registo
  decorativo — cria TAREFAS em processos. Uma regra da rede A a disparar
  sobre um processo da rede B punha trabalho de uma empresa na lista de
  outra.

PORQUE É QUE O MOTOR NÃO LEVA FILTRO
  `check_trigger_conditions` (o caminho de EXECUÇÃO) corre a partir de
  um processo concreto, sem utilizador — não há âmbito de sessão para
  aplicar. O isolamento tem de ir pelo lado do DADO: a regra é filtrada
  pela rede do PROCESSO que a dispara, não pela de quem a lê. Misturar
  os dois caminhos daria um motor que não dispara em background.

A PILHA POR CARIMBAR
  As regras que já existem não têm `network_id`. O
  `build_network_scope_condition` já trata disso: quem tem
  `inclui_rede_de_omissao` continua a vê-las. Esconder as regras
  actuais de toda a gente seria desligar as automações em produção com
  um deploy.
"""
import pytest


def _regra(**extra):
    base = {
        "id": "r1",
        "name": "Ao indexar, pedir IRS",
        "trigger": "process_status_changed",
        "trigger_config": {"target_status": "fase_documental"},
        "action": "create_task",
        "action_config": {"title": "Pedir IRS"},
        "is_active": True,
    }
    base.update(extra)
    return base


class TestListagemIsolada:
    @pytest.mark.asyncio
    async def test_uma_rede_nao_ve_as_regras_da_outra(self, fake_async_db, monkeypatch):
        from services import workflow_engine as mod

        await fake_async_db.automation_rules.insert_one(
            _regra(id="r-power", network_id="grupo_power_precision")
        )
        await fake_async_db.automation_rules.insert_one(
            _regra(id="r-domus", network_id="rede_domus")
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        regras = await mod.list_rules(tenant_condition={"network_id": {"$in": ["rede_domus"]}})
        assert [r["id"] for r in regras] == ["r-domus"]

    @pytest.mark.asyncio
    async def test_sem_condicao_devolve_tudo(self, fake_async_db, monkeypatch):
        """Contraprova: o motor de execução chama sem condição e tem de
        continuar a ver as regras todas."""
        from services import workflow_engine as mod

        await fake_async_db.automation_rules.insert_one(_regra(id="r-a", network_id="a"))
        await fake_async_db.automation_rules.insert_one(_regra(id="r-b", network_id="b"))
        monkeypatch.setattr(mod, "db", fake_async_db)

        assert len(await mod.list_rules()) == 2

    @pytest.mark.asyncio
    async def test_active_only_continua_a_funcionar_com_o_filtro(
        self, fake_async_db, monkeypatch
    ):
        from services import workflow_engine as mod

        await fake_async_db.automation_rules.insert_one(
            _regra(id="r-on", network_id="a", is_active=True)
        )
        await fake_async_db.automation_rules.insert_one(
            _regra(id="r-off", network_id="a", is_active=False)
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        regras = await mod.list_rules(
            active_only=True, tenant_condition={"network_id": {"$in": ["a"]}}
        )
        assert [r["id"] for r in regras] == ["r-on"]


class TestCarimboNaCriacao:
    @pytest.mark.asyncio
    async def test_a_regra_nova_nasce_carimbada(self, fake_async_db, monkeypatch):
        from services import automation_api_rules as mod

        monkeypatch.setattr(mod, "db", fake_async_db, raising=False)

        async def carimbo(_user, **_kwargs):
            return {"network_id": "rede_domus", "company_id": "c-domus"}

        monkeypatch.setattr(mod, "resolve_tenant_stamp", carimbo)
        criadas = {}

        async def criar(data, user):
            criadas.update(data)
            return {**data, "id": "novo"}

        monkeypatch.setattr(mod, "create_rule", criar)

        await mod.run_create_rule(
            mod.RuleCreate(
                name="X", trigger="process_status_changed", action="create_task",
            ),
            {"id": "u1", "company": "Domus"},
        )
        assert criadas.get("network_id") == "rede_domus"

    @pytest.mark.asyncio
    async def test_sem_contexto_de_empresa_nao_inventa_rede(
        self, fake_async_db, monkeypatch
    ):
        """Carimbar a rede errada é pior do que não carimbar: o documento
        ficaria visível à rede errada para SEMPRE."""
        from services import automation_api_rules as mod

        async def sem_carimbo(_user, **_kwargs):
            return None

        monkeypatch.setattr(mod, "resolve_tenant_stamp", sem_carimbo)
        criadas = {}

        async def criar(data, user):
            criadas.update(data)
            return {**data, "id": "novo"}

        monkeypatch.setattr(mod, "create_rule", criar)

        await mod.run_create_rule(
            mod.RuleCreate(
                name="X", trigger="process_status_changed", action="create_task",
            ),
            {"id": "u1"},
        )
        assert "network_id" not in criadas


class TestEditarEApagarSaoGuardados:
    @pytest.mark.asyncio
    async def test_nao_se_edita_a_regra_de_outra_rede(self, fake_async_db, monkeypatch):
        from fastapi import HTTPException
        from services import automation_api_rules as mod

        await fake_async_db.automation_rules.insert_one(
            _regra(id="r-power", network_id="grupo_power_precision")
        )
        monkeypatch.setattr(mod, "db", fake_async_db, raising=False)
        monkeypatch.setattr(mod, "build_tenant_condition", _condicao("rede_domus"))

        with pytest.raises(HTTPException) as erro:
            await mod.run_update_rule(
                "r-power", mod.RuleUpdate(is_active=False), {"id": "admin-domus"}
            )
        # 404 e não 403: confirmar que existe já diria à Domus que a
        # Power tem uma regra com aquele id.
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_nao_se_apaga_a_regra_de_outra_rede(self, fake_async_db, monkeypatch):
        from fastapi import HTTPException
        from services import automation_api_rules as mod

        await fake_async_db.automation_rules.insert_one(
            _regra(id="r-power", network_id="grupo_power_precision")
        )
        monkeypatch.setattr(mod, "db", fake_async_db, raising=False)
        monkeypatch.setattr(mod, "build_tenant_condition", _condicao("rede_domus"))

        with pytest.raises(HTTPException) as erro:
            await mod.run_delete_rule("r-power", {"id": "admin-domus"})
        assert erro.value.status_code == 404

        # E continua lá: um 404 que apagasse na mesma seria pior.
        assert await fake_async_db.automation_rules.find_one({"id": "r-power"})

    @pytest.mark.asyncio
    async def test_contraprova_a_propria_rede_edita_e_apaga(
        self, fake_async_db, monkeypatch
    ):
        """Sem isto, um guarda que recusasse SEMPRE passava nos dois
        testes acima e o ecrã ficava inútil."""
        from services import automation_api_rules as mod

        await fake_async_db.automation_rules.insert_one(
            _regra(id="r-domus", network_id="rede_domus")
        )
        from services import workflow_engine as motor

        monkeypatch.setattr(mod, "db", fake_async_db, raising=False)
        # `delete_rule` vive no `workflow_engine` e tem a SUA referência
        # ao proxy: sem este segundo patch, o teste apanhava o Mongo real
        # e rebentava com "Event loop is closed". É a regra do AGENTS.md
        # sobre `from database import db` ao nível do módulo.
        monkeypatch.setattr(motor, "db", fake_async_db)
        monkeypatch.setattr(mod, "build_tenant_condition", _condicao("rede_domus"))

        async def actualizar(rule_id, data):
            return {"id": rule_id, **data}

        monkeypatch.setattr(mod, "update_rule", actualizar)
        resultado = await mod.run_update_rule(
            "r-domus", mod.RuleUpdate(is_active=False), {"id": "admin-domus"}
        )
        assert resultado["id"] == "r-domus"

        await mod.run_delete_rule("r-domus", {"id": "admin-domus"})
        assert await fake_async_db.automation_rules.find_one({"id": "r-domus"}) is None

    @pytest.mark.asyncio
    async def test_uma_regra_por_carimbar_continua_acessivel(
        self, fake_async_db, monkeypatch
    ):
        """As regras que já existem não têm `network_id`. Escondê-las de
        toda a gente seria desligar as automações com um deploy."""
        from services import automation_api_rules as mod

        await fake_async_db.automation_rules.insert_one(_regra(id="r-antiga"))
        monkeypatch.setattr(mod, "db", fake_async_db, raising=False)

        async def condicao(_user):
            return {
                "$or": [
                    {"network_id": {"$in": ["rede_domus"]}},
                    {"network_id": {"$in": [None, ""]}},
                ]
            }

        monkeypatch.setattr(mod, "build_tenant_condition", condicao)

        async def actualizar(rule_id, data):
            return {"id": rule_id, **data}

        monkeypatch.setattr(mod, "update_rule", actualizar)
        assert await mod.run_update_rule(
            "r-antiga", mod.RuleUpdate(is_active=False), {"id": "admin"}
        )


def _condicao(rede: str):
    async def _build(_user):
        return {"network_id": {"$in": [rede]}}

    return _build
