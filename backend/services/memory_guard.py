"""
Disciplina de MEMÓRIA do processo Worker (limite de 512 MB no Render).

O `powercell-worker` morria por OOM. O que o enchia não era uma fuga: eram picos
sobrepostos — o email inteiro em bytes, a árvore MIME parseada, cada anexo descodificado só
para lhe medir o tamanho, as quatro pastas IMAP (Inbox, Enviados, Rascunhos, Lixo) em memória
ao mesmo tempo, um laço de fila e o agendador a trabalhar em simultâneo, quatro threads IMAP e
um `gather` sobre até 200 caixas. Este módulo é o ponto único dos botões:

  · `IMAP_BATCH_SIZE`          — emails por lote (omissão 20);
  · `IMAP_MAX_EMAIL_BYTES`     — acima disto o email é saltado, com aviso (omissão 15 MB);
  · `EMAIL_EXECUTOR_WORKERS`   — threads IMAP (omissão 4; o worker põe 1);
  · `WORKER_MAX_CONCURRENCY`   — trabalhos pesados em simultâneo no worker (omissão 1);
  · `IMAP_SYNC_CONCURRENCY`    — caixas sincronizadas em simultâneo (omissão 2).

Valores inválidos, zero ou negativos caem na omissão — nunca desligam um tecto.
"""
from __future__ import annotations

import gc
import logging
import os
from typing import Any, Iterator, Optional, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

OMISSAO_LOTE_IMAP = 20
OMISSAO_EMAIL_MAXIMO = 15 * 1024 * 1024
OMISSAO_THREADS_IMAP = 4
OMISSAO_CONCORRENCIA_WORKER = 1
OMISSAO_CONCORRENCIA_SYNC = 2


def inteiro_do_ambiente(nome: str, omissao: int, minimo: int = 1) -> int:
    """Lê um inteiro do ambiente. Inválido ou abaixo do mínimo: a omissão."""
    bruto = (os.environ.get(nome) or "").strip()
    if not bruto:
        return omissao
    try:
        valor = int(bruto)
    except ValueError:
        logger.warning("%s=%r não é um inteiro: a usar %d", nome, bruto, omissao)
        return omissao
    if valor < minimo:
        logger.warning("%s=%d abaixo do mínimo %d: a usar %d", nome, valor, minimo, omissao)
        return omissao
    return valor


def tamanho_do_lote_imap() -> int:
    return inteiro_do_ambiente("IMAP_BATCH_SIZE", OMISSAO_LOTE_IMAP)


def tamanho_maximo_do_email() -> int:
    return inteiro_do_ambiente("IMAP_MAX_EMAIL_BYTES", OMISSAO_EMAIL_MAXIMO, minimo=64 * 1024)


def threads_imap() -> int:
    return inteiro_do_ambiente("EMAIL_EXECUTOR_WORKERS", OMISSAO_THREADS_IMAP)


def concorrencia_do_worker() -> int:
    return inteiro_do_ambiente("WORKER_MAX_CONCURRENCY", OMISSAO_CONCORRENCIA_WORKER)


def concorrencia_da_sincronizacao() -> int:
    return inteiro_do_ambiente("IMAP_SYNC_CONCURRENCY", OMISSAO_CONCORRENCIA_SYNC)


def em_lotes(sequencia: Sequence[T], tamanho: Optional[int] = None) -> Iterator[Sequence[T]]:
    """Fatias consecutivas de `tamanho` elementos (o último pode ser menor)."""
    n = max(1, int(tamanho or tamanho_do_lote_imap()))
    for inicio in range(0, len(sequencia), n):
        yield sequencia[inicio:inicio + n]


def libertar_memoria() -> int:
    """`gc.collect()` + devolve ao sistema as páginas livres do alocador (glibc), se der.

    O `gc.collect()` sozinho apanha os ciclos (a árvore MIME tem-nos) mas o alocador do CPython
    não devolve ao SO a memória de blocos grandes libertados; `malloc_trim` faz isso e é o que
    baixa o RSS que o Render mede. Nunca levanta.
    """
    recolhidos = gc.collect()
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:  # noqa: BLE001 — fora de Linux/glibc não há nada a fazer
        pass
    return recolhidos


def tamanho_do_anexo(parte: Any) -> int:
    """Tamanho aproximado de uma parte MIME SEM a descodificar.

    `get_payload(decode=True)` aloca uma cópia descodificada do anexo inteiro só para lhe fazer
    `len()` — com um PDF de 10 MB são 10 MB de pico por anexo. Em base64 o tamanho sai do
    comprimento do texto (3/4, menos o enchimento); nos outros casos o texto cru.
    """
    try:
        bruto = parte.get_payload()
    except Exception:  # noqa: BLE001
        return 0
    if isinstance(bruto, (list, tuple)):  # multipart/message — não é um anexo "folha"
        return 0
    if isinstance(bruto, bytes):
        return len(bruto)
    texto = str(bruto or "")
    codificacao = str(parte.get("Content-Transfer-Encoding", "")).strip().lower()
    if codificacao == "base64":
        limpo = len(texto.replace("\r", "").replace("\n", ""))
        enchimento = texto.rstrip().count("=") if texto.rstrip().endswith("=") else 0
        return max(0, (limpo * 3) // 4 - min(enchimento, 2))
    return len(texto)
