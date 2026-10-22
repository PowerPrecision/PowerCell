"""«Ver documento» e «Download» de cada linha da aba Documentos da bancada do Index (Out 2026).

`GET /index/processes/{process_id}/files/{document_id}/content[?download=true]`. Serve QUALQUER ficheiro do dossier do
processo (a bancada lista-o todo, a identificação incluída), mas só os DESSE processo — o resto da parede é a do
atalho da pesquisa: âmbito 404 uniforme, visibilidade, posse da chave, tecto, rasto na descarga.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import tenant_db
from tests.unit.test_index_precedencia_e_ver_documento import (  # noqa: F401 — `mundo` é uma fixture
    DIRETOR_DA_DOMUS,
    DIRETORA_DA_POWER,
    _s3,
    mundo,
)


async def _pedir(mundo, process_id, document_id, *, user=DIRETORA_DA_POWER, servico=None, descarregar=False, auditoria=None):
    import services.audit_trail_service as auditoria_real
    import services.document_visibility as dv
    import services.financial_validation as fv
    import services.index_document_content as idc

    servico = servico or _s3()[0]
    auditoria = auditoria if auditoria is not None else AsyncMock(return_value="evento")
    with tenant_db(mundo, idc, dv, fv), patch("services.s3_storage.s3_service", servico), \
            patch.object(auditoria_real, "log_audit_event", auditoria):
        resposta = await idc.run_conteudo_do_ficheiro_do_processo(
            user, process_id, document_id, descarregar=descarregar)
        corpo = b"".join([b async for b in resposta.body_iterator])
    return resposta, corpo


@pytest.mark.asyncio
class TestVerECarregarUmFicheiroDaBancada:
    async def test_serve_um_recibo_inline(self, mundo):
        resposta, corpo = await _pedir(mundo, "p-power", "d-recibo", servico=_s3(b"%PDF-1.4 x")[0])
        assert corpo == b"%PDF-1.4 x" and resposta.headers["content-disposition"].startswith("inline;")

    async def test_serve_a_identificacao_que_o_atalho_da_pesquisa_recusa(self, mundo):
        """A bancada lista o dossier inteiro: o Index tem de poder abrir o cartão de cidadão para o limpar."""
        resposta, _ = await _pedir(mundo, "p-power", "d-cc", servico=_s3(b"\xff\xd8\xff")[0])
        assert resposta.media_type == "image/jpeg"
        from services import index_document_content as idc

        with pytest.raises(HTTPException) as e:  # contraprova: o atalho da pesquisa continua a recusá-la
            import services.document_visibility as dv
            import services.financial_validation as fv

            with tenant_db(mundo, idc, dv, fv), patch("services.s3_storage.s3_service", _s3()[0]):
                await idc.run_conteudo_do_documento(DIRETORA_DA_POWER, "d-cc")
        assert e.value.status_code == 404

    async def test_serve_um_ficheiro_ainda_por_analisar(self, mundo):
        resposta, _ = await _pedir(mundo, "p-power", "d-sem-analise")
        assert resposta.status_code == 200

    async def test_a_descarga_sai_como_attachment_e_deixa_rasto_so_com_ids(self, mundo):
        auditoria = AsyncMock(return_value="evento")
        resposta, _ = await _pedir(mundo, "p-power", "d-recibo", descarregar=True, auditoria=auditoria)
        assert resposta.headers["content-disposition"].startswith("attachment;")
        kw = auditoria.await_args.kwargs
        assert kw["process_id"] == "p-power" and kw["metadata"]["document_id"] == "d-recibo"
        assert "ana_silva" not in repr(kw)

    async def test_ver_nao_deixa_rasto_de_descarga(self, mundo):
        auditoria = AsyncMock(return_value="evento")
        await _pedir(mundo, "p-power", "d-recibo", auditoria=auditoria)
        auditoria.assert_not_awaited()


@pytest.mark.asyncio
class TestAParedeDaBancada:
    async def test_um_ficheiro_de_OUTRO_processo_e_um_404_mesmo_dentro_da_minha_rede(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _pedir(mundo, "p-power", "d-domus", servico=servico)  # o documento é do p-domus
        assert e.value.status_code == 404
        cliente.get_object.assert_not_called()

    async def test_outra_rede_recebe_o_404_de_um_inexistente(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as alheio:
            await _pedir(mundo, "p-power", "d-recibo", user=DIRETOR_DA_DOMUS, servico=servico)
        with pytest.raises(HTTPException) as inexistente:
            await _pedir(mundo, "p-power", "nao-existe", user=DIRETOR_DA_DOMUS, servico=servico)
        assert (alheio.value.status_code, alheio.value.detail) == (inexistente.value.status_code, inexistente.value.detail)
        cliente.get_object.assert_not_called()

    async def test_um_processo_inexistente_ou_de_outra_rede_e_404(self, mundo):
        for pid in ("nao-existe", "p-domus"):
            with pytest.raises(HTTPException) as e:
                await _pedir(mundo, pid, "d-domus")
            assert e.value.status_code == 404, pid

    async def test_uma_chave_envenenada_nao_abre_o_bucket(self, mundo):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as e:
            await _pedir(mundo, "p-power", "d-veneno", servico=servico)
        assert e.value.status_code == 403
        cliente.get_object.assert_not_called()

    async def test_a_chave_de_outro_cliente_nao_abre(self, mundo):
        with pytest.raises(HTTPException) as e:
            await _pedir(mundo, "p-power", "d-outro-cliente")
        assert e.value.status_code == 403

    async def test_um_original_purgado_ja_nao_esta_na_bancada(self, mundo):
        with pytest.raises(HTTPException) as e:
            await _pedir(mundo, "p-power", "d-purgado")
        assert e.value.status_code == 404

    async def test_uma_recusa_nunca_deixa_rasto_de_descarga(self, mundo):
        auditoria = AsyncMock(return_value="evento")
        for pid, did, user in (("p-power", "d-veneno", DIRETORA_DA_POWER), ("p-power", "d-recibo", DIRETOR_DA_DOMUS),
                               ("p-power", "d-domus", DIRETORA_DA_POWER)):
            with pytest.raises(HTTPException):
                await _pedir(mundo, pid, did, user=user, descarregar=True, auditoria=auditoria)
        auditoria.assert_not_awaited()


class TestARota:
    def test_existe_com_download_falso_por_omissao_limite_e_perfis_do_index(self):
        from routes import index_module

        rota = next(r for r in index_module.router.routes if r.path.endswith("/processes/{process_id}/files/{document_id}/content"))
        assert rota.methods == {"GET"}
        assert inspect.signature(index_module.get_process_file_content).parameters["download"].default.default is False
        fonte = inspect.getsource(index_module.get_process_file_content)
        assert "run_conteudo_do_ficheiro_do_processo" in fonte and "request=request" in fonte
        assert "_acesso" in fonte
