"""A Lista de Processos sabe a quem oferecer «Marcar como Pago».

`enriquecer_comissoes_pendentes` acrescenta `processo_fechado` e
`comissoes_pendentes` a cada linha, CALCULADOS ao servir. Só para quem pode
marcar como pago (um valor financeiro não vai a um consultor) e só consulta a
BD de comissões para processos fechados.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import process_closed_guard as guarda
from services import process_pending_commissions as ppc
from tests.unit.helpers_fonte import codigo_sem_comentarios
from tests.unit.helpers_tenant import (  # noqa: F401
    rede_de_omissao_incumbente,
    tenant_db,
)
from tests.unit.test_excepcao_de_pagamento_processo_fechado import (
    ADMINISTRATIVO, CONSULTOR, _semear,
)
from tests.unit.test_processo_fechado_rotas_secundarias import (
    ABERTO, FECHADO, FECHADO_2, FECHADO_DA_DOMUS, PERFIS, _registo,
)


def _linhas(*ids_e_estados):
    return [{"id": i, "status": s} for i, s in ids_e_estados]


@pytest.fixture
def bd(fake_async_db, rede_de_omissao_incumbente):
    import services.finance_scope as fs  # noqa: F401  (sem `db` próprio: usa o do tenant)
    import services.workflow_phases as wp

    _semear(fake_async_db)
    with tenant_db(fake_async_db, ppc, guarda, wp):
        yield fake_async_db


class TestQuemRecebeAsChaves:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", ["master", "admin", "ceo", "diretor", "administrativo"])
    async def test_quem_pode_marcar_recebe(self, bd, perfil):
        linhas = _linhas((FECHADO, "concluido"))
        utilizador = {**PERFIS, "administrativo": ADMINISTRATIVO}[perfil]
        await ppc.enriquecer_comissoes_pendentes(linhas, utilizador, papel=perfil)
        assert linhas[0]["processo_fechado"] is True
        assert linhas[0]["comissoes_pendentes"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "indexacao", "parceiro", ""])
    async def test_quem_nao_pode_nao_recebe_as_chaves_nem_custa_uma_consulta(self, bd, papel):
        linhas = _linhas((FECHADO, "concluido"))
        with patch.object(bd.process_finances, "find") as consulta:
            await ppc.enriquecer_comissoes_pendentes(linhas, CONSULTOR, papel=papel)
        assert "comissoes_pendentes" not in linhas[0] and "processo_fechado" not in linhas[0]
        consulta.assert_not_called()


class TestOQueSeConta:
    @pytest.mark.asyncio
    async def test_processo_aberto_nao_tem_botao_nem_consulta(self, bd):
        linhas = _linhas((ABERTO, "fase_bancaria"))
        with patch.object(bd.process_finances, "find") as consulta:
            await ppc.enriquecer_comissoes_pendentes(linhas, PERFIS["master"], papel="master")
        assert linhas[0]["processo_fechado"] is False and linhas[0]["comissoes_pendentes"] == 0
        consulta.assert_not_called()

    @pytest.mark.asyncio
    async def test_conta_pendentes_e_faturadas_mas_nao_pagas_nem_canceladas(self, bd):
        linhas = _linhas((FECHADO, "concluido"), (FECHADO_2, "arquivo"),
                         ("p-fechado-pago", "concluido"), ("p-fechado-cancelado", "concluido"))
        await ppc.enriquecer_comissoes_pendentes(linhas, PERFIS["master"], papel="master")
        contagens = {l["id"]: l["comissoes_pendentes"] for l in linhas}
        assert contagens == {FECHADO: 1, FECHADO_2: 1, "p-fechado-pago": 0, "p-fechado-cancelado": 0}

    @pytest.mark.asyncio
    async def test_so_conta_o_que_o_utilizador_ve(self, bd):
        """O registo de outra rede não é dele: nem conta, nem aparece."""
        bd.process_finances.docs.append(_registo("f-fechado-domus", FECHADO, "cmp-domus"))
        linhas = _linhas((FECHADO, "concluido"))
        await ppc.enriquecer_comissoes_pendentes(linhas, PERFIS["diretor"], papel="diretor")
        assert linhas[0]["comissoes_pendentes"] == 1

    @pytest.mark.asyncio
    async def test_um_processo_de_outra_rede_conta_zero(self, bd):
        linhas = _linhas((FECHADO_DA_DOMUS, "concluido"))
        await ppc.enriquecer_comissoes_pendentes(linhas, PERFIS["diretor"], papel="diretor")
        assert linhas[0]["processo_fechado"] is True and linhas[0]["comissoes_pendentes"] == 0

    @pytest.mark.asyncio
    async def test_uma_falha_a_ler_nao_derruba_a_listagem(self, bd):
        linhas = _linhas((FECHADO, "concluido"))
        with patch.object(bd.process_finances, "find", side_effect=RuntimeError("bd")):
            await ppc.enriquecer_comissoes_pendentes(linhas, PERFIS["master"], papel="master")
        assert linhas[0]["processo_fechado"] is True and linhas[0]["comissoes_pendentes"] == 0

    @pytest.mark.asyncio
    async def test_lista_vazia_nao_faz_nada(self, bd):
        await ppc.enriquecer_comissoes_pendentes([], PERFIS["master"], papel="master")

    @pytest.mark.asyncio
    async def test_nunca_se_grava(self, bd):
        antes = [dict(d) for d in bd.processes.docs]
        await ppc.enriquecer_comissoes_pendentes(_linhas((FECHADO, "concluido")), PERFIS["master"], papel="master")
        assert bd.processes.docs == antes


class TestLigacaoNasListagens:
    def test_as_duas_listagens_chamam_o_enriquecimento(self):
        import services.process_list_enrichment as le

        for nome in ("run_get_processes", "run_get_processes_paginated"):
            import inspect

            codigo = codigo_sem_comentarios(inspect.getsource(getattr(le, nome)))
            assert "enriquecer_comissoes_pendentes" in codigo, nome
