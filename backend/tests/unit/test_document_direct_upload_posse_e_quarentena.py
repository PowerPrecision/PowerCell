"""D-1 — o `confirm-upload` do CRM: posse, quarentena, e o URL que saiu.

O QUE ESTAVA MAL — É O INCIDENTE P0 DO PORTAL, NO CRM
=====================================================
`run_confirm_upload` recebia o `file_key` do CORPO do pedido e validava-o
só com `s3_service.file_exists()`. Não havia guarda de posse NENHUMA
neste ficheiro (zero ocorrências de `assert_`). E a resposta trazia
`temporary_url` — um URL pré-assinado para a chave que o cliente
nomeara.

No mesmo bucket vivem os documentos de TODAS as redes, os
`backups/*.zip` e os `companies/*`. Um membro da equipa com sessão
válida — incluindo um consultor da Domus, que é uma ilha — nomeava
`backups/dump-2026-09-01.zip` e recebia o URL para o descarregar. Pior:
o registo criado com esse `s3_path` fazia os caminhos de download
autorizarem a chave depois disso.

O registo de dívida classificava a D-1 como "integridade de dados e
higiene do bucket" e dizia explicitamente "não é escalada de
privilégio". Era, e a razão de o diagnóstico ter falhado é conhecida: a
entrada foi escrita a olhar para a quarentena de magic bytes que faltava
e **não para o `file_key` que ninguém validava**.

A ORDEM É A REGRA
=================
Posse ANTES de conteúdo. Invertida, o backend passava a ler 2 KB de
qualquer chave que um utilizador nomeasse — um oráculo feito com a
própria parede.

Os testes de `TestAExploracao` são o ataque, escritos para morder
primeiro: são eles que falham se alguém apagar uma das guardas.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services import document_direct_upload as modulo
from services.s3_content_quarantine import (
    MOTIVO_APROVADO,
    MOTIVO_CONTEUDO,
    Veredicto,
)

PROCESSO = {
    "id": "p-1",
    "process_number": 42,
    "client_name": "Ana Cliente",
    "s3_folder": "Documentação Clientes/Ana Cliente",
}

APROVADO = Veredicto(
    aprovado=True,
    motivo=MOTIVO_APROVADO,
    detalhe="",
    tamanho=1024,
    tipo_detectado="application/pdf",
)


def _pedido(file_key: str, **extra):
    base = {
        "process_id": "p-1",
        "file_key": file_key,
        "original_filename": "cc.pdf",
        "category": "Identificação",
    }
    base.update(extra)
    return base


async def _correr(dados, *, veredicto=APROVADO, processo=PROCESSO):
    """Corre o handler real com as fronteiras de I/O falseadas.

    A base de dados, o S3 e os efeitos secundários são duplos; as
    guardas, a ordem e a resposta são os REAIS.
    """
    db_falso = MagicMock()
    db_falso.processes.find_one = AsyncMock(return_value=processo)

    quarentena = AsyncMock(return_value=veredicto)

    with patch.object(modulo, "db", db_falso), \
            patch.object(modulo, "exigir_conteudo_valido", quarentena), \
            patch.object(modulo.s3_service, "get_file_content", return_value=None), \
            patch.object(modulo, "log_history", AsyncMock()), \
            patch.object(
                modulo, "_auto_fulfill_portal_request",
                AsyncMock(return_value={"fulfilled": 0}),
            ), \
            patch("services.document_intake.db", db_falso):
        resposta = await modulo.run_confirm_upload(
            dados, background_tasks=MagicMock(), user={"id": "u-1", "name": "Ana"}
        )
    return resposta, quarentena



@pytest.fixture(autouse=True)
def _sem_guarda_de_escrita():
    """A guarda de ESCRITA na pasta do processo (Bloco 2) tem a sua bateria
    (`test_escrita_na_pasta_do_processo.py`); aqui testa-se a posse da CHAVE
    e a quarentena, e a guarda precisaria de um âmbito de rede resolvido."""
    with patch.object(modulo, "assert_can_upload_to_process", AsyncMock()):
        yield


class TestAExploracao:
    """O ataque. Escrito para morder primeiro."""

    @pytest.mark.parametrize(
        "chave",
        [
            "backups/dump-2026-09-01.zip",
            "companies/power/logo.png",
            "system/credenciais.json",
        ],
    )
    async def test_uma_chave_fora_da_arvore_de_documentos_e_recusada(self, chave):
        with pytest.raises(HTTPException) as erro:
            await _correr(_pedido(chave))
        assert erro.value.status_code == 403

    async def test_o_documento_do_processo_do_VIZINHO_e_recusado(self):
        """Dentro da árvore de documentos, mas de outro cliente."""
        with pytest.raises(HTTPException) as erro:
            await _correr(
                _pedido("Documentação Clientes/Bruno Vizinho/cc.pdf")
            )
        assert erro.value.status_code == 403

    async def test_a_recusa_acontece_ANTES_de_se_tocar_no_objecto(self):
        """A ordem é a regra: senão a parede vira oráculo.

        Se o conteúdo fosse inspeccionado antes da posse, o backend lia
        2 KB de qualquer chave que o utilizador nomeasse.
        """
        with pytest.raises(HTTPException):
            _, quarentena = await _correr(_pedido("backups/dump.zip"))

        # Reconstituído fora do `raises` para poder afirmar sobre o duplo.
        quarentena = AsyncMock(return_value=APROVADO)
        db_falso = MagicMock()
        db_falso.processes.find_one = AsyncMock(return_value=PROCESSO)
        with patch.object(modulo, "db", db_falso), \
                patch.object(modulo, "exigir_conteudo_valido", quarentena):
            with pytest.raises(HTTPException):
                await modulo.run_confirm_upload(
                    _pedido("backups/dump.zip"),
                    background_tasks=MagicMock(),
                    user={"id": "u-1"},
                )
        quarentena.assert_not_awaited()


class TestSemDonoRecusaSe:
    """O degradado da guarda partilhada aceita a RAIZ inteira.

    `assert_s3_file_belongs_to_process`, sem `s3_folder`, monta os
    prefixos válidos a partir do `client_name`. Com o nome vazio, os dois
    prefixos colapsam em `"Documentação Clientes/"` — e a guarda deixa de
    guardar. É a mesma armadilha que o `portal_upload_ops` fecha com o
    `_dono_do_prefixo_s3` a devolver `None`.
    """

    SEM_DONO = {"id": "p-1", "process_number": 7}

    async def test_processo_sem_pasta_nem_nome_recusa(self):
        with pytest.raises(HTTPException) as erro:
            await _correr(
                _pedido("Documentação Clientes/Quem Calhar/cc.pdf"),
                processo=self.SEM_DONO,
            )
        assert erro.value.status_code == 403

    async def test_nome_so_com_espacos_tambem_recusa(self):
        with pytest.raises(HTTPException):
            await _correr(
                _pedido("Documentação Clientes/Quem Calhar/cc.pdf"),
                processo={**self.SEM_DONO, "client_name": "   "},
            )

    async def test_CONTRAPROVA_com_pasta_mas_sem_nome_continua_a_passar(self):
        """A recusa é por não haver DONO, não por faltar o nome: um
        processo com `s3_folder` tem prefixo próprio e é legítimo."""
        resposta, _ = await _correr(
            _pedido("Documentação Clientes/Ana Cliente/cc.pdf"),
            processo={
                "id": "p-1",
                "s3_folder": "Documentação Clientes/Ana Cliente",
            },
        )
        assert resposta["success"] is True


class TestAQuarentenaDeConteudo:
    async def test_o_ficheiro_aprovado_segue(self):
        resposta, quarentena = await _correr(
            _pedido("Documentação Clientes/Ana Cliente/cc.pdf")
        )
        assert resposta["success"] is True
        quarentena.assert_awaited_once()

    async def test_a_quarentena_recebe_a_chave_EXACTA(self):
        """Inspeccionar uma chave e gravar outra é a forma discreta de a
        parede não valer nada."""
        chave = "Documentação Clientes/Ana Cliente/cc.pdf"
        resposta, quarentena = await _correr(_pedido(chave))
        assert quarentena.await_args.args[0] == chave
        assert resposta["s3_path"] == chave

    async def test_conteudo_reprovado_nao_grava(self):
        """`exigir_conteudo_valido` levanta; o handler não pode engolir."""
        quarentena = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="conteúdo inválido")
        )
        db_falso = MagicMock()
        db_falso.processes.find_one = AsyncMock(return_value=PROCESSO)

        with patch.object(modulo, "db", db_falso), \
                patch.object(modulo, "exigir_conteudo_valido", quarentena):
            with pytest.raises(HTTPException) as erro:
                await modulo.run_confirm_upload(
                    _pedido("Documentação Clientes/Ana Cliente/cc.pdf"),
                    background_tasks=MagicMock(),
                    user={"id": "u-1"},
                )
        assert erro.value.status_code == 400

    async def test_o_tamanho_e_o_tipo_vem_do_VEREDICTO_e_nao_do_cliente(self):
        """O corpo do pedido declara o que quiser; o que vale é o objecto.

        É a lição da quarentena do Portal: o tamanho vem do `HEAD`, nunca
        da declaração.
        """
        capturado = {}

        async def _fulfill(process_id, payload, **kwargs):
            capturado.update(payload)
            return {"fulfilled": 0}

        db_falso = MagicMock()
        db_falso.processes.find_one = AsyncMock(return_value=PROCESSO)

        with patch.object(modulo, "db", db_falso), \
                patch.object(
                    modulo, "exigir_conteudo_valido",
                    AsyncMock(return_value=APROVADO),
                ), \
                patch.object(modulo.s3_service, "get_file_content", return_value=None), \
                patch.object(modulo, "log_history", AsyncMock()), \
                patch.object(modulo, "_auto_fulfill_portal_request", _fulfill), \
                patch("services.document_intake.db", db_falso):
            await modulo.run_confirm_upload(
                _pedido(
                    "Documentação Clientes/Ana Cliente/cc.pdf",
                    file_size=999_999_999,
                    content_type="application/x-mentira",
                ),
                background_tasks=MagicMock(),
                user={"id": "u-1"},
            )

        assert capturado["file_size"] == APROVADO.tamanho
        assert capturado["content_type"] == APROVADO.tipo_detectado


class TestOUrlPreAssinadoSaiuDaResposta:
    async def test_a_resposta_nao_traz_temporary_url(self):
        """Era o veículo da fuga. Ninguém o lia: o `directS3Upload` do
        `api.js` devolvia-o e não tem chamadores."""
        resposta, _ = await _correr(
            _pedido("Documentação Clientes/Ana Cliente/cc.pdf")
        )
        assert "temporary_url" not in resposta

    async def test_CONTRAPROVA_a_resposta_continua_util(self):
        """Sem isto, devolver `{}` satisfazia o teste de cima."""
        resposta, _ = await _correr(
            _pedido("Documentação Clientes/Ana Cliente/cc.pdf")
        )
        assert resposta["success"] is True
        assert resposta["s3_path"]
        assert resposta["normalized_filename"]
        assert resposta["category"]


class TestGuardaDeFonte:
    def _fonte(self):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        _ = Path  # o helper lê a função, não o ficheiro
        return codigo_da_funcao_sem_comentarios(modulo.run_confirm_upload)

    def test_as_DUAS_guardas_estao_ligadas(self):
        """Nenhuma substitui a outra: a da raiz defende de um `s3_folder`
        envenenado, a de posse defende do processo do vizinho."""
        fonte = self._fonte()
        assert "assert_path_within_document_root" in fonte
        assert "assert_s3_file_belongs_to_process" in fonte

    def test_a_quarentena_esta_ligada(self):
        assert "exigir_conteudo_valido" in self._fonte()

    def test_o_file_exists_saiu(self):
        """Era o MESMO `head_object`, bloqueante e a responder a menos
        perguntas."""
        assert "file_exists" not in self._fonte()

    def test_nao_se_gera_url_pre_assinado_neste_caminho(self):
        assert "get_presigned_url" not in self._fonte()
