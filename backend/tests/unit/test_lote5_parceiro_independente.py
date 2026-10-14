"""
Lote 5, ponto 1 (Out 2026) — um Parceiro é um operador EXTERNO e independente: não pertence a uma Empresa.

O que se prova, por ordem de gravidade:

  1. a ausência de empresa NÃO abre dados — o âmbito de um parceiro sem ligações é vazio (condição
     impossível), nunca «sem filtro»;
  2. a ausência de empresa NÃO é a ausência de suspensão — um parceiro com ligações TODAS suspensas continua
     recusado (uma lista de suspensas não pode confundir-se com «nunca esteve ligado»);
  3. o agente independente entra (convite → login → sessão), vê todos os destinos e a primeira lead cria a
     ligação de mercado;
  4. continua gerível: por quem o convidou (rede do convite) e pelo Master — nunca por outra rede (404) —, e a
     suspensão actua na CONTA (não há ligações onde a pôr);
  5. o fluxo de sempre (convite COM empresa) e a conta-fantasma `users.role == "parceiro"` não mudam.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)
from tests.unit.test_parceiro_identidade import (
    ADMIN_DOMUS,
    ADMIN_POWER,
    MASTER,
    PASSWORD,
    _activar,
    _convidar,
    _creds,
    com_bd,  # noqa: F401
    mundo,  # noqa: F401
)


async def _independente(acc, actor=ADMIN_POWER, **extra):
    """Convite SEM empresa (a chave `company_id` nem vai no corpo)."""
    corpo = {"name": "Ivo Independente", "email": "ivo@parceiros.pt", **extra}
    return await acc.run_invite_partner(acc.PartnerInvite(**corpo), actor)


# ════════════════════════════════════════════════════════════════════
#  O CONVITE
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOConviteSemEmpresa:
    async def test_o_convite_nasce_sem_ligacoes_e_com_a_rede_de_quem_convidou(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc)
        doc = next(p for p in com_bd.partners.docs if p["id"] == convite["partner"]["id"])

        assert doc["redes"] == [], "sem empresa não há ligação a nenhuma rede"
        assert doc["convidado_pela_rede"] == REDE_INCUMBENTE
        assert convite["partner"]["redes"] == []
        assert convite["invite_token"], "o convite sai como sempre"

    async def test_com_empresa_nada_mudou(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        doc = next(p for p in com_bd.partners.docs if p["id"] == convite["partner"]["id"])

        assert [r["network_id"] for r in doc["redes"]] == [REDE_INCUMBENTE]
        assert doc["redes"][0]["company_id"] == "cmp-power"

    async def test_o_master_convida_sem_empresa_e_sem_rede_propria(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc, MASTER)
        doc = next(p for p in com_bd.partners.docs if p["id"] == convite["partner"]["id"])
        assert doc["redes"] == []
        assert doc["convidado_pela_rede"] is None, "o Master não tem rede de convite — gere por ser global"

    async def test_uma_empresa_indicada_continua_a_ter_de_estar_no_ambito_de_quem_convida(self, com_bd):
        """O que era obrigatório passou a opcional — mas escolhida, a empresa continua a ser validada."""
        import services.partner_accounts as acc

        with pytest.raises(HTTPException) as erro:
            await _convidar(acc, ADMIN_DOMUS, company_id="cmp-power")
        assert erro.value.status_code in (403, 404)
        assert not com_bd.partners.docs

    async def test_uma_empresa_em_branco_vale_como_ausente(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc, company_id="   ")
        assert convite["partner"]["redes"] == []

    async def test_a_conta_fantasma_do_staff_continua_a_nascer_sem_empresa(self):
        """O outro «Parceiro» do produto (`users.role == parceiro`): nunca exigiu empresa."""
        from services.user_company_bootstrap import assert_acessos_obrigatorios

        assert_acessos_obrigatorios("parceiro", [])  # não levanta
        with pytest.raises(HTTPException):
            assert_acessos_obrigatorios("consultor", [])


# ════════════════════════════════════════════════════════════════════
#  ENTRAR — e não ver nada até haver uma ligação
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOAgenteIndependenteEntra:
    async def test_activa_o_convite_e_recebe_sessao(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc)
        sessao = await _activar(acc, convite)
        assert sessao["access_token"]
        assert sessao["partner"]["redes"] == []

    async def test_faz_login_e_a_dependencia_de_sessao_aceita_o_token(self, com_bd):
        import services.partner_accounts as acc
        import services.partner_security as sec

        convite = await _independente(acc)
        await _activar(acc, convite)
        sessao = await acc.run_partner_login(acc.PartnerLogin(email="ivo@parceiros.pt", password=PASSWORD))

        partner = await sec.get_current_partner(_creds(sessao["access_token"]))
        assert partner["id"] == convite["partner"]["id"]

    async def test_a_exploracao_sem_ligacoes_o_ambito_e_vazio_e_nunca_sem_filtro(self, com_bd):
        """O ATAQUE: um parceiro sem empresa não pode ver processos nem leads de ninguém."""
        import services.partner_accounts as acc
        from services.partner_visibility import condicao_de_leads, condicao_de_processos, scope_do_parceiro
        from tests.unit.helpers_tenant import casa

        convite = await _independente(acc)
        await _activar(acc, convite)
        partner = next(p for p in com_bd.partners.docs if p["id"] == convite["partner"]["id"])

        assert scope_do_parceiro(partner).network_ids == ()
        alheio = {
            "id": "p-x", "network_id": REDE_INCUMBENTE, "assigned_parceiro_id": partner["id"],
            "submitted_by_partner_id": partner["id"], "is_deleted": False,
        }
        assert not casa(alheio, condicao_de_processos(partner)), "nem o processo atribuído a ele, enquanto não há ligação"
        assert not casa(alheio, condicao_de_leads(partner))

    async def test_a_exploracao_o_independente_nao_e_a_rede_de_omissao(self, com_bd):
        """Ser da rede de omissão abre a pilha por carimbar — um independente NÃO o é por não ter rede."""
        import services.partner_accounts as acc
        from services.partner_visibility import scope_do_parceiro

        convite = await _independente(acc)
        partner = next(p for p in com_bd.partners.docs if p["id"] == convite["partner"]["id"])
        assert scope_do_parceiro(partner).inclui_rede_de_omissao is False


# ════════════════════════════════════════════════════════════════════
#  A CONTRAPROVA — «sem empresa» não é «sem suspensão»
# ════════════════════════════════════════════════════════════════════
class TestSuspensasContinuamRecusadas:
    def test_todas_as_ligacoes_suspensas_nao_entram(self):
        from services.partner_security import conta_com_acesso

        partner = {"redes": [{"network_id": REDE_INCUMBENTE, "status": "suspended"}]}
        assert conta_com_acesso(partner) is False

    def test_uma_ligacao_activa_entra(self):
        from services.partner_security import conta_com_acesso

        assert conta_com_acesso({"redes": [{"network_id": REDE_INCUMBENTE, "status": "active"}]}) is True

    def test_sem_nenhuma_ligacao_entra(self):
        from services.partner_security import conta_com_acesso

        assert conta_com_acesso({"redes": []}) is True
        assert conta_com_acesso({"id": "par-antigo"}) is True, "documento antigo sem o campo `redes`"
        assert conta_com_acesso({}) is False, "um documento vazio não é um parceiro"

    def test_uma_ligacao_sem_network_id_nao_conta_como_activa_nem_como_ausencia(self):
        """Dados corrompidos falham FECHADO: a entrada existe, logo não é um agente independente."""
        from services.partner_security import conta_com_acesso

        assert conta_com_acesso({"redes": [{"company_id": "x", "status": "active"}]}) is False

    def test_sem_documento_nao_entra(self):
        from services.partner_security import conta_com_acesso

        assert conta_com_acesso(None) is False

    @pytest.mark.asyncio
    async def test_o_login_de_quem_tem_todas_as_ligacoes_suspensas_e_recusado(self, com_bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        await _activar(acc, convite)
        await acc.run_update_partner(convite["partner"]["id"], acc.PartnerUpdate(suspended=True), ADMIN_POWER)

        with pytest.raises(HTTPException) as erro:
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        assert erro.value.status_code == 403


# ════════════════════════════════════════════════════════════════════
#  DESTINOS E A PRIMEIRA LEAD
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestDestinosESLigacaoDeMercado:
    async def test_lista_todos_os_destinos_incluindo_os_que_aceitam_parceiros(self, com_bd):
        import services.partner_leads as leads

        com_bd.companies.docs.append({"id": "cmp-aberta", "name": "Aberta", "network_id": "rede_x", "aceita_parceiros": True})
        with patch.object(leads, "db", com_bd), \
             patch("services.network_triage.redes_com_index", AsyncMock(return_value={REDE_INCUMBENTE})):
            nomes = {d["company_name"] for d in await leads.destinos_do_parceiro({"id": "par-1", "redes": []})}
        assert "Aberta" in nomes
        assert nomes >= {"Aberta"} and len(nomes) >= 2

    async def test_a_primeira_lead_cria_a_ligacao_de_mercado(self, com_bd):
        import services.partner_accounts as acc
        import services.partner_leads as leads

        convite = await _independente(acc)
        await _activar(acc, convite)
        partner = next(p for p in com_bd.partners.docs if p["id"] == convite["partner"]["id"])

        with patch.object(leads, "db", com_bd), \
             patch("services.network_triage.redes_com_index", AsyncMock(return_value={REDE_INCUMBENTE})):
            ligacao = await leads.resolver_destino(dict(partner), "cmp-power")

        actualizado = next(p for p in com_bd.partners.docs if p["id"] == partner["id"])
        assert [r["network_id"] for r in actualizado["redes"]] == [ligacao["network_id"]]
        assert actualizado["redes"][0]["origem"] == "marketplace"
        assert actualizado["convidado_pela_rede"] == REDE_INCUMBENTE, "a rede do convite não se perde"


# ════════════════════════════════════════════════════════════════════
#  A GESTÃO — quem o vê e quem o trava
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestGestaoDoIndependente:
    async def test_quem_convidou_ve_e_lista_o_parceiro(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc)
        listado = await acc.run_list_partners(ADMIN_POWER)
        assert [p["id"] for p in listado["partners"]] == [convite["partner"]["id"]]
        assert (await acc.run_get_partner(convite["partner"]["id"], ADMIN_POWER))["id"] == convite["partner"]["id"]

    async def test_a_exploracao_outra_rede_nao_o_ve_nem_o_trava(self, com_bd):
        """404 igual ao de «não existe» — o independente não é um directório para a Domus."""
        import services.partner_accounts as acc

        convite = await _independente(acc)
        assert (await acc.run_list_partners(ADMIN_DOMUS))["partners"] == []
        for chamada in (
            acc.run_get_partner(convite["partner"]["id"], ADMIN_DOMUS),
            acc.run_update_partner(convite["partner"]["id"], acc.PartnerUpdate(suspended=True), ADMIN_DOMUS),
            acc.run_resend_invite(convite["partner"]["id"], ADMIN_DOMUS),
        ):
            with pytest.raises(HTTPException) as erro:
                await chamada
            assert erro.value.status_code == 404

    async def test_o_master_gere_o_independente(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc, MASTER)
        assert [p["id"] for p in (await acc.run_list_partners(MASTER))["partners"]] == [convite["partner"]["id"]]

    async def test_suspender_actua_na_conta_e_mata_a_sessao_na_hora(self, com_bd):
        import services.partner_accounts as acc
        import services.partner_security as sec

        convite = await _independente(acc)
        sessao = await _activar(acc, convite)
        pid = convite["partner"]["id"]

        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        assert next(p for p in com_bd.partners.docs if p["id"] == pid)["status"] == "suspended"
        with pytest.raises(HTTPException) as erro:
            await sec.get_current_partner(_creds(sessao["access_token"]))
        assert erro.value.status_code == 401
        with pytest.raises(HTTPException) as erro:
            await acc.run_partner_login(acc.PartnerLogin(email="ivo@parceiros.pt", password=PASSWORD))
        assert erro.value.status_code == 403

    async def test_reactivar_devolve_o_acesso(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc)
        await _activar(acc, convite)
        pid = convite["partner"]["id"]
        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=False), ADMIN_POWER)

        sessao = await acc.run_partner_login(acc.PartnerLogin(email="ivo@parceiros.pt", password=PASSWORD))
        assert sessao["access_token"]

    async def test_reactivar_quem_nunca_definiu_a_palavra_passe_volta_a_convidado(self, com_bd):
        """Reactivar não pode dar ao convite pendente o estado de uma conta activa sem termos aceites."""
        import services.partner_accounts as acc

        convite = await _independente(acc)
        pid = convite["partner"]["id"]
        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        await acc.run_update_partner(pid, acc.PartnerUpdate(suspended=False), ADMIN_POWER)
        assert next(p for p in com_bd.partners.docs if p["id"] == pid)["status"] == "invited"

    async def test_depois_da_primeira_ligacao_mandam_as_ligacoes_e_nao_a_rede_do_convite(self, com_bd):
        """A rede que convidou não passa a gerir as ligações das outras (a suspensão é por ligação)."""
        import services.partner_accounts as acc

        convite = await _independente(acc)
        pid = convite["partner"]["id"]
        await acc.acrescentar_ligacao_de_mercado(
            pid, {"network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus"},
        )

        assert (await acc.run_list_partners(ADMIN_POWER))["partners"] == []
        assert [p["id"] for p in (await acc.run_list_partners(ADMIN_DOMUS))["partners"]] == [pid]


# ════════════════════════════════════════════════════════════════════
#  O PARCEIRO-FANTASMA DO STAFF (`users.role == parceiro`) SEM EMPRESA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestParceiroDoStaffSemEmpresaContinuaVisivel:
    """O defeito: sem empresa, a conta só pertencia a quem detém a rede de omissão — o Admin da Domus
    criava um parceiro e ele desaparecia da lista (e deixava de poder ser editado)."""

    async def _criar(self, com_bd, actor):
        import services.admin_users as admin_users
        from models.auth import UserCreate

        with patch.object(admin_users, "db", com_bd):
            return await admin_users.run_create_user(UserCreate(name="Pedro Parceiro", role="parceiro", email=""), actor)

    async def test_o_parceiro_criado_sem_empresa_leva_a_rede_de_quem_o_criou(self, com_bd):
        await self._criar(com_bd, ADMIN_DOMUS)
        doc = next(u for u in com_bd.users.docs if u.get("name") == "Pedro Parceiro")
        assert doc["criado_pela_rede"] == REDE_DOMUS

    async def test_quem_o_criou_continua_a_ve_lo_no_seu_ambito(self, com_bd):
        from services.admin_users_scope import build_users_scope_query, empresas_do_ambito
        from tests.unit.helpers_tenant import casa

        await self._criar(com_bd, ADMIN_DOMUS)
        doc = next(u for u in com_bd.users.docs if u.get("name") == "Pedro Parceiro")
        consulta = await build_users_scope_query(await empresas_do_ambito(ADMIN_DOMUS))
        assert casa(doc, consulta)

    async def test_a_exploracao_outra_rede_nao_o_ve(self, com_bd):
        from services.admin_users_scope import build_users_scope_query, empresas_do_ambito
        from tests.unit.helpers_tenant import casa

        await self._criar(com_bd, ADMIN_DOMUS)
        doc = next(u for u in com_bd.users.docs if u.get("name") == "Pedro Parceiro")
        consulta = await build_users_scope_query(await empresas_do_ambito(ADMIN_POWER))
        assert not casa(doc, consulta), "o carimbo não é um passe livre entre redes"

    async def test_o_carimbo_so_vale_para_parceiros(self, com_bd):
        """Um utilizador comum com o mesmo campo NÃO fica visível por ele."""
        from services.admin_users_scope import build_users_scope_query, empresas_do_ambito
        from tests.unit.helpers_tenant import casa

        intruso = {"id": "u-x", "role": "consultor", "criado_pela_rede": REDE_DOMUS, "company": "Power Real Estate"}
        consulta = await build_users_scope_query(await empresas_do_ambito(ADMIN_DOMUS))
        assert not casa(intruso, consulta)

    async def test_o_directorio_do_parceiro_do_portal_tambem_leva_a_rede_do_convite(self, com_bd):
        import services.partner_accounts as acc

        convite = await _independente(acc, ADMIN_DOMUS)
        linha = next(u for u in com_bd.users.docs if u["id"] == convite["partner"]["id"])
        assert linha["criado_pela_rede"] == REDE_DOMUS
