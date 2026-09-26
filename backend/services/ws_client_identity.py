"""Identidade e alcance de um socket de CLIENTE do Portal.

PORQUE É QUE ISTO EXISTE
========================
O namespace dos WebSockets era interno. Abri-lo aos tokens dos clientes
externos é uma decisão de autorização — e até aqui o que impedia um token do
Portal de entrar era uma **coincidência**, não uma regra: o `sub` de um token
de Portal é um `process_id`, que simplesmente não existe em `db.users`. O
`verify_websocket_token` decifrava com o MESMO `JWT_SECRET` e nunca olhava
para a claim `type`.

Este módulo é o ponto único das três decisões que tornam a abertura segura:

1. **Que tipos de token são de quem** (`TIPOS_DO_PORTAL` / `TIPO_DO_STAFF`).
2. **Qual é a identidade de um socket de cliente** — `cliente:<process_id>`.
3. **O que um socket de cliente pode RECEBER** — uma lista de PERMISSÃO.

O PREFIXO `cliente:` PAGA TRÊS COISAS DE UMA VEZ
================================================
O `ConnectionManager` e o ZSET de presença são indexados por `user_id`. Dar ao
socket do cliente a identidade `cliente:<process_id>` em vez do `process_id`
cru resolve, com uma decisão só:

* **Presença** — o "quem está online" interno (`chat_presence`) lê o ZSET
  inteiro; sem namespace, os clientes apareciam na lista de consultores
  activos da ferramenta interna.
* **Reconhecimento** — a camada de entrega precisa de saber, olhando só para
  o identificador de um membro de uma sala, se aquele socket é de um cliente.
  Sem isso não há onde aplicar a lista de permissão.
* **Imunidade a eventos dirigidos** — todos os envelopes endereçados a
  `user_id` (tarefas, email novo) usam ids de `db.users`. Nenhum emissor
  escreve `cliente:...`, pelo que **nenhum** evento dirigido pode alcançar um
  cliente, nem por acidente de colisão de ids.

A LISTA É DE PERMISSÃO, E É APLICADA NA ENTREGA
===============================================
A sala `process_<id>` é de STAFF: transporta deltas do processo, bloqueios de
edição, progresso de scrapers e mensagens do Portal, emitidos de sete módulos
diferentes — e vai crescer.

Com uma lista de BLOQUEIO, um emissor novo fuga por omissão. Com uma lista de
PERMISSÃO aplicada na ENTREGA (e não na emissão), um emissor novo **não chega
ao cliente até alguém decidir que deve**. A omissão segura é a única que
sobrevive a seis meses de manutenção — e é na entrega porque é o único ponto
por onde todos os emissores passam.
"""
from __future__ import annotations

import logging
from typing import Optional

from services.websocket_manager import WSEventType

logger = logging.getLogger(__name__)


# ====================================================================
# 1. TIPOS DE TOKEN
# ====================================================================
# Os três tipos que o `portal_security` emite. Um token de cliente que não
# declare um destes não entra — nem no WebSocket do Portal, nem em lado nenhum.
TIPOS_DO_PORTAL: tuple[str, ...] = (
    "magic_link",
    "verified_session",
    "access_code_session",
)

# O tipo que o `auth.create_token` passou a estampar. Tokens de staff emitidos
# ANTES desta alteração não têm claim `type` nenhuma — é por isso que o lado do
# staff aceita `None` (ver `tipo_de_token_e_de_staff`). Essa tolerância pode
# cair quando todos os tokens em circulação tiverem expirado
# (`JWT_EXPIRATION_HOURS` depois do deploy).
TIPO_DO_STAFF = "staff"

# Tipos que existem no sistema e NÃO são de staff nem de Portal. Ficam
# nomeados para o guarda do staff os poder recusar explicitamente em vez de
# os deixar cair numa omissão.
TIPO_GOV = "gov_auth"

TIPOS_ESTRANHOS_AO_STAFF: tuple[str, ...] = (*TIPOS_DO_PORTAL, TIPO_GOV)


def tipo_de_token_e_do_portal(tipo: Optional[str]) -> bool:
    """`True` só para os três tipos oficiais do Portal. Lista de PERMISSÃO."""
    return tipo in TIPOS_DO_PORTAL


def tipo_de_token_e_de_staff(tipo: Optional[str]) -> bool:
    """`True` para um token de staff — incluindo os legados sem `type`.

    Aceitar `None` não é frouxidão: até este lote o `create_token` não
    estampava tipo nenhum, e recusar `None` invalidava **todas** as sessões
    abertas no momento do deploy. O que importa para a segurança é o outro
    lado: um tipo ESTRANHO (um token de Portal, um `gov_auth`) é recusado,
    e é por aí que a fuga entraria.
    """
    if tipo is None or tipo == "":
        return True
    return tipo == TIPO_DO_STAFF


# ====================================================================
# 2. IDENTIDADE DO SOCKET
# ====================================================================
PREFIXO_DO_CLIENTE = "cliente:"


def identidade_de_socket_do_cliente(process_id: str) -> str:
    """A identidade com que um cliente do Portal existe no `ConnectionManager`.

    Nunca o `process_id` cru: ver o cabeçalho do módulo — é este prefixo que
    dá o namespace da presença, o reconhecimento na entrega e a imunidade aos
    eventos dirigidos, tudo de uma vez.
    """
    return f"{PREFIXO_DO_CLIENTE}{process_id}"


def e_socket_de_cliente(identidade: Optional[str]) -> bool:
    """O identificador pertence a um socket de cliente do Portal?"""
    return bool(identidade) and str(identidade).startswith(PREFIXO_DO_CLIENTE)


def processo_da_identidade(identidade: str) -> Optional[str]:
    """O `process_id` de dentro de uma identidade de cliente, ou `None`."""
    if not e_socket_de_cliente(identidade):
        return None
    return str(identidade)[len(PREFIXO_DO_CLIENTE):] or None


def sem_clientes(identidades) -> set[str]:
    """Retira os sockets de cliente de um conjunto de identidades.

    É o filtro que o "quem está online" INTERNO usa: o ZSET de presença é um
    só e, sem isto, um cliente do Portal aparecia na lista de consultores
    activos do Chat da equipa.
    """
    return {str(i) for i in (identidades or ()) if not e_socket_de_cliente(i)}


# ====================================================================
# 3. O QUE UM CLIENTE PODE RECEBER
# ====================================================================
# Lista de PERMISSÃO. Acrescentar aqui é uma decisão deliberada; NÃO
# acrescentar é o comportamento por omissão, e é o seguro.
#
# Porque é que `document_uploaded` NÃO está aqui, apesar de ser o evento que
# os scrapers do Estado emitem: o seu próprio comentário na origem diz
# "Notificar EQUIPA via WebSocket". É um evento genérico, com um nome
# genérico, e nada impede que amanhã um upload da equipa o emita com o NOME do
# ficheiro no payload — e nesse dia o cliente passaria a ver nomes de
# documentos internos, em silêncio. O progresso visível ao cliente tem um
# evento PRÓPRIO (`PORTAL_GOV_PROGRESS`), com um contrato só dele.
EVENTOS_PERMITIDOS_AO_CLIENTE: frozenset[str] = frozenset({
    # A conversa com o consultor — a razão de ser desta ligação.
    WSEventType.PORTAL_MESSAGE,
    # Progresso dos scrapers do Estado (Finanças / Segurança Social), num
    # evento desenhado para o cliente: sem nomes de ficheiros, sem ids
    # internos, só a contagem e a origem.
    WSEventType.PORTAL_GOV_PROGRESS,
})


def evento_permitido_ao_cliente(event_type: Optional[str]) -> bool:
    """O socket de um cliente pode receber este tipo de evento?"""
    return event_type in EVENTOS_PERMITIDOS_AO_CLIENTE


def pode_entregar(identidade: Optional[str], event_type: Optional[str]) -> bool:
    """A decisão de entrega, para UM socket e UM evento.

    Um socket de staff recebe o que a sala transportar (a autorização dele foi
    feita à entrada da sala). Um socket de cliente recebe **só** o que está na
    lista de permissão — e o registo do que foi retido é `debug` de propósito:
    é o caso normal e esperado, não um incidente.
    """
    if not e_socket_de_cliente(identidade):
        return True
    if evento_permitido_ao_cliente(event_type):
        return True
    logger.debug(
        "[WS-CLIENTE] '%s' retido: não está na lista de permissão de %s",
        event_type, identidade,
    )
    return False
