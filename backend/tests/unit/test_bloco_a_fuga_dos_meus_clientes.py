"""
Bloco A, ponto 1 — «Os Meus Clientes» atravessava redes (Out 2026).

O RELATO
  Um utilizador criado numa rede nova (Domus), com zero dados, abria «Os
  Meus Clientes» e via 50 clientes da rede principal.

A CAUSA (não era a rede de omissão)
  `build_my_clients_process_query` devolve `{}` para o diretor e o
  administrativo — «todos os meus, que são todos». Nenhuma das listagens
  de «Os Meus Clientes» passava pela condição de rede, por isso `{}` era
  mesmo a colecção inteira, e o tamanho de página por omissão (50) é o
  número que o utilizador contou. Cada uma das cinco superfícies abaixo
  lia `db.processes` sem perguntar a rede a ninguém:

    GET /processes/my-clients   (a que o ecrã usa)
    GET /my-clients  e  /my-clients/stats
    GET /clients/me
    GET /documents/expiring-dashboard, /documents/expiries*,
        /documents/check-employer-nif, /processes/dsti-alerts,
        /emails/notifications/unread, /ai-bulk/clients*, pending-reviews

  É a quinta vez nesta casa que o inventário das superfícies que LISTAM
  fica incompleto (Kanban, notificações, tarefas, visitas, carteira).
  `TestInventarioDasListagens` é o inventário que falha por omissão.

A REDE DE OMISSÃO
  Um utilizador com empresa em OUTRA rede não herda a rede de omissão
  (`TestRedeDeOmissaoNaoSeHerda`). O que herda é o órfão — conta sem
  empresa nenhuma, só possível em contas antigas — e isso é desenho.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    CARLA,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]

# Muitos clientes ao mesmo tempo, como no relato: se a condição de rede
# faltar, a Domus vê TODOS. Com um só processo da Power o teste passaria
# por sorte do `limit`.
PROCESSOS_EXTRA = [
    {
        "id": f"p-power-{n}", "client_name": f"Cliente {n:02d} da Power",
        "status": "novo", "is_active": True,
        "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
        "assigned_consultor_ids": ["u-ana"], "assigned_consultor_id": "u-ana",
    }
    for n in range(60)
]
PROCESSO_DA_DOMUS = {
    "id": "p-domus-bruno", "client_name": "Cliente da Domus", "status": "novo",
    "is_active": True, "company_id": "cmp-domus", "network_id": REDE_DOMUS,
}


def _cenario(fake_db):
    db = semear(fake_db)
    db.processes.docs.clear()
    db.processes.docs.extend(dict(p) for p in PROCESSOS_EXTRA)
    db.processes.docs.append(dict(PROCESSO_DA_DOMUS))
    # Um legado sem carimbo: só a rede de omissão o vê.
    db.processes.docs.append(
        {"id": "p-legado", "client_name": "Cliente Antigo", "status": "novo", "is_active": True}
    )
    db.workflow_statuses.docs.append(
        {"name": "novo", "label": "Novo", "order": 1, "is_active": True},
    )
    return db


def _ids(linhas) -> set:
    return {linha.get("id") for linha in linhas}


@pytest.fixture(autouse=True)
def _omissao_incumbente(monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)


# ════════════════════════════════════════════════════════════════════
# GET /processes/my-clients — a que o ecrã usa
# ════════════════════════════════════════════════════════════════════
async def _meus_clientes_do_ecra(db, user, role):
    import services.process_my_clients as pmc
    from routes.processes import (
        PROCESS_MY_CLIENTS_PROJECTION,
        build_my_clients_leads_query,
        build_my_clients_process_query,
        decrypt_processes_list,
        slice_page,
    )

    async def _mapa():
        return {"novo": {"label": "Novo", "color": "#000"}}

    import services.document_novelty as novidade

    # `document_novelty` importa o `db` no topo: sem este patch, o resultado
    # depende da ORDEM em que o pytest recolheu os ficheiros (a armadilha
    # do `from database import db` ao nível do módulo).
    with patch.object(pmc, "db", db, create=True), patch.object(novidade, "db", db):
        return await pmc.run_get_my_clients(
            db=db, user=user, role=role, page=1, size=50,
            decrypt_list_fn=decrypt_processes_list,
            my_clients_projection=PROCESS_MY_CLIENTS_PROJECTION,
            build_process_query_fn=build_my_clients_process_query,
            build_leads_query_fn=build_my_clients_leads_query,
            slice_page_fn=slice_page,
            load_status_map_fn=_mapa,
        )


class TestAExploracaoDoRelato:
    """O ataque: o utilizador novo da Domus abre «Os Meus Clientes»."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["diretor", "administrativo"])
    async def test_a_domus_nao_ve_um_unico_cliente_da_power(self, fake_async_db, papel):
        db = _cenario(fake_async_db)
        with tenant_db(db):
            resposta = await _meus_clientes_do_ecra(db, BRUNO, papel)

        vistos = _ids(resposta["clients"])
        fugas = {i for i in vistos if i.startswith("p-power") or i == "p-legado"}
        assert not fugas, f"FUGA: a Domus vê {len(fugas)} clientes de outra rede"
        # E vê o que é dela — esvaziar a lista a toda a gente passaria no
        # assert acima.
        assert "p-domus-bruno" in vistos

    @pytest.mark.asyncio
    async def test_a_power_continua_a_ver_os_seus(self, fake_async_db):
        """Contraprova: a correcção não pode esvaziar a rede incumbente."""
        db = _cenario(fake_async_db)
        with tenant_db(db):
            resposta = await _meus_clientes_do_ecra(db, ANA, "diretor")

        vistos = _ids(resposta["clients"])
        assert sum(1 for i in vistos if i.startswith("p-power")) == 50  # 1.ª página
        assert "p-domus-bruno" not in vistos
        assert resposta["total"] >= 60

    @pytest.mark.asyncio
    async def test_uma_rede_nova_sem_dados_ve_uma_lista_vazia(self, fake_async_db):
        """Exactamente o relato: «zero dados» tem de ser zero clientes."""
        db = _cenario(fake_async_db)
        db.processes.docs[:] = [p for p in db.processes.docs if p["id"] != "p-domus-bruno"]
        with tenant_db(db):
            resposta = await _meus_clientes_do_ecra(db, BRUNO, "diretor")

        assert resposta["clients"] == []
        assert resposta["total"] == 0


# ════════════════════════════════════════════════════════════════════
# GET /my-clients, /my-clients/stats, /clients/me
# ════════════════════════════════════════════════════════════════════
class TestOutrasSuperficiesDeMeusClientes:
    @pytest.mark.asyncio
    async def test_my_clients_nao_atravessa_redes(self, fake_async_db):
        import services.my_clients_api_list as lista
        from starlette.requests import Request

        db = _cenario(fake_async_db)
        pedido = Request({"type": "http", "headers": [], "query_string": b""})
        import services.document_novelty as novidade

        with tenant_db(db, lista, novidade), patch.object(lista, "get_effective_role", create=True), \
                patch("services.my_clients_api_helpers.get_effective_role", lambda r, u: "diretor"):
            resposta = await lista.run_get_my_clients(pedido, BRUNO)

        vistos = _ids(resposta["clients"])
        assert not {i for i in vistos if i.startswith("p-power") or i == "p-legado"}
        assert "p-domus-bruno" in vistos

    @pytest.mark.asyncio
    async def test_my_clients_stats_nao_conta_processos_de_outra_rede(self, fake_async_db):
        import services.my_clients_api_stats as stats

        db = _cenario(fake_async_db)
        # A fake não implementa `aggregate` com `$group`: o que se mede é a
        # CONDIÇÃO que sai para o pipeline, que é o que decide a fuga.
        vistos: list = []

        class _Cursor:
            async def to_list(self, n):
                return []

        def _aggregate(pipeline):
            vistos.append(pipeline)
            return _Cursor()

        with tenant_db(db, stats), patch.object(stats, "db", db):
            db.processes.aggregate = _aggregate
            await stats.run_get_my_clients_stats({**BRUNO, "role": "diretor"})

        match = vistos[0][0]["$match"]
        assert not [d for d in db.processes.docs if _casa(d, match) and d["id"] != "p-domus-bruno"], \
            "FUGA: as estatísticas contam processos de outra rede"

    @pytest.mark.asyncio
    async def test_clients_me_nao_atravessa_redes(self, fake_async_db):
        import services.client_me as me
        from starlette.requests import Request

        db = _cenario(fake_async_db)
        pedido = Request({"type": "http", "headers": [], "query_string": b""})
        with tenant_db(db, me), patch.object(me, "get_effective_role", lambda r, u: "diretor"):
            resposta = await me.run_get_my_assigned_clients(pedido, BRUNO)

        vistos = _ids(resposta["clients"])
        assert not {i for i in vistos if i.startswith("p-power") or i == "p-legado"}
        assert "p-domus-bruno" in vistos


def _casa(doc, condicao):
    from tests.unit.helpers_tenant import casa

    return casa(doc, condicao)


# ════════════════════════════════════════════════════════════════════
# As outras listagens que liam `db.processes` sem rede
# ════════════════════════════════════════════════════════════════════
class TestListagensDeDocumentosENotificacoes:
    @pytest.mark.asyncio
    async def test_dsti_nao_lista_processos_de_outra_rede(self, fake_async_db):
        import services.process_dsti as dsti

        db = _cenario(fake_async_db)
        for p in db.processes.docs:
            p["financial_data"] = {"rendimento_bruto_mensal": 1000}
        capturadas: list = []
        original = db.processes.find

        def _find(query, *a, **k):
            capturadas.append(query)
            return original(query, *a, **k)

        db.processes.find = _find

        class _Cfg:
            class dsti_analysis:  # noqa: N801
                enabled = True
                high_risk_threshold = 0

        async def _cfg():
            return _Cfg()

        with tenant_db(db, dsti), patch.object(dsti, "db", db), \
                patch("services.system_config.get_system_config", _cfg):
            await dsti.run_get_dsti_high_risk_processes(BRUNO)

        assert capturadas, "a consulta não correu"
        apanhados = {d["id"] for d in db.processes.docs if _casa(d, capturadas[0])}
        assert apanhados == {"p-domus-bruno"}

    @pytest.mark.asyncio
    async def test_nif_de_empresa_nao_revela_clientes_de_outra_rede(self, fake_async_db):
        import services.document_misc as misc

        db = _cenario(fake_async_db)
        db.processes.docs[0]["personal_data"] = {"employer_nif": "500100200"}
        with tenant_db(db, misc), patch.object(misc, "db", db):
            resposta = await misc.run_check_employer_nif("500100200", BRUNO)

        assert "Cliente 00 da Power" not in str(resposta), "FUGA: nome de cliente de outra rede"

    @pytest.mark.asyncio
    async def test_validades_de_documentos_so_da_propria_rede(self, fake_async_db):
        import services.document_expiry_crud as exp

        db = _cenario(fake_async_db)
        db.document_expiries.docs.extend([
            {"id": "e-power", "process_id": "p-power-0", "expiry_date": "2030-01-01",
             "document_type": "cc", "created_at": "x"},
            {"id": "e-domus", "process_id": "p-domus-bruno", "expiry_date": "2030-01-01",
             "document_type": "cc", "created_at": "x"},
        ])
        vistos = []
        original = db.document_expiries.find

        def _find(query, *a, **k):
            vistos.append(query)
            return original(query, *a, **k)

        db.document_expiries.find = _find
        with tenant_db(db, exp), patch.object(exp, "db", db):
            try:
                await exp.run_get_document_expiries(None, user={**BRUNO, "role": "diretor"})
            except Exception:  # o modelo de resposta pode exigir mais campos
                pass
            # Mesmo com um `process_id` explícito de outra rede.
            try:
                await exp.run_get_document_expiries("p-power-0", user={**BRUNO, "role": "diretor"})
            except Exception:
                pass

        assert len(vistos) == 2
        for consulta in vistos:
            assert not [
                d for d in db.document_expiries.docs
                if _casa(d, consulta) and d["id"] == "e-power"
            ], "FUGA: validades de documentos de outra rede"


# ════════════════════════════════════════════════════════════════════
# A rede de omissão não se herda
# ════════════════════════════════════════════════════════════════════
class TestRedeDeOmissaoNaoSeHerda:
    @pytest.mark.asyncio
    async def test_utilizador_com_empresa_noutra_rede_nao_inclui_a_pilha_por_carimbar(
        self, fake_async_db,
    ):
        import services.tenant_network as tn

        db = _cenario(fake_async_db)
        with tenant_db(db):
            scope = await tn.resolve_tenant_scope(BRUNO)

        assert scope.network_ids == (REDE_DOMUS,)
        assert scope.inclui_rede_de_omissao is False
        condicao = tn.build_network_scope_condition(scope)
        assert not _casa({"id": "x"}, condicao), "a pilha por carimbar entrou no âmbito da Domus"

    @pytest.mark.asyncio
    async def test_empresa_nova_sem_rede_e_uma_ilha_e_nao_a_rede_de_omissao(self, fake_async_db):
        import services.tenant_network as tn

        db = _cenario(fake_async_db)
        db.companies.docs.append({"id": "cmp-nova", "name": "Nova"})  # sem network_id
        db.user_company_roles.docs.append(
            {"user_id": "u-novo", "company_id": "cmp-nova", "company_name": "Nova",
             "role": "diretor", "is_default": True}
        )
        with tenant_db(db):
            scope = await tn.resolve_tenant_scope({"id": "u-novo", "role": "diretor"})

        assert scope.network_ids == ("rede:cmp-nova",)
        assert scope.inclui_rede_de_omissao is False

    @pytest.mark.asyncio
    async def test_quem_trabalha_nas_duas_redes_ve_as_duas(self, fake_async_db):
        """Contraprova: a Carla tem dois empregos, e não é fuga."""
        import services.tenant_network as tn

        db = _cenario(fake_async_db)
        with tenant_db(db):
            scope = await tn.resolve_tenant_scope(CARLA)

        assert set(scope.network_ids) == {REDE_INCUMBENTE, REDE_DOMUS}


# ════════════════════════════════════════════════════════════════════
# O inventário que falha por omissão
# ════════════════════════════════════════════════════════════════════

#: Módulos que leem `db.processes`/`db.clients` SEM condição de rede, com o
#: MOTIVO. Uma entrada nova exige ler o código e escrever porquê — é a única
#: forma de um módulo novo não ficar de fora sem ninguém reparar.
SEM_CONDICAO_DE_REDE_POR_DESENHO = {
    # Manutenção/migração: ferramentas de operação só-Master.
    "admin_dev_ops.py": "índices e sincronização de BD — só Master",
    "admin_encryption_api_status.py": "estado da encriptação — só Master",
    "admin_migration_api_status.py": "migração de encriptação — só Master",
    "admin_migration_api_task.py": "migração de encriptação — só Master",
    "admin_proc_migration_api.py": "migração de processos — só Master",
    "admin_proc_migration_helpers.py": "migração de processos — só Master",
    "admin_process_ops.py": "operações de manutenção de processos — só Master",
    "admin_s3_client_mappings.py": "mapeamento de pastas S3 — Admin com âmbito próprio",
    "admin_workflow.py": "diagnóstico do motor de fases — só Master",
    "diagnostics_system.py": "diagnóstico de sistema — só Master",
    "gdpr.py": "núcleo RGPD; as rotas (gdpr_api_*) aplicam a rede",
    "migrate_encryption.py": "migração de encriptação — só Master",
    "scheduled_tasks.py": "jobs de fundo sem utilizador",
    "ai_improvement_agent.py": "agente de fundo sem utilizador",
    "process_kanban_diagnose.py": "diagnóstico do quadro — só Master/Admin",
    "s3_folder_relink.py": "religamento manual — Admin com aviso",
    # Resolvem por id um objecto já validado a montante (guardas de router).
    "client_delete.py": "by_id_scope guarda a rota",
    "client_find_or_create.py": "dedupe de cliente (D-32, em aberto e dita)",
    "email_client_match.py": "ligação email→cliente na rede do email",
    "portal_auth.py": "autenticação do cliente do Portal (id próprio)",
    "portal_security.py": "autenticação do cliente do Portal (id próprio)",
    "process_assignment.py": "escritas por id guardadas por process_scope_guard",
    "process_clients_nm.py": "escritas por id guardadas por process_scope_guard",
    "process_service.py": "núcleo de criação/leitura por id (guardas a montante)",
    "restore_api_client.py": "by_id_scope guarda a rota",
    "client_crud.py": "GET/PUT por id guardados por by_id_scope (D-31); os processos listados são os do cliente já visível",
    "finance_helpers.py": "recebe o `ambito` do chamador (finance_scope)",
    "partner_portal_read.py": "âmbito do parceiro por relação ∧ rede",
    "ai_bulk_cache_ops.py": "cache de NIF; a lista de revisões pendentes aplica a rede",
    "document_expiry_crud.py": "criação por id; as listagens aplicam a rede",
}


def _usa_condicao_de_rede(fonte: str) -> bool:
    return any(
        marca in fonte
        for marca in (
            "build_tenant_process_condition",
            "build_tenant_condition",
            "resolve_tenant_scope",
            "com_isolamento",
        )
    )


class TestInventarioDasListagens:
    def test_as_listagens_de_meus_clientes_aplicam_a_condicao_de_rede(self):
        """As superfícies do relato, nomeadas — apagar a chamada parte isto."""
        for ficheiro in (
            "process_my_clients.py",
            "my_clients_api_list.py",
            "my_clients_api_stats.py",
            "client_me.py",
            "document_expiring_dashboard.py",
            "document_expiry_crud.py",
            "document_misc.py",
            "process_dsti.py",
            "email_templates_drafts.py",
            "ai_bulk_clients.py",
            "ai_bulk_cache_ops.py",
        ):
            fonte = (BACKEND / "services" / ficheiro).read_text(encoding="utf-8")
            assert "build_tenant_process_condition" in fonte, (
                f"{ficheiro} lê `db.processes` sem a condição de rede"
            )

    def test_nenhum_modulo_novo_le_processos_ou_clientes_sem_rede(self):
        """Falha por OMISSÃO: um módulo novo tem de aplicar a rede ou ser
        declarado em `SEM_CONDICAO_DE_REDE_POR_DESENHO` com o motivo."""
        leituras = ("find(", "aggregate(", "count_documents(", "distinct(")
        suspeitos = []
        for caminho in sorted((BACKEND / "services").glob("*.py")):
            fonte = caminho.read_text(encoding="utf-8")
            if not any(
                f"db.{colecao}.{op}" in fonte
                for colecao in ("processes", "clients")
                for op in leituras
            ):
                continue
            if _usa_condicao_de_rede(fonte) or any(
                marca in fonte
                for marca in ("by_id_scope", "process_scope_guard", "_scope", "processo_no_ambito")
            ):
                continue
            if caminho.name in SEM_CONDICAO_DE_REDE_POR_DESENHO:
                continue
            suspeitos.append(caminho.name)

        assert not suspeitos, (
            "Módulos que leem processos/clientes sem condição de rede e sem motivo "
            f"declarado: {suspeitos}"
        )

    def test_a_lista_de_excepcoes_nao_tem_entradas_mortas(self):
        """Uma excepção para um ficheiro que já não existe é conhecimento
        apagado — e esconde que a lista deixou de ser lida."""
        for nome in SEM_CONDICAO_DE_REDE_POR_DESENHO:
            assert (BACKEND / "services" / nome).exists(), nome

    def test_o_leitor_do_inventario_le_mesmo_os_modulos(self):
        """Contraprova: um inventário que não lê nada passa sempre."""
        fonte = (BACKEND / "services" / "my_clients_api_list.py").read_text(encoding="utf-8")
        assert "db.processes.find" in fonte
        assert ast.parse(fonte)
