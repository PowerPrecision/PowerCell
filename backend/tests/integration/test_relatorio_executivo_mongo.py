"""O motor do relatório executivo contra um MongoDB REAL (Bloco 4, pontos 13 e 16).

Os testes unitários (`tests/unit/test_relatorio_executivo.py`) provam a lógica
com a costura de acesso substituída. Aqui prova-se o que um duplo NÃO pode
provar — a semântica das pipelines e o uso de índices:

* `$unwind` sobre `assigned_to` (inclusive o valor escalar legado);
* `$substrBytes` sobre datas ISO guardadas como texto;
* a ordem dos dois `$group` (processos distintos vs mudanças);
* o período semiaberto — o relatório antigo ignorava o fim;
* **nenhuma agregação faz COLLSCAN**: é a prova de que o relatório não
  varre `history` nem `tasks` inteiras, e de que os índices declarados em
  `db_indexes.py` são os que a consulta usa.

Os números esperados foram contados À MÃO a partir dos documentos semeados.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

import services.executive_report as er

SEMANA = ("2026-10-05", "2026-10-11")  # segunda a domingo
DENTRO = "2026-10-07T10:00:00+00:00"
DENTRO_2 = "2026-10-08T09:30:00+00:00"
ANTES = "2026-10-04T23:59:59+00:00"
DEPOIS = "2026-10-12T00:00:00+00:00"  # a primeira fracção da semana seguinte


@pytest_asyncio.fixture
async def base():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    nome = f"test_relatorio_exec_{uuid.uuid4().hex[:8]}"
    bd = cliente[nome]
    from services.db_indexes import create_indexes

    await create_indexes(bd)
    er.limpar_cache()
    yield bd
    await cliente.drop_database(nome)
    cliente.close()
    er.limpar_cache()


def _h(uid, pid, quando, campo="status", antigo="a", novo="b", acao="Alterou estado"):
    return {"id": str(uuid.uuid4()), "user_id": uid, "process_id": pid, "action": acao,
            "field": campo, "old_value": antigo, "new_value": novo, "created_at": quando}


def _t(tid, atribuida, criada="2026-10-01T09:00:00+00:00", prazo=None, feita=None,
       por=None, apagada=False, **extra):
    return {"id": tid, "title": tid, "assigned_to": atribuida, "created_at": criada,
            "due_date": prazo, "completed": feita is not None,
            "completed_at": feita, "completed_by": por,
            **({"is_deleted": True} if apagada else {}), **extra}


async def _semear(bd):
    await bd.users.insert_many([
        {"id": "u-ana", "name": "Ana", "email": "ana@x.pt", "role": "consultor", "is_active": True},
        {"id": "u-rui", "name": "Rui", "email": "rui@x.pt", "role": "intermediario", "is_active": True},
        {"id": "u-ix", "name": "Xavier", "email": "ix@x.pt", "role": "indexacao", "is_active": True},
        {"id": "u-zé", "name": "Zé", "email": "ze@x.pt", "role": "diretor", "is_active": True,
         "track_history": False},
        {"id": "u-fora", "name": "Fora", "email": "f@x.pt", "role": "consultor", "is_active": False},
    ])
    await bd.history.insert_many([
        # Ana: p1 duas vezes e p2 uma — 3 mudanças, 2 processos distintos.
        _h("u-ana", "p1", DENTRO, novo="fase_documental"),
        _h("u-ana", "p1", DENTRO_2, antigo="fase_documental", novo="aprovado"),
        _h("u-ana", "p2", DENTRO_2, campo="status", acao="Moveu processo", novo="aprovado"),
        # Fora do período: antes, depois (o relatório antigo contava este).
        _h("u-ana", "p3", ANTES),
        _h("u-ana", "p3", DEPOIS),
        # Não é uma fase: um campo qualquer.
        _h("u-ana", "p4", DENTRO, campo="nif", acao="Alterou dados"),
        # Rui: uma.
        _h("u-rui", "p5", DENTRO, novo="aprovado"),
        # Um utilizador fora do âmbito pedido.
        _h("u-estranho", "p6", DENTRO),
    ])
    await bd.tasks.insert_many([
        # Em aberto, atribuída às duas pessoas, prazo no passado → pendente+atrasada para cada.
        _t("t-aberta", ["u-ana", "u-rui"], prazo="2026-10-03T12:00:00+00:00"),
        # Concluída pela Ana na semana (atribuída a ela).
        _t("t-ana", ["u-ana"], feita=DENTRO, por="u-ana", prazo="2026-10-06"),
        # Concluída pelo Rui na semana, mas atribuída à Ana: conta ao Rui (quem concluiu).
        _t("t-rui", ["u-ana"], feita=DENTRO_2, por="u-rui"),
        # Criada DEPOIS do fim da semana: não existia no fim dela.
        _t("t-futura", ["u-ana"], criada=DEPOIS),
        # Concluída DEPOIS do fim: no fim da semana ainda estava pendente.
        _t("t-tardia", ["u-rui"], feita=DEPOIS, por="u-rui", prazo="2026-10-09"),
        # Apagada: nunca conta.
        _t("t-apagada", ["u-ana"], apagada=True),
        # Prazo SÓ com data, no último dia da semana: vale até ao fim do dia → não atrasada.
        _t("t-hoje", ["u-rui"], prazo="2026-10-12"),
        # Legado: `assigned_to` escalar, não lista.
        _t("t-escalar", "u-ana", prazo="2026-10-01"),
        # Concluída por quem não está no filtro.
        _t("t-estranho", ["u-estranho"], feita=DENTRO, por="u-estranho"),
        # Sem prazo e prazo que não é texto: não pode rebentar a agregação.
        _t("t-sem-prazo", ["u-ana"], prazo=None),
        _t("t-prazo-estranho", ["u-ana"], prazo=12345),
    ])


def _filtros(**kw):
    return er.Filtros(er.construir_periodo(*SEMANA), **kw)


AMBITO = er.Ambito(chave="integracao")
#: «Agora» fixo, DEPOIS da semana: os números não dependem do relógio da máquina.
AGORA = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _linha(r, uid):
    return next(u for u in r["users"] if u["user_id"] == uid)


class TestOsNumeros:
    @pytest.mark.asyncio
    async def test_a_semana_tem_os_numeros_contados_a_mao(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)

        ana, rui = _linha(r, "u-ana"), _linha(r, "u-rui")

        # Mudanças de fase: só as DENTRO e só as de estado (não o `nif`).
        assert (ana["phase_changes"], ana["processes_moved"]) == (3, 2)
        assert (rui["phase_changes"], rui["processes_moved"]) == (1, 1)

        # Concluídas: a quem concluiu. A `t-rui` (atribuída à Ana) é do Rui.
        assert ana["tasks_completed"] == 1
        assert rui["tasks_completed"] == 1

        # Pendentes no FIM da semana, por atribuição:
        #   Ana: aberta, futura(NÃO: criada depois), tardia(não é dela), escalar, sem-prazo,
        #        prazo-estranho, t-rui? (concluída dentro → não), t-ana (concluída → não)
        #        = aberta + escalar + sem-prazo + prazo-estranho = 4
        assert ana["tasks_pending"] == 4
        #   Rui: aberta + tardia (concluída só depois do fim) + hoje = 3
        assert rui["tasks_pending"] == 3

        # Atrasadas (prazo antes do fim da semana, ainda abertas no fim):
        #   Ana: aberta (03/10) + escalar (01/10) = 2 ; Rui: aberta (03/10) + tardia (09/10) = 2
        #   (o prazo «2026-10-12» da `t-hoje` NÃO está atrasado: vale até ao fim do dia 12,
        #    e a semana acaba no dia 11 → limite 2026-10-12, `<` estrito)
        assert ana["tasks_overdue"] == 2
        assert rui["tasks_overdue"] == 2

    @pytest.mark.asyncio
    async def test_o_fim_do_periodo_e_respeitado(self, base):
        """O relatório antigo só tinha `$gte início`: contava a semana seguinte."""
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(user_ids=("u-ana",)), base=base, agora=AGORA)
        assert _linha(r, "u-ana")["phase_changes"] == 3  # não 4, não 5

    @pytest.mark.asyncio
    async def test_a_indexacao_nao_aparece(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)
        assert "u-ix" not in {u["user_id"] for u in r["users"]}

    @pytest.mark.asyncio
    async def test_o_inactivo_nao_aparece(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)
        assert "u-fora" not in {u["user_id"] for u in r["users"]}

    @pytest.mark.asyncio
    async def test_o_silenciado_tem_traco_e_nao_zero(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)
        ze = _linha(r, "u-zé")
        assert ze["phase_changes"] is None and ze["historico_silenciado"] is True

    @pytest.mark.asyncio
    async def test_o_filtro_por_utilizador_so_estreita(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(user_ids=("u-rui", "u-nao-existe")), base=base, agora=AGORA)
        assert [u["user_id"] for u in r["users"]] == ["u-rui"]
        assert r["summary"]["total_users"] == 1

    @pytest.mark.asyncio
    async def test_o_filtro_por_papel(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(papeis=("intermediario",)), base=base, agora=AGORA)
        assert [u["user_id"] for u in r["users"]] == ["u-rui"]

    @pytest.mark.asyncio
    async def test_as_fases_e_a_serie_diaria(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)
        por_fase = {f["fase"]: f["n"] for f in r["por_fase"]}
        # Ana: fase_documental×1, aprovado×2 ; Rui: aprovado×1 ; (o u-zé não tem rasto)
        assert por_fase == {"aprovado": 3, "fase_documental": 1}
        serie = {d["dia"]: d for d in r["serie_diaria"]}
        assert len(serie) == 7
        assert serie["2026-10-07"]["mudancas_de_fase"] == 2  # Ana p1 + Rui p5
        assert serie["2026-10-08"]["mudancas_de_fase"] == 2  # Ana p1 + Ana p2
        assert serie["2026-10-07"]["tarefas_concluidas"] == 1  # t-ana
        assert serie["2026-10-08"]["tarefas_concluidas"] == 1  # t-rui
        assert serie["2026-10-05"] == {"dia": "2026-10-05", "mudancas_de_fase": 0, "tarefas_concluidas": 0}

    @pytest.mark.asyncio
    async def test_a_condicao_de_rede_exclui_as_tarefas_de_outra_rede(self, base):
        await _semear(base)
        await base.tasks.insert_one(
            _t("t-domus", ["u-ana"], feita=DENTRO, por="u-ana", network_id="rede_domus"),
        )
        await base.tasks.insert_one(
            _t("t-power", ["u-ana"], feita=DENTRO, por="u-ana", network_id="rede_power"),
        )
        ambito = er.Ambito(chave="p", condicao_de_tarefas={"network_id": {"$in": ["rede_power"]}})
        r = await er.gerar_relatorio(ambito, _filtros(user_ids=("u-ana",)), base=base, agora=AGORA)
        # Só a `t-power` (carimbada na rede); as outras não têm carimbo e ficam de fora.
        assert _linha(r, "u-ana")["tasks_completed"] == 1


class TestOsIndices:
    """«Não bloquear a base de dados»: nenhuma agregação faz COLLSCAN."""

    PIPELINES = {
        "history": [
            ("mudancas_por_pessoa", lambda i, a, b: er.pipeline_mudancas_por_pessoa(i, a, b)),
            ("mudancas_por_fase", lambda i, a, b: er.pipeline_mudancas_por_fase(i, a, b)),
            ("mudancas_por_dia", lambda i, a, b: er.pipeline_mudancas_por_dia(i, a, b)),
        ],
        "tasks": [
            ("concluidas_por_pessoa", lambda i, a, b: er.pipeline_concluidas_por_pessoa(i, a, b, {})),
            ("concluidas_por_dia", lambda i, a, b: er.pipeline_concluidas_por_dia(i, a, b, {})),
            ("carga_em_aberto", lambda i, a, b: er.pipeline_carga_em_aberto(i, b, "2026-10-12", {})),
        ],
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("colecao,nome", [
        ("history", "mudancas_por_pessoa"), ("history", "mudancas_por_fase"),
        ("history", "mudancas_por_dia"), ("tasks", "concluidas_por_pessoa"),
        ("tasks", "concluidas_por_dia"), ("tasks", "carga_em_aberto"),
    ])
    async def test_a_agregacao_usa_indice(self, base, colecao, nome):
        await _semear(base)
        # Documentos suficientes para o planeador não optar por varrer.
        await base.history.insert_many([_h(f"u-x{i}", f"p{i}", DENTRO) for i in range(300)])
        await base.tasks.insert_many([_t(f"t{i}", [f"u-x{i}"]) for i in range(300)])

        construir = dict(self.PIPELINES[colecao])[nome]
        pipeline = construir(["u-ana", "u-rui"], "2026-10-05T00:00:00+00:00", "2026-10-12T00:00:00+00:00")
        plano = await base.command({
            "explain": {"aggregate": colecao, "pipeline": pipeline, "cursor": {}},
            "verbosity": "queryPlanner",
        })
        texto = json.dumps(plano, default=str)
        assert "COLLSCAN" not in texto, f"{colecao}.{nome} varre a colecção inteira"
        assert "IXSCAN" in texto

    @pytest.mark.asyncio
    async def test_os_indices_novos_estao_criados(self, base):
        nomes = set((await base.tasks.index_information()).keys())
        assert {"idx_tasks_completed_by_time", "idx_tasks_assigned_created"} <= nomes
        semanais = await base.executive_weekly_reports.index_information()
        assert semanais["idx_exec_weekly_scope_week"]["unique"] is True


class TestOTempoLimite:
    @pytest.mark.asyncio
    async def test_o_tecto_chega_a_base_de_dados(self, base):
        """`maxTimeMS` tem de ir no comando (e não só no código que o devia mandar)."""
        pedidos = []
        original = base.history.aggregate

        def espia(pipeline, **kwargs):
            pedidos.append(kwargs)
            return original(pipeline, **kwargs)

        await _semear(base)

        class _Embrulho:
            def __init__(self, colecao):
                self._c = colecao

            def aggregate(self, pipeline, **kwargs):
                pedidos.append(kwargs)
                return self._c.aggregate(pipeline, **kwargs)

            def __getattr__(self, nome):
                return getattr(self._c, nome)

        class _Base:
            users = base.users
            processes = base.processes
            history = _Embrulho(base.history)
            tasks = _Embrulho(base.tasks)

        await er.gerar_relatorio(AMBITO, _filtros(), base=_Base(), agora=AGORA)
        assert pedidos and all(p.get("maxTimeMS", 0) > 0 and p.get("allowDiskUse") is True for p in pedidos)


class TestMasterAdminEIndexacaoForaDoRelatorio:
    """Contas de gestão não são operação (Out 2026).

    Um admin que mova processos ou conclua tarefas NÃO pode aparecer na tabela,
    nos totais, nas fases nem na série diária — senão o gráfico de desempenho
    da equipa mede também quem gere o sistema.
    """

    async def _com_gestao(self, bd):
        """Acrescenta as contas de gestão e o seu trabalho a uma base já semeada."""
        await bd.users.insert_many([
            {"id": "u-admin", "name": "Admin", "email": "a@x.pt", "role": "admin", "is_active": True},
            {"id": "u-master", "name": "Master", "email": "m@x.pt", "role": "master", "is_active": True},
            # Conta de gestão que também trabalha como consultor: continua fora.
            {"id": "u-admin-consultor", "name": "Admin Consultor", "email": "ac@x.pt",
             "role": "admin", "additional_roles": ["consultor"], "is_active": True},
            # Consultor com cargo adicional de admin: a conta é de consultor, entra.
            {"id": "u-consultor-admin", "name": "Consultor Admin", "email": "ca@x.pt",
             "role": "consultor", "additional_roles": ["admin"], "is_active": True},
        ])
        await bd.history.insert_many([
            _h("u-admin", "p9", DENTRO, novo="aprovado"),
            _h("u-master", "p9", DENTRO_2, novo="aprovado"),
            _h("u-admin-consultor", "p9", DENTRO, novo="aprovado"),
        ])
        await bd.tasks.insert_many([
            _t("t-admin", ["u-admin"], feita=DENTRO, por="u-admin"),
            _t("t-master", ["u-master"], feita=DENTRO, por="u-master"),
        ])

    @pytest.mark.asyncio
    async def test_nao_aparecem_na_tabela(self, base):
        await _semear(base)
        await self._com_gestao(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)
        ids = {u["user_id"] for u in r["users"]}
        assert not ids & {"u-admin", "u-master", "u-admin-consultor", "u-ix"}
        assert "u-consultor-admin" in ids  # contraprova: a conta de consultor entra

    @pytest.mark.asyncio
    async def test_o_trabalho_deles_nao_entra_nos_totais_nas_fases_nem_na_serie(self, base):
        await _semear(base)
        sem = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)
        er.limpar_cache()
        await self._com_gestao(base)
        com = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)

        assert com["summary"]["total_phase_changes"] == sem["summary"]["total_phase_changes"]
        assert com["summary"]["total_tasks_completed"] == sem["summary"]["total_tasks_completed"]
        assert com["por_fase"] == sem["por_fase"]
        assert sum(d["mudancas_de_fase"] for d in com["serie_diaria"]) == \
            sum(d["mudancas_de_fase"] for d in sem["serie_diaria"])

    @pytest.mark.asyncio
    async def test_pedir_so_admin_ou_master_nao_devolve_ninguem(self, base):
        await _semear(base)
        await self._com_gestao(base)
        for papel in ("admin", "master", "indexacao"):
            r = await er.gerar_relatorio(AMBITO, _filtros(papeis=(papel,)), base=base, agora=AGORA)
            assert r["users"] == [], papel

    @pytest.mark.asyncio
    async def test_pedir_um_admin_pelo_id_tambem_nao_o_traz(self, base):
        await _semear(base)
        await self._com_gestao(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(user_ids=("u-admin",)), base=base, agora=AGORA)
        assert r["users"] == []

    @pytest.mark.asyncio
    async def test_as_notas_de_criterio_dizem_quem_ficou_de_fora(self, base):
        await _semear(base)
        r = await er.gerar_relatorio(AMBITO, _filtros(), base=base, agora=AGORA)
        assert any("Master, Admin e Indexação" in n for n in r["notas"])
