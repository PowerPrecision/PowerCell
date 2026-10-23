"""`scripts/diagnosticar_saida_para_atlas.py` — corre no Shell do Render, não pode vazar credenciais."""
from __future__ import annotations

import importlib.util
import urllib.request
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "diagnosticar_saida_para_atlas.py"


@pytest.fixture
def modulo():
    spec = importlib.util.spec_from_file_location("diagnosticar_saida_para_atlas", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("url,esperado", [
    ("mongodb+srv://utilizador:segredo@cluster0.abc.mongodb.net/db?retryWrites=true", "cluster0.abc.mongodb.net"),
    ("mongodb://u:p%40ss@h1:27017,h2:27017/db", "h1:27017,h2:27017"),
    ("mongodb://u:pass@word@host:27017", "host:27017"),      # '@' sem escape na palavra-passe
    ("mongodb://localhost:27017", "localhost:27017"),
])
def test_o_host_nunca_leva_credenciais(modulo, url, esperado):
    host = modulo.host_do_url(url)
    assert host == esperado
    assert "segredo" not in host and "pass" not in host.replace("localhost", "")


def test_o_script_nao_imprime_o_url(modulo):
    from tests.unit.helpers_fonte import codigo_sem_comentarios
    fonte = codigo_sem_comentarios(SCRIPT.read_text(encoding="utf-8"))
    assert "{url}" not in fonte and "print(url" not in fonte
    assert "host_do_url(url)" in fonte      # contraprova: o que se imprime é só o host


def test_so_conta_respostas_que_sao_um_ipv4(modulo, monkeypatch):
    class Resposta:
        def __init__(self, texto): self.texto = texto
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.texto.encode()

    respostas = iter(["203.0.113.7", "<html>erro</html>", "203.0.113.7"] * 3)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Resposta(next(respostas)))
    vistos = modulo.ips_de_saida()
    assert set(vistos) == {"203.0.113.7"}


def test_sem_nenhum_eco_nao_ha_ip_e_o_script_di_lo(modulo, monkeypatch, capsys):
    def falha(*a, **k):
        raise OSError("sem rede")
    monkeypatch.setattr(urllib.request, "urlopen", falha)
    assert modulo.main() == 2
    assert "Não foi possível determinar" in capsys.readouterr().out
