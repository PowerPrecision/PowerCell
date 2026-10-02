"""Eliminar um cliente: a porta e a guarda interna lêem o MESMO papel.

O DEFEITO (Lote 4, ponto 2)
===========================
`DELETE /clients/{id}` tem DUAS verificações:

1. `require_roles([ADMIN, CEO, DIRETOR, ADMINISTRATIVO])` na rota, que
   decide pelo cargo **EFECTIVO** (UCR + `X-Active-Role`);
2. dentro de `run_delete_client`,
   `if user.get("role") not in [...]` — o cargo do **JWT**.

Quem tem perfil base de consultor e entra COMO diretor (que é a forma
como o produto quer que se troque de chapéu) passa a porta e leva 403 na
segunda. O botão aparece, o pedido sai, o servidor recusa e não há nada
no ecrã que explique porquê.

É a forma exacta do `history._is_stealth_user` do Lote 4 — duas noções
de papel no mesmo caminho, e a que manda não é a certa. No sentido
inverso não há escalada: um admin de base a agir como consultor é
recusado à PORTA, porque essa é a que lê o papel efectivo. O modo de
falha é a recusa indevida, que é o pior dos dois para quem trabalha.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.unit.helpers_fonte import codigo_sem_comentarios  # noqa: E402

ROTAS = BACKEND / "routes" / "clients.py"
SERVICO = BACKEND / "services" / "client_delete.py"


def _utilizador(papel_base: str) -> dict:
    return {"id": "u1", "role": papel_base, "name": "Quem Apaga"}


async def _eliminar(papel_base: str, papel_efectivo, fake_async_db):
    from unittest.mock import patch

    from services import client_delete

    with patch.object(client_delete, "db", fake_async_db):
        return await client_delete.run_delete_client(
            "cliente-inexistente",
            _utilizador(papel_base),
            papel_efectivo=papel_efectivo,
        )


class TestQuemPodeEliminar:
    @pytest.mark.asyncio
    async def test_consultor_a_agir_COMO_diretor_e_aceito(self, fake_async_db):
        """O caso que estava partido."""
        with pytest.raises(HTTPException) as erro:
            await _eliminar("consultor", "diretor", fake_async_db)
        # 404 (o cliente não existe) e NÃO 403: a guarda deixou passar.
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_consultor_sem_perfil_de_gestao_e_recusado(self, fake_async_db):
        with pytest.raises(HTTPException) as erro:
            await _eliminar("consultor", "consultor", fake_async_db)
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["admin", "ceo", "diretor", "administrativo"])
    async def test_os_quatro_papeis_da_constante_passam(self, papel, fake_async_db):
        with pytest.raises(HTTPException) as erro:
            await _eliminar(papel, papel, fake_async_db)
        assert erro.value.status_code == 404, papel

    @pytest.mark.asyncio
    async def test_o_perfil_indexacao_NUNCA_elimina(self, fake_async_db):
        """E é por isso que esta operação não tem de filtrar o registo de
        actividade do perfil `indexacao`: ele não chega aqui.

        (A operação não escreve em `db.history` — o rasto é o
        `deleted_by`/`deleted_at` no próprio documento, que é o que o
        restauro lê.)
        """
        with pytest.raises(HTTPException) as erro:
            await _eliminar("indexacao", "indexacao", fake_async_db)
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_sem_papel_efectivo_recua_para_o_do_JWT(self, fake_async_db):
        """Compatibilidade: um chamador antigo (sem `Request`) não pode
        passar a ser recusado só por não saber o papel activo."""
        with pytest.raises(HTTPException) as erro:
            await _eliminar("admin", None, fake_async_db)
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test___all_roles___nao_e_um_bypass(self, fake_async_db):
        """O sentinel de filtragem de dados recua para o cargo do JWT —
        é o que `authorization_role` garante, e tê-lo escrito à mão aqui
        significaria descobri-lo outra vez."""
        with pytest.raises(HTTPException) as erro:
            await _eliminar("consultor", "__all_roles__", fake_async_db)
        assert erro.value.status_code == 403


class TestAsDuasPontasDerivamDaMesmaConstante:
    def test_a_rota_usa_a_constante_do_servico(self):
        fonte = codigo_sem_comentarios(ROTAS.read_text(encoding="utf-8"))
        assert "require_roles(list(PAPEIS_QUE_PODEM_ELIMINAR_CLIENTES))" in fonte
        # CONTRAPROVA: a lista escrita à mão saiu de lá.
        assert 'UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))' not in fonte

    def test_a_rota_passa_o_papel_efectivo(self):
        fonte = codigo_sem_comentarios(ROTAS.read_text(encoding="utf-8"))
        # Duas afirmações e não uma cadeia literal: o papel é RESOLVIDO a
        # partir do `request` e PASSADO ao serviço. Uma só afirmação sobre
        # a linha inteira quebra-se com uma mudança de formatação e, pior,
        # resolver sem passar (ou passar outra coisa) satisfazia-a.
        assert "await get_effective_role_async(request, user)" in fonte
        assert "papel_efectivo=papel" in fonte

    def test_a_guarda_interna_nao_le_o_papel_do_JWT(self):
        fonte = codigo_sem_comentarios(SERVICO.read_text(encoding="utf-8"))
        assert 'user.get("role") not in' not in fonte
        assert "effective_role_is_allowed(papel" in fonte

    def test_a_constante_tem_os_quatro_papeis(self):
        from models.auth import UserRole
        from services.client_delete import PAPEIS_QUE_PODEM_ELIMINAR_CLIENTES

        assert set(PAPEIS_QUE_PODEM_ELIMINAR_CLIENTES) == {
            UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO,
        }
