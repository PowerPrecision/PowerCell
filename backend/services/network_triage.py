"""
====================================================================
TRIAGEM (INDEX) POR REDE — multi-fornecedor (Out 2026)
====================================================================
(Substitui o «Hub & Spoke» do Bloco A. O ficheiro chamava-se
`hub_triage.py`; o campo gravado nos processos continua a ser
`hub_triage`, de propósito — ver abaixo.)

O MODELO DO NEGÓCIO
  Cada empresa/rede tem a sua operação. Algumas têm equipa de Index
  (análise documental); outras não e **pedem esse serviço a quem tem**:
  a Domus pede à Precision, outra imobiliária poderá pedir a uma terceira
  — e a mesma rede pode escolher entre vários fornecedores. Não há UM Hub.

  * **Dentro de uma rede sem Index** o processo nasce já a andar — não
    passa por nenhuma triagem (`aplicar_regime_de_indexacao`);
  * **Ao ser partilhado com uma rede de destino que TEM Index** (acção
    explícita «Partilhar com Empresa…» — a Via Rápida, por atribuição,
    foi extinta) o processo **entra na fila de triagem dessa rede
    específica**; quem remete nunca escolhe o utilizador final;
  * **Via Verde (excepção):** se o processo tem `via_verde` ligada, a
    partilha salta o Index do destino e fica logo à guarda da consultoria
    (ex.: processos que só precisam de intermediação de crédito).

QUEM TEM INDEX — DERIVADO, NÃO DECLARADO
  Uma rede «tem Index» quando tem pelo menos um utilizador activo com o
  perfil `indexacao` (a mesma noção do pool de `assign_to_indexer`: o
  indexador sai da equipa da rede). Não há flag a manter à mão — uma flag
  e a equipa real divergem sem dar erro, e a fila de uma rede sem
  indexadores seria um buraco negro que ninguém vê.

  **Sem nenhuma rede com Index nada disto se liga** (instalação nova, dev,
  CI): sem isso, a regra «esta rede não tem Index» tornaria TODAS as
  redes dispensadas, inclusive a do grupo incumbente.

AS EQUIPAS SÃO DA REDE (e não do mundo)
  Os pools de auto-atribuição (indexador, consultor, mediador) são os da
  **equipa do processo** (`rede_da_equipa`): a rede do dono, ou a do
  destino depois de o processo entrar na sua triagem.

TRÊS REGRAS QUE NÃO SE PODEM PERDER
  1. A entrada é **idempotente**: o primeiro registo ganha. Uma segunda
     partilha, ou a repetição da sincronização, não repõe a triagem de
     um processo que o Index já tratou;
  2. **Sem Index disponível não se bloqueia nem se inventa fila**: um
     destino sem indexadores não recebe fila (diz-se ao utilizador) e um
     destino com indexadores mas nenhum livre deixa o processo na fila
     sem indexador (o filtro «sem indexador» mostra-o);
  3. Tudo o que isto escreve deixa **rasto** (histórico + trilho) e
     **nunca** faz a partilha que o provocou falhar;

O CAMPO GRAVADO NO PROCESSO
  `hub_triage` (com `state`, `network_id`, `motivo`…) mantém o nome do
  Bloco A: já existe em produção, `rede_da_equipa` lê-o e renomeá-lo
  exigia uma migração para ganhar só um nome.
====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from database import db
from services.role_query import build_deep_role_query
from services.index_status import aplicar_ao_documento, estado_apos
from services.tenant_network import CAMPO_REDE, resolve_network_id

logger = logging.getLogger(__name__)

#: Registo da entrada do processo na triagem da rede de destino (nome do Bloco A).
CAMPO_TRIAGEM = "hub_triage"

#: A flag da excepção. Vive no PROCESSO (quem o partilha sabe se é urgente
#: ou se já vem triado) e é lida no momento da partilha.
CAMPO_VIA_VERDE = "via_verde"

ESTADO_EM_TRIAGEM = "triagem"
ESTADO_VIA_VERDE = "via_verde"

#: Como o processo ficou dispensado do Index da rede satélite.
MARCA_SEM_INDEX = "rede_sem_index"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ====================================================================
# QUEM TEM INDEX
# ====================================================================
async def redes_com_index() -> set[str]:
    """As redes com pelo menos um indexador activo. Vazio = não há Index.

    DERIVA da equipa real (o mesmo critério do pool de `assign_to_indexer`:
    utilizador activo com o perfil `indexacao`, membro da rede por UCR ou
    pela conta antiga). Falha FECHADA para o lado de «ninguém tem Index»:
    uma leitura que falha desliga a regra (comportamento anterior) em vez
    de a ligar a metade — e diz-se no log.
    """
    try:
        indexadores = await db.users.find(
            build_deep_role_query({"is_active": True}, role="indexacao"),
            {"_id": 0, "id": 1, "company": 1},
        ).to_list(5000)
        if not indexadores:
            return set()

        empresas = await db.companies.find(
            {}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
        ).to_list(1000)
        rede_de: dict[str, str] = {}
        for empresa in empresas:
            rede = resolve_network_id(empresa, company_id=empresa.get("id"))
            if not rede:
                continue
            for chave in (_texto(empresa.get("id")), _texto(empresa.get("name"))):
                if chave:
                    rede_de[chave] = rede

        ids = sorted({_texto(u.get("id")) for u in indexadores if _texto(u.get("id"))})
        ucrs = await db.user_company_roles.find(
            {"user_id": {"$in": ids}},
            {"_id": 0, "user_id": 1, "company_id": 1, "company_name": 1},
        ).to_list(10000)
    except Exception as exc:
        logger.warning("[INDEX] Falha a ler as redes com Index (%s); sem regra de Index.", exc)
        return set()

    redes: set[str] = set()
    for ucr in ucrs:
        for chave in (_texto(ucr.get("company_id")), _texto(ucr.get("company_name"))):
            if chave in rede_de:
                redes.add(rede_de[chave])
    for utilizador in indexadores:
        chave = _texto(utilizador.get("company"))
        if chave in rede_de:
            redes.add(rede_de[chave])
    return redes


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

    A de destino depois de o processo entrar na sua triagem (quem trabalha é
    essa equipa), senão a do dono. Vazio = processo por carimbar (sem restrição).
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
# O REGIME DA REDE SEM INDEX (escritor de processos)
# ====================================================================
async def rede_do_processo_sem_index(processo: Optional[dict]) -> bool:
    """O dono é uma rede SEM Index, havendo Index noutras redes?

    Um processo por carimbar NÃO é «sem Index»: sem saber de quem é, não
    se lhe tira o Index. Um processo já triado por outra rede também não
    (a equipa é a do destino).
    """
    processo = processo or {}
    rede = _texto(processo.get(CAMPO_REDE))
    if not rede or isinstance(processo.get(CAMPO_TRIAGEM), dict):
        return False
    com_index = await redes_com_index()
    return bool(com_index) and rede not in com_index


async def aplicar_regime_de_indexacao(process_doc: dict) -> bool:
    """Uma rede sem Index não passa pelo Index: o processo nasce dispensado dele.

    Chamada por TODOS os escritores de processos, depois de carimbar e
    antes de gravar (inventário por AST em
    `test_triagem_por_rede_de_destino.py` — um escritor novo que a esqueça
    falha). Devolve se escreveu. Nunca sobrescreve `skip_index` já ligado.
    """
    escreveu = False
    try:
        if await rede_do_processo_sem_index(process_doc):
            process_doc["skip_index"] = True
            process_doc["index_dispensado_por"] = MARCA_SEM_INDEX
            escreveu = True
    except Exception as exc:
        logger.warning(
            "[INDEX] Falha a decidir o regime de indexação (%s); o processo "
            "mantém o comportamento por omissão.", exc,
        )
    # Lote 12: o `index_status` nasce AQUI, de todos os caminhos (com `skip_index`
    # pedido pelo escritor, dispensado pela rede, ou normal). É o gancho que os
    # cinco escritores de processos já têm — um sexto a esquecê-lo falha o inventário.
    aplicar_ao_documento(process_doc)
    return escreveu


# ====================================================================
# A ENTRADA NA TRIAGEM DA REDE DE DESTINO (partilha)
# ====================================================================
def decidir_entrada(
    processo: dict,
    *,
    redes_de_destino: Iterable[str],
) -> Optional[dict]:
    """A decisão, PURA: o que fazer com um processo que acaba de ser
    partilhado com uma rede que tem Index. ``None`` = nada a fazer.

    * já tem registo de triagem → nada (idempotente, o primeiro ganha);
    * `via_verde` → registo ``via_verde``, o Index do destino é saltado;
    * já indexado → registo ``via_verde`` com motivo (nada a triar);
    * senão → registo ``triagem``, entra na fila do Index do destino.
    """
    destinos = [_texto(r) for r in redes_de_destino if _texto(r)]
    if not destinos:
        return None
    if isinstance(processo.get(CAMPO_TRIAGEM), dict):
        return None

    rede_destino = destinos[0]
    via_verde = processo.get(CAMPO_VIA_VERDE) is True
    ja_indexado = processo.get("is_indexed") is True

    if via_verde or ja_indexado:
        return {
            "state": ESTADO_VIA_VERDE,
            CAMPO_REDE: rede_destino,
            "motivo": "via_verde" if via_verde else "ja_indexado",
        }
    return {"state": ESTADO_EM_TRIAGEM, CAMPO_REDE: rede_destino, "motivo": "partilha"}


async def entrar_na_triagem_da_rede(
    process_id: str,
    novas: list[dict],
    *,
    por_ordem_de: Any = None,
) -> Optional[dict]:
    """Aplica a entrada na triagem da rede de destino a um processo partilhado.

    ``novas`` são as entradas que a partilha acabou de acrescentar. Só
    interessa a que seja uma rede COM Index. A partilha é sempre
    EXPLÍCITA («enviar para a rede X» é uma instrução): a partilha por
    atribuição (Via Rápida) foi extinta. Devolve o registo gravado, ou
    ``None`` quando não havia nada a fazer.
    """
    com_index = await redes_com_index()
    destinos = [
        _texto(n.get(CAMPO_REDE)) for n in novas if _texto(n.get(CAMPO_REDE)) in com_index
    ]
    if not destinos:
        return None

    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1, CAMPO_REDE: 1, CAMPO_TRIAGEM: 1,
         CAMPO_VIA_VERDE: 1, "is_indexed": 1, "skip_index": 1,
         "assigned_indexacao_id": 1},
    )
    if not processo:
        return None
    dono = _texto(processo.get(CAMPO_REDE))
    destinos = [d for d in destinos if d != dono]
    if not destinos:
        return None
    decisao = decidir_entrada(processo, redes_de_destino=destinos)
    if not decisao:
        return None

    registo = {
        **decisao,
        "entered_at": _agora(),
        "entered_by": _texto(por_ordem_de),
        "from_network": dono,
        "explicit": True,
    }
    atualizacao: dict[str, Any] = {CAMPO_TRIAGEM: registo, "updated_at": registo["entered_at"]}
    if decisao["state"] == ESTADO_EM_TRIAGEM:
        # A rede do dono dispensou o Index; o destino não. Sem isto os
        # ficheiros continuavam a entrar nas pastas finais e a IA nunca corria.
        atualizacao["skip_index"] = False
        atualizacao["index_dispensado_por"] = None
        atualizacao.update(estado_apos(processo, atualizacao))

    await db.processes.update_one({"id": process_id}, {"$set": atualizacao})

    if decisao["state"] == ESTADO_EM_TRIAGEM:
        await _atribuir_indexador_da_rede(process_id, decisao[CAMPO_REDE])
    else:
        # Via Verde: salta o Index, mas o processo não pode ficar sem ninguém. Quem
        # remete NUNCA escolhe o utilizador final — o destino distribui pelas suas
        # regras de auto-atribuição (consultor e intermediário menos ocupados DA REDE
        # DE DESTINO, que é a equipa do processo desde o registo acima).
        await _distribuir_na_rede_de_destino(process_id, por_ordem_de)

    await _deixar_rasto(process_id, processo, registo, por_ordem_de)
    return registo


async def entrar_na_triagem_da_rede_sem_falhar(
    process_id: str, novas: list[dict], *, por_ordem_de: Any = None,
) -> Optional[dict]:
    """Versão que a partilha chama: a partilha já está gravada, logo um
    erro aqui não pode fazer falhar o pedido. Falha **dita**, nunca calada."""
    try:
        return await entrar_na_triagem_da_rede(
            process_id, novas, por_ordem_de=por_ordem_de,
        )
    except Exception as exc:
        logger.warning(
            "[INDEX] Falha a pôr o processo %s na triagem da rede de destino "
            "(%s); a partilha mantém-se mas o Index pode não o ver na fila.",
            process_id, exc,
        )
        return None


async def _distribuir_na_rede_de_destino(process_id: str, por_ordem_de: Any) -> None:
    """Auto-atribui consultor + intermediário da rede de destino (Via Verde explícita).

    Só preenche o que está vazio (a regra da dupla auto-atribuição). Sem ninguém
    disponível não falha: o processo fica no pool do destino, visível à sua gestão,
    que atribui à mão.
    """
    try:
        from services.process_assignment import dual_auto_assign_on_pre_registo_transition

        await dual_auto_assign_on_pre_registo_transition(
            process_id, indexador_user_id=_texto(por_ordem_de) or None,
        )
    except Exception as exc:
        logger.warning(
            "[INDEX] Falha a distribuir o processo %s na rede de destino (%s); "
            "fica no pool do destino sem atribuição.", process_id, exc,
        )


async def _atribuir_indexador_da_rede(process_id: str, rede_destino: str) -> None:
    """Tenta dar o processo a um indexador da rede de destino. Sem
    indexador livre não falha: o processo fica na fila (filtro «sem indexador»)."""
    try:
        from services.process_assignment import assign_to_indexer

        sucesso, dados, msg = await assign_to_indexer(
            process_id, update_status=False, network_id=rede_destino,
        )
        if not (sucesso and dados.get("assigned")):
            logger.info(
                "[INDEX] Processo %s na fila de triagem sem indexador atribuído: %s",
                process_id, msg,
            )
        # o intermediário da rede de destino entra ao mesmo tempo (só se estiver vazio)
        from services.process_assignment import auto_assign_intermediario_on_entry

        await auto_assign_intermediario_on_entry(process_id)
    except Exception as exc:
        logger.warning(
            "[INDEX] Falha a atribuir indexador ao processo %s (%s); "
            "fica na fila sem indexador.", process_id, exc,
        )


async def _deixar_rasto(
    process_id: str, processo: dict, registo: dict, por_ordem_de: Any,
) -> None:
    """Histórico + trilho. **Nunca** propaga."""
    texto = (
        "Processo entrou na fila de triagem (Index) da rede de destino"
        if registo["state"] == ESTADO_EM_TRIAGEM
        else "Processo partilhado em Via Verde — salta o Index da rede de destino"
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
        logger.warning("[INDEX] Falha a registar no histórico de %s (%s).", process_id, exc)

    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id=process_id,
            user={"id": _texto(por_ordem_de)},
            action="hub_triage_entered",  # nome do Bloco A: mantém o histórico consultável
            field=CAMPO_TRIAGEM,
            new_value=registo["state"],
            source="web",
            metadata={
                "process_number": processo.get("process_number"),
                "rede_do_dono": processo.get(CAMPO_REDE),
                "rede_de_destino": registo.get(CAMPO_REDE),
                "motivo": registo.get("motivo"),
            },
        )
    except Exception as exc:
        logger.warning("[INDEX] Falha a registar no trilho de %s (%s).", process_id, exc)


__all__ = [
    "CAMPO_TRIAGEM",
    "CAMPO_VIA_VERDE",
    "ESTADO_EM_TRIAGEM",
    "ESTADO_VIA_VERDE",
    "aplicar_regime_de_indexacao",
    "decidir_entrada",
    "entrar_na_triagem_da_rede",
    "entrar_na_triagem_da_rede_sem_falhar",
    "rede_da_equipa",
    "rede_do_processo_sem_index",
    "redes_com_index",
    "restringir_a_equipa",
    "user_ids_da_rede",
]
