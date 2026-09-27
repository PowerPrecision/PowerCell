"""
====================================================================
TESTES UNITÁRIOS - SERVIÇO DE ÍNDICES MONGODB
====================================================================
Testes para o serviço de criação e gestão de índices.
====================================================================
"""
import ast
import pathlib

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestIndexCreation:
    """Testes para criação de índices."""
    
    def test_process_indexes_definition(self):
        """Verifica definição de índices de processos."""
        definitions = get_index_definitions()
        
        # Verificar que índices essenciais estão definidos
        assert "processes" in definitions
        
        process_indexes = definitions["processes"]
        index_names = [idx.get("name") for idx in process_indexes]
        
        # Índices obrigatórios
        assert "idx_status" in index_names
        assert "idx_client_email" in index_names
        assert "idx_created_at_desc" in index_names
        
        # Novos índices compostos
        assert "idx_status_consultor" in index_names
        assert "idx_status_mediador" in index_names
        assert "idx_email_status" in index_names
    
    def test_o_leitor_das_definicoes_le_mesmo_o_modulo(self):
        """CONTRAPROVA do leitor por AST — sem ela, trocava-se um placebo por outro.

        Todas as asserções deste ficheiro são da forma `"idx_x" in nomes`.
        Um leitor que devolvesse pouco continuaria a passá-las enquanto o
        pouco bastasse, e é assim que a cópia antiga sobreviveu anos: tinha
        2 colecções e 6 índices de `processes`, contra as 13 e 18 reais.

        Os mínimos aqui são deliberadamente folgados — não são uma contagem
        a manter em dia, são um alarme para o caso de o leitor deixar de
        ler (uma mudança na forma do `create_indexes`, um `for` que passe a
        chamar outra função).
        """
        definitions = get_index_definitions()

        assert len(definitions) >= 10, (
            f"o leitor só encontrou {len(definitions)} colecções — deixou de ler o módulo"
        )
        assert len(definitions["processes"]) >= 15
        # E os índices têm de vir com conteúdo, não dicionários vazios.
        assert all(
            idx.get("name") and idx.get("keys")
            for idx in definitions["processes"]
        )

    def test_indice_do_bi_por_rede_esta_declarado(self):
        """O índice composto que TODAS as agregações do BI usam.

        Desde o Lote 4 nenhuma listagem nem agregação de BI corre sem
        filtrar por rede, e quase todas juntam-lhe `is_deleted` e
        `status` (`stats_funnel`, `stats_branches`, `stats_overview`).
        Estava registado no `worklog.md` como uma tarefa MANUAL de
        produção ("criar na mesma janela do backfill") — e uma tarefa
        manual é uma tarefa que se esquece: os logs do arranque de
        produção de 2026-09-27 mostram `idx_network_id` e
        `idx_s3_folder` a serem criados sozinhos e este a faltar.

        Declarar aqui é o que o torna idempotente e automático, como os
        outros. A ORDEM das chaves é a do prefixo mais selectivo para o
        menos (`network_id` está em tudo; `status` só em algumas), que é
        o que permite ao Mongo usar o mesmo índice para uma consulta que
        só traga os dois primeiros campos.
        """
        processes = get_index_definitions()["processes"]
        por_nome = {idx.get("name"): idx for idx in processes}

        assert "idx_network_scope" in por_nome, (
            "sem este índice, cada agregação do BI varre a colecção inteira"
        )
        assert por_nome["idx_network_scope"]["keys"] == [
            ("network_id", 1),
            ("is_deleted", 1),
            ("status", 1),
        ]

    def test_user_indexes_definition(self):
        """Índices de `users` — e o que importa é a UNICIDADE, não o nome.

        Este teste procurava `idx_email_unique`, um nome que NUNCA existiu
        no `db_indexes.py`: era invenção da cópia que este ficheiro
        mantinha, e passava por isso. O índice real chama-se `idx_email`.

        A asserção passou a ser sobre a propriedade que o login depende —
        `unique: True` —, que é o que impede duas contas com o mesmo
        email. Um nome é uma etiqueta; a unicidade é a regra.
        """
        definitions = get_index_definitions()

        assert "users" in definitions
        por_nome = {idx.get("name"): idx for idx in definitions["users"]}

        assert "idx_email" in por_nome
        assert por_nome["idx_email"]["keys"] == [("email", 1)]
        assert por_nome["idx_email"].get("unique") is True, (
            "sem unicidade no email, duas contas podem partilhar o login"
        )
        assert por_nome["idx_user_id"].get("unique") is True

    
    def test_index_structure(self):
        """Verifica estrutura dos índices."""
        definitions = get_index_definitions()
        
        for collection, indexes in definitions.items():
            for idx in indexes:
                # Cada índice deve ter keys e name
                assert "keys" in idx, f"Índice em {collection} sem keys"
                assert "name" in idx, f"Índice em {collection} sem name"
                
                # keys deve ser lista de tuplos
                assert isinstance(idx["keys"], list)
                for key in idx["keys"]:
                    if isinstance(key, tuple):
                        assert len(key) == 2
                        # A direcção é 1/-1 ou um TIPO de índice do Mongo.
                        # A cópia que este ficheiro mantinha só tinha
                        # inteiros, e por isso este teste "provava" que
                        # não há índices de texto — quando `processes` tem
                        # um (`idx_text_search`) desde sempre. A lista é
                        # fechada de propósito: aceitar qualquer string
                        # deixaria passar uma gralha como `("nome", "txt")`,
                        # que o Mongo recusa só no arranque.
                        assert key[1] in (1, -1, "text", "hashed", "2dsphere"), (
                            f"direcção inesperada em {collection}.{idx['name']}: {key[1]!r}"
                        )


class TestPacoteFfCriticalIndexes:
    """Pacote FF — índices críticos em emails e user_company_roles."""

    def _source(self) -> str:
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[2] / "services" / "db_indexes.py"
        ).read_text()

    def test_emails_id_unique_index(self):
        src = self._source()
        assert '{"keys": [("id", 1)], "name": "idx_emails_id", "unique": True}' in src

    def test_emails_mailbox_compound_index(self):
        src = self._source()
        assert '("company_id", 1), ("direction", 1), ("sent_at", -1)' in src
        assert "idx_emails_mailbox" in src

    def test_emails_process_timeline_index(self):
        src = self._source()
        assert '("process_id", 1), ("sent_at", 1)' in src
        assert "idx_emails_process_timeline" in src

    def test_emails_message_dedup_index(self):
        src = self._source()
        assert '("message_id", 1), ("account", 1)' in src
        assert "idx_emails_message_dedup" in src

    def test_ucr_id_unique_index(self):
        src = self._source()
        assert '{"keys": [("id", 1)], "name": "idx_ucr_id", "unique": True}' in src


class TestIndexStats:
    """Testes para estatísticas de índices."""

    def _source(self) -> str:
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[2] / "services" / "db_indexes.py"
        ).read_text()

    def test_get_index_stats_lists_fj_collections(self):
        src = self._source()
        stats_block = src.split("async def get_index_stats")[1].split("return stats")[0]
        for name in ("emails", "user_company_roles", "notifications", "companies"):
            assert f'"{name}"' in stats_block


# ====================================================================
# AS DEFINIÇÕES REAIS, LIDAS DO CÓDIGO
# ====================================================================
# Este ficheiro tinha aqui uma `get_index_definitions()` que devolvia uma
# CÓPIA das definições, escrita à mão, e a seguir fazia
#
#     sys.modules['services.db_indexes'] = type(sys)('services.db_indexes')
#     sys.modules['services.db_indexes'].get_index_definitions = ...
#
# — substituindo o módulo INTEIRO por um objecto vazio. Duas consequências:
#
#   1. Os testes validavam o duplo e não o código. A cópia tinha seis
#      índices de `processes`; o módulo real tem dezoito. Qualquer
#      asserção passava com o `db_indexes.py` a declarar o que quisesse,
#      e foi assim que `idx_network_scope` pôde faltar em produção sem
#      um teste vermelho. Terceira variante da lição "um duplo que
#      reimplementa a lógica valida o duplo".
#
#   2. O `sys.modules` envenenado sobrevivia à sessão do pytest: qualquer
#      módulo importado DEPOIS deste via um `services.db_indexes` vazio.
#      O `test_db_index_stats.py` rebentava com "cannot import name
#      'get_index_stats' (unknown location)" — e só não parte o CI porque
#      a ordem alfabética o coloca antes. É a armadilha da ordem de
#      importação que o AGENTS.md já documenta, agravada: aqui o módulo
#      não é apenas patchado, é apagado.
#
# As definições vivem em literais LOCAIS dentro de `create_indexes`, pelo
# que a leitura é por AST. A associação lista → colecção não é adivinhada
# pelo nome da variável: sai do próprio `_create_index_safe(db.<colecção>,
# …)` que a consome, que é a única fonte que não pode divergir.
def _definicoes_reais() -> dict:
    """Definições de índices lidas de `services/db_indexes.py`."""
    caminho = (
        pathlib.Path(__file__).resolve().parents[2] / "services" / "db_indexes.py"
    )
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))

    funcao = next(
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.AsyncFunctionDef) and no.name == "create_indexes"
    )

    # nome da variável -> lista de dicionários de índice
    listas: dict[str, list] = {}
    for no in ast.walk(funcao):
        if isinstance(no, ast.Assign) and isinstance(no.value, ast.List):
            for destino in no.targets:
                if isinstance(destino, ast.Name):
                    listas[destino.id] = [
                        _dicionario(e) for e in no.value.elts if isinstance(e, ast.Dict)
                    ]

    # `for idx in <lista>:` cujo corpo chama `_create_index_safe(db.<colecção>, …)`
    definicoes: dict[str, list] = {}
    for no in ast.walk(funcao):
        if not (isinstance(no, ast.For) and isinstance(no.iter, ast.Name)):
            continue
        for interno in ast.walk(no):
            if (
                isinstance(interno, ast.Call)
                and isinstance(interno.func, ast.Name)
                and interno.func.id == "_create_index_safe"
                and interno.args
                and isinstance(interno.args[0], ast.Attribute)
            ):
                colecao = interno.args[0].attr
                definicoes.setdefault(colecao, []).extend(
                    listas.get(no.iter.id, [])
                )
    return definicoes


def _dicionario(no: ast.Dict) -> dict:
    """Converte um literal de índice em dicionário, ignorando o que não seja literal."""
    saida = {}
    for chave, valor in zip(no.keys, no.values):
        if not isinstance(chave, ast.Constant):
            continue
        try:
            saida[chave.value] = ast.literal_eval(valor)
        except ValueError:
            saida[chave.value] = None
    return saida


def get_index_definitions() -> dict:
    """As definições REAIS. O nome mantém-se para os testes já escritos."""
    return _definicoes_reais()
