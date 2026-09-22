"""
Extracção de acções a partir da transcrição de uma nota de voz — Épico 7, Eixo 2.

O QUE FAZ
---------
Recebe texto (o que o consultor disse) e devolve estrutura:

    {
      "resumo_timeline": "...",                      # entra no histórico
      "tarefas_extraidas": [                          # entram em `db.tasks`
        {"titulo": "...", "descricao": "...",
         "due_date": "2026-09-26T09:00:00+00:00" | None,
         "prioridade": "Alta" | "Média" | "Baixa"}
      ]
    }

SOBRE A PASTA ``skills/``
-------------------------
Vale aqui o mesmo que em ``voice_transcription``: ``skills/LLM/`` é
documentação TypeScript de um SDK que este backend não tem. O que se
reaproveita é o contrato — um serviço de chat com *system prompt* rigoroso e
saída estruturada — implementado sobre o cliente OpenAI que o PowerCell já
usa, com o modelo a vir da configuração de IA do painel de administração
(``ai_page_analyzer.get_ai_config``), nunca fixo no código.

PORQUE É QUE METADE DESTE MÓDULO É PURA
---------------------------------------
Um LLM devolve texto, não garantias. Envolve o JSON em cercas ```` ```json ````,
acrescenta uma frase de cortesia antes, trunca a meio quando bate no limite
de *tokens*, inventa o campo ``data`` em vez de ``data_sugerida`` e escreve
"sexta-feira" onde se pediu uma data ISO. Todo esse trabalho sujo vive em
funções puras (``parse_extraction_payload``, ``resolver_data_relativa``,
``normalizar_extraccao``) que se testam sem rede e sem base de dados — e é
aí que estão os bugs reais, não na chamada HTTP.

NUNCA ADIVINHA
--------------
Uma expressão temporal que não se saiba resolver com segurança dá
``due_date: None``. Uma tarefa com um prazo errado é pior do que uma tarefa
sem prazo: o consultor confia nela.

VARIÁVEIS DE AMBIENTE
---------------------
``VOICE_LLM_PROVIDER``  ``openai`` | ``mock``  (omissão: igual ao ASR)
``VOICE_LLM_MODEL``     modelo a usar; se ausente, vem de `get_ai_config`
``VOICE_LLM_TIMEOUT``   segundos até desistir (omissão: ``90``)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

PROVIDER_OPENAI = "openai"
PROVIDER_MOCK = "mock"
PROVIDERS_VALIDOS = frozenset({PROVIDER_OPENAI, PROVIDER_MOCK})

# Chave da tarefa no painel de IA (admin escolhe o modelo por tarefa).
CHAVE_AI_CONFIG = "voice_note_extraction"
MODELO_OMISSAO = "gpt-4o-mini"
TIMEOUT_OMISSAO = 90.0

# Limites de sanidade. Um LLM a delirar não pode encher a lista de tarefas
# do consultor nem a timeline do processo.
MAX_TAREFAS = 10
MAX_TITULO = 200
MAX_DESCRICAO = 1000
MAX_RESUMO = 1500

PRIORIDADES = ("Alta", "Média", "Baixa")
PRIORIDADE_OMISSAO = "Média"

# Hora atribuída a um prazo que veio só como dia ("sexta-feira").
HORA_OMISSAO = 9
HORA_MANHA = 9
HORA_TARDE = 15

SYSTEM_PROMPT = (
    "És o assistente de um consultor de crédito habitação em Portugal. "
    "Recebes a transcrição de uma nota de voz gravada por ele depois de "
    "falar com um cliente e devolves APENAS um objecto JSON válido, sem "
    "texto antes ou depois e sem blocos de código.\n\n"
    "Formato obrigatório:\n"
    "{\n"
    '  "resumo_timeline": "string",\n'
    '  "tarefas_extraidas": [\n'
    '    {"titulo": "string", "descricao": "string", '
    '"data_sugerida": "string ou null", "prioridade": "Alta|Média|Baixa"}\n'
    "  ]\n"
    "}\n\n"
    "Regras:\n"
    "1. Escreve em português de Portugal, sem gerúndios brasileiros.\n"
    "2. `resumo_timeline` é um parágrafo objectivo, na terceira pessoa, com "
    "o que ficou decidido. Não inventes factos que não estejam na "
    "transcrição e não repitas a transcrição palavra por palavra.\n"
    "3. `tarefas_extraidas` contém SÓ acções concretas com responsável "
    "implícito no consultor ou no cliente. Uma opinião, um receio ou um "
    "comentário não é uma tarefa. Se não houver acções, devolve [].\n"
    "4. `titulo` é imperativo e curto (máximo 12 palavras): "
    '"Pedir avaliação do imóvel ao banco".\n'
    "5. `data_sugerida`: usa o formato ISO (AAAA-MM-DD) quando a data for "
    "dedutível sem ambiguidade; caso contrário devolve a expressão original "
    '("sexta-feira", "amanhã de manhã"). Se não houver qualquer referência '
    "temporal, devolve null. NUNCA inventes uma data.\n"
    "6. `prioridade`: Alta só quando a transcrição transmitir urgência "
    "explícita ou um prazo dentro de 48 horas."
)


class ErroDeExtraccao(RuntimeError):
    """O modelo não devolveu nada de aproveitável."""


# ====================================================================
# CONFIGURAÇÃO (pura)
# ====================================================================


def _normalizar(valor) -> str:
    return str(valor or "").strip().lower()


def resolver_provider(ambiente=None) -> str:
    """Motor de extracção a usar.

    ``VOICE_LLM_PROVIDER`` manda; sem ele, segue a mesma decisão do ASR
    (``voice_transcription.resolver_provider``) para que dev não tenha um
    passo simulado e outro real — ou é tudo simulado, ou é tudo verdadeiro.
    """
    env = ambiente if ambiente is not None else os.environ

    declarado = _normalizar(env.get("VOICE_LLM_PROVIDER"))
    if declarado:
        if declarado in PROVIDERS_VALIDOS:
            return declarado
        logger.warning(
            f"[NOTA-VOZ] VOICE_LLM_PROVIDER='{declarado}' desconhecido; "
            f"a usar '{PROVIDER_MOCK}'"
        )
        return PROVIDER_MOCK

    from services.voice_transcription import resolver_provider as provider_asr

    return provider_asr(env)


def resolver_timeout(ambiente=None) -> float:
    """Segundos até desistir da extracção (inválido → omissão)."""
    env = ambiente if ambiente is not None else os.environ
    bruto = (env.get("VOICE_LLM_TIMEOUT") or "").strip()
    if not bruto:
        return TIMEOUT_OMISSAO
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        logger.warning(f"[NOTA-VOZ] VOICE_LLM_TIMEOUT='{bruto}' inválido")
        return TIMEOUT_OMISSAO
    return valor if valor > 0 else TIMEOUT_OMISSAO


async def resolver_modelo(ambiente=None) -> str:
    """Modelo do LLM: variável de ambiente → painel de IA → omissão."""
    env = ambiente if ambiente is not None else os.environ

    declarado = (env.get("VOICE_LLM_MODEL") or "").strip()
    if declarado:
        return declarado

    try:
        from services.ai_page_analyzer import get_ai_config

        config = await get_ai_config()
        modelo = (config or {}).get(CHAVE_AI_CONFIG)
        if modelo:
            return str(modelo)
    except Exception as e:  # painel indisponível não pode parar a nota
        logger.warning(f"[NOTA-VOZ] Configuração de IA indisponível: {e}")

    return MODELO_OMISSAO


# ====================================================================
# PROMPT (puro)
# ====================================================================


def build_user_prompt(transcricao: str, *, contexto: Optional[dict] = None) -> str:
    """Monta a mensagem do utilizador com a transcrição e o contexto.

    O contexto (cliente, referência do processo, data de hoje) faz o modelo
    resolver "sexta-feira" e tratar o cliente pelo nome em vez de escrever
    "o cliente" em todas as frases.
    """
    contexto = contexto or {}
    linhas = []

    hoje = contexto.get("hoje")
    if hoje:
        linhas.append(f"Data de hoje: {hoje}")
    if contexto.get("process_ref"):
        linhas.append(f"Processo: {contexto['process_ref']}")
    if contexto.get("client_name"):
        linhas.append(f"Cliente: {contexto['client_name']}")
    if contexto.get("consultor_name"):
        linhas.append(f"Consultor: {contexto['consultor_name']}")

    cabecalho = "\n".join(linhas)
    if cabecalho:
        cabecalho = f"{cabecalho}\n\n"

    return f"{cabecalho}Transcrição da nota de voz:\n\"\"\"\n{transcricao}\n\"\"\""


# ====================================================================
# PARSING DA RESPOSTA (puro)
# ====================================================================


def _extrair_bloco_json(bruto: str) -> Optional[str]:
    """Isola o objecto JSON dentro de texto livre.

    Cobre os três hábitos do modelo: cercas ```` ```json ````, uma frase de
    cortesia antes do objecto, e ambos ao mesmo tempo.
    """
    texto = (bruto or "").strip()
    if not texto:
        return None

    # Cercas de código, com ou sem etiqueta de linguagem.
    cerca = re.search(r"```(?:json)?\s*(.+?)\s*```", texto, re.DOTALL | re.IGNORECASE)
    if cerca:
        texto = cerca.group(1).strip()

    # Tentar o documento inteiro primeiro. Sem isto, uma resposta que seja
    # um ARRAY de tarefas (`[{"titulo": ...}]`) seria "salva" pela varredura
    # abaixo, que devolveria o primeiro objecto de dentro da lista como se
    # fosse o payload — uma tarefa interpretada como extracção, em silêncio.
    try:
        completo = json.loads(texto)
    except json.JSONDecodeError:
        completo = None
    if completo is not None:
        return texto if isinstance(completo, dict) else None

    inicio = texto.find("{")
    if inicio == -1:
        return None

    # Varrer até à chaveta que fecha o objecto, ignorando as que estão
    # dentro de strings (um título com "{" partia um corte ingénuo).
    profundidade = 0
    dentro_de_string = False
    escapado = False
    for posicao in range(inicio, len(texto)):
        caractere = texto[posicao]
        if escapado:
            escapado = False
            continue
        if caractere == "\\":
            escapado = True
            continue
        if caractere == '"':
            dentro_de_string = not dentro_de_string
            continue
        if dentro_de_string:
            continue
        if caractere == "{":
            profundidade += 1
        elif caractere == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio:posicao + 1]

    return None  # truncado a meio — sem objecto fechado não há JSON


def parse_extraction_payload(bruto: str) -> dict:
    """Converte a resposta do modelo no dicionário bruto da extracção.

    Raises:
        ErroDeExtraccao: quando não há JSON aproveitável. É deliberado que
            não devolva ``{}`` em silêncio — o chamador precisa de saber
            que falhou para guardar a transcrição à mesma.
    """
    bloco = _extrair_bloco_json(bruto)
    if not bloco:
        raise ErroDeExtraccao("Resposta do modelo sem objecto JSON")

    try:
        dados = json.loads(bloco)
    except json.JSONDecodeError as e:
        raise ErroDeExtraccao(f"JSON inválido: {e}") from e

    if not isinstance(dados, dict):
        raise ErroDeExtraccao("O JSON devolvido não é um objecto")
    return dados


# ====================================================================
# DATAS (puro)
# ====================================================================

_DIAS_DA_SEMANA = {
    "segunda": 0, "segunda-feira": 0,
    "terca": 1, "terca-feira": 1,
    "quarta": 2, "quarta-feira": 2,
    "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4,
    "sabado": 5,
    "domingo": 6,
}

_UNIDADES = {
    "dia": 1, "dias": 1,
    "semana": 7, "semanas": 7,
    "mes": 30, "meses": 30,
}


def _sem_acentos(texto: str) -> str:
    """"amanhã" → "amanha" (o modelo alterna entre as duas grafias)."""
    normalizado = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def _hora_mencionada(expressao: str) -> int:
    """Hora do dia deduzida da expressão ("de manhã" → 9, "à tarde" → 15)."""
    explicita = re.search(r"\b(?:as|às)\s*(\d{1,2})(?:[:h](\d{2}))?", expressao)
    if explicita:
        hora = int(explicita.group(1))
        if 0 <= hora <= 23:
            return hora
    # `\b` é indispensável: "manha" é subcadeia de "amanha", e um teste
    # de pertença marcava 09:00 em "amanhã à tarde".
    if re.search(r"\bmanha\b", expressao):
        return HORA_MANHA
    if re.search(r"\btarde\b", expressao) or "fim do dia" in expressao:
        return HORA_TARDE
    return HORA_OMISSAO


def _com_hora(base: datetime, expressao: str) -> datetime:
    minutos = 0
    explicita = re.search(r"\b(?:as|às)\s*(\d{1,2})[:h](\d{2})", expressao)
    if explicita:
        minutos = int(explicita.group(2))
        minutos = minutos if 0 <= minutos <= 59 else 0
    return base.replace(
        hour=_hora_mencionada(expressao), minute=minutos, second=0, microsecond=0
    )


def resolver_data_relativa(expressao: Any, *, agora: datetime) -> Optional[str]:
    """Traduz uma expressão temporal em ISO 8601, ou ``None``.

    Aceita o que o modelo devolve na prática: uma data ISO já resolvida, ou
    português corrente ("amanhã de manhã", "daqui a duas semanas",
    "sexta-feira", "final do mês").

    ``agora`` é injectado de propósito — sem isso o teste dependeria do dia
    em que corresse e passaria a falhar sozinho a meio de uma sexta-feira.

    Devolve ``None`` sempre que houver dúvida: uma data errada numa tarefa é
    pior do que tarefa nenhuma.
    """
    if expressao is None:
        return None
    if isinstance(expressao, datetime):
        return expressao.isoformat()

    bruto = str(expressao).strip()
    if not bruto:
        return None

    # 1. Já vem em ISO?
    candidato = bruto.replace("Z", "+00:00")
    try:
        resolvido = datetime.fromisoformat(candidato)
    except ValueError:
        resolvido = None
    if resolvido is not None:
        if resolvido.tzinfo is None:
            resolvido = resolvido.replace(tzinfo=agora.tzinfo or timezone.utc)
        if resolvido.hour == 0 and resolvido.minute == 0:
            resolvido = resolvido.replace(hour=HORA_OMISSAO)
        return resolvido.isoformat()

    texto = _sem_acentos(bruto).lower()

    # 2. Formato português DD/MM/AAAA (ou DD-MM-AAAA).
    numerica = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", texto)
    if numerica:
        dia, mes, ano = (int(g) for g in numerica.groups())
        try:
            base = agora.replace(year=ano, month=mes, day=dia)
        except ValueError:
            return None  # 31/02 — data impossível, não se adivinha
        return _com_hora(base, texto).isoformat()

    # 3. Âncoras do dia.
    if "depois de amanha" in texto:
        return _com_hora(agora + timedelta(days=2), texto).isoformat()
    if "amanha" in texto:
        return _com_hora(agora + timedelta(days=1), texto).isoformat()
    if "hoje" in texto or "ainda hoje" in texto:
        return _com_hora(agora, texto).isoformat()

    # 4. "daqui a N dias/semanas/meses" (N em dígitos ou por extenso).
    contagem = re.search(
        r"daqui\s+a\s+(\d+|um|uma|dois|duas|tres|quatro|cinco|seis)\s+"
        r"(dias?|semanas?|mes|meses)",
        texto,
    )
    if contagem:
        palavra = contagem.group(1)
        numeros = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3,
                   "quatro": 4, "cinco": 5, "seis": 6}
        quantidade = int(palavra) if palavra.isdigit() else numeros[palavra]
        dias = _UNIDADES[contagem.group(2)] * quantidade
        return _com_hora(agora + timedelta(days=dias), texto).isoformat()

    # 5. Fim do mês.
    if "final do mes" in texto or "fim do mes" in texto:
        primeiro_do_proximo = (
            agora.replace(day=28) + timedelta(days=4)
        ).replace(day=1)
        ultimo = primeiro_do_proximo - timedelta(days=1)
        return _com_hora(ultimo, texto).isoformat()

    # 6. Próxima semana (sem dia concreto) → segunda-feira seguinte.
    if "proxima semana" in texto or "semana que vem" in texto:
        dias = 7 - agora.weekday()
        return _com_hora(agora + timedelta(days=dias), texto).isoformat()

    # 7. Dia da semana. "sexta" dito numa sexta significa a sexta seguinte —
    #    ninguém agenda para o dia que já está a decorrer ao gravar a nota.
    for nome, indice in _DIAS_DA_SEMANA.items():
        if re.search(rf"\b{re.escape(nome)}\b", texto):
            avanco = (indice - agora.weekday()) % 7 or 7
            return _com_hora(agora + timedelta(days=avanco), texto).isoformat()

    return None


# ====================================================================
# NORMALIZAÇÃO (puro)
# ====================================================================


def normalizar_prioridade(valor: Any) -> str:
    """Mapeia o que o modelo escreveu para os valores de ``models/task.py``."""
    texto = _sem_acentos(valor).lower().strip()
    if texto in {"alta", "urgente", "high", "critica"}:
        return "Alta"
    if texto in {"baixa", "low"}:
        return "Baixa"
    return PRIORIDADE_OMISSAO


def _texto_limpo(valor: Any, limite: int) -> str:
    texto = " ".join(str(valor or "").split())
    return texto[:limite].strip()


def normalizar_tarefa(tarefa: Any, *, agora: datetime) -> Optional[dict]:
    """Valida e normaliza uma tarefa extraída; ``None`` se for lixo.

    Aceita os nomes alternativos que o modelo usa na prática (``data``,
    ``prazo``, ``title``) — mudar o prompt não impede o modelo de improvisar.
    """
    if not isinstance(tarefa, dict):
        return None

    titulo = _texto_limpo(
        tarefa.get("titulo") or tarefa.get("title") or tarefa.get("tarefa"),
        MAX_TITULO,
    )
    if not titulo:
        return None  # sem título não há tarefa

    expressao = (
        tarefa.get("data_sugerida")
        if tarefa.get("data_sugerida") is not None
        else tarefa.get("data") or tarefa.get("prazo") or tarefa.get("due_date")
    )

    return {
        "titulo": titulo,
        "descricao": _texto_limpo(
            tarefa.get("descricao") or tarefa.get("description"), MAX_DESCRICAO
        ),
        "due_date": resolver_data_relativa(expressao, agora=agora),
        "data_original": _texto_limpo(expressao, 120) or None,
        "prioridade": normalizar_prioridade(tarefa.get("prioridade") or tarefa.get("priority")),
    }


def normalizar_extraccao(payload: Any, *, agora: datetime) -> dict:
    """Devolve a extracção pronta a gravar, sempre com a forma esperada.

    Tolera o que o modelo faz de errado — lista em falta, tarefas a mais,
    entradas que são strings em vez de objectos — sem nunca deixar passar
    uma tarefa sem título ou uma prioridade inventada.
    """
    if not isinstance(payload, dict):
        return {"resumo_timeline": "", "tarefas_extraidas": []}

    brutas = payload.get("tarefas_extraidas") or payload.get("tarefas") or []
    if not isinstance(brutas, list):
        brutas = []

    tarefas = []
    for bruta in brutas[:MAX_TAREFAS]:
        normalizada = normalizar_tarefa(bruta, agora=agora)
        if normalizada:
            tarefas.append(normalizada)

    return {
        "resumo_timeline": _texto_limpo(
            payload.get("resumo_timeline") or payload.get("resumo"), MAX_RESUMO
        ),
        "tarefas_extraidas": tarefas,
    }


# ====================================================================
# PROVIDER SIMULADO (dev)
# ====================================================================

# Marcadores de acção usados pela heurística do provider `mock`. Não é IA —
# é uma aproximação deliberadamente simples que mantém o fluxo de dev vivo
# (e reage ao que se disser) sem chamar uma API paga.
_MARCADORES_DE_ACCAO = (
    "tenho de", "tenho que", "e preciso", "é preciso", "ficou combinado",
    "vou ", "temos de", "temos que", "falta ", "confirmar", "enviar",
    "pedir", "marcar", "agendar", "preparar", "solicitar",
)


def _frases(texto: str) -> list:
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto or "") if f.strip()]


def extrair_com_heuristica(transcricao: str) -> dict:
    """Extracção simulada por palavras-chave (provider ``mock``).

    Existe para que um programador sem chaves veja a nota a aparecer na
    timeline e as tarefas na lista. **Não é usada nos testes** — esses usam
    duplos explícitos, para que um teste nunca possa passar por causa da
    heurística em vez do código que diz estar a provar.
    """
    frases = _frases(transcricao)
    if not frases:
        return {"resumo_timeline": "", "tarefas_extraidas": []}

    resumo = " ".join(frases[:2])[:MAX_RESUMO]

    tarefas = []
    for frase in frases:
        minuscula = _sem_acentos(frase).lower()
        if not any(marcador in minuscula for marcador in _MARCADORES_DE_ACCAO):
            continue
        tarefas.append(
            {
                "titulo": frase[:MAX_TITULO],
                "descricao": "Extraída automaticamente da nota de voz (modo simulado).",
                "data_sugerida": frase,  # o normalizador procura a data no texto
                "prioridade": "Média",
            }
        )
        if len(tarefas) >= 3:
            break

    return {"resumo_timeline": resumo, "tarefas_extraidas": tarefas}


# ====================================================================
# FRONTEIRA PÚBLICA
# ====================================================================


async def _chamar_openai(
    transcricao: str, *, contexto: Optional[dict], modelo: str, timeout: float
) -> str:
    from services.ai_document import get_openai_client

    cliente = get_openai_client()
    try:
        resposta = await asyncio.wait_for(
            cliente.chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(transcricao, contexto=contexto),
                    },
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as e:
        raise ErroDeExtraccao(f"A extracção excedeu {timeout:.0f}s") from e
    except Exception as e:
        raise ErroDeExtraccao(f"{type(e).__name__}: {e}") from e

    try:
        return resposta.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError) as e:
        raise ErroDeExtraccao("Resposta do modelo sem conteúdo") from e


async def extrair_accoes(
    transcricao: str,
    *,
    contexto: Optional[dict] = None,
    agora: Optional[datetime] = None,
    ambiente=None,
) -> dict:
    """Transforma a transcrição em resumo + tarefas.

    Args:
        transcricao: Texto produzido pelo ASR.
        contexto: ``{client_name, process_ref, consultor_name, hoje}``.
        agora: Momento de referência para as datas relativas (testes).
        ambiente: Mapa de ambiente alternativo (testes).

    Returns:
        ``{"resumo_timeline": str, "tarefas_extraidas": [...], "provider": str}``

    Raises:
        ErroDeExtraccao: modelo em baixo ou resposta inaproveitável. O
            chamador guarda a transcrição à mesma — ver ``voice_note_engine``.
    """
    texto = (transcricao or "").strip()
    if not texto:
        raise ErroDeExtraccao("Transcrição vazia")

    agora = agora or datetime.now(timezone.utc)
    provider = resolver_provider(ambiente)

    if provider == PROVIDER_MOCK:
        logger.info("[NOTA-VOZ] Extracção simulada (provider=mock)")
        resultado = normalizar_extraccao(extrair_com_heuristica(texto), agora=agora)
        return {**resultado, "provider": PROVIDER_MOCK, "modelo": "simulado"}

    modelo = await resolver_modelo(ambiente)
    bruto = await _chamar_openai(
        texto,
        contexto=contexto,
        modelo=modelo,
        timeout=resolver_timeout(ambiente),
    )
    resultado = normalizar_extraccao(parse_extraction_payload(bruto), agora=agora)

    logger.info(
        f"[NOTA-VOZ] Extracção concluída: {len(resultado['tarefas_extraidas'])} "
        f"tarefa(s) — modelo={modelo}"
    )
    return {**resultado, "provider": provider, "modelo": modelo}
