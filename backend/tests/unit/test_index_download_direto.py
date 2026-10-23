"""«Download» da pesquisa avançada do Index: `GET /index/documents/{id}/content?download=true` (Out 2026).

É o MESMO caminho do «Ver documento» com `Content-Disposition: attachment`: a parede (rede, visibilidade, posse da
chave, os três tipos) não se afrouxa para descarregar. O que muda — e está afirmado aqui — é o cabeçalho, o tecto, o
tipo declarado, e que uma descarga deixa rasto de auditoria.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import index_ai as ia
from services.previsualizacao_de_ficheiros import (
    MAX_BYTES_DA_PREVISUALIZACAO,
    MAX_BYTES_DO_DOWNLOAD,
    nome_para_o_cabecalho,
    tipo_de_descarga,
)
from tests.unit.helpers_tenant import tenant_db
from tests.unit.test_index_precedencia_e_ver_documento import (  # noqa: F401 — `mundo` é uma fixture
    DIRETOR_DA_DOMUS,
    DIRETORA_DA_POWER,
    PASTA,
    _s3,
    mundo,
)


async def _descarregar(mundo, document_id, *, user=DIRETORA_DA_POWER, servico=None, descarregar=True, auditoria=None):
    import services.audit_trail_service as auditoria_real
    import services.document_visibility as dv
    import services.financial_validation as fv
    import services.index_document_content as idc

    servico = servico or _s3()[0]
    auditoria = auditoria if auditoria is not None else AsyncMock(return_value="evento")
    with tenant_db(mundo, idc, dv, fv), patch("services.s3_storage.s3_service", servico), \
            patch.object(auditoria_real, "log_audit_event", auditoria):
        resposta = await idc.run_conteudo_do_documento(user, document_id, descarregar=descarregar)
        corpo = b"".join([b async for b in resposta.body_iterator])
    return resposta, corpo


@pytest.mark.asyncio
class TestOCabecalhoDaDescarga:
    async def test_sai_como_attachment_com_o_nome_do_registo(self, mundo):
        resposta, corpo = await _descarregar(mundo, "d-recibo", servico=_s3(b"%PDF-1.4 bytes")[0])
        disposicao = resposta.headers["content-disposition"]
        assert disposicao.startswith("attachment;")
        assert 'filename="recibo_ana_silva.pdf"' in disposicao and "filename*=UTF-8''recibo_ana_silva.pdf" in disposicao
        assert corpo == b"%PDF-1.4 bytes" and resposta.media_type == "application/pdf"

    async def test_sem_o_parametro_continua_inline(self, mundo):
        """O «Ver documento» não mudou: a descarga é opt-in."""
        resposta, _ = await _descarregar(mundo, "d-recibo", descarregar=False)
        assert resposta.headers["content-disposition"].startswith("inline;")

    async def test_mantem_nosniff_e_no_store(self, mundo):
        resposta, _ = await _descarregar(mundo, "d-recibo")
        assert resposta.headers["x-content-type-options"] == "nosniff"
        assert "no-store" in resposta.headers["cache-control"]

    async def test_um_tipo_sem_previsualizacao_DESCARREGA_em_vez_de_dar_415(self, mundo):
        """`.docx` não se mostra no ecrã (415) mas pode guardar-se, com o tipo do nome e `nosniff`."""
        servico, cliente = _s3(b"PK-docx")
        resposta, corpo = await _descarregar(mundo, "d-docx", servico=servico)
        assert corpo == b"PK-docx"
        assert resposta.media_type.startswith("application/vnd.openxmlformats")
        assert resposta.headers["content-disposition"].startswith("attachment;")
        with pytest.raises(HTTPException) as e:
            await _descarregar(mundo, "d-docx", descarregar=False)
        assert e.value.status_code == 415

    async def test_o_tecto_da_descarga_e_maior_que_o_da_previsualizacao(self, mundo):
        entre = MAX_BYTES_DA_PREVISUALIZACAO + 1
        assert entre < MAX_BYTES_DO_DOWNLOAD
        resposta, _ = await _descarregar(mundo, "d-recibo", servico=_s3(b"x", tamanho=entre)[0])
        assert resposta.status_code == 200
        with pytest.raises(HTTPException) as e:
            await _descarregar(mundo, "d-recibo", descarregar=False, servico=_s3(b"x", tamanho=entre)[0])
        assert e.value.status_code == 413

    async def test_acima_do_tecto_da_descarga_da_413_sem_ler_os_bytes(self, mundo):
        servico, cliente = _s3(b"x", tamanho=MAX_BYTES_DO_DOWNLOAD + 1)
        with pytest.raises(HTTPException) as e:
            await _descarregar(mundo, "d-recibo", servico=servico)
        assert e.value.status_code == 413
        assert "descarregar" in e.value.detail

    async def test_o_original_purgado_descarrega_o_pdf_limpo(self, mundo):
        """O nome mostrado diz `.jpg`; a chave é o PDF limpo: o tipo e a chave são os do que SAI."""
        servico, cliente = _s3(b"%PDF-limpo")
        resposta, corpo = await _descarregar(mundo, "d-purgado", servico=servico)
        assert resposta.media_type == "application/pdf" and corpo == b"%PDF-limpo"
        cliente.get_object.assert_called_once_with(Bucket="bkt", Key=f"{PASTA}/recibo_limpo.pdf")


class TestONomeNoCabecalho:
    def test_sem_caminhos_aspas_nem_quebras_de_linha(self):
        ascii_, utf8 = nome_para_o_cabecalho('..\\..\\x/Rec"ibo\r\nSet-Cookie: a=b.pdf')
        assert "\r" not in ascii_ + utf8 and "\n" not in ascii_ + utf8
        assert '"' not in ascii_ and "/" not in ascii_ and "\\" not in ascii_
        assert ascii_.endswith(".pdf")

    def test_acentos_ficam_no_utf8_e_perdem_se_no_ascii(self):
        ascii_, utf8 = nome_para_o_cabecalho("Declaração João.pdf")
        assert ascii_ == "Declaracao Joao.pdf"
        assert utf8 == "Declara%C3%A7%C3%A3o%20Jo%C3%A3o.pdf"

    def test_vazio_ou_so_lixo_cai_num_nome_seguro(self):
        assert nome_para_o_cabecalho("")[0] == "ficheiro"
        assert nome_para_o_cabecalho("///")[0] == "ficheiro"

    def test_tem_tecto_de_comprimento(self):
        assert len(nome_para_o_cabecalho("a" * 1000 + ".pdf")[0]) <= 150

    def test_o_tipo_de_uma_descarga_e_sempre_um_valor(self):
        assert tipo_de_descarga("x.pdf") == "application/pdf"
        assert tipo_de_descarga("x.desconhecida") == "application/octet-stream"
        assert tipo_de_descarga(None) == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_um_nome_malicioso_no_registo_nao_parte_o_cabecalho(self, mundo):
        for d in mundo.document_metadata.docs:
            if d["id"] == "d-recibo":
                d["filename"] = 'a"b\r\nX-Injectado: 1.pdf'
        resposta, _ = await _descarregar(mundo, "d-recibo")
        valor = resposta.headers["content-disposition"]
        assert "\r" not in valor and "\n" not in valor and "X-Injectado" in valor  # ficou DENTRO do nome, inofensivo
        assert "x-injectado" not in {k.lower() for k in resposta.headers.keys()}


@pytest.mark.asyncio
class TestAParedeNaoAfrouxaParaDescarregar:
    """O ataque, escrito primeiro: cada recusa do «Ver documento» é a MESMA recusa da descarga."""

    async def test_outra_rede_recebe_o_404_de_um_inexistente(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as alheio:
            await _descarregar(mundo, "d-recibo", user=DIRETOR_DA_DOMUS, servico=servico)
        with pytest.raises(HTTPException) as inexistente:
            await _descarregar(mundo, "nao-existe", user=DIRETOR_DA_DOMUS, servico=servico)
        assert (alheio.value.status_code, alheio.value.detail) == (inexistente.value.status_code, inexistente.value.detail)
        cliente.get_object.assert_not_called()

    async def test_a_identificacao_nunca_sai_por_aqui(self, mundo):
        for i in ("d-cc", "d-sem-analise"):
            with pytest.raises(HTTPException) as e:
                await _descarregar(mundo, i)
            assert e.value.status_code == 404, i

    async def test_uma_chave_envenenada_nao_abre_o_bucket_nem_a_descarregar(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _descarregar(mundo, "d-veneno", servico=servico)
        assert e.value.status_code == 403
        cliente.get_object.assert_not_called()

    async def test_a_chave_de_outro_cliente_nao_abre(self, mundo):
        with pytest.raises(HTTPException) as e:
            await _descarregar(mundo, "d-outro-cliente")
        assert e.value.status_code == 403

    async def test_um_processo_eliminado_nao_serve(self, mundo):
        for p in mundo.processes.docs:
            if p["id"] == "p-power":
                p["is_deleted"] = True
        with pytest.raises(HTTPException) as e:
            await _descarregar(mundo, "d-recibo")
        assert e.value.status_code == 404


@pytest.mark.asyncio
class TestORastoDeAuditoria:
    async def test_uma_descarga_deixa_rasto_so_com_ids_e_o_papel_efectivo(self, mundo):
        auditoria = AsyncMock(return_value="evento")
        await _descarregar(mundo, "d-recibo", auditoria=auditoria)
        auditoria.assert_awaited_once()
        kw = auditoria.await_args.kwargs
        assert kw["process_id"] == "p-power"
        assert kw["metadata"]["document_id"] == "d-recibo" and kw["metadata"]["papel_efectivo"] == "diretor"
        assert "ana_silva" not in repr(kw) and "recibo_ana" not in repr(kw)  # nunca o nome do ficheiro (leva o do cliente)

    async def test_ver_nao_deixa_rasto_de_descarga(self, mundo):
        auditoria = AsyncMock(return_value="evento")
        await _descarregar(mundo, "d-recibo", descarregar=False, auditoria=auditoria)
        auditoria.assert_not_awaited()

    async def test_uma_descarga_recusada_nao_deixa_rasto(self, mundo):
        auditoria = AsyncMock(return_value="evento")
        for i, utilizador in (("d-veneno", DIRETORA_DA_POWER), ("d-recibo", DIRETOR_DA_DOMUS), ("d-cc", DIRETORA_DA_POWER)):
            with pytest.raises(HTTPException):
                await _descarregar(mundo, i, user=utilizador, auditoria=auditoria)
        auditoria.assert_not_awaited()

    async def test_um_ficheiro_ausente_no_s3_nao_deixa_rasto(self, mundo):
        from botocore.exceptions import ClientError

        servico, cliente = _s3()
        cliente.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        auditoria = AsyncMock(return_value="evento")
        with pytest.raises(HTTPException) as e:
            await _descarregar(mundo, "d-recibo", servico=servico, auditoria=auditoria)
        assert e.value.status_code == 404
        auditoria.assert_not_awaited()

    async def test_a_auditoria_a_falhar_nunca_derruba_a_descarga(self, mundo):
        auditoria = AsyncMock(side_effect=RuntimeError("base de dados em baixo"))
        resposta, corpo = await _descarregar(mundo, "d-recibo", auditoria=auditoria, servico=_s3(b"%PDF-1.4 x")[0])
        assert corpo == b"%PDF-1.4 x"
        auditoria.assert_awaited_once()


class TestARotaAceitaODownload:
    def _funcao(self):
        fonte = (Path(__file__).resolve().parents[2] / "routes" / "index_module.py").read_text(encoding="utf-8")
        return next(n for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_document_content")

    def test_o_parametro_download_existe_e_por_omissao_e_falso(self):
        f = self._funcao()
        nomes = [a.arg for a in f.args.args]
        assert "download" in nomes
        padrao = f.args.defaults[nomes.index("download") - (len(nomes) - len(f.args.defaults))]
        assert "False" in ast.unparse(padrao)

    def test_a_rota_passa_o_download_e_o_request_ao_servico(self):
        corpo = ast.unparse(self._funcao())
        assert "descarregar=download" in corpo and "request=request" in corpo

    def test_continua_com_limite_e_so_para_os_perfis_do_index(self):
        f = self._funcao()
        assert any("limiter.limit" in ast.unparse(d) for d in f.decorator_list)
        assert "_acesso" in ast.unparse(f)
