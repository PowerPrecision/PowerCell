"""O registo público responde mesmo com o servidor de email pendurado.

REGRESSÃO (CI, 2026-09-21): `tests/test_public.py` falhou em três testes com
`RuntimeError: No response returned.` ao fim de exactamente 30000ms. O
`/public/client-registration` fazia `await send_email(...)` dentro do pedido
e o `send_email` corria `smtplib.SMTP_SSL(...)` — síncrono — no event loop.
Com o servidor de email inacessível, o pedido ficava pendurado os 30s do
timeout do SMTP e o cliente HTTP desistia primeiro.

O envio de um email nunca pode decidir se um formulário público responde:
o `except` do fluxo já tratava a falha de envio como não-fatal, só que
ninguém sobrevivia à ESPERA. Este teste reproduz a condição original com um
servidor que aceita a ligação e nunca responde.
"""
import socket
import threading
import time
import uuid

import pytest

# A margem entre os dois valores é o que dá dentes ao teste: com o envio
# dentro do pedido, a resposta chega aos 8s; em background, abaixo de 1s.
# (Com um limite frouxo — 5s contra um timeout de 2s — o teste passava
# nas DUAS versões e não provava nada. Verificado por mutação.)
LIMITE_RESPOSTA = 3.0   # o pedido não pode esperar pelo servidor de email
TIMEOUT_SMTP = "8"      # tempo que o envio fica pendurado


class _SmtpPendurado:
    """Aceita ligações TCP e nunca responde — servidor de email inacessível."""

    def __init__(self):
        self._servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._servidor.bind(("127.0.0.1", 0))
        self._servidor.listen(16)
        self._servidor.settimeout(0.5)
        self.porta = self._servidor.getsockname()[1]
        self._abertas = []
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._aceitar, daemon=True)
        self._thread.start()

    def _aceitar(self):
        while not self._parar.is_set():
            try:
                ligacao, _ = self._servidor.accept()
                self._abertas.append(ligacao)   # deixa pendurada de propósito
            except socket.timeout:
                continue
            except OSError:
                break

    def fechar(self):
        self._parar.set()
        for ligacao in self._abertas:
            try:
                ligacao.close()
            except OSError:
                pass
        try:
            self._servidor.close()
        except OSError:
            pass


@pytest.fixture
def smtp_pendurado(monkeypatch):
    servidor = _SmtpPendurado()
    # `get_email_accounts` lê o ambiente a cada chamada: a conta "power"
    # passa a apontar para o servidor que nunca responde.
    monkeypatch.setenv("POWER_EMAIL", "power@test.local")
    monkeypatch.setenv("POWER_PASSWORD", "segredo")
    monkeypatch.setenv("POWER_SMTP_SERVER", "127.0.0.1")
    monkeypatch.setenv("POWER_SMTP_PORT", str(servidor.porta))
    monkeypatch.setenv("SMTP_CONNECT_TIMEOUT", TIMEOUT_SMTP)
    yield servidor
    servidor.fechar()


@pytest.mark.integration
class TestRegistoPublicoComEmailPendurado:
    async def test_responde_depressa_apesar_do_smtp_pendurado(self, client, smtp_pendurado):
        """O pedido não pode esperar pelo servidor de email."""
        inicio = time.monotonic()
        resposta = await client.post("/public/client-registration", json={
            "name": "Teste SMTP Pendurado",
            "email": f"smtp_pendurado_{uuid.uuid4().hex[:8]}@email.pt",
            "phone": "+351 999 000 222",
            "process_type": "credito",
        })
        decorrido = time.monotonic() - inicio

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["success"] is True
        assert decorrido < LIMITE_RESPOSTA, (
            f"o registo público demorou {decorrido:.1f}s com o servidor de email "
            "pendurado — o envio voltou para dentro do ciclo pedido/resposta"
        )

    async def test_o_cliente_fica_gravado_mesmo_sem_email(self, client, smtp_pendurado):
        """O registo é o que importa; o email é acessório e vai em background."""
        email = f"smtp_pendurado_{uuid.uuid4().hex[:8]}@email.pt"
        resposta = await client.post("/public/client-registration", json={
            "name": "Teste Persistência",
            "email": email,
            "phone": "+351 999 000 333",
            "process_type": "credito",
        })

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["client_id"], "o cliente não foi criado"
