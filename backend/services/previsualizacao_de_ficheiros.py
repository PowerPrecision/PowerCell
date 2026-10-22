"""Servir um ficheiro do S3 para pré-visualizar DENTRO do ecrã (Out 2026): PDF e imagens.

Dois sítios usam isto — a gaveta «Ver Detalhes da Lead» e o «Ver documento» da pesquisa avançada do
Index — e as regras são as mesmas, por isso vivem num só lugar. **Quem chama já decidiu que o utilizador
pode ver este ficheiro** (fronteira de rede, posse da chave, papel): aqui só se decide COMO se serve.

* **Lista positiva por extensão** (`TIPOS_COM_PREVISUALIZACAO`): o `Content-Type` declarado sai daqui e
  não do que está no bucket; com `nosniff` o browser não adivinha outro. Word, Excel… → 415.
* **Tecto de tamanho** (`MAX_BYTES_DA_PREVISUALIZACAO`): o ecrã carrega o ficheiro inteiro. → 413.
* **Em blocos**: nunca o ficheiro inteiro em memória no servidor.
* **`private, no-store`**: são documentos de clientes; nada fica em caches partilhadas.
* **Erros que se podem dizer**: ausente → 404; S3 em baixo → 503. O erro do fornecedor nunca sai.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException

logger = logging.getLogger(__name__)

#: O que se pré-visualiza, por extensão. Lista POSITIVA e fechada.
TIPOS_COM_PREVISUALIZACAO = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
#: Acima disto não se serve (o ecrã carrega o ficheiro inteiro para o browser).
MAX_BYTES_DA_PREVISUALIZACAO = 15 * 1024 * 1024
TAMANHO_DO_BLOCO = 64 * 1024


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def tipo_de_previsualizacao(nome: Any) -> Optional[str]:
    """O `Content-Type` com que o ficheiro se pré-visualiza, ou ``None`` se não se consegue."""
    texto = _texto(nome).lower()
    for extensao, tipo in TIPOS_COM_PREVISUALIZACAO.items():
        if texto.endswith(extensao):
            return tipo
    return None


async def servir_ficheiro_do_s3(chave: str, nome: Any, *, referencia: str = "", tipo_pelo: Any = None):
    """`StreamingResponse` `inline` da chave S3, ou a `HTTPException` que o caso merece.

    `referencia` é só para o log (um id do caso): a chave S3 nunca é registada. O tipo decide-se pelo
    `nome`, ou por `tipo_pelo` quando o nome mostrado não é o do que está na chave (um original
    `.jpg` cuja chave passou a ser o PDF limpo: o tipo é o do que SAI, não o do que se chamava).
    """
    from botocore.exceptions import BotoCoreError, ClientError
    from fastapi.responses import StreamingResponse

    from services.s3_storage import s3_service

    tipo = tipo_de_previsualizacao(nome if tipo_pelo is None else tipo_pelo)
    if tipo is None:
        raise HTTPException(status_code=415, detail="Este tipo de ficheiro não tem pré-visualização.")
    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="Serviço de armazenamento indisponível.")

    try:
        resposta = await asyncio.to_thread(
            lambda: s3_service.s3_client.get_object(Bucket=s3_service.bucket_name, Key=chave)
        )
    except ClientError as exc:
        codigo = exc.response.get("Error", {}).get("Code", "")
        if codigo in ("NoSuchKey", "404", "NotFound"):
            raise HTTPException(status_code=404, detail="Ficheiro não encontrado.")
        logger.error("[PREVISUALIZACAO] erro S3 (%s) em %s", codigo, referencia)
        raise HTTPException(status_code=503, detail="Serviço de armazenamento indisponível.")
    except BotoCoreError:
        raise HTTPException(status_code=503, detail="Serviço de armazenamento indisponível.")

    tamanho = int(resposta.get("ContentLength") or 0)
    corpo = resposta["Body"]
    if tamanho > MAX_BYTES_DA_PREVISUALIZACAO:
        corpo.close()
        raise HTTPException(status_code=413, detail="O ficheiro é demasiado grande para pré-visualizar.")

    def blocos():
        try:
            while True:
                bloco = corpo.read(TAMANHO_DO_BLOCO)
                if not bloco:
                    break
                yield bloco
        finally:
            corpo.close()

    return StreamingResponse(
        blocos(),
        media_type=tipo,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(_texto(nome) or 'ficheiro', safe='')}",
            "Content-Length": str(tamanho),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


__all__ = [
    "MAX_BYTES_DA_PREVISUALIZACAO",
    "TIPOS_COM_PREVISUALIZACAO",
    "servir_ficheiro_do_s3",
    "tipo_de_previsualizacao",
]
