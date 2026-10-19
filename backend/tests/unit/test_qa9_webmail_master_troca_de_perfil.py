"""QA-9, ponto 5 — o Master que troca de empresa no topo não pode ver o Webmail vazio.

O QUE A QA VIU
==============
Ao trocar de perfil/empresa no topo, o Webmail mostrava a caixa da empresa mas a lista vinha vazia.

CAUSA (reproduzida aqui, antes da correcção)
    As CONTAS (`/users/me/email-accounts?scope=all`) já seguem a VISTA do Master — mostram a Caixa
    Geral da empresa escolhida mesmo sem ele ter UCR nela —, mas os SEPARADORES e o âmbito da lista
    (`webmail_scope.empresas_do_webmail`) eram só por UCR. O Master a trabalhar como Master numa
    empresa onde não tem UCR via a caixa, e o pedido da lista (`company_id=<essa empresa>`) levava
    404 «Empresa não encontrada»: a interface engolia o erro e mostrava a lista vazia. Duas metades
    certas, a combinação não — a família do `build_company_scope_condition`.

A REGRA
    A empresa da VISTA do Master é sempre um separador válido (com papel `master`); sem vista, só
    os UCR (a vista «Sistema» não inventa separadores). Um perfil local NUNCA ganha a empresa por
    ter escolhido um cabeçalho: o cabeçalho não alarga.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import EMPRESAS, REDE_INCUMBENTE, tenant_db

MASTER = {"id": "u-master", "name": "Master", "role": "master"}
CEO = {"id": "u-ceo", "name": "Rui", "role": "ceo"}


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    import services.webmail_scope as separadores

    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    fake_async_db.companies.docs.extend(dict(e) for e in EMPRESAS)
    # O Master tem UCR só na Power; o CEO só na Power também.
    for uid in ("u-master", "u-ceo"):
        fake_async_db.user_company_roles.docs.append(
            {"user_id": uid, "company_id": "cmp-power", "company_name": "Power Real Estate",
             "role": "admin" if uid == "u-master" else "ceo"},
        )
    with tenant_db(fake_async_db, separadores):
        yield separadores


def _com_vista(user, vista):
    return {**user, "vista_empresa_id": vista}


@pytest.mark.asyncio
class TestOMasterComVista:

    async def test_a_empresa_da_vista_e_um_separador_mesmo_sem_ucr(self, mundo):
        ids = [e.company_id for e in await mundo.empresas_do_webmail(_com_vista(MASTER, "cmp-precision"))]
        assert "cmp-precision" in ids

    async def test_o_pedido_da_lista_dessa_empresa_ja_nao_da_404(self, mundo):
        empresa = await mundo.assert_empresa_no_ambito(_com_vista(MASTER, "cmp-precision"), "cmp-precision")
        assert empresa.company_id == "cmp-precision"
        assert empresa.company_name == "Precision Crédito"

    async def test_o_scope_da_lista_nao_e_impossivel(self, mundo):
        cond = await mundo.build_webmail_scope(_com_vista(MASTER, "cmp-precision"), "cmp-precision", box="personal")
        assert cond != mundo.CONDICAO_IMPOSSIVEL
        assert {"company_id": "cmp-precision"} == cond or "cmp-precision" in repr(cond)

    async def test_a_vista_noutra_rede_tambem_funciona(self, mundo):
        ids = [e.company_id for e in await mundo.empresas_do_webmail(_com_vista(MASTER, "cmp-domus"))]
        assert ids == ["cmp-domus"]  # a Power (outra rede) sai: a vista estreita

    async def test_a_caixa_geral_da_empresa_da_vista_conta_para_o_master(self, mundo):
        empresa = await mundo.assert_empresa_no_ambito(_com_vista(MASTER, "cmp-domus"), "cmp-domus")
        assert empresa.tem_caixa_geral is True


@pytest.mark.asyncio
class TestContraprovas:

    async def test_sem_vista_o_master_so_tem_os_seus_ucr(self, mundo):
        ids = [e.company_id for e in await mundo.empresas_do_webmail(MASTER)]
        assert ids == ["cmp-power"]

    async def test_sem_vista_pedir_outra_empresa_continua_a_ser_404(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await mundo.assert_empresa_no_ambito(MASTER, "cmp-precision")
        assert exc.value.status_code == 404

    async def test_o_ataque_um_ceo_com_cabecalho_forjado_nao_ganha_a_empresa(self, mundo):
        for forjada in ("cmp-precision", "cmp-domus"):
            ceo = _com_vista(CEO, forjada)
            ids = [e.company_id for e in await mundo.empresas_do_webmail(ceo)]
            assert forjada not in ids
            with pytest.raises(HTTPException) as exc:
                await mundo.assert_empresa_no_ambito(ceo, forjada)
            assert exc.value.status_code == 404

    async def test_uma_empresa_inexistente_na_vista_nao_cria_separador(self, mundo):
        ids = [e.company_id for e in await mundo.empresas_do_webmail(_com_vista(MASTER, "cmp-fantasma"))]
        assert "cmp-fantasma" not in ids


# ──────────────────────────────────────────────────────────────────────────────
#  De ponta a ponta: `run_webmail_list` a sério, sem UCR do Master na empresa
# ──────────────────────────────────────────────────────────────────────────────
class TestAListaDoWebmailDeBandaABanda:

    @staticmethod
    async def _listar(fake_db, user, company_id, box="personal"):
        from unittest.mock import patch

        import services.email_enrich as enrich
        import services.email_webmail as mod

        async def papel(_r, _u):
            return "master"

        async def contas(_uid):
            return []

        async def cargos(_r, _u):
            return {"master"}

        with tenant_db(fake_db, mod, enrich), patch("services.webmail_scope.db", fake_db), \
                patch("services.auth.get_effective_role_async", papel), \
                patch.object(mod, "_resolve_conversation_emails", contas), \
                patch.object(mod, "_user_ucr_roles", cargos):
            res = await mod.run_webmail_list(None, user, folder="inbox", box=box, company_id=company_id)
        return {e["id"] for e in res.get("emails", [])}

    @pytest.mark.asyncio
    async def test_o_master_com_a_precision_escolhida_ve_a_caixa_geral_da_precision(self, mundo, fake_async_db):
        fake_async_db.emails.docs.extend([
            {"id": "e-prec", "company_id": "cmp-precision", "shared_role": "geral", "folder": "Inbox", "direction": "received",
             "subject": "Da Precision", "is_archived": False, "received_at": "2026-10-18T10:00:00Z"},
            {"id": "e-dom", "company_id": "cmp-domus", "shared_role": "geral", "folder": "Inbox", "direction": "received",
             "subject": "Da Domus", "is_archived": False, "received_at": "2026-10-18T10:00:00Z"},
        ])
        ids = await self._listar(fake_async_db, _com_vista(MASTER, "cmp-precision"), "cmp-precision", box="general")
        assert ids == {"e-prec"}

    @pytest.mark.asyncio
    async def test_sem_a_vista_o_mesmo_pedido_continua_recusado(self, mundo, fake_async_db):
        with pytest.raises(HTTPException) as exc:
            await self._listar(fake_async_db, MASTER, "cmp-precision", box="general")
        assert exc.value.status_code == 404
