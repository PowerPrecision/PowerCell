"""
====================================================================
AI Executive Summary & Cross-Reference Audit — PowerCell
====================================================================
Route module that provides AI-driven executive summaries with
cross-reference audit (declared vs. documented data) for credit
processes.

Endpoints:
  POST /api/processes/{process_id}/analyze  — generate or regenerate summary
  GET  /api/processes/{process_id}/analyze  — retrieve existing summary

Security:
  - Role-gated via `require_roles` (ADMIN, CEO, CONSULTOR, DIRETOR, ADMINISTRATIVO)
  - OpenAI data-training opt-out verified upstream in `get_openai_client`
  - In-memory concurrency lock prevents parallel analysis of the same process
  - Extracted text truncated to 8 000 chars per document; total context capped at ~30 000 chars
====================================================================
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.auth import UserRole
from services.auth import require_roles
from services.ai_document_analyzer import get_openai_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Executive Summary"])

# ---------------------------------------------------------------------------
# In-memory concurrency lock — prevents multiple concurrent analyses of the
# same process.  Keyed by process_id, value is the thread that owns the lock.
# Simple but effective for a single-worker deployment.  For multi-worker
# setups a distributed lock (Redis) would be required.
# ---------------------------------------------------------------------------
_analysis_locks: Dict[str, threading.Event] = {}


def _acquire_lock(process_id: str) -> bool:
    """Try to acquire an analysis lock for *process_id*.

    Returns True if the lock was acquired, False if another analysis is
    already in progress for this process.
    """
    if process_id in _analysis_locks:
        # Lock already held — check if it's still alive
        event = _analysis_locks[process_id]
        if not event.is_set():
            return False
        # Previous lock released — clean up and re-acquire
        del _analysis_locks[process_id]

    _analysis_locks[process_id] = threading.Event()
    return True


def _release_lock(process_id: str) -> None:
    """Release the analysis lock for *process_id*."""
    event = _analysis_locks.pop(process_id, None)
    if event is not None:
        event.set()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MAX_TEXT_PER_DOC = 8_000       # chars
_MAX_TOTAL_CONTEXT = 30_000     # chars
_AI_MODEL = "gpt-4o-mini"
_AI_TEMPERATURE = 0.2

# ---------------------------------------------------------------------------
# System prompt (Portuguese)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
És um **Analista de Risco de Crédito Sénior** de uma intermediária de crédito em Portugal.

O teu objectivo é produzir um **Resumo Executivo** em **Markdown** que cruze os dados declarados \
pelo cliente no formulário do processo com os dados comprovados extraídos dos documentos \
(CC, IRS, recibos de vencimento, extratos bancários, caderneta predial, etc.).

## Instruções

1. **Sê objectivo e baseado em dados.** Não inventes informação; usa apenas o que está \
disponível no contexto fornecido.
2. **Compara ativamente** os valores declarados com os comprovados. Quando houver \
divergências, sinaliza-as com clareza.
3. **Formatação obrigatória** — o output DEVE conter exactamente as secções abaixo, \
em Markdown:

---

### 📋 Resumo Executivo
Perfil rápido do cliente: nome, idade/profissão, estado civil, tipo de emprego, \
nº de agregado familiar, se há 2.º titular. Resumo em 3-4 linhas.

### 💰 Saúde Financeira
- Rendimento mensal declarado vs. rendimento comprovado (recibos / IRS)
- Estimativa de DSTI (razão entre prestação + créditos e rendimento líquido)
- Avaliação da capacidade financeira (suficiente / limitada / insuficiente)
- Créditos existentes e encargos mensais

### ✅ Pontos Fortes
Factores positivos que favorecem a aprovação bancária:
- Emprego estável (efectivo / termo indeterminado)
- Bom DSTI (< 35 %)
- Entrada significativa
- Sem créditos em incumprimento
- Outros factores relevantes

### 🔴 Alertas de Divergência (CRÍTICO)
Cruza os dados declarados no formulário com os extraídos dos documentos. \
Para cada divergência encontrada indica:
- **Campo** (ex.: rendimento, estado civil, NIF)
- **Declarado:** valor indicado pelo cliente
- **Comprovado:** valor extraído dos documentos
- Usa **negrito** e emoji 🔴 para realçar cada divergência.

Se NÃO houver divergências, escreve:
> ✅ Os documentos validam a informação declarada pelo cliente.

### 📝 Conclusão
Avaliação global de viabilidade do processo e uma recomendação \
(favorável / favorável com condições / desfavorável). Inclui sugestões \
de acção (ex.: solicitar mapa de responsabilidades actualizado, \
confirmar rendimentos adicionais, etc.).

---

4. **Idioma:** Português de Portugal.
5. **Tom:** Profissional, objectivo, directo.
6. **Não uses** fences de código (```` ``` ````) à volta do output — \
responde apenas em Markdown puro."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_dict(
    data: Optional[Dict[str, Any]],
    prefix: str = "",
    max_depth: int = 3,
    _current_depth: int = 0,
) -> Dict[str, Any]:
    """Flatten a nested dict into dot-separated keys for display."""
    if data is None or _current_depth >= max_depth:
        return {}
    result: Dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict) and _current_depth < max_depth - 1:
            result.update(_flatten_dict(value, full_key, max_depth, _current_depth + 1))
        elif isinstance(value, list):
            # Represent lists as a simple count + first few items
            if len(value) == 0:
                result[full_key] = "[]"
            elif len(value) <= 3:
                result[full_key] = str(value)
            else:
                result[full_key] = f"[{len(value)} itens] (primeiros: {value[:2]})"
        elif value is not None and str(value).strip():
            result[full_key] = value
    return result


def _format_declared_section(process: Dict[str, Any]) -> str:
    """Build the 'DADOS DECLARADOS' section from the process form data."""
    sections: List[str] = []

    # Personal data
    personal = process.get("personal_data") or {}
    if personal:
        flat = _flatten_dict(personal)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados Pessoais (Titular 1)\n" + "\n".join(lines))

    # Second titular
    t2 = process.get("titular2_data") or {}
    if t2:
        flat = _flatten_dict(t2)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados Pessoais (Titular 2)\n" + "\n".join(lines))

    # Financial data
    financial = process.get("financial_data") or {}
    if financial:
        flat = _flatten_dict(financial)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados Financeiros\n" + "\n".join(lines))

    # Real estate data
    real_estate = process.get("real_estate_data") or {}
    if real_estate:
        flat = _flatten_dict(real_estate)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados do Imóvel\n" + "\n".join(lines))

    # Credit data
    credit = process.get("credit_data") or {}
    if credit:
        flat = _flatten_dict(credit)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados de Crédito\n" + "\n".join(lines))

    header = "DADOS DECLARADOS (FORMULÁRIO DO PROCESSO):"
    body = "\n\n".join(sections) if sections else "  (sem dados declarados)"
    return f"{header}\n\n{body}"


def _format_documented_section(
    doc_metadata: List[Dict[str, Any]],
    analyzed_documents: Optional[List[Dict[str, Any]]],
) -> str:
    """Build the 'DADOS COMPROVADOS' section from extracted texts & fields."""
    parts: List[str] = []

    # 1) From document_metadata (extracted_text)
    for doc in doc_metadata:
        filename = doc.get("filename", "desconhecido")
        category = doc.get("ai_category", "")
        subcategory = doc.get("ai_subcategory", "")
        extracted_text = doc.get("extracted_text", "")
        ai_summary = doc.get("ai_summary", "")

        label = filename
        if category:
            label += f" [{category}"
            if subcategory:
                label += f" / {subcategory}"
            label += "]"

        doc_lines: List[str] = [f"### 📄 {label}"]
        if extracted_text:
            # Truncate per document
            if len(extracted_text) > _MAX_TEXT_PER_DOC:
                extracted_text = extracted_text[:_MAX_TEXT_PER_DOC] + "\n... [truncado]"
            doc_lines.append(f"\n{extracted_text}")
        elif ai_summary:
            doc_lines.append(f"\n{ai_summary}")
        else:
            doc_lines.append("\n  (sem texto extraído)")

        parts.append("\n".join(doc_lines))

    # 2) From analyzed_documents (fields_extracted)
    if analyzed_documents:
        analyzed_lines: List[str] = ["### 🔍 Campos Extraídos pela IA (análise individual)"]
        for adoc in analyzed_documents:
            doc_type = adoc.get("document_type", "")
            doc_filename = adoc.get("filename", "")
            fields = adoc.get("fields_extracted") or {}
            if fields:
                flat = _flatten_dict(fields)
                if flat:
                    analyzed_lines.append(f"\n**{doc_filename or doc_type}**")
                    for k, v in flat.items():
                        analyzed_lines.append(f"  - {k}: {v}")

        if len(analyzed_lines) > 1:
            parts.append("\n".join(analyzed_lines))

    header = "DADOS COMPROVADOS (EXTRAÍDOS DOS DOCUMENTOS):"
    body = "\n\n".join(parts) if parts else "  (nenhum documento analisado)"
    return f"{header}\n\n{body}"


def _sanitize_ai_response(text: str) -> str:
    """Sanitize the AI response to ensure clean Markdown output.

    - Strip leading/trailing whitespace
    - Remove ```json or ```markdown fences if the AI wrapped its output
    - Remove raw JSON if the AI returned JSON instead of Markdown
    """
    if not text:
        return ""

    text = text.strip()

    # Remove fenced code blocks that the AI might have added
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove opening fence (```json, ```markdown, ```)
        while lines and lines[0].strip().startswith("```"):
            lines.pop(0)
        # Remove closing fence
        while lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines).strip()

    # If the entire response looks like raw JSON, wrap it in a readable block
    if text.startswith("{") and text.endswith("}"):
        import json
        try:
            parsed = json.loads(text)
            text = "```json\n" + json.dumps(parsed, indent=2, ensure_ascii=False) + "\n```"
        except (json.JSONDecodeError, ValueError):
            pass  # Not valid JSON — return as-is

    return text


def _build_context(
    process: Dict[str, Any],
    doc_metadata: List[Dict[str, Any]],
    analyzed_documents: Optional[List[Dict[str, Any]]],
) -> str:
    """Assemble the full context string sent to the LLM.

    Enforces the _MAX_TOTAL_CONTEXT character budget.
    """
    declared = _format_declared_section(process)
    documented = _format_documented_section(doc_metadata, analyzed_documents)

    # Process metadata header
    process_number = process.get("process_number", "N/A")
    client_name = process.get("client_name", "N/A")
    status = process.get("status", "N/A")
    created_at = process.get("created_at", "")

    header = (
        f"## Processo #{process_number}\n"
        f"- Cliente: {client_name}\n"
        f"- Estado: {status}\n"
        f"- Criado em: {created_at or 'N/A'}\n"
    )

    full_context = f"{header}\n\n{declared}\n\n{documented}"

    # Enforce total context limit
    if len(full_context) > _MAX_TOTAL_CONTEXT:
        # Truncate the documented section first (less critical)
        declared_len = len(header) + len(declared) + 4  # +4 for newlines
        documented_budget = _MAX_TOTAL_CONTEXT - declared_len
        if documented_budget < 500:
            documented_budget = 500  # minimum documented section
        documented = documented[:documented_budget] + "\n\n... [contexto truncado]"
        full_context = f"{header}\n\n{declared}\n\n{documented}"

    return full_context


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/processes/{process_id}/analyze",
    summary="Retrieve existing AI executive summary",
)
async def get_analysis(
    process_id: str,
    user: dict = Depends(require_roles([
        UserRole.ADMIN,
        UserRole.CEO,
        UserRole.CONSULTOR,
        UserRole.DIRETOR,
        UserRole.ADMINISTRATIVO,
    ])),
) -> Dict[str, Any]:
    """Return the existing ``ai_executive_summary`` and ``ai_analysis_date``
    stored on the process document.  No AI call is made.

    **Roles:** ADMIN, CEO, CONSULTOR, DIRETOR, ADMINISTRATIVO

    **Returns 404** if the process does not exist.
    """
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "ai_executive_summary": 1, "ai_analysis_date": 1, "id": 1},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    return {
        "process_id": process_id,
        "ai_executive_summary": process.get("ai_executive_summary"),
        "ai_analysis_date": process.get("ai_analysis_date"),
    }


@router.post(
    "/processes/{process_id}/analyze",
    summary="Generate AI executive summary with cross-reference audit",
)
async def generate_analysis(
    process_id: str,
    force: bool = Query(
        default=False,
        description="Force re-analysis even if a summary already exists",
    ),
    user: dict = Depends(require_roles([
        UserRole.ADMIN,
        UserRole.CEO,
        UserRole.CONSULTOR,
        UserRole.DIRETOR,
        UserRole.ADMINISTRATIVO,
    ])),
) -> Dict[str, Any]:
    """Generate (or regenerate) an AI executive summary for a credit process.

    The AI cross-references **declared form data** with **documented data**
    extracted from uploaded documents (CC, IRS, salary receipts, bank
    statements, etc.) and produces a structured Markdown report.

    **Parameters:**
    - ``force`` (query): set to ``true`` to re-analyze even if a summary
      already exists.

    **Behaviour:**
    1. Fetches the full process and associated document metadata.
    2. Builds a structured context string (declared + documented data).
    3. Sends to OpenAI ``gpt-4o-mini`` (temperature=0.2).
    4. Saves ``ai_executive_summary`` and ``ai_analysis_date`` to the process.
    5. Returns the summary and timestamp.

    **Error responses:**
    - ``404`` — process not found
    - ``403`` — insufficient permissions (raised by ``require_roles``)
    - ``409`` — another analysis is already running for this process
    - ``503`` — OpenAI API key not configured

    **Roles:** ADMIN, CEO, CONSULTOR, DIRETOR, ADMINISTRATIVO
    """
    # ------------------------------------------------------------------
    # 0. Verify OpenAI is configured
    # ------------------------------------------------------------------
    client = get_openai_client()
    if client is None:
        logger.error("OpenAI client not configured — cannot run executive summary")
        raise HTTPException(
            status_code=503,
            detail="Serviço de IA não configurado. Configure OPENAI_API_KEY nas variáveis de ambiente.",
        )

    # ------------------------------------------------------------------
    # 1. Fetch full process
    # ------------------------------------------------------------------
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # ------------------------------------------------------------------
    # 2. Check existing summary (skip if present unless force=True)
    # ------------------------------------------------------------------
    if not force and process.get("ai_executive_summary"):
        return {
            "process_id": process_id,
            "ai_executive_summary": process["ai_executive_summary"],
            "ai_analysis_date": process.get("ai_analysis_date"),
            "cached": True,
        }

    # ------------------------------------------------------------------
    # 3. Acquire concurrency lock
    # ------------------------------------------------------------------
    if not _acquire_lock(process_id):
        raise HTTPException(
            status_code=409,
            detail="Já existe uma análise em curso para este processo. Aguarde a conclusão ou use force=true.",
        )

    user_email = user.get("email", "unknown")

    try:
        # ------------------------------------------------------------------
        # 4. Fetch document metadata
        # ------------------------------------------------------------------
        doc_metadata_cursor = db.document_metadata.find(
            {"process_id": process_id},
            {
                "_id": 0,
                "filename": 1,
                "ai_category": 1,
                "ai_subcategory": 1,
                "extracted_text": 1,
                "ai_summary": 1,
            },
        )
        doc_metadata: List[Dict[str, Any]] = await doc_metadata_cursor.to_list(length=200)

        # ------------------------------------------------------------------
        # 5. Get analyzed_documents from the process itself
        # ------------------------------------------------------------------
        analyzed_documents: Optional[List[Dict[str, Any]]] = process.get("analyzed_documents")

        # ------------------------------------------------------------------
        # 6. Build context
        # ------------------------------------------------------------------
        context = _build_context(process, doc_metadata, analyzed_documents)

        logger.info(
            "AI analysis started for process %s (user=%s, docs=%d, context=%d chars)",
            process_id,
            user_email,
            len(doc_metadata),
            len(context),
        )

        # ------------------------------------------------------------------
        # 7. Call OpenAI
        # ------------------------------------------------------------------
        response = await client.chat.completions.create(
            model=_AI_MODEL,
            temperature=_AI_TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            max_tokens=4_096,
        )

        raw_summary = response.choices[0].message.content or ""
        summary = _sanitize_ai_response(raw_summary)

        # ------------------------------------------------------------------
        # 8. Persist to process
        # ------------------------------------------------------------------
        analysis_date = datetime.now(timezone.utc).isoformat()

        await db.processes.update_one(
            {"id": process_id},
            {
                "$set": {
                    "ai_executive_summary": summary,
                    "ai_analysis_date": analysis_date,
                }
            },
        )

        logger.info(
            "AI analysis completed for process %s (user=%s, summary_len=%d chars)",
            process_id,
            user_email,
            len(summary),
        )

        return {
            "process_id": process_id,
            "ai_executive_summary": summary,
            "ai_analysis_date": analysis_date,
        }

    except HTTPException:
        # Re-raise HTTP exceptions (auth, 404, 503) without wrapping
        raise
    except Exception as exc:
        logger.error(
            "AI analysis failed for process %s (user=%s): %s",
            process_id,
            user_email,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar análise: {str(exc)}",
        )
    finally:
        _release_lock(process_id)
