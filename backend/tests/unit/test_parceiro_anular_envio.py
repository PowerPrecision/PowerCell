"""
PORTAL DO PARCEIRO — ANULAR UM ENVIO (Out 2026)

«O parceiro quando se engana no documento não tem como anular e voltar a
submeter.» O que se prova:

  1. anular retira o ficheiro do ecrã do parceiro e da aba Documentos do CRM,
     e o parceiro pode voltar a enviar;
  2. NADA se apaga: o registo fica com `is_deleted`/`status: eliminado`, o
     objecto S3 é MOVIDO (copiar → verificar → reapontar → retirar a origem)
     para a pasta dos anulados, dentro da raiz documental;
  3. um ficheiro dentro de um pedido sai de `attached_files`, vai para
     `attached_files_anulados`, e o pedido volta a pendente se era o único;
  4. só o próprio parceiro anula o que ELE enviou; caso alheio é 404 igual;
     a chave S3 envenenada é 403 antes de tocar no objecto;
  5. o que a equipa já tratou, um caso fechado e o comprovativo que já
     seguiu não se anulam (409, sem gravar nada);
  6. uma falha do S3 é 503 e não grava nada.
"""
from __future__ import annotations

import contextlib
import copy

import pytest
from fastapi import HTTPException

from tests.unit.test_parceiro_escrita import (  # noqa: F401
    CHAVE_BOA,
    _S3Falso,
    _confirmar,
    _mundo,
    com_bd as _com_bd_base,
    mundo,
    s3,
    tarefas,
    veredicto,
)
from tests.unit.helpers_tenant import rede_de_omissao_incumbente, tenant_db  # noqa: F401
from tests.unit.test_parceiro_leitura import PT1, PT2

ANULADOS = "Documentação Clientes/_Anulados pelo parceiro"


class _S3ComObjectos(_S3Falso):
    """Acrescenta ao falso da escrita um bucket mínimo (head/copy/delete por chave exacta)."""

    def __init__(self):
        super().__init__()
        self.objectos: dict[str, int] = {}
        self.falhar_copia = False

    def head_object_metadata(self, chave):
        self.chamadas.append(("head", chave))
        if chave in self.objectos:
            return "ok", {"tamanho": self.objectos[chave], "etag": f"e-{chave}"}
        return "ausente", None

    def copy_object_exact(self, origem, destino):
        self.chamadas.append(("copy", origem, destino))
        if self.falhar_copia or origem not in self.objectos:
            return False
        self.objectos[destino] = self.objectos[origem]
        return True

    def delete_file(self, chave):
        self.chamadas.append(("delete", chave))
        self.objectos.pop(chave, None)
        return True


@pytest.fixture
def s3():  # noqa: F811 — substitui o da escrita
    return _S3ComObjectos()


@pytest.fixture
def com_bd(_com_bd_base, s3):  # noqa: F811
    import services.partner_lead_files as lead_files
    import services.partner_upload_cancel as cancel
    from unittest.mock import patch

    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(_com_bd_base, cancel, lead_files))
        pilha.enter_context(patch.object(cancel, "s3_service", s3))
        pilha.enter_context(patch.object(lead_files, "s3_service", s3))
        yield _com_bd_base


async def _enviar(com_bd, s3, chave=CHAVE_BOA, **extra):
    import services.partner_upload_ops as ops

    s3.objectos[chave] = 2048
    return await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, key=chave, **extra))


def _doc(m, doc_id):
    return next(d for d in m.documents.docs if d["id"] == doc_id)


@pytest.mark.asyncio
class TestAnularUmEnvioSolto:
    async def test_desaparece_do_parceiro_e_pode_voltar_a_enviar(self, com_bd, s3):
        import services.partner_portal_read as ppr
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        resposta = await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert resposta["success"] is True

        detalhe = await ppr.run_get_case(PT1, "a-novo")
        assert detalhe["ficheiros"] == []

        # Volta a submeter o correcto.
        r2 = await _enviar(com_bd, s3, chave="Documentação Clientes/cli-a-novo/Index/cc-certo.pdf")
        detalhe = await ppr.run_get_case(PT1, "a-novo")
        assert [f["id"] for f in detalhe["ficheiros"]] == [r2["id"]]

    async def test_soft_delete_o_registo_fica_com_o_rasto(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        n = len(com_bd.documents.docs)
        await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert len(com_bd.documents.docs) == n, "nada se apaga fisicamente"
        doc = _doc(com_bd, r["id"])
        assert doc["is_deleted"] is True and doc["status"] == "eliminado"
        assert doc["anulado"]["por"] == "partner:pt-1"
        assert doc["anulado"]["s3_path_original"] == CHAVE_BOA

    async def test_o_objecto_e_movido_para_os_anulados_e_nunca_perdido(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        doc = _doc(com_bd, r["id"])
        assert doc["s3_path"].startswith(ANULADOS + "/a-novo/")
        assert doc["s3_path"] in s3.objectos, "a cópia existe"
        assert CHAVE_BOA not in s3.objectos, "a origem saiu da pasta do processo"
        ordem = [c[0] for c in s3.chamadas if c[0] in ("copy", "delete")]
        assert ordem == ["copy", "delete"], "copiar ANTES de retirar a origem"

    async def test_sai_da_aba_documentos_do_crm(self, com_bd, s3):
        from services.document_portal_request import build_portal_requests_query
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        consulta = build_portal_requests_query("a-novo", ["cli-a-novo"])
        assert await com_bd.documents.find_one({"$and": [consulta, {"id": r["id"]}]})
        await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert not await com_bd.documents.find_one({"$and": [consulta, {"id": r["id"]}]})

    async def test_os_metadados_desligam_se_do_processo_e_saem_da_fila(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        meta = next(m for m in com_bd.document_metadata.docs if m["s3_path"] == CHAVE_BOA)
        assert meta["in_index_queue"] is True
        await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert meta["process_id"] is None and meta["in_index_queue"] is False
        assert meta["anulado"]["process_id"] == "a-novo"
        assert meta["s3_path"].startswith(ANULADOS)

    async def test_anular_duas_vezes_e_404(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        with pytest.raises(HTTPException) as erro:
            await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert erro.value.status_code == 404


@pytest.mark.asyncio
class TestAnularDentroDeUmPedido:
    def _pedido(self, m):
        m.documents.docs.append({
            "id": "req-1", "process_id": "a-novo", "status": "REQUESTED", "source": "admin_request",
            "category": "Identificação", "created_at": "2026-10-04T10:00:00+00:00",
        })

    async def test_o_pedido_volta_a_pendente_e_o_ficheiro_fica_guardado_a_parte(self, com_bd, s3):
        import services.partner_portal_read as ppr
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        self._pedido(com_bd)
        r = await _enviar(com_bd, s3, request_id="req-1")
        assert _doc(com_bd, "req-1")["status"] == "RECEIVED"

        resposta = await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert resposta["pedido_reaberto"] is True
        pedido = _doc(com_bd, "req-1")
        assert pedido["status"] == "REQUESTED"
        assert pedido["attached_files"] == []
        assert [a["file_id"] for a in pedido["attached_files_anulados"]] == [r["id"]]
        assert pedido["attached_files_anulados"][0]["s3_path"].startswith(ANULADOS)
        detalhe = await ppr.run_get_case(PT1, "a-novo")
        assert detalhe["pedidos_pendentes"] == 1

    async def test_com_dois_ficheiros_so_sai_o_anulado_e_o_pedido_continua_cumprido(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        self._pedido(com_bd)
        r1 = await _enviar(com_bd, s3, request_id="req-1")
        r2 = await _enviar(com_bd, s3, chave="Documentação Clientes/cli-a-novo/Index/cc2.pdf", request_id="req-1")
        resposta = await cancel.run_partner_cancel_upload(PT1, "a-novo", r1["id"])
        assert resposta["pedido_reaberto"] is False
        pedido = _doc(com_bd, "req-1")
        assert pedido["status"] == "RECEIVED"
        assert [a["file_id"] for a in pedido["attached_files"]] == [r2["id"]]
        assert pedido["s3_path"] == "Documentação Clientes/cli-a-novo/Index/cc2.pdf"


@pytest.mark.asyncio
class TestQuemPodeAnular:
    async def test_outro_parceiro_recebe_404_e_nada_muda(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        antes = copy.deepcopy(com_bd.documents.docs)
        with pytest.raises(HTTPException) as erro:
            await cancel.run_partner_cancel_upload(PT2, "a-novo", r["id"])
        assert erro.value.status_code == 404
        assert com_bd.documents.docs == antes

    async def test_o_que_o_cliente_enviou_nao_se_anula_daqui(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        com_bd.documents.docs.append({
            "id": "do-cliente", "process_id": "a-novo", "status": "RECEIVED", "source": "client_portal",
            "s3_path": "Documentação Clientes/cli-a-novo/Index/irs.pdf", "filename": "irs.pdf",
            "uploaded_by": "portal_client",
        })
        with pytest.raises(HTTPException) as erro:
            await cancel.run_partner_cancel_upload(PT1, "a-novo", "do-cliente")
        assert erro.value.status_code == 403
        assert "is_deleted" not in _doc(com_bd, "do-cliente")
        assert s3.chamadas == []

    async def test_uma_chave_envenenada_e_403_sem_tocar_no_s3(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        com_bd.documents.docs.append({
            "id": "envenenado", "process_id": "a-novo", "status": "RECEIVED", "source": "partner_portal",
            "s3_path": "backups/dump.zip", "filename": "dump.zip", "uploaded_by": "partner:pt-1",
        })
        with pytest.raises(HTTPException) as erro:
            await cancel.run_partner_cancel_upload(PT1, "a-novo", "envenenado")
        assert erro.value.status_code == 403
        assert "is_deleted" not in _doc(com_bd, "envenenado")
        assert s3.chamadas == []


@pytest.mark.asyncio
class TestQuandoJaNaoSePodeAnular:
    async def test_o_que_o_index_ja_leu_nao_se_anula(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        meta = next(m for m in com_bd.document_metadata.docs if m["s3_path"] == CHAVE_BOA)
        meta["index_facts"] = {"tipo": "recibo"}
        with pytest.raises(HTTPException) as erro:
            await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert erro.value.status_code == 409
        assert "is_deleted" not in _doc(com_bd, r["id"])
        assert CHAVE_BOA in s3.objectos

    async def test_uma_falha_do_s3_e_503_e_nao_grava_nada(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        r = await _enviar(com_bd, s3)
        s3.falhar_copia = True
        with pytest.raises(HTTPException) as erro:
            await cancel.run_partner_cancel_upload(PT1, "a-novo", r["id"])
        assert erro.value.status_code == 503
        assert "is_deleted" not in _doc(com_bd, r["id"])
        assert CHAVE_BOA in s3.objectos

    async def test_um_caso_expirado_nao_se_altera(self, com_bd, s3):
        import services.partner_upload_cancel as cancel

        _mundo(com_bd)
        com_bd.documents.docs.append({
            "id": "f-lead", "client_id": "lead-1", "status": "RECEIVED", "source": "partner_portal",
            "s3_path": "Documentação Clientes/lead-1/Index/cc.pdf", "filename": "cc.pdf",
            "uploaded_by": "partner:pt-1",
        })
        lead = next(c for c in com_bd.clients.docs if c["id"] == "lead-1")
        lead["lead_status"] = "expired"
        with pytest.raises(HTTPException) as erro:
            await cancel.run_partner_cancel_upload(PT1, "lead-1", "f-lead")
        assert erro.value.status_code == 409


class TestJaFoiTratado:
    @pytest.mark.parametrize("meta", [
        None, {}, {"is_categorized": True, "ai_category": "Pessoais"},
        {"ai_review_status": "pending_review"},
    ])
    def test_a_categorizacao_automatica_nao_conta(self, meta):
        from services.partner_upload_cancel import ja_foi_tratado

        assert ja_foi_tratado(meta) is False

    @pytest.mark.parametrize("meta", [
        {"index_facts": {"tipo": "recibo"}}, {"ai_review_status": "approved"},
        {"ai_reviewed_by": "u-1"}, {"ai_applied_fields": ["nif"]},
        {"file_state": "sanitizado"}, {"is_clean_pdf": True},
    ])
    def test_o_que_alguem_da_equipa_decidiu_conta(self, meta):
        from services.partner_upload_cancel import ja_foi_tratado

        assert ja_foi_tratado(meta) is True

    def test_a_pasta_dos_anulados_esta_dentro_da_raiz_documental(self):
        from services.document_process_resolve import assert_path_within_document_root
        from services.partner_upload_cancel import chave_na_pasta_dos_anulados

        chave = chave_na_pasta_dos_anulados("a-novo", "../../x", "Documentação Clientes/c/Index/cc.pdf")
        assert ".." not in chave
        assert_path_within_document_root(chave)
