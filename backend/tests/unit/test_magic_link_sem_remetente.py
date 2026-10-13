"""Magic link / email de acesso numa rede SEM remetente: 400 claro e fail fast (QA, Out 2026).

O CONTEXTO
  Cortado o recurso à configuração global, uma rede que não configurou email
  (nem geral nem de sistema) deixou de ter de onde enviar. O que a QA viu:
  `500` em `POST /processes/{id}/generate-magic-link/send` e, no monitor, a
  tarefa do email de acesso «Envio directo falhou — retry agendado na fila»
  para sempre — um retry de um erro de configuração nunca pode ter sucesso.

O QUE SE AFIRMA
  * sem remetente → 400 com a mensagem para o utilizador, ANTES de qualquer
    efeito: nenhum token emitido, nenhum código de acesso gravado, nenhum
    «Enviou o link» no histórico;
  * o email de acesso (boas-vindas) falha DEFINITIVAMENTE e não enfileira retry;
  * falhas de CONFIGURAÇÃO da conta (credenciais) são 400; o serviço de email que
    não entrega (rede, timeout, excepção) é 502; só uma falha NOSSA é 500 — e
    sempre como HTTPException com detalhe (contraprova: o 400 não engoliu tudo);
  * contraprova: com remetente tudo continua a funcionar.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import services.client_portal_email as cpe
import services.portal_email_context as pec
import services.portal_magic_link as pml
from services.background_tasks import aguardar_tarefas_pendentes

REDE_OMISSAO = "grupo_power_precision"
REDE_DOMUS = "grupo_domus"

PROCESSO_DOMUS = {
    "id": "p1", "client_id": "c1", "client_name": "Ana", "client_email": "ana@x.pt",
    "network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus",
}
UTILIZADOR = {"id": "u1", "email": "bruno@domus.pt", "role": "diretor"}


class _Pedido:
    headers = {"origin": "https://app.exemplo.pt"}


@pytest.fixture
def ambiente(fake_async_db, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_OMISSAO)
    monkeypatch.setenv("FRONTEND_URL", "https://app.exemplo.pt")
    fake_async_db.companies.docs.extend([
        {"id": "cmp-power", "name": "Power", "network_id": REDE_OMISSAO},
        {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS},
    ])
    fake_async_db.clients.docs.append({"id": "c1", "company_id": "cmp-domus", "network_id": REDE_DOMUS})
    return fake_async_db


def _conta(email="geral@domus.pt"):
    from services.email_service import EmailAccount

    return EmailAccount(
        name="caixa_geral_da_rede", imap_server="imap.domus.pt", imap_port=993,
        smtp_server="smtp.domus.pt", smtp_port=465, email=email, password="pw",
    )


class _Efeitos:
    """Os efeitos que um envio sem remetente NÃO pode ter."""

    def __init__(self):
        self.codigo = AsyncMock(return_value="123456")
        self.emitir = AsyncMock(return_value={
            "magic_link": "https://app.exemplo.pt/portal/abc", "short_id": "abc",
            "token": "t", "frontend_url": "https://app.exemplo.pt",
        })
        self.historico = AsyncMock()
        self.enviar = AsyncMock(return_value={"success": True})


async def _enviar(db, efeitos, *, conta_de_sistema=None, processo=None):
    with patch.object(pec, "db", db), patch.object(pml, "db", db), \
         patch.object(pec, "_conta_de_sistema_generica", AsyncMock(return_value=conta_de_sistema)), \
         patch.object(pml, "ensure_portal_access_code", efeitos.codigo), \
         patch.object(pml, "issue_portal_magic_link", efeitos.emitir), \
         patch("services.history.log_history", efeitos.historico), \
         patch("services.email_service.send_email", efeitos.enviar):
        resposta = await pml.send_magic_link_to_client(
            process_id="p1", process=processo or PROCESSO_DOMUS, user=UTILIZADOR, request=_Pedido(),
        )
        # A entrega corre em segundo plano (Lote 2): espera-se DENTRO dos patches.
        await aguardar_tarefas_pendentes()
        return resposta


def _notificacoes(db):
    return [n for n in db.notifications.docs if n.get("type") == "email_failed"]


@pytest.mark.asyncio
class TestRedeSemRemetente:
    async def test_devolve_400_com_a_mensagem_para_o_utilizador(self, ambiente):
        efeitos = _Efeitos()
        with pytest.raises(HTTPException) as erro:
            await _enviar(ambiente, efeitos)
        assert erro.value.status_code == 400
        assert "Domus" in erro.value.detail and "não tem e-mail configurado" in erro.value.detail

    async def test_nao_emite_token_nem_codigo_nem_historico_nem_envia(self, ambiente):
        efeitos = _Efeitos()
        with pytest.raises(HTTPException):
            await _enviar(ambiente, efeitos)
        efeitos.emitir.assert_not_awaited()
        efeitos.codigo.assert_not_awaited()
        efeitos.historico.assert_not_awaited()
        efeitos.enviar.assert_not_awaited()

    async def test_contraprova_com_a_caixa_geral_da_rede_envia_e_regista(self, ambiente):
        efeitos = _Efeitos()
        ambiente.system_config.docs.append({
            "_id": "company:cmp-domus",
            "email": {"imap_user": "geral@domus.pt", "imap_password": "pw",
                      "imap_server": "imap.domus.pt", "smtp_server": "smtp.domus.pt"},
        })
        with patch.object(pec, "_caixa_geral_da_rede", AsyncMock(return_value=(_conta(), "caixa_geral_da_empresa"))):
            resposta = await _enviar(ambiente, efeitos)
        assert resposta["success"] is True
        efeitos.enviar.assert_awaited_once()
        efeitos.emitir.assert_awaited_once()
        efeitos.historico.assert_awaited_once()

    async def test_contraprova_com_email_de_sistema_tambem_envia(self, ambiente):
        efeitos = _Efeitos()
        resposta = await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
        assert resposta["success"] is True
        efeitos.enviar.assert_awaited_once()

    async def test_a_rede_de_omissao_nao_e_recusada_antes_de_tentar(self, ambiente):
        # Só ela pode contar com o último recurso do `send_email` (contas de ambiente).
        efeitos = _Efeitos()
        processo = {**PROCESSO_DOMUS, "network_id": REDE_OMISSAO, "company_id": "cmp-power", "company_name": "Power"}
        resposta = await _enviar(ambiente, efeitos, processo=processo)
        assert resposta["success"] is True
        efeitos.enviar.assert_awaited_once()

    async def test_sem_rede_de_omissao_configurada_nao_se_antecipa_a_recusa(self, ambiente, monkeypatch):
        # Dev/CI sem `TENANT_DEFAULT_NETWORK_ID`: mantém-se o comportamento anterior
        # ao isolamento (o critério das outras colecções); em produção a variável existe.
        from services.portal_email_context import verificar_remetente

        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        contexto = type("Ctx", (), {"account": None, "network_id": REDE_DOMUS, "nome": "Domus"})()
        with patch("services.portal_email_context._conta_de_sistema_generica", AsyncMock(return_value=None)):
            assert await verificar_remetente(contexto) is None

    async def test_a_falha_so_depois_do_envio_nao_deixa_historico(self, ambiente):
        efeitos = _Efeitos()
        efeitos.enviar.return_value = {"success": False, "error": "boom", "error_code": "outro"}
        resposta = await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
        # O pedido já não espera pela entrega: responde de imediato e a falha chega
        # ao utilizador como notificação.
        assert resposta["queued"] is True
        assert len(_notificacoes(ambiente)) == 1
        assert "boom" in _notificacoes(ambiente)[0]["message"]
        efeitos.historico.assert_not_awaited(), "«Enviou o link» não descreve um envio que falhou"


@pytest.mark.asyncio
class TestFalhasDeConfiguracaoDaConta:
    @pytest.mark.parametrize("codigo", ["smtp_auth", "smtp_password_unreadable"])
    async def test_credenciais_recusadas_sao_400_nao_500(self, ambiente, codigo):
        efeitos = _Efeitos()
        efeitos.enviar.return_value = {"success": False, "error": "535 recusado", "error_code": codigo}
        await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
        avisos = _notificacoes(ambiente)
        assert len(avisos) == 1
        assert "Contas de Email" in avisos[0]["message"]
        efeitos.historico.assert_not_awaited()

    async def test_smtp_nao_configurado_devolvido_pelo_envio_e_400(self, ambiente):
        efeitos = _Efeitos()
        efeitos.enviar.return_value = {"success": False, "error": "x", "error_code": "SMTP_NOT_CONFIGURED"}
        processo = {**PROCESSO_DOMUS, "network_id": REDE_OMISSAO, "company_id": "cmp-power", "company_name": "Power"}
        await _enviar(ambiente, efeitos, processo=processo)
        assert len(_notificacoes(ambiente)) == 1
        efeitos.historico.assert_not_awaited()

    async def test_uma_excepcao_do_servico_de_email_e_502_nao_500(self, ambiente):
        efeitos = _Efeitos()
        efeitos.enviar.side_effect = RuntimeError("rede em baixo")
        resposta = await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
        assert resposta["queued"] is True  # a excepção do serviço de email já não rebenta o pedido
        avisos = _notificacoes(ambiente)
        assert len(avisos) == 1 and "Contas de Email" in avisos[0]["message"]
        efeitos.historico.assert_not_awaited()


@pytest.mark.asyncio
class TestEmailDeAcessoNaoFicaEmLoop:
    async def _entregar(self, db, *, conta_de_sistema=None, conta_da_rede=None, envio_directo=False):
        fila = AsyncMock(return_value="job-1")
        falhou = AsyncMock()
        agendado = AsyncMock()
        with patch.object(pec, "db", db), patch.object(cpe, "db", db), \
             patch.object(pec, "_conta_de_sistema_generica", AsyncMock(return_value=conta_de_sistema)), \
             patch.object(pec, "_caixa_geral_da_rede", AsyncMock(return_value=(conta_da_rede, "x"))), \
             patch("services.email.send_registration_confirmation", AsyncMock(return_value=envio_directo)), \
             patch("services.task_queue.task_queue.send_registration_email", fila), \
             patch("services.email_delivery_status.begin_portal_email_task", AsyncMock(return_value="t1")), \
             patch("services.email_delivery_status.fail_portal_email_task", falhou), \
             patch("services.email_delivery_status.mark_portal_email_retry_scheduled", agendado), \
             patch("services.email_delivery_status.complete_portal_email_task", AsyncMock()):
            resultado = await cpe.deliver_registration_email(
                client_email="ana@x.pt", client_name="Ana", client_id="c1", company_id="cmp-domus",
            )
        return resultado, fila, falhou, agendado

    async def test_sem_remetente_falha_definitivamente_sem_retry(self, ambiente):
        resultado, fila, falhou, agendado = await self._entregar(ambiente)
        assert resultado is False
        fila.assert_not_awaited()
        agendado.assert_not_awaited()
        falhou.assert_awaited_once()
        assert "não tem e-mail configurado" in falhou.await_args.args[2]

    async def test_contraprova_com_remetente_e_envio_falhado_ainda_enfileira(self, ambiente):
        # Uma falha TRANSITÓRIA (rede) com remetente configurado continua a merecer retry.
        resultado, fila, falhou, agendado = await self._entregar(
            ambiente, conta_da_rede=_conta(), envio_directo=False,
        )
        assert resultado is False
        fila.assert_awaited_once()
        agendado.assert_awaited_once()
        falhou.assert_not_awaited()

    async def test_contraprova_com_remetente_e_envio_ok_nao_falha_nem_enfileira(self, ambiente):
        resultado, fila, falhou, agendado = await self._entregar(
            ambiente, conta_da_rede=_conta(), envio_directo=True,
        )
        assert resultado is True
        fila.assert_not_awaited()
        falhou.assert_not_awaited()


@pytest.mark.asyncio
class TestNenhumaExcepcaoDoServicoDeEmailFura:
    """QA, Out 2026: o 500 continuava em produção apesar do fail fast.

    Os testes anteriores substituíam `_conta_de_sistema_generica` por um duplo que
    devolvia sempre bem, e por isso nunca viam a metade que estava FORA do
    `try/except`: `_resolve_system_smtp_account` faz `int(smtp_port)` e uma
    porta gravada como texto («587 », «SSL») levantava `ValueError` dentro do
    `verificar_remetente`, que corre antes do bloco que traduz erros. Aqui
    patcha-se UM NÍVEL ABAIXO (a leitura da configuração).
    """

    async def _enviar_sem_duplo_da_conta(self, db, efeitos, *, processo=None):
        with patch.object(pec, "db", db), patch.object(pml, "db", db), \
             patch.object(pml, "ensure_portal_access_code", efeitos.codigo), \
             patch.object(pml, "issue_portal_magic_link", efeitos.emitir), \
             patch("services.history.log_history", efeitos.historico), \
             patch("services.email_service.send_email", efeitos.enviar):
            resposta = await pml.send_magic_link_to_client(
                process_id="p1", process=processo or PROCESSO_DOMUS, user=UTILIZADOR, request=_Pedido(),
            )
            await aguardar_tarefas_pendentes()
            return resposta

    async def test_porta_smtp_ilegivel_na_config_de_sistema_e_400_nao_excepcao(self, ambiente):
        efeitos = _Efeitos()
        with patch("services.email_service._resolve_system_smtp_account",
                   AsyncMock(side_effect=ValueError("invalid literal for int() with base 10: 'SSL'"))), \
             patch("services.email.get_system_transporter", AsyncMock(side_effect=RuntimeError("sem db"))):
            with pytest.raises(HTTPException) as erro:
                await self._enviar_sem_duplo_da_conta(ambiente, efeitos)
        assert erro.value.status_code == 400
        assert "não tem e-mail configurado" in erro.value.detail
        efeitos.emitir.assert_not_awaited()
        efeitos.enviar.assert_not_awaited()

    async def test_a_conta_de_sistema_generica_nunca_levanta(self, ambiente):
        for falha in (ValueError("porta"), TypeError("x"), RuntimeError("db"), KeyError("host")):
            with patch("services.email_service._resolve_system_smtp_account", AsyncMock(side_effect=falha)), \
                 patch("services.email.get_system_transporter", AsyncMock(side_effect=falha)):
                assert await pec._conta_de_sistema_generica(REDE_DOMUS) is None

    async def test_transporte_de_sistema_com_campos_em_falta_nao_levanta(self, ambiente):
        # `transporte["host"]` num dicionário incompleto era um KeyError fora do try.
        with patch("services.email_service._resolve_system_smtp_account", AsyncMock(return_value=None)), \
             patch("services.email.get_system_transporter",
                   AsyncMock(return_value={"source": "db"})):
            assert await pec._conta_de_sistema_generica(REDE_DOMUS) is None

    async def test_contraprova_a_conta_de_sistema_valida_continua_a_servir(self, ambiente):
        with patch("services.email_service._resolve_system_smtp_account",
                   AsyncMock(return_value=_conta("no-reply@sistema.pt"))):
            assert (await pec._conta_de_sistema_generica(REDE_DOMUS)).email == "no-reply@sistema.pt"

    async def test_falha_interna_antes_do_envio_e_um_500_com_detalhe(self, ambiente):
        efeitos = _Efeitos()
        efeitos.codigo.side_effect = RuntimeError("mongo em baixo")
        with pytest.raises(HTTPException) as erro:
            await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
        assert erro.value.status_code == 500
        assert erro.value.detail == pml.DETALHE_FALHA_INTERNA
        efeitos.enviar.assert_not_awaited()

    async def test_so_HTTPException_sai_da_funcao_publica(self, ambiente):
        """Qualquer excepção — de qualquer camada — sai traduzida."""
        for ponto in ("codigo", "emitir", "enviar"):
            efeitos = _Efeitos()
            getattr(efeitos, ponto).side_effect = Exception("qualquer coisa")
            try:
                await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
            except HTTPException:
                continue
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"{ponto}: escapou {type(exc).__name__} sem tradução")

    async def test_o_historico_falhar_depois_de_enviar_nao_transforma_o_sucesso_em_erro(self, ambiente):
        efeitos = _Efeitos()
        efeitos.historico.side_effect = RuntimeError("history em baixo")
        resposta = await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
        assert resposta["success"] is True
        efeitos.enviar.assert_awaited_once()


@pytest.mark.asyncio
class TestOEnvioNaoBloqueiaOPedido:
    """Lote 2 (Out 2026): o SMTP pendurado fazia o pedido esperar até ao 502 do proxy."""

    async def test_o_pedido_responde_sem_esperar_pela_entrega(self, ambiente):
        import asyncio

        efeitos = _Efeitos()
        libertar = asyncio.Event()

        async def envio_lento(*a, **k):
            await libertar.wait()
            return {"success": True}

        efeitos.enviar.side_effect = envio_lento
        with patch.object(pec, "db", ambiente), patch.object(pml, "db", ambiente), \
             patch.object(pec, "_conta_de_sistema_generica", AsyncMock(return_value=_conta("no-reply@sistema.pt"))), \
             patch.object(pml, "ensure_portal_access_code", efeitos.codigo), \
             patch.object(pml, "issue_portal_magic_link", efeitos.emitir), \
             patch("services.history.log_history", efeitos.historico), \
             patch("services.email_service.send_email", efeitos.enviar):
            resposta = await asyncio.wait_for(
                pml.send_magic_link_to_client(
                    process_id="p1", process=PROCESSO_DOMUS, user=UTILIZADOR, request=_Pedido(),
                ),
                timeout=2,
            )
            assert resposta["success"] is True and resposta["queued"] is True
            efeitos.historico.assert_not_awaited()  # ainda nada saiu
            libertar.set()
            await aguardar_tarefas_pendentes()
        efeitos.historico.assert_awaited_once()
        assert not _notificacoes(ambiente)

    async def test_cliente_sem_email_continua_a_ser_400_imediato(self, ambiente):
        efeitos = _Efeitos()
        with pytest.raises(HTTPException) as erro:
            await _enviar(
                ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"),
                processo={**PROCESSO_DOMUS, "client_email": ""},
            )
        assert erro.value.status_code == 400
        efeitos.enviar.assert_not_awaited()

    async def test_a_falha_da_entrega_avisa_quem_pediu_e_so_ele(self, ambiente):
        efeitos = _Efeitos()
        efeitos.enviar.return_value = {"success": False, "error": "relay recusado", "error_code": "x"}
        await _enviar(ambiente, efeitos, conta_de_sistema=_conta("no-reply@sistema.pt"))
        avisos = _notificacoes(ambiente)
        assert [a["user_id"] for a in avisos] == [UTILIZADOR["id"]]
        assert avisos[0]["process_id"] == "p1" and avisos[0]["read"] is False
