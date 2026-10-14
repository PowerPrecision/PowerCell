"""Atribuição directa: só a pessoas da MESMA rede de quem atribui (Out 2026).

O QUE MUDOU, E PORQUÊ
=====================
Até aqui havia uma «Via Rápida»: atribuir um processo a alguém de outra
rede abria-o a essa rede (`sincronizar_parceiros`). Era cómodo e quebrava
a regra de encaminhamento B2B: quem atribuía **escolhia o utilizador
final** de outra rede, saltando a fila central de triagem dessa rede. E
tinha um buraco pior — um utilizador com associações em DUAS redes (o
caso real do grupo) abria a segunda rede por mero acaso, a quem só
queria atribuir a um colega.

Hoje a fronteira é esta, e é só esta:

* **atribuição directa** → o atribuído tem de pertencer a uma rede de
  quem atribui. Cruzar redes recusa-se (403, com o caminho certo);
* **passar um processo a outra rede** → obrigatoriamente pela Partilha
  Explícita («Partilhar com Empresa…», `POST /processes/{id}/partners`),
  que o põe na fila central do destino. O remetente nunca escolhe a
  pessoa; a distribuição é das regras da rede de destino.

REGRAS QUE NÃO SE PODEM PERDER
==============================
1. **Só se valida o que ENTRA.** Os atribuídos que já estavam no
   processo ficam como estão: a Via Rápida antiga deixou processos com
   gente de duas redes, e a interface devolve a lista inteira ao gravar
   — validar tudo bloqueava a edição de qualquer um deles.
2. **O Master não abre redes novas.** Não tem fronteira de dados, mas
   atribuir *como Master* não pode reabrir a Via Rápida pela janela: o
   que ele pode atribuir é o que o processo já alcança (a rede dona e as
   convidadas). Sem processo (criação), vale o destino.
3. **Falha FECHADA.** Um atribuído sem rede determinável não se atribui:
   o contrário abria a fronteira por não se saber a empresa de alguém.
4. **Um atribuído inexistente não é um erro daqui.** Os escritores já o
   ignoravam; fazê-lo responder 403 distinguia «não existe» de «não é
   da tua rede» e confirmava ids.
5. **A mensagem não nomeia ninguém** — nem a rede do atribuído.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from fastapi import HTTPException

from database import db
from services.tenant_network import (
    CAMPO_REDE,
    CAMPO_REDES_PARCEIRAS,
    TenantScope,
    redes_parceiras,
    resolve_tenant_scope,
    resolve_vista_scope,
)

logger = logging.getLogger(__name__)

#: O que o utilizador lê quando é recusado. Diz para onde ir; não diz quem.
MENSAGEM_DE_RECUSA = (
    "Só pode atribuir diretamente pessoas da sua própria rede. Para passar "
    "o processo a outra empresa use «Partilhar com Empresa…»: ele entra na "
    "fila de triagem dessa rede e é lá que é distribuído."
)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def redes_permitidas(
    ator: TenantScope,
    processo: Optional[dict] = None,
) -> Optional[set[str]]:
    """Que redes pode o ATOR atribuir. ``None`` = qualquer (só Master a criar).

    PURA — decide sobre o âmbito já resolvido.

    * utilizador normal → as redes a que ele próprio pertence;
    * Master (sem fronteira) → as redes que o processo já alcança; sem
      processo ainda, qualquer uma (o processo nasce na rede do destino,
      não abre nada que já existisse).
    """
    if not ator.sem_fronteira:
        return {r for r in ator.network_ids if r}
    if processo is None:
        return None
    alcance = {_texto(processo.get(CAMPO_REDE))} | set(redes_parceiras(processo))
    return {r for r in alcance if r}


async def redes_permitidas_do_ator(
    ator: dict,
    processo: Optional[dict] = None,
) -> Optional[set[str]]:
    """As redes que o ator pode atribuir, JÁ com a empresa que o Master escolheu (Lote 6).

    «Janela, não porta»: um processo partilhado não faz do Master um atribuidor de toda a gente
    que o processo alcança. Com a Domus seleccionada no cabeçalho, atribui-se Domus — nunca a
    Precision, mesmo num processo partilhado. Sem empresa escolhida (vista «Sistema») vale o
    que valia: o que o processo alcança.

    * utilizador normal → as redes a que pertence (a vista não o toca);
    * Master com empresa escolhida → a rede dessa empresa, e, se há processo, só se o processo a
      alcança (dono ou convidada): escolher a Domus num processo que não é dela não a abre.
    """
    from services.role_scope import conta_e_master
    from services.tenant_network import CAMPO_VISTA

    scope = await resolve_tenant_scope(ator)
    if not (conta_e_master(ator) and _texto((ator or {}).get(CAMPO_VISTA))):
        return redes_permitidas(scope, processo)
    vista = await resolve_vista_scope(ator)
    if vista.sem_fronteira:  # empresa que não existe (cabeçalho velho): não estreita
        return redes_permitidas(scope, processo)

    escolhidas = {r for r in vista.network_ids if r}
    if not scope.sem_fronteira:
        escolhidas &= {r for r in scope.network_ids if r}
    elif processo is not None:
        escolhidas &= redes_permitidas(scope, processo) or set()
    return escolhidas


async def redes_do_atribuido(utilizador: dict) -> Optional[set[str]]:
    """As redes de quem vai ser atribuído. ``None`` = sem fronteira (Master)."""
    scope = await resolve_tenant_scope(utilizador)
    if scope.sem_fronteira:
        return None
    return {r for r in scope.network_ids if r}


def pode_atribuir(
    permitidas: Optional[set[str]],
    redes_do_alvo: Optional[set[str]],
) -> bool:
    """O alvo cabe nas redes que o ator pode atribuir? PURA.

    * ator sem limite (`None`) → sim;
    * alvo sem limite (Master como atribuído) → sim: já vê tudo, não
      ganha nada;
    * alvo sem rede determinável → NÃO (falha fechada);
    * caso contrário, as redes têm de se cruzar.
    """
    if permitidas is None:
        return True
    if redes_do_alvo is None:
        return True
    if not redes_do_alvo:
        return False
    return bool(redes_do_alvo & permitidas)


async def exigir_atribuidos_da_minha_rede(
    ator: dict,
    ids: Iterable[str],
    *,
    processo: Optional[dict] = None,
    ja_atribuidos: Iterable[str] = (),
    base=None,
) -> None:
    """Levanta 403 se algum atribuído NOVO for de fora das redes do ator.

    `base` é a base de dados DO CHAMADOR (a referência ao proxy que o seu módulo tem): este
    módulo faz o seu próprio `from database import db`, e um teste que substitua só a do
    chamador deixava aqui falar com a base real — a armadilha da ordem de importação.

    `ja_atribuidos` são os que já estavam no processo (regra 1): não se
    revalidam. Ids inexistentes passam (regra 4) — quem escreve já os
    ignora.
    """
    # Atribuir-se a si próprio nunca atravessa uma rede: quem actua está sempre na sua. Sem esta
    # excepção, um utilizador cuja rede não se determina (UCR em falta) não conseguia criar uma
    # tarefa para si — que é o valor por omissão — e a falha fechada punia a vítima do dado em falta.
    proprio = _texto((ator or {}).get("id"))
    novos = [
        i for i in dict.fromkeys(_texto(i) for i in ids)
        if i and i != proprio and i not in {_texto(j) for j in ja_atribuidos}
    ]
    if not novos:
        return

    permitidas = await redes_permitidas_do_ator(ator, processo)
    if permitidas is None:
        return

    recusados: list[str] = []
    for uid in novos:
        alvo = await (base if base is not None else db).users.find_one(
            {"id": uid},
            {"_id": 0, "id": 1, "role": 1, "company": 1, "active_company_id": 1},
        )
        if not alvo:
            continue
        if not pode_atribuir(permitidas, await redes_do_atribuido(alvo)):
            recusados.append(uid)

    if recusados:
        logger.warning(
            "[ATRIBUICAO] %s tentou atribuir fora da sua rede (%d pessoa(s)); "
            "recusado — a passagem entre redes é a Partilha Explícita.",
            _texto((ator or {}).get("id")) or "?", len(recusados),
        )
        raise HTTPException(status_code=403, detail=MENSAGEM_DE_RECUSA)


async def ids_atribuiveis(
    ator: dict,
    utilizadores: list[dict],
    *,
    processo: Optional[dict] = None,
    ja_atribuidos: Iterable[str] = (),
) -> list[dict]:
    """Filtra uma lista de utilizadores para os que o ator pode atribuir.

    É o que a interface consome: a lista de «quem posso escolher» sai do
    servidor e não de um filtro no browser, para a regra não viver em
    dois sítios — e é a MESMA pergunta que o `exigir_atribuidos_da_minha_rede`
    faz a quem grava (`redes_permitidas` + `pode_atribuir`).

    Com `processo`, o Master vê só o que esse processo já alcança (dono +
    convidadas): oferecer-lhe tudo para depois responder 403 era a
    interface a contradizer o servidor. Os `ja_atribuidos` ficam sempre
    na lista, mesmo de fora — regra 1: a Via Rápida antiga deixou gente
    de duas redes e a interface devolve a lista inteira ao gravar; se o
    nome desaparecesse da lista, desaparecia da equipa sem ninguém o pedir.
    """
    permitidas = await redes_permitidas_do_ator(ator, processo)
    if permitidas is None:
        return list(utilizadores)
    mantidos = {_texto(i) for i in ja_atribuidos if _texto(i)}
    visiveis: list[dict] = []
    for u in utilizadores:
        if _texto(u.get("id")) in mantidos or pode_atribuir(
            permitidas, await redes_do_atribuido(u)
        ):
            visiveis.append(u)
    return visiveis


async def utilizadores_atribuiveis_ao_processo(
    ator: dict,
    utilizadores: list[dict],
    process_id: Optional[str],
) -> list[dict]:
    """A lista de atribuição quando a interface diz de que processo se trata.

    Só muda alguma coisa para quem não tem fronteira de dados (o Master):
    para todos os outros a lista já vem limitada às suas redes e o
    processo nada acrescenta. Processo inexistente (ou sem id) = sem
    processo, que é o caso da criação — vale o destino.
    """
    if not _texto(process_id):
        return list(utilizadores)
    if not (await resolve_tenant_scope(ator)).sem_fronteira:
        return list(utilizadores)

    from services.task_assignment_hygiene import (
        CAMPOS_DE_ATRIBUICAO_DO_PROCESSO,
        ids_atribuidos_do_processo,
    )

    # Só o que a pergunta precisa: o carimbo, as convidadas e a equipa.
    # Um `find_one` sem projecção traria o documento inteiro, com os
    # dados pessoais do cliente, para decidir uma dropdown.
    projeccao = {
        "_id": 0,
        CAMPO_REDE: 1,
        CAMPO_REDES_PARCEIRAS: 1,
        **{campo: 1 for campo in CAMPOS_DE_ATRIBUICAO_DO_PROCESSO},
    }
    processo = await db.processes.find_one({"id": _texto(process_id)}, projeccao)
    if not processo:
        return list(utilizadores)
    return await ids_atribuiveis(
        ator, utilizadores,
        processo=processo,
        ja_atribuidos=ids_atribuidos_do_processo(processo),
    )


__all__ = [
    "MENSAGEM_DE_RECUSA",
    "exigir_atribuidos_da_minha_rede",
    "ids_atribuiveis",
    "pode_atribuir",
    "redes_do_atribuido",
    "redes_permitidas",
    "redes_permitidas_do_ator",
    "utilizadores_atribuiveis_ao_processo",
]
