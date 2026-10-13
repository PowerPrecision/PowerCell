"""O script de limpeza das cópias órfãs de ``system_config`` contra um MongoDB REAL.

Um duplo in-memory não prova o ``$regex`` sobre ``_id`` nem a eliminação
condicional — e este script apaga em produção.
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from models.system_config import SystemConfig

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "limpar_copias_orfas_system_config.py"


def _script():
    spec = importlib.util.spec_from_file_location("limpar_copias_orfas", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _global() -> dict:
    doc = SystemConfig(company_id="default").model_dump(mode="json")
    doc["_id"] = "main"
    doc["email"]["smtp_user"] = "geral@power.pt"
    doc["updated_at"] = "2026-09-01T00:00:00+00:00"
    return doc


def _copia(empresa: str, glob: dict, **mudancas) -> dict:
    doc = copy.deepcopy(glob)
    doc.update({"_id": f"company:{empresa}", "company_id": empresa, "setup_completed": False,
                "updated_at": "2026-09-02T00:00:00+00:00"})
    for caminho, valor in mudancas.items():
        seccao, _, campo = caminho.partition(".")
        doc[seccao][campo] = valor
    return doc


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_orfas_{uuid.uuid4().hex[:8]}"]
    glob = _global()
    await base.system_config.insert_many([
        glob,
        _copia("cmp-igual", glob),
        _copia("cmp-igual-2", glob),
        _copia("cmp-propria", glob, **{"email.smtp_user": "domus@domus.pt"}),
        _copia("cmp-fantasma", glob),
        # Outros documentos da MESMA colecção que nunca podem ser tocados.
        {"_id": "rgpd_template", "conteudo": "x"},
        {"_id": "minuta_template", "conteudo": "y"},
        {"_id": "finance_config", "valor": 1},
        {"type": "cache_settings", "ttl": 5},
        {"_id": "companyX", "nao": "é prefixo company:"},
    ])
    await base.companies.insert_many([{"id": "cmp-igual"}, {"id": "cmp-igual-2"}, {"id": "cmp-propria"}])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _ids(bd):
    return {str(d["_id"]) for d in await bd.system_config.find({}).to_list(100)}


async def _classificar(bd, s):
    from services.system_config_orphans import classificar_todas

    doc_global, docs, empresas = await s._carregar(bd)
    return docs, classificar_todas(docs, doc_global, empresas)


@pytest.mark.asyncio
async def test_a_leitura_encontra_so_as_company_e_classifica(bd):
    s = _script()
    docs, veredictos = await _classificar(bd, s)
    assert {d["_id"] for d in docs} == {
        "company:cmp-igual", "company:cmp-igual-2", "company:cmp-propria", "company:cmp-fantasma",
    }
    por_id = {v.doc_id: v.veredicto for v in veredictos}
    assert por_id == {
        "company:cmp-igual": "copia_identica",
        "company:cmp-igual-2": "copia_identica",
        "company:cmp-propria": "divergente",
        "company:cmp-fantasma": "copia_sem_empresa",
    }


@pytest.mark.asyncio
async def test_aplicar_apaga_so_as_identicas_e_nada_mais(bd):
    from services.system_config_orphans import a_apagar

    s = _script()
    docs, veredictos = await _classificar(bd, s)
    por_id = {d["_id"]: d for d in docs}
    for v in a_apagar(veredictos):
        assert await s._apagar(bd, por_id[v.doc_id]) is True
    assert await _ids(bd) == {
        "main", "company:cmp-propria", "company:cmp-fantasma",
        "rgpd_template", "minuta_template", "finance_config", "companyX",
    } | {str(d["_id"]) for d in await bd.system_config.find({"type": "cache_settings"}).to_list(5)}


@pytest.mark.asyncio
async def test_com_a_bandeira_apaga_tambem_o_fantasma_mas_nunca_a_divergente(bd):
    from services.system_config_orphans import a_apagar

    s = _script()
    docs, veredictos = await _classificar(bd, s)
    por_id = {d["_id"]: d for d in docs}
    for v in a_apagar(veredictos, incluir_sem_empresa=True):
        await s._apagar(bd, por_id[v.doc_id])
    ids = await _ids(bd)
    assert "company:cmp-fantasma" not in ids
    assert "company:cmp-propria" in ids


@pytest.mark.asyncio
async def test_se_alguem_gravou_entre_a_leitura_e_a_eliminacao_nao_se_apaga(bd):
    s = _script()
    docs, _ = await _classificar(bd, s)
    lido = next(d for d in docs if d["_id"] == "company:cmp-igual")
    # Outra pessoa grava a configuração da empresa (muda o updated_at).
    await bd.system_config.update_one(
        {"_id": "company:cmp-igual"},
        {"$set": {"email.smtp_user": "novo@x.pt", "updated_at": "2026-10-13T09:00:00+00:00"}},
    )
    assert await s._apagar(bd, lido) is False
    assert "company:cmp-igual" in await _ids(bd)


@pytest.mark.asyncio
async def test_a_segunda_passagem_nao_encontra_nada_para_apagar(bd):
    from services.system_config_orphans import a_apagar

    s = _script()
    docs, veredictos = await _classificar(bd, s)
    por_id = {d["_id"]: d for d in docs}
    for v in a_apagar(veredictos):
        await s._apagar(bd, por_id[v.doc_id])
    _, veredictos2 = await _classificar(bd, s)
    assert a_apagar(veredictos2) == []


def test_o_script_so_apaga_com_aplicar_e_so_toca_em_company():
    """Guarda por fonte: a omissão lê; a eliminação é condicional e com prefixo."""
    from tests.unit.helpers_fonte import codigo_sem_comentarios

    s = _script()
    fonte = codigo_sem_comentarios(SCRIPT.read_text(encoding="utf-8"))
    assert fonte.count("delete_one") == 1 and "delete_many" not in fonte
    # `ast.unparse` normaliza as aspas: compara-se sem elas.
    assert "'updated_at': doc.get('updated_at')" in fonte
    assert "if args.aplicar:" in fonte
    assert s.PREFIXO == "company:"
