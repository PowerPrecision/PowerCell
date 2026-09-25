"""O quadro perde cartões que o contador do cabeçalho conta.

ÉPICO 10, PARTE 3 — PROVA DO DEFEITO, ainda POR CORRIGIR.

O DEFEITO
  `group_processes_by_status` agrupa por igualdade EXACTA da string; o
  `build_kanban_columns` só lê as chaves que têm fase configurada. Mas o
  contador do cabeçalho (`build_active_inactive_count_queries`) conta por
  `$in` COM os aliases legados.

  Resultado: um processo em `concluido` (singular) ou numa fase que o
  admin apagou não aparece em coluna nenhuma — e continua a somar para o
  número que o utilizador lê por cima do quadro. Não há erro, não há log:
  o processo simplesmente não existe no ecrã de trabalho da equipa.

PORQUE É QUE ESTE FICHEIRO AFIRMA O COMPORTAMENTO ERRADO
  Porque ele é o que está em produção HOJE, e uma medição precisa de um
  ponto de partida que não seja uma frase numa conversa. Quando a Parte 1
  fechar o buraco (resolução por alias + coluna "Fases desconhecidas"),
  estas asserções INVERTEM-SE: passa a valer `cartoes == contados`, e a
  inversão é a prova de que a correcção mordeu.

  Não é um teste a abençoar o defeito — é o defeito a ficar preso por um
  teste, para não poder mudar sem alguém reparar.
"""
import pytest

from services.process_kanban_enrichment import (
    build_active_inactive_count_queries,
    build_kanban_columns,
    group_processes_by_status,
)


def fase(nome, ordem=1):
    return {"id": nome, "name": nome, "label": nome.title(), "order": ordem}


def montar(fases, processos):
    """Nº de cartões que o quadro mostraria para estes processos."""
    colunas = build_kanban_columns(
        fases, group_processes_by_status(processos), {}, "utilizador",
    )
    return sum(c["count"] for c in colunas)


class TestOQuadroPerdeCartoes:
    def test_o_singular_legado_desaparece_do_quadro(self):
        processos = [
            {"id": "p1", "status": "concluidos"},
            {"id": "p2", "status": "concluido"},
        ]
        assert montar([fase("concluidos")], processos) == 1

    def test_mas_o_contador_do_cabecalho_conta_os_dois(self):
        """O `$in` do contador conhece os aliases que o quadro ignora."""
        _, inactivos = build_active_inactive_count_queries({})
        valores = inactivos["status"]["$in"]
        assert "concluido" in valores and "concluidos" in valores

    def test_uma_fase_apagada_leva_os_processos_com_ela(self):
        """O caso real: `run_delete_workflow_status` move por nome exacto.

        O que ficou com o nome antigo deixa de ter coluna — para sempre,
        e sem ninguém saber.
        """
        processos = [{"id": f"p{i}", "status": "fase_extinta"} for i in range(7)]
        assert montar([fase("clientes_espera")], processos) == 0

    def test_nenhuma_coluna_recolhe_o_que_sobra(self):
        """Não existe hoje coluna de órfãos — é o que a Parte 1 acrescenta."""
        colunas = build_kanban_columns(
            [fase("clientes_espera")],
            group_processes_by_status([{"id": "p1", "status": "desconhecida"}]),
            {}, "utilizador",
        )
        assert [c["name"] for c in colunas] == ["clientes_espera"]

    @pytest.mark.parametrize("status_gravado", [
        "Clientes_Espera", "clientes_espera ", " clientes_espera",
    ])
    def test_uma_gralha_invisivel_tem_o_mesmo_efeito(self, status_gravado):
        """Um espaço à direita é outra chave no Mongo (Lote 5, ponto 2)."""
        processos = [{"id": "p1", "status": status_gravado}]
        assert montar([fase("clientes_espera")], processos) == 0


class TestContraprova:
    """Sem isto, um `build_kanban_columns` que devolvesse sempre `[]`
    satisfazia todas as asserções acima."""

    def test_o_quadro_mostra_mesmo_o_que_esta_alinhado(self):
        processos = [
            {"id": "p1", "status": "clientes_espera"},
            {"id": "p2", "status": "clientes_espera"},
            {"id": "p3", "status": "concluidos"},
        ]
        fases = [fase("clientes_espera", 1), fase("concluidos", 2)]
        assert montar(fases, processos) == 3

    def test_as_colunas_saem_pela_ordem_das_fases(self):
        colunas = build_kanban_columns(
            [fase("primeira", 1), fase("segunda", 2)], {}, {}, "u",
        )
        assert [c["name"] for c in colunas] == ["primeira", "segunda"]
