"""O retrato do `processes.status` contra o motor de workflow.

Épico 10, Parte 3, Passo Zero. Ver `services/workflow_status_coverage.py`
e `scripts/medir_status_producao.py`.

Estes testes cobrem a lógica PURA da medição. O script que fala com a base
de dados fica coberto por uma guarda sobre o código-fonte (no fim do
ficheiro) que afirma o que ele NÃO faz: escrever.
"""
import pathlib

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios
from services.workflow_status_coverage import (
    ALIASES_LEGADOS_DO_PRODUTO,
    MACRO_FASES_DE_HOJE,
    MACRO_FASES_PROPOSTAS,
    MACRO_FASES_VALIDAS,
    analisar,
    candidatos_de_alias,
    construir_tabela_de_aliases,
    formatar_relatorio,
    normalizar_para_gralha,
    para_json,
)

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]


def fase(nome, **extra):
    base = {"id": nome, "name": nome, "label": nome, "order": 1}
    base.update(extra)
    return base


# ====================================================================
# A TABELA DE ALIASES
# ====================================================================

class TestTabelaDeAliases:
    def test_funde_as_duas_tabelas_que_hoje_vivem_separadas(self):
        """`escriturado` (frontend) e `concluido` (backend) são o mesmo grupo.

        Antes desta fusão, o backend só sabia de singular/plural e o
        frontend só sabia dos nomes antigos: procurar por `escriturado`
        no backend não encontrava `concluidos`.
        """
        tabela = construir_tabela_de_aliases()
        assert "concluidos" in tabela["escriturado"]
        assert "concluido" in tabela["escriturado"]
        assert "escriturado" in tabela["concluido"]

    def test_a_relacao_e_simetrica(self):
        tabela = construir_tabela_de_aliases()
        for nome, outros in tabela.items():
            for outro in outros:
                assert nome in tabela[outro], f"{nome} ↔ {outro} não é simétrico"

    def test_ninguem_e_alias_de_si_proprio(self):
        for nome, outros in construir_tabela_de_aliases().items():
            assert nome not in outros

    def test_as_desistencias_todas_no_mesmo_grupo(self):
        """`recusado`, `desistiu`, `desistido` e `desistencia` são um só."""
        tabela = construir_tabela_de_aliases()
        grupo = tabela["desistencias"] | {"desistencias"}
        assert {"recusado", "desistiu", "desistido", "desistencia"} <= grupo

    def test_candidatos_so_devolve_fases_que_o_motor_conhece(self):
        """A regra do alias: o destino tem de existir."""
        assert candidatos_de_alias("escriturado", ["concluidos"]) == ["concluidos"]
        assert candidatos_de_alias("escriturado", ["outra_coisa"]) == []

    def test_candidatos_devolve_varios_quando_ha_ambiguidade(self):
        """Com duas fases do mesmo grupo configuradas, não se escolhe."""
        candidatos = candidatos_de_alias("escriturado", ["concluido", "concluidos"])
        assert candidatos == ["concluido", "concluidos"]

    def test_a_copia_portada_nao_diverge_do_frontend(self):
        """`ALIASES_LEGADOS_DO_PRODUTO` é um PORTE do mapa do frontend.

        Duas cópias da mesma tabela em linguagens diferentes divergem em
        silêncio: editar uma deixa a outra a traduzir fases que já não
        existem. Esta guarda lê o original em
        `frontend/src/utils/processTimeline.js` e exige que sejam o mesmo
        conjunto. A Parte 1 mata a duplicação; até lá, ela é vigiada.
        """
        import re

        origem = (
            RAIZ_BACKEND.parent / "frontend" / "src" / "utils" / "processTimeline.js"
        ).read_text(encoding="utf-8")
        bloco = re.search(
            r"const ALIASES_LEGADOS\s*=\s*\{(.*?)\};", origem, re.S,
        )
        assert bloco, "o mapa mudou de forma no frontend — rever este porte"
        do_frontend = dict(
            re.findall(r'(\w+)\s*:\s*"([^"]+)"', bloco.group(1))
        )
        assert do_frontend == ALIASES_LEGADOS_DO_PRODUTO


# ====================================================================
# GRALHAS INVISÍVEIS
# ====================================================================

class TestGralhas:
    @pytest.mark.parametrize("gravado", [
        "Concluidos", "concluidos ", " concluidos", "CONCLUIDOS", "concluidos",
    ])
    def test_normalizacao_apanha_capitalizacao_e_espacos(self, gravado):
        assert normalizar_para_gralha(gravado) == "concluidos"

    def test_hifen_e_underscore_sao_a_mesma_gralha(self):
        assert normalizar_para_gralha("fase-documental") == "fase_documental"

    def test_none_nao_rebenta(self):
        assert normalizar_para_gralha(None) == ""

    def test_a_gralha_resolve_para_a_fase_certa(self):
        """INVERTIDO pela decisão de produto sobre o retrato de produção.

        Antes, uma gralha ficava órfã: "não se adivinha". Mas `"Concluidos "`
        não é uma adivinhação — é a MESMA string, mal gravada, e a
        normalização cai numa única fase configurada. Adivinhar é escolher
        entre candidatos; isto é reconhecer.

        Continua a aparecer em `suspeitas_de_gralha`: o dado gravado está
        errado e quem reconcilia tem de o ver, mesmo com o cartão já na
        coluna certa.
        """
        retrato = analisar({"Concluidos ": 3}, [fase("concluidos")])
        assert retrato.suspeitas_de_gralha == {"Concluidos ": "concluidos"}
        assert retrato.orfaos_resoluveis == {"Concluidos ": "concluidos"}
        assert "Concluidos " not in retrato.orfaos_desconhecidos

    def test_a_gralha_ambigua_continua_a_nao_ser_adivinhada(self):
        """Duas fases que normalizam para a mesma chave → ninguém escolhe."""
        retrato = analisar(
            {"escritura ": 3}, [fase("escritura"), fase("Escritura")],
        )
        assert retrato.orfaos_resoluveis == {}
        assert "escritura " in retrato.orfaos_desconhecidos


# ====================================================================
# O RETRATO
# ====================================================================

class TestAnalisar:
    def test_status_com_fase_nao_e_orfao(self):
        retrato = analisar({"clientes_espera": 10}, [fase("clientes_espera")])
        assert retrato.processos_orfaos == 0
        assert retrato.percentagem_coberta == 100.0

    def test_orfao_com_alias_unico_e_resoluvel(self):
        retrato = analisar(
            {"concluidos": 5, "escriturado": 2}, [fase("concluidos")],
        )
        assert retrato.orfaos_resoluveis == {"escriturado": "concluidos"}
        assert retrato.orfaos_ambiguos == {}
        assert retrato.processos_orfaos == 2

    def test_orfao_com_dois_candidatos_nao_e_adivinhado(self):
        """A disciplina do `rede_consensual`: mais do que um → ninguém."""
        retrato = analisar(
            {"escriturado": 7}, [fase("concluido"), fase("concluidos")],
        )
        assert retrato.orfaos_resoluveis == {}
        assert retrato.orfaos_ambiguos == {"escriturado": ["concluido", "concluidos"]}
        assert retrato.processos_orfaos == 7

    def test_orfao_sem_candidato_nenhum(self):
        retrato = analisar({"fase_inventada": 4}, [fase("clientes_espera")])
        assert retrato.orfaos_desconhecidos == {"fase_inventada": 4}
        assert retrato.processos_orfaos == 4

    def test_as_tres_categorias_somam_os_invisiveis(self):
        retrato = analisar(
            {
                "clientes_espera": 100,   # tem fase
                "escriturado": 2,         # resolúvel
                "recusado": 3,            # resolúvel
                "fase_inventada": 4,      # desconhecido
            },
            [fase("clientes_espera"), fase("concluidos"), fase("desistencias")],
        )
        assert retrato.processos_orfaos == 9
        assert retrato.processos_totais == 109

    def test_sem_status_conta_a_parte_e_nao_como_orfao(self):
        """Uma lead do formulário público não é uma fase perdida."""
        retrato = analisar({"clientes_espera": 10}, [fase("clientes_espera")],
                           sem_status=5)
        assert retrato.sem_status == 5
        assert retrato.processos_orfaos == 0
        assert retrato.processos_totais == 15

    def test_fases_sem_um_unico_processo_sao_listadas(self):
        retrato = analisar({"clientes_espera": 1},
                           [fase("clientes_espera"), fase("fase_morta")])
        assert retrato.fases_sem_processos == ["fase_morta"]

    def test_colecao_de_fases_vazia_torna_tudo_orfao(self):
        """Sem fases o Kanban não tem colunas — e o retrato di-lo."""
        retrato = analisar({"clientes_espera": 10}, [])
        assert retrato.processos_orfaos == 10
        assert retrato.percentagem_coberta == 0.0

    def test_sem_processos_nenhuns_nao_divide_por_zero(self):
        retrato = analisar({}, [fase("clientes_espera")])
        assert retrato.percentagem_coberta == 0.0
        assert retrato.processos_orfaos == 0

    def test_eliminados_ficam_a_parte(self):
        """Um soft-delete não é uma fase do workflow."""
        retrato = analisar(
            {"clientes_espera": 10}, [fase("clientes_espera")],
            contagens_eliminados={"eliminado": 400},
        )
        assert retrato.processos_totais == 10
        assert retrato.contagens_eliminados == {"eliminado": 400}

    def test_fase_sem_nome_e_ignorada_sem_rebentar(self):
        retrato = analisar({"x": 1}, [fase("x"), {"id": "sem_nome"}, "lixo"])
        assert retrato.fases_configuradas == ["x"]


# ====================================================================
# MACRO-FASES
# ====================================================================

class TestMacroFases:
    def test_nenhuma_fase_esta_em_dois_grupos(self):
        """O defeito do Lote 5: `escritura` estava em Aprovado E Concluído."""
        for grupos in (MACRO_FASES_DE_HOJE, MACRO_FASES_PROPOSTAS):
            vistos = {}
            for macro, nomes in grupos.items():
                for nome in nomes:
                    assert nome not in vistos, (
                        f"{nome} está em '{vistos.get(nome)}' e em '{macro}'"
                    )
                    vistos[nome] = macro

    def test_os_grupos_propostos_sao_o_enum_fechado(self):
        assert set(MACRO_FASES_PROPOSTAS) == set(MACRO_FASES_VALIDAS)

    def test_a_proposta_acrescenta_perdido_e_so_alarga_o_resto(self):
        """AJUSTADO: a proposta agora também acolhe fases de produção.

        Antes era "não mexe no resto". O retrato de produção trouxe
        `renegociacao` e `pausa_cliente` — fases criadas pelo admin que
        nenhum grupo cobria — e a decisão foi mapeá-las para "Em Análise"
        até serem editáveis na UI.

        A invariante que interessa não é "os grupos não mudam": é que a
        proposta nunca REMOVE uma fase de um grupo, só acrescenta. Remover
        seria um processo a mudar de sítio no funil sem ninguém pedir.
        """
        assert set(MACRO_FASES_PROPOSTAS) - set(MACRO_FASES_DE_HOJE) == {"perdido"}
        for macro, nomes in MACRO_FASES_DE_HOJE.items():
            assert set(nomes) <= set(MACRO_FASES_PROPOSTAS[macro])

    def test_as_fases_novas_de_producao_ficam_em_analise(self):
        retrato = analisar(
            {"renegociacao": 1, "pausa_cliente": 1},
            [fase("renegociacao"), fase("pausa_cliente")],
        )
        assert retrato.macro_proposta == {
            "renegociacao": "analise", "pausa_cliente": "analise",
        }
        assert retrato.fases_sem_macro_proposta == []
        # Hoje continuam sem grupo — é a diferença que a Parte 2 fecha.
        assert set(retrato.fases_sem_macro_hoje) == {"renegociacao", "pausa_cliente"}

    def test_as_desistencias_hoje_nao_pertencem_a_grupo_nenhum(self):
        """É o buraco que a proposta fecha, e o retrato mostra-o."""
        retrato = analisar({"desistencias": 12}, [fase("desistencias")])
        assert retrato.fases_sem_macro_hoje == ["desistencias"]
        assert retrato.macro_proposta["desistencias"] == "perdido"
        assert retrato.fases_sem_macro_proposta == []

    def test_fase_criada_pelo_admin_nao_cabe_em_grupo_nenhum(self):
        """Uma fase nova fica sem macro-fase nos dois mapas — e é dito."""
        retrato = analisar({"fase_do_admin": 3}, [fase("fase_do_admin")])
        assert "fase_do_admin" in retrato.fases_sem_macro_hoje
        assert "fase_do_admin" in retrato.fases_sem_macro_proposta


# ====================================================================
# AS LISTAS CRAVADAS, MEDIDAS
# ====================================================================

class TestListasCravadas:
    def test_so_sobram_as_duas_listas_que_sao_residuo_legado(self):
        """INVERTIDO: as três do `stats_branches` já não existem.

        Antes media-se cinco listas. As do BI foram implodidas na Parte
        3 e não há nada para medir onde não há lista.
        """
        retrato = analisar({"clientes_espera": 10}, [fase("clientes_espera")])
        assert set(retrato.cobertura_das_listas) == {
            "process_status.INACTIVE_STATUSES",
            "process_status.ARCHIVED_STATUSES",
        }

    def test_o_funil_bi_passou_a_medir_fases_que_existem(self):
        """A INVERSÃO PRINCIPAL desta parte.

        Antes: `stats_branches._COMPLETED_STATUSES` procurava
        `concluido`/`arquivo`, a fase terminal chamava-se `concluidos`, e
        o tempo médio de fecho por balcão saía de um conjunto vazio — 0
        de 12.450 processos, apresentado como um número no dashboard.

        Agora os conjuntos vêm do motor por macro-fase, e são
        exactamente os nomes que o motor tem.
        """
        from services.workflow_phases import nomes_activos, nomes_por_macro

        fases_do_seed = [
            fase(n) for n in (
                "clientes_espera", "fase_documental", "fase_bancaria",
                "ch_aprovado", "fase_escritura", "escritura_agendada",
            )
        ] + [
            fase("concluidos", is_active=False),
            fase("desistencias", is_active=False),
        ]

        concluidos = nomes_por_macro(fases_do_seed, "concluido")
        assert concluidos == ["concluidos"]

        aprovados = nomes_por_macro(fases_do_seed, "aprovado", "concluido")
        assert set(aprovados) == {
            "ch_aprovado", "fase_escritura", "escritura_agendada", "concluidos",
        }

        activos = nomes_activos(fases_do_seed)
        assert "clientes_espera" in activos
        assert "concluidos" not in activos and "desistencias" not in activos

        # A propriedade que faltava: TUDO o que o BI mede existe no motor.
        conhecidas = {f["name"] for f in fases_do_seed}
        for conjunto in (concluidos, aprovados, activos):
            assert set(conjunto) <= conhecidas

    def test_uma_fase_nova_entra_no_bi_sem_deploy(self):
        """Era isto que uma lista cravada tornava impossível."""
        from services.workflow_phases import nomes_por_macro

        fases = [fase("concluidos", is_active=False), fase("arquivo_morto")]
        assert nomes_por_macro(fases, "concluido") == ["concluidos"]

        fases[1]["macro_fase"] = "concluido"
        assert nomes_por_macro(fases, "concluido") == ["concluidos", "arquivo_morto"]

    def test_contraprova_uma_lista_alinhada_apanharia_os_processos(self):
        """Sem isto, a asserção acima passaria com a medição sempre a zero."""
        retrato = analisar({"concluidos": 500}, [fase("concluidos")])
        medida = retrato.cobertura_das_listas["process_status.ARCHIVED_STATUSES"]
        assert "concluidos" in medida["existem_no_motor"]
        assert medida["processos_abrangidos"] == 500


# ====================================================================
# SAÍDAS
# ====================================================================

class TestSaidas:
    def test_o_relatorio_nomeia_os_orfaos(self):
        retrato = analisar(
            {"clientes_espera": 10, "fase_inventada": 4},
            [fase("clientes_espera")],
        )
        texto = formatar_relatorio(retrato)
        assert "fase_inventada" in texto
        assert "INVISÍVEIS NO KANBAN" in texto

    def test_o_relatorio_aguenta_um_retrato_vazio(self):
        assert formatar_relatorio(analisar({}, []))

    def test_o_json_leva_a_tabela_de_aliases(self):
        """É o `aliases_list` pedido: discutir sobre os mesmos números."""
        saida = para_json(analisar({"x": 1}, [fase("x")]))
        assert "concluidos" in saida["aliases_list"]["escriturado"]
        assert saida["macro_fases_validas"] == list(MACRO_FASES_VALIDAS)

    def test_o_json_e_serializavel(self):
        import json
        retrato = analisar(
            {"clientes_espera": 3, "escriturado": 1, "zzz": 2},
            [fase("clientes_espera"), fase("concluidos")],
            contagens_eliminados={"eliminado": 9},
            sem_status=4,
        )
        assert json.loads(json.dumps(para_json(retrato), ensure_ascii=False))


# ====================================================================
# GUARDA: O SCRIPT NÃO ESCREVE
# ====================================================================

class TestOScriptSoLe:
    """Este script corre contra PRODUÇÃO por desenho.

    Não chama o `env_guard` — o guarda existe para impedir que um seed
    escreva em produção, e é contra produção que isto tem de correr. O
    que o torna seguro é não haver uma única operação de escrita no
    ficheiro, e é isso que se afirma aqui.
    """

    CAMINHO = RAIZ_BACKEND / "scripts" / "medir_status_producao.py"

    @pytest.fixture(scope="class")
    def fonte(self):
        # Sem comentários: a docstring EXPLICA que não há `--aplicar`, e
        # sem esta limpeza a explicação fazia a guarda ficar vermelha.
        return codigo_sem_comentarios(self.CAMINHO.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("escrita", [
        "update_one", "update_many", "insert_one", "insert_many",
        "delete_one", "delete_many", "replace_one", "bulk_write",
        "find_one_and_update", "find_one_and_delete", "drop",
        "$set", "$unset", "$pull", "$push",
    ])
    def test_nenhuma_operacao_de_escrita(self, fonte, escrita):
        assert escrita not in fonte

    def test_nao_tem_flag_aplicar(self, fonte):
        assert "--aplicar" not in fonte

    def test_contraprova_le_mesmo_as_duas_coleccoes(self, fonte):
        """Sem isto, apagar o script inteiro satisfazia as guardas acima."""
        assert "db.processes.aggregate" in fonte
        assert "db.workflow_statuses.find" in fonte

    def test_a_agregacao_exclui_os_eliminados_por_omissao(self, fonte):
        assert "is_deleted" in fonte
