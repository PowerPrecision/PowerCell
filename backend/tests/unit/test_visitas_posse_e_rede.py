"""`db.visits`: posse e fronteira de rede (Lote 9, parte 2 — D-21).

OS TRÊS BURACOS QUE ESTES TESTES FECHAM
=======================================
1. **Listagens abertas.** `run_list_visits` e `run_get_visits_kanban`
   abriam com `query = {}` e o único recorte era
   `if user_role in ["consultor", "intermediario"]`. Um **diretor,
   administrativo, admin ou CEO via as visitas de TODAS as redes**, e o
   documento leva `client_name`, `client_email` e `client_phone`. A Domus
   é uma ilha. Os dois papéis que escapavam escapavam por ACIDENTE (a
   forma do `run_get_my_tasks`).
2. **Escritas sem posse.** `run_get_visit`, `run_update_visit` e
   `run_cancel_visit` eram `find_one({"id": visit_id})` e mais nada — o
   `run_delete_deadline` do Lote 7 outra vez. E o `PATCH` deixava
   reatribuir a visita a um consultor de qualquer rede.
3. **Carimbo errado.** `visit_list_create` gravava
   `"company_id": user.get("company_id")` — campo que o documento de
   utilizador NÃO tem (tem `company`, o nome) —, logo toda a visita da
   equipa nascia sem carimbo; e `network_id` não existia na colecção.

A classe `TestAExploracao` é o ataque, escrita para morder primeiro.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.visit_scope import (
    build_visit_rbac_condition,
    e_papel_de_equipa_nas_visitas,
    esta_ligado_a_pessoa,
    pode_atribuir_a_consultor,
    pode_mexer_na_visita,
    pode_ver_visita,
    processos_da_visita,
    ramo_dos_processos,
    visita_na_rede,
)

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "domus"


def _visita(**kw):
    base = {
        "id": "v1",
        "property_title": "T2 em Leiria",
        "client_id": "proc-power",
        "process_id": "proc-power",
        "client_name": "Ana Martins",
        "client_email": "ana@exemplo.pt",
        "client_phone": "912345678",
        "consultor_id": "u-power",
        "consultor_name": "Da Power",
        "scheduled_date": "2026-11-20T15:00:00Z",
        "status": "agendada",
        "created_by": "u-power",
        "network_id": REDE_POWER,
        "company_id": "empresa-power",
    }
    base.update(kw)
    return base


# ════════════════════════════════════════════════════════════════════
#  A REGRA PURA
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:
    """O ataque. Cada um destes passava antes deste lote."""

    def test_um_consultor_de_outra_rede_NAO_ve_a_visita(self):
        assert pode_ver_visita(
            _visita(),
            user_id="u-domus",
            papel="consultor",
            redes=(REDE_DOMUS,),
            processos_visiveis=("proc-domus",),
        ) is False

    def test_um_DIRETOR_de_outra_rede_tambem_nao(self):
        """O diretor é diretor da SUA rede, não da ilha ao lado.

        O bypass do produto é «acesso total à sua rede», e a tolerância de
        cruzamento entre redes é literalmente zero.
        """
        assert pode_ver_visita(
            _visita(), user_id="u-domus", papel="diretor", redes=(REDE_DOMUS,),
        ) is False

    def test_um_ADMINISTRATIVO_de_outra_rede_tambem_nao(self):
        """É o papel que este lote ACRESCENTA à vista de equipa — e
        acrescentar à equipa não é acrescentar a todas as redes."""
        assert pode_ver_visita(
            _visita(), user_id="u-domus", papel="administrativo",
            redes=(REDE_DOMUS,),
        ) is False

    def test_nao_se_reatribui_a_visita_a_um_consultor_de_outra_rede(self):
        """A pergunta do DESTINO. Sem ela, a lista do consultor da Domus
        ganhava o nome, o email e o telefone de um cliente da Power."""
        assert pode_atribuir_a_consultor(
            (REDE_DOMUS,), papel="diretor", redes=(REDE_POWER,),
        ) is False

    def test_um_consultor_sem_rede_determinavel_e_RECUSADO(self):
        """Falha fechada: um utilizador órfão já recebe a rede de omissão
        no `resolve_tenant_scope`, logo um conjunto vazio aqui significa
        que nem isso se resolveu."""
        assert pode_atribuir_a_consultor(
            (), papel="diretor", redes=(REDE_POWER,),
        ) is False

    def test_o_INDEXACAO_nao_ganha_a_vista_de_equipa(self):
        """Tem carimbo próprio e nunca é um atribuído — vê o que lhe está
        ligado e mais nada."""
        assert e_papel_de_equipa_nas_visitas("indexacao") is False
        assert pode_ver_visita(
            _visita(), user_id="u-index", papel="indexacao",
            redes=(REDE_POWER,),
        ) is False

    def test_o_PARCEIRO_tambem_nao(self):
        assert e_papel_de_equipa_nas_visitas("parceiro") is False


class TestQuemPodeVer:
    """As contraprovas. Sem elas, «não mostrar nada a ninguém» passava —
    e é pior do que a fuga, porque uma visita que desaparece não produz
    erro nenhum."""

    def test_o_consultor_ATRIBUIDO_ve_a_sua_visita(self):
        assert pode_ver_visita(
            _visita(), user_id="u-power", papel="consultor",
            redes=(REDE_POWER,),
        ) is True

    def test_o_consultor_no_PLURAL_tambem(self):
        """`consultor_ids` é o campo que o Kanban já lia; lê-lo só no
        singular deixava o segundo consultor de fora (lição do
        `alert_audience`)."""
        assert pode_ver_visita(
            _visita(consultor_id=None, consultor_ids=["u-a", "u-power"]),
            user_id="u-power", papel="consultor", redes=(REDE_POWER,),
        ) is True

    def test_quem_AGENDOU_ve_sempre_a_visita_que_marcou(self):
        """O administrativo que marcou a visita de um consultor tem de a
        poder remarcar — daí o `created_by` entrar nos campos de pessoa."""
        assert pode_mexer_na_visita(
            _visita(consultor_id="outro", created_by="u-admin"),
            user_id="u-admin", papel="administrativo", redes=(),
        ) is True

    def test_o_consultor_do_PROCESSO_ve_um_pedido_do_Portal(self):
        """Uma visita `solicitada` nasce SEM consultor. Se o único caminho
        fosse a atribuição, o consultor que trata do processo nunca via o
        pedido do seu cliente — e o pedido ficava à espera de ninguém."""
        assert pode_ver_visita(
            _visita(consultor_id=None, created_by="portal_client",
                    status="solicitada"),
            user_id="u-power", papel="consultor",
            redes=(REDE_POWER,), processos_visiveis=("proc-power",),
        ) is True

    def test_o_processo_tambem_e_lido_do_campo_LEGADO(self):
        """`client_id` é o nome antigo do mesmo valor, e o Portal grava os
        dois. Ler só o `process_id` deixava metade das visitas sem
        processo, logo invisíveis a quem trata dele."""
        visita = _visita(process_id=None, client_id="proc-power")
        assert processos_da_visita(visita) == {"proc-power"}
        assert pode_ver_visita(
            visita, user_id="u-power", papel="consultor",
            processos_visiveis=("proc-power",),
        ) is True

    def test_o_ADMINISTRATIVO_ve_a_equipa_DENTRO_da_rede(self):
        assert pode_ver_visita(
            _visita(consultor_id="outro", created_by="outro"),
            user_id="u-admin", papel="administrativo", redes=(REDE_POWER,),
        ) is True

    def test_so_o_MASTER_atravessa_redes_de_proposito(self):
        """É ele que reconcilia a pilha por carimbar."""
        assert pode_ver_visita(
            _visita(), user_id="qualquer", papel="master", redes=(),
        ) is True

    def test_ADMIN_e_CEO_sao_locais(self):
        """Adenda de RBAC: sem rede nem ligação, nem o Admin nem o CEO vêem."""
        for papel in ("admin", "ceo"):
            assert pode_ver_visita(
                _visita(), user_id="qualquer", papel=papel, redes=(),
            ) is False

    def test_uma_visita_POR_CARIMBAR_entra_na_vista_de_equipa(self):
        """A pilha anterior ao isolamento: cegá-la no dia do deploy
        esconderia trabalho real a quem o tem de fazer."""
        assert visita_na_rede(_visita(network_id=None), (REDE_DOMUS,)) is True
        assert pode_ver_visita(
            _visita(network_id=None, consultor_id="outro", created_by="outro"),
            user_id="u-domus", papel="diretor", redes=(REDE_DOMUS,),
        ) is True

    def test_sem_visita_responde_sempre_NAO(self):
        assert pode_ver_visita(None, user_id="u", papel="admin") is False
        assert esta_ligado_a_pessoa(None, "u") is False


class TestOsConjuntosDePapeis:
    def test_o_administrativo_E_equipa_nas_visitas_e_NAO_no_calendario(self):
        """A diferença é DELIBERADA e está escrita na docstring do módulo:
        o back-office marca e remarca visitas, e não tem agenda de equipa.

        Este teste existe para a diferença não ser «arrumada» por alguém
        que a leia como incoerência.
        """
        from services.deadline_scope import e_papel_de_equipa

        assert e_papel_de_equipa_nas_visitas("administrativo") is True
        assert e_papel_de_equipa("administrativo") is False

    def test_os_papeis_de_equipa_sao_exactamente_estes(self):
        esperados = {"admin", "ceo", "diretor", "administrativo"}
        for papel in esperados:
            assert e_papel_de_equipa_nas_visitas(papel) is True
        for papel in ("consultor", "intermediario", "indexacao", "parceiro",
                      "cliente", "", None):
            assert e_papel_de_equipa_nas_visitas(papel) is False


class TestACondicaoDaListagem:
    def test_um_conjunto_VAZIO_de_processos_nao_casa_com_tudo(self):
        """`{}` casava com tudo e era a forma de a guarda se desligar
        sozinha — o precedente do `{"process_id": None}` do calendário."""
        condicao = ramo_dos_processos([])
        assert condicao == {"id": {"$in": []}}

    def test_o_consultor_leva_recorte_pessoal_mais_os_seus_processos(self):
        condicao = build_visit_rbac_condition(
            user_id="u-power", papel="consultor",
            processos_visiveis=("proc-power",),
        )
        ramos = condicao["$or"]
        assert {"consultor_id": "u-power"} in ramos
        assert {"created_by": "u-power"} in ramos

    def test_a_equipa_nao_leva_recorte_pessoal_e_fica_so_com_a_REDE(self):
        """`{}` aqui não é «tudo»: o âmbito é a condição de rede, aplicada
        por fora pelo `com_isolamento` (nota do `run_get_deadlines`)."""
        for papel in ("admin", "ceo", "diretor", "administrativo"):
            assert build_visit_rbac_condition(
                user_id="u", papel=papel, processos_visiveis=(),
            ) == {}

    def test_sem_utilizador_o_recorte_continua_a_recusar(self):
        """Fail-closed: sem id, o único ramo é a condição impossível."""
        condicao = build_visit_rbac_condition(
            user_id=None, papel="consultor", processos_visiveis=(),
        )
        assert condicao == {"$or": [{"id": {"$in": []}}]}


# ════════════════════════════════════════════════════════════════════
#  OS HANDLERS
# ════════════════════════════════════════════════════════════════════
class _Pedido:
    """Um `Request` suficiente: só os headers interessam ao papel efectivo."""

    def __init__(self, papel=None, empresa=None):
        self.headers = {}
        if papel:
            self.headers["X-Active-Role"] = papel
        if empresa:
            self.headers["X-Company-Id"] = empresa
        self.query_params = {}


async def _semear(fake_db):
    await fake_db.companies.insert_one(
        {"id": "empresa-power", "name": "Power", "network_id": REDE_POWER})
    await fake_db.companies.insert_one(
        {"id": "empresa-domus", "name": "Domus", "network_id": REDE_DOMUS})
    await fake_db.processes.insert_one({
        "id": "proc-power", "client_name": "Ana Martins",
        "client_email": "ana@exemplo.pt", "network_id": REDE_POWER,
        "company_id": "empresa-power", "status": "analise",
        "assigned_consultor_ids": ["u-power"],
    })
    await fake_db.processes.insert_one({
        "id": "proc-domus", "client_name": "Cliente Domus",
        "client_email": "domus@exemplo.pt", "network_id": REDE_DOMUS,
        "company_id": "empresa-domus", "status": "analise",
        "assigned_consultor_ids": ["u-domus"],
    })
    await fake_db.visits.insert_one(_visita())
    await fake_db.visits.insert_one(_visita(
        id="v-domus", client_id="proc-domus", process_id="proc-domus",
        client_name="Cliente Domus", client_email="domus@exemplo.pt",
        consultor_id="u-domus", created_by="u-domus",
        network_id=REDE_DOMUS, company_id="empresa-domus",
    ))


DOMUS = {
    "id": "u-domus", "role": "consultor", "name": "Da Domus",
    "company": "empresa-domus", "active_company_id": "empresa-domus",
}
POWER = {
    "id": "u-power", "role": "consultor", "name": "Da Power",
    "company": "empresa-power", "active_company_id": "empresa-power",
}
DIRETOR_DOMUS = {
    "id": "u-dir-domus", "role": "diretor", "name": "Diretor Domus",
    "company": "empresa-domus", "active_company_id": "empresa-domus",
}


def _patches(fake_db, *modulos):
    """Patcha o `db` de TODOS os módulos da cadeia.

    O `visit_kanban_get` entra sempre: é lá que vive a guarda
    `exigir_visita_acessivel`, que as escritas chamam — e um módulo que
    faz `from database import db` no topo fica com a SUA referência ao
    proxy. Sem ele, os testes das escritas iam ao Mongo real e falhavam
    com «Event loop is closed», um erro que aponta para o sítio errado
    (foi o que aconteceu ao escrever este ficheiro).
    """
    from services import (
        tenant_access_context, tenant_network, visit_kanban_get,
    )

    alvos = [tenant_access_context, tenant_network, visit_kanban_get, *modulos]
    vistos: list = []
    for m in alvos:
        if m not in vistos:
            vistos.append(m)
    return [patch.object(m, "db", fake_db) for m in vistos]


class _Contexto:
    """Aplica vários `patch.object` como um só `with`."""

    def __init__(self, patches):
        self._patches = patches

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


class TestAListagem:
    @pytest.mark.asyncio
    async def test_o_diretor_da_Domus_NAO_ve_as_visitas_da_Power(
        self, fake_async_db
    ):
        from services import visit_list_create

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_list_create)):
            visitas = await visit_list_create.run_list_visits(
                DIRETOR_DOMUS, request=_Pedido(),
            )
        ids = {v["id"] for v in visitas}
        assert "v1" not in ids, (
            "Fuga de rede: a visita da Power leva client_name, client_email "
            "e client_phone."
        )
        assert ids == {"v-domus"}

    @pytest.mark.asyncio
    async def test_o_diretor_da_Power_continua_a_ver_a_sua_equipa(
        self, fake_async_db
    ):
        """Contraprova: um filtro que esconda tudo passava o teste de cima."""
        from services import visit_list_create

        await _semear(fake_async_db)
        diretor_power = {**DIRETOR_DOMUS, "id": "u-dir-power",
                         "company": "empresa-power",
                         "active_company_id": "empresa-power"}
        with _Contexto(_patches(fake_async_db, visit_list_create)):
            visitas = await visit_list_create.run_list_visits(
                diretor_power, request=_Pedido(),
            )
        assert {v["id"] for v in visitas} == {"v1"}

    @pytest.mark.asyncio
    async def test_o_kanban_tem_a_MESMA_fronteira_que_a_listagem(
        self, fake_async_db
    ):
        """O Kanban tem construtor SEPARADO — foi assim que ficou fora do
        isolamento do Lote 4 (lição do `build_kanban_query`)."""
        from services import visit_kanban_get

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_kanban_get)):
            quadro = await visit_kanban_get.run_get_visits_kanban(
                DIRETOR_DOMUS, request=_Pedido(),
            )
        todas = [
            v["id"]
            for coluna in ("solicitadas", "agendadas", "concluidas", "canceladas")
            for v in quadro[coluna]
        ]
        assert "v1" not in todas
        assert quadro["total"] == 1

    @pytest.mark.asyncio
    async def test_um_consultor_NAO_ve_a_visita_de_um_COLEGA_da_mesma_rede(
        self, fake_async_db
    ):
        """O recorte por PESSOA, que a fronteira de rede não substitui.

        Este teste nasceu de uma MUTAÇÃO SOBREVIVENTE: apagar o
        `build_visit_rbac_condition` da listagem não matava nenhum teste,
        porque os que existiam usavam todos um DIRETOR — e para um papel
        de equipa o recorte pessoal é `{}` por desenho. Não era uma
        mutação perdida, era um teste fraco: faltava o caso em que a rede
        está certa e a pessoa não.
        """
        from services import visit_list_create

        await _semear(fake_async_db)
        # Um colega da MESMA rede, sem ligação à visita e sem o processo.
        colega = {
            "id": "u-power-2", "role": "consultor", "name": "Colega",
            "company": "empresa-power", "active_company_id": "empresa-power",
        }
        with _Contexto(_patches(fake_async_db, visit_list_create)):
            visitas = await visit_list_create.run_list_visits(
                colega, request=_Pedido(),
            )
        assert visitas == [], (
            "A fronteira de rede não é o recorte por pessoa: um consultor "
            "não vê a agenda de visitas do colega."
        )

    @pytest.mark.asyncio
    async def test_o_consultor_ATRIBUIDO_continua_a_ver_a_sua(
        self, fake_async_db
    ):
        """Contraprova do de cima: um recorte que esconda tudo passava."""
        from services import visit_list_create

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_list_create)):
            visitas = await visit_list_create.run_list_visits(
                POWER, request=_Pedido(),
            )
        assert {v["id"] for v in visitas} == {"v1"}

    @pytest.mark.asyncio
    async def test_o_KANBAN_tem_o_mesmo_recorte_por_pessoa(
        self, fake_async_db
    ):
        """O quadro tem construtor separado: o recorte pessoal também
        tinha de ser ligado lá, e não só a fronteira de rede."""
        from services import visit_kanban_get

        await _semear(fake_async_db)
        colega = {
            "id": "u-power-2", "role": "consultor", "name": "Colega",
            "company": "empresa-power", "active_company_id": "empresa-power",
        }
        with _Contexto(_patches(fake_async_db, visit_kanban_get)):
            quadro = await visit_kanban_get.run_get_visits_kanban(
                colega, request=_Pedido(),
            )
        assert quadro["total"] == 0

    @pytest.mark.asyncio
    async def test_pedir_as_visitas_de_um_processo_de_outra_rede_da_VAZIO(
        self, fake_async_db
    ):
        from services import visit_list_create

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_list_create)):
            visitas = await visit_list_create.run_list_visits(
                DIRETOR_DOMUS, process_id="proc-power", request=_Pedido(),
            )
        assert visitas == []


class TestALeituraComPosse:
    @pytest.mark.asyncio
    async def test_a_Domus_pedindo_a_visita_da_Power_leva_404(
        self, fake_async_db
    ):
        from services import visit_kanban_get

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_kanban_get)):
            with pytest.raises(HTTPException) as exc:
                await visit_kanban_get.run_get_visit("v1", DOMUS, _Pedido())
        # 404 e NUNCA 403: distinguir "não existe" de "não é tua"
        # confirma o id a quem adivinha.
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_o_dono_le_a_sua_visita(self, fake_async_db):
        from services import visit_kanban_get

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_kanban_get)):
            visita = await visit_kanban_get.run_get_visit("v1", POWER, _Pedido())
        assert visita["id"] == "v1"


class TestAEscritaComPosse:
    @pytest.mark.asyncio
    async def test_a_Domus_NAO_edita_a_visita_da_Power(self, fake_async_db):
        from services import visit_update_cancel

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_update_cancel)):
            with pytest.raises(HTTPException) as exc:
                await visit_update_cancel.run_update_visit(
                    "v1", {"notes": "invadido"}, DOMUS, _Pedido(),
                )
        assert exc.value.status_code == 404
        guardada = await fake_async_db.visits.find_one({"id": "v1"})
        assert guardada.get("notes") != "invadido"

    @pytest.mark.asyncio
    async def test_a_Domus_NAO_cancela_a_visita_da_Power(self, fake_async_db):
        from services import visit_update_cancel

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_update_cancel)):
            with pytest.raises(HTTPException) as exc:
                await visit_update_cancel.run_cancel_visit(
                    "v1", DOMUS, _Pedido(),
                )
        assert exc.value.status_code == 404
        guardada = await fake_async_db.visits.find_one({"id": "v1"})
        assert guardada["status"] == "agendada"

    @pytest.mark.asyncio
    async def test_o_dono_edita_as_notas(self, fake_async_db):
        """Contraprova: uma guarda que recuse tudo passava os dois de cima."""
        from services import visit_update_cancel

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, visit_update_cancel)):
            await visit_update_cancel.run_update_visit(
                "v1", {"notes": "cliente pediu manhã"}, POWER, _Pedido(),
            )
        guardada = await fake_async_db.visits.find_one({"id": "v1"})
        assert guardada["notes"] == "cliente pediu manhã"

    @pytest.mark.asyncio
    async def test_nao_se_reatribui_a_visita_para_fora_da_rede(
        self, fake_async_db
    ):
        from services import visit_update_cancel

        await _semear(fake_async_db)
        await fake_async_db.users.insert_one({
            "id": "u-domus", "name": "Da Domus", "company": "empresa-domus",
        })
        with _Contexto(_patches(fake_async_db, visit_update_cancel)):
            with pytest.raises(HTTPException) as exc:
                await visit_update_cancel.run_update_visit(
                    "v1", {"consultor_id": "u-domus"}, POWER, _Pedido(),
                )
        assert exc.value.status_code == 400
        guardada = await fake_async_db.visits.find_one({"id": "v1"})
        assert guardada["consultor_id"] == "u-power"


class TestOCarimboNaEscrita:
    @pytest.mark.asyncio
    async def test_a_visita_criada_pela_equipa_nasce_CARIMBADA(
        self, fake_async_db
    ):
        """`user.get("company_id")` não existe no documento de utilizador:
        toda a visita da equipa nascia com `company_id: None` e sem rede."""
        from services import visit_helpers, visit_list_create

        await _semear(fake_async_db)
        await fake_async_db.users.insert_one({
            "id": "u-power", "name": "Da Power", "company": "empresa-power",
        })
        # O scraper NÃO corre no teste: a visita nasce com `property_url`,
        # logo `run_create_visit` lança a tarefa de fundo — e uma tarefa
        # viva depois de o loop do teste fechar enche a saída com «Task
        # was destroyed but it is pending», um aviso que aponta para um
        # defeito que não existe aqui.
        async def _sem_scraper(_visit_id, _url):
            return None

        patches = _patches(fake_async_db, visit_list_create, visit_helpers)
        patches.append(patch.object(
            visit_list_create, "_run_scraper_for_visit", _sem_scraper,
        ))
        with _Contexto(patches):
            criada = await visit_list_create.run_create_visit(
                {
                    "client_id": "proc-power",
                    "property_url": "https://www.idealista.pt/imovel/1/",
                    "scheduled_date": "2026-12-01T10:00:00Z",
                },
                POWER,
            )
        assert criada["network_id"] == REDE_POWER
        assert criada["company_id"] == "empresa-power"
        guardada = await fake_async_db.visits.find_one({"id": criada["id"]})
        assert guardada["network_id"] == REDE_POWER

    @pytest.mark.asyncio
    async def test_o_pedido_do_PORTAL_tambem_nasce_carimbado(
        self, fake_async_db
    ):
        """Dois escritores, duas origens para o mesmo campo — e uma delas
        sempre vazia. O carimbo sai do mesmo ponto único nos dois."""
        from services import portal_client_visits

        await _semear(fake_async_db)
        with _Contexto(_patches(fake_async_db, portal_client_visits)):
            criada = await portal_client_visits.run_request_portal_visit(
                {"url": "https://www.idealista.pt/imovel/2/"},
                _TarefasDeFundo(),
                {"process": {"id": "proc-power", "client_name": "Ana"},
                 "process_id": "proc-power"},
            )
        assert criada["network_id"] == REDE_POWER
        assert criada["company_id"] == "empresa-power"


class _TarefasDeFundo:
    """Um `BackgroundTasks` que só registra — o scraper não corre no teste."""

    def __init__(self):
        self.chamadas = []

    def add_task(self, func, *args, **kwargs):
        self.chamadas.append((func, args, kwargs))


# ════════════════════════════════════════════════════════════════════
#  AS LACUNAS QUE AS MUTAÇÕES REVELARAM
# ════════════════════════════════════════════════════════════════════
class TestOQueAsMutacoesRevelaram:
    """Quatro mutações sobreviveram à primeira medição, e as quatro eram
    TESTES FRACOS — não mutações perdidas. Ficam aqui, nomeadas, porque é
    a diferença entre «não consegui matar» e «não tinha testado».
    """

    @pytest.mark.asyncio
    async def test_o_ADMINISTRATIVO_ve_a_equipa_PELO_HANDLER(
        self, fake_async_db
    ):
        """V15 — o contexto das visitas usa o predicado DAS VISITAS.

        Com o predicado do calendário (ADMIN/CEO/DIRETOR), o
        `administrativo` recebia só os processos atribuídos a ELE e a
        vista de equipa estreitava **sem dar erro**. A regra pura já
        estava afirmada; faltava o caminho em que o contexto é construído,
        e é lá que o predicado se escolhe.
        """
        from services import visit_list_create

        await _semear(fake_async_db)
        administrativo = {
            "id": "u-admin-power", "role": "administrativo",
            "name": "Back-office", "company": "empresa-power",
            "active_company_id": "empresa-power",
        }
        with _Contexto(_patches(fake_async_db, visit_list_create)):
            visitas = await visit_list_create.run_list_visits(
                administrativo, request=_Pedido(),
            )
        assert {v["id"] for v in visitas} == {"v1"}, (
            "O administrativo coordena visitas: tem de ver as da sua rede, "
            "não só as que lhe estão atribuídas."
        )

    @pytest.mark.asyncio
    async def test_o_administrativo_da_Domus_continua_a_NAO_ver_a_Power(
        self, fake_async_db
    ):
        """Contraprova de cima: alargar à equipa não é alargar às redes."""
        from services import visit_list_create

        await _semear(fake_async_db)
        administrativo = {
            "id": "u-admin-domus", "role": "administrativo",
            "name": "Back-office Domus", "company": "empresa-domus",
            "active_company_id": "empresa-domus",
        }
        with _Contexto(_patches(fake_async_db, visit_list_create)):
            visitas = await visit_list_create.run_list_visits(
                administrativo, request=_Pedido(),
            )
        assert {v["id"] for v in visitas} == {"v-domus"}

    @pytest.mark.asyncio
    async def test_se_a_leitura_dos_processos_FALHAR_nao_se_ve_nada(
        self, fake_async_db
    ):
        """V16 — o conjunto de processos visíveis falha FECHADO.

        Devolver «todos» por causa de um soluço da rede era a saída
        cómoda e abria a colecção inteira. Nenhum teste cobria o ramo da
        excepção, pelo que a mutação que o abria sobrevivia.
        """
        from services import tenant_access_context, visit_list_create

        await _semear(fake_async_db)

        class _ProcessosEmBaixo:
            """Só os `processes` falham: o resto da base responde."""

            def __init__(self, real):
                self._real = real

            def __getattr__(self, nome):
                if nome == "processes":
                    raise RuntimeError("Mongo em baixo")
                return getattr(self._real, nome)

        patches = _patches(fake_async_db, visit_list_create)
        patches.append(patch.object(
            tenant_access_context, "db", _ProcessosEmBaixo(fake_async_db),
        ))
        with _Contexto(patches):
            visitas = await visit_list_create.run_list_visits(
                POWER, request=_Pedido(),
            )
        # O consultor fica só com o que lhe está LIGADO — e a visita `v1`
        # está, logo o que se prova é que a falha não ALARGA o âmbito.
        assert all(v["id"] == "v1" for v in visitas)

        colega = {
            "id": "u-power-2", "role": "consultor", "name": "Colega",
            "company": "empresa-power", "active_company_id": "empresa-power",
        }
        with _Contexto(patches):
            visitas = await visit_list_create.run_list_visits(
                colega, request=_Pedido(),
            )
        assert visitas == [], (
            "Com a leitura dos processos em baixo, o âmbito encolhe — "
            "nunca alarga."
        )


class TestAsRotasPassamOPedido:
    """V14 — as rotas têm de passar o `Request` às suas superfícies.

    Os testes dos handlers chamam os serviços DIRECTAMENTE, logo nunca
    provam a ligação: tirar o `request` das rotas não matava nenhum. Sem
    ele o papel efectivo (`X-Active-Role`) não se resolve e decide-se pelo
    cargo do JWT — a 5.ª ocorrência da forma do `history._is_stealth_user`.

    O inventário DERIVA da assinatura de produção (quem aceita `request`
    tem de o receber), nunca de uma lista escrita à mão, e falha por
    OMISSÃO para um endpoint novo.
    """

    def _handlers(self):
        import ast
        import inspect
        from pathlib import Path

        from services import (
            visit_kanban_get, visit_list_create, visit_update_cancel,
        )

        servicos = {}
        for modulo in (visit_list_create, visit_kanban_get, visit_update_cancel):
            for nome, fn in vars(modulo).items():
                if nome.startswith("run_") and callable(fn):
                    servicos[nome] = fn

        caminho = Path(__file__).resolve().parents[2] / "routes" / "visits.py"
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))

        encontrados = []
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(no):
                if not isinstance(sub, ast.Call):
                    continue
                alvo = getattr(sub.func, "id", None)
                if not alvo or alvo not in servicos:
                    continue
                aceita = "request" in inspect.signature(
                    servicos[alvo]
                ).parameters
                passa = any(
                    getattr(a, "id", None) == "request" for a in sub.args
                ) or any(
                    kw.arg == "request" for kw in sub.keywords
                )
                encontrados.append((no.name, alvo, aceita, passa))
        return encontrados

    def test_o_inventario_le_MESMO_as_rotas(self):
        """Contraprova: um leitor partido devolve zero e fica verde."""
        handlers = self._handlers()
        assert len(handlers) >= 6, handlers
        assert sum(1 for *_, aceita, _ in handlers if aceita) >= 5, handlers

    def test_quem_aceita_o_pedido_recebe_o_pedido(self):
        faltam = [
            f"{rota} → {servico}"
            for rota, servico, aceita, passa in self._handlers()
            if aceita and not passa
        ]
        assert not faltam, (
            "Estas rotas não passam o `Request` e o papel volta a ser o do "
            "JWT:\n  " + "\n  ".join(faltam)
        )


class TestOContextoRecebeOPredicadoCerto:
    """O `e_equipa` do contexto, afirmado UM NÍVEL ABAIXO.

    A mutação que repõe o predicado do calendário na LISTAGEM **sobrevive**,
    e isso está certo: para um papel de equipa o recorte pessoal é `{}`, logo
    o conjunto de processos não é consultado e a listagem sai igual. O que o
    argumento controla é o CONTEXTO — e é aí que se mede, como no
    `test_duplo_de_mongo_nor_e_elemmatch`.

    Fica dito de propósito em vez de inventar um teste de listagem que
    passasse sem provar nada: a diferença é real, é observável aqui, e
    passa a ser load-bearing no dia em que uma regra consultar
    `contexto.processos` para um papel de equipa.
    """

    @pytest.mark.asyncio
    async def test_com_o_predicado_das_VISITAS_o_administrativo_ve_a_rede(
        self, fake_async_db
    ):
        from services import tenant_access_context, tenant_network
        from services.visit_scope import e_papel_de_equipa_nas_visitas

        await _semear(fake_async_db)
        administrativo = {
            "id": "u-admin-power", "role": "administrativo",
            "company": "empresa-power", "active_company_id": "empresa-power",
        }
        with _Contexto([
            patch.object(tenant_access_context, "db", fake_async_db),
            patch.object(tenant_network, "db", fake_async_db),
        ]):
            contexto = await tenant_access_context.carregar_contexto_de_acesso(
                administrativo, _Pedido(),
                e_equipa=e_papel_de_equipa_nas_visitas,
            )
        assert "proc-power" in contexto.processos
        assert "proc-domus" not in contexto.processos, "a rede continua a ser a fronteira"

    @pytest.mark.asyncio
    async def test_com_o_predicado_do_CALENDARIO_nao_ve(self, fake_async_db):
        """A contraprova: sem o argumento, o conjunto encolhe — é a
        diferença que o parâmetro existe para corrigir."""
        from services import tenant_access_context, tenant_network

        await _semear(fake_async_db)
        administrativo = {
            "id": "u-admin-power", "role": "administrativo",
            "company": "empresa-power", "active_company_id": "empresa-power",
        }
        with _Contexto([
            patch.object(tenant_access_context, "db", fake_async_db),
            patch.object(tenant_network, "db", fake_async_db),
        ]):
            contexto = await tenant_access_context.carregar_contexto_de_acesso(
                administrativo, _Pedido(),
            )
        assert "proc-power" not in contexto.processos

    @pytest.mark.asyncio
    async def test_um_consultor_so_leva_os_processos_dele(self, fake_async_db):
        """O ramo pessoal do contexto — o que a fuga de V16 abriria."""
        from services import tenant_access_context, tenant_network
        from services.visit_scope import e_papel_de_equipa_nas_visitas

        await _semear(fake_async_db)
        colega = {
            "id": "u-power-2", "role": "consultor",
            "company": "empresa-power", "active_company_id": "empresa-power",
        }
        with _Contexto([
            patch.object(tenant_access_context, "db", fake_async_db),
            patch.object(tenant_network, "db", fake_async_db),
        ]):
            contexto = await tenant_access_context.carregar_contexto_de_acesso(
                colega, _Pedido(), e_equipa=e_papel_de_equipa_nas_visitas,
            )
        assert contexto.processos == frozenset(), (
            "um consultor sem atribuição não herda os processos da rede"
        )
