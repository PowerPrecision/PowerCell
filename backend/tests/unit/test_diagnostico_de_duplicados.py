"""O diagnóstico de duplicados de clientes (D-38 → D-42: identidade GLOBAL, sem telemóvel).

O que estes testes protegem:
  * a IDENTIDADE de cada campo é a da guarda (`client_uniqueness`): um relatório
    que agrupasse com outra regra contaria violações que a guarda não vê, ou
    esconderia as que vê;
  * a identidade é GLOBAL: o mesmo NIF em duas redes É um duplicado (D-42), e o grupo diz as redes;
  * a ARITMÉTICA — grupos, clientes envolvidos e «casos» (a mesma pessoa
    inserida duas vezes repete 3 campos de uma vez e é UMA decisão, não 3);
  * a PRIVACIDADE: por omissão nada de valores completos nem nomes;
  * que o script é ESTRITAMENTE de leitura (guarda por fonte, com contraprova).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services import client_duplicates_audit as da
from services.client_duplicates_audit import Registo, auditar, mascarar, resumir

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_client_duplicates.py"


def _r(id_, rede="R1", **kw):
    return Registo(id=id_, rede=rede, **kw)


class TestAIdentidadeEADaGuarda:
    def test_o_telemovel_nao_e_um_campo_da_auditoria(self):
        """INVERTIDO (era uma chave única no D-38): o telemóvel saiu da identidade."""
        assert not hasattr(da, "chave_telefone")
        assert "telefone" not in {f for f in Registo.__dataclass_fields__}
        from services.client_uniqueness import CAMPOS_UNICOS

        assert CAMPOS_UNICOS == ("nif", "email")

    def test_nif_so_com_nove_digitos(self):
        assert da.chave_nif("200 000 004") == "200000004"
        assert da.chave_nif("20000000") is None
        assert da.chave_nif("") is None

    def test_email_sem_distincao_de_maiusculas(self):
        assert da.chave_email("  A@X.pt ") == "a@x.pt"
        assert da.chave_email("") is None


class TestOsGrupos:
    def test_dois_clientes_com_o_mesmo_nif_na_mesma_rede_sao_um_grupo(self):
        rel = auditar([_r("a", nif="200000004"), _r("b", nif="200000004"), _r("c", nif="500000000")])
        assert [(g.campo, g.membros) for g in rel.grupos] == [("nif", ("a", "b"))]

    def test_o_mesmo_nif_em_duas_redes_E_um_duplicado_que_atravessa_redes(self):
        """INVERTIDO (D-38: «não é violação»): a identidade é global."""
        rel = auditar([_r("a", "R1", nif="200000004"), _r("b", "R2", nif="200000004")])
        assert [(g.campo, g.membros, g.redes) for g in rel.grupos] == [("nif", ("a", "b"), ("R1", "R2"))]
        assert rel.grupos[0].atravessa_redes
        assert rel.grupos_entre_redes == {"nif": 1}
        assert resumir(rel)["indice_unico_viavel"] is False

    def test_um_grupo_dentro_de_uma_rede_nao_atravessa(self):
        rel = auditar([_r("a", "R1", nif="200000004"), _r("b", "R1", nif="200000004")])
        assert not rel.grupos[0].atravessa_redes and rel.grupos_entre_redes == {}

    def test_a_mesma_pessoa_inserida_duas_vezes_e_UM_caso_com_dois_grupos(self):
        a = dict(nif="200000004", email="a@x.pt")
        rel = auditar([_r("a", **a), _r("b", **a), _r("c", nif="500000000")])
        assert len(rel.grupos) == 2
        assert rel.casos == [("a", "b")]
        assert resumir(rel)["casos"] == 1
        assert resumir(rel)["clientes_afectados"] == 2

    def test_casos_ligados_por_campos_diferentes_fundem_se(self):
        """a~b pelo NIF e b~c pelo email: o operador tem UMA pessoa a resolver, não duas."""
        rel = auditar([
            _r("a", nif="200000004"), _r("b", nif="200000004", email="x@x.pt"), _r("c", email="x@x.pt"),
            _r("z", nif="500000000"),
        ])
        assert rel.casos == [("a", "b", "c")]

    def test_o_mesmo_cliente_nao_forma_grupo_consigo_proprio(self):
        rel = auditar([_r("a", nif="200000004"), _r("a", nif="200000004")])
        assert rel.grupos == []

    def test_sem_violacoes_o_indice_unico_e_viavel(self):
        rel = auditar([_r("a", nif="200000004"), _r("b", nif="500000000")])
        assert resumir(rel)["indice_unico_viavel"] is True

    def test_zero_clientes_lidos_nao_e_sem_duplicados(self):
        """Uma base errada (DB_NAME enganado) não pode ler-se como «índice viável»."""
        assert resumir(auditar([]))["indice_unico_viavel"] is False

    def test_o_resumo_por_rede_conta_so_as_redes_do_grupo(self):
        rel = auditar([
            _r("a", "R1", nif="200000004"), _r("b", "R1", nif="200000004"),
            _r("c", "R2", email="x@x.pt"), _r("d", "R2", email="x@x.pt"), _r("e", "R2", email="x@x.pt"),
        ])
        r = resumir(rel)["por_rede"]
        assert r["R1"] == {"grupos": {"nif": 1, "email": 0}, "clientes": 2}
        assert r["R2"] == {"grupos": {"nif": 0, "email": 1}, "clientes": 3}

    def test_os_maiores_grupos_vem_primeiro(self):
        rel = auditar([
            _r("a", email="p@x.pt"), _r("b", email="p@x.pt"),
            _r("c", nif="200000004"), _r("d", nif="200000004"), _r("e", nif="200000004"),
        ])
        assert [len(g.membros) for g in rel.grupos] == [3, 2]


class TestOValorCifrado:
    def test_valor_cifrado_cai_para_o_indice_cego_e_di_lo(self):
        doc = {"id": "a", "dados_pessoais": {"nif": "ENC:xxx", "nif_hash": "h1"}, "contacto": {}}
        r = da.registo_de(doc, rede="R1")
        assert r.nif == "nif-hash:h1"
        assert r.sem_decifrar == ("nif",)

    def test_dois_cifrados_com_o_mesmo_indice_agrupam(self):
        docs = [{"id": i, "dados_pessoais": {"nif": "ENC:x", "nif_hash": "h1"}} for i in "ab"]
        rel = auditar([da.registo_de(d, rede="R1") for d in docs])
        assert len(rel.grupos) == 1
        assert resumir(rel)["sem_decifrar"] == {"nif": 2}

    def test_cifrado_sem_indice_nao_inventa_chave(self):
        r = da.registo_de({"id": "a", "dados_pessoais": {"nif": "ENC:x"}}, rede="R1")
        assert r.nif is None


class TestAQualRedePertence:
    def test_o_carimbo_vence(self):
        assert da.rede_do_documento({"network_id": "R9", "company_id": "c1"}, {"c1": "R1"}) == "R9"

    def test_a_empresa_da_a_rede(self):
        assert da.rede_do_documento({"company_id": "c1"}, {"c1": "R1"}) == "R1"

    def test_empresa_sem_grupo_e_uma_ilha(self):
        assert da.rede_do_documento({"company_id": "c9"}, {}) == "rede:c9"

    def test_a_pilha_por_carimbar_e_da_rede_de_omissao(self, monkeypatch):
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", "grupo_x")
        assert da.rede_do_documento({}, {}) == "grupo_x"

    def test_sem_rede_de_omissao_a_pilha_fica_a_parte_e_di_lo(self, monkeypatch):
        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        assert da.rede_do_documento({}, {}) == da.SEM_REDE
        assert resumir(auditar([_r("a", da.SEM_REDE, nif="200000004")]))["sem_rede_de_omissao"] is True


class TestAPrivacidade:
    def test_nif_e_telefone_mascarados(self):
        assert mascarar("nif", "200000004") == "*****0004"
        assert mascarar("telefone", "912345678") == "*****5678"

    def test_email_mascarado_mantem_o_dominio(self):
        assert mascarar("email", "ana.costa@x.pt") == "a***@x.pt"

    def test_indice_cego_nao_mostra_o_hash_inteiro(self):
        assert "abcdef0123456789" not in mascarar("nif", "nif-hash:abcdef0123456789")

    def test_valores_completos_so_a_pedido(self):
        assert da.mostrar("nif", "200000004", valores_completos=False) != "200000004"
        assert da.mostrar("nif", "200000004", valores_completos=True) == "200000004"

    def test_o_resumo_nunca_leva_valores(self):
        rel = auditar([_r("a", nif="200000004"), _r("b", nif="200000004")])
        assert "200000004" not in repr(resumir(rel))


def _chamadas(caminho: Path) -> set[str]:
    """Tudo o que o ficheiro CHAMA (`db.clients.find`, `max_time_ms`…), por AST.

    Por AST e não por texto: a docstring do script explica o que ele NÃO faz e
    cita esses nomes — uma guarda que a lesse proibia a própria explicação.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    return {ast.unparse(n.func) for n in ast.walk(arvore) if isinstance(n, ast.Call)}


def _literais(caminho: Path) -> set[str]:
    """Literais de texto que NÃO são docstrings (operadores `$set`, nomes de colunas…)."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    docstrings = {
        id(n.body[0].value) for n in ast.walk(arvore)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
    }
    return {
        n.value for n in ast.walk(arvore)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    }


ESCRITAS = {
    "insert_one", "insert_many", "update_one", "update_many", "delete_one", "delete_many",
    "replace_one", "bulk_write", "find_one_and_update", "find_one_and_delete",
    "find_one_and_replace", "drop", "drop_collection", "create_index", "create_indexes",
    "rename", "save",
}
OPERADORES_DE_ESCRITA = {"$set", "$unset", "$inc", "$push", "$pull", "$out", "$merge", "$setOnInsert"}


class TestOScriptSoLe:
    def test_nenhuma_operacao_de_escrita(self):
        for caminho in (SCRIPT, Path(da.__file__)):
            chamadas = {c.rsplit(".", 1)[-1] for c in _chamadas(caminho)}
            assert not (chamadas & ESCRITAS), f"{caminho.name} passou a escrever: {chamadas & ESCRITAS}"
            assert not (_literais(caminho) & OPERADORES_DE_ESCRITA), f"{caminho.name} usa um operador de escrita"

    def test_o_modulo_puro_nem_importa_a_base_de_dados(self):
        arvore = ast.parse(Path(da.__file__).read_text(encoding="utf-8"))
        importados = {
            (n.module if isinstance(n, ast.ImportFrom) else a.name)
            for n in ast.walk(arvore) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [None])
        }
        assert "database" not in importados and not any((m or "").startswith("motor") for m in importados)

    def test_contraprova_o_script_le_mesmo_clientes_empresas_e_processos(self):
        """Sem isto, apagar o script inteiro satisfazia as guardas acima."""
        chamadas = _chamadas(SCRIPT)
        assert "db.clients.find" in chamadas
        assert "db.companies.find" in chamadas
        assert "db.processes.aggregate" in chamadas
        assert chamadas & ESCRITAS == set()

    def test_contraprova_o_detector_apanha_uma_escrita(self, tmp_path):
        falso = tmp_path / "falso.py"
        falso.write_text('await db.clients.update_one({}, {"$set": {"a": 1}})\n')
        assert "db.clients.update_one" in _chamadas(falso)
        assert "$set" in _literais(falso)

    def test_nao_ha_bandeira_de_escrita(self):
        arvore = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        bandeiras = [
            n.args[0].value for n in ast.walk(arvore)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_argument"
            and n.args and isinstance(n.args[0], ast.Constant)
        ]
        assert bandeiras, "o leitor de argumentos não leu nada"
        assert set(bandeiras) == {"--limite-exemplos", "--csv", "--dados-pessoais"}

    def test_corre_contra_producao_de_proposito(self):
        assert not any("require_non_production_db" in c for c in _chamadas(SCRIPT))

    def test_as_leituras_tem_tecto_de_tempo(self):
        chamadas = _chamadas(SCRIPT)
        assert sum(c.endswith("max_time_ms") for c in chamadas) >= 2
        assert any(k.arg == "maxTimeMS" for n in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8")))
                   if isinstance(n, ast.Call) for k in n.keywords)
