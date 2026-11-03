"""Regras de atribuição definidas com o Flavio (2026-11-03).

1. Gestão e Intermediário alteram; o Index só o campo Index (e fica no histórico); o resto não.
2. Decide o perfil EFECTIVO.
3. A EMPRESA activa é a fronteira: só se põe gente dela; quem outra empresa atribuiu fica sempre.
   O Master na vista «Sistema» mexe em tudo.
4. Campo próprio para a Direção (Diretor/CEO).
5. O nome do Index só aparece a quem é da rede do Index.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services.regras_de_atribuicao import (
    MENSAGEM_EMPRESA,
    MENSAGEM_INDEX,
    exigir_quem_pode_alterar,
)
from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    db_tenant,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

#: Consultor da Power (mesma empresa da Ana).
PAULO = {"id": "u-paulo", "name": "Paulo", "email": "paulo@power.pt", "role": "consultor"}
#: Consultor da Precision (mesma REDE da Power, outra EMPRESA).
PEDRO = {"id": "u-pedro", "name": "Pedro", "email": "pedro@precision.pt", "role": "consultor"}
#: Diretora da Power.
DIANA = {"id": "u-diana", "name": "Diana", "email": "diana@power.pt", "role": "diretor"}
#: Index da rede (empresa Sistema → aqui, Precision).
IVO = {"id": "u-ivo", "name": "Ivo", "email": "ivo@sistema.pt", "role": "indexacao"}
IRIS = {"id": "u-iris", "name": "Iris", "email": "iris@sistema.pt", "role": "indexacao"}
MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}

ANA_NA_POWER = {**ANA, "vista_empresa_id": "cmp-power"}


@pytest.fixture
def casa(db_tenant):  # noqa: F811
    db_tenant.user_company_roles.docs.extend([
        {"user_id": "u-paulo", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "consultor", "is_default": True},
        {"user_id": "u-pedro", "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "role": "consultor", "is_default": True},
        {"user_id": "u-diana", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "diretor", "is_default": True},
        {"user_id": "u-ivo", "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "role": "indexacao", "is_default": True},
        {"user_id": "u-iris", "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "role": "indexacao", "is_default": True},
    ])
    empresa = {"u-ana": "Power Real Estate", "u-bruno": "Domus", "u-paulo": "Power Real Estate",
               "u-pedro": "Precision Crédito", "u-diana": "Power Real Estate",
               "u-ivo": "Precision Crédito", "u-iris": "Precision Crédito"}
    for u in (ANA, BRUNO, PAULO, PEDRO, DIANA, IVO, IRIS, MASTER):
        db_tenant.users.docs.append({
            **u, "is_active": True, **({"company": empresa[u["id"]]} if u["id"] in empresa else {}),
        })
    proc = next(p for p in db_tenant.processes.docs if p["id"] == "p-power")
    # Processo da Power, partilhado: o Pedro (Precision) foi atribuído pela outra empresa.
    proc.update({
        "assigned_consultor_ids": ["u-pedro"], "consultor_names": ["Pedro"],
        "assigned_indexacao_id": "u-ivo", "indexacao_name": "Ivo",
    })
    return db_tenant


def _ctx(fake_db):
    from services import (
        admin_users_scope,
        assignment_network_guard,
        history,
        process_detail,
        process_staff_assignment,
    )

    return _tenant_db(
        fake_db, assignment_network_guard, process_staff_assignment, admin_users_scope,
        history, process_detail,
    )


def _proc(fake_db, pid="p-power"):
    return next(p for p in fake_db.processes.docs if p["id"] == pid)


async def _assign(actor, papel, **kw):
    from services.process_staff_assignment import run_staff_assign_process

    return await run_staff_assign_process(
        "p-power", actor, papel_efectivo=papel,
        inject_cdc_fn=lambda *a, **k: None,
        invalidate_stats_fn=AsyncMock(), broadcast_fn=AsyncMock(), **kw,
    )


class TestQuemAltera:

    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor", "intermediario"])
    def test_gestao_e_intermediario_alteram(self, papel):
        exigir_quem_pode_alterar(papel, consultor_ids="a", mediador_ids="b")

    @pytest.mark.parametrize("papel", ["consultor", "parceiro", "cliente", ""])
    def test_os_outros_nao(self, papel):
        with pytest.raises(HTTPException) as e:
            exigir_quem_pode_alterar(papel, consultor_ids="a")
        assert e.value.status_code == 403

    def test_o_index_so_mexe_no_campo_index(self):
        exigir_quem_pode_alterar("indexacao", indexacao_id="u-iris")
        with pytest.raises(HTTPException) as e:
            exigir_quem_pode_alterar("indexacao", indexacao_id="u-iris", consultor_ids="u-paulo")
        assert e.value.detail == MENSAGEM_INDEX

    def test_decide_o_perfil_efectivo_e_nao_o_da_conta(self):
        """Um consultor de conta com o perfil Intermediário activo altera."""
        exigir_quem_pode_alterar("intermediario", consultor_ids="a")


class TestAEmpresaEAFronteira:

    @pytest.mark.asyncio
    async def test_pr_alguem_de_outra_empresa_da_mesma_rede_e_recusado(self, casa):
        with _ctx(casa), pytest.raises(HTTPException) as e:
            await _assign(ANA_NA_POWER, "diretor", mediador_ids="u-pedro")
        assert e.value.status_code == 403 and e.value.detail == MENSAGEM_EMPRESA

    @pytest.mark.asyncio
    async def test_quem_a_outra_empresa_atribuiu_fica_mesmo_omitido(self, casa):
        with _ctx(casa):
            await _assign(ANA_NA_POWER, "diretor", consultor_ids="u-paulo")
        assert _proc(casa)["assigned_consultor_ids"] == ["u-paulo", "u-pedro"]

    @pytest.mark.asyncio
    async def test_limpar_tudo_nao_tira_quem_e_de_outra_empresa(self, casa):
        with _ctx(casa):
            await _assign(ANA_NA_POWER, "diretor", consultor_ids="")
        assert _proc(casa)["assigned_consultor_ids"] == ["u-pedro"]

    @pytest.mark.asyncio
    async def test_o_master_em_sistema_mexe_em_tudo(self, casa):
        with _ctx(casa):
            await _assign(MASTER, "master", consultor_ids="u-paulo")
        assert _proc(casa)["assigned_consultor_ids"] == ["u-paulo"]

    @pytest.mark.asyncio
    async def test_a_lista_marca_quem_e_de_outra_empresa_como_so_leitura(self, casa):
        from services import users_api_list
        from services.users_api_list import run_get_users

        with _ctx(casa), patch.object(users_api_list, "db", casa):
            lista = await run_get_users(None, ANA_NA_POWER, for_assignment=True, process_id="p-power")
        por_id = {u["id"]: u for u in lista}
        assert por_id["u-pedro"].get("so_leitura") is True
        assert not por_id["u-paulo"].get("so_leitura")


class TestDirecaoEHistorico:

    @pytest.mark.asyncio
    async def test_a_direcao_tem_campo_proprio_e_conta_como_equipa(self, casa):
        from services.task_assignment_hygiene import ids_atribuidos_do_processo

        with _ctx(casa):
            await _assign(ANA_NA_POWER, "diretor", direcao_ids="u-diana")
        p = _proc(casa)
        assert p["assigned_direcao_ids"] == ["u-diana"] and p["direcao_names"] == ["Diana"]
        assert "u-diana" in ids_atribuidos_do_processo(p)

    @pytest.mark.asyncio
    async def test_o_index_que_muda_o_index_fica_no_historico(self, casa):
        ivo = {**IVO, "effective_role": "indexacao"}
        with _ctx(casa):
            await _assign(ivo, "indexacao", indexacao_id="u-iris")
        assert _proc(casa)["assigned_indexacao_id"] == "u-iris"
        linhas = [h for h in casa.history.docs if h.get("process_id") == "p-power"]
        assert any(
            h["field"] == "assigned_indexacao_id" and h["old_value"] == "Ivo"
            and h["new_value"] == "Iris" and h["user_name"] == "Ivo" and h["created_at"]
            for h in linhas
        )

    @pytest.mark.asyncio
    async def test_as_outras_accoes_do_index_continuam_invisiveis(self, casa):
        from services.history import log_history

        with _ctx(casa):
            await log_history("p-power", {**IVO}, "Carregou documento x")
        assert not [h for h in casa.history.docs if h.get("action") == "Carregou documento x"]


class TestNomeDoIndex:

    @pytest.mark.asyncio
    async def test_quem_e_de_outra_rede_nao_ve_o_index(self, casa):
        from services.process_detail import esconder_index_de_outra_rede

        p = dict(_proc(casa))
        with _ctx(casa):
            await esconder_index_de_outra_rede(p, BRUNO)
        assert p["indexacao_name"] is None and p["assigned_indexacao_id"] is None

    @pytest.mark.asyncio
    async def test_quem_e_da_rede_do_index_ve(self, casa):
        from services.process_detail import esconder_index_de_outra_rede

        p = dict(_proc(casa))
        with _ctx(casa):
            await esconder_index_de_outra_rede(p, ANA)
        assert p["indexacao_name"] == "Ivo"
