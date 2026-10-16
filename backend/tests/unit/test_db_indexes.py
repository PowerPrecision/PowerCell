"""
====================================================================
TESTES UNITÁRIOS - SERVIÇO DE ÍNDICES MONGODB
====================================================================
Testes para o serviço de criação e gestão de índices.
====================================================================
"""

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
        """CONTRAPROVA do registo — sem ela, trocava-se um placebo por outro.

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
        from services.db_indexes import colecoes_com_indices

        listadas = colecoes_com_indices()
        for name in ("emails", "user_company_roles", "notifications", "companies"):
            assert name in listadas


# ====================================================================
# AS DEFINIÇÕES REAIS
# ====================================================================
# Este ficheiro tinha aqui uma `get_index_definitions()` que devolvia uma CÓPIA das definições,
# escrita à mão, e a seguir fazia `sys.modules['services.db_indexes'] = type(sys)(...)` —
# substituindo o módulo INTEIRO por um objecto vazio. Os testes validavam o duplo e não o código
# (a cópia tinha seis índices de `processes`; o real tinha dezoito), e o `sys.modules` envenenado
# sobrevivia à sessão do pytest.
#
# Depois, enquanto as definições eram literais LOCAIS de `create_indexes`, a leitura era por AST.
# Desde a D-10 (Lote 5) vivem num registo ao nível do módulo — `INDEX_DEFINITIONS` — e este
# ficheiro IMPORTA-o: o leitor por AST, com a sua contraprova, deixou de ser necessário.
# A contraprova que fica é a mesma de sempre: os mínimos folgados abaixo são o alarme para o dia
# em que o registo deixar de ter o conteúdo que tem.
def get_index_definitions() -> dict:
    """As definições REAIS (cópia profunda: um teste não pode alterar o registo de outro)."""
    import copy

    from services.db_indexes import INDEX_DEFINITIONS

    return copy.deepcopy(INDEX_DEFINITIONS)


# ====================================================================
# D-10 (Lote 5): O REGISTO É A FONTE ÚNICA
# ====================================================================
class TestORegistoEAFonteUnica:
    def test_nenhum_indice_ficou_escrito_dentro_de_uma_funcao(self):
        """Uma lista local de índices dentro de uma função é exactamente o defeito que a D-10 fechou."""
        import ast
        import pathlib

        fonte = pathlib.Path(__file__).resolve().parents[2] / "services" / "db_indexes.py"
        arvore = ast.parse(fonte.read_text(encoding="utf-8"))
        for no in arvore.body:
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for interno in ast.walk(no):
                if isinstance(interno, ast.Dict):
                    chaves = {k.value for k in interno.keys if isinstance(k, ast.Constant)}
                    try:
                        ast.literal_eval(interno)
                        e_literal = True
                    except ValueError:
                        e_literal = False  # um dicionário MONTADO (o construtor dos TTL) não é uma definição
                    assert not ({"keys", "name"} <= chaves and e_literal), (
                        f"definição de índice dentro de `{no.name}` (linha {interno.lineno}): "
                        "declare-a com `_definir(...)` ao nível do módulo"
                    )

    def test_create_indexes_itera_o_registo_e_cria_tudo_o_que_ele_declara(self):
        import asyncio

        import services.db_indexes as di

        criadas = []

        async def falso(colecao, idx, nome, results):
            criadas.append((nome, idx["name"]))

        class Db:
            def __getattr__(self, nome):
                return type("C", (), {"nome": nome})()

        with patch.object(di, "_create_index_safe", falso), \
                patch.object(di, "cleanup_deprecated_indexes", AsyncMock(return_value={})), \
                patch.object(di, "_preparar_indices", AsyncMock()), \
                patch.object(di, "create_ttl_indexes", AsyncMock(return_value={})):
            asyncio.run(di.create_indexes(Db()))

        esperadas = [(c, i["name"]) for c, lista in di.INDEX_DEFINITIONS.items() for i in lista]
        assert criadas == esperadas
        assert len(criadas) >= 100, "alarme: o registo deixou de ter o conteúdo que tem"

    def test_cada_definicao_tem_nome_e_chaves_e_os_nomes_nao_se_repetem_por_colecao(self):
        from services.db_indexes import INDEX_DEFINITIONS

        for colecao, lista in INDEX_DEFINITIONS.items():
            nomes = [i["name"] for i in lista]
            assert all(i.get("name") and i.get("keys") for i in lista), colecao
            assert len(nomes) == len(set(nomes)), f"nome de índice repetido em {colecao}: {nomes}"

    def test_o_painel_de_diagnostico_cobre_todas_as_colecoes_indexadas(self):
        from services.db_indexes import INDEX_DEFINITIONS, TTL_INDEXES, colecoes_com_indices

        todas = set(colecoes_com_indices())
        assert set(INDEX_DEFINITIONS) <= todas
        assert {i["collection"] for i in TTL_INDEXES} <= todas
        assert {"partners", "task_queue", "workflow_statuses"} <= todas  # as que a lista à mão nunca teve

    def test_uma_colecao_inexistente_e_vazia_e_nao_avariada(self):
        import asyncio

        from services.db_indexes import get_index_stats

        class NaoExiste(Exception):
            code = 26

        class Col:
            async def index_information(self):
                raise NaoExiste("ns not found")

        class Db:
            def __getattr__(self, nome):
                return Col()

        stats = asyncio.run(get_index_stats(Db()))
        assert stats["partners"] == {"count": 0, "indexes": []}


class TestArranqueSemBaseDeDadosAlcancavel:
    """Incidente de deploy (16 Out 2026): com o Atlas inalcançável cada índice esperava os seus
    30 s de `serverSelectionTimeout` — o arranque passava os 15 min que o Render dá à porta
    e o deploy morria em «Timed Out» sem causa visível. A criação de índices tem de falhar
    RÁPIDO e DIZER porquê; e uma falha que não é de ligação não pode ser tratada como tal."""

    def _db(self, ping):
        class Db:
            command = staticmethod(ping)

            def __getattr__(self, nome):
                return type("C", (), {"nome": nome})()

        return Db()

    def test_sem_ping_nao_se_tenta_criar_nenhum_indice(self):
        import asyncio

        from pymongo.errors import ServerSelectionTimeoutError

        import services.db_indexes as di

        async def ping_falha(*_a, **_k):
            raise ServerSelectionTimeoutError("timed out")

        criar = AsyncMock()
        limpar = AsyncMock(return_value={})
        with patch.object(di, "_create_index_safe", criar), \
                patch.object(di, "cleanup_deprecated_indexes", limpar), \
                patch.object(di, "create_ttl_indexes", AsyncMock()):
            resultado = asyncio.run(di.create_indexes(self._db(ping_falha)))

        assert resultado["indisponivel"] is True
        assert resultado["created"] == []
        criar.assert_not_called()
        limpar.assert_not_called()

    def test_com_ping_a_responder_cria_tudo_como_antes(self):
        import asyncio

        import services.db_indexes as di

        async def ping_ok(*_a, **_k):
            return {"ok": 1}

        criadas = []

        async def falso(colecao, idx, nome, results):
            criadas.append(idx["name"])

        with patch.object(di, "_create_index_safe", falso), \
                patch.object(di, "cleanup_deprecated_indexes", AsyncMock(return_value={})), \
                patch.object(di, "_preparar_indices", AsyncMock()), \
                patch.object(di, "create_ttl_indexes", AsyncMock(return_value={})):
            resultado = asyncio.run(di.create_indexes(self._db(ping_ok)))

        assert not resultado.get("indisponivel")
        assert len(criadas) >= 100

    def test_um_erro_que_nao_e_de_ligacao_no_ping_nao_aborta(self):
        import asyncio

        import services.db_indexes as di

        async def ping_estranho(*_a, **_k):
            raise ValueError("não é uma falha de ligação")

        assert asyncio.run(di._base_de_dados_alcancavel(self._db(ping_estranho))) is True

    def test_a_ligacao_cair_a_meio_para_o_resto_em_vez_de_esperar_por_cada_indice(self):
        import asyncio

        from pymongo.errors import NetworkTimeout

        import services.db_indexes as di

        async def ping_ok(*_a, **_k):
            return {"ok": 1}

        chamadas = []

        class Colecao:
            async def create_index(self, *_a, **_k):
                chamadas.append(1)
                raise NetworkTimeout("timed out")

        class Db:
            command = staticmethod(ping_ok)

            def __getattr__(self, nome):
                return Colecao()

        with patch.object(di, "cleanup_deprecated_indexes", AsyncMock(return_value={})), \
                patch.object(di, "_preparar_indices", AsyncMock()), \
                patch.object(di, "create_ttl_indexes", AsyncMock()) as ttl:
            resultado = asyncio.run(di.create_indexes(Db()))

        assert resultado["indisponivel"] is True
        assert len(chamadas) == 1, "continuou a tentar índices com a base de dados em baixo"
        ttl.assert_not_called()

    def test_um_erro_de_operacao_num_indice_nao_para_os_restantes(self):
        """Contraprova: só a falha de LIGAÇÃO trava; um índice mau não pode esconder os outros."""
        import asyncio

        import services.db_indexes as di

        async def ping_ok(*_a, **_k):
            return {"ok": 1}

        chamadas = []

        class Colecao:
            async def create_index(self, *_a, **_k):
                chamadas.append(1)
                raise RuntimeError("índice inválido")

        class Db:
            command = staticmethod(ping_ok)

            def __getattr__(self, nome):
                return Colecao()

        with patch.object(di, "cleanup_deprecated_indexes", AsyncMock(return_value={})), \
                patch.object(di, "_preparar_indices", AsyncMock()), \
                patch.object(di, "create_ttl_indexes", AsyncMock(return_value={})):
            resultado = asyncio.run(di.create_indexes(Db()))

        assert not resultado.get("indisponivel")
        assert len(chamadas) >= 100
