"""Relatório semanal: segunda-feira, 06h00, UMA vez (Lote 2, ponto 1 / D-7).

A DOCSTRING DIZIA UMA COISA E O CÓDIGO FAZIA OUTRA
==================================================
`send_weekly_ceo_report` abria com «Corre todas as Segundas-feiras às
~06:00 (quando run_all_tasks é invocado pelo worker/scheduler)». A guarda
real era, na íntegra:

    if today.weekday() != 0:
        return False

E o `run_all_tasks` corre de HORA A HORA. Logo:

  1. **Não havia hora nenhuma.** O relatório saía à hora a que o
     Processador tivesse arrancado. Um deploy às 14h punha o relatório
     semanal a sair às 14h para sempre, com a docstring a prometer 06:00.

  2. **Saía 24 VEZES.** `weekday() == 0` é verdade durante as 24 horas da
     segunda-feira e não havia marca de "já enviei esta semana". O
     `send_weekly_ai_report` tem a mesma forma e o mesmo resultado.

Um horário escrito só numa docstring não é um horário — é uma intenção.

PORQUE É QUE A MARCA TEM DE SER PERSISTIDA
==========================================
O `last_runs` do `scheduler_loop` é um dicionário local a uma função:
morre em cada reinício. Com a marca em memória, um reinício numa
segunda-feira às 10h mandava o relatório outra vez — e o Render reinicia
por deploy, por OOM e por manutenção.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import relatorio_semanal_agenda as agenda  # noqa: E402
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios  # noqa: E402

CHAVE = "relatorio_semanal_ceo"

# 2026-10-05 é uma segunda-feira.
SEGUNDA_05H = datetime(2026, 10, 5, 5, 30, tzinfo=timezone.utc)
SEGUNDA_06H = datetime(2026, 10, 5, 6, 5, tzinfo=timezone.utc)
SEGUNDA_14H = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)
TERCA_08H = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)
SEGUNDA_SEGUINTE = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def marcas(fake_async_db, monkeypatch):
    monkeypatch.setattr(agenda, "db", fake_async_db)
    return fake_async_db


class TestAJanela:
    def test_segunda_feira_depois_das_06h_esta_na_janela(self):
        assert agenda.esta_na_janela(SEGUNDA_06H) is True
        assert agenda.esta_na_janela(SEGUNDA_14H) is True

    def test_segunda_feira_ANTES_das_06h_nao_esta(self):
        """O defeito nº1: não havia hora nenhuma."""
        assert agenda.esta_na_janela(SEGUNDA_05H) is False

    def test_terca_feira_nao_esta(self):
        assert agenda.esta_na_janela(TERCA_08H) is False

    def test_a_janela_e_A_PARTIR_de_06h_e_nao_AS_06h(self):
        """O ciclo é horário, logo a hora exacta não é garantível. Uma
        condição de igualdade (`hora == 6`) perdia a semana inteira se o
        ciclo das 06h falhasse ou o processo estivesse a reiniciar."""
        assert agenda.HORA_MINIMA_UTC == 6
        assert agenda.esta_na_janela(SEGUNDA_14H) is True


class TestUmaVezPorSemana:
    @pytest.mark.asyncio
    async def test_a_primeira_passagem_envia(self, marcas):
        assert await agenda.deve_enviar_relatorio_semanal(CHAVE, momento=SEGUNDA_06H) is True

    @pytest.mark.asyncio
    async def test_a_SEGUNDA_passagem_do_mesmo_dia_nao(self, marcas):
        """O defeito nº2: 24 passagens horárias, 24 emails ao CEO."""
        await agenda.marcar_enviado(CHAVE, SEGUNDA_06H)
        assert await agenda.deve_enviar_relatorio_semanal(CHAVE, momento=SEGUNDA_14H) is False

    @pytest.mark.asyncio
    async def test_na_semana_SEGUINTE_volta_a_enviar(self, marcas):
        """Contraprova: sem ela, "nunca envia" passava o teste acima e o
        relatório semanal desaparecia para sempre."""
        await agenda.marcar_enviado(CHAVE, SEGUNDA_06H)
        assert await agenda.deve_enviar_relatorio_semanal(
            CHAVE, momento=SEGUNDA_SEGUINTE
        ) is True

    @pytest.mark.asyncio
    async def test_a_marca_e_PERSISTIDA_e_nao_vive_na_memoria(self, marcas):
        """O `last_runs` do laço morre em cada reinício, e o Render reinicia
        por deploy, por OOM e por manutenção."""
        await agenda.marcar_enviado(CHAVE, SEGUNDA_06H)
        doc = await marcas.job_schedule_marks.find_one({"chave": CHAVE})
        assert doc["semana"] == "2026-W41"

    @pytest.mark.asyncio
    async def test_jobs_diferentes_tem_marcas_independentes(self, marcas):
        await agenda.marcar_enviado(CHAVE, SEGUNDA_06H)
        assert await agenda.deve_enviar_relatorio_semanal(
            "relatorio_ia", momento=SEGUNDA_06H
        ) is True


class TestASemanaEADoCalendario:
    def test_a_etiqueta_e_a_semana_ISO(self):
        assert agenda.etiqueta_da_semana(SEGUNDA_06H) == "2026-W41"

    def test_a_segunda_seguinte_e_outra_semana(self):
        assert agenda.etiqueta_da_semana(SEGUNDA_SEGUINTE) != agenda.etiqueta_da_semana(
            SEGUNDA_06H
        )

    def test_o_mesmo_dia_a_horas_diferentes_e_a_MESMA_semana(self):
        assert agenda.etiqueta_da_semana(SEGUNDA_06H) == agenda.etiqueta_da_semana(
            SEGUNDA_14H
        )

    def test_a_semana_nao_e_ha_mais_de_7_dias(self):
        """"Há 7 dias" faz o envio deslizar de dia a cada semana até o
        relatório sair à quarta-feira."""
        fonte = codigo_da_funcao_sem_comentarios(agenda.etiqueta_da_semana)
        assert "isocalendar" in fonte
        assert "timedelta" not in fonte


class TestAPeriodicidadeConfiguravel:
    """O relatório de IA é diário / semanal / mensal pelo painel de
    administração, e tem a mesma falha de origem. Mas "uma vez" significa
    coisas diferentes em cada periodicidade: usar a etiqueta semanal num
    relatório diário fazia-o sair uma vez por semana — trocar 24 emails a
    mais por 6 a menos não é uma correcção."""

    def test_diario(self):
        assert agenda.etiqueta_do_periodo("daily", SEGUNDA_06H) == "2026-10-05"
        assert agenda.etiqueta_do_periodo("daily", TERCA_08H) == "2026-10-06"

    def test_semanal(self):
        assert agenda.etiqueta_do_periodo("weekly", SEGUNDA_06H) == "2026-W41"

    def test_mensal(self):
        assert agenda.etiqueta_do_periodo("monthly", SEGUNDA_06H) == "2026-10"

    def test_uma_periodicidade_desconhecida_cai_em_semanal(self):
        assert agenda.etiqueta_do_periodo("qualquer-coisa", SEGUNDA_06H) == "2026-W41"
        assert agenda.etiqueta_do_periodo("", SEGUNDA_06H) == "2026-W41"

    @pytest.mark.asyncio
    async def test_no_diario_o_dia_seguinte_volta_a_enviar(self, marcas):
        await agenda.marcar_enviado_no_periodo("relatorio_ia", "daily", SEGUNDA_06H)
        assert await agenda.ja_enviado_no_periodo("relatorio_ia", "daily", SEGUNDA_14H) is True
        assert await agenda.ja_enviado_no_periodo("relatorio_ia", "daily", TERCA_08H) is False


class TestFalhaFECHADA:
    @pytest.mark.asyncio
    async def test_sem_base_de_dados_diz_que_JA_enviou(self, monkeypatch):
        """O custo de não enviar é um relatório em atraso, que se nota. O
        custo de enviar é um ciclo horário a mandar 24 emails ao CEO, que é
        como se ensina alguém a ignorar o relatório."""
        class DbQueRebenta:
            def __getitem__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(agenda, "db", DbQueRebenta())
        assert await agenda.ja_enviado_esta_semana(CHAVE, SEGUNDA_06H) is True

    @pytest.mark.asyncio
    async def test_falhar_a_GRAVAR_a_marca_nao_propaga(self, monkeypatch):
        """O email já saiu; levantar aqui faria o chamador tratar um envio
        bem-sucedido como falha."""
        class DbQueRebenta:
            def __getitem__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(agenda, "db", DbQueRebenta())
        await agenda.marcar_enviado(CHAVE, SEGUNDA_06H)  # não levanta


class TestOForcadoSaltaAJanelaMasNaoAMarca:
    @pytest.mark.asyncio
    async def test_forcado_numa_terca_envia(self, marcas):
        assert await agenda.deve_enviar_relatorio_semanal(
            CHAVE, momento=TERCA_08H, forcado=True
        ) is True

    @pytest.mark.asyncio
    async def test_mas_nao_envia_duas_vezes_na_mesma_semana(self, marcas):
        """Se o forçado saltasse a marca, carregar no botão dez vezes mandava
        dez relatórios — o defeito original pela porta do lado."""
        await agenda.marcar_enviado(CHAVE, SEGUNDA_06H)
        assert await agenda.deve_enviar_relatorio_semanal(
            CHAVE, momento=TERCA_08H, forcado=True
        ) is False


class TestOsDoisRelatoriosEstaoLigadosAAgenda:
    def test_o_relatorio_do_CEO(self):
        from services.scheduled_tasks import ScheduledTasksService
        fonte = codigo_da_funcao_sem_comentarios(
            ScheduledTasksService.send_weekly_ceo_report
        )
        assert "deve_enviar_relatorio_semanal" in fonte
        assert "marcar_enviado" in fonte
        # E já não tem a guarda que só olhava para o dia da semana.
        assert "weekday() != 0" not in fonte

    def test_o_relatorio_de_IA(self):
        from services.scheduled_tasks import ScheduledTasksService
        fonte = codigo_da_funcao_sem_comentarios(
            ScheduledTasksService.send_weekly_ai_report
        )
        assert "ja_enviado_no_periodo" in fonte
        assert "marcar_enviado_no_periodo" in fonte

    def test_a_marca_e_gravada_DEPOIS_do_envio_confirmado(self):
        """Marcar antes perdia a semana inteira se o SMTP falhasse."""
        from services.scheduled_tasks import ScheduledTasksService
        fonte = codigo_da_funcao_sem_comentarios(
            ScheduledTasksService.send_weekly_ceo_report
        )
        assert fonte.index("result.get") < fonte.index("marcar_enviado(")

    @pytest.mark.asyncio
    async def test_CONTRAPROVA_a_agenda_recusa_mesmo(self, marcas):
        """Sem isto, as guardas de fonte acima passavam com uma agenda que
        dissesse sempre sim — a chamada existe e não decide nada."""
        assert await agenda.deve_enviar_relatorio_semanal(CHAVE, momento=TERCA_08H) is False
        assert await agenda.deve_enviar_relatorio_semanal(CHAVE, momento=SEGUNDA_05H) is False
        assert await agenda.deve_enviar_relatorio_semanal(CHAVE, momento=SEGUNDA_06H) is True
