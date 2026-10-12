"""
====================================================================
COLISÃO B2B (CROSS-NETWORK): QUEM É O MESMO CLIENTE NA REDE DE DESTINO
====================================================================
Quando um registo vindo de FORA da rede (hoje: a lead que um parceiro
submete a uma «Empresa de Destino») chega à equipa do destino, o cliente pode
já existir lá. Duas perguntas, duas regras.

1. QUEM É O MESMO CLIENTE — HIERARQUIA DE IDENTIFICAÇÃO
   * Procura-se **primeiro pelo NIF**. Se o NIF coincide, é o mesmo cliente.
   * Só se o NIF vier **vazio/ausente** se procura pelo **Email**.
   * Um NIF PRESENTE que não coincide com ninguém NÃO cai para o email:
     o NIF identifica a pessoa, e o mesmo email com outro NIF é outra pessoa
     (uma família partilha o email). Fica como «possível duplicado» para a
     triagem decidir — que é o que a submissão já fazia.
   * O telemóvel nunca identifica: partilha-se (família, escritório).
   * A procura vive na rede de destino e só vê clientes activos (a mesma
     condição do D-38, `client_uniqueness`).

2. O QUE SE FAZ COM UM MATCH — A REDE DE DESTINO É SOBERANA
   Associa-se o registo ao cliente existente, mas **nada do que está gravado
   no destino é alterado**: nem o email, nem o telemóvel, nem o NIF, nem o
   nome, nem o estado de lead. (Re-marcar o cliente como lead novo foi
   precisamente o defeito do formulário público que o D-32 corrigiu.)
   O que o destino fica a saber — só a equipa, nunca o parceiro — vai numa
   entrada ACRESCENTADA a `partner_leads`, com os NOMES dos campos em que os
   contactos enviados divergem dos gravados (nunca os valores: o destino já
   tem os seus, e os de fora são dados pessoais de quem a equipa não tem
   relação).

   O parceiro não vê diferença nenhuma: o registo dele passa a «submetido»
   como qualquer outro, sem o `id` do cliente existente (seria um oráculo
   de «este cliente já existe na rede X»).

O QUE NÃO SE FAZ
   * Não se **move** nem se **re-aponta** nada: os ficheiros que o parceiro
     enviou ficam na pasta do registo dele (mover objectos S3 foi o que
     partiu 205 ligações no Épico 10). A entrada guarda `pasta_dos_documentos`
     para a consolidação manual (`s3_relink`).
   * Não se atribui o parceiro ao cliente existente (`submitted_by_partner_id`):
     o parceiro passaria a ver, no portal dele, um cliente que não é seu.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.client_uniqueness import encontrar_cliente_duplicado, so_o_que_mudou

logger = logging.getLogger(__name__)

POR_NIF = "nif"
POR_EMAIL = "email"

#: Os contactos que a rede de destino preserva. O NIF e o nome também não se
#: tocam, mas só os contactos podem divergir sem que o NIF seja a chave.
CAMPOS_DE_CONTACTO = ("email", "telefone")


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def dados_de_identificacao(lead: dict) -> tuple[str, str, str]:
    """(NIF, email, telemóvel) de uma lead JÁ desencriptada, aparados."""
    dados = lead.get("dados_pessoais") or {}
    contacto = lead.get("contacto") or {}
    return _texto(dados.get("nif")), _texto(contacto.get("email")), _texto(contacto.get("telefone"))


async def encontrar_cliente_de_destino(
    lead: dict, *, rede: Optional[str],
) -> tuple[Optional[dict], Optional[str]]:
    """O cliente da rede de destino que É este, e por que critério.

    ``lead`` vem desencriptada. Devolve ``(cliente, "nif"|"email")`` ou
    ``(None, None)``. O NIF decide primeiro; o email só entra sem NIF.
    """
    nif, email, _telefone = dados_de_identificacao(lead)
    if nif:
        existente = await encontrar_cliente_duplicado(nif, None, None, rede=rede)
        return (existente, POR_NIF) if existente else (None, None)
    if email:
        existente = await encontrar_cliente_duplicado(None, email, None, rede=rede)
        return (existente, POR_EMAIL) if existente else (None, None)
    return None, None


def campos_divergentes(existente: dict, lead: dict) -> list[str]:
    """Quais dos contactos enviados DIFEREM dos gravados no destino (só nomes)."""
    _nif, email, telefone = dados_de_identificacao(lead)
    _n, email_novo, telefone_novo = so_o_que_mudou(existente, None, email or None, telefone or None)
    divergentes = []
    if email_novo:
        divergentes.append("email")
    if telefone_novo:
        divergentes.append("telefone")
    return divergentes


def entrada_de_associacao(
    *, lead: dict, existente: dict, por: str, comprovativo: Optional[dict], quando: str,
) -> dict:
    """A entrada acrescentada ao cliente existente. Sem NENHUM dado pessoal."""
    return {
        "lead_id": lead.get("id"),
        "partner_id": lead.get("submitted_by_partner_id"),
        "partner_name": lead.get("submitted_by_partner_name"),
        "empresa_destino": lead.get("company_name"),
        "associada_por": por,
        "campos_divergentes": campos_divergentes(existente, lead),
        "comprovativo": {
            "file_id": (comprovativo or {}).get("file_id"),
            "filename": (comprovativo or {}).get("filename"),
            "uploaded_at": (comprovativo or {}).get("uploaded_at"),
        },
        # Os ficheiros do parceiro ficam onde foram enviados (nada se move).
        "pasta_dos_documentos_do_lead": lead.get("id"),
        "em": quando,
    }


__all__ = [
    "CAMPOS_DE_CONTACTO",
    "POR_EMAIL",
    "POR_NIF",
    "campos_divergentes",
    "dados_de_identificacao",
    "encontrar_cliente_de_destino",
    "entrada_de_associacao",
]
