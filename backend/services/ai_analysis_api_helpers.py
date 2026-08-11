"""Helpers for AI executive-summary analysis API.

Extraído de `routes/ai_analysis.py`. Prefer `ai_analysis_api_*` —
do **not** overwrite `ai_document_analyzer.py` / `ai_page_analyzer.py` /
`ai_document.py`.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# In-memory concurrency lock — prevents multiple concurrent analyses of the
# same process.  Keyed by process_id, value is the thread that owns the lock.
# Simple but effective for a single-worker deployment.  For multi-worker
# setups a distributed lock (Redis) would be required.
# ---------------------------------------------------------------------------
_analysis_locks: Dict[str, threading.Event] = {}

_MAX_TEXT_PER_DOC = 8_000       # chars
_MAX_TOTAL_CONTEXT = 30_000     # chars
_AI_MODEL = "gpt-4o-mini"
_AI_TEMPERATURE = 0.2

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


def acquire_lock(process_id: str) -> bool:
    """Try to acquire an analysis lock for *process_id*.

    Returns True if the lock was acquired, False if another analysis is
    already in progress for this process.
    """
    if process_id in _analysis_locks:
        event = _analysis_locks[process_id]
        if not event.is_set():
            return False
        del _analysis_locks[process_id]

    _analysis_locks[process_id] = threading.Event()
    return True


def release_lock(process_id: str) -> None:
    """Release the analysis lock for *process_id*."""
    event = _analysis_locks.pop(process_id, None)
    if event is not None:
        event.set()


# Private aliases matching the original route names
_acquire_lock = acquire_lock
_release_lock = release_lock


def flatten_dict(
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
            result.update(flatten_dict(value, full_key, max_depth, _current_depth + 1))
        elif isinstance(value, list):
            if len(value) == 0:
                result[full_key] = "[]"
            elif len(value) <= 3:
                result[full_key] = str(value)
            else:
                result[full_key] = f"[{len(value)} itens] (primeiros: {value[:2]})"
        elif value is not None and str(value).strip():
            result[full_key] = value
    return result


_flatten_dict = flatten_dict


def format_declared_section(process: Dict[str, Any]) -> str:
    """Build the 'DADOS DECLARADOS' section from the process form data."""
    sections: List[str] = []

    personal = process.get("personal_data") or {}
    if personal:
        flat = flatten_dict(personal)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados Pessoais (Titular 1)\n" + "\n".join(lines))

    t2 = process.get("titular2_data") or {}
    if t2:
        flat = flatten_dict(t2)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados Pessoais (Titular 2)\n" + "\n".join(lines))

    financial = process.get("financial_data") or {}
    if financial:
        flat = flatten_dict(financial)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados Financeiros\n" + "\n".join(lines))

    real_estate = process.get("real_estate_data") or {}
    if real_estate:
        flat = flatten_dict(real_estate)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados do Imóvel\n" + "\n".join(lines))

    credit = process.get("credit_data") or {}
    if credit:
        flat = flatten_dict(credit)
        if flat:
            lines = [f"  - **{k}**: {v}" for k, v in flat.items()]
            sections.append("### Dados de Crédito\n" + "\n".join(lines))

    header = "DADOS DECLARADOS (FORMULÁRIO DO PROCESSO):"
    body = "\n\n".join(sections) if sections else "  (sem dados declarados)"
    return f"{header}\n\n{body}"


_format_declared_section = format_declared_section


def format_documented_section(
    doc_metadata: List[Dict[str, Any]],
    analyzed_documents: Optional[List[Dict[str, Any]]],
) -> str:
    """Build the 'DADOS COMPROVADOS' section from extracted texts & fields."""
    parts: List[str] = []

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
            if len(extracted_text) > _MAX_TEXT_PER_DOC:
                extracted_text = extracted_text[:_MAX_TEXT_PER_DOC] + "\n... [truncado]"
            doc_lines.append(f"\n{extracted_text}")
        elif ai_summary:
            doc_lines.append(f"\n{ai_summary}")
        else:
            doc_lines.append("\n  (sem texto extraído)")

        parts.append("\n".join(doc_lines))

    if analyzed_documents:
        analyzed_lines: List[str] = ["### 🔍 Campos Extraídos pela IA (análise individual)"]
        for adoc in analyzed_documents:
            doc_type = adoc.get("document_type", "")
            doc_filename = adoc.get("filename", "")
            fields = adoc.get("fields_extracted") or {}
            if fields:
                flat = flatten_dict(fields)
                if flat:
                    analyzed_lines.append(f"\n**{doc_filename or doc_type}**")
                    for k, v in flat.items():
                        analyzed_lines.append(f"  - {k}: {v}")

        if len(analyzed_lines) > 1:
            parts.append("\n".join(analyzed_lines))

    header = "DADOS COMPROVADOS (EXTRAÍDOS DOS DOCUMENTOS):"
    body = "\n\n".join(parts) if parts else "  (nenhum documento analisado)"
    return f"{header}\n\n{body}"


_format_documented_section = format_documented_section


def sanitize_ai_response(text: str) -> str:
    """Sanitize the AI response to ensure clean Markdown output."""
    if not text:
        return ""

    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        while lines and lines[0].strip().startswith("```"):
            lines.pop(0)
        while lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines).strip()

    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            text = "```json\n" + json.dumps(parsed, indent=2, ensure_ascii=False) + "\n```"
        except (json.JSONDecodeError, ValueError):
            pass

    return text


_sanitize_ai_response = sanitize_ai_response


def build_context(
    process: Dict[str, Any],
    doc_metadata: List[Dict[str, Any]],
    analyzed_documents: Optional[List[Dict[str, Any]]],
) -> str:
    """Assemble the full context string sent to the LLM."""
    declared = format_declared_section(process)
    documented = format_documented_section(doc_metadata, analyzed_documents)

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

    if len(full_context) > _MAX_TOTAL_CONTEXT:
        declared_len = len(header) + len(declared) + 4
        documented_budget = _MAX_TOTAL_CONTEXT - declared_len
        if documented_budget < 500:
            documented_budget = 500
        documented = documented[:documented_budget] + "\n\n... [contexto truncado]"
        full_context = f"{header}\n\n{declared}\n\n{documented}"

    return full_context


_build_context = build_context
