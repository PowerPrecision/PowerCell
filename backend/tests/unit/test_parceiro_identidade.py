"""
PORTAL DO PARCEIRO — O PLANO DE IDENTIDADE (V1)

O que se prova aqui, por ordem de gravidade:

  1. as FAMÍLIAS DE TOKENS não se cruzam — cada produtor REAL contra cada
     dependência REAL (nunca um token forjado: foi o forjar que escondeu o
     defeito dos três produtores de token do CRM);
  2. o estado relê-se em cada pedido (suspender, mudar a palavra-passe e
     perder a rede matam a sessão na hora);
  3. o login não é um oráculo e o travão por identidade morde;
  4. o convite é de uso único, expira, e só o Admin/CEO DA REDE convida;
  5. um parceiro de outra rede é «não existe» (404 igual), nunca «não é teu».
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from tests.unit.helpers_tenant import (  # noqa: F401
    rede_de_omissao_incumbente,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    semear,
    tenant_db,
)

ADMIN_POWER = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "admin", "effective_role": "admin"}
ADMIN_DOMUS = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "admin", "effective_role": "admin"}
MASTER = {"id": "u-master", "name": "Master", "email": "m@x.pt", "role": "master", "effective_role": "master"}

PASSWORD = "Parceiro#2026x"


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente, monkeypatch):
    """Duas redes + utilizadores; sem FRONTEND_URL (nenhum email sai)."""
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("JWT_PARTNER_SECRET", raising=False)
    semear(fake_async_db)
    return fake_async_db


@pytest.fixture
def com_bd(mundo):
    import services.admin_users_scope as scope_mod
    import services.audit_trail_service as audit
    import services.partner_accounts as acc
    import services.partner_security as sec
    import services.user_management_scope as ums

    with tenant_db(mundo, scope_mod, ums, acc, sec), patch.object(audit, "db", mundo):
        yield mundo


async def _convidar(acc, actor, **extra):
    corpo = {
        "name": "Rui Parceiro",
        "email": "rui@parceiros.pt",
        "company_id": "cmp-power",
        **extra,
    }
    return await acc.run_invite_partner(acc.PartnerInvite(**corpo), actor)


async def _activar(acc, convite, password=PASSWORD):
    return await acc.run_accept_invite(
        acc.PartnerAcceptInvite(token=convite["invite_token"], password=password, accept_terms=True),
        ip="10.0.0.1",
    )


# ════════════════════════════════════════════════════════════════════
#  O SEGREDO
# ════════════════════════════════════════════════════════════════════
class TestOSegredo:
    def test_em_producao_sem_variavel_o_portal_desliga_se_e_nunca_assina_com_um_literal(self):
        from services.partner_security import resolver_segredo

        assert resolver_segredo(em_producao=True, valor=None, jwt_secret="x" * 40) is None

    def test_uma_variavel_curta_vale_menos_do_que_nenhuma(self):
        from services.partner_security import resolver_segredo

        assert resolver_segredo(em_producao=True, valor="curto", jwt_secret="x" * 40) is None
        assert resolver_segredo(em_producao=False, valor="curto", jwt_secret="x" * 40) is None

    def test_uma_variavel_valida_e_usada_tal_e_qual(self):
        from services.partner_security import resolver_segredo

        valor = "s" * 48
        assert resolver_segredo(em_producao=True, valor=valor, jwt_secret="x" * 40) == valor

    def test_em_dev_deriva_um_segredo_estavel_e_DIFERENTE_do_jwt_secret(self):
        from services.partner_security import resolver_segredo

        jwt_secret = "j" * 40
        a = resolver_segredo(em_producao=False, valor=None, jwt_secret=jwt_secret)
        b = resolver_segredo(em_producao=False, valor=None, jwt_secret=jwt_secret)
        assert a and a == b, "estável entre workers"
        assert a != jwt_secret, "as famílias não se cruzam nem em dev"

    @pytest.mark.asyncio
    async def test_em_producao_sem_variavel_nenhuma_operacao_emite_ou_aceita_sessoes(self, monkeypatch, mundo):
        import services.partner_accounts as acc
        import services.partner_security as sec

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("JWT_PARTNER_SECRET", raising=False)
        with pytest.raises(sec.PortalDoParceiroDesligado) as erro:
            sec.create_partner_token({"id": "p1"})
        assert erro.value.status_code == 503
        assert sec.portal_do_parceiro_ligado() is False
        # O login recusa ANTES de gastar uma tentativa na credencial.
        with patch.object(acc, "db", mundo):
            with pytest.raises(sec.PortalDoParceiroDesligado):
                await acc.run_partner_login(acc.PartnerLogin(email="a@b.pt", password="x"))
        assert mundo.portal_login_attempts.docs == []


# ════════════════════════════════════════════════════════════════════
#  AS FAMÍLIAS DE TOKENS NÃO SE CRUZAM
# ════════════════════════════════════════════════════════════════════
class TestMatrizDeTokens:
    """Cada produtor REAL contra cada dependência REAL."""

    @staticmethod
    def _produtores_do_staff() -> dict:
        from services.auth import create_access_token, create_token
        from services.refresh_token_service import create_access_token as do_login

        return {
            "login-v2/refresh": do_login("user-1", "a@b.pt", "admin"),
            "register": create_token("user-1", "a@b.pt", "consultor"),
            "impersonate": create_access_token({"sub": "user-1", "email": "a@b.pt", "role": "admin"}),
        }

    @staticmethod
    def _produtores_do_portal() -> dict:
        from services.portal_security import (
            create_access_code_session_token,
            create_client_magic_token,
            create_verified_session_token,
        )

        return {
            "magic_link": create_client_magic_token("proc-1"),
            "verified_session": create_verified_session_token("proc-1", "cli-1"),
            "access_code_session": create_access_code_session_token("proc-1", "cli-1"),
        }

    @pytest.mark.asyncio
    async def test_um_token_de_parceiro_e_recusado_pelo_staff_e_pelo_portal_do_cliente(self, com_bd):
        from services.auth import get_current_user
        from services.partner_security import create_partner_token
        from services.portal_security import get_current_client

        token = create_partner_token({"id": "p1", "token_epoch": 0})
        with pytest.raises(HTTPException) as staff:
            await get_current_user(MagicMock(), _creds(token))
        assert staff.value.status_code == 401
        with pytest.raises(HTTPException) as portal:
            await get_current_client(_creds(token))
        assert portal.value.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("origem", ["login-v2/refresh", "register", "impersonate"])
    async def test_cada_produtor_do_staff_e_recusado_pelo_portal_do_parceiro(self, com_bd, origem):
        from services.partner_security import get_current_partner

        with pytest.raises(HTTPException) as erro:
            await get_current_partner(_creds(self._produtores_do_staff()[origem]))
        assert erro.value.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("origem", ["magic_link", "verified_session", "access_code_session"])
    async def test_cada_produtor_do_portal_do_cliente_e_recusado_pelo_portal_do_parceiro(self, com_bd, origem):
        from services.partner_security import get_current_partner

        with pytest.raises(HTTPException) as erro:
            await get_current_partner(_creds(self._produtores_do_portal()[origem]))
        assert erro.value.status_code == 401

    def test_o_validador_de_staff_nao_aceita_o_tipo_do_parceiro(self):
        from services.partner_security import TIPO_DO_PARCEIRO
        from services.ws_client_identity import tipo_de_token_e_de_staff

        assert tipo_de_token_e_de_staff(TIPO_DO_PARCEIRO) is False

    @pytest.mark.asyncio
    async def test_com_o_segredo_certo_a_audiencia_e_o_tipo_continuam_a_ser_exigidos(self, com_bd):
        """Existe um parceiro ACTIVO com este id: a única coisa entre cada
        token abaixo e a sessão são as claims. (Com um `sub` que não existe, o
        teste passava pela razão errada — «não encontrado» — e uma mutação que
        apagasse a verificação da audiência ou do tipo sobrevivia.)"""
        from services.partner_security import _segredo, get_current_partner

        com_bd.partners.docs.append({
            "id": "p1", "name": "P", "email": "p@x.pt", "status": "active", "token_epoch": 0,
            "redes": [{"network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "status": "active"}],
        })
        agora = datetime.now(timezone.utc)

        def token(**claims):
            base = {"sub": "p1", "tv": 0, "type": "partner", "aud": "powercell-partner",
                    "exp": agora + timedelta(hours=1)}
            base.update(claims)
            return jwt.encode({k: v for k, v in base.items() if v is not None}, _segredo(), algorithm="HS256")

        # contraprova: o token inteiramente certo ENTRA
        assert (await get_current_partner(_creds(token())))["id"] == "p1"

        for variante in (
            {"aud": None},            # sem audiência
            {"aud": "outro-sitio"},   # audiência errada
            {"type": "access"},       # tipo do staff
            {"type": None},           # sem tipo
            {"type": "magic_link"},   # tipo do Portal do Cliente
        ):
            with pytest.raises(HTTPException) as erro:
                await get_current_partner(_creds(token(**variante)))
            assert erro.value.status_code == 401, variante


class TestChaveDoLimiter:
    """O limite do parceiro conta por IDENTIDADE: o IP sai do
    `X-Forwarded-For`, que o cliente falsifica (D-4)."""

    @staticmethod
    def _pedido(token=None, xff="1.2.3.4"):
        cabecalhos = {"X-Forwarded-For": xff}
        if token:
            cabecalhos["Authorization"] = f"Bearer {token}"
        return SimpleNamespace(headers=cabecalhos, client=SimpleNamespace(host="9.9.9.9"))

    def test_um_token_de_parceiro_conta_por_parceiro(self):
        from middleware.rate_limit import _get_rate_limit_key
        from services.partner_security import create_partner_token

        token = create_partner_token({"id": "p-77", "token_epoch": 0})
        assert _get_rate_limit_key(self._pedido(token)) == "partner:p-77"
        # variar o IP falsificado NÃO muda a chave: não há como fugir ao limite
        assert _get_rate_limit_key(self._pedido(token, xff="8.8.8.8")) == "partner:p-77"

    def test_staff_continua_a_contar_por_utilizador_e_o_anonimo_por_ip(self):
        from middleware.rate_limit import _get_rate_limit_key
        from services.refresh_token_service import create_access_token

        assert _get_rate_limit_key(self._pedido(create_access_token("u-1", "a@b.pt", "admin"))) == "user:u-1"
        assert _get_rate_limit_key(self._pedido()) == "ip:1.2.3.4"
        assert _get_rate_limit_key(self._pedido("lixo")) == "ip:1.2.3.4"

    def test_a_funcao_pura_nao_levanta_nunca(self):
        from services.partner_security import chave_de_limite_do_parceiro

        for lixo in ("", "x", "a.b.c", None):
            assert chave_de_limite_do_parceiro(lixo) is None


# ════════════════════════════════════════════════════════════════════
#  O ESTADO RELÊ-SE EM CADA PEDIDO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestSessaoRelidaEmCadaPedido:
    async def _sessao(self, acc, actor=ADMIN_POWER):
        convite = await _convidar(acc, actor)
        return convite, await _activar(acc, convite)

    async def test_uma_sessao_valida_devolve_o_parceiro_sem_o_hash_nem_o_convite(self, com_bd):
        import services.partner_accounts as acc
        from services.partner_security import get_current_partner

        _, sessao = await self._sessao(acc)
        partner = await get_current_partner(_creds(sessao["access_token"]))
        assert partner["email"] == "rui@parceiros.pt"
        assert "password_hash" not in partner and "invite" not in partner

    async def test_suspender_mata_a_sessao_na_hora(self, com_bd):
        import services.partner_accounts as acc
        from services.partner_security import get_current_partner

        _, sessao = await self._sessao(acc)
        pid = sessao["partner"]["id"]
        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        with pytest.raises(HTTPException) as erro:
            await get_current_partner(_creds(sessao["access_token"]))
        assert erro.value.status_code == 401

    async def test_reactivar_nao_ressuscita_a_sessao_antiga(self, com_bd):
        """A suspensão sobe a geração: o token de antes continua morto."""
        import services.partner_accounts as acc
        from services.partner_security import get_current_partner

        _, sessao = await self._sessao(acc)
        pid = sessao["partner"]["id"]
        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=False), ADMIN_POWER)
        with pytest.raises(HTTPException):
            await get_current_partner(_creds(sessao["access_token"]))

    async def test_mudar_a_palavra_passe_invalida_as_outras_sessoes_e_devolve_uma_nova(self, com_bd):
        import services.partner_accounts as acc
        from services.partner_security import get_current_partner

        _, sessao = await self._sessao(acc)
        partner = await get_current_partner(_creds(sessao["access_token"]))
        nova = await acc.run_change_password(
            partner, acc.PartnerChangePassword(current_password=PASSWORD, new_password="Outra#Pass2027")
        )
        with pytest.raises(HTTPException):
            await get_current_partner(_creds(sessao["access_token"]))
        assert (await get_current_partner(_creds(nova["access_token"])))["id"] == partner["id"]

    async def test_a_palavra_passe_actual_errada_nao_muda_nada_e_conta_como_tentativa(self, com_bd):
        import services.partner_accounts as acc
        from services.partner_security import get_current_partner

        _, sessao = await self._sessao(acc)
        partner = await get_current_partner(_creds(sessao["access_token"]))
        with pytest.raises(HTTPException) as erro:
            await acc.run_change_password(
                partner, acc.PartnerChangePassword(current_password="Errada#123x", new_password="Outra#Pass2027")
            )
        assert erro.value.status_code == 400
        assert com_bd.portal_login_attempts.docs, "a tentativa falhada contou"
        assert (await get_current_partner(_creds(sessao["access_token"])))["id"] == partner["id"]

    async def test_recusas_de_estado_sao_todas_o_mesmo_401(self, com_bd):
        """«Não existe», «suspenso» e «sem rede activa» não se distinguem
        para quem apresenta um token (seria um directório de contas)."""
        import services.partner_accounts as acc
        import services.partner_security as sec

        _, sessao = await self._sessao(acc)
        pid = sessao["partner"]["id"]
        token = sessao["access_token"]
        base = copy.deepcopy(com_bd.partners.docs[0])

        detalhes = set()
        # suspenso
        com_bd.partners.docs[0]["redes"][0]["status"] = "suspended"
        with pytest.raises(HTTPException) as a:
            await sec.get_current_partner(_creds(token))
        detalhes.add(a.value.detail)
        # inexistente
        com_bd.partners.docs.clear()
        with pytest.raises(HTTPException) as b:
            await sec.get_current_partner(_creds(token))
        detalhes.add(b.value.detail)
        # conta convidada (não activa)
        com_bd.partners.docs.append({**base, "status": "invited"})
        with pytest.raises(HTTPException) as c:
            await sec.get_current_partner(_creds(token))
        detalhes.add(c.value.detail)

        assert {a.value.status_code, b.value.status_code, c.value.status_code} == {401}
        assert len(detalhes) == 1, f"as recusas distinguem-se: {detalhes}"
        assert pid


# ════════════════════════════════════════════════════════════════════
#  O LOGIN
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestLogin:
    async def _parceiro_activo(self, acc):
        convite = await _convidar(acc, ADMIN_POWER)
        await _activar(acc, convite)

    async def test_login_certo_devolve_sessao_e_o_perfil_publico(self, com_bd):
        import services.partner_accounts as acc

        await self._parceiro_activo(acc)
        sessao = await acc.run_partner_login(acc.PartnerLogin(email=" RUI@Parceiros.PT ", password=PASSWORD))
        assert sessao["token_type"] == "bearer" and sessao["access_token"]
        blob = repr(sessao)
        assert "password_hash" not in blob and "token_hash" not in blob and "$2b$" not in blob
        assert com_bd.partners.docs[0]["last_login_at"]

    async def test_nao_existe_sem_password_e_password_errada_sao_a_mesma_resposta(self, com_bd):
        import services.partner_accounts as acc

        await _convidar(acc, ADMIN_POWER)  # convidado, ainda sem password
        respostas = set()
        for email, pw in (
            ("rui@parceiros.pt", "Qualquer#Coisa1"),   # existe, sem password
            ("ninguem@parceiros.pt", "Qualquer#Coisa1"),  # não existe
        ):
            with pytest.raises(HTTPException) as erro:
                await acc.run_partner_login(acc.PartnerLogin(email=email, password=pw))
            respostas.add((erro.value.status_code, erro.value.detail))
        await _activar_pelo_convite_pendente(acc, com_bd)
        with pytest.raises(HTTPException) as erro:
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password="Errada#Pass1x"))
        respostas.add((erro.value.status_code, erro.value.detail))
        assert respostas == {(401, acc.ERRO_CREDENCIAIS)}

    async def test_o_travao_por_identidade_morde_mesmo_com_a_password_certa(self, com_bd):
        import services.partner_accounts as acc
        from services.portal_brute_force import MAX_TENTATIVAS

        await self._parceiro_activo(acc)
        for _ in range(MAX_TENTATIVAS):
            with pytest.raises(HTTPException):
                await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password="Errada#Pass1x"))
        with pytest.raises(HTTPException) as erro:
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        assert erro.value.status_code == 429, "bloqueado: a password certa também é recusada"

    async def test_a_caixa_das_letras_nao_contorna_o_travao(self, com_bd):
        import services.partner_accounts as acc
        from services.portal_brute_force import MAX_TENTATIVAS

        await self._parceiro_activo(acc)
        variantes = ["rui@parceiros.pt", "RUI@parceiros.pt", "Rui@Parceiros.PT"]
        for i in range(MAX_TENTATIVAS):
            with pytest.raises(HTTPException):
                await acc.run_partner_login(acc.PartnerLogin(email=variantes[i % 3], password="Errada#Pass1x"))
        with pytest.raises(HTTPException) as erro:
            await acc.run_partner_login(acc.PartnerLogin(email="RUI@PARCEIROS.PT", password=PASSWORD))
        assert erro.value.status_code == 429

    async def test_um_login_certo_limpa_o_contador(self, com_bd):
        import services.partner_accounts as acc

        await self._parceiro_activo(acc)
        for _ in range(3):
            with pytest.raises(HTTPException):
                await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password="Errada#Pass1x"))
        assert com_bd.portal_login_attempts.docs
        await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        assert com_bd.portal_login_attempts.docs == []

    async def test_texto_que_nao_e_um_email_nao_cria_chaves_no_registo_de_tentativas(self, com_bd):
        import services.partner_accounts as acc

        for lixo in ("nao-e-email", "<script>", "a" * 90):
            with pytest.raises(HTTPException) as erro:
                await acc.run_partner_login(acc.PartnerLogin(email=lixo, password="x"))
            assert erro.value.status_code == 401
        assert com_bd.portal_login_attempts.docs == []

    async def test_o_estado_so_se_diz_depois_da_password_provada(self, com_bd):
        import services.partner_accounts as acc

        await self._parceiro_activo(acc)
        com_bd.partners.docs[0]["redes"][0]["status"] = "suspended"
        # password ERRADA: nada de «conta suspensa» — é o 401 de sempre.
        with pytest.raises(HTTPException) as errada:
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password="Errada#Pass1x"))
        assert errada.value.status_code == 401
        # password CERTA: agora sim, 403.
        with pytest.raises(HTTPException) as certa:
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        assert certa.value.status_code == 403

    async def test_um_hash_legado_sha256_nao_e_aceite_nesta_familia(self, com_bd):
        import hashlib

        import services.partner_accounts as acc

        await self._parceiro_activo(acc)
        com_bd.partners.docs[0]["password_hash"] = hashlib.sha256(PASSWORD.encode()).hexdigest()
        with pytest.raises(HTTPException) as erro:
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        assert erro.value.status_code == 401


async def _activar_pelo_convite_pendente(acc, bd):
    """Activa o parceiro convidado mais recente (o convite foi devolvido uma
    vez; aqui gera-se um novo através do serviço, como faria o Admin)."""
    novo = await acc.run_resend_invite(bd.partners.docs[0]["id"], ADMIN_POWER)
    await _activar(acc, novo)


# ════════════════════════════════════════════════════════════════════
#  CONVITE → ACTIVAÇÃO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestConvite:
    async def test_o_convite_grava_o_hash_e_nunca_o_token(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        guardado = com_bd.partners.docs[0]
        assert convite["invite_token"] not in repr(guardado)
        assert guardado["invite"]["token_hash"] == acc.hash_de_token(convite["invite_token"])
        assert guardado["status"] == "invited" and "password_hash" not in guardado

    async def test_o_parceiro_nasce_ligado_a_UMA_rede_numa_lista(self, com_bd):
        import services.partner_accounts as acc

        await _convidar(acc, ADMIN_POWER)
        redes = com_bd.partners.docs[0]["redes"]
        assert isinstance(redes, list) and len(redes) == 1
        assert redes[0]["network_id"] == REDE_INCUMBENTE
        assert redes[0]["company_id"] == "cmp-power" and redes[0]["status"] == "active"

    async def test_a_entrada_no_directorio_tem_o_mesmo_id_e_nao_autentica(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        pid = convite["partner"]["id"]
        fantasma = next(u for u in com_bd.users.docs if u["id"] == pid)
        assert fantasma["role"] == "parceiro" and fantasma["partner_directory"] is True
        assert "password" not in fantasma and "hashed_password" not in fantasma

    async def test_o_convite_deixa_rasto_no_trilho_de_auditoria(self, com_bd):
        import services.partner_accounts as acc

        await _convidar(acc, ADMIN_POWER)
        assert any("partner_invite" == (r.get("field")) for r in com_bd.audit_trail.docs)

    async def test_activar_define_a_password_aceita_os_termos_e_consome_o_convite(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        guardado = com_bd.partners.docs[0]
        assert guardado["status"] == "active" and guardado["password_hash"].startswith("$2")
        assert "invite" not in guardado
        assert guardado["terms"]["version"] == acc.VERSAO_DOS_TERMOS and guardado["terms"]["ip"] == "10.0.0.1"
        assert sessao["partner"]["status"] == "active"

    async def test_o_convite_e_de_uso_unico(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        await _activar(acc, convite)
        with pytest.raises(HTTPException) as erro:
            await _activar(acc, convite, password="Outra#Pass2027")
        assert erro.value.status_code == 400 and erro.value.detail == acc.ERRO_CONVITE

    async def test_dois_pedidos_com_o_mesmo_link_nao_ganham_os_dois(self, com_bd):
        """A reivindicação é atómica: mesmo que o 2.º pedido tenha lido o
        parceiro ANTES de o 1.º consumir o convite, a escrita não casa."""
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        vista_antiga = copy.deepcopy(com_bd.partners.docs[0])
        await _activar(acc, convite)
        hash_original = com_bd.partners.docs[0]["password_hash"]
        with patch.object(acc, "_parceiro_do_convite", AsyncMock(return_value=vista_antiga)):
            with pytest.raises(HTTPException) as erro:
                await _activar(acc, convite, password="Outra#Pass2027")
        assert erro.value.status_code == 400
        assert com_bd.partners.docs[0]["password_hash"] == hash_original, "a segunda password não vence"

    async def test_um_convite_expirado_e_recusado_e_uma_data_ilegivel_conta_como_expirado(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        for data in ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), "não-é-data"):
            com_bd.partners.docs[0]["invite"]["expires_at"] = data
            with pytest.raises(HTTPException) as erro:
                await _activar(acc, convite)
            assert erro.value.status_code == 400

    async def test_sem_aceitar_os_termos_nao_ha_conta(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        with pytest.raises(HTTPException) as erro:
            await acc.run_accept_invite(
                acc.PartnerAcceptInvite(token=convite["invite_token"], password=PASSWORD, accept_terms=False)
            )
        assert erro.value.status_code == 400
        assert "password_hash" not in com_bd.partners.docs[0]

    async def test_uma_password_fraca_e_recusada_e_o_convite_continua_valido(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        with pytest.raises(HTTPException):
            await _activar(acc, convite, password="fraca")
        assert acc.convite_vigente(com_bd.partners.docs[0])

    async def test_a_leitura_do_convite_nao_diz_nada_de_um_token_invalido(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        info = await acc.run_get_invite(convite["invite_token"])
        assert info["email"] == "rui@parceiros.pt" and info["first_access"] is True
        with pytest.raises(HTTPException) as erro:
            await acc.run_get_invite("x" * 43)
        assert erro.value.status_code == 400

    async def test_reenviar_invalida_o_link_anterior(self, com_bd):
        import services.partner_accounts as acc

        antigo = await _convidar(acc, ADMIN_POWER)
        novo = await acc.run_resend_invite(antigo["partner"]["id"], ADMIN_POWER)
        assert novo["invite_token"] != antigo["invite_token"]
        with pytest.raises(HTTPException):
            await _activar(acc, antigo)
        await _activar(acc, novo)

    async def test_uma_conta_suspensa_nao_se_reactiva_com_um_link_antigo(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        novo = await acc.run_resend_invite(sessao["partner"]["id"], ADMIN_POWER)
        await acc.run_update_partner(sessao["partner"]["id"], acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        # Com a ligação suspensa o link activa a password mas não devolve sessão.
        with pytest.raises(HTTPException) as erro:
            await _activar(acc, novo, password="Outra#Pass2027")
        assert erro.value.status_code == 403


# ════════════════════════════════════════════════════════════════════
#  QUEM CONVIDA, E A QUEM
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestQuemConvida:
    async def test_o_admin_de_uma_rede_nao_convida_para_a_empresa_de_outra(self, com_bd):
        import services.partner_accounts as acc

        with pytest.raises(HTTPException) as erro:
            await _convidar(acc, ADMIN_POWER, company_id="cmp-domus")
        assert erro.value.status_code == 404
        assert com_bd.partners.docs == []

    async def test_o_404_de_uma_empresa_alheia_e_igual_ao_de_uma_inexistente(self, com_bd):
        import services.partner_accounts as acc

        with pytest.raises(HTTPException) as alheia:
            await _convidar(acc, ADMIN_POWER, company_id="cmp-domus")
        with pytest.raises(HTTPException) as nada:
            await _convidar(acc, ADMIN_POWER, company_id="cmp-nao-existe")
        assert (alheia.value.status_code, alheia.value.detail) == (nada.value.status_code, nada.value.detail)

    async def test_nem_o_master_convida_para_uma_empresa_que_nao_existe(self, com_bd):
        import services.partner_accounts as acc

        with pytest.raises(HTTPException) as erro:
            await _convidar(acc, MASTER, company_id="cmp-inventada")
        assert erro.value.status_code == 404 and com_bd.partners.docs == []

    async def test_o_master_convida_para_qualquer_rede(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, MASTER, company_id="cmp-domus")
        assert convite["partner"]["redes"][0]["network_id"] == REDE_DOMUS

    async def test_email_de_staff_e_email_de_parceiro_dao_a_mesma_recusa(self, com_bd):
        import services.partner_accounts as acc

        com_bd.users.docs.append({"id": "u-x", "email": "colega@power.pt", "role": "consultor"})
        with pytest.raises(HTTPException) as staff:
            await _convidar(acc, ADMIN_POWER, email="colega@power.pt")
        await _convidar(acc, ADMIN_POWER)
        with pytest.raises(HTTPException) as parceiro:
            await _convidar(acc, ADMIN_POWER)
        assert (staff.value.status_code, staff.value.detail) == (parceiro.value.status_code, parceiro.value.detail)
        assert staff.value.status_code == 409

    async def test_adoptar_uma_conta_fantasma_mantem_o_id_e_os_processos_que_ja_apontam_para_ela(self, com_bd):
        import services.partner_accounts as acc

        com_bd.users.docs.append({"id": "ghost-1", "name": "Antigo", "role": "parceiro", "is_active": True})
        com_bd.processes.docs.append({"id": "p-x", "assigned_parceiro_id": "ghost-1", "network_id": REDE_INCUMBENTE})
        convite = await _convidar(acc, ADMIN_POWER, adopt_user_id="ghost-1")
        assert convite["partner"]["id"] == "ghost-1"
        assert len([u for u in com_bd.users.docs if u["id"] == "ghost-1"]) == 1, "sem linha duplicada no directório"
        assert com_bd.processes.docs[-1]["assigned_parceiro_id"] == "ghost-1"

    @pytest.mark.parametrize(
        "alvo",
        [
            {"id": "s-1", "role": "consultor"},                                   # staff a sério
            {"id": "s-1", "role": "parceiro", "password": "$2b$12$abc"},          # fantasma COM password
            {"id": "s-1", "role": "parceiro", "hashed_password": "$2b$12$abc"},
        ],
    )
    async def test_nao_se_adopta_uma_conta_que_pode_autenticar_no_staff(self, com_bd, alvo):
        import services.partner_accounts as acc

        com_bd.users.docs.append({"name": "S", "email": "s@x.pt", **alvo})
        with pytest.raises(HTTPException) as erro:
            await _convidar(acc, ADMIN_POWER, adopt_user_id="s-1")
        assert erro.value.status_code == 404
        assert com_bd.partners.docs == []

    async def test_o_corpo_do_convite_recusa_campos_a_mais(self, com_bd):
        import services.partner_accounts as acc
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            acc.PartnerInvite(name="Rui", email="r@p.pt", company_id="cmp-power", network_id="rede-de-outro")
        with pytest.raises(ValidationError):
            acc.PartnerInvite(name="Rui", email="r@p.pt", company_id="cmp-power", status="active")


@pytest.mark.asyncio
class TestParedeEntreRedes:
    async def _parceiro_da_domus(self, acc):
        return (await _convidar(acc, ADMIN_DOMUS, email="d@parceiros.pt", company_id="cmp-domus"))["partner"]["id"]

    async def test_um_admin_de_outra_rede_recebe_404_em_tudo_e_igual_ao_de_inexistente(self, com_bd):
        import services.partner_accounts as acc

        pid = await self._parceiro_da_domus(acc)
        chamadas = {
            "get": lambda i: acc.run_get_partner(i, ADMIN_POWER),
            "patch": lambda i: acc.run_update_partner(i, acc.PartnerUpdate(suspended=True), ADMIN_POWER),
            "resend": lambda i: acc.run_resend_invite(i, ADMIN_POWER),
        }
        for nome, chamar in chamadas.items():
            with pytest.raises(HTTPException) as alheio:
                await chamar(pid)
            with pytest.raises(HTTPException) as nada:
                await chamar("nao-existe")
            assert (alheio.value.status_code, alheio.value.detail) == (nada.value.status_code, nada.value.detail), nome
            assert alheio.value.status_code == 404, nome
        # e a conta alheia ficou intacta
        assert com_bd.partners.docs[0]["redes"][0]["status"] == "active"

    async def test_a_listagem_so_mostra_os_parceiros_da_propria_rede(self, com_bd):
        import services.partner_accounts as acc

        await _convidar(acc, ADMIN_POWER)
        await self._parceiro_da_domus(acc)
        power = await acc.run_list_partners(ADMIN_POWER)
        domus = await acc.run_list_partners(ADMIN_DOMUS)
        master = await acc.run_list_partners(MASTER)
        assert [p["email"] for p in power["partners"]] == ["rui@parceiros.pt"]
        assert [p["email"] for p in domus["partners"]] == ["d@parceiros.pt"]
        assert master["total"] == 2

    async def test_a_listagem_nunca_traz_hash_nem_convite(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        await _activar(acc, convite)
        blob = repr(await acc.run_list_partners(MASTER))
        assert "password_hash" not in blob and "token_hash" not in blob and "$2b$" not in blob

    async def test_suspender_actua_so_na_ligacao_da_rede_de_quem_actua(self, com_bd):
        """Um parceiro com DUAS redes: o Admin da Power suspende a ligação à
        Power e não toca na da Domus, que não é dele."""
        import services.partner_accounts as acc
        from services.partner_security import ids_das_redes_activas

        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        pid = sessao["partner"]["id"]
        com_bd.partners.docs[0]["redes"].append(
            {"network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus", "status": "active"}
        )

        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        estados = {r["network_id"]: r["status"] for r in com_bd.partners.docs[0]["redes"]}
        assert estados == {REDE_INCUMBENTE: "suspended", REDE_DOMUS: "active"}
        assert ids_das_redes_activas(com_bd.partners.docs[0]) == [REDE_DOMUS]

    async def test_o_master_suspende_todas_as_ligacoes(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        com_bd.partners.docs[0]["redes"].append(
            {"network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus", "status": "active"}
        )
        await acc.run_update_partner(sessao["partner"]["id"], acc.PartnerUpdate(suspended=True), MASTER)
        assert {r["status"] for r in com_bd.partners.docs[0]["redes"]} == {"suspended"}

    async def test_editar_o_nome_actualiza_tambem_o_directorio(self, com_bd):
        import services.partner_accounts as acc

        pid = (await _convidar(acc, ADMIN_POWER))["partner"]["id"]
        await acc.run_update_partner(pid, acc.PartnerUpdate(name="Rui Novo"), ADMIN_POWER)
        assert next(u for u in com_bd.users.docs if u["id"] == pid)["name"] == "Rui Novo"


# ════════════════════════════════════════════════════════════════════
#  O PERFIL PÚBLICO É UMA LISTA POSITIVA
# ════════════════════════════════════════════════════════════════════
class TestPerfilPublico:
    def test_publico_nunca_deixa_sair_segredos(self):
        from services.partner_accounts import publico

        doc = {
            "id": "p1", "name": "R", "email": "r@p.pt", "status": "active",
            "password_hash": "$2b$12$segredo", "token_epoch": 7,
            "invite": {"token_hash": "abc"}, "terms": {"ip": "1.2.3.4"},
            "redes": [{"network_id": "n", "company_id": "c", "company_name": "C", "invited_by": "u-1"}],
        }
        saida = publico(doc)
        blob = repr(saida)
        for proibido in ("segredo", "token_epoch", "abc", "1.2.3.4", "u-1"):
            assert proibido not in blob, proibido
        assert saida["redes"] == [{"network_id": "n", "company_id": "c", "company_name": "C", "status": "active"}]
