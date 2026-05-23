"""
====================================================================
GOV SCRAPER v2 — Automação de Portais Governamentais Portugueses
====================================================================
Serviço de RPA (Robotic Process Automation) que utiliza Playwright
em modo headless para extrair documentos dos portais:

1. Portal das Finanças (via Autenticação.gov / acesso.gov.pt)
   - Declaração de IRS
   - Nota de Liquidação de IRS

2. Segurança Social Direta (app.seg-social.pt)
   - Declaração de Situação Contributiva
   - Extrato de Remunerações

v2 MELHORIAS:
- playwright-stealth: disfarça o headless browser (evita anti-bot)
- User-Agent atualizado (Chrome 131)
- Selectors robustos com fallbacks múltiplos
- Screenshot automático em caso de falha (base64, para debug)
- Retry com backoff exponencial (2 tentativas)
- Espera por elementos específicos em vez de networkidle genérico
- Melhor categorização de erros (login_falhado, mfa_requerido,
  selector_desatualizado, timeout, sem_documentos)

SEGURANÇA (CRÍTICO):
- As credenciais (NIF/NISS + password) NUNCA são guardadas na BD.
- São usadas APENAS em memória durante a sessão do Playwright.
- Após a execução, as variáveis são limpas com `del` + `gc.collect()`.
- Nunca são impressas no terminal (log) ou persistidas de qualquer forma.
- O browser é executado em modo headless (sem interface gráfica).
====================================================================
"""

import base64
import gc
import logging
import os
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ================================================================
# CONFIGURAÇÃO — URLs e Selectors (v2 — atualizados 2025)
# ================================================================

# Portal das Finanças (via acesso.gov.pt v2 — Maio 2025)
# A página antiga (/unauthlogin) já não funciona. Usar a nova URL v2 com
# selectedAuthMethod=N para abrir directamente o separador NIF.
FINANCAS_AUTH_URL = (
    "https://www.acesso.gov.pt/v2/loginForm"
    "?partID=PFIN&path=/geral/dashboard&selectedAuthMethod=N"
)

# Selectors do portal acesso.gov.pt (autenticação) — v3 (Maio 2025)
# A nova UI usa Radix UI tabs + classes auto-geradas. Selectors estáveis:
#   - input[name="username"] / input[name="password"]
#   - button[type="submit"] (texto "Autenticar")
#   - button[role="tab"] com texto "NIF" / "CC / CMD"
FINANCAS_SEL = {
    # Página de login — tab NIF (Radix UI)
    "login_tab_nif": [
        "#login-form button[role='tab']:has-text('NIF')",
        "button[role='tab']:has-text('NIF')",
        "[id$='-trigger-N']",
        "#tabNif",  # legado, mantido por segurança
    ],
    # Campo NIF (Número de Contribuinte)
    "nif_input": [
        "#login-form input[name='username']",
        "input[name='username']",
        "input[placeholder*='Contribuinte']",
        "input[aria-label*='Contribuinte']",
        "input[autocomplete='username']",
        "#NIF",  # legado
    ],
    # Campo Password
    "password_input": [
        "#login-form input[name='password']",
        "input[name='password']",
        "input[type='password']",
        "input[placeholder*='Senha']",
        "input[autocomplete='current-password']",
        "#password",
    ],
    # Botão de login ("Autenticar")
    "login_button": [
        "#login-form button[type='submit']",
        "form[name='loginForm'] button[type='submit']",
        "button[type='submit']:has-text('Autenticar')",
        "button:has-text('Autenticar')",
        "button[type='submit']",
        "input[type='submit']",
    ],
    # Erro de login
    "login_error": [
        ".alert-danger",
        ".error-message",
        ".login-error",
        ".alert.alert-danger",
        "[role='alert']",
        ".error-container",
    ],
    # Pós-login — navegação para IRS
    "irs_menu": [
        "a[href*='irs']",
        "a[title*='IRS']",
        "a:has-text('IRS')",
        "a:has-text('Declarações')",
        "nav a:has-text('IRS')",
    ],
    "declaracoes_link": [
        "a[href*='declaracao']",
        "a:has-text('Declara')",
        "a:has-text('Consultar declara')",
    ],
    "nota_liquidacao_link": [
        "a[href*='liquidacao']",
        "a:has-text('Nota de Liquida')",
        "a:has-text('liquidação')",
    ],
    # Download
    "download_button": [
        "a[href*='download']",
        "a[href*='.pdf']",
        "button:has-text('Descarregar')",
        "a:has-text('Descarregar')",
        "a:has-text('Guardar')",
        "a[title*='download']",
    ],
    "pdf_link": [
        "a[href$='.pdf']",
        "a[href*='.pdf']",
    ],
}

# Segurança Social Direta (SSD) — Maio 2025
# A URL antiga /ptss/ redireciona para a homepage pública (não pede login).
# A URL correta para o formulário de autenticação é /sso/login (CAS/SSO).
SEG_SOCIAL_URL = "https://app.seg-social.pt/sso/login"

# Selectors da Segurança Social — v3 (Maio 2025)
# A SSD usa CAS (SSO Java) com #username / #password / #submitBtn
SEG_SOCIAL_SEL = {
    # Toggle para expandir o formulário "Autenticar com utilizador da SS"
    # (na nova SSD, o formulário aparece colapsado por defeito)
    "auth_toggle": [
        "#toogleAuth",
        "a[onclick*='abrirSlideAutenticacao']",
        "a:has-text('Autenticar com utilizador da Segurança Social')",
    ],
    "niss_input": [
        "#username",
        "input[name='username']",
        "input[id='username']",
        "#niss",
        "input[name='niss']",
        "input[placeholder*='NISS']",
    ],
    "password_input": [
        "#password",
        "input[name='password']",
        "input[type='password']",
        "input[autocomplete='current-password']",
    ],
    "login_button": [
        "#submitBtn",
        "input[name='submitBtn']",
        "button[type='submit']",
        "input[type='submit']",
        "button.btn-primary",
        "button:has-text('Entrar')",
        "button:has-text('Autenticar')",
    ],
    "login_error": [
        ".alert-danger",
        ".error-message",
        ".login-error",
        ".alert.alert-danger",
        "[role='alert']",
    ],
    "situacao_contributiva": [
        "a[href*='situacao-contributiva']",
        "a:has-text('Situação Contributiva')",
        "a:has-text('situação contributiva')",
    ],
    "extrato_remuneracoes": [
        "a[href*='extrato']",
        "a:has-text('Extrato de Remunera')",
        "a:has-text('extrato de remunera')",
    ],
    "documentos_menu": [
        "a[href*='documentos']",
        "a:has-text('Documentos')",
        "a:has-text('Certidões')",
    ],
    "download_button": [
        "a[href*='download']",
        "a[href*='.pdf']",
        "button:has-text('Descarregar')",
        "button:has-text('Guardar')",
        "a[title*='download']",
    ],
}

# Tempo máximo de espera por elementos (ms)
# Aumentado para 90s para mitigar cold-start do headless browser no Render
DEFAULT_TIMEOUT = 90000  # 90 segundos
NAVIGATION_TIMEOUT = 90000  # 90 segundos

# Tempo máximo total do scraper (segundos) — prevenir execuções infinitas
MAX_SCRAPER_DURATION = 180  # 3 minutos

# Retry config
MAX_RETRIES = 2
RETRY_DELAYS = [5, 15]  # segundos entre tentativas

# User-Agent atualizado (Chrome 131 — Maio 2025)
MODERN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ================================================================
# TIPOS DE RESULTADO
# ================================================================

class ScraperDocument:
    """Representa um documento obtido pelo scraper."""

    def __init__(
        self,
        filename: str,
        content_bytes: bytes,
        content_type: str = "application/pdf",
        category: str = "Outros",
        label: str = "Documento",
    ):
        self.filename = filename
        self.content_bytes = content_bytes
        self.content_type = content_type
        self.category = category
        self.label = label

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "content_bytes": self.content_bytes,
            "content_type": self.content_type,
            "category": self.category,
            "label": self.label,
            "size": len(self.content_bytes),
        }


class ScraperResult:
    """Resultado da execução do scraper."""

    def __init__(
        self,
        success: bool,
        documents: Optional[List[ScraperDocument]] = None,
        error: Optional[str] = None,
        screenshot_b64: Optional[str] = None,
        step_failed: Optional[str] = None,
    ):
        self.success = success
        self.documents = documents or []
        self.error = error
        self.screenshot_b64 = screenshot_b64  # Base64 screenshot para debug
        self.step_failed = step_failed          # Nome do step que falhou

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "documents_count": len(self.documents),
            "documents": [d.to_dict() for d in self.documents],
            "error": self.error,
            "step_failed": self.step_failed,
            "has_screenshot": self.screenshot_b64 is not None,
        }


# ================================================================
# HELPERS — Segurança, Browser e Selectors
# ================================================================

def _force_gc() -> None:
    """Força o garbage collector para limpar referências não utilizadas."""
    gc.collect()


def _get_browser_launch_args() -> Dict[str, Any]:
    """
    Retorna argumentos de configuração para o browser headless.

    Otimizado para ambientes Docker com RAM (2GB em produção).
    Com playwright-stealth, não precisamos de flags tão agressivas.
    """
    return {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-zygote",
            "--single-process",
            "--disable-extensions",
            "--disable-software-rasterizer",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-ipc-flooding-protection",
            "--window-size=1280,720",
            # Stealth extra flags
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    }


def _mask_identifier(identifier: str) -> str:
    """Mascara um identificador (NIF/NISS) para logging seguro."""
    if not identifier or len(identifier) < 6:
        return "***"
    return f"{identifier[:2]}****{identifier[-1:]}"


async def _try_selectors(page, selectors: List[str], timeout: int = 5000):
    """
    Tenta encontrar o primeiro elemento que corresponda a um dos selectors.

    Retorna (element, selector_usado) ou (None, None) se nenhum funcionar.
    Isto torna o scraper resiliente a mudanças de HTML.
    """
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=min(timeout, 3000)):
                return el, selector
        except Exception:
            continue
    return None, None


async def _take_screenshot(page, label: str = "failure") -> Optional[str]:
    """
    Tira um screenshot da página actual e retorna como base64.

    Útil para debug quando o scraper falha — permite ver o estado
    actual do portal sem aceder ao servidor.
    """
    try:
        screenshot_bytes = await page.screenshot(
            type="jpeg",
            quality=60,  # Qualidade reduzida para poupar memória
            full_page=False,
        )
        b64 = base64.b64encode(screenshot_bytes).decode("ascii")
        logger.info(f"[GOV_SCRAPER] Screenshot tirado ({label}): {len(b64)} chars base64")
        return b64
    except Exception as e:
        logger.warning(f"[GOV_SCRAPER] Não foi possível tirar screenshot: {type(e).__name__}")
        return None


async def _apply_stealth(page_or_context):
    """
    Aplica playwright-stealth ao context (ou page) para disfarçar o
    headless browser.

    Suporta tanto a API antiga (v1.x — `stealth_async(page)`) como a
    nova API (v2.x — `Stealth().apply_stealth_async(context)`).

    Isto evita que os portais governamentais detectem que é um bot
    e bloqueiem o acesso. Inclui:
    - navigator.webdriver = false
    - Chrome runtime mock
    - Permissions API mock
    - Plugin/MimeType mocks
    - WebGL vendor mock
    - etc.
    """
    # Tentar API v2.x primeiro (Stealth class — playwright-stealth >= 2.0)
    try:
        from playwright_stealth import Stealth
    except ImportError as e:
        logger.warning(
            f"[GOV_SCRAPER] playwright-stealth (v2) ImportError: {e}. "
            "Vai tentar API v1.x..."
        )
        Stealth = None
    except Exception as e:
        logger.warning(
            f"[GOV_SCRAPER] playwright-stealth (v2) erro inesperado no import: "
            f"{type(e).__name__}: {e}"
        )
        Stealth = None

    if Stealth is not None:
        try:
            stealth = Stealth()
            # apply_stealth_async aceita BrowserContext ou Page (v2.x)
            await stealth.apply_stealth_async(page_or_context)
            logger.info("[GOV_SCRAPER] Stealth v2 aplicado com sucesso")
            return
        except Exception as e:
            logger.warning(f"[GOV_SCRAPER] Erro ao aplicar stealth v2: {type(e).__name__}: {e}")
            return

    # Fallback para API v1.x (stealth_async)
    try:
        from playwright_stealth import stealth_async
        await stealth_async(page_or_context)
        logger.info("[GOV_SCRAPER] Stealth v1 aplicado com sucesso")
    except ImportError as e:
        logger.warning(
            f"[GOV_SCRAPER] playwright-stealth não instalado (ou import falhou): {e} "
            "— a correr SEM stealth (risco de bloqueio por anti-bot)"
        )
    except Exception as e:
        logger.warning(f"[GOV_SCRAPER] Erro ao aplicar stealth v1: {type(e).__name__}: {e}")


# ================================================================
# SCRAPER: PORTAL DAS FINANÇAS
# ================================================================

async def fetch_financas_documents(
    nif: str,
    password: str,
) -> ScraperResult:
    """
    Obtém documentos do Portal das Finanças (IRS + Nota de Liquidação).

    v2: Inclui retry com backoff e stealth.
    """
    # DEV MODE: Mock do scraper — SÓ PRODUÇÃO lança o browser
    if os.environ.get('ENVIRONMENT', 'dev') != 'production':
        logger.info("[GOV_SCRAPER] BLOCKED: ENVIRONMENT != production — browser will NOT launch")
        return ScraperResult(
            success=True,
            documents=[],
            error="MOCK: Documentos Finanças obtidos (DEV)",
        )

    masked_nif = _mask_identifier(nif)
    last_result = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await asyncio.wait_for(
                _financas_scraper_inner(nif, password),
                timeout=MAX_SCRAPER_DURATION,
            )
            if result.success:
                return result

            last_result = result

            # Se erro de credenciais, não faz sentido retry
            if result.error in ("credenciais_invalidas", "mfa_requerido"):
                return result

            # Retry com backoff
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt]
                logger.info(
                    f"[GOV_SCRAPER] Retry {attempt + 1}/{MAX_RETRIES} "
                    f"para NIF {masked_nif} em {delay}s (erro: {result.error})"
                )
                await asyncio.sleep(delay)

        except asyncio.TimeoutError:
            logger.error(f"[GOV_SCRAPER] Timeout ({MAX_SCRAPER_DURATION}s) para NIF {masked_nif}")
            last_result = ScraperResult(success=False, error="timeout", step_failed="global_timeout")

        except Exception as e:
            logger.error(f"[GOV_SCRAPER] Erro para NIF {masked_nif}: {type(e).__name__}")
            last_result = ScraperResult(success=False, error=type(e).__name__, step_failed="unexpected_error")

        # Retry com backoff para timeouts/erros
        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[attempt]
            logger.info(f"[GOV_SCRAPER] Retry {attempt + 1}/{MAX_RETRIES} em {delay}s")
            await asyncio.sleep(delay)

    # Limpeza final
    del password
    del nif
    _force_gc()

    return last_result or ScraperResult(success=False, error="unknown", step_failed="all_retries_exhausted")


async def _financas_scraper_inner(nif: str, password: str) -> ScraperResult:
    """Lógica interna do scraper das Finanças com stealth e screenshot-on-failure."""
    from playwright.async_api import async_playwright

    masked_nif = _mask_identifier(nif)
    documents: List[ScraperDocument] = []
    screenshot_b64 = None
    step = "init"

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(**_get_browser_launch_args())
    context = None

    try:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="pt-PT",
            user_agent=MODERN_USER_AGENT,
            # Extras para stealth
            java_script_enabled=True,
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            },
        )
        page = await context.new_page()

        # Aplicar stealth ao context (cobre esta página e futuras)
        await _apply_stealth(context)

        # ── Configurar timeouts globais da página ──
        # Aumentado para 90s para mitigar cold-start do headless browser no Render
        page.set_default_timeout(DEFAULT_TIMEOUT)           # 90000 ms
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)  # 90000 ms
        logger.info(
            f"[GOV_SCRAPER] Timeouts configurados — default: {DEFAULT_TIMEOUT}ms, "
            f"navigation: {NAVIGATION_TIMEOUT}ms"
        )

        # ── 1. Navegar para a página de login ──
        step = "navigate_login"
        logger.info(f"[GOV_SCRAPER] Navegando para {FINANCAS_AUTH_URL[:80]}... (NIF {masked_nif})")
        await page.goto(FINANCAS_AUTH_URL, wait_until="domcontentloaded")
        # Esperar pelo formulário em vez de networkidle
        await page.wait_for_load_state("domcontentloaded", timeout=90000)
        # Pequena pausa para a UI React/Radix renderizar
        await asyncio.sleep(2)
        try:
            _page_title = await page.title()
            logger.info(
                f"[GOV_SCRAPER] Página carregada — URL: {page.url[:160]} "
                f"| Title: {_page_title[:80]}"
            )
        except Exception:
            pass

        # ── 2–5. Login (NIF + Password + Submit + Verificação) ──
        # Bloco protegido com try/except para distinguir timeout no login
        # vs. timeout na navegação interna (pós-login)
        login_success = False
        try:
            # ── 2. Selecionar autenticação por NIF ──
            # A nova UI (acesso.gov.pt v2) usa Radix Tabs. O tab activo
            # por defeito é "CC / CMD" (mesmo com selectedAuthMethod=N na URL).
            # Temos de clicar manualmente no tab "NIF" e esperar que o
            # painel correspondente seja renderizado.
            step = "select_nif_tab"
            try:
                # Esperar pela tablist (página totalmente renderizada)
                await page.wait_for_selector("[role='tablist']", timeout=20000)
            except Exception:
                pass

            tab_el, tab_sel = await _try_selectors(page, FINANCAS_SEL["login_tab_nif"], timeout=10000)
            if tab_el:
                try:
                    await tab_el.click()
                    logger.info(f"[GOV_SCRAPER] Tab NIF clicada (selector: {tab_sel})")
                    # Esperar que o input username apareça (Radix renderiza on-demand)
                    await page.wait_for_selector(
                        "input[name='username']", state="visible", timeout=15000
                    )
                except Exception as e:
                    logger.info(f"[GOV_SCRAPER] Tab NIF — clique/render falhou: {type(e).__name__}")
            else:
                logger.info("[GOV_SCRAPER] Tab NIF não encontrada — pode já estar ativa")

            # ── 3. Inserir credenciais ──
            step = "fill_nif"
            nif_el, nif_sel = await _try_selectors(page, FINANCAS_SEL["nif_input"], timeout=15000)
            if not nif_el:
                # ── Diagnóstico detalhado para debug em produção ──
                try:
                    diag_url = page.url
                    diag_title = await page.title()
                    diag_inputs = await page.locator("input").count()
                    diag_tabs = await page.locator("[role='tab']").count()
                    diag_tabs_text = []
                    for i in range(min(diag_tabs, 5)):
                        try:
                            t = (await page.locator("[role='tab']").nth(i).text_content() or "").strip()
                            diag_tabs_text.append(t[:30])
                        except Exception:
                            pass
                    diag_body_text = ""
                    try:
                        diag_body_text = (await page.locator("body").text_content() or "")[:300]
                    except Exception:
                        pass
                    logger.error(
                        f"[GOV_SCRAPER] DIAGNÓSTICO NIF não encontrado:\n"
                        f"  URL: {diag_url[:200]}\n"
                        f"  Title: {diag_title[:120]}\n"
                        f"  Total inputs: {diag_inputs}\n"
                        f"  Tabs visíveis ({diag_tabs}): {diag_tabs_text}\n"
                        f"  Body preview: {diag_body_text[:200].replace(chr(10), ' ')}"
                    )
                except Exception as diag_err:
                    logger.warning(f"[GOV_SCRAPER] Falha no diagnóstico: {type(diag_err).__name__}")
                screenshot_b64 = await _take_screenshot(page, "nif_input_not_found")
                return ScraperResult(
                    success=False,
                    error="selector_desatualizado",
                    step_failed="fill_nif",
                    screenshot_b64=screenshot_b64,
                )
            await nif_el.click()
            await nif_el.fill(nif)
            logger.info(f"[GOV_SCRAPER] NIF inserido via {nif_sel} ({masked_nif})")

            step = "fill_password"
            pass_el, pass_sel = await _try_selectors(page, FINANCAS_SEL["password_input"], timeout=10000)
            if not pass_el:
                screenshot_b64 = await _take_screenshot(page, "password_input_not_found")
                return ScraperResult(
                    success=False,
                    error="selector_desatualizado",
                    step_failed="fill_password",
                    screenshot_b64=screenshot_b64,
                )
            await pass_el.click()
            await pass_el.fill(password)

            # ── 4. Submeter login ──
            step = "submit_login"
            login_el, login_sel = await _try_selectors(page, FINANCAS_SEL["login_button"], timeout=10000)
            if not login_el:
                screenshot_b64 = await _take_screenshot(page, "login_button_not_found")
                return ScraperResult(
                    success=False,
                    error="selector_desatualizado",
                    step_failed="submit_login",
                    screenshot_b64=screenshot_b64,
                )
            await login_el.click()
            logger.info(f"[GOV_SCRAPER] Login submetido via {login_sel}")

            # Esperar navegação — usar domcontentloaded + pausa em vez de networkidle
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=90000)
                await asyncio.sleep(2)  # Dar tempo para redirects
            except Exception:
                pass

            # ── 5. Verificar se o login falhou ──
            step = "check_login"

            # 5a. Verificar mensagem de erro
            error_el, _ = await _try_selectors(page, FINANCAS_SEL["login_error"], timeout=10000)
            if error_el:
                error_text = await error_el.text_content()
                logger.warning(f"[GOV_SCRAPER] Erro de login visível: {error_text[:100]}")
                screenshot_b64 = await _take_screenshot(page, "login_error")
                return ScraperResult(
                    success=False,
                    error="credenciais_invalidas",
                    step_failed="check_login",
                    screenshot_b64=screenshot_b64,
                )

            # 5b. Verificar se ainda estamos na página de login
            current_url_lower = page.url.lower()
            still_on_login = (
                "acesso.gov.pt" in current_url_lower and (
                    "loginform" in current_url_lower
                    or "unauthlogin" in current_url_lower
                    or "login" in current_url_lower
                )
            )
            if still_on_login:
                logger.warning(f"[GOV_SCRAPER] Ainda na página de login (NIF {masked_nif})")
                screenshot_b64 = await _take_screenshot(page, "still_on_login")

                # Verificar se há MFA / Chave Móvel Digital
                mfa_selectors = [
                    "text=Chave Móvel Digital",
                    "text=código de segurança",
                    "text=autenticação multi-fator",
                    "input[placeholder*='código']",
                    "input[placeholder*='digito']",
                ]
                for sel in mfa_selectors:
                    try:
                        mfa_el = page.locator(sel).first
                        if await mfa_el.is_visible(timeout=2000):
                            logger.warning(f"[GOV_SCRAPER] MFA/Chave Móvel Digital detectada")
                            return ScraperResult(
                                success=False,
                                error="mfa_requerido",
                                step_failed="check_login",
                                screenshot_b64=screenshot_b64,
                            )
                    except Exception:
                        continue

                return ScraperResult(
                    success=False,
                    error="credenciais_invalidas",
                    step_failed="check_login",
                    screenshot_b64=screenshot_b64,
                )

            login_success = True
            logger.info(f"[GOV_SCRAPER] Login bem-sucedido para NIF {masked_nif}! URL: {page.url[:80]}")

        except asyncio.TimeoutError:
            logger.error(
                "Timeout na página de Login. Possível bloqueio de WAF/Captcha. "
                f"Step: {step}, NIF: {masked_nif}"
            )
            screenshot_b64 = await _take_screenshot(page, f"login_timeout_{step}")
            return ScraperResult(
                success=False,
                error="timeout_login",
                step_failed=step,
                screenshot_b64=screenshot_b64,
            )

        # ── 6. Navegar para a secção de IRS (pós-login) ──
        step = "navigate_irs"
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=90000)

            irs_el, irs_sel = await _try_selectors(page, FINANCAS_SEL["irs_menu"], timeout=15000)
            if irs_el:
                await irs_el.click()
                await page.wait_for_load_state("domcontentloaded", timeout=90000)
                logger.info(f"[GOV_SCRAPER] Secção de IRS acedida via {irs_sel}")
            else:
                logger.warning("[GOV_SCRAPER] Link IRS não encontrado — a tentar navegação directa")
                # URL actual do portal IRS (sub-domínio dedicado, Maio 2025).
                # A antiga `/pt/irs.action` está descontinuada e devolve
                # "A funcionalidade pode ter mudado de endereço".
                for irs_url in (
                    "https://irs.portaldasfinancas.gov.pt/home.action",
                    "https://www.portaldasfinancas.gov.pt/at/html/index.html#irs",
                ):
                    try:
                        await page.goto(irs_url, wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(2)
                        # Se a página tem conteúdo IRS real (e não a página de erro),
                        # consideramos sucesso
                        body_text = (await page.locator("body").text_content() or "").lower()
                        if "mudado de endere" not in body_text and "página não encontrada" not in body_text:
                            logger.info(f"[GOV_SCRAPER] IRS acedido via navegação directa: {irs_url}")
                            break
                        logger.info(f"[GOV_SCRAPER] {irs_url} devolveu página de erro, a tentar próxima...")
                    except Exception as nav_err:
                        logger.info(f"[GOV_SCRAPER] Falha em {irs_url}: {type(nav_err).__name__}")
                        continue
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout na navegação interna (pós-login). "
                f"Login OK mas falha ao navegar para IRS. NIF: {masked_nif}"
            )
            screenshot_b64 = await _take_screenshot(page, "irs_navigation_timeout")
        except Exception as e:
            logger.error(
                f"Erro na navegação interna (pós-login). "
                f"Login OK mas falha ao navegar para IRS: {type(e).__name__}. NIF: {masked_nif}"
            )
            screenshot_b64 = await _take_screenshot(page, "irs_navigation_failed")

        # ── 7. Descarregar Declaração de IRS ──
        # Categoria S3 = "Financeiros" (corresponde à pasta visível no CRM via
        # S3FileManager). O tipo específico do documento ("Declaração de IRS")
        # fica em `custom_label` no registo da BD para distinguir do resto.
        step = "download_irs"
        doc_irs = await _download_financas_document(
            page, "Declaração de IRS", "Financeiros"
        )
        if doc_irs:
            documents.append(doc_irs)
            logger.info(f"[GOV_SCRAPER] IRS descarregado: {doc_irs.filename} ({len(doc_irs.content_bytes)} bytes)")
        else:
            logger.warning("[GOV_SCRAPER] Não foi possível descarregar a Declaração de IRS")

        # ── 8. Descarregar Nota de Liquidação ──
        step = "download_nota"
        doc_nota = await _download_financas_document(
            page, "Nota de Liquidação IRS", "Financeiros"
        )
        if doc_nota:
            documents.append(doc_nota)
            logger.info(f"[GOV_SCRAPER] Nota de Liquidação descarregada: {doc_nota.filename} ({len(doc_nota.content_bytes)} bytes)")
        else:
            logger.warning("[GOV_SCRAPER] Não foi possível descarregar a Nota de Liquidação")

        # ── 9. Retornar resultados ──
        if not documents:
            logger.warning(f"[GOV_SCRAPER] Nenhum documento obtido para NIF {masked_nif}")
            screenshot_b64 = await _take_screenshot(page, "no_documents_found")
            return ScraperResult(
                success=False,
                error="sem_documentos",
                step_failed=step,
                screenshot_b64=screenshot_b64,
            )

        logger.info(f"[GOV_SCRAPER] {len(documents)} documentos obtidos para NIF {masked_nif}")
        return ScraperResult(success=True, documents=documents)

    except Exception as e:
        logger.error(f"[GOV_SCRAPER] Erro interno Finanças: {type(e).__name__}")
        # Tentar screenshot do erro
        try:
            if 'page' in dir():
                screenshot_b64 = await _take_screenshot(page, f"error_{step}")
        except Exception:
            pass
        return ScraperResult(
            success=False,
            error=type(e).__name__,
            step_failed=step,
            screenshot_b64=screenshot_b64,
        )

    finally:
        # CRÍTICO: Garantir que TODOS os recursos são SEMPRE libertados
        try:
            if context:
                await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass

        # Limpeza de credenciais
        del password
        del nif
        _force_gc()
        logger.info("[GOV_SCRAPER] Credenciais Finanças limpas da memória")


async def _download_financas_document(
    page,
    doc_name: str,
    category: str,
) -> Optional[ScraperDocument]:
    """
    Tenta descarregar um documento específico do Portal das Finanças.

    v2: Usa _try_selectors com fallbacks múltiplos.
    """
    now = datetime.now(timezone.utc)
    safe_filename = f"{doc_name.replace(' ', '_')}_{now.strftime('%Y%m%d')}.pdf"

    # Estratégia 1: Procurar links/botões de download direto
    try:
        all_download_selectors = [
            f"a:has-text('{doc_name}')",
            f"a:has-text('Descarregar')",
            *FINANCAS_SEL["download_button"],
            *FINANCAS_SEL["pdf_link"],
        ]

        for selector in all_download_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            await el.click()
                        download = await download_info.value

                        tmp_path = await download.path()
                        if tmp_path and os.path.exists(tmp_path):
                            with open(tmp_path, "rb") as f:
                                content_bytes = f.read()

                            if content_bytes and len(content_bytes) > 100:
                                try:
                                    os.unlink(tmp_path)
                                except Exception:
                                    pass

                                return ScraperDocument(
                                    filename=download.suggested_filename or safe_filename,
                                    content_bytes=content_bytes,
                                    content_type="application/pdf",
                                    category=category,
                                    label=doc_name,
                                )
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass

    # Estratégia 2: Navegar para sub-página
    try:
        all_nav_selectors = [
            f"a:has-text('{doc_name}')",
            *FINANCAS_SEL["declaracoes_link"],
            *FINANCAS_SEL["nota_liquidacao_link"],
        ]

        for selector in all_nav_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=90000)

                    # Tentar download na nova página
                    dl_el, _ = await _try_selectors(page, FINANCAS_SEL["download_button"], timeout=10000)
                    if dl_el:
                        try:
                            async with page.expect_download(timeout=60000) as download_info:
                                await dl_el.click()
                            download = await download_info.value

                            tmp_path = await download.path()
                            if tmp_path and os.path.exists(tmp_path):
                                with open(tmp_path, "rb") as f:
                                    content_bytes = f.read()

                                if content_bytes and len(content_bytes) > 100:
                                    try:
                                        os.unlink(tmp_path)
                                    except Exception:
                                        pass

                                    return ScraperDocument(
                                        filename=download.suggested_filename or safe_filename,
                                        content_bytes=content_bytes,
                                        content_type="application/pdf",
                                        category=category,
                                        label=doc_name,
                                    )
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        pass

    # Estratégia 3: Gerar PDF da página actual (fallback — captura de ecrã)
    try:
        logger.info(f"[GOV_SCRAPER] Gerando PDF da página para {doc_name} (fallback)")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20px", "bottom": "20px", "left": "20px", "right": "20px"},
        )

        if pdf_bytes and len(pdf_bytes) > 500:
            return ScraperDocument(
                filename=safe_filename,
                content_bytes=pdf_bytes,
                content_type="application/pdf",
                category=category,
                label=f"{doc_name} (captura de ecrã)",
            )
    except Exception:
        pass

    return None


# ================================================================
# SCRAPER: SEGURANÇA SOCIAL
# ================================================================

async def fetch_seg_social_documents(
    niss: str,
    password: str,
) -> ScraperResult:
    """Obtém documentos da Segurança Social Direta. v2: com retry e stealth."""
    # DEV MODE
    if os.environ.get('ENVIRONMENT', 'dev') != 'production':
        logger.info("[GOV_SCRAPER] BLOCKED: ENVIRONMENT != production — browser will NOT launch")
        return ScraperResult(
            success=True,
            documents=[],
            error="MOCK: Documentos Seg. Social obtidos (DEV)",
        )

    masked_niss = _mask_identifier(niss)
    last_result = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await asyncio.wait_for(
                _seg_social_scraper_inner(niss, password),
                timeout=MAX_SCRAPER_DURATION,
            )
            if result.success:
                return result

            last_result = result

            if result.error in ("credenciais_invalidas", "mfa_requerido"):
                return result

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt]
                logger.info(
                    f"[GOV_SCRAPER] Retry {attempt + 1}/{MAX_RETRIES} "
                    f"Seg. Social para NISS {masked_niss} em {delay}s (erro: {result.error})"
                )
                await asyncio.sleep(delay)

        except asyncio.TimeoutError:
            logger.error(f"[GOV_SCRAPER] Timeout ({MAX_SCRAPER_DURATION}s) Seg. Social NISS {masked_niss}")
            last_result = ScraperResult(success=False, error="timeout", step_failed="global_timeout")

        except Exception as e:
            logger.error(f"[GOV_SCRAPER] Erro Seg. Social NISS {masked_niss}: {type(e).__name__}")
            last_result = ScraperResult(success=False, error=type(e).__name__, step_failed="unexpected_error")

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[attempt]
            await asyncio.sleep(delay)

    del password
    del niss
    _force_gc()

    return last_result or ScraperResult(success=False, error="unknown", step_failed="all_retries_exhausted")


async def _seg_social_scraper_inner(niss: str, password: str) -> ScraperResult:
    """Lógica interna do scraper da Segurança Social com stealth e screenshot."""
    from playwright.async_api import async_playwright

    masked_niss = _mask_identifier(niss)
    documents: List[ScraperDocument] = []
    screenshot_b64 = None
    step = "init"

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(**_get_browser_launch_args())
    context = None

    try:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="pt-PT",
            user_agent=MODERN_USER_AGENT,
            java_script_enabled=True,
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            },
        )
        page = await context.new_page()

        # Aplicar stealth ao context
        await _apply_stealth(context)

        # ── Configurar timeouts globais da página ──
        # Aumentado para 90s para mitigar cold-start do headless browser no Render
        page.set_default_timeout(DEFAULT_TIMEOUT)           # 90000 ms
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)  # 90000 ms
        logger.info(
            f"[GOV_SCRAPER] Timeouts configurados — default: {DEFAULT_TIMEOUT}ms, "
            f"navigation: {NAVIGATION_TIMEOUT}ms"
        )

        # ── 1. Navegar para a página de login ──
        step = "navigate_login"
        logger.info(f"[GOV_SCRAPER] Navegando para Seg. Social (NISS {masked_niss})")
        await page.goto(SEG_SOCIAL_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("domcontentloaded", timeout=90000)
        await asyncio.sleep(2)  # Dar tempo para redirects

        # ── 2–5. Login (NISS + Password + Submit + Verificação) ──
        # Bloco protegido com try/except para distinguir timeout no login
        # vs. timeout na navegação interna (pós-login)
        login_success = False
        try:
            # ── 2. Verificar se há redirecionamento para autenticação.gov.pt ──
            current_url = page.url.lower()
            if "acesso.gov.pt" in current_url:
                logger.info("[GOV_SCRAPER] Redirecionado para acesso.gov.pt — usar fluxo de autenticação genérico")
                # Garantir que o tab NIF está activo
                try:
                    tab_el, _ = await _try_selectors(page, FINANCAS_SEL["login_tab_nif"], timeout=8000)
                    if tab_el:
                        await tab_el.click()
                        await page.wait_for_selector("input[name='username']", state="visible", timeout=15000)
                except Exception:
                    pass
                niss_el, niss_sel = await _try_selectors(page, FINANCAS_SEL["nif_input"], timeout=15000)
            else:
                # SSD nativo — clicar no toggle "Autenticar com utilizador da SS"
                # para expandir o formulário (vem colapsado por defeito)
                try:
                    toggle_el, toggle_sel = await _try_selectors(
                        page, SEG_SOCIAL_SEL["auth_toggle"], timeout=8000
                    )
                    if toggle_el:
                        await toggle_el.click()
                        logger.info(f"[GOV_SCRAPER] Formulário SSD expandido via {toggle_sel}")
                        # Esperar pela animação do slide
                        try:
                            await page.wait_for_selector(
                                "#username", state="visible", timeout=10000
                            )
                        except Exception:
                            await asyncio.sleep(2)
                except Exception as toggle_err:
                    logger.warning(f"[GOV_SCRAPER] Toggle SSD falhou: {type(toggle_err).__name__}")

                niss_el, niss_sel = await _try_selectors(page, SEG_SOCIAL_SEL["niss_input"], timeout=15000)

            # ── 3. Inserir credenciais ──
            step = "fill_niss"
            if not niss_el:
                screenshot_b64 = await _take_screenshot(page, "niss_input_not_found")
                return ScraperResult(
                    success=False,
                    error="selector_desatualizado",
                    step_failed="fill_niss",
                    screenshot_b64=screenshot_b64,
                )
            await niss_el.click()
            await niss_el.fill(niss)
            logger.info(f"[GOV_SCRAPER] NISS inserido via {niss_sel} ({masked_niss})")

            step = "fill_password"
            # Determinar quais selectors de password usar
            if "acesso.gov.pt" in page.url.lower():
                pass_el, pass_sel = await _try_selectors(page, FINANCAS_SEL["password_input"], timeout=10000)
            else:
                pass_el, pass_sel = await _try_selectors(page, SEG_SOCIAL_SEL["password_input"], timeout=10000)

            if not pass_el:
                screenshot_b64 = await _take_screenshot(page, "password_input_not_found")
                return ScraperResult(
                    success=False,
                    error="selector_desatualizado",
                    step_failed="fill_password",
                    screenshot_b64=screenshot_b64,
                )
            await pass_el.click()
            await pass_el.fill(password)

            # ── 4. Submeter login ──
            step = "submit_login"
            if "acesso.gov.pt" in page.url.lower():
                login_el, login_sel = await _try_selectors(page, FINANCAS_SEL["login_button"], timeout=10000)
            else:
                login_el, login_sel = await _try_selectors(page, SEG_SOCIAL_SEL["login_button"], timeout=10000)

            if login_el:
                await login_el.click()
                logger.info(f"[GOV_SCRAPER] Login submetido via {login_sel}")
            else:
                await page.keyboard.press("Enter")
                logger.info("[GOV_SCRAPER] Login submetido via Enter")

            # Esperar navegação
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=90000)
                await asyncio.sleep(2)
            except Exception:
                pass

            # ── 5. Verificar se o login falhou ──
            step = "check_login"

            # Verificar erro visível
            error_el, _ = await _try_selectors(page, SEG_SOCIAL_SEL["login_error"], timeout=10000)
            if error_el:
                screenshot_b64 = await _take_screenshot(page, "login_error")
                return ScraperResult(
                    success=False,
                    error="credenciais_invalidas",
                    step_failed="check_login",
                    screenshot_b64=screenshot_b64,
                )

            # Verificar URL
            current_url = page.url.lower()
            if "login" in current_url or "autenticacao" in current_url:
                await asyncio.sleep(3)
                current_url = page.url.lower()
                if "login" in current_url or "autenticacao" in current_url:
                    # Verificar MFA
                    mfa_selectors = [
                        "text=Chave Móvel Digital",
                        "text=código de segurança",
                        "text=autenticação multi-fator",
                        "input[placeholder*='código']",
                    ]
                    for sel in mfa_selectors:
                        try:
                            mfa_el = page.locator(sel).first
                            if await mfa_el.is_visible(timeout=2000):
                                screenshot_b64 = await _take_screenshot(page, "mfa_required")
                                return ScraperResult(
                                    success=False,
                                    error="mfa_requerido",
                                    step_failed="check_login",
                                    screenshot_b64=screenshot_b64,
                                )
                        except Exception:
                            continue

                    screenshot_b64 = await _take_screenshot(page, "still_on_login")
                    return ScraperResult(
                        success=False,
                        error="credenciais_invalidas",
                        step_failed="check_login",
                        screenshot_b64=screenshot_b64,
                    )

            login_success = True
            logger.info(f"[GOV_SCRAPER] Login Seg. Social bem-sucedido para NISS {masked_niss}!")

        except asyncio.TimeoutError:
            logger.error(
                "Timeout na página de Login. Possível bloqueio de WAF/Captcha. "
                f"Step: {step}, NISS: {masked_niss}"
            )
            screenshot_b64 = await _take_screenshot(page, f"login_timeout_{step}")
            return ScraperResult(
                success=False,
                error="timeout_login",
                step_failed=step,
                screenshot_b64=screenshot_b64,
            )

        # ── 6. Navegar para Documentos (pós-login) ──
        step = "navigate_documents"
        try:
            doc_menu_el, _ = await _try_selectors(page, SEG_SOCIAL_SEL["documentos_menu"], timeout=15000)
            if doc_menu_el:
                try:
                    await doc_menu_el.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=90000)
                except asyncio.TimeoutError:
                    logger.error(
                        f"Timeout na navegação interna (pós-login). "
                        f"Login OK mas falha ao navegar para Documentos. NISS: {masked_niss}"
                    )
                    screenshot_b64 = await _take_screenshot(page, "documents_navigation_timeout")
                except Exception:
                    logger.error(
                        f"Erro na navegação interna (pós-login). "
                        f"Login OK mas falha ao navegar para Documentos. NISS: {masked_niss}"
                    )
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout na navegação interna (pós-login). "
                f"Login OK mas falha ao encontrar menu Documentos. NISS: {masked_niss}"
            )
            screenshot_b64 = await _take_screenshot(page, "documents_menu_timeout")
        except Exception:
            pass

        # ── 7. Descarregar Situação Contributiva ──
        # Categoria S3 = "Financeiros" (visível no S3FileManager do CRM)
        step = "download_situacao"
        doc_sit = await _download_seg_social_document(
            page, "Situação Contributiva", "Financeiros"
        )
        if doc_sit:
            documents.append(doc_sit)
            logger.info(f"[GOV_SCRAPER] Situação Contributiva descarregada: {doc_sit.filename}")

        # ── 8. Descarregar Extrato de Remunerações ──
        step = "download_extrato"
        doc_ext = await _download_seg_social_document(
            page, "Extrato de Remunerações", "Financeiros"
        )
        if doc_ext:
            documents.append(doc_ext)
            logger.info(f"[GOV_SCRAPER] Extrato de Remunerações descarregado: {doc_ext.filename}")

        # ── 9. Retornar resultados ──
        if not documents:
            logger.warning(f"[GOV_SCRAPER] Nenhum documento obtido para NISS {masked_niss}")
            screenshot_b64 = await _take_screenshot(page, "no_documents_found")
            return ScraperResult(
                success=False,
                error="sem_documentos",
                step_failed=step,
                screenshot_b64=screenshot_b64,
            )

        logger.info(f"[GOV_SCRAPER] {len(documents)} documentos obtidos para NISS {masked_niss}")
        return ScraperResult(success=True, documents=documents)

    except Exception as e:
        logger.error(f"[GOV_SCRAPER] Erro interno Seg. Social: {type(e).__name__}")
        try:
            if 'page' in dir():
                screenshot_b64 = await _take_screenshot(page, f"error_{step}")
        except Exception:
            pass
        return ScraperResult(
            success=False,
            error=type(e).__name__,
            step_failed=step,
            screenshot_b64=screenshot_b64,
        )

    finally:
        try:
            if context:
                await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass

        del password
        del niss
        _force_gc()
        logger.info("[GOV_SCRAPER] Credenciais Seg. Social limpas da memória")


async def _download_seg_social_document(
    page,
    doc_name: str,
    category: str,
) -> Optional[ScraperDocument]:
    """Tenta descarregar um documento específico da Segurança Social. v2."""
    now = datetime.now(timezone.utc)
    safe_filename = f"{doc_name.replace(' ', '_')}_{now.strftime('%Y%m%d')}.pdf"

    # Estratégia 1: Download direto
    try:
        doc_specific_sels = (
            SEG_SOCIAL_SEL["situacao_contributiva"]
            if "Contributiva" in doc_name
            else SEG_SOCIAL_SEL["extrato_remuneracoes"]
        )
        all_download_selectors = [
            f"a:has-text('{doc_name}')",
            *doc_specific_sels,
            *SEG_SOCIAL_SEL["download_button"],
        ]

        for selector in all_download_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            await el.click()
                        download = await download_info.value

                        tmp_path = await download.path()
                        if tmp_path and os.path.exists(tmp_path):
                            with open(tmp_path, "rb") as f:
                                content_bytes = f.read()

                            if content_bytes and len(content_bytes) > 100:
                                try:
                                    os.unlink(tmp_path)
                                except Exception:
                                    pass

                                return ScraperDocument(
                                    filename=download.suggested_filename or safe_filename,
                                    content_bytes=content_bytes,
                                    content_type="application/pdf",
                                    category=category,
                                    label=doc_name,
                                )
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass

    # Estratégia 2: Navegar para sub-página
    try:
        nav_selectors = [
            f"a:has-text('{doc_name}')",
            *doc_specific_sels,
        ]

        for selector in nav_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=90000)

                    dl_el, _ = await _try_selectors(page, SEG_SOCIAL_SEL["download_button"], timeout=10000)
                    if dl_el:
                        try:
                            async with page.expect_download(timeout=60000) as download_info:
                                await dl_el.click()
                            download = await download_info.value

                            tmp_path = await download.path()
                            if tmp_path and os.path.exists(tmp_path):
                                with open(tmp_path, "rb") as f:
                                    content_bytes = f.read()

                                if content_bytes and len(content_bytes) > 100:
                                    try:
                                        os.unlink(tmp_path)
                                    except Exception:
                                        pass

                                    return ScraperDocument(
                                        filename=download.suggested_filename or safe_filename,
                                        content_bytes=content_bytes,
                                        content_type="application/pdf",
                                        category=category,
                                        label=doc_name,
                                    )
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        pass

    # Estratégia 3: PDF da página actual (fallback)
    try:
        logger.info(f"[GOV_SCRAPER] Gerando PDF da página para {doc_name} (fallback)")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20px", "bottom": "20px", "left": "20px", "right": "20px"},
        )

        if pdf_bytes and len(pdf_bytes) > 500:
            return ScraperDocument(
                filename=safe_filename,
                content_bytes=pdf_bytes,
                content_type="application/pdf",
                category=category,
                label=f"{doc_name} (captura de ecrã)",
            )
    except Exception:
        pass

    return None


# ================================================================
# DIAGNÓSTICO — Verificar se o Playwright está disponível
# ================================================================

async def check_playwright_available() -> Dict[str, Any]:
    """
    Verifica se o Playwright, Chromium e playwright-stealth estão disponíveis.
    """
    if os.environ.get('ENVIRONMENT', 'dev') != 'production':
        return {
            "playwright_installed": False,
            "chromium_available": False,
            "stealth_available": False,
            "dev_mode": True,
            "error": "BLOCKED: ENVIRONMENT != production — check skipped",
        }

    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "(default: ~/.cache/ms-playwright)")

    result = {
        "playwright_installed": False,
        "chromium_available": False,
        "stealth_available": False,
        "browsers_path": browsers_path,
        "version": "2.0.0",
        "error": None,
    }

    try:
        from playwright.async_api import async_playwright
        result["playwright_installed"] = True

        # Verificar playwright-stealth
        try:
            import playwright_stealth
            result["stealth_available"] = True
        except ImportError:
            result["stealth_available"] = False

        # Verificar diretório de browsers
        if os.path.isdir(browsers_path):
            result["browsers_dir_exists"] = True
            try:
                result["browsers_dir_contents"] = os.listdir(browsers_path)
            except Exception:
                result["browsers_dir_contents"] = "(erro ao listar)"
        else:
            result["browsers_dir_exists"] = False

        # Tentar lançar browser
        pw = await async_playwright().start()
        browser = None
        try:
            browser = await pw.chromium.launch(**_get_browser_launch_args())
            result["chromium_available"] = True
        except Exception as e:
            result["error"] = f"Chromium não disponível: {type(e).__name__}: {str(e)[:200]}"
        finally:
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass
            await pw.stop()

    except ImportError:
        result["error"] = "Playwright não instalado"
    except Exception as e:
        result["error"] = f"Erro ao verificar Playwright: {type(e).__name__}: {str(e)[:200]}"

    return result
