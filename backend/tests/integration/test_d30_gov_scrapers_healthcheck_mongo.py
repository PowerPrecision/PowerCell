"""D-30 contra um MongoDB REAL: o job diário, de ponta a ponta, sem browser nem portais.

O que se falseia é a FRONTEIRA do mundo exterior: as duas funções de extracção de produção
(`fetch_financas_documents` / `fetch_seg_social_documents`, que devolvem um `ScraperResult` verdadeiro),
o envio de email e a notificação in-app (gravam o que lhes pedem). Tudo o resto é o código real:
a classificação, a decisão de avisar, o estado persistido, os destinatários (lidos de `db.users`).

O que se prova:
* selectores partidos → alerta CRÍTICO a Master e Admins, e só uma vez por estado;
* credenciais / MFA / rede → aviso só aos Master (a rede só à segunda falha seguida);
* nada da conta de teste (NIF, password, screenshot) chega à base de dados, aos emails, às notificações nem aos logs;
* fora de produção o job diz que saltou (o scraper simulado «passaria» e seria mentira);
* sem variáveis o job diz que não verificou (e avisa os Master semanalmente);
* a execução automática respeita o intervalo; a forçada não.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import gov_scrapers_healthcheck as h
from services.gov_scraper import ScraperDocument, ScraperResult

NIF = "234567891"
PWD = "Pa55-w0rd-SECRETA"
NISS = "11122233344"
AGORA = datetime(2026, 10, 23, 6, 0, tzinfo=timezone.utc)


def _ok():
    return ScraperResult(success=True, documents=[ScraperDocument("irs.pdf", b"%PDF", label="IRS")])


def _falha(erro, passo):
    return ScraperResult(success=False, error=erro, step_failed=passo, screenshot_b64="U0NSRUVOU0hPVC1DT00tTklG")


class Mundo:
    """Regista o que saiu para o exterior e o que o scraper foi chamado a fazer."""

    def __init__(self):
        self.resultados = {"financas": _ok(), "seg_social": _ok()}
        self.chamadas: list[tuple[str, str, str]] = []
        self.emails: list[dict] = []
        self.notificacoes: list[dict] = []

    async def financas(self, nif, pwd, process_id=None):
        self.chamadas.append(("financas", nif, pwd))
        assert process_id is None, "o health check não pode usar o fluxo MFA de um cliente"
        return self.resultados["financas"]

    async def seg_social(self, niss, pwd, process_id=None):
        self.chamadas.append(("seg_social", niss, pwd))
        return self.resultados["seg_social"]

    async def email(self, **kw):
        self.emails.append(kw)
        return {"success": True}

    async def notificacao(self, **kw):
        self.notificacoes.append(kw)
        return {"id": "n"}


@pytest_asyncio.fixture
async def ambiente(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_d30_{uuid.uuid4().hex[:8]}"]
    await base.users.insert_many([
        {"id": "m1", "email": "master@x.pt", "role": "master", "is_active": True},
        {"id": "a1", "email": "admin@x.pt", "role": "admin", "is_active": True},
        {"id": "a2", "email": "admin-inativo@x.pt", "role": "admin", "is_active": False},
        {"id": "c1", "email": "ceo@x.pt", "role": "ceo", "is_active": True},
        {"id": "k1", "email": "consultor@x.pt", "role": "consultor", "is_active": True},
    ])
    mundo = Mundo()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GOV_TEST_NIF", NIF)
    monkeypatch.setenv("GOV_TEST_PWD", PWD)
    monkeypatch.delenv("GOV_TEST_NISS", raising=False)
    monkeypatch.delenv("GOV_HEALTHCHECK_ENABLED", raising=False)
    from services import alert_audience, gov_scraper, realtime_notifications
    import services.email_service as email_service

    with patch.object(h, "db", base), patch.object(alert_audience, "db", base), \
            patch.object(gov_scraper, "fetch_financas_documents", mundo.financas), \
            patch.object(gov_scraper, "fetch_seg_social_documents", mundo.seg_social), \
            patch.object(email_service, "send_email", mundo.email), \
            patch.object(realtime_notifications, "send_realtime_notification", mundo.notificacao):
        yield h, base, mundo
    await cliente.drop_database(base.name)
    cliente.close()


def _destinos(mundo):
    return sorted(e["to_emails"][0] for e in mundo.emails)


@pytest.mark.asyncio
class TestSelectoresPartidos:
    async def test_alerta_critico_a_master_e_admins_activos(self, ambiente):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("selector_desatualizado", "fill_nif")

        relatorio = await modulo.correr_healthcheck(agora=AGORA)

        assert relatorio == {"financas": "selectores", "seg_social": "ok"}
        assert _destinos(mundo) == ["admin@x.pt", "master@x.pt"]
        assert sorted(n["user_id"] for n in mundo.notificacoes) == ["a1", "m1"]
        assert "Portal das Finanças" in mundo.emails[0]["subject"]
        assert "FINANCAS_SEL" in mundo.emails[0]["body"]

    async def test_o_mesmo_estado_nao_volta_a_avisar_no_dia_seguinte(self, ambiente):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("selector_desatualizado", "fill_nif")
        await modulo.correr_healthcheck(agora=AGORA)
        n = len(mundo.emails)
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=1))
        assert len(mundo.emails) == n

    async def test_volta_a_avisar_passados_tres_dias(self, ambiente):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("selector_desatualizado", "fill_nif")
        await modulo.correr_healthcheck(agora=AGORA)
        n = len(mundo.emails)
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=3, hours=1))
        assert len(mundo.emails) == 2 * n

    async def test_seg_social_chama_o_scraper_certo_com_o_niss(self, ambiente, monkeypatch):
        modulo, base, mundo = ambiente
        monkeypatch.setenv("GOV_TEST_NISS", NISS)
        mundo.resultados["seg_social"] = _falha("selector_desatualizado", "fill_niss")
        relatorio = await modulo.correr_healthcheck(agora=AGORA)
        assert relatorio["seg_social"] == "selectores" and relatorio["financas"] == "ok"
        assert ("seg_social", NISS, PWD) in mundo.chamadas and ("financas", NIF, PWD) in mundo.chamadas
        assert "SEG_SOCIAL_SEL" in mundo.emails[0]["body"]

    async def test_recuperacao_avisa_so_os_master(self, ambiente):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("selector_desatualizado", "fill_nif")
        await modulo.correr_healthcheck(agora=AGORA)
        mundo.emails.clear()
        mundo.resultados["financas"] = _ok()
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=1))
        assert _destinos(mundo) == ["master@x.pt"]
        assert "recuperado" in mundo.emails[0]["subject"]
        estado = await base.gov_scrapers_health.find_one({"portal": "financas"})
        assert estado["veredicto"] == "ok" and estado["falhas_seguidas"] == 0 and estado["alertado_veredicto"] is None


@pytest.mark.asyncio
class TestOutrasFalhas:
    @pytest.mark.parametrize("erro,passo,veredicto", [
        ("credenciais_invalidas", "check_login", "credenciais"),
        ("mfa_requerido", "check_login", "mfa"),
    ])
    async def test_conta_de_teste_avisa_so_os_master(self, ambiente, erro, passo, veredicto):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha(erro, passo)
        relatorio = await modulo.correr_healthcheck(agora=AGORA)
        assert relatorio["financas"] == veredicto
        assert _destinos(mundo) == ["master@x.pt"]

    async def test_rede_so_avisa_a_segunda_falha_seguida(self, ambiente):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("timeout_login", "check_login")
        await modulo.correr_healthcheck(agora=AGORA)
        assert mundo.emails == []
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=1))
        assert _destinos(mundo) == ["master@x.pt"]

    async def test_rede_isolada_seguida_de_sucesso_zera_a_contagem(self, ambiente):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("timeout_login", "check_login")
        await modulo.correr_healthcheck(agora=AGORA)
        mundo.resultados["financas"] = _ok()
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=1))
        mundo.resultados["financas"] = _falha("timeout_login", "check_login")
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=2))
        assert mundo.emails == []

    async def test_excepcao_do_scraper_nao_derruba_o_job(self, ambiente):
        modulo, base, mundo = ambiente

        async def rebenta(*_a, **_k):
            raise RuntimeError(f"falhou com {NIF} e {PWD}")

        from services import gov_scraper

        with patch.object(gov_scraper, "fetch_financas_documents", rebenta):
            relatorio = await modulo.correr_healthcheck(agora=AGORA)
        assert relatorio["financas"] == "rede" and relatorio["seg_social"] == "ok"
        estado = await base.gov_scrapers_health.find_one({"portal": "financas"})
        assert estado["erro"] == "RuntimeError"


@pytest.mark.asyncio
class TestNadaDaContaDeTesteSai:
    async def test_nem_a_base_de_dados_nem_os_emails_nem_os_logs(self, ambiente, caplog):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("selector_desatualizado", "fill_nif")
        mundo.resultados["seg_social"] = _falha("credenciais_invalidas", "check_login")
        with caplog.at_level(logging.DEBUG):
            await modulo.correr_healthcheck(agora=AGORA)

        tudo = repr([d async for d in base.gov_scrapers_health.find({}, {"_id": 0})])
        tudo += repr(mundo.emails) + repr(mundo.notificacoes) + caplog.text
        for segredo in (NIF, PWD, "U0NSRUVOU0hPVC1DT00tTklG"):
            assert segredo not in tudo, f"{segredo!r} vazou"

    async def test_o_screenshot_e_deitado_fora(self, ambiente):
        modulo, base, mundo = ambiente
        resultado = _falha("selector_desatualizado", "fill_nif")
        mundo.resultados["financas"] = resultado
        await modulo.correr_healthcheck(agora=AGORA)
        assert resultado.screenshot_b64 is None


@pytest.mark.asyncio
class TestQuandoNaoVerifica:
    async def test_fora_de_producao_salta_e_di_lo(self, ambiente, monkeypatch):
        modulo, base, mundo = ambiente
        monkeypatch.setenv("ENVIRONMENT", "dev")
        assert await modulo.correr_healthcheck(agora=AGORA) == {"saltado": "fora_de_producao"}
        assert mundo.chamadas == [] and mundo.emails == []

    async def test_desligado_por_variavel(self, ambiente, monkeypatch):
        modulo, base, mundo = ambiente
        monkeypatch.setenv("GOV_HEALTHCHECK_ENABLED", "false")
        assert await modulo.correr_healthcheck(agora=AGORA) == {"saltado": "desligado"}
        assert mundo.chamadas == []

    async def test_sem_credenciais_nao_finge_que_verificou(self, ambiente, monkeypatch):
        modulo, base, mundo = ambiente
        monkeypatch.delenv("GOV_TEST_NIF")
        relatorio = await modulo.correr_healthcheck(agora=AGORA)
        assert relatorio == {"financas": "nao_configurado", "seg_social": "nao_configurado"}
        assert mundo.chamadas == []
        assert _destinos(mundo) == ["master@x.pt"], "um só aviso, só aos Master"

    async def test_sem_credenciais_so_avisa_uma_vez_por_semana(self, ambiente, monkeypatch):
        modulo, base, mundo = ambiente
        monkeypatch.delenv("GOV_TEST_PWD")
        await modulo.correr_healthcheck(agora=AGORA)
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=2))
        assert len(mundo.emails) == 1
        await modulo.correr_healthcheck(agora=AGORA + timedelta(days=8))
        assert len(mundo.emails) == 2


@pytest.mark.asyncio
class TestIntervalo:
    async def test_a_execucao_automatica_nao_repete_dentro_do_intervalo(self, ambiente):
        modulo, base, mundo = ambiente
        await modulo.correr_healthcheck(agora=AGORA)
        n = len(mundo.chamadas)
        segunda = await modulo.correr_healthcheck(agora=AGORA + timedelta(hours=2))
        assert segunda == {"saltado": "recente"} and len(mundo.chamadas) == n

    async def test_depois_do_intervalo_volta_a_correr(self, ambiente):
        modulo, base, mundo = ambiente
        await modulo.correr_healthcheck(agora=AGORA)
        n = len(mundo.chamadas)
        await modulo.correr_healthcheck(agora=AGORA + timedelta(hours=21))
        assert len(mundo.chamadas) == 2 * n

    async def test_a_execucao_forcada_ignora_o_intervalo(self, ambiente):
        modulo, base, mundo = ambiente
        await modulo.correr_healthcheck(agora=AGORA)
        n = len(mundo.chamadas)
        await modulo.correr_healthcheck(respeitar_intervalo=False, agora=AGORA + timedelta(minutes=5))
        assert len(mundo.chamadas) == 2 * n

    async def test_cada_portal_e_verificado_uma_vez_por_execucao(self, ambiente):
        modulo, base, mundo = ambiente
        mundo.resultados["financas"] = _falha("credenciais_invalidas", "check_login")
        await modulo.correr_healthcheck(agora=AGORA)
        assert [c[0] for c in mundo.chamadas] == ["financas", "seg_social"], "nunca se repete um login"


@pytest.mark.asyncio
class TestAudiencia:
    async def test_so_utilizadores_activos_com_o_papel(self, ambiente):
        modulo, base, mundo = ambiente
        from services.alert_audience import destinatarios_de_infraestrutura

        com_admins = await destinatarios_de_infraestrutura(incluir_admins=True)
        so_master = await destinatarios_de_infraestrutura(incluir_admins=False)
        assert sorted(d["id"] for d in com_admins) == ["a1", "m1"]
        assert [d["id"] for d in so_master] == ["m1"]
