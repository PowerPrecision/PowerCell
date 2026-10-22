"""Slow backfill do Index — as partes PURAS e a estrutura do script (sem MongoDB)."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import index_slow_backfill as sb
from services.index_ai import TIPO_EXTRATO, TIPO_RECIBO

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "slow_backfill_ia.py"


class TestTamanhoDoLote:
    def test_omissao(self):
        assert sb.tamanho_do_lote({}) == 20 == sb.LOTE_POR_OMISSAO

    def test_variavel_de_ambiente(self):
        assert sb.tamanho_do_lote({"SLOW_BACKFILL_BATCH_SIZE": "35"}) == 35

    @pytest.mark.parametrize("valor", ["0", "-5", "abc", "", "1.5", None])
    def test_invalido_ou_nao_positivo_cai_na_omissao_e_nunca_desliga_o_tecto(self, valor):
        assert sb.tamanho_do_lote({"SLOW_BACKFILL_BATCH_SIZE": valor}) == 20

    def test_nunca_acima_do_tecto(self):
        assert sb.tamanho_do_lote({"SLOW_BACKFILL_BATCH_SIZE": "100000"}) == sb.TECTO_DO_LOTE

    def test_o_argumento_vence_a_variavel(self):
        assert sb.tamanho_do_lote({"SLOW_BACKFILL_BATCH_SIZE": "35"}, pedido=7) == 7
        assert sb.tamanho_do_lote({}, pedido=0) == 20
        assert sb.tamanho_do_lote({}, pedido=10**6) == sb.TECTO_DO_LOTE


class TestPausa:
    def test_omissao_e_valor_valido(self):
        assert sb.pausa_entre_chamadas({}) == 1.0
        assert sb.pausa_entre_chamadas({"SLOW_BACKFILL_PAUSE_SECONDS": "0"}) == 0.0
        assert sb.pausa_entre_chamadas({"SLOW_BACKFILL_PAUSE_SECONDS": "2.5"}) == 2.5

    def test_invalido_ou_negativo_cai_na_omissao_e_ha_tecto(self):
        assert sb.pausa_entre_chamadas({"SLOW_BACKFILL_PAUSE_SECONDS": "x"}) == 1.0
        assert sb.pausa_entre_chamadas({"SLOW_BACKFILL_PAUSE_SECONDS": "-3"}) == 1.0
        assert sb.pausa_entre_chamadas({"SLOW_BACKFILL_PAUSE_SECONDS": "9999"}) == 60.0


class TestCondicaoDosCandidatos:
    AGORA = datetime(2026, 10, 22, tzinfo=timezone.utc)

    def test_cobre_os_dois_tipos_por_omissao(self):
        ramos = sb.condicao_dos_candidatos(agora=self.AGORA)["$and"][0]["$or"]
        assert {r["index_facts.tipo"] for r in ramos} == {TIPO_EXTRATO, TIPO_RECIBO}

    def test_so_um_tipo(self):
        ramos = sb.condicao_dos_candidatos((TIPO_EXTRATO,), agora=self.AGORA)["$and"][0]["$or"]
        assert [r["index_facts.tipo"] for r in ramos] == [TIPO_EXTRATO]

    def test_um_tipo_desconhecido_nao_casa_com_nada(self):
        assert sb.condicao_dos_candidatos(("outro",), agora=self.AGORA) == {"id": {"$in": []}}

    def test_exclui_o_que_nao_se_pode_reler_nem_repetir(self):
        c = sb.condicao_dos_candidatos(agora=self.AGORA)
        assert c["is_clean_pdf"] == {"$ne": True}
        assert c["file_state"] == {"$ne": "purgado"}
        assert c["analysis_fingerprint"] == {"$nin": [None, ""]}
        assert c[f"{sb.CAMPO_DA_MARCA}.estado"] == {"$exists": False}

    def test_o_campo_em_falta_inclui_ausente_nulo_e_vazio(self):
        ramos = sb.condicao_dos_candidatos(agora=self.AGORA)["$and"][0]["$or"]
        for ramo in ramos:
            valores = [v for k, v in ramo.items() if k.endswith(("bank_key", "employer_location"))]
            assert valores == [{"$in": [None, ""]}]

    def test_a_reserva_expirada_volta_a_valer(self):
        reserva = sb.condicao_dos_candidatos(agora=self.AGORA)["$and"][1]["$or"]
        assert {f"{sb.CAMPO_DA_MARCA}.reservado_ate": {"$lte": self.AGORA}} in reserva


class TestPatchDoCampo:
    def _extrato(self, **factos):
        return SimpleNamespace(factos=factos, job=None)

    def test_extrato_com_banco_escreve_so_os_dois_campos_do_banco(self):
        p = sb.patch_do_campo(TIPO_EXTRATO, self._extrato(bank="Caixa Geral", bank_key="cgd", iban="PT50..."))
        assert p == {"index_facts.bank": "Caixa Geral", "index_facts.bank_key": "cgd"}

    @pytest.mark.parametrize("factos", [{}, {"bank": "X"}, {"bank_key": "x"}, {"bank": "", "bank_key": ""}])
    def test_extrato_sem_banco_completo_nao_escreve(self, factos):
        assert sb.patch_do_campo(TIPO_EXTRATO, self._extrato(**factos)) is None

    def test_recibo_com_localidade(self):
        r = SimpleNamespace(factos={}, job=SimpleNamespace(employer_location="Porto"))
        assert sb.patch_do_campo(TIPO_RECIBO, r) == {"index_job.employer_location": "Porto"}

    @pytest.mark.parametrize("job", [None, SimpleNamespace(employer_location=None), SimpleNamespace(employer_location="")])
    def test_recibo_sem_localidade_nao_escreve(self, job):
        assert sb.patch_do_campo(TIPO_RECIBO, SimpleNamespace(factos={}, job=job)) is None

    def test_o_patch_nunca_toca_na_impressao_digital(self):
        for p in (sb.patch_do_campo(TIPO_EXTRATO, self._extrato(bank="B", bank_key="b")),
                  sb.patch_do_campo(TIPO_RECIBO, SimpleNamespace(factos={}, job=SimpleNamespace(employer_location="L")))):
            assert not any("fingerprint" in k for k in p)


class TestOScript:
    def test_chama_o_servico_e_nao_toca_na_base_de_dados_directamente(self):
        fonte = SCRIPT.read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
        assert "db" not in nomes
        assert "correr_lote" in fonte and "sb.correr_lote" in fonte  # contraprova de que lê o sítio certo

    def test_a_omissao_nao_chama_a_ia(self):
        fonte = SCRIPT.read_text(encoding="utf-8")
        # a chamada ao lote vem DEPOIS do `if not args.aplicar: … return 0`
        assert fonte.index("if not args.aplicar") < fonte.index("sb.correr_lote")

    def test_documenta_o_cron_e_as_variaveis(self):
        fonte = SCRIPT.read_text(encoding="utf-8")
        for texto in ("SLOW_BACKFILL_BATCH_SIZE", "SLOW_BACKFILL_PAUSE_SECONDS", "*/30", "--aplicar"):
            assert texto in fonte
