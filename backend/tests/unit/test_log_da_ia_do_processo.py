"""
LOG DA IA DO PROCESSO (`process_ai_log`) — a IA deixa de ser uma caixa preta (Out 2026).

O que se afirma, e porquê:
  · o REGISTO nunca grava o texto de um erro do fornecedor (pode trazer parte da chave) nem
    valores de campos (só nomes), e nunca levanta (observa, não intercepta);
  · cada ponto de IA sobre documentos DEIXA RASTO — cada gancho é provado correndo o código real
    com a IA falseada (e há guarda de fonte de que apagar a chamada parte um teste);
  · a LEITURA é por processo, mais recente primeiro, lista positiva, e `pode_reanalisar` vem da
    MESMA função que as rotas de IA manual usam para recusar;
  · a lacuna de RBAC: `categorize`, `categorize-all` e `ai-analyze-review` só tinham o botão
    escondido — o servidor aceitava qualquer staff. O ataque exige que o handler NUNCA corra.
"""
from __future__ import annotations

import ast
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services import document_ai_access as acesso
from services import document_ai_analyze
from services import document_ai_trigger
from services import document_auto_categorize
from services import document_categorize
from services import document_review
from services import process_ai_log as log
from services import process_ai_log_api
from services.tenant_network import TenantScope
from tests.unit.helpers_fonte import codigo_sem_comentarios

PID = "proc-1"
GESTOR = {"id": "u-dir", "name": "Diana Diretora", "role": "diretor"}
CONSULTOR = {"id": "u-cons", "name": "Carlos Consultor", "role": "consultor"}
INDEXADOR = {"id": "u-idx", "name": "Ivo Index", "role": "indexacao"}

#: Texto de erro REAL de um fornecedor: leva um pedaço de chave. Nunca pode chegar à base de dados.
ERRO_COM_CHAVE = "Incorrect API key provided: sk-proj-SEGREDO123. You can find your API key at ..."


async def _linhas(fake_db, **filtro):
    return await fake_db.process_ai_log.find(filtro).to_list(None)


# ====================================================================
# 1. O registo
# ====================================================================
class TestClassificarFalha:
    def test_nunca_devolve_o_texto_do_erro(self):
        codigo = log.classificar_falha(ERRO_COM_CHAVE)
        assert codigo in log.MOTIVOS
        assert "SEGREDO" not in codigo

    def test_chave_incorrecta_e_configuracao(self):
        assert log.classificar_falha(ERRO_COM_CHAVE) == "ia_nao_configurada"

    def test_o_limite_vem_ANTES_da_credencial(self):
        # «rate limit … api key» tem as duas pistas; mandar rever uma chave certa é pior.
        assert log.classificar_falha("Rate limit reached for key api key abc") == "limite_do_fornecedor"

    @pytest.mark.parametrize("texto", ["429 Too Many Requests", "insufficient_quota", "quota exceeded"])
    def test_limites(self, texto):
        assert log.classificar_falha(texto) == "limite_do_fornecedor"

    def test_tempo_excedido(self):
        assert log.classificar_falha("Request timed out") == "tempo_excedido"

    @pytest.mark.parametrize("vazio", [None, "", 0])
    def test_sem_texto_e_erro_generico(self, vazio):
        assert log.classificar_falha(vazio) == "erro_da_ia"

    def test_excepcao_tambem_serve(self):
        assert log.classificar_falha(TimeoutError("timeout ao ligar")) == "tempo_excedido"


class TestMontarLinha:
    def _base(self, **extra):
        return log.montar_linha(process_id=PID, accao="categorizar", estado="sucesso",
                                gatilho="automatico", **extra)

    def test_so_nomes_de_campos_sem_repeticoes(self):
        linha = self._base(campos=["nif", "morada", "nif", "  ", None])
        assert linha["campos"] == ["nif", "morada", "None"] or "nif" in linha["campos"]
        assert linha["campos"].count("nif") == 1

    def test_um_valor_pessoal_nao_tem_onde_ficar(self):
        linha = self._base(campos=["nif"])
        assert "123456789" not in repr(linha)

    def test_motivo_fora_do_registo_nunca_vai_como_texto_livre(self):
        assert self._base(motivo="Incorrect API key sk-xyz")["motivo"] == "erro_interno"

    @pytest.mark.parametrize("campo,valor", [("accao", "apagar"), ("estado", "talvez"), ("gatilho", "cron")])
    def test_valores_desconhecidos_sao_recusados(self, campo, valor):
        args = {"process_id": PID, "accao": "categorizar", "estado": "sucesso", "gatilho": "manual"}
        args[campo] = valor
        with pytest.raises(ValueError):
            log.montar_linha(**args)

    def test_expira_em_doze_meses_com_datetime_nativo(self):
        from datetime import datetime

        linha = self._base()
        assert isinstance(linha["expire_at"], datetime)  # o TTL ignora strings ISO
        dias = (linha["expire_at"] - datetime.fromisoformat(linha["created_at"])).days
        assert dias == log.RETENCAO_DIAS == 365


class TestRegistar:
    @pytest.mark.asyncio
    async def test_nunca_levanta_se_a_base_de_dados_falha(self):
        falso = MagicMock()
        falso.process_ai_log.insert_one = AsyncMock(side_effect=RuntimeError("mongo em baixo"))
        with patch.object(log, "db", falso):
            await log.registar_accao_ia(process_id=PID, accao="categorizar", estado="falha", gatilho="automatico")

    @pytest.mark.asyncio
    async def test_sem_processo_nao_ha_log(self, fake_async_db):
        with patch.object(log, "db", fake_async_db):
            await log.registar_accao_ia(process_id=None, accao="categorizar", estado="falha", gatilho="automatico")
        assert await _linhas(fake_async_db) == []

    @pytest.mark.asyncio
    async def test_o_automatico_nao_tem_autor_mesmo_que_se_passe_utilizador(self, fake_async_db):
        with patch.object(log, "db", fake_async_db):
            await log.registar_accao_ia(process_id=PID, accao="categorizar", estado="sucesso",
                                        gatilho="automatico", user=GESTOR)
        (linha,) = await _linhas(fake_async_db)
        assert linha["utilizador_id"] is None and linha["utilizador_nome"] is None

    @pytest.mark.asyncio
    async def test_o_manual_regista_quem_carregou(self, fake_async_db):
        with patch.object(log, "db", fake_async_db):
            await log.registar_accao_ia(process_id=PID, accao="rever", estado="sucesso",
                                        gatilho="manual", user=GESTOR)
        (linha,) = await _linhas(fake_async_db)
        assert linha["utilizador_nome"] == "Diana Diretora"

    @pytest.mark.asyncio
    async def test_o_perfil_silenciado_nao_deixa_o_nome(self, fake_async_db):
        with patch.object(log, "db", fake_async_db):
            await log.registar_accao_ia(process_id=PID, accao="rever", estado="sucesso",
                                        gatilho="manual", user=INDEXADOR)
        (linha,) = await _linhas(fake_async_db)
        # A acção fica (é do processo); o NOME de quem a fez, não (a Indexação não deixa rasto pessoal).
        assert linha["accao"] == "rever" and linha["utilizador_nome"] is None


# ====================================================================
# 2. Os ganchos — cada ponto de IA deixa rasto (código real, IA falseada)
# ====================================================================
class TestAutoCategorizacao:
    async def _correr(self, fake_db, resultado, *, conteudo=b"%PDF-1.4 x", nome="cc.pdf",
                      texto="Cartão de Cidadão Maria", ocr=None):
        ocr_fn = AsyncMock(return_value=ocr or {})
        with patch.object(document_auto_categorize, "db", fake_db), \
             patch.object(log, "db", fake_db), \
             patch("services.document_categorization.categorize_document_with_ai", AsyncMock(return_value=resultado)), \
             patch("services.document_categorization.extract_text_from_pdf", return_value=texto), \
             patch("services.ai_document.analyze_document_from_base64", ocr_fn):
            await document_auto_categorize.auto_categorize_document_background(
                process_id=PID, client_name="Maria", s3_path=f"Documentação Clientes/x/{nome}",
                filename=nome, file_content=conteudo, satisfazer_pedidos=False, origem="portal",
            )

    @pytest.mark.asyncio
    async def test_sucesso_regista_categoria_e_so_nomes_dos_campos(self, fake_async_db):
        await self._correr(
            fake_async_db,
            {"success": True, "category": "Identificação", "subcategory": "CC", "confidence": 0.93},
            ocr={"extracted_data": {"nif": "123456789", "morada": "Rua A"}},
        )
        (linha,) = await _linhas(fake_async_db, estado="sucesso")
        assert linha["categoria"] == "Identificação"
        assert linha["gatilho"] == "automatico" and linha["origem"] == "portal"
        assert set(linha["campos"]) == {"nif", "morada"}
        assert "123456789" not in repr(linha) and "Rua A" not in repr(linha)

    @pytest.mark.asyncio
    async def test_falha_do_fornecedor_regista_o_codigo_e_nunca_o_texto(self, fake_async_db):
        await self._correr(fake_async_db, {"success": False, "error": ERRO_COM_CHAVE})
        (linha,) = await _linhas(fake_async_db, estado="falha")
        assert linha["motivo"] == "ia_nao_configurada"
        assert "SEGREDO" not in repr(linha) and "sk-proj" not in repr(linha)

    @pytest.mark.asyncio
    async def test_sem_texto_extraivel_diz_se(self, fake_async_db):
        # «Falhou por falta de contexto»: um PDF digitalizado só deixa o nome do ficheiro à IA.
        await self._correr(fake_async_db,
                           {"success": True, "category": "Outros", "confidence": 0.4}, texto="")
        (linha,) = await _linhas(fake_async_db, estado="sucesso")
        assert linha["motivo"] == "sem_contexto"

    @pytest.mark.asyncio
    async def test_excepcao_inesperada_tambem_fica_registada(self, fake_async_db):
        with patch.object(document_auto_categorize, "db", fake_async_db), \
             patch.object(log, "db", fake_async_db), \
             patch("services.document_categorization.categorize_document_with_ai",
                   AsyncMock(side_effect=RuntimeError(ERRO_COM_CHAVE))), \
             patch("services.document_categorization.extract_text_from_pdf", return_value="t"):
            await document_auto_categorize.auto_categorize_document_background(
                process_id=PID, client_name="M", s3_path="a/b.pdf", filename="b.pdf", file_content=b"x")
        (linha,) = await _linhas(fake_async_db, estado="falha")
        assert "SEGREDO" not in repr(linha)


class TestIaDaEntrada:
    @pytest.mark.asyncio
    async def test_ja_categorizado_fica_como_saltado(self, fake_async_db):
        await fake_async_db.document_metadata.insert_one({"s3_path": "a/b.pdf", "is_categorized": True})
        with patch.object(document_ai_trigger, "db", fake_async_db), patch.object(log, "db", fake_async_db):
            estado = await document_ai_trigger.correr_ia_da_entrada(
                process_id=PID, client_name="M", s3_path="a/b.pdf", filename="b.pdf", origem="portal")
        assert estado == "ja_categorizado"
        (linha,) = await _linhas(fake_async_db)
        assert (linha["estado"], linha["motivo"]) == ("saltado", "ja_categorizado")

    @pytest.mark.asyncio
    async def test_demasiado_grande_fica_como_saltado(self, fake_async_db):
        with patch.object(document_ai_trigger, "db", fake_async_db), patch.object(log, "db", fake_async_db):
            estado = await document_ai_trigger.correr_ia_da_entrada(
                process_id=PID, client_name="M", s3_path="a/b.pdf", filename="b.pdf",
                tamanho=document_ai_trigger.TAMANHO_MAXIMO_PARA_IA + 1)
        assert estado == "demasiado_grande"
        (linha,) = await _linhas(fake_async_db)
        assert (linha["estado"], linha["motivo"]) == ("saltado", "demasiado_grande")

    @pytest.mark.asyncio
    async def test_ficheiro_ilegivel_e_falha(self, fake_async_db):
        s3 = MagicMock()
        s3.get_file_content.return_value = None
        with patch.object(document_ai_trigger, "db", fake_async_db), patch.object(log, "db", fake_async_db), \
             patch.object(document_ai_trigger, "s3_service", s3):
            estado = await document_ai_trigger.correr_ia_da_entrada(
                process_id=PID, client_name="M", s3_path="a/b.pdf", filename="b.pdf", tamanho=10)
        assert estado == "ilegivel"
        (linha,) = await _linhas(fake_async_db)
        assert (linha["estado"], linha["motivo"]) == ("falha", "ilegivel")


class TestCategorizacaoManual:
    @pytest.mark.asyncio
    async def test_um_documento_regista_o_autor(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "client_name": "Maria"})
        s3 = MagicMock()
        s3.get_file_content.return_value = b"%PDF"
        with patch.object(document_categorize, "db", fake_async_db), patch.object(log, "db", fake_async_db), \
             patch.object(document_categorize, "s3_service", s3), \
             patch.object(document_categorize, "extract_text_from_pdf", return_value="texto"), \
             patch.object(document_categorize, "categorize_document_with_ai",
                          AsyncMock(return_value={"success": True, "category": "IRS", "confidence": 0.9})):
            await document_categorize.run_categorize_document(PID, s3_path="a/irs.pdf", filename="irs.pdf", user=GESTOR)
        (linha,) = await _linhas(fake_async_db)
        assert (linha["estado"], linha["gatilho"], linha["utilizador_nome"]) == ("sucesso", "manual", "Diana Diretora")

    @pytest.mark.asyncio
    async def test_falha_regista_e_continua_a_levantar(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "client_name": "Maria"})
        s3 = MagicMock()
        s3.get_file_content.return_value = b"%PDF"
        with patch.object(document_categorize, "db", fake_async_db), patch.object(log, "db", fake_async_db), \
             patch.object(document_categorize, "s3_service", s3), \
             patch.object(document_categorize, "extract_text_from_pdf", return_value="texto"), \
             patch.object(document_categorize, "categorize_document_with_ai",
                          AsyncMock(return_value={"success": False, "error": "429 quota"})):
            with pytest.raises(HTTPException):
                await document_categorize.run_categorize_document(PID, s3_path="a/irs.pdf", filename="irs.pdf", user=GESTOR)
        (linha,) = await _linhas(fake_async_db)
        assert (linha["estado"], linha["motivo"]) == ("falha", "limite_do_fornecedor")


class TestAnaliseEExtraccao:
    DOCS = [
        {"content": b"x", "name": "cc.jpg", "mime_type": "image/jpeg", "source_path": "p/cc.jpg"},
        {"content": b"y", "name": "irs.pdf", "mime_type": "application/pdf", "source_path": "p/irs.pdf"},
    ]

    async def _correr(self, fake_db, resultados, *, accao="analisar", skip=False, analisados=()):
        await fake_db.processes.insert_one({"id": PID, "client_name": "Maria"})
        for nome in analisados:
            await fake_db.document_metadata.insert_one(
                {"process_id": PID, "filename": nome, "ai_analyzed": True, "s3_path": f"p/{nome}"})
        analisador = AsyncMock(return_value=resultados)
        with patch.object(document_ai_analyze, "db", fake_db), patch.object(log, "db", fake_db), \
             patch("services.ai_document_analyzer.analyze_multiple_documents", analisador), \
             patch.object(document_ai_analyze, "_build_titular_matches_for_analysis", AsyncMock(return_value=[])):
            return await document_ai_analyze.run_analysis_on_documents(
                PID, [dict(d) for d in self.DOCS], user=GESTOR, skip_analyzed=skip, accao=accao)

    @pytest.mark.asyncio
    async def test_um_sucesso_e_uma_falha_ficam_cada_um_no_seu_estado(self, fake_async_db):
        await self._correr(fake_async_db, {
            "documents_analyzed": [{"file_name": "cc.jpg", "tipo_documento": "cc",
                                    "extracted_data": {"nif": "123456789"}}],
            "documents_failed": [{"file_name": "irs.pdf", "error": ERRO_COM_CHAVE}],
            "auto_fill_suggestions": {}, "comparison": {},
        })
        linhas = {l["ficheiro"]: l for l in await _linhas(fake_async_db)}
        assert linhas["cc.jpg"]["estado"] == "sucesso" and linhas["cc.jpg"]["campos"] == ["nif"]
        assert linhas["irs.pdf"]["estado"] == "falha" and linhas["irs.pdf"]["motivo"] == "ia_nao_configurada"
        assert "SEGREDO" not in repr(linhas) and "123456789" not in repr(linhas)
        assert linhas["cc.jpg"]["utilizador_nome"] == "Diana Diretora"

    @pytest.mark.asyncio
    async def test_a_extraccao_aparece_com_o_seu_nome(self, fake_async_db):
        await self._correr(fake_async_db, {"documents_analyzed": [{"file_name": "cc.jpg"}],
                                           "documents_failed": [], "auto_fill_suggestions": {}, "comparison": {}},
                           accao="extrair_dados")
        assert {l["accao"] for l in await _linhas(fake_async_db)} == {"extrair_dados"}

    @pytest.mark.asyncio
    async def test_resultado_vazio_do_analisador_e_falha_em_todos(self, fake_async_db):
        await self._correr(fake_async_db, None)
        linhas = await _linhas(fake_async_db)
        assert len(linhas) == 2 and {l["estado"] for l in linhas} == {"falha"}

    @pytest.mark.asyncio
    async def test_analisador_a_rebentar_regista_todos_e_propaga(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": PID, "client_name": "Maria"})
        with patch.object(document_ai_analyze, "db", fake_async_db), patch.object(log, "db", fake_async_db), \
             patch("services.ai_document_analyzer.analyze_multiple_documents",
                   AsyncMock(side_effect=RuntimeError("timeout"))):
            with pytest.raises(HTTPException):
                await document_ai_analyze.run_analysis_on_documents(
                    PID, [dict(d) for d in self.DOCS], user=GESTOR, skip_analyzed=False)
        linhas = await _linhas(fake_async_db)
        assert len(linhas) == 2 and {l["motivo"] for l in linhas} == {"tempo_excedido"}

    @pytest.mark.asyncio
    async def test_o_ja_analisado_fica_como_saltado(self, fake_async_db):
        await self._correr(
            fake_async_db,
            {"documents_analyzed": [{"file_name": "irs.pdf"}], "documents_failed": [],
             "auto_fill_suggestions": {}, "comparison": {}},
            skip=True, analisados=("cc.jpg",),
        )
        saltados = await _linhas(fake_async_db, estado="saltado")
        assert [(l["ficheiro"], l["motivo"]) for l in saltados] == [("cc.jpg", "ja_analisado")]


class TestRevisao:
    async def _correr(self, fake_db, categorizacao, *, texto="texto do documento"):
        await fake_db.document_metadata.insert_one(
            {"id": "d-1", "process_id": PID, "s3_path": "p/cc.pdf", "filename": "cc.pdf"})
        s3 = MagicMock()
        s3.get_file_content.return_value = b"%PDF"
        with patch.object(document_review, "db", fake_db), patch.object(log, "db", fake_db), \
             patch.object(document_review, "s3_service", s3), \
             patch.object(document_review, "extract_text_from_pdf", return_value=texto), \
             patch.object(document_review, "should_run_ocr_for_category", return_value=False), \
             patch.object(document_review, "categorize_document_with_ai", AsyncMock(return_value=categorizacao)):
            return await document_review.run_analyze_document_for_review("d-1", GESTOR)

    @pytest.mark.asyncio
    async def test_sucesso_regista_o_que_foi_proposto(self, fake_async_db):
        await self._correr(fake_async_db, {"success": True, "category": "Identificação", "confidence": 0.9,
                                           "expiry_date": "2030-01-01"})
        (linha,) = await _linhas(fake_async_db)
        assert (linha["accao"], linha["estado"], linha["documento_id"]) == ("rever", "sucesso", "d-1")
        assert "validade" in linha["campos"] and "2030" not in repr(linha)

    @pytest.mark.asyncio
    async def test_falha_regista_o_motivo(self, fake_async_db):
        await self._correr(fake_async_db, {"success": False, "error": ERRO_COM_CHAVE})
        (linha,) = await _linhas(fake_async_db)
        assert (linha["estado"], linha["motivo"]) == ("falha", "ia_nao_configurada")
        assert "SEGREDO" not in repr(linha)


class TestCadaGanchoEstaLigado:
    """Contraprova de FONTE: apagar a chamada ao registo deixa o ponto de IA mudo outra vez."""

    @pytest.mark.parametrize("modulo,minimo", [
        (document_auto_categorize, 3),
        (document_ai_trigger, 4),
        (document_categorize, 5),
        (document_ai_analyze, 4),
        (document_review, 4),
    ])
    def test_o_modulo_regista(self, modulo, minimo):
        fonte = codigo_sem_comentarios(inspect.getsource(modulo))
        assert fonte.count("registar_accao_ia(") >= minimo

    def test_a_extraccao_por_ficheiro_pede_a_accao_certa(self):
        from services import document_vision_extract

        fonte = codigo_sem_comentarios(inspect.getsource(document_vision_extract))
        # `ast.unparse` normaliza as aspas: compara-se o literal já normalizado.
        assert "accao='extrair_dados'" in fonte


# ====================================================================
# 3. A leitura
# ====================================================================
class TestLeitura:
    async def _semear(self, fake_db):
        with patch.object(log, "db", fake_db):
            for i in range(5):
                await log.registar_accao_ia(process_id=PID, accao="categorizar", estado="sucesso",
                                            gatilho="automatico", ficheiro=f"doc{i}.pdf",
                                            s3_path=f"Documentação Clientes/x/doc{i}.pdf", documento_id=f"d{i}")
            await log.registar_accao_ia(process_id=PID, accao="categorizar", estado="falha",
                                        gatilho="automatico", ficheiro="mau.pdf", motivo="ia_nao_configurada")
            await log.registar_accao_ia(process_id="outro", accao="categorizar", estado="sucesso",
                                        gatilho="automatico", ficheiro="alheio.pdf")

    @pytest.mark.asyncio
    async def test_so_o_processo_pedido_e_o_mais_recente_primeiro(self, fake_async_db):
        await self._semear(fake_async_db)
        with patch.object(log, "db", fake_async_db):
            pagina = await log.listar_accoes_ia(PID)
        nomes = [i["ficheiro"] for i in pagina["items"]]
        assert "alheio.pdf" not in nomes and pagina["total"] == 6
        assert nomes[0] == "mau.pdf"  # a última a ser registada

    @pytest.mark.asyncio
    async def test_filtra_por_estado_e_pagina(self, fake_async_db):
        await self._semear(fake_async_db)
        with patch.object(log, "db", fake_async_db):
            falhas = await log.listar_accoes_ia(PID, estado="falha")
            segunda = await log.listar_accoes_ia(PID, pagina=2, por_pagina=4)
        assert [i["ficheiro"] for i in falhas["items"]] == ["mau.pdf"]
        assert len(segunda["items"]) == 2 and segunda["page"] == 2

    @pytest.mark.asyncio
    async def test_a_saida_e_uma_lista_positiva_com_a_mensagem_do_motivo(self, fake_async_db):
        await self._semear(fake_async_db)
        with patch.object(log, "db", fake_async_db):
            pagina = await log.listar_accoes_ia(PID, estado="falha")
        (item,) = pagina["items"]
        assert item["motivo_mensagem"] == log.MOTIVOS["ia_nao_configurada"]
        assert item["accao_rotulo"] == log.ACCOES["categorizar"]
        # Nem a chave do bucket, nem o carimbo de expiração, nem o id do processo saem para o ecrã.
        assert not ({"s3_path", "expire_at", "process_id", "_id"} & set(item))

    @pytest.mark.asyncio
    async def test_o_tecto_da_pagina_e_respeitado(self, fake_async_db):
        with patch.object(log, "db", fake_async_db):
            pagina = await log.listar_accoes_ia(PID, por_pagina=100000)
        assert pagina["size"] == log.MAXIMO_POR_PAGINA

    def test_a_consulta_leva_sempre_o_process_id(self):
        fonte = codigo_sem_comentarios(inspect.getsource(log.listar_accoes_ia))
        assert "'process_id': process_id" in fonte


class TestEndpointDeLeitura:
    @pytest.mark.asyncio
    async def test_devolve_a_pagina_e_a_permissao_de_reanalisar(self):
        processo = {"id": PID}
        with patch.object(process_ai_log_api, "assert_can_view_process_documents_by_id",
                          AsyncMock(return_value=processo)), \
             patch.object(process_ai_log_api, "listar_accoes_ia",
                          AsyncMock(return_value={"items": [], "total": 0, "page": 1, "size": 30})), \
             patch.object(process_ai_log_api, "pode_usar_ia_no_processo", AsyncMock(return_value=True)) as pode:
            r = await process_ai_log_api.run_get_process_ai_log(MagicMock(), PID, GESTOR)
        assert r["pode_reanalisar"] is True
        pode.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_o_consultor_atribuido_ve_o_log_mas_nao_o_botao(self):
        with patch.object(process_ai_log_api, "assert_can_view_process_documents_by_id",
                          AsyncMock(return_value={"id": PID, "assigned_consultor_ids": ["u-cons"]})), \
             patch.object(process_ai_log_api, "listar_accoes_ia",
                          AsyncMock(return_value={"items": [], "total": 0, "page": 1, "size": 30})), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=TenantScope(network_ids=("r",)))):
            r = await process_ai_log_api.run_get_process_ai_log(MagicMock(), PID, CONSULTOR)
        assert r["pode_reanalisar"] is False

    @pytest.mark.asyncio
    async def test_a_visibilidade_dos_documentos_vem_antes_de_ler_o_log(self):
        lista = AsyncMock()
        with patch.object(process_ai_log_api, "assert_can_view_process_documents_by_id",
                          AsyncMock(side_effect=HTTPException(status_code=403, detail="restrito"))), \
             patch.object(process_ai_log_api, "listar_accoes_ia", lista):
            with pytest.raises(HTTPException) as e:
                await process_ai_log_api.run_get_process_ai_log(MagicMock(), PID, CONSULTOR)
        assert e.value.status_code == 403
        lista.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_estado_invalido_e_400(self):
        with pytest.raises(HTTPException) as e:
            await process_ai_log_api.run_get_process_ai_log(MagicMock(), PID, GESTOR, estado="talvez")
        assert e.value.status_code == 400

    def test_a_rota_e_so_staff_e_atras_da_fronteira_de_rede(self):
        from routes import process_ai_log as rota
        from services.process_scope_guard import exigir_processo_no_ambito

        deps = [d.dependency for d in rota.router.dependencies]
        assert exigir_processo_no_ambito in deps
        fonte = codigo_sem_comentarios(inspect.getsource(rota))
        assert "require_staff()" in fonte

    def test_o_router_esta_ligado_ao_servidor(self):
        import server

        caminhos = {getattr(r, "path", "") for r in server.app.routes}
        assert "/api/processes/{process_id}/ai-log" in caminhos


# ====================================================================
# 4. A lacuna de RBAC: o servidor aceitava o que o ecrã escondia
# ====================================================================
def _ambito(redes=("r",)):
    return TenantScope(network_ids=tuple(redes))


class TestAExploracao:
    """O ataque: um staff que NÃO é alto perfil chama as rotas pagas directamente."""

    def _patches(self, fake_db, papel):
        return (
            patch("database.db", fake_db),
            patch.object(acesso, "get_effective_role_async", AsyncMock(return_value=papel)),
            patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=_ambito())),
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "administrativo", "indexacao"])
    async def test_categorize_all_recusa_o_staff_operacional_e_nunca_corre(self, fake_async_db, papel):
        from routes import documents

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "assigned_consultor_ids": ["u-x"]})
        corre = AsyncMock()
        p1, p2, p3 = self._patches(fake_async_db, papel)
        with p1, p2, p3, patch.object(documents, "run_categorize_all_documents", corre):
            with pytest.raises(HTTPException) as e:
                await documents.categorize_all_documents(MagicMock(), PID, user={"id": "u-x", "role": papel})
        assert e.value.status_code == 403
        corre.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_categorize_recusa_o_consultor_ATRIBUIDO(self, fake_async_db):
        from routes import documents

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r", "assigned_consultor_ids": ["u-cons"],
                                                  "consultant_id": "u-cons"})
        corre = AsyncMock()
        p1, p2, p3 = self._patches(fake_async_db, "consultor")
        with p1, p2, p3, patch.object(documents, "run_categorize_document", corre):
            with pytest.raises(HTTPException) as e:
                await documents.categorize_document(MagicMock(), PID, s3_path="a/b.pdf", filename="b.pdf", user=CONSULTOR)
        assert e.value.status_code == 403
        corre.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ai_analyze_review_recusa_o_consultor_e_nunca_corre(self, fake_async_db):
        from routes import documents

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r"})
        await fake_async_db.document_metadata.insert_one({"id": "d-1", "process_id": PID, "s3_path": "a/b.pdf"})
        corre = AsyncMock()
        p1, p2, p3 = self._patches(fake_async_db, "consultor")
        with p1, p2, p3, patch.object(document_review, "run_analyze_document_for_review", corre):
            with pytest.raises(HTTPException) as e:
                await documents.analyze_document_for_review(MagicMock(), "d-1", user=CONSULTOR)
        assert e.value.status_code == 403
        corre.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_contraprova_o_diretor_da_rede_passa_e_o_handler_corre(self, fake_async_db):
        from routes import documents

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r"})
        corre = AsyncMock(return_value={"ok": True})
        p1, p2, p3 = self._patches(fake_async_db, "diretor")
        with p1, p2, p3, patch.object(documents, "run_categorize_all_documents", corre):
            r = await documents.categorize_all_documents(MagicMock(), PID, user=GESTOR)
        assert r == {"ok": True}
        corre.assert_awaited_once()
        assert corre.await_args.kwargs["user"] == GESTOR  # o autor segue para o log

    @pytest.mark.asyncio
    async def test_o_diretor_de_OUTRA_rede_nao_passa(self, fake_async_db):
        from routes import documents

        await fake_async_db.processes.insert_one({"id": PID, "network_id": "r"})
        corre = AsyncMock()
        with patch("database.db", fake_async_db), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="diretor")), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=_ambito(("domus",)))), \
             patch.object(documents, "run_categorize_all_documents", corre):
            with pytest.raises(HTTPException) as e:
                await documents.categorize_all_documents(MagicMock(), PID, user=GESTOR)
        assert e.value.status_code == 403
        corre.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_processo_inexistente_e_404_e_nao_403(self, fake_async_db):
        with patch("database.db", fake_async_db):
            with pytest.raises(HTTPException) as e:
                await acesso.exigir_ia_no_processo_por_id(MagicMock(), GESTOR, "nao-existe")
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_documento_sem_processo_deixa_passar_ao_handler(self, fake_async_db):
        # O handler responde o 404/400 de sempre; um 403 aqui seria inventado.
        with patch("database.db", fake_async_db):
            assert await acesso.exigir_ia_no_documento(MagicMock(), CONSULTOR, "d-fantasma") is None


class TestInventarioDasRotasPagas:
    """Falha por OMISSÃO: uma rota de documentos que chame um serviço de IA sem a guarda."""

    ROTAS_COM_IA = {
        "categorize_document": "run_categorize_document",
        "categorize_all_documents": "run_categorize_all_documents",
        "analyze_document_for_review": "run_analyze_document_for_review",
    }

    def test_cada_rota_paga_chama_a_guarda_antes_do_servico(self):
        from routes import documents

        for handler, servico in self.ROTAS_COM_IA.items():
            fonte = codigo_sem_comentarios(inspect.getsource(getattr(documents, handler)))
            assert "exigir_ia_no_" in fonte, f"{handler} sem guarda de IA"
            assert fonte.index("exigir_ia_no_") < fonte.index(servico), f"{handler}: a guarda vem DEPOIS do serviço"

    def test_o_inventario_le_mesmo_o_modulo(self):
        from routes import documents

        arvore = ast.parse(inspect.getsource(documents))
        nomes = {n.name for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef)}
        assert set(self.ROTAS_COM_IA) <= nomes


class TestIndices:
    def test_o_ttl_e_o_indice_de_leitura_estao_declarados(self):
        from services import db_indexes

        ttl = [t for t in db_indexes.TTL_INDEXES if t["collection"] == "process_ai_log"]
        assert ttl and ttl[0]["field"] == "expire_at" and ttl[0]["seconds"] == 0
        nomes = [i["name"] for i in db_indexes.INDEX_DEFINITIONS.get("process_ai_log", [])]
        assert "idx_process_ai_log_processo" in nomes
