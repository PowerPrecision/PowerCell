"""D-15 — migração das datas de nascimento existentes (parte PURA).

``scripts/migrar_datas_de_nascimento.py`` lê a base de dados e escreve; o que
decide O QUE escrever vive aqui, sem I/O, para ser testado com documentos
reais gerados pela mesma cadeia de produção.

Para cada pessoa do documento que tenha uma data de nascimento:

* **em claro** (ISO, `datetime` BSON, ou texto que não é data) → cifra-se o
  valor e grava-se o ``birth_year`` ao lado (``None`` se o texto não for uma
  data: o ano de uma coisa que não é data não existe);
* **cifrada** → só se acrescenta/corrige o ``birth_year`` (uma passagem
  anterior interrompida a meio, ou um escritor antigo que cifrou sem ano);
* **vazia** → só se limpa um ``birth_year`` que tenha sobrevivido a ela;
* **cifrada mas ilegível** (chave diferente da usada a cifrar) → NÃO se toca:
  escrever aqui um ano ``None`` ou voltar a cifrar destruiria o dado.

É idempotente: um documento já migrado dá um plano vazio.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from services.birthdate_exposure_audit import (
    CIFRADO,
    ISO,
    OUTRO,
    VAZIO,
    estado_do_valor,
)
from services.encryption import encryption_service, is_encrypted
from services.nascimento_protegido import (
    _como_texto,
    ano_de,
    caminhos_com_data_de_nascimento,
    revelar,
)
from services.sub35 import CAMPO_DO_ANO

#: Contadores do relatório.
A_CIFRAR = "a_cifrar"
ANO_A_CARIMBAR = "ano_a_carimbar"
ANO_A_LIMPAR = "ano_a_limpar"
ILEGIVEIS = "ilegiveis"
JA_MIGRADOS = "ja_migrados"

#: Projecção que a migração lê: só o que tem pessoas (e o `_id` para escrever).
PROJECCAO = {
    "personal_data": 1,
    "dados_pessoais": 1,
    "titular2_data": 1,
    "co_buyers": 1,
    "co_applicants": 1,
    "birth_date": 1,
    "data_nascimento": 1,
    CAMPO_DO_ANO: 1,
}


@dataclass
class PlanoDoDocumento:
    """O que escrever num documento, e sob que condição."""

    definir: dict = field(default_factory=dict)
    #: caminho → valor ORIGINAL; vai para o filtro do `update_one`, para uma
    #: edição que chegue a meio da migração não ser pisada.
    condicao: dict = field(default_factory=dict)
    contagem: Counter = field(default_factory=Counter)

    @property
    def vazio(self) -> bool:
        return not self.definir


def _ler_no_caminho(doc: dict, caminho: str) -> Any:
    actual: Any = doc
    for parte in caminho.split("."):
        if isinstance(actual, list):
            try:
                actual = actual[int(parte)]
            except (ValueError, IndexError):
                return None
        elif isinstance(actual, dict):
            actual = actual.get(parte)
        else:
            return None
    return actual


def _caminho_do_ano(caminho_da_data: str) -> str:
    prefixo = caminho_da_data.rsplit(".", 1)[0] if "." in caminho_da_data else ""
    return f"{prefixo}.{CAMPO_DO_ANO}" if prefixo else CAMPO_DO_ANO


def planear(doc: dict) -> PlanoDoDocumento:
    """O plano de migração de UM documento (não escreve nada)."""
    plano = PlanoDoDocumento()
    anos_por_pessoa: dict[str, list[Any]] = {}
    for caminho, valor in caminhos_com_data_de_nascimento(doc):
        anos_por_pessoa.setdefault(_caminho_do_ano(caminho), []).append((caminho, valor))

    for caminho_do_ano, datas in anos_por_pessoa.items():
        # Uma pessoa pode ter os DOIS nomes do campo (birth_date e data_nascimento).
        ano_gravado = _ler_no_caminho(doc, caminho_do_ano)
        ano_certo: Any = None
        mexeu = False
        for caminho, valor in datas:
            estado = estado_do_valor(valor)
            if estado == VAZIO:
                continue
            if estado == CIFRADO:
                lido = ano_de(valor)
                if revelar(valor) is not None and is_encrypted(str(revelar(valor))):
                    plano.contagem[ILEGIVEIS] += 1
                    continue
                if lido is not None and ano_certo is None:
                    ano_certo = lido
                continue
            # em claro (ISO, datetime, outro)
            texto = _como_texto(valor)
            if not texto:
                continue
            ano = ano_de(texto)
            if ano is not None and ano_certo is None:
                ano_certo = ano
            plano.definir[caminho] = encryption_service.encrypt(texto)
            plano.condicao[caminho] = valor
            plano.contagem[A_CIFRAR] += 1
            mexeu = True

        if ano_certo != ano_gravado:
            if ano_certo is None and any(
                estado_do_valor(v) == CIFRADO for _, v in datas
            ):
                # Só cifras ilegíveis: não se apaga o ano que lá está.
                continue
            plano.definir[caminho_do_ano] = ano_certo
            plano.condicao[caminho_do_ano] = ano_gravado
            plano.contagem[ANO_A_LIMPAR if ano_certo is None else ANO_A_CARIMBAR] += 1
            mexeu = True
        if not mexeu and any(estado_do_valor(v) != VAZIO for _, v in datas):
            plano.contagem[JA_MIGRADOS] += 1
    return plano


def filtro_de_escrita(doc_id: Any, plano: PlanoDoDocumento) -> dict:
    """O filtro do `update_one`: o `_id` e cada caminho com o valor que se leu.

    Um caminho que não existia (`ano_gravado` é `None` por ausência) entra
    como ``None``, que no Mongo casa com ausente e com ``null``.
    """
    return {"_id": doc_id, **plano.condicao}
