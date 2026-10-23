"""D-30 — a parte PURA do health check dos scrapers do Estado: classificar e decidir quando avisar."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services import gov_scrapers_healthcheck as h

AGORA = datetime(2026, 10, 23, 6, 0, tzinfo=timezone.utc)


class R:
    """O que o scraper devolve (só o que o classificador lê)."""

    def __init__(self, success=False, error=None, step_failed=None, documents=None, screenshot_b64=None):
        self.success, self.error, self.step_failed = success, error, step_failed
        self.documents = documents or []
        self.screenshot_b64 = screenshot_b64


class TestClassificar:
    def test_sucesso_com_documentos_e_ok(self):
        assert h.classificar(R(success=True, documents=[object()])).veredicto == h.OK

    def test_sucesso_sem_documentos_nao_prova_nada(self):
        assert h.classificar(R(success=True)).veredicto == h.SELECTORES

    @pytest.mark.parametrize("passo", ["fill_nif", "fill_niss", "fill_password", "submit_login", "select_nif_tab",
                                       "navigate_irs", "navigate_documents", "download_irs", "download_extrato"])
    def test_selector_desatualizado_em_qualquer_passo(self, passo):
        d = h.classificar(R(error="selector_desatualizado", step_failed=passo))
        assert d.veredicto == h.SELECTORES and d.passo == passo

    @pytest.mark.parametrize("passo", ["check_login", "init", ""])
    def test_o_codigo_selector_desatualizado_manda_seja_qual_for_o_passo(self, passo):
        """O próprio scraper diz que o selector mudou: nem um passo desconhecido nem o de rede o desmentem."""
        assert h.classificar(R(error="selector_desatualizado", step_failed=passo)).veredicto == h.SELECTORES

    def test_sem_documentos_depois_do_login_e_selectores(self):
        assert h.classificar(R(error="sem_documentos", step_failed="download_irs")).veredicto == h.SELECTORES

    def test_um_passo_de_preenchimento_com_excepcao_desconhecida_e_selectores(self):
        # O Playwright falhou a preencher o campo: a página mudou.
        assert h.classificar(R(error="Error", step_failed="fill_nif")).veredicto == h.SELECTORES

    def test_credenciais_recusadas_nao_sao_selectores(self):
        assert h.classificar(R(error="credenciais_invalidas", step_failed="check_login")).veredicto == h.CREDENCIAIS

    @pytest.mark.parametrize("erro", ["mfa_requerido", "mfa_timeout", "mfa_codigo_incorreto", "mfa_error", "mfa_no_input"])
    def test_mfa_nao_e_selectores_nem_saudavel(self, erro):
        d = h.classificar(R(error=erro, step_failed="check_login"))
        assert d.veredicto == h.MFA

    @pytest.mark.parametrize("erro,passo", [
        ("timeout_login", "fill_nif"), ("timeout", "download_irs"), ("scraper_ocupado", "semaphore_wait"),
        ("unexpected_error", "check_login"), ("TimeoutError", "navigate_irs"),
    ])
    def test_rede_e_bloqueio_nao_sao_selectores(self, erro, passo):
        assert h.classificar(R(error=erro, step_failed=passo)).veredicto == h.REDE

    def test_a_pagina_de_login_que_nao_carrega_e_rede(self):
        assert h.classificar(R(error="Error", step_failed="navigate_login")).veredicto == h.REDE

    def test_excepcao_desconhecida_fora_dos_passos_de_preenchimento_e_rede(self):
        assert h.classificar(R(error="TargetClosedError", step_failed="check_login")).veredicto == h.REDE

    def test_o_erro_so_sai_como_codigo(self):
        d = h.classificar(R(error="Falhou: NIF 123456789 pwd=abc", step_failed="fill_nif"))
        assert d.erro == "erro_desconhecido" and "123456789" not in d.erro

    def test_um_codigo_com_a_forma_de_codigo_passa(self):
        assert h.classificar(R(error="selector_desatualizado", step_failed="fill_nif")).erro == "selector_desatualizado"


class TestDecidirAlerta:
    def _sel(self):
        return h.Diagnostico(h.SELECTORES, "fill_nif", "selector_desatualizado")

    def test_selectores_na_primeira_vez_e_critico(self):
        a = h.decidir_alerta("financas", {}, self._sel(), agora=AGORA)
        assert a and a.nivel == h.NIVEL_CRITICO and a.veredicto == h.SELECTORES

    def test_o_mesmo_veredicto_nao_volta_a_avisar_dentro_do_prazo(self):
        anterior = {"alertado_veredicto": h.SELECTORES, "alertado_em": (AGORA - timedelta(days=2)).isoformat()}
        assert h.decidir_alerta("financas", anterior, self._sel(), agora=AGORA) is None

    def test_volta_a_avisar_passado_o_prazo(self):
        anterior = {"alertado_veredicto": h.SELECTORES,
                    "alertado_em": (AGORA - timedelta(days=h.REPETIR_ALERTA_DIAS, minutes=1)).isoformat()}
        assert h.decidir_alerta("financas", anterior, self._sel(), agora=AGORA) is not None

    def test_veredicto_diferente_avisa_logo(self):
        anterior = {"alertado_veredicto": h.CREDENCIAIS, "alertado_em": (AGORA - timedelta(hours=1)).isoformat()}
        assert h.decidir_alerta("financas", anterior, self._sel(), agora=AGORA) is not None

    def test_credenciais_e_mfa_sao_avisos_nao_criticos(self):
        for v in (h.CREDENCIAIS, h.MFA):
            a = h.decidir_alerta("financas", {}, h.Diagnostico(v), agora=AGORA)
            assert a and a.nivel == h.NIVEL_AVISO

    def test_os_avisos_de_conta_repetem_se_mais_devagar(self):
        anterior = {"alertado_veredicto": h.CREDENCIAIS, "alertado_em": (AGORA - timedelta(days=5)).isoformat()}
        assert h.decidir_alerta("financas", anterior, h.Diagnostico(h.CREDENCIAIS), agora=AGORA) is None
        anterior["alertado_em"] = (AGORA - timedelta(days=8)).isoformat()
        assert h.decidir_alerta("financas", anterior, h.Diagnostico(h.CREDENCIAIS), agora=AGORA) is not None

    def test_rede_so_avisa_a_segunda_falha_seguida(self):
        d = h.Diagnostico(h.REDE, "", "timeout")
        assert h.decidir_alerta("financas", {"falhas_seguidas": 1}, d, agora=AGORA) is None
        assert h.decidir_alerta("financas", {"falhas_seguidas": 2}, d, agora=AGORA) is not None

    def test_ok_sem_historico_de_alerta_nao_diz_nada(self):
        assert h.decidir_alerta("financas", {}, h.Diagnostico(h.OK), agora=AGORA) is None

    def test_ok_depois_de_um_alerta_avisa_que_recuperou(self):
        anterior = {"alertado_veredicto": h.SELECTORES, "alertado_em": AGORA.isoformat()}
        a = h.decidir_alerta("financas", anterior, h.Diagnostico(h.OK), agora=AGORA)
        assert a and a.recuperou and a.nivel == h.NIVEL_AVISO

    def test_nao_configurado_avisa_semanalmente(self):
        d = h.Diagnostico(h.NAO_CONFIGURADO)
        assert h.decidir_alerta("financas", {}, d, agora=AGORA) is not None
        recente = {"alertado_veredicto": h.NAO_CONFIGURADO, "alertado_em": (AGORA - timedelta(days=3)).isoformat()}
        assert h.decidir_alerta("financas", recente, d, agora=AGORA) is None

    def test_data_ilegivel_avisa_em_vez_de_calar(self):
        anterior = {"alertado_veredicto": h.SELECTORES, "alertado_em": "lixo"}
        assert h.decidir_alerta("financas", anterior, self._sel(), agora=AGORA) is not None


class TestMensagem:
    def test_critico_diz_manutencao_preventiva_e_o_portal(self):
        assunto, corpo = h.mensagem_do_alerta(h.Alerta(h.NIVEL_CRITICO, "financas", h.SELECTORES, "fill_nif", "selector_desatualizado"))
        assert "Portal das Finanças" in assunto and "manutenção" in assunto
        assert "FINANCAS_SEL" in corpo and "fill_nif" in corpo

    def test_seg_social_aponta_para_a_tabela_certa(self):
        _a, corpo = h.mensagem_do_alerta(h.Alerta(h.NIVEL_CRITICO, "seg_social", h.SELECTORES, "", ""))
        assert "SEG_SOCIAL_SEL" in corpo and "FINANCAS_SEL" not in corpo

    def test_mfa_nao_se_apresenta_como_saudavel(self):
        _a, corpo = h.mensagem_do_alerta(h.Alerta(h.NIVEL_AVISO, "financas", h.MFA, "check_login", "mfa_requerido"))
        assert "NÃO se sabe" in corpo

    def test_recuperado(self):
        assunto, _c = h.mensagem_do_alerta(h.Alerta(h.NIVEL_AVISO, "financas", h.OK, "", "", recuperou=True))
        assert "recuperado" in assunto


class TestCredenciais:
    def test_sem_variaveis_nada_configurado(self):
        assert h.credenciais_de_teste({}) == {"financas": None, "seg_social": None}

    def test_so_o_nif_nao_chega(self):
        assert h.credenciais_de_teste({"GOV_TEST_NIF": "123456789"}) == {"financas": None, "seg_social": None}

    def test_seg_social_usa_o_niss_quando_existe(self):
        c = h.credenciais_de_teste({"GOV_TEST_NIF": "123456789", "GOV_TEST_PWD": "p", "GOV_TEST_NISS": "11122233344"})
        assert c["financas"] == ("123456789", "p") and c["seg_social"] == ("11122233344", "p")

    def test_seg_social_recua_para_o_nif(self):
        c = h.credenciais_de_teste({"GOV_TEST_NIF": "123456789", "GOV_TEST_PWD": "p"})
        assert c["seg_social"] == ("123456789", "p")

    @pytest.mark.parametrize("valor,esperado", [("false", False), ("0", False), ("OFF", False), ("true", True), ("", True)])
    def test_interruptor(self, valor, esperado):
        assert h.esta_ligado({"GOV_HEALTHCHECK_ENABLED": valor}) is esperado

    def test_ligado_por_omissao(self):
        assert h.esta_ligado({}) is True
