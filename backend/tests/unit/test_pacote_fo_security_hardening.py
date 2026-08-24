"""Unit tests for Pacote FO — SSRF mitigation, gov-auth open-redirect
mitigation, and /ws/status authentication hardening.
"""
from __future__ import annotations

import pytest


class _FakeLoop:
    """Minimal stand-in for asyncio's event loop exposing async getaddrinfo."""

    def __init__(self, addr_infos):
        self._addr_infos = addr_infos

    async def getaddrinfo(self, host, port):
        return self._addr_infos


# ====================================================================
# SSRF mitigation — services/scraper.py
# ====================================================================


class TestIsBlockedIpAddress:
    def test_blocks_known_private_ranges(self):
        from services.scraper import _is_blocked_ip_address

        for ip in ("10.0.0.1", "172.16.0.1", "172.31.255.254", "192.168.1.1"):
            assert _is_blocked_ip_address(ip) is True

    def test_blocks_loopback_and_metadata_ip(self):
        from services.scraper import _is_blocked_ip_address

        assert _is_blocked_ip_address("127.0.0.1") is True
        assert _is_blocked_ip_address("169.254.169.254") is True

    def test_blocks_unparseable_ip_conservatively(self):
        from services.scraper import _is_blocked_ip_address

        assert _is_blocked_ip_address("not-an-ip") is True

    def test_allows_public_ip(self):
        from services.scraper import _is_blocked_ip_address

        assert _is_blocked_ip_address("93.184.216.34") is False


@pytest.mark.asyncio
class TestEnsurePublicUrl:
    async def test_blocks_loopback_literal(self):
        from services.scraper import SSRFBlockedURLError, _ensure_public_url

        with pytest.raises(SSRFBlockedURLError):
            await _ensure_public_url("http://127.0.0.1/admin")

    async def test_blocks_cloud_metadata_ip_literal(self):
        from services.scraper import SSRFBlockedURLError, _ensure_public_url

        with pytest.raises(SSRFBlockedURLError):
            await _ensure_public_url(
                "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
            )

    async def test_blocks_private_ranges_literal(self):
        from services.scraper import SSRFBlockedURLError, _ensure_public_url

        for host in ("10.1.2.3", "172.16.5.6", "192.168.1.1"):
            with pytest.raises(SSRFBlockedURLError):
                await _ensure_public_url(f"http://{host}/x")

    async def test_blocks_disallowed_scheme(self):
        from services.scraper import SSRFBlockedURLError, _ensure_public_url

        with pytest.raises(SSRFBlockedURLError):
            await _ensure_public_url("file:///etc/passwd")

    async def test_blocks_url_without_hostname(self):
        from services.scraper import SSRFBlockedURLError, _ensure_public_url

        with pytest.raises(SSRFBlockedURLError):
            await _ensure_public_url("http:///no-host")

    async def test_allows_public_hostname_resolving_to_public_ip(self, monkeypatch):
        from services import scraper as scraper_module

        fake_loop = _FakeLoop([(2, 1, 6, "", ("93.184.216.34", 0))])
        monkeypatch.setattr(scraper_module.asyncio, "get_running_loop", lambda: fake_loop)

        # Não deve levantar SSRFBlockedURLError
        await scraper_module._ensure_public_url("http://example.com/imovel/123")

    async def test_blocks_dns_rebinding_to_private_ip(self, monkeypatch):
        from services import scraper as scraper_module

        fake_loop = _FakeLoop([(2, 1, 6, "", ("169.254.169.254", 0))])
        monkeypatch.setattr(scraper_module.asyncio, "get_running_loop", lambda: fake_loop)

        with pytest.raises(scraper_module.SSRFBlockedURLError):
            await scraper_module._ensure_public_url("http://attacker-controlled.example/")

    async def test_blocks_when_dns_resolution_fails(self, monkeypatch):
        import socket

        from services import scraper as scraper_module

        class _FailingLoop:
            async def getaddrinfo(self, host, port):
                raise socket.gaierror("name resolution failed")

        monkeypatch.setattr(scraper_module.asyncio, "get_running_loop", lambda: _FailingLoop())

        with pytest.raises(scraper_module.SSRFBlockedURLError):
            await scraper_module._ensure_public_url("http://does-not-resolve.invalid/")


@pytest.mark.asyncio
class TestFetchMethodsRejectBlockedUrls:
    async def test_fetch_url_returns_none_for_blocked_url(self):
        from services.scraper import PropertyScraper

        scraper = PropertyScraper()
        result = await scraper._fetch_url(
            "http://169.254.169.254/latest/meta-data/", retries=1
        )
        assert result is None

    async def test_fetch_page_content_returns_none_for_blocked_url(self):
        from services.scraper import PropertyScraper

        scraper = PropertyScraper()
        result = await scraper._fetch_page_content(
            "http://192.168.1.1/internal-dashboard", use_proxy=False
        )
        assert result is None


@pytest.mark.asyncio
class TestScraperApiAiBlocksPrivateUrls:
    async def test_run_analyze_page_with_ai_blocks_metadata_url(self):
        from fastapi import HTTPException

        from services.scraper_api_ai import run_analyze_page_with_ai
        from services.scraper_api_models import ScrapeRequest

        request = ScrapeRequest(
            url="http://169.254.169.254/latest/meta-data/iam/security-credentials/"
        )
        with pytest.raises(HTTPException) as exc_info:
            await run_analyze_page_with_ai(request, {"id": "u1"})
        assert exc_info.value.status_code == 400

    async def test_run_analyze_page_with_ai_blocks_private_ip(self):
        from fastapi import HTTPException

        from services.scraper_api_ai import run_analyze_page_with_ai
        from services.scraper_api_models import ScrapeRequest

        request = ScrapeRequest(url="http://10.0.0.5/secret")
        with pytest.raises(HTTPException) as exc_info:
            await run_analyze_page_with_ai(request, {"id": "u1"})
        assert exc_info.value.status_code == 400


# ====================================================================
# Gov-auth open-redirect mitigation — services/gov_auth_api_*
# ====================================================================


class TestGovAuthRedirectValidation:
    def test_allows_configured_cors_origin(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)

        assert helpers._is_allowed_redirect_origin("https://app.powercell.pt/public-form") is True

    def test_rejects_attacker_domain(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)

        assert helpers._is_allowed_redirect_origin("https://evil.example.com/phish") is False

    def test_rejects_non_http_scheme(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)

        assert helpers._is_allowed_redirect_origin("javascript:alert(1)") is False

    def test_allows_configured_regex_origin(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers

        monkeypatch.setattr(config, "CORS_ORIGINS", [], raising=False)
        monkeypatch.setattr(
            config,
            "CORS_ORIGIN_REGEX",
            [r"https://[a-z0-9-]+\.vercel\.app$"],
            raising=False,
        )

        assert helpers._is_allowed_redirect_origin("https://preview-123.vercel.app/x") is True
        assert helpers._is_allowed_redirect_origin("https://evil-vercel.app.attacker.com/x") is False

    def test_resolve_safe_redirect_base_falls_back_to_default(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)

        assert helpers.resolve_safe_redirect_base("https://evil.example.com") == helpers.FRONTEND_URL
        assert helpers.resolve_safe_redirect_base(None) == helpers.FRONTEND_URL

    def test_resolve_safe_redirect_base_accepts_allowed_domain(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)

        assert (
            helpers.resolve_safe_redirect_base("https://app.powercell.pt/public-form")
            == "https://app.powercell.pt/public-form"
        )


@pytest.mark.asyncio
class TestGovAuthLoginAndCallbackUseSafeRedirect:
    async def test_login_ignores_disallowed_redirect(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers
        from services.gov_auth_api_login import run_gov_auth_login

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)
        monkeypatch.setattr(helpers, "IS_MOCK", True, raising=False)

        import base64

        response = await run_gov_auth_login(redirect="https://evil.example.com")
        location = response.headers["location"]
        assert "state=" in location
        state = location.split("state=")[1]
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        assert decoded == helpers.FRONTEND_URL

    async def test_login_accepts_allowed_redirect(self, monkeypatch):
        import config
        from services import gov_auth_api_helpers as helpers
        from services.gov_auth_api_login import run_gov_auth_login

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)
        monkeypatch.setattr(helpers, "IS_MOCK", True, raising=False)

        import base64

        response = await run_gov_auth_login(redirect="https://app.powercell.pt/onboarding")
        location = response.headers["location"]
        state = location.split("state=")[1]
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        assert decoded == "https://app.powercell.pt/onboarding"

    async def test_callback_ignores_tampered_state_domain(self, monkeypatch):
        import base64

        import config
        from services import gov_auth_api_helpers as helpers
        from services.gov_auth_api_callback import run_gov_auth_callback

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)
        monkeypatch.setattr(helpers, "IS_MOCK", True, raising=False)

        evil_state = base64.urlsafe_b64encode(b"https://evil.example.com").decode()
        response = await run_gov_auth_callback(code="mock123", state=evil_state)
        location = response.headers["location"]
        assert location.startswith(helpers.FRONTEND_URL)
        assert "evil.example.com" not in location

    async def test_callback_accepts_allowed_state_domain(self, monkeypatch):
        import base64

        import config
        from services import gov_auth_api_helpers as helpers
        from services.gov_auth_api_callback import run_gov_auth_callback

        monkeypatch.setattr(config, "CORS_ORIGINS", ["https://app.powercell.pt"], raising=False)
        monkeypatch.setattr(config, "CORS_ORIGIN_REGEX", [], raising=False)
        monkeypatch.setattr(helpers, "IS_MOCK", True, raising=False)

        good_state = base64.urlsafe_b64encode(b"https://app.powercell.pt").decode()
        response = await run_gov_auth_callback(code="mock123", state=good_state)
        location = response.headers["location"]
        assert location.startswith("https://app.powercell.pt/public-form?gov_token=")


# ====================================================================
# /ws/status authentication hardening — routes/websocket.py
# ====================================================================


class TestWebsocketStatusRequiresAuth:
    def test_status_route_depends_on_require_admin(self):
        from routes.websocket import router

        status_route = next(r for r in router.routes if getattr(r, "path", None) == "/ws/status")
        dependant_calls = [d.call for d in status_route.dependant.dependencies]
        assert any(getattr(c, "__name__", "") == "role_checker" for c in dependant_calls), (
            "GET /ws/status deve exigir autenticação via require_admin()/require_roles()"
        )

    def test_websocket_module_imports_require_admin(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / "routes" / "websocket.py").read_text()
        assert "require_admin" in text
        assert "Depends(require_admin())" in text
