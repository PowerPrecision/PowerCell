"""A ligação do SLA do Index ao resto do sistema (guardas de fonte, com contraprova) — Out 2026."""
from __future__ import annotations

import ast
from pathlib import Path

from services import index_api, index_sla, process_assignment, scheduled_tasks
from services.scheduled_tasks import ScheduledTasksService
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios, codigo_sem_comentarios

SERVICOS = Path(index_sla.__file__).parent


def test_o_ciclo_geral_do_job_horario_executa_o_sla():
    corpo = codigo_da_funcao_sem_comentarios(ScheduledTasksService.run_all_tasks)
    assert "self.run_index_sla" in corpo
    # contraprova: o leitor vê as outras tarefas do mesmo ciclo
    assert "self.check_stale_processes" in corpo


def test_a_tarefa_chama_o_servico_do_sla():
    assert "correr_sla_do_index" in codigo_da_funcao_sem_comentarios(ScheduledTasksService.run_index_sla)


def test_a_reatribuicao_usa_o_mesmo_pool_e_a_mesma_carga_da_atribuicao_normal():
    sla_src = codigo_sem_comentarios((SERVICOS / "index_sla.py").read_text(encoding="utf-8"))
    assert "indexadores_disponiveis" in sla_src
    # uma regra de escolha escrita à mão no SLA divergiria da de `assign_to_indexer`
    assert "build_deep_role_query" not in sla_src and "MAX_ACTIVE_PROCESSES_PER_INDEXER" not in sla_src
    disponiveis = codigo_da_funcao_sem_comentarios(process_assignment.indexadores_disponiveis)
    assert "_indexadores_da_equipa" in disponiveis and "_cargas_dos_indexadores" in disponiveis
    atribuir = codigo_da_funcao_sem_comentarios(process_assignment.assign_to_indexer)
    assert "_indexadores_da_equipa" in atribuir and "_cargas_dos_indexadores" in atribuir


def test_a_gestao_a_avisar_vem_da_rede_do_processo():
    src = codigo_sem_comentarios((SERVICOS / "index_sla.py").read_text(encoding="utf-8"))
    assert "gestao_da_rede_do_processo" in src
    assert "deep_role_in_filter" not in src and "db.users.find" not in src  # nunca uma audiência por cargo sem rede


def test_todo_o_escritor_do_indexador_atribuido_carimba_o_relogio_do_sla():
    """`assign_to_indexer`, `assign_indexacao_to_process`, a fila libertada e a atribuição manual/por cliente."""
    esperados = {
        "process_assignment.py": 3,       # assign_indexacao_to_process, assign_to_indexer, process_queue_for_freed_indexer
        "process_staff_assignment.py": 1,
        "client_assign.py": 1,
    }
    for ficheiro, minimo in esperados.items():
        fonte = codigo_sem_comentarios((SERVICOS / ficheiro).read_text(encoding="utf-8"))
        assert fonte.count("index_assigned_at") >= minimo, ficheiro


def test_a_reatribuicao_do_sla_so_escreve_com_o_filtro_de_nao_iniciado():
    """A guarda da corrida: o `update_one` da reatribuição exige `index_status != in_review` e o mesmo indexador."""
    arvore = ast.parse((SERVICOS / "index_sla.py").read_text(encoding="utf-8"))
    achado = False
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and getattr(no.func, "attr", "") == "update_one" and no.args:
            filtro = ast.unparse(no.args[0])
            if "assigned_indexacao_id" in filtro and "IN_REVIEW" in filtro and "actual" in filtro:
                achado = True
    assert achado, "a reatribuição perdeu a guarda contra a corrida com o indexador que começa a trabalhar"


def test_o_arranque_e_a_actividade_so_vem_de_registar_trabalho():
    for modulo in ("index_api.py", "document_upload.py", "document_direct_upload.py"):
        assert "registar_trabalho" in codigo_sem_comentarios((SERVICOS / modulo).read_text(encoding="utf-8")), modulo
    # o GET da bancada NÃO carimba (uma aba esquecida aberta adiaria o alarme para sempre)
    assert "registar_trabalho" not in codigo_da_funcao_sem_comentarios(index_api.run_get_index_workstation)
    assert "registar_trabalho" in codigo_da_funcao_sem_comentarios(index_api.run_start_work)
