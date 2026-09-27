"""
"VLM no Escuro" — a análise em lote falhava em silêncio (Lote 5, P0).

O SINTOMA
  Clicar em "Analisar Documentos" nos detalhes do processo: a barra
  corre, aparece um toast VERDE ("Análise completa! 3 documento(s)
  processado(s)") e o Diálogo de Revisão Humana nunca abre. Sem erro,
  sem aviso, sem nada para reportar.

A CADEIA DO SILÊNCIO (três pontos, todos a engolir)
  1. `ai_document_analyzer.analyze_multiple_documents` trata cada
     documento num ciclo. Quando a análise devolve
     `{"success": False, "error": ...}` — chave da OpenAI em falta,
     quota esgotada, formato recusado — o erro vai para o LOG de
     importação e o documento é simplesmente SALTADO. O agregado volta
     sem `documents_analyzed`, sem comparação e sem excepção.
  2. `document_ai_analyze.run_analysis_on_documents` devolve
     `"success": True` escrito à mão e `documents_count: len(documents)`
     — o número de documentos ENVIADOS, não o dos que a IA leu. Para o
     frontend, três documentos falhados são indistinguíveis de três
     documentos sem nada a preencher.
  3. No frontend, `commitAIExtractedData` tinha dois `return` mudos.

  Nenhum dos três está errado sozinho; juntos apagam a falha.

A REGRA
  A resposta tem de dizer quantos documentos a IA leu MESMO e quais
  falharam, com o motivo. O contrato `success: True` mantém-se — o
  pedido HTTP correu bem; o que falhou foi o trabalho, e isso é
  conteúdo da resposta, não código de estado.
"""
from unittest.mock import AsyncMock, patch

import pytest


def _doc(nome="irs.pdf"):
    return {"content": b"%PDF-1.4 fake", "name": nome, "mime_type": "application/pdf"}


class TestOAgregadorGuardaAsFalhas:
    @pytest.mark.asyncio
    async def test_um_documento_falhado_aparece_no_resultado(self):
        from services import ai_document_analyzer as mod

        with patch.object(
            mod,
            "analyze_document_with_ai",
            AsyncMock(return_value={"success": False, "error": "Chave de API não configurada"}),
        ), patch("routes.ai_import_logs.update_ai_import_log", AsyncMock()):
            resultado = await mod.analyze_multiple_documents([_doc()], {}, log_id=None)

        assert resultado["documents_analyzed"] == []
        falhas = resultado.get("documents_failed")
        assert falhas, "a falha por documento não pode morrer dentro do ciclo"
        assert falhas[0]["file_name"] == "irs.pdf"
        assert "Chave de API" in falhas[0]["error"]

    @pytest.mark.asyncio
    async def test_um_lote_bem_sucedido_nao_inventa_falhas(self):
        """Contraprova: a lista de falhas fica vazia quando corre tudo bem."""
        from services import ai_document_analyzer as mod

        analise = {
            "success": True,
            "tipo_documento": "irs",
            "confianca": 0.9,
            "dados_extraidos": {"nif": "123456789"},
            "file_name": "irs.pdf",
        }
        with patch.object(mod, "analyze_document_with_ai", AsyncMock(return_value=analise)), \
                patch.object(mod, "compare_extracted_with_existing", return_value={
                    "matching": [], "different": [], "new_fields": [], "empty_fields": []
                }), \
                patch("routes.ai_import_logs.update_ai_import_log", AsyncMock()):
            resultado = await mod.analyze_multiple_documents([_doc()], {}, log_id=None)

        assert resultado.get("documents_failed") == []
        assert len(resultado["documents_analyzed"]) == 1


class TestARespostaDizAVerdade:
    def test_a_contagem_de_lidos_nao_e_a_de_enviados(self):
        """`documents_count` conta o que foi ENVIADO. Quem decide se há
        algo para mostrar precisa de saber quantos a IA leu."""
        from services.document_ai_analyze import resumo_da_analise

        resumo = resumo_da_analise(
            {"documents_analyzed": [], "documents_failed": [
                {"file_name": "irs.pdf", "error": "quota esgotada"}
            ]},
            [_doc()],
        )
        assert resumo["documents_succeeded"] == 0
        assert resumo["documents_failed"][0]["file_name"] == "irs.pdf"

    def test_um_documento_que_a_ia_leu_conta_como_lido(self):
        from services.document_ai_analyze import resumo_da_analise

        resumo = resumo_da_analise(
            {"documents_analyzed": [{"file_name": "irs.pdf"}], "documents_failed": []},
            [_doc()],
        )
        assert resumo["documents_succeeded"] == 1
        assert resumo["documents_failed"] == []

    def test_um_agregado_antigo_sem_a_chave_nao_rebenta(self):
        """Graceful degradation: um resultado sem `documents_failed`
        (analyzer antigo em memória, mock de teste) não pode levantar."""
        from services.document_ai_analyze import resumo_da_analise

        resumo = resumo_da_analise({"documents_analyzed": []}, [_doc()])
        assert resumo["documents_succeeded"] == 0
        assert resumo["documents_failed"] == []

    def test_sem_agregado_nenhum_tambem_nao_rebenta(self):
        from services.document_ai_analyze import resumo_da_analise

        assert resumo_da_analise(None, [_doc()])["documents_succeeded"] == 0
