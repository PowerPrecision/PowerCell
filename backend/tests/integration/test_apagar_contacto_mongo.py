"""Apagar o email/telefone de um cliente persiste — contra um MongoDB REAL (QA, Out 2026).

O defeito: apagar o email nos «Dados do Processo» e guardar dava o toast de
sucesso e o email antigo voltava. Em causa, no servidor:
  * o `email_hash` (índice cego) do endereço antigo ficava para trás;
  * o vazio não era propagado aos PROCESSOS do cliente (`client_email`,
    `personal_data.*`);
  * e a resposta do processo recompõe `client_email` a partir da ficha do
    cliente quando o do processo está vazio — logo bastava um dos dois sítios
    ficar com o valor antigo para ele reaparecer.

Real porque o duplo de Mongo não prova o `$set` com chaves pontuadas em vários
documentos (`update_many`), que é onde este fluxo vive.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_INCUMBENTE, tenant_db

pytestmark = pytest.mark.asyncio

EMAIL = "ana@exemplo.pt"
TELEFONE = "912345678"
ADMIN = {"id": "u-admin", "role": "admin", "email": "admin@x.pt", "permissions": {}}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    base = cliente[f"test_apagar_contacto_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _semear(bd, *, email=EMAIL, telefone=TELEFONE):
    from services.encryption import encrypt_client_data

    await bd.clients.insert_one(encrypt_client_data({
        "id": "cli-1", "nome": "Ana Martins", "network_id": REDE_INCUMBENTE,
        "company_id": "cmp-power", "process_ids": ["p1", "p2"],
        "contacto": {"email": email, "telefone": telefone},
        "dados_pessoais": {"nif": "123456789"},
    }))
    for pid in ("p1", "p2"):
        await bd.processes.insert_one({
            "id": pid, "client_id": "cli-1", "client_name": "Ana Martins",
            "client_email": email, "client_phone": telefone,
            "network_id": REDE_INCUMBENTE,
            "personal_data": {"email": email, "email_hash": "h-antigo", "telefone": telefone,
                              "phone": telefone, "telefone_hash": "t-antigo"},
        })


class _Pedido:
    def __init__(self, corpo=None):
        self._corpo = corpo or {}

    async def json(self):
        return self._corpo


def _contexto(bd):
    import services.client_crud as cc
    import services.client_uniqueness as cu
    import services.process_update as pu

    return tenant_db(bd, cc, cu, pu)


async def _actualizar_cliente(bd, contacto: dict):
    import services.client_crud as cc
    from models.client import ClientUpdate

    with _contexto(bd):
        return await cc.run_update_client(
            "cli-1", ClientUpdate(contacto=contacto), _Pedido(), ADMIN,
        )


async def _cliente(bd):
    from services.encryption import decrypt_client_data

    return decrypt_client_data(await bd.clients.find_one({"id": "cli-1"}))


# ═════════════════════════════════════════════════════════════════════
# 1. PUT /clients/{id}
# ═════════════════════════════════════════════════════════════════════


class TestPutDoCliente:
    async def test_apagar_o_email_limpa_o_valor_e_o_indice_cego(self, bd):
        from services.encryption import generate_email_hash

        await _semear(bd)
        antes = await bd.clients.find_one({"id": "cli-1"})
        assert antes["contacto"]["email_hash"] == generate_email_hash(EMAIL)

        await _actualizar_cliente(bd, {"email": ""})

        cli = await _cliente(bd)
        assert cli["contacto"]["email"] == ""
        assert cli["contacto"]["email_hash"] == ""
        # O telefone e o seu índice ficam como estavam.
        assert cli["contacto"]["telefone"] == TELEFONE
        assert cli["contacto"]["telefone_hash"] == antes["contacto"]["telefone_hash"]

    async def test_apagar_propaga_a_todos_os_processos_do_cliente(self, bd):
        await _semear(bd)
        await _actualizar_cliente(bd, {"email": ""})

        for pid in ("p1", "p2"):
            p = await bd.processes.find_one({"id": pid})
            assert p["client_email"] == ""
            assert p["personal_data"]["email"] == ""
            assert p["personal_data"]["email_hash"] == ""
            # O telefone não é tocado.
            assert p["client_phone"] == TELEFONE
            assert p["personal_data"]["telefone"] == TELEFONE
            assert p["personal_data"]["telefone_hash"] == "t-antigo"

    async def test_apagar_o_telefone_limpa_tudo_o_que_lhe_diz_respeito(self, bd):
        await _semear(bd)
        await _actualizar_cliente(bd, {"telefone": ""})

        cli = await _cliente(bd)
        assert cli["contacto"]["telefone"] == "" and cli["contacto"]["telefone_hash"] == ""
        assert cli["contacto"]["email"] == EMAIL
        for pid in ("p1", "p2"):
            p = await bd.processes.find_one({"id": pid})
            assert p["client_phone"] == ""
            assert p["personal_data"]["telefone"] == "" and p["personal_data"]["phone"] == ""
            assert p["personal_data"]["telefone_hash"] == ""
            assert p["client_email"] == EMAIL

    async def test_null_explicito_tambem_apaga(self, bd):
        await _semear(bd)
        await _actualizar_cliente(bd, {"email": None})

        assert (await _cliente(bd))["contacto"]["email"] == ""
        assert (await bd.processes.find_one({"id": "p1"}))["client_email"] == ""

    async def test_so_espacos_tambem_apaga(self, bd):
        await _semear(bd)
        await _actualizar_cliente(bd, {"email": "   "})
        assert (await _cliente(bd))["contacto"]["email"] == ""

    async def test_a_chave_ausente_nao_apaga_nada(self, bd):
        """A contraprova: «não alterei» ≠ «apaguei»."""
        await _semear(bd)
        await _actualizar_cliente(bd, {"telefone": "966666666"})

        cli = await _cliente(bd)
        assert cli["contacto"]["email"] == EMAIL
        assert cli["contacto"]["email_hash"] != ""
        assert (await bd.processes.find_one({"id": "p1"}))["client_email"] == EMAIL

    async def test_editar_so_o_email_nao_estraga_o_indice_do_telefone(self, bd):
        """Defeito vizinho achado ao escrever isto: o merge recalculava o `telefone_hash`
        sobre o telefone CIFRADO, e o cliente deixava de ser encontrado pelo número."""
        from services.encryption import generate_telefone_hash

        await _semear(bd)
        await _actualizar_cliente(bd, {"email": "novo@exemplo.pt"})

        cli = await bd.clients.find_one({"id": "cli-1"})
        assert cli["contacto"]["telefone_hash"] == generate_telefone_hash(TELEFONE)
        assert cli["contacto"]["telefone"].startswith("ENC:"), "continua cifrado em repouso"
        assert (await _cliente(bd))["contacto"]["telefone"] == TELEFONE

    async def test_editar_so_o_email_nao_escreve_o_telefone_em_claro_nos_processos(self, bd):
        await _semear(bd)
        await bd.processes.update_one({"id": "p1"}, {"$set": {"client_phone": "ENC:cifrado"}})
        await _actualizar_cliente(bd, {"email": "novo@exemplo.pt"})

        assert (await bd.processes.find_one({"id": "p1"}))["client_phone"] == "ENC:cifrado"
        assert (await bd.processes.find_one({"id": "p1"}))["client_email"] == "novo@exemplo.pt"

    async def test_o_email_apagado_deixa_de_bloquear_outro_cliente(self, bd):
        """Com o índice cego antigo, o email apagado continuava a «pertencer» à Ana."""
        import services.client_uniqueness as cu

        await _semear(bd)
        with _contexto(bd):
            assert await cu.encontrar_cliente_duplicado(
                None, EMAIL, None, rede=REDE_INCUMBENTE,
            ) is not None
        await _actualizar_cliente(bd, {"email": ""})
        with _contexto(bd):
            assert await cu.encontrar_cliente_duplicado(
                None, EMAIL, None, rede=REDE_INCUMBENTE,
            ) is None

    async def test_o_processo_nao_recompoe_o_email_antigo_na_resposta(self, bd):
        """O que o ecrã lê: `client_email` vazio no processo cai no do cliente — ambos têm de estar vazios."""
        import services.process_service as ps

        await _semear(bd)
        await _actualizar_cliente(bd, {"email": ""})

        processo = await bd.processes.find_one({"id": "p1"}, {"_id": 0})
        with patch.object(ps, "db", bd):
            resposta = await ps.populate_client_data(processo)
        assert resposta["client_email"] == ""
        assert resposta["personal_data"]["email"] == ""


# ═════════════════════════════════════════════════════════════════════
# 2. PUT /processes/{id}
# ═════════════════════════════════════════════════════════════════════


class TestPutDoProcesso:
    def test_o_corpo_com_client_email_vazio_pede_para_apagar(self):
        from services.process_service import extract_client_updates_from_body as extrair

        assert extrair({"client_email": ""})["contacto.email"] == ""
        assert extrair({"client_email": "   "})["contacto.email"] == ""
        assert extrair({"client_email": None})["contacto.email"] == ""
        assert extrair({"client_phone": ""})["contacto.telefone"] == ""
        assert extrair({"client_phone": None})["contacto.telefone"] == ""

    def test_a_chave_ausente_nao_pede_nada(self):
        from services.process_service import extract_client_updates_from_body as extrair

        assert extrair({"notes": "x"}) == {}

    def test_um_valor_continua_a_ser_normalizado(self):
        from services.process_service import extract_client_updates_from_body as extrair

        assert extrair({"client_email": " ANA@Exemplo.PT "})["contacto.email"] == "ana@exemplo.pt"
        assert extrair({"client_phone": " 912 "})["contacto.telefone"] == "912"

    def test_o_espelho_personal_data_vazio_NAO_apaga(self):
        """O formulário reenvia `personal_data.email` vazio em qualquer gravação: não é um pedido."""
        from services.process_service import extract_client_updates_from_body as extrair

        assert "contacto.email" not in extrair({"personal_data": {"email": "", "nif": "1"}})

    def test_valor_que_nao_e_texto_nao_conta(self):
        from services.process_service import extract_client_updates_from_body as extrair

        assert extrair({"client_email": 123}) == {}
        assert extrair({"client_email": {"$ne": ""}}) == {}

    def test_contacto_do_pedido_distingue_ausente_de_vazio(self):
        from services.process_update import contacto_do_pedido

        assert contacto_do_pedido({}, "client_email") is None
        assert contacto_do_pedido({"client_email": None}, "client_email") == ""
        assert contacto_do_pedido({"client_email": ""}, "client_email") == ""
        assert contacto_do_pedido({"client_email": "a@b.pt"}, "client_email") == "a@b.pt"
        assert contacto_do_pedido({"client_email": 5}, "client_email") is None

    def test_o_seed_grava_o_vazio_e_limpa_o_legado_so_se_existir(self):
        from services.process_update import seed_update_data

        processo = {"client_id": "c", "personal_data": {"email": "a@b.pt", "email_hash": "h"}}
        seed = seed_update_data(
            process=processo, client_id_before="c", new_client_id=None,
            raw_client_email="", raw_client_phone=None,
        )
        assert seed["client_email"] == ""
        assert seed["personal_data.email"] == "" and seed["personal_data.email_hash"] == ""
        assert "client_phone" not in seed
        assert not any(k.startswith("personal_data.tele") for k in seed)

    def test_o_seed_nao_cria_personal_data_que_o_processo_nao_tem(self):
        from services.process_update import seed_update_data

        seed = seed_update_data(
            process={"client_id": "c"}, client_id_before="c", new_client_id=None,
            raw_client_email="", raw_client_phone="",
        )
        assert seed["client_email"] == "" and seed["client_phone"] == ""
        assert not any(k.startswith("personal_data") for k in seed)

    def test_prepare_encrypted_limpa_os_indices_dos_campos_apagados(self):
        from services.process_update import prepare_encrypted_client_updates

        saida = prepare_encrypted_client_updates({
            "contacto.email": "", "contacto.telefone": "", "dados_pessoais.nif": "",
        })
        assert saida["contacto.email_hash"] == ""
        assert saida["contacto.telefone_hash"] == ""
        assert saida["dados_pessoais.nif_hash"] == ""
        assert saida["contacto.email"] == ""

    def test_prepare_encrypted_mantem_o_hash_de_um_valor_novo(self):
        from services.encryption import generate_email_hash
        from services.process_update import prepare_encrypted_client_updates

        saida = prepare_encrypted_client_updates({"contacto.email": "novo@b.pt"})
        assert saida["contacto.email_hash"] == generate_email_hash("novo@b.pt")

    async def test_o_cascade_limpa_os_outros_processos_do_cliente(self, bd):
        import services.process_update as pu

        await _semear(bd)
        with patch.object(pu, "db", bd):
            await pu.apply_client_personal_updates_from_process_put(
                "cli-1",
                pu.prepare_encrypted_client_updates({"contacto.email": ""}),
                "p1",
            )

        cli = await _cliente(bd)
        assert cli["contacto"]["email"] == "" and cli["contacto"]["email_hash"] == ""
        # p1 é o do próprio pedido (o `seed_update_data` trata dele); p2 é o outro.
        assert (await bd.processes.find_one({"id": "p2"}))["client_email"] == ""
        assert (await bd.processes.find_one({"id": "p2"}))["personal_data"]["email"] == ""
        assert (await bd.processes.find_one({"id": "p1"}))["client_email"] == EMAIL

    async def test_sem_apagar_o_cascade_nao_toca_nos_outros_processos(self, bd):
        import services.process_update as pu

        await _semear(bd)
        with patch.object(pu, "db", bd):
            await pu.apply_client_personal_updates_from_process_put(
                "cli-1", pu.prepare_encrypted_client_updates({"contacto.email": "novo@b.pt"}), "p1",
            )
        assert (await bd.processes.find_one({"id": "p2"}))["client_email"] == EMAIL


# ═════════════════════════════════════════════════════════════════════
# 3. O ÍNDICE CEGO
# ═════════════════════════════════════════════════════════════════════


class TestIndiceCego:
    def test_so_os_campos_que_a_submissao_trouxe(self):
        from services.encryption import limpar_blind_indexes_de_campos_vazios as limpar

        contacto = {"telefone": "9"}
        assert limpar(contacto=contacto) == []
        assert "email_hash" not in contacto

    def test_vazio_none_e_espacos_limpam_o_valor_e_o_indice(self):
        from services.encryption import limpar_blind_indexes_de_campos_vazios as limpar

        for vazio in ("", None, "   "):
            contacto = {"email": vazio, "email_hash": "h"}
            assert limpar(contacto=contacto) == ["email"]
            assert contacto == {"email": "", "email_hash": ""}

    def test_um_campo_preenchido_nao_e_tocado(self):
        from services.encryption import limpar_blind_indexes_de_campos_vazios as limpar

        contacto = {"email": "a@b.pt", "email_hash": "h"}
        assert limpar(contacto=contacto) == []
        assert contacto["email_hash"] == "h"

    def test_aceita_ausentes_e_tipos_estranhos(self):
        from services.encryption import limpar_blind_indexes_de_campos_vazios as limpar

        assert limpar() == []
        assert limpar(contacto="x", dados_pessoais=None) == []
