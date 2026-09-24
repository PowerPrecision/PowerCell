"""
====================================================================
HIGIENE DAS ATRIBUIÇÕES DE TAREFAS
====================================================================
Lote 4, ponto 12 — "Atribuição Fantasma".

DOIS PROBLEMAS DISTINTOS, COM A MESMA CARA

  1. UMA FORMA SÓ PARA `assigned_to`. O `workflow_engine` gravava o valor
     cru resolvido do processo — um ESCALAR (`assigned_consultor_id`) ou
     `None` — enquanto `task_api_crud` e `process_assignment` gravam uma
     LISTA. O `enrich_task` faz `{"id": {"$in": task["assigned_to"]}}` e o
     Mongo responde `$in needs an array`; como a listagem enriquece num
     ciclo sem `try`, UMA tarefa de automação fazia a lista INTEIRA
     devolver 500. `normalizar_assigned_to` desarma isso à leitura, e o
     motor de automação passou a gravar lista — normalizar trata o que já
     existe, deixar de produzir impede que volte.

  2. TAREFAS ÓRFÃS. `_create_post_indexing_tasks` cria tarefas de arranque
     para quem é atribuído, e nenhum caminho de atribuição voltava a
     tocar-lhes. Tirar o consultor do processo deixava as tarefas dele lá:
     um processo sem ninguém atribuído com tarefas de consultores.

REGRA DE NEGÓCIO (Opção A, decidida pelo dono)
  Nunca apagar trabalho humano em silêncio. Uma tarefa que o SISTEMA criou
  e que ninguém tocou desaparece com a atribuição que a justificava; tudo o
  resto fica, perde a atribuição e leva `assignment_orphaned` — porque uma
  tarefa órfã e uma tarefa por atribuir mostram as duas "Sem atribuição",
  e só a primeira exige uma decisão humana.

  "Por tocar" = criada pelo sistema, não concluída, e `updated_at` igual a
  `created_at`. Qualquer interacção (concluir, reabrir, editar) muda o
  `updated_at` e transforma-a em trabalho de alguém.
====================================================================
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from database import db

logger = logging.getLogger(__name__)

# Campos de atribuição do PROCESSO, canónicos e legados (ver AGENTS.md,
# "Atribuição: campos CANÓNICOS"). Ler só metade faria a limpeza tratar
# como removido quem continua atribuído.
CAMPOS_DE_ATRIBUICAO_DO_PROCESSO: tuple[str, ...] = (
    "assigned_consultor_ids", "assigned_consultor_id", "consultor_id",
    "assigned_consultant_ids", "assigned_consultant_id", "consultant_id",
    "assigned_mediador_ids", "assigned_mediador_id", "mediador_id",
    "assigned_indexacao_id", "assigned_parceiro_id",
    "assigned_to", "assigned_users", "manager_id",
)

# Marca de que a tarefa perdeu a atribuição por reatribuição do processo.
CAMPO_ORFA = "assignment_orphaned"

# Quem o sistema assume como autor quando a tarefa não é de uma pessoa.
AUTORES_DO_SISTEMA = frozenset({None, "", "system", "sistema"})


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def normalizar_assigned_to(valor: Any) -> list[str]:
    """`assigned_to` numa forma só: lista de ids, sem vazios nem repetidos.

    Aceita o escalar que o motor de automação gravava e o `None` que ele
    gravava quando não conseguia resolver ninguém.
    """
    if valor is None:
        return []
    if isinstance(valor, str):
        itens: Iterable[Any] = [valor]
    elif isinstance(valor, (list, tuple, set)):
        itens = valor
    else:
        itens = [valor]

    return [v for v in dict.fromkeys(_texto(i) for i in itens) if v]


def ids_atribuidos_do_processo(process: Optional[dict]) -> set[str]:
    """Quem está atribuído a um processo, lendo todos os campos canónicos."""
    encontrados: set[str] = set()
    for campo in CAMPOS_DE_ATRIBUICAO_DO_PROCESSO:
        encontrados.update(normalizar_assigned_to((process or {}).get(campo)))
    return encontrados


def tarefa_imaculada_do_sistema(tarefa: dict) -> bool:
    """A tarefa foi criada pelo sistema e ninguém lhe tocou?

    É a única categoria que se pode apagar: não é trabalho de ninguém.
    """
    if tarefa.get("completed") or tarefa.get("completed_at"):
        return False

    autor = tarefa.get("created_by")
    do_sistema = (
        (_texto(autor).lower() or None) in AUTORES_DO_SISTEMA
        or tarefa.get("source") == "automation"
    )
    if not do_sistema:
        return False

    criada = _texto(tarefa.get("created_at"))
    actualizada = _texto(tarefa.get("updated_at"))
    return not actualizada or actualizada == criada


@dataclass(frozen=True)
class PlanoDeLimpeza:
    """O que fazer às tarefas de quem saiu do processo."""

    apagar: list[str] = field(default_factory=list)
    # (task_id, quem continua atribuído) — lista vazia significa órfã.
    desatribuir: list[tuple[str, list[str]]] = field(default_factory=list)


def plano_de_limpeza(
    tarefas: Sequence[dict],
    *,
    removidos: set[str],
) -> PlanoDeLimpeza:
    """Decide, sem tocar na base de dados, o destino de cada tarefa."""
    apagar: list[str] = []
    desatribuir: list[tuple[str, list[str]]] = []

    alvos = {_texto(r) for r in (removidos or set()) if _texto(r)}
    if not alvos:
        # Uma atribuição que só ACRESCENTA pessoas não pode mexer em nada.
        return PlanoDeLimpeza()

    for tarefa in tarefas:
        atribuidos = normalizar_assigned_to(tarefa.get("assigned_to"))
        restantes = [uid for uid in atribuidos if uid not in alvos]
        if restantes == atribuidos:
            continue

        task_id = _texto(tarefa.get("id"))
        if not task_id:
            continue

        # Só fica órfã quando NINGUÉM sobra: tirar o consultor de uma
        # tarefa que também é do mediador não a deixa sem dono, e apagá-la
        # levaria o trabalho de quem ficou.
        if not restantes and tarefa_imaculada_do_sistema(tarefa):
            apagar.append(task_id)
        else:
            desatribuir.append((task_id, restantes))

    return PlanoDeLimpeza(apagar=apagar, desatribuir=desatribuir)


async def limpar_tarefas_orfas(process_id: str, *, removidos: set[str]) -> dict:
    """Aplica o plano às tarefas de um processo. NUNCA levanta.

    Corre DEPOIS de a atribuição já estar gravada: levantar aqui mostraria
    um erro sobre uma operação que correu bem (mesma regra da revogação do
    Portal, ponto 6).
    """
    resumo = {"apagadas": 0, "desatribuidas": 0}
    if not process_id or not removidos:
        return resumo

    try:
        tarefas = await db.tasks.find(
            {"process_id": process_id}, {"_id": 0},
        ).to_list(1000)
        plano = plano_de_limpeza(tarefas, removidos=removidos)

        for task_id in plano.apagar:
            await db.tasks.delete_one({"id": task_id})
            resumo["apagadas"] += 1

        for task_id, restantes in plano.desatribuir:
            await db.tasks.update_one(
                {"id": task_id},
                {"$set": {
                    "assigned_to": restantes,
                    CAMPO_ORFA: not restantes,
                }},
            )
            resumo["desatribuidas"] += 1

        if resumo["apagadas"] or resumo["desatribuidas"]:
            logger.info(
                "[TAREFAS] Processo %s: %d tarefa(s) automática(s) removida(s), "
                "%d tarefa(s) desatribuída(s) por reatribuição.",
                process_id, resumo["apagadas"], resumo["desatribuidas"],
            )
    except Exception as exc:
        logger.warning(
            "[TAREFAS] Falha a limpar tarefas órfãs do processo %s: %s",
            process_id, exc,
        )

    return resumo


async def marcar_reatribuidas(process_id: str, *, atribuidos: set[str]) -> int:
    """Tira a marca de órfã às tarefas que voltaram a ter dono. NUNCA levanta.

    Sem isto, a tarefa ficava para sempre a pedir atenção depois de já a
    ter recebido.
    """
    if not process_id or not atribuidos:
        return 0

    try:
        tarefas = await db.tasks.find(
            {"process_id": process_id, CAMPO_ORFA: True}, {"_id": 0},
        ).to_list(1000)

        tocadas = 0
        alvos = [_texto(a) for a in atribuidos if _texto(a)]
        for tarefa in tarefas:
            await db.tasks.update_one(
                {"id": tarefa.get("id")},
                {"$set": {CAMPO_ORFA: False, "assigned_to": alvos}},
            )
            tocadas += 1
        return tocadas
    except Exception as exc:
        logger.warning(
            "[TAREFAS] Falha a limpar a marca de órfã no processo %s: %s",
            process_id, exc,
        )
        return 0


@dataclass(frozen=True)
class DiffDeResponsaveis:
    """Quem entrou e quem saiu de uma tarefa."""

    entraram: list[str]
    sairam: list[str]

    @property
    def mudou(self) -> bool:
        return bool(self.entraram or self.sairam)


def diff_de_responsaveis(*, antes: Any, depois: Any) -> DiffDeResponsaveis:
    """Diferença entre os responsáveis de uma tarefa (ponto 10).

    Normaliza os DOIS lados antes de comparar. `run_update_task` fazia
    `set(task_data.assigned_to) - set(task.get("assigned_to", []))` e
    `set("u1")` em Python é `{'u', '1'}` — itera os CARACTERES. O ponto
    12 do Lote 4 documentou que o motor de automação gravava escalares e
    acrescentou a normalização à LEITURA; este caminho ficou de fora, e
    reatribuir uma tarefa de automação notificava letras.

    A ordem é a de entrada (não a de um `set`), para que a mensagem ao
    utilizador e o registo no histórico saiam sempre iguais.
    """
    lista_antes = normalizar_assigned_to(antes)
    lista_depois = normalizar_assigned_to(depois)
    conjunto_antes = set(lista_antes)
    conjunto_depois = set(lista_depois)
    return DiffDeResponsaveis(
        entraram=[u for u in lista_depois if u not in conjunto_antes],
        sairam=[u for u in lista_antes if u not in conjunto_depois],
    )
