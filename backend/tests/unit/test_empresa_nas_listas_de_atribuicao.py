"""
A empresa de cada pessoa nas listas de atribuição (QA, Out 2026).

Quem atribui um processo precisa de saber a que EMPRESA pertence cada pessoa da lista
(atribuições B2B, pessoas com acesso a mais do que uma empresa). O servidor calcula a etiqueta
ao servir (nunca gravada), com os UCRs como fonte canónica, restrita às empresas do ÂMBITO de quem
pede — uma pessoa com acesso a duas redes não revela a quem pertence a uma delas o nome da outra.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import user_company_labels as rotulos
from services import users_api_list
from services.admin_users_scope import EmpresasDoAmbito
from services.user_company_labels import (
    MAXIMO_NA_ETIQUETA,
    anexar_empresas,
    empresas_do_utilizador,
    formatar_etiqueta,
)

AMBITO_PRECISION = EmpresasDoAmbito(ids=["c-precision"], nomes=["Precision"])
SEM_FRONTEIRA = EmpresasDoAmbito(sem_fronteira=True)


def _ucr(user_id, company_id, nome):
    return {"user_id": user_id, "company_id": company_id, "company_name": nome, "role": "consultor"}


class TestFormatarEtiqueta:
    def test_uma_empresa(self):
        assert formatar_etiqueta(["Power"]) == "Power"

    def test_varias_empresas(self):
        assert formatar_etiqueta(["Power", "Precision"]) == "Power · Precision"

    def test_resume_acima_do_limite(self):
        nomes = [f"E{i}" for i in range(MAXIMO_NA_ETIQUETA + 2)]
        assert formatar_etiqueta(nomes).endswith("+2")

    def test_exactamente_no_limite_nao_resume(self):
        nomes = [f"E{i}" for i in range(MAXIMO_NA_ETIQUETA)]
        assert "+" not in formatar_etiqueta(nomes)

    def test_vazio(self):
        assert formatar_etiqueta([]) == ""
        assert formatar_etiqueta(["", None]) == ""


class TestEmpresasDoUtilizador:
    def test_os_ucr_sao_a_fonte(self):
        ucrs = [_ucr("u", "c-precision", "Precision")]
        assert empresas_do_utilizador({"id": "u"}, ucrs, ambito=AMBITO_PRECISION) == ["Precision"]

    def test_so_se_mostram_empresas_do_ambito_de_quem_pede(self):
        # A pessoa tem acesso a Precision E Power; quem pede só alcança a Precision.
        ucrs = [_ucr("u", "c-precision", "Precision"), _ucr("u", "c-power", "Power")]
        assert empresas_do_utilizador({"id": "u"}, ucrs, ambito=AMBITO_PRECISION) == ["Precision"]

    def test_o_master_sem_fronteira_ve_todas(self):
        ucrs = [_ucr("u", "c-precision", "Precision"), _ucr("u", "c-power", "Power")]
        assert empresas_do_utilizador({"id": "u"}, ucrs, ambito=SEM_FRONTEIRA) == ["Power", "Precision"]

    def test_o_ucr_antigo_so_com_nome_casa_pelo_nome(self):
        ucrs = [{"user_id": "u", "company_name": "Precision"}]
        assert empresas_do_utilizador({"id": "u"}, ucrs, ambito=AMBITO_PRECISION) == ["Precision"]

    def test_sem_ucr_usa_o_nome_legado_no_utilizador(self):
        utilizador = {"id": "u", "company": "Precision"}
        assert empresas_do_utilizador(utilizador, [], ambito=AMBITO_PRECISION) == ["Precision"]

    def test_o_nome_legado_fora_do_ambito_nao_aparece(self):
        utilizador = {"id": "u", "company": "Power"}
        assert empresas_do_utilizador(utilizador, [], ambito=AMBITO_PRECISION) == []

    def test_o_legado_nao_se_soma_aos_ucr(self):
        utilizador = {"id": "u", "company": "Power"}
        ucrs = [_ucr("u", "c-precision", "Precision")]
        assert empresas_do_utilizador(utilizador, ucrs, ambito=SEM_FRONTEIRA) == ["Precision"]

    def test_sem_nada_devolve_vazio(self):
        assert empresas_do_utilizador({"id": "u"}, [], ambito=SEM_FRONTEIRA) == []

    def test_deduplica_a_mesma_empresa_com_dois_perfis(self):
        ucrs = [_ucr("u", "c-precision", "Precision"), _ucr("u", "c-precision", "Precision")]
        assert empresas_do_utilizador({"id": "u"}, ucrs, ambito=AMBITO_PRECISION) == ["Precision"]

    def test_ordem_estavel_sem_distinguir_maiusculas(self):
        ucrs = [_ucr("u", "b", "beta"), _ucr("u", "a", "Alfa")]
        assert empresas_do_utilizador({"id": "u"}, ucrs, ambito=SEM_FRONTEIRA) == ["Alfa", "beta"]


class TestAnexarEmpresas:
    @pytest.mark.asyncio
    async def test_junta_empresas_e_etiqueta_com_uma_so_consulta(self, fake_async_db):
        await fake_async_db.user_company_roles.insert_many([
            _ucr("u-1", "c-precision", "Precision"),
            _ucr("u-1", "c-power", "Power"),
            _ucr("u-2", "c-precision", "Precision"),
        ])
        utilizadores = [{"id": "u-1", "name": "Ana"}, {"id": "u-2", "name": "Rui"}, {"id": "u-3"}]
        with patch.object(rotulos, "db", fake_async_db):
            resultado = await anexar_empresas(utilizadores, ambito=AMBITO_PRECISION)

        por_id = {u["id"]: u for u in resultado}
        assert por_id["u-1"]["empresas"] == ["Precision"]
        assert por_id["u-1"]["empresa_etiqueta"] == "Precision"
        assert por_id["u-2"]["empresa_etiqueta"] == "Precision"
        assert por_id["u-3"]["empresas"] == []
        assert por_id["u-3"]["empresa_etiqueta"] == ""

    @pytest.mark.asyncio
    async def test_a_consulta_aos_ucr_e_unica_e_so_pergunta_pelos_utilizadores_da_lista(
        self, fake_async_db
    ):
        # Uma consulta por lista (não por utilizador) e nunca a colecção inteira.
        original = fake_async_db.user_company_roles.find
        pedidos = []

        def espia(filtro, *args, **kwargs):
            pedidos.append(filtro)
            return original(filtro, *args, **kwargs)

        with patch.object(rotulos, "db", fake_async_db), \
             patch.object(fake_async_db.user_company_roles, "find", espia):
            await anexar_empresas(
                [{"id": "u-1"}, {"id": "u-2"}, {"id": "u-3"}], ambito=SEM_FRONTEIRA
            )

        assert len(pedidos) == 1
        assert set(pedidos[0]["user_id"]["$in"]) == {"u-1", "u-2", "u-3"}

    @pytest.mark.asyncio
    async def test_o_master_ve_as_duas(self, fake_async_db):
        await fake_async_db.user_company_roles.insert_many([
            _ucr("u-1", "c-precision", "Precision"), _ucr("u-1", "c-power", "Power"),
        ])
        with patch.object(rotulos, "db", fake_async_db):
            [u] = await anexar_empresas([{"id": "u-1"}], ambito=SEM_FRONTEIRA)
        assert u["empresa_etiqueta"] == "Power · Precision"

    @pytest.mark.asyncio
    async def test_nunca_levanta_e_a_lista_segue_intacta(self):
        bd = type("BD", (), {})()
        bd.user_company_roles = type("C", (), {"find": lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x"))})()
        with patch.object(rotulos, "db", bd):
            utilizadores = [{"id": "u-1", "name": "Ana"}]
            resultado = await anexar_empresas(utilizadores, ambito=SEM_FRONTEIRA)
        assert resultado == [{"id": "u-1", "name": "Ana"}]

    @pytest.mark.asyncio
    async def test_lista_vazia(self):
        assert await anexar_empresas([], ambito=SEM_FRONTEIRA) == []


class TestAListaDeUtilizadoresLevaAEtiqueta:
    """Comportamento ponta a ponta do serviço da rota `/users` e `/users/staff`."""

    @pytest.mark.asyncio
    async def test_a_lista_de_atribuicao_sai_com_a_empresa(self, fake_async_db):
        await fake_async_db.users.insert_many([
            {"id": "u-1", "name": "Ana", "role": "consultor", "is_active": True, "company": "Precision"},
            {"id": "u-2", "name": "Rui", "role": "intermediario", "is_active": True},
        ])
        await fake_async_db.user_company_roles.insert_many([
            _ucr("u-1", "c-precision", "Precision"), _ucr("u-1", "c-power", "Power"),
        ])
        with patch.object(users_api_list, "db", fake_async_db), \
             patch.object(rotulos, "db", fake_async_db), \
             patch("services.admin_users_scope.empresas_do_ambito", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch("services.admin_users_scope.build_users_scope_query", AsyncMock(return_value={})):
            lista = await users_api_list.run_get_users(None, {"id": "quem-pede", "role": "diretor"})

        ana = next(u for u in lista if u["id"] == "u-1")
        assert ana["empresa_etiqueta"] == "Precision"  # a Power fica de fora: não é do âmbito
        assert all("empresa_etiqueta" in u for u in lista)

    def test_a_ligacao_existe_no_servico_da_lista(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(users_api_list.run_get_users)
        assert "anexar_empresas(users, ambito=ambito)" in corpo
