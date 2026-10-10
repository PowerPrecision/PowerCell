"""Motor do relatório executivo — desempenho da equipa (Bloco 4, pontos 13 e 16).

UM MOTOR PARA TRÊS SUPERFÍCIES
  O Dashboard Executivo, o Relatório Semanal e o PDF respondem à mesma
  pergunta — «o que fez cada pessoa da minha rede neste período?» — e o
  email de segunda-feira ao CEO também. Havia uma implementação (em
  `analytics_service`) com defeitos que só se viam ao compará-la com os
  dados reais; este módulo substitui-a e o `analytics_service` passa a ser
  uma fachada. Duas implementações da mesma política divergem.

OS DEFEITOS DO ANTERIOR (verificados no código, não presumidos)
  1. **«Tarefas» eram os `task_logs`** — trabalhos de fundo do sistema (IA,
     extracções) — e não as tarefas de uma pessoa (`db.tasks`). O painel do
     CEO mostrava quantas extracções a IA correu, atribuídas a quem as
     despoletou, como «tarefas concluídas».
  2. **O fim do período era ignorado.** Só havia `$gte início`: «Semana
     passada» contava também esta semana.
  3. **`$regex` com `i` sobre `action`**: não usa índice, e `moveu|avançou`
     apanhava qualquer acção com essas letras. A mudança de fase é um facto
     estruturado (`field` ∈ campos de estado), não uma palavra no texto.
  4. **A Indexação aparecia na tabela com zeros.** Por regra, as acções do
     perfil `indexacao` não geram registo; mostrar-lhe uma linha de zeros num
     relatório executivo diz «não fez nada» quando o que é verdade é «não
     se regista». Fica de fora — de todas as colunas.

O QUE «NÃO BLOQUEAR A BASE DE DADOS» QUER DIZER AQUI
  * Todas as agregações abrem com um `$match` sobre campos INDEXADOS
    (`user_id`+`created_at` no histórico; `completed_by`+`completed_at` e
    `assigned_to`+`created_at` nas tarefas — declarados em `db_indexes.py`).
    Nenhuma varre a colecção.
  * Os `$group` encadeados reduzem para (pessoas × fases) linhas dentro da
    base de dados; o Python nunca recebe uma linha por evento.
  * `maxTimeMS` e `allowDiskUse` em todas: uma agregação que demora demais é
    CORTADA pela base de dados (e vira um 503 que diz o que fazer), em vez de
    segurar uma ligação e uma CPU do cluster.
  * O período tem tecto (366 dias) e as listas têm tecto (pessoas, movimentos).
  * As agregações correm em SÉRIE, não em paralelo: um relatório não é urgente
    ao ponto de justificar seis cursores ao mesmo tempo.
  * Cache de 60 s por (âmbito, período, filtros): o botão «Actualizar» e o PDF
    gerado a seguir à vista não repetem o trabalho. A chave inclui o ÂMBITO —
    um filtro de rede sobre uma cache partilhada é teatro.

A REGRA DE ATRIBUIÇÃO (escolhida, documentada, com teste)
  * **Concluída** conta a quem a CONCLUIU (`completed_by`): é o facto
    registado, e uma tarefa partilhada por três não vale três vezes.
  * **Pendente / em atraso** contam a quem está ATRIBUÍDO: é a carga em mãos.
  * «Pendente» é o estado NO FIM do período, reconstruído (criada antes do
    fim e ainda aberta, ou concluída só depois do fim) — uma semana fechada
    dá os mesmos números hoje e daqui a um mês, o que é o que torna o
    registo semanal um REGISTO.
  * «Em atraso» é pendente com prazo anterior ao fim do período (ou a hoje,
    se o período ainda não acabou). Prazos só com data valem até ao fim do dia.

LIMITES CONHECIDOS (ditos, não escondidos)
  * O histórico não leva carimbo de rede: as CONTAGENS de mudanças de fase são
    por pessoa do âmbito, qualquer que seja a rede do processo. A lista de
    movimentos, essa, filtra pelos processos do âmbito de quem pede.
  * Quem tem o histórico desligado (`track_history=False`) não deixa rasto de
    fases: a coluna mostra «—», nunca 0.
"""
from __future__ import annotations

import copy
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from database import db
from services.history import _STATUS_FIELDS

logger = logging.getLogger(__name__)

MAX_DIAS = 366
LIMITE_DE_UTILIZADORES = 500
LIMITE_DE_MOVIMENTOS = 200
DIAS_MAXIMOS_DA_SERIE = 92
TTL_DA_CACHE_SEGUNDOS = 60
MAX_CACHE = 64

#: Perfis que entram no relatório. `indexacao` NUNCA: ver o ponto 4 acima.
PAPEIS_DO_RELATORIO = (
    "consultor", "intermediario", "administrativo", "diretor", "ceo", "master", "admin",
)

CAMPOS_DE_FASE = tuple(sorted(_STATUS_FIELDS))
ACAO_DE_MOVER = "Moveu processo"

NOTAS_DE_CRITERIO = (
    "Tarefa concluída conta a quem a concluiu; pendente e em atraso contam a "
    "quem está atribuído, no estado do fim do período.",
    "Mudança de fase: as registadas no histórico do processo. Quem tem o "
    "histórico desligado aparece com «—».",
    "O perfil Indexação não consta deste relatório (as suas acções não geram registo).",
)


class PeriodoInvalido(ValueError):
    """O período pedido não é válido (a mensagem é para o utilizador)."""


class RelatorioIndisponivel(RuntimeError):
    """A base de dados não respondeu a tempo (ou falhou). Nunca vira «vazio»."""


def _max_time_ms() -> int:
    try:
        valor = int(os.environ.get("EXEC_REPORT_MAX_TIME_MS", "10000"))
    except ValueError:
        return 10_000
    return valor if valor > 0 else 10_000


# ════════════════════════════════════════════════════════════════════
# PERÍODO — puro
# ════════════════════════════════════════════════════════════════════

def parse_data(texto: Any, nome: str) -> date:
    try:
        return datetime.strptime(str(texto).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise PeriodoInvalido(f"{nome} inválido. Use AAAA-MM-DD")


def segunda_da_semana(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def semana_de(dia: date) -> tuple[date, date]:
    """Segunda a domingo da semana (ISO) que contém `dia`."""
    segunda = segunda_da_semana(dia)
    return segunda, segunda + timedelta(days=6)


@dataclass(frozen=True)
class Periodo:
    inicio: date
    fim: date  # inclusivo

    @property
    def inicio_utc(self) -> datetime:
        return datetime.combine(self.inicio, datetime.min.time(), tzinfo=timezone.utc)

    @property
    def fim_exclusivo_utc(self) -> datetime:
        return datetime.combine(self.fim + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1


def construir_periodo(
    inicio: Optional[str], fim: Optional[str], *, hoje: Optional[date] = None,
) -> Periodo:
    """Valida o período. Omissões: fim = hoje, início = 7 dias terminando no fim."""
    hoje = hoje or datetime.now(timezone.utc).date()
    fim_data = parse_data(fim, "end_date") if fim else hoje
    inicio_data = parse_data(inicio, "start_date") if inicio else fim_data - timedelta(days=6)
    if inicio_data > fim_data:
        raise PeriodoInvalido("start_date deve ser anterior ou igual a end_date")
    if (fim_data - inicio_data).days + 1 > MAX_DIAS:
        raise PeriodoInvalido(f"O período não pode exceder {MAX_DIAS} dias")
    return Periodo(inicio_data, fim_data)


@dataclass(frozen=True)
class Filtros:
    periodo: Periodo
    user_ids: tuple[str, ...] = ()
    papeis: tuple[str, ...] = ()
    com_movimentos: bool = False


def normalizar_lista(valor: Any) -> tuple[str, ...]:
    """`"a, b"` / `["a","b"]` → `("a","b")`, sem vazios nem repetidos, ordenado."""
    if valor is None:
        return ()
    bruto = valor.split(",") if isinstance(valor, str) else list(valor)
    return tuple(sorted({str(v).strip() for v in bruto if str(v).strip()}))


# ════════════════════════════════════════════════════════════════════
# ÂMBITO
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Ambito:
    #: Identifica o âmbito (cache e registo semanal). Hash, para não ser lido.
    chave: str
    consulta_de_utilizadores: dict = field(default_factory=dict)
    condicao_de_tarefas: dict = field(default_factory=dict)
    #: `TenantScope` para filtrar movimentos por processo; `None` = consolidado.
    scope: Any = None
    redes: tuple[str, ...] = ()


async def resolver_ambito(user: Optional[dict]) -> Ambito:
    """O âmbito de quem pede; `None` é o consolidado (email de segunda, D-7)."""
    if not user:
        logger.warning(
            "[RELATORIO-EXEC] Relatório gerado SEM utilizador: âmbito global, "
            "atravessa todas as redes. Só o email automático deve chegar aqui."
        )
        return Ambito(chave="global")

    from services.tenant_network import resolve_tenant_scope

    return await resolver_ambito_do_scope(await resolve_tenant_scope(user))


async def resolver_ambito_do_scope(scope) -> Ambito:
    """O âmbito do relatório para um `TenantScope` (sem utilizador).

    É o que o email de segunda-feira usa: corre UMA vez por rede, com o
    âmbito dessa rede, e nunca mistura dados de duas. `sem_fronteira` (o
    Master) entra na chave: um âmbito sem listas é «nada» para um
    utilizador comum e «tudo» para o Master, e partilhar a chave de cache
    serviria os números globais a quem não os pode ver.
    """
    from services.admin_users_scope import build_users_scope_query, empresas_do_scope
    from services.tenant_network import build_network_scope_condition

    consulta = await build_users_scope_query(await empresas_do_scope(scope))
    assinatura = "|".join([
        ",".join(sorted(scope.network_ids)),
        ",".join(sorted(scope.company_ids)),
        ",".join(sorted(scope.company_names)),
        "1" if scope.inclui_rede_de_omissao else "0",
        "g" if scope.sem_fronteira else "l",
    ])
    return Ambito(
        chave=hashlib.sha256(assinatura.encode("utf-8")).hexdigest()[:16],
        consulta_de_utilizadores=consulta,
        condicao_de_tarefas=build_network_scope_condition(scope),
        scope=scope,
        redes=tuple(scope.network_ids),
    )


# ════════════════════════════════════════════════════════════════════
# PIPELINES — puros (testados contra um Mongo REAL em tests/integration)
# ════════════════════════════════════════════════════════════════════

def _iso(momento: datetime) -> str:
    return momento.isoformat()


def match_de_mudancas_de_fase(ids: list[str], inicio_iso: str, fim_iso: str) -> dict:
    """Mudança de fase = facto estruturado (campo de estado), não texto."""
    return {
        "user_id": {"$in": ids},
        "created_at": {"$gte": inicio_iso, "$lt": fim_iso},
        "$or": [{"field": {"$in": list(CAMPOS_DE_FASE)}}, {"action": ACAO_DE_MOVER}],
    }


def pipeline_mudancas_por_pessoa(ids: list[str], inicio_iso: str, fim_iso: str) -> list[dict]:
    return [
        {"$match": match_de_mudancas_de_fase(ids, inicio_iso, fim_iso)},
        {"$group": {
            "_id": {"user_id": "$user_id", "process_id": "$process_id"},
            "n": {"$sum": 1},
        }},
        {"$group": {
            "_id": "$_id.user_id",
            "processos": {"$sum": 1},
            "mudancas": {"$sum": "$n"},
        }},
    ]


def pipeline_mudancas_por_fase(ids: list[str], inicio_iso: str, fim_iso: str) -> list[dict]:
    return [
        {"$match": match_de_mudancas_de_fase(ids, inicio_iso, fim_iso)},
        {"$group": {
            "_id": {"user_id": "$user_id", "fase": "$new_value"},
            "n": {"$sum": 1},
        }},
    ]


def pipeline_mudancas_por_dia(ids: list[str], inicio_iso: str, fim_iso: str) -> list[dict]:
    return [
        {"$match": match_de_mudancas_de_fase(ids, inicio_iso, fim_iso)},
        {"$group": {
            "_id": {"$substrBytes": ["$created_at", 0, 10]},
            "n": {"$sum": 1},
        }},
    ]


def _com_ambito(condicao: dict, ambito_de_tarefas: dict) -> dict:
    if not ambito_de_tarefas:
        return condicao
    return {"$and": [ambito_de_tarefas, condicao]}


def pipeline_concluidas_por_pessoa(
    ids: list[str], inicio_iso: str, fim_iso: str, ambito_de_tarefas: dict,
) -> list[dict]:
    return [
        {"$match": _com_ambito({
            "completed_by": {"$in": ids},
            "completed_at": {"$gte": inicio_iso, "$lt": fim_iso},
            "completed": True,
            "is_deleted": {"$ne": True},
        }, ambito_de_tarefas)},
        {"$group": {"_id": "$completed_by", "n": {"$sum": 1}}},
    ]


def pipeline_concluidas_por_dia(
    ids: list[str], inicio_iso: str, fim_iso: str, ambito_de_tarefas: dict,
) -> list[dict]:
    return [
        {"$match": _com_ambito({
            "completed_by": {"$in": ids},
            "completed_at": {"$gte": inicio_iso, "$lt": fim_iso},
            "completed": True,
            "is_deleted": {"$ne": True},
        }, ambito_de_tarefas)},
        {"$group": {"_id": {"$substrBytes": ["$completed_at", 0, 10]}, "n": {"$sum": 1}}},
    ]


def pipeline_carga_em_aberto(
    ids: list[str], fim_iso: str, limite_de_prazo: str, ambito_de_tarefas: dict,
) -> list[dict]:
    """Pendentes e em atraso por pessoa atribuída, no estado do FIM do período.

    `limite_de_prazo` é uma DATA (AAAA-MM-DD): prazo com data só vale até ao
    fim desse dia. O `$and` com o `$type` protege o `$substrBytes` de um
    prazo que não seja texto (o `$and` faz curto-circuito).
    """
    return [
        {"$match": _com_ambito({
            "assigned_to": {"$in": ids},
            "created_at": {"$lt": fim_iso},
            "is_deleted": {"$ne": True},
            "$or": [{"completed": {"$ne": True}}, {"completed_at": {"$gte": fim_iso}}],
        }, ambito_de_tarefas)},
        {"$unwind": "$assigned_to"},
        {"$match": {"assigned_to": {"$in": ids}}},
        {"$group": {
            "_id": "$assigned_to",
            "pendentes": {"$sum": 1},
            "atrasadas": {"$sum": {"$cond": [
                {"$and": [
                    {"$eq": [{"$type": "$due_date"}, "string"]},
                    {"$lt": [{"$substrBytes": ["$due_date", 0, 10]}, limite_de_prazo]},
                ]},
                1, 0,
            ]}},
        }},
    ]


# ════════════════════════════════════════════════════════════════════
# ACESSO À BASE DE DADOS — a costura que os testes unitários substituem
# ════════════════════════════════════════════════════════════════════

async def _correr(coluna, pipeline: list[dict], max_time_ms: int) -> list[dict]:
    """Corre uma agregação com tecto de tempo. Nunca devolve «vazio» por falha."""
    from pymongo.errors import ExecutionTimeout, PyMongoError

    try:
        cursor = coluna.aggregate(pipeline, allowDiskUse=True, maxTimeMS=max_time_ms)
        return await cursor.to_list(None)
    except ExecutionTimeout as erro:
        logger.warning("[RELATORIO-EXEC] Agregação cortada por tempo (%d ms): %s", max_time_ms, erro)
        raise RelatorioIndisponivel(
            "O relatório demorou demasiado a calcular. Reduza o período ou filtre por utilizador."
        ) from erro
    except PyMongoError as erro:
        logger.error("[RELATORIO-EXEC] Falha na agregação: %s", erro)
        raise RelatorioIndisponivel(
            "Não foi possível calcular o relatório neste momento. Tente novamente."
        ) from erro


async def _ler_utilizadores(base, ambito: Ambito, filtros: Filtros) -> list[dict]:
    from services.role_query import deep_role_in_filter

    papeis = [p for p in (filtros.papeis or PAPEIS_DO_RELATORIO) if p in PAPEIS_DO_RELATORIO]
    if not papeis:
        return []
    condicoes: list[dict] = [
        deep_role_in_filter(papeis),
        {"role": {"$ne": "indexacao"}},
        {"is_active": {"$ne": False}},
    ]
    if ambito.consulta_de_utilizadores:
        condicoes.append(ambito.consulta_de_utilizadores)
    if filtros.user_ids:
        condicoes.append({"id": {"$in": list(filtros.user_ids)}})
    return await base.users.find(
        {"$and": condicoes},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "track_history": 1},
    ).sort("name", 1).to_list(LIMITE_DE_UTILIZADORES + 1)


async def _ler_movimentos(base, ids: list[str], inicio_iso: str, fim_iso: str, max_time_ms: int) -> list[dict]:
    from pymongo.errors import ExecutionTimeout, PyMongoError

    try:
        cursor = base.history.find(
            match_de_mudancas_de_fase(ids, inicio_iso, fim_iso),
            {"_id": 0, "user_id": 1, "process_id": 1, "old_value": 1, "new_value": 1, "created_at": 1},
        ).sort("created_at", -1).limit(LIMITE_DE_MOVIMENTOS * 3)
        if hasattr(cursor, "max_time_ms"):
            cursor = cursor.max_time_ms(max_time_ms)
        return await cursor.to_list(LIMITE_DE_MOVIMENTOS * 3)
    except ExecutionTimeout as erro:
        raise RelatorioIndisponivel(
            "O relatório demorou demasiado a calcular. Reduza o período ou filtre por utilizador."
        ) from erro
    except PyMongoError as erro:
        raise RelatorioIndisponivel(
            "Não foi possível calcular o relatório neste momento. Tente novamente."
        ) from erro


async def _ler_processos(base, process_ids: list[str]) -> dict[str, dict]:
    from services.tenant_network import PROJECCAO_DO_CARIMBO

    if not process_ids:
        return {}
    docs = await base.processes.find(
        {"id": {"$in": process_ids}},
        {"_id": 0, "id": 1, "process_number": 1, "client_name": 1,
         "partner_network_ids": 1, **PROJECCAO_DO_CARIMBO},
    ).to_list(len(process_ids))
    return {d["id"]: d for d in docs if d.get("id")}


# ════════════════════════════════════════════════════════════════════
# MONTAGEM — pura
# ════════════════════════════════════════════════════════════════════

def rotulo_da_fase(chave: Any, fases: list[dict]) -> str:
    """O nome que o utilizador vê para uma fase (ou o próprio texto, legível)."""
    from services.workflow_phases import resolver_nome

    texto = str(chave or "").strip()
    if not texto:
        return "—"
    resolucao = resolver_nome(texto, fases)
    if resolucao.resolvida:
        fase = next((f for f in fases if f.get("name") == resolucao.fase), None)
        if fase:
            return str(fase.get("label") or fase.get("name") or texto)
    return texto.replace("_", " ").strip().capitalize()


def serie_diaria(
    periodo: Periodo, mudancas: dict[str, int], concluidas: dict[str, int],
) -> list[dict]:
    """Um ponto por dia, com zeros — um gráfico com buracos engana."""
    if periodo.dias > DIAS_MAXIMOS_DA_SERIE:
        return []
    dias = []
    for deslocamento in range(periodo.dias):
        dia = (periodo.inicio + timedelta(days=deslocamento)).isoformat()
        dias.append({
            "dia": dia,
            "mudancas_de_fase": int(mudancas.get(dia, 0)),
            "tarefas_concluidas": int(concluidas.get(dia, 0)),
        })
    return dias


def montar_relatorio(
    *,
    utilizadores: list[dict],
    por_pessoa: dict[str, dict],
    por_fase_e_pessoa: list[dict],
    concluidas: dict[str, int],
    carga: dict[str, dict],
    mudancas_por_dia: dict[str, int],
    concluidas_por_dia: dict[str, int],
    fases: list[dict],
    filtros: Filtros,
    truncado: bool,
    agora: Optional[datetime] = None,
) -> dict:
    """Combina os resultados das agregações. Pura: sem base de dados."""
    agora = agora or datetime.now(timezone.utc)
    fases_por_pessoa: dict[str, dict[str, int]] = {}
    fases_total: dict[str, int] = {}
    for linha in por_fase_e_pessoa:
        chave = linha.get("_id") or {}
        uid, fase = chave.get("user_id"), chave.get("fase")
        n = int(linha.get("n") or 0)
        if not uid:
            continue
        fases_por_pessoa.setdefault(uid, {})
        fases_por_pessoa[uid][fase] = fases_por_pessoa[uid].get(fase, 0) + n
        fases_total[fase] = fases_total.get(fase, 0) + n

    def _lista_de_fases(contagens: dict) -> list[dict]:
        return [
            {"fase": fase, "rotulo": rotulo_da_fase(fase, fases), "n": n}
            for fase, n in sorted(contagens.items(), key=lambda kv: (-kv[1], str(kv[0])))
        ]

    linhas = []
    for u in utilizadores:
        uid = u["id"]
        silenciado = u.get("track_history") is False
        feitas = por_pessoa.get(uid, {})
        aberto = carga.get(uid, {})
        linhas.append({
            "user_id": uid,
            "name": u.get("name") or "Desconhecido",
            "email": u.get("email") or "",
            "role": u.get("role") or "",
            # Sem histórico não há rasto de fases: «—» (None), nunca 0.
            "phase_changes": None if silenciado else int(feitas.get("mudancas", 0)),
            "processes_moved": None if silenciado else int(feitas.get("processos", 0)),
            "historico_silenciado": silenciado,
            "tasks_completed": int(concluidas.get(uid, 0)),
            "tasks_pending": int(aberto.get("pendentes", 0)),
            "tasks_overdue": int(aberto.get("atrasadas", 0)),
            "por_fase": _lista_de_fases(fases_por_pessoa.get(uid, {})),
        })

    linhas.sort(key=lambda r: (
        -(r["processes_moved"] or 0), -r["tasks_completed"], r["name"].lower(),
    ))

    def _soma(campo: str) -> int:
        return sum(int(r[campo] or 0) for r in linhas)

    fim_inclusivo = filtros.periodo.fim_exclusivo_utc - timedelta(seconds=1)
    return {
        "period_start": _iso(filtros.periodo.inicio_utc),
        "period_end": _iso(fim_inclusivo),
        "start_date": filtros.periodo.inicio.isoformat(),
        "end_date": filtros.periodo.fim.isoformat(),
        "gerado_em": _iso(agora),
        "filtros": {"user_ids": list(filtros.user_ids), "papeis": list(filtros.papeis)},
        "summary": {
            "total_users": len(linhas),
            "total_phase_changes": _soma("phase_changes"),
            "total_processes_moved": _soma("processes_moved"),
            "total_tasks_completed": _soma("tasks_completed"),
            "total_tasks_pending": _soma("tasks_pending"),
            "total_tasks_overdue": _soma("tasks_overdue"),
        },
        "users": linhas,
        "por_fase": _lista_de_fases(fases_total),
        "serie_diaria": serie_diaria(filtros.periodo, mudancas_por_dia, concluidas_por_dia),
        "serie_omitida": filtros.periodo.dias > DIAS_MAXIMOS_DA_SERIE,
        "truncado": truncado,
        "limite_de_utilizadores": LIMITE_DE_UTILIZADORES,
        "notas": list(NOTAS_DE_CRITERIO),
    }


def _por_chave(linhas: list[dict], campo: str = "n") -> dict[str, int]:
    return {str(l["_id"]): int(l.get(campo) or 0) for l in linhas if l.get("_id") is not None}


async def montar_movimentos(
    base, linhas: list[dict], nomes: dict[str, str], fases: list[dict], ambito: Ambito,
) -> list[dict]:
    """Os movimentos recentes, só dos processos do âmbito. Sem nomes de clientes."""
    from services.tenant_network import processo_no_ambito

    processos = await _ler_processos(base, sorted({l["process_id"] for l in linhas if l.get("process_id")}))
    saida: list[dict] = []
    for linha in linhas:
        processo = processos.get(linha.get("process_id"))
        if not processo:
            continue
        if ambito.scope is not None and not processo_no_ambito(processo, ambito.scope):
            continue
        saida.append({
            "user_id": linha.get("user_id"),
            "user_name": nomes.get(linha.get("user_id"), ""),
            "process_id": linha.get("process_id"),
            "process_number": processo.get("process_number"),
            "de": linha.get("old_value"),
            "de_rotulo": rotulo_da_fase(linha.get("old_value"), fases),
            "para": linha.get("new_value"),
            "para_rotulo": rotulo_da_fase(linha.get("new_value"), fases),
            "em": linha.get("created_at"),
        })
        if len(saida) >= LIMITE_DE_MOVIMENTOS:
            break
    return saida


# ════════════════════════════════════════════════════════════════════
# ORQUESTRAÇÃO
# ════════════════════════════════════════════════════════════════════

_cache: dict[tuple, tuple[float, dict]] = {}


def limpar_cache() -> None:
    _cache.clear()


def _chave_de_cache(ambito: Ambito, filtros: Filtros) -> tuple:
    return (
        ambito.chave, filtros.periodo.inicio, filtros.periodo.fim,
        filtros.user_ids, filtros.papeis, filtros.com_movimentos,
    )


async def gerar_relatorio(
    ambito: Ambito,
    filtros: Filtros,
    *,
    usar_cache: bool = True,
    agora: Optional[datetime] = None,
    base=None,
) -> dict:
    """O relatório do período, para o âmbito de quem pede.

    `base` é a base de dados (omissão: a da aplicação); a fachada
    `analytics_service` passa a que recebeu do chamador.

    Levanta `RelatorioIndisponivel` se a base de dados cortar por tempo.
    """
    base = base if base is not None else db
    chave = _chave_de_cache(ambito, filtros)
    momento = time.monotonic()
    if usar_cache and chave in _cache and _cache[chave][0] > momento:
        return copy.deepcopy(_cache[chave][1])

    agora = agora or datetime.now(timezone.utc)
    utilizadores = await _ler_utilizadores(base, ambito, filtros)
    truncado = len(utilizadores) > LIMITE_DE_UTILIZADORES
    utilizadores = utilizadores[:LIMITE_DE_UTILIZADORES]
    ids = [u["id"] for u in utilizadores if u.get("id")]

    from services.workflow_phases import carregar_fases

    fases = await carregar_fases()
    if not ids:
        relatorio = montar_relatorio(
            utilizadores=[], por_pessoa={}, por_fase_e_pessoa=[], concluidas={}, carga={},
            mudancas_por_dia={}, concluidas_por_dia={}, fases=fases, filtros=filtros,
            truncado=False, agora=agora,
        )
        if filtros.com_movimentos:
            relatorio["movimentos"] = []
        return relatorio

    inicio_iso = _iso(filtros.periodo.inicio_utc)
    fim_iso = _iso(filtros.periodo.fim_exclusivo_utc)
    # «Hoje» é o limite dos atrasos se o período ainda não terminou.
    limite_de_prazo = min(filtros.periodo.fim_exclusivo_utc, agora).date().isoformat()
    tempo = _max_time_ms()
    tarefas_ambito = ambito.condicao_de_tarefas
    com_serie = filtros.periodo.dias <= DIAS_MAXIMOS_DA_SERIE

    # Em SÉRIE, de propósito (ver a docstring do módulo).
    pessoa = await _correr(base.history, pipeline_mudancas_por_pessoa(ids, inicio_iso, fim_iso), tempo)
    por_fase_pessoa = await _correr(base.history, pipeline_mudancas_por_fase(ids, inicio_iso, fim_iso), tempo)
    concluidas = await _correr(
        base.tasks, pipeline_concluidas_por_pessoa(ids, inicio_iso, fim_iso, tarefas_ambito), tempo,
    )
    carga = await _correr(
        base.tasks, pipeline_carga_em_aberto(ids, fim_iso, limite_de_prazo, tarefas_ambito), tempo,
    )
    dia_mudancas, dia_concluidas = [], []
    if com_serie:
        dia_mudancas = await _correr(base.history, pipeline_mudancas_por_dia(ids, inicio_iso, fim_iso), tempo)
        dia_concluidas = await _correr(
            base.tasks, pipeline_concluidas_por_dia(ids, inicio_iso, fim_iso, tarefas_ambito), tempo,
        )

    relatorio = montar_relatorio(
        utilizadores=utilizadores,
        por_pessoa={str(l["_id"]): l for l in pessoa if l.get("_id")},
        por_fase_e_pessoa=por_fase_pessoa,
        concluidas=_por_chave(concluidas),
        carga={str(l["_id"]): l for l in carga if l.get("_id")},
        mudancas_por_dia=_por_chave(dia_mudancas),
        concluidas_por_dia=_por_chave(dia_concluidas),
        fases=fases,
        filtros=filtros,
        truncado=truncado,
        agora=agora,
    )

    if filtros.com_movimentos:
        ids_com_historico = [u["id"] for u in utilizadores if u.get("track_history") is not False]
        brutos = await _ler_movimentos(base, ids_com_historico, inicio_iso, fim_iso, tempo) if ids_com_historico else []
        nomes = {u["id"]: u.get("name") or "" for u in utilizadores}
        relatorio["movimentos"] = await montar_movimentos(base, brutos, nomes, fases, ambito)

    if usar_cache:
        if len(_cache) >= MAX_CACHE:
            _cache.clear()
        _cache[chave] = (momento + TTL_DA_CACHE_SEGUNDOS, copy.deepcopy(relatorio))
    return relatorio
