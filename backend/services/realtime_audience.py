"""A Parede no Envelope: quem alcança um evento de tempo real.

ÉPICO 10, FASE 2 — o problema que este módulo fecha
====================================================
O tempo real de processos fazia ``manager.broadcast()``: um delta com o
``client_name`` chegava a TODOS os sockets ligados. O isolamento por Rede do
Lote 4/5 vive inteiro nas *queries* e o WebSocket não faz query nenhuma — por
isso um processo criado na Power inseria um cartão, com o nome do cliente, no
Kanban de quem estivesse ligado na Domus.

A REGRA
-------
Um evento não sabe para quem vai. Declara a que **audiência** pertence, e quem
decide é o socket, que conhece o seu ``TenantScope`` desde o handshake. Assim
não há uma query por evento: o emissor já tem o documento do processo em mãos
(leu-o para fazer o trabalho) e o carimbo do Lote 4 está lá dentro.

    emissor → audiencia_do_processo(process)   ← zero I/O
            → publish_event(..., audiencia=)   ← UM envelope
            → alcanca(aud, scope_em_cache)     ← zero I/O, em cada worker

DUAS CAMADAS, E TÊM DE PASSAR AMBAS
-----------------------------------
1. **Rede** — a fronteira de segurança, inegociável. Espelha
   ``tenant_network.build_network_scope_condition``.
2. **Necessidade de saber** — espelha
   ``process_list_filters.build_kanban_role_base_query``. Não é segurança: é
   impedir que apareça no quadro de um consultor um cartão que o ``GET`` nunca
   lhe devolveria, e que desapareceria ao recarregar.

DOIS DIALECTOS DA MESMA REGRA
-----------------------------
As funções deste módulo são a escrita **em Python** de uma regra que já existe
escrita **em Mongo**. Podem divergir em silêncio, e uma divergência reabre a
fuga. É por isso que ``tests/unit/test_realtime_audience.py::TestOsDoisDialectos``
corre as duas sobre a mesma matriz e exige o mesmo veredicto — alterar uma
destas funções sem a outra faz esse teste ficar vermelho, que é exactamente o
que se pretende.

FALHA FECHADA
-------------
Uma ``Audiencia`` sem rede, sem empresa e sem ``sem_carimbo`` não alcança
NINGUÉM — não é "toda a gente". É a mesma lei do ``CONDICAO_IMPOSSIVEL`` e do
``resolve_ucr_mailbox_filter`` que devolvia ``None``: um âmbito sem ramos nunca
pode significar "sem filtro".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

from models.auth import UserRoleEnum as UserRole
from services.tenant_network import VALORES_SEM_EMPRESA, TenantScope

# Perfis cuja vista do quadro não é filtrada por atribuição. Espelha o
# fall-through de `build_kanban_role_base_query` — lá a ausência de `if` é
# que os isenta, e uma lista explícita aqui torna a regra legível.
PAPEIS_SEM_FILTRO_DE_ATRIBUICAO = frozenset({
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
})

# O estado que a Indexação vê mesmo sem lhe estar atribuído.
STATUS_FILA_DE_ESPERA = "fila_espera"

# Campos canónicos de atribuição (Lote 5, ponto 4: o `set` e o `clear`
# derivam da mesma constante; aqui a LEITURA deriva dela também).
CAMPOS_CONSULTOR = ("assigned_consultor_ids", "assigned_consultor_id")
CAMPOS_MEDIADOR = ("assigned_mediador_ids", "assigned_mediador_id")
CAMPOS_INDEXACAO = ("assigned_indexacao_ids", "assigned_indexacao_id")

# As três formas como o histórico grava a empresa (igual a `tenant_network`).
CAMPOS_EMPRESA = ("company_id", "company", "company_name")
CAMPO_REDE = "network_id"


def _texto(valor: Any) -> str:
    """Normaliza para texto, desembrulhando Enums.

    ``str()`` sobre um Enum com mistura de ``str`` devolve
    ``"UserRoleEnum.CONSULTOR"`` no Python 3.11, não ``"consultor"``. Sem
    este desembrulho, um papel chegado como membro do Enum (é assim que
    metade do código o passa) não casava com nada e o evento não alcançava
    ninguém — falha fechada, mas o tempo real ficava mudo.
    """
    if valor is None:
        return ""
    if isinstance(valor, Enum):
        valor = valor.value
    return str(valor).strip()


def _ids(doc: dict, campos: Iterable[str]) -> tuple[str, ...]:
    """Recolhe ids de atribuição das formas plural E singular."""
    encontrados: list[str] = []
    for campo in campos:
        valor = doc.get(campo)
        if isinstance(valor, (list, tuple, set)):
            encontrados.extend(_texto(v) for v in valor)
        elif valor is not None:
            encontrados.append(_texto(valor))
    return tuple(dict.fromkeys(v for v in encontrados if v))


@dataclass(frozen=True)
class Audiencia:
    """A quem um evento de processo diz respeito — sem enumerar pessoas."""

    network_id: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    consultor_ids: tuple[str, ...] = field(default_factory=tuple)
    mediador_ids: tuple[str, ...] = field(default_factory=tuple)
    indexacao_ids: tuple[str, ...] = field(default_factory=tuple)
    em_fila_de_espera: bool = False
    # A pilha por carimbar do Lote 4 (nem rede, nem empresa).
    sem_carimbo: bool = False
    # Quem tem de receber ESTE evento apesar de já não estar atribuído —
    # tipicamente o consultor que acabou de ser removido da equipa. Sem
    # isto, a última pessoa a precisar da notícia é a única a não a
    # receber, e fica com um cartão fantasma no quadro até ao F5.
    # Dispensa a Camada 2 (necessidade de saber), NUNCA a Camada 1 (rede).
    extra_user_ids: tuple[str, ...] = field(default_factory=tuple)
    # O evento é para toda a rede, não para a equipa de um processo — a
    # presença de alguém (`USER_ONLINE`), por exemplo. Dispensa a Camada 2
    # (não há processo a que estar atribuído), NUNCA a Camada 1: um colega
    # a ligar-se na Power não é notícia para quem está na Domus.
    toda_a_rede: bool = False

    def tem_alcance(self) -> bool:
        """A audiência consegue alcançar alguém?

        Uma audiência sem rede, sem empresa e sem ``sem_carimbo`` não é
        "toda a gente" — é ninguém. O transporte usa isto para RECUSAR o
        envelope: se uma audiência vazia bastasse para publicar, bastaria um
        emissor esquecer-se de a preencher para reabrir o broadcast que este
        Épico fecha.
        """
        return bool(
            self.network_id or self.company_id or self.company_name or self.sem_carimbo
        )

    def para_envelope(self) -> dict:
        """Forma serializável que viaja no envelope do Redis (JSON)."""
        return {
            "network_id": self.network_id,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "consultor_ids": list(self.consultor_ids),
            "mediador_ids": list(self.mediador_ids),
            "indexacao_ids": list(self.indexacao_ids),
            "em_fila_de_espera": self.em_fila_de_espera,
            "sem_carimbo": self.sem_carimbo,
            "extra_user_ids": list(self.extra_user_ids),
            "toda_a_rede": self.toda_a_rede,
        }

    @classmethod
    def do_envelope(cls, dados: Any) -> Optional["Audiencia"]:
        """Reconstrói a audiência do lado do consumidor. Nunca levanta."""
        if not isinstance(dados, dict):
            return None
        try:
            return cls(
                network_id=dados.get("network_id") or None,
                company_id=dados.get("company_id") or None,
                company_name=dados.get("company_name") or None,
                consultor_ids=tuple(dados.get("consultor_ids") or ()),
                mediador_ids=tuple(dados.get("mediador_ids") or ()),
                indexacao_ids=tuple(dados.get("indexacao_ids") or ()),
                em_fila_de_espera=bool(dados.get("em_fila_de_espera")),
                sem_carimbo=bool(dados.get("sem_carimbo")),
                extra_user_ids=tuple(dados.get("extra_user_ids") or ()),
                toda_a_rede=bool(dados.get("toda_a_rede")),
            )
        except Exception:  # pragma: no cover — envelope corrompido
            return None


def audiencia_do_processo(
    process: dict, *, tambem_para: Iterable[str] = ()
) -> Audiencia:
    """Constrói a audiência a partir do documento do processo.

    **Síncrona de propósito**: não pode tocar na base de dados, porque um
    evento de tempo real não pode custar uma query. Tudo o que é preciso já
    está no documento que o emissor leu para fazer o seu trabalho.

    Args:
        tambem_para: ids que recebem apesar de não constarem das
            atribuições — quem acabou de sair da equipa. Continua sujeito à
            fronteira de rede.
    """
    doc = process or {}

    rede = _texto(doc.get(CAMPO_REDE))
    if rede in VALORES_SEM_EMPRESA:
        rede = ""

    empresa_id = ""
    empresa_nome = ""
    for campo in CAMPOS_EMPRESA:
        valor = _texto(doc.get(campo))
        if not valor or valor in VALORES_SEM_EMPRESA:
            continue
        if campo == "company_id" and not empresa_id:
            empresa_id = valor
        elif not empresa_nome:
            empresa_nome = valor

    # "Por carimbar" exige a ausência de TODAS as marcas (Lote 4): olhar só
    # para a rede deixaria a fuga entrar pela cláusula que a evita.
    sem_carimbo = not rede and not empresa_id and not empresa_nome

    return Audiencia(
        network_id=rede or None,
        company_id=empresa_id or None,
        company_name=empresa_nome or None,
        consultor_ids=_ids(doc, CAMPOS_CONSULTOR),
        mediador_ids=_ids(doc, CAMPOS_MEDIADOR),
        indexacao_ids=_ids(doc, CAMPOS_INDEXACAO),
        em_fila_de_espera=_texto(doc.get("status")) == STATUS_FILA_DE_ESPERA,
        sem_carimbo=sem_carimbo,
        extra_user_ids=tuple(
            dict.fromkeys(_texto(u) for u in (tambem_para or ()) if _texto(u))
        ),
    )


def _passa_a_rede(aud: Audiencia, scope: TenantScope) -> bool:
    """Camada 1 — espelha `build_network_scope_condition`."""
    if aud.network_id and aud.network_id in scope.network_ids:
        return True

    # O histórico grava a empresa ora por id ora por nome; aceitamos as duas
    # formas contra os dois conjuntos, como faz a condição Mongo.
    conhecidas = {*scope.company_ids, *scope.company_names}
    if conhecidas:
        for marca in (aud.company_id, aud.company_name):
            if marca and marca in conhecidas:
                return True

    if aud.sem_carimbo and scope.inclui_rede_de_omissao:
        return True

    return False


def _passa_a_necessidade_de_saber(aud: Audiencia, *, user_id: str, role: str) -> bool:
    """Camada 2 — espelha `build_kanban_role_base_query`."""
    papel = _texto(role).lower()
    uid = _texto(user_id)

    # Um evento de rede não tem processo a que estar atribuído.
    if aud.toda_a_rede:
        return True

    # Quem saiu da equipa recebe ESTE evento (e só passou a Camada 1).
    if uid and uid in aud.extra_user_ids:
        return True

    if papel == UserRole.INDEXACAO:
        # A Indexação tem âmbito próprio mesmo com show_all: o que lhe está
        # atribuído, mais a fila de espera.
        return uid in aud.indexacao_ids or aud.em_fila_de_espera

    if papel == UserRole.CONSULTOR:
        return uid in aud.consultor_ids

    if papel == UserRole.INTERMEDIARIO:
        return uid in aud.mediador_ids

    return papel in PAPEIS_SEM_FILTRO_DE_ATRIBUICAO


def alcanca(
    aud: Optional[Audiencia],
    scope: Optional[TenantScope],
    *,
    user_id: str,
    role: str,
) -> bool:
    """O evento desta audiência chega a este utilizador?

    As duas camadas são um **E**: estar atribuído a um processo não fura a
    fronteira de rede, e pertencer à rede não dá acesso à carteira alheia.
    """
    if aud is None or scope is None:
        return False
    if not _passa_a_rede(aud, scope):
        return False
    return _passa_a_necessidade_de_saber(aud, user_id=user_id, role=role)


def audiencia_das_redes_do_utilizador(scope: TenantScope) -> tuple[Audiencia, ...]:
    """Audiências que cobrem as redes de um utilizador — uma por rede.

    Serve eventos que não pertencem a nenhum processo (presença, por
    exemplo). Devolve uma audiência POR rede porque uma ``Audiencia`` fala
    de uma só; são eventos raros (ligar/desligar), pelo que o custo é
    irrelevante.

    Um utilizador sem rede nenhuma devolve **tupla vazia**: nada é emitido,
    em vez de um evento sem fronteira. Falha fechada.
    """
    if scope is None:
        return ()
    return tuple(
        Audiencia(network_id=rede, toda_a_rede=True)
        for rede in scope.network_ids
        if rede
    )
