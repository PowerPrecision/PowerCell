"""Partilha de um processo entre redes — a Via Rápida (D-25, Out 2026).

O PROBLEMA QUE ISTO RESOLVE
==========================
A topologia é «Power + Precision partilham; a Domus é uma ilha». O modelo
implementava-a com **um** `network_id` por documento: um processo
pertence a uma rede e só essa o vê. Mas a partilha entre agências é uma
operação NORMAL do negócio (a co-angariação), e o modelo financeiro **já
a conhecia**: `db.process_finances` é chaveada por
`(process_id, company_id)` — um registo por empresa no mesmo processo,
que é exactamente o rateio de comissão de uma partilha. Era só a
VISIBILIDADE que não tinha como o expressar.

O recurso disponível até aqui era dar à pessoa um UCR nas duas empresas —
e esse é o pior negócio possível: o âmbito é do UTILIZADOR, logo um
consultor da Precision com acesso à Domus passa a ver **toda** a Domus, e
não aquele processo.

O QUE A PARTILHA É, E O QUE NÃO É
=================================
* **Acrescenta quem VÊ, nunca muda de quem É.** `network_id` continua a
  ser o carimbo de propriedade e é permanente;
  `CAMPO_REDES_PARCEIRAS` é uma lista de convidados. A rede do DONO
  nunca entra na lista de convidados — seria redundante hoje e, no dia
  em que o dono mudasse, deixava lá uma chave da rede antiga.
* **O âmbito é o PROCESSO, não a rede.** O convidado vê aquele processo
  (decisão do dono do produto: «a ficha inteira»), e a fronteira
  continua fechada em todos os restantes. É esta a diferença entre isto
  e o atalho do UCR.
* **Via Rápida: nasce da ATRIBUIÇÃO**, sem aprovação manual. Foi a
  decisão do produto, e tem uma consequência que é preciso dizer: uma
  abertura de fronteira que ninguém aprovou tem de ser **visível e
  auditada**, senão é silenciosa — e uma abertura silenciosa é o oposto
  de tolerância zero. Daí a entrada no trilho, a entrada no histórico do
  processo e a etiqueta na listagem.
* **A revogação é MANUAL** (decisão do dono do produto, 2026-10-09).
  Tirar a atribuição **não** revoga: o parceiro mantém o histórico e os
  documentos que ele próprio produziu, e o registo de comissão continua
  coerente. Revogar em automático fazia desaparecer trabalho real sem
  ninguém decidir — e um documento que desaparece não produz erro
  nenhum. Por isso `sincronizar_parceiros` só **ACRESCENTA**; quem
  retira é `revogar_parceiro`, à mão, e deixa rasto.

PORQUE É QUE A SINCRONIZAÇÃO DERIVA DO DOCUMENTO E NÃO DO DIFF
==============================================================
Há CINCO escritores de atribuições neste projecto, e a lição do Lote 5
(repetida no Lote 7, no ponto 9 e na contagem por campo que encontrou o
quinto) é sempre a mesma: **a regra aplicada aos construtores e não a
quem os usa divergiu em todos eles**. `sincronizar_parceiros` lê o
documento JÁ GRAVADO, resolve as redes de **todos** os atribuídos e
acrescenta as que faltam. É idempotente, não depende de nenhum diff, e
um escritor novo que se esqueça de a chamar é um bug de UM sítio e não
de cinco.

As DUAS listas derivam uma da outra
-----------------------------------
`partner_companies` é o REGISTO (quem, quando, por ordem de quem) e é o
que a etiqueta mostra; `partner_network_ids` é a lista indexável que a
condição Mongo lê, e **deriva** do registo em cada escrita. Duas fontes
de verdade para a mesma coisa divergem sem dar erro — e aqui a que
divergisse ou abria uma rede a mais, ou escondia um processo a quem o
está a trabalhar.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from database import db
from services.task_assignment_hygiene import ids_atribuidos_do_processo
from services.tenant_network import CAMPO_REDE, CAMPO_REDES_PARCEIRAS

logger = logging.getLogger(__name__)

#: O registo da partilha: uma entrada por empresa convidada.
CAMPO_EMPRESAS_PARCEIRAS = "partner_companies"

#: Campos de uma entrada do registo. `added_by` é o id de quem fez a
#: atribuição que abriu a partilha — a Via Rápida não tem aprovação, logo
#: o nome de quem a provocou é a única responsabilização que existe.
CAMPOS_DO_PARCEIRO = (
    "company_id",
    "company_name",
    "network_id",
    "added_at",
    "added_by",
)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def parceiros_do_processo(processo: Optional[dict]) -> list[dict]:
    """O registo de parceiros, sempre uma lista de dicionários.

    Um valor do tipo errado degrada para lista vazia **com aviso** — é a
    regra do `pasta_gravada` (um `or []` não protege de um tipo errado,
    só muda o sítio onde rebenta) e aqui o degradado certo é «sem
    partilha», que é o estado seguro.
    """
    valor = (processo or {}).get(CAMPO_EMPRESAS_PARCEIRAS)
    if valor in (None, "", []):
        return []
    if not isinstance(valor, (list, tuple)):
        logger.warning(
            "[PARTILHA] `%s` do processo %s está gravado como %s; tratado "
            "como SEM partilha.",
            CAMPO_EMPRESAS_PARCEIRAS, (processo or {}).get("id"),
            type(valor).__name__,
        )
        return []
    return [entrada for entrada in valor if isinstance(entrada, dict)]


def redes_do_registo(parceiros: Iterable[dict]) -> list[str]:
    """A lista indexável, DERIVADA do registo.

    Nunca escrita à mão: é esta derivação que impede as duas listas de
    divergirem, e há um teste a afirmá-lo sobre o documento gravado.
    """
    vistas: list[str] = []
    for entrada in parceiros or []:
        rede = _texto((entrada or {}).get(CAMPO_REDE))
        if rede and rede not in vistas:
            vistas.append(rede)
    return vistas


def etiquetas_da_partilha(processo: Optional[dict]) -> list[str]:
    """Os nomes das empresas convidadas, para a etiqueta do ecrã.

    O NOME e não o id: a etiqueta é `[Partilha: Precision]` e quem a lê
    é uma pessoa. Uma entrada sem nome cai para o id — mostrar um uuid é
    pior do que mostrar nada, mas **esconder** a partilha é muito pior,
    porque é a única coisa que torna a Via Rápida visível.
    """
    nomes: list[str] = []
    for entrada in parceiros_do_processo(processo):
        nome = _texto(entrada.get("company_name")) or _texto(entrada.get("company_id"))
        if nome and nome not in nomes:
            nomes.append(nome)
    return nomes


def esta_partilhado(processo: Optional[dict]) -> bool:
    """Tem pelo menos uma rede convidada?

    Lê a lista DERIVADA (`partner_network_ids`) e não o registo: é a
    lista que a condição Mongo usa, logo é ela que define se o processo
    está, de facto, visível a outra rede. Se as duas divergirem, a
    resposta honesta é a que tem efeito.
    """
    valor = (processo or {}).get(CAMPO_REDES_PARCEIRAS)
    if isinstance(valor, (list, tuple, set)):
        return any(_texto(v) for v in valor)
    return bool(_texto(valor))


# ====================================================================
# PROJECÇÃO E SERIALIZAÇÃO — os dois ecrãs têm de mostrar o mesmo
# ====================================================================

#: Os campos que a LISTAGEM e o KANBAN precisam para desenhar a etiqueta.
#: Ponto único, como o `PROJECCAO` do `sub35`: se o Kanban projectar e a
#: listagem não, a mesma linha tem etiqueta num ecrã e não tem no outro.
PROJECCAO = {
    CAMPO_EMPRESAS_PARCEIRAS: 1,
    CAMPO_REDES_PARCEIRAS: 1,
}

#: Os campos que a UI lê. Calculados ao SERIALIZAR e nunca persistidos —
#: um booleano gravado fica errado no dia em que a partilha é revogada,
#: que é a regra que o `sub35` já paga.
CAMPO_DA_FLAG = "is_partilhado"
CAMPO_DAS_ETIQUETAS = "partilha_com"


def aplicar_flag_a_processos(processos: Optional[list]) -> None:
    """Escreve `is_partilhado` e `partilha_com` em cada processo.

    Ponto único de serialização: as listagens e o Kanban chamam isto em
    vez de cada uma calcular a sua — duas respostas à mesma pergunta
    divergem, e a que divergir mostra a etiqueta num ecrã e não no
    outro.
    """
    for processo in processos or []:
        if not isinstance(processo, dict):
            continue
        processo[CAMPO_DA_FLAG] = esta_partilhado(processo)
        processo[CAMPO_DAS_ETIQUETAS] = etiquetas_da_partilha(processo)


# ====================================================================
# O FILTRO RÁPIDO: «Exclusivos da Casa» vs «Partilhados»
# ====================================================================

#: Os dois valores que o filtro aceita. Em pt-PT e iguais ao que o ecrã
#: mostra: um terceiro nome para a mesma coisa é como o `under_35`
#: apareceu em quatro sítios com quatro significados.
FILTRO_EXCLUSIVOS = "exclusivos"
FILTRO_PARTILHADOS = "partilhados"
VALORES_DO_FILTRO = (FILTRO_EXCLUSIVOS, FILTRO_PARTILHADOS)


def condicao_de_filtro(partilha: Optional[str]) -> Optional[dict]:
    """Condição Mongo do filtro rápido, ou ``None`` para «não filtrar».

    PONTO ÚNICO, como o `sub35.condicao_de_filtro`: entra nos DOIS
    construtores de query (a listagem e o Kanban, que tem o seu) e no
    endpoint dos vizinhos — senão a seta da fronteira da página leva a um
    processo que a lista filtrada não contém.

    `{campo: {"$in": [None, []]}}` casa com **ausente**, `null` **e**
    array vazio; o `$nin` com a mesma lista é o complemento exacto,
    incluindo a exclusão dos documentos sem o campo (é o `None` na lista
    que o faz — sem ele, o `$nin` casaria com os ausentes e «Partilhados»
    mostrava a carteira inteira). Verificado contra um `mongod` real,
    porque a semântica de `$in`/`$nin` sobre um campo que contém um ARRAY
    é precisamente onde este projecto já se enganou (a consulta do
    `fix_s3_folder_anomalies`).

    Um valor desconhecido **não filtra** em vez de devolver uma condição
    impossível: um parâmetro escrito à mão no URL não pode esvaziar a
    listagem sem dizer porquê.
    """
    valor = _texto(partilha).lower()
    if valor == FILTRO_EXCLUSIVOS:
        return {CAMPO_REDES_PARCEIRAS: {"$in": [None, []]}}
    if valor == FILTRO_PARTILHADOS:
        return {CAMPO_REDES_PARCEIRAS: {"$nin": [None, []]}}
    if valor:
        logger.warning(
            "[PARTILHA] Filtro de partilha desconhecido (%r); ignorado. "
            "Valores: %s", partilha, list(VALORES_DO_FILTRO),
        )
    return None


async def _associacoes_dos_atribuidos(ids: Iterable[str]) -> dict[str, list[dict]]:
    """Mapa user_id → associações (UCRs). Uma leitura por utilizador."""
    from services.auth import get_user_companies

    mapa: dict[str, list[dict]] = {}
    for uid in sorted({_texto(i) for i in ids if _texto(i)}):
        try:
            mapa[uid] = await get_user_companies(uid) or []
        except Exception as exc:
            logger.warning(
                "[PARTILHA] Falha a ler as empresas de %s (%s); a partilha "
                "não é aberta por causa dele.", uid, exc,
            )
            mapa[uid] = []
    return mapa


async def _redes_das_empresas(chaves: Iterable[str]) -> dict[str, str]:
    """Mapa chave de empresa (id OU nome) → rede.

    DERIVA do `tenant_network`: a rede de uma empresa sem grupo
    configurado é a ilha implícita, e é a mesma função que o
    `resolve_tenant_scope` usa — uma segunda regra aqui divergiria, e a
    que divergisse abria ou fechava a rede errada.
    """
    from services.tenant_network import resolve_network_id

    identificadores = sorted({_texto(c) for c in chaves if _texto(c)})
    if not identificadores:
        return {}

    encontradas: dict[str, dict] = {}
    try:
        cursor = db.companies.find(
            {"$or": [
                {"id": {"$in": identificadores}},
                {"name": {"$in": identificadores}},
            ]},
            {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
        )
        for empresa in await cursor.to_list(200):
            for chave in (_texto(empresa.get("id")), _texto(empresa.get("name"))):
                if chave:
                    encontradas[chave] = empresa
    except Exception as exc:
        logger.warning(
            "[PARTILHA] Falha a ler `companies` (%s); sem redes resolvidas "
            "não se abre partilha nenhuma.", exc,
        )
        return {}

    return {
        chave: resolve_network_id(encontradas.get(chave), company_id=chave) or ""
        for chave in identificadores
    }


async def calcular_parceiros_a_acrescentar(
    processo: dict,
    *,
    por_ordem_de: Any = None,
) -> list[dict]:
    """Que empresas convidadas faltam no registo deste processo.

    PURA em relação à escrita: lê, resolve e devolve — não grava. É o que
    permite ao teste medir a decisão sem medir o `update_one`.

    A EMPRESA DA ETIQUETA É A DA REDE, NÃO A POR OMISSÃO
    ----------------------------------------------------
    A primeira versão resolvia a empresa pela associação **por omissão**
    do utilizador. Para quem trabalha em duas redes — a Carla do cenário
    de testes, que é o caso real deste grupo — abria a rede da Domus e
    escrevia na etiqueta «Precision Crédito»: a partilha ficava rotulada
    com a empresa errada. Uma etiqueta que mente sobre quem passou a ver
    o processo é pior do que etiqueta nenhuma, porque é ela a única
    coisa que torna a Via Rápida visível. Hoje percorre-se
    (utilizador × EMPRESA) e a rede sai da empresa.

    **NÃO usa o `resolve_tenant_scope`**, de propósito: aquele atribui a
    rede de OMISSÃO a um utilizador órfão de empresa (para não cegar
    contas de administração antigas). Aqui isso seria abrir o processo ao
    grupo incumbente por não se saber a empresa de alguém — falha
    ABERTA, no sítio exactamente errado. Sem associações, sem partilha.
    """
    rede_do_dono = _texto(processo.get(CAMPO_REDE))
    ja_convidadas = set(redes_do_registo(parceiros_do_processo(processo)))

    atribuidos = sorted(ids_atribuidos_do_processo(processo))
    if not atribuidos:
        return []

    associacoes = await _associacoes_dos_atribuidos(atribuidos)

    chaves = [
        _texto(a.get("company_id")) or _texto(a.get("company_name"))
        for lista in associacoes.values()
        for a in lista
    ]
    redes_por_empresa = await _redes_das_empresas(chaves)

    novas: list[dict] = []
    vistas = set(ja_convidadas)
    for uid in atribuidos:
        for assoc in associacoes.get(uid) or []:
            cid = _texto(assoc.get("company_id"))
            nome = _texto(assoc.get("company_name"))
            rede = _texto(redes_por_empresa.get(cid) or redes_por_empresa.get(nome))

            if not rede or rede == rede_do_dono or rede in vistas:
                continue
            vistas.add(rede)

            novas.append({
                "company_id": cid,
                "company_name": nome,
                CAMPO_REDE: rede,
                "added_at": _agora(),
                "added_by": _texto(por_ordem_de),
            })

    return novas


async def sincronizar_parceiros(
    process_id: str,
    *,
    por_ordem_de: Any = None,
    registar_historico=None,
) -> list[dict]:
    """Abre a partilha para as redes dos atribuídos que faltem.

    **Só acrescenta.** A revogação é manual (`revogar_parceiro`), por
    decisão de produto: tirar a atribuição não pode fazer desaparecer o
    histórico e os documentos que o parceiro produziu.

    Lê o documento JÁ GRAVADO: é isso que a torna idempotente e
    independente de qualquer diff, e é o que impede os cinco escritores
    de atribuições de divergirem (a lição do Lote 5).

    Devolve as entradas acrescentadas — vazio quando não há nada a fazer,
    que é o caso normal (a atribuição dentro da própria rede).
    """
    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1, CAMPO_REDE: 1,
         CAMPO_REDES_PARCEIRAS: 1, CAMPO_EMPRESAS_PARCEIRAS: 1,
         "assigned_consultor_ids": 1, "assigned_consultor_id": 1,
         "consultor_id": 1, "consultant_id": 1,
         "assigned_mediador_ids": 1, "assigned_mediador_id": 1,
         "mediador_id": 1, "assigned_indexacao_id": 1},
    )
    if not processo:
        return []

    novas = await calcular_parceiros_a_acrescentar(
        processo, por_ordem_de=por_ordem_de
    )
    if not novas:
        return []

    registo = [*parceiros_do_processo(processo), *novas]
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            CAMPO_EMPRESAS_PARCEIRAS: registo,
            # DERIVA do registo, sempre. Escrever as duas listas à mão
            # era garantir que uma delas divergia.
            CAMPO_REDES_PARCEIRAS: redes_do_registo(registo),
        }},
    )

    nomes = [n.get("company_name") or n.get(CAMPO_REDE) for n in novas]
    logger.info(
        "[PARTILHA] Processo %s partilhado com %s (por ordem de %s).",
        process_id, nomes, por_ordem_de or "?",
    )

    # VISÍVEL E AUDITADA: a Via Rápida não tem aprovação, logo o rasto é
    # a única responsabilização. Nunca faz a operação falhar — observa,
    # não intercepta (regra do `job_heartbeat`).
    await _deixar_rasto(
        process_id=process_id,
        processo=processo,
        novas=novas,
        por_ordem_de=por_ordem_de,
        registar_historico=registar_historico,
    )
    return novas


async def sincronizar_parceiros_sem_falhar(
    process_id: str,
    *,
    por_ordem_de: Any = None,
    registar_historico=None,
) -> list[dict]:
    """O que os ESCRITORES de atribuições chamam.

    Uma partilha que rebenta não pode fazer falhar a atribuição: a
    atribuição é a acção do utilizador e **já está gravada** quando isto
    corre, logo propagar daria um 500 por uma operação que teve sucesso,
    e deixava o estado a meio.

    Falhar aqui é falhar FECHADO (o parceiro não ganha visibilidade), que
    é o sentido seguro — e a sincronização é idempotente, pelo que a
    acção de atribuição seguinte repara. Mas **nunca em silêncio**: o
    `warning` nomeia o processo, é a regra do `_emit_event_safe` (uma
    excepção neste ponto é sempre inesperada e não pode ficar invisível).

    A versão ESTRITA fica para os testes: é ela que mede a decisão, e
    embrulhar tudo numa só função escondia um defeito meu atrás do
    mesmo `except` que protege a produção.
    """
    try:
        return await sincronizar_parceiros(
            process_id,
            por_ordem_de=por_ordem_de,
            registar_historico=registar_historico,
        )
    except Exception as exc:
        logger.warning(
            "[PARTILHA] Falha a sincronizar os parceiros do processo %s "
            "(%s); a atribuição mantém-se e a partilha NÃO foi aberta.",
            process_id, exc,
        )
        return []


async def revogar_parceiro(
    process_id: str,
    *,
    company_id: Any = None,
    network_id: Any = None,
    por_ordem_de: Any = None,
    registar_historico=None,
    auditar: bool = True,
) -> list[dict]:
    """Retira UMA empresa convidada. Operação deliberadamente MANUAL.

    Identifica-se por `company_id` **ou** por `network_id`: a etiqueta
    mostra a empresa, e é por ela que uma pessoa a reconhece; a rede é o
    que tem efeito. Sem nenhum dos dois não se faz nada — «revogar tudo»
    não é uma operação que se ofereça por omissão.

    `auditar=False` é para o actor que não pode deixar rasto (o perfil
    `indexacao`, de base ou em exercício): a revogação faz-se, o registo
    não se escreve.

    Devolve as entradas retiradas.
    """
    alvo_empresa = _texto(company_id)
    alvo_rede = _texto(network_id)
    if not alvo_empresa and not alvo_rede:
        return []

    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1,
         CAMPO_EMPRESAS_PARCEIRAS: 1, CAMPO_REDES_PARCEIRAS: 1},
    )
    if not processo:
        return []

    registo = parceiros_do_processo(processo)

    def _e_o_alvo(entrada: dict) -> bool:
        if alvo_empresa and _texto(entrada.get("company_id")) == alvo_empresa:
            return True
        return bool(alvo_rede) and _texto(entrada.get(CAMPO_REDE)) == alvo_rede

    retiradas = [e for e in registo if _e_o_alvo(e)]
    if not retiradas:
        return []

    sobram = [e for e in registo if not _e_o_alvo(e)]
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            CAMPO_EMPRESAS_PARCEIRAS: sobram,
            CAMPO_REDES_PARCEIRAS: redes_do_registo(sobram),
        }},
    )

    logger.info(
        "[PARTILHA] Processo %s: partilha revogada para %s (por ordem de %s).",
        process_id,
        [r.get("company_name") or r.get(CAMPO_REDE) for r in retiradas],
        por_ordem_de or "?",
    )
    await _deixar_rasto(
        process_id=process_id,
        processo=processo,
        novas=retiradas,
        por_ordem_de=por_ordem_de,
        registar_historico=registar_historico,
        acao="process_share_revoked",
        auditar=auditar,
    )
    return retiradas


class _SemAuditoria(Exception):
    """Sinal interno: o actor não pode deixar rasto de auditoria."""


async def _deixar_rasto(
    *,
    process_id: str,
    processo: dict,
    novas: list[dict],
    por_ordem_de: Any,
    registar_historico=None,
    acao: str = "process_shared",
    auditar: bool = True,
) -> None:
    """Trilho de auditoria + histórico do processo. **Nunca** propaga.

    O trilho e não só o `db.history`: isto move uma fronteira de
    visibilidade, que é a mesma natureza da eliminação de um cliente
    (D-16). O papel vai em `metadata` porque o campo partilhado guarda o
    do JWT e quem autoriza é o EFECTIVO.
    """
    detalhe = [
        {
            "company_id": n.get("company_id"),
            "company_name": n.get("company_name"),
            CAMPO_REDE: n.get(CAMPO_REDE),
        }
        for n in novas
    ]
    try:
        if not auditar:
            raise _SemAuditoria()
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id=process_id,
            user={"id": _texto(por_ordem_de)},
            action=acao,
            field=CAMPO_EMPRESAS_PARCEIRAS,
            new_value=[d.get("company_name") or d.get(CAMPO_REDE) for d in detalhe],
            source="web",
            metadata={
                "process_number": processo.get("process_number"),
                "rede_do_dono": processo.get(CAMPO_REDE),
                "parceiros": detalhe,
            },
        )
    except _SemAuditoria:
        pass
    except Exception as exc:
        logger.warning(
            "[PARTILHA] Falha a registar a partilha de %s no trilho (%s).",
            process_id, exc,
        )

    if registar_historico is None:
        return
    nomes = ", ".join(
        n.get("company_name") or n.get(CAMPO_REDE) or "?" for n in novas
    ) or "?"
    texto = (
        f"Processo partilhado com {nomes}"
        if acao == "process_shared"
        else f"Partilha revogada para {nomes}"
    )
    try:
        await registar_historico(texto)
    except Exception as exc:
        logger.warning(
            "[PARTILHA] Falha a registar a partilha de %s no histórico (%s).",
            process_id, exc,
        )


__all__ = [
    "CAMPOS_DO_PARCEIRO",
    "CAMPO_DAS_ETIQUETAS",
    "CAMPO_DA_FLAG",
    "PROJECCAO",
    "aplicar_flag_a_processos",
    "FILTRO_EXCLUSIVOS",
    "FILTRO_PARTILHADOS",
    "VALORES_DO_FILTRO",
    "condicao_de_filtro",
    "CAMPO_EMPRESAS_PARCEIRAS",
    "calcular_parceiros_a_acrescentar",
    "esta_partilhado",
    "etiquetas_da_partilha",
    "parceiros_do_processo",
    "redes_do_registo",
    "revogar_parceiro",
    "sincronizar_parceiros",
    "sincronizar_parceiros_sem_falhar",
]
