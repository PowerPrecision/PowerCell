"""Retrato do campo ``processes.status`` contra o motor de workflow.

ÉPICO 10, PARTE 3 — PASSO ZERO (medir antes de tocar)

PARA QUE SERVE
  O raio-x às três peças (status / workflow / Kanban) mostrou que o código
  se contradiz em cinco vocabulários de fases diferentes, e que dois deles
  não existem no motor. Mas o raio-x foi feito ao CÓDIGO. O que está
  gravado em produção só a produção sabe.

  Antes de dar a `workflow_statuses` o papel de Única Fonte da Verdade, é
  preciso saber o que é que essa decisão torna invisível. Um status sem
  fase configurada é hoje um processo que **não aparece no Kanban** e
  continua a contar para o número do cabeçalho — está provado em
  `tests/unit/test_workflow_status_coverage.py`.

  Este módulo é a parte PURA: recebe contagens e fases, devolve o retrato.
  Quem fala com a base de dados é `scripts/medir_status_producao.py`.

LEITURA. Este módulo não escreve nada, nem propõe escritas.
  Ao contrário do `s3_folder_coverage`, aqui não há `--aplicar`: o passo
  seguinte é uma decisão de produto (que macro-fase leva cada fase), não
  uma correspondência inequívoca que uma máquina possa fechar sozinha.

A REGRA DO ALIAS, repetida aqui porque é a que evita o desastre
  Um alias só vence quando o motor NÃO conhece o nome gravado E conhece o
  destino. E quando há mais do que um destino possível, não se escolhe —
  a mesma disciplina do ``rede_consensual`` (Lote 4) e do
  ``_propor_correspondencias`` (Gestor S3). Um alias errado reescreve a
  fase de um processo, e a execução seguinte aceita-o como verdade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from services.process_status import (
    ARCHIVED_STATUSES,
    INACTIVE_STATUSES,
    STATUS_VALUE_ALIASES,
)

# ====================================================================
# OS VOCABULÁRIOS QUE HOJE VIVEM CRAVADOS, TRAZIDOS PARA UM SÓ SÍTIO
# ====================================================================
# Não é a lista de fases — essa vem do motor. É o retrato do que o código
# ACREDITA hoje, para se poder medir a distância até ao que existe.

# Nomes antigos de fases, portados de `frontend/src/utils/processTimeline.js`
# (`ALIASES_LEGADOS`). O backend não os conhecia: o `STATUS_VALUE_ALIASES`
# só sabe de singular/plural dos terminais. São duas tabelas do mesmo
# assunto em lados opostos da aplicação — a Parte 1 funde-as; aqui estão
# juntas para a medição não ficar cega a metade dos casos.
ALIASES_LEGADOS_DO_PRODUTO: dict[str, str] = {
    "clientes_em_espera": "clientes_espera",
    "enviado_ao_bruno": "enviado_bruno",
    "enviado_ao_luis": "enviado_luis",
    "banco_em_analise": "fase_bancaria",
    "aprovado_pelo_banco": "ch_aprovado",
    "cpcv": "fase_escritura",
    "a_escriturar": "escritura_agendada",
    "escriturado": "concluidos",
    "recusado": "desistencias",
    "desistiu": "desistencias",
}

# As macro-fases COMO ESTÃO HOJE (`frontend/src/utils/funilDeFases.js`).
# Quatro grupos; `desistencias` não pertence a nenhum e cai em "Outras".
MACRO_FASES_DE_HOJE: dict[str, list[str]] = {
    "novo": [
        "clientes_espera", "fase_documental", "fase_documental_ii",
        "documentacao",
    ],
    "analise": [
        "enviado_bruno", "enviado_luis", "enviado_bcp_rui",
        "entradas_precision", "fase_bancaria", "fase_visitas",
        "analise", "pre_aprovacao",
    ],
    "aprovado": [
        "ch_aprovado", "fase_escritura", "escritura_agendada",
        "credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv",
        "minuta", "aprovado",
    ],
    "concluido": ["concluidos", "concluido", "escritura"],
}

# A PROPOSTA para a Parte 2: enum fechado de cinco valores. A diferença
# para o de hoje é o grupo `perdido`, que hoje não existe — as
# desistências caem em "Outras fases", o que num funil de negócio é
# exactamente o sítio errado para elas.
#
# Isto é uma PROPOSTA, não o comportamento actual. O relatório mostra os
# dois lado a lado de propósito: quem decide o agrupamento é o produto,
# e a partir da Parte 2 a decisão vive na base de dados, não aqui.
MACRO_FASES_PROPOSTAS: dict[str, list[str]] = {
    **MACRO_FASES_DE_HOJE,
    "perdido": [
        "desistencias", "desistencia", "desistido",
        "cancelado", "perdido", "arquivo",
    ],
}

MACRO_FASES_VALIDAS = ("novo", "analise", "aprovado", "concluido", "perdido")


# ====================================================================
# TABELA DE ALIASES UNIFICADA
# ====================================================================

def _fundir_grupos(grupos: list[set[str]]) -> list[set[str]]:
    """Funde grupos que partilhem pelo menos um nome.

    `escriturado -> concluidos` e `{concluido, concluidos}` são o mesmo
    assunto visto de dois sítios; sem a fusão, procurar por `escriturado`
    não encontraria `concluido`.
    """
    fundidos: list[set[str]] = []
    for grupo in grupos:
        actual = set(grupo)
        restantes: list[set[str]] = []
        for existente in fundidos:
            if existente & actual:
                actual |= existente
            else:
                restantes.append(existente)
        restantes.append(actual)
        fundidos = restantes
    return fundidos


def construir_tabela_de_aliases() -> dict[str, set[str]]:
    """``nome -> outros nomes que significam o mesmo`` (sem o próprio)."""
    grupos = [set(v) for v in STATUS_VALUE_ALIASES.values()]
    grupos += [{antigo, actual} for antigo, actual in ALIASES_LEGADOS_DO_PRODUTO.items()]
    tabela: dict[str, set[str]] = {}
    for grupo in _fundir_grupos(grupos):
        for nome in grupo:
            tabela[nome] = grupo - {nome}
    return tabela


def candidatos_de_alias(status: str, nomes_de_fases: Iterable[str]) -> list[str]:
    """Fases do motor que um alias de ``status`` poderia designar.

    Devolve ordenado para o relatório ser estável entre execuções.
    """
    conhecidas = set(nomes_de_fases)
    return sorted(construir_tabela_de_aliases().get(status, set()) & conhecidas)


def normalizar_para_gralha(nome: Optional[str]) -> str:
    """Forma canónica para detectar gralhas invisíveis.

    Um espaço à direita é outra chave no Mongo e a diferença não se vê no
    ecrã — a mesma armadilha do Campo de Rede (Lote 5, ponto 2).
    """
    return (nome or "").strip().lower().replace("-", "_")


# ====================================================================
# O RETRATO
# ====================================================================

@dataclass
class Retrato:
    """O que existe gravado, contra o que o motor conhece."""

    # Verdade crua
    contagens: dict[str, int] = field(default_factory=dict)
    contagens_eliminados: dict[str, int] = field(default_factory=dict)
    sem_status: int = 0
    processos_totais: int = 0

    # O motor
    fases_configuradas: list[str] = field(default_factory=list)
    fases_sem_processos: list[str] = field(default_factory=list)

    # Órfãos: status gravado sem fase no motor — HOJE INVISÍVEIS NO QUADRO
    orfaos_resoluveis: dict[str, str] = field(default_factory=dict)
    orfaos_ambiguos: dict[str, list[str]] = field(default_factory=dict)
    orfaos_desconhecidos: dict[str, int] = field(default_factory=dict)

    # Gralhas: normaliza para uma fase existente mas não é igual a ela
    suspeitas_de_gralha: dict[str, str] = field(default_factory=dict)

    # Macro-fases
    macro_de_hoje: dict[str, str] = field(default_factory=dict)
    macro_proposta: dict[str, str] = field(default_factory=dict)
    fases_sem_macro_hoje: list[str] = field(default_factory=list)
    fases_sem_macro_proposta: list[str] = field(default_factory=list)

    # As listas cravadas, medidas contra a realidade
    cobertura_das_listas: dict[str, dict] = field(default_factory=dict)

    @property
    def processos_orfaos(self) -> int:
        """Quantos processos estão hoje invisíveis no Kanban."""
        return (
            sum(self.contagens[s] for s in self.orfaos_resoluveis)
            + sum(self.contagens[s] for s in self.orfaos_ambiguos)
            + sum(self.orfaos_desconhecidos.values())
        )

    @property
    def percentagem_coberta(self) -> float:
        if not self.processos_totais:
            return 0.0
        cobertos = self.processos_totais - self.processos_orfaos - self.sem_status
        return round(100.0 * cobertos / self.processos_totais, 1)


def _macro_de(status: str, grupos: dict[str, list[str]]) -> Optional[str]:
    """Primeiro grupo que declara a fase (a mesma regra do funil)."""
    for macro, nomes in grupos.items():
        if status in nomes:
            return macro
    return None


def _medir_lista(nomes: Iterable[str], contagens: dict[str, int],
                 fases: set[str]) -> dict:
    """Quantos processos e quantas fases reais uma lista cravada apanha."""
    lista = list(nomes)
    return {
        "entradas": len(lista),
        "existem_no_motor": sorted(n for n in lista if n in fases),
        "nao_existem_no_motor": sorted(n for n in lista if n not in fases),
        "processos_abrangidos": sum(contagens.get(n, 0) for n in lista),
    }


def analisar(
    contagens: dict[str, int],
    fases_do_motor: Iterable[dict],
    *,
    contagens_eliminados: Optional[dict[str, int]] = None,
    sem_status: int = 0,
) -> Retrato:
    """Cruza as contagens gravadas com as fases configuradas.

    ``contagens`` é ``status -> nº de processos NÃO eliminados``. Os
    eliminados entram à parte: um soft-delete não é uma fase do workflow e
    contá-lo aqui inflacionava o problema (e o `status: "eliminado"` é o
    caso mais comum de todos).
    """
    fases = [f for f in fases_do_motor if isinstance(f, dict) and f.get("name")]
    nomes_de_fases = [f["name"] for f in fases]
    conjunto_de_fases = set(nomes_de_fases)

    retrato = Retrato(
        contagens=dict(contagens),
        contagens_eliminados=dict(contagens_eliminados or {}),
        sem_status=sem_status,
        processos_totais=sum(contagens.values()) + sem_status,
        fases_configuradas=nomes_de_fases,
        fases_sem_processos=sorted(
            n for n in nomes_de_fases if not contagens.get(n)
        ),
    )

    tabela = construir_tabela_de_aliases()
    normalizadas = {normalizar_para_gralha(n): n for n in nomes_de_fases}

    for status, quantos in contagens.items():
        if status in conjunto_de_fases:
            continue

        # Gralha invisível antes de tudo: `Concluidos ` não é um nome
        # antigo, é o mesmo nome mal gravado.
        canonica = normalizadas.get(normalizar_para_gralha(status))
        if canonica and canonica != status:
            retrato.suspeitas_de_gralha[status] = canonica

        candidatos = sorted(tabela.get(status, set()) & conjunto_de_fases)
        if len(candidatos) == 1:
            retrato.orfaos_resoluveis[status] = candidatos[0]
        elif len(candidatos) > 1:
            retrato.orfaos_ambiguos[status] = candidatos
        else:
            retrato.orfaos_desconhecidos[status] = quantos

    for nome in nomes_de_fases:
        hoje = _macro_de(nome, MACRO_FASES_DE_HOJE)
        proposta = _macro_de(nome, MACRO_FASES_PROPOSTAS)
        if hoje:
            retrato.macro_de_hoje[nome] = hoje
        else:
            retrato.fases_sem_macro_hoje.append(nome)
        if proposta:
            retrato.macro_proposta[nome] = proposta
        else:
            retrato.fases_sem_macro_proposta.append(nome)

    # As listas cravadas que o raio-x encontrou. Importadas dos módulos
    # REAIS (incluindo privadas) de propósito: uma cópia aqui mediria a
    # cópia, não o que o produto usa.
    from services.stats_branches import (
        _ACTIVE_STATUSES,
        _APPROVED_STATUSES,
        _COMPLETED_STATUSES,
    )

    retrato.cobertura_das_listas = {
        "process_status.INACTIVE_STATUSES": _medir_lista(
            INACTIVE_STATUSES, contagens, conjunto_de_fases),
        "process_status.ARCHIVED_STATUSES": _medir_lista(
            ARCHIVED_STATUSES, contagens, conjunto_de_fases),
        "stats_branches._ACTIVE_STATUSES": _medir_lista(
            _ACTIVE_STATUSES, contagens, conjunto_de_fases),
        "stats_branches._APPROVED_STATUSES": _medir_lista(
            _APPROVED_STATUSES, contagens, conjunto_de_fases),
        "stats_branches._COMPLETED_STATUSES": _medir_lista(
            _COMPLETED_STATUSES, contagens, conjunto_de_fases),
    }
    return retrato


# ====================================================================
# SAÍDAS
# ====================================================================

def _linha(rotulo: str, valor, largura: int = 34) -> str:
    return f"  {rotulo.ljust(largura, '.')} {valor}"


def formatar_relatorio(r: Retrato) -> str:
    """Relatório legível — é isto que se leva à decisão do agrupamento."""
    linhas = [
        "",
        "═" * 68,
        "  RETRATO DO CAMPO `processes.status` CONTRA O MOTOR",
        "═" * 68,
        _linha("Processos (não eliminados)", r.processos_totais),
        _linha("  sem status (leads)", r.sem_status),
        _linha("Valores distintos de status", len(r.contagens)),
        _linha("Fases configuradas no motor", len(r.fases_configuradas)),
        "",
        _linha("INVISÍVEIS NO KANBAN hoje", r.processos_orfaos),
        _linha("  resolúveis por alias", len(r.orfaos_resoluveis)),
        _linha("  ambíguos (>1 candidato)", len(r.orfaos_ambiguos)),
        _linha("  desconhecidos", len(r.orfaos_desconhecidos)),
        _linha("Cobertura", f"{r.percentagem_coberta}%"),
        "═" * 68,
    ]

    if r.contagens:
        linhas += ["", "  DISTRIBUIÇÃO (status → processos):"]
        for status, quantos in sorted(
            r.contagens.items(), key=lambda kv: -kv[1]
        ):
            marca = "  " if status in set(r.fases_configuradas) else "!!"
            linhas.append(f"   {marca} {str(status).ljust(30)} {quantos}")
        linhas.append("      (!! = sem fase no motor → não aparece no quadro)")

    if r.suspeitas_de_gralha:
        linhas += ["", "  SUSPEITAS DE GRALHA (mesma fase, mal gravada):"]
        linhas += [
            f"    - {gravado!r} → {fase!r}"
            for gravado, fase in sorted(r.suspeitas_de_gralha.items())
        ]

    if r.orfaos_resoluveis:
        linhas += ["", "  ÓRFÃOS COM ALIAS INEQUÍVOCO:"]
        linhas += [
            f"    - {s} → {destino}  ({r.contagens.get(s, 0)} processo(s))"
            for s, destino in sorted(r.orfaos_resoluveis.items())
        ]

    if r.orfaos_ambiguos:
        linhas += ["", "  ÓRFÃOS AMBÍGUOS (não se adivinha):"]
        linhas += [
            f"    - {s} → {candidatos}  ({r.contagens.get(s, 0)} processo(s))"
            for s, candidatos in sorted(r.orfaos_ambiguos.items())
        ]

    if r.orfaos_desconhecidos:
        linhas += ["", "  ÓRFÃOS SEM QUALQUER CANDIDATO:"]
        linhas += [
            f"    - {s}  ({quantos} processo(s))"
            for s, quantos in sorted(
                r.orfaos_desconhecidos.items(), key=lambda kv: -kv[1]
            )
        ]

    if r.fases_sem_processos:
        linhas += ["", "  FASES CONFIGURADAS SEM UM ÚNICO PROCESSO:"]
        linhas += [f"    - {n}" for n in r.fases_sem_processos]

    if r.fases_sem_macro_proposta:
        linhas += ["", "  FASES QUE O AGRUPAMENTO PROPOSTO NÃO COBRE:"]
        linhas += [f"    - {n}" for n in r.fases_sem_macro_proposta]
        linhas.append("      (ficariam em 'Outras fases' até o admin decidir)")

    linhas += ["", "  LISTAS CRAVADAS NO CÓDIGO, MEDIDAS CONTRA O MOTOR:"]
    for nome, medida in r.cobertura_das_listas.items():
        linhas.append(
            f"    {nome}: {len(medida['existem_no_motor'])}/"
            f"{medida['entradas']} nomes existem  •  "
            f"{medida['processos_abrangidos']} processo(s)"
        )
        if medida["nao_existem_no_motor"]:
            linhas.append(
                f"      inexistentes: {', '.join(medida['nao_existem_no_motor'])}"
            )

    if r.contagens_eliminados:
        total = sum(r.contagens_eliminados.values())
        linhas += ["", f"  (à parte: {total} processo(s) com is_deleted)"]

    return "\n".join(linhas) + "\n"


def para_json(r: Retrato) -> dict:
    """Retrato completo, para devolver e discutir sobre os mesmos números."""
    return {
        "processos_totais": r.processos_totais,
        "sem_status": r.sem_status,
        "percentagem_coberta": r.percentagem_coberta,
        "processos_invisiveis_no_kanban": r.processos_orfaos,
        "contagens": r.contagens,
        "contagens_eliminados": r.contagens_eliminados,
        "fases_configuradas": r.fases_configuradas,
        "fases_sem_processos": r.fases_sem_processos,
        "orfaos_resoluveis": r.orfaos_resoluveis,
        "orfaos_ambiguos": r.orfaos_ambiguos,
        "orfaos_desconhecidos": r.orfaos_desconhecidos,
        "suspeitas_de_gralha": r.suspeitas_de_gralha,
        "macro_de_hoje": r.macro_de_hoje,
        "macro_proposta": r.macro_proposta,
        "fases_sem_macro_hoje": r.fases_sem_macro_hoje,
        "fases_sem_macro_proposta": r.fases_sem_macro_proposta,
        "cobertura_das_listas": r.cobertura_das_listas,
        "aliases_list": {
            nome: sorted(outros)
            for nome, outros in sorted(construir_tabela_de_aliases().items())
        },
        "macro_fases_validas": list(MACRO_FASES_VALIDAS),
    }
