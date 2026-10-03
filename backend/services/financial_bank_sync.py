"""
====================================================================
CRÉDITOS ATIVOS → CONTAS BANCÁRIAS (sincronização no BACKEND)
====================================================================
Lote 2, ponto 3.

A REGRA DE NEGÓCIO
  Ter um crédito num banco implica ter conta nesse banco. Logo, um banco
  que entre em «Bancos com créditos ativos» (`bancos_creditos`) tem de
  aparecer em «Bancos com contas abertas» (`tem_creditos_activos`).

ONDE É QUE ISTO ESTAVA, E PORQUE É QUE NÃO SERVIA
  A regra existia — dentro do `executeSave` do `pages/ProcessDetails.js`,
  no FRONTEND. Corria quando um humano carregava em Gravar naquela
  página, e só então. Todos os outros escritores de `financial_data`
  passavam ao lado:

    · a IA (`build_update_data_from_extraction`), que é precisamente
      quem preenche os créditos a partir do mapa de responsabilidades
      do Banco de Portugal — o caso MAIS comum de todos;
    · o motor financeiro, o `ai-apply-suggestions`, o `ai_bulk`;
    · qualquer importação ou script.

  É a lição do `assigned_to` noutro eixo: **a regra vivia num ecrã e não
  na escrita**, por isso era invisível para o trabalho que não passava
  por aquele botão. E não dava erro nenhum — a lista ficava só
  incompleta, que é o tipo de defeito que ninguém reporta.

  Pior detalhe do bloco antigo: mutava `financialData` em sítio E
  chamava `setFinancialData`. Era a MUTAÇÃO que o fazia funcionar (o
  `setState` é assíncrono e não chegaria a tempo do payload) — o que
  significa que o código parecia idiomático e dependia do contrário.

A SOBREPOSIÇÃO DE NOMES — TRÊS CAMPOS, NÃO DOIS
  `bancos_creditos`      → o que o formulário recolhe: `[{banco, valor}]`
                           ou `["CGD"]` (legado).
  `creditos_ativos`      → o que a IA extrai do CRC: `[{instituicao, …}]`.
  `tem_creditos_activos` → o destino: `["CGD", …]`, ou um BOOLEANO no
                           legado.

  Os dois primeiros respondem à mesma pergunta com chaves diferentes
  (`banco` vs `instituicao`), e quem lê um esquece-se do outro — foi o
  que aconteceu ao bloco do frontend, que só conhecia `bancos_creditos`.
  Aqui a extracção do nome é UMA função, e reconhece as duas chaves.

DUAS COISAS QUE ESTA SINCRONIZAÇÃO NUNCA FAZ
  1. **Nunca remove.** Só acrescenta. Uma conta inserida à mão que não
     tenha crédito associado é informação legítima; apagá-la por não
     aparecer nos créditos destruía trabalho humano em silêncio (a regra
     das tarefas órfãs do Lote 4, aqui outra vez).
  2. **Nunca devolve uma alteração que não existe.** Sem nada a
     acrescentar devolve `None`, e o chamador não escreve — senão cada
     gravação carimbava `updated_at` e enchia a auditoria com diffs
     vazios.

O BOOLEANO DO LEGADO
  `tem_creditos_activos` já foi um sim/não. Um booleano não carrega nome
  de banco nenhum, logo é tratado como "sem nomes registados" e a lista
  derivada toma o seu lugar. Inclui o `False`: a regra de negócio diz
  que um crédito num banco implica conta nesse banco, e o `False` é uma
  resposta a uma pergunta que já não é a mesma.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Campos de ORIGEM: onde vivem os créditos activos do cliente.
CAMPOS_DE_CREDITOS: tuple[str, ...] = ("bancos_creditos", "creditos_ativos")

# Campo de DESTINO: os bancos onde o cliente tem conta aberta.
CAMPO_DE_CONTAS: str = "tem_creditos_activos"

# As chaves com que cada origem guarda o nome da instituição. Duas
# origens, dois nomes para a mesma coisa — e é por isso que isto é uma
# constante e não um `item.get("banco")` escrito em cada sítio.
CHAVES_DO_NOME: tuple[str, ...] = ("banco", "instituicao", "institution", "nome")


def nome_do_banco(item: Any) -> str:
    """O nome do banco de uma entrada de crédito, seja ela texto ou dicionário."""
    if isinstance(item, dict):
        for chave in CHAVES_DO_NOME:
            valor = item.get(chave)
            if valor is not None and str(valor).strip():
                return str(valor).strip()
        return ""
    if item is None:
        return ""
    return str(item).strip()


def _chave_de_comparacao(nome: str) -> str:
    """Para comparar sem distinguir maiúsculas nem espaços nas extremidades.

    A comparação normaliza; o que se GRAVA é o nome original — baixar a
    caixa ao gravar mudava o que o utilizador vê no ecrã.
    """
    return nome.lower().strip()


def _nomes_de(valores: Any) -> list[str]:
    if not isinstance(valores, (list, tuple, set)):
        return []
    nomes = []
    for item in valores:
        nome = nome_do_banco(item)
        if nome:
            nomes.append(nome)
    return nomes


def nomes_de_bancos_com_credito(financial_data: Optional[dict]) -> list[str]:
    """Bancos onde o cliente tem crédito, das DUAS origens, sem repetidos."""
    dados = financial_data if isinstance(financial_data, dict) else {}
    vistos: dict[str, str] = {}
    for campo in CAMPOS_DE_CREDITOS:
        for nome in _nomes_de(dados.get(campo)):
            vistos.setdefault(_chave_de_comparacao(nome), nome)
    return list(vistos.values())


def contas_abertas(financial_data: Optional[dict]) -> list[str]:
    """As contas já registadas. Um booleano do legado conta como vazio."""
    dados = financial_data if isinstance(financial_data, dict) else {}
    return _nomes_de(dados.get(CAMPO_DE_CONTAS))


def contas_sincronizadas(financial_data: Optional[dict]) -> Optional[list[str]]:
    """A nova lista de contas, ou ``None`` se não houver nada a acrescentar.

    O ``None`` é deliberado: distingue "não há alteração" de "a lista
    passou a ser esta", e é o que impede uma gravação inútil em cada
    save.
    """
    com_credito = nomes_de_bancos_com_credito(financial_data)
    if not com_credito:
        return None

    existentes = contas_abertas(financial_data)
    conhecidos = {_chave_de_comparacao(n) for n in existentes}

    resultado = list(existentes)
    for nome in com_credito:
        if _chave_de_comparacao(nome) not in conhecidos:
            resultado.append(nome)
            conhecidos.add(_chave_de_comparacao(nome))

    if resultado == existentes:
        return None
    return resultado


def sincronizar_contas_bancarias(financial_data: Optional[dict]) -> dict:
    """Devolve ``financial_data`` com as contas bancárias sincronizadas.

    Devolve sempre um dicionário NOVO — não muta o que recebe. O bloco
    antigo do frontend mutava o estado em sítio e era essa mutação que o
    fazia funcionar; aqui a função é pura e o chamador decide o que
    grava.
    """
    dados = dict(financial_data) if isinstance(financial_data, dict) else {}
    novas = contas_sincronizadas(dados)
    if novas is None:
        return dados

    dados[CAMPO_DE_CONTAS] = novas
    logger.debug(
        "[BANCOS] Contas sincronizadas a partir dos créditos activos: %s", novas
    )
    return dados


def aplicar_a_update_data(update_data: dict, *, chave: str = "financial_data") -> dict:
    """Sincroniza o `financial_data` que já está dentro de um `update_data`.

    Atalho para os escritores: não toca em nada quando a chave não vem
    no lote (uma actualização que não mexe nos dados financeiros não tem
    de passar a mexer).
    """
    if not isinstance(update_data, dict):
        return update_data
    actual = update_data.get(chave)
    if not isinstance(actual, dict):
        return update_data
    update_data[chave] = sincronizar_contas_bancarias(actual)
    return update_data
