"""«Arquivar no Processo» — do anexo de um email para o processo (Bloco 2).

A sugestão e o arquivo são duas perguntas: a primeira diz QUAL processo, a
segunda faz o upload pelo MESMO pipeline do CRM (desvio inteligente e guarda
de escrita da D-26 incluídos). Os testes do arquivo falseiam só o que sai do
processo (bytes do anexo, upload) e afirmam sobre os parâmetros que saem.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from services import document_upload as multipart
from services import email_archive as arquivo
from services import email_mailbox_ops
from services import webmail_scope
from services import document_visibility as dv
from tests.unit.helpers_tenant import (  # noqa: F401
    ANA, BRUNO, CARLA, REDE_DOMUS, REDE_INCUMBENTE, rede_de_omissao_incumbente, semear, tenant_db,
)

CLIENTE = "joana.cliente@gmail.com"


def _processo(pid, *, email=CLIENTE, rede=REDE_INCUMBENTE, empresa="cmp-power", **extra):
    return {
        "id": pid, "process_number": 7, "client_name": f"Cliente {pid}", "status": "novo",
        "client_email": email, "network_id": rede, "company_id": empresa,
        "is_indexed": True, "created_at": "2026-10-01", **extra,
    }


EMAIL_RECEBIDO = {
    "id": "em-1", "direction": "received", "from_email": f"Joana <{CLIENTE}>",
    "to_emails": ["ana@power.pt"], "company_id": "cmp-power",
    "attachments": [
        {"id": "a1", "filename": "cc.pdf", "content_type": "application/pdf"},
        {"id": "a2", "filename": "irs.pdf", "content_type": "application/pdf"},
    ],
}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.append(
        {"user_id": "u-carla", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "consultor", "is_default": False}
    )
    return fake_async_db


async def _sugerir(mundo, email, user=ANA, enderecos=("ana@power.pt",)):
    with tenant_db(mundo, arquivo, webmail_scope), patch.object(arquivo, "db", mundo), patch(
        "services.user_email_config_service.get_user_mailbox_addresses",
        AsyncMock(return_value=list(enderecos)),
    ):
        return await arquivo.sugerir_processos(dict(email), user)


@pytest.mark.asyncio
class TestASugestao:
    async def test_um_processo_activo_vem_pre_seleccionado(self, mundo):
        mundo.processes.docs.append(_processo("p-1"))
        res = await _sugerir(mundo, EMAIL_RECEBIDO)
        assert res["sugerido"] == "p-1"
        assert [s["process_id"] for s in res["sugestoes"]] == ["p-1"]
        assert res["sugestoes"][0]["motivo"] == "endereço do titular"
        assert res["ambiguo"] is False

    async def test_dois_processos_NAO_pre_seleccionam_nenhum(self, mundo):
        """Arquivar no processo errado é um cruzamento de dados."""
        mundo.processes.docs.extend([_processo("p-1"), _processo("p-2", created_at="2026-10-02")])
        res = await _sugerir(mundo, EMAIL_RECEBIDO)
        assert res["sugerido"] is None and res["ambiguo"] is True
        assert [s["process_id"] for s in res["sugestoes"]] == ["p-2", "p-1"]

    async def test_o_processo_ja_ligado_ao_email_e_a_decisao_tomada(self, mundo):
        mundo.processes.docs.extend([_processo("p-1"), _processo("p-2", created_at="2026-10-02")])
        res = await _sugerir(mundo, {**EMAIL_RECEBIDO, "process_id": "p-1"})
        assert res["sugerido"] == "p-1"
        assert res["sugestoes"][0]["ligado"] is True

    async def test_so_processos_activos(self, mundo):
        mundo.processes.docs.append(_processo("p-fechado", status="cancelado"))
        mundo.processes.docs.append(_processo("p-apagado", is_deleted=True))
        res = await _sugerir(mundo, EMAIL_RECEBIDO)
        assert res["sugestoes"] == [] and res["sugerido"] is None

    async def test_o_segundo_titular_e_os_enderecos_monitorizados_contam(self, mundo):
        mundo.processes.docs.append(_processo("p-t2", email="outro@x.pt", titular2_data={"email": CLIENTE}))
        mundo.processes.docs.append(_processo("p-mon", email="outro2@x.pt", monitored_emails=[CLIENTE]))
        res = await _sugerir(mundo, EMAIL_RECEBIDO)
        motivos = {s["process_id"]: s["motivo"] for s in res["sugestoes"]}
        assert motivos == {"p-t2": "endereço do 2.º titular", "p-mon": "endereço monitorizado"}

    async def test_a_comparacao_de_enderecos_e_exacta(self, mundo):
        mundo.processes.docs.append(_processo("p-1", email="oana.cliente@gmail.com"))
        res = await _sugerir(mundo, EMAIL_RECEBIDO)
        assert res["sugestoes"] == []

    async def test_email_enviado_usa_os_destinatarios_e_nao_o_proprio(self, mundo):
        mundo.processes.docs.append(_processo("p-1"))
        enviado = {
            "id": "em-2", "direction": "sent", "from_email": "ana@power.pt",
            "to_emails": [CLIENTE], "cc_emails": ["Ana <ana@power.pt>"], "attachments": [],
        }
        res = await _sugerir(mundo, enviado)
        assert res["enderecos"] == [CLIENTE]
        assert res["sugerido"] == "p-1"

    async def test_os_enderecos_do_proprio_utilizador_nunca_contam(self, mundo):
        mundo.processes.docs.append(_processo("p-meu", email="ana@power.pt"))
        res = await _sugerir(mundo, {**EMAIL_RECEBIDO, "from_email": "ana@power.pt"})
        assert res["enderecos"] == [] and res["sugestoes"] == []

    async def test_um_processo_de_outra_rede_nao_aparece_nem_revela_se(self, mundo):
        """O remetente é cliente da Domus: para a Ana (Power) não existe."""
        mundo.processes.docs.append(_processo("p-domus", rede=REDE_DOMUS, empresa="cmp-domus"))
        res = await _sugerir(mundo, EMAIL_RECEBIDO, user=ANA)
        assert res["sugestoes"] == [] and res["ambiguo"] is False

    async def test_a_ilha_ve_os_seus(self, mundo):
        mundo.processes.docs.append(_processo("p-domus", rede=REDE_DOMUS, empresa="cmp-domus"))
        res = await _sugerir(mundo, EMAIL_RECEBIDO, user=BRUNO, enderecos=("bruno@domus.pt",))
        assert res["sugerido"] == "p-domus"

    async def test_diz_se_o_processo_ja_passou_a_indexacao(self, mundo):
        """É o que decide se o ecrã pergunta a pasta ou avisa da Index."""
        mundo.processes.docs.append(_processo("p-ix"))
        mundo.processes.docs.append(_processo("p-novo", email="outro@x.pt", is_indexed=False, monitored_emails=[CLIENTE]))
        mundo.processes.docs.append(_processo("p-verde", email="v@x.pt", is_indexed=False, skip_index=True, monitored_emails=[CLIENTE]))
        res = await _sugerir(mundo, EMAIL_RECEBIDO)
        estado = {s["process_id"]: s["ja_indexado"] for s in res["sugestoes"]}
        assert estado == {"p-ix": True, "p-novo": False, "p-verde": True}

    async def test_a_resposta_nao_traz_dados_pessoais(self, mundo):
        mundo.processes.docs.append(_processo("p-1", titular2_data={"email": "t2@x.pt", "nif": "123456789"}))
        res = await _sugerir(mundo, EMAIL_RECEBIDO)
        texto = str(res)
        assert "123456789" not in texto and "t2@x.pt" not in texto


class _Env:
    def __init__(self, upload, conteudo):
        self.upload, self.conteudo = upload, conteudo


@pytest.fixture
def ambiente_arquivo(mundo):
    mundo.emails.docs.append(dict(EMAIL_RECEBIDO))
    upload = AsyncMock(return_value={
        "success": True, "path": "Documentação Clientes/c/Index/cc.pdf", "category": "Index",
        "intake": {"fila_ia": True},
    })

    def montar(conteudo=b"%PDF-1.4 conteudo"):
        return [
            patch.object(arquivo, "db", mundo),
            patch.object(multipart, "run_upload_file_s3", upload),
            patch.object(email_mailbox_ops, "_load_attachment_bytes", AsyncMock(return_value=conteudo)),
        ]

    return upload, montar


async def _arquivar(mundo, patches, user=CARLA, anexo="a1", dados=None, email=None):
    for p in patches:
        p.start()
    try:
        return await arquivo.arquivar_anexo(
            dict(email or mundo.emails.docs[0]), anexo, dados if dados is not None else {"process_id": "p-1"},
            user, BackgroundTasks(),
        )
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
class TestOArquivo:
    async def test_passa_pelo_upload_do_CRM_com_os_bytes_do_anexo(self, mundo, ambiente_arquivo):
        upload, montar = ambiente_arquivo
        res = await _arquivar(mundo, montar(b"%PDF-1.4 bytes"))
        kw = upload.call_args.kwargs
        assert upload.call_args.args == ("p-1",)
        assert kw["file_content"] == b"%PDF-1.4 bytes"
        assert kw["original_filename"] == "cc.pdf"
        assert kw["origem"] == "email"
        assert kw["category"] == "Outros"
        assert kw["user"] == CARLA
        assert res["archived"] is True and res["process_id"] == "p-1"

    async def test_a_categoria_pedida_segue(self, mundo, ambiente_arquivo):
        upload, montar = ambiente_arquivo
        await _arquivar(mundo, montar(), dados={"process_id": "p-1", "category": "Financeiros"})
        assert upload.call_args.kwargs["category"] == "Financeiros"

    async def test_regista_no_anexo_onde_foi_arquivado(self, mundo, ambiente_arquivo):
        _, montar = ambiente_arquivo
        await _arquivar(mundo, montar())
        email = await mundo.emails.find_one({"id": "em-1"})
        registo = email["attachments"][0]["archived_to"][0]
        assert registo["process_id"] == "p-1" and registo["archived_by"] == "u-carla"
        assert "archived_to" not in email["attachments"][1]  # o outro anexo não se toca

    async def test_arquivar_de_novo_no_mesmo_processo_nao_duplica(self, mundo, ambiente_arquivo):
        upload, montar = ambiente_arquivo
        await _arquivar(mundo, montar())
        res = await _arquivar(mundo, montar())
        assert upload.await_count == 1
        assert res["already_archived"] is True

    async def test_outro_processo_arquiva_de_novo(self, mundo, ambiente_arquivo):
        upload, montar = ambiente_arquivo
        await _arquivar(mundo, montar())
        await _arquivar(mundo, montar(), dados={"process_id": "p-2"})
        assert upload.await_count == 2

    @pytest.mark.parametrize("perfil", ["indexacao", "parceiro", "cliente"])
    async def test_quem_nao_trata_documentos_nao_arquiva(self, mundo, ambiente_arquivo, perfil):
        upload, montar = ambiente_arquivo
        with pytest.raises(HTTPException) as exc:
            await _arquivar(mundo, montar(), user={"id": "u-x", "role": perfil})
        assert exc.value.status_code == 403
        upload.assert_not_called()

    @pytest.mark.parametrize("perfil", ["admin", "ceo", "diretor", "administrativo", "consultor", "intermediario"])
    async def test_quem_trata_documentos_arquiva(self, mundo, ambiente_arquivo, perfil):
        upload, montar = ambiente_arquivo
        await _arquivar(mundo, montar(), user={"id": "u-x", "role": perfil})
        upload.assert_awaited_once()

    async def test_sem_processo_e_400(self, mundo, ambiente_arquivo):
        _, montar = ambiente_arquivo
        with pytest.raises(HTTPException) as exc:
            await _arquivar(mundo, montar(), dados={})
        assert exc.value.status_code == 400

    async def test_anexo_desconhecido_e_404(self, mundo, ambiente_arquivo):
        _, montar = ambiente_arquivo
        with pytest.raises(HTTPException) as exc:
            await _arquivar(mundo, montar(), anexo="nao-existe")
        assert exc.value.status_code == 404

    async def test_sem_conteudo_e_404(self, mundo, ambiente_arquivo):
        upload, montar = ambiente_arquivo
        with pytest.raises(HTTPException) as exc:
            await _arquivar(mundo, montar(conteudo=None))
        assert exc.value.status_code == 404
        upload.assert_not_called()

    async def test_anexo_enorme_e_413(self, mundo, ambiente_arquivo, monkeypatch):
        upload, montar = ambiente_arquivo
        monkeypatch.setattr(arquivo, "TAMANHO_MAXIMO_BYTES", 10)
        with pytest.raises(HTTPException) as exc:
            await _arquivar(mundo, montar(conteudo=b"x" * 11))
        assert exc.value.status_code == 413
        upload.assert_not_called()

    async def test_o_utilizador_silenciado_nao_deixa_archived_by(self, mundo, ambiente_arquivo):
        _, montar = ambiente_arquivo
        silencioso = {**CARLA, "track_history": False}
        await _arquivar(mundo, montar(), user=silencioso)
        email = await mundo.emails.find_one({"id": "em-1"})
        assert "archived_by" not in email["attachments"][0]["archived_to"][0]

    async def test_se_o_registo_no_email_falha_o_arquivo_mantem_se(self, mundo, ambiente_arquivo):
        _, montar = ambiente_arquivo
        patches = montar()
        with patch.object(arquivo, "_registar_arquivo", AsyncMock(side_effect=None)):
            res = await _arquivar(mundo, patches)
        assert res["archived"] is True


@pytest.mark.asyncio
class TestOArquivoPassaPelaParedeDaD26:
    async def test_o_diretor_de_uma_ilha_nao_arquiva_no_processo_da_power(self, mundo):
        """O pipeline REAL: a guarda de escrita recusa antes de tocar no S3."""
        mundo.processes.docs.append(_processo("p-1"))
        mundo.emails.docs.append(dict(EMAIL_RECEBIDO))
        s3 = MagicMock()
        s3.is_configured.return_value = True
        with tenant_db(mundo, dv), patch.object(dv, "db", mundo), patch.object(arquivo, "db", mundo), \
                patch.object(multipart, "s3_service", s3), patch.object(multipart, "db", mundo), \
                patch("services.document_process_resolve.db", mundo), \
                patch.object(email_mailbox_ops, "_load_attachment_bytes", AsyncMock(return_value=b"%PDF-1.4")):
            with pytest.raises(HTTPException) as exc:
                await arquivo.arquivar_anexo(
                    dict(mundo.emails.docs[0]), "a1", {"process_id": "p-1"}, BRUNO, BackgroundTasks(),
                )
        assert exc.value.status_code == 403
        s3.upload_file.assert_not_called()


class TestAFonte:
    def test_o_arquivo_nao_tem_pipeline_proprio(self):
        """Duas implementações do mesmo desvio divergem sem dar erro."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(arquivo.arquivar_anexo)
        assert "run_upload_file_s3(" in fonte
        assert "s3_service" not in fonte and "upload_file(" not in fonte.replace("run_upload_file_s3(", "")

    def test_as_rotas_novas_estao_guardadas_e_limitadas(self):
        from routes import emails
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        sugestao = codigo_da_funcao_sem_comentarios(emails.archive_suggestions)
        assert "carregar_email_legivel(email_id, current_user)" in sugestao
        post = codigo_da_funcao_sem_comentarios(emails.archive_attachment)
        assert "carregar_email_legivel(email_id, current_user)" in post
        import inspect
        params = inspect.signature(emails.archive_attachment).parameters
        # `@limiter.limit` exige `request` e `response` na assinatura.
        assert "request" in params and "response" in params
