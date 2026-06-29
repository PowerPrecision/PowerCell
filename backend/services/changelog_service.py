"""
====================================================================
SYSTEM CHANGELOG SERVICE — Mural de Atualizações gerado por IA
====================================================================
Serviço que gere as notas de atualização do sistema (changelog).

FUNCIONALIDADES:
1. Obter changelogs publicados (endpoint público)
2. Gerar notas de atualização por IA a partir de:
   - Histórico de commits Git
   - Ficheiro CHANGELOG.md
   - Ficheiro worklog.md
3. Guardar o resultado na coleção system_changelogs

INTEGRAÇÃO IA:
- Usa OpenAI GPT-4o-mini (via EMERGENT_LLM_KEY) com retry
- Prompt de Gestor de Produto que transforma logs técnicos em anúncios amigáveis
- Suporta sanitização de input para prevenir prompt injection

COLEÇÃO MONGODB: system_changelogs
====================================================================
"""
import os
import subprocess
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from database import db
from models.changelog import ChangelogEntry, ChangelogResponse

logger = logging.getLogger(__name__)

# ── Configuração IA ──
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
AI_MODEL = "gpt-4o-mini"

_openai_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    """Obter ou criar cliente OpenAI assíncrono (lazy singleton)."""
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY)
    return _openai_client


# ── Prompt base para geração de changelog ──
CHANGELOG_SYSTEM_PROMPT = """És um Gestor de Produto experiente a redigir notas de lançamento de software.

REGRAS:
- Transforma logs técnicos num anúncio de lançamento amigável, focado em BENEFÍCIOS para o utilizador.
- Organiza por categorias usando emojis: 🚀 Novidades, 🛠️ Correções, ⚡ Melhorias, 🔒 Segurança.
- Usa Markdown com headers (##), bullets e negrito.
- Sê MUITO conciso — cada item em 1 linha, no máximo 2.
- Não menciones detalhes de implementação (código, ficheiros, endpoints).
- Escreve em Português de Portugal (pt-pt).
- Se não houver dados suficientes, responde com uma mensagem genérica amigável.
- Não inventes funcionalidades que não estejam nos dados fornecidos."""


def sanitize_source_text(text: str) -> str:
    """Sanitizar texto fonte para prevenir prompt injection na IA."""
    # Remover padrões perigosos
    dangerous_patterns = [
        "ignore previous instructions",
        "ignore the above",
        "disregard",
        "system:",
        "assistant:",
        "you are now",
    ]
    sanitized = text
    for pattern in dangerous_patterns:
        sanitized = sanitized.replace(pattern.lower(), "[redacted]")
        sanitized = sanitized.replace(pattern.upper(), "[redacted]")
    return sanitized


# ── Fontes de dados ──

def read_git_log(max_lines: int = 50) -> str:
    """Ler os últimos commits do Git como fonte para o changelog."""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={max_lines}", "--pretty=format:%h %s (%cr)", "--no-merges"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        logger.warning("git log retornou vazio ou erro: %s", result.stderr)
        return ""
    except Exception as e:
        logger.warning("Não foi possível ler git log: %s", e)
        return ""


def read_changelog_file(max_lines: int = 50) -> str:
    """Ler as últimas linhas do ficheiro CHANGELOG.md."""
    try:
        changelog_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "CHANGELOG.md"
        )
        if not os.path.exists(changelog_path):
            logger.warning("CHANGELOG.md não encontrado em %s", changelog_path)
            return ""
        with open(changelog_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Pegar as últimas N linhas
        return "".join(lines[-max_lines:]).strip()
    except Exception as e:
        logger.warning("Não foi possível ler CHANGELOG.md: %s", e)
        return ""


def read_worklog_file(max_lines: int = 50) -> str:
    """Ler as últimas linhas do ficheiro worklog.md."""
    try:
        worklog_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "worklog.md"
        )
        if not os.path.exists(worklog_path):
            logger.warning("worklog.md não encontrado em %s", worklog_path)
            return ""
        with open(worklog_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:]).strip()
    except Exception as e:
        logger.warning("Não foi possível ler worklog.md: %s", e)
        return ""


# ── Serviços ──

async def get_changelogs(limit: int = 5) -> List[Dict[str, Any]]:
    """Obter os últimos changelogs publicados (endpoint público)."""
    try:
        cursor = db.system_changelogs.find(
            {},
            {"_id": 1, "version": 1, "content_markdown": 1, "published_at": 1,
             "generated_by": 1, "source_summary": 1}
        ).sort("published_at", -1).limit(limit)
        changelogs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            changelogs.append(doc)
        return changelogs
    except Exception as e:
        logger.error("Erro ao obter changelogs: %s", e)
        return []


async def generate_changelog_ai(
    source_type: str = "git",
    max_source_lines: int = 50,
    custom_prompt_suffix: Optional[str] = None
) -> Dict[str, Any]:
    """
    Gerar notas de atualização por IA a partir de logs técnicos.
    
    Args:
        source_type: Fonte dos dados ('git', 'changelog_file', 'worklog')
        max_source_lines: Número máximo de linhas a ler
        custom_prompt_suffix: Sufixo opcional para o prompt
    
    Returns:
        Dict com o changelog criado e metadados
    """
    if not EMERGENT_LLM_KEY:
        raise ValueError("Chave API OpenAI não configurada (EMERGENT_LLM_KEY)")

    # 1. Recolher dados da fonte com fallback automático em cadeia
    # CORREÇÃO (Pacote AE-fix): no Render, a pasta .git não está disponível no
    # container de deploy, pelo que read_git_log() devolve "". O fallback agora
    # percorre uma cadeia: git → worklog → changelog_file, parando no primeiro
    # que devolver conteúdo. Isto garante que a geração por IA funciona mesmo
    # quando o git não está disponível.
    source_text = ""
    effective_source = source_type

    if source_type == "git":
        source_text = read_git_log(max_source_lines)
        if source_text:
            effective_source = "git"
        else:
            # Fallback 1: worklog.md (mais fiável no Render — ficheiro físico)
            logger.info("[CHANGELOG] git log indisponível, a tentar worklog.md (fallback)")
            source_text = read_worklog_file(max_source_lines)
            if source_text:
                effective_source = "worklog (fallback de git)"
            else:
                # Fallback 2: CHANGELOG.md
                logger.info("[CHANGELOG] worklog.md vazio, a tentar CHANGELOG.md (fallback)")
                source_text = read_changelog_file(max_source_lines)
                if source_text:
                    effective_source = "changelog_file (fallback de git)"
    elif source_type == "changelog_file":
        source_text = read_changelog_file(max_source_lines)
        if not source_text:
            # Fallback para worklog se CHANGELOG.md estiver vazio
            logger.info("[CHANGELOG] CHANGELOG.md vazio, a tentar worklog.md (fallback)")
            source_text = read_worklog_file(max_source_lines)
            if source_text:
                effective_source = "worklog (fallback de changelog_file)"
    elif source_type == "worklog":
        source_text = read_worklog_file(max_source_lines)
        if not source_text:
            # Fallback para CHANGELOG.md se worklog estiver vazio
            logger.info("[CHANGELOG] worklog.md vazio, a tentar CHANGELOG.md (fallback)")
            source_text = read_changelog_file(max_source_lines)
            if source_text:
                effective_source = "changelog_file (fallback de worklog)"
    else:
        raise ValueError(f"Fonte não suportada: {source_type}. Use 'git', 'changelog_file' ou 'worklog'")

    if not source_text:
        raise ValueError(
            f"Não foi possível obter dados de nenhuma fonte (tentado: git, worklog, changelog_file). "
            f"Verifique se os ficheiros worklog.md ou CHANGELOG.md existem na raiz do projeto."
        )

    # 2. Sanitizar texto fonte
    source_text = sanitize_source_text(source_text)

    # Truncar se muito longo (limite ~8000 chars para não exceder contexto)
    if len(source_text) > 8000:
        source_text = source_text[:8000] + "\n[... truncado]"

    # 3. Montar prompt
    user_prompt = f"""Aqui estão os dados técnicos recentes do nosso CRM (PowerCell - Crédito Habitacional):

--- INÍCIO DOS DADOS ---
{source_text}
--- FIM DOS DADOS ---

Transforma estes dados num anúncio de lançamento amigável para os utilizadores do CRM."""

    if custom_prompt_suffix:
        user_prompt += f"\n\nInstrução adicional: {sanitize_source_text(custom_prompt_suffix)}"

    # 4. Chamar IA com retry
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def call_ai():
        client = get_openai_client()
        response = await client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": CHANGELOG_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        return response

    try:
        response = await call_ai()
    except Exception as e:
        logger.error("Erro ao chamar IA para gerar changelog: %s", e)
        raise RuntimeError(f"Erro ao gerar changelog com IA: {str(e)}")

    # 5. Extrair resultado
    content_markdown = response.choices[0].message.content.strip()
    tokens_used = response.usage.total_tokens if response.usage else None

    # 6. Gerar versão (data atual)
    now = datetime.now(timezone.utc)
    version = now.strftime("%Y-%m-%d")

    # 7. Criar resumo da fonte (primeiras 200 chars)
    source_summary = source_text[:200] + "..." if len(source_text) > 200 else source_text

    # 8. Guardar na coleção system_changelogs
    doc = {
        "version": version,
        "content_markdown": content_markdown,
        "published_at": now,
        "generated_by": "ai",
        "source_summary": source_summary,
    }
    try:
        result = await db.system_changelogs.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        logger.info("Changelog gerado por IA e guardado: version=%s, id=%s", version, doc["id"])
    except Exception as e:
        logger.error("Erro ao guardar changelog na BD: %s", e)
        raise RuntimeError(f"Erro ao guardar changelog: {str(e)}")

    return {
        "changelog": doc,
        "tokens_used": tokens_used,
    }
