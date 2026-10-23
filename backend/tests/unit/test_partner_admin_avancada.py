"""
Gestão avançada de parceiros (Out 2026): a VISTA do Master e as quatro acções de controlo total.

  1. Master com empresa escolhida só vê/gere os parceiros da rede dela (listas, opções, objecto, suspensão);
  2. editar o email (só Master; identidade de login → convite pendente anulado, sessões abatidas);
  3. mudar de empresa (substitui as ligações de gestão, mantém as de mercado, não reactiva suspensões);
  4. eliminar (soft delete, password ANTES de escrever, liberta o email);
  5. gerar nova palavra-passe (o email sai primeiro; sem entrega nada muda).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services.auth import hash_password
from tests.unit.helpers_tenant import rede_de_omissao_incumbente, tenant_db  # noqa: F401
from tests.unit.test_parceiro_identidade import (
    ADMIN_DOMUS,
    ADMIN_POWER,
    MASTER,
    PASSWORD,
    _activar,
    _convidar,
    _creds,
    mundo,  # noqa: F401
)

SENHA_DO_MASTER = "Segredo-Master-9!"
MASTER_NA_DOMUS = {**MASTER, "vista_empresa_id": "cmp-domus"}
MASTER_NA_POWER = {**MASTER, "vista_empresa_id": "cmp-power"}


@pytest.fixture
def bd(mundo):
    import services.admin_users_scope as scope_mod
    import services.audit_trail_service as audit
    import services.partner_accounts as acc
    import services.partner_accounts_admin as adm
    import services.partner_security as sec
    import services.reauth_password as reauth
    import services.user_management_scope as ums

    mundo.users.docs.append(
        {"id": MASTER["id"], "email": MASTER["email"], "password": hash_password(SENHA_DO_MASTER), "is_active": True}
    )
    for u in (ADMIN_POWER, {"id": "u-ceo", "email": "ceo@power.pt"}):
        mundo.users.docs.append({"id": u["id"], "email": u["email"], "password": hash_password(SENHA_DO_MASTER)})
    with tenant_db(mundo, scope_mod, ums, acc, sec, adm, reauth), patch.object(audit, "db", mundo):
        yield mundo


async def _dois_parceiros(acc):
    rui = await _convidar(acc, ADMIN_POWER)
    dina = await _convidar(acc, ADMIN_DOMUS, name="Dina Domus", email="dina@parceiros.pt", company_id="cmp-domus")
    return rui["partner"]["id"], dina["partner"]["id"]


def _doc(bd, pid):
    return next(p for p in bd.partners.docs if p["id"] == pid)


def _rasto(bd, campo):
    return [a for a in bd.audit_trail.docs if a.get("field") == campo]


# ════════════════════════════════════════════════════════════════════
#  1. A VISTA DO MASTER
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAVistaDoMaster:
    async def test_sem_empresa_escolhida_ve_todos(self, bd):
        import services.partner_accounts as acc

        await _dois_parceiros(acc)
        r = await acc.run_list_partners(MASTER)
        assert r["total"] == 2

    async def test_com_a_domus_escolhida_so_ve_os_da_domus(self, bd):
        import services.partner_accounts as acc

        _rui, dina = await _dois_parceiros(acc)
        r = await acc.run_list_partners(MASTER_NA_DOMUS)
        assert [p["id"] for p in r["partners"]] == [dina]

    async def test_com_a_power_escolhida_so_ve_os_da_power(self, bd):
        import services.partner_accounts as acc

        rui, _dina = await _dois_parceiros(acc)
        r = await acc.run_list_partners(MASTER_NA_POWER)
        assert [p["id"] for p in r["partners"]] == [rui]

    async def test_as_opcoes_dos_filtros_seguem_a_vista(self, bd):
        import services.partner_accounts as acc

        _rui, dina = await _dois_parceiros(acc)
        r = await acc.run_list_partner_options(MASTER_NA_DOMUS)
        assert [p["id"] for p in r["partners"]] == [dina]

    async def test_abrir_um_parceiro_de_outra_rede_e_404(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        with pytest.raises(HTTPException) as erro:
            await acc.run_get_partner(rui, MASTER_NA_DOMUS)
        assert erro.value.status_code == 404
        assert (await acc.run_get_partner(rui, MASTER))["id"] == rui

    async def test_um_cabecalho_com_empresa_inexistente_nao_estreita(self, bd):
        import services.partner_accounts as acc

        await _dois_parceiros(acc)
        r = await acc.run_list_partners({**MASTER, "vista_empresa_id": "cmp-velha"})
        assert r["total"] == 2

    async def test_suspender_na_vista_so_toca_nas_ligacoes_dessa_rede(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        await acc.acrescentar_ligacao_de_mercado(
            rui, {"network_id": "grupo_domus", "company_id": "cmp-domus", "company_name": "Domus"}
        )
        await acc.run_update_partner(rui, acc.PartnerUpdate(suspended=True), MASTER_NA_DOMUS)
        estados = {r["network_id"]: r["status"] for r in _doc(bd, rui)["redes"]}
        assert estados == {"grupo_power_precision": "active", "grupo_domus": "suspended"}


# ════════════════════════════════════════════════════════════════════
#  2. EDITAR O EMAIL
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestEditarOEmail:
    async def test_o_master_muda_o_email_e_o_directorio_acompanha(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        r = await acc.run_update_partner(rui, acc.PartnerUpdate(email="Novo@Parceiros.pt"), MASTER)
        assert r["email"] == "novo@parceiros.pt"
        assert next(u for u in bd.users.docs if u["id"] == rui)["email"] == "novo@parceiros.pt"

    async def test_admin_e_ceo_nao_mudam_o_email(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        for actor in (ADMIN_POWER, {**ADMIN_POWER, "role": "ceo", "effective_role": "ceo"}):
            with pytest.raises(HTTPException) as erro:
                await acc.run_update_partner(rui, acc.PartnerUpdate(email="x@parceiros.pt"), actor)
            assert erro.value.status_code == 403
        assert _doc(bd, rui)["email"] == "rui@parceiros.pt"

    async def test_o_admin_continua_a_poder_mudar_o_nome(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        r = await acc.run_update_partner(rui, acc.PartnerUpdate(name="Rui Novo"), ADMIN_POWER)
        assert r["name"] == "Rui Novo"

    async def test_email_de_outro_parceiro_ou_do_staff_e_409_e_nada_muda(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        bd.users.docs.append({"id": "u-staff", "email": "staff@power.pt", "role": "consultor"})
        for email in ("dina@parceiros.pt", "staff@power.pt"):
            with pytest.raises(HTTPException) as erro:
                await acc.run_update_partner(rui, acc.PartnerUpdate(name="Outro Nome", email=email), MASTER)
            assert erro.value.status_code == 409
        doc = _doc(bd, rui)
        assert doc["email"] == "rui@parceiros.pt" and doc["name"] == "Rui Parceiro"

    async def test_o_mesmo_email_e_um_no_op_que_nao_abate_sessoes(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        antes = _doc(bd, rui).get("token_epoch", 0)
        await acc.run_update_partner(rui, acc.PartnerUpdate(email="RUI@parceiros.pt"), MASTER)
        assert _doc(bd, rui).get("token_epoch", 0) == antes

    async def test_um_email_invalido_e_400(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        with pytest.raises(HTTPException) as erro:
            await acc.run_update_partner(rui, acc.PartnerUpdate(email="@@@"), MASTER)
        assert erro.value.status_code == 400

    async def test_conta_activa_as_sessoes_caem_e_o_login_passa_ao_email_novo(self, bd):
        import services.partner_accounts as acc
        import services.partner_security as sec

        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        rui = convite["partner"]["id"]
        await acc.run_update_partner(rui, acc.PartnerUpdate(email="novo@parceiros.pt"), MASTER)

        with pytest.raises(HTTPException) as erro:
            await sec.get_current_partner(_creds(sessao["access_token"]))
        assert erro.value.status_code == 401
        with pytest.raises(HTTPException):
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        nova = await acc.run_partner_login(acc.PartnerLogin(email="novo@parceiros.pt", password=PASSWORD))
        assert nova["access_token"]

    async def test_convite_pendente_antigo_morre_e_o_novo_segue_para_o_endereco_novo(self, bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        rui = convite["partner"]["id"]
        r = await acc.run_update_partner(rui, acc.PartnerUpdate(email="novo@parceiros.pt"), MASTER)

        with pytest.raises(HTTPException):
            await _activar(acc, convite)  # o link enviado para o endereço antigo
        assert r["invite_path"].startswith("/parceiro/convite/")
        token = r["invite_path"].rsplit("/", 1)[1]
        sessao = await acc.run_accept_invite(
            acc.PartnerAcceptInvite(token=token, password=PASSWORD, accept_terms=True), ip="1.1.1.1"
        )
        assert sessao["partner"]["email"] == "novo@parceiros.pt"

    async def test_o_convite_pendente_de_uma_conta_activa_tambem_morre(self, bd):
        """Conta já activa com um convite de «repor acesso» a meio: o link foi para o endereço antigo."""
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        await _activar(acc, convite)
        rui = convite["partner"]["id"]
        novo = await acc.run_resend_invite(rui, ADMIN_POWER)
        await acc.run_update_partner(rui, acc.PartnerUpdate(email="n@parceiros.pt"), MASTER)
        assert "invite" not in _doc(bd, rui)
        token = novo["invite_token"]
        with pytest.raises(HTTPException):
            await acc.run_accept_invite(acc.PartnerAcceptInvite(token=token, password=PASSWORD), ip="1.1.1.1")

    async def test_conta_activa_nao_recebe_convite_novo(self, bd):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        await _activar(acc, convite)
        r = await acc.run_update_partner(convite["partner"]["id"], acc.PartnerUpdate(email="n@parceiros.pt"), MASTER)
        assert "invite_path" not in r
        assert "invite" not in _doc(bd, convite["partner"]["id"])

    async def test_o_master_com_chapeu_de_admin_ainda_e_master(self, bd):
        import services.partner_accounts as acc

        rui, _ = await _dois_parceiros(acc)
        chapeu = {**MASTER, "effective_role": "admin"}
        r = await acc.run_update_partner(rui, acc.PartnerUpdate(email="c@parceiros.pt"), chapeu)
        assert r["email"] == "c@parceiros.pt"


# ════════════════════════════════════════════════════════════════════
#  3. MUDAR DE EMPRESA
# ════════════════════════════════════════════════════════════════════
LIGACAO_DOMUS = {"network_id": "grupo_domus", "company_id": "cmp-domus", "company_name": "Domus"}


class TestCalcularRedes:
    def test_substitui_a_de_gestao_e_mantem_a_de_mercado(self):
        import services.partner_accounts_admin as adm

        redes = [
            {"network_id": "a", "company_id": "ca", "status": "active"},
            {"network_id": "m", "company_id": "cm", "status": "active", "origem": "marketplace"},
        ]
        nova = {"network_id": "b", "company_id": "cb", "status": "active", "origem": "transferencia"}
        r = adm.calcular_redes_apos_mudanca(redes, nova)
        assert [x["network_id"] for x in r] == ["m", "b"]

    def test_uma_ligacao_de_mercado_na_rede_de_destino_e_absorvida(self):
        import services.partner_accounts_admin as adm

        redes = [{"network_id": "b", "company_id": "cx", "status": "active", "origem": "marketplace"}]
        r = adm.calcular_redes_apos_mudanca(redes, {"network_id": "b", "company_id": "cb", "status": "active"})
        assert [x["company_id"] for x in r] == ["cb"]

    def test_a_suspensao_passa_para_a_ligacao_nova(self):
        import services.partner_accounts_admin as adm

        r = adm.calcular_redes_apos_mudanca(
            [{"network_id": "a", "status": "suspended"}], {"network_id": "b", "status": "active"}
        )
        assert r[0]["status"] == "suspended"

    def test_sem_ligacoes_a_nova_nasce_activa(self):
        import services.partner_accounts_admin as adm

        r = adm.calcular_redes_apos_mudanca([], {"network_id": "b", "status": "active"})
        assert r == [{"network_id": "b", "status": "active"}]

    def test_so_suspensas_de_mercado_nao_suspendem_a_nova(self):
        import services.partner_accounts_admin as adm

        redes = [{"network_id": "m", "status": "suspended", "origem": "marketplace"}]
        r = adm.calcular_redes_apos_mudanca(redes, {"network_id": "b", "status": "active"})
        assert r[-1]["status"] == "active"


@pytest.mark.asyncio
class TestMudarDeEmpresa:
    async def _mudar(self, adm, pid, company, actor=MASTER):
        return await adm.run_change_company(pid, adm.PartnerChangeCompany(company_id=company), actor)

    async def test_move_a_ligacao_a_rede_do_convite_e_o_directorio(self, bd):
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(__import__("services.partner_accounts", fromlist=["x"]))
        r = await self._mudar(adm, rui, "cmp-domus")
        doc = _doc(bd, rui)
        assert r["alterado"] is True
        assert [(x["company_id"], x["network_id"]) for x in doc["redes"]] == [("cmp-domus", "grupo_domus")]
        assert doc["convidado_pela_rede"] == "grupo_domus"
        assert next(u for u in bd.users.docs if u["id"] == rui)["criado_pela_rede"] == "grupo_domus"
        assert len(_rasto(bd, "partner_company_change")) == 1

    async def test_a_rede_antiga_perde_a_gestao_e_a_nova_ganha(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        await self._mudar(adm, rui, "cmp-domus")
        with pytest.raises(HTTPException) as erro:
            await acc.run_get_partner(rui, ADMIN_POWER)
        assert erro.value.status_code == 404
        assert (await acc.run_get_partner(rui, ADMIN_DOMUS))["id"] == rui

    async def test_as_ligacoes_de_mercado_mantem_se(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        await acc.acrescentar_ligacao_de_mercado(
            rui, {"network_id": "rede_x", "company_id": "cmp-x", "company_name": "X"}
        )
        await self._mudar(adm, rui, "cmp-domus")
        redes = {r["network_id"] for r in _doc(bd, rui)["redes"]}
        assert redes == {"rede_x", "grupo_domus"}

    async def test_nao_reactiva_uma_suspensao(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        await acc.run_update_partner(rui, acc.PartnerUpdate(suspended=True), ADMIN_POWER)
        await self._mudar(adm, rui, "cmp-domus")
        assert [r["status"] for r in _doc(bd, rui)["redes"]] == ["suspended"]

    async def test_o_independente_ganha_uma_ligacao(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        c = await acc.run_invite_partner(acc.PartnerInvite(name="Ivo Independente", email="ivo@parceiros.pt"), MASTER)
        await self._mudar(adm, c["partner"]["id"], "cmp-domus")
        assert [r["company_id"] for r in _doc(bd, c["partner"]["id"])["redes"]] == ["cmp-domus"]

    async def test_a_mesma_empresa_e_um_no_op(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        antes = list(_doc(bd, rui)["redes"])
        r = await self._mudar(adm, rui, "cmp-power")
        assert r["alterado"] is False and _doc(bd, rui)["redes"] == antes
        assert _rasto(bd, "partner_company_change") == []

    async def test_empresa_inexistente_e_404_e_nada_muda(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        antes = list(_doc(bd, rui)["redes"])
        with pytest.raises(HTTPException) as erro:
            await self._mudar(adm, rui, "cmp-nao-existe")
        assert erro.value.status_code == 404 and _doc(bd, rui)["redes"] == antes

    async def test_so_o_master(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        for actor in (ADMIN_POWER, ADMIN_DOMUS):
            with pytest.raises(HTTPException) as erro:
                await self._mudar(adm, rui, "cmp-domus", actor)
            assert erro.value.status_code == 403

    async def test_parceiro_inexistente_e_404(self, bd):
        import services.partner_accounts_admin as adm

        with pytest.raises(HTTPException) as erro:
            await self._mudar(adm, "nao-existe", "cmp-domus")
        assert erro.value.status_code == 404

    async def test_a_sessao_continua_valida_e_passa_a_ver_a_rede_nova(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm
        import services.partner_security as sec

        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        await self._mudar(adm, convite["partner"]["id"], "cmp-domus")
        parceiro = await sec.get_current_partner(_creds(sessao["access_token"]))
        assert sec.ids_das_redes_activas(parceiro) == ["grupo_domus"]


# ════════════════════════════════════════════════════════════════════
#  4. ELIMINAR
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestEliminar:
    async def test_sem_password_e_400_e_nada_muda(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        antes = dict(_doc(bd, rui))
        with pytest.raises(HTTPException) as erro:
            await adm.run_delete_partner(rui, None, MASTER)
        assert erro.value.status_code == 400
        assert _doc(bd, rui) == antes

    async def test_password_errada_e_403_e_nada_muda(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        antes = dict(_doc(bd, rui))
        with pytest.raises(HTTPException) as erro:
            await adm.run_delete_partner(rui, "errada", MASTER)
        assert erro.value.status_code == 403
        assert _doc(bd, rui) == antes
        assert _rasto(bd, "partner_delete") == []

    async def test_so_o_master_e_antes_de_olhar_para_a_password(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        with pytest.raises(HTTPException) as erro:
            await adm.run_delete_partner(rui, SENHA_DO_MASTER, ADMIN_POWER)
        assert erro.value.status_code == 403
        assert _doc(bd, rui)["status"] != "deleted"

    async def test_elimina_com_soft_delete_e_limpa_o_pessoal(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        convite = await _convidar(acc, ADMIN_POWER, phone="912345678")
        await _activar(acc, convite)
        rui = convite["partner"]["id"]
        r = await adm.run_delete_partner(rui, SENHA_DO_MASTER, MASTER)
        doc = _doc(bd, rui)
        assert r == {"deleted": True, "id": rui}
        assert doc["status"] == "deleted"
        assert doc["email"] == adm.email_marcador(rui) and doc["phone"] is None
        assert doc["redes"] == [] and doc["convidado_pela_rede"] is None
        assert "password_hash" not in doc and "invite" not in doc
        assert doc["terms"].get("ip") is None
        assert doc["name"] == "Rui Parceiro", "o nome fica: atribuições e histórico continuam a dizer quem foi"
        ghost = next(u for u in bd.users.docs if u["id"] == rui)
        assert ghost["is_active"] is False and ghost["partner_eliminado"] is True and ghost["name"] == "Rui Parceiro"
        assert ghost["email"] == adm.email_marcador(rui)

    async def test_deixa_rasto_sem_a_password(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        await adm.run_delete_partner(rui, SENHA_DO_MASTER, MASTER)
        [rasto] = _rasto(bd, "partner_delete")
        assert SENHA_DO_MASTER not in repr(rasto)

    async def test_a_sessao_e_o_login_deixam_de_funcionar(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm
        import services.partner_security as sec

        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        await adm.run_delete_partner(convite["partner"]["id"], SENHA_DO_MASTER, MASTER)
        with pytest.raises(HTTPException) as erro:
            await sec.get_current_partner(_creds(sessao["access_token"]))
        assert erro.value.status_code == 401
        with pytest.raises(HTTPException) as erro:
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        assert erro.value.status_code == 401

    async def test_o_convite_pendente_morre(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        convite = await _convidar(acc, ADMIN_POWER)
        await adm.run_delete_partner(convite["partner"]["id"], SENHA_DO_MASTER, MASTER)
        with pytest.raises(HTTPException):
            await _activar(acc, convite)

    async def test_desaparece_das_listas_e_da_gestao(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, dina = await _dois_parceiros(acc)
        await adm.run_delete_partner(rui, SENHA_DO_MASTER, MASTER)
        assert [p["id"] for p in (await acc.run_list_partners(MASTER))["partners"]] == [dina]
        assert [p["id"] for p in (await acc.run_list_partner_options(MASTER))["partners"]] == [dina]
        for chamada in (
            acc.run_get_partner(rui, MASTER),
            acc.run_update_partner(rui, acc.PartnerUpdate(name="Fantasma"), MASTER),
            acc.run_resend_invite(rui, MASTER),
            adm.run_delete_partner(rui, SENHA_DO_MASTER, MASTER),
            adm.run_reset_password(rui, MASTER),
        ):
            with pytest.raises(HTTPException) as erro:
                await chamada
            assert erro.value.status_code == 404

    async def test_o_contacto_do_parceiro_eliminado_nao_sai(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        assert (await acc.contacto_do_parceiro(rui))["email"] == "rui@parceiros.pt"
        await adm.run_delete_partner(rui, SENHA_DO_MASTER, MASTER)
        assert await acc.contacto_do_parceiro(rui) is None

    async def test_o_email_fica_livre_para_um_convite_novo(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await _dois_parceiros(acc)
        await adm.run_delete_partner(rui, SENHA_DO_MASTER, MASTER)
        novo = await _convidar(acc, ADMIN_POWER)
        assert novo["partner"]["id"] != rui and novo["partner"]["email"] == "rui@parceiros.pt"


# ════════════════════════════════════════════════════════════════════
#  5. NOVA PALAVRA-PASSE
# ════════════════════════════════════════════════════════════════════
class TestGerarPalavraPasse:
    def test_cumpre_sempre_a_politica_da_casa(self):
        from services.auth import validate_password_strength
        import services.partner_accounts_admin as adm

        gerada = {adm.gerar_palavra_passe() for _ in range(200)}
        assert len(gerada) == 200
        for p in gerada:
            assert validate_password_strength(p)[0], p
            assert len(p) == 16

    def test_um_tamanho_pequeno_nao_baixa_do_minimo(self):
        import services.partner_accounts_admin as adm

        assert len(adm.gerar_palavra_passe(3)) == 12


def _envio(sucesso=True):
    return AsyncMock(return_value={"success": sucesso, "error": None if sucesso else "smtp"})


@pytest.mark.asyncio
class TestNovaPalavraPasse:
    async def _activo(self, acc):
        convite = await _convidar(acc, ADMIN_POWER)
        sessao = await _activar(acc, convite)
        return convite["partner"]["id"], sessao

    async def test_envia_por_email_e_a_nova_funciona_a_antiga_nao(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await self._activo(acc)
        with patch("services.email_service.send_email", _envio()) as enviar:
            r = await adm.run_reset_password(rui, MASTER)
        assert r == {"sent": True, "email": "rui@parceiros.pt"}
        kw = enviar.await_args.kwargs
        assert kw["to_emails"] == ["rui@parceiros.pt"] and kw["guardar_copia"] is False
        nova = next(l.split(": ", 1)[1] for l in kw["body"].splitlines() if l.startswith("Nova palavra-passe: "))
        with pytest.raises(HTTPException):
            await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))
        sessao = await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=nova))
        assert sessao["access_token"]

    async def test_a_password_nunca_vai_para_a_resposta_nem_para_o_rasto(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await self._activo(acc)
        with patch("services.email_service.send_email", _envio()) as enviar:
            r = await adm.run_reset_password(rui, MASTER)
        nova = next(l.split(": ", 1)[1] for l in enviar.await_args.kwargs["body"].splitlines()
                    if l.startswith("Nova palavra-passe: "))
        assert nova not in repr(r)
        assert nova not in repr(bd.audit_trail.docs)
        assert nova not in repr(_doc(bd, rui))

    async def test_sem_entrega_e_502_e_nada_muda(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, sessao = await self._activo(acc)
        antes = dict(_doc(bd, rui))
        with patch("services.email_service.send_email", _envio(False)):
            with pytest.raises(HTTPException) as erro:
                await adm.run_reset_password(rui, MASTER)
        assert erro.value.status_code == 502
        assert _doc(bd, rui) == antes
        assert await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=PASSWORD))

    async def test_uma_excepcao_do_envio_tambem_e_502(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await self._activo(acc)
        antes = dict(_doc(bd, rui))
        with patch("services.email_service.send_email", AsyncMock(side_effect=RuntimeError("smtp em baixo"))):
            with pytest.raises(HTTPException) as erro:
                await adm.run_reset_password(rui, MASTER)
        assert erro.value.status_code == 502 and _doc(bd, rui) == antes

    async def test_as_sessoes_abertas_caem(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm
        import services.partner_security as sec

        rui, sessao = await self._activo(acc)
        with patch("services.email_service.send_email", _envio()):
            await adm.run_reset_password(rui, MASTER)
        with pytest.raises(HTTPException) as erro:
            await sec.get_current_partner(_creds(sessao["access_token"]))
        assert erro.value.status_code == 401

    async def test_limpa_um_travao_armado(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await self._activo(acc)
        for _ in range(8):
            with pytest.raises(HTTPException):
                await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password="errada"))
        with patch("services.email_service.send_email", _envio()) as enviar:
            await adm.run_reset_password(rui, MASTER)
        nova = next(l.split(": ", 1)[1] for l in enviar.await_args.kwargs["body"].splitlines()
                    if l.startswith("Nova palavra-passe: "))
        assert await acc.run_partner_login(acc.PartnerLogin(email="rui@parceiros.pt", password=nova))

    async def test_convidado_e_suspenso_sao_409_e_nao_enviam(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        convite = await _convidar(acc, ADMIN_POWER)
        rui = convite["partner"]["id"]
        with patch("services.email_service.send_email", _envio()) as enviar:
            with pytest.raises(HTTPException) as erro:
                await adm.run_reset_password(rui, MASTER)
            assert erro.value.status_code == 409
            await _activar(acc, convite)
            _doc(bd, rui)["status"] = "suspended"
            with pytest.raises(HTTPException) as erro:
                await adm.run_reset_password(rui, MASTER)
            assert erro.value.status_code == 409
        enviar.assert_not_awaited()

    async def test_so_o_master_e_nao_envia(self, bd):
        import services.partner_accounts as acc
        import services.partner_accounts_admin as adm

        rui, _ = await self._activo(acc)
        with patch("services.email_service.send_email", _envio()) as enviar:
            with pytest.raises(HTTPException) as erro:
                await adm.run_reset_password(rui, ADMIN_POWER)
        assert erro.value.status_code == 403
        enviar.assert_not_awaited()


# ════════════════════════════════════════════════════════════════════
#  AS ROTAS
# ════════════════════════════════════════════════════════════════════
class TestAsRotas:
    SO_MASTER = {
        ("POST", "/admin/partners/{partner_id}/change-company"),
        ("POST", "/admin/partners/{partner_id}/reset-password"),
        ("DELETE", "/admin/partners/{partner_id}"),
    }

    @staticmethod
    def _guardas(rota):
        return [d.call for d in rota.dependant.dependencies if hasattr(d.call, "allowed_roles")]

    def _rotas(self):
        from routes.partners_admin import router

        return {(m, r.path): r for r in router.routes for m in r.methods}

    def test_as_tres_acoes_novas_sao_so_master(self):
        from models.auth import UserRole

        rotas = self._rotas()
        for chave in self.SO_MASTER:
            guardas = self._guardas(rotas[chave])
            assert guardas, chave
            assert tuple(guardas[0].allowed_roles) == (UserRole.MASTER,), chave

    def test_admin_e_ceo_continuam_a_gerir_o_resto(self):
        from models.auth import UserRole

        rotas = self._rotas()
        for chave in (("PATCH", "/admin/partners/{partner_id}"), ("POST", "/admin/partners/{partner_id}/resend-invite")):
            (guarda,) = self._guardas(rotas[chave])
            assert {UserRole.ADMIN, UserRole.CEO, UserRole.MASTER} <= set(guarda.allowed_roles)

    def test_o_delete_le_a_password_do_corpo_e_passa_a_ao_servico(self):
        import inspect

        import routes.partners_admin as rota

        fonte = inspect.getsource(rota.delete_partner)
        assert "ConfirmacaoPorPassword" in fonte and "data.password if data else None" in fonte
