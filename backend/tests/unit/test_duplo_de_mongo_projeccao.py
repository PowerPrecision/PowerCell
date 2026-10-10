"""A projecção de inclusão do duplo de Mongo, com dot-notation.

O duplo passa a implementar lógica em que os testes confiam; a semântica
afirma-se um nível abaixo (e foi confirmada contra um `mongod` real).
"""
import pytest

from tests.unit.conftest import FakeAsyncCursor

DOC = {
    "id": "p1", "client_name": "Silva",
    "real_estate_data": {"data_cpcv": "2026-10-05", "valor_imovel": 300000, "morada": "Rua X"},
}


async def _proj(projecao):
    return (await FakeAsyncCursor([dict(DOC)], projecao).to_list(None))[0]


@pytest.mark.asyncio
async def test_um_campo_aninhado_copia_so_esse_campo():
    assert await _proj({"id": 1, "real_estate_data.data_cpcv": 1}) == {
        "id": "p1", "real_estate_data": {"data_cpcv": "2026-10-05"},
    }


@pytest.mark.asyncio
async def test_dois_campos_do_mesmo_contentor_juntam_se():
    r = await _proj({"real_estate_data.data_cpcv": 1, "real_estate_data.valor_imovel": 1})
    assert r == {"real_estate_data": {"data_cpcv": "2026-10-05", "valor_imovel": 300000}}


@pytest.mark.asyncio
async def test_como_o_mongo_real_um_contentor_existente_sem_a_folha_fica_vazio():
    """Verificado contra um mongod: `{'a.nao': 1}` devolve `{'a': {}}`; um
    contentor que não existe não devolve nada."""
    assert await _proj({"id": 1, "real_estate_data.nao_existe": 1}) == {"id": "p1", "real_estate_data": {}}
    assert await _proj({"id": 1, "outro.a.b": 1}) == {"id": "p1"}


@pytest.mark.asyncio
async def test_o_campo_de_topo_continua_a_funcionar():
    assert await _proj({"client_name": 1}) == {"client_name": "Silva"}


@pytest.mark.asyncio
async def test_a_exclusao_nao_mudou():
    r = await _proj({"real_estate_data": 0})
    assert "real_estate_data" not in r and r["id"] == "p1"
