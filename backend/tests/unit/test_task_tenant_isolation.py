"""
Testes unitários — as tarefas NÃO atravessam redes (Lote 6, ponto 4).

O DEFEITO (produção, Set 2026)
==============================
`GET /api/tasks` (`task_api_crud.run_get_tasks`) abria com ``query = {}`` e
nunca acrescentava marca de empresa nem de rede. Sem filtros na query
string — que é como o Dashboard e o `TasksPanel` a chamam — a consulta
final era ``{"completed": False}``: **todas as tarefas não concluídas da
base de dados**, de todas as empresas e de todas as redes.

Um utilizador da Domus — que é uma ilha 100% isolada — via as tarefas da
Power e da Precision. `run_get_my_tasks` filtra por ``assigned_to`` e, por
isso, escapa por acidente: a atribuição coincide com o âmbito. Foi essa
metade que escondeu a outra, exactamente como o `invalidateQueries` por
prefixo escondeu o `setQueryData` por chave exacta.

O AGENTS.md do Lote 4 afirmava que `task_api_crud` fazia parte do
varrimento de isolamento. Não fazia: o ficheiro tinha ZERO ocorrências de
`compan` ou `tenant`. É a terceira vez que o inventário das superfícies
que LISTAM fica incompleto (Kanban no Lote 5, notificações no Lote 5) —
por isso a guarda de fonte no fim deste ficheiro é sobre as DUAS funções
de listagem, e não só sobre a que estava partida.

A REDE, NÃO A EMPRESA
  A topologia é: Power e Precision trabalham juntas (`network_id`
  partilhado), Domus é ilha. Filtrar por `company_id` cortaria a Power da
  Precision, que é uma regra de negócio real. O ponto único é
  `services/tenant_network.py`.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import task_api_crud
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios


REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "ilha_domus"

UTILIZADOR_DA_DOMUS = {
    "id": "u-domus",
    "email": "d@domus.pt",
    "name": "Cliente Domus",
    "role": "consultor",
    "company": "Domus",
    "active_company_id": "c-domus",
}


def _tarefa(tid: str, *, rede: str | None, dono: str, empresa: str | None = None) -> dict:
    doc = {
        "id": tid,
        "title": f"Tarefa {tid}",
        "description": "",
        "assigned_to": [dono],
        "created_by": dono,
        "completed": False,
        "created_at": "2026-09-27T10:00:00+00:00",
        "updated_at": "2026-09-27T10:00:00+00:00",
        "priority": "media",
    }
    if rede is not None:
        doc["network_id"] = rede
    if empresa is not None:
        doc["company_id"] = empresa
    return doc


@pytest.fixture
def db_com_tarefas_de_duas_redes(fake_async_db):
    fake_async_db.tasks.docs.extend([
        _tarefa("t-domus", rede=REDE_DOMUS, dono="u-domus", empresa="c-domus"),
        _tarefa("t-power", rede=REDE_POWER, dono="u-power", empresa="c-power"),
        _tarefa("t-precision", rede=REDE_POWER, dono="u-prec", empresa="c-prec"),
    ])
    return fake_async_db


async def _listar(fake_db, utilizador, scope_redes, scope_empresas, **kwargs):
    """Corre `run_get_tasks` com o âmbito de tenant já resolvido.

    O `resolve_tenant_scope` real vai à colecção `companies` e ao
    `user_company_roles`; aqui interessa o que a LISTAGEM faz com o âmbito,
    por isso é o âmbito que se fixa — e a condição é construída pela
    função de produção, não escrita à mão no teste.
    """
    from services.tenant_network import TenantScope

    scope = TenantScope(
        network_ids=tuple(scope_redes),
        company_ids=tuple(scope_empresas),
        company_names=(),
        inclui_rede_de_omissao=False,
    )
    with patch.object(task_api_crud, "db", fake_db), \
         patch("services.tenant_network.resolve_tenant_scope", return_value=scope), \
         patch.object(task_api_crud, "enrich_task", new=_passa):
        return await task_api_crud.run_get_tasks(utilizador, **kwargs)


async def _carimbo_fixo(*_args, **_kwargs):
    """Carimbo previsível.

    Patchado em `task_api_crud` e NÃO em `services.tenant_network`: o
    serviço faz `from ... import resolve_tenant_stamp` no topo e ficou com
    a SUA referência. Patchar o módulo de origem deixava passar o real, que
    vai à colecção `companies` — o teste ficava a depender da ordem de
    recolha do pytest (AGENTS.md, a armadilha do `from database import db`).
    """
    return {"network_id": REDE_DOMUS, "company_id": "c-domus"}


async def _passa(tarefa):
    """Enriquecimento neutro: os nomes exigem `db.users` e não é o que se testa."""
    tarefa.setdefault("assigned_to_names", [])
    tarefa.setdefault("created_by_name", "")
    return tarefa


class TestAFugaEntreRedes:
    """Escritos para MORDER enquanto a listagem não tiver filtro de rede."""

    @pytest.mark.asyncio
    async def test_utilizador_da_domus_nao_ve_tarefas_da_power(
        self, db_com_tarefas_de_duas_redes,
    ):
        tarefas = await _listar(
            db_com_tarefas_de_duas_redes,
            UTILIZADOR_DA_DOMUS,
            [REDE_DOMUS],
            ["c-domus"],
        )
        ids = {t.id for t in tarefas}
        assert ids == {"t-domus"}, (
            "a listagem devolveu tarefas de outra rede: " f"{sorted(ids)}"
        )

    @pytest.mark.asyncio
    async def test_a_power_ve_a_precision_porque_partilham_a_rede(
        self, db_com_tarefas_de_duas_redes,
    ):
        """Contraprova no sentido oposto.

        Sem este teste, "não devolve nada" satisfaria o teste de cima — e
        um filtro demasiado apertado é uma regressão silenciosa, porque a
        Power e a Precision trabalham MESMO sobre os mesmos dados.
        """
        utilizador = {**UTILIZADOR_DA_DOMUS, "id": "u-power", "company": "Power"}
        tarefas = await _listar(
            db_com_tarefas_de_duas_redes,
            utilizador,
            [REDE_POWER],
            ["c-power", "c-prec"],
        )
        assert {t.id for t in tarefas} == {"t-power", "t-precision"}

    @pytest.mark.asyncio
    async def test_o_calendario_global_do_admin_tambem_e_por_rede(
        self, db_com_tarefas_de_duas_redes,
    ):
        """`user_id="all"` alarga o âmbito de PESSOAS, não o de REDES.

        O ramo do calendário global fazia `# Não adicionar filtro`, e um
        admin da Domus passava a ver a base de dados inteira. Um admin é
        admin da sua rede.
        """
        admin_domus = {**UTILIZADOR_DA_DOMUS, "id": "a-domus", "role": "admin"}
        tarefas = await _listar(
            db_com_tarefas_de_duas_redes,
            admin_domus,
            [REDE_DOMUS],
            ["c-domus"],
            user_id="all",
        )
        assert {t.id for t in tarefas} == {"t-domus"}


class TestTarefasPorCarimbar:
    """A pilha histórica não pode desaparecer do ecrã de quem trabalha nela."""

    @pytest.mark.asyncio
    async def test_tarefa_sem_marca_nenhuma_entra_quando_o_ambito_a_inclui(
        self, fake_async_db,
    ):
        from services.tenant_network import TenantScope

        fake_async_db.tasks.docs.append(_tarefa("t-antiga", rede=None, dono="u-domus"))
        scope = TenantScope(
            network_ids=(REDE_DOMUS,),
            company_ids=("c-domus",),
            company_names=(),
            inclui_rede_de_omissao=True,
        )
        with patch.object(task_api_crud, "db", fake_async_db), \
             patch("services.tenant_network.resolve_tenant_scope", return_value=scope), \
             patch.object(task_api_crud, "enrich_task", new=_passa):
            tarefas = await task_api_crud.run_get_tasks(UTILIZADOR_DA_DOMUS)
        assert {t.id for t in tarefas} == {"t-antiga"}


class TestAsTarefasNovasNascemCarimbadas:
    @pytest.mark.asyncio
    async def test_run_create_task_grava_a_rede(self, fake_async_db):
        """Sem carimbo na ESCRITA, a correcção da leitura esconde o trabalho novo.

        É a lição do `assigned_to`: normalizar à leitura trata o que já
        existe; deixar de produzir mal é o que impede o problema de voltar.
        """
        from models.task import TaskCreate

        dados = TaskCreate(title="Nova", description="x", assigned_to=["u-domus"])
        with patch.object(task_api_crud, "db", fake_async_db), \
             patch.object(
                 task_api_crud,
                 "resolve_tenant_stamp",
                 new=_carimbo_fixo,
             ), \
             patch.object(task_api_crud, "enrich_task", new=_passa):
            await task_api_crud.run_create_task(dados, UTILIZADOR_DA_DOMUS)

        gravada = await fake_async_db.tasks.find_one({"title": "Nova"})
        assert gravada is not None
        assert gravada.get("network_id") == REDE_DOMUS


class TestGuardaDeFonte:
    """As DUAS listagens pedem a condição ao ponto único.

    Não basta afirmar sobre a que estava partida: foi assim que o Kanban
    ficou de fora do Lote 4.
    """

    @pytest.mark.parametrize(
        "funcao",
        [task_api_crud.run_get_tasks, task_api_crud.run_get_my_tasks],
    )
    def test_a_listagem_chama_o_ponto_unico(self, funcao):
        codigo = codigo_da_funcao_sem_comentarios(funcao)
        assert "build_tenant_condition" in codigo, (
            f"{funcao.__name__} não pede a condição de rede ao ponto único "
            "(services/tenant_network.build_tenant_condition)."
        )

    def test_nenhuma_listagem_reconstroi_a_condicao_a_mao(self):
        """Contraprova da guarda acima.

        Uma condição escrita à mão (`{"company_id": ...}`) satisfaria a
        intenção e divergiria do ponto único na primeira mudança de
        topologia — que é precisamente o que o placebo
        `build_company_scope_condition` fez.
        """
        for funcao in (task_api_crud.run_get_tasks, task_api_crud.run_get_my_tasks):
            codigo = codigo_da_funcao_sem_comentarios(funcao)
            assert "network_id" not in codigo, (
                f"{funcao.__name__} nomeia `network_id` directamente — "
                "a condição vem de `build_tenant_condition`."
            )
