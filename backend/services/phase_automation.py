"""Automação por fase: o que acontece quando um processo ENTRA numa fase.

(Bloco 3, ponto 12 — decisões do dono do produto)

O QUE FAZ
  Ao entrar numa fase o sistema (1) atribui, SÓ SE o papel estiver vazio, o
  consultor e/ou o intermediário de menor carga e (2) cria as tarefas modelo
  dessa fase. Ambos são configurados pelo Admin/CEO no editor de fases
  (`workflow_statuses.auto_assign_roles` / `task_templates`); as rotas que os
  gravam já exigem Admin/CEO.

`None` NÃO É `[]`
  Fase SEM configuração (`None`) herda o comportamento por omissão; fase
  configurada como `[]` quer dizer «nada». O por-omissão existe SÓ para a
  saída da Index (`origem="indexacao"`) e reproduz o que o sistema já fazia:
  consultor + intermediário e as duas tarefas de arranque. Qualquer outra
  fase sem configuração não faz nada — uma fase nova nunca atribui por
  acidente.

IDEMPOTÊNCIA
  Cada tarefa leva `phase_template = {fase, template_id}` e só se cria UMA
  vez por (processo, fase, modelo, responsável). Reentrar numa fase não
  duplica; e uma tarefa já concluída também impede a recriação (o trabalho
  foi feito). Apagar o modelo e recriá-lo com outro id cria tarefas novas —
  é uma tarefa diferente.

A ORDEM IMPORTA
  Atribui-se PRIMEIRO e criam-se as tarefas DEPOIS, sobre o documento já
  gravado: as tarefas vão para quem acabou de ser atribuído. Responsáveis
  por papel são quem tem esse papel NO MOMENTO (também o que estava
  atribuído de antes) — mudança face ao desenho antigo, que só tarefava os
  recém-atribuídos.

NUNCA ROMPE O MOVIMENTO
  A mudança de fase já está gravada quando isto corre. `ao_entrar_na_fase_
  sem_falhar` regista (`warning`, nunca em silêncio) e devolve um resultado
  vazio — um 500 aqui mostraria erro por uma operação que teve sucesso.

CARIMBO DE REDE
  As tarefas herdam o carimbo do PROCESSO (a autoridade: `run_create_task`
  carimba pela sessão, e aqui não há sessão — corre em fundo, pelo
  indexador, pelo motor). Sem carimbo no processo não se inventa um: meio
  carimbo é pior do que nenhum.

O CORTE DO PORTAL
  Entrar numa fase TERMINAL fecha já os WebSockets do Portal desse processo
  (`portal_estado`). O bloqueio em si não depende disto: a guarda do Portal
  lê a fase em cada pedido.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from database import db
from services.process_staff_assignment import (
    CONSULTOR_ID_FIELDS,
    MEDIADOR_ID_FIELDS,
)

logger = logging.getLogger(__name__)

ORIGEM_INDEXACAO = "indexacao"
ORIGEM_MOVIMENTO = "movimento"
ORIGEM_ENTRADA_NO_FLUXO = "entrada_no_fluxo"

#: Papéis que uma regra de fase atribui, pela ordem em que se atribuem.
PAPEIS_ATRIBUIVEIS = ("consultor", "intermediario")

#: Por omissão, e SÓ na saída da Index: o que o sistema já fazia.
PAPEIS_POR_OMISSAO_DA_SAIDA_DA_INDEX = PAPEIS_ATRIBUIVEIS

#: As duas tarefas de arranque de sempre. Vivem aqui (e não numa lista
#: escondida em `process_assignment`) para o editor poder MOSTRAR o que a
#: omissão faz e o Admin/CEO poder substituí-lo.
MODELOS_POR_OMISSAO_DA_SAIDA_DA_INDEX: tuple[dict, ...] = (
    {
        "id": "omissao-analisar-documentacao",
        "title": "Analisar documentação inicial",
        "priority": "Alta",
        "due_in_days": None,
        "assigned_role": "todos",
    },
    {
        "id": "omissao-agendar-contacto",
        "title": "Agendar contacto inicial com o cliente",
        "priority": "Média",
        "due_in_days": None,
        "assigned_role": "todos",
    },
)

_IDS_POR_PAPEL = {
    "consultor": ("assigned_consultor_ids", *CONSULTOR_ID_FIELDS),
    "intermediario": ("assigned_mediador_ids", *MEDIADOR_ID_FIELDS),
}


@dataclass(frozen=True)
class Plano:
    """O que fazer ao entrar numa fase. Decidido sem tocar na base de dados."""

    papeis: tuple[str, ...] = ()
    modelos: tuple[dict, ...] = ()
    # fase | omissao | nenhuma — para o log e para os testes.
    origem_da_config: str = "nenhuma"


@dataclass
class Resultado:
    """O que aconteceu. `atribuicao` tem a forma de `dual_auto_assign…`."""

    atribuicao: dict = field(default_factory=dict)
    tarefas_criadas: int = 0
    sessoes_cortadas: int = 0


# ====================================================================
# PURO
# ====================================================================

def plano_da_fase(fase: Optional[dict], origem: str) -> Plano:
    """O plano para uma fase (o documento de `workflow_statuses`) e uma origem."""
    fase = fase or {}
    papeis_cfg = fase.get("auto_assign_roles")
    modelos_cfg = fase.get("task_templates")
    na_saida_da_index = origem == ORIGEM_INDEXACAO

    if papeis_cfg is not None:
        papeis = tuple(p for p in papeis_cfg if p in PAPEIS_ATRIBUIVEIS)
        origem_papeis = "fase"
    elif na_saida_da_index:
        papeis = PAPEIS_POR_OMISSAO_DA_SAIDA_DA_INDEX
        origem_papeis = "omissao"
    else:
        papeis, origem_papeis = (), "nenhuma"

    if modelos_cfg is not None:
        modelos = tuple(dict(m) for m in modelos_cfg if isinstance(m, dict))
        origem_modelos = "fase"
    elif na_saida_da_index:
        # Cópias: o chamador pode mexer-lhes sem alterar a constante.
        modelos = tuple(dict(m) for m in MODELOS_POR_OMISSAO_DA_SAIDA_DA_INDEX)
        origem_modelos = "omissao"
    else:
        modelos, origem_modelos = (), "nenhuma"

    if "fase" in (origem_papeis, origem_modelos):
        origem_da_config = "fase"
    elif "omissao" in (origem_papeis, origem_modelos):
        origem_da_config = "omissao"
    else:
        origem_da_config = "nenhuma"
    return Plano(papeis=papeis, modelos=modelos, origem_da_config=origem_da_config)


def garantir_ids_dos_modelos(modelos: Iterable[dict]) -> list[dict]:
    """Dá um id estável a cada modelo e desfaz repetições.

    O id é a chave da idempotência: dois modelos com o mesmo id criavam uma
    tarefa só (o segundo parecia «já criado»).
    """
    vistos: set[str] = set()
    saida: list[dict] = []
    for modelo in modelos:
        copia = dict(modelo)
        ident = str(copia.get("id") or "").strip()
        if not ident or ident in vistos:
            ident = uuid.uuid4().hex[:12]
        vistos.add(ident)
        copia["id"] = ident
        saida.append(copia)
    return saida


def ids_do_papel(processo: dict, papel: str) -> list[str]:
    """Quem tem este papel no processo, lendo TODOS os campos que o carimbam."""
    campos = _IDS_POR_PAPEL.get(papel, ())
    encontrados: list[str] = []
    for campo in campos:
        valor = (processo or {}).get(campo)
        itens = valor if isinstance(valor, (list, tuple, set)) else [valor]
        for item in itens:
            texto = str(item).strip() if item is not None else ""
            if texto and texto not in encontrados:
                encontrados.append(texto)
    return encontrados


def responsaveis_do_modelo(modelo: dict, processo: dict) -> list[str]:
    """Os utilizadores a quem o modelo dá uma tarefa, neste processo."""
    papel = modelo.get("assigned_role") or "todos"
    papeis = PAPEIS_ATRIBUIVEIS if papel == "todos" else (papel,)
    responsaveis: list[str] = []
    for p in papeis:
        for uid in ids_do_papel(processo, p):
            if uid not in responsaveis:
                responsaveis.append(uid)
    return responsaveis


def construir_tarefa(
    modelo: dict,
    *,
    fase: str,
    processo: dict,
    responsavel: Optional[str],
    agora: datetime,
) -> dict:
    """O documento de `db.tasks` para um modelo, um responsável e um processo."""
    instante = agora.isoformat()
    prazo = modelo.get("due_in_days")
    due_date = (
        (agora + timedelta(days=int(prazo))).isoformat()
        if isinstance(prazo, (int, float)) and not isinstance(prazo, bool) and prazo >= 0
        else None
    )
    tarefa: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": modelo.get("title") or "Tarefa automática",
        "description": None,
        "assigned_to": [responsavel] if responsavel else [],
        "process_id": processo.get("id"),
        "due_date": due_date,
        "priority": modelo.get("priority") or "Média",
        "created_by": "system",
        "source": "phase_template",
        "phase_template": {"fase": fase, "template_id": modelo.get("id")},
        "completed": False,
        "completed_at": None,
        "completed_by": None,
        "created_at": instante,
        "updated_at": instante,
    }
    # Carimbo herdado do processo, só se estiver completo (rede decide).
    rede = str(processo.get("network_id") or "").strip()
    if rede:
        tarefa["network_id"] = rede
        for campo in ("company_id", "company_name"):
            if processo.get(campo):
                tarefa[campo] = processo[campo]
    return tarefa


# ====================================================================
# COM BASE DE DADOS
# ====================================================================

async def _carregar_fase(nome: Optional[str]) -> Optional[dict]:
    if not nome:
        return None
    from services.workflow_phases import carregar_fases, resolver_nome

    fases = await carregar_fases()
    resolucao = resolver_nome(nome, fases)
    alvo = resolucao.fase or nome
    return next((f for f in fases if f.get("name") == alvo), None)


async def criar_tarefas_da_fase(
    processo: dict, fase: str, modelos: Iterable[dict]
) -> int:
    """Cria as tarefas que ainda não existem. Devolve quantas criou."""
    agora = datetime.now(timezone.utc)
    criadas = 0
    for modelo in modelos:
        template_id = modelo.get("id")
        responsaveis = responsaveis_do_modelo(modelo, processo)
        # Sem ninguém no papel: a tarefa nasce sem responsável (visível a
        # quem gere) em vez de não nascer — uma tarefa em falta não se nota.
        alvos: list[Optional[str]] = list(responsaveis) or [None]
        for responsavel in alvos:
            filtro = {
                "process_id": processo.get("id"),
                "phase_template.fase": fase,
                "phase_template.template_id": template_id,
            }
            if responsavel:
                filtro["assigned_to"] = responsavel
            else:
                filtro["assigned_to"] = []
            if await db.tasks.find_one(filtro, {"_id": 0, "id": 1}):
                continue
            await db.tasks.insert_one(
                construir_tarefa(
                    modelo, fase=fase, processo=processo,
                    responsavel=responsavel, agora=agora,
                )
            )
            criadas += 1
    return criadas


async def ao_entrar_na_fase(
    process_id: str,
    fase: Optional[str],
    *,
    origem: str,
    actor: Optional[dict] = None,
) -> Resultado:
    """Executa o plano da fase `fase` sobre o processo (já gravado nela)."""
    resultado = Resultado()
    if not process_id or not fase:
        return resultado

    from services.portal_estado import estado_e_terminal
    from services.workflow_phases import carregar_fases

    fases = await carregar_fases()
    if estado_e_terminal(fase, fases):
        from services.portal_estado import cortar_sessoes_em_tempo_real

        resultado.sessoes_cortadas = await cortar_sessoes_em_tempo_real(process_id)
        return resultado  # uma fase terminal não atribui nem cria trabalho

    plano = plano_da_fase(await _carregar_fase(fase), origem)
    if not plano.papeis and not plano.modelos:
        return resultado

    actor = actor or {}
    if plano.papeis:
        from services.process_assignment import dual_auto_assign_on_pre_registo_transition

        processo_atual = await db.processes.find_one(
            {"id": process_id}, {"_id": 0, "company_id": 1, "company": 1}
        )
        resultado.atribuicao = await dual_auto_assign_on_pre_registo_transition(
            process_id=process_id,
            company_id=(processo_atual or {}).get("company_id")
            or (processo_atual or {}).get("company"),
            indexador_user_id=actor.get("id"),
            actor_role=actor.get("role"),
            papeis=plano.papeis,
        )

    if plano.modelos:
        # Lê o processo DEPOIS de atribuir: as tarefas vão para os novos.
        processo = await db.processes.find_one({"id": process_id}, {"_id": 0})
        if processo:
            resultado.tarefas_criadas = await criar_tarefas_da_fase(
                processo, fase, plano.modelos
            )

    logger.info(
        "[FASE-AUTO] processo=%s fase=%s origem=%s config=%s papeis=%s tarefas=%d",
        process_id, fase, origem, plano.origem_da_config, plano.papeis,
        resultado.tarefas_criadas,
    )
    return resultado


async def ao_entrar_na_fase_sem_falhar(
    process_id: str,
    fase: Optional[str],
    *,
    origem: str,
    actor: Optional[dict] = None,
) -> Resultado:
    """Igual a `ao_entrar_na_fase`, mas NUNCA levanta (ver o cabeçalho)."""
    try:
        return await ao_entrar_na_fase(process_id, fase, origem=origem, actor=actor)
    except Exception as e:
        logger.warning(
            "[FASE-AUTO] Falhou a automação da fase %s no processo %s "
            "(a mudança de fase fica): %s: %s",
            fase, process_id, type(e).__name__, e,
        )
        return Resultado()


__all__ = [
    "MODELOS_POR_OMISSAO_DA_SAIDA_DA_INDEX",
    "ORIGEM_ENTRADA_NO_FLUXO",
    "ORIGEM_INDEXACAO",
    "ORIGEM_MOVIMENTO",
    "PAPEIS_ATRIBUIVEIS",
    "Plano",
    "Resultado",
    "ao_entrar_na_fase",
    "ao_entrar_na_fase_sem_falhar",
    "construir_tarefa",
    "criar_tarefas_da_fase",
    "garantir_ids_dos_modelos",
    "ids_do_papel",
    "plano_da_fase",
    "responsaveis_do_modelo",
]
