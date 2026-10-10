"""Escrever na pasta documental de um processo (Bloco 2, Lote 12).

O upload carregava o processo por id e mais nada: bastava um `process_id`
para plantar um ficheiro na ficha de um cliente de OUTRA rede. A D-26 tinha
fechado a LEITURA; `assert_can_upload_to_process` fecha a escrita, e a regra
é «quem escreve é quem pode ver» — um perfil que a D-26 deixa ler mantém a
capacidade de escrever.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from services import document_direct_upload as directo
from services import document_upload as multipart
from services import document_upload_conflict as conflito
from services import document_visibility as dv
from tests.unit.helpers_tenant import (  # noqa: F401
    ANA, BRUNO, CARLA, REDE_DOMUS, REDE_INCUMBENTE, rede_de_omissao_incumbente, semear, tenant_db,
)

INDEXACAO = {"id": "u-ix", "email": "ix@power.pt", "role": "indexacao"}
PARCEIRO = {"id": "u-parc", "email": "p@x.pt", "role": "parceiro"}

P_POWER_INDEXADO = {
    "id": "p-ix", "client_name": "Ana Cliente", "status": "novo", "is_indexed": True,
    "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
    "s3_folder": "Documentação Clientes/c-power",
}
P_POWER_POR_INDEXAR = {
    **P_POWER_INDEXADO, "id": "p-novo", "is_indexed": False,
    "assigned_consultor_ids": ["u-carla"],
}
P_POWER_POR_INDEXAR_ALHEIO = {**P_POWER_POR_INDEXAR, "id": "p-novo2", "assigned_consultor_ids": ["u-outro"]}
P_PARTILHADO = {
    **P_POWER_INDEXADO, "id": "p-part",
    "partner_network_ids": [REDE_DOMUS], "partner_companies": ["cmp-domus"],
}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-ix", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "indexacao", "is_default": True},
        {"user_id": "u-carla", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "consultor", "is_default": False},
    ])
    for p in (P_POWER_INDEXADO, P_POWER_POR_INDEXAR, P_POWER_POR_INDEXAR_ALHEIO, P_PARTILHADO):
        fake_async_db.processes.docs.append(dict(p))
    return fake_async_db


async def _guarda(mundo, user, processo):
    with tenant_db(mundo, dv), patch.object(dv, "db", mundo):
        await dv.assert_can_upload_to_process(user, dict(processo))


@pytest.mark.asyncio
class TestAExploracao:
    async def test_o_diretor_de_uma_ilha_nao_escreve_na_pasta_da_power(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _guarda(mundo, BRUNO, P_POWER_INDEXADO)
        assert exc.value.status_code == 403

    async def test_um_consultor_de_outra_rede_tambem_nao(self, mundo):
        domus = {"id": "u-dom", "email": "d@domus.pt", "role": "consultor"}
        mundo.user_company_roles.docs.append(
            {"user_id": "u-dom", "company_id": "cmp-domus", "company_name": "Domus",
             "role": "consultor", "is_default": True}
        )
        with pytest.raises(HTTPException):
            await _guarda(mundo, domus, P_POWER_INDEXADO)

    @pytest.mark.parametrize("perfil", ["parceiro", "cliente"])
    async def test_parceiro_e_cliente_nao_carregam_pela_api_do_CRM(self, mundo, perfil):
        with pytest.raises(HTTPException) as exc:
            await _guarda(mundo, {**PARCEIRO, "role": perfil}, P_POWER_INDEXADO)
        assert exc.value.status_code == 403

    async def test_o_perfil_efectivo_parceiro_nao_herda_o_papel_base_de_admin(self, mundo):
        """Roles = base ∪ efectivo (`_user_allows`): um admin de base a
        trabalhar como parceiro mantém o passe do admin — é a regra da D-26,
        aqui só se afirma que a recusa depende de TODOS os papéis serem
        não-carregadores."""
        misto = {"id": "u-adm", "email": "a@x.pt", "role": "admin", "effective_role": "parceiro"}
        await _guarda(mundo, misto, P_POWER_INDEXADO)  # não levanta


@pytest.mark.asyncio
class TestOsPerfisCertosMantemAEscrita:
    async def test_a_gestao_da_rede_escreve(self, mundo):
        await _guarda(mundo, ANA, P_POWER_INDEXADO)
        await _guarda(mundo, ANA, P_POWER_POR_INDEXAR)  # por indexar: gestão tem bypass

    async def test_admin_e_ceo_escrevem_em_qualquer_rede(self, mundo):
        await _guarda(mundo, {"id": "x", "email": "x@x.pt", "role": "admin"}, P_POWER_INDEXADO)
        await _guarda(mundo, {"id": "y", "email": "y@x.pt", "role": "ceo"}, P_POWER_POR_INDEXAR)

    async def test_o_consultor_atribuido_escreve_no_processo_por_indexar(self, mundo):
        await _guarda(mundo, CARLA, P_POWER_POR_INDEXAR)

    async def test_o_consultor_nao_atribuido_nao_escreve_no_processo_por_indexar(self, mundo):
        """Quem a D-26 não deixa LER, não escreve."""
        with pytest.raises(HTTPException):
            await _guarda(mundo, CARLA, P_POWER_POR_INDEXAR_ALHEIO)

    async def test_o_consultor_escreve_no_processo_indexado_da_sua_rede(self, mundo):
        await _guarda(mundo, CARLA, P_POWER_INDEXADO)

    async def test_a_equipa_de_indexacao_escreve_no_processo_por_indexar(self, mundo):
        await _guarda(mundo, INDEXACAO, P_POWER_POR_INDEXAR_ALHEIO)

    async def test_a_rede_convidada_de_uma_partilha_escreve(self, mundo):
        """D-25: o parceiro vê a ficha inteira, documentos incluídos."""
        await _guarda(mundo, BRUNO, P_PARTILHADO)


@pytest.mark.asyncio
class TestOsQuatroFluxosUsamAGuarda:
    """A guarda REAL, sem a patchar, e o S3 nunca é tocado."""

    def _s3(self):
        s3 = MagicMock()
        s3.is_configured.return_value = True
        s3.file_exists.return_value = False
        return s3

    async def test_multipart(self, mundo):
        s3 = self._s3()
        with tenant_db(mundo, dv), patch.object(dv, "db", mundo), \
                patch.object(multipart, "s3_service", s3), \
                patch.object(multipart, "resolve_process_from_flexible_id",
                             AsyncMock(return_value=(dict(P_POWER_INDEXADO), "p-ix"))):
            with pytest.raises(HTTPException) as exc:
                await multipart.run_upload_file_s3(
                    "p-ix", file_content=b"%PDF", original_filename="f.pdf",
                    content_type="application/pdf", category="Outros", empresa_nif=None,
                    custom_filename=None, user=BRUNO, background_tasks=BackgroundTasks(),
                )
        assert exc.value.status_code == 403
        s3.upload_file.assert_not_called()

    async def test_gerar_url(self, mundo):
        s3 = self._s3()
        with tenant_db(mundo, dv), patch.object(dv, "db", mundo), \
                patch.object(directo, "s3_service", s3), patch.object(directo, "db", mundo):
            with pytest.raises(HTTPException) as exc:
                await directo.run_generate_upload_url(
                    {"process_id": "p-ix", "filename": "f.pdf", "content_type": "application/pdf"},
                    user=BRUNO,
                )
        assert exc.value.status_code == 403
        s3.generate_upload_presigned_url.assert_not_called()

    async def test_confirmar(self, mundo):
        quarentena = AsyncMock()
        with tenant_db(mundo, dv), patch.object(dv, "db", mundo), \
                patch.object(directo, "db", mundo), \
                patch.object(directo, "exigir_conteudo_valido", quarentena):
            with pytest.raises(HTTPException) as exc:
                await directo.run_confirm_upload(
                    {"process_id": "p-ix", "file_key": "Documentação Clientes/c-power/Index/f.pdf",
                     "original_filename": "f.pdf"},
                    background_tasks=BackgroundTasks(), user=BRUNO,
                )
        assert exc.value.status_code == 403
        # Posse ANTES de conteúdo: a quarentena nem chega a ler o objecto.
        quarentena.assert_not_called()

    async def test_verificar_conflito(self, mundo):
        s3 = self._s3()
        with tenant_db(mundo, dv), patch.object(dv, "db", mundo), \
                patch.object(conflito, "s3_service", s3), patch.object(conflito, "db", mundo):
            with pytest.raises(HTTPException) as exc:
                await conflito.run_check_upload_conflict(
                    {"process_id": "p-ix", "filenames": ["f.pdf"]}, user=BRUNO,
                )
        assert exc.value.status_code == 403
        s3.file_exists.assert_not_called()


class TestALigacaoNaFonte:
    def test_cada_fluxo_chama_a_guarda_antes_de_tocar_no_s3(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        alvos = [
            (multipart.run_upload_file_s3, "s3_service.upload_file"),
            (directo.run_generate_upload_url, "generate_upload_presigned_url"),
            (directo.run_confirm_upload, "exigir_conteudo_valido("),
            (conflito.run_check_upload_conflict, "find_filename_conflicts("),
        ]
        for funcao, toque in alvos:
            fonte = codigo_da_funcao_sem_comentarios(funcao)
            assert "assert_can_upload_to_process(" in fonte, funcao.__name__
            assert fonte.index("assert_can_upload_to_process(") < fonte.index(toque), funcao.__name__

    def test_a_rota_do_conflito_passa_o_utilizador(self):
        from routes import documents
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        assert "user=user" in codigo_da_funcao_sem_comentarios(documents.check_upload_conflict)
