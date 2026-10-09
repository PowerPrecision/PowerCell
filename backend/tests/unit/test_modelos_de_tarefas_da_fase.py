"""Configuração da automação por fase no editor do workflow (Bloco 3, ponto 12).

Quem escreve: só Admin/CEO (decisão do dono do produto). O servidor valida a
forma — o editor é uma conveniência, não uma parede — e distingue `None`
(«não configurado», herda) de `[]` («configurado como nada»).
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from models.workflow import (
    MAXIMO_DE_MODELOS_POR_FASE,
    TarefaModelo,
    WorkflowStatusCreate,
    WorkflowStatusUpdate,
)
from services import admin_workflow, workflow_phases


def _fase(**extra):
    return WorkflowStatusCreate(name="fase_x", label="Fase X", order=9, **extra)


class TestAValidacaoDoModelo:
    def test_o_minimo_e_um_titulo(self):
        t = TarefaModelo(title="Pedir IRS")
        assert (t.priority, t.assigned_role, t.due_in_days) == ("Média", "todos", None)

    @pytest.mark.parametrize("titulo", ["", "   ", "\t\n"])
    def test_titulo_vazio_ou_so_espacos_e_recusado(self, titulo):
        with pytest.raises(ValidationError):
            TarefaModelo(title=titulo)

    def test_espacos_internos_normalizam_se(self):
        assert TarefaModelo(title="  Pedir   IRS  ").title == "Pedir IRS"

    def test_titulo_demasiado_longo_e_recusado(self):
        with pytest.raises(ValidationError):
            TarefaModelo(title="x" * 121)

    @pytest.mark.parametrize("prioridade", ["alta", "Urgente", "", "High"])
    def test_prioridade_fora_do_conjunto_e_recusada(self, prioridade):
        with pytest.raises(ValidationError):
            TarefaModelo(title="x", priority=prioridade)

    @pytest.mark.parametrize("papel", ["indexacao", "admin", "parceiro", ""])
    def test_o_responsavel_so_pode_ser_consultor_intermediario_ou_todos(self, papel):
        """A Indexação tem carimbo próprio e nunca é atribuída por regra."""
        with pytest.raises(ValidationError):
            TarefaModelo(title="x", assigned_role=papel)

    @pytest.mark.parametrize("dias", [-1, 366, 10_000])
    def test_prazo_fora_dos_limites_e_recusado(self, dias):
        with pytest.raises(ValidationError):
            TarefaModelo(title="x", due_in_days=dias)

    @pytest.mark.parametrize("dias", [0, 1, 365])
    def test_prazo_nos_limites_e_aceite(self, dias):
        assert TarefaModelo(title="x", due_in_days=dias).due_in_days == dias

    def test_uma_fase_tem_um_tecto_de_modelos(self):
        demais = [{"title": f"t{i}"} for i in range(MAXIMO_DE_MODELOS_POR_FASE + 1)]
        with pytest.raises(ValidationError):
            _fase(task_templates=demais)
        assert len(_fase(task_templates=demais[:-1]).task_templates) == MAXIMO_DE_MODELOS_POR_FASE

    @pytest.mark.parametrize("papeis", [["indexacao"], ["consultor", "admin"], ["todos"]])
    def test_papeis_a_atribuir_fora_do_conjunto_sao_recusados(self, papeis):
        with pytest.raises(ValidationError):
            _fase(auto_assign_roles=papeis)

    def test_none_e_lista_vazia_sao_coisas_diferentes_na_forma(self):
        assert _fase().auto_assign_roles is None and _fase().task_templates is None
        assert _fase(auto_assign_roles=[], task_templates=[]).auto_assign_roles == []


@pytest.fixture
async def mundo(fake_async_db):
    await fake_async_db.workflow_statuses.insert_one(
        {"id": "w-1", "name": "fase_x", "label": "Fase X", "order": 9, "color": "blue",
         "is_default": False, "auto_assign_roles": ["consultor"],
         "task_templates": [{"id": "keep", "title": "Antiga", "priority": "Média",
                             "due_in_days": None, "assigned_role": "todos"}]}
    )
    with patch.object(admin_workflow, "db", fake_async_db), \
         patch.object(workflow_phases, "db", fake_async_db):
        yield fake_async_db


async def _gravada(db):
    return await db.workflow_statuses.find_one({"id": "w-1"})


class TestGravarNaFase:
    async def test_um_campo_nao_enviado_nao_mexe_na_configuracao(self, mundo):
        await admin_workflow.run_update_workflow_status(
            "w-1", WorkflowStatusUpdate(label="Novo nome"), {"id": "u"}
        )
        d = await _gravada(mundo)
        assert d["auto_assign_roles"] == ["consultor"]
        assert d["task_templates"][0]["id"] == "keep"

    async def test_null_explicito_volta_a_herdar_o_por_omissao(self, mundo):
        """Sem isto o Admin nunca conseguia desfazer uma configuração: a
        ausência do campo e o `null` chegam iguais ao serviço (`None`), e só
        o `model_fields_set` os distingue."""
        pedido = WorkflowStatusUpdate.model_validate(
            {"auto_assign_roles": None, "task_templates": None}
        )
        await admin_workflow.run_update_workflow_status("w-1", pedido, {"id": "u"})
        d = await _gravada(mundo)
        assert d["auto_assign_roles"] is None and d["task_templates"] is None

    async def test_so_os_campos_enviados_como_null_sao_repostos(self, mundo):
        pedido = WorkflowStatusUpdate.model_validate({"task_templates": None})
        await admin_workflow.run_update_workflow_status("w-1", pedido, {"id": "u"})
        d = await _gravada(mundo)
        assert d["task_templates"] is None
        assert d["auto_assign_roles"] == ["consultor"]  # não enviado: intacto

    async def test_lista_vazia_grava_se_e_desliga_a_automacao(self, mundo):
        """Se `[]` fosse tratado como «não enviado», o Admin nunca conseguia
        desligar a atribuição por omissão da saída da Index."""
        await admin_workflow.run_update_workflow_status(
            "w-1", WorkflowStatusUpdate(auto_assign_roles=[], task_templates=[]), {"id": "u"}
        )
        d = await _gravada(mundo)
        assert d["auto_assign_roles"] == [] and d["task_templates"] == []

    async def test_modelos_novos_recebem_id_e_os_existentes_mantem_o_seu(self, mundo):
        await admin_workflow.run_update_workflow_status(
            "w-1",
            WorkflowStatusUpdate(task_templates=[
                TarefaModelo(id="keep", title="Antiga editada"),
                TarefaModelo(title="Nova"),
            ]),
            {"id": "u"},
        )
        d = await _gravada(mundo)
        ids = [m["id"] for m in d["task_templates"]]
        assert ids[0] == "keep" and ids[1] and ids[1] != "keep"
        assert d["task_templates"][0]["title"] == "Antiga editada"

    async def test_papeis_repetidos_deduplicam_se_pela_ordem(self, mundo):
        await admin_workflow.run_update_workflow_status(
            "w-1",
            WorkflowStatusUpdate(auto_assign_roles=["intermediario", "consultor", "intermediario"]),
            {"id": "u"},
        )
        assert (await _gravada(mundo))["auto_assign_roles"] == ["intermediario", "consultor"]

    async def test_gravar_invalida_a_cache_das_fases(self, mundo):
        """A automação lê as fases pela cache: sem invalidar, a nova
        configuração só valia daí a 30s (e noutro worker, mais)."""
        await workflow_phases.carregar_fases()
        assert workflow_phases._cache_de_fases is not None
        await admin_workflow.run_update_workflow_status(
            "w-1", WorkflowStatusUpdate(auto_assign_roles=[]), {"id": "u"}
        )
        assert workflow_phases._cache_de_fases is None

    async def test_criar_a_fase_sem_configuracao_grava_none_e_nao_lista_vazia(self, mundo):
        await admin_workflow.run_create_workflow_status(
            WorkflowStatusCreate(name="outra", label="Outra", order=10), {"id": "u"}
        )
        d = await mundo.workflow_statuses.find_one({"name": "outra"})
        assert d["auto_assign_roles"] is None and d["task_templates"] is None

    async def test_criar_a_fase_com_configuracao_grava_a_com_ids(self, mundo):
        resposta = await admin_workflow.run_create_workflow_status(
            WorkflowStatusCreate(
                name="outra", label="Outra", order=10,
                auto_assign_roles=["intermediario"],
                task_templates=[TarefaModelo(title="Pedir IRS", assigned_role="intermediario")],
            ),
            {"id": "u"},
        )
        assert resposta.auto_assign_roles == ["intermediario"]
        assert resposta.task_templates[0].id  # gerado no servidor

    async def test_a_resposta_devolve_a_configuracao_ao_editor(self, mundo):
        lista = await admin_workflow.run_get_workflow_statuses({"id": "u"})
        (fase,) = lista
        assert fase.auto_assign_roles == ["consultor"]
        assert fase.task_templates[0].title == "Antiga"


ROUTES = Path(__file__).resolve().parents[2] / "routes" / "admin.py"


class TestSoAdminECeoConfiguram:
    def _roles_da_rota(self, funcao: str) -> str:
        fonte = ROUTES.read_text()
        for no in ast.walk(ast.parse(fonte)):
            if isinstance(no, ast.AsyncFunctionDef) and no.name == funcao:
                return ast.get_source_segment(fonte, no).split("\n")[0]
        raise AssertionError(f"rota {funcao} não encontrada")

    @pytest.mark.parametrize("funcao", ["create_workflow_status", "update_workflow_status"])
    def test_as_rotas_que_gravam_exigem_admin_ou_ceo(self, funcao):
        linha = self._roles_da_rota(funcao)
        assert "UserRole.ADMIN" in linha and "UserRole.CEO" in linha
        for papel in ("DIRETOR", "CONSULTOR", "INTERMEDIARIO", "INDEXACAO", "ADMINISTRATIVO"):
            assert f"UserRole.{papel}" not in linha, f"{papel} não pode configurar fases"

    def test_o_detector_le_mesmo_a_rota(self):
        assert "require_roles" in self._roles_da_rota("update_workflow_status")
