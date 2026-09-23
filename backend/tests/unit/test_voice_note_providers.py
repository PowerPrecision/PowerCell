"""
Escolha de motor (ASR/LLM) das notas de voz — Épico 7, Eixo 4.

O QUE ESTÁ AQUI EM JOGO:
    O ambiente local/dev opera com dados simulados. Uma regressão nesta
    decisão não parte nenhum ecrã — apenas passa a enviar a voz gravada
    sobre um cliente real para uma API externa a partir do portátil de um
    programador, e a facturar por isso. Por ser invisível, tem de estar
    coberta por testes explícitos.

REGRA PROVADA AQUI:
    sem `VOICE_ASR_PROVIDER`, só produção COM chave usa o motor real.
    Tudo o resto simula. Falha fechada.
"""
from unittest.mock import MagicMock, patch

import pytest

from services import voice_extraction, voice_transcription
from services.voice_transcription import (
    ErroDeTranscricao,
    PROVIDER_MOCK,
    PROVIDER_OPENAI,
    TIMEOUT_ASR_OMISSAO,
    extensao_para_mime,
    formato_suportado,
    nome_para_provider,
    resolver_modelo,
    resolver_provider,
    resolver_timeout,
    transcrever_audio,
)

CHAVE = {"EMERGENT_LLM_KEY": "sk-uma-chave-qualquer"}


# ====================================================================
# ESCOLHA DO MOTOR DE TRANSCRIÇÃO
# ====================================================================


class TestResolverProviderASR:
    def test_dev_sem_variavel_simula(self):
        assert resolver_provider({"ENVIRONMENT": "dev"}) == PROVIDER_MOCK

    def test_dev_com_chave_continua_a_simular(self):
        # O caso que interessa: ter chave no `.env` local não é autorização
        # para a usar. Só o ambiente de produção o é.
        assert resolver_provider({"ENVIRONMENT": "dev", **CHAVE}) == PROVIDER_MOCK

    def test_ambiente_vazio_simula(self):
        # CI corre sem ENVIRONMENT definido: tem de cair no simulado.
        assert resolver_provider({}) == PROVIDER_MOCK

    def test_producao_sem_chave_simula(self):
        # Sem chave a chamada falharia de qualquer forma; simular dá um erro
        # legível em vez de um 401 da OpenAI.
        assert resolver_provider({"ENVIRONMENT": "production"}) == PROVIDER_MOCK

    @pytest.mark.parametrize("chave", ["EMERGENT_LLM_KEY", "OPENAI_API_KEY"])
    def test_producao_com_chave_usa_o_motor_real(self, chave):
        ambiente = {"ENVIRONMENT": "production", chave: "sk-x"}

        assert resolver_provider(ambiente) == PROVIDER_OPENAI

    def test_app_env_tambem_conta_como_producao(self):
        assert resolver_provider({"APP_ENV": "prod", **CHAVE}) == PROVIDER_OPENAI

    def test_chave_apenas_com_espacos_nao_conta(self):
        ambiente = {"ENVIRONMENT": "production", "EMERGENT_LLM_KEY": "   "}

        assert resolver_provider(ambiente) == PROVIDER_MOCK

    def test_variavel_explicita_forca_o_motor_real_em_dev(self):
        ambiente = {"ENVIRONMENT": "dev", "VOICE_ASR_PROVIDER": "openai"}

        assert resolver_provider(ambiente) == PROVIDER_OPENAI

    def test_variavel_explicita_forca_simulacao_em_producao(self):
        ambiente = {"ENVIRONMENT": "production", "VOICE_ASR_PROVIDER": "mock", **CHAVE}

        assert resolver_provider(ambiente) == PROVIDER_MOCK

    def test_valor_desconhecido_cai_no_simulado(self):
        # Um typo no `.env` não pode abrir a porta ao motor real.
        ambiente = {"ENVIRONMENT": "production", "VOICE_ASR_PROVIDER": "whisperr", **CHAVE}

        assert resolver_provider(ambiente) == PROVIDER_MOCK


class TestResolverProviderLLM:
    def test_sem_variavel_segue_o_asr(self):
        # Ou é tudo simulado ou é tudo verdadeiro: um passo de cada lado
        # produziria resumos reais a partir de transcrições inventadas.
        ambiente = {"ENVIRONMENT": "production", **CHAVE}

        assert voice_extraction.resolver_provider(ambiente) == PROVIDER_OPENAI
        assert voice_extraction.resolver_provider({"ENVIRONMENT": "dev"}) == PROVIDER_MOCK

    def test_variavel_propria_tem_precedencia(self):
        ambiente = {"ENVIRONMENT": "production", "VOICE_LLM_PROVIDER": "mock", **CHAVE}

        assert voice_extraction.resolver_provider(ambiente) == PROVIDER_MOCK

    def test_valor_desconhecido_cai_no_simulado(self):
        ambiente = {"ENVIRONMENT": "production", "VOICE_LLM_PROVIDER": "gpt5000", **CHAVE}

        assert voice_extraction.resolver_provider(ambiente) == PROVIDER_MOCK


# ====================================================================
# MODELO E TIMEOUT
# ====================================================================


class TestModeloETimeout:
    def test_modelo_por_omissao(self):
        assert resolver_modelo({}) == "whisper-1"

    def test_modelo_configuravel(self):
        assert resolver_modelo({"VOICE_ASR_MODEL": "whisper-large-v3"}) == "whisper-large-v3"

    def test_timeout_por_omissao(self):
        assert resolver_timeout({}) == TIMEOUT_ASR_OMISSAO

    def test_timeout_configuravel(self):
        assert resolver_timeout({"VOICE_ASR_TIMEOUT": "45"}) == 45.0

    @pytest.mark.parametrize("valor", ["0", "-5", "muito", ""])
    def test_timeout_invalido_cai_no_omissao_nunca_desliga(self, valor):
        # Desligar o timeout deixaria uma tarefa presa para sempre a segurar
        # o estado "a processar" no ecrã do consultor.
        assert resolver_timeout({"VOICE_ASR_TIMEOUT": valor}) == TIMEOUT_ASR_OMISSAO

    def test_timeout_do_llm_tem_a_sua_propria_variavel(self):
        assert voice_extraction.resolver_timeout({"VOICE_LLM_TIMEOUT": "30"}) == 30.0


# ====================================================================
# FORMATOS DE ÁUDIO
# ====================================================================


class TestFormatosDeAudio:
    @pytest.mark.parametrize(
        "mime", ["audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav"]
    )
    def test_formatos_do_browser_e_do_telemovel(self, mime):
        assert formato_suportado(mime)

    def test_codecs_anexados_pelo_mediarecorder_nao_estragam(self):
        # O browser devolve "audio/webm;codecs=opus".
        assert formato_suportado("audio/webm;codecs=opus")
        assert extensao_para_mime("audio/webm;codecs=opus") == ".webm"

    @pytest.mark.parametrize("mime", ["video/mp4", "application/pdf", "", "texto"])
    def test_formatos_recusados(self, mime):
        assert not formato_suportado(mime)

    def test_blob_sem_nome_recebe_extensao_do_mime(self):
        # Sem extensão no nome, o Whisper recusa com "Invalid file format".
        assert nome_para_provider("blob", "audio/webm") == "blob.webm"

    def test_nome_vazio_recebe_nome_util(self):
        assert nome_para_provider("", "audio/mpeg") == "nota-de-voz.mp3"

    def test_nome_ja_correcto_fica_como_esta(self):
        assert nome_para_provider("reuniao.mp3", "audio/mpeg") == "reuniao.mp3"

    def test_extensao_errada_e_corrigida_pelo_mime(self):
        assert nome_para_provider("reuniao.txt", "audio/wav") == "reuniao.wav"


# ====================================================================
# GARANTIA DE QUE O MODO SIMULADO NÃO TOCA NA REDE
# ====================================================================


class TestModoSimuladoNaoChamaRede:
    @pytest.mark.asyncio
    async def test_transcricao_simulada_nao_constroi_o_cliente_openai(self):
        # A prova é pela negativa: o construtor do cliente rebenta se for
        # tocado. Se um dia alguém puxar a criação do cliente para fora do
        # ramo `openai`, este teste fica vermelho.
        explode = MagicMock(side_effect=AssertionError("cliente OpenAI construído em modo simulado"))

        with patch.object(voice_transcription, "resolver_provider", return_value=PROVIDER_MOCK), \
                patch("services.ai_document.get_openai_client", explode):
            resultado = await transcrever_audio(b"audio-falso", mime_type="audio/webm")

        assert resultado.provider == PROVIDER_MOCK
        assert resultado.texto
        explode.assert_not_called()

    @pytest.mark.asyncio
    async def test_extraccao_simulada_nao_constroi_o_cliente_openai(self):
        explode = MagicMock(side_effect=AssertionError("cliente OpenAI construído em modo simulado"))

        with patch.object(voice_extraction, "resolver_provider", return_value=PROVIDER_MOCK), \
                patch("services.ai_document.get_openai_client", explode):
            resultado = await voice_extraction.extrair_accoes("Tenho de ligar ao banco amanhã.")

        assert resultado["provider"] == PROVIDER_MOCK
        explode.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_heuristica_simulada_produz_mesmo_tarefas(self):
        # Se o modo simulado devolvesse sempre zero tarefas, o fluxo de dev
        # nunca exercitaria a criação de tarefas — e o Eixo 3 ficaria por
        # testar à mão até chegar a produção.
        with patch.object(voice_extraction, "resolver_provider", return_value=PROVIDER_MOCK):
            resultado = await voice_extraction.extrair_accoes(
                "A reunião correu bem. Tenho de pedir os recibos amanhã. "
                "É preciso confirmar a escritura."
            )

        assert resultado["resumo_timeline"]
        assert len(resultado["tarefas_extraidas"]) >= 2

    @pytest.mark.asyncio
    async def test_audio_vazio_falha_tambem_em_modo_simulado(self):
        # Um upload truncado tem de falhar em dev exactamente como falharia
        # em produção — senão o bug só aparece no cliente.
        with patch.object(voice_transcription, "resolver_provider", return_value=PROVIDER_MOCK):
            with pytest.raises(ErroDeTranscricao):
                await transcrever_audio(b"", mime_type="audio/webm")

    @pytest.mark.asyncio
    async def test_transcricao_vazia_nao_chega_ao_extractor(self):
        with pytest.raises(voice_extraction.ErroDeExtraccao):
            await voice_extraction.extrair_accoes("   ")
