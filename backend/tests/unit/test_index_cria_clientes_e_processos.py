"""RBAC do perfil Index (`indexacao`): cria clientes E processos, como um consultor ou um diretor.

«Index» é um perfil interno de utilizador (data entry), não um site externo. Havia DUAS portas para
criar um processo de staff e as duas diziam «não» ao Index, cada uma por um motivo:

1. `exigir_capacidade("PROCESS_CREATE")` na rota — o registo `ROLE_CAPABILITY_DEFAULTS` tinha
   `PROCESS_CREATE: False` para `indexacao`;
2. `assert_can_create_staff_process` — uma SEGUNDA lista de papéis escrita à mão, dentro do serviço.

Duas respostas à mesma pergunta divergem sem dar erro («menu e rotas têm de concordar»): hoje o serviço
pergunta ao MESMO registo de capacidades que a rota. `POST /clients` nunca teve guarda de papel e
`CLIENT_CREATE` já era verdadeiro — fica afirmado para não regredir.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

INDEXADOR = {"id": "u-idx", "name": "Index", "role": "indexacao", "effective_role": "indexacao",
             "email": "idx@power.pt", "active_company_id": "cmp-power"}


class TestAExploracao:
    """O ataque, escrito primeiro: o Index recebia 403 nas duas portas."""

    def test_o_registo_de_capacidades_deixa_o_index_criar_processos(self):
        from services.capability_gate import tem_capacidade

        assert tem_capacidade(INDEXADOR, "PROCESS_CREATE", papel="indexacao") is True

    def test_a_porta_do_servico_deixa_o_index_criar(self):
        from services.process_create import assert_can_create_staff_process

        assert_can_create_staff_process("indexacao")  # não levanta

    @pytest.mark.asyncio
    async def test_a_dependencia_da_rota_deixa_passar_o_index(self):
        from services import capability_gate as mod

        dependencia = mod.exigir_capacidade("PROCESS_CREATE")
        with patch("services.auth.get_effective_role_async", AsyncMock(return_value="indexacao")):
            assert await dependencia(request=object(), user=INDEXADOR) is INDEXADOR


class TestContraprovas:
    """Abrir a porta ao Index não a abre a mais ninguém."""

    @pytest.mark.parametrize("papel", ["parceiro", "cliente", "desconhecido", ""])
    def test_quem_nao_tem_o_direito_continua_sem_ele(self, papel):
        from services.process_create import assert_can_create_staff_process

        with pytest.raises(HTTPException) as exc:
            assert_can_create_staff_process(papel)
        assert exc.value.status_code == 403

    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor", "administrativo", "consultor", "intermediario", "indexacao"])
    def test_os_papeis_de_staff_criam(self, papel):
        from services.process_create import assert_can_create_staff_process

        assert_can_create_staff_process(papel)

    def test_a_excepcao_pessoal_negativa_vale_na_porta_do_servico(self):
        """Um override pessoal (`permissions.capabilities`) recusa mesmo a quem o cargo permite — nas DUAS portas."""
        from services.process_create import assert_can_create_staff_process

        sem_direito = {**INDEXADOR, "permissions": {"capabilities": {"PROCESS_CREATE": False}}}
        with pytest.raises(HTTPException) as exc:
            assert_can_create_staff_process("indexacao", user=sem_direito)
        assert exc.value.status_code == 403

    def test_a_excepcao_pessoal_positiva_vale_na_porta_do_servico(self):
        from services.process_create import assert_can_create_staff_process

        com_direito = {"id": "u", "role": "parceiro", "permissions": {"capabilities": {"PROCESS_CREATE": True}}}
        assert_can_create_staff_process("parceiro", user=com_direito)

    def test_a_porta_do_servico_deriva_do_registo_e_nao_de_uma_lista_propria(self):
        """Guarda de fonte: sem a lista de papéis escrita à mão (a segunda cópia que divergiu)."""
        from services.process_create import assert_can_create_staff_process
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(assert_can_create_staff_process)
        assert "UserRole." not in corpo, "voltou uma lista de papéis escrita à mão"
        assert "tem_capacidade" in corpo or "get_role_defaults" in corpo


class TestClientes:
    """`POST /clients` nunca teve guarda de papel; o registo diz que o Index cria clientes."""

    def test_o_registo_deixa_o_index_criar_clientes(self):
        from services.capability_gate import tem_capacidade

        assert tem_capacidade(INDEXADOR, "CLIENT_CREATE", papel="indexacao") is True

    def test_a_rota_de_clientes_nao_restringe_o_papel(self):
        import ast
        import pathlib

        fonte = (pathlib.Path(__file__).resolve().parents[2] / "routes" / "clients.py").read_text(encoding="utf-8")
        funcao = next(
            n for n in ast.walk(ast.parse(fonte))
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_client"
        )
        texto = ast.unparse(funcao)
        assert "get_current_user" in texto and "require_roles" not in texto

    @pytest.mark.asyncio
    async def test_o_index_cria_um_cliente_de_ponta_a_ponta(self, fake_async_db, rede_de_omissao_incumbente):
        from models.client import ClientCreate
        from services import client_crud as mod
        from services import client_uniqueness as cu

        semear(fake_async_db)
        payload = ClientCreate(nome="Cliente do Index", email="novo@x.pt", fonte="staff_created")
        with tenant_db(fake_async_db, mod, cu), \
                patch.object(mod, "encrypt_client_data", lambda d: d), \
                patch.object(mod, "decrypt_client_data", lambda d: d), \
                patch.object(mod, "s3_service", MagicMock()), \
                patch.object(mod, "_send_portal_welcome_email_safe", AsyncMock()):
            await mod.run_create_client(payload, dict(INDEXADOR))
        assert any(str(c.get("nome")).lower() == "cliente do index" for c in fake_async_db.clients.docs)
