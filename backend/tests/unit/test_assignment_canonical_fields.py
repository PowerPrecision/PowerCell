"""
Atribuição: o conjunto CANÓNICO de campos (Lote 5, ponto 4).

O QUE FALHOU NO UAT, E PORQUÊ O MEU TESTE DO LOTE 4 NÃO APANHOU
  No Lote 4 liguei a limpeza de tarefas órfãs ao diff da equipa antes e
  depois (`ids_atribuidos_do_processo`), que lê TODOS os campos canónicos
  — incluindo `consultor_id` e `consultant_id`, como o AGENTS.md manda.

  Mas `build_clear_consultor_fields` limpava só metade deles. Remover o
  consultor deixava `consultor_id` e `consultant_id` com o valor antigo,
  o diff dava CONJUNTO VAZIO e a limpeza nunca era chamada.

  O meu teste do Lote 4 passou porque construí os documentos à mão, com
  os campos coerentes. Nunca passou pelo construtor real. É o erro que
  este ficheiro existe para não se repetir: os testes desta regra usam
  SEMPRE os construtores de produção.

E É MAIOR DO QUE AS TAREFAS
  `process_list_filters` usa `consultant_id` em "Os Meus Processos". Com
  esse campo por limpar, o consultor removido CONTINUA A VER O PROCESSO
  na lista dele. Não é uma tarefa pendurada: é acesso a dados.

Referência da forma correcta: `client_assign.py` (AGENTS.md, "Atribuição:
campos CANÓNICOS").
"""
import pytest

from services.process_staff_assignment import (
    build_clear_consultor_fields,
    build_clear_mediador_fields,
    build_set_consultor_fields,
    build_set_mediador_fields,
)
from services.task_assignment_hygiene import ids_atribuidos_do_processo


RITA = "u-rita"
BRUNO = "u-bruno"

# AGENTS.md, "Atribuição: campos CANÓNICOS".
CAMPOS_CONSULTOR = {
    "assigned_consultor_id", "assigned_consultor_ids",
    "consultor_id", "consultant_id",
    "consultor_name", "consultor_names",
}
CAMPOS_MEDIADOR = {
    "assigned_mediador_id", "assigned_mediador_ids",
    "mediador_id",
    "mediador_name", "mediador_names",
}


class TestConjuntoCompleto:
    def test_atribuir_consultor_escreve_todos_os_campos(self):
        campos = build_set_consultor_fields([RITA], ["Rita"])
        assert CAMPOS_CONSULTOR <= set(campos), (
            f"faltam: {CAMPOS_CONSULTOR - set(campos)}"
        )

    def test_limpar_consultor_limpa_todos_os_campos(self):
        """O que partiu: limpar metade deixa o diff cego."""
        campos = build_clear_consultor_fields()
        assert CAMPOS_CONSULTOR <= set(campos), (
            f"por limpar: {CAMPOS_CONSULTOR - set(campos)}"
        )
        assert not any(campos[c] for c in CAMPOS_CONSULTOR)

    def test_atribuir_mediador_escreve_todos_os_campos(self):
        campos = build_set_mediador_fields([BRUNO], ["Bruno"])
        assert CAMPOS_MEDIADOR <= set(campos)

    def test_limpar_mediador_limpa_todos_os_campos(self):
        campos = build_clear_mediador_fields()
        assert CAMPOS_MEDIADOR <= set(campos)
        assert not any(campos[c] for c in CAMPOS_MEDIADOR)

    def test_o_singular_acompanha_o_plural(self):
        """`assigned_consultor_id` é o primeiro da lista — o cartão de
        contexto lê um, as listagens leem o outro."""
        campos = build_set_consultor_fields([RITA, BRUNO], ["Rita", "Bruno"])
        assert campos["assigned_consultor_id"] == RITA
        assert campos["consultor_id"] == RITA
        assert campos["consultant_id"] == RITA
        assert campos["assigned_consultor_ids"] == [RITA, BRUNO]


class TestODiffQueFalhou:
    """O cenário exacto do UAT, pelos construtores REAIS."""

    def _processo_com_consultor(self):
        processo = {"id": "p-1"}
        processo.update(build_set_consultor_fields([RITA], ["Rita"]))
        return processo

    def test_antes_de_remover_a_rita_esta_atribuida(self):
        assert ids_atribuidos_do_processo(self._processo_com_consultor()) == {RITA}

    def test_DEPOIS_de_remover_a_rita_NAO_esta_atribuida(self):
        """É esta a asserção que o Lote 4 não tinha. O diff
        `antes - depois` dava vazio e a limpeza nunca corria."""
        processo = self._processo_com_consultor()
        processo.update(build_clear_consultor_fields())

        assert ids_atribuidos_do_processo(processo) == set(), (
            "sobraram campos com o consultor removido: "
            f"{[k for k, v in processo.items() if v == RITA]}"
        )

    def test_o_diff_da_o_removido(self):
        processo = self._processo_com_consultor()
        antes = ids_atribuidos_do_processo(processo)
        processo.update(build_clear_consultor_fields())
        depois = ids_atribuidos_do_processo(processo)

        assert antes - depois == {RITA}

    def test_remover_o_consultor_nao_afecta_o_mediador(self):
        processo = self._processo_com_consultor()
        processo.update(build_set_mediador_fields([BRUNO], ["Bruno"]))
        processo.update(build_clear_consultor_fields())

        assert ids_atribuidos_do_processo(processo) == {BRUNO}


class TestOutroLadoDoMesmoDefeito:
    """`consultant_id` por limpar não pendura só a tarefa.

    `process_list_filters` usa-o em "Os Meus Processos": o consultor
    removido continuava a ver o processo na lista dele.
    """

    def test_o_processo_sai_de_os_meus_processos_do_removido(self):
        from services.process_list_filters import build_assigned_to_me_condition
        from tests.unit.conftest import FakeAsyncCollection

        processo = {"id": "p-1"}
        processo.update(build_set_consultor_fields([RITA], ["Rita"]))
        condicao = build_assigned_to_me_condition(RITA)
        assert FakeAsyncCollection._matches(processo, condicao)

        processo.update(build_clear_consultor_fields())
        assert not FakeAsyncCollection._matches(processo, condicao), (
            "o consultor removido continua a ver o processo em Os Meus Processos"
        )


class TestGuardaContraORegresso:
    def test_os_construtores_partilham_a_lista_de_campos(self):
        """Limpar e atribuir têm de tocar EXACTAMENTE no mesmo conjunto.

        Foi a divergência entre os dois — um escrevia quatro campos, o
        outro devia limpar seis — que produziu o defeito. Derivar ambos
        da mesma constante é o que impede que volte a divergir.
        """
        assert set(build_set_consultor_fields([RITA], ["Rita"])) == set(
            build_clear_consultor_fields()
        )
        assert set(build_set_mediador_fields([BRUNO], ["Bruno"])) == set(
            build_clear_mediador_fields()
        )
