"""
====================================================================
LOG DA IA DO PROCESSO — o que o motor fez, quando, e porque falhou (Out 2026)
====================================================================
A IA corria como uma caixa preta: lia um documento, gravava a categoria nos
metadados e, se falhava, deixava uma linha no log do servidor que ninguém da
equipa vê. `process_ai_log` é a trilha por PROCESSO que o ecrã mostra.

O QUE SE REGISTA (uma linha por acção sobre UM documento)
  * ``acção``  — categorizar | extrair_dados | analisar | rever
  * ``estado`` — sucesso | falha | saltado   (saltado = nem chegou a chamar o modelo)
  * ``gatilho``— automatico (upload, Portal, Parceiro) | manual (um utilizador carregou)
  * ``motivo`` — um CÓDIGO fechado (``MOTIVOS``) com a mensagem em português; o ecrã
    mostra a mensagem, nunca o texto cru da excepção.

REGRAS QUE NÃO SE PODEM PERDER
  * **Nunca se grava o texto de um erro do fornecedor.** Uma resposta 401 da API
    pode trazer parte da chave; ``classificar_falha`` reduz o texto a um código e o
    texto original morre aqui. É a mesma razão de o ``Veredicto`` do Portal ter
    códigos e não frases.
  * **Nomes de campos, nunca valores.** ``campos`` guarda ``["nif", "morada"]``,
    nunca o NIF: o log é lido por muita gente (staff) e vive 12 meses.
  * **Observa, não intercepta.** ``registar_accao_ia`` nunca levanta (regra do
    ``job_heartbeat``): uma falha a gravar o log não pode transformar uma
    análise bem sucedida num erro, nem estragar o upload do cliente.
  * **Quem carregou fica registado só nas acções manuais** (``utilizador_*``); as
    automáticas não têm autor — o gatilho é o upload. O perfil ``indexacao`` não
    deixa rasto pessoal (``history._is_stealth_user``), por isso, se o autor for
    silenciado, grava-se a acção SEM o nome.
  * **O log não decide nada.** Ninguém lê esta colecção para saber se um
    documento "já foi analisado" — essa verdade continua em ``document_metadata``.
====================================================================
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from database import db

logger = logging.getLogger(__name__)

COLECCAO = "process_ai_log"

#: 12 meses. Vive aqui e é gravado em cada linha (``expire_at``, datetime nativo);
#: o índice TTL de ``db_indexes`` expira na data dessa linha (``seconds: 0``), por
#: isso o prazo só existe num sítio.
RETENCAO_DIAS = 365

ACCOES = {
    "categorizar": "Documento classificado",
    "extrair_dados": "Dados extraídos",
    "analisar": "Documento analisado",
    "rever": "Documento reanalisado",
    # Módulo Index (Lote 12, Fase 5): o PDF limpo e a eliminação do original.
    "sanitizar": "PDF limpo gerado",
    "purgar": "Original eliminado",
}

ESTADOS = ("sucesso", "falha", "saltado")
GATILHOS = ("automatico", "manual")

#: Código → mensagem para o ecrã. Fechado de propósito: um código novo exige
#: decidir o que se diz ao utilizador.
MOTIVOS = {
    "ja_categorizado": "Já tinha sido classificado — não foi chamada a IA outra vez.",
    "ja_analisado": "Já tinha sido analisado pela IA — não foi chamada outra vez.",
    "demasiado_grande": "Ficheiro demasiado grande para a IA (limite de 20 MB).",
    "ilegivel": "Não foi possível ler o ficheiro no armazenamento.",
    "sem_contexto": "Sem texto extraível: só foi possível usar o nome do ficheiro.",
    "limite_do_fornecedor": "O serviço de IA recusou por limite de utilização. Tente mais tarde.",
    "ia_nao_configurada": "O serviço de IA não está configurado ou recusou as credenciais.",
    "tempo_excedido": "O serviço de IA demorou demasiado a responder.",
    "formato_nao_suportado": "Formato de ficheiro não suportado pela IA.",
    "erro_da_ia": "A IA não conseguiu analisar este documento.",
    "erro_interno": "Falha interna ao analisar o documento.",
    "pdf_limpo_invalido": "O PDF limpo não passou a verificação — o original foi mantido.",
    "armazenamento_indisponivel": "Não foi possível gravar ou ler o PDF limpo no armazenamento — o original foi mantido.",
    "formato_nao_sanitizavel": "Formato que não se converte em PDF limpo — o original foi mantido.",
    "purga_adiada": "A eliminação do original foi adiada: o PDF limpo não pôde ser confirmado.",
}

#: Palavras (em minúsculas) → código. A ordem importa: o LIMITE antes da
#: credencial, porque «rate limit … api key» tem as duas e mandar rever uma chave
#: que está certa é pior do que dizer «tente mais tarde».
_PISTAS_DE_FALHA = (
    ("limite_do_fornecedor", ("rate limit", "rate_limit", "quota", "429", "too many requests", "insufficient_quota")),
    ("tempo_excedido", ("timeout", "timed out", "tempo excedido")),
    ("ia_nao_configurada", ("api key", "api_key", "apikey", "unauthorized", "401", "403", "not configured", "não configurad", "chave")),
    ("formato_nao_suportado", ("unsupported", "formato", "mime", "not supported", "não suportad")),
)

MAXIMO_POR_PAGINA = 100


def classificar_falha(erro: Any) -> str:
    """Reduz o texto de uma falha a um CÓDIGO de ``MOTIVOS``. Nunca devolve o texto."""
    texto = str(erro or "").lower()
    for codigo, pistas in _PISTAS_DE_FALHA:
        if any(pista in texto for pista in pistas):
            return codigo
    return "erro_da_ia"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _nomes_de_campos(campos: Optional[Iterable[Any]]) -> list[str]:
    """Só NOMES, deduplicados, com tecto. Um valor (um NIF) nunca entra aqui."""
    vistos: list[str] = []
    for campo in campos or []:
        nome = str(campo).strip()[:60]
        if nome and nome not in vistos:
            vistos.append(nome)
        if len(vistos) >= 40:
            break
    return vistos


def montar_linha(
    *,
    process_id: str,
    accao: str,
    estado: str,
    gatilho: str,
    ficheiro: Optional[str] = None,
    s3_path: Optional[str] = None,
    documento_id: Optional[str] = None,
    motivo: Optional[str] = None,
    categoria: Optional[str] = None,
    campos: Optional[Iterable[Any]] = None,
    confianca: Optional[float] = None,
    origem: Optional[str] = None,
    utilizador_id: Optional[str] = None,
    utilizador_nome: Optional[str] = None,
) -> dict:
    """Constrói a linha (pura, sem I/O) — é o que os testes inspeccionam."""
    if accao not in ACCOES:
        raise ValueError(f"acção desconhecida: {accao}")
    if estado not in ESTADOS:
        raise ValueError(f"estado desconhecido: {estado}")
    if gatilho not in GATILHOS:
        raise ValueError(f"gatilho desconhecido: {gatilho}")
    if motivo is not None and motivo not in MOTIVOS:
        # Um código fora do registo nunca vai para o ecrã como texto livre.
        motivo = "erro_interno"

    agora = _agora()
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "accao": accao,
        "estado": estado,
        "gatilho": gatilho,
        "origem": (origem or None),
        "ficheiro": (ficheiro or None),
        "s3_path": (s3_path or None),
        "documento_id": (documento_id or None),
        "motivo": motivo,
        "categoria": (str(categoria)[:80] if categoria else None),
        "campos": _nomes_de_campos(campos),
        "confianca": confianca if isinstance(confianca, (int, float)) else None,
        "utilizador_id": utilizador_id,
        "utilizador_nome": utilizador_nome,
        "created_at": agora.isoformat(),
        "expire_at": agora + timedelta(days=RETENCAO_DIAS),
    }


def _autor(user: Optional[dict]) -> tuple[Optional[str], Optional[str]]:
    """(id, nome) de quem carregou, ou (None, None) se não houver autor ou se o
    perfil for silenciado (a Indexação não deixa rasto pessoal)."""
    if not user:
        return None, None
    try:
        from services.history import _is_stealth_user

        if _is_stealth_user(user):
            return None, None
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning("[AI-LOG] Não foi possível avaliar o perfil silenciado: %s", exc)
        return None, None
    return user.get("id"), user.get("name")


async def registar_accao_ia(
    *,
    process_id: Optional[str],
    accao: str,
    estado: str,
    gatilho: str,
    user: Optional[dict] = None,
    **detalhe: Any,
) -> None:
    """Grava uma linha no log. NUNCA levanta. Sem processo não há log (um upload
    do onboarding ainda não tem processo: não há onde o mostrar)."""
    if not process_id:
        return
    try:
        uid, nome = _autor(user) if gatilho == "manual" else (None, None)
        linha = montar_linha(
            process_id=process_id,
            accao=accao,
            estado=estado,
            gatilho=gatilho,
            utilizador_id=uid,
            utilizador_nome=nome,
            **detalhe,
        )
        await db[COLECCAO].insert_one(linha)
    except Exception as exc:
        logger.warning(
            "[AI-LOG] Não foi possível registar %s/%s do processo %s: %s: %s",
            accao, estado, process_id, type(exc).__name__, exc,
        )


# --------------------------------------------------------------------
# Leitura (a ÚNICA leitura da colecção — sempre atrás da fronteira do processo)
# --------------------------------------------------------------------
_PROJECCAO = {"_id": 0, "expire_at": 0}


def _para_o_ecra(linha: dict) -> dict:
    """Lista POSITIVA do que sai para o ecrã + a mensagem do motivo."""
    motivo = linha.get("motivo")
    return {
        "id": linha.get("id"),
        "accao": linha.get("accao"),
        "accao_rotulo": ACCOES.get(linha.get("accao"), linha.get("accao")),
        "estado": linha.get("estado"),
        "gatilho": linha.get("gatilho"),
        "origem": linha.get("origem"),
        "ficheiro": linha.get("ficheiro"),
        "documento_id": linha.get("documento_id"),
        "motivo": motivo,
        "motivo_mensagem": MOTIVOS.get(motivo) if motivo else None,
        "categoria": linha.get("categoria"),
        "campos": linha.get("campos") or [],
        "confianca": linha.get("confianca"),
        "utilizador_nome": linha.get("utilizador_nome"),
        "created_at": linha.get("created_at"),
    }


async def listar_accoes_ia(
    process_id: str, *, pagina: int = 1, por_pagina: int = 30, estado: Optional[str] = None
) -> dict:
    """Página do log de UM processo, mais recente primeiro."""
    por_pagina = max(1, min(int(por_pagina or 30), MAXIMO_POR_PAGINA))
    pagina = max(1, int(pagina or 1))
    consulta: dict = {"process_id": process_id}
    if estado in ESTADOS:
        consulta["estado"] = estado

    total = await db[COLECCAO].count_documents(consulta)
    cursor = (
        db[COLECCAO]
        .find(consulta, _PROJECCAO)
        .sort("created_at", -1)
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )
    linhas = await cursor.to_list(por_pagina)
    return {
        "items": [_para_o_ecra(linha) for linha in linhas],
        "total": total,
        "page": pagina,
        "size": por_pagina,
    }
