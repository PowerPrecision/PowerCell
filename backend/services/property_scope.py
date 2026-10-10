"""Quem vê e quem mexe num imóvel — `db.properties` (D-24, Out 2026).

O QUE CORREU MAL
================
A colecção `properties` não tinha fronteira de tenant em sítio NENHUM.
Zero ocorrências de `compan` ou `network` em **doze** módulos que lhe
tocam. E o documento leva `owner.name`, `owner.phone`, `owner.email` e
`owner.nif` — o proprietário de uma angariação — mais `client_name`, que
viaja já no item de LISTAGEM.

As quatro formas do defeito, as três primeiras já conhecidas desta casa:

1. **Listagens abertas.** `run_list_properties` abre com `query = {}`;
   `run_get_property_stats` conta e SOMA `count_documents({})` sobre a
   colecção inteira (a Domus lia o valor da carteira do grupo).
2. **Objecto sem posse.** `run_get_property`, `run_update_property`,
   `run_update_property_status` são `find_one({"id": ...})`, e
   `run_delete_property` é literalmente `delete_one({"id": ...})` — o
   `run_delete_deadline` do Lote 7 outra vez. A rota autoriza o VERBO,
   não o OBJECTO.
3. **Escrita sem carimbo.** `run_create_property` e a importação por
   Excel não gravavam empresa nem rede. Corrigir só a leitura tornava a
   correcção invisível para o trabalho NOVO — é a lição do `assigned_to`
   e, antes dela, a do `build_company_scope_condition`: cláusula que
   admite documentos sem marca + escritores que não marcam = tudo casa.
4. **O DESTINO.** `run_add_interested_client` e `run_register_visit`
   recebem um `client_id` que é um **process_id**, leem
   `db.processes.find_one` e gravam o `client_name` que lá encontram
   dentro do imóvel. Sem a pergunta do destino, quem soubesse um id de
   processo da Power extraía o nome do cliente para a sua própria
   carteira — e ficava lá escrito. É o `pode_apontar_para_o_processo` do
   calendário e o `pode_atribuir_a_consultor` das visitas, pelo mesmo
   motivo: **são duas perguntas, e juntá-las numa deixa a segunda por
   fazer.**

A CARTEIRA É DA REDE, NÃO DA PESSOA
===================================
Ao contrário das visitas e do calendário, aqui **não** há recorte por
pessoa, e isso é uma decisão e não um esquecimento: uma angariação é um
catálogo partilhado — é o consultor que precisa de ver o que a casa tem
para cruzar com os seus clientes, e o `agent_id` sempre foi um FILTRO da
query string e nunca uma fronteira. Inventar aqui um limite por pessoa
escondia trabalho real a quem o tem de fazer, e **um imóvel que
desaparece não produz erro nenhum**.

A fuga medida era entre REDES. É essa que fecha.

O LEGADO POR CARIMBAR NÃO É DE TODOS
====================================
`imovel_no_ambito` deriva do `documento_no_ambito`, que só admite o
documento sem marca quando o utilizador pertence à rede de omissão. É
deliberadamente MAIS ESTRITO do que a tolerância das visitas (onde uma
visita por carimbar entra para todos): a carteira existente está toda
por carimbar — nunca houve escritor que a carimbasse — logo tolerá-la a
todos seria entregar a carteira inteira do grupo incumbente à primeira
ilha que entrasse no sistema. É precisamente a fuga medida.

Em produção `TENANT_DEFAULT_NETWORK_ID` declara a quem pertence essa
pilha, e é isso que faz a regra funcionar sem migração nenhuma.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from fastapi import Request

from services.deadline_scope import e_papel_sem_fronteira
from services.tenant_network import (
    CAMPO_REDE,
    PROJECCAO_DO_CARIMBO,
    TenantScope,
    build_network_scope_condition,
    documento_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

#: A MESMA mensagem para "não existe" e para "não é teu" — e é a que o
#: código já devolvia, para o 404 ser indistinguível. Distinguir as duas
#: confirma o id a quem adivinha (precedente das notificações, do
#: calendário e das visitas), e quem é legítimo nunca a vê porque o
#: imóvel aparece-lhe na lista.
ERRO_IMOVEL_NAO_ENCONTRADO = "Imóvel não encontrado"

#: A projecção mínima de um `find_one` que alimente uma verificação de
#: posse. **Uma projecção que deixe o carimbo de fora cega a guarda** —
#: o documento chega sem rede, conta como legado e a guarda ABRE. Foi o
#: que o `run_get_interested_clients` fazia (`{"interested_clients": 1}`).
PROJECCAO_DE_POSSE: dict = {"_id": 0, "id": 1, **PROJECCAO_DO_CARIMBO}

#: Onde vive o processo a que um imóvel se liga. `interested_clients`
#: guarda **process_ids** (o nome é legado) e é por aí que o
#: `run_get_properties_by_process` o encontra.
CAMPOS_DE_PROCESSO = ("process_id", "client_id")


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def rede_do_imovel(imovel: Optional[dict]) -> str:
    return _texto((imovel or {}).get(CAMPO_REDE))


def imovel_no_ambito(imovel: Optional[dict], scope: TenantScope) -> bool:
    """A rede (ou a empresa) do imóvel é uma das do utilizador?"""
    return documento_no_ambito(imovel, scope)


def pode_ver_imovel(
    imovel: Optional[dict],
    *,
    papel: Any,
    scope: TenantScope,
) -> bool:
    """Pode este utilizador LER este imóvel?

    1. não há imóvel → não;
    2. MASTER → sim (único perfil global). O **diretor, o CEO e o Admin
       não** atravessam redes: têm passe livre DENTRO da sua, que é o que
       o ramo 3 lhes dá;
    3. o imóvel está no âmbito do utilizador → sim;
    4. o resto → não. **Falha fechada.**
    """
    if not imovel:
        return False
    if e_papel_sem_fronteira(papel):
        return True
    return imovel_no_ambito(imovel, scope)


def pode_mexer_no_imovel(
    imovel: Optional[dict],
    *,
    papel: Any,
    scope: TenantScope,
) -> bool:
    """Pode EDITAR, mudar o estado, documentar ou ELIMINAR este imóvel?

    Hoje é a mesma resposta da leitura, e isso é uma decisão: quem tem a
    angariação na carteira é quem lhe muda o preço e o estado ao
    telefone. Fica como função PRÓPRIA porque a pergunta é outra — se um
    dia a escrita tiver de ser mais estrita (como no calendário, onde o
    evento por carimbar entra na leitura e não na escrita), muda aqui e
    os doze chamadores não precisam de saber.

    Quem decide se o VERBO é permitido continua a ser o `require_roles`
    da rota: isto responde pelo OBJECTO.
    """
    return pode_ver_imovel(imovel, papel=papel, scope=scope)


def pode_apontar_para_o_processo(
    processo: Optional[dict],
    *,
    papel: Any,
    scope: TenantScope,
) -> bool:
    """Pode LIGAR um imóvel a este processo? (a pergunta do DESTINO)

    **Falha fechada:** um processo que não existe, ou que está fora do
    âmbito, é recusado. Sem isto, registar uma visita ou um interessado
    com um `process_id` de outra rede copiava o `client_name` de lá para
    dentro do imóvel — e ficava gravado.
    """
    if not processo:
        return False
    if e_papel_sem_fronteira(papel):
        return True
    return documento_no_ambito(processo, scope)


def processos_do_imovel(imovel: Optional[dict]) -> set[str]:
    ids = {
        _texto((imovel or {}).get(campo))
        for campo in CAMPOS_DE_PROCESSO
    }
    for valor in (imovel or {}).get("interested_clients") or []:
        ids.add(_texto(valor))
    return {i for i in ids if i}


async def ambito_dos_imoveis(user: dict) -> tuple[TenantScope, dict]:
    """O âmbito do utilizador e a condição Mongo correspondente.

    Devolve os DOIS porque as listagens precisam da condição e as
    verificações de posse precisam do âmbito — e resolvê-lo duas vezes
    por pedido era um `find` a mais em `companies` por cada verificação.
    """
    scope = await resolve_tenant_scope(user)
    return scope, build_network_scope_condition(scope)


def condicao_dos_imoveis_visiveis(
    *,
    papel: Any,
    condicao_de_rede: dict,
) -> dict:
    """O recorte da LISTAGEM.

    Para o MASTER é `{}` — e é o único sítio onde um `{}` que atravessa
    redes é deliberado, como a nota do `run_get_deadlines` manda dizer.
    Para todos os outros é a condição de REDE, aplicada por fora com o
    `com_isolamento`.
    """
    if e_papel_sem_fronteira(papel):
        return {}
    return dict(condicao_de_rede)


def redes_legiveis(scope: TenantScope) -> tuple[str, ...]:
    """As redes do âmbito, para registo em log (nunca para decidir)."""
    return tuple(_texto(r) for r in scope.network_ids if _texto(r))


def imoveis_no_ambito(
    imoveis: Iterable[dict],
    *,
    papel: Any,
    scope: TenantScope,
) -> list[dict]:
    """Filtra em memória — para listagens que agregam de várias fontes.

    Usado onde a consulta já foi feita por outra chave (o Smart Match, a
    recomendação do Portal): é a segunda linha de defesa, não a
    correcção, e a correcção é a condição ir na consulta.
    """
    return [
        imovel
        for imovel in imoveis or []
        if pode_ver_imovel(imovel, papel=papel, scope=scope)
    ]


# ====================================================================
# O CONTEXTO: resolvido UMA vez por pedido
# ====================================================================
# O papel vem do EFECTIVO e não do JWT. Decidir por `user["role"]` é a
# forma do `history._is_stealth_user`, e já deu as duas respostas erradas
# em quatro sítios diferentes deste projecto: quem tem perfil base de
# consultor e entra COMO diretor caía no ramo restrito, e quem é admin de
# base mantinha o passe livre com outro perfil activo.
#
# Resolver o papel efectivo exige o `Request` — só a ROTA o tem. É por
# isso que as rotas dos imóveis o declaram, e há um inventário por AST
# que falha por OMISSÃO para um endpoint novo que se esqueça dele.


@dataclass(frozen=True)
class ContextoDosImoveis:
    """Papel efectivo, âmbito e condição de listagem — de uma só vez."""

    papel: str = ""
    scope: TenantScope = field(default_factory=TenantScope)
    condicao: dict = field(default_factory=dict)


async def papel_efectivo(user: dict, request: Optional[Request] = None) -> str:
    """O papel com que o utilizador está a trabalhar AGORA.

    DERIVA do `tenant_access_context`, que é o ponto único — escrever a
    resolução aqui era a sexta cópia. A única diferença é o predicado
    que traduz `__all_roles__`: quem pergunta pela FRONTEIRA DE REDE
    quer o `e_papel_sem_fronteira`, e não o predicado de equipa do
    calendário, senão um administrador em modo global perdia o passe
    livre que o produto lhe dá.
    """
    from services.tenant_access_context import resolver_papel_efectivo

    return await resolver_papel_efectivo(
        user, request, traduzir_todos_os_perfis=e_papel_sem_fronteira
    )


async def carregar_contexto_dos_imoveis(
    user: dict,
    request: Optional[Request] = None,
) -> ContextoDosImoveis:
    """Papel efectivo + âmbito + condição da listagem, numa leitura."""
    papel = await papel_efectivo(user, request)
    scope, condicao_de_rede = await ambito_dos_imoveis(user)
    return ContextoDosImoveis(
        papel=papel,
        scope=scope,
        condicao=condicao_dos_imoveis_visiveis(
            papel=papel, condicao_de_rede=condicao_de_rede
        ),
    )


async def exigir_imovel_no_ambito(
    imovel: Optional[dict],
    *,
    user: dict,
    request: Optional[Request] = None,
    escrita: bool = False,
) -> ContextoDosImoveis:
    """Levanta **404** quando o imóvel não é deste utilizador.

    Devolve o contexto para o chamador não o resolver outra vez. O
    `escrita` escolhe a pergunta (hoje a resposta é a mesma, ver
    `pode_mexer_no_imovel`) e serve de documentação no sítio da chamada.
    """
    from fastapi import HTTPException

    contexto = await carregar_contexto_dos_imoveis(user, request)
    permitido = (
        pode_mexer_no_imovel(imovel, papel=contexto.papel, scope=contexto.scope)
        if escrita
        else pode_ver_imovel(imovel, papel=contexto.papel, scope=contexto.scope)
    )
    if not permitido:
        logger.warning(
            "[IMOVEIS] %s recusado: imóvel %s (rede=%r) fora do âmbito de %s "
            "(papel=%s, redes=%s)",
            "Escrita" if escrita else "Leitura",
            (imovel or {}).get("id"),
            rede_do_imovel(imovel),
            (user or {}).get("id"),
            contexto.papel,
            redes_legiveis(contexto.scope),
        )
        raise HTTPException(status_code=404, detail=ERRO_IMOVEL_NAO_ENCONTRADO)
    return contexto


__all__ = [
    "CAMPOS_DE_PROCESSO",
    "ContextoDosImoveis",
    "ERRO_IMOVEL_NAO_ENCONTRADO",
    "PROJECCAO_DE_POSSE",
    "ambito_dos_imoveis",
    "condicao_dos_imoveis_visiveis",
    "imovel_no_ambito",
    "imoveis_no_ambito",
    "pode_apontar_para_o_processo",
    "pode_mexer_no_imovel",
    "pode_ver_imovel",
    "processos_do_imovel",
    "rede_do_imovel",
    "redes_legiveis",
    "carregar_contexto_dos_imoveis",
    "exigir_imovel_no_ambito",
    "papel_efectivo",
]
