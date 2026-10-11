"""A migração que DUPLICA o workflow global por rede (Out 2026).

`scripts/migrar_workflow_por_rede.py`: omissão = só mostra; `--aplicar`
escreve; idempotente; nunca altera o que a rede já tem; recusa-se a copiar um
modelo estragado; tira o índice único por `name` ANTES de copiar.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import migrar_workflow_por_rede as mig
from services import workflow_phases as wp
from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

MODELO = [
    {"id": "m1", "name": "novo", "label": "Novo", "order": 1, "is_active": True, "trigger_finance": None},
    {"id": "m2", "name": "fase_bancaria", "label": "Fase Bancária", "order": 2, "is_active": True},
    {"id": "m3", "name": "concluidos", "label": "Concluídos", "order": 3, "is_active": False,
     "task_templates": [{"id": "t1", "title": "Pedir feedback"}]},
]


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.workflow_scope as ws

    semear(fake_async_db)
    fake_async_db.workflow_statuses.docs.extend(dict(f) for f in MODELO)
    # `index_information` / `drop_index` / `create_index` não existem no duplo:
    fake_async_db.workflow_statuses.index_information = AsyncMock(return_value={
        "_id_": {"key": [("_id", 1)]},
        "idx_workflow_name": {"key": [("name", 1)], "unique": True},
    })
    fake_async_db.workflow_statuses.drop_index = AsyncMock()
    fake_async_db.workflow_statuses.create_index = AsyncMock()
    with tenant_db(fake_async_db, ws):
        wp.invalidar_cache_de_fases()
        yield fake_async_db
    wp.invalidar_cache_de_fases()


def _da_rede(bd, rede):
    return [d for d in bd.workflow_statuses.docs if d.get("network_id") == rede]


class TestPlano:
    @pytest.mark.asyncio
    async def test_so_mostra_e_nao_escreve(self, mundo):
        antes = [dict(d) for d in mundo.workflow_statuses.docs]
        plano = await mig.planear(mundo)
        assert [dict(d) for d in mundo.workflow_statuses.docs] == antes
        assert plano["modelo"] == 3
        assert set(plano["redes"]) == {REDE_INCUMBENTE, REDE_DOMUS}
        assert plano["redes"][REDE_DOMUS] == {"tem": 0, "em_falta": ["novo", "fase_bancaria", "concluidos"]}
        assert plano["indices_unicos_por_nome"] == ["idx_workflow_name"]

    @pytest.mark.asyncio
    async def test_inclui_a_rede_de_omissao_mesmo_sem_empresa(self, mundo, monkeypatch):
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", "rede_sem_empresa")
        plano = await mig.planear(mundo)
        assert "rede_sem_empresa" in plano["redes"]

    @pytest.mark.asyncio
    async def test_recusa_um_modelo_vazio(self, mundo):
        mundo.workflow_statuses.docs.clear()
        with pytest.raises(mig.MigracaoRecusada, match="vazio"):
            await mig.planear(mundo)

    @pytest.mark.asyncio
    async def test_recusa_copiar_nomes_repetidos(self, mundo):
        """Copiar duplicados multiplicava o defeito por todas as redes."""
        mundo.workflow_statuses.docs.append({"id": "m9", "name": "novo", "order": 9})
        with pytest.raises(mig.MigracaoRecusada, match="repetidos"):
            await mig.planear(mundo)

    def test_so_o_indice_unico_exactamente_por_nome_conta(self):
        info = {
            "a": {"key": [("name", 1)], "unique": True},
            "b": {"key": [("name", 1)]},                            # não único
            "c": {"key": [("network_id", 1), ("name", 1)], "unique": True},  # o novo
            "d": {"key": [("order", 1)], "unique": True},
        }
        assert mig._nome_do_indice_unico_por_nome(info) == ["a"]


class TestAplicar:
    @pytest.mark.asyncio
    async def test_cada_rede_fica_com_o_seu_workflow_copiado_do_modelo(self, mundo):
        escrito = await mig.aplicar(mundo)
        for rede in (REDE_INCUMBENTE, REDE_DOMUS):
            copia = _da_rede(mundo, rede)
            assert sorted(d["name"] for d in copia) == ["concluidos", "fase_bancaria", "novo"]
            assert escrito["fases_criadas"][rede] == 3
        concluidos = next(d for d in _da_rede(mundo, REDE_DOMUS) if d["name"] == "concluidos")
        assert concluidos["is_active"] is False
        assert concluidos["task_templates"] == [{"id": "t1", "title": "Pedir feedback"}], \
            "os modelos de tarefas e as flags vão na cópia"

    @pytest.mark.asyncio
    async def test_os_ids_sao_novos_e_o_modelo_fica_intacto(self, mundo):
        modelo_antes = [dict(d) for d in mundo.workflow_statuses.docs if not d.get("network_id")]
        await mig.aplicar(mundo)
        ids = [d["id"] for d in mundo.workflow_statuses.docs if d.get("network_id")]
        assert len(ids) == len(set(ids)) == 6
        assert not set(ids) & {"m1", "m2", "m3"}
        assert [d for d in mundo.workflow_statuses.docs if not d.get("network_id")] == modelo_antes

    @pytest.mark.asyncio
    async def test_a_segunda_passagem_escreve_zero(self, mundo):
        await mig.aplicar(mundo)
        antes = len(mundo.workflow_statuses.docs)
        segunda = await mig.aplicar(mundo)
        assert len(mundo.workflow_statuses.docs) == antes
        assert segunda["fases_criadas"] == {}

    @pytest.mark.asyncio
    async def test_nunca_desfaz_uma_edicao_de_um_administrador(self, mundo):
        mundo.workflow_statuses.docs.append(
            {"id": "x", "name": "novo", "label": "Editado", "order": 1, "network_id": REDE_DOMUS})
        await mig.aplicar(mundo)
        assert next(d for d in _da_rede(mundo, REDE_DOMUS) if d["name"] == "novo")["label"] == "Editado"
        assert len(_da_rede(mundo, REDE_DOMUS)) == 3, "só criou as que faltavam"

    @pytest.mark.asyncio
    async def test_remove_o_indice_unico_por_nome_ANTES_de_copiar(self, mundo):
        ordem = []
        mundo.workflow_statuses.drop_index = AsyncMock(side_effect=lambda *_: ordem.append("drop"))
        original = mundo.workflow_statuses.update_one

        async def update_one(*a, **k):
            ordem.append("copia")
            return await original(*a, **k)

        mundo.workflow_statuses.update_one = update_one
        await mig.aplicar(mundo)
        assert ordem[0] == "drop" and "copia" in ordem

    @pytest.mark.asyncio
    async def test_cria_o_unico_por_rede_e_nome_no_fim(self, mundo):
        escrito = await mig.aplicar(mundo)
        mundo.workflow_statuses.create_index.assert_awaited_once()
        args, kwargs = mundo.workflow_statuses.create_index.await_args
        assert args[0] == [("network_id", 1), ("name", 1)] and kwargs["unique"] is True
        assert escrito["indice_criado"] is True

    @pytest.mark.asyncio
    async def test_com_duplicados_nao_forca_o_indice_e_di_lo(self, mundo):
        # um duplicado DENTRO da rede (o modelo não pode tê-los: seria recusado)
        mundo.workflow_statuses.docs.extend([
            {"id": "d1", "name": "extra", "network_id": REDE_DOMUS, "order": 8},
            {"id": "d2", "name": "extra", "network_id": REDE_DOMUS, "order": 9},
        ])
        escrito = await mig.aplicar(mundo)
        mundo.workflow_statuses.create_index.assert_not_awaited()
        assert escrito["indice_criado"] is False and "repetido" in escrito["indice_nao_criado"]

    @pytest.mark.asyncio
    async def test_is_hub_so_se_retira_a_pedido(self, mundo):
        mundo.companies.docs[0]["is_hub"] = True
        await mig.aplicar(mundo)
        assert mundo.companies.docs[0].get("is_hub") is True
        escrito = await mig.aplicar(mundo, limpar_is_hub=True)
        assert "is_hub" not in mundo.companies.docs[0] and escrito["is_hub_removido"] >= 1

    @pytest.mark.asyncio
    async def test_depois_de_migrar_cada_rede_le_a_sua_copia(self, mundo):
        await mig.aplicar(mundo)
        wp.invalidar_cache_de_fases()
        fases = await wp.carregar_fases(rede=REDE_DOMUS)
        assert fases and all(f["network_id"] == REDE_DOMUS for f in fases)


class TestSegurancaDoScript:
    def test_omissao_e_ler_e_so_aplicar_escreve(self):
        from pathlib import Path

        fonte = (Path(mig.__file__)).read_text(encoding="utf-8")
        assert "--aplicar" in fonte and "Nada foi escrito" in fonte

    def test_usa_a_mesma_funcao_de_copia_que_a_edicao(self):
        """Duas implementações da regra da cópia divergem."""
        from pathlib import Path

        fonte = (Path(mig.__file__)).read_text(encoding="utf-8")
        assert "garantir_workflow_da_rede" in fonte
