"""D-15 — a data de nascimento vive CIFRADA; o ANO fica ao lado, em claro.

Antes: a data estava em texto simples em `processes` e em `clients`, ao lado
de NIF, documento e telefone que já estavam cifrados — com o nome, é dos
campos que mais identifica uma pessoa. Cifrá-la partia o filtro Sub35, que
compara a data com um limite no Mongo (`$gte`/`$lt`).

A solução é a opção (a) da D-15: um campo derivado ``birth_year`` (INTEIRO, o
ano) gravado junto da data cifrada. Três razões para ser o ano e não outra
coisa:

* **o ano nunca muda** — uma idade, ou um booleano «é Sub35», fica errada no
  dia do aniversário (o defeito que o Lote 4 fechou); o ano não;
* **é menos identificador do que a data** (um ano de nascimento diz «nasceu
  nesta década», não «nasceu neste dia»), embora continue a ser um dado
  pessoal — a data completa deixa de existir em claro, o ano não;
* **a idade exacta continua a poder calcular-se**: a etiqueta (o que o
  consultor vê) decifra a data e usa o predicado exacto de `sub35`. O ano só
  alimenta o FILTRO do Mongo.

**O filtro por ano é deliberadamente mais estrito do que a etiqueta.** Quem
nasceu no ano ``Y`` com ``hoje.year - 35 <= Y <= hoje.year - 1`` é Sub35
seja qual for o dia (ver ``intervalo_de_anos``). O ano ``hoje.year - 36`` é a
margem: depende do dia e do mês, que o filtro já não vê. Fica de fora do
filtro (e dentro da etiqueta). O erro vai no sentido seguro — o filtro nunca
mostra uma linha sem etiqueta; pode deixar de mostrar uma que a tem.

Este módulo tem a parte que ESCREVE (carimbar o ano, proteger caminhos
pontuados) e a que LÊ (decifrar um valor gravado). A regra Sub35 e a condição
do Mongo vivem em ``services/sub35.py``.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable, Optional

from services.encryption import decrypt_value, encryption_service, is_encrypted
from services.sub35 import (
    CAMPOS_DE_NASCIMENTO,
    CAMPO_DO_ANO,
    data_iso,
)

logger = logging.getLogger(__name__)

#: Secções onde uma pessoa vive como DICIONÁRIO (processo e cliente).
SECCOES_COM_PESSOA = ("personal_data", "dados_pessoais", "titular2_data")

#: Listas de pessoas, com a data em cada elemento.
LISTAS_COM_PESSOAS = ("co_buyers", "co_applicants")


def revelar(valor: Any) -> Any:
    """O valor gravado, decifrado se for cifra; qualquer outra coisa passa.

    Uma cifra que não se consegue abrir (chave diferente da usada a cifrar)
    volta como está — quem chama vê que continua cifrada
    (``is_encrypted``) e trata-a como «data desconhecida», que na regra Sub35
    bloqueia (falha fechada).
    """
    if isinstance(valor, str) and is_encrypted(valor):
        return decrypt_value(valor)
    return valor


def _como_texto(valor: Any) -> Optional[str]:
    """O texto que se cifra: um `datetime` BSON vira `YYYY-MM-DD`."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    return texto or None


def ano_de(valor: Any) -> Optional[int]:
    """O ano de nascimento de um valor gravado (cifrado ou não), ou `None`."""
    iso = data_iso(revelar(valor))
    return int(iso[:4]) if iso else None


def _ano_da_pessoa(pessoa: dict) -> Optional[int]:
    for campo in CAMPOS_DE_NASCIMENTO:
        ano = ano_de(pessoa.get(campo))
        if ano is not None:
            return ano
    return None


def _carimbar_pessoa(pessoa: Any) -> None:
    """Põe `birth_year` numa pessoa que traga uma data de nascimento.

    Só mexe quando o dicionário TRAZ uma chave de data: uma actualização
    parcial sem data não pode apagar o ano que lá está. Se a data veio vazia
    (foi apagada) ou ilegível, o ano passa a `None` — um ano que sobrevivesse
    à data que o originou deixaria o filtro a achar quem já não tem data.
    """
    if not isinstance(pessoa, dict):
        return
    if not any(campo in pessoa for campo in CAMPOS_DE_NASCIMENTO):
        return
    pessoa[CAMPO_DO_ANO] = _ano_da_pessoa(pessoa)


def _pessoas_do_documento(doc: Any) -> Iterable[dict]:
    """Cada dicionário-pessoa do documento: secções, elementos das listas e a raiz."""
    if not isinstance(doc, dict):
        return
    for seccao in SECCOES_COM_PESSOA:
        if isinstance(doc.get(seccao), dict):
            yield doc[seccao]
    for lista in LISTAS_COM_PESSOAS:
        elementos = doc.get(lista)
        if isinstance(elementos, list):
            for elemento in elementos:
                if isinstance(elemento, dict):
                    yield elemento
    yield doc


def acrescentar_ano_de_nascimento(doc: Any) -> None:
    """Carimba `birth_year` no documento (no sítio), ANTES de cifrar.

    É o par do ``_add_*_blind_indexes``: corre sobre os valores originais (ou
    sobre cifras, que se abrem para ler o ano) em todas as funções de
    escrita que cifram — ``encrypt_client_data``, ``encrypt_sensitive_data`` e
    ``EncryptionService.encrypt_process``.

    Cobre o documento todo: secções (`personal_data`, `dados_pessoais`,
    `titular2_data`), listas (`co_buyers`, `co_applicants`) e a raiz (os
    processos antigos têm a data na raiz).
    """
    for pessoa in _pessoas_do_documento(doc):
        _carimbar_pessoa(pessoa)


def proteger_documento(doc: Any) -> None:
    """Ano + cifra, no sítio, para um documento (ou `$set` de secções) inteiro.

    Para os escritores que gravam secções INTEIRAS sem passar por
    ``encrypt_sensitive_data`` (a análise de documentos da IA devolve
    ``{"personal_data": {...}}``). Idempotente: o que já está cifrado fica.
    """
    for pessoa in _pessoas_do_documento(doc):
        _carimbar_pessoa(pessoa)
        for campo in CAMPOS_DE_NASCIMENTO:
            valor = pessoa.get(campo)
            if valor and not (isinstance(valor, str) and is_encrypted(valor)):
                texto = _como_texto(valor)
                if texto:
                    pessoa[campo] = encryption_service.encrypt(texto)


def _eh_campo_de_nascimento(caminho: str) -> bool:
    return caminho.rsplit(".", 1)[-1] in CAMPOS_DE_NASCIMENTO


def proteger_caminhos(update: dict) -> dict:
    """O mesmo para um dict de caminhos pontuados (`{"personal_data.birth_date": …}`).

    Para os escritores que fazem ``$set`` directo sem passar por
    ``encrypt_sensitive_data``/``encrypt_client_data`` (resolver um conflito
    da IA, sincronizar o cliente para os seus processos, espelhar o perfil do
    Portal). Devolve uma CÓPIA: cada campo de nascimento sai cifrado e leva ao
    lado o ``birth_year`` da mesma pessoa (mesmo prefixo).

    Idempotente: uma cifra já cifrada não se cifra outra vez, e o ano
    recalcula-se sobre o que lá está.
    """
    protegido = dict(update)
    for caminho, valor in update.items():
        if not isinstance(caminho, str) or not _eh_campo_de_nascimento(caminho):
            continue
        prefixo = caminho.rsplit(".", 1)[0] if "." in caminho else ""
        chave_do_ano = f"{prefixo}.{CAMPO_DO_ANO}" if prefixo else CAMPO_DO_ANO
        texto = _como_texto(revelar(valor))
        protegido[chave_do_ano] = ano_de(texto) if texto else None
        if texto and not is_encrypted(str(valor)):
            protegido[caminho] = encryption_service.encrypt(texto)
    return protegido


def caminhos_com_data_de_nascimento(doc: dict) -> Iterable[tuple[str, Any]]:
    """(caminho pontuado, valor) de cada data que o documento tem, listas incluídas.

    Os elementos das listas saem com o índice posicional (`co_buyers.0.birth_date`)
    para a migração os poder escrever com um `$set` directo.
    """
    def _da_pessoa(prefixo: str, pessoa: Any):
        if not isinstance(pessoa, dict):
            return
        for campo in CAMPOS_DE_NASCIMENTO:
            if campo in pessoa:
                yield (f"{prefixo}{campo}", pessoa.get(campo))

    for seccao in SECCOES_COM_PESSOA:
        yield from _da_pessoa(f"{seccao}.", doc.get(seccao))
    for lista in LISTAS_COM_PESSOAS:
        elementos = doc.get(lista)
        if isinstance(elementos, list):
            for i, elemento in enumerate(elementos):
                yield from _da_pessoa(f"{lista}.{i}.", elemento)
    yield from _da_pessoa("", doc)
