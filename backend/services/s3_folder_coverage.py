"""Cobertura do mapeamento pasta S3 ↔ processo (Épico 10, Gestor S3, Passo 2).

PORQUE É QUE ISTO SE MEDE ANTES DE ISOLAR
=========================================
O isolamento por rede do Explorador resolve-se assim: pasta →
`processes.s3_folder` → `processes.network_id`. Uma pasta sem processo que
aponte para ela não tem rede, e **falha fechada**: fica invisível para toda a
gente excepto admin/CEO.

Isso é a decisão certa em segurança e pode ser péssima em produto. Se metade
do bucket estiver por mapear, reabrir a página a utilizadores normais dá-lhes
uma página quase vazia — e a culpa pareceria do isolamento, quando é do
mapeamento. Por isso mede-se PRIMEIRO, e a decisão sobre as órfãs é de quem
conhece o negócio.

OS QUATRO NÚMEROS QUE IMPORTAM
------------------------------
* **pastas no S3** — o denominador real, não o que a base de dados julga.
* **mapeadas** — pastas com pelo menos um processo a apontar-lhes.
* **órfãs** — pastas que nenhum processo reclama. Invisíveis após o Passo 3.
* **ambíguas** — pastas reclamadas por processos de REDES diferentes. Estas
  nunca podem ser mostradas a nenhuma das redes; são as mais perigosas e
  costumam ser as menos numerosas.

E ainda as **ligações partidas**: processos cujo `s3_folder` aponta para uma
pasta que já não existe no S3 — tipicamente um `rename` feito no Explorador,
que move os objectos e não actualiza o mapeamento.

Este módulo é a lógica, testável sem S3 nem Mongo vivos. O script
`scripts/medir_cobertura_s3.py` é a casca que o corre contra o ambiente real.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR

logger = logging.getLogger(__name__)

CAMPO_REDE = "network_id"


@dataclass
class Cobertura:
    """O retrato do bucket, em números e em exemplos."""

    pastas_no_s3: int = 0
    mapeadas: int = 0
    orfas: list[str] = field(default_factory=list)
    ambiguas: list[str] = field(default_factory=list)
    ligacoes_partidas: list[str] = field(default_factory=list)
    processos_totais: int = 0
    processos_com_pasta: int = 0
    # Órfãs que um backfill por nome conseguiria resolver sem adivinhar.
    orfas_resoluveis: dict[str, str] = field(default_factory=dict)

    @property
    def percentagem_mapeada(self) -> float:
        if not self.pastas_no_s3:
            return 0.0
        return round(100.0 * self.mapeadas / self.pastas_no_s3, 1)


def nome_da_pasta(caminho: str) -> str:
    """Último segmento de um caminho de pasta de cliente."""
    return (caminho or "").rstrip("/").split("/")[-1]


def normalizar_para_comparacao(nome: str) -> str:
    """Forma canónica de um nome, para casar pasta com cliente.

    `sanitize_folder_name` remove acentos e troca espaços por `_`, mas fá-lo
    na ALTURA da criação: nomes gravados em épocas diferentes divergem na
    capitalização e nos acentos. Comparar em minúsculas e sem diacríticos é
    o mínimo para não perder correspondências óbvias — e o backfill continua
    a recusar-se a escolher quando há mais de um candidato.
    """
    texto = unicodedata.normalize("NFKD", nome or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s-]", "", texto)
    texto = re.sub(r"[\s_]+", "_", texto.strip())
    return texto.lower()


def _redes_do_grupo(processos: Iterable[dict]) -> set[str]:
    redes = set()
    for p in processos:
        rede = (p.get(CAMPO_REDE) or "").strip()
        if rede:
            redes.add(rede)
    return redes


def analisar(
    pastas_do_s3: Iterable[str],
    processos: Iterable[dict],
) -> Cobertura:
    """Cruza o que existe no S3 com o que a base de dados reclama.

    Args:
        pastas_do_s3: caminhos completos das pastas de cliente.
        processos: documentos com pelo menos ``id``, ``s3_folder``,
            ``network_id`` e ``client_name``.
    """
    pastas = [p.rstrip("/") for p in pastas_do_s3 if p]
    existentes = set(pastas)

    processos = list(processos)
    reclamacoes: dict[str, list[dict]] = {}
    for p in processos:
        pasta = (p.get("s3_folder") or "").rstrip("/")
        if pasta:
            reclamacoes.setdefault(pasta, []).append(p)

    cobertura = Cobertura(
        pastas_no_s3=len(pastas),
        processos_totais=len(processos),
        processos_com_pasta=sum(1 for p in processos if (p.get("s3_folder") or "").strip()),
    )

    for pasta in pastas:
        donos = reclamacoes.get(pasta) or []
        if not donos:
            cobertura.orfas.append(pasta)
            continue
        cobertura.mapeadas += 1
        # Uma pasta reclamada por redes diferentes não pode ser mostrada a
        # nenhuma delas: mostrar à "primeira" seria escolher uma rede à
        # sorte para ver os documentos da outra.
        if len(_redes_do_grupo(donos)) > 1:
            cobertura.ambiguas.append(pasta)

    for pasta in reclamacoes:
        if pasta not in existentes:
            cobertura.ligacoes_partidas.append(pasta)

    cobertura.orfas_resoluveis = _propor_correspondencias(
        cobertura.orfas, processos, reclamadas=set(reclamacoes)
    )
    return cobertura


def _propor_correspondencias(
    orfas: Iterable[str],
    processos: Iterable[dict],
    *,
    reclamadas: set[str],
) -> dict[str, str]:
    """Para cada órfã, o ÚNICO processo cujo nome de cliente lhe corresponde.

    Recusa-se a escolher quando há mais do que um candidato — a mesma regra
    do `rede_consensual` do Lote 4. Um mapeamento errado torna a pasta
    visível à rede errada, e a execução seguinte aceitá-lo-ia como verdade.
    """
    por_nome: dict[str, list[dict]] = {}
    for p in processos:
        if (p.get("s3_folder") or "").strip():
            continue  # já tem pasta; não se rouba um mapeamento existente
        chave = normalizar_para_comparacao(p.get("client_name") or "")
        if chave:
            por_nome.setdefault(chave, []).append(p)

    propostas: dict[str, str] = {}
    for pasta in orfas:
        if pasta in reclamadas:
            continue
        candidatos = por_nome.get(normalizar_para_comparacao(nome_da_pasta(pasta))) or []
        if len(candidatos) == 1:
            propostas[pasta] = candidatos[0].get("id") or ""
    return {k: v for k, v in propostas.items() if v}


def formatar_relatorio(c: Cobertura) -> str:
    """Relatório legível — é isto que se leva à decisão sobre as órfãs."""
    linhas = [
        "",
        "═" * 62,
        f"  COBERTURA DO MAPEAMENTO — {RAIZ_DO_EXPLORADOR}/",
        "═" * 62,
        f"  Pastas no S3 .............. {c.pastas_no_s3}",
        f"  Mapeadas .................. {c.mapeadas}  ({c.percentagem_mapeada}%)",
        f"  ÓRFÃS (ficam invisíveis) .. {len(c.orfas)}",
        f"    das quais resolúveis .... {len(c.orfas_resoluveis)}",
        f"  AMBÍGUAS (>1 rede) ........ {len(c.ambiguas)}",
        "",
        f"  Processos ................. {c.processos_totais}",
        f"    com s3_folder ........... {c.processos_com_pasta}",
        f"  Ligações partidas ......... {len(c.ligacoes_partidas)}",
        "═" * 62,
    ]
    if c.ambiguas:
        linhas += ["", "  AMBÍGUAS (nenhuma rede as pode ver):"]
        linhas += [f"    - {p}" for p in c.ambiguas[:10]]
    if c.orfas:
        linhas += ["", "  Exemplos de órfãs:"]
        linhas += [f"    - {p}" for p in c.orfas[:10]]
    if c.ligacoes_partidas:
        linhas += ["", "  Ligações partidas (pasta já não existe no S3):"]
        linhas += [f"    - {p}" for p in c.ligacoes_partidas[:10]]
    return "\n".join(linhas) + "\n"
