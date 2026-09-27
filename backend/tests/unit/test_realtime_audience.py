"""A Parede no Envelope — quem alcança um evento de tempo real (Épico 10, Fase 2).

Até aqui o tempo real de processos fazia `manager.broadcast()`: um delta com
`client_name` chegava a TODOS os sockets ligados, incluindo os de uma rede
isolada. O isolamento do Lote 4/5 vive todo nas *queries* e o WebSocket não faz
query nenhuma — por isso a fuga passou entre os pingos.

A regra nova: um evento não sabe para quem vai, **declara a que audiência
pertence**; quem decide é o socket, que conhece o seu `TenantScope` desde o
handshake. Zero queries por evento.

O teste central deste ficheiro é `TestOsDoisDialectos`: `alcanca` (Python) e
`build_network_scope_condition` + `build_kanban_role_base_query` (Mongo) são
duas escritas da MESMA regra, e uma divergência silenciosa reabre a fuga.
"""
from __future__ import annotations

import inspect

import pytest

from models.auth import UserRoleEnum as UserRole
from services.realtime_audience import (
    Audiencia,
    alcanca,
    audiencia_do_processo,
)
from services.tenant_network import TenantScope


# ── Fixtures de domínio: a topologia real do produto ──────────────────
# Power e Precision partilham dados; a Domus é uma ilha.
REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "domus"

EMPRESA_POWER = "cmp-power"
EMPRESA_PRECISION = "cmp-precision"
EMPRESA_DOMUS = "cmp-domus"


def processo(
    *,
    rede=REDE_POWER,
    company_id=EMPRESA_POWER,
    company_name="Power Real Estate",
    consultores=(),
    mediadores=(),
    indexadores=(),
    status="em_analise",
):
    doc = {
        "id": "proc-1",
        "client_name": "Maria Silva",
        "status": status,
        "is_deleted": False,
    }
    if rede:
        doc["network_id"] = rede
    if company_id:
        doc["company_id"] = company_id
    if company_name:
        doc["company_name"] = company_name
    if consultores:
        doc["assigned_consultor_ids"] = list(consultores)
    if mediadores:
        doc["assigned_mediador_ids"] = list(mediadores)
    if indexadores:
        doc["assigned_indexacao_id"] = indexadores[0]
    return doc


def escopo(*, redes=(REDE_POWER,), empresas=(EMPRESA_POWER,), nomes=(), omissao=False):
    return TenantScope(
        network_ids=tuple(redes),
        company_ids=tuple(empresas),
        company_names=tuple(nomes),
        inclui_rede_de_omissao=omissao,
    )


class TestAudienciaDoProcesso:
    """A audiência LÊ o carimbo que já está no documento — não pergunta."""

    def test_nao_e_uma_corotina(self):
        """Se fosse async, seria uma query por evento — o que o desenho evita.

        Esta é a garantia de custo, não de correcção: a função não pode
        tocar na base de dados porque não tem como esperar por ela.
        """
        assert not inspect.iscoroutinefunction(audiencia_do_processo)

    def test_le_o_carimbo_do_lote_4(self):
        aud = audiencia_do_processo(processo())
        assert aud.network_id == REDE_POWER
        assert aud.company_id == EMPRESA_POWER
        assert aud.sem_carimbo is False

    def test_recolhe_as_atribuicoes_nas_duas_formas(self):
        """Os campos canónicos são plurais E singulares (Lote 5, ponto 4)."""
        doc = processo(consultores=["u1"])
        doc["assigned_consultor_id"] = "u2"
        aud = audiencia_do_processo(doc)
        assert set(aud.consultor_ids) == {"u1", "u2"}

    def test_processo_por_carimbar_e_marcado_como_tal(self):
        doc = processo(rede=None, company_id=None, company_name=None)
        aud = audiencia_do_processo(doc)
        assert aud.sem_carimbo is True

    def test_carimbo_parcial_nao_conta_como_por_carimbar(self):
        """"Por carimbar" exige ausência de TODAS as marcas (Lote 4).

        Um documento com empresa mas sem rede não pode cair na pilha por
        carimbar: seria visível a quem inclui a rede de omissão, que é
        precisamente a cláusula que a fuga usaria para entrar.
        """
        doc = processo(rede=None)
        assert audiencia_do_processo(doc).sem_carimbo is False


class TestCamada1Rede:
    """A fronteira de segurança. Inegociável."""

    def test_mesma_rede_alcanca(self):
        assert alcanca(
            audiencia_do_processo(processo()),
            escopo(),
            user_id="u1",
            role=UserRole.ADMIN,
        )

    def test_a_domus_nao_alcanca_a_power(self):
        """O caso que motivou todo o Épico 10."""
        assert not alcanca(
            audiencia_do_processo(processo(rede=REDE_POWER)),
            escopo(redes=(REDE_DOMUS,), empresas=(EMPRESA_DOMUS,)),
            user_id="u-domus",
            role=UserRole.ADMIN,
        )

    def test_precision_alcanca_power_pela_rede_partilhada(self):
        assert alcanca(
            audiencia_do_processo(processo(rede=REDE_POWER, company_id=EMPRESA_POWER)),
            escopo(redes=(REDE_POWER,), empresas=(EMPRESA_PRECISION,)),
            user_id="u-prec",
            role=UserRole.CEO,
        )

    def test_empresa_por_nome_tambem_alcanca(self):
        """O histórico grava a empresa ora por id ora por nome."""
        aud = audiencia_do_processo(processo(rede=None, company_id=None))
        assert alcanca(
            aud,
            escopo(redes=(), empresas=(), nomes=("Power Real Estate",)),
            user_id="u1",
            role=UserRole.ADMIN,
        )

    def test_por_carimbar_so_alcanca_quem_inclui_a_omissao(self):
        aud = audiencia_do_processo(processo(rede=None, company_id=None, company_name=None))
        assert alcanca(aud, escopo(omissao=True), user_id="u1", role=UserRole.ADMIN)
        assert not alcanca(aud, escopo(omissao=False), user_id="u1", role=UserRole.ADMIN)


class TestFalhaFechada:
    """Uma audiência vazia é NINGUÉM, nunca toda a gente.

    É a mesma lei do `CONDICAO_IMPOSSIVEL` e do `resolve_ucr_mailbox_filter`
    que devolvia `None`: um âmbito sem ramos não pode significar "sem filtro".
    """

    def test_audiencia_vazia_nao_alcanca_ninguem(self):
        vazia = Audiencia()
        assert not alcanca(vazia, escopo(), user_id="u1", role=UserRole.ADMIN)
        assert not alcanca(vazia, escopo(omissao=True), user_id="u1", role=UserRole.ADMIN)

    def test_escopo_vazio_nao_alcanca_nada(self):
        assert not alcanca(
            audiencia_do_processo(processo()),
            TenantScope(),
            user_id="u1",
            role=UserRole.ADMIN,
        )

    def test_audiencia_none_nao_rebenta_nem_alcanca(self):
        assert not alcanca(None, escopo(), user_id="u1", role=UserRole.ADMIN)


class TestCamada2NecessidadeDeSaber:
    """Espelha `build_kanban_role_base_query`: o quadro e o tempo real
    têm de mostrar o mesmo, senão aparece um cartão que o F5 apaga."""

    def test_consultor_atribuido_alcanca(self):
        assert alcanca(
            audiencia_do_processo(processo(consultores=["u1"])),
            escopo(),
            user_id="u1",
            role=UserRole.CONSULTOR,
        )

    def test_consultor_nao_atribuido_nao_alcanca(self):
        assert not alcanca(
            audiencia_do_processo(processo(consultores=["outro"])),
            escopo(),
            user_id="u1",
            role=UserRole.CONSULTOR,
        )

    def test_intermediario_segue_a_sua_propria_atribuicao(self):
        aud = audiencia_do_processo(processo(consultores=["u1"], mediadores=["u2"]))
        assert alcanca(aud, escopo(), user_id="u2", role=UserRole.INTERMEDIARIO)
        assert not alcanca(aud, escopo(), user_id="u1", role=UserRole.INTERMEDIARIO)

    @pytest.mark.parametrize(
        "papel",
        [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO],
    )
    def test_gestao_alcanca_sem_atribuicao(self, papel):
        assert alcanca(
            audiencia_do_processo(processo(consultores=["outro"])),
            escopo(),
            user_id="u1",
            role=papel,
        )

    def test_indexacao_alcanca_a_fila_de_espera(self):
        aud = audiencia_do_processo(processo(status="fila_espera"))
        assert alcanca(aud, escopo(), user_id="u1", role=UserRole.INDEXACAO)

    def test_indexacao_nao_alcanca_processo_alheio_fora_da_fila(self):
        aud = audiencia_do_processo(processo(indexadores=["outro"]))
        assert not alcanca(aud, escopo(), user_id="u1", role=UserRole.INDEXACAO)

    def test_a_rede_vence_a_atribuicao(self):
        """Estar atribuído não fura a rede: as duas camadas são um E."""
        aud = audiencia_do_processo(processo(rede=REDE_POWER, consultores=["u1"]))
        assert not alcanca(
            aud,
            escopo(redes=(REDE_DOMUS,), empresas=(EMPRESA_DOMUS,)),
            user_id="u1",
            role=UserRole.CONSULTOR,
        )


# ════════════════════════════════════════════════════════════════════
# O TESTE CENTRAL: os dois dialectos da mesma regra
# ════════════════════════════════════════════════════════════════════

from tests.unit.conftest import FakeAsyncCollection  # noqa: E402
from services.process_list_filters import build_kanban_role_base_query  # noqa: E402
from services.tenant_network import build_network_scope_condition  # noqa: E402


def _veredicto_mongo(doc: dict, scope: TenantScope, *, user_id: str, role: str) -> bool:
    """A MESMA regra, escrita em Mongo — como a listagem a aplica.

    `is_deleted` é retirado de propósito: filtra o que o quadro LISTA, não
    quem tem direito a SABER. Quem via o processo tem de receber o evento
    que o apaga, senão fica com um cartão fantasma até ao F5. É a única
    diferença legítima entre os dois dialectos, e está aqui escrita para
    ninguém a "corrigir" alinhando-a no sítio errado.
    """
    base = dict(build_kanban_role_base_query({"id": user_id}, role, show_all=False))
    base.pop("is_deleted", None)
    condicao = {"$and": [base, build_network_scope_condition(scope)]}
    return FakeAsyncCollection._matches(doc, condicao)


# Matriz deliberadamente cruel: cada processo contra cada âmbito e cada papel.
_PROCESSOS = {
    "power_do_u1": processo(consultores=["u1"]),
    "power_de_outro": processo(consultores=["outro"]),
    "power_mediado_por_u1": processo(mediadores=["u1"]),
    "domus": processo(rede=REDE_DOMUS, company_id=EMPRESA_DOMUS, company_name="Domus"),
    "domus_do_u1": processo(
        rede=REDE_DOMUS, company_id=EMPRESA_DOMUS, company_name="Domus",
        consultores=["u1"],
    ),
    "por_carimbar": processo(rede=None, company_id=None, company_name=None),
    "so_com_empresa": processo(rede=None),
    "fila_de_espera": processo(status="fila_espera"),
    "indexado_por_u1": processo(indexadores=["u1"]),
}

_ESCOPOS = {
    "power": escopo(redes=(REDE_POWER,), empresas=(EMPRESA_POWER,)),
    "precision": escopo(redes=(REDE_POWER,), empresas=(EMPRESA_PRECISION,)),
    "domus": escopo(redes=(REDE_DOMUS,), empresas=(EMPRESA_DOMUS,)),
    "power_com_omissao": escopo(redes=(REDE_POWER,), empresas=(EMPRESA_POWER,), omissao=True),
    "orfao": TenantScope(),
}

_PAPEIS = [
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,
    UserRole.INDEXACAO,
]


class TestOsDoisDialectos:
    """`alcanca` (Python) e a condição Mongo têm de dar o MESMO veredicto.

    São duas escritas da mesma regra: uma decide quem recebe o evento em
    tempo real, a outra decide quem vê a linha na listagem. Se divergirem,
    ou aparece um cartão que o utilizador não podia ver (a fuga de volta),
    ou falta-lhe um que ele vê ao recarregar (o tempo real a mentir).
    """

    @pytest.mark.parametrize("nome_proc", sorted(_PROCESSOS))
    @pytest.mark.parametrize("nome_escopo", sorted(_ESCOPOS))
    @pytest.mark.parametrize("papel", _PAPEIS)
    def test_veredictos_coincidem(self, nome_proc, nome_escopo, papel):
        doc = _PROCESSOS[nome_proc]
        scope = _ESCOPOS[nome_escopo]

        python = alcanca(audiencia_do_processo(doc), scope, user_id="u1", role=papel)
        mongo = _veredicto_mongo(doc, scope, user_id="u1", role=papel)

        assert python == mongo, (
            f"DIALECTOS DIVERGEM em {nome_proc} / {nome_escopo} / {papel}: "
            f"alcanca={python}, mongo={mongo}"
        )

    def test_a_matriz_exercita_os_dois_veredictos(self):
        """Contraprova: uma matriz que só desse `False` alinharia por acaso.

        Sem isto, um `alcanca` que devolvesse sempre `False` passaria no
        teste acima desde que a condição Mongo também não casasse nunca.
        """
        veredictos = {
            alcanca(audiencia_do_processo(doc), scope, user_id="u1", role=papel)
            for doc in _PROCESSOS.values()
            for scope in _ESCOPOS.values()
            for papel in _PAPEIS
        }
        assert veredictos == {True, False}


class TestCasosQueAsMutacoesDenunciaram:
    """Lacunas que a bateria de mutação expôs — e que eram reais.

    Três mutações sobreviveram à primeira passagem. Nenhuma era código
    morto: eram comportamentos que eu tinha escrito e não tinha afirmado.
    """

    def test_presenca_alcanca_um_consultor(self):
        """M7: sem isto, `toda_a_rede` podia deixar de dispensar a Camada 2
        e ninguém dava por ela.

        Um evento de presença não tem processo a que estar atribuído. Se a
        Camada 2 se aplicasse, os consultores e intermediários — a maioria
        das pessoas — deixavam de ver quem está online, e o defeito não
        partia teste nenhum porque só os papéis de gestão estavam cobertos.
        """
        presenca = Audiencia(network_id=REDE_POWER, toda_a_rede=True)
        for papel in (UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO):
            assert alcanca(presenca, escopo(), user_id="u-sem-carteira", role=papel), papel

    def test_presenca_continua_presa_a_rede(self):
        """A dispensa é da Camada 2, nunca da Camada 1."""
        presenca = Audiencia(network_id=REDE_POWER, toda_a_rede=True)
        assert not alcanca(
            presenca,
            escopo(redes=(REDE_DOMUS,), empresas=(EMPRESA_DOMUS,)),
            user_id="u-domus",
            role=UserRole.ADMIN,
        )

    def test_escopo_ausente_falha_fechado_e_nao_rebenta(self):
        """M9: sem âmbito, `_passa_a_rede` rebentaria em AttributeError.

        Transformar isso em `False` é a diferença entre falhar fechado e
        falhar de maneira imprevisível — e é o router que depende disto
        quando uma ligação não tem âmbito resolvido.
        """
        assert alcanca(audiencia_do_processo(processo()), None,
                       user_id="u1", role=UserRole.ADMIN) is False
