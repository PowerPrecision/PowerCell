"""A regra «esta rede não tem Index» é UMA e pura; a ligação aos escritores tem guardas por fonte (Out 2026)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services.network_triage import rede_sem_index

RAIZ = Path(__file__).resolve().parents[2] / "services"


class TestARegraPura:
    def test_rede_fora_do_conjunto_com_index_e_sem_index(self):
        assert rede_sem_index("domus", {"power"}) is True

    def test_rede_com_index_nao_e(self):
        assert rede_sem_index("power", {"power", "precision"}) is False

    def test_sem_nenhuma_rede_com_index_a_regra_nao_se_liga(self):
        assert rede_sem_index("domus", set()) is False

    @pytest.mark.parametrize("rede", [None, "", "   "])
    def test_sem_rede_conhecida_nao_se_tira_o_index(self, rede):
        assert rede_sem_index(rede, {"power"}) is False

    def test_aceita_qualquer_iteravel(self):
        assert rede_sem_index("d", iter(["p"])) is True


def _arvore(ficheiro: str, funcao: str | None = None) -> ast.AST:
    arvore = ast.parse((RAIZ / ficheiro).read_text())
    if funcao is None:
        return arvore
    for no in ast.walk(arvore):
        if isinstance(no, (ast.AsyncFunctionDef, ast.FunctionDef)) and no.name == funcao:
            return no
    raise AssertionError(f"{funcao} não existe em {ficheiro}")


def _corpo(ficheiro: str, funcao: str) -> str:
    return ast.unparse(_arvore(ficheiro, funcao))


def _chamadas(ficheiro: str, funcao: str | None, nome: str) -> int:
    """Quantas CHAMADAS a `nome` há (um import ou uma menção em texto não contam — foi o que deixou uma mutação viva)."""
    return sum(
        1 for no in ast.walk(_arvore(ficheiro, funcao))
        if isinstance(no, ast.Call) and getattr(no.func, "id", getattr(no.func, "attr", None)) == nome
    )


class TestLigacaoAosPontosDeEntrada:
    """Apagar a chamada não parte nenhum teste de comportamento dos escritores — daí a guarda (por CHAMADA)."""

    def test_criacao_pelo_staff(self):
        assert _chamadas("process_create.py", "maybe_auto_assign_indexer_on_create", "auto_assign_consultor_on_entry") == 1

    def test_atribuicao_pela_sala_de_triagem(self):
        assert _chamadas("client_assign.py", None, "auto_assign_consultor_on_entry") == 1

    def test_processo_criado_a_partir_da_ficha_do_cliente(self):
        assert _chamadas("client_process_ops.py", None, "auto_assign_consultor_on_entry") == 1

    def test_a_decisao_vem_do_documento_e_nao_de_um_argumento(self):
        corpo = _corpo("process_assignment.py", "auto_assign_consultor_on_entry")
        assert "index_dispensado_por" in corpo and "MARCA_SEM_INDEX" in corpo

    def test_o_consultor_automatico_nao_toca_no_intermediario(self):
        corpo = _corpo("process_assignment.py", "auto_assign_consultor_on_entry")
        assert "('consultor',)" in corpo and "intermediario" not in corpo.replace("auto_assign_intermediario_on_entry", "")

    def test_o_consultor_menos_ocupado_do_portal_escreve_os_seis_campos(self):
        corpo = _corpo("process_assignment.py", "assign_to_least_busy_consultant")
        assert "build_set_consultor_fields" in corpo
