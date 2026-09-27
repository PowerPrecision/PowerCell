"""
Sistema de Etiquetas nos Processos (Lote 5, Secção B, ponto 15).

O QUE JÁ EXISTIA E O QUE FALTAVA
  `labels: Optional[List[str]]` está no modelo do processo desde sempre,
  persiste em `process_update` e vem nas projecções. O que NÃO existia:

  - Editor nenhum. O comentário no `ProcessDetails` diz que a edição foi
    "movida para um Dialog accionado pelo botão +" — esse Dialog nunca
    chegou a ser construído. Hoje só se põem etiquetas pela API.
  - Filtragem nenhuma: nem `build_process_list_query` nem
    `build_kanban_query` conheciam `labels`.

PORQUE É QUE O CATÁLOGO TEM DE TER ÂMBITO DE TENANT
  Para filtrar é preciso saber que etiquetas existem, e a única fonte
  honesta é o que está nos processos. Um `distinct` sem a condição de
  rede seria uma FUGA NOVA, da mesma família das do Lote 4/5: as
  etiquetas da concorrência ("Cliente Banco X", o nome de uma campanha)
  no dropdown de quem não as devia ver. O catálogo herda o mesmo
  `tenant_condition` das listagens.

NORMALIZAR À ESCRITA, NÃO À LEITURA
  "VIP", "vip" e " VIP " são a mesma etiqueta para quem segmenta, e três
  para o Mongo. Se a normalização ficasse na leitura, cada filtro tinha
  de a repetir — e o primeiro que se esquecesse dava uma lista a menos
  sem ninguém reparar.
"""
import pytest


class TestNormalizacao:
    def test_apara_e_descarta_vazios(self):
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas(["  VIP  ", "", "   ", None]) == ["VIP"]

    def test_remove_duplicados_sem_olhar_a_capitalizacao(self):
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas(["VIP", "vip", " Vip "]) == ["VIP"]

    def test_preserva_a_forma_da_PRIMEIRA_ocorrencia(self):
        """Quem escreve "Sub 35" não quer ver "sub 35" no crachá."""
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas(["Sub 35", "SUB 35"]) == ["Sub 35"]

    def test_preserva_a_ordem_de_entrada(self):
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas(["Urgente", "VIP", "Sub 35"]) == ["Urgente", "VIP", "Sub 35"]

    def test_aceita_uma_string_separada_por_virgulas(self):
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas("VIP, Sub 35 ,Urgente") == ["VIP", "Sub 35", "Urgente"]

    def test_corta_uma_etiqueta_absurdamente_longa(self):
        from services.process_labels import MAX_COMPRIMENTO, normalizar_etiquetas

        (etiqueta,) = normalizar_etiquetas(["x" * 500])
        assert len(etiqueta) == MAX_COMPRIMENTO

    def test_limita_o_numero_de_etiquetas_por_processo(self):
        from services.process_labels import MAX_ETIQUETAS, normalizar_etiquetas

        muitas = [f"etiqueta-{i}" for i in range(MAX_ETIQUETAS + 20)]
        assert len(normalizar_etiquetas(muitas)) == MAX_ETIQUETAS

    def test_nada_e_lista_vazia_e_nao_rebenta(self):
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas(None) == []
        assert normalizar_etiquetas([]) == []
        assert normalizar_etiquetas(123) == []

    def test_uma_lista_vazia_explicita_continua_a_ser_lista_vazia(self):
        """Limpar as etiquetas de um processo tem de ser possível — e o
        `sanitizeProcessUpdatePayload` do frontend já permite `labels:[]`
        de propósito."""
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas([]) == []


class TestCondicaoDeFiltro:
    def test_uma_etiqueta_filtra_por_ela(self):
        from services.process_labels import build_labels_condition

        assert build_labels_condition(["VIP"]) == {"labels": {"$in": ["VIP"]}}

    def test_varias_etiquetas_em_OR_por_omissao(self):
        from services.process_labels import build_labels_condition

        cond = build_labels_condition(["VIP", "Sub 35"])
        assert cond == {"labels": {"$in": ["VIP", "Sub 35"]}}

    def test_em_AND_exige_todas(self):
        from services.process_labels import build_labels_condition

        cond = build_labels_condition(["VIP", "Sub 35"], logica="AND")
        assert cond == {"labels": {"$all": ["VIP", "Sub 35"]}}

    def test_sem_etiquetas_nao_devolve_condicao(self):
        """`None` aqui quer dizer "não filtrar" — e é por isso que o
        chamador tem de o testar antes de o juntar à query."""
        from services.process_labels import build_labels_condition

        assert build_labels_condition([]) is None
        assert build_labels_condition(None) is None

    def test_a_condicao_usa_as_etiquetas_normalizadas(self):
        from services.process_labels import build_labels_condition

        cond = build_labels_condition(["  vip ", "VIP"])
        assert cond == {"labels": {"$in": ["vip"]}}


class TestFiltroNasListagens:
    def test_a_listagem_aceita_etiquetas(self):
        from services.process_list_filters import build_process_list_query

        query = build_process_list_query(
            {"id": "u1"}, "admin", labels=["VIP"],
        )
        texto = str(query)
        assert "labels" in texto and "VIP" in texto

    def test_sem_etiquetas_a_query_nao_ganha_ramo_nenhum(self):
        """Contraprova: um filtro que estivesse sempre presente
        escondia processos sem etiqueta nenhuma."""
        from services.process_list_filters import build_process_list_query

        query = build_process_list_query({"id": "u1"}, "admin")
        assert "labels" not in str(query)

    def test_o_kanban_aceita_as_mesmas_etiquetas(self):
        """O quadro tem construtor SEPARADO — foi assim que ficou de fora
        do isolamento no Lote 4 e do Lote 5 ponto 1. Inventariar os
        sítios que listam, não só a condição."""
        from services.process_list_filters import build_kanban_query

        query = build_kanban_query({"id": "u1"}, "admin", labels=["VIP"])
        assert "labels" in str(query) and "VIP" in str(query)

    def test_o_kanban_sem_etiquetas_tambem_nao_ganha_ramo(self):
        from services.process_list_filters import build_kanban_query

        assert "labels" not in str(build_kanban_query({"id": "u1"}, "admin"))

    def test_o_filtro_nao_engole_o_isolamento_de_rede(self):
        """As etiquetas juntam-se com $and: um filtro novo nunca pode
        anular a condição de tenant."""
        from services.process_list_filters import build_kanban_query

        tenant = {"network_id": "rede_a"}
        query = build_kanban_query({"id": "u1"}, "admin", labels=["VIP"], tenant_condition=tenant)
        assert "rede_a" in str(query)
        assert "VIP" in str(query)


class TestCatalogoDeEtiquetas:
    @pytest.mark.asyncio
    async def test_devolve_as_etiquetas_em_uso(self, fake_async_db):
        from services import process_labels as mod

        await fake_async_db.processes.insert_one({"id": "p1", "labels": ["VIP", "Sub 35"]})
        await fake_async_db.processes.insert_one({"id": "p2", "labels": ["VIP"]})

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "db", fake_async_db)
            etiquetas = await mod.listar_etiquetas_em_uso(tenant_condition=None)

        assert sorted(etiquetas) == ["Sub 35", "VIP"]

    @pytest.mark.asyncio
    async def test_o_catalogo_respeita_o_isolamento_de_rede(self, fake_async_db):
        """A fuga que isto fecha: o nome de uma campanha da concorrência
        no dropdown de quem não a devia ver."""
        from services import process_labels as mod

        await fake_async_db.processes.insert_one(
            {"id": "p1", "network_id": "rede_a", "labels": ["Campanha A"]}
        )
        await fake_async_db.processes.insert_one(
            {"id": "p2", "network_id": "rede_b", "labels": ["Campanha B"]}
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "db", fake_async_db)
            etiquetas = await mod.listar_etiquetas_em_uso(
                tenant_condition={"network_id": "rede_a"}
            )

        assert etiquetas == ["Campanha A"]

    @pytest.mark.asyncio
    async def test_a_base_em_baixo_devolve_lista_vazia_e_nao_levanta(self, fake_async_db):
        """Degradação graciosa: sem catálogo o filtro fica sem sugestões,
        mas a página abre."""
        from services import process_labels as mod

        class Partida:
            def __getattr__(self, _nome):
                raise RuntimeError("base em baixo")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "db", Partida())
            assert await mod.listar_etiquetas_em_uso(tenant_condition=None) == []


class TestNormalizacaoNaEscrita:
    """A normalização tem de correr nos DOIS caminhos de escrita.

    `process_update.run_update_process` e `process_service` gravam ambos
    `labels`. Normalizar só num deles dava um sistema em que a mesma
    etiqueta ficava "VIP" ou "  vip " conforme o ecrã que a gravou — e o
    filtro, que compara valores exactos, deixava de as encontrar.
    """

    def test_o_caminho_do_update_normaliza(self):
        from tests.unit.helpers_fonte import codigo_sem_comentarios
        from pathlib import Path

        fonte = codigo_sem_comentarios(
            Path(__file__).resolve().parents[2].joinpath("services", "process_update.py").read_text()
        )
        assert 'update_data["labels"] = data.labels' not in fonte
        assert "normalizar_etiquetas" in fonte

    def test_o_caminho_do_process_service_normaliza(self):
        from tests.unit.helpers_fonte import codigo_sem_comentarios
        from pathlib import Path

        fonte = codigo_sem_comentarios(
            Path(__file__).resolve().parents[2].joinpath("services", "process_service.py").read_text()
        )
        assert 'update_data["labels"] = data.labels' not in fonte
        assert "normalizar_etiquetas" in fonte

    def test_contraprova_a_funcao_faz_mesmo_alguma_coisa(self):
        """Sem isto, apagar o corpo de `normalizar_etiquetas` satisfazia
        as duas guardas acima."""
        from services.process_labels import normalizar_etiquetas

        assert normalizar_etiquetas([" VIP ", "vip", ""]) == ["VIP"]


class TestEndpointDoCatalogo:
    """`GET /processes/labels` — o dropdown do filtro.

    Tem de estar declarado ANTES de `/{process_id}`, senão o FastAPI lê
    "labels" como um id de processo e devolve 404. É a mesma regra das
    rotas estáticas que o AGENTS.md repete para todos os routers.
    """

    def test_a_rota_existe_antes_da_rota_dinamica(self):
        from pathlib import Path
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(
            Path(__file__).resolve().parents[2].joinpath("routes", "processes.py").read_text()
        )
        # `ast.unparse` normaliza as aspas — comparar sem elas.
        assert "router.get(/labels)" in fonte.replace("'", "").replace('"', "")
        limpo = fonte.replace("'", "").replace('"', "")
        assert limpo.index("router.get(/labels)") < limpo.index("router.get(/{process_id}")

    @pytest.mark.asyncio
    async def test_o_handler_passa_o_isolamento_de_rede(self, fake_async_db, monkeypatch):
        """A guarda que interessa: sem a condição de tenant, o dropdown
        mostrava as etiquetas de outra rede."""
        from services import process_labels as mod

        await fake_async_db.processes.insert_one(
            {"id": "p1", "network_id": "rede_a", "labels": ["Campanha A"]}
        )
        await fake_async_db.processes.insert_one(
            {"id": "p2", "network_id": "rede_b", "labels": ["Campanha B"]}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        async def tenant_falso(_user):
            return {"network_id": "rede_a"}

        monkeypatch.setattr(mod, "build_tenant_condition", tenant_falso)
        resposta = await mod.run_get_process_labels({"id": "u1"})

        assert resposta["labels"] == ["Campanha A"]

    @pytest.mark.asyncio
    async def test_contraprova_outra_rede_ve_a_sua(self, fake_async_db, monkeypatch):
        from services import process_labels as mod

        await fake_async_db.processes.insert_one(
            {"id": "p1", "network_id": "rede_a", "labels": ["Campanha A"]}
        )
        await fake_async_db.processes.insert_one(
            {"id": "p2", "network_id": "rede_b", "labels": ["Campanha B"]}
        )
        monkeypatch.setattr(mod, "db", fake_async_db)

        async def tenant_falso(_user):
            return {"network_id": "rede_b"}

        monkeypatch.setattr(mod, "build_tenant_condition", tenant_falso)
        resposta = await mod.run_get_process_labels({"id": "u2"})

        assert resposta["labels"] == ["Campanha B"]
