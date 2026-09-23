"""
Higiene das atribuições de tarefas — Lote 4, ponto 12 ("Atribuição Fantasma").

TRÊS DEFEITOS, UM DELES NÃO ESTAVA NO ENUNCIADO.

  (a) A BOMBA DO `$in`. `workflow_engine` grava `assigned_to` como ESCALAR
      (`process.get("assigned_consultor_id")`) ou `None`; `task_api_crud` e
      `process_assignment` gravam LISTA. O `enrich_task` faz
      `get_user_names(task["assigned_to"])` → `{"id": {"$in": <valor>}}`, e o
      Mongo responde `OperationFailure: $in needs an array`. Como
      `run_list_tasks` enriquece num ciclo SEM try/except, UMA tarefa criada
      por uma regra de automação faz a listagem INTEIRA devolver 500.

  (b) NINGUÉM LIMPA AS TAREFAS QUANDO A ATRIBUIÇÃO MUDA.
      `_create_post_indexing_tasks` cria tarefas de arranque para quem é
      atribuído; nenhum caminho de atribuição volta a tocar-lhes. Tirar o
      consultor do processo deixa as tarefas dele lá — o processo fica sem
      ninguém atribuído e com tarefas de consultores. É a "Atribuição
      Fantasma" do enunciado.

  (c) Uma tarefa órfã é INDISTINGUÍVEL de uma tarefa por atribuir. Ambas
      aparecem como "Sem atribuição"; a primeira exige uma decisão humana,
      a segunda é só um campo vazio.

REGRA DE NEGÓCIO (Opção A, decidida pelo dono):
  Nunca apagar trabalho humano em silêncio. Uma tarefa que o SISTEMA criou e
  que ninguém tocou desaparece com a atribuição que a justificava; tudo o
  resto fica, perde a atribuição e é marcado como órfão à espera de
  reatribuição.
"""
from unittest.mock import patch

import pytest


CONSULTOR = "u-consultor"
MEDIADOR = "u-mediador"
OUTRO = "u-outro"

CRIADA = "2026-09-20T10:00:00+00:00"
TOCADA = "2026-09-21T15:00:00+00:00"


def tarefa_do_sistema(**extra):
    """Tarefa de arranque criada por `_create_post_indexing_tasks`."""
    base = {
        "id": "t-sistema",
        "title": "Contactar o cliente",
        "assigned_to": [CONSULTOR],
        "process_id": "p-1",
        "created_by": "system",
        "completed": False,
        "created_at": CRIADA,
        "updated_at": CRIADA,
    }
    base.update(extra)
    return base


def tarefa_humana(**extra):
    base = {
        "id": "t-humana",
        "title": "Rever a minuta com o notário",
        "assigned_to": [CONSULTOR],
        "process_id": "p-1",
        "created_by": "u-diretora",
        "completed": False,
        "created_at": CRIADA,
        "updated_at": CRIADA,
    }
    base.update(extra)
    return base


# ════════════════════════════════════════════════════════════════════
# (a) A BOMBA DO `$in`
# ════════════════════════════════════════════════════════════════════
class TestFormaUnicaDoAssignedTo:
    def test_lista_passa_intacta(self):
        from services.task_assignment_hygiene import normalizar_assigned_to

        assert normalizar_assigned_to([CONSULTOR, MEDIADOR]) == [CONSULTOR, MEDIADOR]

    def test_escalar_vira_lista(self):
        """É esta a forma que o `workflow_engine` grava e que rebenta o `$in`."""
        from services.task_assignment_hygiene import normalizar_assigned_to

        assert normalizar_assigned_to(CONSULTOR) == [CONSULTOR]

    def test_none_e_vazio_viram_lista_vazia(self):
        from services.task_assignment_hygiene import normalizar_assigned_to

        assert normalizar_assigned_to(None) == []
        assert normalizar_assigned_to("") == []
        assert normalizar_assigned_to([]) == []

    def test_descarta_entradas_vazias_e_duplicados(self):
        from services.task_assignment_hygiene import normalizar_assigned_to

        assert normalizar_assigned_to([CONSULTOR, "", None, CONSULTOR]) == [CONSULTOR]

    @pytest.mark.asyncio
    async def test_enrich_task_sobrevive_a_um_escalar(self, fake_async_db):
        """A prova da bomba: sem normalização, isto levanta OperationFailure
        contra o Mongo real (`$in needs an array`) e derruba a listagem
        inteira de tarefas, não só esta linha."""
        import services.task_api_helpers as helpers

        fake_async_db.users.docs.append({"id": CONSULTOR, "name": "Rita"})
        tarefa = {"id": "t-automacao", "assigned_to": CONSULTOR, "completed": False}

        with patch.object(helpers, "db", fake_async_db):
            enriquecida = await helpers.enrich_task(dict(tarefa))

        assert enriquecida["assigned_to"] == [CONSULTOR]
        assert enriquecida["assigned_to_names"] == ["Rita"]

    def test_o_motor_de_automacao_grava_lista(self):
        """Guarda sobre o código-fonte: a origem da forma errada.

        Normalizar à leitura trata os documentos que já existem; só deixar
        de os PRODUZIR impede que o problema volte.
        """
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = (
            Path(__file__).resolve().parents[2] / "services" / "workflow_engine.py"
        ).read_text("utf-8")
        codigo = codigo_sem_comentarios(fonte).replace('"', "'")
        assert "'assigned_to': assigned_to," not in codigo, (
            "o motor de automação continua a gravar o valor cru (escalar ou None)"
        )
        assert "normalizar_assigned_to" in codigo


# ════════════════════════════════════════════════════════════════════
# (b) e (c) — a atribuição fantasma
# ════════════════════════════════════════════════════════════════════
class TestEquipaDoProcesso:
    def test_le_todos_os_campos_canonicos(self):
        """Os campos de atribuição existem em singular e em lista (ver
        AGENTS.md, "Atribuição: campos CANÓNICOS"). Ler só metade faria a
        limpeza tratar como removido quem continua atribuído."""
        from services.task_assignment_hygiene import ids_atribuidos_do_processo

        processo = {
            "assigned_consultor_ids": [CONSULTOR],
            "assigned_mediador_id": MEDIADOR,
            "consultant_id": CONSULTOR,
            "assigned_indexacao_id": None,
        }
        assert ids_atribuidos_do_processo(processo) == {CONSULTOR, MEDIADOR}

    def test_processo_sem_ninguem_devolve_conjunto_vazio(self):
        from services.task_assignment_hygiene import ids_atribuidos_do_processo

        assert ids_atribuidos_do_processo({"id": "p-1"}) == set()


class TestPlanoDeLimpeza:
    def test_tarefa_do_sistema_por_tocar_desaparece(self):
        from services.task_assignment_hygiene import plano_de_limpeza

        plano = plano_de_limpeza([tarefa_do_sistema()], removidos={CONSULTOR})
        assert plano.apagar == ["t-sistema"]
        assert plano.desatribuir == []

    def test_tarefa_humana_fica_mas_perde_a_atribuicao(self):
        """Regra de ouro: nunca apagar trabalho humano em silêncio."""
        from services.task_assignment_hygiene import plano_de_limpeza

        plano = plano_de_limpeza([tarefa_humana()], removidos={CONSULTOR})
        assert plano.apagar == []
        assert plano.desatribuir == [("t-humana", [])]

    def test_tarefa_do_sistema_JA_TOCADA_nao_se_apaga(self):
        """`updated_at` diferente de `created_at` significa que alguém lhe
        mexeu — deixa de ser trabalho do sistema e passa a ser de alguém."""
        from services.task_assignment_hygiene import plano_de_limpeza

        plano = plano_de_limpeza(
            [tarefa_do_sistema(updated_at=TOCADA)], removidos={CONSULTOR},
        )
        assert plano.apagar == []
        assert plano.desatribuir == [("t-sistema", [])]

    def test_tarefa_do_sistema_JA_CONCLUIDA_nao_se_apaga(self):
        """Apagar uma tarefa concluída reescreve o histórico do processo."""
        from services.task_assignment_hygiene import plano_de_limpeza

        plano = plano_de_limpeza(
            [tarefa_do_sistema(completed=True, completed_by=CONSULTOR)],
            removidos={CONSULTOR},
        )
        assert plano.apagar == []

    def test_atribuicao_partilhada_so_perde_quem_saiu(self):
        """Tirar o consultor de uma tarefa que também é do mediador não a
        deixa órfã — e apagá-la levaria o trabalho de quem ficou."""
        from services.task_assignment_hygiene import plano_de_limpeza

        tarefa = tarefa_do_sistema(assigned_to=[CONSULTOR, MEDIADOR])
        plano = plano_de_limpeza([tarefa], removidos={CONSULTOR})
        assert plano.apagar == []
        assert plano.desatribuir == [("t-sistema", [MEDIADOR])]

    def test_tarefa_de_quem_ficou_nao_e_tocada(self):
        from services.task_assignment_hygiene import plano_de_limpeza

        tarefa = tarefa_humana(assigned_to=[MEDIADOR])
        plano = plano_de_limpeza([tarefa], removidos={CONSULTOR})
        assert plano.apagar == []
        assert plano.desatribuir == []

    def test_sem_removidos_nao_faz_nada(self):
        """Uma atribuição que só ACRESCENTA pessoas não pode mexer em nada."""
        from services.task_assignment_hygiene import plano_de_limpeza

        plano = plano_de_limpeza(
            [tarefa_do_sistema(), tarefa_humana()], removidos=set(),
        )
        assert plano.apagar == [] and plano.desatribuir == []

    def test_tarefa_com_escalar_tambem_e_tratada(self):
        """As tarefas da automação são precisamente as que ficam órfãs, e
        são as que têm a forma antiga. Se o plano não as normalizasse,
        escapavam à limpeza."""
        from services.task_assignment_hygiene import plano_de_limpeza

        tarefa = {
            "id": "t-automacao", "assigned_to": CONSULTOR, "source": "automation",
            "created_by": None, "completed": False,
            "created_at": CRIADA, "updated_at": CRIADA,
        }
        plano = plano_de_limpeza([tarefa], removidos={CONSULTOR})
        assert plano.apagar == ["t-automacao"]


class TestLimpezaAplicada:
    @pytest.mark.asyncio
    async def test_aplica_o_plano_na_base_de_dados(self, fake_async_db):
        import services.task_assignment_hygiene as higiene

        fake_async_db.tasks.docs.extend([
            tarefa_do_sistema(),
            tarefa_humana(),
            tarefa_humana(id="t-doutro", assigned_to=[OUTRO]),
        ])

        with patch.object(higiene, "db", fake_async_db):
            resumo = await higiene.limpar_tarefas_orfas("p-1", removidos={CONSULTOR})

        restantes = {t["id"] for t in fake_async_db.tasks.docs}
        assert restantes == {"t-humana", "t-doutro"}

        humana = next(t for t in fake_async_db.tasks.docs if t["id"] == "t-humana")
        assert humana["assigned_to"] == []
        assert humana["assignment_orphaned"] is True

        doutro = next(t for t in fake_async_db.tasks.docs if t["id"] == "t-doutro")
        assert doutro["assigned_to"] == [OUTRO]
        assert "assignment_orphaned" not in doutro

        assert resumo == {"apagadas": 1, "desatribuidas": 1}

    @pytest.mark.asyncio
    async def test_reatribuir_limpa_a_marca_de_orfa(self, fake_async_db):
        """Sem isto, a tarefa ficava para sempre a dizer que precisa de
        atenção depois de já a ter recebido."""
        import services.task_assignment_hygiene as higiene

        fake_async_db.tasks.docs.append(
            tarefa_humana(assigned_to=[], assignment_orphaned=True),
        )

        with patch.object(higiene, "db", fake_async_db):
            await higiene.marcar_reatribuidas("p-1", atribuidos={CONSULTOR})

        tarefa = fake_async_db.tasks.docs[0]
        assert tarefa.get("assignment_orphaned") is not True

    @pytest.mark.asyncio
    async def test_nunca_levanta(self, fake_async_db):
        """A limpeza corre DEPOIS de a atribuição já estar gravada. Levantar
        aqui mostraria um erro sobre uma operação bem sucedida."""
        import services.task_assignment_hygiene as higiene

        class BaseEmBaixo:
            def __getattr__(self, _nome):
                raise RuntimeError("Mongo em baixo")

        with patch.object(higiene, "db", BaseEmBaixo()):
            resumo = await higiene.limpar_tarefas_orfas("p-1", removidos={CONSULTOR})

        assert resumo == {"apagadas": 0, "desatribuidas": 0}


class TestLigacaoAoCaminhoDeAtribuicao:
    def test_a_atribuicao_de_staff_chama_mesmo_a_limpeza(self):
        """Contraprova: sem esta asserção, o serviço seria código morto —
        exactamente o que aconteceu com a revogação do Portal (ponto 6)."""
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2]
            / "services" / "process_staff_assignment.py"
        ).read_text("utf-8")
        assert "limpar_tarefas_orfas" in fonte

    def test_sair_do_processo_tambem_limpa(self):
        """Sair por `unassign-me` deixa exactamente as mesmas tarefas para
        trás que ser removido por um gestor — tratar só um dos caminhos
        deixaria metade do defeito de pé."""
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2]
            / "services" / "process_staff_assignment.py"
        ).read_text("utf-8")
        bloco = fonte[fonte.index("async def run_unassign_me_from_process"):]
        assert "limpar_tarefas_orfas" in bloco
