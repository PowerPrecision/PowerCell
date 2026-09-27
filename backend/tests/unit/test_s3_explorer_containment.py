"""As SEIS operações do Explorador, uma a uma (Épico 10, Gestor S3, Passo 1).

Este ficheiro é também o INVENTÁRIO das superfícies. A lição do Lote 5,
ponto 1: o Kanban tinha construtor de query separado e ficou de fora do
isolamento do Lote 4, porque tínhamos um ponto único para a CONDIÇÃO e
nenhum inventário dos sítios que a usam. Aqui há uma asserção por operação,
e acrescentar uma sétima obriga a acrescentá-la a esta lista.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services import admin_s3_explorer as explorador
from services.admin_s3_explorer import (
    S3CreateFolderRequest,
    S3DeleteRequest,
    S3RenameRequest,
)
from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR

UTILIZADOR = {"id": "u1", "role": "admin", "email": "a@x.pt"}

# A chave que ninguém pode alcançar: é a base de dados inteira num ficheiro.
BACKUP = "backups/powercell-2026-09-25.gz"


@pytest.fixture
def s3_falso():
    """Duplo do S3 que REGISTA as chaves pedidas.

    Asserir sobre as chaves que chegam ao cliente é o que interessa — um
    teste que só verificasse o 400 não provaria que, no caminho que passa,
    a chave certa é usada.
    """
    servico = MagicMock()
    servico.is_configured.return_value = True
    servico.bucket_name = "balde"
    servico.s3_client = MagicMock()
    servico.s3_client.list_objects_v2.return_value = {"CommonPrefixes": [], "Contents": []}
    servico.s3_client.get_object.return_value = {
        "ContentType": "application/gzip",
        "Body": MagicMock(read=MagicMock(side_effect=[b""])),
    }
    servico.delete_file.return_value = True
    with patch("services.s3_storage.s3_service", servico):
        yield servico


def _chaves_tocadas(s3_falso):
    """Todas as chaves S3 que o duplo viu, em qualquer operação."""
    chamadas = []
    for metodo in ("get_object", "put_object", "copy_object", "delete_object", "list_objects_v2"):
        for chamada in getattr(s3_falso.s3_client, metodo).call_args_list:
            for campo in ("Key", "Prefix"):
                if campo in chamada.kwargs:
                    chamadas.append(chamada.kwargs[campo])
    for chamada in s3_falso.delete_file.call_args_list:
        chamadas.extend(chamada.args)
    return chamadas


class TestOBackupNuncaEAlcancado:
    """Uma por operação. Nenhuma delas pode produzir a chave do backup."""

    async def test_listar(self, s3_falso):
        # Subir acima da raiz é recusado ANTES de tocar no S3 — a recusa é
        # mais forte do que a contenção, e aqui é o que acontece.
        with pytest.raises(HTTPException) as exc:
            await explorador.run_get_s3_folder_contents("../backups", UTILIZADOR)
        assert exc.value.status_code == 400
        assert _chaves_tocadas(s3_falso) == []

    async def test_listar_relativo_fica_contido(self, s3_falso):
        await explorador.run_get_s3_folder_contents("backups", UTILIZADOR)
        assert not any(c.startswith("backups/") for c in _chaves_tocadas(s3_falso))

    async def test_download(self, s3_falso):
        """Fazia `get_object(Key=path)` com a chave CRUA."""
        await explorador.run_s3_download(BACKUP, UTILIZADOR)
        chaves = _chaves_tocadas(s3_falso)
        assert BACKUP not in chaves
        assert all(c.startswith(RAIZ_DO_EXPLORADOR) for c in chaves)

    async def test_delete_de_pasta(self, s3_falso):
        """`path="backups/"` + `is_folder=True` apagava todos os backups."""
        await explorador.run_s3_delete(
            S3DeleteRequest(path="backups/", is_folder=True), UTILIZADOR
        )
        assert not any(c.startswith("backups/") for c in _chaves_tocadas(s3_falso))

    async def test_delete_de_ficheiro(self, s3_falso):
        await explorador.run_s3_delete(
            S3DeleteRequest(path=BACKUP, is_folder=False), UTILIZADOR
        )
        assert BACKUP not in _chaves_tocadas(s3_falso)

    async def test_rename(self, s3_falso):
        await explorador.run_s3_rename(
            S3RenameRequest(old_path="backups/", new_name="lixo", is_folder=True),
            UTILIZADOR,
        )
        assert not any(c.startswith("backups/") for c in _chaves_tocadas(s3_falso))

    async def test_criar_pasta(self, s3_falso):
        with pytest.raises(HTTPException) as exc:
            await explorador.run_s3_create_folder(
                S3CreateFolderRequest(folder_path="../backups/nova"), UTILIZADOR
            )
        assert exc.value.status_code == 400
        assert _chaves_tocadas(s3_falso) == []

    async def test_upload(self, s3_falso):
        ficheiro = MagicMock()
        ficheiro.filename = "x.pdf"
        ficheiro.read = MagicMock(return_value=b"")
        with pytest.raises(HTTPException) as exc:
            await explorador.run_s3_upload(ficheiro, "../backups", UTILIZADOR)
        assert exc.value.status_code == 400
        assert _chaves_tocadas(s3_falso) == []


class TestSubirAcimaDaRaizERecusado:
    async def test_download_com_subida_da_raiz_e_400(self, s3_falso):
        with pytest.raises(HTTPException) as exc:
            await explorador.run_s3_download("../../backups/dump.gz", UTILIZADOR)
        assert exc.value.status_code == 400
        assert _chaves_tocadas(s3_falso) == []

    async def test_rename_nao_aceita_barra_no_nome_novo(self, s3_falso):
        """O nome novo é um SEGMENTO: com `/` era outra chave arbitrária."""
        with pytest.raises(HTTPException) as exc:
            await explorador.run_s3_rename(
                S3RenameRequest(
                    old_path=f"{RAIZ_DO_EXPLORADOR}/Joao",
                    new_name="../../backups",
                    is_folder=True,
                ),
                UTILIZADOR,
            )
        assert exc.value.status_code == 400


class TestPaginacaoDaListagem:
    """Uma raiz com mais de mil pastas ficava truncada em silêncio."""

    async def test_segue_o_cursor_ate_ao_fim(self, s3_falso):
        s3_falso.s3_client.list_objects_v2.side_effect = [
            {
                "CommonPrefixes": [{"Prefix": f"{RAIZ_DO_EXPLORADOR}/Cliente_{i}/"} for i in range(3)],
                "Contents": [],
                "IsTruncated": True,
                "NextContinuationToken": "pagina-2",
            },
            {
                "CommonPrefixes": [{"Prefix": f"{RAIZ_DO_EXPLORADOR}/Cliente_{i}/"} for i in range(3, 5)],
                "Contents": [],
                "IsTruncated": False,
            },
        ]
        r = await explorador.run_get_s3_folder_contents("", UTILIZADOR)

        assert len(r["subfolders"]) == 5
        assert r["total_items"] == 5
        segunda = s3_falso.s3_client.list_objects_v2.call_args_list[1]
        assert segunda.kwargs["ContinuationToken"] == "pagina-2"

    async def test_truncado_sem_cursor_nao_cicla_para_sempre(self, s3_falso):
        """Defesa: "truncado" sem cursor não pode pendurar o pedido."""
        s3_falso.s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [{"Prefix": f"{RAIZ_DO_EXPLORADOR}/A/"}],
            "Contents": [],
            "IsTruncated": True,
        }
        s3_falso.s3_client.list_objects_v2.side_effect = None

        r = await explorador.run_get_s3_folder_contents("", UTILIZADOR)
        assert len(r["subfolders"]) == 1
        assert s3_falso.s3_client.list_objects_v2.call_count == 1

    async def test_sem_truncagem_faz_uma_so_chamada(self, s3_falso):
        """Contraprova: a paginação não pode custar chamadas a mais."""
        s3_falso.s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [], "Contents": [], "IsTruncated": False,
        }
        s3_falso.s3_client.list_objects_v2.side_effect = None
        await explorador.run_get_s3_folder_contents("", UTILIZADOR)
        assert s3_falso.s3_client.list_objects_v2.call_count == 1
