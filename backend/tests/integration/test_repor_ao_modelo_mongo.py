"""«Repor ao Modelo» contra um MongoDB REAL.

O que o duplo em memória NÃO prova: o `distinct` com a condição de rede composta
(`$or` + `$in: [None, ""]`), o `delete_many` por rede e o travão por utilizador
com o `upsert` + `$inc` + `$setOnInsert` reais.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from services.auth import hash_password
from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, tenant_db

SENHA = "Segredo-Certo-9!"
ADMIN = {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "Admin", "email": "a@p.pt"}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    base = cliente[f"test_repor_modelo_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    await base.user_company_roles.insert_one(
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin", "is_default": True}
    )
    await base.users.insert_one({"id": "u-admin", "email": "a@p.pt", "password": hash_password(SENHA), "is_active": True})
    await base.workflow_statuses.insert_many([
        {"id": "m1", "name": "novo", "order": 1},
        {"id": "p1", "name": "novo", "order": 1, "network_id": REDE_INCUMBENTE},
        {"id": "p2", "name": "fase_custom", "order": 2, "network_id": REDE_INCUMBENTE},
        {"id": "d1", "name": "triagem", "order": 1, "network_id": REDE_DOMUS},
    ])
    await base.form_config.insert_many([
        {"type": "public_form", "fields": []},
        {"type": "public_form", "network_id": REDE_INCUMBENTE, "fields": []},
        {"type": "public_form", "network_id": REDE_DOMUS, "fields": []},
    ])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


@pytest.fixture
def cadeia(bd):
    import services.admin_helpers as helpers
    import services.form_config_scope as fcs
    import services.reauth_password as reauth
    import services.repor_ao_modelo as repor
    import services.workflow_scope as ws

    with tenant_db(bd, ws, helpers, reauth, repor, fcs), \
            patch("services.auth.get_active_company_id_async", AsyncMock(return_value="cmp-power")):
        yield bd, repor


def _pedido():
    return MagicMock(headers={"X-Company-Id": "cmp-power"}, state=MagicMock(spec=[]))


async def _nomes(bd, rede):
    filtro = {"network_id": rede} if rede else {"network_id": {"$in": [None, ""]}}
    return sorted([d["name"] async for d in bd.workflow_statuses.find(filtro, {"_id": 0, "name": 1})])


class TestWorkflowReal:
    @pytest.mark.asyncio
    async def test_apaga_so_a_copia_da_rede(self, cadeia):
        bd, repor = cadeia
        r = await repor.run_repor_workflow_ao_modelo(repor.ReporAoModeloIn(password=SENHA), ADMIN, _pedido())
        assert r["reposto"] is True and r["fases_removidas"] == 2
        assert await _nomes(bd, REDE_INCUMBENTE) == []
        assert await _nomes(bd, None) == ["novo"]
        assert await _nomes(bd, REDE_DOMUS) == ["triagem"]

    @pytest.mark.asyncio
    async def test_a_fase_em_uso_so_conta_na_rede_certa(self, cadeia):
        bd, repor = cadeia
        await bd.processes.insert_many([
            {"id": "x1", "status": "fase_custom", "network_id": REDE_DOMUS, "company_id": "cmp-domus"},
            {"id": "x2", "status": "fase_custom", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
            {"id": "x3", "status": "fase_custom"},  # por carimbar: pertence à rede de omissão
        ])
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(repor.ReporAoModeloIn(password=SENHA), ADMIN, _pedido())
        assert erro.value.status_code == 409
        assert erro.value.detail["fases_em_uso"] == [{"name": "fase_custom", "total": 2}]
        assert await _nomes(bd, REDE_INCUMBENTE) == ["fase_custom", "novo"]

    @pytest.mark.asyncio
    async def test_o_travao_por_utilizador_com_upsert_real(self, cadeia):
        from services.portal_brute_force import MAX_TENTATIVAS

        bd, repor = cadeia
        for _ in range(MAX_TENTATIVAS):
            with pytest.raises(HTTPException) as erro:
                await repor.run_repor_workflow_ao_modelo(repor.ReporAoModeloIn(password="errada"), ADMIN, _pedido())
            assert erro.value.status_code == 403
        with pytest.raises(HTTPException) as bloqueado:
            await repor.run_repor_workflow_ao_modelo(repor.ReporAoModeloIn(password=SENHA), ADMIN, _pedido())
        assert bloqueado.value.status_code == 429
        assert await _nomes(bd, REDE_INCUMBENTE) == ["fase_custom", "novo"]
        registo = await bd.portal_login_attempts.find_one({"_id": "confirmar_password:u-admin"})
        assert registo["attempts"] == MAX_TENTATIVAS and isinstance(registo["expire_at"], __import__("datetime").datetime)


class TestFormularioReal:
    @pytest.mark.asyncio
    async def test_apaga_so_o_da_rede(self, cadeia):
        bd, repor = cadeia
        r = await repor.run_repor_formulario_ao_modelo(repor.ReporAoModeloIn(password=SENHA), ADMIN, _pedido())
        assert r["reposto"] is True
        redes = sorted([(d.get("network_id") or "modelo") async for d in bd.form_config.find({}, {"_id": 0})])
        assert redes == sorted(["modelo", REDE_DOMUS])
