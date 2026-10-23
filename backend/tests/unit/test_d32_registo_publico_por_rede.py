"""
D-32 — o registo público procurava e actualizava clientes em TODAS as redes.

O ATAQUE (a que os testes de `TestAExploracao` dão corpo)
  `POST /public/client-registration` é anónimo e escreve. Procurava o email
  «em toda a base de dados»: quem se registasse pelo link da Domus com o
  email de um cliente da Power encontrava esse cliente, **actualizava-o**
  (telefone, campos, dados pessoais, 2.º titular), **re-marcava-o como lead
  novo** e recebia o `client_id` — e a resposta distinguia «já existia» de
  «novo» (`is_new_client`). Além disso, o aviso à gestão (push + email com
  nome, email e telefone do cliente) ia para a gestão de TODAS as redes: o
  «primeiro admin/CEO/diretor da base de dados».

O QUE SE GARANTE
  1. A procura de duplicados vive na rede do link: nunca toca num cliente de
     outra rede, e a pilha por carimbar só conta para a rede de omissão.
  2. A mesma pessoa em duas redes é DOIS clientes, cada um na sua.
  3. O aviso (push, email e notificação) vai só à gestão da rede do link.
  4. A resposta não revela se o email já existia.
"""
from __future__ import annotations

import ast
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

UCRS_DA_GESTAO = [
    {"user_id": "g-power", "company_id": "cmp-power", "role": "admin", "is_default": True},
    {"user_id": "g-precision", "company_id": "cmp-precision", "role": "diretor", "is_default": True},
    {"user_id": "g-domus", "company_id": "cmp-domus", "role": "ceo", "is_default": True},
    # Cargos que NÃO recebem o aviso, na rede da Domus.
    {"user_id": "c-domus-consultor", "company_id": "cmp-domus", "role": "consultor", "is_default": True},
]
UTILIZADORES = [
    {"id": "g-power", "email": "admin@power.pt", "name": "Admin Power", "role": "admin", "is_active": True},
    {"id": "g-precision", "email": "dir@precision.pt", "name": "Dir Precision", "role": "diretor", "is_active": True},
    {"id": "g-domus", "email": "ceo@domus.pt", "name": "CEO Domus", "role": "ceo", "is_active": True},
    {"id": "c-domus-consultor", "email": "cons@domus.pt", "name": "Consultor Domus", "role": "consultor", "is_active": True},
    {"id": "m-1", "email": "master@x.pt", "name": "Master", "role": "master", "is_active": True},
]


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.alert_audience as audiencia
    import services.alerts as alertas
    import services.client_uniqueness as cu
    import services.form_config_scope as fcs
    import services.public_registration as pr

    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend(dict(u) for u in UCRS_DA_GESTAO)
    fake_async_db.users.docs.extend(dict(u) for u in UTILIZADORES)

    push = AsyncMock(return_value=True)
    email_ao_staff = AsyncMock(return_value=True)
    email_de_alerta = AsyncMock(return_value=True)
    s3 = MagicMock()
    s3.initialize_client_folders = MagicMock(return_value=(True, "Documentação Clientes/x"))

    tarefas = []

    def _fechar(coro, name="", **_k):
        # Só corre o aviso ao staff (é o que se observa); o resto não interessa.
        import asyncio

        if str(name).startswith("staff-new-client-email"):
            tarefas.append(asyncio.get_event_loop().create_task(coro))
        else:
            coro.close()

    with tenant_db(fake_async_db, pr, alertas, audiencia, fcs, cu), \
            patch.object(pr, "s3_service", s3), \
            patch.object(pr, "spawn_background_task", _fechar), \
            patch.object(pr, "send_new_client_notification", email_ao_staff), \
            patch.object(alertas, "send_notification_with_preference_check", email_de_alerta), \
            patch("services.push_notifications.send_push_notification", push), \
            patch("services.portal_documents_notify.generate_mandatory_document_requests", AsyncMock()), \
            patch("asyncio.create_task", lambda c, **k: c.close()):
        yield MagicMock(
            pr=pr, bd=fake_async_db, push=push, email_ao_staff=email_ao_staff,
            email_de_alerta=email_de_alerta, tarefas=tarefas,
        )


def _pedido():
    return MagicMock(headers={}, state=MagicMock(spec=[]))


def _dados(**extra):
    from models.process import PublicClientRegistration

    base = dict(name="Maria Teste", email="maria@teste.pt", phone="912345678", process_type="credito_habitacao")
    base.update(extra)
    return PublicClientRegistration(**base)


def _publicos(bd):
    return [c for c in bd.clients.docs if c.get("fonte") == "public_form"]


def _cliente_da_rede(bd, rede, email="maria@teste.pt", **extra):
    doc = {
        "id": f"c-existente-{rede}", "nome": "Maria Original", "fonte": "public_form",
        "contacto": {"email": email, "telefone": "900000000"},
        "dados_pessoais": {"nome": "Maria Original"},
        "lead_status": "converted", "custom_fields": {"original": "sim"},
        **extra,
    }
    if rede:
        doc["network_id"] = rede
        doc["company_id"] = "cmp-domus" if rede == REDE_DOMUS else "cmp-power"
    bd.clients.docs.append(doc)
    return doc


async def _esperar_fundo(mundo):
    import asyncio

    await asyncio.gather(*mundo.tarefas)


# ====================================================================
# 1. O ATAQUE — a procura nunca atravessa redes
# ====================================================================

class TestAExploracao:
    """D-32 → D-42: o link da Domus não encontra NEM TOCA no cliente da Power.

    O que mudou no D-42: a mesma pessoa em duas redes já não são «dois clientes» — a identidade
    é global, logo o registo anónimo da Domus com o email da Power é recusado (409 genérico) em
    vez de criar um segundo cliente. O que NÃO mudou: o cliente da Power fica intacto e a resposta
    não diz quem é.
    """

    @pytest.mark.asyncio
    async def test_o_link_da_domus_nao_encontra_nem_toca_no_cliente_da_power(self, mundo):
        original = _cliente_da_rede(mundo.bd, REDE_INCUMBENTE)
        antes = {k: (dict(v) if isinstance(v, dict) else v) for k, v in original.items()}

        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus", phone="999888777"))

        assert r.status_code == 409, "INVERTIDO (era 200): a identidade é global"
        vitima = next(c for c in mundo.bd.clients.docs if c["id"] == original["id"])
        assert {k: vitima[k] for k in antes} == antes, "o cliente da Power ficou intacto"
        assert vitima["lead_status"] == "converted", "não foi re-marcado como lead novo"
        assert vitima["network_id"] == REDE_INCUMBENTE
        assert [c for c in _publicos(mundo.bd) if c["id"] != original["id"]] == [], "e não nasceu um segundo"

    @pytest.mark.asyncio
    async def test_a_resposta_nao_devolve_o_id_do_cliente_de_outra_rede(self, mundo):
        import json

        original = _cliente_da_rede(mundo.bd, REDE_INCUMBENTE)
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        corpo = json.loads(r.body)
        assert original["id"] not in r.body.decode()
        assert "client_id" not in corpo and corpo["code"] == "DUPLICATE_CLIENT"

    @pytest.mark.asyncio
    async def test_a_mesma_pessoa_em_duas_redes_e_um_so_cliente(self, mundo):
        """INVERTIDO (eram dois clientes no D-32): o segundo registo, em qualquer rede, é 409."""
        primeiro = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        segundo = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert primeiro.status_code == 200
        assert segundo.status_code == 409
        assert len(_publicos(mundo.bd)) == 1

    @pytest.mark.asyncio
    async def test_a_pilha_por_carimbar_tambem_conta(self, mundo):
        """INVERTIDO (a Domus «criava o seu» no D-32): com identidade global não há ilha que escape."""
        legado = _cliente_da_rede(mundo.bd, None)
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        assert r.status_code == 409
        intacto = next(c for c in mundo.bd.clients.docs if c["id"] == legado["id"])
        assert "network_id" not in intacto and "company_id" not in intacto
        assert intacto["lead_status"] == "converted"
        assert len(_publicos(mundo.bd)) == 1

    @pytest.mark.asyncio
    async def test_a_resposta_nao_tem_o_oraculo_is_new_client(self, mundo):
        import json

        novo = json.loads((await mundo.pr.run_public_client_registration(
            _pedido(), _dados(empresa_id="cmp-domus", email="outra@teste.pt"))).body)
        assert "is_new_client" not in novo


# ====================================================================
# 3. OS AVISOS — só a gestão DA REDE
# ====================================================================

class TestOAvisoVaiSoAGestaoDaRede:
    @pytest.mark.asyncio
    async def test_um_registo_da_domus_avisa_so_a_gestao_da_domus(self, mundo):
        await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        await _esperar_fundo(mundo)

        avisados = {c.kwargs["user_id"] for c in mundo.push.await_args_list}
        assert avisados == {"g-domus"}, "nem a Power, nem a Precision, nem o consultor da Domus"
        assert "c-domus-consultor" not in avisados

        notificados = {n["user_id"] for n in mundo.bd.notifications.docs}
        assert notificados == {"g-domus"}

        destinos = {c.kwargs.get("staff_email") for c in mundo.email_ao_staff.await_args_list}
        assert destinos == {"ceo@domus.pt"}

    @pytest.mark.asyncio
    async def test_um_registo_da_power_avisa_a_gestao_do_grupo_e_nunca_a_domus(self, mundo):
        await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        await _esperar_fundo(mundo)

        avisados = {c.kwargs["user_id"] for c in mundo.push.await_args_list}
        assert avisados == {"g-power", "g-precision"}
        assert "g-domus" not in {n["user_id"] for n in mundo.bd.notifications.docs}
        # O email ao staff tem UM destinatário, da rede certa.
        destinos = {c.kwargs.get("staff_email") for c in mundo.email_ao_staff.await_args_list}
        assert len(destinos) == 1 and destinos <= {"admin@power.pt", "dir@precision.pt"}

    @pytest.mark.asyncio
    async def test_o_nome_do_cliente_nunca_chega_a_um_email_de_outra_rede(self, mundo):
        await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        await _esperar_fundo(mundo)
        for chamada in [*mundo.email_ao_staff.await_args_list, *mundo.email_de_alerta.await_args_list]:
            destino = chamada.kwargs.get("staff_email") or chamada.args[0]
            assert destino.endswith("@domus.pt"), destino

    @pytest.mark.asyncio
    async def test_rede_sem_gestao_nao_avisa_ninguem_em_vez_de_avisar_toda_a_gente(self, mundo):
        mundo.bd.user_company_roles.docs[:] = [
            u for u in mundo.bd.user_company_roles.docs if u["company_id"] != "cmp-domus"
        ]
        await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        await _esperar_fundo(mundo)
        mundo.push.assert_not_awaited()
        mundo.email_ao_staff.assert_not_awaited()
        assert mundo.bd.notifications.docs == []

    @pytest.mark.asyncio
    async def test_o_master_nao_e_o_destinatario_por_omissao(self, mundo):
        await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        await _esperar_fundo(mundo)
        assert "m-1" not in {c.kwargs["user_id"] for c in mundo.push.await_args_list}


# ====================================================================
# 4. GUARDAS SOBRE O CÓDIGO
# ====================================================================

class TestGuardasDeFonte:
    def _funcao(self):
        import services.public_registration as pr

        arvore = ast.parse(inspect.getsource(pr))
        return arvore, next(
            n for n in ast.walk(arvore)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_public_client_registration"
        )

    def test_o_registo_publico_nao_procura_clientes_por_conta_propria(self):
        """Só `encontrar_cliente_duplicado` (com rede) procura um cliente por email/NIF/telemóvel."""
        arvore, _ = self._funcao()
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "find_one"):
                continue
            if ast.unparse(no.func.value) != "db.clients":
                continue
            texto = ast.unparse(no)
            assert not any(c in texto for c in ("email_hash", "contacto.email", "nif_hash", "dados_pessoais.nif", "telefone")), texto

    def test_contraprova_a_procura_e_global_e_unica(self):
        """D-42: a procura já não diz a rede do link (a identidade é global), e é UMA só."""
        _, funcao = self._funcao()
        chamadas = [
            n for n in ast.walk(funcao)
            if isinstance(n, ast.Call) and ast.unparse(n.func) == "encontrar_cliente_duplicado"
        ]
        assert len(chamadas) == 1
        assert "rede" not in {k.arg for k in chamadas[0].keywords}

    def test_o_registo_nao_consulta_a_gestao_de_toda_a_base_de_dados(self):
        import services.public_registration as pr

        codigo = inspect.getsource(pr)
        assert "deep_role_in_filter" not in codigo
        assert "gestao_da_rede_do_processo" in codigo

    def test_a_resposta_nao_tem_oraculo(self):
        import services.public_registration as pr

        assert "is_new_client" not in inspect.getsource(pr).split("return JSONResponse(")[-1]

    def test_o_ramo_de_actualizacao_silenciosa_foi_apagado(self):
        """Apagado, não desligado: um `update_one` sobre um cliente existente não pode voltar."""
        import services.public_registration as pr

        fonte = inspect.getsource(pr.run_public_client_registration)
        assert "existing_client" not in fonte
        assert 'update_one({"id": client_id}, {"$set": client_updates})' not in fonte
