"""O alerta «Email de acesso não entregue» desaparece quando o acesso é reenviado (QA-6).

Só o email de BOAS-VINDAS actualizava `clients.portal_email_delivery`. «Enviar por Email» do
link do Portal e «Reenviar acesso» enviavam com sucesso e deixavam o estado a `failed`: o
aviso crítico ficava para sempre nos Detalhes do Processo.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import email_delivery_status as eds
from services import portal_magic_link as pml
from services.alerts import check_portal_email_delivery_alert


async def _mundo(db):
    await db.clients.insert_one({
        "id": "c1", "contacto": {"email": "cli@x.pt"},
        "portal_email_delivery": {"status": "failed", "error": "smtp"},
    })
    await db.processes.insert_one({"id": "p1", "client_id": "c1"})


def _entrega(**extra):
    base = dict(
        contexto=object(), process_id="p1", user={"id": "u1"}, client_email="cli@x.pt",
        client_name="Cli", text_body="t", html_body="h", short_id="abc",
    )
    base.update(extra)
    return base


@pytest.mark.asyncio
class TestOAlertaLimpaAoReenviar:
    async def test_um_envio_com_sucesso_limpa_o_alerta(self, fake_async_db):
        await _mundo(fake_async_db)
        ok = AsyncMock(return_value={"success": True})
        with patch.object(eds, "db", fake_async_db), patch("services.alerts.db", fake_async_db), \
                patch("services.portal_email_context.enviar_email_do_portal", ok), \
                patch("services.history.log_history", AsyncMock()):
            assert (await check_portal_email_delivery_alert({"client_id": "c1"}))["active"] is True
            await pml._entregar_magic_link(**_entrega())
            assert (await check_portal_email_delivery_alert({"client_id": "c1"}))["active"] is False
        cliente = await fake_async_db.clients.find_one({"id": "c1"})
        assert cliente["portal_email_delivery"]["status"] == "sent"

    async def test_um_envio_que_FALHA_nao_limpa_o_alerta(self, fake_async_db):
        """Contraprova: limpar sem entregar esconderia um problema real."""
        await _mundo(fake_async_db)
        falha = AsyncMock(return_value={"success": False, "error": "535"})
        with patch.object(eds, "db", fake_async_db), patch("services.alerts.db", fake_async_db), \
                patch("services.portal_email_context.enviar_email_do_portal", falha), \
                patch.object(pml, "_avisar_falha_do_envio", AsyncMock()):
            await pml._entregar_magic_link(**_entrega())
            assert (await check_portal_email_delivery_alert({"client_id": "c1"}))["active"] is True

    async def test_processo_inexistente_nao_rebenta(self, fake_async_db):
        with patch.object(eds, "db", fake_async_db):
            await eds.registar_acesso_entregue_do_processo("nao-existe")
            await eds.registar_acesso_entregue_do_processo(None)
