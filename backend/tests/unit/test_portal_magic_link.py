"""
Testes unitários para services.portal_magic_link (builders puros).
"""
from services.portal_magic_link import build_magic_link_email_bodies


class TestBuildMagicLinkEmailBodies:
    def test_includes_client_name_and_link(self):
        text, html = build_magic_link_email_bodies(
            client_name="Maria Silva",
            client_email="maria@example.com",
            magic_link="https://app.example.com/portal/abc12345",
            portal_access_code="XYZ99",
        )
        assert "Maria Silva" in text
        assert "https://app.example.com/portal/abc12345" in text
        assert "XYZ99" in text
        assert "maria@example.com" in text
        assert "Maria Silva" in html
        assert "https://app.example.com/portal/abc12345" in html
        assert "XYZ99" in html

    def test_missing_access_code_shows_dash(self):
        text, html = build_magic_link_email_bodies(
            client_name="João",
            client_email="joao@example.com",
            magic_link="https://app.example.com/portal/zzzz",
            portal_access_code=None,
        )
        assert "—" in text
        assert "—" in html
