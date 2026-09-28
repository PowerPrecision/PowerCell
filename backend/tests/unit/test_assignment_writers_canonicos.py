"""Quem ATRIBUI tem de escrever o conjunto canónico COMPLETO.

PORQUE É QUE ISTO EXISTE (Lote 6, ponto 8 — a leitura dos números)
==================================================================
O diagnóstico em produção devolveu, em 333 processos:

    divergente   0
    em_falta   297
    ambiguo    213

O `divergente` a zero foi o que desmontou a minha própria hipótese: não
há um único processo em que um campo singular aponte para alguém FORA da
lista. O `em_falta` a 297 mandou-me procurar a causa no sítio certo — e
ela **não é histórico**: `apply_creator_role_assignment` (criação de
processo) e o bloco equivalente do `client_assign` escreviam CINCO dos
seis campos canónicos do consultor, deixando de fora `consultant_id`; no
mediador deixavam de fora `mediador_id`. Cada processo criado nascia
desfasado. Corrigir a base de dados sem corrigir estes dois escritores
seria esfregar o chão com a torneira aberta.

A regra do Lote 5 — "o `set` e o `clear` derivam da MESMA constante" —
tinha sido aplicada aos construtores e **não** a quem os devia usar.

O ORÁCULO DESTES TESTES
=======================
Não afirmam uma lista de campos escrita à mão (seria a quarta cópia da
lista, que é o defeito com outro nome): afirmam que o documento
produzido pelo escritor REAL tem zero desfasamentos segundo o detector
REAL. Acrescentar um campo canónico novo passa a ser detectado aqui sem
tocar neste ficheiro.
"""
from __future__ import annotations

import pytest

from services.assignment_drift import desfasamentos_do_processo
from services.process_staff_assignment import (
    CONSULTOR_ID_FIELDS,
    MEDIADOR_ID_FIELDS,
)


class TestACriacaoDeProcessoCarimbaOConjuntoCompleto:
    """`process_create.apply_creator_role_assignment` — o criador."""

    @pytest.mark.parametrize("papel", ["consultor", "diretor"])
    def test_criador_consultor_nao_deixa_desfasamento(self, papel):
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc, {"id": "u-1", "name": "Ana", "effective_role": papel}
        )

        assert doc["assigned_consultor_ids"] == ["u-1"]
        assert desfasamentos_do_processo(doc) == []

    def test_criador_intermediario_nao_deixa_desfasamento(self):
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc, {"id": "u-2", "name": "Rui", "effective_role": "intermediario"}
        )

        assert doc["assigned_mediador_ids"] == ["u-2"]
        assert desfasamentos_do_processo(doc) == []

    def test_o_campo_que_faltava_e_mesmo_escrito(self):
        """Contraprova dirigida: sem ela, um detector preguiçoso passa.

        `consultant_id` é o campo que o escritor omitia, e é o que
        `process_list_filters` usa em "Os Meus Processos".
        """
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc, {"id": "u-1", "name": "Ana", "effective_role": "consultor"}
        )
        for campo in CONSULTOR_ID_FIELDS:
            assert doc[campo] == "u-1", f"{campo} por escrever"

    def test_o_campo_que_faltava_no_mediador_e_mesmo_escrito(self):
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc, {"id": "u-2", "name": "Rui", "effective_role": "intermediario"}
        )
        for campo in MEDIADOR_ID_FIELDS:
            assert doc[campo] == "u-2", f"{campo} por escrever"

    def test_um_papel_sem_atribuicao_nao_carimba_nada(self):
        """Contraprova: admin não é consultor nem mediador."""
        from services.process_create import apply_creator_role_assignment

        doc = {}
        apply_creator_role_assignment(
            doc, {"id": "u-9", "name": "Chefe", "effective_role": "admin"}
        )
        assert doc == {}


class TestAAtribuicaoDeClienteCarimbaOConjuntoCompleto:
    """`client_assign` — a Sala de Triagem."""

    def test_alvo_consultor_nao_deixa_desfasamento(self):
        from services.client_assign import apply_target_role_assignment

        doc = {}
        apply_target_role_assignment(
            doc, {"id": "u-3", "name": "Marta", "role": "consultor"}
        )

        assert doc["assigned_consultor_ids"] == ["u-3"]
        assert desfasamentos_do_processo(doc) == []

    def test_alvo_intermediario_nao_deixa_desfasamento(self):
        from services.client_assign import apply_target_role_assignment

        doc = {}
        apply_target_role_assignment(
            doc, {"id": "u-4", "name": "Jorge", "role": "intermediario"}
        )

        assert doc["assigned_mediador_ids"] == ["u-4"]
        assert desfasamentos_do_processo(doc) == []

    def test_alvo_indexacao_continua_a_ter_campo_proprio(self):
        """O Índice não é consultor: carimbo próprio, sem lista."""
        from services.client_assign import apply_target_role_assignment

        doc = {}
        apply_target_role_assignment(
            doc, {"id": "u-5", "name": "Índice", "role": "indexacao"}
        )

        assert doc == {"assigned_indexacao_id": "u-5"}
        assert desfasamentos_do_processo(doc) == []


class TestADuplaAutoAtribuicaoUsaOsMesmosConstrutores:
    """O terceiro escritor — já completo, agora derivado da constante."""

    def test_o_bloco_do_consultor_nao_deixa_desfasamento(self):
        from services.process_staff_assignment import build_set_consultor_fields

        doc = build_set_consultor_fields(["u-6"], ["Sofia"])
        assert desfasamentos_do_processo(doc) == []


class TestODiretorTemOsMesmosDeveresDoConsultor:
    """Ponto 9, fio solto 3 — os dois escritores divergiam no `diretor`.

    `process_create` tratava o diretor como consultor
    (``effective in [CONSULTOR, DIRETOR]``); o `client_assign` só
    conhecia `"consultor"`, pelo que um cliente atribuído a um diretor
    pela Sala de Triagem nascia com processo e **sem atribuição
    nenhuma** — nem lista, nem singulares, nem nome. Não dava erro: o
    processo simplesmente não era de ninguém, e um processo sem dono não
    se nota até alguém reparar que ninguém lhe pega.

    Era a MESMA forma do defeito dos campos — a decisão escrita à mão em
    dois sítios —, só que num eixo diferente: ali divergia a lista de
    CAMPOS, aqui a lista de PAPÉIS. Por isso a correcção também é a
    mesma: uma constante, não uma segunda cópia.
    """

    def test_o_diretor_e_atribuido_como_consultor(self):
        from services.client_assign import apply_target_role_assignment

        doc = {}
        apply_target_role_assignment(
            doc, {"id": "u-dir", "name": "Marta Diretora", "role": "diretor"}
        )

        assert doc["assigned_consultor_ids"] == ["u-dir"]
        assert doc["consultor_names"] == ["Marta Diretora"]
        assert desfasamentos_do_processo(doc) == []

    def test_os_dois_escritores_concordam_sobre_quem_e_consultor(self):
        """A contraprova que impede a divergência de voltar.

        Compara os escritores REAIS papel a papel. Uma lista de papéis
        escrita à mão neste teste seria a terceira cópia.
        """
        from services.client_assign import apply_target_role_assignment
        from services.process_create import apply_creator_role_assignment
        from services.process_staff_assignment import (
            PAPEIS_COMO_CONSULTOR,
            PAPEIS_COMO_MEDIADOR,
        )

        for papel in (*PAPEIS_COMO_CONSULTOR, *PAPEIS_COMO_MEDIADOR):
            do_criador = {}
            apply_creator_role_assignment(
                do_criador, {"id": "u-1", "name": "Ana", "effective_role": papel}
            )
            do_alvo = {}
            apply_target_role_assignment(
                do_alvo, {"id": "u-1", "name": "Ana", "role": papel}
            )

            assert do_criador == do_alvo, (
                f"os dois escritores divergem no papel {papel!r} — foi "
                "exactamente assim que o diretor ficou sem atribuição"
            )

    def test_um_papel_fora_das_constantes_continua_sem_atribuicao(self):
        """Contraprova no sentido oposto: alargar não é alargar a todos.

        Sem isto, fazer os dois concordarem atribuindo SEMPRE também
        passaria — e um `parceiro` ou um `administrativo` passaria a ser
        carimbado como consultor do processo.
        """
        from services.client_assign import apply_target_role_assignment

        for papel in ("administrativo", "parceiro", "ceo"):
            doc = {}
            apply_target_role_assignment(
                doc, {"id": "u-x", "name": "Alguém", "role": papel}
            )
            assert doc == {}, f"{papel} não é um atribuído do processo"
