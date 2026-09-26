"""
Quarentena de conteúdo — validar os bytes DEPOIS de eles chegarem ao S3.

PORQUE É QUE ISTO EXISTE
========================
A parede de magic bytes (`services/file_validation.py`) diz de si própria que
"NUNCA se deve confiar apenas na extensão" e é chamada pelos uploads do CRM,
que passam pelo backend (`routes/documents.py`, `ai_bulk_analyze`,
`async_jobs_api_session`).

O Portal do Cliente **não pode** chamá-la no mesmo ponto, e não é distracção:
o upload é por URL pré-assinado, os bytes vão do browser DIRECTAMENTE para o
S3 e o backend nunca os vê. Foi para isso que o pré-assinado existe — foi
precisamente para tirar ficheiros de clientes do event loop (o mesmo motivo
pelo qual o `send_email` foi para `asyncio.to_thread`).

Consequência, até aqui: o cliente carregava o que quisesse (um `.exe`
renomeado, HTML com script, 5 GB) e o `file_size`/`content_type` gravados na
base de dados eram os que ele DECLAROU, nunca verificados.

A quarentena resolve isso sem abdicar do pré-assinado: depois do upload, e
ANTES de existir qualquer registo na base de dados, o backend faz um `HEAD`
(tamanho e tipo reais) e um `GET` com `Range: bytes=0-2047` (a assinatura),
e só cria o registo se os bytes forem o que dizem ser.

TRÊS DECISÕES QUE NÃO SE PODEM PERDER
=====================================

1. **O tamanho vem do `HEAD`, nunca da amostra.** O `validate_file_content`
   também verifica tamanho — mas a partir do `len()` do que lhe dermos, e nós
   damos-lhe 2 KB. Essa verificação é, no nosso caso, VÁCUA: 2 KB passa
   sempre. Se confiássemos nela, tínhamos uma parede que valida o tipo e
   carimba qualquer tamanho — um placebo. A amostra responde "o que é isto?";
   o `HEAD` responde "que tamanho tem?". Nenhuma das duas responde à
   pergunta da outra.

2. **Falha de infraestrutura NÃO é reprovação.** Se o `HEAD` ou o `GET`
   falharem (rede, credenciais, 5xx do S3), não sabemos o que lá está — e
   apagar o objecto por não o conseguirmos ler destruiria o upload legítimo
   de um cliente por causa de um soluço do S3. Esses casos são
   `transitorio=True` → **503, sem apagar**, e o cliente pode reconfirmar.
   Só uma reprovação de CONTEÚDO apaga.

3. **Reprovar é apagar E não gravar.** Apagar sem impedir o registo deixava
   um documento a apontar para o vazio; gravar sem apagar deixava o objecto
   mau no bucket, e os prefixos deste bucket são servidos por URLs
   pré-assinados. A ordem é: inspeccionar → (reprovado) apagar → 400; o
   registo só nasce a jusante, se se chegar lá.

O QUE ESTA PAREDE **NÃO** FAZ, E CONVÉM SABER
=============================================
Magic bytes provam o formato, não a inocência. Um `.docx`/`.xlsx` é um ZIP
(`PK\\x03\\x04`), pelo que um ZIP renomeado passa como documento Office — é o
limite do método, não um defeito desta implementação. Um PDF válido com
JavaScript dentro também passa: é um PDF. Quem quiser mais do que isto precisa
de antivírus/sandbox, que é outro lote e outra conversa.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException

from services.s3_storage import s3_service
from services.file_validation import (
    ALLOWED_MIME_TYPES,
    validate_file_content,
    sanitize_for_log,
)

logger = logging.getLogger(__name__)

# Quantos bytes chegam para a assinatura. As maiores que validamos têm 8
# bytes (PNG); 2 KB dá folga para wrappers e para o `libmagic` decidir com
# contexto, e continua a ser um `Range` desprezável face ao ficheiro.
BYTES_DE_INSPECCAO = 2048

# Tecto absoluto, independente do tipo. O `ALLOWED_MIME_TYPES` tem limites
# por tipo (o maior é 50 MB); este é a rede que apanha o que não tiver limite
# declarado, para nunca ficarmos sem nenhum.
TAMANHO_MAXIMO_MB = 50

MOTIVO_APROVADO = "aprovado"
MOTIVO_AUSENTE = "ausente"
MOTIVO_VAZIO = "vazio"
MOTIVO_GRANDE = "grande"
MOTIVO_CONTEUDO = "conteudo"
MOTIVO_ILEGIVEL = "ilegivel"

# Motivos que NÃO são culpa do conteúdo — não apagam o objecto.
MOTIVOS_TRANSITORIOS = (MOTIVO_ILEGIVEL,)


@dataclass(frozen=True)
class Veredicto:
    """O resultado da inspecção, em dados e não em excepções.

    A função devolve isto em vez de levantar directamente para que o
    chamador possa decidir o que fazer (apagar? gravar? que código?) com o
    quadro completo à frente — e para que o veredicto seja testável sem
    apanhar excepções.
    """

    aprovado: bool
    motivo: str
    detalhe: str
    tamanho: Optional[int] = None
    tipo_detectado: Optional[str] = None
    tipo_declarado_s3: Optional[str] = None

    @property
    def transitorio(self) -> bool:
        """`True` quando a reprovação é da infraestrutura e não do ficheiro.

        É esta propriedade que impede a quarentena de apagar o upload
        legítimo de um cliente quando o S3 tem um soluço.
        """
        return self.motivo in MOTIVOS_TRANSITORIOS

    @property
    def codigo_http(self) -> int:
        if self.aprovado:
            return 200
        return 503 if self.transitorio else 400


def limite_em_bytes(tipo_detectado: Optional[str]) -> int:
    """Tecto de tamanho para este tipo, em bytes.

    Sai do MESMO `ALLOWED_MIME_TYPES` que a parede do CRM usa — duplicar
    aqui uma tabela de limites era garantir que as duas divergiriam. Um tipo
    sem limite declarado cai no tecto absoluto, nunca em "sem limite".
    """
    config = ALLOWED_MIME_TYPES.get(tipo_detectado or "", {})
    megabytes = config.get("max_size_mb") or TAMANHO_MAXIMO_MB
    return int(megabytes) * 1024 * 1024


def _tamanho_legivel(bytes_: Optional[int]) -> str:
    """Tamanho para humanos — em bytes quando é pequeno.

    Um "0.0 MB" num log de segurança sobre um ficheiro de 192 bytes esconde
    exactamente o número que interessa a quem está a investigar.
    """
    if bytes_ is None:
        return "tamanho desconhecido"
    if bytes_ < 1024:
        return f"{bytes_} bytes"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.1f} KB"
    return f"{bytes_ / (1024 * 1024):.1f} MB"


def avaliar_amostra(
    amostra: Optional[bytes],
    *,
    filename: str,
    tamanho_real: Optional[int],
    tipo_declarado_s3: Optional[str] = None,
) -> Veredicto:
    """Decide o veredicto a partir da amostra e do tamanho REAL. Puro.

    Separado do I/O de propósito: é aqui que vive toda a decisão, e é isto
    que se testa sem S3 nenhum. `tamanho_real` vem do `HEAD`; a `amostra`
    são os primeiros bytes.
    """
    if amostra is None:
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_ILEGIVEL,
            detalhe=(
                "Não foi possível verificar o ficheiro neste momento. "
                "Aguarde um instante e tente novamente."
            ),
            tamanho=tamanho_real,
            tipo_declarado_s3=tipo_declarado_s3,
        )

    if not amostra:
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_VAZIO,
            detalhe="O ficheiro está vazio. Verifique o ficheiro e envie novamente.",
            tamanho=tamanho_real or 0,
            tipo_declarado_s3=tipo_declarado_s3,
        )

    # O `validate_file_content` sinaliza reprovação levantando `HTTPException`
    # (é o que serve os endpoints do CRM). Aqui queremos o veredicto como
    # dados, por isso apanha-se e traduz-se — a MENSAGEM dele é reaproveitada
    # tal e qual, para o cliente do Portal ler exactamente o mesmo texto que
    # um utilizador do CRM leria para o mesmo ficheiro.
    #
    # NOTA: não se passa `max_size_mb` de propósito. Ele compararia contra o
    # `len()` da AMOSTRA (2 KB), o que passa sempre; o tamanho é verificado
    # em baixo, contra o valor do `HEAD`.
    try:
        _, tipo_detectado, _ = validate_file_content(amostra, filename)
    except HTTPException as recusa:
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_CONTEUDO,
            detalhe=str(recusa.detail),
            tamanho=tamanho_real,
            tipo_declarado_s3=tipo_declarado_s3,
        )
    except Exception as erro:
        # Um `libmagic` em falta no sistema é um problema NOSSO, não um
        # ficheiro mau: falha fechada, mas como transitória — não se apaga
        # o ficheiro do cliente por causa de uma dependência nossa.
        logger.error(
            "[QUARENTENA] Erro inesperado a validar %s: %s: %s",
            sanitize_for_log(filename), type(erro).__name__, erro,
        )
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_ILEGIVEL,
            detalhe=(
                "Não foi possível verificar o ficheiro neste momento. "
                "Aguarde um instante e tente novamente."
            ),
            tamanho=tamanho_real,
            tipo_declarado_s3=tipo_declarado_s3,
        )

    # O tamanho, agora sim, contra o valor REAL do objecto.
    limite = limite_em_bytes(tipo_detectado)
    if tamanho_real is not None and tamanho_real > limite:
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_GRANDE,
            detalhe=(
                f"Ficheiro demasiado grande ({_tamanho_legivel(tamanho_real)}). "
                f"O máximo permitido para este tipo é {_tamanho_legivel(limite)}."
            ),
            tamanho=tamanho_real,
            tipo_detectado=tipo_detectado,
            tipo_declarado_s3=tipo_declarado_s3,
        )

    return Veredicto(
        aprovado=True,
        motivo=MOTIVO_APROVADO,
        detalhe="",
        tamanho=tamanho_real,
        tipo_detectado=tipo_detectado,
        tipo_declarado_s3=tipo_declarado_s3,
    )


async def inspeccionar(file_key: str, *, filename: str) -> Veredicto:
    """Lê os metadados e a amostra do S3 e devolve o veredicto. Não apaga.

    **Todo o I/O do `boto3` vai por `asyncio.to_thread`.** O `boto3` é
    síncrono: chamá-lo de uma corotina pára o event loop do worker INTEIRO
    enquanto a rede não responder — é o incidente do `smtplib` outra vez, com
    outro nome. São dois saltos de thread por upload, e não mais: um `HEAD` e
    um `Range` de 2 KB.
    """
    estado, metadados = await asyncio.to_thread(
        s3_service.head_object_metadata, file_key
    )

    if estado == "ausente":
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_AUSENTE,
            detalhe=(
                "Ficheiro não encontrado. O upload pode ter falhado. "
                "Tente novamente."
            ),
        )

    if estado != "ok" or metadados is None:
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_ILEGIVEL,
            detalhe=(
                "Não foi possível verificar o ficheiro neste momento. "
                "Aguarde um instante e tente novamente."
            ),
        )

    tamanho_real = metadados.get("tamanho")
    tipo_declarado_s3 = metadados.get("tipo")

    # Um objecto absurdamente grande é reprovado SEM se lerem os bytes: o
    # tamanho já o condena, e ler 2 KB de um ficheiro de 5 GB para chegar à
    # mesma conclusão é trabalho a mais.
    if tamanho_real is not None and tamanho_real > TAMANHO_MAXIMO_MB * 1024 * 1024:
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_GRANDE,
            detalhe=(
                f"Ficheiro demasiado grande ({_tamanho_legivel(tamanho_real)}). "
                f"O máximo permitido é {TAMANHO_MAXIMO_MB} MB."
            ),
            tamanho=tamanho_real,
            tipo_declarado_s3=tipo_declarado_s3,
        )

    if tamanho_real == 0:
        return Veredicto(
            aprovado=False,
            motivo=MOTIVO_VAZIO,
            detalhe="O ficheiro está vazio. Verifique o ficheiro e envie novamente.",
            tamanho=0,
            tipo_declarado_s3=tipo_declarado_s3,
        )

    amostra = await asyncio.to_thread(
        s3_service.get_object_prefix, file_key, BYTES_DE_INSPECCAO
    )

    return avaliar_amostra(
        amostra,
        filename=filename,
        tamanho_real=tamanho_real,
        tipo_declarado_s3=tipo_declarado_s3,
    )


async def apagar_reprovado(file_key: str) -> bool:
    """Apaga do S3 um objecto reprovado. Nunca propaga.

    Falhar a apagar não pode transformar-se num erro diferente do que o
    cliente tem de ler: a recusa mantém-se, o registo continua a não nascer,
    e fica um objecto órfão no bucket — registado a `error` porque é preciso
    alguém ir buscá-lo, não porque o pedido tenha corrido de outra maneira.
    """
    try:
        apagado = await asyncio.to_thread(s3_service.delete_file, file_key)
    except Exception as erro:
        logger.error(
            "[QUARENTENA] Excepção ao apagar %s: %s: %s",
            file_key, type(erro).__name__, erro,
        )
        return False

    if not apagado:
        logger.error(
            "[QUARENTENA] ÓRFÃO: o ficheiro reprovado %s NÃO foi apagado do "
            "S3. O registo não foi criado, mas o objecto ficou no bucket.",
            file_key,
        )
    return apagado


async def exigir_conteudo_valido(file_key: str, *, filename: str) -> Veredicto:
    """Inspecciona e, se reprovar, apaga e levanta. Devolve o veredicto se passar.

    É este o ponto único a chamar de um `confirm-upload`: garante que, quando
    devolve, o objecto foi visto e aprovado — e que, quando levanta, já não
    está no bucket (excepto reprovação transitória, que não apaga nada).
    """
    veredicto = await inspeccionar(file_key, filename=filename)

    if veredicto.aprovado:
        logger.info(
            "[QUARENTENA] Aprovado: %s (%s, %s)",
            sanitize_for_log(filename), veredicto.tipo_detectado, _tamanho_legivel(veredicto.tamanho),
        )
        return veredicto

    if veredicto.transitorio:
        # Sem apagar: não sabemos o que lá está, e a dúvida não condena o
        # ficheiro do cliente.
        logger.warning(
            "[QUARENTENA] Inconclusivo (%s) para %s — objecto MANTIDO; "
            "o cliente pode reconfirmar.",
            veredicto.motivo, sanitize_for_log(filename),
        )
        raise HTTPException(status_code=503, detail=veredicto.detalhe)

    if veredicto.motivo == MOTIVO_AUSENTE:
        # Não há nada para apagar.
        raise HTTPException(status_code=400, detail=veredicto.detalhe)

    logger.warning(
        "[QUARENTENA] REPROVADO (%s): %s (declarado pelo S3: %s, %s) — "
        "objecto apagado, registo não criado.",
        veredicto.motivo,
        sanitize_for_log(filename),
        veredicto.tipo_declarado_s3,
        _tamanho_legivel(veredicto.tamanho),
    )
    await apagar_reprovado(file_key)
    raise HTTPException(status_code=400, detail=veredicto.detalhe)
