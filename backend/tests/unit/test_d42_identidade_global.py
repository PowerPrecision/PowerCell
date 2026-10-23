"""
D-42/D-40 — NIF e Email definem o cliente ÚNICO, em TODA a base de dados.

(Este ficheiro nasceu como `test_d38_duplicados_por_rede.py`: a regra era «NIF, Email e
Telemóvel não se repetem dentro da rede». Os testes que a afirmavam foram INVERTIDOS, não
apagados — ver o `worklog.md`.)

A DECISÃO DA DIRECÇÃO
  * O telemóvel NÃO é critério de unicidade.
  * O cliente (NIF/Email) é uma entidade global; pode ter processos em redes diferentes, e a
    segregação do CRM mantém-se (cada equipa só vê o seu processo — `client_window`).

O QUE SE GARANTE
  1. Registo público: NIF/Email já usado — em QUALQUER rede — dá 409 genérico (sem id, nome nem
     campo) e NÃO cria nem altera nada. Um telemóvel repetido já não trava.
  2. Criação no CRM: o cliente de outra rede só se ASSOCIA com a prova de NIF **e** Email do
     MESMO cliente; com menos que isso é o 409 opaco. Associar acrescenta a rede e mais nada, e
     a resposta nunca devolve a ficha. Um cliente da própria rede ganha sempre (409 com o nome).
  3. Edição: só se verifica o que MUDOU; o de outra rede é opaco, o da mesma rede é nomeado.
  4. Eliminados não bloqueiam.
"""
from __future__ import annotations

import ast
import inspect
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

MENSAGEM = "Já existe um registo associado a este NIF ou Email."


# ====================================================================
# 1. HELPERS PUROS
# ====================================================================

class TestHelpersPuros:
    def test_telefones_candidatos_continua_a_existir_para_o_contacto(self):
        """Já não identifica ninguém, mas o B2B ainda compara contactos (`campos_divergentes`)."""
        from services.client_uniqueness import telefones_candidatos

        assert telefones_candidatos("912 345 678") == ["912345678", "351912345678"]
        assert telefones_candidatos("12345") == []

    def test_condicoes_levam_so_nif_e_email_com_hash_e_claro(self):
        from services.client_uniqueness import construir_condicoes_de_duplicado

        condicoes = construir_condicoes_de_duplicado("285739461", "A@B.pt")
        chaves = {k for c in condicoes for k in c}
        assert chaves == {
            "dados_pessoais.nif_hash", "dados_pessoais.nif",
            "contacto.email_hash", "contacto.email",
        }

    def test_o_telemovel_nao_entra_nas_condicoes(self):
        """A mutação que o devolve às condições quebra este teste."""
        import inspect as _inspect

        from services.client_uniqueness import construir_condicoes_de_duplicado

        assert "telefone" not in _inspect.signature(construir_condicoes_de_duplicado).parameters
        assert not any("telefone" in k for c in construir_condicoes_de_duplicado("285739461", "a@b.pt") for k in c)

    def test_sem_valores_nao_ha_condicoes(self):
        from services.client_uniqueness import construir_condicoes_de_duplicado

        assert construir_condicoes_de_duplicado(None, "") == []

    def test_erro_publico_e_generico(self):
        from services.client_uniqueness import erro_publico_de_duplicado

        corpo = erro_publico_de_duplicado()
        assert corpo == {"success": False, "code": "DUPLICATE_CLIENT", "detail": MENSAGEM}
        assert not {"existing_client_id", "existing_client_name", "matched_fields", "client_id"} & set(corpo)

    def test_erro_opaco_da_equipa_nao_tem_id_nem_nome_nem_campos(self):
        from services.client_uniqueness import erro_opaco_de_duplicado

        exc = erro_opaco_de_duplicado()
        assert exc.status_code == 409
        assert exc.detail == {"message": MENSAGEM, "code": "DUPLICATE_CLIENT"}

    def test_so_o_que_mudou_ignora_o_que_o_cliente_ja_tem(self):
        from services.client_uniqueness import so_o_que_mudou
        from services.encryption import generate_email_hash, generate_nif_hash

        cliente = {
            "dados_pessoais": {"nif_hash": generate_nif_hash("285739461")},
            "contacto": {"email_hash": generate_email_hash("a@b.pt")},
        }
        assert so_o_que_mudou(cliente, "285739461", "A@B.pt") == (None, None)
        assert so_o_que_mudou(cliente, "987654321", "novo@b.pt") == ("987654321", "novo@b.pt")

    def test_so_o_que_mudou_reconhece_valores_em_claro(self):
        from services.client_uniqueness import so_o_que_mudou

        cliente = {"dados_pessoais": {"nif": "285739461"}, "contacto": {"email": "a@b.pt"}}
        assert so_o_que_mudou(cliente, "285739461", "a@b.pt") == (None, None)


# ====================================================================
# 2. REGISTO PÚBLICO — 409 e nada é tocado
# ====================================================================

@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.alert_audience as audiencia
    import services.alerts as alertas
    import services.client_uniqueness as cu
    import services.form_config_scope as fcs
    import services.public_registration as pr

    semear(fake_async_db)
    s3 = MagicMock()
    s3.initialize_client_folders = MagicMock(return_value=(True, "Documentação Clientes/x"))

    with tenant_db(fake_async_db, pr, alertas, audiencia, fcs, cu), \
            patch.object(pr, "s3_service", s3), \
            patch.object(pr, "spawn_background_task", lambda coro, **k: coro.close()), \
            patch.object(pr, "send_new_client_notification", AsyncMock()), \
            patch("services.push_notifications.send_push_notification", AsyncMock()), \
            patch("services.portal_documents_notify.generate_mandatory_document_requests", AsyncMock()), \
            patch("asyncio.create_task", lambda c, **k: c.close()):
        yield MagicMock(pr=pr, bd=fake_async_db)


def _pedido():
    return MagicMock(headers={}, state=MagicMock(spec=[]))


def _dados(**extra):
    from models.process import PublicClientRegistration

    base = dict(name="Maria Teste", email="maria@teste.pt", phone="912345678", process_type="credito_habitacao")
    base.update(extra)
    return PublicClientRegistration(**base)


def _publicos(bd):
    return [c for c in bd.clients.docs if c.get("fonte") == "public_form"]


def _existente(bd, rede=REDE_INCUMBENTE, **campos):
    """Um cliente já registado (campos em claro e com blind index)."""
    from services.encryption import generate_email_hash, generate_nif_hash, generate_telefone_hash

    email = campos.pop("email", "outro@x.pt")
    telefone = campos.pop("telefone", "900000001")
    nif = campos.pop("nif", "100000001")
    doc = {
        "id": campos.pop("id", f"c-ex-{len(bd.clients.docs)}"),
        "nome": "Pessoa Original",
        "fonte": "public_form",
        "lead_status": "converted",
        "contacto": {
            "email": email, "email_hash": generate_email_hash(email),
            "telefone": telefone, "telefone_hash": generate_telefone_hash(telefone),
        },
        "dados_pessoais": {"nif": nif, "nif_hash": generate_nif_hash(nif)},
        **campos,
    }
    if rede:
        doc["network_id"] = rede
        doc["company_id"] = "cmp-domus" if rede == REDE_DOMUS else "cmp-power"
    bd.clients.docs.append(doc)
    return doc


def _foto(bd):
    return json.dumps(bd.clients.docs, sort_keys=True, default=str)


class TestRegistoPublicoBloqueiaDuplicados:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "campo,existente,submetido",
        [
            ("email", {"email": "maria@teste.pt"}, {}),
            ("email com maiúsculas", {"email": "maria@teste.pt"}, {"email": "MARIA@Teste.pt"}),
            (
                "nif",
                {"nif": "285739461"},
                {"email": "nova@teste.pt", "phone": "933333333", "personal_data": {"nif": "285739461"}},
            ),
        ],
    )
    @pytest.mark.parametrize("rede_do_cliente_existente", [REDE_INCUMBENTE, REDE_DOMUS])
    async def test_campo_repetido_em_qualquer_rede_da_409(
        self, mundo, campo, existente, submetido, rede_do_cliente_existente,
    ):
        """A identidade é GLOBAL: o cliente existe numa rede, o link é da outra, e é 409 na mesma."""
        _existente(mundo.bd, rede_do_cliente_existente, **existente)
        antes = _foto(mundo.bd)

        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power", **submetido))

        assert r.status_code == 409, campo
        assert json.loads(r.body) == {"success": False, "code": "DUPLICATE_CLIENT", "detail": MENSAGEM}
        assert _foto(mundo.bd) == antes, "nem criou nem alterou nada"

    @pytest.mark.asyncio
    async def test_um_telemovel_repetido_ja_nao_trava_o_registo(self, mundo):
        """INVERTIDO (era 409 no D-38): o telemóvel partilha-se — família, casal, escritório."""
        _existente(mundo.bd, REDE_INCUMBENTE, telefone="912345678")
        r = await mundo.pr.run_public_client_registration(
            _pedido(), _dados(empresa_id="cmp-power", email="nova@teste.pt", phone="+351 912 345 678"),
        )
        assert r.status_code == 200
        assert len([c for c in _publicos(mundo.bd) if c["contacto"]["email"] == "nova@teste.pt"]) == 1

    @pytest.mark.asyncio
    async def test_a_resposta_nao_revela_quem_nem_qual_campo(self, mundo):
        original = _existente(mundo.bd, REDE_INCUMBENTE, email="maria@teste.pt")
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        texto = r.body.decode()
        assert original["id"] not in texto and original["nome"] not in texto
        for proibido in ("existing_client", "matched_fields", "client_id", "is_new_client"):
            assert proibido not in texto

    @pytest.mark.asyncio
    async def test_o_cliente_existente_nao_e_re_marcado_como_lead(self, mundo):
        original = _existente(mundo.bd, REDE_INCUMBENTE, email="maria@teste.pt")
        await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power", name="Outro Nome"))
        intacto = next(c for c in mundo.bd.clients.docs if c["id"] == original["id"])
        assert intacto["lead_status"] == "converted"
        assert intacto["nome"] == "Pessoa Original"

    @pytest.mark.asyncio
    async def test_a_pilha_por_carimbar_conta(self, mundo):
        _existente(mundo.bd, None, email="maria@teste.pt")
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_a_pilha_por_carimbar_bloqueia_tambem_uma_ilha(self, mundo):
        """INVERTIDO (era 200): a identidade é global, a ilha da Domus não escapa à unicidade."""
        _existente(mundo.bd, None, email="maria@teste.pt")
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_cliente_eliminado_nao_bloqueia(self, mundo):
        _existente(mundo.bd, REDE_INCUMBENTE, email="maria@teste.pt", is_deleted=True, status="eliminado")
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_dados_novos_e_distintos_criam_o_cliente(self, mundo):
        _existente(mundo.bd, REDE_INCUMBENTE)
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert r.status_code == 200
        assert len([c for c in _publicos(mundo.bd) if c["contacto"]["email"] == "maria@teste.pt"]) == 1

    @pytest.mark.asyncio
    async def test_a_corrida_que_o_indice_unico_apanha_tambem_e_409(self, mundo):
        """Dois pedidos ao mesmo tempo: a procura não vê o outro, o índice único sim."""
        from pymongo.errors import DuplicateKeyError

        async def rebenta(_doc):
            raise DuplicateKeyError("E11000 duplicate key")

        with patch.object(mundo.bd.clients, "insert_one", rebenta):
            r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert r.status_code == 409
        assert json.loads(r.body)["code"] == "DUPLICATE_CLIENT"


# ====================================================================
# 3. CRIAÇÃO NO CRM
# ====================================================================

USER_POWER = {"id": "u-ana", "email": "ana@power.pt", "role": "diretor", "active_company_id": "cmp-power"}
USER_DOMUS = {"id": "u-bruno", "email": "bruno@domus.pt", "role": "diretor", "active_company_id": "cmp-domus"}


class TestCriacaoNoCrm:
    async def _criar(self, bd, *, email="nova@x.pt", nif=None, telefone=None, user=None, nome="Nova Pessoa"):
        from models.client import ClientCreate
        from services import client_crud as mod
        from services import client_uniqueness as cu

        payload = ClientCreate(nome=nome, email=email, nif=nif, telefone=telefone, fonte="staff_created")
        with tenant_db(bd, mod, cu), \
                patch.object(mod, "encrypt_client_data", lambda d: d), \
                patch.object(mod, "decrypt_client_data", lambda d: d), \
                patch.object(mod, "s3_service", MagicMock()), \
                patch.object(mod, "_send_portal_welcome_email_safe", AsyncMock()):
            return await mod.run_create_client(payload, user or USER_POWER)

    @pytest.mark.asyncio
    async def test_telefone_repetido_ja_nao_da_409(self, fake_async_db, rede_de_omissao_incumbente):
        """INVERTIDO (era 409 no D-38)."""
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-tel", telefone="912345678")
        cliente = await self._criar(fake_async_db, telefone="+351 912 345 678")
        assert cliente.id != "c-tel"

    @pytest.mark.asyncio
    async def test_nif_repetido_na_mesma_rede_da_409_com_o_cliente(self, fake_async_db, rede_de_omissao_incumbente):
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-nif", nif="285739461")
        with pytest.raises(HTTPException) as exc:
            await self._criar(fake_async_db, nif="285739461")
        assert exc.value.status_code == 409
        assert exc.value.detail["matched_fields"] == ["nif"]
        assert exc.value.detail["existing_client_id"] == "c-nif"

    @pytest.mark.asyncio
    async def test_a_domus_com_nif_e_email_de_um_cliente_da_power_associa_sem_o_ver(
        self, fake_async_db, rede_de_omissao_incumbente,
    ):
        """O caso do D-42: a mesma pessoa, outra empresa. Uma ficha; a Domus ganha a janela, não o documento."""
        semear(fake_async_db)
        original = _existente(fake_async_db, REDE_INCUMBENTE, id="c-orig", nif="285739461", email="x@power.pt")
        antes = json.loads(json.dumps(original, default=str))

        resposta = await self._criar(
            fake_async_db, nif="285739461", email="x@power.pt", nome="Nome Que A Domus Escreveu",
            user=USER_DOMUS,
        )

        assert resposta.id == "c-orig", "é o MESMO cliente, não um segundo"
        # a resposta só tem o que a Domus escreveu — nunca o nome, o código do Portal ou os dados da Power
        assert resposta.nome == "Nome Que A Domus Escreveu"
        assert resposta.portal_access_code is None
        assert resposta.process_ids == []
        # nenhum segundo cliente nasceu
        assert len([c for c in fake_async_db.clients.docs if c.get("nif_dup") or c["id"] != "c-orig" and
                    c.get("contacto", {}).get("email") == "x@power.pt"]) == 0
        # o documento da Power só ganhou a rede associada
        depois = next(c for c in fake_async_db.clients.docs if c["id"] == "c-orig")
        assert depois.pop("redes_associadas") == [REDE_DOMUS]
        assert depois == antes

    @pytest.mark.asyncio
    async def test_associar_duas_vezes_nao_repete_a_rede(self, fake_async_db, rede_de_omissao_incumbente):
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-orig", nif="285739461", email="x@power.pt")
        for _ in range(2):
            await self._criar(fake_async_db, nif="285739461", email="x@power.pt", user=USER_DOMUS)
        depois = next(c for c in fake_async_db.clients.docs if c["id"] == "c-orig")
        assert depois["redes_associadas"] == [REDE_DOMUS]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "submetido",
        [
            {"nif": "285739461", "email": "outro@x.pt"},          # só o NIF coincide
            {"nif": "999999990", "email": "x@power.pt"},          # só o Email coincide
        ],
    )
    async def test_sem_a_prova_dos_dois_campos_a_resposta_e_opaca(
        self, fake_async_db, rede_de_omissao_incumbente, submetido,
    ):
        """Um NIF sozinho nunca abre a ficha de outra rede — e a resposta não diz de quem é."""
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-orig", nif="285739461", email="x@power.pt")
        antes = _foto(type("B", (), {"clients": fake_async_db.clients}))
        with pytest.raises(HTTPException) as exc:
            await self._criar(fake_async_db, nif=submetido["nif"], email=submetido["email"], user=USER_DOMUS)
        assert exc.value.status_code == 409
        assert set(exc.value.detail) == {"message", "code"}, "sem id, sem nome, sem campos"
        assert "c-orig" not in json.dumps(exc.value.detail)
        assert _foto(type("B", (), {"clients": fake_async_db.clients})) == antes, "nada foi escrito"

    @pytest.mark.asyncio
    async def test_dois_clientes_diferentes_de_outra_rede_nao_dao_prova(self, fake_async_db, rede_de_omissao_incumbente):
        """O NIF é de um cliente e o Email de outro: não há «o mesmo cliente» a provar."""
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-1", nif="285739461", email="um@power.pt")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-2", nif="100000099", email="dois@power.pt")
        with pytest.raises(HTTPException) as exc:
            await self._criar(fake_async_db, nif="285739461", email="dois@power.pt", user=USER_DOMUS)
        assert set(exc.value.detail) == {"message", "code"}

    @pytest.mark.asyncio
    async def test_um_duplicado_legado_torna_a_prova_ambigua(self, fake_async_db, rede_de_omissao_incumbente):
        """Dois clientes de outra rede já partilham o email (a base é antiga): quem pede prova conhecer
        UM deles, mas não se sabe QUAL é a pessoa — não se escolhe por ele."""
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-1", nif="285739461", email="casal@power.pt")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-2", nif="100000099", email="casal@power.pt")
        with pytest.raises(HTTPException) as exc:
            await self._criar(fake_async_db, nif="285739461", email="casal@power.pt", user=USER_DOMUS)
        assert set(exc.value.detail) == {"message", "code"}
        assert not any("redes_associadas" in c for c in fake_async_db.clients.docs)

    @pytest.mark.asyncio
    async def test_o_da_propria_rede_ganha_a_um_de_outra_rede(self, fake_async_db, rede_de_omissao_incumbente):
        """Se a equipa já vê um cliente com aquele NIF, é esse que lhe é mostrado — nunca o alheio."""
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_DOMUS, id="c-domus-meu", nif="285739461", email="a@domus.pt")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-orig", nif="111222333", email="x@power.pt")
        with pytest.raises(HTTPException) as exc:
            await self._criar(fake_async_db, nif="285739461", email="x@power.pt", user=USER_DOMUS)
        assert exc.value.detail["existing_client_id"] == "c-domus-meu"

    @pytest.mark.asyncio
    async def test_cliente_eliminado_nao_bloqueia_nem_se_associa(self, fake_async_db, rede_de_omissao_incumbente):
        semear(fake_async_db)
        _existente(
            fake_async_db, REDE_INCUMBENTE, id="c-velho", nif="285739461", email="x@power.pt",
            is_deleted=True, status="eliminado",
        )
        cliente = await self._criar(fake_async_db, nif="285739461", email="x@power.pt", user=USER_DOMUS)
        assert cliente.id != "c-velho"

    @pytest.mark.asyncio
    async def test_dados_distintos_criam_normalmente(self, fake_async_db, rede_de_omissao_incumbente):
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE)
        cliente = await self._criar(fake_async_db, telefone="966666666", nif="555666777")
        assert cliente.id

    @pytest.mark.asyncio
    async def test_a_corrida_do_indice_unico_na_criacao_e_409_opaco(self, fake_async_db, rede_de_omissao_incumbente):
        from fastapi import HTTPException
        from pymongo.errors import DuplicateKeyError

        semear(fake_async_db)

        async def rebenta(_doc):
            raise DuplicateKeyError("E11000")

        with patch.object(fake_async_db.clients, "insert_one", rebenta):
            with pytest.raises(HTTPException) as exc:
                await self._criar(fake_async_db, nif="555666777")
        assert exc.value.status_code == 409 and set(exc.value.detail) == {"message", "code"}


# ====================================================================
# 4. EDIÇÃO NO CRM
# ====================================================================

class TestEdicaoNoCrm:
    async def _editar(self, bd, client_id, **contacto):
        from models.client import ClientUpdate
        from services import client_crud as mod
        from services import client_uniqueness as cu

        dados = ClientUpdate(contacto=contacto) if contacto else ClientUpdate(nome="Outro Nome")
        with tenant_db(bd, mod, cu), \
                patch.object(mod, "encrypt_client_data", lambda d: d), \
                patch.object(mod, "decrypt_client_data", lambda d: d), \
                patch.object(mod, "s3_service", MagicMock()):
            return await mod.run_update_client(client_id, dados, MagicMock(headers={}, json=AsyncMock(return_value={})), USER_POWER)

    @pytest.mark.asyncio
    async def test_mudar_para_o_email_de_outro_da_mesma_rede_da_409_com_o_cliente(
        self, fake_async_db, rede_de_omissao_incumbente,
    ):
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-a", email="a@x.pt", nif="100000011")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-b", email="b@x.pt", nif="100000012")
        with pytest.raises(HTTPException) as exc:
            await self._editar(fake_async_db, "c-b", email="a@x.pt")
        assert exc.value.status_code == 409
        assert exc.value.detail["existing_client_id"] == "c-a"
        assert exc.value.detail["matched_fields"] == ["email"]

    @pytest.mark.asyncio
    async def test_mudar_para_o_email_de_um_cliente_de_outra_rede_da_409_opaco(
        self, fake_async_db, rede_de_omissao_incumbente,
    ):
        """A identidade é global: a edição não consegue fabricar o duplicado, e não diz de quem é."""
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_DOMUS, id="c-d", email="d@x.pt", nif="100000013")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-p", email="p@x.pt", nif="100000014")
        with pytest.raises(HTTPException) as exc:
            await self._editar(fake_async_db, "c-p", email="d@x.pt")
        assert exc.value.status_code == 409
        assert set(exc.value.detail) == {"message", "code"}
        assert "c-d" not in json.dumps(exc.value.detail)

    @pytest.mark.asyncio
    async def test_mudar_o_telefone_para_o_de_outro_ja_nao_trava(self, fake_async_db, rede_de_omissao_incumbente):
        """INVERTIDO (era 409 no D-38)."""
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-a", telefone="911111111", email="a@x.pt", nif="100000011")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-b", telefone="922222222", email="b@x.pt", nif="100000012")
        await self._editar(fake_async_db, "c-b", telefone="911111111")

    @pytest.mark.asyncio
    async def test_gravar_o_proprio_email_nao_trava(self, fake_async_db, rede_de_omissao_incumbente):
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-a", telefone="911111111", email="a@x.pt")
        await self._editar(fake_async_db, "c-a", telefone="911111111", email="a@x.pt")

    @pytest.mark.asyncio
    async def test_duplicado_legado_em_que_nao_se_tocou_nao_trava_a_edicao(self, fake_async_db, rede_de_omissao_incumbente):
        """A regra é nova e a base é antiga: dois clientes já partilham o email."""
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-a", email="mesmo@x.pt", nif="100000011")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-b", email="mesmo@x.pt", nif="100000012")
        await self._editar(fake_async_db, "c-b", email="mesmo@x.pt")
        await self._editar(fake_async_db, "c-b")


# ====================================================================
# 5. GUARDAS SOBRE O CÓDIGO
# ====================================================================

#: Os escritores de `db.clients.insert_one` que NÃO passam pela guarda de
#: unicidade, cada um com o motivo. Um escritor novo falha o teste.
ESCRITORES_SEM_GUARDA = {
    "admin_proc_migration_helpers.py": "migração: cria um cliente por cada processo legado, a partir de dados já existentes",
    "admin_dev_ops.py": "semeador de desenvolvimento do painel de administração",
    "admin_proc_migration_api.py": "reversão de migração: repõe a cópia de segurança da colecção inteira",
    "partner_drafts.py": "liberta a lead retida do parceiro: a associação/retenção por identidade global vive em b2b_client_match (test_b2b_colisao_de_cliente, test_d42_*)",
}

#: Escritores que passam por `assert_cliente_unico` / `encontrar_cliente_duplicado`.
ESCRITORES_COM_GUARDA = {"client_crud.py", "public_registration.py"}


def _escritores_de_clientes():
    raiz = pathlib.Path(__file__).resolve().parents[2] / "services"
    encontrados = {}
    for ficheiro in raiz.glob("*.py"):
        arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr in {"insert_one", "insert_many"}
                and ast.unparse(no.func.value).endswith("clients")
                and "partner" not in ast.unparse(no.func.value)
            ):
                encontrados.setdefault(ficheiro.name, []).append(no.lineno)
    return encontrados


class TestGuardas:
    def test_inventario_dos_escritores_de_clientes(self):
        conhecidos = ESCRITORES_COM_GUARDA | set(ESCRITORES_SEM_GUARDA)
        novos = set(_escritores_de_clientes()) - conhecidos
        assert not novos, (
            f"Escritor(es) novo(s) de db.clients sem decisão sobre unicidade: {sorted(novos)}. "
            "Ligue-o a client_uniqueness ou acrescente-o a ESCRITORES_SEM_GUARDA com o motivo."
        )

    def test_contraprova_o_inventario_ve_os_escritores_conhecidos(self):
        encontrados = _escritores_de_clientes()
        assert ESCRITORES_COM_GUARDA <= set(encontrados), encontrados

    def test_os_escritores_com_guarda_chamam_a_guarda(self):
        import services.client_crud as crud
        import services.public_registration as pr

        for modulo, nome in (
            (crud, "resolver_identidade"), (crud, "assert_cliente_unico"), (pr, "encontrar_cliente_duplicado"),
        ):
            arvore = ast.parse(inspect.getsource(modulo))
            chamadas = [n for n in ast.walk(arvore) if isinstance(n, ast.Call) and ast.unparse(n.func) == nome]
            assert chamadas, f"{modulo.__name__} deixou de chamar {nome}"

    def test_a_criacao_e_a_edicao_dizem_a_rede_e_o_registo_publico_nao(self):
        """A rede decide o que se DIZ (nomear ou ser opaco); a procura é global. O registo público é
        anónimo: nunca nomeia, logo não tem rede a passar."""
        import services.client_crud as crud
        import services.public_registration as pr

        for nome in ("resolver_identidade", "assert_cliente_unico"):
            chamadas = [
                n for n in ast.walk(ast.parse(inspect.getsource(crud)))
                if isinstance(n, ast.Call) and ast.unparse(n.func) == nome
            ]
            assert all("rede" in {k.arg for k in c.keywords} for c in chamadas), nome
        publicas = [
            n for n in ast.walk(ast.parse(inspect.getsource(pr)))
            if isinstance(n, ast.Call) and ast.unparse(n.func) == "encontrar_cliente_duplicado"
        ]
        assert publicas and all("rede" not in {k.arg for k in c.keywords} for c in publicas)

    def test_a_edicao_so_verifica_o_que_mudou(self):
        import services.client_crud as crud

        fonte = inspect.getsource(crud.run_update_client)
        assert "so_o_que_mudou" in fonte
        assert "excluir_id=client_id" in fonte

    def test_a_procura_de_duplicados_e_global(self):
        """A mutação que lhe volta a pôr o âmbito de rede quebra o D-42."""
        import services.client_uniqueness as cu

        for funcao in (cu.encontrar_clientes_duplicados, cu.encontrar_cliente_duplicado):
            fonte = inspect.getsource(funcao)
            assert "condicao_de_unicidade" not in fonte and "com_isolamento" not in fonte, funcao.__name__
        assert "rede" not in inspect.signature(cu.encontrar_cliente_duplicado).parameters

    def test_os_campos_unicos_sao_nif_e_email(self):
        from services.client_uniqueness import CAMPOS_UNICOS

        assert CAMPOS_UNICOS == ("nif", "email")
