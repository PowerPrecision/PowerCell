"""O JWT do WebSocket e o utilizador nos logs do Render (Nov 2026)."""
from __future__ import annotations

import logging

from utils.logger import FiltroDeSegredos, ocultar_segredos

JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhIn0.YEWJBbhe5z4Ui52S7yOxKsCLaFsJbCWEqQFi1BmeEj0"


def test_o_token_do_websocket_sai_do_log():
    linha = "('10.1.2.3', 60060) - \"WebSocket /api/ws/notifications?token=" + JWT + "\" [accepted]"
    limpa = ocultar_segredos(linha)
    assert JWT not in limpa and "token=[oculto]" in limpa and "[accepted]" in limpa


def test_outros_parametros_ficam():
    assert ocultar_segredos("/api/x?page=2&access_token=abc&q=ana") == "/api/x?page=2&access_token=[oculto]&q=ana"


def test_o_filtro_reescreve_o_registo_com_argumentos_como_o_uvicorn():
    # o uvicorn regista '%s - "WebSocket %s" [accepted]' com argumentos: o filtro tem de ver a mensagem final
    registo = logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1, '%s - "WebSocket %s" [accepted]',
                                ("10.1.2.3:1", f"/api/ws/notifications?token={JWT}"), None)
    assert FiltroDeSegredos().filter(registo) is True
    assert JWT not in registo.getMessage() and "token=[oculto]" in registo.getMessage()


def test_o_filtro_esta_no_logger_do_uvicorn():
    assert any(isinstance(f, FiltroDeSegredos) for f in logging.getLogger("uvicorn.error").filters)


def test_o_log_de_pedidos_mostra_o_utilizador_sem_email():
    from types import SimpleNamespace

    from middleware.logging_middleware import LoggingMiddleware

    pedido = SimpleNamespace(state=SimpleNamespace(user={"id": "u-1", "role": "indexacao"}))
    assert LoggingMiddleware._extract_user_info(pedido) == "[User: u-1 role=indexacao]"
