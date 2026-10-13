"""Cópias órfãs de ``system_config`` (``company:<id>``) — o que se pode apagar (Out 2026).

COMO NASCERAM
  ``get_system_config(<empresa>)`` — para uma empresa sem configuração própria —
  gravava uma CÓPIA da global em ``company:<id>`` só por alguém a LER (abrir o
  ecrã, enviar um email, gerar uma proposta). Cada cópia leva as credenciais da
  global em claro (SMTP, IMAP, chaves de IA e de storage) e fazia o Webmail de
  uma rede satélite mostrar a caixa da rede-mãe. A leitura deixou de gravar
  (copy-on-write: só o primeiro ``PATCH`` cria o documento), mas as cópias que
  já existem ficaram na base de dados.

O QUE É «ÓRFÃ» E O QUE NÃO É
  Só se apaga o que se PROVA ser uma cópia sem informação própria: igual à
  global em tudo o que não é volátil. Quatro veredictos:

    ``copia_identica``       igual à global e a empresa existe — apagar é sem
                             perda (reconstrói-se da global quando alguém a
                             editar);
    ``copia_sem_empresa``    igual à global mas a empresa já não existe em
                             ``companies``: fantasma. Apaga-se só com uma
                             bandeira própria, porque o ecrã do Master ainda
                             aceita uma empresa que "tenha configuração" como
                             existente (``_empresa_existe``);
    ``divergente``           difere da global em ≥1 secção: pode ser configuração
                             REAL da empresa ou uma cópia desactualizada — não
                             há forma de o distinguir por conteúdo. **Nunca se
                             apaga automaticamente**; o relatório diz as
                             secções (nunca os valores: são credenciais);
    ``ilegivel``             não valida como configuração: decisão humana.

  Volátil = ``_id``, ``company_id``, ``created_at``, ``updated_at`` e
  ``setup_completed`` (a cópia nunca herda a flag de setup).

Puro: recebe documentos, devolve veredictos. Nunca imprime valores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from models.system_config import SystemConfig

PREFIXO = "company:"
ID_GLOBAL = "main"
VOLATEIS = ("_id", "company_id", "created_at", "updated_at", "setup_completed")

VEREDICTO_IDENTICA = "copia_identica"
VEREDICTO_SEM_EMPRESA = "copia_sem_empresa"
VEREDICTO_DIVERGENTE = "divergente"
VEREDICTO_ILEGIVEL = "ilegivel"

#: Os que o script pode apagar por omissão com ``--aplicar``.
APAGAVEIS_POR_OMISSAO = (VEREDICTO_IDENTICA,)


class ConfiguracaoGlobalIlegivel(RuntimeError):
    """Sem a global não há com quê comparar: nada se classifica (falha fechada)."""


@dataclass(frozen=True)
class Veredicto:
    doc_id: str
    company_id: str
    veredicto: str
    seccoes_diferentes: tuple = ()
    updated_at: Optional[str] = None
    motivo: str = ""

    @property
    def apagavel_por_omissao(self) -> bool:
        return self.veredicto in APAGAVEIS_POR_OMISSAO


@dataclass
class Resumo:
    total: int = 0
    por_veredicto: dict = field(default_factory=dict)


def e_documento_de_empresa(doc_id: Any) -> bool:
    """``company:<algo>`` — e só isso. A colecção guarda muito mais (templates, RGPD…)."""
    return isinstance(doc_id, str) and doc_id.startswith(PREFIXO) and len(doc_id) > len(PREFIXO)


def _normalizar(doc: dict) -> dict:
    """O documento tal como o modelo o entende, sem o que é volátil.

    Passar pelo modelo preenche omissões: uma global antiga, sem campos que a
    cópia (gravada pelo modelo actual) já tem, não pode parecer divergente por
    isso.
    """
    limpo = {k: v for k, v in doc.items() if k not in VOLATEIS}
    modelo = SystemConfig(**limpo).model_dump(mode="json")
    for chave in VOLATEIS:
        modelo.pop(chave, None)
    return modelo


def normalizar_global(doc_global: Optional[dict]) -> dict:
    if not isinstance(doc_global, dict) or not doc_global:
        raise ConfiguracaoGlobalIlegivel("Não existe documento da configuração global (_id: main).")
    try:
        return _normalizar(doc_global)
    except Exception as exc:  # noqa: BLE001
        raise ConfiguracaoGlobalIlegivel(f"A configuração global não valida: {type(exc).__name__}") from exc


def classificar(doc: dict, global_normalizada: dict, empresas_existentes: set) -> Veredicto:
    """Veredicto de UM documento ``company:<id>`` face à global já normalizada."""
    doc_id = str(doc.get("_id"))
    company_id = doc_id[len(PREFIXO):]
    atualizado = doc.get("updated_at") if isinstance(doc.get("updated_at"), str) else None
    try:
        propria = _normalizar(doc)
    except Exception as exc:  # noqa: BLE001
        return Veredicto(doc_id, company_id, VEREDICTO_ILEGIVEL, updated_at=atualizado,
                         motivo=f"não valida como configuração ({type(exc).__name__})")

    diferentes = tuple(sorted(
        chave for chave in set(propria) | set(global_normalizada)
        if propria.get(chave) != global_normalizada.get(chave)
    ))
    if diferentes:
        return Veredicto(doc_id, company_id, VEREDICTO_DIVERGENTE, diferentes, atualizado,
                         "difere da global: pode ser configuração própria")
    if company_id not in empresas_existentes:
        return Veredicto(doc_id, company_id, VEREDICTO_SEM_EMPRESA, (), atualizado,
                         "cópia da global de uma empresa que já não existe")
    return Veredicto(doc_id, company_id, VEREDICTO_IDENTICA, (), atualizado,
                     "cópia exacta da global")


def classificar_todas(
    docs: Iterable[dict], doc_global: Optional[dict], empresas_existentes: Iterable[str],
) -> list[Veredicto]:
    """Classifica os documentos ``company:<id>`` (ignora os restantes da colecção)."""
    global_normalizada = normalizar_global(doc_global)
    existentes = {str(e) for e in empresas_existentes}
    return [
        classificar(doc, global_normalizada, existentes)
        for doc in docs
        if e_documento_de_empresa(doc.get("_id"))
    ]


def resumir(veredictos: Iterable[Veredicto]) -> Resumo:
    resumo = Resumo()
    for v in veredictos:
        resumo.total += 1
        resumo.por_veredicto[v.veredicto] = resumo.por_veredicto.get(v.veredicto, 0) + 1
    return resumo


def a_apagar(veredictos: Iterable[Veredicto], *, incluir_sem_empresa: bool = False) -> list[Veredicto]:
    permitidos = set(APAGAVEIS_POR_OMISSAO)
    if incluir_sem_empresa:
        permitidos.add(VEREDICTO_SEM_EMPRESA)
    return [v for v in veredictos if v.veredicto in permitidos]
