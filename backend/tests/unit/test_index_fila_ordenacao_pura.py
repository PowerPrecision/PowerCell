"""Regras PURAS da ordenação e dos filtros da fila do Index (Out 2026) + a ligação da rota.

A semântica contra dados reais (colação, `$nor`, paginação estável) está em
`tests/integration/test_index_fila_ordenacao_e_filtros_mongo.py`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from services import index_queue_query as q
from services.tenant_network import TenantScope, build_network_scope_condition

SCOPE = TenantScope(network_ids=("rede-A",))


class TestOrdenacao:
    def test_omissao_por_aba(self):
        assert q.validar_ordenacao("pending", None)[3] == "created_asc"
        assert q.validar_ordenacao("reviews", "")[3] == "indexed_desc"

    def test_campo_sentido_e_texto(self):
        assert q.validar_ordenacao("pending", "client_desc") == ("client_name", -1, True, "client_desc")
        assert q.validar_ordenacao("pending", "alerts_asc") == ("index_alerts_open", 1, False, "alerts_asc")
        assert q.validar_ordenacao("pending", "number_asc")[2] is True

    def test_o_nome_do_campo_mongo_nunca_sai_do_pedido(self):
        for malicioso in ("process_number_asc", "$where_asc", "client_name_asc", "created_at_asc", "_id_asc"):
            with pytest.raises(HTTPException) as e:
                q.validar_ordenacao("pending", malicioso)
            assert e.value.status_code == 422, malicioso

    @pytest.mark.parametrize("valor", ["client", "client_", "_asc", "client_up", "CLIENT_ASC", "client_asc ", "client asc"])
    def test_formas_invalidas_sao_422(self, valor):
        if valor == "client_asc ":
            assert q.validar_ordenacao("pending", valor)[3] == "client_asc"  # aparado
            return
        with pytest.raises(HTTPException) as e:
            q.validar_ordenacao("pending", valor)
        assert e.value.status_code == 422

    def test_indexed_so_nas_revisoes(self):
        assert q.validar_ordenacao("reviews", "indexed_asc")[0] == "indexed_at"
        with pytest.raises(HTTPException):
            q.validar_ordenacao("pending", "indexed_asc")

    def test_ha_sempre_desempate_por_id(self):
        assert q.ordem_mongo("client_name", -1) == [("client_name", -1), ("id", 1)]

    def test_a_colacao_tem_acentos_maiusculas_e_numeros(self):
        assert q.COLACAO == {"locale": "pt", "strength": 2, "numericOrdering": True}


class TestFiltros:
    def test_sem_filtros_nao_ha_condicao(self):
        f = q.validar_filtros("pending", index_status=None, company_id="", origin=" ")
        assert f == {"index_status": None, "company_id": None, "origin": None}
        assert q.condicao_dos_filtros("pending", f, SCOPE) is None

    def test_estado_pending_inclui_o_legado_sem_index_status(self):
        f = q.validar_filtros("pending", index_status="pending", company_id=None, origin=None)
        assert q.condicao_dos_filtros("pending", f, SCOPE) == {
            "$or": [{"index_status": "pending"}, {"index_status": {"$exists": False}}]
        }

    def test_estado_em_tratamento_nao_inclui_o_legado(self):
        f = q.validar_filtros("pending", index_status="in_review", company_id=None, origin=None)
        assert q.condicao_dos_filtros("pending", f, SCOPE) == {"$or": [{"index_status": "in_review"}]}

    def test_nas_revisoes_o_estado_indexado_nao_acrescenta_condicao(self):
        f = q.validar_filtros("reviews", index_status="indexed", company_id=None, origin=None)
        assert q.condicao_dos_filtros("reviews", f, SCOPE) is None

    @pytest.mark.parametrize("aba,estado", [("pending", "indexed"), ("reviews", "pending"), ("reviews", "in_review"), ("pending", "x"), ("xyz", "pending")])
    def test_estado_que_a_aba_nao_tem_e_422(self, aba, estado):
        with pytest.raises(HTTPException) as e:
            q.validar_filtros(aba, index_status=estado, company_id=None, origin=None)
        assert e.value.status_code == 422

    def test_empresa_e_exacta_e_tem_tecto(self):
        f = q.validar_filtros("pending", index_status=None, company_id=" c1 ", origin=None)
        assert q.condicao_dos_filtros("pending", f, SCOPE) == {"company_id": "c1"}
        with pytest.raises(HTTPException):
            q.validar_filtros("pending", index_status=None, company_id="x" * 65, origin=None)

    def test_a_empresa_nunca_e_uma_expressao(self):
        """Valor com operadores é texto: vai como igualdade, nunca como `{"$ne": …}`."""
        f = q.validar_filtros("pending", index_status=None, company_id='{"$ne": null}', origin=None)
        assert q.condicao_dos_filtros("pending", f, SCOPE) == {"company_id": '{"$ne": null}'}

    def test_origem(self):
        propria = build_network_scope_condition(SCOPE)
        own = q.validar_filtros("pending", index_status=None, company_id=None, origin="own")
        shared = q.validar_filtros("pending", index_status=None, company_id=None, origin="shared")
        assert q.condicao_dos_filtros("pending", own, SCOPE) == propria
        assert q.condicao_dos_filtros("pending", shared, SCOPE) == {"$nor": [propria]}
        with pytest.raises(HTTPException):
            q.validar_filtros("pending", index_status=None, company_id=None, origin="todas")

    def test_sem_fronteira_nada_e_de_outra_rede(self):
        master = TenantScope(sem_fronteira=True)
        shared = q.validar_filtros("pending", index_status=None, company_id=None, origin="shared")
        assert q.condicao_dos_filtros("pending", shared, master) == {"id": {"$in": []}}

    def test_varios_filtros_juntam_se_com_and(self):
        f = q.validar_filtros("pending", index_status="in_review", company_id="c1", origin="own")
        cond = q.condicao_dos_filtros("pending", f, SCOPE)
        assert len(cond["$and"]) == 3


class TestARota:
    def _funcao(self):
        fonte = (Path(__file__).resolve().parents[2] / "routes" / "index_module.py").read_text(encoding="utf-8")
        return next(n for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_index_queue")

    def test_a_rota_declara_e_passa_os_quatro_parametros(self):
        f = self._funcao()
        nomes = {a.arg for a in f.args.args}
        assert {"sort_by", "index_status", "company_id", "origin"} <= nomes
        corpo = ast.unparse(f)
        for par in ("sort_by=sort_by", "index_status=index_status", "company_id=company_id", "origin=origin"):
            assert par in corpo

    def test_o_servico_valida_antes_de_tocar_na_base_de_dados(self):
        fonte = (Path(__file__).resolve().parents[1] / ".." / "services" / "index_api.py").resolve().read_text(encoding="utf-8")
        corpo = fonte[fonte.index("async def run_get_index_queue("):]
        assert corpo.index("validar_ordenacao") < corpo.index("resolve_vista_scope") < corpo.index("count_documents")
        assert corpo.index("validar_filtros") < corpo.index("resolve_vista_scope")

    def test_a_ordem_vai_com_desempate_e_a_colacao_so_em_texto(self):
        fonte = (Path(__file__).resolve().parents[2] / "services" / "index_api.py").read_text(encoding="utf-8")
        corpo = fonte[fonte.index("async def run_get_index_queue("):]
        assert "ordem_mongo(campo, sentido)" in corpo
        assert "if e_texto" in corpo and ".collation(" in corpo
