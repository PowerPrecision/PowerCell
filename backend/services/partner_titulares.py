"""De quem é cada documento: 1.º ou 2.º titular (Portal do Parceiro, Out 2026).

Num processo com dois compradores os documentos misturavam-se: o parceiro via «Cartão de Cidadão» três
vezes sem saber de quem. Aqui vive a regra (PURA) que decide a que titular pertence um pedido ou um ficheiro:

* **só há titulares a distinguir quando há 2.º titular** — com um comprador só, nenhuma etiqueta (ruído);
* um **marcador explícito** (`titular`) vence — é o que o parceiro escolhe ao enviar, ou o que a equipa gravar;
* sem marcador, o `client_id` do documento: o do 2.º cliente é do 2.º titular (um envio do Portal feito pelo
  próprio 2.º titular chega assim);
* um **pedido** sem marcador e sem 2.º cliente NÃO se atribui a ninguém — o pedido da checklist pertence ao
  cliente registado, mas pode servir os dois, e afirmar «1.º titular» seria inventar. Um ficheiro sem marcador
  cai no 1.º titular (é o registo que o originou).

O nome do 2.º titular sai para o ecrã (o parceiro foi quem o escreveu); nada mais da ficha sai daqui.
"""
from __future__ import annotations

from typing import Any, Optional

TITULAR_1 = "titular1"
TITULAR_2 = "titular2"
TITULARES_VALIDOS = (TITULAR_1, TITULAR_2)
ROTULOS = {TITULAR_1: "1.º titular", TITULAR_2: "2.º titular"}

#: O valor de `compra_tipo` que liga o 2.º titular numa lead (igual a `partner_client_form.VALOR_DO_SEGUNDO_TITULAR`;
#: há um teste a afirmá-lo — não se importa de lá porque `partner_client_form` importa este módulo por via do detalhe).
_VALOR_DE_COMPRA_COM_OUTRA_PESSOA = "outra_pessoa"


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def titular_marcado(valor: Any) -> Optional[str]:
    """O marcador, se for um dos dois valores conhecidos; qualquer outra coisa não é um marcador."""
    texto = _texto(valor)
    return texto if texto in TITULARES_VALIDOS else None


def _nome_do_segundo(origem: dict) -> str:
    dados = origem.get("titular2_data") if isinstance(origem.get("titular2_data"), dict) else {}
    return _texto(origem.get("second_client_name")) or _texto(dados.get("name")) or _texto(dados.get("nome"))


def tem_segundo_titular(caso: Any) -> bool:
    """O caso tem dois compradores?"""
    if getattr(caso, "e_processo", False):
        proc = caso.process or {}
        return bool(_texto(proc.get("second_client_id")) or _nome_do_segundo(proc))
    cliente = caso.client or {}
    dados = cliente.get("dados_pessoais") if isinstance(cliente.get("dados_pessoais"), dict) else {}
    return dados.get("compra_tipo") == _VALOR_DE_COMPRA_COM_OUTRA_PESSOA or bool(_nome_do_segundo(cliente))


def titulares_do_caso(caso: Any) -> list[dict]:
    """`[{id, label, nome}]` — vazio quando só há um comprador (nada a distinguir)."""
    if not tem_segundo_titular(caso):
        return []
    if getattr(caso, "e_processo", False):
        primeiro = _texto((caso.process or {}).get("client_name"))
        segundo = _nome_do_segundo(caso.process or {})
    else:
        primeiro = _texto((caso.client or {}).get("nome"))
        segundo = _nome_do_segundo(caso.client or {})
    return [
        {"id": TITULAR_1, "label": ROTULOS[TITULAR_1], "nome": primeiro or None},
        {"id": TITULAR_2, "label": ROTULOS[TITULAR_2], "nome": segundo or None},
    ]


def titular_do_documento(
    caso: Any,
    *,
    marcado: Any = None,
    client_id: Any = None,
    e_pedido: bool = False,
) -> Optional[str]:
    """A que titular pertence um pedido (`e_pedido`) ou um ficheiro. ``None`` = não se distingue."""
    if not tem_segundo_titular(caso):
        return None
    explicito = titular_marcado(marcado)
    if explicito:
        return explicito
    segundo_id = _texto((getattr(caso, "process", None) or {}).get("second_client_id"))
    if segundo_id and _texto(client_id) == segundo_id:
        return TITULAR_2
    return None if e_pedido else TITULAR_1


def rotulo(titular: Optional[str]) -> Optional[str]:
    return ROTULOS.get(titular or "")


__all__ = [
    "ROTULOS",
    "TITULARES_VALIDOS",
    "TITULAR_1",
    "TITULAR_2",
    "rotulo",
    "tem_segundo_titular",
    "titular_do_documento",
    "titular_marcado",
    "titulares_do_caso",
]
