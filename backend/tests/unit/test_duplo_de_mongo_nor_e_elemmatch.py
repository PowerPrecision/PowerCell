"""O duplo de Mongo: `$nor` e `$elemMatch`, um nível ABAIXO (Lote 6).

PORQUE É QUE ESTE FICHEIRO EXISTE
=================================
A regra Sub35 dos `co_buyers` (D-17) precisa do quantificador **todos os
elementos do array**, e no Mongo não há forma POSITIVA de o dizer: escreve-se
"não existe elemento que falhe" (`$nor` + `$elemMatch`). O `FakeAsyncCollection`
não os implementava, e o teste de concordância entre o filtro e a etiqueta
passaria a confiar nesta implementação.

É o caso da regra do projecto: **quando o duplo implementa a lógica de que o
código depende, é preciso um teste um nível abaixo** — aqui, a semântica dos
dois operadores afirmada directamente, com casos cujo resultado é óbvio sem
olhar para a implementação.

CORRECÇÃO A UMA NOTA ANTIGA
===========================
O `AGENTS.md` dizia que o duplo "ignora" o `$nor`. Não ignorava: o `$nor`
caía no `_lookup_path` (devolve `None`), comparava-se com uma lista e a query
deixava de casar com NADA. É fail-closed, e é igualmente enganador — um teste
de filtro mostrava a lista vazia em vez de revelar o defeito.
"""
from __future__ import annotations

from tests.unit.conftest import FakeAsyncCollection as C


class TestNor:
    def test_nor_e_verdadeiro_quando_nenhum_ramo_casa(self):
        assert C._matches({"a": 1}, {"$nor": [{"a": 2}, {"a": 3}]}) is True

    def test_nor_e_falso_quando_UM_ramo_casa(self):
        assert C._matches({"a": 1}, {"$nor": [{"a": 2}, {"a": 1}]}) is False

    def test_nor_vazio_nao_exclui_nada(self):
        assert C._matches({"a": 1}, {"$nor": []}) is True

    def test_nor_combina_com_as_outras_chaves(self):
        doc = {"a": 1, "b": 2}
        assert C._matches(doc, {"b": 2, "$nor": [{"a": 9}]}) is True
        assert C._matches(doc, {"b": 9, "$nor": [{"a": 9}]}) is False

    def test_nor_sobre_campo_AUSENTE(self):
        # "não tem data válida" tem de ser verdadeiro quando não há data.
        assert C._matches({}, {"$nor": [{"d": {"$gte": "2000-01-01"}}]}) is True


class TestElemMatch:
    DOC = {"xs": [{"n": 1, "t": "a"}, {"n": 2, "t": "b"}]}

    def test_casa_quando_UM_elemento_satisfaz_tudo(self):
        assert C._matches(self.DOC, {"xs": {"$elemMatch": {"n": 2, "t": "b"}}}) is True

    def test_NAO_casa_quando_as_condicoes_vivem_em_elementos_DIFERENTES(self):
        """É a diferença entre `$elemMatch` e dois caminhos com ponto.

        `{"xs.n": 1, "xs.t": "b"}` casaria (cada condição encontra o seu
        elemento); o `$elemMatch` exige o MESMO elemento. É isso que faz dele
        o operador certo para "este comprador tem identidade E não tem data".
        """
        assert C._matches(self.DOC, {"xs": {"$elemMatch": {"n": 1, "t": "b"}}}) is False

    def test_array_ausente_nao_casa(self):
        assert C._matches({}, {"xs": {"$elemMatch": {"n": 1}}}) is False

    def test_array_vazio_nao_casa(self):
        assert C._matches({"xs": []}, {"xs": {"$elemMatch": {"n": 1}}}) is False

    def test_elementos_que_nao_sao_dicionarios_sao_ignorados(self):
        assert C._matches({"xs": ["texto", 7]}, {"xs": {"$elemMatch": {"n": 1}}}) is False

    def test_operadores_dentro_do_elemMatch(self):
        assert C._matches(self.DOC, {"xs": {"$elemMatch": {"n": {"$gte": 2}}}}) is True
        assert C._matches(self.DOC, {"xs": {"$elemMatch": {"n": {"$gte": 9}}}}) is False


class TestOsDoisJuntos:
    """`$nor` + `$elemMatch` = "TODOS os elementos cumprem"."""

    @staticmethod
    def _todos_tem_data(doc):
        return C._matches(
            doc, {"$nor": [{"xs": {"$elemMatch": {"d": {"$in": [None, ""]}}}}]}
        )

    def test_array_ausente_conta_como_todos_cumprem(self):
        # Vacuamente verdadeiro — e é o comportamento que se quer: um
        # processo sem `co_buyers` não pode ser excluído por eles.
        assert self._todos_tem_data({}) is True

    def test_todos_com_data(self):
        assert self._todos_tem_data({"xs": [{"d": "1995-01-01"}, {"d": "1996-01-01"}]}) is True

    def test_um_sem_data_chega_para_falhar(self):
        assert self._todos_tem_data({"xs": [{"d": "1995-01-01"}, {"d": ""}]}) is False

    def test_um_com_a_chave_AUSENTE_tambem_falha(self):
        assert self._todos_tem_data({"xs": [{"d": "1995-01-01"}, {"outro": 1}]}) is False
