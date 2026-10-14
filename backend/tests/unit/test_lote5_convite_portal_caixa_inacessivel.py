"""
Lote 5, ponto 2 (Out 2026) — o convite/link do Portal falhava com «o servidor de e-mail da empresa não
respondeu ou recusou o envio», enquanto o RGPD e o resto saíam bem para o MESMO cliente.

A CAUSA
  O email do Portal sai PRIMEIRO pela Caixa Geral da rede (SMTP directo, `SMTP_SSL`), ao contrário do RGPD,
  que sai pelo Email do Sistema (Resend, HTTPS). Quando a ligação à Caixa Geral não chega a acontecer
  (timeout, ligação recusada, porta SMTP bloqueada pela hospedagem), o `send_email` devolvia uma falha
  GENÉRICA, sem `error_code` — e o `enviar_email_do_portal` só recua para o Email do Sistema em falhas de
  configuração. O envio morria na caixa avariada com o canal bom ao lado.

A REGRA
  Uma falha ANTES de o login ter sucesso é uma falha em que NADA foi entregue (`smtp_connection`): recuar
  para outro canal não duplica o email. Uma falha DEPOIS (a meio do `sendmail`) continua a não recuar.

Os testes patcham o `smtplib` (o transporte), nunca o `send_email`: um duplo do `send_email` reimplementaria
a classificação que falhou.
"""
from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.email_service as es
import services.portal_email_context as pec
import services.portal_magic_link as pml
from services.background_tasks import aguardar_tarefas_pendentes
from tests.unit.test_magic_link_sem_remetente import PROCESSO_DOMUS, UTILIZADOR, _Pedido, _conta, ambiente  # noqa: F401


def _smtp_que_aceita():
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    return smtp


def _smtp_que_falha_no_login():
    smtp = _smtp_que_aceita()
    smtp.login.side_effect = OSError("rede caiu no login")
    return smtp


def _smtp_que_falha_no_envio():
    smtp = _smtp_que_aceita()
    smtp.sendmail.side_effect = OSError("rede caiu a meio do envio")
    return smtp


def _transporte(caixa, sistema):
    """`SMTP_SSL` que escolhe o comportamento pelo servidor: a caixa da rede vs o email de sistema."""
    def fabrica(host, *args, **kwargs):
        if isinstance(caixa, Exception) and host == "smtp.domus.pt":
            raise caixa
        return caixa if host == "smtp.domus.pt" else sistema

    return fabrica


@pytest.mark.asyncio
class TestOSendEmailClassificaAFalhaDeLigacao:
    async def _enviar(self, **efeito):
        with patch.object(es.smtplib, "SMTP_SSL", side_effect=efeito.get("fabrica")):
            return await es.send_email(
                account_name="x", to_emails=["cli@x.pt"], subject="s", body="b", account_override=_conta(),
            )

    @pytest.mark.parametrize("erro", [
        socket.timeout("timed out"),
        ConnectionRefusedError("recusada"),
        socket.gaierror("sem DNS"),
        OSError("Network is unreachable"),
    ])
    async def test_falha_ao_ligar_nao_entrega_nada_e_diz_se(self, erro):
        r = await self._enviar(fabrica=_transporte(erro, _smtp_que_aceita()))
        assert r["success"] is False
        assert r["error_code"] == "smtp_connection"
        assert "smtp.domus.pt:465" in r["error"], "diz a que servidor não se chegou"

    async def test_falha_no_login_por_rede_tambem_e_antes_da_entrega(self):
        r = await self._enviar(fabrica=_transporte(_smtp_que_falha_no_login(), _smtp_que_aceita()))
        assert r["error_code"] == "smtp_connection"

    async def test_contraprova_falha_a_meio_do_envio_NAO_e_classificada_como_sem_ligacao(self):
        """O servidor pode já ter aceitado a mensagem: recuar aqui duplicava o email ao cliente."""
        r = await self._enviar(fabrica=_transporte(_smtp_que_falha_no_envio(), _smtp_que_aceita()))
        assert r["success"] is False
        assert r.get("error_code") != "smtp_connection"

    async def test_contraprova_autenticacao_recusada_continua_a_ser_smtp_auth(self):
        import smtplib

        smtp = _smtp_que_aceita()
        smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad")
        r = await self._enviar(fabrica=_transporte(smtp, _smtp_que_aceita()))
        assert r["error_code"] == "smtp_auth"

    async def test_contraprova_um_envio_bom_continua_bom(self):
        smtp = _smtp_que_aceita()
        r = await self._enviar(fabrica=_transporte(smtp, _smtp_que_aceita()))
        assert r["success"] is True
        smtp.sendmail.assert_called_once()


@pytest.mark.asyncio
class TestOPortalRecuaParaOEmailDoSistema:
    async def _contexto(self, ambiente):
        with patch.object(pec, "db", ambiente), \
                patch.object(pec, "_caixa_geral_da_rede", AsyncMock(return_value=(_conta(), "caixa_geral_da_empresa"))):
            return await pec.resolver_contexto(company_id="cmp-domus", client_id="c1", user=UTILIZADOR)

    async def _enviar_portal(self, ambiente, caixa, sistema, *, conta_do_sistema="presente"):
        contexto = await self._contexto(ambiente)
        conta_sis = _conta("no-reply@sistema.pt") if conta_do_sistema == "presente" else None
        if conta_sis is not None:
            conta_sis.smtp_server = "smtp.sistema.pt"
        with patch.object(pec, "_conta_de_sistema_generica", AsyncMock(return_value=conta_sis)), \
                patch.object(es.smtplib, "SMTP_SSL", side_effect=_transporte(caixa, sistema)):
            return await pec.enviar_email_do_portal(
                contexto, to_emails=["cli@x.pt"], subject="Portal", body="corpo", body_html="<p>corpo</p>",
            )

    async def test_a_caixa_da_rede_inacessivel_recua_para_o_email_do_sistema(self, ambiente):
        sistema = _smtp_que_aceita()
        r = await self._enviar_portal(ambiente, socket.timeout("timed out"), sistema)
        assert r["success"] is True
        sistema.sendmail.assert_called_once()

    async def test_a_caixa_que_responde_nao_toca_no_email_do_sistema(self, ambiente):
        caixa, sistema = _smtp_que_aceita(), _smtp_que_aceita()
        r = await self._enviar_portal(ambiente, caixa, sistema)
        assert r["success"] is True
        caixa.sendmail.assert_called_once()
        sistema.sendmail.assert_not_called()

    async def test_a_exploracao_falha_a_meio_do_envio_nao_duplica_pelo_canal_de_sistema(self, ambiente):
        caixa, sistema = _smtp_que_falha_no_envio(), _smtp_que_aceita()
        r = await self._enviar_portal(ambiente, caixa, sistema)
        assert r["success"] is False
        sistema.sendmail.assert_not_called()

    async def test_sem_email_do_sistema_a_falha_e_devolvida_com_o_motivo(self, ambiente):
        r = await self._enviar_portal(ambiente, socket.timeout("t"), _smtp_que_aceita(), conta_do_sistema="ausente")
        assert r["success"] is False
        assert r["error_code"] == "smtp_connection"


@pytest.mark.asyncio
class TestOBotaoDoLinkDoPortalDePontaAPonta:
    """O fluxo real do botão, com o `send_email` REAL e só o `smtplib` falso."""

    async def _clicar(self, ambiente, caixa, sistema):
        conta_sis = _conta("no-reply@sistema.pt")
        conta_sis.smtp_server = "smtp.sistema.pt"
        with patch.object(pec, "db", ambiente), patch.object(pml, "db", ambiente), \
                patch.object(pec, "_conta_de_sistema_generica", AsyncMock(return_value=conta_sis)), \
                patch.object(pec, "_caixa_geral_da_rede", AsyncMock(return_value=(_conta(), "caixa_geral_da_empresa"))), \
                patch.object(pml, "ensure_portal_access_code", AsyncMock(return_value="123456")), \
                patch.object(pml, "issue_portal_magic_link", AsyncMock(return_value={
                    "magic_link": "https://app.exemplo.pt/portal/abc", "short_id": "abc", "token": "t",
                    "frontend_url": "https://app.exemplo.pt"})), \
                patch("services.history.log_history", AsyncMock()), \
                patch.object(es.smtplib, "SMTP_SSL", side_effect=_transporte(caixa, sistema)):
            await pml.send_magic_link_to_client(
                process_id="p1", process=PROCESSO_DOMUS, user=UTILIZADOR, request=_Pedido(),
            )
            await aguardar_tarefas_pendentes()
        return [n for n in ambiente.notifications.docs if n.get("type") == "email_failed"]

    async def test_caixa_geral_inacessivel_o_cliente_recebe_o_link_e_ninguem_e_avisado_de_falha(self, ambiente):
        sistema = _smtp_que_aceita()
        falhas = await self._clicar(ambiente, ConnectionRefusedError("recusada"), sistema)
        assert falhas == []
        sistema.sendmail.assert_called_once()

    async def test_se_os_dois_canais_falham_quem_pediu_e_avisado_com_o_motivo(self, ambiente):
        falhas = await self._clicar(
            ambiente, ConnectionRefusedError("recusada"), OSError("sistema também em baixo"),
        )
        assert len(falhas) == 1
        assert "não foi enviado" in falhas[0]["message"]
