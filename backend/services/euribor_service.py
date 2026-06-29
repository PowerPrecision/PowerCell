"""
Serviço de Taxas Euribor — cache diário com fallback gracioso.

Busca as taxas Euribor reais (1M, 3M, 6M, 12M) junto de uma API externa
pública e guarda-as em cache durante 24h para não exceder limites de taxa.

ARQUITECTURA:
- Cache em memória (módulo-level) com TTL de 24h.
- Se a API externa falhar, devolve os últimos valores conhecidos (se houver).
- Se não houver valores em cache, devolve valores de fallback hardcoded
  (taxas aproximadas, claramente identificadas como estimativas).

FONTE DE DADOS:
- API primária: https://www.euribor-rates.eu/api/ (JSON público, sem auth)
- Fallback: valores hardcoded atualizados manualmente

ENDPOINT: GET /api/public/euribor
"""
import os
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# ====================================================================
# CONFIGURAÇÃO
# ====================================================================
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 horas
REQUEST_TIMEOUT_SECONDS = 8
EURIBOR_API_URL = os.environ.get(
    "EURIBOR_API_URL",
    "https://www.euribor-rates.eu/api/current_rates.json"
)

# Valores de fallback (estimativas — atualizar periodicamente)
# Usados apenas se a API externa estiver indisponível E não houver cache.
FALLBACK_RATES = {
    "1m": 3.65,
    "3m": 3.60,
    "6m": 3.55,
    "12m": 3.50,
}

# ====================================================================
# CACHE EM MEMÓRIA (módulo-level, partilhado entre workers do mesmo processo)
# ====================================================================
_cache: Dict[str, Any] = {
    "data": None,        # dict com as taxas
    "fetched_at": 0,     # timestamp Unix
    "is_fallback": True, # True se os valores são estimativas
}

# Lock para evitar múltiplas buscas concorrentes à API externa
_fetch_lock = asyncio.Lock()


async def _fetch_euribor_from_api() -> Optional[Dict[str, Any]]:
    """
    Busca as taxas Euribor reais junto da API externa.

    Returns:
        Dict com {euribor_1m, euribor_3m, euribor_6m, euribor_12m, fetched_at}
        ou None se a API falhar.
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.get(EURIBOR_API_URL)
            if resp.status_code != 200:
                logger.warning(f"[EURIBOR] API externa devolveu status {resp.status_code}")
                return None

            data = resp.json()

        # A API euribor-rates.eu devolve um dict com chaves por maturidade.
        # Tentar vários formatos possíveis para robustez.
        rates = {}

        # Formato esperado: {"1m": {"rate": 3.65}, "3m": {...}, ...}
        # ou: {"1m": 3.65, "3m": 3.60, ...}
        # ou: {"current_rates": {"1m": 3.65, ...}}
        source = data.get("current_rates", data) if isinstance(data, dict) else {}

        for period in ("1m", "3m", "6m", "12m"):
            val = source.get(period)
            if isinstance(val, dict):
                val = val.get("rate") or val.get("value")
            if val is not None:
                try:
                    rates[f"euribor_{period}"] = float(val)
                except (ValueError, TypeError):
                    continue

        # Validar que obtivemos pelo menos a Euribor 12M (a mais usada)
        if "euribor_12m" not in rates:
            logger.warning(f"[EURIBOR] API não devolveu euribor_12m: {data}")
            return None

        rates["fetched_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[EURIBOR] Taxas obtidas da API: {rates}")
        return rates

    except httpx.TimeoutException:
        logger.warning(f"[EURIBOR] Timeout ao contactar API externa ({REQUEST_TIMEOUT_SECONDS}s)")
        return None
    except Exception as e:
        logger.warning(f"[EURIBOR] Erro ao contactar API externa: {type(e).__name__}: {e}")
        return None


async def get_euribor_rates() -> Dict[str, Any]:
    """
    Obtém as taxas Euribor, usando cache quando possível.

    Lógica:
    1. Se o cache tem < 24h, devolver cache.
    2. Caso contrário, buscar à API externa (com lock anti-concorrência).
    3. Se a API falhar, devolver o cache antigo (mesmo que expirado).
    4. Se não houver cache nem API, devolver valores de fallback.

    Returns:
        Dict com:
        - euribor_1m, euribor_3m, euribor_6m, euribor_12m (float, em %)
        - fetched_at (ISO timestamp)
        - is_fallback (bool): True se valores são estimativas
        - source (str): "cache" | "api" | "fallback"
    """
    now = time.time()
    cache_age = now - _cache["fetched_at"]

    # 1. Cache fresco — devolver de imediato
    if _cache["data"] is not None and cache_age < CACHE_TTL_SECONDS:
        result = {**_cache["data"], "is_fallback": _cache["is_fallback"], "source": "cache"}
        return result

    # 2. Cache expirado — buscar à API (com lock)
    async with _fetch_lock:
        # Dupla verificação: outro worker pode ter atualizado o cache enquanto
        # esperávamos o lock
        now = time.time()
        cache_age = now - _cache["fetched_at"]
        if _cache["data"] is not None and cache_age < CACHE_TTL_SECONDS:
            result = {**_cache["data"], "is_fallback": _cache["is_fallback"], "source": "cache"}
            return result

        fresh = await _fetch_euribor_from_api()

        if fresh:
            # Atualizar cache
            _cache["data"] = fresh
            _cache["fetched_at"] = now
            _cache["is_fallback"] = False
            return {**fresh, "is_fallback": False, "source": "api"}

        # 3. API falhou — usar cache antigo se existir
        if _cache["data"] is not None:
            logger.info("[EURIBOR] API indisponível — a usar cache antigo")
            return {**_cache["data"], "is_fallback": True, "source": "cache_stale"}

    # 4. Sem cache nem API — valores de fallback
    fallback = {
        "euribor_1m": FALLBACK_RATES["1m"],
        "euribor_3m": FALLBACK_RATES["3m"],
        "euribor_6m": FALLBACK_RATES["6m"],
        "euribor_12m": FALLBACK_RATES["12m"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"[EURIBOR] Sem cache nem API — a usar valores de fallback: {fallback}")
    return {**fallback, "is_fallback": True, "source": "fallback"}
