"""D-15 — quanta data de nascimento está em texto simples? (medição, só leitura)

A decisão sobre a D-15 (encriptar e perder o filtro Sub35, ou manter) é do
dono do produto com o DPO. Esta medição serve-a com números: em que colecções
e campos a data existe, em que fracção está em claro, e quantos valores não
são nem uma data ISO nem um valor encriptado (lixo que uma migração teria de
tratar à mão). Parte PURA; `scripts/medir_datas_de_nascimento.py` lê a base.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from services.encryption import is_encrypted

#: Os caminhos onde a data pode viver, por colecção. Os nomes de campo vêm da
#: regra Sub35 (`CAMPOS_DE_NASCIMENTO`) — uma lista à mão divergiria dela.
from services.sub35 import CAMPOS_DE_NASCIMENTO

SECCOES_POR_COLECCAO: dict[str, tuple[str, ...]] = {
    "processes": ("personal_data", "titular2_data", ""),
    "clients": ("dados_pessoais", "titular2_data", ""),
}

#: Listas de pessoas dentro do documento, com a data em cada elemento.
LISTAS_POR_COLECCAO: dict[str, tuple[str, ...]] = {
    "processes": ("co_buyers",),
    "clients": (),
}

VAZIO, CIFRADO, ISO, OUTRO = "vazio", "cifrado", "iso", "outro"
ESTADOS = (VAZIO, CIFRADO, ISO, OUTRO)

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def caminhos_de_uma_colecao(colecao: str) -> list[str]:
    """Os caminhos pontuados escalares (`personal_data.birth_date`, `birth_date`, …)."""
    caminhos = []
    for seccao in SECCOES_POR_COLECCAO.get(colecao, ()):
        for campo in CAMPOS_DE_NASCIMENTO:
            caminhos.append(f"{seccao}.{campo}" if seccao else campo)
    return caminhos


def projeccao(colecao: str) -> dict:
    proj = {"_id": 0}
    for c in caminhos_de_uma_colecao(colecao):
        proj[c] = 1
    for lista in LISTAS_POR_COLECCAO.get(colecao, ()):
        for campo in CAMPOS_DE_NASCIMENTO:
            proj[f"{lista}.{campo}"] = 1
    return proj


def estado_do_valor(valor: Any) -> str:
    """vazio / cifrado / iso / outro. Um `datetime` conta como `iso` (está em claro)."""
    if valor is None:
        return VAZIO
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return VAZIO
        if is_encrypted(texto):
            return CIFRADO
        return ISO if _ISO.match(texto) else OUTRO
    if hasattr(valor, "isoformat"):
        return ISO
    return OUTRO


def _valor_no_caminho(doc: dict, caminho: str) -> Any:
    actual: Any = doc
    for parte in caminho.split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
    return actual


def valores_do_documento(colecao: str, doc: dict) -> Iterable[tuple[str, Any]]:
    """(caminho, valor) para cada data que o documento tem — escalares e em listas."""
    for caminho in caminhos_de_uma_colecao(colecao):
        yield caminho, _valor_no_caminho(doc, caminho)
    for lista in LISTAS_POR_COLECCAO.get(colecao, ()):
        elementos = doc.get(lista)
        if not isinstance(elementos, list):
            continue
        for elemento in elementos:
            if not isinstance(elemento, dict):
                continue
            for campo in CAMPOS_DE_NASCIMENTO:
                yield f"{lista}[].{campo}", elemento.get(campo)


@dataclass
class Relatorio:
    documentos: Counter = field(default_factory=Counter)             # colecção → docs lidos
    por_caminho: dict = field(default_factory=dict)                  # (colecção, caminho) → Counter(estado)
    documentos_com_data_em_claro: Counter = field(default_factory=Counter)

    def somar(self, colecao: str, doc: dict) -> None:
        self.documentos[colecao] += 1
        em_claro = False
        for caminho, valor in valores_do_documento(colecao, doc):
            estado = estado_do_valor(valor)
            self.por_caminho.setdefault((colecao, caminho), Counter())[estado] += 1
            if estado == ISO:
                em_claro = True
        if em_claro:
            self.documentos_com_data_em_claro[colecao] += 1


def auditar(colecao: str, documentos: Iterable[dict], relatorio: Relatorio | None = None) -> Relatorio:
    relatorio = relatorio or Relatorio()
    for doc in documentos:
        relatorio.somar(colecao, doc)
    return relatorio


def resumir(relatorio: Relatorio) -> dict:
    """Totais por colecção e por estado, sem os caminhos sem nenhum valor."""
    por_colecao: dict[str, dict] = {}
    for (colecao, caminho), contagem in sorted(relatorio.por_caminho.items()):
        presentes = sum(v for k, v in contagem.items() if k != VAZIO)
        if not presentes:
            continue
        por_colecao.setdefault(colecao, {})[caminho] = {e: contagem.get(e, 0) for e in ESTADOS}
    return {
        "documentos": dict(relatorio.documentos),
        "com_data_em_claro": dict(relatorio.documentos_com_data_em_claro),
        "por_colecao": por_colecao,
        "total_em_claro": sum(
            c.get(ISO, 0) for c in relatorio.por_caminho.values()
        ),
        "total_outro": sum(
            c.get(OUTRO, 0) for c in relatorio.por_caminho.values()
        ),
    }
