"""Data de expiração dos registos ANTIGOS de `portal_verify_attempts` e `portal_login_attempts` (D-31).

Os registos novos nascem com `expire_at` (ver `portal_security._record_failed_attempt`);
os que já existiam não o têm e o índice TTL ignora-os para sempre. Esta função
PURA diz que data lhes dar, e é a que o `scripts/backfill_portal_attempts_ttl.py`
usa. Duas regras:

* parte da última tentativa (`last_attempt_at`), não de «agora» — dar-lhes mais
  30 minutos de vida a partir do deploy faria um ataque de há um mês parecer
  recente; sem data legível, parte de agora;
* **nunca antes do fim de um bloqueio ainda em curso** (`locked_until` + 1 min):
  o backfill não pode desbloquear quem está, neste instante, legitimamente
  bloqueado.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.portal_brute_force import expira_em

#: As duas colecções de tentativas do Portal. O backfill percorre as DUAS.
COLECCOES_DE_TENTATIVAS = ("portal_verify_attempts", "portal_login_attempts")


def _para_data(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        lido = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)


def expire_at_do_registo(doc: dict, *, agora: datetime) -> datetime:
    """A data de expiração a gravar num registo que ainda não a tem."""
    ultima = _para_data((doc or {}).get("last_attempt_at")) or agora
    alvo = expira_em(ultima)
    bloqueado_ate = _para_data((doc or {}).get("locked_until"))
    if bloqueado_ate is not None:
        alvo = max(alvo, bloqueado_ate + timedelta(minutes=1))
    return alvo
