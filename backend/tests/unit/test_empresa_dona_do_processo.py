"""«A que empresa pertence este processo?» no detalhe (Multi-Tenant, Out 2026).

Com a partilha B2B (D-25) abre-se um processo que não é da nossa casa. O
detalhe passa a trazer `empresa_dona`: nome da empresa, rede e se quem vê é de
outra rede (isto é, o processo lhe foi partilhado).
"""
from __future__ import annotations

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

DIRETOR_DOMUS = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt",
                 "role": "diretor", "effective_role": "diretor"}
DIRETOR_POWER = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt",
                 "role": "diretor", "effective_role": "diretor"}
MASTER = {"id": "u-master", "name": "M", "email": "m@x.pt",
          "role": "master", "effective_role": "master"}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    return fake_async_db


async def _empresa_dona(mundo, processo, user):
    import services.process_owner as po

    with tenant_db(mundo, po):
        await po.anexar_empresa_dona(processo, user)
    return processo["empresa_dona"]


@pytest.mark.asyncio
class TestEmpresaDona:
    async def test_o_nome_vem_da_empresa_do_carimbo(self, mundo):
        r = await _empresa_dona(mundo, {"id": "p", "company_id": "cmp-power",
                                        "network_id": REDE_INCUMBENTE}, DIRETOR_POWER)
        assert r["company_name"] == "Power Real Estate"
        assert r["company_id"] == "cmp-power"
        assert r["network_id"] == REDE_INCUMBENTE
        assert r["e_de_outra_rede"] is False

    async def test_o_nome_gravado_no_carimbo_vence_a_consulta(self, mundo):
        r = await _empresa_dona(mundo, {"id": "p", "company_id": "cmp-power", "company_name": "Nome Gravado",
                                        "network_id": REDE_INCUMBENTE}, DIRETOR_POWER)
        assert r["company_name"] == "Nome Gravado"

    async def test_processo_partilhado_e_marcado_como_de_outra_rede(self, mundo):
        proc = {"id": "p", "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
                "partner_network_ids": [REDE_DOMUS]}
        r = await _empresa_dona(mundo, proc, DIRETOR_DOMUS)
        assert r["company_name"] == "Power Real Estate"
        assert r["e_de_outra_rede"] is True

    async def test_contraprova_o_proprio_dono_nao_e_marcado(self, mundo):
        proc = {"id": "p", "company_id": "cmp-domus", "network_id": REDE_DOMUS}
        assert (await _empresa_dona(mundo, proc, DIRETOR_DOMUS))["e_de_outra_rede"] is False

    async def test_o_master_nunca_e_de_outra_rede(self, mundo):
        proc = {"id": "p", "company_id": "cmp-domus", "network_id": REDE_DOMUS}
        r = await _empresa_dona(mundo, proc, MASTER)
        assert r["company_name"] == "Domus" and r["e_de_outra_rede"] is False

    async def test_o_legado_sem_marca_e_da_rede_de_omissao_e_lista_as_suas_empresas(self, mundo):
        r = await _empresa_dona(mundo, {"id": "p"}, DIRETOR_POWER)
        assert r["network_id"] == REDE_INCUMBENTE
        assert r["company_name"] == "Power Real Estate · Precision Crédito"
        assert r["e_de_outra_rede"] is False

    async def test_o_legado_visto_pela_ilha_e_de_outra_rede(self, mundo):
        r = await _empresa_dona(mundo, {"id": "p"}, DIRETOR_DOMUS)
        assert r["e_de_outra_rede"] is True

    async def test_sem_carimbo_de_rede_mas_com_empresa_nao_inventa_rede(self, mundo):
        r = await _empresa_dona(mundo, {"id": "p", "company_id": "cmp-domus"}, DIRETOR_DOMUS)
        assert r["company_name"] == "Domus"
        assert r["network_id"] is None
        assert r["e_de_outra_rede"] is False, "sem rede dona não se afirma «partilhado»"

    async def test_sem_nada_que_o_identifique_e_none(self, mundo):
        # empresa desconhecida e sem rede: não se adivinha
        r = await _empresa_dona(mundo, {"id": "p", "company_id": "cmp-inexistente"}, DIRETOR_DOMUS)
        assert r is None

    async def test_a_ilha_implicita_usa_o_nome_da_propria_empresa(self, mundo):
        mundo.companies.docs.append({"id": "cmp-solo", "name": "Solo Lda"})
        r = await _empresa_dona(mundo, {"id": "p", "network_id": "rede:cmp-solo"}, MASTER)
        assert r["company_name"] == "Solo Lda"

    async def test_nunca_levanta(self, mundo, monkeypatch):
        import services.process_owner as po

        async def rebenta(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(po, "resolve_tenant_scope", rebenta)
        proc = {"id": "p", "company_id": "cmp-power"}
        await po.anexar_empresa_dona(proc, DIRETOR_POWER)
        assert proc["empresa_dona"] is None

    async def test_so_lista_empresas_activas_e_com_tecto(self, mundo):
        for i in range(5):
            mundo.companies.docs.append({"id": f"x{i}", "name": f"Extra {i}", "network_id": REDE_INCUMBENTE})
        mundo.companies.docs.append({"id": "off", "name": "Inactiva", "network_id": REDE_INCUMBENTE,
                                     "is_active": False})
        r = await _empresa_dona(mundo, {"id": "p"}, DIRETOR_POWER)
        nomes = r["company_name"].split(" · ")
        assert len(nomes) == 3 and "Inactiva" not in nomes


def test_o_detalhe_do_processo_anexa_a_empresa_dona():
    from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
    import services.process_detail as pd

    codigo = codigo_da_funcao_sem_comentarios(pd.run_get_process_detail)
    assert "anexar_empresa_dona(process, user)" in codigo


def test_a_resposta_do_detalhe_nao_deita_fora_a_empresa_dona():
    """`response_model=ProcessResponse` serializa o que a rota devolve: se o
    modelo ignorasse campos extra, o servidor calculava a empresa e o ecrã
    nunca a recebia."""
    from models.process import ProcessResponse

    empresa = {"company_id": "c", "company_name": "Power", "network_id": "r", "e_de_outra_rede": True}
    saida = ProcessResponse(**{"id": "p", "client_name": "X", "empresa_dona": empresa}).model_dump()
    assert saida["empresa_dona"] == empresa
