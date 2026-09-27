"""
Cadência do IMAP em alojamento partilhado (Lote 5, fecho do ponto 7).

O SINTOMA
  `Erro IMAP constante` no servidor de produção com credenciais
  CONFIRMADAS pelo dono. Um `535`/desligar a meio com a password certa,
  repetido, não é autenticação: é rate limit / bloqueio de IP por
  excesso de ligações — o alojamento partilhado corta.

  O laço do processo web (`run_email_auto_sync`) ligava-se de 60 em 60
  segundos POR CAIXA CONFIGURADA, com um jitter de 15s no máximo. Com N
  caixas e `UVICORN_WORKERS` a arrancar ao mesmo tempo, são N ligações
  IMAP por minuto à mesma máquina, sempre no mesmo instante.

O MONITOR NÃO PODE MENTIR AO MESMO TEMPO
  `estado_do_job` lia o intervalo de `JOBS_DECLARADOS` — uma CONSTANTE.
  Abrandar o laço sem mexer na constante punha o Monitor de Sinais
  Vitais (ponto 14) a declarar `atrasado` um job que está a cumprir o
  seu horário novo: limiar de 2x60s contra ciclos de 5 minutos. O
  batimento JÁ grava o `interval_seconds` que o laço usou de facto — é
  essa a verdade do processo que correu; o declarado é só a expectativa
  de quem nunca bateu.
"""
from datetime import datetime, timedelta, timezone


AGORA = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def _iso(momento):
    return momento.isoformat()


class TestCadenciaDoAutoSync:
    def test_a_omissao_deixou_de_ser_um_minuto(self, monkeypatch):
        from services.scheduled_tasks import get_email_auto_sync_interval_seconds

        monkeypatch.delenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", raising=False)
        assert get_email_auto_sync_interval_seconds() >= 300

    def test_nao_se_pode_voltar_a_martelar_o_servidor(self, monkeypatch):
        """O clamp é a protecção: uma variável de ambiente mal posta não
        pode reabrir o bloqueio de IP que este ponto veio fechar."""
        from services.scheduled_tasks import get_email_auto_sync_interval_seconds

        monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "10")
        assert get_email_auto_sync_interval_seconds() >= 120

    def test_continua_a_permitir_afinar_para_cima(self, monkeypatch):
        from services.scheduled_tasks import get_email_auto_sync_interval_seconds

        monkeypatch.setenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "900")
        assert get_email_auto_sync_interval_seconds() == 900

    def test_o_jitter_espalha_mesmo_os_arranques(self):
        """Um jitter de 15s num ciclo de 5 minutos é 5% — dois workers que
        arranquem juntos continuam a bater ao mesmo tempo."""
        from services.scheduled_tasks import jitter_do_auto_sync

        amostras = {jitter_do_auto_sync(300) for _ in range(200)}
        assert max(amostras) >= 45
        assert min(amostras) >= 0
        assert max(amostras) <= 300


class TestOMonitorSegueOLacoReal:
    def test_o_intervalo_do_batimento_vence_a_constante(self):
        """O laço correu a 300s e bateu há 200s: está a cumprir."""
        from services.job_heartbeat import estado_do_job

        declarado = {"chave": "email_auto_sync", "interval_seconds": 60, "processo": "web"}
        registo = {
            "finished_at": _iso(AGORA - timedelta(seconds=200)),
            "status": "ok",
            "interval_seconds": 300,
        }
        assert estado_do_job(declarado, registo, agora=AGORA) == "saudavel"

    def test_um_laco_lento_que_pare_mesmo_continua_a_dar_atraso(self):
        """Contraprova: honrar o intervalo do batimento não pode passar a
        desculpar tudo."""
        from services.job_heartbeat import estado_do_job

        declarado = {"chave": "email_auto_sync", "interval_seconds": 60, "processo": "web"}
        registo = {
            "finished_at": _iso(AGORA - timedelta(seconds=1200)),
            "status": "ok",
            "interval_seconds": 300,
        }
        assert estado_do_job(declarado, registo, agora=AGORA) == "atrasado"

    def test_a_proxima_execucao_usa_o_intervalo_real(self):
        from services.job_heartbeat import proxima_execucao

        declarado = {"chave": "email_auto_sync", "interval_seconds": 60, "processo": "web"}
        fim = AGORA - timedelta(seconds=100)
        registo = {"finished_at": _iso(fim), "status": "ok", "interval_seconds": 300}
        assert proxima_execucao(declarado, registo) == (fim + timedelta(seconds=300)).isoformat()

    def test_sem_batimento_o_declarado_ainda_manda(self):
        """Contraprova: um job que nunca bateu não tem intervalo real."""
        from services.job_heartbeat import estado_do_job

        declarado = {"chave": "scheduled_tasks", "interval_seconds": 3600, "processo": "worker"}
        registo = {"finished_at": _iso(AGORA - timedelta(seconds=100)), "status": "ok"}
        assert estado_do_job(declarado, registo, agora=AGORA) == "saudavel"


class TestODeclaradoAcompanhaOLaco:
    def test_o_painel_anuncia_a_cadencia_nova(self):
        """`JOBS_DECLARADOS` é o que o painel mostra a um job que ainda não
        bateu — anunciar 60s seria prometer o que o laço já não faz."""
        from services.job_heartbeat import JOBS_DECLARADOS
        from services.scheduled_tasks import get_email_auto_sync_interval_seconds

        declarado = next(j for j in JOBS_DECLARADOS if j["chave"] == "email_auto_sync")
        assert declarado["interval_seconds"] == get_email_auto_sync_interval_seconds()
