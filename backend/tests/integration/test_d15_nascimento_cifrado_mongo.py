"""D-15 — datas de nascimento cifradas, contra um MongoDB REAL.

O duplo de teste não prova a semântica de ``$gte``/``$lte`` sobre números nem
de ``$elemMatch`` dentro de listas; e a migração só vale se uma segunda
passagem der «0 a fazer» sobre dados reais. Os documentos nascem pelas
funções de produção (``encrypt_sensitive_data``/``encrypt_client_data``) — não
se escreve na colecção pesquisada nada que a cadeia real não produziria.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import sub35
from services.birthdate_exposure_audit import Relatorio, auditar
from services.encryption import EncryptionService, encryption_service
from services.process_service import encrypt_sensitive_data

pytestmark = pytest.mark.asyncio

HOJE = date(2026, 10, 2)
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrar_datas_de_nascimento.py"


def _script():
    spec = importlib.util.spec_from_file_location("migrar_datas_de_nascimento", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_d15_{uuid.uuid4().hex[:8]}"]
    monkeypatch.setattr("database.db", base)
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _inserir(base, pid, *, cifrado=True, **pessoa):
    doc = {"id": pid, "personal_data": dict(pessoa)}
    await base.processes.insert_one(encrypt_sensitive_data(doc) if cifrado else doc)


async def _ids_do_filtro(base, hoje=HOJE):
    cursor = base.processes.find(sub35.condicao_sub35(hoje), {"_id": 0, "id": 1})
    return {d["id"] async for d in cursor}


async def _ids_com_etiqueta(base, hoje=HOJE):
    return {
        d["id"] async for d in base.processes.find({}, {"_id": 0})
        if sub35.processo_e_sub35(d, hoje)
    }


NASCIMENTOS = {
    "n-1995": "1995-03-15",     # 31 anos
    "n-1991-jan": "1991-01-01",  # 35
    "n-1991-dez": "1991-12-31",  # 34/35
    "n-2025": "2025-06-01",      # criança — Sub35 por regra
    "n-1980": "1980-01-01",
    "n-1990-antes": "1990-03-01",   # margem: já fez 36 este ano
    "n-1990-depois": "1990-12-01",  # margem: ainda tem 35
    "n-futuro": "2030-01-01",
    "n-corrente-passado": "2026-03-01",   # ano corrente
}


class TestOFiltroSobreDadosCifrados:
    async def test_o_filtro_nunca_mostra_uma_linha_sem_etiqueta(self, bd):
        for pid, data in NASCIMENTOS.items():
            await _inserir(bd, pid, birth_date=data, data_nascimento=data)
        filtro = await _ids_do_filtro(bd)
        etiqueta = await _ids_com_etiqueta(bd)
        assert filtro, "a amostra tem de produzir resultados"
        assert filtro <= etiqueta, f"filtro mostra sem etiqueta: {filtro - etiqueta}"

    async def test_os_anos_seguros_estao_todos_no_filtro(self, bd):
        for pid, data in NASCIMENTOS.items():
            await _inserir(bd, pid, birth_date=data)
        filtro = await _ids_do_filtro(bd)
        assert {"n-1995", "n-1991-jan", "n-1991-dez", "n-2025"} <= filtro

    async def test_o_ano_da_margem_fica_de_fora_do_filtro_mas_nao_da_etiqueta(self, bd):
        """O CUSTO da D-15, afirmado: quem faz 36 anos depois de hoje é Sub35 e o filtro já o não vê."""
        for pid in ("n-1990-antes", "n-1990-depois"):
            await _inserir(bd, pid, birth_date=NASCIMENTOS[pid])
        assert await _ids_com_etiqueta(bd) == {"n-1990-depois"}
        assert await _ids_do_filtro(bd) == set()

    async def test_o_futuro_o_ano_corrente_e_os_velhos_ficam_de_fora(self, bd):
        for pid in ("n-futuro", "n-corrente-passado", "n-1980"):
            await _inserir(bd, pid, birth_date=NASCIMENTOS[pid])
        assert await _ids_do_filtro(bd) == set()

    async def test_o_segundo_titular_cifrado_bloqueia_no_filtro(self, bd):
        await bd.processes.insert_one(encrypt_sensitive_data({
            "id": "t2-velho", "personal_data": {"birth_date": "1995-03-15"},
            "titular2_data": {"name": "Rui", "nif": "501964842", "birth_date": "1970-01-01"},
        }))
        await bd.processes.insert_one(encrypt_sensitive_data({
            "id": "t2-novo", "personal_data": {"birth_date": "1995-03-15"},
            "titular2_data": {"name": "Rui", "nif": "501964842", "birth_date": "1996-01-01"},
        }))
        assert await _ids_do_filtro(bd) == {"t2-novo"}
        assert await _ids_com_etiqueta(bd) == {"t2-novo"}

    async def test_um_comprador_adicional_cifrado_bloqueia_no_filtro(self, bd):
        for pid, nasc in (("c-velho", "1970-01-01"), ("c-novo", "2000-01-01")):
            await bd.processes.insert_one(encrypt_sensitive_data({
                "id": pid, "personal_data": {"birth_date": "1995-03-15"},
                "co_buyers": [{"nome": "Ana", "birth_date": nasc}],
            }))
        assert await _ids_do_filtro(bd) == {"c-novo"}
        assert await _ids_com_etiqueta(bd) == {"c-novo"}

    async def test_os_documentos_por_migrar_continuam_a_casar(self, bd):
        # data em claro e sem `birth_year`: a ordem deploy → migração não importa
        await _inserir(bd, "legado", cifrado=False, birth_date="1995-03-15")
        await _inserir(bd, "legado-velho", cifrado=False, birth_date="1970-03-15")
        assert await _ids_do_filtro(bd) == {"legado"}

    async def test_a_data_em_claro_nao_esta_na_base(self, bd):
        await _inserir(bd, "p", birth_date="1995-03-15", data_nascimento="1995-03-15")
        bruto = await bd.processes.find_one({"id": "p"})
        assert "1995-03-15" not in repr(bruto)
        assert bruto["personal_data"]["birth_year"] == 1995


class TestAMigracaoNaBaseReal:
    async def _semear_legado(self, bd):
        await bd.processes.insert_many([
            {"id": "p1", "personal_data": {"nif": encryption_service.encrypt("501964842"),
                                           "birth_date": "1995-03-15", "data_nascimento": "1995-03-15"},
             "co_buyers": [{"nome": "a", "data_nascimento": "2001-07-01"}]},
            {"id": "p2", "personal_data": {"data_nascimento": encryption_service.encrypt("1990-12-01")}},
            {"id": "p3", "birth_date": "1980-05-05"},
            {"id": "p4", "personal_data": {"data_nascimento": datetime(1992, 2, 2)}},
            {"id": "p5", "personal_data": {"data_nascimento": "", "birth_year": 1999}},
        ])
        await bd.clients.insert_one({"id": "c1", "dados_pessoais": {"data_nascimento": "1999-12-31"}})

    async def _em_claro(self, bd):
        rel = Relatorio()
        for colecao in ("processes", "clients"):
            auditar(colecao, [d async for d in getattr(bd, colecao).find({}, {"_id": 0})], rel)
        return sum(rel.documentos_com_data_em_claro.values())

    async def test_cifra_tudo_e_a_segunda_passagem_nao_tem_nada_a_fazer(self, bd):
        modulo = _script()
        await self._semear_legado(bd)
        assert await self._em_claro(bd) > 0

        primeira = await modulo.migrar(aplicar=True)
        assert sum(primeira["escritos"].values()) == 6   # 5 processos + 1 cliente
        assert await self._em_claro(bd) == 0

        segunda = await modulo.migrar(aplicar=True)
        assert sum(segunda["com_pendencias"].values()) == 0
        assert sum(segunda["escritos"].values()) == 0

    async def test_a_omissao_nao_escreve_nada(self, bd):
        modulo = _script()
        await self._semear_legado(bd)
        antes = [d async for d in bd.processes.find({}, {"_id": 0})]
        relatorio = await modulo.migrar(aplicar=False)
        assert sum(relatorio["com_pendencias"].values()) > 0
        assert [d async for d in bd.processes.find({}, {"_id": 0})] == antes

    async def test_os_dados_ficam_legiveis_e_a_etiqueta_nao_muda(self, bd):
        modulo = _script()
        await self._semear_legado(bd)
        antes = await _ids_com_etiqueta(bd)
        await modulo.migrar(aplicar=True)
        assert await _ids_com_etiqueta(bd) == antes
        p1 = await bd.processes.find_one({"id": "p1"})
        assert p1["personal_data"]["birth_year"] == 1995
        assert p1["co_buyers"][0]["birth_year"] == 2001
        assert encryption_service.decrypt(p1["personal_data"]["birth_date"]) == "1995-03-15"
        p4 = await bd.processes.find_one({"id": "p4"})
        assert encryption_service.decrypt(p4["personal_data"]["data_nascimento"]) == "1992-02-02"
        p5 = await bd.processes.find_one({"id": "p5"})
        assert p5["personal_data"]["birth_year"] is None

    async def test_nao_mexe_em_updated_at_nem_em_ids(self, bd):
        modulo = _script()
        await bd.processes.insert_one({"id": "p", "updated_at": "ontem", "personal_data": {"birth_date": "1995-03-15"}})
        await modulo.migrar(aplicar=True)
        p = await bd.processes.find_one({"id": "p"})
        assert p["updated_at"] == "ontem"

    async def test_uma_edicao_a_meio_nao_e_pisada(self, bd):
        from services.birthdate_migration import filtro_de_escrita, planear

        await bd.processes.insert_one({"id": "p", "personal_data": {"birth_date": "1995-03-15"}})
        doc = await bd.processes.find_one({"id": "p"})
        plano = planear(doc)
        # alguém edita a data entre a leitura e a escrita
        await bd.processes.update_one({"id": "p"}, {"$set": {"personal_data.birth_date": "1996-04-16"}})
        resultado = await bd.processes.update_one(filtro_de_escrita(doc["_id"], plano), {"$set": plano.definir})
        assert resultado.modified_count == 0
        assert (await bd.processes.find_one({"id": "p"}))["personal_data"]["birth_date"] == "1996-04-16"

    async def test_uma_cifra_ilegivel_nao_e_tocada(self, bd):
        modulo = _script()
        await bd.processes.insert_one({"id": "p", "personal_data": {"birth_date": "ENC:nao-abre", "birth_year": 1990}})
        relatorio = await modulo.migrar(aplicar=True)
        assert sum(relatorio["escritos"].values()) == 0
        p = await bd.processes.find_one({"id": "p"})
        assert p["personal_data"] == {"birth_date": "ENC:nao-abre", "birth_year": 1990}


class TestAProvaDaChave:
    async def test_a_chave_certa_abre_o_que_ja_esta_cifrado(self, bd):
        modulo = _script()
        await bd.processes.insert_one({"id": "p", "personal_data": {"nif": encryption_service.encrypt("501964842")}})
        experimentados, abertos = await modulo.a_chave_abre_o_que_ja_esta_cifrado(bd)
        assert (experimentados, abertos) == (1, 1)

    async def test_uma_chave_diferente_nao_abre_nada(self, bd, monkeypatch):
        modulo = _script()
        await bd.processes.insert_one({"id": "p", "personal_data": {"nif": encryption_service.encrypt("501964842")}})
        monkeypatch.setenv("ENCRYPTION_KEY", "uma-chave-que-nao-e-a-de-producao-123456")
        monkeypatch.setattr(modulo, "encryption_service", EncryptionService())
        experimentados, abertos = await modulo.a_chave_abre_o_que_ja_esta_cifrado(bd)
        assert experimentados == 1 and abertos == 0

    async def test_sem_valores_cifrados_nao_ha_prova_mas_nao_ha_erro(self, bd):
        modulo = _script()
        await bd.processes.insert_one({"id": "p", "personal_data": {"birth_date": "1995-03-15"}})
        assert await modulo.a_chave_abre_o_que_ja_esta_cifrado(bd) == (0, 0)


def test_recusa_escrever_sem_cifra_disponivel(monkeypatch, capsys):
    modulo = _script()
    monkeypatch.setattr(modulo.encryption_service, "is_available", lambda: False)
    assert modulo.main(["--aplicar"]) == 3
    assert "RECUSADO" in capsys.readouterr().out
