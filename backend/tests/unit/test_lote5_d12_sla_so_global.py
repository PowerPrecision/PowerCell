"""
Lote 5 — D-12 FECHADA: os limiares de SLA são GLOBAIS e a API deixou de aceitar gravá-los por empresa.

O DEFEITO
  `SystemConfig` guarda por empresa, mas o leitor (`stats_sla._limiares`) chama `get_system_config()` SEM
  argumento e lê sempre a configuração `default`. `PATCH /system-config/dashboard_slas?company_id=X` gravava
  um valor que nada lê: o primeiro administrador a configurá-lo por empresa via-o ignorado, em silêncio.

A DECISÃO (dita no relatório do lote)
  Fecha-se o buraco em vez de se construir o leitor por empresa: a única superfície que existe é o ecrã
  GLOBAL, e ninguém tem limiares distintos configurados. Ficam as duas metades afirmadas — o leitor lê o
  `default`, e a escrita por empresa é recusada alto (400). Se o negócio pedir SLAs por empresa, faz-se o
  leitor e retira-se a secção de `SECCOES_SO_GLOBAIS`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import services.system_config_api as api


@pytest.mark.asyncio
class TestEscritaDosSlas:
    async def test_a_exploracao_gravar_por_empresa_e_recusado_e_nada_e_escrito(self):
        escrita = AsyncMock()
        with patch.object(api, "update_config_section", escrita):
            with pytest.raises(HTTPException) as erro:
                await api.run_update_config("dashboard_slas", {"analise": 3}, company_id="cmp-domus")
        assert erro.value.status_code == 400
        assert "global" in erro.value.detail
        escrita.assert_not_awaited()

    @pytest.mark.parametrize("global_", [None, "", "default"])
    async def test_gravar_a_configuracao_global_continua_a_funcionar(self, global_):
        escrita = AsyncMock()
        with patch.object(api, "update_config_section", escrita):
            r = await api.run_update_config("dashboard_slas", {"analise": 3}, company_id=global_)
        assert r["success"] is True
        escrita.assert_awaited_once()

    async def test_contraprova_as_outras_seccoes_continuam_a_aceitar_empresa(self):
        escrita = AsyncMock()
        with patch.object(api, "update_config_section", escrita):
            r = await api.run_update_config("system_smtp", {"x": 1}, company_id="cmp-domus")
        assert r["success"] is True

    def test_so_os_slas_estao_na_lista(self):
        assert api.SECCOES_SO_GLOBAIS == frozenset({"dashboard_slas"})
        assert api.SECCOES_SO_GLOBAIS <= api.EXTRA_SECTIONS | set(api.CONFIG_FIELDS)


@pytest.mark.asyncio
async def test_o_leitor_continua_a_ler_a_configuracao_default():
    """A outra metade: se o leitor passasse a ler outra coisa, a recusa acima deixava de ser verdadeira."""
    import services.stats_sla as sla
    from models.system_config import DashboardSlaConfig

    config = type("C", (), {"dashboard_slas": DashboardSlaConfig()})()
    leitura = AsyncMock(return_value=config)
    with patch("services.system_config.get_system_config", leitura):
        await sla._limiares()
    leitura.assert_awaited_once_with()
