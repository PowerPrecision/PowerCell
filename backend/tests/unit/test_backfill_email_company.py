"""
Ponto 8, Fase 1 — o carimbo dos emails por carimbar.

A regra que estes testes protegem é a mesma do `backfill_network_id`:
**nunca escrever uma empresa "provável"**. Aqui é ainda mais importante
do que lá, porque `build_company_mailbox_condition` faz o carimbo
explícito MANDAR sobre a dedução pelo endereço. Um carimbo errado não
se auto-corrige na leitura seguinte: prende o email à empresa errada
para sempre.
"""
import pytest
from unittest.mock import patch

from scripts.backfill_email_company_id import (
    empresa_consensual,
    mapa_endereco_para_empresa,
    empresa_unica_do_utilizador,
)


class TestEmpresaConsensual:
    def test_uma_candidata_e_uma_resposta(self):
        assert empresa_consensual(["power"]) == "power"
        assert empresa_consensual(["power", "power", " power "]) == "power"

    def test_duas_candidatas_nao_se_resolvem_por_maioria(self):
        # Um endereço configurado em duas empresas não se adivinha.
        assert empresa_consensual(["power", "power", "domus"]) is None

    def test_sem_candidatas_devolve_none(self):
        assert empresa_consensual([]) is None
        assert empresa_consensual([None, "", "   "]) is None


class TestMapaEnderecoParaEmpresa:

    @pytest.mark.asyncio
    async def test_mapeia_as_contas_pessoais_e_as_da_empresa(self, fake_async_db):
        fake_async_db.user_email_configs.docs.append(
            {"email_address": "Ana@Power.PT", "company_id": "power"},
        )
        fake_async_db.company_email_configs.docs.append(
            {"email_address": "geral@domus.pt", "company_id": "domus"},
        )
        mapa = await mapa_endereco_para_empresa(fake_async_db)
        # Normalizado para minúsculas: o `account` gravado varia na caixa.
        assert mapa["ana@power.pt"] == "power"
        assert mapa["geral@domus.pt"] == "domus"

    @pytest.mark.asyncio
    async def test_um_endereco_em_duas_empresas_fica_ambiguo(self, fake_async_db):
        # `None` no mapa significa "não carimbar", não "carimbar com nada".
        fake_async_db.user_email_configs.docs.extend([
            {"email_address": "partilhado@x.pt", "company_id": "power"},
            {"email_address": "partilhado@x.pt", "company_id": "domus"},
        ])
        mapa = await mapa_endereco_para_empresa(fake_async_db)
        assert mapa["partilhado@x.pt"] is None

    @pytest.mark.asyncio
    async def test_ignora_registos_sem_empresa_ou_sem_endereco(self, fake_async_db):
        fake_async_db.user_email_configs.docs.extend([
            {"email_address": "sem-empresa@x.pt"},
            {"company_id": "power"},
        ])
        mapa = await mapa_endereco_para_empresa(fake_async_db)
        assert "sem-empresa@x.pt" not in mapa


class TestEmpresaUnicaDoUtilizador:

    @pytest.mark.asyncio
    async def test_um_utilizador_de_uma_empresa_so(self, fake_async_db):
        fake_async_db.user_company_roles.docs.append(
            {"user_id": "u1", "company_id": "power", "is_active": True},
        )
        assert await empresa_unica_do_utilizador(fake_async_db, "u1") == "power"

    @pytest.mark.asyncio
    async def test_um_multi_perfil_nao_se_adivinha(self, fake_async_db):
        # É exactamente o utilizador que este épico serve. Carimbar-lhe
        # os emails "pela primeira empresa" seria inventar.
        fake_async_db.user_company_roles.docs.extend([
            {"user_id": "u1", "company_id": "power", "is_active": True},
            {"user_id": "u1", "company_id": "precision", "is_active": True},
        ])
        assert await empresa_unica_do_utilizador(fake_async_db, "u1") is None

    @pytest.mark.asyncio
    async def test_sem_utilizador_devolve_none(self, fake_async_db):
        assert await empresa_unica_do_utilizador(fake_async_db, "") is None

    @pytest.mark.asyncio
    async def test_falha_de_io_nao_inventa_empresa(self, fake_async_db):
        class Partida:
            def find(self, *a, **k):
                raise RuntimeError("base em baixo")

        class BD:
            user_company_roles = Partida()

        assert await empresa_unica_do_utilizador(BD(), "u1") is None
