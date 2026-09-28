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
    ORIGEM_ATRIBUICAO_LEGADA,
    ORIGEM_ATRIBUIDO_INVALIDO,
    ORIGEM_INDEXACAO_NAS_LISTAS,
    ORIGEM_ORFAO,
    ORIGEM_DESATRIBUICAO,
    ORIGEM_INDETERMINADA,
    VEREDICTO_AMBIGUO,
    VEREDICTO_DIVERGENTE,
    VEREDICTO_EM_FALTA,
    correccao_do_processo,
    desfasamentos_do_processo,
    origem_do_ambiguo,
    reposicao_de_listas_do_processo,
    resumir,
    resumir_ambiguos,
)
from services.process_staff_assignment import (
    CONSULTOR_ID_FIELDS,
    PAPEIS_COMO_CONSULTOR,
    PAPEIS_COMO_MEDIADOR,
    PAPEL_DA_INDEXACAO,
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

        CORRECÇÃO (Lote 6): esta forma — `consultor_id` E `consultant_id`
        — é a do CLEAR antigo, não a da dupla auto-atribuição, que
        gravava apenas `consultant_id` (ver `git log` de
        `d8a739d1`). A distinção só ficou visível quando foi preciso
        classificar os 213 ambíguos de produção, e é ela que decide
        quem se pode limpar: ver `TestDeOndeVeioOAmbiguo`.
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


class TestDeOndeVeioOAmbiguo:
    """Lote 6 — desambiguar os 213 em vez de atirar uma moeda ao ar.

    Os dois escritores antigos deixavam rastos DIFERENTES, e é isso que
    transforma "indecidível" em "decidível com prova".
    """

    def test_a_assinatura_do_clear_antigo_e_uma_desatribuicao(self):
        """`consultor_id` + `consultant_id`, `assigned_consultor_id` limpo."""
        processo = {
            "assigned_consultor_ids": [],
            "assigned_consultor_id": None,
            "consultor_id": "ex",
            "consultant_id": "ex",
        }
        assert origem_do_ambiguo(processo, "consultor") == ORIGEM_DESATRIBUICAO

    def test_a_assinatura_da_dupla_auto_atribuicao_e_um_processo_com_dono(self):
        """Só `consultant_id` — era tudo o que esse escritor gravava.

        Este é o caso que o `--incluir-ambiguos` NÃO pode tocar: limpar
        aqui desatribui um processo que tem consultor a trabalhar nele.
        """
        processo = {
            "assigned_consultor_ids": [],
            "consultant_id": "consultor-real",
        }
        assert origem_do_ambiguo(processo, "consultor") == ORIGEM_ATRIBUICAO_LEGADA

    def test_o_mediador_nao_se_decide_pela_assinatura(self):
        """Contraprova honesta: os dois escritores deixavam `{mediador_id}`.

        Sem esta afirmação seria fácil acreditar que a classificação
        resolve tudo — e resolvê-lo por assinatura no mediador seria
        inventar uma prova que não existe.
        """
        processo = {"assigned_mediador_ids": [], "mediador_id": "alguem"}
        assert origem_do_ambiguo(processo, "mediador") == ORIGEM_INDETERMINADA

    def test_o_historico_decide_o_mediador(self):
        processo = {"assigned_mediador_ids": [], "mediador_id": "alguem"}
        historico = [
            {
                "field": "assigned_mediador_ids",
                "action": "Removeu todos os intermediários",
                "new_value": None,
            },
        ]
        assert (
            origem_do_ambiguo(processo, "mediador", historico=historico)
            == ORIGEM_DESATRIBUICAO
        )

    def test_o_historico_de_uma_dupla_auto_atribuicao_protege_o_mediador(self):
        processo = {"assigned_mediador_ids": [], "mediador_id": "alguem"}
        historico = [
            {
                "field": "assignment",
                "action": "Dupla auto-atribuição (pré-registo → pipeline): "
                          "Intermediário: Rui",
                "new_value": "Intermediário: Rui",
            },
        ]
        assert (
            origem_do_ambiguo(processo, "mediador", historico=historico)
            == ORIGEM_ATRIBUICAO_LEGADA
        )

    def test_conta_o_ULTIMO_acontecimento_e_nao_o_primeiro(self):
        """Atribuído, removido, e o singular ficou: é resíduo."""
        processo = {"assigned_mediador_ids": [], "mediador_id": "alguem"}
        historico = [
            {
                "field": "assignment",
                "action": "Dupla auto-atribuição: Intermediário: Rui",
                "new_value": "Intermediário: Rui",
            },
            {
                "field": "assigned_mediador_ids",
                "action": "Removeu todos os intermediários",
                "new_value": None,
            },
        ]
        assert (
            origem_do_ambiguo(processo, "mediador", historico=historico)
            == ORIGEM_DESATRIBUICAO
        )

    def test_um_registo_que_so_fala_do_consultor_nao_decide_o_mediador(self):
        """A entrada genérica `assignment` cobre os DOIS papéis."""
        processo = {"assigned_mediador_ids": [], "mediador_id": "alguem"}
        historico = [
            {
                "field": "assignment",
                "action": "Dupla auto-atribuição: Consultor: Ana",
                "new_value": "Consultor: Ana",
            },
        ]
        assert (
            origem_do_ambiguo(processo, "mediador", historico=historico)
            == ORIGEM_INDETERMINADA
        )

    def test_o_historico_ganha_a_assinatura(self):
        """Assinatura diz resíduo; o registo diz que foi atribuído."""
        processo = {
            "assigned_consultor_ids": [],
            "assigned_consultor_id": None,
            "consultor_id": "ex",
            "consultant_id": "ex",
        }
        historico = [
            {
                "field": "assignment",
                "action": "Dupla auto-atribuição: Consultor: Ana",
                "new_value": "Consultor: Ana",
            },
        ]
        assert (
            origem_do_ambiguo(processo, "consultor", historico=historico)
            == ORIGEM_ATRIBUICAO_LEGADA
        )


class TestOIncluirAmbiguosExigeProva:
    """A bandeira autoriza a escrita; não substitui a prova."""

    def test_limpa_o_residuo_provado(self):
        processo = {
            "assigned_consultor_ids": [],
            "assigned_consultor_id": None,
            "consultor_id": "ex",
            "consultant_id": "ex",
        }
        assert correccao_do_processo(processo, incluir_ambiguos=True) == {
            "consultor_id": None,
            "consultant_id": None,
        }

    def test_NAO_limpa_a_atribuicao_legada_nem_com_a_bandeira_ligada(self):
        """A guarda que impede desatribuir trabalho real."""
        processo = {
            "assigned_consultor_ids": [],
            "consultant_id": "consultor-real",
        }
        assert correccao_do_processo(processo, incluir_ambiguos=True) == {}

    def test_NAO_limpa_o_indeterminado_nem_com_a_bandeira_ligada(self):
        processo = {"assigned_mediador_ids": [], "mediador_id": "alguem"}
        assert correccao_do_processo(processo, incluir_ambiguos=True) == {}

    def test_o_inequivoco_continua_a_ser_corrigido_sem_bandeira(self):
        """Contraprova: a narrativa nova não apertou o que já era seguro."""
        processo = {
            "assigned_consultor_ids": ["u-1"],
            "assigned_consultor_id": "u-1",
            "consultor_id": "u-1",
        }
        assert correccao_do_processo(processo) == {"consultant_id": "u-1"}


class TestReporAListaEOCaminhoOposto:
    """Para um `atribuicao_legada` a correcção NÃO é limpar."""

    def test_repoe_a_lista_a_partir_do_singular(self):
        processo = {
            "assigned_consultor_ids": [],
            "consultant_id": "consultor-real",
        }
        assert reposicao_de_listas_do_processo(processo) == {
            "assigned_consultor_ids": ["consultor-real"]
        }

    def test_nao_toca_num_residuo_de_desatribuicao(self):
        """Repor aqui RE-ATRIBUIRIA um processo de onde alguém foi tirado."""
        processo = {
            "assigned_consultor_ids": [],
            "assigned_consultor_id": None,
            "consultor_id": "ex",
            "consultant_id": "ex",
        }
        assert reposicao_de_listas_do_processo(processo) == {}

    def test_nao_toca_num_indeterminado(self):
        processo = {"assigned_mediador_ids": [], "mediador_id": "alguem"}
        assert reposicao_de_listas_do_processo(processo) == {}

    def test_repoe_o_mediador_quando_o_historico_o_prova(self):
        processo = {"assigned_mediador_ids": [], "mediador_id": "rui"}
        historicos = {
            "mediador": [
                {
                    "field": "assignment",
                    "action": "Dupla auto-atribuição: Intermediário: Rui",
                    "new_value": "Intermediário: Rui",
                }
            ]
        }
        assert reposicao_de_listas_do_processo(
            processo, historicos_por_papel=historicos
        ) == {"assigned_mediador_ids": ["rui"]}

    def test_um_processo_com_lista_nao_e_tocado(self):
        processo = build_set_consultor_fields(["u-1"], ["Ana"])
        assert reposicao_de_listas_do_processo(processo) == {}


class TestOResumoPorOrigem:
    def test_conta_cada_papel_por_origem(self):
        processos = [
            {
                "id": "p-1",
                "assigned_consultor_ids": [],
                "assigned_consultor_id": None,
                "consultor_id": "ex",
                "consultant_id": "ex",
            },
            {"id": "p-2", "assigned_consultor_ids": [], "consultant_id": "real"},
            {"id": "p-3", "assigned_mediador_ids": [], "mediador_id": "alguem"},
        ]
        resumo = resumir_ambiguos(processos)

        assert resumo["por_papel_e_origem"] == {
            "consultor:desatribuicao": 1,
            "consultor:atribuicao_legada": 1,
            "mediador:indeterminada": 1,
        }
        assert resumo["processos_por_origem"][ORIGEM_ATRIBUICAO_LEGADA] == ["p-2"]

    def test_um_processo_coerente_nao_entra_na_contagem(self):
        processos = [build_set_consultor_fields(["u-1"], ["Ana"])]
        assert resumir_ambiguos(processos)["por_papel_e_origem"] == {}


class TestOResumoNaoContaDuasVezesOMesmoProcesso:
    """A lista dos indeterminados saía com ids repetidos.

    `processos_por_origem` acumulava por (processo, PAPEL): um processo
    com o consultor e o mediador ambíguos aparecia DUAS vezes, e o
    relatório anunciava "199 casos" sobre uma lista de 199 entradas que
    eram ~132 processos. Quem lê aquilo para decidir uma migração tem de
    saber se o número é de processos ou de papéis — e o rótulo dizia
    "casos", que não é nem uma coisa nem outra.
    """

    def _dois_papeis_ambiguos(self):
        return {
            "id": "p-1",
            "assigned_consultor_ids": [],
            "assigned_consultor_id": "u-c",
            "assigned_mediador_ids": [],
            "assigned_mediador_id": "u-m",
        }

    def test_o_mesmo_processo_aparece_UMA_vez_na_lista(self):
        resumo = resumir_ambiguos([self._dois_papeis_ambiguos()])
        assert resumo["processos_por_origem"][ORIGEM_INDETERMINADA] == ["p-1"]

    def test_mas_a_contagem_por_papel_continua_a_contar_os_DOIS(self):
        """Contraprova: deduplicar a lista não pode apagar a contagem.

        São dois problemas distintos no mesmo processo — um por papel — e
        é por papel que se decide o que fazer.
        """
        resumo = resumir_ambiguos([self._dois_papeis_ambiguos()])
        assert resumo["por_papel_e_origem"] == {
            "consultor:indeterminada": 1,
            "mediador:indeterminada": 1,
        }

    def test_a_lista_fica_ordenada_para_ser_comparavel(self):
        processos = [
            {"id": "p-b", "assigned_consultor_ids": [], "assigned_consultor_id": "u"},
            {"id": "p-a", "assigned_consultor_ids": [], "assigned_consultor_id": "u"},
        ]
        assert resumir_ambiguos(processos)["processos_por_origem"][
            ORIGEM_INDETERMINADA
        ] == ["p-a", "p-b"]


class TestQuemAparecNosAmbiguos:
    """A pergunta que o relatório não respondia — e é a que decide.

    Os 199 indeterminados de produção mostravam, nos exemplos, SEMPRE os
    mesmos dois ou três ids de utilizador. Isso não é actividade orgânica
    de pessoas a atribuir processos um a um: é uma escrita em massa. Mas
    para o afirmar era preciso ler os exemplos à mão e contar de cabeça.

    `responsaveis_por_origem` transforma "199 processos indecidíveis" em
    "duas pessoas a confirmar" — e é a diferença entre uma decisão e um
    encolher de ombros.
    """

    def test_conta_quantas_vezes_cada_id_aparece(self):
        processos = [
            {"id": "p-1", "assigned_consultor_ids": [], "assigned_consultor_id": "u-a"},
            {"id": "p-2", "assigned_consultor_ids": [], "assigned_consultor_id": "u-a"},
            {"id": "p-3", "assigned_consultor_ids": [], "assigned_consultor_id": "u-b"},
        ]
        resumo = resumir_ambiguos(processos)

        assert resumo["responsaveis_por_origem"][ORIGEM_INDETERMINADA] == {
            "u-a": 2,
            "u-b": 1,
        }

    def test_separa_por_ORIGEM_e_nao_mistura(self):
        """Um id que apareça em duas origens conta em cada uma."""
        processos = [
            {"id": "p-1", "assigned_consultor_ids": [], "assigned_consultor_id": "u-a"},
            {"id": "p-2", "assigned_consultor_ids": [], "consultant_id": "u-a"},
        ]
        resumo = resumir_ambiguos(processos)

        assert resumo["responsaveis_por_origem"][ORIGEM_INDETERMINADA] == {"u-a": 1}
        assert resumo["responsaveis_por_origem"][ORIGEM_ATRIBUICAO_LEGADA] == {"u-a": 1}

    def test_um_processo_coerente_nao_traz_ninguem(self):
        processos = [build_set_consultor_fields(["u-1"], ["Ana"])]
        assert resumir_ambiguos(processos)["responsaveis_por_origem"] == {}


class TestQuemEstaLaDecideOAmbiguo:
    """A terceira fonte de prova: o UTILIZADOR (Set 2026, fecho da limpeza).

    Os 199 indeterminados de produção não eram um bloco. Resolvidos os
    ids contra `db.users`, partiram-se em três grupos com respostas
    OPOSTAS:

      153 papéis  o utilizador **não existe**
       34 papéis  utilizador activo com o papel CERTO para o campo
       12 papéis  utilizador activo com papel `indexacao`

    A assinatura e o histórico não os distinguem — só saber quem lá
    está. Daí esta terceira fonte, e a ordem: o utilizador ganha ao
    registo, porque um processo atribuído a alguém que já não existe não
    tem dono, diga o histórico o que disser.

    A REGRA QUE ISTO FECHA
      **Limpar um órfão não desatribui ninguém.** O risco contra o qual
      todo este módulo foi construído — "limpar deixa o processo sem
      dono" — não se materializa quando o dono não existe: o processo já
      está sem dono, e o campo está a mentir.
    """

    def _processo(self, campo="assigned_consultor_id", valor="u-x"):
        lista = (
            "assigned_consultor_ids"
            if campo in CONSULTOR_ID_FIELDS
            else "assigned_mediador_ids"
        )
        return {"id": "p-1", lista: [], campo: valor}

    def test_utilizador_INEXISTENTE_e_orfao(self):
        processo = self._processo()
        assert (
            origem_do_ambiguo(processo, "consultor", utilizadores={"u-x": None})
            == ORIGEM_ORFAO
        )

    def test_o_orfao_ganha_ao_historico(self):
        """Mesmo com registo de atribuição: quem lá está já não existe."""
        processo = self._processo()
        historico = [
            {
                "field": "assignment",
                "action": "Dupla auto-atribuição: Consultor: Ana",
                "new_value": "Consultor: Ana",
            }
        ]
        assert (
            origem_do_ambiguo(
                processo, "consultor", historico=historico,
                utilizadores={"u-x": None},
            )
            == ORIGEM_ORFAO
        )

    def test_utilizador_activo_com_o_papel_CERTO_e_uma_atribuicao(self):
        processo = self._processo()
        utilizadores = {"u-x": {"role": "consultor", "is_active": True}}
        assert (
            origem_do_ambiguo(processo, "consultor", utilizadores=utilizadores)
            == ORIGEM_ATRIBUICAO_LEGADA
        )

    def test_o_diretor_tambem_serve_de_consultor(self):
        """Deriva de `PAPEIS_COMO_CONSULTOR` — não de uma lista à mão."""
        processo = self._processo()
        utilizadores = {"u-x": {"role": "diretor", "is_active": True}}
        assert (
            origem_do_ambiguo(processo, "consultor", utilizadores=utilizadores)
            == ORIGEM_ATRIBUICAO_LEGADA
        )

    def test_um_intermediario_num_campo_de_CONSULTOR_e_invalido(self):
        """O papel tem de bater com o CAMPO, não apenas ser atribuível."""
        processo = self._processo()
        utilizadores = {"u-x": {"role": "intermediario", "is_active": True}}
        assert (
            origem_do_ambiguo(processo, "consultor", utilizadores=utilizadores)
            == ORIGEM_ATRIBUIDO_INVALIDO
        )

    def test_o_mesmo_intermediario_num_campo_de_MEDIADOR_e_valido(self):
        """Contraprova: não é o papel que é mau, é o sítio."""
        processo = self._processo(campo="assigned_mediador_id")
        utilizadores = {"u-x": {"role": "intermediario", "is_active": True}}
        assert (
            origem_do_ambiguo(processo, "mediador", utilizadores=utilizadores)
            == ORIGEM_ATRIBUICAO_LEGADA
        )

    def test_o_perfil_INDEXACAO_nunca_e_um_atribuido(self):
        """O Índice tem carimbo próprio e não entra nas listas.

        É o caso real do `2285198b` ("654"): um utilizador de indexação
        em 12 campos de consultor. Repor a lista cimentaria um estado que
        as regras do produto não admitem.

        INVERTIDO (Set 2026): a origem deixou de ser `atribuido_invalido`
        e passou a ter nome próprio. O teste não mudou de sentido — mudou
        de destino, porque juntar este caso ao da conta inactiva metia
        duas provas opostas na mesma bandeira.
        """
        for papel, campo in (
            ("consultor", "assigned_consultor_id"),
            ("mediador", "assigned_mediador_id"),
        ):
            processo = self._processo(campo=campo)
            utilizadores = {"u-x": {"role": "indexacao", "is_active": True}}
            assert (
                origem_do_ambiguo(processo, papel, utilizadores=utilizadores)
                == ORIGEM_INDEXACAO_NAS_LISTAS
            )

    def test_utilizador_INACTIVO_nao_e_atribuicao_automatica(self):
        """Existe, mas saiu. Pode voltar — não se decide por automatismo."""
        processo = self._processo()
        utilizadores = {"u-x": {"role": "consultor", "is_active": False}}
        assert (
            origem_do_ambiguo(processo, "consultor", utilizadores=utilizadores)
            == ORIGEM_ATRIBUIDO_INVALIDO
        )

    def test_sem_mapa_de_utilizadores_o_comportamento_ANTIGO_mantem_se(self):
        """Contraprova: a fonte nova não pode alterar quem não a usa."""
        processo = {"id": "p-1", "assigned_consultor_ids": [], "consultant_id": "u-y"}
        assert origem_do_ambiguo(processo, "consultor") == ORIGEM_ATRIBUICAO_LEGADA

    def test_um_id_ausente_do_mapa_nao_e_tratado_como_orfao(self):
        """"Não perguntei" é diferente de "perguntei e não existe".

        Sem esta distinção, um mapa incompleto — uma consulta que falhou,
        um lote por resolver — apagaria atribuições boas em silêncio.
        """
        processo = self._processo()
        assert (
            origem_do_ambiguo(processo, "consultor", utilizadores={"outro": None})
            == ORIGEM_INDETERMINADA
        )


class TestLimparOrfaosEUmaOrdemPropria:
    def _orfao(self):
        return {
            "id": "p-1",
            "assigned_consultor_ids": [],
            "assigned_consultor_id": "u-fantasma",
        }

    def test_o_incluir_ambiguos_sozinho_NAO_toca_no_orfao(self):
        """Bandeiras distintas para provas distintas."""
        assert correccao_do_processo(
            self._orfao(),
            incluir_ambiguos=True,
            utilizadores={"u-fantasma": None},
        ) == {}

    def test_com_incluir_orfaos_o_campo_e_limpo(self):
        assert correccao_do_processo(
            self._orfao(),
            incluir_orfaos=True,
            utilizadores={"u-fantasma": None},
        ) == {"assigned_consultor_id": None}

    def test_o_incluir_orfaos_NAO_toca_numa_atribuicao_real(self):
        """A bandeira nova é cirúrgica: só o que não tem ninguém."""
        processo = self._orfao()
        assert correccao_do_processo(
            processo,
            incluir_orfaos=True,
            utilizadores={"u-fantasma": {"role": "consultor", "is_active": True}},
        ) == {}

    def test_nem_no_papel_invalido(self):
        """Um intermediário num campo de CONSULTOR: existe, está activo, e
        nenhuma das duas bandeiras lhe toca.

        O exemplo era o perfil `indexacao`; passou a ter bandeira própria,
        pelo que aqui deixou de provar o que este teste afirma.
        """
        processo = self._orfao()
        assert correccao_do_processo(
            processo,
            incluir_orfaos=True,
            incluir_ambiguos=True,
            utilizadores={
                "u-fantasma": {"role": "intermediario", "is_active": True}
            },
        ) == {}

    def test_repor_listas_alcanca_o_atribuido_existente(self):
        processo = self._orfao()
        assert reposicao_de_listas_do_processo(
            processo,
            utilizadores={"u-fantasma": {"role": "consultor", "is_active": True}},
        ) == {"assigned_consultor_ids": ["u-fantasma"]}

    def test_repor_listas_NAO_ressuscita_um_orfao(self):
        """Repor a lista de um utilizador que não existe é inventar equipa."""
        assert reposicao_de_listas_do_processo(
            self._orfao(), utilizadores={"u-fantasma": None}
        ) == {}


class TestLimparAIndexacaoEAUltimaOrdem:
    """Os 12 que sobreviveram: a mesma conta de Indexação em `assigned_consultor_id`.

    Ficavam em `atribuido_invalido`, que junta DUAS provas opostas:

      conta inactiva    um consultor a sério que saiu — o campo regista
                        uma atribuição REAL e a conta pode voltar;
      perfil indexacao  nunca foi uma atribuição, e reactivar a conta não
                        muda isso.

    Limpar o segundo é seguro pela MESMA razão que o órfão, por um
    caminho diferente: não desatribui ninguém. Não porque a pessoa não
    exista — existe e está activa — mas porque não é por este campo que
    ela vê o processo. Isso não é uma suposição: está afirmado abaixo
    contra o `process_list_filters` real.
    """

    def _indexador(self, campo="assigned_consultor_id"):
        return {
            "id": "p-1",
            "assigned_consultor_ids": [],
            "assigned_mediador_ids": [],
            campo: "u-indice",
        }

    def _mapa(self, is_active=True):
        return {"u-indice": {"role": PAPEL_DA_INDEXACAO, "is_active": is_active}}

    # ── A bandeira ──────────────────────────────────────────────────

    def test_o_incluir_ambiguos_sozinho_NAO_toca_na_indexacao(self):
        assert correccao_do_processo(
            self._indexador(), incluir_ambiguos=True, utilizadores=self._mapa()
        ) == {}

    def test_o_limpar_orfaos_sozinho_TAMBEM_nao_lhe_toca(self):
        """Bandeiras distintas para provas distintas.

        Quem autorizou limpar por ausência de utilizador não autorizou,
        com isso, limpar um utilizador que existe e está activo.
        """
        assert correccao_do_processo(
            self._indexador(), incluir_orfaos=True, utilizadores=self._mapa()
        ) == {}

    def test_com_incluir_indexacao_o_campo_e_limpo(self):
        assert correccao_do_processo(
            self._indexador(), incluir_indexacao=True, utilizadores=self._mapa()
        ) == {"assigned_consultor_id": None}

    def test_limpa_tambem_no_campo_do_mediador(self):
        assert correccao_do_processo(
            self._indexador(campo="assigned_mediador_id"),
            incluir_indexacao=True,
            utilizadores=self._mapa(),
        ) == {"assigned_mediador_id": None}

    # ── O que a bandeira NÃO alcança ────────────────────────────────

    def test_NAO_toca_numa_atribuicao_real(self):
        assert correccao_do_processo(
            self._indexador(),
            incluir_indexacao=True,
            utilizadores={"u-indice": {"role": "consultor", "is_active": True}},
        ) == {}

    def test_NAO_toca_num_consultor_INACTIVO(self):
        """A metade que ficou em `atribuido_invalido` continua intocável.

        É a contraprova da separação: se a bandeira nova varresse as duas,
        não teria valido a pena separá-las.
        """
        assert correccao_do_processo(
            self._indexador(),
            incluir_indexacao=True,
            utilizadores={"u-indice": {"role": "consultor", "is_active": False}},
        ) == {}

    def test_NAO_toca_num_orfao(self):
        assert correccao_do_processo(
            self._indexador(),
            incluir_indexacao=True,
            utilizadores={"u-indice": None},
        ) == {}

    def test_repor_listas_NUNCA_poe_a_indexacao_numa_lista(self):
        """Repor cimentaria o estado que as regras do produto não admitem."""
        assert reposicao_de_listas_do_processo(
            self._indexador(), utilizadores=self._mapa()
        ) == {}

    # ── O papel ganha ao estado da conta ────────────────────────────

    def test_um_indexador_INACTIVO_continua_a_ser_indexacao(self):
        """Reactivar a conta não a torna consultor: a ordem certa é papel
        primeiro, estado depois."""
        assert (
            origem_do_ambiguo(
                self._indexador(), "consultor", utilizadores=self._mapa(is_active=False)
            )
            == ORIGEM_INDEXACAO_NAS_LISTAS
        )

    def test_o_historico_nao_transforma_a_indexacao_em_atribuicao(self):
        historico = [
            {
                "field": "assignment",
                "action": "Dupla auto-atribuição: Consultor: 654",
                "new_value": "Consultor: 654",
            }
        ]
        assert (
            origem_do_ambiguo(
                self._indexador(),
                "consultor",
                historico=historico,
                utilizadores=self._mapa(),
            )
            == ORIGEM_INDEXACAO_NAS_LISTAS
        )

    # ── As contraprovas que sustentam a decisão ─────────────────────

    def test_a_indexacao_nao_esta_nas_tuplas_de_papeis_atribuiveis(self):
        """Guarda de fonte: se alguém a acrescentar, isto grita.

        A bandeira só é defensável enquanto o Índice não for um atribuído.
        """
        assert PAPEL_DA_INDEXACAO not in PAPEIS_COMO_CONSULTOR
        assert PAPEL_DA_INDEXACAO not in PAPEIS_COMO_MEDIADOR

    def test_limpar_NAO_tira_acesso_a_indexacao(self):
        """A razão pela qual isto é seguro, afirmada contra o código REAL.

        Se um dia a visibilidade do Índice passar a depender de
        `assigned_consultor_id`, limpar deixa de ser inócuo — e é este
        teste que o denuncia, não o relatório do script.

        Duas superfícies, dois testes: a listagem e o Kanban têm
        construtores SEPARADOS (a lição do Lote 5).
        """
        from models.auth import UserRole
        from services.process_list_filters import (
            build_kanban_role_base_query,
            build_role_visibility_conditions,
        )

        utilizador = {"id": "u-indice", "email": "indice@exemplo.pt"}

        listagem = build_role_visibility_conditions(utilizador, UserRole.INDEXACAO)
        kanban = build_kanban_role_base_query(utilizador, UserRole.INDEXACAO)

        for condicoes in (repr(listagem), repr(kanban)):
            assert "assigned_consultor_id" not in condicoes
            assert "assigned_mediador_id" not in condicoes
            # Contraprova: o carimbo próprio ESTÁ lá. Sem isto, um
            # construtor que devolvesse vazio passaria nas duas de cima.
            assert "assigned_indexacao_id" in condicoes
