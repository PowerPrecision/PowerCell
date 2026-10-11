"""D-4 — o IP em que o limite por IP confia conta-se a partir da DIREITA.

O ATAQUE (`TestAExploracao`): o `_get_client_ip` lia o PRIMEIRO elemento do
`X-Forwarded-For`, que é o que o cliente envia (os proxies acrescentam ao
fim). Quem ataca mudava-o a cada pedido e o limite por IP nunca mordia. Estes
testes são o ataque, escritos para morder primeiro: dois pedidos com o
mesmo peer e o mesmo IP real, e `X-Forwarded-For` forjado diferente, TÊM de
cair na MESMA chave de limite.
"""
from __future__ import annotations

import logging

import pytest
from starlette.requests import Request

from middleware import rate_limit
from middleware.client_ip import ip_do_cliente, proxies_de_confianca

REAL = "198.51.100.7"
PEER_DO_PROXY = "10.0.0.5"


def _pedido(*, xff=None, peer=PEER_DO_PROXY, extra=None):
    cabecalhos = []
    for valor in ([xff] if isinstance(xff, str) else (xff or [])):
        cabecalhos.append((b"x-forwarded-for", valor.encode()))
    for nome, valor in (extra or {}).items():
        cabecalhos.append((nome.lower().encode(), valor.encode()))
    return Request({
        "type": "http", "method": "POST", "path": "/x", "query_string": b"",
        "headers": cabecalhos,
        "client": (peer, 1234) if peer else None,
    })


@pytest.fixture(autouse=True)
def _um_proxy(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)


class TestAExploracao:
    def test_o_cliente_nao_escolhe_a_sua_chave_de_limite(self):
        """O proxy acrescenta o IP real ao fim; o que vem antes é do atacante."""
        chaves = {
            rate_limit._get_rate_limit_key(_pedido(xff=f"203.0.113.{i}, {REAL}"))
            for i in range(1, 30)
        }
        assert chaves == {f"ip:{REAL}"}

    def test_forjar_varios_elementos_a_esquerda_tambem_nao_serve(self):
        pedido = _pedido(xff=f"1.1.1.1, 2.2.2.2, 3.3.3.3, {REAL}")
        assert ip_do_cliente(pedido) == REAL

    def test_cabecalho_repetido_conta_o_ultimo_acrescentado(self):
        """Duas linhas do cabeçalho: o proxy acrescenta ao fim da última."""
        pedido = _pedido(xff=["9.9.9.9", f"8.8.8.8, {REAL}"])
        assert ip_do_cliente(pedido) == REAL

    def test_x_real_ip_nao_e_lido(self):
        """Também é um cabeçalho do cliente."""
        pedido = _pedido(xff=f"1.1.1.1, {REAL}", extra={"X-Real-IP": "6.6.6.6"})
        assert ip_do_cliente(pedido) == REAL
        sem_xff = _pedido(xff=None, extra={"X-Real-IP": "6.6.6.6"})
        assert ip_do_cliente(sem_xff) == PEER_DO_PROXY

    def test_utilizadores_diferentes_atras_do_mesmo_proxy_nao_colapsam(self):
        """A contraprova: a correcção não pode juntar toda a gente numa chave."""
        a = rate_limit._get_rate_limit_key(_pedido(xff="1.1.1.1, 198.51.100.1"))
        b = rate_limit._get_rate_limit_key(_pedido(xff="1.1.1.1, 198.51.100.2"))
        assert a != b


class TestOsProxiesDeConfianca:
    def test_por_omissao_e_um(self):
        assert proxies_de_confianca() == 1

    def test_dois_proxies_cloudflare_mais_render(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
        pedido = _pedido(xff=f"1.1.1.1, {REAL}, 172.70.0.1")
        assert ip_do_cliente(pedido) == REAL

    def test_zero_ignora_o_cabecalho_e_usa_o_peer(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
        assert ip_do_cliente(_pedido(xff=f"1.1.1.1, {REAL}")) == PEER_DO_PROXY

    @pytest.mark.parametrize("valor", ["abc", "-1", "1.5"])
    def test_valor_invalido_volta_ao_omisso_e_diz_no_log(self, monkeypatch, caplog, valor):
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", valor)
        with caplog.at_level(logging.WARNING, logger="middleware.client_ip"):
            assert proxies_de_confianca() == 1
        assert any("TRUSTED_PROXY_HOPS" in r.getMessage() for r in caplog.records)

    def test_vazio_conta_como_nao_definido(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "  ")
        assert proxies_de_confianca() == 1


class TestRecuoParaOPeer:
    def test_sem_cabecalho_usa_o_peer(self):
        assert ip_do_cliente(_pedido(xff=None)) == PEER_DO_PROXY

    def test_cabecalho_mais_curto_do_que_os_proxies_usa_o_peer(self, monkeypatch):
        """Com dois proxies declarados, um só elemento é um pedido que não
        passou por eles — não se adivinha."""
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
        assert ip_do_cliente(_pedido(xff=REAL)) == PEER_DO_PROXY

    def test_elemento_que_nao_e_ip_usa_o_peer(self):
        assert ip_do_cliente(_pedido(xff="1.1.1.1, <script>")) == PEER_DO_PROXY

    def test_ipv6_e_aceite(self):
        assert ip_do_cliente(_pedido(xff="1.1.1.1, 2001:db8::1")) == "2001:db8::1"

    def test_sem_peer_nem_cabecalho_nao_levanta(self):
        assert ip_do_cliente(_pedido(xff=None, peer=None)) == "unknown"

    def test_pedido_falso_dos_testes_nao_levanta(self):
        from unittest.mock import MagicMock
        assert ip_do_cliente(MagicMock()) == "unknown"


class TestLigacao:
    """Apagar a chamada não parte teste nenhum se ninguém a afirmar."""

    def test_o_limiter_usa_o_ponto_unico(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(rate_limit._get_client_ip)
        assert "ip_do_cliente" in corpo
        assert "split" not in corpo and "X-Forwarded-For" not in corpo

    @pytest.mark.parametrize("ficheiro", [
        "services/auth_login_handlers.py",
        "services/auth_sessions_handlers.py",
        "services/audit_trail_service.py",
        "services/rgpd_public.py",
    ])
    def test_ninguem_le_o_primeiro_elemento_do_cabecalho(self, ficheiro):
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        with open(ficheiro, encoding="utf-8") as f:
            codigo = codigo_sem_comentarios(f.read())
        assert "X-Forwarded-For" not in codigo
        assert "ip_do_cliente" in codigo
