"""
Bateria e2e — Visão computacional: ficheiro no S3 → IA → revisão. Épico 9.

Exercita a cadeia COMPLETA num único fluxo por teste:

    POST /processes/{id}/documents/extract (caminho S3)
        → guardas de âmbito (raiz de documentos + prefixo do processo)
        → leitura do ficheiro no S3
        → motor de visão (SIMULADO — nenhuma API paga é contactada)
        → comparação com a ficha do processo
        → separação em conflitos vs. campos a preencher
        → resposta com o contrato que o diálogo de revisão consome

O QUE É REAL E O QUE É FALSO
----------------------------
Falso: só o S3 e a chamada ao modelo (`analyze_document_with_ai`). Tudo o
que está entre os dois — as guardas, a comparação com a ficha, o cálculo
de conflitos e o formato da resposta — é o código de produção. É aí que
estão os erros que um teste de unidade não apanha.

A REGRA DE OURO
---------------
A extracção é de LEITURA. Há um teste explícito a provar que este caminho
não escreve nada na ficha do processo: quem escreve é
`/documents/ai-apply-suggestions`, depois de o consultor confirmar.

CAMINHOS COBERTOS
  1. CC — a ficha está vazia: tudo entra como campo a preencher.
  2. Recibo de vencimento — a ficha já tem rendimento: nasce um conflito.
  3. Caderneta predial — o esquema novo do Eixo 2, ponta a ponta.
  4. Documento ilegível — resposta honesta, sem inventar dados.
  5. S3 em baixo / ficheiro inexistente — erro legível, não 500 opaco.
  6. Guardas de âmbito — backup e processo do vizinho.
  7. Nada é escrito na base de dados.

SEM MONGO E SEM REDE: usa a `FakeAsyncDatabase` de `tests/unit/conftest.py`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from services import ai_document_analyzer, document_ai_analyze, document_vision_extract
from services.document_vision_extract import run_extract_document_data
from tests.unit.conftest import FakeAsyncDatabase

pytestmark = pytest.mark.integration


PASTA = "Documentação Clientes/Ana Martins"
UTILIZADOR = {"id": "u-1", "name": "Carla Gestora", "role": "diretor"}


# ====================================================================
# MOTOR DE VISÃO SIMULADO
# ====================================================================


class FakeVLMService:
    """Substitui a chamada paga ao modelo de visão.

    Devolve o contrato de `analyze_document_with_ai`, pelo que toda a
    cadeia a jusante (comparação, conflitos, formato da resposta) corre a
    sério.
    """

    CC = {
        "success": True,
        "tipo_documento": "cc",
        "confianca": 0.96,
        "dados_extraidos": {
            "nome_completo": "Ana Martins",
            "nif": "234567891",
            "numero_documento": "12345678 9 ZZ1",
            "data_nascimento": "1988-04-12",
        },
        "confianca_campos": {"nif": 0.98, "nome_completo": 0.95},
        "observacoes": "",
    }

    RECIBO = {
        "success": True,
        "tipo_documento": "recibo_vencimento",
        "confianca": 0.91,
        "dados_extraidos": {
            "salario_liquido": 1480.0,
            "entidade_empregadora": "ACME Lda",
        },
        "confianca_campos": {"salario_liquido": 0.92},
        "observacoes": "",
    }

    CADERNETA = {
        "success": True,
        "tipo_documento": "caderneta_predial",
        "confianca": 0.89,
        "dados_extraidos": {
            "artigo_matricial": "U-1234",
            "valor_patrimonial_tributario": 145000.0,
            "area_bruta": 92.5,
            "tipologia": "T3",
            "localizacao": "Rua das Flores 12, Porto",
        },
        "confianca_campos": {"artigo_matricial": 0.94},
        "observacoes": "",
    }

    ILEGIVEL = {
        "success": False,
        "error": "Não foi possível ler o documento",
        "dados_extraidos": {},
    }

    def __init__(self, resposta):
        self.resposta = resposta
        self.chamadas = []

    async def __call__(self, file_content, file_name, mime_type):
        self.chamadas.append(
            {"name": file_name, "mime_type": mime_type, "bytes": len(file_content)}
        )
        # A função real acrescenta `file_name` ao resultado e a cadeia a
        # jusante conta com isso para casar o tipo detectado com o caminho
        # S3 do ficheiro. Um duplo que o omita mente.
        return {**self.resposta, "file_name": file_name}


def _processo(**extra):
    base = {
        "id": "proc-1",
        "client_name": "Ana Martins",
        "s3_folder": PASTA,
        "personal_data": {},
        "financial_data": {},
        "real_estate_data": {},
    }
    base.update(extra)
    return base


def _s3(conteudo=b"%PDF-1.4 fingido", falha=None):
    servico = MagicMock()
    servico.is_configured.return_value = True
    if falha is not None:
        servico.s3_client.get_object.side_effect = falha
    else:
        corpo = MagicMock()
        corpo.read.return_value = conteudo
        servico.s3_client.get_object.return_value = {"Body": corpo}
    return servico


class Cenario:
    """Monta a cadeia com o S3 e o modelo falseados, e nada mais."""

    def __init__(self, resposta_vlm, processo=None, s3=None):
        self.motor = FakeVLMService(resposta_vlm)
        self.db = FakeAsyncDatabase()
        self.processo = processo or _processo()
        self.s3 = s3 or _s3()
        self._patches = []

    async def __aenter__(self):
        await self.db.processes.insert_one(dict(self.processo))
        self._patches = [
            patch.object(document_vision_extract, "db", self.db),
            patch.object(document_ai_analyze, "db", self.db),
            patch.object(document_vision_extract, "s3_service", self.s3),
            patch.object(
                ai_document_analyzer, "analyze_document_with_ai", self.motor
            ),
            # O log de importação é acessório e toca na BD: não faz parte
            # do que este ficheiro prova.
            patch(
                "routes.ai_import_logs.create_ai_import_log",
                AsyncMock(return_value=None),
            ),
            patch(
                "routes.ai_import_logs.finalize_ai_import_log", AsyncMock()
            ),
            patch("routes.ai_import_logs.update_ai_import_log", AsyncMock()),
        ]
        for p in self._patches:
            p.start()
        return self

    async def __aexit__(self, *_):
        for p in reversed(self._patches):
            p.stop()
        return False

    async def extrair(self, caminho):
        return await run_extract_document_data(
            self.processo["id"], caminho, user=UTILIZADOR
        )


# ====================================================================
# 1. CARTÃO DE CIDADÃO — FICHA VAZIA
# ====================================================================


class TestCartaoDeCidadao:
    @pytest.mark.asyncio
    async def test_dados_do_cc_chegam_ao_dialogo_de_revisao(self):
        async with Cenario(FakeVLMService.CC) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")

        extraidos = resultado["extracted_data"]
        assert extraidos["nif"] == "234567891"
        # `client_name` já está na ficha e é igual: entra em `matching` e
        # não em `empty_fields`, logo não é sugestão. Só o que a ficha NÃO
        # tem é que chega aqui.
        assert extraidos["documento_id"] == "12345678 9 ZZ1"

    @pytest.mark.asyncio
    async def test_ficha_vazia_nao_gera_conflitos(self):
        # Sem valor anterior não há nada a decidir — mas tudo vai ser
        # gravado na mesma. É por isso que o diálogo mostra os dois grupos.
        async with Cenario(FakeVLMService.CC) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")

        assert resultado["conflicts"] == []
        assert len(resultado["extracted_data"]) > 0

    @pytest.mark.asyncio
    async def test_o_motor_recebe_a_imagem_com_o_mime_certo(self):
        async with Cenario(FakeVLMService.CC) as cenario:
            await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")
            chamada = cenario.motor.chamadas[0]

        assert chamada["mime_type"] == "image/jpeg"
        assert chamada["name"] == "cc.jpg"
        assert chamada["bytes"] > 0

    @pytest.mark.asyncio
    async def test_a_resposta_diz_de_que_ficheiro_veio(self):
        async with Cenario(FakeVLMService.CC) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")

        assert resultado["source_document"]["name"] == "cc.jpg"
        assert resultado["source_document"]["s3_path"].endswith("cc.jpg")

    @pytest.mark.asyncio
    async def test_a_confianca_por_campo_e_transportada(self):
        # É o que alimenta o aviso de baixa confiança no frontend.
        async with Cenario(FakeVLMService.CC) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")

        assert resultado["field_confidence"]


# ====================================================================
# 2. RECIBO DE VENCIMENTO — FICHA JÁ PREENCHIDA
# ====================================================================


class TestReciboComConflito:
    @pytest.mark.asyncio
    async def test_valor_diferente_do_da_ficha_nasce_como_conflito(self):
        processo = _processo(financial_data={"monthly_income": 1200.0})
        async with Cenario(FakeVLMService.RECIBO, processo=processo) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Financeiros/recibo.pdf")

        conflitos = {c["field"]: c for c in resultado["conflicts"]}
        assert "monthly_income" in conflitos, resultado["conflicts"]
        assert conflitos["monthly_income"]["new_value"] == 1480.0

    @pytest.mark.asyncio
    async def test_o_conflito_leva_o_valor_actual_para_comparacao(self):
        # Sem o valor existente o consultor não consegue escolher.
        processo = _processo(financial_data={"monthly_income": 1200.0})
        async with Cenario(FakeVLMService.RECIBO, processo=processo) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Financeiros/recibo.pdf")

        conflito = next(
            c for c in resultado["conflicts"] if c["field"] == "monthly_income"
        )
        assert str(conflito["existing_value"]) == "1200.0"

    @pytest.mark.asyncio
    async def test_pdf_segue_com_o_mime_de_pdf(self):
        async with Cenario(FakeVLMService.RECIBO) as cenario:
            await cenario.extrair(f"{PASTA}/Financeiros/recibo.pdf")

        assert cenario.motor.chamadas[0]["mime_type"] == "application/pdf"


# ====================================================================
# 3. CADERNETA PREDIAL — O ESQUEMA NOVO DO EIXO 2
# ====================================================================


class TestCadernetaPredial:
    @pytest.mark.asyncio
    async def test_a_caderneta_atravessa_a_cadeia_toda(self):
        async with Cenario(FakeVLMService.CADERNETA) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Imóvel/caderneta.pdf")

        # Antes do Épico 9 a caderneta caía no esquema genérico e nada
        # disto chegava ao fim da cadeia.
        assert resultado["extracted_data"], resultado
        assert resultado["documents"][0]["type"] == "caderneta_predial"

    @pytest.mark.asyncio
    async def test_o_tipo_detectado_acompanha_o_caminho_s3(self):
        # É por este par (tipo + caminho) que a organização em pastas sabe
        # para onde mover o ficheiro.
        caminho = f"{PASTA}/Imóvel/caderneta.pdf"
        async with Cenario(FakeVLMService.CADERNETA) as cenario:
            resultado = await cenario.extrair(caminho)

        assert resultado["documents"][0]["source_path"] == caminho


# ====================================================================
# 4. DOCUMENTO ILEGÍVEL
# ====================================================================


class TestDocumentoIlegivel:
    @pytest.mark.asyncio
    async def test_nao_inventa_dados(self):
        # O pior resultado possível seria devolver campos plausíveis.
        async with Cenario(FakeVLMService.ILEGIVEL) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Identificação/borrao.jpg")

        assert resultado["extracted_data"] == {}
        assert resultado["conflicts"] == []

    @pytest.mark.asyncio
    async def test_responde_sem_rebentar(self):
        async with Cenario(FakeVLMService.ILEGIVEL) as cenario:
            resultado = await cenario.extrair(f"{PASTA}/Identificação/borrao.jpg")

        assert resultado["success"] is True
        assert resultado["source_document"]["name"] == "borrao.jpg"


# ====================================================================
# 5. ARMAZENAMENTO EM BAIXO
# ====================================================================


class TestArmazenamentoEmBaixo:
    @pytest.mark.asyncio
    async def test_ficheiro_inexistente_da_404_e_nao_chama_o_modelo(self):
        falha = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        async with Cenario(FakeVLMService.CC, s3=_s3(falha=falha)) as cenario:
            with pytest.raises(HTTPException) as erro:
                await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")
            chamadas = cenario.motor.chamadas

        assert erro.value.status_code == 404
        assert chamadas == []

    @pytest.mark.asyncio
    async def test_s3_por_configurar_da_erro_legivel(self):
        servico = MagicMock()
        servico.is_configured.return_value = False
        async with Cenario(FakeVLMService.CC, s3=servico) as cenario:
            with pytest.raises(HTTPException) as erro:
                await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")

        assert erro.value.status_code == 500
        assert "S3" in erro.value.detail


# ====================================================================
# 6. GUARDAS DE ÂMBITO
# ====================================================================


class TestGuardasDeAmbito:
    @pytest.mark.asyncio
    async def test_um_backup_nao_e_um_documento(self):
        # Backups vivem no MESMO bucket, sob outro prefixo.
        async with Cenario(FakeVLMService.CC) as cenario:
            with pytest.raises(HTTPException) as erro:
                # Com extensão suportada, para que seja a guarda de âmbito
                # a recusar e não o filtro de formato.
                await cenario.extrair("backups/powercell-2026-09.pdf")
            chamadas = cenario.motor.chamadas

        assert erro.value.status_code == 403
        assert chamadas == []

    @pytest.mark.asyncio
    async def test_documento_de_outro_cliente_e_recusado(self):
        async with Cenario(FakeVLMService.CC) as cenario:
            with pytest.raises(HTTPException) as erro:
                await cenario.extrair(
                    "Documentação Clientes/João Costa/Identificação/cc.jpg"
                )
            chamadas = cenario.motor.chamadas

        assert erro.value.status_code == 403
        assert chamadas == []

    @pytest.mark.asyncio
    async def test_formato_nao_suportado_e_recusado_antes_de_tudo(self):
        async with Cenario(FakeVLMService.CC) as cenario:
            with pytest.raises(HTTPException) as erro:
                await cenario.extrair(f"{PASTA}/Outros/procuracao.docx")
            chamadas = cenario.motor.chamadas

        assert erro.value.status_code == 400
        assert chamadas == []


# ====================================================================
# 7. A REGRA DE OURO
# ====================================================================


class TestNadaEEscrito:
    @pytest.mark.asyncio
    async def test_a_ficha_do_processo_fica_intacta(self):
        # O teste que dá sentido ao épico: a IA lê, não escreve. A escrita
        # é de `/documents/ai-apply-suggestions`, depois da confirmação.
        processo = _processo(personal_data={"nif": "111111111"})
        async with Cenario(FakeVLMService.CC, processo=processo) as cenario:
            await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")
            depois = await cenario.db.processes.find_one({"id": "proc-1"})

        assert depois["personal_data"] == {"nif": "111111111"}
        assert depois.get("financial_data") == {}

    @pytest.mark.asyncio
    async def test_o_documento_nao_e_marcado_como_analisado(self):
        # Marcar aqui faria o ficheiro ser saltado na análise em lote sem
        # que nada tivesse sido aplicado à ficha.
        async with Cenario(FakeVLMService.CC) as cenario:
            await cenario.extrair(f"{PASTA}/Identificação/cc.jpg")
            metadados = await cenario.db.document_metadata.find_one(
                {"process_id": "proc-1"}
            )

        assert metadados is None
