"""`media-src 'self' blob:` e `microphone=(self)` — nos TRÊS sítios.

OS DOIS DEFEITOS (Set 2026)
===========================
1. **CSP sem `media-src`.** Nem os dois blocos do `frontend/vercel.json`
   nem o cabeçalho do `server.py` o declaravam. O `media-src` **não
   herda** o `img-src`: cai no `default-src 'self'`, e as notas de voz —
   que o browser serve de um `blob:` — eram recusadas com
   *"Loading media from 'blob:...' violates the following Content
   Security Policy directive"*.

2. **`Permissions-Policy: microphone=()`.** A lista VAZIA desliga o
   microfone para **todas** as origens. O `getUserMedia` falha com
   `NotAllowedError` **sem o browser pedir permissão** — e era essa a
   parte do sintoma que nenhuma outra hipótese explicava ("aparece
   'Acesso ao microfone recusado' sem que o browser pergunte nada").

   Registo de uma suposição minha que estava errada: eu tinha apontado
   o contexto seguro (HTTPS) como causa provável. Não era. O HTTPS
   explicaria a falha mas não a ausência de prompt.

PORQUE É QUE O TESTE OLHA PARA OS TRÊS SÍTIOS
=============================================
O `vercel.json` governa a PÁGINA (é ele que serve o documento HTML) e o
`server.py` governa as respostas da API. Corrigir um e esquecer o outro
é a forma do "Menu e rotas têm de concordar": divergem sem dar erro, e o
sintoma volta no ambiente que usar o outro caminho. São três blocos —
dois no `vercel.json` (`/portal(.*)` e o resto) e um no `server.py` — e
o do Portal conta porque o cliente também reproduz áudio.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]


def _blocos_do_vercel() -> list[dict]:
    dados = json.loads((RAIZ / "frontend" / "vercel.json").read_text(encoding="utf-8"))
    blocos = []
    for entrada in dados.get("headers", []):
        mapa = {h["key"]: h["value"] for h in entrada.get("headers", [])}
        if "Content-Security-Policy" in mapa or "Permissions-Policy" in mapa:
            blocos.append({"source": entrada.get("source"), **mapa})
    return blocos


def _cabecalhos_do_backend() -> str:
    return (RAIZ / "backend" / "server.py").read_text(encoding="utf-8")


class TestOVercelPermiteMediaBlob:
    def test_ha_mesmo_dois_blocos_a_verificar(self):
        """Contraprova de cobertura: se um bloco desaparecer do ficheiro,
        os testes abaixo passariam sem verificar o Portal."""
        fontes = {b["source"] for b in _blocos_do_vercel()}
        assert any("portal" in (s or "") for s in fontes)
        assert len(_blocos_do_vercel()) >= 2

    @pytest.mark.parametrize("bloco", _blocos_do_vercel())
    def test_cada_bloco_declara_media_src_com_blob(self, bloco):
        csp = bloco.get("Content-Security-Policy", "")
        assert "media-src" in csp, bloco["source"]
        directiva = csp.split("media-src", 1)[1].split(";", 1)[0]
        assert "blob:" in directiva, bloco["source"]
        assert "'self'" in directiva, bloco["source"]

    @pytest.mark.parametrize("bloco", _blocos_do_vercel())
    def test_cada_bloco_permite_o_microfone_na_propria_origem(self, bloco):
        politica = bloco.get("Permissions-Policy", "")
        assert "microphone=(self)" in politica, bloco["source"]
        assert "microphone=()" not in politica, bloco["source"]


class TestOBackendPermiteOMesmo:
    def test_o_csp_declara_media_src_com_blob(self):
        fonte = _cabecalhos_do_backend()
        assert '"media-src \'self\' blob:; "' in fonte

    def test_o_microfone_nao_esta_desligado(self):
        fonte = _cabecalhos_do_backend()
        assert '"microphone=(self), "' in fonte
        assert '"microphone=(), "' not in fonte


class TestNaoSeAbriuMaisDoQueOPedido:
    """Relaxar uma política é o tipo de alteração que se alarga sozinha."""

    @pytest.mark.parametrize("bloco", _blocos_do_vercel())
    def test_a_camara_continua_desligada(self, bloco):
        assert "camera=()" in bloco.get("Permissions-Policy", ""), bloco["source"]

    @pytest.mark.parametrize("bloco", _blocos_do_vercel())
    def test_o_media_src_nao_abre_para_qualquer_origem(self, bloco):
        # O `in` antes do `split` nao e zelo: sem ele, um `media-src`
        # AUSENTE fazia este teste morrer com `IndexError` em vez de
        # dizer o que falta — apanhado a medir a mutacao deste lote.
        csp = bloco.get("Content-Security-Policy", "")
        assert "media-src" in csp, f"{bloco['source']}: media-src ausente"
        directiva = csp.split("media-src", 1)[1].split(";", 1)[0]
        assert "*" not in directiva, bloco["source"]
        assert "http:" not in directiva, bloco["source"]

    def test_o_default_src_continua_self(self):
        for bloco in _blocos_do_vercel():
            csp = bloco.get("Content-Security-Policy", "")
            assert "default-src 'self'" in csp, bloco["source"]
