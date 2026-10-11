"""Partilha de um processo entre redes (D-25, Out 2026; Via Rápida extinta).

O PROBLEMA QUE ISTO RESOLVE
==========================
A topologia é «Power + Precision partilham; a Domus é uma ilha». O modelo
implementa-a com **um** `network_id` por documento: um processo pertence
a uma rede e só essa o vê. Mas passar trabalho a outra empresa é uma
operação NORMAL do negócio, e o modelo financeiro **já a conhecia**:
`db.process_finances` é chaveada por `(process_id, company_id)` — um
registo por empresa no mesmo processo, que é o rateio de uma partilha.
Era só a VISIBILIDADE que não tinha como o expressar.

O atalho de dar à pessoa um UCR nas duas empresas é o pior negócio
possível: o âmbito é do UTILIZADOR, logo um consultor da Precision com
acesso à Domus passa a ver **toda** a Domus, e não aquele processo.

O QUE A PARTILHA É, E O QUE NÃO É
=================================
* **Acrescenta quem VÊ, nunca muda de quem É.** `network_id` continua a
  ser o carimbo de propriedade e é permanente;
  `CAMPO_REDES_PARCEIRAS` é uma lista de convidados. A rede do DONO
  nunca entra na lista de convidados.
* **O âmbito é o PROCESSO, não a rede.** O convidado vê aquele processo
  (a ficha inteira), e a fronteira continua fechada em todos os outros.
* **Só EXPLÍCITA.** A «Via Rápida» — abrir o processo a uma rede por se
  atribuir lá uma pessoa — foi extinta (Out 2026): quem atribuía
  escolhia o utilizador final de outra rede e saltava a fila de triagem
  dela, e quem tinha UCRs em duas redes abria a segunda por acaso. Hoje a
  atribuição directa só alcança a própria rede
  (`assignment_network_guard`) e passar um processo a outra empresa é
  `partilhar_com_rede` («Partilhar com Empresa…»), que o põe na fila
  central do destino; a distribuição é das regras dessa rede. **Apagada,
  não desligada**: código adormecido atrás de uma condição é um convite a
  religá-lo (`sincronizar_parceiros` já não existe, e há um teste que o
  afirma).
* **A revogação é MANUAL** (decisão do dono do produto, 2026-10-09):
  o parceiro mantém o histórico e os documentos que ele próprio produziu
  e o registo de comissão continua coerente — revogar em automático fazia
  desaparecer trabalho real sem ninguém decidir. Quem retira é
  `revogar_parceiro`, à mão, e deixa rasto.
* **Visível e auditada.** A abertura de uma fronteira deixa entrada no
  trilho, no histórico do processo e na etiqueta da listagem.

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


class DestinoInvalido(Exception):
    """A rede de destino não serve (vazia, a do dono, ou sem empresas)."""


async def empresas_da_rede(network_id: str) -> list[dict]:
    """As empresas de uma rede, por nome. Vazio = a rede não existe."""
    from services.tenant_network import resolve_network_id

    rede = _texto(network_id)
    if not rede:
        return []
    empresas = await db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1, "is_active": 1},
    ).to_list(1000)
    return sorted(
        (
            e for e in empresas
            if e.get("is_active") is not False
            and resolve_network_id(e, company_id=e.get("id")) == rede
        ),
        key=lambda e: _texto(e.get("name")).lower(),
    )


async def partilhar_com_rede(
    process_id: str,
    network_id: str,
    *,
    via_verde: Optional[bool] = None,
    por_ordem_de: Any = None,
    registar_historico=None,
) -> dict:
    """Envia um processo para uma rede de destino ESCOLHIDA (multi-fornecedor).

    É a versão explícita da Via Rápida: a partilha por atribuição deduz o
    destino de quem foi atribuído; aqui o utilizador di-lo. Acrescenta a
    rede aos convidados (nunca muda o dono), e se o destino tem Index o
    processo entra na fila dessa rede — salvo `via_verde`, que o salta.

    `via_verde` é gravada no processo ANTES da triagem (a triagem lê-a do
    documento); `None` mantém o que lá está.

    Levanta `DestinoInvalido` para um destino que não serve. Devolve
    `{partilhado, ja_partilhado, rede, empresas, triagem, destino_tem_index}`.
    """
    from services.network_triage import (
        entrar_na_triagem_da_rede_sem_falhar,
        redes_com_index,
    )

    destino = _texto(network_id)
    if not destino:
        raise DestinoInvalido("Escolha a rede de destino.")

    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1, CAMPO_REDE: 1,
         CAMPO_REDES_PARCEIRAS: 1, CAMPO_EMPRESAS_PARCEIRAS: 1, "via_verde": 1},
    )
    if not processo:
        raise DestinoInvalido("Processo não encontrado.")
    if destino == _texto(processo.get(CAMPO_REDE)):
        raise DestinoInvalido("O processo já pertence a essa rede.")

    empresas = await empresas_da_rede(destino)
    if not empresas:
        raise DestinoInvalido("Rede de destino desconhecida.")

    if via_verde is not None and bool(via_verde) != (processo.get("via_verde") is True):
        await db.processes.update_one(
            {"id": process_id},
            {"$set": {"via_verde": bool(via_verde), "updated_at": _agora()}},
        )

    registo = parceiros_do_processo(processo)
    ja_partilhado = destino in redes_do_registo(registo)
    nova = {
        "company_id": _texto(empresas[0].get("id")),
        "company_name": " / ".join(_texto(e.get("name")) for e in empresas if _texto(e.get("name"))),
        CAMPO_REDE: destino,
        "added_at": _agora(),
        "added_by": _texto(por_ordem_de),
    }
    if not ja_partilhado:
        novo_registo = [*registo, nova]
        await db.processes.update_one(
            {"id": process_id},
            {"$set": {
                CAMPO_EMPRESAS_PARCEIRAS: novo_registo,
                CAMPO_REDES_PARCEIRAS: redes_do_registo(novo_registo),
            }},
        )
        await _deixar_rasto(
            process_id=process_id,
            processo=processo,
            novas=[nova],
            por_ordem_de=por_ordem_de,
            registar_historico=registar_historico,
        )

    com_index = await redes_com_index()
    triagem = await entrar_na_triagem_da_rede_sem_falhar(
        process_id, [nova], por_ordem_de=por_ordem_de,
    )
    return {
        "partilhado": not ja_partilhado,
        "ja_partilhado": ja_partilhado,
        "rede": destino,
        "empresas": [_texto(e.get("name")) for e in empresas],
        "destino_tem_index": destino in com_index,
        "triagem": triagem,
    }


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
    "DestinoInvalido",
    "empresas_da_rede",
    "partilhar_com_rede",
    "esta_partilhado",
    "etiquetas_da_partilha",
    "parceiros_do_processo",
    "redes_do_registo",
    "revogar_parceiro",
]
