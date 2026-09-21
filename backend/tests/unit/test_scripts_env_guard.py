"""Guarda de ambiente dos scripts de dados simulados.

Protege a separação dev/prod no único sítio onde ela não existia: os scripts
de seed, que escrevem centenas de registos fictícios na base de dados que
estiver configurada no ambiente.
"""

import ast
import io
import pathlib

import pytest

from scripts.env_guard import (
    VARIAVEL_DE_ESCAPE,
    db_name_parece_producao,
    detectar_producao,
    escape_autorizado,
    require_non_production_db,
)

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]
PASTA_SCRIPTS = RAIZ_BACKEND / "scripts"

# Scripts que geram/inserem dados simulados e têm de estar protegidos.
SEEDS_PROTEGIDOS = [
    "seed_completo.py",
    "seed_fill_mock_data.py",
    "seed_massive_dev_data.py",
    "seed_notes.py",
    "seed_performance_data.py",
    "seed_qa_ultimate.py",
    "seed_realistic_data.py",
    "seed_test_clients.py",
]


class TestDeteccaoDeProducao:
    def test_environment_production_e_producao(self):
        e_prod, motivo = detectar_producao({"ENVIRONMENT": "production"})
        assert e_prod is True
        assert "ENVIRONMENT" in motivo

    def test_app_env_prod_e_producao(self):
        e_prod, motivo = detectar_producao({"APP_ENV": "PROD"})
        assert e_prod is True
        assert "APP_ENV" in motivo

    def test_development_nao_e_producao(self):
        assert detectar_producao({"ENVIRONMENT": "development"}) == (False, "")

    def test_ambiente_vazio_nao_e_producao(self):
        """O CI corre sem ENVIRONMENT definido — não pode bloquear."""
        assert detectar_producao({}) == (False, "")

    def test_db_name_com_prod_e_producao(self):
        e_prod, motivo = detectar_producao({"DB_NAME": "powercell_prod"})
        assert e_prod is True
        assert "DB_NAME" in motivo

    def test_marcador_seguro_ganha_ao_prod(self):
        """"prod_test_db" é uma base de teste, não produção."""
        assert db_name_parece_producao("prod_test_db") is False
        assert db_name_parece_producao("powercell_dev") is False
        assert db_name_parece_producao("staging_prod") is False

    def test_db_name_ausente_nao_e_producao(self):
        assert db_name_parece_producao(None) is False
        assert db_name_parece_producao("") is False


class TestVariavelDeEscape:
    @pytest.mark.parametrize("valor", ["true", "TRUE", "1", "yes", "sim"])
    def test_valores_aceites(self, valor):
        assert escape_autorizado({VARIAVEL_DE_ESCAPE: valor}) is True

    @pytest.mark.parametrize("valor", ["false", "0", "no", "", "talvez"])
    def test_valores_recusados(self, valor):
        assert escape_autorizado({VARIAVEL_DE_ESCAPE: valor}) is False

    def test_ausente_e_recusado(self):
        assert escape_autorizado({}) is False


class TestRequireNonProductionDb:
    def test_aborta_em_producao(self):
        saida = io.StringIO()
        with pytest.raises(SystemExit) as exc:
            require_non_production_db("seed_x", ambiente={"ENVIRONMENT": "production"}, saida=saida)
        assert exc.value.code == 2
        texto = saida.getvalue()
        assert "ABORTADO" in texto
        assert VARIAVEL_DE_ESCAPE in texto, "a mensagem tem de dizer como prosseguir"

    def test_deixa_passar_em_dev(self):
        saida = io.StringIO()
        require_non_production_db("seed_x", ambiente={"ENVIRONMENT": "dev"}, saida=saida)
        assert saida.getvalue() == ""

    def test_deixa_passar_sem_variaveis(self):
        """Ambiente local/CI sem ENVIRONMENT: não bloqueia."""
        require_non_production_db("seed_x", ambiente={}, saida=io.StringIO())

    def test_escape_explicito_permite_mas_avisa(self):
        saida = io.StringIO()
        require_non_production_db(
            "seed_x",
            ambiente={"ENVIRONMENT": "production", VARIAVEL_DE_ESCAPE: "true"},
            saida=saida,
        )
        texto = saida.getvalue()
        assert "PRODUÇÃO" in texto
        assert "ordem explícita" in texto


class TestScriptsProtegidos:
    """Guardas sobre o código-fonte: o guarda tem de continuar ligado."""

    @pytest.mark.parametrize("nome", SEEDS_PROTEGIDOS)
    def test_script_chama_o_guarda(self, nome):
        caminho = PASTA_SCRIPTS / nome
        assert caminho.exists(), f"{nome} desapareceu — actualizar esta lista"
        fonte = caminho.read_text(encoding="utf-8")
        assert "require_non_production_db(" in fonte, (
            f"{nome} insere dados simulados sem guarda de ambiente"
        )

    @pytest.mark.parametrize("nome", SEEDS_PROTEGIDOS)
    def test_guarda_corre_antes_do_main(self, nome):
        """A chamada tem de ser a PRIMEIRA instrução executável do `__main__`.

        Se ficasse depois do `main()`, os dados já estariam escritos.
        """
        fonte = (PASTA_SCRIPTS / nome).read_text(encoding="utf-8")
        arvore = ast.parse(fonte)

        blocos_main = [
            no for no in arvore.body
            if isinstance(no, ast.If)
            and isinstance(no.test, ast.Compare)
            and isinstance(no.test.left, ast.Name)
            and no.test.left.id == "__name__"
        ]
        assert blocos_main, f"{nome} não tem bloco __main__"

        corpo = blocos_main[0].body
        chamadas = [
            i for i, no in enumerate(corpo)
            if isinstance(no, ast.Expr)
            and isinstance(no.value, ast.Call)
            and getattr(no.value.func, "id", "") == "require_non_production_db"
        ]
        assert chamadas, f"{nome}: guarda ausente do bloco __main__"

        indice_guarda = chamadas[0]
        outras_chamadas = [
            i for i, no in enumerate(corpo)
            if isinstance(no, ast.Expr) and isinstance(no.value, ast.Call) and i != indice_guarda
        ]
        assert all(i > indice_guarda for i in outras_chamadas), (
            f"{nome}: há trabalho a correr ANTES do guarda de ambiente"
        )
