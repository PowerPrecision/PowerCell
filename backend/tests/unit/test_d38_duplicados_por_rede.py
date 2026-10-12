"""
D-38 — NIF, Email e Telemóvel não se repetem DENTRO DA REDE.

O QUE ESTAVA ERRADO
  * O formulário PÚBLICO «reaproveitava» o cliente existente: um anónimo
    actualizava em silêncio os dados de quem já estava registado.
  * A criação no CRM verificava NIF e email (nunca o telemóvel) numa procura
    GLOBAL, e o 409 devolvia o `id` e o nome do cliente — de qualquer rede.
  * A edição só verificava NIF e email.

O QUE SE GARANTE
  1. Registo público: um NIF/Email/Telemóvel já usado na rede do link dá 409
     genérico (sem id, nome nem campo) e NÃO cria nem altera nada.
  2. A mesma pessoa noutra rede continua a ser um cliente novo (D-32).
  3. Criação no CRM: 409 estruturado com `matched_fields` (incl. «telefone»),
     só dentro da rede de destino.
  4. Edição: só se verifica o que MUDOU; o próprio cliente e um duplicado
     legado em que não se tocou nunca travam.
  5. Eliminados não bloqueiam; um telefone com menos de 9 dígitos não
     identifica ninguém.
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

MENSAGEM = "Já existe um registo associado a este NIF, Email ou Telemóvel."


# ====================================================================
# 1. HELPERS PUROS
# ====================================================================

class TestHelpersPuros:
    def test_telefones_candidatos_cobre_com_e_sem_indicativo(self):
        from services.client_uniqueness import telefones_candidatos

        assert telefones_candidatos("912 345 678") == ["912345678", "351912345678"]
        assert telefones_candidatos("+351 912 345 678") == ["912345678", "351912345678"]
        assert telefones_candidatos("00351912345678") == ["912345678", "351912345678"]

    @pytest.mark.parametrize("valor", [None, "", "  ", "12345", "abc", "+351 91"])
    def test_telefone_curto_ou_vazio_nao_identifica_ninguem(self, valor):
        from services.client_uniqueness import telefones_candidatos

        assert telefones_candidatos(valor) == []

    def test_condicoes_levam_os_tres_campos_com_hash_e_claro(self):
        from services.client_uniqueness import construir_condicoes_de_duplicado

        condicoes = construir_condicoes_de_duplicado("285739461", "A@B.pt", "912345678")
        chaves = {k for c in condicoes for k in c}
        assert {
            "dados_pessoais.nif_hash", "dados_pessoais.nif",
            "contacto.email_hash", "contacto.email",
            "contacto.telefone_hash", "contacto.telefone",
        } <= chaves

    def test_sem_valores_nao_ha_condicoes(self):
        from services.client_uniqueness import construir_condicoes_de_duplicado

        assert construir_condicoes_de_duplicado(None, "", "123") == []

    def test_erro_publico_e_generico(self):
        from services.client_uniqueness import erro_publico_de_duplicado

        corpo = erro_publico_de_duplicado()
        assert corpo == {"success": False, "code": "DUPLICATE_CLIENT", "detail": MENSAGEM}
        assert not {"existing_client_id", "existing_client_name", "matched_fields", "client_id"} & set(corpo)

    def test_so_o_que_mudou_ignora_o_que_o_cliente_ja_tem(self):
        from services.client_uniqueness import so_o_que_mudou
        from services.encryption import generate_email_hash, generate_nif_hash, generate_telefone_hash

        cliente = {
            "dados_pessoais": {"nif_hash": generate_nif_hash("285739461")},
            "contacto": {
                "email_hash": generate_email_hash("a@b.pt"),
                "telefone_hash": generate_telefone_hash("912345678"),
            },
        }
        assert so_o_que_mudou(cliente, "285739461", "A@B.pt", "+351 912 345 678") == (None, None, None)
        assert so_o_que_mudou(cliente, "987654321", "novo@b.pt", "933333333") == (
            "987654321", "novo@b.pt", "933333333",
        )

    def test_so_o_que_mudou_reconhece_valores_em_claro(self):
        from services.client_uniqueness import so_o_que_mudou

        cliente = {"dados_pessoais": {"nif": "285739461"}, "contacto": {"email": "a@b.pt", "telefone": "912345678"}}
        assert so_o_que_mudou(cliente, "285739461", "a@b.pt", "912345678") == (None, None, None)


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
            ("telefone", {"telefone": "912345678"}, {"email": "nova@teste.pt"}),
            ("telefone com indicativo", {"telefone": "912345678"}, {"email": "nova@teste.pt", "phone": "+351 912 345 678"}),
            (
                "nif",
                {"nif": "285739461"},
                {"email": "nova@teste.pt", "phone": "933333333", "personal_data": {"nif": "285739461"}},
            ),
        ],
    )
    async def test_campo_repetido_na_rede_do_link_da_409(self, mundo, campo, existente, submetido):
        _existente(mundo.bd, REDE_INCUMBENTE, **existente)
        antes = _foto(mundo.bd)

        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power", **submetido))

        assert r.status_code == 409, campo
        assert json.loads(r.body) == {"success": False, "code": "DUPLICATE_CLIENT", "detail": MENSAGEM}
        assert _foto(mundo.bd) == antes, "nem criou nem alterou nada"

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
    async def test_a_pilha_por_carimbar_conta_para_a_rede_de_omissao(self, mundo):
        _existente(mundo.bd, None, email="maria@teste.pt")
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_cliente_sem_rede_mas_com_empresa_da_rede_conta(self, mundo):
        """Carimbado com a empresa e ainda sem rede continua a ser da rede dessa empresa."""
        doc = _existente(mundo.bd, None, email="maria@teste.pt")
        doc["company_id"] = "cmp-power"
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_a_mesma_pessoa_noutra_rede_e_um_cliente_novo(self, mundo):
        _existente(mundo.bd, REDE_INCUMBENTE, email="maria@teste.pt", telefone="912345678")
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        assert r.status_code == 200
        novos = [c for c in _publicos(mundo.bd) if c.get("network_id") == REDE_DOMUS]
        assert len(novos) == 1

    @pytest.mark.asyncio
    async def test_a_pilha_por_carimbar_nao_bloqueia_uma_ilha(self, mundo):
        _existente(mundo.bd, None, email="maria@teste.pt")
        r = await mundo.pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        assert r.status_code == 200

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
        assert len([c for c in _publicos(mundo.bd) if c.get("email") or c["contacto"]["email"] == "maria@teste.pt"]) == 1


# ====================================================================
# 3. CRIAÇÃO NO CRM
# ====================================================================

class TestCriacaoNoCrm:
    async def _criar(self, bd, *, email="nova@x.pt", nif=None, telefone=None, user=None):
        from models.client import ClientCreate
        from services import client_crud as mod
        from services import client_uniqueness as cu

        payload = ClientCreate(nome="Nova Pessoa", email=email, nif=nif, telefone=telefone, fonte="staff_created")
        user = user or {"id": "u-ana", "email": "ana@power.pt", "role": "diretor", "active_company_id": "cmp-power"}
        with tenant_db(bd, mod, cu), \
                patch.object(mod, "encrypt_client_data", lambda d: d), \
                patch.object(mod, "decrypt_client_data", lambda d: d), \
                patch.object(mod, "s3_service", MagicMock()), \
                patch.object(mod, "_send_portal_welcome_email_safe", AsyncMock()):
            return await mod.run_create_client(payload, user)

    @pytest.mark.asyncio
    async def test_telefone_repetido_na_rede_da_409_com_o_campo(self, fake_async_db, rede_de_omissao_incumbente):
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-tel", telefone="912345678")
        with pytest.raises(HTTPException) as exc:
            await self._criar(fake_async_db, telefone="+351 912 345 678")
        assert exc.value.status_code == 409
        assert exc.value.detail["matched_fields"] == ["telefone"]
        assert "Telemóvel" in exc.value.detail["message"]

    @pytest.mark.asyncio
    async def test_nif_repetido_na_rede_da_409(self, fake_async_db, rede_de_omissao_incumbente):
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-nif", nif="285739461")
        with pytest.raises(HTTPException) as exc:
            await self._criar(fake_async_db, nif="285739461")
        assert exc.value.status_code == 409 and "nif" in exc.value.detail["matched_fields"]

    @pytest.mark.asyncio
    async def test_o_409_nunca_revela_um_cliente_de_outra_rede(self, fake_async_db, rede_de_omissao_incumbente):
        """A Domus cria com o NIF de um cliente da Power: é um cliente novo, sem 409."""
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-power", nif="285739461", email="x@power.pt", telefone="912345678")
        cliente = await self._criar(
            fake_async_db, nif="285739461", email="x@power.pt", telefone="912345678",
            user={"id": "u-bruno", "email": "bruno@domus.pt", "role": "diretor", "active_company_id": "cmp-domus"},
        )
        assert cliente.id != "c-power"

    @pytest.mark.asyncio
    async def test_dados_distintos_criam_normalmente(self, fake_async_db, rede_de_omissao_incumbente):
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE)
        cliente = await self._criar(fake_async_db, telefone="966666666", nif="555666777")
        assert cliente.id


# ====================================================================
# 4. EDIÇÃO NO CRM
# ====================================================================

class TestEdicaoNoCrm:
    async def _editar(self, bd, client_id, **contacto):
        from models.client import ClientUpdate
        from services import client_crud as mod
        from services import client_uniqueness as cu

        dados = ClientUpdate(contacto=contacto) if contacto else ClientUpdate(nome="Outro Nome")
        user = {"id": "u-ana", "email": "ana@power.pt", "role": "diretor", "active_company_id": "cmp-power"}
        with tenant_db(bd, mod, cu), \
                patch.object(mod, "encrypt_client_data", lambda d: d), \
                patch.object(mod, "decrypt_client_data", lambda d: d), \
                patch.object(mod, "s3_service", MagicMock()):
            return await mod.run_update_client(client_id, dados, MagicMock(headers={}, json=AsyncMock(return_value={})), user)

    @pytest.mark.asyncio
    async def test_mudar_para_o_telefone_de_outro_da_409(self, fake_async_db, rede_de_omissao_incumbente):
        from fastapi import HTTPException

        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-a", telefone="911111111", email="a@x.pt", nif="100000011")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-b", telefone="922222222", email="b@x.pt", nif="100000012")
        with pytest.raises(HTTPException) as exc:
            await self._editar(fake_async_db, "c-b", telefone="911111111")
        assert exc.value.status_code == 409
        assert exc.value.detail["existing_client_id"] == "c-a"
        assert exc.value.detail["matched_fields"] == ["telefone"]

    @pytest.mark.asyncio
    async def test_gravar_o_proprio_telefone_nao_trava(self, fake_async_db, rede_de_omissao_incumbente):
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-a", telefone="911111111", email="a@x.pt")
        await self._editar(fake_async_db, "c-a", telefone="911111111", email="a@x.pt")

    @pytest.mark.asyncio
    async def test_duplicado_legado_em_que_nao_se_tocou_nao_trava_a_edicao(self, fake_async_db, rede_de_omissao_incumbente):
        """A regra é nova e a base é antiga: dois clientes já partilham o telemóvel."""
        semear(fake_async_db)
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-a", telefone="911111111", email="a@x.pt", nif="100000011")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-b", telefone="911111111", email="b@x.pt", nif="100000012")
        await self._editar(fake_async_db, "c-b", telefone="911111111", email="b@x.pt")
        await self._editar(fake_async_db, "c-b")

    @pytest.mark.asyncio
    async def test_telefone_de_cliente_de_outra_rede_nao_trava(self, fake_async_db, rede_de_omissao_incumbente):
        semear(fake_async_db)
        _existente(fake_async_db, REDE_DOMUS, id="c-d", telefone="933333333", email="d@x.pt", nif="100000013")
        _existente(fake_async_db, REDE_INCUMBENTE, id="c-p", telefone="944444444", email="p@x.pt", nif="100000014")
        await self._editar(fake_async_db, "c-p", telefone="933333333")


# ====================================================================
# 5. GUARDAS SOBRE O CÓDIGO
# ====================================================================

#: Os escritores de `db.clients.insert_one` que NÃO passam pela guarda de
#: unicidade, cada um com o motivo. Um escritor novo falha o teste.
ESCRITORES_SEM_GUARDA = {
    "admin_proc_migration_helpers.py": "migração: cria um cliente por cada processo legado, a partir de dados já existentes",
    "admin_dev_ops.py": "semeador de desenvolvimento do painel de administração",
    "admin_proc_migration_api.py": "reversão de migração: repõe a cópia de segurança da colecção inteira",
    "partner_drafts.py": "liberta a lead retida do parceiro (porta de parceiro, resposta sem oráculo, ver TECHNICAL_DEBT)",
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

    def test_os_escritores_com_guarda_chamam_a_guarda_com_a_rede(self):
        import services.client_crud as crud
        import services.public_registration as pr

        for modulo, nome in ((crud, "assert_cliente_unico"), (pr, "encontrar_cliente_duplicado")):
            arvore = ast.parse(inspect.getsource(modulo))
            chamadas = [
                n for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and ast.unparse(n.func) == nome
            ]
            assert chamadas, f"{modulo.__name__} deixou de chamar {nome}"
            assert all("rede" in {k.arg for k in c.keywords} for c in chamadas), (
                f"{modulo.__name__}: {nome} sem dizer a rede (esquecer a rede fecha, mas diga-a)"
            )

    def test_a_edicao_so_verifica_o_que_mudou(self):
        import services.client_crud as crud

        fonte = inspect.getsource(crud.run_update_client)
        assert "so_o_que_mudou" in fonte
        assert "excluir_id=client_id" in fonte

    def test_a_unicidade_nao_procura_sem_ambito_de_rede(self):
        import services.client_uniqueness as cu

        fonte = inspect.getsource(cu.encontrar_cliente_duplicado)
        assert "condicao_de_unicidade" in fonte and "com_isolamento" in fonte

    def test_o_telefone_e_um_dos_campos_unicos(self):
        from services.client_uniqueness import CAMPOS_UNICOS

        assert CAMPOS_UNICOS == ("nif", "email", "telefone")
