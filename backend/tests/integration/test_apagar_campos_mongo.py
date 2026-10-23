"""Apagar QUALQUER campo opcional de um cliente/processo persiste — contra um MongoDB REAL (QA, Out 2026).

A primeira correcção (email/telefone) deixou o resto de fora: apagar o NIF — ou a
morada, o código postal, a naturalidade… — e guardar dava o toast de sucesso e o
valor antigo voltava. As causas, no servidor, são as mesmas do email e mais algumas:

  * o `nif_hash` (índice cego) copiado para o PROCESSO nunca era limpo, e a
    pesquisa continuava a achar o processo pelo NIF que já não existe;
  * `client_nif` (raiz do processo) nunca era limpo, e `populate_client_data` só
    recompõe quando está vazio — logo o valor antigo vencia;
  * os campos de `personal_data` copiados para o processo (e os seus nomes
    alternativos: `morada`/`address`, `birth_date`…) ficavam com o valor antigo;
  * o PUT do processo só limpava os contactos.

Real porque o duplo de Mongo não prova o `$set` com chaves pontuadas em vários
documentos (`update_many`), que é onde este fluxo vive.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_INCUMBENTE, tenant_db

pytestmark = pytest.mark.asyncio

NIF = "123456789"
MORADA = "Rua das Flores 1"
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
    base = cliente[f"test_apagar_campos_{uuid.uuid4().hex[:8]}"]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


class _Pedido:
    """Duplo mínimo de `Request`: corpo JSON e cabeçalhos vazios."""

    def __init__(self, corpo=None):
        self._corpo = corpo or {}
        self.headers = {}
        self.state = type("E", (), {})()

    async def json(self):
        return self._corpo


async def _semear(bd, *, dados_pessoais=None, legado=None, extra_processo=None):
    from services.encryption import encrypt_client_data
    from services.process_service import encrypt_sensitive_data

    pessoais = {"nif": NIF, "morada_fiscal": MORADA, "codigo_postal": "4000-001",
                "naturalidade": "Porto", "niss": "12345678901"}
    pessoais.update(dados_pessoais or {})
    await bd.clients.insert_one(encrypt_client_data({
        "id": "cli-1", "nome": "Ana Martins", "network_id": REDE_INCUMBENTE,
        "company_id": "cmp-power", "process_ids": ["p1", "p2"],
        "contacto": {"email": "ana@exemplo.pt", "telefone": "912345678"},
        "dados_pessoais": pessoais,
    }))
    copia = {"nif": NIF, "morada_fiscal": MORADA, "morada": MORADA, "address": MORADA,
             "naturalidade": "Porto", "data_nascimento": "1990-01-01", "birth_date": "1990-01-01"}
    copia.update(legado or {})
    for pid in ("p1", "p2"):
        doc = {
            "id": pid, "client_id": "cli-1", "client_name": "Ana Martins",
            "client_nif": NIF, "client_email": "ana@exemplo.pt", "client_phone": "912345678",
            "network_id": REDE_INCUMBENTE, "status": "novo",
            "personal_data": dict(copia, nif_hash="h-antigo"),
        }
        doc.update(extra_processo or {})
        await bd.processes.insert_one(encrypt_sensitive_data(doc))


def _contexto(bd):
    import services.client_crud as cc
    import services.client_uniqueness as cu
    import services.process_service as ps
    import services.process_update as pu
    import services.process_phase_clock as clock

    # Só os módulos que têm um `db` próprio (referência importada no topo).
    modulos = [m for m in (cc, cu, pu, ps, clock) if hasattr(m, "db")]
    return tenant_db(bd, *modulos)


async def _put_cliente(bd, corpo: dict):
    import services.client_crud as cc
    from models.client import ClientUpdate

    with _contexto(bd):
        return await cc.run_update_client(
            "cli-1", ClientUpdate(**corpo), _Pedido(corpo), ADMIN,
        )


async def _put_processo(bd, corpo: dict, processo="p1"):
    import services.process_update as pu
    from models.process import ProcessUpdate
    from services.audit_cdc import inject_cdc_context
    from services.process_service import (
        decrypt_sensitive_data, extract_client_updates_from_body, populate_client_data,
    )

    nada = AsyncMock(return_value=None)
    with _contexto(bd):
        return await pu.run_update_process(
            processo, ProcessUpdate(**{k: v for k, v in corpo.items() if k in ProcessUpdate.model_fields}),
            _Pedido(corpo), ADMIN,
            decrypt_fn=decrypt_sensitive_data, populate_fn=populate_client_data,
            extract_client_updates_fn=extract_client_updates_from_body,
            inject_cdc_fn=inject_cdc_context, broadcast_fn=nada,
            ensure_finance_snapshot_fn=nada, log_history_fn=nada,
            log_audit_event_fn=nada, cliente_role="cliente",
        )


async def _cliente(bd):
    from services.encryption import decrypt_client_data

    return decrypt_client_data(await bd.clients.find_one({"id": "cli-1"}))


async def _processo_lido(bd, pid="p1"):
    """O que o ecrã recebe: o documento desencriptado e recomposto pela API."""
    import services.process_service as ps

    doc = await bd.processes.find_one({"id": pid}, {"_id": 0})
    with patch.object(ps, "db", bd):
        return await ps.populate_client_data(ps.decrypt_sensitive_data(doc))


def _hash_do_nif() -> str:
    """O índice cego que o `encrypt_sensitive_data` grava para o NIF semeado."""
    from services.encryption import generate_nif_hash

    return generate_nif_hash(NIF)


def _vazio(valor) -> bool:
    return valor in (None, "")


# ═════════════════════════════════════════════════════════════════════
# 1. O NIF — o caso que o QA apanhou
# ═════════════════════════════════════════════════════════════════════


class TestApagarONifPeloCliente:
    async def test_limpa_o_valor_e_o_indice_cego_no_cliente(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"nif": ""}})

        cli = await _cliente(bd)
        assert _vazio(cli["dados_pessoais"]["nif"])
        assert _vazio(cli["dados_pessoais"].get("nif_hash"))
        # O resto da ficha não é tocado.
        assert cli["dados_pessoais"]["morada_fiscal"] == MORADA

    async def test_limpa_todas_as_copias_nos_processos_do_cliente(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"nif": ""}})

        for pid in ("p1", "p2"):
            bruto = await bd.processes.find_one({"id": pid})
            assert _vazio(bruto["client_nif"]), f"{pid}: client_nif ficou com o valor antigo"
            assert _vazio(bruto["personal_data"]["nif"])
            assert _vazio(bruto["personal_data"]["nif_hash"]), (
                f"{pid}: o índice cego do NIF antigo ficou no processo"
            )

    async def test_o_ecra_nao_recebe_o_nif_antigo(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"nif": ""}})

        lido = await _processo_lido(bd)
        assert _vazio(lido["client_nif"])
        assert _vazio(lido["personal_data"]["nif"])

    async def test_o_nif_apagado_deixa_de_bloquear_outro_cliente(self, bd):
        import services.client_uniqueness as cu

        await _semear(bd)
        with _contexto(bd):
            assert await cu.encontrar_cliente_duplicado(NIF, None) is not None
        await _put_cliente(bd, {"dados_pessoais": {"nif": ""}})
        with _contexto(bd):
            assert await cu.encontrar_cliente_duplicado(NIF, None) is None

    async def test_null_explicito_tambem_apaga(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"nif": None}})
        assert _vazio((await _cliente(bd))["dados_pessoais"]["nif"])
        assert _vazio((await bd.processes.find_one({"id": "p1"}))["client_nif"])

    async def test_a_chave_ausente_nao_apaga_nada(self, bd):
        """A contraprova: «não alterei» ≠ «apaguei»."""
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"naturalidade": "Lisboa"}})

        assert (await _cliente(bd))["dados_pessoais"]["nif"] == NIF
        p1 = await bd.processes.find_one({"id": "p1"})
        assert p1["personal_data"]["nif_hash"] == _hash_do_nif()
        assert (await _processo_lido(bd))["client_nif"] == NIF


class TestApagarONifPeloProcesso:
    async def test_o_put_do_processo_com_nif_vazio_apaga_em_todo_o_lado(self, bd):
        await _semear(bd)
        await _put_processo(bd, {"personal_data": {"nif": ""}})

        cli = await _cliente(bd)
        assert _vazio(cli["dados_pessoais"]["nif"]) and _vazio(cli["dados_pessoais"].get("nif_hash"))
        for pid in ("p1", "p2"):
            bruto = await bd.processes.find_one({"id": pid})
            assert _vazio(bruto["client_nif"]), pid
            assert _vazio(bruto["personal_data"]["nif"]), pid
            assert _vazio(bruto["personal_data"]["nif_hash"]), pid
        assert _vazio((await _processo_lido(bd))["client_nif"])

    async def test_sem_a_chave_o_nif_fica(self, bd):
        await _semear(bd)
        await _put_processo(bd, {"personal_data": {"naturalidade": "Lisboa"}})
        assert (await _cliente(bd))["dados_pessoais"]["nif"] == NIF
        assert (await bd.processes.find_one({"id": "p2"}))["personal_data"]["nif_hash"] == _hash_do_nif()


# ═════════════════════════════════════════════════════════════════════
# 2. Qualquer outro campo pessoal
# ═════════════════════════════════════════════════════════════════════

#: (campo da ficha do cliente, chaves do processo que o espelham).
CAMPOS_PESSOAIS = [
    ("morada_fiscal", ["morada_fiscal", "morada", "address"]),
    ("naturalidade", ["naturalidade"]),
    ("data_nascimento", ["data_nascimento", "birth_date"]),
]


class TestApagarOutrosCamposPessoais:
    @pytest.mark.parametrize("campo,espelhos", CAMPOS_PESSOAIS)
    async def test_pelo_cliente(self, bd, campo, espelhos):
        await _semear(bd, dados_pessoais={"data_nascimento": "1990-01-01"})
        await _put_cliente(bd, {"dados_pessoais": {campo: ""}})

        assert _vazio((await _cliente(bd))["dados_pessoais"].get(campo))
        for pid in ("p1", "p2"):
            pd = (await bd.processes.find_one({"id": pid}))["personal_data"]
            for chave in espelhos:
                assert _vazio(pd.get(chave)), f"{pid}: personal_data.{chave} = {pd.get(chave)!r}"
        lido = (await _processo_lido(bd))["personal_data"]
        for chave in espelhos:
            assert _vazio(lido.get(chave)), f"o ecrã recebe personal_data.{chave} = {lido.get(chave)!r}"

    @pytest.mark.parametrize("campo,espelhos", CAMPOS_PESSOAIS)
    async def test_pelo_processo(self, bd, campo, espelhos):
        await _semear(bd, dados_pessoais={"data_nascimento": "1990-01-01"})
        await _put_processo(bd, {"personal_data": {campo: ""}})

        assert _vazio((await _cliente(bd))["dados_pessoais"].get(campo))
        for pid in ("p1", "p2"):
            pd = (await bd.processes.find_one({"id": pid}))["personal_data"]
            for chave in espelhos:
                assert _vazio(pd.get(chave)), f"{pid}: personal_data.{chave} = {pd.get(chave)!r}"

    async def test_o_nome_alternativo_da_ficha_do_cliente_sai_com_o_canonico(self, bd):
        """A ficha também pode ter `address`: a leitura (e o ecrã) recompõem a morada a partir dele."""
        await _semear(bd, dados_pessoais={"address": MORADA, "morada": MORADA})
        await _put_cliente(bd, {"dados_pessoais": {"morada_fiscal": ""}})

        pessoais = (await _cliente(bd))["dados_pessoais"]
        assert _vazio(pessoais["morada_fiscal"])
        assert _vazio(pessoais["address"]) and _vazio(pessoais["morada"])

    async def test_o_mesmo_pelo_put_do_processo(self, bd):
        await _semear(bd, dados_pessoais={"address": MORADA})
        await _put_processo(bd, {"personal_data": {"morada_fiscal": ""}})

        pessoais = (await _cliente(bd))["dados_pessoais"]
        assert _vazio(pessoais["morada_fiscal"]) and _vazio(pessoais["address"])

    async def test_nao_cria_nomes_alternativos_que_a_ficha_nunca_teve(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"morada_fiscal": ""}})
        pessoais = (await _cliente(bd))["dados_pessoais"]
        assert "address" not in pessoais and "morada" not in pessoais

    async def test_apagar_um_campo_nao_apaga_os_outros(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"morada_fiscal": ""}})

        cli = await _cliente(bd)
        assert cli["dados_pessoais"]["nif"] == NIF
        assert cli["dados_pessoais"]["naturalidade"] == "Porto"
        pd = (await bd.processes.find_one({"id": "p1"}))["personal_data"]
        assert pd["naturalidade"] == "Porto"
        assert (await bd.processes.find_one({"id": "p1"}))["client_nif"] != ""

    async def test_espacos_em_branco_tambem_apagam(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"morada_fiscal": "   "}})
        assert _vazio((await _cliente(bd))["dados_pessoais"]["morada_fiscal"])


# ═════════════════════════════════════════════════════════════════════
# 3. O nome NÃO se apaga — e di-lo
# ═════════════════════════════════════════════════════════════════════


class TestONomeEObrigatorio:
    @pytest.mark.parametrize("vazio", ["", "   "])
    async def test_nome_vazio_e_recusado_e_nada_e_gravado(self, bd, vazio):
        await _semear(bd)
        with pytest.raises(HTTPException) as exc:
            await _put_cliente(bd, {"nome": vazio, "dados_pessoais": {"nif": ""}})
        assert exc.value.status_code == 400
        assert "nome" in str(exc.value.detail).lower()
        # Recusa ANTES de gravar: nem o NIF do mesmo pedido foi apagado.
        assert (await _cliente(bd))["nome"] == "Ana Martins"
        assert (await _cliente(bd))["dados_pessoais"]["nif"] == NIF

    async def test_sem_a_chave_nome_nada_acontece(self, bd):
        await _semear(bd)
        await _put_cliente(bd, {"dados_pessoais": {"naturalidade": "Lisboa"}})
        assert (await _cliente(bd))["nome"] == "Ana Martins"


# ═════════════════════════════════════════════════════════════════════
# 4. 2.º titular (titular2_data)
# ═════════════════════════════════════════════════════════════════════

TITULAR2 = {"name": "Rui Costa", "email": "rui@exemplo.pt", "nif": "987654321",
            "birth_date": "1991-02-03", "morada_fiscal": "Rua B 2", "naturalidade": "Braga"}


async def _semear_titular2(bd):
    from services.encryption import encrypt_client_data
    from services.process_service import encrypt_sensitive_data

    await _semear(bd)
    await bd.clients.update_one(
        {"id": "cli-1"},
        {"$set": {"titular2_data": encrypt_client_data({"titular2_data": dict(TITULAR2)})["titular2_data"]}},
    )
    # O processo nasce com uma CÓPIA do 2.º titular (client_assign).
    copia = encrypt_sensitive_data({"titular2_data": dict(TITULAR2)})["titular2_data"]
    await bd.processes.update_many({}, {"$set": {"titular2_data": copia}})


class TestSegundoTitular:
    async def test_apagar_o_nif_do_segundo_titular(self, bd):
        await _semear_titular2(bd)
        novo = {k: v for k, v in TITULAR2.items() if k != "nif"}
        await _put_processo(bd, {"titular2_data": {**novo, "nif": ""}})

        lido = await _processo_lido(bd)
        assert _vazio(lido["titular2_data"].get("nif")), (
            f"o ecrã recebe o NIF antigo do 2.º titular: {lido['titular2_data'].get('nif')!r}"
        )
        cli = await _cliente(bd)
        assert _vazio(cli["titular2_data"].get("nif"))
        assert _vazio(cli["titular2_data"].get("nif_hash"))

    async def test_editar_um_campo_do_segundo_titular_chega_ao_ecra(self, bd):
        await _semear_titular2(bd)
        await _put_processo(bd, {"titular2_data": {**TITULAR2, "naturalidade": "Faro"}})
        assert (await _processo_lido(bd))["titular2_data"]["naturalidade"] == "Faro"

    async def test_apagar_a_morada_do_segundo_titular(self, bd):
        await _semear_titular2(bd)
        await _put_processo(bd, {"titular2_data": {**TITULAR2, "morada_fiscal": ""}})
        assert _vazio((await _processo_lido(bd))["titular2_data"].get("morada_fiscal"))
        # O que não foi apagado fica.
        assert (await _processo_lido(bd))["titular2_data"]["nif"] == "987654321"

    async def test_sem_titular2_no_pedido_nada_e_tocado(self, bd):
        await _semear_titular2(bd)
        await _put_processo(bd, {"personal_data": {"naturalidade": "Lisboa"}})
        assert (await _processo_lido(bd))["titular2_data"]["nif"] == "987654321"


# ═════════════════════════════════════════════════════════════════════
# 5. Secções do processo: financeiro, imóvel, crédito
# ═════════════════════════════════════════════════════════════════════


async def _semear_seccao(bd, seccao: str, dados: dict):
    from services.process_service import encrypt_sensitive_data

    await _semear(bd)
    await bd.processes.update_one(
        {"id": "p1"}, {"$set": {seccao: encrypt_sensitive_data({seccao: dict(dados)})[seccao]}},
    )


async def _seccao(bd, seccao: str) -> dict:
    return (await _processo_lido(bd))[seccao]


class TestSeccoesFinanceiras:
    async def test_limpar_o_canonico_leva_os_alternativos_que_o_ecra_usa_como_recurso(self, bd):
        """`monthly_income` vazio e `salario_liquido` preenchido: o ecrã mostra o segundo."""
        await _semear_seccao(bd, "financial_data", {
            "monthly_income": 2000, "salario_liquido": 1800, "rendimento_mensal": 1900,
            "employer_name": "ACME", "empresa": "ACME", "entidade_patronal": "ACME",
            "capital_proprio": 5000, "other_income": 100,
        })
        await _put_processo(bd, {"financial_data": {"monthly_income": None, "employer_name": ""}})

        fin = await _seccao(bd, "financial_data")
        for chave in ("monthly_income", "salario_liquido", "rendimento_mensal",
                      "employer_name", "empresa", "entidade_patronal"):
            assert _vazio(fin.get(chave)), f"{chave} = {fin.get(chave)!r}"
        # O resto da secção fica.
        assert fin["capital_proprio"] == 5000 and fin["other_income"] == 100

    async def test_o_alternativo_que_o_pedido_traz_preenchido_nao_e_retirado(self, bd):
        await _semear_seccao(bd, "financial_data", {"monthly_income": 2000, "salario_liquido": 1800})
        await _put_processo(bd, {"financial_data": {"monthly_income": None, "salario_liquido": 1500}})
        fin = await _seccao(bd, "financial_data")
        assert _vazio(fin.get("monthly_income")) and fin["salario_liquido"] == 1500

    async def test_sem_a_chave_nada_e_retirado(self, bd):
        await _semear_seccao(bd, "financial_data", {"monthly_income": 2000, "salario_liquido": 1800})
        await _put_processo(bd, {"financial_data": {"capital_proprio": 10}})
        fin = await _seccao(bd, "financial_data")
        assert fin["monthly_income"] == 2000 and fin["salario_liquido"] == 1800

    async def test_zero_e_um_valor_nao_um_vazio(self, bd):
        await _semear_seccao(bd, "financial_data", {"nr_dependentes": 2, "number_of_dependents": 2})
        await _put_processo(bd, {"financial_data": {"nr_dependentes": 0}})
        fin = await _seccao(bd, "financial_data")
        assert fin["nr_dependentes"] == 0
        assert fin["number_of_dependents"] == 2, "um 0 não é «apagar»: os alternativos ficam"


def _amostra(campo):
    """Um valor válido para o tipo do campo do modelo (para semear e depois apagar)."""
    import typing

    anotacao = campo.annotation
    args = [a for a in typing.get_args(anotacao) if a is not type(None)]
    tipo = args[0] if args else anotacao
    if typing.get_origin(tipo) is list:
        return ["a"]
    return {str: "valor", float: 12.5, int: 7, bool: True}.get(tipo, "valor")


def _campos(modelo):
    return {nome: _amostra(campo) for nome, campo in modelo.model_fields.items()}


class TestSeccoesDoProcessoCampoACampo:
    @pytest.mark.parametrize("seccao,modelo_nome", [
        ("real_estate_data", "RealEstateData"), ("credit_data", "CreditData"),
    ])
    async def test_cada_campo_do_modelo_pode_ser_apagado(self, bd, seccao, modelo_nome):
        import models.process as modelos

        modelo = getattr(modelos, modelo_nome)
        dados = _campos(modelo)
        falhas = []
        for campo in dados:
            await bd.processes.delete_many({})
            await bd.clients.delete_many({})
            await _semear_seccao(bd, seccao, dados)
            try:
                await _put_processo(bd, {seccao: {campo: None}})
            except Exception as erro:  # um 422/500 também é «não consegue apagar»
                falhas.append(f"{campo}: {type(erro).__name__}: {erro}")
                continue
            depois = await _seccao(bd, seccao)
            if not _vazio(depois.get(campo)):
                falhas.append(f"{campo}: ficou {depois.get(campo)!r}")
            outros = [c for c in dados if c != campo and _vazio(depois.get(c))]
            if outros:
                falhas.append(f"{campo}: apagou também {outros}")
        assert not falhas, "\n".join(falhas)


# ═════════════════════════════════════════════════════════════════════
# 6. O Portal do Cliente (PUT /portal/me)
# ═════════════════════════════════════════════════════════════════════


async def _put_portal(bd, contacto=None, dados_pessoais=None):
    import services.portal_profile as pp

    modelo = pp.ClientProfileUpdate(contacto=contacto, dados_pessoais=dados_pessoais)
    # O Portal só deixa editar enquanto o processo está na recolha (pré-registo).
    await bd.processes.update_many({}, {"$set": {"status": "pre_registo"}})
    with tenant_db(bd, pp):
        return await pp.run_update_client_profile(modelo, {"client_id": "cli-1"})


class TestPerfilDoPortal:
    async def test_o_cliente_que_apaga_o_email_nao_deixa_o_indice_cego_para_tras(self, bd):
        await _semear(bd)
        await _put_portal(bd, contacto={"email": None})

        cli = await bd.clients.find_one({"id": "cli-1"})
        assert _vazio(cli["contacto"]["email"]) and _vazio(cli["contacto"].get("email_hash"))
        # Telefone intacto.
        assert not _vazio(cli["contacto"]["telefone"])

    async def test_e_sai_das_copias_nos_processos(self, bd):
        await _semear(bd)
        await _put_portal(bd, contacto={"email": ""}, dados_pessoais={"morada_fiscal": None})

        for pid in ("p1", "p2"):
            p = await bd.processes.find_one({"id": pid})
            assert _vazio(p["client_email"]), pid
            assert _vazio(p["personal_data"]["morada_fiscal"]), pid
            assert _vazio(p["personal_data"]["morada"]) and _vazio(p["personal_data"]["address"])
        cli = await _cliente(bd)
        assert _vazio(cli["dados_pessoais"]["morada_fiscal"])

    async def test_apagar_grava_vazio_e_nao_null(self, bd):
        """`""` é como o CRM e a leitura reconhecem «apagado»."""
        await _semear(bd)
        await _put_portal(bd, dados_pessoais={"naturalidade": None})
        assert (await bd.clients.find_one({"id": "cli-1"}))["dados_pessoais"]["naturalidade"] == ""

    async def test_um_campo_nao_enviado_nao_e_tocado(self, bd):
        await _semear(bd)
        await _put_portal(bd, dados_pessoais={"naturalidade": "Lisboa"})
        cli = await _cliente(bd)
        assert cli["dados_pessoais"]["morada_fiscal"] == MORADA
        assert cli["contacto"]["email"] == "ana@exemplo.pt"
        p = await bd.processes.find_one({"id": "p1"})
        assert p["client_email"] != "" and not _vazio(p["personal_data"]["morada_fiscal"])

    async def test_o_nif_continua_trancado(self, bd):
        """O cliente nunca grava (nem apaga) o NIF pelo Portal."""
        await _semear(bd)
        await _put_portal(bd, dados_pessoais={"nif": None, "naturalidade": "Lisboa"})
        assert (await _cliente(bd))["dados_pessoais"]["nif"] == NIF


# ═════════════════════════════════════════════════════════════════════
# 7. Editor administrativo de registos (PUT /admin/client-registrations/{id})
# ═════════════════════════════════════════════════════════════════════


class TestRegistoDoAdmin:
    async def _put(self, bd, corpo):
        import services.admin_observability as ao

        with tenant_db(bd, ao):
            return await ao.run_update_client_registration("p1", corpo, ADMIN)

    async def test_apagar_o_nif_do_registo_limpa_o_indice_cego_e_a_copia_da_raiz(self, bd):
        await _semear(bd)
        await self._put(bd, {"personal_data": {"nif": ""}})

        p = await bd.processes.find_one({"id": "p1"})
        assert _vazio(p["personal_data"]["nif"]) and _vazio(p["personal_data"]["nif_hash"])
        assert _vazio(p["client_nif"])
        # O outro processo do cliente não é deste pedido.
        assert not _vazio((await bd.processes.find_one({"id": "p2"}))["client_nif"])

    async def test_sem_a_chave_o_nif_fica(self, bd):
        await _semear(bd)
        await self._put(bd, {"personal_data": {"naturalidade": "Lisboa"}})

        p = await bd.processes.find_one({"id": "p1"})
        assert not _vazio(p["client_nif"]) and not _vazio(p["personal_data"]["nif_hash"])
