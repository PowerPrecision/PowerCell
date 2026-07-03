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

INTEGRAÇÃO IA (Pacote AG — multi-provider):
- Lê as credenciais e o provider ativo da BD (system_config.ai),
  configurados pelo Admin via /api/admin/ai-config.
- Fallback gracioso para variáveis de ambiente (EMERGENT_LLM_KEY /
  OPENAI_API_KEY) se a BD não tiver config.
- Suporta providers OpenAI e Emergent (endpoint OpenAI-compatible).
- Prompt de Gestor de Produto que transforma logs técnicos em anúncios amigáveis
- Suporta sanitização de input para prevenir prompt injection

COLEÇÃO MONGODB: system_changelogs
====================================================================
"""
import os
import re
import subprocess
import logging
from typing import Optional, List, Dict, Any, Tuple
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

# ── Defaults (usados apenas se a BD não tiver configuração) ──
_DEFAULT_AI_MODEL = "gpt-4o-mini"

# PACOTE CC — limite de linhas fallback quando não há changelog anterior na BD
_DEFAULT_MAX_SOURCE_LINES = 50


# ====================================================================
# PACOTE CC — Obter data do último changelog gerado
# ====================================================================
async def _get_last_changelog_date() -> Optional[datetime]:
    """
    PACOTE CR — Procurar o último anúncio gerado na coleção announcements.

    Query: {"type": "changelog"}, sort=[("created_at", -1)].
    Retorna a data (created_at) do último anúncio, ou None se não houver.

    Fallback: se announcements não tiver registo, tenta system_changelogs
    (published_at) para retrocompatibilidade.
    """
    # 1. Tentar announcements (coleção do Mural da Equipa)
    try:
        last_announcement = await db.announcements.find_one(
            {"type": "changelog"},
            sort=[("created_at", -1)]
        )
        if last_announcement and "created_at" in last_announcement:
            raw = last_announcement["created_at"]
            if isinstance(raw, datetime):
                return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            if isinstance(raw, str):
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
    except Exception as e:
        logger.warning("[CHANGELOG-CR] Erro ao obter data do último announcement: %s", e)

    # 2. Fallback: system_changelogs (published_at)
    try:
        last_doc = await db.system_changelogs.find_one(
            {},
            {"_id": 0, "published_at": 1}
        )
        if last_doc and last_doc.get("published_at"):
            raw = last_doc["published_at"]
            if isinstance(raw, datetime):
                return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            if isinstance(raw, str):
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
    except Exception as e:
        logger.warning("[CHANGELOG-CR] Erro ao obter data do último changelog (fallback): %s", e)

    return None


# ====================================================================
# PACOTE CC — Filtragem por data em ficheiros Markdown
# ====================================================================
# Padrões de data em headers Markdown:
#   ## [2026-07-16] — Pacote CB: ...
#   ### Date: 2026-03-04
_MD_DATE_PATTERNS = [
    re.compile(r"^##\s*\[(\d{4}-\d{2}-\d{2})\]"),      # ## [2026-07-16]
    re.compile(r"^###\s*Date:\s*(\d{4}-\d{2}-\d{2})"),   # ### Date: 2026-03-04
    re.compile(r"^##\s*(\d{4}-\d{2}-\d{2})"),             # ## 2026-07-16
]


def _parse_md_date(line: str) -> Optional[datetime]:
    """Extrai datetime de uma linha de header Markdown, se contiver uma data."""
    for pattern in _MD_DATE_PATTERNS:
        match = pattern.match(line)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def _filter_lines_since(lines: List[str], since_date: Optional[datetime], max_lines: int) -> str:
    """
    Filtra linhas de um ficheiro Markdown para incluir apenas entradas
    posteriores a since_date.

    Heurística: percorre as linhas do FIM para o INÍCIO. Quando encontra
    um header com data <= since_date, para — tudo a partir daí é histórico.
    Se since_date for None ou não houver datas no ficheiro, usa max_lines
    como fallback (comportamento original).

    Returns:
        String com as linhas filtradas (apenas o delta recente).
    """
    if since_date is None:
        # Fallback: últimas max_lines linhas (comportamento original)
        return "".join(lines[-max_lines:]).strip()

    # Percorrer do fim para o início, coletando linhas até encontrar
    # um header com data <= since_date
    delta_lines: List[str] = []
    for line in reversed(lines):
        line_date = _parse_md_date(line)
        if line_date and line_date <= since_date:
            # Encontramos um header com data anterior ou igual à última
            # geração. Tudo a partir daqui é histórico — parar.
            break
        delta_lines.insert(0, line)

    if not delta_lines:
        logger.info("[CHANGELOG-CC] Nenhuma entrada nova desde %s — a usar fallback de %d linhas",
                     since_date.strftime("%Y-%m-%d"), max_lines)
        return "".join(lines[-max_lines:]).strip()

    logger.info("[CHANGELOG-CC] Filtrado %d linhas (delta desde %s)",
                 len(delta_lines), since_date.strftime("%Y-%m-%d"))
    return "".join(delta_lines).strip()


async def get_ai_client_and_model() -> Tuple[Optional[AsyncOpenAI], str]:
    """
    Obtém o cliente OpenAI e o modelo ativo a partir da configuração do sistema.

    PACOTE AG — Multi-provider:
    Lê as credenciais e o provider definidos pelo Admin na BD
    (coleção system_config, secção "ai"). Se a BD não tiver config,
    faz fallback para as variáveis de ambiente (EMERGENT_LLM_KEY /
    OPENAI_API_KEY) — retrocompatibilidade.

    Returns:
        Tuple (client, model):
        - client: AsyncOpenAI configurado, ou None se não houver credenciais.
        - model: Nome do modelo a usar (ex: "gpt-4o-mini").
    """
    api_key = None
    base_url = None
    model = _DEFAULT_AI_MODEL

    # 1. Tentar ler da BD (configuração do Admin)
    try:
        from services.system_config import get_system_config
        config = await get_system_config()
        ai_config = getattr(config, "ai", None)
        if ai_config:
            api_key = ai_config.api_key or None
            model = ai_config.model or model
            # Se o provider for Emergent, usar o endpoint compatível
            provider_value = getattr(ai_config, "provider", None)
            provider_str = provider_value.value if hasattr(provider_value, "value") else str(provider_value)
            if provider_str and "emergent" in provider_str.lower():
                base_url = os.environ.get("EMERGENT_BASE_URL", "https://api.emergent.ai/v1")
    except Exception as e:
        logger.warning("[CHANGELOG] Erro ao ler config de IA da BD, a usar fallback env: %s", e)

    # 2. Fallback para env vars se a BD não tiver api_key
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
        if api_key and api_key.startswith("sk-emerg"):
            base_url = os.environ.get("EMERGENT_BASE_URL", "https://api.emergent.ai/v1")

    if not api_key:
        return None, model

    # 3. Construir cliente
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    return AsyncOpenAI(**client_kwargs), model


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

# PACOTE AI: config do GitHub para fallback de ficheiros.
# No Render, o Docker build context é ./backend, pelo que worklog.md e
# CHANGELOG.md (na raiz do repo) não são incluídos na imagem. O fallback
# busca-os via GitHub raw URL (repo é público para fetch).
GITHUB_REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER", "PowerPrecision")
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "PowerCell")
GITHUB_REPO_BRANCH = os.environ.get("GITHUB_REPO_BRANCH", "dev")


def _resolve_project_file(filename: str) -> Optional[str]:
    """
    Resolve o caminho absoluto de um ficheiro na raiz do projeto.

    Tenta vários diretórios candidatos (cwd, repo_root, backend_dir).
    Retorna o caminho se encontrado, None caso contrário.
    """
    from pathlib import Path

    this_file = Path(__file__).resolve()
    backend_dir = this_file.parent.parent  # /app (pasta backend/)
    repo_root = backend_dir.parent          # raiz do repositório

    candidate_dirs = [
        Path.cwd(),                   # cwd atual
        repo_root,                    # raiz do repo (um nível acima de backend/)
        backend_dir,                  # pasta backend/ (fallback)
    ]

    for d in candidate_dirs:
        candidate = d / filename
        if candidate.exists() and candidate.is_file():
            logger.info("[CHANGELOG] Ficheiro '%s' encontrado localmente em %s", filename, candidate)
            return str(candidate)

    logger.warning(
        "[CHANGELOG] Ficheiro '%s' não encontrado localmente em: %s",
        filename, [str(d) for d in candidate_dirs]
    )
    return None


def _read_local_file_tail(filepath: str, max_lines: int, since_date: Optional[datetime] = None) -> str:
    """Lê as últimas N linhas de um ficheiro local, com filtragem por data opcional.

    PACOTE CC: se since_date for fornecido, filtra apenas as entradas posteriores
    a essa data (via _filter_lines_since). Se None, usa as últimas max_lines linhas.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return _filter_lines_since(lines, since_date, max_lines)


async def _fetch_from_github(filename: str, max_lines: int, since_date: Optional[datetime] = None) -> str:
    """
    Busca um ficheiro do GitHub via raw URL (fallback para produção).

    PACOTE AI: no Render, o Docker build context é ./backend, pelo que
    os ficheiros na raiz do repo (worklog.md, CHANGELOG.md) não são
    incluídos na imagem. Esta função busca-os directamente do GitHub
    via raw.githubusercontent.com (repo público, sem auth necessária).

    PACOTE CC: se since_date for fornecido, filtra apenas as entradas
    posteriores a essa data (via _filter_lines_since).

    Returns:
        Linhas filtradas do ficheiro, ou "" se falhar.
    """
    import httpx

    url = f"https://raw.githubusercontent.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/{GITHUB_REPO_BRANCH}/{filename}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("[CHANGELOG] GitHub raw devolveu %s para %s", resp.status_code, url)
                return ""
            text = resp.text
            lines = text.splitlines(keepends=True)
            filtered = _filter_lines_since(lines, since_date, max_lines)
            logger.info("[CHANGELOG] Ficheiro '%s' obtido do GitHub (%d linhas, filtrado para %d chars)",
                         filename, len(lines), len(filtered))
            return filtered
    except Exception as e:
        logger.warning("[CHANGELOG] Erro ao buscar '%s' do GitHub: %s", filename, e)
        return ""


def read_git_log(max_lines: int = 50, since_date: Optional[datetime] = None) -> str:
    """Ler os últimos commits do Git como fonte para o changelog.

    PACOTE CC: se since_date for fornecido, usa --since="{data}" em vez de
    --max-count, para obter apenas commits posteriores à última geração.
    Se since_date for None, usa --max-count como fallback (comportamento original).
    """
    try:
        cmd = ["git", "log", "--pretty=format:%h %s (%cr)", "--no-merges"]
        if since_date:
            # Formato ISO para --since: "2026-07-16T00:00:00"
            since_str = since_date.strftime("%Y-%m-%dT%H:%M:%S")
            cmd.insert(1, f"--since={since_str}")
            logger.info("[CHANGELOG-CC] git log --since=%s", since_str)
        else:
            cmd.insert(1, f"--max-count={max_lines}")

        result = subprocess.run(
            cmd,
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


async def read_changelog_file(max_lines: int = 50, since_date: Optional[datetime] = None) -> str:
    """Ler as últimas linhas do ficheiro CHANGELOG.md, com filtragem por data.

    PACOTE AI: tenta ficheiro local primeiro (_resolve_project_file).
    Se não encontrar (ex: no Render onde o build context é ./backend),
    faz fallback para GitHub raw URL.

    PACOTE CC: se since_date for fornecido, filtra apenas as entradas
    posteriores a essa data (via _filter_lines_since com parsing de
    headers Markdown ## [YYYY-MM-DD]).
    """
    try:
        # 1. Tentar ficheiro local
        changelog_path = _resolve_project_file("CHANGELOG.md")
        if changelog_path:
            return _read_local_file_tail(changelog_path, max_lines, since_date)

        # 2. Fallback: GitHub raw URL
        logger.info("[CHANGELOG] CHANGELOG.md não encontrado localmente, a tentar GitHub...")
        return await _fetch_from_github("CHANGELOG.md", max_lines, since_date)
    except Exception as e:
        logger.warning("Não foi possível ler CHANGELOG.md: %s", e)
        return ""


async def read_worklog_file(max_lines: int = 50, since_date: Optional[datetime] = None) -> str:
    """Ler as últimas linhas do ficheiro worklog.md, com filtragem por data.

    PACOTE AI: tenta ficheiro local primeiro (_resolve_project_file).
    Se não encontrar (ex: no Render onde o build context é ./backend),
    faz fallback para GitHub raw URL.

    PACOTE CC: se since_date for fornecido, filtra apenas as entradas
    posteriores a essa data (via _filter_lines_since com parsing de
    headers Markdown ### Date: YYYY-MM-DD).
    """
    try:
        # 1. Tentar ficheiro local
        worklog_path = _resolve_project_file("worklog.md")
        if worklog_path:
            return _read_local_file_tail(worklog_path, max_lines, since_date)

        # 2. Fallback: GitHub raw URL
        logger.info("[CHANGELOG] worklog.md não encontrado localmente, a tentar GitHub...")
        return await _fetch_from_github("worklog.md", max_lines, since_date)
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
    # PACOTE AG: a validação de credenciais foi movida para o passo 4,
    # onde get_ai_client_and_model() lê da BD (config do Admin) com
    # fallback para env vars. Isto respeita a regra multi-provider.

    # PACOTE CR — Obter a data do último anúncio/changelog gerado para filtrar
    # apenas as novidades introduzidas desde então. Se não houver registo
    # anterior, since_date = None e as funções de leitura usam max_source_lines
    # como fallback (comportamento original).
    since_date = await _get_last_changelog_date()
    since_date_str = since_date.strftime("%Y-%m-%d %H:%M") if since_date else "nunca"
    if since_date:
        logger.info("[CHANGELOG-CR] Último anúncio: %s — a filtrar fonte desde esta data",
                     since_date_str)
    else:
        logger.info("[CHANGELOG-CR] Nenhum anúncio anterior na BD — a usar fallback de %d linhas",
                     max_source_lines)

    # 1. Recolher dados da fonte com fallback automático em cadeia
    # CORREÇÃO (Pacote AE-fix): no Render, a pasta .git não está disponível no
    # container de deploy, pelo que read_git_log() devolve "". O fallback agora
    # percorre uma cadeia: git → worklog → changelog_file, parando no primeiro
    # que devolver conteúdo. Isto garante que a geração por IA funciona mesmo
    # quando o git não está disponível.
    source_text = ""
    effective_source = source_type

    if source_type == "git":
        source_text = read_git_log(max_source_lines, since_date=since_date)
        if source_text:
            effective_source = "git"
        else:
            # Fallback 1: worklog.md (mais fiável no Render — ficheiro físico)
            logger.info("[CHANGELOG] git log indisponível, a tentar worklog.md (fallback)")
            source_text = await read_worklog_file(max_source_lines, since_date=since_date)
            if source_text:
                effective_source = "worklog (fallback de git)"
            else:
                # Fallback 2: CHANGELOG.md
                logger.info("[CHANGELOG] worklog.md vazio, a tentar CHANGELOG.md (fallback)")
                source_text = await read_changelog_file(max_source_lines, since_date=since_date)
                if source_text:
                    effective_source = "changelog_file (fallback de git)"
    elif source_type == "changelog_file":
        source_text = await read_changelog_file(max_source_lines, since_date=since_date)
        if not source_text:
            # Fallback para worklog se CHANGELOG.md estiver vazio
            logger.info("[CHANGELOG] CHANGELOG.md vazio, a tentar worklog.md (fallback)")
            source_text = await read_worklog_file(max_source_lines, since_date=since_date)
            if source_text:
                effective_source = "worklog (fallback de changelog_file)"
    elif source_type == "worklog":
        source_text = await read_worklog_file(max_source_lines, since_date=since_date)
        if not source_text:
            # Fallback para CHANGELOG.md se worklog estiver vazio
            logger.info("[CHANGELOG] worklog.md vazio, a tentar CHANGELOG.md (fallback)")
            source_text = await read_changelog_file(max_source_lines, since_date=since_date)
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
    # PACOTE CR — Injeção obrigatória da data no prompt de sistema para
    # que o LLM faça o corte temporal mesmo que o código Python não consiga
    # filtrar perfeitamente (barreira de segurança extra).
    temporal_instruction = (
        f"IMPORTANTE: A última nota de atualização foi gerada em {since_date_str}. "
        f"A tua tarefa é extrair e resumir APENAS as novidades e alterações que tenham ocorrido DEPOIS dessa data. "
        f"Ignora completamente qualquer ponto do histórico que seja anterior a essa data."
    )

    system_prompt = CHANGELOG_SYSTEM_PROMPT + "\n\n" + temporal_instruction

    user_prompt = f"""Aqui estão os dados técnicos recentes do nosso CRM (PowerCell - Crédito Habitacional):

--- INÍCIO DOS DADOS ---
{source_text}
--- FIM DOS DADOS ---

Transforma estes dados num anúncio de lançamento amigável para os utilizadores do CRM."""

    if custom_prompt_suffix:
        user_prompt += f"\n\nInstrução adicional: {sanitize_source_text(custom_prompt_suffix)}"

    # 4. Obter cliente IA + modelo da configuração do sistema (Pacote AG)
    #    Lê as credenciais da BD (configuradas pelo Admin) com fallback para env vars.
    client, ai_model = await get_ai_client_and_model()
    if client is None:
        raise ValueError(
            "Nenhuma credencial de IA configurada. Configure o provider e a API key "
            "em /api/admin/ai-config (painel de administração) ou defina OPENAI_API_KEY / "
            "EMERGENT_LLM_KEY nas variáveis de ambiente."
        )

    # 5. Chamar IA com retry
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def call_ai():
        response = await client.chat.completions.create(
            model=ai_model,
            messages=[
                {"role": "system", "content": system_prompt},
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

    # 6. Extrair resultado
    content_markdown = response.choices[0].message.content.strip()
    tokens_used = response.usage.total_tokens if response.usage else None

    # 7. Gerar versão (data atual)
    now = datetime.now(timezone.utc)
    version = now.strftime("%Y-%m-%d")

    # 8. Criar resumo da fonte (primeiras 200 chars)
    source_summary = source_text[:200] + "..." if len(source_text) > 200 else source_text

    # 9. Guardar na coleção system_changelogs
    now_iso = now.isoformat()
    doc = {
        "version": version,
        "content_markdown": content_markdown,
        "published_at": now_iso,
        "generated_by": "ai",
        "source_summary": source_summary,
    }
    try:
        result = await db.system_changelogs.insert_one(doc)
        # PACOTE AS: insert_one adiciona _id (ObjectId) ao doc in-place.
        # Remover _id e usar id como string para evitar erro de serialização.
        doc.pop("_id", None)
        doc["id"] = str(result.inserted_id)
        logger.info("Changelog gerado por IA e guardado: version=%s, id=%s", version, doc["id"])
    except Exception as e:
        logger.error("Erro ao guardar changelog na BD: %s", e)
        raise RuntimeError(f"Erro ao guardar changelog: {str(e)}")

    return {
        "changelog": doc,
        "tokens_used": tokens_used,
    }
