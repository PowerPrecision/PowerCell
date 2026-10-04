"""A guarda de retorno do `s3_folder`: nenhum escritor grava o que não é texto.

O QUE FICOU EM ABERTO NO LOTE 8
===============================
O Lote 8 corrigiu os ONZE leitores (`pasta_gravada`) e sanou as 10 fichas
que produção tinha com o par `(sucesso, caminho)` gravado inteiro. O que
NÃO existia era rede do lado da escrita: os cinco chamadores de
`initialize_client_folders` / `ensure_client_folder_mapping`
desempacotavam o par corretamente **hoje**, e nada mantinha isso assim.
Um chamador novo que gravasse o valor de retorno cru reintroduzia o
defeito em silêncio — e só se saberia quando a aba Documentos de alguém
respondesse 500.

DUAS COISAS QUE ESTA GUARDA ENCONTROU AO SER ESCRITA
====================================================
1. **O `_clean_s3_folder` fechou a torneira a APAGAR.** A correcção do
   Lote 8 usou o primitivo da LEITURA (`pasta_gravada`), que devolve
   `None` — e o `$set` corre à mesma, escrevendo `None` por cima de um
   mapeamento válido. Deixou de gravar lixo e passou a apagar a pasta da
   ficha por causa de um erro de tipo do chamador. Recusar é o único
   veredicto que não perde informação.

2. **O escritor dos mapeamentos de UTILIZADOR não tinha validação
   nenhuma.** `run_update_user_s3_mapping` grava `s3_folder` em
   `db.users` e a anotação `str | None` é documentação, não uma parede.
   O irmão do lado ganhou o `_clean_s3_folder` no Lote 8 e este ficou de
   fora: é a forma do defeito do Lote 5 (o `set` e o `clear` a
   divergirem) aplicada a dois endpoints que gravam o MESMO campo.

PORQUE É QUE A GUARDA É UM INVENTÁRIO
=====================================
Um ponto único não se prova com um teste ao ponto único — prova-se
enumerando QUEM o devia usar. O inventário percorre `services/`,
`routes/` e `scripts/`, resolve o payload de cada `update_one`/
`insert_one`/… e falha por OMISSÃO: um escritor novo que não passe pelo
primitivo fica vermelho sem ninguém se lembrar de acrescentar um teste.
É o mesmo desenho do inventário dos chamadores de `list_files`.

E como toda a leitura por AST, tem **contraprova** ao lado: sem ela, um
leitor que devolva pouco deixa a guarda verde a provar zero.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services.s3_document_root import (
    PastaGravadaInvalida,
    pasta_para_gravar,
)

RAIZ_DO_REPO = Path(__file__).resolve().parents[3]
BACKEND = RAIZ_DO_REPO / "backend"

#: Os valores do tipo errado que se podem encontrar num campo de texto.
#: O primeiro é o que produção tinha: `(sucesso, caminho)` gravado inteiro.
VALORES_DO_TIPO_ERRADO = [
    [True, "Documentação Clientes/Ana"],
    (True, "Documentação Clientes/Ana"),
    ["Documentação Clientes/Ana"],
    [],
    {"path": "Documentação Clientes/Ana"},
    {},
    123,
    12.5,
    True,
    False,
]

#: Os métodos do Motor que GRAVAM. `$unset` não leva valor, logo não entra.
METODOS_DE_ESCRITA = {
    "update_one",
    "update_many",
    "insert_one",
    "insert_many",
    "replace_one",
    "find_one_and_update",
    "find_one_and_replace",
    "bulk_write",
}

#: O ponto único, e os dois envolucros que o chamam. Cada envolucro tem
#: contraprova em `TestOsEnvolucros`: sem ela, bastava acrescentar um nome
#: a esta lista para a guarda deixar de morder.
SANEADORES = {"pasta_para_gravar", "_clean_s3_folder", "validar_pasta"}

#: As pastas varridas. `tests/` fica fora de propósito: um teste grava
#: valores inválidos a sério, e é isso que o torna um teste.
PASTAS = ("services", "routes", "scripts")


def _modulos() -> list[Path]:
    ficheiros: list[Path] = []
    for pasta in PASTAS:
        ficheiros.extend(sorted((BACKEND / pasta).rglob("*.py")))
    return ficheiros


def _fonte(caminho: Path) -> str:
    """O código tal e qual — e aqui isso é a opção CERTA.

    As guardas de fonte deste projecto passam pelo
    `codigo_sem_comentarios` para que a explicação do defeito que
    previnem não as faça morder. Esta não precisa: a análise é por AST, e
    um comentário não produz nós. Uma docstring produz um `Constant`, que
    nunca é uma chamada a `update_one` nem um dicionário com a chave — o
    exemplo do defeito escrito numa docstring é invisível a este leitor.

    E insistir no filtro era pior: ao remover docstrings, uma função cujo
    corpo é só a docstring fica sem corpo e o `ast.parse` levanta
    `IndentationError` — foi o que aconteceu em seis módulos e deixou a
    guarda a falhar por um motivo que nada tem a ver com o que mede.
    """
    return caminho.read_text(encoding="utf-8")


def _contem_saneador(no: ast.AST) -> bool:
    for sub in ast.walk(no):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        nome = getattr(func, "id", None) or getattr(func, "attr", None)
        if nome in SANEADORES:
            return True
    return False


def _atribuicoes(corpo: list[ast.AST]) -> dict[str, list[ast.AST]]:
    """Nome → todos os valores que lhe são atribuídos neste âmbito.

    Inclui o `AnnAssign` (`process_doc: dict[str, Any] = {...}`), que é
    como um dos dois inserts do sistema declara o documento — ignorá-lo
    deixava esse escritor invisível à guarda.
    """
    mapa: dict[str, list[ast.AST]] = {}
    for no in corpo:
        for sub in ast.walk(no):
            if isinstance(sub, ast.Assign) and sub.value is not None:
                alvos = sub.targets
            elif isinstance(sub, ast.AnnAssign) and sub.value is not None:
                alvos = [sub.target]
            else:
                continue
            for alvo in alvos:
                if isinstance(alvo, ast.Name):
                    mapa.setdefault(alvo.id, []).append(sub.value)
    return mapa


def _nomes_seguros(atribuicoes: dict[str, list[ast.AST]]) -> set[str]:
    """Os nomes cujas atribuições passam TODAS pelo primitivo.

    «Todas» e não «alguma»: no `portal_upload_ops` o mesmo nome
    `s3_folder` recebia primeiro `process.get("s3_folder")` (uma LEITURA)
    e só depois o valor saneado. Com a regra «alguma», a guarda ficava
    verde sobre um nome que podia chegar ao `$set` pelo ramo cru — a
    forma exacta da mutação N11 do Lote 8 («não é uma mutação perdida, é
    um teste fraco»). Com esta regra, o escritor é obrigado a usar um
    nome com uma origem só.

    Um nome copiado de um nome já seguro continua seguro — daí o ponto
    fixo; sem ele, `s3_folder = pasta_criada` dava falso positivo.
    """
    seguros: set[str] = set()
    while True:
        novos = set()
        for nome, valores in atribuicoes.items():
            if nome in seguros:
                continue
            if all(
                _contem_saneador(v)
                or isinstance(v, ast.Constant)
                or (isinstance(v, ast.Name) and v.id in seguros)
                for v in valores
            ):
                novos.add(nome)
        if not novos:
            return seguros
        seguros |= novos


def _resolver(no: ast.AST, atribuicoes: dict[str, list[ast.AST]]) -> list[ast.AST]:
    """O payload, seguindo um salto de atribuição quando é um nome."""
    if isinstance(no, ast.Name):
        return atribuicoes.get(no.id, [])
    return [no]


def _valores_de_s3_folder(
    no: ast.AST,
    atribuicoes: dict[str, list[ast.AST]],
    _vistos: set[str] | None = None,
) -> list[ast.AST]:
    """Os valores associados à chave `"s3_folder"` dentro do payload.

    Resolve um nome que apareça como VALOR de um dicionário:
    `{"$set": update_fields}` é a forma que metade dos escritores usa, e
    sem este salto o leitor não via lá dentro. Foi a contraprova
    (`test_o_inventario_cobre_os_escritores_conhecidos`) a denunciá-lo: o
    `admin_s3_client_mappings` dava verde no teste do veredicto por o
    leitor ser CEGO àquele sítio, e um verde desses é pior do que um
    vermelho — é a terceira vez neste projecto que um leitor por AST
    prova menos do que parece.
    """
    vistos = set() if _vistos is None else _vistos
    encontrados: list[ast.AST] = []
    for sub in ast.walk(no):
        if not isinstance(sub, ast.Dict):
            continue
        for chave, valor in zip(sub.keys, sub.values):
            if isinstance(chave, ast.Constant) and chave.value == "s3_folder":
                encontrados.append(valor)
            elif isinstance(valor, ast.Name) and valor.id not in vistos:
                vistos.add(valor.id)
                for origem in atribuicoes.get(valor.id, []):
                    encontrados.extend(
                        _valores_de_s3_folder(origem, atribuicoes, vistos)
                    )
    return encontrados


def _payloads(chamada: ast.Call) -> list[ast.AST]:
    """Os argumentos de uma chamada de escrita que transportam valores.

    Nos `update_*` o filtro é o 1.º argumento e o documento o 2.º; nos
    `insert_*` o documento é o 1.º. Varrer os dois nos updates faria a
    guarda morder consultas (`{"s3_folder": antigo}`), que não gravam
    nada — e uma guarda que morde o sítio errado é apagada por quem a
    encontra vermelha.
    """
    nome = getattr(chamada.func, "attr", "")
    if nome in {"insert_one", "insert_many", "bulk_write"}:
        posicionais = chamada.args[:1]
    else:
        posicionais = chamada.args[1:2]
    nomeados = [
        kw.value for kw in chamada.keywords
        if kw.arg in {"update", "document", "documents", "replacement"}
    ]
    return list(posicionais) + nomeados


def escritores_crus(codigo: str, ficheiro: str) -> list[str]:
    """Os sítios que gravam `s3_folder` sem passar pelo primitivo."""
    arvore = ast.parse(codigo)
    achados: list[str] = []

    def analisar(corpo: list[ast.AST], onde: str) -> None:
        atribuicoes = _atribuicoes(corpo)
        seguros = _nomes_seguros(atribuicoes)
        for no in corpo:
            for sub in ast.walk(no):
                if not isinstance(sub, ast.Call):
                    continue
                if getattr(sub.func, "attr", None) not in METODOS_DE_ESCRITA:
                    continue
                for payload in _payloads(sub):
                    for candidato in _resolver(payload, atribuicoes):
                        for valor in _valores_de_s3_folder(candidato, atribuicoes):
                            if _contem_saneador(valor):
                                continue
                            if isinstance(valor, ast.Constant):
                                continue
                            if isinstance(valor, ast.Name) and valor.id in seguros:
                                continue
                            achados.append(
                                f"{ficheiro}:{sub.lineno} em {onde} "
                                f"({ast.unparse(valor)})"
                            )

    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            analisar(no.body, no.name)
    analisar(
        [n for n in arvore.body
         if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))],
        "<módulo>",
    )
    return achados


def escritores_de_s3_folder(codigo: str) -> int:
    """Quantos sítios deste código gravam `s3_folder` (crus ou saneados)."""
    arvore = ast.parse(codigo)
    total = 0
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            atribuicoes = _atribuicoes(no.body)
            for sub in ast.walk(no):
                if not isinstance(sub, ast.Call):
                    continue
                if getattr(sub.func, "attr", None) not in METODOS_DE_ESCRITA:
                    continue
                for payload in _payloads(sub):
                    for candidato in _resolver(payload, atribuicoes):
                        total += len(_valores_de_s3_folder(candidato, atribuicoes))
    return total


# ───────────────────────── o primitivo ─────────────────────────


class TestOPrimitivo:
    """`pasta_para_gravar` recusa; não degrada."""

    @pytest.mark.parametrize("valor", VALORES_DO_TIPO_ERRADO)
    def test_um_valor_que_nao_e_texto_e_RECUSADO(self, valor):
        with pytest.raises(PastaGravadaInvalida):
            pasta_para_gravar(valor)

    @pytest.mark.parametrize("valor", VALORES_DO_TIPO_ERRADO)
    def test_a_recusa_nomeia_o_TIPO_e_o_valor_cru(self, valor):
        """Sem o tipo e o valor na mensagem, encontrar o chamador obriga a
        ir aos logs do servidor — e o 400 que o admin recebe não diz nada."""
        with pytest.raises(PastaGravadaInvalida) as erro:
            pasta_para_gravar(valor, contexto="processo 42")
        mensagem = str(erro.value)
        assert type(valor).__name__ in mensagem
        assert repr(valor) in mensagem
        assert "processo 42" in mensagem

    def test_a_excepcao_transporta_o_valor_para_quem_a_apanha(self):
        with pytest.raises(PastaGravadaInvalida) as erro:
            pasta_para_gravar([True, "x"], contexto="aqui")
        assert erro.value.valor == [True, "x"]
        assert erro.value.contexto == "aqui"

    def test_uma_excepcao_de_tipo_e_um_ValueError(self):
        """Quem já apanha `ValueError` não deixa de apanhar isto."""
        assert issubclass(PastaGravadaInvalida, ValueError)

    def test_None_continua_a_ser_a_remocao_EXPLICITA_do_mapeamento(self):
        """O `s3_relink` remove um mapeamento de propósito (regra 5).
        Recusar `None` fechava uma operação legítima."""
        assert pasta_para_gravar(None) is None

    @pytest.mark.parametrize("valor", ["", "   ", "\t\n"])
    def test_texto_vazio_vale_como_ausencia(self, valor):
        assert pasta_para_gravar(valor) is None

    def test_uma_pasta_real_passa_aparada(self):
        assert pasta_para_gravar("  Documentação Clientes/abc  ") == (
            "Documentação Clientes/abc"
        )

    def test_o_veredicto_e_o_INVERSO_do_primitivo_da_leitura(self):
        """A LEITURA degrada para «sem mapeamento» — o ecrã serve o que
        consegue. A ESCRITA recusa — gravar `None` apagaria a pasta.

        É esta assimetria que o módulo existe para afirmar; se os dois
        primitivos passarem a responder o mesmo, um deles está errado.
        """
        from services.s3_document_root import pasta_gravada

        assert pasta_gravada([True, "x"]) is None
        with pytest.raises(PastaGravadaInvalida):
            pasta_para_gravar([True, "x"])


# ──────────────────── o inventário dos escritores ────────────────────


class TestOInventarioDosEscritores:
    """Nenhum `$set`/`insert` de `s3_folder` escapa ao primitivo."""

    @pytest.mark.parametrize(
        "modulo", [str(m.relative_to(BACKEND)) for m in _modulos()]
    )
    def test_nenhum_escritor_grava_o_valor_cru(self, modulo):
        caminho = BACKEND / modulo
        achados = escritores_crus(_fonte(caminho), modulo)
        assert not achados, (
            "Gravam `s3_folder` sem passar por `pasta_para_gravar`:\n  "
            + "\n  ".join(achados)
        )

    def test_o_inventario_encontra_MESMO_os_escritores_que_existem(self):
        """Contraprova: um leitor partido devolve zero e fica verde.

        O número é afirmado como um MÍNIMO — um escritor novo não parte
        este teste (parte o de cima, que é o que deve morder) — mas um
        leitor que deixe de ver os escritores de hoje parte este.
        """
        total = sum(escritores_de_s3_folder(_fonte(m)) for m in _modulos())
        assert total >= 17, total

    def test_o_inventario_cobre_os_escritores_conhecidos(self):
        """Os sítios que gravam o campo, por módulo.

        Escritos à mão de propósito: é a lista que alguém tem de olhar
        quando este ficheiro ficar vermelho, e é o que distingue «o
        leitor vê 12 sítios» de «o leitor vê os 12 sítios CERTOS».
        """
        esperados = {
            "services/admin_s3_process_mappings.py",
            "services/admin_s3_user_mappings.py",
            "services/admin_s3_client_mappings.py",
            "services/client_assign.py",
            "services/document_misc.py",
            "services/onboarding_mandatory_config.py",
            "services/portal_upload_ops.py",
            "services/public_registration.py",
            "services/s3_folder_relink.py",
            "services/s3_mapping_on_create.py",
            "services/s3_relink.py",
            # Este foi o inventário a corrigir o meu: `run_create_client`
            # grava o mapeamento logo após inserir o cliente, e não estava
            # na lista que escrevi à mão.
            "services/client_crud.py",
            # E estes quatro: as ferramentas de operações escrevem o MESMO
            # campo e nenhuma delas aparecia em nota nenhuma do projecto.
            # Correm contra produção com o `$set` na mão — é onde um valor
            # do tipo errado tem mais alcance, não menos.
            "scripts/backfill_s3_mappings.py",
            "scripts/hotfix_restore_s3_mappings.py",
            "scripts/medir_cobertura_s3.py",
            "scripts/fix_s3_folder_anomalies.py",
        }
        encontrados = {
            str(m.relative_to(BACKEND))
            for m in _modulos()
            if escritores_de_s3_folder(_fonte(m))
        }
        assert esperados <= encontrados, esperados - encontrados

    def test_a_guarda_morde_um_escritor_cru(self):
        """Contraprova do veredicto: o defeito real, em código."""
        achados = escritores_crus(
            "async def f(db, result):\n"
            "    await db.clients.update_one(\n"
            "        {'id': 1}, {'$set': {'s3_folder': result}}\n"
            "    )\n",
            "especime.py",
        )
        assert len(achados) == 1, achados

    def test_a_guarda_morde_um_INSERT_cru(self):
        achados = escritores_crus(
            "async def f(db, result):\n"
            "    doc = {'id': 1, 's3_folder': result}\n"
            "    await db.processes.insert_one(doc)\n",
            "especime.py",
        )
        assert len(achados) == 1, achados

    def test_a_guarda_morde_um_nome_com_DUAS_origens(self):
        """A lição da mutação N11: um nome que recebe o valor cru NUM ramo
        chega ao `$set` por esse ramo, e a guarda não pode dar-lhe passe só
        porque o outro ramo está saneado."""
        achados = escritores_crus(
            "async def f(db, doc, mapping):\n"
            "    pasta = doc.get('s3_folder')\n"
            "    pasta = pasta_para_gravar(mapping['s3_folder'])\n"
            "    await db.clients.update_one({'id': 1}, {'$set': {'s3_folder': pasta}})\n",
            "especime.py",
        )
        assert len(achados) == 1, achados

    def test_a_guarda_NAO_morde_o_escritor_saneado(self):
        """Contraprova no sentido oposto: uma guarda que recuse tudo
        também passaria os testes de cima, e seria inútil."""
        assert not escritores_crus(
            "async def f(db, result):\n"
            "    caminho = pasta_para_gravar(result)\n"
            "    await db.clients.update_one(\n"
            "        {'id': 1}, {'$set': {'s3_folder': caminho}}\n"
            "    )\n",
            "especime.py",
        )

    def test_a_guarda_ve_dentro_de_um_payload_com_NOME(self):
        """`{"$set": update_fields}` — o ponto cego que a contraprova achou."""
        achados = escritores_crus(
            "async def f(db, result):\n"
            "    update_fields = {'s3_folder': result}\n"
            "    await db.processes.update_one({'id': 1}, {'$set': update_fields})\n",
            "especime.py",
        )
        assert len(achados) == 1, achados

    def test_a_guarda_NAO_morde_uma_CONSULTA_por_s3_folder(self):
        """`{"s3_folder": antigo}` é o filtro, não o documento."""
        assert not escritores_crus(
            "async def f(db, antigo, novo):\n"
            "    await db.processes.update_one(\n"
            "        {'s3_folder': antigo}, {'$set': {'status': novo}}\n"
            "    )\n",
            "especime.py",
        )

    def test_a_guarda_NAO_morde_uma_PROJECCAO(self):
        assert not escritores_crus(
            "async def f(db):\n"
            "    await db.processes.find_one({'id': 1}, {'s3_folder': 1})\n",
            "especime.py",
        )


class TestOsEnvolucros:
    """Cada nome na lista de saneadores chama MESMO o ponto único.

    Sem isto, a lista `SANEADORES` é uma porta: bastava acrescentar-lhe o
    nome de uma função que não valida nada para a guarda deixar de morder
    — e a saída óbvia, quando ela fica vermelha, é exactamente essa.
    """

    @pytest.mark.parametrize(
        "modulo,funcao",
        [
            ("services.admin_s3_process_mappings", "_clean_s3_folder"),
            ("services.s3_relink", "validar_pasta"),
        ],
    )
    def test_o_envolucro_chama_o_ponto_unico(self, modulo, funcao):
        import importlib

        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        alvo = getattr(importlib.import_module(modulo), funcao)
        assert "pasta_para_gravar" in codigo_da_funcao_sem_comentarios(alvo)

    @pytest.mark.parametrize("valor", VALORES_DO_TIPO_ERRADO)
    def test_o_envolucro_dos_mapeamentos_RECUSA_em_vez_de_apagar(self, valor):
        """A inversão do Lote 8: devolver `None` escrevia `None` no `$set`
        e apagava a pasta da ficha."""
        from services.admin_s3_process_mappings import _clean_s3_folder

        with pytest.raises(PastaGravadaInvalida):
            _clean_s3_folder(valor)

    @pytest.mark.parametrize("valor", ["undefined", "null", "None", "", None])
    def test_os_sentinelas_de_texto_continuam_a_virar_None(self, valor):
        """Contraprova: a recusa é sobre o TIPO. `"undefined"` que o
        frontend envia continua a significar «sem mapeamento»."""
        from services.admin_s3_process_mappings import _clean_s3_folder

        assert _clean_s3_folder(valor) is None

    def test_uma_pasta_real_continua_a_ser_aceite(self):
        from services.admin_s3_process_mappings import _clean_s3_folder

        assert _clean_s3_folder("Documentação Clientes/abc") == (
            "Documentação Clientes/abc"
        )


# ─────────────── o comportamento, a correr o código ───────────────


class TestOComportamentoDosEscritores:
    """O que uma guarda de fonte não consegue afirmar: que NÃO gravou.

    O inventário prova que o primitivo está no caminho; não prova o que
    acontece quando ele recusa. E o que acontece é a metade que importa:
    a ficha tem de ficar com a pasta que já tinha.
    """

    @pytest.mark.parametrize("valor", VALORES_DO_TIPO_ERRADO)
    async def test_o_mapeamento_de_utilizador_recusa_com_400_e_NAO_grava(
        self, fake_async_db, valor
    ):
        from unittest.mock import patch

        from fastapi import HTTPException

        from services import admin_s3_user_mappings as alvo

        await fake_async_db.users.insert_one(
            {"id": "u1", "name": "Ana", "s3_folder": "Documentação Clientes/u1"}
        )

        with patch.object(alvo, "db", fake_async_db):
            with pytest.raises(HTTPException) as erro:
                await alvo.run_update_user_s3_mapping("u1", valor, {"id": "admin"})

        assert erro.value.status_code == 400
        assert type(valor).__name__ in str(erro.value.detail)

        guardado = await fake_async_db.users.find_one({"id": "u1"})
        assert guardado["s3_folder"] == "Documentação Clientes/u1", (
            "A pasta que já estava gravada não pode desaparecer por causa "
            "de um valor do tipo errado — era o que o `None` fazia."
        )

    async def test_o_mapeamento_de_utilizador_continua_a_gravar_o_caso_normal(
        self, fake_async_db
    ):
        """Contraprova: uma guarda que recuse tudo passaria o teste de cima."""
        from unittest.mock import patch

        from services import admin_s3_user_mappings as alvo

        await fake_async_db.users.insert_one({"id": "u1", "name": "Ana"})

        with patch.object(alvo, "db", fake_async_db):
            resposta = await alvo.run_update_user_s3_mapping(
                "u1", "  Documentação Clientes/u1  ", {"id": "admin"}
            )

        assert resposta["s3_folder"] == "Documentação Clientes/u1"
        guardado = await fake_async_db.users.find_one({"id": "u1"})
        assert guardado["s3_folder"] == "Documentação Clientes/u1"

    async def test_remover_o_mapeamento_de_utilizador_continua_a_funcionar(
        self, fake_async_db
    ):
        """`None` é a remoção EXPLÍCITA; recusá-la fechava uma operação
        legítima do painel de Manutenção."""
        from unittest.mock import patch

        from services import admin_s3_user_mappings as alvo

        await fake_async_db.users.insert_one(
            {"id": "u1", "s3_folder": "Documentação Clientes/u1"}
        )

        with patch.object(alvo, "db", fake_async_db):
            resposta = await alvo.run_update_user_s3_mapping(
                "u1", None, {"id": "admin"}
            )

        assert resposta["s3_folder"] is None
        guardado = await fake_async_db.users.find_one({"id": "u1"})
        assert guardado["s3_folder"] is None

    @pytest.mark.parametrize("valor", VALORES_DO_TIPO_ERRADO)
    async def test_o_mapeamento_de_processo_recusa_com_400_e_NAO_grava(
        self, fake_async_db, valor
    ):
        from unittest.mock import patch

        from fastapi import HTTPException

        from services import admin_s3_process_mappings as alvo

        await fake_async_db.processes.insert_one(
            {"id": "p1", "client_name": "Ana",
             "s3_folder": "Documentação Clientes/c1"}
        )

        with patch.object(alvo, "db", fake_async_db):
            with pytest.raises(HTTPException) as erro:
                await alvo.run_update_process_s3_mapping("p1", valor, {"id": "admin"})

        assert erro.value.status_code == 400
        guardado = await fake_async_db.processes.find_one({"id": "p1"})
        assert guardado["s3_folder"] == "Documentação Clientes/c1"

    @pytest.mark.parametrize("valor", VALORES_DO_TIPO_ERRADO)
    async def test_o_LOTE_recusa_a_ficha_errada_e_NAO_toca_nas_outras(
        self, fake_async_db, valor
    ):
        """O caminho por onde o lixo entrou: `mappings: List[dict] = Body(...)`
        — um `dict` não é validado pelo FastAPI.

        Um lote parcialmente mau grava o que está bom e REPORTA o resto:
        rebentar o lote inteiro fazia uma gralha num item desfazer o
        trabalho dos outros.
        """
        from unittest.mock import patch

        from services import admin_s3_process_mappings as alvo

        await fake_async_db.processes.insert_one(
            {"id": "mau", "s3_folder": "Documentação Clientes/antiga"}
        )
        await fake_async_db.processes.insert_one({"id": "bom"})

        with patch.object(alvo, "db", fake_async_db):
            resultado = await alvo.run_batch_update_process_s3_mappings(
                [
                    {"process_id": "mau", "s3_folder": valor},
                    {"process_id": "bom", "s3_folder": "Documentação Clientes/nova"},
                ],
                {"id": "admin"},
            )

        assert resultado["failed"] == 1
        assert resultado["updated"] == 1
        assert resultado["errors"][0]["process_id"] == "mau"
        assert type(valor).__name__ in resultado["errors"][0]["error"]

        mau = await fake_async_db.processes.find_one({"id": "mau"})
        assert mau["s3_folder"] == "Documentação Clientes/antiga"
        bom = await fake_async_db.processes.find_one({"id": "bom"})
        assert bom["s3_folder"] == "Documentação Clientes/nova"

    @pytest.mark.parametrize("valor", VALORES_DO_TIPO_ERRADO)
    def test_o_religamento_manual_recusa_com_400(self, valor):
        from fastapi import HTTPException

        from services.s3_relink import validar_pasta

        with pytest.raises(HTTPException) as erro:
            validar_pasta(valor)
        assert erro.value.status_code == 400

    def test_o_religamento_manual_continua_a_aceitar_uma_pasta_e_a_remocao(self):
        """Contraprova dupla: o caso normal e a remoção explícita (regra 5)."""
        from services.s3_relink import validar_pasta

        assert validar_pasta("Documentação Clientes/abc/") == (
            "Documentação Clientes/abc"
        )
        assert validar_pasta("") is None


class TestQuemRecusaEQuemDegrada:
    """A mesma guarda, dois destinos — e a pergunta que os separa.

    «Se o primitivo disparar AQUI, o utilizador vê um erro sobre algo que
    JÁ aconteceu?»

    * **Não** → é validação de entrada, e recusa-se com 400. Nada foi
      feito ainda, e quem enviou o valor é quem o pode corrigir.
    * **Sim** → apanha-se, registra-se e segue-se sem mapeamento. É a
      regra do `document_portal_revoke`: quando o `religar_apos_rename`
      corre, o objecto JÁ se moveu no S3; levantar mostraria um erro
      sobre uma operação bem sucedida E deixava o ponteiro
      desactualizado, que é o pior dos dois mundos. O mesmo vale para o
      Portal (um defeito nosso não se despeja em 500 na única superfície
      externa), para o auto-mapeamento (uma pasta má não aborta a
      varredura das outras) e para a criação de cliente/processo, que
      nunca rebenta por causa de uma pasta.

    O que NUNCA acontece em nenhum dos dois ramos é gravar o valor.
    """

    #: Transformam a recusa em 400 — nada foi feito, quem enviou corrige.
    RECUSAM = [
        ("services.admin_s3_process_mappings", "run_update_process_s3_mapping"),
        ("services.admin_s3_user_mappings", "run_update_user_s3_mapping"),
        ("services.s3_relink", "validar_pasta"),
    ]

    #: Apanham e seguem — o efeito no S3 (ou a inserção) já aconteceu.
    DEGRADAM = [
        ("services.s3_folder_relink", "religar_apos_rename"),
        ("services.portal_upload_ops", "run_generate_portal_upload_url"),
        ("services.admin_s3_client_mappings", "run_auto_map_client_s3_folders"),
        ("services.s3_mapping_on_create", "ensure_s3_mapping_for_entity"),
        ("services.document_misc", "run_initialize_folders"),
    ]

    def _fonte_da_funcao(self, modulo, funcao):
        import importlib

        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        return codigo_da_funcao_sem_comentarios(
            getattr(importlib.import_module(modulo), funcao)
        )

    @pytest.mark.parametrize("modulo,funcao", RECUSAM)
    def test_quem_valida_entrada_devolve_400(self, modulo, funcao):
        codigo = self._fonte_da_funcao(modulo, funcao)
        assert "PastaGravadaInvalida" in codigo or "pasta_para_gravar" in codigo
        assert "HTTPException" in codigo

    @pytest.mark.parametrize("modulo,funcao", DEGRADAM)
    def test_quem_corre_depois_do_efeito_APANHA_a_excepcao(self, modulo, funcao):
        """Sem este `except`, um defeito nosso virava 500 — num caminho em
        que o S3 (ou a base de dados) já mudou e não há nada a desfazer."""
        codigo = self._fonte_da_funcao(modulo, funcao)
        assert "PastaGravadaInvalida" in codigo, (
            f"{modulo}.{funcao} corre DEPOIS do efeito e tem de apanhar a "
            "recusa pelo nome, não propagá-la."
        )

    async def test_o_religamento_apos_rename_devolve_erro_e_NAO_rebenta(
        self, fake_async_db
    ):
        from unittest.mock import patch

        from services import s3_folder_relink as alvo

        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": "Documentação Clientes/antiga"}
        )

        with patch.object(alvo, "db", fake_async_db):
            resultado = await alvo.religar_apos_rename(
                "Documentação Clientes/antiga",
                [True, "Documentação Clientes/nova"],
            )

        assert resultado["erro"] is True
        assert resultado["processos"] == 0
        guardado = await fake_async_db.processes.find_one({"id": "p1"})
        assert guardado["s3_folder"] == "Documentação Clientes/antiga"

    async def test_o_religamento_apos_rename_continua_a_religar(self, fake_async_db):
        """Contraprova: uma guarda que recusasse tudo deixava o ponteiro
        para trás em TODOS os renames — e as 205 ligações partidas do
        Épico 10 são exactamente isso."""
        from unittest.mock import patch

        from services import s3_folder_relink as alvo

        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": "Documentação Clientes/antiga"}
        )

        with patch.object(alvo, "db", fake_async_db):
            resultado = await alvo.religar_apos_rename(
                "Documentação Clientes/antiga", "Documentação Clientes/nova"
            )

        assert resultado["erro"] is False
        assert resultado["processos"] == 1
        guardado = await fake_async_db.processes.find_one({"id": "p1"})
        assert guardado["s3_folder"] == "Documentação Clientes/nova"
