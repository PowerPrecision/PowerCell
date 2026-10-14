"""Os defaults de capacidades POR CARGO, persistidos de verdade (D-27 fechada, Lote 5).

O DEFEITO
  `PUT /admin/permissions/role-defaults/{role}` alterava `ROLE_CAPABILITY_DEFAULTS` EM MEMÓRIA e
  escrevia uma cópia em `system_config` que **nada lia de volta**. A edição perdia-se no reinício e,
  com mais de um worker, só o que recebeu o pedido a conhecia.

O DESENHO — GUARDAR O DESVIO, NÃO O RETRATO
  A cópia antiga era um retrato COMPLETO da matriz (todos os cargos, todas as capacidades). Lê-la de
  volta teria sido o erro caro: o retrato congela também os defaults do CÓDIGO no dia em que foi
  tirado, e um deploy que mude um default passava a ser desfeito em silêncio pelo retrato. Por isso
  o documento novo guarda só os **overrides** (o que o administrador mudou em relação ao código):

      {key: "role_capability_defaults_v2", overrides: {cargo: {CAPACIDADE: bool}}}

  e a matriz em vigor é sempre `código + overrides`. Uma capacidade nova do código, ou um default
  corrigido num deploy, chega a toda a gente excepto aos cargos onde o administrador a decidiu à mão.

O DOCUMENTO ANTIGO NÃO SE APLICA
  Não se distingue, num retrato, a edição de um administrador de um default que o código tinha na
  altura. Aplicá-lo revivia edições de que ninguém se lembra. O que se faz é MOSTRÁ-LO
  (`diferencas_do_legado`: no log do arranque e no registo de capacidades do ecrã) para o
  administrador voltar a fazer, pelo ecrã, as que ainda quer. Depois de rever, apaga-se o documento
  (`{key: "role_capability_defaults"}` em `system_config`).

CONVERGÊNCIA ENTRE WORKERS
  O `get_current_user` chama `refrescar()` — cache de 30 s por worker, a mesma de
  `history_tracking`. Uma escrita refresca o worker que a recebeu; os outros apanham-na no máximo
  30 s depois. Falhar a ler NUNCA derruba o pedido nem repõe os defaults do código: mantém-se o que
  está em memória (com aviso).
"""
from __future__ import annotations

import copy
import logging
import time
from typing import Any, Optional

from database import db
from models.permissions import (
    CAPABILITIES,
    ROLE_CAPABILITY_DEFAULTS,
    SUPER_ADMIN_ROLES,
)

logger = logging.getLogger(__name__)

COLECCAO = "system_config"
CHAVE = "role_capability_defaults_v2"
CHAVE_LEGADA = "role_capability_defaults"
TTL_SEGUNDOS = 30

#: Os defaults do CÓDIGO, fixados no import — antes de qualquer edição em memória. Tudo o que o
#: administrador muda mede-se contra isto.
DEFAULTS_DO_CODIGO: dict[str, dict[str, bool]] = copy.deepcopy(ROLE_CAPABILITY_DEFAULTS)

_cache: dict[str, Any] = {"em": 0.0}


def _cargo_editavel(cargo: Any) -> bool:
    """Só cargos que existem e que o bypass de super-admin não torna irrelevantes."""
    return cargo in DEFAULTS_DO_CODIGO and cargo not in SUPER_ADMIN_ROLES


def limpar_overrides(bruto: Any) -> dict[str, dict[str, bool]]:
    """Só o que é válido: cargo conhecido e editável, capacidade conhecida, valor booleano. PURA.

    Lixo na base de dados nunca vira permissão: um valor que não seja `bool` é descartado (nada de
    `"false"` a contar como verdadeiro), e uma capacidade desconhecida não é inventada.
    """
    if not isinstance(bruto, dict):
        return {}
    limpo: dict[str, dict[str, bool]] = {}
    for cargo, caps in bruto.items():
        if not _cargo_editavel(cargo) or not isinstance(caps, dict):
            continue
        validas = {c: v for c, v in caps.items() if c in CAPABILITIES and isinstance(v, bool)}
        if validas:
            limpo[cargo] = validas
    return limpo


def overrides_em_memoria() -> dict[str, dict[str, bool]]:
    """O que a matriz em memória tem de DIFERENTE do código. PURA (lê só os dicionários)."""
    saida: dict[str, dict[str, bool]] = {}
    for cargo, base in DEFAULTS_DO_CODIGO.items():
        if not _cargo_editavel(cargo):
            continue
        actual = ROLE_CAPABILITY_DEFAULTS.get(cargo, {})
        desvios = {c: v for c, v in actual.items() if base.get(c) != v}
        if desvios:
            saida[cargo] = desvios
    return saida


def aplicar(overrides: dict[str, dict[str, bool]]) -> None:
    """Põe a matriz em memória em `código + overrides` — IN PLACE.

    In place porque 15 módulos fazem `from models.permissions import ROLE_CAPABILITY_DEFAULTS` e
    guardam a referência: substituir o dicionário deixava-os a ler o antigo. Repõe primeiro o código
    (um override que desapareceu da base de dados tem de desaparecer da memória).
    """
    for cargo in DEFAULTS_DO_CODIGO:
        if not _cargo_editavel(cargo):
            continue
        ROLE_CAPABILITY_DEFAULTS[cargo].clear()
        ROLE_CAPABILITY_DEFAULTS[cargo].update(DEFAULTS_DO_CODIGO[cargo])
    for cargo, caps in limpar_overrides(overrides).items():
        ROLE_CAPABILITY_DEFAULTS[cargo].update(caps)


async def _ler_overrides_da_base() -> dict[str, dict[str, bool]]:
    doc = await db[COLECCAO].find_one({"key": CHAVE}, {"_id": 0, "overrides": 1}) or {}
    return limpar_overrides(doc.get("overrides"))


async def refrescar(*, forcar: bool = False) -> bool:
    """Sincroniza a memória deste worker com a base de dados. Nunca levanta.

    Devolve ``True`` se leu. Com a cache fresca (<30 s) e sem ``forcar`` não faz nada.
    """
    agora = time.monotonic()
    if not forcar and agora - _cache["em"] < TTL_SEGUNDOS:
        return False
    try:
        overrides = await _ler_overrides_da_base()
    except Exception as exc:  # noqa: BLE001 — a autenticação não pode cair por causa disto
        logger.warning(
            "[PERMISSÕES] Falha a ler os defaults por cargo (%s): mantém-se o que está em memória.", exc,
        )
        # Também a falha respeita o intervalo: sem isto, uma base de dados em baixo fazia CADA pedido
        # autenticado esperar pelo timeout do driver.
        _cache["em"] = agora
        return False
    aplicar(overrides)
    _cache["em"] = agora
    return True


def invalidar_cache() -> None:
    _cache["em"] = 0.0


async def guardar_overrides_actuais(actor: Optional[dict] = None) -> dict[str, dict[str, bool]]:
    """Persiste os desvios da matriz em memória em relação ao código (substitui o documento)."""
    overrides = overrides_em_memoria()
    await db[COLECCAO].update_one(
        {"key": CHAVE},
        {"$set": {
            "key": CHAVE,
            "overrides": overrides,
            "updated_by": (actor or {}).get("id"),
        }},
        upsert=True,
    )
    _cache["em"] = time.monotonic()
    return overrides


async def diferencas_do_legado() -> list[dict]:
    """O que o retrato antigo diz de DIFERENTE do código — para REVER, nunca para aplicar. Nunca levanta."""
    try:
        doc = await db[COLECCAO].find_one({"key": CHAVE_LEGADA}, {"_id": 0, "value": 1}) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PERMISSÕES] Não foi possível ler o retrato legado dos defaults: %s", exc)
        return []
    retrato = doc.get("value")
    if not isinstance(retrato, dict):
        return []
    diferencas = []
    for cargo, caps in sorted(retrato.items()):
        if not _cargo_editavel(cargo) or not isinstance(caps, dict):
            continue
        for capacidade, valor in sorted(caps.items()):
            if capacidade in CAPABILITIES and isinstance(valor, bool) \
                    and DEFAULTS_DO_CODIGO[cargo].get(capacidade) != valor:
                diferencas.append({
                    "cargo": cargo, "capacidade": capacidade,
                    "retrato_antigo": valor, "codigo": DEFAULTS_DO_CODIGO[cargo].get(capacidade),
                })
    return diferencas


async def arrancar() -> None:
    """Chamada no arranque: carrega os overrides e avisa se há um retrato antigo por rever."""
    await refrescar(forcar=True)
    diferencas = await diferencas_do_legado()
    if diferencas:
        logger.warning(
            "[PERMISSÕES] Existe um retrato ANTIGO dos defaults por cargo (system_config key=%s) com "
            "%d diferença(s) em relação ao código — NÃO é aplicado. Reveja-as no ecrã de permissões "
            "(registo de capacidades) e apague o documento. Primeiras: %s",
            CHAVE_LEGADA, len(diferencas), diferencas[:5],
        )


__all__ = [
    "CHAVE", "CHAVE_LEGADA", "DEFAULTS_DO_CODIGO", "aplicar", "arrancar", "diferencas_do_legado",
    "guardar_overrides_actuais", "invalidar_cache", "limpar_overrides", "overrides_em_memoria", "refrescar",
]
