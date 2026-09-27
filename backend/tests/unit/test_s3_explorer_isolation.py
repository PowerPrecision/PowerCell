"""O INVENTÁRIO das seis operações, com a Parede ligada (Épico 10, Passo 3).

Este ficheiro é o que responde a "mostra-me as 6 operações blindadas". Cada
operação tem o seu teste, e acrescentar uma sétima obriga a acrescentá-la
aqui — a lição do Lote 5, ponto 1, onde o Kanban tinha construtor próprio e
ficou de fora do isolamento por não haver inventário das superfícies.

As asserções são sobre o COMPORTAMENTO observável (404, chaves que chegam ao
S3, pastas devolvidas), não sobre o código-fonte.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.auth import UserRoleEnum as UserRole
from services import admin_s3_explorer as explorador
from services.admin_s3_explorer import (
    S3CreateFolderRequest,
    S3DeleteRequest,
    S3RenameRequest,
)
from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR as R
from services.tenant_network import TenantScope

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "domus"

PASTA_POWER = f"{R}/Cliente_Power"
PASTA_DOMUS = f"{R}/Cliente_Domus"
PASTA_ORFA = f"{R}/Pasta_Antiga"

ESCOPO_POWER = TenantScope(network_ids=(REDE_POWER,), company_ids=("cmp-power",))
ESCOPO_DOMUS = TenantScope(network_ids=(REDE_DOMUS,), company_ids=("cmp-domus",))

UTILIZADOR = {"id": "u1", "role": "consultor", "email": "c@power.pt"}


@pytest.fixture
def s3_falso():
    servico = MagicMock()
    servico.is_configured.return_value = True
    servico.bucket_name = "balde"
    servico.s3_client = MagicMock()
    servico.s3_client.list_objects_v2.return_value = {
        "CommonPrefixes": [], "Contents": [], "IsTruncated": False,
    }
    servico.s3_client.get_object.return_value = {
        "ContentType": "application/pdf",
        "Body": MagicMock(read=MagicMock(side_effect=[b""])),
    }
    servico.delete_file.return_value = True
    servico.rename_file.return_value = True
    with patch("services.s3_storage.s3_service", servico):
        yield servico


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    """Um bucket com uma pasta da Power, uma da Domus e uma órfã."""
    import services.s3_explorer_scope as escopo
    import services.s3_folder_relink as relink

    monkeypatch.setattr(escopo, "db", fake_async_db)
    monkeypatch.setattr(relink, "db", fake_async_db)

    async def semear():
        await fake_async_db.processes.insert_one(
            {"id": "p-power", "s3_folder": PASTA_POWER, "network_id": REDE_POWER})
        await fake_async_db.processes.insert_one(
            {"id": "p-domus", "s3_folder": PASTA_DOMUS, "network_id": REDE_DOMUS})

    return semear, fake_async_db


def _como(scope, papel=UserRole.CONSULTOR):
    """Substitui a resolução de âmbito — o pedido HTTP não existe aqui."""
    return patch.object(
        explorador, "ambito_do_utilizador",
        AsyncMock(return_value=(scope, papel)),
    )


def _chaves(s3_falso):
    chaves = []
    for metodo in ("get_object", "put_object", "copy_object", "delete_object", "list_objects_v2"):
        for c in getattr(s3_falso.s3_client, metodo).call_args_list:
            for campo in ("Key", "Prefix"):
                if campo in c.kwargs:
                    chaves.append(c.kwargs[campo])
    for c in s3_falso.delete_file.call_args_list:
        chaves.extend(c.args)
    for c in s3_falso.rename_file.call_args_list:
        chaves.extend(c.args)
    return chaves


class TestAsSeisOperacoesBlindadas:
    """Uma por operação. A Domus nunca toca numa pasta da Power."""

    async def test_1_listar_a_raiz_devolve_so_a_propria_rede(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        s3_falso.s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": f"{PASTA_POWER}/"},
                {"Prefix": f"{PASTA_DOMUS}/"},
                {"Prefix": f"{PASTA_ORFA}/"},
            ],
            "Contents": [],
            "IsTruncated": False,
        }
        with _como(ESCOPO_DOMUS):
            r = await explorador.run_get_s3_folder_contents("", UTILIZADOR)

        assert [p["name"] for p in r["subfolders"]] == ["Cliente_Domus"]
        assert r["total_items"] == 1

    async def test_2_entrar_numa_pasta_de_outra_rede_da_404(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_get_s3_folder_contents(PASTA_POWER, UTILIZADOR)
        assert exc.value.status_code == 404

    async def test_3_descarregar_de_outra_rede_da_404(self, s3_falso, mundo):
        """O pior caso: o ficheiro do cliente da concorrência."""
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_download(
                    f"{PASTA_POWER}/Financeiros/irs.pdf", UTILIZADOR
                )
        assert exc.value.status_code == 404
        assert _chaves(s3_falso) == []

    async def test_4_apagar_noutra_rede_da_404(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_delete(
                    S3DeleteRequest(path=PASTA_POWER, is_folder=True), UTILIZADOR
                )
        assert exc.value.status_code == 404
        assert _chaves(s3_falso) == []

    async def test_5_renomear_noutra_rede_da_404(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_rename(
                    S3RenameRequest(old_path=PASTA_POWER, new_name="Roubado", is_folder=True),
                    UTILIZADOR,
                )
        assert exc.value.status_code == 404
        assert _chaves(s3_falso) == []

    async def test_6_criar_pasta_noutra_rede_da_404(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path=f"{PASTA_POWER}/Nova"), UTILIZADOR
                )
        assert exc.value.status_code == 404
        assert _chaves(s3_falso) == []

    async def test_7_carregar_ficheiro_noutra_rede_da_404(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        ficheiro = MagicMock()
        ficheiro.filename = "x.pdf"
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_upload(ficheiro, PASTA_POWER, UTILIZADOR)
        assert exc.value.status_code == 404
        assert _chaves(s3_falso) == []


class TestOAcessoLegitimoContinuaAFuncionar:
    """Uma parede que tranca toda a gente também "isola"."""

    async def test_a_propria_rede_entra(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_POWER):
            r = await explorador.run_get_s3_folder_contents(PASTA_POWER, UTILIZADOR)
        assert r["folder_path"] == PASTA_POWER

    async def test_a_propria_rede_descarrega(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_POWER):
            await explorador.run_s3_download(f"{PASTA_POWER}/a.pdf", UTILIZADOR)
        assert f"{PASTA_POWER}/a.pdf" in _chaves(s3_falso)

    async def test_consultor_ve_a_carteira_dos_colegas_da_sua_rede(self, s3_falso, mundo):
        """Só a Camada 1: o Explorador é arrumação da empresa."""
        semear, bd = mundo
        await semear()
        await bd.processes.insert_one({
            "id": "p-colega", "s3_folder": f"{R}/Cliente_De_Outro",
            "network_id": REDE_POWER,
        })
        with _como(ESCOPO_POWER):
            r = await explorador.run_get_s3_folder_contents(
                f"{R}/Cliente_De_Outro", UTILIZADOR
            )
        assert r["folder_path"].endswith("Cliente_De_Outro")


class TestOrfasEReconciliacao:
    async def test_orfa_e_invisivel_ao_utilizador_normal(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_POWER):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_get_s3_folder_contents(PASTA_ORFA, UTILIZADOR)
        assert exc.value.status_code == 404

    async def test_admin_entra_na_orfa_para_reconciliar(self, s3_falso, mundo):
        """São ~250 depois do backfill, e 45 ambíguas. Alguém as trata."""
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_POWER, UserRole.ADMIN):
            r = await explorador.run_get_s3_folder_contents(PASTA_ORFA, UTILIZADOR)
        assert r["folder_path"] == PASTA_ORFA

    async def test_ambigua_e_invisivel_as_duas_redes(self, s3_falso, mundo):
        semear, bd = mundo
        await semear()
        partilhada = f"{R}/Maria_Santos"
        await bd.processes.insert_one(
            {"id": "a1", "s3_folder": partilhada, "network_id": REDE_POWER})
        await bd.processes.insert_one(
            {"id": "a2", "s3_folder": partilhada, "network_id": REDE_DOMUS})

        for escopo in (ESCOPO_POWER, ESCOPO_DOMUS):
            with _como(escopo):
                with pytest.raises(HTTPException) as exc:
                    await explorador.run_get_s3_folder_contents(partilhada, UTILIZADOR)
            assert exc.value.status_code == 404


class TestRenameReligaOMapeamento:
    """Passo 4, ponta-a-ponta: a pasta não desaparece do mundo."""

    async def test_o_mapeamento_segue_a_pasta(self, s3_falso, mundo):
        semear, bd = mundo
        await semear()
        s3_falso.s3_client.list_objects_v2.return_value = {
            "Contents": [{"Key": f"{PASTA_POWER}/Financeiros/irs.pdf"}],
            "IsTruncated": False,
        }
        await bd.document_metadata.insert_one(
            {"id": "d1", "s3_path": f"{PASTA_POWER}/Financeiros/irs.pdf"})

        with _como(ESCOPO_POWER, UserRole.DIRETOR):
            r = await explorador.run_s3_rename(
                S3RenameRequest(old_path=PASTA_POWER, new_name="Cliente_Power_Novo",
                                is_folder=True),
                UTILIZADOR,
            )

        novo = f"{R}/Cliente_Power_Novo"
        assert r["relink"]["processos"] == 1
        processo = await bd.processes.find_one({"id": "p-power"})
        assert processo["s3_folder"] == novo
        doc = await bd.document_metadata.find_one({"id": "d1"})
        assert doc["s3_path"] == f"{novo}/Financeiros/irs.pdf"

    async def test_a_pasta_renomeada_continua_visivel(self, s3_falso, mundo):
        """A prova de que a cegueira auto-infligida acabou: renomear e
        entrar logo a seguir."""
        semear, bd = mundo
        await semear()
        s3_falso.s3_client.list_objects_v2.return_value = {
            "Contents": [], "IsTruncated": False, "CommonPrefixes": [],
        }
        with _como(ESCOPO_POWER, UserRole.DIRETOR):
            await explorador.run_s3_rename(
                S3RenameRequest(old_path=PASTA_POWER, new_name="Renomeada",
                                is_folder=True),
                UTILIZADOR,
            )
            r = await explorador.run_get_s3_folder_contents(
                f"{R}/Renomeada", UTILIZADOR
            )
        assert r["folder_path"].endswith("Renomeada")

    async def test_rename_de_pasta_grande_pagina(self, s3_falso, mundo):
        """Movia 1000 e apagava-os, deixando o resto para trás."""
        semear, _ = mundo
        await semear()
        s3_falso.s3_client.list_objects_v2.side_effect = [
            {"Contents": [{"Key": f"{PASTA_POWER}/a{i}.pdf"} for i in range(3)],
             "IsTruncated": True, "NextContinuationToken": "p2"},
            {"Contents": [{"Key": f"{PASTA_POWER}/b{i}.pdf"} for i in range(2)],
             "IsTruncated": False},
        ]
        with _como(ESCOPO_POWER, UserRole.DIRETOR):
            r = await explorador.run_s3_rename(
                S3RenameRequest(old_path=PASTA_POWER, new_name="Grande", is_folder=True),
                UTILIZADOR,
            )
        assert r["objects_moved"] == 5

    async def test_renomear_um_FICHEIRO_tambem_reaponta(self, s3_falso, mundo):
        """O ramo do ficheiro solto tinha ficado sem teste — e a mutação
        que lhe tirava o religamento sobrevivia.

        Um ficheiro renomeado sem reapontar desaparece do separador
        Documentos da ficha (é o `document_metadata.s3_path` que o
        sustenta) e do pedido do Portal que o reclamava.
        """
        semear, bd = mundo
        await semear()
        antigo = f"{PASTA_POWER}/Financeiros/irs.pdf"
        await bd.document_metadata.insert_one({"id": "d1", "s3_path": antigo})

        with _como(ESCOPO_POWER, UserRole.DIRETOR):
            r = await explorador.run_s3_rename(
                S3RenameRequest(old_path=antigo, new_name="irs_2024.pdf",
                                is_folder=False),
                UTILIZADOR,
            )

        assert r["relink"]["documentos"] == 1
        doc = await bd.document_metadata.find_one({"id": "d1"})
        assert doc["s3_path"] == f"{PASTA_POWER}/Financeiros/irs_2024.pdf"
