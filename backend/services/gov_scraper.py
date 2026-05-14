"""
====================================================================
GOV SCRAPER — Automação de Portais Governamentais Portugueses
====================================================================
Serviço de RPA (Robotic Process Automation) que utiliza Playwright
em modo headless para extrair documentos dos portais:

1. Portal das Finanças (via Autenticação.gov / acesso.gov.pt)
   - Declaração de IRS
   - Nota de Liquidação de IRS

2. Segurança Social Direta (app.seg-social.pt)
   - Declaração de Situação Contributiva
   - Extrato de Remunerações

SEGURANÇA (CRÍTICO):
- As credenciais (NIF/NISS + password) NUNCA são guardadas na BD.
- São usadas APENAS em memória durante a sessão do Playwright.
- Após a execução, as variáveis são limpas com `del` + `gc.collect()`.
- Nunca são impressas no terminal (log) ou persistidas de qualquer forma.
- O browser é executado em modo headless (sem interface gráfica).

FLUXO GERAL:
1. Lançar browser headless (Chromium)
2. Navegar para o portal de autenticação
3. Inserir credenciais e submeter
4. Verificar se o login foi bem-sucedido
5. Navegar até à secção de documentos
6. Descarregar os PDFs relevantes
7. Fechar browser e limpar credenciais da memória
8. Retornar os bytes dos ficheiros descarregados

NOTA: Os portais governamentais portugueses não possuem API pública.
Este scraper simula a interação humana num browser. Caso os portais
alterem a sua estrutura HTML, os selectors poderão necessitar de
atualização — os selectors estão centralizados em constantes no topo
do ficheiro para facilitar a manutenção.
====================================================================
"""

import gc
import logging
import os
import tempfile
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ================================================================
# CONFIGURAÇÃO — URLs e Selectors
# ================================================================

# Portal das Finanças (via acesso.gov.pt)
FINANCAS_AUTH_URL = "https://www.acesso.gov.pt/unauthlogin?pathpart=&target="

# Selectors do portal acesso.gov.pt (autenticação)
FINANCAS_SEL = {
    # Página de login
    "login_tab_nif": "button[onclick*='tabNif'], a[data-toggle='tab'][href='#tabNif'], #tabNif",
    "nif_input": "#NIF, input[name='username'], input[id='username']",
    "password_input": "#password, input[name='password'], input[type='password']",
    "login_button": "button[type='submit'], input[type='submit'], button.btn-primary",
    # Erro de login
    "login_error": ".alert-danger, .error-message, .login-error, .alert.alert-danger",
    # Pós-login (Portal das Finanças)
    "irs_menu": "a[href*='irs'], a[title*='IRS'], a:has-text('IRS')",
    "declaracoes_link": "a[href*='declaracao'], a:has-text('Declara')",
    "nota_liquidacao_link": "a[href*='liquidacao'], a:has-text('Nota de Liquida')",
    # Download
    "download_button": "a[href*='download'], a[href*='.pdf'], button:has-text('Descarregar'), a:has-text('Descarregar')",
    "pdf_link": "a[href$='.pdf']",
}

# Segurança Social Direta
SEG_SOCIAL_URL = "https://app.seg-social.pt/ptss/"

# Selectors da Segurança Social
SEG_SOCIAL_SEL = {
    # Login
    "niss_input": "#niss, input[name='niss'], input[name='username'], input[id='username']",
    "password_input": "#password, input[name='password'], input[type='password']",
    "login_button": "button[type='submit'], input[type='submit'], button.btn-primary",
    # Erro de login
    "login_error": ".alert-danger, .error-message, .login-error, .alert.alert-danger",
    # Documentos
    "situacao_contributiva": "a[href*='situacao-contributiva'], a:has-text('Situação Contributiva')",
    "extrato_remuneracoes": "a[href*='extrato'], a:has-text('Extrato de Remunera')",
    "documentos_menu": "a[href*='documentos'], a:has-text('Documentos')",
    # Download
    "download_button": "a[href*='download'], a[href*='.pdf'], button:has-text('Descarregar')",
}

# Tempo máximo de espera por elementos (ms)
DEFAULT_TIMEOUT = 30000  # 30 segundos
NAVIGATION_TIMEOUT = 60000  # 60 segundos

# Tempo máximo total do scraper (segundos) — prevenir execuções infinitas
MAX_SCRAPER_DURATION = 180  # 3 minutos


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
    ):
        self.success = success
        self.documents = documents or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "documents_count": len(self.documents),
            "documents": [d.to_dict() for d in self.documents],
            "error": self.error,
        }


# ================================================================
# HELPERS — Segurança e Browser
# ================================================================

def _force_gc() -> None:
    """
    Força o garbage collector para limpar referências não utilizadas.

    Deve ser chamado APÓS `del password` no scope do caller.

    NOTA IMPORTANTE: Em Python, strings são imutáveis e não podemos
    garantir a limpeza absoluta da memória (devido ao string interning
    e ao garbage collector). No entanto:
    - `del password` no scope do caller remove a referência local
    - `gc.collect()` força a recolha de objetos órfãos
    - Isto reduz significativamente a janela de exposição das credenciais

    Em produção, para segurança máxima, considere usar ctypes
    para zerar a memória diretamente, ou usar bytes mutáveis
    em vez de strings.
    """
    gc.collect()


def _get_browser_launch_args() -> Dict[str, Any]:
    """
    Retorna argumentos de configuração para o browser headless.

    Otimizado para ambientes Docker com RAM limitada (512MB no Render).
    As flags --single-process + --no-zygote reduzem o Chromium de ~6 processos
    para apenas 1, cortando o consumo de RAM em ~60%.
    """
    return {
        "headless": True,
        "args": [
            "--no-sandbox",                    # Necessário em Docker (sem kernel sandbox)
            "--disable-setuid-sandbox",        # Idem
            "--disable-dev-shm-usage",          # Usa /tmp em vez de /dev/shm (crucial p/ Docker)
            "--disable-gpu",                    # Sem GPU em headless
            "--no-zygote",                      # Não fork do processo zygote
            "--single-process",                 # 1 processo só (vs ~6 por default)
            "--disable-extensions",             # Sem extensões
            "--disable-software-rasterizer",    # Sem rasterização por software
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-ipc-flooding-protection",
            "--window-size=1280,720",           # Viewport menor = menos RAM p/ rendering
        ],
    }


def _mask_identifier(identifier: str) -> str:
    """
    Mascara um identificador (NIF/NISS) para logging seguro.
    Mostra apenas os primeiros 2 e último 1 caracteres.

    Ex: 123456789 → 12****9
    """
    if not identifier or len(identifier) < 6:
        return "***"
    return f"{identifier[:2]}****{identifier[-1:]}"


# ================================================================
# SCRAPER: PORTAL DAS FINANÇAS
# ================================================================

async def fetch_financas_documents(
    nif: str,
    password: str,
) -> ScraperResult:
    """
    Obtém documentos do Portal das Finanças (IRS + Nota de Liquidação).

    FLUXO:
    1. Abre o browser headless
    2. Navega para acesso.gov.pt (autenticação do Estado)
    3. Seleciona a tab de NIF e insere credenciais
    4. Verifica se o login foi bem-sucedido
    5. Navega até à secção de IRS
    6. Descarrega a Declaração de IRS mais recente
    7. Descarrega a Nota de Liquidação mais recente
    8. Fecha o browser e limpa credenciais

    SEGURANÇA:
    - A password NUNCA é logada ou guardada
    - Após a execução, a variável é eliminada com `del` + `gc.collect()`
    - O browser é sempre fechado, mesmo em caso de erro

    Args:
        nif: NIF do contribuinte (9 dígitos)
        password: Password do Portal das Finanças

    Returns:
        ScraperResult com documentos obtidos ou erro
    """
    # DEV MODE: Mock do scraper — SÓ PRODUÇÃO lança o browser
    # REGRA ABSOLUTA: Se ENVIRONMENT != 'production', o Chromium NÃO lança.
    # O Playwright/Chromium consome ~150-300MB RAM, inviável em 512MB.
    if os.environ.get('ENVIRONMENT', '').lower() != 'production':
        logger.info("[GOV_SCRAPER] BLOCKED: ENVIRONMENT != production — browser will NOT launch")
        return ScraperResult(
            success=True,
            documents=[],
            error="MOCK: Documentos Finanças obtidos (DEV)",
        )

    masked_nif = _mask_identifier(nif)
    logger.info(f"[GOV_SCRAPER] Iniciando scraper Finanças para NIF {masked_nif}")

    # Variáveis para cleanup
    pw = None
    browser = None
    documents: List[ScraperDocument] = []

    try:
        # Timeout global — cancela se demorar demasiado
        result = await asyncio.wait_for(
            _financas_scraper_inner(nif, password),
            timeout=MAX_SCRAPER_DURATION,
        )
        return result

    except asyncio.TimeoutError:
        logger.error(f"[GOV_SCRAPER] Timeout ({MAX_SCRAPER_DURATION}s) no scraper Finanças para NIF {masked_nif}")
        return ScraperResult(success=False, error="timeout")

    except Exception as e:
        # NUNCA logar a password ou o NIF completo
        logger.error(f"[GOV_SCRAPER] Erro no scraper Finanças para NIF {masked_nif}: {type(e).__name__}")
        return ScraperResult(success=False, error=type(e).__name__)

    finally:
        # LIMPEZA CRÍTICA: Eliminar credenciais da memória no scope do caller
        # O `del` DEVE ser feito neste scope (do caller) para remover
        # a referência local. O inner scraper limpa o browser no seu finally.
        del password
        del nif
        _force_gc()

        logger.info("[GOV_SCRAPER] Credenciais Finanças limpas da memória")


async def _financas_scraper_inner(nif: str, password: str) -> ScraperResult:
    """
    Lógica interna do scraper das Finanças.
    Separada do wrapper para garantir cleanup no finally.
    """
    from playwright.async_api import async_playwright

    masked_nif = _mask_identifier(nif)
    documents: List[ScraperDocument] = []

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(**_get_browser_launch_args())
    context = None

    try:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="pt-PT",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

        # ── 1. Navegar para a página de login ──
        logger.info(f"[GOV_SCRAPER] Navegando para acesso.gov.pt (NIF {masked_nif})")
        await page.goto(FINANCAS_AUTH_URL, wait_until="networkidle")

        # ── 2. Selecionar autenticação por NIF ──
        try:
            # Clicar na tab de NIF (pode já estar selecionada)
            nif_tab = page.locator(FINANCAS_SEL["login_tab_nif"]).first
            if await nif_tab.is_visible(timeout=5000):
                await nif_tab.click()
                await page.wait_for_load_state("networkidle")
                logger.info("[GOV_SCRAPER] Tab NIF selecionada")
        except Exception:
            logger.info("[GOV_SCRAPER] Tab NIF não encontrada — pode já estar ativa")

        # ── 3. Inserir credenciais ──
        # NIF
        nif_input = page.locator(FINANCAS_SEL["nif_input"]).first
        await nif_input.wait_for(state="visible", timeout=10000)
        await nif_input.click()
        await nif_input.fill(nif)
        logger.info(f"[GOV_SCRAPER] NIF inserido ({masked_nif})")

        # Password
        pass_input = page.locator(FINANCAS_SEL["password_input"]).first
        await pass_input.wait_for(state="visible", timeout=5000)
        await pass_input.click()
        await pass_input.fill(password)
        # Nunca logar a password!

        # ── 4. Submeter login ──
        login_btn = page.locator(FINANCAS_SEL["login_button"]).first
        await login_btn.click()
        logger.info("[GOV_SCRAPER] Login submetido, aguardando resposta...")

        # Aguardar navegação
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # ── 5. Verificar se o login falhou ──
        try:
            error_el = page.locator(FINANCAS_SEL["login_error"]).first
            if await error_el.is_visible(timeout=5000):
                logger.warning(f"[GOV_SCRAPER] Login falhou para NIF {masked_nif}")
                return ScraperResult(success=False, error="credenciais_invalidas")
        except Exception:
            # Sem elemento de erro visível — provavelmente o login correu bem
            pass

        # Verificar se ainda estamos na página de login (URL não mudou)
        if "acesso.gov.pt" in page.url and "unauthlogin" in page.url:
            logger.warning(f"[GOV_SCRAPER] Ainda na página de login — credenciais inválidas (NIF {masked_nif})")
            return ScraperResult(success=False, error="credenciais_invalidas")

        logger.info(f"[GOV_SCRAPER] Login bem-sucedido para NIF {masked_nif}!")

        # ── 6. Navegar para a secção de IRS ──
        try:
            # Aguardar que a página principal carregue
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Procurar link para IRS / Declarações
            irs_link = page.locator(FINANCAS_SEL["irs_menu"]).first
            if await irs_link.is_visible(timeout=10000):
                await irs_link.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                logger.info("[GOV_SCRAPER] Secção de IRS acedida")
            else:
                logger.warning("[GOV_SCRAPER] Link IRS não encontrado — a tentar navegação alternativa")
                # Tentar navegar diretamente para a página de IRS
                await page.goto(
                    "https://www.portaldasfinancas.gov.pt/pt/irs.action",
                    wait_until="networkidle",
                    timeout=15000,
                )
        except Exception as e:
            logger.warning(f"[GOV_SCRAPER] Erro ao navegar para IRS: {type(e).__name__}")
            # Continuar — talvez já estejamos na página certa

        # ── 7. Descarregar Declaração de IRS ──
        doc_irs = await _download_financas_document(
            page, "Declaração de IRS", "IRS"
        )
        if doc_irs:
            documents.append(doc_irs)
            logger.info(f"[GOV_SCRAPER] IRS descarregado: {doc_irs.filename} ({doc_irs.size} bytes)")
        else:
            logger.warning("[GOV_SCRAPER] Não foi possível descarregar a Declaração de IRS")

        # ── 8. Descarregar Nota de Liquidação ──
        doc_nota = await _download_financas_document(
            page, "Nota de Liquidação", "Declaracao_Imposto_Renda"
        )
        if doc_nota:
            documents.append(doc_nota)
            logger.info(f"[GOV_SCRAPER] Nota de Liquidação descarregada: {doc_nota.filename} ({doc_nota.size} bytes)")
        else:
            logger.warning("[GOV_SCRAPER] Não foi possível descarregar a Nota de Liquidação")

        # ── 9. Retornar resultados ──
        if not documents:
            logger.warning(f"[GOV_SCRAPER] Nenhum documento obtido para NIF {masked_nif}")
            return ScraperResult(success=False, error="sem_documentos")

        logger.info(f"[GOV_SCRAPER] {len(documents)} documentos obtidos para NIF {masked_nif}")
        return ScraperResult(success=True, documents=documents)

    except Exception as e:
        # NUNCA logar detalhes que possam conter credenciais
        logger.error(f"[GOV_SCRAPER] Erro interno no scraper Finanças: {type(e).__name__}")
        return ScraperResult(success=False, error=type(e).__name__)

    finally:
        # CRÍTICO: Garantir que TODOS os recursos são SEMPRE libertados
        # Ordem: context → browser → playwright (evita processos zombie)
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


async def _download_financas_document(
    page,
    doc_name: str,
    category: str,
) -> Optional[ScraperDocument]:
    """
    Tenta descarregar um documento específico do Portal das Finanças.

    Estratégia:
    1. Procurar link/botão de download na página atual
    2. Se não encontrar, procurar links de navegação para a sub-página
    3. Tentar descarregar o PDF
    4. Se o download falhar, tentar gerar um PDF da página (print-to-pdf)
    """
    now = datetime.now(timezone.utc)
    safe_filename = f"{doc_name.replace(' ', '_')}_{now.strftime('%Y%m%d')}.pdf"

    # Estratégia 1: Procurar links/botões de download direto
    try:
        # Procurar qualquer link de download ou PDF
        download_selectors = [
            f"a:has-text('{doc_name}')",
            f"a:has-text('Descarregar')",
            FINANCAS_SEL["download_button"],
            FINANCAS_SEL["pdf_link"],
        ]

        for selector in download_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    # Tentar iniciar o download
                    async with page.expect_download(timeout=30000) as download_info:
                        await el.click()
                    download = await download_info.value

                    # Ler os bytes do download
                    tmp_path = await download.path()
                    if tmp_path and os.path.exists(tmp_path):
                        with open(tmp_path, "rb") as f:
                            content_bytes = f.read()

                        if content_bytes and len(content_bytes) > 100:
                            # Limpar ficheiro temporário
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
    except Exception as e:
        logger.debug(f"[GOV_SCRAPER] Download direto falhou para {doc_name}: {type(e).__name__}")

    # Estratégia 2: Procurar navegação para sub-página
    try:
        nav_selectors = [
            f"a:has-text('{doc_name}')",
            FINANCAS_SEL["declaracoes_link"],
            FINANCAS_SEL["nota_liquidacao_link"],
        ]

        for selector in nav_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)

                    # Tentar novamente o download na nova página
                    dl_el = page.locator(FINANCAS_SEL["download_button"]).first
                    if await dl_el.is_visible(timeout=5000):
                        async with page.expect_download(timeout=30000) as download_info:
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
    except Exception as e:
        logger.debug(f"[GOV_SCRAPER] Navegação falhou para {doc_name}: {type(e).__name__}")

    # Estratégia 3: Gerar PDF da página atual (fallback)
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
    except Exception as e:
        logger.debug(f"[GOV_SCRAPER] PDF fallback falhou para {doc_name}: {type(e).__name__}")

    return None


# ================================================================
# SCRAPER: SEGURANÇA SOCIAL
# ================================================================

async def fetch_seg_social_documents(
    niss: str,
    password: str,
) -> ScraperResult:
    """
    Obtém documentos da Segurança Social Direta.

    FLUXO:
    1. Abre o browser headless
    2. Navega para app.seg-social.pt
    3. Insere credenciais (NISS + password)
    4. Verifica se o login foi bem-sucedido
    5. Navega até à secção de documentos
    6. Descarrega a Declaração de Situação Contributiva
    7. Descarrega o Extrato de Remunerações (se disponível)
    8. Fecha o browser e limpa credenciais

    SEGURANÇA:
    - A password NUNCA é logada ou guardada
    - Após a execução, a variável é eliminada com `del` + `gc.collect()`
    - O browser é sempre fechado, mesmo em caso de erro

    Args:
        niss: NISS do beneficiário (11 dígitos)
        password: Password da Segurança Social Direta

    Returns:
        ScraperResult com documentos obtidos ou erro
    """
    # DEV MODE: Mock do scraper — SÓ PRODUÇÃO lança o browser
    if os.environ.get('ENVIRONMENT', '').lower() != 'production':
        logger.info("[GOV_SCRAPER] BLOCKED: ENVIRONMENT != production — browser will NOT launch")
        return ScraperResult(
            success=True,
            documents=[],
            error="MOCK: Documentos Seg. Social obtidos (DEV)",
        )

    masked_niss = _mask_identifier(niss)
    logger.info(f"[GOV_SCRAPER] Iniciando scraper Seg. Social para NISS {masked_niss}")

    try:
        result = await asyncio.wait_for(
            _seg_social_scraper_inner(niss, password),
            timeout=MAX_SCRAPER_DURATION,
        )
        return result

    except asyncio.TimeoutError:
        logger.error(f"[GOV_SCRAPER] Timeout ({MAX_SCRAPER_DURATION}s) no scraper Seg. Social para NISS {masked_niss}")
        return ScraperResult(success=False, error="timeout")

    except Exception as e:
        logger.error(f"[GOV_SCRAPER] Erro no scraper Seg. Social para NISS {masked_niss}: {type(e).__name__}")
        return ScraperResult(success=False, error=type(e).__name__)

    finally:
        # LIMPEZA CRÍTICA: Eliminar credenciais da memória no scope do caller
        del password
        del niss
        _force_gc()

        logger.info("[GOV_SCRAPER] Credenciais Seg. Social limpas da memória")


async def _seg_social_scraper_inner(niss: str, password: str) -> ScraperResult:
    """
    Lógica interna do scraper da Segurança Social.
    Separada do wrapper para garantir cleanup no finally.
    """
    from playwright.async_api import async_playwright

    masked_niss = _mask_identifier(niss)
    documents: List[ScraperDocument] = []

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(**_get_browser_launch_args())
    context = None

    try:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="pt-PT",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

        # ── 1. Navegar para a página de login ──
        logger.info(f"[GOV_SCRAPER] Navegando para Seg. Social (NISS {masked_niss})")
        await page.goto(SEG_SOCIAL_URL, wait_until="networkidle")

        # ── 2. Verificar se há redirecionamento para login ──
        # A Seg. Social pode redirecionar para autenticação.gov.pt
        await page.wait_for_load_state("networkidle", timeout=15000)

        # ── 3. Inserir credenciais ──
        # Tentar encontrar os campos de login
        niss_found = False
        try:
            niss_input = page.locator(SEG_SOCIAL_SEL["niss_input"]).first
            await niss_input.wait_for(state="visible", timeout=10000)
            await niss_input.click()
            await niss_input.fill(niss)
            niss_found = True
            logger.info(f"[GOV_SCRAPER] NISS inserido ({masked_niss})")
        except Exception:
            # Pode usar autenticação.gov.pt — tentar campo genérico de username
            try:
                username_input = page.locator("input[name='username'], input[id='username']").first
                await username_input.wait_for(state="visible", timeout=10000)
                await username_input.click()
                await username_input.fill(niss)
                niss_found = True
                logger.info(f"[GOV_SCRAPER] NISS inserido via campo username ({masked_niss})")
            except Exception:
                logger.warning("[GOV_SCRAPER] Campo NISS/username não encontrado")

        if not niss_found:
            return ScraperResult(success=False, error="campo_niss_nao_encontrado")

        # Password
        try:
            pass_input = page.locator(SEG_SOCIAL_SEL["password_input"]).first
            await pass_input.wait_for(state="visible", timeout=5000)
            await pass_input.click()
            await pass_input.fill(password)
        except Exception:
            logger.warning("[GOV_SCRAPER] Campo password não encontrado")
            return ScraperResult(success=False, error="campo_password_nao_encontrado")

        # ── 4. Submeter login ──
        try:
            login_btn = page.locator(SEG_SOCIAL_SEL["login_button"]).first
            await login_btn.click()
            logger.info("[GOV_SCRAPER] Login Seg. Social submetido")
        except Exception:
            # Tentar Enter
            await page.keyboard.press("Enter")
            logger.info("[GOV_SCRAPER] Login submetido via Enter")

        # Aguardar navegação
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass

        # ── 5. Verificar se o login falhou ──
        try:
            error_el = page.locator(SEG_SOCIAL_SEL["login_error"]).first
            if await error_el.is_visible(timeout=5000):
                logger.warning(f"[GOV_SCRAPER] Login Seg. Social falhou para NISS {masked_niss}")
                return ScraperResult(success=False, error="credenciais_invalidas")
        except Exception:
            pass

        # Verificar URL — se ainda estamos na página de login
        current_url = page.url.lower()
        if "login" in current_url or "autenticacao" in current_url:
            # Pode ser que a página de login ainda esteja carregando
            # Esperar mais um pouco
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            current_url = page.url.lower()
            if "login" in current_url or "autenticacao" in current_url:
                logger.warning(f"[GOV_SCRAPER] Ainda na página de login — credenciais inválidas (NISS {masked_niss})")
                return ScraperResult(success=False, error="credenciais_invalidas")

        logger.info(f"[GOV_SCRAPER] Login Seg. Social bem-sucedido para NISS {masked_niss}!")

        # ── 6. Navegar para Documentos / Situação Contributiva ──
        try:
            # Procurar menu de documentos
            doc_menu = page.locator(SEG_SOCIAL_SEL["documentos_menu"]).first
            if await doc_menu.is_visible(timeout=10000):
                await doc_menu.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            logger.debug("[GOV_SCRAPER] Menu Documentos não encontrado")

        # ── 7. Descarregar Situação Contributiva ──
        doc_sit = await _download_seg_social_document(
            page, "Declaração de Situação Contributiva", "Recibo_Vencimento"
        )
        if doc_sit:
            documents.append(doc_sit)
            logger.info(f"[GOV_SCRAPER] Situação Contributiva descarregada: {doc_sit.filename}")

        # ── 8. Descarregar Extrato de Remunerações ──
        doc_ext = await _download_seg_social_document(
            page, "Extrato de Remunerações", "Mapa_Creditos"
        )
        if doc_ext:
            documents.append(doc_ext)
            logger.info(f"[GOV_SCRAPER] Extrato de Remunerações descarregado: {doc_ext.filename}")

        # ── 9. Retornar resultados ──
        if not documents:
            logger.warning(f"[GOV_SCRAPER] Nenhum documento obtido para NISS {masked_niss}")
            return ScraperResult(success=False, error="sem_documentos")

        logger.info(f"[GOV_SCRAPER] {len(documents)} documentos obtidos para NISS {masked_niss}")
        return ScraperResult(success=True, documents=documents)

    except Exception as e:
        logger.error(f"[GOV_SCRAPER] Erro interno no scraper Seg. Social: {type(e).__name__}")
        # NÃO logar detalhes que possam conter credenciais
        return ScraperResult(success=False, error=type(e).__name__)

    finally:
        # CRÍTICO: Garantir que TODOS os recursos são SEMPRE libertados
        # Ordem: context → browser → playwright (evita processos zombie)
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


async def _download_seg_social_document(
    page,
    doc_name: str,
    category: str,
) -> Optional[ScraperDocument]:
    """
    Tenta descarregar um documento específico da Segurança Social.

    Segue a mesma estratégia do _download_financas_document:
    1. Procurar link/botão de download direto
    2. Navegar para sub-página e tentar download
    3. Fallback: gerar PDF da página atual
    """
    now = datetime.now(timezone.utc)
    safe_filename = f"{doc_name.replace(' ', '_')}_{now.strftime('%Y%m%d')}.pdf"

    # Estratégia 1: Download direto
    try:
        download_selectors = [
            f"a:has-text('{doc_name}')",
            SEG_SOCIAL_SEL["download_button"],
            SEG_SOCIAL_SEL["situacao_contributiva"] if "Contributiva" in doc_name else SEG_SOCIAL_SEL["extrato_remuneracoes"],
        ]

        for selector in download_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    async with page.expect_download(timeout=30000) as download_info:
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
        pass

    # Estratégia 2: Navegar para sub-página
    try:
        nav_selectors = [
            f"a:has-text('{doc_name}')",
            SEG_SOCIAL_SEL["situacao_contributiva"] if "Contributiva" in doc_name else SEG_SOCIAL_SEL["extrato_remuneracoes"],
        ]

        for selector in nav_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)

                    # Tentar download na nova página
                    dl_el = page.locator(SEG_SOCIAL_SEL["download_button"]).first
                    if await dl_el.is_visible(timeout=5000):
                        async with page.expect_download(timeout=30000) as download_info:
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
        pass

    # Estratégia 3: Gerar PDF da página atual (fallback)
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
    Verifica se o Playwright e o browser Chromium estão disponíveis.

    Retorna informações sobre o estado da instalação para diagnóstico.
    Inclui o PLAYWRIGHT_BROWSERS_PATH para ajudar a debugar problemas de path.
    """
    # DEV MODE: SÓ PRODUÇÃO tenta lançar o browser
    if os.environ.get('ENVIRONMENT', '').lower() != 'production':
        return {
            "playwright_installed": False,
            "chromium_available": False,
            "dev_mode": True,
            "error": "BLOCKED: ENVIRONMENT != production — Playwright check skipped",
        }

    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "(default: ~/.cache/ms-playwright)")

    result = {
        "playwright_installed": False,
        "chromium_available": False,
        "browsers_path": browsers_path,
        "error": None,
    }

    try:
        from playwright.async_api import async_playwright
        result["playwright_installed"] = True

        # Verificar se o diretório de browsers existe
        if os.path.isdir(browsers_path):
            result["browsers_dir_exists"] = True
            try:
                result["browsers_dir_contents"] = os.listdir(browsers_path)
            except Exception:
                result["browsers_dir_contents"] = "(erro ao listar)"
        else:
            result["browsers_dir_exists"] = False

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
        result["error"] = "Playwright não instalado. Execute: pip install playwright && playwright install --with-deps chromium"
    except Exception as e:
        result["error"] = f"Erro ao verificar Playwright: {type(e).__name__}: {str(e)[:200]}"

    return result
