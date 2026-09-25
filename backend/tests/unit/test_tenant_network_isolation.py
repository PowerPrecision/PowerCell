"""
Isolamento multi-tenant por Rede (`network_id`) — Lote 4, ponto 10.

O ENUNCIADO ERA "A LISTAGEM MOSTRA TUDO A TODOS". O DIAGNÓSTICO É PIOR.
  1. Não havia filtro de tenant NENHUM nas listagens e pesquisas
     (`search_api_*`, `client_list_*`, `my_clients_*`, `task_api_crud`:
     zero ocorrências de "compan"). Um consultor da Domus que carregasse
     Ctrl+K via os clientes da Power — com o NIF já desencriptado, porque
     `run_global_search` chama `decrypt_client_data` antes de devolver.
  2. `build_role_visibility_conditions` devolve `[]` para admin / ceo /
     administrativo / diretor: uma Diretora de uma empresa via o pipeline
     inteiro de outra.
  3. O ÚNICO filtro que existia era um placebo. `build_company_scope_condition`
     inclui de propósito `{"company_id": {"$exists": False}}` — e
     `build_staff_process_doc` NÃO ESCREVE campo de empresa nenhum. Logo
     todo o processo criado pelo CRM casa com o filtro de QUALQUER empresa.
     Parecia isolar porque o `mine_only` já restringia por atribuição, e
     era a atribuição a fazer o trabalho todo.

Daí as camadas: a rede vive na EMPRESA (1), resolve-se num PONTO ÚNICO (2)
e é CARIMBADA NA ESCRITA (3) — um filtro sobre um campo que ninguém
escreve é exactamente o placebo que já tínhamos.

Estes testes foram escritos ANTES da correcção e falham contra o código
antigo, cada um a apontar para a fuga concreta que fecha.
"""
from unittest.mock import patch

import pytest


# ────────────────────────────────────────────────────────────────────
# Cenário partilhado: duas redes, três empresas, um utilizador em cada.
# ────────────────────────────────────────────────────────────────────
REDE_INCUMBENTE = "grupo_power_precision"
REDE_DOMUS = "grupo_domus"

EMPRESAS = [
    {"id": "cmp-power", "name": "Power Real Estate", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-precision", "name": "Precision Crédito", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS},
]

UCRS = [
    {"user_id": "u-ana", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "diretor", "is_default": True},
    {"user_id": "u-bruno", "company_id": "cmp-domus", "company_name": "Domus",
     "role": "diretor", "is_default": True},
    # Carla trabalha nas duas redes — não é fuga, são os dois empregos dela.
    {"user_id": "u-carla", "company_id": "cmp-precision", "company_name": "Precision Crédito",
     "role": "consultor", "is_default": True},
    {"user_id": "u-carla", "company_id": "cmp-domus", "company_name": "Domus",
     "role": "consultor", "is_default": False},
]

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor"}
CARLA = {"id": "u-carla", "name": "Carla", "email": "carla@precision.pt", "role": "consultor"}
ORFAO = {"id": "u-orfao", "name": "Orfão", "email": "orfao@sistema.pt", "role": "admin"}

PROCESSOS = [
    {"id": "p-power", "client_name": "Cliente da Power", "status": "novo",
     "company_id": "cmp-power", "network_id": REDE_INCUMBENTE},
    {"id": "p-domus", "client_name": "Cliente da Domus", "status": "novo",
     "company_id": "cmp-domus", "network_id": REDE_DOMUS},
    # O processo que já lá estava antes desta mudança: sem carimbo nenhum.
    {"id": "p-legado", "client_name": "Cliente Antigo", "status": "novo"},
    # Carimbado com empresa mas ainda sem rede (criado entre a camada 3 e
    # a migração). NÃO é "sem marca de tenant" — ver teste dedicado.
    {"id": "p-domus-sem-rede", "client_name": "Outro da Domus", "status": "novo",
     "company_id": "cmp-domus"},
]

CLIENTES = [
    {"id": "c-power", "nome": "Silva da Power", "network_id": REDE_INCUMBENTE,
     "company_id": "cmp-power", "contacto": {}, "dados_pessoais": {"nif": "111111111"}},
    {"id": "c-domus", "nome": "Silva da Domus", "network_id": REDE_DOMUS,
     "company_id": "cmp-domus", "contacto": {}, "dados_pessoais": {"nif": "222222222"}},
    {"id": "c-legado", "nome": "Silva Antigo", "contacto": {},
     "dados_pessoais": {"nif": "333333333"}},
]


def _semear(fake_db):
    for empresa in EMPRESAS:
        fake_db.companies.docs.append(dict(empresa))
    for ucr in UCRS:
        fake_db.user_company_roles.docs.append(dict(ucr))
    for proc in PROCESSOS:
        fake_db.processes.docs.append(dict(proc))
    for cli in CLIENTES:
        fake_db.clients.docs.append(dict(cli))
    return fake_db


def _casa(doc: dict, condicao: dict) -> bool:
    """Aplica uma condição Mongo a um documento com o matcher da fake."""
    from tests.unit.conftest import FakeAsyncCollection

    return FakeAsyncCollection._matches(doc, condicao)


def _por_id(docs):
    return {d["id"] for d in docs}


def _tenant_db(fake_db):
    """Patcha a BD em TODA a cadeia de resolução do âmbito.

    `tenant_network` importa `db` no topo (referência própria), mas
    delega a lista de empresas válidas em `auth.get_user_companies`, que
    faz `from database import db` DENTRO da função. Patchar só um dos
    dois deixa metade da cadeia a falar com o proxy real — e o resultado
    passa ou falha conforme a ORDEM de recolha do pytest (ver AGENTS.md).

    ÉPICO 10, PONTO 1 — a cadeia cresceu: `workflow_phases` também
    importa `db` no topo, e o quadro passou a perguntar-lhe que fases
    estão fechadas. Sem este patch o `carregar_fases` falava com o proxy
    real, a excepção era engolida (degradação graciosa), devolvia `[]` e
    o quadro vinha SEM COLUNAS — um teste vermelho a apontar para o
    isolamento quando o problema era o `db`. **Uma cadeia nova de `db`
    entra aqui.**
    """
    import contextlib

    import services.tenant_network as tn
    import services.workflow_phases as wp

    @contextlib.contextmanager
    def _ctx():
        with patch.object(tn, "db", fake_db), \
             patch.object(wp, "db", fake_db), \
             patch("database.db", fake_db):
            yield

    return _ctx()


@pytest.fixture
def db_tenant(fake_async_db):
    return _semear(fake_async_db)


@pytest.fixture
def rede_de_omissao_incumbente(monkeypatch):
    """Produção: a pilha por carimbar pertence ao grupo incumbente."""
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    yield REDE_INCUMBENTE


# ════════════════════════════════════════════════════════════════════
# CAMADA 1 — a rede vive na empresa
# ════════════════════════════════════════════════════════════════════
class TestRedeDaEmpresa:
    def test_empresa_com_rede_configurada_usa_essa_rede(self):
        from services.tenant_network import resolve_network_id

        assert resolve_network_id(
            {"id": "cmp-power", "network_id": REDE_INCUMBENTE}
        ) == REDE_INCUMBENTE

    def test_empresa_sem_rede_e_uma_ilha_de_uma(self):
        """Omissão segura: uma empresa nova nasce isolada.

        Se caísse na rede de omissão, uma empresa criada hoje veria a
        pilha inteira do grupo incumbente — exactamente a fuga.
        """
        from services.tenant_network import resolve_network_id, rede_implicita

        rede = resolve_network_id({"id": "cmp-nova", "name": "Nova"})
        assert rede == rede_implicita("cmp-nova")
        assert rede != REDE_INCUMBENTE

    def test_a_ilha_implicita_nunca_colide_com_outra_empresa(self):
        from services.tenant_network import rede_implicita

        assert rede_implicita("cmp-a") != rede_implicita("cmp-b")


# ════════════════════════════════════════════════════════════════════
# CAMADA 2 — ponto único: resolução do âmbito + condição pura
# ════════════════════════════════════════════════════════════════════
class TestResolucaoDoAmbito:
    @pytest.mark.asyncio
    async def test_utilizador_de_uma_rede_so_traz_essa_rede(self, db_tenant):
        import services.tenant_network as tn

        with _tenant_db(db_tenant):
            scope = await tn.resolve_tenant_scope(BRUNO)

        assert set(scope.network_ids) == {REDE_DOMUS}
        assert REDE_INCUMBENTE not in scope.network_ids

    @pytest.mark.asyncio
    async def test_utilizador_em_duas_redes_traz_as_duas(self, db_tenant):
        """Carla é consultora na Precision E na Domus: vê as duas redes."""
        import services.tenant_network as tn

        with _tenant_db(db_tenant):
            scope = await tn.resolve_tenant_scope(CARLA)

        assert set(scope.network_ids) == {REDE_INCUMBENTE, REDE_DOMUS}

    @pytest.mark.asyncio
    async def test_empresas_do_mesmo_grupo_partilham_visibilidade(self, db_tenant):
        """Regra de negócio: Power e Precision partilham sem permissões extra."""
        import services.tenant_network as tn

        with _tenant_db(db_tenant):
            scope = await tn.resolve_tenant_scope(ANA)
            condicao = tn.build_network_scope_condition(scope)

        processo_da_precision = {
            "id": "p-precision", "company_id": "cmp-precision",
            "network_id": REDE_INCUMBENTE,
        }
        assert _casa(processo_da_precision, condicao), (
            "Ana é da Power; a Precision está na mesma rede e tem de ser visível"
        )

    @pytest.mark.asyncio
    async def test_utilizador_orfao_cai_na_rede_de_omissao(
        self, db_tenant, rede_de_omissao_incumbente
    ):
        """Contas antigas sem UCR não podem ficar cegas no dia do deploy."""
        import services.tenant_network as tn

        with _tenant_db(db_tenant):
            scope = await tn.resolve_tenant_scope(ORFAO)

        assert REDE_INCUMBENTE in scope.network_ids
        assert scope.inclui_rede_de_omissao is True


class TestCondicaoPura:
    def test_sem_variavel_de_ambiente_o_legado_continua_visivel(self, monkeypatch):
        """Dev/CI: a variável não está definida → comportamento de hoje.

        Sem isto, toda a bateria existente (e a base de dev) ficava com
        listagens vazias — "partir os dados existentes" pela porta do lado.
        """
        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        from services.tenant_network import TenantScope, build_network_scope_condition

        scope = TenantScope(
            network_ids=(REDE_DOMUS,),
            company_ids=("cmp-domus",),
            company_names=("Domus",),
            inclui_rede_de_omissao=True,
        )
        assert _casa(PROCESSOS[2], build_network_scope_condition(scope))

    def test_documento_com_empresa_mas_sem_rede_nao_conta_como_por_carimbar(self):
        """A armadilha: `network_id` ausente NÃO basta para ser "legado".

        Um processo da Domus criado entre a camada 3 e a migração tem
        `company_id` mas ainda não tem `network_id`. Se o ramo do legado
        olhasse só para o `network_id`, a Power via-o — a fuga a entrar
        outra vez pela cláusula que existe para a evitar.
        """
        from services.tenant_network import TenantScope, build_network_scope_condition

        scope_power = TenantScope(
            network_ids=(REDE_INCUMBENTE,),
            company_ids=("cmp-power", "cmp-precision"),
            company_names=("Power Real Estate", "Precision Crédito"),
            inclui_rede_de_omissao=True,
        )
        condicao = build_network_scope_condition(scope_power)
        alvo = dict(PROCESSOS[3])  # p-domus-sem-rede
        assert not _casa(alvo, condicao), (
            "documento com company_id de outra rede não é um documento por carimbar"
        )

    def test_ambito_sem_rede_nenhuma_nao_devolve_condicao_vazia(self):
        """Fail-closed: um âmbito fechado nunca pode virar 'sem filtro'.

        Devolver `None` aqui seria reabrir a fuga inteira em silêncio.
        """
        from services.tenant_network import TenantScope, build_network_scope_condition

        condicao = build_network_scope_condition(
            TenantScope(network_ids=(), company_ids=(), company_names=(),
                        inclui_rede_de_omissao=False)
        )
        assert condicao is not None
        for doc in PROCESSOS:
            assert not _casa(doc, condicao)


# ════════════════════════════════════════════════════════════════════
# A FUGA — listagens e pesquisas
# ════════════════════════════════════════════════════════════════════
class TestFugaNaListagemDeProcessos:
    @pytest.mark.asyncio
    async def test_diretora_de_outra_rede_nao_ve_processos_da_power(
        self, db_tenant, rede_de_omissao_incumbente
    ):
        """A FUGA original: `build_role_visibility_conditions` devolve []
        para diretor/admin/ceo, logo a Diretora da Domus via tudo."""
        import services.process_list_enrichment as ple

        with _tenant_db(db_tenant), \
             patch.object(ple, "db", db_tenant), \
             patch.object(ple, "load_workflow_status_order", _async_none), \
             patch.object(ple, "enrich_processes_assignee_names", _async_noop), \
             patch.object(ple, "enrich_processes_portal_flags", _async_noop), \
             patch.object(ple, "enrich_processes_latest_notes", _async_noop):
            resposta = await ple.run_get_processes(
                user=BRUNO, role="diretor", page=1, size=50,
                status=None, search=None, view_mode=None,
                sort_field=None, sort_order=None, show_all=True,
                is_indexed=None, all_roles=None,
                decrypt_list_fn=lambda docs, **kw: docs,
                list_projection={"_id": 0},
            )

        vistos = _por_id(resposta["items"])
        assert "p-power" not in vistos, "FUGA: Domus a ver processos da Power"
        assert "p-legado" not in vistos, (
            "FUGA: a pilha por carimbar pertence ao grupo incumbente"
        )
        assert vistos == {"p-domus", "p-domus-sem-rede"}

    @pytest.mark.asyncio
    async def test_grupo_incumbente_nao_sofre_regressao(
        self, db_tenant, rede_de_omissao_incumbente
    ):
        """O outro lado da moeda: a Power continua a ver o que vê hoje."""
        import services.process_list_enrichment as ple

        with _tenant_db(db_tenant), \
             patch.object(ple, "db", db_tenant), \
             patch.object(ple, "load_workflow_status_order", _async_none), \
             patch.object(ple, "enrich_processes_assignee_names", _async_noop), \
             patch.object(ple, "enrich_processes_portal_flags", _async_noop), \
             patch.object(ple, "enrich_processes_latest_notes", _async_noop):
            resposta = await ple.run_get_processes(
                user=ANA, role="diretor", page=1, size=50,
                status=None, search=None, view_mode=None,
                sort_field=None, sort_order=None, show_all=True,
                is_indexed=None, all_roles=None,
                decrypt_list_fn=lambda docs, **kw: docs,
                list_projection={"_id": 0},
            )

        vistos = _por_id(resposta["items"])
        assert "p-power" in vistos
        assert "p-legado" in vistos, "regressão: a pilha antiga desapareceu"
        assert "p-domus" not in vistos


class TestFugaNaPesquisaGlobal:
    @pytest.mark.asyncio
    async def test_pesquisa_global_nao_atravessa_redes(
        self, db_tenant, rede_de_omissao_incumbente
    ):
        """Ctrl+K devolvia clientes de outra empresa com o NIF já
        desencriptado (`decrypt_client_data` antes do return)."""
        import services.search_api_global as sag

        with _tenant_db(db_tenant), \
             patch.object(sag, "db", db_tenant), \
             patch.object(sag, "decrypt_client_data", lambda d: d):
            resultado = await sag.run_global_search("Silva", 10, BRUNO)

        nomes = {c["client_name"] for c in resultado["clients"]}
        assert "Silva da Power" not in nomes, "FUGA: pesquisa a atravessar redes"
        assert "Silva Antigo" not in nomes
        assert nomes == {"Silva da Domus"}

    @pytest.mark.asyncio
    async def test_pesquisa_avancada_de_processos_nao_atravessa_redes(
        self, db_tenant, rede_de_omissao_incumbente
    ):
        import services.search_api_processes as sap

        with _tenant_db(db_tenant), patch.object(sap, "db", db_tenant):
            resultado = await sap.run_search_processes("Cliente", None, None, 20, BRUNO)

        # "Outro da Domus" não casa com o termo — a expectativa inicial
        # deste teste incluía-o e falhou por isso, não por fuga.
        assert _por_id(resultado) == {"p-domus"}

    @pytest.mark.asyncio
    async def test_documento_so_com_empresa_continua_visivel_a_propria_rede(
        self, db_tenant, rede_de_omissao_incumbente
    ):
        """O outro lado de `test_documento_com_empresa_mas_sem_rede_...`.

        Provar que a Power não o vê não chega: se o filtro o escondesse
        TAMBÉM da Domus, a migração ficava a esconder trabalho a quem o
        fez. A cláusula por `company_id` existe exactamente para isto.
        """
        import services.search_api_processes as sap

        with _tenant_db(db_tenant), patch.object(sap, "db", db_tenant):
            da_domus = await sap.run_search_processes("Outro", None, None, 20, BRUNO)
            da_power = await sap.run_search_processes("Outro", None, None, 20, ANA)

        assert _por_id(da_domus) == {"p-domus-sem-rede"}
        assert _por_id(da_power) == set()

    @pytest.mark.asyncio
    async def test_sugestoes_nao_atravessam_redes(
        self, db_tenant, rede_de_omissao_incumbente
    ):
        """As sugestões devolvem NOMES DE CLIENTES — é fuga de dados
        pessoais mesmo sem abrir o processo."""
        import services.search_api_suggestions as sas

        with _tenant_db(db_tenant), patch.object(sas, "db", db_tenant):
            sugestoes = await sas.run_get_search_suggestions("Cliente", BRUNO)

        assert "Cliente da Power" not in sugestoes
        assert "Cliente Antigo" not in sugestoes


# ════════════════════════════════════════════════════════════════════
# CAMADA 3 — carimbo na escrita
# ════════════════════════════════════════════════════════════════════
class TestCarimboNaEscrita:
    def test_processo_novo_nasce_com_rede(self):
        """Sem isto, o filtro da camada 2 é o mesmo placebo de antes."""
        from services.process_create import build_staff_process_doc

        doc = build_staff_process_doc(
            process_id="p1", process_number="PROC-1", now="2026-09-22",
            client_id="c1", client_name="Ana", client_email="a@a.pt",
            client_phone="", client_nif=None, process_type="credito",
            initial_status="novo", is_lead=False,
            tenant={"company_id": "cmp-domus", "company_name": "Domus",
                    "network_id": REDE_DOMUS},
        )
        assert doc["company_id"] == "cmp-domus"
        assert doc["network_id"] == REDE_DOMUS

    def test_processo_sem_contexto_de_empresa_nao_inventa_rede(self):
        """Carimbar uma rede errada é pior do que não carimbar: o
        documento passaria a ser visível à rede errada para sempre."""
        from services.process_create import build_staff_process_doc

        doc = build_staff_process_doc(
            process_id="p1", process_number="PROC-1", now="2026-09-22",
            client_id="c1", client_name="Ana", client_email="a@a.pt",
            client_phone="", client_nif=None, process_type="credito",
            initial_status="novo", is_lead=False, tenant=None,
        )
        assert "network_id" not in doc
        assert "company_id" not in doc

    @pytest.mark.asyncio
    async def test_carimbo_vem_da_empresa_activa_de_quem_cria(self, db_tenant):
        import services.tenant_network as tn

        with _tenant_db(db_tenant):
            carimbo = await tn.resolve_tenant_stamp(BRUNO, active_company_id="cmp-domus")

        assert carimbo == {
            "company_id": "cmp-domus",
            "company_name": "Domus",
            "network_id": REDE_DOMUS,
        }


# ════════════════════════════════════════════════════════════════════
# GUARDA sobre o código-fonte — o ponto único não se reconstrói em linha
# ════════════════════════════════════════════════════════════════════
class TestGuardaDoPontoUnico:
    def test_nenhuma_listagem_reconstroi_a_condicao_a_mao(self):
        """Foi ter a cadeia de resolução duplicada que produziu o
        incidente da conta de envio (2026-09-21). A condição de rede
        sai de `tenant_network`, ou não sai de lado nenhum."""
        from pathlib import Path
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        servicos = Path(__file__).resolve().parents[2] / "services"
        infractores = []
        for nome in (
            "search_api_global.py", "search_api_processes.py",
            "search_api_suggestions.py", "client_list_search.py",
            "process_list_enrichment.py",
        ):
            codigo = codigo_sem_comentarios((servicos / nome).read_text("utf-8"))
            if '"network_id"' in codigo or "'network_id'" in codigo:
                infractores.append(nome)
        assert not infractores, (
            f"{infractores} escrevem a condição de rede à mão em vez de a "
            "pedirem a services/tenant_network.py"
        )

    def test_as_listagens_pedem_mesmo_o_filtro(self):
        """Contraprova do teste acima: sem esta asserção, apagar a
        chamada satisfazia o guarda e reabria a fuga."""
        from pathlib import Path

        servicos = Path(__file__).resolve().parents[2] / "services"
        for nome in (
            "search_api_global.py", "search_api_processes.py",
            "search_api_suggestions.py", "client_list_search.py",
            "process_list_enrichment.py",
        ):
            codigo = (servicos / nome).read_text("utf-8")
            assert "tenant_network" in codigo, f"{nome} não aplica o filtro de rede"


async def _async_none(*args, **kwargs):
    return None


async def _async_noop(*args, **kwargs):
    return None


# ════════════════════════════════════════════════════════════════════
# CAMADA 4 — dedução do dono na migração
# ════════════════════════════════════════════════════════════════════
class TestDeducaoDaMigracao:
    def test_recolhe_ids_de_campos_singulares_e_de_listas(self):
        """Os campos de atribuição são ora string ora lista (ver AGENTS.md,
        "Atribuição: campos CANÓNICOS"). Ler só um dos formatos deixaria
        processos atribuídos sem dono dedutível."""
        from scripts.backfill_network_id import ids_atribuidos

        doc = {
            "assigned_consultor_ids": ["u-1", "u-2"],
            "assigned_mediador_id": "u-3",
            "consultant_id": "u-1",  # duplicado: não pode aparecer duas vezes
            "assigned_indexacao_id": None,
        }
        campos = (
            "assigned_consultor_ids", "assigned_mediador_id",
            "consultant_id", "assigned_indexacao_id",
        )
        assert ids_atribuidos(doc, campos) == ["u-1", "u-2", "u-3"]

    def test_consenso_unico_resolve(self):
        from scripts.backfill_network_id import rede_consensual

        assert rede_consensual([REDE_DOMUS, REDE_DOMUS, None]) == REDE_DOMUS

    def test_sem_consenso_nao_adivinha(self):
        """Um processo trabalhado por pessoas de redes diferentes não tem
        dono óbvio — e adivinhar aqui é escolher a quem vazar. Fica por
        carimbar, coberto pela rede de omissão."""
        from scripts.backfill_network_id import rede_consensual

        assert rede_consensual([REDE_DOMUS, REDE_INCUMBENTE]) is None

    def test_sem_candidatas_nao_inventa(self):
        from scripts.backfill_network_id import rede_consensual

        assert rede_consensual([None, None]) is None


class TestEmpresaNovaNaoHerdaRede:
    def test_criacao_de_empresa_grava_a_rede_pedida_e_so_essa(self):
        """Se a criação herdasse a rede de omissão, a empresa nova nascia
        a ver a pilha inteira do grupo incumbente — a fuga no acto da
        criação. O campo é explícito e o padrão é `None` (ilha)."""
        from tests.unit.helpers_fonte import codigo_sem_comentarios
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2]
            / "services" / "companies_crud_api_mutate.py"
        ).read_text("utf-8")
        # `ast.unparse` normaliza as aspas — comparar sem elas.
        codigo = codigo_sem_comentarios(fonte).replace('"', "'")
        assert "'network_id': data.network_id" in codigo
        assert "rede_de_omissao" not in codigo
