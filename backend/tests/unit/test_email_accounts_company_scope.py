"""
Contas de email: cada perfil vê as suas (Missão de Limpeza, ponto 3).

O DEFEITO
---------
O cartão de contas da Área Pessoal renderiza um separador POR PERFIL e
passa o `company_id` desse perfil. Um perfil sem empresa associada passa
o sentinela `"default"` — e, nesse caso, o `EmailAccountsCard` não envia
o header `X-Company-Id` (só o envia quando difere de "default").

No backend:

    active_company_id = _non_default_company_id(company_id, header_company)

`_non_default_company_id` DESCARTA "default" por desenho. O pedido caía
então em `header_company`, que sem header é `user["company"]` — a empresa
por omissão do utilizador. Resultado: o separador pedia as contas de
"default" e recebia as de outra empresa. As contas de um perfil apareciam
listadas noutro.

A CORRECÇÃO
-----------
"default" pedido EXPLICITAMENTE é uma resposta, não uma ausência. Só
quando o cliente não diz nada é que o contexto da sessão decide.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import users_api_email_config
from services.users_api_email_config import (
    _non_default_company_id,
    resolve_accounts_company_id,
)


# ====================================================================
# O HELPER, ISOLADO
# ====================================================================


class TestResolucaoDaEmpresa:
    def test_empresa_pedida_explicitamente_ganha(self):
        assert resolve_accounts_company_id("comp-power", "comp-precision") == "comp-power"

    def test_default_pedido_explicitamente_e_respeitado(self):
        # O CASO DO DEFEITO: o separador pediu "default" e recebia
        # "comp-precision" (a empresa activa da sessão).
        assert resolve_accounts_company_id("default", "comp-precision") == "default"

    def test_sem_pedido_manda_o_contexto_da_sessao(self):
        assert resolve_accounts_company_id(None, "comp-precision") == "comp-precision"

    def test_pedido_vazio_conta_como_ausencia(self):
        assert resolve_accounts_company_id("   ", "comp-precision") == "comp-precision"

    def test_sem_pedido_e_sem_sessao_cai_em_default(self):
        assert resolve_accounts_company_id(None, None) == "default"

    def test_sessao_em_default_tambem_e_default(self):
        assert resolve_accounts_company_id(None, "default") == "default"

    def test_o_helper_antigo_continua_a_descartar_default(self):
        # `_non_default_company_id` mantém-se como estava — é usado noutros
        # sítios onde "default" É mesmo uma ausência. O que mudou foi quem
        # o usa para ESTA decisão.
        assert _non_default_company_id("default", "comp-x") == "comp-x"


# ====================================================================
# O ENDPOINT
# ====================================================================


def _pedido(header=None):
    request = MagicMock()
    request.headers = {"X-Company-Id": header} if header else {}
    return request


CONTAS = {
    "comp-precision": [
        {
            "id": "c-1",
            "company_id": "comp-precision",
            "email_address": "ana@precision.pt",
            "encrypted_password": "x",
        }
    ],
    "default": [],
}


def _patches(monkey_list):
    return [
        patch(
            "services.user_email_config_service.list_company_email_configs",
            AsyncMock(side_effect=monkey_list),
        ),
        patch(
            "services.auth.get_active_company_id_async",
            AsyncMock(side_effect=lambda req, user: req.headers.get("X-Company-Id") or user.get("company")),
        ),
        patch("services.auth.get_effective_role", MagicMock(return_value="consultor")),
        patch(
            "services.email_config_resolver.load_caixa_geral_config",
            AsyncMock(return_value=None),
        ),
    ]


class TestListagemPorPerfil:
    @pytest.mark.asyncio
    async def test_separador_sem_empresa_nao_ve_as_contas_de_outra(self):
        chamadas = []

        async def listar(user_id, company_id):
            chamadas.append(company_id)
            return CONTAS.get(company_id, [])

        activos = _patches(listar)
        for p in activos:
            p.start()
        try:
            resultado = await users_api_email_config.run_list_my_email_accounts(
                _pedido(),  # sem header — é o que o cartão faz em "default"
                "default",  # ...e pede explicitamente "default"
                {"id": "u-1", "company": "comp-precision"},
            )
        finally:
            for p in reversed(activos):
                p.stop()

        assert chamadas == ["default"], f"consultou {chamadas}"
        assert resultado["company_id"] == "default"
        assert resultado["accounts"] == []

    @pytest.mark.asyncio
    async def test_separador_de_uma_empresa_ve_as_contas_dela(self):
        chamadas = []

        async def listar(user_id, company_id):
            chamadas.append(company_id)
            return CONTAS.get(company_id, [])

        activos = _patches(listar)
        for p in activos:
            p.start()
        try:
            resultado = await users_api_email_config.run_list_my_email_accounts(
                _pedido("comp-precision"),
                "comp-precision",
                {"id": "u-1", "company": "comp-precision"},
            )
        finally:
            for p in reversed(activos):
                p.stop()

        assert chamadas == ["comp-precision"]
        assert len(resultado["accounts"]) == 1

    @pytest.mark.asyncio
    async def test_sem_company_id_o_contexto_da_sessao_continua_a_valer(self):
        # Retrocompatibilidade: consumidores que não passam company_id.
        chamadas = []

        async def listar(user_id, company_id):
            chamadas.append(company_id)
            return CONTAS.get(company_id, [])

        activos = _patches(listar)
        for p in activos:
            p.start()
        try:
            await users_api_email_config.run_list_my_email_accounts(
                _pedido("comp-precision"),
                None,
                {"id": "u-1", "company": "comp-precision"},
            )
        finally:
            for p in reversed(activos):
                p.stop()

        assert chamadas == ["comp-precision"]
