"""O cliente de análise de documentos tem de ler a `OPENAI_API_KEY`.

O QUE ESTAVA MAL (401 em produção, Set 2026)
============================================
O dono definiu `OPENAI_API_KEY` / `OPENAI_ORGANIZATION_ID` no Render e a
API continuou a responder **401 "you didn't provide an API key"**.

`services/ai_document.py` tinha:

    EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')   # topo
    ...
    _openai_client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY)

Três defeitos no mesmo sítio:

1. lê **só** `EMERGENT_LLM_KEY` — a `OPENAI_API_KEY` nunca é consultada,
   logo o cliente nascia com `api_key=""`;
2. lê no **import**, não na chamada — uma variável definida depois não é
   vista, e o cliente fica em cache num global;
3. nunca passa `organization`, que contas corporativas exigem.

E havia DOIS guardas (`if not EMERGENT_LLM_KEY: return "não
configurado"`) que recusavam o trabalho antes de sequer tentar — com a
`OPENAI_API_KEY` definida e válida.

A ARMADILHA DO NOME
===================
Já existia o construtor certo, com o **mesmo nome**, no módulo vizinho:
`ai_document_analyzer.get_openai_client` — prioridade
`OPENAI_API_KEY` > `EMERGENT_LLM_KEY`, `base_url` para chaves
`sk-emerg`, e `organization`. Duas funções homónimas, uma correcta e uma
partida, e quem lê `get_openai_client()` não tem como saber qual é.
Hoje a ingénua **delega** na completa.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import ai_document as modulo


class TestAChaveEResolvidaNaChamada:
    def test_a_OPENAI_API_KEY_e_suficiente(self, monkeypatch):
        """O caso de produção: só esta variável definida."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-de-producao")
        monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
        assert modulo.chave_de_ia_configurada() is True

    def test_a_EMERGENT_LLM_KEY_continua_a_servir(self, monkeypatch):
        """Contraprova: não se parte quem usava a chave antiga."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-emerg-abc")
        assert modulo.chave_de_ia_configurada() is True

    def test_sem_nenhuma_das_duas_nao_esta_configurada(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
        assert modulo.chave_de_ia_configurada() is False

    def test_uma_variavel_VAZIA_conta_como_ausente(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
        assert modulo.chave_de_ia_configurada() is False

    def test_le_na_CHAMADA_e_nao_no_import(self, monkeypatch):
        """O defeito nº 2: uma constante de módulo congela o ambiente.

        Sem isto, definir a variável no Render e reiniciar o serviço não
        bastava se a ordem de import fosse outra — e, pior, o teste
        passava em dev porque lá a variável existe desde o arranque.
        """
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
        assert modulo.chave_de_ia_configurada() is False

        monkeypatch.setenv("OPENAI_API_KEY", "sk-definida-agora")
        assert modulo.chave_de_ia_configurada() is True


class TestOClienteDelegaNoConstrutorCompleto:
    def test_get_openai_client_usa_o_do_analyzer(self):
        """Uma quarta cópia do construtor seria a quarta a divergir."""
        marcador = object()
        with patch(
            "services.ai_document_analyzer.get_openai_client",
            return_value=marcador,
        ):
            modulo._openai_client = None
            assert modulo.get_openai_client() is marcador

    def test_levanta_quando_nao_ha_chave(self, monkeypatch):
        """O construtor completo devolve `None` sem chave.

        Devolver `None` daqui faria o chamador rebentar com
        `AttributeError` numa linha que não diz nada sobre configuração.
        """
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
        modulo._openai_client = None
        with pytest.raises(RuntimeError, match="(?i)chave"):
            modulo.get_openai_client()


class TestGuardaDeFonte:
    def _fonte(self, nome):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = Path(__file__).resolve().parents[2] / "services" / f"{nome}.py"
        texto = caminho.read_text(encoding="utf-8")
        return codigo_sem_comentarios(texto).replace('"', "").replace("'", "")

    def test_nenhuma_decisao_depende_da_constante_de_modulo(self):
        """Era `if not EMERGENT_LLM_KEY` em dois sítios — ambos recusavam
        o trabalho com a `OPENAI_API_KEY` definida."""
        fonte = self._fonte("ai_document")
        assert "if not EMERGENT_LLM_KEY" not in fonte

    def test_o_cliente_nao_e_construido_a_mao_aqui(self):
        fonte = self._fonte("ai_document")
        assert "AsyncOpenAI(api_key=" not in fonte

    def test_CONTRAPROVA_o_construtor_completo_le_as_duas_variaveis(self):
        """Sem isto, delegar para uma função igualmente partida passava."""
        fonte = self._fonte("ai_document_analyzer")
        assert "os.environ.get(OPENAI_API_KEY)" in fonte
        assert "EMERGENT_LLM_KEY" in fonte
        assert "organization" in fonte
