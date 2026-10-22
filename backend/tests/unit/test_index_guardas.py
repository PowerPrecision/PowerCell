"""Guardas de arquitectura do módulo Index (Lote 12): o que NUNCA pode acontecer, por AST.

Cada guarda tem a sua CONTRAPROVA: um leitor que não vê nada passa em tudo.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SERVICOS = RAIZ / "services"
ROTAS = RAIZ / "routes"
MODULOS_DO_INDEX = ("index_ai.py", "index_matrix.py", "index_store.py", "index_jobs.py", "index_api.py", "index_finalize.py",
                    "index_advanced_search.py", "index_banks.py", "index_document_content.py",
                    "previsualizacao_de_ficheiros.py")
ESCRITAS = {"insert_one", "insert_many", "update_one", "update_many", "replace_one", "delete_one", "delete_many",
            "find_one_and_update", "find_one_and_delete", "find_one_and_replace", "bulk_write"}
COLECCOES_DO_INDEX = ("process_professional_metadata", "employers", "process_index_alerts", "process_index_documents")
#: Quem pode tocar nas colecções do Index: o módulo de persistência e a declaração dos índices.
DONOS_DAS_COLECCOES = {"index_store.py", "db_indexes.py"}


def _arvore(ficheiro: Path) -> ast.AST:
    return ast.parse(ficheiro.read_text(encoding="utf-8"))


def _acessos_a_db(arvore: ast.AST) -> list[tuple[str, str | None, int]]:
    """`(colecção, método, linha)` de cada `db.<colecção>.<método>` / `db["colecção"].<método>`."""
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Attribute):
            continue
        base = no.value
        # db.colecao.metodo
        if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name) and base.value.id == "db":
            achados.append((base.attr, no.attr, no.lineno))
        # db["colecao"].metodo
        elif (isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name) and base.value.id == "db"
              and isinstance(base.slice, ast.Constant)):
            achados.append((str(base.slice.value), no.attr, no.lineno))
    return achados


def _fonte_acede(fonte: str, colecao: str) -> bool:
    return any(c == colecao for c, _, _ in _acessos_a_db(ast.parse(fonte)))


class TestALeituraDosGuardas:
    def test_o_leitor_ve_acessos_a_colecoes(self):
        fonte = 'async def f():\n    await db.clients.update_one({}, {})\n    await db["employers"].find({})\n'
        assert sorted((c, m) for c, m, _ in _acessos_a_db(ast.parse(fonte))) == [("clients", "update_one"), ("employers", "find")]

    def test_o_leitor_ve_o_proprio_modulo_de_persistencia(self):
        assert _fonte_acede((SERVICOS / "index_store.py").read_text(encoding="utf-8"), "employers")
        assert _fonte_acede((SERVICOS / "index_store.py").read_text(encoding="utf-8"), "process_professional_metadata")


class TestAIANuncaGravaNaFicha:
    @pytest.mark.parametrize("nome", MODULOS_DO_INDEX)
    def test_nenhum_modulo_do_motor_toca_em_clientes(self, nome):
        for colecao, metodo, linha in _acessos_a_db(_arvore(SERVICOS / nome)):
            assert colecao != "clients", f"{nome}:{linha} toca em db.clients.{metodo}"

    @pytest.mark.parametrize("nome", MODULOS_DO_INDEX)
    def test_nenhum_modulo_do_motor_escreve_em_processos(self, nome):
        # os contadores do processo escrevem-se SÓ por `index_status.gravar_contadores`
        for colecao, metodo, linha in _acessos_a_db(_arvore(SERVICOS / nome)):
            assert not (colecao == "processes" and metodo in ESCRITAS), f"{nome}:{linha} escreve em db.processes"

    def test_so_o_estado_do_index_escreve_em_processos_dentro_do_modulo(self):
        escritas = [m for c, m, _ in _acessos_a_db(_arvore(SERVICOS / "index_status.py")) if c == "processes" and m in ESCRITAS]
        assert escritas, "o leitor ficou cego: index_status.py escreve em db.processes"

    def test_contraprova_o_guarda_apanha_uma_escrita_na_ficha(self):
        fonte = "async def f():\n    await db.processes.update_one({}, {})\n"
        assert [(c, m) for c, m, _ in _acessos_a_db(ast.parse(fonte)) if c == "processes" and m in ESCRITAS]


class TestColecoesDoIndexTemDono:
    def test_so_o_modulo_de_persistencia_toca_nas_colecoes(self):
        intrusos = []
        for pasta in (SERVICOS, ROTAS):
            for ficheiro in sorted(pasta.glob("*.py")):
                if ficheiro.name in DONOS_DAS_COLECCOES:
                    continue
                for colecao, metodo, linha in _acessos_a_db(_arvore(ficheiro)):
                    if colecao in COLECCOES_DO_INDEX:
                        intrusos.append(f"{ficheiro.name}:{linha} db.{colecao}.{metodo}")
        assert intrusos == [], intrusos

    def test_o_job_nao_acede_directamente_as_colecoes_do_index(self):
        # lê-as e escreve-as por `index_store`: um único sítio decide o que se grava
        for colecao, _, _ in _acessos_a_db(_arvore(SERVICOS / "index_jobs.py")):
            assert colecao not in COLECCOES_DO_INDEX


class TestPurezas:
    def test_a_matriz_e_pura(self):
        arvore = _arvore(SERVICOS / "index_matrix.py")
        importados = {n.module for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) and n.module}
        importados |= {a.name for n in ast.walk(arvore) if isinstance(n, ast.Import) for a in n.names}
        assert "database" not in importados
        assert not any(isinstance(n, (ast.Await, ast.AsyncFunctionDef)) for n in ast.walk(arvore))

    def test_o_motor_de_ia_nao_persiste_nada(self):
        assert not _acessos_a_db(_arvore(SERVICOS / "index_ai.py"))
        importados = {n.module for n in ast.walk(_arvore(SERVICOS / "index_ai.py")) if isinstance(n, ast.ImportFrom)}
        assert "database" not in importados

    def test_contraprova_o_detector_de_awaits_funciona(self):
        arvore = ast.parse("async def f():\n    await g()\n")
        assert any(isinstance(n, (ast.Await, ast.AsyncFunctionDef)) for n in ast.walk(arvore))


class TestSoOIndexCriaJobsDoIndex:
    def test_so_index_jobs_cria_tasklogs_do_index(self):
        intrusos = []
        for ficheiro in sorted(SERVICOS.glob("*.py")) + sorted(ROTAS.glob("*.py")):
            if ficheiro.name == "index_jobs.py":
                continue
            fonte = ficheiro.read_text(encoding="utf-8")
            if "TaskType.INDEX_" in fonte and "create_task" in fonte:
                intrusos.append(ficheiro.name)
        assert intrusos == [], "um job do Index sem a chave de unicidade pode correr duas vezes"

    def test_index_jobs_cria_com_a_chave(self):
        fonte = (SERVICOS / "index_jobs.py").read_text(encoding="utf-8")
        assert "create_task" in fonte and "index_job_key" in fonte


class TestNaoSeGuardaTextoDeErros:
    def test_o_motor_nunca_devolve_str_da_excepcao(self):
        # a regra do Log da IA: um erro do fornecedor pode trazer parte da chave
        fonte = (SERVICOS / "index_ai.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "ResultadoDaAnalise":
                for kw in no.keywords:
                    if kw.arg == "motivo":
                        assert "classificar_falha" in ast.unparse(kw.value) or isinstance(kw.value, ast.Constant), ast.unparse(no)
