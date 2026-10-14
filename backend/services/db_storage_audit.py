"""Passo 1 da D-13 — MEDIR antes de mover: peso e idade das colecções.

A PERGUNTA
==========
O épico de custos do Atlas (TECHNICAL_DEBT D-13) tem cinco passos e o primeiro
é «medir». Sem a tabela, arquiva-se a colecção errada: a intuição diz
`history`, os números podem dizer `emails`. Este módulo é a parte PURA da
medição (classificar, ordenar, condições de idade); `scripts/medir_colecoes.py`
é a parte que fala com a base de dados, só de leitura.

A IDADE NÃO É UM TIPO
=====================
As colecções guardam a data de duas maneiras: `datetime` (os campos `_dt` e
`expire_at`, que os TTL exigem) e **texto ISO** (`created_at` em quase tudo —
ex.: `datetime.now(timezone.utc).isoformat()`). Uma consulta `{campo: {$lt: x}}`
com x datetime só casa com datetimes e com x texto só casa com texto (o Mongo
compara por tipo), pelo que contar «mais antigo que N dias» com UM só tipo
subestima em silêncio — e uma medição que subestima o que é velho é a que
autoriza não arquivar nada. `condicao_mais_antigo_que` junta os dois com `$or`.

O QUE ESTA MEDIÇÃO NÃO DIZ
==========================
Não diz o que PODE ser apagado. Os prazos de conservação são decisão jurídica
(o `audit_trail` é conformidade), e `LEITURA_DO_PESO` só aponta onde está o
volume. Quem decide é uma pessoa com a tabela à frente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

#: Escalões de idade, em dias, do mais novo para o mais velho.
ESCALOES_EM_DIAS: tuple[int, ...] = (30, 90, 180, 365)

#: Colecção → campos de data candidatos, por ordem de preferência. O primeiro
#: que tiver documentos é o que se usa (`escolher_campo_de_data`).
COLECCOES_MEDIDAS: dict[str, tuple[str, ...]] = {
    "processes": ("updated_at", "created_at"),
    "clients": ("updated_at", "created_at"),
    "history": ("timestamp", "created_at"),
    "activities": ("created_at", "timestamp"),
    "system_error_logs": ("timestamp_dt", "timestamp", "created_at"),
    "audit_logs": ("timestamp", "created_at"),
    "audit_trail": ("created_at", "timestamp"),
    "emails": ("updated_at_dt", "created_at", "date"),
    "notifications": ("created_at",),
    "task_logs": ("created_at",),
    "chat_messages": ("created_at",),
    "documents": ("created_at", "uploaded_at"),
    "refresh_tokens": ("created_at_dt", "created_at"),
    "job_heartbeats": ("last_run_at", "updated_at"),
}

#: Acima desta fatia do total de dados, uma colecção merece atenção.
FATIA_RELEVANTE = 0.10

#: Fatia mínima do que é mais velho que o último escalão para ser candidata.
FATIA_ANTIGA_RELEVANTE = 0.50

LEITURA_DO_PESO = (
    "Isto aponta onde está o volume e quanto dele é antigo; não diz o que se "
    "pode apagar. Retenção é decisão jurídica (o audit_trail é conformidade)."
)


@dataclass
class LinhaDaColeccao:
    """O que se sabe de UMA colecção."""

    nome: str
    existe: bool = True
    documentos: int = 0
    bytes_dados: int = 0
    bytes_indices: int = 0
    bytes_armazenados: int = 0
    campo_de_data: Optional[str] = None
    #: documentos mais velhos que cada escalão (dias → contagem)
    mais_antigos_que: dict[int, int] = field(default_factory=dict)
    sem_data: int = 0
    #: motivo, quando a colecção não foi medida por inteiro
    aviso: Optional[str] = None

    @property
    def bytes_totais(self) -> int:
        return self.bytes_dados + self.bytes_indices

    @property
    def media_por_documento(self) -> int:
        return self.bytes_dados // self.documentos if self.documentos else 0

    def fatia_mais_antiga_que(self, dias: int) -> Optional[float]:
        """Fatia dos documentos COM data que é mais velha que `dias`; `None` se não se mediu."""
        if dias not in self.mais_antigos_que:
            return None
        com_data = self.documentos - self.sem_data
        if com_data <= 0:
            return None
        return self.mais_antigos_que[dias] / com_data


def _inteiro(valor: Any) -> int:
    try:
        return max(int(valor), 0)
    except (TypeError, ValueError):
        return 0


def linha_de_collstats(nome: str, stats: Optional[dict]) -> LinhaDaColeccao:
    """Traduz a resposta do `collStats`. `None` = a colecção não existe (não é zero bytes)."""
    if stats is None:
        return LinhaDaColeccao(nome=nome, existe=False, aviso="a colecção não existe")
    return LinhaDaColeccao(
        nome=nome,
        documentos=_inteiro(stats.get("count")),
        bytes_dados=_inteiro(stats.get("size")),
        bytes_indices=_inteiro(stats.get("totalIndexSize")),
        bytes_armazenados=_inteiro(stats.get("storageSize")),
    )


# ────────────────────────────────────────────────────────────────────
# Idade
# ────────────────────────────────────────────────────────────────────

def _para_utc(valor: datetime) -> datetime:
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)


def corte_em(agora: datetime, dias: int) -> tuple[datetime, str]:
    """O limite «há `dias` dias» como datetime e como texto ISO (mesmo formato de `.isoformat()`)."""
    limite = _para_utc(agora) - timedelta(days=dias)
    return limite, limite.isoformat()


def condicao_mais_antigo_que(campo: str, agora: datetime, dias: int) -> dict:
    """«`campo` anterior a há `dias` dias», para datetime E para texto ISO.

    O Mongo compara por tipo: o ramo datetime só casa datetimes e o ramo texto
    só casa texto. Um campo ausente ou `null` não casa em nenhum (conta-se à
    parte em `condicao_sem_data`).
    """
    limite, limite_iso = corte_em(agora, dias)
    return {"$or": [{campo: {"$lt": limite}}, {campo: {"$lt": limite_iso}}]}


def condicao_sem_data(campo: str) -> dict:
    """Documentos sem data utilizável: ausente, `null` ou de um tipo que não é data nem texto."""
    return {"$nor": [
        {campo: {"$type": "date"}},
        {campo: {"$type": "string"}},
    ]}


def escolher_campo_de_data(contagens: dict[str, int], candidatos: Iterable[str]) -> Optional[str]:
    """O primeiro candidato com documentos; `None` quando nenhum tem (não se inventa um)."""
    for campo in candidatos:
        if contagens.get(campo, 0) > 0:
            return campo
    return None


# ────────────────────────────────────────────────────────────────────
# Leitura da tabela
# ────────────────────────────────────────────────────────────────────

def ordenar_por_peso(linhas: Iterable[LinhaDaColeccao]) -> list[LinhaDaColeccao]:
    """As que ocupam mais primeiro; empate pelo nome (saída estável)."""
    return sorted(linhas, key=lambda l: (-l.bytes_totais, l.nome))


def total_de_bytes(linhas: Iterable[LinhaDaColeccao]) -> int:
    return sum(l.bytes_totais for l in linhas if l.existe)


def fatia_do_total(linha: LinhaDaColeccao, linhas: Iterable[LinhaDaColeccao]) -> float:
    total = total_de_bytes(linhas)
    return linha.bytes_totais / total if total else 0.0


def pontos_de_atencao(linhas: list[LinhaDaColeccao]) -> list[tuple[str, str]]:
    """(colecção, motivo) onde o volume E a idade juntos justificam olhar.

    Uma colecção grande e toda recente não é candidata a arquivo; uma velha e
    minúscula também não. É a conjunção que interessa.
    """
    ultimo = ESCALOES_EM_DIAS[-1]
    saida: list[tuple[str, str]] = []
    for linha in ordenar_por_peso(linhas):
        if not linha.existe or fatia_do_total(linha, linhas) < FATIA_RELEVANTE:
            continue
        antiga = linha.fatia_mais_antiga_que(ultimo)
        if antiga is None:
            saida.append((linha.nome, "pesa muito mas não tem data utilizável: a idade não se mede"))
        elif antiga >= FATIA_ANTIGA_RELEVANTE:
            saida.append((
                linha.nome,
                f"{antiga:.0%} dos documentos têm mais de {ultimo} dias",
            ))
    return saida


def formatar_bytes(n: int) -> str:
    valor = float(n)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{valor:.0f} {unidade}" if unidade == "B" else f"{valor:.1f} {unidade}"
        valor /= 1024
    return f"{n} B"  # inalcançável; satisfaz o tipo
