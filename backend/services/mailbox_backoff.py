"""Recuo da sincronização de uma caixa cuja password foi recusada (Bloco 5, ponto 34).

O PROBLEMA
==========
`webmail_worker_sync`, o auto-sync do `scheduled_tasks` e o sync global do
`email_service` percorrem todas as contas configuradas **de 10 em 10 minutos** e
fazem login IMAP em cada uma. Se a password de uma conta deixou de servir — foi
mudada no webmail, expirou, ou foi gravada mal —, cada ciclo é mais uma tentativa
falhada, para sempre: 6 por hora, 144 por dia, por conta.

Servidores de email (cPanel/cPHulk, Dovecot, Exim) respondem a isto de uma forma
previsível: passam a **recusar ou atrasar a conta/IP**, e a recusa aparece como
`535 Incorrect authentication data` — **também no SMTP, também com a password
certa**. É exactamente o erro que o consultor vê ao enviar documentação para um
balcão: a conta que o ENVIO usa foi bloqueada pelos logins falhados do SINCRONIZADOR.

Este módulo é o travão: depois de duas falhas de autenticação consecutivas a conta
deixa de ser tentada pelos ciclos automáticos, com intervalos crescentes (1 h → 6 h →
24 h), e **volta a ser tentada de imediato quando a configuração muda** (nova
password gravada depois da última tentativa).

QUATRO DECISÕES
===============
1. **Só a autenticação recua.** Rede e limite de tráfego passam sozinhos e a conta
   tem de continuar a ser tentada; uma password errada não se resolve a tentar.
2. **Uma falha isolada não recua** — pode ser um soluço do servidor.
3. **A configuração nova vence o recuo.** Sem isto, corrigir a password deixava a
   caixa parada até ao fim do intervalo, e o utilizador concluía que a correcção
   não funcionou.
4. **Nunca esgota a conta**: o teto é 24 h, não «para sempre». Uma caixa recuperada
   pelo administrador no servidor (sem mexer no CRM) volta sozinha.

Puro e sem I/O: recebe o documento da config e o «agora».
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.mailbox_health import CLASSE_AUTENTICACAO

#: Espera entre tentativas, pelo número de falhas: 2 → 1 h, 3 → 6 h, 4+ → 24 h.
#: É a ÚNICA definição do limiar — com menos de 2 falhas a espera é zero, ou
#: seja, uma falha isolada nunca recua (pode ser um soluço do servidor).
ESPERA_POR_FALHAS = ((2, timedelta(hours=1)), (3, timedelta(hours=6)), (4, timedelta(hours=24)))


def _data(valor: Any) -> Optional[datetime]:
    """Interpreta um ISO 8601 (com ou sem fuso); `None` se ilegível."""
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        analisado = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return analisado if analisado.tzinfo else analisado.replace(tzinfo=timezone.utc)


def espera_para(falhas: int) -> timedelta:
    """O intervalo mínimo entre tentativas, para este número de falhas."""
    espera = timedelta(0)
    for limiar, intervalo in ESPERA_POR_FALHAS:
        if falhas >= limiar:
            espera = intervalo
    return espera


def deve_esperar(config: dict, agora: Optional[datetime] = None) -> bool:
    """True se esta caixa NÃO deve ser tentada neste ciclo.

    `config` é o documento de `user_email_configs` (ou a sua projecção com os
    campos de saúde). Falha ABERTA: dados em falta ou ilegíveis nunca param uma
    sincronização — pior do que tentar de mais é uma caixa parada sem aviso.
    """
    if (config or {}).get("sync_error_class") != CLASSE_AUTENTICACAO:
        return False
    try:
        falhas = int(config.get("sync_failures") or 0)
    except (TypeError, ValueError):
        return False

    ultima = _data(config.get("last_sync_attempt_at"))
    if ultima is None:
        return False

    alterada = _data(config.get("updated_at"))
    if alterada is not None and alterada > ultima:
        return False  # a configuração mudou depois da última falha: tentar já

    agora = agora or datetime.now(timezone.utc)
    return (agora - ultima) < espera_para(falhas)
