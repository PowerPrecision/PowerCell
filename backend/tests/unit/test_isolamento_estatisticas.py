"""
Isolamento de rede no Dashboard — Refinamento Analítico e SLAs, ponto 1.

O DIAGNÓSTICO
  `grep "tenant\\|network_id"` nos seis módulos de estatísticas e no
  `analytics_service`: ZERO ocorrências. O Lote 4 fechou as listagens e
  as pesquisas, o Lote 5 acrescentou o quadro e o explorador de
  ficheiros; o Dashboard nunca entrou nesse inventário. É a lição do
  Lote 5, ponto 1, a repetir-se noutra superfície: um ponto único para a
  CONDIÇÃO não chega — é preciso inventariar os sítios que AGREGAM.

  Cada teste aqui aponta para a fuga concreta que fecha, e todos falham
  contra o código anterior. O mais grave não é uma contagem: o
  `stats_communications` devolvia a papéis privilegiados os primeiros
  150 caracteres do que os clientes escreveram no Portal e os assuntos
  dos emails não lidos, de TODAS as redes.

A CACHE ERA METADE DO PROBLEMA
  `stats:branches:v2` e `stats:global:conversion` são chaves GLOBAIS: com
  o filtro posto e a chave partilhada, o primeiro pedido semeava a cache
  para todos. Há testes dedicados a isso — um filtro sobre uma cache
  partilhada é teatro.
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios
from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    CARLA,
    ORFAO,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    rede_de_omissao_incumbente,  # noqa: F401  (fixture)
    tenant_db,
)

import pathlib

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]

MODULOS_DE_ESTATISTICAS = (
    "stats_overview",
    "stats_leads",
    "stats_conversion",
    "stats_communications",
    "stats_branches",
)

#: Os que têm cache própria. O `stats_communications` não tem nenhuma (o
#: feed é time-sensitive) — patchar-lhe um `cache_get` inexistente
#: rebentava a fixture com um AttributeError, que é informação: o módulo
#: não fala com o Redis.
MODULOS_COM_CACHE = (
    "stats_overview",
    "stats_leads",
    "stats_conversion",
    "stats_branches",
)


def _modulos(*nomes):
    """Importa módulos de serviço por nome, para o patch de `db`."""
    import importlib

    return [importlib.import_module(f"services.{n}") for n in nomes]


@pytest.fixture
def sem_cache():
    """Neutraliza a cache: em dev o `redis_cache` usa memória do processo.

    Sem isto o primeiro teste semeava a resposta e o segundo — que é
    precisamente o de OUTRA rede — recebia-a da cache. O defeito que
    estamos a fechar, dentro da própria bateria.
    """
    import contextlib

    with contextlib.ExitStack() as pilha:
        for nome in MODULOS_COM_CACHE:
            pilha.enter_context(patch(
                f"services.{nome}.cache_get",
                new_callable=AsyncMock, return_value=None,
            ))
            pilha.enter_context(patch(
                f"services.{nome}.cache_set",
                new_callable=AsyncMock, return_value=True,
            ))
        yield


# ════════════════════════════════════════════════════════════════════
# O ÂMBITO (lógica pura)
# ════════════════════════════════════════════════════════════════════

class TestSufixoDeCache:
    def _scope(self, **kwargs):
        from services.tenant_network import TenantScope

        return TenantScope(**kwargs)

    def test_o_mesmo_ambito_da_o_mesmo_sufixo(self):
        from services.stats_scope import sufixo_de_cache

        a = self._scope(network_ids=("r1",), company_ids=("c1",))
        b = self._scope(network_ids=("r1",), company_ids=("c1",))
        assert sufixo_de_cache(a) == sufixo_de_cache(b)

    def test_redes_diferentes_dao_sufixos_diferentes(self):
        """O teste que impede a fuga pela cache."""
        from services.stats_scope import sufixo_de_cache

        power = self._scope(network_ids=(REDE_INCUMBENTE,))
        domus = self._scope(network_ids=(REDE_DOMUS,))
        assert sufixo_de_cache(power) != sufixo_de_cache(domus)

    def test_a_ordem_das_associacoes_nao_conta(self):
        """As associações chegam do Mongo na ordem que ele quiser.

        Sem ordenar, a mesma pessoa tinha duas chaves em pedidos
        consecutivos e a cache nunca acertava.
        """
        from services.stats_scope import sufixo_de_cache

        uma = self._scope(network_ids=("r1", "r2"), company_names=("B", "A"))
        outra = self._scope(network_ids=("r2", "r1"), company_names=("A", "B"))
        assert sufixo_de_cache(uma) == sufixo_de_cache(outra)

    def test_empresas_diferentes_na_mesma_rede_dao_sufixos_diferentes(self):
        """A condição de filtro inclui ramos por EMPRESA, não só por rede.

        Duas pessoas na mesma rede e em empresas diferentes têm condições
        diferentes: partilhar a entrada da cache servia a uma os números
        filtrados para a outra.
        """
        from services.stats_scope import sufixo_de_cache

        power = self._scope(network_ids=(REDE_INCUMBENTE,), company_ids=("cmp-power",))
        precision = self._scope(
            network_ids=(REDE_INCUMBENTE,), company_ids=("cmp-precision",),
        )
        assert sufixo_de_cache(power) != sufixo_de_cache(precision)

    def test_a_bandeira_da_rede_de_omissao_conta(self):
        """Incluir ou não a pilha por carimbar muda o conjunto medido."""
        from services.stats_scope import sufixo_de_cache

        com = self._scope(network_ids=("r1",), inclui_rede_de_omissao=True)
        sem = self._scope(network_ids=("r1",), inclui_rede_de_omissao=False)
        assert sufixo_de_cache(com) != sufixo_de_cache(sem)

    def test_o_sufixo_e_seguro_numa_chave_de_redis(self):
        """Nomes de empresa têm espaços e acentos; a chave não pode tê-los."""
        from services.stats_scope import sufixo_de_cache

        scope = self._scope(company_names=("Precision Crédito", "Domus"))
        sufixo = sufixo_de_cache(scope)
        assert " " not in sufixo
        assert sufixo.isascii()
        assert len(sufixo) <= 24


class TestComAmbito:
    def _ambito(self):
        from services.stats_scope import AmbitoEstatistico
        from services.tenant_network import TenantScope

        return AmbitoEstatistico(
            scope=TenantScope(network_ids=("r1",)),
            condicao={"network_id": {"$in": ["r1"]}},
            sufixo="a1deadbeefdeadbe",
        )

    def test_junta_por_and(self):
        from services.stats_scope import com_ambito

        query = com_ambito({"is_deleted": {"$ne": True}}, self._ambito())
        assert query == {
            "$and": [
                {"network_id": {"$in": ["r1"]}},
                {"is_deleted": {"$ne": True}},
            ]
        }

    def test_nao_apaga_um_or_que_ja_exista(self):
        """A fusão de dicionários apagava a visibilidade por papel.

        E em silêncio: a query continuava válida e devolvia MAIS.
        """
        from services.stats_scope import com_ambito

        original = {"$or": [{"assigned_consultor_id": "u-1"}]}
        query = com_ambito(original, self._ambito())
        assert original in query["$and"]

    def test_query_vazia_fica_so_com_o_ambito(self):
        from services.stats_scope import com_ambito

        assert com_ambito({}, self._ambito()) == {"network_id": {"$in": ["r1"]}}

    def test_a_chave_leva_o_sufixo(self):
        ambito = self._ambito()
        assert ambito.chave("stats:branches:v3").endswith(ambito.sufixo)


class TestProcessosNoAmbito:
    async def test_devolve_so_os_da_rede(self, db_tenant, rede_de_omissao_incumbente):
        from services.stats_scope import processos_no_ambito, resolver_ambito
        import services.stats_scope as ss

        with tenant_db(db_tenant, ss):
            ambito = await resolver_ambito(BRUNO)
            permitidos = await processos_no_ambito(
                ["p-power", "p-domus", "p-legado"], ambito,
            )

        assert permitidos == {"p-domus"}

    async def test_sem_ids_devolve_vazio_e_nao_consulta(
        self, db_tenant, rede_de_omissao_incumbente,
    ):
        """Fail-closed: um "sem filtro" aqui devolvia tudo."""
        from services.stats_scope import processos_no_ambito, resolver_ambito
        import services.stats_scope as ss

        with tenant_db(db_tenant, ss):
            ambito = await resolver_ambito(BRUNO)
            assert await processos_no_ambito([], ambito) == set()
            assert await processos_no_ambito(None, ambito) == set()

    async def test_uma_so_consulta_para_muitos_ids(
        self, db_tenant, rede_de_omissao_incumbente,
    ):
        """O sentido barato: o `$in` é limitado pela colecção PEQUENA."""
        from services.stats_scope import processos_no_ambito, resolver_ambito
        import services.stats_scope as ss

        chamadas = []
        original = db_tenant.processes.find

        def contar(query, projeccao=None):
            chamadas.append(query)
            return original(query, projeccao)

        with tenant_db(db_tenant, ss):
            ambito = await resolver_ambito(ANA)
            with patch.object(db_tenant.processes, "find", contar):
                await processos_no_ambito([f"p-{i}" for i in range(50)], ambito)

        assert len(chamadas) == 1


# ════════════════════════════════════════════════════════════════════
# /stats — A FUGA NOS KPIs
# ════════════════════════════════════════════════════════════════════

class TestFugaNosKPIs:
    async def _stats(self, db_tenant, user):
        # `admin_users_scope` entra SEMPRE na cadeia, não só nos testes de
        # contagem de utilizadores: um papel admin/ceo passa por lá para as
        # seis contagens. Sem o patch, o teste do utilizador órfão (que é
        # admin) falava com o proxy real — passava isolado e rebentava na
        # bateria completa com "Event loop is closed". É o defeito de ordem
        # de import descrito no AGENTS.md, e foi assim que apareceu.
        import services.admin_users_scope as aus
        import services.stats_overview as so
        import services.stats_scope as ss

        with tenant_db(db_tenant, so, ss, aus):
            return await so.run_get_stats(dict(user))

    async def test_a_diretora_da_domus_nao_conta_os_processos_da_power(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """A fuga, afirmada.

        Bruno é Diretor da Domus. Antes disto a query base era `{}` mais
        um filtro por PAPEL, e o papel dele não restringe nada — via os
        totais da Power no seu próprio Dashboard.
        """
        stats = await self._stats(db_tenant, BRUNO)

        # Só `p-domus`. O `p-domus-sem-rede` tem empresa da Domus e entra
        # pelo ramo da empresa; o `p-power` e o `p-legado` não.
        assert stats["total_processes"] == 2

    async def test_a_diretora_da_power_ve_a_sua_rede_e_a_pilha_antiga(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """Contraprova: o filtro isola, não esvazia.

        Ana vê `p-power` e `p-legado` — a pilha por carimbar pertence à
        rede de omissão, que em produção é a do grupo incumbente.
        """
        stats = await self._stats(db_tenant, ANA)

        assert stats["total_processes"] == 2

    async def test_quem_trabalha_nas_duas_redes_ve_as_duas(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """A Carla não é uma fuga: são os dois empregos dela.

        Mas é consultora, e o filtro por atribuição aplica-se por cima —
        nenhum destes processos lhe está atribuído.
        """
        stats = await self._stats(db_tenant, CARLA)

        assert stats["total_processes"] == 0

    async def test_o_utilizador_orfao_nao_ve_a_domus(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """Conta antiga sem empresa: cai na rede de omissão, não em "tudo"."""
        stats = await self._stats(db_tenant, ORFAO)

        assert stats["total_processes"] == 2

    async def test_os_prazos_abertos_seguem_a_rede(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """Apanhado por mutação (N11): a contagem de prazos não tinha teste.

        Era `{"completed": False}` — todos os prazos abertos de todas as
        redes. E o mutante que trocava `processos_no_ambito(ids, ambito)`
        por `ids` passava, porque nenhum teste semeava prazos.
        """
        db_tenant.deadlines.docs.extend([
            {"id": "d-power", "process_id": "p-power", "completed": False},
            {"id": "d-domus", "process_id": "p-domus", "completed": False},
            {"id": "d-domus-2", "process_id": "p-domus", "completed": False},
            # Prazo pessoal do Bruno (sem processo): conta para ele.
            {"id": "d-bruno", "process_id": None, "completed": False,
             "created_by": "u-bruno"},
            # Prazo pessoal da Ana: NÃO conta para o Bruno. Antes contava
            # — o cartão da Direção somava os lembretes de todos.
            {"id": "d-ana", "process_id": None, "completed": False,
             "created_by": "u-ana"},
            # Fechado: nunca conta.
            {"id": "d-feito", "process_id": "p-domus", "completed": True},
        ])

        stats = await self._stats(db_tenant, BRUNO)

        assert stats["pending_deadlines"] == 3

    async def test_o_distinct_dos_prazos_e_so_dos_abertos(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """Contrato de CUSTO, não de resultado (mutação N24).

        Trocar o filtro do `distinct` por `{}` não muda a contagem — o
        `count_documents` final continua a filtrar `completed: False`. Muda
        o CUSTO: o conjunto de candidatos passa a incluir os processos que
        só têm prazos já fechados, e é esse conjunto que vai para o `$in`
        da verificação de rede. O mesmo tipo de contrato que se afirma na
        presença global com "uma chamada para 50 utilizadores".
        """
        import services.stats_overview as so
        import services.stats_scope as ss

        filtros = []
        original = db_tenant.deadlines.distinct

        async def espiar(chave, query=None):
            filtros.append(query)
            return await original(chave, query)

        db_tenant.deadlines.docs.append(
            {"id": "d-feito", "process_id": "p-domus", "completed": True},
        )

        with tenant_db(db_tenant, so, ss):
            with patch.object(db_tenant.deadlines, "distinct", espiar):
                await so.run_get_stats(dict(BRUNO))

        assert filtros == [{"completed": False}]

    async def test_o_prazo_pessoal_de_outro_nao_conta(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """A mudança de significado, afirmada de forma isolada."""
        db_tenant.deadlines.docs.append(
            {"id": "d-ana", "process_id": None, "completed": False,
             "created_by": "u-ana"},
        )

        stats = await self._stats(db_tenant, BRUNO)

        assert stats["pending_deadlines"] == 0

    async def test_a_chave_do_utilizador_muda_quando_o_ambito_dele_muda(
        self, db_tenant, rede_de_omissao_incumbente,
    ):
        """O MESMO utilizador, dois âmbitos. Teste reescrito após mutação.

        A primeira versão comparava a chave do Bruno com a da Ana — que
        são utilizadores diferentes e por isso já tinham chaves diferentes
        sem sufixo nenhum. Afirmava algo verdadeiro também no código
        antigo, que é a definição de teste fraco (e foi assim que o
        mutante que apaga o sufixo lhe passou por baixo).

        O que interessa é isto: o TTL é de **24 horas**. Tirar alguém de
        uma empresa mudava-lhe o âmbito e o Dashboard continuava a
        servir-lhe os números antigos até ao dia seguinte. Com o sufixo, a
        mudança estreia uma chave nova no primeiro pedido.
        """
        import services.stats_overview as so
        import services.stats_scope as ss

        chaves = []

        async def cache_get(chave, *a, **k):
            chaves.append(chave)
            return None

        with tenant_db(db_tenant, so, ss):
            with patch.object(so, "cache_get", cache_get), \
                 patch.object(so, "cache_set", AsyncMock(return_value=True)):
                await so.run_get_stats(dict(BRUNO))

                # O Bruno muda de empresa: sai da Domus, entra na Power.
                for ucr in db_tenant.user_company_roles.docs:
                    if ucr["user_id"] == "u-bruno":
                        ucr["company_id"] = "cmp-power"
                        ucr["company_name"] = "Power Real Estate"

                # A resolução do âmbito é por pedido (não há cache dela),
                # por isso a segunda chamada já vê a associação nova.
                await so.run_get_stats(dict(BRUNO))

        assert chaves[0] != chaves[1], (
            "a chave não reagiu à mudança de âmbito do MESMO utilizador"
        )
        # O padrão de invalidação (`stats:user:{id}:*`) tem de a apanhar.
        assert all(c.startswith("stats:user:u-bruno:") for c in chaves)

    async def test_as_contagens_de_utilizadores_seguem_a_rede(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        """"Ser Admin significa ser Admin da sua REDE" (decisão do dono).

        O painel de administração já contava assim desde o Lote 5; o
        cartão do Dashboard contava `db.users` inteira e contradizia-o.
        """
        import services.admin_users_scope as aus
        import services.stats_overview as so
        import services.stats_scope as ss

        for u in (dict(ANA, role="admin"), dict(BRUNO, role="admin")):
            db_tenant.users.docs.append(dict(u, is_active=True))
        db_tenant.users.docs.append(
            {"id": "u-solta", "name": "Solta", "role": "consultor",
             "company": "Power Real Estate", "is_active": True},
        )

        with tenant_db(db_tenant, so, ss, aus):
            stats_domus = await so.run_get_stats(dict(BRUNO, role="admin"))
            stats_power = await so.run_get_stats(dict(ANA, role="admin"))


        assert stats_domus["total_users"] < stats_power["total_users"]
        assert stats_domus["total_users"] == 1


# ════════════════════════════════════════════════════════════════════
# /stats/communications — A FUGA DE CONTEÚDO
# ════════════════════════════════════════════════════════════════════

class TestFugaNasComunicacoes:
    @pytest.fixture
    def com_mensagens(self, db_tenant):
        db_tenant.portal_messages.docs.extend([
            {"id": "m-power", "process_id": "p-power", "read_by_staff": False,
             "sender_name": "Cliente da Power", "created_at": "2026-09-20T10:00:00Z",
             "content": "Envio em anexo o meu IRS e o recibo de vencimento."},
            {"id": "m-domus", "process_id": "p-domus", "read_by_staff": False,
             "sender_name": "Cliente da Domus", "created_at": "2026-09-21T10:00:00Z",
             "content": "Quando é a escritura?"},
        ])
        db_tenant.emails.docs.extend([
            {"id": "e-power", "process_id": "p-power", "is_read": False,
             "subject": "Proposta do banco para o cliente da Power",
             "from_address": "banco@exemplo.pt", "received_at": "2026-09-20T09:00:00Z"},
            {"id": "e-domus", "process_id": "p-domus", "is_read": False,
             "subject": "Escritura Domus", "from_address": "notario@exemplo.pt",
             "received_at": "2026-09-21T09:00:00Z"},
            # Email sem processo: não se consegue atribuir a uma rede.
            {"id": "e-geral", "process_id": None, "is_read": False,
             "subject": "Newsletter", "from_address": "news@exemplo.pt",
             "received_at": "2026-09-22T09:00:00Z"},
        ])
        return db_tenant

    async def _feed(self, db, user):
        import services.stats_communications as sc
        import services.stats_scope as ss

        with tenant_db(db, sc, ss):
            return await sc.run_get_communications_feed(dict(user))

    async def test_o_diretor_da_domus_nao_le_as_mensagens_da_power(
        self, com_mensagens, rede_de_omissao_incumbente,
    ):
        """A pior das seis fugas: isto devolve CONTEÚDO, não contagens."""
        feed = await self._feed(com_mensagens, BRUNO)

        ids = {m["id"] for m in feed["portal_messages"]}
        assert ids == {"m-domus"}
        textos = " ".join(m["content"] for m in feed["portal_messages"])
        assert "IRS" not in textos

    async def test_nem_os_assuntos_dos_emails(
        self, com_mensagens, rede_de_omissao_incumbente,
    ):
        feed = await self._feed(com_mensagens, BRUNO)

        assuntos = " ".join(e["subject"] for e in feed["unread_emails"])
        assert "Power" not in assuntos

    async def test_as_contagens_tambem_sao_por_rede(
        self, com_mensagens, rede_de_omissao_incumbente,
    ):
        """Filtrar a lista e deixar o cartão de KPI global era meia correcção."""
        feed = await self._feed(com_mensagens, BRUNO)

        assert feed["portal_unread_count"] == 1
        assert feed["email_unread_count"] == 1

    async def test_a_diretora_da_power_ve_as_suas(
        self, com_mensagens, rede_de_omissao_incumbente,
    ):
        """Contraprova: isolar não é esvaziar."""
        feed = await self._feed(com_mensagens, ANA)

        assert {m["id"] for m in feed["portal_messages"]} == {"m-power"}
        assert {e["id"] for e in feed["unread_emails"]} == {"e-power"}

    async def test_email_sem_processo_nao_entra(
        self, com_mensagens, rede_de_omissao_incumbente,
    ):
        """`db.emails` não é carimbada; o âmbito vem do PROCESSO do email.

        Consequência assumida: um email sem processo não se consegue
        atribuir a uma rede e por isso não se mostra a nenhuma. Era já o
        que acontecia aos consultores.
        """
        feed = await self._feed(com_mensagens, ANA)

        assert "e-geral" not in {e["id"] for e in feed["unread_emails"]}

    async def test_o_cliente_continua_sem_ver_nada(self, com_mensagens):
        feed = await self._feed(com_mensagens, {"id": "c-1", "role": "cliente"})

        assert feed["portal_messages"] == []
        assert feed["unread_emails"] == []


# ════════════════════════════════════════════════════════════════════
# /stats/branches — A AGREGAÇÃO E A CHAVE DE CACHE
# ════════════════════════════════════════════════════════════════════

class TestFugaNosBalcoes:
    @pytest.fixture
    def capturar(self):
        """Captura o pipeline e a chave de cache sem correr a agregação.

        A fake não sabe `$project` com `$in`/`$cond`, e o que interessa
        aqui é o PRIMEIRO estágio: a fronteira de rede tem de estar no
        `$match` inicial, antes do `$group`. Um `$match` depois do grupo
        já teria somado os processos da outra rede.
        """
        pipelines, chaves = [], []

        def aggregate(pipeline, **kwargs):
            pipelines.append(pipeline)
            raise RuntimeError("agregação não corre neste teste")

        async def cache_get(chave, *a, **k):
            chaves.append(chave)
            return None

        return pipelines, chaves, aggregate, cache_get

    async def _balcoes(self, db, user, capturar):
        import services.stats_branches as sb
        import services.stats_scope as ss

        pipelines, chaves, aggregate, cache_get = capturar
        with tenant_db(db, sb, ss):
            with patch.object(db.processes, "aggregate", aggregate), \
                 patch.object(sb, "cache_get", cache_get), \
                 patch.object(sb, "cache_set", AsyncMock(return_value=True)), \
                 patch("models.permissions.resolve_capability", return_value=True):
                await sb.run_get_branch_performance(dict(user))
        return pipelines, chaves

    async def test_a_rede_entra_no_primeiro_match(
        self, db_tenant, rede_de_omissao_incumbente, capturar,
    ):
        pipelines, _ = await self._balcoes(db_tenant, BRUNO, capturar)

        primeiro = pipelines[0][0]["$match"]
        assert "$and" in primeiro
        texto = repr(primeiro)
        assert REDE_DOMUS in texto
        assert REDE_INCUMBENTE not in texto

    async def test_a_chave_de_cache_muda_com_a_rede(
        self, db_tenant, rede_de_omissao_incumbente, capturar,
    ):
        """Com a chave global, o primeiro pedido semeava a cache para todos.

        O filtro funcionava perfeitamente e os números vinham da outra
        rede pelo Redis.
        """
        # O `capturar` acumula nas MESMAS listas nas duas chamadas: a
        # chave do Bruno é a primeira e a da Ana a segunda.
        await self._balcoes(db_tenant, BRUNO, capturar)
        _, chaves = await self._balcoes(db_tenant, ANA, capturar)

        assert len(chaves) == 2
        assert chaves[0] != chaves[1]

    async def test_a_chave_antiga_nao_e_servida(
        self, db_tenant, rede_de_omissao_incumbente, capturar,
    ):
        """`stats:branches:v2` ficou para trás: tinha semântica global."""
        _, chaves = await self._balcoes(db_tenant, ANA, capturar)

        assert chaves[0] != "stats:branches:v2"
        assert chaves[0].startswith("stats:branches:v3:")


# ════════════════════════════════════════════════════════════════════
# /stats/leads — O CARIMBO NA ESCRITA
# ════════════════════════════════════════════════════════════════════

class TestCarimboNasLeads:
    async def test_a_lead_nasce_com_a_rede(self, db_tenant):
        """Sem campo por onde filtrar, `/stats/leads` media a colecção toda."""
        import services.lead_crud as lc
        import services.tenant_network as tn

        class Dados:
            """O mínimo que o `run_create_lead` lê: `.url` e `.model_dump()`."""

            url = "https://exemplo.pt/x"

            def model_dump(self):
                return {"title": "T3 em Lisboa", "url": self.url}

        with tenant_db(db_tenant, lc):
            with patch.object(tn, "db", db_tenant):
                await lc.run_create_lead(
                    Dados(), dict(BRUNO, active_company_id="cmp-domus"),
                )

        assert db_tenant.property_leads.docs[0]["network_id"] == REDE_DOMUS

    async def test_os_dois_caminhos_de_escrita_carimbam(self):
        """Carimbar só um deixava as leads do outro na rede de omissão.

        Guarda sobre o código-fonte: os dois sítios de `insert_one` em
        `property_leads` têm de resolver o carimbo. Um carimbo parcial é
        pior do que nenhum, porque a metade sem marca fica visível ao
        grupo incumbente para sempre.
        """
        for nome in ("lead_crud", "lead_extract"):
            fonte = codigo_sem_comentarios(
                (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
            )
            assert "db.property_leads.insert_one" in fonte, nome
            assert "resolve_tenant_stamp" in fonte, nome

    async def test_as_contagens_de_leads_seguem_a_rede(
        self, db_tenant, rede_de_omissao_incumbente, sem_cache,
    ):
        import services.stats_leads as sl
        import services.stats_scope as ss

        db_tenant.property_leads.docs.extend([
            {"id": "l-power", "status": "novo", "source": "idealista",
             "network_id": REDE_INCUMBENTE, "created_by_id": "u-ana"},
            {"id": "l-domus", "status": "novo", "source": "imovirtual",
             "network_id": REDE_DOMUS, "created_by_id": "u-bruno"},
        ])

        with tenant_db(db_tenant, sl, ss):
            domus = await sl.run_get_leads_stats(dict(BRUNO))
            power = await sl.run_get_leads_stats(dict(ANA))

        assert domus["total_leads"] == 1
        assert power["total_leads"] == 1
        assert [s["source"] for s in domus["leads_by_source"]] == ["imovirtual"]

    async def test_a_conversao_tem_chave_de_cache_por_ambito(
        self, db_tenant, rede_de_omissao_incumbente,
    ):
        import services.stats_conversion as sc
        import services.stats_scope as ss

        chaves = []

        async def cache_get(chave, *a, **k):
            chaves.append(chave)
            return None

        with tenant_db(db_tenant, sc, ss):
            with patch.object(sc, "cache_get", cache_get), \
                 patch.object(sc, "cache_set", AsyncMock(return_value=True)):
                await sc.run_get_conversion_stats(dict(BRUNO))
                await sc.run_get_conversion_stats(dict(ANA))

        assert chaves[0] != chaves[1]
        assert all(c != "stats:global:conversion" for c in chaves)


# ════════════════════════════════════════════════════════════════════
# Desempenho da Equipa — PESSOAS, NÃO NÚMEROS
# ════════════════════════════════════════════════════════════════════

class TestFugaNoDesempenhoDaEquipa:
    @pytest.fixture
    def equipa(self, db_tenant):
        db_tenant.users.docs.extend([
            {"id": "u-ana", "name": "Ana", "email": "ana@power.pt",
             "role": "diretor", "is_active": True, "company": "Power Real Estate"},
            {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt",
             "role": "diretor", "is_active": True, "company": "Domus"},
        ])
        return db_tenant

    async def test_o_relatorio_de_uma_rede_nao_traz_as_pessoas_da_outra(
        self, equipa, rede_de_omissao_incumbente,
    ):
        """Nome, email e produtividade de cada pessoa. É o pior tipo de fuga."""
        import services.admin_users_scope as aus
        import services.analytics_service as ans

        with tenant_db(equipa, aus):
            relatorio = await ans.generate_weekly_team_report(equipa, user=dict(BRUNO))

        emails = {u["email"] for u in relatorio["users"]}
        assert "ana@power.pt" not in emails
        assert "bruno@domus.pt" in emails

    async def test_sem_utilizador_mantem_o_ambito_global_e_avisa(
        self, equipa, caplog,
    ):
        """O email automático de Segunda não tem quem peça.

        Fica global como estava — passar a um email POR REDE é uma
        decisão de produto — mas nunca em silêncio.
        """
        import logging

        import services.admin_users_scope as aus
        import services.analytics_service as ans

        with caplog.at_level(logging.WARNING):
            with tenant_db(equipa, aus):
                relatorio = await ans.generate_weekly_team_report(equipa)

        assert len(relatorio["users"]) == 2
        assert any("âmbito global" in r.message for r in caplog.records)

    async def test_o_endpoint_passa_o_utilizador(self):
        """Contraprova: sem isto o parâmetro novo era decorativo."""
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / "admin_observability.py").read_text(
                encoding="utf-8",
            )
        )
        assert "generate_weekly_team_report(" in fonte
        assert "user=user" in fonte


# ════════════════════════════════════════════════════════════════════
# GUARDA DO PONTO ÚNICO
# ════════════════════════════════════════════════════════════════════

class TestGuardaDoPontoUnico:
    """Nenhum módulo de estatísticas reconstrói a condição à mão.

    Foi tê-la duplicada que produziu o incidente da conta de envio
    (2026-09-21) e o placebo do Lote 4. A guarda é sobre o código-fonte
    porque um `db` falseado não distingue quem pediu a condição ao ponto
    único de quem a escreveu à mão com os mesmos campos.
    """

    @pytest.mark.parametrize("nome", MODULOS_DE_ESTATISTICAS)
    def test_o_modulo_pede_o_ambito_ao_ponto_unico(self, nome):
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
        )
        assert "from services.stats_scope import" in fonte, nome
        assert "resolver_ambito" in fonte, nome

    @pytest.mark.parametrize("nome", MODULOS_DE_ESTATISTICAS)
    def test_o_modulo_nao_escreve_a_condicao_a_mao(self, nome):
        """`network_id` escrito à mão num módulo de BI é a cadeia duplicada."""
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
        )
        assert "network_id" not in fonte, nome
        assert "build_network_scope_condition" not in fonte, nome

    def test_o_ponto_unico_usa_mesmo_o_tenant_network(self):
        """Contraprova: sem isto, um `stats_scope` vazio satisfazia tudo."""
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / "stats_scope.py").read_text(encoding="utf-8")
        )
        assert "build_network_scope_condition" in fonte
        assert "resolve_tenant_scope" in fonte


# ════════════════════════════════════════════════════════════════════
# A INVALIDAÇÃO TEM DE ACERTAR NAS CHAVES NOVAS
# ════════════════════════════════════════════════════════════════════

class TestInvalidacaoDasChavesGlobais:
    """Pôr o âmbito na chave global quase quebrou a invalidação cirúrgica.

    O `invalidate_stats_cache` apagava as chaves globais por NOME EXACTO
    (`stats:global:conversion`). Com o sufixo do âmbito, esse nome deixa de
    existir: a invalidação ficava silenciosamente sem efeito e as
    estatísticas ficavam 24h desactualizadas depois de cada mutação. Não é
    uma fuga — é uma correcção de segurança a estragar uma correcção de
    frescura, que é o género de dano que passa sem ninguém ver.
    """

    def test_o_padrao_cobre_a_chave_base_e_as_por_ambito(self):
        import fnmatch

        from services.redis_cache import (
            GLOBAL_KEY_PATTERNS,
            STATS_GLOBAL_CONVERSION_KEY,
        )

        padrao = GLOBAL_KEY_PATTERNS[0]
        assert fnmatch.fnmatch(STATS_GLOBAL_CONVERSION_KEY, padrao)
        assert fnmatch.fnmatch(
            f"{STATS_GLOBAL_CONVERSION_KEY}:a1deadbeefdeadbe", padrao,
        )

    def test_o_padrao_nao_apanha_as_chaves_de_utilizador(self):
        """Apagar `stats:user:*` aqui deitava fora a cache de toda a gente."""
        import fnmatch

        from services.redis_cache import GLOBAL_KEY_PATTERNS

        assert not fnmatch.fnmatch(
            "stats:user:u-ana:kpis", GLOBAL_KEY_PATTERNS[0],
        )

    async def test_invalidar_apaga_por_padrao(self):
        """Comportamento, não só o padrão: o `delete` recebe a chave com sufixo."""
        from unittest.mock import MagicMock

        import services.redis_cache as rc

        apagadas = []
        falso = MagicMock()

        async def keys(padrao):
            return [f"{rc.STATS_GLOBAL_CONVERSION_KEY}:a1abcdefabcdefab"]

        async def delete(*chaves):
            apagadas.extend(chaves)
            return len(chaves)

        falso.keys = keys
        falso.delete = delete

        with patch.object(rc, "get_redis", return_value=falso):
            await rc.invalidate_stats_cache()

        assert any(c.endswith("a1abcdefabcdefab") for c in apagadas)
