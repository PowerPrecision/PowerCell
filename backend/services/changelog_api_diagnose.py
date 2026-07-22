"""Changelog diagnose handler.

Extraído de `routes/changelog.py`.
Do **not** overwrite changelog_service.py — use changelog_api_*.
"""
from __future__ import annotations

import os

from services.changelog_service import (
    _resolve_project_file, read_worklog_file, read_changelog_file,
    get_ai_client_and_model, read_git_log,
)


async def run_diagnose_changelog_generation():
    report = {
        "checks": {},
        "can_generate": False,
        "blocking_issue": None,
    }

    worklog_local = _resolve_project_file("worklog.md")
    changelog_local = _resolve_project_file("CHANGELOG.md")

    report["checks"]["files"] = {
        "worklog_md_local_path": worklog_local,
        "changelog_md_local_path": changelog_local,
        "worklog_md_local_exists": worklog_local is not None,
        "changelog_md_local_exists": changelog_local is not None,
    }

    try:
        worklog_content = await read_worklog_file(10)
        report["checks"]["files"]["worklog_md_readable"] = bool(worklog_content)
        report["checks"]["files"]["worklog_md_sample"] = worklog_content[:100] if worklog_content else None
    except Exception as e:
        report["checks"]["files"]["worklog_md_readable"] = False
        report["checks"]["files"]["worklog_md_error"] = str(e)

    try:
        changelog_content = await read_changelog_file(10)
        report["checks"]["files"]["changelog_md_readable"] = bool(changelog_content)
        report["checks"]["files"]["changelog_md_sample"] = changelog_content[:100] if changelog_content else None
    except Exception as e:
        report["checks"]["files"]["changelog_md_readable"] = False
        report["checks"]["files"]["changelog_md_error"] = str(e)

    try:
        client, model = await get_ai_client_and_model()
        report["checks"]["ai_credentials"] = {
            "configured": client is not None,
            "model": model,
            "has_openai_env_key": bool(os.environ.get("OPENAI_API_KEY")),
            "has_emergent_env_key": bool(os.environ.get("EMERGENT_LLM_KEY")),
        }
    except Exception as e:
        report["checks"]["ai_credentials"] = {
            "configured": False,
            "error": str(e),
        }

    try:
        git_log = read_git_log(5)
        report["checks"]["git"] = {
            "available": bool(git_log),
            "sample": git_log[:100] if git_log else None,
        }
    except Exception as e:
        report["checks"]["git"] = {"available": False, "error": str(e)}

    has_source = (
        report["checks"]["files"].get("worklog_md_readable")
        or report["checks"]["files"].get("changelog_md_readable")
        or report["checks"]["git"].get("available")
    )
    has_credentials = report["checks"]["ai_credentials"].get("configured", False)

    if not has_credentials:
        report["blocking_issue"] = (
            "Credenciais de IA não configuradas. Configure no painel de administração "
            "(Configurações → IA) ou defina OPENAI_API_KEY / EMERGENT_LLM_KEY nas env vars."
        )
    elif not has_source:
        report["blocking_issue"] = (
            "Nenhuma fonte de dados disponível (worklog.md, CHANGELOG.md e git log todos vazios). "
            "Verifique se o fallback do GitHub está a funcionar."
        )
    else:
        report["can_generate"] = True
        report["blocking_issue"] = None

    return report
