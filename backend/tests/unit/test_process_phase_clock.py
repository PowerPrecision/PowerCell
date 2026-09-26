"""
O relógio de fases — Refinamento Analítico e SLAs, Camada 1.

Ver `services/process_phase_clock.py`.

O QUE ESTES TESTES DEFENDEM
  1. **Que o relógio não tem ator.** É a regra de ouro do perfil
     `indexacao`: as acções dele não geram registo. O relógio funciona
     onde o rasto não pode existir porque não pergunta quem move — e há
     uma guarda sobre o código-fonte a afirmar que nenhuma noção de
     utilizador entra no módulo.
  2. **Que guardar sem mudar de fase não reinicia nada.** Sem esta
     guarda, cada `PUT` punha a permanência a zero e nenhum processo
     aparecia preso — o defeito seria invisível porque os números
     continuavam a existir.
  3. **Que mover DENTRO da mesma macro-fase não reinicia o relógio da
     macro.** Se reiniciasse, medir o gargalo da Análise passava a contar
     só a última sub-fase: o número ficava bonito à custa de ser falso.
  4. **Que o acumulador só leva tempo MEDIDO.** Um carimbo estimado pelo
     backfill nunca entra no `tempos_macro`. Misturar medido com estimado
     é o erro que este épico inteiro existe para não cometer.
  5. **Que a reestruturação do funil não reinicia os SLAs** (decisão do
     dono), e que o mesmo vale para o ciclo de vida (soft-delete).

`agora` é sempre INJECTADO.
"""
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios
from services.process_phase_clock import (
    CAMPO_FASE_DESDE,
    CAMPO_FASE_ESTIMADO,
    CAMPO_MACRO_DESDE,
    CAMPO_MACRO_ESTIMADO,
    CAMPO_TEMPOS,
    MACROS_SEM_PERMANENCIA,
    Transicao,
    campos_de_transicao,
    montar_update,
    transicao_de_fase,
)

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]

AGORA = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
UM_DIA = 86400


def fase(nome, macro=None, **extra):
    base = {"id": nome, "name": nome, "label": nome, "order": 1}
    if macro:
        base["macro_fase"] = macro
    base.update(extra)
    return base


FASES = [
    fase("clientes_espera", "novo"),
    fase("analise_documental", "analise"),
    fase("fase_documental", "analise"),
    fase("renegociacao", "analise", is_active=False),
    fase("pre_aprovado", "aprovado"),
    fase("fase_escritura", "aprovado"),
    fase("concluidos", "concluido", is_active=False),
]


def processo(**campos):
    base = {
        "id": "p-1",
        "status": "analise_documental",
        "created_at": (AGORA - timedelta(days=100)).isoformat(),
    }
    base.update(campos)
    return base


def transicao(**kwargs):
    """`campos_de_transicao` com os argumentos obrigatórios por omissão."""
    args = {
        "fase_anterior": "analise_documental",
        "fase_nova": "pre_aprovado",
        "macro_anterior": "analise",
        "macro_nova": "aprovado",
        "documento": processo(),
        "agora": AGORA,
    }
    args.update(kwargs)
    return campos_de_transicao(**args)


# ════════════════════════════════════════════════════════════════════
# O QUE NÃO É UMA TRANSIÇÃO
# ════════════════════════════════════════════════════════════════════

class TestNaoEUmaTransicao:
    def test_guardar_com_o_mesmo_estado_nao_toca_no_relogio(self):
        """Sem esta guarda, cada `PUT` punha a permanência a zero.

        E o defeito era invisível: os números continuavam a existir, só
        que nenhum processo aparecia preso em fase nenhuma.
        """
        t = transicao(fase_anterior="analise_documental", fase_nova="analise_documental")

        assert t.vazia
        assert t.set == {}
        assert t.inc == {}

    def test_sem_fase_nova_nao_ha_transicao(self):
        """`next_status` do fim do pipeline, ou um `PUT` sem estado."""
        assert transicao(fase_nova=None).vazia
        assert transicao(fase_nova="").vazia

    def test_um_processo_novo_sem_estado_anterior_arranca_o_relogio(self):
        """Contraprova: `fase_anterior=None` É uma transição."""
        t = transicao(fase_anterior=None, macro_anterior=None)

        assert not t.vazia
        assert t.set[CAMPO_FASE_DESDE] == AGORA.isoformat()


# ════════════════════════════════════════════════════════════════════
# LEITURA DE INSTANTES
# ════════════════════════════════════════════════════════════════════

class TestLeituraDeInstantes:
    """`_instante` é privado e é testado directamente, de propósito.

    Apanhado por mutação (P12): trocar o `return None` do ramo de excepção
    por `agora_utc()` sobrevivia a todos os testes de transição, porque o
    `agora` injectado nos testes está no PASSADO em relação ao relógio da
    máquina e o resultado caía na guarda dos segundos negativos. O teste
    passava por acidente de calendário.

    A tolerância na leitura é a regra que decide se um carimbo corrompido
    conta como ausente; afirma-se aqui, onde não depende de mais nada.
    """

    def test_le_iso_com_z(self):
        from services.process_phase_clock import _instante

        assert _instante("2026-09-01T10:00:00Z") == datetime(
            2026, 9, 1, 10, 0, tzinfo=timezone.utc,
        )

    def test_iso_sem_fuso_assume_utc(self):
        from services.process_phase_clock import _instante

        assert _instante("2026-09-01T10:00:00").tzinfo is not None

    def test_datetime_nativo_do_mongo_ganha_fuso(self):
        from services.process_phase_clock import _instante

        assert _instante(datetime(2026, 9, 1, 10, 0)).tzinfo is not None

    @pytest.mark.parametrize("lixo", [None, "", "  ", "ontem", "0000", 17, [], {}])
    def test_o_que_nao_se_le_e_ausente_nunca_agora(self, lixo):
        """Se devolvesse "agora", um carimbo corrompido dava permanência zero
        — e zero é um número que ninguém questiona."""
        from services.process_phase_clock import _instante

        assert _instante(lixo) is None


# ════════════════════════════════════════════════════════════════════
# O CARIMBO
# ════════════════════════════════════════════════════════════════════

class TestCarimbo:
    def test_a_fase_e_a_macro_carimbam_quando_a_macro_muda(self):
        t = transicao()

        assert t.set[CAMPO_FASE_DESDE] == AGORA.isoformat()
        assert t.set[CAMPO_MACRO_DESDE] == AGORA.isoformat()

    def test_mover_dentro_da_macro_nao_reinicia_o_relogio_da_macro(self):
        """`fase_documental` → `fase_escritura` não sai da Análise.

        É o teste discriminante do desenho: se a macro reiniciasse aqui, o
        gargalo da Análise media só a última sub-fase.
        """
        t = transicao(
            fase_anterior="analise_documental",
            fase_nova="fase_documental",
            macro_anterior="analise",
            macro_nova="analise",
        )

        assert t.set[CAMPO_FASE_DESDE] == AGORA.isoformat()
        assert CAMPO_MACRO_DESDE not in t.set
        assert t.inc == {}

    def test_a_transicao_limpa_a_bandeira_de_estimado_da_fase(self):
        """O carimbo passou a ser medido; a estimativa do backfill sai."""
        t = transicao(documento=processo(**{CAMPO_FASE_ESTIMADO: True}))

        assert t.set[CAMPO_FASE_ESTIMADO] is False

    def test_a_bandeira_da_macro_so_se_limpa_quando_a_macro_carimba(self):
        """Duas bandeiras, cada uma com o seu carimbo.

        Um movimento dentro da macro torna o `fase_desde` medido mas deixa
        o `macro_fase_desde` como estava. Limpar a bandeira da macro aqui
        fazia a transição SEGUINTE acumular segundos estimados.
        """
        doc = processo(**{CAMPO_MACRO_ESTIMADO: True})

        dentro = transicao(
            fase_nova="fase_documental", macro_nova="analise", documento=doc,
        )
        assert CAMPO_MACRO_ESTIMADO not in dentro.set

        fora = transicao(documento=doc)
        assert fora.set[CAMPO_MACRO_ESTIMADO] is False


# ════════════════════════════════════════════════════════════════════
# O ACUMULADOR
# ════════════════════════════════════════════════════════════════════

class TestAcumulador:
    def test_acumula_os_segundos_na_macro_que_deixa(self):
        doc = processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=12)).isoformat(),
        })
        t = transicao(documento=doc)

        assert t.inc == {f"{CAMPO_TEMPOS}.analise": 12 * UM_DIA}

    def test_acumula_na_macro_ANTERIOR_e_nunca_na_nova(self):
        """Trocar as duas atribuía o tempo ao grupo errado — e o número
        continuava plausível, que é o pior tipo de erro aqui."""
        doc = processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=5)).isoformat(),
        })
        t = transicao(documento=doc)

        assert f"{CAMPO_TEMPOS}.analise" in t.inc
        assert f"{CAMPO_TEMPOS}.aprovado" not in t.inc

    def test_soma_as_duas_passagens_pela_mesma_macro(self):
        """`aprovado` → `renegociacao` → `aprovado`: a Análise conta duas vezes.

        É a razão de ser do acumulador em vez de um campo que se
        sobrescreve. Um processo que volta atrás passa pela Análise duas
        vezes e o que interessa é a soma — o `$inc` faz isso sem ler o
        valor anterior, e portanto sem corrida.
        """
        primeira = transicao(
            fase_anterior="analise_documental", fase_nova="pre_aprovado",
            macro_anterior="analise", macro_nova="aprovado",
            documento=processo(**{
                CAMPO_MACRO_DESDE: (AGORA - timedelta(days=10)).isoformat(),
            }),
        )
        segunda = transicao(
            fase_anterior="renegociacao", fase_nova="pre_aprovado",
            macro_anterior="analise", macro_nova="aprovado",
            documento=processo(
                status="renegociacao",
                **{CAMPO_MACRO_DESDE: (AGORA - timedelta(days=3)).isoformat()},
            ),
        )

        chave = f"{CAMPO_TEMPOS}.analise"
        assert primeira.inc[chave] == 10 * UM_DIA
        assert segunda.inc[chave] == 3 * UM_DIA
        # O Mongo soma; o código nunca lê o total para o reescrever.

    def test_um_carimbo_estimado_nao_entra_no_acumulador(self):
        """O teste que impede a contaminação.

        Depois do backfill os dois coexistem no mesmo documento. Acumular
        a partir de uma estimativa punha segundos inventados no campo de
        onde saem todas as médias.
        """
        doc = processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=200)).isoformat(),
            CAMPO_MACRO_ESTIMADO: True,
        })
        t = transicao(documento=doc)

        assert t.inc == {}
        # Mas o carimbo novo é gravado e a bandeira limpa: a transição
        # SEGUINTE já acumula.
        assert t.set[CAMPO_MACRO_DESDE] == AGORA.isoformat()
        assert t.set[CAMPO_MACRO_ESTIMADO] is False

    def test_sem_carimbo_nenhum_recorre_ao_created_at(self):
        """Um processo nascido depois deste código: a entrada na primeira
        fase É a criação, e isso é exacto, não uma estimativa."""
        doc = processo(created_at=(AGORA - timedelta(days=7)).isoformat())
        t = transicao(documento=doc)

        assert t.inc == {f"{CAMPO_TEMPOS}.analise": 7 * UM_DIA}

    def test_carimbo_ilegivel_nao_recorre_ao_created_at(self):
        """Dado corrompido não se troca por um número plausível e errado.

        Se o documento TEM carimbo mas ele não se lê, o `created_at` daria
        a idade total do processo — um valor credível e falso, que é o
        pior resultado possível num acumulador.
        """
        doc = processo(**{CAMPO_MACRO_DESDE: "ontem"})
        t = transicao(documento=doc)

        assert t.inc == {}

    def test_carimbo_no_futuro_nao_subtrai_tempo(self):
        """Um `$inc` negativo tirava tempo já medido de outras passagens."""
        doc = processo(**{
            CAMPO_MACRO_DESDE: (AGORA + timedelta(days=2)).isoformat(),
        })
        t = transicao(documento=doc)

        assert t.inc == {}

    def test_sem_macro_anterior_nao_acumula(self):
        """Uma fase que o administrador ainda não classificou."""
        doc = processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=5)).isoformat(),
        })
        t = transicao(macro_anterior=None, documento=doc)

        assert t.inc == {}
        assert t.set[CAMPO_MACRO_DESDE] == AGORA.isoformat()

    @pytest.mark.parametrize("formato", [
        "2026-09-16T12:00:00Z",
        "2026-09-16T12:00:00+00:00",
        "2026-09-16T12:00:00",
        datetime(2026, 9, 16, 12, 0),
        datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
    ])
    def test_le_os_formatos_que_a_coleccao_tem(self, formato):
        """ISO com `Z`, ISO sem fuso e `datetime` nativo, no mesmo campo."""
        doc = processo(**{CAMPO_MACRO_DESDE: formato})
        t = transicao(documento=doc)

        assert t.inc == {f"{CAMPO_TEMPOS}.analise": 10 * UM_DIA}


# ════════════════════════════════════════════════════════════════════
# O DOCUMENTO DE ACTUALIZAÇÃO
# ════════════════════════════════════════════════════════════════════

class TestMontarUpdate:
    def test_junta_o_set_e_o_inc(self):
        t = Transicao(set={"fase_desde": "x"}, inc={"tempos_macro.analise": 10})
        update = montar_update({"status": "pre_aprovado"}, t)

        assert update["$set"] == {"status": "pre_aprovado", "fase_desde": "x"}
        assert update["$inc"] == {"tempos_macro.analise": 10}

    def test_omite_o_inc_vazio(self):
        """O Mongo recusa um operador de actualização sem campos.

        E a transição dentro da mesma macro-fase produz exactamente isso —
        seria um erro a cada movimento entre sub-fases.
        """
        update = montar_update({"status": "x"}, Transicao(set={"fase_desde": "y"}))

        assert "$inc" not in update

    def test_uma_transicao_vazia_deixa_o_update_original_intacto(self):
        update = montar_update({"status": "x"}, Transicao())

        assert update == {"$set": {"status": "x"}}

    def test_nao_muta_o_conjunto_recebido(self):
        original = {"status": "x"}
        montar_update(original, Transicao(set={"fase_desde": "y"}))

        assert original == {"status": "x"}


# ════════════════════════════════════════════════════════════════════
# RESOLUÇÃO PELO MOTOR
# ════════════════════════════════════════════════════════════════════

class TestResolucaoPeloMotor:
    @pytest.fixture(autouse=True)
    def motor(self, monkeypatch):
        async def fases():
            return FASES

        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "carregar_fases", fases)
        return FASES

    async def test_resolve_as_macros_das_duas_fases(self):
        doc = processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=4)).isoformat(),
        })
        t = await transicao_de_fase(doc, "pre_aprovado", agora=AGORA)

        assert t.set[CAMPO_MACRO_DESDE] == AGORA.isoformat()
        assert t.inc == {f"{CAMPO_TEMPOS}.analise": 4 * UM_DIA}

    async def test_um_alias_gravado_conta_na_macro_da_fase_real(self):
        """O processo está gravado como `cpcv`, que o motor não conhece.

        O resolvedor manda-o para `fase_escritura` (macro `aprovado`), a
        mesma coluna que o quadro lhe desenha. Sem isto, os 217 processos
        de alias e gralha mudavam de macro a cada movimento e o acumulador
        enchia-se de intervalos atribuídos ao grupo errado.
        """
        doc = processo(
            status="cpcv",
            **{CAMPO_MACRO_DESDE: (AGORA - timedelta(days=6)).isoformat()},
        )
        t = await transicao_de_fase(doc, "concluidos", agora=AGORA)

        assert t.inc == {f"{CAMPO_TEMPOS}.aprovado": 6 * UM_DIA}

    async def test_uma_gralha_gravada_tambem(self):
        """`"Concluidos "` é `concluidos` mal gravado."""
        doc = processo(
            status="Concluidos ",
            **{CAMPO_MACRO_DESDE: (AGORA - timedelta(days=2)).isoformat()},
        )
        t = await transicao_de_fase(doc, "pre_aprovado", agora=AGORA)

        assert t.inc == {f"{CAMPO_TEMPOS}.concluido": 2 * UM_DIA}

    async def test_mover_entre_subfases_da_mesma_macro_pelo_motor(self):
        doc = processo(status="analise_documental", **{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=9)).isoformat(),
        })
        t = await transicao_de_fase(doc, "fase_documental", agora=AGORA)

        assert CAMPO_MACRO_DESDE not in t.set
        assert t.inc == {}

    async def test_degrada_para_o_carimbo_da_fase_se_o_motor_falhar(self, monkeypatch):
        """Nunca levanta, e nunca escreve um intervalo que não sabe.

        Parar uma transição de negócio por causa de uma métrica seria
        pior do que perder a métrica; escrever o intervalo na macro
        errada seria pior do que as duas coisas.
        """
        import services.workflow_phases as wp

        async def rebenta():
            raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(wp, "carregar_fases", rebenta)

        doc = processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=4)).isoformat(),
        })
        t = await transicao_de_fase(doc, "pre_aprovado", agora=AGORA)

        assert t.set[CAMPO_FASE_DESDE] == AGORA.isoformat()
        assert CAMPO_MACRO_DESDE not in t.set
        assert t.inc == {}

    async def test_documento_none_nao_rebenta(self):
        t = await transicao_de_fase(None, "pre_aprovado", agora=AGORA)

        assert t.set[CAMPO_FASE_DESDE] == AGORA.isoformat()


# ════════════════════════════════════════════════════════════════════
# O RELÓGIO NÃO TEM ATOR
# ════════════════════════════════════════════════════════════════════

class TestSemAtor:
    """A regra de ouro do perfil `indexacao`, afirmada sobre o módulo.

    O relógio existe precisamente porque metade das transições não pode
    deixar rasto. Se um dia alguém lhe passar o utilizador — para
    registar quem moveu, para filtrar, para qualquer coisa — a peça deixa
    de poder ser usada nos caminhos silenciosos, e o silêncio deles é uma
    regra de negócio, não um detalhe.
    """

    @pytest.fixture(scope="class")
    def fonte(self):
        caminho = RAIZ_BACKEND / "services" / "process_phase_clock.py"
        # Sem comentários: a docstring EXPLICA o stealth e o `indexacao`,
        # e sem esta limpeza a explicação fazia a guarda ficar vermelha.
        return codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("nocao_de_utilizador", [
        "user", "user_id", "created_by", "track_history",
        "_is_stealth_user", "log_history", "effective_role",
        "audit", "activities",
    ])
    def test_nenhuma_nocao_de_utilizador_entra_no_relogio(
        self, fonte, nocao_de_utilizador,
    ):
        assert nocao_de_utilizador not in fonte

    def test_contraprova_o_modulo_faz_mesmo_o_trabalho(self, fonte):
        """Sem isto, apagar o módulo satisfazia a guarda acima."""
        assert "def campos_de_transicao" in fonte
        assert "def montar_update" in fonte
        assert "fase_desde" in fonte
        assert "tempos_macro" in fonte

    def test_o_relogio_nao_escreve_na_base_de_dados(self, fonte):
        """A parte pura não persiste: quem persiste é o caminho de escrita.

        Um `update_one` aqui dentro seria uma segunda escrita, fora da
        mesma operação atómica do `status` — e um processo podia ficar com
        a fase nova e o relógio antigo.
        """
        for escrita in ("update_one", "update_many", "insert_one", "bulk_write"):
            assert escrita not in fonte

    def test_a_leitura_do_motor_e_a_unica_ida_a_base_de_dados(self, fonte):
        """Contraprova da anterior: ler as fases é preciso, e é `find`-only."""
        assert "carregar_fases" in fonte


# ════════════════════════════════════════════════════════════════════
# OS CAMINHOS LIGADOS — E OS QUE FICAM DE FORA
# ════════════════════════════════════════════════════════════════════

class TestCaminhosLigados:
    """Inventário dos sítios, não só da condição (lição do Lote 5, ponto 1).

    Seis caminhos escrevem `status` num processo. Cinco carimbam o
    relógio; o sexto não carimba POR DECISÃO, e é por isso que também tem
    teste — sem ele, alguém "corrige" a omissão de boa fé daqui a seis
    meses.
    """

    CAMINHOS_COM_RELOGIO = (
        "process_update",
        "process_kanban_move",
        "process_indexing",
        "portal_onboarding_advance",
        "workflow_engine",
    )

    def _fonte(self, nome):
        return codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
        )

    @pytest.mark.parametrize("nome", CAMINHOS_COM_RELOGIO)
    def test_o_caminho_carimba_o_relogio(self, nome):
        fonte = self._fonte(nome)
        assert "transicao_de_fase" in fonte, nome
        assert "montar_update" in fonte, nome

    @pytest.mark.parametrize("nome", CAMINHOS_COM_RELOGIO)
    def test_o_caminho_continua_a_escrever_o_estado(self, nome):
        """Contraprova: o carimbo tem de ir NA MESMA escrita que o estado.

        Duas escritas separadas deixavam uma janela em que o processo
        tinha a fase nova e o relógio da antiga — e se a segunda falhasse,
        ficava assim para sempre.
        """
        fonte = self._fonte(nome)
        assert "montar_update(" in fonte, nome
        assert "processes.update_one" in fonte or "update_one" in fonte, nome

    def test_a_eliminacao_de_uma_fase_NAO_toca_no_relogio(self):
        """Decisão do dono: reestruturar o funil não é avançar.

        "O tempo continua a contar como antes; não queremos esconder
        ineficiência reiniciando os SLAs à força."
        """
        fonte = self._fonte("admin_workflow")

        assert "update_many" in fonte
        assert "transicao_de_fase" not in fonte
        assert "fase_desde" not in fonte

    def test_o_ciclo_de_vida_NAO_toca_no_relogio(self):
        """Soft-delete e restauro escrevem `status` e não são fases.

        Apagar e restaurar um processo não pode limpar a prova de que
        esteve 90 dias em Análise.
        """
        for nome in ("process_delete", "restore_api_process"):
            fonte = self._fonte(nome)
            assert "transicao_de_fase" not in fonte, nome
            assert "fase_desde" not in fonte, nome


class TestProjeccaoDoRelogio:
    """Apanhado por mutação (P18), e resolvido movendo o facto.

    Tirar o `status` da projecção com que dois caminhos leem o processo
    fazia o cronómetro carimbar sem nunca acumular — e era INVISÍVEL nos
    testes, porque a base de dados falsa ignora projecções (contrato
    documentado no `conftest`). Uma mutação que nenhum teste pode matar é
    um sinal de que o facto está no sítio errado: passou a ser uma
    constante do relógio, e uma constante afirma-se.
    """

    @pytest.mark.parametrize("campo", [
        "status",            # sem ele não há macro anterior: não acumula
        "created_at",        # o recurso para um processo recém-criado
        "macro_fase_desde",  # o carimbo de onde sai o intervalo
        "macro_fase_desde_estimado",  # decide se o intervalo é medido
    ])
    def test_a_projeccao_traz_o_que_o_relogio_le(self, campo):
        from services.process_phase_clock import PROJECCAO_DO_RELOGIO

        assert PROJECCAO_DO_RELOGIO.get(campo) == 1

    def test_a_projeccao_nao_traz_dados_pessoais(self):
        """Ler o processo inteiro para ver datas trazia o `personal_data`
        encriptado em cada movimento de cartão."""
        from services.process_phase_clock import PROJECCAO_DO_RELOGIO

        assert "personal_data" not in PROJECCAO_DO_RELOGIO
        assert PROJECCAO_DO_RELOGIO["_id"] == 0

    @pytest.mark.parametrize("nome", ["workflow_engine", "portal_onboarding_advance"])
    def test_quem_le_o_processo_para_o_relogio_usa_a_projeccao(self, nome):
        """Os outros três caminhos já tinham o processo em mão; estes dois
        vão buscá-lo de propósito, e é aqui que a projecção pode divergir.

        A guarda é sobre a CHAMADA e não sobre o texto do ficheiro.
        Primeira versão procurava o nome em qualquer sítio — e o `import`
        sozinho satisfazia-a, pelo que a mutação que trocava a projecção
        por `{"_id": 0}` passou por baixo. É a terceira vez que uma guarda
        minha casa uma GRAFIA em vez de um comportamento (Q13, N-anterior,
        esta): procurar um nome num módulo prova que ele é mencionado, não
        que é usado onde importa.
        """
        import ast

        arvore = ast.parse(
            (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
        )

        def e_a_projeccao(no):
            return isinstance(no, ast.Name) and no.id == "PROJECCAO_DO_RELOGIO"

        chamadas_com_projeccao = [
            no for no in ast.walk(arvore)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "find_one"
            and (
                any(e_a_projeccao(arg) for arg in no.args)
                or any(e_a_projeccao(kw.value) for kw in no.keywords)
            )
        ]

        assert chamadas_com_projeccao, (
            f"{nome}: nenhum `find_one` usa a PROJECCAO_DO_RELOGIO — "
            "o import sozinho não basta"
        )


class TestMacrosSemPermanencia:
    def test_as_terminais_estao_declaradas(self):
        """Um processo concluído não "demora" em concluído, fica lá.

        A medição de produção mostra-o em bruto: 3.200 processos na banda
        `61+` de `concluido` e 820 na de `perdido`. Quem procurar gargalos
        tem de excluir estas macro-fases.
        """
        assert set(MACROS_SEM_PERMANENCIA) == {"concluido", "perdido"}

    def test_a_medicao_usa_a_mesma_lista(self):
        """Duas listas de "o que é terminal" divergem na primeira mudança."""
        from services import phase_clock_coverage

        assert phase_clock_coverage._MACROS_TERMINAIS is MACROS_SEM_PERMANENCIA


# ════════════════════════════════════════════════════════════════════
# O CRONÓMETRO A FUNCIONAR — DE PONTA A PONTA
# ════════════════════════════════════════════════════════════════════

class TestCronometroDePontaAPonta:
    """Não é só o construtor: é o documento na base de dados a mudar.

    A lição dos sobreviventes N8/N9 e P11 dos lotes anteriores foi sempre
    a mesma — **nunca testei a costura**. Um construtor perfeito com o
    caminho de escrita a ignorá-lo passa em todos os testes unitários.

    O caminho escolhido é a AUTOMAÇÃO (`workflow_engine.change_status`),
    de propósito: é o único dos seis que não escreve absolutamente nada em
    `history`. Se o cronómetro funciona aqui, funciona onde o rasto não
    existe — que é a razão de ser do desenho.
    """

    @pytest.fixture
    def db_falso(self, fake_async_db, monkeypatch):
        import services.process_phase_clock as pc
        import services.workflow_engine as we
        import services.workflow_phases as wp

        # O caminho real não recebe `agora` — chama o `agora_utc` do
        # módulo. É para isto que ele está isolado: sem esta injecção, o
        # teste comparava com o relógio da máquina e só passava por
        # tolerância, que é a forma de não afirmar nada.
        monkeypatch.setattr(pc, "agora_utc", lambda: AGORA)

        for fase_doc in FASES:
            fake_async_db.workflow_statuses.docs.append(dict(fase_doc))
        fake_async_db.automation_rules.docs.append({"id": "r-1", "name": "Regra"})

        monkeypatch.setattr(we, "db", fake_async_db)
        monkeypatch.setattr(wp, "db", fake_async_db)
        monkeypatch.setattr("database.db", fake_async_db)
        return fake_async_db

    @staticmethod
    def _regra(nova_fase):
        return {
            "id": "r-1",
            "name": "Regra",
            "action": "change_status",
            "action_config": {"new_status": nova_fase},
        }

    async def test_a_automacao_move_e_o_cronometro_registra(self, db_falso):
        """Doze dias em Análise, medidos por quem não deixa rasto."""
        from services.workflow_engine import execute_action

        db_falso.processes.docs.append(processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=12)).isoformat(),
            CAMPO_FASE_DESDE: (AGORA - timedelta(days=12)).isoformat(),
        }))

        assert await execute_action(self._regra("pre_aprovado"), {"process_id": "p-1"})

        doc = await db_falso.processes.find_one({"id": "p-1"})
        assert doc["status"] == "pre_aprovado"
        assert doc[CAMPO_TEMPOS]["analise"] == 12 * UM_DIA
        assert doc[CAMPO_FASE_DESDE] != (AGORA - timedelta(days=12)).isoformat()
        assert doc[CAMPO_FASE_ESTIMADO] is False

    async def test_duas_transicoes_somam_no_acumulador(self, db_falso):
        """O `$inc` do Mongo soma; o código nunca lê o total para o reescrever.

        É isso que torna o acumulador seguro sob concorrência — e é a razão
        de ser de um contador em vez de um campo que se sobrescreve.
        """
        from services.workflow_engine import execute_action

        db_falso.processes.docs.append(processo(**{
            CAMPO_TEMPOS: {"analise": 5 * UM_DIA},
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=3)).isoformat(),
        }))

        # analise → aprovado (acumula ~3 dias em `analise`)
        await execute_action(self._regra("pre_aprovado"), {"process_id": "p-1"})
        # aprovado → concluidos (acumula o tempo em `aprovado`, ~0)
        await execute_action(self._regra("concluidos"), {"process_id": "p-1"})

        doc = await db_falso.processes.find_one({"id": "p-1"})
        assert doc[CAMPO_TEMPOS]["analise"] >= 8 * UM_DIA
        assert "aprovado" in doc[CAMPO_TEMPOS]
        assert doc["status"] == "concluidos"

    async def test_mover_entre_subfases_nao_reinicia_o_relogio_da_macro(
        self, db_falso,
    ):
        """Na base de dados, não só no construtor."""
        from services.workflow_engine import execute_action

        entrada = (AGORA - timedelta(days=20)).isoformat()
        db_falso.processes.docs.append(processo(**{CAMPO_MACRO_DESDE: entrada}))

        await execute_action(self._regra("fase_documental"), {"process_id": "p-1"})

        doc = await db_falso.processes.find_one({"id": "p-1"})
        assert doc["status"] == "fase_documental"
        assert doc[CAMPO_MACRO_DESDE] == entrada
        assert CAMPO_TEMPOS not in doc or doc.get(CAMPO_TEMPOS) == {}

    async def test_a_automacao_com_a_mesma_fase_nao_toca_no_relogio(self, db_falso):
        """Uma regra mal configurada não pode reiniciar o cronómetro."""
        from services.workflow_engine import execute_action

        entrada = (AGORA - timedelta(days=30)).isoformat()
        db_falso.processes.docs.append(processo(**{
            CAMPO_FASE_DESDE: entrada, CAMPO_MACRO_DESDE: entrada,
        }))

        await execute_action(
            self._regra("analise_documental"), {"process_id": "p-1"},
        )

        doc = await db_falso.processes.find_one({"id": "p-1"})
        assert doc[CAMPO_FASE_DESDE] == entrada
        assert doc[CAMPO_MACRO_DESDE] == entrada

    async def test_um_carimbo_estimado_nao_contamina_o_acumulador(self, db_falso):
        """Ponta a ponta: o backfill semeou, o cronómetro não soma a estimativa."""
        from services.workflow_engine import execute_action

        db_falso.processes.docs.append(processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=400)).isoformat(),
            CAMPO_MACRO_ESTIMADO: True,
            CAMPO_FASE_ESTIMADO: True,
        }))

        await execute_action(self._regra("pre_aprovado"), {"process_id": "p-1"})

        doc = await db_falso.processes.find_one({"id": "p-1"})
        assert CAMPO_TEMPOS not in doc or doc.get(CAMPO_TEMPOS) == {}
        assert doc[CAMPO_MACRO_ESTIMADO] is False


class TestCosturaDoKanban:
    """O arrastar de um cartão: a operação Mongo que sai do caminho real.

    Aqui interessa uma coisa em concreto — que o carimbo vá na MESMA
    escrita que o `status`. Duas escritas separadas deixavam uma janela
    com a fase nova e o relógio da antiga, e se a segunda falhasse ficava
    assim para sempre.
    """

    async def test_o_relogio_vai_na_mesma_escrita_que_o_estado(
        self, fake_async_db, monkeypatch,
    ):
        import services.process_kanban_move as km
        import services.process_phase_clock as pc
        import services.workflow_phases as wp

        monkeypatch.setattr(pc, "agora_utc", lambda: AGORA)

        for fase_doc in FASES:
            fake_async_db.workflow_statuses.docs.append(dict(fase_doc))
        fake_async_db.processes.docs.append(processo(**{
            CAMPO_MACRO_DESDE: (AGORA - timedelta(days=8)).isoformat(),
        }))

        monkeypatch.setattr(km, "db", fake_async_db)
        monkeypatch.setattr(wp, "db", fake_async_db)
        monkeypatch.setattr("database.db", fake_async_db)

        operacoes = []
        original = fake_async_db.processes.update_one

        async def espiar(query, update, **kwargs):
            operacoes.append(update)
            return await original(query, update, **kwargs)

        async def sem_efeitos(**kwargs):
            return {}

        monkeypatch.setattr(fake_async_db.processes, "update_one", espiar)
        monkeypatch.setattr(km, "run_kanban_move_side_effects", sem_efeitos)

        await km.run_move_process_kanban(
            "p-1", "pre_aprovado", {"id": "u-1", "role": "admin"},
            deed_date=None,
            can_view_fn=lambda *a: True,
            inject_cdc_fn=lambda *a: None,
            broadcast_fn=None,
            create_finance_snapshot_fn=None,
        )

        assert len(operacoes) == 1, "o relógio tem de ir na MESMA escrita"
        (operacao,) = operacoes
        assert operacao["$set"]["status"] == "pre_aprovado"
        assert operacao["$set"][CAMPO_FASE_DESDE]
        assert operacao["$inc"][f"{CAMPO_TEMPOS}.analise"] == 8 * UM_DIA
