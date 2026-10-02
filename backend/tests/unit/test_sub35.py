"""Sub35: a regra, as fronteiras e a concordância filtro↔etiqueta.

O TESTE QUE IMPORTA MAIS é o último grupo: o predicado em Python
(`processo_e_sub35`, que decide a ETIQUETA) e a condição Mongo
(`condicao_sub35`, que decide a LISTA FILTRADA) são duas
implementações da mesma pergunta. Se divergirem, o consultor filtra
"Sub35" e recebe linhas sem etiqueta — ou, pior, uma lista a que falta
um processo que está etiquetado no ecrã ao lado. A única defesa é
correr as duas sobre os MESMOS documentos e exigir o mesmo veredicto.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.sub35 import (  # noqa: E402
    CAMPOS_DE_NASCIMENTO,
    CAMPO_DA_FLAG,
    IDADE_EXCLUSIVA,
    IDADE_MAXIMA_INCLUSIVE,
    MARCAS_MANUAIS,
    aplicar_flag_a_clientes,
    aplicar_flag_a_processos,
    cliente_e_sub35,
    condicao_de_filtro,
    condicao_sub35,
    data_iso,
    data_limite_de_nascimento,
    e_sub35,
    idade,
    intervalo_de_nascimento,
    processo_e_sub35,
)

HOJE = date(2026, 10, 2)


class TestARegra:
    def test_o_limite_e_menos_de_36_anos(self):
        # A regra do produto: até aos 35 INCLUSIVE. Foi aqui que o
        # `check_age_alert` (que usava `< 35`) deixava de fora um ano
        # inteiro de clientes elegíveis.
        assert IDADE_MAXIMA_INCLUSIVE == 35
        assert IDADE_EXCLUSIVA == 36

    @pytest.mark.parametrize(
        "nascimento,esperado",
        [
            ("2000-01-01", True),    # 26 anos
            ("1991-10-03", True),    # 34 anos
            ("1990-10-03", True),    # 35 anos — ELEGÍVEL (era o caso perdido)
            ("1990-10-02", False),   # faz 36 HOJE — já não
            ("1990-10-01", False),   # 36 anos
            ("1960-05-05", False),
        ],
    )
    def test_fronteiras_ao_dia(self, nascimento, esperado):
        assert e_sub35(nascimento, HOJE) is esperado

    def test_o_dia_do_36_aniversario_ja_nao_e_sub35(self):
        # `$gt` e não `$gte`: quem faz 36 hoje sai da lista hoje.
        assert idade("1990-10-02", HOJE) == 36
        assert e_sub35("1990-10-02", HOJE) is False

    def test_uma_data_no_futuro_nao_e_elegibilidade(self):
        # Gralha de introdução (ano 2206 em vez de 2006). Sem esta
        # guarda, uma idade negativa é "menos de 36".
        assert e_sub35("2206-01-01", HOJE) is False

    def test_sem_data_nao_ha_etiqueta(self):
        for valor in (None, "", "   ", {}, [], 0):
            assert e_sub35(valor, HOJE) is False


class TestOFormatoDaData:
    def test_aceita_iso_com_e_sem_hora(self):
        assert data_iso("1995-03-15") == "1995-03-15"
        assert data_iso("1995-03-15T00:00:00Z") == "1995-03-15"
        assert data_iso("1995-03-15 08:30:00") == "1995-03-15"

    def test_aceita_objectos_de_data(self):
        assert data_iso(date(1995, 3, 15)) == "1995-03-15"
        assert data_iso(datetime(1995, 3, 15, 8, 30)) == "1995-03-15"

    def test_RECUSA_o_formato_portugues(self):
        # `03/04/1990` é ambíguo (3 de Abril ou 4 de Março?) e adivinhar
        # põe o cliente na lista errada sem dar erro. Melhor sem
        # etiqueta do que com a etiqueta errada.
        assert data_iso("15/03/1995") is None
        assert data_iso("03/04/1990") is None
        assert e_sub35("15/03/2010", HOJE) is False

    def test_recusa_lixo(self):
        assert data_iso("ontem") is None
        assert data_iso("1995-13-45") is None


class TestOsDoisNomesDoCampo:
    def test_le_birth_date_e_data_nascimento(self):
        # O `client_crud` sincroniza AMBAS as entradas do formulário
        # para `personal_data.data_nascimento` — que é precisamente o
        # nome que o `check_age_alert` não lia.
        assert CAMPOS_DE_NASCIMENTO == ("birth_date", "data_nascimento")
        for campo in CAMPOS_DE_NASCIMENTO:
            processo = {"personal_data": {campo: "2000-01-01"}}
            assert processo_e_sub35(processo, HOJE) is True

    def test_le_a_raiz_quando_a_seccao_nao_tem(self):
        assert processo_e_sub35({"birth_date": "2000-01-01"}, HOJE) is True

    def test_a_seccao_vence_a_raiz(self):
        processo = {
            "personal_data": {"birth_date": "1960-01-01"},
            "birth_date": "2000-01-01",
        }
        assert processo_e_sub35(processo, HOJE) is False

    def test_o_cliente_da_pool_usa_dados_pessoais(self):
        assert cliente_e_sub35({"dados_pessoais": {"birth_date": "2000-01-01"}}, HOJE) is True
        # E não lê `personal_data`, que é o nome do PROCESSO: confundi-los
        # daria a Pool sempre sem etiqueta.
        assert cliente_e_sub35({"personal_data": {"birth_date": "2000-01-01"}}, HOJE) is False


class TestAsMarcasManuais:
    @pytest.mark.parametrize("campo", MARCAS_MANUAIS)
    def test_uma_marca_verdadeira_vence_a_falta_de_data(self, campo):
        # `idade_menos_35` e `under_35` são legado. O registo público
        # grava `idade_menos_35: False` à letra e ninguém o calcula —
        # mas se alguém o puser a True à mão, isso é informação.
        assert processo_e_sub35({campo: True}, HOJE) is True

    def test_uma_marca_FALSA_nao_nega_a_data(self):
        # É o caso REAL de produção: todo o registo público tem
        # `idade_menos_35: False`. Tratar isso como "não é Sub35"
        # desligava a funcionalidade para todos os clientes do portal.
        processo = {"idade_menos_35": False, "personal_data": {"birth_date": "2000-01-01"}}
        assert processo_e_sub35(processo, HOJE) is True


class TestAFlagNaSerializacao:
    def test_escreve_os_dois_nomes_que_a_ui_le(self):
        # `under_35` é o nome que `KanbanCard`, `SearchResultsList` e
        # `FilteredProcessList` já leem; `is_sub35` é o novo. Enviar os
        # dois é o que permite a transição sem um ecrã ficar sem etiqueta.
        processos = [{"personal_data": {"birth_date": "2000-01-01"}}, {"id": "x"}]
        aplicar_flag_a_processos(processos, HOJE)
        assert processos[0][CAMPO_DA_FLAG] is True
        assert processos[0]["under_35"] is True
        assert processos[1][CAMPO_DA_FLAG] is False
        assert processos[1]["under_35"] is False

    def test_a_flag_e_SEMPRE_escrita(self):
        # Ausente ≠ falso no frontend: `{process.is_sub35 && …}` trata
        # `undefined` como falso, mas um `||` numa cascata não. Escrever
        # sempre fecha a dúvida.
        processos = [{"id": "a"}]
        aplicar_flag_a_processos(processos, HOJE)
        assert CAMPO_DA_FLAG in processos[0]

    def test_aguenta_lixo_na_lista(self):
        lista = [None, "x", {"id": "a"}]
        aplicar_flag_a_processos(lista, HOJE)
        aplicar_flag_a_processos(None, HOJE)
        assert lista[2][CAMPO_DA_FLAG] is False

    def test_clientes_da_pool(self):
        clientes = [{"dados_pessoais": {"data_nascimento": "2005-06-01"}}, {"id": "b"}]
        aplicar_flag_a_clientes(clientes, HOJE)
        assert clientes[0][CAMPO_DA_FLAG] is True
        assert clientes[1][CAMPO_DA_FLAG] is False


class TestOLimiteNoCalendario:
    def test_o_limite_e_a_data_de_quem_faz_36_hoje(self):
        assert data_limite_de_nascimento(HOJE) == "1990-10-02"

    def test_29_de_fevereiro_nao_rebenta(self):
        # `replace(year=…)` levanta ValueError quando o ano destino não é
        # bissexto. Num endpoint de listagem isso seria um 500.
        assert data_limite_de_nascimento(date(2024, 2, 29)) == "1988-02-29"
        limite = data_limite_de_nascimento(date(2136, 2, 29))  # 2100 não é bissexto
        assert limite == "2100-03-01"

    def test_aceita_datetime_como_hoje(self):
        assert data_limite_de_nascimento(datetime(2026, 10, 2, 23, 59)) == "1990-10-02"


class TestOFiltro:
    def test_none_nao_filtra(self):
        assert condicao_de_filtro(None, HOJE) is None

    def test_false_tambem_nao_filtra_e_e_de_proposito(self):
        # "Não é Sub35" juntaria quem tem mais de 35 com quem não tem
        # data na ficha. O filtro não afirma o que não sabe.
        assert condicao_de_filtro(False, HOJE) is None

    def test_true_devolve_a_condicao(self):
        assert condicao_de_filtro(True, HOJE) == condicao_sub35(HOJE)

    def test_a_condicao_exige_data_ISO(self):
        # Sem a âncora, `"25/03/1988" >= "1990-10-03"` é VERDADEIRO em
        # comparação lexicográfica (`"2"` > `"1"`) e um registo com a
        # data em formato português entrava na lista.
        cond = condicao_sub35(HOJE)
        ramos_de_texto = [
            r for r in cond["$or"]
            for v in r.values()
            if isinstance(v, dict) and isinstance(v.get("$gte"), str)
        ]
        assert ramos_de_texto, cond
        for ramo in ramos_de_texto:
            (expressao,) = ramo.values()
            assert "$regex" in expressao, ramo

    def test_a_condicao_e_um_intervalo_FECHADO_dos_dois_lados(self):
        """Sem o limite de cima, uma data no futuro (a gralha `2206` por
        `2006`) entra na lista filtrada e não tem etiqueta no ecrã — foi
        o que o teste de concordância apanhou à primeira execução."""
        inicio, fim = intervalo_de_nascimento(HOJE)
        assert inicio == "1990-10-03"   # quem faz 36 amanhã
        assert fim == "2026-10-03"      # amanhã: o futuro fica fora
        for ramo in condicao_sub35(HOJE)["$or"]:
            (expressao,) = ramo.values()
            if isinstance(expressao, dict):
                assert "$gte" in expressao and "$lt" in expressao, ramo

    def test_a_condicao_inclui_as_marcas_manuais(self):
        cond = condicao_sub35(HOJE)
        for campo in MARCAS_MANUAIS:
            assert {campo: True} in cond["$or"], campo

    def test_a_condicao_cobre_os_dois_nomes_em_personal_data(self):
        chaves = {chave for ramo in condicao_sub35(HOJE)["$or"] for chave in ramo}
        assert "personal_data.birth_date" in chaves
        assert "personal_data.data_nascimento" in chaves

    def test_a_condicao_do_cliente_usa_dados_pessoais(self):
        from services.sub35 import SECCOES_DO_CLIENTE

        chaves = {
            chave
            for ramo in condicao_sub35(HOJE, seccoes=SECCOES_DO_CLIENTE)["$or"]
            for chave in ramo
        }
        assert "dados_pessoais.birth_date" in chaves
        assert "personal_data.birth_date" not in chaves


# ════════════════════════════════════════════════════════════════════
# A CONCORDÂNCIA — o teste que justifica o módulo
# ════════════════════════════════════════════════════════════════════

DOCUMENTOS = [
    ("jovem por birth_date", {"personal_data": {"birth_date": "2000-01-01"}}),
    ("jovem por data_nascimento", {"personal_data": {"data_nascimento": "2005-06-01"}}),
    ("35 anos (fronteira)", {"personal_data": {"birth_date": "1990-10-03"}}),
    ("36 anos hoje (fronteira)", {"personal_data": {"birth_date": "1990-10-02"}}),
    ("velho", {"personal_data": {"birth_date": "1960-05-05"}}),
    ("sem data", {"personal_data": {"nif": "123456789"}}),
    ("sem personal_data", {"id": "x"}),
    ("data na raiz", {"birth_date": "1999-02-02"}),
    ("formato PT", {"personal_data": {"birth_date": "15/03/2010"}}),
    ("data BSON jovem", {"personal_data": {"birth_date": datetime(2001, 4, 4)}}),
    ("data BSON velha", {"personal_data": {"birth_date": datetime(1950, 4, 4)}}),
    ("marca manual", {"under_35": True}),
    ("marca manual falsa + jovem", {"idade_menos_35": False, "personal_data": {"birth_date": "2002-02-02"}}),
    ("futuro", {"personal_data": {"birth_date": "2206-01-01"}}),
]


class TestOFiltroEAEtiquetaConcordam:
    @pytest.mark.parametrize("nome,doc", DOCUMENTOS, ids=[n for n, _ in DOCUMENTOS])
    @pytest.mark.asyncio
    async def test_a_lista_filtrada_e_exactamente_a_lista_etiquetada(
        self, nome, doc, fake_async_db
    ):
        from tests.unit.conftest import FakeAsyncCollection

        esperado = processo_e_sub35(doc, HOJE)
        cond = condicao_sub35(HOJE)
        obtido = FakeAsyncCollection._matches(doc, cond)
        assert obtido is esperado, (
            f"{nome}: a condição Mongo diz {obtido} e o predicado diz {esperado}"
        )

    def test_a_amostra_tem_casos_dos_DOIS_lados(self):
        """Contraprova: uma amostra só de jovens faria um filtro que
        aceita tudo passar o teste acima."""
        veredictos = {processo_e_sub35(doc, HOJE) for _, doc in DOCUMENTOS}
        assert veredictos == {True, False}



class TestOAlertaDeOIdadeDerivaDoPontoUnico:
    """`alerts.check_age_alert` era a TERCEIRA resposta à mesma pergunta."""

    def test_um_cliente_de_35_anos_passa_a_ser_elegivel(self):
        from services.alerts import check_age_alert
        from services.sub35 import data_limite_de_nascimento
        from datetime import datetime as _dt, timedelta as _td

        # Alguém que faz 36 daqui a um mês: tem 35 anos hoje.
        limite = _dt.strptime(data_limite_de_nascimento(), "%Y-%m-%d")
        nascimento = (limite + _td(days=30)).date().isoformat()

        alerta = check_age_alert({"personal_data": {"birth_date": nascimento}})
        assert alerta["active"] is True
        assert alerta["age"] == 35
        # A comparação antiga (`age < 35`) devolvia `active: False` aqui.

    def test_le_data_nascimento_e_nao_so_birth_date(self):
        # O `client_crud` grava as duas entradas do formulário em
        # `personal_data.data_nascimento`, que esta função NÃO lia.
        from services.alerts import check_age_alert

        alerta = check_age_alert({"personal_data": {"data_nascimento": "2000-01-01"}})
        assert alerta["active"] is True
        assert alerta["age"] is not None

    def test_um_cliente_com_mais_de_36_nao_tem_alerta(self):
        from services.alerts import check_age_alert

        assert check_age_alert({"personal_data": {"birth_date": "1960-01-01"}})["active"] is False

    def test_a_marca_manual_nao_inventa_uma_idade(self):
        # Sem data de nascimento não há idade: um "0 anos" na mensagem
        # era pior do que não a dizer.
        from services.alerts import check_age_alert

        alerta = check_age_alert({"idade_menos_35": True})
        assert alerta["active"] is True
        assert "age" not in alerta
        assert "0 anos" not in alerta["message"]

    def test_calculate_age_continua_a_funcionar_para_quem_a_importa(self):
        # Função pública do módulo; delegar não pode mudar o contrato.
        from services.alerts import calculate_age

        assert calculate_age("2000-01-01") == idade("2000-01-01")
        assert calculate_age(None) is None
        assert calculate_age("lixo") is None


# ════════════════════════════════════════════════════════════════════
# O INVENTÁRIO — "inventariar os sítios que LISTAM, não só a condição"
# ════════════════════════════════════════════════════════════════════
#
# O Kanban tem um construtor de query SEPARADO e foi assim que ficou
# fora do isolamento por Rede durante meses (Lote 4/5). A etiqueta e o
# filtro novos têm o mesmo risco, e um ponto único para a REGRA não
# chega: o que falha é a LIGAÇÃO. Estes testes enumeram por árvore de
# sintaxe e afirmam o NÚMERO, para um sítio novo não poder entrar em
# silêncio.

import ast  # noqa: E402

ROTAS_PROCESSOS = BACKEND / "routes" / "processes.py"
ENRIQUECIMENTO = BACKEND / "services" / "process_list_enrichment.py"
KANBAN = BACKEND / "services" / "process_kanban_enrichment.py"
FILTROS = BACKEND / "services" / "process_list_filters.py"
NAVEGACAO = BACKEND / "services" / "process_navigation.py"


def _arvore(caminho):
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _funcoes(arvore):
    return [
        no
        for no in ast.walk(arvore)
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _nomes_chamados(no) -> set[str]:
    nomes = set()
    for filho in ast.walk(no):
        if isinstance(filho, ast.Call):
            alvo = filho.func
            if isinstance(alvo, ast.Name):
                nomes.add(alvo.id)
            elif isinstance(alvo, ast.Attribute):
                nomes.add(alvo.attr)
    return nomes


def _kwargs_da_chamada(no, nome_da_funcao) -> list[set[str]]:
    """As palavras-chave de cada chamada a `nome_da_funcao` dentro de `no`."""
    resultado = []
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Call):
            continue
        alvo = filho.func
        chamado = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", "")
        if chamado == nome_da_funcao:
            resultado.append({kw.arg for kw in filho.keywords if kw.arg})
    return resultado


def _quem_chama(caminhos, nome_da_funcao):
    """(ficheiro, função, kwargs) para cada chamador de `nome_da_funcao`."""
    encontrados = []
    for caminho in caminhos:
        for funcao in _funcoes(_arvore(caminho)):
            for kwargs in _kwargs_da_chamada(funcao, nome_da_funcao):
                encontrados.append((caminho.name, funcao.name, kwargs))
    return encontrados


CONSTRUTORES_DE_QUERY = [ENRIQUECIMENTO, KANBAN, NAVEGACAO]


class TestTodosOsSitiosQueListamRecebemOFiltro:
    def test_ha_QUATRO_chamadores_dos_construtores_de_query(self):
        """Três listagens + os vizinhos. Se este número mudar, há um
        sítio novo a ligar — e é esse o momento em que o filtro costuma
        ficar de fora."""
        chamadores = _quem_chama(
            CONSTRUTORES_DE_QUERY, "build_process_list_query"
        ) + _quem_chama(CONSTRUTORES_DE_QUERY, "build_kanban_query")
        assert len(chamadores) == 4, chamadores

    @pytest.mark.parametrize(
        "ficheiro,funcao,kwargs",
        _quem_chama(CONSTRUTORES_DE_QUERY, "build_process_list_query")
        + _quem_chama(CONSTRUTORES_DE_QUERY, "build_kanban_query"),
        ids=lambda v: v if isinstance(v, str) else "",
    )
    def test_cada_chamador_passa_sub35(self, ficheiro, funcao, kwargs):
        assert "sub35" in kwargs, f"{ficheiro}:{funcao} monta a query sem sub35"

    def test_os_VIZINHOS_tambem_o_recebem(self):
        """O endpoint de vizinhança repete os filtros da listagem de
        origem. Sem o sub35, a seta da fronteira da página levava a um
        processo que a lista filtrada não contém — e um vizinho errado é
        pior do que não haver seta, porque ninguém desconfia."""
        chamadores = _quem_chama([NAVEGACAO], "build_process_list_query")
        assert len(chamadores) == 1, chamadores
        assert "sub35" in chamadores[0][2]


class TestTodosOsSitiosQueSerializamEscrevemAFlag:
    ORQUESTRADORES = {
        "run_get_processes": ENRIQUECIMENTO,
        "run_get_processes_paginated": ENRIQUECIMENTO,
        "run_get_kanban_board": KANBAN,
    }

    @pytest.mark.parametrize("nome", sorted(ORQUESTRADORES))
    def test_o_orquestrador_aplica_a_flag(self, nome):
        caminho = self.ORQUESTRADORES[nome]
        funcao = next(f for f in _funcoes(_arvore(caminho)) if f.name == nome)
        assert "aplicar_flag_sub35" in _nomes_chamados(funcao), (
            f"{nome} devolve processos à UI sem escrever a etiqueta — "
            f"o `is_sub35` ficaria ausente e um campo ausente lê-se como "
            f"«não é Sub35»."
        )

    def test_a_POOL_tambem_etiqueta(self):
        from services.client_registered import run_list_registered_clients  # noqa: F401

        fonte = (BACKEND / "services" / "client_registered.py").read_text(encoding="utf-8")
        assert "cliente_e_sub35(c)" in fonte

    def test_CONTRAPROVA_o_nome_importado_e_o_do_ponto_unico(self):
        """Sem isto, uma função local chamada `aplicar_flag_sub35` que
        não fizesse nada satisfazia os testes acima."""
        for caminho in (ENRIQUECIMENTO, KANBAN):
            fonte = caminho.read_text(encoding="utf-8")
            assert (
                "from services.sub35 import aplicar_flag_a_processos as aplicar_flag_sub35"
                in fonte
            ), caminho.name


class TestAsRotasDeclaramOParametro:
    @staticmethod
    def _handlers_de_listagem():
        """Handlers de rota que declaram os filtros da listagem.

        `labels_logic` é o marcador: é um parâmetro que só existe nos
        endpoints que listam processos com filtros (as três listagens, o
        quadro e os vizinhos).
        """
        return [
            f
            for f in _funcoes(_arvore(ROTAS_PROCESSOS))
            if any(a.arg == "labels_logic" for a in f.args.args + f.args.kwonlyargs)
        ]

    def test_ha_CINCO_handlers_com_filtros_de_listagem(self):
        nomes = sorted(f.name for f in self._handlers_de_listagem())
        assert len(nomes) == 5, nomes

    def test_cada_um_declara_e_passa_o_sub35(self):
        for funcao in self._handlers_de_listagem():
            argumentos = {a.arg for a in funcao.args.args + funcao.args.kwonlyargs}
            assert "sub35" in argumentos, f"{funcao.name} não declara sub35"
            # Declarar e não passar é o modo silencioso de falhar: o
            # endpoint aceita `?sub35=true`, responde 200 e ignora-o.
            passa = any(
                "sub35" in kwargs
                for nome in ("run_get_processes", "run_get_processes_paginated",
                             "run_get_kanban_board", "run_get_process_neighbours")
                for kwargs in _kwargs_da_chamada(funcao, nome)
            )
            assert passa, f"{funcao.name} declara sub35 e não o passa ao serviço"


class TestAsProjeccoesTrazemOsCampos:
    def test_a_listagem_e_o_quadro_projectam_o_mesmo_conjunto(self):
        from services.process_service import (
            PROCESS_KANBAN_PROJECTION,
            PROCESS_LIST_PROJECTION,
        )
        from services.sub35 import PROJECCAO

        for nome, projeccao in (
            ("lista", PROCESS_LIST_PROJECTION),
            ("kanban", PROCESS_KANBAN_PROJECTION),
        ):
            faltam = set(PROJECCAO) - set(projeccao)
            assert not faltam, f"projecção {nome} sem {faltam}"

    def test_a_projeccao_nao_traz_o_bloco_de_PII_inteiro(self):
        """Contraprova de âmbito: `personal_data: 1` resolveria a
        etiqueta e mandaria NIF, morada e documento para uma listagem
        que não precisa deles."""
        from services.process_service import (
            PROCESS_KANBAN_PROJECTION,
            PROCESS_LIST_PROJECTION,
        )

        for projeccao in (PROCESS_LIST_PROJECTION, PROCESS_KANBAN_PROJECTION):
            assert "personal_data" not in projeccao
