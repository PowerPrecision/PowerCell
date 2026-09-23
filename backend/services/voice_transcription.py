"""
Transcrição de áudio (ASR) para as notas de voz do consultor — Épico 7, Eixo 2.

PORQUÊ ESTE MÓDULO EXISTE
-------------------------
O consultor sai de uma reunião com o cliente e quer registar o que ficou
combinado sem escrever. A nota de voz entra por aqui: este módulo converte
áudio em texto e **nada mais** — não conhece processos, tarefas nem base de
dados. Quem orquestra é ``voice_note_engine``.

SOBRE A PASTA ``skills/``
-------------------------
O repositório traz ``skills/ASR/`` com documentação e exemplos em TypeScript
para o ``z-ai-web-dev-sdk``. **Não é código importável por este backend**: é
TypeScript, o SDK não está instalado e nada no produto o referencia. O que
se reaproveita é o *contrato* que essa documentação descreve — um serviço
que recebe áudio e devolve texto, isolado do resto da aplicação. A
implementação real usa o cliente OpenAI que o PowerCell já tem configurado
em ``ai_document.get_openai_client``.

DEV NUNCA CHAMA UMA API PAGA
----------------------------
O ambiente local/dev opera com dados simulados. O *provider* é escolhido por
variável de ambiente e o valor por omissão é ``mock`` sempre que o ambiente
não é produção ou não há chave configurada — ver ``resolver_provider``. Um
programador que corra o CRM em casa vê o fluxo completo a funcionar sem
gastar um cêntimo nem enviar a voz de ninguém para fora.

VARIÁVEIS DE AMBIENTE
---------------------
``VOICE_ASR_PROVIDER``   ``openai`` | ``mock``  (omissão: automático)
``VOICE_ASR_MODEL``      modelo de transcrição  (omissão: ``whisper-1``)
``VOICE_ASR_TIMEOUT``    segundos até desistir  (omissão: ``120``)
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

PROVIDER_OPENAI = "openai"
PROVIDER_MOCK = "mock"
PROVIDERS_VALIDOS = frozenset({PROVIDER_OPENAI, PROVIDER_MOCK})

MODELO_ASR_OMISSAO = "whisper-1"
TIMEOUT_ASR_OMISSAO = 120.0

# Marcadores de ambiente de produção (mesma leitura que `scripts/env_guard`;
# duplicada de propósito para um serviço não depender da pasta de scripts).
_AMBIENTES_DE_PRODUCAO = frozenset({"production", "prod", "live"})

# Formatos que o browser grava (MediaRecorder → webm/ogg) mais os que um
# consultor pode carregar do telemóvel (m4a/mp3/wav).
FORMATOS_SUPORTADOS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}

# Transcrição devolvida pelo provider `mock`. É deliberadamente realista (um
# consultor a resumir uma reunião, com prazos e responsáveis) para que o
# fluxo de dev exercite o extractor a sério em vez de uma frase vazia.
TRANSCRICAO_SIMULADA = (
    "Acabei de sair da reunião com o cliente. Ficou combinado que ele envia "
    "os recibos de vencimento dos últimos três meses até sexta-feira. "
    "Tenho de pedir a avaliação do imóvel ao banco amanhã de manhã. "
    "O cliente está preocupado com a taxa e quer uma simulação com taxa fixa "
    "a trinta anos. Também é preciso confirmar com a mediadora a data da "
    "escritura, que deve ficar para o final do mês."
)


class ErroDeTranscricao(RuntimeError):
    """A transcrição falhou de forma que o chamador deve reportar."""


@dataclass(frozen=True)
class ResultadoTranscricao:
    """Texto transcrito e a proveniência de quem o produziu."""

    texto: str
    provider: str
    modelo: str

    def as_dict(self) -> dict:
        return {"texto": self.texto, "provider": self.provider, "modelo": self.modelo}


# ====================================================================
# FUNÇÕES PURAS (testáveis sem rede, sem Mongo, sem ficheiros)
# ====================================================================


def _normalizar(valor) -> str:
    return str(valor or "").strip().lower()


def ambiente_e_producao(ambiente=None) -> bool:
    """True quando ``ENVIRONMENT``/``APP_ENV`` declaram produção."""
    env = ambiente if ambiente is not None else os.environ
    return any(
        _normalizar(env.get(chave)) in _AMBIENTES_DE_PRODUCAO
        for chave in ("ENVIRONMENT", "APP_ENV")
    )


def resolver_provider(ambiente=None) -> str:
    """Decide que motor de transcrição usar.

    Regras, por ordem:
        1. ``VOICE_ASR_PROVIDER`` válido manda — inclusive para forçar
           ``mock`` em produção (útil numa demonstração) ou ``openai`` em
           dev (quem tiver chave e quiser testar a sério);
        2. um valor inválido é ignorado com aviso, nunca rebenta o arranque;
        3. sem variável: ``openai`` só se for produção **e** houver chave.
           Em qualquer outro caso, ``mock``.

    Falha fechada: na dúvida, simula — nunca envia áudio para fora.
    """
    env = ambiente if ambiente is not None else os.environ

    declarado = _normalizar(env.get("VOICE_ASR_PROVIDER"))
    if declarado:
        if declarado in PROVIDERS_VALIDOS:
            return declarado
        logger.warning(
            f"[NOTA-VOZ] VOICE_ASR_PROVIDER='{declarado}' desconhecido; "
            f"a usar '{PROVIDER_MOCK}'"
        )
        return PROVIDER_MOCK

    tem_chave = bool(
        (env.get("EMERGENT_LLM_KEY") or "").strip()
        or (env.get("OPENAI_API_KEY") or "").strip()
    )
    if ambiente_e_producao(env) and tem_chave:
        return PROVIDER_OPENAI
    return PROVIDER_MOCK


def resolver_modelo(ambiente=None) -> str:
    """Modelo de transcrição configurado (nunca hardcoded no chamador)."""
    env = ambiente if ambiente is not None else os.environ
    return (env.get("VOICE_ASR_MODEL") or "").strip() or MODELO_ASR_OMISSAO


def resolver_timeout(ambiente=None) -> float:
    """Segundos até desistir da transcrição.

    Um valor inválido ou não-positivo cai no valor por omissão: desligar o
    timeout deixaria um pedido pendurado a segurar uma tarefa para sempre.
    """
    env = ambiente if ambiente is not None else os.environ
    bruto = (env.get("VOICE_ASR_TIMEOUT") or "").strip()
    if not bruto:
        return TIMEOUT_ASR_OMISSAO
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        logger.warning(f"[NOTA-VOZ] VOICE_ASR_TIMEOUT='{bruto}' inválido")
        return TIMEOUT_ASR_OMISSAO
    return valor if valor > 0 else TIMEOUT_ASR_OMISSAO


def extensao_para_mime(mime_type: str) -> Optional[str]:
    """Extensão canónica de um mime de áudio suportado, ou ``None``."""
    # "audio/webm;codecs=opus" → "audio/webm" (o MediaRecorder anexa codecs).
    base = _normalizar(mime_type).split(";")[0].strip()
    return FORMATOS_SUPORTADOS.get(base)


def formato_suportado(mime_type: str) -> bool:
    """True se o mime corresponde a um formato de áudio que sabemos tratar."""
    return extensao_para_mime(mime_type) is not None


def nome_para_provider(filename: str, mime_type: str) -> str:
    """Nome de ficheiro com extensão coerente com o mime.

    O Whisper escolhe o desmultiplexador pela extensão do nome que recebe.
    Um blob do browser chega muitas vezes sem nome (ou como "blob"), e sem
    extensão a API devolve "Invalid file format" — daí esta normalização.
    """
    extensao = extensao_para_mime(mime_type) or ".webm"
    base = (filename or "").strip() or "nota-de-voz"
    if base.lower().endswith(extensao):
        return base
    return f"{base.rsplit('.', 1)[0] or 'nota-de-voz'}{extensao}"


# ====================================================================
# PROVIDERS
# ====================================================================


async def _transcrever_com_mock(conteudo: bytes) -> str:
    """Devolve uma transcrição simulada, sem tocar na rede.

    Recebe o conteúdo só para rejeitar um ficheiro vazio — um upload
    truncado deve falhar em dev exactamente como falharia em produção.
    """
    if not conteudo:
        raise ErroDeTranscricao("Áudio vazio")
    return TRANSCRICAO_SIMULADA


async def _transcrever_com_openai(
    conteudo: bytes,
    *,
    filename: str,
    mime_type: str,
    modelo: str,
    timeout: float,
) -> str:
    """Transcreve com a API de transcrições da OpenAI."""
    from services.ai_document import get_openai_client

    ficheiro = io.BytesIO(conteudo)
    ficheiro.name = nome_para_provider(filename, mime_type)

    cliente = get_openai_client()
    try:
        resposta = await asyncio.wait_for(
            cliente.audio.transcriptions.create(
                model=modelo,
                file=ficheiro,
                # O produto é português de Portugal; sem esta pista o modelo
                # troca por vezes para castelhano em gravações curtas.
                language="pt",
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as e:
        raise ErroDeTranscricao(
            f"A transcrição excedeu {timeout:.0f}s"
        ) from e
    except Exception as e:  # rede, chave inválida, quota, formato recusado
        raise ErroDeTranscricao(f"{type(e).__name__}: {e}") from e

    texto = getattr(resposta, "text", None)
    if texto is None and isinstance(resposta, dict):
        texto = resposta.get("text")
    return (texto or "").strip()


# ====================================================================
# FRONTEIRA PÚBLICA
# ====================================================================


async def transcrever_audio(
    conteudo: bytes,
    *,
    filename: str = "",
    mime_type: str = "",
    ambiente=None,
) -> ResultadoTranscricao:
    """Converte áudio em texto.

    Args:
        conteudo: Bytes do ficheiro de áudio.
        filename: Nome original (usado para a extensão enviada ao provider).
        mime_type: Tipo MIME declarado pelo browser.
        ambiente: Mapa de ambiente alternativo (testes).

    Returns:
        ``ResultadoTranscricao`` com o texto e a proveniência.

    Raises:
        ErroDeTranscricao: áudio vazio, formato recusado ou provider em
            baixo. O chamador decide o que fazer — aqui nunca se inventa
            uma transcrição para tapar um erro.
    """
    if not conteudo:
        raise ErroDeTranscricao("Áudio vazio")

    provider = resolver_provider(ambiente)
    modelo = resolver_modelo(ambiente)

    if provider == PROVIDER_MOCK:
        texto = await _transcrever_com_mock(conteudo)
        logger.info(
            f"[NOTA-VOZ] Transcrição simulada ({len(conteudo)} bytes) — "
            f"provider=mock"
        )
        return ResultadoTranscricao(texto=texto, provider=PROVIDER_MOCK, modelo="simulado")

    texto = await _transcrever_com_openai(
        conteudo,
        filename=filename,
        mime_type=mime_type,
        modelo=modelo,
        timeout=resolver_timeout(ambiente),
    )
    if not texto:
        raise ErroDeTranscricao("O motor de transcrição devolveu texto vazio")

    logger.info(
        f"[NOTA-VOZ] Transcrição concluída ({len(texto)} caracteres) — "
        f"provider={provider} modelo={modelo}"
    )
    return ResultadoTranscricao(texto=texto, provider=provider, modelo=modelo)
