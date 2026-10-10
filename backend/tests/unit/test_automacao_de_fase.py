"""Automação por fase: atribuição e tarefas modelo (Bloco 3, ponto 12).

DECISÕES DO DONO DO PRODUTO QUE ESTES TESTES FIXAM
  * Os modelos de tarefa e os papéis a atribuir são configuração de CADA
    FASE (Admin/CEO), não código.
  * Fase sem configuração herda o que o sistema já fazia — mas só à saída da
    Index. Uma fase configurada como «nada» (`[]`) é uma resposta e vence.
  * Entrar numa fase terminal não atribui nem cria trabalho.

O QUE A MUTAÇÃO TEM DE PROVAR
  Que `None` não é `[]`, que a atribuição nunca sobrepõe quem já lá está, que
  a criação é idempotente e que a mudança de fase nunca falha por causa disto.
"""
from __future__ import annotations

import ast
import functools
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services import (
    phase_automation as pa,
    process_assignment,
    workflow_phases,
)

FASES = [
    {"name": "fase_documental", "order": 1, "is_active": True},
    {"name": "fase_bancaria", "order": 2, "is_active": True},
    {"name": "concluidos", "order": 3, "is_active": False},
]

CONSULTOR = {"id": "u-cons", "name": "Carla Consultora", "email": "c@x.pt"}
MEDIADOR = {"id": "u-med", "name": "Marta Mediadora", "email": "m@x.pt"}


def _modelo(titulo="Pedir IRS", papel="todos", ident="t-1", **extra):
    return {"id": ident, "title": titulo, "priority": "Alta", "due_in_days": None,
            "assigned_role": papel, **extra}


# ─────────────────────────────────────────────────────────────────────
# PURO — o plano
# ─────────────────────────────────────────────────────────────────────

class TestONaoConfiguradoNaoEOVazio:
    def test_saida_da_index_sem_configuracao_herda_o_que_sempre_se_fez(self):
        plano = pa.plano_da_fase({"name": "x"}, pa.ORIGEM_INDEXACAO)
        assert plano.papeis == ("consultor", "intermediario")
        assert [m["title"] for m in plano.modelos] == [
            "Analisar documentação inicial",
            "Agendar contacto inicial com o cliente",
        ]
        assert plano.origem_da_config == "omissao"

    @pytest.mark.parametrize("origem", [pa.ORIGEM_MOVIMENTO, pa.ORIGEM_ENTRADA_NO_FLUXO])
    def test_outra_origem_sem_configuracao_nao_faz_nada(self, origem):
        """Uma fase nova nunca atribui por acidente."""
        plano = pa.plano_da_fase({"name": "x"}, origem)
        assert plano.papeis == () and plano.modelos == ()
        assert plano.origem_da_config == "nenhuma"

    def test_fase_inexistente_comporta_se_como_nao_configurada(self):
        assert pa.plano_da_fase(None, pa.ORIGEM_INDEXACAO).papeis == pa.PAPEIS_ATRIBUIVEIS
        assert pa.plano_da_fase(None, pa.ORIGEM_MOVIMENTO).papeis == ()

    def test_lista_vazia_configurada_vence_o_por_omissao(self):
        """`[]` = «não fazer nada». Se fosse tratado como `None`, o Admin
        não conseguia desligar a atribuição da saída da Index."""
        plano = pa.plano_da_fase(
            {"auto_assign_roles": [], "task_templates": []}, pa.ORIGEM_INDEXACAO
        )
        assert plano.papeis == () and plano.modelos == ()
        assert plano.origem_da_config == "fase"

    def test_configuracao_parcial_so_substitui_o_que_foi_configurado(self):
        plano = pa.plano_da_fase(
            {"auto_assign_roles": ["intermediario"]}, pa.ORIGEM_INDEXACAO
        )
        assert plano.papeis == ("intermediario",)
        assert len(plano.modelos) == 2  # os modelos continuam a herdar

    def test_a_configuracao_da_fase_substitui_os_modelos_por_omissao(self):
        plano = pa.plano_da_fase(
            {"task_templates": [_modelo("Só esta")]}, pa.ORIGEM_INDEXACAO
        )
        assert [m["title"] for m in plano.modelos] == ["Só esta"]

    def test_so_papeis_atribuiveis_passam(self):
        plano = pa.plano_da_fase(
            {"auto_assign_roles": ["consultor", "indexacao", "admin"]}, pa.ORIGEM_MOVIMENTO
        )
        assert plano.papeis == ("consultor",)

    def test_o_chamador_nao_consegue_adulterar_as_tarefas_por_omissao(self):
        plano = pa.plano_da_fase({}, pa.ORIGEM_INDEXACAO)
        plano.modelos[0]["title"] = "adulterado"
        outro = pa.plano_da_fase({}, pa.ORIGEM_INDEXACAO)
        assert outro.modelos[0]["title"] == "Analisar documentação inicial"
        assert pa.MODELOS_POR_OMISSAO_DA_SAIDA_DA_INDEX[0]["title"] == (
            "Analisar documentação inicial"
        )

    def test_nem_a_configuracao_da_fase_e_partilhada_com_o_chamador(self):
        fase = {"task_templates": [_modelo("original")]}
        plano = pa.plano_da_fase(fase, pa.ORIGEM_MOVIMENTO)
        plano.modelos[0]["title"] = "adulterado"
        assert fase["task_templates"][0]["title"] == "original"


class TestIdsDosModelos:
    def test_gera_id_para_quem_nao_tem(self):
        saida = pa.garantir_ids_dos_modelos([{"title": "a"}, {"title": "b"}])
        ids = [m["id"] for m in saida]
        assert all(ids) and len(set(ids)) == 2

    def test_preserva_o_id_que_o_editor_devolveu(self):
        saida = pa.garantir_ids_dos_modelos([_modelo(ident="estavel")])
        assert saida[0]["id"] == "estavel"

    def test_ids_repetidos_desfazem_se(self):
        """Dois modelos com o mesmo id criavam uma tarefa só."""
        saida = pa.garantir_ids_dos_modelos([_modelo(ident="x"), _modelo("b", ident="x")])
        assert saida[0]["id"] == "x" and saida[1]["id"] != "x"

    def test_nao_altera_a_entrada(self):
        entrada = [{"title": "a"}]
        pa.garantir_ids_dos_modelos(entrada)
        assert "id" not in entrada[0]


class TestResponsaveis:
    PROC = {
        "id": "p-1",
        "assigned_consultor_ids": ["c1"], "consultor_id": "c1",
        "assigned_mediador_ids": ["m1"],
    }

    def test_todos_junta_consultor_e_intermediario(self):
        assert pa.responsaveis_do_modelo(_modelo(papel="todos"), self.PROC) == ["c1", "m1"]

    def test_um_papel_so_devolve_esse_papel(self):
        assert pa.responsaveis_do_modelo(_modelo(papel="consultor"), self.PROC) == ["c1"]
        assert pa.responsaveis_do_modelo(_modelo(papel="intermediario"), self.PROC) == ["m1"]

    def test_le_os_campos_singulares_legados(self):
        """Quem só tem `consultant_id` (escrito pela dupla antiga) conta."""
        proc = {"id": "p", "consultant_id": "legado"}
        assert pa.responsaveis_do_modelo(_modelo(papel="consultor"), proc) == ["legado"]

    def test_sem_ninguem_no_papel_devolve_vazio(self):
        assert pa.responsaveis_do_modelo(_modelo(papel="consultor"), {"id": "p"}) == []

    def test_um_utilizador_nos_dois_papeis_nao_duplica(self):
        proc = {"id": "p", "assigned_consultor_ids": ["u"], "assigned_mediador_ids": ["u"]}
        assert pa.responsaveis_do_modelo(_modelo(papel="todos"), proc) == ["u"]


class TestConstruirTarefa:
    from datetime import datetime, timezone

    AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)

    def test_forma_da_tarefa(self):
        t = pa.construir_tarefa(
            _modelo(due_in_days=3), fase="fase_documental",
            processo={"id": "p-1"}, responsavel="u-1", agora=self.AGORA,
        )
        assert t["assigned_to"] == ["u-1"]  # SEMPRE lista
        assert t["created_by"] == "system"
        assert t["source"] == "phase_template"
        assert t["phase_template"] == {"fase": "fase_documental", "template_id": "t-1"}
        assert t["due_date"].startswith("2026-10-13")
        assert t["completed"] is False
        assert t["updated_at"] == t["created_at"]  # «por tocar» (higiene)

    def test_prazo_zero_e_um_prazo(self):
        """`if prazo` trataria 0 como «sem prazo» — a armadilha do `|| 30`."""
        t = pa.construir_tarefa(
            _modelo(due_in_days=0), fase="f", processo={"id": "p"},
            responsavel=None, agora=self.AGORA,
        )
        assert t["due_date"].startswith("2026-10-10")

    def test_sem_prazo_nao_ha_data(self):
        t = pa.construir_tarefa(
            _modelo(), fase="f", processo={"id": "p"}, responsavel=None, agora=self.AGORA,
        )
        assert t["due_date"] is None and t["assigned_to"] == []

    def test_herda_o_carimbo_de_rede_do_processo(self):
        t = pa.construir_tarefa(
            _modelo(), fase="f",
            processo={"id": "p", "network_id": "rede-domus", "company_id": "c-9",
                      "company_name": "Domus"},
            responsavel="u", agora=self.AGORA,
        )
        assert (t["network_id"], t["company_id"], t["company_name"]) == (
            "rede-domus", "c-9", "Domus",
        )

    def test_sem_rede_no_processo_nao_se_inventa_carimbo(self):
        """Meio carimbo é pior do que nenhum."""
        t = pa.construir_tarefa(
            _modelo(), fase="f", processo={"id": "p", "company_id": "c-9"},
            responsavel="u", agora=self.AGORA,
        )
        assert "network_id" not in t and "company_id" not in t


# ─────────────────────────────────────────────────────────────────────
# COM BASE DE DADOS
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
async def mundo(fake_async_db):
    for fase in FASES:
        await fake_async_db.workflow_statuses.insert_one(dict(fase))
    await fake_async_db.processes.insert_one(
        {"id": "p-1", "client_name": "Joana", "status": "fase_documental",
         "network_id": "rede-power", "company_id": "c-1"}
    )
    for u in (CONSULTOR, MEDIADOR):
        await fake_async_db.users.insert_one({**u, "role": "x", "is_active": True})

    async def _menos_ocupado(papel, company_id=None, network_id=None):
        return CONSULTOR if papel == "consultor" else MEDIADOR

    with patch.object(pa, "db", fake_async_db), \
         patch.object(process_assignment, "db", fake_async_db), \
         patch.object(workflow_phases, "db", fake_async_db), \
         patch.object(process_assignment, "_find_least_busy_user", AsyncMock(side_effect=_menos_ocupado)), \
         patch.object(process_assignment, "_notify_newly_assigned_users", AsyncMock()), \
         patch("services.history.log_history", AsyncMock()), \
         patch("services.process_sharing.sincronizar_parceiros_sem_falhar", AsyncMock()):
        yield fake_async_db


async def _configurar(db, nome, **campos):
    await db.workflow_statuses.update_one({"name": nome}, {"$set": campos})
    workflow_phases.invalidar_cache_de_fases()


async def _tarefas(db, **filtro):
    return await db.tasks.find({"process_id": "p-1", **filtro}).to_list(100)


class TestCriarTarefas:
    PROC_COM_EQUIPA = {
        "id": "p-1", "assigned_consultor_ids": ["c1"], "assigned_mediador_ids": ["m1"],
    }

    async def test_uma_tarefa_por_responsavel(self, mundo):
        n = await pa.criar_tarefas_da_fase(self.PROC_COM_EQUIPA, "f", [_modelo()])
        assert n == 2
        assert {t["assigned_to"][0] for t in await _tarefas(mundo)} == {"c1", "m1"}

    async def test_e_idempotente(self, mundo):
        await pa.criar_tarefas_da_fase(self.PROC_COM_EQUIPA, "f", [_modelo()])
        assert await pa.criar_tarefas_da_fase(self.PROC_COM_EQUIPA, "f", [_modelo()]) == 0
        assert len(await _tarefas(mundo)) == 2

    async def test_uma_tarefa_concluida_tambem_impede_a_recriacao(self, mundo):
        """O trabalho foi feito: reentrar na fase não o pede outra vez."""
        await pa.criar_tarefas_da_fase(self.PROC_COM_EQUIPA, "f", [_modelo()])
        await mundo.tasks.update_many({}, {"$set": {"completed": True}})
        assert await pa.criar_tarefas_da_fase(self.PROC_COM_EQUIPA, "f", [_modelo()]) == 0

    async def test_outra_fase_ou_outro_modelo_nao_conta_como_ja_criada(self, mundo):
        await pa.criar_tarefas_da_fase(self.PROC_COM_EQUIPA, "f1", [_modelo()])
        assert await pa.criar_tarefas_da_fase(self.PROC_COM_EQUIPA, "f2", [_modelo()]) == 2
        assert await pa.criar_tarefas_da_fase(
            self.PROC_COM_EQUIPA, "f1", [_modelo(ident="t-2")]
        ) == 2

    async def test_sem_ninguem_no_papel_nasce_uma_tarefa_sem_responsavel(self, mundo):
        """Uma tarefa que não nasce não se nota; uma sem dono vê-se."""
        n = await pa.criar_tarefas_da_fase({"id": "p-1"}, "f", [_modelo(papel="consultor")])
        assert n == 1
        (t,) = await _tarefas(mundo)
        assert t["assigned_to"] == []

    async def test_a_tarefa_sem_responsavel_tambem_e_idempotente(self, mundo):
        await pa.criar_tarefas_da_fase({"id": "p-1"}, "f", [_modelo(papel="consultor")])
        assert await pa.criar_tarefas_da_fase({"id": "p-1"}, "f", [_modelo(papel="consultor")]) == 0


class TestEntrarNaFase:
    async def test_saida_da_index_sem_configuracao_faz_o_que_sempre_fez(self, mundo):
        r = await pa.ao_entrar_na_fase("p-1", "fase_documental", origem=pa.ORIGEM_INDEXACAO,
                                       actor={"id": "ix", "role": "indexacao"})
        proc = await mundo.processes.find_one({"id": "p-1"})
        assert proc["consultant_id"] == "u-cons" and proc["mediador_id"] == "u-med"
        assert r.tarefas_criadas == 4  # 2 modelos × 2 responsáveis
        assert r.atribuicao["mediador_id"] == "u-med"

    async def test_so_o_intermediario_quando_a_fase_o_diz(self, mundo):
        await _configurar(mundo, "fase_documental", auto_assign_roles=["intermediario"],
                          task_templates=[_modelo("Tarefa do mediador", papel="intermediario")])
        r = await pa.ao_entrar_na_fase("p-1", "fase_documental", origem=pa.ORIGEM_INDEXACAO)
        proc = await mundo.processes.find_one({"id": "p-1"})
        assert proc["mediador_id"] == "u-med"
        assert not proc.get("consultant_id") and not proc.get("assigned_consultor_ids")
        (t,) = await _tarefas(mundo)
        assert t["assigned_to"] == ["u-med"] and t["title"] == "Tarefa do mediador"
        assert r.tarefas_criadas == 1

    async def test_nunca_sobrepoe_quem_ja_esta_atribuido(self, mundo):
        await mundo.processes.update_one(
            {"id": "p-1"},
            {"$set": {"assigned_consultor_ids": ["ja-la"], "assigned_consultor_id": "ja-la",
                      "consultor_id": "ja-la", "consultant_id": "ja-la"}},
        )
        await pa.ao_entrar_na_fase("p-1", "fase_documental", origem=pa.ORIGEM_INDEXACAO)
        proc = await mundo.processes.find_one({"id": "p-1"})
        assert proc["assigned_consultor_ids"] == ["ja-la"]
        # E as tarefas vão também para quem JÁ lá estava (responsável por papel).
        assert "ja-la" in {t["assigned_to"][0] for t in await _tarefas(mundo)}

    async def test_movimento_sem_configuracao_nao_toca_em_nada(self, mundo):
        r = await pa.ao_entrar_na_fase("p-1", "fase_bancaria", origem=pa.ORIGEM_MOVIMENTO)
        proc = await mundo.processes.find_one({"id": "p-1"})
        assert not proc.get("mediador_id") and not proc.get("consultant_id")
        assert r.tarefas_criadas == 0 and await _tarefas(mundo) == []

    async def test_movimento_com_configuracao_atribui_e_cria(self, mundo):
        await _configurar(mundo, "fase_bancaria", auto_assign_roles=["consultor"],
                          task_templates=[_modelo("Preparar dossier", papel="consultor", ident="d1")])
        await pa.ao_entrar_na_fase("p-1", "fase_bancaria", origem=pa.ORIGEM_MOVIMENTO)
        proc = await mundo.processes.find_one({"id": "p-1"})
        assert proc["consultant_id"] == "u-cons" and not proc.get("mediador_id")
        (t,) = await _tarefas(mundo)
        assert t["assigned_to"] == ["u-cons"]

    async def test_reentrar_na_fase_nao_duplica_tarefas_nem_atribuicoes(self, mundo):
        await _configurar(mundo, "fase_bancaria", auto_assign_roles=["consultor"],
                          task_templates=[_modelo(papel="consultor")])
        await pa.ao_entrar_na_fase("p-1", "fase_bancaria", origem=pa.ORIGEM_MOVIMENTO)
        r2 = await pa.ao_entrar_na_fase("p-1", "fase_bancaria", origem=pa.ORIGEM_MOVIMENTO)
        assert r2.tarefas_criadas == 0 and len(await _tarefas(mundo)) == 1

    async def test_fase_terminal_nao_atribui_nem_cria_e_corta_o_portal(self, mundo):
        await _configurar(mundo, "concluidos", auto_assign_roles=["consultor"],
                          task_templates=[_modelo()])
        cortar = AsyncMock(return_value=2)
        with patch("services.portal_estado.cortar_sessoes_em_tempo_real", cortar):
            r = await pa.ao_entrar_na_fase("p-1", "concluidos", origem=pa.ORIGEM_MOVIMENTO)
        cortar.assert_awaited_once_with("p-1")
        assert r.sessoes_cortadas == 2 and r.tarefas_criadas == 0
        assert await _tarefas(mundo) == []

    async def test_fase_activa_nao_corta_o_portal(self, mundo):
        cortar = AsyncMock()
        with patch("services.portal_estado.cortar_sessoes_em_tempo_real", cortar):
            await pa.ao_entrar_na_fase("p-1", "fase_bancaria", origem=pa.ORIGEM_MOVIMENTO)
        cortar.assert_not_called()

    async def test_as_tarefas_herdam_a_rede_do_processo(self, mundo):
        await pa.ao_entrar_na_fase("p-1", "fase_documental", origem=pa.ORIGEM_INDEXACAO)
        assert {t["network_id"] for t in await _tarefas(mundo)} == {"rede-power"}

    @pytest.mark.parametrize("pid,fase", [("", "x"), ("p-1", None), ("p-1", "")])
    async def test_sem_processo_ou_fase_nao_faz_nada(self, mundo, pid, fase):
        r = await pa.ao_entrar_na_fase(pid, fase, origem=pa.ORIGEM_INDEXACAO)
        assert r.tarefas_criadas == 0 and r.atribuicao == {}


class TestNuncaRompeOMovimento:
    async def test_uma_falha_e_registada_e_nao_propaga(self, mundo, caplog):
        with patch.object(pa, "criar_tarefas_da_fase", AsyncMock(side_effect=RuntimeError("mongo caiu"))):
            r = await pa.ao_entrar_na_fase_sem_falhar(
                "p-1", "fase_documental", origem=pa.ORIGEM_INDEXACAO
            )
        assert r.tarefas_criadas == 0
        assert "mongo caiu" in caplog.text and "p-1" in caplog.text

    async def test_a_versao_estrita_propaga(self, mundo):
        """Contraprova: embrulhar tudo numa só função escondia o defeito."""
        with patch.object(pa, "criar_tarefas_da_fase", AsyncMock(side_effect=RuntimeError("x"))):
            with pytest.raises(RuntimeError):
                await pa.ao_entrar_na_fase("p-1", "fase_documental", origem=pa.ORIGEM_INDEXACAO)


# ─────────────────────────────────────────────────────────────────────
# A LIGAÇÃO AOS ESCRITORES DE FASE
# ─────────────────────────────────────────────────────────────────────

SERVICES = Path(__file__).resolve().parents[2] / "services"

#: Funções que mudam o `status` de um PROCESSO e, de propósito, NÃO correm a
#: automação da fase. Cada uma com o motivo. Uma função nova que escreva o
#: estado e não esteja aqui nem chame o gancho FALHA — a lição do Lote 5
#: («inventariar os escritores»).
SEM_AUTOMACAO_DE_FASE = {
    ("admin_workflow.py", "run_delete_workflow_status"):
        "mover em massa os processos de uma fase apagada: dispararia automações "
        "sobre processos que ninguém tocou",
    ("client_delete.py", "run_delete_client"): "eliminação (soft-delete): não é entrar numa fase",
    ("admin_observability.py", "run_delete_client_registration"): "eliminação (soft-delete)",
    ("restore_api_client.py", "run_restore_client"): "restauro: repõe, não é uma entrada nova",
    ("restore_api_process.py", "run_restore_process"): "restauro: repõe, não é uma entrada nova",
    ("process_assignment.py", "assign_to_indexer"): "fila de espera do indexador, não é uma fase de trabalho",
    ("process_assignment.py", "process_queue_for_freed_indexer"): "fila de espera do indexador",
    # Falsos positivos do detector (escrevem outro `status`, não o do processo):
    ("admin_process_ops.py", "run_update_process_active_status"): "recalcula a flag `is_active`",
    ("admin_process_ops.py", "run_sync_process_emails"): "emails; o `status` é um filtro",
    ("admin_proc_migration_helpers.py", "run_migration_task"): "estado da migração, não do processo",
    ("ai_bulk_helpers.py", "update_client_data"): "estado de revisão da IA",
    ("ai_bulk_sessions.py", "run_finish_aggregated_session"): "estado do job",
    ("portal_documents_notify.py", "check_and_notify_documents_complete"): "estado do pedido de documento",
}

#: Os escritores que TÊM de chamar o gancho (contraprova do inventário).
COM_AUTOMACAO_DE_FASE = {
    ("process_kanban_move.py", "run_kanban_move_side_effects"),
    ("process_update.py", "run_process_update_side_effects"),
    ("process_indexing.py", "auto_assign_after_indexacao"),
    ("portal_onboarding_advance.py", "_auto_advance_from_pre_registo"),
    ("workflow_engine.py", "execute_action"),
}


@functools.lru_cache(maxsize=1)
def _indice_dos_servicos():
    """Uma só passagem pelo AST de `services/`: ({escritores}, {com_gancho}, {todas}).

    Analisar a árvore inteira em CADA teste custava ~10s por teste.
    """
    escritores, com_gancho, todas = set(), set(), set()
    for caminho in sorted(SERVICES.glob("*.py")):
        fonte = caminho.read_text()
        if ("ao_entrar_na_fase" not in fonte
                and "processes" not in fonte):
            for no in ast.walk(ast.parse(fonte)):
                if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    todas.add((caminho.name, no.name))
            continue
        for no in ast.walk(ast.parse(fonte)):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            todas.add((caminho.name, no.name))
            texto = ast.get_source_segment(fonte, no) or ""
            if "ao_entrar_na_fase" in texto:
                com_gancho.add((caminho.name, no.name))
            escreve = chave = False
            for n in ast.walk(no):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr in ("update_one", "update_many", "find_one_and_update")):
                    alvo = ast.get_source_segment(fonte, n.func.value) or ""
                    escreve = escreve or alvo.endswith("processes")
                if isinstance(n, ast.Dict):
                    chave = chave or any(
                        isinstance(k, ast.Constant) and k.value == "status" for k in n.keys
                    )
            if escreve and chave:
                escritores.add((caminho.name, no.name))
    return escritores, com_gancho, todas


class TestOInventarioDosEscritoresDeFase:
    def test_o_detector_le_mesmo_o_codigo(self):
        """Contraprova: um detector cego passava sempre."""
        escritores, _, _ = _indice_dos_servicos()
        assert ("workflow_engine.py", "execute_action") in escritores
        assert ("portal_onboarding_advance.py", "_auto_advance_from_pre_registo") in escritores
        assert len(escritores) >= 10

    def test_cada_escritor_chama_o_gancho_ou_esta_justificado(self):
        escritores, chamam, _ = _indice_dos_servicos()
        sem_resposta = {e for e in escritores if e not in chamam and e not in SEM_AUTOMACAO_DE_FASE}
        assert not sem_resposta, (
            "Escritor do estado do processo sem automação de fase e sem justificação: "
            f"{sorted(sem_resposta)}"
        )

    @pytest.mark.parametrize("ficheiro,funcao", sorted(COM_AUTOMACAO_DE_FASE))
    def test_os_escritores_principais_chamam_mesmo_o_gancho(self, ficheiro, funcao):
        """Sem isto, apagar a chamada deixava o inventário de cima verde."""
        _, chamam, _ = _indice_dos_servicos()
        assert (ficheiro, funcao) in chamam

    def test_as_justificacoes_nao_apontam_para_funcoes_que_ja_nao_existem(self):
        _, _, existentes = _indice_dos_servicos()
        assert set(SEM_AUTOMACAO_DE_FASE) <= existentes


class TestOMovimentoSoDisparaQuandoMudaDeFase:
    """Um cartão largado na mesma coluna não ENTRA nela."""

    async def test_kanban_sem_mudanca_nao_dispara(self):
        from services import process_kanban_move as pkm

        hook = AsyncMock()
        with patch("services.phase_automation.ao_entrar_na_fase_sem_falhar", hook), \
             patch.object(pkm, "run_kanban_move_alerts", AsyncMock(return_value=[])), \
             patch.object(pkm, "notify_client_and_staff_status_change", AsyncMock()), \
             patch.object(pkm, "trigger_waitlist_on_inactive_move", AsyncMock()), \
             patch("services.realtime_delivery.entregar_a_processo", AsyncMock()), \
             patch("services.history.log_history", AsyncMock()), \
             patch("services.trello_service.sync_process_to_trello", AsyncMock()), \
             patch("services.redis_cache.invalidate_stats_cache", AsyncMock()), \
             patch("services.workflow_engine.process_trigger", AsyncMock()):
            for antes, depois, esperado in (("a", "a", 0), ("a", "b", 1)):
                hook.reset_mock()
                await pkm.run_kanban_move_side_effects(
                    process={"id": "p", "client_name": "x"}, process_id="p",
                    user={"id": "u"}, old_status=antes, new_status=depois,
                    flags={"trigger_finance": False, "is_active": True},
                    deed_date=None, broadcast_fn=AsyncMock(),
                    create_finance_snapshot_fn=AsyncMock(), inject_cdc_fn=lambda *a, **k: None,
                )
                assert hook.await_count == esperado, (antes, depois)


class TestAsRegrasEOPutTambemFazemOProcessoEntrarNaFase:
    async def test_uma_regra_que_muda_a_fase_corre_a_automacao_dela(self, mundo):
        from services import process_phase_clock, workflow_engine

        hook = AsyncMock()
        regra = {"id": "r1", "name": "Mover", "action": "change_status",
                 "action_config": {"new_status": "fase_bancaria"}}
        with patch.object(workflow_engine, "db", mundo), \
             patch.object(process_phase_clock, "db", mundo, create=True), \
             patch("services.phase_automation.ao_entrar_na_fase_sem_falhar", hook):
            assert await workflow_engine.execute_action(regra, {"process_id": "p-1"}) is True
        hook.assert_awaited_once()
        assert hook.await_args.args[:2] == ("p-1", "fase_bancaria")
        assert (await mundo.processes.find_one({"id": "p-1"}))["status"] == "fase_bancaria"

    async def test_uma_regra_que_mantem_a_fase_nao_a_corre(self, mundo):
        from services import process_phase_clock, workflow_engine

        hook = AsyncMock()
        regra = {"id": "r1", "name": "Mover", "action": "change_status",
                 "action_config": {"new_status": "fase_documental"}}  # já lá está
        with patch.object(workflow_engine, "db", mundo), \
             patch.object(process_phase_clock, "db", mundo, create=True), \
             patch("services.phase_automation.ao_entrar_na_fase_sem_falhar", hook):
            await workflow_engine.execute_action(regra, {"process_id": "p-1"})
        hook.assert_not_called()

    async def test_o_put_decide_pelo_estado_gravado_e_nao_pelo_pedido(self, mundo):
        from types import SimpleNamespace

        from services import process_update

        hook = AsyncMock()
        passos = [
            # (estado antes, estado gravado, pedido) → corre?
            ("fase_documental", "fase_bancaria", "fase_bancaria", True),
            ("fase_documental", "fase_documental", "fase_bancaria", False),  # recusado
            ("fase_documental", "fase_documental", None, False),
        ]
        for antes, gravado, pedido, corre in passos:
            hook.reset_mock()
            await mundo.processes.update_one({"id": "p-1"}, {"$set": {"status": gravado}})
            with patch.object(process_update, "db", mundo), \
                 patch("services.phase_automation.ao_entrar_na_fase_sem_falhar", hook), \
                 patch("services.trello_service.sync_process_to_trello", AsyncMock()), \
                 patch("services.workflow_engine.process_trigger", AsyncMock()):
                await process_update.run_process_update_side_effects(
                    process={"id": "p-1", "status": antes, "client_name": "J"},
                    process_id="p-1", data=SimpleNamespace(status=pedido),
                    updated={"id": "p-1", "status": gravado}, user={"id": "u"},
                    can_update_status=True,
                    broadcast_fn=AsyncMock(), ensure_finance_snapshot_fn=AsyncMock(),
                    decrypt_fn=lambda d: d,
                )
            assert (hook.await_count == 1) is corre, (antes, gravado, pedido)


class TestADuplaJaNaoCriaTarefas:
    """As tarefas de arranque passaram a ser os MODELOS da fase. Se a dupla
    voltasse a criá-las, cada saída da Index geraria duas séries."""

    def test_nao_resta_o_criador_antigo(self):
        assert not hasattr(process_assignment, "_create_post_indexing_tasks")
        assert not hasattr(process_assignment, "POST_INDEXING_AUTO_TASKS")

    async def test_a_dupla_atribui_sem_criar_tarefas(self, mundo):
        resultado = await process_assignment.dual_auto_assign_on_pre_registo_transition("p-1")
        assert resultado["mediador_id"] == "u-med" and resultado["consultant_id"] == "u-cons"
        assert await mundo.tasks.count_documents({}) == 0

    async def test_a_dupla_so_toca_nos_papeis_pedidos(self, mundo):
        await process_assignment.dual_auto_assign_on_pre_registo_transition(
            "p-1", papeis=("intermediario",)
        )
        proc = await mundo.processes.find_one({"id": "p-1"})
        assert proc["mediador_id"] == "u-med" and not proc.get("consultant_id")
        process_assignment._find_least_busy_user.assert_awaited_once()  # só procurou um papel
