"""Anexar a um email ficheiros que já estão no PowerCell.

O caminho S3 vem do browser: cada teste de `TestGuardas` é uma tentativa de
o usar para tirar um ficheiro de onde não se deve (outra rede, outro
processo, `backups/`, a pasta `Index`). `TestCopia` prova que o documento do
cliente nunca é movido: o envio faz `rename_file` (copiar + apagar) do anexo
temporário, logo o anexo TEM de ser uma cópia.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import services.document_visibility as dv
from services import email_document_attachments as anexos
from services import email_send_queue
from tests.unit.helpers_tenant import (  # noqa: F401
    ANA, BRUNO, CARLA, REDE_INCUMBENTE, rede_de_omissao_incumbente, semear, tenant_db,
)

PASTA = "Documentação Clientes/c-ana/processos/p-ix"
RAIZ_CLIENTE = "Documentação Clientes/c-ana"
OUTRO_PROCESSO = "Documentação Clientes/c-ana/processos/p-outro"


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.processes.docs.append(
        {"id": "p-ix", "client_id": "c-ana", "client_name": "Ana", "status": "novo",
         "is_indexed": True, "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
         "s3_folder": PASTA}
    )
    fake_async_db.processes.docs.append(
        {"id": "p-apagado", "client_name": "Zé", "status": "eliminado", "is_deleted": True,
         "is_indexed": True, "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
         "s3_folder": "Documentação Clientes/c-ze"}
    )
    return fake_async_db


@pytest.fixture
def s3():
    falso = MagicMock()
    falso.head_object_metadata.return_value = ("ok", {"tamanho": 1234, "tipo": "application/pdf"})
    falso.copy_object_exact.return_value = True
    with patch("services.s3_storage.s3_service", falso):
        yield falso


async def _anexar(mundo, user, caminhos, process_id="p-ix"):
    with tenant_db(mundo, anexos, dv):
        return await anexos.run_anexar_documentos_do_processo(process_id, caminhos, user)


@pytest.mark.asyncio
class TestGuardas:
    async def test_diretor_de_outra_rede_nao_anexa(self, mundo, s3):
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, BRUNO, [f"{PASTA}/Pessoais/cc.pdf"])
        assert e.value.status_code == 403
        s3.copy_object_exact.assert_not_called()

    async def test_fora_da_raiz_documental_e_recusado(self, mundo, s3):
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, ANA, ["backups/2026-10-30.zip"])
        assert e.value.status_code == 403
        s3.copy_object_exact.assert_not_called()

    async def test_raiz_documental_vale_mesmo_que_a_posse_falhe_aberta(self, mundo, s3):
        """Defesa em profundidade: a guarda da raiz não depende da de posse."""
        with patch(
            "services.document_process_resolve.assert_s3_file_belongs_to_process",
            lambda *_a, **_k: None,
        ), pytest.raises(HTTPException) as e:
            await _anexar(mundo, ANA, ["backups/2026-10-30.zip"])
        assert e.value.status_code == 403
        s3.copy_object_exact.assert_not_called()

    async def test_ficheiro_de_outro_processo_recusa_o_pedido_inteiro(self, mundo, s3):
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, ANA, [
                f"{PASTA}/Pessoais/cc.pdf",
                f"{OUTRO_PROCESSO}/Financeiros/irs.pdf",
            ])
        assert e.value.status_code == 403
        # Nem o primeiro, legítimo, foi copiado.
        s3.copy_object_exact.assert_not_called()
        assert mundo.temp_attachments.docs == []

    async def test_pasta_vizinha_com_nome_prefixo_e_recusada(self, mundo, s3):
        with pytest.raises(HTTPException):
            await _anexar(mundo, ANA, [f"{PASTA}-x/Pessoais/cc.pdf"])

    async def test_subida_de_pasta_e_recusada(self, mundo, s3):
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, ANA, [f"{PASTA}/../p-outro/irs.pdf"])
        assert e.value.status_code == 403

    async def test_pasta_index_so_para_quem_a_ve(self, mundo, s3):
        caminho = f"{PASTA}/Index/recibo.pdf"
        # Carla (consultora) não vê a pasta cofre; a Ana (diretora) vê.
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, CARLA, [caminho])
        assert e.value.status_code == 403
        assert s3.copy_object_exact.call_count == 0
        resultado = await _anexar(mundo, ANA, [caminho])
        assert len(resultado["attachments"]) == 1

    async def test_processo_eliminado_da_404(self, mundo, s3):
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, ANA, ["Documentação Clientes/c-ze/x.pdf"], process_id="p-apagado")
        assert e.value.status_code == 404

    async def test_limite_de_ficheiros(self, mundo, s3):
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, ANA, [f"{PASTA}/f{i}.pdf" for i in range(11)])
        assert e.value.status_code == 400

    async def test_sem_ficheiros(self, mundo, s3):
        with pytest.raises(HTTPException) as e:
            await _anexar(mundo, ANA, [])
        assert e.value.status_code == 400


@pytest.mark.asyncio
class TestCopia:
    async def test_copia_para_temporarios_sem_tocar_no_original(self, mundo, s3):
        original = f"{PASTA}/Pessoais/cc.pdf"
        resultado = await _anexar(mundo, ANA, [original])

        [anexo] = resultado["attachments"]
        assert anexo["file_name"] == "cc.pdf"
        assert anexo["file_size"] == 1234
        assert anexo["temp_key"].startswith(f"temp/attachments/{ANA['id']}/")
        s3.copy_object_exact.assert_called_once_with(original, anexo["temp_key"])
        s3.rename_file.assert_not_called()
        s3.delete_file.assert_not_called()

        [registo] = mundo.temp_attachments.docs
        assert registo["id"] == anexo["id"]
        assert registo["user_id"] == ANA["id"]
        assert registo["source_s3_path"] == original
        assert registo["source_process_id"] == "p-ix"

    async def test_raiz_do_cliente_que_a_listagem_mostra_pode_ser_anexada(self, mundo, s3):
        resultado = await _anexar(mundo, ANA, [f"{RAIZ_CLIENTE}/Pessoais/cc_onboarding.pdf"])
        assert len(resultado["attachments"]) == 1

    async def test_ficheiro_grande_ou_ausente_e_reportado(self, mundo, s3):
        s3.head_object_metadata.side_effect = [
            ("ok", {"tamanho": 26 * 1024 * 1024, "tipo": "application/pdf"}),
            ("ausente", None),
            ("ok", {"tamanho": 10, "tipo": ""}),
        ]
        resultado = await _anexar(mundo, ANA, [
            f"{PASTA}/grande.pdf", f"{PASTA}/sumiu.pdf", f"{PASTA}/ok.jpg",
        ])
        assert [a["file_name"] for a in resultado["attachments"]] == ["ok.jpg"]
        assert resultado["attachments"][0]["mime_type"] == "image/jpeg"
        assert len(resultado["errors"]) == 2

    async def test_o_envio_encontra_o_anexo(self, mundo, s3):
        """O anexo entra no fluxo de envio de sempre, por `attachment_ids`."""
        resultado = await _anexar(mundo, ANA, [f"{PASTA}/Pessoais/cc.pdf"])
        s3.get_file_content.return_value = b"%PDF"
        record = {"attachment_ids": [resultado["attachments"][0]["id"]], "created_by": ANA["id"]}
        with patch.object(email_send_queue, "db", mundo):
            enviados, _registos, _limpar = await email_send_queue._prepare_temp_attachments(record)
        assert enviados == [{"filename": "cc.pdf", "content_bytes": b"%PDF", "content_type": "application/pdf"}]


@pytest.mark.asyncio
class TestListagem:
    async def test_lista_plana_sem_urls_e_sem_index_para_quem_nao_o_ve(self, mundo, s3):
        s3.list_files.return_value = {
            "files": {
                "Pessoais": [{"name": "cc.pdf", "path": f"{PASTA}/Pessoais/cc.pdf", "size": 10,
                              "category": "Pessoais", "temporary_url": "https://assinado"}],
                "Index": [{"name": "r.pdf", "path": f"{PASTA}/Index/r.pdf", "size": 5,
                           "category": "Index", "temporary_url": "https://assinado"}],
            },
            "stats": {"total_files": 2, "total_size": 15},
        }
        request = MagicMock()
        with tenant_db(mundo, anexos, dv), patch(
            "services.auth.get_effective_role_async", AsyncMock(return_value="consultor")
        ), patch(
            "services.index_substituicao.ids_substituidos", AsyncMock(return_value=set())
        ), patch("services.document_novelty.marcar_como_vistos", AsyncMock()) as vistos:
            resultado = await anexos.run_listar_documentos_para_anexar("p-ix", request, CARLA)

        assert [f["path"] for f in resultado["files"]] == [f"{PASTA}/Pessoais/cc.pdf"]
        assert "temporary_url" not in resultado["files"][0]
        assert resultado["em_indexacao"] == 1
        vistos.assert_not_called()

    async def test_outra_rede_nao_lista(self, mundo, s3):
        with tenant_db(mundo, anexos, dv), pytest.raises(HTTPException) as e:
            await anexos.run_listar_documentos_para_anexar("p-ix", MagicMock(), BRUNO)
        assert e.value.status_code == 403
        s3.list_files.assert_not_called()


def test_rotas_sem_process_id_no_caminho_do_post():
    """O POST não leva `{process_id}` no caminho: a guarda de processo fechado
    (que é de ESCRITA) não deve impedir anexar um documento de um processo
    concluído — e a leitura é guardada no serviço."""
    from routes.emails import router

    caminhos = {(r.path, tuple(sorted(r.methods))) for r in router.routes}
    assert ("/emails/attachments/from-documents", ("POST",)) in caminhos
    assert ("/emails/attachments/documents/{process_id}", ("GET",)) in caminhos
