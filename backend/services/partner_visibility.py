"""
====================================================================
PORTAL DO PARCEIRO — O QUE UM PARCEIRO VÊ (V1)
====================================================================
Condições de visibilidade, funil e DTOs. PURO (sem base de dados): o que
faz I/O vive em `partner_portal_read.py`, para esta regra se poder provar
sem Mongo — e para ser UM ponto, lido por todas as superfícies do parceiro.

A REGRA DE VISIBILIDADE É UMA RELAÇÃO, NÃO UM ÂMBITO
  O staff vê o que a sua rede contém. O parceiro vê **o que lhe foi
  atribuído** dentro da(s) sua(s) rede(s):

      assigned_parceiro_id == eu   E   rede ∈ as minhas redes activas

  As duas pernas, de propósito: a atribuição diz de quem é, a rede diz
  de que casa. Um erro de carimbo numa delas não abre o processo — só o
  esconde, que é o lado seguro de falhar.

  É a variante de **uma só perna de rede** do CRM
  (`build_network_scope_condition`), e NÃO a de processos
  (`build_process_scope_condition`): aquela acrescenta o ramo das redes
  convidadas (D-25), e um parceiro não herda uma partilha entre casas.
  Mais uma excepção ESCRITA ao inventário por AST da D-25.

O PARCEIRO NUNCA RECEBE O DOCUMENTO
  Tudo o que sai é construído campo a campo a partir de uma lista
  POSITIVA (`CAMPOS_DO_PROCESSO`, `CAMPOS_DA_LEAD`, …). O `ProcessModel`
  tem `extra="allow"` e já vazou campos por aí; aqui um campo novo no
  documento do processo NÃO chega ao parceiro sem alguém o escrever.
  **V1: nenhum dado financeiro, valor ou comissão** — nem na lista, nem
  no detalhe, nem nas métricas (decisão de produto; o teste
  `TestSemDadosFinanceiros` percorre a saída à procura de tokens
  financeiros, com contraprova).

O FUNIL USA A MACRO-FASE DO MOTOR
  O agrupamento das fases (Novo / Análise / Aprovado / Concluído /
  Perdido) já existe, é editável pelo Master e é o que o BI usa. O
  parceiro lê a MESMA classificação: duas tabelas de «o que conta como
  escriturado» divergem na primeira fase nova. Uma fase sem macro-fase
  (ou um estado que o motor não reconhece) cai em «Em curso» — nunca
  desaparece, e nunca é inventada como «Em análise».
====================================================================
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Optional

from services.partner_security import ids_das_redes_activas
from services.tenant_network import (
    TenantScope,
    build_network_scope_condition,
    rede_de_omissao,
)
from services.workflow_phases import macro_da_fase, resolver_nome

# ── O funil ─────────────────────────────────────────────────────────
ETAPA_LEAD = "lead"
ETAPA_NOVO = "novo"
ETAPA_ANALISE = "analise"
ETAPA_APROVADO = "aprovado"
ETAPA_CONCLUIDO = "concluido"
ETAPA_PERDIDO = "perdido"
ETAPA_EM_CURSO = "em_curso"

#: Pela ordem em que o parceiro as vê.
ETAPAS: tuple[str, ...] = (
    ETAPA_LEAD, ETAPA_NOVO, ETAPA_ANALISE, ETAPA_APROVADO,
    ETAPA_CONCLUIDO, ETAPA_PERDIDO, ETAPA_EM_CURSO,
)

ROTULOS_DAS_ETAPAS: dict[str, str] = {
    ETAPA_LEAD: "Leads",
    ETAPA_NOVO: "Em preparação",
    ETAPA_ANALISE: "Em análise",
    ETAPA_APROVADO: "Em aprovação",
    ETAPA_CONCLUIDO: "Escriturados",
    ETAPA_PERDIDO: "Perdidos",
    ETAPA_EM_CURSO: "Em curso",
}

#: macro-fase do motor → etapa do parceiro. Os valores à esquerda são os do
#: `MacroFase`; um valor novo no enum que não esteja aqui cai em «Em curso»
#: (e o teste de inventário falha a dizê-lo).
ETAPA_POR_MACRO_FASE: dict[str, str] = {
    "novo": ETAPA_NOVO,
    "analise": ETAPA_ANALISE,
    "aprovado": ETAPA_APROVADO,
    "concluido": ETAPA_CONCLUIDO,
    "perdido": ETAPA_PERDIDO,
}

# ── Os pedidos de documentos ────────────────────────────────────────
ESTADOS_PENDENTES = ("REQUESTED", "PENDING", "requested", "pending")
ORIGEM_DO_PARCEIRO = "partner_portal"
PREFIXO_DE_AUTORIA = "partner:"
AUTORIA_DO_CLIENTE = "portal_client"


def autoria_do_parceiro(partner_id: str) -> str:
    """O valor de `uploaded_by` que um ficheiro do parceiro leva."""
    return f"{PREFIXO_DE_AUTORIA}{partner_id}"


# ════════════════════════════════════════════════════════════════════
#  CONDIÇÕES
# ════════════════════════════════════════════════════════════════════
def scope_do_parceiro(partner: Optional[dict]) -> TenantScope:
    """O âmbito de REDE do parceiro: só as ligações activas.

    Sem nenhuma, o âmbito é vazio e `build_network_scope_condition` devolve
    a condição impossível — nunca «sem filtro». A rede de omissão (a pilha
    por carimbar) só entra para quem pertence a ela.
    """
    redes = ids_das_redes_activas(partner)
    omissao = rede_de_omissao()
    return TenantScope(
        network_ids=tuple(redes),
        inclui_rede_de_omissao=bool(omissao and omissao in redes),
    )


def condicao_de_processos(partner: dict) -> dict:
    """Os processos DESTE parceiro, nas suas redes, não eliminados."""
    return {
        "$and": [
            {"assigned_parceiro_id": str((partner or {}).get("id") or "")},
            build_network_scope_condition(scope_do_parceiro(partner)),
            {"is_deleted": {"$ne": True}},
        ]
    }


def condicao_de_leads(partner: dict) -> dict:
    """As leads DESTE parceiro: clientes que ele submeteu e que ainda não
    têm processo. `$in: [None, []]` casa com ausente, nulo e lista vazia."""
    return {
        "$and": [
            {"submitted_by_partner_id": str((partner or {}).get("id") or "")},
            build_network_scope_condition(scope_do_parceiro(partner)),
            {"is_deleted": {"$ne": True}},
            {"process_ids": {"$in": [None, []]}},
            {"lead_status": {"$in": [None, "new"]}},
        ]
    }


# ════════════════════════════════════════════════════════════════════
#  O FUNIL
# ════════════════════════════════════════════════════════════════════
def etapa_de_um_estado(status: Any, fases: Iterable[dict]) -> str:
    """A etapa do parceiro para o `status` gravado num processo."""
    fases = list(fases)
    resolucao = resolver_nome(str(status) if status is not None else "", fases)
    if not resolucao.resolvida:
        return ETAPA_EM_CURSO
    fase = next((f for f in fases if f.get("name") == resolucao.fase), None)
    macro = macro_da_fase(fase) if fase else None
    return ETAPA_POR_MACRO_FASE.get(macro or "", ETAPA_EM_CURSO)


def contagem_do_funil(etapas_dos_processos: Iterable[str], leads: int) -> dict[str, int]:
    contagem = Counter(etapas_dos_processos)
    funil = {etapa: int(contagem.get(etapa, 0)) for etapa in ETAPAS}
    funil[ETAPA_LEAD] = int(leads)
    return funil


def taxa_de_conversao(funil: dict[str, int]) -> Optional[float]:
    """Escriturados sobre tudo o que o parceiro trouxe. `None` sem base —
    zero casos não é «0 %» (um ecrã que diz 0 % a quem ainda não trouxe nada
    lê-se como fracasso)."""
    total = sum(int(v) for v in funil.values())
    if total <= 0:
        return None
    return round(100.0 * int(funil.get(ETAPA_CONCLUIDO, 0)) / total, 1)


# ════════════════════════════════════════════════════════════════════
#  OS DTOs — LISTAS POSITIVAS
# ════════════════════════════════════════════════════════════════════
#: O que se LÊ do processo para servir o parceiro. O `s3_folder` e os ids dos
#: clientes entram na leitura (as guardas de ficheiros precisam deles) mas
#: NÃO na saída.
PROJECCAO_DO_PROCESSO: dict[str, int] = {
    "_id": 0,
    "id": 1, "process_number": 1, "client_name": 1, "process_type": 1,
    "status": 1, "created_at": 1, "updated_at": 1,
    "consultor_name": 1, "consultor_names": 1,
    "assigned_parceiro_id": 1,
    "network_id": 1, "company_id": 1, "company_name": 1, "company": 1,
    "client_id": 1, "second_client_id": 1, "client_ids": 1,
    "s3_folder": 1, "is_indexed": 1, "skip_index": 1, "is_deleted": 1,
}

PROJECCAO_DA_LEAD: dict[str, int] = {
    "_id": 0,
    "id": 1, "nome": 1, "created_at": 1, "updated_at": 1,
    "pending_process_type": 1, "s3_folder": 1,
    "submitted_by_partner_id": 1,
    "network_id": 1, "company_id": 1, "company_name": 1, "company": 1,
    "process_ids": 1, "lead_status": 1, "is_deleted": 1,
}


def _nome_do_consultor(proc: dict) -> Optional[str]:
    nomes = proc.get("consultor_names")
    if isinstance(nomes, list):
        limpos = [str(n).strip() for n in nomes if isinstance(n, str) and n.strip()]
        if limpos:
            return ", ".join(limpos)
    nome = proc.get("consultor_name")
    return nome.strip() if isinstance(nome, str) and nome.strip() else None


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    return str(getattr(valor, "value", valor))


def dto_do_processo(proc: dict, etapa: str, *, pedidos_pendentes: int = 0) -> dict:
    """Um processo, como o parceiro o vê. Campo a campo — nunca `**proc`."""
    return {
        "kind": "process",
        "id": proc.get("id"),
        "process_number": proc.get("process_number"),
        "client_name": proc.get("client_name"),
        "process_type": _texto(proc.get("process_type")),
        "etapa": etapa,
        "etapa_label": ROTULOS_DAS_ETAPAS.get(etapa, ROTULOS_DAS_ETAPAS[ETAPA_EM_CURSO]),
        "consultor_name": _nome_do_consultor(proc),
        "pedidos_pendentes": int(pedidos_pendentes),
        "created_at": proc.get("created_at"),
        "updated_at": proc.get("updated_at") or proc.get("created_at"),
    }


def dto_da_lead(client: dict, *, pedidos_pendentes: int = 0) -> dict:
    return {
        "kind": "lead",
        "id": client.get("id"),
        "process_number": None,
        "client_name": client.get("nome"),
        "process_type": _texto(client.get("pending_process_type")),
        "etapa": ETAPA_LEAD,
        "etapa_label": ROTULOS_DAS_ETAPAS[ETAPA_LEAD],
        "consultor_name": None,
        "pedidos_pendentes": int(pedidos_pendentes),
        "created_at": client.get("created_at"),
        "updated_at": client.get("updated_at") or client.get("created_at"),
    }


def ordenar_por_actividade(casos: list[dict]) -> list[dict]:
    """O mais recente primeiro; sem data, no fim."""
    return sorted(casos, key=lambda c: str(c.get("updated_at") or ""), reverse=True)


def filtrar_casos(casos: list[dict], *, etapa: Optional[str] = None, pesquisa: Optional[str] = None) -> list[dict]:
    resultado = casos
    if etapa:
        resultado = [c for c in resultado if c.get("etapa") == etapa]
    termo = (pesquisa or "").strip().lower()
    if termo:
        resultado = [
            c for c in resultado
            if termo in str(c.get("client_name") or "").lower()
            or termo in str(c.get("process_number") or "").lower()
        ]
    return resultado


# ── Ficheiros ───────────────────────────────────────────────────────
def ficheiro_e_visivel(uploaded_by: Any, partner_id: str) -> bool:
    """O parceiro vê o que ele próprio e o cliente submeteram — e mais nada.

    O que a EQUIPA juntou (extractos obtidos, propostas, minutas) tem outro
    `uploaded_by` e fica de fora, mesmo estando na mesma pasta: a pasta é
    do cliente, a visibilidade é do ficheiro.
    """
    autor = str(uploaded_by or "")
    return autor == AUTORIA_DO_CLIENTE or (bool(partner_id) and autor == autoria_do_parceiro(partner_id))


def quem_enviou(uploaded_by: Any, partner_id: str) -> str:
    return "eu" if str(uploaded_by or "") == autoria_do_parceiro(partner_id) else "cliente"


__all__ = [
    "AUTORIA_DO_CLIENTE",
    "ESTADOS_PENDENTES",
    "ETAPAS",
    "ETAPA_CONCLUIDO",
    "ETAPA_EM_CURSO",
    "ETAPA_LEAD",
    "ETAPA_POR_MACRO_FASE",
    "ORIGEM_DO_PARCEIRO",
    "PREFIXO_DE_AUTORIA",
    "PROJECCAO_DA_LEAD",
    "PROJECCAO_DO_PROCESSO",
    "ROTULOS_DAS_ETAPAS",
    "autoria_do_parceiro",
    "condicao_de_leads",
    "condicao_de_processos",
    "contagem_do_funil",
    "dto_da_lead",
    "dto_do_processo",
    "etapa_de_um_estado",
    "ficheiro_e_visivel",
    "filtrar_casos",
    "ordenar_por_actividade",
    "quem_enviou",
    "scope_do_parceiro",
    "taxa_de_conversao",
]
