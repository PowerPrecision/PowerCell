"""O quadro deixou de perder cartões. (Épico 10, Parte 3)

ESTE FICHEIRO ESTAVA INVERTIDO
  Na versão anterior afirmava o comportamento ERRADO — 2 processos, 1
  cartão — porque era o que estava em produção e uma medição precisa de
  um ponto de partida. As asserções inverteram-se agora, e a inversão é
  a prova de que a correcção mordeu.

O DEFEITO, PARA MEMÓRIA
  `group_processes_by_status` agrupava por igualdade EXACTA da string; o
  contador do cabeçalho contava por `$in` COM os aliases. Um processo em
  `concluido` (singular), numa fase apagada ou com um espaço a mais não
  aparecia em coluna nenhuma e continuava a somar para o número lido por
  cima do quadro. Sem erro, sem log.

  O retrato de produção pôs números nisto: **342 processos invisíveis**
  em 12.450 — 205 com nome antigo, 12 com gralha, 125 em fases que o
  motor não tem.

A REGRA AGORA
  As colunas são ditadas pelo motor. O nome gravado passa pelo
  resolvedor; o que ele não reconhece vai para a coluna de
  reconciliação, visível a quem a pode arrumar. **Nenhum processo
  carregado desaparece do quadro.**
"""
import pytest

from services.process_kanban_enrichment import (
    build_active_inactive_count_queries,
    build_kanban_columns,
    group_processes_by_status,
)
from services.process_status import INACTIVE_STATUSES
from services.workflow_phases import (
    ETIQUETA_DESCONHECIDA,
    FASE_DESCONHECIDA,
    nomes_terminais,
)


def fase(nome, ordem=1, **extra):
    base = {"id": nome, "name": nome, "label": nome.title(), "order": ordem}
    base.update(extra)
    return base


MOTOR = [
    fase("clientes_espera", 1),
    fase("fase_documental", 2),
    fase("fase_escritura", 3),
    fase("concluidos", 4, is_active=False),
]


def montar(processos, fases=MOTOR, *, reconcilia=True):
    colunas = build_kanban_columns(
        fases,
        group_processes_by_status(processos, fases),
        {}, "utilizador",
        incluir_desconhecidas=reconcilia,
    )
    return colunas


def cartoes(colunas):
    return sum(c["count"] for c in colunas)


def coluna(colunas, nome):
    return next((c for c in colunas if c["name"] == nome), None)


# ====================================================================
# INVERTIDO: o que desaparecia, aparece
# ====================================================================

class TestNenhumCartaoSePerde:
    def test_o_singular_legado_cai_na_coluna_certa(self):
        """ANTES: 2 processos → 1 cartão. AGORA: 2 → 2."""
        processos = [
            {"id": "p1", "status": "concluidos"},
            {"id": "p2", "status": "concluido"},
        ]
        colunas = montar(processos)
        assert cartoes(colunas) == 2
        assert coluna(colunas, "concluidos")["count"] == 2
        assert coluna(colunas, FASE_DESCONHECIDA) is None

    def test_o_nome_antigo_do_produto_tambem(self):
        """`escriturado` era como `concluidos` se chamava."""
        colunas = montar([{"id": "p1", "status": "escriturado"}])
        assert coluna(colunas, "concluidos")["count"] == 1

    def test_a_gralha_invisivel_cai_na_coluna_certa(self):
        """Os 12 `Concluidos ` do retrato de produção."""
        colunas = montar([{"id": f"p{i}", "status": "Concluidos "} for i in range(12)])
        assert coluna(colunas, "concluidos")["count"] == 12

    @pytest.mark.parametrize("gravado", [
        "Clientes_Espera", "clientes_espera ", " clientes_espera",
        "clientes-espera", "CLIENTES_ESPERA",
    ])
    def test_todas_as_formas_da_mesma_gralha(self, gravado):
        colunas = montar([{"id": "p1", "status": gravado}])
        assert coluna(colunas, "clientes_espera")["count"] == 1

    def test_o_cartao_traduzido_diz_de_onde_veio(self):
        """A UI tem de poder mostrar que o cartão está ali por tradução.

        E o `status` GRAVADO não muda: a resolução é de leitura.
        """
        colunas = montar([{"id": "p1", "status": "escriturado"}])
        cartao = coluna(colunas, "concluidos")["processes"][0]
        assert cartao["status_resolvido_de"] == "escriturado"
        assert cartao["status"] == "escriturado"

    def test_o_cartao_exacto_nao_leva_o_campo(self):
        colunas = montar([{"id": "p1", "status": "concluidos"}])
        cartao = coluna(colunas, "concluidos")["processes"][0]
        assert "status_resolvido_de" not in cartao

    def test_a_resolucao_nao_muta_o_processo_de_entrada(self):
        """Cópia rasa: a lista original é usada noutros sítios do pedido."""
        processo = {"id": "p1", "status": "escriturado"}
        montar([processo])
        assert processo == {"id": "p1", "status": "escriturado"}


# ====================================================================
# INVERTIDO: o que sobra fica VISÍVEL, não some
# ====================================================================

class TestColunaDeReconciliacao:
    ORFAOS = [
        {"id": "o1", "status": "perdido"},
        {"id": "o2", "status": "cancelado"},
        {"id": "o3", "status": "arquivo"},
    ]

    def test_os_orfaos_juntam_se_numa_coluna(self):
        """Os 125 processos do retrato: `perdido`, `cancelado`, `arquivo`."""
        colunas = montar(self.ORFAOS)
        desconhecidas = coluna(colunas, FASE_DESCONHECIDA)
        assert desconhecidas["count"] == 3
        assert desconhecidas["label"] == ETIQUETA_DESCONHECIDA
        assert desconhecidas["reconciliacao"] is True

    def test_a_coluna_fica_no_fim(self):
        """Não é um passo do workflow — é uma caixa de entrada."""
        colunas = montar(self.ORFAOS + [{"id": "p", "status": "clientes_espera"}])
        assert colunas[-1]["name"] == FASE_DESCONHECIDA
        assert colunas[-1]["order"] > max(f["order"] for f in MOTOR)

    def test_quem_nao_reconcilia_nao_recebe_a_coluna(self):
        colunas = montar(self.ORFAOS, reconcilia=False)
        assert coluna(colunas, FASE_DESCONHECIDA) is None

    def test_sem_orfaos_a_coluna_nao_aparece(self):
        """Ruído permanente ensina toda a gente a ignorar o painel."""
        colunas = montar([{"id": "p", "status": "clientes_espera"}])
        assert coluna(colunas, FASE_DESCONHECIDA) is None

    def test_uma_fase_apagada_ja_nao_leva_os_processos_com_ela(self):
        """ANTES: 7 processos → 0 cartões."""
        processos = [{"id": f"p{i}", "status": "fase_extinta"} for i in range(7)]
        colunas = montar(processos)
        assert cartoes(colunas) == 7
        assert coluna(colunas, FASE_DESCONHECIDA)["count"] == 7


# ====================================================================
# A INVARIANTE
# ====================================================================

class TestInvariante:
    @pytest.mark.parametrize("estados", [
        ["clientes_espera", "concluido", "escriturado", "perdido", "xpto"],
        ["Concluidos ", "cpcv", "", "clientes_espera"],
        ["fase_inventada"] * 5,
        [],
    ])
    def test_nenhum_processo_carregado_desaparece(self, estados):
        processos = [{"id": f"p{i}", "status": e} for i, e in enumerate(estados)]
        assert cartoes(montar(processos)) == len(processos)

    def test_nenhum_processo_e_contado_duas_vezes(self):
        processos = [
            {"id": "p1", "status": "concluido"},
            {"id": "p2", "status": "escriturado"},
        ]
        vistos = [
            c["id"] for col in montar(processos) for c in col["processes"]
        ]
        assert sorted(vistos) == ["p1", "p2"]

    def test_o_contador_passa_a_usar_os_terminais_do_motor(self):
        """TESTE FRACO CORRIGIDO — sobreviveu à mutação M14.

        A versão anterior afirmava que `concluidos` estava no `$in` e
        `clientes_espera` não. Só que isso é verdade TAMBÉM com a lista
        legada: eu tinha escolhido dois nomes em que os dois dialectos
        concordam, e portanto não estava a testar nada.

        A asserção que distingue precisa de uma fase que seja terminal
        PARA O MOTOR e não exista na lista legada — uma fase que o admin
        fechou. Com a lista cravada, um processo lá dentro conta como
        activo para sempre.
        """
        motor = MOTOR + [fase("renegociacao", 5, is_active=False)]
        terminais = nomes_terminais(motor)
        assert "renegociacao" in terminais
        assert "renegociacao" not in INACTIVE_STATUSES  # não vem do legado

        _, inactivos = build_active_inactive_count_queries({}, terminais)
        assert "renegociacao" in inactivos["status"]["$in"]

        activos, _ = build_active_inactive_count_queries({}, terminais)
        assert "renegociacao" in activos["status"]["$nin"]

    def test_uma_fase_reaberta_pelo_admin_deixa_de_contar_como_fechada(self):
        """O outro lado: `is_active=True` vence a lista legada."""
        motor = [fase("concluidos", 1, is_active=True)]
        _, inactivos = build_active_inactive_count_queries(
            {}, nomes_terminais(motor),
        )
        assert "concluidos" not in inactivos["status"]["$in"]

    def test_o_contador_sem_motor_mantem_a_lista_legada(self):
        """Degradação: sem fases, o comportamento anterior, não o vazio."""
        _, inactivos = build_active_inactive_count_queries({})
        assert "concluidos" in inactivos["status"]["$in"]


# ====================================================================
# SEM MOTOR NÃO SE INVENTAM COLUNAS
# ====================================================================

class TestSemMotor:
    def test_sem_fases_o_agrupamento_volta_ao_exacto(self):
        """Não é compatibilidade: é a resposta certa quando não há motor.

        Inventar colunas a partir de nada seria pior do que agrupar pelo
        que está gravado.
        """
        agrupado = group_processes_by_status([{"id": "p", "status": "seja_o_que_for"}])
        assert list(agrupado) == ["seja_o_que_for"]

    def test_sem_fases_nao_ha_colunas(self):
        assert build_kanban_columns([], {}, {}, "u", incluir_desconhecidas=True) == []


class TestContraprova:
    """Sem isto, um `build_kanban_columns` que devolvesse sempre `[]`
    satisfazia metade das asserções acima."""

    def test_o_quadro_mostra_mesmo_o_que_esta_alinhado(self):
        processos = [
            {"id": "p1", "status": "clientes_espera"},
            {"id": "p2", "status": "clientes_espera"},
            {"id": "p3", "status": "concluidos"},
        ]
        assert cartoes(montar(processos)) == 3

    def test_as_colunas_saem_pela_ordem_das_fases(self):
        colunas = build_kanban_columns(MOTOR, {}, {}, "u")
        assert [c["name"] for c in colunas] == [f["name"] for f in MOTOR]
