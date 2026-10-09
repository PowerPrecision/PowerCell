"""Revogar uma partilha À MÃO — a rota e as regras (Bloco 1, remate).

O CONTEXTO
==========
A Via Rápida (D-25) abre um processo à rede de quem foi atribuído, sem
aprovação. Tirar a atribuição **não** revoga (decisão do dono do produto):
o parceiro mantém o histórico e os documentos que produziu. A revogação é
um acto manual — e até aqui só existia a função de serviço, o que fazia da
Via Rápida uma abertura IRREVERSÍVEL sem acesso à base de dados.

AS REGRAS
=========
* quem revoga: **admin, CEO e diretor** — e o diretor só da casa DONA do
  processo. Um diretor da rede convidada vê o processo mas não é ele quem
  decide quem mais o vê (403, e não 404: já sabe que o processo existe);
* a rede que não vê o processo recebe 404 (não se confirma o id);
* o diretor com `indexacao` de base não deixa rasto de auditoria — a
  restrição de segurança do perfil Indexação;
* a revogação **só retira a empresa pedida**: as outras partilhas e o
  `network_id` do dono ficam intactos.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor"}
CARLA = {"id": "u-carla", "name": "Carla", "email": "carla@precision.pt", "role": "consultor"}
ADMIN = {"id": "u-admin", "name": "Admin", "email": "a@x.pt", "role": "admin"}
CEO = {"id": "u-ceo", "name": "CEO", "email": "c@x.pt", "role": "ceo"}

PARCEIRA_DOMUS = {
    "company_id": "cmp-domus", "company_name": "Domus", "network_id": REDE_DOMUS,
    "added_at": "2026-10-09T10:00:00Z", "added_by": "u-ana",
}
PARCEIRA_OUTRA = {
    "company_id": "cmp-x", "company_name": "Outra", "network_id": "rede_x",
    "added_at": "2026-10-09T10:00:00Z", "added_by": "u-ana",
}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.process_sharing as ps
    import services.process_sharing_api as api
    import services.history as history

    semear(fake_async_db)
    fake_async_db.processes.docs.clear()
    fake_async_db.processes.docs.append({
        "id": "p1", "process_number": 12, "client_name": "Silva", "status": "em_analise",
        "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
        "partner_companies": [dict(PARCEIRA_DOMUS), dict(PARCEIRA_OUTRA)],
        "partner_network_ids": [REDE_DOMUS, "rede_x"],
    })
    with tenant_db(fake_async_db, ps, api, history):
        yield fake_async_db


async def _revogar(user=ANA, company_id="cmp-domus", process_id="p1"):
    import services.process_sharing_api as api

    return await api.run_revoke_partner(process_id, company_id, user, None)


def _processo(db):
    return next(p for p in db.processes.docs if p["id"] == "p1")


class TestAExploracao:
    @pytest.mark.asyncio
    async def test_o_diretor_da_casa_dona_revoga_e_o_parceiro_deixa_de_ver(self, mundo):
        res = await _revogar()
        assert res["success"] is True
        p = _processo(mundo)
        assert [e["company_id"] for e in p["partner_companies"]] == ["cmp-x"]
        assert p["partner_network_ids"] == ["rede_x"]

    @pytest.mark.asyncio
    async def test_a_revogacao_fecha_a_porta_de_facto(self, mundo):
        """O efeito que importa: o convidado deixa de estar no âmbito."""
        from services.tenant_network import processo_no_ambito, resolve_tenant_scope

        scope_bruno = await resolve_tenant_scope(BRUNO)
        assert processo_no_ambito(_processo(mundo), scope_bruno) is True
        await _revogar()
        assert processo_no_ambito(_processo(mundo), scope_bruno) is False


class TestQuemPode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("quem", [ANA, ADMIN, CEO], ids=["diretor", "admin", "ceo"])
    async def test_os_papeis_de_gestao(self, mundo, quem):
        assert (await _revogar(user=quem))["success"] is True

    @pytest.mark.asyncio
    async def test_um_consultor_nao_revoga(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _revogar(user=CARLA)
        assert exc.value.status_code == 403
        assert len(_processo(mundo)["partner_companies"]) == 2

    @pytest.mark.asyncio
    async def test_o_diretor_da_rede_CONVIDADA_nao_revoga_a_propria_entrada(self, mundo):
        """Vê o processo, mas não decide quem o vê: 403 (já sabe que existe)."""
        with pytest.raises(HTTPException) as exc:
            await _revogar(user=BRUNO)
        assert exc.value.status_code == 403
        assert len(_processo(mundo)["partner_companies"]) == 2

    @pytest.mark.asyncio
    async def test_quem_nao_ve_o_processo_recebe_404(self, mundo):
        """Uma rede sem relação nenhuma não aprende que o id existe."""
        mundo.processes.docs[0]["partner_companies"] = []
        mundo.processes.docs[0]["partner_network_ids"] = []
        with pytest.raises(HTTPException) as exc_fora:
            await _revogar(user=BRUNO)
        with pytest.raises(HTTPException) as exc_nada:
            await _revogar(user=ANA, process_id="p-fantasma")
        assert exc_fora.value.status_code == 404
        assert exc_fora.value.detail == exc_nada.value.detail

    @pytest.mark.asyncio
    async def test_o_perfil_efectivo_conta_e_nao_o_do_jwt(self, mundo):
        """Base diretor a trabalhar COMO consultor: não revoga."""
        como_consultor = {**ANA, "effective_role": "consultor"}
        import services.process_sharing_api as api

        class _Req:
            headers = {"X-Active-Role": "consultor"}

        with patch.object(api, "resolver_papel_efectivo", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as exc:
                await api.run_revoke_partner("p1", "cmp-domus", como_consultor, _Req())
        assert exc.value.status_code == 403


class TestOQueSeRevoga:
    @pytest.mark.asyncio
    async def test_so_a_empresa_pedida(self, mundo):
        await _revogar(company_id="cmp-x")
        p = _processo(mundo)
        assert [e["company_id"] for e in p["partner_companies"]] == ["cmp-domus"]
        assert p["network_id"] == REDE_INCUMBENTE, "a propriedade nunca muda"

    @pytest.mark.asyncio
    async def test_uma_empresa_que_nao_e_parceira_da_404(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _revogar(company_id="cmp-precision")
        assert exc.value.status_code == 404
        assert len(_processo(mundo)["partner_companies"]) == 2

    @pytest.mark.asyncio
    async def test_revogar_duas_vezes_a_segunda_da_404(self, mundo):
        await _revogar()
        with pytest.raises(HTTPException) as exc:
            await _revogar()
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_resposta_traz_o_que_sobra(self, mundo):
        res = await _revogar()
        assert [e["company_id"] for e in res["parceiros_restantes"]] == ["cmp-x"]
        assert res["revogadas"] == ["Domus"]


class TestORasto:
    @pytest.mark.asyncio
    async def test_fica_no_trilho_e_no_historico(self, mundo):
        trilho = AsyncMock(return_value="x")
        with patch("services.audit_trail_service.log_audit_event", trilho):
            await _revogar()
        trilho.assert_awaited_once()
        assert trilho.await_args.kwargs["action"] == "process_share_revoked"
        textos = [h["action"] for h in mundo.history.docs]
        assert any("Partilha revogada" in t and "Domus" in t for t in textos)

    @pytest.mark.asyncio
    async def test_o_actor_silenciado_nao_deixa_rasto_nenhum(self, mundo):
        """Restrição de segurança: o perfil Indexação não gera registos de
        actividade/auditoria — aqui, indexação de base a trabalhar como diretor."""
        actor = {**ANA, "role": "indexacao", "effective_role": "diretor"}
        import services.process_sharing_api as api

        trilho = AsyncMock(return_value="x")
        with patch("services.audit_trail_service.log_audit_event", trilho), \
                patch.object(api, "resolver_papel_efectivo", AsyncMock(return_value="diretor")):
            res = await api.run_revoke_partner("p1", "cmp-domus", actor, None)
        assert res["success"] is True
        trilho.assert_not_awaited()
        assert mundo.history.docs == []

    @pytest.mark.asyncio
    async def test_o_desligar_do_historico_de_uma_pessoa_tambem_se_aplica(self, mundo):
        await _revogar(user={**ANA, "track_history": False})
        assert mundo.history.docs == []
        assert len(_processo(mundo)["partner_companies"]) == 1


BACKEND = Path(__file__).resolve().parents[2]


class TestALigacao:
    def _handler(self):
        arvore = ast.parse((BACKEND / "routes" / "processes.py").read_text(encoding="utf-8"))
        return next(
            n for n in arvore.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "revoke_process_partner"
        )

    def test_a_rota_existe_com_request_e_so_para_a_gestao(self):
        h = self._handler()
        fonte = ast.unparse(h)
        assert "request" in {a.arg for a in h.args.args}
        for papel in ("UserRole.ADMIN", "UserRole.CEO", "UserRole.DIRETOR"):
            assert papel in fonte
        assert "UserRole.CONSULTOR" not in fonte
        assert "@router.delete" in ast.unparse(h.decorator_list[0]) or "delete" in ast.unparse(h.decorator_list[0])

    def test_a_rota_chama_o_servico(self):
        assert "run_revoke_partner" in ast.unparse(self._handler())
