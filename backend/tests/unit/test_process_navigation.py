"""
Ponto 17 — Navegação Contígua (Anterior/Seguinte nos Detalhes).

O risco desta funcionalidade não é falhar: é acertar por pouco. Uma
seta que leve ao processo errado não dá erro, não deixa rasto e ninguém
desconfia dela — o utilizador só percebe quando já editou a ficha
errada. Por isso os testes aqui atacam duas coisas acima de tudo:

  1. que a query é a MESMA da listagem (filtros e isolamento por Rede
     incluídos), e não um construtor paralelo como o do Kanban;
  2. que a ORDEM é a mesma da listagem — que é ordenada em Python, não
     no Mongo, e que a projecção mínima deste endpoint não a altera.
"""
import ast
import pytest
from unittest.mock import patch

from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
from services.process_navigation import (
    PROCESS_NAV_PROJECTION,
    vizinhos_na_lista,
    run_get_process_neighbours,
)
from services.process_list_enrichment import sort_process_list


# ====================================================================
# vizinhos_na_lista — puro
# ====================================================================

class TestVizinhosNaLista:
    def test_meio_da_lista_tem_os_dois_lados(self):
        r = vizinhos_na_lista(["a", "b", "c"], "b")
        assert r["previous_id"] == "a"
        assert r["next_id"] == "c"
        assert r["position"] == 2
        assert r["total"] == 3

    def test_primeiro_nao_tem_anterior(self):
        r = vizinhos_na_lista(["a", "b", "c"], "a")
        assert r["previous_id"] is None
        assert r["next_id"] == "b"
        assert r["position"] == 1

    def test_ultimo_nao_tem_seguinte(self):
        r = vizinhos_na_lista(["a", "b", "c"], "c")
        assert r["previous_id"] == "b"
        assert r["next_id"] is None
        assert r["position"] == 3

    def test_lista_de_um_nao_tem_nenhum(self):
        r = vizinhos_na_lista(["a"], "a")
        assert r["previous_id"] is None
        assert r["next_id"] is None
        assert r["position"] == 1
        assert r["total"] == 1

    def test_processo_fora_da_lista_nao_inventa_posicao(self):
        # Pode ter mudado de estado e saído do filtro entre a listagem e
        # o clique. Dar-lhe uma posição seria mentir sobre o conjunto.
        r = vizinhos_na_lista(["a", "b"], "z")
        assert r["previous_id"] is None
        assert r["next_id"] is None
        assert r["position"] is None
        assert r["total"] == 2

    def test_lista_vazia_ou_nula_nao_rebenta(self):
        for vazio in ([], None):
            r = vizinhos_na_lista(vazio, "a")
            assert r["position"] is None
            assert r["total"] == 0

    def test_ids_nulos_sao_descartados_antes_de_contar(self):
        # Um `None` no meio corria o risco de deslocar a posição em um e
        # de a seta apontar sempre uma casa ao lado.
        r = vizinhos_na_lista(["a", None, "b", "", "c"], "b")
        assert r["previous_id"] == "a"
        assert r["next_id"] == "c"
        assert r["position"] == 2
        assert r["total"] == 3


# ====================================================================
# A projecção mínima não pode mudar a ordem
# ====================================================================

def _processo(i, **extra):
    doc = {
        "id": f"p{i}",
        "client_name": f"Cliente {chr(90 - i)}",
        "client_email": f"c{i}@exemplo.pt",
        "client_phone": f"9100000{i:02d}",
        "status": ["cpcv", "fase_bancaria", "clientes_espera"][i % 3],
        # Os DOIS campos de prioridade alternam de propósito: o produto
        # guarda uns processos com `prioridade` (PT) e outros com
        # `priority` (EN), e `get_priority_weight` lê os dois. Uma
        # amostra só com um deles deixava passar uma projecção a que
        # faltasse o outro — foi uma mutação sobrevivente que o mostrou.
        **(
            {"prioridade": ["alta", "media", "baixa"][i % 3]}
            if i % 2 == 0
            else {"priority": ["media", "alta", "baixa"][i % 3]}
        ),
        "property_value": 100000 + (i * 1000),
        "property_location": f"Zona {i % 4}",
        "created_at": f"2026-0{(i % 9) + 1}-01T00:00:00",
        "updated_at": f"2026-0{(i % 9) + 1}-15T00:00:00",
        # Campos PESADOS que a listagem traz e este endpoint não deve:
        "documents": ["a" * 200],
        "observation_notes": [{"text": "x" * 500}],
        "credit_data": {"montante": 1},
    }
    doc.update(extra)
    return doc


class TestProjeccaoPreservaAOrdem:
    """
    A prova de que `PROCESS_NAV_PROJECTION` é suficiente.

    Não é uma guarda sobre a lista de campos (essa envelhece mal): é a
    ordenação REAL aplicada aos documentos completos e aos documentos
    reduzidos à projecção, com a exigência de darem a mesma sequência.
    Acrescentar um campo ao ordenador sem o acrescentar aqui fica
    vermelho.
    """

    CAMPOS = tuple(k for k in PROCESS_NAV_PROJECTION if k != "_id")

    @pytest.mark.parametrize("sort_field", [
        None, "client_name", "status", "created_at", "updated_at",
        "priority", "property_value", "property_location", "contacto",
    ])
    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    def test_mesma_ordem_com_e_sem_projeccao(self, sort_field, sort_order):
        completos = [_processo(i) for i in range(12)]
        reduzidos = [
            {k: v for k, v in p.items() if k in self.CAMPOS}
            for p in completos
        ]
        status_order = {"clientes_espera": 0, "fase_bancaria": 1, "cpcv": 2}

        sort_process_list(
            completos, sort_field=sort_field,
            sort_order=sort_order, status_order=status_order,
        )
        sort_process_list(
            reduzidos, sort_field=sort_field,
            sort_order=sort_order, status_order=status_order,
        )

        assert [p["id"] for p in completos] == [p["id"] for p in reduzidos]

    def test_a_projeccao_nao_traz_os_campos_pesados(self):
        # O ponto do endpoint é devolver ids, não processos. Se a
        # projecção crescesse para o `PROCESS_LIST_PROJECTION`, deixava
        # de ser barato e a Camada 3 perdia a razão de existir.
        for pesado in ("documents", "observation_notes", "credit_data", "notes"):
            assert pesado not in PROCESS_NAV_PROJECTION


# ====================================================================
# run_get_process_neighbours — com a base de dados falsa
# ====================================================================

def _sem_decifrar(docs, fields_to_decrypt=None):
    return docs


@pytest.fixture
def db_com_processos(fake_async_db):
    for i in range(6):
        fake_async_db.processes.docs.append(_processo(i))
    return fake_async_db


class TestRunGetProcessNeighbours:

    async def _correr(self, fake_db, process_id, **kwargs):
        import services.process_navigation as nav
        with patch.object(nav, "db", fake_db), \
             patch.object(nav, "build_tenant_condition", return_value={}), \
             patch.object(nav, "load_workflow_status_order", return_value={}):
            return await run_get_process_neighbours(
                user={"id": "u1", "role": "admin"},
                role="admin",
                process_id=process_id,
                decrypt_list_fn=_sem_decifrar,
                show_all=True,
                view_mode="all",
                **kwargs,
            )

    @pytest.mark.asyncio
    async def test_devolve_os_vizinhos_pela_ordem_da_listagem(self, db_com_processos):
        esperado = [_processo(i) for i in range(6)]
        sort_process_list(esperado, sort_field="client_name", sort_order="asc")
        ids = [p["id"] for p in esperado]
        alvo = ids[2]

        r = await self._correr(
            db_com_processos, alvo,
            sort_field="client_name", sort_order="asc",
        )

        assert r["previous_id"] == ids[1]
        assert r["next_id"] == ids[3]
        assert r["position"] == 3
        assert r["total"] == 6

    @pytest.mark.asyncio
    async def test_a_ordem_inversa_troca_os_vizinhos(self, db_com_processos):
        asc = await self._correr(
            db_com_processos, "p2", sort_field="client_name", sort_order="asc",
        )
        desc = await self._correr(
            db_com_processos, "p2", sort_field="client_name", sort_order="desc",
        )
        # Contraprova de que o `sort_order` é mesmo usado: se fosse
        # ignorado, os dois lados seriam iguais.
        assert asc["previous_id"] != desc["previous_id"]
        assert asc["position"] != desc["position"]
        assert asc["total"] == desc["total"] == 6

        # E a posição é a que a ordenação da LISTAGEM dá — não uma
        # aritmética minha. (As duas ordens não são espelhos exactos:
        # `sort_process_list` aplica um segundo sort, estável, por peso
        # de prioridade, que domina o campo escolhido.)
        for sentido, resultado in (("asc", asc), ("desc", desc)):
            esperado = [_processo(i) for i in range(6)]
            sort_process_list(
                esperado, sort_field="client_name", sort_order=sentido,
            )
            ids = [p["id"] for p in esperado]
            assert resultado["position"] == ids.index("p2") + 1

    @pytest.mark.asyncio
    async def test_o_filtro_de_estado_muda_quem_e_o_vizinho(self, db_com_processos):
        # O vizinho é o vizinho DENTRO do filtro aberto. Ignorar o filtro
        # saltaria para um processo que o utilizador nem está a ver.
        r = await self._correr(
            db_com_processos, "p0", status="cpcv", sort_field="client_name",
        )
        assert r["total"] == 2  # p0 e p3 partilham o estado "cpcv"
        assert r["next_id"] in (None, "p3")
        assert r["previous_id"] in (None, "p3")

    @pytest.mark.asyncio
    async def test_processo_fora_do_ambito_devolve_404(self, db_com_processos):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await self._correr(db_com_processos, "processo-de-outra-rede")
        assert exc.value.status_code == 404
        # 404 e não 403: confirmar que o id existe revelaria processos
        # da rede do lado.
        assert "não encontrado" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_um_unico_processo_no_ambito_nao_tem_setas(self, fake_async_db):
        fake_async_db.processes.docs.append(_processo(0))
        r = await self._correr(fake_async_db, "p0")
        assert r["previous_id"] is None
        assert r["next_id"] is None
        assert r["position"] == 1


# ====================================================================
# Guardas sobre o código-fonte — e as suas contraprovas
# ====================================================================

class TestNaoHaConstrutorParalelo:
    """
    O Kanban teve um construtor de query só dele e ficou meses fora do
    isolamento por Rede (Lote 4, fechado no Lote 5). Este endpoint é a
    terceira superfície a listar processos: se reconstruísse a query à
    mão, repetiria o mesmo defeito com outro nome.
    """

    def test_usa_o_construtor_da_listagem(self):
        fonte = codigo_da_funcao_sem_comentarios(run_get_process_neighbours)
        assert "build_process_list_query" in fonte

    def test_aplica_o_isolamento_por_rede(self):
        fonte = codigo_da_funcao_sem_comentarios(run_get_process_neighbours)
        assert "build_tenant_condition" in fonte
        assert "tenant_condition=tenant_condition" in fonte.replace(" ", "")

    def test_ordena_com_a_funcao_da_listagem(self):
        fonte = codigo_da_funcao_sem_comentarios(run_get_process_neighbours)
        assert "sort_process_list" in fonte

    def test_contraprova_o_modulo_nao_constroi_query_a_mao(self):
        # Sem esta contraprova, apagar a chamada e escrever
        # `{"is_deleted": {"$ne": True}}` à mão satisfazia as guardas de
        # cima… desde que a chamada continuasse algures. Aqui exigimos
        # que NÃO existam operadores Mongo crus no módulo.
        fonte = open("services/process_navigation.py").read()
        arvore = ast.parse(fonte)
        literais = [
            n.value for n in ast.walk(arvore)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        operadores = [s for s in literais if s.startswith("$")]
        assert not operadores, f"query construída à mão: {operadores}"
