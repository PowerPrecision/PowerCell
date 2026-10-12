"""D-31 (remate 2) — a pesquisa e as categorias GLOBAIS aplicam a regra de pré-indexação.

O QUE ESTAVA ABERTO
===================
`POST /documents/search` e `GET /documents/categories` sem `process_id` foram
recortados à REDE (D-31). A regra FINA — um processo «Por Indexar» só mostra os
documentos à gestão, à equipa de Index, a quem está atribuído e a quem tem
relação com o cliente — continuava por aplicar: um consultor não atribuído levava
403 ao abrir os documentos do processo e, na pesquisa, via o nome do ficheiro, o
resumo da IA e o URL pré-assinado desse mesmo ficheiro; nas categorias, a
contagem. E quem não vê a pasta `Index` (consultor, administrativo) via os
ficheiros dela contados.

COMO SE TESTA
=============
Os routers REAIS por HTTP com os serviços de pesquisa REAIS sobre a BD falsa — e
um teste de CONCORDÂNCIA: a lista agregada tem de dizer, para cada utilizador e
cada processo, o mesmo que a guarda individual (`assert_can_view_process_documents`).
Duas respostas à mesma pergunta divergem na primeira mudança e a que divergir não
dá erro.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixtures)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
)
from tests.unit.test_d31_documentos_id_no_corpo import (  # noqa: F401  (fixtures)
    corpo,
    pesquisa,
)
from tests.unit.test_d31_documentos_tasklogs_portal import (
    NUNO,
    SESSOES,
    _sessao,
)

IDX = {"id": "u-idx", "name": "Index Domus", "email": "idx@domus.pt", "role": "indexacao"}
ADM = {"id": "u-adm", "name": "Administrativo", "email": "adm@domus.pt", "role": "administrativo"}
CRIADOR = {"id": "u-criador", "name": "Criador", "email": "criador@domus.pt", "role": "consultor"}

SESSOES.setdefault("nuno", _sessao(NUNO))
SESSOES.setdefault("idx", _sessao(IDX))
SESSOES.setdefault("adm", _sessao(ADM))
SESSOES.setdefault("criador", _sessao(CRIADOR))

PASTA = "Documentação Clientes"


def _doc(i, pid, nome, categoria="Identificação", **extra):
    return {
        "id": i, "process_id": pid, "filename": nome, "is_categorized": True,
        "ai_category": categoria, "s3_path": f"{PASTA}/{pid}/{categoria}/{nome}",
        "ai_summary": "cartao de cidadao", **extra,
    }


@pytest.fixture
def cenario(pesquisa, corpo):  # noqa: F811
    """Processos da Domus em vários estados de indexação, e os seus documentos."""
    como, _chamadas, bd = corpo[0], corpo[1], corpo[2]
    bd.users.docs.extend([
        {**p, "is_active": True, "company": "Domus"} for p in (IDX, ADM, CRIADOR)
    ])
    bd.user_company_roles.docs.extend([
        {"user_id": p["id"], "company_id": "cmp-domus", "company_name": "Domus",
         "role": p["role"], "is_default": True} for p in (IDX, ADM, CRIADOR)
    ])
    bd.clients.docs.extend([
        # O Nuno é o consultor deste cliente (PACOTE 12) — sem estar no processo.
        {"id": "c-do-nuno", "nome": "Do Nuno", "network_id": REDE_DOMUS, "company_id": "cmp-domus",
         "assigned_to": "u-nuno", "process_ids": ["p-pre-cliente"]},
        {"id": "c-do-criador", "nome": "Do Criador", "network_id": REDE_DOMUS, "company_id": "cmp-domus",
         "created_by": "criador@domus.pt", "process_ids": ["p-pre-criador"]},
    ])
    base = {"network_id": REDE_DOMUS, "company_id": "cmp-domus", "status": "novo"}
    bd.processes.docs.extend([
        {"id": "p-pre-atribuido", "is_indexed": False, "client_id": "x1",
         "assigned_consultor_id": "u-nuno", **base},
        # Só o singular legado: o defeito de `collect_assigned_user_ids` já uma vez.
        {"id": "p-pre-legado", "is_indexed": False, "client_id": "x2",
         "consultant_id": "u-nuno", **base},
        {"id": "p-pre-lista", "is_indexed": False, "client_id": "x3",
         "assigned_mediador_ids": ["u-outro", "u-nuno"], **base},
        {"id": "p-pre-outro", "is_indexed": False, "client_id": "x4",
         "assigned_consultor_id": "u-outro", **base},
        {"id": "p-pre-cliente", "is_indexed": False, "client_id": "c-do-nuno", **base},
        {"id": "p-pre-criador", "is_indexed": False, "client_id": "c-do-criador", **base},
        # Sem a marca: `is_indexed` ausente conta como por indexar.
        {"id": "p-pre-sem-marca", "client_id": "x5", **base},
    ])
    bd.document_metadata.docs.extend([
        _doc("m-pre-atribuido", "p-pre-atribuido", "atribuido.pdf"),
        _doc("m-pre-legado", "p-pre-legado", "legado.pdf"),
        _doc("m-pre-lista", "p-pre-lista", "lista.pdf"),
        _doc("m-pre-outro", "p-pre-outro", "outro.pdf"),
        _doc("m-pre-cliente", "p-pre-cliente", "cliente.pdf"),
        _doc("m-pre-criador", "p-pre-criador", "criador.pdf"),
        _doc("m-pre-sem-marca", "p-pre-sem-marca", "sem-marca.pdf"),
        # Um ficheiro na pasta `Index` de um processo JÁ indexado, e outro ainda
        # na fila da IA: a parede da pasta cofre vale na pesquisa e na contagem.
        {**_doc("m-index", "p-dm", "na-index.pdf"), "s3_path": f"{PASTA}/p-dm/Index/na-index.pdf"},
        {**_doc("m-fila", "p-dm", "na-fila.pdf"), "in_index_queue": True},
    ])
    return como, bd


def _ids(resposta) -> set[str]:
    assert resposta.status_code == 200, resposta.text
    return {r["id"] for r in resposta.json()["results"]}


def _pesquisar(como, quem: str) -> set[str]:
    return _ids(como(quem).post("/documents/search", json={"query": "cartao", "limit": 100}))


PRE = {
    "m-pre-atribuido", "m-pre-legado", "m-pre-lista", "m-pre-outro",
    "m-pre-cliente", "m-pre-criador", "m-pre-sem-marca",
}
INDEXADOS = {"m-dm", "m-part"}


# ════════════════════════════════════════════════════════════════════
class TestAPesquisaGlobalNaoMostraOQueONaoSePodeAbrir:
    def test_o_consultor_nao_atribuido_so_ve_os_indexados_e_os_seus(self, cenario):
        como, _ = cenario
        # Os do Nuno: atribuído (campo canónico, singular legado, lista do
        # mediador) e a relação com o cliente (PACOTE 12).
        assert _pesquisar(como, "nuno") == INDEXADOS | {
            "m-pre-atribuido", "m-pre-legado", "m-pre-lista", "m-pre-cliente",
        }

    def test_o_Nuno_nao_ve_nada_do_que_nao_e_dele(self, cenario):
        como, _ = cenario
        encontrados = _pesquisar(como, "nuno")
        for fora in ("m-pre-outro", "m-pre-criador", "m-pre-sem-marca"):
            assert fora not in encontrados

    def test_nenhum_url_pre_assinado_de_um_processo_vedado_sai(self, cenario):
        como, _ = cenario
        texto = como("nuno").post("/documents/search", json={"query": "cartao", "limit": 100}).text
        assert "outro.pdf" not in texto and "sem-marca.pdf" not in texto

    def test_o_criador_do_cliente_ve_o_processo_desse_cliente(self, cenario):
        como, _ = cenario
        assert _pesquisar(como, "criador") == INDEXADOS | {"m-pre-criador"}

    def test_a_gestao_ve_todos_os_da_sua_rede(self, cenario):
        como, _ = cenario
        assert PRE <= _pesquisar(como, "bruno")                    # diretor (bypass)
        assert PRE <= _pesquisar(como, "adm")                      # administrativo (bypass)

    def test_a_equipa_de_Index_ve_a_pre_indexacao_por_desenho(self, cenario):
        como, _ = cenario
        assert PRE <= _pesquisar(como, "idx")

    def test_o_Master_ve_tudo(self, cenario):
        como, _ = cenario
        assert PRE | INDEXADOS <= _pesquisar(como, "master")

    def test_a_rede_continua_a_valer_para_a_gestao(self, cenario):
        como, _ = cenario
        assert "m-pw" not in _pesquisar(como, "bruno")
        assert not (PRE & _pesquisar(como, "ana"))

    def test_a_parede_da_Index_vale_na_pesquisa(self, cenario):
        como, _ = cenario
        assert not {"m-index", "m-fila"} & _pesquisar(como, "nuno")
        assert not {"m-index", "m-fila"} & _pesquisar(como, "adm")
        assert {"m-index", "m-fila"} <= _pesquisar(como, "bruno")


class TestAsCategoriasGlobaisContamSoOQueSePodeAbrir:
    @staticmethod
    def _total(como, quem) -> int:
        r = como(quem).get("/documents/categories")
        assert r.status_code == 200, r.text
        return sum(c["count"] for c in r.json()["categories"])

    def test_o_consultor_nao_atribuido_conta_so_os_visiveis(self, cenario):
        como, _ = cenario
        # 2 indexados + 4 dele; a Index e a fila ficam de fora.
        assert self._total(como, "nuno") == len(INDEXADOS) + 4

    def test_a_gestao_conta_tudo_o_que_ve_incluindo_a_Index(self, cenario):
        como, _ = cenario
        # diretor vê a pasta Index: 7 pré-indexação + 2 indexados + 2 da Index.
        assert self._total(como, "bruno") == len(PRE) + len(INDEXADOS) + 2

    def test_o_administrativo_ve_a_pre_indexacao_mas_nao_a_Index(self, cenario):
        como, _ = cenario
        assert self._total(como, "adm") == len(PRE) + len(INDEXADOS)

    def test_as_duas_vias_de_contagem_concordam(self, cenario):
        """Quem vê a Index conta por agregação e quem não vê conta em memória:
        sem ficheiros na Index os dois caminhos têm de dar o mesmo."""
        como, bd = cenario
        bd.document_metadata.docs[:] = [
            d for d in bd.document_metadata.docs if d["id"] not in ("m-index", "m-fila")
        ]
        assert self._total(como, "adm") == self._total(como, "bruno")

    def test_um_processo_vedado_pedido_por_id_e_403_tambem_nas_categorias(self, cenario):
        como, _ = cenario
        assert como("nuno").get("/documents/categories", params={"process_id": "p-pre-outro"}).status_code == 403
        assert como("nuno").get("/documents/categories", params={"process_id": "p-pre-atribuido"}).status_code == 200

    def test_um_processo_que_nao_existe_e_404(self, cenario):
        como, _ = cenario
        assert como("nuno").get("/documents/categories", params={"process_id": "p-nunca"}).status_code == 404

    def test_o_alheio_continua_a_ser_404_antes_de_qualquer_403(self, cenario):
        como, _ = cenario
        assert como("nuno").get("/documents/categories", params={"process_id": "p-pw"}).status_code == 404


# ════════════════════════════════════════════════════════════════════
class TestAListaAgregadaConcordaComAGuardaIndividual:
    """Para cada utilizador e cada processo, `ids_de_processos_com_documentos_visiveis`
    diz o que `assert_can_view_process_documents` diz. É este teste, e não a
    leitura das duas, que apanha a regra a divergir."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("quem", ["nuno", "criador", "idx", "adm", "bruno", "carla", "ana", "ceo_domus"])
    async def test_concordam(self, cenario, quem):
        import services.document_visibility as dv
        from tests.unit.helpers_tenant import tenant_db

        _, bd = cenario
        user = SESSOES[quem]
        with tenant_db(bd, dv):
            agregada = set(await dv.ids_de_processos_com_documentos_visiveis(user) or [])
            individual = set()
            for processo in bd.processes.docs:
                try:
                    await dv.assert_can_view_process_documents(user, processo)
                except HTTPException:
                    continue
                individual.add(processo["id"])
        assert agregada == individual, (quem, agregada ^ individual)

    @pytest.mark.asyncio
    async def test_o_Master_nao_tem_recorte(self, cenario):
        import services.document_visibility as dv
        from tests.unit.helpers_tenant import tenant_db

        _, bd = cenario
        with tenant_db(bd, dv):
            assert await dv.ids_de_processos_com_documentos_visiveis(SESSOES["master"]) is None

    @pytest.mark.asyncio
    async def test_sem_ambito_resolvivel_nao_ha_processos(self, cenario):
        """Falha FECHADA: um utilizador sem empresa nem rede não recebe «todos»."""
        import services.document_visibility as dv
        from tests.unit.helpers_tenant import tenant_db

        _, bd = cenario
        fantasma = _sessao({"id": "u-fantasma", "name": "F", "role": "consultor"})
        with tenant_db(bd, dv):
            visiveis = await dv.ids_de_processos_com_documentos_visiveis(fantasma)
        assert not (set(visiveis) & PRE_PROCESSOS)


PRE_PROCESSOS = {
    "p-pre-atribuido", "p-pre-legado", "p-pre-lista", "p-pre-outro",
    "p-pre-cliente", "p-pre-criador", "p-pre-sem-marca",
}
