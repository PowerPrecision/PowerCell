"""Quem está atribuído a um processo: UMA lista de campos, não quatro.

O QUE ESTAVA MAL (403 falso positivo, Set 2026)
==============================================
O QA reportou: "tenho o processo atribuído e os documentos dão 403". As
duas coisas eram verdade ao mesmo tempo, porque **cada lado lia uma
lista de campos diferente**:

  `process_list_filters.ASSIGNMENT_ID_FIELDS`  15 campos (a mais completa)
  `process_indexing.collect_assigned_user_ids`  5 campos, à mão
  `portal_assigned_users.get_all_assigned_user_ids`  6 campos, à mão

Às duas últimas faltavam `consultor_id`, `consultant_id` e `mediador_id`
— exactamente os singulares legados que o
`dual_auto_assign_on_pre_registo_transition` escrevia SOZINHOS antes da
correcção dos escritores canónicos.

Consequência exacta: o consultor via o processo em "Os Meus Processos"
(o `process_list_filters` lê `consultant_id`) e levava 403 na listagem
de documentos (o `document_visibility` chama o
`collect_assigned_user_ids`, que não lê). Foi essa metade a funcionar
que escondeu a outra — a forma do `run_get_my_tasks`.

E a ironia do nome: `process_portal_messages` chama o
`get_all_assigned_user_ids` "fonte de verdade" numa docstring, e ele era
uma das cópias incompletas.

A REGRA
=======
`ASSIGNMENT_ID_FIELDS` vive em `process_staff_assignment`, ao lado de
`CONSULTOR_ID_FIELDS`/`MEDIADOR_ID_FIELDS`, e **deriva delas**. Quem
precisa de saber se alguém está atribuído chama `collect_assigned_ids`.
Uma quarta lista escrita à mão é o defeito do Lote 5 outra vez.
"""
from __future__ import annotations

import pytest

from services.process_staff_assignment import (
    CONSULTOR_ID_FIELDS,
    MEDIADOR_ID_FIELDS,
    ASSIGNMENT_ID_FIELDS,
    collect_assigned_ids,
)


class TestOsSingularesLegadosContamComoAtribuicao:
    """O caso de produção: lista vazia, singular preenchido."""

    @pytest.mark.parametrize("campo", ["consultant_id", "consultor_id"])
    def test_o_consultor_legado_e_reconhecido(self, campo):
        processo = {"id": "p-1", "assigned_consultor_ids": [], campo: "u-1"}
        assert "u-1" in collect_assigned_ids(processo)

    def test_o_mediador_legado_e_reconhecido(self):
        processo = {"id": "p-1", "assigned_mediador_ids": [], "mediador_id": "u-2"}
        assert "u-2" in collect_assigned_ids(processo)

    def test_a_lista_continua_a_contar(self):
        processo = {"id": "p-1", "assigned_consultor_ids": ["u-3", "u-4"]}
        assert {"u-3", "u-4"} <= set(collect_assigned_ids(processo))

    def test_a_indexacao_e_o_parceiro_contam(self):
        processo = {
            "id": "p-1",
            "assigned_indexacao_id": "u-idx",
            "assigned_parceiro_id": "u-parc",
        }
        ids = set(collect_assigned_ids(processo))
        assert {"u-idx", "u-parc"} <= ids

    def test_nao_inventa_ninguem_num_processo_vazio(self):
        """Contraprova: devolver sempre algo tornaria o guard inútil."""
        assert collect_assigned_ids({"id": "p-1"}) == []

    def test_deduplica(self):
        """O mesmo id em seis campos é uma pessoa, não seis."""
        processo = {
            "assigned_consultor_ids": ["u-1"],
            "assigned_consultor_id": "u-1",
            "consultor_id": "u-1",
            "consultant_id": "u-1",
        }
        assert collect_assigned_ids(processo) == ["u-1"]

    def test_ignora_vazios_e_nulos(self):
        processo = {"assigned_consultor_id": "", "consultor_id": None, "mediador_id": "u-9"}
        assert collect_assigned_ids(processo) == ["u-9"]


class TestACONSTANTEDerivaEnaoEUmaQuartaCopia:
    def test_inclui_TODOS_os_campos_canonicos(self):
        """Deriva de `CONSULTOR_ID_FIELDS`/`MEDIADOR_ID_FIELDS`.

        Uma lista à mão divergiria dos escritores na primeira mudança, e
        quem divergisse recusaria acesso a quem está atribuído — sem dar
        erro nenhum.
        """
        for campo in (*CONSULTOR_ID_FIELDS, *MEDIADOR_ID_FIELDS):
            assert campo in ASSIGNMENT_ID_FIELDS, campo

    def test_o_process_list_filters_usa_A_MESMA_constante(self):
        """Era a única completa das três; agora é a mesma que as outras."""
        from services.process_list_filters import (
            ASSIGNMENT_ID_FIELDS as DA_LISTAGEM,
        )

        assert DA_LISTAGEM is ASSIGNMENT_ID_FIELDS

    def test_nao_perdeu_nenhum_campo_que_a_listagem_ja_lia(self):
        """Contraprova de regressão: unificar não pode ENCOLHER o conjunto.

        Se a unificação tivesse ficado pela interseção, utilizadores que
        hoje vêem processos deixariam de os ver.
        """
        ja_lidos = (
            "assigned_to", "assigned_consultor_ids", "assigned_consultor_id",
            "assigned_consultant_ids", "assigned_consultant_id",
            "assigned_mediador_ids", "assigned_mediador_id",
            "assigned_indexacao_id", "assigned_parceiro_id",
            "assigned_users", "assigned_user_ids",
            "consultant_id", "consultor_id", "mediador_id", "manager_id",
        )
        for campo in ja_lidos:
            assert campo in ASSIGNMENT_ID_FIELDS, campo


class TestOsTRESLeitoresConcordam:
    """O inventário dos sítios que decidem "está atribuído?".

    Um ponto único para a lista não basta — é preciso que cada leitor o
    use. É a lição do Lote 5, e é por isso que este teste compara os
    leitores REAIS entre si em vez de cada um contra uma expectativa.
    """

    PROCESSO_LEGADO = {
        "id": "p-1",
        "assigned_consultor_ids": [],
        "consultant_id": "u-legado",
    }

    def test_o_guard_dos_documentos_reconhece(self):
        from services.process_indexing import collect_assigned_user_ids

        assert "u-legado" in collect_assigned_user_ids(self.PROCESSO_LEGADO)

    def test_a_audiencia_do_portal_reconhece(self):
        from services.portal_assigned_users import get_all_assigned_user_ids

        assert "u-legado" in get_all_assigned_user_ids(self.PROCESSO_LEGADO)

    def test_os_tres_devolvem_O_MESMO_conjunto(self):
        from services.portal_assigned_users import get_all_assigned_user_ids
        from services.process_indexing import collect_assigned_user_ids

        processo = {
            "assigned_consultor_ids": ["u-a"],
            "consultant_id": "u-b",
            "assigned_mediador_id": "u-c",
            "mediador_id": "u-d",
            "assigned_indexacao_id": "u-e",
            "assigned_parceiro_id": "u-f",
        }
        canonico = set(collect_assigned_ids(processo))
        assert set(collect_assigned_user_ids(processo)) == canonico
        assert set(get_all_assigned_user_ids(processo)) == canonico


class TestGuardaDeFonte:
    """Nenhum leitor pode voltar a escrever a lista à mão."""

    def _fonte(self, funcao):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        return codigo_da_funcao_sem_comentarios(funcao).replace('"', "").replace("'", "")

    def test_o_guard_dos_documentos_delega(self):
        from services.process_indexing import collect_assigned_user_ids

        fonte = self._fonte(collect_assigned_user_ids)
        assert "collect_assigned_ids" in fonte
        assert "assigned_consultor_ids" not in fonte

    def test_a_audiencia_do_portal_delega(self):
        from services.portal_assigned_users import get_all_assigned_user_ids

        fonte = self._fonte(get_all_assigned_user_ids)
        assert "collect_assigned_ids" in fonte
        assert "assigned_mediador_ids" not in fonte

    def test_CONTRAPROVA_o_ponto_unico_le_mesmo_os_campos(self):
        """Sem isto, um `collect_assigned_ids` que devolvesse `[]`
        satisfazia as duas guardas acima."""
        fonte = self._fonte(collect_assigned_ids)
        assert "ASSIGNMENT_ID_FIELDS" in fonte
