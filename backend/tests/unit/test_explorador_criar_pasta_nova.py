"""Criar uma pasta NOVA no Explorador ("Ficheiros") devolvia 404 «Pasta não encontrada».

A parede decide pelo dono da pasta de topo. Uma pasta acabada de pedir não tem dono: contava
como ÓRFÃ, e uma órfã só é visível ao Master — logo o Admin/CEO (e o Master com uma empresa
escolhida) levava 404 ao criar a primeira pasta, e a ferramenta de arrumação não arrumava nada.
Hoje a pasta de topo nova nasce com a rede de quem a cria e passa a ser dele (e só da rede dele).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.auth import UserRoleEnum as UserRole
from services import admin_s3_explorer as explorador
from services import s3_explorer_scope as escopo
from services.admin_s3_explorer import S3CreateFolderRequest
from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR as R
from services.tenant_network import TenantScope

REDE_DOMUS = "domus"
REDE_POWER = "grupo_power_precision"
ESCOPO_DOMUS = TenantScope(network_ids=(REDE_DOMUS,), company_ids=("cmp-domus",))
ESCOPO_POWER = TenantScope(network_ids=(REDE_POWER,), company_ids=("cmp-power",))
UTILIZADOR = {"id": "u1", "role": "ceo", "email": "c@domus.pt", "active_company_id": "cmp-domus"}


@pytest.fixture
def s3_falso():
    servico = MagicMock()
    servico.is_configured.return_value = True
    servico.bucket_name = "balde"
    servico.s3_client = MagicMock()
    servico.s3_client.list_objects_v2.return_value = {"Contents": [], "CommonPrefixes": []}
    with patch("services.s3_storage.s3_service", servico):
        yield servico


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    import services.s3_folder_relink as relink
    import services.tenant_network as rede

    for modulo in (escopo, relink, rede):
        monkeypatch.setattr(modulo, "db", fake_async_db)

    async def semear():
        await fake_async_db.companies.insert_one(
            {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS})
        await fake_async_db.companies.insert_one(
            {"id": "cmp-power", "name": "Power", "network_id": REDE_POWER})
        await fake_async_db.processes.insert_one(
            {"id": "p-power", "s3_folder": f"{R}/Cliente_Power", "network_id": REDE_POWER})
    return semear, fake_async_db


def _como(scope, papel=UserRole.CEO):
    return patch.object(explorador, "ambito_do_utilizador", AsyncMock(return_value=(scope, papel)))


def _put(s3):
    return [c.kwargs["Key"] for c in s3.s3_client.put_object.call_args_list]


class TestPastaDeTopoNova:
    async def test_o_ceo_cria_a_primeira_pasta(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            r = await explorador.run_s3_create_folder(
                S3CreateFolderRequest(folder_path="Nova_Pasta/"), UTILIZADOR)
        assert r["success"] is True
        assert _put(s3_falso) == [f"{R}/Nova_Pasta/.keep"]

    async def test_fica_com_dono_e_o_criador_volta_a_ve_la(self, s3_falso, mundo):
        semear, bd = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            await explorador.run_s3_create_folder(
                S3CreateFolderRequest(folder_path="Nova_Pasta/"), UTILIZADOR)
        registo = await bd.s3_explorer_folders.find_one({"path": f"{R}/Nova_Pasta"})
        assert registo["network_id"] == REDE_DOMUS
        assert registo["created_by"] == "u1"

        mapa = await escopo.carregar_pastas([f"{R}/Nova_Pasta"])
        pasta = mapa[f"{R}/Nova_Pasta"]
        assert not pasta.orfa
        assert escopo.pode_ver(pasta, ESCOPO_DOMUS, role="ceo")

    async def test_outra_rede_nao_ve_a_pasta_nova(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            await explorador.run_s3_create_folder(
                S3CreateFolderRequest(folder_path="Nova_Pasta/"), UTILIZADOR)
        mapa = await escopo.carregar_pastas([f"{R}/Nova_Pasta"])
        assert not escopo.pode_ver(mapa[f"{R}/Nova_Pasta"], ESCOPO_POWER, role="ceo")

    async def test_sem_empresa_determinavel_diz_o_que_falta(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        sem_empresa = {"id": "u2", "role": "ceo"}
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path="Nova_Pasta/"), sem_empresa)
        assert exc.value.status_code == 400
        assert _put(s3_falso) == []

    async def test_empresa_fora_do_ambito_nao_serve_de_carimbo(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        forjado = {**UTILIZADOR, "active_company_id": "cmp-power"}
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path="Nova_Pasta/"), forjado)
        assert exc.value.status_code == 400
        assert _put(s3_falso) == []

    async def test_falha_do_s3_desfaz_o_registo(self, s3_falso, mundo):
        semear, bd = mundo
        await semear()
        s3_falso.s3_client.put_object.side_effect = RuntimeError("s3 em baixo")
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path="Nova_Pasta/"), UTILIZADOR)
        assert exc.value.status_code == 500
        assert await bd.s3_explorer_folders.find_one({"path": f"{R}/Nova_Pasta"}) is None


class TestAParedeContinuaDeFora:
    async def test_pasta_alheia_continua_a_ser_404(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path=f"{R}/Cliente_Power/Nova"), UTILIZADOR)
        assert exc.value.status_code == 404
        assert _put(s3_falso) == []

    async def test_pasta_de_topo_com_o_nome_de_uma_alheia_nao_se_reclama(self, s3_falso, mundo):
        """Mesmo sem objectos no S3, um nome já reclamado por outra rede não ganha segundo dono
        (a pasta ficaria AMBÍGUA e deixava de ser visível às duas)."""
        semear, bd = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path="Cliente_Power/"), UTILIZADOR)
        assert exc.value.status_code == 404
        assert _put(s3_falso) == []
        assert await bd.s3_explorer_folders.find_one({}) is None

    async def test_orfa_com_conteudo_nao_se_reclama(self, s3_falso, mundo):
        """Uma pasta antiga sem dono NÃO pode ser apanhada por quem criar uma com o mesmo nome."""
        semear, bd = mundo
        await semear()
        s3_falso.s3_client.list_objects_v2.return_value = {"Contents": [{"Key": f"{R}/Antiga/x.pdf"}]}
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path="Antiga/"), UTILIZADOR)
        assert exc.value.status_code == 404
        assert _put(s3_falso) == []
        assert await bd.s3_explorer_folders.find_one({"path": f"{R}/Antiga"}) is None

    async def test_pasta_nova_mais_funda_que_o_topo_continua_404(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path="Inexistente/Sub/"), UTILIZADOR)
        assert exc.value.status_code == 404

    async def test_falha_a_ler_o_s3_nao_abre_a_criacao(self, s3_falso, mundo):
        semear, _ = mundo
        await semear()
        s3_falso.s3_client.list_objects_v2.side_effect = RuntimeError("sem rede")
        with _como(ESCOPO_DOMUS):
            with pytest.raises(HTTPException) as exc:
                await explorador.run_s3_create_folder(
                    S3CreateFolderRequest(folder_path="Nova_Pasta/"), UTILIZADOR)
        assert exc.value.status_code == 503
        assert _put(s3_falso) == []

    async def test_pasta_visivel_segue_a_regra_de_sempre(self, s3_falso, mundo):
        semear, bd = mundo
        await semear()
        with _como(ESCOPO_POWER):
            await explorador.run_s3_create_folder(
                S3CreateFolderRequest(folder_path=f"{R}/Cliente_Power/Sub"),
                {**UTILIZADOR, "active_company_id": "cmp-power"})
        assert _put(s3_falso) == [f"{R}/Cliente_Power/Sub/.keep"]
        assert await bd.s3_explorer_folders.find_one({}) is None
