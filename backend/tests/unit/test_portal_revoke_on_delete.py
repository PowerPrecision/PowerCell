"""
Ficheiro apagado no CRM desaparece do Portal (Missão de Limpeza, ponto 6).

O DEFEITO
---------
`document_delete.run_delete_file_s3` apagava o objecto no S3 e o registo
em `document_metadata` — e NUNCA tocava em `db.documents`, que é onde o
Portal do Cliente guarda os pedidos com `status: RECEIVED`, `s3_path` e
`attached_files`.

Resultado: o cliente continuava a ver na sua área um documento que já não
existia. Clicar nele dava erro; e, pior, um pedido que o consultor tinha
apagado por estar ERRADO continuava a contar como satisfeito — o processo
avançava com um documento inexistente.

A OPERAÇÃO INVERSA
------------------
`document_portal_fulfill` faz REQUESTED→RECEIVED ao carregar. Apagar tem
de fazer o caminho de volta: tirar o ficheiro de `attached_files` e, se o
pedido deixar de estar satisfeito (contagem abaixo do pedido), devolvê-lo
a REQUESTED para o cliente o voltar a ver como pendente.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import document_portal_revoke
from services.document_portal_revoke import (
    revoke_portal_files_on_delete,
    rebuild_after_removal,
)

CAMINHO = "Documentação Clientes/Ana/Financeiros/recibo.pdf"
OUTRO = "Documentação Clientes/Ana/Financeiros/recibo2.pdf"


def _ficheiro(caminho, nome=None):
    return {
        "file_id": f"f-{caminho[-8:]}",
        "filename": nome or caminho.split("/")[-1],
        "s3_path": caminho,
        "uploaded_at": "2026-09-01T10:00:00Z",
    }


# ====================================================================
# A DECISÃO, ISOLADA E PURA
# ====================================================================


class TestReconstrucaoDoPedido:
    def test_pedido_de_um_ficheiro_volta_a_pendente(self):
        # O caso central: o único ficheiro foi apagado, logo o pedido
        # deixa de estar satisfeito e o cliente tem de o ver outra vez.
        estado = rebuild_after_removal(
            {"status": "RECEIVED", "attached_files": [_ficheiro(CAMINHO)]},
            removidos=[CAMINHO],
        )
        assert estado["status"] == "REQUESTED"
        assert estado["attached_files"] == []

    def test_pedido_de_tres_com_um_apagado_volta_a_pendente(self):
        estado = rebuild_after_removal(
            {
                "status": "RECEIVED",
                "expected_count": 3,
                "attached_files": [
                    _ficheiro(CAMINHO),
                    _ficheiro(OUTRO),
                    _ficheiro("x/c.pdf"),
                ],
            },
            removidos=[CAMINHO],
        )
        assert estado["status"] == "REQUESTED"
        assert estado["uploaded_count"] == 2

    def test_pedido_ainda_satisfeito_mantem_se_recebido(self):
        # Pedia 1, tinha 2, apagou-se 1: continua satisfeito.
        estado = rebuild_after_removal(
            {
                "status": "RECEIVED",
                "expected_count": 1,
                "attached_files": [_ficheiro(CAMINHO), _ficheiro(OUTRO)],
            },
            removidos=[CAMINHO],
        )
        assert estado["status"] == "RECEIVED"
        assert estado["uploaded_count"] == 1

    def test_o_ficheiro_de_topo_aponta_para_o_que_sobra(self):
        # Os campos de topo são o que o Portal mostra por omissão. Deixá-los
        # a apontar para o ficheiro apagado era metade do defeito.
        estado = rebuild_after_removal(
            {
                "status": "RECEIVED",
                "expected_count": 1,
                "s3_path": CAMINHO,
                "filename": "recibo.pdf",
                "attached_files": [_ficheiro(CAMINHO), _ficheiro(OUTRO)],
            },
            removidos=[CAMINHO],
        )
        assert estado["s3_path"] == OUTRO
        assert estado["filename"] == "recibo2.pdf"

    def test_sem_ficheiros_o_caminho_de_topo_e_limpo(self):
        estado = rebuild_after_removal(
            {"status": "RECEIVED", "s3_path": CAMINHO, "attached_files": [_ficheiro(CAMINHO)]},
            removidos=[CAMINHO],
        )
        assert estado["s3_path"] == ""
        assert estado["filename"] == ""

    def test_apagar_varios_de_uma_vez(self):
        estado = rebuild_after_removal(
            {
                "status": "RECEIVED",
                "expected_count": 2,
                "attached_files": [_ficheiro(CAMINHO), _ficheiro(OUTRO)],
            },
            removidos=[CAMINHO, OUTRO],
        )
        assert estado["attached_files"] == []
        assert estado["status"] == "REQUESTED"

    def test_caminho_que_nao_pertence_ao_pedido_nao_muda_nada(self):
        pedido = {
            "status": "RECEIVED",
            "expected_count": 1,
            "attached_files": [_ficheiro(OUTRO)],
        }
        estado = rebuild_after_removal(pedido, removidos=[CAMINHO])
        assert estado is None, "não devia haver nada a actualizar"

    def test_pedido_ja_pendente_nao_e_alterado_para_tras(self):
        estado = rebuild_after_removal(
            {"status": "REQUESTED", "attached_files": [_ficheiro(CAMINHO)]},
            removidos=[CAMINHO],
        )
        assert estado["status"] == "REQUESTED"

    def test_pedido_sem_attached_files_mas_com_s3_path_de_topo(self):
        # Pedidos legados, anteriores ao array.
        estado = rebuild_after_removal(
            {"status": "RECEIVED", "s3_path": CAMINHO},
            removidos=[CAMINHO],
        )
        assert estado["status"] == "REQUESTED"
        assert estado["s3_path"] == ""


# ====================================================================
# A OPERAÇÃO COMPLETA
# ====================================================================


def _db(pedidos):
    fake = MagicMock()

    class Cursor:
        def __aiter__(self):
            async def gen():
                for d in pedidos:
                    yield d
            return gen()

    fake.documents.find = MagicMock(return_value=Cursor())
    fake.documents.update_one = AsyncMock()
    return fake


class TestRevogacao:
    @pytest.mark.asyncio
    async def test_devolve_o_pedido_a_pendente_na_base_de_dados(self):
        pedido = {
            "id": "d-1",
            "process_id": "proc-1",
            "status": "RECEIVED",
            "attached_files": [_ficheiro(CAMINHO)],
        }
        fake = _db([pedido])
        with patch.object(document_portal_revoke, "db", fake):
            resultado = await revoke_portal_files_on_delete("proc-1", [CAMINHO])

        assert resultado["revoked"] == 1
        escrita = fake.documents.update_one.call_args[0][1]["$set"]
        assert escrita["status"] == "REQUESTED"

    @pytest.mark.asyncio
    async def test_sem_caminhos_nao_toca_na_base_de_dados(self):
        fake = _db([])
        with patch.object(document_portal_revoke, "db", fake):
            resultado = await revoke_portal_files_on_delete("proc-1", [])
        assert resultado["revoked"] == 0
        fake.documents.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_uma_falha_nunca_impede_a_eliminacao(self):
        # O ficheiro JÁ foi apagado do S3 quando isto corre. Levantar aqui
        # faria o utilizador ver um erro sobre uma operação bem sucedida.
        fake = _db([{"id": "d-1", "status": "RECEIVED",
                     "attached_files": [_ficheiro(CAMINHO)]}])
        fake.documents.update_one = AsyncMock(side_effect=RuntimeError("mongo"))
        with patch.object(document_portal_revoke, "db", fake):
            resultado = await revoke_portal_files_on_delete("proc-1", [CAMINHO])
        assert resultado["revoked"] == 0
        assert resultado.get("erro")


# ====================================================================
# A LIGAÇÃO À ELIMINAÇÃO (o que faltava de todo)
# ====================================================================


class TestLigacaoAoDelete:
    def test_a_eliminacao_individual_chama_a_revogacao(self):
        # Sem esta chamada, tudo o resto deste ficheiro é código morto: a
        # revogação funciona e ninguém a invoca.
        import inspect

        from services import document_delete

        fonte = inspect.getsource(document_delete.run_delete_file_s3)
        assert "revoke_portal_files_on_delete(" in fonte

    def test_a_eliminacao_em_massa_chama_a_revogacao(self):
        import inspect

        from services import document_delete

        fonte = inspect.getsource(document_delete.run_bulk_delete_files)
        assert "revoke_portal_files_on_delete(" in fonte

    def test_a_eliminacao_em_massa_limpa_os_metadados(self):
        # A individual limpava, a em massa não — os ficheiros apagados em
        # massa continuavam listados no CRM com badges e análises de IA.
        import inspect

        from services import document_delete

        fonte = inspect.getsource(document_delete.run_bulk_delete_files)
        assert "document_metadata.delete_many(" in fonte

    def test_a_revogacao_recebe_apenas_o_que_foi_mesmo_apagado(self):
        # Um ficheiro que falhou a eliminação continua a existir no S3: o
        # cliente TEM de continuar a vê-lo.
        import inspect

        from services import document_delete

        fonte = inspect.getsource(document_delete.run_bulk_delete_files)
        assert "revoke_portal_files_on_delete(process.get(\"id\"), deleted_paths)" in fonte
        assert "deleted_paths.append(file_path)" in fonte
