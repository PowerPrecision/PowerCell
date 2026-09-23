"""
Extracção de dados de documentos por visão — Épico 9, Eixo 4.

O QUE ESTÁ AQUI EM JOGO
-----------------------
Este caminho lê um NIF, um nome ou um vencimento de uma imagem e propõe
escrevê-los na ficha de um cliente. Duas coisas não podem falhar em
silêncio:

1. **O caminho vem do cliente.** Sem as duas guardas (raiz de documentos
   E prefixo do processo), um utilizador com acesso a um processo lê os
   documentos do vizinho — ou os backups, que vivem no mesmo bucket.
2. **Nenhum teste pode chamar uma API paga.** Há uma guarda explícita
   para isso no fim do ficheiro.

O modelo é o outro ponto sensível: estava fixo no código (`gpt-4o-mini`)
apesar de o painel de admin ter uma escolha por tarefa. Um modelo fixo
não se nota — apenas ignora o que o administrador configurou.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services import ai_document, document_vision_extract
from services.ai_document import (
    AI_MODEL,
    get_document_tool_definition,
    get_extraction_prompts,
    resolve_ai_model,
)
from services.document_vision_extract import (
    ERRO_CAMINHO_VAZIO,
    ERRO_FORMATO,
    EXTENSOES_SUPORTADAS,
    extensao_de,
    formato_suportado,
    mime_de,
    nome_de,
    run_extract_document_data,
)

PROCESSO = {
    "id": "proc-1",
    "client_name": "Maria Silva",
    "s3_folder": "Documentação Clientes/Maria Silva",
}
CAMINHO = "Documentação Clientes/Maria Silva/Identificação/cc.jpg"


# ====================================================================
# FORMATOS SUPORTADOS
# ====================================================================


class TestFormatoSuportado:
    @pytest.mark.parametrize("nome", ["a.pdf", "a.jpg", "a.JPEG", "a.png", "a.WEBP"])
    def test_aceita_imagens_e_pdf(self, nome):
        assert formato_suportado(nome) is True

    @pytest.mark.parametrize("nome", ["a.docx", "a.xlsx", "a.zip", "a.txt", "a.mp3"])
    def test_recusa_o_que_o_motor_de_visao_nao_le(self, nome):
        # Não é preciosismo: um .docx seguiria para uma chamada PAGA e
        # voltaria vazio.
        assert formato_suportado(nome) is False

    def test_ficheiro_sem_extensao_e_recusado(self):
        assert formato_suportado("Documentação Clientes/X/recibo") is False

    def test_extensao_do_caminho_completo_e_nao_da_pasta(self):
        # Uma pasta com ponto no nome não pode fazer passar o ficheiro.
        assert extensao_de("Clientes/pasta.pdf/ficheiro.docx") == "docx"

    def test_case_insensitive(self):
        assert extensao_de("A.PnG") == "png"

    def test_mime_deduzido_da_extensao(self):
        assert mime_de("x.pdf") == "application/pdf"
        assert mime_de("x.jpg") == "image/jpeg"
        assert mime_de("x.jpeg") == "image/jpeg"
        assert mime_de("x.png") == "image/png"
        assert mime_de("x.zip") == "application/octet-stream"

    def test_nome_isolado_do_caminho(self):
        assert nome_de("a/b/c/recibo de vencimento.pdf") == "recibo de vencimento.pdf"

    def test_todas_as_extensoes_suportadas_tem_mime(self):
        # Uma extensão aceite sem MIME chegaria ao motor como
        # application/octet-stream e voltaria vazia.
        for ext in EXTENSOES_SUPORTADAS:
            assert mime_de(f"x.{ext}") != "application/octet-stream"


# ====================================================================
# ESQUEMA DA CADERNETA PREDIAL (Eixo 2)
# ====================================================================


class TestEsquemaCadernetaPredial:
    def test_caderneta_tem_esquema_proprio(self):
        # Antes do Épico 9 caía no ramo genérico: a IA devolvia texto livre
        # e o mapeador não encontrava nada.
        tool = get_document_tool_definition("caderneta_predial")
        assert tool["function"]["name"] == "extract_caderneta_predial_data"

    def test_generico_continua_a_ser_o_ultimo_recurso(self):
        tool = get_document_tool_definition("tipo_que_nao_existe")
        assert tool["function"]["name"] == "extract_documento_data"

    def test_campos_casam_com_o_mapeador_da_ficha(self):
        # O ponto crítico: os nomes NÃO são livres. Têm de ser exactamente
        # os do field_mapping de build_update_data_from_extraction, senão a
        # extracção corre bem e a ficha fica vazia.
        propriedades = get_document_tool_definition("caderneta_predial")[
            "function"
        ]["parameters"]["properties"]
        for campo in (
            "artigo_matricial",
            "valor_patrimonial_tributario",
            "area_bruta",
            "localizacao",
            "tipologia",
        ):
            assert campo in propriedades, f"campo {campo} em falta no esquema"

    def test_vpt_e_area_sao_numeros(self):
        propriedades = get_document_tool_definition("caderneta_predial")[
            "function"
        ]["parameters"]["properties"]
        assert propriedades["valor_patrimonial_tributario"]["type"] == "number"
        assert propriedades["area_bruta"]["type"] == "number"

    def test_artigo_matricial_e_obrigatorio(self):
        parametros = get_document_tool_definition("caderneta_predial")["function"][
            "parameters"
        ]
        assert parametros["required"] == ["artigo_matricial"]

    def test_titulares_sao_uma_lista_de_objectos(self):
        titulares = get_document_tool_definition("caderneta_predial")["function"][
            "parameters"
        ]["properties"]["titulares"]
        assert titulares["type"] == "array"
        assert "nome" in titulares["items"]["properties"]

    def test_prompt_proprio_distingue_vpt_de_preco(self):
        sistema, _ = get_extraction_prompts("caderneta_predial")
        assert "VPT" in sistema
        # A confusão que o prompt existe para evitar.
        assert "preço de compra" in sistema

    def test_prompt_proibe_inventar(self):
        sistema, _ = get_extraction_prompts("caderneta_predial")
        assert "NUNCA inventes" in sistema


class TestMapeamentoDaCaderneta:
    def test_campos_extraidos_entram_em_real_estate_data(self):
        resultado = ai_document.build_update_data_from_extraction(
            {
                "artigo_matricial": "U-1234",
                "valor_patrimonial_tributario": 145000.0,
                "area_bruta": 92.5,
                "localizacao": "Rua das Flores 12",
                "tipologia": "T3",
            },
            "caderneta_predial",
            {},
        )
        imovel = resultado["real_estate_data"]
        assert imovel["artigo_matricial"] == "U-1234"
        assert imovel["valor_patrimonial"] == 145000.0
        assert imovel["area"] == 92.5
        assert imovel["tipologia"] == "T3"

    def test_campos_mapeados_nao_sao_repetidos_nas_observacoes(self):
        # O ramo da caderneta não marcava os campos como mapeados, pelo que
        # os mesmos cinco valores entravam na ficha E eram copiados outra
        # vez para `ai_extracted_notes`.
        resultado = ai_document.build_update_data_from_extraction(
            {"artigo_matricial": "U-1234", "tipologia": "T3"},
            "caderneta_predial",
            {},
        )
        notas = resultado.get("ai_extracted_notes", "")
        # Atenção ao formato: as notas escrevem o rótulo legível
        # ("Artigo Matricial"), não a chave crua. Procurar pela chave crua
        # faria este teste passar com o bug de volta.
        assert "Artigo Matricial" not in notas
        assert "Tipologia" not in notas

    def test_campo_desconhecido_continua_a_ir_para_as_observacoes(self):
        # A contraprova do teste anterior: o que NÃO é mapeado não pode
        # desaparecer em silêncio.
        resultado = ai_document.build_update_data_from_extraction(
            {"artigo_matricial": "U-1", "campo_exotico_da_at": "valor"},
            "caderneta_predial",
            {},
        )
        assert "Campo Exotico Da At" in resultado.get("ai_extracted_notes", "")


# ====================================================================
# MODELO VEM DO PAINEL DE ADMIN, NÃO DO CÓDIGO (Eixo 2)
# ====================================================================


class TestResolucaoDoModelo:
    @pytest.mark.asyncio
    async def test_usa_o_modelo_configurado_pelo_admin(self):
        with patch(
            "services.ai_document_analyzer.resolve_document_analysis_model",
            AsyncMock(return_value="gpt-4o"),
        ):
            assert await resolve_ai_model() == "gpt-4o"

    @pytest.mark.asyncio
    async def test_configuracao_inacessivel_cai_na_omissao(self):
        with patch(
            "services.ai_document_analyzer.resolve_document_analysis_model",
            AsyncMock(side_effect=RuntimeError("base de dados em baixo")),
        ):
            # Degradação graciosa: sem painel, analisa na mesma.
            assert await resolve_ai_model() == AI_MODEL

    @pytest.mark.asyncio
    async def test_modelo_vazio_cai_na_omissao(self):
        with patch(
            "services.ai_document_analyzer.resolve_document_analysis_model",
            AsyncMock(return_value="   "),
        ):
            assert await resolve_ai_model() == AI_MODEL

    @pytest.mark.asyncio
    async def test_a_chamada_a_openai_usa_o_modelo_resolvido(self):
        # A prova que interessa: não basta resolver, tem de CHEGAR à chamada.
        cliente = MagicMock()
        resposta = MagicMock()
        escolha = MagicMock()
        escolha.message.tool_calls = []
        escolha.message.content = '{"nif": "123456789"}'
        resposta.choices = [escolha]
        cliente.chat.completions.create = AsyncMock(return_value=resposta)

        with patch.object(ai_document, "get_openai_client", return_value=cliente), \
             patch.object(ai_document, "resolve_ai_model", AsyncMock(return_value="gpt-4o")):
            resultado = await ai_document.call_openai_api(messages=[])

        assert cliente.chat.completions.create.call_args.kwargs["model"] == "gpt-4o"
        assert resultado["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_modelo_explicito_nao_e_resolvido_outra_vez(self):
        cliente = MagicMock()
        resposta = MagicMock()
        escolha = MagicMock()
        escolha.message.tool_calls = []
        escolha.message.content = "{}"
        resposta.choices = [escolha]
        cliente.chat.completions.create = AsyncMock(return_value=resposta)
        resolutor = AsyncMock(return_value="nunca-usado")

        with patch.object(ai_document, "get_openai_client", return_value=cliente), \
             patch.object(ai_document, "resolve_ai_model", resolutor):
            await ai_document.call_openai_api(messages=[], model="gemini-2.0-flash")

        resolutor.assert_not_awaited()
        assert (
            cliente.chat.completions.create.call_args.kwargs["model"]
            == "gemini-2.0-flash"
        )

    def test_nenhuma_chamada_usa_a_constante_fixa(self):
        # Guarda de regressão sobre o código-fonte: se alguém voltar a pôr
        # `"model": AI_MODEL` numa chamada, o modelo do admin deixa outra
        # vez de contar — e nada mais falha.
        import inspect

        fonte = inspect.getsource(ai_document)
        assert '"model": AI_MODEL' not in fonte


# ====================================================================
# SEGURANÇA DO CAMINHO S3
# ====================================================================


def _mock_db(processo=PROCESSO):
    fake = MagicMock()
    fake.processes.find_one = AsyncMock(return_value=processo)
    return fake


class TestGuardasDeCaminho:
    @pytest.mark.asyncio
    async def test_caminho_vazio_e_recusado(self):
        with pytest.raises(HTTPException) as erro:
            await run_extract_document_data("proc-1", "   ", user={})
        assert erro.value.status_code == 400
        assert erro.value.detail == ERRO_CAMINHO_VAZIO

    @pytest.mark.asyncio
    async def test_formato_nao_suportado_e_recusado_antes_do_s3(self):
        s3 = MagicMock()
        with patch.object(document_vision_extract, "s3_service", s3):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data(
                    "proc-1",
                    "Documentação Clientes/Maria Silva/contrato.docx",
                    user={},
                )
        assert erro.value.status_code == 400
        assert erro.value.detail == ERRO_FORMATO
        # E o S3 nunca foi tocado: a recusa é barata.
        s3.s3_client.get_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_processo_inexistente_da_404(self):
        fake = MagicMock()
        fake.processes.find_one = AsyncMock(return_value=None)
        with patch.object(document_vision_extract, "db", fake):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data("proc-x", CAMINHO, user={})
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_caminho_fora_da_raiz_de_documentos_e_recusado(self):
        # O ataque que a primeira guarda existe para travar: backups e
        # logótipos vivem no MESMO bucket, sob outros prefixos.
        with patch.object(document_vision_extract, "db", _mock_db()):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data(
                    "proc-1", "backups/dump-2026.pdf", user={}
                )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_documento_de_outro_cliente_e_recusado(self):
        # A segunda guarda: dentro da raiz de documentos, mas no processo
        # do vizinho.
        with patch.object(document_vision_extract, "db", _mock_db()):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data(
                    "proc-1",
                    "Documentação Clientes/João Costa/Identificação/cc.jpg",
                    user={},
                )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_s3_nao_configurado_da_500_legivel(self):
        s3 = MagicMock()
        s3.is_configured.return_value = False
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", s3):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data("proc-1", CAMINHO, user={})
        assert erro.value.status_code == 500


# ====================================================================
# O CAMINHO FELIZ (com motor simulado)
# ====================================================================


class FakeVLMService:
    """Motor de visão simulado. NUNCA faz rede.

    Devolve o contrato de `run_analysis_on_documents` para dois tipos de
    documento, que é o que o diálogo de revisão consome.
    """

    CC = {
        "success": True,
        "extracted_data": {"nif": "123456789", "nome": "Maria Silva"},
        "field_confidence": {"nif": 0.97, "nome": 0.93},
        "conflicts": [],
        "documents": [{"file_name": "cc.jpg", "type": "cc", "confidence": 0.97}],
        "titular_matches": [],
        "needs_titular_choice": False,
    }

    IRS = {
        "success": True,
        "extracted_data": {"rendimento_anual": 28400.0, "employer_name": "ACME Lda"},
        "field_confidence": {"rendimento_anual": 0.88},
        "conflicts": [
            {
                "field": "rendimento_anual",
                "existing_value": 25000.0,
                "new_value": 28400.0,
                "source": "irs.pdf",
                "type": "override",
            }
        ],
        "documents": [{"file_name": "irs.pdf", "type": "irs", "confidence": 0.9}],
        "titular_matches": [],
        "needs_titular_choice": False,
    }

    def __init__(self, payload):
        self.payload = payload
        self.chamadas = []

    async def __call__(self, process_id, documents, *, user, skip_analyzed=True):
        self.chamadas.append(
            {
                "process_id": process_id,
                "documents": documents,
                "skip_analyzed": skip_analyzed,
            }
        )
        return dict(self.payload)


def _s3_com(conteudo=b"%PDF-1.4 conteudo"):
    s3 = MagicMock()
    s3.is_configured.return_value = True
    corpo = MagicMock()
    corpo.read.return_value = conteudo
    s3.s3_client.get_object.return_value = {"Body": corpo}
    return s3


class TestExtraccaoComMotorSimulado:
    @pytest.mark.asyncio
    async def test_devolve_dados_do_cc_e_o_ficheiro_de_origem(self):
        motor = FakeVLMService(FakeVLMService.CC)
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", _s3_com()), \
             patch.object(document_vision_extract, "run_analysis_on_documents", motor):
            resultado = await run_extract_document_data("proc-1", CAMINHO, user={})

        assert resultado["extracted_data"]["nif"] == "123456789"
        # O diálogo precisa de dizer DE QUE ficheiro vieram os dados.
        assert resultado["source_document"]["name"] == "cc.jpg"
        assert resultado["source_document"]["mime_type"] == "image/jpeg"
        assert resultado["source_document"]["size"] > 0

    @pytest.mark.asyncio
    async def test_conflitos_do_irs_chegam_intactos(self):
        motor = FakeVLMService(FakeVLMService.IRS)
        caminho = "Documentação Clientes/Maria Silva/Financeiros/irs.pdf"
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", _s3_com()), \
             patch.object(document_vision_extract, "run_analysis_on_documents", motor):
            resultado = await run_extract_document_data("proc-1", caminho, user={})

        assert len(resultado["conflicts"]) == 1
        assert resultado["conflicts"][0]["field"] == "rendimento_anual"
        assert resultado["source_document"]["mime_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_nao_salta_documentos_ja_analisados(self):
        # O consultor carregou no botão DESTE ficheiro. Responder "já foi
        # analisado" e mais nada seria incompreensível.
        motor = FakeVLMService(FakeVLMService.CC)
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", _s3_com()), \
             patch.object(document_vision_extract, "run_analysis_on_documents", motor):
            await run_extract_document_data("proc-1", CAMINHO, user={})

        assert motor.chamadas[0]["skip_analyzed"] is False

    @pytest.mark.asyncio
    async def test_um_unico_documento_e_enviado_ao_motor(self):
        motor = FakeVLMService(FakeVLMService.CC)
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", _s3_com()), \
             patch.object(document_vision_extract, "run_analysis_on_documents", motor):
            await run_extract_document_data("proc-1", CAMINHO, user={})

        documentos = motor.chamadas[0]["documents"]
        assert len(documentos) == 1
        assert documentos[0]["source_path"] == CAMINHO
        assert documentos[0]["content"] == b"%PDF-1.4 conteudo"

    @pytest.mark.asyncio
    async def test_ficheiro_vazio_no_s3_da_erro_legivel(self):
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", _s3_com(b"")), \
             patch.object(
                 document_vision_extract,
                 "run_analysis_on_documents",
                 FakeVLMService(FakeVLMService.CC),
             ):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data("proc-1", CAMINHO, user={})
        assert erro.value.status_code == 400

    @pytest.mark.asyncio
    async def test_ficheiro_grande_demais_e_recusado_antes_do_motor(self):
        grande = b"x" * (document_vision_extract.MAX_TAMANHO_BYTES + 1)
        motor = FakeVLMService(FakeVLMService.CC)
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", _s3_com(grande)), \
             patch.object(document_vision_extract, "run_analysis_on_documents", motor):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data("proc-1", CAMINHO, user={})
        assert erro.value.status_code == 400
        # Uma chamada paga sobre 20 MB que o motor ia recusar na mesma.
        assert motor.chamadas == []

    @pytest.mark.asyncio
    async def test_ficheiro_inexistente_no_s3_da_404(self):
        from botocore.exceptions import ClientError

        s3 = MagicMock()
        s3.is_configured.return_value = True
        s3.s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", s3):
            with pytest.raises(HTTPException) as erro:
                await run_extract_document_data("proc-1", CAMINHO, user={})
        assert erro.value.status_code == 404


# ====================================================================
# GUARDA: NENHUM TESTE PODE CHAMAR UMA API PAGA
# ====================================================================


class TestNenhumaChamadaReal:
    @pytest.mark.asyncio
    async def test_o_cliente_openai_nunca_e_construido_no_caminho_feliz(self):
        # Se alguém trocar o motor simulado por uma chamada a sério, este
        # teste passa a gastar dinheiro — e a falhar.
        construtor = MagicMock(side_effect=AssertionError("chamada real à OpenAI"))
        with patch.object(document_vision_extract, "db", _mock_db()), \
             patch.object(document_vision_extract, "s3_service", _s3_com()), \
             patch.object(
                 document_vision_extract,
                 "run_analysis_on_documents",
                 FakeVLMService(FakeVLMService.CC),
             ), \
             patch.object(ai_document, "get_openai_client", construtor):
            await run_extract_document_data("proc-1", CAMINHO, user={})

        construtor.assert_not_called()
