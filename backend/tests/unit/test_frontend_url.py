"""
Testes unitários para utils.frontend_url.get_frontend_url.

Cobre as 3 prioridades documentadas:
1. Header Referer/Origin
2. Env var FRONTEND_URL
3. String vazia (sem fallback hardcoded)
"""
import os
from unittest.mock import MagicMock

import pytest

from utils.frontend_url import get_frontend_url


def _fake_request(headers: dict | None = None) -> MagicMock:
    req = MagicMock()
    req.headers = headers or {}
    return req


class TestGetFrontendUrlFromHeaders:
    def test_prefer_referer(self, monkeypatch):
        monkeypatch.delenv("FRONTEND_URL", raising=False)
        req = _fake_request({"referer": "https://app.example.com/processos/123"})
        assert get_frontend_url(req) == "https://app.example.com"

    def test_fall_back_to_origin_when_no_referer(self, monkeypatch):
        monkeypatch.delenv("FRONTEND_URL", raising=False)
        req = _fake_request({"origin": "https://portal.example.com"})
        assert get_frontend_url(req) == "https://portal.example.com"

    def test_referer_beats_origin(self, monkeypatch):
        monkeypatch.delenv("FRONTEND_URL", raising=False)
        req = _fake_request({
            "referer": "https://from-referer.example.com/x",
            "origin": "https://from-origin.example.com",
        })
        assert get_frontend_url(req) == "https://from-referer.example.com"

    def test_referer_beats_env(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "https://env.example.com")
        req = _fake_request({"referer": "https://browser.example.com/page"})
        assert get_frontend_url(req) == "https://browser.example.com"

    def test_ignores_malformed_referer_without_scheme(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "https://env.example.com")
        req = _fake_request({"referer": "not-a-url"})
        assert get_frontend_url(req) == "https://env.example.com"


class TestGetFrontendUrlFromEnv:
    def test_uses_frontend_url_env(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "https://env.example.com/")
        req = _fake_request()
        assert get_frontend_url(req) == "https://env.example.com"

    def test_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_URL", "https://env.example.com///")
        req = _fake_request()
        assert get_frontend_url(req) == "https://env.example.com"


class TestGetFrontendUrlEmpty:
    def test_returns_empty_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv("FRONTEND_URL", raising=False)
        req = _fake_request()
        assert get_frontend_url(req) == ""
