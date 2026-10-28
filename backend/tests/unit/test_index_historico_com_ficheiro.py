"""Arquivo histórico COM ficheiro e «Tudo» na pesquisa avançada (28/10/2026).

O Index pediu para ver e descarregar os documentos que a pesquisa encontra no arquivo histórico (até aqui só havia
«Só os dados (ficheiro não guardado)») e uma opção «Tudo» em «O que procurar». Afirma-se aqui:
* a chave S3 só leva ids e fica na pasta da rede E da importação; a guarda de posse recusa tudo o resto;
* o endpoint do «Ver documento»/«Download» serve uma linha histórica do âmbito, e dá 404 uniforme fora dele;
* a importação guarda o ficheiro depois da linha, e uma reexecução liga o ficheiro a uma linha antiga SEM a IA;
* `document_type=todos` aceita todos os filtros e casa com os três tipos.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import index_advanced_search as pesquisa
from services import index_historical_import as imp
from services import index_store as store
from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE, tenant_db
from tests.unit.test_index_precedencia_e_ver_documento import (  # noqa: F401 — `mundo` é uma fixture
    DIRETOR_DA_DOMUS,
    DIRETORA_DA_POWER,
    _s3,
    mundo,
)

PASTA_POWER = f"{store.PREFIXO_S3_DO_ARQUIVO}{REDE_INCUMBENTE}/imp123/"


class TestChaveEPosse:
    def test_a_chave_so_leva_ids(self):
        chave = store.chave_do_ficheiro_historico(REDE_INCUMBENTE, "imp123", "hist_abc", ".PDF")
        assert chave == f"{PASTA_POWER}hist_abc.pdf"

    @pytest.mark.parametrize("rede,imp_id,doc,ext", [
        ("", "imp", "hist_a", ".pdf"), ("r", "", "hist_a", ".pdf"), ("r", "imp", "", ".pdf"), ("r", "imp", "hist_a", ".exe"),
    ])
    def test_sem_um_dos_ids_ou_com_extensao_estranha_nao_ha_chave(self, rede, imp_id, doc, ext):
        assert store.chave_do_ficheiro_historico(rede, imp_id, doc, ext) is None

    def test_segmentos_nao_escapam_da_pasta(self):
        chave = store.chave_do_ficheiro_historico("../backups", "imp/../x", "hist_a", ".pdf")
        assert ".." not in chave.split("/") and chave.count("/") == 3

    def test_posse_da_linha(self):
        linha = {"network_id": REDE_INCUMBENTE, "import_id": "imp123"}
        assert store.chave_historica_e_da_linha(f"{PASTA_POWER}hist_abc.pdf", linha)
        for chave in (
            f"{store.PREFIXO_S3_DO_ARQUIVO}{REDE_DOMUS}/imp123/hist_abc.pdf",  # outra rede
            f"{store.PREFIXO_S3_DO_ARQUIVO}{REDE_INCUMBENTE}/outra/hist_abc.pdf",  # outra importação
            f"{PASTA_POWER}sub/hist_abc.pdf",  # subpasta
            f"{PASTA_POWER}../../backups/dump.zip",
            "backups/dump.zip", "", None, PASTA_POWER,
        ):
            assert not store.chave_historica_e_da_linha(chave, linha), chave


def _linha(i, rede, *, chave="__omissao__", tipo="recibo"):
    return {"id": i, "historical": True, "network_id": rede, "import_id": "imp123", "doc_type": tipo,
            "period": "2025-09", "process_id": "historical_import_imp123",
            "s3_path": f"{store.PREFIXO_S3_DO_ARQUIVO}{rede}/imp123/{i}.pdf" if chave == "__omissao__" else chave}


@pytest.fixture
def arquivo(mundo):
    mundo.process_index_documents.docs.extend([
        _linha("hist_power", REDE_INCUMBENTE),
        _linha("hist_domus", REDE_DOMUS),
        _linha("hist_sem_ficheiro", REDE_INCUMBENTE, chave=None),
        _linha("hist_veneno", REDE_INCUMBENTE, chave="backups/dump-2026.zip"),
        _linha("hist_outra_rede_na_chave", REDE_INCUMBENTE, chave=f"{store.PREFIXO_S3_DO_ARQUIVO}{REDE_DOMUS}/imp123/x.pdf"),
    ])
    return mundo


async def _servir(bd, document_id, *, user=DIRETORA_DA_POWER, descarregar=False, servico=None, auditoria=None):
    import services.audit_trail_service as auditoria_real
    import services.document_visibility as dv
    import services.financial_validation as fv
    import services.index_document_content as idc

    servico = servico or _s3()[0]
    auditoria = auditoria if auditoria is not None else AsyncMock(return_value="evento")
    with tenant_db(bd, idc, dv, fv, store), patch("services.s3_storage.s3_service", servico), \
            patch.object(auditoria_real, "log_audit_event", auditoria):
        resposta = await idc.run_conteudo_do_documento(user, document_id, descarregar=descarregar)
        corpo = b"".join([b async for b in resposta.body_iterator])
    return resposta, corpo


@pytest.mark.asyncio
class TestServirODoArquivo:
    async def test_serve_a_linha_da_rede_pela_chave_do_registo(self, arquivo):
        servico, cliente = _s3(b"%PDF-1.4 historico")
        resposta, corpo = await _servir(arquivo, "hist_power", servico=servico)
        assert corpo == b"%PDF-1.4 historico" and resposta.media_type == "application/pdf"
        cliente.get_object.assert_called_once_with(Bucket="bkt", Key=f"{store.PREFIXO_S3_DO_ARQUIVO}{REDE_INCUMBENTE}/imp123/hist_power.pdf")

    async def test_descarregar_e_attachment_com_nome_neutro_e_deixa_rasto(self, arquivo):
        auditoria = AsyncMock(return_value="evento")
        resposta, _ = await _servir(arquivo, "hist_power", descarregar=True, auditoria=auditoria)
        assert resposta.headers["content-disposition"].startswith("attachment;")
        assert "recibo_2025-09.pdf" in resposta.headers["content-disposition"]
        assert auditoria.await_args.kwargs["metadata"]["document_id"] == "hist_power"

    @pytest.mark.parametrize("doc_id", ["hist_domus", "hist_sem_ficheiro", "hist_veneno", "hist_outra_rede_na_chave", "hist_nao_existe"])
    async def test_fora_do_ambito_sem_ficheiro_ou_chave_envenenada_e_404_igual(self, arquivo, doc_id):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _servir(arquivo, doc_id, servico=servico)
        assert e.value.status_code == 404 and e.value.detail == "Documento não encontrado."
        cliente.get_object.assert_not_called()

    async def test_contraprova_a_rede_dona_abre_o_seu(self, arquivo):
        _, corpo = await _servir(arquivo, "hist_domus", user=DIRETOR_DA_DOMUS)
        assert corpo


class _ZipFalso:
    pass


@pytest.mark.asyncio
class TestImportarGuardaOFicheiro:
    def _resultado(self):
        return SimpleNamespace(ok=True, job=None, factos={})

    async def test_linha_nova_guarda_o_ficheiro_depois_da_linha(self):
        guardar = AsyncMock(return_value=True)
        resumo = imp.Resumo(import_id="imp123", process_id="historical_import_imp123", rede=REDE_INCUMBENTE)
        linha = {"id": "hist_x", "network_id": REDE_INCUMBENTE, "import_id": "imp123", "doc_type": "recibo",
                 "historical": True, "net_salary_num": 1000.0}
        info = SimpleNamespace(filename="2019/Recibos/Joao_Segredo_recibo_vencimento.pdf")
        with patch.object(imp, "ler_membro", return_value=(b"%PDF conteudo", None)), \
                patch.object(imp.store, "ids_historicos_conhecidos", AsyncMock(return_value={})), \
                patch.object(imp, "analisar_documento", AsyncMock(return_value=self._resultado())), \
                patch.object(imp.store, "linha_historica", return_value=linha), \
                patch.object(imp.store, "gravar_documento_historico", AsyncMock(return_value=True)) as gravar, \
                patch.object(imp.store, "registar_entidades", AsyncMock(return_value=0)), \
                patch.object(imp.store, "ligar_ficheiro_historico", AsyncMock(return_value=True)) as ligar:
            estado = await imp._importar_membro(
                _ZipFalso(), info, resumo, rede=REDE_INCUMBENTE, label="x", vistos=set(),
                classificar_sempre=False, permitir_simulado=True, guardar_ficheiro=guardar,
            )
        assert estado == "importado" and gravar.await_count == 1
        chave, conteudo, mime = guardar.await_args.args
        assert chave == f"{PASTA_POWER}hist_x.pdf" and conteudo == b"%PDF conteudo" and mime == "application/pdf"
        assert "Joao" not in chave  # o nome do ficheiro (do cliente) nunca entra na chave
        ligar.assert_awaited_once_with("hist_x", chave)
        assert resumo.ficheiros_guardados == 1 and resumo.ficheiros_falhados == 0

    async def test_reexecucao_liga_o_ficheiro_a_linha_antiga_sem_ia(self):
        guardar = AsyncMock(return_value=True)
        resumo = imp.Resumo(import_id="imp999", process_id="historical_import_imp999", rede=REDE_INCUMBENTE)
        antiga = {"id": "hist_y", "network_id": REDE_INCUMBENTE, "import_id": "imp123"}
        analisar = AsyncMock()
        with patch.object(imp, "ler_membro", return_value=(b"%PDF y", None)), \
                patch.object(imp.store, "ids_historicos_conhecidos", AsyncMock(side_effect=lambda ids: {ids[0]: "importado"})), \
                patch.object(imp.store, "linha_historica_sem_ficheiro", AsyncMock(return_value=antiga)), \
                patch.object(imp.store, "ligar_ficheiro_historico", AsyncMock(return_value=True)), \
                patch.object(imp, "analisar_documento", analisar), patch.object(imp, "classificar_documento", analisar):
            estado = await imp._importar_membro(
                _ZipFalso(), SimpleNamespace(filename="a/scan.pdf"), resumo, rede=REDE_INCUMBENTE, label="x",
                vistos=set(), classificar_sempre=False, permitir_simulado=True, guardar_ficheiro=guardar,
            )
        assert estado == "ja_importado" and analisar.await_count == 0
        # a chave é a da importação ORIGINAL da linha, não a desta execução
        assert guardar.await_args.args[0] == f"{PASTA_POWER}hist_y.pdf"
        assert resumo.ficheiros_guardados == 1

    async def test_falha_a_guardar_conta_e_nao_rebenta(self):
        resumo = imp.Resumo(import_id="imp123", process_id="p", rede=REDE_INCUMBENTE)
        linha = {"id": "hist_z", "network_id": REDE_INCUMBENTE, "import_id": "imp123"}
        with patch.object(imp.store, "ligar_ficheiro_historico", AsyncMock(return_value=True)) as ligar:
            await imp._guardar(linha, b"x", ".pdf", "application/pdf", resumo, AsyncMock(side_effect=RuntimeError("s3")))
            await imp._guardar(linha, b"x", ".pdf", "application/pdf", resumo, AsyncMock(return_value=False))
        assert resumo.ficheiros_falhados == 2 and resumo.ficheiros_guardados == 0
        ligar.assert_not_awaited()

    async def test_sem_guardar_ficheiro_comporta_se_como_antes(self):
        resumo = imp.Resumo(import_id="imp123", process_id="p", rede=REDE_INCUMBENTE)
        with patch.object(imp, "ler_membro", return_value=(b"%PDF", None)), \
                patch.object(imp.store, "ids_historicos_conhecidos", AsyncMock(side_effect=lambda ids: {ids[0]: "importado"})), \
                patch.object(imp.store, "linha_historica_sem_ficheiro", AsyncMock()) as sem_ficheiro:
            estado = await imp._importar_membro(
                _ZipFalso(), SimpleNamespace(filename="a/scan.pdf"), resumo, rede=REDE_INCUMBENTE, label="x",
                vistos=set(), classificar_sempre=False, permitir_simulado=True,
            )
        assert estado == "ja_importado"
        sem_ficheiro.assert_not_awaited()

    async def test_desfazer_apaga_tambem_os_ficheiros(self):
        apagar = AsyncMock(return_value=True)
        with patch.object(imp.store, "chaves_da_importacao_historica", AsyncMock(return_value=["k1", "k2"])), \
                patch.object(imp.store, "apagar_importacao_historica", AsyncMock(return_value=2)):
            assert await imp.desfazer_importacao("imp123", apagar_ficheiro=apagar) == 2
        assert [c.args[0] for c in apagar.await_args_list] == ["k1", "k2"]


def _filtros(**extra):
    base = dict(min_salary=None, max_salary=None, contract_type=None, employer_nif=None, employer_name=None,
                employer_location=None, job_title=None, period_from=None, period_to=None, sort="period_desc")
    return pesquisa.validar_filtros(**{**base, **extra})


class TestTudo:
    def test_todos_aceita_todos_os_filtros(self):
        f = _filtros(document_type="todos", bank="CGD", employer_name="Qiado", min_salary=1000)
        assert f["document_type"] == "todos"

    def test_todos_casa_com_os_tres_tipos(self):
        condicoes = pesquisa._condicoes_do_documento(_filtros(document_type="todos"), [])
        assert condicoes[0] == {"doc_type": {"$in": list(store.DOC_TYPES_PESQUISAVEIS)}}

    def test_um_tipo_continua_a_recusar_o_filtro_alheio(self):
        with pytest.raises(HTTPException) as e:
            _filtros(document_type="recibo", bank="CGD")
        assert e.value.status_code == 422

    def test_tipo_desconhecido_continua_422(self):
        with pytest.raises(HTTPException):
            _filtros(document_type="tudo_e_mais")


class TestHasFile:
    def test_historico_diz_se_tem_ficheiro_sem_mostrar_a_chave(self):
        com = pesquisa.resultado_do_documento({"id": "hist_a", "doc_type": "recibo", "historical": True, "s3_path": "k/x.pdf"})
        sem = pesquisa.resultado_do_documento({"id": "hist_b", "doc_type": "recibo", "historical": True})
        assert com["has_file"] is True and sem["has_file"] is False
        assert "s3_path" not in com and "k/x.pdf" not in str(com)

    def test_documento_normal_nao_leva_has_file(self):
        assert "has_file" not in pesquisa.resultado_do_documento({"id": "d", "doc_type": "recibo", "process_id": "p"})
