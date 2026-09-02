"""
====================================================================
SERVIÇO: Companies — Teste de Ligação SMTP/IMAP (ad-hoc, sem gravar)
====================================================================
Testa as credenciais SMTP e/ou IMAP fornecidas diretamente pelo
formulário de configuração de email de uma Empresa (CompaniesAdminTab),
antes de gravar. Cada protocolo é testado de forma independente porque
a Empresa pode ter contas SMTP e IMAP distintas.
====================================================================
"""
import asyncio
import imaplib
import smtplib
import ssl

import certifi
from fastapi import HTTPException

from models.company import CompanyEmailConnectionTest

_TEST_TIMEOUT_SECONDS = 15.0


def _friendly_error(raw_err: str, protocol: str) -> str:
    """Traduz erros técnicos de SMTP/IMAP para mensagens claras em português."""
    err_lower = raw_err.lower()
    if "authenticationfailed" in err_lower or ("auth" in err_lower and "fail" in err_lower) or "invalid credentials" in err_lower or "not accepted" in err_lower or "badcredentials" in err_lower or "username and password" in err_lower:
        return f"{protocol}: credenciais inválidas. Verifique o email e a password."
    if "connection refused" in err_lower:
        return f"{protocol}: ligação recusada. Verifique o servidor e a porta."
    if "timed out" in err_lower or "timeout" in err_lower:
        return f"{protocol}: tempo de ligação esgotado. Verifique o servidor, a porta e a rede."
    if "ssl" in err_lower or "certificate" in err_lower:
        return f"{protocol}: erro de certificado SSL/TLS."
    if "name resolution" in err_lower or "not known" in err_lower or "nodename nor servname" in err_lower:
        return f"{protocol}: servidor não encontrado. Verifique o endereço."
    if "network is unreachable" in err_lower:
        return f"{protocol}: rede inacessível."
    return f"{protocol}: não foi possível ligar ({raw_err[:150]})."


def _test_smtp_sync(host: str, port: int, email: str, password: str) -> None:
    """Liga-se ao servidor SMTP e autentica (SSL implícito na porta 465, STARTTLS nas restantes)."""
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    port = int(port) if port else 587
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, context=ssl_context, timeout=_TEST_TIMEOUT_SECONDS)
    else:
        server = smtplib.SMTP(host, port, timeout=_TEST_TIMEOUT_SECONDS)
        server.ehlo()
        server.starttls(context=ssl_context)
        server.ehlo()
    try:
        server.login(email, password)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _test_imap_sync(host: str, port: int, email: str, password: str) -> None:
    """Liga-se ao servidor IMAP (SSL) e autentica."""
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    port = int(port) if port else 993
    conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl_context, timeout=_TEST_TIMEOUT_SECONDS)
    try:
        conn.login(email, password)
    finally:
        try:
            conn.logout()
        except Exception:
            pass


async def run_test_email_connection(data: CompanyEmailConnectionTest) -> dict:
    """Testa SMTP e/ou IMAP com os dados atuais do formulário, cada um de forma independente."""
    results = {}
    failures = []
    tested_any = False

    if data.smtp_host and data.smtp_email and data.smtp_password:
        tested_any = True
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_test_smtp_sync, data.smtp_host, data.smtp_port, data.smtp_email, data.smtp_password),
                timeout=_TEST_TIMEOUT_SECONDS + 5,
            )
            results["smtp"] = {"success": True, "message": "Ligação SMTP validada com sucesso."}
        except asyncio.TimeoutError:
            msg = "SMTP: tempo de ligação esgotado."
            results["smtp"] = {"success": False, "message": msg}
            failures.append(msg)
        except Exception as exc:
            msg = _friendly_error(str(exc), "SMTP")
            results["smtp"] = {"success": False, "message": msg}
            failures.append(msg)

    if data.imap_host and data.imap_email and data.imap_password:
        tested_any = True
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_test_imap_sync, data.imap_host, data.imap_port, data.imap_email, data.imap_password),
                timeout=_TEST_TIMEOUT_SECONDS + 5,
            )
            results["imap"] = {"success": True, "message": "Ligação IMAP validada com sucesso."}
        except asyncio.TimeoutError:
            msg = "IMAP: tempo de ligação esgotado."
            results["imap"] = {"success": False, "message": msg}
            failures.append(msg)
        except Exception as exc:
            msg = _friendly_error(str(exc), "IMAP")
            results["imap"] = {"success": False, "message": msg}
            failures.append(msg)

    if not tested_any:
        raise HTTPException(
            status_code=400,
            detail="Preencha o email, a password e o servidor de SMTP e/ou IMAP para testar a ligação.",
        )

    if failures:
        raise HTTPException(status_code=400, detail=" | ".join(failures))

    return {"success": True, "results": results}
