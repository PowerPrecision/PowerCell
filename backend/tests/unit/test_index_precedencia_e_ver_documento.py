"""A Declaração de Efetividade manda no emprego, e o «Ver documento» da pesquisa avançada (Out 2026).

Decisão da direcção: o tipo de contrato e a data de admissão da Declaração (atestada pelos RH) têm
PRECEDÊNCIA ABSOLUTA sobre tudo o que se leu ou inferiu dos recibos, na agregação do emprego.
Os dados nascem dos normalizadores de produção (`index_ai`), nunca de objectos escritos à mão.
"""
from __future__ import annotations

import io
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services import index_ai as ia
from services import index_store as store
from tests.unit.helpers_tenant import REDE_INCUMBENTE, semear, tenant_db

HOJE = date(2026, 10, 15)


def _c(v, conf="alta"):
    return {"value": v, "confidence": conf, "page": 1}


def _recibo(doc_id, periodo, *, nif="501964843", nome="Empresa Simulada, Lda", contrato="termo_certo", liquido=1000):
    bruto = {"employer_nif": _c(nif), "employer_name": _c(nome), "job_title": _c("Técnico"),
             "contract_type": _c(contrato), "net_salary": _c(liquido), "period": _c(periodo)}
    return doc_id, ia.normalizar_recibo(bruto, document_id=doc_id)["job"]


def _declaracao(doc_id, *, nif="501964843", nome="Empresa Simulada, Lda", contrato="efetivo",
                admissao="2021-05-03", emissao="2026-10-01", conf_contrato="alta", conf_admissao="alta"):
    bruto = {"employer_nif": _c(nif), "employer_name": _c(nome), "admission_date": _c(admissao, conf_admissao),
             "contract_type": _c(contrato, conf_contrato), "issue_date": _c(emissao)}
    return doc_id, ia.normalizar_declaracao(bruto, document_id=doc_id)["factos"]


def _um_emprego(recibos, declaracoes):
    trabalhos = store.calcular_trabalhos(recibos, declaracoes)
    assert len(trabalhos) == 1, trabalhos
    return trabalhos[0]


class TestAPrecedenciaAbsoluta:
    def test_o_contrato_da_declaracao_vence_o_dos_recibos(self):
        recibos = [_recibo("r1", "2026-08"), _recibo("r2", "2026-09")]  # ambos «termo certo»
        job = _um_emprego(recibos, [_declaracao("d1", contrato="efetivo")])
        assert job.contract_type.value == "efetivo"
        assert job.contract_type.source.document_id == "d1"
        assert job.certified_by_declaration is True

    def test_vence_mesmo_com_um_recibo_mais_recente_que_a_declaracao(self):
        """Não é uma questão de data: «absoluta» quer dizer que o recibo de 2026-12 não a destrona."""
        job = _um_emprego([_recibo("r9", "2026-12", contrato="termo_incerto")], [_declaracao("d1", emissao="2026-01-10")])
        assert job.contract_type.value == "efetivo"

    def test_a_data_de_admissao_vem_da_declaracao(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1", admissao="2019-02-11")])
        assert job.admission_date == "2019-02-11"

    def test_sem_declaracao_tudo_como_antes(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [])
        assert job.contract_type.value == "termo_certo"
        assert job.admission_date is None and job.certified_by_declaration is False

    def test_a_declaracao_entra_nas_fontes_do_emprego(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1")])
        assert job.source_document_ids == ["d1", "r1"]

    def test_o_resto_do_emprego_continua_a_vir_dos_recibos(self):
        job = _um_emprego([_recibo("r1", "2026-09", liquido=1234)], [_declaracao("d1")])
        assert str(job.net_salary.value) == "1234.00" and job.job_title.value == "Técnico" and job.period == "2026-09"

    def test_independente_da_ordem_de_entrada(self):
        a = _um_emprego([_recibo("r1", "2026-08"), _recibo("r2", "2026-09")], [_declaracao("d1"), _declaracao("d2", contrato="termo_certo", emissao="2026-02-01")])
        b = _um_emprego([_recibo("r2", "2026-09"), _recibo("r1", "2026-08")], [_declaracao("d2", contrato="termo_certo", emissao="2026-02-01"), _declaracao("d1")])
        assert a.model_dump(mode="json") == b.model_dump(mode="json")


class TestOQueUmaDeclaracaoNaoFaz:
    def test_um_campo_que_ela_nao_traz_nao_apaga_o_dos_recibos(self):
        decl = _declaracao("d1", contrato=None, admissao="2020-01-01")
        job = _um_emprego([_recibo("r1", "2026-09", contrato="termo_certo")], [decl])
        assert job.contract_type.value == "termo_certo"      # a declaração não diz: ficam os recibos
        assert job.admission_date == "2020-01-01"            # e o que diz, vale

    def test_nao_cria_um_emprego_sozinha(self):
        assert store.calcular_trabalhos([], [_declaracao("d1")]) == []

    def test_de_outra_entidade_nao_manda(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1", nif="509442013", nome="Outra SA")])
        assert job.contract_type.value == "termo_certo" and job.certified_by_declaration is False

    def test_dois_NIFs_validos_diferentes_nao_casam_pelo_nome(self):
        """Mesmo nome, NIFs diferentes: são duas entidades (uma sucursal). A identidade forte vence."""
        job = _um_emprego([_recibo("r1", "2026-09", nif="501964843", nome="Grupo X, Lda")],
                          [_declaracao("d1", nif="509442013", nome="Grupo X, Lda")])
        assert job.certified_by_declaration is False and job.contract_type.value == "termo_certo"

    def test_sem_NIF_valido_casa_pelo_nome(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1", nif=None)])
        assert job.contract_type.value == "efetivo"

    def test_o_NIF_casa_mesmo_que_o_nome_venha_escrito_de_outra_maneira(self):
        job = _um_emprego([_recibo("r1", "2026-09", nome="Empresa Simulada Lda")], [_declaracao("d1", nome="EMPRESA SIMULADA, LDA.")])
        assert job.certified_by_declaration is True


class TestVariasDeclaracoes:
    def test_a_mais_recente_ganha(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [
            _declaracao("d-velha", contrato="termo_certo", admissao="2020-01-01", emissao="2025-03-01"),
            _declaracao("d-nova", contrato="efetivo", admissao="2020-01-01", emissao="2026-09-01"),
        ])
        assert job.contract_type.value == "efetivo" and job.contract_type.source.document_id == "d-nova"

    def test_sem_data_de_emissao_e_a_mais_antiga(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [
            _declaracao("d-sem-data", contrato="termo_certo", emissao=None),
            _declaracao("d-datada", contrato="efetivo", emissao="2024-01-01"),
        ])
        assert job.contract_type.source.document_id == "d-datada"

    def test_empate_desempata_pelo_id(self):
        a = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d-a", contrato="efetivo"), _declaracao("d-b", contrato="termo_certo")])
        b = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d-b", contrato="termo_certo"), _declaracao("d-a", contrato="efetivo")])
        assert a.contract_type.value == b.contract_type.value == "termo_certo"  # d-b > d-a


class TestADuvidaVaiARever:
    def test_contrato_lido_com_confianca_baixa_vence_mas_pede_revisao(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1", conf_contrato="baixa")])
        assert job.contract_type.value == "efetivo" and job.contract_type.needs_review is True
        assert "contract_type" in job.campos_a_rever()

    def test_contrato_com_boa_confianca_nao_pede_revisao(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1")])
        assert job.contract_type.needs_review is False

    def test_admissao_duvidosa_nao_se_propaga_porque_nao_tem_editor(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1", conf_admissao="baixa")])
        assert job.admission_date is None and job.contract_type.value == "efetivo"

    def test_uma_admissao_posterior_a_emissao_nao_chega_ao_emprego(self):
        job = _um_emprego([_recibo("r1", "2026-09")], [_declaracao("d1", admissao="2027-01-01", emissao="2026-10-01")])
        assert job.admission_date is None


class TestUmaPessoaVenceTudo:
    def test_o_contrato_escrito_por_uma_pessoa_sobrevive_a_reanalise(self):
        calculado = store.calcular_trabalhos([_recibo("r1", "2026-09")], [_declaracao("d1")])
        existente = calculado[0].model_dump(mode="json")
        existente["contract_type"] = {"value": "termo_incerto", "needs_review": False, "confidence": None,
                                      "source": None, "edited_by_human": True}
        novo = store.aplicar_edicoes_humanas([existente], store.calcular_trabalhos([_recibo("r1", "2026-09")], [_declaracao("d1")]))
        assert novo[0].contract_type.value == "termo_incerto"
        assert novo[0].admission_date == "2021-05-03"          # a admissão continua a ser da declaração
        assert novo[0].certified_by_declaration is True

    def test_sem_admissao_o_contrato_humano_deixa_de_ser_da_declaracao(self):
        decl = _declaracao("d1", admissao=None)
        existente = store.calcular_trabalhos([_recibo("r1", "2026-09")], [decl])[0].model_dump(mode="json")
        existente["contract_type"] = {"value": "outro", "needs_review": False, "confidence": None,
                                      "source": None, "edited_by_human": True}
        novo = store.aplicar_edicoes_humanas([existente], store.calcular_trabalhos([_recibo("r1", "2026-09")], [decl]))
        assert novo[0].contract_type.value == "outro" and novo[0].certified_by_declaration is False


class TestAAdmissaoNoModelo:
    def test_data_invalida_e_recusada(self):
        from models.index_module import TrabalhoProfissional

        with pytest.raises(ValueError):
            TrabalhoProfissional(job_id="j", admission_date="03/05/2021")

    def test_um_documento_antigo_sem_os_campos_novos_continua_a_ler_se(self):
        from models.index_module import TrabalhoProfissional

        antigo = {"job_id": "j", "period": "2026-09", "source_document_ids": ["r1"]}
        job = TrabalhoProfissional.model_validate(antigo)
        assert job.admission_date is None and job.certified_by_declaration is False

    def test_a_declaracao_guarda_a_confianca_com_que_foi_lida(self):
        _, f = _declaracao("d1", conf_contrato="media", conf_admissao="baixa")
        assert f["contract_confidence"] == "media" and f["admission_confidence"] == "baixa"


# ════════════════════════════════════════════════════════════════════
#  «VER DOCUMENTO»
# ════════════════════════════════════════════════════════════════════
pytestmark_async = pytest.mark.asyncio

DIRETORA_DA_POWER = {"id": "u-ana", "name": "Ana", "role": "diretor", "effective_role": "diretor"}
DIRETOR_DA_DOMUS = {"id": "u-bruno", "name": "Bruno", "role": "diretor", "effective_role": "diretor"}
RAIZ = "Documentação Clientes"
PASTA = f"{RAIZ}/c-power/processos/p-power"


def _s3(corpo=b"%PDF-1.4 recibo", tamanho=None):
    cliente = MagicMock()
    cliente.get_object.return_value = {
        "Body": io.BytesIO(corpo), "ContentLength": len(corpo) if tamanho is None else tamanho,
        "ContentType": "binary/octet-stream",
    }
    return MagicMock(is_configured=MagicMock(return_value=True), s3_client=cliente, bucket_name="bkt"), cliente


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    semear(fake_async_db)
    for p in fake_async_db.processes.docs:
        if p["id"] == "p-power":
            p.update(client_id="c-power", s3_folder=PASTA, is_deleted=False)
        if p["id"] == "p-domus":
            p.update(client_id="c-domus", s3_folder=f"{RAIZ}/c-domus/processos/p-domus", is_deleted=False)

    def doc(i, processo, tipo, chave, nome, **extra):
        return {"id": i, "process_id": processo, "s3_path": chave, "filename": nome,
                "index_facts": {"tipo": tipo, "document_id": i}, **extra}

    fake_async_db.document_metadata.docs.extend([
        doc("d-recibo", "p-power", ia.TIPO_RECIBO, f"{PASTA}/recibo_ana_silva.pdf", "recibo_ana_silva.pdf"),
        doc("d-extrato", "p-power", ia.TIPO_EXTRATO, f"{PASTA}/extrato.png", "extrato.png"),
        doc("d-decl", "p-power", ia.TIPO_DECLARACAO, f"{PASTA}/declaracao.pdf", "declaracao.pdf"),
        doc("d-cc", "p-power", ia.TIPO_IDENTIFICACAO, f"{PASTA}/cc.jpg", "cc.jpg"),
        doc("d-sem-analise", "p-power", ia.TIPO_RECIBO, f"{PASTA}/x.pdf", "x.pdf") | {"index_facts": None},
        doc("d-veneno", "p-power", ia.TIPO_RECIBO, "backups/dump-2026-09-01.zip", "dump.pdf"),
        doc("d-outro-cliente", "p-power", ia.TIPO_RECIBO, f"{RAIZ}/c-domus/processos/p-domus/r.pdf", "r.pdf"),
        doc("d-domus", "p-domus", ia.TIPO_RECIBO, f"{RAIZ}/c-domus/processos/p-domus/r.pdf", "r.pdf"),
        doc("d-docx", "p-power", ia.TIPO_RECIBO, f"{PASTA}/r.docx", "r.docx"),
        doc("d-purgado", "p-power", ia.TIPO_RECIBO, f"{PASTA}/recibo_limpo.pdf", "recibo_original.jpg",
            file_state="purgado"),
    ])
    return fake_async_db


async def _ver(mundo, document_id, user=DIRETORA_DA_POWER, servico=None):
    import services.document_visibility as dv
    import services.financial_validation as fv
    import services.index_document_content as idc

    servico = servico or _s3()[0]
    with tenant_db(mundo, idc, dv, fv), patch("services.s3_storage.s3_service", servico):
        resposta = await idc.run_conteudo_do_documento(user, document_id)
        corpo = b"".join([b async for b in resposta.body_iterator])
    return resposta, corpo


@pytest.mark.asyncio
class TestVerDocumento:
    async def test_um_pdf_sai_inline_com_o_tipo_que_nos_decidimos(self, mundo):
        servico, cliente = _s3(b"%PDF-1.4 bytes")
        resposta, corpo = await _ver(mundo, "d-recibo", servico=servico)
        assert corpo == b"%PDF-1.4 bytes" and resposta.media_type == "application/pdf"
        assert resposta.headers["content-disposition"].startswith("inline;")
        assert resposta.headers["x-content-type-options"] == "nosniff"
        assert "no-store" in resposta.headers["cache-control"]
        # a chave que sai para o S3 é a do REGISTO, nunca uma que viaje no pedido
        cliente.get_object.assert_called_once_with(Bucket="bkt", Key=f"{PASTA}/recibo_ana_silva.pdf")

    async def test_uma_imagem_sai_com_o_tipo_da_extensao(self, mundo):
        resposta, _ = await _ver(mundo, "d-extrato", servico=_s3(b"\x89PNG....")[0])
        assert resposta.media_type == "image/png"

    async def test_o_original_purgado_serve_o_pdf_limpo_com_o_tipo_da_CHAVE(self, mundo):
        """O nome diz `.jpg` e a chave é o PDF limpo: o tipo é o do que sai, não o do que se chamava."""
        resposta, _ = await _ver(mundo, "d-purgado")
        assert resposta.media_type == "application/pdf"

    async def test_so_serve_o_que_a_pesquisa_mostra(self, mundo):
        for i in ("d-cc", "d-sem-analise", "nao-existe"):
            with pytest.raises(HTTPException) as e:
                await _ver(mundo, i)
            assert e.value.status_code == 404, i

    async def test_tipo_sem_previsualizacao_da_415_sem_ir_ao_s3(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _ver(mundo, "d-docx", servico=servico)
        assert e.value.status_code == 415
        cliente.get_object.assert_not_called()

    async def test_demasiado_grande_da_413(self, mundo):
        from services.previsualizacao_de_ficheiros import MAX_BYTES_DA_PREVISUALIZACAO

        with pytest.raises(HTTPException) as e:
            await _ver(mundo, "d-recibo", servico=_s3(b"x", tamanho=MAX_BYTES_DA_PREVISUALIZACAO + 1)[0])
        assert e.value.status_code == 413


@pytest.mark.asyncio
class TestAExploracaoDoVerDocumento:
    async def test_outra_rede_recebe_404_igual_ao_de_nao_existe(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as alheio:
            await _ver(mundo, "d-recibo", user=DIRETOR_DA_DOMUS, servico=servico)
        with pytest.raises(HTTPException) as inexistente:
            await _ver(mundo, "nao-existe", user=DIRETOR_DA_DOMUS)
        assert alheio.value.status_code == inexistente.value.status_code == 404
        assert alheio.value.detail == inexistente.value.detail
        cliente.get_object.assert_not_called()  # a recusa vem ANTES de tocar no bucket

    async def test_o_dono_da_domus_ve_o_seu(self, mundo):
        resposta, _ = await _ver(mundo, "d-domus", user=DIRETOR_DA_DOMUS)
        assert resposta.media_type == "application/pdf"

    async def test_uma_rede_convidada_ve_o_documento_do_processo_partilhado(self, mundo):
        for p in mundo.processes.docs:
            if p["id"] == "p-power":
                p["partner_network_ids"] = ["grupo_domus"]
        resposta, _ = await _ver(mundo, "d-recibo", user=DIRETOR_DA_DOMUS)
        assert resposta.media_type == "application/pdf"

    async def test_uma_chave_envenenada_nao_abre_o_bucket(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _ver(mundo, "d-veneno", servico=servico)
        assert e.value.status_code == 403
        cliente.get_object.assert_not_called()

    async def test_a_chave_de_outro_cliente_nao_abre(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _ver(mundo, "d-outro-cliente", servico=servico)
        assert e.value.status_code == 403
        cliente.get_object.assert_not_called()

    async def test_um_processo_por_indexar_nao_se_abre_a_quem_nao_esta_atribuido(self, mundo):
        """A visibilidade dos documentos pré-indexação continua a valer: o atalho não a contorna."""
        carla = {"id": "u-carla", "name": "Carla", "role": "consultor", "effective_role": "consultor"}
        for p in mundo.processes.docs:
            if p["id"] == "p-power":
                p["is_indexed"] = False
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _ver(mundo, "d-recibo", user=carla, servico=servico)
        assert e.value.status_code == 403
        cliente.get_object.assert_not_called()

    async def test_indexado_a_mesma_pessoa_ve(self, mundo):
        carla = {"id": "u-carla", "name": "Carla", "role": "consultor", "effective_role": "consultor"}
        for p in mundo.processes.docs:
            if p["id"] == "p-power":
                p["is_indexed"] = True
        resposta, _ = await _ver(mundo, "d-recibo", user=carla)
        assert resposta.media_type == "application/pdf"

    async def test_um_processo_eliminado_nao_serve(self, mundo):
        for p in mundo.processes.docs:
            if p["id"] == "p-power":
                p["is_deleted"] = True
        with pytest.raises(HTTPException) as e:
            await _ver(mundo, "d-recibo")
        assert e.value.status_code == 404


class TestARotaDoVerDocumento:
    def _funcao(self):
        import ast
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "routes" / "index_module.py").read_text(encoding="utf-8")
        return next(n for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_document_content")

    def test_so_os_perfis_do_index(self):
        assert "_acesso" in __import__("ast").unparse(self._funcao())

    def test_tem_limite_e_response(self):
        import ast

        f = self._funcao()
        assert any("limiter.limit" in ast.unparse(d) for d in f.decorator_list)
        assert {"request", "response"} <= {a.arg for a in f.args.args}

    def test_o_resultado_da_pesquisa_nao_leva_o_nome_do_ficheiro(self):
        """O nome de um ficheiro leva o do cliente: o atalho vai pelo id, o nome só viaja no cabeçalho."""
        from services.index_advanced_search import resultado_do_documento

        r = resultado_do_documento({"id": "d1", "doc_type": "recibo", "process_id": "p", "filename": "ana_silva.pdf"})
        assert "ana_silva" not in str(r) and r["document_id"] == "d1"


class TestEmpregosPorTitular:
    """Afinação do cliente (Out 2026): o emprego e o vencimento seguem o titular do ficheiro."""

    def test_dois_titulares_na_mesma_empresa_sao_dois_empregos(self):
        recibos = [_recibo("r1", "2026-09", liquido=1500), _recibo("r2", "2026-09", liquido=900)]
        trabalhos = store.calcular_trabalhos(recibos, [], {"r1": "titular1", "r2": "titular2"})
        por_titular = {t.titular: t for t in trabalhos}
        assert set(por_titular) == {"titular1", "titular2"}
        assert str(por_titular["titular1"].net_salary.value) == "1500.00"
        assert str(por_titular["titular2"].net_salary.value) == "900.00"
        assert por_titular["titular2"].source_document_ids == ["r2"]

    def test_a_declaracao_do_2o_nao_certifica_o_emprego_do_1o(self):
        trabalhos = store.calcular_trabalhos(
            [_recibo("r1", "2026-09")], [_declaracao("d2")], {"r1": "titular1", "d2": "titular2"})
        assert trabalhos[0].contract_type.value == "termo_certo" and not trabalhos[0].certified_by_declaration

    def test_o_job_id_do_1o_titular_nao_muda(self):
        sem = store.calcular_trabalhos([_recibo("r1", "2026-09")], [])
        com = store.calcular_trabalhos([_recibo("r1", "2026-09")], [], {"r1": "titular1"})
        assert sem[0].job_id == com[0].job_id
        assert sem[0].titular is None and com[0].titular == "titular1"
