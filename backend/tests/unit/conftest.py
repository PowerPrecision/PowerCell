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

import re
from unittest.mock import MagicMock

import pytest


class FakeAsyncCursor:
    """Cursor assíncrono mínimo (PACOTE 8 — find/sort/skip/limit/to_list).

    Imita o encadeamento do Motor o suficiente para exercitar serviços
    que listam documentos (``find(...).sort(...).to_list(n)``).
    Determinístico: ordenação lexicográfica simples das chaves dadas.
    """

    def __init__(self, docs: list, projection: dict = None):
        self._docs = docs
        self._projection = dict(projection) if projection else None
        self._skip = 0
        self._limit = None

    def sort(self, key_or_list, direction=1):
        def sort_key(doc: dict):
            if isinstance(key_or_list, (list, tuple)) and key_or_list:
                if isinstance(key_or_list[0], (list, tuple)):
                    return tuple(str(doc.get(k) or "") for k, _ in key_or_list)
                return tuple(str(doc.get(k) or "") for k in key_or_list)
            return str(doc.get(key_or_list) or "")

        self._docs = sorted(self._docs, key=sort_key)
        return self

    def skip(self, n: int):
        self._skip = n
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    async def to_list(self, length=None):
        docs = self._docs[self._skip:]
        if self._limit is not None:
            docs = docs[: self._limit]
        elif length is not None:
            docs = docs[:length]
        if self._projection:
            include = {k for k, v in self._projection.items() if v}
            exclude = {k for k, v in self._projection.items() if not v}
            if include:
                docs = [
                    {k: d[k] for k in include if k in d and k not in exclude}
                    for d in docs
                ]
            else:
                docs = [
                    {k: v for k, v in d.items() if k not in exclude}
                    for d in docs
                ]
        return docs

    def __aiter__(self):
        """PACOTE 9 — iteração assíncrona (``async for doc in cursor``),
        usada pelos scripts de manutenção (ex.: backfill_s3_mappings).
        """
        return self._iterate()

    async def _iterate(self):
        docs = await self.to_list(None)
        for doc in docs:
            yield doc


class FakeAsyncCollection:
    """Coleção assíncrona em memória (substituto leve do Motor).

    Implementa apenas o subconjunto de operações usado pelos serviços sob
    teste: `find_one` (igualdade e `$ne`), `insert_one`, `update_one`
    (`$set` + `$push` escalar/`$each`, com upsert), `delete_one` e
    `count_documents`. Não é um clone do Motor — é determinística e não
    faz I/O de rede.
    """

    def __init__(self):
        self.docs: list = []

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        """Matcher: igualdade, ``$ne``, ``$in``, ``$regex``, ``$exists``,
        ``$or``/``$and`` recursivos (PACOTE 8 — os filtros do Webmail usam
        $and/$or/$regex).

        Aproximações determinísticas: ``$regex`` casa contra ``str(valor)``
        (em arrays casa contra a lista stringificada — suficiente para os
        testes); ``$options: i`` activa IGNORECASE.
        """
        for key, expected in query.items():
            if key == "$or":
                if not any(FakeAsyncCollection._matches(doc, q) for q in expected):
                    return False
                continue
            if key == "$and":
                if not all(FakeAsyncCollection._matches(doc, q) for q in expected):
                    return False
                continue
            value = doc.get(key)
            if isinstance(expected, dict):
                matched_operator = False
                if "$ne" in expected:
                    matched_operator = True
                    if value == expected["$ne"]:
                        return False
                if "$in" in expected:
                    matched_operator = True
                    if value not in expected["$in"]:
                        return False
                if "$exists" in expected:
                    matched_operator = True
                    exists = key in doc
                    if bool(expected["$exists"]) is not exists:
                        return False
                if "$regex" in expected:
                    matched_operator = True
                    pattern = expected["$regex"]
                    if value is None:
                        return False
                    flags = re.IGNORECASE if "i" in (expected.get("$options") or "") else 0
                    try:
                        if not re.search(pattern, str(value), flags):
                            return False
                    except re.error:
                        return False
                if not matched_operator and value != expected:
                    return False
            elif value != expected:
                return False
        return True

    async def find_one(self, query: dict, projection: dict = None, sort=None):
        """``find_one`` com ``sort`` opcional (PACOTE 9 — usado por
        ``db.workflow_statuses.find_one({}, ..., sort=[("order", 1)])``).

        Contrato histórico mantido: a projecção é IGNORADA (devolve o doc
        completo) — vários serviços usam projecções com dot-notation
        (ex.: "settings.company_name") e dependem de receber o doc inteiro
        (o Motor real resolve dot-notation; o fake devolve sempre o doc
        completo, que é um superconjunto seguro para os testes).
        """
        matched = [doc for doc in self.docs if self._matches(doc, query)]
        if sort:
            key_or_list = sort
            def sort_key(doc: dict):
                if isinstance(key_or_list, (list, tuple)) and key_or_list:
                    if isinstance(key_or_list[0], (list, tuple)):
                        return tuple(str(doc.get(k) or "") for k, _ in key_or_list)
                    return tuple(str(doc.get(k) or "") for k in key_or_list)
                return str(doc.get(key_or_list) or "")
            matched = sorted(matched, key=sort_key)
        for doc in matched:
            return dict(doc)
        return None

    async def insert_one(self, doc: dict):
        self.docs.append(dict(doc))
        return MagicMock(inserted_id="fake-inserted-id")

    @staticmethod
    def _apply_push(doc: dict, push_ops: dict) -> None:
        """Aplica `$push` (escalar ou {$each: [...]}) — fiel ao Mongo: permite duplicados."""
        for field, value in push_ops.items():
            values = value.get("$each", [value]) if isinstance(value, dict) else [value]
            target = doc.get(field)
            if not isinstance(target, list):
                target = []
                doc[field] = target
            target.extend(values)

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        matched = [doc for doc in self.docs if self._matches(doc, query)]
        for doc in matched:
            doc.update(update.get("$set", {}))
            push_ops = update.get("$push")
            if push_ops:
                self._apply_push(doc, push_ops)
        if matched:
            return MagicMock(matched_count=len(matched), modified_count=len(matched))
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            push_ops = update.get("$push")
            if push_ops:
                self._apply_push(new_doc, push_ops)
            self.docs.append(new_doc)
            return MagicMock(matched_count=0, modified_count=0, upserted_id="fake-upserted-id")
        return MagicMock(matched_count=0, modified_count=0)

    async def insert_many(self, docs: list, ordered: bool = True):
        for doc in docs:
            self.docs.append(dict(doc))
        return MagicMock(inserted_ids=["fake-inserted-id"] * len(docs))

    async def delete_one(self, query: dict):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]
        return MagicMock(deleted_count=before - len(self.docs))

    async def count_documents(self, query: dict) -> int:
        return sum(1 for doc in self.docs if self._matches(doc, query))

    def find(self, query: dict, projection: dict = None):
        """Cursor com sort/skip/limit/to_list (PACOTE 8) — matcher igualdade/$ne/$in."""
        matched = [dict(doc) for doc in self.docs if self._matches(doc, query)]
        return FakeAsyncCursor(matched, projection)

    async def update_many(self, query: dict, update: dict, upsert: bool = False):
        return await self.update_one(query, update, upsert=upsert)


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
