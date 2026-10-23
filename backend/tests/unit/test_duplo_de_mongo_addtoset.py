"""O duplo de Mongo implementa `$addToSet` — e a semântica é afirmada um nível abaixo.

Os testes da associação de redes (D-42) confiam neste operador: se o duplo
duplicasse elementos ou ignorasse o `$each`, uma associação repetida
«passava» por idempotente sem o ser.
"""
import pytest


@pytest.mark.asyncio
async def test_addtoset_cria_a_lista_e_nao_duplica(fake_async_db):
    fake_async_db.clients.docs.append({"id": "c1"})
    await fake_async_db.clients.update_one({"id": "c1"}, {"$addToSet": {"redes": "A"}})
    await fake_async_db.clients.update_one({"id": "c1"}, {"$addToSet": {"redes": "A"}})
    await fake_async_db.clients.update_one({"id": "c1"}, {"$addToSet": {"redes": "B"}})
    assert fake_async_db.clients.docs[0]["redes"] == ["A", "B"]


@pytest.mark.asyncio
async def test_addtoset_each_acrescenta_so_o_que_falta_e_guarda_a_ordem(fake_async_db):
    fake_async_db.clients.docs.append({"id": "c1", "redes": ["B"]})
    await fake_async_db.clients.update_one(
        {"id": "c1"}, {"$addToSet": {"redes": {"$each": ["A", "B", "A", "C"]}}},
    )
    assert fake_async_db.clients.docs[0]["redes"] == ["B", "A", "C"]


@pytest.mark.asyncio
async def test_addtoset_num_campo_que_nao_e_lista_recomeca_como_lista(fake_async_db):
    fake_async_db.clients.docs.append({"id": "c1", "redes": None})
    await fake_async_db.clients.update_one({"id": "c1"}, {"$addToSet": {"redes": "A"}})
    assert fake_async_db.clients.docs[0]["redes"] == ["A"]
