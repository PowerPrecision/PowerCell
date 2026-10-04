"""O scraper tem de chamar o modelo que o administrador configurou (D-22).

O QUE CORREU MAL
================
`_extract_with_gemini` fazia três coisas, por esta ordem:

1. lia o modelo configurado em `SystemConfig` (`scraping_model`);
2. **escrevia-o no log** — «Usando modelo configurado: X»;
3. chamava `genai.GenerativeModel("gemini-2.0-flash")`, literal.

Só os modelos `gpt*` eram honrados, porque esses desviam para o
`_extract_with_openai`. Um administrador que escolhesse outro modelo
Gemini via no log que ele estava em uso e recebia 2.0-flash — e o
`ai_usage_tracker` recebia o mesmo literal, pelo que o **relatório de
custos atribuía a despesa ao modelo errado**.

**O log a dizer o contrário é o que tornava isto difícil de ver.** É o
defeito que a regra «Modelo de IA: nunca fixo no código» descreve e que
`test_nenhuma_chamada_usa_a_constante_fixa` impede no `ai_document` —
num módulo que essa guarda não cobria.

PORQUE É QUE O TESTE É AO NÍVEL DA CHAMADA
==========================================
A asserção é sobre o PARÂMETRO que sai para o SDK, não sobre o resultado:
é a regra do «duplo demasiado esperto» (Set 2026). Um falso que
reimplemente a escolha do modelo esconderia exactamente a única coisa que
esta correcção faz.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from services import scraper as modulo_do_scraper
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

MODELO_ESCOLHIDO = "gemini-2.5-pro"
LITERAL_ANTIGO = "gemini-2.0-flash"

RESPOSTA = {
    "titulo": "T2 em Leiria",
    "preco": 185000,
    "localizacao": "Leiria",
    "tipologia": "T2",
    "area": 95,
    "estado": "usado",
}


class _Resposta:
    def __init__(self, texto):
        self.text = texto


class _ModeloFalso:
    """Registra o modelo e a configuração com que foi construído."""

    construcoes: list = []

    def __init__(self, nome, generation_config=None, **kw):
        type(self).construcoes.append((nome, generation_config))

    def generate_content(self, prompt):
        return _Resposta(json.dumps(RESPOSTA))


@pytest.fixture
def genai_falso(monkeypatch):
    """Um `google.generativeai` ao nível da CHAMADA.

    Não substitui o módulo sob teste (regra do `sys.modules` envenenado) —
    substitui o SDK de terceiros, e o `monkeypatch.setitem` repõe-o no
    fim da função de teste.
    """
    _ModeloFalso.construcoes = []
    falso = types.ModuleType("google.generativeai")
    falso.configure = lambda **kw: None
    falso.GenerativeModel = _ModeloFalso
    monkeypatch.setitem(sys.modules, "google.generativeai", falso)
    monkeypatch.setattr(modulo_do_scraper, "GEMINI_API_KEY", "chave-de-teste")
    return _ModeloFalso


@pytest.fixture
def usos_registados(monkeypatch):
    """Captura o que vai para o `ai_usage_tracker`."""
    from services import ai_usage_tracker as modulo

    registos: list[dict] = []

    async def _log(**kw):
        registos.append(kw)

    monkeypatch.setattr(modulo.ai_usage_tracker, "log_usage", _log)
    return registos


async def _extrair(scraper, modelo: str):
    async def _configurado():
        return modelo

    scraper._get_ai_model_for_scraping = _configurado
    return await scraper._extract_with_gemini("<html>casa</html>", "https://x.pt/1")


class TestOModeloQueSAI:
    @pytest.mark.asyncio
    async def test_o_modelo_configurado_chega_ao_SDK(
        self, genai_falso, usos_registados
    ):
        scraper = modulo_do_scraper.PropertyScraper()
        dados = await _extrair(scraper, MODELO_ESCOLHIDO)

        assert genai_falso.construcoes, "o SDK nem foi chamado"
        nome, config = genai_falso.construcoes[0]
        assert nome == MODELO_ESCOLHIDO
        # O modo JSON nativo não se pode perder ao trocar o modelo: sem
        # ele a resposta volta com ```json e o `json.loads` rebenta.
        assert config == {"response_mime_type": "application/json"}
        assert dados.get("titulo") == "T2 em Leiria"

    @pytest.mark.asyncio
    async def test_o_relatorio_de_custos_leva_o_modelo_REAL(
        self, genai_falso, usos_registados
    ):
        """O tracker recebia o literal: a despesa de um modelo caro ficava
        imputada ao barato, e o painel de custos mentia."""
        scraper = modulo_do_scraper.PropertyScraper()
        await _extrair(scraper, MODELO_ESCOLHIDO)

        assert usos_registados, "nenhum uso registado"
        assert usos_registados[0]["model"] == MODELO_ESCOLHIDO
        assert usos_registados[0]["provider"] == "gemini"

    @pytest.mark.asyncio
    async def test_a_resposta_diz_que_modelo_a_extraiu(
        self, genai_falso, usos_registados
    ):
        """`_extracted_by` é o que o `property_scraper` propaga para o
        `raw_data` e o que um operador lê para saber quem extraiu."""
        scraper = modulo_do_scraper.PropertyScraper()
        dados = await _extrair(scraper, MODELO_ESCOLHIDO)
        assert dados["_extracted_by"] == MODELO_ESCOLHIDO

    @pytest.mark.asyncio
    async def test_a_OMISSAO_continua_a_ser_o_2_0_flash(
        self, genai_falso, usos_registados
    ):
        """Contraprova: uma correcção que passasse a exigir configuração
        deixava o scraper sem modelo nenhum quando nada está configurado.
        A omissão vive no resolvedor, não na chamada.
        """
        scraper = modulo_do_scraper.PropertyScraper()
        await _extrair(scraper, LITERAL_ANTIGO)
        assert genai_falso.construcoes[0][0] == LITERAL_ANTIGO

    @pytest.mark.asyncio
    async def test_um_modelo_gpt_continua_a_desviar_para_o_OpenAI(
        self, genai_falso, usos_registados
    ):
        """A metade que já funcionava não se parte: era por aqui que o
        administrador conseguia mudar de modelo, e foi ela que escondeu a
        outra."""
        scraper = modulo_do_scraper.PropertyScraper()
        chamadas: list = []

        async def _openai(html, url, model):
            chamadas.append(model)
            return {"titulo": "via openai"}

        scraper._extract_with_openai = _openai
        dados = await _extrair(scraper, "gpt-4o-mini")

        assert chamadas == ["gpt-4o-mini"]
        assert dados == {"titulo": "via openai"}
        assert not genai_falso.construcoes, "não devia ter tocado no Gemini"


class TestAGuardaSobreAFonte:
    """O literal não pode voltar — e a contraprova de que a guarda lê mesmo."""

    def _codigo(self):
        return codigo_da_funcao_sem_comentarios(
            modulo_do_scraper.PropertyScraper._extract_with_gemini
        )

    def test_a_extraccao_nao_tem_o_modelo_escrito_a_letra(self):
        codigo = self._codigo()
        assert LITERAL_ANTIGO not in codigo, (
            "O modelo voltou a ser literal dentro de `_extract_with_gemini`. "
            "A omissão vive no `_get_ai_model_for_scraping`, não aqui."
        )

    def test_a_extraccao_USA_o_modelo_resolvido(self):
        """Sem esta contraprova, apagar a resolução satisfazia a guarda."""
        codigo = self._codigo()
        assert "_get_ai_model_for_scraping" in codigo
        assert codigo.count("configured_model") >= 5

    def test_o_resolvedor_e_que_tem_a_omissao(self):
        """A omissão continua a existir, e é lá que se lê."""
        codigo = codigo_da_funcao_sem_comentarios(
            modulo_do_scraper.PropertyScraper._get_ai_model_for_scraping
        )
        assert LITERAL_ANTIGO in codigo
