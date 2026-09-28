"""
Testes unitários — desfasamento entre a lista de atribuídos e os singulares.

Ver `services/assignment_drift.py` para o porquê. O que estes testes
protegem, e que é a parte fácil de errar: **"lista vazia + singular
preenchido" NÃO é resíduo por definição.** O
`dual_auto_assign_on_pre_registo_transition` gravava só `consultant_id`,
pelo que há processos legitimamente atribuídos cuja lista nunca foi
escrita — e limpá-los desatribui trabalho real. Esse caso é `ambiguo` e
fica fora da correcção automática.
"""
from __future__ import annotations

import pytest

from services.assignment_drift import (
    VEREDICTO_AMBIGUO,
    VEREDICTO_DIVERGENTE,
    VEREDICTO_EM_FALTA,
    correccao_do_processo,
    desfasamentos_do_processo,
    resumir,
)
from services.process_staff_assignment import (
    build_clear_consultor_fields,
    build_set_consultor_fields,
)


class TestUmProcessoCoerenteNaoEstaDesfasado:
    def test_atribuido_pelos_construtores_de_producao(self):
        """Usa os construtores REAIS, nunca um documento montado à mão.

        Foi montar os documentos à mão — já com os campos coerentes — que
        fez o meu teste do Lote 4 passar sobre o defeito do Lote 5.
        """
        processo = build_set_consultor_fields(["u-1", "u-2"], ["Ana", "Rui"])
        assert desfasamentos_do_processo(processo) == []

    def test_desatribuido_pelos_construtores_de_producao(self):
        processo = build_clear_consultor_fields()
        assert desfasamentos_do_processo(processo) == []

    def test_um_processo_sem_campos_nenhuns(self):
        """Por atribuir não é desfasado — é por atribuir."""
        assert desfasamentos_do_processo({"id": "p-1"}) == []


class TestOResiduoDoLote5:
    """O defeito real: `consultor_id`/`consultant_id` por limpar."""

    def test_o_clear_antigo_deixava_dois_campos_para_tras(self):
        # Reprodução do que o `build_clear_consultor_fields` fazia ANTES
        # do Lote 5: limpava a lista e os nomes, não os dois singulares.
        processo = {
            "assigned_consultor_ids": [],
            "consultor_names": [],
            "assigned_consultor_id": None,
            "consultor_id": "ex-consultor",
            "consultant_id": "ex-consultor",
        }
        desfasados = desfasamentos_do_processo(processo)

        campos = {d.campo for d in desfasados}
        assert campos == {"consultor_id", "consultant_id"}
        # Lista vazia → indecidível a partir do documento.
        assert all(d.veredicto == VEREDICTO_AMBIGUO for d in desfasados)

    def test_esse_caso_NAO_e_corrigido_automaticamente(self):
        """A guarda que impede desatribuir trabalho legado.

        Um processo do `dual_auto_assign_on_pre_registo_transition` tem
        exactamente esta forma e está LEGITIMAMENTE atribuído.
        """
        processo = {
            "assigned_consultor_ids": [],
            "consultor_id": "ex-consultor",
            "consultant_id": "ex-consultor",
        }
        assert correccao_do_processo(processo) == {}

    def test_mas_corrige_se_lhe_derem_ordem_explicita(self):
        processo = {
            "assigned_consultor_ids": [],
            "consultor_id": "ex-consultor",
            "consultant_id": "ex-consultor",
        }
        correccao = correccao_do_processo(processo, incluir_ambiguos=True)
        assert correccao == {"consultor_id": None, "consultant_id": None}


class TestOsCasosInequivocos:
    def test_singular_a_apontar_para_fora_da_lista_e_divergente(self):
        processo = {
            "assigned_consultor_ids": ["u-novo"],
            "assigned_consultor_id": "u-novo",
            "consultor_id": "u-antigo",
            "consultant_id": "u-novo",
        }
        desfasados = desfasamentos_do_processo(processo)
        assert len(desfasados) == 1
        assert desfasados[0].campo == "consultor_id"
        assert desfasados[0].veredicto == VEREDICTO_DIVERGENTE
        assert correccao_do_processo(processo) == {"consultor_id": "u-novo"}

    def test_singular_vazio_com_lista_cheia_esta_em_falta(self):
        """Este PERDE notificações — o sinal contrário ao relatado."""
        processo = {
            "assigned_consultor_ids": ["u-1"],
            "assigned_consultor_id": "u-1",
            "consultor_id": None,
            "consultant_id": "u-1",
        }
        desfasados = desfasamentos_do_processo(processo)
        assert [d.veredicto for d in desfasados] == [VEREDICTO_EM_FALTA]
        assert correccao_do_processo(processo) == {"consultor_id": "u-1"}

    def test_o_primeiro_id_da_lista_e_o_esperado(self):
        processo = {
            "assigned_consultor_ids": ["u-1", "u-2"],
            "assigned_consultor_id": "u-2",
            "consultor_id": "u-1",
            "consultant_id": "u-1",
        }
        assert correccao_do_processo(processo) == {"assigned_consultor_id": "u-1"}


class TestOMediadorSegueAMesmaRegra:
    def test_mediador_divergente(self):
        processo = {
            "assigned_mediador_ids": ["m-novo"],
            "assigned_mediador_id": "m-antigo",
            "mediador_id": "m-novo",
        }
        desfasados = desfasamentos_do_processo(processo)
        assert [d.papel for d in desfasados] == ["mediador"]
        assert correccao_do_processo(processo) == {"assigned_mediador_id": "m-novo"}


class TestOsCamposVemDasConstantesDeProducao:
    def test_cobre_os_tres_campos_do_consultor(self):
        """Contraprova: uma lista escrita à mão aqui divergiria do `clear`.

        Se alguém acrescentar um campo canónico e não o puser em
        `CONSULTOR_ID_FIELDS`, o `set`/`clear` e este diagnóstico divergem
        — e o diagnóstico passa a declarar "sem desfasamento" um processo
        desfasado.
        """
        processo = {
            "assigned_consultor_ids": ["u-1"],
            "assigned_consultor_id": "x",
            "consultor_id": "x",
            "consultant_id": "x",
        }
        campos = {d.campo for d in desfasamentos_do_processo(processo)}
        from services.process_staff_assignment import CONSULTOR_ID_FIELDS

        assert campos == set(CONSULTOR_ID_FIELDS)


class TestOResumo:
    def test_conta_processos_e_campos(self):
        processos = [
            build_set_consultor_fields(["u-1"], ["Ana"]),          # coerente
            {"assigned_consultor_ids": [], "consultor_id": "ex"},   # ambíguo
            {                                                       # divergente
                "assigned_consultor_ids": ["u-9"],
                "assigned_consultor_id": "u-9",
                "consultor_id": "u-8",
                "consultant_id": "u-9",
            },
        ]
        resumo = resumir(processos)

        assert resumo["total_analisados"] == 3
        assert resumo["processos_afectados"] == 2
        assert resumo["processos_corrigiveis"] == 1
        assert resumo["processos_ambiguos"] == 1
        assert resumo["por_veredicto"][VEREDICTO_AMBIGUO] == 1
        assert resumo["por_veredicto"][VEREDICTO_DIVERGENTE] == 1
        assert resumo["por_campo"]["consultor_id"] == 2

    def test_um_conjunto_vazio_nao_inventa_numeros(self):
        resumo = resumir([])
        assert resumo["total_analisados"] == 0
        assert resumo["processos_afectados"] == 0
        assert resumo["por_campo"] == {}
