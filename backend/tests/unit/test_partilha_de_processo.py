"""Partilha de um processo entre redes — a Via Rápida (D-25, Out 2026).

O QUE ISTO RESOLVE
==================
O modelo tinha **um** `network_id` por documento: um processo pertence a
uma rede e só essa o vê. Mas a co-angariação é uma operação NORMAL do
negócio, e o modelo financeiro já a conhecia — `db.process_finances` é
chaveada por `(process_id, company_id)`, um registo por empresa no mesmo
processo, que é exactamente o rateio de comissão de uma partilha. Era só
a VISIBILIDADE que não tinha como o expressar.

O recurso disponível era dar à pessoa um UCR nas duas empresas, e é o
pior negócio possível: o âmbito é do UTILIZADOR, logo um consultor da
Precision com acesso à Domus passa a ver **toda** a Domus. O teste
`test_a_partilha_de_UM_processo_nao_abre_os_OUTROS` é precisamente a
diferença entre as duas coisas, e sem ele esta entrega não se distingue
do atalho que ela substitui.

DECISÕES DE PRODUTO (dono do produto, 2026-10-09)
=================================================
* o lado convidado vê **a ficha inteira do processo** — e a fronteira
  continua fechada em todos os restantes;
* **Via Rápida**: nasce da ATRIBUIÇÃO, sem aprovação manual;
* a **revogação é MANUAL**: tirar a atribuição não revoga, porque o
  parceiro mantém o histórico e os documentos que ele próprio produziu e
  o registo de comissão continua coerente.

A terceira tem uma consequência que estes testes afirmam: uma abertura de
fronteira que ninguém aprovou tem de ser **visível e auditada**, senão é
silenciosa — e uma abertura silenciosa é o oposto de tolerância zero.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services.process_sharing import (
    CAMPO_EMPRESAS_PARCEIRAS,
    esta_partilhado,
    etiquetas_da_partilha,
    parceiros_do_processo,
    redes_do_registo,
)
from services.tenant_network import (
    CAMPO_REDES_PARCEIRAS,
    TenantScope,
    build_process_scope_condition,
    processo_no_ambito,
)
from tests.unit.helpers_tenant import (
    ANA,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    casa as _casa_a_condicao,
    db_tenant,  # noqa: F401  (fixture)
    rede_de_omissao_incumbente,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

#: Um consultor da Precision — mesma rede da Power, empresa diferente.
CARLA_PRECISION = {
    "id": "u-carla", "name": "Carla", "email": "carla@precision.pt",
    "role": "consultor",
}
#: Um consultor da Domus — rede DIFERENTE. É este que abre a partilha.
NUNO_DOMUS = {
    "id": "u-nuno", "name": "Nuno", "email": "nuno@domus.pt",
    "role": "consultor",
}


def _processo_da_power(**kw) -> dict:
    base = {
        "id": "p-power",
        "process_number": 12,
        "client_name": "Cliente da Power",
        "status": "em_analise",
        "network_id": REDE_INCUMBENTE,
        "company_id": "cmp-power",
    }
    base.update(kw)
    return base


@pytest.fixture
def casa(db_tenant):  # noqa: F811
    """O cenário multi-tenant + o Nuno da Domus.

    O processo da Power é o `p-power` que o `helpers_tenant` já semeia —
    **não** se acrescenta um segundo com o mesmo id. A primeira versão
    deste ficheiro fazia-o, o `find_one` devolvia o do helper (o
    primeiro a casar) e os testes mediam um documento sem atribuição
    nenhuma: um vermelho a apontar para a partilha quando o problema era
    a colisão de ids no cenário.
    """
    db_tenant.user_company_roles.docs.append({
        "user_id": "u-nuno", "company_id": "cmp-domus",
        "company_name": "Domus", "role": "consultor", "is_default": True,
    })
    db_tenant.users.docs.append(dict(NUNO_DOMUS))
    return db_tenant


def _atribuir(fake_db, *ids, process_id="p-power") -> dict:
    """Põe estes ids como consultores do processo e devolve o documento."""
    doc = _doc(fake_db, process_id)
    doc["assigned_consultor_ids"] = list(ids)
    return doc


def _modulos():
    from services import process_sharing, tenant_access_context

    return (process_sharing, tenant_access_context)


def _patch(fake_db):
    return _tenant_db(fake_db, *_modulos())


async def _sincronizar(fake_db, process_id, **kw):
    from services.process_sharing import sincronizar_parceiros

    with _patch(fake_db):
        return await sincronizar_parceiros(process_id, **kw)


def _doc(fake_db, process_id="p-power") -> dict:
    return next(p for p in fake_db.processes.docs if p["id"] == process_id)


# ════════════════════════════════════════════════════════════════════
#  A VIA RÁPIDA
# ════════════════════════════════════════════════════════════════════
class TestAViaRapida:

    @pytest.mark.asyncio
    async def test_atribuir_a_alguem_de_OUTRA_rede_abre_a_partilha(self, casa):
        _atribuir(casa, "u-nuno")

        novas = await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert [n["network_id"] for n in novas] == [REDE_DOMUS]
        assert novas[0]["company_name"] == "Domus"
        assert novas[0]["added_by"] == ANA["id"]

        doc = _doc(casa)
        assert doc[CAMPO_REDES_PARCEIRAS] == [REDE_DOMUS]

    @pytest.mark.asyncio
    async def test_e_o_processo_passa_a_ser_VISIVEL_a_essa_rede(self, casa):
        _atribuir(casa, "u-nuno")
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        doc = _doc(casa)
        ambito_da_domus = TenantScope(
            network_ids=(REDE_DOMUS,), company_ids=("cmp-domus",),
        )

        assert processo_no_ambito(doc, ambito_da_domus) is True
        # E em Mongo, que é o que a listagem corre:
        assert _casa_a_condicao(
            doc, build_process_scope_condition(ambito_da_domus)
        ) is True

    @pytest.mark.asyncio
    async def test_a_PROPRIEDADE_nao_muda(self, casa):
        """Uma partilha acrescenta quem VÊ, nunca muda de quem É. O
        `network_id` é o carimbo de propriedade e é permanente."""
        _atribuir(casa, "u-nuno")
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert _doc(casa)["network_id"] == REDE_INCUMBENTE

    @pytest.mark.asyncio
    async def test_a_rede_do_DONO_nunca_entra_na_lista_de_convidados(self, casa):
        """Seria redundante hoje e, no dia em que o dono mudasse, deixava
        lá uma chave da rede antiga."""
        _atribuir(casa, ANA["id"])

        novas = await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert novas == []
        assert not _doc(casa).get(CAMPO_REDES_PARCEIRAS)

    @pytest.mark.asyncio
    async def test_atribuir_dentro_da_MESMA_rede_nao_abre_nada(self, casa):
        """A Precision é outra EMPRESA e a mesma REDE: não há partilha a
        registar, porque já vê o processo.

        O Pedro existe só para este teste: é consultor **apenas** na
        Precision. A Carla não serve aqui — ela trabalha nas duas redes
        (são os dois empregos dela), e foi a tentar usá-la que este
        teste revelou o defeito da etiqueta.
        """
        casa.user_company_roles.docs.append({
            "user_id": "u-pedro", "company_id": "cmp-precision",
            "company_name": "Precision Crédito", "role": "consultor",
            "is_default": True,
        })
        _atribuir(casa, "u-pedro")

        novas = await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert novas == []

    @pytest.mark.asyncio
    async def test_a_etiqueta_nomeia_a_empresa_DA_REDE_que_abriu(self, casa):
        """A Carla trabalha na Precision (mesma rede) **e** na Domus. Ao
        atribuí-la, a partilha que se abre é com a **Domus** — e a
        etiqueta tem de dizer Domus, não «Precision Crédito», que é a
        empresa por omissão dela.

        Uma etiqueta que mente sobre quem passou a ver o processo é pior
        do que etiqueta nenhuma: é a única coisa que torna visível uma
        abertura de fronteira que ninguém aprovou.
        """
        _atribuir(casa, "u-carla")

        novas = await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert [(n["company_name"], n["network_id"]) for n in novas] == [
            ("Domus", REDE_DOMUS)
        ]

    @pytest.mark.asyncio
    async def test_um_atribuido_SEM_empresa_nao_abre_a_rede_de_OMISSAO(
        self, casa, rede_de_omissao_incumbente,  # noqa: F811
    ):
        """`resolve_tenant_scope` dá a rede de OMISSÃO a um utilizador
        órfão de empresa, para não cegar contas de administração antigas.
        Usá-lo aqui abria o processo ao grupo incumbente por não se saber
        a empresa de alguém — falha ABERTA, no sítio exactamente errado.
        """
        casa.users.docs.append({
            "id": "u-orfao-2", "name": "Órfão", "role": "consultor",
        })
        _atribuir(casa, "u-orfao-2")

        novas = await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert novas == []

    @pytest.mark.asyncio
    async def test_e_IDEMPOTENTE(self, casa):
        """Lê o documento já gravado e só acrescenta o que falta — é o que
        permite chamá-la de cinco escritores sem contar diffs."""
        _atribuir(casa, "u-nuno")

        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])
        segunda = await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert segunda == []
        assert len(_doc(casa)[CAMPO_EMPRESAS_PARCEIRAS]) == 1

    @pytest.mark.asyncio
    async def test_um_atribuido_sem_rede_determinavel_NAO_abre_a_partilha(self, casa):
        """**Falha fechada.** A partilha abre uma fronteira; abri-la por
        não saber a rede de alguém é o pior sentido do erro."""
        _atribuir(casa, "u-fantasma")

        novas = await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert novas == []

    @pytest.mark.asyncio
    async def test_as_DUAS_listas_concordam_sempre(self, casa):
        """`partner_companies` é o REGISTO (o que a etiqueta mostra) e
        `partner_network_ids` é a lista indexável que a condição lê. Duas
        fontes de verdade divergem sem dar erro — e a que divergisse ou
        abria uma rede a mais, ou escondia um processo a quem o trabalha.
        """
        _atribuir(casa, "u-nuno")
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        doc = _doc(casa)
        assert doc[CAMPO_REDES_PARCEIRAS] == redes_do_registo(
            parceiros_do_processo(doc)
        )


# ════════════════════════════════════════════════════════════════════
#  A FRONTEIRA CONTINUA FECHADA — a diferença face ao atalho do UCR
# ════════════════════════════════════════════════════════════════════
class TestOQueAPartilhaNAOAbre:

    @pytest.mark.asyncio
    async def test_a_partilha_de_UM_processo_nao_abre_os_OUTROS(self, casa):
        """É a razão de existir desta entrega. Com um UCR nas duas
        empresas, o convidado veria **toda** a outra rede."""
        _atribuir(casa, "u-nuno")
        casa.processes.docs.append(
            _processo_da_power(id="p-power-2", client_name="Outro da Power")
        )
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        ambito_da_domus = TenantScope(
            network_ids=(REDE_DOMUS,), company_ids=("cmp-domus",),
        )
        condicao = build_process_scope_condition(ambito_da_domus)

        visiveis = {
            p["id"] for p in casa.processes.docs
            if _casa_a_condicao(p, condicao)
        }
        assert "p-power" in visiveis
        assert "p-power-2" not in visiveis, (
            f"a partilha de um processo abriu outro: {visiveis}"
        )

    def test_a_condicao_de_PROCESSOS_nao_toca_nas_outras_coleccoes(self):
        """`CAMPO_REDES_PARCEIRAS` vive só no documento de processo. Pôr o
        ramo no construtor genérico fá-lo-ia viajar para as 33 superfícies
        que o usam — e no dia em que alguém gravasse o campo noutra
        colecção passava a ser uma porta."""
        from services.tenant_network import build_network_scope_condition

        ambito = TenantScope(network_ids=(REDE_DOMUS,))
        generica = build_network_scope_condition(ambito)

        assert CAMPO_REDES_PARCEIRAS not in str(generica)
        assert CAMPO_REDES_PARCEIRAS in str(
            build_process_scope_condition(ambito)
        )

    def test_um_ambito_SEM_redes_nao_ganha_nada(self):
        """Sem redes não há com que casar a lista de convidadas: fica a
        condição impossível, que é a que se lê."""
        from services.tenant_network import CONDICAO_IMPOSSIVEL

        assert build_process_scope_condition(TenantScope()) == CONDICAO_IMPOSSIVEL


# ════════════════════════════════════════════════════════════════════
#  REVOGAÇÃO — manual, por decisão de produto
# ════════════════════════════════════════════════════════════════════
class TestARevogacao:

    @pytest.mark.asyncio
    async def test_tirar_a_atribuicao_NAO_revoga(self, casa):
        """Decisão de produto: o parceiro mantém o histórico e os
        documentos que ele próprio produziu, e o registo de comissão
        continua coerente. Revogar em automático fazia desaparecer
        trabalho real sem ninguém decidir."""
        _atribuir(casa, "u-nuno")
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        # O Nuno sai da equipa.
        _doc(casa)["assigned_consultor_ids"] = []
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        assert _doc(casa)[CAMPO_REDES_PARCEIRAS] == [REDE_DOMUS]

    @pytest.mark.asyncio
    async def test_revogar_a_MAO_retira_a_rede_e_a_lista_DERIVA(self, casa):
        from services.process_sharing import revogar_parceiro

        _atribuir(casa, "u-nuno")
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        with _patch(casa):
            retiradas = await revogar_parceiro(
                "p-power", company_id="cmp-domus", por_ordem_de=ANA["id"],
            )

        assert [r["network_id"] for r in retiradas] == [REDE_DOMUS]
        doc = _doc(casa)
        assert doc[CAMPO_REDES_PARCEIRAS] == []
        assert doc[CAMPO_EMPRESAS_PARCEIRAS] == []

    @pytest.mark.asyncio
    async def test_revogar_sem_dizer_O_QUE_nao_faz_nada(self, casa):
        """«Revogar tudo» não é uma operação que se ofereça por omissão."""
        from services.process_sharing import revogar_parceiro

        _atribuir(casa, "u-nuno")
        await _sincronizar(casa, "p-power", por_ordem_de=ANA["id"])

        with _patch(casa):
            retiradas = await revogar_parceiro("p-power", por_ordem_de=ANA["id"])

        assert retiradas == []
        assert _doc(casa)[CAMPO_REDES_PARCEIRAS] == [REDE_DOMUS]


# ════════════════════════════════════════════════════════════════════
#  VISÍVEL E AUDITADA — a Via Rápida não tem aprovação
# ════════════════════════════════════════════════════════════════════
class TestORasto:

    @pytest.mark.asyncio
    async def test_a_partilha_deixa_entrada_no_TRILHO(self, casa):
        """Isto move uma fronteira de visibilidade: é a mesma natureza da
        eliminação de um cliente (D-16), e o trilho é onde se registam as
        operações de conformidade."""
        from services import process_sharing

        registos: list = []

        async def _trilho(**kw):
            registos.append(kw)

        _atribuir(casa, "u-nuno")
        with _patch(casa):
            with patch("services.audit_trail_service.log_audit_event", _trilho):
                await process_sharing.sincronizar_parceiros(
                    "p-power", por_ordem_de=ANA["id"],
                )

        assert len(registos) == 1
        assert registos[0]["action"] == "process_shared"
        assert registos[0]["process_id"] == "p-power"
        assert registos[0]["user"]["id"] == ANA["id"]
        assert registos[0]["metadata"]["parceiros"][0]["company_name"] == "Domus"

    @pytest.mark.asyncio
    async def test_e_entrada_no_HISTORICO_do_processo(self, casa):
        """O trilho é para a conformidade; o histórico é onde a equipa do
        processo vê o que lhe aconteceu."""
        _atribuir(casa, "u-nuno")
        escritos: list = []

        async def _historico(texto):
            escritos.append(texto)

        await _sincronizar(
            casa, "p-power", por_ordem_de=ANA["id"],
            registar_historico=_historico,
        )

        assert escritos and "Domus" in escritos[0]

    @pytest.mark.asyncio
    async def test_o_rasto_NUNCA_faz_a_operacao_falhar(self, casa):
        """Observa, não intercepta — a regra do `job_heartbeat`. Uma
        partilha que rebenta porque o trilho está em baixo deixava a
        atribuição a meio."""
        from services import process_sharing

        async def _rebenta(**_kw):
            raise RuntimeError("trilho em baixo")

        _atribuir(casa, "u-nuno")
        with _patch(casa):
            with patch("services.audit_trail_service.log_audit_event", _rebenta):
                novas = await process_sharing.sincronizar_parceiros(
                    "p-power", por_ordem_de=ANA["id"],
                )

        assert [n["network_id"] for n in novas] == [REDE_DOMUS]
        assert _doc(casa)[CAMPO_REDES_PARCEIRAS] == [REDE_DOMUS]


# ════════════════════════════════════════════════════════════════════
#  A ETIQUETA — o que torna a Via Rápida visível
# ════════════════════════════════════════════════════════════════════
class TestAEtiqueta:

    def test_mostra_o_NOME_da_empresa(self):
        processo = {
            CAMPO_EMPRESAS_PARCEIRAS: [
                {"company_id": "cmp-domus", "company_name": "Domus",
                 "network_id": REDE_DOMUS},
            ],
            CAMPO_REDES_PARCEIRAS: [REDE_DOMUS],
        }
        assert etiquetas_da_partilha(processo) == ["Domus"]
        assert esta_partilhado(processo) is True

    def test_sem_nome_cai_para_o_ID_em_vez_de_desaparecer(self):
        """Mostrar um uuid é pior do que mostrar o nome; **esconder** a
        partilha é muito pior, porque a etiqueta é a única coisa que torna
        a Via Rápida visível."""
        processo = {
            CAMPO_EMPRESAS_PARCEIRAS: [
                {"company_id": "cmp-x", "network_id": "rede-x"},
            ],
        }
        assert etiquetas_da_partilha(processo) == ["cmp-x"]

    def test_um_processo_normal_nao_tem_etiqueta(self):
        assert etiquetas_da_partilha(_processo_da_power()) == []
        assert esta_partilhado(_processo_da_power()) is False

    def test_o_registo_com_TIPO_errado_degrada_para_SEM_partilha(self):
        """Um `or []` não protege de um tipo errado, só muda o sítio onde
        rebenta — é a regra do `pasta_gravada`. Aqui o degradado certo é
        «sem partilha», que é o estado seguro."""
        assert parceiros_do_processo({CAMPO_EMPRESAS_PARCEIRAS: "Domus"}) == []
        assert etiquetas_da_partilha({CAMPO_EMPRESAS_PARCEIRAS: {"a": 1}}) == []


# ════════════════════════════════════════════════════════════════════
#  CONCORDÂNCIA: o predicado e a condição Mongo
# ════════════════════════════════════════════════════════════════════
class TestOPredicadoConcordaComACondicao:

    AMOSTRA = [
        {"nome": "do dono", "network_id": REDE_INCUMBENTE},
        {"nome": "de outra rede", "network_id": REDE_DOMUS},
        {"nome": "partilhado com a Domus", "network_id": REDE_INCUMBENTE,
         CAMPO_REDES_PARCEIRAS: [REDE_DOMUS]},
        {"nome": "partilhado com duas", "network_id": "rede-terceira",
         CAMPO_REDES_PARCEIRAS: [REDE_DOMUS, REDE_INCUMBENTE]},
        {"nome": "lista de partilha vazia", "network_id": REDE_DOMUS,
         CAMPO_REDES_PARCEIRAS: []},
        {"nome": "sem marca nenhuma"},
        {"nome": "só com empresa", "company_id": "cmp-power"},
    ]

    @pytest.mark.parametrize("inclui_omissao", [False, True])
    @pytest.mark.parametrize(
        "redes,empresas",
        [
            ((REDE_INCUMBENTE,), ("cmp-power",)),
            ((REDE_DOMUS,), ("cmp-domus",)),
            ((), ()),
        ],
    )
    def test_respondem_o_mesmo_sobre_a_amostra_inteira(
        self, redes, empresas, inclui_omissao,
    ):
        scope = TenantScope(
            network_ids=redes,
            company_ids=empresas,
            inclui_rede_de_omissao=inclui_omissao,
        )
        condicao = build_process_scope_condition(scope)

        for doc in self.AMOSTRA:
            em_mongo = _casa_a_condicao(doc, condicao)
            em_python = processo_no_ambito(doc, scope)
            assert em_mongo == em_python, (
                f"discordam sobre {doc['nome']!r} (redes={redes}, "
                f"omissão={inclui_omissao}): Mongo={em_mongo} "
                f"Python={em_python}"
            )


# ════════════════════════════════════════════════════════════════════
#  O FILTRO RÁPIDO: «Exclusivos da Casa» vs «Partilhados»
# ════════════════════════════════════════════════════════════════════
class TestOFiltroRapido:
    """A semântica de `$in`/`$nin` sobre um campo que contém um ARRAY é
    precisamente onde este projecto já se enganou (a consulta do
    `fix_s3_folder_anomalies` encontrou 1 de 7 casos). Foi **verificada
    contra um `mongod` real**: os dois valores são complementos exactos
    sobre {ausente, null, [], ["x"], ["x","y"]}.
    """

    AMOSTRA = [
        {"id": "sem-campo"},
        {"id": "nulo", CAMPO_REDES_PARCEIRAS: None},
        {"id": "vazio", CAMPO_REDES_PARCEIRAS: []},
        {"id": "uma", CAMPO_REDES_PARCEIRAS: [REDE_DOMUS]},
        {"id": "duas", CAMPO_REDES_PARCEIRAS: [REDE_DOMUS, "rede-x"]},
    ]

    def _ids(self, valor):
        from services.process_sharing import condicao_de_filtro

        condicao = condicao_de_filtro(valor)
        return sorted(
            d["id"] for d in self.AMOSTRA if _casa_a_condicao(d, condicao)
        )

    def test_EXCLUSIVOS_apanha_ausente_nulo_e_vazio(self):
        from services.process_sharing import FILTRO_EXCLUSIVOS

        assert self._ids(FILTRO_EXCLUSIVOS) == ["nulo", "sem-campo", "vazio"]

    def test_PARTILHADOS_apanha_so_quem_tem_rede_convidada(self):
        from services.process_sharing import FILTRO_PARTILHADOS

        assert self._ids(FILTRO_PARTILHADOS) == ["duas", "uma"]

    def test_os_dois_sao_COMPLEMENTOS_exactos(self):
        """Sem isto, as duas condições podiam esconder ou duplicar uma
        linha e nenhum dos testes de cima dava por isso."""
        from services.process_sharing import (
            FILTRO_EXCLUSIVOS, FILTRO_PARTILHADOS,
        )

        a, b = set(self._ids(FILTRO_EXCLUSIVOS)), set(self._ids(FILTRO_PARTILHADOS))
        assert a | b == {d["id"] for d in self.AMOSTRA}
        assert not (a & b)

    def test_sem_valor_NAO_filtra(self):
        from services.process_sharing import condicao_de_filtro

        assert condicao_de_filtro(None) is None
        assert condicao_de_filtro("") is None

    def test_um_valor_DESCONHECIDO_nao_filtra_em_vez_de_esvaziar(self):
        """Um parâmetro escrito à mão no URL não pode esvaziar a listagem
        sem dizer porquê — e o `warning` diz."""
        from services.process_sharing import condicao_de_filtro

        assert condicao_de_filtro("talvez") is None

    def test_entra_nos_DOIS_construtores_de_query(self):
        """O quadro tem construtor SEPARADO: é a lição do
        `build_kanban_query`, e um filtro que só exista na listagem dá um
        quadro a ignorá-lo sem erro nenhum."""
        import json

        from services.process_list_filters import (
            build_kanban_query, build_process_list_query,
        )

        listagem = build_process_list_query(
            {"id": "u"}, "diretor", partilha="partilhados",
            tenant_condition={"network_id": "r"},
        )
        quadro = build_kanban_query(
            {"id": "u"}, "diretor", partilha="partilhados",
            tenant_condition={"network_id": "r"},
        )
        assert CAMPO_REDES_PARCEIRAS in json.dumps(listagem)
        assert CAMPO_REDES_PARCEIRAS in json.dumps(quadro)

    def test_e_no_endpoint_dos_VIZINHOS(self):
        """Senão a seta da fronteira da página leva a um processo que a
        lista filtrada não contém — o defeito que o Sub35 já teve."""
        import inspect

        from services.process_navigation import run_get_process_neighbours

        assert "partilha" in inspect.signature(
            run_get_process_neighbours
        ).parameters


# ════════════════════════════════════════════════════════════════════
#  A PROJECÇÃO E A SERIALIZAÇÃO — os dois ecrãs mostram o mesmo
# ════════════════════════════════════════════════════════════════════
class TestAProjeccaoEAFlag:

    def test_a_flag_e_CALCULADA_e_nunca_persistida(self):
        """Um booleano gravado fica errado no dia em que a partilha é
        revogada — a regra que o `sub35` já paga."""
        from services.process_sharing import (
            CAMPO_DAS_ETIQUETAS, CAMPO_DA_FLAG, aplicar_flag_a_processos,
        )

        processos = [
            {"id": "a", CAMPO_REDES_PARCEIRAS: [REDE_DOMUS],
             CAMPO_EMPRESAS_PARCEIRAS: [
                 {"company_name": "Domus", "network_id": REDE_DOMUS},
             ]},
            {"id": "b"},
        ]
        aplicar_flag_a_processos(processos)

        assert processos[0][CAMPO_DA_FLAG] is True
        assert processos[0][CAMPO_DAS_ETIQUETAS] == ["Domus"]
        assert processos[1][CAMPO_DA_FLAG] is False
        assert processos[1][CAMPO_DAS_ETIQUETAS] == []

    def test_a_projeccao_entra_nas_DUAS_listagens(self):
        """Se o Kanban projectar e a listagem não, a mesma linha tem
        etiqueta num ecrã e não tem no outro — é a nota do
        `PROJECCAO_SUB35`, no mesmo sítio."""
        from services.process_service import (
            PROCESS_KANBAN_PROJECTION, PROCESS_LIST_PROJECTION,
        )

        for projeccao in (PROCESS_LIST_PROJECTION, PROCESS_KANBAN_PROJECTION):
            assert CAMPO_EMPRESAS_PARCEIRAS in projeccao
            assert CAMPO_REDES_PARCEIRAS in projeccao

    def test_as_duas_listagens_e_o_quadro_APLICAM_a_flag(self):
        """Uma projecção sem serialização é um campo que chega cru ao
        ecrã; uma serialização sem projecção é uma etiqueta sempre
        vazia. Precisam das duas."""
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        for caminho in (
            "services/process_list_enrichment.py",
            "services/process_kanban_enrichment.py",
        ):
            fonte = codigo_sem_comentarios(open(caminho).read())
            assert "aplicar_flag_partilha(" in fonte, caminho


# ════════════════════════════════════════════════════════════════════
#  OS ESCRITORES DE ATRIBUIÇÃO CHAMAM A SINCRONIZAÇÃO
# ════════════════════════════════════════════════════════════════════
#  A variante `_sem_falhar` engole excepções de propósito (uma partilha
#  que rebenta não pode fazer falhar uma atribuição já gravada). O custo
#  é que apagar a chamada não parte teste nenhum — por isso a LIGAÇÃO
#  precisa de guarda própria.

ESCRITORES = {
    "services/process_staff_assignment.py": (
        "run_staff_assign_process", "run_assign_me_to_process",
    ),
    "services/process_assignment.py": (
        "dual_auto_assign_on_pre_registo_transition",
    ),
    "services/client_assign.py": ("run_assign_client_to_user",),
}


@pytest.mark.parametrize(
    "caminho,funcao",
    [(c, f) for c, fs in ESCRITORES.items() for f in fs],
)
def test_cada_escritor_de_atribuicao_sincroniza_a_partilha(caminho, funcao):
    import importlib

    from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

    modulo = importlib.import_module(
        caminho.replace("/", ".").removesuffix(".py")
    )
    fonte = codigo_da_funcao_sem_comentarios(getattr(modulo, funcao))
    assert "sincronizar_parceiros_sem_falhar" in fonte, (
        f"`{funcao}` atribui pessoas a um processo e não sincroniza a "
        "partilha: uma atribuição a alguém de outra rede deixava de "
        "abrir o processo a essa rede, sem erro nenhum"
    )


def test_a_sincronizacao_ESTRITA_propaga_e_a_outra_nao():
    """Contraprova das duas variantes. Sem ela, embrulhar tudo num
    `except` escondia um defeito meu atrás do mesmo bloco que protege a
    produção."""
    import asyncio

    from services import process_sharing

    async def _rebenta(*_a, **_k):
        raise RuntimeError("Mongo em baixo")

    with patch.object(process_sharing, "db") as falso:
        falso.processes.find_one = _rebenta

        with pytest.raises(RuntimeError):
            asyncio.run(process_sharing.sincronizar_parceiros("p1"))

        assert asyncio.run(
            process_sharing.sincronizar_parceiros_sem_falhar("p1")
        ) == []


# ════════════════════════════════════════════════════════════════════
#  INVENTÁRIO: quem LISTA processos usa a condição de PROCESSOS
# ════════════════════════════════════════════════════════════════════
#  A lição do `build_kanban_query`, quinta vez: um ponto único para a
#  CONDIÇÃO não chega, é preciso enumerar as superfícies. Este teste
#  falha por OMISSÃO para uma superfície nova que use a genérica.

#: Módulos que consultam `db.processes` com uma condição de tenant e que
#: **deliberadamente** ficam na condição genérica. Escritos em vez de
#: ausentes, com o motivo — uma lista de exclusão sem motivo é a forma de
#: isto se desligar sozinho.
EXCEPCOES_ESCRITAS = {
    "deadlines_api_calendar": (
        "lê processos por ID para ENRIQUECER linhas já filtradas; a "
        "fronteira do calendário vem do `carregar_contexto_de_acesso`, "
        "que já usa a condição de processos"
    ),
    "lead_list": (
        "consulta `db.processes` só para resolver o nome do cliente de "
        "uma lead; a fronteira das leads é a condição genérica, porque "
        "uma lead não é partilhável"
    ),
    "task_api_crud": (
        "`find_one` por id para montar o prefixo [PROC-nnn] do título de "
        "uma tarefa; não é uma listagem e não decide visibilidade"
    ),
    "client_registered": (
        "é a POOL (`build_tenant_pool_condition`): por desenho mostra o "
        "que NÃO tem carimbo a todas as redes (claim-based routing). Um "
        "processo partilhado já tem dono e não é um item de pool"
    ),
    "stats_scope": (
        "as AGREGAÇÕES ficam na genérica de propósito: o KPI é a "
        "produção da casa, e contar um processo partilhado nas duas "
        "redes torna a conversão do parceiro ilegível. A verificação de "
        "VISIBILIDADE (`processos_permitidos`) usa a de processos"
    ),
    "property_scope": (
        "a colecção é `db.properties`; a leitura de `db.processes` é a "
        "pergunta do DESTINO (D-24), e um imóvel não se liga a um "
        "processo partilhado de outra rede"
    ),
    "admin_users_scope": "a colecção é `db.users`, que não é partilhável",
    "email_draft_service": (
        "a condição de rede aplica-se à colecção `db.emails` (rascunhos, que "
        "levam o carimbo do dono do processo); as leituras de `db.processes` "
        "resolvem QUAIS processos estão atribuídos a quem pergunta e enriquecem "
        "o nome do cliente — não decidem visibilidade. Um rascunho do dono não "
        "se mostra à rede convidada: o convidado vê o processo, não a "
        "correspondência de quem o trata"
    ),
    "automation_api_rules": "a colecção é `db.automation_rules` (regras da casa)",
    "companies_crud_api_list": "a colecção é `db.companies` (as empresas)",
    "deadline_scope": "regra PURA do calendário; não consulta nada",
    "visit_scope": "regra PURA das visitas; não consulta nada",
    "finance_scope": (
        "a fronteira das finanças deriva da EMPRESA e não da rede "
        "(D-24): `process_finances` nunca teve `network_id`"
    ),
    "finance_process_records": (
        "a colecção é `db.process_finances`, com fronteira própria"
    ),
    "client_match": (
        "a âncora é o DOCUMENTO (`condicao_da_mesma_rede`, D-24) e não "
        "o utilizador: corre em background, sem sessão"
    ),
    "match_api_smart": (
        "o Smart Match ancora-se no DOCUMENTO e não no utilizador "
        "(`condicao_da_mesma_rede`, D-24): um cruzamento liga duas "
        "pontas da mesma rede"
    ),
    "portal_recommendations": (
        "a recomendação ancora-se no processo do cliente do Portal, "
        "pela mesma regra do Smart Match (D-24)"
    ),
    "property_list": "a colecção é `db.properties` (a carteira, D-24)",
    "property_crud": "a colecção é `db.properties` (a carteira, D-24)",
    "webmail_scope": "a colecção é `db.emails` (ver a D-8, em aberto)",
    "realtime_audience": (
        "audiência de WebSocket: decide a quem se difunde um evento, "
        "não o que uma listagem devolve"
    ),
    "visit_list_create": "a colecção é `db.visits` (fronteira própria, D-21)",
    "visit_kanban_get": "a colecção é `db.visits` (fronteira própria, D-21)",
    "deadlines_api_list": "a colecção é `db.deadlines` (fronteira própria)",
    "tenant_network": "é o próprio ponto único de onde tudo isto deriva",
}

CONSTRUTORES_DE_PROCESSOS = (
    "build_tenant_process_condition",
    "build_process_scope_condition",
)


def _modulos_com_condicao_de_tenant() -> dict[str, str]:
    """Módulos de `services/` que usam uma condição de tenant. Derivado."""
    import pathlib

    encontrados: dict[str, str] = {}
    for caminho in sorted(pathlib.Path("services").glob("*.py")):
        texto = caminho.read_text(encoding="utf-8")
        if any(
            chamada in texto
            for chamada in (
                "build_tenant_condition(",
                "build_network_scope_condition(",
                "build_tenant_pool_condition(",
                *(f"{c}(" for c in CONSTRUTORES_DE_PROCESSOS),
            )
        ):
            encontrados[caminho.stem] = texto
    return encontrados


def test_o_leitor_do_inventario_le_mesmo_os_modulos():
    """Contraprova: uma asserção da forma «X in encontrados» continua a
    passar com um leitor que devolva pouco. É a regra de toda a leitura
    por AST deste projecto."""
    encontrados = _modulos_com_condicao_de_tenant()
    assert len(encontrados) >= 15, (
        f"o leitor só encontrou {len(encontrados)} módulos — está cego"
    )
    assert "process_list_enrichment" in encontrados
    assert "tenant_network" in encontrados


def test_quem_LISTA_processos_usa_a_condicao_de_PROCESSOS():
    """Falha por OMISSÃO: uma superfície nova que consulte `db.processes`
    com a condição genérica e não esteja nas excepções ESCRITAS fica
    vermelha, e o nome dela aparece na mensagem."""
    faltam: list[str] = []
    for nome, texto in _modulos_com_condicao_de_tenant().items():
        if nome in EXCEPCOES_ESCRITAS:
            continue
        toca_processos = any(
            f"db.processes.{op}" in texto
            for op in ("find", "count_documents", "aggregate", "distinct")
        )
        if not toca_processos:
            continue
        if not any(c in texto for c in CONSTRUTORES_DE_PROCESSOS):
            faltam.append(nome)

    assert faltam == [], (
        "estas superfícies consultam `db.processes` com a condição "
        "GENÉRICA e esconderiam um processo partilhado a quem o trabalha: "
        f"{faltam}. Use `build_tenant_process_condition` ou escreva o "
        "motivo em EXCEPCOES_ESCRITAS."
    )


def test_as_excepcoes_sao_todas_REAIS():
    """Uma excepção para um módulo que já não existe é uma excepção que
    protege um módulo novo com o mesmo nome. E uma sem motivo é o começo
    de uma lista de exclusão que ninguém revê."""
    import pathlib

    for nome, motivo in EXCEPCOES_ESCRITAS.items():
        assert pathlib.Path(f"services/{nome}.py").exists(), (
            f"a excepção `{nome}` aponta para um módulo que não existe"
        )
        assert len(motivo) > 20, f"a excepção `{nome}` não tem motivo escrito"
