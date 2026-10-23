"""Arquivo histórico do Index — as partes PURAS (sem MongoDB nem modelo)."""
from __future__ import annotations

import ast
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services import index_advanced_search as pesquisa
from services import index_ai as ia
from services import index_historical_import as imp

FONTE = Path(imp.__file__)


class TestPistaDoTipo:
    @pytest.mark.parametrize("nome,esperado", [
        ("2019/Recibos/Maria_recibo_vencimento_maio.pdf", ia.TIPO_RECIBO),
        ("a/Recibo de Vencimento 03-2019.pdf", ia.TIPO_RECIBO),
        ("a/recibo-de-salario.PDF", ia.TIPO_RECIBO),
        ("x/extrato_conta_ordem.pdf", ia.TIPO_EXTRATO),
        ("x/Extracto movimentos.png", ia.TIPO_EXTRATO),
        ("x/declaracao_efetividade.pdf", ia.TIPO_DECLARACAO),
        ("x/Declaração da entidade patronal.pdf", ia.TIPO_DECLARACAO),
        ("x/cartao_de_cidadao_frente.jpg", ia.TIPO_IDENTIFICACAO),
        ("x/passaporte.pdf", ia.TIPO_IDENTIFICACAO),
        ("x/scan0001.pdf", None),
        ("x/IRS 2018.pdf", None),
    ])
    def test_tipos(self, nome, esperado):
        assert imp.pista_do_tipo(nome) == esperado

    def test_a_pasta_tambem_conta(self):
        assert imp.pista_do_tipo("Extratos bancários/scan0001.pdf") == ia.TIPO_EXTRATO

    def test_separadores_do_windows(self):
        assert imp.pista_do_tipo("2019\\Recibos de vencimento\\scan.pdf") == ia.TIPO_RECIBO


class TestExclusao:
    def _info(self, nome, **kw):
        i = zipfile.ZipInfo(nome)
        for k, v in kw.items():
            setattr(i, k, v)
        return i

    @pytest.mark.parametrize("nome,motivo", [
        ("a/", "pasta"), ("__MACOSX/a.pdf", "lixo_do_sistema"), ("a/.DS_Store", "lixo_do_sistema"),
        ("a/~$recibo.pdf", "lixo_do_sistema"), ("a/Thumbs.db", "lixo_do_sistema"), ("a/b.zip", "zip_aninhado"),
        ("a/b.docx", "formato"), ("a/b.txt", "formato"), ("a/ok.PDF", None), ("a/ok.jpeg", None), ("a/ok.png", None),
    ])
    def test_motivos(self, nome, motivo):
        assert imp.motivo_de_exclusao(self._info(nome)) == motivo

    def test_cifrado(self):
        assert imp.motivo_de_exclusao(self._info("a/ok.pdf", flag_bits=0x1)) == "cifrado"


class TestIdentificadores:
    def test_o_id_deriva_do_conteudo_e_da_rede(self):
        assert imp.id_do_documento("A", "abc") == imp.id_do_documento("A", "abc")
        assert imp.id_do_documento("A", "abc") != imp.id_do_documento("B", "abc")
        assert imp.id_do_documento("A", "abc") != imp.id_do_documento("A", "abd")
        assert imp.id_do_documento("A", "abc").startswith("hist_")

    def test_o_process_id_artificial(self):
        from services import index_store as store

        assert store.processo_historico("1a2b3c") == "historical_import_1a2b3c"

    def test_a_etiqueta_e_limpa_e_tem_tecto(self):
        assert imp.etiqueta_da_importacao(None, "/dados/Arquivo 2019.zip") == "Arquivo 2019"
        assert imp.etiqueta_da_importacao("  <b>OneDrive</b>\n2019 ", "x.zip") == "bOneDrive/b 2019"
        assert len(imp.etiqueta_da_importacao("x" * 500, "x.zip")) == imp.TAMANHO_DA_ETIQUETA

    def test_o_hash_do_zip_e_o_do_conteudo(self, tmp_path):
        import hashlib

        f = tmp_path / "a.zip"
        f.write_bytes(b"abc" * 1_000_000)
        assert imp.hash_do_zip(str(f)) == hashlib.sha256(b"abc" * 1_000_000).hexdigest()


class TestDadosUteis:
    @pytest.mark.parametrize("linha,esperado", [
        (None, False), ({}, False),
        ({"doc_type": "recibo", "net_salary_num": 0.0}, True),  # zero é um valor
        ({"doc_type": "recibo", "employer_nif": "501964843"}, True),
        ({"doc_type": "recibo"}, False),
        ({"doc_type": "extrato", "bank": "CGD"}, True),
        ({"doc_type": "extrato", "period": "2019-05"}, True),
        ({"doc_type": "extrato"}, False),
        ({"doc_type": "declaracao_efetividade", "employer_name": "X"}, True),
        ({"doc_type": "declaracao_efetividade"}, False),
        ({"doc_type": "outro", "employer_name": "X"}, False),
    ])
    def test_tem_dados_uteis(self, linha, esperado):
        assert imp.tem_dados_uteis(linha) is esperado


class TestPipelineDoArquivo:
    FILTROS = pesquisa.validar_filtros(
        min_salary=None, max_salary=None, contract_type=None, employer_nif=None, employer_name=None,
        employer_location=None, job_title=None, period_from=None, period_to=None, sort="period_desc",
        document_type="recibo",
    )

    def _pipeline(self, historicos):
        return pesquisa.construir_pipeline_de_documentos(
            self.FILTROS, [], {"network_id": {"$in": ["r"]}}, pagina=1, tamanho=10, condicao_dos_historicos=historicos)

    def _match_final(self, pipeline):
        return [e for e in pipeline if "$match" in e][-1]["$match"]

    def test_sem_condicao_o_arquivo_nao_entra(self):
        assert self._match_final(self._pipeline(None)) == {"proc.0": {"$exists": True}}

    def test_com_condicao_o_ramo_do_arquivo_junta_se_ao_do_processo(self):
        condicao = {"$and": [{"historical": True}, {"network_id": {"$in": ["r"]}}]}
        assert self._match_final(self._pipeline(condicao)) == {"$or": [{"proc.0": {"$exists": True}}, condicao]}

    def test_o_tipo_continua_a_ser_o_primeiro_match(self):
        primeiro = self._pipeline({"historical": True})[0]["$match"]
        assert primeiro["$and"][0] == {"doc_type": "recibo"}

    def test_a_projeccao_leva_a_marca_e_a_etiqueta(self):
        projecao = [e for e in self._pipeline(None)[-1]["$facet"]["items"] if "$project" in e][0]["$project"]
        assert projecao["historical"] == 1 and projecao["import_label"] == 1


class TestDtoDoArquivo:
    def test_o_dto_marca_e_esconde_o_processo_artificial(self):
        dto = pesquisa.resultado_do_documento({
            "id": "hist_x", "process_id": "historical_import_abc", "doc_type": "recibo", "historical": True,
            "import_label": "OneDrive", "net_salary_num": 1000.0, "employer_nif": "501964843",
        })
        assert dto["historical"] is True and dto["import_label"] == "OneDrive"
        assert dto["process_id"] is None and "historical_import" not in str(dto)

    def test_um_documento_normal_nao_leva_etiqueta_e_mantem_o_processo(self):
        dto = pesquisa.resultado_do_documento({"id": "d", "process_id": "p1", "doc_type": "recibo", "proc": {"process_number": 7}})
        assert dto["historical"] is False and "import_label" not in dto and dto["process_id"] == "p1"

    def test_so_true_estrito_e_historico(self):
        for valor in ("true", 1, "sim"):
            assert pesquisa.resultado_do_documento({"id": "d", "process_id": "p1", "doc_type": "recibo", "historical": valor})["historical"] is False


class TestClassificacao:
    async def test_com_o_motor_simulado_nao_inventa_nem_chama_o_modelo(self, monkeypatch):
        monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
        chamada = AsyncMock()
        with patch("services.ai_document.call_openai_api", chamada):
            r = await ia.classificar_documento(conteudo=b"x", filename="documento.pdf")
        assert r.tipo is None and r.origem == ia.ORIGEM_SIMULADA and chamada.await_count == 0

    def test_a_ferramenta_tem_uma_lista_fechada(self):
        enum = ia.definicao_de_classificacao()["function"]["parameters"]["properties"]["tipo"]["enum"]
        assert set(enum) == {"recibo_vencimento", "extrato_bancario", "declaracao_efetividade", "identificacao", "outro"}

    def test_a_analise_continua_a_usar_a_assinatura_antiga_de_mensagens(self):
        mensagens, sem_contexto, _ = ia._mensagens(ia.TIPO_RECIBO, b"nao e pdf", "x.pdf", "application/pdf")
        assert sem_contexto is True and "x.pdf" in mensagens[1]["content"]  # a análise do CRM mantém o recurso ao nome

    def test_a_classificacao_nunca_recua_para_o_nome_do_ficheiro(self):
        mensagens, sem_contexto, _ = ia._mensagens_do_documento(
            ia.PROMPT_DE_CLASSIFICACAO, b"nao e pdf", "Joao_Segredo.pdf", "application/pdf", enviar_nome=False)
        assert sem_contexto is True and "Joao_Segredo" not in str(mensagens)


class TestGuardaDeFonte:
    """O nome do ficheiro e o caminho do ZIP nunca saem do módulo: a IA recebe `documento.<ext>`."""

    def _chamadas(self, nome):
        arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
        return [n for n in ast.walk(arvore) if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == nome]

    @pytest.mark.parametrize("funcao", ["classificar_documento", "analisar_documento"])
    def test_o_modelo_so_recebe_o_nome_neutro(self, funcao):
        chamadas = self._chamadas(funcao)
        assert chamadas, f"o leitor ficou cego: nenhuma chamada a {funcao}"
        for c in chamadas:
            nome = next(k.value for k in c.keywords if k.arg == "filename")
            assert isinstance(nome, ast.Name) and nome.id == "nome_neutro"

    def test_nada_do_zip_e_gravado_em_disco(self):
        fonte = FONTE.read_text(encoding="utf-8")
        for proibido in ("extractall", ".extract(", "NamedTemporaryFile", "write_bytes", '"wb"', "mkdtemp"):
            assert proibido not in fonte
