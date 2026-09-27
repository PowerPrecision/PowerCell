"""
O retrato do relógio de fases — Refinamento Analítico e SLAs, Passo Zero.

Ver `services/phase_clock_coverage.py` e `scripts/medir_relogio_de_fases.py`.

O QUE ESTES TESTES DEFENDEM
  1. Que a medição resolve os valores gravados pelo MOTOR. Os 205
     processos em `cpcv`/`escriturado` e as 12 gralhas `"Concluidos "`
     contam na macro-fase certa, como já contam no quadro. Se a medição
     os deixasse cair em "desconhecido", o retrato diria que 217
     processos não têm grupo quando o Kanban lhes desenha a coluna
     correcta — duas verdades sobre os mesmos dados, que é o erro que o
     Épico 10 fechou.
  2. Que um instante que não se consegue ler conta como AUSENTE e nunca
     como "agora". Era o erro fácil: inflacionava a cobertura do relógio
     e a permanência aparecia como zero dias.
  3. Que o carimbo REAL ganha ao aproximado. Depois do backfill os dois
     coexistem no mesmo documento, e medir pelo `updated_at` quando há
     `fase_desde` tornaria o retrato cego ao próprio trabalho.
  4. Que o script não escreve. Corre contra produção de propósito (por
     isso não chama o `env_guard`), e é a ausência de operações de
     escrita que o torna seguro.

`agora` é sempre INJECTADO. Uma medição que dependesse do relógio da
máquina não se conseguia afirmar aqui.
"""
import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios
from services.workflow_phases import FASE_DESCONHECIDA, MACRO_FASES_VALIDAS
from services.phase_clock_coverage import (
    CAMPO_ESTIMADO,
    CAMPO_FASE_DESDE,
    CAMPO_MACRO_DESDE,
    CAMPO_TEMPOS,
    ETIQUETAS_DAS_BANDAS,
    Retrato,
    analisar,
    banda_de_dias,
    dias_entre,
    formatar_relatorio,
    instante,
    mediana,
    para_json,
)

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]

AGORA = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)


def fase(nome, **extra):
    base = {"id": nome, "name": nome, "label": nome, "order": 1}
    base.update(extra)
    return base


# O motor tal como o retrato de produção o mostrou: a fase terminal
# chama-se `concluidos` (plural) e existe uma `fase_escritura`.
FASES = [
    fase("clientes_espera", macro_fase="novo"),
    fase("analise_documental", macro_fase="analise"),
    fase("pre_aprovado", macro_fase="aprovado"),
    fase("fase_escritura", macro_fase="aprovado"),
    fase("concluidos", macro_fase="concluido", is_active=False),
]


def processo(**campos):
    """Linha crua como a projecção do script a devolve."""
    base = {
        "status": "analise_documental",
        "created_at": (AGORA - timedelta(days=100)).isoformat(),
        "updated_at": (AGORA - timedelta(days=10)).isoformat(),
    }
    base.update(campos)
    return base


# ====================================================================
# LEITURA DE INSTANTES
# ====================================================================

class TestInstante:
    def test_iso_com_z(self):
        lido = instante("2026-09-01T10:00:00Z")
        assert lido == datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

    def test_iso_com_fuso_explicito(self):
        assert instante("2026-09-01T10:00:00+00:00").tzinfo is not None

    def test_iso_sem_fuso_assume_utc(self):
        """A colecção tem os dois formatos no mesmo campo."""
        assert instante("2026-09-01T10:00:00") == datetime(
            2026, 9, 1, 10, 0, tzinfo=timezone.utc,
        )

    def test_datetime_nativo_do_mongo(self):
        cru = datetime(2026, 9, 1, 10, 0)
        assert instante(cru).tzinfo is not None

    def test_datetime_ja_com_fuso_fica_igual(self):
        cru = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
        assert instante(cru) is cru

    @pytest.mark.parametrize("lixo", [None, "", "  ", "ontem", "0000", 17, [], {}])
    def test_o_que_nao_se_le_e_ausente_nunca_agora(self, lixo):
        """O erro fácil: cair em `datetime.now()` e inflacionar a cobertura.

        Um instante ilegível tem de valer `None` — o processo conta como
        SEM carimbo, que é a verdade. Se valesse "agora", a permanência
        dele aparecia como zero dias e o retrato dizia que o relógio
        estava em dia.
        """
        assert instante(lixo) is None


class TestDiasEBandas:
    def test_dias_entre_conta_fraccoes(self):
        assert dias_entre(AGORA - timedelta(hours=36), AGORA) == pytest.approx(1.5)

    @pytest.mark.parametrize("falta", [(None, AGORA), (AGORA, None), (None, None)])
    def test_dias_entre_exige_os_dois_instantes(self, falta):
        assert dias_entre(*falta) is None

    @pytest.mark.parametrize("dias,esperado", [
        (0, "0-7"), (7.9, "0-7"),
        (8, "8-15"), (15.9, "8-15"),
        (16, "16-30"), (30.9, "16-30"),
        (31, "31-60"), (60.9, "31-60"),
        (61, "61+"), (4000, "61+"),
    ])
    def test_fronteiras_das_bandas(self, dias, esperado):
        assert banda_de_dias(dias) == esperado

    def test_dias_negativos_nao_tem_banda(self):
        """`updated_at` anterior a `created_at` é dado corrompido, não uma banda."""
        assert banda_de_dias(-3) is None
        assert banda_de_dias(None) is None

    def test_as_bandas_cobrem_todas_as_etiquetas(self):
        """Contraprova: uma etiqueta que nenhum valor alcance é decorativa."""
        alcancadas = {banda_de_dias(d) for d in (1, 10, 20, 45, 900)}
        assert alcancadas == set(ETIQUETAS_DAS_BANDAS)


class TestMediana:
    def test_amostra_impar(self):
        assert mediana([5, 1, 3]) == 3

    def test_amostra_par_e_a_media_dos_dois_centrais(self):
        assert mediana([1, 2, 3, 4]) == 2.5

    def test_amostra_vazia(self):
        assert mediana([]) is None

    def test_a_mediana_resiste_ao_processo_esquecido(self):
        """É por isto que o relatório não mostra só a média.

        Nove processos em 5 dias e um esquecido há 400: a média diz 44,5
        dias e não existe processo nenhum perto disso.
        """
        amostra = [5.0] * 9 + [400.0]
        assert mediana(amostra) == 5.0
        media = sum(amostra) / len(amostra)
        assert media > 40


# ====================================================================
# A ANÁLISE
# ====================================================================

class TestMacroFasesResolvidas:
    def test_alias_conta_na_macro_da_fase_de_destino(self):
        """`cpcv` não existe no motor; `fase_escritura` existe e é `aprovado`.

        É o teste discriminante deste ficheiro: se a medição agrupasse
        pelo valor CRU, este processo caía em desconhecido e o retrato
        contradizia o quadro, que já lhe desenha a coluna certa.
        """
        retrato = analisar([processo(status="cpcv")], FASES, agora=AGORA)

        assert retrato.por_macro["aprovado"] == 1
        assert retrato.por_macro[FASE_DESCONHECIDA] == 0
        assert retrato.desconhecidos_por_valor == {}

    def test_gralha_conta_na_fase_certa(self):
        """`"Concluidos "` é `concluidos` mal gravado, não uma fase antiga."""
        retrato = analisar([processo(status="Concluidos ")], FASES, agora=AGORA)

        assert retrato.por_macro["concluido"] == 1
        assert retrato.por_macro[FASE_DESCONHECIDA] == 0

    def test_valor_que_o_motor_nao_conhece_fica_visivel(self):
        """`perdido` existe em dados reais e não é fase — não se esconde."""
        retrato = analisar(
            [processo(status="perdido"), processo(status="perdido")],
            FASES, agora=AGORA,
        )

        assert retrato.por_macro[FASE_DESCONHECIDA] == 2
        assert retrato.desconhecidos_por_valor == {"perdido": 2}

    def test_processo_sem_status_e_contado_a_parte(self):
        retrato = analisar([processo(status=None)], FASES, agora=AGORA)

        assert retrato.sem_status == 1
        assert retrato.por_macro[FASE_DESCONHECIDA] == 1

    def test_nada_se_perde_pelo_caminho(self):
        """A soma das macro-fases é sempre o total. Invariante do funil."""
        linhas = [
            processo(status="clientes_espera"),
            processo(status="analise_documental"),
            processo(status="cpcv"),
            processo(status="Concluidos "),
            processo(status="perdido"),
            processo(status=None),
        ]
        retrato = analisar(linhas, FASES, agora=AGORA)

        assert sum(retrato.por_macro.values()) == retrato.total == len(linhas)

    def test_o_campo_do_admin_vence_o_mapa_de_omissao(self):
        """Uma fase reclassificada na UI muda de grupo no retrato."""
        fases = [fase("analise_documental", macro_fase="aprovado")]
        retrato = analisar(
            [processo(status="analise_documental")], fases, agora=AGORA,
        )

        assert retrato.por_macro["aprovado"] == 1
        assert retrato.por_macro["analise"] == 0

    def test_sem_fases_nenhum_valor_se_resolve(self):
        """Motor vazio: tudo desconhecido, e o retrato di-lo em vez de rebentar."""
        retrato = analisar([processo(status="analise_documental")], [], agora=AGORA)

        assert retrato.por_macro[FASE_DESCONHECIDA] == 1


class TestCoberturaDoRelogio:
    def test_antes_do_backfill_nada_tem_carimbo(self):
        retrato = analisar([processo(), processo()], FASES, agora=AGORA)

        assert retrato.cobertura_do_relogio["com_fase_desde"] == 0
        assert retrato.cobertura_do_relogio["sem_fase_desde"] == 2
        assert retrato.cobertura_do_relogio["estimados"] == 0

    def test_conta_os_carimbos_que_existirem(self):
        linhas = [
            processo(**{
                CAMPO_FASE_DESDE: (AGORA - timedelta(days=3)).isoformat(),
                CAMPO_MACRO_DESDE: (AGORA - timedelta(days=3)).isoformat(),
                CAMPO_ESTIMADO: True,
                CAMPO_TEMPOS: {"analise": 900},
            }),
            processo(),
        ]
        retrato = analisar(linhas, FASES, agora=AGORA)
        cob = retrato.cobertura_do_relogio

        assert cob["com_fase_desde"] == 1
        assert cob["sem_fase_desde"] == 1
        assert cob["estimados"] == 1
        assert cob["com_macro_fase_desde"] == 1
        assert cob["com_tempos_macro"] == 1

    def test_tempos_macro_vazio_nao_conta_como_carimbo(self):
        """`{}` é o campo criado e nunca incrementado — não é cobertura."""
        retrato = analisar(
            [processo(**{CAMPO_TEMPOS: {}})], FASES, agora=AGORA,
        )

        assert retrato.cobertura_do_relogio["com_tempos_macro"] == 0

    def test_o_carimbo_real_vence_o_aproximado(self):
        """Discriminante: os dois campos divergem 297 dias.

        Se a medição continuasse a usar o `updated_at` depois do
        backfill, o retrato ficava cego ao trabalho que o backfill fez.
        """
        linha = processo(
            updated_at=(AGORA - timedelta(days=300)).isoformat(),
            **{CAMPO_FASE_DESDE: (AGORA - timedelta(days=3)).isoformat()},
        )
        retrato = analisar([linha], FASES, agora=AGORA)
        perm = retrato.permanencia_por_macro["analise"]

        assert perm.bandas["0-7"] == 1
        assert perm.bandas["61+"] == 0
        assert perm.mediana_dias == pytest.approx(3.0)

    def test_sem_carimbo_usa_o_aproximado(self):
        """Contraprova do teste anterior: sem `fase_desde` mede o `updated_at`."""
        linha = processo(updated_at=(AGORA - timedelta(days=300)).isoformat())
        retrato = analisar([linha], FASES, agora=AGORA)

        assert retrato.permanencia_por_macro["analise"].bandas["61+"] == 1


class TestQualidadeDoAproximado:
    def test_nunca_tocado_e_sinalizado(self):
        """`updated_at == created_at`: a estimativa cai na data de criação."""
        criado = (AGORA - timedelta(days=200)).isoformat()
        retrato = analisar(
            [processo(created_at=criado, updated_at=criado)], FASES, agora=AGORA,
        )

        assert retrato.proxy_suspeito["nunca_tocado"] == 1

    def test_processo_tocado_depois_de_criado_nao_e_sinalizado(self):
        retrato = analisar([processo()], FASES, agora=AGORA)

        assert retrato.proxy_suspeito["nunca_tocado"] == 0

    def test_terminal_tocado_ha_pouco_e_criado_ha_muito(self):
        """O caso que SUBESTIMA: parece ter entrado na fase esta semana."""
        linha = processo(
            status="concluidos",
            created_at=(AGORA - timedelta(days=400)).isoformat(),
            updated_at=(AGORA - timedelta(days=2)).isoformat(),
        )
        retrato = analisar([linha], FASES, agora=AGORA)

        assert retrato.proxy_suspeito["tocado_apos_fecho"] == 1

    def test_processo_activo_tocado_ha_pouco_nao_e_suspeito(self):
        """Num processo em curso, um toque recente é trabalho normal."""
        linha = processo(
            status="analise_documental",
            created_at=(AGORA - timedelta(days=400)).isoformat(),
            updated_at=(AGORA - timedelta(days=2)).isoformat(),
        )
        retrato = analisar([linha], FASES, agora=AGORA)

        assert retrato.proxy_suspeito["tocado_apos_fecho"] == 0

    def test_terminal_recente_mas_novo_nao_e_suspeito(self):
        """Criado e fechado na mesma semana: a estimativa está certa."""
        linha = processo(
            status="concluidos",
            created_at=(AGORA - timedelta(days=5)).isoformat(),
            updated_at=(AGORA - timedelta(days=1)).isoformat(),
        )
        retrato = analisar([linha], FASES, agora=AGORA)

        assert retrato.proxy_suspeito["tocado_apos_fecho"] == 0

    def test_data_invertida_nao_conta_como_nunca_tocado(self):
        """Apanhado por mutação (M11): `==` contra `<=`.

        Um `updated_at` anterior ao `created_at` é dado corrompido e já
        está contado em `datas_invalidas`. Contá-lo também aqui
        inflacionava o número pelo qual se decide se a estimativa serve.
        """
        linha = processo(
            created_at=(AGORA - timedelta(days=100)).isoformat(),
            updated_at=(AGORA - timedelta(days=200)).isoformat(),
        )
        retrato = analisar([linha], FASES, agora=AGORA)

        assert retrato.datas_invalidas["updated_at_antes_de_created_at"] == 1
        assert retrato.proxy_suspeito["nunca_tocado"] == 0

    def test_terminal_tocado_ha_muito_tempo_nao_e_suspeito(self):
        """Apanhado por mutação (M16): a janela tinha limite superior por testar.

        Um processo fechado há muito e tocado pela última vez há 200 dias
        tem no `updated_at` uma data de entrada na fase PLAUSÍVEL — é
        exactamente o caso em que a estimativa serve, e marcá-lo como
        suspeito diluía o aviso até ninguém lhe dar atenção.
        """
        linha = processo(
            status="concluidos",
            created_at=(AGORA - timedelta(days=400)).isoformat(),
            updated_at=(AGORA - timedelta(days=200)).isoformat(),
        )
        retrato = analisar([linha], FASES, agora=AGORA)

        assert retrato.proxy_suspeito["tocado_apos_fecho"] == 0

    def test_sem_updated_at(self):
        retrato = analisar([processo(updated_at=None)], FASES, agora=AGORA)

        assert retrato.proxy_suspeito["sem_updated_at"] == 1

    def test_datas_invalidas(self):
        linhas = [
            processo(created_at=None),
            processo(
                created_at=(AGORA - timedelta(days=1)).isoformat(),
                updated_at=(AGORA - timedelta(days=5)).isoformat(),
            ),
        ]
        retrato = analisar(linhas, FASES, agora=AGORA)

        assert retrato.datas_invalidas["created_at_ausente"] == 1
        assert retrato.datas_invalidas["updated_at_antes_de_created_at"] == 1

    def test_data_invertida_nao_entra_na_amostra(self):
        """Uma permanência negativa não é zero dias: é dado que não se usa."""
        linha = processo(
            created_at=AGORA.isoformat(),
            updated_at=(AGORA + timedelta(days=5)).isoformat(),
        )
        retrato = analisar([linha], FASES, agora=AGORA)

        assert retrato.permanencia_por_macro["analise"].amostra == 0


class TestCarimboDeRede:
    def test_com_rede(self):
        retrato = analisar(
            [processo(network_id="grupo_power_precision", company_id="cmp-power")],
            FASES, agora=AGORA,
        )

        assert retrato.carimbo_de_rede["com_rede"] == 1
        assert retrato.redes == {"grupo_power_precision": 1}

    def test_empresa_sem_rede_nao_e_pilha_antiga(self):
        """O processo criado entre o carimbo na escrita e a migração.

        Tem empresa e ainda não tem rede. Contá-lo como "sem marca" era
        exactamente a confusão que o isolamento fechou: ele NÃO é visível
        pela cláusula da rede de omissão.
        """
        retrato = analisar([processo(company_id="cmp-domus")], FASES, agora=AGORA)

        assert retrato.carimbo_de_rede["com_empresa_sem_rede"] == 1
        assert retrato.carimbo_de_rede["sem_marca_nenhuma"] == 0

    def test_empresa_escrita_pelo_nome_tambem_conta(self):
        """O histórico grava a empresa ora por id ora por nome."""
        retrato = analisar([processo(company="Domus")], FASES, agora=AGORA)

        assert retrato.carimbo_de_rede["com_empresa_sem_rede"] == 1

    def test_sem_marca_nenhuma(self):
        retrato = analisar([processo()], FASES, agora=AGORA)

        assert retrato.carimbo_de_rede["sem_marca_nenhuma"] == 1

    def test_o_carimbo_soma_o_total(self):
        linhas = [
            processo(network_id="r1"),
            processo(company_id="c1"),
            processo(),
        ]
        retrato = analisar(linhas, FASES, agora=AGORA)

        assert sum(retrato.carimbo_de_rede.values()) == retrato.total == 3


class TestDeterminismo:
    def test_o_agora_injectado_manda(self):
        """Dois `agora` diferentes dão permanências diferentes — e só isso."""
        linha = processo(updated_at=(AGORA - timedelta(days=10)).isoformat())

        hoje = analisar([linha], FASES, agora=AGORA)
        daqui_a_um_ano = analisar([linha], FASES, agora=AGORA + timedelta(days=365))

        assert hoje.permanencia_por_macro["analise"].bandas["8-15"] == 1
        assert daqui_a_um_ano.permanencia_por_macro["analise"].bandas["61+"] == 1

    def test_a_analise_nao_le_o_relogio_do_sistema(self):
        """Guarda sobre o código: um `datetime.now` aqui tornava isto inafirmável."""
        import services.phase_clock_coverage as modulo

        fonte = codigo_sem_comentarios(
            pathlib.Path(modulo.__file__).read_text(encoding="utf-8")
        )
        assert "datetime.now" not in fonte
        assert "utcnow" not in fonte


# ====================================================================
# SAÍDAS
# ====================================================================

class TestSaidas:
    @pytest.fixture
    def retrato(self):
        linhas = [
            processo(status="clientes_espera"),
            processo(status="cpcv", network_id="grupo_power_precision"),
            processo(status="perdido"),
            processo(status="concluidos", updated_at=None),
        ]
        return analisar(linhas, FASES, agora=AGORA)

    def test_json_e_serializavel(self, retrato):
        texto = json.dumps(para_json(retrato), ensure_ascii=False)
        assert "por_macro" in texto

    def test_json_declara_as_bandas_e_as_macros(self, retrato):
        saida = para_json(retrato)
        assert saida["bandas_usadas"] == list(ETIQUETAS_DAS_BANDAS)
        assert saida["macro_fases_validas"] == list(MACRO_FASES_VALIDAS)

    def test_json_leva_a_cobertura_e_a_suspeita(self, retrato):
        saida = para_json(retrato)
        assert "cobertura_do_relogio" in saida
        assert "proxy_suspeito" in saida
        assert "carimbo_de_rede" in saida

    def test_relatorio_menciona_as_seccoes(self, retrato):
        texto = formatar_relatorio(retrato)
        assert "COBERTURA DO RELÓGIO" in texto
        assert "PERMANÊNCIA POR MACRO-FASE" in texto
        assert "CARIMBO DE REDE" in texto

    def test_relatorio_avisa_quando_nao_ha_carimbo_nenhum(self, retrato):
        texto = formatar_relatorio(retrato)
        assert "ESTIMATIVA" in texto

    def test_relatorio_de_retrato_vazio_nao_rebenta(self):
        vazio = analisar([], FASES, agora=AGORA)
        texto = formatar_relatorio(vazio)
        assert "Processos analisados: 0" in texto
        assert isinstance(vazio, Retrato)


# ====================================================================
# O SCRIPT SÓ LÊ
# ====================================================================

class TestOScriptSoLe:
    """O script corre contra PRODUÇÃO, e por isso não chama o `env_guard`.

    Esse guarda existe para impedir que um seed escreva em produção, e é
    contra produção que isto tem de correr. O que o torna seguro é não
    haver uma única operação de escrita no ficheiro.
    """

    CAMINHO = RAIZ_BACKEND / "scripts" / "medir_relogio_de_fases.py"

    @pytest.fixture(scope="class")
    def fonte(self):
        # Sem comentários: a docstring EXPLICA que não há `--aplicar`, e
        # sem esta limpeza a explicação fazia a guarda ficar vermelha.
        return codigo_sem_comentarios(self.CAMINHO.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("escrita", [
        "update_one", "update_many", "insert_one", "insert_many",
        "delete_one", "delete_many", "replace_one", "bulk_write",
        "find_one_and_update", "find_one_and_delete", "drop",
        "$set", "$unset", "$pull", "$push", "$inc",
    ])
    def test_nenhuma_operacao_de_escrita(self, fonte, escrita):
        assert escrita not in fonte

    def test_nao_tem_flag_aplicar(self, fonte):
        assert "--aplicar" not in fonte

    def test_contraprova_le_mesmo_as_duas_coleccoes(self, fonte):
        """Sem isto, apagar o script inteiro satisfazia as guardas acima."""
        assert "db.processes.find" in fonte
        assert "db.workflow_statuses.find" in fonte

    def test_exclui_os_eliminados_por_omissao(self, fonte):
        assert "is_deleted" in fonte

    def test_a_projeccao_nao_traz_dados_pessoais(self, fonte):
        """Ler o processo inteiro traria o `personal_data` encriptado.

        Um script de medição de datas não tem de tocar em dados de
        cliente — e a projecção é o que o impede.
        """
        assert "personal_data" not in fonte
        assert "PROJECCAO" in fonte
