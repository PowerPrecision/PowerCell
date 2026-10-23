"""SLA do Index, nível 2 — a estagnação conta DIAS ÚTEIS (sábados e domingos não contam).

O cliente viu um processo marcado como parado numa segunda-feira por causa de um fim-de-semana. A regra é
afirmada sobre as funções de PRODUÇÃO (`tempo_util`, `esta_estagnado`, `deve_alertar`), com datas reais de
Outubro de 2026 (segunda = 12, 19, 26) e o fuso de Lisboa (WEST até 25/10).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services import index_sla as sla

LISBOA = sla.FUSO_DOS_DIAS_UTEIS


def lx(dia: int, hora: int = 10, minuto: int = 0, mes: int = 10) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, tzinfo=LISBOA)


def processo(ultima: datetime, **extra) -> dict:
    return {
        "assigned_indexacao_id": "u1", "index_status": "in_review",
        "index_last_activity_at": ultima.isoformat(), **extra,
    }


class TestTempoUtil:
    def test_o_fim_de_semana_nao_conta(self):
        # sexta 17:00 → segunda 09:00: 7 h de sexta + 9 h de segunda
        assert sla.tempo_util(lx(16, 17), lx(19, 9)) == timedelta(hours=16)

    def test_so_fim_de_semana_e_zero(self):
        assert sla.tempo_util(lx(17, 8), lx(18, 22)) == timedelta(0)

    def test_uma_semana_de_calendario_sao_cinco_dias_uteis(self):
        assert sla.tempo_util(lx(12, 10), lx(19, 10)) == timedelta(days=5)

    def test_dois_fins_de_semana_nao_contam(self):
        assert sla.tempo_util(lx(12, 10), lx(26, 10, mes=10)) == timedelta(days=10)

    def test_o_dia_de_semana_conta_inteiro(self):
        assert sla.tempo_util(lx(13, 0), lx(14, 0)) == timedelta(days=1)

    def test_ate_antes_de_desde_e_zero(self):
        assert sla.tempo_util(lx(14), lx(13)) == timedelta(0)

    def test_o_sabado_e_o_de_lisboa_nao_o_de_utc(self):
        # sexta 23:30 UTC já é sábado 00:30 em Lisboa (UTC+1): essa meia hora NÃO conta;
        # segunda 00:00 de Lisboa = domingo 23:00 UTC
        desde = datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc)
        ate = datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc)
        assert sla.tempo_util(desde, ate) == timedelta(0)

    def test_aceita_momentos_em_utc(self):
        assert sla.tempo_util(lx(12, 10).astimezone(timezone.utc), lx(13, 10).astimezone(timezone.utc)) == timedelta(days=1)

    def test_uma_data_absurda_nao_pendura_o_job(self):
        antigo = datetime(1970, 1, 1, tzinfo=timezone.utc)
        assert sla.tempo_util(antigo, lx(19)) > timedelta(days=100)   # termina (tecto do laço)

    def test_dias_uteis_completos(self):
        assert sla.dias_uteis_parado(lx(12, 10), lx(20, 9)) == 5


class TestEstagnadoEmDiasUteis:
    def test_seis_dias_de_calendario_com_fim_de_semana_ainda_nao_e_estagnado(self):
        # sex 16/10 10:00 → qui 22/10 10:00: 6 dias de calendário, 4 úteis. Com dias de calendário era estagnado.
        p = processo(lx(16, 10))
        assert sla.esta_estagnado(p, lx(22, 10), 5) is False

    def test_cinco_dias_uteis_exactos_ainda_nao(self):
        p = processo(lx(16, 10))
        assert sla.esta_estagnado(p, lx(23, 10), 5) is False       # sexta → sexta: 5 dias úteis, não é «mais de» 5

    def test_passados_os_cinco_dias_uteis_e_estagnado(self):
        p = processo(lx(16, 10))
        assert sla.esta_estagnado(p, lx(23, 10, 1), 5) is True

    def test_o_fim_de_semana_no_meio_adia_o_prazo(self):
        # sexta 10:00 + 5 dias de calendário (quarta 21/10) seriam estagnado; em dias úteis ainda não
        p = processo(lx(16, 10))
        assert sla.esta_estagnado(p, lx(21, 11), 5) is False

    def test_um_fim_de_semana_nunca_estagna_sozinho(self):
        p = processo(lx(16, 17))
        assert sla.esta_estagnado(p, lx(18, 23), 1) is False      # só 7 h de sexta decorreram
        assert sla.esta_estagnado(p, lx(20, 8), 2) is False       # 39 h úteis < 2 dias
        assert sla.esta_estagnado(p, lx(20, 8), 1) is True        # 39 h úteis > 1 dia

    def test_continua_a_exigir_in_review_e_atribuido(self):
        assert sla.esta_estagnado({**processo(lx(12)), "index_status": "pending"}, lx(26), 5) is False
        assert sla.esta_estagnado({**processo(lx(12)), "assigned_indexacao_id": None}, lx(26), 5) is False
        assert sla.esta_estagnado({**processo(lx(12)), "is_indexed": True}, lx(26), 5) is False

    def test_a_actividade_mais_recente_reinicia_a_contagem(self):
        p = processo(lx(23, 10))        # sexta
        assert sla.esta_estagnado(p, lx(26, 10, mes=10), 5) is False


class TestLembreteEmDiasUteis:
    def test_o_lembrete_so_depois_de_cinco_dias_uteis(self):
        base = processo(lx(5, 10), index_stagnation_alerted_at=lx(12, 10).isoformat())
        assert sla.deve_alertar(base, lx(16, 10), 5) is False     # 4 dias úteis depois do alerta
        assert sla.deve_alertar(base, lx(19, 10), 5) is True      # 5 dias úteis (uma semana)

    def test_o_lembrete_nao_se_conta_pelo_calendario(self):
        # alertado sexta; 5 dias de calendário depois (quarta) são 3 úteis → ainda não
        base = processo(lx(1, 10), index_stagnation_alerted_at=lx(9, 10).isoformat())
        assert sla.deve_alertar(base, lx(14, 10), 5) is False

    def test_actividade_depois_do_alerta_reabre_o_ciclo(self):
        p = processo(lx(15, 10), index_stagnation_alerted_at=lx(8, 10).isoformat())
        # com actividade posterior ao alerta o ciclo recomeça (só alerta se voltar a estagnar)
        assert sla.deve_alertar(p, lx(16, 10), 5) is False


class TestAMensagem:
    @pytest.mark.parametrize("texto", ["dias úteis"])
    def test_a_mensagem_diz_dias_uteis(self, texto):
        import inspect

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(inspect.getsource(sla.alertar_estagnados))
        assert texto in fonte
        assert "(agora - desde).days" not in fonte        # contraprova: já não conta o calendário
