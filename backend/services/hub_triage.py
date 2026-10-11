"""
====================================================================
HUB & SPOKE — a Triagem (Index) vive no Hub (Bloco A, Out 2026)
====================================================================
O MODELO DO NEGÓCIO
  A Precision é o **Hub**: tem a equipa de Index. As redes satélite
  (Domus) NÃO têm Index e operam assim:

  * **Dentro da satélite** o processo nasce já a andar — não passa por
    nenhuma triagem (`aplicar_regime_de_indexacao`, no escritor);
  * **Ao ser partilhado com o Hub** (a Via Rápida: nasce da atribuição de
    alguém do Hub) o processo **entra imediatamente na fila de triagem
    do Hub** (`entrar_na_triagem_do_hub`);
  * **Via Verde (excepção):** se o processo tem `via_verde` ligada, a
    partilha salta o Index do Hub e fica logo à guarda da consultoria.

QUEM É O HUB
  `companies.is_hub` (booleano, só o Master o altera — é uma decisão de
  topologia, da mesma natureza do `network_id`). O Hub é a REDE dessas
  empresas. **Sem nenhum Hub configurado nada disto se liga**: sem Hub, a
  regra «a satélite não tem Index» tornaria TODAS as redes satélite —
  inclusive a da Precision — e os processos do grupo incumbente deixavam
  de passar pelo Index sem ninguém ter decidido.

AS EQUIPAS SÃO DA REDE (e não do mundo)
  Os pools de auto-atribuição (indexador, consultor, mediador) liam
  `db.users` inteiro: um processo da Domus era atribuído a um indexador
  ou consultor da Precision, sem partilha nenhuma. Agora o pool é o da
  **equipa do processo** (`rede_da_equipa`): a rede do dono, ou a do Hub
  depois de o processo entrar na triagem do Hub.

TRÊS REGRAS QUE NÃO SE PODEM PERDER
  1. A entrada é **idempotente**: o primeiro registo ganha. Uma segunda
     partilha, ou a repetição da sincronização, não repõe a triagem de
     um processo que o Index já tratou;
  2. **Sem Index disponível não se bloqueia**: o processo fica na fila
     sem indexador (o filtro «sem indexador» do Index mostra-o) — nunca
     parado à espera de alguém;
  3. Tudo o que isto escreve deixa **rasto** (histórico + trilho) e
     **nunca** faz a atribuição que o provocou falhar.
====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from database import db
from services.tenant_network import CAMPO_REDE, resolve_network_id

logger = logging.getLogger(__name__)

#: Campo da empresa que a torna Hub.
CAMPO_HUB = "is_hub"

#: Registo da entrada do processo na triagem do Hub.
CAMPO_TRIAGEM = "hub_triage"

#: A flag da excepção. Vive no PROCESSO (quem o partilha sabe se é urgente
#: ou se já vem triado) e é lida no momento da partilha.
CAMPO_VIA_VERDE = "via_verde"

ESTADO_EM_TRIAGEM = "triagem"
ESTADO_VIA_VERDE = "via_verde"

#: Como o processo ficou dispensado do Index da rede satélite.
MARCA_SATELITE = "rede_satelite"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ====================================================================
# QUEM É O HUB
# ====================================================================
async def hub_network_ids() -> set[str]:
    """As redes das empresas marcadas como Hub. Vazio = não há Hub.

    Falha FECHADA para o lado de «não há Hub»: uma leitura que falha
    desliga a regra (comportamento anterior) em vez de a ligar a
    metade — e é dito no log.
    """
    try:
        empresas = await db.companies.find(
            {CAMPO_HUB: True},
            {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1, CAMPO_HUB: 1},
        ).to_list(200)
    except Exception as exc:
        logger.warning("[HUB] Falha a ler as empresas Hub (%s); sem Hub.", exc)
        return set()

    return {
        rede
        for empresa in empresas
        if empresa.get(CAMPO_HUB) is True
        for rede in [resolve_network_id(empresa, company_id=empresa.get("id"))]
        if rede
    }


async def user_ids_da_rede(network_id: Any) -> Optional[set[str]]:
    """Os utilizadores que trabalham numa rede, ou ``None`` se não há rede.

    Um utilizador pertence à rede por QUALQUER das suas empresas (UCR) ou,
    nas contas antigas sem UCR, pelo `users.company` (o nome).
    ``None`` significa «sem restrição» — um processo por carimbar não
    tem equipa conhecida; um conjunto vazio significa «equipa vazia».
    """
    rede = _texto(network_id)
    if not rede:
        return None

    empresas = await db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
    ).to_list(1000)
    ids, nomes = [], []
    for empresa in empresas:
        if resolve_network_id(empresa, company_id=empresa.get("id")) == rede:
            if _texto(empresa.get("id")):
                ids.append(_texto(empresa["id"]))
            if _texto(empresa.get("name")):
                nomes.append(_texto(empresa["name"]))
    if not ids and not nomes:
        return set()

    membros: set[str] = set()
    ucrs = await db.user_company_roles.find(
        {"$or": [{"company_id": {"$in": ids}}, {"company_name": {"$in": nomes}}]},
        {"_id": 0, "user_id": 1},
    ).to_list(10000)
    membros.update(_texto(u.get("user_id")) for u in ucrs if _texto(u.get("user_id")))

    antigos = await db.users.find(
        {"company": {"$in": [*nomes, *ids]}}, {"_id": 0, "id": 1},
    ).to_list(10000)
    membros.update(_texto(u.get("id")) for u in antigos if _texto(u.get("id")))
    return membros


def rede_da_equipa(processo: Optional[dict]) -> str:
    """A rede cuja equipa trabalha o processo AGORA.

    A do Hub depois de o processo entrar na sua triagem (quem trabalha é
    o Hub), senão a do dono. Vazio = processo por carimbar (sem restrição).
    """
    processo = processo or {}
    triagem = processo.get(CAMPO_TRIAGEM)
    if isinstance(triagem, dict) and _texto(triagem.get(CAMPO_REDE)):
        return _texto(triagem[CAMPO_REDE])
    return _texto(processo.get(CAMPO_REDE))


async def restringir_a_equipa(consulta: dict, processo: Optional[dict]) -> dict:
    """Junta à consulta de utilizadores a restrição à equipa do processo."""
    membros = await user_ids_da_rede(rede_da_equipa(processo))
    if membros is None:
        return consulta
    return {"$and": [consulta, {"id": {"$in": sorted(membros)}}]}


# ====================================================================
# O REGIME DA SATÉLITE (escritor de processos)
# ====================================================================
async def processo_e_de_satelite(processo: Optional[dict]) -> bool:
    """O dono é uma rede satélite (há Hub, e não é a rede dele)?

    Um processo por carimbar NÃO é de satélite: sem saber de quem é, não
    se lhe tira o Index.
    """
    processo = processo or {}
    rede = _texto(processo.get(CAMPO_REDE))
    if not rede or isinstance(processo.get(CAMPO_TRIAGEM), dict):
        return False
    hubs = await hub_network_ids()
    return bool(hubs) and rede not in hubs


async def aplicar_regime_de_indexacao(process_doc: dict) -> bool:
    """A satélite não passa pelo Index: o processo nasce dispensado dele.

    Chamada por TODOS os escritores de processos, depois de carimbar e
    antes de gravar (inventário por AST em
    `test_hub_e_via_verde.py` — um escritor novo que a esqueça falha).
    Devolve se escreveu. Nunca sobrescreve `skip_index` já ligado.
    """
    try:
        if not await processo_e_de_satelite(process_doc):
            return False
    except Exception as exc:
        logger.warning(
            "[HUB] Falha a decidir o regime de indexação (%s); o processo "
            "mantém o comportamento por omissão.", exc,
        )
        return False

    process_doc["skip_index"] = True
    process_doc["index_dispensado_por"] = MARCA_SATELITE
    return True


# ====================================================================
# A ENTRADA NA TRIAGEM DO HUB (partilha)
# ====================================================================
def decidir_entrada(
    processo: dict,
    *,
    redes_do_hub_convidadas: Iterable[str],
) -> Optional[dict]:
    """A decisão, PURA: o que fazer com um processo que acaba de ser
    partilhado com o Hub. ``None`` = nada a fazer.

    * já tem registo de triagem → nada (idempotente, o primeiro ganha);
    * `via_verde` → registo ``via_verde``, o Index do Hub é saltado;
    * já indexado → registo ``via_verde`` com motivo (nada a triar);
    * senão → registo ``triagem``, entra na fila do Index do Hub.
    """
    hubs = [_texto(r) for r in redes_do_hub_convidadas if _texto(r)]
    if not hubs:
        return None
    if isinstance(processo.get(CAMPO_TRIAGEM), dict):
        return None

    rede_hub = hubs[0]
    via_verde = processo.get(CAMPO_VIA_VERDE) is True
    ja_indexado = processo.get("is_indexed") is True

    if via_verde or ja_indexado:
        return {
            "state": ESTADO_VIA_VERDE,
            CAMPO_REDE: rede_hub,
            "motivo": "via_verde" if via_verde else "ja_indexado",
        }
    return {"state": ESTADO_EM_TRIAGEM, CAMPO_REDE: rede_hub, "motivo": "partilha"}


async def entrar_na_triagem_do_hub(
    process_id: str,
    novas: list[dict],
    *,
    por_ordem_de: Any = None,
) -> Optional[dict]:
    """Aplica a entrada na triagem do Hub a um processo recém-partilhado.

    ``novas`` são as entradas que a partilha acabou de acrescentar. Só
    interessa a que seja uma rede Hub. Devolve o registo gravado, ou
    ``None`` quando não havia nada a fazer.
    """
    hubs = await hub_network_ids()
    convidadas_do_hub = [
        _texto(n.get(CAMPO_REDE)) for n in novas if _texto(n.get(CAMPO_REDE)) in hubs
    ]
    if not convidadas_do_hub:
        return None

    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1, CAMPO_REDE: 1, CAMPO_TRIAGEM: 1,
         CAMPO_VIA_VERDE: 1, "is_indexed": 1, "skip_index": 1,
         "assigned_indexacao_id": 1},
    )
    if not processo or _texto(processo.get(CAMPO_REDE)) in hubs:
        return None

    decisao = decidir_entrada(processo, redes_do_hub_convidadas=convidadas_do_hub)
    if not decisao:
        return None

    registo = {
        **decisao,
        "entered_at": _agora(),
        "entered_by": _texto(por_ordem_de),
        "from_network": _texto(processo.get(CAMPO_REDE)),
    }
    atualizacao: dict[str, Any] = {CAMPO_TRIAGEM: registo, "updated_at": registo["entered_at"]}
    if decisao["state"] == ESTADO_EM_TRIAGEM:
        # A satélite dispensou o Index; o Hub não. Sem isto os ficheiros
        # continuavam a entrar nas pastas finais e a IA nunca corria.
        atualizacao["skip_index"] = False
        atualizacao["index_dispensado_por"] = None

    await db.processes.update_one({"id": process_id}, {"$set": atualizacao})

    if decisao["state"] == ESTADO_EM_TRIAGEM:
        await _atribuir_indexador_do_hub(process_id, decisao[CAMPO_REDE])

    await _deixar_rasto(process_id, processo, registo, por_ordem_de)
    return registo


async def entrar_na_triagem_do_hub_sem_falhar(
    process_id: str, novas: list[dict], *, por_ordem_de: Any = None,
) -> Optional[dict]:
    """Versão que os escritores chamam: a partilha já está gravada, logo
    um erro aqui não pode fazer falhar a atribuição (regra de
    `sincronizar_parceiros_sem_falhar`). Falha **dita**, nunca calada."""
    try:
        return await entrar_na_triagem_do_hub(
            process_id, novas, por_ordem_de=por_ordem_de,
        )
    except Exception as exc:
        logger.warning(
            "[HUB] Falha a pôr o processo %s na triagem do Hub (%s); a "
            "partilha mantém-se mas o Index pode não o ver na fila.",
            process_id, exc,
        )
        return None


async def _atribuir_indexador_do_hub(process_id: str, rede_hub: str) -> None:
    """Tenta dar o processo a um indexador do Hub. Sem indexador não falha:
    o processo fica na fila (filtro «sem indexador»)."""
    try:
        from services.process_assignment import assign_to_indexer

        sucesso, dados, msg = await assign_to_indexer(
            process_id, update_status=False, network_id=rede_hub,
        )
        if not (sucesso and dados.get("assigned")):
            logger.info(
                "[HUB] Processo %s na fila de triagem sem indexador atribuído: %s",
                process_id, msg,
            )
    except Exception as exc:
        logger.warning(
            "[HUB] Falha a atribuir indexador do Hub ao processo %s (%s); "
            "fica na fila sem indexador.", process_id, exc,
        )


async def _deixar_rasto(
    process_id: str, processo: dict, registo: dict, por_ordem_de: Any,
) -> None:
    """Histórico + trilho. **Nunca** propaga."""
    texto = (
        "Processo entrou na fila de triagem (Index) do Hub"
        if registo["state"] == ESTADO_EM_TRIAGEM
        else "Processo partilhado com o Hub em Via Verde — salta o Index"
    )
    try:
        from services.history import log_history

        await log_history(
            process_id=process_id,
            user={"id": _texto(por_ordem_de) or "system", "name": "Sistema", "role": "admin"},
            action=texto,
            field=CAMPO_TRIAGEM,
            old_value="",
            new_value=registo["state"],
        )
    except Exception as exc:
        logger.warning("[HUB] Falha a registar no histórico de %s (%s).", process_id, exc)

    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id=process_id,
            user={"id": _texto(por_ordem_de)},
            action="hub_triage_entered",
            field=CAMPO_TRIAGEM,
            new_value=registo["state"],
            source="web",
            metadata={
                "process_number": processo.get("process_number"),
                "rede_do_dono": processo.get(CAMPO_REDE),
                "rede_do_hub": registo.get(CAMPO_REDE),
                "motivo": registo.get("motivo"),
            },
        )
    except Exception as exc:
        logger.warning("[HUB] Falha a registar no trilho de %s (%s).", process_id, exc)


__all__ = [
    "CAMPO_HUB",
    "CAMPO_TRIAGEM",
    "CAMPO_VIA_VERDE",
    "ESTADO_EM_TRIAGEM",
    "ESTADO_VIA_VERDE",
    "aplicar_regime_de_indexacao",
    "decidir_entrada",
    "entrar_na_triagem_do_hub",
    "entrar_na_triagem_do_hub_sem_falhar",
    "hub_network_ids",
    "processo_e_de_satelite",
    "rede_da_equipa",
    "restringir_a_equipa",
    "user_ids_da_rede",
]
