"""`s3_folder` gravado com o tipo errado (Lote 8 — hotfix).

O QUE ACONTECEU
===============
A medição da D-19 correu contra produção e morreu na primeira ficha:

    gravado = (ficha.s3_folder or "").strip().rstrip("/")
    AttributeError: 'list' object has no attribute 'strip'

Há pelo menos uma ficha com `s3_folder` gravado como LISTA. O script foi
só o mensageiro: **a aplicação que corre todos os dias lê esse campo
exactamente da mesma maneira**, e o `list_files` tem a mesma linha. Para
essa ficha, a aba Documentos responde 500 — hoje, sem ninguém cortar
nada.

A FORMA DO DEFEITO
==================
Todos estes sítios têm a mesma guarda:

    if s3_folder:
        base_path = s3_folder.rstrip("/")

**Uma lista é truthy.** A guarda passa e o erro acontece na linha
seguinte. É a regra do `Array.isArray` do frontend escrita em Python: um
`or ""` (ou um `if x:`) não protege de um valor do TIPO errado — só muda
o sítio onde rebenta. E `(x or "")` é literalmente o `|| []` que o
`FRONTEND_GUIDELINES.md` § 27.38 proíbe.

A DECISÃO
=========
`s3_document_root.pasta_gravada` é o ponto único: devolve texto
utilizável ou `None`, **com `warning`**. `None` faz o chamador cair no
caminho de «sem mapeamento», que é o degradado certo — numa leitura
procura-se pelo nome, numa escrita deriva-se do ID. Nenhum dos dois
inventa uma pasta a partir de um valor que não se entende, e nenhum dos
dois é silencioso: um degradado calado era a ficha a perder documentos
sem ninguém saber porquê.

E A TORNEIRA
============
Corrigir os leitores e deixar o escritor a aceitar listas é esfregar o
chão com a torneira aberta (regra do `assignment_drift`). O escritor é o
`_clean_s3_folder`: `["a"] in [None, "", "undefined", ...]` é `False`,
logo a lista era devolvida tal e qual e gravada no Mongo.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services.s3_document_root import (
    e_pasta_gravada_corrompida,
    leituras_do_mapeamento,
    pasta_gravada,
)
from tests.unit.helpers_fonte import codigo_sem_comentarios


def _fonte(caminho: str) -> str:
    """O código do módulo, sem comentários.

    `codigo_sem_comentarios` recebe TEXTO, não um caminho — passar-lhe o
    caminho analisa a própria string como Python, não encontra nada e a
    guarda fica verde a provar zero. Foi o que aconteceu ao escrever
    este ficheiro, e foi a contraprova que o denunciou.
    """
    with open(Path(__file__).resolve().parents[3] / caminho, encoding="utf-8") as fh:
        return codigo_sem_comentarios(fh.read())

#: Os valores do tipo errado que se podem encontrar num campo de texto.
VALORES_CORROMPIDOS = [
    ["Documentação Clientes/Ana"],
    ["a", "b"],
    [],
    {"path": "Documentação Clientes/Ana"},
    {},
    123,
    12.5,
    True,
    ("a",),
]


def _especime_do_defeito(processo: dict) -> str:
    """O defeito, escrito em CÓDIGO, para a contraprova do leitor morder.

    Tem de ser código e não um exemplo numa docstring: o
    `codigo_sem_comentarios` remove docstrings, logo um espécime lá
    dentro deixava a contraprova a provar zero — foi o que aconteceu na
    primeira versão deste ficheiro.
    """
    s3_folder = processo.get("s3_folder")
    if s3_folder:
        return s3_folder.rstrip("/")
    return ""


class TestOPrimitivo:
    @pytest.mark.parametrize("valor", VALORES_CORROMPIDOS)
    def test_qualquer_valor_que_nao_seja_texto_e_corrompido(self, valor):
        assert e_pasta_gravada_corrompida(valor) is True

    @pytest.mark.parametrize("valor", [None, "", "  ", "Documentação Clientes/Ana"])
    def test_texto_e_ausencia_NAO_sao_corrupcao(self, valor):
        # Contraprova que importa: `None` e `""` são a ausência NORMAL de
        # mapeamento, com caminho próprio (o recurso por nome). Tratá-las
        # como corrupção enchia os logs e escondia o caso real.
        assert e_pasta_gravada_corrompida(valor) is False

    @pytest.mark.parametrize("valor", VALORES_CORROMPIDOS)
    def test_a_pasta_de_um_valor_corrompido_e_None(self, valor):
        assert pasta_gravada(valor) is None

    def test_uma_pasta_valida_passa_aparada(self):
        assert pasta_gravada("  Documentação Clientes/Ana  ") == (
            "Documentação Clientes/Ana"
        )

    @pytest.mark.parametrize("valor", [None, "", "   "])
    def test_ausencia_e_None_para_o_chamador_cair_no_recurso_por_nome(self, valor):
        assert pasta_gravada(valor) is None

    def test_a_corrupcao_fica_REGISTADA_e_nunca_em_silencio(self, caplog):
        with caplog.at_level("WARNING"):
            pasta_gravada(["x"], contexto="processo p1")
        registo = "\n".join(r.getMessage() for r in caplog.records)
        assert "s3_folder" in registo
        assert "list" in registo, "o tipo real tem de aparecer no log"
        assert "p1" in registo, "sem contexto ninguém sabe que ficha corrigir"

    def test_uma_pasta_valida_NAO_produz_aviso(self, caplog):
        # Senão o log do dia-a-dia enche-se e o aviso deixa de se ver.
        with caplog.at_level("WARNING"):
            pasta_gravada("Documentação Clientes/Ana")
        assert caplog.records == []


class TestALeituraDoMapeamento:
    @pytest.mark.parametrize("valor", VALORES_CORROMPIDOS)
    def test_um_valor_corrompido_nao_produz_leitura_nenhuma(self, valor):
        # Já era o comportamento (o `normalizar` recusa não-strings), e
        # fixa-se aqui: nunca se deriva um prefixo de um valor ilegível,
        # porque um prefixo inventado lê a pasta de outra pessoa.
        assert leituras_do_mapeamento(valor) == []


class TestOsLeitoresDeProducao:
    """O inventário dos sítios que leem `s3_folder` e lhe aplicam string.

    Guarda por FONTE porque o defeito é uma linha, não um comportamento
    observável sem S3 vivo — e porque o que falha aqui é a repetição:
    são onze sítios, e foi assim que quatro cópias da mesma guarda do
    Kanban perderam o `Array.isArray`. Falha por OMISSÃO para qualquer
    leitor novo.
    """

    #: Módulos que leem `s3_folder` da base de dados e constroem caminhos.
    MODULOS = [
        "backend/services/s3_storage.py",
        "backend/services/s3_mapping_on_create.py",
        "backend/services/document_upload_conflict.py",
        "backend/services/document_delete.py",
        "backend/services/s3_folder_coverage.py",
        "backend/services/admin_s3_process_mappings.py",
        "backend/services/storage_service.py",
    ]

    #: Os métodos de string que rebentam num valor do tipo errado.
    METODOS = ("strip", "rstrip", "lstrip", "replace", "split",
               "startswith", "endswith", "lower", "upper")

    #: Os pontos únicos por onde um `s3_folder` tem de passar antes de
    #: levar um método de string. São DOIS desde o Lote 9, e são
    #: equivalentes para esta guarda: ambos devolvem `Optional[str]`. O
    #: que os distingue é o veredicto para um valor do tipo errado —
    #: `pasta_gravada` degrada (LEITURA), `pasta_para_gravar` recusa
    #: (ESCRITA) — e isso é a pergunta do
    #: `test_guarda_de_escrita_do_s3_folder.py`, não desta.
    PONTOS_UNICOS = ("pasta_gravada", "pasta_para_gravar")

    def _chamadas_cruas(self, caminho):
        """Sítios que aplicam um método de string a um `s3_folder` NÃO saneado.

        Olhar só para o NOME não serve: depois da correcção o código é

            s3_folder = pasta_gravada(doc.get("s3_folder"), ...)
            if s3_folder:
                return s3_folder.rstrip("/")

        e o nome continua a ser `s3_folder`. Logo a pergunta é sobre a
        ATRIBUIÇÃO: dentro de cada função, um nome é seguro se vier de
        `pasta_gravada(...)` (também através de `... or ""`), e uma
        expressão `get("s3_folder")` é segura se tiver o ponto único
        dentro dela.

        É uma análise por função, não global: um módulo que chame o ponto
        único NUMA função e não noutra é exactamente o defeito das quatro
        cópias do Kanban que perderam o `Array.isArray`.
        """
        codigo = _fonte(caminho)
        arvore = ast.parse(codigo)
        encontrados = []

        def ha_ponto_unico(no):
            despejo = ast.dump(no)
            return any(p in despejo for p in self.PONTOS_UNICOS)

        def nomes_saneados(corpo):
            seguros = set()
            for no in corpo:
                for sub in ast.walk(no):
                    if isinstance(sub, ast.Assign) and ha_ponto_unico(sub.value):
                        for alvo in sub.targets:
                            if isinstance(alvo, ast.Name):
                                seguros.add(alvo.id)
            return seguros

        def nomes_contaminados(corpo, seguros):
            """Nomes que recebem o `s3_folder` CRU, com outro nome.

            A mutação N11 mostrou que seguir só identificadores com
            «s3_folder» não chega: o `move_file` fazia
            `client_folder = s3_folder` e depois `.rstrip()` — um nome
            intermédio basta para escapar. Segue-se um salto de
            atribuição, que é o que o defeito real usava.

            Uma origem JÁ SANEADA não contamina: `folder_name =
            s3_folder.replace(...)` onde o `s3_folder` veio do
            `pasta_gravada` é seguro, e tratá-lo como cru era um falso
            positivo desta guarda (apanhado a medir a N11).
            """
            contaminados = set()
            for no in corpo:
                for sub in ast.walk(no):
                    if not isinstance(sub, ast.Assign):
                        continue
                    if ha_ponto_unico(sub.value):
                        continue
                    origens = {
                        n.id for n in ast.walk(sub.value)
                        if isinstance(n, ast.Name) and "s3_folder" in n.id
                    } | {
                        "s3_folder" for c in ast.walk(sub.value)
                        if isinstance(c, ast.Constant) and c.value == "s3_folder"
                    }
                    if not origens or origens <= seguros:
                        continue
                    for alvo in sub.targets:
                        if isinstance(alvo, ast.Name):
                            contaminados.add(alvo.id)
            return contaminados

        def analisar(corpo, onde):
            seguros = nomes_saneados(corpo)
            contaminados = nomes_contaminados(corpo, seguros) - seguros
            for no in corpo:
                for sub in ast.walk(no):
                    if not isinstance(sub, ast.Call):
                        continue
                    func = sub.func
                    if not isinstance(func, ast.Attribute):
                        continue
                    if func.attr not in self.METODOS:
                        continue
                    alvo = func.value
                    if ha_ponto_unico(alvo):
                        continue  # saneado na própria expressão
                    # Um NOME e um acesso ao CAMPO são perguntas
                    # diferentes, e `ast.dump` escreve as duas com aspas
                    # (`Name(id='s3_folder')`): procurar texto no dump
                    # confundia-as e dava falsos positivos nas cadeias
                    # `x.replace(...).rstrip(...)`.
                    nomes = {
                        n.id for n in ast.walk(alvo)
                        if isinstance(n, ast.Name)
                        and ("s3_folder" in n.id or n.id in contaminados)
                    }
                    campo_cru = any(
                        isinstance(c, ast.Constant) and c.value == "s3_folder"
                        for c in ast.walk(alvo)
                    )
                    if campo_cru:
                        encontrados.append(
                            f"{onde}: get(s3_folder).{func.attr}"
                        )
                    elif nomes and not (nomes & seguros):
                        encontrados.append(
                            f"{onde}: {sorted(nomes)[0]}.{func.attr}"
                        )

        funcoes = [
            no for no in ast.walk(arvore)
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for fn in funcoes:
            analisar(fn.body, fn.name)
        # Nível de módulo (fora de qualquer função).
        analisar(
            [no for no in arvore.body
             if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef))],
            "<módulo>",
        )
        return encontrados

    @pytest.mark.parametrize("modulo", MODULOS)
    def test_nenhum_leitor_aplica_string_ao_valor_cru(self, modulo):
        cruas = self._chamadas_cruas(modulo)
        assert cruas == [], (
            f"{modulo} aplica {cruas} ao `s3_folder` cru. Uma lista é "
            "truthy: passa o `if` e rebenta aqui. Passar por "
            "`s3_document_root.pasta_gravada` primeiro."
        )

    def test_o_leitor_desta_guarda_le_MESMO_o_codigo(self):
        # Contraprova obrigatória: uma asserção da forma `== []` passa com
        # um leitor que não leia nada. Este ficheiro de teste tem, ele
        # próprio, `s3_folder.rstrip` escrito num exemplo, e o leitor
        # tem de o encontrar.
        cruas = self._chamadas_cruas("backend/tests/unit/test_s3_folder_corrompido.py")
        assert cruas, "o leitor não encontrou nada nem no próprio ficheiro"

    @pytest.mark.parametrize("modulo", MODULOS)
    def test_cada_leitor_usa_MESMO_o_ponto_unico(self, modulo):
        # Segunda contraprova: apagar a chamada satisfazia o teste de
        # cima. O sítio certo tem de chamar o primitivo.
        codigo = _fonte(modulo)
        assert "pasta_gravada" in codigo, (
            f"{modulo} não passa pelo ponto único `pasta_gravada`"
        )


class TestOMoveFile:
    """A mutação N11 sobreviveu — e isso era um teste fraco, não uma
    mutação perdida (terceira variante da lição já registada).

    A guarda por AST segue nomes que CONTÊM `s3_folder`. No `move_file` o
    valor cru era atribuído a `client_folder` e aí a guarda não o via:
    um nome intermédio é suficiente para escapar a uma guarda que olha
    só para o identificador. Daí um teste de COMPORTAMENTO ao lado dela
    — o que a guarda não consegue afirmar, afirma-se a correr o código.
    """

    @pytest.mark.parametrize("valor", VALORES_CORROMPIDOS)
    def test_mover_com_mapeamento_corrompido_recusa_sem_rebentar(self, valor):
        from services.s3_storage import S3Service

        servico = S3Service.__new__(S3Service)
        servico.s3_client = object()  # basta não ser None
        assert servico.move_file(
            "Documentação Clientes/x/Outros/a.pdf", valor, "Pessoais", "a.pdf"
        ) is False

    def test_mover_sem_mapeamento_e_REGISTADO(self, caplog):
        from services.s3_storage import S3Service

        servico = S3Service.__new__(S3Service)
        servico.s3_client = object()
        with caplog.at_level("WARNING"):
            servico.move_file(
                "Documentação Clientes/x/Outros/a.pdf", ["x"], "Pessoais",
                "a.pdf",
            )
        assert caplog.records, "recusar em silêncio esconde a causa"


class TestOEscritorQueDeixouEntrar:
    """A torneira: `_clean_s3_folder` aceitava qualquer tipo.

    LOTE 9 — ESTE TESTE FOI INVERTIDO, NÃO APAGADO
    A versão de cima afirmava que um valor do tipo errado virava `None`.
    Estava certa sobre «não grava lixo» e errada sobre o resto: o `$set`
    corre à mesma e escreve `None` POR CIMA de um mapeamento válido, pelo
    que a correcção do Lote 8 fechou a torneira a APAGAR. O veredicto de
    hoje é uma recusa, e é aqui que isso fica dito — um teste legado
    inverte-se, porque um teste apagado não impede o regresso do defeito
    que descrevia.
    """

    @pytest.mark.parametrize("valor", VALORES_CORROMPIDOS)
    def test_o_escritor_RECUSA_em_vez_de_apagar(self, valor):
        from services.s3_document_root import PastaGravadaInvalida
        from services.admin_s3_process_mappings import _clean_s3_folder

        # `["a"] in [None, "", "undefined", ...]` é False, logo a lista
        # era devolvida tal e qual e gravada. Devolver `None` deixou de
        # gravar lixo e passou a apagar a pasta da ficha; hoje recusa.
        with pytest.raises(PastaGravadaInvalida):
            _clean_s3_folder(valor)

    @pytest.mark.parametrize("valor", ["undefined", "null", "None", "", None])
    def test_os_sentinelas_continuam_a_virar_None(self, valor):
        from services.admin_s3_process_mappings import _clean_s3_folder

        assert _clean_s3_folder(valor) is None

    def test_uma_pasta_real_continua_a_ser_gravada(self):
        from services.admin_s3_process_mappings import _clean_s3_folder

        # Contraprova: a guarda nova não pode recusar o caso normal.
        assert _clean_s3_folder("Documentação Clientes/Ana") == (
            "Documentação Clientes/Ana"
        )
