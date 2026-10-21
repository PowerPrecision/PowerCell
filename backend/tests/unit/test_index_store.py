"""Persistência do Index (Lote 12, Fase 2): agrupar, preservar edições humanas, directório, alertas."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from models.index_module import CampoRevisavel, TrabalhoProfissional
from services import index_ai as ia
from services import index_store as st

NIF_A, NIF_B = "501964843", "509442013"


def job(nif=NIF_A, nome="Acme, Lda", cargo="Técnica", liquido="1000", contrato="efetivo", period="2026-09", doc="d1",
        revisar=()):
    """`revisar`: nomes dos campos (`nif`, `nome`, `cargo`, `liquido`, `contrato`) marcados «a rever»."""
    def c(v, campo):
        return CampoRevisavel(value=v, needs_review=campo in revisar, confidence="alta")

    return TrabalhoProfissional(
        job_id="x", employer_nif=c(nif, "nif"), employer_name=c(nome, "nome"), job_title=c(cargo, "cargo"),
        net_salary=c(Decimal(liquido) if liquido is not None else None, "liquido"),
        contract_type=c(contrato, "contrato"), period=period, source_document_ids=[doc],
    )


class TestCalcularTrabalhos:
    def test_recibos_da_mesma_entidade_sao_um_trabalho(self):
        r = st.calcular_trabalhos([("d1", job(period="2026-07", doc="d1")), ("d2", job(period="2026-08", doc="d2")),
                                   ("d3", job(period="2026-09", doc="d3"))])
        assert len(r) == 1 and r[0].source_document_ids == ["d1", "d2", "d3"] and r[0].period == "2026-09"

    def test_entidades_diferentes_sao_trabalhos_diferentes(self):
        r = st.calcular_trabalhos([("d1", job(NIF_A)), ("d2", job(NIF_B, nome="Beta SA", doc="d2"))])
        assert len(r) == 2 and len({j.job_id for j in r}) == 2

    def test_o_recibo_mais_recente_manda_no_salario(self):
        r = st.calcular_trabalhos([("d1", job(liquido="900", period="2026-07", doc="d1")),
                                   ("d2", job(liquido="1100", period="2026-09", doc="d2"))])
        assert r[0].net_salary.value == Decimal("1100")

    def test_um_campo_em_falta_no_mais_recente_vem_do_anterior(self):
        r = st.calcular_trabalhos([("d1", job(cargo="Engenheira", period="2026-07", doc="d1")),
                                   ("d2", job(cargo=None, period="2026-09", doc="d2"))])
        assert r[0].job_title.value == "Engenheira"

    def test_a_ordem_de_entrada_nao_importa(self):
        a = [("d1", job(period="2026-07", doc="d1", liquido="900")), ("d2", job(period="2026-09", doc="d2", liquido="1100")),
             ("d3", job(NIF_B, nome="Beta", doc="d3"))]
        r1 = st.calcular_trabalhos(a)
        r2 = st.calcular_trabalhos(list(reversed(a)))
        assert [j.model_dump(mode="json") for j in r1] == [j.model_dump(mode="json") for j in r2]

    def test_o_job_id_e_estavel_entre_corridas(self):
        assert st.calcular_trabalhos([("d1", job())])[0].job_id == st.calcular_trabalhos([("d9", job(doc="d9"))])[0].job_id

    def test_sem_nif_valido_agrupa_pelo_nome(self):
        r = st.calcular_trabalhos([("d1", job(nif=None, nome="ACME Lda")), ("d2", job(nif=None, nome="Acmé, Limitada", doc="d2"))])
        assert len(r) == 1

    def test_nif_invalido_nao_serve_de_chave(self):
        r = st.calcular_trabalhos([("d1", job(nif="518789370", nome="Acme")), ("d2", job(nif="518789371", nome="Acme", doc="d2"))])
        assert len(r) == 1  # ambos caem no nome

    def test_sem_nif_nem_nome_cada_documento_e_um_trabalho(self):
        r = st.calcular_trabalhos([("d1", job(nif=None, nome=None)), ("d2", job(nif=None, nome=None, doc="d2"))])
        assert len(r) == 2

    def test_a_duvida_do_campo_escolhido_acompanha_o_valor(self):
        r = st.calcular_trabalhos([("d1", job(cargo="X", period="2026-09", doc="d1", revisar=("cargo",)))])
        assert r[0].job_title.needs_review is True

    def test_vazio(self):
        assert st.calcular_trabalhos([]) == []


class TestEdicoesHumanas:
    def existente(self, **campos):
        j = job().model_dump(mode="json")
        j["job_id"] = "job_antigo"
        j["source_document_ids"] = ["d1"]
        j.update(campos)
        return j

    def test_o_que_uma_pessoa_escreveu_sobrevive_a_reanalise(self):
        ex = self.existente(job_title={"value": "Diretora", "needs_review": False, "edited_by_human": True})
        novo = st.calcular_trabalhos([("d1", job(cargo="Técnica"))])
        r = st.aplicar_edicoes_humanas([ex], novo)
        assert r[0].job_title.value == "Diretora" and r[0].job_title.edited_by_human is True

    def test_o_que_a_ia_propos_e_substituido(self):
        ex = self.existente(job_title={"value": "Velho", "needs_review": False, "edited_by_human": False})
        r = st.aplicar_edicoes_humanas([ex], st.calcular_trabalhos([("d1", job(cargo="Novo"))]))
        assert r[0].job_title.value == "Novo"

    def test_o_job_id_antigo_mantem_se(self):
        ex = self.existente()
        r = st.aplicar_edicoes_humanas([ex], st.calcular_trabalhos([("d1", job())]))
        assert r[0].job_id == "job_antigo"

    def test_corrigir_o_nif_nao_cria_um_trabalho_novo(self):
        # a pessoa corrigiu o NIF: a chave de agrupamento mudaria, mas os recibos são os mesmos
        ex = self.existente(employer_nif={"value": NIF_B, "needs_review": False, "edited_by_human": True})
        r = st.aplicar_edicoes_humanas([ex], st.calcular_trabalhos([("d1", job(nif=NIF_A))]))
        assert len(r) == 1 and r[0].job_id == "job_antigo" and r[0].employer_nif.value == NIF_B

    def test_um_trabalho_sem_documentos_de_origem_desaparece(self):
        ex = self.existente(source_document_ids=["d_apagado"])
        r = st.aplicar_edicoes_humanas([ex], st.calcular_trabalhos([("d2", job(NIF_B, nome="Beta", doc="d2"))]))
        assert len(r) == 1 and r[0].job_id != "job_antigo"

    def test_o_codigo_reforca_o_que_uma_pessoa_escreveu(self):
        ex = self.existente(employer_nif={"value": "518789370", "needs_review": False, "edited_by_human": True})
        r = st.aplicar_edicoes_humanas([ex], st.calcular_trabalhos([("d1", job())]))
        assert r[0].employer_nif.value == "518789370" and r[0].employer_nif.needs_review is True

    def test_dois_trabalhos_novos_nao_roubam_a_mesma_edicao(self):
        ex = self.existente(source_document_ids=["d1", "d2"])
        novos = st.calcular_trabalhos([("d1", job(NIF_A)), ("d2", job(NIF_B, nome="Beta", doc="d2"))])
        r = st.aplicar_edicoes_humanas([ex], novos)
        assert len({j.job_id for j in r}) == 2

    def test_sem_existentes_devolve_o_calculado(self):
        novos = st.calcular_trabalhos([("d1", job())])
        assert st.aplicar_edicoes_humanas([], novos) == novos


class TestEntidades:
    def test_so_entra_o_que_esta_certo(self):
        ok = st.entidades_a_registar([job()])
        assert ok == [(NIF_A, "Acme, Lda")]

    @pytest.mark.parametrize("kw", [
        dict(nif="518789370"),                      # sem dígito de controlo
        dict(nif=None), dict(nome=None),
        dict(revisar=("nif",)),                     # válido, mas o modelo duvidou
        dict(revisar=("nome",)),
    ])
    def test_o_que_nao_entra(self, kw):
        assert st.entidades_a_registar([job(**kw)]) == []

    def test_uma_pessoa_que_confirmou_entra_mesmo_em_duvida(self):
        j = job(nif=NIF_A)
        j.employer_nif.needs_review, j.employer_nif.edited_by_human = True, True
        assert st.entidades_a_registar([j]) == [(NIF_A, "Acme, Lda")]

    @pytest.mark.asyncio
    async def test_o_primeiro_nome_ganha(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            assert await st.registar_entidades([job(nome="Acme, Lda")]) == 1
            assert await st.registar_entidades([job(nome="Outro Nome SA")]) == 0
        docs = await fake_async_db.employers.find({}).to_list(10)
        assert len(docs) == 1 and docs[0]["name"] == "Acme, Lda" and docs[0]["name_normalizado"] == "acme"

    @pytest.mark.asyncio
    async def test_o_directorio_nao_leva_referencias_a_clientes_nem_processos(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            await st.registar_entidades([job()])
        doc = (await fake_async_db.employers.find({}).to_list(10))[0]
        assert set(doc) - {"_id"} == {"nif", "name", "name_normalizado", "first_seen_at"}

    @pytest.mark.asyncio
    async def test_falha_do_directorio_nunca_propaga(self):
        class Rebenta:
            class employers:
                @staticmethod
                async def update_one(*a, **k):
                    raise RuntimeError("bd")

        with patch.object(st, "db", Rebenta):
            assert await st.registar_entidades([job()]) == 0

    @pytest.mark.asyncio
    async def test_conhecidas_por_nome(self, fake_async_db):
        await fake_async_db.employers.insert_one({"nif": NIF_A, "name": "Acme", "name_normalizado": "acme"})
        with patch.object(st, "db", fake_async_db):
            assert await st.entidades_conhecidas(["ACME, Lda", "Outra"]) == {"acme": NIF_A}
            assert await st.entidades_conhecidas([]) == {}
            assert await st.entidades_conhecidas([None, ""]) == {}


class TestAlertas:
    ACHADO = {"code": "recibo_sem_credito", "refs": [{"document_id": "r1", "page": None}], "periodo": "2026-09"}

    def test_a_chave_e_estavel_e_distingue(self):
        assert st.chave_do_alerta(self.ACHADO) == st.chave_do_alerta(dict(self.ACHADO))
        assert st.chave_do_alerta(self.ACHADO) != st.chave_do_alerta({**self.ACHADO, "periodo": "2026-08"})
        assert st.chave_do_alerta(self.ACHADO) != st.chave_do_alerta({**self.ACHADO, "code": "nif_invalido"})
        outra = {**self.ACHADO, "refs": [{"document_id": "r2", "page": None}]}
        assert st.chave_do_alerta(self.ACHADO) != st.chave_do_alerta(outra)

    @pytest.mark.asyncio
    async def test_insere_e_a_severidade_vem_da_tabela(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            r = await st.substituir_alertas("p", "n1", "run1", [self.ACHADO])
        assert r["abertos"] == 1
        a = (await fake_async_db.process_index_alerts.find({}).to_list(10))[0]
        assert a["severity"] == "aviso" and a["run_id"] == "run1" and a["network_id"] == "n1"
        assert a["message"].startswith("O líquido de um recibo")

    @pytest.mark.asyncio
    async def test_nova_corrida_substitui_os_abertos(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("p", "n1", "run1", [self.ACHADO])
            await st.substituir_alertas("p", "n1", "run2", [self.ACHADO])
        alertas = await fake_async_db.process_index_alerts.find({}).to_list(10)
        assert len(alertas) == 1 and alertas[0]["run_id"] == "run2"

    @pytest.mark.asyncio
    async def test_o_que_deixou_de_ser_verdade_desaparece(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("p", "n1", "run1", [self.ACHADO])
            r = await st.substituir_alertas("p", "n1", "run2", [])
        assert r["abertos"] == 0 and await fake_async_db.process_index_alerts.find({}).to_list(10) == []

    @pytest.mark.asyncio
    async def test_um_dispensado_nao_ressuscita(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("p", "n1", "run1", [self.ACHADO])
            await fake_async_db.process_index_alerts.update_one({"process_id": "p"}, {"$set": {"dismissed_by_human": True}})
            r = await st.substituir_alertas("p", "n1", "run2", [self.ACHADO])
        alertas = await fake_async_db.process_index_alerts.find({}).to_list(10)
        assert r["abertos"] == 0 and r["inseridos"] == 0
        assert len(alertas) == 1 and alertas[0]["dismissed_by_human"] is True

    @pytest.mark.asyncio
    async def test_um_dispensado_cuja_condicao_acabou_sai(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("p", "n1", "run1", [self.ACHADO])
            await fake_async_db.process_index_alerts.update_one({"process_id": "p"}, {"$set": {"dismissed_by_human": True}})
            await st.substituir_alertas("p", "n1", "run2", [])
        assert await fake_async_db.process_index_alerts.find({}).to_list(10) == []

    @pytest.mark.asyncio
    async def test_um_achado_novo_aparece_ao_lado_do_dispensado(self, fake_async_db):
        outro = {**self.ACHADO, "code": "nif_invalido"}
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("p", "n1", "run1", [self.ACHADO])
            await fake_async_db.process_index_alerts.update_one({"process_id": "p"}, {"$set": {"dismissed_by_human": True}})
            r = await st.substituir_alertas("p", "n1", "run2", [self.ACHADO, outro])
        assert r["abertos"] == 1

    @pytest.mark.asyncio
    async def test_so_mexe_nos_alertas_do_proprio_processo(self, fake_async_db):
        with patch.object(st, "db", fake_async_db):
            await st.substituir_alertas("outro", "n1", "r", [self.ACHADO])
            await st.substituir_alertas("p", "n1", "r", [])
        assert len(await fake_async_db.process_index_alerts.find({"process_id": "outro"}).to_list(10)) == 1


class TestFicheiro:
    def resultado(self, tipo, **kw):
        return ia.ResultadoDaAnalise(ok=True, tipo=tipo, modelo="m", origem="ia", **kw)

    def test_recibo(self):
        j = job()
        c = st.campos_do_ficheiro(self.resultado(ia.TIPO_RECIBO, job=j, factos={"tipo": "recibo_vencimento"}), "h:1")
        assert c["ai_category"] == "Financeiros" and c["ai_subcategory"] == "Recibo de Vencimento"
        assert c["analysis_fingerprint"] == "h:1" and c["index_job"]["employer_nif"]["value"] == NIF_A
        assert c["ai_subtype"] is None and c["is_categorized"] is True

    def test_extrato(self):
        c = st.campos_do_ficheiro(self.resultado(ia.TIPO_EXTRATO, factos={"tipo": "extrato_bancario"}), "h:1")
        assert c["ai_category"] == "Bancários" and c["index_job"] is None

    @pytest.mark.parametrize("sub, rotulo", [("cc", "Cartão de Cidadão"), ("bi", "Bilhete de Identidade"),
                                              ("passaporte", "Passaporte"), ("titulo_residencia", "Título de Residência")])
    def test_todos_os_tipos_de_identificacao_na_mesma_categoria(self, sub, rotulo):
        c = st.campos_do_ficheiro(self.resultado(ia.TIPO_IDENTIFICACAO, subtype=sub, factos={}), "h:1")
        assert c["ai_category"] == "Identificação" and c["ai_subtype"] == sub and c["ai_subcategory"] == rotulo

    def test_identificacao_de_tipo_desconhecido_continua_em_identificacao(self):
        c = st.campos_do_ficheiro(self.resultado(ia.TIPO_IDENTIFICACAO, subtype=None, factos={}), "h:1")
        assert c["ai_category"] == "Identificação" and c["ai_subtype"] is None

    def test_nada_pessoal_nos_campos_gravados(self):
        c = st.campos_do_ficheiro(self.resultado(ia.TIPO_IDENTIFICACAO, subtype="cc",
                                                 factos={"tipo": "identificacao", "subtype": "cc", "expirada": False}), "h:1")
        assert not {"name", "nome", "nif", "document_number", "birth_date"} & set(c)
