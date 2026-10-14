"""
Lote 4, ponto 8 (Out 2026) — a Domus não aparecia como destino no Portal do Parceiro.

A CAUSA
  O destino é «empresa de uma rede COM Index», e o Index é derivado da equipa (pelo menos um
  utilizador `indexacao` activo). A Domus é uma rede satélite SEM indexadores: desaparecia da lista
  sem aviso e sem nada que o Master pudesse ligar (a antiga flag `is_hub` foi retirada).

A REGRA
  `companies.aceita_parceiros` é um tri-estado, só o Master o define:
    true → sempre destino · false → nunca · null/ausente → automático (só com Index).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE

PARCEIRO = {"id": "par-1", "redes": []}


@pytest.fixture
def mundo(fake_async_db):
    import services.partner_leads as mod

    fake_async_db.companies.docs.extend([
        {"id": "cmp-power", "name": "Power Real Estate", "network_id": REDE_INCUMBENTE},
        {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS},
        {"id": "cmp-fechada", "name": "Fechada", "network_id": "rede_f", "is_active": False},
    ])
    # SÓ a rede incumbente tem Index.
    with patch.object(mod, "db", fake_async_db), \
         patch("services.network_triage.redes_com_index", AsyncMock(return_value={REDE_INCUMBENTE})):
        yield fake_async_db, mod


def _nomes(destinos):
    return {d["company_name"] for d in destinos}


@pytest.mark.asyncio
class TestOTriEstadoAceitaParceiros:
    async def test_a_exploracao_sem_a_flag_a_domus_continua_fora(self, mundo):
        bd, mod = mundo
        assert _nomes(await mod.destinos_do_parceiro(PARCEIRO)) == {"Power Real Estate"}

    async def test_a_flag_true_abre_a_domus_mesmo_sem_index(self, mundo):
        bd, mod = mundo
        next(c for c in bd.companies.docs if c["id"] == "cmp-domus")["aceita_parceiros"] = True
        assert _nomes(await mod.destinos_do_parceiro(PARCEIRO)) == {"Power Real Estate", "Domus"}

    async def test_a_flag_false_esconde_uma_empresa_com_index(self, mundo):
        bd, mod = mundo
        next(c for c in bd.companies.docs if c["id"] == "cmp-power")["aceita_parceiros"] = False
        assert _nomes(await mod.destinos_do_parceiro(PARCEIRO)) == set()

    async def test_null_e_automatico(self, mundo):
        bd, mod = mundo
        for c in bd.companies.docs:
            c["aceita_parceiros"] = None
        assert _nomes(await mod.destinos_do_parceiro(PARCEIRO)) == {"Power Real Estate"}

    async def test_uma_empresa_inactiva_nunca_e_destino_nem_com_a_flag(self, mundo):
        bd, mod = mundo
        next(c for c in bd.companies.docs if c["id"] == "cmp-fechada")["aceita_parceiros"] = True
        assert "Fechada" not in _nomes(await mod.destinos_do_parceiro(PARCEIRO))

    async def test_sem_nenhuma_rede_com_index_a_flag_continua_a_funcionar(self, mundo):
        """O `if not com_index: return []` antigo escondia a Domus mesmo com a flag ligada."""
        bd, mod = mundo
        next(c for c in bd.companies.docs if c["id"] == "cmp-domus")["aceita_parceiros"] = True
        with patch("services.network_triage.redes_com_index", AsyncMock(return_value=set())):
            assert _nomes(await mod.destinos_do_parceiro(PARCEIRO)) == {"Domus"}

    async def test_a_ligacao_suspensa_continua_a_esconder_o_destino(self, mundo):
        bd, mod = mundo
        next(c for c in bd.companies.docs if c["id"] == "cmp-domus")["aceita_parceiros"] = True
        parceiro = {"id": "par-1", "redes": [{"network_id": REDE_DOMUS, "status": "suspenso"}]}
        assert "Domus" not in _nomes(await mod.destinos_do_parceiro(parceiro))

    async def test_resolver_destino_aceita_a_empresa_aberta_pela_flag(self, mundo):
        bd, mod = mundo
        next(c for c in bd.companies.docs if c["id"] == "cmp-domus")["aceita_parceiros"] = True
        with patch.object(mod, "acrescentar_ligacao_de_mercado", AsyncMock()):
            ligacao = await mod.resolver_destino(dict(PARCEIRO), "cmp-domus")
        assert ligacao["network_id"] == REDE_DOMUS

    async def test_resolver_destino_recusa_a_empresa_sem_flag_e_sem_index(self, mundo):
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.resolver_destino(dict(PARCEIRO), "cmp-domus")
        assert erro.value.status_code == 404

    async def test_o_network_id_nunca_sai_para_o_parceiro(self, mundo):
        bd, mod = mundo
        next(c for c in bd.companies.docs if c["id"] == "cmp-domus")["aceita_parceiros"] = True
        for destino in await mod.destinos_do_parceiro(PARCEIRO):
            assert set(destino) == {"company_id", "company_name"}


class TestSoOMasterDefineAFlag:
    def test_o_servico_recusa_a_quem_nao_e_global(self):
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "services" / "companies_crud_api_mutate.py").read_text(encoding="utf-8")
        assert '"aceita_parceiros" in data.model_fields_set and not utilizador_e_global(actor)' in fonte

    @pytest.mark.asyncio
    async def test_um_admin_local_recebe_403_e_nada_e_escrito(self, fake_async_db):
        import services.companies_crud_api_mutate as mod
        from models.company import CompanyUpdate

        fake_async_db.companies.docs.append({"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS})
        admin = {"id": "u-adm", "role": "admin", "effective_role": "admin"}
        with patch.object(mod, "db", fake_async_db), \
             patch.object(mod, "exigir_empresas_concediveis", AsyncMock()):
            with pytest.raises(HTTPException) as erro:
                await mod.run_update_company("cmp-domus", CompanyUpdate(aceita_parceiros=True), actor=admin)
        assert erro.value.status_code == 403
        assert "aceita_parceiros" not in fake_async_db.companies.docs[0]

    @pytest.mark.asyncio
    async def test_null_explicito_tambem_conta_como_definir(self, fake_async_db):
        """`model_fields_set` apanha o `null` (voltar ao automático); `is not None` deixava passar."""
        import services.companies_crud_api_mutate as mod
        from models.company import CompanyUpdate

        fake_async_db.companies.docs.append({"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS})
        admin = {"id": "u-adm", "role": "admin", "effective_role": "admin"}
        with patch.object(mod, "db", fake_async_db), \
             patch.object(mod, "exigir_empresas_concediveis", AsyncMock()):
            with pytest.raises(HTTPException) as erro:
                await mod.run_update_company("cmp-domus", CompanyUpdate(aceita_parceiros=None), actor=admin)
        assert erro.value.status_code == 403
