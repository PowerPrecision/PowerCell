"""Instituições bancárias do Index (Out 2026): um nome canónico por banco, para os extratos serem pesquisáveis.

POR QUE EXISTE
==============
A IA lê o banco como vem impresso no extrato («Caixa Geral de Depósitos, S.A.», «CGD», «Banco Santander
Totta»). Quem pesquisa escreve «cgd» ou «santander». Se o texto do extrato fosse o que se guarda e se
compara, «CGD» nunca encontraria a Caixa. Aqui cada banco conhecido tem uma CHAVE estável (`cgd`) e um
nome de apresentação; o texto lido e o texto pesquisado reduzem-se à mesma chave.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **O código dispõe, a IA propõe.** O nome lido pela IA só vale se for reconhecido; um banco que não
   conste da tabela guarda-se como o modelo o leu (limpo e cortado), com uma chave derivada do texto —
   continua pesquisável por nome, e uma tabela incompleta nunca esconde um banco.
2. **A pesquisa por palavras inteiras.** `bes` não pode casar com «Besta Bank» nem `bic` com «Bicicletas»:
   um alias só vale como palavra (ou sequência de palavras) completa.
3. **O IBAN só serve de recurso e só para o que se sabe de certeza.** O código do banco (4 dígitos a
   seguir a `PT50`) preenche o banco quando a IA não o leu. A tabela tem SÓ os códigos de que não há
   dúvida: um código errado atribuiria um extrato ao banco errado sem ninguém dar por isso, e um banco
   em falta é uma lacuna visível. O IBAN nunca é guardado: é dado da conta do cliente.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

#: chave → (nome de apresentação, aliases). Os aliases são o texto que aparece nos extratos ou que se escreve.
BANCOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "cgd": ("Caixa Geral de Depósitos", ("cgd", "caixa geral de depositos", "caixa geral", "caixadirecta")),
    "millennium": ("Millennium bcp", ("millennium bcp", "millennium", "millenniumbcp", "bcp",
                                      "banco comercial portugues")),
    "santander": ("Santander", ("santander", "santander totta", "banco santander totta", "banco santander", "totta")),
    "bpi": ("BPI", ("bpi", "banco bpi", "banco portugues de investimento")),
    "novo_banco": ("Novo Banco", ("novo banco", "novobanco", "bes", "banco espirito santo")),
    "activobank": ("ActivoBank", ("activobank", "activo bank")),
    "montepio": ("Montepio", ("montepio", "banco montepio", "caixa economica montepio geral")),
    "credito_agricola": ("Crédito Agrícola", ("credito agricola", "caixa agricola", "ccam",
                                              "caixa de credito agricola mutuo")),
    "banco_ctt": ("Banco CTT", ("banco ctt", "bctt")),
    "eurobic": ("EuroBic", ("eurobic", "banco bic", "bic portugues")),
    "bankinter": ("Bankinter", ("bankinter",)),
    "abanca": ("Abanca", ("abanca",)),
    "openbank": ("Openbank", ("openbank",)),
    "revolut": ("Revolut", ("revolut",)),
    "n26": ("N26", ("n26",)),
}

#: Código de banco do IBAN português → chave. Só os que não admitem dúvida (regra 3).
BANCO_PELO_CODIGO_DO_IBAN: dict[str, str] = {
    "0035": "cgd",
    "0033": "millennium",
    "0010": "bpi",
    "0007": "novo_banco",
    "0018": "santander",
    "0036": "montepio",
    "0023": "activobank",
}

TAMANHO_MAXIMO_DO_NOME = 80


def _normalizar(texto: Optional[str]) -> str:
    """Minúsculas, sem acentos nem pontuação, espaços únicos: a forma em que se compara."""
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or "").lower()) if unicodedata.category(c) != "Mn"
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acentos).split())


# (alias normalizado, chave), dos mais longos para os mais curtos: «santander totta» antes de «totta».
_ALIASES = sorted(
    ((_normalizar(alias), chave) for chave, (_, aliases) in BANCOS.items() for alias in aliases),
    key=lambda par: (-len(par[0]), par[0]),
)


def chave_do_banco(texto: Optional[str]) -> Optional[str]:
    """A chave do banco conhecido que o texto nomeia (palavras inteiras), ou `None`."""
    normal = _normalizar(texto)
    if not normal:
        return None
    contexto = f" {normal} "
    for alias, chave in _ALIASES:
        if f" {alias} " in contexto:
            return chave
    return None


def banco_do_iban(iban: Optional[str]) -> Optional[str]:
    """A chave do banco pelo código do IBAN PORTUGUÊS, ou `None` (IBAN estrangeiro, código fora da tabela)."""
    compacto = re.sub(r"\s+", "", str(iban or "")).upper()
    if not re.fullmatch(r"PT\d{2}\d{4}[A-Z0-9]{17}", compacto):
        return None
    return BANCO_PELO_CODIGO_DO_IBAN.get(compacto[4:8])


def _texto_limpo(texto: Optional[str]) -> Optional[str]:
    if texto is None or isinstance(texto, (dict, list, bool)):
        return None
    limpo = " ".join(re.sub(r"[<>`]", "", str(texto)).split())
    return limpo[:TAMANHO_MAXIMO_DO_NOME].strip() or None


def banco_do_extrato(nome_lido: Optional[str], iban: Optional[str] = None) -> dict[str, Optional[str]]:
    """`{"nome", "chave"}` do banco de um extrato. `{None, None}` se nem o texto nem o IBAN o dizem.

    Ordem: o que a IA leu e se reconhece → o que a IA leu e não se reconhece (como veio) → o IBAN.
    """
    chave = chave_do_banco(nome_lido)
    if chave:
        return {"nome": BANCOS[chave][0], "chave": chave}
    lido = _texto_limpo(nome_lido)
    if lido and len(_normalizar(lido)) >= 2:
        # banco fora da tabela: continua pesquisável pelo próprio texto
        return {"nome": lido, "chave": "outro:" + _normalizar(lido).replace(" ", "_")[:60]}
    pelo_iban = banco_do_iban(iban)
    if pelo_iban:
        return {"nome": BANCOS[pelo_iban][0], "chave": pelo_iban}
    return {"nome": None, "chave": None}


def chave_do_filtro(texto: Optional[str]) -> Optional[str]:
    """A chave de um banco conhecido para o texto pesquisado (`cgd`, «caixa geral»…), ou `None`."""
    return chave_do_banco(texto)


__all__ = ["BANCOS", "banco_do_extrato", "banco_do_iban", "chave_do_banco", "chave_do_filtro"]
