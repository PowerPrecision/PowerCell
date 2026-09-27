"""
Cadência do auto-sync de IMAP — ponto ÚNICO (Lote 5, fecho do ponto 7).

PORQUE É QUE ISTO VIVE NUM MÓDULO SÓ SEU
  Dois sítios precisam do mesmo número e não se podem importar um ao
  outro: o laço que dorme (`services/scheduled_tasks.run_email_auto_sync`,
  módulo pesado) e o Monitor de Sinais Vitais
  (`services/job_heartbeat.JOBS_DECLARADOS`, importado no arranque do
  `server.py` e do `worker.py`). Pôr o `scheduled_tasks` dentro do
  `job_heartbeat` arrastaria a máquina toda de e-mail para o arranque de
  ambos os processos.

PORQUE É QUE A CADÊNCIA SUBIU DE 60s PARA 5 MINUTOS
  O sintoma era `Erro IMAP constante` em produção com credenciais
  CONFIRMADAS pelo dono. Uma password certa que falha repetidamente não
  é autenticação: é rate limit / bloqueio de IP. O laço ligava-se de 60
  em 60 segundos A CADA CAIXA CONFIGURADA e o jitter chegava aos 15s —
  5% de um ciclo, o que não chega para desencontrar dois workers que
  arranquem juntos. Em alojamento partilhado isso é tratado como abuso.

O CHÃO DO CLAMP É A PROTECÇÃO
  `EMAIL_AUTO_SYNC_INTERVAL_SECONDS` continua a afinar o valor, mas já
  não pode descer abaixo de 2 minutos: uma variável mal posta reabriria
  o bloqueio que este ponto veio fechar.
"""
import os
import random

# 5 minutos entre ciclos. O correio novo continua a chegar em tempo real
# pelo WebSocket quando o utilizador está na página (Épico 5); este laço
# é a rede que apanha o que o `new_email` não apanhou.
DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 120
MAX_INTERVAL_SECONDS = 1800

_ENV_VAR = "EMAIL_AUTO_SYNC_INTERVAL_SECONDS"


def get_email_auto_sync_interval_seconds(
    default: int = DEFAULT_INTERVAL_SECONDS,
) -> int:
    """Intervalo entre ciclos de auto-sync IMAP, em segundos.

    Lido a CADA chamada (não fixado no arranque) para que afinar a
    variável no Render não obrigue a um deploy. Valor inválido cai na
    omissão — nunca em zero, que seria um laço sem pausa.
    """
    raw = os.environ.get(_ENV_VAR, str(default))
    try:
        valor = int(raw)
    except (TypeError, ValueError):
        valor = default
    return max(MIN_INTERVAL_SECONDS, min(valor, MAX_INTERVAL_SECONDS))


def jitter_do_auto_sync(interval_seconds: int) -> int:
    """Desvio aleatório a somar ao intervalo, até 1/4 do ciclo.

    Proporcional ao intervalo, e não um tecto fixo de 15s: é o que
    desencontra de facto os workers que arrancam ao mesmo tempo e as
    várias caixas configuradas.
    """
    tecto = max(1, int(interval_seconds) // 4)
    return random.randint(0, tecto)
