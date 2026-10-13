"""E-mails de SISTEMA (transacionais) saem pelo «Email do Sistema (Transacional)» (QA, Out 2026).

REGRA DE NEGÓCIO
  O Magic Link e as boas-vindas do Portal são transacionais: usam o cartão «Email do
  Sistema (Transacional)» (`SystemConfig.system_smtp`, o «Bloco A», no documento
  GLOBAL), para QUALQUER empresa — incluindo as das redes satélite. O isolamento do
  Webmail (`webmail_heranca`) é sobre as CAIXAS de correio (IMAP/SMTP de cada empresa);
  não toca neste cartão.

POR QUE ESTE TESTE NÃO USA DUPLOS DA CONTA
  Os anteriores substituíam `_conta_de_sistema_generica`/`send_email`, ou seja, a
  própria coisa que decide se há remetente. Aqui só o TRANSPORTE (`_send_via_resend`)
  é falso: a leitura do Bloco A, o `portal_email_context`, o `send_email` e a
  resolução da empresa são os de produção, sobre uma base de dados em memória.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import services.client_portal_email as cpe
import services.email_service as es
import services.portal_email_context as pec
import services.portal_magic_link as pml
import services.system_config as sc
from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE, semear, tenant_db

PROCESSO_DOMUS = {
    "id": "p1", "client_id": "c1", "client_name": "Ana", "client_email": "ana@x.pt",
    "network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus",
}
PROCESSO_POWER = {
    "id": "p2", "client_id": "c2", "client_name": "Rui", "client_email": "rui@x.pt",
    "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "company_name": "Power Real Estate",
}
UTILIZADOR = {"id": "u1", "email": "bruno@domus.pt", "role": "diretor", "effective_role": "diretor"}


class _Pedido:
    headers = {"origin": "https://app.exemplo.pt"}


def _bloco_a(**campos):
    return {
        "_id": "main", "company_id": "default",
        "system_smtp": {
            "resend_api_key": "re_CHAVE_DO_SISTEMA",
            "smtp_from_email": "no-reply@sistema.pt",
            "smtp_from_name": "Sistema",
            **campos,
        },
    }


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    monkeypatch.setenv("FRONTEND_URL", "https://app.exemplo.pt")
    semear(fake_async_db)
    fake_async_db.clients.docs.append({"id": "c1", "company_id": "cmp-domus", "network_id": REDE_DOMUS})
    sc._config_cache.clear()
    yield fake_async_db
    sc._config_cache.clear()


def _contexto_de_producao(db, *extra):
    """Patcha a `db` de TODA a cadeia real (e só ela)."""
    return tenant_db(db, pec, es, sc, pml, cpe, *extra)


async def _enviar_link(db, processo):
    transporte = MagicMock(return_value={"id": "email-1"})
    with _contexto_de_producao(db), \
         patch.object(es, "_send_via_resend", transporte), \
         patch.object(pml, "ensure_portal_access_code", MagicMock(side_effect=lambda cid: _coro("123456"))), \
         patch.object(pml, "issue_portal_magic_link", MagicMock(side_effect=lambda **k: _coro({
             "magic_link": "https://app.exemplo.pt/portal/abc", "short_id": "abc",
             "token": "t", "frontend_url": "https://app.exemplo.pt"}))), \
         patch("services.history.log_history", MagicMock(side_effect=lambda *a, **k: _coro(None))):
        resposta = await pml.send_magic_link_to_client(
            process_id=processo["id"], process=processo, user=UTILIZADOR, request=_Pedido(),
        )
        from services.background_tasks import aguardar_tarefas_pendentes
        await aguardar_tarefas_pendentes()  # a entrega corre em segundo plano
    return resposta, transporte


async def _coro(valor):
    return valor


@pytest.mark.asyncio
class TestMagicLinkPeloEmailDoSistema:
    async def test_empresa_satelite_sem_caixa_propria_envia_pelo_email_do_sistema(self, mundo):
        mundo.system_config.docs.append(_bloco_a())
        resposta, transporte = await _enviar_link(mundo, PROCESSO_DOMUS)
        assert resposta["success"] is True
        transporte.assert_called_once()
        assert transporte.call_args.kwargs.get("api_key", transporte.call_args.args[0] if transporte.call_args.args else None) is not None

    async def test_o_remetente_leva_o_nome_da_empresa_e_nao_o_da_outra_rede(self, mundo):
        mundo.system_config.docs.append(_bloco_a())
        _, transporte = await _enviar_link(mundo, PROCESSO_DOMUS)
        texto = repr(transporte.call_args)
        assert "no-reply@sistema.pt" in texto, "sai pela conta transaccional do sistema"
        assert "Domus" in texto, "com o nome da empresa do cliente"

    async def test_a_rede_de_omissao_tambem_envia_pelo_email_do_sistema(self, mundo):
        mundo.system_config.docs.append(_bloco_a())
        resposta, transporte = await _enviar_link(mundo, PROCESSO_POWER)
        assert resposta["success"] is True
        transporte.assert_called_once()

    async def test_smtp_directo_do_bloco_a_tambem_serve(self, mundo):
        mundo.system_config.docs.append({
            "_id": "main", "company_id": "default",
            "system_smtp": {"smtp_host": "smtp.sistema.pt", "smtp_username": "no-reply@sistema.pt",
                            "smtp_password": "pw", "smtp_port": 587},
        })
        with _contexto_de_producao(mundo):
            conta = await pec._conta_de_sistema_generica(REDE_DOMUS)
        assert conta is not None and conta.smtp_server == "smtp.sistema.pt"

    async def test_sem_bloco_a_continua_a_ser_400_claro(self, mundo):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as erro:
            await _enviar_link(mundo, PROCESSO_DOMUS)
        assert erro.value.status_code == 400
        assert "não tem e-mail configurado" in erro.value.detail


def _caixa_geral_da_rede(email="geral@domus.pt"):
    return es.EmailAccount(
        name="caixa_geral_da_rede", imap_server="imap.domus.pt", imap_port=993,
        smtp_server="smtp.domus.pt", smtp_port=465, email=email, password="pw",
    )


@pytest.mark.asyncio
class TestBlocoAResisteAoResto:
    async def test_um_campo_invalido_noutra_seccao_nao_apaga_o_email_do_sistema(self, mundo):
        """`get_system_config` valida o documento INTEIRO e, se falha, devolve a config
        do ambiente SEM o Bloco A. Um campo qualquer de outra secção não pode deixar a
        empresa «sem e-mail»."""
        doc = _bloco_a()
        doc["dsti_analysis"] = "isto não é um bloco de DSTI"   # o documento deixa de validar
        mundo.system_config.docs.append(doc)

        with _contexto_de_producao(mundo):
            via_modelo = await es._resolve_system_smtp_account()
            conta = await pec._conta_de_sistema_generica(REDE_DOMUS)
        assert via_modelo is None, "premissa: o caminho pelo modelo perde o Bloco A"
        assert conta is not None and conta.email == "no-reply@sistema.pt"

    async def test_o_magic_link_envia_mesmo_assim(self, mundo):
        doc = _bloco_a()
        doc["dsti_analysis"] = "lixo"
        mundo.system_config.docs.append(doc)
        resposta, transporte = await _enviar_link(mundo, PROCESSO_DOMUS)
        assert resposta["success"] is True
        transporte.assert_called_once()

    async def test_contraprova_bloco_a_vazio_continua_sem_conta(self, mundo):
        mundo.system_config.docs.append({"_id": "main", "company_id": "default", "system_smtp": {}})
        with _contexto_de_producao(mundo):
            assert await pec._conta_de_sistema_generica(REDE_DOMUS) is None

    async def test_leitura_em_bruto_nunca_levanta(self, mundo):
        mundo.system_config.docs.append({"_id": "main", "system_smtp": {"smtp_port": "SSL", "smtp_host": "h",
                                                                        "smtp_username": "u"}})
        with _contexto_de_producao(mundo):
            assert await pec._conta_do_bloco_a_em_bruto() is None


@pytest.mark.asyncio
class TestEmailDoSistemaGravadoNaEmpresaSistema:
    """«…cartão Email do Sistema (Transacional) (ou da empresa Sistema)» (QA, Out 2026).

    Um Master que escolhe trabalhar como «Sistema» no seletor de contexto edita o documento
    `company:<id>` dessa empresa, não o global. Se o cartão ficou lá, as redes satélite não o
    achavam (só o `main` era lido) e o envio falhava com «a empresa não tem e-mail».
    """

    def _empresa_sistema(self, db, nome="Sistema"):
        db.companies.docs.append({"id": "cmp-sistema", "name": nome, "network_id": "rede-sistema",
                                  "is_active": True})

    def _bloco_da_empresa(self):
        return {"_id": "company:cmp-sistema", "company_id": "cmp-sistema",
                "system_smtp": {"resend_api_key": "re_DA_EMPRESA_SISTEMA",
                                "smtp_from_email": "no-reply@sistema.pt"}}

    async def test_sem_bloco_no_global_usa_o_da_empresa_sistema(self, mundo):
        self._empresa_sistema(mundo)
        mundo.system_config.docs.append(self._bloco_da_empresa())
        with _contexto_de_producao(mundo):
            conta = await pec._conta_do_bloco_a_em_bruto()
        assert conta is not None and conta.password == "re_DA_EMPRESA_SISTEMA"

    async def test_uma_rede_satelite_envia_o_link_por_ele(self, mundo):
        self._empresa_sistema(mundo)
        mundo.system_config.docs.append(self._bloco_da_empresa())
        resposta, transporte = await _enviar_link(mundo, PROCESSO_DOMUS)
        assert resposta["success"] is True
        transporte.assert_called_once()

    async def test_o_global_vence_quando_os_dois_existem(self, mundo):
        self._empresa_sistema(mundo)
        mundo.system_config.docs.extend([_bloco_a(), self._bloco_da_empresa()])
        with _contexto_de_producao(mundo):
            conta = await pec._conta_do_bloco_a_em_bruto()
        assert conta.password == "re_CHAVE_DO_SISTEMA"

    async def test_o_global_vazio_nao_esconde_o_da_empresa_sistema(self, mundo):
        self._empresa_sistema(mundo)
        mundo.system_config.docs.extend([
            {"_id": "main", "company_id": "default", "system_smtp": {}}, self._bloco_da_empresa(),
        ])
        with _contexto_de_producao(mundo):
            assert (await pec._conta_do_bloco_a_em_bruto()).password == "re_DA_EMPRESA_SISTEMA"

    async def test_o_nome_casa_sem_distinguir_maiusculas(self, mundo):
        self._empresa_sistema(mundo, nome="SISTEMA")
        mundo.system_config.docs.append(self._bloco_da_empresa())
        with _contexto_de_producao(mundo):
            assert await pec._conta_do_bloco_a_em_bruto() is not None

    async def test_uma_empresa_com_nome_parecido_NAO_serve(self, mundo):
        # «Sistema Antigo» não é a empresa do sistema: exacto, nunca por prefixo.
        self._empresa_sistema(mundo, nome="Sistema Antigo")
        mundo.system_config.docs.append(self._bloco_da_empresa())
        with _contexto_de_producao(mundo):
            assert await pec._conta_do_bloco_a_em_bruto() is None

    async def test_sem_empresa_sistema_nem_global_continua_sem_conta(self, mundo):
        with _contexto_de_producao(mundo):
            assert await pec._conta_do_bloco_a_em_bruto() is None

    async def test_a_empresa_sistema_com_bloco_ilegivel_nao_levanta(self, mundo):
        self._empresa_sistema(mundo)
        mundo.system_config.docs.append({"_id": "company:cmp-sistema",
                                         "system_smtp": {"smtp_host": "h", "smtp_username": "u", "smtp_port": "SSL"}})
        with _contexto_de_producao(mundo):
            assert await pec._conta_do_bloco_a_em_bruto() is None


@pytest.mark.asyncio
class TestCaixaDaRedeAvariadaRecuaParaOEmailDoSistema:
    async def _enviar(self, db, resultado_da_caixa, *, com_bloco_a=True):
        if com_bloco_a:
            db.system_config.docs.append(_bloco_a())
        contexto = pec.ContextoDoEmailDoPortal(
            company_id="cmp-domus", company_name="Domus", network_id=REDE_DOMUS,
            account=_caixa_geral_da_rede(), account_source=pec.ORIGEM_CAIXA_DA_EMPRESA,
        )
        chamadas = []

        async def send_email(**k):
            chamadas.append(k["account_name"])
            if k["account_name"] == "caixa_geral_da_rede":
                if isinstance(resultado_da_caixa, Exception):
                    raise resultado_da_caixa
                return resultado_da_caixa
            return {"success": True, "account": "system_smtp"}

        with _contexto_de_producao(db), patch.object(es, "send_email", send_email):
            r = await pec.enviar_email_do_portal(contexto, to_emails=["a@x.pt"], subject="s", body="b")
        return r, chamadas

    @pytest.mark.parametrize("codigo", ["smtp_auth", "smtp_password_unreadable", "SMTP_NOT_CONFIGURED"])
    async def test_falha_de_configuracao_da_caixa_recua_para_o_email_do_sistema(self, mundo, codigo):
        r, chamadas = await self._enviar(mundo, {"success": False, "error": "x", "error_code": codigo})
        assert r["success"] is True
        assert chamadas == ["caixa_geral_da_rede", "sistema"]

    async def test_value_error_da_caixa_tambem_recua(self, mundo):
        r, chamadas = await self._enviar(mundo, ValueError("purpose inválido"))
        assert r["success"] is True and chamadas == ["caixa_geral_da_rede", "sistema"]

    async def test_falha_generica_NAO_recua_porque_pode_ja_ter_sido_entregue(self, mundo):
        """Um email duplicado ao cliente é pior do que um aviso de falha."""
        r, chamadas = await self._enviar(mundo, {"success": False, "error": "Não foi possível enviar"})
        assert r["success"] is False
        assert chamadas == ["caixa_geral_da_rede"]

    async def test_se_a_caixa_funciona_nao_ha_segundo_envio(self, mundo):
        r, chamadas = await self._enviar(mundo, {"success": True})
        assert r["success"] is True and chamadas == ["caixa_geral_da_rede"]

    async def test_sem_email_do_sistema_devolve_o_erro_da_caixa(self, mundo):
        r, chamadas = await self._enviar(
            mundo, {"success": False, "error": "535", "error_code": "smtp_auth"}, com_bloco_a=False,
        )
        assert r["success"] is False and r["error_code"] == "smtp_auth"
        assert chamadas == ["caixa_geral_da_rede"]


@pytest.mark.asyncio
class TestBoasVindasDoPortalPeloEmailDoSistema:
    async def test_cliente_de_rede_satelite_recebe_as_boas_vindas_sem_retry(self, mundo):
        mundo.system_config.docs.append(_bloco_a())
        transporte = MagicMock(return_value={"id": "e1"})
        fila = MagicMock()
        with _contexto_de_producao(mundo), \
             patch.object(es, "_send_via_resend", transporte), \
             patch("services.task_queue.task_queue", fila):
            enviado = await cpe.deliver_registration_email(
                client_email="ana@x.pt", client_name="Ana", portal_access_code="ABC123",
                client_id="c1", company_id="cmp-domus",
            )
        assert enviado is True
        transporte.assert_called_once()
        fila.send_registration_email.assert_not_called()
