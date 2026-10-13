"""«Registos de Clientes»: só os da casa, e só os que não foram eliminados (QA, Out 2026).

O QUE A QA VIU
  Um utilizador de uma rede satélite abria «Registos de Clientes» e via registos
  que não eram dele. A reprodução contra um MongoDB real mostrou DUAS causas na
  listagem (a fronteira de rede em si estava certa):

    * o `soft delete` do próprio módulo (`is_deleted: True`, `status: "eliminado"`)
      nunca era excluído da listagem, das estatísticas nem dos processos parados;
    * o âmbito era o de PROCESSOS (dono + redes convidadas): um processo da Power
      partilhado com a Domus aparecia nos registos da Domus — com o documento
      inteiro — e o editor do mesmo módulo deixava a Domus EDITÁ-LO e ELIMINÁ-LO.

  Registos são os da casa. O processo partilhado continua visível e trabalhável
  no detalhe (é essa a partilha), mas não é um registo nosso.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

CEO_DOMUS = {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt",
             "role": "ceo", "effective_role": "ceo"}
ADMIN_POWER = {"id": "u-adm-power", "name": "Admin Power", "email": "adm@power.pt",
               "role": "admin", "effective_role": "admin"}
MASTER = {"id": "u-master", "name": "Master", "email": "m@x.pt",
          "role": "master", "effective_role": "master"}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-adm-power", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin", "is_default": True},
        {"user_id": "u-ceo-domus", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "ceo", "is_default": True},
    ])
    fake_async_db.processes.docs.extend([
        # Da Power, partilhado com a Domus (D-25): a Domus vê no detalhe, não é registo dela.
        {"id": "p-partilhado", "client_name": "Partilhado", "status": "novo",
         "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
         "partner_network_ids": [REDE_DOMUS]},
        # Da Domus, já eliminado (soft delete).
        {"id": "p-domus-apagado", "client_name": "Apagado", "status": "eliminado",
         "network_id": REDE_DOMUS, "company_id": "cmp-domus", "is_deleted": True},
        {"id": "p-power-apagado", "client_name": "Apagado Power", "status": "eliminado",
         "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "is_deleted": True},
    ])
    return fake_async_db


def _ids(resposta):
    return {p["id"] for p in resposta["registrations"]}


@pytest.mark.asyncio
class TestListagem:
    async def test_a_ilha_nao_ve_registos_de_outra_rede_nem_o_processo_partilhado(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            r = await obs.run_list_client_registrations(CEO_DOMUS)
        ids = _ids(r)
        assert "p-domus" in ids
        assert "p-power" not in ids
        assert "p-partilhado" not in ids, "um processo partilhado não é um registo da rede convidada"

    async def test_um_registo_eliminado_nao_aparece(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            domus = await obs.run_list_client_registrations(CEO_DOMUS)
            power = await obs.run_list_client_registrations(ADMIN_POWER)
        assert "p-domus-apagado" not in _ids(domus)
        assert "p-power-apagado" not in _ids(power)

    async def test_o_total_e_as_paginas_nao_contam_os_eliminados(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            r = await obs.run_list_client_registrations(CEO_DOMUS, limit=1)
        # Activos da ilha no cenário base: p-domus e p-domus-sem-rede.
        assert r["total"] == 2 and r["pages"] == 2

    async def test_contraprova_o_Master_ve_tudo_menos_os_eliminados(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            r = await obs.run_list_client_registrations(MASTER, limit=100)
        ids = _ids(r)
        assert {"p-power", "p-domus", "p-partilhado"} <= ids
        assert not ({"p-domus-apagado", "p-power-apagado"} & ids)

    async def test_contraprova_a_casa_continua_a_ver_os_seus_registos(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            r = await obs.run_list_client_registrations(ADMIN_POWER)
        assert {"p-power", "p-partilhado"} <= _ids(r), (
            "o dono continua a ver o processo que partilhou"
        )


@pytest.mark.asyncio
class TestEstatisticasEParados:
    async def test_as_estatisticas_nao_contam_eliminados_nem_partilhados_de_fora(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            domus = await obs.run_get_client_registrations_stats(CEO_DOMUS)
            master = await obs.run_get_client_registrations_stats(MASTER)
        assert domus["total"] == 2  # p-domus e p-domus-sem-rede; sem eliminados nem partilhados
        ativos = [p for p in mundo.processes.docs if not p.get("is_deleted")]
        assert master["total"] == len(ativos)

    async def test_os_parados_nao_incluem_eliminados(self, mundo):
        import services.admin_observability as obs

        # Eliminado mas com um estado de workflow ACTIVO: é o caso que só o
        # `is_deleted` apanha (o `status: "eliminado"` já saía pelo filtro de estado).
        mundo.processes.docs.append({
            "id": "p-domus-apagado-activo", "client_name": "Apagado activo", "status": "novo",
            "network_id": REDE_DOMUS, "company_id": "cmp-domus", "is_deleted": True,
        })
        for p in mundo.processes.docs:
            p["updated_at"] = "2020-01-01T00:00:00+00:00"
        with tenant_db(mundo, obs):
            domus = await obs.run_get_stale_processes(CEO_DOMUS, 14)
        ids = {p["id"] for p in domus["processes"]}
        assert "p-domus" in ids
        assert "p-domus-apagado-activo" not in ids


@pytest.mark.asyncio
class TestEditorNaoAlcancaOQueNaoEDaCasa:
    async def test_a_ilha_nao_edita_nem_elimina_um_processo_que_lhe_foi_partilhado(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            for chamada in (
                lambda: obs.run_get_client_registration("p-partilhado", CEO_DOMUS),
                lambda: obs.run_update_client_registration("p-partilhado", {"client_name": "X"}, CEO_DOMUS),
                lambda: obs.run_delete_client_registration("p-partilhado", CEO_DOMUS),
            ):
                with pytest.raises(HTTPException) as erro:
                    await chamada()
                assert erro.value.status_code == 404
        partilhado = next(p for p in mundo.processes.docs if p["id"] == "p-partilhado")
        assert partilhado["client_name"] == "Partilhado" and not partilhado.get("is_deleted")

    async def test_contraprova_o_dono_continua_a_gerir_o_que_partilhou(self, mundo):
        import services.admin_observability as obs

        with tenant_db(mundo, obs):
            r = await obs.run_get_client_registration("p-partilhado", ADMIN_POWER)
        assert r["registration"]["id"] == "p-partilhado"
