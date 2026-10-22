"""Pesquisa avançada POR DOCUMENTO contra um MongoDB REAL (Out 2026): declarações, recibos isolados, extratos.

Os dados nascem da cadeia de produção — os normalizadores de `index_ai`, `campos_do_ficheiro` e
`reconstruir_documentos_do_index` — e nunca de linhas escritas à mão na colecção pesquisada: um fixture que
escrevesse a projecção validaria o fixture.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from services import index_advanced_search as pesquisa
from services import index_ai as ia
from services import index_store as store
from services.tenant_network import TenantScope

pytestmark = pytest.mark.asyncio

USER = {"id": "u-index", "name": "Ivo", "role": "indexacao"}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_index_docs_{uuid.uuid4().hex[:8]}"]
    monkeypatch.setattr(store, "db", base)
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _ambito(*redes):
    return patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=TenantScope(network_ids=redes)))


def _c(v, conf="alta"):
    return {"value": v, "confidence": conf, "page": 1}


def _recibo(liquido, periodo, *, local="Lisboa", nif="501964843", nome="Empresa Simulada, Lda", contrato="efetivo", cargo="Técnico"):
    return {"employer_nif": _c(nif), "employer_name": _c(nome), "employer_location": _c(local), "job_title": _c(cargo),
            "contract_type": _c(contrato), "net_salary": _c(liquido), "period": _c(periodo)}


def _declaracao(local, *, nif="501964843", nome="Empresa Simulada, Lda", contrato="efetivo", admissao="2021-05-03", emissao="2026-10-01"):
    return {"employer_nif": _c(nif), "employer_name": _c(nome), "employer_location": _c(local),
            "admission_date": _c(admissao), "contract_type": _c(contrato), "issue_date": _c(emissao)}


def _extrato(banco, *, iban=None, inicio="2026-09-01"):
    return {"bank_name": _c(banco), "iban": _c(iban), "period_start": _c(inicio), "period_end": _c("2026-09-28"),
            "movements": [{"amount": 10, "kind": "credit", "counterpart": "Maria Segredo"}]}


async def _ficheiro(bd, doc_id, processo, tipo, bruto, *, filename="cliente_segredo.pdf"):
    resultado = ia.normalizar(tipo, bruto, document_id=doc_id)
    assert resultado.ok
    await bd.document_metadata.insert_one(
        {"id": doc_id, "process_id": processo, "filename": filename, **store.campos_do_ficheiro(resultado, "h:2")})


async def _semear(bd):
    await bd.processes.insert_many([
        {"id": "a1", "network_id": "rede-A", "process_number": 101, "is_deleted": False, "client_name": "Ana Segredo"},
        {"id": "a2", "network_id": "rede-A", "process_number": 102, "is_deleted": False},
        {"id": "b1", "network_id": "rede-B", "process_number": 201, "is_deleted": False},
        {"id": "a3", "network_id": "rede-A", "process_number": 103, "is_deleted": True},
        {"id": "b2", "network_id": "rede-B", "process_number": 202, "is_deleted": False, "partner_network_ids": ["rede-A"]},
    ])
    # a1: três recibos da MESMA entidade — o emprego agregado mostra só o mais recente (1500)
    await _ficheiro(bd, "r-a1-jul", "a1", ia.TIPO_RECIBO, _recibo("1200.00", "2026-07"))
    await _ficheiro(bd, "r-a1-ago", "a1", ia.TIPO_RECIBO, _recibo("900.00", "2026-08"))
    await _ficheiro(bd, "r-a1-set", "a1", ia.TIPO_RECIBO, _recibo("1500.00", "2026-09"))
    await _ficheiro(bd, "d-a1", "a1", ia.TIPO_DECLARACAO, _declaracao("Lisboa"))
    await _ficheiro(bd, "e-a1", "a1", ia.TIPO_EXTRATO, _extrato("Caixa Geral de Depósitos, S.A."))
    await _ficheiro(bd, "r-a2", "a2", ia.TIPO_RECIBO, _recibo("1234.56", "2026-09", local="Setúbal", nif="509442013", nome="Outra SA"))
    await _ficheiro(bd, "d-a2", "a2", ia.TIPO_DECLARACAO, _declaracao("Setúbal", nif="509442013", nome="Outra SA", contrato="termo_certo"))
    await _ficheiro(bd, "e-a2", "a2", ia.TIPO_EXTRATO, _extrato("Banco Santander Totta"))
    await _ficheiro(bd, "e-a2-2", "a2", ia.TIPO_EXTRATO, _extrato("Banco Exemplo Regional", inicio="2026-08-01"))
    await _ficheiro(bd, "d-b1", "b1", ia.TIPO_DECLARACAO, _declaracao("Lisboa"))
    await _ficheiro(bd, "e-b1", "b1", ia.TIPO_EXTRATO, _extrato("CGD"))
    await _ficheiro(bd, "r-b1", "b1", ia.TIPO_RECIBO, _recibo("1234.56", "2026-09"))
    await _ficheiro(bd, "d-a3", "a3", ia.TIPO_DECLARACAO, _declaracao("Lisboa"))
    await _ficheiro(bd, "d-b2", "b2", ia.TIPO_DECLARACAO, _declaracao("Faro"))
    await _ficheiro(bd, "i-a1", "a1", ia.TIPO_IDENTIFICACAO, ia.simular(ia.TIPO_IDENTIFICACAO, "cc.jpg"))
    for processo, rede in (("a1", "rede-A"), ("a2", "rede-A"), ("b1", "rede-B"), ("a3", "rede-A"), ("b2", "rede-B")):
        await store.reconstruir_documentos_do_index(processo, rede)


async def _procurar(rede="rede-A", **filtros):
    with _ambito(rede):
        return await pesquisa.run_advanced_search(USER, **filtros)


def _ids(r):
    return sorted(i["document_id"] for i in r["items"])


class TestCenario1DeclaracoesPorRegiao:
    async def test_declaracoes_de_uma_localidade_dentro_do_ambito(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="declaracao_efetividade", employer_location="lisboa")
        # d-b1 é da rede B (não partilhada); d-a3 está eliminado
        assert _ids(r) == ["d-a1"] and r["total"] == 1 and r["view"] == "documents"

    async def test_sem_localidade_lista_todas_as_do_ambito_incluindo_a_partilhada(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="declaracao_efetividade")
        assert _ids(r) == ["d-a1", "d-a2", "d-b2"]

    async def test_acentos_e_maiusculas_nao_importam(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(document_type="declaracao_efetividade", employer_location="SETUBAL")) == ["d-a2"]

    async def test_o_que_a_declaracao_certifica_vem_no_resultado(self, bd):
        await _semear(bd)
        item = (await _procurar(document_type="declaracao_efetividade", employer_location="setubal"))["items"][0]
        assert item["admission_date"] == "2021-05-03" and item["contract_type"] == "termo_certo"
        assert item["employer"] == {"nif": "509442013", "name": "Outra SA", "location": "Setúbal"}

    async def test_cruza_com_o_tipo_de_contrato(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="declaracao_efetividade", contract_type=["termo_certo"])
        assert _ids(r) == ["d-a2"]

    async def test_a_declaracao_nao_aparece_nos_outros_tipos(self, bd):
        await _semear(bd)
        for tipo in ("recibo", "extrato"):
            assert not [i for i in (await _procurar(document_type=tipo))["items"] if i["document_id"].startswith("d-")]


class TestCenario2RecibosPorValor:
    async def test_um_recibo_antigo_encontra_se_mesmo_que_o_emprego_ja_ganhe_mais(self, bd):
        """O emprego de a1 mostra 1500 (o recibo mais recente): o de 1200 só se acha por documento."""
        await _semear(bd)
        por_emprego = await _procurar(min_salary=1200, max_salary=1200)
        assert [i for i in por_emprego["items"] if i["process_id"] == "a1"] == []
        r = await _procurar(document_type="recibo", min_salary=1200, max_salary=1200)
        assert _ids(r) == ["r-a1-jul"]

    async def test_valor_exacto_com_centimos(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="recibo", min_salary=1234.56, max_salary=1234.56)
        assert _ids(r) == ["r-a2"]  # r-b1 tem o mesmo valor mas é da rede B

    async def test_intervalo(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(document_type="recibo", min_salary=1000, max_salary=1300)) == ["r-a1-jul", "r-a2"]

    async def test_900_nao_e_maior_do_que_1500(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="recibo", min_salary=1000)
        assert "r-a1-ago" not in _ids(r) and {"r-a1-set", "r-a1-jul", "r-a2"} <= set(_ids(r))

    async def test_ordena_por_valor(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="recibo", sort="salary_asc")
        assert [i["net_salary"] for i in r["items"]] == [900.0, 1200.0, 1234.56, 1500.0]

    async def test_cruza_valor_com_localidade_no_mesmo_recibo(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="recibo", min_salary=1000, employer_location="Setúbal")
        assert _ids(r) == ["r-a2"]

    async def test_o_periodo_filtra_recibos(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(document_type="recibo", period_from="2026-08", period_to="2026-08")) == ["r-a1-ago"]


class TestCenario3ExtratosPorBanco:
    @pytest.mark.parametrize("texto", ["cgd", "CGD", "caixa geral", "Caixa Geral de Depósitos"])
    async def test_o_mesmo_banco_escrito_de_varias_maneiras(self, bd, texto):
        await _semear(bd)
        assert _ids(await _procurar(document_type="extrato", bank=texto)) == ["e-a1"]  # e-b1 é da rede B

    async def test_santander(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(document_type="extrato", bank="santander")) == ["e-a2"]

    async def test_banco_fora_da_tabela_pesquisa_se_pelo_nome(self, bd):
        await _semear(bd)
        r = await _procurar(document_type="extrato", bank="exemplo regional")
        assert _ids(r) == ["e-a2-2"] and r["items"][0]["bank"] == "Banco Exemplo Regional"

    async def test_sem_banco_lista_os_extratos(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(document_type="extrato")) == ["e-a1", "e-a2", "e-a2-2"]

    async def test_o_banco_e_o_periodo_cruzam(self, bd):
        await _semear(bd)
        assert _ids(await _procurar(document_type="extrato", period_from="2026-09")) == ["e-a1", "e-a2"]

    async def test_a_rede_b_ve_o_seu_banco(self, bd):
        await _semear(bd)
        assert _ids(await _procurar("rede-B", document_type="extrato", bank="cgd")) == ["e-b1"]

    async def test_filtro_que_nao_se_aplica_e_422(self, bd):
        await _semear(bd)
        with pytest.raises(HTTPException) as e:
            await _procurar(document_type="recibo", bank="cgd")
        assert e.value.status_code == 422


class TestAFronteiraEOQueNaoSai:
    async def test_so_processos_vivos_e_do_ambito(self, bd):
        await _semear(bd)
        for tipo in ("recibo", "declaracao_efetividade", "extrato"):
            ids = _ids(await _procurar(document_type=tipo))
            assert not any(i.endswith(("-b1", "-a3")) or i == "d-b1" for i in ids), (tipo, ids)

    async def test_a_resposta_nao_leva_cliente_nem_ficheiro_nem_contraparte(self, bd):
        await _semear(bd)
        for tipo in ("recibo", "declaracao_efetividade", "extrato"):
            texto = str(await _procurar(document_type=tipo)).lower()
            assert "segredo" not in texto and "filename" not in texto and "client_name" not in texto

    async def test_a_identificacao_nunca_aparece(self, bd):
        await _semear(bd)
        assert not await bd.process_index_documents.find_one({"id": "i-a1"})

    async def test_a_colecao_pesquisavel_nao_guarda_nome_de_ficheiro_nem_iban(self, bd):
        await _semear(bd)
        await _ficheiro(bd, "e-iban", "a1", ia.TIPO_EXTRATO, _extrato("CGD", iban="PT50003500001234567890123"))
        await store.reconstruir_documentos_do_index("a1", "rede-A")
        for linha in await bd.process_index_documents.find({}).to_list(100):
            texto = str(linha).lower()
            assert "segredo" not in texto and "pt50" not in texto and "filename" not in linha

    async def test_a_vista_por_emprego_continua_igual(self, bd):
        await _semear(bd)
        await bd.process_professional_metadata.insert_one({"process_id": "a1", "network_id": "rede-A", "jobs": []})
        r = await _procurar()
        assert r["view"] == "jobs" and r["items"] == []


class TestAProjeccaoRecalcula:
    async def test_idempotente(self, bd):
        await _semear(bd)
        antes = await bd.process_index_documents.count_documents({})
        await store.reconstruir_documentos_do_index("a1", "rede-A")
        await store.reconstruir_documentos_do_index("a1", "rede-A")
        assert await bd.process_index_documents.count_documents({}) == antes

    async def test_um_ficheiro_apagado_deixa_de_constar(self, bd):
        await _semear(bd)
        await bd.document_metadata.delete_one({"id": "r-a1-jul"})
        assert await store.reconstruir_documentos_do_index("a1", "rede-A") == 4  # 3 recibos − 1 + declaração + extrato (a identificação não é pesquisável)
        assert _ids(await _procurar(document_type="recibo", min_salary=1200, max_salary=1200)) == []

    async def test_um_original_purgado_continua_a_contar(self, bd):
        await _semear(bd)
        await bd.document_metadata.update_one({"id": "r-a1-jul"}, {"$set": {"file_state": "purgado"}})
        await store.reconstruir_documentos_do_index("a1", "rede-A")
        assert _ids(await _procurar(document_type="recibo", min_salary=1200, max_salary=1200)) == ["r-a1-jul"]

    async def test_o_pdf_limpo_nao_conta_duas_vezes(self, bd):
        await _semear(bd)
        await bd.document_metadata.update_one({"id": "r-a1-jul"}, {"$set": {"is_clean_pdf": True}})
        await store.reconstruir_documentos_do_index("a1", "rede-A")
        assert await bd.process_index_documents.find_one({"id": "r-a1-jul"}) is None

    async def test_a_correccao_humana_do_nif_chega_a_pesquisa(self, bd):
        await _semear(bd)
        await store.recalcular_metadados("a2", "rede-A", "imp")
        job = (await store.carregar_metadados("a2"))["jobs"][0]
        await store.editar_trabalho("a2", "rede-A", job["job_id"], {"employer_nif": "501964843"})
        r = await _procurar(document_type="recibo", employer_nif="501964843", min_salary=1234.56, max_salary=1234.56)
        assert _ids(r) == ["r-a2"]

    async def test_uma_falha_nunca_levanta(self, bd, monkeypatch):
        await _semear(bd)

        async def rebenta(*a, **k):
            raise RuntimeError("mongo caiu")

        monkeypatch.setattr(store, "carregar_metadados", rebenta)
        assert await store.reconstruir_documentos_do_index("a1", "rede-A") == 0


class TestOFimDaCadeia:
    async def test_concluir_resultados_alimenta_a_pesquisa_e_o_directorio(self, bd, monkeypatch):
        """O elo que um fixture da projecção não prova: a conclusão da análise chama a reconstrução."""
        from services import index_jobs

        monkeypatch.setattr(index_jobs, "store", store)
        monkeypatch.setattr(index_jobs, "db", bd)  # cada módulo tem a SUA referência ao proxy da base de dados
        await bd.processes.insert_one({"id": "z1", "network_id": "rede-A", "process_number": 1, "is_deleted": False})
        await _ficheiro(bd, "d-z1", "z1", ia.TIPO_DECLARACAO, _declaracao("Braga", nif="500000000", nome="Nova Entidade, Lda"))
        with patch.object(index_jobs, "gravar_contadores", AsyncMock()):
            await index_jobs.concluir_resultados({"id": "z1", "network_id": "rede-A"}, {})
        assert _ids(await _procurar(document_type="declaracao_efetividade", employer_location="braga")) == ["d-z1"]
        assert await bd.employers.find_one({"nif": "500000000"}) is not None


class TestBackfill:
    async def test_o_resumo_conta_o_que_a_escrita_produziria(self, bd):
        from scripts.backfill_index_documentos import resumir

        await _semear(bd)
        docs = await bd.document_metadata.find({"index_facts": {"$exists": True}}).to_list(100)
        r = resumir(docs)
        assert r["por_tipo"] == {"recibo": 5, "declaracao_efetividade": 5, "extrato": 4}  # a identificação não conta
        assert r["linhas"] == 14 and r["extratos_com_banco"] == 4 and r["recibos_com_localidade"] == 5
