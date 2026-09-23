"""
Leitura de código-fonte para guardas sobre o CÓDIGO (não sobre o comportamento).

PORQUE É QUE ISTO EXISTE
  Algumas regras deste projecto não se conseguem provar com um teste de
  comportamento: se o transporte estiver falseado, um `fetch` e um
  `api.get` são indistinguíveis, e um `db` falseado não distingue quem
  reconstruiu uma condição à mão de quem a pediu ao ponto único. Nesses
  casos a guarda afirma sobre o texto do módulo.

A ARMADILHA, JÁ APANHADA DUAS VEZES
  Uma guarda que leia os comentários acaba por proibir a EXPLICAÇÃO do
  defeito que previne — e a saída óbvia, quando fica vermelha, é apagar
  a explicação, que é precisamente a parte que impede a regressão de
  voltar. Por isso os comentários e as docstrings saem ANTES da procura.

  `tokenize` trata as cadeias de caracteres com o mesmo cuidado que o
  interpretador: uma expressão regular ingénua sobre `#` cortaria a meio
  de um literal que contivesse o símbolo.
"""
from __future__ import annotations

import ast
import inspect
import io
import textwrap
import tokenize


def codigo_sem_comentarios(fonte: str) -> str:
    """Devolve `fonte` sem comentários nem docstrings.

    Aceita o texto de um módulo inteiro ou de uma função já extraída.
    Se o texto não for Python analisável (um ficheiro parcial, por
    exemplo), devolve-o apenas sem comentários — uma guarda nunca pode
    rebentar a bateria por causa da sua própria ferramenta.
    """
    texto = textwrap.dedent(fonte)

    try:
        tokens = [
            token[:2]
            for token in tokenize.generate_tokens(io.StringIO(texto).readline)
            if token.type != tokenize.COMMENT
        ]
        sem_comentarios = tokenize.untokenize(tokens)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return texto

    try:
        arvore = ast.parse(textwrap.dedent(sem_comentarios))
    except SyntaxError:
        return sem_comentarios

    for no in ast.walk(arvore):
        if isinstance(
            no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ) and ast.get_docstring(no):
            no.body = no.body[1:]

    return ast.unparse(arvore)


def codigo_da_funcao_sem_comentarios(funcao) -> str:
    """Código de uma função (ou método), sem comentários nem docstrings."""
    return codigo_sem_comentarios(inspect.getsource(funcao))
