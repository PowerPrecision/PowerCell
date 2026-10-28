"""
Emails enviados chegavam como «texto corrido» (Out 2026).

Causa: o corpo em texto simples escrito no Webmail (e nos templates,
rascunhos automáticos e mensagem do envio de documentação aos bancos)
passava por ``sanitize_string``, que faz ``' '.join(value.split())`` —
todas as quebras de linha e parágrafos desapareciam ANTES do envio.
De caminho, ``&``/``<``/``>`` eram apagados (o bleach escapava-os para
entidades e o passo seguinte removia as entidades): «Silva & Filhos»
saía «Silva Filhos».

Correr: .venv/bin/python -m pytest tests/unit/test_emails_preservam_formatacao.py -q
"""
import os
import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CORPO = "Bom dia,\n\nSegue a documentação:\n- CC\n- IRS\n\nCumprimentos,\nSilva & Filhos, Lda. (taxa < 3%)"


class TestSanitizeMultilineText:
    def test_preserva_quebras_de_linha_e_paragrafos(self):
        from utils.input_sanitization import sanitize_multiline_text

        assert sanitize_multiline_text(CORPO, max_length=10000) == CORPO

    def test_normaliza_crlf_e_remove_nulos(self):
        from utils.input_sanitization import sanitize_multiline_text

        assert sanitize_multiline_text("a\r\nb\rc\x00d") == "a\nb\ncd"

    def test_remove_tags_html_mas_mantem_caracteres_literais(self):
        from utils.input_sanitization import sanitize_multiline_text

        out = sanitize_multiline_text("<b>Taxa</b> < 3% & spread > 1%\n<script>x</script>fim")
        assert "<b>" not in out and "<script" not in out
        assert out.startswith("Taxa < 3% & spread > 1%\n")

    def test_trunca_ao_tamanho_maximo(self):
        from utils.input_sanitization import sanitize_multiline_text

        assert sanitize_multiline_text("a\n" * 50, max_length=10) == "a\na\na\na\na"

    def test_vazio(self):
        from utils.input_sanitization import sanitize_multiline_text

        assert sanitize_multiline_text("") == ""
        assert sanitize_multiline_text(None) == ""


class TestPlainTextToHtml:
    def test_escapa_e_converte_quebras(self):
        from utils.input_sanitization import plain_text_to_html

        assert plain_text_to_html("a & <b>\nc") == "a &amp; &lt;b&gt;<br/>c"


async def test_webmail_envio_guarda_o_corpo_com_as_quebras_de_linha(fake_async_db):
    """O registo que segue para o envio real mantém o corpo tal como escrito."""
    from models.email import EmailSendRequest
    from services import email_process_crud as crud
    from services import email_send_queue as q

    payload = EmailSendRequest(to_emails=["destino@x.pt"], subject="Assunto", body=CORPO)
    request = MagicMock()
    request.headers = {}

    with patch.object(q, "db", fake_async_db), \
         patch.object(q, "schedule_pending_email_send", AsyncMock()), \
         patch.object(q, "send_email", AsyncMock(return_value={"success": True})), \
         patch("services.email_config_resolver.resolve_email_config_for_sync",
               AsyncMock(return_value={"email_address": "geral@x.pt"})), \
         patch("services.auth.get_active_company_id_async", AsyncMock(return_value=None)):
        response = await crud.run_send_email(
            payload, request, {"id": "u1", "email": "u1@x.pt", "role": "consultor"},
            account="personal",
        )

    stored = await fake_async_db.pending_email_sends.find_one({"id": response["send_id"]})
    assert stored["body"] == CORPO


async def test_template_de_email_guarda_o_corpo_com_as_quebras_de_linha(fake_async_db):
    from models.email import EmailTemplateCreate
    from services import email_templates_drafts as mod

    template = EmailTemplateCreate(name="T", subject="S", body=CORPO)
    with patch.object(mod, "db", fake_async_db), \
         patch("services.auth.get_active_company_id_async", AsyncMock(return_value=None)):
        await mod.run_create_email_template(template, MagicMock(), {"id": "u1"})

    stored = await fake_async_db.email_templates.find_one({"name": "T"})
    assert stored["body"] == CORPO


def test_nenhum_corpo_de_email_passa_por_sanitize_string():
    """Guarda: os corpos de email não podem voltar a ser achatados."""
    ficheiros = [
        "services/email_process_crud.py",
        "services/email_templates_drafts.py",
        "services/email_documentation.py",
    ]
    padrao = re.compile(r"sanitize_string\([^)]*(body|custom_message)")
    culpados = []
    for rel in ficheiros:
        with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
            for n, linha in enumerate(fh, 1):
                if padrao.search(linha):
                    culpados.append(f"{rel}:{n}")
    assert culpados == []


def test_notas_do_link_temporario_sao_escapadas_e_mantem_quebras():
    """As notas do link de upload entravam cruas no HTML (sem escape nem <br/>)."""
    with open(os.path.join(BACKEND, "services/temp_link_service.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "<strong>Notas:</strong> {description}" not in src
    assert "plain_text_to_html(description)" in src
