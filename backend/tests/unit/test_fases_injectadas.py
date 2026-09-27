"""O fim do `INACTIVE_STATUSES` como definição de terminal.

ÉPICO 10, PONTO 1.

O QUE ESTAVA ERRADO
  ~30 linhas espalhadas por 13 módulos decidiam "este processo está
  fechado" por uma LISTA CRAVADA. Seis dessas eram piores: constantes
  derivadas no IMPORT (`set(INACTIVE_STATUSES) | {...}`), que congelam o
  motor no arranque do processo — uma fase fechada pelo administrador só
  passava a contar no deploy seguinte.

A SOLUÇÃO, E PORQUE NÃO FOI TORNAR TUDO ASSÍNCRONO
  Os construtores de query são funções PURAS, e é isso que as torna
  testáveis sem Mongo no `backend-fast`. Passaram a aceitar `terminais`;
  quem resolve as fases é o chamador, que já era assíncrono. O valor por
  omissão mantém `INACTIVE_STATUSES` — que deixou de ser a DEFINIÇÃO de
  terminal e passou a ser o RESÍDUO legado.
"""
import pytest

from models.auth import UserRole
from services.my_clients_api_helpers import (
    build_my_clients_process_query,
    build_my_clients_stats_query,
)
from services.process_list_filters import (
    _arquivadas,
    build_kanban_view_mode_filter,
    build_view_mode_status_conditions,
)
from services.process_status import ARCHIVED_STATUSES, INACTIVE_STATUSES
from services.process_update import assert_process_editable_for_role
from services.workflow_phases import nomes_terminais


def fase(nome, **extra):
    base = {"id": nome, "name": nome, "label": nome.title(),
            "order": 1, "color": "blue"}
    base.update(extra)
    return base


# Um motor onde o admin fechou uma fase que a lista legada NÃO conhece.
# É a única forma de distinguir os dois dialectos: qualquer asserção
# sobre `concluidos` passaria com a lista cravada também.
MOTOR = [
    fase("clientes_espera"),
    fase("fase_bancaria"),
    fase("renegociacao", is_active=False),   # fechada PELO ADMIN
    fase("concluidos", is_active=False),
]
TERMINAIS = nomes_terminais(MOTOR)


def test_o_caso_de_teste_e_mesmo_discriminante():
    """Sem isto, tudo o que se segue podia passar com a lista legada."""
    assert "renegociacao" in TERMINAIS
    assert "renegociacao" not in INACTIVE_STATUSES


# ====================================================================
# OS CINCO CONSTRUTORES PUROS
# ====================================================================

class TestInjeccaoNosConstrutores:
    def test_view_mode_activo_exclui_a_fase_fechada_pelo_admin(self):
        cond = build_view_mode_status_conditions(
            status=None, view_mode="active_only", terminais=TERMINAIS,
        )
        assert cond == [{"status": {"$nin": TERMINAIS}}]
        assert "renegociacao" in cond[0]["status"]["$nin"]

    def test_sem_injeccao_mantem_a_lista_legada(self):
        """A omissão é o comportamento de hoje — nada muda por acidente."""
        cond = build_view_mode_status_conditions(
            status=None, view_mode="active_only",
        )
        assert cond == [{"status": {"$nin": INACTIVE_STATUSES}}]

    def test_o_historico_deriva_dos_terminais_sem_os_eliminados(self):
        """`eliminado` é soft-delete, não uma fase — nunca entra no histórico."""
        cond = build_view_mode_status_conditions(
            status=None, view_mode="historical", terminais=TERMINAIS,
        )
        arquivadas = cond[0]["status"]["$in"]
        assert "renegociacao" in arquivadas
        assert "eliminado" not in arquivadas and "eliminados" not in arquivadas

    def test_arquivadas_sem_injeccao_mantem_a_lista_legada(self):
        assert _arquivadas() == ARCHIVED_STATUSES

    def test_o_kanban_activo_usa_os_terminais_do_motor(self):
        f = build_kanban_view_mode_filter(
            view_mode="active_only", terminais=TERMINAIS,
        )
        assert "renegociacao" in f["status"]["$nin"]

    def test_o_kanban_recente_usa_os_dois_conjuntos(self):
        f = build_kanban_view_mode_filter(
            view_mode="all", completed_days=30, terminais=TERMINAIS,
        )
        ramos = f["$or"]
        assert "renegociacao" in ramos[0]["status"]["$nin"]
        assert "renegociacao" in ramos[1]["$and"][0]["status"]["$in"]

    @pytest.mark.parametrize("papel", [UserRole.CONSULTOR, UserRole.INTERMEDIARIO,
                                       UserRole.DIRETOR, UserRole.ADMINISTRATIVO])
    def test_my_clients_esconde_a_fase_fechada(self, papel):
        query = build_my_clients_process_query(
            user_id="u1", user_email="u@x.pt", role=papel,
            wants_deleted=False, terminais=TERMINAIS,
        )
        assert "renegociacao" in str(query)

    @pytest.mark.parametrize("papel", [UserRole.CONSULTOR, UserRole.INTERMEDIARIO,
                                       UserRole.DIRETOR, UserRole.ADMINISTRATIVO])
    def test_as_estatisticas_usam_o_mesmo_conjunto(self, papel):
        """A lista e as estatísticas do mesmo ecrã não podem divergir."""
        lista = build_my_clients_process_query(
            user_id="u1", user_email="u@x.pt", role=papel,
            wants_deleted=False, terminais=TERMINAIS,
        )
        stats = build_my_clients_stats_query(
            user_id="u1", user_email="u@x.pt", role=papel, terminais=TERMINAIS,
        )
        assert ("renegociacao" in str(lista)) == ("renegociacao" in str(stats))

    def test_os_construtores_continuam_puros(self):
        """Não levam `await` nenhum: é o que os mantém no `backend-fast`,
        que corre SEM Mongo."""
        import inspect

        for f in (build_view_mode_status_conditions, build_kanban_view_mode_filter,
                  build_my_clients_process_query, build_my_clients_stats_query,
                  assert_process_editable_for_role):
            assert not inspect.iscoroutinefunction(f), f.__name__


# ====================================================================
# A REGRA DE EDIÇÃO
# ====================================================================

class TestEdicaoEmFaseTerminal:
    def test_a_fase_fechada_pelo_admin_bloqueia_a_edicao(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            assert_process_editable_for_role(
                "renegociacao", UserRole.CONSULTOR, tuple(TERMINAIS),
            )
        assert e.value.status_code == 403

    def test_sem_injeccao_a_mesma_fase_passava(self):
        """A prova de que a injecção muda mesmo o comportamento."""
        assert_process_editable_for_role("renegociacao", UserRole.CONSULTOR)

    def test_admin_e_ceo_continuam_isentos(self):
        for papel in (UserRole.ADMIN, UserRole.CEO):
            assert_process_editable_for_role(
                "renegociacao", papel, tuple(TERMINAIS),
            )

    def test_uma_fase_aberta_nao_bloqueia(self):
        assert_process_editable_for_role(
            "fase_bancaria", UserRole.CONSULTOR, tuple(TERMINAIS),
        )


# ====================================================================
# AS SEIS CONSTANTES QUE CONGELAVAM O MOTOR NO IMPORT
# ====================================================================

class TestConstantesDerivadasMorreram:
    """`set(INACTIVE_STATUSES) | {...}` calculado no IMPORT congela o
    motor no arranque do processo. Com `UVICORN_WORKERS=2` e um servidor
    que fica dias de pé, uma fase fechada pelo admin não contava até ao
    deploy seguinte — e ninguém ligava as duas coisas."""

    MORTAS = [
        ("services.process_assignment", "INDEXER_INACTIVE_STATUSES"),
        ("services.process_assignment", "CONSULTANT_INACTIVE_STATUSES"),
        ("services.process_assignment", "_WORKFLOW_START_EXCLUDED"),
        ("services.process_update", "TERMINAL_PROCESS_STATUSES"),
    ]

    @pytest.mark.parametrize("modulo,nome", MORTAS)
    def test_a_constante_desapareceu(self, modulo, nome):
        import importlib

        assert not hasattr(importlib.import_module(modulo), nome), (
            f"{nome} voltou a ser calculada no import"
        )

    @pytest.mark.parametrize("modulo,nome", [
        ("services.process_assignment", "indexer_inactive_statuses"),
        ("services.process_assignment", "consultant_inactive_statuses"),
        ("services.process_assignment", "workflow_start_excluded"),
        ("services.process_update", "terminal_process_statuses"),
    ])
    def test_contraprova_a_funcao_existe_e_e_assincrona(self, modulo, nome):
        """Sem isto, apagar a constante bastava para passar acima."""
        import importlib
        import inspect

        f = getattr(importlib.import_module(modulo), nome)
        assert inspect.iscoroutinefunction(f)

    @pytest.mark.parametrize("ficheiro,constante", [
        ("services/deadlines_api_list.py", "FINISHED_STATUS"),
        ("services/portal_onboarding_advance.py", "EXCLUDED_FROM_KANBAN_START"),
    ])
    def test_as_locais_resolvem_no_pedido(self, ficheiro, constante):
        """Estas duas vivem DENTRO da função, logo não congelavam no
        import — mas liam a lista cravada. Agora derivam do motor."""
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[2]
        fonte = (raiz / ficheiro).read_text(encoding="utf-8")
        i = fonte.index(constante)
        trecho = fonte[i:i + 400]
        assert "nomes_terminais" in trecho
        assert "INACTIVE_STATUSES" not in trecho

    async def test_o_indexador_conta_a_fase_que_o_admin_fechou(
        self, fake_async_db, monkeypatch,
    ):
        """O comportamento, não só a forma."""
        import services.process_assignment as pa
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_many(
            [fase("clientes_espera"), fase("renegociacao", is_active=False)],
        )
        fechadas = await pa.indexer_inactive_statuses()
        assert "renegociacao" in fechadas
        assert "pre_registo" in fechadas          # o extra local sobrevive
        assert "clientes_espera" not in fechadas


# ====================================================================
# A CACHE
# ====================================================================

class TestCacheDasFases:
    """Uma leitura por pedido de listagem. São 14 documentos com índice,
    mas numa listagem de alta frequência é uma ida ao Mongo a mais."""

    async def test_a_segunda_leitura_nao_volta_a_base_de_dados(
        self, fake_async_db, monkeypatch,
    ):
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(fase("clientes_espera"))

        primeira = await wp.carregar_fases()
        # Muda a BD por baixo: só quem NÃO usa cache é que vê.
        await fake_async_db.workflow_statuses.insert_one(fase("fase_nova"))
        segunda = await wp.carregar_fases()

        assert [f["name"] for f in segunda] == [f["name"] for f in primeira]

    async def test_usar_cache_false_le_fresco_e_NAO_escreve_na_cache(
        self, fake_async_db, monkeypatch,
    ):
        """TESTE FRACO CORRIGIDO — sobreviveu à mutação P10.

        Antes só afirmava que `usar_cache=False` devolvia dados frescos.
        Mas se ele TAMBÉM gravasse na cache, isso continuava verdade — e
        a leitura seguinte passava a servir o que uma chamada explícita
        de "não uses cache" tinha deixado lá.
        """
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(fase("clientes_espera"))
        await wp.carregar_fases()                       # cache quente com 1

        await fake_async_db.workflow_statuses.insert_one(fase("fase_nova"))
        assert len(await wp.carregar_fases(usar_cache=False)) == 2

        # A cache não foi tocada: continua a servir o retrato antigo.
        assert len(await wp.carregar_fases()) == 1

    async def test_a_invalidacao_faz_a_leitura_seguinte_ir_a_base(
        self, fake_async_db, monkeypatch,
    ):
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(fase("clientes_espera"))
        await wp.carregar_fases()

        await fake_async_db.workflow_statuses.insert_one(fase("fase_nova"))
        wp.invalidar_cache_de_fases()
        assert len(await wp.carregar_fases()) == 2

    async def test_o_ttl_expira(self, fake_async_db, monkeypatch):
        """TESTE FRACO CORRIGIDO — sobreviveu à mutação P8.

        A versão anterior aquecia a cache DEPOIS de inserir a segunda
        fase, e depois afirmava que via duas. Só que a cache já tinha
        duas: o valor em cache e o valor fresco eram iguais, portanto a
        expiração era invisível. Trocar `agora < expira_em` por `True`
        passava à mesma.

        A asserção que distingue precisa de uma fase inserida DEPOIS de
        a cache estar quente.
        """
        import services.workflow_phases as wp

        relogio = [0.0]
        monkeypatch.setattr(wp.time, "monotonic", lambda: relogio[0])
        monkeypatch.setattr(wp, "db", fake_async_db)

        await fake_async_db.workflow_statuses.insert_one(fase("clientes_espera"))
        wp.invalidar_cache_de_fases()
        assert len(await wp.carregar_fases()) == 1   # cache quente com 1

        await fake_async_db.workflow_statuses.insert_one(fase("fase_nova"))
        relogio[0] = wp._TTL_DA_CACHE_SEGUNDOS - 1
        assert len(await wp.carregar_fases()) == 1, "ainda dentro do TTL"

        relogio[0] = wp._TTL_DA_CACHE_SEGUNDOS + 1
        assert len(await wp.carregar_fases()) == 2, "o TTL tem de expirar"

    async def test_uma_leitura_FALHADA_nao_fica_em_cache(self, monkeypatch):
        """Guardar `[]` por 30s transformava um soluço do Mongo em meio
        minuto de listagens vazias — e o quadro sem colunas nenhumas."""
        import services.workflow_phases as wp

        class BDPartida:
            def __getattr__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(wp, "db", BDPartida())
        assert await wp.carregar_fases() == []
        assert wp._cache_de_fases is None

    def test_quem_escreve_uma_fase_esquece_a_cache(self):
        """Sem isto, o próprio admin continuava a ver a versão antiga
        durante 30s depois de gravar."""
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[2]
        fonte = (raiz / "services" / "admin_workflow.py").read_text(encoding="utf-8")
        assert fonte.count("invalidar_cache_de_fases()") >= 3  # criar/editar/apagar


# ====================================================================
# A COSTURA: O QUADRO INTEIRO
# ====================================================================

class TestOQuadroUsaOsTerminaisDoMotor:
    """Sobreviveu à mutação P11 (`terminais = None` no quadro).

    Testei os construtores um a um e nunca testei a COSTURA: o
    `run_get_kanban_board` a resolver as fases e a passá-las à query. Com
    `terminais=None` o filtro de vista caía na lista legada — as colunas
    vinham do motor e o FILTRO da lista legada, que são os dois dialectos
    outra vez, agora dentro do mesmo pedido.
    """

    MOTOR_COM_FASE_FECHADA = [
        fase("clientes_espera", order=1),
        # Fechada PELO ADMIN. Não existe na lista legada — é o único
        # caso que distingue os dois dialectos.
        fase("renegociacao", order=2, is_active=False),
    ]

    async def _quadro(self, fake_async_db, monkeypatch, **kwargs):
        from unittest.mock import patch

        import services.process_kanban_enrichment as kanban
        import services.process_list_enrichment as ple
        import services.tenant_network as tn
        import services.workflow_phases as wp

        await fake_async_db.workflow_statuses.insert_many(
            [dict(f) for f in self.MOTOR_COM_FASE_FECHADA],
        )
        await fake_async_db.processes.insert_many([
            {"id": "p-aberto", "status": "clientes_espera"},
            {"id": "p-fechado", "status": "renegociacao"},
        ])

        async def _noop(*a, **k):
            return None

        monkeypatch.setattr(wp, "db", fake_async_db)
        monkeypatch.setattr(kanban, "db", fake_async_db)
        monkeypatch.setattr(tn, "db", fake_async_db)
        with patch("database.db", fake_async_db), \
             patch.object(ple, "enrich_processes_portal_flags", _noop), \
             patch.object(ple, "enrich_processes_latest_activity", _noop, create=True):
            return await kanban.run_get_kanban_board(
                user={"id": "u1", "role": "admin", "name": "A"},
                role="admin", show_all=True,
                consultor_id=None, mediador_id=None,
                indexacao_id=None, parceiro_id=None,
                decrypt_list_fn=lambda docs, **kw: docs,
                kanban_projection={"_id": 0},
                **kwargs,
            )

    async def test_a_fase_fechada_pelo_admin_nao_conta_como_activa(
        self, fake_async_db, monkeypatch,
    ):
        """O contador do cabeçalho tem de a ver como fechada."""
        resposta = await self._quadro(
            fake_async_db, monkeypatch, view_mode="all", completed_days=0,
        )
        assert resposta["total_processes"] == 1      # só o `clientes_espera`
        assert resposta["total_inactive"] == 1       # a `renegociacao`

    async def test_active_only_deixa_o_processo_fechado_de_fora(
        self, fake_async_db, monkeypatch,
    ):
        """Com a lista legada, `renegociacao` entrava no quadro activo."""
        resposta = await self._quadro(
            fake_async_db, monkeypatch, view_mode="active_only", completed_days=0,
        )
        cartoes = {
            p["id"] for col in resposta["columns"] for p in col["processes"]
        }
        assert cartoes == {"p-aberto"}

    async def test_contraprova_sem_filtro_os_dois_aparecem(
        self, fake_async_db, monkeypatch,
    ):
        """Sem isto, um quadro sempre vazio satisfazia o teste acima."""
        resposta = await self._quadro(
            fake_async_db, monkeypatch, view_mode="all", completed_days=0,
        )
        cartoes = {
            p["id"] for col in resposta["columns"] for p in col["processes"]
        }
        assert cartoes == {"p-aberto", "p-fechado"}
