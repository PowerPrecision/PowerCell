"""Estado de indexação de um processo — `index_status` (Lote 12, Fase 1).

PONTO ÚNICO DE ESCRITA. Até aqui «indexado?» era `is_indexed` (booleano), mais
`skip_index` (Via Verde / rede sem Index) e `hub_triage.state` (a fila), lidos por
~10 módulos. O módulo Index precisa de um estado com três valores (`pending`,
`in_review`, `indexed`); em vez de mudar os leitores, `is_indexed` fica
**derivado** e gravado no mesmo `$set`.

::

    pending ──o indexador atribuído começa a trabalhar──▶ in_review ──mark-indexed──▶ indexed
       ▲                                                                      │
       └──────────────────────── set-indexed OFF ─────────────────────────────┘

Estar ATRIBUÍDO não é estar «em tratamento» (Out 2026): a atribuição é automática e o processo
continua `pending` até a pessoa lhe mexer (`registar_trabalho`). É essa diferença que permite ao SLA do
Index (`index_sla`) distinguir o processo intocado (reatribui-se) do estagnado (só se avisa). Já não há
«reivindicar» nem «devolver à fila»: o puxar manual deu lugar à atribuição automática.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Um só escritor.** Quem muda o estado chama uma função daqui; um `$set`
   à mão de `index_status` ou `is_indexed` (fora de `process_indexing`, que
   delega) é um desvio — há guarda por AST.
2. **`skip_index` ⇒ `indexed` + `index_skipped=True`, mas `is_indexed` NÃO
   muda.** O desenho inicial dizia `is_indexed = (index_status == "indexed")`.
   Aplicado aos processos dispensados (Via Verde, rede sem Index) viraria
   `is_indexed` para `True` em todos eles e mudava, sem erro nenhum, o que as
   listas de «por indexar», o filtro `is_indexed` e a fila do indexador
   devolvem. `is_indexed` só é verdadeiro quando uma PESSOA indexou
   (`document_intake` já trata `skip_index` à parte; o estado novo diz o mesmo).
3. **O estado é DERIVADO do documento** (`derivar_estado`), nunca de um diff:
   os escritores de `skip_index` são vários (criação, edição, triagem B2B) e a
   regra aplicada só ao construtor e não a quem o usa divergiu neste projecto
   cinco vezes. `estado_apos(doc, alteracoes)` calcula o `$set` a partir do
   documento já com a alteração.
4. **Legado sem `index_status` lê-se como a derivação dá** (`condicao_da_fila`
   tolera o campo ausente): a migração é conveniência, não pré-requisito do
   deploy — um processo não migrado não pode desaparecer da fila.
5. Datas em ISO-8601 (texto), como o resto de `processes`.

Nada aqui é pessoal: estado e contadores. Os metadados profissionais vivem
numa colecção própria (`process_professional_metadata`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from database import db

logger = logging.getLogger(__name__)

PENDING = "pending"
IN_REVIEW = "in_review"
INDEXED = "indexed"

ESTADOS = (PENDING, IN_REVIEW, INDEXED)
EstadoDeIndexacao = Literal["pending", "in_review", "indexed"]

#: Estados em que o processo ainda está na fila do Index (dashboard «Fila de Espera»).
ESTADOS_NA_FILA = (PENDING, IN_REVIEW)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _e_verdadeiro(valor: Any) -> bool:
    """`True` estrito: `"false"`, `1` e `"x"` não são a flag ligada."""
    return valor is True


def derivar_estado(doc: dict) -> dict[str, Any]:
    """Estado de indexação que o documento DIZ (função pura; ponto único da regra).

    * `skip_index` ligado (Via Verde / rede sem Index) e ninguém indexou
      → `indexed` dispensado (`index_skipped=True`);
    * `is_indexed` ligado → `indexed`;
    * o estado `in_review` JÁ gravado (alguém começou a trabalhar) mantém-se;
    * o resto → `pending` — **inclui o processo atribuído a um indexador que ainda não lhe mexeu**.

    Devolve `{"index_status", "index_skipped"}`; nunca levanta.
    """
    if not isinstance(doc, dict):
        return {"index_status": PENDING, "index_skipped": False}
    if _e_verdadeiro(doc.get("is_indexed")):
        return {"index_status": INDEXED, "index_skipped": False}
    if _e_verdadeiro(doc.get("skip_index")):
        return {"index_status": INDEXED, "index_skipped": True}
    # `in_review` só se o estado JÁ gravado o diz: foi `registar_trabalho` que o escreveu. Antes deste
    # lote um indexador atribuído bastava — e com a atribuição automática TODO o processo nascia «em
    # tratamento», o que apagava a diferença entre «ninguém lhe pegou» e «alguém está a trabalhar».
    if doc.get("index_status") == IN_REVIEW:
        return {"index_status": IN_REVIEW, "index_skipped": False}
    return {"index_status": PENDING, "index_skipped": False}


def estado_apos(doc_atual: dict, alteracoes: dict) -> dict[str, Any]:
    """`$set` de estado para um documento a que se vão aplicar `alteracoes`.

    É a função dos escritores de `skip_index`/`is_indexed`: o estado nasce do
    documento RESULTANTE (`{**atual, **alteracoes}`), não do que mudou.
    Devolve apenas os campos de estado (o chamador junta-os ao seu `$set`).
    """
    # `derivar_estado` só lê um `index_status` guardado para `in_review` (conveniência
    # do dashboard), nunca para `indexed`: um `indexed` herdado do documento não
    # sobrevive a desligar `is_indexed` (há teste).
    return derivar_estado({**(doc_atual or {}), **(alteracoes or {})})


def aplicar_ao_documento(doc: dict) -> dict:
    """Escreve `index_status`/`index_skipped` NUM documento novo (criação de processos).

    Chamada pelos escritores de processos DEPOIS de decidirem `skip_index`
    (`aplicar_regime_de_indexacao` incluída). Devolve o próprio documento.
    """
    doc.update(derivar_estado(doc))
    return doc


def campos_ao_indexar(user: dict, now: str) -> dict[str, Any]:
    """`$set` de «marcar como indexado» (pessoa a indexar): o estado e a assinatura."""
    return {
        "index_status": INDEXED,
        "index_skipped": False,
        "is_indexed": True,
        "indexed_at": now,
        "indexed_by": (user or {}).get("id"),
        "indexed_by_name": (user or {}).get("name", ""),
    }


def campos_ao_reverter(doc_atual: dict, user: dict, now: str) -> dict[str, Any]:
    """`$set` de «desligar indexado»: volta à fila (ou continua dispensado se `skip_index`)."""
    estado = estado_apos(doc_atual, {"is_indexed": False})
    return {
        **estado,
        "is_indexed": False,
        "unindexed_at": now,
        "unindexed_by": (user or {}).get("id"),
        "unindexed_by_name": (user or {}).get("name", ""),
    }


# ====================================================================
# A FILA (condições Mongo)
# ====================================================================
def condicao_da_fila(aba: str) -> dict:
    """Condição Mongo das duas abas do dashboard, tolerante a documentos sem `index_status`.

    * `pending` — «Fila de Espera»: ainda não indexado e não dispensado;
    * `reviews` — «Revisões Pendentes»: indexado por uma pessoa com campos a rever.

    Aba desconhecida → condição IMPOSSÍVEL (nunca `{}`, que seria «tudo»).
    """
    if aba == "pending":
        return {
            "$and": [
                {"is_indexed": {"$ne": True}},
                {"skip_index": {"$ne": True}},
                {
                    "$or": [
                        {"index_status": {"$in": list(ESTADOS_NA_FILA)}},
                        {"index_status": {"$exists": False}},
                    ]
                },
            ]
        }
    if aba == "reviews":
        return {"is_indexed": True, "has_pending_review": True}
    return {"id": {"$in": []}}


# ====================================================================
# TRABALHO EM CURSO (pending → in_review, automático)
# ====================================================================
async def assumir(process_id: str, anterior: Optional[str], novo: dict) -> bool:
    """«Atribuir a mim» (Out 2026): passa o processo ao indexador `novo` SÓ se o dono e o estado são os lidos.

    Condicional a `anterior` (ou a nenhum) e a ninguém ter começado (`in_review`, indexado, Via Verde):
    se o colega abrir a bancada entretanto, ganha quem trabalha (`False`). O relógio das 48 h recomeça.
    """
    agora = _agora()
    r = await db.processes.update_one(
        {
            "id": process_id, "is_deleted": {"$ne": True}, "is_indexed": {"$ne": True}, "skip_index": {"$ne": True},
            "index_status": {"$ne": IN_REVIEW},
            "assigned_indexacao_id": anterior if anterior else {"$in": [None, ""]},
        },
        {"$set": {
            "assigned_indexacao_id": novo.get("id"), "indexacao_name": novo.get("name"),
            "index_assigned_at": agora, "updated_at": agora,
        }},
    )
    return bool(r.modified_count)


async def registar_trabalho(process_id: str, user_id: Optional[str]) -> dict[str, Any]:
    """O indexador ATRIBUÍDO trabalhou no processo: arranca o tratamento e carimba a actividade.

    * `pending → in_review` (a primeira vez): grava `index_work_started_at`;
    * em qualquer caso carimba `index_last_activity_at` — é o relógio da estagnação (SLA nível 2).

    **Só conta o indexador atribuído**: um diretor a espreitar a bancada não começa o tratamento nem
    adia o alarme de um processo parado. Idempotente, atómico (um só `update_one` por passo, com o filtro
    a fazer de guarda) e nunca levanta — observa, não intercepta: falhar a carimbar não pode travar o trabalho.
    Devolve `{"iniciado": bool, "registado": bool}`.
    """
    if not user_id:
        return {"iniciado": False, "registado": False}
    agora = _agora()
    base = {
        "id": process_id,
        "is_deleted": {"$ne": True},
        "is_indexed": {"$ne": True},
        "skip_index": {"$ne": True},
        "assigned_indexacao_id": user_id,
    }
    try:
        arranque = await db.processes.update_one(
            {**base, "index_status": {"$ne": IN_REVIEW}},
            {"$set": {
                "index_status": IN_REVIEW, "index_skipped": False, "index_work_started_at": agora,
                "index_last_activity_at": agora, "updated_at": agora,
            }, "$unset": {"index_stagnation_alerted_at": ""}},
        )
        if arranque.modified_count:
            return {"iniciado": True, "registado": True}
        actividade = await db.processes.update_one(
            {**base, "index_status": IN_REVIEW},
            # voltar a mexer apaga a marca de estagnação: se parar outra vez, o alerta novo não espera pelo lembrete
            {"$set": {"index_last_activity_at": agora}, "$unset": {"index_stagnation_alerted_at": ""}},
        )
        return {"iniciado": False, "registado": bool(actividade.modified_count)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Actividade do processo %s não registada: %s", process_id, type(exc).__name__)
        return {"iniciado": False, "registado": False}


# ====================================================================
# CONTADORES (denormalizados para as duas abas)
# ====================================================================
async def gravar_contadores(
    process_id: str,
    *,
    has_pending_review: Optional[bool] = None,
    index_alerts_open: Optional[int] = None,
) -> None:
    """Actualiza os contadores denormalizados do processo. Nunca levanta (observa, não intercepta)."""
    campos: dict[str, Any] = {}
    if has_pending_review is not None:
        campos["has_pending_review"] = bool(has_pending_review)
    if index_alerts_open is not None:
        campos["index_alerts_open"] = max(0, int(index_alerts_open))
    if not campos:
        return
    try:
        await db.processes.update_one({"id": process_id}, {"$set": campos})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Contadores do processo %s não gravados: %s", process_id, exc)
