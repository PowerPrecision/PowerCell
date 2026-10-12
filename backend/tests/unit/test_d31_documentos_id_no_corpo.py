"""D-31 (remate) — o `process_id` que não vem no caminho: corpo JSON e query.

O QUE ESTAVA ABERTO
===================
O router `/documents` ganhou, no fecho da D-31, guardas para o que vem no
CAMINHO (`{process_id}`, `{client_id}`, `{doc_id}`). Ficaram por baixo de
qualquer dependência de caminho as rotas que levam o id no CORPO:

* `check-upload-conflict`, `generate-upload-url`, `confirm-upload` — só tinham a
  guarda de visibilidade/escrita DENTRO do serviço (403, que confirma o id);
* `check-move-conflict` — **nenhuma guarda e nem recebia o utilizador**: era
  «este ficheiro existe?» sobre a pasta de qualquer processo;
* `search` — com `process_id` tinha a guarda de visibilidade; **sem** `process_id`
  percorria os metadados de documentos de TODAS as redes e devolvia URLs
  pré-assinados;
* e, da mesma forma, `POST /expiry` (corpo) e `GET /categories`/`GET /expiry`
  (query).

COMO SE TESTA
=============
Os routers REAIS por HTTP, com os `run_*` como sentinelas: o ataque exige que o
handler NUNCA seja chamado. Onde o objecto é o serviço (a pesquisa sem
`process_id`, o `check-move-conflict`) corre-se o serviço real sobre a BD falsa.
"""
from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tests.unit.helpers_tenant import (  # noqa: F401  (fixtures)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,
    rede_de_omissao_incumbente,
    tenant_db,
)
from tests.unit.test_d31_documentos_tasklogs_portal import (
    SESSOES,
    _cenario_docs,
)

DETALHE = {"sentinela": "handler chamado"}
#: Os dois `/expiry` têm `response_model`: a sentinela tem de o cumprir, senão o
#: 500 da validação da resposta mascarava o que o teste mede.
RESPOSTAS = {
    "run_create_document_expiry": {
        "id": "e1", "process_id": "p", "document_type": "cc", "document_name": "CC",
        "expiry_date": "2030-01-01", "created_at": "2026-01-01", "created_by": "u",
    },
    "run_get_document_expiries": [],
}
NAO_ENCONTRADO = "Processo não encontrado"

HANDLERS = [
    "run_check_upload_conflict", "run_generate_upload_url", "run_confirm_upload",
    "run_check_move_conflict", "run_search_documents", "run_get_all_categories",
    "run_create_document_expiry", "run_get_document_expiries",
]

#: nome → (método, caminho, como o `process_id` viaja, handler que NÃO pode correr)
ROTAS = {
    "check-upload-conflict": ("post", "/documents/check-upload-conflict",
                              {"filenames": ["a.pdf"]}, "run_check_upload_conflict"),
    "generate-upload-url": ("post", "/documents/generate-upload-url",
                            {"filename": "a.pdf", "content_type": "application/pdf"},
                            "run_generate_upload_url"),
    "confirm-upload": ("post", "/documents/confirm-upload",
                       {"file_key": "k", "original_filename": "a.pdf", "category": "Outros"},
                       "run_confirm_upload"),
    "check-move-conflict": ("post", "/documents/check-move-conflict",
                            {"source_path": "x/a.pdf"}, "run_check_move_conflict"),
    "search": ("post", "/documents/search", {"query": "cartao"}, "run_search_documents"),
    "expiry-create": ("post", "/documents/expiry",
                      {"document_type": "cc", "document_name": "CC", "expiry_date": "2030-01-01"},
                      "run_create_document_expiry"),
}
ROTAS_DE_QUERY = {
    "categories": ("/documents/categories", "run_get_all_categories"),
    "expiry-list": ("/documents/expiry", "run_get_document_expiries"),
}
ROTAS_DE_CORPO = list(ROTAS)


@pytest.fixture
def corpo(fake_async_db, rede_de_omissao_incumbente):  # noqa: F811
    import routes.documents as rd
    import services.auth as auth_mod
    import services.by_id_scope as guard
    import services.document_process_resolve as dpr
    import services.document_queries as dq
    import services.document_visibility as dv
    import services.process_closed_guard as pcg
    import services.process_scope_guard as psg
    from services.auth import get_current_user

    _cenario_docs(fake_async_db)
    atual = {"user": SESSOES["ana"]}
    chamadas: dict[str, AsyncMock] = {}

    app = FastAPI()
    app.include_router(rd.router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]

    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, guard, auth_mod, psg, pcg, rd, dpr, dv, dq))
        for nome in HANDLERS:
            chamadas[nome] = AsyncMock(return_value=RESPOSTAS.get(nome, DETALHE))
            pilha.enter_context(patch.object(rd, nome, chamadas[nome]))
        cliente = TestClient(app)

        def como(quem: str):
            atual["user"] = SESSOES[quem]
            return cliente

        yield como, chamadas, fake_async_db


def _pedir(cliente, rota: str, process_id):
    metodo, caminho, base, _ = ROTAS[rota]
    return getattr(cliente, metodo)(caminho, json={"process_id": process_id, **base})


def _nenhum_handler_correu(chamadas) -> bool:
    return all(m.await_count == 0 for m in chamadas.values())


# ════════════════════════════════════════════════════════════════════
class TestOAtaqueComOProcessIdNoCorpo:
    """`TestAExploracao`: a Domus contra os processos da Power, pelo CORPO."""

    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    @pytest.mark.parametrize("alvo", ["p-pw", "c-pw", "cli-sem-ficha"])
    def test_o_Bruno_da_Domus_nao_alcanca_o_processo_da_Power(self, corpo, rota, alvo):
        como, chamadas, _ = corpo
        resposta = _pedir(como("bruno"), rota, alvo)

        assert resposta.status_code == 404, (rota, alvo, resposta.text)
        assert resposta.json()["detail"] == NAO_ENCONTRADO
        assert _nenhum_handler_correu(chamadas), {
            n: m.await_count for n, m in chamadas.items() if m.await_count
        }

    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    def test_o_CEO_da_Domus_e_local_e_tambem_nao(self, corpo, rota):
        como, chamadas, _ = corpo
        assert _pedir(como("ceo_domus"), rota, "p-pw").status_code == 404
        assert _nenhum_handler_correu(chamadas)

    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    def test_a_Power_nao_alcanca_o_da_Domus(self, corpo, rota):
        como, chamadas, _ = corpo
        assert _pedir(como("ana"), rota, "p-dm").status_code == 404
        assert _nenhum_handler_correu(chamadas)

    @pytest.mark.parametrize("rota", ["categories", "expiry-list"])
    def test_o_process_id_da_QUERY_tambem_e_um_alvo(self, corpo, rota):
        como, chamadas, _ = corpo
        caminho, _handler = ROTAS_DE_QUERY[rota]
        resposta = como("bruno").get(caminho, params={"process_id": "p-pw"})

        assert resposta.status_code == 404
        assert resposta.json()["detail"] == NAO_ENCONTRADO
        assert _nenhum_handler_correu(chamadas)

    def test_o_alheio_e_o_inexistente_nao_se_distinguem_pelo_detalhe(self, corpo):
        """O handler responde 'Processo não encontrado' a um id que não existe;
        o alheio responde o MESMO texto — a diferença seria o oráculo."""
        como, chamadas, _ = corpo
        alheio = _pedir(como("bruno"), "check-move-conflict", "p-pw")
        assert alheio.status_code == 404 and alheio.json()["detail"] == NAO_ENCONTRADO
        # (o inexistente passa a guarda e o handler — aqui sentinela — responde)
        assert _pedir(como("bruno"), "check-move-conflict", "p-nunca").status_code == 200
        assert chamadas["run_check_move_conflict"].await_count == 1


class TestOsFluxosLegitimosComOIdNoCorpo:
    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    def test_cada_rede_abre_o_seu_e_o_corpo_chega_inteiro_ao_handler(self, corpo, rota):
        """Ler o corpo na guarda não o pode consumir: o handler recebe-o inteiro."""
        como, chamadas, _ = corpo
        handler = ROTAS[rota][3]

        assert _pedir(como("ana"), rota, "p-pw").status_code == 200
        assert _pedir(como("bruno"), rota, "p-dm").status_code == 200
        assert chamadas[handler].await_count == 2
        recebido = chamadas[handler].await_args_list[0]
        corpo_recebido = recebido.args[0] if recebido.args else recebido.kwargs.get("data")
        if isinstance(corpo_recebido, dict):
            assert corpo_recebido["process_id"] == "p-pw"
        else:                                   # modelo Pydantic (search / expiry)
            assert corpo_recebido.process_id == "p-pw"

    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    def test_quem_trabalha_nas_duas_redes_abre_ambas(self, corpo, rota):
        como, _, _ = corpo
        assert _pedir(como("carla"), rota, "p-pw").status_code == 200
        assert _pedir(como("carla"), rota, "p-dm").status_code == 200

    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    def test_o_Master_abre_qualquer_um(self, corpo, rota):
        como, _, _ = corpo
        assert _pedir(como("master"), rota, "p-pw").status_code == 200
        assert _pedir(como("master"), rota, "p-dm").status_code == 200

    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    def test_o_processo_partilhado_abre_ao_convidado(self, corpo, rota):
        """D-25: a rede convidada vê o processo partilhado."""
        como, _, _ = corpo
        assert _pedir(como("bruno"), rota, "p-part").status_code == 200
        assert _pedir(como("bruno"), rota, "p-part-so").status_code == 200

    @pytest.mark.parametrize("rota", ["categories", "expiry-list"])
    def test_a_query_do_proprio_abre(self, corpo, rota):
        como, chamadas, _ = corpo
        caminho, handler = ROTAS_DE_QUERY[rota]
        assert como("bruno").get(caminho, params={"process_id": "p-dm"}).status_code == 200
        assert como("bruno").get(caminho).status_code == 200      # sem id: sem guarda
        assert chamadas[handler].await_count == 2

    def test_sem_process_id_a_guarda_nao_decide(self, corpo):
        como, chamadas, _ = corpo
        resposta = como("bruno").post("/documents/search", json={"query": "cartao"})
        assert resposta.status_code == 200
        assert chamadas["run_search_documents"].await_count == 1


class TestUmProcessIdQueNaoETextoNaoContornaAGuarda:
    """`{"$ne": null}` chegaria ao `find_one({"id": …})` do handler e devolvia o
    primeiro processo de QUALQUER rede: a guarda a ignorar o valor era a porta."""

    @pytest.mark.parametrize("rota", ROTAS_DE_CORPO)
    @pytest.mark.parametrize("injeccao", [{"$ne": None}, {"$regex": ".*"}, ["p-pw"], 7])
    def test_recusa_com_400_e_o_handler_nao_corre(self, corpo, rota, injeccao):
        como, chamadas, _ = corpo
        resposta = _pedir(como("bruno"), rota, injeccao)

        assert resposta.status_code in (400, 422), (rota, injeccao, resposta.text)
        assert _nenhum_handler_correu(chamadas)

    def test_um_corpo_ilegivel_passa_ao_422_do_FastAPI(self, corpo):
        como, chamadas, _ = corpo
        resposta = como("bruno").post(
            "/documents/check-move-conflict", content=b"{nao e json",
            headers={"content-type": "application/json"},
        )
        assert resposta.status_code == 422
        assert _nenhum_handler_correu(chamadas)

    @pytest.mark.asyncio
    async def test_um_upload_multipart_nao_e_carregado_para_memoria(self):
        """A guarda só lê JSON: o ficheiro inteiro não pode ficar em RAM antes
        do handler."""
        from services.by_id_scope import _process_id_do_corpo

        pedido = MagicMock()
        pedido.method = "POST"
        pedido.headers = {"content-type": "multipart/form-data; boundary=x"}
        pedido.json = AsyncMock(side_effect=AssertionError("leu o corpo"))
        pedido.body = AsyncMock(side_effect=AssertionError("leu o corpo"))

        assert await _process_id_do_corpo(pedido) is None
        pedido.json.assert_not_awaited()
        pedido.body.assert_not_awaited()


# ════════════════════════════════════════════════════════════════════
#  A pesquisa SEM process_id (o buraco maior)
# ════════════════════════════════════════════════════════════════════
def _semear_metadados(fake_db) -> None:
    def doc(i, pid, nome):
        return {"id": i, "process_id": pid, "filename": nome, "is_categorized": True,
                "ai_category": "Identificação", "s3_path": f"Documentação Clientes/{pid}/{nome}",
                "ai_summary": "cartao de cidadao"}

    fake_db.document_metadata.docs.extend([
        doc("m-pw", "p-pw", "cartao-power.pdf"),
        doc("m-dm", "p-dm", "cartao-domus.pdf"),
        doc("m-part", "p-part", "cartao-partilhado.pdf"),
        # Sem processo nenhum: não se prova de ninguém.
        {"id": "m-orfao", "filename": "cartao-orfao.pdf", "is_categorized": True,
         "ai_category": "Identificação", "s3_path": "x/cartao-orfao.pdf",
         "ai_summary": "cartao de cidadao"},
    ])


@pytest.fixture
def pesquisa(corpo):
    """O `run_search_documents` / `run_get_all_categories` REAIS."""
    import routes.documents as rd
    import services.document_queries as dq

    como, chamadas, fake_db = corpo
    _semear_metadados(fake_db)
    s3 = MagicMock()
    s3.get_presigned_url.side_effect = lambda caminho: f"https://s3/assinado/{caminho}"
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(patch.object(dq, "s3_service", s3))
        pilha.enter_context(patch.object(rd, "run_search_documents", dq.run_search_documents))
        pilha.enter_context(patch.object(rd, "run_get_all_categories", dq.run_get_all_categories))
        yield como


def _ids(resposta) -> set[str]:
    return {r["id"] for r in resposta.json()["results"]}


class TestAPesquisaSemProcessIdNaoAtravessaRedes:
    def test_a_Domus_so_encontra_os_seus_e_os_partilhados(self, pesquisa):
        resposta = pesquisa("bruno").post("/documents/search", json={"query": "cartao"})

        assert resposta.status_code == 200
        assert _ids(resposta) == {"m-dm", "m-part"}

    def test_nenhum_url_pre_assinado_de_outra_rede_sai(self, pesquisa):
        resposta = pesquisa("bruno").post("/documents/search", json={"query": "cartao"})
        assert "cartao-power.pdf" not in resposta.text
        assert "cartao-orfao.pdf" not in resposta.text

    def test_a_Power_so_encontra_os_seus_e_os_que_partilhou(self, pesquisa):
        resposta = pesquisa("ana").post("/documents/search", json={"query": "cartao"})
        assert _ids(resposta) == {"m-pw", "m-part"}

    def test_quem_trabalha_nas_duas_redes_ve_ambas(self, pesquisa):
        resposta = pesquisa("carla").post("/documents/search", json={"query": "cartao"})
        assert _ids(resposta) == {"m-pw", "m-dm", "m-part"}

    def test_o_Master_ve_tudo_ate_o_que_nao_tem_dono(self, pesquisa):
        resposta = pesquisa("master").post("/documents/search", json={"query": "cartao"})
        assert _ids(resposta) == {"m-pw", "m-dm", "m-part", "m-orfao"}

    def test_o_filtro_por_categoria_nao_alarga_o_ambito(self, pesquisa):
        resposta = pesquisa("bruno").post(
            "/documents/search", json={"query": "cartao", "categories": ["Identificação"]},
        )
        assert _ids(resposta) == {"m-dm", "m-part"}

    def test_as_categorias_contam_so_os_documentos_da_rede(self, pesquisa):
        bruno = pesquisa("bruno").get("/documents/categories").json()
        master = pesquisa("master").get("/documents/categories").json()

        assert bruno["categories"] == [{"name": "Identificação", "count": 2}]
        assert master["categories"] == [{"name": "Identificação", "count": 4}]


class TestOCheckMoveConflictJaNaoEUmOraculo:
    @pytest.mark.asyncio
    async def test_o_utilizador_e_obrigatorio(self):
        from services.document_move import run_check_move_conflict

        with pytest.raises(TypeError):
            await run_check_move_conflict({"process_id": "p", "source_path": "x"})

    @pytest.mark.asyncio
    async def test_a_regra_de_visibilidade_documental_vale_no_servico(self, fake_async_db,
                                                                      rede_de_omissao_incumbente):  # noqa: F811
        """Dentro da rede, um processo por indexar não é de qualquer consultor:
        o serviço aplica a mesma regra das leituras (403), não só a rede."""
        import services.document_move as dm
        import services.document_visibility as dv
        from services.document_move import run_check_move_conflict
        import services.tenant_network as tn  # noqa: F401

        _cenario_docs(fake_async_db)
        fake_async_db.processes.docs.append({
            "id": "p-dm-novo", "is_indexed": False, "client_id": "c-dm", "status": "novo",
            "network_id": REDE_DOMUS, "company_id": "cmp-domus",
        })
        nuno = {**SESSOES["bruno"], "id": "u-nuno", "role": "consultor", "effective_role": "consultor"}
        with tenant_db(fake_async_db, dm, dv):
            with pytest.raises(HTTPException) as erro:
                await run_check_move_conflict(
                    {"process_id": "p-dm-novo", "source_path": "x/a.pdf"}, user=nuno,
                )
        assert erro.value.status_code == 403


# ════════════════════════════════════════════════════════════════════
class TestAGuardaDoCorpoEstaLigada:
    def test_a_rota_entrega_o_utilizador_aos_servicos_que_o_precisam(self):
        import ast
        import inspect

        import routes.documents as rd

        fonte = inspect.getsource(rd)
        arvore = ast.parse(fonte)
        chamadas = {
            n.func.id: {k.arg for k in n.keywords}
            for n in ast.walk(arvore)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in {"run_check_move_conflict", "run_search_documents", "run_get_all_categories"}
        }
        assert chamadas == {
            "run_check_move_conflict": {"user"},
            "run_search_documents": {"user"},
            "run_get_all_categories": {"user"},
        }

    def test_toda_a_rota_com_corpo_ou_query_com_process_id_esta_sob_a_guarda(self):
        """Inventário por AST dos handlers que LÊEM `process_id` do corpo/query:
        todos vivem no router guardado, que é o único do módulo. Com
        contraprova: o inventário encontra as rotas conhecidas."""
        import ast
        import inspect

        import routes.documents as rd

        arvore = ast.parse(inspect.getsource(rd))
        leem = set()
        for no in ast.walk(arvore):
            if not isinstance(no, ast.AsyncFunctionDef):
                continue
            sub = ast.dump(no)
            corpo_ou_query = any(
                a.arg in {"data", "request"} or a.arg == "process_id"
                for a in no.args.args
            )
            if corpo_ou_query and "process_id" in sub:
                for d in no.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) \
                            and d.func.attr in {"get", "post", "put", "patch", "delete"}:
                        leem.add(d.args[0].value)
        assert {"/check-upload-conflict", "/generate-upload-url", "/confirm-upload",
                "/check-move-conflict", "/search", "/categories", "/expiry"} <= leem
        assert inspect.getsource(rd).count("APIRouter(") == 1
