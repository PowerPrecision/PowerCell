"""Contactos sugeridos ao escrever (Bloco 2) + associar/pesquisar emails por rede."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import email_access, email_contacts as contactos
from services import email_process_crud as crud
from services import webmail_scope
from tests.unit.helpers_tenant import (  # noqa: F401
    ANA, BRUNO, CARLA, REDE_DOMUS, REDE_INCUMBENTE, rede_de_omissao_incumbente, semear, tenant_db,
)

USER = {"id": "u-1", "email": "eu@power.pt", "role": "consultor"}
POWER, DOMUS = "cmp-power", "cmp-domus"


@pytest.fixture
def bd(fake_async_db):
    with patch.object(contactos, "db", fake_async_db), patch(
        "services.user_email_config_service.get_user_mailbox_addresses",
        AsyncMock(return_value=["eu@power.pt", "geral@power.pt"]),
    ):
        yield fake_async_db


class TestSepararContacto:
    @pytest.mark.parametrize("valor,esperado", [
        ("Ana Costa <ANA@X.pt>", ("ana@x.pt", "Ana Costa")),
        ('"Costa, Ana" <ana@x.pt>', ("ana@x.pt", "Costa, Ana")),
        ("ana@x.pt", ("ana@x.pt", "")),
        ("  ana@x.pt  ", ("ana@x.pt", "")),
    ])
    def test_formas_validas(self, valor, esperado):
        assert contactos.separar_contacto(valor) == esperado

    @pytest.mark.parametrize("valor", ["", None, "sem-arroba", "a@b", "a b@c.pt", "<>", 42, "a@b.c"])
    def test_o_que_nao_e_endereco_e_recusado(self, valor):
        assert contactos.separar_contacto(valor) == ("", "")

    def test_none_e_default_sao_a_mesma_empresa(self):
        assert {contactos.empresa_da_chave(v) for v in (None, "", "default", "None")} == {""}
        assert contactos.empresa_da_chave(POWER) == POWER


@pytest.mark.asyncio
class TestAprender:
    async def test_conta_um_uso_por_destinatario(self, bd):
        await contactos.registar_contactos_usados("u-1", POWER, ["Ana <ana@x.pt>", "rui@x.pt"])
        await contactos.registar_contactos_usados("u-1", POWER, ["ana@x.pt"])
        por_endereco = {c["address"]: c for c in bd.email_contacts.docs}
        assert por_endereco["ana@x.pt"]["use_count"] == 2
        assert por_endereco["ana@x.pt"]["name"] == "Ana"
        assert por_endereco["rui@x.pt"]["use_count"] == 1

    async def test_repetidos_no_mesmo_envio_contam_uma_vez(self, bd):
        await contactos.registar_contactos_usados("u-1", POWER, ["ana@x.pt", "ANA@x.pt", "Ana <ana@x.pt>"])
        assert bd.email_contacts.docs[0]["use_count"] == 1

    async def test_enderecos_invalidos_nao_entram(self, bd):
        assert await contactos.registar_contactos_usados("u-1", POWER, ["lixo", None, ""]) == 0
        assert bd.email_contacts.docs == []

    async def test_sem_utilizador_nao_grava(self, bd):
        assert await contactos.registar_contactos_usados("", POWER, ["a@x.pt"]) == 0

    async def test_nunca_propaga(self):
        class Quebrada:
            def __getitem__(self, _):
                raise RuntimeError("Mongo em baixo")

        with patch.object(contactos, "db", Quebrada()):
            assert await contactos.registar_contactos_usados("u-1", POWER, ["a@x.pt"]) == 0

    async def test_usar_um_contacto_escondido_traz_o_de_volta(self, bd):
        await contactos.registar_contactos_usados("u-1", POWER, ["ana@x.pt"])
        await contactos.esconder_contacto(USER, POWER, "ana@x.pt")
        assert await contactos.listar_contactos(USER, POWER) == []
        await contactos.registar_contactos_usados("u-1", POWER, ["ana@x.pt"])
        assert [c["address"] for c in await contactos.listar_contactos(USER, POWER)] == ["ana@x.pt"]


@pytest.mark.asyncio
class TestSugerir:
    async def _com(self, bd, *linhas):
        for i, (end, nome, uso, fav) in enumerate(linhas):
            bd.email_contacts.docs.append({
                "id": f"c{i}", "user_id": "u-1", "company_id": POWER, "address": end, "name": nome,
                "use_count": uso, "favorite": fav, "hidden": False, "last_used_at": f"2026-10-0{i+1}",
            })

    async def test_ordem_favoritos_depois_mais_usados_depois_recentes(self, bd):
        await self._com(bd, ("a@x.pt", "", 5, False), ("b@x.pt", "", 9, False),
                        ("c@x.pt", "", 1, True), ("d@x.pt", "", 9, False))
        res = [c["address"] for c in await contactos.listar_contactos(USER, POWER)]
        assert res == ["c@x.pt", "d@x.pt", "b@x.pt", "a@x.pt"]  # d: mesmo uso que b, mais recente

    async def test_pesquisa_por_prefixo_do_endereco_do_nome_ou_de_uma_palavra(self, bd):
        await self._com(bd, ("ana.costa@x.pt", "Ana Costa", 1, False),
                        ("rui@x.pt", "Rui da Costa", 1, False), ("zé@x.pt", "", 1, False))
        enderecos = lambda r: {c["address"] for c in r}  # noqa: E731
        assert enderecos(await contactos.listar_contactos(USER, POWER, q="ana")) == {"ana.costa@x.pt"}
        assert enderecos(await contactos.listar_contactos(USER, POWER, q="costa")) == {"ana.costa@x.pt", "rui@x.pt"}
        assert enderecos(await contactos.listar_contactos(USER, POWER, q="RU")) == {"rui@x.pt"}
        # No MEIO de uma palavra não é prefixo.
        assert await contactos.listar_contactos(USER, POWER, q="osta") == []

    async def test_os_enderecos_do_proprio_nunca_sao_sugeridos(self, bd):
        await self._com(bd, ("eu@power.pt", "Eu", 9, True), ("geral@power.pt", "Geral", 9, True),
                        ("cliente@x.pt", "", 1, False))
        assert [c["address"] for c in await contactos.listar_contactos(USER, POWER)] == ["cliente@x.pt"]

    async def test_o_limite_manda(self, bd):
        await self._com(bd, *[(f"c{i}@x.pt", "", i, False) for i in range(6)])
        assert len(await contactos.listar_contactos(USER, POWER, limite=3)) == 3
        assert len(await contactos.listar_contactos(USER, POWER, limite=10_000)) == 6

    async def test_a_carla_nao_leva_os_clientes_de_uma_ilha_para_outra(self, bd):
        """Regra 1: a chave inclui a empresa."""
        await contactos.registar_contactos_usados("u-1", DOMUS, ["cliente.domus@x.pt"])
        await contactos.registar_contactos_usados("u-1", POWER, ["cliente.power@x.pt"])
        assert [c["address"] for c in await contactos.listar_contactos(USER, POWER)] == ["cliente.power@x.pt"]
        assert [c["address"] for c in await contactos.listar_contactos(USER, DOMUS)] == ["cliente.domus@x.pt"]

    async def test_os_contactos_de_outro_utilizador_nao_aparecem(self, bd):
        await contactos.registar_contactos_usados("u-outro", POWER, ["segredo@x.pt"])
        assert await contactos.listar_contactos(USER, POWER) == []

    async def test_a_resposta_nao_traz_ids_nem_o_dono(self, bd):
        await self._com(bd, ("a@x.pt", "A", 1, False))
        assert set((await contactos.listar_contactos(USER, POWER))[0]) == {
            "address", "name", "favorite", "use_count", "last_used_at",
        }


@pytest.mark.asyncio
class TestArranqueAFrio:
    def _enviado(self, bd, para, empresa=POWER, autor="u-1", **extra):
        bd.emails.docs.append({
            "id": f"e{len(bd.emails.docs)}", "direction": "sent", "company_id": empresa,
            "created_by": autor, "to_emails": para, "sent_at": "2026-10-01", **extra,
        })

    async def test_semeia_a_partir_do_enviado_pelo_proprio_na_empresa_activa(self, bd):
        self._enviado(bd, ["Ana <ana@x.pt>"])
        self._enviado(bd, ["rui@x.pt"], cc_emails=["eu@power.pt", "paulo@x.pt"])
        res = {c["address"] for c in await contactos.listar_contactos(USER, POWER)}
        assert res == {"ana@x.pt", "rui@x.pt", "paulo@x.pt"}

    async def test_nao_semeia_com_emails_de_outra_empresa_ou_de_outro_autor(self, bd):
        self._enviado(bd, ["domus@x.pt"], empresa=DOMUS)
        self._enviado(bd, ["alheio@x.pt"], autor="u-outro")
        assert await contactos.listar_contactos(USER, POWER) == []

    async def test_sem_empresa_activa_nao_semeia(self, bd):
        """Um email sem carimbo de empresa não prova a que ilha pertence."""
        self._enviado(bd, ["ana@x.pt"], empresa="")
        self._enviado(bd, ["rui@x.pt"], empresa=None)
        assert await contactos.listar_contactos(USER, None) == []
        assert await contactos.listar_contactos(USER, "default") == []

    async def test_so_semeia_quando_nao_ha_contactos(self, bd):
        await contactos.registar_contactos_usados("u-1", POWER, ["ja@x.pt"])
        self._enviado(bd, ["novo@x.pt"])
        assert [c["address"] for c in await contactos.listar_contactos(USER, POWER)] == ["ja@x.pt"]

    async def test_o_que_o_utilizador_removeu_nao_ressuscita_com_a_semente(self, bd):
        self._enviado(bd, ["ana@x.pt"])
        await contactos.listar_contactos(USER, POWER)
        await contactos.esconder_contacto(USER, POWER, "ana@x.pt")
        assert await contactos.listar_contactos(USER, POWER) == []


@pytest.mark.asyncio
class TestGerir:
    async def test_criar_e_marcar_favorito(self, bd):
        r = await contactos.guardar_contacto(USER, POWER, address="Ana <ana@x.pt>", favorite=True)
        assert r == {"address": "ana@x.pt", "name": "Ana", "favorite": True, "use_count": 0}

    async def test_renomear_nao_perde_os_usos(self, bd):
        await contactos.registar_contactos_usados("u-1", POWER, ["ana@x.pt"])
        r = await contactos.guardar_contacto(USER, POWER, address="ana@x.pt", name="Ana Costa")
        assert r["name"] == "Ana Costa" and r["use_count"] == 1

    async def test_endereco_invalido_levanta(self, bd):
        with pytest.raises(ValueError):
            await contactos.guardar_contacto(USER, POWER, address="lixo")

    async def test_esconder_inexistente_devolve_false(self, bd):
        assert await contactos.esconder_contacto(USER, POWER, "nao@x.pt") is False
        assert await contactos.esconder_contacto(USER, POWER, "lixo") is False

    async def test_esconder_tira_o_favorito(self, bd):
        await contactos.guardar_contacto(USER, POWER, address="ana@x.pt", favorite=True)
        await contactos.esconder_contacto(USER, POWER, "ana@x.pt")
        assert bd.email_contacts.docs[0]["favorite"] is False


class TestALigacao:
    def test_aprende_no_envio_REAL_e_nao_ao_pedir_o_envio(self):
        """Depois de enviado e antes de apagar o pendente; nunca ao cancelar."""
        from services import email_send_queue
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        executar = codigo_da_funcao_sem_comentarios(email_send_queue.execute_pending_email_send)
        assert executar.index("send_email(") < executar.index("registar_contactos_usados(")
        assert executar.index("registar_contactos_usados(") < executar.index("delete_one(")
        for nome in ("cancel_pending_email_send", "build_pending_send_record"):
            assert "registar_contactos_usados" not in codigo_da_funcao_sem_comentarios(
                getattr(email_send_queue, nome)
            )

    def test_as_rotas_de_contactos_vem_antes_de_email_id(self):
        """`/contacts` depois de `/{email_id}` seria engolido por ele."""
        from routes import emails

        caminhos = [(r.path, sorted(r.methods)) for r in emails.router.routes]
        pos_dinamica = min(i for i, (p, m) in enumerate(caminhos) if p.endswith("/{email_id}") and "GET" in m)
        for i, (p, _) in enumerate(caminhos):
            if p.endswith("/contacts"):
                assert i < pos_dinamica, p


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.processes.docs.append({
        "id": "p-ix", "client_name": "Ana", "status": "novo", "is_indexed": True,
        "company_id": POWER, "network_id": REDE_INCUMBENTE,
    })
    fake_async_db.processes.docs.append({
        "id": "p-ix-domus", "client_name": "Rui", "status": "novo", "is_indexed": True,
        "company_id": DOMUS, "network_id": REDE_DOMUS,
    })
    fake_async_db.emails.docs.extend([
        {"id": "e-power", "company_id": POWER, "from_email": "cli@x.pt", "to_emails": ["a@power.pt"],
         "subject": "a.b contrato", "body": "texto", "synced_for_user": "u-outro"},
        {"id": "e-axb", "company_id": POWER, "from_email": "cli@x.pt", "to_emails": ["a@power.pt"],
         "subject": "axb contrato", "body": "texto", "synced_for_user": "u-outro"},
    ])
    return fake_async_db


@pytest.mark.asyncio
class TestAssociarEPesquisarPorRede:
    async def test_o_diretor_de_uma_ilha_nao_associa_um_email_alheio(self, mundo):
        with tenant_db(mundo, email_access, webmail_scope), patch.object(crud, "db", mundo), \
                patch.object(email_access, "db", mundo), patch("services.document_visibility.db", mundo), \
                patch("services.user_email_config_service.get_user_mailbox_addresses", AsyncMock(return_value=[])):
            with pytest.raises(HTTPException) as exc:
                await crud.run_associate_email_to_client({"email_id": "e-power", "process_id": "p-ix"}, BRUNO)
        assert exc.value.status_code == 403

    async def test_ler_o_email_nao_basta_o_processo_tambem_tem_de_ser_visivel(self, mundo):
        """A Ana lê o email da Power, mas o processo é da Domus."""
        with tenant_db(mundo, email_access, webmail_scope), patch.object(crud, "db", mundo), \
                patch.object(email_access, "db", mundo), patch("services.document_visibility.db", mundo), \
                patch("services.user_email_config_service.get_user_mailbox_addresses", AsyncMock(return_value=[])):
            with pytest.raises(HTTPException) as exc:
                await crud.run_associate_email_to_client({"email_id": "e-power", "process_id": "p-ix-domus"}, ANA)
        assert exc.value.status_code == 403
        assert "process_id" not in next(e for e in mundo.emails.docs if e["id"] == "e-power")

    async def test_o_diretor_da_casa_associa(self, mundo):
        with tenant_db(mundo, email_access, webmail_scope), patch.object(crud, "db", mundo), \
                patch.object(email_access, "db", mundo), patch("services.document_visibility.db", mundo), \
                patch("services.user_email_config_service.get_user_mailbox_addresses", AsyncMock(return_value=[])):
            res = await crud.run_associate_email_to_client({"email_id": "e-power", "process_id": "p-ix"}, ANA)
        assert res["success"] is True

    async def test_a_pesquisa_do_diretor_de_uma_ilha_nao_traz_emails_de_outra_rede(self, mundo):
        with tenant_db(mundo, email_access, webmail_scope), patch.object(crud, "db", mundo), \
                patch.object(webmail_scope, "db", mundo), \
                patch.object(crud, "enrich_emails", AsyncMock(side_effect=lambda e: e)):
            res = await crud.run_search_emails("contrato", BRUNO)
        assert res["emails"] == []

    async def test_a_pesquisa_do_diretor_da_casa_traz_os_da_sua_empresa(self, mundo):
        with tenant_db(mundo, email_access, webmail_scope), patch.object(crud, "db", mundo), \
                patch.object(webmail_scope, "db", mundo), \
                patch.object(crud, "enrich_emails", AsyncMock(side_effect=lambda e: e)):
            res = await crud.run_search_emails("contrato", ANA)
        assert {e["id"] for e in res["emails"]} == {"e-power", "e-axb"}

    async def test_o_termo_nao_e_uma_expressao_regular(self, mundo):
        admin = {"id": "u-adm", "email": "a@x.pt", "role": "admin"}
        with patch.object(crud, "db", mundo), patch.object(crud, "enrich_emails", AsyncMock(side_effect=lambda e: e)):
            res = await crud.run_search_emails("a.b", admin)
        assert [e["id"] for e in res["emails"]] == ["e-power"]
