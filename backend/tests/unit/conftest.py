"""Fixtures partilhadas dos testes unitários (tests/unit).

REGRA DE ARQUITETURA DE TESTES:
Os testes em `tests/unit/` NÃO dependem de MongoDB vivo. O job
`backend-fast` do CI corre `pytest tests/unit/` SEM serviço de Mongo
(por design — é o job rápido; só `backend-full` e `e2e-smoke` têm Mongo).
Qualquer teste que precise de I/O real contra a base de dados deve:
- mockar a camada `db` no módulo do serviço (padrão estabelecido em
  `test_document_portal_fulfill.py`), usando este módulo; ou
- viver em `tests/integration/` (onde o Mongo é assumido).

As fakes aqui presentes imitam o comportamento do Motor/DatabaseProxy o
suficiente para exercitar os serviços de forma determinística, sem I/O.
"""

from unittest.mock import MagicMock

import pytest


class FakeAsyncCollection:
    """Coleção assíncrona em memória (substituto leve do Motor).

    Implementa apenas o subconjunto de operações usado pelos serviços sob
    teste: `find_one` (igualdade e `$ne`), `insert_one`, `update_one`
    (`$set`, com upsert), `delete_one` e `count_documents`. Não é um clone
    do Motor — é determinística e não faz I/O de rede.
    """

    def __init__(self):
        self.docs: list = []

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        """Matcher mínimo: igualdade simples + operador $ne."""
        for key, expected in query.items():
            value = doc.get(key)
            if isinstance(expected, dict) and "$ne" in expected:
                if value == expected["$ne"]:
                    return False
            elif value != expected:
                return False
        return True

    async def find_one(self, query: dict, projection: dict = None):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, doc: dict):
        self.docs.append(dict(doc))
        return MagicMock(inserted_id="fake-inserted-id")

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        matched = [doc for doc in self.docs if self._matches(doc, query)]
        for doc in matched:
            doc.update(update.get("$set", {}))
        if matched:
            return MagicMock(matched_count=len(matched), modified_count=len(matched))
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)
            return MagicMock(matched_count=0, modified_count=0, upserted_id="fake-upserted-id")
        return MagicMock(matched_count=0, modified_count=0)

    async def delete_one(self, query: dict):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]
        return MagicMock(deleted_count=before - len(self.docs))

    async def count_documents(self, query: dict) -> int:
        return sum(1 for doc in self.docs if self._matches(doc, query))


class FakeAsyncDatabase:
    """Substituto in-memory do `DatabaseProxy` (database.py).

    `fake_db.users` devolve (e cacheia) uma `FakeAsyncCollection` distinta
    por nome de coleção — o mesmo padrão de acesso por atributo do `db`
    real, para os serviços poderem ser patchados sem alterações.
    """

    def __init__(self):
        self._collections: dict = {}

    def __getattr__(self, name: str) -> FakeAsyncCollection:
        # Guard: atributos privados/internos nunca são coleções
        # (evita recursões infinitas com copy/pickle/inspect).
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._collections:
            self._collections[name] = FakeAsyncCollection()
        return self._collections[name]

    def collection(self, name: str) -> FakeAsyncCollection:
        """Acesso explícito a uma coleção (para asserções diretas nos testes)."""
        return getattr(self, name)


@pytest.fixture
def fake_async_db() -> FakeAsyncDatabase:
    """Base de dados fake (nova por teste) para patchar `db` nos serviços.

    Uso típico:
        with patch.object(me modulo_de_servico, "db", fake_async_db):
            await meu_servico.run_x(...)
        stored = await fake_async_db.minha_colecao.find_one({...})
    """
    return FakeAsyncDatabase()
