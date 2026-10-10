"""
Análise de desempenho da equipa no PDF do relatório executivo — OPCIONAL.

O PDF do Dashboard Executivo e do Relatório Semanal pode levar um parágrafo de
avaliação e comparação do desempenho da equipa, escrito por um modelo de
linguagem. É uma escolha de quem pede o PDF (caixa «Incluir análise de IA»):
sem ela, **nenhuma chamada é feita** e o PDF é o mesmo de sempre.

O QUE VAI AO MODELO, E O QUE NÃO VAI
  Só os números do relatório já agregado: período, totais, fases mais usadas e,
  por colaborador, nome + perfil + as cinco contagens. Nunca emails, nomes de
  clientes, números de processo, movimentos individuais nem o texto de nada que
  uma pessoa tenha escrito. O modelo analisa números, não lê dados de clientes.

O MODELO NÃO É UMA PAREDE
  Pede-se um texto curto, factual e sem juízos de valor sobre pessoas — mas o
  que o PDF imprime passa por `limpar_texto`: sem HTML/markdown, com tecto de
  tamanho, e uma resposta vazia, demasiado curta ou com endereços (email/URL)
  é recusada. Recusada ou falhada → o PDF sai SEM a secção e o servidor di-lo
  (`X-Analise-IA`); nunca um PDF «em branco» no sítio da análise.

DEV SIMULA, SEMPRE
  Como nas notas de voz e nos rascunhos de receção: só produção COM chave chama
  o modelo. Em desenvolvimento/testes o texto é calculado a partir dos números
  (determinístico) e vem rotulado como simulado. O modelo vem do painel de IA
  (tarefa `executive_report_analysis`), nunca fixo no código.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

CHAVE_AI_CONFIG = "executive_report_analysis"
MODELO_OMISSAO = "gpt-4o-mini"
TIMEOUT_OMISSAO = 45.0

PROVIDER_OPENAI = "openai"
PROVIDER_MOCK = "mock"
PROVIDERS_VALIDOS = frozenset({PROVIDER_OPENAI, PROVIDER_MOCK})

ORIGEM_IA = "ia"
ORIGEM_SIMULADA = "simulado"

MAX_CARACTERES = 1800
MIN_CARACTERES = 60
MAX_PESSOAS_ENVIADAS = 25
MAX_FASES_ENVIADAS = 8

ROTULOS_DOS_PERFIS = {
    "consultor": "Consultor", "intermediario": "Intermediário",
    "administrativo": "Administrativo", "diretor": "Diretor", "ceo": "CEO",
}

SYSTEM_PROMPT = (
    "És um analista de operações de uma empresa de intermediação de crédito e "
    "imobiliária em Portugal. Recebes os números de desempenho da equipa num "
    "período e escreves, em português de Portugal, uma avaliação curta e uma "
    "comparação entre colaboradores. Regras: (1) usa APENAS os números "
    "recebidos — não inventes valores, causas nem factos; (2) compara e "
    "destaca, em termos factuais, quem mais avançou processos, quem concluiu "
    "mais tarefas e onde há tarefas em atraso; (3) um valor nulo significa "
    "«sem histórico registado», não zero — não o interpretes como falta de "
    "trabalho; (4) tom profissional e neutro, sem juízos de valor sobre as "
    "pessoas nem recomendações disciplinares; (5) no máximo 150 palavras, "
    "em 2 a 3 parágrafos curtos, texto simples, sem listas, sem markdown e "
    "sem títulos. Responde só com o texto da análise."
)


# ====================================================================
# O QUE VAI AO MODELO — puro
# ====================================================================

def _numero(valor: Any) -> Optional[int]:
    """Um número, ou `None` (histórico silenciado: «sem registo», nunca 0)."""
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def dados_para_o_modelo(relatorio: dict) -> dict:
    """Os números do relatório, e nada mais. Pura."""
    resumo = relatorio.get("summary") or {}
    pessoas = []
    for u in (relatorio.get("users") or [])[:MAX_PESSOAS_ENVIADAS]:
        pessoas.append({
            "nome": str(u.get("name") or "Colaborador"),
            "perfil": ROTULOS_DOS_PERFIS.get(u.get("role"), str(u.get("role") or "")),
            "fases_alteradas": _numero(u.get("phase_changes")),
            "processos_avancados": _numero(u.get("processes_moved")),
            "tarefas_concluidas": _numero(u.get("tasks_completed")),
            "tarefas_pendentes": _numero(u.get("tasks_pending")),
            "tarefas_em_atraso": _numero(u.get("tasks_overdue")),
        })
    fases = [
        {"fase": str(f.get("rotulo") or f.get("fase") or ""), "entradas": _numero(f.get("n")) or 0}
        for f in (relatorio.get("por_fase") or [])[:MAX_FASES_ENVIADAS]
    ]
    return {
        "periodo": {"inicio": relatorio.get("start_date"), "fim": relatorio.get("end_date")},
        "totais": {
            "colaboradores": _numero(resumo.get("total_users")) or 0,
            "fases_alteradas": _numero(resumo.get("total_phase_changes")) or 0,
            "processos_avancados": _numero(resumo.get("total_processes_moved")) or 0,
            "tarefas_concluidas": _numero(resumo.get("total_tasks_completed")) or 0,
            "tarefas_pendentes": _numero(resumo.get("total_tasks_pending")) or 0,
            "tarefas_em_atraso": _numero(resumo.get("total_tasks_overdue")) or 0,
        },
        "colaboradores": pessoas,
        "fases_mais_usadas": fases,
    }


def construir_mensagens(dados: dict) -> list[dict]:
    import json

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Números do período (JSON):\n" + json.dumps(dados, ensure_ascii=False)},
    ]


def ha_dados_para_analisar(dados: dict) -> bool:
    """Sem colaboradores não há nada a comparar — não se gasta uma chamada."""
    return bool(dados.get("colaboradores"))


# ====================================================================
# O TEXTO — o que o PDF imprime
# ====================================================================

_MARCAS = re.compile(r"[*_`#>]+")
_ETIQUETAS = re.compile(r"<[^>]{0,200}>")
_ENDERECOS = re.compile(r"(https?://|www\.|[\w.+-]+@[\w-]+\.[\w.]+)", re.IGNORECASE)


def limpar_texto(bruto: Any) -> Optional[str]:
    """O texto aproveitável, ou `None`. Pura.

    Tira HTML e marcas de markdown (o PDF imprime texto), junta linhas dentro
    do parágrafo e põe tecto no tamanho (cortando numa frase, não a meio de
    uma palavra). Recusa: vazio, curto demais ou com endereços.
    """
    if not isinstance(bruto, str):
        return None
    texto = _ETIQUETAS.sub(" ", bruto)
    texto = _MARCAS.sub("", texto)
    paragrafos = []
    for bloco in re.split(r"\n\s*\n", texto.replace("\r", "")):
        linha = re.sub(r"\s+", " ", bloco.replace("\n", " ")).strip(" -•\t")
        if linha:
            paragrafos.append(linha)
    texto = "\n\n".join(paragrafos)
    if len(texto) < MIN_CARACTERES or _ENDERECOS.search(texto):
        return None
    if len(texto) > MAX_CARACTERES:
        corte = texto[:MAX_CARACTERES]
        ultimo_ponto = max(corte.rfind(". "), corte.rfind(".\n"), corte.rfind("?"), corte.rfind("!"))
        texto = corte[: ultimo_ponto + 1] if ultimo_ponto >= MIN_CARACTERES else corte.rsplit(" ", 1)[0] + "…"
    return texto


def analise_simulada(dados: dict) -> str:
    """Texto determinístico calculado dos números (desenvolvimento e testes)."""
    pessoas = dados.get("colaboradores") or []
    totais = dados.get("totais") or {}
    periodo = dados.get("periodo") or {}
    com_registo = [p for p in pessoas if p.get("processos_avancados") is not None]

    def _melhor(campo: str, lista: list[dict]) -> Optional[dict]:
        validos = [p for p in lista if (p.get(campo) or 0) > 0]
        return max(validos, key=lambda p: p[campo]) if validos else None

    avancou = _melhor("processos_avancados", com_registo)
    concluiu = _melhor("tarefas_concluidas", pessoas)
    atraso = _melhor("tarefas_em_atraso", pessoas)

    primeiro = (
        f"[Texto simulado — sem chamada ao modelo] Entre {periodo.get('inicio')} e {periodo.get('fim')}, "
        f"a equipa ({totais.get('colaboradores', len(pessoas))} colaboradores) alterou "
        f"{totais.get('fases_alteradas', 0)} fases, fez avançar {totais.get('processos_avancados', 0)} "
        f"processos e concluiu {totais.get('tarefas_concluidas', 0)} tarefas."
    )
    partes = []
    if avancou:
        partes.append(f"{avancou['nome']} fez avançar mais processos ({avancou['processos_avancados']})")
    if concluiu:
        partes.append(f"{concluiu['nome']} concluiu mais tarefas ({concluiu['tarefas_concluidas']})")
    segundo = ("Em destaque: " + "; ".join(partes) + ".") if partes else "Não há movimentos a destacar neste período."
    terceiro = (
        f"As tarefas em atraso somam {totais.get('tarefas_em_atraso', 0)}"
        + (f", com maior peso em {atraso['nome']} ({atraso['tarefas_em_atraso']})." if atraso else ".")
    )
    return "\n\n".join((primeiro, segundo, terceiro))


# ====================================================================
# CONFIGURAÇÃO E MOTOR
# ====================================================================

def _env(ambiente, chave: str) -> str:
    return str((ambiente if ambiente is not None else os.environ).get(chave) or "").strip().lower()


def resolver_provider(ambiente=None) -> str:
    """`EXEC_REPORT_AI_PROVIDER` manda; sem ele, OpenAI só em produção COM chave."""
    declarado = _env(ambiente, "EXEC_REPORT_AI_PROVIDER")
    if declarado:
        if declarado in PROVIDERS_VALIDOS:
            return declarado
        logger.warning("[RELATORIO-IA] EXEC_REPORT_AI_PROVIDER='%s' desconhecido; a usar '%s'",
                       declarado, PROVIDER_MOCK)
        return PROVIDER_MOCK
    producao = any(_env(ambiente, c) in {"production", "prod", "producao", "produção"}
                   for c in ("ENVIRONMENT", "APP_ENV"))
    tem_chave = bool(_env(ambiente, "OPENAI_API_KEY") or _env(ambiente, "EMERGENT_LLM_KEY"))
    return PROVIDER_OPENAI if producao and tem_chave else PROVIDER_MOCK


async def resolver_modelo() -> str:
    """Modelo do painel de IA (tarefa `executive_report_analysis`), nunca fixo."""
    try:
        from services.ai_page_analyzer import get_ai_config

        configurado = (await get_ai_config() or {}).get(CHAVE_AI_CONFIG)
        if configurado:
            return str(configurado)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RELATORIO-IA] Painel de IA indisponível (%s): modelo por omissão.", exc)
    return MODELO_OMISSAO


async def _chamar_modelo(mensagens: list[dict], modelo: str) -> tuple[str, dict]:
    from services.ai_document import get_openai_client

    cliente = get_openai_client()
    resposta = await asyncio.wait_for(
        cliente.chat.completions.create(
            model=modelo, messages=mensagens, temperature=0.3, max_tokens=600,
        ),
        timeout=TIMEOUT_OMISSAO,
    )
    uso = getattr(resposta, "usage", None)
    return (resposta.choices[0].message.content or ""), {
        "entrada": int(getattr(uso, "prompt_tokens", 0) or 0),
        "saida": int(getattr(uso, "completion_tokens", 0) or 0),
    }


async def _registar_uso(modelo: str, uso: dict, decorrido_ms: int, sucesso: bool, erro: Optional[str] = None) -> None:
    """Alimenta o relatório de custos de IA. Observa, nunca interfere."""
    try:
        from services.ai_usage_tracker import ai_usage_tracker

        await ai_usage_tracker.log_usage(
            task=CHAVE_AI_CONFIG, model=modelo, provider=PROVIDER_OPENAI,
            input_tokens=uso.get("entrada", 0), output_tokens=uso.get("saida", 0),
            response_time_ms=decorrido_ms, success=sucesso, error_message=erro,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[RELATORIO-IA] Uso não registado: %s", exc)


async def gerar_analise(relatorio: dict, *, ambiente=None) -> Optional[dict]:
    """A análise para o PDF, ou `None` (o PDF sai sem a secção).

    Devolve `{"texto": str, "origem": "ia" | "simulado"}`. Nunca levanta: uma
    IA em baixo não pode impedir o PDF.
    """
    dados = dados_para_o_modelo(relatorio)
    if not ha_dados_para_analisar(dados):
        return None
    if resolver_provider(ambiente) != PROVIDER_OPENAI:
        return {"texto": analise_simulada(dados), "origem": ORIGEM_SIMULADA}

    inicio = time.monotonic()
    modelo = MODELO_OMISSAO
    try:
        modelo = await resolver_modelo()
        bruto, uso = await _chamar_modelo(construir_mensagens(dados), modelo)
    except Exception as exc:  # noqa: BLE001 — a IA em baixo não pode parar o PDF
        logger.warning("[RELATORIO-IA] Falha do modelo (%s): PDF sem análise.", exc)
        await _registar_uso(modelo, {}, int((time.monotonic() - inicio) * 1000), False, str(exc)[:200])
        return None
    await _registar_uso(modelo, uso, int((time.monotonic() - inicio) * 1000), True)

    texto = limpar_texto(bruto)
    if texto is None:
        logger.warning("[RELATORIO-IA] Resposta do modelo recusada (vazia/curta/endereços): PDF sem análise.")
        return None
    return {"texto": texto, "origem": ORIGEM_IA}
