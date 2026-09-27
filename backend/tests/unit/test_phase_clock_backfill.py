"""
Backfill do relógio de fases — Camada 1.5.

Ver `services/phase_clock_backfill.py` e
`scripts/semear_relogio_de_fases.py`.

O QUE ESTES TESTES DEFENDEM
  1. **Que a classificação é UMA.** A medição conta e o backfill carimba;
     se cada um classificasse à sua maneira, o relatório deixava de
     descrever os dados escritos e a discrepância só aparecia meses
     depois, num gráfico. Há um teste a cruzar os dois.
  2. **Que os três níveis são mesmo três.** Um booleano cego obrigava o BI
     a escolher entre não ter história e desenhar médias sobre cinco mil
     valores aberrantes — e os dois aberrantes erram para lados OPOSTOS,
     pelo que juntá-los numa classe perdia a informação que permite
     excluí-los.
  3. **Que um processo com relógio nunca é tocado**, e que a condição de
     idempotência está na QUERY e não num `if`: entre a leitura e a
     escrita pode ter havido uma transição REAL, e é ela que manda.
  4. **Que não escreve sem `--aplicar`.**
"""
import ast
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios
from services.phase_clock_coverage import (
    QUALIDADES,
    QUALIDADES_ABERRANTES,
    QUALIDADE_NUNCA_TOCADO,
    QUALIDADE_PLAUSIVEL,
    QUALIDADE_SEM_ESTIMATIVA,
    QUALIDADE_TOCADO_APOS_FECHO,
    analisar,
    classificar_estimativa,
    instante,
)
from services.phase_clock_backfill import (
    CAMPO_QUALIDADE,
    PROJECCAO_DO_BACKFILL,
    campos_do_backfill,
    formatar_plano,
    para_json,
    preparar,
)
from services.process_phase_clock import (
    CAMPO_FASE_DESDE,
    CAMPO_FASE_ESTIMADO,
    CAMPO_MACRO_DESDE,
    CAMPO_MACRO_ESTIMADO,
)

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]

AGORA = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)


def fase(nome, macro=None, **extra):
    base = {"id": nome, "name": nome, "label": nome, "order": 1}
    if macro:
        base["macro_fase"] = macro
    base.update(extra)
    return base


FASES = [
    fase("clientes_espera", "novo"),
    fase("analise_documental", "analise"),
    fase("concluidos", "concluido", is_active=False),
]

MACROS = {
    "clientes_espera": "novo",
    "analise_documental": "analise",
    "concluidos": "concluido",
    "": None,
}


def linha(**campos):
    base = {
        "id": "p-1",
        "status": "analise_documental",
        "created_at": (AGORA - timedelta(days=100)).isoformat(),
        "updated_at": (AGORA - timedelta(days=10)).isoformat(),
    }
    base.update(campos)
    return base


# ════════════════════════════════════════════════════════════════════
# A CLASSIFICAÇÃO
# ════════════════════════════════════════════════════════════════════

class TestClassificacao:
    def _classificar(self, **kwargs):
        args = {
            "criado": AGORA - timedelta(days=100),
            "tocado": AGORA - timedelta(days=10),
            "macro": "analise",
            "agora": AGORA,
        }
        args.update(kwargs)
        return classificar_estimativa(**args)

    def test_plausivel_e_o_caso_utilizavel(self):
        assert self._classificar() == QUALIDADE_PLAUSIVEL

    def test_nunca_tocado(self):
        """`updated_at == created_at`: a estimativa é a data de criação."""
        mesmo = AGORA - timedelta(days=200)
        assert self._classificar(criado=mesmo, tocado=mesmo) == QUALIDADE_NUNCA_TOCADO

    def test_tocado_apos_fecho(self):
        """Terminal, tocado há pouco, criado há muito: a factura anexada tarde."""
        assert self._classificar(
            macro="concluido",
            criado=AGORA - timedelta(days=400),
            tocado=AGORA - timedelta(days=2),
        ) == QUALIDADE_TOCADO_APOS_FECHO

    def test_sem_updated_at_nao_ha_estimativa(self):
        assert self._classificar(tocado=None) == QUALIDADE_SEM_ESTIMATIVA

    def test_um_processo_activo_tocado_ha_pouco_e_plausivel(self):
        """Contraprova: num processo em curso, um toque recente é trabalho."""
        assert self._classificar(
            macro="analise",
            criado=AGORA - timedelta(days=400),
            tocado=AGORA - timedelta(days=2),
        ) == QUALIDADE_PLAUSIVEL

    def test_terminal_tocado_ha_muito_e_plausivel(self):
        """O limite SUPERIOR da janela: 200 dias é uma data de entrada
        plausível, e marcá-la como aberrante diluía o aviso."""
        assert self._classificar(
            macro="concluido",
            criado=AGORA - timedelta(days=400),
            tocado=AGORA - timedelta(days=200),
        ) == QUALIDADE_PLAUSIVEL

    def test_terminal_recente_mas_novo_e_plausivel(self):
        """Criado e fechado na mesma semana: a estimativa está certa."""
        assert self._classificar(
            macro="concluido",
            criado=AGORA - timedelta(days=5),
            tocado=AGORA - timedelta(days=1),
        ) == QUALIDADE_PLAUSIVEL

    def test_data_invertida_nao_e_nunca_tocado(self):
        """`updated_at` ANTES do `created_at` é dado corrompido, não "nunca
        tocado" — contado à parte em `datas_invalidas`."""
        assert self._classificar(
            criado=AGORA - timedelta(days=10),
            tocado=AGORA - timedelta(days=50),
        ) == QUALIDADE_PLAUSIVEL

    def test_os_dois_aberrantes_sao_mutuamente_exclusivos(self):
        """`nunca_tocado` implica `tocado` antigo, logo nunca é recente.

        Se se sobrepusessem, um deles ficava por contar e a soma das
        qualidades deixava de ser o total.
        """
        mesmo = AGORA - timedelta(days=400)
        assert self._classificar(
            macro="concluido", criado=mesmo, tocado=mesmo,
        ) == QUALIDADE_NUNCA_TOCADO

    def test_a_classificacao_e_exaustiva(self):
        """Toda a entrada cai num dos quatro níveis declarados."""
        casos = [
            {},
            {"tocado": None},
            {"criado": None},
            {"criado": AGORA, "tocado": AGORA},
            {"macro": None},
            {"macro": "perdido", "criado": AGORA - timedelta(days=500),
             "tocado": AGORA - timedelta(days=1)},
        ]
        for caso in casos:
            assert self._classificar(**caso) in QUALIDADES, caso

    def test_os_aberrantes_erram_para_lados_opostos(self):
        """É por isto que são duas classes e não uma.

        Um sobrestima (a estimativa recua até à criação) e o outro
        subestima (a estimativa salta para o último toque). Em média não se
        anulam — anulam-se na aparência e cada gráfico fica errado de uma
        maneira diferente.
        """
        assert set(QUALIDADES_ABERRANTES) == {
            QUALIDADE_NUNCA_TOCADO, QUALIDADE_TOCADO_APOS_FECHO,
        }
        assert QUALIDADE_PLAUSIVEL not in QUALIDADES_ABERRANTES


# ════════════════════════════════════════════════════════════════════
# UMA REGRA, DUAS UTILIZAÇÕES
# ════════════════════════════════════════════════════════════════════

class TestAMedicaoEOBackfillConcordam:
    def test_as_contagens_do_retrato_sao_o_que_o_backfill_carimbaria(self):
        """O teste que impede o relatório de descrever outros dados.

        A medição conta e o backfill escreve. Se divergissem, o
        `relogio.json` que se lê antes de aplicar deixava de descrever o
        que fica na base de dados — e a diferença só aparecia num gráfico,
        meses depois.
        """
        mesmo = (AGORA - timedelta(days=300)).isoformat()
        linhas = [
            linha(id="p-plausivel"),
            linha(id="p-nunca", created_at=mesmo, updated_at=mesmo),
            linha(
                id="p-fecho", status="concluidos",
                created_at=(AGORA - timedelta(days=400)).isoformat(),
                updated_at=(AGORA - timedelta(days=3)).isoformat(),
            ),
            linha(id="p-sem", updated_at=None),
        ]

        retrato = analisar(linhas, FASES, agora=AGORA)
        _, plano = preparar(linhas, MACROS, agora=AGORA)

        assert retrato.qualidade_da_estimativa == plano.por_qualidade

    def test_o_retrato_e_o_plano_concordam_tambem_nos_aliases(self):
        """Um processo gravado como `cpcv` tem de ser classificado pela
        macro da fase REAL — nos dois lados."""
        from services.phase_clock_coverage import macro_por_valor

        fases = [*FASES, fase("fase_escritura", "aprovado")]
        linhas = [linha(
            id="p-cpcv", status="cpcv",
            created_at=(AGORA - timedelta(days=400)).isoformat(),
            updated_at=(AGORA - timedelta(days=2)).isoformat(),
        )]

        retrato = analisar(linhas, fases, agora=AGORA)
        _, plano = preparar(
            linhas,
            macro_por_valor((l.get("status") for l in linhas), fases),
            agora=AGORA,
        )

        assert retrato.qualidade_da_estimativa == plano.por_qualidade


# ════════════════════════════════════════════════════════════════════
# OS CAMPOS ESCRITOS
# ════════════════════════════════════════════════════════════════════

class TestCamposEscritos:
    def test_carimba_o_updated_at_nos_dois_relogios(self):
        campos = campos_do_backfill(linha(), QUALIDADE_PLAUSIVEL)
        marca = instante(linha()["updated_at"]).isoformat()

        assert campos[CAMPO_FASE_DESDE] == marca
        assert campos[CAMPO_MACRO_DESDE] == marca

    def test_marca_os_dois_carimbos_como_estimados(self):
        """São as bandeiras que impedem o acumulador de se contaminar."""
        campos = campos_do_backfill(linha(), QUALIDADE_PLAUSIVEL)

        assert campos[CAMPO_FASE_ESTIMADO] is True
        assert campos[CAMPO_MACRO_ESTIMADO] is True

    def test_guarda_a_qualidade(self):
        campos = campos_do_backfill(linha(), QUALIDADE_NUNCA_TOCADO)

        assert campos[CAMPO_QUALIDADE] == QUALIDADE_NUNCA_TOCADO

    def test_a_bandeira_e_a_qualidade_sao_campos_diferentes(self):
        """A bandeira diz ao RELÓGIO para não acumular; a qualidade diz ao
        BI o que pode mostrar. Juntá-las num campo obrigava um dos dois a
        interpretar a intenção do outro."""
        campos = campos_do_backfill(linha(), QUALIDADE_PLAUSIVEL)

        assert campos[CAMPO_MACRO_ESTIMADO] is True
        assert campos[CAMPO_QUALIDADE] == QUALIDADE_PLAUSIVEL

    def test_sem_estimativa_nao_escreve_nada(self):
        """Semear o `created_at` no lugar do `updated_at` era inventar um
        quarto nível de má qualidade sem o dizer."""
        assert campos_do_backfill(linha(updated_at=None), QUALIDADE_SEM_ESTIMATIVA) is None
        assert campos_do_backfill(linha(updated_at="ontem"), QUALIDADE_PLAUSIVEL) is None


# ════════════════════════════════════════════════════════════════════
# O PLANO
# ════════════════════════════════════════════════════════════════════

class TestPlano:
    def test_um_processo_com_relogio_nunca_e_tocado(self):
        """Correr isto duas vezes não desfaz uma medição."""
        escritas, plano = preparar(
            [linha(**{CAMPO_FASE_DESDE: AGORA.isoformat()})], MACROS, agora=AGORA,
        )

        assert escritas == []
        assert plano.ja_tinham_relogio == 1
        assert plano.a_carimbar == 0

    def test_um_processo_com_carimbo_estimado_de_uma_passagem_anterior(self):
        """Idempotência de verdade: a segunda corrida não recarimba."""
        escritas, plano = preparar(
            [linha(**{
                CAMPO_FASE_DESDE: AGORA.isoformat(),
                CAMPO_FASE_ESTIMADO: True,
            })],
            MACROS, agora=AGORA,
        )

        assert escritas == []
        assert plano.ja_tinham_relogio == 1

    def test_conta_e_prepara_os_que_faltam(self):
        escritas, plano = preparar(
            [linha(id="p-1"), linha(id="p-2")], MACROS, agora=AGORA,
        )

        assert len(escritas) == 2
        assert {i for i, _ in escritas} == {"p-1", "p-2"}
        assert plano.a_carimbar == 2
        assert plano.lidos == 2

    def test_um_processo_sem_id_e_ignorado(self):
        """Uma escrita por `_id` saltava a condição de idempotência."""
        escritas, plano = preparar([linha(id=None)], MACROS, agora=AGORA)

        assert escritas == []
        assert plano.a_carimbar == 0

    def test_sem_estimativa_e_contado_a_parte(self):
        escritas, plano = preparar([linha(updated_at=None)], MACROS, agora=AGORA)

        assert escritas == []
        assert plano.sem_estimativa == 1
        assert plano.por_qualidade[QUALIDADE_SEM_ESTIMATIVA] == 1

    def test_a_soma_das_qualidades_e_o_que_nao_tinha_relogio(self):
        """Invariante: nada se perde entre "lido" e "classificado"."""
        linhas = [
            linha(id="p-1"),
            linha(id="p-2", updated_at=None),
            linha(id="p-3", **{CAMPO_FASE_DESDE: AGORA.isoformat()}),
        ]
        _, plano = preparar(linhas, MACROS, agora=AGORA)

        assert sum(plano.por_qualidade.values()) == plano.lidos - plano.ja_tinham_relogio

    def test_o_agora_injectado_manda(self):
        """A mesma linha, dois instantes, classificações diferentes."""
        l = linha(
            status="concluidos",
            created_at=(AGORA - timedelta(days=400)).isoformat(),
            updated_at=(AGORA - timedelta(days=2)).isoformat(),
        )

        _, hoje = preparar([l], MACROS, agora=AGORA)
        _, tarde = preparar([l], MACROS, agora=AGORA + timedelta(days=365))

        assert hoje.por_qualidade[QUALIDADE_TOCADO_APOS_FECHO] == 1
        assert tarde.por_qualidade[QUALIDADE_PLAUSIVEL] == 1


class TestSaidas:
    def test_a_simulacao_diz_que_nao_escreveu(self):
        _, plano = preparar([linha()], MACROS, agora=AGORA)
        texto = formatar_plano(plano, aplicado=False)

        assert "SIMULAÇÃO" in texto
        assert "--aplicar" in texto

    def test_o_aplicado_mostra_os_escritos(self):
        _, plano = preparar([linha()], MACROS, agora=AGORA)
        plano.escritos = 1
        texto = formatar_plano(plano, aplicado=True)

        assert "APLICADO" in texto
        assert "documentos escritos" in texto

    def test_o_relatorio_explica_porque_sao_tres_niveis(self):
        _, plano = preparar([linha()], MACROS, agora=AGORA)
        texto = formatar_plano(plano, aplicado=False)

        assert "plausivel" in texto
        assert "OPOSTOS" in texto

    def test_json_serializavel(self):
        import json

        _, plano = preparar([linha()], MACROS, agora=AGORA)
        assert "por_qualidade" in json.dumps(para_json(plano, aplicado=False))


# ════════════════════════════════════════════════════════════════════
# O SCRIPT
# ════════════════════════════════════════════════════════════════════

class TestOScript:
    CAMINHO = RAIZ_BACKEND / "scripts" / "semear_relogio_de_fases.py"

    @pytest.fixture(scope="class")
    def fonte(self):
        return codigo_sem_comentarios(self.CAMINHO.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("destrutiva", [
        "delete_one", "delete_many", "drop", "$unset", "$pull",
        "replace_one", "find_one_and_delete",
    ])
    def test_nenhuma_operacao_destrutiva(self, fonte, destrutiva):
        assert destrutiva not in fonte

    def test_tem_a_bandeira_aplicar(self, fonte):
        """Por omissão simula — a mesma disciplina do `limpar_is_notified`."""
        assert "--aplicar" in fonte

    def test_so_escreve_com_a_bandeira(self, fonte):
        """Guarda sobre o fluxo: o `bulk_write` está atrás do `if`."""
        arvore = ast.parse(self.CAMINHO.read_text(encoding="utf-8"))

        chamadas_de_escrita = [
            no for no in ast.walk(arvore)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "bulk_write"
        ]
        assert chamadas_de_escrita, "o script tem de escrever quando lhe pedem"

        # A chamada a `escrever(...)` tem de estar dentro de um `if` que
        # mencione `aplicar`.
        guardadas = []
        for no in ast.walk(arvore):
            if not isinstance(no, ast.If):
                continue
            condicao = ast.unparse(no.test)
            if "aplicar" not in condicao:
                continue
            for interno in ast.walk(no):
                if (
                    isinstance(interno, ast.Call)
                    and isinstance(interno.func, ast.Name)
                    and interno.func.id == "escrever"
                ):
                    guardadas.append(condicao)
        assert guardadas, "a escrita não está atrás de um `if ... aplicar`"

    def test_a_condicao_de_idempotencia_esta_na_QUERY(self, fonte):
        """Não num `if` em Python.

        Entre a leitura e a escrita pode ter havido uma transição REAL. Com
        a condição na query, a operação perde a corrida em vez de a
        sobrepor — o que é o resultado certo: a medição ganha à estimativa.
        """
        assert "UpdateOne" in fonte
        assert "$exists" in fonte
        assert "False" in fonte

    def test_a_projeccao_nao_traz_dados_pessoais(self):
        assert "personal_data" not in PROJECCAO_DO_BACKFILL
        assert PROJECCAO_DO_BACKFILL["_id"] == 0
        assert PROJECCAO_DO_BACKFILL["id"] == 1

    def test_contraprova_le_mesmo_as_duas_coleccoes(self, fonte):
        assert "db.processes.find" in fonte
        assert "db.workflow_statuses.find" in fonte

    def test_a_macro_vem_do_resolvedor(self, fonte):
        """Sem isto, os 217 processos de alias caíam fora da regra do
        `tocado_apos_fecho`."""
        assert "macro_por_valor" in fonte
        assert "resolver" in fonte or "phase_clock_coverage" in fonte
