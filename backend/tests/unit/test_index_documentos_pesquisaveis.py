"""Declarações de efetividade, bancos dos extratos e a projecção pesquisável por documento (Out 2026).

Sem Mongo: a AI é a simulada e a projecção é uma função pura. O que precisa de um MongoDB real (o
`$lookup` à fronteira de processos, o `$facet`) está em `tests/integration/test_index_documentos_mongo.py`.
"""
from __future__ import annotations

import ast
import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

from services import index_advanced_search as pesquisa
from services import index_ai as ia
from services import index_store as store
from services.index_banks import banco_do_extrato, banco_do_iban, chave_do_banco, chave_do_filtro

SERVICOS = Path(__file__).resolve().parents[2] / "services"
HOJE = date(2026, 10, 15)


def _campo(v, c="alta"):
    return {"value": v, "confidence": c, "page": 1}


# ====================================================================
# BANCOS
# ====================================================================
class TestBancos:
    @pytest.mark.parametrize("texto,chave", [
        ("CGD", "cgd"), ("Caixa Geral de Depósitos, S.A.", "cgd"), ("caixa geral", "cgd"),
        ("Banco Santander Totta, S.A.", "santander"), ("Totta", "santander"), ("Santander", "santander"),
        ("Millennium bcp", "millennium"), ("BCP", "millennium"), ("ActivoBank", "activobank"),
        ("Activo Bank", "activobank"), ("Banco BPI", "bpi"), ("Novo Banco, S.A.", "novo_banco"),
        ("Crédito Agrícola", "credito_agricola"), ("Banco CTT", "banco_ctt"),
    ])
    def test_o_texto_impresso_e_o_pesquisado_dao_a_mesma_chave(self, texto, chave):
        assert chave_do_banco(texto) == chave
        assert chave_do_filtro(texto) == chave

    @pytest.mark.parametrize("texto", ["Besta Bank", "Bicicletas Lda", "Totalmente Outro", "", None, "   "])
    def test_so_casa_por_palavras_inteiras(self, texto):
        """`bes` não pode casar com «Besta» nem `totta` com «Totalmente»: um extrato no banco errado não dá erro."""
        assert chave_do_banco(texto) is None

    def test_o_alias_mais_longo_ganha(self):
        # «santander totta» tem de ser avaliado antes de «totta» (ambos são o mesmo banco, mas a ordem é a regra)
        assert chave_do_banco("Banco Santander Totta") == "santander"

    def test_a_ia_vence_o_iban(self):
        r = banco_do_extrato("Millennium bcp", "PT50003500000000000000000")  # IBAN de outro banco
        assert r == {"nome": "Millennium bcp", "chave": "millennium"}

    def test_sem_nome_o_iban_portugues_preenche(self):
        assert banco_do_extrato(None, "PT50 0035 0000 0000 0000 0000 0") == {
            "nome": "Caixa Geral de Depósitos", "chave": "cgd"}
        assert banco_do_iban("PT50003300000000000000000") == "millennium"

    @pytest.mark.parametrize("iban", [None, "", "ES9121000418450200051332", "PT50999900000000000000000", "PT50", "xx"])
    def test_iban_estrangeiro_ou_fora_da_tabela_nao_adivinha(self, iban):
        assert banco_do_iban(iban) is None
        assert banco_do_extrato(None, iban) == {"nome": None, "chave": None}

    def test_um_banco_fora_da_tabela_fica_pesquisavel_pelo_nome(self):
        r = banco_do_extrato("Banco Exemplo Regional, S.A.")
        assert r["nome"] == "Banco Exemplo Regional, S.A." and r["chave"].startswith("outro:")

    def test_o_nome_lido_e_limpo_e_cortado(self):
        r = banco_do_extrato("<b>Banco" + " Longo" * 40 + "</b>")
        assert "<" not in r["nome"] and len(r["nome"]) <= 80


# ====================================================================
# O ESQUEMA E A CLASSIFICAÇÃO
# ====================================================================
class TestTipoEEsquemas:
    @pytest.mark.parametrize("categoria,sub,nome", [
        ("Emprego", "Declaração de Efetividade", "doc.pdf"),
        (None, None, "declaracao_efetividade_empresa.pdf"),
        (None, None, "Declaração de Efectividade.pdf"),
        ("Financeiros", "Declaração da Entidade Patronal", "x.pdf"),
        (None, "Declaração de Vínculo", "x.pdf"),
    ])
    def test_reconhece_a_declaracao(self, categoria, sub, nome):
        assert ia.tipo_de_analise(categoria, sub, nome) == ia.TIPO_DECLARACAO

    def test_a_declaracao_e_um_tipo_analisado_e_tem_categoria(self):
        assert ia.TIPO_DECLARACAO in ia.TIPOS_ANALISADOS
        assert ia.CATEGORIA_DO_TIPO[ia.TIPO_DECLARACAO] == ia.CATEGORIA_DO_TIPO[ia.TIPO_RECIBO]

    def test_nao_confunde_os_outros_tipos(self):
        assert ia.tipo_de_analise("Financeiros", "Recibo de Vencimento", "r.pdf") == ia.TIPO_RECIBO
        assert ia.tipo_de_analise("Bancários", "Extrato Bancário", "e.pdf") == ia.TIPO_EXTRATO
        assert ia.tipo_de_analise(None, "Contrato de Trabalho", "c.pdf") is None

    def test_o_extrato_exige_o_banco_no_esquema_e_no_prompt(self):
        ferramenta = ia.definicao_da_ferramenta(ia.TIPO_EXTRATO)["function"]["parameters"]
        assert "bank_name" in ferramenta["properties"] and "bank_name" in ferramenta["required"]
        assert "bank_name" in ia.PROMPTS_POR_TIPO[ia.TIPO_EXTRATO]

    def test_o_esquema_da_declaracao_tem_o_que_foi_pedido_e_nada_do_trabalhador(self):
        props = ia.definicao_da_ferramenta(ia.TIPO_DECLARACAO)["function"]["parameters"]["properties"]
        assert {"employer_name", "employer_nif", "admission_date", "contract_type", "employer_location"} <= set(props)
        assert not {"worker_name", "employee_name", "nif_trabalhador", "document_number"} & set(props)
        assert set(props["contract_type"]["properties"]["value"]["enum"]) >= {"efetivo", "termo_certo", None}

    def test_o_esquema_nao_mudou_de_versao(self):
        """Decisão da direcção: sem reanálise retroactiva. Mudar a versão invalida TODAS as impressões."""
        assert ia.ESQUEMA_VERSAO == "2"
        assert ia.tem_a_impressao_atual("abc:2") and not ia.tem_a_impressao_atual("abc:1")


# ====================================================================
# NORMALIZAR
# ====================================================================
class TestNormalizarDeclaracao:
    def _bruto(self, **mudar):
        base = {
            "employer_nif": _campo("501964843"), "employer_name": _campo("Empresa Simulada, Lda"),
            "employer_location": _campo("Setúbal"), "admission_date": _campo("2022-03-01"),
            "contract_type": _campo("sem termo"), "job_title": _campo("Técnico"), "issue_date": _campo("2026-10-02"),
        }
        base.update(mudar)
        return base

    def test_extrai_o_pedido(self):
        f = ia.normalizar_declaracao(self._bruto(), document_id="d1")["factos"]
        assert f["tipo"] == ia.TIPO_DECLARACAO and f["document_id"] == "d1"
        assert (f["employer_nif"], f["nif_valido"], f["employer_name"]) == ("501964843", True, "Empresa Simulada, Lda")
        assert (f["admission_date"], f["contract_type"], f["employer_location"]) == ("2022-03-01", "efetivo", "Setúbal")
        assert f["period"] == "2026-10" and f["needs_review"] is False

    def test_nao_ha_nenhum_campo_do_trabalhador(self):
        f = ia.normalizar_declaracao(self._bruto(worker_name=_campo("Ana Segredo")), document_id="d1")["factos"]
        assert "Segredo" not in str(f)

    def test_admissao_posterior_a_emissao_nao_se_guarda(self):
        f = ia.normalizar_declaracao(self._bruto(admission_date=_campo("2027-01-01")))["factos"]
        assert f["admission_date"] is None

    def test_nif_sem_digito_de_controlo_vai_a_rever(self):
        f = ia.normalizar_declaracao(self._bruto(employer_nif=_campo("501964840")))["factos"]
        assert f["nif_valido"] is False and f["needs_review"] is True

    def test_confianca_baixa_vai_a_rever(self):
        assert ia.normalizar_declaracao(self._bruto(employer_name=_campo("X Lda", "baixa")))["factos"]["needs_review"]

    def test_lixo_do_modelo_nao_levanta(self):
        for bruto in ({}, None, {"admission_date": "ontem", "contract_type": 7}):
            f = ia.normalizar_declaracao(bruto)["factos"]
            assert f["admission_date"] is None

    def test_a_declaracao_nao_gera_emprego(self):
        r = ia.normalizar(ia.TIPO_DECLARACAO, ia.simular(ia.TIPO_DECLARACAO, "d.pdf", hoje=HOJE), document_id="d1", hoje=HOJE)
        assert r.ok and r.job is None and r.subtype == ia.SUBTIPO_DA_DECLARACAO


class TestNormalizarExtratoComBanco:
    def test_o_banco_do_extrato_e_guardado_canonico(self):
        f = ia.normalizar_extrato({"bank_name": _campo("Banco Santander Totta, S.A."), "movements": []})["factos"]
        assert (f["bank"], f["bank_key"]) == ("Santander", "santander")

    def test_sem_banco_lido_vale_o_iban_mas_o_iban_continua_a_ser_guardado_como_antes(self):
        f = ia.normalizar_extrato({"iban": _campo("PT50003500000000000000000"), "movements": []})["factos"]
        assert f["bank_key"] == "cgd"

    def test_sem_nada_o_banco_e_nulo_e_a_analise_nao_falha(self):
        f = ia.normalizar_extrato({"movements": []})["factos"]
        assert f["bank"] is None and f["bank_key"] is None

    def test_a_contraparte_continua_a_nao_ser_guardada(self):
        f = ia.normalizar_extrato({"bank_name": _campo("CGD"), "movements": [
            {"amount": 10, "kind": "credit", "counterpart": "Maria Segredo"}]})["factos"]
        assert "Segredo" not in str(f)


@pytest.mark.asyncio
class TestAnaliseSimulada:
    @pytest.mark.parametrize("tipo", ia.TIPOS_ANALISADOS)
    async def test_todos_os_tipos_analisam_em_dev(self, tipo):
        r = await ia.analisar_documento(tipo=tipo, conteudo=b"x", filename="f.pdf", hoje=HOJE, ambiente={})
        assert r.ok and r.origem == ia.ORIGEM_SIMULADA

    async def test_o_extrato_simulado_traz_banco(self):
        r = await ia.analisar_documento(tipo=ia.TIPO_EXTRATO, conteudo=b"x", filename="e.pdf", hoje=HOJE, ambiente={})
        assert r.factos["bank_key"] == "cgd"


# ====================================================================
# O QUE SE GRAVA NO FICHEIRO
# ====================================================================
class TestCamposDoFicheiro:
    def _resultado(self, tipo, **kw):
        return ia.normalizar(tipo, ia.simular(tipo, "f.pdf", hoje=HOJE), document_id="d1", hoje=HOJE)

    def test_a_declaracao_grava_subtipo_e_subcategoria(self):
        c = store.campos_do_ficheiro(self._resultado(ia.TIPO_DECLARACAO), "h:2")
        assert c["ai_subtype"] == "declaracao_efetividade"
        assert c["ai_subcategory"] == "Declaração de Efetividade"
        assert c["ai_category"] == "Financeiros" and c["index_job"] is None

    def test_o_recibo_e_o_extrato_continuam_sem_subtipo(self):
        assert store.campos_do_ficheiro(self._resultado(ia.TIPO_RECIBO), "h:2")["ai_subtype"] is None
        e = store.campos_do_ficheiro(self._resultado(ia.TIPO_EXTRATO), "h:2")
        assert e["ai_subtype"] is None and e["ai_subcategory"] == "Extrato Bancário"

    def test_a_identificacao_nao_mudou(self):
        c = store.campos_do_ficheiro(self._resultado(ia.TIPO_IDENTIFICACAO), "h:2")
        assert c["ai_subtype"] == "cc" and c["ai_category"] == "Identificação"


# ====================================================================
# A PROJECÇÃO POR DOCUMENTO
# ====================================================================
def _doc(doc_id, tipo, bruto=None, *, filename="joao_segredo.pdf"):
    r = ia.normalizar(tipo, bruto or ia.simular(tipo, filename, hoje=HOJE), document_id=doc_id, hoje=HOJE)
    return {"id": doc_id, "filename": filename, "process_id": "p1", **store.campos_do_ficheiro(r, "h:2")}


def _proj(doc, **kw):
    return store.projectar_documento(doc, process_id="p1", network_id="rede-A", **kw)


class TestProjectarDocumento:
    def test_recibo_traz_valor_numerico_localidade_e_contrato(self):
        recibo = _doc("r1", ia.TIPO_RECIBO)
        linha = _proj(recibo)
        assert linha["doc_type"] == "recibo" and linha["net_salary_num"] == 1000.0 and linha["net_salary"] == "1000.00"
        assert (linha["employer_location"], linha["contract_type"], linha["job_title"]) == ("Lisboa", "efetivo", "Técnico")
        assert linha["period"] and linha["bank_key"] is None

    def test_declaracao_traz_admissao_e_localidade(self):
        linha = _proj(_doc("d1", ia.TIPO_DECLARACAO))
        assert linha["doc_type"] == "declaracao_efetividade"
        assert linha["admission_date"] and linha["employer_location"] == "Lisboa" and linha["net_salary_num"] is None

    def test_extrato_traz_banco_e_periodo(self):
        linha = _proj(_doc("e1", ia.TIPO_EXTRATO))
        assert linha["doc_type"] == "extrato" and linha["bank_key"] == "cgd" and linha["bank"] == "Caixa Geral de Depósitos"
        assert linha["period"] == "2026-09" and linha["employer_nif"] is None

    def test_a_identificacao_nao_e_pesquisavel(self):
        assert _proj(_doc("i1", ia.TIPO_IDENTIFICACAO)) is None

    def test_sem_factos_ou_sem_id_nao_ha_linha(self):
        assert _proj({"id": "x"}) is None
        assert _proj({"index_facts": {"tipo": ia.TIPO_RECIBO}}) is None

    def test_nada_pessoal_na_linha(self):
        """Nem o nome do ficheiro (leva o nome do cliente), nem o IBAN, nem a contraparte."""
        extrato = _doc("e1", ia.TIPO_EXTRATO, {
            "bank_name": _campo("CGD"), "iban": _campo("PT50003500001234567890123"),
            "movements": [{"amount": 5, "kind": "credit", "counterpart": "Maria Segredo"}]})
        for doc in (_doc("r1", ia.TIPO_RECIBO), _doc("d1", ia.TIPO_DECLARACAO), extrato):
            texto = str(_proj(doc))
            assert "segredo" not in texto.lower() and "PT50" not in texto and "joao" not in texto.lower()

    def test_um_valor_ilegivel_nao_vira_zero(self):
        doc = _doc("r1", ia.TIPO_RECIBO)
        doc["index_facts"]["net"] = "abc"
        doc["index_job"]["net_salary"]["value"] = "abc"
        linha = _proj(doc)
        assert linha["net_salary_num"] is None and linha["net_salary"] is None

    def test_zero_e_um_valor_e_negativo_nao(self):
        doc = _doc("r1", ia.TIPO_RECIBO)
        doc["index_job"]["net_salary"]["value"] = "0.00"
        assert _proj(doc)["net_salary_num"] == 0.0

    def test_a_correccao_humana_do_nif_sobrepoe_se_a_leitura_da_ia(self):
        doc = _doc("r1", ia.TIPO_RECIBO)
        trabalho = {"employer_nif": {"value": "509442013", "edited_by_human": True},
                    "employer_name": {"value": "Lida Mal", "edited_by_human": False}}
        linha = _proj(doc, trabalho_do_documento=trabalho)
        assert linha["employer_nif"] == "509442013"
        assert linha["employer_name"] == "Empresa Simulada, Lda"  # só o que uma pessoa escreveu se sobrepõe

    def test_o_extrato_ignora_o_emprego(self):
        trabalho = {"employer_nif": {"value": "509442013", "edited_by_human": True}}
        assert _proj(_doc("e1", ia.TIPO_EXTRATO), trabalho_do_documento=trabalho)["employer_nif"] is None


class TestEntidadesDasDeclaracoes:
    def test_so_entra_nif_valido_com_nome_e_sem_duvida(self):
        bons = ia.normalizar_declaracao({"employer_nif": _campo("501964843"), "employer_name": _campo("Boa, Lda")})["factos"]
        invalido = ia.normalizar_declaracao({"employer_nif": _campo("501964840"), "employer_name": _campo("Má, Lda")})["factos"]
        duvida = ia.normalizar_declaracao({"employer_nif": _campo("509442013", "baixa"), "employer_name": _campo("X, Lda")})["factos"]
        sem_nome = ia.normalizar_declaracao({"employer_nif": _campo("501964843")})["factos"]
        recibo = {"tipo": ia.TIPO_RECIBO, "employer_nif": "501964843", "employer_name": "R", "nif_valido": True}
        assert store.entidades_das_declaracoes([bons, invalido, duvida, sem_nome, recibo]) == [
            ("501964843", "Boa, Lda")]


# ====================================================================
# OS FILTROS
# ====================================================================
def _validar(**kw):
    base = dict(min_salary=None, max_salary=None, contract_type=None, employer_nif=None, employer_name=None,
                employer_location=None, job_title=None, period_from=None, period_to=None, sort="period_desc")
    base.update(kw)
    return pesquisa.validar_filtros(**base)


class TestValidarFiltrosPorDocumento:
    def test_sem_tipo_continua_a_vista_por_emprego(self):
        assert _validar(min_salary=Decimal(1))["document_type"] is None

    def test_tipo_desconhecido_e_422(self):
        with pytest.raises(HTTPException) as e:
            _validar(document_type="contrato")
        assert e.value.status_code == 422

    @pytest.mark.parametrize("tipo,filtro", [
        ("extrato", {"min_salary": Decimal(1)}), ("extrato", {"employer_name": "Empresa"}),
        ("extrato", {"employer_location": "Lisboa"}), ("extrato", {"contract_type": ["efetivo"]}),
        ("declaracao_efetividade", {"min_salary": Decimal(1)}), ("declaracao_efetividade", {"bank": "cgd"}),
        ("recibo", {"bank": "cgd"}),
    ])
    def test_um_filtro_que_nao_existe_no_tipo_e_422_e_nao_uma_lista_vazia(self, tipo, filtro):
        with pytest.raises(HTTPException) as e:
            _validar(document_type=tipo, **filtro)
        assert e.value.status_code == 422 and "não se aplica" in e.value.detail

    def test_o_banco_sem_tipo_e_422(self):
        with pytest.raises(HTTPException) as e:
            _validar(bank="cgd")
        assert e.value.status_code == 422 and "extrato" in e.value.detail

    @pytest.mark.parametrize("tipo,filtro", [
        ("recibo", {"min_salary": Decimal(1), "max_salary": Decimal(2), "employer_location": "x1"}),
        ("declaracao_efetividade", {"employer_location": "Lisboa", "contract_type": ["efetivo"]}),
        ("extrato", {"bank": "cgd", "period_from": "2026-01"}),
    ])
    def test_as_combinacoes_validas_passam(self, tipo, filtro):
        assert _validar(document_type=tipo, **filtro)["document_type"] == tipo

    def test_banco_curto_demais_e_422(self):
        with pytest.raises(HTTPException):
            _validar(document_type="extrato", bank="x")

    def test_valor_exacto_e_minimo_igual_ao_maximo(self):
        f = _validar(document_type="recibo", min_salary=Decimal("1234.56"), max_salary=Decimal("1234.56"))
        pipe = pesquisa.construir_pipeline_de_documentos(f, [], {}, pagina=1, tamanho=10)
        condicoes = pipe[0]["$match"]["$and"]
        assert {"net_salary_num": {"$ne": None, "$gte": 1234.56, "$lte": 1234.56}} in condicoes


class TestPipelineDeDocumentos:
    def _pipe(self, **kw):
        f = _validar(**kw)
        return pesquisa.construir_pipeline_de_documentos(f, [], {"network_id": {"$in": ["rede-A"]}}, pagina=2, tamanho=7)

    def test_filtra_primeiro_pelo_tipo_e_so_depois_resolve_o_processo(self):
        pipe = self._pipe(document_type="declaracao_efetividade", employer_location="Lisboa")
        assert pipe[0]["$match"]["$and"][0] == {"doc_type": "declaracao_efetividade"}
        assert "$lookup" in pipe[1] and pipe[2] == {"$match": {"proc.0": {"$exists": True}}}

    def test_a_fronteira_de_processos_e_aplicada_e_os_eliminados_ficam_fora(self):
        pipe = self._pipe(document_type="recibo")
        interno = pipe[1]["$lookup"]["pipeline"][0]["$match"]["$and"]
        assert {"is_deleted": {"$ne": True}} in interno and {"network_id": {"$in": ["rede-A"]}} in interno

    def test_o_banco_conhecido_compara_pela_chave(self):
        pipe = self._pipe(document_type="extrato", bank="caixa geral")
        ou = next(c["$or"] for c in pipe[0]["$match"]["$and"] if "$or" in c)
        assert {"bank_key": "cgd"} in ou

    def test_o_banco_desconhecido_pesquisa_se_pelo_nome_sem_expressao_regular_do_utilizador(self):
        pipe = self._pipe(document_type="extrato", bank="Banco (Ex.*)")
        cond = next(c for c in pipe[0]["$match"]["$and"] if "bank" in c)
        # parêntese, ponto e asterisco chegam escapados: o texto do utilizador nunca é uma expressão regular
        assert r"\(" in cond["bank"]["$regex"] and r"\.\*" in cond["bank"]["$regex"]
        assert cond["bank"]["$options"] == "i"

    def test_paginacao_e_projeccao(self):
        facet = self._pipe(document_type="recibo")[-1]["$facet"]
        assert facet["items"][1] == {"$skip": 7} and facet["items"][2] == {"$limit": 7}
        projeccao = facet["items"][3]["$project"]
        assert "filename" not in projeccao and "client_name" not in projeccao


class TestResultadoDoDocumento:
    def _linha(self, tipo):
        base = _proj(_doc("x", {"recibo": ia.TIPO_RECIBO, "declaracao_efetividade": ia.TIPO_DECLARACAO,
                               "extrato": ia.TIPO_EXTRATO}[tipo]))
        return {**base, "proc": {"process_number": 7, "company_name": "Casa"}}

    def test_recibo(self):
        r = pesquisa.resultado_do_documento(self._linha("recibo"))
        assert r["net_salary"] == 1000.0 and "bank" not in r and "admission_date" not in r
        assert r["employer"]["location"] == "Lisboa" and r["process_number"] == 7

    def test_declaracao(self):
        r = pesquisa.resultado_do_documento(self._linha("declaracao_efetividade"))
        assert r["admission_date"] and "net_salary" not in r and "bank" not in r

    def test_extrato_so_tem_o_banco(self):
        r = pesquisa.resultado_do_documento(self._linha("extrato"))
        assert r["bank"] == "Caixa Geral de Depósitos" and "employer" not in r and "net_salary" not in r

    def test_nunca_leva_dados_do_cliente_nem_o_ficheiro(self):
        for tipo in ("recibo", "declaracao_efetividade", "extrato"):
            texto = str(pesquisa.resultado_do_documento(self._linha(tipo))).lower()
            assert "segredo" not in texto and "filename" not in texto


# ====================================================================
# LIGAÇÕES (guardas de fonte, cada uma com a sua contraprova)
# ====================================================================
def _corpo(modulo, nome):
    arvore = ast.parse((SERVICOS / modulo).read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nome)


def _chama(fn, nome):
    return any(isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", None)) == nome for n in ast.walk(fn))


class TestLigacoes:
    def test_a_conclusao_da_analise_reconstroi_a_projeccao(self):
        assert _chama(_corpo("index_jobs.py", "concluir_resultados"), "reconstruir_documentos_do_index")

    def test_a_edicao_humana_tambem_a_reconstroi(self):
        assert _chama(_corpo("index_store.py", "editar_trabalho"), "reconstruir_documentos_do_index")

    def test_as_declaracoes_alimentam_o_directorio(self):
        assert _chama(_corpo("index_jobs.py", "concluir_resultados"), "entidades_das_declaracoes")

    def test_contraprova_o_detector_ve_uma_chamada_que_existe_e_uma_que_nao(self):
        fn = ast.parse("async def f():\n    await store.x()\n").body[0]
        assert _chama(fn, "x") and not _chama(fn, "y")

    def test_o_indice_da_projeccao_esta_declarado(self):
        from services.db_indexes import INDEX_DEFINITIONS

        nomes = {i["name"] for i in INDEX_DEFINITIONS["process_index_documents"]}
        assert {"idx_index_docs_id", "idx_index_docs_processo", "idx_index_docs_valor", "idx_index_docs_banco"} <= nomes
        assert next(i for i in INDEX_DEFINITIONS["process_index_documents"] if i["name"] == "idx_index_docs_id")["unique"]

    def test_a_rota_aceita_os_filtros_novos(self):
        from routes.index_module import advanced_search

        assert {"document_type", "bank"} <= set(inspect.signature(advanced_search).parameters)
