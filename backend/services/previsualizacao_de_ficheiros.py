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

DESCARREGAR (`descarregar=True`, Out 2026)
------------------------------------------
O mesmo ficheiro, com `Content-Disposition: attachment` — o browser guarda-o em vez de o mostrar. Diferenças, todas
deliberadas: (1) qualquer extensão serve (uma descarga não executa nada no nosso contexto), e o que não está
na lista de pré-visualização sai como `application/octet-stream` — com `nosniff` o browser não adivinha outro;
(2) o tecto é maior (`MAX_BYTES_DO_DOWNLOAD`): é o ficheiro original, não uma imagem para desenhar num diálogo;
(3) o nome vem do registo, saneado para o cabeçalho (nunca uma quebra de linha: injecção de cabeçalhos).
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
import unicodedata
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
#: O tecto de uma DESCARGA (o ficheiro original, em blocos; o browser guarda-o em disco).
MAX_BYTES_DO_DOWNLOAD = 50 * 1024 * 1024
TIPO_GENERICO = "application/octet-stream"
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


def tipo_de_descarga(nome: Any) -> str:
    """O `Content-Type` de uma DESCARGA: o da pré-visualização, o que o nome diz, ou o genérico.

    Só ajuda o browser a escolher o programa que abre o ficheiro depois de guardado. Nunca é confiança:
    com `attachment` + `nosniff` nada é interpretado pelo browser, seja qual for o tipo declarado.
    """
    tipo = tipo_de_previsualizacao(nome)
    if tipo:
        return tipo
    adivinhado, _ = mimetypes.guess_type(_texto(nome))
    return adivinhado or TIPO_GENERICO


def nome_para_o_cabecalho(nome: Any) -> tuple[str, str]:
    """`(ascii, utf8_codificado)` de um nome de ficheiro, prontos para o `Content-Disposition`.

    Sem caminhos (`/`, `\\`), sem aspas nem caracteres de controlo (uma quebra de linha num cabeçalho é
    injecção de cabeçalhos), com um tecto de comprimento. O `ascii` é o recurso dos clientes antigos.
    """
    limpo = re.sub(r'[\x00-\x1f\x7f/\\"]', "_", _texto(nome).replace("\\", "/").rsplit("/", 1)[-1]).strip() or "ficheiro"
    limpo = limpo[:150]
    ascii_ = unicodedata.normalize("NFKD", limpo).encode("ascii", "ignore").decode("ascii").strip() or "ficheiro"
    return ascii_.replace("%", "_"), quote(limpo, safe="")


async def servir_ficheiro_do_s3(
    chave: str, nome: Any, *, referencia: str = "", tipo_pelo: Any = None, descarregar: bool = False
):
    """`StreamingResponse` da chave S3 (`inline`, ou `attachment` se `descarregar`), ou a `HTTPException` do caso.

    `referencia` é só para o log (um id do caso): a chave S3 nunca é registada. O tipo decide-se pelo
    `nome`, ou por `tipo_pelo` quando o nome mostrado não é o do que está na chave (um original
    `.jpg` cuja chave passou a ser o PDF limpo: o tipo é o do que SAI, não o do que se chamava).
    """
    from botocore.exceptions import BotoCoreError, ClientError
    from fastapi.responses import StreamingResponse

    from services.s3_storage import s3_service

    base_do_tipo = nome if tipo_pelo is None else tipo_pelo
    if descarregar:
        tipo = tipo_de_descarga(base_do_tipo)
    else:
        tipo = tipo_de_previsualizacao(base_do_tipo)
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
    tecto = MAX_BYTES_DO_DOWNLOAD if descarregar else MAX_BYTES_DA_PREVISUALIZACAO
    if tamanho > tecto:
        corpo.close()
        raise HTTPException(
            status_code=413,
            detail="O ficheiro é demasiado grande para descarregar por aqui." if descarregar
            else "O ficheiro é demasiado grande para pré-visualizar.",
        )

    ascii_, utf8 = nome_para_o_cabecalho(nome)
    disposicao = (
        f'attachment; filename="{ascii_}"; filename*=UTF-8\'\'{utf8}' if descarregar
        else f"inline; filename*=UTF-8''{quote(_texto(nome) or 'ficheiro', safe='')}"
    )

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
            "Content-Disposition": disposicao,
            "Content-Length": str(tamanho),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


__all__ = [
    "MAX_BYTES_DA_PREVISUALIZACAO",
    "MAX_BYTES_DO_DOWNLOAD",
    "TIPOS_COM_PREVISUALIZACAO",
    "nome_para_o_cabecalho",
    "servir_ficheiro_do_s3",
    "tipo_de_descarga",
    "tipo_de_previsualizacao",
]
