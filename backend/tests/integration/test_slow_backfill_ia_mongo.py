"""Reanálise retroactiva LENTA do Index (Out 2026) — MongoDB real.

Real porque o que se afirma é a semântica do selector sobre campos AUSENTES/nulos e subdocumentos, a reserva
atómica, o `$set` pontual por caminho com ponto e a ordem de saída dos candidatos: o duplo em memória não prova
nada disto. Os documentos «antigos» nascem da cadeia de produção (normalizadores + `campos_do_ficheiro`) sem o
banco/localidade; o S3 e o modelo são as duas FRONTEIRAS falseadas, ao nível em que a produção as chama.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import index_advanced_search as pesquisa
from services import index_ai as ia
from services import index_jobs as jobs
from services import index_slow_backfill as sb
from services import index_status as ist
from services import index_store as store
from services import process_ai_log as log_da_ia
from services.tenant_network import TenantScope

pytestmark = pytest.mark.asyncio

USER = {"id": "u-index", "name": "Ivo", "role": "indexacao"}
CONTEUDO = {}  # s3_path → bytes


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_slow_backfill_{uuid.uuid4().hex[:8]}"]
    for modulo in (sb, store, jobs, ist, log_da_ia):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.setenv("INDEX_AI_PROVIDER", "openai")
    monkeypatch.setenv("SLOW_BACKFILL_PAUSE_SECONDS", "0")
    CONTEUDO.clear()
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _c(v, conf="alta"):
    return {"value": v, "confidence": conf, "page": 1}


def _bruto_extrato(banco=None, iban=None):
    base = {"period_start": _c("2026-09-01"), "period_end": _c("2026-09-30"), "opening_balance": _c(500), "closing_balance": _c(800),
            "movements": [{"date": "2026-09-05", "description": "Pagamento", "amount": 300, "balance": 800}]}
    if banco:
        base["bank_name"] = _c(banco)
    if iban:
        base["iban"] = _c(iban)
    return base


def _bruto_recibo(local=None, contrato="efetivo"):
    return {"employer_nif": _c("501964843"), "employer_name": _c("Empresa Simulada, Lda"), "employer_location": _c(local),
            "job_title": _c("Técnico"), "contract_type": _c(contrato), "net_salary": _c(1234.56), "period": _c("2026-09")}


async def _processo(bd, pid="p1", rede="rede-A", **extra):
    await bd.processes.insert_one({"id": pid, "network_id": rede, "client_name": "Cliente", "is_deleted": False,
                                   "status": "novo", **extra})


async def _documento(bd, doc_id, tipo, bruto, *, pid="p1", analisado="2026-08-01T10:00:00+00:00", bytes_=None, **extra):
    """Um documento analisado como as análises ANTIGAS o deixaram (sem banco / sem localidade)."""
    bytes_ = bytes_ or f"conteudo-{doc_id}".encode()
    chave = f"Documentação Clientes/c1/processos/{pid}/{doc_id}.pdf"
    CONTEUDO[chave] = bytes_
    resultado = ia.normalizar(tipo, bruto, document_id=doc_id)
    campos = store.campos_do_ficheiro(resultado, ia.impressao_digital(bytes_))
    campos["index_analyzed_at"] = analisado
    await bd.document_metadata.insert_one({"id": doc_id, "process_id": pid, "filename": f"{doc_id}.pdf", "s3_path": chave, **campos, **extra})


def _s3():
    async def ler(chave):
        return CONTEUDO[chave], "application/pdf"
    return patch("services.document_vision_extract.ler_ficheiro_do_s3", AsyncMock(side_effect=ler))


def _modelo(respostas):
    """O modelo falseado AO NÍVEL DA CHAMADA: devolve `respostas[i]` à i-ésima chamada (ou levanta)."""
    fila = list(respostas)
    chamada = AsyncMock(side_effect=lambda **kw: _proxima(fila))
    return chamada


def _proxima(fila):
    r = fila.pop(0) if len(fila) > 1 else fila[0]
    if isinstance(r, Exception):
        raise r
    return {"data": r, "model": "modelo-teste"}


async def _correr(bd, *, tamanho=20, respostas, **kw):
    chamada = _modelo(respostas)
    with _s3(), patch("services.index_ai._mensagens", return_value=([{"role": "system", "content": "p"}], False, 60.0)), \
            patch("services.ai_document.call_openai_api", chamada):
        resumo = await sb.correr_lote(tamanho=tamanho, pausa=0, escrever=lambda _l: None, **kw)
    return resumo, chamada


async def _doc(bd, doc_id):
    return await bd.document_metadata.find_one({"id": doc_id}, {"_id": 0})


class TestOQueSePreenche:
    async def test_o_banco_de_um_extrato_antigo(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        antes = await _doc(bd, "e1")
        assert not antes["index_facts"]["bank_key"]

        resumo, chamada = await _correr(bd, respostas=[_bruto_extrato(banco="Caixa Geral de Depósitos, S.A.")])
        depois = await _doc(bd, "e1")

        assert resumo["por_estado"] == {"preenchido": 1} and chamada.await_count == 1
        assert depois["index_facts"]["bank_key"] == "cgd" and depois["index_facts"]["bank"] == "Caixa Geral de Depósitos"
        # a impressão digital NÃO mudou — é ela que faz a análise normal saltar este ficheiro
        assert depois["analysis_fingerprint"] == antes["analysis_fingerprint"]
        # e nada mais do documento mudou: só o banco (o resto dos factos é o que estava)
        for campo in ("iban", "period_start", "period_end", "opening", "closing", "movimentos", "achados", "tipo"):
            assert depois["index_facts"][campo] == antes["index_facts"][campo], campo
        assert depois["index_job"] == antes["index_job"] and depois["index_analyzed_at"] == antes["index_analyzed_at"]
        assert depois[sb.CAMPO_DA_MARCA]["estado"] == "preenchido"
        assert "reservado_ate" not in depois[sb.CAMPO_DA_MARCA]

    async def test_a_localidade_de_um_recibo_antigo_chega_ao_emprego_e_a_pesquisa(self, bd):
        await _processo(bd)
        await _documento(bd, "r1", ia.TIPO_RECIBO, _bruto_recibo())
        await store.recalcular_metadados("p1", "rede-A", "x")
        assert (await store.carregar_metadados("p1"))["jobs"][0].get("employer_location") is None

        resumo, _ = await _correr(bd, respostas=[_bruto_recibo(local="Setúbal")])
        assert resumo["por_estado"] == {"preenchido": 1} and resumo["recalculados"] == 1

        doc = await _doc(bd, "r1")
        assert doc["index_job"]["employer_location"] == "Setúbal"
        assert (await store.carregar_metadados("p1"))["jobs"][0]["employer_location"] == "Setúbal"
        linha = await bd.process_index_documents.find_one({"id": "r1"}, {"_id": 0})
        assert linha["employer_location"] == "Setúbal"

        # e AGORA a pesquisa avançada por localidade encontra o que antes não encontrava
        with patch("services.tenant_network.resolve_tenant_scope", AsyncMock(return_value=TenantScope(network_ids=("rede-A",)))), \
                patch("services.index_advanced_search.build_tenant_process_condition", AsyncMock(return_value={"network_id": "rede-A"})):
            r = await pesquisa.run_advanced_search(USER, document_type="recibo", employer_location="setubal")
        assert [i["document_id"] for i in r["items"]] == ["r1"]

    async def test_a_correccao_humana_do_emprego_sobrevive(self, bd):
        await _processo(bd)
        await _documento(bd, "r1", ia.TIPO_RECIBO, _bruto_recibo(contrato="outro"))
        await store.recalcular_metadados("p1", "rede-A", "x")
        meta = await store.carregar_metadados("p1")
        meta["jobs"][0]["contract_type"].update(value="efetivo", edited_by_human=True)
        await bd.process_professional_metadata.update_one({"process_id": "p1"}, {"$set": {"jobs": meta["jobs"]}})

        await _correr(bd, respostas=[_bruto_recibo(local="Porto", contrato="outro")])
        job = (await store.carregar_metadados("p1"))["jobs"][0]
        assert job["contract_type"]["value"] == "efetivo" and job["employer_location"] == "Porto"

    async def test_so_o_campo_que_falta_nunca_o_resto_da_releitura(self, bd):
        """O modelo lê agora OUTRO líquido: o valor guardado (que alguém pode ter conferido) não muda."""
        await _processo(bd)
        await _documento(bd, "r1", ia.TIPO_RECIBO, _bruto_recibo())
        antes = await _doc(bd, "r1")
        outro = _bruto_recibo(local="Faro")
        outro["net_salary"] = _c(9999)
        await _correr(bd, respostas=[outro])
        depois = await _doc(bd, "r1")
        assert depois["index_job"]["net_salary"] == antes["index_job"]["net_salary"]
        assert depois["index_facts"] == antes["index_facts"]


class TestSoOsCandidatos:
    async def test_quem_nao_e_candidato_nao_gasta_chamadas(self, bd):
        await _processo(bd)
        await _documento(bd, "tem-banco", ia.TIPO_EXTRATO, _bruto_extrato(banco="CGD"))
        await _documento(bd, "tem-local", ia.TIPO_RECIBO, _bruto_recibo(local="Lisboa"))
        await _documento(bd, "purgado", ia.TIPO_EXTRATO, _bruto_extrato(), file_state="purgado")
        await _documento(bd, "limpo", ia.TIPO_EXTRATO, _bruto_extrato(), is_clean_pdf=True)
        await _documento(bd, "sem-chave", ia.TIPO_EXTRATO, _bruto_extrato())
        await bd.document_metadata.update_one({"id": "sem-chave"}, {"$set": {"s3_path": ""}})
        await _documento(bd, "declaracao", ia.TIPO_DECLARACAO, {
            "employer_nif": _c("501964843"), "employer_name": _c("X, Lda"), "admission_date": _c("2021-01-01"),
            "contract_type": _c("efetivo"), "issue_date": _c("2026-10-01")})
        await _documento(bd, "ident", ia.TIPO_IDENTIFICACAO, {"document_subtype": _c("cc")})
        resumo, chamada = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert resumo["candidatos"] == 0 and chamada.await_count == 0
        assert await sb.contar_candidatos() == {"banco": 0, "localidade": 0}

    async def test_um_recibo_com_index_job_nulo_nao_rebenta_o_lote(self, bd):
        await _processo(bd)
        await _documento(bd, "r-nulo", ia.TIPO_RECIBO, _bruto_recibo())
        await bd.document_metadata.update_one({"id": "r-nulo"}, {"$set": {"index_job": None}})
        resumo, chamada = await _correr(bd, respostas=[_bruto_recibo(local="Faro")])
        assert resumo["candidatos"] == 0 and chamada.await_count == 0

    async def test_o_campo_vazio_ou_ausente_ambos_contam(self, bd):
        await _processo(bd)
        await _documento(bd, "e-vazio", ia.TIPO_EXTRATO, _bruto_extrato())
        await bd.document_metadata.update_one({"id": "e-vazio"}, {"$set": {"index_facts.bank_key": ""}})
        await _documento(bd, "e-ausente", ia.TIPO_EXTRATO, _bruto_extrato())
        await bd.document_metadata.update_one({"id": "e-ausente"}, {"$unset": {"index_facts.bank_key": ""}})
        assert (await sb.contar_candidatos())["banco"] == 2

    async def test_um_processo_eliminado_ou_inexistente_nao_gasta_a_chamada(self, bd):
        await _processo(bd, "eliminado", is_deleted=True)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato(), pid="eliminado")
        await _documento(bd, "e2", ia.TIPO_EXTRATO, _bruto_extrato(), pid="nao-existe")
        resumo, chamada = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert resumo["por_estado"] == {"sem_processo": 2} and chamada.await_count == 0
        assert (await _doc(bd, "e1"))[sb.CAMPO_DA_MARCA]["estado"] == "sem_processo"


class TestContido:
    async def test_um_lote_so_faz_tantos_documentos_como_o_tamanho(self, bd):
        await _processo(bd)
        for i in range(5):
            await _documento(bd, f"e{i}", ia.TIPO_EXTRATO, _bruto_extrato(), analisado=f"2026-08-0{i + 1}T10:00:00+00:00")
        r1, c1 = await _correr(bd, tamanho=2, respostas=[_bruto_extrato(banco="CGD")])
        assert c1.await_count == 2 and r1["por_estado"] == {"preenchido": 2}
        assert (await sb.contar_candidatos())["banco"] == 3
        # os mais antigos primeiro: e0 e e1 ficaram feitos
        assert {d["id"] for d in await bd.document_metadata.find({"index_facts.bank_key": "cgd"}).to_list(10)} == {"e0", "e1"}
        r2, c2 = await _correr(bd, tamanho=2, respostas=[_bruto_extrato(banco="CGD")])
        assert c2.await_count == 2
        r3, c3 = await _correr(bd, tamanho=2, respostas=[_bruto_extrato(banco="CGD")])
        assert c3.await_count == 1 and (await sb.contar_candidatos())["banco"] == 0

    async def test_o_tecto_do_lote_nao_se_ultrapassa(self, bd):
        await _processo(bd)
        for i in range(sb.TECTO_DO_LOTE + 5):
            await bd.document_metadata.insert_one({
                "id": f"x{i}", "process_id": "p1", "s3_path": f"k/x{i}.pdf", "filename": "x.pdf", "analysis_fingerprint": "a:2",
                "index_facts": {"tipo": ia.TIPO_EXTRATO}, "index_analyzed_at": "2026-08-01"})
        with patch.object(sb, "_processar", AsyncMock(return_value="sem_valor")) as p:
            resumo = await sb.correr_lote(tamanho=10_000, pausa=0, escrever=lambda _l: None)
        assert p.await_count == sb.TECTO_DO_LOTE and resumo["lote"] == sb.TECTO_DO_LOTE


class TestNuncaEntraEmCiclo:
    async def test_o_que_o_documento_nao_diz_nao_se_paga_duas_vezes(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        r1, c1 = await _correr(bd, respostas=[_bruto_extrato()])  # a IA também não encontra banco
        assert r1["por_estado"] == {"sem_valor": 1} and c1.await_count == 1
        antes = await _doc(bd, "e1")
        assert not antes["index_facts"]["bank_key"] and antes[sb.CAMPO_DA_MARCA]["estado"] == "sem_valor"
        r2, c2 = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert r2["candidatos"] == 0 and c2.await_count == 0
        assert (await sb.contar_candidatos())["banco"] == 0

    async def test_um_ficheiro_substituido_nao_recebe_factos_de_outro(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        chave = (await _doc(bd, "e1"))["s3_path"]
        CONTEUDO[chave] = b"OUTRO ficheiro no mesmo caminho"
        resumo, chamada = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert resumo["por_estado"] == {"conteudo_alterado": 1} and chamada.await_count == 0
        d = await _doc(bd, "e1")
        assert not d["index_facts"]["bank_key"]

    async def test_uma_impressao_de_um_esquema_antigo_tambem_nao_se_mistura(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        await bd.document_metadata.update_one({"id": "e1"}, {"$set": {"analysis_fingerprint": "abc:1"}})
        resumo, chamada = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert resumo["por_estado"] == {"conteudo_alterado": 1} and chamada.await_count == 0

    async def test_uma_falha_transitoria_conta_tentativas_e_a_terceira_e_terminal(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        for n in (1, 2):
            r, _ = await _correr(bd, respostas=[RuntimeError("timeout do fornecedor")])
            assert r["por_estado"] == {"adiado": 1}
            d = await _doc(bd, "e1")
            assert d[sb.CAMPO_DA_MARCA]["tentativas"] == n and "estado" not in d[sb.CAMPO_DA_MARCA]
            assert "reservado_ate" not in d[sb.CAMPO_DA_MARCA]
        r, _ = await _correr(bd, respostas=[RuntimeError("timeout do fornecedor")])
        assert r["por_estado"] == {"falhou": 1}
        assert (await _doc(bd, "e1"))[sb.CAMPO_DA_MARCA]["estado"] == "falhou"
        r, c = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert r["candidatos"] == 0 and c.await_count == 0

    async def test_o_texto_do_erro_do_fornecedor_nunca_fica_gravado(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        await _correr(bd, respostas=[RuntimeError("401 api key sk-SEGREDO123 inválida")])
        d = await _doc(bd, "e1")
        assert "SEGREDO" not in repr(d)
        linhas = await bd.process_ai_log.find({}, {"_id": 0}).to_list(10)
        assert linhas and "SEGREDO" not in repr(linhas)

    async def test_uma_falha_nao_bloqueia_a_cabeca_da_fila(self, bd):
        """O mais antigo falha sempre: com lote de 1, o seguinte tem de chegar a ser processado."""
        await _processo(bd)
        await _documento(bd, "mau", ia.TIPO_EXTRATO, _bruto_extrato(), analisado="2026-07-01T00:00:00+00:00")
        await _documento(bd, "bom", ia.TIPO_EXTRATO, _bruto_extrato(), analisado="2026-08-01T00:00:00+00:00")
        await _correr(bd, tamanho=1, respostas=[RuntimeError("timeout")])        # mau: tentativa 1
        r, _ = await _correr(bd, tamanho=1, respostas=[_bruto_extrato(banco="CGD")])  # agora o bom passa à frente
        assert r["por_estado"] == {"preenchido": 1}
        assert (await _doc(bd, "bom"))["index_facts"]["bank_key"] == "cgd"

    async def test_um_ficheiro_ausente_no_s3_conta_como_falha_transitoria(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        with patch("services.document_vision_extract.ler_ficheiro_do_s3", AsyncMock(side_effect=RuntimeError("S3 em baixo"))), \
                patch("services.ai_document.call_openai_api", AsyncMock(side_effect=AssertionError("não devia chamar a IA"))):
            resumo = await sb.correr_lote(tamanho=5, pausa=0, escrever=lambda _l: None)
        assert resumo["por_estado"] == {"adiado": 1}


class TestReservaAtomica:
    async def test_duas_execucoes_sobrepostas_nao_pagam_duas_vezes_o_mesmo_documento(self, bd):
        await _processo(bd)
        for i in range(4):
            await _documento(bd, f"e{i}", ia.TIPO_EXTRATO, _bruto_extrato())
        chamada = _modelo([_bruto_extrato(banco="CGD")])
        with _s3(), patch("services.index_ai._mensagens", return_value=([], False, 60.0)), \
                patch("services.ai_document.call_openai_api", chamada):
            await asyncio.gather(*[sb.correr_lote(tamanho=4, pausa=0, escrever=lambda _l: None) for _ in range(3)])
        assert chamada.await_count == 4  # nunca 12

    async def test_uma_reserva_activa_salta_e_uma_expirada_volta_a_valer(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        futuro = sb._agora() + timedelta(minutes=10)
        await bd.document_metadata.update_one({"id": "e1"}, {"$set": {f"{sb.CAMPO_DA_MARCA}.reservado_ate": futuro}})
        r, c = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert r["candidatos"] == 0 and c.await_count == 0
        passado = sb._agora() - timedelta(minutes=1)
        await bd.document_metadata.update_one({"id": "e1"}, {"$set": {f"{sb.CAMPO_DA_MARCA}.reservado_ate": passado}})
        r, c = await _correr(bd, respostas=[_bruto_extrato(banco="CGD")])
        assert r["por_estado"] == {"preenchido": 1}


class TestSemMotorSimulado:
    async def test_recusa_correr_com_o_motor_simulado(self, bd, monkeypatch):
        monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        with pytest.raises(sb.IASimulada):
            await sb.correr_lote(tamanho=5, pausa=0, escrever=lambda _l: None)
        assert not (await _doc(bd, "e1")).get(sb.CAMPO_DA_MARCA)

    async def test_com_a_permissao_explicita_aceita_o_resultado_simulado(self, bd, monkeypatch):
        monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        with _s3():
            resumo = await sb.correr_lote(tamanho=5, pausa=0, escrever=lambda _l: None, permitir_simulado=True)
        assert resumo["candidatos"] == 1 and resumo["por_estado"].get("preenchido", 0) + resumo["por_estado"].get("sem_valor", 0) == 1


class TestORegistoNoLogDaIA:
    async def test_cada_documento_deixa_uma_linha_automatica_sem_valores(self, bd):
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        await _correr(bd, respostas=[_bruto_extrato(banco="Santander")])
        linhas = await bd.process_ai_log.find({"process_id": "p1"}, {"_id": 0}).to_list(10)
        assert len(linhas) == 1
        assert linhas[0]["gatilho"] == "automatico" and linhas[0]["estado"] == "sucesso"
        assert "Santander" not in repr(linhas) and "santander" not in repr(linhas)


class TestOScript:
    """`scripts/slow_backfill_ia.py` por `principal(argv)`: saída, códigos e que a omissão não paga."""

    async def test_a_omissao_so_conta_e_nao_chama_a_ia(self, bd, capsys):
        from scripts import slow_backfill_ia as cli

        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        modelo = _modelo([_bruto_extrato(banco="Caixa Geral de Depósitos")])
        with _s3(), patch("services.ai_document.call_openai_api", modelo):
            codigo = await cli.principal([])
        saida = capsys.readouterr().out
        assert codigo == 0 and "banco=1" in saida and "Nada foi chamado" in saida
        assert modelo.await_count == 0
        assert "slow_backfill_ia" not in (await bd.document_metadata.find_one({"id": "e1"}))

    async def test_aplicar_imprime_o_progresso_so_com_ids_e_contagens(self, bd, capsys):
        from scripts import slow_backfill_ia as cli

        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        modelo = _modelo([_bruto_extrato(banco="Caixa Geral de Depósitos", iban="PT50003500000000000000000")])
        with _s3(), patch("services.ai_document.call_openai_api", modelo):
            codigo = await cli.principal(["--aplicar", "--batch-size", "5"])
        saida = capsys.readouterr().out
        assert codigo == 0
        assert "doc=e1 tipo=banco → preenchido" in saida
        assert "PROGRESSO: lote=1/5 preenchidos=1" in saida and "restantes=0" in saida
        for segredo in ("Caixa Geral", "PT50", "e1.pdf", "Cliente"):
            assert segredo not in saida

    async def test_com_o_motor_simulado_sai_com_codigo_3(self, bd, monkeypatch, capsys):
        from scripts import slow_backfill_ia as cli

        monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
        await _processo(bd)
        await _documento(bd, "e1", ia.TIPO_EXTRATO, _bruto_extrato())
        assert await cli.principal(["--aplicar"]) == 3
        assert "RECUSADO" in capsys.readouterr().out

    async def test_sem_nada_em_falta_diz_concluido(self, bd, capsys):
        from scripts import slow_backfill_ia as cli

        assert await cli.principal(["--aplicar"]) == 0
        assert "concluído" in capsys.readouterr().out
