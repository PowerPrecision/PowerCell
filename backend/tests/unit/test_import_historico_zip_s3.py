"""`import_historico_zip` com o ZIP no S3 (`s3://bucket/chave`, 28/10/2026): descarrega para um temporário e apaga-o."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from scripts import import_historico_zip as script


class TestUri:
    def test_separa_bucket_e_chave(self):
        assert script.separar_uri_s3("s3://powerprecision-docs-storage/temp/import/import.zip") == (
            "powerprecision-docs-storage", "temp/import/import.zip")

    @pytest.mark.parametrize("texto", ["s3://bucket", "s3://bucket/", "s3://bucket/pasta/", "/dados/a.zip", "", None])
    def test_o_resto_nao_e_uri(self, texto):
        assert script.separar_uri_s3(texto) is None


@pytest.mark.asyncio
class TestPrincipal:
    async def test_uri_incompleto_e_erro_2(self):
        assert await script.principal(["s3://bucket"]) == 2

    async def test_sem_s3_configurado_e_5(self):
        with patch.object(script, "_s3_pronto", AsyncMock(return_value=False)):
            assert await script.principal(["s3://b/k.zip"]) == 5

    async def test_falha_ao_descarregar_e_2(self):
        with patch.object(script, "_s3_pronto", AsyncMock(return_value=True)), \
                patch.object(script, "_descarregar_do_s3", AsyncMock(side_effect=RuntimeError("403"))):
            assert await script.principal(["s3://b/k.zip"]) == 2

    async def test_importa_o_temporario_e_apaga_o_no_fim(self, tmp_path):
        temporario = tmp_path / "t.zip"
        temporario.write_bytes(b"PK")
        resto = AsyncMock(return_value=0)
        with patch.object(script, "_s3_pronto", AsyncMock(return_value=True)), \
                patch.object(script, "_descarregar_do_s3", AsyncMock(return_value=str(temporario))) as descarregar, \
                patch.object(script, "_principal", resto):
            assert await script.principal(["s3://b/temp/import/import.zip", "--rede", "r", "--aplicar"]) == 0
        descarregar.assert_awaited_once_with("b", "temp/import/import.zip")
        assert resto.await_args.args[0].zip == str(temporario)
        assert not os.path.exists(temporario)

    async def test_caminho_local_segue_como_antes(self):
        with patch.object(script, "_principal", AsyncMock(return_value=0)) as resto, \
                patch.object(script, "_descarregar_do_s3", AsyncMock()) as descarregar:
            assert await script.principal(["/dados/a.zip"]) == 0
        descarregar.assert_not_awaited()
        assert resto.await_args.args[0].zip == "/dados/a.zip"
